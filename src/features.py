"""Etapa 2 · Features: data/processed/pitches_limpios.parquet → data/processed/features.parquet.

Construye las variables del plan (docs/02_plan_features.md) en el orden en que dependen
una de otra:

1. Aire del juego (`air_ratio`), medido con el arrastre de las rectas.
2. Exponente k de la relación movimiento ∝ air_ratio^k, estimado con datos.
3. Forma equivalente a nivel del mar (`ivb_sea_level`, `hb_sea_level`).
4. Reclasificación por forma de los pitches posiblemente mal etiquetados (`pitch_class`).
5. Sweeper contra slider sobre la forma a nivel del mar (`slider_shape`, decisión D-013).
6. Ángulos de llegada relativos a la ubicación (`vaa_rel`, `haa_rel`, decisión D-012).
7. Arsenal contra la recta principal con referencia ponderada (decisión D-014).
8. Contexto para Location+ y Pitching+ (zona, platoon).
9. Secuencia: turno al bat, pitch anterior, tunneling, conteo de pitches, vuelta al orden y rol
   (decisión D-015: las filas del dataset vienen en orden cronológico).

Ninguna variable usa el resultado del pitch. Escribe reportes/etapa_02_resumen.json con
todas las cifras que citan el documento y el reporte de la etapa.

Uso:
    python src/features.py
"""

import json

import duckdb
import numpy as np
from sklearn.mixture import GaussianMixture

from config import CLEAN_PARQUET, FEATURES_PARQUET, REPORTS_DIR

SUMMARY_JSON = REPORTS_DIR / "etapa_02_resumen.json"
GRAVITY_FT_S2 = 32.174
RANDOM_SEED = 2026

# 1. Aire: rectas usadas para medir el arrastre y mínimo por juego para confiar en la medida.
AIR_FASTBALLS = ("Four-Seam", "Sinker")
MIN_FASTBALLS_FOR_GAME_AIR = 20

# 2. Exponente k: solo pitches con movimiento claro (el logaritmo de valores cercanos a 0 es ruido).
MIN_BREAK_FOR_EXPONENT_IN = 4.0
MIN_PITCHES_PER_PITCHER_GAME = 5
BOOTSTRAP_SAMPLES = 200
# Un tipo de pitch usa su propio exponente si hay suficientes pitchers; si no, el de la liga.
MIN_PITCHERS_FOR_OWN_EXPONENT = 100
EXPONENT_PITCH_GROUPS = ("Four-Seam", "Sinker", "Cutter", "Slider", "Curveball", "Changeup", "Splitter")
MOVEMENT_COMPONENTS = {"ivb": "InducedVertBreak", "hb": "hb_arm_side"}

# 4. Reclasificación: centroides por pitcher y grupo, con al menos 30 pitches bien etiquetados.
MIN_PITCHES_FOR_CENTROID = 30
MAX_RECLASS_DISTANCE = 6.0

# 5. Sweeper: punto de partida y criterio de separación natural entre dos grupos.
SWEEPER_START_THRESHOLD_IN = -12.0
MIN_ASHMAN_D = 2.0

# 7. Arsenal: rectas candidatas a recta principal y uso mínimo para contar un pitch en el arsenal.
FASTBALL_CLASSES = ("Four-Seam", "Sinker", "Cutter")
MIN_USAGE_FOR_ARSENAL = 0.05
REFERENCE_VARIABLES = {
    "velo": "RelSpeed",
    "ivb": "InducedVertBreak",
    "hb": "hb_arm_side",
    "axis": "spin_axis_arm",
    "rel_height": "RelHeight",
    "rel_side": "rel_side_arm",
    "extension": "Extension",
}

# 9. Secuencia. Trackman: X = distancia al home (el frente del plato está en 1.417 ft), Y = altura,
#    Z = lado con el signo invertido respecto a PlateLocSide (verificado con los datos).
PLATE_FRONT_FT = 1.417
# El bateador decide ~175 ms antes de que la pelota llegue: ahí se mide el tunneling.
DECISION_TIME_BEFORE_PLATE_S = 0.175
PA_ENDING_CALLS = ("InPlay", "HitByPitch")
# Más de 6 turnos del mismo bateador contra el mismo pitcher en un juego no ocurre: es un ID genérico.
MAX_PLAUSIBLE_TIMES_THROUGH_ORDER = 6

# 8. Zona de strike (pies): la misma caja fija que usa la bandera in_strike_zone del dataset
#    (medida con los datos: 1.62 a 3.21 ft de alto y ±0.708 ft, el ancho del plato).
ZONE_HALF_WIDTH_FT = 0.708
ZONE_BOTTOM_FT = 1.62
ZONE_TOP_FT = 3.21


def rows(con, sql: str) -> list[dict]:
    frame = con.sql(sql).df().round(4)
    # Los nulos salen como None (null en JSON), no como NaN, que no es JSON válido.
    return frame.astype(object).where(frame.notna(), None).to_dict(orient="records")


def scalar(con, sql: str):
    return con.sql(sql).fetchone()[0]


# ─── 1. Aire del juego ────────────────────────────────────────────────────────────────────

