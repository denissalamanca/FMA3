"""book_orchestrator_sim.py — python STATEMENT MIRROR of the
CBookOrchestrator driving loop (mt5/ea/Include/Book/BookOrchestrator.mqh),
UNIT 3 of the S1 R1 whole-book compute gate.

WHAT THIS PROVES (the R1 number): the assembled native compute chain —
H1 signals (8 Sat sleeves + Ensemble -> f_sat[31]; CoreSim -> f_core[8]),
M1 equity (a = CoreSim combined eqc, b = SatEquityNative on the HELD
prior-hour f_sat targets), H1 blend (BookBlend on asof-sampled a_h/b_h)
— reproduces the golden RECON-4-pinned stream FMA3_fed_frac_v3.csv on
FROZEN inputs, consuming the SAME installed Common-Files bundles the
in-terminal twin (mt5/ea/scripts/TestBook.mq5) reads.

SCOPE PIN (S1): the Core leg targets are the FROZEN tgt column of the
CoreSim segment bundles (the live Core leg-target source = CoreEngine's
proven live signal path, wired in S2/S3). This mirror proves
ORCHESTRATION + COMPUTE, not the live feed (S0 proved that) nor
execution (S2/S3).

COMPONENTS (all individually proven; imported or copied verbatim):
  * H1 chain      : the Wave-1 steppers + EnsembleStepper, driven with
                    research/bpure/mql5/harness_sim.py's EXACT loop
                    statements (ffill[37], daily queues, deferred SC
                    emit, xau_ret clip) — recorded 4.197e-14 vs the
                    golden book;
  * b engine      : bh_stepper.BHAccountStepper (bitwise vs the numba
                    kernel + golden curve), quarter bundles parsed with
                    sat_equity_harness_sim's sparsity/f32 rules
                    (vectorized here — value-identical: parse float64,
                    ffill == carry, cast float32->float64);
  * a + f_core    : run_leg_scalar_pos / combine_legs copied VERBATIM
                    from research/bpure/coresim/fcore_reference.py /
                    coresim_reference.py (bit-equal on all 32 segments,
                    gates G-a..G-f) — copied, not imported, so the
                    mirror consumes ONLY the installed bundles (no NSF5
                    imports); ComputeFCore mirrored vectorized with the
                    identical float groupings and seam-carry law;
  * blend         : mirror_blend.BookBlendMirror (bit-proven vs golden).

DRIVING LOOP (BookOrchestrator drive contract, three clocks):
  1. core feed SEGMENT-BATCH fully AHEAD of the H1 clock (all 32 frozen
     segments, seed-chained), then core_done — every f_core row is
     consumable, the straddle guard is trivially satisfied;
  2. per H1 grid stamp h (previous stamp p): FIRST feed all pending M1
     rows with ts <= p, then StepH1(h). This is the general form of
     drive-contract 2 ("minutes of [h,h+1h) after StepH1(h)") that
     stays faithful across GRID GAPS: a minute in [p+1h, p+2h) needs
     the ring row of hour p, which only materializes at StepH1(h) (the
     deferred SC lag) — feeding it after StepH1(h) gives it pos[p],
     exactly the offline pos.reindex(floor(m)-1h) law;
  3. after the last H1 row: feed ALL remaining minutes, FinalizeH1
     (deferred SC row + trailing core-only hours).

The b tgt law (bh_stepper.iter_chunks): tgt(minute m) = the HELD f_sat
row at EXACTLY floor(m,1h)-1h; absent row -> 0.0 (reindex method=None +
nan_to_num). Held ring depth 16 (BOOKORC_HELD) — misses of rows that
WERE emitted are counted as ring-depth violations (must be 0).

EMISSION (scripts/export_book_frac_v3.py::build_rows semantics): per
grid hour (sat grid UNION f_core grid), one row per |net_frac| > 1e-12
in BROKER names (DAX->DE40, USA500->US500), sorted (epoch, broker name
ordinal); an all-flat present hour emits ONE __GRID__ sentinel.

Usage (run from FMA2/research per campaign convention; NEEDS python >= 3.13
— carry_breakout_stepper uses math.fma — i.e. /usr/local/bin/python3):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && \
    /usr/local/bin/python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/book/book_orchestrator_sim.py
Writes out/FMA3_book_mirror_actual.csv + book_mirror_parity.json and
prints the R1 verdict via validate_book_stream.compare().
"""
from __future__ import annotations

import bisect
import gc
import hashlib
import json
import math
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- paths
FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
HERE = FMA3 / "research/bpure/book"
COMMON = Path("/Users/dsalamanca/Library/Application Support/"
              "net.metaquotes.wine.metatrader5/drive_c/users/crossover/"
              "AppData/Roaming/MetaQuotes/Terminal/Common/Files")
GOLDEN = FMA3 / "research/outputs/mt5/FMA3_fed_frac_v3.csv"
GOLDEN_SHA = "d00b614b650b649ac9301b1ffd1eae66af4785ce4417bfa91755d367f8ab452e"
OUT_CSV = HERE / "out/FMA3_book_mirror_actual.csv"
OUT_JSON = HERE / "book_mirror_parity.json"

