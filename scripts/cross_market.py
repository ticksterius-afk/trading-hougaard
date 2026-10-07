"""Full per-market treatment of the Advanced School Run.

The rule is translated faithfully to each market -- the 4th 5-minute bar after
that market's OWN cash open -- and every cost is expressed in that market's own
ticks and currency, so nothing is compared in "points", which are not
commensurable across contracts.
"""
import sys; sys.path.insert(0, '.')
import json
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments

CACHE = {}
MKTS = ["DAX", "NQ", "ES", "YM"]
# commission per round turn, in the contract's own currency (retail futures)
COMM = {"DAX": 5.0, "NQ": 4.0, "ES": 4.0, "YM": 4.0}
BUF_ADR = 0.008          # 0.8% of average daily range ~= Hougaard's 2 DAX points

def cfg(mkt, **kw):
    d = dict(instrument=mkt, data_key="fut_eth", strategy="asrs", signal_bar=4,
             buffer=BUF_ADR, buffer_mode="atr_frac", stop_mode="opposite",
             tp_mode="none", trail_mode="none", entry_window_minutes=120,
             allow_flip=True, intrabar="bar_direction", commission=COMM[mkt])
    d.update(kw)
    return Config(**d)

def run(c):
    e = Engine(c).load(CACHE).run()
    inst = instruments.get(c.instrument)
    s = metrics.summarise(e.trades, len(e.days), inst.point_value, c.label)
    s.update(metrics.bootstrap_ci(e.trades))
    s["currency"] = inst.currency
    return e, s

def costs(mkt, level):
    """(spread, slippage) in POINTS for a given realism level."""
    t = instruments.get(mkt).tick_size
    return {"tight": (t, 0.0), "realistic": (t, t), "poor": (2 * t, t)}[level]

# ====================================================== 1. cost ladder
print("=" * 86)
print("1. HEADLINE BY MARKET -- 4th 5-min bar after that market's own cash open")
print("=" * 86)
rows = []
for m in MKTS:
    inst = instruments.get(m)
    for lvl in ("tight", "realistic", "poor"):
        sp, sl = costs(m, lvl)
        _, s = run(cfg(m, label=f"{m}_{lvl}", spread=sp, slippage=sl))
        rows.append(dict(market=m, cost=lvl, ccy=inst.currency,
                         spread_pts=sp, slip_pts=sl, comm=COMM[m],
                         sessions=s["sessions"], trades=s["trades"],
                         money=s["total_money"], per_year=s["money_per_year"],
                         per_trade_R=s["expectancy_R"], pf=s["profit_factor"],
                         win=s["win_rate"], sharpe=s["sharpe"], t=s["t_stat"],
                         dd_money=s["max_dd_intraday_money"],
                         boot_p05=s["boot_p05"] * inst.point_value,
                         prob_pos=s["boot_prob_positive"]))
        r = rows[-1]
        print(f"  {m:4s} {lvl:10s} {r['ccy']} {r['money']:>10,.0f}  "
              f"/yr {r['per_year']:>9,.0f}  PF {r['pf']:.3f}  R {r['per_trade_R']:+.4f}  "
              f"t {r['t']:>5.2f}  DD {r['dd_money']:>10,.0f}  n={r['trades']}", flush=True)
pd.DataFrame(rows).to_csv("results/xm_costs.csv", index=False)

# ====================================================== 2. SRS vs ASRS
print("\n" + "=" * 86)
print("2. SIMPLE (15-min) vs ADVANCED (5-min), at realistic costs")
print("=" * 86)
rows2 = []
for m in MKTS:
    sp, sl = costs(m, "realistic")
    for nm, kw in (("ASRS 5m bar4", dict(strategy="asrs", signal_bar=4)),
                   ("ASRS 5m bar5", dict(strategy="asrs", signal_bar=5)),
                   ("SRS 15m bar2", dict(strategy="srs", signal_bar=2))):
        _, s = run(cfg(m, label=f"{m}|{nm}", spread=sp, slippage=sl, **kw))
        rows2.append(dict(market=m, variant=nm, trades=s["trades"],
                          money=s["total_money"], per_year=s["money_per_year"],
                          pf=s["profit_factor"], R=s["expectancy_R"], t=s["t_stat"],
                          dd=s["max_dd_intraday_money"]))
        r = rows2[-1]
        print(f"  {m:4s} {nm:14s} {r['money']:>10,.0f}  /yr {r['per_year']:>9,.0f}  "
              f"PF {r['pf']:.3f}  t {r['t']:>5.2f}  n={r['trades']}", flush=True)
pd.DataFrame(rows2).to_csv("results/xm_variants.csv", index=False)

# ====================================================== 3. buffer sensitivity
print("\n" + "=" * 86)
print("3. BUFFER SENSITIVITY (fraction of average daily range), realistic costs")
print("=" * 86)
rows3 = []
for m in MKTS:
    sp, sl = costs(m, "realistic")
    line = f"  {m:4s} "
    for b in (0.002, 0.004, 0.008, 0.016, 0.032):
        _, s = run(cfg(m, label=f"{m}_b{b}", buffer=b, spread=sp, slippage=sl))
        rows3.append(dict(market=m, buffer_adr=b, money=s["total_money"],
                          trades=s["trades"], pf=s["profit_factor"]))
        line += f"{b*100:.1f}%:{s['total_money']:>9,.0f}  "
    print(line, flush=True)
pd.DataFrame(rows3).to_csv("results/xm_buffer.csv", index=False)

# ====================================================== 4. stability
print("\n" + "=" * 86)
print("4. STABILITY -- year by year and first half vs second half, realistic costs")
print("=" * 86)
rows4 = []
for m in MKTS:
    sp, sl = costs(m, "realistic")
    e, s = run(cfg(m, label=f"{m}_stab", spread=sp, slippage=sl))
    inst = instruments.get(m)
    tf = metrics.trades_to_frame(e.trades)
    daily = tf.groupby("date")["points"].sum() * inst.point_value
    yr = daily.groupby(daily.index.year).sum()
    print(f"  {m:4s} " + "  ".join(f"{int(y)}:{v:>8,.0f}" for y, v in yr.items()), flush=True)
    mid = tf["date"].quantile(0.5)
    h1 = tf[tf.date <= mid]["points"].sum() * inst.point_value
    h2 = tf[tf.date > mid]["points"].sum() * inst.point_value
    srt = daily.sort_values(ascending=False)
    tot = daily.sum()
    rows4.append(dict(market=m, ccy=inst.currency, half1=h1, half2=h2,
                      top5=srt.head(5).sum() / tot * 100,
                      top10=srt.head(10).sum() / tot * 100,
                      top20=srt.head(20).sum() / tot * 100,
                      sessions=len(daily), pct_days_pos=(daily > 0).mean() * 100,
                      median_trade_R=float(tf["r"].median())))
    daily.to_frame("money").to_csv(f"results/xm_daily_{m}.csv")
    print(f"       1st half {h1:>10,.0f} | 2nd half {h2:>10,.0f} | "
          f"top 5 days {rows4[-1]['top5']:5.1f}% | top 20 days {rows4[-1]['top20']:5.1f}% "
          f"of all profit", flush=True)
pd.DataFrame(rows4).to_csv("results/xm_stability.csv", index=False)
print("\nwrote results/xm_*.csv")
