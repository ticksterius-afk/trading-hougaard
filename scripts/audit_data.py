import pandas as pd, numpy as np, sys
from pathlib import Path
MD = Path.home()/ "mnt" / "Market Data"

def load(p, tz):
    df = pd.read_csv(p)
    df['ts'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert(tz)
    df = df.sort_values('ts').drop_duplicates('ts').set_index('ts')
    return df[['open','high','low','close']]

def audit(name, p, tz):
    df = load(p, tz)
    print(f"\n{'='*70}\n{name}  ({p.name})")
    print(f"  rows={len(df):,}  {df.index[0]} -> {df.index[-1]}")
    g = df.groupby(df.index.date)
    print(f"  trading days={g.ngroups:,}")
    # session open bar presence at 09:00 local
    t = df.index.strftime('%H:%M')
    for probe in ['09:00','09:15','09:20','09:30']:
        n = (t==probe).sum()
        print(f"  bars at {probe} local: {n:,}")
    # overnight gaps (roll detection) on session-open bar vs prior day close
    daily = g.agg(o=('open','first'), c=('close','last'))
    gap = (daily['o'] - daily['c'].shift()).dropna()
    print(f"  overnight gap: mean={gap.mean():.2f} std={gap.std():.2f} "
          f"|gap|>100: {(gap.abs()>100).sum()}  max|gap|={gap.abs().max():.1f}")
    big = gap[gap.abs()>150]
    if len(big): print(f"   biggest gaps: {list(zip(big.abs().nlargest(5).index.astype(str), big.abs().nlargest(5).round(0)))}")
    # price granularity
    px = df['close'].to_numpy()
    frac = np.abs(px - np.round(px))
    print(f"  integer prices: {(frac<1e-9).mean()*100:.1f}%")
    # bar range stats for the 4th 5-min bar of session (09:15-09:20)
    return df

audit("DAX futures ETH 5m", MD/"5min_ETH/DAX_5min_ETH.csv", "Europe/Berlin")
audit("DAX cash RTH 5m",    MD/"5min_RTH/DAX_5min_RTH.csv", "Europe/Berlin")
audit("DAX cash RTH long",  MD/"5min_RTH/DAX_5min_RTH_long.csv", "Europe/Berlin")
