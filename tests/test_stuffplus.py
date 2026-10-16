"""Regression tests for scientific and data-integrity invariants. Run with unittest."""

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from stuffplus.data import ALTITUDES, PHYSICAL, context, eligibility, movement_inputs, physics
from stuffplus.model import Bundle, Config, add_plus_scores, fit_normalizers, group_folds
from stuffplus.pipeline import predict_profile, train
from stuffplus.target import EVENTS, RunValueTarget, transitions


def profile():
    return {"pitch_group": "Four-Seam", "pitcher_hand": "Right", "altitude_category": "No Altitude",
            "RelSpeed": 93., "SpinRate": 2300., "SpinAxis": 200., "RelHeight": 6.,
            "RelSide": 2., "Extension": 6.2, "InducedVertBreak": 17., "HorzBreak": 9.,
            "usable_stuff": True, "pitcher_anon_id": "p", "game_anon_id": "g"}


class DataTests(unittest.TestCase):
    def test_mirrored_throwing_hands_have_identical_features(self):
        right = profile()
        left = right | {"pitcher_hand": "Left", "SpinAxis": 160., "RelSide": -2., "HorzBreak": -9.}
        x = physics(pd.DataFrame([right, left]))
        np.testing.assert_allclose(x.iloc[0], x.iloc[1], atol=1e-12)

    def test_outcomes_location_and_altitude_never_enter_quality_features(self):
        a = profile() | {"PlateLocSide": 0., "Balls": 0, "PitchCall": "StrikeSwinging"}
        b = a | {"PlateLocSide": 4., "Balls": 3, "PitchCall": "InPlay", "altitude_category": "Extreme Altitude"}
        x = physics(pd.DataFrame([a, b]))
        self.assertEqual(list(x), PHYSICAL)
        np.testing.assert_array_equal(x.iloc[0], x.iloc[1])

    def test_missing_measurement_after_cleaning_is_excluded(self):
        frame = pd.DataFrame([profile() | {"SpinRate": np.nan}])
        self.assertEqual(eligibility(frame).iloc[0], "missing_physics")

    def test_pitcher_folds_do_not_overlap_and_cover_every_row(self):
        frame = pd.DataFrame({"pitcher_anon_id": np.repeat([f"p{i}" for i in range(20)], 7)})
        seen = []
        for fit, test in group_folds(frame, Config()):
            self.assertTrue(set(frame.iloc[fit].pitcher_anon_id).isdisjoint(frame.iloc[test].pitcher_anon_id))
            seen.extend(test)
        self.assertEqual(sorted(seen), list(range(len(frame))))


class TargetTests(unittest.TestCase):
    def test_walk_strikeout_and_two_strike_foul(self):
        frame = pd.DataFrame({"Balls": [3, 0, 2, 1, 0], "Strikes": [2, 2, 2, 1, 0],
                              "PitchCall": ["BallCalled", "StrikeSwinging", "FoulBall", "StrikeCalled", "Undefined"],
                              "play_result": ["Walk", "Strikeout", "NeutralPlay", "NeutralPlay", "NeutralPlay"],
                              "OutsOnPlay": [0, 1, 0, 0, 0]})
        t = transitions(frame)
        self.assertEqual(t.event.tolist()[:2], ["BB", "K"])
        self.assertEqual(t.next_state.iloc[2], t.state.iloc[2])
        weights = {e: 0.5 for e in EVENTS} | {"K": -0.1}
        target = RunValueTarget(weights, [0.2] * 12, {})
        np.testing.assert_allclose(target.transform(frame)[:4], [0.3, -0.3, 0., 0.])
        self.assertTrue(np.isnan(target.transform(frame)[4]))

    def test_fieldable_foul_requires_evidence_of_an_out(self):
        frame = pd.DataFrame({"Balls": [0, 0], "Strikes": [2, 2],
                              "PitchCall": ["FoulBallFieldable"] * 2,
                              "play_result": ["FoulBallFieldable", "Out"], "OutsOnPlay": [0, 1]})
        t = transitions(frame)
        self.assertEqual(t.event.tolist(), ["", "OUT"])
        self.assertEqual(t.next_state.iloc[0], 2)


class ScoreTests(unittest.TestCase):
    def test_normalizer_ignores_holdout_and_is_frozen_across_altitudes(self):
        frame = pd.DataFrame({"pitch_group": ["Four-Seam"] * 41, "split": ["train"] * 40 + ["holdout"]})
        pred = pd.DataFrame({"predicted_adjusted_run_value": np.r_[np.linspace(-.03, .03, 40), 10.]})
        for slug in ("no_altitude", "medium_altitude", "extreme_altitude"):
            pred[f"scenario_raw_{slug}"] = pred.predicted_adjusted_run_value
        pred["scenario_raw_extreme_altitude"] += .01
        norm = fit_normalizers(frame, pred)
        self.assertAlmostEqual(norm["Four-Seam"]["mean"], 0.)
        scored = add_plus_scores(frame, pred, norm)
        self.assertAlmostEqual(scored.stuff_plus.iloc[:40].mean(), 100.)
        self.assertTrue((scored.stuff_plus_extreme_altitude < scored.stuff_plus_no_altitude).all())

    def test_refuse_to_overwrite_a_run(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                train(Path("not-read.parquet"), Path(temp), Config())

    def test_saved_models_and_profile_api_preserve_source_scenario(self):
        # Small real XGBoost models verify serialization and the standalone dashboard API.
        rng = np.random.default_rng(1)
        records = [profile() | {"RelSpeed": float(v), "altitude_category": ALTITUDES[i % 3]}
                   for i, v in enumerate(rng.uniform(89, 97, 90))]
        f = pd.DataFrame(records)
        f["exclusion_reason"] = ""
        x = physics(f)
        def fit(a, y):
            return XGBRegressor(n_estimators=5, max_depth=2, n_jobs=1).fit(a, y)
        adjustment = fit(pd.DataFrame({"a": np.arange(90)}), np.zeros(90))
        bundle = Bundle(Config(), RunValueTarget({}, [0.] * 12, {}), adjustment)
        bundle.quality["Four-Seam"] = fit(x, -.001 * x.velocity)
        mx = movement_inputs(x, f.altitude_category)
        bundle.movement["Four-Seam"] = {axis: fit(mx, x[axis] - f.altitude_category.map(dict(zip(ALTITUDES, [0., 1., 2.])))) for axis in ("ivb", "hb")}
        bundle.metadata["Four-Seam"] = {"status": "fitted", "residual_mean": -.09,
            "ranges": {c: [-10000., 10000.] for c in PHYSICAL},
            "altitude_support": {a: {"pitches": 1000, "pitchers": 50} for a in ALTITUDES},
            "movement_mean": {"ivb": 17., "hb": 9.}}
        bundle.normalizers = {"Four-Seam": {"mean": -.09, "std": .01}}
        before = bundle.predict(f, evaluate=False)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "models"
            bundle.save(directory)
            loaded = Bundle.load(directory)
            after = loaded.predict(f, evaluate=False)
            np.testing.assert_allclose(before.predicted_adjusted_run_value, after.predicted_adjusted_run_value)
            scored = predict_profile(directory, profile())
            self.assertAlmostEqual(scored["observed_stuff_plus"], scored["scenarios"][0]["stuff_plus"], places=6)
            with self.assertRaises(ValueError):
                predict_profile(directory, profile() | {"RelSpeed": 300.})


if __name__ == "__main__":
    unittest.main()
