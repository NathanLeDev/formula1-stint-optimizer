"""Phase 3: a gradient-boosted tree model of `gap`, scored with the tools of `baseline.py`.

What this module does:

1. `design()`            the feature matrix. `circuit` and `compound` are categorical, with the
                         categories fixed by the caller so a circuit never seen in training
                         (Madring) becomes a missing value instead of a new code.
2. `fit_xgb()`           one XGBoost regressor, returned as a model dict that `baseline.predict()`
                         understands, so `baseline.evaluate()`, `stint_table()` and
                         `plot_residuals()` score it exactly as they score the reference.
3. `cv_predict()`        out-of-fold predictions inside the training seasons, folds made of whole
                         races. This is what chooses the variables and the hyperparameters, so
                         that 2025 is read once and not used to choose.
4. `partial_dependence()` the mean prediction when tyre age alone is moved: the check that the
                         model learned wear and not something else.
5. `stint_slopes()` / `race_age_slopes()`  the two errors on the degradation slope.
6. `boot_diff()`         an interval on a difference of RMSE, by resampling whole races.

`traffic` is never a feature: it depends on the other cars and the simulator cannot know it
(`docs/02-decisions-log.md`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import baseline

NUMERIC = ["lap_number", "age", "race_frac", "driver_level", "track_temp"]
CATEGORICAL = ["circuit", "compound"]

# The ladder of variables, each rung adding one thing to the previous one. `base` carries the
# same information as the reference spec `circuit`: fuel (lap number), tyre age, circuit.
FEATURE_SETS = {
    "base": ["lap_number", "age", "circuit"],
    "+ race_frac": ["lap_number", "age", "circuit", "race_frac"],
    "+ driver_level": ["lap_number", "age", "circuit", "race_frac", "driver_level"],
    "+ compound": ["lap_number", "age", "circuit", "race_frac", "driver_level", "compound"],
    "+ track_temp": ["lap_number", "age", "circuit", "race_frac", "driver_level", "compound",
                     "track_temp"],
}

# Fixed, not tuned: the learning rate trades against the number of trees, which is tuned.
# `subsample` and `min_child_weight` are assumed values, not measured ones.
PARAMS = {"learning_rate": 0.05, "subsample": 0.8, "min_child_weight": 50,
          "tree_method": "hist", "random_state": 0, "n_jobs": 4}

SLOPE_MIN_LAPS = 8      # assumed: laps a stint needs before a slope fitted on it means anything
RACE_KEY = ["session_key", "driver_number"]


# 1. Features --------------------------------------------------------------------

def categories(train):
    """The levels of each categorical column, read on the training sample only."""
    return {c: sorted(train[c].dropna().unique()) for c in CATEGORICAL}


def design(x, features, cats):
    """The feature matrix of `x`. A level absent from `cats` becomes a missing value."""
    out = pd.DataFrame(index=x.index)
    for f in features:
        if f in CATEGORICAL:
            out[f] = pd.Categorical(x[f], categories=cats[f])
        else:
            out[f] = x[f].astype(float)
    return out


# 2. The model ---------------------------------------------------------------------

def _regressor(features, monotone, **params):
    from xgboost import XGBRegressor
    kw = {**PARAMS, **params}
    if monotone:
        # +1 on age only: with every other variable held fixed, an older tyre may not be
        # predicted faster. Nothing is imposed on the other variables.
        kw["monotone_constraints"] = {f: int(f == "age") for f in features}
    return XGBRegressor(enable_categorical=True, **kw)


def fit_xgb(train, features, monotone=False, name=None, **params):
    """Fit on `train`, return a model dict scored by `baseline.evaluate()` like any other.

    `params` must give `max_depth` and `n_estimators`; the rest comes from PARAMS.
    """
    cats = categories(train)
    reg = _regressor(features, monotone, **params)
    reg.fit(design(train, features, cats), train["gap"].to_numpy(float))
    return {"spec": name or "xgb", "by": {}, "features": list(features), "cats": cats,
            "monotone": monotone, "reg": reg,
            "predict": lambda x: reg.predict(design(x, features, cats)).astype(float)}


def as_model(pred, name):
    """Wrap a Series of predictions (indexed like the table) as a model dict.

    For out-of-fold predictions, where no single fitted model exists.
    """
    return {"spec": name, "by": {}, "predict": lambda x: pred.loc[x.index].to_numpy(float)}


# 3. Choosing inside the training seasons ---------------------------------------------

def race_folds(x, k=5, seed=0):
    """`k` lists of session keys covering the races of `x`, drawn at random. Whole races."""
    keys = np.sort(x["session_key"].unique())
    np.random.default_rng(seed).shuffle(keys)
    return [list(part) for part in np.array_split(keys, k)]


def cv_predict(train, features, monotone=False, n_trees=(400,), folds=None, **params):
    """Out-of-fold predictions on `train`: each race is predicted by a model that never saw it.

    Returns {n: Series} for each value of `n_trees`. One model per fold is fitted with the
    largest value and read at each smaller one, since boosting adds trees one after another.
    """
    folds = folds or race_folds(train)
    out = {n: pd.Series(np.nan, index=train.index) for n in n_trees}
    for held in folds:
        te = train["session_key"].isin(held)
        m = fit_xgb(train[~te], features, monotone, n_estimators=max(n_trees), **params)
        X = design(train[te], features, m["cats"])
        for n in n_trees:
            out[n][te] = m["reg"].predict(X, iteration_range=(0, n))
    return out


def cv_reference(train, spec="circuit", folds=None):
    """The reference regression predicted out of fold on the same folds, for a like-for-like."""
    folds = folds or race_folds(train)
    out = pd.Series(np.nan, index=train.index)
    for held in folds:
        te = train["session_key"].isin(held)
        out[te] = baseline.predict(baseline.fit(train[~te], spec), train[te])
    return out


# 4. Does the prediction rise with tyre age? -----------------------------------------------

def partial_dependence(model, x, ages, by=None):
    """Mean prediction over the laps of `x` when every lap is given the tyre age `a`.

    Everything else on the lap is left as it is, the lap number included, so the curve reads the
    effect the model attaches to age itself and not to the fuel that moves with it. The price:
    some combinations do not exist (age 40 on lap 5), and the curve is only as good as the model
    is there. One column per level of `by` if given, else a single column `all`.
    """
    rows = {}
    for a in ages:
        p = pd.Series(baseline.predict(model, x.assign(age=float(a))), index=x.index)
        rows[a] = p.groupby(x[by]).mean() if by else pd.Series({"all": p.mean()})
    return pd.DataFrame(rows).T.rename_axis("age")


# 5. The error on the degradation slope --------------------------------------------------------

def _slope(t, y):
    t = t - t.mean()
    return float((t * (y - y.mean())).sum() / (t ** 2).sum())


def stint_slopes(model, x, min_laps=SLOPE_MIN_LAPS):
    """Definition A. One row per hole-free stint of at least `min_laps` clean laps:
    the slope of the actual gap on lap number, and the slope of the predicted gap.

    Inside a stint the tyre age and the lap number advance together, so this slope is the net
    of fuel and wear, not wear alone. It is what the simulator adds up along a stint.
    """
    st = baseline.stints(x)
    ok = st[st["hole_free"] & (st["laps"] >= min_laps)][baseline.STINT_KEY + ["laps"]]
    d = x[baseline.STINT_KEY + ["lap_number", "gap"]].assign(pred=baseline.predict(model, x))
    d = d.merge(ok, on=baseline.STINT_KEY)
    rows = []
    for key, g in d.groupby(baseline.STINT_KEY):
        t = g["lap_number"].to_numpy(float)
        rows.append((*key, len(g), _slope(t, g["gap"].to_numpy()), _slope(t, g["pred"].to_numpy())))
    out = pd.DataFrame(rows, columns=baseline.STINT_KEY + ["laps", "actual", "predicted"])
    out["error"] = out["predicted"] - out["actual"]
    return out


def _age_coef(x, y, per_driver):
    cols = pd.DataFrame({"lap": x["lap_number"].to_numpy(float), "age": x["age"].to_numpy(float),
                         "y": np.asarray(y, dtype=float)})
    if per_driver:      # a free level per driver = every column centred inside each driver
        cols = cols - cols.groupby(x["driver_number"].to_numpy()).transform("mean")
    X = np.column_stack([np.ones(len(cols)), cols["lap"], cols["age"]])
    return float(np.linalg.lstsq(X, cols["y"].to_numpy(), rcond=None)[0][2])


def race_age_slopes(model, x, per_driver=False):
    """Definition B. One row per race: the tyre-age coefficient of `gap = c + a lap + b age`
    fitted on the actual gaps of the race, and the same fit on the predicted gaps.

    Drivers pit on different laps, which is what separates age from lap number, so this one
    isolates wear from fuel. Fitting the same regression on the predictions reads the slope a
    model implies on the laps actually driven: for the linear reference it returns its own
    coefficient exactly, and for a tree model it needs no made-up tyre ages.

    `per_driver=False` is the fit of `02-baseline.ipynb` section 4. It has no driver term, so
    the coefficient also carries who runs the old tyres: if slow cars stop later, age looks
    costlier than it is. `per_driver=True` gives each driver a free level, as the phase 1 fit
    did, and reads the slope inside a driver's race only.
    """
    pred = pd.Series(baseline.predict(model, x), index=x.index)
    rows = [(k, g["circuit"].iloc[0], _age_coef(g, g["gap"], per_driver),
             _age_coef(g, pred.loc[g.index], per_driver))
            for k, g in x.groupby("session_key")]
    out = pd.DataFrame(rows, columns=["session_key", "circuit", "actual", "predicted"])
    out["error"] = out["predicted"] - out["actual"]
    return out.set_index("session_key")


# 6. An interval on a difference ---------------------------------------------------------------

def within(model, x):
    """Residuals with the mean of each (race, driver) removed, as in `rmse within driver`."""
    r = baseline.residuals(model, x)
    return r - r.groupby([x[k] for k in RACE_KEY]).transform("mean")


def boot_diff(races, err_a, err_b, n=2000, seed=0):
    """RMSE of `err_b` minus RMSE of `err_a`, with a 95 % interval from resampling whole races.

    `races` gives the race of each error. Races are resampled, not laps: laps of one race are
    not independent, and an interval built on laps would be far too narrow.
    Returns (difference, low, high). Negative means `b` has the lower error.
    """
    t = pd.DataFrame({"s": np.asarray(races), "a": np.square(np.asarray(err_a, dtype=float)),
                      "b": np.square(np.asarray(err_b, dtype=float))})
    g = t.groupby("s").agg(a=("a", "sum"), b=("b", "sum"), n=("a", "size")).to_numpy()
    diff = lambda m: np.sqrt(m[:, 1].sum() / m[:, 2].sum()) - np.sqrt(m[:, 0].sum() / m[:, 2].sum())
    rng = np.random.default_rng(seed)
    draws = [diff(g[rng.integers(0, len(g), len(g))]) for _ in range(n)]
    return float(diff(g)), float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))
