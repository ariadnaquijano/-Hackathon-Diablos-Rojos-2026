"""Hipótesis H4: el spin rate por sí solo resulta insuficiente como predictor de Stuff+.

Análisis sobre el dataset original, como acordó el equipo, con filtros mínimos. Plan fijado antes
de correrlo (docs/hipotesis_h4.md):

1. Poder predictivo: ¿qué predice mejor el swing fallido, el spin rate o el movimiento?
   Cinco modelos por tipo de pitch, entrenados con 2024–2025 y evaluados en 2026.
2. Prueba de altitud: entrenar a nivel del mar y predecir en altitud extrema. Si H4 es cierta,
   el modelo de solo spin sobreestima el whiff en altura, porque no ve que el pitch se mueve menos.
3. Mismo spin, distinto movimiento: rectas en una banda estrecha de spin, separadas por su IVB.

Escribe reportes/h4_resumen.json y, con la plantilla src/plantillas/hipotesis_h4.html,
genera reportes/h4_spin_rate.html.

Uso:
    python src/hipotesis_h4.py
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score

from config import RAW_PARQUET, REPORTS_DIR, ROOT

SUMMARY_JSON = REPORTS_DIR / "h4_resumen.json"
TEMPLATE = Path(__file__).parent / "plantillas" / "hipotesis_h4.html"
OUTPUT_HTML = REPORTS_DIR / "h4_spin_rate.html"
RANDOM_SEED = 2026
BOOTSTRAP_SAMPLES = 200

PITCH_TYPES = ("Four-Seam", "Sinker", "Slider", "Curveball", "Changeup")
TEST_SEASON = 2026
MODELS = {
    "spin": ["SpinRate"],
    "velocidad": ["RelSpeed"],
    "movimiento": ["InducedVertBreak", "hb_arm_side"],
    "velocidad_movimiento": ["RelSpeed", "InducedVertBreak", "hb_arm_side"],
    "velocidad_movimiento_spin": ["RelSpeed", "InducedVertBreak", "hb_arm_side", "SpinRate"],
}
# Comparaciones que responden H4: ¿el movimiento le gana al spin? ¿el spin agrega algo al movimiento?
COMPARISONS = {
    "movimiento_vs_spin": ("movimiento", "spin"),
    "spin_agrega_al_movimiento": ("velocidad_movimiento_spin", "velocidad_movimiento"),
}
# Banda estrecha de spin para comparar rectas con el mismo giro.
SPIN_BAND_RPM = (2250, 2400)


def load_swings(con):
    """Swings con física medida. HB se expresa hacia el lado del brazo para juntar zurdos y derechos."""
    types = ", ".join(f"'{t}'" for t in PITCH_TYPES)
    return con.sql(f"""
        select year, pitcher_anon_id, AutoPitchType pitch_type, altitude_category,
               RelSpeed, SpinRate, InducedVertBreak,
               HorzBreak * case PitcherThrows when 'Left' then -1 else 1 end hb_arm_side,
               is_whiff::int whiff
        from '{RAW_PARQUET}'
        where is_swing = 1 and AutoPitchType in ({types})
          and PitcherThrows in ('Left', 'Right')
          and RelSpeed is not null and SpinRate is not null
          and InducedVertBreak is not null and HorzBreak is not null""").df()


def fit(train, features):
    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                           min_samples_leaf=200, random_state=RANDOM_SEED)
    return model.fit(train[features], train.whiff)


def skill(y, p) -> dict:
    """AUC y mejora del log loss contra predecir siempre la tasa base (0 = no aprende nada)."""
    base = np.full_like(p, y.mean(), dtype=float)
    return {"auc": float(roc_auc_score(y, p)),
            "mejora_log_loss": float(1 - log_loss(y, p) / log_loss(y, base))}


def bootstrap_auc_difference(test, preds_a, preds_b) -> list[float]:
    """IC 95 % de AUC(a) − AUC(b), remuestreando pitchers completos."""
    rng = np.random.default_rng(RANDOM_SEED)
    groups = test.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(groups))
    y = test.whiff.to_numpy()
    diffs = []
    for _ in range(BOOTSTRAP_SAMPLES):
        idx = np.concatenate([groups[p] for p in rng.choice(pitchers, size=len(pitchers), replace=True)])
        diffs.append(roc_auc_score(y[idx], preds_a[idx]) - roc_auc_score(y[idx], preds_b[idx]))
    low, high = np.percentile(diffs, [2.5, 97.5])
    return [round(float(low), 4), round(float(high), 4)]


def predictive_power(swings) -> list[dict]:
    results = []
    for pitch_type in PITCH_TYPES:
        data = swings[swings.pitch_type == pitch_type]
        train, test = data[data.year < TEST_SEASON], data[data.year == TEST_SEASON].reset_index(drop=True)
        preds = {name: fit(train, cols).predict_proba(test[cols])[:, 1] for name, cols in MODELS.items()}
        row = {"tipo": pitch_type, "swings_entrenamiento": len(train), "swings_prueba": len(test),
               "whiff_base": round(float(test.whiff.mean()), 4)}
        for name, p in preds.items():
            row[name] = {k: round(v, 4) for k, v in skill(test.whiff, p).items()}
        for label, (a, b) in COMPARISONS.items():
            row[label] = {"diferencia_auc": round(row[a]["auc"] - row[b]["auc"], 4),
                          "ic95": bootstrap_auc_difference(test, preds[a], preds[b])}
        results.append(row)
    return results


def altitude_transfer(swings) -> list[dict]:
    """Entrena a nivel del mar, predice en altitud extrema: whiff predicho contra real."""
    results = []
    for pitch_type in PITCH_TYPES:
        data = swings[swings.pitch_type == pitch_type]
        sea, high = data[data.altitude_category == "No Altitude"], data[data.altitude_category == "Extreme Altitude"]
        row = {"tipo": pitch_type, "swings_altitud": len(high),
               "whiff_real_altitud": round(float(high.whiff.mean()), 4),
               "whiff_real_mar": round(float(sea.whiff.mean()), 4)}
        for name in ("spin", "movimiento"):
            cols = MODELS[name]
            row[f"whiff_predicho_{name}"] = round(float(fit(sea, cols).predict_proba(high[cols])[:, 1].mean()), 4)
        results.append(row)
    return results


def bootstrap_rate_difference(frame, group_col: str, high, low) -> list[float]:
    """IC 95 % de whiff(high) − whiff(low), remuestreando pitchers completos.

    Los swings del mismo pitcher no son independientes; remuestrear pitchers evita un intervalo
    artificialmente estrecho.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    groups = frame.groupby("pitcher_anon_id").indices
    pitchers = np.array(list(groups))
    whiff, group = frame.whiff.to_numpy(), frame[group_col].to_numpy()
    diffs = []
    for _ in range(BOOTSTRAP_SAMPLES):
        idx = np.concatenate([groups[p] for p in rng.choice(pitchers, size=len(pitchers), replace=True)])
        w, g = whiff[idx], group[idx]
        diffs.append(w[g == high].mean() - w[g == low].mean())
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def same_spin_different_movement(con) -> dict:
    """Rectas con el mismo spin: si el spin bastara, el whiff no cambiaría con el movimiento."""
    low, high = SPIN_BAND_RPM
    fastballs = con.sql(f"""
        select pitcher_anon_id, altitude_category, SpinRate, RelSpeed, InducedVertBreak, is_whiff::int whiff,
               ntile(3) over (order by InducedVertBreak) tercil
        from '{RAW_PARQUET}'
        where AutoPitchType = 'Four-Seam' and is_swing = 1 and SpinRate between {low} and {high}
          and InducedVertBreak is not null and RelSpeed is not null""").df()

    def describe(group_col):
        return (fastballs.dropna(subset=[group_col]).groupby(group_col)
                .agg(spin_mediano=("SpinRate", "median"), velocidad_mediana=("RelSpeed", "median"),
                     ivb_mediano=("InducedVertBreak", "median"), whiff_por_swing=("whiff", "mean"),
                     swings=("whiff", "size"))
                .round(4).reset_index().to_dict(orient="records"))

    by_altitude = fastballs.dropna(subset=["altitude_category"])
    return {
        "banda_rpm": [low, high],
        "por_tercil_ivb": describe("tercil"),
        "diferencia_tercil_alto_vs_bajo": {
            "whiff": round(float(fastballs[fastballs.tercil == 3].whiff.mean()
                                 - fastballs[fastballs.tercil == 1].whiff.mean()), 4),
            "ic95": bootstrap_rate_difference(fastballs, "tercil", 3, 1)},
        "por_altitud": describe("altitude_category"),
        "diferencia_mar_vs_altitud_extrema": {
            "whiff": round(float(by_altitude[by_altitude.altitude_category == "No Altitude"].whiff.mean()
                                 - by_altitude[by_altitude.altitude_category == "Extreme Altitude"].whiff.mean()), 4),
            "ic95": bootstrap_rate_difference(by_altitude, "altitude_category", "No Altitude", "Extreme Altitude")},
    }


