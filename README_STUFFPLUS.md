# Local XGBoost Stuff+ implementation

This standalone package trains one physical-quality model per pitch family, evaluates
unseen pitchers and a held-out season, and writes pitcher summaries plus altitude
movement scenarios. It reads the supplied cleaned Parquet directly; it does not need
the team's feature-engineering branch or modify the input data.

**Read [the complete model and meeting guide](docs/STUFFPLUS_MODEL_GUIDE.md)** before
presenting scores. It explains the target, adjustment, normalization, validation,
altitude assumptions, output columns, and limitations.

## Windows setup

Use Python 3.12, the version used for verification. From this repository's root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-stuffplus.txt
```

The local `.venv` has already been created and dependencies installed for this task.
If `python` opens the Microsoft Store, use an installed Python interpreter instead.

## Train and produce summaries

```powershell
.\.venv\Scripts\python.exe -m stuffplus train `
  --data "C:\Users\maxim\Downloads\StuffPlus\pitches_limpios.parquet" `
  --output artifacts\stuffplus_v1 `
  --jobs 4
```

The completed run is already in `artifacts/stuffplus_v1`. For a new run choose a
new output directory, for example `artifacts/stuffplus_v2`; the program refuses
to overwrite existing runs. Outputs and model binaries are excluded from Git.

Start with these files:

- `artifacts/stuffplus_v1/run_report.md`: results and interpretation.
- `artifacts/stuffplus_v1/pitcher_summary.csv`: one row per pitcher and season.
- `artifacts/stuffplus_v1/pitcher_pitch_type_summary.csv`: one row per pitcher, season, and pitch family.
- `artifacts/stuffplus_v1/altitude_scenarios.csv`: the same pitch mix projected into all three altitude categories.
- `artifacts/stuffplus_v1/validation_metrics.csv`: error and comparisons with baselines.

## Score a hypothetical pitch

```powershell
.\.venv\Scripts\python.exe -m stuffplus predict `
  --model-dir artifacts\stuffplus_v1\models `
  --profile examples\hypothetical_pitch.json
```

The example is synthetic. Specify measurements at the **source** altitude. The
output includes its observed-physics score and projected movement/scores at each
destination altitude.

## Launch the local dashboard

The simple browser dashboard uses only the Python standard library and the saved
models. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m stuffplus dashboard
```

Then open <http://127.0.0.1:8501>. Enter one hypothetical pitch's measurements
with either the numeric fields or their synchronized sliders,
pitch family, throwing hand, and the altitude where its movement was measured.
The dashboard shows its family-relative Stuff+ score and modeled projections for
all three altitude categories. It does not build a full pitcher's arsenal. Stop
the local server with `Ctrl+C` in the terminal.

The app binds to localhost by default. To use a different local port, pass, for
example, `--port 8502`. It is intended for local use only.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

No Git commit, branch switch, push, or pull request is required to run this code.
Keep the competition dataset and generated pitch-level artifacts local.
