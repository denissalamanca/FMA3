#!/usr/bin/env python3
"""FMA3 v1.0 OFFICIAL PIN — the single source of truth for shipped numbers.

Rebuilds the locked federation matrix from strategy_fma3.FMA3_CONFIG
(static federation, w=0.70, s=1.1 — the FMA3-RT probe-robust adjudication of
H-FED-3's ceiling-rule s=1.4), runs the engine of record end-to-end WITH the
house bootstrap, verifies against the corresponding H-FED-3 grid point
(key derived from the config scale), and emits:

    research/outputs/fma3_v1_pin.json     (official metric block + provenance)
    research/outputs/fma3_v1_pin_curve.parquet  (1m equity + worst curves)

Reproduction gate (FMA2 house rule: a version ships only when its numbers
reproduce end-to-end): every headline metric must match hfed3_results.json
grid[hfed3_s140] exactly (same engine, same inputs — expected delta 0.0).

Run: python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/eval_fma3_pin.py
Runtime ~7 min (engine + 5000-path bootstrap).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3))
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))

import record_engine as RE                     # noqa: E402
from run_hfed1_lib import load_inputs, crisis_tail  # noqa: E402
from strategy_fma3 import FMA3_CONFIG, config_hash  # noqa: E402

TOL = 1e-9


def build_locked_matrix() -> pd.DataFrame:
    """The locked construction, verbatim from FMA3_CONFIG['construction']."""
    w = FMA3_CONFIG["w_v7"]
    s = FMA3_CONFIG["global_scale"]
    frac7, frac34, a, b = load_inputs()
    hours = frac7.index.union(frac34.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    f7 = frac7.reindex(hours).fillna(0.0)
    f34 = frac34.reindex(hours).fillna(0.0)
    cols = sorted(set(f7.columns) | set(f34.columns))
    fed = (f7.reindex(columns=cols, fill_value=0.0).mul(w * a_h / j, axis=0)
           + f34.reindex(columns=cols, fill_value=0.0)
           .mul((1 - w) * b_h / j, axis=0))
    return fed * s


def main() -> int:
    t0 = time.time()
    print(f"[pin] FMA3 v{FMA3_CONFIG['version']} "
          f"(config_hash {config_hash()}) ...", flush=True)
    fed = build_locked_matrix()
    res = RE.run_record(fed, label="fma3_v1_pin", verbose=True)
    tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])

    # reproduction gate vs the FMA3-003 shipped grid point
    # reproduction target = the grid point at the ADJUDICATED scale
    # (FMA3-RT re-picked s=1.4 -> s=1.1; see docs/REGISTRY.md)
    _s_key = f"hfed3_s{int(round(FMA3_CONFIG['global_scale'] * 100))}"
    ship = json.loads((RE.PATHS.OUTPUTS / "hfed3_results.json")
                      .read_text())["grid"][_s_key]
    checks = {
        "cagr": (res["cagr"], ship["cagr"]),
        "maxdd_worst": (res["maxdd_worst"], ship["maxdd_worst"]),
        "sharpe": (res["sharpe"], ship["sharpe"]),
        "final_equity": (res["final_equity"], ship["final_equity"]),
        "crisis_tail": (tail, ship["crisis_tail"]),
    }
    fails = {k: (g, w_) for k, (g, w_) in checks.items()
             if abs(g - w_) > max(TOL, abs(w_) * TOL)}
    for k, (g, w_) in checks.items():
        print(f"  {k:14s} {g:>16.10f} vs {w_:>16.10f} "
              f"{'OK' if k not in fails else 'MISMATCH'}", flush=True)
    if fails:
        print(f"\nPIN FAILED — {len(fails)} mismatches vs FMA3-003; "
              "do not ship.", flush=True)
        return 1

    pin = {
        "version": FMA3_CONFIG["version"],
        "config_hash": config_hash(),
        "locked": FMA3_CONFIG["locked"],
        "engine": FMA3_CONFIG["engine_of_record"],
        "sample": "2020Q1..2025Q4, IC feed, EUR 10,000",
        "pin": {
            "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
            "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
            "crisis_tail": tail, "final_equity": res["final_equity"],
            "n_trades": res["n_trades"], "yearly": res["yearly"],
            "quarterly": res["quarterly"],
            "neg_years": res["neg_years"],
            "neg_quarters": res["neg_quarters"],
        },
        "breach": res["breach"],
        "gates": {
            "owner": {"cagr>0.961": res["cagr"] > 0.961,
                      "maxdd<0.209": res["maxdd_worst"] < 0.209,
                      "sharpe>2.03": res["sharpe"] > 2.03,
                      "tail<=0.356": tail <= 0.356,
                      "negY==0": res["n_neg_years"] == 0,
                      "negQ<=1": res["n_neg_quarters"] <= 1},
        },
        "provenance": {
            "registry": "docs/REGISTRY.md FMA3-000..003",
            "protocol": "research/protocol/PROTOCOL.md (pre-registered)",
            "parents": FMA3_CONFIG["parents"],
        },
    }
    (RE.PATHS.OUTPUTS / "fma3_v1_pin.json").write_text(
        json.dumps(pin, indent=1, default=str))
    pd.DataFrame({"equity": res["curves"]["equity"],
                  "worst": res["curves"]["worst"]}).to_parquet(
        RE.PATHS.OUTPUTS / "fma3_v1_pin_curve.parquet")
    print(f"\nPIN OK ({time.time()-t0:.0f}s) — all gates "
          f"{all(pin['gates']['owner'].values())} -> fma3_v1_pin.json",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
