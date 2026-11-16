"""Phase 4: the parameters of the simulator.

The simulated season is **2025** (decided 2026-11-12): the lap-time models are fitted on 2023-2024, so
every simulator parameter is measured on **2023-2024** too, and the real 2025 races stay available to
check the recommendations (step 6). `PARAM_YEARS` is that window.

What this module does, in the order of `04-simulator-params.ipynb`:

1. `stop_losses()`   one row per pit stop with its loss, measured exactly as phase 1 does it
                     (`data-viz.ipynb` section 7): in-lap + out-lap - 2 x the median of the driver's
                     clean laps within REF_WINDOW laps, kept between LOSS_MIN and LOSS_MAX seconds,
                     dry races, no neutralisation on the in-lap or the out-lap. The stops come from
                     `f1data.pit_entries()`, so a race with no `pit` row contributes the stops read
                     off `stints`.
2. `loss_table()`    the loss per circuit as a distribution: count, median, mean, spread, tail.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import f1data

PARAM_YEARS = (2023, 2024)

LOSS_MIN, LOSS_MAX = 10.0, 45.0   # phase 1: outside this a stop is a penalty, a repair or a botch
REF_WINDOW = 3                    # laps either side of the stop that the reference reads
REF_MIN_LAPS = 2                  # clean laps the reference needs
TAIL = 30.0                       # seconds above which a stop counts in the tail

KEY = ["session_key", "driver_number", "lap_number"]


def stop_losses(raw, entries=None):
    """One row per pit entry in a dry race, with its loss and why it is kept or not.

    `entries` defaults to `f1data.pit_entries(raw.pit, raw.stints)`; pass another table to measure
    a different set of stops on the same rules (the notebook does, to check the stints-derived ones).

    Columns added: `t_in`, `t_out` (the in-lap and out-lap times), `ref` (median of the driver's
    clean laps within REF_WINDOW laps), `ref_laps`, `loss`, `neutral` (in-lap or out-lap under safety
    car, VSC or red flag), `kept`, and `circuit` / `year`.
    """
    if entries is None:
        entries = f1data.pit_entries(raw.pit, raw.stints)
    dry = f1data.dry_keys(raw.weather, raw.races)
    s = entries[entries["session_key"].isin(dry)].reset_index(drop=True).copy()

    neutral = f1data.neutral_laps(raw.race_control)
    s["neutral"] = [(k, l) in neutral or (k, l + 1) in neutral
                    for k, l in zip(s["session_key"], s["lap_number"])]

    lap_time = raw.laps.set_index(KEY)["lap_duration"]
    s["t_in"] = lap_time.reindex(pd.MultiIndex.from_frame(s[KEY])).to_numpy()
    out_key = s[KEY].assign(lap_number=s["lap_number"] + 1)
    s["t_out"] = lap_time.reindex(pd.MultiIndex.from_frame(out_key)).to_numpy()

    clean = f1data.clean_laps(raw.laps, raw.pit, raw.stints)[KEY + ["lap_duration"]]
    near = (s[KEY].reset_index(names="stop")
            .merge(clean, on=["session_key", "driver_number"], suffixes=("", "_r")))
    near = near[(near["lap_number_r"] - near["lap_number"]).abs() <= REF_WINDOW]
    ref = near.groupby("stop")["lap_duration"].agg(["median", "size"])
    s["ref"] = ref["median"].reindex(s.index)
    s["ref_laps"] = ref["size"].reindex(s.index).fillna(0).astype(int)

    s["loss"] = s["t_in"] + s["t_out"] - 2 * s["ref"]
    s["kept"] = (~s["neutral"] & (s["ref_laps"] >= REF_MIN_LAPS)
                 & s["loss"].between(LOSS_MIN, LOSS_MAX))
    race = raw.races.set_index("session_key")
    s["circuit"] = s["session_key"].map(race["circuit_short_name"])
    s["year"] = s["session_key"].map(race["date_start"].dt.year)
    return s


def loss_table(stops):
    """The kept stops of `stops`, summarised per circuit, plus one `ALL` row for the calendar."""
    k = stops[stops["kept"]]

    def summary(g):
        x = g["loss"]
        return pd.Series({"races": g["session_key"].nunique(), "stops": len(x),
                          "median": x.median(), "mean": x.mean(), "sd": x.std(),
                          "q25": x.quantile(0.25), "q75": x.quantile(0.75), "q90": x.quantile(0.90),
                          f"share > {TAIL:.0f} s": (x > TAIL).mean()})

    table = k.groupby("circuit").apply(summary, include_groups=False)
    table.loc["ALL"] = summary(k)
    table[["races", "stops"]] = table[["races", "stops"]].astype(int)
    return table
