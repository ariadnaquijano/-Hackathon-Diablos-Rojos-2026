"""Evidencia preliminar del acarreo de la pelota bateada en altitud.

Pregunta: con el mismo contacto (misma velocidad de salida y ángulo), ¿la pelota vuela más y se
vuelve jonrón más seguido en altitud? Es la base de la herramienta de "jonrones regalados por el
aire" (docs/retroalimentacion_experto.md).

Se compara una sola ventana de contacto fijada de antemano: la del jonrón típico. Las diferencias
llevan intervalo de 95 % remuestreando pitchers completos.

Escribe reportes/evidencia_acarreo.json.

Uso:
    python src/evidencia_acarreo.py
"""

import json

import duckdb
import numpy as np

from config import RAW_PARQUET, REPORTS_DIR

SUMMARY_JSON = REPORTS_DIR / "evidencia_acarreo.json"
RANDOM_SEED = 2026
BOOTSTRAP_SAMPLES = 1000

# Ventana de contacto de jonrón típico, fijada antes de ver resultados.
EXIT_SPEED_MPH = (98, 104)
LAUNCH_ANGLE_DEG = (24, 34)
SEA_LEVEL, EXTREME = "No Altitude", "Extreme Altitude"


def load_contact(con):
    (ev_low, ev_high), (la_low, la_high) = EXIT_SPEED_MPH, LAUNCH_ANGLE_DEG
    return con.sql(f"""
        select pitcher_anon_id, altitude_category, ExitSpeed, Angle, Distance, home_run::int home_run
        from '{RAW_PARQUET}'
        where ExitSpeed between {ev_low} and {ev_high} and Angle between {la_low} and {la_high}
          and altitude_category is not null""").df()


def describe_by_altitude(contact) -> list[dict]:
    """La velocidad y el ángulo medianos muestran que el contacto es comparable entre grupos."""
    return (contact.groupby("altitude_category")
            .agg(batazos=("home_run", "size"), velocidad_salida_mediana=("ExitSpeed", "median"),
                 angulo_mediano=("Angle", "median"), distancia_mediana=("Distance", "median"),
                 pct_jonron=("home_run", "mean"))
            .round(4).reset_index().to_dict(orient="records"))


def bootstrap_extreme_minus_sea(contact) -> dict:
    """Diferencia altitud extrema − nivel del mar en jonrones y distancia, con IC 95 % por pitcher."""
    rng = np.random.default_rng(RANDOM_SEED)
    groups = contact.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(groups))
    altitude = contact.altitude_category.to_numpy()
    home_run, distance = contact.home_run.to_numpy(), contact.Distance.to_numpy()

    def difference(idx):
        high, sea = idx[altitude[idx] == EXTREME], idx[altitude[idx] == SEA_LEVEL]
        return (home_run[high].mean() - home_run[sea].mean(),
                np.nanmedian(distance[high]) - np.nanmedian(distance[sea]))

    point = difference(np.arange(len(contact)))
    draws = np.array([difference(np.concatenate([groups[p] for p in rng.choice(pitchers, len(pitchers))]))
                      for _ in range(BOOTSTRAP_SAMPLES)])
    low, high = np.percentile(draws, [2.5, 97.5], axis=0)
    return {"pct_jonron": {"diferencia": round(float(point[0]), 4), "ic95": [round(float(low[0]), 4), round(float(high[0]), 4)]},
            "distancia_pies": {"diferencia": round(float(point[1]), 1), "ic95": [round(float(low[1]), 1), round(float(high[1]), 1)]}}


def main():
    contact = load_contact(duckdb.connect())
    summary = {
        "ventana_contacto": {"velocidad_salida_mph": EXIT_SPEED_MPH, "angulo_grados": LAUNCH_ANGLE_DEG},
        "por_altitud": describe_by_altitude(contact),
        "extrema_menos_mar": bootstrap_extreme_minus_sea(contact),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
