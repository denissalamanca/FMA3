"""One-command reproducible run of the v7.0 band-book position extraction.

Usage:
    /opt/homebrew/Caskroom/miniforge/base/bin/python3 \
        /Users/dsalamanca/vs_env/FableMultiAssets3/engine/v7_bridge/run_extract.py

Runs the full pipeline (see extract_positions.py module docstring):
  1. prime the IC feed and build the v7.0 book (BTC_REP swap, USTEC),
  2. bit-exact self-test of the copied numba core against NSF5's engine,
  3. band-book run (up=0.25, down=(1/7)/1.75, kmult=2.5) with per-bar
     per-instrument position capture,
  4. verification: exact anchor-metric reproduction + <1e-6 position->equity
     rebuild consistency,
  5. artifacts to research/outputs/: v7_book_lots_1m.parquet,
     v7_book_equity_1m.parquet, v7_book_frac_1h.parquet,
     v7_extract_verification.json.

Single-process by NSF5 convention (module-level bar caches). Expect ~10-25
minutes (numba JIT on first call; ~60+ window re-runs; CPU contention from
concurrent backtests slows it further). Exits non-zero if any gate fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_positions import extract  # noqa: E402

if __name__ == "__main__":
    report = extract(write_artifacts=True, run_self_test=True, verbose=True)
    sys.exit(0 if report["status"] == "reconciled" else 1)