def create_air_ratio(con):
    """air_ratio = arrastre del juego ÷ arrastre típico a nivel del mar en esa temporada.

    Normalizar por temporada corrige la deriva del arrastre año con año (docs/02_plan_features.md).
    Si un juego tiene pocas rectas se usa la mediana de su categoría de altitud y temporada.
    """
    fastballs = ", ".join(f"'{p}'" for p in AIR_FASTBALLS)
    con.execute(f"""
        create or replace table game_drag as
        select game_anon_id, any_value(year) as year, any_value(altitude_category) altitude_category,
               median((vx0*ax0 + vy0*ay0 + vz0*(az0 + {GRAVITY_FT_S2}))
                      / -(vx0*vx0 + vy0*vy0 + vz0*vz0)) drag,
               count(*) fastballs
        from clean where usable_stuff and pitch_group in ({fastballs})
        group by 1""")
    con.execute(f"""
        create or replace table game_air as
        with reliable as (select * from game_drag where fastballs >= {MIN_FASTBALLS_FOR_GAME_AIR}),
        sea_level as (
            select year, median(drag) sea_drag from reliable
            where altitude_category = 'No Altitude' group by 1),
        by_category as (
            select year, altitude_category, median(drag) category_drag
            from reliable where altitude_category is not null group by all)
        select g.game_anon_id,
               case when g.fastballs >= {MIN_FASTBALLS_FOR_GAME_AIR} then g.drag / s.sea_drag
                    else c.category_drag / s.sea_drag end as air_ratio,
               case when g.fastballs >= {MIN_FASTBALLS_FOR_GAME_AIR} then 'juego'
                    when c.category_drag is not null then 'categoria' end as air_source
        from game_drag g
        join sea_level s using (year)
        left join by_category c using (year, altitude_category)""")


def air_summary(con) -> dict:
    return {
        "por_altitud_y_temporada": rows(con, """
            select coalesce(d.altitude_category, 'Sin dato') altitud, d.year as year, count(*) juegos,
                   quantile_cont(a.air_ratio, 0.1) p10, median(a.air_ratio) p50,
                   quantile_cont(a.air_ratio, 0.9) p90
            from game_air a join game_drag d using (game_anon_id)
            where a.air_source = 'juego' group by all order by all"""),
        "fuente": rows(con, """
            select coalesce(air_source, 'sin medida') fuente, count(*) juegos
            from game_air group by 1 order by 2 desc"""),
        "histograma": rows(con, """
            select coalesce(d.altitude_category, 'Sin dato') altitud,
                   round(floor(a.air_ratio * 50) / 50, 2) air_ratio, count(*) juegos
            from game_air a join game_drag d using (game_anon_id)
            where a.air_source = 'juego' group by all order by all"""),
    }


# ─── 2. Exponente k ───────────────────────────────────────────────────────────────────────

def exponent_games(con, expr: str, pitch_group: str | None = None):
    """Salidas de un pitcher con un pitch, centradas dentro de cada pitcher y tipo de pitch.

    Se comparan las salidas de un mismo pitcher con su mismo pitch en aires distintos, así que la
    calidad del pitcher no confunde la estimación. `z` es el aire típico de la categoría de altitud
    y temporada del juego: el instrumento de la variable instrumental (ver bootstrap_slope).
    """
    group_filter = f"and pitch_group = '{pitch_group}'" if pitch_group else ""
    return con.sql(f"""
        with category_air as (
            select d.altitude_category, d.year, median(a.air_ratio) category_air
            from game_air a join game_drag d using (game_anon_id)
            where a.air_source = 'juego' and d.altitude_category is not null group by all),
        pitches as (
            select c.pitcher_anon_id, c.pitch_group, c.game_anon_id, ln({expr}) log_break,
                   ln(a.air_ratio) log_air, ln(k.category_air) log_category_air
            from clean c join game_air a using (game_anon_id)
            join category_air k on k.altitude_category = c.altitude_category and k.year = c.year
            where c.usable_stuff and a.air_source = 'juego' and {expr} >= {MIN_BREAK_FOR_EXPONENT_IN}
              {group_filter}),
        per_game as (
            select pitcher_anon_id, pitch_group, game_anon_id, avg(log_break) log_break,
                   any_value(log_air) log_air, any_value(log_category_air) log_category_air
            from pitches group by all having count(*) >= {MIN_PITCHES_PER_PITCHER_GAME})
        select pitcher_anon_id,
               log_break - avg(log_break) over w as y,
               log_air - avg(log_air) over w as x,
               log_category_air - avg(log_category_air) over w as z
        from per_game window w as (partition by pitcher_anon_id, pitch_group)""").df()


def estimate_air_exponent(con) -> dict:
    """k de movimiento ∝ air_ratio^k: de la liga y por tipo de pitch y componente.

    El movimiento horizontal y el vertical no responden igual al aire, ni todos los tipos de pitch,
    así que la conversión a nivel del mar usa el k de su tipo y componente cuando hay datos.
    """
    expressions = {"movimiento_total": "sqrt(InducedVertBreak^2 + hb_arm_side^2)",
                   **{name: f"abs({col})" for name, col in MOVEMENT_COMPONENTS.items()}}
    league = {name: bootstrap_slope(exponent_games(con, expr)) for name, expr in expressions.items()}
    by_group = {}
    for group in EXPONENT_PITCH_GROUPS:
        by_group[group] = {}
        for name, col in MOVEMENT_COMPONENTS.items():
            estimate = bootstrap_slope(exponent_games(con, f"abs({col})", group))
            estimate["usa_propio"] = estimate["pitchers"] >= MIN_PITCHERS_FOR_OWN_EXPONENT
            estimate["k_usado"] = estimate["k"] if estimate["usa_propio"] else league[name]["k"]
            by_group[group][name] = estimate
    return {"liga": league, "por_tipo": by_group}


