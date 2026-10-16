"""Genera reportes/etapa_04_modelo.html a partir del resumen del modelo final.

La plantilla (src/plantillas/reporte_etapa_04.html) contiene el diseño; este script solo le inyecta
los datos, así el reporte siempre coincide con la última corrida.

Uso:
    python src/modelo.py
    python src/reporte_modelo.py
"""

import json
from pathlib import Path

from config import REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "reporte_etapa_04.html"
MODEL_JSON = REPORTS_DIR / "etapa_04_modelo.json"
OUTPUT_HTML = REPORTS_DIR / "etapa_04_modelo.html"


def main():
    data = json.loads(MODEL_JSON.read_text())
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
