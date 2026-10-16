"""Etapa 4: proyección del año siguiente con tasas observadas (D-031).

El modelo congelado (D-030) no predice el xRV del año siguiente mejor que la historia del pitcher. Aquí
se prueba si las tasas observadas, que se estabilizan más rápido que el resultado en carreras, lo
logran. Los candidatos y la regla se fijaron antes de correr:

- persistencia: xRV del año pasado, encogido con una regresión (la base);
- valores: xRV, Stuff+ y Location+;
- tasas: xRV y tasas observadas (swing, whiff, persecución, zona, strike cantado, foul, contacto);
- todo: tasas más Stuff+, Location+ y los componentes predichos de Stuff+.

Agregados después de ver que ninguno de esos ganó (D-032): el xRV sin contacto, donde cada bola en juego
vale lo que vale un batazo promedio en ese conteo. La parte del contacto casi no se repite de un año a
otro; la parte sin contacto sí.

- sin_contacto: persistencia del xRV sin contacto;
- sin_contacto_y_valores: xRV sin contacto, tasas, Stuff+ y Location+.

Confirmación con más datos (D-032): dentro de cada temporada de 2024 y 2025, la primera mitad de los
pitches de cada pitcher para predecir el xRV total de la segunda mitad.

Prueba con los pares 2024 → 2025: validación cruzada de 10 pliegues por pitcher, repetida 20 veces.
Gana el de menor error, y se adopta solo si le gana a la persistencia con intervalo fuera de cero. El
ganador se mira una vez en 2026 como segunda mirada, junto al resultado de D-030.

Escribe reportes/etapa_04_proyeccion.json.

Uso:
    python src/proyeccion.py   # requiere haber corrido src/modelo.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.model_selection import GroupKFold, RepeatedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR
from exploracion_etapa_04 import compare_pitchers
from modelo import PREDICTIONS_CACHE, add_values, load
from modelos_base import MIN_PITCHES_PER_PERIOD, RANDOM_SEED, TARGET
from stuff_componentes import COMPONENTS, SWINGS

SUMMARY_JSON = REPORTS_DIR / "etapa_04_proyeccion.json"
FOLDS, REPEATS = 10, 20
FIRST, SECOND = HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1

# Cada tasa: sobre qué pitches se mide y qué cuenta.
RATES = {
    "swing": (lambda f: np.full(len(f), True), lambda f: f.outcome.isin(SWINGS)),
    "whiff": (lambda f: f.outcome.isin(SWINGS), lambda f: f.outcome == "whiff"),
    "persecucion": (lambda f: f.in_strike_zone == 0, lambda f: f.outcome.isin(SWINGS)),
    "zona": (lambda f: np.full(len(f), True), lambda f: f.in_strike_zone == 1),
    "strike_cantado": (lambda f: ~f.outcome.isin(SWINGS), lambda f: f.outcome == "strike"),
    "foul": (lambda f: f.outcome.isin({"foul", "batazo"}), lambda f: f.outcome == "foul"),
    "contacto": (lambda f: f.outcome == "batazo", lambda f: f.contact_value),
}
MODEL_VALUES = ["stuff", "location", *COMPONENTS]
NO_CONTACT = "xrv_sin_contacto"
CANDIDATES = {
    "valores": [TARGET, "stuff", "location"],
    "tasas": [TARGET, *RATES],
    "todo": [TARGET, *RATES, *MODEL_VALUES],
    "sin_contacto": [NO_CONTACT],
    "sin_contacto_y_valores": [NO_CONTACT, *RATES, "stuff", "location"],
}


def load_pitches() -> pd.DataFrame:
    pitches, _ = add_values(load(), pd.read_parquet(PREDICTIONS_CACHE))
    zone = duckdb.sql(f"select pitch_seq, in_strike_zone from '{MODEL_PARQUET}'").df()
    pitches = pitches.merge(zone, on="pitch_seq", how="left", validate="one_to_one")
    balls_in_play = pitches.outcome == "batazo"
    average_contact = pitches[balls_in_play].groupby(["year", "Balls", "Strikes"])[TARGET].transform("mean")
    pitches[NO_CONTACT] = pitches[TARGET].mask(balls_in_play, average_contact)
    return pitches[pitches.pitcher_anon_id != "sin_id"].reset_index(drop=True)


def centered_columns(pitches: pd.DataFrame) -> pd.DataFrame:
    """Cada valor por pitch menos el promedio de su temporada, dentro de los pitches donde se mide.

    Así el promedio de un pitcher es su diferencia contra la liga, y se puede juntar 2024 con 2025.
    """
    frame = pitches[["pitcher_anon_id", "year"]].copy()
    for name, (rows, value) in RATES.items():
        mask = np.asarray(rows(pitches), dtype=bool)
        series = pd.Series(np.where(mask, value(pitches).astype(float), np.nan), index=pitches.index)
        frame[name] = series - series.groupby(pitches.year).transform("mean")
    for name in [TARGET, NO_CONTACT, *MODEL_VALUES]:
        frame[name] = pitches[name] - pitches.groupby("year")[name].transform("mean")
    return frame


def pitcher_values(frame: pd.DataFrame) -> pd.DataFrame:
    """Promedio de cada pitcher, por 100 pitches o en puntos porcentuales."""
    columns = [TARGET, NO_CONTACT, *RATES, *MODEL_VALUES]
    table = frame.groupby("pitcher_anon_id").agg(pitches=(TARGET, "size"), **{c: (c, "mean") for c in columns})
    table[columns] *= 100
    return table[table.pitches >= MIN_PITCHES_PER_PERIOD].dropna()


def new_model(features: list[str]):
    if len(features) == 1:
        return LinearRegression()
    return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20)))


def cross_validated(pairs: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Predicción fuera de pliegue de cada pitcher, promediada sobre las repeticiones."""
    x, y = pairs[[f"{c}_antes" for c in features]].to_numpy(), pairs["real_despues"].to_numpy()
    total, counts = np.zeros(len(pairs)), np.zeros(len(pairs))
    for fit_rows, other_rows in RepeatedKFold(n_splits=FOLDS, n_repeats=REPEATS, random_state=RANDOM_SEED).split(x):
        total[other_rows] += new_model(features).fit(x[fit_rows], y[fit_rows]).predict(x[other_rows])
        counts[other_rows] += 1
    return total / counts


