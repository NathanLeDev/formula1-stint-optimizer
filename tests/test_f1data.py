"""Tests of the lap cleaning in `f1data.py`, on small synthetic frames."""
import pandas as pd

import f1data


def laps_frame():
    """Two races, one driver each, 6 laps of 90 s; the car pits on lap 3 (lap 4 is the out-lap)."""
    rows = [{"session_key": s, "driver_number": 1, "lap_number": lap, "lap_duration": 90.0,
             "is_pit_out_lap": lap == 4} for s in (10, 20) for lap in range(1, 7)]
    return pd.DataFrame(rows)


def stints_frame():
    return pd.DataFrame([{"session_key": s, "driver_number": 1, "stint_number": n,
                          "lap_start": a, "lap_end": b}
                         for s in (10, 20) for n, a, b in [(1, 1, 3), (2, 4, 6)]])


PIT = pd.DataFrame({"session_key": [10], "driver_number": [1], "lap_number": [3]})  # race 20: no row


def test_entry_laps_from_pit_only_without_stints():
    assert f1data.entry_laps(PIT) == {(10, 1, 3)}


def test_entry_laps_fills_a_race_without_pit_rows_from_stints():
    entry = f1data.entry_laps(PIT, stints_frame())
    assert entry == {(10, 1, 3), (20, 1, 3)}          # the last lap of the final stint is not an entry


def test_entry_laps_ignores_stints_of_races_with_pit_rows():
    st = stints_frame()
    st.loc[(st["session_key"] == 10) & (st["stint_number"] == 1), "lap_end"] = 2   # disagrees with pit
    assert (10, 1, 2) not in f1data.entry_laps(PIT, st)


def test_clean_laps_drops_the_in_lap_of_a_race_without_pit_rows():
    laps = laps_frame()
    old = f1data.clean_laps(laps, PIT)
    new = f1data.clean_laps(laps, PIT, stints_frame())
    kept = lambda x, s: sorted(x.loc[x["session_key"] == s, "lap_number"])
    assert kept(old, 20) == [1, 2, 3, 5, 6]           # before the fix: the in-lap stays
    assert kept(new, 20) == [1, 2, 5, 6]
    assert kept(new, 10) == kept(old, 10) == [1, 2, 5, 6]
