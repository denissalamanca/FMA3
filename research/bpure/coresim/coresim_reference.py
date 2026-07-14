"""coresim_reference.py — scalar per-bar reference of the IDEALIZED STANDALONE
Core account (the a_h engine), Track B of the B-pure port.

WHAT THIS IS
------------
The Core book's idealized standalone equity multiple a_h is consumed by the
blend (model/v3/reproduce.py::static_blend) as the FROZEN native curve
research/outputs/v7_book_equity_1m.parquet [legacy on-disk name] column `eqc`,
normalized to 1.0 at its first bar and asof-ffilled onto the hourly grid.
That parquet was produced by engine/v7_bridge/extract_positions.py — a
bit-exact re-run of the NSF5 anchor (gbandrebal/sim.py::run_generic ->
v51_bandharvest._run_window -> engine/backtest.py::_run_core, notional mode,
noliq stop_out=1e-9), gate `status=reconciled` in
research/outputs/v7_extract_verification.json.

This module re-implements the ACCOUNT ARITHMETIC of that anchor as a pure
scalar per-bar loop (the analog of research/bpure/engine/bh_stepper.py for
the Satellite), so the future MQL5 CoreSim.mqh can be written from a spec
whose every statement has been validated bitwise in Python first:

  * per-leg stepper  = scalar port of NSF5 _run_core, notional sizing only,
    dd_k=0, throttle off, sl/tp = NaN, stop_out = 1e-9 (noliq);
  * book combiner    = scalar-faithful port of engine/portfolio.combine_curves
    (union grid, close-mark ffill, first-value backfill, worst marks only on
    own bars, margin ffill with 0-fill) + the flat legcap;
  * segment replay   = FROZEN band-trigger dates (the 31 'act' dates recorded
    in v7_extract_verification.json) with anchor seed chaining
    legcap = seed * (1/7) / n_legs. Trigger DETECTION is deliberately NOT
    re-implemented here (band-trigger DATE fork risk — see CORESIM_SPEC.md
    section 6): the standalone shadow REPLAYS the frozen dates exactly as
    model/v3 replays the frozen native curves.

INPUT BUILDERS ARE IMPORTED, NOT REWRITTEN (same discipline as bh_stepper):
bars / eurq / swap arrays come from NSF5 engine/backtest.prep_arrays and the
per-leg target arrays from sim.book("BTC_REP","USTEC") — both READ-ONLY
imports through the exact import dance of engine/v7_bridge/extract_positions
(sim import side-effect sets stop_out=1e-9 BEFORE anything runs).

VALIDATION GATES (per requested segment)
----------------------------------------
  G-a  per-leg bitwise: scalar leg stepper vs NSF5 numba run_backtest
       (eq_c / eq_w / margin, np.array_equal) on the window slice;
  G-b  book bitwise: combined eqc / eqw / margin vs the parity parquet slice
       [t0, t1) — index equality AND bit equality;
  G-c  seed-chain check: seed(segment j) == parquet eqc at the last bar < t0
       (and == triggers[j-1]['book'] where applicable).

Usage (python3 runs from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresim/coresim_reference.py \
    --segments 3 4            # validate segments 3 and 4 (0-based, of 32)
  ... --all                   # every committed segment (slow, ~full re-run)
  ... --no-selftest           # skip gate G-a (numba cross-check)

Writes research/bpure/coresim/coresim_parity.json with MEASURED results.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- FMA3 canonical paths by FILE (FMA3's config/engine dirs must NOT get on
# sys.path — they shadow NSF5's packages of the same names) -------------------
_HERE = Path(__file__).resolve()
FMA3 = _HERE.parents[3]
_spec = importlib.util.spec_from_file_location("fma3_paths",
                                               FMA3 / "config" / "paths.py")
paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paths)

# --- NSF5 READ-ONLY imports, order matters (sim -> lock_v5 stop_out=1e-9) ----
for _p in (paths.NSF5,
           paths.NSF5 / "mt5" / "reconcile",
           paths.NSF5 / "mt5" / "reconcile" / "gbandrebal"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sim  # noqa: E402  (side-effect: ACCOUNT['stop_out_level'] = 1e-9)
import engine.backtest as bt  # noqa: E402
from config import settings as S  # noqa: E402
from engine.cpcv_portfolio import _mask_from_windows  # noqa: E402
from sim import INIT, book, prime_feed  # noqa: E402

assert S.ACCOUNT["stop_out_level"] == 1e-9, \
    "lock_v5 stop_out side-effect missing — a_h anchor semantics need noliq"

VERIFICATION_JSON = paths.OUTPUTS / "v7_extract_verification.json"
PARITY_PARQUET = paths.OUTPUTS / "v7_book_equity_1m.parquet"
OUT_JSON = _HERE.parent / "coresim_parity.json"

MARGIN_CAP = 0.9          # run_backtest default (anchor call passes none)
REBAL_BAND = 0.25         # run_backtest default
STOP_OUT = 1e-9           # noliq (lock_v5)
W7 = 1.0 / 7.0            # 7 slots


# =============================================================================
# 1. Scalar per-leg stepper — statement-for-statement port of NSF5
#    engine/backtest.py::_run_core, NOTIONAL mode only, with the branches that
#    are structurally dead in the a_h configuration kept but asserted dead:
#    sl/tp are NaN (never armed), dd_k=0, throttle_thr=0, stop_out=1e-9.
#    Any edit that changes an expression's grouping breaks bit-parity.
# =============================================================================
def run_leg_scalar(bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c,
                   eurq, swap_flag, swap_long, swap_short, target,
                   contract, comm_side, leverage, lot_step, min_lot,
                   initial, i0, i1):
    """Run bars [i0, i1) starting flat with balance=initial (exact for a
    committed segment: the mask zeroes targets before i0, so the anchor's
    full-array state at i0 is exactly (balance=initial, pos=0, entry=0)).

    Returns (eq_c, eq_w, margin) float64 arrays of length i1-i0 plus the
    final carry state dict.  All arithmetic mirrors _run_core exactly;
    dd_scale/thr_scale are kept as literal 1.0 multiplications (bit-exact
    no-ops, retained so the expression shapes match the engine of record).
    """
    balance = initial
    pos = 0.0
    entry = 0.0
    blocked = math.nan  # forced-exit block: unreachable under noliq, kept
    dd_scale = 1.0
    thr_scale = 1.0
    n_out = i1 - i0
    eq_c = np.empty(n_out)
    eq_w = np.empty(n_out)
    margin_arr = np.zeros(n_out)
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
        if not math.isnan(blocked):                    # dead under noliq
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
            # _round_lots
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
                # close/reduce part
                if pos != 0.0 and (desired == 0.0 or desired * pos < 0.0
                                   or abs(desired) < abs(pos)):
                    close_lots = pos if desired * pos <= 0.0 else pos - desired
                    px = bid_o[i] if pos > 0 else ask_o[i]
                    pnl = (px - entry) * close_lots * contract * eurq[i]
                    balance += pnl - comm_side * abs(close_lots)
                    pos -= close_lots
                    n_trades += 1
                # open/add part
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

        # ---- 3. intrabar SL/TP: sl/tp are NaN for every a_h leg -> dead ----

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

        # ---- 5. margin stop-out (noliq: threshold 1e-9 never binds) ----
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
                entry = 0.0  # NSF5 leaves entry stale; harmless: pos==0
                blocked = target[i]
                eq_c[o] = balance
                eq_w[o] = balance
                margin_arr[o] = 0.0

        # ---- 6. negative balance protection ----
        if pos == 0.0 and balance <= 0.0:
            balance = 0.0
            eq_c[o:] = 0.0
            eq_w[o:] = 0.0
            raise AssertionError("a_h leg died — never happens in the anchor")

    state = dict(balance=balance, pos=pos, entry=entry, n_trades=n_trades)
    return eq_c, eq_w, margin_arr, state


# =============================================================================
# 2. Book combiner — scalar-faithful port of combine_curves + flat legcap.
#    Alignment is index logic (no FP); the FP-sensitive part is the LEFT-TO-
#    RIGHT per-minute summation in leg append order, reproduced here with
#    elementwise numpy adds in the same order.
# =============================================================================
def combine_legs(legs, flat):
    """legs = list of dicts {idx (DatetimeIndex), eq_c, eq_w, margin} in the
    anchor append order.  Returns (union_idx, eqc, eqw, mg)."""
    union = legs[0]["idx"]
    for lg in legs[1:]:
        union = union.union(lg["idx"])
    u = union.values  # datetime64[ns]

    tot_c = None
    tot_w = None
    aligned_m = []
    for lg in legs:
        li = lg["idx"].values
        # position of the last own bar <= each union stamp (-1 = before first)
        p = np.searchsorted(li, u, side="right") - 1
        has_bar = np.zeros(len(u), dtype=bool)
        exact = np.searchsorted(li, u, side="left")
        in_rng = exact < len(li)
        has_bar[in_rng] = li[exact[in_rng]] == u[in_rng]
        pc = np.clip(p, 0, None)
        c_f = lg["eq_c"][pc]                # ffill; p<0 -> index 0 = backfill
        c_f = np.where(p >= 0, c_f, lg["eq_c"][0])   # fillna(c.iloc[0])
        w_eff = np.where(has_bar, lg["eq_w"][pc], c_f)
        m_f = np.where(p >= 0, lg["margin"][pc], 0.0)  # ffill().fillna(0.0)
        tot_c = c_f if tot_c is None else tot_c + c_f
        tot_w = w_eff if tot_w is None else tot_w + w_eff
        aligned_m.append(m_f)
    # margin: builtin-sum semantics (0 + m0 + m1 + ...)
    tot_m = np.zeros(len(u))
    for m_f in aligned_m:
        tot_m = tot_m + m_f
    return union, tot_c + flat, tot_w + flat, tot_m


# =============================================================================
# 3. Segment replay + gates
# =============================================================================
def load_segments():
    rep = json.loads(VERIFICATION_JSON.read_text())
    assert rep["status"] == "reconciled", rep["status"]
    segs = [(pd.Timestamp(s["t0"]), pd.Timestamp(s["t1"])) for s in rep["segments"]]
    trig_books = [t["book"] for t in rep["triggers"]]
    return segs, trig_books


def leg_arrays(inst):
    bars, eurq, swap_flag, swap_long, swap_short = bt.prep_arrays(inst)
    return dict(
        idx=bars.index,
        bid_o=bars["bid_o"].to_numpy(), bid_h=bars["bid_h"].to_numpy(),
        bid_l=bars["bid_l"].to_numpy(), bid_c=bars["bid_c"].to_numpy(),
        ask_o=bars["ask_o"].to_numpy(), ask_h=bars["ask_h"].to_numpy(),
        ask_l=bars["ask_l"].to_numpy(), ask_c=bars["ask_c"].to_numpy(),
        eurq=eurq, swap_flag=swap_flag,
        swap_long=swap_long, swap_short=swap_short,
        cfg=S.INSTRUMENTS[inst])


def run_segment(sleeves, arrays, t0, t1, seed, selftest=True):
    """Replay one committed segment. Returns (union_idx, eqc, eqw, mg, report)."""
    legs_out = []
    flat = 0.0
    selftest_ok = True
    nan_targets = 0
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
            nan_targets += int(np.isnan(tgt64[i0:i1]).sum())
            cfg = A["cfg"]
            eq_c, eq_w, mg, state = run_leg_scalar(
                A["bid_o"], A["bid_h"], A["bid_l"], A["bid_c"],
                A["ask_o"], A["ask_h"], A["ask_l"], A["ask_c"],
                A["eurq"], A["swap_flag"], A["swap_long"], A["swap_short"],
                tgt64,
                float(cfg["contract_size"]), float(cfg["commission_side"]),
                float(cfg["leverage"]), float(cfg["lot_step"]),
                float(cfg["min_lot"]), float(legcap), i0, i1)
            if selftest:  # gate G-a: bitwise vs the NSF5 numba engine
                mask = _mask_from_windows(idx, [(t0, t1)])
                ref = bt.run_backtest(inst, tgt, sizing="notional",
                                      initial=legcap, mask=mask)
                sel = (idx >= t0) & (idx < t1)
                ok = (np.array_equal(ref.equity.to_numpy()[sel], eq_c)
                      and np.array_equal(ref.equity_worst.to_numpy()[sel], eq_w)
                      and np.array_equal(ref.margin.to_numpy()[sel], mg))
                if not ok:
                    selftest_ok = False
                    print(f"      G-a FAIL {name}/{inst}", flush=True)
            legs_out.append(dict(idx=idx[i0:i1], eq_c=eq_c, eq_w=eq_w,
                                 margin=mg, sleeve=name, inst=inst))
    assert nan_targets == 0, f"NaN targets in-window: {nan_targets}"
    union, eqc, eqw, mg = combine_legs(legs_out, flat)
    rep = dict(n_legs=len(legs_out), flat=flat, selftest_ok=selftest_ok)
    return union, eqc, eqw, mg, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", type=int, nargs="*", default=[3],
                    help="0-based committed-segment indices (see verification json)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-selftest", action="store_true")
    args = ap.parse_args()

    t_start = time.time()
    segs, trig_books = load_segments()
    which = list(range(len(segs))) if args.all else args.segments

    print(f"[1/3] prime IC feed + book('BTC_REP','USTEC')", flush=True)
    prime_feed("ic")
    sleeves = book("BTC_REP", "USTEC")
    insts = sorted({inst for legs in sleeves.values() for inst, _ in legs})
    arrays = {inst: leg_arrays(inst) for inst in insts}
    par = pd.read_parquet(PARITY_PARQUET)
    par_idx = par.index.values

    print(f"[2/3] replaying {len(which)} of {len(segs)} committed segments",
          flush=True)
    results = []
    all_pass = True
    for j in which:
        t0, t1 = segs[j]
        # gate G-c: seed = parquet eqc at the last bar < t0
        if j == 0:
            seed = INIT
            seed_src = "INIT"
        else:
            k = int(np.searchsorted(par_idx, np.datetime64(t0), side="left")) - 1
            seed = float(par["eqc"].iloc[k])
            seed_src = f"parquet@{par.index[k]}"
            tb = trig_books[j - 1]
            assert seed == tb, f"seed chain mismatch seg {j}: {seed!r} vs json {tb!r}"
        ts = time.time()
        union, eqc, eqw, mg, rep = run_segment(
            sleeves, arrays, t0, t1, seed, selftest=not args.no_selftest)
        sel = (par_idx >= np.datetime64(t0)) & (par_idx < np.datetime64(t1))
        ps = par[sel]
        idx_eq = bool(union.equals(ps.index))
        r = dict(segment=j, t0=str(t0), t1=str(t1), seed=seed, seed_src=seed_src,
                 bars=int(len(union)), n_legs=rep["n_legs"], flat=rep["flat"],
                 selftest_G_a=(None if args.no_selftest else rep["selftest_ok"]),
                 index_equal=idx_eq,
                 bit_equal_eqc=bool(idx_eq and np.array_equal(eqc, ps["eqc"].to_numpy())),
                 bit_equal_eqw=bool(idx_eq and np.array_equal(eqw, ps["eqw"].to_numpy())),
                 bit_equal_margin=bool(idx_eq and np.array_equal(mg, ps["margin"].to_numpy())),
                 max_abs_deqc=float(np.abs(eqc - ps["eqc"].to_numpy()).max()) if idx_eq else None,
                 max_abs_deqw=float(np.abs(eqw - ps["eqw"].to_numpy()).max()) if idx_eq else None,
                 max_abs_dmargin=float(np.abs(mg - ps["margin"].to_numpy()).max()) if idx_eq else None,
                 seconds=round(time.time() - ts, 1))
        seg_pass = (idx_eq and r["bit_equal_eqc"] and r["bit_equal_eqw"]
                    and r["bit_equal_margin"]
                    and (r["selftest_G_a"] in (True, None)))
        r["pass"] = bool(seg_pass)
        all_pass &= seg_pass
        results.append(r)
        print(f"      seg {j:2d} [{t0.date()} .. {t1.date()}) bars={r['bars']:>7,} "
              f"G-a={r['selftest_G_a']} idx={idx_eq} "
              f"eqc={r['bit_equal_eqc']} eqw={r['bit_equal_eqw']} "
              f"mg={r['bit_equal_margin']} ({r['seconds']}s)", flush=True)

    print("[3/3] writing report", flush=True)
    report = dict(generated=pd.Timestamp.now().isoformat(),
                  parity_target=str(PARITY_PARQUET),
                  verification_source=str(VERIFICATION_JSON),
                  segments_requested=which,
                  results=results,
                  all_pass=bool(all_pass),
                  runtime_s=round(time.time() - t_start, 1))
    OUT_JSON.write_text(json.dumps(report, indent=1))
    print(f"PASS={all_pass}  ({OUT_JSON}, {report['runtime_s']}s)", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
