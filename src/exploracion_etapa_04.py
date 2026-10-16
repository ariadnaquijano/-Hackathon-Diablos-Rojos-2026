"""Etapa 4, exploración: primera versión de Stuff+, Location+ y Pitching+ contra los modelos base.

Responde, con 2026 como prueba, tres preguntas antes de escribir el plan de la etapa 4:

1. ¿Un modelo de gradient boosting predice el xRV neutral mejor que la escalera de modelos base
   (D-020), con intervalo que no toque cero?
2. ¿El Stuff+ de 2024–2025 de un pitcher predice su xRV real de 2026 mejor que su propia historia?
   Para eso cada pitch de 2024–2025 recibe la predicción de un modelo que no vio a ese pitcher.
3. ¿La forma a nivel del mar (D-001) hace que un pitcher valga lo mismo en altura y a nivel del mar,
   mejor que el movimiento observado o que meter `altitude_category` como variable?

Escribe reportes/etapa_04_exploracion.json.

Uso:
    python src/exploracion_etapa_04.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR, ROOT
from modelos_base import (BASELINES, MIN_PITCHES_PER_PERIOD, PREDICTIONS_PARQUET, RANDOM_SEED, TARGET,
                          center_by_season, pitcher_bootstrap, pitcher_table, shrunk_persistence)

SUMMARY_JSON = REPORTS_DIR / "etapa_04_exploracion.json"
PREDICTIONS_CACHE = ROOT / "data" / "processed" / "predicciones_etapa_04_exploracion.parquet"
BOOTSTRAP_SAMPLES = 1000
CROSS_FIT_FOLDS = 5
MAX_ITERATIONS = 800
# Pitches mínimos de un pitcher con el mismo tipo de pitch en cada altitud para la prueba de altitud.
MIN_PITCHES_PER_ALTITUDE = 50
EXTREME, SEA_LEVEL = "Extreme Altitude", "No Altitude"

ARSENAL = ["velo_diff_vs_fb", "ivb_diff_vs_fb", "hb_diff_vs_fb", "axis_diff_vs_fb",
           "release_dist_vs_fb", "extension_diff_vs_fb"]
RELEASE = ["RelSpeed", "SpinRate", "spin_axis_arm", "RelHeight", "rel_side_arm", "Extension", "vaa_rel"]
HANDS = ["pitch_class", "pitcher_hand", "platoon_same_side"]
LOCATION = ["PlateLocHeight", "PlateLocSide", "batter_side", "Balls", "Strikes"]
SEQUENCE = ["tunnel_dist_vs_prev", "velo_diff_vs_prev", "times_through_order"]

# Cada modelo: variables y qué representa. Los tres primeros son variantes de Stuff+.
MODELS = {
    "stuff_nivel_mar": (["ivb_sea_level", "hb_sea_level", *RELEASE, *ARSENAL, *HANDS],
                        "Stuff+: forma a nivel del mar (D-001)"),
    "stuff_observado": (["InducedVertBreak", "hb_arm_side", *RELEASE, *ARSENAL, *HANDS],
                        "Stuff+ con el movimiento observado, sin ajuste de altitud"),
    "stuff_con_altitud": (["InducedVertBreak", "hb_arm_side", "altitude_category", *RELEASE, *ARSENAL, *HANDS],
                          "Stuff+ con altitude_category como variable (alternativa de D-001)"),
    "location": (["pitch_class", "pitcher_hand", *LOCATION], "Location+: solo dónde y en qué conteo"),
    "pitching": (["ivb_sea_level", "hb_sea_level", *RELEASE, *ARSENAL, *HANDS, *LOCATION, *SEQUENCE],
                 "Pitching+: forma, ubicación, conteo y secuencia"),
}
CATEGORICAL = {"pitch_class", "pitcher_hand", "platoon_same_side", "batter_side", "altitude_category"}
FORWARD_MODELS = ["stuff_nivel_mar", "pitching"]
ALTITUDE_MODELS = ["stuff_nivel_mar", "stuff_observado", "stuff_con_altitud"]


def load_pitches() -> pd.DataFrame:
    columns = sorted({c for features, _ in MODELS.values() for c in features})
    pitches = duckdb.sql(f"""
        select pitch_seq, year, pitcher_anon_id, {", ".join(columns)}, {TARGET}
        from '{MODEL_PARQUET}'
        where {TARGET} is not null
        order by pitch_seq""").df()
    # 3,093 pitches sin pitcher identificado forman un solo grupo, para no repartirlos entre pliegues.
    pitches["pitcher_anon_id"] = pitches.pitcher_anon_id.fillna("sin_id")
    for column in CATEGORICAL:
        pitches[column] = pitches[column].astype("string").fillna("desconocido").astype("category")
    return pitches


def new_model(iterations: int = MAX_ITERATIONS) -> HistGradientBoostingRegressor:
    # Hojas grandes y aprendizaje lento: el xRV de un pitch es casi todo ruido.
    return HistGradientBoostingRegressor(max_iter=iterations, learning_rate=0.05, max_leaf_nodes=15,
                                         min_samples_leaf=1000, l2_regularization=1.0,
                                         categorical_features="from_dtype", random_state=RANDOM_SEED)


def choose_iterations(train: pd.DataFrame, features: list[str]) -> int:
    """Número de árboles con menor error en un 20 % de pitchers que el modelo no vio."""
    split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=RANDOM_SEED)
    fit_rows, check_rows = next(split.split(train, groups=train.pitcher_anon_id))
    model = new_model().fit(train.iloc[fit_rows][features], train.iloc[fit_rows][TARGET])
    y = train.iloc[check_rows][TARGET].to_numpy()
    errors = [np.mean((y - p) ** 2) for p in model.staged_predict(train.iloc[check_rows][features])]
    return int(np.argmin(errors)) + 1


def fit_and_predict(pitches: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, int]:
    """Predicción de 2026 con un modelo de 2024–2025, y de 2024–2025 con modelos que no vieron al pitcher."""
    history = (pitches.year < HOLDOUT_SEASON).to_numpy()
    train = pitches[history]
    iterations = choose_iterations(train, features)
    holdout_prediction = new_model(iterations).fit(train[features], train[TARGET]).predict(pitches[~history][features])
    out_of_fold = np.full(len(train), np.nan)
    for fit_rows, other_rows in GroupKFold(CROSS_FIT_FOLDS).split(train, groups=train.pitcher_anon_id):
        model = new_model(iterations).fit(train.iloc[fit_rows][features], train.iloc[fit_rows][TARGET])
        out_of_fold[other_rows] = model.predict(train.iloc[other_rows][features])
    prediction = np.empty(len(pitches))
    prediction[history], prediction[~history] = out_of_fold, holdout_prediction
    return prediction, iterations


def pitch_level(test: pd.DataFrame, columns: list[str]) -> dict:
    """Mejora del error cuadrático contra la media de la liga en 2026, en %, con IC por pitchers."""
    y = test[TARGET].to_numpy()
    reference = test.media_liga.to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / np.mean((y[idx] - reference[idx]) ** 2)
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / np.mean((y[idx] - reference[idx]) ** 2)
            return 100 * gain
        return statistic

    best_base = test.lineal_por_tipo.to_numpy()
    results = {}
    for name in columns:
        p = test[name].to_numpy()
        results[name] = {"mejora_vs_media_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                         "ic95_mejora_pct": pitcher_bootstrap(test, improvement(p)),
                         "ic95_diferencia_vs_lineal_pct": pitcher_bootstrap(test, improvement(p, best_base))}
    return results


def compare_pitchers(table: pd.DataFrame, actual: str, columns: list[str], reference: str) -> dict:
    """r y error por 100 pitches de cada columna contra `actual`, y diferencia pareada contra `reference`."""
    y = table[actual].to_numpy()
    rng = np.random.default_rng(RANDOM_SEED)
    samples = [rng.integers(0, len(table), len(table)) for _ in range(BOOTSTRAP_SAMPLES)]

    def r(p, idx):
        return np.corrcoef(p[idx], y[idx])[0, 1]

    def mse(p, idx):
        return np.mean((y[idx] - p[idx]) ** 2)

    def interval(draws):
        return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]

    base = table[reference].to_numpy()
    results = {}
    for name in columns:
        p = table[name].to_numpy()
        if p.std() < 1e-9:
            results[name] = {"r": None, "ecm_por_100": round(float(mse(p, np.arange(len(table)))), 4)}
            continue
        everyone = np.arange(len(table))
        results[name] = {
            "r": round(float(r(p, everyone)), 4),
            "ic95_r": interval([r(p, idx) for idx in samples]),
            "ecm_por_100": round(float(mse(p, everyone)), 4),
            f"ic95_diferencia_r_vs_{reference}": interval([r(p, idx) - r(base, idx) for idx in samples]),
            f"ic95_diferencia_ecm_vs_{reference}": interval([mse(p, idx) - mse(base, idx) for idx in samples]),
        }
    return results


def same_season(pitches: pd.DataFrame, columns: list[str]) -> dict:
    """Por pitcher en 2026: lo predicho para sus pitches de 2026 contra su xRV real de 2026."""
    centered = center_by_season(pitches[["pitcher_anon_id", "year", TARGET, *columns]], [TARGET, *columns])
    table = pitcher_table(centered[centered.year == HOLDOUT_SEASON], [TARGET, *columns])
    table = table.query("pitches >= @MIN_PITCHES_PER_PERIOD")
    history = pitcher_table(centered[centered.year < HOLDOUT_SEASON], [TARGET]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    table = table[table.index.isin(history.index)]
    return {"pitchers": len(table), **compare_pitchers(table, TARGET, columns, "lineal_por_tipo")}


def forward(pitches: pd.DataFrame, columns: list[str]) -> dict:
    """Lo que el club usaría en noviembre: el valor de 2024–2025 de un pitcher para predecir su 2026.

    Las predicciones de 2024–2025 vienen de modelos que no vieron a ese pitcher, así que el modelo no
    puede haber memorizado sus resultados. Se compara contra la persistencia encogida (su xRV de
    2024–2025 llevado hacia la media con la pendiente de 2024 → 2025).
    """
    centered = center_by_season(pitches[["pitcher_anon_id", "year", TARGET, *columns]], [TARGET, *columns])
    history = centered[centered.year < HOLDOUT_SEASON]
    before = pitcher_table(history, [TARGET, *columns]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    after = pitcher_table(centered[centered.year == HOLDOUT_SEASON], [TARGET]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    shrunk, slope, _ = shrunk_persistence(history, before)
    table = before.drop(columns=TARGET).assign(persistencia_encogida=shrunk, real_2026=after[TARGET]).dropna()
    return {"pitchers": len(table), "pendiente_persistencia": slope,
            **compare_pitchers(table, "real_2026", [*columns, "persistencia_encogida"], "persistencia_encogida")}


def altitude_consistency(pitches: pd.DataFrame, columns: list[str], reference: str) -> dict:
    """El mismo pitcher con el mismo pitch: valor predicho en altitud extrema menos a nivel del mar.

    Si el ajuste funciona, la diferencia debe acercarse a cero y la correlación entre ambas altitudes
    debe ser alta. Los intervalos remuestrean pitchers completos, con todos sus tipos de pitch, y las
    diferencias son pareadas contra `reference`.
    """
    extremes = pitches[pitches.altitude_category.isin([EXTREME, SEA_LEVEL]) & (pitches.pitcher_anon_id != "sin_id")]
    by_group = (extremes.groupby(["pitcher_anon_id", "pitch_class", "altitude_category"], observed=True)
                .agg(pitches=(TARGET, "size"), **{c: (c, "mean") for c in [TARGET, *columns]}).reset_index())
    by_group = by_group[by_group.pitches >= MIN_PITCHES_PER_ALTITUDE]
    wide = by_group.pivot(index=["pitcher_anon_id", "pitch_class"], columns="altitude_category",
                          values=[TARGET, *columns]).dropna()
    rows = pd.Series(np.arange(len(wide))).groupby(wide.index.get_level_values(0).to_numpy()).indices
    pitchers = np.array(list(rows))
    rng = np.random.default_rng(RANDOM_SEED)
    samples = [np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))]) for _ in range(BOOTSTRAP_SAMPLES)]

    def values(name):
        return wide[(name, EXTREME)].to_numpy() * 100, wide[(name, SEA_LEVEL)].to_numpy() * 100

    def gap(name, idx):
        high, low = values(name)
        return np.mean(high[idx] - low[idx])

    def r(name, idx):
        high, low = values(name)
        return np.corrcoef(high[idx], low[idx])[0, 1]

    def interval(draws):
        return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]

    everyone = np.arange(len(wide))
    results = {"pitcher_tipo": len(wide), "pitchers": len(pitchers)}
    for name in [TARGET, *columns]:
        results[name] = {"extrema_menos_mar_por_100": round(float(gap(name, everyone)), 4),
                         "ic95_extrema_menos_mar": interval([gap(name, idx) for idx in samples]),
                         "r_entre_altitudes": round(float(r(name, everyone)), 4),
                         "ic95_r": interval([r(name, idx) for idx in samples])}
        if name in columns and name != reference:
            results[name][f"ic95_diferencia_r_vs_{reference}"] = interval(
                [r(name, idx) - r(reference, idx) for idx in samples])
            results[name][f"ic95_diferencia_brecha_absoluta_vs_{reference}"] = interval(
                [abs(gap(name, idx)) - abs(gap(reference, idx)) for idx in samples])
    return results


def main():
    pitches = load_pitches()
    base = pd.read_parquet(PREDICTIONS_PARQUET)
    pitches = pitches.merge(base, on="pitch_seq", how="left", validate="one_to_one")
    if PREDICTIONS_CACHE.exists():
        cached = pd.read_parquet(PREDICTIONS_CACHE)
        iterations = json.loads(cached.attrs["arboles"])
        pitches = pitches.merge(cached, on="pitch_seq", how="left", validate="one_to_one")
    else:
        iterations = {}
        for name, (features, _) in MODELS.items():
            pitches[name], iterations[name] = fit_and_predict(pitches, features)
            print(f"{name}: {iterations[name]} árboles")
        cached = pitches[["pitch_seq", *MODELS]].copy()
        cached.attrs["arboles"] = json.dumps(iterations)
        cached.to_parquet(PREDICTIONS_CACHE, index=False)
    models = list(MODELS)
    holdout = pitches[pitches.year == HOLDOUT_SEASON].reset_index(drop=True)
    summary = {
        "target": TARGET,
        "descripcion": {name: text for name, (_, text) in MODELS.items()},
        "arboles": iterations,
        "por_pitch_2026": pitch_level(holdout, [*BASELINES, *models]),
        "por_pitcher_misma_temporada": same_season(pitches, [*BASELINES, *models]),
        "por_pitcher_a_futuro": forward(pitches, [*FORWARD_MODELS, "lineal_por_tipo"]),
        "altitud_mismo_pitcher": altitude_consistency(pitches, ALTITUDE_MODELS, "stuff_observado"),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
