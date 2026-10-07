"""Run a named batch of configurations and write one summary row each."""
import sys, time, json, argparse
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import Config, ScaleLeg, Engine, metrics, instruments

CACHE = {}

def run_one(cfg: Config) -> dict:
    t0 = time.time()
    e = Engine(cfg).load(CACHE).run()
    inst = instruments.get(cfg.instrument)
    s = metrics.summarise(e.trades, len(e.days), inst.point_value, cfg.label)
    s.update(metrics.bootstrap_ci(e.trades))
    s["secs"] = round(time.time() - t0, 1)
    return s

def dax(**kw):
    d = dict(instrument="DAX", data_key="fut_eth", strategy="asrs",
             signal_bar=4, entry_mode="stop", buffer=2.0, stop_mode="opposite",
             tp_mode="none", trail_mode="none", entry_window_minutes=120,
             intrabar="bar_direction")
    d.update(kw)
    return Config(**d)

# ---------------------------------------------------------------- batches
def batch_baseline():
    out = []
    for sp in (0.0, 0.9, 2.0, 3.0):
        out.append(dax(label=f"A_cost_{sp}", spread=sp))
    for ib in ("pessimistic", "bar_direction", "optimistic"):
        out.append(dax(label=f"A_intrabar_{ib}", intrabar=ib))
    for w in (60, 120, 240, None):
        out.append(dax(label=f"A_window_{w}", entry_window_minutes=w))
    for m in (1, 2, 3, None):
        out.append(dax(label=f"A_maxentry_{m}", max_entries_per_day=m))
    for b in (0.0, 1.0, 2.0, 4.0, 8.0):
        out.append(dax(label=f"A_buffer_{b}", buffer=b))
    return out

def batch_variants():
    out = [
        dax(label="B_ASRS_bar4", signal_bar=4),
        dax(label="B_ASRS_bar5", signal_bar=5),
        dax(label="B_ASRS_bar3", signal_bar=3),
        dax(label="B_ASRS_bar6", signal_bar=6),
        dax(label="B_ASRS_bar4+5", signal_bar=4, combine_next_bar=True),
        dax(label="B_ASRS_bar4_cond_atr08", signal_bar=4,
            combine_if_range_below_atr_frac=0.08),
        dax(label="B_ASRS_bar4_cond_atr12", signal_bar=4,
            combine_if_range_below_atr_frac=0.12),
        dax(label="B_SRS_15m_bar2", strategy="srs", signal_bar=2),
        dax(label="B_SRS_15m_bar1", strategy="srs", signal_bar=1),
        dax(label="B_SRS_15m_bar3", strategy="srs", signal_bar=3),
        dax(label="B_SRS_15m_bar2_win240", strategy="srs", signal_bar=2,
            entry_window_minutes=240),
        dax(label="C_entry_close_bar4", entry_mode="close"),
        dax(label="C_entry_close_SRS", strategy="srs", signal_bar=2,
            entry_mode="close"),
        dax(label="D_longonly", direction="long"),
        dax(label="D_shortonly", direction="short"),
        dax(label="D_noflip", allow_flip=False),
    ]
    return out

def batch_exits():
    out = []
    for p in (10, 15, 20, 25, 30, 40, 60):
        out.append(dax(label=f"E_trailpts_{p}", trail_mode="points", trail_points=p))
    for r in (0.5, 0.75, 1.0, 1.5, 2.0):
        out.append(dax(label=f"E_trailR_{r}", trail_mode="r_multiple", trail_r=r))
    for a in (0.08, 0.12, 0.16, 0.25, 0.4):
        out.append(dax(label=f"E_trailATR_{a}", trail_mode="atr", trail_atr_mult=a))
    for n in (1, 2, 3, 5, 8):
        out.append(dax(label=f"E_trailbar_{n}", trail_mode="prior_bar", trail_prior_bars=n))
    for r in (0.5, 1.0, 1.5):
        out.append(dax(label=f"E_trailR1_act{r}", trail_mode="r_multiple",
                       trail_r=1.0, trail_activate_at_r=r))
    for r in (0.5, 1.0, 1.5, 2.0):
        out.append(dax(label=f"E_BE_{r}R", breakeven_at_r=r))
    for r in (1.0, 1.5, 2.0, 3.0, 5.0):
        out.append(dax(label=f"E_TP_{r}R", tp_mode="r_multiple", tp_r=r))
    out.append(dax(label="E_none_baseline"))
    for m in (60, 120, 240):
        out.append(dax(label=f"E_timeexit_{m}", time_exit_minutes=m))
    return out

def batch_scaling():
    out = []
    for r in (1.0, 1.5, 2.0):
        out.append(dax(label=f"F_scaleout50_{r}R",
                       scale_out=[ScaleLeg(r, 0.5)]))
        out.append(dax(label=f"F_scaleout50_{r}R_BE",
                       scale_out=[ScaleLeg(r, 0.5)],
                       breakeven_after_first_scale_out=True))
    out.append(dax(label="F_scaleout_1R_2R",
                   scale_out=[ScaleLeg(1.0, 0.34), ScaleLeg(2.0, 0.33)]))
    out.append(dax(label="F_scaleout_1R_2R_BE",
                   scale_out=[ScaleLeg(1.0, 0.34), ScaleLeg(2.0, 0.33)],
                   breakeven_after_first_scale_out=True))
    for r in (0.5, 1.0, 2.0):
        out.append(dax(label=f"F_scalein50_{r}R", scale_in=[ScaleLeg(r, 0.5)]))
        out.append(dax(label=f"F_scalein50_{r}R_BEavg",
                       scale_in=[ScaleLeg(r, 0.5)], scale_in_stop="breakeven_avg"))
    out.append(dax(label="F_scaleout50_1R_trail20",
                   scale_out=[ScaleLeg(1.0, 0.5)], trail_mode="points",
                   trail_points=20))
    return out

BATCHES = dict(baseline=batch_baseline, variants=batch_variants,
               exits=batch_exits, scaling=batch_scaling)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    a = ap.parse_args()
    cfgs = BATCHES[a.batch]()
    rows = []
    for i, c in enumerate(cfgs, 1):
        r = run_one(c)
        rows.append(r)
        print(f"[{i}/{len(cfgs)}] {c.label:28s} pts={r.get('total_points',0):9.1f} "
              f"trades={r.get('trades',0):5d} PF={r.get('profit_factor',0):.3f} "
              f"({r['secs']}s)", flush=True)
    df = pd.DataFrame(rows)
    out = ROOT / "results" / f"sweep_{a.batch}.csv"
    df.to_csv(out, index=False)
    print("wrote", out)
