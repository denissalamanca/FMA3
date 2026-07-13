#!/usr/bin/env python3
"""FMA3-009: FTMO model v3 (payout-cycle) re-score + probe walk-down + re-ship.

Committed spec: research/protocol/FTMO_CAMPAIGN.md (FMA3-009). Model + all
conventions: scripts/ftmo_model_v3.py (importable scorer). Procedure:

1. Engine-free re-score of ALL saved base curves (hrisk2_s{40..80}).
2. Probe walk-down (FMA3-005c standing amendment — the FULL walk, no
   truncation): starting at the largest v3-compliant s, run BOTH +-20% w
   probes (w56, w84; engine passes — the 005b/005c probe curves were not
   saved) and walk down the compliant list until a probe-robust s is found
   or the list is exhausted. Probe curves ARE saved this time
   (hrisk2v3_probe_*_curve.parquet) so future models re-score engine-free;
   if a probe curve already exists on disk it is re-scored, not re-run.
3. Re-ship: hrisk2_results.json ship block (provenance FMA3-009/model-v3;
   005b/005c blocks kept intact) + hrisk2_ship_curve.parquet.

Engine passes run SEQUENTIALLY (single-process convention). All output is
appended to research/outputs/ftmo_campaign.log with flush.

Run: python3 scripts/run_hrisk2v3.py   (~6 min per probe engine pass)
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
from ftmo_model_v3 import score_v3  # noqa: E402

S_GRID = (0.4, 0.5, 0.6, 0.7, 0.8)
W_PROBES = (0.56, 0.84)
INITIAL = 100_000.0
LOG = _FMA3 / "research" / "outputs" / "ftmo_campaign.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [FMA3-009] {msg}"
    print(line, flush=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")
        fh.flush()


def fmt(sc: dict) -> str:
    h, b, c = sc["historical"], sc["bootstrap"], sc["challenge"]
    return (f"dip>5%base {h['daily_dip_gt5pct']} | monthFloorLo "
            f"{h['worst_month_floor_touch']:.4f} | P(breach12m) "
            f"{b['p_breach_12m']:.4f} | P(passP1) {c['p_pass_p1']:.3f} "
            f"med {c['median_days_p1']} | negY {sc['neg_years']} negQ "
            f"{sc['neg_quarters']} | "
            f"{'COMPLIANT' if sc['compliant'] else 'fails'}")


def probe_curve(wp: float, s: float) -> tuple[pd.DataFrame, str, bool]:
    """Load a saved v3 probe curve or run the engine pass (and save it)."""
    lbl = f"hrisk2v3_probe_w{int(wp*100)}_s{int(round(s*100))}"
    cp = RE.PATHS.OUTPUTS / f"{lbl}_curve.parquet"
    if cp.exists():
        return pd.read_parquet(cp), lbl, True
    r = RE.run_record(static_fed(wp) * s, label=lbl, verbose=False,
                      initial=INITIAL, run_bootstrap=False)
    c = pd.DataFrame({"equity": r["curves"]["equity"],
                      "worst": r["curves"]["worst"]})
    c.to_parquet(cp)
    del r["curves"]
    return c, lbl, False


def main() -> int:
    t0 = time.time()
    log("start — model v3 (payout-cycle) re-score of saved base curves")
    res = json.loads((RE.PATHS.OUTPUTS / "hrisk2_results.json").read_text())
    b09 = {"model": "FMA3-009 rule-accurate v3 (monthly payout-to-base; "
                    "absolute 0.90x-base floor within month; daily dip vs "
                    "prev close > 5% of base; 10k 12-month month-block "
                    "bootstrap, seed 20260710)",
           "base": {}, "probes": {}}

    # 1. engine-free re-score of all saved base curves
    for s in S_GRID:
        key = f"s{int(round(s*100))}"
        cp = RE.PATHS.OUTPUTS / f"hrisk2_{key}_curve.parquet"
        if not cp.exists():
            log(f"base {key}: curve MISSING — skipped")
            continue
        c = pd.read_parquet(cp)
        sc = score_v3(c["equity"], c["worst"])
        b09["base"][key] = {"s": s, **sc, "cagr": res["grid"][key]["cagr"]}
        log(f"base {key} CAGR {res['grid'][key]['cagr']:+.4f} | {fmt(sc)}")

    # 2. probe walk-down (FMA3-005c standing amendment: full list, no
    #    truncation) — largest v3-compliant s first
    compliant = sorted((v["s"] for v in b09["base"].values()
                        if v["compliant"]), reverse=True)
    log(f"v3 base-compliant list (walk-down order): {compliant}")
    ship_s = None
    for cand in compliant:
        probe_ok = True
        for wp in W_PROBES:
            c, lbl, reused = probe_curve(wp, cand)
            sc = score_v3(c["equity"], c["worst"])
            b09["probes"][lbl] = {"w": wp, "s": cand, **sc,
                                  "curve_reused": reused}
            log(f"probe {lbl}{' (re-scored saved curve)' if reused else ''} "
                f"| {fmt(sc)}")
            probe_ok = probe_ok and sc["compliant"]
        if probe_ok:
            ship_s = cand
            break
        log(f"s={cand} NOT probe-robust — walking down")

    # 3. re-ship (005b/005c blocks left intact)
    if ship_s is not None:
        key = f"s{int(round(ship_s*100))}"
        row = b09["base"][key]
        res["ship"] = {
            "s": ship_s, "provenance": "FMA3-009/model-v3",
            "cagr": row["cagr"],
            "p_breach_12m": row["bootstrap"]["p_breach_12m"],
            "daily_dip_gt5pct": row["historical"]["daily_dip_gt5pct"],
            "worst_month_floor_touch":
                row["historical"]["worst_month_floor_touch"],
            "p_pass_p1": row["challenge"]["p_pass_p1"],
            "median_days_p1": row["challenge"]["median_days_p1"],
            "verdict": f"SHIP s={ship_s} (model v3 payout-cycle; base + "
                       "both +-20% w probes clear)"}
        src = RE.PATHS.OUTPUTS / f"hrisk2_{key}_curve.parquet"
        (RE.PATHS.OUTPUTS / "hrisk2_ship_curve.parquet").write_bytes(
            src.read_bytes())
        log(f"SHIP s={ship_s} CAGR {row['cagr']:+.4f} — ship curve copied")
    else:
        res["ship"] = {"s": None, "provenance": "FMA3-009/model-v3",
                       "verdict": "NO v3 probe-robust s in the registered "
                                  "grid (walk-down exhausted)"}
        log("walk-down exhausted — NO SHIP (recorded honestly)")

    b09["ship"] = res["ship"]
    res["fma3_009"] = b09
    (RE.PATHS.OUTPUTS / "hrisk2_results.json").write_text(
        json.dumps(res, indent=1, default=str))
    log(f"DONE ({time.time()-t0:.0f}s) | {res['ship']['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