def bootstrap_slope(games) -> dict:
    """Pendiente por variable instrumental y su intervalo de 95 % por bootstrap de pitchers.

    El aire de cada juego se mide con ruido, y el ruido en la variable explicativa achica la
    pendiente (atenuación). La variable instrumental usa solo la parte del aire que explica la
    categoría de altitud y temporada, que se mide con mucha precisión: k = Σ y·z / Σ x·z.
    También se reporta la pendiente directa (mínimos cuadrados), para mostrar la atenuación.
    """
    def iv(x, y, z):
        return float((y * z).sum() / (x * z).sum())

    def ols(x, y):
        return float((x * y).sum() / (x ** 2).sum())

    rng = np.random.default_rng(RANDOM_SEED)
    by_pitcher = {p: g for p, g in games.groupby("pitcher_anon_id")}
    pitchers = np.array(list(by_pitcher))
    draws = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = rng.choice(pitchers, size=len(pitchers), replace=True)
        frame = [by_pitcher[p] for p in sample]
        draws.append(iv(*(np.concatenate([f[c].to_numpy() for f in frame]) for c in ("x", "y", "z"))))
    low, high = np.percentile(draws, [2.5, 97.5])
    return {"k": round(iv(games.x, games.y, games.z), 4), "ic95": [round(low, 4), round(high, 4)],
            "k_sin_corregir_atenuacion": round(ols(games.x, games.y), 4),
            "salidas": len(games), "pitchers": int(games.pitcher_anon_id.nunique())}


# ─── 3 y 4. Forma a nivel del mar y reclasificación ───────────────────────────────────────

def create_sea_level_shape(con, exponent: dict):
    """Movimiento ÷ air_ratio^k, con el k del tipo de pitch y del componente."""
    def k_case(component: str) -> str:
        branches = " ".join(f"when '{group}' then {values[component]['k_usado']}"
                            for group, values in exponent["por_tipo"].items())
        return f"case pitch_group {branches} else {exponent['liga'][component]['k']} end"

    con.execute(f"""
        create or replace table shaped as
        select c.*, a.air_ratio, a.air_source,
               c.InducedVertBreak / pow(a.air_ratio, {k_case('ivb')}) as ivb_sea_level,
               c.hb_arm_side / pow(a.air_ratio, {k_case('hb')}) as hb_sea_level
        from clean c left join game_air a using (game_anon_id)""")


def reclassify_by_shape(con) -> dict:
    """Cada pitch posiblemente mal etiquetado se asigna al pitch de su propio repertorio
    cuya forma a nivel del mar se le parece más (velocidad, IVB y HB)."""
    con.execute(f"""
        create or replace table centroids as
        select pitcher_anon_id, pitch_group, median(RelSpeed) velo, median(ivb_sea_level) ivb,
               median(hb_sea_level) hb
        from shaped
        where usable_stuff and not flag_posible_mal_etiquetado and ivb_sea_level is not null
        group by all having count(*) >= {MIN_PITCHES_FOR_CENTROID}""")
    con.execute("""
        create or replace table shape_scale as
        with spread as (
            select pitcher_anon_id, pitch_group,
                   median(abs(s.RelSpeed - c.velo)) velo, median(abs(s.ivb_sea_level - c.ivb)) ivb,
                   median(abs(s.hb_sea_level - c.hb)) hb
            from shaped s join centroids c using (pitcher_anon_id, pitch_group)
            where s.usable_stuff and not s.flag_posible_mal_etiquetado group by all)
        select 1.4826 * median(velo) velo, 1.4826 * median(ivb) ivb, 1.4826 * median(hb) hb from spread""")
    con.execute(f"""
        create or replace table reassigned as
        with candidates as (
            select s.PitchUID, s.pitch_group original, c.pitch_group candidate,
                   sqrt(((s.RelSpeed - c.velo) / k.velo)^2 + ((s.ivb_sea_level - c.ivb) / k.ivb)^2
                        + ((s.hb_sea_level - c.hb) / k.hb)^2) distance
            from shaped s join centroids c using (pitcher_anon_id), shape_scale k
            where s.flag_posible_mal_etiquetado and s.usable_stuff and s.ivb_sea_level is not null),
        best as (
            select *, row_number() over (partition by PitchUID order by distance) rk from candidates)
        select PitchUID, original, candidate, distance from best
        where rk = 1 and distance <= {MAX_RECLASS_DISTANCE}""")
    return {
        "escala_robusta": rows(con, "select * from shape_scale")[0],
        "posibles_mal_etiquetados": int(scalar(con, """
            select count(*) from shaped where flag_posible_mal_etiquetado and usable_stuff""")),
        "reasignados": int(scalar(con, "select count(*) from reassigned where candidate <> original")),
        "confirmados": int(scalar(con, "select count(*) from reassigned where candidate = original")),
        "cambios": rows(con, """
            select original, candidate nuevo, count(*) pitches from reassigned
            where candidate <> original group by all order by 3 desc limit 12"""),
    }


