"""Per-market time-of-day scan + does trading all four together help?"""
import sys; sys.path.insert(0, '.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE = {}
MKTS = ["DAX", "NQ", "ES", "YM"]
COMM = {"DAX": 5.0, "NQ": 4.0, "ES": 4.0, "YM": 4.0}

def cost(m):
    t = instruments.get(m).tick_size
    return t, t                      # realistic: 1 tick spread + 1 tick slippage

def cfg(m, **kw):
    sp, sl = cost(m)
    d = dict(instrument=m, data_key="fut_eth", strategy="asrs", signal_bar=4,
             buffer=0.008, buffer_mode="atr_frac", stop_mode="opposite",
             tp_mode="none", trail_mode="none", entry_window_minutes=120,
             intrabar="bar_direction", spread=sp, slippage=sl, commission=COMM[m])
    d.update(kw); return Config(**d)

# ---------------------------------------------------------- time-of-day scan
print("=" * 78); print("TIME-OF-DAY SCAN -- money by which bar is used, per market")
print("(each bar gets the same 90 minutes after it closes)"); print("=" * 78)
tod = []
for m in MKTS:
    inst = instruments.get(m)
    best = None
    for n in range(1, 49):
        c = cfg(m, label=f"{m}_b{n}", signal_bar=n,
                entry_window_minutes=None, entry_window_after_signal=90)
        e = Engine(c).load(CACHE).run()
        s = metrics.summarise(e.trades, len(e.days), inst.point_value, c.label)
        mins = (n - 1) * 5
        oh, om = divmod(mins, 60)
        tod.append(dict(market=m, bar=n, mins_after_open=mins,
                        clock=f"+{oh}:{om:02d}", money=s.get("total_money", 0),
                        t=s.get("t_stat", np.nan), pf=s.get("profit_factor", np.nan)))
    d = pd.DataFrame([r for r in tod if r["market"] == m])
    b4 = float(d[d.bar == 4].money.iloc[0])
    rank = (d.money < b4).mean() * 100
    h = [d[(d.mins_after_open >= a) & (d.mins_after_open < a + 60)].money.mean()
         for a in (0, 60, 120, 180)]
    print(f"  {m:4s} bar4={b4:>10,.0f} ({rank:.0f}th pct of 48) | "
          f"hour1 {h[0]:>9,.0f}  hour2 {h[1]:>9,.0f}  hour3 {h[2]:>9,.0f}  hour4 {h[3]:>9,.0f}",
          flush=True)
pd.DataFrame(tod).to_csv("results/xm_tod.csv", index=False)

# ------------------------------------------------------------- portfolio
print("\n" + "=" * 78)
print("PORTFOLIO -- one contract of each, daily P&L converted to a common unit")
print("(USD, EURUSD held at 1.08 for simplicity -- the point is correlation, not FX)")
print("=" * 78)
FX = {"DAX": 1.08, "NQ": 1.0, "ES": 1.0, "YM": 1.0}
series = {}
for m in MKTS:
    e = Engine(cfg(m, label=m)).load(CACHE).run()
    tf = metrics.trades_to_frame(e.trades)
    pv = instruments.get(m).point_value * FX[m]
    series[m] = tf.groupby("date")["points"].sum() * pv
daily = pd.DataFrame(series).fillna(0.0)
daily = daily[daily.index >= daily.index.min()]
print("\ncorrelation of daily P&L:")
print(daily.corr().round(3).to_string())
port = daily.sum(axis=1)
def stats(x, nm):
    eq = x.cumsum(); dd = (np.maximum.accumulate(eq) - eq).max()
    sh = x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) else np.nan
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    print(f"  {nm:22s} total {x.sum():>11,.0f}  /yr {x.mean()*252:>9,.0f}  "
          f"maxDD {dd:>10,.0f}  Sharpe {sh:5.2f}  t {t:5.2f}  "
          f"return/DD {x.sum()/dd if dd else float('nan'):5.2f}")
    return dict(name=nm, total=x.sum(), per_year=x.mean()*252, dd=dd, sharpe=sh, t=t)
print("\nstandalone vs combined:")
out = [stats(daily[m], m + " alone") for m in MKTS]
out.append(stats(port, "ALL FOUR combined"))
out.append(stats(daily[["DAX", "NQ"]].sum(axis=1), "DAX + NQ only"))
pd.DataFrame(out).to_csv("results/xm_portfolio.csv", index=False)
daily.to_csv("results/xm_portfolio_daily.csv")
print("\nwrote results/xm_tod.csv, xm_portfolio.csv")
