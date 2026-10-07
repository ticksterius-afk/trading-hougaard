# Verification handoff — School Run / Advanced School Run study

**You are verifying this work, not continuing it. Your job is to break it.**

Three rounds of research produced a configurable backtest engine and a set of
claims about Tom Hougaard's School Run (SRS) and Advanced School Run (ASRS)
strategies. Two subagent audits have already run and found two real bugs. This
handoff exists so a fresh session can attack the whole thing independently.

---

## 0. Read this first — anti-anchoring protocol

The previous session wrote three report artifacts and three findings docs in the
claude.ai project. **Do not read any of them until you have produced your own
numbers.** They contain a narrative that will anchor you. The claims you need to
check are listed in section 4 of this file, stated as bare numbers with no
supporting argument, deliberately.

Order of work:
1. Build your own understanding from the raw data and the strategy rules (§2).
2. Re-derive the claims in §4 independently.
3. Only then read the reports, and report any claim you cannot reproduce.

The prior session's conclusions are a hypothesis to be tested, not context to be
absorbed. If you find yourself explaining why a discrepancy is fine, stop and
report the discrepancy.

---

## 1. Environment

- Repo: `C:\Users\andrz\Documents\_building_with_Claude\Trading Hougaard`
  (mounted at `$HOME/mnt/Trading Hougaard` for `device_bash`)
- Market data: `C:\Users\andrz\Downloads\Market Data`
  (mounted at `$HOME/mnt/Market Data`)
- Use `mcp__remote-devices__device_bash`. Python 3.10, pandas 2.3, numpy 2.2 are
  installed there. 2 cores, 3 GB RAM. Each call is a fresh shell, 180s max.
- Do NOT write scratch work into the repo. Use `$HOME/verify/` (outside `mnt/`).
- Run the existing suite first: `cd "$HOME/mnt/Trading Hougaard" && python3 tests/test_engine.py`
  (22 checks; all should pass). A failure here is itself a finding.

### Data files
| File | What it is | Rows | Period |
|---|---|---|---|
| `5min_ETH/DAX_5min_ETH.csv` | DAX futures, **back-adjusted continuous** | 302k | 2021-08 → 2026-08 |
| `5min_RTH/DAX_5min_RTH_long.csv` | DAX **cash index**, 09:00–17:30 Frankfurt | 364k | 2012-11 → 2026-08 |
| `5min_RTH/DAX_5min_RTH.csv` | DAX cash index, shorter | 88k | 2023-04 → 2026-08 |
| `5min_ETH/{NQ,ES,YM,FTSE,GC}_5min_ETH.csv` | futures, same format | | 2021-08 → 2026-08 |
| `1min_ETH/NQ/*.csv` | NQ 1-minute (18 files, heavily duplicated) | 355k unique | 2025-08 → 2026-08 |
| `data/NQ_1min_combined.csv` | derived: deduplicated concatenation of the above | | |

Format: `time,open,high,low,close` where `time` is a unix timestamp in seconds,
UTC, marking the **start** of the bar.

---

## 2. The strategies, as stated in the source PDF

The PDF `Advanced School Run Strategy.pdf` is attached to the claude.ai project
(read it with the Projects tool, not from disk). Reading it is encouraged — it is
the primary source and the previous session's reading of it is itself checkable.

- **SRS**: 15-minute chart. Signal bar = 2nd bar of the Frankfurt cash session
  (09:15–09:30 local). Buy stop 2 points above its high, sell stop 2 points below
  its low. Stop-loss = the opposite order's level, so a stop-out **flips** you
  into the opposite position. No profit target.
- **ASRS**: identical, but a 5-minute chart and the 4th bar (09:15–09:20),
  sometimes the 5th.
- Hougaard works "the first two hours" and uses a 0.9-point spread-bet spread.

Note: the SRS rules above were **reconstructed** by the previous session from
references inside the ASRS paper; the original School Run PDF was never supplied.
The user confirmed the reconstruction. Treat it as an assumption to sanity-check
against the PDF text, not as ground truth.

---

## 3. The single most valuable thing you can do

**Write your own backtester from scratch and compare.**

Do not read `engine/engine.py` first. From the rules in §2 and the raw CSV,
implement the ASRS on DAX futures independently — your own session slicing, your
own bar indexing, your own fill logic — and produce: total points, trade count,
win rate, profit factor. Then compare against claim C1 below.

