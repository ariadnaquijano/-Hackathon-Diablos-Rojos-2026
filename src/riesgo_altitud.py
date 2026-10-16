"""Etapa 6: riesgo de altitud por arsenal, el número de la ficha del pitcher (D-036).

Riesgo = suma, sobre los pitches del pitcher, de su uso × la pérdida promedio de la liga para ese tipo
de pitch. Se prueba con los pares de D-034 (2024–2025, 50+ pitches por lado), agregados por pitcher.
La pérdida por tipo y la pérdida general se calculan sin el pitcher evaluado.

Regla fijada antes de correr (D-036):

- ordena si la correlación entre riesgo y cambio real es positiva con intervalo fuera de cero;
- sirve como cifra si además su error es menor que dar a todos la pérdida promedio, con intervalo
  fuera de cero.

Escribe reportes/etapa_06_riesgo_altitud.json, sin identificadores.

Uso:
    python src/riesgo_altitud.py   # requiere haber corrido src/pasaporte_altitud.py
"""

import json

import numpy as np
import pandas as pd

from config import REPORTS_DIR
from modelos_base import RANDOM_SEED
from pasaporte_altitud import BOOTSTRAP_SAMPLES, PREDICTIONS_CACHE, interval, load_pitches, pairs_table

SUMMARY_JSON = REPORTS_DIR / "etapa_06_riesgo_altitud.json"


def leave_one_out_type_loss(pairs: pd.DataFrame) -> pd.Series:
    """Pérdida promedio del tipo de pitch en los demás pitchers (promedio simple de los pares)."""
    by_type = pairs.groupby("pitch_class", observed=True).cambio_real
    own = pairs.groupby(["pitch_class", "pitcher_anon_id"], observed=True).cambio_real
    total, count = by_type.transform("sum"), by_type.transform("size")
    own_total, own_count = own.transform("sum"), own.transform("size")
    return (total - own_total) / (count - own_count)


def pitcher_table(pairs: pd.DataFrame) -> pd.DataFrame:
    pairs = pairs.assign(perdida_tipo=leave_one_out_type_loss(pairs), costo=100 * pairs.costo).dropna()
    weighted = pairs[["cambio_real", "perdida_tipo", "costo"]].mul(pairs.n_mar, axis=0)
    table = weighted.groupby(pairs.pitcher_anon_id).sum().div(pairs.groupby("pitcher_anon_id").n_mar.sum(), axis=0)
    table = table.rename(columns={"perdida_tipo": "riesgo_arsenal", "costo": "pasaporte"})
    total, count = pairs.cambio_real.sum(), len(pairs)
    own = pairs.groupby("pitcher_anon_id").cambio_real.agg(["sum", "size"])
    table["constante"] = (total - own["sum"]) / (count - own["size"])
    return table


def evaluate(table: pd.DataFrame) -> dict:
    actual = table.cambio_real.to_numpy()
    rng = np.random.default_rng(RANDOM_SEED)
    samples = [rng.integers(0, len(table), len(table)) for _ in range(BOOTSTRAP_SAMPLES)]

    def correlation(column, idx):
        return np.corrcoef(table[column].to_numpy()[idx], actual[idx])[0, 1]

    def error(column, idx):
        return np.mean((actual[idx] - table[column].to_numpy()[idx]) ** 2)

    result = {}
    for column in ("riesgo_arsenal", "pasaporte"):
        everyone = np.arange(len(table))
        result[column] = {
            "r_con_cambio_real": round(float(correlation(column, everyone)), 4),
            "ic95_r": interval([correlation(column, idx) for idx in samples]),
            "ecm": round(float(error(column, everyone)), 4),
            "ecm_constante": round(float(error("constante", everyone)), 4),
            "ic95_diferencia_ecm_vs_constante": interval([error(column, idx) - error("constante", idx) for idx in samples]),
            "promedio_predicho": round(float(table[column].mean()), 4),
        }
    result["cambio_real_promedio"] = round(float(actual.mean()), 4)
    result["rango_riesgo_arsenal_p10_p90"] = [round(float(v), 3) for v in table.riesgo_arsenal.quantile([0.1, 0.9])]
    return result


def verdict(result: dict) -> str:
    risk = result["riesgo_arsenal"]
    if risk["ic95_r"][0] <= 0:
        return "no ordena"
    return "ordena y sirve como cifra" if risk["ic95_diferencia_ecm_vs_constante"][1] < 0 else "ordena, no como cifra"


def main():
    pitches = load_pitches().merge(pd.read_parquet(PREDICTIONS_CACHE), on="pitch_seq", how="left", validate="one_to_one")
    pitches["costo"] = pitches.stuff_local_extrema - pitches.stuff_local_mar
    table = pitcher_table(pairs_table(pitches))
    result = evaluate(table)
    summary = {"nota": "Pares de D-034 agregados por pitcher (D-036). 2026 no se usa.",
               "pitchers": len(table), **result, "veredicto": verdict(result)}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
