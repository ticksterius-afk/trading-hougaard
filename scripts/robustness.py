"""Does the effect survive outside the sample Hougaard looked at?

Three questions:
  1. Does it hold on 14 years of DAX rather than 5?
  2. Is it stable year by year, or was it one good stretch?
  3. Does it show up on other index futures, or is it a DAX quirk?
"""
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE={}

def run(label, **kw):
    c = Config(label=label, **kw)
    e = Engine(c).load(CACHE).run()
    inst = instruments.get(c.instrument)
    s = metrics.summarise(e.trades, len(e.days), inst.point_value, label)
    s.update(metrics.bootstrap_ci(e.trades))
    return e, s

KEEP = ("label","sessions","trades","total_points","points_per_trade","win_rate",
        "avg_win","avg_loss","profit_factor","expectancy_R","sharpe","t_stat",
        "max_dd_points","boot_p05","boot_prob_positive","total_money")

# ---------------------------------------------------- 1) long DAX history
print("=== DAX cash index, 2012-2026 ===")
rows=[]
for lbl, kw in [
    ("ASRS_bar4_cash14y", dict(strategy="asrs", signal_bar=4)),
    ("SRS_15m_bar2_cash14y", dict(strategy="srs", signal_bar=2)),
]:
    e,s = run(lbl, instrument="DAX", data_key="cash_long", buffer=2.0,
              stop_mode="opposite", entry_window_minutes=120, spread=0.9,
              intrabar="bar_direction", **kw)
    rows.append({k:s.get(k) for k in KEEP}); print(rows[-1], flush=True)
    if lbl.startswith("ASRS"):
        yr = metrics.yearly(e.trades); print(yr.to_string())
        yr.to_csv("results/dax_cash_yearly.csv")

# ------------------------------------------------- 2) DAX futures by year
print("\n=== DAX futures by year (the primary series) ===")
e,s = run("ASRS_bar4_fut", instrument="DAX", data_key="fut_eth", buffer=2.0,
          strategy="asrs", signal_bar=4, stop_mode="opposite",
          entry_window_minutes=120, spread=0.9)
yr = metrics.yearly(e.trades); print(yr.to_string()); yr.to_csv("results/dax_fut_yearly.csv")

# --------------------------------------------------- 3) other instruments
print("\n=== other markets, same rules, buffer = 0.8% of average daily range ===")
for name in ("DAX","NQ","ES","YM","FTSE","GC"):
    for strat, bar in (("asrs",4), ("srs",2)):
        try:
            e,s = run(f"{name}_{strat}{bar}", instrument=name, data_key="fut_eth",
                      strategy=strat, signal_bar=bar, buffer=0.008,
                      buffer_mode="atr_frac", stop_mode="opposite",
                      entry_window_minutes=120, intrabar="bar_direction")
            rows.append({k:s.get(k) for k in KEEP}); print(rows[-1], flush=True)
        except Exception as ex:
            print(name, strat, "ERROR", ex)
pd.DataFrame(rows).to_csv("results/robustness.csv", index=False)
print("\nwrote results/robustness.csv")
