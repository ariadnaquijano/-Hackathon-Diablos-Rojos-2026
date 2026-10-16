"""Genera reportes/etapa_03_target.html a partir de los resúmenes de la etapa 3.

La plantilla (src/plantillas/reporte_etapa_03.html) contiene el diseño; este script solo le inyecta
los datos, así el reporte siempre coincide con la última corrida.

Uso:
    python src/target.py           # primero, el target
    python src/modelos_base.py     # luego, los modelos base
    python src/reporte_target.py
"""

import json
from pathlib import Path

from config import REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "reporte_etapa_03.html"
TARGET_JSON = REPORTS_DIR / "etapa_03_resumen.json"
BASELINES_JSON = REPORTS_DIR / "modelos_base.json"
OUTPUT_HTML = REPORTS_DIR / "etapa_03_target.html"


def main():
    data = {"target": json.loads(TARGET_JSON.read_text()), "base": json.loads(BASELINES_JSON.read_text())}
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
