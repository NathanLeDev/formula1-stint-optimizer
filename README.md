# formula1-stint-optimizer

**Goal** — turn OpenF1 race data (2023-2026) into the three inputs a stint optimizer needs, one row
per circuit: tyre degradation, pit stop loss, and observed stint lengths.

**Key result** — degradation is a circuit effect, one slope per circuit from 0.024 to 0.121 s/lap,
exported with its between-race dispersion. A compound gets a pace offset but **no slope of its
own**: a slope per compound predicts held-out races worse than a single one, so the model cannot
choose a compound and that decision stays outside the simulator (section 11). Baseline to beat:
0.703 s of RMSE per lap on a race the fit has never seen.

**Running it** — open `app/data-viz.ipynb` and run the cells in order. The first run downloads from
the OpenF1 API into `app/data/cache` (a few minutes); later runs read that cache. The reference
table is written to `app/data/reference_circuits.csv`.
