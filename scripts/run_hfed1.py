#!/usr/bin/env python3
"""FMA3-001: H-FED-1 — static blend (no cross-book rebalance).

Pre-registered in research/protocol/HYPOTHESES.md BEFORE any merged number
was computed. Grid w in {0.30, 0.40, 0.50, 0.60, 0.70} (v7 share), each book
at its native operating point (v7 @ R8-anchor extraction, v3.4 @ scale 10).

MECHANICS — virtual sub-account bookkeeping
-------------------------------------------
Each book compounds its own sub-capital independently; neither book's internal
state sees the other's P&L (the PROTOCOL §5.7 anti-coupling guard holds by
construction). The joint target fraction at hour h is the capital-weighted
blend of the parents' native fractions:

    book_frac_h = fracV7_h * (w * A_h / J_h) + fracV34_h * ((1-w) * B_h / J_h)

where A_h, B_h are the parents' NATIVE equity curves normalized to 1.0 at t0
(both byte-reconciled artifacts: v7_book_equity_1m.parquet eqc and the pinned
v34_s10_pin_curve.parquet equity), sampled causally at hour h (last known 1m
value <= h; the engine lags row h into hour h+1's first minute), and
J_h = w*A_h + (1-w)*B_h is the ideal joint curve.

The record engine then simulates the ACTUAL combined account — joint margin,
joint stop-out, real fills/costs on the blended targets (cross-book netting
on shared instruments, e.g. USDJPY, is real and is measured, not assumed).
The realized joint curve may drift from the ideal J; the drift is reported
(ideal-vs-realized CAGR/DD deltas) as the blend-friction measurement.

PRE-REGISTERED BARS (H-FED-1, all must pass at >=1 grid point):
  combined worst-mark DD  < min(parent DDs in record engine) - 0.5pp
  combined Sharpe         > max(parent Sharpes) + 0.05
  neg years               == 0
  neg quarters            <= min(parents)
CAGR is NOT a bar here (bought later with scale, H-FED-3).

Run: python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/run_hfed1.py
Runtime ~35 min (5 engine passes + bootstraps). Single process. Writes
research/outputs/hfed1_results.json.
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

W_GRID = (0.30, 0.40, 0.50, 0.60, 0.70)   # v7 share; pre-registered, fixed
COVID_LO, COVID_HI = pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-15")


def crisis_tail(eq_close: pd.Series, eq_worst: pd.Series) -> float:
    peak = eq_close.cummax()
    win = (eq_worst.index >= COVID_LO) & (eq_worst.index <= COVID_HI)
    dd = (peak[win] - eq_worst[win]) / peak[win]
    return float(dd.max())


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Native frac matrices + native equity curves normalized to 1.0 at t0."""
    core_frac = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_frac_1h.parquet")
    sat_frac = books.build_sat_frac_1h()
    core_eq = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_equity_1m.parquet")["eqc"]
    sat_eq = pd.read_parquet(
        RE.PATHS.BASELINES / "fma2" / "v34_s10_pin_curve.parquet")["equity"]
    return core_frac, sat_frac, core_eq / core_eq.iloc[0], sat_eq / sat_eq.iloc[0]


def build_book_frac(core_frac: pd.DataFrame, sat_frac: pd.DataFrame,
                   a: pd.Series, b: pd.Series, w: float
                   ) -> tuple[pd.DataFrame, pd.Series]:
    """Blend the parents' fraction matrices by causal sub-equity weights."""
    hours = core_frac.index.union(sat_frac.index)
    # causal hourly sample: last native 1m equity value at or before hour h
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours)
    # before a book's first bar, its sub-equity is its seed (=1.0 normalized)
    a_h, b_h = a_h.fillna(1.0), b_h.fillna(1.0)
    j_h = w * a_h + (1.0 - w) * b_h
    wa = (w * a_h / j_h)
    wb = ((1.0 - w) * b_h / j_h)
    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat = sat_frac.reindex(hours).fillna(0.0)
    cols = sorted(set(f_core.columns) | set(f_sat.columns))
    fed = (f_core.reindex(columns=cols, fill_value=0.0).mul(wa, axis=0)
           + f_sat.reindex(columns=cols, fill_value=0.0).mul(wb, axis=0))
    ideal_daily = j_h.resample("1D").last().dropna()
    return fed, ideal_daily


