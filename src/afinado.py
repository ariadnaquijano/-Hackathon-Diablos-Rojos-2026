"""Etapa 4, versión 2: afinado de Stuff+ y Location+ (D-035).

Se entrena con 2024 y se evalúa en 2025; 2026 no se toca. Cada configuración cambia los
hiperparámetros del gradient boosting y, para Stuff+, agrega variables físicas que no cambian con el
aire. La versión 1 es la primera de cada lista.

Regla fijada antes de correr, para Stuff+ y Location+ por separado:

- gana la configuración con menor error por pitch en 2025;
- se adopta solo si le gana a la versión 1 por pitch con intervalo fuera de cero y no empeora el error
  por pitcher;
- si ninguna cumple, se queda la versión 1.

Escribe reportes/etapa_04_afinado.json.

Uso:
    python src/afinado.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR, ROOT
from exploracion_etapa_04 import MAX_ITERATIONS, MODELS, compare_pitchers
from modelos_base import MIN_PITCHES_PER_PERIOD, RANDOM_SEED, TARGET, pitcher_bootstrap
from stuff_componentes import COMPONENTS, FEATURES as STUFF_V1, combine, load, loss, outcome_values

SUMMARY_JSON = REPORTS_DIR / "etapa_04_afinado.json"
PREDICTIONS_CACHE = ROOT / "data" / "processed" / "predicciones_afinado.parquet"
TRAIN_SEASON, TEST_SEASON = HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1
EXTRA_STUFF = ["magnus_dependence", "total_break_sea_level", "haa_rel", "arsenal_size"]
LOCATION = MODELS["location"][0]
SETTINGS = {"hojas1000_15": (1000, 15), "hojas200_15": (200, 15), "hojas1000_31": (1000, 31), "hojas200_31": (200, 31)}
STUFF_CONFIGS = {f"stuff_{name}{suffix}": (setting, features)
                 for suffix, features in (("", STUFF_V1), ("_fisica", [*STUFF_V1, *EXTRA_STUFF]))
                 for name, setting in SETTINGS.items()}
LOCATION_CONFIGS = {f"location_{name}": (setting, LOCATION) for name, setting in SETTINGS.items()}
STUFF_V1_NAME, LOCATION_V1_NAME = "stuff_hojas1000_15", "location_hojas1000_15"


def load_pitches() -> pd.DataFrame:
    pitches = load()
    extra = pd.read_parquet(MODEL_PARQUET, columns=["pitch_seq", *EXTRA_STUFF])
    return pitches.merge(extra, on="pitch_seq", how="left", validate="one_to_one")


def new_model(kind: str, setting: tuple[int, int], iterations: int = MAX_ITERATIONS):
    min_leaf, leaves = setting
    model = HistGradientBoostingClassifier if kind == "clasificador" else HistGradientBoostingRegressor
    return model(max_iter=iterations, learning_rate=0.05, max_leaf_nodes=leaves, min_samples_leaf=min_leaf,
                 l2_regularization=1.0, categorical_features="from_dtype", random_state=RANDOM_SEED)


def fit(kind: str, setting: tuple[int, int], train: pd.DataFrame, y: pd.Series, features: list[str]):
    """Árboles elegidos con un 20 % de pitchers no vistos; después se reentrena con todo 2024."""
    split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=RANDOM_SEED)
    fit_rows, check_rows = next(split.split(train, groups=train.pitcher_anon_id))
    model = new_model(kind, setting).fit(train.iloc[fit_rows][features], y.iloc[fit_rows])
    stages = model.staged_predict_proba if kind == "clasificador" else model.staged_predict
    errors = [loss(kind, y.iloc[check_rows].to_numpy(), p) for p in stages(train.iloc[check_rows][features])]
    iterations = int(np.argmin(errors)) + 1
    return new_model(kind, setting, iterations).fit(train[features], y), iterations


def stuff_prediction(train: pd.DataFrame, test: pd.DataFrame, setting, features) -> tuple[np.ndarray, dict]:
    predicted, iterations = pd.DataFrame(index=test.index), {}
    for name, (rows, label) in COMPONENTS.items():
        subset = train[rows(train)]
        model, iterations[name] = fit("clasificador", setting, subset, label(subset).astype(int), features)
        predicted[name] = model.predict_proba(test[features])[:, 1]
    balls_in_play = train[train.outcome == "batazo"]
    model, iterations["valor_batazo"] = fit("regresor", setting, balls_in_play, balls_in_play.contact_value, features)
    predicted["valor_batazo"] = model.predict(test[features])
    return combine(predicted, outcome_values(train)), iterations


def predict_all(pitches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    train, test = pitches[pitches.year == TRAIN_SEASON], pitches[pitches.year == TEST_SEASON]
    predictions, iterations = pd.DataFrame({"pitch_seq": test.pitch_seq}), {}
    for name, (setting, features) in STUFF_CONFIGS.items():
        predictions[name], iterations[name] = stuff_prediction(train, test, setting, features)
        print(f"{name}: {iterations[name]}", flush=True)
    for name, (setting, features) in LOCATION_CONFIGS.items():
        model, iterations[name] = fit("regresor", setting, train, train[TARGET], features)
        predictions[name] = model.predict(test[features])
        print(f"{name}: {iterations[name]}", flush=True)
    return predictions, iterations


def pitch_level(test: pd.DataFrame, columns: list[str], reference: str, mean: float) -> dict:
    y = test[TARGET].to_numpy()
    base = test[reference].to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            denominator = np.mean((y[idx] - mean) ** 2)
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / denominator
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / denominator
            return 100 * gain
        return statistic

    return {name: {"mejora_vs_media_pct": round(float(improvement(test[name].to_numpy())(np.arange(len(y)))), 4),
                   f"ic95_diferencia_vs_{reference}_pct": pitcher_bootstrap(test, improvement(test[name].to_numpy(), base))}
            for name in columns}


def pitcher_level(test: pd.DataFrame, columns: list[str], reference: str) -> dict:
    centered = test[["pitcher_anon_id", TARGET, *columns]].copy()
    centered[[TARGET, *columns]] -= centered[[TARGET, *columns]].mean()
    table = centered.groupby("pitcher_anon_id").agg(pitches=(TARGET, "size"), **{c: (c, "mean") for c in [TARGET, *columns]})
    table[[TARGET, *columns]] *= 100
    table = table[table.pitches >= MIN_PITCHES_PER_PERIOD]
    return {"pitchers": len(table), **compare_pitchers(table, TARGET, columns, reference)}


def decide(by_pitch: dict, by_pitcher: dict, reference: str) -> str:
    best = max(by_pitch, key=lambda name: by_pitch[name]["mejora_vs_media_pct"])
    if best == reference:
        return reference
    beats = by_pitch[best][f"ic95_diferencia_vs_{reference}_pct"][0] > 0
    not_worse = by_pitcher[best]["ecm_por_100"] <= by_pitcher[reference]["ecm_por_100"]
    return best if beats and not_worse else reference


def main():
    pitches = load_pitches()
    if PREDICTIONS_CACHE.exists():
        predictions = pd.read_parquet(PREDICTIONS_CACHE)
        iterations = json.loads(predictions.attrs["arboles"])
    else:
        predictions, iterations = predict_all(pitches)
        predictions.attrs["arboles"] = json.dumps(iterations)
        predictions.to_parquet(PREDICTIONS_CACHE, index=False)
    test = pitches[pitches.year == TEST_SEASON][["pitch_seq", "pitcher_anon_id", TARGET]]
    test = test.merge(predictions, on="pitch_seq", validate="one_to_one")
    test = test[test.pitcher_anon_id != "sin_id"].reset_index(drop=True)
    mean = float(pitches.loc[pitches.year == TRAIN_SEASON, TARGET].mean())
    summary = {"nota": "Entrenado con 2024, evaluado en 2025 (D-035). 2026 no se usa.", "arboles": iterations}
    for piece, configs, reference in (("stuff", STUFF_CONFIGS, STUFF_V1_NAME), ("location", LOCATION_CONFIGS, LOCATION_V1_NAME)):
        by_pitch = pitch_level(test, list(configs), reference, mean)
        by_pitcher = pitcher_level(test, list(configs), reference)
        summary[piece] = {"por_pitch_2025": by_pitch, "por_pitcher_2025": by_pitcher,
                          "elegida": decide(by_pitch, by_pitcher, reference)}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
