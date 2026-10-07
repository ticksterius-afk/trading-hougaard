import pandas as pd, numpy as np
from pathlib import Path
MD = Path.home()/"mnt"/"Market Data"
def load(p):
    df=pd.read_csv(p); df['ts']=pd.to_datetime(df['time'],unit='s',utc=True).dt.tz_convert('Europe/Berlin')
    return df.sort_values('ts').drop_duplicates('ts').set_index('ts')[['open','high','low','close']]
e=load(MD/"5min_ETH/DAX_5min_ETH.csv"); c=load(MD/"5min_RTH/DAX_5min_RTH_long.csv")
j=e.join(c,how='inner',lsuffix='_e',rsuffix='_c')
j['off']=j['close_e']-j['close_c']
d=j.resample('D')['off'].median().dropna()
print("offset (futures - cash), daily median, sampled:")
print(d.iloc[::60].round(1).to_string())
print("\nnum distinct offset 'levels' (rounded to 5):", d.round(-0).diff().abs().gt(20).sum(), "jumps >20pts")
jm=d[d.diff().abs()>20]
print("jump dates:\n", jm.round(0).to_string())
# intraday structure check: 09:15-09:20 bar range, futures vs cash
b=j[(j.index.strftime('%H:%M')=='09:15')]
print("\n4th-bar range  futures mean %.2f  cash mean %.2f  corr %.3f  n=%d"%(
  (b.high_e-b.low_e).mean(),(b.high_c-b.low_c).mean(),
  np.corrcoef(b.high_e-b.low_e,b.high_c-b.low_c)[0,1],len(b)))
