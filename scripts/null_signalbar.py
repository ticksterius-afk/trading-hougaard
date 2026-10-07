"""Falsification test: is the 4th 5-minute bar actually special?

We run the identical strategy using every 5-minute bar of the session as the
breakout box, giving each one the same amount of time to work (90 minutes from
the end of the signal bar). If bar 4 is genuinely special it should stand out
from the crowd. If it just sits inside the pack, the 'School Run' is really
'open-range breakouts work on the DAX', and the specific bar is decoration.
"""
import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics

CACHE={}
rows=[]
for n in range(1, 49):          # 09:00 -> 13:00
    c = Config(label=f"bar{n}", instrument="DAX", data_key="fut_eth",
               signal_bar=n, buffer=2.0, stop_mode="opposite",
               entry_window_minutes=None, entry_window_after_signal=90,
               spread=0.9, intrabar="bar_direction")
    e = Engine(c).load(CACHE).run()
    s = metrics.summarise(e.trades, len(e.days), 1.0, c.label)
    rows.append(dict(bar=n, clock=f"{9+((n-1)*5)//60:02d}:{((n-1)*5)%60:02d}",
                     trades=s.get('trades',0), points=s.get('total_points',0),
                     ppt=s.get('points_per_trade',0), pf=s.get('profit_factor',0),
                     sharpe=s.get('sharpe',np.nan), t=s.get('t_stat',np.nan)))
    print(rows[-1], flush=True)
df=pd.DataFrame(rows); df.to_csv("results/null_signalbar.csv", index=False)
p=df.points.to_numpy()
b4=float(df[df.bar==4].points.iloc[0])
print(f"\nbar 4 = {b4:.0f} points")
print(f"all 48 bars: median {np.median(p):.0f}  mean {p.mean():.0f}  sd {p.std(ddof=1):.0f}")
print(f"percentile rank of bar 4: {(p<b4).mean()*100:.0f}th")
print(f"bars beating bar 4: {(p>b4).sum()} of 48")
