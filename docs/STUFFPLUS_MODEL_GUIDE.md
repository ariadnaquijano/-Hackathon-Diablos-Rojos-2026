# Physical Stuff+ with XGBoost: implementation and meeting guide

This guide describes the code in this local repository, not a proposed future
implementation. The companion `artifacts/stuffplus_v1/run_report.md` contains the
measured results of the full-data run. A simple local browser dashboard now uses
the saved-model prediction function for one hypothetical pitch at a time.

**Actual result to present honestly:** the full run successfully scored 617,732
pitches and produced 1,718 pitcher-season and 9,310 pitcher-season-family summaries.
However, XGBoost did not beat the linear physical baseline in either evaluation.
It also lost narrowly to the constant baseline in historical pitcher holdout.
Treat these scores and altitude projections as an experimental modeling result,
not a validated scouting decision system. Section 20 gives the measured results.

## 1. What we built

The pipeline takes the cleaned pitch-level Parquet file, trains separate XGBoost
regression models for seven pitch families, and assigns each eligible pitch a
Stuff+ score. It aggregates those scores by pitcher and season, then by pitcher,
season, and pitch family. It also estimates how the same recorded pitches would
score if their movement changed to match a different altitude category.

The system has four distinct statistical components:

1. **Run-value target construction:** estimate the offensive value of pitch
   outcomes using training data only.
2. **Context adjustment:** estimate the contribution associated with pitch
   location, count, and handedness, then remove that prediction from the label.
3. **Physical quality:** use only pitch physics to predict the adjusted run value,
   separately for each pitch family. Convert this prediction to a plus scale.
4. **Movement projection:** predict vertical and horizontal movement from release
   properties and altitude, transport a recorded pitch to another altitude, and
   feed its projected physics into the same quality model.

The resulting metric is our team's **physical Stuff+ estimate**, with an explicit
definition. It is not a reproduction of FanGraphs' proprietary model, a certified
causal estimate, or a claim that the full competition submission is complete.

### A short explanation for the meeting

> We train a separate XGBoost model for each pitch family. Its inputs are speed,
> spin, movement, release position, and extension. Its label is run value after
> statistical adjustment for location and count. Higher predicted offensive value
> is worse for the pitcher, so we reverse the direction when turning it into
> Stuff+. A score of 100 is average for the same pitch family in our historical
> reference. We validate on pitchers excluded from training and on the 2026 season.
> For altitude, a separate model changes projected movement first, then we rescore
> the physical pitch. We report these as observational scenarios.

## 2. Why separate pitch families are appropriate

Your intuition was sound: a physical characteristic is valuable in relation to
the type of pitch. High velocity means something different for a changeup and a
four-seam fastball. Horizontal movement and vertical movement also interact with
each other differently across families.

One shared tree model with a pitch-type input could learn these interactions. It
is not mathematically necessary to fit separate models. We chose separate models
because the dataset supports them, their explanations are easier to present, and
the requested summaries are pitch-type-specific.

The input cleaner provides `pitch_group`, which this package treats as the family:

| Pitch family | Training rows before this package's eligibility checks | 2026 rows before checks |
|---|---:|---:|
| Four-Seam | 174,046 | 43,572 |
| Sinker | 85,774 | 25,125 |
| Cutter | 20,680 | 5,788 |
| Slider | 108,618 | 31,099 |
| Curveball | 42,759 | 11,265 |
| Changeup | 61,647 | 17,278 |
| Splitter | 5,815 | 1,474 |
| Other | 59 | 3 |

`Other` is unsupported. The cleaner groups two-seam/one-seam fastballs under
Sinker and Sweepers under Slider. Thus the models are **family-specific**, not
necessarily one model for every original `AutoPitchType` label. In particular,
this version does not have a separate sweeper model.

For each fitting partition, a family needs at least 1,000 labeled physical pitches
and 10 pitchers. Insufficient families are explicitly marked unsupported; the code
does not invent a score from a tiny model. The final run metadata records support
separately for every family and fold.

### What family normalization means

A 110 cutter means better physical-quality predictions than the historical cutter
reference, on the defined scale. A 110 slider has the equivalent standardized
standing within sliders. These are not necessarily identical changes in expected
runs. This distinction matters when combining families into a pitcher's score.

## 3. Input data and its boundaries

The supplied input file is:

`C:\Users\maxim\Downloads\StuffPlus\pitches_limpios.parquet`

The code opens it for reading. It neither edits the file nor copies the full
dataset into the source-code tree.

The file contains 635,002 rows:

| Season | Existing split | Rows |
|---|---|---:|
| 2024 | train | 243,254 |
| 2025 | train | 256,144 |
| 2026 | holdout | 135,604 |

Altitude categories are exactly `No Altitude`, `Medium Altitude`, and
`Extreme Altitude`. There are 3,020 rows with no altitude category. A pitch with
known physics can still receive an observed score without known altitude, but it
cannot be transported from an unknown source environment.

The file does not contain a ready-made `xRunValue` target, a verified stadium ID,
runner-on-base states, or `pitch_seq`. The code therefore does not assume it can
reconstruct full plate appearances from row order or calculate a traditional
base-out run expectancy matrix.

### Eligibility checks

The package requires a unique, nonmissing `PitchUID`, consistent year/split labels,
recognized altitude categories, and a specific explicit schema. It fails with an
explanation if the schema or split is inconsistent.

For a pitch to train or receive a physical score, it needs:

- `usable_stuff == True` from the cleaner;
- a supported pitch family;
- resolved throwing hand;
- a pitcher identifier and game identifier;
- all eight raw physical measurements present and finite;
- physical measurements within the documented hard bounds.

