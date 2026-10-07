#!/usr/bin/env python3
"""CLI: python3 run.py config/xyz.yaml [--csv]"""
import sys, json, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from engine import Config, Engine, metrics, instruments

def run_cfg(cfg: Config, cache=None):
    e = Engine(cfg).load(cache).run()
    inst = instruments.get(cfg.instrument)
    s = metrics.summarise(e.trades, len(e.days), inst.point_value, cfg.label)
    s.update(metrics.bootstrap_ci(e.trades))
    s.update({f"skip_{k}": v for k, v in e.skipped.items()})
    return e, s

if __name__ == "__main__":
    path = Path(sys.argv[1])
    raw = yaml.safe_load(path.read_text())
    cfg = Config.from_dict(raw)
    e, s = run_cfg(cfg)
    print(json.dumps(s, indent=2, default=str))
    if "--csv" in sys.argv:
        out = Path("results") / f"{cfg.label}_trades.csv"
        metrics.trades_to_frame(e.trades).to_csv(out, index=False)
        print("wrote", out)
