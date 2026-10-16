"""
Location+ con XGBoost, para comparar contra la red de PyTorch de location_plus.py.

Lo único que cambia es el modelo. Todo lo demás se reutiliza de location_plus.py:
mismas columnas, mismo run value (run_value.py), mismo árbol de resultados, misma partición
de validación por juegos, mismas fórmulas de xCSW / xRV y mismo cálculo de Location+.

En lugar de una red con 10 salidas se entrena un modelo por cabeza, cada uno solo con su población:
    1. P(swing)                          -> todos los pitches
    2. P(whiff | swing)                  -> pitches con swing
    3. P(called strike | take)           -> pitches sin swing
    4. P(HBP | take sin strike)          -> takes que no fueron called strike
    5. P(foul | contacto)                -> swings con contacto
    6. P(OUT, 1B, 2B, 3B, HR | en juego) -> bolas en juego (multi:softprob)

XGBoost maneja las categóricas de forma nativa, así que no se usa one-hot ni estandarización.
Las salidas llevan el sufijo _xgb para no pisar las de la red.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from location_plus import (CABEZAS_BINARIAS, CLASES_EN_JUEGO, SEMILLA, agregar_predicciones,
                           columnas_modelo, columnas_numericas, etiquetas, guardar, preparar_datos, reportar,
                           separar_validacion)

CARPETA_MODELOS = 'location_plus_xgb_modelos'

# Hiperparámetros compartidos por todas las cabezas; n_estimators es el máximo, lo corta el early stopping
PARAMETROS = dict(
    n_estimators=2000,
    learning_rate=0.05,
    max_depth=6,
    min_child_weight=50,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    tree_method='hist',
    enable_categorical=True,
    early_stopping_rounds=50,
    random_state=SEMILLA,
    n_jobs=-1,
)


def matriz(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas del modelo: numéricas como float y categóricas como category (las usa XGBoost directo)."""
    X = df[columnas_modelo].copy()
    X[columnas_numericas] = X[columnas_numericas].astype('float32')
    return X


def entrenar(train: pd.DataFrame) -> dict[str, XGBClassifier]:
    es_val = separar_validacion(train)
    X_tr, X_val = matriz(train[~es_val]), matriz(train[es_val])
    e_tr, e_val = etiquetas(train[~es_val]), etiquetas(train[es_val])

    modelos = {}
    for cabeza in CABEZAS_BINARIAS:
        tr, val = e_tr[cabeza].notna().to_numpy(), e_val[cabeza].notna().to_numpy()
        modelo = XGBClassifier(objective='binary:logistic', eval_metric='logloss', **PARAMETROS)
        modelo.fit(X_tr[tr], e_tr.loc[tr, cabeza].astype(int), eval_set=[(X_val[val], e_val.loc[val, cabeza].astype(int))],
                   verbose=False)
        print(f"  {cabeza:<26} n={tr.sum():>7,}  árboles={modelo.best_iteration + 1:>4}  "
              f"logloss val={modelo.best_score:.4f}")
        modelos[cabeza] = modelo

    tr, val = (e_tr['clase_en_juego'] >= 0).to_numpy(), (e_val['clase_en_juego'] >= 0).to_numpy()
    modelo = XGBClassifier(objective='multi:softprob', num_class=len(CLASES_EN_JUEGO), eval_metric='mlogloss',
                           **PARAMETROS)
    modelo.fit(X_tr[tr], e_tr.loc[tr, 'clase_en_juego'], eval_set=[(X_val[val], e_val.loc[val, 'clase_en_juego'])],
               verbose=False)
    print(f"  {'resultado_en_juego':<26} n={tr.sum():>7,}  árboles={modelo.best_iteration + 1:>4}  "
          f"mlogloss val={modelo.best_score:.4f}")
    modelos['resultado_en_juego'] = modelo
    return modelos


def predecir_proba(modelos: dict[str, XGBClassifier], df: pd.DataFrame) -> np.ndarray:
    """Mismo orden de columnas que predecir_proba de la red: 5 binarias y luego las 5 clases en juego."""
    X = matriz(df)
    binarias = [modelos[c].predict_proba(X)[:, 1] for c in CABEZAS_BINARIAS]
    return np.column_stack(binarias + [modelos['resultado_en_juego'].predict_proba(X)])


def main() -> None:
    rv, train, test = preparar_datos()

    print("Entrenando XGBoost (un modelo por cabeza):")
    modelos = entrenar(train)
    Path(CARPETA_MODELOS).mkdir(exist_ok=True)
    for cabeza, modelo in modelos.items():
        modelo.save_model(f'{CARPETA_MODELOS}/{cabeza}.json')

    test = agregar_predicciones(test, predecir_proba(modelos, test), rv)
    lp_pitcher, lp_pitch = reportar(train, test)
    archivos = guardar(rv, test, lp_pitcher, lp_pitch, sufijo='_xgb')
    print(f"\nGuardado: {CARPETA_MODELOS}/, " + ", ".join(archivos))


if __name__ == '__main__':
    main()