def choose(pairs: pd.DataFrame) -> tuple[dict, str]:
    table = pairs[["real_despues"]].copy()
    table["persistencia"] = cross_validated(pairs, [TARGET])
    for name, features in CANDIDATES.items():
        table[name] = cross_validated(pairs, features)
    results = compare_pitchers(table, "real_despues", ["persistencia", *CANDIDATES], "persistencia")
    best = min(CANDIDATES, key=lambda name: results[name]["ecm_por_100"])
    beats_base = results[best]["ic95_diferencia_ecm_vs_persistencia"][1] < 0
    return results, best if beats_base else "persistencia"


def second_look(frame: pd.DataFrame, pairs: pd.DataFrame, winner: str) -> dict:
    """El ganador, ajustado con los pares 2024 → 2025, aplicado a 2024–2025 para predecir 2026."""
    features = [TARGET] if winner == "persistencia" else CANDIDATES[winner]
    before = pitcher_values(frame[frame.year < HOLDOUT_SEASON])
    after = pitcher_values(frame[frame.year == HOLDOUT_SEASON])[[TARGET]].rename(columns={TARGET: "real_2026"})
    table = before.join(after, how="inner")
    columns = {"persistencia": [TARGET], winner: features}
    for name, used in columns.items():
        model = new_model(used).fit(pairs[[f"{c}_antes" for c in used]], pairs["real_despues"])
        table[name] = model.predict(table[used].set_axis([f"{c}_antes" for c in used], axis=1))
    return {"pitchers": len(table), **compare_pitchers(table, "real_2026", list(columns), "persistencia")}


