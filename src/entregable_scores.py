"""Entregable 1: Stuff+, Location+ y Pitching+ por pitch, por pitcher y por arsenal, y qué arsenal rinde
más en el Harp Helú (D-038).

Escalas (docs/07_guia_documento_tecnico.md, sección 5):

- **Por pitch:** 100 − 10 × (valor − media) ÷ desviación entre pitches. Stuff+ se compara contra su
  tipo de pitch y temporada; Location+ y Pitching+, contra la temporada. Es el z(score_pitch) de la
  convocatoria, con el signo invertido porque menos carreras es mejor.
- **Por pitcher y por arsenal:** las de la ficha (src/modelo.py y src/arsenal.py).
- **En el Harp Helú:** se resta la pérdida real promedio de su tipo en altitud extrema (D-034),
  convertida a puntos con la misma desviación. Para un pitcher, la de su mezcla (D-036).

Los archivos con identificadores van a data/entregables/, que no se sube al repo. El resumen sin
identificadores va a reportes/etapa_06_scores.json.

Uso:
    python src/entregable_scores.py   # requiere modelo_v3, arsenal, pasaporte y ficha
"""

import json

import duckdb
import numpy as np
import pandas as pd

from arsenal import ARSENAL_PARQUET
from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR, ROOT
from exploracion_etapa_04 import EXTREME, SEA_LEVEL
from ficha import altitude_risk, arsenal_table, harp_arsenal, harp_pitcher, type_losses
from modelo import load
from modelo_v3 import PITCHER_VALUES_V3, official_pitches
from modelos_base import RANDOM_SEED, TARGET
from proyeccion import NO_CONTACT

OUTPUT_DIR = ROOT / "data" / "entregables"
SUMMARY_JSON = REPORTS_DIR / "etapa_06_scores.json"
BOOTSTRAP_SAMPLES = 1000
MIN_PITCHES_PER_ALTITUDE = 200
VALUES = ["stuff", "location", "pitching"]
# Arquetipos de D-038, en el orden en que se asignan.
ARCHETYPES = [
    ("Rompimiento", ["Slider", "Curveball"], 40),
    ("Recta y sinker", ["Four-Seam", "Sinker"], 60),
    ("Cambio o split", ["Changeup", "Splitter"], 25),
]
MIXED = "Mixto"


def pitch_scores(losses: dict) -> pd.DataFrame:
    pitches, _ = official_pitches(load())
    pitches = pitches[pitches.pitcher_anon_id != "sin_id"].copy()
    extra = duckdb.sql(f"select pitch_seq, PitchUID, hit_type, is_ball_in_play from '{MODEL_PARQUET}'").df()
    pitches = pitches.merge(extra, on="pitch_seq", how="left", validate="one_to_one")
    pitches["pitch_class"] = pitches.pitch_class.astype(str)
    by_type = pitches.groupby(["year", "pitch_class"]).stuff
    pitches["stuff_plus"] = 100 - 10 * (pitches.stuff - by_type.transform("mean")) / by_type.transform("std")
    for value in ("location", "pitching"):
        season = pitches.groupby("year")[value]
        pitches[f"{value}_plus"] = 100 - 10 * (pitches[value] - season.transform("mean")) / season.transform("std")
    loss = pitches.pitch_class.map({t: v["perdida"] for t, v in losses.items()}) / 100
    pitches["stuff_plus_harp"] = pitches.stuff_plus - 10 * loss / by_type.transform("std")
    balls_in_play = pitches.outcome == "batazo"
    average_contact = pitches[balls_in_play].groupby(["year", "Balls", "Strikes"])[TARGET].transform("mean")
    pitches[NO_CONTACT] = pitches[TARGET].mask(balls_in_play, average_contact)
    return pitches


def usage_shares(pitches: pd.DataFrame) -> pd.DataFrame:
    counts = pitches.groupby(["pitcher_anon_id", "year", "pitch_class"]).size().unstack(fill_value=0)
    return 100 * counts.div(counts.sum(axis=1), axis=0)


def archetype(shares: pd.DataFrame) -> pd.Series:
    labels = pd.Series(MIXED, index=shares.index)
    assigned = pd.Series(False, index=shares.index)
    for name, types, threshold in ARCHETYPES:
        hit = shares.reindex(columns=types, fill_value=0).sum(axis=1).ge(threshold) & ~assigned
        labels[hit], assigned = name, assigned | hit
    return labels


def pitcher_scores(pitches: pd.DataFrame, losses: dict) -> pd.DataFrame:
    values = pd.read_parquet(PITCHER_VALUES_V3)
    risk = altitude_risk(arsenal_table(losses))
    values = values.merge(risk, on=["pitcher_anon_id", "year"], how="left")
    values["stuff_plus_harp_estimado"] = harp_pitcher(values)
    # Solo bolas en juego: los fouls también traen tipo de batazo y no cuentan para el rolling.
    batted = pitches[(pitches.is_ball_in_play == 1) & pitches.hit_type.notna() & (pitches.hit_type != "Bunt")]
    rolling = batted.groupby(["pitcher_anon_id", "year"]).hit_type.apply(lambda s: 100 * (s == "GroundBall").mean())
    values = values.merge(rolling.rename("rolling_pct").reset_index(), on=["pitcher_anon_id", "year"], how="left")
    labels = archetype(usage_shares(pitches)).rename("arquetipo").reset_index()
    return values.merge(labels, on=["pitcher_anon_id", "year"], how="left")


def arsenal_scores(losses: dict) -> pd.DataFrame:
    arsenal = pd.read_parquet(ARSENAL_PARQUET)
    arsenal["pitch_class"] = arsenal.pitch_class.astype(str)
    arsenal["perdida_altura"] = arsenal.pitch_class.map({t: v["perdida"] for t, v in losses.items()})
    arsenal["stuff_plus_harp"] = harp_arsenal(arsenal)
    arsenal = arsenal.rename(columns={"perdida_altura": "perdida_altura_por_100"})
    return arsenal


