"""Etapa 1 · Limpieza: data/raw → data/processed/pitches_limpios.parquet.

Aplica las reglas de docs/01_limpieza.md. Principio central: ni inventar ni borrar.
Ninguna fila se elimina; cada problema queda en una columna flag_*, un valor mal medido
se anula (queda nulo) sin tocar el resto del pitch, y `usable_stuff` resume si el pitch
sirve para el modelo Stuff+.

También escribe reportes/etapa_01_resumen.json con el conteo de cada regla,
que alimenta el documento y el reporte HTML de la etapa.

Uso:
    python src/limpieza.py
"""

import json

import duckdb

from config import (CLEAN_PARQUET, HOLDOUT_SEASON, KEY_PHYSICS, PHYSICAL_LIMITS, RAW_PARQUET,
                    REPORTS_DIR, SUSPICIOUS_EXIT_SPEED)

SUMMARY_JSON = REPORTS_DIR / "etapa_01_resumen.json"

# Tipos de pitch con muy pocos casos o mal etiquetados se reagrupan (regla F, decisión D-010).
PITCH_GROUPS = {
    "Four-Seam": "Four-Seam",
    "Sinker": "Sinker",
    "TwoSeamFastBall": "Sinker",
    "OneSeamFastBall": "Sinker",
    "Cutter": "Cutter",
    "Slider": "Slider",
    "Sweeper": "Slider",
    "Curveball": "Curveball",
    "Changeup": "Changeup",
    "Splitter": "Splitter",
}

# Atípico dentro de su propio pitch: más de 6 desviaciones robustas de la mediana del pitcher
# para ese grupo de pitch (regla D, segunda capa, decisión D-011).
ROBUST_Z_LIMIT = 6
MIN_PITCHES_FOR_ROBUST_Z = 30
# Errores de medición: el valor está mal, el resto del pitch está bien → se anula el valor.
MEASUREMENT_VARIABLES = ["SpinRate", "Extension", "RelHeight", "RelSide"]
# Forma del pitch: el valor está bien medido, lo sospechoso es la etiqueta → solo se marca.
SHAPE_VARIABLES = ["RelSpeed", "InducedVertBreak", "HorzBreak"]
ROBUST_Z_VARIABLES = MEASUREMENT_VARIABLES + SHAPE_VARIABLES

# PitchCall es la fuente primaria; las banderas de resultado se recalculan desde ahí (regla E).
SWING_CALLS = ("StrikeSwinging", "FoulBall", "FoulBallNotFieldable", "FoulBallFieldable", "InPlay")
CONTACT_CALLS = ("FoulBall", "FoulBallNotFieldable", "FoulBallFieldable", "InPlay")
DERIVED_OUTCOMES = {
    "is_swing": f"PitchCall in ({', '.join(repr(c) for c in SWING_CALLS)})",
    "is_whiff": "PitchCall = 'StrikeSwinging'",
    "is_contact": f"PitchCall in ({', '.join(repr(c) for c in CONTACT_CALLS)})",
    "is_ball_in_play": "PitchCall = 'InPlay'",
}

OUTCOME_FLAGS = ["is_swing", "is_whiff", "is_contact", "is_called_strike", "is_swinging_strike",
                 "is_ball_in_play", "is_batted", "is_hit", "single", "double", "triple",
                 "home_run", "base_on_balls", "strikeout", "is_hit_by_pitch", "in_strike_zone",
                 "outside_strike_zone", "swung_outside_strike_zone"]
COUNT_COLUMNS = ["Balls", "Strikes", "Outs", "Inning", "RunsScored", "OutsOnPlay"]

