#!/usr/bin/env python3
"""FMA3-009: rule-accurate FTMO model v3 (payout-cycle) — importable scorer.

WHY v3 DIFFERS FROM FMA3-005b
-----------------------------
005b scored the FTMO Max Loss rule as "book peak-relative worst-mark %DD
< 10%" over the whole sample. That is STRICTER than FTMO's actual rule: the
Max Loss floor is ABSOLUTE — equity must never touch 0.90 x initial capital —
so any unpaid profit above base is extra buffer, and a peak-relative 10% draw
from a +8% high never threatens the floor. v3 models the funded account the
way it is actually operated (the FMA3-005b assumption, now made structural):
a monthly payout-to-base cycle. Each calendar month starts at base (profits
withdrawn at the boundary); WITHIN the month the floor is the absolute
0.90 x base, not 10%-off-peak. The daily rule is unchanged from 005b in
spirit — a single-day dip vs the previous close greater than 5% of the FIXED
base (an EUR limit, not a percent-of-current-equity limit) — which means a
day that dips 4.8% off an intra-month high of 1.08 x base DOES breach
(dip = 5.2% of base), while the same percent dip below base does not. v3 is
therefore looser than 005b on the floor axis and slightly stricter on the
daily axis when a month is in profit.

Bootstrap: 10,000 twelve-month paths sampled in MONTH blocks — the calendar-
month segments of the daily (r, d) pairs, drawn stationarily across months
(the payout reset makes months start-identical: every month opens at base, so
the stationary month-chain is exchangeable and is implemented as uniform
i.i.d. month draws; within-month day order is preserved exactly). Seed
20260710. Breach = daily-rule hit OR absolute-floor touch within any month.

Challenge block: P1 is simulated from base with NO monthly reset (no payouts
exist during the challenge), chaining sampled month segments and compounding
until close equity >= 1.10 x base (pass), a rule breach (fail), or 252 days.

HONEST CAVEAT (historical block)
--------------------------------
The historical scan applies the monthly-reset frame to the actual 2020-25
curve: each calendar month of the realized path is rebased to start at base,
then the daily and floor rules are scanned inside it. The realized book never
traded this payout cycle — the scan is the committed operating model imposed
on realized returns, not a record of an account that existed. Partial edge
months (the first month starts at the first trading day) are scanned as-is.

Conventions inherited from run_hrisk2b (FMA3-005b): daily (r, d) pairs from
1D-resampled minute equity close / minute worst-mark; negY/negQ from the raw
(non-reset) equity curve; seed/paths/rules constants below.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DAILY_LIMIT = 0.05     # single-day dip vs prev close, as fraction of BASE
FLOOR = 0.90           # absolute Max Loss floor, as fraction of BASE
P1_TARGET = 1.10       # Phase-1 profit target (+10% of base)
N_PATHS = 10_000
MONTHS_PER_PATH = 12
HORIZON_D = 252        # challenge simulation cap (12 months of trading days)
SEED = 20260710


def daily_frame(eq: pd.Series, wo: pd.Series) -> pd.DataFrame:
    """Per-day (close return r, worst dip vs previous close d) — 005b conv."""
    dc = eq.resample("1D").last().dropna()
    dw = wo.resample("1D").min().reindex(dc.index)
    prev = dc.shift(1)
    return pd.DataFrame({"r": dc / prev - 1.0,
                         "d": dw / prev - 1.0}).dropna()


def neg_year_quarter(eq: pd.Series) -> tuple[int, int]:
    """negY / negQ on the raw equity curve (unchanged from run_hrisk2b)."""
    y = eq.resample("YE").last()
    y0 = pd.concat([pd.Series([float(eq.iloc[0])], index=[eq.index[0]]), y])
    ry = y0.pct_change().dropna()
    q = eq.resample("QE").last()
    q0 = pd.concat([pd.Series([float(eq.iloc[0])], index=[eq.index[0]]), q])
    rq = q0.pct_change().dropna()
    return int((ry < 0).sum()), int((rq < 0).sum())


def month_segments(df: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    """Chronological calendar-month segments of the daily (r, d) frame."""
    return [(g["r"].to_numpy(), g["d"].to_numpy())
            for _, g in df.groupby(df.index.to_period("M"), sort=True)]


def _month_scan(r: np.ndarray, d: np.ndarray) -> tuple[int, float, bool]:
    """Scan one month started at base = 1.0 after payout.

    Returns (n_daily_dip_days, min day-min equity / base, breach_flag).
    Prev close for day i is base * cumprod(1+r)[:i]; day 1's prev close is
    the base itself (the payout reset). Daily rule: dip in base units
    -d_i * prev_i > DAILY_LIMIT. Floor rule: prev_i * (1+d_i) < FLOOR.
    """
    cp = np.cumprod(1.0 + r)
    prev = np.concatenate(([1.0], cp[:-1]))
    day_min = prev * (1.0 + d)
    dips = prev * (-d)
    n_dip = int((dips > DAILY_LIMIT).sum())
    lo = float(day_min.min()) if len(day_min) else 1.0
    return n_dip, lo, bool(n_dip > 0 or lo < FLOOR)


def score_v3(eq: pd.Series, wo: pd.Series) -> dict:
    """Full FMA3-009 model-v3 score of a saved (equity, worst) curve pair."""
    df = daily_frame(eq, wo)
    months = month_segments(df)
    m = len(months)

    # --- historical block: monthly-reset frame imposed on the 2020-25 path
    n_dip_total, worst_lo = 0, 1.0
    flags = np.zeros(m, dtype=bool)
    for i, (r, d) in enumerate(months):
        n_dip, lo, br = _month_scan(r, d)
        n_dip_total += n_dip
        worst_lo = min(worst_lo, lo)
        flags[i] = br
    hist = {"daily_dip_gt5pct": n_dip_total,
            "worst_month_floor_touch": worst_lo,
            "months_scanned": m}

    rng = np.random.default_rng(SEED)

    # --- bootstrap block: 10k x 12-month paths of month blocks.
    # Every sampled month starts at base (payout reset), so the per-month
    # breach flag is deterministic given the segment; a path breaches iff any
    # of its 12 drawn months carries the flag.
    draws = rng.integers(m, size=(N_PATHS, MONTHS_PER_PATH))
    p_breach = float(flags[draws].any(axis=1).mean())
    boot = {"p_breach_12m": p_breach}

    # --- challenge block: P1 from base, compounding, no monthly reset
    p1_pass, p1_days = 0, []
    for _ in range(N_PATHS):
        e, days, done = 1.0, 0, False
        while days < HORIZON_D and not done:
            r, d = months[rng.integers(m)]
            for i in range(len(r)):
                day_min = e * (1.0 + d[i])
                if e * (-d[i]) > DAILY_LIMIT or day_min < FLOOR:
                    done = True          # breach: fail the challenge
                    break
                e *= (1.0 + r[i])
                days += 1
                if e >= P1_TARGET:
                    p1_pass += 1
                    p1_days.append(days)
                    done = True          # pass
                    break
                if days >= HORIZON_D:
                    break
    chal = {"p_pass_p1": p1_pass / N_PATHS,
            "median_days_p1": (float(np.median(p1_days))
                               if p1_days else None)}

    ny, nq = neg_year_quarter(eq)
    ok = (hist["daily_dip_gt5pct"] == 0
          and hist["worst_month_floor_touch"] > FLOOR
          and boot["p_breach_12m"] <= 0.05
          and ny == 0 and nq <= 1)
    return {"historical": hist, "bootstrap": boot, "challenge": chal,
            "neg_years": ny, "neg_quarters": nq, "compliant": bool(ok)}
