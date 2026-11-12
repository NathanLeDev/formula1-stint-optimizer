# formula1-stint-optimizer — state and roadmap

Last updated: 2026-11-01. Repo: https://github.com/NathanLeDev/formula1-stint-optimizer (public).
Written from the working sessions of 2026-10-27 to 2026-11-01 and a read of the repo on 2026-10-31 (HEAD 0d51a3e,
dated 2026-10-27 16:42). Check the repo for anything newer.
The step 2 work of 2026-11-01 (sections 6-9 of `02-baseline.ipynb`, the stint metrics in `baseline.py`) is committed as
`72a1c8f`, not yet pushed. The corrections made after it are **not committed**: the `add_target` docstring, the lap-time
spans in sections 3 and 5, the fuel wording in section 4, and section 5 recomputed on 2023-2025.

## Goal
Predictive race strategy: model lap time as a function of tyre age, fuel and conditions, then simulate
pit-stop windows to find the strategy with the lowest predicted race time. Portfolio project
(GitHub), built by Nathan (MSc student). He wants to **understand every step**, not receive code dumps.

## Data
- Source: **OpenF1** (free, no auth, historical 2023 onward). Endpoints used: sessions, laps, stints,
  pit, weather, race_control, session_result, drivers, intervals (traffic).
- FastF1 was abandoned: since ~15 Oct 2026 the F1 livetiming archive answers 401 (F1 TV subscription
  needed; a Canal+ "Sport" option did not qualify).
- Scope: Grand Prix **races only** (session_name == "Race"; sprints, practice, qualifying and
  testing are not used). 91 races held 2023-2026, 81 dry, 77 usable.
- OpenF1 quirks: only strict `>` / `<` filter operators; `laps` and `intervals` are fetched one race at a time
  (422 on wide ranges); 404 means "no result"; 429 needs a retry.

## Repo layout (as of the 2026-10-31 read)
- `app/f1data.py` — the single place for loading and cleaning: cached client `get()`, `load_raw()`,
  `neutral_laps()`, `dry_keys()`, `clean_laps()`, `attach_stints()`, `attach_weather()`, `attach_traffic()`,
  `build_base()`, `race_stints()`, and for phase 2 `add_target()` / `check_target()`.
- `app/baseline.py` — phase 2 modelling: `split()`, `add_features()`, `fit()` / `predict()`, `residuals()`,
  `stints()` / `stint_sums()` / `stint_table()`, `evaluate()`, `compare()`, `loro()`, `plot_residuals()`.
- `app/data-viz.ipynb` — phase 1 (to be renamed `01-data-viz.ipynb`).
- `app/02-baseline.ipynb` — phase 2: sections 1-9 done (see below).
- `.gitignore` covers `app/data/` and `*.csv` (cache and generated tables); `README.md` has the key result, layout and phase 2 note.
- No tests in the repo yet.
- **Not yet pushed at the time of the read**: the phase 1 notebook updates of 28-30 Oct (offsets read at age 10, test 3 on the same
  circuits, test 4 scored on the same races plus the 2023-2025 evaluation, the explanation cells for sections 9-10). The repo copy of
  `data-viz.ipynb` is the 27 Oct version.

## Roadmap with status

### 0. Foundations — done, tests missing
One module does all the cleaning (pit stops, red flags, shared boundary laps); notebooks only import it.
Done when: one function returns the clean-lap table, and the tests pass.
Status: `f1data.build_base()` is that function and the phase 1 numbers were checked identical after the move. **No automated tests yet**:
write a few on synthetic frames (shared lap kept once, neutralised laps removed, target median zero per race). Phase 2 adds three
functions that need the same treatment: `baseline.add_features()` (the `.shift()` in `driver_level` — if it slips, the future leaks and
every model improves silently), `baseline.stints()` (the hole-free flag) and `baseline.stint_sums()`.

### 1. Understand the data — done, clean-up pending
Four plots only: quality per race (which to exclude); fuel-corrected degradation, one circuit at a time, per compound;
pit stop loss per circuit; strategies actually played (compound and stint length), which give the simulator's domain of validity.
Done when: for 2-3 circuits you can state the degradation per compound, the pit loss and the observed stint lengths.
Status: done in `data-viz.ipynb`, with a reference table per circuit and three race profiles. Reference numbers (use as non-regression checks):
- 77 races fitted, 62 in training (2023-2025), 2026 held apart; 3 756 stints, 1 735 measured pit stops.
  (Phase 2 counts **3 763** stints on the same table. The 7-stint difference is not explained.)
