"""Does standing aside on narrow (or very wide) 4th bars help?

Hougaard: 'The bar range is uncharacteristically small - just 13 points. That is
a cause for concern.' This turns that instinct into a rule and measures it.
Note this is an IN-SAMPLE search: treat the best number as an upper bound.
"""
import sys; sys.path.insert(0,'.')
import pandas as pd, numpy as np
from engine import Config, Engine, metrics, instruments
CACHE={}; COMM={"DAX":5.0,"NQ":4.0}
def go(m,label,**kw):
    inst=instruments.get(m); t=inst.tick_size
    d=dict(instrument=m,data_key="fut_eth",strategy="asrs",signal_bar=4,buffer=0.008,
           buffer_mode="atr_frac",stop_mode="opposite",entry_window_minutes=120,
           intrabar="bar_direction",spread=t,slippage=t,commission=COMM[m]); d.update(kw)
    e=Engine(Config(label=label,**d)).load(CACHE).run()
    s=metrics.summarise(e.trades,len(e.days),inst.point_value,label)
    s["skipped"]=sum(v for k,v in e.skipped.items() if k!="no_signal_bar")
    return s
rows=[]
for m in ("DAX","NQ"):
    base=go(m,"base")
    print(f"\n=== {m} === baseline {base['total_money']:>10,.0f}  "
          f"({base['sessions']} sessions, {base['trades']} trades, t={base['t_stat']})")
    print(f"  {'rule':34s} {'money':>11s} {'/yr':>9s} {'days':>6s} {'trades':>7s} {'PF':>6s} {'t':>6s} {'DD':>10s}")
    print(f"  {'no filter':34s} {base['total_money']:>11,.0f} {base['money_per_year']:>9,.0f} "
          f"{base['sessions']:>6d} {base['trades']:>7d} {base['profit_factor']:>6.3f} "
          f"{base['t_stat']:>6.2f} {base['max_dd_intraday_money']:>10,.0f}")
    tests=[(f"skip range < {x:.0%} of ADR", dict(min_signal_range_adr=x)) for x in
           (0.02,0.03,0.04,0.05,0.06,0.08)]
    tests+=[(f"skip range > {x:.0%} of ADR", dict(max_signal_range_adr=x)) for x in (0.15,0.20,0.25)]
    tests+=[("skip <4% and >20% of ADR", dict(min_signal_range_adr=0.04,max_signal_range_adr=0.20))]
    tests+=[(f"use bar4+5 if bar4 < {x:.0%} ADR", dict(combine_if_range_below_atr_frac=x))
            for x in (0.03,0.04,0.05,0.06)]
    for nm,kw in tests:
        s=go(m,nm,**kw)
        rows.append(dict(market=m,rule=nm,**{k:s.get(k) for k in
            ("sessions","trades","total_money","money_per_year","profit_factor",
             "t_stat","max_dd_intraday_money","expectancy_R")}))
        print(f"  {nm:34s} {s['total_money']:>11,.0f} {s['money_per_year']:>9,.0f} "
              f"{s['sessions']-s['skipped']:>6d} {s['trades']:>7d} {s['profit_factor']:>6.3f} "
              f"{s['t_stat']:>6.2f} {s['max_dd_intraday_money']:>10,.0f}", flush=True)
pd.DataFrame(rows).to_csv("results/vol_filter.csv",index=False)
