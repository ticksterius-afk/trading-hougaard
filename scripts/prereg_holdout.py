"""Tests the two hypotheses of pre-registration #2 on the three holdout sets."""
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE={}; COMM={"DAX":5.0,"NQ":4.0}
SETS=[("A DAX cash 2020-26","DAX","cash_long","2020-01-01","2026-08-28"),
      ("B DAX futures",     "DAX","fut_eth",  None,        None),
      ("C NQ futures",      "NQ", "fut_eth",  None,        None)]

def go(mkt,key,f,t,**kw):
    inst=instruments.get(mkt); tick=inst.tick_size
    d=dict(instrument=mkt,data_key=key,strategy="srs",signal_bar=2,buffer=0.008,
           buffer_mode="atr_frac",stop_mode="opposite",tp_mode="none",
           entry_window_minutes=120,intrabar="bar_direction",spread=tick,
           slippage=tick,commission=COMM[mkt],date_from=f,date_to=t); d.update(kw)
    e=Engine(Config(label="h",**d)).load(CACHE).run()
    tf=metrics.trades_to_frame(e.trades)
    days=e.days_df.copy(); days["date"]=pd.to_datetime(days["date"])
    tf=tf.merge(days[["date","prev_dir","bar_dir"]],on="date",how="left")
    return tf, inst.point_value

print("="*78); print("H1  break aligned with the 1st 15-min bar vs against it"); print("="*78)
pool_a=[]; pool_b=[]; h1=[]
for nm,mkt,key,f,t in SETS:
    tf,pv=go(mkt,key,f,t); tf=tf[np.isfinite(tf.r)]
    a=tf[tf.side==tf.prev_dir]["r"]; b=tf[tf.side==-tf.prev_dir]["r"]
    se=np.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b)); d=a.mean()-b.mean()
    pool_a.append(a); pool_b.append(b); h1.append(d)
    print(f"  {nm:22s} with {a.mean():+.4f} (n={len(a):4d})  against {b.mean():+.4f} "
          f"(n={len(b):4d})  diff {d:+.4f}  t {d/se:+.2f}")
A=pd.concat(pool_a); B=pd.concat(pool_b)
se=np.sqrt(A.var(ddof=1)/len(A)+B.var(ddof=1)/len(B)); D=A.mean()-B.mean()
print(f"  {'POOLED HOLDOUT':22s} with {A.mean():+.4f} (n={len(A):4d})  against {B.mean():+.4f} "
      f"(n={len(B):4d})  diff {D:+.4f}  t {D/se:+.2f}")
print(f"  signs: {[round(x,3) for x in h1]}  -> all positive? {all(x>0 for x in h1)}")
print(f"  VERDICT H1: {'PASS' if all(x>0 for x in h1) and abs(D/se)>2.24 else 'FAIL'}"
      f"  (needs all 3 positive AND |t|>2.24)")

print("\n"+"="*78); print("H2  stop beyond the whole 09:00-09:30 range, money per trade"); print("="*78)
h2=[]
for nm,mkt,key,f,t in SETS:
    base,pv=go(mkt,key,f,t); both,_=go(mkt,key,f,t,stop_mode="both_bars")
    mb=base.points.sum()*pv/len(base); mo=both.points.sum()*pv/len(both)
    h2.append(mo-mb)
    print(f"  {nm:22s} opposite {mb:8.1f}/trade (n={len(base):4d}) | "
          f"both bars {mo:8.1f}/trade (n={len(both):4d}) | diff {mo-mb:+8.1f} "
          f"({(mo/mb-1)*100 if mb else float('nan'):+5.1f}%)")
print(f"  signs: {[round(x,1) for x in h2]}  -> all positive? {all(x>0 for x in h2)}")
print(f"  VERDICT H2: {'PASS' if all(x>0 for x in h2) else 'FAIL'}  (needs all 3 positive)")
