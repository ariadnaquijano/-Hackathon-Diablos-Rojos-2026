"""Validación por estadio (park holdout, D-037).

Con 2024–2025 y los mismos 5 pliegues por pitcher que la versión oficial, cada modelo se entrena sin
ningún pitch de altitud extrema y predice los pitches de altitud extrema de los pitchers que no vio.
Así el modelo nunca vio ni al pitcher ni el aire del Harp Helú. Se compara contra el modelo nulo de la
convocatoria (promedio por conteo) y contra el modelo entrenado con todas las altitudes.

Escribe reportes/etapa_06_validacion_estadio.json, sin identificadores.

La versión 3 (D-040) se evalúa igual: Stuff+ de la misma prueba, el Location+ de Ben entrenado sin
altitud extrema (`python src/location_ben.py --estadio`) y los pesos oficiales de Pitching+ v3.

Uso:
    python src/validacion_estadio.py   # requiere modelo_v2, modelo_v3 y location_ben --estadio
"""

import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold

from afinado import new_model as tuned_model
from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import CROSS_FIT_FOLDS, EXTREME
from location_ben import PARK_CACHE
from modelo import SPECS, load, predict
from modelo_v2 import SETTING, official_predictions
from modelo_v3 import SUMMARY_JSON as V3_JSON
from modelo_v3 import official_pitches
from modelos_base import TARGET, group_mean, pitcher_bootstrap
from stuff_componentes import choose_iterations, combine, new_model, outcome_values

SUMMARY_JSON = REPORTS_DIR / "etapa_06_validacion_estadio.json"
HOLDOUT_CACHE = ROOT / "data" / "processed" / "predicciones_estadio.parquet"
STRICT_CACHE = ROOT / "data" / "processed" / "predicciones_estadio_estricta.parquet"
STUFF_NAMES = [name for name in SPECS if name != "location"]
VALUES = ["stuff", "location", "pitching"]
COUNT = ["Balls", "Strikes"]


def model_for(name: str, iterations: int):
    kind = SPECS[name][0]
    return tuned_model(kind, SETTING, iterations) if name == "location" else new_model(kind, iterations)


def park_holdout(history: pd.DataFrame, iterations: dict, weights: dict | None, names: list[str] = list(SPECS)) -> pd.DataFrame:
    """Pitches de altitud extrema, predichos por modelos sin ese pitcher y sin altitud extrema.

    Sin pesos (versión estricta) solo entrena los componentes pedidos y no arma Pitching+.
    """
    parts = []
    for fold, (fit_rows, other_rows) in enumerate(GroupKFold(CROSS_FIT_FOLDS).split(history, groups=history.pitcher_anon_id)):
        train = history.iloc[fit_rows]
        train = train[train.altitude_category != EXTREME]
        test = history.iloc[other_rows]
        test = test[test.altitude_category == EXTREME].copy()
        for name in names:
            kind, rows, label, features = SPECS[name]
            subset = train[rows(train)]
            model = model_for(name, iterations[name]).fit(subset[features], label(subset))
            test[name] = predict(model, kind, test, features)
        test["stuff"] = combine(test, outcome_values(train))
        if weights is not None:
            test["pitching"] = weights["intercepto"] + weights["stuff"] * test.stuff + weights["location"] * test.location
        test["media_conteo"] = group_mean(train, test, COUNT)
        test["media_liga"] = train[TARGET].mean()
        kept = [c for c in VALUES if c in test]
        parts.append(test[["pitch_seq", "pitcher_anon_id", TARGET, *kept, "media_conteo", "media_liga"]])
        print(f"pliegue {fold + 1} listo", flush=True)
    return pd.concat(parts, ignore_index=True)


def gains(test: pd.DataFrame, columns: list[str], reference: str = "media_conteo", versus: pd.DataFrame | None = None) -> dict:
    y = test[TARGET].to_numpy()
    base = test[reference].to_numpy()

    def improvement(p, minus=None):
        def statistic(idx):
            denominator = np.mean((y[idx] - base[idx]) ** 2)
            gain = 1 - np.mean((y[idx] - p[idx]) ** 2) / denominator
            if minus is not None:
                gain -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / denominator
            return 100 * gain
        return statistic

    result = {}
    for name in columns:
        p = test[name].to_numpy()
        result[name] = {f"mejora_vs_{reference}_pct": round(float(improvement(p)(np.arange(len(y)))), 4),
                        "ic95_pct": pitcher_bootstrap(test, improvement(p))}
        if versus is not None:
            result[name]["ic95_diferencia_vs_todas_las_altitudes_pct"] = pitcher_bootstrap(
                test, improvement(p, versus[name].to_numpy()))
    return result


def calibration(test: pd.DataFrame) -> dict:
    """Nivel predicho contra real en altitud extrema. El sesgo de cada modelo se compara con el del nulo,
    que no sabe nada del pitch: lo que comparten es un corrimiento del nivel de la liga en altura."""
    real = 100 * test[TARGET].mean()
    null_bias = 100 * test.media_conteo.mean() - real
    result = {"real_por_100": round(float(real), 4), "sesgo_nulo_por_100": round(float(null_bias), 4)}
    for name in VALUES:
        slope = np.polyfit(test[name], test[TARGET], 1)[0]
        bias = 100 * test[name].mean() - real
        result[name] = {"predicho_por_100": round(float(100 * test[name].mean()), 4), "pendiente": round(float(slope), 3),
                        "sesgo_por_100": round(float(bias), 4), "sesgo_menos_nulo": round(float(bias - null_bias), 4)}
    return result


