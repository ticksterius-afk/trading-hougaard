# Pre-registration — bar-shape conditioning and exit placement
Locked 2026-09-18, BEFORE any of the tests below were run.
Engine commit state: 18 tests passing; two independent audits, no open bugs.

## Why this document exists
Three earlier searches in this project (best signal bar, best buffer, two
volatility filters) all came back flat or self-contradicting. The tests below
are a fourth search of the same kind, over roughly 32 hypotheses, on data where
a purely random 25%/75% split of the SAME trades produces a bucket difference of
+/-0.24 R ninety-five percent of the time. Without declaring the rules in
advance, something will look significant and it will not be.

## Measured noise floor (computed before locking, from the existing trade log)
- per-trade R: mean +0.119, sd 2.743, n = 2,707
- random 25/75 split of identical trades: |difference| <= 0.239 R, 95% of the time
- minimum detectable difference at 300 sessions/bucket: ~0.31 R
=> Any bucket difference below 0.24 R is reported as NO EFFECT regardless of
   how good the money column looks.

## Data split — fixed now, not negotiable later
- DISCOVERY:  DAX cash index, 2012-11-05 .. 2019-12-31  (~1,800 sessions)
- HOLDOUT A:  DAX cash index, 2020-01-01 .. 2026-08-28  (~1,700 sessions)
- HOLDOUT B:  DAX futures,    2021-08-30 .. 2026-08-28  (1,275 sessions)
- HOLDOUT C:  NQ futures,     2021-08-30 .. 2026-08-28  (1,275 sessions)
The holdouts are not to be examined until discovery is complete and this file
is unchanged. Holdout C is a different market, so it tests transfer, not just
a different period.

## Baseline configuration (held constant across every test)
School Run, 15-minute bars, signal bar 2 (09:15-09:30 Frankfurt).
Buffer 0.8% of average daily range. Stop = opposite trigger. No target.
Entry window 120 min. Unlimited flips. Realistic costs: 1 tick spread +
1 tick slippage + commission. Intrabar model: bar_direction.

## Locked definitions
- bar1 = 1st 15-min bar (09:00-09:15). bar2 = 2nd = the signal bar (09:15-09:30).
- INSIDE BAR: bar2.high <= bar1.high AND bar2.low >= bar1.low.
- BODY FRACTION: |close - open| / (high - low) of bar2.
    trend   >= 0.70
    strong  0.50 - 0.70
    middling 0.25 - 0.50
    doji    < 0.25
- DIRECTION: sign(close - open). A bar with close == open is excluded from
  direction tests (not silently bucketed as up).
- All thresholds above are fixed. If a boundary later looks arbitrary, that is
  a new pre-registration, not an edit to this one.

## Hypotheses (32 declared; Bonferroni alpha = 0.05/32 = 0.0016, |t| > 3.15)
T1 (1 test)  Inside bar2 changes expectancy vs non-inside.
             PREDICTION: no effect. Rationale: an inside bar means a narrower
             signal range, which tightens the stop and widens R symmetrically.
T2 (4 tests) Expectancy differs across the four body-fraction buckets.
             PREDICTION: no effect, or weakly better after doji bars (a doji
             means unresolved positioning, so the eventual break travels).
T3 (8 tests) bar1/bar2 direction pair predicts WHICH SIDE of the break wins.
             4 pairs x {long breakout, short breakout}.
             PREDICTION: this is the only family with a plausible mechanism
             (two bars agreeing = established direction). Genuinely open.
T4 (14 tests) Take profit set at 30/50/75/100/150/200/300% of bar1 range,
             and the same seven of bar2 range.
             PREDICTION: all reduce expectancy; win rate rises monotonically
             while expectancy falls. Prior work found every target harmful.
T5 (5 tests) Stop placed at: bar1 extreme / bar2 extreme with no buffer /
             bar1 midpoint / bar2 midpoint / combined 09:00-09:30 extreme.
             PREDICTION: wider stops reduce whipsaw count and raise win rate
             but lower R per winner; net roughly neutral. Highest-value family
             because stop placement changes R, which rescales everything.

## Decision rule — all three must hold
1. DISCOVERY: |bucket expectancy - complement expectancy| >= 0.24 R, and the
   bucket has >= 150 sessions.
2. SIGNIFICANCE: |t| > 3.15 on the discovery difference (Bonferroni over 32).
3. CONFIRMATION: the SAME SIGN in all three holdout sets. Magnitude may shrink;
   a sign flip in any holdout kills the finding outright.
A result failing any of these is reported as dead, in the same table and the
same typeface as the survivors.

## Anti-fishing commitments
- Every hypothesis above is reported, including boring ones. No selective
  reporting of the interesting subset.
- No new bucket boundaries, no new thresholds, no "we also tried" additions
  after seeing discovery results. Those require a new pre-registration file.
- Results tables are produced by a subagent given this spec and not the
  project's existing narrative, to reduce the analyst's confirmation bias.
- If nothing survives, that is the finding, and it is the fourth consecutive
  negative result for conditioning rules on this strategy.
