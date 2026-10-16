"""Etapa 4: cómo se relacionan Stuff+ y Location+ con Pitching+.

Usa solo 2024 y 2025 (D-025): las predicciones de esos años vienen de modelos que no vieron al
pitcher (5 pliegues por pitcher, `exploracion_etapa_04.py`). 2026 no se toca.

Preguntas, fijadas antes de correr:

1. Estructura: ¿Stuff+ y Location+ son habilidades distintas (correlación entre pitchers)? ¿Cuánto del
   Pitching+ de un pitcher explican juntas y con qué peso cada una? ¿Cuánto sigue cada una al xRV real
   del pitcher en esa misma temporada?
2. Por pitch: ¿Pitching+ predice mejor que sumar Stuff+ y Location+? La suma se ajusta en 2024 y se
   evalúa en 2025. La diferencia mide interacciones forma × ubicación y la secuencia.
3. Estabilidad: ¿cuál se repite más, entre mitades de la misma temporada y de 2024 a 2025?
4. A futuro: ¿el valor de 2024 de cada uno predice el xRV real de 2025 mejor que el xRV de 2024?

Escribe reportes/etapa_04_relacion_componentes.json.

Uso:
    python src/relacion_componentes.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from config import HOLDOUT_SEASON, REPORTS_DIR
from exploracion_etapa_04 import PREDICTIONS_CACHE, load_pitches
from modelos_base import MIN_PITCHES_PER_PERIOD, RANDOM_SEED, TARGET, center_by_season, pitcher_bootstrap

SUMMARY_JSON = REPORTS_DIR / "etapa_04_relacion_componentes.json"
BOOTSTRAP_SAMPLES = 1000
STUFF, LOCATION, PITCHING = "stuff_nivel_mar", "location", "pitching"
COMPONENTS = [STUFF, LOCATION, PITCHING]
FIRST, SECOND = HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1


def load() -> pd.DataFrame:
    pitches = load_pitches()[["pitch_seq", "year", "pitcher_anon_id", TARGET]]
    pitches = pitches[(pitches.year < HOLDOUT_SEASON) & (pitches.pitcher_anon_id != "sin_id")]
    predictions = pd.read_parquet(PREDICTIONS_CACHE, columns=["pitch_seq", *COMPONENTS])
    pitches = pitches.merge(predictions, on="pitch_seq", how="left", validate="one_to_one")
    return center_by_season(pitches, [TARGET, *COMPONENTS]).reset_index(drop=True)


def season_table(pitches: pd.DataFrame, year: int) -> pd.DataFrame:
    """Valor por 100 pitches de cada pitcher con muestra suficiente en esa temporada."""
    season = pitches[pitches.year == year]
    table = season.groupby("pitcher_anon_id").agg(pitches=(TARGET, "size"),
                                                  **{c: (c, "mean") for c in [TARGET, *COMPONENTS]})
    table[[TARGET, *COMPONENTS]] *= 100
    return table[table.pitches >= MIN_PITCHES_PER_PERIOD]


def bootstrap_rows(n: int) -> list[np.ndarray]:
    rng = np.random.default_rng(RANDOM_SEED)
    return [rng.integers(0, n, n) for _ in range(BOOTSTRAP_SAMPLES)]


def interval(draws) -> list[float]:
    return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]


def correlation(a: np.ndarray, b: np.ndarray, samples: list[np.ndarray]) -> dict:
    return {"r": round(float(np.corrcoef(a, b)[0, 1]), 4),
            "ic95": interval([np.corrcoef(a[idx], b[idx])[0, 1] for idx in samples])}


def structure(table: pd.DataFrame) -> dict:
    """Pitching+ de cada pitcher explicado por su Stuff+ y su Location+, en unidades estándar."""
    z = (table[COMPONENTS] - table[COMPONENTS].mean()) / table[COMPONENTS].std()
    samples = bootstrap_rows(len(z))

    def fit(idx):
        model = LinearRegression().fit(z[[STUFF, LOCATION]].iloc[idx], z[PITCHING].iloc[idx])
        return model.coef_, model.score(z[[STUFF, LOCATION]].iloc[idx], z[PITCHING].iloc[idx])

    everyone = np.arange(len(z))
    (beta_stuff, beta_location), r2 = fit(everyone)
    draws = [fit(idx) for idx in samples]
    return {
        "pitchers": len(z),
        "r_stuff_location": correlation(z[STUFF].to_numpy(), z[LOCATION].to_numpy(), samples),
        "r_pitching_stuff": correlation(z[PITCHING].to_numpy(), z[STUFF].to_numpy(), samples),
        "r_pitching_location": correlation(z[PITCHING].to_numpy(), z[LOCATION].to_numpy(), samples),
        "peso_stuff": {"beta": round(float(beta_stuff), 4), "ic95": interval([d[0][0] for d in draws])},
        "peso_location": {"beta": round(float(beta_location), 4), "ic95": interval([d[0][1] for d in draws])},
        "r2_pitching_con_ambos": {"r2": round(float(r2), 4), "ic95": interval([d[1] for d in draws])},
        "r_con_xrv_real": {c: correlation(table[c].to_numpy(), table[TARGET].to_numpy(), samples) for c in COMPONENTS},
        "desviacion_entre_pitchers_por_100": {c: round(float(table[c].std()), 4) for c in [TARGET, *COMPONENTS]},
    }


def pitch_level(pitches: pd.DataFrame) -> dict:
    """Error por pitch en 2025 contra la media: Pitching+ frente a la suma de Stuff+ y Location+ ajustada en 2024."""
    train = pitches[pitches.year == FIRST]
    test = pitches[pitches.year == SECOND].reset_index(drop=True)
    stack = LinearRegression().fit(train[[STUFF, LOCATION]], train[TARGET])
    test = test.assign(suma=stack.predict(test[[STUFF, LOCATION]]))
    y = test[TARGET].to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            base = np.mean(y[idx] ** 2)  # el target está centrado por temporada: la media es cero
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / base
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / base
            return 100 * gain
        return statistic

    suma = test.suma.to_numpy()
    results = {"pesos_suma_2024": {"stuff": round(float(stack.coef_[0]), 4),
                                   "location": round(float(stack.coef_[1]), 4)}}
    for name in [STUFF, LOCATION, "suma", PITCHING]:
        p = test[name].to_numpy()
        results[name] = {"mejora_vs_media_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                         "ic95_mejora_pct": pitcher_bootstrap(test, improvement(p)),
                         "ic95_diferencia_vs_suma_pct": pitcher_bootstrap(test, improvement(p, suma))}
    return results


def split_half(pitches: pd.DataFrame, year: int) -> dict:
    """Pitches pares contra impares del mismo pitcher en la misma temporada, con Spearman-Brown."""
    season = pitches[pitches.year == year].sort_values("pitch_seq")
    season = season.assign(half=season.groupby("pitcher_anon_id").cumcount() % 2)
    halves = season.groupby(["pitcher_anon_id", "half"])[[TARGET, *COMPONENTS]].mean().unstack("half")
    counts = season.groupby("pitcher_anon_id").size()
    halves = halves[counts.reindex(halves.index) >= MIN_PITCHES_PER_PERIOD]
    samples = bootstrap_rows(len(halves))

    def reliability(column, idx):
        r = np.corrcoef(halves[(column, 0)].to_numpy()[idx], halves[(column, 1)].to_numpy()[idx])[0, 1]
        return 2 * r / (1 + r)

    everyone = np.arange(len(halves))
    return {"pitchers": len(halves),
            **{c: {"confiabilidad": round(float(reliability(c, everyone)), 4),
                   "ic95": interval([reliability(c, idx) for idx in samples])} for c in [TARGET, *COMPONENTS]}}


def year_to_year(first: pd.DataFrame, second: pd.DataFrame) -> dict:
    """Mismo pitcher en 2024 y 2025: cuánto se repite cada valor y cuánto predice su xRV real de 2025."""
    pairs = first.join(second, lsuffix="_antes", rsuffix="_despues", how="inner")
    samples = bootstrap_rows(len(pairs))
    actual = pairs[f"{TARGET}_despues"].to_numpy()
    history = pairs[f"{TARGET}_antes"].to_numpy()

    def r(a, idx):
        return np.corrcoef(a[idx], actual[idx])[0, 1]

    repeat = {c: correlation(pairs[f"{c}_antes"].to_numpy(), pairs[f"{c}_despues"].to_numpy(), samples)
              for c in [TARGET, *COMPONENTS]}
    forward = {}
    for c in COMPONENTS:
        before = pairs[f"{c}_antes"].to_numpy()
        forward[c] = {**correlation(before, actual, samples),
                      "ic95_diferencia_vs_xrv_2024": interval([r(before, idx) - r(history, idx) for idx in samples])}
    forward["xrv_real_2024"] = correlation(history, actual, samples)
    return {"pitchers": len(pairs), "repeticion_2024_a_2025": repeat, "predice_xrv_2025": forward}


def main():
    pitches = load()
    first, second = season_table(pitches, FIRST), season_table(pitches, SECOND)
    summary = {
        "nota": "Solo 2024 y 2025 (D-025). Valores por 100 pitches, centrados por temporada.",
        "estructura": {str(FIRST): structure(first), str(SECOND): structure(second)},
        "por_pitch_2025": pitch_level(pitches),
        "confiabilidad_mitades": {str(FIRST): split_half(pitches, FIRST), str(SECOND): split_half(pitches, SECOND)},
        "entre_temporadas": year_to_year(first, second),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
