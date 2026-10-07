"""Data loading and session slicing.

The raw CSVs are `time,open,high,low,close` where `time` is a unix timestamp
(seconds, UTC) marking the START of the bar. We convert to the instrument's
local timezone so that "the 4th 5-minute bar of the Frankfurt session" means the
same thing in summer and winter.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import time as dtime
from .instruments import Instrument


def _hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def load_bars(path: Path, tz: str) -> pd.DataFrame:
    """Load a 5-min (or 1-min) OHLC csv into a tz-aware, de-duplicated frame."""
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"])
    idx = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(tz)
    df = df.drop(columns=["time"]).set_index(idx).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df.astype(float)
    # sanity: high must bound open/close/low
    bad = (df["high"] < df[["open", "close", "low"]].max(axis=1) - 1e-9) | \
          (df["low"] > df[["open", "close", "high"]].min(axis=1) + 1e-9)
    if bad.any():
        df = df[~bad]
    df.index.name = "ts"
    return df


def sessionize(df: pd.DataFrame, inst: Instrument,
               session_open: str | None = None,
               session_close: str | None = None) -> pd.DataFrame:
    """Keep only bars inside the cash session and tag each with its session date.

    A bar belongs to the session if its START time is in
    [session_open, session_close).  `session_date` is the local calendar date.
    """
    o = _hhmm(session_open or inst.session_open)
    c = _hhmm(session_close or inst.session_close)
    t = df.index.time
    mask = (t >= o) & (t < c)
    out = df.loc[mask].copy()
    out["session_date"] = out.index.date
    out["minutes_from_open"] = (
        (out.index.hour * 60 + out.index.minute) - (o.hour * 60 + o.minute)
    )
    return out


def resample_from_open(df: pd.DataFrame, minutes: int, inst: Instrument,
                       session_open: str | None = None) -> pd.DataFrame:
    """Build N-minute bars anchored on the session open (not on midnight).

    Needed because the School Run Strategy uses 15-minute bars counted from the
    Frankfurt open; anchoring on midnight would be wrong for any session that
    does not start on a clean 15-minute boundary.
    """
    o = _hhmm(session_open or inst.session_open)
    open_min = o.hour * 60 + o.minute
    d = df.copy()
    d["_grp"] = (d["minutes_from_open"] // minutes).astype(int)
    g = d.groupby(["session_date", "_grp"])
    out = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"),
                start=("minutes_from_open", "min"),
                n_sub=("open", "size")).reset_index()
    out["minutes_from_open"] = out["_grp"] * minutes
    out["bar_no"] = out["_grp"] + 1          # 1-based, matching Hougaard
    out = out.drop(columns=["_grp"])
    return out


def bars_by_day(df: pd.DataFrame) -> dict:
    """session_date -> numpy arrays, for fast iteration in the engine."""
    out = {}
    for d, g in df.groupby("session_date", sort=True):
        out[d] = dict(
            ts=g.index.to_numpy(),
            o=g["open"].to_numpy(), h=g["high"].to_numpy(),
            l=g["low"].to_numpy(), c=g["close"].to_numpy(),
            mfo=g["minutes_from_open"].to_numpy(),
        )
    return out


def avg_daily_range(day_bars: dict, lookback_days: int = 14,
                    min_obs: int | None = None) -> dict:
    """Average daily RANGE in POINTS (session high minus session low --
    NOT a textbook true range, which would also use the prior close), computed on session highs/lows only,
    using the previous `lookback_days` sessions (no look-ahead)."""
    dates = sorted(day_bars)
    rng = {}
    for d in dates:
        b = day_bars[d]
        rng[d] = float(b["h"].max() - b["l"].min())
    # default: require a full window. A 14-day average built from 3 days is not
    # a 14-day average, and it silently feeds every atr_frac buffer.
    if min_obs is None:
        min_obs = lookback_days
    atr = {}
    vals = []
    for d in dates:
        # `min_obs` guards the warm-up. For the long window it must equal
        # `lookback_days`, otherwise a 100-session average computed from 8
        # sessions is indistinguishable from the 14-session one, and any ratio
        # of the two is pinned at exactly 1.0.
        atr[d] = float(np.mean(vals[-lookback_days:])) if len(vals) >= min_obs else np.nan
        vals.append(rng[d])
    return atr


# kept for backwards compatibility
true_range_by_day = avg_daily_range