- Median fitted slope per season: 0.053 (2023), 0.051 (2024), 0.039 (2025), 0.025 (2026).
- Published slope on 23 of 25 circuits (>= 2 training races), from 0.024 s/lap (Melbourne, Montreal) to 0.121 (Sakhir); dispersion measured on
  15 circuits (>= 3 races), calendar-wide fallback 0.015.
- Fuel coefficient: median about -0.057 s/lap, from -0.030 (Spielberg) to -0.097 (Spa).
- Pit stop loss: mean 22.9 s, from 20.0 (Miami) to 28.1 (Lusail); 7.3 % of stops above 30 s.
- Held-out RMSE (leave one race out, 76 races): no tyre term 0.771, one slope 0.703, slope per compound 0.710; tyre term wins on 65/76,
  slope per compound wins on 34/76. Evaluated on the 62 races of 2023-2025: 0.756 / 0.683 / 0.688, slope per compound wins 28/62.
- Stop-count consistency test: matches the observed median number of stops on 19 of 23 circuits (misses: Zandvoort, Spa, Suzuka, Lusail).

Clean-up items seen at the last review (2026-10-30), check whether they are done:
1. Findings bullets "What wear costs over a stint is small" and "8 s spread larger than all the wear" use slope x length (the last-lap
   slowdown) instead of the cumulative cost slope x n(n-1)/2.
2. Over-strong wording: "worse" (should be "no better"), "settles it", "noise being fitted", "leaves the confound ... as the explanation".
3. Test 4b is evaluated on 2023-2025 races only; 2026 laps still sit in the training folds.
4. Section 8 text (raw text, "57laps"), a garbled sentence in section 9, "0.055" stale in Findings, and the section 10 explanation cell
   still says 2023-2026 and "panels mix seasons".

