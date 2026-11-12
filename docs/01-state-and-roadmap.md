# formula1-stint-optimizer — state and roadmap

Last updated: 2026-11-12. Repo: https://github.com/NathanLeDev/formula1-stint-optimizer (public).
Figures below come from the notebooks as re-run on 2026-11-12, after the cache fix of `69d4feb`: 3 races that a stale range
cache had kept out now enter the table (77 -> 80 races; which three is not recorded here). Phase 2 is merged on `main` (`439720f`).
Phase 3 (`trees.py`, `03-xgboost.ipynb`, `tests/`, one branch in `baseline.predict()`) is on `feature/XGBoost-prediction`,
**not committed** at the time of writing.

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
  testing are not used). 93 races held 2023-2026, 83 dry, 80 in the analysis table, 79 fitted in phase 1.
  Imola 2023 carries no lap data; Sakhir 2026 and Jeddah 2026 have no row on any endpoint.
- OpenF1 quirks: only strict `>` / `<` filter operators; `laps` and `intervals` are fetched one race at a time
  (422 on wide ranges); 404 means "no result"; 429 needs a retry; a range request is cached under a key built from
  the whole calendar, so `load_raw()` tops it up race by race (`_top_up()`).

## Time windows (one per phase, on purpose)
- **Phases 2 and 3**: fit on **2023-2024**, validate on **2025**, **2026 apart** (new regulations: never fitted on, never
  used to choose).
- **Phase 1** (the exported circuit table, `reference_circuits.csv`): slopes fitted on **2023-2025**, 2026 apart. Pit loss
  and stint lengths average 2023-2026. Decided 2026-11-12 to keep it so (see `docs/02-decisions-log.md`); the consequence is
  that a phase 1 slope has seen 2025, so a simulator check on 2025 that uses those slopes is not out of sample for them.

## Repo layout
- `app/f1data.py` — the single place for loading and cleaning: cached client `get()`, `load_raw()` (with `_top_up()`),
  `neutral_laps()`, `dry_keys()`, `clean_laps()`, `attach_stints()`, `attach_weather()`, `attach_traffic()`,
  `build_base()`, `race_stints()`, and for phase 2 `add_target()` / `check_target()`.
- `app/baseline.py` — phase 2 modelling: `split()`, `add_features()`, `fit()` / `predict()`, `residuals()`,
  `stints()` / `stint_sums()` / `stint_table()`, `evaluate()`, `compare()`, `loro()`, `plot_residuals()`.
  `predict()` calls a model's own `predict` function when the model dict carries one (phase 3).
- `app/trees.py` — phase 3: `design()`, `fit_xgb()`, `as_model()`, `race_folds()`, `cv_predict()`, `cv_reference()`,
  `partial_dependence()`, `stint_slopes()`, `race_age_slopes()`, `within()`, `boot_diff()`.
- `app/data-viz.ipynb` — phase 1 (to be renamed `01-data-viz.ipynb`).
- `app/02-baseline.ipynb` — phase 2, sections 1-9.
- `app/03-xgboost.ipynb` — phase 3, sections 1-8 and Findings.
- `tests/test_trees.py` — 9 tests on synthetic frames for `trees.py` and the `predict()` hook. Run `python -m pytest tests/`.
- `.gitignore` covers `app/data/` and `*.csv`. Dependency added for phase 3: `xgboost` 3.4.1.

## Roadmap with status

### 0. Foundations — done, tests partly missing
One module does all the cleaning (pit stops, red flags, shared boundary laps); notebooks only import it.
Done when: one function returns the clean-lap table, and the tests pass.
Status: `f1data.build_base()` is that function. Tests exist for phase 3 only. **Still to write**, on synthetic frames: shared lap
kept once, neutralised laps removed, target median zero per race; `baseline.add_features()` (the `.shift()` in `driver_level` — if it
slips, the future leaks and every model improves silently), `baseline.stints()` (the hole-free flag) and `baseline.stint_sums()`.

### 1. Understand the data — done, clean-up pending
Four plots only: quality per race (which to exclude); fuel-corrected degradation, one circuit at a time, per compound;
pit stop loss per circuit; strategies actually played (compound and stint length), which give the simulator's domain of validity.
Done when: for 2-3 circuits you can state the degradation per compound, the pit loss and the observed stint lengths.
Status: done in `data-viz.ipynb`, with a reference table per circuit and three race profiles. Reference numbers (use as non-regression checks):
- 79 races fitted, 62 in training (2023-2025), 2026 held apart; 3 911 stints, 1 819 measured pit stops (83 dry races).
  Phase 2 counts the same 3 911 stints on its table (the 7-stint gap recorded before the cache fix is gone).
