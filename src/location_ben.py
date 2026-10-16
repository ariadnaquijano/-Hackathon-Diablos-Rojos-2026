"""Location+ del equipo (Ben, PR #2) dentro del modelo oficial (D-039).

Usa el diseño de `location_plus_xgb.py` y `docs/LOCATIONPLUS_MODEL_GUIDE.md` sin cambios: un XGBoost por
cabeza del árbol de resultados (swing, whiff, strike cantado, golpeado, foul y resultado en juego),
las mismas variables, los mismos hiperparámetros, el run value de `run_value.py` y las fórmulas de
xCSW, xRV y Location+ (50 % CSW+ y 50 % RV+, ajustados por cuenta). Las piezas que el PR importaba
pero no traía (preparar datos, agregar predicciones y separar validación) se rearman con la guía.

Lo único que se agrega es la partición: 2024–2025 se predice con 5 pliegues por pitcher, como el resto
del modelo, y 2026 con un modelo entrenado en 2024–2025.

Escribe reportes/etapa_06_location_ben.json (comparación informativa contra Location+ v2, solo
2024–2025). Las predicciones van a data/processed/predicciones_location_ben.parquet.

Con `--estadio` escribe las predicciones de la validación por estadio (D-037): cada pliegue se entrena
sin ningún pitch de altitud extrema y predice los de altitud extrema de los pitchers que no vio.

Uso:
    python src/location_ben.py             # requiere modelo_v2
    python src/location_ben.py --estadio
"""

import json
import sys

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import CROSS_FIT_FOLDS, EXTREME, SEA_LEVEL
from modelo import load
from modelos_base import MIN_PITCHES_PER_PERIOD, PREDICTIONS_PARQUET, RANDOM_SEED, TARGET, pitcher_bootstrap
from modelo_v2 import official_predictions

sys.path.append(str(ROOT))  # run_value.py vive en la raíz del repo, como lo dejó el PR #2
from run_value import COLUMNAS_RV, RunValue, transiciones  # noqa: E402

CLEAN_PARQUET = ROOT / "data" / "processed" / "pitches_limpios.parquet"
PREDICTIONS_CACHE = ROOT / "data" / "processed" / "predicciones_location_ben.parquet"
PARK_CACHE = ROOT / "data" / "processed" / "predicciones_location_ben_estadio.parquet"
SUMMARY_JSON = REPORTS_DIR / "etapa_06_location_ben.json"

# Variables y cabezas de location_plus.py (PR #2)
CONTEXT = ["Balls", "Strikes", "count", "Outs", "Inning", "Top/Bottom", "altitude_category"]
LOCATION = ["PlateLocHeight", "PlateLocSide", "in_strike_zone", "outside_strike_zone"]
HANDS = ["pitcher_hand", "batter_side"]
FEATURES = CONTEXT + LOCATION + HANDS
CATEGORICAL = ["count", "Top/Bottom", "altitude_category", "pitcher_hand", "batter_side"]
BINARY_HEADS = ["swing", "whiff_dado_swing", "called_strike_dado_take", "hbp_dado_take_no_strike", "foul_dado_contacto"]
IN_PLAY_CLASSES = ["OUT", "1B", "2B", "3B", "HR"]
CLASS_OF_EVENT = {"OUT": 0, "E": 0, "SAC": 0, "FC": 0, "1B": 1, "2B": 2, "3B": 3, "HR": 4}
FOULS = ["FoulBall", "FoulBallNotFieldable", "FoulBallFieldable"]
CSW_WEIGHT = 0.5
PLUS_COLUMNS = ["location_plus_ben", "location_plus_ben_neutral", "location_plus_v2"]
VALIDATION_SHARE = 0.1
BEN_SEED = 42
# Hiperparámetros de location_plus_xgb.py (PR #2)
PARAMETERS = dict(n_estimators=2000, learning_rate=0.05, max_depth=6, min_child_weight=50, subsample=0.8,
                  colsample_bytree=0.8, reg_lambda=1.0, tree_method="hist", enable_categorical=True,
                  early_stopping_rounds=50, random_state=BEN_SEED, n_jobs=-1)


