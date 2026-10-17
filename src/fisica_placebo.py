"""Placebo de calibración del exponente k (D-043).

Si k viniera de la calibración del TrackMan de cada estadio y no de la física, el k estimado con
altitud media contra nivel del mar diferiría del estimado con altitud extrema contra nivel del mar.
Se usa exactamente el método de D-016 (src/features.py): mismo pitcher con su mismo pitch en juegos
con distinto aire, y variable instrumental con el aire típico de la categoría y temporada.

También revisa si el patrón "el HB cae más que la IVB" aparece en las dos comparaciones.

Escribe reportes/etapa_06_fisica_placebo.json.

Uso:
    python src/fisica_placebo.py   # requiere src/limpieza.py
"""

import json

import duckdb
import numpy as np

from config import CLEAN_PARQUET, REPORTS_DIR
from features import BOOTSTRAP_SAMPLES, MOVEMENT_COMPONENTS, RANDOM_SEED, create_air_ratio, exponent_games

SUMMARY_JSON = REPORTS_DIR / "etapa_06_fisica_placebo.json"
SUBSETS = {"media_contra_mar": "Medium Altitude", "extrema_contra_mar": "Extreme Altitude"}
EXPRESSIONS = {"liga_total": ("sqrt(InducedVertBreak^2 + hb_arm_side^2)", None),
               **{f"liga_{name}": (f"abs({col})", None) for name, col in MOVEMENT_COMPONENTS.items()},
               **{f"{group}_{name}": (f"abs({col})", group) for group in ("Four-Seam", "Sinker")
                  for name, col in MOVEMENT_COMPONENTS.items()}}


def iv(games) -> float:
    return float((games.y * games.z).sum() / (games.x * games.z).sum())


def draws(games) -> np.ndarray:
    """Bootstrap de pitchers completos de la pendiente instrumental."""
    rng = np.random.default_rng(RANDOM_SEED)
    by_pitcher = games.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(by_pitcher))
    return np.array([iv(games.iloc[np.concatenate([by_pitcher[p] for p in rng.choice(pitchers, len(pitchers))])])
                     for _ in range(BOOTSTRAP_SAMPLES)])


def estimates(category: str) -> dict:
    con = duckdb.connect()
    con.execute(f"""create or replace view clean as select * from '{CLEAN_PARQUET}'
                    where altitude_category in ('No Altitude', '{category}')""")
    create_air_ratio(con)
    result = {}
    for name, (expression, group) in EXPRESSIONS.items():
        games = exponent_games(con, expression, group)
        result[name] = {"k": iv(games), "draws": draws(games), "pitchers": int(games.pitcher_anon_id.nunique())}
    return result


def interval(values) -> list[float]:
    return [round(float(v), 3) for v in np.percentile(values, [2.5, 97.5])]


def main():
    by_subset = {name: estimates(category) for name, category in SUBSETS.items()}
    medium, extreme = by_subset["media_contra_mar"], by_subset["extrema_contra_mar"]
    comparison = {}
    for name in EXPRESSIONS:
        # Bootstraps independientes de cada subconjunto: aproximado, porque hay pitchers en los dos.
        difference = extreme[name]["draws"] - medium[name]["draws"]
        comparison[name] = {
            "k_media": round(medium[name]["k"], 3), "ic95_media": interval(medium[name]["draws"]),
            "pitchers_media": medium[name]["pitchers"],
            "k_extrema": round(extreme[name]["k"], 3), "ic95_extrema": interval(extreme[name]["draws"]),
            "pitchers_extrema": extreme[name]["pitchers"],
            "extrema_menos_media": round(extreme[name]["k"] - medium[name]["k"], 3),
            "ic95_diferencia": interval(difference),
            "consistente": bool(np.percentile(difference, 2.5) <= 0 <= np.percentile(difference, 97.5)),
        }
    hb_minus_ivb = {name: {"hb_menos_ivb": round(subset["liga_hb"]["k"] - subset["liga_ivb"]["k"], 3),
                           "ic95": interval(subset["liga_hb"]["draws"] - subset["liga_ivb"]["draws"])}
                    for name, subset in by_subset.items()}
    summary = {"nota": "Mismo método que D-016, separado por categoría de altitud (D-043).",
               "k_por_comparacion": comparison, "patron_hb_mayor_que_ivb": hb_minus_ivb}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
