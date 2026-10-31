# Limits and open questions

## What the project can claim today
It predicts how lap time decays with tyre age on a given circuit, and supports decisions on **when and how many times to stop**.
It **cannot choose a compound**: the pace offsets between compounds are not in the expected order and the slopes per compound
do not predict held-out races better than a single slope.

## The compound confound (blocking for compound choice)
- Hypothesis (untested): which compound is on the car is tied to when it runs, so a compound effect and a race-phase effect
  cannot be separated by a model whose only time variable is a straight line in lap number. Evidence: at Catalunya and Baku the
  soft starts slower than the hard at age 1, probably because first laps of a soft stint are often the first laps of the race
  (bunched field, traffic).
- Other plausible explanations to keep in mind: pace is a choice (a driver planning 35 laps on a hard manages the tyre and
  drives slower than on a 12-lap soft stint); traffic differs by phase; a straight line misses non-linear track evolution;
  SC restarts leave residual effects.
- Tests not done: (a) a free offset per lap number inside each race (lap fixed effect), then re-read the compound offsets;
  (b) a model-free comparison at the same lap and similar tyre age across drivers on different compounds; (c) add track/air
  temperature and laps since last neutralisation (temperature is already in `build_base`).

## Validation weaknesses
- The held-out RMSE (0.703) gives each driver of the tested race a free pace level estimated on that race: comparative, not a forecast.
  Needed: the same with a driver/team level estimated on past races only.
- Within-race standard errors (0.005 s/lap) understate uncertainty (autocorrelated laps); the between-race dispersion is the honest one.
- The leave-one-race-out trains with 2026 races of the same circuit; only the evaluation is restricted to 2023-2025 in the 4b check.
- Win counts (34/76, 28/62) are coin flips; report an average RMSE difference with a resampling interval.

## Data and measurement limits
- A median stint length describes when a compound was used (strategy, safety cars, survivors), not its life. Monza soft: median 3 laps
  over 17 stints (7 are lap-3 stops on one 2026 afternoon, 5 are end-of-race runs).
- Pit loss excludes stops under safety car / red flag, so at circuits with many neutralisations the sample is thin (Baku: 38 stops
  retained for 154 stints). Part of the long tail may be measurement (yellow flags, traffic behind a slow car).
- Thin circuits: Madring has no training race, Silverstone one; 2026 has one race per circuit (slope 2026 is a drift signal).
- Races with no weather rows may count as dry; check how many.
- Pit loss and stint lengths average four seasons while the slope uses 2023-2025; 2026 pit loss is about 2 s higher.
- The straight line cannot represent an end-of-life cliff; 40-lap stint costs are extrapolations. Check whether the gap curve bends beyond ~25 laps.
- The fuel limit drops to 70 kg in 2026, so the fuel coefficient and slopes do not transfer to 2026.

## Project-value concern
With one linear slope per circuit and no compound information, the optimal strategy is nearly closed-form (equal stints, number of stops from the
stop-versus-wear trade-off). A learning model and a simulator must earn their place through what the formula cannot do: a non-linear wear curve
(cliff), a lower pit loss and different timing under safety car / undercut, traffic, and uncertainty (draw slope and pit loss from distributions,
possibly conformal prediction). Variables that depend on other cars (traffic, dirty air) can explain residuals but cannot feed the simulator.
Possible extra signal: Pirelli tyre-compound numbers (C1-C5) instead of relative soft/medium/hard labels, and a pre-race pace level from qualifying
or practice.

## Open decisions
- Should the optimizer only be fed stints long enough to be real tyre runs?
- Should the exported pit loss follow the 2023-2025 window like the slope?
- Hierarchical model that borrows strength across circuits for thin circuits?
- Which uncertainty method for the simulator inputs?
