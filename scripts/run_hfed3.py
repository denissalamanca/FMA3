#!/usr/bin/env python3
"""FMA3-003: H-FED-3 — scale re-pick on the winning federation structure.

THE LAST LEVER (pre-registered in HYPOTHESES.md; scale is never tuned
alongside other levers). Mechanical shipping rule, committed 2026-07-10
before any scaled number was computed:

    Sweep s in {0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4} x native.
    SHIP the LARGEST s such that:
        worst-mark DD < 20.9%   (owner ceiling)
        negQ <= 1, negY == 0
        breach P(maxDD>30%) <= 0.12
        crisis tail <= 35.6%
    If no s clears the owner CAGR gate (>96.1%) under those ceilings, the
    highest-CAGR compliant s is the honest frontier and ships as such.

Winner selection: reads hfed2_results.json; per HYPOTHESES.md the rebalanced
variant must have paid for its cadence (pays_for_cadence AND hfed1_bars_pass)
— the best such variant by Sharpe wins; otherwise the static H-FED-1 winner
stands. The federation matrix is rebuilt from the winner's declared
construction (mode + params), never loaded from a tuned artifact.

Run: python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/run_hfed3.py
Runtime ~50 min (7 engine passes + bootstraps).
Writes research/outputs/hfed3_results.json + hfed3_ship_curve.parquet.
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
from run_hfed2 import federation_weights, blend     # noqa: E402

S_GRID = (0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4)   # pre-registered, fixed
CEIL = {"dd": 0.209, "negq": 1, "negy": 0, "breach": 0.12, "tail": 0.356}
USER_CAGR_GATE = 0.961


def pick_winner() -> dict:
    """Apply the pre-registered winner rule across FMA3-001/002 results."""
    h1 = json.loads((RE.PATHS.OUTPUTS / "hfed1_results.json").read_text())
    static_key = max((k for k, v in h1["grid"].items() if v["bars_pass"]),
                     key=lambda k: h1["grid"][k]["sharpe"])
    static = h1["grid"][static_key]
    winner = {"structure": "static", "w_v7": static["w_v7"],
              "params": {}, "base_metrics": static, "key": static_key}

    h2_path = RE.PATHS.OUTPUTS / "hfed2_results.json"
    if h2_path.exists():
        h2 = json.loads(h2_path.read_text())
        paid = {k: v for k, v in h2["grid"].items()
                if v["pays_for_cadence"] and v["hfed1_bars_pass"]}
        if paid:
            best = max(paid, key=lambda k: paid[k]["sharpe"])
            v = paid[best]
            winner = {"structure": v["mode"], "w_v7": h2["base"]["w_v7"],
                      "params": {"b_up": v["b_up"]},
                      "base_metrics": v, "key": best}
    return winner


def build_matrix(winner: dict) -> pd.DataFrame:
    frac7, frac34, a, b = load_inputs()
    hours = frac7.index.union(frac34.index)
    w = winner["w_v7"]
    if winner["structure"] == "static":
        a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
        b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
        j = w * a_h + (1 - w) * b_h
        f7 = frac7.reindex(hours).fillna(0.0)
        f34 = frac34.reindex(hours).fillna(0.0)
        cols = sorted(set(f7.columns) | set(f34.columns))
        return (f7.reindex(columns=cols, fill_value=0.0)
                .mul(w * a_h / j, axis=0)
                + f34.reindex(columns=cols, fill_value=0.0)
                .mul((1 - w) * b_h / j, axis=0))
    a_star, b_star, _ = federation_weights(
        a, b, w, hours, winner["structure"],
        winner["params"].get("b_up"))
    return blend(frac7, frac34, a_star, b_star)


def main() -> int:
    t0 = time.time()
    winner = pick_winner()
    print(f"[hfed3] winning structure: {winner['key']} "
          f"({winner['structure']}, w_v7={winner['w_v7']}, "
          f"params={winner['params']})", flush=True)
    fed = build_matrix(winner)

    results = {"winner": {k: winner[k] for k in
                          ("structure", "w_v7", "params", "key")},
               "ceilings": CEIL, "user_cagr_gate": USER_CAGR_GATE,
               "grid": {}}
    for s in S_GRID:
        lbl = f"hfed3_s{int(round(s*100))}"
        print(f"[{lbl}] engine pass ({time.time()-t0:.0f}s elapsed) ...",
              flush=True)
        res = RE.run_record(fed * s, label=lbl, verbose=False)
        tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
        compliant = (res["maxdd_worst"] < CEIL["dd"]
                     and res["n_neg_quarters"] <= CEIL["negq"]
                     and res["n_neg_years"] == CEIL["negy"]
                     and res["breach"]["breach_worst"] <= CEIL["breach"]
                     and tail <= CEIL["tail"])
        row = {"s": s, "cagr": res["cagr"],
               "maxdd_worst": res["maxdd_worst"],
               "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
               "crisis_tail": tail, "final_equity": res["final_equity"],
               "neg_years": res["neg_years"],
               "neg_quarters": res["neg_quarters"],
               "n_neg_quarters": res["n_neg_quarters"],
               "breach": res["breach"], "yearly": res["yearly"],
               "compliant": bool(compliant)}
        results["grid"][lbl] = row
        print(f"[{lbl}] CAGR {res['cagr']:+.4f} | DDw {res['maxdd_worst']:.4f}"
              f" | Sh {res['sharpe']:.3f} | tail {tail:.4f} | "
              f"negQ {res['n_neg_quarters']} | "
              f"breach {res['breach']['breach_worst']:.4f} | "
              f"{'COMPLIANT' if compliant else 'breaches ceiling'}",
              flush=True)
        pd.DataFrame({"equity": res["curves"]["equity"],
                      "worst": res["curves"]["worst"]}).to_parquet(
            RE.PATHS.OUTPUTS / f"{lbl}_curve.parquet")
        del res["curves"]

    compliant = {k: v for k, v in results["grid"].items() if v["compliant"]}
    if compliant:
        ship_key = max(compliant, key=lambda k: compliant[k]["s"])
        ship = compliant[ship_key]
        clears = ship["cagr"] > USER_CAGR_GATE
        results["ship"] = {
            "key": ship_key, "s": ship["s"],
            "clears_user_cagr_gate": bool(clears),
            "verdict": ("GATES BREACHED" if clears else
                        "HONEST FRONTIER (owner CAGR gate not cleared under "
                        "risk ceilings)")}
        # persist the shipped curve under a stable name
        src = RE.PATHS.OUTPUTS / f"{ship_key}_curve.parquet"
        (RE.PATHS.OUTPUTS / "hfed3_ship_curve.parquet").write_bytes(
            src.read_bytes())
        print(f"\nSHIP: {ship_key} (s={ship['s']}) — CAGR {ship['cagr']:+.4f}"
              f" | {results['ship']['verdict']}", flush=True)
    else:
        results["ship"] = {"key": None,
                           "verdict": "NO COMPLIANT SCALE (all breach)"}
        print("\nSHIP: none compliant", flush=True)

    out = RE.PATHS.OUTPUTS / "hfed3_results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print(f"DONE ({time.time()-t0:.0f}s) -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
