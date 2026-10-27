"""Loading and cleaning of the OpenF1 race data, shared by every notebook.

`data-viz.ipynb` built its analysis table in three places — the cleaning in
section 4, the neutralised laps in section 7, and the final table at the top of
section 9, which redid the cleaning its own way. One table assembled from three
cells is one table that can diverge from itself, so it is built here instead.

The entry point is `build_base()`: one clean lap per row, with the compound and
age of the tyre on it, the circuit, the season, the weather and the traffic.

    import f1data

    raw = f1data.load_raw()           # cached after the first run
    base = f1data.build_base(raw)

Two groups of columns are new, and are here because phase 1 listed them as the
next thing to check: `track_temp` for the compound confound (section 11), and
`traffic` / `dirty_air` from the `intervals` endpoint, which nothing loaded.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE_URL = "https://api.openf1.org/v1"
CACHE = Path(__file__).resolve().parent / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

SEASONS = (2023, 2024, 2025, 2026)
COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

PACE_MAX = 1.10    # a lap above this x the race's best lap is not race pace
RAIN_MAX = 0.1     # mean `rainfall` above which the race is called wet
DIRTY_AIR = 1.0    # seconds behind the car ahead that count as dirty air
ENDPOINTS = ["race_control", "session_result", "stints", "pit", "weather"]


# 1. API access ---------------------------------------------------------------

def get(endpoint, force=False, **params):
    """GET OpenF1 with a disk-based cache and a retry on 429 (rate-limited API)."""
    key = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    path = CACHE / f"{endpoint}_{hashlib.md5(key.encode()).hexdigest()[:10]}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)

    for attempt in range(6):
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
    else:
        raise RuntimeError(f"persistent 429 on {endpoint} {params}")

    time.sleep(0.5)
    if r.status_code == 404:
        return pd.DataFrame()
    r.raise_for_status()

    df = _castable(endpoint, pd.DataFrame(r.json()))
    try:
        if not df.empty:
            df.to_parquet(path, index=False)
    except Exception:
        print(f"cannot cache {endpoint} {params}")
    return df


# Columns that arrive with mixed types, which parquet refuses to write: without
# this the endpoint says "cannot cache" and is re-downloaded on every run. The
# notebook pays that on `session_result` today. `numeric` coerces, `text`
# flattens what is genuinely not one type (`session_result.duration` is a lap
# time for a race and a list of three for a qualifying).
_MIXED = {
    "intervals": {"numeric": ["gap_to_leader", "interval"]},
    "session_result": {"numeric": ["position"], "text": ["duration", "gap_to_leader"]},
}


def _castable(endpoint, df):
    """Make the frame writable to parquet without losing what the analysis reads."""
    cast = _MIXED.get(endpoint)
    if not cast or df.empty:
        return df
    if endpoint == "intervals":
        # "+1 LAP" instead of a gap: the flag is kept, the string is not.
        df["lapped"] = df["gap_to_leader"].astype(str).str.contains("LAP", na=False)
    for col in cast.get("numeric", []):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in cast.get("text", []):
        df[col] = df[col].astype(str).where(df[col].notna())
    return df


def _utc(s):
    return pd.to_datetime(s, format="ISO8601", utc=True)


# 2. Loading ------------------------------------------------------------------

@dataclass
class Raw:
    """The endpoints as they come out of the API, before any cleaning."""
    sessions: pd.DataFrame
    races: pd.DataFrame
    laps: pd.DataFrame
    stints: pd.DataFrame
    pit: pd.DataFrame
    weather: pd.DataFrame
    race_control: pd.DataFrame
    session_result: pd.DataFrame
    intervals: pd.DataFrame = field(default_factory=pd.DataFrame)


def key_region(sessions):
    """A whole range of seasons in one request, per endpoint.

    OpenF1 only accepts the **strict** operators `>` and `<` (`session_key>=X`
    returns a misleading 404), hence the -1 / +1.
    """
    return {"session_key>": int(sessions["session_key"].min()) - 1,
            "session_key<": int(sessions["session_key"].max()) + 1}


def load_sessions(seasons=SEASONS):
    return pd.concat([get("sessions", year=y) for y in seasons], ignore_index=True)


def held_races(sessions):
    """Races already run: the calendar carries dates with no data behind them yet."""
    races = sessions.query("session_name == 'Race'").copy()
    races["date_start"] = _utc(races["date_start"])
    return races[races["date_start"] <= pd.Timestamp.now(tz="UTC")]


def by_session(endpoint, session_keys):
    """One request per race, for the endpoints too large to fetch by range."""
    frames = [get(endpoint, session_key=int(k)) for k in session_keys]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_raw(seasons=SEASONS, traffic=True, verbose=True):
    """Every endpoint the analysis needs. The first run downloads, later runs read the cache.

    `laps` and `intervals` go one request per race; the rest fit in a single
    `session_key` range per endpoint. `intervals` is the heavy one (~25k rows a
    race, a few minutes on the first run): pass traffic=False to skip it.
    """
    sessions = load_sessions(seasons)
    races = held_races(sessions)
    region = key_region(sessions)

    frames = {ep: get(ep, **region) for ep in ENDPOINTS}
    raw = Raw(sessions=sessions, races=races,
              laps=by_session("laps", races["session_key"]),
              intervals=by_session("intervals", races["session_key"]) if traffic
              else pd.DataFrame(),
              **frames)
    if verbose:
        print(f"{len(races)} races held over {min(seasons)}-{max(seasons)}")
        for name in ["laps", "stints", "pit", "weather", "race_control", "intervals"]:
            print(f"  {name:13s} {getattr(raw, name).shape}")
    return raw


# 3. Neutralisations ----------------------------------------------------------

def neutral_laps(race_control):
    """Laps run under safety car, virtual safety car or red flag.

    From the deployment (or the red flag) through the lap following the restart.
    These are not race pace and leave the analysis table. A yellow flag is
    **not** a neutralisation and is not in here — section 6 of the notebook
    measures it separately, and the two rank the circuits differently.
    """
    rc = race_control.assign(date=_utc(race_control["date"]))
    sc = rc[rc["message"].str.contains(
                "SAFETY CAR DEPLOYED|SAFETY CAR IN THIS LAP|SAFETY CAR ENDING", na=False)
            | rc["flag"].eq("RED")].dropna(subset=["lap_number"]).sort_values(
                ["session_key", "date"]).copy()
    sc["start"] = sc["message"].str.contains("DEPLOYED", na=False) | sc["flag"].eq("RED")
    sc["end"] = sc.groupby("session_key")["lap_number"].shift(-1).fillna(sc["lap_number"])
    return {(r.session_key, l) for r in sc[sc["start"]].itertuples()
            for l in range(int(r.lap_number), int(r.end) + 2)}


def dry_keys(weather, races, rain_max=RAIN_MAX):
    """session_key of the races run in the dry, rain taken from `weather`."""
    rain = weather.groupby("session_key")["rainfall"].mean()
    return set(races["session_key"]) - set(rain[rain > rain_max].index)


# 4. Cleaning -----------------------------------------------------------------

def clean_laps(laps, pit, pace_max=PACE_MAX):
    """The laps that reflect actual pace.

    Dropped: laps with no time, out-laps, in-laps (the `pit` endpoint gives the
    entry lap), and laps above pace_max x the fastest lap of their own race
    (safety car, traffic, flags). `pace` is kept — a lap time over the best lap
    of its own race is comparable from one circuit to the next.
    """
    entry = set(zip(pit["session_key"], pit["driver_number"], pit["lap_number"]))
    keys = pd.Series(list(zip(laps["session_key"], laps["driver_number"], laps["lap_number"])),
                     index=laps.index)
    out = laps[laps["lap_duration"].notna() & ~laps["is_pit_out_lap"]
               & ~keys.isin(entry)].copy()
    out["pace"] = out["lap_duration"] / out.groupby("session_key")["lap_duration"].transform("min")
    return out[out["pace"] <= pace_max]


def drop_neutral(laps, neutral):
    """Remove the laps in a `neutral_laps()` set."""
    return laps[[(k, l) not in neutral
                 for k, l in zip(laps["session_key"], laps["lap_number"])]]


def attach_stints(laps, stints):
    """The compound and the tyre age of each lap.

    A lap shared by two stints (the pit lap closes one and opens the next) is
    kept once, with the stint that ends: that lap was driven on the old tyres.
    """
    out = (laps.merge(stints.drop(columns="meeting_key", errors="ignore"),
                      on=["session_key", "driver_number"])
           .query("lap_start <= lap_number <= lap_end")
           .sort_values(["session_key", "driver_number", "lap_number", "stint_number"])
           .drop_duplicates(["session_key", "driver_number", "lap_number"]).copy())
    out["age"] = out["tyre_age_at_start"] + out["lap_number"] - out["lap_start"]
    return out


# 5. Conditions on the lap ----------------------------------------------------

WEATHER_COLS = {"track_temperature": "track_temp", "air_temperature": "air_temp",
                "humidity": "humidity"}


def _asof(laps, right, cols, by, tolerance, direction="nearest"):
    """Join `right` on the lap's start date, keeping every row and the index of `laps`."""
    left = pd.DataFrame({"_t": _utc(laps["date_start"])}, index=laps.index)
    left[by] = laps[by].values
    left = left[left["_t"].notna()].sort_values("_t").reset_index(names="_i")
    merged = pd.merge_asof(left, right, left_on="_t", right_on="date", by=by,
                           direction=direction, tolerance=tolerance)
    return laps.join(merged.set_index("_i")[cols])


