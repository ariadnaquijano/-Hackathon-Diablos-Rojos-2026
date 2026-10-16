"""Etapa 3: el target de carreras esperadas por pitch (xRV).

Plan validado en docs/03_plan_target.md. Pasos:

1. Valor en carreras de cada desenlace: regresión sobre medias entradas completas de 2024–2025,
   para la liga (versión neutral) y por altitud (versión local).
2. Valor de cada conteo: promedio del desenlace final de los turnos que pasaron por él.
3. Valor esperado de cada bola en juego según su contacto, con predicciones cruzadas para que el
   resultado real de un batazo no entre en su propio valor esperado.
4. Valor de cada pitch: conteo después − conteo antes, o desenlace − conteo antes si termina el turno.
5. Regla fijada antes de probar: entre velocidad + ángulo y velocidad + ángulo + dirección, se queda
   la versión cuyo promedio por pitcher en 2024–2025 prediga mejor su valor real en 2026.

Escribe data/processed/dataset_modelo.parquet (features + target) y reportes/etapa_03_resumen.json.

Uso:
    python src/target.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold

from config import FEATURES_PARQUET, HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR

SUMMARY_JSON = REPORTS_DIR / "etapa_03_resumen.json"
RANDOM_SEED = 2026
BOOTSTRAP_SAMPLES = 1000
CROSS_FIT_FOLDS = 5
# Pitchers con al menos esta muestra en cada periodo entran a las pruebas por pitcher.
MIN_PITCHES_PER_PERIOD = 300

LEAGUE = "liga"
SEA_LEVEL = "No Altitude"
ALTITUDES = ("No Altitude", "Medium Altitude", "Extreme Altitude")
ALTITUDE_CODE = {altitude: code for code, altitude in enumerate(ALTITUDES)}

# Desenlace del turno según las columnas que lo registran.
PA_EVENT = """
    case when PitchCall = 'HitByPitch' then 'HBP'
         when KorBB = 'Strikeout' or play_result = 'Strikeout' then 'K'
         when KorBB = 'Walk' or play_result = 'Walk' then 'BB'
         when PitchCall = 'InPlay' then case play_result
             when 'Single' then '1B' when 'Double' then '2B' when 'Triple' then '3B'
             when 'HomeRun' then 'HR' when 'Error' then 'E' when 'Sacrifice' then 'SAC'
             when 'FieldersChoice' then 'FC' else 'OUT' end
    end"""
EVENTS = ["1B", "2B", "3B", "HR", "BB", "HBP", "K", "OUT", "E", "SAC", "FC"]
# Para el pitcher, error, sacrificio y bola ocupada son outs: no se le cobra la defensa.
TARGET_EVENT = {"E": "OUT", "SAC": "OUT", "FC": "OUT"}

# Qué hizo el pitch con el turno, deducido de su resultado y no de la fila siguiente.
PITCH_EVENT = """
    case when PitchCall in ('BallCalled', 'BallinDirt') then if(Balls = 3, 'BB', 'BALL')
         when PitchCall in ('StrikeCalled', 'StrikeSwinging') then if(Strikes = 2, 'K', 'STRIKE')
         when PitchCall like 'Foul%' then 'FOUL'
         when PitchCall = 'HitByPitch' then 'HBP'
         when PitchCall = 'InPlay' then 'BIP'
    end"""

BIP_FEATURE_SETS = {
    "ev_angulo": ["ExitSpeed", "Angle"],
    "ev_angulo_direccion": ["ExitSpeed", "Angle", "spray_pull"],
}


# ---------- 1. Valor de cada desenlace ----------

def create_events(con):
    con.sql(f"""
        create table events as
        select *, {PA_EVENT} as pa_event, {PITCH_EVENT} as pitch_event
        from '{FEATURES_PARQUET}'""")


def half_innings(con) -> pd.DataFrame:
    """Medias entradas con su conteo de desenlaces. Completa = empieza con 0 outs y termina con 3."""
    counts = ", ".join(f"count(*) filter (where pa_event = '{e}') as \"{e}\"" for e in EVENTS)
    return con.sql(f"""
        select game_anon_id, Inning, "Top/Bottom", year, any_value(altitude_category) altitude,
               arg_min(Outs, pitch_seq) = 0
                 and arg_max(Outs + coalesce(OutsOnPlay, 0), pitch_seq) >= 3 as complete,
               sum(RunsScored) runs, {counts}
        from events
        group by game_anon_id, Inning, "Top/Bottom", year""").df()


def linear_weights(halves: pd.DataFrame) -> dict:
    """Carreras por desenlace: regresión de las carreras de cada media entrada sobre sus desenlaces."""
    weights, _, _, _ = np.linalg.lstsq(halves[EVENTS].to_numpy(float), halves.runs.to_numpy(float), rcond=None)
    return {event: round(float(w), 4) for event, w in zip(EVENTS, weights)}


def estimate_outcome_values(halves: pd.DataFrame) -> dict:
    train = halves[halves.complete & (halves.year < HOLDOUT_SEASON)]
    scopes = {LEAGUE: train} | {altitude: train[train.altitude == altitude] for altitude in ALTITUDES}
    return {scope: {"medias_entradas": len(subset),
                    "carreras_por_media_entrada": round(float(subset.runs.mean()), 4),
                    "pesos_regresion": linear_weights(subset)}
            for scope, subset in scopes.items()}


def create_outcome_values(con, outcome_values: dict):
    """Tabla (ámbito, desenlace, carreras) con error, sacrificio y bola ocupada valuados como out."""
    rows = [(scope, event, info["pesos_regresion"][TARGET_EVENT.get(event, event)])
            for scope, info in outcome_values.items() for event in EVENTS]
    con.sql("create table outcome_value(scope varchar, pa_event varchar, run_value double)")
    con.executemany("insert into outcome_value values (?, ?, ?)", rows)


# ---------- 2. Valor de cada conteo ----------

def create_count_values(con):
    """Promedio del desenlace final de los turnos de 2024–2025 que pasaron por cada conteo.

    Neutral: todos los turnos con pesos de la liga. Local: los turnos de cada altitud con sus pesos.
    """
    con.sql(f"""
        create table pa_outcome as
        select pa_id, any_value(altitude_category) altitude, max(pa_event) pa_event
        from events
        where year < {HOLDOUT_SEASON}
        group by pa_id
        having count(pa_event) = 1""")
    con.sql(f"""
        create table count_value as
        with valued as (
            select e.Balls, e.Strikes, '{LEAGUE}' as scope, v.run_value
            from events e join pa_outcome p using (pa_id)
            join outcome_value v on v.scope = '{LEAGUE}' and v.pa_event = p.pa_event
            union all
            select e.Balls, e.Strikes, p.altitude, v.run_value
            from events e join pa_outcome p using (pa_id)
            join outcome_value v on v.scope = p.altitude and v.pa_event = p.pa_event)
        select scope, Balls, Strikes, avg(run_value) run_value, count(*) pitches
        from valued
        group by scope, Balls, Strikes""")


# ---------- 3. Valor esperado de la bola en juego ----------

def load_balls_in_play(con) -> pd.DataFrame:
    """Bolas en juego con el valor real de su desenlace en las dos versiones."""
    return con.sql(f"""
        select e.pitch_seq, e.year, e.game_anon_id, e.pitcher_anon_id, e.altitude_category,
               e.ExitSpeed, e.Angle, e.hit_type,
               e.Direction * case e.batter_side when 'Right' then -1 else 1 end spray_pull,
               neutral.run_value value_neutral, local.run_value value_local
        from events e
        join outcome_value neutral on neutral.scope = '{LEAGUE}' and neutral.pa_event = e.pa_event
        left join outcome_value local on local.scope = e.altitude_category and local.pa_event = e.pa_event
        where e.pitch_event = 'BIP'
        order by e.pitch_seq""").df()


def new_contact_model():
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, min_samples_leaf=200,
                                         random_state=RANDOM_SEED)


def cross_fit(frame: pd.DataFrame, fit_mask: np.ndarray, features: list[str], label: str) -> np.ndarray:
    """Predicciones donde ninguna fila usa un modelo que vio su propio resultado.

    Las filas de entrenamiento reciben la predicción del pliegue que las dejó fuera (agrupando por
    juego); el resto, la del modelo entrenado con todas.
    """
    predictions = np.full(len(frame), np.nan)
    fit_rows = np.flatnonzero(fit_mask)
    X, y = frame[features], frame[label].to_numpy()
    for train_idx, out_idx in GroupKFold(CROSS_FIT_FOLDS).split(fit_rows, groups=frame.game_anon_id.to_numpy()[fit_rows]):
        model = new_contact_model().fit(X.iloc[fit_rows[train_idx]], y[fit_rows[train_idx]])
        predictions[fit_rows[out_idx]] = model.predict(X.iloc[fit_rows[out_idx]])
    rest = np.flatnonzero(~fit_mask)
    predictions[rest] = new_contact_model().fit(X.iloc[fit_rows], y[fit_rows]).predict(X.iloc[rest])
    return predictions


def untracked_values(bip: pd.DataFrame, tracked: np.ndarray, train: np.ndarray) -> pd.DataFrame:
    """Valor de las bolas sin velocidad de salida: el promedio real de su grupo en 2024–2025.

    Toques por un lado y el resto por otro. Neutral, a nivel del mar; local, por altitud.
    """
    is_bunt = bip.hit_type.eq("Bunt")
    base = bip[~tracked & train]
    neutral = base[base.altitude_category == SEA_LEVEL].groupby(is_bunt).value_neutral.mean()
    local = base.groupby([is_bunt, "altitude_category"]).value_local.mean()
    return pd.DataFrame({
        "neutral": is_bunt.map(neutral).to_numpy(),
        "local": [local.get((bunt, altitude), np.nan) for bunt, altitude in zip(is_bunt, bip.altitude_category)],
    })


def expected_bip_values(bip: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Valor esperado de cada bola en juego, para cada conjunto de variables y versión."""
    tracked = bip[["ExitSpeed", "Angle"]].notna().all(axis=1).to_numpy()
    train = (bip.year < HOLDOUT_SEASON).to_numpy()
    test = ~train & tracked
    sea_level = (bip.altitude_category == SEA_LEVEL).to_numpy()
    with_altitude = bip.altitude_category.notna().to_numpy()
    bip = bip.assign(altitude_code=bip.altitude_category.map(ALTITUDE_CODE))
    fallback = untracked_values(bip, tracked, train)

    expected, r2 = {}, {}
    for name, features in BIP_FEATURE_SETS.items():
        neutral = cross_fit(bip, tracked & train & sea_level, features, "value_neutral")
        local = cross_fit(bip, tracked & train & with_altitude, features + ["altitude_code"], "value_local")
        local[~with_altitude] = np.nan
        expected[f"xbip_neutral_{name}"] = np.where(tracked, neutral, fallback.neutral)
        expected[f"xbip_local_{name}"] = np.where(tracked, local, fallback.local)
        r2[name] = {
            "neutral_nivel_del_mar": round(float(r2_score(bip.value_neutral[test & sea_level], neutral[test & sea_level])), 4),
            "local": round(float(r2_score(bip.value_local[test & with_altitude], local[test & with_altitude])), 4),
        }
    untracked = {"bolas_sin_velocidad": int((~tracked).sum()),
                 "valor_neutral_toque": round(float(fallback.neutral[bip.hit_type.eq("Bunt") & ~tracked].mean()), 4),
                 "valor_neutral_resto": round(float(fallback.neutral[~bip.hit_type.eq("Bunt") & ~tracked].mean()), 4)}
    return pd.DataFrame({"pitch_seq": bip.pitch_seq} | expected), {"r2_2026": r2, "sin_velocidad_salida": untracked}


