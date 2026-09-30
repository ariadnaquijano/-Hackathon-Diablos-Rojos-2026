"""Exploración para la etapa 2: valida las ideas de docs/02_plan_features.md antes de construirlas.

Preguntas que responde:
1. ¿El proxy de arrastre por juego mide aire real o calibración de Trackman?
2. ¿Hay orden de pitches dentro del juego (para variables de secuencia)?
3. ¿La altitud cambia la forma lo suficiente como para confundir una clasificación por forma?
4. ¿Qué recta usar como referencia para las diferencias de arsenal?

Uso:
    python src/exploracion_etapa_02.py
"""

import duckdb

from config import CLEAN_PARQUET

MIN_FASTBALLS_PER_GAME = 15
GRAVITY_FT_S2 = 32.174


def show(con: duckdb.DuckDBPyConnection, title: str, sql: str) -> None:
    print(f"\n## {title}\n")
    print(con.sql(sql).df().round(4).to_string(index=False))


def create_game_drag(con):
    """Proxy de arrastre = desaceleración a lo largo de la trayectoria / v², sin gravedad."""
    con.execute(f"""
        create or replace table pitch_drag as
        select *, (vx0*ax0 + vy0*ay0 + vz0*(az0 + {GRAVITY_FT_S2}))
                  / -(vx0*vx0 + vy0*vy0 + vz0*vz0) as drag_proxy
        from clean where usable_stuff and altitude_category is not null""")
    con.execute(f"""
        create or replace table game_drag as
        select game_anon_id, altitude_category, year, pitch_group, median(drag_proxy) drag, count(*) n
        from pitch_drag where pitch_group in ('Four-Seam', 'Sinker')
        group by all having count(*) >= {MIN_FASTBALLS_PER_GAME}""")


def drag_is_physical(con):
    show(con, "Four-Seam vs Sinker en el mismo juego (si es aire real, deben coincidir)", """
        select corr(f.drag, s.drag) correlacion, count(*) juegos,
               median(f.drag - s.drag) diferencia_mediana
        from game_drag f join game_drag s using (game_anon_id)
        where f.pitch_group = 'Four-Seam' and s.pitch_group = 'Sinker'""")
    show(con, "Arrastre vs movimiento en el mismo juego (menos aire = menos arrastre y menos IVB)", """
        with pitcher_ref as (
            select pitcher_anon_id, median(InducedVertBreak) ivb_ref
            from pitch_drag where pitch_group = 'Four-Seam' group by 1),
        game_ivb as (
            select game_anon_id, median(InducedVertBreak - ivb_ref) ivb_vs_own_normal
            from pitch_drag join pitcher_ref using (pitcher_anon_id)
            where pitch_group = 'Four-Seam' group by 1 having count(*) >= 15)
        select coalesce(altitude_category, 'Todas') altitude_category, corr(drag, ivb_vs_own_normal) correlacion_dentro_de_altitud,
               count(*) juegos
        from game_drag join game_ivb using (game_anon_id)
        where pitch_group = 'Four-Seam' group by rollup (altitude_category) order by 1""")
    show(con, "Distribución del arrastre por altitud y temporada (deriva de Trackman)", """
        select altitude_category, year, count(*) juegos,
               quantile_cont(drag, 0.1) p10, median(drag) p50, quantile_cont(drag, 0.9) p90
        from game_drag where pitch_group = 'Four-Seam' group by all order by all""")
    show(con, "Razón de arrastre contra nivel del mar (≈ razón de densidad del aire)", """
        with m as (select altitude_category, median(drag) drag from game_drag
                   where pitch_group = 'Four-Seam' group by 1)
        select altitude_category, drag / (select drag from m where altitude_category = 'No Altitude') razon
        from m order by 1""")


def pitch_order_available(con):
    show(con, "¿Hay columnas de orden de pitch?", """
        select column_name from (describe clean)
        where regexp_matches(lower(column_name), 'pitchno|pitch_no|time|order|sequence|atbat|pa_id')""")


def altitude_shifts_shape(con):
    """Si una slider en altitud se parece a otra cosa a nivel del mar, clasificar por forma sin
    ajustar por altitud mezclaría tipos de pitch."""
    show(con, "Forma mediana por grupo y altitud (mismo pitcher en ambas, ≥ 30 pitches)", """
        with g as (
            select pitcher_anon_id, pitch_group, altitude_category,
                   median(RelSpeed) velo, median(InducedVertBreak) ivb, median(hb_arm_side) hb
            from clean where usable_stuff and altitude_category in ('No Altitude', 'Extreme Altitude')
            group by all having count(*) >= 30)
        select s.pitch_group, count(*) pares,
               median(s.velo) velo_mar, median(s.ivb) ivb_mar, median(s.hb) hb_mar,
               median(e.ivb) ivb_altitud, median(e.hb) hb_altitud
        from g s join g e using (pitcher_anon_id, pitch_group)
        where s.altitude_category = 'No Altitude' and e.altitude_category = 'Extreme Altitude'
        group by 1 order by pares desc""")
    show(con, "Sliders: cuántas parecen sweeper (≥ 12 in al lado del guante) según la altitud", """
        select altitude_category, count(*) sliders,
               avg((hb_arm_side <= -12)::int) pct_parece_sweeper
        from clean where usable_stuff and pitch_group = 'Slider' and altitude_category is not null
        group by 1 order by 1""")


def primary_fastball(con):
    show(con, "Recta principal: ¿cuál es el pitch rápido más usado de cada pitcher?", """
        with usage as (
            select pitcher_anon_id, pitch_group, count(*) n,
                   row_number() over (partition by pitcher_anon_id order by count(*) desc) rk
            from clean where usable_stuff and pitch_group in ('Four-Seam', 'Sinker', 'Cutter')
            group by pitcher_anon_id, pitch_group)
        select pitch_group recta_principal, count(*) pitchers
        from usage where rk = 1 group by 1 order by 2 desc""")
    show(con, "Pitchers sin ninguna recta registrada (≥ 100 pitches)", """
        select count(*) pitchers from (
            select pitcher_anon_id from clean where usable_stuff group by 1
            having count(*) >= 100
               and count(*) filter (where pitch_group in ('Four-Seam', 'Sinker', 'Cutter')) = 0)""")
    show(con, "Juegos por pitcher con suficientes rectas para una referencia del mismo juego", f"""
        with per_game as (
            select pitcher_anon_id, game_anon_id,
                   count(*) filter (where pitch_group in ('Four-Seam', 'Sinker')) fastballs
            from clean where usable_stuff group by all)
        select avg((fastballs >= 5)::int) pct_juegos_con_5_rectas,
               avg((fastballs >= {MIN_FASTBALLS_PER_GAME})::int) pct_juegos_con_15_rectas
        from per_game""")


def main():
    con = duckdb.connect()
    con.execute(f"create view clean as select * from '{CLEAN_PARQUET}'")
    create_game_drag(con)
    drag_is_physical(con)
    pitch_order_available(con)
    altitude_shifts_shape(con)
    primary_fastball(con)


if __name__ == "__main__":
    main()