# ─── 5. Sweeper contra slider ─────────────────────────────────────────────────────────────

def sweeper_cut(con) -> dict:
    """Corte natural entre dos grupos de sliders en la forma a nivel del mar (D-013).

    Ajusta una mezcla de dos normales con los datos de entrenamiento. Si los grupos no están
    claramente separados (D de Ashman < 2), se usa el corte de partida de 12 in.
    """
    sample = con.sql(f"""
        select hb_sea_level from shaped
        where usable_stuff and split = 'train' and pitch_group = 'Slider' and hb_sea_level is not null
        order by pitch_seq""").df()
    values = sample.hb_sea_level.to_numpy().reshape(-1, 1)
    gmm = GaussianMixture(n_components=2, random_state=RANDOM_SEED).fit(values)
    means = gmm.means_.ravel()
    sds = np.sqrt(gmm.covariances_.ravel())
    ashman_d = float(np.sqrt(2) * abs(means[0] - means[1]) / np.sqrt(sds[0] ** 2 + sds[1] ** 2))

    grid = np.linspace(min(means), max(means), 2001).reshape(-1, 1)
    posterior = gmm.predict_proba(grid)
    sweeper_component = int(np.argmin(means))
    crossing = grid.ravel()[np.argmin(np.abs(posterior[:, sweeper_component] - 0.5))]

    natural = ashman_d >= MIN_ASHMAN_D
    return {
        "medias_in": [round(float(m), 2) for m in means],
        "desviaciones_in": [round(float(s), 2) for s in sds],
        "pesos": [round(float(w), 3) for w in gmm.weights_],
        "ashman_d": round(ashman_d, 3),
        "corte_mezcla_in": round(float(crossing), 2),
        "hay_corte_natural": natural,
        "corte_usado_in": round(float(crossing), 2) if natural else SWEEPER_START_THRESHOLD_IN,
    }


# ─── 6. Ángulos relativos ─────────────────────────────────────────────────────────────────

def fit_relative_angles(con) -> dict:
    """Ángulo esperado por ubicación: parábola por tipo de pitch, ajustada solo con entrenamiento."""
    data = con.sql("""
        select coalesce(r.candidate, s.pitch_group) pitch_class, VertApprAngle vaa, PlateLocHeight h,
               horz_appr_angle_arm haa, PlateLocSide * case pitcher_hand when 'Left' then -1 else 1 end side
        from shaped s left join reassigned r using (PitchUID)
        where usable_stuff and split = 'train' and pitch_group <> 'Other'
          and VertApprAngle is not null and PlateLocHeight > 0""").df()
    fits = {}
    for pitch_class, g in data.groupby("pitch_class"):
        fits[pitch_class] = {
            "vaa": [float(c) for c in np.polyfit(g.h, g.vaa, 2)],
            "haa": [float(c) for c in np.polyfit(g.side, g.haa, 2)],
        }
    return fits


def angle_case(fits: dict, angle: str, location: str) -> str:
    branches = " ".join(
        f"when '{cls}' then {c[angle][0]} * {location} * {location} + {c[angle][1]} * {location} + {c[angle][2]}"
        for cls, c in fits.items())
    return f"case pitch_class {branches} end"


# ─── 7. Arsenal ───────────────────────────────────────────────────────────────────────────

def estimate_shrinkage(con) -> dict:
    """k = varianza dentro del juego ÷ varianza real entre juegos, por variable (D-014)."""
    estimates = {}
    for name, column in REFERENCE_VARIABLES.items():
        estimates[name] = rows(con, f"""
            with games as (
                select pitcher_anon_id, year, altitude_category, game_anon_id, count(*) n,
                       avg({column}) m, var_samp({column}) v
                from classified
                where is_primary_fb and {column} is not null and altitude_category is not null
                group by all having count(*) >= 2),
            groups as (
                select var_samp(m) between_var, avg(v / n) noise, avg(v) within_var
                from games group by pitcher_anon_id, year, altitude_category having count(*) >= 3)
            select avg(within_var) sigma2, avg(between_var) - avg(noise) tau2,
                   avg(within_var) / (avg(between_var) - avg(noise)) k
            from groups""")[0]
    return estimates


def mark_primary_fastball(con):
    """Recta principal = el pitch rápido más usado del pitcher en la temporada."""
    fastballs = ", ".join(f"'{c}'" for c in FASTBALL_CLASSES)
    con.execute(f"""
        create or replace table classified_fb as
        with fb as (
            select pitcher_anon_id, year, first(pitch_class order by n desc, pitch_class) primary_fb_type
            from (select pitcher_anon_id, year, pitch_class, count(*) n from classified
                  where usable_stuff and pitch_class in ({fastballs}) group by all)
            group by all)
        select c.*, fb.primary_fb_type,
               coalesce(c.usable_stuff and c.pitch_class = fb.primary_fb_type, false) is_primary_fb
        from classified c left join fb using (pitcher_anon_id, year)""")
    con.execute("drop table classified")
    con.execute("alter table classified_fb rename to classified")


