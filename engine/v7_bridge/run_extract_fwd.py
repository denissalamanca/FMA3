"""One-command v7.0 band-book position extraction on the FORWARD feed.

Usage:
    /opt/homebrew/Caskroom/miniforge/base/bin/python3 \
        /Users/dsalamanca/vs_env/FableMultiAssets3/engine/v7_bridge/run_extract_fwd.py

WHAT THIS RUNS (FORWARD_TEST.md execution plan, step 1)
-------------------------------------------------------
The SAME v7.0 band book as the verified IC anchor (book('BTC_REP', us5),
up=0.25, down=(1/7)/1.75, kmult=2.5, min_gap 5d, noliq stop_out=1e-9) on the
NSF5 v51_rig forward feed:

  * v51_rig.prime_2026(): Dukascopy 2020-2025 1m bars with the 2026H1 holdout
    appended per instrument (14 symbols), FxConverter holdout-aware — the
    exact warm-start convention of NSF5's published duka+2026H1 rig.
  * us5='USA500': USTEC has no Duka feed; USA500 (corr 0.89) is the rig's
    documented proxy. The proxy book is NOT the deployed book — directional
    confirmation only (FORWARD_TEST.md caveat).
  * window [2020-01-01, 2026-05-01): the full history so 2026 book state is
    warm-started from 2020-25 exactly as a continuous run would be; per-symbol
    data ends 2026-04-30 UTC (EURUSD/XAUUSD extend further but the window is
    cut at 05-01 for uniformity).

TIMEZONE (landmine)
-------------------
The Duka feed is tz-naive TRUE UTC, so every artifact index here is TRUE UTC —
unlike the IC artifacts (broker SERVER time). Convert ONLY via
utc.tz_localize('UTC').tz_convert('America/New_York') + 7h -> tz_localize(None).
NB: converting the full 2020-25 index creates duplicate naive stamps inside
each NY fall-back fold hour (crypto trades through it); the 2026H1 test window
contains no fold (next: 2026-11-01) and converts cleanly.

HOLDOUT DISCIPLINE (PROTOCOL.md §4 / FORWARD_TEST.md)
-----------------------------------------------------
2026 position matrices and equity curves are BUILT and SAVED blind. No 2026
portfolio metric is computed or printed: trigger console lines are suppressed
from 2026-01-01, trigger equity/share floats are redacted in the verification
JSON, and the only metrics reported are sim.bd_metrics over
[2020-01-01, 2026-01-01) — development-window feed-quality context.

GATES (anchor gate is IC-only; these two still run)
---------------------------------------------------
  1. bit-exact core self-test vs NSF5 run_backtest on this feed, every leg;
  2. positions -> book-equity rebuild < 1e-6 relative on the full window.

ARTIFACTS (research/outputs/fwd/, index = tz-naive TRUE UTC)
------------------------------------------------------------
  v7_book_lots_1m_fwd.parquet     net signed lots per instrument, union 1m grid
  v7_book_equity_1m_fwd.parquet   eqc / eqw / margin
  v7_book_frac_1h_fwd.parquet     hourly fraction-of-book-equity matrix
                                  (FMA2 convention, hour-start stamp = last 1m
                                  snapshot in [h, h+1))
  v7_extract_fwd_verification.json

Single-process by NSF5 convention (module-level bar caches). Expect ~5-25 min.
Exits non-zero if any gate fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_positions import OUT_DIR, extract  # noqa: E402

#: Forward extraction window (full history -> uniform per-symbol data end).
LO_FWD = pd.Timestamp("2020-01-01")
HI_FWD = pd.Timestamp("2026-05-01")
#: Holdout boundary: nothing at/after this stamp is printed or metricized.
BLIND_FROM = pd.Timestamp("2026-01-01")

if __name__ == "__main__":
    report = extract(
        write_artifacts=True,
        run_self_test=True,
        verbose=True,
        feed="duka2026",
        us5="USA500",
        lo=LO_FWD,
        hi=HI_FWD,
        anchor_gate=False,          # no IC reference exists on this feed
        out_dir=OUT_DIR / "fwd",
        artifact_suffix="_fwd",
        blind_from=BLIND_FROM,
        dev_metrics_hi=BLIND_FROM,  # 2020-25 feed-quality context only
    )
    sys.exit(0 if report["status"] == "consistent" else 1)