def attach_weather(laps, weather, tolerance="10min"):
    """Track temperature, air temperature and humidity on each lap.

    `weather` is sampled about once a minute and matched to the nearest reading
    on either side of the lap's start. Temperature is the first thing phase 1
    asks for: the compound a car runs is tied to *when* it runs, so without
    something that varies with the race phase the compound offsets stay
    confounded and the simulator cannot choose a tyre. Lap 1 carries no
    `date_start`, and `base` starts at lap 2 anyway.
    """
    w = (weather.assign(date=_utc(weather["date"]))
         .rename(columns=WEATHER_COLS)[["session_key", "date", *WEATHER_COLS.values()]]
         .sort_values("date"))
    return _asof(laps, w, list(WEATHER_COLS.values()), "session_key",
                 pd.Timedelta(tolerance))


def attach_traffic(laps, intervals, dirty_air=DIRTY_AIR):
    """The gap to the car ahead during each lap, from the `intervals` endpoint.

    `intervals` is sampled about every 4 s. Each sample is assigned to the lap it
    falls in — backward from the lap's `date_start`, inside its `lap_duration` —
    which gives three columns:

    - `traffic`   median gap to the car ahead over the lap, in seconds;
    - `dirty_air` share of the lap spent within `dirty_air` seconds of that car;
    - `traffic_n` how many samples the two above rest on.

    The leader is reported with `interval` = 0 and `gap_to_leader` = 0. A median
    would read that as the heaviest traffic on the grid when it is the clearest
    air on it, so those samples count as clear air and stay out of the median.

    `traffic` is left unclipped: 2 laps in a thousand are above 60 s, which is a
    car genuinely alone rather than an error, and where to cut a variable that
    saturates past ~10 s is the model's decision, not this function's.
    """
    if intervals.empty:
        return laps.assign(traffic=np.nan, dirty_air=np.nan, traffic_n=0)

    s = intervals.assign(date=_utc(intervals["date"]))
    s = s[s["date"].notna()][["session_key", "driver_number", "date", "interval",
                              "gap_to_leader"]].copy()
    s["interval"] = s["interval"].where(~s["gap_to_leader"].eq(0))   # leader: nothing ahead
    s = s.sort_values("date")

    start = _utc(laps["date_start"])
    window = pd.DataFrame({"_t": start,
                           "_end": start + pd.to_timedelta(laps["lap_duration"], unit="s")},
                          index=laps.index)
    window[["session_key", "driver_number"]] = laps[["session_key", "driver_number"]].values
    window = window[window["_t"].notna()].sort_values("_t").reset_index(names="_i")

    m = pd.merge_asof(s, window, left_on="date", right_on="_t",
                      by=["session_key", "driver_number"], direction="backward")
    m = m[m["date"] <= m["_end"]]
    m["_close"] = m["interval"].le(dirty_air)        # NaN (leader) -> False, clear air

    agg = m.groupby("_i").agg(traffic=("interval", "median"),
                              dirty_air=("_close", "mean"),
                              traffic_n=("_close", "size"))
    out = laps.join(agg)
    out["traffic_n"] = out["traffic_n"].fillna(0).astype(int)
    return out


