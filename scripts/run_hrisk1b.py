#!/usr/bin/env python3
"""FMA3-004b: corrected probe-robust search for Preset 1 (amends FMA3-004).

Pre-registered in research/protocol/PRESETS.md (FMA3-004b section, committed
before any s<1.6 probe). FMA3-004's two-stage window ({1.7, 1.6}) was
under-powered — the w+20% probe penalty exceeds one grid step. This completes
the deterministic "largest probe-robust s" search top-down.

Reuses the 1.6/1.7 probe rows already in hrisk1_results.json. Runs probe pairs
(w56, w84) at s in {1.5, 1.4, 1.3, 1.2}, largest-first; ships the first s
where BOTH probes clear the IC ceilings (DD<30% · tail≤30% · negY 0 · negQ≤1 ·
breach≤0.15). Updates hrisk1_results.json['ship'] with FMA3-004b provenance.

Run (chained after FTMO): python3 scripts/run_hrisk1b.py  (~2-8 engine passes)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))

import record_engine as RE  # noqa: E402
from run_hrisk1 import static_blend, run_point, CEIL, W_PROBES  # noqa: E402

SEARCH = (1.5, 1.4, 1.3, 1.2)   # pre-registered top-down grid


def main() -> int:
    t0 = time.time()
    res = json.loads((RE.PATHS.OUTPUTS / "hrisk1_results.json").read_text())
    res.setdefault("fma3_004b", {"pre_registration": "PRESETS.md FMA3-004b",
                                 "search": {}})

    ship_s = None
    for s in SEARCH:
        both_ok = True
        for wp in W_PROBES:
            lbl = f"hrisk1b_probe_w{int(wp*100)}_s{int(round(s*100))}"
            row = run_point(static_blend(wp), s, lbl)
            res["fma3_004b"]["search"][lbl] = row
            res["probes"][lbl] = row
            both_ok = both_ok and row["compliant"]
        # base must also be compliant at this s (it is, for s<=1.7, but assert)
        base_key = f"s{int(round(s*100))}"
        base = res["base"].get(base_key)
        if base is None:
            # s<=1.4 base lives in hfed3; pull it for the record
            h3 = json.loads((RE.PATHS.OUTPUTS / "hfed3_results.json").read_text())
            base = next((v for v in h3["grid"].values()
                         if abs(v["s"] - s) < 1e-9), None)
        base_ok = base is not None and (
            base["maxdd_worst"] < CEIL["dd"]
            and base.get("crisis_tail", 0) <= CEIL["tail"]
            and not base["neg_years"]
            and base["n_neg_quarters"] <= CEIL["negq"]
            and base["breach"]["breach_worst"] <= CEIL["breach"])
        if both_ok and base_ok:
            ship_s = s
            break

    if ship_s is not None:
        # pull the shipped base metric row (from base grid or hfed3)
        base_key = f"s{int(round(ship_s*100))}"
        srow = res["base"].get(base_key)
        if srow is None:
            h3 = json.loads((RE.PATHS.OUTPUTS / "hfed3_results.json").read_text())
            srow = next(v for v in h3["grid"].values()
                        if abs(v["s"] - ship_s) < 1e-9)
        res["ship"] = {
            "s": ship_s, "provenance": "FMA3-004b (corrected probe search)",
            "cagr": srow["cagr"], "maxdd_worst": srow["maxdd_worst"],
            "sharpe": srow["sharpe"],
            "breach": srow["breach"]["breach_worst"],
            "verdict": f"SHIP s={ship_s} (largest probe-robust; base + both "
                       "±20% w probes clear all IC ceilings)"}
        # ensure a curve parquet exists under the shipped key for the dashboard
        src = RE.PATHS.OUTPUTS / f"hrisk1_s{int(round(ship_s*100))}_curve.parquet"
        if src.exists():
            (RE.PATHS.OUTPUTS / "hrisk1_ship_curve.parquet").write_bytes(
                src.read_bytes())
    else:
        res["ship"] = {"s": None,
                       "verdict": "no probe-robust s down to 1.2 — fall back "
                                  "to v1.0 s=1.1 (known probe-robust)"}
    (RE.PATHS.OUTPUTS / "hrisk1_results.json").write_text(
        json.dumps(res, indent=1, default=str))
    print(f"\nHRISK1b DONE ({time.time()-t0:.0f}s) | {res['ship']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
