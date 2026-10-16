"""
Location+ : mide la calidad de la ubicación de un pitch con una red neuronal (PyTorch).

Una sola red con tronco compartido modela el árbol de resultados de un pitch
(solo usa las columnas de `columnas_modelo`):
    1. P(swing)                         -> todos los pitches
    2. P(whiff | swing)                 -> pitches con swing
    3. P(called strike | take)          -> pitches sin swing
    4. P(HBP | take sin strike)         -> takes que no fueron called strike
    5. P(foul | contacto)               -> swings con contacto
    6. P(OUT, 1B, 2B, 3B, HR | en juego) -> bolas en juego (softmax)

Con ellas se calculan dos métricas esperadas por pitch:
    xCSW = P(swing) * P(whiff | swing) + (1 - P(swing)) * P(called strike | take)
    xRV  = suma sobre resultados de P(resultado) * RV(resultado | cuenta)
donde RV viene de run_value.py (misma construcción que la rama Max: pesos lineales por
media entrada + valores de cuenta con cadena de Markov). xRV negativo = bueno para el pitcher.

Location+ por pitcher (y por pitch_group) combina ambas, cada una residualizada contra el
promedio de la liga en la misma cuenta y en escala "plus" (100 = liga, ±10 = ±1 desv. est.):
    CSW+      = 100 + 10 * xCSW_resid / desv
    RV+       = 100 - 10 * xRV_resid  / desv
    Location+ = 100 + 10 * z_combinado / desv,  z_combinado = PESO_CSW * z_CSW + (1 - PESO_CSW) * z_RV

Train = split 'train' (2024-2025), test = split 'holdout' (2026).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import torch
from torch import nn
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from run_value import COLUMNAS_RV, RunValue, transiciones

ARCHIVO = Path(__file__).parent / "pitches_limpios.parquet"

columnas_contexto = ['Balls', 'Strikes', 'count', 'Outs', 'Inning', 'Top/Bottom', 'altitude_category']
columnas_loc = ['PlateLocHeight', 'PlateLocSide', 'in_strike_zone', 'outside_strike_zone']
# Lateralidad: PlateLocSide significa "adentro" o "afuera" según la mano del pitcher y el lado del bateador
columnas_mano = ['pitcher_hand', 'batter_side']

columnas_modelo = columnas_contexto + columnas_loc + columnas_mano
columnas_categoricas = ['count', 'Top/Bottom', 'altitude_category', 'pitcher_hand', 'batter_side']
columnas_numericas = [c for c in columnas_modelo if c not in columnas_categoricas]

# Columnas que NO entran al modelo: objetivos, split e identificadores para agregar
columnas_objetivo = ['is_swing', 'is_whiff', 'is_called_strike']
columnas_id = ['split', 'game_anon_id', 'pitcher_anon_id', 'pitch_group']

# Cabezas binarias (sigmoide) seguidas de las clases de bola en juego (softmax)
CABEZAS_BINARIAS = ['swing', 'whiff_dado_swing', 'called_strike_dado_take', 'hbp_dado_take_no_strike',
                    'foul_dado_contacto']
CLASES_EN_JUEGO = ['OUT', '1B', '2B', '3B', 'HR']
# E, SAC y FC valen lo mismo que OUT en run_value.py, así que se agrupan con OUT
CLASE_DE_EVENTO = {'OUT': 0, 'E': 0, 'SAC': 0, 'FC': 0, '1B': 1, '2B': 2, '3B': 3, 'HR': 4}
FOULS = ['FoulBall', 'FoulBallNotFieldable', 'FoulBallFieldable']

MIN_PITCHES_PITCHER = 200
MIN_PITCHES_PITCH_GROUP = 75
# Peso de CSW frente a run value en Location+ (0.5 = mitad y mitad)
PESO_CSW = 0.5

# Hiperparámetros de la red
CAPAS_OCULTAS = [128, 64, 32]
DROPOUT = 0.1
BATCH_SIZE = 2048
LR = 1e-3
EPOCAS_MAX = 40
PACIENCIA = 4
FRACCION_VALIDACION = 0.1
SEMILLA = 42

DEVICE = torch.device('mps' if torch.backends.mps.is_available()
                      else 'cuda' if torch.cuda.is_available() else 'cpu')


def cargar_datos() -> pd.DataFrame:
    """Lee solo las columnas necesarias con pyarrow. No filtra: el run value necesita las medias entradas completas."""
    columnas = list(dict.fromkeys(columnas_modelo + columnas_objetivo + columnas_id + COLUMNAS_RV))
    tabla = pq.read_table(ARCHIVO, columns=columnas)

    for c in ['altitude_category', 'batter_side']:
        tabla = tabla.set_column(tabla.schema.get_field_index(c), c, pc.fill_null(tabla[c], 'Unknown'))

    df = tabla.to_pandas()
    # Categorías fijas en todo el df para que train y holdout tengan las mismas columnas one-hot
    for c in columnas_categoricas:
        df[c] = df[c].astype('category')
    return df


def filtrar_para_modelo(df: pd.DataFrame) -> pd.DataFrame:
    """Pitches con resultado definido y cuenta válida."""
    ok = (df['PitchCall'].ne('Undefined') & df['is_swing'].notna() &
          df['Balls'].between(0, 3) & df['Strikes'].between(0, 2))
    return df[ok].copy()


class Preprocesador:
    """One-hot para categóricas y estandarización (con media/desv. de train) para numéricas."""

    def fit(self, df: pd.DataFrame) -> 'Preprocesador':
        num = df[columnas_numericas].astype('float32')
        self.media = num.mean()
        self.desv = num.std().replace(0, 1)
        return self

    def transform(self, df: pd.DataFrame) -> torch.Tensor:
        num = (df[columnas_numericas].astype('float32') - self.media) / self.desv
        cat = pd.get_dummies(df[columnas_categoricas], dtype='float32')
        X = np.hstack([num.to_numpy(np.float32), cat.to_numpy(np.float32)])
        return torch.from_numpy(X)


class RedLocation(nn.Module):
    """Tronco compartido + cabezas (logits): 5 binarias y 5 clases de bola en juego."""

    def __init__(self, n_entradas: int):
        super().__init__()
        capas, n = [], n_entradas
        for h in CAPAS_OCULTAS:
            capas += [nn.Linear(n, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(DROPOUT)]
            n = h
        self.tronco = nn.Sequential(*capas)
        self.cabezas = nn.Linear(n, len(CABEZAS_BINARIAS) + len(CLASES_EN_JUEGO))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.cabezas(self.tronco(x))


def etiquetas(df: pd.DataFrame) -> pd.DataFrame:
    """Etiquetas de cada cabeza y la máscara de su población (NaN = el pitch no cuenta para esa cabeza)."""
    swing = df['is_swing'].to_numpy(bool)
    whiff = df['is_whiff'].to_numpy(bool)
    cs = df['is_called_strike'].to_numpy(bool)
    hbp = df['PitchCall'].eq('HitByPitch').to_numpy()
    evento = transiciones(df)['evento']
    # Un foul fildeable atrapado termina en OUT: cuenta como bola en juego, no como foul
    foul = (df['PitchCall'].isin(FOULS) & evento.ne('OUT')).to_numpy()
    contacto = swing & ~whiff
    clase = evento.map(CLASE_DE_EVENTO).fillna(-1).astype(int).to_numpy()

    return pd.DataFrame({
        'swing': swing.astype(float),
        'whiff_dado_swing': np.where(swing, whiff, np.nan),
        'called_strike_dado_take': np.where(~swing, cs, np.nan),
        'hbp_dado_take_no_strike': np.where(~swing & ~cs, hbp, np.nan),
        'foul_dado_contacto': np.where(contacto, foul, np.nan),
        'clase_en_juego': np.where(contacto & ~foul, clase, -1),
    }, index=df.index)


def objetivos(df: pd.DataFrame) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Devuelve (y, máscara) de forma (n, 5) para las binarias y la clase en juego (-1 = no aplica)."""
    e = etiquetas(df)
    binarias = e[CABEZAS_BINARIAS].to_numpy(np.float32)
    mascara = ~np.isnan(binarias)
    return (torch.from_numpy(np.nan_to_num(binarias)), torch.from_numpy(mascara.astype(np.float32)),
            torch.from_numpy(e['clase_en_juego'].to_numpy(np.int64)))