for p in (str(FMA2 / "research"), str(FMA2),
          str(FMA3 / "research/bpure/steppers"),
          str(FMA3 / "research/bpure/engine"),
          str(FMA3 / "research/bpure/blend"),
          str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import core                                                     # noqa: E402
engine_costs = core.engine_costs
import ensemble_stepper as ES                                   # noqa: E402
from mag_xau_stepper import MagXauStepper                       # noqa: E402
from intraday_stepper import IntradayStepper, SYMBOLS as ID_SYMS  # noqa: E402
from meanrev_stepper import MeanrevStepper, SYMBOLS as MR_SYMS  # noqa: E402
from consolidate_p1c_stepper import ConsolidateP1cStepper, CR_SYMBOLS  # noqa: E402
from carry_breakout_stepper import (CarryBreakoutStepper,       # noqa: E402
                                    SYMBOLS as CB_SYMS, parse_policy_rates)
from crisis_stepper import CrisisStepper, INPUT_SYMS as CR_IN, SYMS as CR_OUT  # noqa: E402
from trend_v2_stepper import TrendV2Stepper, SYMS as TV_SYMS, EXEC_HOUR  # noqa: E402
from sat_equity_harness_sim import (make_engine, SYMBOLS as SAT_SYMS,  # noqa: E402
                                    CROSS_IX, expected_header)
from mirror_blend import BookBlendMirror, broker_sym, cmp_ordinal  # noqa: E402
import validate_book_stream as VJ                               # noqa: E402

NAN = float("nan")
NSYM = 31
NNET = 8
W_CORE = 0.70                 # BOOKORC_W (model v3 Core capital share)
EPS = 1e-12                   # BOOKORC_EPS build_rows emission threshold
HELD = 16                     # BOOKORC_HELD f_sat held-row ring depth
CORE_SEED0 = 10000.0          # anchor INIT
W7 = 1.0 / 7.0                # CCoreBookSim m_W with SetSlots(7)
FINAL_EQC_TARGET = 532229.8433634703   # export_coresim_inputs.py pin

# H1 input CSV symbol order == core.ALL (BOOKORC_IN_SYMS)
IN_SYMS = ["AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY",
           "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD",
           "EURSEK", "EURUSD", "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY",
           "NZDUSD", "USDCHF", "USDJPY",
           "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
           "DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
           "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"]
CB_KEPT = ["AUDJPY", "CADCHF", "CADJPY", "EURCAD", "EURNZD", "EURUSD",
           "GBPJPY", "NZDJPY", "USDCHF", "USDJPY", "DAX", "JP225", "UK100",
           "US30", "USA500", "USTEC", "XAGUSD", "XAUUSD", "XBRUSD",
           "XNGUSD", "XTIUSD"]

# CoreSim leg static config (BOOKORC_LEG_* / TestCoreSim LEG TABLE)
LEG_SLOT = [1, 1, 1, 1, 1, 3, 3, 3, 1]
LEG_CONTRACT = [100.0, 100000.0, 1.0, 100000.0, 1.0,
                100000.0, 100000.0, 100000.0, 1.0]
LEG_COMM = [3.25, 3.25, 0.0, 3.25, 0.0, 3.25, 3.25, 3.25, 0.0]
LEG_LEV = [20.0, 30.0, 2.0, 30.0, 20.0, 30.0, 20.0, 20.0, 2.0]
LEG_STEP = [0.01, 0.01, 0.01, 0.01, 0.1, 0.01, 0.01, 0.01, 0.01]
LEG_MIN = [0.01, 0.01, 0.01, 0.01, 0.1, 0.01, 0.01, 0.01, 0.01]
LEG_NET = [7, 5, 2, 3, 6, 5, 0, 4, 1]     # leg -> f_core net column
NET_SYMS = ["AUDUSD", "BTCUSD", "ETHUSD", "EURGBP",
            "NZDUSD", "USDJPY", "USTEC", "XAUUSD"]
N_SEG = 32
SEG_COLS = ["leg", "ts", "bid_o", "bid_h", "bid_l", "bid_c",
            "ask_o", "ask_h", "ask_l", "ask_c",
            "eurq", "swap_flag", "swap_long", "swap_short", "tgt"]

QUARTERS = [f"{y}Q{q}" for y in range(2020, 2026) for q in range(1, 5)]

T0 = time.time()


def log(m):
    print(f"[{time.time() - T0:8.1f}s] {m}", flush=True)


# =============================================================================
# VERBATIM COPIES (research/bpure/coresim) — copied so the mirror consumes
# ONLY the installed bundles (no NSF5 sys.path dance). Do not edit:
# expression groupings are bit-parity load-bearing.
#   run_leg_scalar_pos : fcore_reference.py (gate G-d: bitwise ==
#                        coresim_reference.run_leg_scalar on every leg of
#                        every segment; pos captured after fills/stop-out)
#   combine_legs       : coresim_reference.py (gate G-b bitwise), adapted
#                        ONLY in that leg 'idx' is an int64 epoch array
#                        instead of a DatetimeIndex (searchsorted semantics
#                        identical; no float arithmetic touched).
# =============================================================================
MARGIN_CAP = 0.9
REBAL_BAND = 0.25
STOP_OUT = 1e-9


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


def combine_legs(legs, flat):
    """legs = list of dicts {idx (int64 epochs), eq_c, eq_w, margin} in the
    anchor append order.  Returns (union int64 epochs, eqc, eqw, mg)."""
    union = legs[0]["idx"]
    for lg in legs[1:]:
        union = np.union1d(union, lg["idx"])
    u = union

    tot_c = None
    tot_w = None
    aligned_m = []
    for lg in legs:
        li = lg["idx"]
        p = np.searchsorted(li, u, side="right") - 1
        has_bar = np.zeros(len(u), dtype=bool)
        exact = np.searchsorted(li, u, side="left")
        in_rng = exact < len(li)
        has_bar[in_rng] = li[exact[in_rng]] == u[in_rng]
        pc = np.clip(p, 0, None)
        c_f = lg["eq_c"][pc]
        c_f = np.where(p >= 0, c_f, lg["eq_c"][0])   # fillna(c.iloc[0])
        w_eff = np.where(has_bar, lg["eq_w"][pc], c_f)
        m_f = np.where(p >= 0, lg["margin"][pc], 0.0)
        tot_c = c_f if tot_c is None else tot_c + c_f
        tot_w = w_eff if tot_w is None else tot_w + w_eff
        aligned_m.append(m_f)
    tot_m = np.zeros(len(u))
    for m_f in aligned_m:
        tot_m = tot_m + m_f
    return u, tot_c + flat, tot_w + flat, tot_m


# =============================================================================
# Core phase — CCoreBookSim mirror: segment-batch replay of the 32 frozen
# segments from the installed bundles, harvesting (a) the combined 1m eqc
# into the a-sampler arrays and (b) the accumulated hourly f_core rows with
# the seam-carry / same-hour-overwrite (seam heal) law of ComputeFCore.
# =============================================================================
def run_core_phase():
    man = COMMON / "FMA3_coresim_segments.csv"
    rows = [ln.split(",") for ln in man.read_text().strip().split("\n")]
    assert len(rows) == N_SEG, f"manifest has {len(rows)} segments, want {N_SEG}"
    for j, r in enumerate(rows):
        assert int(r[0]) == j, "manifest not contiguous-from-0"

    a_ts: list[int] = []
    a_eqc: list[float] = []
    fts: list[int] = []
    frows: list[list[float]] = []
    carry = [None] * 9            # per-leg (pos, mid_c, eurq) seam ffill
    seed = CORE_SEED0

    for j in range(N_SEG):
        t_seg = time.time()
        df = pd.read_csv(COMMON / f"FMA3_coresim_seg{j}.csv", header=None,
                         names=SEG_COLS, float_precision="round_trip",
                         dtype={"leg": np.int64, "ts": np.int64,
                                **{c: np.float64 for c in SEG_COLS[2:]}})
        lid = df["leg"].to_numpy()
        assert (np.diff(lid) >= 0).all(), f"seg {j} not leg-major"
        assert len(df) == int(rows[j][3]), f"seg {j} rows != manifest"

        legs_out = []          # for combine (participating legs, book order)
        leg_cap = []           # per leg: (ts, pos, mid_c, eurq) or None
        flat = 0.0
        for leg_id in range(9):
            legcap = seed * W7 / LEG_SLOT[leg_id]   # NORMATIVE (seed*W)/n
            sub = df[lid == leg_id]
            if len(sub) == 0:
                flat += legcap
                leg_cap.append(None)
                continue
            ts = sub["ts"].to_numpy()
            assert (np.diff(ts) > 0).all(), f"seg {j} leg {leg_id} not ascending"
            n = len(sub)
            eq_c, eq_w, mg, pos_arr, _st = run_leg_scalar_pos(
                sub["bid_o"].tolist(), sub["bid_h"].tolist(),
                sub["bid_l"].tolist(), sub["bid_c"].tolist(),
                sub["ask_o"].tolist(), sub["ask_h"].tolist(),
                sub["ask_l"].tolist(), sub["ask_c"].tolist(),
                sub["eurq"].tolist(), sub["swap_flag"].tolist(),
                sub["swap_long"].tolist(), sub["swap_short"].tolist(),
                sub["tgt"].tolist(),
                LEG_CONTRACT[leg_id], LEG_COMM[leg_id], LEG_LEV[leg_id],
                LEG_STEP[leg_id], LEG_MIN[leg_id], legcap, 0, n)
            legs_out.append(dict(idx=ts, eq_c=eq_c, eq_w=eq_w, margin=mg))
            # captured f_core triple: pos AFTER fills, mid_c, eurq (own bars)
            mid_c = 0.5 * (sub["bid_c"].to_numpy() + sub["ask_c"].to_numpy())
            leg_cap.append((ts, pos_arr, mid_c, sub["eurq"].to_numpy()))
        assert legs_out, f"seg {j}: all legs empty"
        u, eqc, eqw, mg = combine_legs(legs_out, flat)

        # ---- a-sampler harvest (EndCoreSegment) ----
        if a_ts:
            assert u[0] > a_ts[-1], f"seg {j}: union stamps not ascending at seam"
        a_ts.extend(int(t) for t in u)
        a_eqc.extend(eqc.tolist())

        # ---- ComputeFCore mirror (vectorized; identical groupings) ----
        nu = len(u)
        net_pos = [np.zeros(nu) for _ in range(NNET)]
        net_mid = [np.zeros(nu) for _ in range(NNET)]
        net_qe = [np.zeros(nu) for _ in range(NNET)]
        net_ct = [np.zeros(nu) for _ in range(NNET)]
        net_has = [np.zeros(nu, dtype=bool) for _ in range(NNET)]
        for leg_id in range(9):        # net accumulation in LEG INDEX ORDER
            s = LEG_NET[leg_id]
            cap = leg_cap[leg_id]
            if cap is not None:
                lts, lpos, lmid, lqe = cap
                pi = np.searchsorted(lts, u, side="right") - 1
                hv = pi >= 0
                pc = np.clip(pi, 0, None)
                p = lpos[pc]
                mc = lmid[pc]
                qe = lqe[pc]
                if carry[leg_id] is not None:
                    cp, cm, cq = carry[leg_id]
                    p = np.where(hv, p, cp)
                    mc = np.where(hv, mc, cm)
                    qe = np.where(hv, qe, cq)
                    contrib = np.ones(nu, dtype=bool)
                else:
                    p = np.where(hv, p, 0.0)
                    mc = np.where(hv, mc, 0.0)
                    qe = np.where(hv, qe, 0.0)
                    contrib = hv       # before the instrument's first bar ever
            else:
                if carry[leg_id] is None:
                    continue           # flat leg, never traded before
                cp, cm, cq = carry[leg_id]
                p = np.full(nu, cp)
                mc = np.full(nu, cm)
                qe = np.full(nu, cq)
                contrib = np.ones(nu, dtype=bool)
            # skip-vs-add-0.0 is bit-identical here (0.0 + 0.0 == 0.0)
            net_pos[s] = net_pos[s] + np.where(contrib, p, 0.0)
            new = contrib & ~net_has[s]
            net_mid[s][new] = mc[new]
            net_qe[s][new] = qe[new]
            net_ct[s][new] = LEG_CONTRACT[leg_id]
            net_has[s] |= contrib
        fr = np.empty((nu, NNET))
        for s in range(NNET):
            # NORMATIVE grouping: ((lots * contract) * mid) * eurq / eqc
            val = ((net_pos[s] * net_ct[s]) * net_mid[s]) * net_qe[s]
            frs = val / eqc
            frs[~net_has[s]] = 0.0     # fillna(0) case
            fr[:, s] = frs
        hours = u - (u % 3600)
        last = np.ones(nu, dtype=bool)
        last[:-1] = hours[1:] != hours[:-1]
        hts = hours[last]
        hrows = fr[last]
        start = 0
        if fts and int(hts[0]) == fts[-1]:       # segment-seam straddle heal
            frows[-1] = hrows[0].tolist()
            start = 1
        for k in range(start, len(hts)):
            fts.append(int(hts[k]))
            frows.append(hrows[k].tolist())

        # ---- seam carry update (legs that traded this segment) ----
        for leg_id in range(9):
            cap = leg_cap[leg_id]
            if cap is not None:
                lts, lpos, lmid, lqe = cap
                carry[leg_id] = (float(lpos[-1]), float(lmid[-1]),
                                 float(lqe[-1]))

        seed = float(eqc[-1])                    # spec 6.2 seed chain
        log(f"core seg {j:2d}: {len(df):>7,} leg-bars, union {nu:>7,}, "
            f"flat {flat:.6g}, final_eqc {seed!r} "
            f"({time.time() - t_seg:.1f}s)")
        del df, legs_out, leg_cap
        gc.collect()

    assert all(fts[i] < fts[i + 1] for i in range(len(fts) - 1)), \
        "f_core hours not strictly ascending"
    return a_ts, a_eqc, fts, frows, seed


# =============================================================================
# M1 quarter loader — sat_equity_harness_sim's parse rules, VECTORIZED
# (value-identical: numpy strtod is correctly rounded like StringToDouble;
# ffill == the empty-cell carry; float32 cast applied after parse).
# =============================================================================
EXP_HEADER = expected_header().split(",")


def _dense_carry(col_str: np.ndarray, n: int) -> np.ndarray:
    """empty = carry previous (row 0 explicit) — the tgt/eurq/price rule."""
    mask = col_str != ""
    assert mask[0], "row 0 not explicit"
    vals = np.zeros(n)
    vals[mask] = col_str[mask].astype(np.float64)
    idx = np.where(mask, np.arange(n), -1)
    np.maximum.accumulate(idx, out=idx)
    return vals[idx]


def load_quarter(q: str) -> dict:
    df = pd.read_csv(COMMON / f"FMA3_bh_inputs_{q}.csv", dtype=str,
                     na_filter=False)
    assert list(df.columns) == EXP_HEADER, f"{q}: input header mismatch"
    n = len(df)
    ts = df["ts"].to_numpy().astype(np.int64)
    assert (np.diff(ts) > 0).all(), f"{q}: grid not strictly increasing"
    joined = "".join(df["has"].tolist()).encode()
    assert len(joined) == n * NSYM, f"{q}: bad has bitmask"
    has = (np.frombuffer(joined, dtype="S1").reshape(n, NSYM) == b"1")

    out = {"ts": ts.tolist(), "has": has.tolist(), "n": n}
    for short in ("bo", "ao", "bc", "ac", "bl", "ah"):
        m = np.empty((n, NSYM))
        for k, s in enumerate(SAT_SYMS):
            dense = _dense_carry(df[f"{short}_{s}"].to_numpy(), n)
            # float32-quantized feed: parse -> (float) cast -> double
            m[:, k] = dense.astype(np.float32).astype(np.float64)
        out[short] = m.tolist()
    cr = np.empty((n, 8))
    for c, cross in enumerate(("EURCAD", "EURCHF", "EURGBP", "EURJPY",
                               "EURNOK", "EURNZD", "EURSEK", "EURUSD")):
        cr[:, c] = _dense_carry(df[f"eurq_{cross}"].to_numpy(), n)
    out["cross"] = cr.tolist()
    for short, pre in (("swl", "swl"), ("sws", "sws")):
        m = np.zeros((n, NSYM))
        for k, s in enumerate(SAT_SYMS):
            col = df[f"{pre}_{s}"].to_numpy()
            mask = col != ""
            m[mask, k] = col[mask].astype(np.float64)   # empty = 0.0
        out[short] = m.tolist()
    # frozen tgt matrix — DIAGNOSTIC ONLY (the b tgt comes from the ring)
    m = np.empty((n, NSYM))
    for k, s in enumerate(SAT_SYMS):
        m[:, k] = _dense_carry(df[f"tgt_{s}"].to_numpy(), n)
    out["tgt_frozen"] = m.tolist()
    del df
    return out


# =============================================================================
# The three-clock driver
# =============================================================================
def main() -> int:
    log("verify golden pin ...")
    sha = hashlib.sha256(GOLDEN.read_bytes()).hexdigest()
    assert sha == GOLDEN_SHA, f"golden sha drift: {sha}"
    log(f"golden OK: {GOLDEN.name} sha256 {sha[:16]}...")

    # ------------------------------------------------ core phase (clock 1)
    log("core phase: 32 frozen segments, segment-batch ahead of the H1 clock")
    a_ts, a_eqc, fts, frows, final_eqc = run_core_phase()
    assert final_eqc == FINAL_EQC_TARGET, \
        f"core seed chain drift: {final_eqc!r} != {FINAL_EQC_TARGET!r}"
    a_first = a_eqc[0]
    core_done = True
    log(f"core done: {len(a_ts):,} union 1m bars, {len(fts):,} f_core rows, "
        f"a_first={a_first!r}, final_eqc BIT-EQUAL pin {FINAL_EQC_TARGET!r}")

    # ------------------------------------------------ components (H1 chain)
    ix = {s: i for i, s in enumerate(IN_SYMS)}
    mr_ix = [ix[s] for s in MR_SYMS]
    cb_ix = [ix[s] for s in CB_SYMS]
    id_ix = [ix[s] for s in ID_SYMS]
    tv_ix = [ix[s] for s in TV_SYMS]
    cr_in_ix = [ix[s] for s in CR_IN]
    cb_keep_ix = [list(CB_SYMS).index(s) for s in CB_KEPT]
    ix_xau, ix_btc, ix_eth, ix_sol = (ix["XAUUSD"], ix["BTCUSD"],
                                      ix["ETHUSD"], ix["SOLUSD"])

    mag = MagXauStepper()
    intr = IntradayStepper()
    mr = MeanrevStepper()
    sc = ConsolidateP1cStepper()
    cb = CarryBreakoutStepper(parse_policy_rates(engine_costs.POLICY_RATES))
    crisis = CrisisStepper()
    tv = TrendV2Stepper()
    sleeve_cols = {"meanrev": list(MR_SYMS), "carry_breakout": CB_KEPT,
                   "seasonal": ["XAUUSD"], "intraday": list(ID_SYMS),
                   "crisis": list(CR_OUT), "trend_v2": list(TV_SYMS),
                   "crypto_smart": list(CR_SYMBOLS), "mag": ["XAUUSD"]}
    shell = ES.EnsembleStepper(sleeve_cols)
    book_syms = list(shell.symbols)
    assert book_syms == list(SAT_SYMS), "shell symbols != SATEQ_SYMBOLS"

    blend = BookBlendMirror(W_CORE, NET_SYMS, book_syms)
    nnet = len(blend.net)
    assert nnet == 33, f"net columns {nnet} != 33"
    # emission order: broker-name ordinal insertion sort (build_rows sort key)
    perm = list(range(nnet))
    bsym = [broker_sym(blend.net[k]) for k in range(nnet)]
    for i in range(1, nnet):
        pk = perm[i]
        jj = i - 1
        while jj >= 0 and cmp_ordinal(bsym[perm[jj]], bsym[pk]) > 0:
            perm[jj + 1] = perm[jj]
            jj -= 1
        perm[jj + 1] = pk

    beng = make_engine()               # fresh 10k (2020Q1 state-in is fresh)

    # ------------------------------------------------ glue state
    ZEROS31 = [0.0] * NSYM
    ffill = [NAN] * 37
    has_day, cur_day = False, 0
    tvq: list = []
    crq: list = []
    trend_cur = [0.0] * 5
    crisis_cur = [NAN] * 4
    have_prev, prev_ts, prev_rows = False, 0, None
    h1_bars = 0

    ring: dict[int, list] = {}         # BOOKORC_HELD=16 exact-hour ring
    ring_order: deque = deque()
    ring_evicted: set = set()          # emitted-but-evicted hours (violation probe)
    ring_depth_violations = 0

    b_ts: list[int] = []
    b_v: list[float] = []
    m1_bars = 0

    fc_cursor = 0
    emit_rows: list[tuple] = []        # (epoch, symbol, "%.17g" | "0")
    stats = {"hours": 0, "data_rows": 0, "sentinels": 0}
    last_emit_hour = [None]
    tgt_diag = {"max_abs": 0.0, "n_hours_diff": 0}

    def a_query(h: int) -> float:
        i = bisect.bisect_right(a_ts, h) - 1
        if i < 0:
            return 1.0                 # model fillna(1.0)
        return a_eqc[i] / a_first

    def b_query(h: int) -> float:
        i = bisect.bisect_right(b_ts, h) - 1
        if i < 0:
            return 1.0
        return b_v[i] / b_v[0]

    def emit_hour(h: int, fc: list, fs: list):
        assert last_emit_hour[0] is None or h > last_emit_hour[0], \
            f"emission hour {h} not ascending"
        out = blend.step(fc, fs, a_query(h), b_query(h))
        any_leg = False
        for k in range(nnet):
            v = out[perm[k]]
            if abs(v) > EPS:
                emit_rows.append((h, bsym[perm[k]], f"{v:.17g}"))
                stats["data_rows"] += 1
                any_leg = True
        if not any_leg:
            emit_rows.append((h, "__GRID__", "0"))
            stats["sentinels"] += 1
        stats["hours"] += 1
        last_emit_hour[0] = h

    def blend_and_emit(h: int, fsat: list):
        nonlocal fc_cursor
        assert core_done, "core feed must be done before the H1 clock"
        while fc_cursor < len(fts) and fts[fc_cursor] < h:
            emit_hour(fts[fc_cursor], frows[fc_cursor], ZEROS31)
            fc_cursor += 1
        if fc_cursor < len(fts) and fts[fc_cursor] == h:
            fc = frows[fc_cursor]
            fc_cursor += 1
        else:
            fc = [0.0] * NNET          # static_blend fillna(0.0)
        emit_hour(h, fc, fsat)

    def stage_step_emit(ts_sec: int, saved: dict, emit_row: dict):
        srows = dict(saved)
        srows["seasonal"] = {"XAUUSD": emit_row["XAUUSD"]}
        srows["crypto_smart"] = {s: emit_row[s] for s in CR_SYMBOLS}
        net = shell.step(ts_sec * 10 ** 9, srows)
        fsat = [net[s] for s in book_syms]
        # held ring (the b tgt source): raw f_sat, depth 16
        ring[ts_sec] = fsat
        ring_order.append(ts_sec)
        if len(ring_order) > HELD:
            old = ring_order.popleft()
            del ring[old]
            ring_evicted.add(old)
        blend_and_emit(ts_sec, fsat)

    def step_h1(ts: int, raw: list):
        nonlocal has_day, cur_day, trend_cur, have_prev, prev_ts, prev_rows
        nonlocal h1_bars
        ts_ns = ts * 10 ** 9
        # --- daily rollover (ffill still as-of the previous bar) --------
        day = ts // 86400
        if not has_day:
            has_day, cur_day = True, day
        elif day != cur_day:
            tvcl = np.array([ffill[j] for j in tv_ix])
            held = list(tv.step(tvcl))
            tvq.append(((cur_day + 1) * 86400 + EXEC_HOUR * 3600, held))
            if (cur_day + 3) % 7 < 5:
                crcl = [ffill[j] for j in cr_in_ix]
                res = crisis.step(cur_day * 86400 * 10 ** 9, crcl)
                crq.append((res["effective_ns"] // 10 ** 9,
                            [res["w"][s] for s in CR_OUT]))
            cur_day = day
        # --- xau ret (prev ffill), then streaming ffill ------------------
        prev_x = ffill[ix_xau]
        for j in range(37):
            if raw[j] == raw[j]:
                ffill[j] = raw[j]
        xret = 0.0
        if prev_x == prev_x:
            r = ffill[ix_xau] / prev_x - 1.0
            xret = -0.30 if r < -0.30 else (0.30 if r > 0.30 else r)
        # --- activate pending daily targets -------------------------------
        while tvq and tvq[0][0] <= ts:
            trend_cur = list(tvq.pop(0)[1])
        while crq and crq[0][0] <= ts:
            w = crq.pop(0)[1]
            for j in range(4):
                if w[j] == w[j]:
                    crisis_cur[j] = w[j]
        # --- current-bar rows for the 7 non-deferred sleeves --------------
        cur = {}
        cur["mag"] = mag.step(ts_ns, {"XAUUSD": raw[ix_xau]})
        cur["intraday"] = intr.step(ts_ns,
                                    {s: raw[id_ix[k]]
                                     for k, s in enumerate(ID_SYMS)})
        cur["meanrev"] = mr.step(
            datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None),
            {s: raw[mr_ix[k]] for k, s in enumerate(MR_SYMS)})
        cb32 = cb.step(ts // 86400, [raw[j] for j in cb_ix])
        cur["carry_breakout"] = {s: cb32[cb_keep_ix[k]]
                                 for k, s in enumerate(CB_KEPT)}
        cur["trend_v2"] = {s: trend_cur[k] for k, s in enumerate(TV_SYMS)}
        cur["crisis"] = {s: (crisis_cur[k] if crisis_cur[k] == crisis_cur[k]
                             else 0.0) for k, s in enumerate(CR_OUT)}
        # --- seasonal/crypto deferred emission -----------------------------
        o = sc.step(ts_ns, xret, ffill[ix_btc], ffill[ix_eth], ffill[ix_sol])
        if o is not None:
            emit_t, emit_row = o
            assert have_prev and emit_t == prev_ts * 10 ** 9, \
                f"SC emission misaligned at H1 bar {h1_bars}"
            stage_step_emit(prev_ts, prev_rows, emit_row)
        else:
            assert h1_bars == 0, f"expected SC emission at H1 bar {h1_bars}"
        prev_rows = cur
        prev_ts = ts
        have_prev = True
        h1_bars += 1

    # ------------------------------------------------ M1 feeder (clock 3)
    q_state = {"qi": 0, "data": None, "t": 0, "cur_wanted": None,
               "cur_tgt": ZEROS31}

    def feed_until(limit: int):
        """StepM1 for every pending 1m row with ts <= limit."""
        nonlocal m1_bars, ring_depth_violations
        while True:
            d = q_state["data"]
            if d is None or q_state["t"] >= d["n"]:
                if d is not None:
                    q_state["data"] = None
                    gc.collect()
                if q_state["qi"] >= len(QUARTERS):
                    return
                q = QUARTERS[q_state["qi"]]
                t_q = time.time()
                q_state["data"] = load_quarter(q)
                q_state["t"] = 0
                q_state["qi"] += 1
                d = q_state["data"]
                log(f"M1 quarter {q}: {d['n']:,} bars loaded "
                    f"({time.time() - t_q:.1f}s); b bal={beng.balance:,.2f} "
                    f"trades={beng.n_trades:,}")
            ts_l = d["ts"]
            has_l = d["has"]
            bo_l, ao_l, bc_l, ac_l = d["bo"], d["ao"], d["bc"], d["ac"]
            bl_l, ah_l = d["bl"], d["ah"]
            cr_l, swl_l, sws_l = d["cross"], d["swl"], d["sws"]
            tgtf_l = d["tgt_frozen"]
            t = q_state["t"]
            n = d["n"]
            step = beng.step
            while t < n:
                mts = ts_l[t]
                if mts > limit:
                    q_state["t"] = t
                    return
                # held f_sat -> tgt (iter_chunks lag law: exact-hour match,
                # NaN scrub, absent row -> 0.0)
                wanted = mts - (mts % 3600) - 3600
                if wanted != q_state["cur_wanted"]:
                    q_state["cur_wanted"] = wanted
                    row = ring.get(wanted)
                    if row is None:
                        if wanted in ring_evicted:
                            ring_depth_violations += 1
                        q_state["cur_tgt"] = ZEROS31
                    else:
                        q_state["cur_tgt"] = [v if v == v else 0.0
                                              for v in row]
                    # diagnostic: computed tgt vs the frozen tgt column
                    ct = q_state["cur_tgt"]
                    ft = tgtf_l[t]
                    dmax = max(abs(ct[k] - ft[k]) for k in range(NSYM))
                    if dmax > tgt_diag["max_abs"]:
                        tgt_diag["max_abs"] = dmax
                    if dmax > 0.0:
                        tgt_diag["n_hours_diff"] += 1
                tgt = q_state["cur_tgt"]
                cr = cr_l[t]
                eurq_sym = [1.0 if CROSS_IX[k] < 0 else cr[CROSS_IX[k]]
                            for k in range(NSYM)]
                eq_c, _eq_w = step(tgt, has_l[t], bo_l[t], ao_l[t],
                                   bc_l[t], ac_l[t], bl_l[t], ah_l[t],
                                   eurq_sym, swl_l[t], sws_l[t])
                b_ts.append(mts)
                b_v.append(eq_c)
                m1_bars += 1
                t += 1
            q_state["t"] = t

    # ------------------------------------------------ H1 master loop (clock 2)
    log("H1+M1 drive: master grid with pending-minute schedule "
        "(feed ts<=prev, then StepH1)")
    in_csv = COMMON / "FMA3_v34_inputs.csv"
    prev_grid_ts = None
    trailing_hazard_minutes = 0
    with open(in_csv) as fh:
        header = fh.readline().rstrip("\n")
        assert header.split(",") == ["timestamp"] + IN_SYMS, "master header"
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            f = line.split(",")
            assert len(f) == 38, f"master row width {len(f)}"
            ts = int(f[0])
            assert ts % 3600 == 0, "H1 stamp not hour-aligned"
            raw = [NAN if c == "" else float(c) for c in f[1:]]
            if prev_grid_ts is not None:
                feed_until(prev_grid_ts)
            step_h1(ts, raw)
            prev_grid_ts = ts
            if h1_bars % 5000 == 0:
                log(f"H1 bar {h1_bars:,}, m1 {m1_bars:,}, hours "
                    f"{stats['hours']:,}, rows {stats['data_rows']:,}")
    # trailing: ALL remaining minutes, then FinalizeH1
    n_before = m1_bars
    feed_until(1 << 62)
    # minutes at/after prev_grid_ts+3600 would want the FINAL ring row
    # (emitted only in finalize) — count the hazard (expected 0)
    for k in range(len(b_ts) - 1, len(b_ts) - 1 - (m1_bars - n_before), -1):
        if k >= 0 and b_ts[k] >= prev_grid_ts + 3600:
            trailing_hazard_minutes += 1
    log(f"H1 done: {h1_bars:,} bars; m1 {m1_bars:,}; trailing minutes past "
        f"last grid hour+1h: {trailing_hazard_minutes}")

    # FinalizeH1: flush the deferred SC row + trailing core-only hours
    o = sc.finalize()
    assert o is not None
    emit_t, emit_row = o
    assert emit_t == prev_ts * 10 ** 9, "FINAL SC emission misaligned"
    stage_step_emit(prev_ts, prev_rows, emit_row)
    while fc_cursor < len(fts):
        emit_hour(fts[fc_cursor], frows[fc_cursor], ZEROS31)
        fc_cursor += 1
    assert fc_cursor == len(fts)
    assert ring_depth_violations == 0, \
        f"{ring_depth_violations} held-ring depth violations (HELD={HELD})"
    log(f"finalize done: hours {stats['hours']:,}, data rows "
        f"{stats['data_rows']:,}, sentinels {stats['sentinels']:,}; "
        f"b_first={b_v[0]!r} b_final={b_v[-1]!r} bal={beng.balance!r} "
        f"trades={beng.n_trades:,}")
    log(f"tgt diagnostic (computed ring vs frozen column): "
        f"max|d|={tgt_diag['max_abs']:.3g} over "
        f"{tgt_diag['n_hours_diff']:,} differing (hour,quarter) probes")

    # ------------------------------------------------ write + judge
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w") as fh:
        fh.write(f"w_v7={W_CORE:.17g},config_hash=51a7541cc2aaa593,"
                 f"fmt=3,prec=17,src=book_orchestrator_sim\n")
        for e, s, v in emit_rows:
            fh.write(f"{e},{s},{v}\n")
    log(f"wrote {OUT_CSV} ({len(emit_rows):,} rows incl. sentinels)")

    actual = [(e, s, v) for e, s, v in emit_rows]
    golden = VJ.parse_stream(GOLDEN)
    rep = VJ.compare(actual, golden, tol=1e-12)
    rep.update(
        r1_gate="book_frac max|diff| <= 1e-12 vs 12dp golden (5e-13 "
                "quantization bound counts as PASS per Track-C precedent)",
        golden_sha256=sha,
        h1_bars=h1_bars, m1_bars=m1_bars,
        hours=stats["hours"], data_rows=stats["data_rows"],
        sentinels=stats["sentinels"],
        core_union_bars=len(a_ts), fcore_rows=len(fts),
        a_first=a_first, core_final_eqc=final_eqc,
        core_final_eqc_bit_equal_pin=bool(final_eqc == FINAL_EQC_TARGET),
        b_first=b_v[0], b_final_eq=b_v[-1],
        b_final_balance=beng.balance, b_trades=beng.n_trades,
        ring_depth_violations=ring_depth_violations,
        trailing_hazard_minutes=trailing_hazard_minutes,
        tgt_diag_max_abs=tgt_diag["max_abs"],
        tgt_diag_n_probes_diff=tgt_diag["n_hours_diff"],
        runtime_s=round(time.time() - T0, 1),
        actual_path=str(OUT_CSV), golden_path=str(GOLDEN))
    OUT_JSON.write_text(json.dumps(rep, indent=1))

    log(f"=== R1 MIRROR RESULT ===")
    log(f"rows {rep['rows_actual']:,} vs golden {rep['rows_golden']:,} | "
        f"structural_ok={rep['structural_ok']} | "
        f"max|diff|={rep['max_abs_diff']:.6g} | >1e-12: {rep['n_over_tol']:,}"
        f" | >5e-13: {rep['n_over_quant_bound']:,}")
    if rep["first_divergence"]:
        log(f"FIRST DIVERGENCE: {rep['first_divergence']}")
    log(f"VERDICT: {'PASS' if rep['pass'] else 'FAIL'}  "
        f"(report -> {OUT_JSON}, {rep['runtime_s']}s)")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
