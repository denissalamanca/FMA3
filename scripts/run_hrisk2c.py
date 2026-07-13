#!/usr/bin/env python3
"""FMA3-005c: FTMO probe fallback — completes the FMA3-005b ship rule.

Pre-registered in PRESETS.md FMA3-005c (committed after the s=0.5 w84 probe
FAIL, before probing s=0.4). Probes the remaining base-compliant candidate
s=0.4 with both ±20% w drifts under the corrected fixed-base model. Both
clear → FTMO ships s=0.4; else no ship in the registered grid.

Run: python3 scripts/run_hrisk2c.py   (~12 min: 2 engine passes)
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
from run_hrisk1 import static_fed  # noqa: E402
from run_hrisk2b import score  # noqa: E402

CAND = 0.4
W_PROBES = (0.56, 0.84)


def main() -> int:
    t0 = time.time()
    res = json.loads((RE.PATHS.OUTPUTS / "hrisk2_results.json").read_text())
    b05 = res["fma3_005b"]
    base = b05["base"][f"s{int(round(CAND*100))}"]
    assert base["compliant"], "s=0.4 base row must be compliant"

    probe_ok = True
    for wp in W_PROBES:
        lbl = f"hrisk2c_probe_w{int(wp*100)}_s{int(round(CAND*100))}"
        r = RE.run_record(static_fed(wp) * CAND, label=lbl, verbose=False,
                          initial=100_000.0, run_bootstrap=False)
        sc = score(r["curves"]["equity"], r["curves"]["worst"])
        b05["probes"][lbl] = {"w": wp, **sc}
        h = sc["historical"]
        print(f"[005c probe {lbl}] dip>5% {h['daily_dip_gt5pct']} | maxDD "
              f"{h['max_worst_dd']:.4f} | P(breach) "
              f"{sc['bootstrap']['p_breach_12m']:.4f} | "
              f"{'ok' if sc['compliant'] else 'fail'}", flush=True)
        probe_ok = probe_ok and sc["compliant"]
        del r["curves"]

    if probe_ok:
        res["ship"] = {"s": CAND, "provenance": "FMA3-005c (probe fallback)",
                       "cagr": base["cagr"],
                       "max_worst_dd": base["historical"]["max_worst_dd"],
                       "p_breach_12m": base["bootstrap"]["p_breach_12m"],
                       "daily_dip_gt5pct":
                           base["historical"]["daily_dip_gt5pct"],
                       "verdict": f"SHIP s={CAND} (corrected model; base + "
                                  "both ±20% w probes clear)"}
        src = RE.PATHS.OUTPUTS / f"hrisk2_s{int(round(CAND*100))}_curve.parquet"
        (RE.PATHS.OUTPUTS / "hrisk2_ship_curve.parquet").write_bytes(
            src.read_bytes())
    else:
        res["ship"] = {"s": None,
                       "verdict": "NO FTMO SHIP in the registered grid "
                                  "(s=0.4 probe failed) — s<0.4 would be a "
                                  "new pre-registration"}
    res["fma3_005b"] = b05
    (RE.PATHS.OUTPUTS / "hrisk2_results.json").write_text(
        json.dumps(res, indent=1, default=str))
    print(f"\nHRISK2c DONE ({time.time()-t0:.0f}s) | {res['ship']['verdict']}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
