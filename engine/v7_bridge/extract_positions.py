"""v7.0 band-book POSITION EXTRACTOR — faithful re-run of the NSF5 Python anchor
that additionally captures per-1m-bar, per-instrument LOTS.

WHY THIS EXISTS
---------------
The v7.0 Python anchor (NSF5 mt5/reconcile/gbandrebal/sim.py::run_generic ->
v51_bandharvest._run_window -> engine/backtest.py::run_backtest) reports only
equity curves; per-instrument positions are discarded inside the numba core.
The FMA3 merge campaign needs the book's actual held exposure per minute, so
this module re-runs the EXACT anchor pipeline while capturing positions.

WHY THE CORE IS COPIED INSTEAD OF POST-PROCESSING TRADES
--------------------------------------------------------
run_backtest's trade records are emitted only when lots are CLOSED, with
`entry_i` = the bar where the position first opened and `entry_px` = the
volume-averaged entry. In notional sizing mode the engine ADDS to same-sign
positions whenever desired lots deviate from held lots by more than the 25%
rebalance band; those adds leave no record until (part of) the position is
closed, so the per-bar lots path is NOT losslessly reconstructible from the
trades array alone. The only faithful capture point is the engine loop itself:
`_run_core_pos` below is a verbatim copy of NSF5 engine/backtest.py::_run_core
(same statements, same order, same IEEE float semantics under numba's default
strict-FP njit) with two appended per-bar outputs:

  pos_arr[i]  = signed lots held over bar i (recorded after fills, intrabar
                SL/TP and margin stop-out — i.e. the position whose marks
                define eq_c[i]/eq_w[i]),
  cash_arr[i] = balance - entry * pos * contract * eurq[i]  (the cash/basis
                term such that eq_c[i] == cash_arr[i] + pos*contract*mark*eurq,
                mark = bid_c for longs / ask_c for shorts).

Everything else — feed priming, sleeve construction, masking, probe loop,
trigger logic, seed chaining, the 'no splice flattery' exact segment re-runs —
is either imported from NSF5 (READ-ONLY) or mirrored line-for-line.

IMPORT-ORDER LANDMINE (replicated deliberately)
-----------------------------------------------
`import sim` (gbandrebal) transitively imports lock_v5, whose import
side-effect sets config.settings.ACCOUNT['stop_out_level'] = 1e-9 (the 'noliq'
convention every v7 anchor number was computed under). This module imports sim
BEFORE any backtest runs and asserts the side-effect took hold.

NSF5's `config` and `engine` top-level package names collide with FMA3's
directories of the same names, so FMA3's canonical config/paths.py is loaded
by file location (importlib) and the FMA3 root is intentionally NOT put on
sys.path.

VERIFICATION GATE (non-negotiable)
----------------------------------
1. Core-copy self-test: every leg of the book is run once over the full
   [LO,HI) window through BOTH NSF5's run_backtest and run_backtest_pos; the
   equity / worst / margin / trades arrays must be BIT-IDENTICAL.
2. Anchor reproduction: sim.pack() on the captured run must equal every float
   of research/baselines/nsf5/engine_reproduce.json results.harvest_band_sym
   EXACTLY (== on floats), incl. 31 band + 0 harvest triggers.
3. Internal consistency: book equity is rebuilt from the captured positions
   (per leg: cash + lots*contract*side_close_px*eurq; legs ffilled onto the
   union index exactly as engine/portfolio.combine_curves does, plus the flat
   legcap) and must match the captured eqc curve to < 1e-6 relative.

ARTIFACTS (research/outputs/, all timestamps tz-naive broker SERVER time)
-------------------------------------------------------------------------
v7_book_lots_1m.parquet
    Index = the committed band-book union 1m bar grid over [2020-01-01,
    2026-01-01) (every bar where at least one book instrument traded).
    Columns = instruments; values = NET signed lots held over that bar,
    summed across sleeves/legs (USDJPY appears in both S5_JPY and S6_OPEXUSD).
    Lots are forward-filled across an instrument's bar-less stretches
    (positions persist), including re-split seams: at a seam t the model
    closes and reopens at the instrument's first bar >= t, so between t and
    that bar the previous segment's lots are carried.
v7_book_equity_1m.parquet
    Columns eqc / eqw / margin on the same index: combined close-mark equity,
    worst-mark equity, and summed used margin (EUR), exactly the anchor's
    curves.
v7_book_frac_1h.parquet
    Hourly fraction-of-book-equity matrix in the FMA2 position convention
    (signed notional / joint equity). SAMPLING CONVENTION: the row stamped at
    hour start h is the snapshot at the LAST 1m bar with timestamp in
    [h, h+1) — frac[inst] = lots * contract_size * mid_close * eurq / eqc,
    all four factors taken from that same bar (per-instrument mid/eurq
    forward-filled onto the union grid first). Hours with no union bar are
    dropped; instruments before their first bar contribute 0. NOTE: this is a
    HELD-exposure snapshot, not a decision signal — an FMA2-style engine that
    lags row h into hour h+1 will execute ~1 bar later than the anchor did.

Usage:  python3 engine/v7_bridge/run_extract.py       (IC anchor; ~10-25 min)
        python3 engine/v7_bridge/run_extract_fwd.py   (FORWARD duka+2026H1
            feed, USA500 proxying USTEC, [2020-01-01, 2026-05-01); artifacts
            to research/outputs/fwd/ with '_fwd' suffix, index = tz-naive
            TRUE UTC, 2026 numbers saved BLIND — see run_extract_fwd.py)
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

warnings.filterwarnings("ignore")

# --- FMA3 canonical paths, loaded by FILE (never via sys.path: FMA3's
# `config`/`engine` dirs shadow NSF5's packages of the same name) -------------
_HERE = Path(__file__).resolve()
FMA3 = _HERE.parents[2]
_spec = importlib.util.spec_from_file_location("fma3_paths",
                                               FMA3 / "config" / "paths.py")
paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paths)

# --- NSF5 (READ-ONLY) imports. ORDER MATTERS: `import sim` applies lock_v5's
# stop_out=1e-9 side-effect before anything can run a backtest. ---------------
for _p in (paths.NSF5,
           paths.NSF5 / "mt5" / "reconcile",
           paths.NSF5 / "mt5" / "reconcile" / "gbandrebal"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sim  # noqa: E402  (side-effect: ACCOUNT['stop_out_level'] = 1e-9)
import engine.backtest as bt  # noqa: E402
import v51_rig  # noqa: E402  (already imported by sim; provides prime_2026)
from config import settings as S  # noqa: E402
from engine.cpcv_portfolio import _mask_from_windows  # noqa: E402
from engine.portfolio import combine_curves  # noqa: E402
from sim import (HI, INIT, LO, W7, bd_metrics, book,  # noqa: E402
                 earliest_trigger, pack, prime_feed, slot_frame)

assert S.ACCOUNT["stop_out_level"] == 1e-9, \
    "lock_v5 stop_out side-effect missing — anchor numbers need noliq (1e-9)"

REFERENCE_JSON = paths.BASELINES / "nsf5" / "engine_reproduce.json"
REFERENCE_KEY = "harvest_band_sym"
OUT_DIR = paths.OUTPUTS


def prime(feed: str) -> None:
    """Prime NSF5's module-level bar/FX caches for one of the known feeds.

    'ic'       — IC Markets native 1m bars (broker SERVER time), the verified
                 anchor feed (multifeed_optim.prime_feed('ic') verbatim).
    'duka'     — Dukascopy 2020-2025 1m bars (tz-naive TRUE UTC).
    'duka2026' — the NSF5 v51_rig FORWARD feed: Duka 2020-2025 with the 2026H1
                 holdout appended per instrument (v51_rig.prime_2026 verbatim;
                 index stays tz-naive TRUE UTC; FxConverter picks up holdout
                 rates by construction — see NSF5 engine/costs.FxConverter._mid).
    """
    if feed in ("ic", "duka"):
        prime_feed(feed)
    elif feed == "duka2026":
        v51_rig.prime_2026()
    else:
        raise ValueError(f"unknown feed {feed!r} (expected ic|duka|duka2026)")


# =============================================================================
# 1. Numba core — VERBATIM copy of NSF5 engine/backtest.py::_run_core with
#    per-bar position + cash-basis capture appended. Any edit here other than
#    the pos/cash lines breaks bit-exactness against the anchor.
# =============================================================================
@njit(cache=True)
def _run_core_pos(bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c,
                  eurq, swap_flag, swap_long, swap_short,
                  target, sl_dist, tp_dist,
                  contract, comm_side, leverage, lot_step, min_lot,
                  initial, stop_out_level, sizing_mode, margin_cap,
                  rebalance_band, dd_k, dd_floor, throttle_thr, throttle_f):
    n = bid_o.shape[0]
    balance = initial
    pos = 0.0
    entry = 0.0
    sl = np.nan
    tp = np.nan
    blocked = np.nan  # target value at forced exit; re-entry blocked until change
    entry_i = -1
    eq_peak = initial
    dd_scale = 1.0  # drawdown-responsive sizing overlay (causal: uses prior bar)
    thr_scale = 1.0  # soft loss-throttle multiplier (causal: uses prior bar equity)
    entry_comm = 0.0  # entry-side commission carried into trade records

    eq_c = np.empty(n)
    eq_w = np.empty(n)
    margin_arr = np.zeros(n)  # used margin (EUR) at bar close
    trades = np.empty((500_000, 7))
    n_tr = 0
    dead = False
    # --- extraction additions (no effect on engine arithmetic) ---
    pos_arr = np.zeros(n)   # signed lots held over bar i
    cash_arr = np.zeros(n)  # balance - entry*pos*contract*eurq[i]

    for i in range(n):
        mid_o = 0.5 * (bid_o[i] + ask_o[i])

        # ---- 1. swap at rollover ----
        if swap_flag[i] > 0 and pos != 0.0:
            frac = swap_long[i] if pos > 0 else swap_short[i]
            notional = np.abs(pos) * contract * mid_o
            balance += notional * frac / 365.0 * swap_flag[i] * eurq[i]

        # ---- 2. signal execution at open ----
        tgt = target[i]
        if not np.isnan(blocked):
            if tgt == blocked:
                tgt = pos if sizing_mode == 0 else (0.0 if pos == 0.0 else tgt)
            else:
                blocked = np.nan
        if sizing_mode == 0:
            want_change = tgt != pos
            desired = tgt
        elif sizing_mode == 1:
            # risk mode: act only on sign changes
            sgn_t = 0.0 if tgt == 0.0 else (1.0 if tgt > 0 else -1.0)
            sgn_p = 0.0 if pos == 0.0 else (1.0 if pos > 0 else -1.0)
            want_change = sgn_t != sgn_p
            desired = 0.0
            if want_change and sgn_t != 0.0:
                sd = sl_dist[i]
                if sd > 0.0 and not np.isnan(sd):
                    risk_eur = balance * np.abs(tgt) * dd_scale * thr_scale
                    lots = risk_eur / (sd * contract * eurq[i])
                    px = ask_o[i] if sgn_t > 0 else bid_o[i]
                    max_lots = (balance * leverage * margin_cap) / (
                        px * contract * eurq[i])
                    if lots > max_lots:
                        lots = max_lots
                    lots = _round_lots(lots, lot_step, min_lot)
                    desired = sgn_t * lots
                # sd invalid -> desired stays 0 (close only)
        else:
            # notional mode: target = notional multiple of balance
            sgn_t = 0.0 if tgt == 0.0 else (1.0 if tgt > 0 else -1.0)
            sgn_p = 0.0 if pos == 0.0 else (1.0 if pos > 0 else -1.0)
            desired = 0.0
            if sgn_t == 0.0:
                want_change = pos != 0.0
            else:
                px = ask_o[i] if sgn_t > 0 else bid_o[i]
                unit_eur = px * contract * eurq[i]
                lots = balance * np.abs(tgt) * dd_scale * thr_scale / unit_eur
                max_lots = (balance * leverage * margin_cap) / unit_eur
                if lots > max_lots:
                    lots = max_lots
                lots = _round_lots(lots, lot_step, min_lot)
                if sgn_t != sgn_p:
                    want_change = True
                    desired = sgn_t * lots
                elif pos != 0.0 and np.abs(lots - np.abs(pos)) \
                        / np.abs(pos) > rebalance_band:
                    want_change = True
                    desired = sgn_t * lots
                else:
                    want_change = False

        if want_change and not dead:
            delta = desired - pos
            if delta != 0.0:
                # close/reduce part
                if pos != 0.0 and (desired == 0.0 or desired * pos < 0.0
                                   or np.abs(desired) < np.abs(pos)):
                    close_lots = pos if desired * pos <= 0.0 else pos - desired
                    px = bid_o[i] if pos > 0 else ask_o[i]
                    pnl = (px - entry) * close_lots * contract * eurq[i]
                    ec_share = entry_comm * np.abs(close_lots / pos)
                    entry_comm -= ec_share
                    balance += pnl - comm_side * np.abs(close_lots)
                    if n_tr < 500_000:
                        trades[n_tr, 0] = entry_i
                        trades[n_tr, 1] = i
                        trades[n_tr, 2] = close_lots
                        trades[n_tr, 3] = entry
                        trades[n_tr, 4] = px
                        trades[n_tr, 5] = (pnl - comm_side * np.abs(close_lots)
                                           - ec_share)
                        trades[n_tr, 6] = 0.0
                        n_tr += 1
                    pos -= close_lots
                    if pos == 0.0:
                        sl = np.nan
                        tp = np.nan
                # open/add part
                if desired != 0.0 and np.abs(desired) > np.abs(pos):
                    add = desired - pos
                    px = ask_o[i] if add > 0 else bid_o[i]
                    if pos == 0.0:
                        entry = px
                        entry_i = i
                        sd = sl_dist[i]
                        td = tp_dist[i]
                        sgn = 1.0 if add > 0 else -1.0
                        sl = px - sgn * sd if (not np.isnan(sd)) and sd > 0 else np.nan
                        tp = px + sgn * td if (not np.isnan(td)) and td > 0 else np.nan
                    else:
                        entry = (entry * pos + px * add) / (pos + add)
                    balance -= comm_side * np.abs(add)
                    if pos == 0.0:
                        entry_comm = comm_side * np.abs(add)
                    else:
                        entry_comm += comm_side * np.abs(add)
                    pos = desired

        # ---- 3. intrabar SL/TP ----
        if pos != 0.0:
            exit_px = np.nan
            reason = -1.0
            if pos > 0.0:
                if (not np.isnan(sl)) and bid_l[i] <= sl:
                    exit_px = bid_o[i] if bid_o[i] <= sl else sl
                    reason = 1.0
                elif (not np.isnan(tp)) and bid_h[i] >= tp:
                    exit_px = bid_o[i] if bid_o[i] >= tp else tp
                    reason = 2.0
            else:
                if (not np.isnan(sl)) and ask_h[i] >= sl:
                    exit_px = ask_o[i] if ask_o[i] >= sl else sl
                    reason = 1.0
                elif (not np.isnan(tp)) and ask_l[i] <= tp:
                    exit_px = ask_o[i] if ask_o[i] <= tp else tp
                    reason = 2.0
            if not np.isnan(exit_px):
                pnl = (exit_px - entry) * pos * contract * eurq[i]
                balance += pnl - comm_side * np.abs(pos)
                if n_tr < 500_000:
                    trades[n_tr, 0] = entry_i
                    trades[n_tr, 1] = i
                    trades[n_tr, 2] = pos
                    trades[n_tr, 3] = entry
                    trades[n_tr, 4] = exit_px
                    trades[n_tr, 5] = (pnl - comm_side * np.abs(pos)
                                       - entry_comm)
                    trades[n_tr, 6] = reason
                    n_tr += 1
                entry_comm = 0.0
                pos = 0.0
                sl = np.nan
                tp = np.nan
                blocked = target[i]

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
        eq_c[i] = balance + unreal_c
        eq_w[i] = balance + unreal_w

        # ---- 5. margin stop-out ----
        if pos != 0.0:
            mid_c = 0.5 * (bid_c[i] + ask_c[i])
            margin = np.abs(pos) * contract * mid_c * eurq[i] / leverage
            margin_arr[i] = margin
            if eq_w[i] < stop_out_level * margin:
                px = bid_l[i] if pos > 0 else ask_h[i]
                pnl = (px - entry) * pos * contract * eurq[i]
                balance += pnl - comm_side * np.abs(pos)
                if n_tr < 500_000:
                    trades[n_tr, 0] = entry_i
                    trades[n_tr, 1] = i
                    trades[n_tr, 2] = pos
                    trades[n_tr, 3] = entry
                    trades[n_tr, 4] = px
                    trades[n_tr, 5] = (pnl - comm_side * np.abs(pos)
                                       - entry_comm)
                    trades[n_tr, 6] = 3.0
                    n_tr += 1
                entry_comm = 0.0
                pos = 0.0
                sl = np.nan
                tp = np.nan
                blocked = target[i]
                eq_c[i] = balance
                eq_w[i] = balance
                margin_arr[i] = 0.0

        # ---- extraction capture: the position whose marks defined eq_c[i] ---
        pos_arr[i] = pos
        cash_arr[i] = balance - entry * pos * contract * eurq[i]

        # ---- 5b. update drawdown-responsive scale for NEXT bar ----
        if eq_c[i] > eq_peak:
            eq_peak = eq_c[i]
        if dd_k > 0.0 and eq_peak > 0.0:
            dd_now = 1.0 - eq_c[i] / eq_peak
            s = 1.0 - dd_k * dd_now
            dd_scale = dd_floor if s < dd_floor else s
        # soft loss-throttle: once quarter loss vs INITIAL exceeds threshold,
        # de-gross to throttle_f for the rest of the run (sticky within quarter;
        # re-risks next quarter since each quarter is a fresh run_backtest call).
        if throttle_thr > 0.0 and eq_c[i] <= (1.0 - throttle_thr) * initial:
            thr_scale = throttle_f
        # ---- 6. negative balance protection / death ----
        if pos == 0.0 and balance <= 0.0:
            balance = 0.0
            for j in range(i, n):
                eq_c[j] = 0.0
                eq_w[j] = 0.0
                pos_arr[j] = 0.0
                cash_arr[j] = 0.0
            dead = True
            break

    return eq_c, eq_w, balance, trades[:n_tr], dead, margin_arr, pos_arr, cash_arr


@njit(cache=True)
def _round_lots(lots: float, step: float, min_lot: float) -> float:
    """Verbatim copy of NSF5 engine/backtest.py::_round_lots."""
    n = np.floor(lots / step + 1e-9)
    out = n * step
    if out < min_lot:
        return 0.0
    return out


# =============================================================================
# 2. Python wrapper — mirrors NSF5 run_backtest but returns pos/cash series.
#    Reuses NSF5's prep_arrays (so multifeed_optim.prime_feed's IC hot-swap
#    and cost model apply identically) and S.ACCOUNT (lock_v5 stop_out).
# =============================================================================
def run_backtest_pos(inst: str, target: np.ndarray, *,
                     sl_dist: np.ndarray | None = None,
                     tp_dist: np.ndarray | None = None,
                     sizing: str = "lots",
                     initial: float | None = None,
                     margin_cap: float = 0.9,
                     rebalance_band: float = 0.25,
                     dd_k: float = 0.0,
                     dd_floor: float = 0.25,
                     throttle_thr: float = 0.0,
                     throttle_f: float = 1.0,
                     holdout: bool = False,
                     mask: np.ndarray | None = None) -> dict:
    """One instrument backtest with per-bar position capture.

    Mirrors NSF5 engine/backtest.py::run_backtest argument-for-argument (same
    prep, same mask semantics, same core arithmetic) and returns a dict with
    pandas Series: equity, equity_worst, margin, pos (signed lots held over
    each bar), cash (equity minus lots*contract*side_close_px*eurq), plus the
    trades DataFrame and dead flag.
    """
    bars, eurq, swap_flag, swap_long, swap_short = bt.prep_arrays(inst, holdout)
    n = len(bars)
    assert len(target) == n, f"target len {len(target)} != bars {n}"
    cfg = S.INSTRUMENTS[inst]
    initial = S.ACCOUNT["initial"] if initial is None else initial

    tgt = np.asarray(target, dtype=np.float64)
    if mask is not None:
        tgt = np.where(mask, tgt, 0.0)
    nan_arr = np.full(n, np.nan)
    sl = nan_arr if sl_dist is None else np.asarray(sl_dist, dtype=np.float64)
    tp = nan_arr if tp_dist is None else np.asarray(tp_dist, dtype=np.float64)

    eq_c, eq_w, balance, tr, dead, margin_arr, pos_arr, cash_arr = _run_core_pos(
        bars["bid_o"].to_numpy(), bars["bid_h"].to_numpy(),
        bars["bid_l"].to_numpy(), bars["bid_c"].to_numpy(),
        bars["ask_o"].to_numpy(), bars["ask_h"].to_numpy(),
        bars["ask_l"].to_numpy(), bars["ask_c"].to_numpy(),
        eurq, swap_flag, swap_long, swap_short,
        tgt, sl, tp,
        float(cfg["contract_size"]), float(cfg["commission_side"]),
        float(cfg["leverage"]), float(cfg["lot_step"]), float(cfg["min_lot"]),
        float(initial), float(S.ACCOUNT["stop_out_level"]),
        {"lots": 0, "risk": 1, "notional": 2}[sizing], float(margin_cap),
        float(rebalance_band), float(dd_k), float(dd_floor),
        float(throttle_thr), float(throttle_f),
    )
    idx = bars.index
    return dict(
        inst=inst,
        equity=pd.Series(eq_c, index=idx, name="equity"),
        equity_worst=pd.Series(eq_w, index=idx, name="equity_worst"),
        margin=pd.Series(margin_arr, index=idx, name="margin_used"),
        pos=pd.Series(pos_arr, index=idx, name="lots"),
        cash=pd.Series(cash_arr, index=idx, name="cash"),
        trades=pd.DataFrame(tr, columns=bt.TRADE_COLS),
        dead=dead,
    )


# =============================================================================
# 3. Window runner — mirrors v51_bandharvest._run_window line-for-line
#    (identical curve ordering => identical FP summation in combine_curves),
#    additionally returning the per-leg captured pos/cash series and the flat
#    legcap so book equity can be rebuilt from positions.
# =============================================================================
def _run_window_pos(sleeves: dict, lo: pd.Timestamp, hi: pd.Timestamp,
                    seed: float):
    """One equal-slot window [lo,hi) at book seed `seed`.

    Returns (tc, tw, tm, slot, legs_cap, flat): combined close/worst/margin
    curves and per-sleeve daily slot equity exactly as NSF5's _run_window,
    plus legs_cap = [{sleeve, inst, pos, cash, eqc}] (Series sliced to the
    window) and the summed flat legcap of legs with no bars in the window.
    """
    W = 1.0 / len(sleeves)
    cc, cw, cm = [], [], []
    flat = 0.0
    slot: dict = {}
    legs_cap: list[dict] = []
    for name, legs in sleeves.items():
        legcap = seed * W / len(legs)
        scurves, sflat = [], 0.0
        for inst, tgt in legs:
            bars = bt.load_bars(inst)
            mask = _mask_from_windows(bars.index, [(lo, hi)])
            res = run_backtest_pos(inst, tgt, sizing="notional",
                                   initial=legcap, mask=mask)
            sel = (res["equity"].index >= lo) & (res["equity"].index < hi)
            if not sel.any():
                flat += legcap
                sflat += legcap
                continue
            cc.append(res["equity"][sel])
            cw.append(res["equity_worst"][sel])
            cm.append(res["margin"][sel])
            scurves.append(res["equity"][sel])
            legs_cap.append(dict(sleeve=name, inst=inst,
                                 pos=res["pos"][sel],
                                 cash=res["cash"][sel],
                                 eqc=res["equity"][sel]))
        if scurves:
            sc, _ = combine_curves(scurves, scurves)
            slot[name] = sc.resample("D").last().dropna() + sflat
        else:
            slot[name] = None
    tc, tw = combine_curves(cc, cw)
    tc, tw = tc + flat, tw + flat
    idx = tc.index
    tm = sum(m.reindex(idx).ffill().fillna(0.0) for m in cm)
    return tc, tw, tm, slot, legs_cap, flat


# =============================================================================
# 4. Generic band/harvest runner — mirrors gbandrebal/sim.py::run_generic
#    (same probe loop 6/18/999 months, same triggers via sim.earliest_trigger,
#    same seed chaining, same exact re-run of every committed segment), with a
#    per-committed-segment `sink` callback receiving the captured legs.
# =============================================================================
def run_generic_capture(sleeves: dict, edges: list, up=None, down=None,
                        kmult=np.inf, min_gap_days: int = 5, label: str = "",
                        verbose: bool = True, sink=None,
                        print_before: pd.Timestamp | None = None):
    """Triggered equal-capital re-split over `edges` with band and/or harvest
    triggers; every committed segment is re-run EXACTLY (no splice flattery)
    and handed to `sink(t0, t1, tc_seg, legs_cap, flat)` for position capture.
    Returns (out, triggers) identical in content to sim.run_generic.

    `print_before` (holdout discipline): when set, per-trigger console lines
    (which contain book-equity levels and slot shares) are suppressed for
    triggers acting at or after that timestamp. Numbers are unaffected."""
    W = 1.0 / len(sleeves)
    seed = INIT
    pc, pw, pm = [], [], []
    triggers = []
    guard = 0
    for j in range(len(edges) - 1):
        lo, hi = edges[j], edges[j + 1]
        cur = lo
        while cur < hi and guard < 3000:
            hit = None
            for probe_m in (6, 18, 999):
                probe_hi = min(hi, cur + pd.DateOffset(months=probe_m))
                tc, tw, tm, slot, legs_cap, flat = _run_window_pos(
                    sleeves, cur, probe_hi, seed)
                sf = slot_frame(slot, seed, cur)
                hit = earliest_trigger(sf, slot, up, down, kmult, seed, W,
                                       cur, probe_hi, min_gap_days)
                if hit is not None or probe_hi >= hi:
                    break
            if hit is None:                                    # no trigger before hi
                sel = tc.index < hi
                pc.append(tc[sel]); pw.append(tw[sel]); pm.append(tm[sel])
                if sink is not None:
                    sink(cur, hi, tc[sel], legs_cap, flat)
                seed = float(tc[sel].iloc[-1])
                cur = hi
            else:
                t, info = hit
                tc2, tw2, tm2, _s2, legs_cap2, flat2 = _run_window_pos(
                    sleeves, cur, t, seed)                     # exact re-run
                sel = tc2.index < t
                pc.append(tc2[sel]); pw.append(tw2[sel]); pm.append(tm2[sel])
                if sink is not None:
                    sink(cur, t, tc2[sel], legs_cap2, flat2)
                newseed = float(tc2[sel].iloc[-1])
                info = dict(info); info.update(act=str(t.date()), book=newseed)
                triggers.append(info)
                if verbose and (print_before is None or t < print_before):
                    tag = info["kind"]
                    extra = (f"max {info['max_share']:.3f} ({info['max_sleeve']}) "
                             f"min {info['min_share']:.3f} ({info['min_sleeve']})"
                             if tag == "band" else
                             f"slot {info['slot']:>10,.0f} > {info['thr']:>10,.0f} "
                             f"({info['sleeve']})")
                    print(f"      [{label}] trig {len(triggers):>3} {tag:7} act {t.date()} "
                          f"{extra}  book -> {newseed:>12,.0f}", flush=True)
                seed = newseed
                cur = t
                guard += 1
    if guard >= 3000:
        raise RuntimeError(f"guard exhausted ({label})")
    eqc, eqw, mg = pd.concat(pc), pd.concat(pw), pd.concat(pm)
    d = eqc.resample("D").last().dropna()
    return dict(eqc=eqc, eqw=eqw, mg=mg, daily=d), triggers


# =============================================================================
# 5. Per-segment position sink: verifies the cash+marks decomposition per leg,
#    rebuilds book equity combine_curves-style, accumulates per-instrument lots.
# =============================================================================
class PositionAccumulator:
    """Collects committed-segment positions and runs the internal-consistency
    rebuild as segments stream in (bounded memory: per-leg cash/eq series are
    dropped once the segment is verified)."""

    def __init__(self) -> None:
        self.lots: dict[str, list[pd.Series]] = {}
        self.rebuilt: list[pd.Series] = []
        self.max_leg_relerr = 0.0
        self.max_book_relerr = 0.0
        self.n_segments = 0
        self.segments: list[dict] = []
        self._eurq: dict[str, pd.Series] = {}

    def _eurq_series(self, inst: str) -> pd.Series:
        if inst not in self._eurq:
            bars, eurq, *_ = bt.prep_arrays(inst)
            self._eurq[inst] = pd.Series(eurq, index=bars.index)
        return self._eurq[inst]

    def __call__(self, t0: pd.Timestamp, t1: pd.Timestamp, tc_seg: pd.Series,
                 legs_cap: list[dict], flat: float) -> None:
        rebuilt_legs: list[pd.Series] = []
        per_inst: dict[str, pd.Series] = {}
        for lc in legs_cap:
            inst = lc["inst"]
            m = lc["pos"].index < t1          # probe windows already end < t1;
            pos = lc["pos"][m]                # slice defensively anyway
            cash = lc["cash"][m]
            eqc_leg = lc["eqc"][m]
            if len(pos) == 0:
                continue
            bars = bt.load_bars(inst)
            sub = bars.loc[pos.index]
            e = self._eurq_series(inst).loc[pos.index]
            pv = pos.to_numpy()
            side_px = np.where(pv > 0, sub["bid_c"].to_numpy(),
                               np.where(pv < 0, sub["ask_c"].to_numpy(), 0.0))
            c_size = float(S.INSTRUMENTS[inst]["contract_size"])
            val = cash.to_numpy() + pv * c_size * side_px * e.to_numpy()
            err = np.abs(val - eqc_leg.to_numpy()) / np.maximum(
                np.abs(eqc_leg.to_numpy()), 1e-12)
            self.max_leg_relerr = max(self.max_leg_relerr, float(err.max()))
            rebuilt_legs.append(pd.Series(val, index=pos.index))
            per_inst[inst] = pos if inst not in per_inst else per_inst[inst] + pos
        # book rebuild, mirroring combine_curves' close-mark path exactly
        idx = rebuilt_legs[0].index
        for r in rebuilt_legs[1:]:
            idx = idx.union(r.index)
        tot = None
        for r in rebuilt_legs:
            rf = r.reindex(idx).ffill().fillna(r.iloc[0])
            tot = rf if tot is None else tot + rf
        tot = (tot + flat).reindex(tc_seg.index)
        book_err = float(((tot - tc_seg).abs() / tc_seg.abs()).max())
        self.max_book_relerr = max(self.max_book_relerr, book_err)
        self.rebuilt.append(tot)
        for inst, s in per_inst.items():
            self.lots.setdefault(inst, []).append(s)
        self.n_segments += 1
        self.segments.append(dict(t0=str(t0), t1=str(t1),
                                  n_legs=len(rebuilt_legs),
                                  book_relerr=book_err))

    # -- post-run assembly ----------------------------------------------------
    def lots_matrix(self, union_idx: pd.DatetimeIndex) -> pd.DataFrame:
        """Net signed lots per instrument on the committed union 1m grid.
        Forward-filled across an instrument's bar-less stretches; 0 before its
        first position-bearing bar."""
        cols = {}
        for inst in sorted(self.lots):
            s = pd.concat(self.lots[inst])
            assert s.index.is_monotonic_increasing and s.index.is_unique, inst
            cols[inst] = s.reindex(union_idx).ffill().fillna(0.0)
        return pd.DataFrame(cols, index=union_idx)


# =============================================================================
# 6. Self-test, reference gate, artifact assembly
# =============================================================================
def self_test_core(sleeves: dict, lo: pd.Timestamp = LO,
                   hi: pd.Timestamp = HI) -> dict:
    """Run every leg once over the full [lo,hi) window through BOTH NSF5's
    engine and the position-capturing copy; demand BIT-IDENTICAL outputs.
    Fails fast before the expensive band run if the copied core drifted."""
    report = {}
    for name, legs in sleeves.items():
        legcap = INIT * (1.0 / len(sleeves)) / len(legs)
        for inst, tgt in legs:
            bars = bt.load_bars(inst)
            mask = _mask_from_windows(bars.index, [(lo, hi)])
            ref = bt.run_backtest(inst, tgt, sizing="notional",
                                  initial=legcap, mask=mask)
            mine = run_backtest_pos(inst, tgt, sizing="notional",
                                    initial=legcap, mask=mask)
            ok = (np.array_equal(ref.equity.to_numpy(), mine["equity"].to_numpy())
                  and np.array_equal(ref.equity_worst.to_numpy(),
                                     mine["equity_worst"].to_numpy())
                  and np.array_equal(ref.margin.to_numpy(),
                                     mine["margin"].to_numpy())
                  and np.array_equal(ref.trades[bt.TRADE_COLS].to_numpy(),
                                     mine["trades"][bt.TRADE_COLS].to_numpy()))
            report[f"{name}/{inst}"] = bool(ok)
            if not ok:
                raise AssertionError(
                    f"core self-test FAILED for {name}/{inst}: the copied "
                    f"_run_core_pos is not bit-identical to NSF5 _run_core")
    return report


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def extract(write_artifacts: bool = True, run_self_test: bool = True,
            verbose: bool = True, *,
            feed: str = "ic",
            us5: str = "USTEC",
            lo: pd.Timestamp = LO,
            hi: pd.Timestamp = HI,
            anchor_gate: bool = True,
            out_dir: Path = OUT_DIR,
            artifact_suffix: str = "",
            blind_from: pd.Timestamp | None = None,
            dev_metrics_hi: pd.Timestamp | None = None) -> dict:
    """Full extraction pipeline. Returns the verification report dict (also
    written to `out_dir`/v7_extract{artifact_suffix}_verification.json).

    DEFAULTS REPRODUCE THE VERIFIED IC ANCHOR PATH EXACTLY: prime_feed('ic'),
    book('BTC_REP','USTEC'), [sim.LO, sim.HI) window, anchor gate against
    research/baselines/nsf5/engine_reproduce.json, artifacts to
    research/outputs/ under the original names.

    Forward-feed parameters (driven by run_extract_fwd.py):
      feed='duka2026'   v51_rig.prime_2026() — Duka 2020-25 + 2026H1 holdout,
                        tz-naive TRUE UTC index (NOT server time).
      us5='USA500'      the rig's documented USTEC proxy (no Duka USTEC).
      lo/hi             the extraction window, e.g. [2020-01-01, 2026-05-01).
      anchor_gate=False no reference exists off the IC feed; the bit-exact
                        core self-test and the <1e-6 position->equity rebuild
                        gate still run.
      artifact_suffix   e.g. '_fwd' -> v7_book_lots_1m_fwd.parquet etc.
      blind_from        HOLDOUT DISCIPLINE: suppress trigger console lines and
                        redact trigger equity/share floats in the report for
                        triggers acting at/after this stamp (artifacts still
                        contain full data — saved blind, never printed).
      dev_metrics_hi    if set, report sim.bd_metrics over [lo, dev_metrics_hi)
                        (feed-quality context on the development window only).
    """
    t_start = time.time()
    reference = (json.loads(REFERENCE_JSON.read_text())["results"][REFERENCE_KEY]
                 if anchor_gate else None)

    print(f"[1/6] prime feed {feed!r} + build book('BTC_REP', {us5!r})",
          flush=True)
    prime(feed)
    sleeves = book("BTC_REP", us5)
    print(f"      sleeves: {list(sleeves)}", flush=True)

    st_report = {}
    if run_self_test:
        print("[2/6] core-copy self-test (bit-exact vs NSF5 _run_core, all legs)",
              flush=True)
        st_report = self_test_core(sleeves, lo, hi)
        print(f"      {len(st_report)} legs bit-identical: "
              f"{all(st_report.values())}", flush=True)

    print("[3/6] band-book run with position capture "
          "(up=0.25, down=W7/1.75, kmult=2.5)", flush=True)
    acc = PositionAccumulator()
    out, triggers = run_generic_capture(
        sleeves, [lo, hi], up=0.25, down=W7 / 1.75, kmult=2.5,
        label="extract", verbose=verbose, sink=acc, print_before=blind_from)

    if anchor_gate:
        print("[4/6] anchor reconciliation gate", flush=True)
        m = pack(out, triggers)
        rep_flat, ref_flat = _flatten(m), _flatten(reference)
        deltas = {k: (rep_flat.get(k), ref_flat[k],
                      None if rep_flat.get(k) is None
                      else rep_flat[k] - ref_flat[k])
                  for k in ref_flat}
        exact = all(rep_flat.get(k) == v for k, v in ref_flat.items())
        for k, (mine_v, ref_v, d) in deltas.items():
            tag = "OK " if mine_v == ref_v else "FAIL"
            print(f"      {tag} {k:22} mine={mine_v!r} ref={ref_v!r} delta={d!r}",
                  flush=True)
    else:
        print("[4/6] anchor gate SKIPPED (no reference exists for this feed)",
              flush=True)
        deltas, exact = {}, None

    dev_metrics = None
    if dev_metrics_hi is not None:
        dev_metrics = bd_metrics(out, lo, dev_metrics_hi)
        print(f"      dev window [{lo.date()} .. {dev_metrics_hi.date()}): "
              f"CAGR_bd {dev_metrics['cagr_bd']:.4f}  "
              f"MDD_bd {dev_metrics['mdd_bd']:.4f}  "
              f"Sharpe_bd {dev_metrics['sharpe_bd']:.3f}  "
              f"final {dev_metrics['final_eq']:,.0f}  "
              f"({dev_metrics['n_bdays']} bdays)", flush=True)

    print("[5/6] internal consistency (positions -> book equity rebuild)",
          flush=True)
    book_rebuilt = pd.concat(acc.rebuilt)
    assert book_rebuilt.index.equals(out["eqc"].index)
    final_relerr = float(((book_rebuilt - out["eqc"]).abs()
                          / out["eqc"].abs()).max())
    consistency_ok = (final_relerr < 1e-6 and acc.max_leg_relerr < 1e-6
                      and acc.max_book_relerr < 1e-6)
    print(f"      max per-leg relerr {acc.max_leg_relerr:.3e} | "
          f"max book relerr {acc.max_book_relerr:.3e} | "
          f"concat relerr {final_relerr:.3e} | "
          f"segments {acc.n_segments}", flush=True)

    artifacts = []
    if write_artifacts:
        print("[6/6] writing artifacts", flush=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        idx = out["eqc"].index
        lots_df = acc.lots_matrix(idx)
        eq_df = pd.DataFrame({"eqc": out["eqc"], "eqw": out["eqw"],
                              "margin": out["mg"]}, index=idx)
        # hourly fraction-of-book matrix (FMA2 convention; see module docstring)
        val_1m = pd.DataFrame(index=idx)
        for inst in lots_df.columns:
            bars = bt.load_bars(inst)
            mid = ((bars["bid_c"] + bars["ask_c"]) * 0.5).reindex(idx).ffill()
            e = acc._eurq_series(inst).reindex(idx).ffill()
            c_size = float(S.INSTRUMENTS[inst]["contract_size"])
            val_1m[inst] = lots_df[inst] * c_size * mid * e
        eq_h = out["eqc"].resample("1h").last().dropna()
        frac_h = (val_1m.resample("1h").last().reindex(eq_h.index)
                  .div(eq_h, axis=0).fillna(0.0))

        p_lots = out_dir / f"v7_book_lots_1m{artifact_suffix}.parquet"
        p_eq = out_dir / f"v7_book_equity_1m{artifact_suffix}.parquet"
        p_frac = out_dir / f"v7_book_frac_1h{artifact_suffix}.parquet"
        lots_df.to_parquet(p_lots)
        eq_df.to_parquet(p_eq)
        frac_h.to_parquet(p_frac)
        artifacts = [str(p_lots), str(p_eq), str(p_frac)]
        for p in artifacts:
            print(f"      wrote {p}", flush=True)

    # holdout discipline: redact trigger floats (book equity levels, slot
    # shares/thresholds) for triggers acting at/after blind_from. Structural
    # fields (kind, dates, sleeve names) stay; parquet artifacts keep full data.
    triggers_rep = triggers
    if blind_from is not None:
        cut = str(blind_from.date())
        keep = {"kind", "decided", "act", "sleeve", "max_sleeve", "min_sleeve"}
        triggers_rep = [
            ({k: (v if k in keep else "REDACTED-HOLDOUT") for k, v in t.items()}
             if t.get("act", "") >= cut else dict(t))
            for t in triggers]

    if anchor_gate:
        status = "reconciled" if (exact and consistency_ok) else "failed"
    else:
        status = "consistent" if consistency_ok else "failed"
    report = dict(
        status=status,
        feed=feed,
        us5_instrument=us5,
        window=[str(lo), str(hi)],
        index_timezone=("tz-naive broker SERVER time (IC native)" if feed == "ic"
                        else "tz-naive TRUE UTC (Duka native) — convert ONLY "
                             "via utc.tz_convert('America/New_York') + 7h, "
                             "then tz_localize(None)"),
        reference_key=REFERENCE_KEY if anchor_gate else None,
        anchor_exact_match=None if exact is None else bool(exact),
        metric_deltas={k: dict(mine=v[0], ref=v[1], delta=v[2])
                       for k, v in deltas.items()},
        dev_window_metrics=(None if dev_metrics is None else dict(
            window=[str(lo), str(dev_metrics_hi)], **dev_metrics)),
        n_triggers=len(triggers),
        triggers=triggers_rep,
        self_test=st_report,
        consistency=dict(max_leg_relerr=acc.max_leg_relerr,
                         max_book_relerr=acc.max_book_relerr,
                         concat_relerr=final_relerr,
                         gate="<1e-6 relative",
                         ok=bool(consistency_ok)),
        n_segments=acc.n_segments,
        segments=acc.segments,
        artifacts=artifacts,
        runtime_min=(time.time() - t_start) / 60.0,
        generated=pd.Timestamp.now().isoformat(),
    )
    rp = out_dir / f"v7_extract{artifact_suffix}_verification.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=1, default=str))
    print(f"STATUS: {report['status']}  (report: {rp}, "
          f"{report['runtime_min']:.1f} min)", flush=True)
    return report
