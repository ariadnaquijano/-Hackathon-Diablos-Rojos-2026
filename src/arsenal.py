"""Etapa 5: Stuff+ por tipo de pitch, el arsenal de cada pitcher (D-033).

Cada pitch de cada pitcher (100+ pitches en la temporada) recibe su Stuff+ en escala 100 dentro de su
tipo: una slider se compara contra las sliders de la liga. También sus componentes: P(swing),
P(whiff | swing), P(foul | contacto) y P(strike cantado | toma).

Prueba con los pares 2024 → 2025 del mismo pitcher y tipo de pitch, fijada antes de correr:

1. ¿Cuánto se repite el Stuff+ de un pitch de un año a otro, comparado con su resultado?
2. ¿El Stuff+ de 2024 predice el xRV sin contacto de ese pitch en 2025 (D-032), con intervalo fuera de
   cero? ¿Mejor que la historia de ese pitch?

Las predicciones de 2024–2025 vienen de modelos que no vieron al pitcher (src/modelo.py). 2026 solo se
usa para escribir la tabla del arsenal, no para evaluar.

Escribe reportes/etapa_05_arsenal.json, sin identificadores. La tabla del arsenal va a
data/processed/arsenal.parquet, que no se sube al repo.

Uso:
    python src/arsenal.py   # requiere haber corrido src/modelo.py
"""

import json

import numpy as np
import pandas as pd

from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from modelos_base import RANDOM_SEED, TARGET
from proyeccion import NO_CONTACT, load_pitches
from stuff_componentes import COMPONENTS

SUMMARY_JSON = REPORTS_DIR / "etapa_05_arsenal.json"
ARSENAL_PARQUET = ROOT / "data" / "processed" / "arsenal.parquet"
MIN_PITCHES_PER_PITCH_TYPE = 100
BOOTSTRAP_SAMPLES = 1000
VALUES = [TARGET, NO_CONTACT, "stuff", *COMPONENTS]
FIRST, SECOND = HOLDOUT_SEASON - 2, HOLDOUT_SEASON - 1


def arsenal(pitches: pd.DataFrame) -> pd.DataFrame:
    """Cada pitcher y tipo de pitch por temporada, con su Stuff+ dentro del tipo."""
    keys = ["year", "pitch_class"]
    centered = pitches[["pitcher_anon_id", *keys]].copy()
    centered[VALUES] = pitches[VALUES] - pitches.groupby(keys, observed=True)[VALUES].transform("mean")
    table = (centered.groupby(["pitcher_anon_id", *keys], observed=True)
             .agg(pitches=(TARGET, "size"), **{c: (c, "mean") for c in VALUES}).reset_index())
    table[VALUES] *= 100
    total = table.groupby(["pitcher_anon_id", "year"]).pitches.transform("sum")
    table["uso_pct"] = 100 * table.pitches / total
    table = table[table.pitches >= MIN_PITCHES_PER_PITCH_TYPE].copy()
    spread = table.groupby(keys, observed=True).stuff.transform("std")
    table["stuff_plus"] = 100 - 10 * table.stuff / spread
    return table


def interval(draws) -> list[float]:
    return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]


def year_to_year(table: pd.DataFrame) -> dict:
    """Mismo pitcher y tipo de pitch en 2024 y 2025, con IC remuestreando pitchers completos."""
    keys = ["pitcher_anon_id", "pitch_class"]
    pairs = (table[table.year == FIRST].set_index(keys)
             .join(table[table.year == SECOND].set_index(keys), lsuffix="_antes", rsuffix="_despues", how="inner")
             .reset_index())
    rows = pairs.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(rows))
    rng = np.random.default_rng(RANDOM_SEED)
    samples = [np.concatenate([rows[p] for p in rng.choice(pitchers, len(pitchers))]) for _ in range(BOOTSTRAP_SAMPLES)]

    def r(a, b, idx):
        return np.corrcoef(pairs[a].to_numpy()[idx], pairs[b].to_numpy()[idx])[0, 1]

    def described(a, b, reference=None):
        everyone = np.arange(len(pairs))
        result = {"r": round(float(r(a, b, everyone)), 4), "ic95": interval([r(a, b, i) for i in samples])}
        if reference:
            result["ic95_diferencia_vs_historia"] = interval([r(a, b, i) - r(*reference, i) for i in samples])
        return result

    outcome = f"{NO_CONTACT}_despues"
    history = (f"{NO_CONTACT}_antes", outcome)
    return {
        "pares_pitcher_tipo": len(pairs), "pitchers": len(pitchers),
        "repeticion": {c: described(f"{c}_antes", f"{c}_despues") for c in VALUES},
        "predice_xrv_sin_contacto_2025": {
            "historia_sin_contacto": described(*history),
            "stuff": described("stuff_antes", outcome, history),
        },
        "predice_xrv_total_2025": {
            "historia_total": described(f"{TARGET}_antes", f"{TARGET}_despues"),
            "stuff": described("stuff_antes", f"{TARGET}_despues", (f"{TARGET}_antes", f"{TARGET}_despues")),
        },
        "por_tipo": {str(t): {"pares": len(g), "r_repeticion_stuff": round(float(g.stuff_antes.corr(g.stuff_despues)), 4),
                              "r_stuff_con_sin_contacto_2025": round(float(g.stuff_antes.corr(g[outcome])), 4)}
                     for t, g in pairs.groupby("pitch_class", observed=True) if len(g) >= 30},
    }


def describe(table: pd.DataFrame) -> dict:
    """Cuántos pitches entran por tipo y temporada, y la relación de Stuff+ con sus componentes."""
    result = {}
    for year, season in table.groupby("year"):
        result[str(year)] = {
            "pitches_de_pitcher": len(season),
            "por_tipo": season.groupby("pitch_class", observed=True).size().astype(int).to_dict(),
            "r_stuff_plus_con_componentes": {c: round(float(-season.stuff.corr(season[c])), 4) for c in COMPONENTS},
        }
    return result


def main():
    pitches = load_pitches()
    table = arsenal(pitches)
    table.to_parquet(ARSENAL_PARQUET, index=False)
    summary = {
        "nota": "Evaluación con pares 2024 → 2025 (D-033). 2026 solo entra a la tabla del arsenal.",
        "minimo_pitches_por_tipo": MIN_PITCHES_PER_PITCH_TYPE,
        "descripcion": describe(table),
        "entre_temporadas": year_to_year(table[table.year < HOLDOUT_SEASON]),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
