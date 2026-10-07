"""The backtest engine.

Model of reality
----------------
We only have 5-minute OHLC bars, so when several of our price levels sit inside
one bar we have to ASSUME the order in which price visited them. The engine
walks a three-leg path through every bar:

    up bar   (close >= open):  open -> low  -> high -> close
    down bar (close <  open):  open -> high -> low  -> close

and fires every resting order the path crosses, in the order it crosses them.
`intrabar="pessimistic"` flips the middle two legs whenever doing so hurts the
open position, giving a conservative lower bound; `"optimistic"` gives the
(unreachable) upper bound.

Every resting order carries a direction:
    d = +1  fires when price trades AT OR ABOVE the level  (buy stops, sell
            targets when long, the stop-loss when short)
    d = -1  fires when price trades AT OR BELOW the level
If, at any point of the walk, price is already past a live order's level on its
trigger side, the order fills THERE, not at its level. That is how gap fills and
open-through fills are handled.

Triggering always uses the raw data price. Costs (half the spread, plus
slippage on stop-type orders) are applied only to the FILL price.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .config import Config
from . import instruments as I
from . import data as D

LONG, SHORT, FLAT = 1, -1, 0
MAX_EVENTS_PER_BAR = 40
EPS = 1e-9

# lower number = fills first when two orders sit at the same price
PRIORITY = {"stop": 0, "scale_out": 1, "target": 2, "scale_in": 3,
            "buy_stop": 4, "sell_stop": 4}


@dataclass
class Fill:
    ts: object
    kind: str
    side: int
    units: float
    price_raw: float
    price_fill: float


@dataclass
class Trade:
    date: object
    side: int
    entry_ts: object
    entry_raw: float
    entry_fill: float
    risk_points: float
    exit_ts: object = None
    exit_reason: str = ""
    points: float = 0.0        # unit-weighted P&L in points, AFTER costs
    units_traded: float = 0.0
    mae: float = 0.0
    mfe: float = 0.0
    seq: int = 0               # 1 = first trade of the day, 2 = flip, ...
    fills: List[Fill] = field(default_factory=list)

    @property
    def r_multiple(self) -> float:
        return self.points / self.risk_points if self.risk_points > 0 else np.nan


class _Pos:
    __slots__ = ("side", "units", "cost_basis", "stop", "tp", "risk",
                 "entry_raw", "extreme", "realized", "units_traded",
                 "so_done", "si_done", "entry_bar_idx", "mae", "mfe", "trade")

    def __init__(self):
        self.side = FLAT


def _clone(p: "_Pos") -> "_Pos":
    q = _Pos()
    for sl in _Pos.__slots__:
        if hasattr(p, sl):
            v = getattr(p, sl)
            setattr(q, sl, set(v) if isinstance(v, set) else v)
    return q


def _snap(state: dict) -> dict:
    """A copy of the day's mutable state, so one bar can be replayed."""
    return dict(pos=_clone(state["pos"]), entries=state["entries"],
                sides_used=set(state["sides_used"]), blocked=state["blocked"],
                armed=dict(state["armed"]))


def _unrealised(pos: "_Pos", price: float, half_cost: float) -> float:
    """Mark an open position to `price`, so the two replays of a bar are
    compared on the same footing even when one of them ends still holding."""
    if pos.side == FLAT:
        return 0.0
    fill = price - pos.side * half_cost
    return pos.realized + pos.side * (fill - pos.cost_basis) * pos.units