Two independent implementations agreeing is far stronger evidence than any
amount of code review. If they disagree, find out which is wrong; that is the
highest-value outcome of this session.

Only after that should you read the engine and review it directly.

---

## 4. Claims to verify

Stated as bare numbers. No justification is given on purpose. All "realistic
costs" below mean 1 tick spread + 1 tick slippage on stop fills + commission
(EUR 5 per round turn for DAX, USD 4 for US index futures).

### Core backtest
- **C1** DAX futures, ASRS 4th 5-min bar, 2-point buffer, stop = opposite trigger,
  no target, entry window 120 min, unlimited flips, 0.9 spread, bar-direction
  intrabar model: **+9,317.7 points, 2,707 trades, profit factor 1.138,
  win rate 21.5%, avg win +132.1, avg loss −31.9.**
- **C2** Same but intrabar = "pessimistic": **−1,196.3 points.** (The sign flip
  is the point. Verify the pessimistic model is implemented coherently and is not
  simply broken.)
- **C3** DAX cash index 2012–2026, same rules: **+36,277.3 points, PF 1.291,
  t-stat 6.55, positive in 14 of 15 years.**

### The intrabar realism calibration (the study's biggest modelling choice)
- **C4** NQ, 259 sessions, 2025-08 → 2026-08. 5-min bar-direction **+1,684.5**;
  true 1-minute execution path **+1,516.5** (90%); 1-minute pessimistic **+977.0**
  (58%); 5-min pessimistic **−843.5**.
- The study then applies a **58–90% haircut** derived from this single year of one
  market to DAX results spanning five years. **Attack this.** Is the haircut
  defensible? Does it hold if you split the NQ year in half? Does the
  5-min-vs-1-min gap vary with volatility?

### Structure and falsification
- **C5** Time-of-day scan, DAX futures, every 5-min bar as the breakout box with
  an equal 90-minute window: bar 4 = **+9,596 points, 90th percentile of 48**.
  Hourly averages **+8,367 / +2,389 / −3,179 / −7,437**.
- **C6** Concentration: the best **20 of 1,275 sessions = 99.3%** of all profit;
  best 5 = 33.6%; median trade −24.9 points.
- **C7** Out of sample around the 2023-05-08 publication date: **12.95 → 4.30
  points per session**, PF 1.268 → 1.077, t 2.27 → 1.01.
- **C8** Worst drawdown 3,275 points (end-of-day) / 3,371 (marked intraday),
  **407 sessions below a prior peak**.

### Cross-market (realistic costs, buffer = 0.8% of average daily range,
4th 5-min bar after each market's own cash open)
- **C9** NQ **$39,276/yr**, max DD $52,289, PF 1.102, t 1.74.
  DAX **EUR 27,881/yr**, max DD EUR 97,957, PF 1.080, t 1.29.
  ES $4,063/yr, t 0.34. YM $5,027/yr, t 0.60.
- **C10** Cost sensitivity tight→poor: DAX loses **72%** of profit, NQ loses **17%**.
  Claimed mechanism: cost per trade as a share of average-daily-range-in-money is
  ~4x smaller for NQ (DAX ≈1.34%, NQ ≈0.31%).
- **C11** Daily P&L correlation DAX–NQ = **0.0525**; NQ–ES = 0.77.
  Underlying session returns: DAX–NQ 0.23, NQ–ES 0.95.
- **C12** DAX+NQ combined: **$68,634/yr, max DD $112,567, Sharpe 0.92, t 2.08** —
  claimed to be the only configuration in the study with t > 2.
- **C13** Payoff shape: bucketing sessions into deciles of the index's own session
  return, DAX worst decile **+EUR 3,897/session**, middle 40% ≈ **−EUR 1,200**,
  best decile **+EUR 2,527**. Same U on NQ. Long and short trades contribute
  roughly equally.

### Pre-registered round (the discipline itself needs auditing)
- **C14** 32 hypotheses declared in `preregistration/2026-09-18_bar_shape_and_exits.md`,
  **0 survived**. Largest: body-fraction 0.50–0.70 at −0.214 R, t −2.32.
- **C15** 2 post-discovery hypotheses in `..._2026-09-18b_two_survivors.md`, both
  failed on holdout. H1 pooled holdout difference **−0.002 R (t −0.03)**.
