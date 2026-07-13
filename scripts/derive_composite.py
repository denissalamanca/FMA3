#!/usr/bin/env python3
"""FMA3-000b: composite benchmark + M-0 measurements.

Measures BOTH parent books in the engine of record (Python 1m worst-mark,
single cross-margined account, IC feed, 2020-2025, EUR 10k) and derives the
composite gates per research/protocol/PROTOCOL.md §2. Also computes the M-0
measurement block (research/protocol/HYPOTHESES.md) — book-level correlation,
co-drawdown, exposure overlap, duplicate-edge check — which gates whether the
federation thesis proceeds.

Parents measured:
  * v3.4 @ scale 10 — cited from the pinned reference (byte-reproduced twice
    today); crisis tail computed from the backed-up pinned curve.
  * v7.0 band book — the R8-anchored extracted fraction matrix
    (research/outputs/v7_book_frac_1h.parquet) run at scale multipliers
    s/8 for s in {8, 9, 10}.  s=8 is EXACT (the byte-reconciled anchor
    expressed in record accounting); s in {9, 10} are LINEAR approximations
    (the native book's per-sleeve caps do not rescale linearly) — labeled so.

Crisis tail convention (pre-registered): max over t in the COVID window
[2020-02-15, 2020-04-15] of (running_peak_close(<=t) - worst(t)) /
running_peak_close(<=t) — i.e. the worst-mark drawdown whose trough lies in
the window, against the all-history-to-date close peak.

Run AFTER scripts/verify_record_engine.py has printed RECONCILED:
  python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/derive_composite.py
Runtime ~20 min (3 engine passes + 3 bootstraps). Single process.
Writes research/outputs/composite_benchmark.json.
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

COVID_LO, COVID_HI = pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-15")


def crisis_tail(eq_close: pd.Series, eq_worst: pd.Series) -> float:
    """Worst-mark COVID-window drawdown vs the running all-history close peak."""
    peak = eq_close.cummax()
    win = (eq_worst.index >= COVID_LO) & (eq_worst.index <= COVID_HI)
    dd = (peak[win] - eq_worst[win]) / peak[win]
    return float(dd.max())


def metric_block(res: dict, tail: float, note: str = "") -> dict:
    return {
        "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
        "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
        "crisis_tail": tail, "final_equity": res["final_equity"],
        "n_trades": res["n_trades"], "yearly": res["yearly"],
        "neg_years": res["neg_years"], "neg_quarters": res["neg_quarters"],
        "n_neg_quarters": res["n_neg_quarters"],
        "breach": res["breach"], "note": note,
    }


def daily_close(eq: pd.Series) -> pd.Series:
    return eq.resample("1D").last().dropna()


def main() -> int:
    t0 = time.time()
    out: dict = {"generated": pd.Timestamp.now().isoformat(),
                 "engine": "FMA2 account_engine_1m via FMA3 record_engine",
                 "sample": "2020Q1..2025Q4, IC feed, EUR 10k"}

    # ---- v3.4: cited from the pinned reference -----------------------------
    ref = json.loads((RE.PATHS.BASELINES / "fma2" / "v34_s10_pin_1m.json")
                     .read_text())
    curve34 = pd.read_parquet(
        RE.PATHS.BASELINES / "fma2" / "v34_s10_pin_curve.parquet")
    tail34 = crisis_tail(curve34["equity"], curve34["worst"])
    pin = ref["pin"]
    out["v34_record"] = {
        "cagr": pin["cagr"], "maxdd_worst": pin["maxdd"],
        "sharpe": pin["sharpe"], "crisis_tail": tail34,
        "final_equity": pin["final_equity"], "n_trades": pin["n_trades"],
        "yearly": pin["yearly"],
        "neg_years": [], "neg_quarters": ["2023Q1"],
        "n_neg_quarters": pin["n_neg_quarters"],
        "breach": ref["breach"],
        "note": "pinned reference, byte-reproduced 2026-07-10 (twice)",
    }
    print(f"[v34] cited pin; crisis_tail={tail34:.4f}", flush=True)

    # ---- v7.0 at s in {8,9,10} ---------------------------------------------
    frac = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_frac_1h.parquet")
    v7 = {}
    curves_v7_r8 = None
    for s in (8, 9, 10):
        lbl = f"v7_record_r{s}"
        print(f"[{lbl}] engine pass ({time.time()-t0:.0f}s elapsed) ...",
              flush=True)
        res = RE.run_record(frac * (s / 8.0), label=lbl, verbose=False)
        tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
        v7[f"r{s}"] = metric_block(
            res, tail,
            note=("EXACT: byte-reconciled R8 anchor in record accounting"
                  if s == 8 else
                  "linear approximation (native caps do not rescale)"))
        print(f"[{lbl}] CAGR {res['cagr']:+.4f} | DDworst "
              f"{res['maxdd_worst']:.4f} | Sharpe {res['sharpe']:.4f} | "
              f"tail {tail:.4f} | negQ {res['n_neg_quarters']} | "
              f"breach {res['breach']['breach_worst']:.4f}", flush=True)
        if s == 8:
            curves_v7_r8 = {k: v.copy() for k, v in res["curves"].items()}
        del res["curves"]

    out["v7_record"] = v7

    # ---- composite gates: dimension-wise best of parents -------------------
    # Parent points considered: v34@s10 and the EXACT v7 point (r8). The
    # r9/r10 approximations are reported but do NOT set gates (pre-registered:
    # gates come from measured parents, not approximations).
    p34, p7 = out["v34_record"], v7["r8"]
    out["composite_gates"] = {
        "cagr_gt": max(p34["cagr"], p7["cagr"]),
        "maxdd_worst_lt": min(p34["maxdd_worst"], p7["maxdd_worst"]),
        "sharpe_gt": max(p34["sharpe"], p7["sharpe"]),
        "crisis_tail_le": min(p34["crisis_tail"], p7["crisis_tail"]),
        "neg_years_eq": 0,
        "neg_quarters_le": min(p34["n_neg_quarters"], p7["n_neg_quarters"]),
        "breach_lt": min(p34["breach"]["breach_worst"],
                         p7["breach"]["breach_worst"]),
        "basis": "dimension-wise best of v34@s10 (pin) and v7@r8 (exact) "
                 "in the engine of record",
    }
    out["original_user_gates"] = {
        "cagr": 0.961, "dd": 0.209, "sharpe": 2.03, "crisis": 0.356,
        "negY": 0, "negQ": 1,
        "note": "straddle two engines (MT5 real-tick R10 vs Python 1m "
                "worst-mark) — secondary scoreboard",
    }

    # ---- M-0 measurements ---------------------------------------------------
    print(f"[m0] measurements ({time.time()-t0:.0f}s elapsed) ...", flush=True)
    d34 = daily_close(curve34["equity"])
    d7 = daily_close(curves_v7_r8["equity"])
    idx = d34.index.intersection(d7.index)
    r34, r7 = d34[idx].pct_change().dropna(), d7[idx].pct_change().dropna()
    ridx = r34.index.intersection(r7.index)
    r34, r7 = r34[ridx], r7[ridx]

    rho_full = float(np.corrcoef(r34, r7)[0, 1])
    rho_yearly = {int(y): float(np.corrcoef(r34[r34.index.year == y],
                                            r7[r7.index.year == y])[0, 1])
                  for y in sorted(set(r34.index.year))}

    # each book's return on the other's 10 worst days
    w7_days = r7.nsmallest(10).index
    w34_days = r34.nsmallest(10).index
    on_worst = {
        "v34_ret_on_v7_10worst": float(r34[w7_days].mean()),
        "v7_ret_on_v34_10worst": float(r7[w34_days].mean()),
        "v7_10worst": {str(d.date()): [float(r7[d]), float(r34[d])]
                       for d in w7_days},
    }

    # co-drawdown: each book's own DD state on the day the other trough'd
    dd34 = 1 - d34 / d34.cummax()
    dd7 = 1 - d7 / d7.cummax()
    co_dd = {
        "v34_dd_at_v7_trough": float(dd34.reindex([dd7.idxmax()],
                                                  method="ffill").iloc[0]),
        "v7_dd_at_v34_trough": float(dd7.reindex([dd34.idxmax()],
                                                 method="ffill").iloc[0]),
        "v7_trough": str(dd7.idxmax().date()),
        "v34_trough": str(dd34.idxmax().date()),
    }

    # quarterly M2M side-by-side
    q34 = d34.resample("QE").last().pct_change().dropna()
    q7 = d7.resample("QE").last().pct_change().dropna()
    qmat = {str(pd.Period(k, freq="Q")): [float(q7.get(k, np.nan)),
                                          float(q34.get(k, np.nan))]
            for k in q7.index.union(q34.index)}

    # exposure overlap: mean |frac| per instrument, both books
    v34frac = books.build_v34_frac_1h()
    common_idx = frac.index.intersection(v34frac.index)
    ov = {}
    for inst in sorted(set(frac.columns) | set(v34frac.columns)):
        a = frac[inst].reindex(common_idx).fillna(0).abs() \
            if inst in frac.columns else pd.Series(0.0, index=common_idx)
        b = v34frac[inst].reindex(common_idx).fillna(0).abs() \
            if inst in v34frac.columns else pd.Series(0.0, index=common_idx)
        if a.mean() > 1e-4 or b.mean() > 1e-4:
            ov[inst] = {"v7_mean_absfrac": float(a.mean()),
                        "v34_mean_absfrac": float(b.mean()),
                        "both_active_share": float(
                            ((a > 1e-6) & (b > 1e-6)).mean())}

    # duplicate-edge check: v7 USTEC exposure vs FMA2 intraday USTEC position
    intr = pd.read_parquet(RE.PATHS.FMA2_SLEEVE_OUTPUTS / "intraday_pos.parquet")
    dup = {}
    if "USTEC" in intr.columns and "USTEC" in frac.columns:
        a = frac["USTEC"].reindex(common_idx).fillna(0)
        b = intr["USTEC"].reindex(common_idx).fillna(0)
        both = (a.abs() > 1e-6) & (b.abs() > 1e-6)
        dup = {"hours_both_active_share": float(both.mean()),
               "rho_on_both_active": float(np.corrcoef(a[both], b[both])[0, 1])
               if both.sum() > 100 else None}

    out["m0"] = {
        "rho_daily_full": rho_full, "rho_daily_by_year": rho_yearly,
        "on_worst_days": on_worst, "co_drawdown": co_dd,
        "quarterly_matrix_v7_v34": qmat,
        "exposure_overlap": ov,
        "duplicate_edge_ustec": dup,
        "note": "measurement only (no adoption decision) per HYPOTHESES.md M-0",
    }

    out_path = RE.PATHS.OUTPUTS / "composite_benchmark.json"
    out_path.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nDONE ({time.time()-t0:.0f}s) -> {out_path}", flush=True)
    print(json.dumps(out["composite_gates"], indent=1), flush=True)
    print(f"rho_full={rho_full:+.3f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