class Engine:
    # --------------------------------------------------------------- setup
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.inst = I.get(cfg.instrument)
        self.spread = cfg.spread if cfg.spread is not None else self.inst.default_spread
        self.slip = cfg.slippage if cfg.slippage is not None else self.inst.default_slippage
        self.hs = self.spread / 2.0
        # commission is quoted in money per round turn; convert to points and
        # charge half on the way in, half on the way out
        self.half_comm = (cfg.commission / self.inst.point_value) / 2.0
        # adverse adjustment applied to each fill, by order type
        self.cost_stop = self.hs + self.slip + self.half_comm   # stop orders
        self.cost_lmt = self.hs + self.half_comm                # limits / market
        if cfg.intrabar == "pessimistic":       # legacy name
            cfg.intrabar = "adverse_hold"
        self.buffer_pts = cfg.buffer if cfg.buffer is not None else self.inst.default_buffer

    def load(self, cache: dict | None = None):
        cfg = self.cfg
        path = self.inst.files[cfg.data_key]
        key = (str(path), self.inst.tz, cfg.session_open, cfg.session_close,
               cfg.date_from, cfg.date_to, cfg.exec_data_key,
               cfg.bar_minutes if cfg.strategy == "asrs" else 15)
        if cache is not None and key in cache:
            (self.bars5, self.days, self.atr, self.atr_slow, self.signal_bars,
             self.bar_minutes) = cache[key]
            return self
        raw = D.load_bars(path, self.inst.tz)
        if cfg.date_from:
            raw = raw[raw.index >= pd.Timestamp(cfg.date_from, tz=self.inst.tz)]
        if cfg.date_to:
            raw = raw[raw.index <= pd.Timestamp(cfg.date_to, tz=self.inst.tz)
                      + pd.Timedelta(days=1)]
        sess = D.sessionize(raw, self.inst, cfg.session_open, cfg.session_close)
        self.bars5 = sess
        bm = cfg.bar_minutes if cfg.strategy == "asrs" else 15
        self.bar_minutes = bm
        self.signal_bars = D.resample_from_open(sess, bm, self.inst, cfg.session_open)
        if cfg.exec_data_key:
            fine = D.load_bars(self.inst.files[cfg.exec_data_key], self.inst.tz)
            if cfg.date_from:
                fine = fine[fine.index >= pd.Timestamp(cfg.date_from, tz=self.inst.tz)]
            if cfg.date_to:
                fine = fine[fine.index <= pd.Timestamp(cfg.date_to, tz=self.inst.tz)
                            + pd.Timedelta(days=1)]
            exec_sess = D.sessionize(fine, self.inst, cfg.session_open, cfg.session_close)
            # only keep sessions that exist in BOTH series
            keep = set(sess["session_date"]) & set(exec_sess["session_date"])
            exec_sess = exec_sess[exec_sess["session_date"].isin(keep)]
            self.signal_bars = self.signal_bars[self.signal_bars["session_date"].isin(keep)]
            self.days = D.bars_by_day(exec_sess)
        else:
            self.days = D.bars_by_day(sess)
        self.atr = D.avg_daily_range(self.days)
        self.atr_slow = D.avg_daily_range(self.days, lookback_days=100, min_obs=100)
        if cache is not None:
            cache[key] = (self.bars5, self.days, self.atr, self.atr_slow,
                          self.signal_bars, self.bar_minutes)
        return self

    # ------------------------------------------------------ signal levels
    def _levels(self, date):
        """(signal high, signal low, ready-minutes, context) for one session.

        `context` carries the signal bar and the bar immediately before it, so
        stops and targets can be placed relative to either, and so each session
        can be tagged with the shape of those bars.
        """
        cfg = self.cfg
        g = self._sig_by_day.get(date)
        if g is None:
            return None
        row = g.get(cfg.signal_bar)
        if row is None:
            return None
        hi, lo, ready = row["h"], row["l"], row["m"] + self.bar_minutes
        prev = g.get(cfg.signal_bar - 1)
        combine = cfg.combine_next_bar
        if not combine and cfg.combine_if_range_below is not None:
            combine = (hi - lo) < cfg.combine_if_range_below
        if not combine and cfg.combine_if_range_below_atr_frac is not None:
            a = self.atr.get(date, np.nan)
            if np.isfinite(a):
                combine = (hi - lo) < cfg.combine_if_range_below_atr_frac * a
        if combine:
            nxt = g.get(cfg.signal_bar + 1)
            if nxt is None:
                return None
            hi = max(hi, nxt["h"]); lo = min(lo, nxt["l"])
            ready = nxt["m"] + self.bar_minutes
        ctx = dict(sig=row, prev=prev, hi=hi, lo=lo)
        return hi, lo, ready, ctx

    def load_frame(self, df):
        """Load already-built bars directly (used by the unit tests)."""
        c = self.cfg
        sess = D.sessionize(df, self.inst, c.session_open, c.session_close)
        self.bars5 = sess
        self.days = D.bars_by_day(sess)
        self.atr = D.avg_daily_range(self.days)
        self.atr_slow = D.avg_daily_range(self.days, lookback_days=100, min_obs=100)
        bm = c.bar_minutes if c.strategy == "asrs" else 15
        self.bar_minutes = bm
        self.signal_bars = D.resample_from_open(sess, bm, self.inst, c.session_open)
        return self

    def _index_signals(self):
        out = {}
        sb = self.signal_bars
        for d, no, h, l, m, o, c in zip(sb["session_date"], sb["bar_no"], sb["high"],
                                        sb["low"], sb["minutes_from_open"],
                                        sb["open"], sb["close"]):
            out.setdefault(d, {})[int(no)] = dict(h=float(h), l=float(l), m=int(m),
                                                  o=float(o), c=float(c))
        self._sig_by_day = out

    def _buffer(self, date, hi, lo):
        c = self.cfg
        if c.buffer_mode == "points":
            return self.buffer_pts
        if c.buffer_mode == "range_frac":
            return self.buffer_pts * (hi - lo)
        a = self.atr.get(date, np.nan)
        return self.buffer_pts * a if np.isfinite(a) else np.nan

    def _stop_level(self, date, side, entry, hi, lo, buy_t, sell_t, ctx=None):
        """Where the protective stop goes. `side` is +1 long, -1 short."""
        c = self.cfg
        m = c.stop_mode
        if m == "opposite":
            lvl = sell_t if side == LONG else buy_t
        elif m == "signal_bar":
            lvl = lo if side == LONG else hi
        elif m == "signal_bar_mid":
            sig = (ctx or {}).get("sig")
            if not sig:
                return None
            lvl = (sig["h"] + sig["l"]) / 2.0
        elif m in ("prev_bar", "prev_bar_mid", "both_bars"):
            prev = (ctx or {}).get("prev")
            if not prev:
                return None                 # no bar before the signal bar
            if m == "prev_bar":
                lvl = prev["l"] if side == LONG else prev["h"]
            elif m == "prev_bar_mid":
                lvl = (prev["h"] + prev["l"]) / 2.0
            else:
                lvl = (min(lo, prev["l"]) if side == LONG
                       else max(hi, prev["h"]))
        elif m == "points":
            lvl = entry - side * c.stop_points
        elif m == "atr":
            a = self.atr.get(date, np.nan)
            if not np.isfinite(a):
                return None
            lvl = entry - side * c.stop_atr_mult * a
        else:
            lvl = entry - side * c.stop_range_mult * (hi - lo)
        # a stop must sit on the losing side of the entry
        if (side == LONG and lvl >= entry - EPS) or (side == SHORT and lvl <= entry + EPS):
            return None
        if c.min_stop_points and abs(entry - lvl) < c.min_stop_points:
            lvl = entry - side * c.min_stop_points
        return lvl

    # ------------------------------------------------------------ run loop
    def run(self):
        cfg = self.cfg
        self._index_signals()
        trades: List[Trade] = []
        skipped = {"no_signal_bar": 0, "risk_too_wide": 0, "too_few_bars": 0}
        rows = []
        for date in sorted(self.days):
            lv = self._levels(date)
            if lv is None:
                skipped["no_signal_bar"] += 1; continue
            hi, lo, ready, ctx = lv
            buf = self._buffer(date, hi, lo)
            if not np.isfinite(buf):
                skipped["no_signal_bar"] += 1; continue
            rng = hi - lo
            a = self.atr.get(date, np.nan)
            if cfg.min_vol_regime is not None or cfg.max_vol_regime is not None:
                slow = self.atr_slow.get(date, np.nan)
                if not (np.isfinite(a) and np.isfinite(slow) and slow > 0):
                    skipped["no_signal_bar"] += 1; continue
                reg = a / slow
                if cfg.min_vol_regime is not None and reg < cfg.min_vol_regime:
                    skipped.setdefault("vol_too_low", 0)
                    skipped["vol_too_low"] += 1; continue
                if cfg.max_vol_regime is not None and reg > cfg.max_vol_regime:
                    skipped.setdefault("vol_too_high", 0)
                    skipped["vol_too_high"] += 1; continue
            if (cfg.min_signal_range_adr is not None
                    or cfg.max_signal_range_adr is not None):
                if not np.isfinite(a):
                    skipped["no_signal_bar"] += 1; continue
                if cfg.min_signal_range_adr is not None and rng < cfg.min_signal_range_adr * a:
                    skipped.setdefault("range_too_narrow", 0)
                    skipped["range_too_narrow"] += 1; continue
                if cfg.max_signal_range_adr is not None and rng > cfg.max_signal_range_adr * a:
                    skipped.setdefault("range_too_wide", 0)
                    skipped["range_too_wide"] += 1; continue
            buy_t, sell_t = hi + buf, lo - buf
            if (cfg.max_stop_points and cfg.stop_mode == "opposite"
                    and (buy_t - sell_t) > cfg.max_stop_points):
                skipped["risk_too_wide"] += 1; continue
            b = self.days[date]
            idx = np.where(b["mfo"] >= ready)[0]
            if len(idx) < 1:
                skipped["too_few_bars"] += 1; continue
            dts = self._run_day(date, b, idx, hi, lo, buy_t, sell_t, ready, ctx)
            trades.extend(dts)
            rows.append(dict(date=date, sig_high=hi, sig_low=lo, sig_range=hi - lo,
                             buy_trigger=buy_t, sell_trigger=sell_t,
                             adr=self.atr.get(date, np.nan),
                             n_trades=len(dts),
                             points=sum(t.points for t in dts),
                             **self._day_features(ctx)))
        self.trades = trades
        self.skipped = skipped
        self.days_df = pd.DataFrame(rows)
        return self

    @staticmethod
    def _day_features(ctx):
        """Shape of the signal bar and the one before it, for later grouping.

        body_frac is |close - open| / (high - low): 1.0 is a bar that opened at
        one extreme and closed at the other (a trend bar), 0.0 is a bar that
        closed exactly where it opened (a doji). dir is +1 up, -1 down, 0 flat.
        """
        out = dict(inside_bar=np.nan, body_frac=np.nan, prev_body_frac=np.nan,
                   bar_dir=0, prev_dir=0, prev_range=np.nan)
        if not ctx:
            return out
        sig, prev = ctx.get("sig"), ctx.get("prev")
        if sig:
            r = sig["h"] - sig["l"]
            out["body_frac"] = abs(sig["c"] - sig["o"]) / r if r > 0 else np.nan
            out["bar_dir"] = int(np.sign(sig["c"] - sig["o"]))
        if prev:
            pr = prev["h"] - prev["l"]
            out["prev_range"] = pr
            out["prev_body_frac"] = abs(prev["c"] - prev["o"]) / pr if pr > 0 else np.nan
            out["prev_dir"] = int(np.sign(prev["c"] - prev["o"]))
            if sig:
                out["inside_bar"] = bool(sig["h"] <= prev["h"] and sig["l"] >= prev["l"])
        return out

    # --------------------------------------------------------- single day
    def _run_day(self, date, b, idx, hi, lo, buy_t, sell_t, ready=0, ctx=None) -> List[Trade]:
        c = self.cfg
        out: List[Trade] = []
        pos = _Pos()
        entries = 0
        sides_used = set()
        blocked = False
        last_i = idx[-1]
        allow = {LONG: c.direction in ("both", "long"),
                 SHORT: c.direction in ("both", "short")}
        armed = {LONG: True, SHORT: True}

        def rearm(price, st):
            if price < buy_t - EPS:
                st["armed"][LONG] = True
            if price > sell_t + EPS:
                st["armed"][SHORT] = True

        def can_open(mfo, st):
            if st["blocked"]:
                return False
            if c.entry_window_minutes is not None and mfo >= c.entry_window_minutes:
                return False
            if (c.entry_window_after_signal is not None
                    and mfo - ready >= c.entry_window_after_signal):
                return False
            if c.max_entries_per_day is not None and st["entries"] >= c.max_entries_per_day:
                return False
            return True

        def side_ok(side, st):
            if not allow[side]:
                return False
            if not c.reenter_same_direction and side in st["sides_used"]:
                return False
            return True

        for i in idx:
            O, H, L, C = b["o"][i], b["h"][i], b["l"][i], b["c"][i]
            ts, mfo = b["ts"][i], int(b["mfo"][i])

            def play(up_first, st):
                """Walk one bar under an assumed path. `st` is mutable state that
                the caller snapshots, so the bar can be replayed both ways."""
                pos_, out_ = st["pos"], []
                arm_ = (c.entry_mode == "stop") and can_open(mfo, st)
                legs = ([(O, L), (L, H), (H, C)] if up_first
                        else [(O, H), (H, L), (L, C)])
                if pos_.side == FLAT:
                    rearm(O, st)
                events = 0
                for (a, z) in legs:
                    leg_lo, leg_hi = min(a, z), max(a, z)
                    while events <= MAX_EVENTS_PER_BAR:
                        lvls = self._pending(pos_, buy_t, sell_t, arm_, 
                                             lambda sd: side_ok(sd, st), st["armed"])
                        hit = self._first_hit(a, z, lvls)
                        if hit is None:
                            break
                        price, kind, meta = hit
                        a = price
                        events += 1
                        if pos_.side == FLAT:
                            side = LONG if kind == "buy_stop" else SHORT
                            np_ = self._open(pos_, date, ts, side, price, hi, lo,
                                             buy_t, sell_t, i, ctx)
                            if np_.side == FLAT:
                                st["blocked"] = True; arm_ = False; break
                            pos_ = np_
                            st["entries"] += 1
                            st["sides_used"].add(side)
                            st["armed"][side] = False
                            pos_.trade.seq = st["entries"]
                            arm_ = (c.entry_mode == "stop") and can_open(mfo, st)
                        else:
                            done = self._handle(pos_, ts, price, kind, meta)
                            if done is not None:
                                out_.append(done)
                                pos_ = _Pos()
                                rearm(price, st)
                                if not c.allow_flip:
                                    st["blocked"] = True
                                arm_ = (c.entry_mode == "stop") and can_open(mfo, st)
                    if pos_.side != FLAT:
                        self._excursion(pos_, leg_hi, leg_lo)
                        if c.trail_update == "intrabar":
                            self._update_trail(pos_, b, i, date)
                            self._update_breakeven(pos_)
                    if events > MAX_EVENTS_PER_BAR:
                        break
                st["pos"] = pos_
                return out_

            state = dict(pos=pos, entries=entries, sides_used=sides_used,
                         blocked=blocked, armed=armed)
            if c.intrabar == "worst_case":
                # genuinely simulate BOTH orderings and keep the worse one
                snapA = _snap(state); newA = play(True, snapA)
                scoreA = (sum(t.points for t in newA)
                          + _unrealised(snapA["pos"], C, self.cost_lmt))
                snapB = _snap(state); newB = play(False, snapB)
                scoreB = (sum(t.points for t in newB)
                          + _unrealised(snapB["pos"], C, self.cost_lmt))
                chosen, new_trades = ((snapA, newA) if scoreA <= scoreB
                                      else (snapB, newB))
                state = chosen
            else:
                up = C >= O
                # legs are [O->L, L->H, H->C] when `up_first` is True, i.e. the
                # LOW is visited first, which is the adverse ordering for a long.
                if c.intrabar == "adverse_hold" and pos.side != FLAT:
                    up = (pos.side == LONG)
                elif c.intrabar == "optimistic" and pos.side != FLAT:
                    up = (pos.side == SHORT)
                new_trades = play(up, state)
            out.extend(new_trades)
            pos = state["pos"]; entries = state["entries"]
            sides_used = state["sides_used"]; blocked = state["blocked"]
            armed = state["armed"]

            # ---------------------------------------- end-of-bar handling
            if pos.side != FLAT:
                self._excursion(pos, H, L)
                if c.trail_update == "bar_close":
                    self._update_trail(pos, b, i, date)
                self._update_breakeven(pos)
                if c.time_exit_minutes is not None:
                    held = mfo - int(b["mfo"][pos.entry_bar_idx])
                    if held >= c.time_exit_minutes:
                        out.append(self._close_at(pos, ts, C, "time_exit"))
                        pos = _Pos()
                        rearm(C, state)

            if pos.side == FLAT and c.entry_mode == "close" and can_open(mfo, state):
                side = None
                if C > buy_t + EPS and side_ok(LONG, state):
                    side = LONG
                elif C < sell_t - EPS and side_ok(SHORT, state):
                    side = SHORT
                if side is not None:
                    newpos = self._open(pos, date, ts, side, C, hi, lo,
                                        buy_t, sell_t, i, ctx)
                    if newpos.side != FLAT:
                        pos = newpos
                        entries += 1
                        sides_used.add(side)
                        armed[side] = False
                        pos.trade.seq = entries

        # This engine is intraday-only: a position is always closed on the
        # last bar of the session. Carrying a position overnight would need
        # out-of-session bars, which `sessionize` deliberately removes.
        if pos.side != FLAT:
            out.append(self._close_at(pos, b["ts"][last_i], b["c"][last_i],
                                      "session_close"))
        return out

    # --------------------------------------------------------- order book
    def _pending(self, pos, buy_t, sell_t, arm, side_ok, armed):
        """[(level, direction, kind, meta)] of live resting orders.

        `armed[side]` is False while price is already past that side's trigger.
        A buy STOP order can only rest above the market: if we have just exited
        a long 30 points above the breakout level, we are not instantly long
        again -- price has to come back below the trigger first.
        """
        out = []
        if pos.side == FLAT:
            if arm and armed[LONG] and side_ok(LONG):
                out.append((buy_t, +1, "buy_stop", None))
            if arm and armed[SHORT] and side_ok(SHORT):
                out.append((sell_t, -1, "sell_stop", None))
            return out
        s = pos.side
        out.append((pos.stop, -s, "stop", None))
        if pos.tp is not None:
            out.append((pos.tp, +s, "target", None))
        for k, leg in enumerate(self.cfg.scale_out):
            if k not in pos.so_done:
                out.append((pos.entry_raw + s * leg.trigger_r * pos.risk,
                            +s, "scale_out", k))
        for k, leg in enumerate(self.cfg.scale_in):
            if k not in pos.si_done:
                out.append((pos.entry_raw + s * leg.trigger_r * pos.risk,
                            +s, "scale_in", k))
        return out

    @staticmethod
    def _first_hit(a, z, lvls) -> Optional[Tuple[float, str, object]]:
        if not lvls:
            return None
        # 1) anything price is ALREADY past on its trigger side fills at `a`
        through = [(PRIORITY[k], k, m) for (lv, d, k, m) in lvls
                   if lv is not None and ((d > 0 and a >= lv - EPS)
                                          or (d < 0 and a <= lv + EPS))]
        if through:
            through.sort()
            return a, through[0][1], through[0][2]
        if a == z:
            return None
        lo_, hi_ = (a, z) if a < z else (z, a)
        best = None
        for (lv, d, k, m) in lvls:
            if lv is None or not (lo_ - EPS <= lv <= hi_ + EPS):
                continue
            cand = (abs(lv - a), PRIORITY[k], lv, k, m)
            if best is None or cand[:2] < best[:2]:
                best = cand
        return None if best is None else (best[2], best[3], best[4])

    # ------------------------------------------------------ position ops
    def _open(self, pos, date, ts, side, price, hi, lo, buy_t, sell_t, bar_idx, ctx=None):
        c = self.cfg
        stop = self._stop_level(date, side, price, hi, lo, buy_t, sell_t, ctx)
        if stop is None:
            return _Pos()
        risk = abs(price - stop)
        if risk <= EPS:
            return _Pos()
        if c.max_stop_points and risk > c.max_stop_points:
            return _Pos()
        p = _Pos()
        p.side = side
        p.units = 1.0
        p.units_traded = 1.0
        fill = price + side * self.cost_stop
        p.cost_basis = fill
        p.entry_raw = price
        p.stop = stop
        p.risk = risk
        p.extreme = price
        p.realized = 0.0
        p.so_done = set()
        p.si_done = set()
        p.entry_bar_idx = bar_idx
        p.mae = p.mfe = 0.0
        p.tp = self._tp_level(side, price, risk, hi, lo, ctx)
        t = Trade(date=date, side=side, entry_ts=ts, entry_raw=price,
                  entry_fill=fill, risk_points=risk)
        t.fills.append(Fill(ts, "entry", side, 1.0, price, fill))
        p.trade = t
        return p

    def _tp_level(self, side, entry, risk, hi, lo, ctx=None):
        c = self.cfg
        if c.tp_mode == "none":
            return None
        if c.tp_mode == "points":
            d = c.tp_points
        elif c.tp_mode == "r_multiple":
            d = c.tp_r * risk
        elif c.tp_mode == "range_mult":
            d = c.tp_range_mult * (hi - lo)
        elif c.tp_mode == "prev_range_mult":
            prev = (ctx or {}).get("prev")
            if not prev:
                return None
            d = c.tp_prev_range_mult * (prev["h"] - prev["l"])
        else:  # both_range_mult
            prev = (ctx or {}).get("prev")
            if not prev:
                return None
            d = c.tp_both_range_mult * (max(hi, prev["h"]) - min(lo, prev["l"]))
        return entry + side * d if d > 0 else None

    def _handle(self, pos, ts, price, kind, meta) -> Optional[Trade]:
        s = pos.side
        if kind == "scale_out":
            leg = self.cfg.scale_out[meta]
            u = min(leg.size, pos.units)
            if u > EPS:
                fill = price - s * self.cost_lmt
                pos.realized += s * (fill - pos.cost_basis) * u
                pos.units -= u
                pos.trade.fills.append(Fill(ts, "scale_out", s, u, price, fill))
            pos.so_done.add(meta)
            if self.cfg.breakeven_after_first_scale_out:
                be = pos.cost_basis + s * self.cfg.breakeven_offset
                pos.stop = max(pos.stop, be) if s == LONG else min(pos.stop, be)
            return self._finish(pos, ts, "scaled_out") if pos.units <= EPS else None
        if kind == "scale_in":
            leg = self.cfg.scale_in[meta]
            fill = price + s * self.cost_stop
            newu = pos.units + leg.size
            pos.cost_basis = (pos.cost_basis * pos.units + fill * leg.size) / newu
            pos.units = newu
            pos.units_traded += leg.size
            pos.si_done.add(meta)
            pos.trade.fills.append(Fill(ts, "add", s, leg.size, price, fill))
            if self.cfg.scale_in_stop == "breakeven_avg":
                be = pos.cost_basis
                pos.stop = max(pos.stop, be) if s == LONG else min(pos.stop, be)
            return None
        if kind in ("stop", "target"):
            extra = self.cost_stop if kind == "stop" else self.cost_lmt
            fill = price - s * extra
            pos.realized += s * (fill - pos.cost_basis) * pos.units
            pos.trade.fills.append(Fill(ts, kind, s, pos.units, price, fill))
            pos.units = 0.0
            return self._finish(pos, ts, kind)
        return None

    def _close_at(self, pos, ts, price, reason) -> Trade:
        s = pos.side
        fill = price - s * self.cost_lmt
        pos.realized += s * (fill - pos.cost_basis) * pos.units
        pos.trade.fills.append(Fill(ts, reason, s, pos.units, price, fill))
        pos.units = 0.0
        return self._finish(pos, ts, reason)

    def _finish(self, pos, ts, reason) -> Trade:
        t = pos.trade
        t.exit_ts = ts
        t.exit_reason = reason
        t.points = pos.realized
        t.units_traded = pos.units_traded
        t.mae, t.mfe = pos.mae, pos.mfe
        return t

    def _excursion(self, pos, H, L):
        s = pos.side
        pos.mfe = max(pos.mfe, (H - pos.entry_raw) if s == LONG else (pos.entry_raw - L))
        pos.mae = max(pos.mae, (pos.entry_raw - L) if s == LONG else (H - pos.entry_raw))
        pos.extreme = max(pos.extreme, H) if s == LONG else min(pos.extreme, L)

    def _update_breakeven(self, pos):
        c = self.cfg
        s = pos.side
        gain = (pos.extreme - pos.entry_raw) * s
        if ((c.breakeven_at_r is not None and gain >= c.breakeven_at_r * pos.risk)
                or (c.breakeven_at_points is not None and gain >= c.breakeven_at_points)):
            be = pos.entry_raw + s * c.breakeven_offset
            pos.stop = max(pos.stop, be) if s == LONG else min(pos.stop, be)

    def _update_trail(self, pos, b, i, date):
        c = self.cfg
        if c.trail_mode == "none":
            return
        s = pos.side
        if (pos.extreme - pos.entry_raw) * s < c.trail_activate_at_r * pos.risk:
            return
        if c.trail_mode == "points":
            cand = pos.extreme - s * c.trail_points
        elif c.trail_mode == "r_multiple":
            cand = pos.extreme - s * c.trail_r * pos.risk
        elif c.trail_mode == "atr":
            a = self.atr.get(date, np.nan)
            if not np.isfinite(a):
                return
            cand = pos.extreme - s * c.trail_atr_mult * a
        else:
            j0 = max(pos.entry_bar_idx, i - c.trail_prior_bars + 1)
            cand = float(b["l"][j0:i + 1].min()) if s == LONG else float(b["h"][j0:i + 1].max())
        pos.stop = max(pos.stop, cand) if s == LONG else min(pos.stop, cand)