- **C16** Take-profit prediction confirmed: across 4 datasets x 7 target sizes,
  **0 of 28 beat having no target**; a 30%-of-range target gives a **79–81% win
  rate** on every dataset and negative expectancy on 3 of 4.
- **Audit the pre-registration process, not just the numbers**: were the files
  actually written before the runs (check the anti-fishing commitments against
  what the scripts actually do)? Were all declared hypotheses reported, or was
  anything quietly dropped? Did the second pre-registration smuggle in a metric
  change to rescue a dead result — it openly says it switched from R to money,
  so decide whether that was legitimate or a rationalisation.

---

## 5. Where I would attack first — known soft spots

These are disclosed honestly. They are the places the previous session was least
certain, and a verifier's time is best spent here.

1. **The intrabar path assumption dominates everything.** 5-minute bars cannot
   show the order in which price touched two levels. The whole result rests on
   the "up bar goes open→low→high→close" convention. C2 shows the sign flips
   under the pessimistic alternative. The 58–90% haircut rests on one year of
   one market.
2. **Back-adjusted futures data.** The DAX futures file's price *levels* are
   offset by ~2,600 points in 2021. The claim is that intraday point moves are
   unaffected. Verify that — and check whether roll dates create artefacts on
   specific days.
3. **The DAX cash index is not tradable.** Its 14-year result (C3) is far better
   than the futures result and is used as "evidence the effect is old". Cash bars
   are ~14% narrower than futures, which mechanically tightens stops. Also check
   the opening-print artefact: the cash index at 09:00 is computed from stocks
   that have not all opened. The previous session checked bar 1 (ratio 1.70) and
   bar 4 (1.14) and concluded bar 4 is clean. Re-check.
4. **Warm-up in `data.py::avg_daily_range`.** `min_obs=3` for the 14-day window
   means the first few sessions average only 3 days. This feeds the `atr_frac`
   buffers used throughout cross-market work. A previous audit found and fixed a
   related bug in the 100-day window; check the fast window too.
5. **Session close.** DAX is flattened at 17:30 local; cash data ends ~17:25–17:35
   and futures run to 22:00. Does the choice of close time change conclusions?
   The engine is intraday-only by construction — verify nothing leaks across days.
6. **Costs are modelled as symmetric adverse adjustments.** Real slippage on a
   fast breakout is asymmetric and fat-tailed. Whether the "realistic" scenario is
   actually realistic is an open question the data cannot settle.
7. **Time-of-day scan runway.** Later signal bars have less time before the forced
   close. A previous audit checked this was not driving the "late bars lose"
   result but called it a directional check, not a proof.
8. **Selection at the family level.** Even the pre-registered round involved
   choosing which five families to declare. That choice was not itself
   pre-registered.
9. **Trade count and cost coupling.** Many configurations differ in trade count,
   so cost assumptions interact with every comparison. Check that no conclusion is
   an artefact of one variant simply trading less.

---

## 6. Already audited — do not redo unless you suspect it

Two adversarial subagent audits have run. Round 1 found two real bugs (a
look-ahead in intrabar trailing-stop updates; a non-functional
`force_flat_at_close` flag) — both fixed, both now covered by tests. Round 2
found no bugs and independently confirmed the commission maths, the day-skipping
filters, the absence of look-ahead in the ADR windows, the equal-window scan, and
the DAX–NQ correlation.

Verified previously and probably not worth re-running from scratch: P&L
reconstruction from fill lists, cost sign correctness in all four directions,
gap-through fill behaviour, metric formulas against hand-computed values.

**Not yet independently audited**: everything added in round 3 — the new stop
placements (`prev_bar`, `prev_bar_mid`, `both_bars`, `signal_bar_mid`), the
bar-range take-profit modes, and the per-session bar-shape tagging. Also never
audited: whether the *conclusions* follow from the numbers.

---

## 7. Deliverable

A verification report covering:
1. **Independent reimplementation** — your numbers vs C1, and the explanation for
   any gap.
2. **Claim-by-claim**: for each of C1–C16, state CONFIRMED / NOT CONFIRMED /
   PARTIAL with your own figure. Do not round toward the claimed value.
3. **New bugs** with the experiment output proving each.
4. **Judgement calls you disagree with** — places where the numbers are right but
   the interpretation is arguable. This is explicitly wanted, not out of scope.
5. **Anything overstated** in the three reports once you finally read them.

Be concrete. No praise. A verification that finds nothing should say so in one
line and spend its space on what it checked and how hard.