### 2. Target, variables, reference — done (`02-baseline.ipynb`, sections 1-9)
Original plan: normalised target (gap to the race's reference pace, not raw seconds: circuits run from 71 s (Spielberg) to 111 s (Spa-Francorchamps)); variables tyre age,
compound, fuel, track temperature, circuit, driver/team level; split by race and year (2023-2024 train, 2025 validate, never by lap; 2026 apart);
reference = a simple regression.
**Update to the plan (2026-10-31)**: the reference regression is one slope per circuit plus a compound offset, not a slope per compound and
circuit (phase 1 showed a slope per compound does not predict held-out races better).
**Revised 2026-11-01 — this reopens the line above**: section 8 measured that the compound **offset** earns nothing either, so the reference
is **`circuit` alone** (a constant, a fuel slope and a tyre slope per circuit). See `docs/02-decisions-log.md`.
Done in the notebook (executed, no error):
- `load_raw()` + `build_base()`: 73 343 laps, 77 races, 25 circuits, 4 seasons; `track_temp` on 100 % of laps, `traffic` on 94.5 %.
- Target chosen: **`gap` = lap time minus the median clean lap of the same race, in seconds**, added once by `f1data.add_target()` on the whole
  table (columns `ref_pace`, `gap`); a race needs >= 200 clean laps and >= 12 drivers (none excluded; thinnest: Miami 2025, 409 laps, 19 drivers).
  `check_target()` asserts: median gap 0 in every race, no missing value.
- Within-race trend present, and it is **not** a fuel measurement: it nets fuel burn and the improving track against tyre wear. Raw per-race slope of
  gap on lap number: median -0.0445 s/lap, negative in 77/77 races. With tyre age in the same fit the fuel coefficient is -0.0557 s/lap (which is phase
  1's -0.057) and the age coefficient +0.0476, positive in 71/77; the two readings are tied by `raw = fuel + age x (slope of age on lap number)`, exact
  race by race (max error 2e-16). Mean gap +1.49 s over the first 5 % of the race, -0.85 s over the last 5 %. Three fuel figures circulate in the
  project and only the order of magnitude, 0.04 to 0.06 s/lap, is common to them: see `docs/03-concepts-and-maths.md` section 5.
- The reference must never be recomputed on a subset. The reference itself moves by up to 1.25 s on tyres <= 15 laps old (0.24 s on average), 0.62 s on
  clear-air laps, 0.18 s on laps with traffic known. A shift is **not** a change in the error of the same size (the two add roughly in quadrature), so
  section 4 now measures the error instead: it re-references the whole table, re-splits, re-fits on 2023-2024 and scores 2025. Change against the target
  as built, `rmse` / `stint rmse`: tyres <= 15 laps **+0.095 / +2.80** (18 % of the stint error), more than the 0.068 s the tyre term was worth in phase
  1; clear air +0.015 / -0.18; traffic known -0.0002 / +0.10, i.e. nothing measurable. `rmse within driver` moves +0.003 s at worst, because a shift that
  is constant inside a race cancels out of it exactly. So the rule protects the **raw error and the stint error** — the two the simulator inherits — and
  of these three subsets only the tyre-age one shifts enough to matter.
- Seconds versus relative scale, measured on **2023-2025 only** (2026 is a different formula, and it is also the only season carrying Madring):
  24 circuits, 59 134 laps, lap 70.8 to 111.1 s (x1.57); spread of the gap per circuit 0.91 to 1.74 s (x1.90) against 1.13 to 2.22 % of a lap (x1.97);
  corr(lap, spread) +0.43, so lap length explains 18 % of the spread; corr(lap, relative spread) -0.30. On the 23 circuits with >= 2 races the spans are
  identical and the correlation is +0.45 (r2 0.20), so the verdict rests on no single-race circuit. The relative scale makes the range **wider**
  (x1.97 against x1.90) and turns the correlation negative, i.e. overcorrects, so **seconds stay**.
  Superseded figures: 0.94-2.10 s (x2.25) / 1.13-2.11 % (x1.87) / 21 %, computed on 2023-2026 with the ranges excluding single-race circuits while the
  correlations did not. Madring was the maximum of the range in seconds; removing it alone moves the correlation only from +0.460 to +0.457, so the old
  r2 was not an artefact of it, but the ranges and the correlations were not the same sample.

Established in sections 6-9 (executed from a fresh kernel; 14/14 code cells reproduce identical outputs). Use as non-regression checks.

**Variables** (`baseline.add_features`, computed on the whole table **before** the split):
- `race_frac` = lap number / highest lap number of that race in the raw table.
- `driver_level` = sum of the driver's mean gap over at most his 5 previous races / (that count + 3); range -0.989 to +1.922 s; 2.2 % of
  (race, driver) still at the no-history default. Four checks hold: constant inside a (race, driver); exactly 0 on each driver's first race
  (33/33); a brute-force recomputation from past races only matches to 4e-16 over 1 516 (race, driver); and it correlates **more** with the
  driver's previous race (+0.861) than with the race it is attached to (+0.769), which is the signature of no look-ahead.

**Split** (`baseline.split`, by whole race and season): train 2023-2024 38 785 laps / 41 races / 24 circuits; valid 2025 20 349 / 21 / 21;
apart 2026 14 209 / 15 / 15. No race in two samples, no lap lost. `Madring` (2026) is never trained (7.0 % of the 2026 laps).
- **Only 17 of 24 training circuits clear `MIN_TRAIN_RACES` = 2**, so `own coef` is 0.815 on train, **0.692 on valid 2025** and 0.671 on 2026:
  nearly a third of the validation is predicted by the calendar-wide fallback. Cause: Interlagos 2024, Monte Carlo 2023, Montreal 2024,
  Silverstone 2024 and Zandvoort 2023 were excluded as wet, Shanghai was not held in 2023, and Imola 2023 carries no lap data (consistent with
  its cancellation; not verified outside this data). Section 9 then measured that the fallback is **not** where the circuit error comes from
  (mean absolute residual 0.205 s with own coefficients against 0.242 s on the fallback, six circuits).

**Reference errors**, fitted on 2023-2024. Cells are `rmse` / `rmse within driver` / `stint rmse`, in seconds:

| spec | train 2023-24 | valid 2025 | apart 2026 |
|---|---|---|---|
| `zero` | 1.241 / 1.043 / 20.72 | 1.199 / 1.010 / 21.70 | 1.605 / 1.043 / 26.28 |
| `circuit` | 0.914 / 0.650 / 14.63 | 0.948 / 0.695 / 15.43 | 1.459 / 0.843 / 23.44 |
| `circuit + compound` | 0.903 / 0.651 / 14.36 | 0.971 / 0.714 / 16.08 | 1.493 / 0.865 / 24.23 |
| `circuit x compound` | 0.888 / 0.651 / 13.95 | 0.960 / 0.712 / 15.72 | 1.482 / 0.862 / 23.69 |
| `circuit + driver level` | 0.768 / 0.650 / 9.69 | 0.832 / 0.695 / 11.71 | 1.108 / 0.843 / 14.88 |

- No compound term shows a measurable gain on 2025. One split and no interval, so this is "no gain measured", not "worse".
- `circuit + driver level` lowers `rmse` and `stint rmse` but leaves `rmse within driver` at 0.695, identical to `circuit`: it buys nothing for
  ranking strategies of one driver in one race, which is the simulator's case. What it does show is that much of the **stint** error is a
  constant offset per driver rather than anything about tyres.
- `bias` on train is within 0.006 s of zero for the three fitted single-stage specs; it is -0.059 s for `circuit + driver level`, because
  `fit()` estimates `level_beta` in a second pass on the residuals instead of jointly. That spec is not the least-squares solution of its own
  design matrix and its coefficients should not be read as such.

**Stint-sum error** (`circuit`, valid 2025; hole-free stints of >= 2 clean laps, 847 of 988):

| bracket | stints | mean laps | rmse | bias | rmse/sqrt(n) | rmse/n |
|---|---|---|---|---|---|---|
| 1-10 | 154 | 6.4 | 5.02 | -0.34 | 1.98 | 0.782 |
| 11-20 | 275 | 15.9 | 11.25 | -1.06 | 2.82 | 0.707 |
| 21-30 | 281 | 24.6 | 16.35 | -2.21 | 3.30 | 0.665 |
| 31+ | 137 | 38.2 | 25.31 | -2.67 | 4.09 | 0.662 |

**The error on a stint sum grows much closer to `n` than to `sqrt(n)`** (`rmse/sqrt(n)` x2.1 across the brackets, `rmse/n` only -15 %). A
24.6-lap stint would cost 4.7 s on the sum if the per-lap errors were independent; it costs 16.3 s, about **3.5x** that. Measured directly in
section 9: lag-1 autocorrelation inside a stint **+0.798** raw, **+0.533** with the stint mean removed, so the correlation is not only a
constant offset. Consequence: a per-lap RMSE understates what a stint costs by a large factor, and the bias (-2.7 s on stints over 30 laps) is
systematic, so it does not cancel between two strategies using stints of different lengths.

**Residual structure** (`circuit`, valid 2025):
- Variance split, exact decomposition of the sum of squares: between races 6.9 %, **between drivers inside a race 39.2 %**, between stints
  inside a driver-race 8.9 %, **between laps inside a stint 45.0 %**. The race is already known (that is what `gap` references); the driver is
  the largest structured term.
- Driver: the driver-race mean residual correlates +0.687 with `driver_level`; adding the term takes that to -0.039 and its standard deviation
  from 0.664 s to 0.483 s.
- Tyre age x compound: the residual rises with age on SOFT (-0.153 s at age 8 to +0.143 s at 22) and drifts the other way on HARD (-0.044 s at
  age 2 to -0.153 s at 32), 0.227 s apart read at age 22. One slope per circuit sits between the two. Phase 1 showed the direct per-compound fit
  does not pay on held-out races, so this is a structure the reference does not carry, **not** a fix known to work.
- Circuit: -0.540 s (Suzuka) to +0.827 s (Miami), sd 0.290 s over 21 circuits. Miami is also the thinnest race in the table (409 laps, 19 drivers).
- Season: mean residual per race within 0.040 s of zero in all four seasons; dispersion 0.154 (2023) and 0.099 (2024) on the fitted seasons
  against 0.290 (2025) and 0.250 (2026) on the held-out ones. Not biased per season, just less certain on a season it never saw.
- Track temperature: no monotone trend (-0.214 s at 21 C, +0.256 s at 36 C, -0.140 s at 48 C).
- **Traffic**: mean residual +0.419 s on the 25.0 % of laps within `DIRTY_AIR` = 1 s of a car ahead, against -0.129 s in clear air, about 0.55 s
  of spread. Traffic **cannot be an input of the simulator** (it depends on the other cars), so this is a floor on the per-lap error, and part of
  the 45 % lap-to-lap variance above is it.

**Bridge with phase 1 — not closed.** `baseline.loro()` replays the phase 1 protocol on `gap`:

| sample | circuits with >= 2 races | laps covered | no tyre term | one slope | phase 1 |
|---|---|---|---|---|---|
| all races | 24/25 | 98.6 % | 0.791 | 0.729 | 0.771 / 0.703 |
| 2023-2025 | 23/24 | 98.7 % | 0.773 | 0.717 | 0.756 / 0.683 |
| train 2023-24 | 17/24 | 81.5 % | 0.778 | 0.696 | not measured |

The **gain** from the tyre term reproduces (0.062 s against phase 1's 0.068 s) but the **level** sits 0.026 to 0.034 s above phase 1, in the same
direction both times. **Unexplained.** Candidates, none checked: the target here is `gap` where phase 1 fitted a fuel-corrected lap time;
`loro()` applies no minimum laps per compound; the race sets may differ (77 here, 76 quoted). Until it closes, any comparison between a phase 1
figure and a phase 2 figure carries about 0.03 s of extra uncertainty on top of everything else.

**Deviations from the plan, to know before using these numbers:**
1. **2025 was used to choose, not only to confirm.** `loro()` fits a fixed layout and cannot rank the five specs, so the ranking above is read on
   the validation. The error of whichever spec wins is optimistic by an amount the notebook does not measure. The 2026 column is the only one
   never used for anything, and it is the honest one.
2. **The ladder was not built as M0-M5.** `baseline.SPECS` has five rungs, but `lap_number` (fuel) and `age` (tyre) always enter together, so M1
   and M2 are not separable, and there is **no `track_temp` rung** (M4). Decided: if one is added it will be judged by `loro()` on 2023-2024,
   never on the 2025 residual panel.
3. **The driver level is reported one way only** (estimated on past races = honest). The optimistic variant refitted on the test race, which the
   plan asked for beside it, is not done.
4. Limit unchanged: the median of a race is not known before the race, so these numbers rank models and strategies, they do not forecast an
   absolute lap time.

Done when (met): the baseline error is known per lap and per stint bracket, and the residual plots show where it fails.
Still open: the automated tests of step 0, and deviation 3 above.

### 3. XGBoost / Random Forest — not started
To check: the predicted time must increase with tyre age (partial dependence on age); otherwise the model learned something else (team speed,
for example). XGBoost can enforce this with a monotonic constraint on age — an option to try and to compare.
To compare: the error on the degradation slope matters more than the mean error per lap; use the same validation races as the baseline and the
stint-sum error. **To beat on valid 2025** (`rmse` / `rmse within driver` / `stint rmse`): `circuit` 0.948 / 0.695 / 15.43, and
`circuit + driver level` 0.832 / 0.695 / 11.71. Judge it on `rmse within driver` and on the stint brackets, not on the raw RMSE, since the
simulator ranks strategies for one driver in one race.
Interface note before starting: `baseline.evaluate()` takes a model dict and calls `baseline.predict()`, so scoring a tree model means either
giving it that interface or changing `residuals()` / `evaluate()` to take a vector of predictions. Decide which, once.
Done when: it beats the baseline on races never seen, with coherent curves. If it does not beat it, that is a valid result: write it down.
Do not expect a compound effect from it: compound information is unreliable in this data (phase 1, section 11).

### 4. Simulator parameters — not started
Pit stop loss per circuit as a distribution (median and dispersion, with the tail), probability and timing of safety cars, a lower pit loss under safety car
(those stops are excluded so far), tyres available, stint lengths already seen. Done when: one table per circuit. Partly available already in
the phase 1 reference table (slope, sd, pit loss mean, stint lengths).

### 5. Simulator — not started
A race is a sequence of stints. Total time = sum of predicted lap times + pit losses. Respect the two-different-compounds rule in the dry and stay
within observed stint lengths. Then add random draws (safety car, pit loss, slope from its dispersion) to get a time distribution per strategy.
Plots: map of total time by stop lap and compound combination; boxplots of strategies under uncertainty.
Open decision: the model cannot tell compounds apart, so the two-compound rule can only act as "at least one stop" unless observed compound sequences are used.
Done when: one recommendation per race, with its uncertainty margin.

### 6. Validation — not started
Calibration: is the predicted total time for the strategy actually played close to the real time? Comparison: simulator with the baseline model against
simulator with XGBoost. Limit to write: fast drivers pit at chosen moments, so a counterfactual strategy is hard to validate.
Done when: a clear results table, including the cases where it fails.

### 7. GitHub — partly done
README (problem, data, method, results, limits), reproduction commands, tests, a small sample of derived data (not the raw data), figures.
Status: README with key result and layout exists; `.gitignore` is in place; tests missing. Decision needed: `.gitignore` excludes `*.csv`, so a small derived
`reference_circuits.csv` must be added explicitly if it is committed.

### Not now
Telemetry, rain, qualifying (except possibly as a pre-race team/driver pace level if that proves the main residual), deep learning, web interface.
Traffic effects and conformal prediction for uncertainty come later, once the core is validated.
