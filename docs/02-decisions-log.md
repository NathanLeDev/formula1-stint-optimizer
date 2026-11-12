# Decisions log — formula1-stint-optimizer

One entry per decision: what was chosen, why, and what would change it. Dates are 2026.

## Data and cleaning
- **OpenF1 instead of FastF1** (Oct 2026). FastF1's livetiming archive now returns 401 (F1 TV subscription
  needed). OpenF1 is free and covers 2023 onward; 2018-2022 returns 404.
- **Races only.** Practice, qualifying, testing and sprints are loaded as calendar entries but their laps
  are never used. Possible later use: qualifying / practice for a driver and team pace level known before the race.
- **Lap cleaning** (`f1data.clean_laps`, `neutral_laps`, `dry_keys`, `attach_stints`):
  drop laps with no time, out-laps, in-laps (entry lap from the `pit` endpoint), laps above 1.10 x the race's
  best lap, lap 1 (standing start); drop laps under safety car, virtual safety car or red flag (from the
  deployment, or the red flag, through the lap after the restart); keep dry races only (mean rainfall <= 0.1;
  a race with no weather rows counts as dry — to check).
- **A yellow flag is not a neutralisation.** Section 6 measures yellows separately; the two rank circuits differently.
- **A lap shared by two stints** (the pit lap closes one and opens the next) belongs to the stint that ends.
- **One table built in one place.** `build_base()` replaced three cells of the notebook that each built
  their own version; results were checked identical after the move.

## Tyre degradation model
- **Fitted per race, all drivers pooled**: `time = driver pace + compound offset + fuel x lap number + slope x tyre age`.
  Per driver it is impossible: inside one driver's stint age is an affine function of lap number, so fuel and
  wear are collinear. Drivers pit on different laps, which separates the two effects. A race keeps compounds with
  at least 25 clean laps and needs at least two compounds; a rank check rejects degenerate fits.
- **One slope per circuit, compounds pooled.** A slope per compound did not predict held-out races better
  (see section 11 results). The compound keeps an offset in the model but offsets are not exported.
- **Offsets are read at a common age of 10 laps**, not at age 0. A tyre run mostly at ages 5-15 has an age-0
  value tied to its slope (steeper slope => lower intercept). Predictions are unchanged by the shift; only the
  reading of the offsets changes. Result: the order still does not appear (soft faster than hard on 18/38 races,
  medium on 17/38), so the disorder is not an extrapolation artefact.
- **The fuel term is fitted**, and absorbs the lighter car *and* track evolution. It is not a physical measurement.
  The fixed constant used for the section 8 picture (0.058 s/lap) is an assumption: 110 kg / 56 laps = 1.96 kg per lap,
  x 0.03 s per kg, neither number sourced (110 kg is the 2025 maximum; teams may carry less). For Austin the fitted
  value is -0.069.
- **2026 is held out of training.** Median slope 0.053 / 0.051 / 0.039 / 0.028 for 2023-2026, and the 2026 fuel
  limit is 70 kg instead of 110. `slope 2026` is reported beside the training value, never merged.
- **Publication rules**: a slope needs >= 2 training races, its dispersion >= 3; below 3 the cell carries the
  calendar-wide median (0.015 s/lap). Silverstone (1 race) and Madring (0) publish no slope.
- **Plain medians for the slope across races**, standard deviation between races as the dispersion (the in-race
  standard error, 0.005, understates it).

## Pit stop loss
- Loss = in-lap time + out-lap time - 2 x reference, where the reference is the median of the driver's clean laps
  within +-3 laps. Kept: stops in dry races, not under neutralisation, loss between 10 and 45 s.
- Stops under safety car are excluded, so the loss describes green-flag stops only; modelling a lower loss under
  safety car is a planned step because that is where strategies are decided.
- Use a **distribution per circuit** (central value plus tail), not a constant. The mean is pulled up by a tail
  (Monza: most stops 24-26 s, mean 26.0 s). Part of the tail may be measurement (stop under a yellow flag or behind a slow car).
- The exported pit loss and stint lengths average 2023-2026 (observations, not fitted parameters).

## Validation (phase 1)
- **Leave one race out inside each circuit**, three nested models (no tyre term, one slope, one slope per compound),
  every driver of the held-out race keeps a free pace level (so only the tyre and fuel structure is scored).
  This makes the RMSE comparative, not a true forecast error.
- All three models are scored on the same races (79; 62 for 2023-2025 evaluation). 2026 laps remain in
  the training folds of the 2023-2025 evaluation.
- Same circuits and same 10-stint floor when comparing the age window (<= 15 laps) with and without.

