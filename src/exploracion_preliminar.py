"""Exploración preliminar: valida con datos las ideas del enfoque antes de limpiar.

Reproduce todas las cifras citadas en docs/00_contexto_y_approach.md.
Trabaja directo sobre el parquet crudo (sin limpieza), por eso los números
son indicativos y se recalcularán sobre el dataset limpio.

Uso:
    python src/exploracion_preliminar.py
"""

import duckdb

from config import RAW_PARQUET

# Mínimo de pitches por pitcher-tipo-altitud para comparar al mismo pitcher contra sí mismo.
MIN_PITCHES_PER_GROUP = 30

# Umbral para considerar que un pitcher "vive" en altitud extrema.
RESIDENT_SHARE = 0.5
MIN_PITCHES_PER_PITCHER = 300


def show(con: duckdb.DuckDBPyConnection, title: str, sql: str) -> None:
    print(f"\n## {title}\n")
    print(con.sql(sql).df().round(3).to_string(index=False))


def dataset_overview(con):
    show(con, "Tamaño del dataset", """
        select count(*) pitches,
               count(distinct pitcher_anon_id) pitchers,
               count(distinct game_anon_id) juegos,
               count(distinct batter_anon_id) bateadores
        from raw""")
    show(con, "Pitches por temporada y altitud", """
        select year, altitude_category, count(*) pitches, count(distinct game_anon_id) juegos
        from raw group by all order by all""")


def outcomes_by_altitude(con):
    show(con, "Resultados por altitud", """
        select altitude_category,
               sum(is_whiff) / sum(is_swing) whiff_por_swing,
               sum(home_run) / sum(is_ball_in_play) hr_por_bip,
               sum(is_hit) / sum(is_ball_in_play) hit_por_bip,
               sum(RunsScored) / count(distinct game_anon_id) carreras_por_juego
        from raw where altitude_category is not null
        group by 1 order by 1""")


def within_pitcher_movement_change(con):
    """Mismo pitcher, mismo tipo de pitch: altitud extrema contra nivel del mar."""
    show(con, "Cambio de movimiento dentro del mismo pitcher (Extreme - No Altitude)", f"""
        with by_group as (
            select pitcher_anon_id pitcher, AutoPitchType pitch_type, altitude_category altitude,
                   avg(RelSpeed) velo, avg(InducedVertBreak) ivb, avg(abs(HorzBreak)) hb,
                   avg(PlateLocHeight) plate_height
            from raw where altitude_category is not null
            group by all having count(*) >= {MIN_PITCHES_PER_GROUP}
        )
        select sea.pitch_type, count(*) pares,
               median(alt.ivb - sea.ivb) delta_ivb_in,
               median(alt.hb - sea.hb) delta_hb_in,
               median((alt.ivb - sea.ivb) / nullif(sea.ivb, 0)) pct_ivb,
               median((alt.hb - sea.hb) / nullif(sea.hb, 0)) pct_hb,
               median(alt.velo - sea.velo) delta_velo_mph,
               median(alt.plate_height - sea.plate_height) * 12 delta_altura_llegada_in
        from by_group sea join by_group alt
          on sea.pitcher = alt.pitcher and sea.pitch_type = alt.pitch_type
         and sea.altitude = 'No Altitude' and alt.altitude = 'Extreme Altitude'
        group by 1 having count(*) >= 20 order by pares desc""")


def drag_proxy_by_altitude(con):
    """Arrastre por juego: desaceleración a lo largo de la velocidad / v², sin gravedad.

    Es proporcional a densidad del aire × coeficiente de arrastre, así que debe
    bajar con la altitud si Trackman mide bien la física.
    """
    show(con, "Proxy de arrastre por juego (four-seams)", """
        with per_game as (
            select game_anon_id, altitude_category,
                   median((vx0*ax0 + vy0*ay0 + vz0*(az0 + 32.174))
                          / -(vx0*vx0 + vy0*vy0 + vz0*vz0)) drag_proxy
            from raw where AutoPitchType = 'Four-Seam' and altitude_category is not null
            group by all having count(*) >= 20
        )
        select altitude_category, count(*) juegos,
               avg(drag_proxy) promedio, stddev(drag_proxy) desviacion
        from per_game group by 1 order by 1""")


def whiff_by_magnus_dependence(con):
    """Terciles de "eficiencia" (movimiento por unidad de spin/velo) dentro de cada altitud."""
    show(con, "Whiff/swing por tercil de dependencia del Magnus", """
        with scored as (
            select *, ntile(3) over (
                       partition by AutoPitchType, altitude_category
                       order by sqrt(InducedVertBreak^2 + HorzBreak^2) / (SpinRate / RelSpeed)
                   ) tercil_magnus
            from raw
            where AutoPitchType in ('Four-Seam', 'Slider', 'Curveball')
              and SpinRate > 0 and altitude_category is not null
        )
        select AutoPitchType, tercil_magnus, altitude_category,
               sum(is_whiff) / sum(is_swing) whiff_por_swing, count(*) pitches
        from scored group by all order by all""")


def resident_vs_visitor(con):
    show(con, "Residentes de altitud contra visitantes, jugando en altitud extrema", f"""
        with share as (
            select pitcher_anon_id, avg((altitude_category = 'Extreme Altitude')::int) extreme_share
            from raw where altitude_category is not null
            group by 1 having count(*) >= {MIN_PITCHES_PER_PITCHER}
        )
        select case when extreme_share >= {RESIDENT_SHARE} then 'residente' else 'visitante' end grupo,
               AutoPitchType, count(*) pitches,
               sum(is_whiff) / sum(is_swing) whiff_por_swing,
               sum(home_run) / sum(is_ball_in_play) hr_por_bip
        from raw join share using (pitcher_anon_id)
        where altitude_category = 'Extreme Altitude'
          and AutoPitchType in ('Four-Seam', 'Slider', 'Curveball', 'Changeup')
        group by all order by AutoPitchType, grupo""")


def main():
    con = duckdb.connect()
    con.execute(f"create view raw as select * from '{RAW_PARQUET}'")
    dataset_overview(con)
    outcomes_by_altitude(con)
    within_pitcher_movement_change(con)
    drag_proxy_by_altitude(con)
    whiff_by_magnus_dependence(con)
    resident_vs_visitor(con)


if __name__ == "__main__":
    main()