def halves(frame: pd.DataFrame) -> dict:
    """Primera mitad de cada temporada de un pitcher contra el xRV total de su segunda mitad (2024 y 2025)."""
    # Las filas vienen en orden cronológico (D-015): la primera mitad son los primeros pitches.
    history = frame[frame.year < HOLDOUT_SEASON]
    size = history.groupby(["pitcher_anon_id", "year"])[TARGET].transform("size")
    history = history[size >= MIN_PITCHES_PER_PERIOD]
    order = history.groupby(["pitcher_anon_id", "year"]).cumcount()
    size = size[history.index]
    history = history.assign(mitad=np.where(order < size / 2, "antes", "despues"))
    means = history.groupby(["pitcher_anon_id", "year", "mitad"])[[TARGET, NO_CONTACT]].mean().unstack("mitad") * 100
    table = pd.DataFrame({f"{TARGET}_antes": means[(TARGET, "antes")], f"{NO_CONTACT}_antes": means[(NO_CONTACT, "antes")],
                          "real_despues": means[(TARGET, "despues")]}).dropna()
    groups = table.index.get_level_values("pitcher_anon_id")
    predictions = {}
    for name, features in {"persistencia": [TARGET], "sin_contacto": [NO_CONTACT]}.items():
        x, y = table[[f"{c}_antes" for c in features]].to_numpy(), table["real_despues"].to_numpy()
        predicted = np.empty(len(table))
        for fit_rows, other_rows in GroupKFold(FOLDS).split(x, groups=groups):
            predicted[other_rows] = new_model(features).fit(x[fit_rows], y[fit_rows]).predict(x[other_rows])
        predictions[name] = predicted
    result = pd.DataFrame({"real_despues": table.real_despues.to_numpy(), **predictions,
                           "pitcher_anon_id": groups})
    return {"temporadas_de_pitcher": len(result), "pitchers": int(result.pitcher_anon_id.nunique()),
            **clustered_comparison(result, ["persistencia", "sin_contacto"], "persistencia")}


def clustered_comparison(table: pd.DataFrame, columns: list[str], reference: str) -> dict:
    """r y error contra `real_despues`, con IC remuestreando pitchers completos (un pitcher aparece dos años)."""
    y = table.real_despues.to_numpy()
    rows = table.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(rows))
    rng = np.random.default_rng(RANDOM_SEED)
    samples = [np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))]) for _ in range(1000)]

    def r(p, idx):
        return np.corrcoef(p[idx], y[idx])[0, 1]

    def mse(p, idx):
        return np.mean((y[idx] - p[idx]) ** 2)

    def interval(draws):
        return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]

    everyone, base = np.arange(len(table)), table[reference].to_numpy()
    results = {}
    for name in columns:
        p = table[name].to_numpy()
        results[name] = {"r": round(float(r(p, everyone)), 4), "ic95_r": interval([r(p, i) for i in samples]),
                         "ecm_por_100": round(float(mse(p, everyone)), 4)}
        if name != reference:
            results[name][f"ic95_diferencia_r_vs_{reference}"] = interval([r(p, i) - r(base, i) for i in samples])
            results[name][f"ic95_diferencia_ecm_vs_{reference}"] = interval([mse(p, i) - mse(base, i) for i in samples])
    return results


def stability(pairs: pd.DataFrame) -> dict:
    """Cuánto se repite cada tasa y cada valor del mismo pitcher de 2024 a 2025."""
    columns = [TARGET, NO_CONTACT, *RATES, *MODEL_VALUES]
    return {c: round(float(pairs[f"{c}_antes"].corr(pairs[f"{c}_despues"])), 4) for c in columns}


def main():
    pitches = load_pitches()
    frame = centered_columns(pitches)
    first, second = pitcher_values(frame[frame.year == FIRST]), pitcher_values(frame[frame.year == SECOND])
    pairs = first.add_suffix("_antes").join(second.add_suffix("_despues"), how="inner")
    pairs["real_despues"] = pairs[f"{TARGET}_despues"]
    results, winner = choose(pairs)
    confirmation = halves(frame)
    if winner == "persistencia" and confirmation["sin_contacto"]["ic95_diferencia_ecm_vs_persistencia"][1] < 0:
        winner = "sin_contacto"
    summary = {
        "nota": "Elección con pares 2024 → 2025 (D-031) y mitades de 2024–2025 (D-032). "
                "La mirada a 2026 es la segunda, después de D-030.",
        "pares": len(pairs),
        "repeticion_2024_a_2025": stability(pairs),
        "validacion_cruzada_2024_a_2025": results,
        "confirmacion_mitades_2024_2025": confirmation,
        "ganador": winner,
        "segunda_mirada_2026": None if winner == "persistencia" else second_look(frame, pairs, winner),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