def ideal_metrics(ideal_daily: pd.Series) -> dict:
    r = ideal_daily.pct_change().dropna()
    cum = ideal_daily / ideal_daily.iloc[0]
    yrs = (ideal_daily.index[-1] - ideal_daily.index[0]).days / 365.25
    return {
        "cagr": float(cum.iloc[-1] ** (1 / yrs) - 1),
        "maxdd_close": float((1 - cum / cum.cummax()).max()),
        "sharpe": float(r.mean() / r.std() * np.sqrt(252)),
    }


def main() -> int:
    t0 = time.time()
    print("[hfed1] loading inputs ...", flush=True)
    core_frac, sat_frac, a, b = load_inputs()

    # parent reference points (engine of record) for the pre-registered bars
    comp = json.loads((RE.PATHS.OUTPUTS / "composite_benchmark.json")
                      .read_text())
    p34, p7 = comp["v34_record"], comp["v7_record"]["r8"]
    bars = {
        "dd_lt": min(p34["maxdd_worst"], p7["maxdd_worst"]) - 0.005,
        "sharpe_gt": max(p34["sharpe"], p7["sharpe"]) + 0.05,
        "neg_years_eq": 0,
        "neg_quarters_le": min(p34["n_neg_quarters"], p7["n_neg_quarters"]),
    }
    print(f"[hfed1] bars: DD<{bars['dd_lt']:.4f} Sharpe>{bars['sharpe_gt']:.3f}"
          f" negY==0 negQ<={bars['neg_quarters_le']}", flush=True)

    results = {"bars": bars, "grid": {}, "parents": {
        "v34_record": {k: p34[k] for k in
                       ("cagr", "maxdd_worst", "sharpe", "crisis_tail",
                        "n_neg_quarters")},
        "v7_record_r8": {k: p7[k] for k in
                         ("cagr", "maxdd_worst", "sharpe", "crisis_tail",
                          "n_neg_quarters")}}}

    for w in W_GRID:
        lbl = f"hfed1_w{int(w*100)}"
        print(f"[{lbl}] building blend + engine pass "
              f"({time.time()-t0:.0f}s elapsed) ...", flush=True)
        fed, ideal_daily = build_book_frac(core_frac, sat_frac, a, b, w)
        res = RE.run_record(fed, label=lbl, verbose=False)
        tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
        im = ideal_metrics(ideal_daily)
        passed = (res["maxdd_worst"] < bars["dd_lt"]
                  and res["sharpe"] > bars["sharpe_gt"]
                  and res["n_neg_years"] == bars["neg_years_eq"]
                  and res["n_neg_quarters"] <= bars["neg_quarters_le"])
        row = {
            "w_v7": w,
            "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
            "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
            "crisis_tail": tail, "final_equity": res["final_equity"],
            "n_trades": res["n_trades"],
            "neg_years": res["neg_years"],
            "neg_quarters": res["neg_quarters"],
            "n_neg_quarters": res["n_neg_quarters"],
            "breach": res["breach"],
            "yearly": res["yearly"],
            "ideal": im,
            "friction_cagr_pp": (res["cagr"] - im["cagr"]) * 100,
            "bars_pass": bool(passed),
        }
        results["grid"][lbl] = row
        print(f"[{lbl}] CAGR {res['cagr']:+.4f} | DDworst "
              f"{res['maxdd_worst']:.4f} | Sh {res['sharpe']:.3f} | "
              f"tail {tail:.4f} | negQ {res['n_neg_quarters']} | "
              f"breach {res['breach']['breach_worst']:.4f} | "
              f"friction {row['friction_cagr_pp']:+.2f}pp | "
              f"bars {'PASS' if passed else 'fail'}", flush=True)
        # persist the winning-candidate curves for later phases
        pd.DataFrame({"equity": res["curves"]["equity"],
                      "worst": res["curves"]["worst"]}).to_parquet(
            RE.PATHS.OUTPUTS / f"{lbl}_curve.parquet")
        del res["curves"]

    n_pass = sum(1 for r in results["grid"].values() if r["bars_pass"])
    results["verdict_hint"] = (
        f"{n_pass}/{len(W_GRID)} grid points pass all pre-registered bars")
    out = RE.PATHS.OUTPUTS / "hfed1_results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print(f"\nDONE ({time.time()-t0:.0f}s) -> {out}\n"
          f"{results['verdict_hint']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
