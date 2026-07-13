#!/usr/bin/env python3
"""BIT-IDENTITY gate for record_engine_ext vs the pinned v3.4 reference.

record_engine_ext.py is a COPY of FMA2's engine of record with the quarter
range and bar source parameterized (needed for the 2026H1 one-shot). Per
PROTOCOL.md paragraph 5.6, a copied engine may not ship a single number until
it reproduces the pin EXACTLY: this script rebuilds the v3.4 book matrix
(the same eval_v34_pin_s10.build_c2 construction the pin used), runs the EXT
engine over the default 2020Q1..2025Q4 range with default (IC) bar sources,
and demands:

  * equity + worst 1m curves BIT-IDENTICAL (np.array_equal, tolerance ZERO)
    to research/baselines/fma2/v34_s10_pin_curve.parquet, index included;
  * every headline metric EXACTLY equal (float ==) to
    research/baselines/fma2/v34_s10_pin_1m.json (json floats round-trip
    exactly, the engine is deterministic — any nonzero delta means the copy
    drifted, full stop).

The house breach bootstrap is NOT re-run here: it is a deterministic pure
function of the curve (seed 20260709), so a bit-identical curve implies the
pinned breach numbers verbatim (that path is already exercised by
scripts/verify_record_engine.py for the wrapper).

This is an ENGINE RUN (~5-8 min: 24 quarters of 1m data + numba JIT). Obey
the campaign CPU-etiquette rule: do not launch while the pre-registered
experiment queue (run_hfed*/derive_composite) is running.

Run:  python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/verify_record_engine_ext.py
Writes research/outputs/verify_record_engine_ext.json; exit 0 iff reconciled.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))

import record_engine_ext as RX  # noqa: E402
import books                    # noqa: E402


def main() -> int:
    ref_path = RX.PATHS.BASELINES / "fma2" / "v34_s10_pin_1m.json"
    pin = json.loads(ref_path.read_text())["pin"]
    curve_ref = pd.read_parquet(
        RX.PATHS.BASELINES / "fma2" / "v34_s10_pin_curve.parquet")

    t0 = time.time()
    print("[1/3] reconstructing v3.4 book (eval_v34_pin_s10.build_c2) ...",
          flush=True)
    pos = books.build_v34_frac_1h()
    print(f"      book matrix {pos.shape}, {time.time()-t0:.0f}s", flush=True)

    print("[2/3] EXT engine run, default range 2020Q1..2025Q4, default IC "
          "bar sources ...", flush=True)
    eq_c, eq_w, m = RX.simulate_account_1m_ext(pos, initial=10_000.0,
                                               verbose=True)
    print(f"      done, {time.time()-t0:.0f}s total", flush=True)

    print("[3/3] BIT-IDENTITY reconciliation")
    rows: list[tuple[str, float, float, float, bool]] = []

    def check(name: str, got, want) -> None:
        d = float(got) - float(want)
        rows.append((name, float(got), float(want), d, d == 0.0))

    check("cagr", m["cagr"], pin["cagr"])
    check("maxdd_worst", m["maxdd"], pin["maxdd"])
    check("sharpe", m["sharpe"], pin["sharpe"])
    check("final_equity", m["final_equity"], pin["final_equity"])
    check("years", m["years"], pin["years"])
    check("n_trades", m["n_trades"], pin["n_trades"])
    check("n_neg_years", m["n_neg_years"], pin["n_neg_years"])
    check("n_neg_quarters", m["n_neg_quarters"], pin["n_neg_quarters"])
    for y, v in pin["yearly"].items():
        check(f"yearly.{y}", m["yearly"][int(y)], v)
    for q, v in pin["quarterly"].items():
        check(f"quarterly.{q}", m["quarterly"][q], v)

    idx_ok = eq_c.index.equals(curve_ref.index)
    eq_bit = idx_ok and np.array_equal(eq_c.to_numpy(),
                                       curve_ref["equity"].to_numpy())
    wo_bit = idx_ok and np.array_equal(eq_w.to_numpy(),
                                       curve_ref["worst"].to_numpy())
    d_eq = float(np.abs(eq_c.to_numpy()
                        - curve_ref["equity"].to_numpy()).max()) if idx_ok else float("nan")
    d_wo = float(np.abs(eq_w.to_numpy()
                        - curve_ref["worst"].to_numpy()).max()) if idx_ok else float("nan")

    print(f"\n{'metric':<22}{'got':>22}{'reference':>22}{'delta':>12}  ok")
    for name, got, want, d, ok in rows:
        print(f"{name:<22}{got:>22.12f}{want:>22.12f}{d:>12.3e}  "
              f"{'PASS' if ok else 'FAIL'}")
    print(f"curve index identical: {idx_ok}")
    print(f"equity curve bit-identical: {eq_bit} (max|d| {d_eq:.3e})")
    print(f"worst  curve bit-identical: {wo_bit} (max|d| {d_wo:.3e})")

    all_ok = all(r[4] for r in rows) and eq_bit and wo_bit

    report = {
        "status": "reconciled" if all_ok else "FAILED",
        "gate": "BIT-IDENTICAL (tolerance zero)",
        "reference_json": str(ref_path),
        "reference_curve": str(RX.PATHS.BASELINES / "fma2"
                               / "v34_s10_pin_curve.parquet"),
        "engine": "engine/record_engine_ext.py::simulate_account_1m_ext "
                  "(default range + default IC bar sources)",
        "checks": [{"metric": n, "got": g, "reference": w, "delta": d,
                    "ok": ok} for n, g, w, d, ok in rows],
        "curve_bit_identical": {"index": bool(idx_ok),
                                "equity": bool(eq_bit),
                                "worst": bool(wo_bit),
                                "max_abs_delta_equity": d_eq,
                                "max_abs_delta_worst": d_wo},
        "assumed_2026H1_policy_rates": RX.ASSUMED_2026H1_POLICY_RATES,
        "runtime_sec": round(time.time() - t0, 1),
    }
    out_path = RX.PATHS.OUTPUTS / "verify_record_engine_ext.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1))
    print(f"\n{'RECONCILED' if all_ok else 'FAILED'} "
          f"({report['runtime_sec']:.0f}s) -> {out_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
