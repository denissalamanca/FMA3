#!/usr/bin/env python3
"""Build the v3.4 book's FORWARD hourly fraction matrix (2020 -> 2026-04-30).

WHAT
----
Materializes the shipped FMA2 v3.4 book's position matrix on the forward-
extended hourly feed as a standalone artifact:

    research/outputs/fwd/v34_frac_1h_fwd.parquet   (+ _report.json sidecar)

so the one-shot driver (scripts/run_forward_oneshot.py) can consume it via
``"v34_forward": {"mode": "parquet", "path": ...}`` instead of rebuilding
in-process, and so the construction is verified BEFORE the gated one-shot.

HOW (single code path — no reimplementation)
--------------------------------------------
This script deliberately delegates to
``run_forward_oneshot.build_v34_forward_frac()`` — the one-shot's own
FMA2-side loader — rather than re-deriving the recipe. That function:

  a. materializes the 37-symbol hybrid hourly cache research/fwd_cache_1h/
     (14 Duka-covered symbols from FMA2 research_cache_fwd = IC 2020-2025 +
     converted 2026H1 holdout tail; the other 23 are byte-copies of FMA2
     research_cache, ending 2025-12-31);
  b. repoints FMA2 core.CACHE (both module instances), clears the lru caches,
     re-RUNS all 8 shipped sleeves' ``make_positions()`` with their frozen
     in-module defaults (7 sleeves + the mag_xau overlay — zero re-tuning),
     and combines exactly as ``eval_v34_pin_s10.build_c2`` does: RAW v3.4
     weights (cash-parked, never renormalized) x GLOBAL_SCALE 10, then
     ``ensemble.apply_hard_limits`` with the structural gold cap 1.80;
  c. GATES the rebuild: on the 2020-2025 prefix the re-run matrix must match
     the pinned construction ``books.build_sat_frac_1h()`` to <= 1e-9 on the
     common index/columns (aborts otherwise). The 2020-2025 portion of the
     hybrid cache is bit-identical to research_cache by construction
     (verified empirically 2026-07-10 for all 14 fwd symbols), so any
     deviation would mean a sleeve is not truncation-stable — diagnose, do
     not ship.

Using the loader itself (instead of a copy) means this artifact and the
one-shot's ``"rebuild"`` mode cannot drift — with the two documented,
DELIBERATE post-processing differences below.

2026 COVERAGE CONVENTION (documented decision)
----------------------------------------------
Only 14 of the 37 instruments have a real 2026H1 feed (FWD_REAL_SYMS; USTEC
has NO hourly forward feed — the USA500 proxy file is a 1m engine pricing
opt-in, not sleeve signal data). For the other 23 instruments the hybrid
cache ends 2025-12-31, so their 2026 "signals" would be frozen-price
artifacts: state-machine sleeves (e.g. carry_breakout's Donchian) HOLD their
last position through 2026 on a frozen close — an ffill ghost, not a trading
decision. The honest forward-test convention adopted here:

    sleeves contribute ONLY their covered legs in 2026 — every uncovered
    instrument's positions are set to 0.0 on all rows >= 2026-01-01, and the
    zeroed (would-have-been) gross exposure is disclosed in the sidecar
    report. 2020-2025 rows are untouched.

This mirrors FMA2's own cross-feed precedent (research/feed_test.py restricts
the harness to covered symbols) at book level, without perturbing the
2020-2025 verification surface. Consequence for the one-shot: sleeves whose
2026 book is partially uncovered (meanrev: only EURGBP/DAX/USA500 of its FX
crosses+indices; crisis: XAU leg only, JPY-cross leg uncovered; trend_v2:
XAU/XAG only; crypto_smart: BTC/ETH only, SOL uncovered; intraday: USA500
only, USTEC uncovered; carry: covered pairs only) run 2026 with reduced
breadth — a disclosed limitation of the forward window, NOT a change to any
frozen parameter. Covered-leg 2026 signals are computed on the full hybrid
grid, so cross-instrument inputs that reference uncovered symbols (crisis
stress baskets, carry top-k ranking, carry's policy-rate table which is
ffilled flat beyond 2025-12-31) see frozen 2025 values for those inputs —
deterministic and disclosed.

WINDOW TRUNCATION (documented decision)
---------------------------------------
The matrix is truncated at server stamp 2026-04-30 23:59:59. Pre-registered
window (FORWARD_TEST.md): the test ends 2026-04-30 for uniformity — 12 of 14
symbols end there; only EURUSD/XAUUSD extend to 05-31. Truncating the matrix
enforces the committed uniform end at the artifact level (the engine maps a
missing hourly row to zero target, so the book goes flat after the last row).
The one-shot's "rebuild" mode would instead carry EURUSD/XAUUSD rows through
May — parquet mode + this artifact is the variant consistent with the
pre-registration.

DISCIPLINE (PROTOCOL.md / FORWARD_TEST.md)
------------------------------------------
This script computes NO performance number of any kind on 2026 data — no
returns, no equity, no simulate() call. It builds and saves positions blind.
Everything printed/saved about 2026 is index ranges and position/coverage
statistics. The 2020-2025 verification gate (allowed) reports only position
deviations vs the pinned construction.

CPU ETIQUETTE: waits for the FMA3 verification lock chain
(verify_record_engine_ext / eval_fma3_pin) to finish before doing any heavy
work.

Run:  python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/build_v34_fwd.py
(~2-5 min: pinned baseline + 8 sleeve re-runs on the hybrid cache.)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
_SCRIPTS = _FMA3 / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

#: Pre-registered uniform end of the forward window (FORWARD_TEST.md):
#: last hourly row kept is the final server-time stamp of 2026-04-30.
TRUNCATE_END = pd.Timestamp("2026-04-30 23:59:59")
#: First forward-window row — uncovered instruments are zeroed from here on.
FWD_START = pd.Timestamp("2026-01-01 00:00:00")

OUT_DIR = _FMA3 / "research" / "outputs" / "fwd"
OUT_PARQUET = OUT_DIR / "v34_frac_1h_fwd.parquet"
OUT_REPORT = OUT_DIR / "v34_frac_1h_fwd_report.json"

_LOCK_PATTERN = "verify_record_engine|eval_fma3_pin"


def wait_for_lock_chain(poll_sec: int = 60) -> None:
    """Block until the FMA3 verification lock chain is idle (CPU etiquette)."""
    while subprocess.run(["pgrep", "-f", _LOCK_PATTERN],
                         capture_output=True).returncode == 0:
        print(f"[build_v34_fwd] lock chain ({_LOCK_PATTERN}) running — "
              f"waiting {poll_sec}s ...", flush=True)
        time.sleep(poll_sec)


def _abs_mean_by_symbol(block: pd.DataFrame) -> dict[str, float]:
    """Mean |position| per symbol, nonzero entries only — a coverage stat."""
    m = block.abs().mean()
    return {k: float(v) for k, v in
            m[m > 0].sort_values(ascending=False).items()}


def main() -> int:
    wait_for_lock_chain()

    # Import AFTER the wait: pulls the FMA2/NSF5 stack via record_engine_ext.
    import run_forward_oneshot as RFO  # noqa: PLC0415

    t0 = time.time()
    fwd, gate = RFO.build_v34_forward_frac()   # aborts if 2020-25 gate fails

    covered = list(RFO.FWD_REAL_SYMS)
    uncovered = [c for c in fwd.columns if c not in covered]
    is_2026 = fwd.index >= FWD_START

    # --- honest coverage convention: covered legs only in 2026 --------------
    ghost_2026 = fwd.loc[is_2026, uncovered]
    zeroed_disclosure = {
        "uncovered_symbols": uncovered,
        "zeroed_cells_nonzero": int((ghost_2026 != 0.0).to_numpy().sum()),
        "zeroed_mean_abs_frac_by_symbol": _abs_mean_by_symbol(ghost_2026),
        "zeroed_mean_gross_frac":
            float(ghost_2026.abs().sum(axis=1).mean()) if len(ghost_2026)
            else 0.0,
    }
    fwd.loc[is_2026, uncovered] = 0.0

    # --- pre-registered uniform window end ----------------------------------
    n_before = len(fwd)
    fwd = fwd.loc[:TRUNCATE_END]
    rows_truncated = n_before - len(fwd)

    # --- save (blind: positions only, no metrics) ----------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fwd.to_parquet(OUT_PARQUET)

    w26 = fwd.loc[fwd.index >= FWD_START]
    report = {
        "artifact": str(OUT_PARQUET),
        "generated": pd.Timestamp.now().isoformat(),
        "construction": ("run_forward_oneshot.build_v34_forward_frac() — the "
                         "one-shot's own FMA2-side loader (single code path); "
                         "sleeves re-run from frozen make_positions() defaults "
                         "on research/fwd_cache_1h, combined per "
                         "eval_v34_pin_s10.build_c2 (RAW weights x SCALE 10 + "
                         "apply_hard_limits, gold cap 1.80)"),
        "verification_gate_2020_2025": {
            "reference": "FMA3 engine/books.py::build_v34_frac_1h() "
                         "(the pinned construction)",
            "overlap_rows": gate["overlap_rows"],
            "max_abs_deviation": gate["overlap_max_abs_delta"],
            "tolerance": 1e-9,
            "note": "hybrid cache 2020-2025 content is byte-identical to "
                    "research_cache (research_cache_fwd concatenates it "
                    "verbatim; the other 23 symbols are byte-copies), so the "
                    "IC-vs-Duka feed difference exists ONLY in 2026 rows.",
        },
        "index": {
            "first": str(fwd.index[0]),
            "last": str(fwd.index[-1]),
            "n_rows": len(fwd),
            "n_rows_2026": int(len(w26)),
            "rows_truncated_after_2026_04_30": rows_truncated,
            "grid_end_before_truncation": gate["grid_end"],
        },
        "columns": list(fwd.columns),
        "coverage_2026": {
            "covered_symbols": covered,
            "covered_nonzero_2026_cells":
                {c: int((w26[c] != 0.0).sum()) for c in covered
                 if c in w26.columns and (w26[c] != 0.0).any()},
            "mean_gross_frac_2026_positions":
                float(w26.abs().sum(axis=1).mean()) if len(w26) else 0.0,
            "uncovered_zeroed": zeroed_disclosure,
            "convention": ("sleeves contribute ONLY their covered legs in "
                           "2026; uncovered instruments (incl. USTEC — no "
                           "hourly forward feed; the USA500 proxy is a 1m "
                           "pricing opt-in, not signal data) are zeroed from "
                           "2026-01-01. Deliberate deviation from the "
                           "one-shot 'rebuild' mode, which would carry "
                           "frozen-price ghost positions on uncovered "
                           "state-machine sleeves."),
        },
        "discipline": "positions built and saved blind — no 2026 performance "
                      "number was computed by this script.",
        "build_sec": round(time.time() - t0, 1),
    }
    OUT_REPORT.write_text(json.dumps(report, indent=1))

    print(f"\n[build_v34_fwd] 2020-2025 gate: max|d| "
          f"{gate['overlap_max_abs_delta']:.3e} over "
          f"{gate['overlap_rows']:,} rows (tol 1e-9) — PASS")
    print(f"[build_v34_fwd] matrix {fwd.shape}: {fwd.index[0]} -> "
          f"{fwd.index[-1]} | 2026 rows {len(w26):,} "
          f"(truncated {rows_truncated} rows past 2026-04-30)")
    print(f"[build_v34_fwd] 2026 coverage: {len(covered)} covered symbols; "
          f"zeroed {zeroed_disclosure['zeroed_cells_nonzero']:,} ghost cells "
          f"on {len(uncovered)} uncovered symbols "
          f"(mean gross frac {zeroed_disclosure['zeroed_mean_gross_frac']:.3f})")
    print(f"[build_v34_fwd] saved -> {OUT_PARQUET}\n"
          f"                 report -> {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
