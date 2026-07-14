"""Parity validation: carry_breakout scalar stepper vs frozen pandas sleeve.

Ground truth:
  - positions: model/v3/freeze/FMA3-v34-freeze-1/golden/carry_breakout_pos.parquet
  - intermediates/states: FMA2 live sleeve code path (byte-identical to the
    frozen source — verified by diff), instrumented here with identical lines.

Checks (contract):
  (1) continuous: hourly vol30 (32 syms), breakout ATR (11 syms), carry daily
      w rows (21 pairs) — max rel err vs pandas, target <= 1e-8
  (2) discrete states: Donchian state (0/1) per bar per symbol per system —
      EXACT; carry daily sig (-1/0/+1) and post-rank direction — EXACT
  (3) final hourly positions vs golden parquet, all 49,379 hours x 32 sleeve
      symbols (golden's 21 nonzero cols + 11 all-zero dropped cols) <= 1e-12
"""
import json
import math
import sys
import time

FMA2 = "/Users/dsalamanca/vs_env/FableMultiAssets2"
FMA3 = "/Users/dsalamanca/vs_env/FableMultiAssets3"
sys.path.insert(0, FMA2 + "/research")
sys.path.insert(0, FMA2)
sys.path.insert(0, FMA3 + "/research/bpure/steppers")

import numpy as np
import pandas as pd

import core  # FMA2 live
from carry_breakout_stepper import (
    CarryBreakoutStepper, parse_policy_rates, SYMBOLS, FX, BK_UNIV, N_FX,
    SWAP_MARKUP, RISK_PER_POS, VOL_FLOOR, VOL_SPAN_DAYS, ATR_DAYS,
    CARRY_THR, GATE_DAYS, TOP_K, N_FAST, N_SLOW, M_ATR, EXIT_RATIO)

GOLDEN = (FMA3 + "/model/v3/freeze/FMA3-v34-freeze-1/golden/"
          "carry_breakout_pos.parquet")
OUT_JSON = FMA3 + "/research/bpure/parity/carry_breakout_parity.json"

CARRY_UNIV = list(core.FX)
assert CARRY_UNIV == FX


# ---------------------------------------------------------------------------
# Reference (pandas, frozen-source lines) with instrumentation
# ---------------------------------------------------------------------------
def ref_policy_rate_daily():
    days = pd.date_range("2019-12-01", "2025-12-31", freq="D")
    out = {}
    for ccy, steps in core.engine_costs.POLICY_RATES.items():
        if len(ccy) != 3 or ccy.startswith("X"):
            continue
        s = pd.Series({pd.Timestamp(d): r for d, r in steps})
        out[ccy] = s.reindex(days.union(s.index)).ffill().reindex(days)
    return pd.DataFrame(out)


def ref_carry_book():
    """Exact carry_book(0.5, 63, 5) with intermediates returned."""
    rates = ref_policy_rate_daily()
    dc = core.daily_closes(CARRY_UNIV)
    diff = pd.DataFrame(
        {s: rates[s[:3]] - rates[s[3:]] for s in CARRY_UNIV}
    ).reindex(dc.index).ffill()
    net = diff.abs() - SWAP_MARKUP
    direction = np.sign(diff).where(net > CARRY_THR, 0.0)
    ranked = net.where(direction != 0).rank(axis=1, ascending=False)
    direction = direction.where(ranked <= TOP_K, 0.0)
    mom = dc / dc.shift(GATE_DAYS) - 1.0
    gate = (np.sign(mom) == direction) & (direction != 0)
    sig = direction.where(gate, 0.0)
    U = core.universe_frames()
    vol = core.realized_vol(U["ret"][CARRY_UNIV], span_days=VOL_SPAN_DAYS)
    vol_d = vol.resample("1D").last().reindex(dc.index).ffill()
    w = sig * RISK_PER_POS / vol_d.clip(lower=VOL_FLOOR)
    return {"w": w.fillna(0.0), "sig": sig, "direction": direction,
            "dc_index": dc.index}


