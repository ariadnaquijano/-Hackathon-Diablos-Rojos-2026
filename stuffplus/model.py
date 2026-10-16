"""Fit physical-only XGBoost models and independent movement transport models."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from .data import (ALTITUDES, ALTITUDE_SLUGS, PHYSICAL, PITCH_TYPES, RAW_PHYSICS,
                   context, movement_inputs, physics)
from .target import RunValueTarget


@dataclass
class Config:
    seed: int = 2026
    folds: int = 3
    trees: int = 250
    jobs: int = 4
    holdout_year: int = 2026
    min_type_pitches: int = 1000
    min_type_pitchers: int = 10
    min_altitude_pitches: int = 200
    min_altitude_pitchers: int = 10
    bootstrap: int = 300


def regressor(config: Config, kind: str = "physical") -> XGBRegressor:
    return XGBRegressor(
        n_estimators=config.trees, max_depth=3 if kind == "physical" else 4,
        learning_rate=0.04, min_child_weight=100 if kind == "context" else 40,
        subsample=0.85, colsample_bytree=1.0, reg_lambda=20.0, reg_alpha=0.0,
        objective="reg:squarederror", tree_method="hist", max_bin=128,
        n_jobs=config.jobs, random_state=config.seed,
    )


def group_folds(frame: pd.DataFrame, config: Config):
    if frame.pitcher_anon_id.nunique() < config.folds:
        raise ValueError("Too few pitchers for grouped cross-validation.")
    splitter = GroupKFold(n_splits=config.folds, shuffle=True, random_state=config.seed)
    return list(splitter.split(frame, groups=frame.pitcher_anon_id))


def crossfit_context(frame: pd.DataFrame, y: np.ndarray, config: Config):
    x = context(frame)
    prediction = np.full(len(frame), np.nan)
    for fit, test in group_folds(frame, config):
        fit = fit[np.isfinite(y[fit])]
        m = regressor(config, "context").fit(x.iloc[fit], y[fit])
        prediction[test] = m.predict(x.iloc[test])
    valid = np.isfinite(y)
    final = regressor(config, "context").fit(x.loc[valid], y[valid])
    return prediction, final


@dataclass
class Bundle:
    config: Config
    target: RunValueTarget
    adjustment: XGBRegressor
    quality: dict = field(default_factory=dict)
    movement: dict = field(default_factory=dict)
    linear: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    normalizers: dict = field(default_factory=dict)

    @classmethod
    def fit(cls, training: pd.DataFrame, config: Config) -> "Bundle":
        # training contains only the outer fitting pitchers/years; outcomes of held-out
        # pitchers and 2026 cannot affect the target, context adjustment or transport.
        target = RunValueTarget.fit(training)
        eligible = training.exclusion_reason.eq("")
        f = training.loc[eligible].reset_index(drop=True)
        y = target.transform(f)
        nuisance_oof, adjustment = crossfit_context(f, y, config)
        residual = y - nuisance_oof
        bundle = cls(config, target, adjustment)
        x = physics(f)
        for pitch_type in PITCH_TYPES:
            select = f.pitch_group.eq(pitch_type).to_numpy()
            fit = select & np.isfinite(residual)
            pitchers = f.loc[fit, "pitcher_anon_id"].nunique()
            if fit.sum() < config.min_type_pitches or pitchers < config.min_type_pitchers:
                bundle.metadata[pitch_type] = {"status": "insufficient_training_support",
                                               "training_pitches": int(fit.sum()), "pitchers": int(pitchers)}
                continue
            bundle.quality[pitch_type] = regressor(config).fit(x.loc[fit], residual[fit])
            bundle.linear[pitch_type] = make_pipeline(StandardScaler(), Ridge(alpha=100.0)).fit(x.loc[fit], residual[fit])
            ranges = {c: [float(x.loc[fit, c].quantile(0.005)), float(x.loc[fit, c].quantile(0.995))]
                      for c in PHYSICAL if c not in ("spin_sin", "spin_cos")}
            support = {}
            for altitude in ALTITUDES:
                a = select & f.altitude_category.eq(altitude).to_numpy()
                support[altitude] = {"pitches": int(a.sum()),
                                     "pitchers": int(f.loc[a, "pitcher_anon_id"].nunique())}
            move_fit = select & f.altitude_category.isin(ALTITUDES).to_numpy()
            mx = movement_inputs(x.loc[move_fit], f.loc[move_fit, "altitude_category"])
            bundle.movement[pitch_type] = {
                axis: regressor(config, "movement").fit(mx, x.loc[move_fit, axis])
                for axis in ("ivb", "hb")}
            bundle.metadata[pitch_type] = {
                "status": "fitted", "training_pitches": int(fit.sum()), "pitchers": int(pitchers),
                "residual_mean": float(np.mean(residual[fit])), "ranges": ranges, "altitude_support": support,
                "movement_mean": {a: float(x.loc[move_fit, a].mean()) for a in ("ivb", "hb")},
            }
        if not bundle.quality:
            raise ValueError("No pitch family has sufficient training support.")
        return bundle

    def supported(self, pitch_type: str, altitude: str) -> bool:
        s = self.metadata[pitch_type]["altitude_support"].get(altitude, {})
        return (s.get("pitches", 0) >= self.config.min_altitude_pitches and
                s.get("pitchers", 0) >= self.config.min_altitude_pitchers)

    def predict(self, frame: pd.DataFrame, evaluate: bool = True) -> pd.DataFrame:
        """Score observed physics and anchor each altitude scenario to that same pitch.

        Movement at destination = observed movement + predicted(destination) - predicted(source).
        The source scenario is therefore exactly equal to the observed pitch.
        """
        x = physics(frame)
        out = pd.DataFrame(index=frame.index)
        numeric = ["predicted_adjusted_run_value", "baseline_adjusted_run_value", "linear_adjusted_run_value",
                   "observed_run_value", "context_prediction", "residual_target", "predicted_ivb", "predicted_hb",
                   "baseline_ivb", "baseline_hb"]
        for slug in ALTITUDE_SLUGS:
            numeric += [f"scenario_raw_{slug}", f"scenario_ivb_{slug}", f"scenario_hb_{slug}"]
            out[f"scenario_supported_{slug}"] = False
            out[f"scenario_outside_reference_{slug}"] = False
        for c in numeric:
            out[c] = np.nan
        out["outside_reference"] = False
        out["scored"] = False
        for pitch_type, quality in self.quality.items():
            idx = frame.index[frame.pitch_group.eq(pitch_type) & frame.exclusion_reason.eq("")]
            if len(idx) == 0:
                continue
            px = x.loc[idx]
            out.loc[idx, "predicted_adjusted_run_value"] = quality.predict(px)
            out.loc[idx, "baseline_adjusted_run_value"] = self.metadata[pitch_type]["residual_mean"]
            if pitch_type in self.linear:
                out.loc[idx, "linear_adjusted_run_value"] = self.linear[pitch_type].predict(px)
            out.loc[idx, "scored"] = True
            ranges = self.metadata[pitch_type]["ranges"]
            outside = lambda z: np.column_stack([~z[c].between(lo, hi) for c, (lo, hi) in ranges.items()]).any(axis=1)
            out.loc[idx, "outside_reference"] = outside(px)
            source = frame.loc[idx, "altitude_category"]
            known = source.isin(ALTITUDES)
            valid_idx = idx[known]
            if len(valid_idx) == 0:
                continue
            mx = movement_inputs(x.loc[valid_idx], source.loc[valid_idx])
            original = {axis: self.movement[pitch_type][axis].predict(mx) for axis in ("ivb", "hb")}
            for axis in ("ivb", "hb"):
                out.loc[valid_idx, f"predicted_{axis}"] = original[axis]
                out.loc[valid_idx, f"baseline_{axis}"] = self.metadata[pitch_type]["movement_mean"][axis]
            for altitude, slug in zip(ALTITUDES, ALTITUDE_SLUGS):
                if not self.supported(pitch_type, altitude):
                    continue
                supported_source = source.loc[valid_idx].map(lambda a: self.supported(pitch_type, a)).to_numpy(bool)
                dest = pd.Series(altitude, index=valid_idx)
                dx = movement_inputs(x.loc[valid_idx], dest)
                moved = x.loc[valid_idx].copy()
                for axis in ("ivb", "hb"):
                    moved[axis] += self.movement[pitch_type][axis].predict(dx) - original[axis]
                    out.loc[valid_idx[supported_source], f"scenario_{axis}_{slug}"] = moved.loc[valid_idx[supported_source], axis]
                out.loc[valid_idx[supported_source], f"scenario_raw_{slug}"] = quality.predict(moved.loc[valid_idx[supported_source]])
                out.loc[valid_idx[supported_source], f"scenario_supported_{slug}"] = True
                out.loc[valid_idx[supported_source], f"scenario_outside_reference_{slug}"] = outside(moved.loc[valid_idx[supported_source]])
        if evaluate:
            out["observed_run_value"] = self.target.transform(frame)
            out["context_prediction"] = self.adjustment.predict(context(frame))
            out["residual_target"] = out.observed_run_value - out.context_prediction
        return out

    def save(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=False)
        self.adjustment.save_model(directory / "context.ubj")
        for pitch_type, model in self.quality.items():
            model.save_model(directory / f"quality_{pitch_type}.ubj")
            for axis, movement in self.movement[pitch_type].items():
                movement.save_model(directory / f"movement_{pitch_type}_{axis}.ubj")
        manifest = {"format_version": 1, "config": asdict(self.config), "physical_features": PHYSICAL,
                    "target": self.target.as_dict(), "types": self.metadata, "normalizers": self.normalizers}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "Bundle":
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["format_version"] != 1 or manifest["physical_features"] != PHYSICAL:
            raise ValueError("Incompatible model manifest.")
        target = RunValueTarget(**manifest["target"])
        adjustment = XGBRegressor()
        adjustment.load_model(directory / "context.ubj")
        obj = cls(Config(**manifest["config"]), target, adjustment,
                  metadata=manifest["types"], normalizers=manifest["normalizers"])
        for pitch_type, meta in obj.metadata.items():
            if meta["status"] != "fitted":
                continue
            obj.quality[pitch_type] = XGBRegressor()
            obj.quality[pitch_type].load_model(directory / f"quality_{pitch_type}.ubj")
            obj.movement[pitch_type] = {}
            for axis in ("ivb", "hb"):
                obj.movement[pitch_type][axis] = XGBRegressor()
                obj.movement[pitch_type][axis].load_model(directory / f"movement_{pitch_type}_{axis}.ubj")
        return obj


def fit_normalizers(frame: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    """One frozen OOF reference per pitch family, shared by all altitude scenarios."""
    result = {}
    for pitch_type in PITCH_TYPES:
        mask = frame.pitch_group.eq(pitch_type) & frame.split.eq("train")
        raw = predictions.loc[mask, "predicted_adjusted_run_value"].dropna()
        if len(raw) < 30:
            continue
        std = float(raw.std(ddof=0))
        if not np.isfinite(std) or std < 1e-6:
            raise ValueError(f"Cannot define a meaningful plus scale for {pitch_type}: near-constant predictions.")
        result[pitch_type] = {"mean": float(raw.mean()), "std": std, "reference_pitches": len(raw)}
    return result


def add_plus_scores(frame: pd.DataFrame, prediction: pd.DataFrame, normalizers: dict) -> pd.DataFrame:
    out = prediction.copy()
    for suffix in ["", *[f"_{slug}" for slug in ALTITUDE_SLUGS]]:
        raw = "predicted_adjusted_run_value" if suffix == "" else f"scenario_raw{suffix}"
        out[f"stuff_plus{suffix}"] = np.nan
        for pitch_type, reference in normalizers.items():
            mask = frame.pitch_group.eq(pitch_type)
            out.loc[mask, f"stuff_plus{suffix}"] = 100 - 10 * (out.loc[mask, raw] - reference["mean"]) / reference["std"]
    out["delta_extreme_vs_no_altitude"] = out.stuff_plus_extreme_altitude - out.stuff_plus_no_altitude
    return out
