"""Etapa 4: modelo final de Stuff+, Location+ y Pitching+, y su única evaluación en 2026.

Decisiones que lo fijan (docs/decisiones.md):

- D-027: Stuff+ por componentes, solo con la forma a nivel del mar.
- D-028: Location+ con ubicación y conteo.
- D-029: Pitching+ como suma pesada de los dos.
- D-030: proyección a futuro con historia y Pitching+, pesos de 2024 → 2025.
- D-026: se compara contra la lineal observada y contra la lineal a nivel del mar.

Cada modelo se entrena con 2024–2025 y predice 2026. Además, cada pitch de 2024–2025 recibe la
predicción de un modelo que no vio a ese pitcher (5 pliegues por pitcher), para la proyección y para
los pesos de Pitching+. 2026 se mira una sola vez, al final, y se reporta lo que salga (D-030).

Escribe reportes/etapa_04_modelo.json, sin identificadores. Los valores por pitcher van a
data/processed/valores_pitchers.parquet, que no se sube al repo.

Uso:
    python src/modelo.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR, ROOT
from exploracion_etapa_04 import (CROSS_FIT_FOLDS, MODELS, altitude_consistency, compare_pitchers,
                                  load_pitches)
from modelos_base import (MIN_PITCHES_PER_PERIOD, PREDICTIONS_PARQUET, TARGET, center_by_season,
                          group_mean, linear_by_type, pitcher_bootstrap, pitcher_table, shrunk_persistence)
from stuff_componentes import (COMPONENTS, FEATURES as STUFF_FEATURES, OUTCOME, SEA_LEVEL_LINEAR, choose_iterations,
                               combine, new_model, outcome_values)

SUMMARY_JSON = REPORTS_DIR / "etapa_04_modelo.json"
PREDICTIONS_CACHE = ROOT / "data" / "processed" / "predicciones_modelo.parquet"
PITCHER_VALUES = ROOT / "data" / "processed" / "valores_pitchers.parquet"
LOCATION_FEATURES = MODELS["location"][0]
VALUES = ["stuff", "location", "pitching"]

# Cada modelo: tipo, a qué pitches se ajusta, qué predice y con qué variables.
SPECS = {
    **{name: ("clasificador", rows, lambda f, label=label: label(f).astype(int), STUFF_FEATURES)
       for name, (rows, label) in COMPONENTS.items()},
    "valor_batazo": ("regresor", lambda f: f.outcome == "batazo", lambda f: f.contact_value, STUFF_FEATURES),
    "location": ("regresor", lambda f: np.full(len(f), True), lambda f: f[TARGET], LOCATION_FEATURES),
}


def load() -> pd.DataFrame:
    pitches = load_pitches()
    extra = duckdb.sql(f"select pitch_seq, PitchCall, count_value_before from '{MODEL_PARQUET}'").df()
    pitches = pitches.merge(extra, on="pitch_seq", how="left", validate="one_to_one")
    pitches["outcome"] = pitches.PitchCall.map(OUTCOME)
    pitches["contact_value"] = pitches[TARGET] + pitches.count_value_before
    pitches = pitches[pitches.outcome.notna()]
    base = pd.read_parquet(PREDICTIONS_PARQUET, columns=["pitch_seq", "media_liga", "lineal_por_tipo"])
    return pitches.merge(base, on="pitch_seq", how="left", validate="one_to_one").reset_index(drop=True)


def predict(model, kind: str, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    return model.predict_proba(frame[features])[:, 1] if kind == "clasificador" else model.predict(frame[features])


def fit_and_predict(pitches: pd.DataFrame, spec: tuple) -> tuple[np.ndarray, int]:
    """2026 con un modelo de 2024–2025; 2024–2025 con modelos que no vieron al pitcher."""
    kind, rows, label, features = spec
    history = pitches[pitches.year < HOLDOUT_SEASON]
    subset = history[rows(history)]
    iterations = choose_iterations(kind, subset, label(subset), features)
    prediction = np.full(len(pitches), np.nan)
    holdout = (pitches.year == HOLDOUT_SEASON).to_numpy()
    model = new_model(kind, iterations).fit(subset[features], label(subset))
    prediction[holdout] = predict(model, kind, pitches[holdout], features)
    positions = np.flatnonzero(~holdout)
    for fit_rows, other_rows in GroupKFold(CROSS_FIT_FOLDS).split(history, groups=history.pitcher_anon_id):
        train = history.iloc[fit_rows]
        train = train[rows(train)]
        model = new_model(kind, iterations).fit(train[features], label(train))
        prediction[positions[other_rows]] = predict(model, kind, history.iloc[other_rows], features)
    return prediction, iterations


def build_predictions(pitches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    predictions, iterations = pd.DataFrame({"pitch_seq": pitches.pitch_seq}), {}
    for name, spec in SPECS.items():
        predictions[name], iterations[name] = fit_and_predict(pitches, spec)
        print(f"{name}: {iterations[name]} árboles")
    history = pitches.year < HOLDOUT_SEASON
    fallback = group_mean(pitches[history], pitches, ["pitch_class", "pitcher_hand"])
    predictions["lineal_nivel_mar"] = linear_by_type(pitches[history], pitches, fallback, SEA_LEVEL_LINEAR)
    return predictions, iterations


def add_values(pitches: pd.DataFrame, predictions: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Stuff+ como combinación de componentes y Pitching+ como suma pesada (D-029)."""
    pitches = pitches.merge(predictions, on="pitch_seq", validate="one_to_one")
    history = pitches.year < HOLDOUT_SEASON
    pitches["stuff"] = combine(pitches, outcome_values(pitches[history]))
    stack = LinearRegression().fit(pitches.loc[history, ["stuff", "location"]], pitches.loc[history, TARGET])
    pitches["pitching"] = stack.predict(pitches[["stuff", "location"]])
    weights = {"intercepto": round(float(stack.intercept_), 5), "stuff": round(float(stack.coef_[0]), 4),
               "location": round(float(stack.coef_[1]), 4)}
    return pitches, weights


