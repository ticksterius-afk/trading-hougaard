"""How much does the 5-minute intrabar guess actually cost us?

NQ is the only market here with 1-minute history, so we run the identical
strategy three ways on the SAME sessions:
  * 5-min bars, each of the three intrabar assumptions
  * 1-minute bars as the execution path (25x more path detail)
and see which 5-minute assumption tracks the 1-minute answer.
"""
import sys; sys.path.insert(0, '.')
import pandas as pd
from engine import Config, Engine, metrics, instruments

FROM, TO = "2025-08-25", "2026-08-25"
rows = []
def go(label, **kw):
    c = Config(label=label, instrument="NQ", data_key="fut_eth", signal_bar=4,
               buffer=5.0, stop_mode="opposite", entry_window_minutes=120,
               spread=0.25, date_from=FROM, date_to=TO, **kw)
    e = Engine(c).load().run()
    s = metrics.summarise(e.trades, len(e.days), 1.0, label)
    rows.append({k: s.get(k) for k in
                 ("label","sessions","trades","total_points","points_per_trade",
                  "win_rate","profit_factor","max_dd_points")})
    print(rows[-1], flush=True)

for ib in ("pessimistic", "bar_direction", "optimistic"):
    go(f"5min_{ib}", intrabar=ib)
go("1min_path", exec_data_key="fut_1m", intrabar="bar_direction")
go("1min_path_pess", exec_data_key="fut_1m", intrabar="pessimistic")
pd.DataFrame(rows).to_csv("results/calibration_intrabar.csv", index=False)
print("\n", pd.DataFrame(rows).to_string(index=False))
