import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments
CACHE={}; COMM={"DAX":5.0,"NQ":4.0,"ES":4.0,"YM":4.0}; FX={"DAX":1.08,"NQ":1,"ES":1,"YM":1}
MKTS=["DAX","NQ","ES","YM"]; series={}
for m in MKTS:
    inst=instruments.get(m); t=inst.tick_size
    c=Config(label=m,instrument=m,data_key="fut_eth",strategy="asrs",signal_bar=4,
             buffer=0.008,buffer_mode="atr_frac",stop_mode="opposite",
             entry_window_minutes=120,intrabar="bar_direction",
             spread=t,slippage=t,commission=COMM[m])
    e=Engine(c).load(CACHE).run(); tf=metrics.trades_to_frame(e.trades)
    series[m]=tf.groupby("date")["points"].sum()*inst.point_value*FX[m]
daily=pd.DataFrame(series).fillna(0.0)
print("Correlation of daily P&L (USD-equivalent):")
print(daily.corr().round(3).to_string())
print("\nShare of sessions where both DAX and NQ traded:",
      f"{((daily.DAX!=0)&(daily.NQ!=0)).mean()*100:.0f}%")
def stats(x,nm):
    eq=x.cumsum(); dd=float((np.maximum.accumulate(eq)-eq).max())
    sd=x.std(ddof=1); sh=x.mean()/sd*np.sqrt(252) if sd else np.nan
    t=x.mean()/(sd/np.sqrt(len(x))) if sd else np.nan
    print(f"  {nm:20s} {x.sum():>11,.0f}  /yr {x.mean()*252:>9,.0f}  maxDD {dd:>10,.0f}  "
          f"Sharpe {sh:5.2f}  t {t:5.2f}  ret/DD {x.sum()/dd if dd else np.nan:5.2f}")
    return dict(name=nm,total=x.sum(),per_year=x.mean()*252,dd=dd,sharpe=sh,t=t,
                ret_dd=x.sum()/dd if dd else np.nan)
print("\nEnd-of-day marked, 1 contract each:")
out=[stats(daily[m],m+" alone") for m in MKTS]
out.append(stats(daily.sum(axis=1),"ALL FOUR"))
out.append(stats(daily[["DAX","NQ"]].sum(axis=1),"DAX + NQ"))
out.append(stats(daily["NQ"],"NQ alone (again)"))
pd.DataFrame(out).to_csv("results/xm_portfolio.csv",index=False)
daily.to_csv("results/xm_portfolio_daily.csv")
# do the big days coincide?
tot=daily.sum(axis=1)
top=tot.nlargest(20).index
print(f"\nOn the 20 best combined days, how many markets were positive?")
print("  ", daily.loc[top].gt(0).sum(axis=1).value_counts().sort_index().to_dict())
print("\nBest 20 days as % of each market's own total:")
for m in MKTS:
    s=daily[m]; print(f"  {m:4s} {s.nlargest(20).sum()/s.sum()*100:6.1f}%")
