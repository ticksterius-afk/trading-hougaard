"""Confirms pre-registration #1's T4 PREDICTION ('all targets reduce expectancy')
across the holdouts. This is checking a negative that was predicted in advance,
not searching for a target that works."""
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE={}; COMM={"DAX":5.0,"NQ":4.0}
SETS=[("DAX cash 12-19 (discovery)","DAX","cash_long","2012-11-05","2019-12-31"),
      ("DAX cash 20-26","DAX","cash_long","2020-01-01","2026-08-28"),
      ("DAX futures","DAX","fut_eth",None,None),
      ("NQ futures","NQ","fut_eth",None,None)]
def go(mkt,key,f,t,**kw):
    inst=instruments.get(mkt); tick=inst.tick_size
    d=dict(instrument=mkt,data_key=key,strategy="srs",signal_bar=2,buffer=0.008,
           buffer_mode="atr_frac",stop_mode="opposite",tp_mode="none",
           entry_window_minutes=120,intrabar="bar_direction",spread=tick,
           slippage=tick,commission=COMM[mkt],date_from=f,date_to=t); d.update(kw)
    e=Engine(Config(label="t",**d)).load(CACHE).run()
    tf=metrics.trades_to_frame(e.trades)
    return tf, inst.point_value
PCTS=[0.30,0.50,0.75,1.00,1.50,2.00,3.00]
rows=[]
print(f"{'dataset':28s} {'target':>22s} {'win rate':>9s} {'mean R':>8s} {'vs no target':>13s}")
for nm,mkt,key,f,t in SETS:
    base,pv=go(mkt,key,f,t); bR=base.r.mean()
    print(f"{nm:28s} {'NONE (Hougaard)':>22s} {(base.points>0).mean()*100:8.1f}% "
          f"{bR:+8.4f} {'--':>13s}")
    for p in PCTS:
        tf,_=go(mkt,key,f,t,tp_mode="range_mult",tp_range_mult=p)
        rows.append(dict(dataset=nm,pct=p,win=(tf.points>0).mean()*100,
                         meanR=tf.r.mean(),delta=tf.r.mean()-bR,
                         money=tf.points.sum()*pv))
        r=rows[-1]
        print(f"{'':28s} {f'{p:.0%} of signal range':>22s} {r['win']:8.1f}% "
              f"{r['meanR']:+8.4f} {r['delta']:+13.4f}")
d=pd.DataFrame(rows); d.to_csv("results/prereg_tp_confirm.csv",index=False)
print("\nPrediction was: win rate rises monotonically, expectancy falls monotonically.")
for nm in d.dataset.unique():
    g=d[d.dataset==nm].sort_values("pct")
    wm=(g.win.diff().dropna()<=0).all(); rm=(g.meanR.diff().dropna()>=0).all()
    print(f"  {nm:28s} win rate falls as target widens: {str(wm):5s} | "
          f"expectancy rises as target widens: {str(rm):5s} | "
          f"any target beats no target: {str((g.delta>0).any()):5s}")
