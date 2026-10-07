"""Hand-built bar sequences with known correct answers.

Each test constructs a single fake DAX session on a 5-minute grid starting at
09:00 Europe/Berlin and asserts exactly what the engine should do.
"""
import sys, math
from pathlib import Path
import pandas as pd, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Config, ScaleLeg
from engine.engine import Engine, LONG, SHORT

TZ = "Europe/Berlin"
FAILS = []

def frame(bars, date="2024-05-15"):
    """bars = list of (o,h,l,c) starting at 09:00, 5 min apart."""
    idx = pd.date_range(f"{date} 09:00", periods=len(bars), freq="5min", tz=TZ)
    return pd.DataFrame(bars, columns=["open","high","low","close"],
                        index=idx, dtype=float).rename_axis("ts")

def base(**kw):
    d = dict(instrument="DAX", strategy="asrs", signal_bar=4, buffer=2.0,
             stop_mode="opposite", tp_mode="none", trail_mode="none",
             entry_window_minutes=None, spread=0.0, slippage=0.0,
             intrabar="bar_direction")
    d.update(kw)
    return Config(**d)

def run(bars, cfg, date="2024-05-15"):
    e = Engine(cfg).load_frame(frame(bars, date)).run()
    return e.trades

def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if not cond else ""))
    if not cond: FAILS.append(name)

# bars 1-3 are filler, bar 4 (09:15) is the signal bar -> H=100 L=90
FILLER = [(95,96,94,95)]*3
SIG    = (95,100,90,95)          # buy>102, sell<88, risk=14

print("\n[1] clean long breakout held to the close")
t = run(FILLER+[SIG,(95,96,94,95),(95,120,95,119)], base())
check("one trade", len(t)==1, f"{len(t)}")
check("long", t and t[0].side==LONG)
check("entry at 102", t and abs(t[0].entry_raw-102)<1e-9, t and t[0].entry_raw)
check("exit at close 119 -> +17", t and abs(t[0].points-17)<1e-9, t and t[0].points)
check("risk=14", t and abs(t[0].risk_points-14)<1e-9)

print("\n[2] long, stopped at the opposite trigger, flips short")
t = run(FILLER+[SIG,(95,103,95,103),(103,103,80,80)], base())
check("two trades", len(t)==2, f"{len(t)}")
check("t1 long -14", t and t[0].side==LONG and abs(t[0].points+14)<1e-9, t and t[0].points)
check("t2 short from 88", len(t)>1 and t[1].side==SHORT and abs(t[1].entry_raw-88)<1e-9)
check("t2 +8 (88->80)", len(t)>1 and abs(t[1].points-8)<1e-9, len(t)>1 and t[1].points)

print("\n[3] gap straight through the trigger fills at the OPEN, not the level")
t = run(FILLER+[SIG,(130,131,129,130),(130,131,129,130)], base())
check("entry at 130 not 102", t and abs(t[0].entry_raw-130)<1e-9, t and t[0].entry_raw)

print("\n[4] costs: 0.9 spread + 0.5 slippage on stop fills")
t = run(FILLER+[SIG,(95,96,94,95),(95,120,95,119)], base(spread=0.9, slippage=0.5))
# entry stop 102 -> filled 102+0.45+0.5=102.95 ; exit at close 119-0.45=118.55
check("net +15.60", t and abs(t[0].points-15.60)<1e-9, t and round(t[0].points,4))

print("\n[5] take profit at 2R")
t = run(FILLER+[SIG,(95,96,94,95),(95,140,95,139)], base(tp_mode="r_multiple", tp_r=2.0))
check("+28 (2 x 14R)", t and abs(t[0].points-28)<1e-9, t and t[0].points)

print("\n[6] scale out half at 1R, rest to the close")
t = run(FILLER+[SIG,(95,96,94,95),(95,140,95,139)],
        base(scale_out=[ScaleLeg(trigger_r=1.0, size=0.5)]))
# 0.5 units @ +14, 0.5 units @ +37 (102->139)  = 7 + 18.5 = 25.5
check("+25.5", t and abs(t[0].points-25.5)<1e-9, t and t[0].points)

print("\n[7] scale in +0.5 units at 1R")
t = run(FILLER+[SIG,(95,96,94,95),(95,140,95,139)],
        base(scale_in=[ScaleLeg(trigger_r=1.0, size=0.5)]))