The physical bounds match the team cleaner where applicable: velocity 40–110 mph,
spin 0–4,000 rpm, release height 1–8.5 ft, release side −6–6 ft, extension 3–9.5 ft,
and each movement component −35–35 inches. Spin axis must lie in 0–360 degrees.
These are invalid-data guards, not suggested coaching targets.

Rechecking completeness is necessary: the supplied cleaner can null a suspicious
measurement after computing an earlier usability flag. The model should not learn
that a missing sensor reading itself predicts a good or bad pitcher.

On this input, 617,732 pitches pass physical and identifier eligibility. The other
17,270 have the following **primary** reasons, assigned in priority order:

| Primary reason | Rows |
|---|---:|
| Missing physics | 12,311 |
| Missing pitcher ID | 3,007 |
| Cleaner marked unusable | 1,952 |

These categories do not claim that a row has only one issue. The pitch-level output
retains every input row and its reason. An eligible pitch with an unknown outcome
can receive a physical score, but it cannot supply a supervised training label.

## 4. Code structure and reading order

```text
README_STUFFPLUS.md                  quick start
requirements-stuffplus.txt          exact direct package versions
stuffplus/
    __init__.py                     package version
    __main__.py                     train/predict command-line interface
    data.py                         schema, validation, feature construction
    target.py                       run weights, count transitions, target
    model.py                        XGBoost, cross-fitting, transport, persistence
    reporting.py                    metrics, intervals, summaries, run report
    pipeline.py                     full orchestration and public prediction API
examples/
    hypothetical_pitch.json         synthetic future-dashboard example
tests/
    test_stuffplus.py                scientific and data-integrity checks
docs/
    STUFFPLUS_MODEL_GUIDE.md         this document
artifacts/stuffplus_v1/              local run results; excluded from Git
```

This package is independent of the teammate's `src/` layout on `etapas-0-a-2`.
That avoids silently replacing their existing modules or importing a different
`config.py`. It can later be integrated through a small reviewed pull request.

### Main functions and classes

| Component | Responsibility |
|---|---|
| `load_data` | Read required columns, check identifiers/splits, build the audit |
| `eligibility` | Assign the primary reason a pitch cannot be scored |
| `physics` | Build the exact physical feature matrix |
| `context` | Build the separate location/count adjustment matrix |
| `movement_inputs` | Build release features plus altitude indicators |
| `transitions` | Classify each pitch as a terminal outcome or a count transition |
| `RunValueTarget.fit` | Learn outcome weights and count values on fitting data |
| `RunValueTarget.transform` | Apply those frozen weights to any partition |
| `crossfit_context` | Produce adjustment predictions excluding each fitting pitcher |
| `Bundle.fit` | Train adjustment, physical, linear-baseline, and movement models |
| `Bundle.predict` | Produce observed and altitude-scenario predictions |
| `fit_normalizers` | Estimate the frozen scale from historical OOF predictions |
| `add_plus_scores` | Convert run-value predictions into Stuff+ |
| `Bundle.save/load` | Persist and restore models with explicit metadata |
| `comparison_metrics` | Evaluate models and pitcher-clustered error intervals |
| `summarize` | Aggregate by pitcher/type and compute game-clustered intervals |
| `train` | Execute the entire workflow and save outputs |
| `predict_profile` | Score a hypothetical pitch from saved models |

## 5. Physical features: what the model can and cannot see

Each quality model has exactly these nine numeric input columns:

| Model feature | Input measurement | Units / meaning |
|---|---|---|
| `velocity` | `RelSpeed` | mph at release |
| `spin_rate` | `SpinRate` | rpm |
| `spin_sin` | transformed `SpinAxis` | sine of the arm-normalized spin angle |
| `spin_cos` | transformed `SpinAxis` | cosine of the same angle |
| `release_height` | `RelHeight` | feet |
| `release_side` | `RelSide`, mirrored by throwing hand | feet toward the arm side |
| `extension` | `Extension` | feet |
| `ivb` | `InducedVertBreak` | induced vertical break, inches |
| `hb` | `HorzBreak`, mirrored by throwing hand | horizontal break, inches toward the arm side |

The two trigonometric columns encode one physical measurement, so these represent
eight raw measurements. Encoding an angle as sine and cosine makes 359° and 1°
neighbors instead of putting them at opposite ends of a linear scale.

For right-handers, horizontal measurements retain their sign. For left-handers,
the horizontal signs and spin orientation are mirrored. The convention matches
the inspected cleaner. The package constructs this explicitly from raw fields
rather than depending on optional precomputed feature columns.

**Excluded from the physical predictors:** pitch location, count, inning, outs,
altitude category, year, pitcher/batter/catcher IDs, batter handedness, observed
pitch results, batted-ball speed, launch angle, runs scored, and balls-in-play
outcomes. Pitch family selects a model; it is not an additional numeric input.

Throwing hand is used to express geometry consistently, not as a separate quality
predictor. Pitcher identity is used to partition and summarize data, never to let
the model memorize a pitcher's name or historical success.

This first pure-physics version also omits arsenal-relative features, previous
pitch, release angles, and plate approach angles. Arsenal features belong in a
later explicit extension; raw trajectory/approach angles can encode location.
This is a scope choice, not a claim that arsenal is irrelevant to the competition.

## 6. The supervised target, step by step

XGBoost needs a number to learn from. The cleaned data has outcomes but no official
expected-run-value label. We construct an **observed linear-weight pitch run value**
and let the regression model estimate its expected component from physics.

There is no manually weighted combination such as “70% whiff plus 20% weak contact.”
All target values come from a documented run-value construction fitted within the
training partition. This does not make the target perfect: defensive outcomes and
unmeasured situations remain noisy.

### 6.1 Identify terminal outcomes and count transitions

Each pitch is classified using its own call, count, and recorded result:

- Ball with fewer than three balls: advance the ball count.
- Ball with three balls: terminal walk.
- Called or swinging strike with fewer than two strikes: advance the strike count.
- Called or swinging strike with two strikes: terminal strikeout.
- Ordinary foul with fewer than two strikes: add a strike.
- Ordinary foul with two strikes: the count stays the same.
- Hit by pitch: terminal HBP.
- Ball in play: single, double, triple, home run, out, error, sacrifice, or fielder's choice.
- A fieldable foul is terminal only when an out is recorded; otherwise it behaves
  as a foul. “Fieldable” alone is not treated as proof that a fielder caught it.

Undefined calls and unrecognized in-play results produce a missing target. They
are not silently relabeled as outs. The implementation does not model rare special
rules such as a two-strike foul bunt unless the recorded call already distinguishes it.

### 6.2 Estimate run values from half-innings

Group fitting rows by season, game, inning, and top/bottom. A half-inning qualifies
for the regression when its records include zero outs, reach exactly three outs,
sum to three recorded outs, contain no unknown transitions, and have nonnegative runs.

For each qualifying half-inning count the terminal events. Fit ordinary least squares:

```text
runs in half-inning ≈
    w_1B × singles + w_2B × doubles + w_3B × triples + w_HR × home runs
  + w_BB × walks + w_HBP × hit-by-pitches + w_K × strikeouts
  + w_OUT × ordinary outs + w_E × errors + w_SAC × sacrifices + w_FC × fielder choices
```

The implementation uses no intercept, matching the event-count linear-weight
approach inspected in the team's target work. It checks sample size, matrix rank,
finite coefficients, and basic ordering such as a home run being more valuable
to the offense than a single and a single being more valuable than an out.

After estimation, the scoring weights for errors, sacrifices, and fielder's choices
are replaced by the ordinary-out weight. Their original regression coefficients
remain in diagnostics. This deliberate convention reduces the amount of defensive
and runner-strategy information charged to the pitch.

On the final 2024–2025 fitting set, 24,977 half-innings meet these conditions. The
estimated scoring weights are approximately:

| Outcome | Runs |
|---|---:|
| Single | +0.5328 |
| Double | +0.8259 |
| Triple | +1.1241 |
| Home run | +1.4260 |
| Walk | +0.3956 |
| Hit by pitch | +0.4295 |
| Strikeout | −0.1233 |
| Ordinary out | −0.1081 |

These are empirical average linear weights, not exact base-state values. With no
runner positions, a single with empty bases and a single with the bases loaded
receive the same terminal weight. The half-inning completeness rules also cannot
prove that every nonterminal pitch is present.

### 6.3 Estimate the value of each count without guessing pitch order

There are twelve legal pre-pitch counts: 0–0 through 3–2. Let `V(c)` denote the
expected eventual terminal value of a plate appearance currently at count `c`.

Estimate the transition probabilities from fitting pitches. A transition can go
to another count or end in a terminal event. Then solve:

```text
V(c) = sum over next counts d of P(d | c) × V(d)
     + sum over terminal outcomes e of P(e | c) × w_e

In matrix notation: (I - Q) V = r
```

This is an absorbing Markov-chain calculation. In plain language, the value of a
count is the average of what can happen next. A two-strike foul loops back to the
same count. The program solves all twelve relationships together with linear algebra.

Every count requires at least 30 fitting observations, and an ill-conditioned
system causes an explicit error. The model averages over batters and pitchers;
it assumes count is a sufficient state for this target construction. That is a
practical approximation, not a complete baseball simulator.

The final training count values are roughly:

| Balls / strikes | 0 strikes | 1 strike | 2 strikes |
|---|---:|---:|---:|
| 0 balls | 0.1496 | 0.1109 | 0.0543 |
| 1 ball | 0.1819 | 0.1358 | 0.0733 |
| 2 balls | 0.2305 | 0.1769 | 0.1081 |
| 3 balls | 0.3112 | 0.2588 | 0.1864 |

### 6.4 Assign a pitch run value

```text
Nonterminal pitch: RV = V(count after) - V(count before)
Terminal pitch:    RV = weight(terminal outcome) - V(count before)
```

For example, a called strike in 0–0 has approximately:

```text
RV = 0.1109 - 0.1496 = -0.0387 runs
```

Negative is good for the pitcher because it reduces the offense's expected value.
A two-strike foul has value zero under this count-based definition. A home run has
positive value. The same outcome can have a different incremental value depending
on the prior count.

The code derives the next count from the current call, not the next row. This
avoids relying on the Parquet's row order.

### Why this is not the teammate's exact xRV target

The team branch also models expected contact value using exit speed and launch
angle. This standalone implementation does not copy that target or its
feature-engineering prerequisites. It uses observed outcome run values instead.
Therefore it must be described as a **context-adjusted physical run-value model**,
not as a reproduced version of the team's contact-smoothed xRV pipeline.

An eventual integration can replace the target component with a thoroughly
cross-fitted team xRV label while retaining the physical models, summaries, and
transport API. Any such change requires revalidation and a new score reference.

## 7. Removing location and count from the quality label

Excluding location from the physical input matrix alone does not make outcomes
independent of location. A fastball at the top of the zone and the same fastball
down the middle can have different results.

We fit a separate adjustment model `g(context)` to predict the observed pitch RV
using:

- balls and strikes;
- horizontal and vertical plate location;
- pitch family;
- pitcher hand and batter side, with explicit missing-category indicators.

It does not use physical measurements, altitude, year, identity, or future outcomes
as predictors. Its target, naturally, is the observed RV.

For each fitting pitch, generate an adjustment prediction from a model that did
not train on that pitcher. Define:

```text
adjusted_RV = observed_RV - predicted_RV_from_context
```

Then train the physical model to predict `adjusted_RV` from the nine physical
features. This gives the intended separation between a location/context adjustment
and the physical-quality predictor.

### The limitation of residualization

This is a statistical adjustment. It is not proof that all location, batter, and
selection effects have disappeared. Physics and location can be correlated, and
an adjustment model without physics can remove some signal shared with physics.
Unobserved variables such as catcher skill or batter quality can remain.

Thus “pure” here means **an explicitly restricted physical predictor with a
context-adjusted label**, not a causally isolated physical talent parameter.
The scope is closer to the competition's physical Stuff+ component than a
combined model that accepts location, count, and altitude directly.

## 8. XGBoost implementation

XGBoost combines many small decision trees. Each new tree improves the residual
errors of the current collection. This lets it capture nonlinear relationships
such as a velocity effect depending on vertical movement without writing that
interaction by hand.

The code uses `XGBRegressor`, a squared-error objective, and CPU histogram-based
tree construction. It has fixed, documented hyperparameters:

| Setting | Value | Reason |
|---|---|---|
| Trees | 250 by default | Moderate fixed model size |
| Physical-model depth | 3 | Restrict complexity relative to noisy pitch outcomes |
| Adjustment/movement depth | 4 | Allow somewhat richer contextual/physical relationships |
| Learning rate | 0.04 | Each tree makes a small update |
| Minimum child weight | 40; 100 for context | Discourage tiny, unstable leaves |
| Row subsample | 0.85 | Reduce overfitting |
| Column subsample | 1.0 | Use the full small feature set |
| L2 regularization | 20 | Shrink unstable leaf values |
| L1 regularization | 0 | No L1 penalty |
| Histogram bins | 128 | Bound computation |
| Seed | 2026 | Reproducible randomized operations |
| CPU threads | 4 by default | Bound local CPU use |

There is no automatic hyperparameter search. There is no early stopping on the
2026 data or the outer validation fold. The model size is fixed before final
evaluation. If early stopping is added later, it needs a separate fitting-side
validation partition; the final test season must not choose tree counts.

Tree models do not need standardized physical inputs. The linear comparison
model does: it uses `StandardScaler` followed by `Ridge(alpha=100)`, fitted only
within the corresponding training partition.

All training is CPU based. No GPU, cloud service, live database, or web application
server is needed. Model files are native XGBoost UBJ files with a JSON manifest;
the prediction interface does not require loading an arbitrary Python pickle.

## 9. Validation and leakage controls

### 9.1 Respect the existing season split

2024 and 2025 are training years. 2026 is held out by this run. The `split` column
must agree with the requested holdout year; disagreement raises an error.

### 9.2 Outer pitcher-grouped folds

Historical pitchers are divided into three folds. Every historical pitch from the
same pitcher belongs to the same outer fold, including pitches from both years.

For each fold, fit on the other pitchers and predict the excluded pitchers. These
are **out-of-fold (OOF)** predictions. They make up the delivered historical pitch
scores and the historical normalization reference. We do not use final-model
in-sample predictions for the 2024–2025 leaderboard.

### 9.3 Refit learned components inside every outer fold

Each outer fitting partition gets its own:

- event/run weights;
- count-value system;
- context adjustment models;
- physical XGBoost and linear baseline models;
- movement models;
- support counts and reference ranges.

The excluded pitchers' outcomes cannot fit these components. The half-inning
target regression uses only half-innings that remain complete in the fitting data;
an inning split across fitting/excluded pitchers is normally omitted.

### 9.4 Inner pitcher-grouped folds for context adjustment

Within the outer fitting data, the adjustment model is itself cross-fitted by
pitcher in three folds. This prevents overly optimistic in-sample context
predictions from creating unrealistically small training residuals.

After obtaining these fitting residuals, a full fitting-side context model is
trained for predictions on the outer excluded pitchers. The outer fold is never
used to train that model.

### 9.5 Final historical models and 2026 evaluation

After OOF predictions exist, train final models on all historical training rows.
They produce the 2026 scores and are saved for hypothetical profiles. The frozen
normalization remains the historical OOF normalization; the test season does not
reset its own average to 100.

### 9.6 Baseline comparisons

For each population, compute squared error against the adjusted run-value target.
Compare:

1. **Pitch-family mean adjusted RV:** the constant baseline learned in that fit.
2. **Regularized linear physical model:** uses the same physical feature matrix.
3. **XGBoost physical model:** the proposed nonlinear model.

All competitors are evaluated on identical rows. Adding the same context
prediction back to each competitor would give the same error differences against
unadjusted observed RV. The reported error is not a comparison against a
completely context-free league-mean predictor.

```text
RMSE = square root of mean squared prediction error
MSE improvement (%) = 100 × (1 - XGBoost_MSE / constant_baseline_MSE)
```

Positive improvement means XGBoost beat the constant baseline; negative means it
lost. Small improvements are possible because single-pitch outcomes are noisy.
The run report must be read as measured, even if a comparison is unfavorable.

Metrics are reported overall, by family, and by altitude. The season holdout is
also split into pitchers seen in historical data and pitchers not seen before
2026. This distinguishes temporal evaluation from entirely new-pitcher evaluation.

### 9.7 Confidence intervals for validation

The code resamples **whole pitchers** 300 times by default, aggregating their loss
sums and pitch counts. The interval describes uncertainty in the comparison across
the sampled pitchers. It is not obtained by treating all pitches as independent.

The code reports both the interval for improvement against the constant baseline
and an interval for MSE gain over the linear model. An interval crossing zero does
not establish a clear improvement at that confidence level.

### 9.8 What this evaluation does not establish