def version_3(holdout: pd.DataFrame, pitches: pd.DataFrame) -> dict:
    """Stuff+ sin altitud extrema, Location+ de Ben sin altitud extrema y los pesos oficiales de la versión 3."""
    weights = json.loads(V3_JSON.read_text())["pesos_pitching"]
    ben = pd.read_parquet(PARK_CACHE)[["pitch_seq", "xRV_neutral"]].rename(columns={"xRV_neutral": "location"})
    test = holdout.drop(columns=["location", "pitching"]).merge(ben, on="pitch_seq", validate="one_to_one")
    test["pitching"] = weights["intercepto"] + weights["stuff"] * test.stuff + weights["location"] * test.location
    official, _ = official_pitches(pitches)
    full = test[["pitch_seq"]].merge(official[["pitch_seq", *VALUES]], on="pitch_seq", validate="one_to_one")
    result = {"pitches": len(test), "sin_altitud_extrema": gains(test, VALUES, versus=full),
              "con_todas_las_altitudes": gains(test.drop(columns=VALUES).join(full[VALUES]), VALUES),
              "calibracion": calibration(test)}
    result["pasa"] = all(result["sin_altitud_extrema"][v]["ic95_pct"][0] > 0 for v in VALUES)
    return result


def strict_version_3(history: pd.DataFrame, pitches: pd.DataFrame) -> dict:
    """Versión 3 con árboles y pesos de Pitching+ elegidos sin ningún pitch de altitud extrema (D-042)."""
    others = history[history.altitude_category != EXTREME]
    if STRICT_CACHE.exists():
        holdout = pd.read_parquet(STRICT_CACHE)
        iterations = json.loads(holdout.attrs["arboles"])
    else:
        iterations = {}
        for name in STUFF_NAMES:
            kind, rows, label, features = SPECS[name]
            subset = others[rows(others)]
            iterations[name] = choose_iterations(kind, subset, label(subset), features)
        holdout = park_holdout(history, iterations, None, STUFF_NAMES)
        holdout.attrs["arboles"] = json.dumps(iterations)
        holdout.to_parquet(STRICT_CACHE, index=False)
    official, _ = official_pitches(pitches)
    fit_rows = official[(official.year < HOLDOUT_SEASON) & (official.altitude_category != EXTREME)
                        & (official.pitcher_anon_id != "sin_id")]
    stack = LinearRegression().fit(fit_rows[["stuff", "location"]], fit_rows[TARGET])
    ben = pd.read_parquet(PARK_CACHE)[["pitch_seq", "xRV_neutral"]].rename(columns={"xRV_neutral": "location"})
    test = holdout.merge(ben, on="pitch_seq", validate="one_to_one")
    test["pitching"] = stack.predict(test[["stuff", "location"]])
    result = {"pitches": len(test), "arboles": iterations,
              "pesos_pitching": {"intercepto": round(float(stack.intercept_), 5), "stuff": round(float(stack.coef_[0]), 4),
                                 "location": round(float(stack.coef_[1]), 4)},
              "sin_altitud_extrema": gains(test, VALUES), "calibracion": calibration(test)}
    result["pasa"] = all(result["sin_altitud_extrema"][v]["ic95_pct"][0] > 0 for v in VALUES)
    return result


def main():
    pitches = load()
    official, weights, iterations = official_predictions(pitches)
    history = pitches[(pitches.year < HOLDOUT_SEASON) & (pitches.pitcher_anon_id != "sin_id")].reset_index(drop=True)
    if HOLDOUT_CACHE.exists():
        holdout = pd.read_parquet(HOLDOUT_CACHE)
    else:
        holdout = park_holdout(history, iterations, weights)
        holdout.to_parquet(HOLDOUT_CACHE, index=False)
    full = holdout[["pitch_seq"]].merge(official[["pitch_seq", *VALUES]], on="pitch_seq", validate="one_to_one")
    summary = {
        "nota": "2024–2025; modelos sin el pitcher y sin altitud extrema, evaluados en altitud extrema (D-037).",
        "pitches": len(holdout), "pitchers": int(holdout.pitcher_anon_id.nunique()),
        "sin_altitud_extrema": gains(holdout, VALUES, versus=full),
        "con_todas_las_altitudes": gains(holdout.drop(columns=VALUES).join(full[VALUES]), VALUES),
        "contra_media_liga": gains(holdout, [*VALUES, "media_conteo"], reference="media_liga"),
        "calibracion": calibration(holdout),
    }
    summary["pasa"] = all(summary["sin_altitud_extrema"][v]["ic95_pct"][0] > 0 for v in VALUES)
    summary["version_3"] = version_3(holdout, pitches)
    summary["version_3_estricta"] = strict_version_3(history, pitches)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