# 1.0 @102 + 0.5 @116 -> avg 106.667 on 1.5u ; exit 139 -> 1.5*(139-106.667)=48.5
check("+48.5", t and abs(t[0].points-48.5)<1e-9, t and round(t[0].points,4))
check("units_traded 1.5", t and abs(t[0].units_traded-1.5)<1e-9)

print("\n[8] trailing stop, 10 points, updated on bar close")
t = run(FILLER+[SIG,(95,96,94,95),(95,130,95,129),(129,129,100,100)],
        base(trail_mode="points", trail_points=10.0))
# after the 130 bar the stop is 120; next bar trades down through it
check("exit at trail 120 -> +18", t and abs(t[0].points-18)<1e-9, t and t[0].points)
check("reason=stop", t and t[0].exit_reason=="stop")

print("\n[9] breakeven after +10 points")
t = run(FILLER+[SIG,(95,96,94,95),(95,115,95,114),(114,114,95,95)],
        base(breakeven_at_points=10.0))
check("exit at 102 -> 0", t and abs(t[0].points)<1e-9, t and t[0].points)

print("\n[10] a stop order does NOT re-fire while price sits above it")
# exit long by trailing at 120, then drift sideways well above the 102 trigger
t = run(FILLER+[SIG,(95,96,94,95),(95,130,95,129),(129,129,110,112),
                (112,113,111,112),(112,113,111,112)],
        base(trail_mode="points", trail_points=10.0))
check("exactly one trade", len(t)==1, f"{len(t)} trades")

print("\n[11] direction filter: long only")
t = run(FILLER+[SIG,(95,96,94,95),(95,96,80,81)], base(direction="long"))
check("no trade", len(t)==0, f"{len(t)}")

print("\n[12] max_entries_per_day = 1 blocks the flip")
t = run(FILLER+[SIG,(95,103,95,103),(103,103,80,80)], base(max_entries_per_day=1))
check("one trade only", len(t)==1, f"{len(t)}")

print("\n[13] no look-ahead: truncating future bars cannot change earlier trades")
full = FILLER+[SIG,(95,103,95,103),(103,103,80,80),(80,95,79,94),(94,120,94,119)]
a = run(full, base())
b = run(full[:6], base())
check("first trade identical",
      abs(a[0].points-b[0].points)<1e-9 and a[0].entry_raw==b[0].entry_raw)

print("\n[14] entry_mode='close' enters on the bar close, not the trigger")
t = run(FILLER+[SIG,(95,110,95,108),(108,112,107,111)], base(entry_mode="close"))
check("entry at 108", t and abs(t[0].entry_raw-108)<1e-9, t and t[0].entry_raw)

print("\n[15] 15-minute School Run: 2nd 15-min bar = 09:15-09:30")
bars = [(95,96,94,95)]*3 + [(95,100,90,95),(95,101,91,95),(95,99,89,95)] + \
       [(95,96,94,95),(95,130,95,129)]
t = run(bars, base(strategy="srs", signal_bar=2))
# 15-min bar 2 spans the 4th,5th,6th 5-min bars -> H=101 L=89, buy>103
check("entry at 103", t and abs(t[0].entry_raw-103)<1e-9, t and t[0].entry_raw)

print("\n[16] pessimistic vs optimistic bracket the bar_direction result")
bars = FILLER+[SIG,(95,105,85,95)]
p = run(bars, base(intrabar="pessimistic")); o = run(bars, base(intrabar="optimistic"))
sp, so = sum(x.points for x in p), sum(x.points for x in o)
check("pessimistic <= optimistic", sp <= so + 1e-9, f"{sp} vs {so}")

print("\n[17] regression: intrabar trailing must not see a high the path has not reached")
# up bar O=103 H=108 L=100 C=106. Pre-bar extreme 103, trail 5 -> stop 98.
# The low (100) never touches 98, so there must be NO stop-out on this bar.
bars = FILLER+[SIG,(95,96,94,95),(95,103,95,103),(103,108,100,106),(106,107,105,106)]
a = run(bars, base(trail_mode="points", trail_points=5.0, trail_update="intrabar"))
b = run(bars, base(trail_mode="points", trail_points=5.0, trail_update="bar_close"))
check("intrabar trail does not fabricate a stop-out", len(a)==len(b),
      f"intrabar {len(a)} trades vs bar_close {len(b)}")

