"""Etapa 4, versión 2 del modelo: Location+ con árboles de 31 hojas (D-035).

El afinado con 2024 → 2025 (`src/afinado.py`) cambió solo Location+; Stuff+ se queda igual. Este script
reentrena Location+ con la configuración elegida, rehace los pesos de Pitching+ y repite las pruebas
de `src/modelo.py` en 2026. Es la cuarta mirada a 2026 y se reporta junto a la versión 1, sin
reemplazarla.

Escribe reportes/etapa_04_modelo_v2.json y la tabla por pitcher en escala 100
data/processed/valores_pitchers_v2.parquet, que no se sube al repo.

Uso:
    python src/modelo.py      # primero, la versión 1
    python src/afinado.py
    python src/modelo_v2.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from afinado import LOCATION, SETTINGS, fit, new_model
from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import CROSS_FIT_FOLDS, altitude_consistency
from modelo import (PREDICTIONS_CACHE, VALUES, add_values, describe_scale, forward, load, pitch_level, plus_scale,
                    same_season, stability)
from modelos_base import TARGET

SUMMARY_JSON = REPORTS_DIR / "etapa_04_modelo_v2.json"
V2_CACHE = ROOT / "data" / "processed" / "predicciones_location_v2.parquet"
PITCHER_VALUES_V2 = ROOT / "data" / "processed" / "valores_pitchers_v2.parquet"
SETTING = SETTINGS["hojas1000_31"]


def location_v2(pitches: pd.DataFrame) -> tuple[np.ndarray, int]:
    """2026 con un modelo de 2024–2025; 2024–2025 con modelos que no vieron al pitcher."""
    history = pitches[pitches.year < HOLDOUT_SEASON]
    holdout = (pitches.year == HOLDOUT_SEASON).to_numpy()
    model, iterations = fit("regresor", SETTING, history, history[TARGET], LOCATION)
    prediction = np.full(len(pitches), np.nan)
    prediction[holdout] = model.predict(pitches[holdout][LOCATION])
    positions = np.flatnonzero(~holdout)
    for fit_rows, other_rows in GroupKFold(CROSS_FIT_FOLDS).split(history, groups=history.pitcher_anon_id):
        train = history.iloc[fit_rows]
        fold_model = new_model("regresor", SETTING, iterations).fit(train[LOCATION], train[TARGET])
        prediction[positions[other_rows]] = fold_model.predict(history.iloc[other_rows][LOCATION])
    return prediction, iterations


def main():
    pitches = load()
    predictions = pd.read_parquet(PREDICTIONS_CACHE)
    if V2_CACHE.exists():
        v2 = pd.read_parquet(V2_CACHE)
        iterations = int(v2.attrs["arboles"])
    else:
        prediction, iterations = location_v2(pitches)
        v2 = pd.DataFrame({"pitch_seq": pitches.pitch_seq, "location": prediction})
        v2.attrs["arboles"] = str(iterations)
        v2.to_parquet(V2_CACHE, index=False)
    predictions = predictions.drop(columns="location").merge(v2, on="pitch_seq", validate="one_to_one")
    pitches, weights = add_values(pitches, predictions)
    values = plus_scale(pitches)
    values.to_parquet(PITCHER_VALUES_V2, index=False)
    evaluated = pitches[pitches.pitcher_anon_id != "sin_id"]
    holdout = evaluated[evaluated.year == HOLDOUT_SEASON].reset_index(drop=True)
    columns = ["lineal_por_tipo", "lineal_nivel_mar", *VALUES]
    summary = {
        "nota": "Versión 2 (D-035): Location+ con 31 hojas. Cuarta mirada a 2026, junto a la versión 1.",
        "arboles_location": iterations,
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