def ref_donchian_states(n_days, x_days, m_atr):
    """Exact _donchian_long_only loop, recording the integer state per bar."""
    U = core.universe_frames()
    close = U["close"][BK_UNIV]
    has = U["has_bar"][BK_UNIV]
    vol = core.realized_vol(U["ret"][BK_UNIV], span_days=VOL_SPAN_DAYS)
    n, x = int(n_days * 24), int(x_days * 24)
    hi = close.rolling(n).max().shift(1)
    xlo = close.rolling(x).min().shift(1)
    atr_d = close.diff().abs().ewm(span=ATR_DAYS * 24).mean() * 24.0

    out = np.zeros((len(close), len(BK_UNIV)))
    st_rec = np.zeros((len(close), len(BK_UNIV)), dtype=np.int8)
    for j, sym in enumerate(BK_UNIV):
        c = close[sym].to_numpy()
        hb = has[sym].to_numpy()
        hi_a = hi[sym].to_numpy()
        xlo_a = xlo[sym].to_numpy()
        a_a = atr_d[sym].to_numpy()
        v_a = vol[sym].to_numpy()
        state, size, best = 0, 0.0, np.nan
        for i in range(len(c)):
            if not hb[i] or np.isnan(hi_a[i]) or np.isnan(a_a[i]):
                out[i, j] = state * size
                st_rec[i, j] = state
                continue
            if state == 0:
                if c[i] > hi_a[i]:
                    state, best = 1, c[i]
                    size = min(RISK_PER_POS / max(v_a[i], VOL_FLOOR), 1.0)
            else:
                best = max(best, c[i])
                if c[i] < xlo_a[i] or c[i] < best - m_atr * a_a[i]:
                    state, size = 0, 0.0
            out[i, j] = state * size
            st_rec[i, j] = state
        atr_ref = atr_d
    return out, st_rec, atr_ref