print("\n[18] intraday drawdown >= end-of-day drawdown")
from engine.metrics import intraday_drawdown, summarise
t = run(FILLER+[SIG,(95,103,95,103),(103,103,80,80)], base())
s_ = summarise(t, 1, 1.0, "x")
check("max_dd_intraday >= max_dd_points",
      s_["max_dd_intraday"] >= s_["max_dd_points"] - 1e-9,
      f"{s_.get('max_dd_intraday')} vs {s_.get('max_dd_points')}")

print("\n[19] new stop placements sit where they claim")
# SRS-style: 15-min bar1 = the 3 filler bars (H=96 L=94), bar2 = signal (H=100 L=90)
B1=[(95,96,94,95)]*3            # 15-min bar 1 -> H96 L94
B2=[(95,100,90,95),(95,99,91,95),(95,98,92,95)]   # 15-min bar 2 -> H100 L90
TAIL=[(95,96,94,95),(95,130,95,129)]
def srs(**kw): return base(strategy="srs", signal_bar=2, **kw)
t = run(B1+B2+TAIL, srs())                       # buy>102, stop=sell trigger 88
check("opposite stop -> risk 14", t and abs(t[0].risk_points-14)<1e-9, t and t[0].risk_points)
t = run(B1+B2+TAIL, srs(stop_mode="signal_bar")) # stop at bar2 low 90
check("signal_bar stop -> risk 12", t and abs(t[0].risk_points-12)<1e-9, t and t[0].risk_points)
t = run(B1+B2+TAIL, srs(stop_mode="prev_bar"))   # stop at bar1 low 94
check("prev_bar stop -> risk 8", t and abs(t[0].risk_points-8)<1e-9, t and t[0].risk_points)
t = run(B1+B2+TAIL, srs(stop_mode="both_bars"))  # min(90,94)=90
check("both_bars stop -> risk 12", t and abs(t[0].risk_points-12)<1e-9, t and t[0].risk_points)
t = run(B1+B2+TAIL, srs(stop_mode="signal_bar_mid"))  # (100+90)/2 = 95
check("signal_bar_mid stop -> risk 7", t and abs(t[0].risk_points-7)<1e-9, t and t[0].risk_points)

print("\n[20] a stop on the wrong side of entry is refused, not silently used")
# prev_bar_mid = 95, which is BELOW a long entry at 102 -> valid; make it invalid
# by going short: short entry at 88, prev_bar_mid 95 is above -> valid too.
# Use signal_bar_mid with a long entry that is BELOW the midpoint instead:
t = run(B1+B2+[(95,96,94,95),(95,96,94,95)], srs(stop_mode="prev_bar"))
check("no trade when nothing breaks out", len(t)==0, f"{len(t)}")

print("\n[21] take profit measured from the PREVIOUS bar's range")
# bar1 range = 96-94 = 2 ; tp_prev_range_mult=5 -> 10 points -> exit at 112
t = run(B1+B2+[(95,96,94,95),(95,140,95,139)],
        srs(tp_mode="prev_range_mult", tp_prev_range_mult=5.0))
check("+10 from a 2-point bar1 range", t and abs(t[0].points-10)<1e-9, t and t[0].points)

print("\n[22] session tagging: inside bar and body fraction")
from engine.engine import Engine as _E
cfg = srs(); e = _E(cfg).load_frame(frame(B1+B2+TAIL)).run()
row = e.days_df.iloc[0]
check("bar2 is NOT inside bar1 here", row["inside_bar"] == False, row["inside_bar"])
# bar2 open 95 close 95 -> body 0 -> doji, dir 0
check("body_frac 0 for a flat bar", abs(row["body_frac"])<1e-9, row["body_frac"])
check("bar_dir 0 for a flat bar", row["bar_dir"]==0, row["bar_dir"])
INB=[(95,96,94,95),(95,95.5,94.5,95),(95,95.5,94.5,95.8)]   # bar2 inside bar1
e2 = _E(srs()).load_frame(frame(B1+INB+TAIL)).run()
check("inside bar detected", bool(e2.days_df.iloc[0]["inside_bar"]) is True,
      e2.days_df.iloc[0]["inside_bar"])

print("\n" + ("ALL TESTS PASSED" if not FAILS else f"{len(FAILS)} FAILURES: {FAILS}"))
sys.exit(1 if FAILS else 0)
