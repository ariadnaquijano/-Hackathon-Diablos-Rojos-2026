"""Perfil de calidad de datos: sustenta las reglas de docs/01_limpieza.md.

Mide dos cosas antes de limpiar:
1. Si los batazos sin ExitSpeed faltan al azar o no (define si imputar o eliminar).
2. Cuántos pitches caen fuera de límites físicos imposibles (define los rangos).

Uso:
    python src/perfil_calidad_datos.py
"""

import duckdb

from config import PHYSICAL_LIMITS, RAW_PARQUET, SUSPICIOUS_EXIT_SPEED


def show(con: duckdb.DuckDBPyConnection, title: str, sql: str) -> None:
    print(f"\n## {title}\n")
    print(con.sql(sql).df().round(4).to_string(index=False))


def missing_exit_speed(con):
    show(con, "Bolas en juego con y sin ExitSpeed", """
        select ExitSpeed is null sin_exit_speed, count(*) bolas_en_juego,
               sum(is_hit) / count(*) hit_rate, sum(home_run) / count(*) hr_rate,
               avg((hit_type is null)::int) sin_hit_type
        from raw where is_ball_in_play = 1 group by 1""")
    show(con, "ExitSpeed faltante por tipo de batazo", """
        select hit_type, count(*) bolas_en_juego, avg((ExitSpeed is null)::int) pct_sin_exit_speed
        from raw where is_ball_in_play = 1 group by 1 order by 2 desc""")
    show(con, "ExitSpeed faltante por altitud", """
        select altitude_category, avg((ExitSpeed is null)::int) pct_sin_exit_speed
        from raw where is_ball_in_play = 1 group by 1 order by 1""")
    show(con, "ExitSpeed faltante por tipo de pitch", """
        select AutoPitchType, count(*) bolas_en_juego, avg((ExitSpeed is null)::int) pct_sin_exit_speed
        from raw where is_ball_in_play = 1 group by 1 having count(*) > 1000 order by 1""")


def tails(con):
    columns = [*PHYSICAL_LIMITS, "PlateLocHeight", "PlateLocSide", "ExitSpeed"]
    union = " union all ".join(
        f"""select '{c}' as variable_fisica, min("{c}") min, quantile_cont("{c}", 0.001) p0_1,
                   median("{c}") p50, quantile_cont("{c}", 0.999) p99_9, max("{c}") max from raw"""
        for c in columns
    )
    show(con, "Colas de las variables físicas", union)


def out_of_physical_limits(con):
    conditions = {c: f'"{c}" not between {lo} and {hi}' for c, (lo, hi) in PHYSICAL_LIMITS.items()}
    counts = ", ".join(f'count(*) filter (where {cond}) as "{c}"' for c, cond in conditions.items())
    any_violation = " or ".join(conditions.values())
    show(con, "Pitches fuera de límites físicos", f"""
        select count(*) total, {counts},
               count(*) filter (where {any_violation}) cualquiera,
               count(*) filter (where {any_violation}) / count(*) pct_cualquiera,
               count(*) filter (where ExitSpeed > {SUSPICIOUS_EXIT_SPEED}) exit_speed_sospechosa
        from raw""")


def plate_height_floor(con):
    show(con, "Pitches con PlateLocHeight exactamente 0 (tocan el suelo)", """
        select PitchCall, count(*) pitches
        from raw where PlateLocHeight = 0 group by 1 order by 2 desc""")


def main():
    con = duckdb.connect()
    con.execute(f"create view raw as select * from '{RAW_PARQUET}'")
    missing_exit_speed(con)
    tails(con)
    out_of_physical_limits(con)
    plate_height_floor(con)


if __name__ == "__main__":
    main()
