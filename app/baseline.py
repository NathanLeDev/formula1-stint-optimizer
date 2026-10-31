"""Phase 2, step 2: the split, the variables and the reference regression.

What this module does, in the order of the roadmap:

1. `split()`           2023-2024 to fit, 2025 to validate, 2026 apart. Always by race.
2. `add_features()`    `race_frac` and `driver_level`, both computed without looking ahead.
3. `fit()` / `predict()` the reference: a plain least-squares regression of `gap` on the
                       fuel (lap number) and the tyre age, per circuit, optionally per compound.
4. `evaluate()`        two errors, always together (see below).
5. `loro()`            the Phase 1 protocol replayed on `gap`, to cross-check the 0.703 s.
6. `plot_residuals()`  where the reference fails.

Two errors, because Phase 1's 0.703 s is only one of them. Its residual has the mean of each
driver in the held-out race removed before the RMSE is taken, so it measures the error inside a
driver's race, with his level and the level of the race given for free.

- `rmse`               raw error on `gap`: nothing about the held-out race is known.
- `rmse within driver` the same residual after removing the mean of each (race, driver). This is
                       the one that compares with 0.703, and the one that matters for ranking
                       strategies of one driver in one race, where his level is a constant.

`driver_level` is the mean gap of the driver over his previous LEVEL_WINDOW races, shrunk towards 0
by LEVEL_SHRINK pseudo-races. It only uses races that precede the lap in date, so it is available
before the start. Driver numbers are assumed to stay with the same driver.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRAIN_YEARS = (2023, 2024)
VALID_YEAR = 2025
APART_YEAR = 2026          # new regulations: reported on its own, never fitted on

MIN_TRAIN_RACES = 2        # races a circuit needs before it gets its own coefficients
MIN_CELL_LAPS = 150        # laps a (circuit, compound) cell needs before it gets its own
LEVEL_WINDOW = 5           # previous races used for the driver level
LEVEL_SHRINK = 3           # pseudo-races at 0 that pull a short history towards the field

COMPOUND_COLS = ["MEDIUM", "HARD"]     # offsets against SOFT
SPECS = ["zero", "circuit", "circuit + compound", "circuit x compound", "circuit + driver level"]


def rms(s):
    return float(np.sqrt(np.mean(np.square(np.asarray(s, dtype=float)))))


# 1. Split ---------------------------------------------------------------------

def split(base):
    """(train, valid, apart): 2023-2024, 2025, 2026. Whole races, never random laps."""
    y = base["year"]
    return base[y.isin(TRAIN_YEARS)], base[y == VALID_YEAR], base[y == APART_YEAR]


# 2. Variables -----------------------------------------------------------------

def add_features(base, raw):
    """Adds `race_frac` (lap / distance of the race) and `driver_level`.

    `driver_level` for a driver in a race is the sum of his mean gap over his previous races
    (at most LEVEL_WINDOW, date order) divided by (number of those races + LEVEL_SHRINK).
    A driver with no history gets 0.
    """
    out = base.reset_index(drop=True).copy()
    distance = raw.laps.groupby("session_key")["lap_number"].max()
    out["race_frac"] = out["lap_number"] / out["session_key"].map(distance)

    date = raw.races.set_index("session_key")["date_start"]
    dm = (out.groupby(["session_key", "driver_number"])["gap"].mean().rename("gap_mean")
          .reset_index())
    dm["date"] = dm["session_key"].map(date)
    dm = dm.sort_values(["driver_number", "date"])
    g = dm.groupby("driver_number")["gap_mean"]
    past_sum = g.transform(lambda s: s.shift().rolling(LEVEL_WINDOW, min_periods=1).sum())
    past_n = g.transform(lambda s: s.shift().rolling(LEVEL_WINDOW, min_periods=1).count())
    dm["driver_level"] = past_sum.fillna(0.0) / (past_n.fillna(0.0) + LEVEL_SHRINK)
    return out.merge(dm[["session_key", "driver_number", "driver_level"]],
                     on=["session_key", "driver_number"], how="left")


# 3. The reference regression ---------------------------------------------------

def _X(x, offsets):
    cols = [np.ones(len(x)), x["lap_number"].to_numpy(float), x["age"].to_numpy(float)]
    if offsets:
        cols += [(x["compound"] == c).to_numpy(float) for c in COMPOUND_COLS]
    return np.column_stack(cols)


def _lstsq(X, y):
    # minimum-norm solution: a compound absent from a circuit (an all-zero column) gets 0
    return np.linalg.lstsq(X, np.asarray(y, dtype=float), rcond=None)[0]


def _parts(spec):
    """(coefficient layout, offsets?, driver level?)"""
    layout = "circuit x compound" if spec == "circuit x compound" else "circuit"
    return layout, spec == "circuit + compound", spec == "circuit + driver level"


def fit(train, spec):
    """Gap = const + a * lap_number + b * age (+ compound offsets), one fit per circuit.

    A circuit seen in fewer than MIN_TRAIN_RACES training races has no coefficients of its own
    and falls back on the fit over all circuits.
    """
    assert spec in SPECS, spec
    model = {"spec": spec, "by": {}}
    if spec == "zero":
        return model
    layout, offsets, level = _parts(spec)
    model["global"] = _lstsq(_X(train, offsets), train["gap"])
    n_races = train.groupby("circuit")["session_key"].nunique()
    for c, x in train.groupby("circuit"):
        if n_races[c] < MIN_TRAIN_RACES:
            continue
        if layout == "circuit x compound":
            cells = {comp: _lstsq(_X(xc, False), xc["gap"])
                     for comp, xc in x.groupby("compound") if len(xc) >= MIN_CELL_LAPS}
            model["by"][c] = (_lstsq(_X(x, False), x["gap"]), cells)
        else:
            model["by"][c] = _lstsq(_X(x, offsets), x["gap"])
    if level:
        resid = train["gap"].to_numpy() - predict(model, train.assign(driver_level=0.0))
        lv = train["driver_level"].to_numpy()
        model["level_beta"] = float((resid * lv).sum() / (lv ** 2).sum())
    return model


def predict(model, x):
    spec = model["spec"]
    if spec == "zero":
        return np.zeros(len(x))
    layout, offsets, _ = _parts(spec)
    pred = _X(x, offsets) @ model["global"]
    for c, idx in x.groupby("circuit").indices.items():
        if c not in model["by"]:
            continue
        sub = x.iloc[idx]
        if layout == "circuit x compound":
            circuit_coef, cells = model["by"][c]
            p = _X(sub, False) @ circuit_coef
            for comp, coef in cells.items():
                m = (sub["compound"] == comp).to_numpy()
                p[m] = _X(sub[m], False) @ coef
            pred[idx] = p
        else:
            pred[idx] = _X(sub, offsets) @ model["by"][c]
    if "level_beta" in model:
        pred = pred + model["level_beta"] * x["driver_level"].to_numpy()
    return pred


def own_coefficients(model, x):
    """Share of the laps of `x` that sit on a circuit with coefficients of its own."""
    if model["spec"] == "zero":
        return np.nan
    return float(x["circuit"].isin(model["by"]).mean())


# 4. The error -------------------------------------------------------------------

def residuals(model, x):
    return pd.Series(x["gap"].to_numpy() - predict(model, x), index=x.index, name="res")


def evaluate(model, x):
    r = residuals(model, x)
    within = r - r.groupby([x["session_key"], x["driver_number"]]).transform("mean")
    return {"rmse": rms(r), "rmse within driver": rms(within), "bias": float(r.mean()),
            "own coef": own_coefficients(model, x)}


def compare(train, valid, apart, specs=SPECS):
    """One row per model and per sample: the error of the reference where it is fitted,
    on the 2025 validation, and on 2026."""
    rows, models = [], {}
    for spec in specs:
        m = fit(train, spec)
        models[spec] = m
        for name, x in [("train 2023-24", train), ("valid 2025", valid), ("apart 2026", apart)]:
            rows.append({"model": spec, "sample": name, **evaluate(m, x)})
    return pd.DataFrame(rows), models


# 5. Phase 1 protocol, replayed on `gap` -----------------------------------------------

def loro(base, tyre=True):
    """Leave one race out, fit on the other races of the same circuit, error after removing the
    mean of each driver in the held-out race: the protocol of `data-viz.ipynb` section 11, on
    `gap`. Phase 1 reports 0.771 s without a tyre term and 0.703 s with one slope per circuit.
    Differences: the fit here has no driver level in training, and no minimum laps per compound.
    """
    res = []
    for _, g in base.groupby("circuit"):
        if g["session_key"].nunique() < 2:
            continue
        for s in g["session_key"].unique():
            tr, te = g[g["session_key"] != s], g[g["session_key"] == s]
            def X(x):
                cols = [np.ones(len(x)), x["lap_number"].to_numpy(float)]
                cols += [x["age"].to_numpy(float)] if tyre else []
                cols += [(x["compound"] == c).to_numpy(float) for c in COMPOUND_COLS]
                return np.column_stack(cols)
            r = pd.Series(te["gap"].to_numpy() - X(te) @ _lstsq(X(tr), tr["gap"]), index=te.index)
            res.append(r - r.groupby(te["driver_number"]).transform("mean"))
    return rms(pd.concat(res))


# 6. Where the reference fails ------------------------------------------------------------

def _binned(x, r, by, bins, min_n=200):
    t = pd.DataFrame({"r": r, "b": pd.cut(by, bins)})
    g = t.groupby("b", observed=True)["r"].agg(["mean", "size"])
    g = g[g["size"] >= min_n]
    return [i.mid for i in g.index], g["mean"].to_numpy()


def plot_residuals(model, train, valid, apart):
    import matplotlib.pyplot as plt
    rv, ra = residuals(model, valid), residuals(model, apart)
    fig, ax = plt.subplots(2, 3, figsize=(19, 10.5))
    colour = {"SOFT": "#c0392b", "MEDIUM": "#d4a017", "HARD": "#555555"}

    a = ax[0, 0]
    for comp in ["SOFT", "MEDIUM", "HARD"]:
        m = valid["compound"] == comp
        xs, ys = _binned(valid[m], rv[m], valid.loc[m, "age"], np.arange(0, 46, 5))
        a.plot(xs, ys, marker="o", color=colour[comp], label=comp.lower())
    a.axhline(0, color="#9a9a9a", ls=":")
    a.set(title="Residual by tyre age and compound (2025)", xlabel="tyre age (laps)",
          ylabel="mean residual (s)")
    a.legend()

    a = ax[0, 1]
    for name, x, r, c in [("2025", valid, rv, "#2c7fb8"), ("2026", apart, ra, "#c0392b")]:
        xs, ys = _binned(x, r, x["race_frac"], np.linspace(0, 1, 11))
        a.plot(xs, ys, marker="o", color=c, label=name)
    a.axhline(0, color="#9a9a9a", ls=":")
    a.set(title="Residual by fraction of the race", xlabel="fraction of the race distance",
          ylabel="mean residual (s)")
    a.legend()

    a = ax[0, 2]
    t = valid["track_temp"]
    xs, ys = _binned(valid, rv, t, np.quantile(t.dropna(), np.linspace(0, 1, 11)))
    a.plot(xs, ys, marker="o", color="#2c7fb8")
    a.axhline(0, color="#9a9a9a", ls=":")
    a.set(title="Residual by track temperature (2025)", xlabel="track temperature (C)",
          ylabel="mean residual (s)")

    a = ax[1, 0]
    per = pd.DataFrame({"r": rv, "c": valid["circuit"], "s": valid["session_key"]})
    bc = per.groupby("c").agg(mean=("r", "mean"), races=("s", "nunique")).sort_values("mean")
    a.barh(bc.index, bc["mean"], color=np.where(bc["mean"] > 0, "#c0392b", "#2c7fb8"))
    a.axvline(0, color="#9a9a9a", lw=0.8)
    a.tick_params(axis="y", labelsize=8)
    a.set(title="Mean residual per circuit (2025)", xlabel="mean residual (s)")

    a = ax[1, 1]
    allx = pd.concat([train, valid, apart])
    race = (pd.DataFrame({"r": residuals(model, allx), "y": allx["year"], "s": allx["session_key"]})
            .groupby("s").agg(r=("r", "mean"), y=("y", "first")))
    for i, (y, g) in enumerate(race.groupby("y")):
        a.scatter(np.full(len(g), i) + np.linspace(-0.2, 0.2, len(g)), g["r"], s=22, alpha=0.7)
        a.plot([i - 0.3, i + 0.3], [g["r"].mean()] * 2, color="black", lw=2)
    a.set_xticks(range(race["y"].nunique()), sorted(race["y"].unique()))
    a.axhline(0, color="#9a9a9a", ls=":")
    a.set(title="Mean residual per race, by season (black = season mean)",
          ylabel="mean residual of the race (s)")

    a = ax[1, 2]
    d = pd.DataFrame({"r": rv, "lv": valid["driver_level"], "s": valid["session_key"],
                      "d": valid["driver_number"]}).groupby(["s", "d"]).mean()
    a.scatter(d["lv"], d["r"], s=10, alpha=0.5, color="#2c7fb8")
    corr = np.corrcoef(d["lv"], d["r"])[0, 1]
    a.axhline(0, color="#9a9a9a", ls=":")
    a.set(title=f"Driver-race mean residual vs driver_level (2025, r = {corr:+.2f})",
          xlabel="driver_level (s, past races only)", ylabel="mean residual of the driver (s)")
    fig.suptitle(f"Where the reference fails: {model['spec']}, fitted on 2023-2024", y=0.995)
    fig.tight_layout()
    return fig
