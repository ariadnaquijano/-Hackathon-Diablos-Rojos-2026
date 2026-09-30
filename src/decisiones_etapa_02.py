"""Evidencia para las tres decisiones abiertas del plan de features (docs/02_plan_features.md).

1. ¿El ángulo de llegada (VAA) o el de salida entran a Stuff+, si dependen de la ubicación?
2. ¿Umbral de sweeper fijo o sacado de los datos, si la altitud cambia el movimiento?
3. ¿Cuántas rectas mínimas por juego para usar una referencia del mismo juego?

Escribe reportes/etapa_02_decisiones.json y, con la plantilla
src/plantillas/decisiones_etapa_02.html, genera reportes/etapa_02_decisiones.html.

Uso:
    python src/decisiones_etapa_02.py
"""

import json
from pathlib import Path

import duckdb

from config import CLEAN_PARQUET, REPORTS_DIR

TEMPLATE = Path(__file__).parent / "plantillas" / "decisiones_etapa_02.html"
OUTPUT_JSON = REPORTS_DIR / "etapa_02_decisiones.json"
OUTPUT_HTML = REPORTS_DIR / "etapa_02_decisiones.html"

FASTBALLS = ("Four-Seam", "Sinker")
SWEEPER_START_THRESHOLD_IN = 12
FASTBALL_THRESHOLDS = [1, 3, 5, 10, 15]
MIN_PITCHES_PER_GROUP = 30


def rows(con, sql: str) -> list[dict]:
    return con.sql(sql).df().round(4).to_dict(orient="records")


def one(con, sql: str) -> dict:
    return rows(con, sql)[0]


def vaa_evidence(con) -> dict:
    """¿Cuánto del ángulo se explica solo por la altura a la que llega el pitch?"""
    return {
        "dependencia_de_ubicacion": rows(con, """
            select pitch_group,
                   regr_r2(VertApprAngle, PlateLocHeight) r2_vaa_por_altura,
                   regr_slope(VertApprAngle, PlateLocHeight) grados_vaa_por_pie,
                   regr_r2(VertRelAngle, PlateLocHeight) r2_salida_por_altura,
                   regr_slope(VertRelAngle, PlateLocHeight) grados_salida_por_pie,
                   count(*) pitches
            from clean where usable_stuff and pitch_group in ('Four-Seam', 'Sinker', 'Slider', 'Curveball', 'Changeup')
            group by 1 order by pitches desc"""),
        # VAA relativo: cuánto más plano o inclinado llega que otro pitch del mismo tipo a esa altura.
        "vaa_relativo": one(con, """
            with fit as (
                select pitch_group, regr_slope(VertApprAngle, PlateLocHeight) b,
                       regr_intercept(VertApprAngle, PlateLocHeight) a
                from clean where usable_stuff group by 1),
            rel as (
                select c.*, VertApprAngle - (f.a + f.b * PlateLocHeight) vaa_rel
                from clean c join fit f using (pitch_group)
                where usable_stuff and pitch_group = 'Four-Seam')
            select corr(vaa_rel, PlateLocHeight) corr_con_altura_llegada,
                   corr(vaa_rel, RelHeight) corr_con_altura_release,
                   corr(vaa_rel, Extension) corr_con_extension,
                   corr(vaa_rel, InducedVertBreak) corr_con_ivb,
                   stddev(vaa_rel) desviacion_grados
            from rel"""),
        "whiff_por_vaa_relativo_rectas_altas": rows(con, """
            with fit as (
                select regr_slope(VertApprAngle, PlateLocHeight) b,
                       regr_intercept(VertApprAngle, PlateLocHeight) a
                from clean where usable_stuff and pitch_group = 'Four-Seam'),
            rel as (
                select c.is_whiff, c.is_swing,
                       ntile(4) over (order by VertApprAngle - (f.a + f.b * PlateLocHeight)) cuartil
                from clean c, fit f
                where usable_stuff and pitch_group = 'Four-Seam' and PlateLocHeight > 3.0)
            select cuartil, sum(is_whiff) / sum(is_swing) whiff_por_swing, count(*) pitches
            from rel group by 1 order by 1"""),
    }