def type_deltas(arsenal: pd.DataFrame, losses: dict) -> dict:
    """Delta de Stuff+ de cada tipo en el Harp Helú, en la escala oficial del arsenal, con su intervalo."""
    result = {}
    for pitch_type, loss in losses.items():
        spread = arsenal[arsenal.pitch_class == pitch_type].groupby("year").stuff.std().mean()
        low, high = loss["ic95"]
        result[pitch_type] = {"pitches_de_pitcher": int((arsenal.pitch_class == pitch_type).sum()),
                              "perdida_por_100": loss["perdida"],
                              "delta_stuff_plus": round(float(-10 * loss["perdida"] / spread), 1),
                              "ic95_delta": [round(float(-10 * high / spread), 1), round(float(-10 * low / spread), 1)]}
    return result


def interval(draws) -> list[float]:
    return [round(float(v), 3) for v in np.percentile(draws, [2.5, 97.5])]


def altitude_change(pitches: pd.DataFrame, pitchers: pd.DataFrame) -> pd.DataFrame:
    """Cambio del xRV sin contacto (por 100) entre altitud extrema y nivel del mar, por pitcher y temporada."""
    keys = ["pitcher_anon_id", "year"]
    history = pitches[pitches.year < HOLDOUT_SEASON]
    sides = history[history.altitude_category.isin([EXTREME, SEA_LEVEL])]
    table = sides.groupby([*keys, "altitude_category"], observed=True)[NO_CONTACT].agg(["mean", "size"]).unstack()
    enough = (table[("size", EXTREME)] >= MIN_PITCHES_PER_ALTITUDE) & (table[("size", SEA_LEVEL)] >= MIN_PITCHES_PER_ALTITUDE)
    change = (100 * (table[("mean", EXTREME)] - table[("mean", SEA_LEVEL)]))[enough].rename("cambio").reset_index()
    return change.merge(pitchers[[*keys, "arquetipo"]], on=keys)


def archetype_summary(pitchers: pd.DataFrame, changes: pd.DataFrame) -> dict:
    rng = np.random.default_rng(RANDOM_SEED)
    history = pitchers[pitchers.year < HOLDOUT_SEASON]
    result = {}
    for name in [*(a[0] for a in ARCHETYPES), MIXED]:
        group, change = history[history.arquetipo == name], changes[changes.arquetipo == name].cambio.to_numpy()
        entry = {"pitchers_temporada": len(group),
                 "stuff_plus_mar": round(float(group.stuff_plus.mean()), 1),
                 "stuff_plus_harp_estimado": round(float(group.stuff_plus_harp_estimado.mean()), 1),
                 "pitching_plus": round(float(group.pitching_plus.mean()), 1),
                 "rolling_pct": round(float(group.rolling_pct.mean()), 1),
                 "pitchers_con_las_dos_altitudes": len(change)}
        if len(change) >= 10:
            entry["cambio_real_sin_contacto_por_100"] = round(float(change.mean()), 3)
            entry["ic95_cambio_real"] = interval([rng.choice(change, len(change)).mean() for _ in range(BOOTSTRAP_SAMPLES)])
        result[name] = entry
    breaking = changes[changes.arquetipo == "Rompimiento"].cambio.to_numpy()
    fastball = changes[changes.arquetipo == "Recta y sinker"].cambio.to_numpy()
    draws = [rng.choice(breaking, len(breaking)).mean() - rng.choice(fastball, len(fastball)).mean()
             for _ in range(BOOTSTRAP_SAMPLES)]
    result["rompimiento_menos_recta_y_sinker"] = {"diferencia": round(float(breaking.mean() - fastball.mean()), 3),
                                                  "ic95": interval(draws)}
    return result


def export(frame: pd.DataFrame, name: str, columns: list[str]):
    frame[columns].round(3).to_csv(OUTPUT_DIR / f"{name}.csv", index=False)


def main():
    losses = type_losses()
    pitches = pitch_scores(losses)
    pitchers = pitcher_scores(pitches, losses)
    arsenal = arsenal_scores(losses)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export(pitches, "scores_por_pitch", ["PitchUID", "pitcher_anon_id", "year", "altitude_category", "pitch_class",
                                         "stuff_plus", "location_plus", "pitching_plus", "stuff_plus_harp",
                                         "stuff", "location", "pitching", TARGET])
    export(pitchers, "scores_por_pitcher", ["pitcher_anon_id", "year", "pitches", "stuff_plus", "location_plus",
                                            "pitching_plus", "stuff_plus_harp_estimado", "riesgo_altura",
                                            "cobertura_pct", "rolling_pct", "arquetipo", "p_swing", "p_whiff",
                                            "p_foul", "p_strike"])
    export(arsenal, "scores_por_arsenal", ["pitcher_anon_id", "year", "pitch_class", "pitches", "uso_pct",
                                           "stuff_plus", "stuff_plus_harp", "perdida_altura_por_100", "p_swing",
                                           "p_whiff", "p_foul", "p_strike"])
    by_type = type_deltas(arsenal[arsenal.year < HOLDOUT_SEASON], losses)
    summary = {
        "nota": "Arquetipos de D-038 con 2024–2025; archivos con identificadores en data/entregables/.",
        "filas": {"por_pitch": len(pitches), "por_pitcher": len(pitchers), "por_arsenal": len(arsenal)},
        "arquetipos": archetype_summary(pitchers, altitude_change(pitches, pitchers)),
        "stuff_plus_harp_promedio_por_tipo": by_type,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
