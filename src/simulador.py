"""Entregable 4: simulador de Stuff+ para el pitching coach.

Se ingresan las características físicas de un pitch (como las da TrackMan) y su recta de referencia.
El simulador devuelve:

- **Stuff+ oficial** (D-027): el pitch llevado a nivel del mar y comparado contra su tipo en la liga.
- **Harp Helú contra nivel del mar:** el mismo pitch con el aire de cada lugar. El movimiento se
  traduce con aire^k por tipo (D-016). El Stuff+ en el Harp Helú resta la pérdida real promedio de su
  tipo en la liga, en los puntos de la escala oficial del arsenal (src/entregable_scores.py). El pasaporte (D-034) solo dice si este pitch, por su
  forma, pierde más o menos que el típico de su tipo, como percentil: en la prueba ordenó a los
  pitches, pero exageró la cifra de las rectas.
- **Mapa de movimiento:** los pitches de la liga de ese tipo (promedio por pitcher y temporada), con
  los más y menos efectivos marcados, y el pitch ingresado en los dos aires.

La primera corrida entrena los modelos con 2024–2025 y los guarda en data/modelos/, que no se sube.
Después levanta un servidor local en http://127.0.0.1:8050, que también sirve las fichas de los
pitchers (src/ficha.py) en /fichas.

Uso:
    python src/simulador.py             # entrena si hace falta y abre el servidor
    python src/simulador.py --entrenar  # vuelve a entrenar todo
    python src/simulador.py --metadatos # solo recalcula escala, mapa y rangos, sin reentrenar
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from config import HOLDOUT_SEASON, REPORTS_DIR, ROOT
from exploracion_etapa_04 import EXTREME, SEA_LEVEL
from modelo import PREDICTIONS_CACHE, SPECS, predict
from pasaporte_altitud import FASTBALL, LOCAL_FEATURES, PASSPORT_PARQUET, exponents, extreme_air, load_pitches
from stuff_componentes import FEATURES, choose_iterations, combine, new_model, outcome_values

BUNDLE = ROOT / "data" / "modelos" / "simulador.joblib"
TEMPLATE = Path(__file__).parent / "plantillas" / "simulador.html"
CARDS_HTML = ROOT / "data" / "fichas" / "fichas_pitchers.html"
# Delta de Stuff+ por tipo en la escala oficial del arsenal (src/entregable_scores.py), para no dar dos cifras.
SCORES_JSON = REPORTS_DIR / "etapa_06_scores.json"
HOST, PORT = "127.0.0.1", 8050
PITCH_TYPES = ["Four-Seam", "Sinker", "Cutter", "Slider", "Curveball", "Changeup", "Splitter"]
MIN_PITCHES_PER_PITCH_TYPE = 100
# Lo que el coach ingresa, en la convención de TrackMan.
INPUTS = ["RelSpeed", "SpinRate", "SpinAxis", "InducedVertBreak", "HorzBreak", "RelHeight", "RelSide", "Extension"]
STUFF_MODELS = [name for name in SPECS if name != "location"]


def raw_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """De la convención del lado del brazo a la de TrackMan para un diestro."""
    return frame.assign(SpinAxis=frame.spin_axis_arm, HorzBreak=frame.hb_arm_side, RelSide=frame.rel_side_arm)


def fit_models(pitches: pd.DataFrame, features: list[str], iterations: dict) -> dict:
    models = {}
    for name in STUFF_MODELS:
        kind, rows, label, _ = SPECS[name]
        subset = pitches[rows(pitches)]
        steps = iterations.get(name) or choose_iterations(kind, subset, label(subset), features)
        models[name] = (kind, new_model(kind, steps).fit(subset[features], label(subset)))
        print(f"{name}: {steps} árboles", flush=True)
    return models


def profile_values(profiles: pd.DataFrame, models: dict, values: pd.Series, categories: dict) -> np.ndarray:
    """Valor del Stuff+ oficial de cada perfil promedio, contra los dos lados del bateador."""
    rows = pd.concat([profiles.assign(platoon_same_side=side) for side in ("True", "False")], ignore_index=True)
    for column, levels in categories.items():
        rows[column] = pd.Categorical(rows[column].astype(str), categories=levels)
    predicted = pd.DataFrame({name: predict(model, kind, rows, FEATURES) for name, (kind, model) in models.items()})
    return combine(predicted, values).reshape(2, len(profiles)).mean(axis=0)


def scale_and_map(pitches: pd.DataFrame, models: dict, values: pd.Series, categories: dict) -> tuple[dict, dict]:
    """Escala y mapa con perfiles promedio de pitcher, temporada y tipo (100+ pitches).

    El coach escribe el perfil promedio de un pitch, así que se compara contra perfiles promedio de la
    liga evaluados con el mismo modelo, no contra pitches sueltos, que traen la variación de cada
    lanzamiento y harían ver a cualquier perfil limpio como élite.
    """
    numeric = [f for f in FEATURES if f not in categories]
    keys = ["pitcher_anon_id", "year", "pitch_class"]
    groups = pitches.groupby(keys, observed=True)
    profiles = groups[numeric].mean().join(groups.size().rename("pitches"))
    profiles = profiles.join(groups.pitcher_hand.agg(lambda s: s.mode().iloc[0])).reset_index()
    profiles = profiles[(profiles.pitches >= MIN_PITCHES_PER_PITCH_TYPE) & profiles.pitch_class.isin(PITCH_TYPES)]
    profiles = profiles.dropna(subset=numeric).reset_index(drop=True)
    profiles["stuff"] = profile_values(profiles, models, values, categories)
    scale, points = {}, {}
    for pitch_type in PITCH_TYPES:
        group = profiles[profiles.pitch_class == pitch_type]
        center, spread = float(group.stuff.mean()), float(group.stuff.std())
        scale[pitch_type] = {"media": center, "desviacion": spread, "perfiles": len(group)}
        profiles.loc[group.index, "plus"] = 100 - 10 * (group.stuff - center) / spread
    for pitch_type in PITCH_TYPES:
        group = profiles[profiles.pitch_class == pitch_type].copy()
        low, high = group.plus.quantile([0.1, 0.9])
        group["grupo"] = np.select([group.plus >= high, group.plus <= low], ["mejores", "peores"], "resto")
        group = group.rename(columns={"ivb_sea_level": "ivb", "hb_sea_level": "hb", "RelSpeed": "velo"})
        points[pitch_type] = group[["hb", "ivb", "velo", "plus", "grupo"]].round(2).to_dict(orient="list")
    return scale, points, median_profiles(profiles)


def median_profiles(profiles: pd.DataFrame) -> dict:
    """Para cada tipo, el perfil real cuyo Stuff+ está más cerca de 100, con la recta del mismo pitcher.

    Es lo que carga "valores típicos": un pitch mediano de la LMB que existe, no una mezcla de medianas
    de cada variable por separado, que no corresponde a ningún pitch.
    """
    keys = ["pitcher_anon_id", "year"]
    fastballs = profiles[profiles.pitch_class == FASTBALL].set_index(keys)
    result = {}
    for pitch_type in PITCH_TYPES:
        group = profiles[profiles.pitch_class == pitch_type].set_index(keys)
        if pitch_type != FASTBALL:
            group = group[group.index.isin(fastballs.index)]
        own = group.loc[(group.plus - 100).abs().idxmin()]
        fastball = fastballs.loc[own.name]
        result[pitch_type] = {**trackman_inputs(own), **{f"fb_{k}": v for k, v in trackman_inputs(fastball).items()},
                              "vaa_rel": round(float(own.vaa_rel), 2), "stuff_plus": round(float(own.plus), 1)}
    return result


def trackman_inputs(profile: pd.Series) -> dict:
    """Un perfil a nivel del mar, del lado del brazo, escrito como TrackMan para un diestro."""
    values = {"RelSpeed": profile.RelSpeed, "SpinRate": profile.SpinRate, "SpinAxis": profile.spin_axis_arm,
              "InducedVertBreak": profile.ivb_sea_level, "HorzBreak": profile.hb_sea_level,
              "RelHeight": profile.RelHeight, "RelSide": profile.rel_side_arm, "Extension": profile.Extension}
    return {k: round(float(v), 1) for k, v in values.items()}


def league_ranges(pitches: pd.DataFrame) -> dict:
    """Percentiles 1 y 99 de cada entrada por tipo, a nivel del mar, escritos como TrackMan para un diestro."""
    groups = raw_columns(pitches[pitches.altitude_category == SEA_LEVEL]).groupby("pitch_class", observed=True)
    low, high = groups[INPUTS].quantile(0.01).round(1), groups[INPUTS].quantile(0.99).round(1)
    return {t: {c: [float(low.loc[t, c]), float(high.loc[t, c])] for c in INPUTS} for t in PITCH_TYPES}


def passport_costs() -> dict:
    """Costo del pasaporte de cada pitch de la liga (100+ pitches a nivel del mar), para dar percentiles."""
    passport = pd.read_parquet(PASSPORT_PARQUET)
    passport = passport[passport.pitches >= MIN_PITCHES_PER_PITCH_TYPE]
    return {t: np.sort(passport.loc[passport.pitch_class == t, "costo_por_100"].to_numpy()) for t in PITCH_TYPES}


def metadata(pitches: pd.DataFrame, models: dict, values: pd.Series) -> dict:
    """Todo lo que el simulador necesita además de los modelos: escala, mapa, rangos y pérdidas."""
    k_by_type, k_league = exponents()
    by_type = json.loads((REPORTS_DIR / "etapa_05_pasaporte.json").read_text())["chequeo_por_tipo"]
    categories = {c: list(pitches[c].cat.categories) for c in ("pitch_class", "pitcher_hand", "platoon_same_side")}
    scale, points, typical = scale_and_map(pitches, models, values, categories)
    return {
        "categorias": categories,
        "k": {t: k_by_type.get(t, k_league) for t in PITCH_TYPES},
        "aire": {"mar": 1.0, "harp": extreme_air()[HOLDOUT_SEASON - 1]},
        "escala": scale,
        "mapa": points,
        "valores_tipicos": typical,
        "rangos": league_ranges(pitches),
        "dispersion_salida": float(pitches.loc[pitches.pitch_class == FASTBALL, "release_dist_vs_fb"].median()),
        "perdida_liga": {t: v["cambio_real_sin_contacto_por_100"] for t, v in by_type.items()},
        "delta_harp": {t: v["delta_stuff_plus"] for t, v in json.loads(SCORES_JSON.read_text())["stuff_plus_harp_promedio_por_tipo"].items()},
        "costos_pasaporte": passport_costs(),
    }


def training_pitches() -> pd.DataFrame:
    pitches = load_pitches()
    return pitches[pitches.pitcher_anon_id != "sin_id"]


def train() -> dict:
    pitches = training_pitches()
    iterations = json.loads(pd.read_parquet(PREDICTIONS_CACHE).attrs["arboles"])
    bundle = {
        "oficial": fit_models(pitches, FEATURES, iterations),
        "local": fit_models(pitches, LOCAL_FEATURES, {}),
        "valores": outcome_values(pitches),
    }
    bundle.update(metadata(pitches, bundle["oficial"], bundle["valores"]))
    save(bundle)
    return bundle


def refresh_metadata() -> dict:
    bundle = joblib.load(BUNDLE)
    bundle.update(metadata(training_pitches(), bundle["oficial"], bundle["valores"]))
    save(bundle)
    return bundle


def save(bundle: dict):
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, BUNDLE)


def arm_side(profile: dict, prefix: str = "") -> dict:
    """Valores de TrackMan llevados al lado del brazo, como en src/limpieza.py."""
    sign = -1 if profile["pitcher_hand"] == "Left" else 1
    axis = profile[f"{prefix}SpinAxis"]
    return {"hb": profile[f"{prefix}HorzBreak"] * sign, "rel_side": profile[f"{prefix}RelSide"] * sign,
            "axis": 360 - axis if sign < 0 else axis}


def pitch_rows(bundle: dict, profile: dict, air: float) -> pd.DataFrame:
    """El pitch con el aire dado, contra los dos lados del bateador, con las variables de los dos modelos."""
    pitch_type, measured = profile["pitch_class"], profile["aire_medido"]
    k, k_fb = bundle["k"][pitch_type], bundle["k"][FASTBALL]
    own, fb = arm_side(profile), arm_side(profile, "fb_")
    ivb_sea = profile["InducedVertBreak"] / measured ** k["ivb"]
    hb_sea = own["hb"] / measured ** k["hb"]
    fb_ivb_sea = profile["fb_InducedVertBreak"] / measured ** k_fb["ivb"]
    fb_hb_sea = fb["hb"] / measured ** k_fb["hb"]
    ivb, hb = ivb_sea * air ** k["ivb"], hb_sea * air ** k["hb"]
    row = {
        "RelSpeed": profile["RelSpeed"], "SpinRate": profile["SpinRate"], "spin_axis_arm": own["axis"],
        "RelHeight": profile["RelHeight"], "rel_side_arm": own["rel_side"], "Extension": profile["Extension"],
        "vaa_rel": profile["vaa_rel"], "InducedVertBreak": ivb, "hb_arm_side": hb,
        "ivb_sea_level": ivb_sea, "hb_sea_level": hb_sea,
        "velo_diff_vs_fb": profile["RelSpeed"] - profile["fb_RelSpeed"],
        "ivb_diff_vs_fb": ivb - fb_ivb_sea * air ** k_fb["ivb"],
        "hb_diff_vs_fb": hb - fb_hb_sea * air ** k_fb["hb"],
        "axis_diff_vs_fb": ((own["axis"] - fb["axis"] + 540) % 360) - 180,
        # Distancia entre promedios más la dispersión normal de cada lanzamiento: en los datos nunca es 0.
        "release_dist_vs_fb": float(np.hypot(np.hypot(profile["RelHeight"] - profile["fb_RelHeight"],
                                                      own["rel_side"] - fb["rel_side"]), bundle["dispersion_salida"])),
        "extension_diff_vs_fb": profile["Extension"] - profile["fb_Extension"],
        "pitch_class": pitch_type, "pitcher_hand": profile["pitcher_hand"],
    }
    rows = pd.DataFrame([{**row, "platoon_same_side": side} for side in ("True", "False")])
    for column, categories in bundle["categorias"].items():
        rows[column] = pd.Categorical(rows[column], categories=categories)
    return rows


def runs(bundle: dict, models: str, rows: pd.DataFrame, features: list[str]) -> float:
    predicted = pd.DataFrame({name: predict(model, kind, rows, features) for name, (kind, model) in bundle[models].items()})
    return float(np.mean(combine(predicted, bundle["valores"])))


def score(bundle: dict, profile: dict) -> dict:
    pitch_type = profile["pitch_class"]
    if pitch_type == FASTBALL:
        profile = {**profile, **{f"fb_{c}": profile[c] for c in INPUTS}}
    scale = bundle["escala"][pitch_type]

    def plus(value):
        return 100 - 10 * (value - scale["media"]) / scale["desviacion"]

    sea_rows = pitch_rows(bundle, profile, bundle["aire"]["mar"])
    harp_rows = pitch_rows(bundle, profile, bundle["aire"]["harp"])
    official = runs(bundle, "oficial", sea_rows, FEATURES)
    local_sea = runs(bundle, "local", sea_rows, LOCAL_FEATURES)
    local_harp = runs(bundle, "local", harp_rows, LOCAL_FEATURES)
    stuff_plus = plus(official)
    loss = bundle["perdida_liga"].get(pitch_type)
    cost = 100 * (local_harp - local_sea)
    league_costs = bundle["costos_pasaporte"][pitch_type]
    return {
        "stuff_plus": round(stuff_plus, 1),
        "stuff_plus_harp": None if loss is None else round(stuff_plus + bundle["delta_harp"][pitch_type], 1),
        "perdida_liga_por_100": loss,
        "mar": {"ivb": round(float(sea_rows.InducedVertBreak[0]), 1), "hb": round(float(sea_rows.hb_arm_side[0]), 1)},
        "harp": {"ivb": round(float(harp_rows.InducedVertBreak[0]), 1), "hb": round(float(harp_rows.hb_arm_side[0]), 1)},
        "percentil_costo_forma": None if len(league_costs) == 0
        else round(100 * float(np.searchsorted(league_costs, cost)) / len(league_costs)),
    }


def page(bundle: dict) -> bytes:
    config = {key: bundle[key] for key in ("mapa", "valores_tipicos", "rangos", "aire", "perdida_liga", "k")}
    config["tipos"] = PITCH_TYPES
    return TEMPLATE.read_text().replace("__CONFIG__", json.dumps(config, ensure_ascii=False)).encode()


def cards_page() -> bytes:
    if CARDS_HTML.exists():
        return CARDS_HTML.read_bytes()
    return "<p>Faltan las fichas: corre <code>python src/ficha.py</code> y recarga.</p>".encode()


def serve(bundle: dict):
    routes = {"/": page(bundle), "/fichas": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path not in routes:
                self.send(404, "text/plain; charset=utf-8", "No existe".encode())
                return
            self.send(200, "text/html; charset=utf-8", routes[path] or cards_page())

        def do_POST(self):
            try:
                profile = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                result = json.dumps(score(bundle, profile)).encode()
                self.send(200, "application/json", result)
            except (KeyError, TypeError, ValueError) as error:
                self.send(400, "application/json", json.dumps({"error": str(error)}).encode())

        def send(self, status, content_type, payload):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            # Sin caché: así una pestaña abierta nunca muestra una versión vieja del simulador.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    print(f"Simulador en http://{HOST}:{PORT} · fichas en http://{HOST}:{PORT}/fichas", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


def main():
    if "--entrenar" in sys.argv or not BUNDLE.exists():
        bundle = train()
    elif "--metadatos" in sys.argv:
        bundle = refresh_metadata()
    else:
        bundle = joblib.load(BUNDLE)
    serve(bundle)


if __name__ == "__main__":
    main()
