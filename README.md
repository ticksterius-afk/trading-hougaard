# School Run / Advanced School Run — configurable backtest engine

A configurable engine for testing Tom Hougaard's **School Run Strategy (SRS)** and
**Advanced School Run Strategy (ASRS)**, plus anything in the same family, on any
instrument you have 5-minute OHLC data for.

## The strategies as written

| | School Run (SRS) | Advanced School Run (ASRS) |
|---|---|---|
| Chart | 15-minute | 5-minute |
| Signal bar | 2nd bar of the session (09:15–09:30 Frankfurt) | 4th bar (09:15–09:20), sometimes the 5th |
| Buy order | stop order 2 points above the signal bar's high | same |
| Sell order | stop order 2 points below the signal bar's low | same |
| Stop loss | the opposite order's level — so a stop-out **flips** you | same |
| Target | none | none |

## Quick start

```bash
python3 run.py config/dax_asrs_baseline.yaml --csv     # one configuration
python3 scripts/sweep.py exits                          # a batch of configurations
python3 tests/test_engine.py                            # 18 correctness tests
```

## Configuration

Every knob lives in `engine/config.py`. The ones you asked for:

**Entry** — `entry_mode: stop` places a resting stop order `buffer` beyond the
signal bar (Hougaard's own method). `entry_mode: close` instead waits for a
5-minute bar to *close* beyond the trigger and enters on that close.
`buffer_mode` can be fixed `points`, a fraction of the signal bar's range
(`range_frac`), or a fraction of the average daily range (`atr_frac`, which is
how you compare markets of different sizes fairly).

**Stop loss** — `stop_mode` is one of `opposite` (Hougaard's), `signal_bar`,
`points`, `atr` (a multiple of average daily range) or `range_mult` (a multiple
of the signal bar's range). `min_stop_points` / `max_stop_points` floor and cap
the risk, and `max_stop_points` can skip a day whose range is too wide to trade.

**Take profit** — `tp_mode` is `none` (Hougaard's), `points`, `r_multiple`
(a multiple of the initial risk) or `range_mult`.

**Trade management** — `breakeven_at_r` / `breakeven_at_points` move the stop to
entry once the trade is far enough ahead. `trail_mode` is `points`,
`r_multiple`, `atr` or `prior_bar` (stop under the low of the last N bars),
with `trail_activate_at_r` to delay trailing until the trade is already
working, and `trail_update` to choose whether the trail tightens once per
completed bar or continuously.

**Scaling** — `scale_out: [{trigger_r: 1.0, size: 0.5}]` sells half the position
once it is 1R in front. `scale_in` adds size on the same schedule.
`breakeven_after_first_scale_out` and `scale_in_stop: breakeven_avg` handle the
stop after a partial.

**Re-entry** — `allow_flip` (stopped out → reverse), `max_entries_per_day`,
`reenter_same_direction`, `entry_window_minutes` (Hougaard works the first two
hours), `entry_window_after_signal`, `direction` (both / long / short).

**Costs** — `spread` (round trip, in points) and `slippage` (extra adverse
points on every stop-type fill, charged on entry *and* exit).

**Other instruments** — add an `Instrument` to `engine/instruments.py` with its
timezone, session open/close, tick size and point value, then set
`instrument:` in the config. DAX, NQ, ES, YM, FTSE and GC are already defined.

## How a bar is simulated

We only have 5-minute bars, so when several of our price levels sit inside one
bar the engine has to assume the order price visited them. It walks a three-leg
path — `open → low → high → close` on an up bar, the reverse on a down bar —
and fires each resting order as the path crosses it. `intrabar: pessimistic`
forces the adverse ordering; `optimistic` gives the unreachable upper bound.
An order that price is already past fills at the current price, not at its
level, so gaps through a trigger fill at the open.

`scripts/calibrate_intrabar.py` measures how much this assumption actually
costs, by re-running NQ on true 1-minute data (see FINDINGS.md).

## Limitations

- **Intraday only.** Any position still open on the last bar of the session is
  closed at that bar's close. Overnight carry would need out-of-session bars,
  which `sessionize` deliberately removes.
- **No intrabar path below the bar size**, except where `exec_data_key` points
  at a finer series (only NQ has 1-minute history here).
- **The DAX futures file is back-adjusted**, so price *levels* before 2026 are
  offset from the real contract. Point moves inside a day are unaffected, which
  is all this engine uses — but do not read the absolute prices as real.
- **`intrabar: optimistic` is not a strict upper bound** in the rare case where
  a stop and a target sit at exactly the same price; the stop still wins.

## Layout

```
engine/     config.py  instruments.py  data.py  engine.py  metrics.py
scripts/    audit_data  validate_levels  replay_days  sweep  calibrate_intrabar
            null_signalbar  robustness  final_analysis
tests/      test_engine.py     18 hand-built cases with known answers
config/     yaml configurations
results/    csv output from every run
data/       NQ_1min_combined.csv (derived; built by scripts)
```
