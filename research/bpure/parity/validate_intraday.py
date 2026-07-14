#!/usr/bin/env python3
"""Parity validation: intraday sleeve scalar stepper vs frozen pandas sleeve.

Checks (per the FMA3 bpure shared contract):
  (1) continuous quantities (hourly vol30; per-entry-day mv, sc(shifted), z,
      w, sig) — max rel err vs the pandas intermediates, target <= 1e-8;
  (2) discrete state sequence — EXACT match at every bar x symbol over the
      full grid: hold flag, entry state (0 = day not in mv index, 1 = mv-index
      day with NaN sig, 2 = valid sig), and per-entry-day clip/cap states
      (z clip at +-2, w cap at 1, sig clip at +-1; 9 = undefined/NaN);
  (3) final hourly positions max |diff| vs the frozen golden parquet over the
      full 49,379-hour x 2-symbol grid, target <= 1e-12.

Reference intermediates replicate the frozen make_positions line-for-line
(source diff-verified byte-identical to FMA2 live); the replica's position
matrix is itself checked against the golden parquet as a sanity gate.

Run from FMA2/research:  python3 validate_intraday.py
Writes intraday_parity.json next to this file.
"""
import json
import math
import sys
from pathlib import Path

FMA2R = "/Users/dsalamanca/vs_env/FableMultiAssets2/research"
FMA2 = "/Users/dsalamanca/vs_env/FableMultiAssets2"
BPURE = "/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure"
for p in (BPURE, FMA2, FMA2R):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402

import core                                            # noqa: E402
from steppers.intraday_stepper import IntradayStepper, DAY_NS  # noqa: E402

GOLDEN = ("/Users/dsalamanca/vs_env/FableMultiAssets3/model/v3/freeze/"
          "FMA3-v34-freeze-1/golden/intraday_pos.parquet")
OUT_JSON = Path(__file__).resolve().parent / "intraday_parity.json"

SYMS = ("USA500", "USTEC")
ENTRY_H, EXIT_H = 16, 21
ZCAP, SPAN_D, REF_VOL, SCALE = 2.0, 60, 0.15, 1.111


def rel_err(a, b):
    """Max-rel-err contribution for one pair; NaN pattern must match."""
    an, bn = a != a, b != b
    if an and bn:
        return 0.0
    if an != bn:
        return math.inf
    return abs(a - b) / max(abs(b), 1e-15)


