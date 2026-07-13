#!/usr/bin/env python3
"""FMA3-005b: corrected FTMO model (fixed-base) — amends FMA3-005.

Pre-registered in research/protocol/PRESETS.md (FMA3-005b). Re-adjudicates the
FTMO preset with the scale-invariant, de-compounded model:
  * daily rule    : 0 days with intraday worst dip vs prior close > 5%
  * static rule   : book worst-mark %DD < 10%
  * bootstrap     : P(any >5% daily dip OR 12mo path %DD > 10%) <= 0.05
  * negY 0 · negQ <= 1 · both +-20% w probes clear
Re-scores FMA3-005's ALREADY-SAVED base curves engine-free; only the probes at
the corrected ship s need engine passes. Ship largest compliant s.

Run (chained after FTMO grid): python3 scripts/run_hrisk2b.py
Updates hrisk2_results.json['ship'] (+ fma3_005b block) and
hrisk2_ship_curve.parquet.
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
from run_hrisk1 import static_fed  # noqa: E402

S_GRID = (0.4, 0.5, 0.6, 0.7, 0.8)
W_PROBES = (0.56, 0.84)
DAILY_DIP = -0.05      # >5% intraday dip vs prior close
STATIC_DD = 0.10       # 10% worst-mark drawdown floor
N_PATHS, HORIZON, BLOCK, SEED = 10_000, 252, 20, 20260710


def daily_frame(eq: pd.Series, wo: pd.Series) -> pd.DataFrame:
    dc = eq.resample("1D").last().dropna()
    dw = wo.resample("1D").min().reindex(dc.index)
    prev = dc.shift(1)
    return pd.DataFrame({"r": dc / prev - 1.0,
                         "d": dw / prev - 1.0}).dropna()


def neg_year_quarter(eq: pd.Series) -> tuple[int, int]:
    y = eq.resample("YE").last()
    y0 = pd.concat([pd.Series([float(eq.iloc[0])], index=[eq.index[0]]), y])
    ry = y0.pct_change().dropna()
    q = eq.resample("QE").last()
    q0 = pd.concat([pd.Series([float(eq.iloc[0])], index=[eq.index[0]]), q])
    rq = q0.pct_change().dropna()
    return int((ry < 0).sum()), int((rq < 0).sum())


def corrected_historical(df: pd.DataFrame, eq: pd.Series, wo: pd.Series) -> dict:
    peak = eq.cummax()
    max_dd = float((1.0 - wo / peak).max())
    daily_hits = int((df["d"] < DAILY_DIP).sum())
    return {"daily_dip_gt5pct": daily_hits, "max_worst_dd": max_dd,
            "worst_daily_dip": float(df["d"].min())}


def corrected_bootstrap(df: pd.DataFrame) -> dict:
    rng = np.random.default_rng(SEED)
    r = df["r"].to_numpy()
    d = df["d"].to_numpy()
    T = len(r)
    p_cont = 1.0 - 1.0 / BLOCK
    breach = 0
    for _ in range(N_PATHS):
        idx = np.empty(HORIZON, dtype=np.int64)
        j = rng.integers(T)
        for t in range(HORIZON):
            idx[t] = j
            j = (j + 1) % T if rng.random() < p_cont else rng.integers(T)
        dd = d[idx]
        if (dd < DAILY_DIP).any():
            breach += 1
            continue
        e = np.cumprod(1.0 + r[idx])
        peak = np.maximum.accumulate(e)
        if (1.0 - e / peak).max() > STATIC_DD:
            breach += 1
    return {"p_breach_12m": breach / N_PATHS}


def score(eq: pd.Series, wo: pd.Series) -> dict:
    df = daily_frame(eq, wo)
    hist = corrected_historical(df, eq, wo)
    boot = corrected_bootstrap(df)
    ny, nq = neg_year_quarter(eq)
    ok = (hist["daily_dip_gt5pct"] == 0 and hist["max_worst_dd"] < STATIC_DD
          and boot["p_breach_12m"] <= 0.05 and ny == 0 and nq <= 1)
    return {"historical": hist, "bootstrap": boot,
            "neg_years": ny, "neg_quarters": nq, "compliant": bool(ok)}


def main() -> int:
    t0 = time.time()
    res = json.loads((RE.PATHS.OUTPUTS / "hrisk2_results.json").read_text())
    b05 = {"model": "FMA3-005b fixed-base corrected", "base": {}, "probes": {}}

    # engine-free re-score of the saved base curves
    for s in S_GRID:
        key = f"s{int(round(s*100))}"
        cp = RE.PATHS.OUTPUTS / f"hrisk2_{key}_curve.parquet"
        if not cp.exists():
            continue
        c = pd.read_parquet(cp)
        sc = score(c["equity"], c["worst"])
        b05["base"][key] = {"s": s, **sc,
                            "cagr": res["grid"][key]["cagr"]}
        h = sc["historical"]
        print(f"[005b {key}] CAGR {res['grid'][key]['cagr']:+.4f} | "
              f"dip>5% days {h['daily_dip_gt5pct']} | maxDD "
              f"{h['max_worst_dd']:.4f} | P(breach) "
              f"{sc['bootstrap']['p_breach_12m']:.4f} | "
              f"{'COMPLIANT' if sc['compliant'] else 'fails'}", flush=True)

    compliant = sorted((v["s"] for v in b05["base"].values()
                        if v["compliant"]), reverse=True)
    ship_s = None
    if compliant:
        cand = compliant[0]
        # probes at the candidate (engine passes)
        probe_ok = True
        for wp in W_PROBES:
            lbl = f"hrisk2b_probe_w{int(wp*100)}_s{int(round(cand*100))}"
            r = RE.run_record(static_fed(wp) * cand, label=lbl,
                              verbose=False, initial=100_000.0,
                              run_bootstrap=False)
            sc = score(r["curves"]["equity"], r["curves"]["worst"])
            b05["probes"][lbl] = {"w": wp, **sc}
            probe_ok = probe_ok and sc["compliant"]
            h = sc["historical"]
            print(f"[005b probe {lbl}] dip>5% {h['daily_dip_gt5pct']} | "
                  f"maxDD {h['max_worst_dd']:.4f} | P(breach) "
                  f"{sc['bootstrap']['p_breach_12m']:.4f} | "
                  f"{'ok' if sc['compliant'] else 'fail'}", flush=True)
            del r["curves"]
        if probe_ok:
            ship_s = cand

    if ship_s is not None:
        srow = b05["base"][f"s{int(round(ship_s*100))}"]
        res["ship"] = {"s": ship_s, "provenance": "FMA3-005b (fixed-base)",
                       "cagr": srow["cagr"],
                       "max_worst_dd": srow["historical"]["max_worst_dd"],
                       "p_breach_12m": srow["bootstrap"]["p_breach_12m"],
                       "daily_dip_gt5pct": srow["historical"]["daily_dip_gt5pct"],
                       "verdict": f"SHIP s={ship_s} (corrected FTMO model; "
                                  "base + both probes clear)"}
        src = RE.PATHS.OUTPUTS / f"hrisk2_s{int(round(ship_s*100))}_curve.parquet"
        if src.exists():
            (RE.PATHS.OUTPUTS / "hrisk2_ship_curve.parquet").write_bytes(
                src.read_bytes())
    else:
        res["ship"] = {"s": None,
                       "verdict": "no compliant s under corrected model — "
                                  "FTMO preset needs s<0.4 (new pre-reg) or "
                                  "book is too hot for FTMO daily/static rules"}
    res["fma3_005b"] = b05
    (RE.PATHS.OUTPUTS / "hrisk2_results.json").write_text(
        json.dumps(res, indent=1, default=str))
    print(f"\nHRISK2b DONE ({time.time()-t0:.0f}s) | {res['ship']['verdict']}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
