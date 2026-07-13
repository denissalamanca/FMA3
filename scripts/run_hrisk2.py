#!/usr/bin/env python3
"""FMA3-005: H-RISK-2 — Preset 2 (FTMO 2-Step Swing) risk dial.

Pre-registered in research/protocol/PRESETS.md. FTMO rules modeled (verified
against ftmo.com 2026-07-10): Max Daily Loss = equity (incl. floating) must
stay above [previous-midnight balance − 5% × initial]; Max Loss = equity must
never touch 0.90 × initial (static). Modeling conventions: initial €100,000;
daily anchor = previous server-day's closing equity (server midnight ≈ CE(S)T
midnight ± 1h, and midnight-equity ≈ prior close — both documented
approximations; the anchor uses equity, not balance, since balance is not
separable from the pinned curves).

BAR (composite, pre-registered): P(breach either rule within 12 months)
≤ 0.05 on 10,000 stationary-bootstrap paths (20d mean block, seed 20260710)
built from daily pairs (close return r_t, worst dip vs previous close d_t):
path E_d = E_{d-1}(1+r), day-min = E_{d-1}(1+d); daily-rule breach iff
d < −5000/E_{d-1}; static breach iff E_{d-1}(1+d) < 90,000. Plus: zero
breaches on the actual 2020–25 path; negY 0; negQ ≤ 1; both ±20% w probes
clear the composite bar at the shipped s. Grid s ∈ {0.4,0.5,0.6,0.7,0.8};
ship the largest compliant s. Also reported: P(pass Phase-1 +10% without
breach) and median days-to-target, same for Phase-2 +5%.

Run: python3 scripts/run_hrisk2.py   (~50 min: up to 7 engine passes)
Writes research/outputs/hrisk2_results.json.
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
from run_hrisk1 import static_fed  # noqa: E402  (same blend builder)

INITIAL = 100_000.0
DAILY_LOSS_EUR = 0.05 * INITIAL
STATIC_FLOOR = 0.90 * INITIAL
S_GRID = (0.4, 0.5, 0.6, 0.7, 0.8)
W_LOCKED, W_PROBES = 0.70, (0.56, 0.84)
N_PATHS, HORIZON_D, BLOCK_D, SEED = 10_000, 252, 20, 20260710


def daily_pairs(eq: pd.Series, worst: pd.Series) -> pd.DataFrame:
    """Per-server-day (close return, worst dip vs previous close)."""
    dc = eq.resample("1D").last().dropna()
    dw = worst.resample("1D").min().reindex(dc.index)
    prev = dc.shift(1)
    df = pd.DataFrame({"r": dc / prev - 1.0, "d": dw / prev - 1.0}).dropna()
    return df


def ftmo_historical(eq: pd.Series, worst: pd.Series) -> dict:
    """Direct rule scan of the actual path, rebased to EUR 100k start."""
    scale = INITIAL / float(eq.iloc[0])
    e, w = eq * scale, worst * scale
    dc = e.resample("1D").last().dropna()
    anchors = dc.shift(1)
    dw = w.resample("1D").min().reindex(dc.index)
    daily_breach = (dw < (anchors - DAILY_LOSS_EUR)).fillna(False)
    static_breach = (dw < STATIC_FLOOR).fillna(False)
    return {"daily_breaches": int(daily_breach.sum()),
            "static_breaches": int(static_breach.sum()),
            "worst_daily_dip_eur": float((dw - anchors).min()),
            "min_equity_eur": float(dw.min())}


def ftmo_bootstrap(pairs: pd.DataFrame) -> dict:
    """Composite 12-month survival + challenge-pass statistics."""
    rng = np.random.default_rng(SEED)
    r = pairs["r"].to_numpy()
    d = pairs["d"].to_numpy()
    T = len(r)
    p_cont = 1.0 - 1.0 / BLOCK_D
    breach = 0
    p1_pass = 0
    p1_days_all = []
    for _ in range(N_PATHS):
        idx = np.empty(HORIZON_D, dtype=np.int64)
        j = rng.integers(T)
        for t in range(HORIZON_D):
            idx[t] = j
            j = (j + 1) % T if rng.random() < p_cont else rng.integers(T)
        e = INITIAL
        breached = False
        p1_day = None
        for t in range(HORIZON_D):
            day_min = e * (1.0 + d[idx[t]])
            if day_min < STATIC_FLOOR or day_min < e - DAILY_LOSS_EUR:
                breached = True
                break
            e *= (1.0 + r[idx[t]])
            if p1_day is None and e >= INITIAL * 1.10:
                p1_day = t + 1
        if breached:
            breach += 1
        elif p1_day is not None:
            p1_pass += 1
            p1_days_all.append(p1_day)
    return {"p_breach_12m": breach / N_PATHS,
            "p_pass_p1_10pct_no_breach": p1_pass / N_PATHS,
            "median_days_to_p1": (float(np.median(p1_days_all))
                                  if p1_days_all else None)}


def run_point(fed: pd.DataFrame, s: float, label: str) -> dict:
    res = RE.run_record(fed * s, label=label, verbose=False,
                        initial=INITIAL, run_bootstrap=False)
    eq, wo = res["curves"]["equity"], res["curves"]["worst"]
    hist = ftmo_historical(eq, wo)
    boot = ftmo_bootstrap(daily_pairs(eq / eq.iloc[0] * INITIAL,
                                      wo / eq.iloc[0] * INITIAL))
    ok = (boot["p_breach_12m"] <= 0.05
          and hist["daily_breaches"] == 0 and hist["static_breaches"] == 0
          and res["n_neg_years"] == 0 and res["n_neg_quarters"] <= 1)
    row = {"s": s, "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
           "sharpe": res["sharpe"], "neg_quarters": res["neg_quarters"],
           "historical": hist, "bootstrap": boot, "compliant": bool(ok)}
    pd.DataFrame({"equity": eq, "worst": wo}).to_parquet(
        RE.PATHS.OUTPUTS / f"{label}_curve.parquet")
    print(f"[{label}] CAGR {res['cagr']:+.4f} | DDw {res['maxdd_worst']:.4f}"
          f" | P(breach 12m) {boot['p_breach_12m']:.4f} | histDaily "
          f"{hist['daily_breaches']} histStatic {hist['static_breaches']} | "
          f"P(passP1) {boot['p_pass_p1_10pct_no_breach']:.3f} | "
          f"{'COMPLIANT' if ok else 'fails'}", flush=True)
    del res["curves"]
    return row


def main() -> int:
    t0 = time.time()
    out = {"rules": {"daily_loss_eur": DAILY_LOSS_EUR,
                     "static_floor_eur": STATIC_FLOOR, "initial": INITIAL,
                     "vehicle": "FTMO 2-Step Swing (verified 2026-07-10)"},
           "grid": {}, "probes": {}, "ship": None}
    fed = static_fed(W_LOCKED)
    for s in S_GRID:
        out["grid"][f"s{int(round(s*100))}"] = run_point(
            fed, s, f"hrisk2_s{int(round(s*100))}")
    compliant = [v["s"] for v in out["grid"].values() if v["compliant"]]
    if not compliant:
        out["ship"] = {"verdict": "NO COMPLIANT SCALE"}
    else:
        s_cand = max(compliant)
        probe_ok = True
        for wp in W_PROBES:
            lbl = f"hrisk2_probe_w{int(wp*100)}_s{int(round(s_cand*100))}"
            row = run_point(static_fed(wp), s_cand, lbl)
            out["probes"][lbl] = row
            probe_ok = probe_ok and row["compliant"]
        out["ship"] = ({"s": s_cand, "verdict": f"SHIP s={s_cand}"}
                       if probe_ok else
                       {"s": None, "verdict": f"candidate s={s_cand} failed "
                        "probes — next-lower re-evaluation requires a new "
                        "pre-registration entry"})
    (RE.PATHS.OUTPUTS / "hrisk2_results.json").write_text(
        json.dumps(out, indent=1, default=str))
    print(f"\nHRISK2 DONE ({time.time()-t0:.0f}s) | {out['ship']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
