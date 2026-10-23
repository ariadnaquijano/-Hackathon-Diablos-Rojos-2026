"""¿Lo que el modelo estima de un pitcher anticipa lo que hará el año siguiente?

En carreras ningún índice le gana a la historia del pitcher (D-039), pero el resultado en carreras
casi no se repite (r 0.18). Aquí se mide en lo que el pitcher sí controla: para cada componente
(swing, whiff, foul y strike cantado), la tasa que estima el modelo en 2024 contra la tasa real de
2024, como predictoras de la tasa real de 2025. Mismos pitchers (300+ pitches en los dos años).

Regla fijada antes de correr: el componente del modelo predice mejor si el intervalo del 95 % de la
diferencia de correlaciones (modelo menos real), remuestreando pitchers 1,000 veces, queda arriba de
cero. 2026 no se usa.

Escribe reportes/etapa_06_componentes_futuro.json.

Uso:
    python src/componentes_futuro.py   # requiere src/modelo.py
"""

import json

import numpy as np

from config import REPORTS_DIR
from modelos_base import RANDOM_SEED
from pasaporte_altitud import BOOTSTRAP_SAMPLES, interval
from proyeccion import FIRST, SECOND, centered_columns, load_pitches, pitcher_values

SUMMARY_JSON = REPORTS_DIR / "etapa_06_componentes_futuro.json"
# Componente estimado por el modelo y la tasa real que le corresponde (src/proyeccion.py).
PAIRS = {"p_swing": "swing", "p_whiff": "whiff", "p_foul": "foul", "p_strike": "strike_cantado"}


def compare(pairs, estimate: str, observed: str) -> dict:
    target = pairs[f"{observed}_despues"].to_numpy()
    model, history = pairs[f"{estimate}_antes"].to_numpy(), pairs[f"{observed}_antes"].to_numpy()
    r = lambda x, idx: float(np.corrcoef(x[idx], target[idx])[0, 1])
    everyone = np.arange(len(pairs))
    rng = np.random.default_rng(RANDOM_SEED)
    draws = [r(model, idx) - r(history, idx) for idx in (rng.choice(everyone, len(everyone)) for _ in range(BOOTSTRAP_SAMPLES))]
    low, high = interval(draws)
    return {"r_modelo": round(r(model, everyone), 3), "r_real_anterior": round(r(history, everyone), 3),
            "ic95_diferencia": [low, high], "modelo_predice_mejor": bool(low > 0)}


def main():
    frame = centered_columns(load_pitches())
    first, second = pitcher_values(frame[frame.year == FIRST]), pitcher_values(frame[frame.year == SECOND])
    pairs = first.add_suffix("_antes").join(second.add_suffix("_despues"), how="inner")
    summary = {"nota": f"Tasa real de {SECOND} predicha con el modelo o con la tasa real de {FIRST}; 2026 no se usa.",
               "pitchers": len(pairs),
               "componentes": {observed: compare(pairs, estimate, observed) for estimate, observed in PAIRS.items()}}
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
