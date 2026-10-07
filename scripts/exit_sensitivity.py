"""The sensitivity that was missing: how much of the result is the exit rule?

Hougaard's paper specifies entries and a stop. It never specifies when you go
flat. The study assumed "hold to the cash close". This measures what that
assumption is worth, which turns out to be most of the result.
"""
import sys; sys.path.insert(0,'.')
import pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE={}; COMM={"DAX":5.0,"NQ":4.0}
def go(m,label,**kw):
    inst=instruments.get(m); t=inst.tick_size
    d=dict(instrument=m,data_key="fut_eth",strategy="asrs",signal_bar=4,buffer=0.008,
           buffer_mode="atr_frac",stop_mode="opposite",entry_window_minutes=120,
           intrabar="bar_direction",spread=t,slippage=t,commission=COMM[m])
    d.update(kw)
    e=Engine(Config(label=label,**d)).load(CACHE).run()
    return metrics.summarise(e.trades,len(e.days),inst.point_value,label)
rows=[]
for m,closes in (("DAX",["11:00","12:00","13:00","14:00","15:00","16:00","17:00","17:30","18:00","20:00"]),
                 ("NQ", ["11:00","12:00","13:00","14:00","15:00","16:00"])):
    print(f"\n=== {m}: forced flatten time (entry rule unchanged) ===")
    print(f"  {'flat at':>9s} {'per year':>11s} {'PF':>7s} {'t':>6s} {'maxDD':>10s}")
    for cl in closes:
        s=go(m,f"{m}_close_{cl}",session_close=cl)
        rows.append(dict(market=m,kind="session_close",setting=cl,**{k:s.get(k) for k in
            ("total_money","money_per_year","profit_factor","t_stat","max_dd_intraday_money","trades")}))
        star=" <- used in the reports" if (m=="DAX" and cl=="17:30") or (m=="NQ" and cl=="16:00") else ""
        print(f"  {cl:>9s} {s['money_per_year']:>11,.0f} {s['profit_factor']:>7.3f} "
              f"{s['t_stat']:>6.2f} {s['max_dd_intraday_money']:>10,.0f}{star}")
    print(f"  --- maximum hold measured from ENTRY instead ---")
    for mins in (60,120,180,240,360,None):
        s=go(m,f"{m}_hold_{mins}",time_exit_minutes=mins)
        rows.append(dict(market=m,kind="max_hold",setting=str(mins),**{k:s.get(k) for k in
            ("total_money","money_per_year","profit_factor","t_stat","max_dd_intraday_money","trades")}))
        lbl=f"{mins} min" if mins else "no limit"
        print(f"  {lbl:>9s} {s['money_per_year']:>11,.0f} {s['profit_factor']:>7.3f} "
              f"{s['t_stat']:>6.2f} {s['max_dd_intraday_money']:>10,.0f}")
pd.DataFrame(rows).to_csv("results/exit_sensitivity.csv",index=False)
print("\nwrote results/exit_sensitivity.csv")
