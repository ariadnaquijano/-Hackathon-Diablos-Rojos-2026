"""
Run value por pitch, construido igual que en la rama Max (stuffplus/target.py, sección 6 de
docs/STUFFPLUS_MODEL_GUIDE.md). Se ajusta SOLO con train para no filtrar el holdout.

1. Cada pitch se clasifica con su propio PitchCall y cuenta: o pasa a otra cuenta o termina
   el turno con un evento (1B, 2B, 3B, HR, BB, HBP, K, OUT, E, SAC, FC).
2. Pesos lineales: OLS sin intercepto de carreras por media entrada completa contra el conteo
   de eventos. E, SAC y FC se reemplazan por el peso de OUT (no se le cobran al pitcher).
3. Valor de cada cuenta V(c) con una cadena de Markov absorbente: (I - Q) V = r.
4. RV del pitch:  no terminal = V(cuenta después) - V(cuenta antes)
                  terminal    = peso(evento)      - V(cuenta antes)
Negativo = bueno para el pitcher. No hay corredores en base en los datos, así que los pesos
son promedios (un sencillo vale lo mismo con bases vacías que llenas).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

EVENTOS = ('1B', '2B', '3B', 'HR', 'BB', 'HBP', 'K', 'OUT', 'E', 'SAC', 'FC')
EVENTO_EN_JUEGO = {'Single': '1B', 'Double': '2B', 'Triple': '3B', 'HomeRun': 'HR',
                   'Out': 'OUT', 'Error': 'E', 'Sacrifice': 'SAC', 'FieldersChoice': 'FC'}

# Columnas que necesita el ajuste (además de las del modelo)
COLUMNAS_RV = ['year', 'game_anon_id', 'Inning', 'Top/Bottom', 'Outs', 'OutsOnPlay', 'RunsScored',
               'Balls', 'Strikes', 'PitchCall', 'play_result']


def transiciones(df: pd.DataFrame) -> pd.DataFrame:
    """Evento terminal o siguiente cuenta, usando solo el resultado registrado del propio pitch."""
    b, s = df['Balls'], df['Strikes']
    valida = b.between(0, 3) & s.between(0, 2)
    estado = (3 * b + s).where(valida, 0).astype(int)
    evento = pd.Series('', index=df.index, dtype='str')
    siguiente = pd.Series(-1, index=df.index, dtype=int)
    call = df['PitchCall']

    bola = call.isin(['BallCalled', 'BallinDirt'])
    strike = call.isin(['StrikeCalled', 'StrikeSwinging'])
    foul = call.isin(['FoulBall', 'FoulBallNotFieldable'])
    siguiente[bola & (b < 3)] = estado[bola & (b < 3)] + 3
    evento[bola & (b == 3)] = 'BB'
    siguiente[strike & (s < 2)] = estado[strike & (s < 2)] + 1
    evento[strike & (s == 2)] = 'K'
    siguiente[foul] = estado[foul] + (s[foul] < 2).astype(int)
    evento[call.eq('HitByPitch')] = 'HBP'
    en_juego = call.eq('InPlay')
    evento[en_juego] = df.loc[en_juego, 'play_result'].map(EVENTO_EN_JUEGO).fillna('')
    # "Fieldable" no significa atrapado: se exige un out registrado
    fildeable = call.eq('FoulBallFieldable')
    atrapado = fildeable & (df['OutsOnPlay'].gt(0) | df['play_result'].eq('Out'))
    evento[atrapado] = 'OUT'
    no_atrapado = fildeable & ~atrapado
    siguiente[no_atrapado] = estado[no_atrapado] + (s[no_atrapado] < 2).astype(int)

    conocida = valida & (evento.ne('') | siguiente.ge(0))
    return pd.DataFrame({'estado': estado, 'siguiente': siguiente, 'evento': evento,
                         'conocida': conocida}, index=df.index)


@dataclass
class RunValue:
    pesos: dict
    valores_cuenta: np.ndarray  # V(c), índice = 3 * balls + strikes
    diagnostico: dict

    @classmethod
    def fit(cls, df: pd.DataFrame) -> 'RunValue':
        t = transiciones(df)
        trabajo = df[['year', 'game_anon_id', 'Inning', 'Top/Bottom', 'Outs',
                      'OutsOnPlay', 'RunsScored']].copy()
        trabajo['outs_final'] = trabajo['Outs'] + trabajo['OutsOnPlay']
        trabajo['desconocida'] = ~t['conocida']
        for e in EVENTOS:
            trabajo[e] = t['evento'].eq(e).astype(int)

        llaves = ['year', 'game_anon_id', 'Inning', 'Top/Bottom']
        entradas = trabajo.groupby(llaves, dropna=False, observed=True).agg(
            min_outs=('Outs', 'min'), max_outs_final=('outs_final', 'max'),
            outs_registrados=('OutsOnPlay', 'sum'), carreras=('RunsScored', 'sum'),
            desconocidas=('desconocida', 'sum'), **{e: (e, 'sum') for e in EVENTOS})
        completas = entradas[(entradas['min_outs'] == 0) & (entradas['max_outs_final'] == 3) &
                             (entradas['outs_registrados'] == 3) & (entradas['desconocidas'] == 0) &
                             (entradas['carreras'] >= 0)]
        if len(completas) < 200:
            raise ValueError("Menos de 200 medias entradas completas para estimar los pesos.")

        X = completas[list(EVENTOS)].to_numpy(float)
        coef, _, rango, _ = np.linalg.lstsq(X, completas['carreras'].to_numpy(float), rcond=None)
        if rango < len(EVENTOS) or not np.isfinite(coef).all():
            raise ValueError("No hay suficiente variedad de eventos para la regresión.")
        pesos = dict(zip(EVENTOS, map(float, coef)))
        if not (pesos['HR'] > pesos['1B'] > pesos['OUT'] and pesos['BB'] > pesos['K']):
            raise ValueError(f"Pesos implausibles: {pesos}")
        for e in ('E', 'SAC', 'FC'):
            pesos[e] = pesos['OUT']

        # Cadena de Markov absorbente: V(c) = promedio de [peso terminal o V(siguiente cuenta)]
        validas = t[t['conocida']]
        n = np.bincount(validas['estado'], minlength=12).astype(float)
        if (n < 30).any():
            raise ValueError("Se necesitan al menos 30 transiciones por cuenta.")
        sigue = validas['siguiente'].ge(0)
        Q = np.zeros((12, 12))
        np.add.at(Q, (validas.loc[sigue, 'estado'], validas.loc[sigue, 'siguiente']), 1)
        Q /= n[:, None]
        terminales = validas[~sigue]
        r = np.bincount(terminales['estado'], weights=terminales['evento'].map(pesos), minlength=12) / n
        if np.linalg.cond(np.eye(12) - Q) > 1e8:
            raise ValueError("El sistema de transiciones de cuenta está mal condicionado.")
        valores = np.linalg.solve(np.eye(12) - Q, r)

        return cls(pesos, valores, {
            'medias_entradas_completas': len(completas),
            'pesos_regresion_originales': dict(zip(EVENTOS, map(float, coef))),
            'rmse_por_media_entrada': float(np.sqrt(np.mean((X @ coef - completas['carreras']) ** 2))),
        })

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """RV observado de cada pitch (NaN si la transición no se conoce)."""
        t = transiciones(df)
        v = self.valores_cuenta
        rv = np.full(len(df), np.nan)
        conocida = t['conocida'].to_numpy()
        sigue = conocida & t['siguiente'].ge(0).to_numpy()
        terminal = conocida & ~sigue
        estado, siguiente = t['estado'].to_numpy(), t['siguiente'].to_numpy()
        rv[sigue] = v[siguiente[sigue]] - v[estado[sigue]]
        rv[terminal] = t.loc[terminal, 'evento'].map(self.pesos).to_numpy() - v[estado[terminal]]
        return rv

    def valores_por_resultado(self, balls: np.ndarray, strikes: np.ndarray) -> dict:
        """RV de cada resultado posible del pitch en su cuenta, para armar el xRV esperado."""
        v, w = self.valores_cuenta, self.pesos
        estado = 3 * balls + strikes
        antes = v[estado]
        return {
            'bola': np.where(balls == 3, w['BB'], v[np.minimum(estado + 3, 11)]) - antes,
            'strike': np.where(strikes == 2, w['K'], v[np.minimum(estado + 1, 11)]) - antes,
            'foul': v[estado + (strikes < 2)] - antes,
            'hbp': w['HBP'] - antes,
            # Mismo orden que CLASES_EN_JUEGO en location_plus.py
            'en_juego': np.stack([w[e] - antes for e in ('OUT', '1B', '2B', '3B', 'HR')], axis=1),
        }

    def as_dict(self) -> dict:
        return {'pesos': self.pesos, 'valores_cuenta': self.valores_cuenta.tolist(),
                'diagnostico': self.diagnostico}
