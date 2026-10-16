"""Entregable 2: qué características físicas hacen que un pitch pierda menos en el Harp Helú (descriptivo).

Usa los pares de D-034: el mismo pitcher con el mismo tipo de pitch en altitud extrema y a nivel del mar
(2024–2025, 50+ pitches por lado). Para cada tipo con 50+ pares, correlaciona las características del
pitch a nivel del mar con:

- el costo que predice el pasaporte (lo que el modelo cree que importa), y
- el cambio real del xRV sin contacto (lo que pasó; ruidoso).

Una característica cuenta como evidencia si las dos correlaciones apuntan al mismo lado y la del cambio
real tiene intervalo fuera de cero. Es descriptivo: no elige modelo ni toca 2026.

Escribe reportes/etapa_06_perfil_ideal.json.

Uso:
    python src/perfil_ideal.py   # requiere src/pasaporte_altitud.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import MODEL_PARQUET, REPORTS_DIR
from exploracion_etapa_04 import SEA_LEVEL
from modelos_base import RANDOM_SEED
from pasaporte_altitud import BOOTSTRAP_SAMPLES, KEYS, PREDICTIONS_CACHE, interval, load_pitches, pairs_table

SUMMARY_JSON = REPORTS_DIR / "etapa_06_perfil_ideal.json"
MIN_PAIRS = 50
FEATURES = {
    "RelSpeed": "velocidad",
    "SpinRate": "spin",
    "InducedVertBreak": "IVB",
    "hb_arm_side": "HB hacia el brazo",
    "Extension": "extensión",
    "magnus_dependence": "dependencia del efecto Magnus",
    "vaa_rel": "ángulo vertical de llegada relativo",
    "velo_diff_vs_fb": "diferencia de velocidad contra la recta",
}


def pairs_with_features() -> pd.DataFrame:
    pitches = load_pitches().merge(pd.read_parquet(PREDICTIONS_CACHE), on="pitch_seq", how="left", validate="one_to_one")
    pitches["costo"] = pitches.stuff_local_extrema - pitches.stuff_local_mar
    extra = duckdb.sql(f"select pitch_seq, magnus_dependence from '{MODEL_PARQUET}'").df()
    pitches = pitches.merge(extra, on="pitch_seq", how="left", validate="one_to_one")
    sea = pitches[pitches.altitude_category == SEA_LEVEL]
    features = sea.groupby(KEYS, observed=True)[list(FEATURES)].mean().reset_index()
    pairs = pairs_table(pitches).merge(features, on=KEYS, how="left")
    pairs["costo"] *= 100
    return pairs


def correlations(group: pd.DataFrame) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)
    rows = group.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(rows))
    samples = [np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))]) for _ in range(BOOTSTRAP_SAMPLES)]
    result = {}
    for column, label in FEATURES.items():
        if group[column].std() == 0 or group[column].isna().all():
            continue
        x, cost, real = group[column].to_numpy(), group.costo.to_numpy(), group.cambio_real.to_numpy()
        draws = [spearmanr(x[idx], real[idx]).statistic for idx in samples]
        r_cost, r_real = spearmanr(x, cost).statistic, spearmanr(x, real).statistic
        low, high = interval(draws)
        result[label] = {"r_con_costo_predicho": round(float(r_cost), 3), "r_con_cambio_real": round(float(r_real), 3),
                         "ic95_r_cambio_real": [low, high],
                         "evidencia": bool(np.sign(r_cost) == np.sign(r_real) and (low > 0 or high < 0))}
    return result


def main():
    pairs = pairs_with_features()
    summary = {"nota": "Pares de D-034 (2024–2025). Correlación de Spearman; positiva = más pérdida en altura.",
               "por_tipo": {}}
    for pitch_type, group in pairs.groupby("pitch_class", observed=True):
        if len(group) < MIN_PAIRS:
            continue
        summary["por_tipo"][str(pitch_type)] = {"pares": len(group), "correlaciones": correlations(group.reset_index(drop=True))}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
