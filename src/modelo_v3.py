"""Versión 3 del modelo oficial: Stuff+ v1 y el Location+ del equipo (D-039).

- El componente de ubicación de Pitching+ pasa a ser el xRV por pitch del modelo de Ben
  (src/location_ben.py) en su versión neutral, predicho como si el pitch fuera a nivel del mar (D-040);
  los pesos de Pitching+ se reajustan con 2024–2025.
- El Location+ por pitcher usa su fórmula: 50 % CSW+ y 50 % RV+, ajustados por cuenta, también neutral.
- Se repiten las pruebas de src/modelo.py en 2026. Es la quinta mirada a 2026, declarada en D-039:
  no se elige nada con ella.

Escribe reportes/etapa_06_modelo_v3.json y la tabla por pitcher
data/processed/valores_pitchers_v3.parquet, que no se sube al repo.

Uso:
    python src/modelo.py && python src/location_ben.py && python src/modelo_v3.py
"""

import json

import pandas as pd

from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import altitude_consistency
from location_ben import PREDICTIONS_CACHE as BEN_CACHE
from location_ben import ben_plus, residuals_by_pitcher
from modelo import (PREDICTIONS_CACHE, VALUES, add_values, describe_scale, forward, load, pitch_level, plus_scale,
                    same_season, stability)
from modelos_base import MIN_PITCHES_PER_PERIOD

SUMMARY_JSON = REPORTS_DIR / "etapa_06_modelo_v3.json"
PITCHER_VALUES_V3 = ROOT / "data" / "processed" / "valores_pitchers_v3.parquet"


def predictions_v3() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predicciones de la versión 1 con el xRV neutral de Ben en lugar del componente de ubicación."""
    ben = pd.read_parquet(BEN_CACHE)
    predictions = pd.read_parquet(PREDICTIONS_CACHE).drop(columns="location")
    predictions = predictions.merge(ben[["pitch_seq", "xRV_neutral"]].rename(columns={"xRV_neutral": "location"}), on="pitch_seq",
                                    validate="one_to_one")
    return predictions, ben


def official_pitches(pitches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Cada pitch con Stuff, Location y Pitching de la versión oficial (3), en carreras."""
    predictions, _ = predictions_v3()
    return add_values(pitches, predictions)


def ben_location_plus(ben: pd.DataFrame, values: pd.DataFrame) -> pd.Series:
    """Location+ de Ben para cada pitcher-temporada de la tabla oficial (300+ pitches)."""
    tables = []
    for year, season in ben[ben.pitcher_anon_id != "sin_id"].groupby("year"):
        table = residuals_by_pitcher(season, {}, "_neutral")
        table = table[table.pitches >= MIN_PITCHES_PER_PERIOD].copy()
        table["location_plus"] = ben_plus(table)
        tables.append(table.assign(year=year).reset_index()[["pitcher_anon_id", "year", "location_plus"]])
    plus = pd.concat(tables)
    return values[["pitcher_anon_id", "year"]].merge(plus, on=["pitcher_anon_id", "year"], how="left").location_plus.to_numpy()


def main():
    pitches, weights = official_pitches(load())
    ben = pd.read_parquet(BEN_CACHE)
    values = plus_scale(pitches)
    values["location_plus"] = ben_location_plus(ben, values)
    values.to_parquet(PITCHER_VALUES_V3, index=False)
    evaluated = pitches[pitches.pitcher_anon_id != "sin_id"]
    holdout = evaluated[evaluated.year == HOLDOUT_SEASON].reset_index(drop=True)
    columns = ["lineal_por_tipo", "lineal_nivel_mar", *VALUES]
    summary = {
        "nota": "Versión 3 (D-039 y D-040): Location+ de Ben, neutral. Quinta mirada a 2026, declarada; no se elige nada con ella.",
        "pitches": len(pitches),
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
