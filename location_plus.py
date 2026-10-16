"""
Location+ : mide la calidad de la ubicación de un pitch con una red neuronal (PyTorch).

Una sola red con tronco compartido y tres salidas (solo usa las columnas de `columnas_modelo`):
    1. P(swing)                    -> se entrena con todos los pitches
    2. P(whiff | swing)            -> se entrena solo con pitches con swing
    3. P(called strike | take)     -> se entrena solo con pitches sin swing

Con ellas se calcula la probabilidad esperada de CSW (called strike + whiff):
    xCSW = P(swing) * P(whiff | swing) + (1 - P(swing)) * P(called strike | take)

Location+ por pitcher (y por pitch_group) compara su xCSW contra el xCSW promedio
de la liga en las mismas cuentas, en escala "plus" (100 = promedio de la liga):
    Location+ = 100 * (xCSW_liga + residuo_promedio_pitcher) / xCSW_liga

Train = split 'train' (2024-2025), test = split 'holdout' (2026).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import torch
from torch import nn
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

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

MIN_PITCHES_PITCHER = 200
MIN_PITCHES_PITCH_GROUP = 75

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
    """Lee solo las columnas necesarias con pyarrow y filtra pitches sin resultado definido."""
    tabla = pq.read_table(
        ARCHIVO,
        columns=columnas_modelo + columnas_objetivo + columnas_id,
        filters=[('PitchCall', '!=', 'Undefined')],
    )
    tabla = tabla.filter(pc.is_valid(tabla['is_swing']))

    for c in ['altitude_category', 'batter_side']:
        tabla = tabla.set_column(tabla.schema.get_field_index(c), c, pc.fill_null(tabla[c], 'Unknown'))

    df = tabla.to_pandas()
    # Categorías fijas en todo el df para que train y holdout tengan las mismas columnas one-hot
    for c in columnas_categoricas:
        df[c] = df[c].astype('category')
    return df


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
    """Tronco compartido + 3 cabezas (logits): swing, whiff|swing, called strike|take."""

    def __init__(self, n_entradas: int):
        super().__init__()
        capas, n = [], n_entradas
        for h in CAPAS_OCULTAS:
            capas += [nn.Linear(n, h), nn.BatchNorm1d(h), nn.ReLU(), nn.Dropout(DROPOUT)]
            n = h
        self.tronco = nn.Sequential(*capas)
        self.cabezas = nn.Linear(n, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.cabezas(self.tronco(x))


def objetivos(df: pd.DataFrame) -> tuple[torch.Tensor, torch.Tensor]:
    """Devuelve (y, máscara) de forma (n, 3). La máscara indica qué pitches cuentan para cada cabeza."""
    swing = df['is_swing'].to_numpy(np.float32)
    y = np.stack([swing,
                  df['is_whiff'].to_numpy(np.float32),
                  df['is_called_strike'].to_numpy(np.float32)], axis=1)
    mascara = np.stack([np.ones_like(swing), swing, 1 - swing], axis=1)
    return torch.from_numpy(y), torch.from_numpy(mascara)


def perdida(logits: torch.Tensor, y: torch.Tensor, mascara: torch.Tensor) -> torch.Tensor:
    """BCE promedio de cada cabeza, solo sobre los pitches de su población; suma de las 3."""
    bce = nn.functional.binary_cross_entropy_with_logits(logits, y, reduction='none') * mascara
    return (bce.sum(0) / mascara.sum(0).clamp(min=1)).sum()


@torch.no_grad()
def predecir_proba(modelo: RedLocation, X: torch.Tensor) -> np.ndarray:
    modelo.eval()
    salidas = [torch.sigmoid(modelo(X[i:i + 65536].to(DEVICE))).cpu()
               for i in range(0, len(X), 65536)]
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
    X_tr, (y_tr, m_tr) = prep.transform(tr), objetivos(tr)
    X_val, (y_val, m_val) = prep.transform(val).to(DEVICE), objetivos(val)
    y_val, m_val = y_val.to(DEVICE), m_val.to(DEVICE)

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
            xb, yb, mb = X_tr[idx].to(DEVICE), y_tr[idx].to(DEVICE), m_tr[idx].to(DEVICE)
            optimizador.zero_grad()
            loss = perdida(modelo(xb), yb, mb)
            loss.backward()
            optimizador.step()
            total += loss.item() * len(idx)

        modelo.eval()
        with torch.no_grad():
            loss_val = perdida(modelo(X_val), y_val, m_val).item()
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


def predecir(modelo: RedLocation, prep: Preprocesador, df: pd.DataFrame) -> pd.DataFrame:
    proba = predecir_proba(modelo, prep.transform(df))
    df = df.copy()
    df['p_swing'], df['p_whiff_swing'], df['p_cs_take'] = proba[:, 0], proba[:, 1], proba[:, 2]

    df['p_whiff'] = df['p_swing'] * df['p_whiff_swing']
    df['p_called_strike'] = (1 - df['p_swing']) * df['p_cs_take']
    df['xCSW'] = df['p_whiff'] + df['p_called_strike']
    df['CSW'] = df['is_whiff'] + df['is_called_strike']
    return df


def calcular_location_plus(df: pd.DataFrame, por: list, min_pitches: int) -> pd.DataFrame:
    # Residuo vs. el promedio de la liga en la misma cuenta, para que la cuenta no se acredite como ubicación
    df = df.assign(xCSW_resid=df['xCSW'] - df.groupby('count', observed=True)['xCSW'].transform('mean'))
    xcsw_liga = df['xCSW'].mean()

    res = (df.groupby(por, observed=True)
             .agg(pitches=('xCSW', 'size'),
                  xCSW=('xCSW', 'mean'),
                  CSW=('CSW', 'mean'),
                  p_whiff=('p_whiff', 'mean'),
                  p_called_strike=('p_called_strike', 'mean'),
                  xCSW_resid=('xCSW_resid', 'mean'))
             .reset_index())
    res = res[res['pitches'] >= min_pitches]
    res['Location+'] = 100 * (xcsw_liga + res['xCSW_resid']) / xcsw_liga
    return res.sort_values('Location+', ascending=False).reset_index(drop=True)


def main() -> None:
    df = cargar_datos()
    train = df[df['split'] == 'train']
    test = df[df['split'] == 'holdout']
    print(f"Train: {len(train):,} pitches | Holdout: {len(test):,} pitches | device: {DEVICE}\n")

    print("Entrenando red neuronal:")
    modelo, prep = entrenar(train)
    torch.save({'estado': modelo.state_dict(), 'media': prep.media, 'desv': prep.desv},
               'location_plus_red.pt')

    test = predecir(modelo, prep, test)

    print("\nMétricas en holdout (base = tasa de entrenamiento constante):")
    swing = test['is_swing'] == 1
    evaluar('swing', test['is_swing'].to_numpy(), test['p_swing'].to_numpy(), train['is_swing'].mean())
    evaluar('whiff_dado_swing', test.loc[swing, 'is_whiff'].to_numpy(),
            test.loc[swing, 'p_whiff_swing'].to_numpy(), train.loc[train['is_swing'] == 1, 'is_whiff'].mean())
    evaluar('called_strike_dado_take', test.loc[~swing, 'is_called_strike'].to_numpy(),
            test.loc[~swing, 'p_cs_take'].to_numpy(),
            train.loc[train['is_swing'] == 0, 'is_called_strike'].mean())

    print(f"\nxCSW medio holdout = {test['xCSW'].mean():.3f}  |  CSW real = {test['CSW'].mean():.3f}")
    print(f"Correlación pitch a pitch xCSW vs CSW: {np.corrcoef(test['xCSW'], test['CSW'])[0, 1]:.3f}")

    lp_pitcher = calcular_location_plus(test, ['pitcher_anon_id'], MIN_PITCHES_PITCHER)
    lp_pitch = calcular_location_plus(test, ['pitcher_anon_id', 'pitch_group'], MIN_PITCHES_PITCH_GROUP)

    print(f"\nTop 10 Location+ por pitcher (holdout, >= {MIN_PITCHES_PITCHER} pitches):")
    print(lp_pitcher.head(10).to_string(index=False, float_format='%.3f'))
    print(f"\nCorrelación Location+ vs CSW real (pitchers): "
          f"{lp_pitcher['Location+'].corr(lp_pitcher['CSW']):.3f}")

    pq.write_table(pa.Table.from_pandas(lp_pitcher, preserve_index=False), 'location_plus_pitcher.parquet')
    pq.write_table(pa.Table.from_pandas(lp_pitch, preserve_index=False), 'location_plus_pitcher_pitch.parquet')
    print("\nGuardado: location_plus_red.pt, location_plus_pitcher.parquet, location_plus_pitcher_pitch.parquet")


if __name__ == '__main__':
    main()
