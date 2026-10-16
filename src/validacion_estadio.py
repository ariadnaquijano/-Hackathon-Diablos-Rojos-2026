"""Validación por estadio (park holdout, D-037).

Con 2024–2025 y los mismos 5 pliegues por pitcher que la versión oficial, cada modelo se entrena sin
ningún pitch de altitud extrema y predice los pitches de altitud extrema de los pitchers que no vio.
Así el modelo nunca vio ni al pitcher ni el aire del Harp Helú. Se compara contra el modelo nulo de la
convocatoria (promedio por conteo) y contra el modelo entrenado con todas las altitudes.

Escribe reportes/etapa_06_validacion_estadio.json, sin identificadores.

Uso:
    python src/validacion_estadio.py   # requiere src/modelo.py y src/modelo_v2.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from afinado import new_model as tuned_model
from config import HOLDOUT_SEASON, REPORTS_DIR
from exploracion_etapa_04 import CROSS_FIT_FOLDS, EXTREME
from modelo import PREDICTIONS_CACHE, SPECS, add_values, load, predict
from modelo_v2 import SETTING, V2_CACHE
from modelos_base import TARGET, group_mean, pitcher_bootstrap
from stuff_componentes import combine, new_model, outcome_values

SUMMARY_JSON = REPORTS_DIR / "etapa_06_validacion_estadio.json"
VALUES = ["stuff", "location", "pitching"]
COUNT = ["Balls", "Strikes"]


def official_predictions(pitches: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Predicciones fuera de pliegue de la versión 2, entrenada con todas las altitudes."""
    predictions = pd.read_parquet(PREDICTIONS_CACHE)
    iterations = json.loads(predictions.attrs["arboles"])
    v2 = pd.read_parquet(V2_CACHE)
    iterations["location"] = int(v2.attrs["arboles"])
    predictions = predictions.drop(columns="location").merge(v2, on="pitch_seq", validate="one_to_one")
    official, weights = add_values(pitches, predictions)
    return official, weights, iterations


def model_for(name: str, iterations: int):
    kind = SPECS[name][0]
    return tuned_model(kind, SETTING, iterations) if name == "location" else new_model(kind, iterations)


def park_holdout(history: pd.DataFrame, iterations: dict, weights: dict) -> pd.DataFrame:
    """Pitches de altitud extrema, predichos por modelos sin ese pitcher y sin altitud extrema."""
    parts = []
    for fold, (fit_rows, other_rows) in enumerate(GroupKFold(CROSS_FIT_FOLDS).split(history, groups=history.pitcher_anon_id)):
        train = history.iloc[fit_rows]
        train = train[train.altitude_category != EXTREME]
        test = history.iloc[other_rows]
        test = test[test.altitude_category == EXTREME].copy()
        for name, (kind, rows, label, features) in SPECS.items():
            subset = train[rows(train)]
            model = model_for(name, iterations[name]).fit(subset[features], label(subset))
            test[name] = predict(model, kind, test, features)
        test["stuff"] = combine(test, outcome_values(train))
        test["pitching"] = weights["intercepto"] + weights["stuff"] * test.stuff + weights["location"] * test.location
        test["media_conteo"] = group_mean(train, test, COUNT)
        test["media_liga"] = train[TARGET].mean()
        parts.append(test[["pitch_seq", "pitcher_anon_id", TARGET, *VALUES, "media_conteo", "media_liga"]])
        print(f"pliegue {fold + 1} listo", flush=True)
    return pd.concat(parts, ignore_index=True)


def gains(test: pd.DataFrame, columns: list[str], reference: str = "media_conteo", versus: pd.DataFrame | None = None) -> dict:
    y = test[TARGET].to_numpy()
    base = test[reference].to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            denominator = np.mean((y[idx] - base[idx]) ** 2)
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / denominator
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / denominator
            return 100 * gain
        return statistic

    result = {}
    for name in columns:
        p = test[name].to_numpy()
        result[name] = {f"mejora_vs_{reference}_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                        "ic95_pct": pitcher_bootstrap(test, improvement(p))}
        if versus is not None:
            result[name]["ic95_diferencia_vs_todas_las_altitudes_pct"] = pitcher_bootstrap(
                test, improvement(p, versus[name].to_numpy()))
    return result


def calibration(test: pd.DataFrame) -> dict:
    result = {"real_por_100": round(float(100 * test[TARGET].mean()), 4)}
    for name in VALUES:
        slope = np.polyfit(test[name], test[TARGET], 1)[0]
        result[name] = {"predicho_por_100": round(float(100 * test[name].mean()), 4), "pendiente": round(float(slope), 3)}
    return result


def main():
    pitches = load()
    official, weights, iterations = official_predictions(pitches)
    history = pitches[(pitches.year < HOLDOUT_SEASON) & (pitches.pitcher_anon_id != "sin_id")].reset_index(drop=True)
    holdout = park_holdout(history, iterations, weights)
    full = holdout[["pitch_seq"]].merge(official[["pitch_seq", *VALUES]], on="pitch_seq", validate="one_to_one")
    summary = {
        "nota": "2024–2025; modelos sin el pitcher y sin altitud extrema, evaluados en altitud extrema (D-037).",
        "pitches": len(holdout), "pitchers": int(holdout.pitcher_anon_id.nunique()),
        "sin_altitud_extrema": gains(holdout, VALUES, versus=full),
        "con_todas_las_altitudes": gains(holdout.drop(columns=VALUES).join(full[VALUES]), VALUES),
        "contra_media_liga": gains(holdout, [*VALUES, "media_conteo"], reference="media_liga"),
        "calibracion": calibration(holdout),
    }
    summary["pasa"] = all(summary["sin_altitud_extrema"][v]["ic95_pct"][0] > 0 for v in VALUES)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