def main():
    # ------------------------------------------------------------- reference
    U = core.universe_frames()                      # tuple(core.ALL)
    idx = U["ret"].index
    close, hasb = U["close"], U["has_bar"]
    hours = idx.hour.to_numpy()
    dates = idx.normalize()

    vol = core.realized_vol(U["ret"][list(SYMS)], span_days=30)
    vol_d = vol.resample("1D").last().shift(1)
    hold = (hours >= ENTRY_H) & (hours < EXIT_H)

    ref = {}
    for s in SYMS:
        m_pre = (hours == ENTRY_H - 1) & hasb[s].to_numpy()
        c_pre = close[s][m_pre]
        c_pre.index = c_pre.index.normalize()
        c_pre = c_pre.groupby(c_pre.index).last()
        m_open = (hours == ENTRY_H) & hasb[s].to_numpy()
        c_open = close[s][m_open]
        c_open.index = c_open.index.normalize()
        c_open = c_open.groupby(c_open.index).last()

        mv = c_open / c_pre - 1.0
        sc = mv.abs().ewm(span=SPAN_D, min_periods=20).mean().shift(1)
        z_raw = mv / sc
        z = z_raw.clip(-ZCAP, ZCAP) / ZCAP
        w_raw = (REF_VOL / vol_d[s]).clip(upper=1.0)
        w = w_raw.reindex(z.index)
        sig_pre = z * w * SCALE
        sig = sig_pre.clip(-1.0, 1.0)
        out = np.where(hold, np.nan_to_num(sig.reindex(dates).to_numpy()), 0.0)
        ref[s] = dict(c_pre=c_pre, c_open=c_open, mv=mv, sc=sc, z_raw=z_raw,
                      z=z, w=w, sig_pre=sig_pre, sig=sig, out=out)

    pos_ref = pd.DataFrame({s: ref[s]["out"] for s in SYMS}, index=idx)

    golden = pd.read_parquet(GOLDEN)
    assert golden.index.equals(idx), "golden index != universe grid index"
    assert list(golden.columns) == list(SYMS)
    ref_vs_golden = float(np.abs(pos_ref.to_numpy()
                                 - golden.to_numpy()).max())

    # --------------------------------------------------------------- stepper
    raw = {s: U["close"][s].where(U["has_bar"][s]).to_numpy() for s in SYMS}
    ts = idx.asi8
    n = len(ts)

    stp = IntradayStepper(log_entries=True)
    pos_stp = np.zeros((n, len(SYMS)))
    vol_stp = np.zeros((n, len(SYMS)))
    flags = np.zeros((n, len(SYMS), 2), dtype=bool)     # has15/has16 snapshot
    sig_state = np.full((n, len(SYMS)), np.nan)         # st['sig'] after step

    for t in range(n):
        tsn = int(ts[t])
        c = {s: float(raw[s][t]) for s in SYMS}
        p = stp.step(tsn, c)
        for k, s in enumerate(SYMS):
            st = stp.state[s]
            pos_stp[t, k] = p[s]
            vol_stp[t, k] = st["vol"]
            flags[t, k, 0] = st["has15"]
            flags[t, k, 1] = st["has16"]
            sig_state[t, k] = st["sig"]

    # ------------------------------------------------ (3) positions vs golden
    pos_maxabs = float(np.abs(pos_stp - golden.to_numpy()).max())

    # ------------------------------------------- (1) continuous quantities
    cont = {}
    # hourly vol30, full grid
    e = 0.0
    vp = vol.to_numpy()
    for k in range(len(SYMS)):
        for t in range(n):
            e = max(e, rel_err(vol_stp[t, k], vp[t, k]))
    cont["vol30_hourly"] = e

    # per-entry-day intermediates (days with an hour-16 bar == c_open.index)
    day_names = ["mv", "sc", "z", "w", "sig"]
    for nm in day_names:
        cont[nm] = 0.0
    n_entry_days = {}
    for k, s in enumerate(SYMS):
        log = stp.entry_log[s]
        open_days = ref[s]["c_open"].index
        assert len(log) == len(open_days), (
            f"{s}: stepper entry events {len(log)} != pandas hour-16 days "
            f"{len(open_days)}")
        n_entry_days[s] = len(log)
        mv_r = ref[s]["mv"].reindex(open_days).to_numpy()
        sc_r = ref[s]["sc"].reindex(open_days).to_numpy()
        z_r = ref[s]["z"].reindex(open_days).to_numpy()
        w_r = ref[s]["w"].reindex(open_days).to_numpy()
        sig_r = ref[s]["sig"].reindex(open_days).to_numpy()
        for i, rec in enumerate(log):
            assert rec["day_ns"] == open_days[i].value, \
                f"{s}: entry-day mismatch at {i}"
            cont["mv"] = max(cont["mv"], rel_err(rec["mv"], mv_r[i]))
            cont["sc"] = max(cont["sc"], rel_err(rec["sc"], sc_r[i]))
            cont["z"] = max(cont["z"], rel_err(rec["z"], z_r[i]))
            cont["w"] = max(cont["w"], rel_err(rec["w"], w_r[i]))
            cont["sig"] = max(cont["sig"], rel_err(rec["sig"], sig_r[i]))
    cont_max = max(cont.values())

    # --------------------------------------- (2) discrete state sequence
    # per bar x symbol: (hold, e_state) with e_state on hold rows:
    #   2 = valid sig, 1 = mv-index day but NaN sig, 0 = day not in mv index.
    # pandas side (day-level, broadcast to the day's rows):
    n_mismatch = 0
    mismatch_first = None
    for k, s in enumerate(SYMS):
        in_mv_days = set(ref[s]["mv"].index.asi8 // DAY_NS)
        sig_day = ref[s]["sig"].reindex(dates).to_numpy()   # per hourly row
        day_arr = ts // DAY_NS
        for t in range(n):
            h = hours[t]
            hold_t = ENTRY_H <= h < EXIT_H
            # pandas state
            if hold_t:
                sv = sig_day[t]
                if sv == sv:
                    e_p = 2
                elif day_arr[t] in in_mv_days:
                    e_p = 1
                else:
                    e_p = 0
                st_p = (1, e_p)
            else:
                st_p = (0, -1)
            # stepper state
            if hold_t:
                sv = sig_state[t, k]
                if sv == sv:
                    e_s = 2
                elif flags[t, k, 0] or flags[t, k, 1]:
                    e_s = 1
                else:
                    e_s = 0
                st_s = (1, e_s)
            else:
                st_s = (0, -1)
            if st_p != st_s:
                n_mismatch += 1
                if mismatch_first is None:
                    mismatch_first = (s, str(idx[t]), st_p, st_s)

    # mv-index day-set equality (full mv index incl. hour-15-only days):
    # stepper's committed days = days where flags at the day's LAST row show
    # has15|has16. Reconstruct per symbol.
    day_set_equal = {}
    for k, s in enumerate(SYMS):
        day_arr = ts // DAY_NS
        last_row_of_day = np.r_[day_arr[1:] != day_arr[:-1], True]
        stp_days = set(day_arr[last_row_of_day
                               & (flags[:, k, 0] | flags[:, k, 1])])
        pd_days = set(ref[s]["mv"].index.asi8 // DAY_NS)
        day_set_equal[s] = stp_days == pd_days
        if not day_set_equal[s]:
            n_mismatch += len(stp_days ^ pd_days)

    # per-entry-day clip/cap states (exact integer match)
    def zstate(z_raw):
        if z_raw != z_raw:
            return 9
        return -1 if z_raw <= -ZCAP else (1 if z_raw >= ZCAP else 0)

    def wstate(w):
        if w != w:
            return 9
        return 1 if w >= 1.0 else 0

    def sstate(sig_pre):
        if sig_pre != sig_pre:
            return 9
        return -1 if sig_pre <= -1.0 else (1 if sig_pre >= 1.0 else 0)

    n_day_state_mismatch = 0
    for k, s in enumerate(SYMS):
        open_days = ref[s]["c_open"].index
        zr = ref[s]["z_raw"].reindex(open_days).to_numpy()
        wr = ref[s]["w"].reindex(open_days).to_numpy()
        spr = ref[s]["sig_pre"].reindex(open_days).to_numpy()
        for i, rec in enumerate(stp.entry_log[s]):
            st_p = (zstate(zr[i]), wstate(wr[i]), sstate(spr[i]))
            st_s = (zstate(rec["z_raw"]), wstate(rec["w"]),
                    sstate(rec["sig_pre"]))
            if st_p != st_s:
                n_day_state_mismatch += 1
    n_mismatch += n_day_state_mismatch

    n_bars_states = n * len(SYMS)

    # ----------------------------------------------------- serialization test
    st1 = IntradayStepper()
    half = n // 2
    for t in range(half):
        st1.step(int(ts[t]), {s: float(raw[s][t]) for s in SYMS})
    blob = json.dumps(st1.get_state())              # round-trip through JSON
    st2 = IntradayStepper()
    st2.set_state(json.loads(blob))
    warm_max = 0.0
    for t in range(half, n):
        c = {s: float(raw[s][t]) for s in SYMS}
        p1 = st1.step(int(ts[t]), c)
        p2 = st2.step(int(ts[t]), c)
        for k, s in enumerate(SYMS):
            warm_max = max(warm_max,
                           abs(p1[s] - pos_stp[t, k]),
                           abs(p2[s] - pos_stp[t, k]))

    result = {
        "sleeve": "intraday",
        "grid": {"n_hours": int(n), "n_symbols": len(SYMS),
                 "start": str(idx[0]), "end": str(idx[-1])},
        "sanity_ref_replica_vs_golden_maxabs": ref_vs_golden,
        "continuous_rel_err": {k2: (None if v == math.inf else v)
                               for k2, v in cont.items()},
        "cont_max_err": None if cont_max == math.inf else cont_max,
        "n_entry_days": n_entry_days,
        "state_seq": {
            "n_bar_states": n_bars_states,
            "n_mismatches": int(n_mismatch),
            "exact": n_mismatch == 0,
            "mv_day_set_equal": day_set_equal,
            "n_day_clip_state_mismatch": int(n_day_state_mismatch),
            "first_mismatch": mismatch_first,
        },
        "pos_maxabs_vs_golden": pos_maxabs,
        "warm_start_resume_maxabs": warm_max,
        "pass": {
            "continuous_le_1e-8": bool(cont_max <= 1e-8),
            "states_exact": bool(n_mismatch == 0),
            "pos_le_1e-12": bool(pos_maxabs <= 1e-12),
        },
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
