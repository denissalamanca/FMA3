#!/usr/bin/env python3
"""FTMO 1%-idea kill engine (RULE v0.2, trailing-window) — gate then sweep.

GATE (non-negotiable, before ANY kill-on number): kill_pct=None,
violations_only=False must reproduce the FTMO golden of
model/v3/reproduce.py:99-104 — final_equity == 1332404.1921628967 EXACTLY
(also maxdd_worst 0.13326785098278104, n_daily_stops == 26). Any inequality
aborts the sweep.

SWEEP (all at s=0.70 x fed(w=0.70), initial 100k, daily_stop_x=3.0,
ref = CURRENT balance), priority order:
  (a) kill_pct=0.008 net   [PRIMARY]
  (b) kill_pct=0.006 net
  (c) kill_pct=0.008 loss_only
  (d) kill_pct=0.010 net
  (e) NO-KILL violations-only census (how non-compliant the raw book is)

Run: python3 research/ftmo1pct/run_sweep.py [--gate-only] [--runs a,b,...]
Out: research/ftmo1pct/out/sweep_results_v02.json (+ per-run curves parquet)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "model" / "v3"))

import kill_engine as KE            # noqa: E402  (bootstraps engine path)
import reproduce as M               # noqa: E402  model/v3 golden definition

GOLD_FINAL = 1_332_404.1921628967
GOLD_MAXDD = 0.13326785098278104
GOLD_NSTOPS = 26
OUT = HERE / "out"
YEARS = 6.0                          # 2020-2025 window

#        tag   kill_pct  real_mode    violations_only
SWEEP = [("f_knee_70bp", 0.007, "net", False, 3.0),
         ("a", 0.008,    "net",       False, 3.0),
         ("b", 0.006,    "net",       False, 3.0),
         ("c", 0.008,    "loss_only", False, 3.0),
         ("d", 0.010,    "net",       False, 3.0),
         ("e", None,     "net",       True,  3.0),
         ("g_90bp_ds30", 0.009, "net", False, 3.0),
         ("h_80bp_ds40", 0.008, "net", False, 4.0),
         ("i_90bp_ds40", 0.009, "net", False, 4.0)]


def jrow(r: dict) -> dict:
    k = r["kill"]
    return {"label": r["label"], "kill_pct": k["kill_pct"],
            "real_mode": k["real_mode"],
            "violations_only": k["violations_only"],
            "final_equity": r["final_equity"], "cagr": r["cagr"],
            "maxdd_worst": r["maxdd_worst"], "maxdd_close": r["maxdd_close"],
            "sharpe": r["sharpe"], "n_daily_stops": r["n_daily_stops"],
            "n_trades": r["n_trades"],
            "n_kills_total": k["n_kills_total"],
            "kills_by_cluster": k["kills_by_cluster"],
            "violations_total": k["violations_total"],
            "violations_by_cluster": k["violations_by_cluster"],
            "pend_check": {kk: vv for kk, vv in k["pend_check"].items()
                           if kk != "flushed_by_cluster"},
            "yearly": r["yearly"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate-only", action="store_true")
    ap.add_argument("--runs", default="a,b,c,d,e")
    args = ap.parse_args()
    wanted = set(args.runs.split(","))
    OUT.mkdir(exist_ok=True)
    t0 = time.time()

    print("building fed = static_blend(0.70) ...", flush=True)
    fed = M.static_blend(M.CORE_WEIGHT)
    print(f"fed: {fed.shape[0]} hours x {fed.shape[1]} symbols", flush=True)
    cid, names = KE.build_cluster_id(list(fed.columns))
    print(f"cluster map OK: {len(names)} clusters over {len(fed.columns)} "
          f"columns: {names}", flush=True)

    rfile = OUT / "sweep_results_v02.json"
    results: dict = {"gate": None, "sweep": {}}
    if rfile.exists():
        results = json.loads(rfile.read_text())

    # ---- GATE: overlay-off must be bit-exact vs the FTMO golden ----------
    print("\n=== GATE: kill OFF @ s=0.70, 100k, daily_stop_x=3.0 ===",
          flush=True)
    r0 = KE.run_record_kill(fed * 0.7, initial=100_000.0, daily_stop_x=3.0,
                            kill_pct=None, label="ftmo1pct_gate_killoff",
                            verbose=True)
    fe = r0["final_equity"]
    bit_equal = (fe == GOLD_FINAL)
    delta = fe - GOLD_FINAL
    print(f"final_equity   = {fe!r}")
    print(f"golden target  = {GOLD_FINAL!r}")
    print(f"bit-equal      = {bit_equal}   delta = {delta!r}")
    print(f"maxdd_worst    = {r0['maxdd_worst']!r} (target {GOLD_MAXDD!r})")
    print(f"n_daily_stops  = {r0['n_daily_stops']} (target {GOLD_NSTOPS})")
    results["gate"] = {"final_equity": fe, "target": GOLD_FINAL,
                       "bit_equal": bool(bit_equal), "delta": delta,
                       "maxdd_worst": r0["maxdd_worst"],
                       "n_daily_stops": r0["n_daily_stops"],
                       "n_trades": r0["n_trades"]}
    rfile.write_text(json.dumps(results, indent=1, default=str))
    if (not bit_equal or r0["n_daily_stops"] != GOLD_NSTOPS
            or r0["maxdd_worst"] != GOLD_MAXDD):
        print("\nGATE FAILED — STOPPING before any kill-on number.")
        return 1
    print(f"GATE PASSED ({time.time()-t0:.0f}s)\n", flush=True)
    if args.gate_only:
        return 0

    # ---- SWEEP ------------------------------------------------------------
    base_cagr = r0["cagr"]
    for tag, kp, mode, vonly, dsx in SWEEP:
        if tag not in wanted:
            continue
        lbl = (f"ftmo1pct_{tag}_viol_census" if vonly
               else f"ftmo1pct_{tag}_{mode}_{int(kp*10000)}bp")
        print(f"=== SWEEP ({tag}) kill_pct={kp} real_mode={mode} "
              f"violations_only={vonly} ===", flush=True)
        t1 = time.time()
        r = KE.run_record_kill(fed * 0.7, initial=100_000.0, daily_stop_x=dsx,
                               kill_pct=kp, real_mode=mode,
                               violations_only=vonly, label=lbl,
                               verbose=True)
        row = jrow(r)
        row["retention_vs_nokill"] = r["final_equity"] / GOLD_FINAL
        row["cagr_delta_pp"] = (r["cagr"] - base_cagr) * 100.0
        row["kills_per_year"] = row["n_kills_total"] / YEARS
        row["violations_per_year"] = row["violations_total"] / YEARS
        results["sweep"][lbl] = row
        pd.DataFrame({"equity": r["curves"]["equity"],
                      "worst": r["curves"]["worst"]}).to_parquet(
            OUT / f"{lbl}_curve.parquet")
        rfile.write_text(json.dumps(results, indent=1, default=str))
        top5 = sorted(row["kills_by_cluster"].items(),
                      key=lambda x: -x[1])[:5]
        pc = row["pend_check"]
        print(f"  final €{r['final_equity']:,.0f} "
              f"(retention {row['retention_vs_nokill']:.3f}) | kills "
              f"{row['n_kills_total']} ({row['kills_per_year']:.1f}/yr) "
              f"top5 {top5} | stops {r['n_daily_stops']} | DDw "
              f"{r['maxdd_worst']:.4f} | VIOLATIONS {row['violations_total']} "
              f"({row['violations_per_year']:.1f}/yr) | pend resid "
              f"{pc['identity_residual']:.3e} | {time.time()-t1:.0f}s\n",
              flush=True)

    print(f"DONE ({time.time()-t0:.0f}s) -> {rfile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
