"""Parity validation: trend_v2 scalar stepper vs pandas pipeline + golden.

Truth sources:
  * intermediates: FMA2/research live pipeline (byte-identical to the frozen
    spec model/v3/freeze/FMA3-v34-freeze-1/src — verified by diff),
    replicated inline here (same calls, same order) to expose sig_d / s /
    max_w / target / hysteresis move flags.
  * final hourly positions: frozen golden parquet
    model/v3/freeze/FMA3-v34-freeze-1/golden/trend_v2_pos.parquet
    (this script also cross-checks the inline replication + live
    make_positions() against the golden parquet).

Checks (contract):
  (1) continuous quantities (sig_d, s post-deadband, max_w, target) max rel
      err vs pandas — target <= 1e-8;
  (2) discrete state sequence (hysteresis move flags + held weights) — EXACT
      at every daily bar x symbol;
  (3) stepper hourly positions (scalar to_hourly mapping, lag 6h) vs golden
      parquet — max |diff| target <= 1e-12 over the full grid;
  (4) if (3) fails anywhere, substitute into build_c2 and run
      account_engine_1m for the gate delta.

Run:  python3 validate_trend_v2.py   (from anywhere; paths are absolute)
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
for p in (str(FMA2 / "research"), str(FMA2),
          str(FMA3 / "research" / "bpure" / "steppers")):
    if p not in sys.path:
        sys.path.insert(0, p)

import core  # noqa: E402  (FMA2/research)
from sleeves import trend_v2 as sleeve  # noqa: E402
from trend_v2_stepper import (  # noqa: E402
    DELTA, EXEC_HOUR, K, LOOKBACKS, S0, SYMS, V0, VOL_MINP, VOL_SPAN,
    XAG_SHARE, TrendV2Stepper,
)

GOLDEN = (FMA3 / "model/v3/freeze/FMA3-v34-freeze-1/golden/"
          "trend_v2_pos.parquet")
OUT_JSON = FMA3 / "research/bpure/parity/trend_v2_parity.json"


def rel_err(a: np.ndarray, b: np.ndarray) -> tuple[float, int]:
    """max |a-b|/max(|b|,1e-15) where both finite-or-nan aligned; plus count
    of NaN-pattern mismatches."""
    an, bn = np.isnan(a), np.isnan(b)
    nan_mism = int((an != bn).sum())
    both = ~an & ~bn
    if both.sum() == 0:
        return 0.0, nan_mism
    d = np.abs(a[both] - b[both]) / np.maximum(np.abs(b[both]), 1e-15)
    return float(d.max()), nan_mism


def main() -> None:
    syms = list(SYMS)

    # ---------------- pandas truth (replicates make_positions internals) ----
    warnings.filterwarnings("ignore", category=FutureWarning)
    U = core.universe_frames()
    idx = U["ret"].index
    dc = core.daily_closes(syms)
    dret = dc.pct_change()

    sig_d = np.sqrt(dret.pow(2).ewm(span=VOL_SPAN, min_periods=VOL_MINP)
                    .mean())
    ann_vol = sig_d * np.sqrt(252.0)

    legs = []
    for L in LOOKBACKS:
        z = (dc / dc.shift(L) - 1.0) / (sig_d * np.sqrt(L))
        legs.append(np.tanh(z / K))
    s = sum(legs) / len(legs)
    agree = sum((np.sign(leg) == np.sign(s)).astype(float)
                for leg in legs) / len(legs)
    s = s * agree
    s = np.sign(s) * (s.abs() - S0).clip(lower=0.0) / (1.0 - S0)

    max_w = (V0 / ann_vol).clip(upper=1.0)
    max_w["XAGUSD"] = max_w["XAGUSD"] * XAG_SHARE
    target = (s * max_w).clip(-1.0, 1.0)

    tgt = target.to_numpy()
    mw = max_w.to_numpy()
    w = np.zeros_like(tgt)
    moved_truth = np.zeros(tgt.shape, dtype=bool)
    held = np.zeros(tgt.shape[1])
    for i in range(tgt.shape[0]):
        row_t, row_m = tgt[i], mw[i]
        valid = np.isfinite(row_t)
        band = DELTA * np.where(np.isfinite(row_m), row_m, 1.0)
        move = valid & (np.abs(row_t - held) > band)
        held = np.where(move, row_t, held)
        moved_truth[i] = move
        w[i] = held
    w_truth = pd.DataFrame(w, index=dc.index, columns=syms)
    pos_truth = core.to_hourly(w_truth, idx,
                               lag_hours=EXEC_HOUR + 1).fillna(0.0)

    # anchor: inline replication and live make_positions vs golden parquet
    golden = pd.read_parquet(GOLDEN)
    assert list(golden.columns) == syms, golden.columns
    assert golden.index.equals(idx), "golden grid != universe hourly grid"
    live = sleeve.make_positions()
    anchor_live = float((live - golden).abs().to_numpy().max())
    anchor_repl = float((pos_truth - golden).abs().to_numpy().max())

    # ---------------- run the scalar stepper over the full daily grid -------
    stp = TrendV2Stepper()
    n_days = len(dc.index)
    dc_np = dc.to_numpy()
    held_step = np.empty((n_days, len(syms)))
    sig_step = np.empty_like(held_step)
    s_step = np.empty_like(held_step)
    mw_step = np.empty_like(held_step)
    tgt_step = np.empty_like(held_step)
    moved_step = np.zeros((n_days, len(syms)), dtype=bool)
    for t in range(n_days):
        held_step[t] = stp.step(dc_np[t])
        sig_step[t] = stp.last["sig_d"]
        s_step[t] = stp.last["s"]
        mw_step[t] = stp.last["max_w"]
        tgt_step[t] = stp.last["target"]
        moved_step[t] = stp.last["moved"]

    # mid-history warm-start round-trip: serialize at day n//2, restore into a
    # fresh instance, re-run the second half — must be bitwise identical.
    stp2 = TrendV2Stepper()
    half = n_days // 2
    for t in range(half):
        stp2.step(dc_np[t])
    st = json.loads(json.dumps(stp2.get_state()))  # force JSON round-trip
    stp3 = TrendV2Stepper()
    stp3.set_state(st)
    warm_ok = True
    for t in range(half, n_days):
        h3 = stp3.step(dc_np[t])
        if not np.array_equal(np.asarray(h3), held_step[t]):
            warm_ok = False
            break

    # ---------------- (1) continuous parity --------------------------------
    cont = {}
    for name, a, b in (("sig_d", sig_step, sig_d.to_numpy()),
                       ("s_deadband", s_step, s.to_numpy()),
                       ("max_w", mw_step, mw),
                       ("target", tgt_step, tgt)):
        e, nm = rel_err(a, b)
        cont[name] = {"max_rel_err": e, "nan_pattern_mismatches": nm}
    cont_max = max(v["max_rel_err"] for v in cont.values())
    nan_mism_total = sum(v["nan_pattern_mismatches"] for v in cont.values())

    # ---------------- (2) discrete state sequence --------------------------
    move_mism = int((moved_step != moved_truth).sum())
    held_bitwise = int(sum((held_step[:, j] != w[:, j]).sum()
                           for j in range(len(syms))))
    n_state_bars = int(n_days * len(syms))
    state_exact = (move_mism == 0 and held_bitwise == 0)

    # ---------------- (3) hourly positions vs golden ------------------------
    # scalar-equivalent to_hourly: daily stamp d 00:00 -> effective
    # d+1 00:00 + (lag_hours-1)h = d+1 05:00; ffill onto hourly grid; NaN->0.
    eff = (dc.index + pd.Timedelta(days=1)
           + pd.Timedelta(hours=EXEC_HOUR + 1 - 1)).asi8
    hrs = idx.asi8
    j = np.searchsorted(eff, hrs, side="right") - 1
    pos_step = np.zeros((len(idx), len(syms)))
    valid_rows = j >= 0
    pos_step[valid_rows] = held_step[j[valid_rows]]

    gold_np = golden.to_numpy()
    diff = np.abs(pos_step - gold_np)
    pos_maxabs = float(diff.max())
    n_cells_over = int((diff > 1e-12).sum())

    result = {
        "sleeve": "trend_v2",
        "grid": {"n_hours": int(len(idx)), "n_daily_rows": int(n_days),
                 "n_syms": len(syms),
                 "start": str(idx[0]), "end": str(idx[-1])},
        "anchors": {
            "live_make_positions_vs_golden_maxabs": anchor_live,
            "inline_replication_vs_golden_maxabs": anchor_repl,
        },
        "continuous": cont,
        "continuous_max_rel_err": cont_max,
        "nan_pattern_mismatches_total": nan_mism_total,
        "state_sequence": {
            "n_bars": n_state_bars,
            "move_flag_mismatches": move_mism,
            "held_bitwise_mismatches": held_bitwise,
            "exact": state_exact,
        },
        "positions_vs_golden": {
            "max_abs_diff": pos_maxabs,
            "n_cells_over_1e-12": n_cells_over,
            "n_cells": int(diff.size),
        },
        "warm_start_roundtrip_bitwise": warm_ok,
    }

    print(json.dumps(result, indent=2))
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
