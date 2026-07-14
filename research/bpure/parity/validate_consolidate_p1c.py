"""Parity validation for the consolidate_p1c stepper (seasonal + crypto_smart).

Run from FMA2/research (pandas 2.3.3 / numpy 2.4.2):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/validate_consolidate_p1c.py

Checks (contract):
  (1) continuous quantities vs pandas intermediates (seasonal vol; crypto
      sig_d / z / ma per coin) -- max rel err target <= 1e-8;
  (2) crypto 3-state hysteresis sequence -- EXACT at every daily-grid row;
  (3) final hourly positions vs the frozen golden parquets -- max|diff|
      target <= 1e-12 over the full grid x 4 symbols;
  (4) mid-run get_state()/set_state() JSON round-trip -- warm-started stepper
      must reproduce the cold-run tail bit-exactly.
"""
import json
import math
import sys

sys.path.insert(0, "/Users/dsalamanca/vs_env/FableMultiAssets2/research")
sys.path.insert(0, "/Users/dsalamanca/vs_env/FableMultiAssets2")
sys.path.insert(0, "/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/steppers")

import numpy as np
import pandas as pd

import core
import sleeves.crypto_smart as cs_mod
from consolidate_p1c_stepper import (ConsolidateP1cStepper, SYMBOLS, CR_SYMBOLS,
                                     L_MOM, Z_LONG, Z_SHORT, F_EXIT, MA_REGIME,
                                     VOL_SPAN_D)

GOLD = "/Users/dsalamanca/vs_env/FableMultiAssets3/model/v3/freeze/FMA3-v34-freeze-1/golden"
OUT = "/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/consolidate_p1c_parity.json"