def pct(rate: float) -> str:
    """Tasa como porcentaje con un decimal, redondeando .5 hacia arriba como el reporte HTML."""
    return str((Decimal(str(rate)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def print_predictive_power(rows: list[dict]):
    print("\n1. ¿Qué predice mejor el swing fallido? AUC en 2026 (0.5 = azar)")
    print(f"   {'Pitch':<11}{'spin':>7}{'velo':>7}{'mov':>7}{'velo+mov':>10}{'+spin':>7}   movimiento − spin [IC 95 %]")
    for r in rows:
        diff = r["movimiento_vs_spin"]
        print(f"   {r['tipo']:<11}" + "".join(f"{r[m]['auc']:>{w}.3f}" for m, w in
              zip(MODELS, (7, 7, 7, 10, 7))) + f"   {diff['diferencia_auc']:+.3f} {diff['ic95']}")


def print_same_spin(result: dict):
    low, high = result["banda_rpm"]
    print(f"\n2. Rectas con el mismo spin ({low}–{high} rpm), por tercio de IVB")
    for r in result["por_tercil_ivb"]:
        print(f"   Tercio {r['tercil']}: IVB {r['ivb_mediano']:.1f} in, spin {r['spin_mediano']:.0f} rpm, "
              f"whiff {pct(r['whiff_por_swing'])} %")
    diff = result["diferencia_tercil_alto_vs_bajo"]
    print(f"   Diferencia alto − bajo: {100 * diff['whiff']:+.1f} puntos [IC 95 % {pct(diff['ic95'][0])} a {pct(diff['ic95'][1])}]")
    print("\n3. Las mismas rectas por altitud")
    for r in result["por_altitud"]:
        print(f"   {r['altitude_category']:<17} IVB {r['ivb_mediano']:.1f} in, spin {r['spin_mediano']:.0f} rpm, "
              f"whiff {pct(r['whiff_por_swing'])} %")
    diff = result["diferencia_mar_vs_altitud_extrema"]
    print(f"   Nivel del mar − altitud extrema: {100 * diff['whiff']:+.1f} puntos [IC 95 % {pct(diff['ic95'][0])} a {pct(diff['ic95'][1])}]")


def print_altitude_transfer(rows: list[dict]):
    print("\n4. Entrenado a nivel del mar, predicho en altitud extrema (whiff por swing)")
    for r in rows:
        print(f"   {r['tipo']:<11} real {pct(r['whiff_real_altitud'])} %  ·  solo spin "
              f"{pct(r['whiff_predicho_spin'])} %  ·  solo movimiento {pct(r['whiff_predicho_movimiento'])} %")


def main():
    con = duckdb.connect()
    swings = load_swings(con)
    print(f"H4 · {len(swings):,} swings con spin, velocidad y movimiento medidos")
    summary = {
        "swings_analizados": len(swings),
        "poder_predictivo": predictive_power(swings),
        "transferencia_altitud": altitude_transfer(swings),
        "mismo_spin": same_spin_different_movement(con),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    OUTPUT_HTML.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(summary, ensure_ascii=False)))
    print_predictive_power(summary["poder_predictivo"])
    print_same_spin(summary["mismo_spin"])
    print_altitude_transfer(summary["transferencia_altitud"])
    print(f"\nResumen en {SUMMARY_JSON.relative_to(ROOT)} y reporte en {OUTPUT_HTML.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