# ---------- 4. Valor de cada pitch ----------

def create_pitch_values(con, expected: pd.DataFrame):
    """Valor real y esperado de cada pitch, en las dos versiones y para cada conjunto de variables."""
    con.register("expected_bip", expected)
    versions = {"neutral": f"'{LEAGUE}'", "local": "e.altitude_category"}
    terms = []
    for version in versions:
        before = f"cb_{version}.run_value"
        after = f"ca_{version}.run_value"
        outcome = f"ov_{version}.run_value"
        terms.append(f"""
            case when e.pitch_event in ('BALL', 'STRIKE', 'FOUL') then {after} - {before}
                 when e.pitch_event in ('BB', 'K', 'HBP', 'BIP') then {outcome} - {before} end as rv_real_{version}""")
        for name in BIP_FEATURE_SETS:
            terms.append(f"""
            case when e.pitch_event = 'BIP' then x.xbip_{version}_{name} - {before}
                 else rv_real_{version} end as xrv_{version}_{name}""")
    joins = []
    for version, scope in versions.items():
        joins.append(f"""
        left join count_value cb_{version} on cb_{version}.scope = {scope}
             and cb_{version}.Balls = e.Balls and cb_{version}.Strikes = e.Strikes
        left join count_value ca_{version} on ca_{version}.scope = {scope}
             and ca_{version}.Balls = e.Balls + (e.pitch_event = 'BALL')::int
             and ca_{version}.Strikes = e.Strikes + (e.pitch_event = 'STRIKE' or (e.pitch_event = 'FOUL' and e.Strikes < 2))::int
        left join outcome_value ov_{version} on ov_{version}.scope = {scope}
             and ov_{version}.pa_event = case when e.pitch_event = 'BIP' then e.pa_event else e.pitch_event end""")
    con.sql(f"""
        create table pitch_values as
        select e.pitch_seq, cb_neutral.run_value count_value_before, {",".join(terms)}
        from events e {"".join(joins)}
        left join expected_bip x using (pitch_seq)""")


