"""Etapa 4, camino 1 de Stuff+: modelar los componentes del pitch en lugar de su valor final.

El xRV de un pitch es casi todo ruido: el mismo pitch puede terminar en strike o en bola. En lugar de
predecir ese valor directo, se predice cada paso por separado, solo con la forma del pitch (las mismas
variables del Stuff+ a nivel del mar, D-001):

- P(swing)
- P(whiff | swing)
- P(foul | contacto)
- valor esperado del batazo si hay bola en juego
- P(strike cantado | no swing)

Después se combinan con el valor promedio en carreras de cada desenlace en 2024:

    Stuff = P(swing) × [P(whiff) × V(whiff) + (1 − P(whiff)) × (P(foul) × V(foul) + (1 − P(foul)) × V(batazo))]
          + (1 − P(swing)) × [P(strike) × V(strike) + (1 − P(strike)) × V(bola o pelotazo)]

Regla fijada antes de probar (docs/04_plan_modelo.md, D-025): se entrena con 2024 y se evalúa en 2025.
Gana el camino con menor error por pitcher en 2025. Si ninguno le gana a la regresión lineal por tipo
con intervalo fuera de cero, se reporta así y la lineal se queda como Stuff+. 2026 no se toca.

Chequeo agregado después de ver el resultado, y marcado así en el reporte: la lineal base usa el
movimiento observado, que lleva el efecto de la altitud. Se compara también contra la misma lineal con
la forma a nivel del mar, que tiene la misma información que los Stuff+.

Los valores son promedios de todos los conteos, no del conteo del pitch: las probabilidades no ven el
conteo, y combinarlas con valores de un conteo específico mezcla información que el modelo no tuvo (una
primera corrida así quedó peor que la media por pitch, −0.36 %).

Escribe reportes/etapa_04_stuff_componentes.json.

Uso:
    python src/stuff_componentes.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit

from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import MAX_ITERATIONS, MODELS, compare_pitchers, load_pitches
from modelos_base import (MIN_PITCHES_PER_PERIOD, RANDOM_SEED, TARGET, group_mean, linear_by_type,
                          pitcher_bootstrap)

SEA_LEVEL_LINEAR = ["RelSpeed", "ivb_sea_level", "hb_sea_level", "Extension"]

SUMMARY_JSON = REPORTS_DIR / "etapa_04_stuff_componentes.json"
PREDICTIONS_CACHE = ROOT / "data" / "processed" / "predicciones_stuff_componentes.parquet"
TRAIN_SEASON, TEST_SEASON = HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1
FEATURES = MODELS["stuff_nivel_mar"][0]

# Desenlace de cada pitch según lo que hizo el bateador.
OUTCOME = {"StrikeSwinging": "whiff", "StrikeCalled": "strike", "InPlay": "batazo",
           "FoulBall": "foul", "FoulBallFieldable": "foul", "FoulBallNotFieldable": "foul",
           "BallCalled": "bola", "BallinDirt": "bola", "HitByPitch": "bola"}
SWINGS = {"whiff", "foul", "batazo"}

# Cada componente: a qué pitches se ajusta y qué predice.
COMPONENTS = {
    "p_swing": (lambda f: np.full(len(f), True), lambda f: f.outcome.isin(SWINGS)),
    "p_whiff": (lambda f: f.outcome.isin(SWINGS), lambda f: f.outcome == "whiff"),
    "p_foul": (lambda f: f.outcome.isin({"foul", "batazo"}), lambda f: f.outcome == "foul"),
    "p_strike": (lambda f: ~f.outcome.isin(SWINGS), lambda f: f.outcome == "strike"),
}


def load() -> pd.DataFrame:
    pitches = load_pitches()
    pitches = pitches[pitches.year.isin([TRAIN_SEASON, TEST_SEASON])]
    extra = pd.read_parquet(ROOT / "data" / "processed" / "dataset_modelo.parquet",
                            columns=["pitch_seq", "PitchCall", "count_value_before"])
    pitches = pitches.merge(extra, on="pitch_seq", how="left", validate="one_to_one")
    pitches["outcome"] = pitches.PitchCall.map(OUTCOME)
    # Valor del batazo sin el conteo: el xRV de una bola en juego es su valor esperado menos el conteo.
    pitches["contact_value"] = pitches[TARGET] + pitches.count_value_before
    return pitches[pitches.outcome.notna()].reset_index(drop=True)


def new_model(kind: str, iterations: int = MAX_ITERATIONS):
    model = HistGradientBoostingClassifier if kind == "clasificador" else HistGradientBoostingRegressor
    return model(max_iter=iterations, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=1000,
                 l2_regularization=1.0, categorical_features="from_dtype", random_state=RANDOM_SEED)


def loss(kind: str, y: np.ndarray, p: np.ndarray) -> float:
    if kind == "clasificador":
        p = np.clip(p[:, 1], 1e-6, 1 - 1e-6)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return float(np.mean((y - p) ** 2))


def choose_iterations(kind: str, train: pd.DataFrame, y: pd.Series, features: list[str] = FEATURES) -> int:
    """Número de árboles con menor error en un 20 % de pitchers que el modelo no vio."""
    split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=RANDOM_SEED)
    fit_rows, check_rows = next(split.split(train, groups=train.pitcher_anon_id))
    model = new_model(kind).fit(train.iloc[fit_rows][features], y.iloc[fit_rows])
    stages = model.staged_predict_proba if kind == "clasificador" else model.staged_predict
    errors = [loss(kind, y.iloc[check_rows].to_numpy(), p) for p in stages(train.iloc[check_rows][features])]
    return int(np.argmin(errors)) + 1


def fit(kind: str, train: pd.DataFrame, y: pd.Series):
    """Modelo con los árboles elegidos, reentrenado con todo el entrenamiento."""
    iterations = choose_iterations(kind, train, y)
    return new_model(kind, iterations).fit(train[FEATURES], y), iterations


def outcome_values(train: pd.DataFrame) -> pd.Series:
    """Valor promedio en carreras de cada desenlace en entrenamiento, sobre todos los conteos.

    La bola incluye el pelotazo en su proporción real. Para el batazo se guarda el valor del conteo
    promedio en que ocurre, que se resta al valor esperado del contacto.
    """
    values = train.groupby("outcome")[TARGET].mean()
    values["conteo_batazo"] = train.loc[train.outcome == "batazo", "count_value_before"].mean()
    return values


def components(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Predicción de cada componente para los pitches de 2025, y su calidad contra la tasa base."""
    predicted, report = pd.DataFrame(index=test.index), {}
    for name, (rows, label) in COMPONENTS.items():
        subset = train[rows(train)]
        model, iterations = fit("clasificador", subset, label(subset).astype(int))
        predicted[name] = model.predict_proba(test[FEATURES])[:, 1]
        evaluated = test[rows(test)]
        y = label(evaluated).astype(int).to_numpy()
        p = predicted.loc[evaluated.index, name].to_numpy()
        rate = np.full_like(p, label(subset).mean())
        report[name] = {"arboles": iterations, "pitches_evaluados": len(y),
                        "mejora_log_loss_vs_tasa_base_pct": round(100 * (1 - loss("clasificador", y, np.c_[1 - p, p])
                                                                          / loss("clasificador", y, np.c_[1 - rate, rate])), 3)}
    balls_in_play = train[train.outcome == "batazo"]
    model, iterations = fit("regresor", balls_in_play, balls_in_play.contact_value)
    predicted["valor_batazo"] = model.predict(test[FEATURES])
    evaluated = test[test.outcome == "batazo"]
    y, p = evaluated.contact_value.to_numpy(), predicted.loc[evaluated.index, "valor_batazo"].to_numpy()
    report["valor_batazo"] = {"arboles": iterations, "pitches_evaluados": len(y),
                              "mejora_ecm_vs_media_pct": round(100 * (1 - np.mean((y - p) ** 2)
                                                                      / np.mean((y - balls_in_play.contact_value.mean()) ** 2)), 3)}
    return predicted, report