def create_arsenal(con, shrinkage: dict):
    """Referencia de la recta = mezcla del mismo juego con el resto de las salidas del pitcher en
    esa altitud y temporada, con peso n / (n + k) (D-014).

    El respaldo excluye el juego actual (leave-one-out) para no contarlo dos veces. Si el pitcher
    no tiene otras salidas en esa altitud, se usa el resto de su temporada.
    """
    sums = ", ".join(f"sum({col}) filter (where {col} is not null) s_{name}, "
                     f"count({col}) n_{name}" for name, col in REFERENCE_VARIABLES.items())
    altitude = "coalesce(altitude_category, 'Sin dato')"
    con.execute(f"""
        create or replace table fb_game as
        select pitcher_anon_id, year, {altitude} altitude, game_anon_id, count(*) n, {sums}
        from classified where is_primary_fb group by all""")
    con.execute(f"""
        create or replace table fb_altitude as
        select pitcher_anon_id, year, altitude, {", ".join(f"sum(s_{n}) s_{n}, sum(n_{n}) n_{n}" for n in REFERENCE_VARIABLES)}
        from fb_game group by all""")
    con.execute(f"""
        create or replace table fb_season as
        select pitcher_anon_id, year, {", ".join(f"sum(s_{n}) s_{n}, sum(n_{n}) n_{n}" for n in REFERENCE_VARIABLES)}
        from fb_game group by all""")

    def reference(name: str) -> str:
        game_n = f"coalesce(g.n_{name}, 0)"
        game_s = f"coalesce(g.s_{name}, 0)"
        prior = f"""coalesce(
            (a.s_{name} - {game_s}) / nullif(a.n_{name} - {game_n}, 0),
            (s.s_{name} - {game_s}) / nullif(s.n_{name} - {game_n}, 0))"""
        game_mean = f"g.s_{name} / nullif(g.n_{name}, 0)"
        k = shrinkage[name]["k"]
        return f"""case when {game_n} = 0 then {prior}
                        when {prior} is null then {game_mean}
                        else ({game_n} * {game_mean} + {k} * {prior}) / ({game_n} + {k}) end as ref_{name}"""

    con.execute(f"""
        create or replace table fb_reference as
        select c.PitchUID, g.n fb_in_game, {", ".join(reference(n) for n in REFERENCE_VARIABLES)}
        from classified c
        left join fb_game g using (pitcher_anon_id, game_anon_id)
        left join fb_altitude a on a.pitcher_anon_id = c.pitcher_anon_id and a.year = c.year
             and a.altitude = coalesce(c.altitude_category, 'Sin dato')
        left join fb_season s on s.pitcher_anon_id = c.pitcher_anon_id and s.year = c.year""")
    con.execute(f"""
        create or replace table usage as
        with counts as (
            select pitcher_anon_id, year, pitch_class, count(*) n
            from classified where usable_stuff group by all),
        shares as (
            select *, n / sum(n) over (partition by pitcher_anon_id, year) pitch_usage_pct from counts)
        select *, count(*) filter (where pitch_usage_pct >= {MIN_USAGE_FOR_ARSENAL})
                      over (partition by pitcher_anon_id, year) arsenal_size
        from shares""")


# ─── 8. Contexto ──────────────────────────────────────────────────────────────────────────

def zone_expression() -> str:
    """9 celdas dentro de la zona (alto/medio/bajo × adentro/centro/afuera respecto al bateador)
    y 4 regiones fuera de ella."""
    third_w = 2 * ZONE_HALF_WIDTH_FT / 3
    third_h = (ZONE_TOP_FT - ZONE_BOTTOM_FT) / 3
    side = "PlateLocSide * case batter_side when 'Right' then -1 else 1 end"  # positivo = adentro
    return f"""
        case
          when PlateLocHeight is null or PlateLocSide is null or batter_side is null then null
          when PlateLocHeight > {ZONE_TOP_FT} then 'fuera_alto'
          when PlateLocHeight < {ZONE_BOTTOM_FT} then 'fuera_bajo'
          when {side} > {ZONE_HALF_WIDTH_FT} then 'fuera_adentro'
          when {side} < -{ZONE_HALF_WIDTH_FT} then 'fuera_afuera'
          else (case when PlateLocHeight >= {ZONE_TOP_FT - third_h} then 'alto'
                     when PlateLocHeight >= {ZONE_BOTTOM_FT + third_h} then 'medio' else 'bajo' end)
               || '_' ||
               (case when {side} >= {ZONE_HALF_WIDTH_FT - third_w} then 'adentro'
                     when {side} >= -{ZONE_HALF_WIDTH_FT - third_w} then 'centro' else 'afuera' end)
        end"""



# ─── 9. Secuencia ─────────────────────────────────────────────────────────────────────────

def trajectory_position(t: str) -> tuple[str, str]:
    """Altura y lado (con el signo de PlateLocSide) del pitch en el instante t."""
    height = f"(PitchTrajectoryYc0 + PitchTrajectoryYc1 * {t} + PitchTrajectoryYc2 * {t} * {t})"
    side = f"-(PitchTrajectoryZc0 + PitchTrajectoryZc1 * {t} + PitchTrajectoryZc2 * {t} * {t})"
    return height, side