# ---------- 5. Elección de variables del contacto ----------

def season_centered(column: str) -> str:
    """Pitches con el valor menos el promedio de su temporada.

    El ambiente de carreras cambia entre temporadas (2025 tuvo más carreras que 2024), y Stuff+ se mide
    contra el promedio de su temporada; sin centrar, el promedio de un pitcher dependería de en qué
    años lanzó.
    """
    return f"""
        select pitcher_anon_id, year, pitch_seq, {column} - avg({column}) over (partition by year) as centered
        from events join pitch_values using (pitch_seq)"""


def pitcher_periods(con, column: str) -> pd.DataFrame:
    """Valor por 100 pitches sobre el promedio de la temporada, de cada pitcher en 2024–2025 y en 2026."""
    return con.sql(f"""
        select pitcher_anon_id, year = {HOLDOUT_SEASON} as holdout,
               100 * avg(centered) per_100, count(centered) pitches
        from ({season_centered(column)})
        group by all""").df()


def persistence(con, predictor: str, outcome: str = "rv_real_neutral") -> pd.DataFrame:
    """Pitchers con muestra en ambos periodos: su valor de 2024–2025 contra su valor real de 2026."""
    before = pitcher_periods(con, predictor).query("not holdout and pitches >= @MIN_PITCHES_PER_PERIOD")
    after = pitcher_periods(con, outcome).query("holdout and pitches >= @MIN_PITCHES_PER_PERIOD")
    return before.merge(after, on="pitcher_anon_id", suffixes=("_antes", "_2026"))


