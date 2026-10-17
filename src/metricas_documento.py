"""Métricas del documento técnico: RMSE y calibración del modelo oficial (versión 3, D-040).

La convocatoria pide RMSE y calibración en holdout contra el modelo nulo (promedio de xRunValue por
conteo). Aquí se reportan con las mismas predicciones congeladas, sin elegir nada:

- pitcher holdout: 2024–2025, cada pitch predicho por un modelo que no vio a su pitcher;
- season holdout: 2026, con modelos entrenados en 2024–2025 (la misma mirada de D-040, otra métrica).

El park holdout está en src/validacion_estadio.py.

Escribe reportes/etapa_06_metricas_documento.json.

Uso:
    python src/metricas_documento.py   # requiere src/modelo_v3.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

from config import HOLDOUT_SEASON, REPORTS_DIR
from exploracion_etapa_04 import CROSS_FIT_FOLDS
from modelo import load
from modelos_base import PREDICTIONS_PARQUET, TARGET, pitcher_bootstrap
from modelo_v3 import official_pitches

SUMMARY_JSON = REPORTS_DIR / "etapa_06_metricas_documento.json"
COLUMNS = ["media_conteo", "stuff", "location", "pitching"]
DECILES = 10


def rmse_table(test: pd.DataFrame) -> dict:
    y = test[TARGET].to_numpy()
    null = test.media_conteo.to_numpy()
    result = {}
    for name in COLUMNS:
        p = test[name].to_numpy()
        result[name] = {"rmse": round(float(np.sqrt(np.mean((y - p) ** 2))), 5)}
        if name != "media_conteo":
            result[name]["ic95_diferencia_rmse_vs_nulo"] = pitcher_bootstrap(
                test, lambda idx, p=p: np.sqrt(np.mean((y[idx] - p[idx]) ** 2)) - np.sqrt(np.mean((y[idx] - null[idx]) ** 2)))
    return result


def calibration(test: pd.DataFrame, column: str = "pitching") -> dict:
    """Promedio predicho contra real por decil de la predicción, en carreras por 100 pitches."""
    deciles = pd.qcut(test[column], DECILES, labels=False)
    table = test.groupby(deciles).agg(predicho=(column, "mean"), real=(TARGET, "mean")) * 100
    slope = np.polyfit(test[column], test[TARGET], 1)[0]
    return {"pendiente": round(float(slope), 3),
            "deciles": table.round(3).reset_index(drop=True).to_dict(orient="list")}


def out_of_fold_pitching(history: pd.DataFrame) -> np.ndarray:
    """Pitching+ con pesos ajustados en otros pitchers (D-042): la pendiente deja de ser 1 por construcción."""
    prediction = np.empty(len(history))
    for fit_rows, other_rows in GroupKFold(CROSS_FIT_FOLDS).split(history, groups=history.pitcher_anon_id):
        stack = LinearRegression().fit(history.iloc[fit_rows][["stuff", "location"]], history.iloc[fit_rows][TARGET])
        prediction[other_rows] = stack.predict(history.iloc[other_rows][["stuff", "location"]])
    return prediction


def main():
    pitches = load()
    official, _ = official_pitches(pitches)
    null = pd.read_parquet(PREDICTIONS_PARQUET, columns=["pitch_seq", "media_conteo"])
    official = official.merge(null, on="pitch_seq", validate="one_to_one")
    official = official[official.pitcher_anon_id != "sin_id"]
    summary = {"nota": "Modelo oficial (versión 3). Las mismas predicciones de D-040; solo cambia la métrica."}
    for name, rows in (("pitcher_holdout_2024_2025", official.year < HOLDOUT_SEASON),
                       ("season_holdout_2026", official.year == HOLDOUT_SEASON)):
        test = official[rows].reset_index(drop=True)
        summary[name] = {"pitches": len(test), "rmse": rmse_table(test),
                         "calibracion_pitching": calibration(test), "calibracion_stuff": calibration(test, "stuff")}
        if name.startswith("pitcher"):
            test["pitching_pesos_fuera_de_pliegue"] = out_of_fold_pitching(test)
            summary[name]["calibracion_pitching_pesos_fuera_de_pliegue"] = calibration(test, "pitching_pesos_fuera_de_pliegue")
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