def create_sequence(con):
    """Reconstruye turnos al bat y la secuencia de pitches con el orden del dataset (D-015).

    Un turno nuevo empieza cuando cambia la media entrada o el bateador, o cuando el pitch anterior
    terminó el turno (bola en juego, golpe, ponche o base por bolas).
    """
    plate_time = f"""(-PitchTrajectoryXc1 - sqrt(PitchTrajectoryXc1^2
                      - 4 * PitchTrajectoryXc2 * (PitchTrajectoryXc0 - {PLATE_FRONT_FT})))
                     / (2 * PitchTrajectoryXc2)"""
    ending = ", ".join(f"'{c}'" for c in PA_ENDING_CALLS)
    con.execute(f"""
        create or replace table sequence_base as
        with timed as (
            select PitchUID, pitch_seq, game_anon_id, pitcher_anon_id, batter_anon_id, Inning,
                   "Top/Bottom" half, Balls, Strikes, PitchCall, KorBB, pitch_class, RelSpeed,
                   PlateLocHeight, PlateLocSide, PitchTrajectoryYc0, PitchTrajectoryYc1, PitchTrajectoryYc2,
                   PitchTrajectoryZc0, PitchTrajectoryZc1, PitchTrajectoryZc2,
                   case when PitchTrajectoryXc1^2 - 4 * PitchTrajectoryXc2 * (PitchTrajectoryXc0 - {PLATE_FRONT_FT}) >= 0
                        then {plate_time} end as t_plate
            from classified),
        positioned as (
            select *, {trajectory_position(f"(t_plate - {DECISION_TIME_BEFORE_PLATE_S})")[0]} decision_height,
                      {trajectory_position(f"(t_plate - {DECISION_TIME_BEFORE_PLATE_S})")[1]} decision_side
            from timed),
        marked as (
            select *,
                   coalesce(lag(Inning) over g is distinct from Inning
                            or lag(half) over g is distinct from half
                            or lag(batter_anon_id) over g is distinct from batter_anon_id
                            or lag(PitchCall) over g in ({ending})
                            or lag(KorBB) over g in ('Strikeout', 'Walk'), true) new_pa
            from positioned window g as (partition by game_anon_id order by pitch_seq))
        select *, game_anon_id || '-' || sum(new_pa::int) over (partition by game_anon_id order by pitch_seq) pa_id
        from marked""")
    con.execute(f"""
        create or replace table sequence_features as
        with ordered as (
            select *,
                   row_number() over pa pitch_of_pa,
                   lag(pitch_class) over pa prev_class,
                   lag(RelSpeed) over pa prev_velo,
                   lag(PlateLocHeight) over pa prev_height,
                   lag(PlateLocSide) over pa prev_side,
                   lag(decision_height) over pa prev_decision_height,
                   lag(decision_side) over pa prev_decision_side,
                   lag(pitcher_anon_id) over pa prev_pitcher,
                   row_number() over (partition by game_anon_id, pitcher_anon_id order by pitch_seq) pitcher_pitch_count,
                   min(Inning) over (partition by game_anon_id, pitcher_anon_id) entry_inning
            from sequence_base window pa as (partition by pa_id order by pitch_seq)),
        orders as (
            select pa_id, pitcher_anon_id, batter_anon_id, dense_rank() over (partition by game_anon_id, pitcher_anon_id, batter_anon_id
                                             order by min(pitch_seq)) times_through_order
            from sequence_base group by pa_id, game_anon_id, pitcher_anon_id, batter_anon_id)
        select o.PitchUID, o.pa_id, o.pitch_of_pa, o.pitcher_pitch_count,
               case when max(t.times_through_order) over (partition by o.game_anon_id, o.pitcher_anon_id, o.batter_anon_id)
                         <= {MAX_PLAUSIBLE_TIMES_THROUGH_ORDER} then t.times_through_order end times_through_order,
               case when o.entry_inning = 1 then 'abridor' else 'relevista' end pitcher_role,
               o.entry_inning,
               case when o.prev_pitcher = o.pitcher_anon_id then o.prev_class end prev_pitch_class,
               case when o.prev_pitcher = o.pitcher_anon_id then o.pitch_class = o.prev_class end same_as_prev,
               case when o.prev_pitcher = o.pitcher_anon_id then o.RelSpeed - o.prev_velo end velo_diff_vs_prev,
               case when o.prev_pitcher = o.pitcher_anon_id
                    then sqrt((o.PlateLocHeight - o.prev_height)^2 + (o.PlateLocSide - o.prev_side)^2) end plate_dist_vs_prev,
               case when o.prev_pitcher = o.pitcher_anon_id
                    then sqrt((o.decision_height - o.prev_decision_height)^2
                              + (o.decision_side - o.prev_decision_side)^2) end tunnel_dist_vs_prev
        from ordered o join orders t using (pa_id, pitcher_anon_id, batter_anon_id)""")


