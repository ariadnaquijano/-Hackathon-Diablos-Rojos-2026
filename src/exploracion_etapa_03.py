"""Evidencia para el plan de la etapa 3: el target de carreras esperadas.

Responde, antes de construir nada, si los datos alcanzan para:
1. Reconstruir medias entradas completas (para estimar el valor en carreras de cada desenlace).
2. Estimar ese valor por regresión, para la liga y por altitud.
3. Dar valor a cada conteo de bolas y strikes.
4. Confiar en el conteo registrado pitch a pitch.
5. Predecir el valor de una bola en juego con su velocidad de salida, ángulo y dirección.

Todo con datos de 2024–2025 salvo la prueba del punto 5, que evalúa en 2026.
Escribe reportes/etapa_03_exploracion.json, que cita docs/03_plan_target.md.

Uso:
    python src/exploracion_etapa_03.py
"""

import json

import duckdb
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score

from config import HOLDOUT_SEASON, REPORTS_DIR
from target import ALTITUDES, EVENTS, TARGET_EVENT, create_events, half_innings, linear_weights

SUMMARY_JSON = REPORTS_DIR / "etapa_03_exploracion.json"
RANDOM_SEED = 2026


def weights_summary(halves) -> dict:
    train = halves[halves.complete & (halves.year < HOLDOUT_SEASON)]
    by_altitude = {}
    for altitude in ALTITUDES:
        subset = train[train.altitude == altitude]
        by_altitude[altitude] = {"medias_entradas": len(subset), "carreras_por_media_entrada": round(float(subset.runs.mean()), 3),
                                 "pesos": linear_weights(subset)}
    return {
        "medias_entradas": len(halves),
        "completas": int(halves.complete.sum()),
        "pct_completas": round(float(halves.complete.mean()), 4),
        "liga": {"medias_entradas": len(train), "carreras_por_media_entrada": round(float(train.runs.mean()), 3),
                 "pesos": linear_weights(train)},
        "por_altitud": by_altitude,
    }


def count_values(con, weights: dict) -> dict:
    """Valor de cada conteo: promedio del desenlace final de los turnos que pasaron por él."""
    pairs = ", ".join(f"('{e}', {weights[TARGET_EVENT.get(e, e)]})" for e in EVENTS)
    con.sql(f"create table event_value(pa_event varchar, run_value double); insert into event_value values {pairs}")
    con.sql(f"""
        create table pa_value as
        select pa_id, max(v.run_value) run_value
        from events e left join event_value v using (pa_event)
        where e.year < {HOLDOUT_SEASON}
        group by pa_id""")
    rows = con.sql("""
        select Balls, Strikes, avg(p.run_value) run_value, count(*) pitches
        from events e join pa_value p using (pa_id)
        where p.run_value is not null and Balls <= 3 and Strikes <= 2
        group by Balls, Strikes order by Balls, Strikes""").df()
    turns = con.sql("select count(*) total, count(run_value) with_outcome from pa_value").df().iloc[0]
    return {"turnos_entrenamiento": int(turns.total), "turnos_con_desenlace": int(turns.with_outcome),
            "por_conteo": rows.round(4).to_dict(orient="records")}


def count_consistency(con) -> dict:
    """¿El conteo del pitch siguiente coincide con lo que dice el PitchCall del anterior?"""
    row = con.sql("""
        with p as (
            select Balls, Strikes, pa_id,
                   lag(Balls) over w prev_balls, lag(Strikes) over w prev_strikes,
                   lag(PitchCall) over w prev_call, lag(pa_id) over w prev_pa
            from events window w as (partition by game_anon_id order by pitch_seq))
        select count(*) filter (where pa_id = prev_pa) transiciones,
               count(*) filter (where pa_id = prev_pa and (
                   (prev_call in ('BallCalled', 'BallinDirt') and (Balls <> prev_balls + 1 or Strikes <> prev_strikes))
                or (prev_call in ('StrikeCalled', 'StrikeSwinging') and (Strikes <> prev_strikes + 1 or Balls <> prev_balls))
                or (prev_call like 'Foul%' and Strikes <> least(prev_strikes + 1, 2)))) inconsistentes
        from p""").df().iloc[0]
    return {"transiciones": int(row.transiciones), "inconsistentes": int(row.inconsistentes),
            "pct_inconsistentes": round(float(row.inconsistentes / row.transiciones), 4)}


def balls_in_play(con) -> dict:
    """Valor real de las bolas en juego con y sin velocidad de salida, y qué tanto la predicen EV, ángulo y dirección."""
    bip = con.sql("""
        select e.year, ExitSpeed, Angle,
               Direction * case batter_side when 'Right' then -1 else 1 end spray_pull,
               v.run_value
        from events e join event_value v using (pa_event)
        where PitchCall = 'InPlay'""").df()
    tracked = bip.dropna(subset=["ExitSpeed", "Angle"])
    train, test = tracked[tracked.year < HOLDOUT_SEASON], tracked[tracked.year == HOLDOUT_SEASON]
    r2 = {}
    for name, features in {"ev_angulo": ["ExitSpeed", "Angle"],
                           "ev_angulo_direccion": ["ExitSpeed", "Angle", "spray_pull"]}.items():
        model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, min_samples_leaf=200,
                                              random_state=RANDOM_SEED).fit(train[features], train.run_value)
        r2[name] = round(float(r2_score(test.run_value, model.predict(test[features]))), 4)
    untracked = bip[bip.ExitSpeed.isna()]
    return {"bolas_en_juego": len(bip), "sin_velocidad_salida": len(untracked),
            "valor_medio_con_ev": round(float(tracked.run_value.mean()), 3),
            "valor_medio_sin_ev": round(float(untracked.run_value.mean()), 3),
            "r2_2026": r2}


def main():
    con = duckdb.connect()
    create_events(con)
    weights = weights_summary(half_innings(con))
    summary = {
        "pesos_lineales": weights,
        "valor_por_conteo": count_values(con, weights["liga"]["pesos"]),
        "consistencia_conteo": count_consistency(con),
        "bolas_en_juego": balls_in_play(con),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