- Median fitted slope per season: 0.053 (2023), 0.051 (2024), 0.039 (2025), 0.028 (2026).
- Published slope on 23 of 25 circuits (>= 2 training races), from 0.024 s/lap (Melbourne, Montreal) to 0.121 (Sakhir); dispersion measured on
  15 circuits (>= 3 races), calendar-wide fallback 0.015.
- Fuel coefficient: median about -0.057 s/lap, from -0.030 (Spielberg) to -0.097 (Spa).
- Pit stop loss: mean 23.0 s, from 20.0 (Miami) to 28.1 (Lusail); 7.9 % of stops above 30 s; 2026 at 24.7 s against 22.4-22.7 in 2023-2025.
- Held-out RMSE (leave one race out, 79 races): no tyre term 0.778, one slope 0.714, slope per compound 0.720; tyre term wins on 67/79,
  slope per compound wins on 34/79. Evaluated on the 62 races of 2023-2025: 0.757 / 0.684 / 0.689, slope per compound wins 28/62.
- Offsets read at age 10: soft faster than hard on 18/38 races, medium on 17/38; expected order on 6/21 circuits.
- Stop-count consistency test: matches the observed median number of stops on 18 of 23 circuits (misses: Interlagos, Zandvoort, Spa,
  Suzuka, Lusail; only Lusail by a real margin, 19 s).

Clean-up items, status at 2026-11-12:
1. ~~Findings use slope x length instead of the cumulative cost~~ — done: the Findings now use `slope x n(n-1)/2` (8.7 s for 20 laps at
   0.046; 39.6 s for Shanghai hard, 33 laps at 0.075).
2. Over-strong wording **still present** in the Findings: "out of sample it is worse" (should be "no better"), "A slope per compound is
   noise being fitted", and in section 11 "leaves the confound with the race phase as the explanation".
3. Test 4b is evaluated on 2023-2025 races only; 2026 laps still sit in the training folds.
4. Section 8 text (raw text, "57laps"), a garbled sentence in section 9, "0.055" stale in Findings, and the section 10 explanation cell
   still says 2023-2026 and "panels mix seasons" — not re-checked on 2026-11-12.

