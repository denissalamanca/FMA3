#!/usr/bin/env python3
"""FMA3-010: FTMO-specific (w, s) grid WITH the adopted breaker (x=3.0%).

Pre-registered in FTMO_CAMPAIGN.md FMA3-010. The blend w is preset-
specific for FTMO (config-only; both parent books internally unchanged). Tests
whether a capital split other than IC's w=0.70 lets FTMO push past the
FMA3-008 breaker ship (s=0.7, +54.0%).

GRID (pre-registered): w in {0.50, 0.60, 0.70} x s in {0.6, 0.7, 0.8},
breaker x=3.0% (the adopted value), model-v3 scoring. w=0.40 dropped (v3.4-
heavy worsens the static floor — the binding constraint; the FMA3-008 w56
probe already showed the v3.4-tilt floor is the weaker one). Ship = max-CAGR
compliant (w,s) that is probe-robust (+-20% w drift, full walk-down).
BAR: adopt only if >= +8pp gross over the FMA3-008 ship (+54.0%); else the
extra config axis is not paid for and w=0.70 stands.

Run: python3 scripts/run_fma3_010.py   (~2.5h; sequential engine passes)
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
from run_hrisk1 import static_blend               # noqa: E402
from ftmo_model_v3 import score_v3              # noqa: E402

INITIAL, X = 100_000.0, 3.0
W_GRID, S_GRID = (0.50, 0.60, 0.70), (0.6, 0.7, 0.8)
W_PROBE_DELTA = 0.20
BAR = 0.5402 + 0.08          # FMA3-008 ship + 8pp


def log(m: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [FMA3-010] {m}", flush=True)


def cell(w: float, s: float, tag: str) -> dict:
    res = run_record_ext(static_blend(w) * s, initial=INITIAL, daily_stop_x=X,
                         label=tag, verbose=False, run_bootstrap=False)
    sc = score_v3(res["curves"]["equity"], res["curves"]["worst"])
    row = {"w": w, "s": s, "x": X, "cagr": res["cagr"],
           "maxdd_worst": res["maxdd_worst"], **sc}
    del res["curves"]
    h = sc["historical"]
    log(f"{tag} | CAGR {row['cagr']:+.4f} | dips {h['daily_dip_gt5pct']} | "
        f"floor {h['worst_month_floor_touch']:.4f} | P {sc['bootstrap']['p_breach_12m']:.4f}"
        f" | {'COMPLIANT' if sc['compliant'] else 'fails'}")
    return row


def main() -> int:
    t0 = time.time()
    log(f"start — breaker x={X}%, bar CAGR>={BAR:.4f} (FMA3-008 +8pp)")
    out = {"bar": BAR, "grid": {}, "probes": {}, "verdict": None}
    for w in W_GRID:
        for s in S_GRID:
            tag = f"fma3010_w{int(w*100)}_s{int(s*100)}"
            out["grid"][tag] = cell(w, s, tag)

    compliant = [v for v in out["grid"].values() if v["compliant"]]
    ranked = sorted(compliant, key=lambda v: -v["cagr"])   # max CAGR first
    ship = None
    for cand in ranked:
        w, s = cand["w"], cand["s"]
        ok = True
        for wp in (round(w * (1 - W_PROBE_DELTA), 4), round(w * (1 + W_PROBE_DELTA), 4)):
            if not (0 < wp < 1):
                continue
            r = cell(wp, s, f"fma3010_probe_w{int(wp*10000)}_s{int(s*100)}")
            out["probes"][f"{cand['w']}_{s}_{wp}"] = r
            ok = ok and r["compliant"]
        if ok:
            ship = cand
            break

    ship_cagr = ship["cagr"] if ship else None
    if ship and ship_cagr >= BAR:
        out["verdict"] = {"decision": "ADOPT", "w": ship["w"], "s": ship["s"],
                          "cagr": ship_cagr,
                          "gain_pp_vs_008": (ship_cagr - 0.5402) * 100}
    elif ship:
        out["verdict"] = {"decision": "DECLINE (bar miss — w=0.70 stands)",
                          "best_probe_robust": {k: ship[k] for k in
                                                ("w", "s", "cagr")},
                          "gain_pp_vs_008": (ship_cagr - 0.5402) * 100}
    else:
        out["verdict"] = {"decision": "DECLINE (no probe-robust cell beyond "
                                      "w=0.70) — FTMO keeps w=0.70"}
    (RE.PATHS.OUTPUTS / "fma3_010_results.json").write_text(
        json.dumps(out, indent=1, default=str))
    log(f"DONE ({time.time()-t0:.0f}s) | {out['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