def perdida(logits: torch.Tensor, y: torch.Tensor, mascara: torch.Tensor, clase: torch.Tensor) -> torch.Tensor:
    """BCE promedio de cada cabeza binaria sobre su población + entropía cruzada de las bolas en juego."""
    nb = len(CABEZAS_BINARIAS)
    bce = nn.functional.binary_cross_entropy_with_logits(logits[:, :nb], y, reduction='none') * mascara
    total = (bce.sum(0) / mascara.sum(0).clamp(min=1)).sum()
    en_juego = clase >= 0
    if en_juego.any():
        total = total + nn.functional.cross_entropy(logits[en_juego, nb:], clase[en_juego])
    return total


@torch.no_grad()
def predecir_proba(modelo: RedLocation, X: torch.Tensor) -> np.ndarray:
    """Columnas: probabilidades de las 5 cabezas binarias y luego las 5 clases en juego."""
    modelo.eval()
    nb = len(CABEZAS_BINARIAS)
    salidas = []
    for i in range(0, len(X), 65536):
        logits = modelo(X[i:i + 65536].to(DEVICE))
        salidas.append(torch.cat([torch.sigmoid(logits[:, :nb]), torch.softmax(logits[:, nb:], dim=1)], dim=1).cpu())
    return torch.cat(salidas).numpy()