def pitch_level(test: pd.DataFrame, columns: list[str]) -> dict:
    """Mejora del error por pitch en 2026 contra la media, y diferencia contra cada lineal."""
    y = test[TARGET].to_numpy()
    mean = test.media_liga.to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / np.mean((y[idx] - mean[idx]) ** 2)
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / np.mean((y[idx] - mean[idx]) ** 2)
            return 100 * gain
        return statistic

    results = {}
    for name in columns:
        p = test[name].to_numpy()
        results[name] = {"mejora_vs_media_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                         "ic95_mejora_pct": pitcher_bootstrap(test, improvement(p))}
        for reference in ["lineal_por_tipo", "lineal_nivel_mar"]:
            if name != reference:
                results[name][f"ic95_diferencia_vs_{reference}_pct"] = pitcher_bootstrap(
                    test, improvement(p, test[reference].to_numpy()))
    return results


def same_season(pitches: pd.DataFrame, columns: list[str]) -> dict:
    """Por pitcher en 2026: lo predicho para sus pitches contra su xRV real, centrado por temporada."""
    centered = center_by_season(pitches[["pitcher_anon_id", "year", TARGET, *columns]], [TARGET, *columns])
    table = pitcher_table(centered[centered.year == HOLDOUT_SEASON], [TARGET, *columns])
    table = table.query("pitches >= @MIN_PITCHES_PER_PERIOD")
    return {"pitchers": len(table),
            "contra_lineal_observada": compare_pitchers(table, TARGET, columns, "lineal_por_tipo"),
            "contra_lineal_nivel_mar": compare_pitchers(table, TARGET, columns, "lineal_nivel_mar")}


def projection_weights(history: pd.DataFrame) -> LinearRegression:
    """Pesos de la proyección: xRV de 2025 con xRV y Pitching+ de 2024, solo pares 2024 → 2025 (D-030)."""
    first, second = (pitcher_table(history[history.year == year], [TARGET, "pitching"])
                     .query("pitches >= @MIN_PITCHES_PER_PERIOD") for year in (HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1))
    pairs = first.join(second[[TARGET]], rsuffix="_despues", how="inner")
    return LinearRegression().fit(pairs[[TARGET, "pitching"]], pairs[f"{TARGET}_despues"]), len(pairs)


def forward(pitches: pd.DataFrame) -> dict:
    """El valor de 2024–2025 de cada pitcher para predecir su xRV real de 2026."""
    columns = [TARGET, *VALUES, "lineal_nivel_mar", "lineal_por_tipo"]
    centered = center_by_season(pitches[["pitcher_anon_id", "year", *columns]], columns)
    history = centered[centered.year < HOLDOUT_SEASON]
    before = pitcher_table(history, columns).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    after = pitcher_table(centered[centered.year == HOLDOUT_SEASON], [TARGET]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
    shrunk, slope, _ = shrunk_persistence(history, before)
    model, pairs = projection_weights(history)
    table = before.drop(columns=TARGET).assign(
        persistencia_encogida=shrunk, proyeccion=model.predict(before[[TARGET, "pitching"]]),
        real_2026=after[TARGET]).dropna()
    predictors = [*VALUES, "lineal_nivel_mar", "lineal_por_tipo", "proyeccion", "persistencia_encogida"]
    return {"pitchers": len(table), "pares_para_pesos": pairs, "pendiente_persistencia": slope,
            "pesos_proyeccion": {"historia": round(float(model.coef_[0]), 4),
                                 "pitching": round(float(model.coef_[1]), 4)},
            **compare_pitchers(table, "real_2026", predictors, "persistencia_encogida")}


def plus_scale(pitches: pd.DataFrame) -> pd.DataFrame:
    """Escala 100 por temporada: 100 − 10 × (valor − media) ÷ desviación entre pitchers. Más es mejor."""
    tables = []
    for year, season in pitches[pitches.pitcher_anon_id != "sin_id"].groupby("year"):
        table = pitcher_table(season, [TARGET, *VALUES, *COMPONENTS]).query("pitches >= @MIN_PITCHES_PER_PERIOD")
        centered = season[VALUES].mean() * 100
        for value in VALUES:
            table[f"{value}_plus"] = 100 - 10 * (table[value] - centered[value]) / table[value].std()
        tables.append(table.assign(year=year))
    return pd.concat(tables).reset_index()


def describe_scale(values: pd.DataFrame) -> dict:
    """Distribución de la escala y correlación entre los tres valores, sin identificadores."""
    result = {}
    for year, season in values.groupby("year"):
        plus = season[[f"{v}_plus" for v in VALUES]]
        result[str(year)] = {
            "pitchers": len(season),
            "percentiles_10_50_90": {c: [round(float(x), 1) for x in plus[c].quantile([0.1, 0.5, 0.9])] for c in plus},
            "r_entre_valores": {f"{a}_vs_{b}": round(float(plus[f"{a}_plus"].corr(plus[f"{b}_plus"])), 4)
                                for a, b in [("stuff", "location"), ("stuff", "pitching"), ("location", "pitching")]},
        }
    return result


def stability(values: pd.DataFrame) -> dict:
    """Mismo pitcher en 2024 y 2025: cuánto se repite cada valor y cada componente."""
    first, second = (values[values.year == year].set_index("pitcher_anon_id")
                     for year in (HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1))
    pairs = first.join(second, lsuffix="_antes", rsuffix="_despues", how="inner")
    return {"pitchers": len(pairs),
            **{c: round(float(pairs[f"{c}_antes"].corr(pairs[f"{c}_despues"])), 4)
               for c in [TARGET, *VALUES, *COMPONENTS]}}


def main():
    pitches = load()
    if PREDICTIONS_CACHE.exists():
        predictions = pd.read_parquet(PREDICTIONS_CACHE)
        iterations = json.loads(predictions.attrs["arboles"])
    else:
        predictions, iterations = build_predictions(pitches)
        predictions.attrs["arboles"] = json.dumps(iterations)
        predictions.to_parquet(PREDICTIONS_CACHE, index=False)
    pitches, weights = add_values(pitches, predictions)
    values = plus_scale(pitches)
    values.to_parquet(PITCHER_VALUES, index=False)
    evaluated = pitches[pitches.pitcher_anon_id != "sin_id"]
    holdout = evaluated[evaluated.year == HOLDOUT_SEASON].reset_index(drop=True)
    columns = ["lineal_por_tipo", "lineal_nivel_mar", *VALUES]
    summary = {
        "nota": "Modelo congelado (D-030). Entrenado con 2024–2025; 2026 evaluado una sola vez.",
        "arboles": iterations,
        "pesos_pitching": weights,
        "por_pitch_2026": pitch_level(holdout, columns),
        "por_pitcher_2026": same_season(evaluated, columns),
        "a_futuro_2026": forward(evaluated),
        "altitud_mismo_pitcher": altitude_consistency(evaluated, ["stuff", "pitching"], "stuff"),
        "escala_100": describe_scale(values),
        "repeticion_2024_a_2025": stability(values),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
