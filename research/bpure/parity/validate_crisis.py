"""Parity validation: crisis scalar stepper vs frozen pandas sleeve + golden parquet.

Truths:
  * intermediates: the FMA2 live sleeve pipeline (cmp-verified byte-identical to
    model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/crisis.py), re-derived
    line-for-line here with intermediate capture.
  * final hourly positions: the frozen golden parquet
    model/v3/freeze/FMA3-v34-freeze-1/golden/crisis_pos.parquet.

Checks (contract):
  (1) continuous quantities max rel err vs pandas   target <= 1e-8
  (2) integer/discrete state sequence EXACT (trig_eq, trig_fx, up_au, 4 grid levels)
  (3) hourly positions max|diff| vs golden over the full grid   target <= 1e-12
  (4) warm-start round trip: serialize state mid-sample, restore, continue -> identical

Run:  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
      /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/validate_crisis.py
"""
import json
import math
import sys
from pathlib import Path

FMA2_RESEARCH = "/Users/dsalamanca/vs_env/FableMultiAssets2/research"
FMA2 = "/Users/dsalamanca/vs_env/FableMultiAssets2"
FMA3 = "/Users/dsalamanca/vs_env/FableMultiAssets3"
sys.path.insert(0, FMA2)
sys.path.insert(0, FMA2_RESEARCH)
sys.path.insert(0, str(Path(FMA3) / "research" / "bpure" / "steppers"))

import numpy as np                                    # noqa: E402
import pandas as pd                                   # noqa: E402
import core                                           # noqa: E402
import crisis_stepper as cs                           # noqa: E402
from crisis_stepper import CrisisStepper, expand_to_hourly  # noqa: E402

GOLDEN = Path(FMA3) / "model/v3/freeze/FMA3-v34-freeze-1/golden/crisis_pos.parquet"
OUT_JSON = Path(FMA3) / "research/bpure/parity/crisis_parity.json"

V0, D0, FX_V0 = 1.25, 0.05, 1.20
K_AU, K_JP, SPAN = 0.30, 0.25, 3
GRID = 0.02


def pandas_reference():
    """Frozen crisis.make_positions() line-for-line with intermediate capture."""
    U = core.universe_frames()
    idx = U["ret"].index

    dcA = core.daily_closes(core.ALL)
    dcA = dcA[dcA.index.dayofweek < 5]
    rA = dcA.pct_change()

    br = rA[core.INDICES].mean(axis=1)
    vr = (br.rolling(10).std() * np.sqrt(252)) / \
         (br.rolling(60).std() * np.sqrt(252))
    lev = (1.0 + br.fillna(0)).cumprod()
    dd = lev / lev.rolling(126, min_periods=20).max() - 1.0
    trig_eq = ((vr > V0) | (dd < -D0)).astype(float)
    s_eq = trig_eq.ewm(span=SPAN).mean()

    fr = rA[cs.JPX].mean(axis=1)
    fvr = (fr.rolling(10).std() * np.sqrt(252)) / \
          (fr.rolling(60).std() * np.sqrt(252))
    flev = (1.0 + fr.fillna(0)).cumprod()
    fma = flev.rolling(50, min_periods=20).mean()
    trig_fx = ((fvr > FX_V0) & (flev < fma)).astype(float)
    s_fx = trig_fx.ewm(span=SPAN).mean()

    au = dcA["XAUUSD"]
    au_ma = au.rolling(50, min_periods=20).mean()
    up_au = (au > au_ma).astype(float)

    vol = (rA[cs.SYMS].ewm(span=250, min_periods=60).std()
           * np.sqrt(252)).clip(lower=0.05)

    w_pre = pd.DataFrame(0.0, index=rA.index, columns=cs.SYMS)
    w_pre["XAUUSD"] = s_eq * up_au * (K_AU / vol["XAUUSD"])
    for s in cs.JPX:
        w_pre[s] = -s_fx * (K_JP / 3.0) / vol[s]

    w = ((w_pre / GRID).round() * GRID).clip(-1.0, 1.0)
    level = (w_pre / GRID).round()          # integer grid levels (pre-cap)
    gross = w.abs().sum(axis=1)
    scale = (3.0 / gross).clip(upper=1.0)
    w = w.mul(scale, axis=0)

    pos = core.to_hourly(w, idx, lag_hours=14).fillna(0.0)
    return {
        "dcA": dcA, "rA": rA, "idx": idx,
        "vr": vr, "dd": dd, "trig_eq": trig_eq, "s_eq": s_eq,
        "fvr": fvr, "flev": flev, "fma": fma, "trig_fx": trig_fx, "s_fx": s_fx,
        "au_ma": au_ma, "up_au": up_au, "vol": vol,
        "w_pre": w_pre, "level": level, "gross": gross, "scale": scale,
        "w": w, "pos": pos,
    }


