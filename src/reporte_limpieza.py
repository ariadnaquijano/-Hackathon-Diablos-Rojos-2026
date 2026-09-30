"""Genera reportes/etapa_01_limpieza.html a partir del resumen de la limpieza.

La plantilla (src/plantillas/reporte_etapa_01.html) contiene el diseño; este script
solo le inyecta los datos, así el reporte siempre coincide con el último `limpieza.py`.

Uso:
    python src/limpieza.py          # primero, genera el resumen
    python src/reporte_limpieza.py
"""

import json
from pathlib import Path

from config import REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "reporte_etapa_01.html"
SUMMARY_JSON = REPORTS_DIR / "etapa_01_resumen.json"
OUTPUT_HTML = REPORTS_DIR / "etapa_01_limpieza.html"

# Qué pasa con el pitch según cada bandera; se muestra como etiqueta en el reporte.
FLAG_ACTIONS = {
    "flag_sin_fisica": "out",
    "flag_fisica_imposible": "out",
    "flag_tipo_pitch_raro": "out",
    "flag_valor_anulado": "nulled",
    "flag_resultado_corregido": "fixed",
    "flag_mano_inferida": "fixed",
    "flag_lado_bateador_inferido": "fixed",
    "flag_sin_altitud": "kept",
    "flag_posible_mal_etiquetado": "kept",
    "flag_pitchcall_indefinido": "kept",
    "flag_outs_invalido": "kept",
    "flag_sin_exit_speed": "kept",
    "flag_exit_speed_sospechosa": "kept",
}


def main():
    summary = json.loads(SUMMARY_JSON.read_text())
    missing = {f["flag"] for f in summary["banderas"]} - FLAG_ACTIONS.keys()
    if missing:
        raise ValueError(f"Banderas sin acción definida en FLAG_ACTIONS: {sorted(missing)}")

    html = (TEMPLATE.read_text()
            .replace("__DATA__", json.dumps(summary, ensure_ascii=False))
            .replace("__ACTIONS__", json.dumps(FLAG_ACTIONS)))
    OUTPUT_HTML.write_text(html)
    print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