- Pitcher folds can share games; this is pitcher holdout, not simultaneous game holdout.
- There is no genuine park holdout because stadium IDs are unavailable.
- All three altitude categories are represented during training; this does not
  validate extrapolation to an unseen altitude category or a new altitude in meters.
- No hyperparameter comparison is selected using 2026 in this implementation.
- The team has already inspected 2026 in other project analyses. It is excluded
  from fitting here, but it cannot honestly be called historically untouched.
- The supplied cleaner used whole-file statistics for some cleaning and handedness
  operations. A strict final benchmark would redo those learned preprocessing
  steps within each fold. Our evaluation is conditional on the provided cleaned file.
- Labels use average linear weights and actual contact outcomes, so they include noise.

## 10. Converting a prediction to Stuff+

For pitch family `t`, calculate the mean `mu_t` and population standard deviation
`sigma_t` of its historical OOF physical predictions. These predictions are in
adjusted offensive runs: lower is better.

```text
Stuff+ = 100 - 10 × (predicted_adjusted_RV - mu_t) / sigma_t
```

Interpretation:

- 100: the historical OOF average physical prediction for that family.
- 110: one standard deviation better in predicted adjusted run value.
- 90: one standard deviation worse.
- 110 does **not** mean 10% fewer runs, 10% more whiffs, or a 10% probability change.

The reference distribution is pitch-weighted. A pitcher who throws many pitches
contributes more observations than one who throws few. We use population SD
(`ddof=0`). A near-constant prediction distribution causes a clear failure instead
of division by an arbitrary tiny number.

We do not clip scores into a visually pleasing interval and do not force every
season or altitude to average 100. Destination-specific normalization would erase
part of the altitude difference we want to observe.

Because the numerator is a model prediction, the scale's SD is the variation in
predicted quality, not the much larger variation in realized run outcomes. A
standardized score can look well-spread even when predictive accuracy is modest;
always present its validation results alongside its rankings.

## 11. How altitude scenarios work

### 11.1 Quality and movement are distinct models

The physical quality model has no altitude category input. It evaluates the pitch
physics it is given. Therefore, identical physics produce identical quality
scores even if someone changes an altitude label in isolation.

The movement model is the mechanism for changing the physics. For each pitch
family, fit two additional XGBoost regressors:

```text
IVB = model(release velocity, spin, spin direction, release geometry, extension, altitude)
HB  = model(release velocity, spin, spin direction, release geometry, extension, altitude)
```

Altitude is encoded as three named indicators. It is not treated as an arbitrary
numeric 0/1/2 distance. The movement models do not use pitcher outcomes, batter
location, observed destination movement, or pitcher identity as features.

### 11.2 Anchor the projection to the measured pitch

Let `m_a(r)` be the movement predicted from release properties `r` at altitude `a`.
For each movement component:

```text
projected_movement(destination)
  = observed_movement(source)
  + predicted_movement(destination)
  - predicted_movement(source)
```

This preserves the pitch's measured departure from the average movement model.
It does not replace the pitch with an average pitch. At the source altitude, the
two model predictions cancel, so the source scenario exactly equals the original.
Both automated tests and the full-run integrity check verify this property.

After changing IVB and HB, keep the other physical inputs fixed and rescore with
the same family-specific quality model. Use the same frozen family normalization.

The reported primary scenario difference is:

```text
delta_extreme_vs_no_altitude
    = Stuff+(Extreme Altitude) - Stuff+(No Altitude)
```

Negative means the model projects a lower physical-quality score in extreme
altitude. The model is not forced to make this negative for every family or pitcher.

### 11.3 Support and extrapolation indicators

A source/destination category needs at least 200 fitting pitches and 10 fitting
pitchers for that family. Otherwise the scenario is unavailable. Missing source
altitude also prevents transport.

The code stores the historical 0.5th–99.5th percentile range for each nonangular
physical input. It flags observed or projected profiles outside any range. This
is an extrapolation indicator; it does not automatically invalidate a plausible
rare pitch, and it does not establish joint multivariate support inside the ranges.

### 11.4 Two different altitude tables

`observed_altitude_summary.csv` groups pitches actually observed in each category.
Those differences can reflect different pitchers, velocity, pitch mix, and game
situations. They should not be described as the effect of moving the same pitch.

`altitude_scenarios.csv` transports the **same source pitches** to all three
destinations. Its three averages use the same subset with all scenarios available.
This controls the input pitch mix within the comparison. The summary includes
`scenario_pitches` so incomplete coverage is visible.

### 11.5 What remains uncertain

The transport model is observational. Different altitude categories can also
differ in pitch-tracking calibration, personnel, climate, training choices, or
unmeasured release characteristics. The model adjusts for the measured release
variables but cannot prove that its entire category difference is caused by air.

Anchoring movement does not solve this causal identification problem. It also
assumes the movement residual carries from one environment to another.

The projection holds release velocity, spin, release geometry, and extension
fixed. It does not model a pitcher changing technique, fatigue, acclimatization,
speed loss after release, or direct effects of air on batted-ball carry. Those
belong in later modeling layers and should not be hidden inside a pure Stuff+ label.

`Extreme Altitude` is not synonymous with Harp Helu. The interface accepts the
three observed categories, not a precise altitude in meters. Within-category
stadium differences are not identifiable from the supplied field alone.

## 12. Pitcher summaries and uncertainty

The main summary has one row per pitcher and season. Scores are arithmetic means
of eligible pitch scores. That makes the overall score implicitly weighted by
the pitcher's observed pitch usage: 70% fastballs and 30% sliders gives those
weights to the family-relative scores.

The type summary adds `pitch_group`. It is the best place to explain a pitcher's
arsenal, because an overall average can hide a strong slider and a weak fastball.

