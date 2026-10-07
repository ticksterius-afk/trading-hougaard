"""Does conditioning on the VOLATILITY REGIME help?

The strategy has a long-volatility payoff: it wins on big-move days in either
direction and bleeds on quiet ones. The obvious follow-up is to trade only when
the market has recently been lively. `regime` = average daily range of the last
14 sessions / that of the last 100, both using prior days only.
This is an IN-SAMPLE search: treat any improvement as an upper bound.
"""
import sys; sys.path.insert(0, '.')
import pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE = {}
COMM = {"DAX": 5.0, "NQ": 4.0, "ES": 4.0, "YM": 4.0}

def go(m, label, **kw):
    inst = instruments.get(m); t = inst.tick_size
    d = dict(instrument=m, data_key="fut_eth", strategy="asrs", signal_bar=4,
             buffer=0.008, buffer_mode="atr_frac", stop_mode="opposite",
             entry_window_minutes=120, intrabar="bar_direction",
             spread=t, slippage=t, commission=COMM[m])
    d.update(kw)
    e = Engine(Config(label=label, **d)).load(CACHE).run()
    s = metrics.summarise(e.trades, len(e.days), inst.point_value, label)
    # days actually traded = sessions that produced at least one trade
    s["traded_days"] = int(metrics.trades_to_frame(e.trades)["date"].nunique())
    return s

if __name__ == "__main__":
    rows = []
    for m in ("DAX", "NQ"):
        print(f"\n=== {m}: volatility regime filter ===")
        print(f"  {'rule':32s} {'money':>11s} {'/yr':>9s} {'days':>6s} {'PF':>6s} "
              f"{'t':>6s} {'R':>8s} {'DD':>10s}")
        tests = [("trade every day", {})]
        tests += [(f"only when regime > {x:.2f}", dict(min_vol_regime=x))
                  for x in (0.9, 1.0, 1.1, 1.2, 1.3)]
        tests += [(f"only when regime < {x:.2f}", dict(max_vol_regime=x))
                  for x in (0.9, 1.0, 1.1)]
        for nm, kw in tests:
            s = go(m, nm, **kw)
            rows.append(dict(market=m, rule=nm, **{k: s.get(k) for k in
                ("traded_days", "trades", "total_money", "money_per_year",
                 "profit_factor", "t_stat", "expectancy_R",
                 "max_dd_intraday_money", "sharpe")}))
            print(f"  {nm:32s} {s['total_money']:>11,.0f} {s['money_per_year']:>9,.0f} "
                  f"{s['traded_days']:>6d} {s['profit_factor']:>6.3f} {s['t_stat']:>6.2f} "
                  f"{s['expectancy_R']:>8.4f} {s['max_dd_intraday_money']:>10,.0f}", flush=True)
    pd.DataFrame(rows).to_csv("results/vol_regime.csv", index=False)