# 6. The analysis table -------------------------------------------------------

def build_base(raw=None, *, seasons=SEASONS, dry_only=True, neutral=True, from_lap=2,
               weather=True, traffic=True):
    """The table every analysis starts from: one clean race lap per row.

    Applied in order — clean laps, dry races only, from `from_lap` on, minus the
    neutralised laps — then the compound and age of the tyre, the circuit, the
    season, and the conditions on the lap.

    The defaults are the table the phase 1 figures were computed on. Section 4
    of `data-viz.ipynb` looks at a wider set on purpose (every race, lap 1
    included): that is this with dry_only=False, neutral=False, from_lap=None.
    """
    if raw is None:
        raw = load_raw(seasons, traffic=traffic)

    laps = clean_laps(raw.laps, raw.pit)
    if dry_only:
        laps = laps[laps["session_key"].isin(dry_keys(raw.weather, raw.races))]
    if from_lap:
        laps = laps[laps["lap_number"] >= from_lap]
    if neutral:
        laps = drop_neutral(laps, neutral_laps(raw.race_control))

    base = attach_stints(laps, raw.stints)
    race = raw.races.set_index("session_key")
    base["circuit"] = base["session_key"].map(race["circuit_short_name"])
    base["year"] = base["session_key"].map(race["date_start"].dt.year)

    if weather:
        base = attach_weather(base, raw.weather)
    if traffic:
        base = attach_traffic(base, raw.intervals)
    return base


def race_stints(base):
    """One row per stint actually driven, with its length in laps."""
    return (base.drop_duplicates(["session_key", "driver_number", "stint_number"])
            .assign(n_laps=lambda d: d["lap_end"] - d["lap_start"] + 1))


if __name__ == "__main__":
    base = build_base(load_raw())
    print(f"\nbase {base.shape[0]} laps, {base['session_key'].nunique()} races, "
          f"{base['circuit'].nunique()} circuits")
    print(base[["lap_duration", "age", "track_temp", "traffic", "dirty_air"]]
          .describe().round(2).to_string())
    print(f"\ntrack_temp on {base['track_temp'].notna().mean():.1%} of laps, "
          f"traffic on {base['traffic'].notna().mean():.1%}")