FLAG_DESCRIPTIONS = {
    "flag_sin_altitud": "Sin categoría de altitud",
    "flag_sin_fisica": "Falta alguna variable física clave en el dato original",
    "flag_fisica_imposible": "Algún valor físico fuera de límites imposibles",
    "flag_valor_anulado": "Spin o release mal medido para ese pitcher; solo ese valor se anuló",
    "flag_posible_mal_etiquetado": "Velocidad o movimiento muy distinto a su tipo de pitch; se conserva",
    "flag_tipo_pitch_raro": "Tipo de pitch sin grupo modelable (Other, Knuckleball)",
    "flag_mano_inferida": "Mano del pitcher faltante, inferida",
    "flag_lado_bateador_inferido": "Lado del bateador faltante o switch, inferido",
    "flag_resultado_corregido": "Banderas de resultado inconsistentes con PitchCall, recalculadas",
    "flag_pitchcall_indefinido": "PitchCall = Undefined, no sirve como target",
    "flag_outs_invalido": "Outs = 3 antes del pitch (imposible)",
    "flag_sin_exit_speed": "Bola en juego sin ExitSpeed (se conserva, decisión D-007)",
    "flag_exit_speed_sospechosa": f"ExitSpeed mayor a {SUSPICIOUS_EXIT_SPEED} mph (se conserva)",
}


def create_typed(con):
    """Regla A: tipos correctos, grupo de pitch limpio y orden cronológico.

    El dataset no trae número de pitch, pero sus filas vienen en orden cronológico: dentro de cada
    juego la entrada y el conteo nunca retroceden, y los juegos vienen por fecha (decisión D-015).
    `pitch_seq` guarda ese orden para construir secuencias, series y relevos.
    """
    flags = ", ".join(f"cast({c} as tinyint) as {c}" for c in OUTCOME_FLAGS)
    counts = ", ".join(f"cast({c} as integer) as {c}" for c in COUNT_COLUMNS)
    pitch_group = " ".join(f"when '{raw}' then '{group}'" for raw, group in PITCH_GROUPS.items())
    con.execute(f"""
        create or replace view typed as
        select * replace (try_cast(EffectiveVelo as double) as EffectiveVelo, {flags}, {counts}),
               case AutoPitchType {pitch_group} else 'Other' end as pitch_group,
               file_row_number as pitch_seq
        from read_parquet('{RAW_PARQUET}', file_row_number = true)""")


def create_handedness(con):
    """Regla B: mano del pitcher y lado del bateador.

    Mano faltante → la mano habitual de ese pitcher; si nunca se registró, el lado del release.
    Lado del bateador faltante → el lado habitual de ese bateador contra esa mano;
    un switch batea del lado contrario a la mano del pitcher.
    """
    con.execute("""
        create or replace table pitcher_modal_hand as
        select pitcher_anon_id, mode(PitcherThrows) as modal_hand
        from typed where PitcherThrows in ('Left', 'Right') group by 1""")
    con.execute("""
        create or replace view with_pitcher_hand as
        select t.*,
               case when t.PitcherThrows in ('Left', 'Right') then t.PitcherThrows
                    when p.modal_hand is not null then p.modal_hand
                    when t.RelSide < 0 then 'Left'
                    when t.RelSide > 0 then 'Right' end as pitcher_hand
        from typed t left join pitcher_modal_hand p using (pitcher_anon_id)""")
    con.execute("""
        create or replace table batter_modal_side as
        select batter_anon_id, pitcher_hand, mode(BatterSide) as modal_side
        from with_pitcher_hand where BatterSide in ('Left', 'Right') group by all""")
    con.execute("""
        create or replace view handed as
        select h.*,
               case when h.BatterSide in ('Left', 'Right') then h.BatterSide
                    when h.BatterSide = 'Switch' then
                         case h.pitcher_hand when 'Left' then 'Right' when 'Right' then 'Left' end
                    else b.modal_side end as batter_side
        from with_pitcher_hand h left join batter_modal_side b using (batter_anon_id, pitcher_hand)""")


