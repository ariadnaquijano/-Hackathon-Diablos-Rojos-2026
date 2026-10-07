"""Etapa 3: la escalera de modelos base (decisión D-020).

Todo modelo de la etapa 4 debe ganarles en 2026. Se entrenan con 2024–2025 y predicen el xRV neutral:

1. Media de la liga.
2. Media por conteo.
3. Media por tipo de pitch y mano del pitcher.
4. Regresión lineal por tipo de pitch con velocidad, movimiento y extensión.

El modelo con `altitude_category` como variable (alternativa de D-001) usa el mismo algoritmo que la
etapa 4, así que se evalúa ahí.

Se evalúan por pitch (error cuadrático) y por pitcher (qué tanto el promedio predicho de sus pitches
de 2026 coincide con su xRV real de 2026). Por pitcher también se mide la persistencia: su propio xRV
de 2024–2025 como predicción de 2026.

Escribe data/processed/predicciones_base.parquet (para comparar pitch a pitch en la etapa 4) y
reportes/modelos_base.json.

Uso:
    python src/modelos_base.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR, ROOT

SUMMARY_JSON = REPORTS_DIR / "modelos_base.json"
PREDICTIONS_PARQUET = ROOT / "data" / "processed" / "predicciones_base.parquet"
RANDOM_SEED = 2026
BOOTSTRAP_SAMPLES = 1000
TARGET = "xrv_neutral"
MIN_PITCHES_PER_PERIOD = 300
# Un tipo de pitch con menos pitches de entrenamiento usa su media en vez de la regresión.
MIN_PITCHES_FOR_REGRESSION = 1000
LINEAR_FEATURES = ["RelSpeed", "InducedVertBreak", "hb_arm_side", "Extension"]
BASELINES = {
    "media_liga": "Predecir siempre el promedio de 2024–2025",
    "media_conteo": "Promedio por conteo de bolas y strikes",
    "media_tipo_mano": "Promedio por tipo de pitch y mano del pitcher",
    "lineal_por_tipo": "Regresión lineal por tipo de pitch: velocidad, IVB, HB y extensión",
}


def load_pitches() -> pd.DataFrame:
    return duckdb.sql(f"""
        select pitch_seq, year, pitcher_anon_id, pitch_class, pitcher_hand, Balls, Strikes,
               {", ".join(LINEAR_FEATURES)}, {TARGET}
        from '{MODEL_PARQUET}'
        where {TARGET} is not null
        order by pitch_seq""").df()


def group_mean(train: pd.DataFrame, frame: pd.DataFrame, keys: list[str]) -> np.ndarray:
    """Media de entrenamiento del grupo; un grupo que no existía en entrenamiento recibe la de la liga."""
    means = train.groupby(keys)[TARGET].mean().rename("prediction").reset_index()
    return frame[keys].merge(means, on=keys, how="left").prediction.fillna(train[TARGET].mean()).to_numpy()


def linear_by_type(train: pd.DataFrame, frame: pd.DataFrame, fallback: np.ndarray) -> np.ndarray:
    """Regresión por tipo de pitch; sin física completa o con poca muestra, la media del tipo y mano."""
    prediction = fallback.copy()
    complete = frame[LINEAR_FEATURES].notna().all(axis=1).to_numpy()
    for pitch_class, rows in train[train[LINEAR_FEATURES].notna().all(axis=1)].groupby("pitch_class"):
        if len(rows) < MIN_PITCHES_FOR_REGRESSION:
            continue
        model = LinearRegression().fit(rows[LINEAR_FEATURES], rows[TARGET])
        target_rows = complete & (frame.pitch_class == pitch_class).to_numpy()
        prediction[target_rows] = model.predict(frame.loc[target_rows, LINEAR_FEATURES])
    return prediction


def predict_baselines(pitches: pd.DataFrame) -> pd.DataFrame:
    train = pitches[pitches.year < HOLDOUT_SEASON]
    by_type_hand = group_mean(train, pitches, ["pitch_class", "pitcher_hand"])
    return pd.DataFrame({
        "media_liga": np.full(len(pitches), train[TARGET].mean()),
        "media_conteo": group_mean(train, pitches, ["Balls", "Strikes"]),
        "media_tipo_mano": by_type_hand,
        "lineal_por_tipo": linear_by_type(train, pitches, by_type_hand),
    })


def pitcher_bootstrap(test: pd.DataFrame, statistic) -> list[float]:
    """IC 95 % de un estadístico remuestreando pitchers completos."""
    rng = np.random.default_rng(RANDOM_SEED)
    groups = test.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(groups))
    draws = [statistic(np.concatenate([groups[p] for p in rng.choice(pitchers, len(pitchers))]))
             for _ in range(BOOTSTRAP_SAMPLES)]
    low, high = np.percentile(draws, [2.5, 97.5])
    return [round(float(low), 5), round(float(high), 5)]


def pitch_level(test: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    """Error cuadrático en 2026 y mejora contra la media de la liga (en %)."""
    y = test[TARGET].to_numpy()
    reference = predictions.media_liga.to_numpy()

    def improvement(p):
        return lambda idx: 100 * (1 - np.mean((y[idx] - p[idx]) ** 2) / np.mean((y[idx] - reference[idx]) ** 2))

    results = {}
    for name in BASELINES:
        p = predictions[name].to_numpy()
        results[name] = {"ecm": round(float(np.mean((y - p) ** 2)), 6),
                         "mejora_vs_media_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                         "ic95_mejora_pct": pitcher_bootstrap(test, improvement(p))}
    return results


def center_by_season(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Resta a cada columna su promedio de la temporada.

    El ambiente de carreras cambia de un año a otro (10.4 carreras por juego en 2024, 12.1 en 2025), y
    Stuff+ se define contra el promedio de su temporada. Sin centrar, la comparación por pitcher
    premiaría a quien adivina el nivel de la liga, no a quien ordena bien a los pitchers.
    """
    centered = frame.copy()
    centered[columns] = frame[columns] - frame.groupby("year")[columns].transform("mean")
    return centered