def entrenar(train: pd.DataFrame) -> tuple[RedLocation, Preprocesador]:
    torch.manual_seed(SEMILLA)
    rng = np.random.default_rng(SEMILLA)

    # Validación dentro de train para early stopping (el holdout solo se usa al final).
    # Se separa por juego, no por pitch, para que pitches del mismo juego no queden en ambos lados.
    juegos = train['game_anon_id'].unique()
    juegos_val = rng.choice(juegos, size=int(len(juegos) * FRACCION_VALIDACION), replace=False)
    es_val = train['game_anon_id'].isin(juegos_val).to_numpy()
    tr, val = train[~es_val], train[es_val]

    prep = Preprocesador().fit(tr)
    X_tr, (y_tr, m_tr, c_tr) = prep.transform(tr), objetivos(tr)
    X_val = prep.transform(val).to(DEVICE)
    y_val, m_val, c_val = (t.to(DEVICE) for t in objetivos(val))

    modelo = RedLocation(X_tr.shape[1]).to(DEVICE)
    optimizador = torch.optim.AdamW(modelo.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizador, factor=0.5, patience=1)

    mejor_val, mejor_estado, sin_mejora = float('inf'), None, 0
    for epoca in range(1, EPOCAS_MAX + 1):
        modelo.train()
        orden = torch.randperm(len(X_tr))
        total = 0.0
        for i in range(0, len(orden), BATCH_SIZE):
            idx = orden[i:i + BATCH_SIZE]
            xb, yb, mb, cb = (t[idx].to(DEVICE) for t in (X_tr, y_tr, m_tr, c_tr))
            optimizador.zero_grad()
            loss = perdida(modelo(xb), yb, mb, cb)
            loss.backward()
            optimizador.step()
            total += loss.item() * len(idx)

        modelo.eval()
        with torch.no_grad():
            loss_val = perdida(modelo(X_val), y_val, m_val, c_val).item()
        scheduler.step(loss_val)
        print(f"  época {epoca:>2}  loss train={total / len(X_tr):.4f}  loss val={loss_val:.4f}")

        if loss_val < mejor_val - 1e-4:
            mejor_val, sin_mejora = loss_val, 0
            mejor_estado = {k: v.detach().clone() for k, v in modelo.state_dict().items()}
        else:
            sin_mejora += 1
            if sin_mejora >= PACIENCIA:
                print(f"  early stopping (mejor loss val={mejor_val:.4f})")
                break

    modelo.load_state_dict(mejor_estado)
    return modelo, prep


def evaluar(nombre: str, y: np.ndarray, p: np.ndarray, p_base: float) -> None:
    base = np.full_like(p, p_base, dtype=float)
    print(f"  {nombre:<26} n={len(y):>7,}  tasa={y.mean():.3f}  "
          f"AUC={roc_auc_score(y, p):.3f}  "
          f"LogLoss={log_loss(y, p):.4f} (base {log_loss(y, base):.4f})  "
          f"Brier={brier_score_loss(y, p):.4f} (base {brier_score_loss(y, base):.4f})")