### 2. Target, variables, reference — done (`02-baseline.ipynb`, sections 1-9)
Original plan: normalised target (gap to the race's reference pace, not raw seconds: circuits run from 71 s (Spielberg) to 111 s (Spa-Francorchamps)); variables tyre age,
compound, fuel, track temperature, circuit, driver/team level; split by race and year (2023-2024 train, 2025 validate, never by lap; 2026 apart);
reference = a simple regression.
**Update to the plan (2026-10-31)**: the reference regression is one slope per circuit plus a compound offset, not a slope per compound and
circuit (phase 1 showed a slope per compound does not predict held-out races better).
**Revised 2026-11-01 — this reopens the line above**: section 8 measured that the compound **offset** earns nothing either, so the reference
is **`circuit` alone** (a constant, a fuel slope and a tyre slope per circuit). See `docs/02-decisions-log.md`.
Done in the notebook (executed from a fresh kernel on 2026-11-12, no error):
- `load_raw()` + `build_base()`: 75 991 laps, 80 races, 25 circuits, 4 seasons; `track_temp` on 100 % of laps, `traffic` on 94.5 %.
- Target chosen: **`gap` = lap time minus the median clean lap of the same race, in seconds**, added once by `f1data.add_target()` on the whole
  table (columns `ref_pace`, `gap`); a race needs >= 200 clean laps and >= 12 drivers (none excluded; thinnest: Miami 2025, 409 laps, 19 drivers;
  fewest drivers: Monte Carlo 2024, 16). `check_target()` asserts: median gap 0 in every race, no missing value.
- Within-race trend present, and it is **not** a fuel measurement: it nets fuel burn and the improving track against tyre wear. Raw per-race slope of
  gap on lap number: median -0.0449 s/lap, negative in 80/80 races. With tyre age in the same fit the fuel coefficient is -0.0557 s/lap (which is phase
  1's -0.057) and the age coefficient +0.0463, positive in 74/80; the two readings are tied by `raw = fuel + age x (slope of age on lap number)`, exact
  race by race (max error 2e-16). Mean gap +1.46 s over the first 5 % of the race, -0.85 s over the last 5 %. Three fuel figures circulate in the
  project and only the order of magnitude, 0.04 to 0.06 s/lap, is common to them: see `docs/03-concepts-and-maths.md` section 5.
- The reference must never be recomputed on a subset. The reference itself moves by up to 1.247 s on tyres <= 15 laps old (0.233 s on average), 0.615 s
  on clear-air laps, 0.178 s on laps with traffic known. A shift is **not** a change in the error of the same size (the two add roughly in quadrature), so
  section 4 measures the error instead: it re-references the whole table, re-splits, re-fits on 2023-2024 and scores 2025. Change against the target
  as built, `rmse` / `stint rmse`: tyres <= 15 laps **+0.095 / +2.80** (18 % of the stint error), more than the 0.064 s the tyre term was worth in phase
  1; clear air +0.015 / -0.18; traffic known -0.0002 / +0.10, i.e. nothing measurable. `rmse within driver` moves +0.003 s at worst, because a shift that
  is constant inside a race cancels out of it exactly. So the rule protects the **raw error and the stint error** — the two the simulator inherits — and
  of these three subsets only the tyre-age one shifts enough to matter.
- Seconds versus relative scale, measured on **2023-2025 only** (2026 is a different formula, and it is also the only season carrying Madring):
  24 circuits, 59 134 laps, lap 70.8 to 111.1 s (x1.57); spread of the gap per circuit 0.91 to 1.74 s (x1.90) against 1.13 to 2.22 % of a lap (x1.97);
  corr(lap, spread) +0.43, so lap length explains 18 % of the spread; corr(lap, relative spread) -0.30. On the 23 circuits with >= 2 races the spans are
  identical and the correlation is +0.45 (r2 0.20), so the verdict rests on no single-race circuit. The relative scale makes the range **wider**
  (x1.97 against x1.90) and turns the correlation negative, i.e. overcorrects, so **seconds stay**. On 2026 alone (18 circuits, one race each) the
  relative scale would look better (x1.66 against x2.01); not enough to reopen the scale. 2026 sits on the same slope as 2023-2025, raised by about 0.3 s.

Established in sections 6-9. Use as non-regression checks.

**Variables** (`baseline.add_features`, computed on the whole table **before** the split):
- `race_frac` = lap number / highest lap number of that race in the raw table.
- `driver_level` = sum of the driver's mean gap over at most his 5 previous races / (that count + 3); range -0.989 to +1.922 s; 2.2 % of
  (race, driver) still at the no-history default. Four checks hold: constant inside a (race, driver); exactly 0 on each driver's first race
  (34/34); a brute-force recomputation from past races only matches to 4e-16 over 1 581 (race, driver); and it correlates **more** with the
  driver's previous race (+0.860) than with the race it is attached to (+0.771), which is the signature of no look-ahead.

**Split** (`baseline.split`, by whole race and season): train 2023-2024 38 785 laps / 41 races / 24 circuits; valid 2025 20 349 / 21 / 21;
apart 2026 16 857 / 18 / 18. No race in two samples, no lap lost. `Madring` (2026) is never trained (5.9 % of the 2026 laps).
- **Only 17 of 24 training circuits clear `MIN_TRAIN_RACES` = 2**, so `own coef` is 0.815 on train, **0.692 on valid 2025** and 0.678 on 2026:
  nearly a third of the validation is predicted by the calendar-wide fallback. Cause: Interlagos 2024, Monte Carlo 2023, Montreal 2024,
  Silverstone 2024 and Zandvoort 2023 were excluded as wet, Shanghai was not held in 2023, and Imola 2023 carries no lap data (consistent with
  its cancellation; not verified outside this data). Section 9 then measured that the fallback is **not** where the circuit error comes from
  (mean absolute residual 0.205 s with own coefficients against 0.242 s on the fallback, six circuits).

**Reference errors**, fitted on 2023-2024. Cells are `rmse` / `rmse within driver` / `stint rmse`, in seconds:

| spec | train 2023-24 | valid 2025 | apart 2026 |
|---|---|---|---|
| `zero` | 1.241 / 1.043 / 20.72 | 1.199 / 1.010 / 21.70 | 1.575 / 1.047 / 24.99 |
| `circuit` | 0.914 / 0.650 / 14.63 | 0.948 / 0.695 / 15.43 | 1.433 / 0.849 / 22.13 |
| `circuit + compound` | 0.903 / 0.651 / 14.36 | 0.971 / 0.714 / 16.08 | 1.469 / 0.873 / 22.83 |
| `circuit x compound` | 0.888 / 0.651 / 13.95 | 0.960 / 0.712 / 15.72 | 1.452 / 0.865 / 22.30 |
| `circuit + driver level` | 0.768 / 0.650 / 9.69 | 0.832 / 0.695 / 11.71 | 1.100 / 0.849 / 14.00 |

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
  against 0.290 (2025) and 0.280 (2026) on the held-out ones. Not biased per season, just less certain on a season it never saw.
- Track temperature: no monotone trend (-0.214 s at 21 C, +0.256 s at 36 C, -0.140 s at 48 C).
- **Traffic**: mean residual +0.419 s on the 25.0 % of laps within `DIRTY_AIR` = 1 s of a car ahead, against -0.129 s in clear air, about 0.55 s
  of spread. Traffic **cannot be an input of the simulator** (it depends on the other cars), so this is a floor on the per-lap error, and part of
  the 45 % lap-to-lap variance above is it.

**Bridge with phase 1 — not closed.** `baseline.loro()` replays the phase 1 protocol on `gap`:

| sample | circuits with >= 2 races | laps covered | no tyre term | one slope | phase 1 |
|---|---|---|---|---|---|
| all races | 24/25 | 98.7 % | 0.796 | 0.737 | 0.778 / 0.714 |
| 2023-2025 | 23/24 | 98.7 % | 0.773 | 0.717 | 0.757 / 0.684 |
| train 2023-24 | 17/24 | 81.5 % | 0.778 | 0.696 | not measured |

The **gain** from the tyre term reproduces (0.059 s against phase 1's 0.064 s) but the **level** sits 0.023 to 0.033 s above phase 1, in the same
direction both times. **Unexplained.** Candidates, none checked: the target here is `gap` where phase 1 fitted a fuel-corrected lap time;
`loro()` applies no minimum laps per compound; the race sets may differ (80 here, 79 in phase 1). Until it closes, any comparison between a phase 1
figure and a phase 2 figure carries about 0.03 s of extra uncertainty on top of everything else.

**Deviations from the plan, to know before using these numbers:**
1. **2025 was used to choose, not only to confirm.** `loro()` fits a fixed layout and cannot rank the five specs, so the ranking above is read on
   the validation. The error of whichever spec wins is optimistic by an amount the notebook does not measure. The 2026 column is the only one
   never used for anything, and it is the honest one. (Phase 3 does not repeat this: see below.)
2. **The ladder was not built as M0-M5.** `baseline.SPECS` has five rungs, but `lap_number` (fuel) and `age` (tyre) always enter together, so M1
   and M2 are not separable, and there is **no `track_temp` rung** (M4). Phase 3 tested `track_temp` inside 2023-2024: no measurable gain.
3. **The driver level is reported one way only** (estimated on past races = honest). The optimistic variant refitted on the test race, which the
   plan asked for beside it, is not done.
4. Limit unchanged: the median of a race is not known before the race, so these numbers rank models and strategies, they do not forecast an
   absolute lap time.

Done when (met): the baseline error is known per lap and per stint bracket, and the residual plots show where it fails.
Still open: the automated tests of step 0, and deviation 3 above.

### 3. XGBoost — done (`03-xgboost.ipynb`, `trees.py`), 2026-11-12
**Protocol.** Every choice is made by 5-fold cross-validation on whole races inside 2023-2024 (41 races), criterion out-of-fold
`rmse within driver`; valid 2025 is read once with the model already chosen; 2026 apart. Assumed, not tuned: learning rate 0.05,
`subsample` 0.8, `min_child_weight` 50. Intervals: 95 %, 2 000 resamplings of whole races.

**Chosen model**: `lap_number`, `age`, `circuit`, `race_frac`, `driver_level`; depth 2; 200 trees; monotone constraint on `age`.
Cross-validation, out-of-fold `rmse within driver`, each rung against the previous one (monotone models):
- `base` (lap, age, circuit) against the reference `circuit` predicted on the same folds: -0.051 s [-0.072, -0.031].
- `+ race_frac` -0.009 [-0.015, -0.004]; `+ driver_level` -0.003 [-0.013, +0.004] (kept: it moves `rmse` 0.987 -> 0.832 and stint error
  16.9 -> 11.8 s out of fold); `+ compound` -0.0001 [-0.007, +0.007]; `+ track_temp` +0.0003 [-0.008, +0.008]. Neither of the last two kept.
- Monotone against free: +0.001 s on every rung, every interval contains zero.
- More or deeper trees degrade `rmse` and stint error while `rmse within driver` barely moves (depth 2: 100 trees 0.817 / 10.6 s, 400 trees
  0.908 / 14.6 s). The criterion picks 200 trees, the raw and stint errors would pick 100.

**Errors**, `rmse` / `rmse within driver` / `stint rmse`, in seconds:

| model | train 2023-24 | valid 2025 | apart 2026 |
|---|---|---|---|
| `circuit` | 0.914 / 0.650 / 14.63 | 0.948 / 0.695 / 15.43 | 1.433 / 0.849 / 22.13 |
| `circuit + driver level` | 0.768 / 0.650 / 9.69 | 0.832 / 0.695 / 11.71 | 1.100 / 0.849 / 14.00 |
| `xgb monotone` | 0.732 / 0.636 / 8.68 | 0.802 / 0.666 / 11.05 | 1.148 / 0.829 / 15.58 |

Differences (XGBoost minus reference), 95 % interval:
- valid 2025: `rmse within driver` vs `circuit` **-0.029 [-0.058, -0.007], lower**; stint error within (race, driver) vs `circuit` -0.07
  [-0.82, +0.54]; `rmse` vs `circuit + driver level` -0.030 [-0.074, +0.005]; stint error vs `circuit + driver level` -0.66 [-1.67, +0.29]. The
  last three: no measurable difference.
- apart 2026: `rmse within driver` -0.020 [-0.047, +0.005], no measurable difference; stint error within (race, driver) -0.90 [-1.55, -0.17],
  lower; `rmse` +0.048 [-0.002, +0.094], no measurable difference; stint error **+1.58 [+0.03, +3.28], higher**.
- Stint brackets (valid 2025, absolute, vs `circuit + driver level`): bias on stints over 30 laps -1.65 s against -5.51 s. Lag-1 autocorrelation
  inside a stint +0.714 raw, **+0.492** stint mean removed (reference +0.533): still there.

**Curves.** Partial dependence on tyre age (valid 2025): the predicted gap rises with age; pooled, no downward step between ages 1 and 40 for
either XGBoost model; without the constraint 2 of 21 circuits show a local dip, with it none. The curve is concave: +0.55 s at age 10, +1.05 s at
25, **flat from age 30 at +1.06 s** (the reference line: +1.46 s at 30, +1.96 s at 40). Mean slope ages 1-30: 0.037 s/lap (reference 0.050).
Per circuit 0.031 to 0.044 s/lap (reference -0.020 to +0.118); correlation of the two orderings +0.56. 3 110 of the 38 785 training laps (8.0 %)
are on a tyre older than 30 laps. **No cliff.** The plateau may be a selection effect (only tyres that hold are kept that long): untested, and it
must not be used to price very long stints.

**Slope error** (s/lap; see `docs/03-concepts-and-maths.md` section 11 for the definitions):
- A, per stint (>= 8 consecutive clean laps, assumed floor; 748 stints in 2025): reference 0.0725, XGBoost 0.0666, `zero` 0.0702. XGBoost vs
  reference -0.006 [-0.013, +0.001]: no measurable difference, and no model does better than predicting zero.
- B, age coefficient per race, no driver term: valid 2025 reference 0.030, XGBoost 0.016, -0.014 [-0.026, -0.002]; 2026 0.044 against 0.030,
  -0.015 [-0.029, -0.001].
- B', same with a free level per driver (added after reading 2025, it changes the reading, not the choice): valid 2025 0.028 against 0.016,
  -0.012 [-0.024, +0.001]; 2026 0.036 against 0.027, -0.009 [-0.023, +0.003]. Same size of gain, intervals reach zero.

**Verdict, as written in the notebook**: XGBoost beats the reference on races never seen by a small margin on one of the two metrics that judge
it (`rmse within driver`, 2025), with coherent curves; it does **not** beat it on the sum of a stint, and is measurably worse than
`circuit + driver level` on the absolute stint error in 2026. Its value for the simulator is the shape of its wear curve, which is also where it is
least trustworthy (the plateau): to be tested against the reference inside the simulator (step 6), not adopted on these numbers.
Do not expect a compound effect from it: compound offered to the trees, no measurable gain (third time the project measures it).

### 4. Simulator parameters — not started
Pit stop loss per circuit as a distribution (median and dispersion, with the tail), probability and timing of safety cars, a lower pit loss under safety car
(those stops are excluded so far), tyres available, stint lengths already seen. Done when: one table per circuit. Partly available already in
the phase 1 reference table (slope, sd, pit loss mean, stint lengths). Open here: the phase 1 table is fitted on 2023-2025 while the models are fitted
on 2023-2024 (see "Time windows").

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
Status: README has the key results of phases 1-3, the split and the test command; `.gitignore` is in place; tests for phase 3 only. Decision needed:
`.gitignore` excludes `*.csv`, so a small derived `reference_circuits.csv` must be added explicitly if it is committed.

### Not now
Telemetry, rain, qualifying (except possibly as a pre-race team/driver pace level if that proves the main residual), deep learning, web interface.
Traffic effects and conformal prediction for uncertainty come later, once the core is validated.
