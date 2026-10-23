# Location+ original del equipo (PR #2)

Primera versión del Location+, tal como la entregó el equipo: una red neuronal (`location_plus.py`) y su
variante con XGBoost (`location_plus_xgb.py`), con la guía `GUIA_MODELO.md`. Se conserva como
referencia; la versión oficial es `src/location_ben.py`, que usa el mismo diseño con los pliegues del
proyecto (docs/06_location_ben.md, D-039 y D-040).

El run value que usan los dos está en `src/run_value.py`. Para correrlos:

    PYTHONPATH=src python location_plus_original/location_plus_xgb.py

Escriben sus resultados en la carpeta actual; esos archivos traen datos por pitcher y no se suben.
