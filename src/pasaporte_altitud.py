"""Etapa 5: pasaporte de altitud (D-034).

Con los pitches a nivel del mar de un pitcher, predice cómo cambia cada uno en altitud extrema:

1. Forma: movimiento a nivel del mar × aire^k, con la mediana del aire en altitud extrema de esa
   temporada y el k de su tipo de pitch (D-016). Las diferencias contra la recta se traducen igual,
   moviendo también la recta de referencia.
2. Valor: un Stuff+ local, con los componentes de D-027 pero con el movimiento observado, evalúa el
   mismo pitch con el aire del nivel del mar (1.0) y con el de altitud extrema. El costo es la
   diferencia, en carreras por 100 pitches.

Prueba con pitchers que lanzaron el mismo tipo de pitch en altitud extrema y a nivel del mar en
2024–2025 (50+ pitches por lado). Los modelos de valor no vieron al pitcher (5 pliegues por pitcher).
Reglas fijadas antes de correr (D-034):

- Forma: gana si su error contra el movimiento real en altura es menor que suponer que no cambia y que
  aplicar a todos la pérdida promedio de la liga, con intervalo fuera de cero.
- Valor: cuenta si la correlación entre el costo predicho y el cambio real del xRV sin contacto es
  positiva con intervalo fuera de cero, y si su error es menor que dar a todos el costo promedio.

Escribe reportes/etapa_05_pasaporte.json, sin identificadores. El costo por pitcher y tipo de pitch va a
data/processed/pasaporte.parquet, que no se sube al repo.

Uso:
    python src/pasaporte_altitud.py   # requiere haber corrido src/modelo.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR, ROOT
from exploracion_etapa_04 import CROSS_FIT_FOLDS, EXTREME, MIN_PITCHES_PER_ALTITUDE, MODELS, SEA_LEVEL
from modelo import SPECS, load, predict
from modelos_base import RANDOM_SEED, TARGET
from proyeccion import NO_CONTACT
from stuff_componentes import choose_iterations, combine, new_model, outcome_values

SUMMARY_JSON = REPORTS_DIR / "etapa_05_pasaporte.json"
PASSPORT_PARQUET = ROOT / "data" / "processed" / "pasaporte.parquet"
PREDICTIONS_CACHE = ROOT / "data" / "processed" / "predicciones_pasaporte.parquet"
STAGE_02_JSON = REPORTS_DIR / "etapa_02_resumen.json"
LOCAL_FEATURES = MODELS["stuff_observado"][0]
BOOTSTRAP_SAMPLES = 1000
FASTBALL = "Four-Seam"
KEYS = ["pitcher_anon_id", "pitch_class"]


def exponents() -> tuple[dict, dict]:
    """k usado por tipo de pitch para IVB y HB (D-016), y el de la liga para los tipos sin k propio."""
    k = json.loads(STAGE_02_JSON.read_text())["exponente_k"]
    by_type = {t: {c: v[c]["k_usado"] for c in ("ivb", "hb")} for t, v in k["por_tipo"].items()}
    return by_type, {c: k["liga"][c]["k"] for c in ("ivb", "hb")}


def extreme_air() -> dict:
    """Mediana del aire de los juegos en altitud extrema, por temporada."""
    air = json.loads(STAGE_02_JSON.read_text())["aire"]["por_altitud_y_temporada"]
    return {row["year"]: row["p50"] for row in air if row["altitud"] == EXTREME}


def load_pitches() -> pd.DataFrame:
    pitches = load()
    pitches = pitches[pitches.year < HOLDOUT_SEASON]
    extra = duckdb.sql(f"select pitch_seq, pitch_group, air_ratio from '{MODEL_PARQUET}'").df()
    pitches = pitches.merge(extra, on="pitch_seq", how="left", validate="one_to_one")
    balls_in_play = pitches.outcome == "batazo"
    average_contact = pitches[balls_in_play].groupby(["year", "Balls", "Strikes"])[TARGET].transform("mean")
    pitches[NO_CONTACT] = pitches[TARGET].mask(balls_in_play, average_contact)
    for column in [TARGET, NO_CONTACT]:
        pitches[column] -= pitches.groupby("year")[column].transform("mean")
    by_type, league = exponents()
    for component in ("ivb", "hb"):
        pitches[f"k_{component}"] = pitches.pitch_group.map({t: v[component] for t, v in by_type.items()}).fillna(league[component])
        pitches[f"k_{component}_recta"] = by_type[FASTBALL][component]
    return pitches.reset_index(drop=True)


def translated(frame: pd.DataFrame, air: pd.Series) -> pd.DataFrame:
    """El mismo pitch con otro aire: movimiento y diferencias contra la recta, con k por tipo."""
    moved = frame.copy()
    game_air = frame.air_ratio.fillna(1.0)
    for component, observed, diff in (("ivb", "InducedVertBreak", "ivb_diff_vs_fb"), ("hb", "hb_arm_side", "hb_diff_vs_fb")):
        sea = frame[f"{component}_sea_level"]
        reference_sea = (frame[observed] - frame[diff]) / game_air ** frame[f"k_{component}_recta"]
        moved[observed] = sea * air ** frame[f"k_{component}"]
        moved[diff] = moved[observed] - reference_sea * air ** frame[f"k_{component}_recta"]
    return moved


def local_values(pitches: pd.DataFrame) -> pd.DataFrame:
    """Stuff local de cada pitch a nivel del mar, con aire 1.0 y con el de altitud extrema.

    Cada pitch se evalúa con modelos que no vieron a su pitcher.
    """
    sea = pitches.altitude_category == SEA_LEVEL
    extreme = pitches.year.map(extreme_air())
    at_sea = translated(pitches[sea], pd.Series(1.0, index=pitches.index)[sea])
    at_altitude = translated(pitches[sea], extreme[sea])
    predicted = {"sea": pd.DataFrame(index=at_sea.index), "alt": pd.DataFrame(index=at_sea.index)}
    folds = GroupKFold(CROSS_FIT_FOLDS).split(pitches, groups=pitches.pitcher_anon_id)
    splits = list(folds)
    for name, (kind, rows, label, _) in SPECS.items():
        if name == "location":
            continue
        subset = pitches[rows(pitches)]
        iterations = choose_iterations(kind, subset, label(subset), LOCAL_FEATURES)
        print(f"{name}: {iterations} árboles")
        for frame in predicted.values():
            frame[name] = np.nan
        for fit_rows, other_rows in splits:
            train = pitches.iloc[fit_rows]
            train = train[rows(train)]
            model = new_model(kind, iterations).fit(train[LOCAL_FEATURES], label(train))
            held_out = at_sea.index.intersection(pitches.index[other_rows])
            predicted["sea"].loc[held_out, name] = predict(model, kind, at_sea.loc[held_out], LOCAL_FEATURES)
            predicted["alt"].loc[held_out, name] = predict(model, kind, at_altitude.loc[held_out], LOCAL_FEATURES)
    values = outcome_values(pitches)
    result = pitches.loc[sea, ["pitch_seq"]].copy()
    result["stuff_local_mar"] = combine(predicted["sea"], values)
    result["stuff_local_extrema"] = combine(predicted["alt"], values)
    result["ivb_extrema_predicho"] = at_altitude.InducedVertBreak
    result["hb_extrema_predicho"] = at_altitude.hb_arm_side
    return result


def pairs_table(pitches: pd.DataFrame) -> pd.DataFrame:
    """Pitcher y tipo de pitch con muestra en las dos altitudes: lo predicho con su lado del mar y lo real en altura."""
    sea = pitches[pitches.altitude_category == SEA_LEVEL]
    high = pitches[pitches.altitude_category == EXTREME]
    sea_side = sea.groupby(KEYS, observed=True).agg(
        n_mar=(TARGET, "size"), ivb_mar=("InducedVertBreak", "mean"), hb_mar=("hb_arm_side", "mean"),
        ivb_predicho=("ivb_extrema_predicho", "mean"), hb_predicho=("hb_extrema_predicho", "mean"),
        costo=("costo", "mean"), xrv_mar=(NO_CONTACT, "mean"), total_mar=(TARGET, "mean"))
    high_side = high.groupby(KEYS, observed=True).agg(
        n_extrema=(TARGET, "size"), ivb_real=("InducedVertBreak", "mean"), hb_real=("hb_arm_side", "mean"),
        xrv_extrema=(NO_CONTACT, "mean"), total_extrema=(TARGET, "mean"))
    table = sea_side.join(high_side, how="inner")
    table = table[(table.n_mar >= MIN_PITCHES_PER_ALTITUDE) & (table.n_extrema >= MIN_PITCHES_PER_ALTITUDE)].dropna()
    table["cambio_real"] = 100 * (table.xrv_extrema - table.xrv_mar)
    table["cambio_real_total"] = 100 * (table.total_extrema - table.total_mar)
    return table.reset_index()


def bootstrap(table: pd.DataFrame):
    rows = table.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(rows))
    rng = np.random.default_rng(RANDOM_SEED)
    return [np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))]) for _ in range(BOOTSTRAP_SAMPLES)]


def interval(draws) -> list[float]:
    return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]


def shape_test(table: pd.DataFrame, samples) -> dict:
    """Error del movimiento predicho en altura contra el real, frente a dos bases."""
    results = {}
    for component in ("ivb", "hb"):
        real = table[f"{component}_real"].to_numpy()
        sea = table[f"{component}_mar"].to_numpy()
        # Base (b): la pérdida promedio de la liga en ese tipo de pitch, como proporción.
        ratio = table.groupby("pitch_class", observed=True)[[f"{component}_real", f"{component}_mar"]].transform("sum")
        league = sea * (ratio[f"{component}_real"] / ratio[f"{component}_mar"]).to_numpy()
        candidates = {"pasaporte": table[f"{component}_predicho"].to_numpy(), "sin_cambio": sea, "perdida_promedio": league}

        def mse(p, idx):
            return np.mean((real[idx] - p[idx]) ** 2)

        everyone = np.arange(len(table))
        passport = candidates["pasaporte"]
        results[component] = {
            name: {"ecm_pulgadas2": round(float(mse(p, everyone)), 4),
                   **({} if name == "pasaporte" else
                      {"ic95_diferencia_pasaporte_menos_base": interval([mse(passport, i) - mse(p, i) for i in samples])})}
            for name, p in candidates.items()}
        results[component]["cambio_real_promedio_pulgadas"] = round(float(np.mean(real - sea)), 3)
    return results


def value_test(table: pd.DataFrame, samples, actual: str) -> dict:
    """Costo predicho contra el cambio real del xRV, frente a dar a todos el costo promedio.

    El costo se calibra a la escala real con una recta ajustada en otros pitchers (10 pliegues por
    pitcher), y la base es el cambio promedio de esos mismos pitchers de entrenamiento.
    """
    y, cost = table[actual].to_numpy(), table.costo.to_numpy() * 100
    calibrated, constant = np.empty(len(y)), np.empty(len(y))
    for fit_rows, other_rows in GroupKFold(10).split(table, groups=table.pitcher_anon_id):
        slope, intercept = np.polyfit(cost[fit_rows], y[fit_rows], 1)
        calibrated[other_rows] = intercept + slope * cost[other_rows]
        constant[other_rows] = y[fit_rows].mean()

    def r(idx):
        return np.corrcoef(cost[idx], y[idx])[0, 1]

    def mse_difference(idx):
        return np.mean((y[idx] - calibrated[idx]) ** 2) - np.mean((y[idx] - constant[idx]) ** 2)

    everyone = np.arange(len(y))
    return {"r": round(float(r(everyone)), 4), "ic95_r": interval([r(i) for i in samples]),
            "costo_predicho_promedio_por_100": round(float(cost.mean()), 4),
            "cambio_real_promedio_por_100": round(float(y.mean()), 4),
            "ecm_calibrado": round(float(np.mean((y - calibrated) ** 2)), 4),
            "ecm_costo_constante": round(float(np.mean((y - constant) ** 2)), 4),
            "ic95_diferencia_ecm_vs_costo_constante": interval([mse_difference(i) for i in samples])}


def by_type(table: pd.DataFrame) -> dict:
    """Chequeo descriptivo, agregado después de la prueba: costo predicho y cambio real promedio por tipo."""
    rng = np.random.default_rng(RANDOM_SEED)
    result = {}
    for pitch_type, group in table.groupby("pitch_class", observed=True):
        if len(group) < 30:
            continue
        rows = group.groupby("pitcher_anon_id").indices
        pitchers = np.array(list(rows))
        real = group.cambio_real.to_numpy()
        draws = [real[np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))])].mean()
                 for _ in range(BOOTSTRAP_SAMPLES)]
        result[str(pitch_type)] = {"pares": len(group), "costo_predicho_por_100": round(float(100 * group.costo.mean()), 3),
                                   "cambio_real_sin_contacto_por_100": round(float(real.mean()), 3),
                                   "ic95_cambio_real": interval(draws)}
    return result


def main():
    pitches = load_pitches()
    if PREDICTIONS_CACHE.exists():
        local = pd.read_parquet(PREDICTIONS_CACHE)
    else:
        local = local_values(pitches)
        local.to_parquet(PREDICTIONS_CACHE, index=False)
    pitches = pitches.merge(local, on="pitch_seq", how="left", validate="one_to_one")
    pitches["costo"] = pitches.stuff_local_extrema - pitches.stuff_local_mar
    table = pairs_table(pitches)
    samples = bootstrap(table)
    passport = (pitches[pitches.altitude_category == SEA_LEVEL].groupby(KEYS, observed=True)
                .agg(pitches=(TARGET, "size"), costo_por_100=("costo", "mean")).reset_index())
    passport["costo_por_100"] *= 100
    passport.to_parquet(PASSPORT_PARQUET, index=False)
    summary = {
        "nota": "Solo 2024–2025 (D-034). Pares con 50+ pitches por lado; modelos de valor sin ver al pitcher.",
        "aire_extremo_mediana": extreme_air(),
        "pares_pitcher_tipo": len(table), "pitchers": int(table.pitcher_anon_id.nunique()),
        "forma": shape_test(table, samples),
        "valor_sin_contacto": value_test(table, samples, "cambio_real"),
        "valor_total_referencia": value_test(table, samples, "cambio_real_total"),
        "chequeo_por_tipo": by_type(table),
        "costo_por_tipo_por_100": (passport[passport.pitches >= 100].groupby("pitch_class", observed=True)
                                   .costo_por_100.describe()[["count", "mean", "25%", "75%"]].round(3)
                                   .to_dict(orient="index")),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