def bootstrap_correlation_difference(a: pd.DataFrame, b: pd.DataFrame) -> list[float]:
    """IC 95 % de r(a) − r(b), remuestreando los mismos pitchers en ambos."""
    rng = np.random.default_rng(RANDOM_SEED)
    xa, ya = a.per_100_antes.to_numpy(), a.per_100_2026.to_numpy()
    xb, yb = b.per_100_antes.to_numpy(), b.per_100_2026.to_numpy()
    diffs = []
    for _ in range(BOOTSTRAP_SAMPLES):
        idx = rng.integers(0, len(a), len(a))
        diffs.append(np.corrcoef(xa[idx], ya[idx])[0, 1] - np.corrcoef(xb[idx], yb[idx])[0, 1])
    low, high = np.percentile(diffs, [2.5, 97.5])
    return [round(float(low), 4), round(float(high), 4)]


def split_half_reliability(con, column: str) -> float:
    """Correlación entre dos mitades al azar de los pitches de 2024–2025 de cada pitcher."""
    halves = con.sql(f"""
        select pitcher_anon_id, hash(pitch_seq, {RANDOM_SEED}) % 2 as half, avg(centered) as half_value, count(centered) as pitches
        from ({season_centered(column)})
        where year < {HOLDOUT_SEASON}
        group by all""").df()
    wide = halves[halves.pitches >= MIN_PITCHES_PER_PERIOD // 2].pivot(index="pitcher_anon_id", columns="half", values="half_value").dropna()
    return round(float(np.corrcoef(wide[0], wide[1])[0, 1]), 4)


def choose_bip_features(con) -> dict:
    """Aplica la regla fijada: gana el xRV de 2024–2025 que mejor predice el valor real de 2026."""
    real = persistence(con, "rv_real_neutral")
    candidates = {name: persistence(con, f"xrv_neutral_{name}") for name in BIP_FEATURE_SETS}
    pitchers = set(real.pitcher_anon_id).intersection(*(c.pitcher_anon_id for c in candidates.values()))

    def aligned(frame):
        return frame[frame.pitcher_anon_id.isin(pitchers)].sort_values("pitcher_anon_id").reset_index(drop=True)

    real = aligned(real)
    candidates = {name: aligned(frame) for name, frame in candidates.items()}
    correlation = {name: round(float(np.corrcoef(f.per_100_antes, f.per_100_2026)[0, 1]), 4)
                   for name, f in {**candidates, "real": real}.items()}
    chosen = max(BIP_FEATURE_SETS, key=lambda name: correlation[name])
    other = next(name for name in BIP_FEATURE_SETS if name != chosen)
    return {
        "pitchers": len(real),
        "r_con_valor_real_2026": correlation,
        "elegido": chosen,
        "ic95_elegido_menos_otro": bootstrap_correlation_difference(candidates[chosen], candidates[other]),
        "ic95_elegido_menos_real": bootstrap_correlation_difference(candidates[chosen], real),
        "confiabilidad_mitades": {name: split_half_reliability(con, f"xrv_neutral_{name}") for name in BIP_FEATURE_SETS}
                                 | {"real": split_half_reliability(con, "rv_real_neutral")},
    }


# ---------- Salida ----------

def write_model_dataset(con, chosen: str):
    con.sql(f"""
        copy (
            select e.*, p.count_value_before, p.rv_real_neutral, p.rv_real_local,
                   p.xrv_neutral_{chosen} as xrv_neutral, p.xrv_local_{chosen} as xrv_local,
                   p.xrv_neutral_{chosen} is null as flag_sin_target,
                   p.xrv_local_{chosen} is null and p.xrv_neutral_{chosen} is not null as flag_sin_target_local
            from events e join pitch_values p using (pitch_seq)
            order by e.pitch_seq)
        to '{MODEL_PARQUET}' (format parquet)""")


def consistency_checks(con) -> dict:
    """El fin de turno deducido del pitch debe coincidir con el registrado, y el valor del turno debe sumar.

    La suma de los pitches de un turno es desenlace − conteo inicial, salvo cuando el conteo registrado
    salta (falta un pitch): cada pitch se valúa con su propio conteo, así que el salto no se le cobra a nadie.
    """
    row = con.sql("""
        select count(*) filter (where pitch_event in ('BB', 'K') and pa_event is distinct from pitch_event) fin_distinto,
               count(*) filter (where pitch_event in ('BB', 'K')) fines_ponche_base
        from events""").df().iloc[0]
    sums = con.sql("""
        with p as (
            select e.pa_id, e.pitch_seq, e.pitch_event, e.Balls, e.Strikes, v.rv_real_neutral, v.count_value_before,
                   lead(e.Balls) over w next_balls, lead(e.Strikes) over w next_strikes, lead(e.pa_id) over w next_pa
            from events e join pitch_values v using (pitch_seq)
            window w as (order by e.pitch_seq)),
        pa as (
            select sum(rv_real_neutral) total,
                   arg_max(rv_real_neutral + count_value_before, pitch_seq) - arg_min(count_value_before, pitch_seq) expected,
                   count(*) filter (where next_pa = pa_id and pitch_event in ('BALL', 'STRIKE', 'FOUL') and (
                       next_balls <> Balls + (pitch_event = 'BALL')::int
                       or next_strikes <> Strikes + (pitch_event = 'STRIKE' or (pitch_event = 'FOUL' and Strikes < 2))::int)) > 0 jumps,
                   arg_max(pitch_event, pitch_seq) in ('BB', 'K', 'HBP', 'BIP') ends_in_outcome,
                   count(*) = count(rv_real_neutral) all_valued
            from p group by pa_id)
        select count(*) turnos,
               count(*) filter (where abs(total - expected) < 1e-9) suman_exacto,
               count(*) filter (where abs(total - expected) >= 1e-9 and jumps) no_suman_por_salto_de_conteo,
               count(*) filter (where abs(total - expected) >= 1e-9 and not jumps) no_suman_sin_explicacion
        from pa where ends_in_outcome and all_valued""").df().iloc[0]
    return {"fin_de_turno_distinto_al_registrado": int(row.fin_distinto),
            "fines_por_ponche_o_base": int(row.fines_ponche_base),
            "suma_por_turno": {key: int(value) for key, value in sums.items()}}


def target_coverage(con) -> dict:
    row = con.sql(f"""
        select count(*) pitches,
               count(*) filter (where flag_sin_target) sin_target,
               count(*) filter (where flag_sin_target_local) sin_target_local,
               avg(xrv_neutral) media_xrv, stddev(xrv_neutral) sd_xrv
        from '{MODEL_PARQUET}'""").df().iloc[0]
    return {key: (round(float(value), 5) if isinstance(value, float) else int(value)) for key, value in row.items()}


def count_value_table(con) -> list[dict]:
    return con.sql("select scope, Balls, Strikes, round(run_value, 4) run_value from count_value order by all").df().to_dict(orient="records")


def main():
    con = duckdb.connect()
    create_events(con)
    outcome_values = estimate_outcome_values(half_innings(con))
    create_outcome_values(con, outcome_values)
    create_count_values(con)
    expected, contact = expected_bip_values(load_balls_in_play(con))
    create_pitch_values(con, expected)
    selection = choose_bip_features(con)
    write_model_dataset(con, selection["elegido"])
    summary = {
        "valor_desenlaces": outcome_values,
        "desenlaces_valuados_como_out": TARGET_EVENT,
        "valor_conteos": count_value_table(con),
        "bola_en_juego": contact,
        "eleccion_variables_contacto": selection,
        "chequeos": consistency_checks(con),
        "cobertura": target_coverage(con),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({k: summary[k] for k in ("bola_en_juego", "eleccion_variables_contacto", "chequeos", "cobertura")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
