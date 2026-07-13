#!/usr/bin/env python3
"""FMA3-006: H-TAIL-1 — crisis reinforcement from the cash-park (v1.2 candidate).

Pre-registered in research/protocol/HTAIL1.md (committed before any number).
Phased for run economy:

PHASE M (mechanism, both variants m in {1.5, 2.0}):
  1. v3.4'(m) alone in the record engine (EUR 10k) -> native curve B'_m.
  2. Federation blend w=0.70 with the unchanged v7 native curve A and B'_m:
     native s=1.0 run + both +-20% w probes.
  3. Bars: M1 probe-DD improvement >= 1.5pp vs 17.97%; M2 CAGR cost <= 0.5pp
     vs 89.71%; M3 all FMA3-001 bars still pass at w=0.70.
  Committed tie-break: higher w70-native Sharpe among bar-passers proceeds.

PHASE S (shippable, winner only):
  P1 track: coarse s {1.5,1.6,1.7,1.8,1.9,2.0} under PRESETS.md H-RISK-1
  ceilings, 0.05 refinement between last-compliant and first-non-compliant,
  probes at the refined candidate (drop to next lower once if probes fail).
  P2 track: no-regression check at FMA3-005's shipped s (composite bar must
  pass with margin no worse) + probes. No full P2 re-grid.
  A1 bar: P1-track shippable CAGR >= FMA3-004 baseline + 8pp AND P2 no worse.

Reads FMA3-004/005 baselines from hrisk1/2_results.json at runtime (refuses
to run before they exist). Writes research/outputs/htail1_results.json.
Runtime ~2.5h worst case.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))

import record_engine as RE  # noqa: E402
import books                # noqa: E402
from run_hfed1_lib import crisis_tail  # noqa: E402
from run_hrisk2 import daily_pairs, ftmo_historical, ftmo_bootstrap  # noqa: E402

BASE = {"probe_dd": 0.17970, "cagr_w70": 0.89713,
        "hfed1_bars": {"dd": 0.2072, "sharpe": 2.317}}
P1_CEIL = {"dd": 0.30, "tail": 0.30, "negy": 0, "negq": 1, "breach": 0.20}  # owner Pareto revision (FMA3-004c)
COARSE = (1.5, 1.6, 1.7, 1.8, 1.9, 2.0)
W_LOCKED, W_PROBES = 0.70, (0.56, 0.84)


def load_v7() -> tuple[pd.DataFrame, pd.Series]:
    frac7 = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_frac_1h.parquet")
    a = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_equity_1m.parquet")["eqc"]
    return frac7, a / a.iloc[0]


def blend(frac7, a, frac34, b, w) -> pd.DataFrame:
    hours = frac7.index.union(frac34.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    f7 = frac7.reindex(hours).fillna(0.0)
    f34 = frac34.reindex(hours).fillna(0.0)
    cols = sorted(set(f7.columns) | set(f34.columns))
    return (f7.reindex(columns=cols, fill_value=0.0).mul(w * a_h / j, axis=0)
            + f34.reindex(columns=cols, fill_value=0.0)
            .mul((1 - w) * b_h / j, axis=0))


def p1_point(fed, s, label) -> dict:
    res = RE.run_record(fed * s, label=label, verbose=False)
    tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
    ok = (res["maxdd_worst"] < P1_CEIL["dd"] and tail <= P1_CEIL["tail"]
          and res["n_neg_years"] == 0
          and res["n_neg_quarters"] <= P1_CEIL["negq"]
          and res["breach"]["breach_worst"] <= P1_CEIL["breach"])
    print(f"[{label}] CAGR {res['cagr']:+.4f} | DDw {res['maxdd_worst']:.4f} "
          f"| tail {tail:.4f} | negQ {res['n_neg_quarters']} | breach "
          f"{res['breach']['breach_worst']:.4f} | "
          f"{'COMPLIANT' if ok else 'fails'}", flush=True)
    del res["curves"]
    return {"s": s, "compliant": bool(ok), "cagr": res["cagr"],
            "maxdd_worst": res["maxdd_worst"], "sharpe": res["sharpe"],
            "crisis_tail": tail, "breach": res["breach"],
            "n_neg_quarters": res["n_neg_quarters"],
            "neg_years": res["neg_years"]}


def main() -> int:
    t0 = time.time()
    h1 = json.loads((RE.PATHS.OUTPUTS / "hrisk1_results.json").read_text())
    h2 = json.loads((RE.PATHS.OUTPUTS / "hrisk2_results.json").read_text())
    if not h1.get("ship", {}).get("s") or not h2.get("ship", {}).get("s"):
        print("[htail1] REFUSING: FMA3-004/005 baselines not shipped yet")
        return 2
    p1_base_s = h1["ship"]["s"]
    # baseline P1 CAGR: from the base grid entry at the shipped s
    p1_base_cagr = None
    for v in h1["base"].values():
        if abs(v["s"] - p1_base_s) < 1e-9:
            p1_base_cagr = v["cagr"]
    if p1_base_cagr is None:  # shipped s may be <=1.4 (from hfed3 frontier)
        h3 = json.loads((RE.PATHS.OUTPUTS / "hfed3_results.json").read_text())
        for v in h3["grid"].values():
            if abs(v["s"] - p1_base_s) < 1e-9:
                p1_base_cagr = v["cagr"]
    p2_base_s = h2["ship"]["s"]
    p2_base_pb = h2["grid"][f"s{int(round(p2_base_s*100))}"]["bootstrap"][
        "p_breach_12m"]
    print(f"[htail1] baselines: P1 s={p1_base_s} CAGR {p1_base_cagr:+.4f} | "
          f"P2 s={p2_base_s} P(breach) {p2_base_pb:.4f}", flush=True)

    out = {"pre_registration": "research/protocol/HTAIL1.md",
           "baselines": {"p1_s": p1_base_s, "p1_cagr": p1_base_cagr,
                         "p2_s": p2_base_s, "p2_p_breach": p2_base_pb},
           "variants": {}, "winner": None, "ship": None}
    frac7, a = load_v7()

    # ---- PHASE M ------------------------------------------------------------
    for m, cw in ((1.5, 0.15), (2.0, 0.20)):
        tag = f"m{int(m*10)}"
        print(f"[htail1:{tag}] building v3.4' (crisis {cw}) ...", flush=True)
        f34m = books.build_v34_variant_frac_1h(cw)
        alone = RE.run_record(f34m, label=f"htail1_{tag}_v34alone",
                              verbose=False, run_bootstrap=False)
        b_m = alone["curves"]["equity"] / alone["curves"]["equity"].iloc[0]
        v34_metrics = {k: alone[k] for k in
                       ("cagr", "maxdd_worst", "sharpe", "n_neg_quarters")}
        del alone["curves"]
        runs = {}
        for w, lbl in ((W_LOCKED, "w70"), (W_PROBES[0], "w56"),
                       (W_PROBES[1], "w84")):
            fed = blend(frac7, a, f34m, b_m, w)
            r = RE.run_record(fed, label=f"htail1_{tag}_{lbl}",
                              verbose=False, run_bootstrap=False)
            runs[lbl] = {"cagr": r["cagr"], "maxdd_worst": r["maxdd_worst"],
                         "sharpe": r["sharpe"],
                         "n_neg_quarters": r["n_neg_quarters"],
                         "neg_years": r["neg_years"]}
            del r["curves"]
        m1 = (BASE["probe_dd"] - runs["w84"]["maxdd_worst"]) * 100 >= 1.5
        m2 = (BASE["cagr_w70"] - runs["w70"]["cagr"]) * 100 <= 0.5
        m3 = (runs["w70"]["maxdd_worst"] < BASE["hfed1_bars"]["dd"]
              and runs["w70"]["sharpe"] > BASE["hfed1_bars"]["sharpe"]
              and not runs["w70"]["neg_years"]
              and runs["w70"]["n_neg_quarters"] == 0)
        out["variants"][tag] = {
            "crisis_w": cw, "v34_alone": v34_metrics, "fed": runs,
            "bars": {"M1_probe_dd_gain_pp":
                     (BASE["probe_dd"] - runs["w84"]["maxdd_worst"]) * 100,
                     "M1": bool(m1), "M2": bool(m2), "M3": bool(m3)},
            "pass": bool(m1 and m2 and m3)}
        print(f"[htail1:{tag}] M1 {'PASS' if m1 else 'fail'} "
              f"(probe DD {runs['w84']['maxdd_worst']:.4f}, gain "
              f"{(BASE['probe_dd']-runs['w84']['maxdd_worst'])*100:+.2f}pp) | "
              f"M2 {'PASS' if m2 else 'fail'} (CAGR {runs['w70']['cagr']:+.4f})"
              f" | M3 {'PASS' if m3 else 'fail'}", flush=True)

    passers = {k: v for k, v in out["variants"].items() if v["pass"]}
    if not passers:
        out["ship"] = {"verdict": "DECLINE — no variant passed M1-M3"}
        (RE.PATHS.OUTPUTS / "htail1_results.json").write_text(
            json.dumps(out, indent=1, default=str))
        print(f"\nHTAIL1 DONE ({time.time()-t0:.0f}s) | DECLINE (mechanism)",
              flush=True)
        return 0
    win = max(passers, key=lambda k: passers[k]["fed"]["w70"]["sharpe"])
    out["winner"] = win
    cw = out["variants"][win]["crisis_w"]
    print(f"[htail1] winner {win} (crisis {cw}); PHASE S ...", flush=True)

    # ---- PHASE S ------------------------------------------------------------
    f34m = books.build_v34_variant_frac_1h(cw)
    alone = RE.run_record(f34m, label=f"htail1_{win}_v34alone_s",
                          verbose=False, run_bootstrap=False)
    b_m = alone["curves"]["equity"] / alone["curves"]["equity"].iloc[0]
    del alone["curves"]
    fed = blend(frac7, a, f34m, b_m, W_LOCKED)

    p1 = {}
    for s in COARSE:
        p1[s] = p1_point(fed, s, f"htail1_{win}_p1_s{int(round(s*100))}")
    comp = [s for s in COARSE if p1[s]["compliant"]]
    if comp:
        lo = max(comp)
        hi_candidates = [s for s in COARSE if s > lo]
        refine = round(lo + 0.05, 2) if hi_candidates else None
        if refine:
            p1[refine] = p1_point(fed, refine,
                                  f"htail1_{win}_p1_s{int(round(refine*100))}")
            cand = refine if p1[refine]["compliant"] else lo
        else:
            cand = lo
        # probes at the candidate (drop once if they fail)
        for attempt in (cand, round(cand - 0.05, 2)):
            ok = True
            for wp in W_PROBES:
                fedp = blend(frac7, a, f34m, b_m, wp)
                r = p1_point(fedp, attempt,
                             f"htail1_{win}_p1probe_w{int(wp*100)}_"
                             f"s{int(round(attempt*100))}")
                ok = ok and r["compliant"]
            if ok:
                ship_s = attempt
                break
        else:
            ship_s = None
    else:
        ship_s = None

    # P2 no-regression at FMA3-005's shipped s
    fedp2 = fed * 1.0
    r2 = RE.run_record(fedp2 * p2_base_s, label=f"htail1_{win}_p2check",
                       verbose=False, initial=100_000.0, run_bootstrap=False)
    eq, wo = r2["curves"]["equity"], r2["curves"]["worst"]
    boot = ftmo_bootstrap(daily_pairs(eq / eq.iloc[0] * 100_000.0,
                                      wo / eq.iloc[0] * 100_000.0))
    hist = ftmo_historical(eq, wo)
    p2_ok = (boot["p_breach_12m"] <= min(0.05, p2_base_pb + 1e-9)
             and hist["daily_breaches"] == 0 and hist["static_breaches"] == 0)
    del r2["curves"]
    out["p2_check"] = {"p_breach_12m": boot["p_breach_12m"],
                       "historical": hist, "no_regression": bool(p2_ok)}

    if ship_s is not None:
        gain = (p1[ship_s]["cagr"] - p1_base_cagr) * 100
        a1 = gain >= 8.0 and p2_ok
        out["ship"] = {"p1_s": ship_s, "p1_cagr": p1[ship_s]["cagr"],
                       "gain_pp_vs_base": gain, "A1": bool(a1),
                       "verdict": ("ADOPT" if a1 else
                                   "DECLINE (A1 miss)")}
    else:
        out["ship"] = {"verdict": "DECLINE (no probe-robust P1 point)"}
    out["p1_grid"] = {str(k): v for k, v in p1.items()}
    (RE.PATHS.OUTPUTS / "htail1_results.json").write_text(
        json.dumps(out, indent=1, default=str))
    print(f"\nHTAIL1 DONE ({time.time()-t0:.0f}s) | {out['ship']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
