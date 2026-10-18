"""Comprueba que el simulador en el navegador da lo mismo que el de Python.

El jurado no ejecuta código, así que la página calcula el Stuff+ con los árboles exportados
(src/plantillas/motor_stuff.js). Aquí se evalúan 2,000 pitches al azar alrededor del perfil típico de
cada tipo, con las dos manos y los dos aires, con score() de Python y con el motor en Node. Pasa si
ningún Stuff+ difiere en más de 0.1 puntos (el redondeo a un decimal).

Escribe reportes/verificacion_simulador.json.

Uso:
    python src/verificar_simulador.py   # requiere Node y data/modelos/simulador.joblib
"""

import json
import subprocess
import tempfile
from pathlib import Path

import joblib
import numpy as np

from config import REPORTS_DIR
from modelos_base import RANDOM_SEED
from simulador import BUNDLE, ENGINE_JS, INPUTS, PHYSICAL_LIMITS, PITCH_TYPES, browser_model, score

SUMMARY_JSON = REPORTS_DIR / "verificacion_simulador.json"
PITCHES = 2000
TOLERANCE = 0.1
# Ruido alrededor del perfil típico, en las unidades de TrackMan.
NOISE = {"RelSpeed": 4, "SpinRate": 300, "SpinAxis": 25, "InducedVertBreak": 4, "HorzBreak": 4,
         "RelHeight": 0.4, "RelSide": 0.6, "Extension": 0.4}
NODE_SCRIPT = """
const motor = require(process.argv[1]), fs = require("fs");
const [model, profiles] = [JSON.parse(fs.readFileSync(process.argv[2])), JSON.parse(fs.readFileSync(process.argv[3]))];
process.stdout.write(JSON.stringify(profiles.map(p => motor.score(model, p))));
"""


def random_profiles(bundle: dict) -> list[dict]:
    rng = np.random.default_rng(RANDOM_SEED)
    profiles = []
    for _ in range(PITCHES):
        pitch_type = str(rng.choice(PITCH_TYPES))
        typical = bundle["valores_tipicos"][pitch_type]
        profile = {"pitch_class": pitch_type, "pitcher_hand": str(rng.choice(["Right", "Left"])),
                   "aire_medido": float(rng.choice([bundle["aire"]["mar"], bundle["aire"]["harp"]]))}
        for prefix in ("", "fb_"):
            for key in INPUTS:
                value = typical[prefix + key] + rng.normal(0, NOISE[key])
                value = value % 360 if key == "SpinAxis" else np.clip(value, *PHYSICAL_LIMITS[key])
                profile[prefix + key] = round(float(value), 1)
        profiles.append(profile)
    return profiles


def browser_scores(model: dict, profiles: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as folder:
        model_path, profiles_path = Path(folder) / "modelo.json", Path(folder) / "perfiles.json"
        model_path.write_text(json.dumps(model))
        profiles_path.write_text(json.dumps(profiles))
        output = subprocess.run(["node", "-e", NODE_SCRIPT, str(ENGINE_JS), str(model_path), str(profiles_path)],
                                capture_output=True, text=True, check=True).stdout
    return json.loads(output)


def largest_gap(python: list[dict], browser: list[dict], key: str) -> float:
    pairs = [(p[key], b[key]) for p, b in zip(python, browser) if p[key] is not None or b[key] is not None]
    if any(p is None or b is None for p, b in pairs):
        return float("inf")
    return max((abs(p - b) for p, b in pairs), default=0.0)


def main():
    bundle = joblib.load(BUNDLE)
    profiles = random_profiles(bundle)
    python = [score(bundle, profile) for profile in profiles]
    browser = browser_scores(browser_model(bundle), profiles)
    gaps = {key: round(largest_gap(python, browser, key), 4) for key in ("stuff_plus", "stuff_plus_harp")}
    movement = max(abs(p[place][axis] - b[place][axis]) for p, b in zip(python, browser)
                   for place in ("mar", "harp") for axis in ("ivb", "hb"))
    summary = {"pitches": PITCHES, "diferencia_maxima": {**gaps, "movimiento": round(movement, 4)},
               "tolerancia": TOLERANCE, "pasa": all(g <= TOLERANCE for g in (*gaps.values(), movement))}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