def predecir(modelo: RedLocation, prep: Preprocesador, rv: RunValue, df: pd.DataFrame) -> pd.DataFrame:
    proba = predecir_proba(modelo, prep.transform(df))
    df = df.copy()
    p_swing, p_whiff_swing, p_cs_take, p_hbp_take, p_foul_contacto = proba[:, :len(CABEZAS_BINARIAS)].T
    p_clases = proba[:, len(CABEZAS_BINARIAS):]
    df['p_swing'], df['p_whiff_swing'], df['p_cs_take'] = p_swing, p_whiff_swing, p_cs_take
    df['p_hbp_take'], df['p_foul_contacto'] = p_hbp_take, p_foul_contacto
    for i, c in enumerate(CLASES_EN_JUEGO):
        df[f'p_{c}_en_juego'] = p_clases[:, i]

    # Probabilidad de cada resultado final del pitch (suman 1)
    df['p_whiff'] = p_swing * p_whiff_swing
    df['p_called_strike'] = (1 - p_swing) * p_cs_take
    p_hbp = (1 - p_swing) * (1 - p_cs_take) * p_hbp_take
    p_bola = (1 - p_swing) * (1 - p_cs_take) * (1 - p_hbp_take)
    p_foul = p_swing * (1 - p_whiff_swing) * p_foul_contacto
    p_en_juego = p_swing * (1 - p_whiff_swing) * (1 - p_foul_contacto)

    df['xCSW'] = df['p_whiff'] + df['p_called_strike']
    df['CSW'] = df['is_whiff'] + df['is_called_strike']

    valor = rv.valores_por_resultado(df['Balls'].to_numpy(), df['Strikes'].to_numpy())
    df['xRV'] = (p_bola * valor['bola'] + p_hbp * valor['hbp'] + df['xCSW'] * valor['strike']
                 + p_foul * valor['foul'] + p_en_juego * (p_clases * valor['en_juego']).sum(axis=1))
    df['RV'] = rv.transform(df)
    return df


def calcular_location_plus(df: pd.DataFrame, por: list, min_pitches: int) -> pd.DataFrame:
    # Residuo vs. el promedio de la liga en la misma cuenta, para que la cuenta no se acredite como ubicación
    df = df.assign(**{f'{c}_resid': df[c] - df.groupby('count', observed=True)[c].transform('mean')
                      for c in ['xCSW', 'xRV']})

    res = (df.groupby(por, observed=True)
             .agg(pitches=('xCSW', 'size'),
                  xCSW=('xCSW', 'mean'),
                  CSW=('CSW', 'mean'),
                  p_whiff=('p_whiff', 'mean'),
                  p_called_strike=('p_called_strike', 'mean'),
                  xRV=('xRV', 'mean'),
                  RV=('RV', 'mean'),
                  xCSW_resid=('xCSW_resid', 'mean'),
                  xRV_resid=('xRV_resid', 'mean'))
             .reset_index())
    res = res[res['pitches'] >= min_pitches].copy()

    # Escala plus como el Stuff+ de Max: 100 ± 10 por desv. estándar poblacional (ddof=0).
    # Se centra en residuo 0 = promedio de la liga en la misma cuenta. En RV, menos es mejor.
    z_csw = res['xCSW_resid'] / res['xCSW_resid'].std(ddof=0)
    z_rv = -res['xRV_resid'] / res['xRV_resid'].std(ddof=0)
    z = PESO_CSW * z_csw + (1 - PESO_CSW) * z_rv
    res['CSW+'] = 100 + 10 * z_csw
    res['RV+'] = 100 + 10 * z_rv
    res['Location+'] = 100 + 10 * z / z.std(ddof=0)
    return res.sort_values('Location+', ascending=False).reset_index(drop=True)