def load_pitches() -> pd.DataFrame:
    columns = sorted(set(FEATURES + COLUMNAS_RV + ["pitch_seq", "pitcher_anon_id", "is_swing", "is_whiff", "is_called_strike"]))
    pitches = duckdb.sql(f"select {', '.join(f'\"{c}\"' for c in columns)} from '{CLEAN_PARQUET}'").df()
    pitches[["altitude_category", "batter_side"]] = pitches[["altitude_category", "batter_side"]].fillna("Unknown")
    pitches["pitcher_anon_id"] = pitches.pitcher_anon_id.fillna("sin_id")
    for column in CATEGORICAL:
        pitches[column] = pitches[column].astype("category")
    return pitches


def model_rows(pitches: pd.DataFrame) -> pd.DataFrame:
    """Pitches con resultado definido y cuenta válida (filtrar_para_modelo del PR #2)."""
    ok = (pitches.PitchCall.ne("Undefined") & pitches.is_swing.notna()
          & pitches.Balls.between(0, 3) & pitches.Strikes.between(0, 2))
    return pitches[ok].reset_index(drop=True)


def labels(frame: pd.DataFrame) -> pd.DataFrame:
    """Etiqueta de cada cabeza; NaN o −1 si el pitch no pertenece a su población (etiquetas del PR #2)."""
    swing, whiff, called = (frame[c].to_numpy(bool) for c in ("is_swing", "is_whiff", "is_called_strike"))
    hbp = frame.PitchCall.eq("HitByPitch").to_numpy()
    event = transiciones(frame)["evento"]
    foul = (frame.PitchCall.isin(FOULS) & event.ne("OUT")).to_numpy()
    contact = swing & ~whiff
    in_play_class = event.map(CLASS_OF_EVENT).fillna(-1).astype(int).to_numpy()
    return pd.DataFrame({
        "swing": swing.astype(float),
        "whiff_dado_swing": np.where(swing, whiff, np.nan),
        "called_strike_dado_take": np.where(~swing, called, np.nan),
        "hbp_dado_take_no_strike": np.where(~swing & ~called, hbp, np.nan),
        "foul_dado_contacto": np.where(contact, foul, np.nan),
        "clase_en_juego": np.where(contact & ~foul, in_play_class, -1),
    }, index=frame.index)


def matrix(frame: pd.DataFrame) -> pd.DataFrame:
    X = frame[FEATURES].copy()
    numeric = [c for c in FEATURES if c not in CATEGORICAL]
    X[numeric] = X[numeric].astype("float32")
    return X


def validation_games(train: pd.DataFrame) -> np.ndarray:
    """10 % de los juegos para el early stopping, separados por juego (separar_validacion del PR #2)."""
    games = train.game_anon_id.unique()
    chosen = np.random.default_rng(BEN_SEED).choice(games, size=int(len(games) * VALIDATION_SHARE), replace=False)
    return train.game_anon_id.isin(chosen).to_numpy()


def fit_heads(train: pd.DataFrame) -> tuple[dict, dict]:
    held = validation_games(train)
    X_fit, X_val = matrix(train[~held]), matrix(train[held])
    y_fit, y_val = labels(train[~held]), labels(train[held])
    models, trees = {}, {}
    for head in BINARY_HEADS:
        fit_rows, val_rows = y_fit[head].notna().to_numpy(), y_val[head].notna().to_numpy()
        model = XGBClassifier(objective="binary:logistic", eval_metric="logloss", **PARAMETERS)
        model.fit(X_fit[fit_rows], y_fit.loc[fit_rows, head].astype(int),
                  eval_set=[(X_val[val_rows], y_val.loc[val_rows, head].astype(int))], verbose=False)
        models[head], trees[head] = model, model.best_iteration + 1
    fit_rows, val_rows = (y_fit.clase_en_juego >= 0).to_numpy(), (y_val.clase_en_juego >= 0).to_numpy()
    model = XGBClassifier(objective="multi:softprob", num_class=len(IN_PLAY_CLASSES), eval_metric="mlogloss", **PARAMETERS)
    model.fit(X_fit[fit_rows], y_fit.loc[fit_rows, "clase_en_juego"],
              eval_set=[(X_val[val_rows], y_val.loc[val_rows, "clase_en_juego"])], verbose=False)
    models["resultado_en_juego"], trees["resultado_en_juego"] = model, model.best_iteration + 1
    return models, trees


