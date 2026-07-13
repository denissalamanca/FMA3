#!/usr/bin/env python3
"""Debug: dump per-leg USDJPY (sleeve, W_leg, lots, eqc_leg) + eq_joint around
May/Jul-2022 to diagnose the R = F_joint/F_own ratio direction."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine" / "v7_bridge"))
import extract_positions as EP
import engine.backtest as bt
from config import settings as S
from sim import HI, LO, W7, book, pack

TARGET = "USDJPY"

class Dbg(EP.PositionAccumulator):
    def __init__(self, nlegs, n_sleeves):
        super().__init__()
        self._nlegs = nlegs; self._n = n_sleeves
        self.rows = []  # per-leg (sleeve,inst) series of lots, eqc, W_leg
    def __call__(self, t0, t1, tc_seg, legs_cap, flat):
        super().__call__(t0, t1, tc_seg, legs_cap, flat)
        for lc in legs_cap:
            if lc["inst"] != TARGET:
                continue
            m = lc["pos"].index < t1
            w_leg = (1.0/self._n)/self._nlegs[lc["sleeve"]]
            self.rows.append(dict(sleeve=lc["sleeve"], w_leg=w_leg,
                                  lots=lc["pos"][m], eqc=lc["eqc"][m]))

EP.prime("ic")
sleeves = book("BTC_REP", "USTEC")
nlegs = {k: len(v) for k, v in sleeves.items()}
acc = Dbg(nlegs, len(sleeves))
out, trig = EP.run_generic_capture(sleeves, [LO, HI], up=0.25, down=W7/1.75,
                                   kmult=2.5, label="dbg", verbose=False, sink=acc)
eqj = out["eqc"]
print("legs carrying USDJPY:", sorted({r["sleeve"] for r in acc.rows}))
# assemble per-sleeve lots & eqc on union
def asm(key, sleeve):
    parts = [r[key] for r in acc.rows if r["sleeve"] == sleeve]
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s
for win in ("2022-05-16 2022-05-20", "2022-07-20 2022-07-24"):
    a, b = win.split()
    print(f"\n=== {a}..{b} ===")
    ejw = eqj.loc[a:b]
    stamp = ejw.index[len(ejw)//2]
    print("eq_joint at", stamp, "=", round(float(eqj.asof(stamp)), 0))
    tot_own = 0.0; tot_joint = 0.0
    for sl in sorted({r["sleeve"] for r in acc.rows}):
        lots = asm("lots", sl); eqc = asm("eqc", sl)
        wl = [r["w_leg"] for r in acc.rows if r["sleeve"] == sl][0]
        l = float(lots.asof(stamp)); e = float(eqc.asof(stamp))
        ej = float(eqj.asof(stamp))
        share = e/ej
        tgt = l*  1.0  # relative; we compare lots basis
        print(f"  {sl:12} W_leg {wl:.4f} lots {l:+.3f} eqc_leg {e:,.0f} "
              f"share {share:.4f} (equal {wl:.4f}) R_leg=W/share {wl/share:.3f}")
