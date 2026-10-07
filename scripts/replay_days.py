"""Replay named sessions and print the engine's trade log, so it can be checked
line-by-line against Hougaard's written commentary."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Config, Engine

DAYS = ["2023-04-05","2023-04-06","2023-04-11","2023-04-12","2023-04-13",
        "2023-04-17","2023-04-18","2023-04-19","2023-04-27"]

cfg = Config(label="validation", instrument="DAX", data_key="cash_long",
             strategy="asrs", signal_bar=4, entry_mode="stop", buffer=2.0,
             stop_mode="opposite", tp_mode="none", trail_mode="none",
             entry_window_minutes=120, allow_flip=True,
             spread=0.0, slippage=0.0, intrabar="bar_direction",
             date_from="2023-04-01", date_to="2023-04-30")
e = Engine(cfg).load().run()
by_day = {}
for t in e.trades:
    by_day.setdefault(str(t.date), []).append(t)
rows = {str(r["date"]): r for _, r in e.days_df.iterrows()}

for d in DAYS:
    r = rows.get(d)
    if r is None:
        print(f"\n### {d}: no session"); continue
    print(f"\n### {d}  4th-bar H={r['sig_high']:.1f} L={r['sig_low']:.1f} "
          f"(range {r['sig_range']:.1f})  BUY>{r['buy_trigger']:.1f}  "
          f"SELL<{r['sell_trigger']:.1f}  risk={r['buy_trigger']-r['sell_trigger']:.1f}")
    for t in by_day.get(d, []):
        side = "LONG " if t.side == 1 else "SHORT"
        print(f"   #{t.seq} {side} @{t.entry_raw:8.1f} {str(t.entry_ts)[11:16]}"
              f" -> {t.exit_reason:14s} {str(t.exit_ts)[11:16]}"
              f"  P&L {t.points:+7.1f}   MFE {t.mfe:5.1f}  MAE {t.mae:5.1f}")
    if not by_day.get(d):
        print("   (no trade)")