def main() -> None:
    df = cargar_datos()

    rv = RunValue.fit(df[df['split'] == 'train'])
    print(f"Run value ajustado con {rv.diagnostico['medias_entradas_completas']:,} medias entradas completas de train")
    print("  Pesos: " + "  ".join(f"{e}={w:+.3f}" for e, w in rv.pesos.items()))
    print("  V(cuenta):\n" + pd.DataFrame(rv.valores_cuenta.reshape(4, 3), index=[f'{b} bolas' for b in range(4)],
                                          columns=[f'{s} strikes' for s in range(3)]).round(4).to_string())

    df = filtrar_para_modelo(df)
    train = df[df['split'] == 'train']
    test = df[df['split'] == 'holdout']
    print(f"\nTrain: {len(train):,} pitches | Holdout: {len(test):,} pitches | device: {DEVICE}\n")

    print("Entrenando red neuronal:")
    modelo, prep = entrenar(train)
    torch.save({'estado': modelo.state_dict(), 'media': prep.media, 'desv': prep.desv, 'run_value': rv.as_dict()},
               'location_plus_red.pt')

    test = predecir(modelo, prep, rv, test)

    print("\nMétricas en holdout (base = tasa de entrenamiento constante):")
    e_tr, e_te = etiquetas(train), etiquetas(test)
    columnas_p = ['p_swing', 'p_whiff_swing', 'p_cs_take', 'p_hbp_take', 'p_foul_contacto']
    for cabeza, col_p in zip(CABEZAS_BINARIAS, columnas_p):
        aplica = e_te[cabeza].notna()
        evaluar(cabeza, e_te.loc[aplica, cabeza].to_numpy(), test.loc[aplica, col_p].to_numpy(),
                e_tr[cabeza].mean())
    en_juego = e_te['clase_en_juego'] >= 0
    base = np.bincount(e_tr.loc[e_tr['clase_en_juego'] >= 0, 'clase_en_juego'], minlength=len(CLASES_EN_JUEGO))
    p_clases = test.loc[en_juego, [f'p_{c}_en_juego' for c in CLASES_EN_JUEGO]].to_numpy()
    y_clases = e_te.loc[en_juego, 'clase_en_juego'].to_numpy()
    print(f"  {'resultado_en_juego':<26} n={en_juego.sum():>7,}  "
          f"LogLoss={log_loss(y_clases, p_clases, labels=range(len(CLASES_EN_JUEGO))):.4f} "
          f"(base {log_loss(y_clases, np.tile(base / base.sum(), (len(y_clases), 1)), labels=range(len(CLASES_EN_JUEGO))):.4f})")

    print(f"\nxCSW medio holdout = {test['xCSW'].mean():.3f}  |  CSW real = {test['CSW'].mean():.3f}")
    print(f"Correlación pitch a pitch xCSW vs CSW: {np.corrcoef(test['xCSW'], test['CSW'])[0, 1]:.3f}")
    con_rv = test['RV'].notna()
    print(f"xRV medio holdout = {test['xRV'].mean():+.4f}  |  RV real = {test.loc[con_rv, 'RV'].mean():+.4f}")
    print(f"Correlación pitch a pitch xRV vs RV: {np.corrcoef(test.loc[con_rv, 'xRV'], test.loc[con_rv, 'RV'])[0, 1]:.3f}")
    print("Calibración por cuenta (xRV vs RV real):")
    print(test[con_rv].groupby('count', observed=True)[['xRV', 'RV']].mean().round(4).T.to_string())

    lp_pitcher = calcular_location_plus(test, ['pitcher_anon_id'], MIN_PITCHES_PITCHER)
    lp_pitch = calcular_location_plus(test, ['pitcher_anon_id', 'pitch_group'], MIN_PITCHES_PITCH_GROUP)

    print(f"\nTop 10 Location+ por pitcher (holdout, >= {MIN_PITCHES_PITCHER} pitches, PESO_CSW={PESO_CSW}):")
    print(lp_pitcher.head(10).to_string(index=False, float_format='%.3f'))
    print("\nCorrelaciones por pitcher:")
    for col in ['Location+', 'CSW+', 'RV+']:
        print(f"  {col:<10} vs CSW real: {lp_pitcher[col].corr(lp_pitcher['CSW']):+.3f}   "
              f"vs RV real: {lp_pitcher[col].corr(lp_pitcher['RV']):+.3f}")

    with open('run_value_tablas.json', 'w') as f:
        json.dump(rv.as_dict(), f, indent=2)
    pq.write_table(pa.Table.from_pandas(lp_pitcher, preserve_index=False), 'location_plus_pitcher.parquet')
    pq.write_table(pa.Table.from_pandas(lp_pitch, preserve_index=False), 'location_plus_pitcher_pitch.parquet')
    print("\nGuardado: location_plus_red.pt, run_value_tablas.json, location_plus_pitcher.parquet, "
          "location_plus_pitcher_pitch.parquet")


if __name__ == '__main__':
    main()
