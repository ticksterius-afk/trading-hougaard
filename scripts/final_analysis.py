"""Headline numbers, out-of-sample split, and the data behind the charts."""
import sys; sys.path.insert(0,'.')
import json, numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE={}
PUB = "2023-05-08"     # Hougaard published the ASRS paper on this date

def R(label, **kw):
    d = dict(instrument="DAX", data_key="fut_eth", strategy="asrs", signal_bar=4,
             buffer=2.0, stop_mode="opposite", tp_mode="none", trail_mode="none",
             entry_window_minutes=120, spread=0.9, intrabar="bar_direction")
    d.update(kw)
    c = Config(label=label, **d)
    e = Engine(c).load(CACHE).run()
    inst = instruments.get(c.instrument)
    s = metrics.summarise(e.trades, len(e.days), inst.point_value, label)
    s.update(metrics.bootstrap_ci(e.trades))
    return e, s

out = {}

# ---------------------------------------------------------- 1) headline
print("== cost scenarios on DAX futures, 2021-2026 ==")
tbl=[]
for name, sp, sl in [("zero cost",0.0,0.0), ("Hougaard 0.9",0.9,0.0),
                     ("retail 1.2 + 0.5 slip",1.2,0.5), ("stressed 3.0",3.0,0.5)]:
    e,s = R(name, spread=sp, slippage=sl)
    tbl.append(dict(scenario=name, spread=sp, slip=sl, trades=s['trades'],
                    points=s['total_points'], per_trade=s['points_per_trade'],
                    pf=s['profit_factor'], sharpe=s['sharpe'], t=s['t_stat'],
                    maxdd=s['max_dd_points'], money=s['total_money']))
    print(tbl[-1], flush=True)
out['costs']=tbl

# --------------------------------------------- 2) out of sample since pub
print("\n== before / after Hougaard published (8 May 2023) ==")
oos=[]
# PUB itself belongs to exactly one leg. date_to is inclusive, so the in-sample
# leg must stop the day before, or the 2023-05-08 session is counted twice.
for nm, kw in [("in-sample-ish (pre 2023-05-08)", dict(date_to="2023-05-05")),
               ("out-of-sample (from 2023-05-08)", dict(date_from=PUB))]:
    e,s = R(nm, **kw)
    oos.append(dict(period=nm, sessions=s['sessions'], trades=s['trades'],
                    points=s['total_points'], per_session=s['points_per_session'],
                    per_trade=s['points_per_trade'], pf=s['profit_factor'],
                    t=s['t_stat'], win=s['win_rate']))
    print(oos[-1], flush=True)
out['oos']=oos

# -------------------------------------------------- 3) equity + charts
e,s = R("chart", spread=0.9)
tf = metrics.trades_to_frame(e.trades)
daily = tf.groupby("date")["points"].sum()
eq = daily.cumsum()
pd.DataFrame({"date":eq.index.astype(str), "equity":eq.values.round(1),
              "daily":daily.values.round(1)}).to_csv("results/equity_fut.csv", index=False)
print("\nequity curve: %d days, final %.0f, max dd %.0f"
      % (len(eq), eq.iloc[-1], (np.maximum.accumulate(eq)-eq).max()))

e2,_ = R("cash14", data_key="cash_long", spread=0.9)
tf2 = metrics.trades_to_frame(e2.trades)
d2 = tf2.groupby("date")["points"].sum(); eq2=d2.cumsum()
pd.DataFrame({"date":eq2.index.astype(str),"equity":eq2.values.round(1)}).to_csv(
    "results/equity_cash14.csv", index=False)
print("cash 14y: %d days, final %.0f, max dd %.0f"
      % (len(eq2), eq2.iloc[-1], (np.maximum.accumulate(eq2)-eq2).max()))

# ------------------------------------- 4) where does the money come from?
print("\n== concentration: how much comes from the best days? ==")
srt = daily.sort_values(ascending=False)
tot = daily.sum()
conc = {}
for k in (1, 5, 10, 20, 50):
    pct = k/len(daily)*100
    conc[f"top_{k}_days"] = round(float(srt.head(k).sum()/tot*100),1)
    print(f"  best {k:3d} days ({pct:4.1f}% of sessions) = "
          f"{srt.head(k).sum()/tot*100:5.1f}% of all profit")
out['concentration']=conc
# how many trades produce the profit
tp = tf["points"].sort_values(ascending=False)
print(f"  best 5% of trades ({int(len(tp)*.05)}) = "
      f"{tp.head(int(len(tp)*.05)).sum()/tf['points'].sum()*100:.0f}% of all profit")

# ----------------------------------------------- 5) trade-level detail
print("\n== trade anatomy (Hougaard 0.9 spread) ==")
print(f"  trades {len(tf)}, win rate {(tf.points>0).mean()*100:.1f}%")
print(f"  avg win {tf.points[tf.points>0].mean():.1f}  avg loss {tf.points[tf.points<0].mean():.1f}")
print(f"  median trade {tf.points.median():.1f}")
print(f"  avg risk (stop distance) {tf.risk_points.mean():.1f} points")
print("  exit reasons:", tf.exit_reason.value_counts().to_dict())
print("  by entry number in the day:")
for seq,g in tf.groupby("seq"):
    if seq<=5: print(f"    #{seq}: {len(g):5d} trades  {g.points.sum():+9.1f} pts  "
                     f"{g.points.mean():+6.2f}/trade")
tf.to_csv("results/trades_baseline.csv", index=False)
json.dump(out, open("results/final_analysis.json","w"), indent=2, default=str)
print("\nwrote results/trades_baseline.csv, equity_*.csv, final_analysis.json")