def sequence_summary(con) -> dict:
    return {
        "turnos": rows(con, """
            select count(distinct pa_id) turnos,
                   avg(case when pitch_of_pa = 1 then (Balls = 0 and Strikes = 0)::int end) primer_pitch_en_0_0,
                   avg(case when pitch_of_pa > 1 then (Balls + Strikes > 0 or PitchCall like 'Foul%')::int end) resto_con_conteo_avanzado
            from features"""),
        "roles": rows(con, """
            select pitcher_role, count(distinct game_anon_id || pitcher_anon_id) salidas, count(*) pitches,
                   median(entry_inning) entrada_mediana
            from features group by 1 order by 1"""),
        "vuelta_al_orden": rows(con, """
            select times_through_order, count(*) pitches from features group by 1 order by 1"""),
        "tunneling": rows(con, """
            select same_as_prev mismo_tipo, count(*) pares,
                   median(tunnel_dist_vs_prev) separacion_decision_ft, median(plate_dist_vs_prev) separacion_plato_ft
            from features where tunnel_dist_vs_prev is not null group by 1 order by 1"""),
        "efecto_tunneling": rows(con, """
            with d as (
                select is_whiff, is_swing, plate_dist_vs_prev - tunnel_dist_vs_prev separacion_despues,
                       ntile(4) over (order by plate_dist_vs_prev - tunnel_dist_vs_prev) cuartil
                from features
                where usable_stuff and is_swing is not null and same_as_prev = false
                  and tunnel_dist_vs_prev is not null)
            select cuartil, median(separacion_despues) separacion_despues_ft,
                   sum(is_whiff) / sum(is_swing) whiff_por_swing, count(*) pitches
            from d group by 1 order by 1"""),
        "efecto_vuelta_al_orden": rows(con, """
            select times_through_order, sum(is_whiff) / sum(is_swing) whiff_por_swing,
                   avg(case when is_ball_in_play = 1 then is_hit end) hit_por_bola_en_juego, count(*) pitches
            from features
            where usable_stuff and is_swing is not null and times_through_order <= 3
            group by 1 order by 1"""),
        "efecto_repetir": rows(con, """
            select same_as_prev mismo_tipo, sum(is_whiff) / sum(is_swing) whiff_por_swing, count(*) pitches
            from features where usable_stuff and is_swing is not null and same_as_prev is not null
            group by 1 order by 1"""),
        "cobertura": rows(con, """
            select avg((tunnel_dist_vs_prev is not null)::int) con_tunneling,
                   avg((pitch_of_pa > 1)::int) pitches_con_anterior
            from features"""),
    }


# ─── Ensamble ─────────────────────────────────────────────────────────────────────────────

def create_classified(con, cut: float):
    con.execute(f"""
        create or replace table classified as
        select s.*, coalesce(r.candidate, s.pitch_group) pitch_class,
               r.candidate is not null and r.candidate <> s.pitch_group as flag_reclasificado,
               case when coalesce(r.candidate, s.pitch_group) = 'Slider' and s.hb_sea_level is not null
                    then case when s.hb_sea_level <= {cut} then 'sweeper' else 'slider' end end as slider_shape
        from shaped s left join reassigned r using (PitchUID)""")


def create_features(con, fits: dict):
    plate_side_arm = "PlateLocSide * case pitcher_hand when 'Left' then -1 else 1 end"
    con.execute(f"""
        create or replace table features as
        select c.*,
               sqrt(InducedVertBreak^2 + hb_arm_side^2) total_break,
               sqrt(ivb_sea_level^2 + hb_sea_level^2) total_break_sea_level,
               sqrt(ivb_sea_level^2 + hb_sea_level^2) / nullif(SpinRate / RelSpeed, 0) magnus_dependence,
               VertApprAngle - ({angle_case(fits, 'vaa', 'PlateLocHeight')}) vaa_rel,
               horz_appr_angle_arm - ({angle_case(fits, 'haa', plate_side_arm)}) haa_rel,
               r.fb_in_game,
               RelSpeed - r.ref_velo velo_diff_vs_fb,
               InducedVertBreak - r.ref_ivb ivb_diff_vs_fb,
               hb_arm_side - r.ref_hb hb_diff_vs_fb,
               ((spin_axis_arm - r.ref_axis + 540) % 360) - 180 axis_diff_vs_fb,
               sqrt((RelHeight - r.ref_rel_height)^2 + (rel_side_arm - r.ref_rel_side)^2) release_dist_vs_fb,
               Extension - r.ref_extension extension_diff_vs_fb,
               u.pitch_usage_pct, u.arsenal_size,
               q.* exclude (PitchUID),
               pitcher_hand = batter_side platoon_same_side,
               {zone_expression()} as zone
        from classified c
        left join fb_reference r using (PitchUID)
        left join usage u using (pitcher_anon_id, year, pitch_class)
        left join sequence_features q using (PitchUID)
        order by c.pitch_seq""")


