"""Riesgo de contacto duro y jonrón en altitud (entregable 3, descriptivo).

Con 2024–2025, compara los batazos en altitud extrema contra nivel del mar:

1. Liga: jonrones por fly, jonrones por batazo, contacto duro (95+ mph), rolling y carreras por
   batazo, con la diferencia y su intervalo (remuestreo de pitchers).
2. Cuánto vale cada tipo de batazo en cada altitud: cuánto más cuesta un fly en la CDMX (H3).
3. Por tipo de pitch, el mismo pitcher con el mismo pitch en las dos altitudes (20+ batazos por lado).

Es descriptivo: no elige modelo ni toca 2026. Escribe reportes/etapa_06_riesgo_contacto.json.

Uso:
    python src/riesgo_contacto.py
"""

import json

import duckdb
import numpy as np
import pandas as pd

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR
from exploracion_etapa_04 import EXTREME, SEA_LEVEL
from modelos_base import RANDOM_SEED

SUMMARY_JSON = REPORTS_DIR / "etapa_06_riesgo_contacto.json"
BOOTSTRAP_SAMPLES = 1000
HARD_HIT_MPH = 95
MIN_BATTED_PER_SIDE = 20
# Con menos pitchers por tipo, el intervalo depende de dos o tres casos y no se reporta.
MIN_PITCHERS_PER_TYPE = 20
PITCH_TYPES = ["Four-Seam", "Sinker", "Cutter", "Slider", "Curveball", "Changeup"]
# Cada métrica: columna por batazo y a qué batazos aplica.
METRICS = {
    "jonron_por_fly_pct": ("home_run", lambda f: f.hit_type == "FlyBall"),
    "jonron_por_batazo_pct": ("home_run", lambda f: f.hit_type.notna()),
    "contacto_duro_pct": ("hard_hit", lambda f: f.ExitSpeed.notna()),
    "rolling_pct": ("groundball", lambda f: f.hit_type.notna()),
    "fly_pct": ("flyball", lambda f: f.hit_type.notna()),
    "carreras_por_100_batazos": ("runs", lambda f: f.hit_type.notna()),
}


def load() -> pd.DataFrame:
    batted = duckdb.sql(f"""
        select pitcher_anon_id, pitch_class, altitude_category, hit_type, ExitSpeed, home_run::int as home_run,
               rv_real_neutral as runs
        from '{MODEL_PARQUET}'
        where is_ball_in_play = 1 and year < {HOLDOUT_SEASON} and hit_type <> 'Bunt'
          and altitude_category in ('{EXTREME}', '{SEA_LEVEL}') and pitcher_anon_id is not null
          and rv_real_neutral is not null and not coalesce(flag_exit_speed_sospechosa, false)""").df()
    batted["pitch_class"] = batted.pitch_class.astype(str)
    batted["hard_hit"] = (batted.ExitSpeed >= HARD_HIT_MPH).astype(float).where(batted.ExitSpeed.notna())
    batted["groundball"] = (batted.hit_type == "GroundBall").astype(float)
    batted["flyball"] = (batted.hit_type == "FlyBall").astype(float)
    return batted


def interval(draws) -> list[float]:
    return [round(float(v), 3) for v in np.percentile(draws, [2.5, 97.5])]


def league(batted: pd.DataFrame) -> dict:
    """Tasa en cada altitud y diferencia extrema − mar, remuestreando pitchers completos."""
    rng = np.random.default_rng(RANDOM_SEED)
    result = {}
    for name, (column, rows) in METRICS.items():
        subset = batted[rows(batted)]
        sums = subset.groupby(["pitcher_anon_id", "altitude_category"])[column].agg(["sum", "count"]).unstack(fill_value=0)
        pitchers = sums.index.to_numpy()

        def gap(table):
            rate = 100 * table["sum"].sum() / table["count"].sum()
            return rate[EXTREME] - rate[SEA_LEVEL], rate

        difference, rate = gap(sums)
        draws = [gap(sums.loc[rng.choice(pitchers, len(pitchers))])[0] for _ in range(BOOTSTRAP_SAMPLES)]
        result[name] = {"altitud_extrema": round(float(rate[EXTREME]), 3), "nivel_del_mar": round(float(rate[SEA_LEVEL]), 3),
                        "diferencia": round(float(difference), 3), "ic95_diferencia": interval(draws)}
    return result


def value_by_hit_type(batted: pd.DataFrame) -> dict:
    table = batted.groupby(["hit_type", "altitude_category"]).runs.agg(["mean", "size"]).unstack()
    return {hit_type: {"carreras_extrema": round(float(row[("mean", EXTREME)]), 4),
                       "carreras_mar": round(float(row[("mean", SEA_LEVEL)]), 4),
                       "diferencia": round(float(row[("mean", EXTREME)] - row[("mean", SEA_LEVEL)]), 4),
                       "batazos_extrema": int(row[("size", EXTREME)]), "batazos_mar": int(row[("size", SEA_LEVEL)])}
            for hit_type, row in table.iterrows()}


def by_pitch_type(batted: pd.DataFrame) -> dict:
    """Mismo pitcher y mismo tipo de pitch en las dos altitudes: cambio promedio de cada métrica."""
    rng = np.random.default_rng(RANDOM_SEED)
    result = {}
    for pitch_type in PITCH_TYPES:
        subset = batted[batted.pitch_class == pitch_type]
        means = subset.groupby(["pitcher_anon_id", "altitude_category"])[["home_run", "hard_hit", "flyball", "runs"]].mean().unstack()
        counts = subset.groupby(["pitcher_anon_id", "altitude_category"]).size().unstack(fill_value=0)
        eligible = counts[(counts[EXTREME] >= MIN_BATTED_PER_SIDE) & (counts[SEA_LEVEL] >= MIN_BATTED_PER_SIDE)].index
        if len(eligible) < MIN_PITCHERS_PER_TYPE:
            result[pitch_type] = {"pitchers": len(eligible), "nota": "muestra insuficiente"}
            continue
        changes = 100 * (means.xs(EXTREME, axis=1, level=1) - means.xs(SEA_LEVEL, axis=1, level=1)).loc[eligible]
        entry = {"pitchers": len(eligible)}
        for column, label in (("home_run", "jonron_por_batazo_pp"), ("hard_hit", "contacto_duro_pp"),
                              ("flyball", "fly_pp"), ("runs", "carreras_por_100_batazos")):
            values = changes[column].dropna().to_numpy()
            draws = [rng.choice(values, len(values)).mean() for _ in range(BOOTSTRAP_SAMPLES)]
            entry[label] = {"cambio": round(float(values.mean()), 3), "ic95": interval(draws)}
        entry["fly_pct_liga_mar"] = round(float(100 * subset[subset.altitude_category == SEA_LEVEL].flyball.mean()), 2)
        result[pitch_type] = entry
    return result


def main():
    batted = load()
    summary = {
        "nota": "2024–2025, batazos sin toques; descriptivo, no elige modelo.",
        "batazos": {EXTREME: int((batted.altitude_category == EXTREME).sum()),
                    SEA_LEVEL: int((batted.altitude_category == SEA_LEVEL).sum())},
        "liga": league(batted),
        "valor_por_tipo_de_batazo": value_by_hit_type(batted),
        "por_tipo_de_pitch_mismo_pitcher": by_pitch_type(batted),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
