"""Reproducible training orchestration and dashboard prediction interface."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd

from .data import ALTITUDES, ALTITUDE_SLUGS, RAW_PHYSICS, eligibility, load_data
from .model import Bundle, Config, add_plus_scores, fit_normalizers, group_folds
from .reporting import (comparison_metrics, feature_importance, movement_metrics,
                        summarize, write_run_report)


def write_json(path: Path, value):
    def convert(x):
        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, Path):
            return str(x)
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(value, indent=2, default=convert, allow_nan=False), encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def train(data_path: Path, output: Path, config: Config) -> dict:
    if config.folds < 2 or config.trees < 1 or config.jobs < 1 or config.bootstrap < 0:
        raise ValueError("Use folds >= 2, trees >= 1, jobs >= 1, bootstrap >= 0.")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}. Choose a new --output directory.")
    if not data_path.is_file():
        raise FileNotFoundError(data_path)
    started = time.monotonic()
    log("Reading and validating the cleaned data")
    frame, audit = load_data(data_path, config.holdout_year)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "data_audit.json", audit)
    historical = frame[frame.split.eq("train") & frame.pitcher_anon_id.notna()]
    pieces, fold_diagnostics, assignment = [], [], []
    for number, (fit, test) in enumerate(group_folds(historical, config)):
        train_frame, eval_frame = historical.iloc[fit], historical.iloc[test]
        assert set(train_frame.pitcher_anon_id).isdisjoint(set(eval_frame.pitcher_anon_id))
        log(f"Outer fold {number + 1}/{config.folds}: fit {len(train_frame):,}, score {len(eval_frame):,} pitches")
        fitted = Bundle.fit(train_frame, config)
        predictions = fitted.predict(eval_frame)
        predictions["prediction_source"] = "pitcher_oof"
        predictions["outer_fold"] = number
        pieces.append(predictions)
        fold_diagnostics.append({"fold": number, "target": fitted.target.as_dict(), "types": fitted.metadata})
        assignment.extend({"pitcher_anon_id": p, "outer_fold": number} for p in eval_frame.pitcher_anon_id.unique())
    log("Fitting final models on 2024-2025 only")
    final = Bundle.fit(frame[frame.split.eq("train")], config)
    heldout = frame[frame.split.eq("holdout")]
    log(f"Evaluating and scoring the held-out season ({len(heldout):,} pitches)")
    test_scores = final.predict(heldout)
    test_scores["prediction_source"] = "season_holdout"
    test_scores["outer_fold"] = -1
    pieces.append(test_scores)
    predictions = pd.concat(pieces).reindex(frame.index)
    final.normalizers = fit_normalizers(frame, predictions)
    predictions = add_plus_scores(frame, predictions, final.normalizers)
    final.save(output / "models")
    write_json(output / "fold_diagnostics.json", fold_diagnostics)
    pd.DataFrame(assignment).to_csv(output / "fold_assignment.csv", index=False)
    write_json(output / "normalization.json", final.normalizers)
    log("Writing pitcher summaries and clustered validation intervals")
    metrics = comparison_metrics(frame, predictions, config.bootstrap, config.seed)
    metrics.to_csv(output / "validation_metrics.csv", index=False)
    movement_metrics(frame, predictions).to_csv(output / "movement_validation.csv", index=False)
    summary = summarize(frame, predictions, ["pitcher_anon_id", "year"], config.bootstrap, config.seed)
    by_type = summarize(frame, predictions, ["pitcher_anon_id", "year", "pitch_group"], config.bootstrap, config.seed)
    by_altitude = summarize(frame, predictions, ["pitcher_anon_id", "year", "pitch_group", "altitude_category"], 0, config.seed)
    summary.to_csv(output / "pitcher_summary.csv", index=False)
    by_type.to_csv(output / "pitcher_pitch_type_summary.csv", index=False)
    by_altitude.to_csv(output / "observed_altitude_summary.csv", index=False)
    # Compare the same source pitches at all destinations; no destination-specific renormalization.
    scenario_columns = ["pitcher_anon_id", "year", "pitch_group", "pitches", "scenario_pitches",
                        *[f"stuff_plus_{s}" for s in ALTITUDE_SLUGS], "delta_extreme_vs_no_altitude",
                        "delta_extreme_vs_no_altitude_ci_low", "delta_extreme_vs_no_altitude_ci_high",
                        *[f"scenario_outside_reference_fraction_{s}" for s in ALTITUDE_SLUGS], "low_sample"]
    by_type[scenario_columns].to_csv(output / "altitude_scenarios.csv", index=False)
    importance = feature_importance(final)
    importance.to_csv(output / "feature_importance.csv", index=False)
    metadata_columns = ["PitchUID", "pitcher_anon_id", "game_anon_id", "year", "split", "pitch_group",
                        "altitude_category", "exclusion_reason"]
    frame[metadata_columns].join(predictions).to_parquet(output / "pitch_scores.parquet", index=False)
    # An excluded row is retained, never silently dropped from the delivered pitch-level file.
    if predictions.loc[frame.exclusion_reason.ne(""), "stuff_plus"].notna().any():
        raise AssertionError("An ineligible pitch received a score.")
    for altitude, slug in zip(ALTITUDES, ALTITUDE_SLUGS):
        same = frame.altitude_category.eq(altitude) & predictions[f"stuff_plus_{slug}"].notna()
        if not np.allclose(predictions.loc[same, "stuff_plus"], predictions.loc[same, f"stuff_plus_{slug}"], atol=1e-5):
            raise AssertionError("Source-altitude scenario must equal the original score.")
    versions = {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "pyarrow", "scikit-learn", "xgboost"]}
    provenance = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": asdict(config),
                  "python": platform.python_version(), "packages": versions, "input_file": data_path.name,
                  "input_sha256": file_hash(data_path),
                  "source_sha256": {p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")},
                  "seconds": time.monotonic() - started,
                  "scored_pitches": int(predictions.stuff_plus.notna().sum()),
                  "unscored_eligible": int((frame.exclusion_reason.eq("") & predictions.stuff_plus.isna()).sum()),
                  "status": "complete"}
    write_json(output / "run_manifest.json", provenance)
    write_run_report(output / "run_report.md", audit, metrics, summary, by_type, importance, provenance["seconds"])
    log(f"Complete: {output.resolve()}")
    print(metrics[metrics.scope.eq("all")].to_string(index=False), flush=True)
    return provenance


def predict_profile(model_directory: Path, profile: dict) -> dict:
    """Public API used by the local dashboard. Units match the cleaned TrackMan file.

    Required: pitch_group, pitcher_hand, altitude_category (source), and RAW_PHYSICS.
    HorzBreak, RelSide and SpinAxis use the ORIGINAL, unmirrored sensor convention.
    """
    required = set(RAW_PHYSICS + ["pitch_group", "pitcher_hand", "altitude_category"])
    if required - profile.keys():
        raise ValueError(f"Missing profile fields: {sorted(required - profile.keys())}")
    if profile["altitude_category"] not in ALTITUDES:
        raise ValueError(f"Source altitude must be one of {ALTITUDES}")
    record = {k: profile[k] for k in required}
    record.update(usable_stuff=True, pitcher_anon_id="hypothetical", game_anon_id="hypothetical")
    frame = pd.DataFrame([record])
    for column in RAW_PHYSICS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["exclusion_reason"] = eligibility(frame)
    if frame.exclusion_reason.iloc[0]:
        raise ValueError(f"Invalid physical profile: {frame.exclusion_reason.iloc[0]}")
    bundle = Bundle.load(model_directory)
    if profile["pitch_group"] not in bundle.quality or profile["pitch_group"] not in bundle.normalizers:
        raise ValueError("No trained model/reference is available for this pitch family.")
    scored = add_plus_scores(frame, bundle.predict(frame, evaluate=False), bundle.normalizers).iloc[0]
    scenarios = []
    for altitude, slug in zip(ALTITUDES, ALTITUDE_SLUGS):
        valid = bool(scored[f"scenario_supported_{slug}"])
        scenarios.append({"altitude": altitude, "supported": valid,
                          "stuff_plus": float(scored[f"stuff_plus_{slug}"]) if valid else None,
                          "ivb_inches": float(scored[f"scenario_ivb_{slug}"]) if valid else None,
                          "hb_arm_side_inches": float(scored[f"scenario_hb_{slug}"]) if valid else None,
                          "outside_reference_range": bool(scored[f"scenario_outside_reference_{slug}"])})
    delta = scored.delta_extreme_vs_no_altitude
    return {"pitch_type": profile["pitch_group"], "source_altitude": profile["altitude_category"],
            "observed_stuff_plus": float(scored.stuff_plus), "outside_reference_range": bool(scored.outside_reference),
            "delta_extreme_vs_no_altitude": float(delta) if np.isfinite(delta) else None,
            "scenarios": scenarios,
            "interpretation": "Relative to historical pitches of the same family; observational movement projection, not a causal park effect."}