## Phase 2: the target
- **Target = `gap`**: lap time minus the median clean lap of the same race, over all drivers, in seconds
  (`f1data.add_target`). Chosen among five candidates (raw time, gap to the race median, ratio to the fastest lap, gap to the
  driver's own median, gap to the median of the same lap across the field).
- **Not the driver's own median**: a one-stopper and a two-stopper do not run the same average tyre age, so the target would move
  with the strategy the simulator scores. Twenty drivers absorb that.
- **Not the median of the same lap across the field**: it removes fuel, weather and restarts, which are what the model has to learn.
- **Seconds, not a ratio**: pit loss and slope are in seconds and the simulator adds them. Checked on **2023-2025 only**, since 2026 is a different
  formula: 24 circuits, spread of the gap per circuit 0.91-1.74 s (x1.90) vs 1.13-2.22 % of a lap (x1.97); lap length explains 18 % of the spread
  (corr +0.43); the relative scale makes the range **wider**, not tighter, and turns the correlation negative (-0.30), i.e. overcorrects. The spans are
  identical on the 23 circuits with >= 2 races, so the verdict rests on no single-race circuit. What would change it: a future circuit both long and
  wide. (The earlier x2.25 / x1.87 / 21 % figures came from 2023-2026, with the ranges and the correlations computed on different circuit sets.)
- **One constant per race, computed once on the full table, stored in `ref_pace`.** Recomputed on a subset the reference moves by up to 1.25 s
  (tyre age <= 15 laps). That shift is **not** an error of the same size: the two add roughly in quadrature, and re-fitting on that target costs
  +0.095 s of raw RMSE and +2.80 s of stint error on 2025 — real, and more than the +0.064 s the whole tyre term was worth in phase 1, but not the
  ~18x the raw 1.25 s would suggest. On the laps whose traffic is known the same exercise costs nothing measurable (-0.0002 s). And `rmse within
  driver` is immune by construction: a shift constant inside a race cancels when the mean of each (race, driver) is removed. So the rule protects the
  raw error and the stint error, the two the simulator inherits. `check_target()` asserts median gap 0 per race and no missing values.
- **What the target keeps and removes**: keeps fuel, driver and team level, tyre age, compound, weather; removes the level of the race itself
  (that season's car, the track state that day). Consequence: the median is not known before the race, so results rank models and strategies
  and do not forecast absolute lap times.
- Race eligibility guard: >= 200 clean laps and >= 12 drivers (excludes nothing on 2023-2026).

## Phase 2: variables, split, reference and metrics
- **Variables are computed on the whole table, before the split** (`baseline.add_features`). `driver_level` reads only races that precede a lap
  in date order, so the whole table carries no more information than a race already had at its start. Computed after the split, a driver in an
  early 2025 race would lose his 2024 history and the variable would not mean the same thing in the two samples.
- **`driver_level` is deliberately shrunk** and is not an unbiased level: the sum of the mean gap over at most 5 previous races, divided by
  (that count + 3), so a full window keeps 5/8 of the measured mean and a single race keeps 1/4. `fit()` estimates `level_beta` on it, so the
  shrinkage decides how much a short history is trusted, not the size of the effect.
- **Split by whole race and season, never by lap.** Two laps of the same race share the `ref_pace` that defines their target, so a lap-level
  split would put part of a race's median in training and the rest in validation, and the error would come out too low for a reason unrelated
  to the model.
- **2026 is apart, not in the validation.** New regulations (median slope 0.028 s/lap against 0.051 in 2024), so it is kept out of both the fit
  and the model choice, and read as how far the reference travels rather than as a target to tune on.
- **The reference is `circuit` alone** (2026-11-01). **This revises the 2026-10-31 decision "one slope per circuit plus a compound offset"**: on
  valid 2025 the offset shows no measurable gain (0.971 s against 0.948 s rmse, and higher on every other metric), and neither does a fit per
  (circuit, compound) cell (0.960 s). One split with no interval attached, so the claim is "no gain measured", not "worse". What would change
  it: an interval on the difference, or a method that borrows the compound slope across circuits.
- **Two errors per lap, and one per stint.** `rmse` is the raw error. `rmse within driver` removes the mean of each (race, driver) and is both
  the one comparable with phase 1 and the one that matters for the simulator, where a driver's level is a constant. `mae` sits beside the RMSE
  because the two part company when a few large errors dominate.
- **The stint-sum error is measured on hole-free stints of at least 2 clean laps**, in brackets 1-10 / 11-20 / 21-30 / 31+. Only 1 stint in
  3 911 keeps every lap it ran (the cleaning removes the pit-out lap, the pit-in lap and lap 1), so "the sum of a whole stint" is not available;
  82.9 % have their clean laps consecutive, which is what the simulator adds. A stint with a hole inside it is left out rather than summed
  across the hole, and a one-lap "sum" is already covered by the per-lap RMSE. Cost: the 17.1 % left out skew long, so this is a selection and
  is stated as one. Brackets are on the clean consecutive laps, not on the nominal stint length.
- **`loro()` has two separate uses.** On the whole table it is the only version comparable with phase 1's 0.714 s; restricted to 2023-2024 it
  would not compare at all. On 2023-2024 alone it is the only version that may decide a variable, since deciding on the whole table means
  deciding on 2025 and 2026. On 2023-2024 it covers only 17 of 24 circuits (81.5 % of the laps), so it is a weaker arbiter here than in phase 1.
- **The phase 2 replay does not reproduce phase 1's 0.714 s**: it gives 0.737 s on the whole table (80 races against 79), and 0.717 s against
  0.684 s on 2023-2025.
  Recorded as open, not resolved by adjusting either number. See `docs/01-state-and-roadmap.md` for the candidate causes.
- **Known deviation: 2025 was used to choose, not only to confirm.** `loro()` fits a fixed layout and cannot rank the five specs, so the ranking
  comes from the validation. Recorded rather than fixed; the 2026 column is the honest one.
- **`circuit + driver level` is a two-stage fit**, which is why its training bias is -0.059 s instead of ~0: `level_beta` is estimated on the
  residuals of the other coefficients, not jointly with them. Its coefficients are not least-squares estimates of its own design matrix. What
  would change it: one joint `lstsq` with the level as a column.
- **Traffic is measured, never used as an input.** Mean residual +0.419 s on the 25 % of laps within 1 s of a car ahead against -0.129 s in
  clear air. It depends on the other cars, so it sets a floor on the per-lap error rather than offering a variable; phase 3 is to be judged on
  the error it reaches despite it, not against an error that pretends traffic is knowable.

- **Phase 1 keeps its 2023-2025 window** (2026-11-12). The exported circuit table stays fitted on 2023-2025 while phases 2 and 3 fit on
  2023-2024. Why: the table is an input of the simulator, the models are what is being judged, and the choice of window for simulator inputs
  belongs to step 4. Consequence, recorded as a limit: a phase 1 slope has seen 2025. What would change it: step 4 deciding the windows of
  every simulator input together.

## Phase 3: XGBoost (2026-11-12)
- **A tree model is scored through `baseline.predict()`**: one branch calls the model's own `predict` when the model dict carries one, so
  `evaluate()`, `stint_table()` and `plot_residuals()` score XGBoost and the reference with the same code on the same laps and stints.
  Chosen over changing `residuals()` / `evaluate()` to take a vector, which would have touched every phase 2 call.
- **Every phase 3 choice is made inside 2023-2024**, by 5-fold cross-validation on whole races, criterion out-of-fold `rmse within driver`.
  2025 is read once. This is the phase 2 deviation (2025 used to choose) not repeated. One exception, stated in the notebook: definition B'
  of the slope error was added after reading 2025; it changes how the slope is read, not which model was chosen.
- **Model kept**: `lap_number`, `age`, `circuit`, `race_frac`, `driver_level`; depth 2; 200 trees; monotone on `age`. `compound` and
  `track_temp` show no measurable gain inside 2023-2024 and are left out. `traffic` is never a feature.
- **The monotonic constraint on age is kept**: no measurable cost (+0.001 s out of fold, every interval contains zero), and it removes local
  dips on 2 of 21 circuits. What would change it: a measurable cost on a larger sample.
- **`driver_level` is kept for the raw and stint errors**, not for `rmse within driver` (-0.003 s [-0.013, +0.004], as expected for a level
  constant inside a race).
- **200 trees, not 100**: the criterion fixed in advance picks 200; the raw and stint errors would pick 100 (about 0.015 s and 1.2 s out of
  fold). Recorded rather than re-chosen after the fact.
- **The slope error has two definitions, both reported** (`docs/03-concepts-and-maths.md` section 11): A per stint, B (and B') per race.
- **Differences are given with a 95 % interval from resampling whole races**, not as win counts.
- **Verdict recorded as is**: XGBoost beats the reference on `rmse within driver` on 2025 (-0.029 s [-0.058, -0.007]) and not on any
  stint-sum error; on 2026 it is higher than `circuit + driver level` on the absolute stint error. Not adopted as the simulator's model on
  these numbers: both models go to step 6.

## Strategy arithmetic
- With equal stints, the extra time of k stops over a race of L laps is
  `k x pit + slope x L x (L/(k+1) - 1) / 2`; take the minimum over k >= 1 (two-compound rule).
  It matches the observed median number of stops on 19 of 23 circuits. It is a consistency check, not a validation
  (slope and stops come from the same races).
- The simulator should only offer stints similar to those observed on the circuit; the compound choice stays outside
  the simulator until the compound confound is resolved.

## Repo and process
- Cache and generated CSV go to `app/data/` (git-ignored). Never commit tokens or `.env`.
- Notebook outputs are kept in the repository (a recruiter should see results without running anything).
- Workflow rule: change one thing at a time and re-run the notebook; after a refactor compare to the reference
  numbers in the state document.
