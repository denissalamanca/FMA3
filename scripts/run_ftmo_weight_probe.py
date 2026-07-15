#!/usr/bin/env python3
"""FMA3-011: FTMO ±20% weight-probe — the clean, self-contained deliverable.

WHY THIS EXISTS
---------------
The IC preset shipped s=1.6 under a pre-registered ±20% weight-probe
(FMA3-004c / run_hrisk1.py): the dial is "probe-robust" iff the base blend
(w=0.70) AND both ±20% w drifts (w=0.56, w=0.84) clear every ceiling. The
FTMO dial (s≈0.70, ≤1-breach/yr) needs the SAME treatment surfaced as one
artifact.

A record-engine ±20% FTMO probe already ran inside FMA3-008 (run_hftmo1.py)
and FMA3-010 (run_fma3_010.py) on 2026-07-10 and PASSED at s=0.70 (base +
both probes COMPLIANT, P(breach12m)=0.0). This script (a) REPRODUCES those
archived cells as a drift-guard, (b) FILLS the s=0.65 crisis-margin dial that
was never probed, and (c) reports BOTH frames side-by-side:
  - the score_v3 (FMA3-009) monthly-payout-reset frame — matches the owner's
    monthly-withdrawal operating model; ceiling P(breach12m) ≤ 0.05;
  - the STATIC max-mark drawdown (maxdd_worst) — comparable to the native-EA
    static DD (Run A s=0.70 = 14.11%), so the two framings can be reconciled.

This is a RECORD-ENGINE probe (frictionless-optimistic + COVID cold-start
blind, exactly like IC's FMA3-004c probe). It brings FTMO to record-engine
parity with IC. The higher, native-EA-grade probe (edit compiled w, recompile,
run MT5 per weight) is a separate bar that NEITHER preset has — owner-MT5.

Ceilings (score_v3 / FMA3-009, all must hold at locked w AND both ±20% w probes):
  daily_dip_gt5pct == 0 · worst_month_floor_touch > 0.90 · P(breach12m) ≤ 0.05
  · negY == 0 · negQ ≤ 1.

Run: /usr/local/bin/python3 scripts/run_ftmo_weight_probe.py   (~25-30 min: 6 passes)
Writes research/outputs/ftmo_weight_probe_results.json (+ curve per cell).
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

import record_engine as RE                      # noqa: E402
from record_engine_ext import run_record_ext    # noqa: E402
from run_hrisk1 import static_blend             # noqa: E402  (identical blend as IC)
from ftmo_model_v3 import score_v3              # noqa: E402

INITIAL, X = 100_000.0, 3.0                     # FTMO base + adopted 3% breaker
S_SHIP, S_CRISIS = 0.70, 0.65                   # shipped dial + crisis-margin alt
S_GRID = (S_SHIP, S_CRISIS)                      # ship first (drift-guard cells fail-fast)
W_LOCKED, W_PROBES = 0.70, (0.56, 0.84)         # ±20% of 0.70

# score_v3 ceilings (FMA3-009), restated here for the compliance predicate.
CEIL = {"daily_dip": 0, "floor": 0.90, "p_breach": 0.05, "negy": 0, "negq": 1}

# Archived FMA3-008/010 cells to drift-check (w, s) -> (maxdd_worst, p_breach12m).
# Source: research/outputs/fma3_010_results.json + ftmo_campaign.log (2026-07-10).
ARCHIVE = {
    (0.70, 0.70): {"maxdd_worst": 0.13326785098278104, "p_breach": 0.0},
    (0.56, 0.70): {"maxdd_worst": 0.11574396563362943, "p_breach": 0.0},
    (0.84, 0.70): {"maxdd_worst": 0.13203922425074488, "p_breach": 0.0},
}


def log(m: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [FMA3-011] {m}", flush=True)


def cell(w: float, s: float, tag: str) -> dict:
    res = run_record_ext(static_blend(w) * s, initial=INITIAL, daily_stop_x=X,
                         label=tag, verbose=False, run_bootstrap=False)
    sc = score_v3(res["curves"]["equity"], res["curves"]["worst"])
    h, b = sc["historical"], sc["bootstrap"]
    ok = (h["daily_dip_gt5pct"] == CEIL["daily_dip"]
          and h["worst_month_floor_touch"] > CEIL["floor"]
          and b["p_breach_12m"] <= CEIL["p_breach"]
          and sc["neg_years"] == CEIL["negy"]
          and sc["neg_quarters"] <= CEIL["negq"])
    row = {"w": w, "s": s, "x": X,
           "cagr": res["cagr"],
           "maxdd_worst_static": res["maxdd_worst"],   # static frame (~native-EA)
           "daily_dip_gt5pct": h["daily_dip_gt5pct"],
           "worst_month_floor_touch": h["worst_month_floor_touch"],
           "p_breach_12m": b["p_breach_12m"],           # monthly-reset frame
           "p_pass_p1": sc["challenge"]["p_pass_p1"],
           "neg_years": sc["neg_years"], "neg_quarters": sc["neg_quarters"],
           "compliant": bool(ok)}
    pd.DataFrame({"equity": res["curves"]["equity"],
                  "worst": res["curves"]["worst"]}).to_parquet(
        RE.PATHS.OUTPUTS / f"{tag}_curve.parquet")
    del res["curves"]
    # drift-guard against the archived FMA3-008/010 cell, if we have one
    drift = ""
    a = ARCHIVE.get((round(w, 2), round(s, 2)))
    if a is not None:
        d_dd = abs(row["maxdd_worst_static"] - a["maxdd_worst"])
        d_pb = abs(row["p_breach_12m"] - a["p_breach"])
        drift = (f" | REPRO ddΔ={d_dd:.2e} pbΔ={d_pb:.2e} "
                 f"{'OK' if (d_dd < 1e-6 and d_pb < 1e-9) else 'DRIFT!!'}")
    log(f"{tag} | CAGR {row['cagr']:+.4f} | staticDD {row['maxdd_worst_static']:.4f}"
        f" | dips {row['daily_dip_gt5pct']} | floor {row['worst_month_floor_touch']:.4f}"
        f" | P(breach12m) {row['p_breach_12m']:.4f} | "
        f"{'COMPLIANT' if ok else 'BREACHES CEILING'}{drift}")
    return row


def main() -> int:
    t0 = time.time()
    log(f"start — FTMO ±20% weight-probe | base w={W_LOCKED} probes {W_PROBES} "
        f"| dials s∈{S_GRID} | breaker x={X}% | initial €{INITIAL:,.0f}")
    out = {"ceilings": CEIL, "base": {}, "probes": {}, "verdict": {},
           "reproduction": {}}

    for s in S_GRID:
        st = f"s{int(round(s*100))}"
        # base (locked w)
        base = cell(W_LOCKED, s, f"ftmoP_w70_{st}")
        out["base"][st] = base
        # ±20% probes
        probe_ok = True
        for wp in W_PROBES:
            r = cell(wp, s, f"ftmoP_w{int(wp*100)}_{st}")
            out["probes"][f"{st}_w{int(wp*100)}"] = r
            probe_ok = probe_ok and r["compliant"]
        robust = bool(base["compliant"] and probe_ok)
        out["verdict"][st] = {
            "s": s,
            "base_compliant": base["compliant"],
            "both_probes_compliant": probe_ok,
            "probe_robust": robust,
            "verdict": (f"PROBE-ROBUST at s={s} (base w=0.70 + both ±20% probes "
                        "clear every score_v3 ceiling)" if robust else
                        f"NOT probe-robust at s={s}")}

    # reproduction summary vs archive (FMA3-008/010)
    rep_ok = True
    for (w, s), a in ARCHIVE.items():
        st = f"s{int(round(s*100))}"
        key = f"{st}_w{int(w*100)}" if w != W_LOCKED else st
        row = out["probes"].get(key) or out["base"].get(st)
        d_dd = abs(row["maxdd_worst_static"] - a["maxdd_worst"])
        d_pb = abs(row["p_breach_12m"] - a["p_breach"])
        cell_ok = bool(d_dd < 1e-6 and d_pb < 1e-9)
        rep_ok = rep_ok and cell_ok
        out["reproduction"][f"w{int(w*100)}_{st}"] = {
            "d_maxdd": d_dd, "d_p_breach": d_pb, "reproduced": cell_ok}
    out["reproduction"]["all_reproduced"] = rep_ok

    (RE.PATHS.OUTPUTS / "ftmo_weight_probe_results.json").write_text(
        json.dumps(out, indent=1, default=str))
    log(f"DONE ({time.time()-t0:.0f}s) | ship s={S_SHIP}: "
        f"{out['verdict'][f's{int(S_SHIP*100)}']['probe_robust']} | "
        f"crisis s={S_CRISIS}: "
        f"{out['verdict'][f's{int(S_CRISIS*100)}']['probe_robust']} | "
        f"archive reproduced: {rep_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
