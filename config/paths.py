"""Canonical filesystem paths for FableMultiAssets3.

Both parent repos are referenced READ-ONLY, in place (no 4.6 GB copies).
Every FMA3 module imports paths from here — no hardcoded parent paths
anywhere else (the FMA2 hardcoded-path lesson).
"""
from __future__ import annotations

from pathlib import Path

# --- this repo ---------------------------------------------------------------
FMA3 = Path(__file__).resolve().parent.parent
RESEARCH = FMA3 / "research"
OUTPUTS = RESEARCH / "outputs"
BASELINES = RESEARCH / "baselines"
PROTOCOL = RESEARCH / "protocol"

# --- parents (READ-ONLY) ------------------------------------------------------
NSF5 = Path("/Users/dsalamanca/vs_env/NewStrategyFable5")
FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")

# --- price data (READ-ONLY) ---------------------------------------------------
# IC Markets native 1m bid/ask bars, 37 instruments, broker SERVER time
# (tz-naive, UTC+2/+3, day break = 17:00 ET). 2020-01-02 -> 2025-12-31.
BARS_1M_IC = NSF5 / "cache" / "bars_1m_ic"          # {SYM}_IC_1m.parquet
# Dukascopy 2nd feed, 14 instruments, tz-naive TRUE UTC.
BARS_1M_DUKA = NSF5 / "cache" / "bars_1m"           # {SYM}_2020_2025_1m.parquet
# Extended Duka history 2015-2025, 10 instruments (edge-persistence tests).
BARS_1M_EXT = NSF5 / "cache" / "bars_1m_ext"        # {SYM}_2015_2025_1m.parquet
# NEVER-FITTED 2026H1 forward holdout (Duka schema, UTC). Do not train on this.
BARS_1M_HOLDOUT = NSF5 / "cache" / "bars_1m_holdout"  # {SYM}_2026H1_1m.parquet

# FMA2 hourly research caches (server time).
FMA2_CACHE_1H = FMA2 / "research_cache"             # {SYM}_1h.parquet (mid OHLC)
FMA2_CACHE_EXEC = FMA2 / "research_cache" / "exec"  # {SYM}_1h_exec.parquet
FMA2_CACHE_DUKA = FMA2 / "research_cache_duka"
FMA2_CACHE_EXT = FMA2 / "research_cache_ext"        # 2015-2020, ASSIGNED spreads
FMA2_CACHE_FWD = FMA2 / "research_cache_fwd"        # includes 2026 holdout tail

# FMA2 sleeve position matrices (hourly fraction-of-equity, server time).
FMA2_SLEEVE_OUTPUTS = FMA2 / "research" / "outputs"

# Shared raw data outside both projects.
DATA_ROOT = Path("/Users/dsalamanca/vs_env/data")

# --- timezone rule (the canonical landmine) -----------------------------------
# IC caches: tz-naive broker SERVER time. Duka caches: tz-naive TRUE UTC.
# Convert Duka->server ONLY via:  utc.tz_convert("America/New_York") + 7h,
# then tz_localize(None).  Mixing conventions reproduces the retracted
# PF-1.49 artifact (see /Users/dsalamanca/vs_env/data/DO_NOT_USE.md).
