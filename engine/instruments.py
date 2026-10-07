"""Instrument definitions.

Everything the engine needs to know about a tradable market that is NOT part of
the strategy itself: what timezone its session is quoted in, when the cash
session opens/closes, how big a tick is, what one point is worth in money, and
sensible default costs.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MARKET_DATA = Path.home() / "mnt" / "Market Data"


@dataclass(frozen=True)
class Instrument:
    name: str
    tz: str                 # timezone the *session* is defined in
    session_open: str       # local clock time of the cash open, "HH:MM"
    session_close: str      # local clock time we force-flatten by, "HH:MM"
    tick_size: float        # smallest price increment
    point_value: float      # money per 1.0 point of price move, per 1 unit
    currency: str
    default_buffer: float   # points beyond the signal bar for the entry trigger
    default_spread: float   # round-trip spread in points
    default_slippage: float # extra adverse points on each stop fill
    files: dict = field(default_factory=dict)   # label -> csv path


DAX = Instrument(
    name="DAX", tz="Europe/Berlin", session_open="09:00", session_close="17:30",
    tick_size=1.0, point_value=25.0, currency="EUR",
    default_buffer=2.0, default_spread=0.9, default_slippage=0.0,
    files={
        "fut_eth":  MARKET_DATA / "5min_ETH" / "DAX_5min_ETH.csv",
        "cash_rth": MARKET_DATA / "5min_RTH" / "DAX_5min_RTH.csv",
        "cash_long": MARKET_DATA / "5min_RTH" / "DAX_5min_RTH_long.csv",
    },
)

NQ = Instrument(
    name="NQ", tz="America/New_York", session_open="09:30", session_close="16:00",
    tick_size=0.25, point_value=20.0, currency="USD",
    default_buffer=5.0, default_spread=0.25, default_slippage=0.0,
    files={
        "fut_eth": MARKET_DATA / "5min_ETH" / "NQ_5min_ETH.csv",
        "rth":     MARKET_DATA / "5min_RTH" / "NQ_5min_RTH.csv",
        "fut_1m":  Path(__file__).resolve().parents[1] / "data" / "NQ_1min_combined.csv",
    },
)

ES = Instrument(
    name="ES", tz="America/New_York", session_open="09:30", session_close="16:00",
    tick_size=0.25, point_value=50.0, currency="USD",
    default_buffer=1.0, default_spread=0.25, default_slippage=0.0,
    files={"fut_eth": MARKET_DATA / "5min_ETH" / "ES_5min_ETH.csv",
           "rth":     MARKET_DATA / "5min_RTH" / "ES_5min_RTH.csv"},
)

YM = Instrument(
    name="YM", tz="America/New_York", session_open="09:30", session_close="16:00",
    tick_size=1.0, point_value=5.0, currency="USD",
    default_buffer=10.0, default_spread=1.0, default_slippage=0.0,
    files={"fut_eth": MARKET_DATA / "5min_ETH" / "YM_5min_ETH.csv",
           "rth":     MARKET_DATA / "5min_RTH" / "YM_5min_RTH.csv"},
)

FTSE = Instrument(
    name="FTSE", tz="Europe/London", session_open="08:00", session_close="16:30",
    tick_size=0.5, point_value=10.0, currency="GBP",
    default_buffer=1.0, default_spread=1.0, default_slippage=0.0,
    files={"fut_eth": MARKET_DATA / "5min_ETH" / "FTSE_5min_ETH.csv",
           "rth":     MARKET_DATA / "5min_RTH" / "FTSE_5min_RTH.csv"},
)

GC = Instrument(
    name="GC", tz="America/New_York", session_open="08:20", session_close="13:30",
    tick_size=0.1, point_value=100.0, currency="USD",
    default_buffer=0.5, default_spread=0.2, default_slippage=0.0,
    files={"fut_eth": MARKET_DATA / "5min_ETH" / "GC_5min_ETH.csv",
           "rth":     MARKET_DATA / "5min_RTH" / "GC_5min_RTH.csv"},
)

REGISTRY = {i.name: i for i in (DAX, NQ, ES, YM, FTSE, GC)}


def get(name: str) -> Instrument:
    try:
        return REGISTRY[name.upper()]
    except KeyError:
        raise KeyError(f"unknown instrument {name!r}; known: {sorted(REGISTRY)}")
