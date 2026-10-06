"""Rutas y parámetros compartidos por todos los scripts del proyecto."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_PARQUET = ROOT / "data" / "raw" / "stuff_model_df.parquet"
CLEAN_PARQUET = ROOT / "data" / "processed" / "pitches_limpios.parquet"
FEATURES_PARQUET = ROOT / "data" / "processed" / "features.parquet"
REPORTS_DIR = ROOT / "reportes"

# Límites físicos duros: fuera de ellos el valor es imposible, no solo raro (decisión D-008).
PHYSICAL_LIMITS = {
    "RelSpeed": (40, 110),
    "SpinRate": (0, 4000),
    "Extension": (3, 9.5),
    "RelHeight": (1, 8.5),
    "RelSide": (-6, 6),
    "InducedVertBreak": (-35, 35),
    "HorzBreak": (-35, 35),
}
SUSPICIOUS_EXIT_SPEED = 125

# Variables sin las cuales no se puede calcular Stuff+.
KEY_PHYSICS = ["RelSpeed", "SpinRate", "SpinAxis", "InducedVertBreak", "HorzBreak",
               "Extension", "RelHeight", "RelSide"]

HOLDOUT_SEASON = 2026