def validation_summary(con, cut: float) -> dict:
    return {
        "sweeper_por_altitud": rows(con, f"""
            select altitude_category altitud, count(*) sliders,
                   avg((hb_arm_side <= {cut})::int) pct_sweeper_observado,
                   avg((slider_shape = 'sweeper')::int) pct_sweeper_nivel_del_mar
            from features where usable_stuff and pitch_class = 'Slider' and altitude_category is not null
              and hb_sea_level is not null
            group by 1 order by 1"""),
        "sweeper_mismo_pitcher": rows(con, f"""
            with g as (
                select pitcher_anon_id, altitude_category,
                       median(hb_arm_side) <= {cut} sweeper_observado,
                       median(hb_sea_level) <= {cut} sweeper_nivel_del_mar
                from features where usable_stuff and pitch_class = 'Slider'
                  and altitude_category in ('No Altitude', 'Extreme Altitude')
                group by all having count(*) >= {MIN_PITCHES_FOR_CENTROID})
            select count(*) pitchers,
                   avg((m.sweeper_observado = e.sweeper_observado)::int) misma_etiqueta_observado,
                   avg((m.sweeper_nivel_del_mar = e.sweeper_nivel_del_mar)::int) misma_etiqueta_nivel_del_mar
            from g m join g e using (pitcher_anon_id)
            where m.altitude_category = 'No Altitude' and e.altitude_category = 'Extreme Altitude'"""),
        "forma_mismo_pitcher": rows(con, """
            with g as (
                select pitcher_anon_id, pitch_class, altitude_category,
                       median(InducedVertBreak) ivb, median(hb_arm_side) hb,
                       median(ivb_sea_level) ivb_sl, median(hb_sea_level) hb_sl
                from features where usable_stuff and altitude_category in ('No Altitude', 'Extreme Altitude')
                group by all having count(*) >= 30)
            select m.pitch_class, count(*) pares,
                   median(e.ivb - m.ivb) delta_ivb_observado, median(e.ivb_sl - m.ivb_sl) delta_ivb_nivel_del_mar,
                   median(e.hb - m.hb) delta_hb_observado, median(e.hb_sl - m.hb_sl) delta_hb_nivel_del_mar
            from g m join g e using (pitcher_anon_id, pitch_class)
            where m.altitude_category = 'No Altitude' and e.altitude_category = 'Extreme Altitude'
            group by 1 having count(*) >= 20 order by 2 desc"""),
        "angulos_relativos": rows(con, """
            select pitch_class,
                   corr(vaa_rel, PlateLocHeight) corr_vaa_rel_altura,
                   corr(VertApprAngle, PlateLocHeight) corr_vaa_altura,
                   corr(haa_rel, PlateLocSide * case pitcher_hand when 'Left' then -1 else 1 end) corr_haa_rel_lado,
                   stddev(vaa_rel) sd_vaa_rel
            from features where usable_stuff and split = 'holdout' and pitch_class <> 'Other'
            group by 1 order by 1"""),
        "vaa_rel_por_decil_de_altura": rows(con, """
            with d as (select ntile(10) over (order by PlateLocHeight) decil, vaa_rel
                       from features where usable_stuff and split = 'holdout' and pitch_class = 'Four-Seam'
                         and PlateLocHeight > 0)
            select decil, avg(vaa_rel) media_vaa_rel from d group by 1 order by 1"""),
        "recta_principal": rows(con, """
            select primary_fb_type, count(distinct pitcher_anon_id) pitchers
            from features where primary_fb_type is not null group by 1 order by 2 desc"""),
        "cobertura": rows(con, """
            select count(*) pitches_usables,
                   avg((velo_diff_vs_fb is not null)::int) con_diferencias_arsenal,
                   avg((fb_in_game is not null)::int) con_rectas_en_el_juego,
                   avg((air_ratio is not null)::int) con_air_ratio,
                   avg((vaa_rel is not null)::int) con_vaa_rel,
                   avg((magnus_dependence is not null)::int) con_magnus_dependence,
                   avg((zone is not null)::int) con_zona
            from features where usable_stuff"""),
        "zona_contra_bandera_dataset": rows(con, """
            select (zone not like 'fuera%') dentro_cuadricula, in_strike_zone, count(*) pitches
            from features where zone is not null and in_strike_zone is not null
            group by all order by all"""),
        "magnus_por_tipo": rows(con, """
            select pitch_class, median(magnus_dependence) mediana, quantile_cont(magnus_dependence, 0.1) p10,
                   quantile_cont(magnus_dependence, 0.9) p90
            from features where usable_stuff and pitch_class <> 'Other' group by 1 order by 2 desc"""),
    }


def main():
    con = duckdb.connect()
    con.execute(f"create or replace view clean as select * from '{CLEAN_PARQUET}'")

    create_air_ratio(con)
    exponent = estimate_air_exponent(con)
    create_sea_level_shape(con, exponent)
    reclass = reclassify_by_shape(con)
    sweeper = sweeper_cut(con)
    create_classified(con, sweeper["corte_usado_in"])
    fits = fit_relative_angles(con)
    mark_primary_fastball(con)
    shrinkage = estimate_shrinkage(con)
    create_arsenal(con, shrinkage)
    create_sequence(con)
    create_features(con, fits)

    FEATURES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"copy features to '{FEATURES_PARQUET}' (format parquet, compression zstd)")

    summary = {
        "aire": air_summary(con),
        "exponente_k": exponent,
        "reclasificacion": reclass,
        "sweeper": sweeper,
        "encogimiento": shrinkage,
        "angulos_ajuste": {cls: {a: [round(v, 5) for v in c] for a, c in f.items()} for cls, f in fits.items()},
        "validacion": validation_summary(con, sweeper["corte_usado_in"]),
        "secuencia": sequence_summary(con),
        "columnas": int(scalar(con, "select count(*) from (describe features)")),
        "pitches": int(scalar(con, "select count(*) from features")),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({key: summary[key] for key in ("secuencia", "columnas", "pitches")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
