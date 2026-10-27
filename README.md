# formula1-stint-optimizer

**Goal** — turn OpenF1 race data (2023-2026) into the three inputs a stint optimizer needs, one row
per circuit: tyre degradation, pit stop loss, and observed stint lengths.

**Key result** — degradation is a circuit effect, one slope per circuit from 0.024 to 0.121 s/lap,
exported with its between-race dispersion. A compound gets a pace offset but **no slope of its
own**: a slope per compound predicts held-out races worse than a single one, so the model cannot
choose a compound and that decision stays outside the simulator (section 11). Baseline to beat:
0.703 s of RMSE per lap on a race the fit has never seen.

**Layout** — `app/f1data.py` loads and cleans the data: the cached OpenF1 client, the
neutralised laps, and `build_base()`, the one clean-lap table every notebook analyses. It exists
because `data-viz.ipynb` assembled that table in three separate cells, which is one table that can
diverge from itself. It also carries the two columns phase 1 asked for and phase 1 did not have:
track temperature, and the gap to the car ahead from the `intervals` endpoint.

```python
import f1data

raw = f1data.load_raw()          # cached after the first run
base = f1data.build_base(raw)    # one clean race lap per row
base, per_race = f1data.add_target(base)   # `gap`: that lap against the median lap of its race
```

**Phase 2** (`app/02-baseline.ipynb`) fits the baseline every later model has to beat. Its target is
`gap`, in seconds, so that it adds up with the pit stop loss and the degradation slope of phase 1.
The reference is the median of the race over all its drivers, computed once on the whole table: it
deliberately keeps the fuel, the driver level and the tyre, and removes the level of the race
itself. The limit that comes with it: the median of a race is not known before that race, so these
numbers rank models and strategies, they do not forecast an absolute lap time.

**Running it** — open `app/data-viz.ipynb` and run the cells in order. The first run downloads from
the OpenF1 API into `app/data/cache` (a few minutes); later runs read that cache. The reference
table is written to `app/data/reference_circuits.csv`.