def main():
    t0 = time.time()
    U = core.universe_frames(tuple(core.ALL))
    hidx = U["ret"].index
    golden = pd.read_parquet(GOLDEN)
    assert golden.index.equals(hidx), "golden index != union hourly index"
    n_bars = len(hidx)

    # ---- pandas references ------------------------------------------------
    vol_ref = core.realized_vol(U["ret"][SYMBOLS],
                                span_days=VOL_SPAN_DAYS).to_numpy()
    car = ref_carry_book()
    x_fast = max(5, int(round(EXIT_RATIO * N_FAST)))
    x_slow = max(5, int(round(EXIT_RATIO * N_SLOW)))
    _, st_fast_ref, atr_ref_df = ref_donchian_states(N_FAST, x_fast, M_ATR)
    _, st_slow_ref, _ = ref_donchian_states(N_SLOW, x_slow, M_ATR)
    atr_ref = atr_ref_df.to_numpy()
    print(f"[{time.time()-t0:7.1f}s] pandas references done")

    # ---- drive the scalar stepper ------------------------------------------
    closes_raw = U["close"][SYMBOLS].where(U["has_bar"][SYMBOLS]).to_numpy()
    rows = closes_raw.tolist()
    epoch_days = (hidx.asi8 // (86400 * 10**9)).tolist()

    st = CarryBreakoutStepper(
        parse_policy_rates(core.engine_costs.POLICY_RATES))

    n_sym = len(SYMBOLS)
    pos_mine = np.empty((n_bars, n_sym))
    vol_mine = np.empty((n_bars, n_sym))
    atr_mine = np.empty((n_bars, len(BK_UNIV)))
    stf_mine = np.zeros((n_bars, len(BK_UNIV)), dtype=np.int8)
    sts_mine = np.zeros((n_bars, len(BK_UNIV)), dtype=np.int8)
    carry_rows = {}   # epoch_day -> (direction, sig, w)

    ann = 24.0 * 365.25
    for i in range(n_bars):
        p = st.step(epoch_days[i], rows[i])
        pos_mine[i] = p
        for j in range(n_sym):
            v = st.vol_ewm[j].value()
            vol_mine[i, j] = math.sqrt((v * 24.0) * 365.25) if v == v else math.nan
        for k in range(len(BK_UNIV)):
            a = st.atr_ewm[k].value()
            atr_mine[i, k] = a * 24.0 if a == a else math.nan
            stf_mine[i, k] = st.sys_f[k].state
            sts_mine[i, k] = st.sys_s[k].state
        lc = st.last_carry
        if lc is not None and lc["day"] not in carry_rows:
            carry_rows[lc["day"]] = (list(lc["direction"]), list(lc["sig"]),
                                     list(lc["w"]))
        if i % 10000 == 0:
            print(f"[{time.time()-t0:7.1f}s] bar {i}/{n_bars}")
    print(f"[{time.time()-t0:7.1f}s] stepper drive done")

    notes = []

    # ---- (1) continuous parity ---------------------------------------------
    def max_rel(mine, ref):
        both = np.isfinite(mine) & np.isfinite(ref)
        nan_mismatch = int((np.isnan(mine) != np.isnan(ref)).sum())
        e = np.abs(mine[both] - ref[both]) / np.maximum(np.abs(ref[both]),
                                                        1e-12)
        return (float(e.max()) if e.size else 0.0), nan_mismatch

    vol_err, vol_nanmm = max_rel(vol_mine, vol_ref)
    atr_err, atr_nanmm = max_rel(atr_mine, atr_ref)

    # carry daily rows: compare stepper-stamped days vs pandas frames
    dc_days = (car["dc_index"].asi8 // (86400 * 10**9))
    day_to_row = {int(d): r for r, d in enumerate(dc_days)}
    w_ref = car["w"].to_numpy()
    sig_ref = car["sig"].to_numpy()
    dir_ref = car["direction"].to_numpy()
    w_err = 0.0
    n_carry_state_mm = 0
    n_carry_days = 0
    for d, (dirn, sig, w) in carry_rows.items():
        r = day_to_row.get(int(d))
        if r is None:
            notes.append(f"stepper stamped day {d} missing from dc index")
            n_carry_state_mm += N_FX
            continue
        n_carry_days += 1
        for j in range(N_FX):
            if float(dirn[j]) != float(dir_ref[r, j]):
                n_carry_state_mm += 1
            elif float(sig[j]) != float(sig_ref[r, j]):
                n_carry_state_mm += 1
            rr = w_ref[r, j]
            e = abs(w[j] - rr) / max(abs(rr), 1e-12)
            if e > w_err:
                w_err = e
    cont_max_err = max(vol_err, atr_err, w_err)

    # ---- (2) discrete state sequences ---------------------------------------
    n_bk_mm = int((stf_mine != st_fast_ref).sum()) + \
        int((sts_mine != st_slow_ref).sum())
    n_state_mismatches = n_bk_mm + n_carry_state_mm
    state_seq_exact = n_state_mismatches == 0

    # ---- (3) positions vs golden --------------------------------------------
    gold_full = golden.reindex(columns=SYMBOLS, fill_value=0.0).to_numpy()
    pos_diff = np.abs(pos_mine - gold_full)
    pos_maxabs = float(pos_diff.max())
    ib, jb = np.unravel_index(int(pos_diff.argmax()), pos_diff.shape)
    notes.append(f"worst pos diff at {hidx[ib]} {SYMBOLS[jb]} "
                 f"(mine {pos_mine[ib, jb]!r} vs golden {gold_full[ib, jb]!r})")
    # golden dropped-columns sanity: our extra symbols must be identically 0
    extra = [s for s in SYMBOLS if s not in golden.columns]
    extra_max = float(np.abs(
        pos_mine[:, [SYMBOLS.index(s) for s in extra]]).max()) if extra else 0.0
    notes.append(f"symbols dropped by golden (must be all-zero): {extra}; "
                 f"stepper max|pos| there = {extra_max:.3e}")

    result = {
        "sleeve": "carry_breakout",
        "n_bars": n_bars,
        "n_symbols": n_sym,
        "golden_columns": list(golden.columns),
        "cont": {"vol30_max_rel_err": vol_err, "vol30_nan_mismatch": vol_nanmm,
                 "atr_max_rel_err": atr_err, "atr_nan_mismatch": atr_nanmm,
                 "carry_w_max_rel_err": w_err,
                 "n_carry_days_compared": n_carry_days},
        "cont_max_err": cont_max_err,
        "state_seq_exact": bool(state_seq_exact),
        "n_state_mismatches": int(n_state_mismatches),
        "n_state_mismatches_breakout": int(n_bk_mm),
        "n_state_mismatches_carry": int(n_carry_state_mm),
        "pos_maxabs_vs_golden": pos_maxabs,
        "notes": notes,
        "runtime_sec": round(time.time() - t0, 1),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