There is no empirical-Bayes shrinkage in this version. Instead, sample sizes and
low-sample flags are explicit. Do not promote a five-pitch score as equally reliable
as a 500-pitch score.

### Important output columns

| Column | Interpretation |
|---|---|
| `pitcher_anon_id` | Dataset's anonymous pitcher identifier |
| `year` | Season being summarized |
| `pitch_group` | Family, where applicable |
| `pitches` | Number of scored pitches contributing to this summary |
| `games` | Number of represented games |
| `stuff_plus` | Mean score using the observed physical measurements |
| `mean_adjusted_run_value` | Mean physical-model prediction before normalization |
| `prediction_source` | `pitcher_oof` or `season_holdout` |
| `low_sample` | Fewer than 200 pitches for a type, or 300 overall |
| `outside_reference_fraction` | Fraction of pitches outside at least one stored range |
| `scenario_pitches` | Pitches supported at all three destinations |
| `stuff_plus_no_altitude` | Same-pitch-mix projection to No Altitude |
| `stuff_plus_medium_altitude` | Same-pitch-mix projection to Medium Altitude |
| `stuff_plus_extreme_altitude` | Same-pitch-mix projection to Extreme Altitude |
| `delta_extreme_vs_no_altitude` | Difference between extreme and no-altitude scenarios |
| `*_ci_low`, `*_ci_high` | Conditional 95% bootstrap intervals |

For a pitcher's summary, intervals resample whole games rather than individual
pitches. A group needs at least five games; otherwise interval fields are blank.
For scenario differences, the same resampled source games are used for the paired
difference. This is more appropriate than subtracting endpoints from two unrelated
intervals.

These intervals describe sampling variation in the observed pitches/games while
holding fitted models fixed. They do not include uncertainty from refitting XGBoost,
run-weight estimation, movement identification, or future changes in the pitcher.
They are not guaranteed prediction intervals for future performance.

## 13. Feature importance and coaching use

`feature_importance.csv` reports each physical feature's share of total training
gain within a family. The two spin-angle columns are combined into `spin_axis`.
This answers which variables the fitted trees used to reduce training error.

It does not prove:

- that changing the feature will cause improvement;
- that the direction is always positive or negative;
- that correlated inputs have uniquely separable contributions;
- that the same importance ordering generalizes to a new league or season.

The dashboard collects **all eight physical measurements**, not only
the three top-ranked inputs. The trained function depends on all nine transformed
columns. It should show the source altitude, projected movement, score, and support
flags so a coach can see what the calculation assumes.

## 14. Running the code and reusing the model

Use Python 3.12 and install the exact direct dependencies from
`requirements-stuffplus.txt`. The verified local virtual environment is `.venv`.
Calling its interpreter explicitly avoids activation-script issues on Windows.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m stuffplus train `
  --data "C:\Users\maxim\Downloads\StuffPlus\pitches_limpios.parquet" `
  --output artifacts\stuffplus_v1 `
  --jobs 4
```

An existing output directory is never overwritten. For another run, choose a new
name. Command-line options expose tree count, fold count, CPU threads, seed,
holdout year, and bootstrap repetitions. Defaults are the values documented above.

Changing those settings after seeing holdout results constitutes further model
development. It should be recorded as such, not presented as another untouched test.

### Score the synthetic example

```powershell
.\.venv\Scripts\python.exe -m stuffplus predict `
  --model-dir artifacts\stuffplus_v1\models `
  --profile examples\hypothetical_pitch.json
```

Input fields:

```json
{
  "pitch_group": "Four-Seam",
  "pitcher_hand": "Right",
  "altitude_category": "No Altitude",
  "RelSpeed": 93.0,
  "SpinRate": 2300.0,
  "SpinAxis": 200.0,
  "RelHeight": 6.0,
  "RelSide": 2.0,
  "Extension": 6.2,
  "InducedVertBreak": 17.0,
  "HorzBreak": 9.0
}
```

These are hypothetical values, not a claim about a real pitcher. Inputs use
original unmirrored sensor coordinates. For a left-hander, provide the original
signed `HorzBreak`, `RelSide`, and `SpinAxis`; the package mirrors them internally.
Do not supply already mirrored fields under the raw names.

`altitude_category` means the environment where the input IVB/HB were measured or
are assumed to hold. The function returns all destination scenarios. Merely
changing the source label while retaining an inconsistent movement profile changes
the hypothetical question; the future UI should explain this.

### Python API for a future dashboard

```python
from pathlib import Path
from stuffplus.pipeline import predict_profile

result = predict_profile(
    Path("artifacts/stuffplus_v1/models"),
    profile_dict,
)
```

The result includes observed Stuff+, three scenario scores, projected IVB/HB,
support/range indicators, and the extreme-minus-no-altitude difference. It requires
no pitch outcomes or original training data at prediction time. For an interactive
app, the `Bundle` can be cached in memory instead of reloading on every request.

A hypothetical pitcher with an arsenal would be represented by several pitch
profiles plus usage weights. This package currently exposes the single-profile
building block; it does not invent a full arsenal from a pitcher's name.

## 15. Output inventory and reproducibility

| Output | Contents |
|---|---|
| `data_audit.json` | Input dimensions, required columns, exclusions, year counts |
| `fold_assignment.csv` | Historical pitcher-to-outer-fold assignment |
| `fold_diagnostics.json` | Target weights and model support for every outer fit |
| `normalization.json` | Historical OOF mean/SD for every scored family |
| `validation_metrics.csv` | Model/baseline errors and clustered intervals |
| `movement_validation.csv` | IVB/HB held-out RMSE by family and altitude, versus type mean |
| `pitcher_summary.csv` | Pitcher-season score summaries |
| `pitcher_pitch_type_summary.csv` | Pitcher-season-family summaries |
| `observed_altitude_summary.csv` | Scores grouped by actual observed altitude |
| `altitude_scenarios.csv` | Fixed-source-pitch-mix comparisons across destinations |
| `feature_importance.csv` | Physical-feature training-gain shares |
| `pitch_scores.parquet` | All input pitch IDs, exclusions, predictions, scores, scenarios |
| `models/manifest.json` | Configuration, schema, target, support, ranges, normalization |
| `models/*.ubj` | Final context, physical-quality, and movement XGBoost models |
| `run_manifest.json` | Completion status, config, package versions, timing, SHA-256 hashes |
| `run_report.md` | Human-readable run results and limitations |

