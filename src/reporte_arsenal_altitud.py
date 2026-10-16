"""Genera reportes/etapa_05_arsenal_altitud.html con los resúmenes del arsenal, el pasaporte y la proyección.

La plantilla (src/plantillas/reporte_etapa_05.html) contiene el diseño; este script solo le inyecta
los datos, así el reporte siempre coincide con la última corrida.

Uso:
    python src/arsenal.py
    python src/pasaporte_altitud.py
    python src/proyeccion.py
    python src/reporte_arsenal_altitud.py
"""

import json
from pathlib import Path

from config import REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "reporte_etapa_05.html"
SOURCES = {"arsenal": "etapa_05_arsenal.json", "pasaporte": "etapa_05_pasaporte.json",
           "proyeccion": "etapa_04_proyeccion.json"}
OUTPUT_HTML = REPORTS_DIR / "etapa_05_arsenal_altitud.html"


def main():
    data = {name: json.loads((REPORTS_DIR / file).read_text()) for name, file in SOURCES.items()}
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
