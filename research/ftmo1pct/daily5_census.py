#!/usr/bin/env python3
"""Post-hoc FTMO daily-5%-rule census over the kill-engine minute curves.

For each *_curve.parquet: group minutes by SERVER day (ts // 86400), anchor each
day at the PREVIOUS day's closing eq_c (day 1: initial 100k) — the Guardian /
record-engine daily-anchor law — and count days whose worst-mark equity (eq_w)
fell to or below anchor*(1-0.05). That is the FTMO-visible daily-rule breach
count: gap-through PAST the 5% line despite (or before) the 3%/4% breaker.
Also reports near-misses (>=4% depth) for headroom context. Read-only.
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
INITIAL = 100_000.0
LIMIT = 0.05
NEAR = 0.04

def census(path: str) -> None:
    df = pd.read_parquet(path)
    cols = {c.lower(): c for c in df.columns}
    # locate the ts / eq_c / eq_w columns robustly
    ts = None
    for cand in ("ts", "ts_ns", "time", "minute"):
        if cand in cols:
            ts = df[cols[cand]].to_numpy()
            break
    if ts is None and np.issubdtype(df.index.dtype, np.number):
        ts = df.index.to_numpy()
    if ts is None and isinstance(df.index, pd.DatetimeIndex):
        ts = df.index.asi8
    eqc = next((df[cols[c]].to_numpy(float) for c in ("eq_c", "eqc", "equity", "equity_close", "eq_close") if c in cols), None)
    eqw = next((df[cols[c]].to_numpy(float) for c in ("eq_w", "eqw", "worst", "equity_worst", "eq_worst") if c in cols), None)
    if ts is None or eqc is None or eqw is None:
        print(f"  {Path(path).name}: SKIP (cols={list(df.columns)[:8]}, index={df.index.dtype})")
        return
    ts = np.asarray(ts, dtype=np.int64)
    if ts.max() > 10**14:            # ns -> s
        ts = ts // 1_000_000_000
    day = ts // 86_400
    order = np.argsort(ts, kind="stable")
    day, eqc, eqw = day[order], eqc[order], eqw[order]

    uniq, first_idx = np.unique(day, return_index=True)
    # last index of each day = next day's first index - 1
    last_idx = np.r_[first_idx[1:] - 1, len(day) - 1]
    close_by_day = eqc[last_idx]
    anchors = np.r_[INITIAL, close_by_day[:-1]]      # day 1 anchored at initial
    # min worst-mark within each day
    min_eqw = np.minimum.reduceat(eqw, first_idx)
    depth = (anchors - min_eqw) / anchors
    breach = depth >= LIMIT
    near = (depth >= NEAR) & ~breach
    n_years = (ts[-1] - ts[0]) / (365.25 * 86_400)
    name = Path(path).name.replace("_curve.parquet", "")
    print(f"  {name:34s} days={len(uniq):5d}  5%-BREACH days={int(breach.sum()):3d} "
          f"({breach.sum()/n_years:.2f}/yr)  4-5%% near-miss={int(near.sum()):3d}  "
          f"worst day depth={depth.max()*100:.2f}%")
    if breach.any():
        for d, dep in zip(uniq[breach][:10], depth[breach][:10]):
            print(f"      breach day {pd.Timestamp(int(d)*86400, unit='s').date()}  depth {dep*100:.2f}%")

if __name__ == "__main__":
    pats = sys.argv[1:] or ["out/gate_killoff_curve.parquet", "out/ftmo1pct_*_curve.parquet"]
    print("=== FTMO daily-5% worst-mark breach census (anchor = prev-day close eq_c) ===")
    for pat in pats:
        for f in sorted(glob.glob(str(HERE / pat))):
            census(f)