def create_robust_stats(con):
    """Regla D, segunda capa: mediana y desviación robusta por pitcher y grupo de pitch."""
    medians = ", ".join(f"median({v}) as med_{v}" for v in ROBUST_Z_VARIABLES)
    spreads = ", ".join(f"1.4826 * median(abs(h.{v} - m.med_{v})) as mad_{v}"
                        for v in ROBUST_Z_VARIABLES)
    con.execute(f"""
        create or replace table pitch_medians as
        select pitcher_anon_id, pitch_group, {medians}
        from handed group by all having count(*) >= {MIN_PITCHES_FOR_ROBUST_Z}""")
    con.execute(f"""
        create or replace table robust_stats as
        select m.*, {spreads}
        from handed h join pitch_medians m using (pitcher_anon_id, pitch_group)
        group by all""")


def is_atypical(variable: str) -> str:
    return (f"coalesce(abs(h.{variable} - s.med_{variable}) / nullif(s.mad_{variable}, 0)"
            f" > {ROBUST_Z_LIMIT}, false)")


def any_of(conditions) -> str:
    return " or ".join(f"({c})" for c in conditions)


def create_clean(con):
    """Reglas C–I: banderas, valores anulados, resultados recalculados y columnas derivadas."""
    physics_missing = any_of(f"h.{c} is null" for c in KEY_PHYSICS)
    impossible = any_of(f"h.{c} not between {lo} and {hi}" for c, (lo, hi) in PHYSICAL_LIMITS.items())
    nulled_values = ", ".join(
        f"case when {is_atypical(v)} then null else h.{v} end as {v}" for v in MEASUREMENT_VARIABLES)
    recomputed = ", ".join(
        f"case when h.PitchCall = 'Undefined' then null else ({expr})::tinyint end as {col}"
        for col, expr in DERIVED_OUTCOMES.items())
    outcome_mismatch = any_of(f"h.{col} is distinct from ({expr})::tinyint"
                              for col, expr in DERIVED_OUTCOMES.items())

    con.execute(f"""
        create or replace table flagged as
        select h.* replace ({nulled_values}, {recomputed}),
               h.altitude_category is null as flag_sin_altitud,
               {physics_missing} as flag_sin_fisica,
               coalesce({impossible}, false) as flag_fisica_imposible,
               {any_of(is_atypical(v) for v in MEASUREMENT_VARIABLES)} as flag_valor_anulado,
               {any_of(is_atypical(v) for v in SHAPE_VARIABLES)} as flag_posible_mal_etiquetado,
               h.pitch_group = 'Other' as flag_tipo_pitch_raro,
               h.PitcherThrows is distinct from h.pitcher_hand as flag_mano_inferida,
               h.BatterSide is distinct from h.batter_side as flag_lado_bateador_inferido,
               h.PitchCall <> 'Undefined' and ({outcome_mismatch}) as flag_resultado_corregido,
               coalesce(h.PitchCall = 'Undefined', true) as flag_pitchcall_indefinido,
               coalesce(h.Outs >= 3, false) as flag_outs_invalido,
               h.PitchCall = 'InPlay' and h.ExitSpeed is null as flag_sin_exit_speed,
               coalesce(h.ExitSpeed > {SUSPICIOUS_EXIT_SPEED}, false) as flag_exit_speed_sospechosa
        from handed h left join robust_stats s using (pitcher_anon_id, pitch_group)""")

    # Regla G: con la mano resuelta y los valores ya anulados, todo se expresa del lado del brazo
    # (positivo = hacia el brazo del pitcher) para que zurdos y derechos sean comparables.
    con.execute(f"""
        create or replace table clean as
        with signed as (select *, case pitcher_hand when 'Left' then -1 else 1 end as hand_sign
                        from flagged)
        select * exclude (hand_sign),
               HorzBreak * hand_sign as hb_arm_side,
               RelSide * hand_sign as rel_side_arm,
               HorzRelAngle * hand_sign as horz_rel_angle_arm,
               HorzApprAngle * hand_sign as horz_appr_angle_arm,
               case pitcher_hand when 'Left' then 360 - SpinAxis else SpinAxis end as spin_axis_arm,
               not (flag_sin_fisica or flag_fisica_imposible or flag_tipo_pitch_raro
                    or pitcher_hand is null) as usable_stuff,
               case when year = {HOLDOUT_SEASON} then 'holdout' else 'train' end as split
        from signed""")