def sweeper_evidence(con) -> dict:
    """Distribución del movimiento horizontal de las sliders por altitud."""
    return {
        "histograma": rows(con, """
            select altitude_category, floor(hb_arm_side) hb_in, count(*) sliders
            from clean
            where usable_stuff and pitch_group = 'Slider'
              and altitude_category in ('No Altitude', 'Extreme Altitude')
              and hb_arm_side between -25 and 10
            group by all order by all"""),
        "pct_mas_alla_del_umbral": rows(con, f"""
            select altitude_category, count(*) sliders,
                   avg((hb_arm_side <= -{SWEEPER_START_THRESHOLD_IN})::int) pct_sweeper_fijo
            from clean where usable_stuff and pitch_group = 'Slider' and altitude_category is not null
            group by 1 order by 1"""),
        "mismo_pitcher": one(con, f"""
            with g as (
                select pitcher_anon_id, altitude_category, median(hb_arm_side) hb
                from clean where usable_stuff and pitch_group = 'Slider'
                  and altitude_category in ('No Altitude', 'Extreme Altitude')
                group by all having count(*) >= {MIN_PITCHES_PER_GROUP})
            select count(*) pitchers,
                   count(*) filter (where s.hb <= -{SWEEPER_START_THRESHOLD_IN}) sweeper_a_nivel_del_mar,
                   count(*) filter (where s.hb <= -{SWEEPER_START_THRESHOLD_IN}
                                      and e.hb > -{SWEEPER_START_THRESHOLD_IN}) dejan_de_serlo_en_altitud,
                   median(e.hb / nullif(s.hb, 0)) razon_hb_altitud_vs_mar
            from g s join g e using (pitcher_anon_id)
            where s.altitude_category = 'No Altitude' and e.altitude_category = 'Extreme Altitude'"""),
    }


def fastball_reference_evidence(con) -> dict:
    fastballs = ", ".join(f"'{p}'" for p in FASTBALLS)
    coverage = ", ".join(f"avg((rectas >= {n})::int) as \"{n}\"" for n in FASTBALL_THRESHOLDS)
    con.execute(f"""
        create or replace table game_fb as
        select pitcher_anon_id, game_anon_id, year, altitude_category,
               count(*) filter (where pitch_group in ({fastballs})) rectas,
               stddev(RelSpeed) filter (where pitch_group in ({fastballs})) sd_velo,
               stddev(InducedVertBreak) filter (where pitch_group in ({fastballs})) sd_ivb,
               median(InducedVertBreak) filter (where pitch_group in ({fastballs})) ivb_juego
        from clean where usable_stuff group by all""")
    return {
        "cobertura_por_umbral": one(con, f"select {coverage} from game_fb"),
        "ruido_dentro_del_juego": one(con, """
            select median(sd_velo) sd_velo_mph, median(sd_ivb) sd_ivb_in
            from game_fb where rectas >= 10"""),
        "error_referencia_de_temporada": rows(con, """
            with season as (
                select pitcher_anon_id, year, median(InducedVertBreak) ivb_temporada
                from clean where usable_stuff and pitch_group in ('Four-Seam', 'Sinker')
                group by all)
            select altitude_category,
                   median(abs(g.ivb_juego - s.ivb_temporada)) error_ivb_in,
                   median(g.ivb_juego - s.ivb_temporada) sesgo_ivb_in,
                   count(*) salidas
            from game_fb g join season s using (pitcher_anon_id, year)
            where g.rectas >= 5 and altitude_category is not null
            group by 1 order by 1"""),
    }


def main():
    con = duckdb.connect()
    con.execute(f"create view clean as select * from '{CLEAN_PARQUET}'")
    evidence = {
        "vaa": vaa_evidence(con),
        "sweeper": sweeper_evidence(con),
        "recta_referencia": fastball_reference_evidence(con),
        "parametros": {"umbral_sweeper_in": SWEEPER_START_THRESHOLD_IN,
                       "umbrales_rectas": FASTBALL_THRESHOLDS},
    }
    OUTPUT_JSON.write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in evidence.items() if k != "sweeper"}, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in evidence["sweeper"].items() if k != "histograma"}, indent=2))

    if TEMPLATE.exists():
        OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(evidence, ensure_ascii=False)))
        print(f"Reporte escrito en {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