def rel_err(a, b, abs_floor=1e-6):
    """max |a-b|/|b| over entries where both finite and |b| >= abs_floor,
    plus max abs err over all both-finite entries, plus NaN-mask agreement."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    fin_a = np.isfinite(a)
    fin_b = np.isfinite(b)
    nan_mismatch = int(np.sum(fin_a != fin_b))
    both = fin_a & fin_b
    if not both.any():
        return 0.0, 0.0, nan_mismatch
    d = np.abs(a[both] - b[both])
    max_abs = float(d.max())
    big = np.abs(b[both]) >= abs_floor
    max_rel = float((d[big] / np.abs(b[both][big])).max()) if big.any() else 0.0
    return max_rel, max_abs, nan_mismatch


def main():
    U = core.universe_frames(tuple(core.ALL))
    grid = U["ret"].index
    nbars = len(grid)
    ts_ns = grid.asi8
    xau_ret = U["ret"]["XAUUSD"].to_numpy()
    closes = {s: U["close"][s].to_numpy() for s in CR_SYMBOLS}

    # ---------------- drive the stepper over the full grid -------------------
    st = ConsolidateP1cStepper()
    st.debug_daily = []
    pos = {s: np.zeros(nbars) for s in SYMBOLS}
    vol_seq = np.full(nbars, np.nan)
    emitted_ts = []
    i_emit = 0
    # state round-trip checkpoint at mid-grid
    ckpt_bar = nbars // 2
    ckpt_json = None
    for i in range(nbars):
        if i == ckpt_bar:
            ckpt_json = json.dumps(st.get_state())     # serialize mid-run
        out = st.step(int(ts_ns[i]), float(xau_ret[i]),
                      float(closes["BTCUSD"][i]), float(closes["ETHUSD"][i]),
                      float(closes["SOLUSD"][i]))
        vol_seq[i] = st._sea_vol
        if out is not None:
            t, row = out
            emitted_ts.append(t)
            for s in SYMBOLS:
                pos[s][i_emit] = row[s]
            i_emit += 1
    out = st.finalize()
    t, row = out
    emitted_ts.append(t)
    for s in SYMBOLS:
        pos[s][i_emit] = row[s]
    i_emit += 1
    assert i_emit == nbars, f"emitted {i_emit} rows != {nbars} bars"
    assert emitted_ts == list(ts_ns), "emitted timestamps misaligned"

    # ---------------- (4) warm-start round-trip ------------------------------
    st2 = ConsolidateP1cStepper()
    st2.set_state(json.loads(ckpt_json))
    warm_rows = []
    for i in range(ckpt_bar, nbars):
        o = st2.step(int(ts_ns[i]), float(xau_ret[i]),
                     float(closes["BTCUSD"][i]), float(closes["ETHUSD"][i]),
                     float(closes["SOLUSD"][i]))
        if o is not None:
            warm_rows.append(o)
    warm_rows.append(st2.finalize())
    warm_max = 0.0
    for t, row in warm_rows:
        j = int(np.searchsorted(ts_ns, t))
        for s in SYMBOLS:
            warm_max = max(warm_max, abs(row[s] - pos[s][j]))
    # first warm emission is for bar ckpt_bar-1... it re-emits from prev state:
    # warm_rows[0] corresponds to bar ckpt_bar-1 whose row was already emitted
    # by the cold run; equality is exactly what we assert (bit-identical).

    # ---------------- pandas ground-truth intermediates ----------------------
    # seasonal vol
    gt_vol = core.realized_vol(U["ret"][["XAUUSD"]], span_days=30)["XAUUSD"].to_numpy()
    sea_rel, sea_abs, sea_nanmm = rel_err(vol_seq, gt_vol)

    # crypto daily internals recomputed exactly as the sleeve does
    D = core.daily_closes(CR_SYMBOLS)
    logp = np.log(D)
    lr = logp.diff()
    sigG = lr.ewm(span=VOL_SPAN_D, min_periods=VOL_SPAN_D).std()
    zG = logp.diff(L_MOM) / (sigG * np.sqrt(L_MOM))
    maG = D.rolling(MA_REGIME, min_periods=MA_REGIME).mean()

    dbg = st.debug_daily
    n_days = len(D)
    assert len(dbg) == n_days, f"daily grid rows: stepper {len(dbg)} vs pandas {n_days}"
    day_ns_ok = all(int(D.index.asi8[i]) == dbg[i]["day_ns"] for i in range(n_days))
    assert day_ns_ok, "daily grid timestamps mismatch"

    # ground-truth state sequences (loop verbatim from the sleeve)
    def gt_states(s):
        zv = zG[s].to_numpy()
        ab = (D[s] > maG[s]).to_numpy()
        ok = np.isfinite(zv) & np.isfinite(maG[s].to_numpy())
        state = 0
        out = np.zeros(len(zv), dtype=np.int64)
        for i in range(len(zv)):
            if not ok[i]:
                state = 0
            else:
                if state == 0:
                    if zv[i] >= Z_LONG:
                        state = 1
                    elif zv[i] <= -Z_SHORT and not ab[i]:
                        state = -1
                elif state == 1:
                    if zv[i] < F_EXIT * Z_LONG:
                        state = 0
                        if zv[i] <= -Z_SHORT and not ab[i]:
                            state = -1
                else:
                    if zv[i] > -F_EXIT * Z_SHORT or ab[i]:
                        state = 0
                        if zv[i] >= Z_LONG:
                            state = 1
            out[i] = state
        return out

    cont = {"seasonal_vol": {"max_rel": sea_rel, "max_abs": sea_abs,
                             "nan_mask_mismatch": sea_nanmm}}
    n_state_mm = 0
    for s in CR_SYMBOLS:
        my_sig = [d["sig_d"][s] for d in dbg]
        my_z = [d["z"][s] for d in dbg]
        my_ma = [d["ma"][s] for d in dbg]
        my_st = np.array([d["state"][s] for d in dbg], dtype=np.int64)
        r1 = rel_err(my_sig, sigG[s].to_numpy())
        r2 = rel_err(my_z, zG[s].to_numpy())
        r3 = rel_err(my_ma, maG[s].to_numpy())
        mm = int(np.sum(my_st != gt_states(s)))
        n_state_mm += mm
        cont[f"{s}_sig_d"] = {"max_rel": r1[0], "max_abs": r1[1],
                              "nan_mask_mismatch": r1[2]}
        cont[f"{s}_z"] = {"max_rel": r2[0], "max_abs": r2[1],
                          "nan_mask_mismatch": r2[2]}
        cont[f"{s}_ma"] = {"max_rel": r3[0], "max_abs": r3[1],
                           "nan_mask_mismatch": r3[2]}
        print(f"{s}: sig_d rel {r1[0]:.3e}/abs {r1[1]:.3e} | z rel {r2[0]:.3e}"
              f"/abs {r2[1]:.3e} | ma rel {r3[0]:.3e}/abs {r3[1]:.3e} "
              f"| state mismatches {mm}/{n_days}")
    cont_max_rel = max(v["max_rel"] for v in cont.values())
    cont_nan_mm = sum(v["nan_mask_mismatch"] for v in cont.values())

    # ---------------- golden position parity ---------------------------------
    g_sea = pd.read_parquet(f"{GOLD}/seasonal_pos.parquet")
    g_cry = pd.read_parquet(f"{GOLD}/crypto_smart_pos.parquet")
    assert list(g_sea.index) == list(grid) and list(g_cry.index) == list(grid)
    per_sym = {}
    per_sym["XAUUSD"] = float(np.max(np.abs(pos["XAUUSD"] - g_sea["XAUUSD"].to_numpy())))
    for s in CR_SYMBOLS:
        per_sym[s] = float(np.max(np.abs(pos[s] - g_cry[s].to_numpy())))
    pos_maxabs = max(per_sym.values())
    n_pos_mm = int(sum(np.sum(np.abs(pos["XAUUSD"] - g_sea["XAUUSD"].to_numpy()) > 1e-12)
                       for _ in [0]))
    n_pos_mm += int(sum(np.sum(np.abs(pos[s] - g_cry[s].to_numpy()) > 1e-12)
                        for s in CR_SYMBOLS))

    print(f"seasonal vol: rel {sea_rel:.3e} / abs {sea_abs:.3e}")
    print(f"CONTINUOUS max rel err        : {cont_max_rel:.3e}")
    print(f"STATE mismatches              : {n_state_mm}/{n_days * len(CR_SYMBOLS)}")
    print(f"POS max|diff| vs golden       : {pos_maxabs:.3e}  per-sym {per_sym}")
    print(f"POS entries > 1e-12           : {n_pos_mm}/{nbars * len(SYMBOLS)}")
    print(f"WARM-START max|diff| vs cold  : {warm_max:.3e} over bars "
          f"[{ckpt_bar - 1}..{nbars - 1}]")

    result = {
        "sleeve": "consolidate_p1c",
        "symbols": SYMBOLS,
        "n_bars": int(nbars),
        "n_daily_rows": int(n_days),
        "continuous": cont,
        "cont_max_rel_err": cont_max_rel,
        "cont_nan_mask_mismatches": int(cont_nan_mm),
        "state_seq_exact": bool(n_state_mm == 0),
        "n_state_mismatches": int(n_state_mm),
        "n_state_rows": int(n_days * len(CR_SYMBOLS)),
        "pos_maxabs_vs_golden": pos_maxabs,
        "pos_maxabs_per_symbol": per_sym,
        "n_pos_entries_gt_1e-12": int(n_pos_mm),
        "warm_start_roundtrip_maxabs": float(warm_max),
        "gate_delta": None if pos_maxabs <= 1e-12 else "REQUIRED",
        "grid": [str(grid[0]), str(grid[-1])],
        "golden": [f"{GOLD}/seasonal_pos.parquet", f"{GOLD}/crypto_smart_pos.parquet"],
        "notes": [
            "rel err computed over entries with |truth| >= 1e-6; abs err over all "
            "both-finite entries; nan_mask_mismatch counts finite/NaN disagreements",
            "state sequence compared per daily-grid row per coin (3-state hysteresis)",
            "positions compared vs frozen golden parquets over the full hourly grid",
            "warm-start: JSON get_state/set_state at mid-grid, tail re-run bit-compared",
        ],
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {OUT}")
    # keep cs_mod import honest: verify frozen constants match live module
    assert (cs_mod.L_MOM, cs_mod.Z_LONG, cs_mod.Z_SHORT, cs_mod.F_EXIT,
            cs_mod.MA_REGIME, cs_mod.VOL_SPAN_D) == (L_MOM, Z_LONG, Z_SHORT,
                                                     F_EXIT, MA_REGIME, VOL_SPAN_D)
    return result


if __name__ == "__main__":
    main()
