"""Runs the pre-registered test families on ONE dataset.

Usage: python3 scripts/prereg_run.py <tag> <market> <data_key> [date_from] [date_to]
Writes results/prereg_<tag>.csv -- one row per declared hypothesis.
Purely mechanical: no interpretation, no selection.
"""
import sys, os
sys.path.insert(0, '.')
import numpy as np, pandas as pd
from engine import Config, Engine, metrics, instruments

TAG, MKT, KEY = sys.argv[1], sys.argv[2], sys.argv[3]
DFROM = sys.argv[4] if len(sys.argv) > 4 else None
DTO   = sys.argv[5] if len(sys.argv) > 5 else None
COMM  = {"DAX": 5.0, "NQ": 4.0, "ES": 4.0, "YM": 4.0}[MKT]
TICK  = instruments.get(MKT).tick_size
PV    = instruments.get(MKT).point_value
CACHE = {}

def cfg(**kw):
    d = dict(instrument=MKT, data_key=KEY, strategy="srs", signal_bar=2,
             buffer=0.008, buffer_mode="atr_frac", stop_mode="opposite",
             tp_mode="none", trail_mode="none", entry_window_minutes=120,
             intrabar="bar_direction", spread=TICK, slippage=TICK,
             commission=COMM, date_from=DFROM, date_to=DTO)
    d.update(kw)
    return Config(**d)

def run(label, **kw):
    e = Engine(cfg(label=label, **kw)).load(CACHE).run()
    tf = metrics.trades_to_frame(e.trades)
    return e, tf

def welch(a, b):
    """Difference in mean R between two groups, and how many standard errors
    that difference is from zero. No equal-variance assumption."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 5 or len(b) < 5:
        return np.nan, np.nan, len(a), len(b)
    se = np.sqrt(a.var(ddof=1)/len(a) + b.var(ddof=1)/len(b))
    d = a.mean() - b.mean()
    return d, (d/se if se > 0 else np.nan), len(a), len(b)

rows = []
def emit(family, hyp, diff, t, na, nb, extra=None):
    r = dict(dataset=TAG, family=family, hypothesis=hyp,
             diff_R=round(diff, 4) if np.isfinite(diff) else np.nan,
             t_stat=round(t, 3) if np.isfinite(t) else np.nan,
             n_in=na, n_out=nb)
    if extra: r.update(extra)
    rows.append(r)

# ============================================ one baseline run, then group
base_e, base_tf = run("baseline")
days = base_e.days_df.copy()
days["date"] = pd.to_datetime(days["date"])
tf = base_tf.merge(days[["date", "inside_bar", "body_frac", "bar_dir",
                         "prev_dir", "prev_range", "sig_range"]],
                   on="date", how="left")
tf.to_csv(f"results/prereg_trades_{TAG}.csv", index=False)
BASE_R = tf["r"].mean()
print(f"[{TAG}] baseline: {len(tf)} trades over {days.shape[0]} sessions, "
      f"mean R {BASE_R:+.4f}, money {tf.points.sum()*PV:,.0f}")

# --- T1: inside bar -------------------------------------------------------
ins = tf[tf.inside_bar == True]["r"]; oth = tf[tf.inside_bar == False]["r"]
emit("T1 inside bar", "bar2 inside bar1 vs not", *welch(ins, oth))

# --- T2: body fraction buckets -------------------------------------------
BUCKETS = [("trend  body>=0.70", 0.70, 1.01), ("strong body 0.50-0.70", 0.50, 0.70),
           ("mid    body 0.25-0.50", 0.25, 0.50), ("doji   body<0.25", -.01, 0.25)]
for nm, lo, hi in BUCKETS:
    m = (tf.body_frac >= lo) & (tf.body_frac < hi)
    emit("T2 body shape", nm, *welch(tf[m]["r"], tf[~m]["r"]))

# --- T3: bar1/bar2 direction pair x breakout side -------------------------
for d1, n1 in ((1, "bar1 up"), (-1, "bar1 dn")):
    for d2, n2 in ((1, "bar2 up"), (-1, "bar2 dn")):
        for sd, ns in ((1, "LONG break"), (-1, "SHORT break")):
            m = (tf.prev_dir == d1) & (tf.bar_dir == d2) & (tf.side == sd)
            same = tf[(tf.side == sd)]
            emit("T3 direction", f"{n1} / {n2} / {ns}",
                 *welch(tf[m]["r"], same[~same.index.isin(tf[m].index)]["r"]))

# --- T4: take profit as a share of a bar's range --------------------------
for which, key in (("bar1", "prev_range_mult"), ("bar2", "range_mult")):
    for pct in (0.30, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00):
        kw = {"tp_mode": key,
              ("tp_prev_range_mult" if which == "bar1" else "tp_range_mult"): pct}
        _, t2 = run(f"tp_{which}_{pct}", **kw)
        _d, _t, _na, _nb = welch(t2["r"], tf["r"])
        emit("T4 take profit", f"TP = {pct:.0%} of {which} range",
             t2["r"].mean() - BASE_R, _t, len(t2), len(tf),
             extra=dict(mean_R=round(t2["r"].mean(), 4),
                        win_rate=round((t2.points > 0).mean()*100, 1),
                        money=round(t2.points.sum()*PV)))

# --- T5: stop placement ---------------------------------------------------
for nm, sm in (("opposite trigger (baseline)", "opposite"),
               ("bar2 extreme, no buffer", "signal_bar"),
               ("bar1 extreme", "prev_bar"),
               ("bar1 midpoint", "prev_bar_mid"),
               ("bar2 midpoint", "signal_bar_mid"),
               ("both bars combined", "both_bars")):
    _, t2 = run(f"stop_{sm}", stop_mode=sm)
    if len(t2) == 0:
        emit("T5 stop placement", nm, np.nan, np.nan, 0, len(tf)); continue
    _d, _t, _na, _nb = welch(t2["r"], tf["r"])
    emit("T5 stop placement", nm, t2["r"].mean() - BASE_R, _t, len(t2), len(tf),
         extra=dict(mean_R=round(t2["r"].mean(), 4),
                    win_rate=round((t2.points > 0).mean()*100, 1),
                    avg_risk=round(t2.risk_points.mean(), 1),
                    money=round(t2.points.sum()*PV)))

df = pd.DataFrame(rows)
out = f"results/prereg_{TAG}.csv"
df.to_csv(out, index=False)
print(df.to_string(index=False))
print("wrote", out)
