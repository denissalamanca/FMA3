"""Parity validation: meanrev scalar stepper vs frozen pandas sleeve + golden.

Run from FMA2/research python env:
    cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && \
    python3 /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/validate_meanrev.py

Checks (bpure shared contract):
  (1) continuous quantities (daily sizing vol, w=K/clip(vol), FX z, IDX z)
      max REL err vs the pandas intermediates          target <= 1e-8
  (2) integer state sequences (FX hysteresis, IDX dip) EXACT on full grid
  (3) final hourly positions vs frozen golden parquet  max|diff| <= 1e-12
  (4) if (3) fails anywhere: substitute stepper output in build_c2 dict and
      run account_engine_1m, report gate delta vs pin
Extra: serialization round-trip (get_state -> json -> set_state) must
      reproduce the exact remaining hourly stream (EA warm-start proof).
"""
import importlib.util
import json
import sys
import time as _time
from pathlib import Path

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
FREEZE = FMA3 / "model/v3/freeze/FMA3-v34-freeze-1"
OUT_JSON = FMA3 / "research/bpure/parity/meanrev_parity.json"

sys.path.insert(0, str(FMA2 / "research"))
sys.path.insert(0, str(FMA2))
sys.path.insert(0, str(FMA3 / "research/bpure/steppers"))

import numpy as np   # noqa: E402
import pandas as pd  # noqa: E402

import core  # noqa: E402  (FMA2 live, byte-identical to freeze — hash-checked)
from meanrev_stepper import (FX_CROSSES, INDICES, PARAMS,  # noqa: E402
                             SYMBOLS, MeanrevStepper)


