# formula1-stint-optimizer — state and roadmap

Last updated: 2026-10-31. Repo: https://github.com/NathanLeDev/formula1-stint-optimizer (public).
Written from the working sessions of 2026-10-27 to 2026-10-30 and a read of the repo on 2026-10-31 (HEAD 0d51a3e,
dated 2026-10-27 16:42). Check the repo for anything newer.

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
- `app/data-viz.ipynb` — phase 1 (to be renamed `01-data-viz.ipynb`).
- `app/02-baseline.ipynb` — phase 2, started: sections 1-5 done (see below).
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
write a few on synthetic frames (shared lap kept once, neutralised laps removed, target median zero per race).

### 1. Understand the data — done, clean-up pending
Four plots only: quality per race (which to exclude); fuel-corrected degradation, one circuit at a time, per compound;
pit stop loss per circuit; strategies actually played (compound and stint length), which give the simulator's domain of validity.
Done when: for 2-3 circuits you can state the degradation per compound, the pit loss and the observed stint lengths.
Status: done in `data-viz.ipynb`, with a reference table per circuit and three race profiles. Reference numbers (use as non-regression checks):
- 77 races fitted, 62 in training (2023-2025), 2026 held apart; 3 756 stints, 1 735 measured pit stops.
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

### 2. Target, variables, reference — in progress (`02-baseline.ipynb`)
Original plan: normalised target (gap to the race's reference pace, not raw seconds: circuits run from 70 to 105 s); variables tyre age,
compound, fuel, track temperature, circuit, driver/team level; split by race and year (2023-2024 train, 2025 validate, never by lap; 2026 apart);
reference = a simple regression.
**Update to the plan**: the reference regression is **one slope per circuit plus a compound offset**, not a slope per compound and circuit
(phase 1 showed a slope per compound does not predict held-out races better).
Done in the notebook (executed, no error):
- `load_raw()` + `build_base()`: 73 343 laps, 77 races, 25 circuits, 4 seasons; `track_temp` on 100 % of laps, `traffic` on 94.5 %.
- Target chosen: **`gap` = lap time minus the median clean lap of the same race, in seconds**, added once by `f1data.add_target()` on the whole
  table (columns `ref_pace`, `gap`); a race needs >= 200 clean laps and >= 12 drivers (none excluded; thinnest: Miami 2025, 409 laps, 19 drivers).
  `check_target()` asserts: median gap 0 in every race, no missing value.
- Fuel signature present (per-race slope of gap on lap number: median -0.0445 s/lap, negative in 77/77 races; mean gap +1.49 s over the first 5 %
  of the race, -0.85 s over the last 5 %).
- The reference must never be recomputed on a subset: redone on tyres <= 15 laps old it moves by up to 1.25 s (0.24 s on average); on clear-air laps up to
  0.62 s; on laps with traffic known up to 0.18 s.
- Seconds versus relative scale: spread of the gap per circuit 0.94 to 2.10 s (x2.25) against 1.13 to 2.11 % of a lap (x1.87); lap length explains 21 %
  of the spread (corr +0.46, relative: -0.20). Relative scale does not tidy the range, so **seconds stay**.

To do next in step 2:
- **Split**: train 2023-2024, validate 2025, 2026 apart. Choose features by leave-one-race-out inside 2023-2024 and read 2025 once at the end.
- **Model ladder** (each rung must lower the validation error): M0 circuit median, M1 + fuel (fraction of race), M2 + tyre age with one slope per
  circuit, M3 + compound offset, M4 + track temperature, M5 + team/driver level estimated on **past** races only.
- **Metrics**: RMSE and MAE per lap, bias, and the **error on the sum of a whole stint** by length bracket (the simulator adds laps).
- **Residual plots**: by tyre age, race fraction, compound, circuit, season, driver/team, track temperature, traffic, mean residual per race,
  lag-1 autocorrelation inside a stint; variance split between races, drivers and within stints.
- Traffic and dirty-air columns explain residuals but **cannot be inputs of the simulator** (they depend on other cars).
- Report the driver level two ways (estimated on past races = honest; refitted on the test race = optimistic, like the 0.703 of phase 1).
- Limit to state: the median of a race is not known before the race, so the numbers rank models and strategies, they do not forecast an
  absolute lap time.
Done when: the baseline error is known per lap and per 20-lap stint, and the residual plots show where it fails.

### 3. XGBoost / Random Forest — not started
To check: the predicted time must increase with tyre age (partial dependence on age); otherwise the model learned something else (team speed,
for example). XGBoost can enforce this with a monotonic constraint on age — an option to try and to compare.
To compare: the error on the degradation slope matters more than the mean error per lap; use the same validation races as the baseline and the
stint-sum error.
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
