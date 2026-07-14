"""MAG_XAU stepper parity validation vs pandas intermediates + golden parquet.

Run from /Users/dsalamanca/vs_env/FableMultiAssets2/research:
    python3 /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/validate_mag_xau.py

Checks (per FMA3 bpure contract):
  1. continuous daily intermediates (mid, near, dist, ann, raw target) vs the
     pandas pipeline of the frozen source — max rel err, target <= 1e-8
  2. discrete state sequence (sig entry flag, near grid level) — EXACT at
     every daily bar, report n_mismatches / n_bars
  3. final hourly positions vs the frozen golden parquet — max|diff| over the
     full hourly grid, target <= 1e-12
  4. state round-trip: serialize mid-run, resume, identical tail positions
"""
import json
import math
import sys

FMA2 = "/Users/dsalamanca/vs_env/FableMultiAssets2"
FMA3_BPURE = "/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure"
for p in (FMA2 + "/research", FMA2, FMA3_BPURE):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

import research.core as core
from research.ext_import import mag_xau

from steppers.mag_xau_stepper import MagXauStepper, SYM, NAN

GOLDEN = ("/Users/dsalamanca/vs_env/FableMultiAssets3/model/v3/freeze/"
          "FMA3-v34-freeze-1/golden/mag_pos.parquet")
OUT = ("/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/"
       "mag_xau_parity.json")


def rel_err(a, b):
    """max relative error, NaN-pattern must match (mismatch -> inf)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = np.isnan(a), np.isnan(b)
    if (na != nb).any():
        return math.inf
    m = ~na
    if not m.any():
        return 0.0
    d = np.abs(a[m] - b[m])
    s = np.maximum(np.abs(b[m]), 1e-300)
    return float((d / s).max())


def main():
    # ------------------------------------------------------------- inputs
    hgrid = core.universe_frames(tuple(core.ALL))["ret"].index
    raw_close = core.load_hourly(SYM)["c"].reindex(hgrid)  # RAW closes, NaN off-bar
    ts_ns = hgrid.asi8
    vals = raw_close.to_numpy(dtype=float)
    n_hours = len(hgrid)

    # ------------------------------------------------------ run the stepper
    stepper = MagXauStepper(log_daily=True)
    pos_step = np.empty(n_hours, dtype=float)
    for i in range(n_hours):
        pos_step[i] = stepper.step(int(ts_ns[i]), {SYM: float(vals[i])})[SYM]
    stepper.flush_final_day()

    # ------------------------------------------- pandas reference pipeline
    d = mag_xau._daily_mid(SYM)
    near_pd = ((d / mag_xau.STEP - mag_xau.OFFSET).round() + mag_xau.OFFSET) * mag_xau.STEP
    dist_pd = (d - near_pd) / mag_xau.STEP
    sig_pd = ((dist_pd < -mag_xau.MIND) & (dist_pd > -mag_xau.BAND)).astype(float)
    ann_pd = d.pct_change().rolling(mag_xau.VOL_WIN).std() * np.sqrt(252)
    raw_pd = (sig_pd * mag_xau.VT / ann_pd).clip(-mag_xau.CAP, mag_xau.CAP)

    log = stepper.daily_log
    day_ns = np.array([r[0] for r in log], dtype=np.int64)
    mid_s = np.array([r[1] for r in log])
    near_s = np.array([r[2] for r in log])
    dist_s = np.array([r[3] for r in log])
    sig_s = np.array([r[4] for r in log])
    ann_s = np.array([r[5] for r in log])
    tgt_s = np.array([r[6] for r in log])

    n_daily = len(d)
    grid_match = (len(log) == n_daily) and bool((day_ns == d.index.asi8).all())

    # (1) continuous
    errs = {
        "mid": rel_err(mid_s, d.to_numpy()),
        "near": rel_err(near_s, near_pd.to_numpy()),
        "dist": rel_err(dist_s, dist_pd.to_numpy()),
        "ann": rel_err(ann_s, ann_pd.to_numpy()),
        "raw_target": rel_err(tgt_s, raw_pd.to_numpy()),
    }
    cont_max_err = max(errs.values()) if grid_match else math.inf

    # (2) discrete state: sig flag + near grid level, exact
    if grid_match:
        sig_mm = int((sig_s != sig_pd.to_numpy()).sum())
        near_mm = int((near_s != near_pd.to_numpy()).sum())
    else:
        sig_mm = near_mm = n_daily
    n_state_mm = sig_mm + near_mm
    state_exact = (n_state_mm == 0) and grid_match

    # (3) hourly positions vs golden
    golden = pd.read_parquet(GOLDEN)
    assert list(golden.columns) == [SYM]
    assert len(golden) == n_hours and bool((golden.index.asi8 == ts_ns).all())
    gvals = golden[SYM].to_numpy(dtype=float)
    pos_maxabs = float(np.abs(pos_step - gvals).max())
    n_pos_mm_1e12 = int((np.abs(pos_step - gvals) > 1e-12).sum())

    # cross-check: live make_positions == golden (sanity on inputs)
    live = mag_xau.make_positions().reindex(hgrid)[SYM].to_numpy(dtype=float)
    live_vs_golden = float(np.abs(live - gvals).max())

    # (4) state round-trip: serialize at midpoint, resume, compare tail
    half = n_hours // 2
    s1 = MagXauStepper()
    for i in range(half):
        s1.step(int(ts_ns[i]), {SYM: float(vals[i])})
    blob = json.dumps(s1.get_state())            # force real serialization
    s2 = MagXauStepper.from_state(json.loads(blob))
    tail_max = 0.0
    for i in range(half, n_hours):
        p2 = s2.step(int(ts_ns[i]), {SYM: float(vals[i])})[SYM]
        dd = abs(p2 - pos_step[i])
        if dd > tail_max:
            tail_max = dd

    result = {
        "sleeve": "mag_xau",
        "n_hourly_bars": n_hours,
        "n_daily_bars": n_daily,
        "daily_grid_match": grid_match,
        "continuous_rel_err": errs,
        "cont_max_err": cont_max_err,
        "state_seq_exact": state_exact,
        "n_state_mismatches": n_state_mm,
        "state_detail": {"sig_mismatches": sig_mm, "near_mismatches": near_mm},
        "pos_maxabs_vs_golden": pos_maxabs,
        "n_pos_bars_over_1e-12": n_pos_mm_1e12,
        "live_make_positions_vs_golden_maxabs": live_vs_golden,
        "state_roundtrip_tail_maxabs": tail_max,
        "pass": {
            "continuous_1e-8": cont_max_err <= 1e-8,
            "state_exact": state_exact,
            "positions_1e-12": pos_maxabs <= 1e-12,
            "state_roundtrip": tail_max == 0.0,
        },
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
