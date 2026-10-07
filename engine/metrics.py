"""Performance statistics, with plain-English definitions in the docstrings."""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List


def trades_to_frame(trades: List) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["date", "side", "entry_ts", "entry_raw",
                                     "entry_fill", "risk_points", "exit_ts",
                                     "exit_reason", "points", "r", "mae",
                                     "mfe", "seq", "units_traded"])
    rows = []
    for t in trades:
        rows.append(dict(date=t.date, side=t.side, entry_ts=t.entry_ts,
                         entry_raw=t.entry_raw, entry_fill=t.entry_fill,
                         risk_points=t.risk_points, exit_ts=t.exit_ts,
                         exit_reason=t.exit_reason, points=t.points,
                         r=t.r_multiple, mae=t.mae, mfe=t.mfe, seq=t.seq,
                         units_traded=t.units_traded))
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "entry_ts"]).reset_index(drop=True)


def _max_drawdown(equity: np.ndarray) -> float:
    """Largest peak-to-trough fall of the running P&L curve, in points.
    This is the worst losing run you would have had to sit through."""
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def intraday_drawdown(trades: List) -> float:
    """Worst peak-to-trough fall when the account is marked to market DURING
    the day, not just at the close.

    Both excursions are used, so a trade that peaks at +1,486 and closes at
    +394 registers the peak. `max_dd_points` is computed on end-of-day totals, so a day that swings
    -400 and finishes +10 shows up as +10. This version walks the trades in
    order and, for each one, dips the running equity by that trade's own worst
    unrealised loss (its maximum adverse excursion) before banking the result.
    It is the number a trader actually watches on the screen."""
    tf = trades_to_frame(trades)
    if tf.empty:
        return 0.0
    eq = 0.0
    peak = 0.0
    worst = 0.0
    for pts, mae, mfe in zip(tf["points"], tf["mae"], tf["mfe"]):
        # A trade that runs deep into profit on paper sets a new high-water mark
        # even if it gives it all back -- that peak is what the trader saw, and
        # the fall from it is what they lived through. Counting only realised
        # equity understates the drawdown.
        peak = max(peak, eq + abs(mfe))
        worst = max(worst, peak - (eq - abs(mae)))
        eq += pts
        peak = max(peak, eq)
        worst = max(worst, peak - eq)
    return float(worst)


def summarise(trades: List, n_sessions: int, point_value: float = 1.0,
              label: str = "") -> dict:
    tf = trades_to_frame(trades)
    n = len(tf)
    if n == 0:
        return dict(label=label, trades=0, sessions=n_sessions, points=0.0)

    pts = tf["points"].to_numpy()
    wins, losses = pts[pts > 0], pts[pts < 0]
    daily = tf.groupby("date")["points"].sum()
    # calendar of traded sessions only
    eq_trade = np.cumsum(pts)
    eq_day = daily.cumsum().to_numpy()

    gross_win = wins.sum()
    gross_loss = -losses.sum()
    dstd = daily.std(ddof=1)
    mean_d = daily.mean()

    out = dict(
        label=label,
        sessions=int(n_sessions),
        traded_sessions=int(daily.size),
        trades=int(n),
        trades_per_session=round(n / max(n_sessions, 1), 2),

        # ---- headline P&L -------------------------------------------------
        total_points=round(float(pts.sum()), 1),
        points_per_session=round(float(pts.sum()) / max(n_sessions, 1), 3),
        points_per_trade=round(float(pts.mean()), 3),
        total_money=round(float(pts.sum()) * point_value, 0),

        # ---- shape of the edge --------------------------------------------
        win_rate=round(float((pts > 0).mean()) * 100, 1),
        avg_win=round(float(wins.mean()) if len(wins) else 0.0, 2),
        avg_loss=round(float(losses.mean()) if len(losses) else 0.0, 2),
        # profit factor = money made on winners / money lost on losers.
        # >1 means the system made money; 1.3+ is usually considered tradable.
        profit_factor=round(float(gross_win / gross_loss), 3) if gross_loss > 0 else np.inf,
        expectancy_R=round(float(np.nanmean(tf["r"])), 4),
        avg_risk_points=round(float(tf["risk_points"].mean()), 2),

        # ---- risk ----------------------------------------------------------
        # end-of-day drawdown: what the equity curve shows if you only
        # look once a day, after the close.
        max_dd_points=round(_max_drawdown(eq_day), 1),
        # mark-to-market drawdown: includes the damage inside the day.
        max_dd_intraday=round(intraday_drawdown(trades), 1),
        max_dd_money=round(_max_drawdown(eq_day) * point_value, 0),
        max_dd_intraday_money=round(intraday_drawdown(trades) * point_value, 0),
        money_per_session=round(float(pts.sum()) * point_value / max(n_sessions, 1), 1),
        money_per_year=round(float(pts.sum()) * point_value / max(n_sessions, 1) * 252, 0),
        worst_day=round(float(daily.min()), 1),
        best_day=round(float(daily.max()), 1),
        daily_std=round(float(dstd), 2) if np.isfinite(dstd) else np.nan,
        # Sharpe: average daily points divided by their standard deviation,
        # scaled to a year (252 sessions). Rough "return per unit of wobble".
        sharpe=round(float(mean_d / dstd * np.sqrt(252)), 2) if dstd and dstd > 0 else np.nan,

        # ---- is it luck? ----------------------------------------------------
        # t-stat = how many standard errors the average day sits above zero.
        # |t| > 2 is the usual rule of thumb for "probably not noise", but it
        # assumes independent days, so treat it as a smoke alarm, not proof.
        t_stat=round(float(mean_d / (dstd / np.sqrt(daily.size))), 2) if dstd and dstd > 0 else np.nan,
        pct_days_positive=round(float((daily > 0).mean()) * 100, 1),
    )
    for reason, g in tf.groupby("exit_reason"):
        out[f"exit_{reason}"] = len(g)
    for seq, g in tf.groupby("seq"):
        if seq <= 4:
            out[f"seq{int(seq)}_points"] = round(float(g["points"].sum()), 1)
    return out


def yearly(trades: List) -> pd.DataFrame:
    tf = trades_to_frame(trades)
    if tf.empty:
        return tf
    tf["year"] = tf["date"].dt.year
    g = tf.groupby("year")
    return pd.DataFrame({
        "trades": g.size(),
        "points": g["points"].sum().round(1),
        "win_rate": (g["points"].apply(lambda x: (x > 0).mean()) * 100).round(1),
        "expectancy_R": g["r"].mean().round(3),
    })


def bootstrap_ci(trades: List, n_boot: int = 2000, seed: int = 7) -> dict:
    """Resample whole DAYS with replacement to get a confidence interval on the
    total. Answers: 'if the same process ran again, how different could the
    result plausibly be?' Days (not trades) are resampled because trades inside
    one day are obviously related to each other."""
    tf = trades_to_frame(trades)
    if tf.empty:
        return {}
    daily = tf.groupby("date")["points"].sum().to_numpy()
    rng = np.random.default_rng(seed)
    n = len(daily)
    sims = rng.choice(daily, size=(n_boot, n), replace=True).sum(axis=1)
    return dict(
        boot_mean=round(float(sims.mean()), 1),
        boot_p05=round(float(np.percentile(sims, 5)), 1),
        boot_p50=round(float(np.percentile(sims, 50)), 1),
        boot_p95=round(float(np.percentile(sims, 95)), 1),
        boot_prob_positive=round(float((sims > 0).mean()) * 100, 1),
    )
