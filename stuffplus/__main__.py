"""Run with python -m stuffplus --help."""

import argparse
import json
from pathlib import Path

from .model import Config
from .pipeline import predict_profile, train
from .dashboard import serve


def main():
    parser = argparse.ArgumentParser(description="Train physical-only Stuff+ and compare altitude movement scenarios.")
    sub = parser.add_subparsers(dest="command", required=True)
    training = sub.add_parser("train", help="Train, evaluate, save models, and produce pitcher summaries")
    training.add_argument("--data", type=Path, required=True, help="Path to pitches_limpios.parquet")
    training.add_argument("--output", type=Path, default=Path("artifacts/stuffplus_v1"), help="New output directory; existing directories are never overwritten")
    training.add_argument("--trees", type=int, default=250)
    training.add_argument("--folds", type=int, default=3)
    training.add_argument("--jobs", type=int, default=4)
    training.add_argument("--seed", type=int, default=2026)
    training.add_argument("--holdout-year", type=int, default=2026)
    training.add_argument("--bootstrap", type=int, default=300)
    scoring = sub.add_parser("predict", help="Score one JSON pitch profile using saved models")
    scoring.add_argument("--model-dir", type=Path, required=True)
    scoring.add_argument("--profile", type=Path, required=True)
    dashboard = sub.add_parser("dashboard", help="Launch the local hypothetical-pitch dashboard")
    dashboard.add_argument("--model-dir", type=Path, default=Path("artifacts/stuffplus_v1/models"))
    dashboard.add_argument("--host", default="127.0.0.1", help="Bind address; defaults to localhost only")
    dashboard.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if args.command == "train":
        config = Config(trees=args.trees, folds=args.folds, jobs=args.jobs, seed=args.seed,
                        holdout_year=args.holdout_year, bootstrap=args.bootstrap)
        train(args.data, args.output, config)
    elif args.command == "predict":
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        print(json.dumps(predict_profile(args.model_dir, profile), indent=2, allow_nan=False))
    else:
        serve(args.model_dir, args.host, args.port)


if __name__ == "__main__":
    main()