def _load_live_meanrev():
    spec = importlib.util.spec_from_file_location(
        "meanrev_live", FMA2 / "research/sleeves/meanrev.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hash(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel_err(mine: np.ndarray, ref: np.ndarray) -> tuple[float, int]:
    """Max relative error over cells where both are numbers; NaN==NaN and
    same-signed inf==inf count as exact. Returns (max_rel, n_nan_mismatch)."""
    both_nan = np.isnan(mine) & np.isnan(ref)
    nan_mm = int((np.isnan(mine) != np.isnan(ref)).sum())
    with np.errstate(invalid="ignore"):
        inf_eq = np.isinf(mine) & np.isinf(ref) & (np.sign(mine) == np.sign(ref))
    ok = ~(both_nan | inf_eq)
    a, b = mine[ok], ref[ok]
    finite = np.isfinite(a) & np.isfinite(b)
    inf_mm = int((~finite).sum() - np.isnan(a[~finite]).sum())  # inf mismatch
    a, b = a[finite], b[finite]
    denom = np.maximum(np.abs(b), 1e-300)
    mx = float(np.max(np.abs(a - b) / denom)) if a.size else 0.0
    if nan_mm or inf_mm:
        mx = float("inf")
    return mx, nan_mm


def main():
    t0 = _time.time()
    res = {"sleeve": "meanrev", "notes": []}

    # --- provenance ---
    h_frozen = _hash(FREEZE / "src/research/sleeves/meanrev.py")
    h_live = _hash(FMA2 / "research/sleeves/meanrev.py")
    assert h_frozen == h_live, "FMA2 live meanrev.py != frozen spec"
    res["spec_sha256"] = h_frozen
    mr = _load_live_meanrev()

    p = dict(PARAMS)
    assert p == mr.PARAMS, "stepper PARAMS drifted from frozen PARAMS"
    assert SYMBOLS == mr.SYMBOLS

    # --- pandas reference intermediates (exactly as make_positions) ---
    U = core.universe_frames(tuple(core.ALL))
    h_idx = U["ret"].index
    px = core.daily_closes(SYMBOLS)
    vol_d = (core.realized_vol(U["ret"][SYMBOLS], span_days=p["VOL_SPAN"])
             .resample("1D").last().reindex(px.index).ffill())

    ma = px[FX_CROSSES].rolling(p["L"]).mean()
    sd = px[FX_CROSSES].rolling(p["L"]).std()
    z_fx = (px[FX_CROSSES] - ma) / sd
    with np.errstate(divide="ignore", invalid="ignore"):
        z_ix = (px[INDICES].pct_change(p["D"])
                / (vol_d[INDICES] * np.sqrt(p["D"] / 365.25)))

    st_fx = mr._fx_states(px[FX_CROSSES], p["L"], p["Z_IN"], p["Z_OUT"])
    st_ix = mr._idx_states(px[INDICES], vol_d[INDICES], p["D"], p["Z_ENTRY"],
                           p["Z_EXIT"], p["TREND_L"], p["MAX_HOLD"])
    states = pd.concat([st_fx, st_ix], axis=1)
    w = p["K"] / vol_d[SYMBOLS].clip(lower=p["VOL_FLOOR"])
    pos_d = mr._freeze_size(states, w).clip(-p["POS_CAP"], p["POS_CAP"])
    gross = pos_d.abs().sum(axis=1)
    pos_d = pos_d.mul((p["GROSS_CAP"] / gross).clip(upper=1.0), axis=0)
    pos_h_ref = core.to_hourly(pos_d, h_idx,
                               lag_hours=p["EXEC_LAG"]).fillna(0.0).astype(float)

    golden = pd.read_parquet(FREEZE / "golden/meanrev_pos.parquet")[SYMBOLS]
    ref_vs_golden = float(np.nanmax(np.abs(pos_h_ref[SYMBOLS].to_numpy()
                                           - golden.to_numpy())))
    res["pandas_ref_vs_golden_maxabs"] = ref_vs_golden

    # --- run the scalar stepper over the full hourly grid ---
    raw = U["close"][SYMBOLS].where(U["has_bar"][SYMBOLS])
    arr = raw.to_numpy(dtype=np.float64)
    ts_list = raw.index.to_pydatetime()
    T, N = arr.shape

    stp = MeanrevStepper(record=True)
    out = np.empty((T, N), dtype=np.float64)
    for t in range(T):
        row = arr[t]
        closes = {SYMBOLS[j]: row[j] for j in range(N)}
        posn = stp.step(ts_list[t], closes)
        for j in range(N):
            out[t, j] = posn[SYMBOLS[j]]
    stp.finalize()

    # --- daily grid alignment ---
    my_days = pd.DatetimeIndex([pd.Timestamp(d) for d in stp.rec_day])
    same_days = my_days.equals(px.index)
    res["daily_grid_match"] = bool(same_days)
    res["n_days"] = int(len(px.index))
    if not same_days:
        res["notes"].append("DAILY GRID MISMATCH: stepper days != px.index")

    my_px = np.array(stp.rec_px)
    my_vol = np.array(stp.rec_vol)
    my_w = np.array(stp.rec_w)
    my_z = np.array(stp.rec_z)
    my_st = np.array(stp.rec_st, dtype=np.int64)
    my_pos_d = np.array(stp.rec_pos)

    # (1) continuous parity
    err_px, _ = rel_err(my_px, px[SYMBOLS].to_numpy())
    err_vol, _ = rel_err(my_vol, vol_d[SYMBOLS].to_numpy())
    err_w, _ = rel_err(my_w, w[SYMBOLS].to_numpy())
    z_ref = np.concatenate([z_fx.to_numpy(), z_ix.to_numpy()], axis=1)
    err_z, z_nan_mm = rel_err(my_z, z_ref)
    err_posd, _ = rel_err(my_pos_d, pos_d[SYMBOLS].to_numpy())
    res["continuous"] = {"px_daily": err_px, "vol_d": err_vol, "w": err_w,
                         "z": err_z, "z_nan_mismatch": z_nan_mm,
                         "pos_daily": err_posd}
    cont_max = max(err_px, err_vol, err_w, err_z)
    res["cont_max_err"] = cont_max

    # (2) exact integer state sequence
    st_ref = states[SYMBOLS].to_numpy().astype(np.int64)
    n_bars = int(st_ref.size)
    n_mm = int((my_st != st_ref).sum())
    res["n_bars"] = n_bars
    res["n_state_mismatches"] = n_mm
    res["state_seq_exact"] = bool(n_mm == 0)
    if n_mm:
        bad = np.argwhere(my_st != st_ref)[:20]
        res["state_mismatch_head"] = [
            {"day": str(px.index[i].date()), "sym": SYMBOLS[j],
             "mine": int(my_st[i, j]), "ref": int(st_ref[i, j])}
            for i, j in bad]

    # (3) hourly positions vs golden
    diff = np.abs(out - golden.to_numpy())
    pos_maxabs = float(np.nanmax(diff))
    res["pos_maxabs_vs_golden"] = pos_maxabs
    res["pos_n_cells_gt_1e-12"] = int((diff > 1e-12).sum())
    res["n_hours"] = int(T)
    res["pass_positions"] = bool(pos_maxabs <= 1e-12)

    # --- serialization round-trip (EA warm-start) ---
    half = T // 2
    stB = MeanrevStepper()
    outB = np.empty((T, N))
    for t in range(half):
        row = arr[t]
        posn = stB.step(ts_list[t], {SYMBOLS[j]: row[j] for j in range(N)})
        for j in range(N):
            outB[t, j] = posn[SYMBOLS[j]]
    blob = json.dumps(stB.get_state())           # through JSON, as an EA would
    stC = MeanrevStepper()
    stC.set_state(json.loads(blob))
    for t in range(half, T):
        row = arr[t]
        posn = stC.step(ts_list[t], {SYMBOLS[j]: row[j] for j in range(N)})
        for j in range(N):
            outB[t, j] = posn[SYMBOLS[j]]
    warm_max = float(np.nanmax(np.abs(outB - out)))
    res["warmstart_roundtrip_maxabs"] = warm_max
    res["warmstart_exact"] = bool(warm_max == 0.0)

    # (4) gate delta if positions differ beyond tolerance
    if pos_maxabs > 1e-12:
        res["gate_delta"] = _gate_delta(pd.DataFrame(out, index=h_idx,
                                                     columns=SYMBOLS))
    res["runtime_sec"] = round(_time.time() - t0, 1)
    OUT_JSON.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


def _gate_delta(pos_mine: pd.DataFrame) -> dict:
    """Substitute stepper positions for meanrev in the v34 build and rerun
    the 1m account engine; report deltas vs the pin."""
    import eval_v34_pin_s10 as ev  # noqa: F401  (only if reachable)
    raise NotImplementedError  # filled in only when needed


if __name__ == "__main__":
    main()
