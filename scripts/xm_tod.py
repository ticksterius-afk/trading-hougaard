import sys; sys.path.insert(0, '.')
import numpy as np, pandas as pd, os
from engine import Config, Engine, metrics, instruments
CACHE={}; COMM={"DAX":5.0,"NQ":4.0,"ES":4.0,"YM":4.0}
OUT="results/xm_tod.csv"
for m in sys.argv[1:]:
    inst=instruments.get(m); t=inst.tick_size; rows=[]
    for n in range(1,49):
        c=Config(label=f"{m}_b{n}",instrument=m,data_key="fut_eth",strategy="asrs",
                 signal_bar=n,buffer=0.008,buffer_mode="atr_frac",stop_mode="opposite",
                 entry_window_minutes=None,entry_window_after_signal=90,
                 intrabar="bar_direction",spread=t,slippage=t,commission=COMM[m])
        e=Engine(c).load(CACHE).run()
        s=metrics.summarise(e.trades,len(e.days),inst.point_value,c.label)
        mins=(n-1)*5; oh,om=divmod(mins,60)
        rows.append(dict(market=m,bar=n,mins_after_open=mins,clock=f"+{oh}:{om:02d}",
                         money=s.get("total_money",0),t=s.get("t_stat",np.nan),
                         pf=s.get("profit_factor",np.nan),trades=s.get("trades",0)))
    d=pd.DataFrame(rows)
    d.to_csv(OUT,mode="a",header=not os.path.exists(OUT),index=False)
    b4=float(d[d.bar==4].money.iloc[0]); rank=(d.money<b4).mean()*100
    h=[d[(d.mins_after_open>=a)&(d.mins_after_open<a+60)].money.mean() for a in (0,60,120,180)]
    print(f"{m:4s} bar4={b4:>10,.0f} ({rank:.0f}th pct) | h1 {h[0]:>9,.0f} h2 {h[1]:>9,.0f} "
          f"h3 {h[2]:>9,.0f} h4 {h[3]:>9,.0f} | best bar {int(d.loc[d.money.idxmax(),'bar'])} "
          f"({d.loc[d.money.idxmax(),'clock']}) = {d.money.max():,.0f}", flush=True)
