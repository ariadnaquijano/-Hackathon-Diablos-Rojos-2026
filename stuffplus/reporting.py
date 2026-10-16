"""Held-out evaluation and game-clustered summaries; no model fitting here."""

import numpy as np
import pandas as pd

from .data import ALTITUDE_SLUGS, PITCH_TYPES


def comparison_metrics(frame: pd.DataFrame, prediction: pd.DataFrame, bootstrap: int, seed: int) -> pd.DataFrame:
    joined = frame[["pitcher_anon_id", "pitch_group", "altitude_category", "split"]].join(prediction)
    rows = []
    for population, part in joined.groupby("prediction_source", dropna=True):
        slices = [("all", "all", part)]
        slices += [("pitch_type", str(k), g) for k, g in part.groupby("pitch_group")]
        slices += [("altitude", str(k), g) for k, g in part.groupby("altitude_category")]
        if population == "season_holdout":
            train_pitchers = set(frame.loc[frame.split.eq("train"), "pitcher_anon_id"].dropna())
            novel = ~part.pitcher_anon_id.isin(train_pitchers)
            slices += [("pitcher_history", "unseen_before_holdout", part[novel]),
                       ("pitcher_history", "seen_before_holdout", part[~novel])]
        for scope, name, group in slices:
            use = group.dropna(subset=["residual_target", "predicted_adjusted_run_value",
                                      "baseline_adjusted_run_value", "linear_adjusted_run_value", "pitcher_anon_id"])
            if len(use) == 0:
                continue
            y = use.residual_target.to_numpy()
            loss = (y - use.predicted_adjusted_run_value.to_numpy()) ** 2
            base = (y - use.baseline_adjusted_run_value.to_numpy()) ** 2
            linear = (y - use.linear_adjusted_run_value.to_numpy()) ** 2
            row = {"population": population, "scope": scope, "group": name, "pitches": len(use),
                   "pitchers": use.pitcher_anon_id.nunique(), "xgb_rmse": float(np.sqrt(loss.mean())),
                   "baseline_rmse": float(np.sqrt(base.mean())), "linear_rmse": float(np.sqrt(linear.mean())),
                   "mse_improvement_pct": float(100 * (1 - loss.mean() / base.mean())),
                   "mean_actual_adjusted_rv": float(y.mean()),
                   "mean_predicted_adjusted_rv": float(use.predicted_adjusted_run_value.mean())}
            # Sample whole pitchers; do not pretend 600,000 pitches are independent.
            clusters = pd.DataFrame({"pitcher": use.pitcher_anon_id, "base": base, "linear": linear,
                                     "model": loss, "n": 1}).groupby("pitcher").sum()
            if len(clusters) >= 10 and bootstrap > 0:
                rng = np.random.default_rng(seed)
                draws = rng.integers(0, len(clusters), size=(bootstrap, len(clusters)))
                totals = clusters.to_numpy()[draws].sum(axis=1)
                improvements = 100 * (1 - totals[:, 2] / totals[:, 0])
                row["improvement_ci_low"], row["improvement_ci_high"] = np.percentile(improvements, [2.5, 97.5])
                versus_linear = (totals[:, 1] - totals[:, 2]) / totals[:, 3]
                row["mse_gain_vs_linear_ci_low"], row["mse_gain_vs_linear_ci_high"] = np.percentile(versus_linear, [2.5, 97.5])
            rows.append(row)
    return pd.DataFrame(rows)


def movement_metrics(frame: pd.DataFrame, prediction: pd.DataFrame) -> pd.DataFrame:
    from .data import physics
    joined = frame[["pitch_group", "altitude_category"]].join(prediction)
    actual = physics(frame)
    rows = []
    for (source, pitch_type, altitude), group in joined.groupby(["prediction_source", "pitch_group", "altitude_category"]):
        for axis in ("ivb", "hb"):
            idx = group.index[group[f"predicted_{axis}"].notna()]
            if len(idx) == 0:
                continue
            y = actual.loc[idx, axis].to_numpy()
            rows.append({"population": source, "pitch_type": pitch_type, "altitude": altitude,
                         "axis": axis, "pitches": len(idx),
                         "rmse_inches": float(np.sqrt(np.mean((y - group.loc[idx, f"predicted_{axis}"]) ** 2))),
                         "type_mean_rmse_inches": float(np.sqrt(np.mean((y - group.loc[idx, f"baseline_{axis}"]) ** 2)))})
    return pd.DataFrame(rows)


