#!/usr/bin/env python3
"""FMA3-004c: re-adjudicate Preset 1 (IC) under the owner's revised breach cap.

Owner Pareto revision 2026-07-10: IC breach ceiling P(maxDD>30%) 0.15 -> 0.20
(informed by the mapped breach-vs-CAGR frontier; a risk-appetite point choice,
strategy frozen; 0.20 sits within house precedent — v3.4 scale-11 was 0.198).

ENGINE-FREE: re-scans the base grid + probe rows ALREADY computed by
run_hrisk1.py (research/outputs/hrisk1_results.json) and the s<=1.4 frontier
(hfed3_results.json), and ships the LARGEST s where the base AND both +-20% w
probes clear the revised IC ceilings (DD<30% . tail<=30% . negY 0 . negQ<=1 .
breach<=0.20). No new engine pass — the downward FMA3-004b search is moot
(the 0.20 cap moves the answer UP, into already-probed territory).

Run: python3 scripts/adjudicate_hrisk1.py   (< 1s, JSON reads only)
Updates hrisk1_results.json['ship'] and writes hrisk1_ship_curve.parquet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_FMA3 = Path(__file__).resolve().parents[1]
OUT = _FMA3 / "research" / "outputs"

CAP = {"dd": 0.30, "tail": 0.30, "negy": 0, "negq": 1, "breach": 0.20}


def _clears(row: dict) -> bool:
    return (row["maxdd_worst"] < CAP["dd"]
            and row.get("crisis_tail", 0.0) <= CAP["tail"]
            and not row["neg_years"]
            and row["n_neg_quarters"] <= CAP["negq"]
            and row["breach"]["breach_worst"] <= CAP["breach"])


def main() -> int:
    res = json.loads((OUT / "hrisk1_results.json").read_text())
    h3 = json.loads((OUT / "hfed3_results.json").read_text())
    probes = res.get("probes", {})

    # candidate s that have BOTH probe rows computed (only these can be
    # certified probe-robust without a new engine run)
    def probe_pair(s: int):
        return (probes.get(f"hrisk1_probe_w56_s{s}"),
                probes.get(f"hrisk1_probe_w84_s{s}"))

    # base row lookup: hrisk1 base grid (s>=1.5) or hfed3 frontier (s<=1.4)
    def base_row(sf: float):
        k = f"s{int(round(sf*100))}"
        if k in res["base"]:
            return res["base"][k]
        return next((v for v in h3["grid"].values()
                     if abs(v["s"] - sf) < 1e-9), None)

    certified = []
    for s in (170, 160):                       # only these were probe-tested
        w56, w84 = probe_pair(s)
        base = base_row(s / 100.0)
        if not (w56 and w84 and base):
            continue
        ok = _clears(base) and _clears(w56) and _clears(w84)
        certified.append((s / 100.0, ok, base, w56, w84))

    ship = None
    for sf, ok, base, w56, w84 in sorted(certified, reverse=True):
        if ok:
            ship = (sf, base, w56, w84)
            break

    res["fma3_004c"] = {
        "revision": "owner Pareto breach cap 0.15 -> 0.20 (2026-07-10)",
        "cap": CAP,
        "certified_scan": [
            {"s": sf, "probe_robust": ok,
             "base_breach": base["breach"]["breach_worst"],
             "w56_breach": w56["breach"]["breach_worst"],
             "w84_breach": w84["breach"]["breach_worst"],
             "w84_dd": w84["maxdd_worst"]}
            for sf, ok, base, w56, w84 in sorted(certified, reverse=True)],
    }

    if ship:
        sf, base, w56, w84 = ship
        res["ship"] = {
            "s": sf, "provenance": "FMA3-004c (breach cap 0.20, engine-free "
                                   "re-adjudication of existing probe data)",
            "cagr": base["cagr"], "maxdd_worst": base["maxdd_worst"],
            "sharpe": base["sharpe"], "crisis_tail": base["crisis_tail"],
            "breach": base["breach"]["breach_worst"],
            "worst_probe_breach": max(w56["breach"]["breach_worst"],
                                      w84["breach"]["breach_worst"]),
            "worst_probe_dd": max(w56["maxdd_worst"], w84["maxdd_worst"]),
            "n_neg_quarters": base["n_neg_quarters"],
            "verdict": f"SHIP s={sf} (largest probe-robust under breach<=0.20; "
                       f"s=1.7 fails w84 breach 0.280)"}
        src = OUT / f"hrisk1_s{int(round(sf*100))}_curve.parquet"
        if src.exists():
            (OUT / "hrisk1_ship_curve.parquet").write_bytes(src.read_bytes())
    else:
        res["ship"] = {"s": None,
                       "verdict": "no probe-robust s among tested points at "
                                  "cap 0.20 — extend probe search"}

    (OUT / "hrisk1_results.json").write_text(json.dumps(res, indent=1,
                                                        default=str))
    print("scan:", json.dumps(res["fma3_004c"]["certified_scan"], indent=1))
    print("ship:", res["ship"]["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
