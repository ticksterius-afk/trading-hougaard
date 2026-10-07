"""Strategy configuration.

Every knob the user asked for lives here. Defaults reproduce Tom Hougaard's
Advanced School Run Strategy on the DAX exactly as written in his PDF.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal
import json


@dataclass
class ScaleLeg:
    """One partial entry (scale-in) or partial exit (scale-out).

    trigger_r : how far the trade must be in profit before this leg fires,
                measured in R  (R = the initial risk in points, i.e. the
                distance from entry to the original stop). trigger_r=1 means
                "once the trade has made as many points as it was risking".
    size      : fraction of the ORIGINAL position size.
    """
    trigger_r: float
    size: float


@dataclass
class Config:
    # ------------------------------------------------------------------ setup
    instrument: str = "DAX"
    data_key: str = "fut_eth"
    # optional finer-grained series used ONLY to walk the path inside
    # each bar. Signals still come from `data_key`. Lets us check how
    # much the 5-minute intrabar guess actually matters.
    exec_data_key: Optional[str] = None
    session_open: Optional[str] = None      # None -> instrument default
    session_close: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    # ----------------------------------------------------------- signal bar
    # "asrs" -> Nth 5-minute bar;  "srs" -> Nth 15-minute bar
    strategy: Literal["asrs", "srs"] = "asrs"
    bar_minutes: int = 5
    signal_bar: int = 4                      # 1-based, counted from the open
    # optionally widen the range using the following bar(s) -- Hougaard's
    # "consult the 5th bar" rule.
    combine_next_bar: bool = False
    # ...or do that only when the signal bar is unusually narrow:
    combine_if_range_below: Optional[float] = None   # in points
    combine_if_range_below_atr_frac: Optional[float] = None  # e.g. 0.10 of ADR

    # ---------------------------------------------------------------- entry
    # "stop"  : resting stop order `buffer` beyond the signal bar extreme
    # "close" : wait for a bar to CLOSE beyond the trigger, enter on that close
    entry_mode: Literal["stop", "close"] = "stop"
    buffer: Optional[float] = None           # points; None -> instrument default
    buffer_mode: Literal["points", "range_frac", "atr_frac"] = "points"
    direction: Literal["both", "long", "short"] = "both"
    # how long entry orders stay live, in minutes after the session open
    entry_window_minutes: Optional[int] = 120   # Hougaard's "first 2 hours"
    # same idea but measured from the END OF THE SIGNAL BAR, so that different
    # signal bars can be compared on equal terms.
    entry_window_after_signal: Optional[int] = None
    max_entries_per_day: Optional[int] = None   # None = unlimited
    allow_flip: bool = True                  # stopped out -> reverse
    reenter_same_direction: bool = True      # allow re-arming after a flat exit

    # ------------------------------------------------------------ stop loss
    # "opposite"   : the opposite entry trigger (Hougaard's own rule)
    # "signal_bar" : the opposite extreme of the signal bar, no buffer
    # "points"     : fixed points
    # "atr"        : atr_mult x average daily range
    # "range_mult" : range_mult x signal-bar range
    #   "opposite"      : the opposite entry trigger (Hougaard's own rule)
    #   "signal_bar"    : the signal bar's own opposite extreme, no buffer
    #   "signal_bar_mid": the 50% level of the signal bar
    #   "prev_bar"      : the opposite extreme of the bar BEFORE the signal bar
    #                     (for the School Run that is the 1st 15-min bar)
    #   "prev_bar_mid"  : the 50% level of that earlier bar
    #   "both_bars"     : the opposite extreme of both bars combined
    #                     (for the School Run that is the whole 09:00-09:30 range)
    stop_mode: Literal["opposite", "signal_bar", "signal_bar_mid", "prev_bar",
                       "prev_bar_mid", "both_bars", "points", "atr",
                       "range_mult"] = "opposite"
    stop_points: float = 20.0
    stop_atr_mult: float = 0.25
    stop_range_mult: float = 1.0
    max_stop_points: Optional[float] = None  # skip the day if risk is wider
    # Stand aside when the signal bar is unusually narrow or unusually wide,
    # measured as a fraction of the average daily range of the last 14 sessions.
    # Hougaard's instinct that a narrow 4th bar is "a cause for concern",
    # expressed as a testable rule.
    min_signal_range_adr: Optional[float] = None
    max_signal_range_adr: Optional[float] = None
    # Volatility REGIME filter: ratio of recent average daily range (14 sessions)
    # to the longer-run one (100 sessions), both using only prior days. Above 1
    # means the market has been livelier than usual lately.
    min_vol_regime: Optional[float] = None
    max_vol_regime: Optional[float] = None
    min_stop_points: Optional[float] = None  # floor, avoids absurd 1-pt stops

    # ---------------------------------------------------------- take profit
    # "none" is Hougaard's own rule
    #   "range_mult"      : a multiple of the SIGNAL bar's range
    #   "prev_range_mult" : a multiple of the range of the bar before it
    #   "both_range_mult" : a multiple of the two bars' combined range
    tp_mode: Literal["none", "points", "r_multiple", "range_mult",
                     "prev_range_mult", "both_range_mult"] = "none"
    tp_points: float = 30.0
    tp_r: float = 2.0
    tp_range_mult: float = 1.0
    tp_prev_range_mult: float = 1.0
    tp_both_range_mult: float = 1.0

    # --------------------------------------------------- trade management
    breakeven_at_r: Optional[float] = None      # move stop to entry at +X R
    breakeven_at_points: Optional[float] = None
    breakeven_offset: float = 0.0               # points beyond entry

    trail_mode: Literal["none", "points", "r_multiple", "atr", "prior_bar"] = "none"
    trail_points: float = 20.0
    trail_r: float = 1.0
    trail_atr_mult: float = 0.2
    trail_prior_bars: int = 2                   # stop under low of last N bars
    trail_activate_at_r: float = 0.0            # don't trail until +X R
    trail_update: Literal["bar_close", "intrabar"] = "bar_close"

    # ------------------------------------------------------------- scaling
    scale_out: List[ScaleLeg] = field(default_factory=list)
    scale_in: List[ScaleLeg] = field(default_factory=list)
    scale_in_stop: Literal["keep", "breakeven_avg"] = "keep"
    breakeven_after_first_scale_out: bool = False

    # ---------------------------------------------------------------- exits
    time_exit_minutes: Optional[int] = None     # flat X min after ENTRY
    # NOTE: this engine is intraday-only. Any position still open on the last
    # bar of the session is closed at that bar's close. There is no overnight
    # carry -- see README "limitations".

    # ---------------------------------------------------------------- costs
    spread: Optional[float] = None    # round-trip, points; None -> instrument default
    slippage: Optional[float] = None  # extra adverse points per stop fill
    # Broker commission per ROUND TURN per unit, in the instrument's currency
    # (not points). Converted to points internally with the point value, which
    # is what makes a EUR25/point DAX contract comparable with a USD5/point Dow.
    commission: float = 0.0

    # ------------------------------------------------------------- realism
    # How we assume price moved WITHIN a 5-minute bar when several of our
    # levels sit inside it.
    #   "bar_direction" : up bars go open->low->high->close, down bars the
    #                     other way round. Measured against 1-minute NQ data this
    #                     is the true ordering on 87.9% of resolvable bars, and
    #                     on 95% of the widest decile -- which are exactly the
    #                     bars where the ordering changes the outcome.
    #   "adverse_hold"  : adverse ordering while a position is already open.
    #                     NOT a lower bound: the entry bar keeps the ordinary
    #                     convention, so the worst whipsaws are not counted.
    #                     (Called "pessimistic" before; the old name still works.)
    #   "worst_case"    : a genuine lower bound. Each bar is simulated BOTH ways
    #                     and the worse outcome is kept. Slow, and unreachably
    #                     bad -- no real path is adverse in every single bar.
    #   "optimistic"    : the mirror image, an unreachable upper bound.
    intrabar: Literal["bar_direction", "adverse_hold", "worst_case",
                      "pessimistic", "optimistic"] = "bar_direction"

    label: str = "unnamed"

    # -------------------------------------------------------------- helpers
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @staticmethod
    def from_dict(d: dict) -> "Config":
        d = dict(d)
        for k in ("scale_out", "scale_in"):
            if k in d and d[k]:
                d[k] = [ScaleLeg(**x) if isinstance(x, dict) else x for x in d[k]]
        return Config(**d)

    def replace(self, **kw) -> "Config":
        d = asdict(self)
        d.update(kw)
        return Config.from_dict(d)