A SHA-256 hash identifies the exact input bytes and source modules used for a run.
Matching file names alone do not prove two teammates used the same dataset. The
manifest records direct package versions and Python version; exact reproducibility
also depends on hardware/library behavior and the upstream cleaned data.

The final saved models fit all training pitchers; the historical summaries use
outer-fold models. Therefore predicting a historical pitch through the saved
dashboard API need not reproduce its historical OOF score exactly. The latter
was deliberately computed without that pitcher's training data. The frozen scale
is shared, but the fitted predictor differs.

Failed runs can leave partial artifacts. A completed run has a `run_manifest.json`
with `status: complete` and the human-readable report. Use a new directory when
retrying; do not mistake a partially created folder for a successful run.

## 16. Tests and verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover:

1. Mirroring left/right geometry gives equivalent physical inputs.
2. Changing outcomes, location, or altitude labels alone does not change physical features.
3. A missing physical measurement is excluded even if the cleaner marked the row usable.
4. Pitcher-grouped folds have no pitcher overlap and cover all historical rows.
5. Walks, strikeouts, and two-strike fouls produce correct target transitions.
6. A fieldable foul requires evidence of an out to be terminal.
7. Holdout predictions cannot influence the normalizer; altitude scenarios share its scale.
8. Existing output directories are not overwritten.
9. Saving/loading real XGBoost models preserves predictions, the API preserves the
   source scenario, and impossible hypothetical inputs are rejected.

The full-data run adds end-to-end verification: all ineligible pitches remain
unscored, and every supported source-altitude scenario equals its observed score.
The actual run and serialized-model example are checked in addition to unit tests.

## 17. What to say carefully in the meeting

Use these distinctions when answering questions:

| Question | Accurate answer |
|---|---|
| Is this pure Stuff+? | The quality predictor uses only physics and a statistically context-adjusted target. It is our operational definition, not proof of causal isolation. |
| Why XGBoost? | It can represent nonlinear physical interactions with a compact tabular-data pipeline; we compare it against a linear physical baseline. |
| Why one model per family? | Physical inputs have family-dependent meanings and the dataset supplies enough examples. A shared model remains a possible future comparator. |
| Is 110 ten percent better? | No. It is one historical SD better in predicted adjusted run value for that family. |
| Does altitude enter Stuff+ directly? | No. It enters a separate movement model, which changes IVB/HB before physical rescoring. |
| Is the altitude difference causal? | No. It is an observational scenario conditional on measured release features and the transport assumptions. |
| Is Extreme Altitude definitely Harp Helu? | No. We do not have stadium IDs. |
| Are training scores in-sample? | Historical delivered scores are pitcher-held-out; 2026 is scored with models trained on earlier seasons. |
| Is 2026 completely untouched? | This pipeline excludes it from fitting, but the broader team has already examined it. |
| Is the target official xRunValue? | No. It is a training-estimated observed linear-weight run-value target, followed by context adjustment. |
| Does the model include arsenal/tunneling? | Not in this pure-physics version. The outputs are separated by family; an explicit arsenal extension is future work. |
| Are confidence intervals total model uncertainty? | No. They resample observed pitchers/games conditional on fitted models. |
| Can we use it in a dashboard now? | Yes. The local prototype scores one physical profile and shows all three altitude scenarios. It does not combine an arsenal or identify a real pitcher. |

### Suggested presentation order

1. Show the data and the explicit training/test split.
2. Explain the physical inputs and why family-specific models were chosen.
3. Explain run-value direction and the context adjustment in plain language.
4. Show measured validation results, including the linear comparison.
5. Show one pitcher's family breakdown and sample sizes.
6. Show the same-pitch-mix altitude scenarios and projected movement.
7. State the limits and what will be validated next.

## 18. Sensible next steps after this deliverable

- Align the standalone target with the team's chosen contact-smoothed xRV definition.
- Reproduce preprocessing inside fitting folds for a stricter benchmark.
- Evaluate movement portability within pitchers who appear in multiple altitude categories.
- Add game-based or time-based validation, and park holdout if stadium IDs become available.
- Compare a shared family-aware model with the separate-family approach.
- Consider a carefully cross-fitted arsenal-relative extension as a distinct model variant.
- Add full model-refitting uncertainty or shrinkage for small pitcher samples.
- Extend the prototype to support a multi-pitch arsenal with pitch-usage weights.

These are future improvements, not prerequisites secretly omitted from the
delivered training-and-summary pipeline. The current code runs end to end and
makes its statistical scope explicit.

## 19. Sources and relationship to team work

