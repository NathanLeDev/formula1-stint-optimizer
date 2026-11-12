"""Tests of `trees.py` and of the hook it uses in `baseline.predict()`, on small synthetic frames."""
import numpy as np
import pandas as pd
import pytest

import baseline
import trees


def make(n_races=6, n_drivers=4, n_laps=30, seed=0):
    """Races of `n_drivers` cars, two stints each, pitting on different laps.

    gap = 1 - 0.05 x lap + 0.08 x age + a level per driver + a little noise.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_races):
        for d in range(n_drivers):
            stop = 10 + 3 * d
            for lap in range(2, n_laps + 1):
                first = lap <= stop
                rows.append({"session_key": s, "driver_number": d, "lap_number": lap,
                             "stint_number": 1 if first else 2,
                             "age": lap if first else lap - stop,
                             "circuit": "A" if s % 2 == 0 else "B",
                             "compound": "HARD" if first else "MEDIUM",
                             "race_frac": lap / n_laps, "driver_level": 0.3 * d,
                             "track_temp": 30.0})
    x = pd.DataFrame(rows)
    x["gap"] = (1 - 0.05 * x["lap_number"] + 0.08 * x["age"] + 0.3 * x["driver_number"]
                + rng.normal(0, 0.01, len(x)))
    return x


def linear(a, b):
    """A model dict predicting a x lap + b x age."""
    return {"spec": "linear", "by": {},
            "predict": lambda x: a * x["lap_number"].to_numpy(float) + b * x["age"].to_numpy(float)}


def test_predict_hook_is_scored_like_any_model():
    x = make()
    perfect = trees.as_model(x["gap"], "perfect")
    e = baseline.evaluate(perfect, x)
    assert e["rmse"] == 0 and e["stint rmse"] == 0
    assert np.isnan(e["own coef"])
    # the reference specs do not go through the hook
    assert np.allclose(baseline.predict(baseline.fit(x, "zero"), x), 0)


def test_design_unseen_category_is_missing():
    x = make()
    cats = trees.categories(x[x["circuit"] == "A"])
    X = trees.design(x, ["age", "circuit"], cats)
    assert X.loc[x["circuit"] == "B", "circuit"].isna().all()
    assert X.loc[x["circuit"] == "A", "circuit"].notna().all()


def test_race_folds_partition_whole_races():
    x = make(n_races=11)
    folds = trees.race_folds(x, k=5)
    flat = [k for f in folds for k in f]
    assert sorted(flat) == sorted(x["session_key"].unique())
    assert len(flat) == len(set(flat))


def test_cv_predict_never_trains_on_the_predicted_race(monkeypatch):
    x = make()
    seen = []
    real = trees.fit_xgb

    def spy(train, *a, **k):
        seen.append(set(train["session_key"]))
        return real(train, *a, **k)

    monkeypatch.setattr(trees, "fit_xgb", spy)
    folds = trees.race_folds(x, k=3)
    out = trees.cv_predict(x, ["lap_number", "age"], n_trees=(5, 10), folds=folds, max_depth=2)
    assert all(not (set(held) & trained) for held, trained in zip(folds, seen))
    assert all(p.notna().all() for p in out.values())
    assert not np.allclose(out[5], out[10])


def test_monotone_constraint_holds_against_the_data():
    x = make()
    x["gap"] = -0.1 * x["age"]                       # data in which an older tyre is faster
    free = trees.fit_xgb(x, ["lap_number", "age"], monotone=False, max_depth=2, n_estimators=50,
                         min_child_weight=1)
    mono = trees.fit_xgb(x, ["lap_number", "age"], monotone=True, max_depth=2, n_estimators=50,
                         min_child_weight=1)
    ages = np.arange(1, 25)
    assert trees.partial_dependence(free, x, ages)["all"].diff().min() < 0
    assert trees.partial_dependence(mono, x, ages)["all"].diff().min() >= -1e-9


def test_partial_dependence_reads_the_age_term_only():
    x = make()
    pdp = trees.partial_dependence(linear(-0.05, 0.08), x, [1, 11], by="circuit")
    assert np.allclose(pdp.loc[11] - pdp.loc[1], 0.8)
    assert list(pdp.columns) == ["A", "B"]


def test_stint_slopes_values_and_hole():
    x = make(n_races=1, n_drivers=1)
    x["gap"] = 0.1 * x["lap_number"]
    x = x[x["lap_number"] != 20]                      # a hole inside the second stint
    s = trees.stint_slopes(linear(0.04, 0.0), x, min_laps=5)
    assert len(s) == 1 and s["stint_number"].iloc[0] == 1
    assert s["actual"].iloc[0] == pytest.approx(0.1)
    assert s["error"].iloc[0] == pytest.approx(-0.06)
    assert trees.stint_slopes(linear(0.04, 0.0), x, min_laps=10).empty


def test_race_age_slopes_recover_the_coefficient():
    x = make()
    for per_driver in (False, True):
        s = trees.race_age_slopes(linear(-0.05, 0.05), x, per_driver)
        assert np.allclose(s["predicted"], 0.05)             # a linear model returns its own slope
        assert np.allclose(s["error"], 0.05 - s["actual"])
    # the driver level is tied to the stop lap here, so only the per-driver fit finds 0.08
    assert np.allclose(trees.race_age_slopes(linear(0, 0), x, True)["actual"], 0.08, atol=0.002)


def test_boot_diff():
    races = np.repeat(np.arange(10), 20)
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 200)
    assert trees.boot_diff(races, a, a) == (0.0, 0.0, 0.0)
    d, lo, hi = trees.boot_diff(races, a, 2 * a)
    assert d == pytest.approx(baseline.rms(a)) and lo > 0
    d2, lo2, hi2 = trees.boot_diff(races, 2 * a, a)
    assert d2 == pytest.approx(-d) and hi2 < 0
