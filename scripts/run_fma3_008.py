#!/usr/bin/env python3
"""FMA3-008 grid: the H-FTMO-1 daily circuit breaker under model v3.

The hook (record_engine_ext daily_stop_x) is built and its identity gate
PASSED bit-identically on both off-paths (ftmo_campaign.log 19:16/19:21).
This runner executes the pre-registered evaluation:

  GRID: (w=0.70) x s in {0.5, 0.6, 0.7} x x in {3.0, 3.5, 4.0}%  (9 passes)
  WALK-UP: if any cell compliant -> s in {0.8, 0.9} at the best x.
  CELL SELECTION (committed before any cell ran): among compliant cells pick
  max s; tie-break lowest P(breach12m), then fewest daily stops.
  PROBES: both +-20% w at the selected cell, walking DOWN compliant cells
  until probe-robust (FMA3-005c standing amendment).
  BAR (locked 19:11): probe-robust CAGR >= +0.3867 (FMA3-009 ship +8pp) at
  P(breach12m) <= 0.05 -> ADOPT (guardian goes into the unified EA); else
  DECLINE honestly (re-entry cost / gap-through residual eating the edge is
  a valid result).

Per-cell reporting: score_v3 blocks + n_daily_stops + re-entry cost
(CAGR delta vs the no-breaker grid cell) + residual >5% dip days.
Writes research/outputs/fma3_008_results.json + registry-ready summary.
Runtime ~90-105 min.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))

import record_engine as RE                      # noqa: E402 (paths)
from record_engine_ext import run_record_ext    # noqa: E402
from run_hrisk1 import static_fed               # noqa: E402
from ftmo_model_v3 import score_v3              # noqa: E402

INITIAL = 100_000.0
BAR_CAGR, BAR_P = 0.3867, 0.05
S_GRID, X_GRID = (0.5, 0.6, 0.7), (3.0, 3.5, 4.0)
WALK_UP = (0.8, 0.9)
W_LOCKED, W_PROBES = 0.70, (0.56, 0.84)
NO_BREAKER_CAGR = {0.5: 0.3969, 0.6: 0.4909, 0.7: 0.5932,
                   0.8: 0.6956, 0.9: None}


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [FMA3-008] {msg}", flush=True)


def run_cell(fed_base: pd.DataFrame, s: float, x: float, w: float,
             tag: str) -> dict:
    res = run_record_ext(fed_base * s, initial=INITIAL, daily_stop_x=x,
                         label=tag, verbose=False, run_bootstrap=False)
    eq, wo = res["curves"]["equity"], res["curves"]["worst"]
    sc = score_v3(eq, wo)
    stops = res["engine_metrics"].get("n_daily_stops")
    nb = NO_BREAKER_CAGR.get(s)
    cost_pp = None if nb is None else (nb - res["cagr"]) * 100
    row = {"w": w, "s": s, "x": x, "cagr": res["cagr"],
           "maxdd_worst": res["maxdd_worst"], "n_daily_stops": stops,
           "reentry_cost_pp": cost_pp, **sc}
    pd.DataFrame({"equity": eq, "worst": wo}).to_parquet(
        RE.PATHS.OUTPUTS / f"{tag}_curve.parquet")
    del res["curves"]
    h = sc["historical"]
    log(f"{tag} | CAGR {row['cagr']:+.4f} | stops {stops} | cost "
        f"{cost_pp if cost_pp is None else round(cost_pp,2)}pp | residual "
        f"dips {h['daily_dip_gt5pct']} | floorLo {h.get('worst_month_floor_touch', h.get('monthFloorLo','?'))} "
        f"| P(breach) {sc['bootstrap']['p_breach_12m']:.4f} | "
        f"{'COMPLIANT' if sc['compliant'] else 'fails'}")
    return row


def main() -> int:
    t0 = time.time()
    log("grid start — hook identity gate already PASSED (19:21)")
    fed = static_fed(W_LOCKED)
    out = {"bar": {"cagr_ge": BAR_CAGR, "p_le": BAR_P},
           "grid": {}, "walk_up": {}, "probes": {}, "verdict": None}

    for s in S_GRID:
        for x in X_GRID:
            tag = f"fma3008_s{int(s*100)}_x{int(x*10)}"
            out["grid"][tag] = run_cell(fed, s, x, W_LOCKED, tag)

    compliant = [v for v in out["grid"].values() if v["compliant"]]
    if compliant:
        best_x = sorted(compliant, key=lambda v: (-v["s"],
                        v["bootstrap"]["p_breach_12m"],
                        v["n_daily_stops"] or 0))[0]["x"]
        for s in WALK_UP:
            tag = f"fma3008_s{int(s*100)}_x{int(best_x*10)}"
            row = run_cell(fed, s, best_x, W_LOCKED, tag)
            out["walk_up"][tag] = row
            if not row["compliant"]:
                break

    all_cells = list(out["grid"].values()) + list(out["walk_up"].values())
    ranked = sorted([v for v in all_cells if v["compliant"]],
                    key=lambda v: (-v["s"], v["bootstrap"]["p_breach_12m"],
                                   v["n_daily_stops"] or 0))
    ship = None
    for cand in ranked:                       # walk-down until probe-robust
        s, x = cand["s"], cand["x"]
        ok = True
        for wp in W_PROBES:
            tag = f"fma3008_probe_w{int(wp*100)}_s{int(s*100)}_x{int(x*10)}"
            row = run_cell(static_fed(wp), s, x, wp, tag)
            out["probes"][tag] = row
            ok = ok and row["compliant"]
        if ok:
            ship = cand
            break

    if ship and ship["cagr"] >= BAR_CAGR \
            and ship["bootstrap"]["p_breach_12m"] <= BAR_P:
        out["verdict"] = {"decision": "ADOPT", "s": ship["s"], "x": ship["x"],
                          "cagr": ship["cagr"],
                          "gain_pp_vs_009": (ship["cagr"] - 0.3067) * 100,
                          "note": "guardian module goes into the unified EA"}
    elif ship:
        out["verdict"] = {"decision": "DECLINE (bar miss)",
                          "best_probe_robust": {k: ship[k] for k in
                                                ("s", "x", "cagr")},
                          "gain_pp_vs_009": (ship["cagr"] - 0.3067) * 100}
    else:
        out["verdict"] = {"decision": "DECLINE (no probe-robust cell)"}

    (RE.PATHS.OUTPUTS / "fma3_008_results.json").write_text(
        json.dumps(out, indent=1, default=str))
    log(f"DONE ({time.time()-t0:.0f}s) | {out['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
