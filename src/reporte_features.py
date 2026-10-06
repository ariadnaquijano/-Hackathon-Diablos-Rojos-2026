"""Genera reportes/etapa_02_features.html a partir del resumen de la etapa 2.

La plantilla (src/plantillas/reporte_etapa_02.html) contiene el diseño; este script solo le
inyecta los datos, así el reporte siempre coincide con el último `features.py`.

Uso:
    python src/features.py          # primero, genera el resumen
    python src/reporte_features.py
"""

import json
from pathlib import Path

from config import REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "reporte_etapa_02.html"
SUMMARY_JSON = REPORTS_DIR / "etapa_02_resumen.json"
OUTPUT_HTML = REPORTS_DIR / "etapa_02_features.html"


def main():
    summary = json.loads(SUMMARY_JSON.read_text())
    data = json.dumps(summary, ensure_ascii=False)
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", data))
    print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
