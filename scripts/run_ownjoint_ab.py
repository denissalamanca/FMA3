#!/usr/bin/env python3
"""OWN-vs-JOINT A/B — STAGE 2: replay both frac matrices through the SAME
record engine on the SAME basis (warmup, feed, friction, dial).

Process B: imports record_engine ONLY (stop_out=0.50). Never co-import
engine/v7_bridge here.

OWN  = v7_book_frac_1h_ab.parquet  (standalone-equity leverage; == existing
       v7_book_frac_1h, gated in Stage 1)
JOINT= v7_book_tgt_1h_ab.parquet   (constant blended leverage)

Metrics per (regime, dial): CAGR, worst-mark MaxDD, Sharpe, desired peak joint
margin load (analytic = max_t sum_k |frac_k*s|/lev_k; the record engine's own
margin_cap=0.9 clamps realized load at 0.9 — a JOINT load > 0.9 means that
governor binds). Per-episode worst-mark DD on COVID and the 2022 carry cluster.
Matrix spot-check R = F_joint/F_own at the May/Jul-2022 USDJPY carry episodes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))

import record_engine as RE  # noqa: E402
import core                 # noqa: E402
from run_hfed1_lib import crisis_tail  # noqa: E402

OUT = RE.PATHS.OUTPUTS
LEV = None  # filled after columns known

# episode windows (server time)
COVID = (pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-15"))
CARRY = (pd.Timestamp("2022-04-15"), pd.Timestamp("2022-08-15"))   # May+Jul '22
CARRY_FULL = (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31"))  # cluster


def window_dd(eq_c: pd.Series, eq_w: pd.Series, lo, hi) -> float:
    """Worst-mark DD inside [lo,hi] vs the running ALL-history close peak."""
    peak = eq_c.cummax()
    win = (eq_w.index >= lo) & (eq_w.index <= hi)
    if not win.any():
        return float("nan")
    return float(((peak[win] - eq_w[win]) / peak[win]).max())


def peak_load(frac: pd.DataFrame, s: float, lev: pd.Series, lo, hi) -> float:
    m = (frac.index >= lo) & (frac.index <= hi)
    load = (frac.loc[m].abs() * s).div(lev).sum(axis=1)
    return float(load.max())


def one(frac: pd.DataFrame, s: float, lev, regime, label: str) -> dict:
    sq, eq_end = regime
    res = RE.run_record(frac * s, start_quarter=sq, end_quarter="2025Q4",
                        label=label, verbose=False, run_bootstrap=False)
    ec, ew = res["curves"]["equity"], res["curves"]["worst"]
    lo = pd.Period(sq, "Q").start_time
    hi = pd.Period("2025Q4", "Q").end_time
    row = {
        "label": label, "s": s, "start_quarter": sq,
        "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
        "sharpe": res["sharpe"], "final_equity": res["final_equity"],
        "peak_margin_load": peak_load(frac, s, lev, lo, hi),
        "dd_covid": window_dd(ec, ew, *COVID),
        "dd_carry_maysep22": window_dd(ec, ew, *CARRY),
        "dd_carry_cluster_2223": window_dd(ec, ew, *CARRY_FULL),
        "neg_quarters": res["neg_quarters"],
    }
    pd.DataFrame({"equity": ec, "worst": ew}).to_parquet(
        OUT / f"{label}_curve.parquet")
    print(f"[{label}] CAGR {res['cagr']:+.4f} DDw {res['maxdd_worst']:.4f} "
          f"Sh {res['sharpe']:.3f} load {row['peak_margin_load']:.3f} "
          f"covid {row['dd_covid']:.4f} carry {row['dd_carry_maysep22']:.4f}",
          flush=True)
    return row


def spotcheck(f_own, f_joint) -> dict:
    """Pure-matrix R = F_joint/F_own at the USDJPY carry episodes."""
    out = {}
    for tag, lo, hi in (("may2022", "2022-05-01", "2022-05-20"),
                        ("jul2022", "2022-07-01", "2022-07-31")):
        o = f_own["USDJPY"].loc[lo:hi]
        j = f_joint["USDJPY"].loc[lo:hi]
        # peak-exposure bar in the window (by |F_own|)
        idx = o.abs().idxmax()
        r_at_peak = float(j.loc[idx] / o.loc[idx]) if o.loc[idx] != 0 else float("nan")
        # robust: ratio at bars where both meaningfully nonzero
        mask = o.abs() > 0.1
        r_series = (j[mask] / o[mask]).replace([np.inf, -np.inf], np.nan).dropna()
        out[tag] = {"peak_bar": str(idx),
                    "F_own_at_peak": float(o.loc[idx]),
                    "F_joint_at_peak": float(j.loc[idx]),
                    "R_at_peak": r_at_peak,
                    "R_median": float(r_series.median()),
                    "R_p90": float(r_series.quantile(0.9))}
    return out


def main() -> int:
    f_own = pd.read_parquet(OUT / "v7_book_frac_1h_ab.parquet")
    f_joint = pd.read_parquet(OUT / "v7_book_tgt_1h_ab.parquet")
    cols = sorted(set(f_own.columns) | set(f_joint.columns))
    f_own = f_own.reindex(columns=cols, fill_value=0.0)
    f_joint = f_joint.reindex(columns=cols, fill_value=0.0)
    lev = pd.Series({c: float(core.S.INSTRUMENTS[c]["leverage"]) for c in cols})

    sc = spotcheck(f_own, f_joint)
    print("SPOT-CHECK R=F_joint/F_own (expect ~2.25 May, ~3.3 Jul):", flush=True)
    for k, v in sc.items():
        print(f"  {k}: R_at_peak {v['R_at_peak']:.3f} (own {v['F_own_at_peak']:.3f}"
              f" -> joint {v['F_joint_at_peak']:.3f}) | R_med {v['R_median']:.3f}",
              flush=True)

    regimes = {"cold": ("2020Q1", "2025Q4"), "warm": ("2021Q1", "2025Q4")}
    dials = [1.0, 1.6]
    results = {"spotcheck": sc, "cold": {}, "warm": {}}
    for rname, reg in regimes.items():
        for s in dials:
            si = int(round(s * 100))
            results[rname][f"own_s{si}"] = one(
                f_own, s, lev, reg, f"oj_{rname}_own_s{si}")
            results[rname][f"joint_s{si}"] = one(
                f_joint, s, lev, reg, f"oj_{rname}_joint_s{si}")

    (OUT / "ownjoint_ab_results.json").write_text(
        json.dumps(results, indent=1, default=str))
    print("\nDONE -> ownjoint_ab_results.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
