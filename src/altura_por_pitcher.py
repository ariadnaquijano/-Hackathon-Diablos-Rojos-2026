"""Estimado de la pérdida en altura de cada pitch con encogimiento (D-043).

Hoy la pérdida de un pitch en el Harp Helú es la pérdida promedio de su tipo (D-034). Candidato:

    pérdida = promedio del tipo + w · (costo del pasaporte − costo promedio del tipo)

El peso w se ajusta en otros pitchers (5 pliegues por pitcher) y los promedios del tipo también
salen solo de los pitchers de entrenamiento de cada pliegue. Se compara contra el cambio real del xRV
sin contacto del mismo pitcher con el mismo tipo en las dos altitudes (pares de D-034, 2024–2025).
Se adopta solo si el error baja con intervalo fuera de cero.

Escribe reportes/etapa_06_altura_por_pitcher.json.

Uso:
    python src/altura_por_pitcher.py   # requiere src/pasaporte_altitud.py
"""

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from config import REPORTS_DIR
from diferencias_tipo import pairs
from exploracion_etapa_04 import CROSS_FIT_FOLDS
from modelos_base import RANDOM_SEED
from pasaporte_altitud import BOOTSTRAP_SAMPLES, interval

SUMMARY_JSON = REPORTS_DIR / "etapa_06_altura_por_pitcher.json"
# Los tipos con 30+ pares, los mismos que tienen pérdida medida en la ficha (D-034).
MIN_PAIRS_PER_TYPE = 30


def out_of_fold(table: pd.DataFrame) -> pd.DataFrame:
    """Promedio del tipo y estimado con encogimiento, cada pitcher con números de otros pitchers."""
    table = table.assign(costo=100 * table.costo)
    result = pd.DataFrame(index=table.index, columns=["promedio_tipo", "encogido"], dtype=float)
    weights = []
    for fit_rows, other_rows in GroupKFold(CROSS_FIT_FOLDS).split(table, groups=table.pitcher_anon_id):
        train, test = table.iloc[fit_rows], table.iloc[other_rows]
        real_mean = train.groupby("pitch_class").cambio_real.mean()
        cost_mean = train.groupby("pitch_class").costo.mean()
        x = train.costo - train.pitch_class.map(cost_mean)
        y = train.cambio_real - train.pitch_class.map(real_mean)
        weight = float((x * y).sum() / (x ** 2).sum())
        weights.append(weight)
        base = test.pitch_class.map(real_mean)
        result.loc[test.index, "promedio_tipo"] = base
        result.loc[test.index, "encogido"] = base + weight * (test.costo - test.pitch_class.map(cost_mean))
    return table.join(result), weights


def compare(table: pd.DataFrame) -> dict:
    rows = table.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(rows))
    rng = np.random.default_rng(RANDOM_SEED)
    real, base, shrunk = (table[c].to_numpy() for c in ("cambio_real", "promedio_tipo", "encogido"))

    def errors(idx):
        return np.mean((real[idx] - base[idx]) ** 2), np.mean((real[idx] - shrunk[idx]) ** 2)

    everyone = np.arange(len(table))
    base_error, shrunk_error = errors(everyone)
    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        idx = np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))])
        b, s = errors(idx)
        draws.append(s - b)
    low, high = interval(draws)
    return {"ecm_promedio_tipo": round(float(base_error), 4), "ecm_encogido": round(float(shrunk_error), 4),
            "ic95_encogido_menos_promedio": [low, high], "se_adopta": bool(high < 0),
            "r_encogido_con_real_dentro_del_tipo": round(float(np.corrcoef(shrunk - base, real - base)[0, 1]), 3)}


def main():
    table = pairs()
    counts = table.pitch_class.value_counts()
    table = table[table.pitch_class.isin(counts[counts >= MIN_PAIRS_PER_TYPE].index)].reset_index(drop=True)
    table, weights = out_of_fold(table)
    summary = {"nota": "Pares de D-034 (2024–2025); w y promedios del tipo ajustados en otros pitchers (D-043).",
               "pares": len(table), "pitchers": int(table.pitcher_anon_id.nunique()),
               "peso_w_por_pliegue": [round(w, 3) for w in weights], **compare(table)}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
