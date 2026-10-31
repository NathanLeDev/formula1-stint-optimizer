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
  reading of the offsets changes. Result: the order still does not appear (soft faster than hard on 18/37 races,
  medium on 17/37), so the disorder is not an extrapolation artefact.
- **The fuel term is fitted**, and absorbs the lighter car *and* track evolution. It is not a physical measurement.
  The fixed constant used for the section 8 picture (0.058 s/lap) is an assumption: 110 kg / 56 laps = 1.96 kg per lap,
  x 0.03 s per kg, neither number sourced (110 kg is the 2025 maximum; teams may carry less). For Austin the fitted
  value is -0.069.
- **2026 is held out of training.** Median slope 0.053 / 0.051 / 0.039 / 0.025 for 2023-2026, and the 2026 fuel
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
- All three models are scored on the same races (76; 62 for 2023-2025 evaluation). 2026 laps remain in
  the training folds of the 2023-2025 evaluation.
- Same circuits and same 10-stint floor when comparing the age window (<= 15 laps) with and without.

## Phase 2: the target
- **Target = `gap`**: lap time minus the median clean lap of the same race, over all drivers, in seconds
  (`f1data.add_target`). Chosen among five candidates (raw time, gap to the race median, ratio to the fastest lap, gap to the
  driver's own median, gap to the median of the same lap across the field).
- **Not the driver's own median**: a one-stopper and a two-stopper do not run the same average tyre age, so the target would move
  with the strategy the simulator scores. Twenty drivers absorb that.
- **Not the median of the same lap across the field**: it removes fuel, weather and restarts, which are what the model has to learn.
- **Seconds, not a ratio**: pit loss and slope are in seconds and the simulator adds them. Checked: spread of the gap per circuit
  0.94-2.10 s (x2.25) vs 1.13-2.11 % of a lap (x1.87); lap length explains 21 % of the spread; the relative scale does not tidy the range.
- **One constant per race, computed once on the full table, stored in `ref_pace`.** Recomputed on a subset (tyre age <= 15 laps) it moves by up
  to 1.25 s, more than the error to beat. `check_target()` asserts median gap 0 per race and no missing values.
- **What the target keeps and removes**: keeps fuel, driver and team level, tyre age, compound, weather; removes the level of the race itself
  (that season's car, the track state that day). Consequence: the median is not known before the race, so results rank models and strategies
  and do not forecast absolute lap times.
- Race eligibility guard: >= 200 clean laps and >= 12 drivers (excludes nothing on 2023-2026).

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
