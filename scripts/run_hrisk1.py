#!/usr/bin/env python3
"""FMA3-004: H-RISK-1 — Preset 1 (private IC account) risk-budget re-lever.

Pre-registered in research/protocol/PRESETS.md (owner risk revision,
2026-07-10). Book unchanged (static fed w=0.70). Ceilings, at locked w AND
both ±20% w probes: worst-mark DD < 30% · crisis tail ≤ 30% · negY 0 ·
negQ ≤ 1 · breach P(maxDD>30%) ≤ 0.15. Grid extension s ∈ {1.5,1.6,1.7,1.8}
(s ≤ 1.4 already pinned in hfed3_results.json). Two-stage: base grid, then
probes at the largest compliant s and the next lower grid point. Ship the
largest s where base + both probes clear every ceiling.

Run: python3 scripts/run_hrisk1.py   (~55 min: up to 8 engine passes)
Writes research/outputs/hrisk1_results.json (+ curves per run).
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

import record_engine as RE  # noqa: E402
from run_hfed1_lib import load_inputs, crisis_tail  # noqa: E402

S_NEW = (1.5, 1.6, 1.7, 1.8)          # pre-registered extension
CEIL = {"dd": 0.30, "tail": 0.30, "negy": 0, "negq": 1, "breach": 0.15}
W_LOCKED, W_PROBES = 0.70, (0.56, 0.84)


def static_blend(w: float) -> pd.DataFrame:
    """Fresh-seed static blend matrix at share w (probe-compatible)."""
    core_frac, sat_frac, a, b = load_inputs()
    hours = core_frac.index.union(sat_frac.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat = sat_frac.reindex(hours).fillna(0.0)
    cols = sorted(set(f_core.columns) | set(f_sat.columns))
    return (f_core.reindex(columns=cols, fill_value=0.0).mul(w * a_h / j, axis=0)
            + f_sat.reindex(columns=cols, fill_value=0.0)
            .mul((1 - w) * b_h / j, axis=0))


def run_point(fed: pd.DataFrame, s: float, label: str) -> dict:
    res = RE.run_record(fed * s, label=label, verbose=False)
    tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
    ok = (res["maxdd_worst"] < CEIL["dd"] and tail <= CEIL["tail"]
          and res["n_neg_years"] == CEIL["negy"]
          and res["n_neg_quarters"] <= CEIL["negq"]
          and res["breach"]["breach_worst"] <= CEIL["breach"])
    row = {"s": s, "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
           "sharpe": res["sharpe"], "crisis_tail": tail,
           "final_equity": res["final_equity"],
           "neg_years": res["neg_years"],
           "neg_quarters": res["neg_quarters"],
           "n_neg_quarters": res["n_neg_quarters"],
           "breach": res["breach"], "yearly": res["yearly"],
           "compliant": bool(ok)}
    pd.DataFrame({"equity": res["curves"]["equity"],
                  "worst": res["curves"]["worst"]}).to_parquet(
        RE.PATHS.OUTPUTS / f"{label}_curve.parquet")
    print(f"[{label}] CAGR {res['cagr']:+.4f} | DDw {res['maxdd_worst']:.4f} "
          f"| Sh {res['sharpe']:.3f} | tail {tail:.4f} | "
          f"negQ {res['n_neg_quarters']} | "
          f"breach {res['breach']['breach_worst']:.4f} | "
          f"{'COMPLIANT' if ok else 'breaches ceiling'}", flush=True)
    del res["curves"]
    return row


def main() -> int:
    t0 = time.time()
    out = {"ceilings": CEIL, "base": {}, "probes": {}, "ship": None}
    fed_locked = static_blend(W_LOCKED)

    # Stage A — base grid at locked w
    for s in S_NEW:
        out["base"][f"s{int(round(s*100))}"] = run_point(
            fed_locked, s, f"hrisk1_s{int(round(s*100))}")

    # merge with the pinned <=1.4 frontier for candidate selection
    h3 = json.loads((RE.PATHS.OUTPUTS / "hfed3_results.json").read_text())
    frontier = {round(v["s"], 2): v["compliant"] or (
        v["maxdd_worst"] < CEIL["dd"] and v["crisis_tail"] <= CEIL["tail"]
        and not v["neg_years"] and v["n_neg_quarters"] <= CEIL["negq"]
        and v["breach"]["breach_worst"] <= CEIL["breach"])
        for v in h3["grid"].values()}
    frontier.update({round(v["s"], 2): v["compliant"]
                     for v in out["base"].values()})
    compliant_s = sorted(s for s, ok in frontier.items() if ok)
    if not compliant_s:
        out["ship"] = {"verdict": "NO COMPLIANT SCALE"}
    else:
        cands = [compliant_s[-1]]
        lower = [s for s in sorted(frontier) if s < cands[0]]
        if lower:
            cands.append(lower[-1])
        print(f"[hrisk1] Stage B probes at s in {cands}", flush=True)
        ship = None
        for s in cands:  # largest first
            probe_ok = True
            for wp in W_PROBES:
                lbl = f"hrisk1_probe_w{int(wp*100)}_s{int(round(s*100))}"
                row = run_point(static_blend(wp), s, lbl)
                out["probes"][lbl] = row
                probe_ok = probe_ok and row["compliant"]
            if probe_ok:
                ship = s
                break
        out["ship"] = ({"s": ship,
                        "verdict": f"SHIP s={ship} (base + both probes clear "
                                   "all ceilings)"}
                       if ship is not None else
                       {"verdict": "no candidate cleared the probes"})
    (RE.PATHS.OUTPUTS / "hrisk1_results.json").write_text(
        json.dumps(out, indent=1, default=str))
    print(f"\nHRISK1 DONE ({time.time()-t0:.0f}s) -> hrisk1_results.json | "
          f"{out['ship']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
