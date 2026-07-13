#!/usr/bin/env python3
"""End-to-end verification of the FMA3 engine-of-record wrapper.

Reconstructs the shipped v3.4 book exactly as FMA2's official pin script does
(via ``books.build_v34_frac_1h`` -> ``eval_v34_pin_s10.build_c2``), runs it
through ``record_engine.run_record``, and reconciles every headline number
against the pinned reference backed up at
``FMA3/research/baselines/fma2/v34_s10_pin_1m.json`` — plus a minute-level
curve comparison against the backed-up ``v34_s10_pin_curve.parquet``.

Expected deltas: ZERO (same engine, same inputs, same seed).  The gate is
NON-NEGOTIABLE: any metric outside tolerance fails the run (exit code 1).

Run:  python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/verify_record_engine.py
Runtime ~6-8 min (numba JIT + 24 engine quarters + 5000-path bootstrap).
Writes FMA3/research/outputs/verify_record_engine.json.
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

import record_engine as RE  # noqa: E402
import books                # noqa: E402

# Absolute tolerances per metric.  Everything is deterministic (seeded
# bootstrap, numba engine, frozen parquets) and JSON floats round-trip
# exactly, so the expected delta is 0.0; the tolerances below only allow
# for float printing noise and are NOT to be relaxed.
TOL = {
    "cagr": 1e-9, "maxdd_worst": 1e-9, "sharpe": 1e-9,
    "final_equity": 1e-4,           # EUR
    "breach_close": 1e-12, "breach_worst": 1e-12,
    "median_dd_worst": 1e-12, "p95_dd_worst": 1e-12,
    "yearly": 1e-9, "quarterly": 1e-9,
}


def main() -> int:
    ref_path = RE.PATHS.BASELINES / "fma2" / "v34_s10_pin_1m.json"
    ref = json.loads(ref_path.read_text())
    pin, bref = ref["pin"], ref["breach"]

    t0 = time.time()
    print("[1/3] reconstructing v3.4 book (eval_v34_pin_s10.build_c2) ...",
          flush=True)
    pos = books.build_v34_frac_1h()
    print(f"      book matrix {pos.shape}, {time.time()-t0:.0f}s", flush=True)

    print("[2/3] engine of record run (24 quarters, 1m) ...", flush=True)
    res = RE.run_record(pos, label="v34_s10_verify")
    print(f"      done, {time.time()-t0:.0f}s total", flush=True)

    print("[3/3] reconciliation vs", ref_path, flush=True)
    rows: list[tuple[str, float, float, float, bool]] = []

    def check(name, got, want, tol):
        d = float(got) - float(want)
        rows.append((name, float(got), float(want), d, abs(d) <= tol))

    check("cagr", res["cagr"], pin["cagr"], TOL["cagr"])
    check("maxdd_worst", res["maxdd_worst"], pin["maxdd"], TOL["maxdd_worst"])
    check("sharpe", res["sharpe"], pin["sharpe"], TOL["sharpe"])
    check("final_equity", res["final_equity"], pin["final_equity"],
          TOL["final_equity"])
    check("n_trades", res["n_trades"], pin["n_trades"], 0)
    check("n_neg_years", res["n_neg_years"], pin["n_neg_years"], 0)
    check("n_neg_quarters", res["n_neg_quarters"], pin["n_neg_quarters"], 0)
    for y, v in pin["yearly"].items():
        check(f"yearly.{y}", res["yearly"][int(y)], v, TOL["yearly"])
    for q, v in pin["quarterly"].items():
        check(f"quarterly.{q}", res["quarterly"][q], v, TOL["quarterly"])
    for k in ("breach_close", "breach_worst", "median_dd_worst",
              "p95_dd_worst"):
        check(f"breach.{k}", res["breach"][k], bref[k], TOL[k])

    neg_q_ok = res["neg_quarters"] == ["2023Q1"]
    neg_y_ok = res["neg_years"] == []

    # Minute-level curve reconciliation against the backed-up pinned curve.
    curve_ref = pd.read_parquet(
        RE.PATHS.BASELINES / "fma2" / "v34_s10_pin_curve.parquet")
    eq, wo = res["curves"]["equity"], res["curves"]["worst"]
    idx_ok = eq.index.equals(curve_ref.index)
    d_eq = float(np.abs(eq.to_numpy() - curve_ref["equity"].to_numpy()).max()) \
        if idx_ok else float("nan")
    d_wo = float(np.abs(wo.to_numpy() - curve_ref["worst"].to_numpy()).max()) \
        if idx_ok else float("nan")
    curve_ok = idx_ok and d_eq <= 1e-6 and d_wo <= 1e-6

    print(f"\n{'metric':<22}{'got':>20}{'reference':>20}{'delta':>14}  ok")
    for name, got, want, d, ok in rows:
        print(f"{name:<22}{got:>20.10f}{want:>20.10f}{d:>14.3e}  "
              f"{'PASS' if ok else 'FAIL'}")
    print(f"{'neg_quarters==[2023Q1]':<22}{str(res['neg_quarters']):>40}  "
          f"{'PASS' if neg_q_ok else 'FAIL'}")
    print(f"{'neg_years==[]':<22}{str(res['neg_years']):>40}  "
          f"{'PASS' if neg_y_ok else 'FAIL'}")
    print(f"curve idx match {idx_ok} | max|d equity| {d_eq:.3e} "
          f"| max|d worst| {d_wo:.3e}  {'PASS' if curve_ok else 'FAIL'}")

    all_ok = all(r[4] for r in rows) and neg_q_ok and neg_y_ok and curve_ok

    out_dir = RE.PATHS.OUTPUTS
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "reconciled" if all_ok else "FAILED",
        "reference": str(ref_path),
        "label": res["label"],
        "checks": [{"metric": n, "got": g, "reference": w, "delta": d,
                    "ok": ok} for n, g, w, d, ok in rows],
        "neg_quarters": res["neg_quarters"],
        "neg_years": res["neg_years"],
        "curve_max_abs_delta": {"equity": d_eq, "worst": d_wo,
                                "index_match": bool(idx_ok)},
        "runtime_sec": round(time.time() - t0, 1),
    }
    out_path = out_dir / "verify_record_engine.json"
    out_path.write_text(json.dumps(report, indent=1))
    print(f"\n{'RECONCILED' if all_ok else 'FAILED'} "
          f"({report['runtime_sec']:.0f}s) -> {out_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
