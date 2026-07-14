"""fcore_reference.py — TRACK B identity check + python reference for f_core[8],
the Core book's held fraction-of-own-equity per NET symbol, as frozen in
research/outputs/v7_book_frac_1h.parquet [legacy name].

HOW THE FROZEN PARQUET WAS ACTUALLY PRODUCED (engine/v7_bridge/
extract_positions.py, lines 850-860, gate status=reconciled):

    lots_df[inst] = NET signed lots summed across legs (USDJPY = 2 legs),
                    concat over committed segments, reindex(union).ffill()
                    .fillna(0.0)                       # seam carry included
    mid  = ((bars.bid_c + bars.ask_c) * 0.5).reindex(union).ffill()
    e    = eurq.reindex(union).ffill()
    val  = lots_df[inst] * contract_size * mid * e     # signed EUR notional
    eq_h = book_eqc.resample("1h").last().dropna()
    frac = val.resample("1h").last().reindex(eq_h.index).div(eq_h).fillna(0)

So f_core is NET-NOTIONAL / BOOK-EQUITY — the denominator is the combined
book close-mark equity, NOT any per-leg equity sum.  Every input is CoreSim
state (per-leg pos after fills/stop-out, the leg bar data, the combined book
eqc) — hypothesis (c) of FABLE REVISION v2 item 1.

THIS MODULE measures that identity over the FULL frozen hourly grid:

  candidate  f_H4[inst] = sum_legs(pos) * c_size * mid * eurq / book_eqc
             with pos captured from the CoreSim scalar stepper (a verbatim
             copy of coresim_reference.run_leg_scalar + pos capture, gated
             bitwise per leg against the original — gate G-d below), and
             book_eqc from CoreSim's own combine_legs (RECON-8d-proven).

  rejected hypotheses, measured for the record (USDJPY, the 2-leg symbol):
    H1/H2  equity-weighted / notional-sum-over-leg-equity-sum:
           (n1+n5)/(e1_leg+e5_leg)   — wrong denominator (leg equities sum
           to the book MINUS the other 7 legs' equity; expected to fail)
    H3     tgt passthrough (tgt1+tgt5) — ignores lot rounding, the 25%
           rebalance band, margin cap and the open-vs-close denominators.

GATES
  G-d  stepper-copy drift gate: run_leg_scalar_pos eq_c/eq_w/margin bitwise
       == coresim_reference.run_leg_scalar, every leg, every segment;
  G-e  net-lots bitwise vs frozen v7_book_lots_1m.parquet (all 8 columns);
  G-f  f_core bitwise (<=1e-12) vs frozen v7_book_frac_1h.parquet, full grid.

VERDICT (c)-VIABLE requires G-d AND G-e AND G-f.

Usage (python3 runs from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresim/fcore_reference.py

Writes research/bpure/coresim/fcore_identity.json with MEASURED results.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()

# importing coresim_reference by FILE does the whole NSF5 import dance
# (paths, sys.path order, sim stop_out side-effect, the lock_v5 assert)
_spec = importlib.util.spec_from_file_location(
    "coresim_reference", _HERE.parent / "coresim_reference.py")
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

from sim import INIT  # noqa: E402  (NSF5 path already set up by cr)
from config import settings as S  # noqa: E402

LOTS_PARQUET = cr.paths.OUTPUTS / "v7_book_lots_1m.parquet"
FRAC_PARQUET = cr.paths.OUTPUTS / "v7_book_frac_1h.parquet"
OUT_JSON = _HERE.parent / "fcore_identity.json"

MARGIN_CAP = cr.MARGIN_CAP
REBAL_BAND = cr.REBAL_BAND
STOP_OUT = cr.STOP_OUT
W7 = cr.W7


# =============================================================================
# 1. Stepper copy with position capture — VERBATIM run_leg_scalar plus
#    pos_arr[o] recorded at the anchor's capture point (extract_positions
#    _run_core_pos line 385: after fills AND after any stop-out, i.e. the
#    position whose marks defined eq_c[o]).  Gate G-d asserts the copy did
#    not drift from coresim_reference.run_leg_scalar.
# =============================================================================
def run_leg_scalar_pos(bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c,
                       eurq, swap_flag, swap_long, swap_short, target,
                       contract, comm_side, leverage, lot_step, min_lot,
                       initial, i0, i1):
    balance = initial
    pos = 0.0
    entry = 0.0
    blocked = math.nan
    dd_scale = 1.0
    thr_scale = 1.0
    n_out = i1 - i0
    eq_c = np.empty(n_out)
    eq_w = np.empty(n_out)
    margin_arr = np.zeros(n_out)
    pos_arr = np.zeros(n_out)
    n_trades = 0

    for i in range(i0, i1):
        o = i - i0
        mid_o = 0.5 * (bid_o[i] + ask_o[i])

        # ---- 1. swap at rollover ----
        if swap_flag[i] > 0 and pos != 0.0:
            frac = swap_long[i] if pos > 0 else swap_short[i]
            notional = abs(pos) * contract * mid_o
            balance += notional * frac / 365.0 * swap_flag[i] * eurq[i]

        # ---- 2. signal execution at open (notional mode) ----
        tgt = target[i]
        if not math.isnan(blocked):
            if tgt == blocked:
                tgt = 0.0 if pos == 0.0 else tgt
            else:
                blocked = math.nan
        sgn_t = 0.0 if tgt == 0.0 else (1.0 if tgt > 0 else -1.0)
        sgn_p = 0.0 if pos == 0.0 else (1.0 if pos > 0 else -1.0)
        desired = 0.0
        if sgn_t == 0.0:
            want_change = pos != 0.0
        else:
            px = ask_o[i] if sgn_t > 0 else bid_o[i]
            unit_eur = px * contract * eurq[i]
            lots = balance * abs(tgt) * dd_scale * thr_scale / unit_eur
            max_lots = (balance * leverage * MARGIN_CAP) / unit_eur
            if lots > max_lots:
                lots = max_lots
            nn = math.floor(lots / lot_step + 1e-9)
            lots = nn * lot_step
            if lots < min_lot:
                lots = 0.0
            if sgn_t != sgn_p:
                want_change = True
                desired = sgn_t * lots
            elif pos != 0.0 and abs(lots - abs(pos)) / abs(pos) > REBAL_BAND:
                want_change = True
                desired = sgn_t * lots
            else:
                want_change = False

        if want_change:
            delta = desired - pos
            if delta != 0.0:
                if pos != 0.0 and (desired == 0.0 or desired * pos < 0.0
                                   or abs(desired) < abs(pos)):
                    close_lots = pos if desired * pos <= 0.0 else pos - desired
                    px = bid_o[i] if pos > 0 else ask_o[i]
                    pnl = (px - entry) * close_lots * contract * eurq[i]
                    balance += pnl - comm_side * abs(close_lots)
                    pos -= close_lots
                    n_trades += 1
                if desired != 0.0 and abs(desired) > abs(pos):
                    add = desired - pos
                    px = ask_o[i] if add > 0 else bid_o[i]
                    if pos == 0.0:
                        entry = px
                    else:
                        entry = (entry * pos + px * add) / (pos + add)
                    balance -= comm_side * abs(add)
                    pos = desired
                    n_trades += 1

        # ---- 4. marks ----
        if pos > 0.0:
            unreal_c = (bid_c[i] - entry) * pos * contract * eurq[i]
            unreal_w = (bid_l[i] - entry) * pos * contract * eurq[i]
        elif pos < 0.0:
            unreal_c = (ask_c[i] - entry) * pos * contract * eurq[i]
            unreal_w = (ask_h[i] - entry) * pos * contract * eurq[i]
        else:
            unreal_c = 0.0
            unreal_w = 0.0
        eq_c[o] = balance + unreal_c
        eq_w[o] = balance + unreal_w

        # ---- 5. margin stop-out (noliq: never binds) ----
        if pos != 0.0:
            mid_c = 0.5 * (bid_c[i] + ask_c[i])
            margin = abs(pos) * contract * mid_c * eurq[i] / leverage
            margin_arr[o] = margin
            if eq_w[o] < STOP_OUT * margin:
                px = bid_l[i] if pos > 0 else ask_h[i]
                pnl = (px - entry) * pos * contract * eurq[i]
                balance += pnl - comm_side * abs(pos)
                n_trades += 1
                pos = 0.0
                entry = 0.0
                blocked = target[i]
                eq_c[o] = balance
                eq_w[o] = balance
                margin_arr[o] = 0.0

        # ---- extraction capture (anchor line 385) ----
        pos_arr[o] = pos

        # ---- 6. negative balance protection ----
        if pos == 0.0 and balance <= 0.0:
            raise AssertionError("a_h leg died — never happens in the anchor")

    state = dict(balance=balance, pos=pos, entry=entry, n_trades=n_trades)
    return eq_c, eq_w, margin_arr, pos_arr, state


# =============================================================================
# 2. Segment replay with capture
# =============================================================================
def run_segment_pos(sleeves, arrays, t0, t1, seed, drift_gate=True):
    """Replay one committed segment; returns (union, eqc, legs_cap, report).
    legs_cap = [{sleeve, inst, idx, pos, eq_c, tgt_slice}] in anchor order."""
    legs_out = []
    legs_cap = []
    flat = 0.0
    drift_ok = True
    for name, legs in sleeves.items():
        legcap = seed * W7 / len(legs)
        for inst, tgt in legs:
            A = arrays[inst]
            idx = A["idx"]
            i0 = int(np.searchsorted(idx.values, np.datetime64(t0), side="left"))
            i1 = int(np.searchsorted(idx.values, np.datetime64(t1), side="left"))
            if i1 <= i0:
                flat += legcap
                continue
            tgt64 = np.asarray(tgt, dtype=np.float64)
            args = (A["bid_o"], A["bid_h"], A["bid_l"], A["bid_c"],
                    A["ask_o"], A["ask_h"], A["ask_l"], A["ask_c"],
                    A["eurq"], A["swap_flag"], A["swap_long"], A["swap_short"],
                    tgt64,
                    float(A["cfg"]["contract_size"]),
                    float(A["cfg"]["commission_side"]),
                    float(A["cfg"]["leverage"]), float(A["cfg"]["lot_step"]),
                    float(A["cfg"]["min_lot"]), float(legcap), i0, i1)
            eq_c, eq_w, mg, pos, _ = run_leg_scalar_pos(*args)
            if drift_gate:  # G-d: copy bitwise == validated original
                r_c, r_w, r_m, _ = cr.run_leg_scalar(*args)
                if not (np.array_equal(eq_c, r_c) and np.array_equal(eq_w, r_w)
                        and np.array_equal(mg, r_m)):
                    drift_ok = False
                    print(f"      G-d FAIL {name}/{inst}", flush=True)
            legs_out.append(dict(idx=idx[i0:i1], eq_c=eq_c, eq_w=eq_w,
                                 margin=mg))
            legs_cap.append(dict(sleeve=name, inst=inst, idx=idx[i0:i1],
                                 pos=pos, eq_c=eq_c, tgt=tgt64[i0:i1]))
    union, eqc, eqw, mg = cr.combine_legs(legs_out, flat)
    return union, eqc, legs_cap, dict(flat=flat, drift_ok=drift_ok)


# =============================================================================
# 3. Full-grid identity check
# =============================================================================
def main():
    drift_gate = "--no-drift-gate" not in sys.argv
    t_start = time.time()
    segs, trig_books = cr.load_segments()

    print("[1/5] prime IC feed + book('BTC_REP','USTEC')", flush=True)
    cr.prime_feed("ic")
    sleeves = cr.book("BTC_REP", "USTEC")
    insts = sorted({inst for legs in sleeves.values() for inst, _ in legs})
    arrays = {inst: cr.leg_arrays(inst) for inst in insts}
    par = pd.read_parquet(cr.PARITY_PARQUET)          # eqc/eqw/margin 1m
    lots_par = pd.read_parquet(LOTS_PARQUET)          # net lots 1m
    frac_par = pd.read_parquet(FRAC_PARQUET)          # f_core 1h (target)
    par_idx = par.index.values

    print(f"[2/5] replaying ALL {len(segs)} committed segments "
          f"(drift gate G-d: {drift_gate})", flush=True)
    per_inst: dict[str, list[pd.Series]] = {}
    per_leg_jpy: dict[str, list[pd.Series]] = {}      # sleeve -> pos series
    per_leg_jpy_eq: dict[str, list[pd.Series]] = {}   # sleeve -> leg eqc
    per_leg_jpy_tgt: dict[str, list[pd.Series]] = {}  # sleeve -> tgt slices
    tgt_single: dict[str, list[pd.Series]] = {}       # single-leg tgt slices
    eqc_parts = []
    all_drift_ok = True
    eqc_bit_ok = True
    for j, (t0, t1) in enumerate(segs):
        if j == 0:
            seed = INIT
        else:
            k = int(np.searchsorted(par_idx, np.datetime64(t0), side="left")) - 1
            seed = float(par["eqc"].iloc[k])
            assert seed == trig_books[j - 1], f"seed chain mismatch seg {j}"
        union, eqc, legs_cap, rep = run_segment_pos(
            sleeves, arrays, t0, t1, seed, drift_gate=drift_gate)
        all_drift_ok &= rep["drift_ok"]
        sel = (par_idx >= np.datetime64(t0)) & (par_idx < np.datetime64(t1))
        ps = par[sel]
        if not (union.equals(ps.index)
                and np.array_equal(eqc, ps["eqc"].to_numpy())):
            eqc_bit_ok = False
            print(f"      seg {j}: book eqc NOT bit-equal", flush=True)
        eqc_parts.append(pd.Series(eqc, index=union))
        # net pos per instrument, anchor accumulation order
        seg_inst: dict[str, pd.Series] = {}
        for lc in legs_cap:
            s = pd.Series(lc["pos"], index=lc["idx"])
            seg_inst[lc["inst"]] = (s if lc["inst"] not in seg_inst
                                    else seg_inst[lc["inst"]] + s)
            if lc["inst"] == "USDJPY":
                per_leg_jpy.setdefault(lc["sleeve"], []).append(s)
                per_leg_jpy_eq.setdefault(lc["sleeve"], []).append(
                    pd.Series(lc["eq_c"], index=lc["idx"]))
                per_leg_jpy_tgt.setdefault(lc["sleeve"], []).append(
                    pd.Series(lc["tgt"], index=lc["idx"]))
            else:
                tgt_single.setdefault(lc["inst"], []).append(
                    pd.Series(lc["tgt"], index=lc["idx"]))
        for inst, s in seg_inst.items():
            per_inst.setdefault(inst, []).append(s)
        print(f"      seg {j:2d} [{t0.date()} .. {t1.date()}) ok", flush=True)

    print("[3/5] G-e: net lots vs frozen v7_book_lots_1m", flush=True)
    union_idx = par.index
    lots_mine = pd.DataFrame(
        {inst: pd.concat(per_inst[inst]).reindex(union_idx).ffill().fillna(0.0)
         for inst in sorted(per_inst)}, index=union_idx)
    lots_diff = {c: float((lots_mine[c] - lots_par[c]).abs().max())
                 for c in lots_par.columns}
    lots_bit = {c: bool(np.array_equal(lots_mine[c].to_numpy(),
                                       lots_par[c].to_numpy()))
                for c in lots_par.columns}

    print("[4/5] G-f: f_core H4 (net-notional / book-eqc) vs frozen frac",
          flush=True)
    eqc_mine = pd.concat(eqc_parts)
    assert eqc_mine.index.equals(union_idx)
    # verbatim producer arithmetic (extract_positions.py lines 850-860)
    val_1m = pd.DataFrame(index=union_idx)
    for inst in lots_mine.columns:
        A = arrays[inst]
        mid = pd.Series((A["bid_c"] + A["ask_c"]) * 0.5,
                        index=A["idx"]).reindex(union_idx).ffill()
        e = pd.Series(A["eurq"], index=A["idx"]).reindex(union_idx).ffill()
        c_size = float(A["cfg"]["contract_size"])
        val_1m[inst] = lots_mine[inst] * c_size * mid * e
    eq_h = eqc_mine.resample("1h").last().dropna()
    frac_mine = (val_1m.resample("1h").last().reindex(eq_h.index)
                 .div(eq_h, axis=0).fillna(0.0))
    idx_eq = bool(frac_mine.index.equals(frac_par.index))
    frac_diff = {c: float((frac_mine[c] - frac_par[c]).abs().max())
                 for c in frac_par.columns} if idx_eq else None
    frac_bit = {c: bool(np.array_equal(frac_mine[c].to_numpy(),
                                       frac_par[c].to_numpy()))
                for c in frac_par.columns} if idx_eq else None

    print("[5/5] rejected-hypothesis measurements (USDJPY + naive tgt)",
          flush=True)
    jpy_sleeves = sorted(per_leg_jpy)
    n_legs_series = []
    e_legs_series = []
    t_legs_series = []
    A = arrays["USDJPY"]
    midj = pd.Series((A["bid_c"] + A["ask_c"]) * 0.5,
                     index=A["idx"]).reindex(union_idx).ffill()
    ej = pd.Series(A["eurq"], index=A["idx"]).reindex(union_idx).ffill()
    cj = float(A["cfg"]["contract_size"])
    for sl in jpy_sleeves:
        p = pd.concat(per_leg_jpy[sl]).reindex(union_idx).ffill().fillna(0.0)
        n_legs_series.append(p * cj * midj * ej)
        e_legs_series.append(pd.concat(per_leg_jpy_eq[sl])
                             .reindex(union_idx).ffill().bfill())
        t_legs_series.append(pd.concat(per_leg_jpy_tgt[sl])
                             .reindex(union_idx).ffill().fillna(0.0))
    n_sum = sum(n_legs_series)
    e_sum = sum(e_legs_series)
    t_sum = sum(t_legs_series)
    h1 = ((n_sum.resample("1h").last() / e_sum.resample("1h").last())
          .reindex(eq_h.index).fillna(0.0))
    h3 = t_sum.resample("1h").last().reindex(eq_h.index).fillna(0.0)
    jpy_ref = frac_par["USDJPY"]
    hyp = dict(
        H1_H2_notional_sum_over_leg_equity_sum=float((h1 - jpy_ref).abs().max()),
        H3_tgt_sum=float((h3 - jpy_ref).abs().max()),
        H4_net_notional_over_book_eqc=(frac_diff["USDJPY"]
                                       if frac_diff is not None else None))
    tgt_naive = {}
    for inst in sorted(tgt_single):
        t = (pd.concat(tgt_single[inst]).reindex(union_idx)
             .ffill().fillna(0.0).resample("1h").last()
             .reindex(eq_h.index).fillna(0.0))
        tgt_naive[inst] = float((t - frac_par[inst]).abs().max())

    viable = (all_drift_ok and eqc_bit_ok and all(lots_bit.values())
              and idx_eq and frac_diff is not None
              and all(v <= 1e-12 for v in frac_diff.values()))
    report = dict(
        generated=pd.Timestamp.now().isoformat(),
        frozen_target=str(FRAC_PARQUET),
        producer="engine/v7_bridge/extract_positions.py lines 850-860",
        formula=("f_core[inst] = net_lots(ffill union, seam-carry) * c_size"
                 " * mid_c(ffill) * eurq(ffill) / book_eqc, hourly sample ="
                 " last 1m union bar in [h,h+1), fillna 0"),
        drift_gate_G_d=(all_drift_ok if drift_gate else None),
        book_eqc_bit_equal=eqc_bit_ok,
        lots_bit_equal_G_e=lots_bit,
        lots_max_abs_diff=lots_diff,
        frac_index_equal=idx_eq,
        frac_bit_equal_G_f=frac_bit,
        frac_max_abs_diff=frac_diff,
        usdjpy_hypotheses_max_abs_diff=hyp,
        naive_tgt_passthrough_max_abs_diff=tgt_naive,
        verdict=("(c)-VIABLE" if viable else "(c)-DEAD"),
        runtime_s=round(time.time() - t_start, 1))
    OUT_JSON.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in
                      ("drift_gate_G_d", "book_eqc_bit_equal",
                       "lots_max_abs_diff", "frac_max_abs_diff",
                       "usdjpy_hypotheses_max_abs_diff",
                       "naive_tgt_passthrough_max_abs_diff", "verdict",
                       "runtime_s")}, indent=1), flush=True)
    print(f"VERDICT={report['verdict']}  ({OUT_JSON})", flush=True)
    return 0 if viable else 1


if __name__ == "__main__":
    sys.exit(main())