def expected_values(models: dict, frame: pd.DataFrame, run_value: RunValue) -> pd.DataFrame:
    """xCSW y xRV de cada pitch con las fórmulas de la guía (secciones 6.1 a 6.4)."""
    X = matrix(frame)
    p_swing, p_whiff, p_called, p_hbp, p_foul = (models[h].predict_proba(X)[:, 1] for h in BINARY_HEADS)
    p_classes = models["resultado_en_juego"].predict_proba(X)
    whiff, called = p_swing * p_whiff, (1 - p_swing) * p_called
    hbp = (1 - p_swing) * (1 - p_called) * p_hbp
    ball = (1 - p_swing) * (1 - p_called) * (1 - p_hbp)
    foul = p_swing * (1 - p_whiff) * p_foul
    in_play = p_swing * (1 - p_whiff) * (1 - p_foul)
    value = run_value.valores_por_resultado(frame.Balls.to_numpy(), frame.Strikes.to_numpy())
    xcsw = whiff + called
    xrv = (ball * value["bola"] + hbp * value["hbp"] + xcsw * value["strike"] + foul * value["foul"]
           + in_play * (p_classes * value["en_juego"]).sum(axis=1))
    return pd.DataFrame({"xCSW": xcsw, "xRV": xrv, "p_whiff": whiff, "p_called_strike": called}, index=frame.index)


def local_and_neutral(models: dict, frame: pd.DataFrame, run_value: RunValue) -> pd.DataFrame:
    """Cada pitch con su altitud real (local) y como si fuera a nivel del mar (neutral, D-040)."""
    at_sea = frame.assign(altitude_category=pd.Categorical([SEA_LEVEL] * len(frame),
                                                           categories=frame.altitude_category.cat.categories))
    neutral = expected_values(models, at_sea, run_value).add_suffix("_neutral")
    return expected_values(models, frame, run_value).join(neutral)


