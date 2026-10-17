"""El exponente k reexpresado en densidad del aire (D-041).

`air_ratio` es un cociente de frenado de las rectas (densidad × coeficiente de arrastre), no de
densidad. Este script:

1. Estima la densidad relativa del Harp Helú (2,240 m) contra un estadio a nivel del mar con la
   atmósfera estándar y rangos de temperatura de juego (ρ = p ÷ R·T; la humedad mueve menos de 1 %).
2. Convierte cada k a un exponente en densidad: k_ρ = k · ln(air_ratio) ÷ ln(ρ relativa).
3. Mide con los datos cuánto cambia el tiempo de vuelo de la recta. El movimiento es ½ · a · t², con la
   aceleración de Magnus ∝ ρ, así que la física predice k_ρ = 1 + ln(t²_extrema ÷ t²_mar) ÷ ln(ρ relativa).

No cambia el modelo: la traducción a nivel del mar usa el frenado medido y su k juntos.
Escribe reportes/etapa_06_fisica_densidad.json.

Uso:
    python src/fisica_densidad.py   # requiere src/features.py
"""

import json
import math

import duckdb

from config import HOLDOUT_SEASON, MODEL_PARQUET, REPORTS_DIR
from exploracion_etapa_04 import EXTREME, SEA_LEVEL

SUMMARY_JSON = REPORTS_DIR / "etapa_06_fisica_densidad.json"
STAGE_02_JSON = REPORTS_DIR / "etapa_02_resumen.json"
HARP_ALTITUDE_M = 2240
# Atmósfera estándar internacional (troposfera)
SEA_PRESSURE_PA, LAPSE_K_PER_M, SEA_TEMPERATURE_K, PRESSURE_EXPONENT = 101_325, 0.0065, 288.15, 5.2559
# Temperaturas de juego supuestas (°C): noches de verano en estadios de la costa y el norte, y en la CDMX.
SEA_GAME_C = {"baja": 24, "central": 28, "alta": 32}
HARP_GAME_C = {"baja": 14, "central": 19, "alta": 24}
DISTANCE_FT = 55  # de la salida al plato, aproximado


def pressure(altitude_m: float) -> float:
    return SEA_PRESSURE_PA * (1 - LAPSE_K_PER_M * altitude_m / SEA_TEMPERATURE_K) ** PRESSURE_EXPONENT


def density_ratio(sea_c: float, harp_c: float) -> float:
    """ρ_Harp ÷ ρ_mar = (p_Harp ÷ p_mar) · (T_mar ÷ T_Harp), con la ley de gases ideales."""
    return pressure(HARP_ALTITUDE_M) / SEA_PRESSURE_PA * (sea_c + 273.15) / (harp_c + 273.15)


def extreme_air() -> float:
    """Mediana del frenado relativo en altitud extrema, promedio de 2024 y 2025."""
    rows = json.loads(STAGE_02_JSON.read_text())["aire"]["por_altitud_y_temporada"]
    values = [r["p50"] for r in rows if r["altitud"] == EXTREME and r["year"] < HOLDOUT_SEASON]
    return sum(values) / len(values)


def flight_time() -> dict:
    """Velocidad media de la recta de la salida al plato en cada altitud: el tiempo de vuelo es su inverso."""
    rows = duckdb.sql(f"""
        select altitude_category, median(RelSpeed) salida, median(ZoneSpeed) plato, count(*) n
        from '{MODEL_PARQUET}'
        where pitch_class = 'Four-Seam' and year < {HOLDOUT_SEASON} and usable_stuff
          and altitude_category in ('{EXTREME}', '{SEA_LEVEL}') and ZoneSpeed is not null
        group by 1""").df().set_index("altitude_category")
    mean_speed = (rows.salida + rows.plato) / 2
    ratio = mean_speed[SEA_LEVEL] / mean_speed[EXTREME]
    return {"velocidad_salida_mph": rows.salida.round(1).to_dict(), "velocidad_plato_mph": rows.plato.round(1).to_dict(),
            "tiempo_extrema_entre_mar": round(float(ratio), 4),
            "efecto_en_movimiento_pct": round(float(100 * (ratio ** 2 - 1)), 2),
            "tiempo_de_vuelo_mar_s": round(float(DISTANCE_FT / (mean_speed[SEA_LEVEL] * 5280 / 3600)), 3)}


def main():
    air = extreme_air()
    densities = {name: density_ratio(SEA_GAME_C[name], HARP_GAME_C[name]) for name in SEA_GAME_C}
    # Más calor en la costa o más frío en la CDMX baja la densidad relativa; el rango toma los extremos.
    low, high = density_ratio(SEA_GAME_C["baja"], HARP_GAME_C["alta"]), density_ratio(SEA_GAME_C["alta"], HARP_GAME_C["baja"])
    factors = {"central": math.log(air) / math.log(densities["central"]),
               "rango": sorted([math.log(air) / math.log(low), math.log(air) / math.log(high)])}
    k = json.loads(STAGE_02_JSON.read_text())["exponente_k"]
    flight = flight_time()
    expected = 1 + math.log(flight["tiempo_extrema_entre_mar"] ** 2) / math.log(densities["central"])
    exponents = {}
    for pitch_type, components in k["por_tipo"].items():
        exponents[pitch_type] = {}
        for component in ("ivb", "hb"):
            entry = components[component]
            if not entry["usa_propio"]:
                continue
            exponents[pitch_type][component] = {
                "k_frenado": round(entry["k_usado"], 2),
                "k_densidad": round(entry["k_usado"] * factors["central"], 2),
                "k_densidad_rango_temperatura": [round(entry["k_usado"] * f, 2) for f in factors["rango"]],
                "k_densidad_ic95": [round(v * factors["central"], 2) for v in entry["ic95"]],
            }
    summary = {
        "nota": "Atmósfera estándar y temperaturas de juego supuestas; no hay datos de clima ni de estadio (D-041).",
        "presion_harp_kpa": round(pressure(HARP_ALTITUDE_M) / 1000, 1),
        "densidad_relativa_harp": {"central": round(densities["central"], 3), "rango": [round(low, 3), round(high, 3)]},
        "frenado_relativo_medido": round(air, 4),
        "cd_relativo_implicito": {"central": round(air / densities["central"], 3), "rango": [round(air / high, 3), round(air / low, 3)]},
        "factor_k_a_densidad": {"central": round(factors["central"], 3), "rango": [round(f, 3) for f in factors["rango"]]},
        "k_densidad_esperado_por_la_fisica": round(expected, 2),
        "k_liga_total": {"k_frenado": k["liga"]["movimiento_total"]["k"],
                         "k_densidad": round(k["liga"]["movimiento_total"]["k"] * factors["central"], 2)},
        "por_tipo": exponents,
        "tiempo_de_vuelo_recta": flight,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
