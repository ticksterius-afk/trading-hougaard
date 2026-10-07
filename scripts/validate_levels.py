"""Find the days Hougaard quotes in the PDF and check our 4th 5-min bar matches.

If our bar indexing (4th 5-minute bar of the Frankfurt session = 09:15-09:20
local) is correct, the high/low pairs he prints should turn up on real dates
with a near-exact match.
"""
import sys, pandas as pd, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import instruments as I, data as D

QUOTED = [  # (high, low) as printed in the Advanced School Run PDF
    (15625, 15610), (15558, 15534), (15720, 15698), (15686, 15671),
    (15744, 15726), (15869, 15856), (15839, 15825), (15858, 15841),
    (15550, 15526), (15768, 15736),
]

dax = I.get("DAX")
for key in ("cash_long", "fut_eth"):
    raw = D.load_bars(dax.files[key], dax.tz)
    sess = D.sessionize(raw, dax)
    b5 = D.resample_from_open(sess, 5, dax)
    b4 = b5[b5["bar_no"] == 4].copy()
    print(f"\n===== {key}: {len(b4)} sessions with a 4th 5-min bar =====")
    for (qh, ql) in QUOTED:
        d = (b4["high"] - qh).abs() + (b4["low"] - ql).abs()
        j = d.idxmin()
        r = b4.loc[j]
        tag = "MATCH " if d[j] <= 6 else "      "
        print(f"{tag}quoted H={qh} L={ql}  ->  {r.session_date}  "
              f"H={r.high:.1f} L={r.low:.1f}  err={d[j]:.1f}")