- [Official ISAC competition page](https://www.isac-app.com/competition-details/hackathon-diablos-rojos.html):
  competition objective, physical/location/combined distinction, altitude context,
  deliverables, and data-use rules.
- [FanGraphs Stuff+, Location+, and Pitching+ primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/):
  background on separating physical pitch quality from location and combined evaluation.
- [XGBoost's scikit-learn interface documentation](https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html):
  estimator use, training/evaluation separation, and native model persistence.
- Team branch `origin/etapas-0-a-2`, inspected locally: `docs/convenciones.md`,
  `docs/00_contexto_y_approach.md`, `docs/03_target.md`, `src/limpieza.py`,
  `src/target.py`, and `src/modelos_base.py`. These provided context about the
  cleaner, physical sign convention, linear-weight target strategy, and baseline expectations.
- The existing experiment in the user's `Downloads/StuffPlus` folder was inspected
  as background. This implementation addresses its stated limitations through
  explicit grouping, learned run-value labels, context adjustment, and movement transport.

All repository changes remain local. No branch switch, commit, push, teammate
message, or pull request was performed for this deliverable.

## 20. Measured results from the completed run

The run used the default configuration: three outer pitcher folds, three inner
context-adjustment folds, 250 trees per regressor, four CPU threads, and 300
bootstrap replicates. It completed in about **7 minutes 50 seconds** on this machine.
This is an observation for this run, not a guaranteed runtime on another computer.

### Coverage and reproducibility

- Input rows: **635,002**.
- Scored pitches: **617,732**.
- Eligible pitches left unscored: **0**.
- Pitches with all three supported altitude projections: **615,052**.
- Pitcher-season summary rows: **1,718**.
- Pitcher-season-family summary rows: **9,310**.
- Trained physical families: **7**.
- Saved final XGBoost models: **22** — seven quality, fourteen movement, one adjustment.
- Verified runtime: Python **3.12.14**.

The data hash, package versions, exact configuration, and source-module hashes
are recorded in `run_manifest.json`. Scores for excluded rows are blank, while
those rows remain present in `pitch_scores.parquet`.

### Overall predictive results

| Evaluation | Labeled, scored pitches | Pitchers | XGBoost RMSE | Constant RMSE | Linear RMSE | XGB MSE improvement vs constant | 95% interval |
|---|---:|---:|---:|---:|---:|---:|---:|
| Historical pitcher OOF | 488,782 | 885 | 0.184614 | 0.184569 | 0.184473 | **−0.0489%** | [−0.0814%, −0.0175%] |
| 2026 season holdout | 128,471 | 549 | 0.192064 | 0.192121 | 0.191996 | **+0.0594%** | [+0.0055%, +0.1202%] |

The scored-pitch count exceeds the evaluation-pitch count because a pitch can have
complete physics but no usable outcome label. It can be scored without being
included in an accuracy calculation.

The positive 2026 improvement is small and is relative to the **constant adjusted
RV baseline**, not the linear physical model. The linear model has lower error in
both populations. The paired MSE-gain intervals versus linear are negative in
both populations as well. Consequently, it would be incorrect to say this run
demonstrated the superiority of XGBoost.

### Results by pitch family

Values below are percent improvement in MSE against the family constant baseline.

| Family | Historical pitcher OOF | 2026 holdout |
|---|---:|---:|
| Four-Seam | +0.1041% | +0.2295% |
| Sinker | −0.0539% | −0.0056% |
| Cutter | −0.4727% | −0.1451% |
| Slider | −0.0294% | −0.0058% |
| Curveball | −0.1939% | +0.0281% |
| Changeup | −0.1103% | +0.0620% |
| Splitter | −1.7992% | −1.3345% |

The separate-family design is understandable and technically supported by minimum
sample counts, but those thresholds do not establish that every family model is
reliable. Splitter is an especially clear example: passing the minimum row count
did not make this nonlinear model competitive. Pooling families or stronger
regularization is a reasonable future comparison using historical validation.

Do not use the table as a reason to repeatedly tune against 2026. A later modeling
iteration should document its selection process and use training-side validation.

### Which inputs the fitted trees used most

These are the leading three variables by final-model training gain, not a claim
about intervention effects:

| Family | First | Second | Third |
|---|---|---|---|
| Four-Seam | IVB | Velocity | Release side |
| Sinker | HB | Release height | Spin axis |
| Cutter | Spin axis | Velocity | Release height |
| Slider | Spin axis | Velocity | HB |
| Curveball | Velocity | Spin rate | Release height |
| Changeup | HB | Spin axis | Extension |
| Splitter | Spin axis | Release side | Release height |

### Working hypothetical-profile example

The saved-model API was run on `examples/hypothetical_pitch.json`, a synthetic
right-handed 93 mph four-seam with 2,300 rpm, 17 inches IVB, and 9 inches HB at
No Altitude. Other inputs are specified in the example file.

| Scenario | Projected IVB | Projected arm-side HB | Stuff+ |
|---|---:|---:|---:|
| No Altitude | 17.000 in | 9.000 in | 105.413 |
| Medium Altitude | 13.974 in | 7.800 in | 96.464 |
| Extreme Altitude | 13.078 in | 7.480 in | 90.659 |

The extreme-minus-no-altitude difference is **−14.754 Stuff+ points**. The source
scenario reproduces the input physics and observed score exactly. All three
scenarios met the stored support and univariate-range checks in this example.

This demonstrates a working transport-and-rescore calculation. It does not prove
that moving a real pitcher to a specific stadium will cost exactly 14.754 points.
The score scale, model accuracy, category confounding, and uncertainty limitations
still apply. Use this example to explain the calculation, not to sell a precise
causal forecast.

### Verification completed

All nine unit tests passed. The full-data checks confirmed preservation of every
input row, no scores for excluded rows, source-altitude scenario identity, and
complete scoring of eligible pitches. Additional output checks verified summary
averages against pitch-level results, historical OOF centering, unique pitcher
fold assignment, and saved-model predictions against actual held-out pitch scores.

The completed engineering deliverable is the reusable training pipeline, its
outputs, and its documented methodology. The scientific result is a transparent
first XGBoost baseline with meaningful limitations and a stronger linear comparator
already identified—not a claim that the modeling competition has been solved.
