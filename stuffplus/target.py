"""Learn a transparent run-value target exclusively from the fitting partition.

No assumption about Parquet row order or a plate-appearance identifier is needed.
This is observed linear-weight run value, NOT a supplied official xRunValue label.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

EVENTS = ("1B", "2B", "3B", "HR", "BB", "HBP", "K", "OUT", "E", "SAC", "FC")
PLAY_EVENT = {"Single": "1B", "Double": "2B", "Triple": "3B", "HomeRun": "HR",
              "Out": "OUT", "Error": "E", "Sacrifice": "SAC", "FieldersChoice": "FC"}


def transitions(frame: pd.DataFrame) -> pd.DataFrame:
    """Terminal outcome or next count, using only this pitch's recorded outcome."""
    b, s = frame.Balls, frame.Strikes
    valid = b.between(0, 3) & s.between(0, 2)
    state = (3 * b + s).astype(int)
    event = pd.Series("", index=frame.index, dtype="str")
    next_state = pd.Series(-1, index=frame.index, dtype=int)
    call = frame.PitchCall
    ball = call.isin(["BallCalled", "BallinDirt"])
    strike = call.isin(["StrikeCalled", "StrikeSwinging"])
    foul = call.isin(["FoulBall", "FoulBallNotFieldable"])
    next_state.loc[ball & (b < 3)] = state[ball & (b < 3)] + 3
    event.loc[ball & (b == 3)] = "BB"
    next_state.loc[strike & (s < 2)] = state[strike & (s < 2)] + 1
    event.loc[strike & (s == 2)] = "K"
    next_state.loc[foul] = state[foul] + (s[foul] < 2).astype(int)
    event.loc[call.eq("HitByPitch")] = "HBP"
    bip = call.eq("InPlay")
    event.loc[bip] = frame.loc[bip, "play_result"].map(PLAY_EVENT).fillna("")
    # Fieldable is not synonymous with caught: require recorded outs or an explicit out.
    fieldable = call.eq("FoulBallFieldable")
    caught = fieldable & (frame.OutsOnPlay.gt(0) | frame.play_result.eq("Out"))
    event.loc[caught] = "OUT"
    next_state.loc[fieldable & ~caught] = state[fieldable & ~caught] + (s[fieldable & ~caught] < 2).astype(int)
    known = valid & (event.ne("") | next_state.ge(0))
    return pd.DataFrame({"state": state, "next_state": next_state, "event": event,
                         "known": known}, index=frame.index)


@dataclass
class RunValueTarget:
    weights: dict
    count_values: list
    diagnostics: dict

    @classmethod
    def fit(cls, frame: pd.DataFrame) -> "RunValueTarget":
        t = transitions(frame)
        work = frame[["year", "game_anon_id", "Inning", "Top/Bottom", "Outs",
                      "OutsOnPlay", "RunsScored"]].copy()
        work["end_outs"] = work.Outs + work.OutsOnPlay
        work["unknown"] = ~t.known
        for event in EVENTS:
            work[event] = t.event.eq(event).astype(int)
        keys = ["year", "game_anon_id", "Inning", "Top/Bottom"]
        agg = work.groupby(keys, dropna=False).agg(
            min_outs=("Outs", "min"), max_end_outs=("end_outs", "max"),
            recorded_outs=("OutsOnPlay", "sum"), runs=("RunsScored", "sum"),
            unknown=("unknown", "sum"), **{e: (e, "sum") for e in EVENTS})
        complete = agg[(agg.min_outs == 0) & (agg.max_end_outs == 3) &
                       (agg.recorded_outs == 3) & (agg.unknown == 0) & (agg.runs >= 0)]
        if len(complete) < 200:
            raise ValueError("Fewer than 200 complete half-innings to estimate run weights.")
        design = complete[list(EVENTS)].to_numpy(float)
        coef, _, rank, _ = np.linalg.lstsq(design, complete.runs.to_numpy(float), rcond=None)
        if rank < len(EVENTS) or not np.isfinite(coef).all():
            raise ValueError("Insufficient event diversity for run-value regression.")
        weights = dict(zip(EVENTS, map(float, coef)))
        if not (weights["HR"] > weights["1B"] > weights["OUT"] and
                weights["BB"] > weights["K"]):
            raise ValueError(f"Implausible learned event weights: {weights}")
        # Defense and runner choices should not be charged to the physical pitch.
        for event in ("E", "SAC", "FC"):
            weights[event] = weights["OUT"]

        # Absorbing Markov chain: V(count) = mean[terminal value or V(next count)].
        # Solving this avoids reconstructing PAs from undocumented row ordering.
        valid = t[t.known]
        n = np.bincount(valid.state, minlength=12).astype(float)
        if (n < 30).any():
            raise ValueError("At least 30 observed transitions per count are required.")
        q = np.zeros((12, 12))
        ongoing = valid.next_state.ge(0)
        np.add.at(q, (valid.loc[ongoing, "state"], valid.loc[ongoing, "next_state"]), 1)
        q /= n[:, None]
        terminal = valid.loc[~ongoing]
        reward = np.bincount(terminal.state, weights=terminal.event.map(weights), minlength=12) / n
        if np.linalg.cond(np.eye(12) - q) > 1e8:
            raise ValueError("Count transition system is ill-conditioned.")
        values = np.linalg.solve(np.eye(12) - q, reward)
        return cls(weights, values.tolist(), {
            "complete_half_innings": len(complete), "training_rows": len(frame),
            "known_transitions": len(valid), "count_sample_sizes": n.astype(int).tolist(),
            "regression_weights_before_defense_adjustment": dict(zip(EVENTS, map(float, coef))),
            "half_inning_regression_rmse": float(np.sqrt(np.mean((design @ coef - complete.runs) ** 2))),
        })

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        t = transitions(frame)
        result = np.full(len(frame), np.nan)
        v = np.asarray(self.count_values)
        known = t.known.to_numpy()
        ongoing = known & t.next_state.ge(0).to_numpy()
        terminal = known & ~ongoing
        result[ongoing] = v[t.next_state.to_numpy()[ongoing]] - v[t.state.to_numpy()[ongoing]]
        result[terminal] = t.event.loc[terminal].map(self.weights).to_numpy() - v[t.state.to_numpy()[terminal]]
        return result

    def as_dict(self) -> dict:
        return {"weights": self.weights, "count_values": self.count_values, "diagnostics": self.diagnostics}