def pitcher_table(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Pitches y valor medio por 100 pitches de cada pitcher."""
    table = frame.groupby("pitcher_anon_id").agg(pitches=(TARGET, "size"), **{c: (c, "mean") for c in columns})
    table[columns] *= 100
    return table


def shrunk_persistence(pitches: pd.DataFrame, history: pd.DataFrame) -> pd.Series:
    """Persistencia encogida hacia la media: cuánto se repite el xRV de un año al siguiente.

    La pendiente se estima solo con 2024 → 2025, para no mirar 2026.
    """
    seasons = [pitcher_table(pitches[pitches.year == year], [TARGET]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
               for year in (HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1)]
    pairs = seasons[0].join(seasons[1], lsuffix="_antes", rsuffix="_despues", how="inner")
    model = LinearRegression().fit(pairs[[f"{TARGET}_antes"]], pairs[f"{TARGET}_despues"])
    shrunk = model.predict(history[[TARGET]].rename(columns={TARGET: f"{TARGET}_antes"}))
    return pd.Series(shrunk, index=history.index), round(float(model.coef_[0]), 4), len(pairs)


def pitcher_level(pitches: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    """Por pitcher, en carreras por 100 pitches sobre el promedio de la temporada: lo predicho para sus
    pitches de 2026 contra su xRV real de 2026.

    Todos los modelos se evalúan sobre los mismos pitchers: los que tienen muestra en ambos periodos,
    para poder comparar con su propia historia.
    """
    columns = [TARGET, *BASELINES]
    centered = center_by_season(pd.concat([pitches[["pitcher_anon_id", "year", TARGET]], predictions], axis=1), columns)
    holdout = centered.year == HOLDOUT_SEASON
    after = pitcher_table(centered[holdout], columns).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    history = pitcher_table(centered[~holdout], [TARGET]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    both = after.join(history[[TARGET]].rename(columns={TARGET: "persistencia"}), how="inner")
    shrunk, slope, pairs = shrunk_persistence(centered[~holdout], history)
    both["persistencia_encogida"] = shrunk
    actual = both[TARGET].to_numpy()
    rng = np.random.default_rng(RANDOM_SEED)
    samples = [rng.integers(0, len(both), len(both)) for _ in range(BOOTSTRAP_SAMPLES)]

    def describe(column):
        predicted = both[column].to_numpy()
        if predicted.std() < 1e-9:
            r, interval = None, None
        else:
            r = round(float(np.corrcoef(predicted, actual)[0, 1]), 4)
            draws = [np.corrcoef(predicted[idx], actual[idx])[0, 1] for idx in samples]
            interval = [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]
        return {"r": r, "ic95_r": interval, "ecm_por_100": round(float(np.mean((actual - predicted) ** 2)), 4)}

    return {"pitchers_2026": len(after), "pitchers_con_historia": len(both),
            "pitchers_sin_historia": len(after) - len(both),
            "sd_real_por_100": round(float(actual.std()), 4),
            "persistencia_pendiente_2024_2025": {"pendiente": slope, "pitchers": pairs},
            "modelos": {name: describe(name) for name in [*BASELINES, "persistencia", "persistencia_encogida"]}}


def main():
    pitches = load_pitches()
    predictions = predict_baselines(pitches)
    holdout = (pitches.year == HOLDOUT_SEASON).to_numpy()
    test = pitches[holdout].reset_index(drop=True)
    summary = {
        "target": TARGET,
        "descripcion": BASELINES,
        "pitches_prueba": int(holdout.sum()),
        "por_pitch": pitch_level(test, predictions[holdout].reset_index(drop=True)),
        "por_pitcher": pitcher_level(pitches, predictions),
    }
    pd.concat([pitches[["pitch_seq"]], predictions], axis=1).to_parquet(PREDICTIONS_PARQUET, index=False)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
