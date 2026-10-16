"""Etapa 6: ficha del pitcher para el cuerpo técnico.

Junta en una página local, por pitcher y temporada (300+ pitches):

- Stuff+, Location+ y Pitching+ de la versión 3 (D-040), con su percentil en la liga;
- el arsenal: Stuff+ de cada pitch dentro de su tipo, su uso y sus componentes (D-033);
- el riesgo en el Harp Helú: uso × pérdida promedio de la liga por tipo (D-036), mostrado como
  tercio de la liga porque ordena pero no sirve como cifra exacta, y solo si cubre 60 %+ de sus pitches;
- lecturas con reglas fijas, descritas en docs/06_ficha.md.

La página trae identificadores y datos por pitcher, así que se escribe en data/fichas/, que no se sube
al repo.

Uso:
    python src/modelo_v3.py
    python src/arsenal.py
    python src/pasaporte_altitud.py
    python src/ficha.py
"""

import json
from pathlib import Path

import pandas as pd

from arsenal import ARSENAL_PARQUET
from config import REPORTS_DIR, ROOT
from modelo_v3 import PITCHER_VALUES_V3

TEMPLATE = Path(__file__).parent / "plantillas" / "ficha_pitcher.html"
OUTPUT_HTML = ROOT / "data" / "fichas" / "fichas_pitchers.html"
COMPONENTS = ["p_swing", "p_whiff", "p_foul", "p_strike"]
PLUS = ["stuff_plus", "location_plus", "pitching_plus"]
TERCILES = ["bajo", "medio", "alto"]
# Con menos de esta parte de sus pitches cubierta, el riesgo lo decidiría un solo pitch.
MIN_COVERAGE_PCT = 60


def type_losses() -> dict:
    """Pérdida real promedio por tipo en altura (D-034), con su intervalo."""
    by_type = json.loads((REPORTS_DIR / "etapa_05_pasaporte.json").read_text())["chequeo_por_tipo"]
    return {pitch_type: {"perdida": v["cambio_real_sin_contacto_por_100"], "ic95": v["ic95_cambio_real"]}
            for pitch_type, v in by_type.items()}


def arsenal_table(losses: dict) -> pd.DataFrame:
    arsenal = pd.read_parquet(ARSENAL_PARQUET)
    arsenal["pitch_class"] = arsenal.pitch_class.astype(str)
    keys = ["year", "pitch_class"]
    for component in COMPONENTS:
        arsenal[f"{component}_pct"] = 100 * arsenal.groupby(keys)[component].rank(pct=True)
    arsenal["perdida_altura"] = arsenal.pitch_class.map(lambda t: losses.get(t, {}).get("perdida"))
    return arsenal


def altitude_risk(arsenal: pd.DataFrame) -> pd.DataFrame:
    """Riesgo = uso × pérdida del tipo, sobre los pitches con pérdida conocida.

    La cobertura es el % de todos sus pitches que entra al cálculo: quedan fuera los tipos con menos de
    100 pitches y los que no tienen pérdida medida (cutter, splitter).
    """
    covered = arsenal.dropna(subset=["perdida_altura"])
    risk = (covered.uso_pct * covered.perdida_altura).groupby([covered.pitcher_anon_id, covered.year]).sum()
    covered_use = covered.groupby(["pitcher_anon_id", "year"]).uso_pct.sum()
    table = pd.DataFrame({"riesgo_altura": risk / covered_use, "cobertura_pct": covered_use})
    return table.reset_index()


def pitcher_table(risk: pd.DataFrame) -> pd.DataFrame:
    values = pd.read_parquet(PITCHER_VALUES_V3)
    for plus in PLUS:
        values[f"{plus}_pct"] = 100 * values.groupby("year")[plus].rank(pct=True)
    values = values.merge(risk, on=["pitcher_anon_id", "year"], how="left")
    covered = values[values.cobertura_pct >= MIN_COVERAGE_PCT]
    terciles = covered.groupby("year").riesgo_altura.transform(lambda s: pd.qcut(s, 3, labels=TERCILES))
    values["riesgo_tercio"] = terciles.astype(str).reindex(values.index)
    return values


def records(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    return json.loads(frame[columns].round(2).to_json(orient="records"))


def main():
    losses = type_losses()
    arsenal = arsenal_table(losses)
    pitchers = pitcher_table(altitude_risk(arsenal))
    arsenal = arsenal[arsenal.set_index(["pitcher_anon_id", "year"]).index.isin(
        pitchers.set_index(["pitcher_anon_id", "year"]).index)]
    data = {
        "perdidas_por_tipo": losses,
        "repeticion": json.loads((REPORTS_DIR / "etapa_06_modelo_v3.json").read_text())["repeticion_2024_a_2025"],
        "pitchers": records(pitchers, ["pitcher_anon_id", "year", "pitches", *PLUS, *[f"{p}_pct" for p in PLUS],
                                       "riesgo_altura", "riesgo_tercio", "cobertura_pct"]),
        "arsenal": records(arsenal, ["pitcher_anon_id", "year", "pitch_class", "pitches", "uso_pct", "stuff_plus",
                                     *COMPONENTS, *[f"{c}_pct" for c in COMPONENTS], "perdida_altura"]),
    }
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"{len(pitchers)} fichas escritas en {OUTPUT_HTML.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
