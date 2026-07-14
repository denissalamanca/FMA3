#!/usr/bin/env python3
"""H-CAPS-1 measurement: combined-book structural exposure analysis (no engine).

Measures, on a blend matrix (CLI: hfed1 winner by default, or a results
key), the joint exposures that v3.4's two structural hard limits governed
single-book:

1. Overnight |XAUUSD| (server hours >= 21 or < 6): distribution of the joint
   fraction vs each book's structural entitlement — v3.4's cap contribution
   scales with its bookkeeping sub-equity share (cap 1.80 x its share), and
   the v7 book's gold demand is single-sleeve-intended by construction
   (BOOK_XAU is THE gold sleeve; its own night leg is its intent).
   By construction the joint can never exceed the sum of entitlements —
   this script VERIFIES that claim empirically and quantifies headroom.
2. Managed crosses (EURCHF/EURSEK/EURNOK/AUDNZD) joint |frac| vs the 0.5 x
   v3.4-share entitlement (v7 trades none of them — verified, not assumed).
3. USTEC joint |frac| distribution (BOOK_USTEC + intraday), for the record.

Output: research/outputs/hcaps1_analysis.json + verdict line. If measured
joint overnight gold respects entitlements everywhere (expected by
construction), H-CAPS-1 resolves as a DOCUMENTED NO-OP: the inherited
per-book caps are sufficient and no new joint cap is pre-registered.
Any excess triggers a pre-registration step BEFORE a cap variant is run.
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
from run_hfed1_lib import load_inputs  # noqa: E402

MANAGED = ("EURCHF", "EURSEK", "EURNOK", "AUDNZD")
V34_GOLD_CAP = 1.80          # x its own sub-equity (v3.4 structural rule)
V34_CROSS_CAP = 0.5


def main() -> int:
    core_frac, sat_frac, a, b = load_inputs()
    h1 = json.loads((RE.PATHS.OUTPUTS / "hfed1_results.json").read_text())
    key = sys.argv[1] if len(sys.argv) > 1 else max(
        (k for k, v in h1["grid"].items() if v["bars_pass"]),
        key=lambda k: h1["grid"][k]["sharpe"])
    w = h1["grid"][key]["w_v7"]

    hours = core_frac.index.union(sat_frac.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    sh7, sh34 = w * a_h / j, (1 - w) * b_h / j

    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat = sat_frac.reindex(hours).fillna(0.0)

    night = (hours.hour >= 21) | (hours.hour < 6)
    out: dict = {"config": key, "w_v7": w, "n_hours": int(len(hours))}

    # 1. overnight gold
    g7 = f_core.get("XAUUSD", pd.Series(0.0, index=hours)) * sh7
    g34 = f_sat.get("XAUUSD", pd.Series(0.0, index=hours)) * sh34
    joint = (g7 + g34)[night]
    entitle = (g7.abs() + (V34_GOLD_CAP * sh34).clip(
        upper=V34_GOLD_CAP))[night]  # v7 intent + v34 cap contribution
    entitle = (g7.abs()[night] + V34_GOLD_CAP * sh34[night])
    excess = (joint.abs() - entitle).clip(lower=0)
    out["overnight_gold"] = {
        "joint_abs_p50": float(joint.abs().quantile(0.50)),
        "joint_abs_p95": float(joint.abs().quantile(0.95)),
        "joint_abs_p99": float(joint.abs().quantile(0.99)),
        "joint_abs_max": float(joint.abs().max()),
        "entitlement_at_max": float(entitle[joint.abs().idxmax()]),
        "hours_exceeding_entitlement": int((excess > 1e-9).sum()),
        "note": "entitlement = |v7 own gold demand| x its share "
                "+ 1.80 x v34 share",
    }

    # 2. managed crosses
    mc = {}
    for c in MANAGED:
        jc = (f_core.get(c, pd.Series(0.0, index=hours)) * sh7
              + f_sat.get(c, pd.Series(0.0, index=hours)) * sh34)
        v7_trades_it = bool(c in f_core.columns and f_core[c].abs().max() > 1e-9)
        mc[c] = {"joint_abs_max": float(jc.abs().max()),
                 "entitlement_max": float((V34_CROSS_CAP * sh34).max()),
                 "v7_trades_it": v7_trades_it,
                 "exceeds": bool(jc.abs().max()
                                 > (V34_CROSS_CAP * sh34).max() + 1e-9)}
    out["managed_crosses"] = mc

    # 3. USTEC
    u = (f_core.get("USTEC", pd.Series(0.0, index=hours)) * sh7
         + f_sat.get("USTEC", pd.Series(0.0, index=hours)) * sh34)
    out["ustec"] = {"joint_abs_p99": float(u.abs().quantile(0.99)),
                    "joint_abs_max": float(u.abs().max())}

    gold_ok = out["overnight_gold"]["hours_exceeding_entitlement"] == 0
    cross_ok = not any(v["exceeds"] for v in mc.values())
    out["verdict"] = ("NO-OP (inherited per-book caps sufficient)"
                      if gold_ok and cross_ok else
                      "EXCESS FOUND — pre-register a joint cap before any "
                      "cap variant is run")
    (RE.PATHS.OUTPUTS / "hcaps1_analysis.json").write_text(
        json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print(f"\nH-CAPS-1: {out['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
