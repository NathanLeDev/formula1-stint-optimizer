"""Tests of `simparams.py` and `f1data.pit_entries()`, on a small synthetic `Raw`."""
import numpy as np
import pandas as pd
import pytest

import f1data
import simparams


def make_raw(sc_lap=None):
    """Two dry races (10 = has `pit` rows, 20 = none), one driver, 10 laps of 90 s.

    The car pits on lap 5: in-lap 100 s, out-lap 105 s, so the loss is 100 + 105 - 2 x 90 = 25 s.
    `sc_lap` puts a safety car deployment in race 10 on that lap.
    """
    laps = []
    for s in (10, 20):
        for lap in range(1, 11):
            t = {5: 100.0, 6: 105.0}.get(lap, 90.0)
            laps.append({"session_key": s, "driver_number": 1, "lap_number": lap,
                         "lap_duration": t, "is_pit_out_lap": lap == 6,
                         "date_start": pd.Timestamp("2024-03-01", tz="UTC") + pd.Timedelta(minutes=lap)})
    stints = pd.DataFrame([{"session_key": s, "driver_number": 1, "stint_number": n,
                            "lap_start": a, "lap_end": b, "compound": "MEDIUM", "tyre_age_at_start": 0}
                           for s in (10, 20) for n, a, b in [(1, 1, 5), (2, 6, 10)]])
    rc = [{"session_key": 10, "date": "2024-03-01T00:00:00+00:00", "lap_number": 1.0,
           "message": "GREEN LIGHT - PIT EXIT OPEN", "flag": "GREEN"}]
    if sc_lap is not None:
        rc += [{"session_key": 10, "date": "2024-03-01T00:30:00+00:00", "lap_number": float(sc_lap),
                "message": "SAFETY CAR DEPLOYED", "flag": None},
               {"session_key": 10, "date": "2024-03-01T00:40:00+00:00", "lap_number": float(sc_lap),
                "message": "SAFETY CAR IN THIS LAP", "flag": None}]
    races = pd.DataFrame({"session_key": [10, 20], "circuit_short_name": ["A", "B"],
                          "date_start": pd.to_datetime(["2024-03-01", "2024-03-08"], utc=True)})
    return f1data.Raw(sessions=races, races=races, laps=pd.DataFrame(laps), stints=stints,
                      pit=pd.DataFrame({"session_key": [10], "driver_number": [1], "lap_number": [5]}),
                      weather=pd.DataFrame({"session_key": [10, 20], "rainfall": [0, 0]}),
                      race_control=pd.DataFrame(rc), session_result=pd.DataFrame())


def test_pit_entries_sources():
    raw = make_raw()
    e = f1data.pit_entries(raw.pit, raw.stints)
    assert sorted(map(tuple, e[["session_key", "lap_number", "source"]].values)) == \
        [(10, 5, "pit"), (20, 5, "stints")]
    assert f1data.entry_laps(raw.pit, raw.stints) == {(10, 1, 5), (20, 1, 5)}


def test_stop_losses_values_and_sources():
    s = simparams.stop_losses(make_raw()).set_index("session_key")
    assert s.loc[10, "loss"] == pytest.approx(25.0) and s.loc[20, "loss"] == pytest.approx(25.0)
    assert s.loc[10, "ref"] == 90.0 and s.loc[10, "ref_laps"] == 5     # laps 2-4 and 7-8 are clean
    assert s["kept"].all()
    assert list(s["circuit"]) == ["A", "B"] and set(s["year"]) == {2024}


def test_stop_losses_drops_a_neutralised_stop():
    s = simparams.stop_losses(make_raw(sc_lap=5)).set_index("session_key")
    assert s.loc[10, "neutral"] and not s.loc[10, "kept"]
    assert s.loc[20, "kept"]


def test_stop_losses_bounds():
    raw = make_raw()
    raw.laps.loc[raw.laps["lap_number"] == 5, "lap_duration"] = 125.0    # loss 50 s: out of range
    s = simparams.stop_losses(raw)
    assert not s["kept"].any()


def test_loss_table():
    s = simparams.stop_losses(make_raw())
    t = simparams.loss_table(s)
    assert list(t.index) == ["A", "B", "ALL"]
    assert t.loc["ALL", "stops"] == 2 and t.loc["ALL", "median"] == pytest.approx(25.0)
