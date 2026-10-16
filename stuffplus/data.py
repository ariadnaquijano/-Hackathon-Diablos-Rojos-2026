"""Explicit schema, eligibility rules, and outcome-free physical features."""

from pathlib import Path

import numpy as np
import pandas as pd

PITCH_TYPES = ("Four-Seam", "Sinker", "Cutter", "Slider", "Curveball", "Changeup", "Splitter")
ALTITUDES = ("No Altitude", "Medium Altitude", "Extreme Altitude")
ALTITUDE_SLUGS = ("no_altitude", "medium_altitude", "extreme_altitude")
RAW_PHYSICS = ["RelSpeed", "SpinRate", "SpinAxis", "RelHeight", "RelSide", "Extension",
               "InducedVertBreak", "HorzBreak"]
PHYSICAL = ["velocity", "spin_rate", "spin_sin", "spin_cos", "release_height",
            "release_side", "extension", "ivb", "hb"]
RELEASE = [c for c in PHYSICAL if c not in ("ivb", "hb")]
CONTEXT_NUMERIC = ["Balls", "Strikes", "PlateLocSide", "PlateLocHeight"]
CONTEXT_CATEGORIES = {"pitch_group": PITCH_TYPES, "pitcher_hand": ("Left", "Right"),
                      "batter_side": ("Left", "Right")}
REQUIRED = ["PitchUID", "year", "split", "pitcher_anon_id", "game_anon_id", "pitch_group",
            "pitcher_hand", "batter_side", "altitude_category", "usable_stuff", *RAW_PHYSICS,
            "PitchCall", "play_result", "KorBB", "Balls", "Strikes", "PlateLocSide",
            "PlateLocHeight", "Outs", "OutsOnPlay", "RunsScored", "Inning", "Top/Bottom"]
LIMITS = {"RelSpeed": (40, 110), "SpinRate": (0, 4000), "SpinAxis": (0, 360),
          "RelHeight": (1, 8.5), "RelSide": (-6, 6), "Extension": (3, 9.5),
          "InducedVertBreak": (-35, 35), "HorzBreak": (-35, 35)}


def physics(frame: pd.DataFrame) -> pd.DataFrame:
    """Mirror horizontal geometry by throwing hand; encode the circular spin axis."""
    sign = frame.pitcher_hand.map({"Left": -1.0, "Right": 1.0})
    axis = np.deg2rad(pd.to_numeric(frame.SpinAxis) * sign)
    return pd.DataFrame({
        "velocity": frame.RelSpeed, "spin_rate": frame.SpinRate,
        "spin_sin": np.sin(axis), "spin_cos": np.cos(axis),
        "release_height": frame.RelHeight, "release_side": frame.RelSide * sign,
        "extension": frame.Extension, "ivb": frame.InducedVertBreak,
        "hb": frame.HorzBreak * sign,
    }, index=frame.index).astype(float)


def context(frame: pd.DataFrame) -> pd.DataFrame:
    """Used only by the adjustment model, never by the Stuff+ predictor."""
    out = frame[CONTEXT_NUMERIC].astype(float).copy()
    for column, values in CONTEXT_CATEGORIES.items():
        for value in values:
            out[f"{column}_{value}"] = frame[column].eq(value).astype(float)
        out[f"{column}_missing"] = (~frame[column].isin(values)).astype(float)
    return out


def movement_inputs(features: pd.DataFrame, altitude: pd.Series) -> pd.DataFrame:
    out = features[RELEASE].copy()
    for value, slug in zip(ALTITUDES, ALTITUDE_SLUGS):
        out[f"altitude_{slug}"] = altitude.eq(value).astype(float)
    return out


def eligibility(frame: pd.DataFrame) -> pd.Series:
    """Return a primary exclusion reason; missing measurements are not imputed."""
    reason = pd.Series("", index=frame.index, dtype="str")
    checks = [
        (~frame.usable_stuff.eq(True), "cleaner_marked_unusable"),
        (~frame.pitch_group.isin(PITCH_TYPES), "unsupported_pitch_type"),
        (~frame.pitcher_hand.isin(["Left", "Right"]), "unknown_throwing_hand"),
        (frame.pitcher_anon_id.isna(), "missing_pitcher_id"),
        (frame.game_anon_id.isna(), "missing_game_id"),
        (~np.isfinite(frame[RAW_PHYSICS].to_numpy(float)).all(axis=1), "missing_physics"),
    ]
    impossible = pd.Series(False, index=frame.index)
    for col, (lo, hi) in LIMITS.items():
        impossible |= frame[col].notna() & ~frame[col].between(lo, hi)
    checks.append((impossible, "physics_out_of_bounds"))
    for mask, label in checks:
        reason.loc[(reason == "") & mask] = label
    return reason


def load_data(path: Path, holdout_year: int) -> tuple[pd.DataFrame, dict]:
    import pyarrow.parquet as pq

    schema = pq.read_schema(path)
    missing = sorted(set(REQUIRED) - set(schema.names))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    frame = pd.read_parquet(path, columns=REQUIRED).reset_index(drop=True)
    if frame.PitchUID.isna().any() or frame.PitchUID.duplicated().any():
        raise ValueError("PitchUID must be present and unique; resolve duplicates before training.")
    if not frame.year.notna().all() or not frame.split.isin(["train", "holdout"]).all():
        raise ValueError("year and split must identify train/holdout unambiguously.")
    expected = np.where(frame.year < holdout_year, "train", "holdout")
    if (expected != frame.split).any() or (frame.year > holdout_year).any():
        raise ValueError("split disagrees with the requested holdout year, or later seasons are present.")
    if set(frame.split) != {"train", "holdout"}:
        raise ValueError("Both historical training data and the held-out season are required.")
    unknown_alt = set(frame.altitude_category.dropna()) - set(ALTITUDES)
    if unknown_alt:
        raise ValueError(f"Unrecognized altitude categories: {unknown_alt}")
    frame["exclusion_reason"] = eligibility(frame)
    audit = {
        "rows": len(frame), "eligible": int(frame.exclusion_reason.eq("").sum()),
        "exclusions": frame.loc[frame.exclusion_reason.ne(""), "exclusion_reason"].value_counts().to_dict(),
        "by_year": frame.year.value_counts().sort_index().to_dict(),
        "missing_altitude": int(frame.altitude_category.isna().sum()),
        "input_columns": REQUIRED,
    }
    return frame, audit
