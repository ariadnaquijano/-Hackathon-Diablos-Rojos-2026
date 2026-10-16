"""Etapa 4: ¿cuánto del Location+ es ubicación y cuánto es el conteo?

El Location+ de la exploración usa la ubicación y el conteo (bolas y strikes). Si el conteo le diera
crédito a un pitcher por estar en conteos buenos, Location+ mezclaría ubicación con manejo del conteo.
Se compara contra una versión sin conteo, entrenada igual: mismos hiperparámetros, árboles elegidos con
un 20 % de pitchers no vistos y predicciones de modelos que no vieron al pitcher (5 pliegues).

Solo 2024 y 2025 (D-025). Preguntas, fijadas antes de correr:

1. ¿Cuánto varía entre pitchers el valor que da solo el conteo (modelo base `media_conteo`)?
2. Por pitch en 2025: ¿cuánto pierde Location+ al quitarle el conteo?
3. Por pitcher: ¿las dos versiones ordenan igual a los pitchers? ¿Cuál sigue mejor al xRV real, cuál se
   repite más y cuál predice mejor el año siguiente?
4. ¿Pitching+ se sigue explicando con Stuff+ y la versión sin conteo?

Escribe reportes/etapa_04_location_sin_conteo.json.

Uso:
    python src/location_sin_conteo.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import (CROSS_FIT_FOLDS, PREDICTIONS_CACHE, choose_iterations, load_pitches,
                                  new_model)
from modelos_base import (MIN_PITCHES_PER_PERIOD, PREDICTIONS_PARQUET, RANDOM_SEED, TARGET,
                          center_by_season, pitcher_bootstrap)

SUMMARY_JSON = REPORTS_DIR / "etapa_04_location_sin_conteo.json"
OWN_CACHE = ROOT / "data" / "processed" / "predicciones_location_sin_conteo.parquet"
FEATURES = ["pitch_class", "pitcher_hand", "PlateLocHeight", "PlateLocSide", "batter_side"]
BOOTSTRAP_SAMPLES = 1000
WITH_COUNT, WITHOUT_COUNT, COUNT_ONLY = "location", "location_sin_conteo", "media_conteo"
STUFF, PITCHING = "stuff_nivel_mar", "pitching"
VALUES = [TARGET, WITH_COUNT, WITHOUT_COUNT, COUNT_ONLY, STUFF, PITCHING]
FIRST, SECOND = HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1


def out_of_fold(history: pd.DataFrame) -> tuple[np.ndarray, int]:
    """Predicción de cada pitch de 2024–2025 con un modelo que no vio a ese pitcher."""
    iterations = choose_iterations(history, FEATURES)
    prediction = np.full(len(history), np.nan)
    for fit_rows, other_rows in GroupKFold(CROSS_FIT_FOLDS).split(history, groups=history.pitcher_anon_id):
        model = new_model(iterations).fit(history.iloc[fit_rows][FEATURES], history.iloc[fit_rows][TARGET])
        prediction[other_rows] = model.predict(history.iloc[other_rows][FEATURES])
    return prediction, iterations


def load() -> tuple[pd.DataFrame, int]:
    history = load_pitches()
    history = history[history.year < HOLDOUT_SEASON].reset_index(drop=True)
    if OWN_CACHE.exists():
        own = pd.read_parquet(OWN_CACHE)
        iterations = int(own.attrs["arboles"])
    else:
        prediction, iterations = out_of_fold(history)
        own = pd.DataFrame({"pitch_seq": history.pitch_seq, WITHOUT_COUNT: prediction})
        own.attrs["arboles"] = str(iterations)
        own.to_parquet(OWN_CACHE, index=False)
    pitches = (history[["pitch_seq", "year", "pitcher_anon_id", TARGET]]
               .merge(own, on="pitch_seq", validate="one_to_one")
               .merge(pd.read_parquet(PREDICTIONS_CACHE, columns=["pitch_seq", WITH_COUNT, STUFF, PITCHING]),
                      on="pitch_seq", validate="one_to_one")
               .merge(pd.read_parquet(PREDICTIONS_PARQUET, columns=["pitch_seq", COUNT_ONLY]),
                      on="pitch_seq", validate="one_to_one"))
    pitches = pitches[pitches.pitcher_anon_id != "sin_id"]
    return center_by_season(pitches, VALUES).reset_index(drop=True), iterations


def interval(draws) -> list[float]:
    return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]


def bootstrap_rows(n: int) -> list[np.ndarray]:
    rng = np.random.default_rng(RANDOM_SEED)
    return [rng.integers(0, n, n) for _ in range(BOOTSTRAP_SAMPLES)]


def r(a: np.ndarray, b: np.ndarray, idx: np.ndarray) -> float:
    return np.corrcoef(a[idx], b[idx])[0, 1]


def paired(table: pd.DataFrame, pairs: dict[str, tuple[str, str]], reference: str) -> dict:
    """r de cada par (valor, objetivo), con IC y diferencia pareada contra el par `reference`."""
    samples = bootstrap_rows(len(table))
    everyone = np.arange(len(table))
    columns = {name: (table[a].to_numpy(), table[b].to_numpy()) for name, (a, b) in pairs.items()}
    base = columns[reference]
    results = {}
    for name, (a, b) in columns.items():
        results[name] = {"r": round(float(r(a, b, everyone)), 4), "ic95": interval([r(a, b, idx) for idx in samples])}
        if name != reference:
            results[name][f"ic95_diferencia_vs_{reference}"] = interval(
                [r(a, b, idx) - r(*base, idx) for idx in samples])
    return results


def season_table(pitches: pd.DataFrame, year: int) -> pd.DataFrame:
    season = pitches[pitches.year == year]
    table = season.groupby("pitcher_anon_id").agg(pitches=(TARGET, "size"), **{c: (c, "mean") for c in VALUES})
    table[VALUES] *= 100
    return table[table.pitches >= MIN_PITCHES_PER_PERIOD]


def pitch_level(pitches: pd.DataFrame) -> dict:
    """Mejora del error por pitch en 2025 contra la media, y diferencia contra Location+ con conteo."""
    test = pitches[pitches.year == SECOND].reset_index(drop=True)
    y = test[TARGET].to_numpy()
    with_count = test[WITH_COUNT].to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            base = np.mean(y[idx] ** 2)  # el target está centrado por temporada: la media es cero
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / base
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / base
            return 100 * gain
        return statistic

    results = {}
    for name in [COUNT_ONLY, WITHOUT_COUNT, WITH_COUNT]:
        p = test[name].to_numpy()
        results[name] = {"mejora_vs_media_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                         "ic95_mejora_pct": pitcher_bootstrap(test, improvement(p)),
                         "ic95_diferencia_vs_location_pct": pitcher_bootstrap(test, improvement(p, with_count))}
    return results


def split_half(pitches: pd.DataFrame, year: int) -> dict:
    """Confiabilidad entre pitches pares e impares del pitcher, con Spearman-Brown."""
    season = pitches[pitches.year == year].sort_values("pitch_seq")
    season = season.assign(half=season.groupby("pitcher_anon_id").cumcount() % 2)
    halves = season.groupby(["pitcher_anon_id", "half"])[[WITH_COUNT, WITHOUT_COUNT]].mean().unstack("half")
    halves = halves[season.groupby("pitcher_anon_id").size().reindex(halves.index) >= MIN_PITCHES_PER_PERIOD]
    samples = bootstrap_rows(len(halves))

    def reliability(column, idx):
        value = r(halves[(column, 0)].to_numpy(), halves[(column, 1)].to_numpy(), idx)
        return 2 * value / (1 + value)

    everyone = np.arange(len(halves))
    return {c: {"confiabilidad": round(float(reliability(c, everyone)), 4),
                "ic95": interval([reliability(c, idx) for idx in samples])} for c in [WITH_COUNT, WITHOUT_COUNT]}


def structure(table: pd.DataFrame) -> dict:
    """R² del Pitching+ de cada pitcher con Stuff+ y cada versión de Location+."""
    samples = bootstrap_rows(len(table))

    def r2(location, idx):
        x, y = table[[STUFF, location]].iloc[idx], table[PITCHING].iloc[idx]
        return LinearRegression().fit(x, y).score(x, y)

    everyone = np.arange(len(table))
    results = {}
    for location in [WITH_COUNT, WITHOUT_COUNT]:
        results[location] = {"r2": round(float(r2(location, everyone)), 4),
                             "ic95": interval([r2(location, idx) for idx in samples])}
    results[WITHOUT_COUNT]["ic95_diferencia_vs_location"] = interval(
        [r2(WITHOUT_COUNT, idx) - r2(WITH_COUNT, idx) for idx in samples])
    return results


def by_season(pitches: pd.DataFrame, year: int) -> dict:
    table = season_table(pitches, year)
    return {
        "pitchers": len(table),
        "desviacion_entre_pitchers_por_100": {c: round(float(table[c].std()), 4) for c in VALUES},
        "acuerdo_entre_versiones": paired(table, {"con_vs_sin": (WITH_COUNT, WITHOUT_COUNT)}, "con_vs_sin"),
        "r_con_xrv_real": paired(table, {WITH_COUNT: (WITH_COUNT, TARGET), WITHOUT_COUNT: (WITHOUT_COUNT, TARGET)},
                                 WITH_COUNT),
        "r_con_stuff": paired(table, {WITH_COUNT: (WITH_COUNT, STUFF), WITHOUT_COUNT: (WITHOUT_COUNT, STUFF)},
                              WITH_COUNT),
        "r2_pitching_con_stuff_y_location": structure(table),
        "confiabilidad_mitades": split_half(pitches, year),
    }


def between_seasons(pitches: pd.DataFrame) -> dict:
    pairs = season_table(pitches, FIRST).join(season_table(pitches, SECOND), lsuffix="_antes",
                                              rsuffix="_despues", how="inner")
    return {
        "pitchers": len(pairs),
        "repeticion_2024_a_2025": paired(pairs, {c: (f"{c}_antes", f"{c}_despues") for c in [WITH_COUNT, WITHOUT_COUNT]},
                                         WITH_COUNT),
        "predice_xrv_2025": paired(pairs, {c: (f"{c}_antes", f"{TARGET}_despues") for c in [WITH_COUNT, WITHOUT_COUNT]},
                                   WITH_COUNT),
    }


def main():
    pitches, iterations = load()
    summary = {
        "nota": "Solo 2024 y 2025 (D-025). Valores por 100 pitches, centrados por temporada.",
        "variables_sin_conteo": FEATURES,
        "arboles_sin_conteo": iterations,
        "por_pitch_2025": pitch_level(pitches),
        "por_temporada": {str(FIRST): by_season(pitches, FIRST), str(SECOND): by_season(pitches, SECOND)},
        "entre_temporadas": between_seasons(pitches),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
