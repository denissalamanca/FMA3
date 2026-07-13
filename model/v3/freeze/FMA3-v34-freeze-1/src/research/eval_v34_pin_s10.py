"""v3.4 scale-10 pin — shipped v3 book (v2 + MAG@0.05) at SCALE=10.0, full 1m
engine pin (account_engine_1m, EUR10k) + house 20d-block worst-mark breach
bootstrap on the pinned curve. Copy of eval_c2_pin_s11.py with SCALE=10.0; gold
cap re-derives structurally to 0.18*10 = 1.80. (2026-07-10)

Construction mirrors run_v2_pin.py: V2_CAPS @ scale 10 + overlay MAG@0.05,
combined, then apply_hard_limits (overnight gold structural cap on the COMBINED
XAU column; MAG intraday gold governed by its 0.05 weight).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
HERE = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
sys.path.insert(0, str(HERE / "research"))
sys.path.insert(0, str(HERE))

import numpy as np
import pandas as pd
import core
import ensemble as E
import account_engine_1m as A1
from ext_import import mag_xau

V2_CAPS = {"meanrev": 0.11, "carry_breakout": 0.046, "seasonal": 0.18,
           "intraday": 0.168, "crisis": 0.10, "trend_v2": 0.042,
           "crypto_smart": 0.13}
SCALE = 10.0
MAG_W = 0.05
RNG_SEED = 20260709
NP = 5000
BLOCK = 20


def build_c2():
    sleeves = E.load_sleeves(list(V2_CAPS))
    grid = core.universe_frames(tuple(core.ALL))["ret"].index
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
    weights = {**V2_CAPS, "mag": MAG_W}
    pos = E.combine(sleeves, weights) * SCALE
    gcap = E.structural_gold_cap(V2_CAPS, SCALE)
    return E.apply_hard_limits(pos, gold_cap=gcap)


def worst_mark_breach(curve: pd.DataFrame, seed: int = RNG_SEED,
                      n_paths: int = NP, block: int = BLOCK) -> dict:
    """House 20d-block stationary bootstrap, worst-mark P(maxDD>30%) — the exact
    procedure from rederive_claimA.py applied to a scale-9 pinned curve (no s/10
    rescale: this curve is already at its shipped scale)."""
    c = curve["equity"]; w = curve["worst"]
    dc = c.resample("1D").last().dropna()
    dwmin = w.resample("1D").min().reindex(dc.index)
    r = dc.pct_change().dropna().to_numpy()
    dip = (dwmin / dc).to_numpy()[1:]
    T = len(r)
    rng = np.random.default_rng(seed)
    p = 1.0 / block
    ix = np.empty((n_paths, T), dtype=np.int64)
    for i in range(n_paths):
        j = rng.integers(0, T)
        for t in range(T):
            ix[i, t] = j
            j = rng.integers(0, T) if rng.random() < p else (j + 1) % T
    rs = r[ix]
    eq_close = np.cumprod(1.0 + rs, axis=1)
    peak = np.maximum.accumulate(eq_close, axis=1)
    dd_close = (1.0 - eq_close / peak).max(axis=1)
    dipf = dip[ix]                       # worst/close ratio per day
    eq_worst = eq_close * dipf
    dd_worst = (1.0 - eq_worst / peak).max(axis=1)
    return {"breach_close": float((dd_close > 0.30).mean()),
            "breach_worst": float((dd_worst > 0.30).mean()),
            "median_dd_worst": float(np.median(dd_worst)),
            "p95_dd_worst": float(np.percentile(dd_worst, 95))}


if __name__ == "__main__":
    # validation: reproduce v2-pin breach 0.061 with this exact code path
    v2c = pd.read_parquet(HERE/"research/outputs/v2_pin_curve.parquet")
    v2b = worst_mark_breach(v2c)
    print(f"[validate] v2-pin worst-mark breach = {v2b['breach_worst']:.4f} "
          f"(target 0.061) | median {v2b['median_dd_worst']:.3f} "
          f"p95 {v2b['p95_dd_worst']:.3f}")

    pos = build_c2()
    eqc, eqw, m = A1.simulate_account_1m(pos, initial=10_000.0, verbose=True)
    print(f"\n=== v3.4 s10 PIN (v3 book, scale 10, 1m) ===")
    print(f"CAGR {m['cagr']:+.4f} | DDworst {m['maxdd']:.4f} | Sharpe {m['sharpe']:.4f} "
          f"| negY {m['n_neg_years']} negQ {m['n_neg_quarters']} | EUR{m['final_equity']:,.0f}")
    curve = pd.DataFrame({"equity": eqc, "worst": eqw})
    curve.to_parquet(HERE/"research/outputs/v34_s10_pin_curve.parquet")
    c2b = worst_mark_breach(curve)
    print(f"C2 worst-mark breach = {c2b['breach_worst']:.4f} | "
          f"median {c2b['median_dd_worst']:.3f} p95 {c2b['p95_dd_worst']:.3f}")

    out = {"pin": {k: (m[k] if not isinstance(m[k], dict) else m[k]) for k in m},
           "breach": c2b, "v2_breach_validation": v2b}
    json.dump(out, open(HERE/"research/outputs/v34_s10_pin_1m.json","w"),
              default=str, indent=1)
    print("saved outputs/v34_s10_pin_1m.json + v34_s10_pin_curve.parquet")
