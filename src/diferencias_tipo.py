"""Diferencias de pérdida en altura entre tipos de pitch, con intervalo (D-042).

"La slider casi no pierde" decía que su intervalo tocaba cero, no que perdiera menos que la recta.
Aquí se prueba la diferencia directa con los pares de D-034 (mismo pitcher y mismo tipo en las dos
altitudes, 2024–2025): se remuestrean pitchers completos y en cada repetición se calcula la pérdida
promedio de cada tipo. Se reporta en carreras por 100 pitches y en puntos de Stuff+ de la escala del
arsenal. Una diferencia cuenta si su intervalo excluye el cero.

Escribe reportes/etapa_06_diferencias_tipo.json.

Uso:
    python src/diferencias_tipo.py   # requiere src/pasaporte_altitud.py y src/arsenal.py
"""

import json

import numpy as np
import pandas as pd

from arsenal import ARSENAL_PARQUET
from config import HOLDOUT_SEASON, REPORTS_DIR
from modelos_base import RANDOM_SEED
from pasaporte_altitud import BOOTSTRAP_SAMPLES, PREDICTIONS_CACHE, interval, load_pitches, pairs_table

SUMMARY_JSON = REPORTS_DIR / "etapa_06_diferencias_tipo.json"
COMPARISONS = [("Four-Seam", "Slider"), ("Four-Seam", "Curveball"), ("Sinker", "Slider"), ("Changeup", "Four-Seam")]


def pairs() -> pd.DataFrame:
    pitches = load_pitches().merge(pd.read_parquet(PREDICTIONS_CACHE), on="pitch_seq", how="left", validate="one_to_one")
    pitches["costo"] = pitches.stuff_local_extrema - pitches.stuff_local_mar
    table = pairs_table(pitches)
    table["pitch_class"] = table.pitch_class.astype(str)
    return table


def type_spreads() -> dict:
    """Desviación del Stuff+ en carreras por 100 de cada tipo, la de la escala del arsenal (2024–2025)."""
    arsenal = pd.read_parquet(ARSENAL_PARQUET)
    arsenal = arsenal[arsenal.year < HOLDOUT_SEASON]
    return arsenal.groupby(arsenal.pitch_class.astype(str)).apply(lambda g: g.groupby("year").stuff.std().mean()).to_dict()


def main():
    table = pairs()
    spreads = type_spreads()
    types = sorted({t for pair in COMPARISONS for t in pair})
    rows = table.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(rows))
    rng = np.random.default_rng(RANDOM_SEED)
    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = table.iloc[np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))])]
        draws.append(sample.groupby("pitch_class").cambio_real.mean())
    draws = pd.DataFrame(draws)
    observed = table.groupby("pitch_class").cambio_real.mean()
    result = {}
    for first, second in COMPARISONS:
        runs = draws[first] - draws[second]
        points = -10 * draws[first] / spreads[first] + 10 * draws[second] / spreads[second]
        low, high = interval(runs)
        result[f"{first} menos {second}"] = {
            "carreras_por_100": round(float(observed[first] - observed[second]), 3), "ic95_carreras": [low, high],
            "puntos_stuff_plus": round(float(-10 * observed[first] / spreads[first] + 10 * observed[second] / spreads[second]), 1),
            "ic95_puntos": [round(v, 1) for v in interval(points)],
            "fuera_de_cero": bool(low > 0 or high < 0)}
    summary = {"nota": "Pares de D-034 (2024–2025); remuestreo de pitchers completos (D-042). Positivo = el primero pierde más.",
               "pares_por_tipo": table.pitch_class.value_counts()[types].to_dict(), "diferencias": result}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