def combine(predicted: pd.DataFrame, v: pd.Series) -> np.ndarray:
    contact = predicted.p_foul * v.foul + (1 - predicted.p_foul) * (predicted.valor_batazo - v.conteo_batazo)
    swing = predicted.p_whiff * v.whiff + (1 - predicted.p_whiff) * contact
    take = predicted.p_strike * v.strike + (1 - predicted.p_strike) * v.bola
    return (predicted.p_swing * swing + (1 - predicted.p_swing) * take).to_numpy()


def predict(pitches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    train = pitches[pitches.year == TRAIN_SEASON]
    test = pitches[pitches.year == TEST_SEASON]
    predicted, report = components(train, test)
    direct, report["stuff_directo_arboles"] = fit("regresor", train, train[TARGET])
    fallback = group_mean(train, test, ["pitch_class", "pitcher_hand"])
    predictions = pd.DataFrame({
        "pitch_seq": test.pitch_seq,
        "media_tipo_mano": fallback,
        "lineal_por_tipo": linear_by_type(train, test, fallback),
        "lineal_nivel_mar": linear_by_type(train, test, fallback, SEA_LEVEL_LINEAR),
        "stuff_directo": direct.predict(test[FEATURES]),
        **{name: predicted[name] for name in predicted},
    })
    return predictions, report


def pitch_level(test: pd.DataFrame, columns: list[str], reference: str) -> dict:
    """Mejora del error por pitch en 2025 contra la media de 2024, y diferencia contra `reference`."""
    y = test[TARGET].to_numpy()
    mean = np.full(len(y), test.attrs["media_entrenamiento"])
    base = test[reference].to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / np.mean((y[idx] - mean[idx]) ** 2)
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / np.mean((y[idx] - mean[idx]) ** 2)
            return 100 * gain
        return statistic

    return {name: {"mejora_vs_media_pct": round(float(improvement(test[name].to_numpy())(np.arange(len(y)))), 4),
                   "ic95_mejora_pct": pitcher_bootstrap(test, improvement(test[name].to_numpy())),
                   f"ic95_diferencia_vs_{reference}_pct": pitcher_bootstrap(test, improvement(test[name].to_numpy(), base))}
            for name in columns}


def pitcher_level(test: pd.DataFrame, columns: list[str], reference: str) -> dict:
    """Por pitcher en 2025, centrado por temporada: lo predicho para sus pitches contra su xRV real."""
    centered = test[["pitcher_anon_id", TARGET, *columns]].copy()
    centered[[TARGET, *columns]] -= centered[[TARGET, *columns]].mean()
    table = centered.groupby("pitcher_anon_id").agg(pitches=(TARGET, "size"),
                                                    **{c: (c, "mean") for c in [TARGET, *columns]})
    table[[TARGET, *columns]] *= 100
    table = table[table.pitches >= MIN_PITCHES_PER_PERIOD]
    return {"pitchers": len(table), **compare_pitchers(table, TARGET, columns, reference)}


def main():
    pitches = load()
    if PREDICTIONS_CACHE.exists():
        predictions = pd.read_parquet(PREDICTIONS_CACHE)
        report = json.loads(predictions.attrs["componentes"])
    else:
        predictions, report = predict(pitches)
        predictions.attrs["componentes"] = json.dumps(report)
        predictions.to_parquet(PREDICTIONS_CACHE, index=False)
    test = pitches[pitches.year == TEST_SEASON][["pitch_seq", "pitcher_anon_id", TARGET]]
    test = test.merge(predictions, on="pitch_seq", validate="one_to_one")
    test["stuff_componentes"] = combine(test, outcome_values(pitches[pitches.year == TRAIN_SEASON]))
    test = test[test.pitcher_anon_id != "sin_id"].reset_index(drop=True)
    test.attrs["media_entrenamiento"] = float(pitches.loc[pitches.year == TRAIN_SEASON, TARGET].mean())
    candidates = ["media_tipo_mano", "lineal_por_tipo", "stuff_directo", "stuff_componentes"]
    sea_level = ["lineal_nivel_mar", "stuff_directo", "stuff_componentes"]
    summary = {
        "nota": "Entrenado con 2024, evaluado en 2025 (D-025). 2026 no se usa.",
        "componentes": report,
        "por_pitch_2025": pitch_level(test, candidates, "lineal_por_tipo"),
        "por_pitcher_2025": pitcher_level(test, candidates, "lineal_por_tipo"),
        "chequeo_posterior_misma_informacion": {
            "por_pitch_2025": pitch_level(test, sea_level, "lineal_nivel_mar"),
            "por_pitch_2025_contra_directo": pitch_level(test, ["stuff_componentes"], "stuff_directo"),
            "por_pitcher_2025": pitcher_level(test, sea_level, "lineal_nivel_mar"),
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