def scalar(con, sql: str) -> int:
    return int(con.sql(sql).fetchone()[0])


def rows(con, sql: str) -> list[dict]:
    return con.sql(sql).df().round(4).to_dict(orient="records")


def build_summary(con) -> dict:
    total = scalar(con, "select count(*) from clean")
    flag_counts = []
    for name, description in FLAG_DESCRIPTIONS.items():
        pitches = scalar(con, f"select count(*) from clean where {name}")
        flag_counts.append({"flag": name, "descripcion": description,
                            "pitches": pitches, "pct": round(pitches / total, 5)})
    return {
        "total_pitches": total,
        "usable_stuff": scalar(con, "select count(*) from clean where usable_stuff"),
        "lado_bateador_sin_resolver": scalar(con, "select count(*) from clean where batter_side is null"),
        "banderas": flag_counts,
        "valores_anulados_por_variable": rows(con, " union all ".join(
            f"select '{v}' as variable, count(*)::int as valores_anulados from flagged f "
            f"join handed h using (PitchUID) where f.{v} is null and h.{v} is not null"
            for v in MEASUREMENT_VARIABLES)),
        "batazos_con_y_sin_exit_speed": rows(con, """
            select flag_sin_exit_speed sin_exit_speed, count(*)::int bolas_en_juego,
                   avg(is_hit) hit_rate, avg(home_run) hr_rate
            from clean where is_ball_in_play = 1 group by 1 order by 1"""),
        "por_split": rows(con, """
            select split, count(*)::int pitches, count(*) filter (where usable_stuff)::int usable_stuff
            from clean group by 1 order by 1"""),
        "por_grupo_pitch": rows(con, """
            select pitch_group, count(*)::int pitches,
                   count(*) filter (where usable_stuff)::int usable_stuff
            from clean group by 1 order by 2 desc"""),
        "por_altitud": rows(con, """
            select coalesce(altitude_category, 'Sin dato') altitud, count(*)::int pitches,
                   count(*) filter (where usable_stuff)::int usable_stuff
            from clean group by 1 order by 1"""),
        "correcciones_resultado": rows(con, f"""
            select r.PitchCall, count(*)::int pitches,
                   count(*) filter (where r.is_swing = 1 and c.is_swing = 0)::int swing_quitado,
                   count(*) filter (where r.is_contact = 1 and c.is_contact = 0)::int contacto_quitado
            from read_parquet('{RAW_PARQUET}') r join clean c using (PitchUID)
            where c.flag_resultado_corregido group by 1 order by 2 desc"""),
        "resolucion_mano": rows(con, """
            select coalesce(PitcherThrows, 'NULL') original, pitcher_hand resuelta, count(*)::int pitches
            from clean where flag_mano_inferida group by all order by 3 desc"""),
        "recta_por_mano_antes_despues": rows(con, """
            select pitcher_hand, median(HorzBreak) hb_original, median(hb_arm_side) hb_lado_brazo,
                   median(SpinAxis) eje_original, median(spin_axis_arm) eje_lado_brazo
            from clean where pitch_group = 'Four-Seam' and pitcher_hand is not null
            group by 1 order by 1"""),
    }


def main():
    con = duckdb.connect()
    create_typed(con)
    create_handedness(con)
    create_robust_stats(con)
    create_clean(con)

    CLEAN_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"copy (select * from clean order by pitch_seq) to '{CLEAN_PARQUET}' (format parquet, compression zstd)")

    summary = build_summary(con)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
