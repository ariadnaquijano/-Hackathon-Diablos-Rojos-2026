"""Genera reportes/entregables_1_a_3.html con los entregables 1, 2 y 3.

La plantilla (src/plantillas/reporte_entregables.html) contiene el diseño y el texto; este script solo
le inyecta las cifras de reportes/, así el reporte siempre coincide con la última corrida. No lleva
identificadores de pitchers.

Uso:
    python src/entregable_scores.py
    python src/riesgo_contacto.py
    python src/reporte_entregables.py
"""

import json
from pathlib import Path

from config import REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "reporte_entregables.html"
OUTPUT_HTML = REPORTS_DIR / "entregables_1_a_3.html"


def read(name: str) -> dict:
    return json.loads((REPORTS_DIR / name).read_text())


def count_values() -> dict:
    """Valor de cada conteo a nivel del mar y en altitud extrema (docs/03_target.md, sección 2)."""
    rows = read("etapa_03_resumen.json")["valor_conteos"]
    return {scope: {f"{r['Balls']}-{r['Strikes']}": r["run_value"] for r in rows if r["scope"] == scope}
            for scope in ("No Altitude", "Extreme Altitude")}


def main():
    scores = read("etapa_06_scores.json")
    k = read("etapa_02_resumen.json")["exponente_k"]["por_tipo"]
    data = {
        "deltas": scores["stuff_plus_harp_promedio_por_tipo"],
        "arquetipos": scores["arquetipos"],
        "filas": scores["filas"],
        "contacto": read("etapa_06_riesgo_contacto.json"),
        "k": {t: {"ivb": v["ivb"]["k_usado"], "hb": v["hb"]["k_usado"]} for t, v in k.items()},
        "k_densidad": {t: {c: v[c]["k_densidad"] for c in ("ivb", "hb") if c in v}
                       for t, v in read("etapa_06_fisica_densidad.json")["por_tipo"].items()},
        "pares": {t: v["pares"] for t, v in read("etapa_05_pasaporte.json")["chequeo_por_tipo"].items()},
        "conteos": count_values(),
        "diferencias": read("etapa_06_diferencias_tipo.json")["diferencias"],
    }
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