def summarize(frame: pd.DataFrame, scores: pd.DataFrame, keys: list[str], bootstrap: int, seed: int) -> pd.DataFrame:
    joined = frame[["pitcher_anon_id", "year", "pitch_group", "game_anon_id", "altitude_category"]].join(scores)
    joined = joined[joined.stuff_plus.notna()]
    rows = []
    for group_key, group in joined.groupby(keys, dropna=False, sort=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        row = dict(zip(keys, group_key))
        row.update(pitches=len(group), games=group.game_anon_id.nunique(),
                   stuff_plus=float(group.stuff_plus.mean()),
                   mean_adjusted_run_value=float(group.predicted_adjusted_run_value.mean()),
                   prediction_source=group.prediction_source.iloc[0],
                   low_sample=len(group) < (200 if "pitch_group" in keys else 300),
                   outside_reference_fraction=float(group.outside_reference.mean()))
        complete = group[[f"stuff_plus_{s}" for s in ALTITUDE_SLUGS]].notna().all(axis=1)
        supported = group.loc[complete]
        row["scenario_pitches"] = len(supported)
        for slug in ALTITUDE_SLUGS:
            row[f"stuff_plus_{slug}"] = float(supported[f"stuff_plus_{slug}"].mean())
            row[f"scenario_outside_reference_fraction_{slug}"] = float(supported[f"scenario_outside_reference_{slug}"].mean())
        row["delta_extreme_vs_no_altitude"] = float(supported.delta_extreme_vs_no_altitude.mean())
        for column in ["stuff_plus", "delta_extreme_vs_no_altitude"]:
            eligible = group if column == "stuff_plus" else supported
            cluster = eligible.groupby("game_anon_id")[column].agg(["sum", "count"])
            row[f"{column}_ci_low"] = np.nan
            row[f"{column}_ci_high"] = np.nan
            if len(cluster) >= 5 and bootstrap > 0:
                rng = np.random.default_rng(seed)
                draws = rng.integers(0, len(cluster), size=(bootstrap, len(cluster)))
                totals = cluster.to_numpy()[draws].sum(axis=1)
                means = totals[:, 0] / totals[:, 1]
                row[f"{column}_ci_low"], row[f"{column}_ci_high"] = np.percentile(means, [2.5, 97.5])
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["year", "stuff_plus"], ascending=[False, False])


def feature_importance(bundle) -> pd.DataFrame:
    rows = []
    for pitch_type, model in bundle.quality.items():
        gains = model.get_booster().get_score(importance_type="total_gain")
        merged = {}
        for feature, gain in gains.items():
            name = "spin_axis" if feature in ("spin_sin", "spin_cos") else feature
            merged[name] = merged.get(name, 0) + gain
        total = sum(merged.values())
        for name, gain in sorted(merged.items(), key=lambda kv: -kv[1]):
            rows.append({"pitch_type": pitch_type, "feature": name, "fraction_of_training_gain": gain / total if total else 0})
    return pd.DataFrame(rows)


def write_run_report(path, audit, metrics, summary, scenario, importance, elapsed):
    overall = metrics[(metrics.scope == "all")]
    lines = ["# Stuff+ training run", "", f"Elapsed time: {elapsed:.1f} seconds.", "",
             f"Input pitches: {audit['rows']:,}; physically eligible with known IDs: {audit['eligible']:,}.",
             "", "## Validation", "", "Positive improvement means lower squared error than the pitch-family mean adjusted-run-value baseline.",
             "The context-adjustment prediction is common to both competitors. A negative value means the model lost.", "",
             "| Population | Pitches | XGB RMSE | Baseline RMSE | Linear RMSE | MSE improvement | 95% interval |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in overall.itertuples():
        lines.append(f"| {r.population} | {r.pitches:,} | {r.xgb_rmse:.5f} | {r.baseline_rmse:.5f} | {r.linear_rmse:.5f} | {r.mse_improvement_pct:.3f}% | [{getattr(r, 'improvement_ci_low', float('nan')):.3f}, {getattr(r, 'improvement_ci_high', float('nan')):.3f}]% |")
    lines += ["", "## Scores and coverage", "",
              f"Pitcher-season summaries: {len(summary):,}. Pitcher/type/season summaries: {len(scenario):,}.",
              "Scores use pitcher-held-out predictions for training years and the final historical model for 2026.",
              "100 is the historical OOF mean within pitch family; 10 points is one SD of predicted adjusted run value.",
              "All destination altitudes use the same reference. Overall pitcher scores weight family-relative scores by pitch usage.",
              "", "## Leading physical predictors by training gain", "",
              "Training gain is descriptive model usage, not a causal effect or a held-out importance measure.", ""]
    for pitch_type in PITCH_TYPES:
        names = importance[importance.pitch_type.eq(pitch_type)].head(3).feature.tolist()
        lines.append(f"- {pitch_type}: {', '.join(names)}.")
    lines += ["", "## Interpretation boundaries", "",
              "- The run-value label is estimated from observed outcomes; there is no supplied official xRunValue column.",
              "- Location/count/batter context is adjusted using nested pitcher-held-out predictions. This is statistical adjustment, not causal identification.",
              "- Altitude changes the projected IVB and HB, then the physical model rescores the pitch. Direct batted-ball carry is outside pure Stuff+.",
              "- Altitude categories are not stadium identities. This is not a Harp Helu-specific or true park-holdout result.",
              "- Bootstrap intervals describe sampling of pitchers (validation) or games (individual summaries), conditional on fitted models.",
              "- The supplied cleaner used whole-file statistics. Validation is conditional on that upstream cleaning; rerun fold-local cleaning for a strict final benchmark.",
              "- 2026 has already been explored elsewhere in the team project. This run excludes it from fitting, but it is not a historically untouched competition test set.",
              "- Reports contain anonymized identifiers and derived results; source data and trained artifacts stay local.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