def max_rel_err(mine, ref, name, nan_report):
    a = np.asarray(mine, dtype=float)
    b = np.asarray(ref, dtype=float)
    na, nb = np.isnan(a), np.isnan(b)
    n_nan_mismatch = int((na != nb).sum())
    if n_nan_mismatch:
        nan_report.append(f"{name}: {n_nan_mismatch} NaN-pattern mismatches")
    both = ~na & ~nb
    if not both.any():
        return 0.0
    err = np.abs(a[both] - b[both])
    den = np.maximum(np.abs(b[both]), 1e-30)
    rel = np.where(err == 0.0, 0.0, err / den)
    return float(rel.max())


def main():
    ref = pandas_reference()
    dcA = ref["dcA"]
    days = dcA.index
    n_days = len(days)

    # sanity: for the 10 input symbols there must be no INTERIOR NaN in the
    # daily closes (ffilled union grid) — the stepper's pct_change rule
    # (NaN if either side missing, pad prev) is only exercised on leading NaN.
    for s in cs.INPUT_SYMS:
        col = dcA[s]
        fv = col.first_valid_index()
        assert col.loc[fv:].notna().all(), f"interior NaN in daily closes {s}"

    # ---- run the scalar stepper over the full daily grid -------------------
    stepper = CrisisStepper()
    closes_mat = dcA[cs.INPUT_SYMS].to_numpy()
    ts_ns = days.view("int64")

    rows_w, rows_eff, diags = [], [], []
    half_state = None
    half_at = n_days // 2
    for i in range(n_days):
        if i == half_at:
            half_state = json.dumps(stepper.get_state())   # serializable proof
        out = stepper.step(int(ts_ns[i]), [float(x) for x in closes_mat[i]])
        rows_w.append([out["w"][s] for s in cs.SYMS])
        rows_eff.append(out["effective_ns"])
        diags.append(out["diag"])

    # ---- warm-start round trip: restore at half, redo the 2nd half --------
    st2 = CrisisStepper()
    st2.set_state(json.loads(half_state))
    warm_ok = True
    for i in range(half_at, n_days):
        out2 = st2.step(int(ts_ns[i]), [float(x) for x in closes_mat[i]])
        for k, s in enumerate(cs.SYMS):
            a, b = out2["w"][s], rows_w[i][k]
            if not ((a != a and b != b) or a == b):
                warm_ok = False

    # ---- (1) continuous parity ---------------------------------------------
    nan_report = []
    errs = {}
    errs["vr"] = max_rel_err([d["vr"] for d in diags], ref["vr"], "vr", nan_report)
    errs["dd"] = max_rel_err([d["dd"] for d in diags], ref["dd"], "dd", nan_report)
    errs["s_eq"] = max_rel_err([d["s_eq"] for d in diags], ref["s_eq"], "s_eq", nan_report)
    errs["fvr"] = max_rel_err([d["fvr"] for d in diags], ref["fvr"], "fvr", nan_report)
    errs["flev"] = max_rel_err([d["flev"] for d in diags], ref["flev"], "flev", nan_report)
    errs["fma"] = max_rel_err([d["fma"] for d in diags], ref["fma"], "fma", nan_report)
    errs["s_fx"] = max_rel_err([d["s_fx"] for d in diags], ref["s_fx"], "s_fx", nan_report)
    errs["au_ma"] = max_rel_err([d["au_ma"] for d in diags], ref["au_ma"], "au_ma", nan_report)
    for s in cs.SYMS:
        errs[f"vol_{s}"] = max_rel_err([d["vol"][s] for d in diags],
                                       ref["vol"][s], f"vol_{s}", nan_report)
        errs[f"w_pre_{s}"] = max_rel_err([d["w_pre"][s] for d in diags],
                                         ref["w_pre"][s], f"w_pre_{s}", nan_report)
        errs[f"w_{s}"] = max_rel_err([r[k] for r, k in
                                      zip(rows_w, [cs.SYMS.index(s)] * n_days)],
                                     ref["w"][s], f"w_{s}", nan_report)
    cont_max_err = float(max(errs.values()))

    # ---- (2) integer/discrete state sequence, EXACT ------------------------
    n_state_mismatches = 0
    ref_te = ref["trig_eq"].to_numpy()
    ref_tf = ref["trig_fx"].to_numpy()
    ref_up = ref["up_au"].to_numpy()
    for i in range(n_days):
        if diags[i]["trig_eq"] != int(ref_te[i]):
            n_state_mismatches += 1
        if diags[i]["trig_fx"] != int(ref_tf[i]):
            n_state_mismatches += 1
        if diags[i]["up_au"] != int(ref_up[i]):
            n_state_mismatches += 1
    ref_lvl = ref["level"]
    for s in cs.SYMS:
        rl = ref_lvl[s].to_numpy()
        for i in range(n_days):
            mine = diags[i]["level"][s]
            theirs = None if np.isnan(rl[i]) else int(rl[i])
            if mine != theirs:
                n_state_mismatches += 1
    n_state_checks = n_days * 7
    state_seq_exact = n_state_mismatches == 0

    # ---- (3) hourly positions vs golden ------------------------------------
    golden = pd.read_parquet(GOLDEN)
    hourly_ns = [int(t) for t in golden.index.view("int64")]
    pos_maxabs = 0.0
    n_pos_diff = 0
    for k, s in enumerate(cs.SYMS):
        col = expand_to_hourly(rows_eff, [r[k] for r in rows_w], hourly_ns)
        g = golden[s].to_numpy()
        d = np.abs(np.asarray(col) - g)
        pos_maxabs = max(pos_maxabs, float(d.max()))
        n_pos_diff += int((d > 1e-12).sum())

    # sanity: pandas reference itself vs golden (environment check)
    ref_vs_golden = float((ref["pos"][cs.SYMS].to_numpy()
                           - golden[cs.SYMS].to_numpy()).__abs__().max())

    # ---- margins to discrete thresholds (robustness diagnostics) ----------
    def _mindist(series, thresh):
        v = series.to_numpy()
        v = v[~np.isnan(v)]
        return float(np.abs(v - thresh).min()) if len(v) else float("nan")
    frac = (ref["w_pre"].to_numpy() / GRID)
    frac = frac[~np.isnan(frac)]
    tie_dist = float(np.abs(np.abs(frac - np.floor(frac)) - 0.5).min())
    margins = {
        "min|vr-1.25|": _mindist(ref["vr"], V0),
        "min|dd+0.05|": _mindist(ref["dd"], -D0),
        "min|fvr-1.20|": _mindist(ref["fvr"], FX_V0),
        "min|flev-fma|": float(np.nanmin(np.abs((ref["flev"] - ref["fma"]).to_numpy()))),
        "min|au-au_ma|": float(np.nanmin(np.abs((dcA["XAUUSD"] - ref["au_ma"]).to_numpy()))),
        "min|grid_tie|": tie_dist,
        "max_gross_pre_cap": float(ref["gross"].max()),
        "n_days_gross_gt_cap": int((ref["gross"] > 3.0).sum()),
    }

    result = {
        "sleeve": "crisis",
        "stepper_path": str(Path(FMA3) / "research/bpure/steppers/crisis_stepper.py"),
        "validate_path": str(Path(__file__).resolve()),
        "golden_path": str(GOLDEN),
        "grid": {"n_daily_bars": int(n_days), "n_hourly_bars": len(hourly_ns),
                 "daily_first": str(days[0]), "daily_last": str(days[-1])},
        "continuous": {"max_rel_err": cont_max_err, "per_quantity": errs,
                       "nan_pattern_mismatches": nan_report},
        "state_sequence": {"exact": state_seq_exact,
                           "n_mismatches": n_state_mismatches,
                           "n_daily_bars": int(n_days),
                           "n_checks": n_state_checks,
                           "states": ["trig_eq", "trig_fx", "up_au",
                                      "level_XAUUSD", "level_AUDJPY",
                                      "level_NZDJPY", "level_CADJPY"]},
        "positions": {"max_abs_diff_vs_golden": pos_maxabs,
                      "n_cells_gt_1e-12": n_pos_diff,
                      "n_cells": len(hourly_ns) * len(cs.SYMS),
                      "pandas_ref_vs_golden_maxabs": ref_vs_golden},
        "warm_start_roundtrip_identical": warm_ok,
        "threshold_margins": margins,
    }
    OUT_JSON.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