def build_predictions(pitches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    history = pitches[pitches.year < HOLDOUT_SEASON]
    run_value = RunValue.fit(history)  # como el PR #2: con todo 2024–2025, antes de filtrar
    rows = model_rows(pitches)
    train, holdout = rows[rows.year < HOLDOUT_SEASON], rows[rows.year == HOLDOUT_SEASON]
    parts, trees = [], {}
    models, trees["2026"] = fit_heads(train)
    parts.append(local_and_neutral(models, holdout, run_value))
    for fold, (fit_rows, other_rows) in enumerate(GroupKFold(CROSS_FIT_FOLDS).split(train, groups=train.pitcher_anon_id)):
        models, trees[f"pliegue_{fold + 1}"] = fit_heads(train.iloc[fit_rows])
        parts.append(local_and_neutral(models, train.iloc[other_rows], run_value))
        print(f"pliegue {fold + 1} listo", flush=True)
    predictions = pd.concat(parts).sort_index()
    rows = rows.join(predictions)
    rows["CSW"] = rows.is_whiff + rows.is_called_strike
    rows["RV_ben"] = run_value.transform(rows)
    keep = ["pitch_seq", "year", "pitcher_anon_id", "count", "altitude_category", "CSW", "RV_ben", *predictions.columns]
    return rows[keep], {"arboles": trees, "run_value": run_value.as_dict()}


def park_holdout_predictions(pitches: pd.DataFrame) -> pd.DataFrame:
    """Pitches de altitud extrema de 2024–2025, predichos sin ver al pitcher ni la altitud extrema."""
    history = pitches[pitches.year < HOLDOUT_SEASON]
    run_value = RunValue.fit(history[history.altitude_category != EXTREME])
    train = model_rows(history)
    parts = []
    for fold, (fit_rows, other_rows) in enumerate(GroupKFold(CROSS_FIT_FOLDS).split(train, groups=train.pitcher_anon_id)):
        fit_part = train.iloc[fit_rows]
        models, _ = fit_heads(fit_part[fit_part.altitude_category != EXTREME])
        test = train.iloc[other_rows]
        test = test[test.altitude_category == EXTREME]
        parts.append(local_and_neutral(models, test, run_value)[["xCSW_neutral", "xRV_neutral"]].join(test.pitch_seq))
        print(f"pliegue {fold + 1} listo", flush=True)
    return pd.concat(parts, ignore_index=True)


def residuals_by_pitcher(season: pd.DataFrame, extra: dict, suffix: str = "") -> pd.DataFrame:
    """xCSW y xRV de cada pitch menos el promedio de la liga en esa cuenta, promediados por pitcher."""
    season = season.assign(**{f"{c}_resid": season[c + suffix] - season.groupby("count", observed=True)[c + suffix].transform("mean")
                              for c in ("xCSW", "xRV")})
    return season.groupby("pitcher_anon_id").agg(pitches=("xCSW_resid", "size"), xCSW_resid=("xCSW_resid", "mean"),
                                                  xRV_resid=("xRV_resid", "mean"), **extra)


def ben_plus(table: pd.DataFrame) -> pd.Series:
    """Location+ = 100 + 10 · z ÷ desv(z), con z = 50 % CSW y 50 % RV (calcular_location_plus del PR #2)."""
    z_csw = table.xCSW_resid / table.xCSW_resid.std(ddof=0)
    z_rv = -table.xRV_resid / table.xRV_resid.std(ddof=0)
    z = CSW_WEIGHT * z_csw + (1 - CSW_WEIGHT) * z_rv
    return 100 + 10 * z / z.std(ddof=0)


def location_plus(frame: pd.DataFrame, min_pitches: int) -> pd.DataFrame:
    """Location+ de Ben y Location+ v2 por pitcher y temporada, con el mínimo de pitches oficial."""
    tables = []
    for year, season in frame.groupby("year"):
        table = residuals_by_pitcher(season, {"CSW": ("CSW", "mean"), "xrv_real": (TARGET, "mean"),
                                              "location_v2": ("location", "mean")})
        table = table[table.pitches >= min_pitches].copy()
        table["location_plus_ben"] = ben_plus(table)
        neutral = residuals_by_pitcher(season, {}, "_neutral").loc[table.index]
        table["location_plus_ben_neutral"] = ben_plus(neutral)
        table["location_plus_v2"] = 100 - 10 * (table.location_v2 - table.location_v2.mean()) / table.location_v2.std()
        tables.append(table.assign(year=year).reset_index())
    return pd.concat(tables, ignore_index=True)


def interval(draws) -> list[float]:
    return [round(float(v), 4) for v in np.percentile(draws, [2.5, 97.5])]


def per_pitch(history: pd.DataFrame) -> dict:
    """Mejora del error de cada Pitching+ (y de cada componente solo) contra el promedio por conteo."""
    y, null = history[TARGET].to_numpy(), history.media_conteo.to_numpy()
    fitted = {}
    for name, columns in (("pitching_v2", ["stuff", "location"]), ("pitching_ben", ["stuff", "xRV"]),
                          ("pitching_ben_neutral", ["stuff", "xRV_neutral"]), ("location_v2", ["location"]),
                          ("location_ben", ["xRV"]), ("location_ben_neutral", ["xRV_neutral"])):
        fitted[name] = LinearRegression().fit(history[columns], y).predict(history[columns])

    def gain(p, minus=None):
        def statistic(idx):
            base = np.mean((y[idx] - null[idx]) ** 2)
            value = 1 - np.mean((y[idx] - p[idx]) ** 2) / base
            if minus is not None:
                value -= 1 - np.mean((y[idx] - minus[idx]) ** 2) / base
            return 100 * value
        return statistic

    everyone = np.arange(len(y))
    result = {name: round(float(gain(p)(everyone)), 4) for name, p in fitted.items()}
    result["ic95_pitching_ben_menos_v2_pct"] = pitcher_bootstrap(history, gain(fitted["pitching_ben"], fitted["pitching_v2"]))
    result["ic95_location_ben_menos_v2_pct"] = pitcher_bootstrap(history, gain(fitted["location_ben"], fitted["location_v2"]))
    result["ic95_pitching_ben_neutral_menos_v2_pct"] = pitcher_bootstrap(
        history, gain(fitted["pitching_ben_neutral"], fitted["pitching_v2"]))
    return result


def per_pitcher(table: pd.DataFrame) -> dict:
    """Correlación de cada Location+ con el xRV real y el CSW real de la misma temporada, y su repetición."""
    rng = np.random.default_rng(RANDOM_SEED)
    result = {}
    for target, sign in (("xrv_real", -1), ("CSW", 1)):
        entry = {column: round(float(sign * table[column].corr(table[target])), 3) for column in PLUS_COLUMNS}
        samples = [table.iloc[rng.integers(0, len(table), len(table))] for _ in range(1000)]
        for column in ("location_plus_ben", "location_plus_ben_neutral"):
            entry[f"ic95_{column}_menos_v2"] = interval(
                [sign * (sample[column].corr(sample[target]) - sample.location_plus_v2.corr(sample[target])) for sample in samples])
        result[f"r_con_{target}"] = entry
    pairs = table[table.year == HOLDOUT_SEASON - 2].merge(table[table.year == HOLDOUT_SEASON - 1], on="pitcher_anon_id",
                                                         suffixes=("_a", "_b"))
    result["repeticion_2024_a_2025"] = {"pitchers": len(pairs), **{
        column: round(float(pairs[f"{column}_a"].corr(pairs[f"{column}_b"])), 3)
        for column in PLUS_COLUMNS}}
    return result


def main():
    if "--estadio" in sys.argv:
        park_holdout_predictions(load_pitches()).to_parquet(PARK_CACHE, index=False)
        return
    if PREDICTIONS_CACHE.exists():
        predictions = pd.read_parquet(PREDICTIONS_CACHE)
        meta = json.loads(predictions.attrs["meta"])
    else:
        predictions, meta = build_predictions(load_pitches())
        predictions.attrs["meta"] = json.dumps(meta)
        predictions.to_parquet(PREDICTIONS_CACHE, index=False)
    official, _, _ = official_predictions(load())
    null = pd.read_parquet(PREDICTIONS_PARQUET, columns=["pitch_seq", "media_conteo"])
    merged = (official[["pitch_seq", "pitcher_anon_id", "year", TARGET, "stuff", "location"]]
              .merge(null, on="pitch_seq", validate="one_to_one")
              .merge(predictions.drop(columns=["pitcher_anon_id", "year"]), on="pitch_seq", validate="one_to_one"))
    history = merged[(merged.year < HOLDOUT_SEASON) & (merged.pitcher_anon_id != "sin_id")].reset_index(drop=True)
    summary = {
        "nota": "Comparación informativa (D-039), solo 2024–2025; la adopción la decidió el equipo.",
        "pitches_comparados": len(history),
        "arboles": meta["arboles"],
        "run_value_pesos": meta["run_value"]["pesos"],
        "por_pitch_mejora_vs_promedio_por_conteo_pct": per_pitch(history),
        "por_pitcher": per_pitcher(location_plus(history, MIN_PITCHES_PER_PERIOD)),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
