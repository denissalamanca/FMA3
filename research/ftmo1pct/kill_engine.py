"""FTMO 1%-per-idea kill engine — a physical fork of record_engine_ext.

WHAT THIS IS
------------
A research fork of engine/record_engine_ext.py that adds a per-CLUSTER
trailing-window loss-kill overlay on top of the FTMO daily circuit breaker:

* kernel  ``_run_chunk_kill``       <- verbatim copy of _run_chunk_stop
                                       (record_engine_ext.py:444-600) + hooks
                                       A-D (see RULE SPEC below);
* driver  ``simulate_account_1m_kill`` <- copy of simulate_account_1m_ext
                                       (607-776) + cluster/kill params and
                                       cross-quarter per-cluster carry;
* wrapper ``run_record_kill``       <- copy of run_record_ext (779-842).

The kernel is a PHYSICAL COPY (numba njit needs a real function to fork);
everything else (bar loaders, eurq/swap builders, PATHS, core) is IMPORTED
from record_engine_ext, never copied.

BIT-IDENTITY DESIGN (the gate)
------------------------------
Every kill-overlay statement is guarded by ``track_on`` (overlay enabled)
and writes only to NEW per-cluster accumulators; with the overlay OFF every
pre-existing floating-point statement of _run_chunk_stop executes in the
original order, so a kill-off run is bit-identical to record_engine_ext's
FTMO golden (gated in run_sweep.py against 1,332,404.1921628967 before any
kill-on number). Two refactors are provably bit-neutral: ``x += (expr)`` ->
``d = expr; x += d`` (same ops, same order).

RULE SPEC v0.2 — OWNER-CLARIFIED (supersedes the v0.1 "idea since
inception" reading, which was a misinterpretation)
----------------------------------------------------------------
Owner's own example (gold+silver on a 100k account): combined DD hits
-1,001 = breach; auto-cut at -800 at 16:20; no new gold/silver until 17:20.

For cluster C at minute t:

* FLOAT_C(t)  = worst-marked unrealized P&L of C's OPEN net positions,
  from each net position's entry (the kernel's existing per-leg
  entry/unrealized terms — hook C). While a position stays OPEN its meter
  anchors at ENTRY: there is NO hourly re-anchor for held trades.
* REAL1H_C(t) = realized P&L (incl. commissions) booked on C's symbols in
  the trailing 60 minutes, TIMESTAMP-based (window = ts in (t-60min, t];
  survives union-grid gaps/weekends). real_mode='net' (default: profits
  offset losses — the owner's "1% risk combined") or 'loss_only'
  (conservative variant: only loss-minutes count).
* IDEA_DD_C(t) = FLOAT_C(t) + REAL1H_C(t).
* KILL when IDEA_DD_C(t) <= -kill_pct * BALANCE(t). ref = CURRENT balance
  (the owner's example is 1% of the 100k account; in deployment monthly
  withdrawals keep balance near base, so current-balance is the faithful
  frame). The balance is SNAPSHOT once per minute before the cluster loop,
  so same-minute kills are order-invariant across clusters.
* On kill: flatten ONLY C at the minute's worst-side prices (bid_l longs /
  ask_h shorts, commission per lot — the existing breaker flatten pattern),
  then a 60-min cooldown (kill 16:20 -> first re-entry 17:20; the kill's
  realized loss ages out of the trailing window exactly at re-entry).
  The kill check runs AFTER the daily breaker (ordering unchanged).
* VIOLATION (the FTMO-visible number): any episode where IDEA_DD_C (net
  mode) <= -1.0% x balance before/at flatten, counted ONCE per episode
  (episode = one continuous below-the-line excursion; the flag clears when
  IDEA_DD_C recovers above the line). Kill/breaker/stop-out flatten fills
  enter REAL1H before the violation check — gap overshoot past the hard 1%
  is counted, not erased.
* There is NO months-long idea state: no inception ref freezing, no
  realized-since-inception meter. Cluster bookkeeping = the 60-slot
  realized ring + cooldown + the violation-episode flag, nothing else.

TIMING WINDOW (post-kill daily-breaker re-check)
------------------------------------------------
The daily breaker (step 6) runs BEFORE the kill hook (6b) and is NOT
re-checked after kill flattens. A kill's own fills (worst-side prices +
commission) can push eq_w below the daily line inside the kill minute; the
breaker then only sees it at the NEXT minute's check. The exposure is one
minute of commission/overshoot-sized slack, identical in kind to the
engine's existing intraminute gap-through convention. Ordering is kept so
n_daily_stops stays comparable to the no-kill golden.

LABELED APPROXIMATIONS
----------------------
* per-symbol NETTING: the engine nets each symbol into one position with a
  volume-weighted average entry; the live hedging account does per-ticket
  accounting. FLOAT_C is therefore the netted meter, not the ticket meter.
* worst marks are per-leg intraminute extremes (bid_l/ask_h) summed across
  legs — each leg's own worst print, not one simultaneous timestamp (the
  engine of record's existing worst-mark convention).
* swap carry is NOT attributed to REAL1H (flows to balance only) — swaps
  are second-order vs spreads/commissions at 1h turnover. The
  pend-completeness identity (driver) accounts for them separately.
* 'loss_only' aggregates at 1-minute cluster granularity: a minute's fills
  on one cluster net against each other before the min(.,0) is taken.
* 1-minute granularity (engine of record): intraminute overshoot past the
  kill line is kept, not erased (honest gap-through, same physics as the
  daily breaker).

PROVENANCE: fork of engine/record_engine_ext.py at the sha256 recorded in
manifest.json (this directory). NEVER edit the parent engine.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
from numba import njit

# ---------------------------------------------------------------------------
# Import (not copy) the parent engine: loaders, helpers, constants, core.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
_ENGINE_DIR = str(_REPO / "engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
import record_engine_ext as REX      # noqa: E402  (bootstraps record_engine + FMA2 core)
import core                          # noqa: E402  FMA2 research core

PATHS = REX.PATHS
_FIELDS = REX._FIELDS
_EUR_CROSS = REX._EUR_CROSS
_resolve_bar_files = REX._resolve_bar_files
_native = REX._native
_densify = REX._densify
_eurq_chunk = REX._eurq_chunk
_swap_chunk = REX._swap_chunk
BASE_QUARTERS = REX.BASE_QUARTERS

__all__ = ["simulate_account_1m_kill", "run_record_kill", "CLUSTERS",
           "build_cluster_id", "PATHS"]

# ---------------------------------------------------------------------------
# Cluster table (13 idea-units + EURSEK singleton if present). MODEL symbol
# names as used by the fed matrix columns (USA500/DAX/USTEC — NOT the
# CSV-serialized tester names US500/DE40).
# ---------------------------------------------------------------------------
CLUSTERS: dict[str, tuple[str, ...]] = {
    "IDX":     ("DAX", "JP225", "UK100", "US30", "USA500", "USTEC"),
    "DBLOC":   ("AUDCAD", "AUDUSD", "EURNZD", "NZDCAD", "NZDUSD"),
    "JPYX":    ("AUDJPY", "CADJPY", "GBPJPY", "NZDJPY", "USDJPY"),
    "CRYPTO":  ("BTCUSD", "ETHUSD", "SOLUSD"),
    "EURCADX": ("CADCHF", "EURCAD"),
    "EURUSDX": ("EURUSD", "USDCHF"),
    "PMET":    ("XAGUSD", "XAUUSD"),
    "OIL":     ("XBRUSD", "XTIUSD"),
    "AUDNZD":  ("AUDNZD",),
    "EURCHF":  ("EURCHF",),
    "EURGBP":  ("EURGBP",),
    "EURNOK":  ("EURNOK",),
    "XNGUSD":  ("XNGUSD",),
    "EURSEK":  ("EURSEK",),   # singleton if present (dropped in the 80k recipe)
}

_SYM2CLUSTER: dict[str, str] = {}
for _cname, _syms in CLUSTERS.items():
    for _s in _syms:
        if _s in _SYM2CLUSTER:
            raise AssertionError(f"symbol {_s} mapped to two clusters "
                                 f"({_SYM2CLUSTER[_s]}, {_cname})")
        _SYM2CLUSTER[_s] = _cname


def build_cluster_id(symbols: list[str]) -> tuple[np.ndarray, list[str]]:
    """cluster_id int64 array aligned to symbol columns + ordered cluster
    name list (only clusters actually present). FAILS LOUDLY on any column
    that does not map to exactly one cluster."""
    unmapped = [s for s in symbols if s not in _SYM2CLUSTER]
    if unmapped:
        raise AssertionError(
            f"fed columns not mapped to any cluster: {unmapped} — the "
            "cluster table must cover every traded column (model names, "
            "e.g. USA500/DAX/USTEC).")
    names = [c for c in CLUSTERS if any(s in symbols for s in CLUSTERS[c])]
    idx = {c: i for i, c in enumerate(names)}
    cid = np.array([idx[_SYM2CLUSTER[s]] for s in symbols], dtype=np.int64)
    return cid, names


# ---------------------------------------------------------------------------
# Kernel — VERBATIM copy of record_engine_ext._run_chunk_stop (lines
# 444-600) + kill hooks A-D. All overlay state is mutated IN PLACE (ring_*
# / cl_* arrays) so it carries across quarter chunks without extra return
# plumbing. Timestamp-based throughout: cooldown expiry and window aging
# use grid_ns, NEVER "grid minutes elapsed", so union-grid gaps (weekends:
# positions persist across 200+ gaps) are handled correctly and a held
# cluster is never treated as flat/reset across a gap.
# ---------------------------------------------------------------------------
@njit(cache=True)
def _run_chunk_kill(tgt, has_bar, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
                    eurq, swap_l, swap_s,
                    contract, comm_side, leverage, lot_step, min_lot, vol_limit,
                    stop_out_level, margin_cap, rebalance_band,
                    balance0, lots0, entry0,
                    day_id, stop_frac, anchor0, last_close0, cur_day0,
                    halted0,
                    grid_ns, cluster_id, n_clusters,
                    track_on, kill_on, kill_frac, loss_mode, viol_frac,
                    cooldown_ns, window_ns,
                    ring_ts, ring_net, ring_loss,
                    cl_violflag, cl_cool, cl_nkills, cl_nviol,
                    cl_flushed, acct_acc):
    """_run_chunk_stop + per-cluster trailing-window kill overlay (hooks
    A-D, RULE SPEC v0.2). Returns the _run_chunk_stop tuple; ring_*/cl_*
    /acct_acc arrays are mutated in place.

    track_on : overlay bookkeeping active (rings, violations). kill_on :
    the kill trigger itself (False + track_on = violations-only census).
    ring_ts/ring_net/ring_loss : (n_clusters, 60) per-cluster realized ring
    keyed by absolute minute (slot = minute % 60; each slot stores its own
    ts, stale slots are excluded by the ts > t-60min window test and
    overwritten lazily). acct_acc[0] accumulates swap carry (for the
    driver's pend-completeness identity).
    """
    T, K = tgt.shape
    balance = balance0
    lots = lots0.copy()
    entry = entry0.copy()
    eq_c = np.empty(T)
    eq_w = np.empty(T)
    n_trades = 0
    anchor = anchor0
    last_close = last_close0
    cur_day = cur_day0
    halted = halted0
    n_stops = 0

    pend = np.zeros(n_clusters)               # per-minute realized delta
    cl_uw = np.zeros(n_clusters)              # co-timed worst-mark unrealized
    nzc = np.zeros(n_clusters, dtype=np.int64)

    for t in range(T):
        ts_now = grid_ns[t]
        if track_on:
            for c in range(n_clusters):
                pend[c] = 0.0
                cl_uw[c] = 0.0
                nzc[c] = 0
        account_flattened = False

        # 0. server-day rollover: re-anchor at prev day's close, lift halt
        if day_id[t] != cur_day:
            anchor = last_close
            halted = False
            cur_day = day_id[t]

        # 1. swaps at the rollover minute (NOT attributed to REAL1H — labeled
        #    approximation; tracked in acct_acc[0] for the balance identity)
        for k in range(K):
            if lots[k] != 0.0 and (swap_l[t, k] != 0.0 or swap_s[t, k] != 0.0):
                mid = 0.5 * (bid_o[t, k] + ask_o[t, k])
                notional = abs(lots[k]) * contract[k] * mid * eurq[t, k]
                d_sw = notional * (swap_l[t, k] if lots[k] > 0 else swap_s[t, k])
                balance += d_sw
                if track_on:
                    acct_acc[0] += d_sw

        # 2. desired lots from the shared balance (halt forces zero targets)
        #    HOOK A: cooldown-blocked clusters are also forced to zero
        #    (timestamp compare — gap-safe; expiry at cl_cool exactly).
        desired = np.zeros(K)
        margin_sum = 0.0
        for k in range(K):
            g = tgt[t, k]
            if halted:
                g = 0.0
            if kill_on and g != 0.0 and cl_cool[cluster_id[k]] > ts_now:
                g = 0.0
            if not has_bar[t, k]:
                desired[k] = lots[k]
                continue
            if g == 0.0:
                desired[k] = 0.0
                continue
            px = ask_o[t, k] if g > 0 else bid_o[t, k]
            unit = px * contract[k] * eurq[t, k]
            raw = g * balance / unit
            n = np.floor(abs(raw) / lot_step[k] + 1e-9)
            L = n * lot_step[k]
            if L < min_lot[k]:
                L = 0.0
            desired[k] = np.sign(g) * L
            margin_sum += abs(desired[k]) * unit / leverage[k]

        shrink = 1.0
        cap = balance * margin_cap
        if margin_sum > cap and margin_sum > 0.0:
            shrink = cap / margin_sum

        # 3. execute fills (cross the spread), with rebalance band
        #    HOOK B: accumulate per-cluster REALIZED P&L (pnl - comm) into
        #    pend — every close AND every add-commission; nothing realized
        #    is ever dropped from the trailing window.
        for k in range(K):
            if not has_bar[t, k]:
                continue
            want = desired[k] * shrink
            n = np.floor(abs(want) / lot_step[k] + 1e-9)
            want = np.sign(want) * n * lot_step[k]
            if abs(want) < min_lot[k]:
                want = 0.0
            if vol_limit[k] > 0.0 and abs(want) > vol_limit[k]:   # broker per-symbol total-volume cap (inert when 0)
                want = np.sign(want) * np.floor(vol_limit[k] / lot_step[k] + 1e-9) * lot_step[k]
            if (lots[k] != 0.0 and want != 0.0 and want * lots[k] > 0.0
                    and abs(want - lots[k]) / abs(lots[k]) <= rebalance_band):
                continue
            if want == lots[k]:
                continue
            if lots[k] != 0.0 and (want == 0.0 or want * lots[k] < 0.0
                                   or abs(want) < abs(lots[k])):
                close_lots = lots[k] if want * lots[k] <= 0.0 else lots[k] - want
                px = bid_o[t, k] if lots[k] > 0 else ask_o[t, k]
                pnl = (px - entry[k]) * close_lots * contract[k] * eurq[t, k]
                net = pnl - comm_side[k] * abs(close_lots)
                balance += net
                if track_on:
                    pend[cluster_id[k]] += net
                lots[k] -= close_lots
                n_trades += 1
                if lots[k] == 0.0:
                    entry[k] = 0.0
            if want != 0.0 and abs(want) > abs(lots[k]):
                add = want - lots[k]
                px = ask_o[t, k] if add > 0 else bid_o[t, k]
                if lots[k] == 0.0:
                    entry[k] = px
                else:
                    entry[k] = (entry[k] * lots[k] + px * add) / (lots[k] + add)
                cost = comm_side[k] * abs(add)
                balance -= cost
                if track_on:
                    pend[cluster_id[k]] -= cost
                lots[k] = want
                n_trades += 1

        # 4. joint marks (co-timed at this minute)
        #    HOOK C: per-cluster co-timed worst-mark unrealized from each net
        #    position's ENTRY (no hourly re-anchor for held trades) — this is
        #    FLOAT_C. Reset above each minute; recomputed from open lots, so
        #    a held cluster carries its meter across weekends untouched.
        unreal_c = 0.0
        unreal_w = 0.0
        margin_used = 0.0
        for k in range(K):
            if lots[k] == 0.0:
                continue
            if lots[k] > 0:
                d_c = (bid_c[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                d_w = (bid_l[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
            else:
                d_c = (ask_c[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                d_w = (ask_h[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
            unreal_c += d_c
            unreal_w += d_w
            if track_on:
                cc = cluster_id[k]
                cl_uw[cc] += d_w
                nzc[cc] = 1
            mid_c = 0.5 * (bid_c[t, k] + ask_c[t, k])
            margin_used += abs(lots[k]) * contract[k] * mid_c * eurq[t, k] / leverage[k]
        eq_c[t] = balance + unreal_c
        eq_w[t] = balance + unreal_w

        # 5. joint stop-out on the worst co-timed mark
        #    (flatten fills enter pend -> REAL1H; crisis-correlated fills are
        #    never dropped from the window or the violation check)
        if margin_used > 0.0 and eq_w[t] < stop_out_level * margin_used:
            for k in range(K):
                if lots[k] == 0.0:
                    continue
                px = bid_l[t, k] if lots[k] > 0 else ask_h[t, k]
                pnl = (px - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                net = pnl - comm_side[k] * abs(lots[k])
                balance += net
                if track_on:
                    pend[cluster_id[k]] += net
                lots[k] = 0.0
                entry[k] = 0.0
            eq_c[t] = balance
            eq_w[t] = balance
            if track_on:
                account_flattened = True

        # 6. FTMO daily circuit breaker: worst co-timed mark vs day anchor.
        # Gap-through: eq_w[t] can already be far below the stop level — the
        # flatten executes at the worst-side prices that PRODUCED that mark,
        # so the crossing minute's overshoot is kept, not erased.
        if not halted and eq_w[t] <= anchor * (1.0 - stop_frac):
            halted = True
            n_stops += 1
            for k in range(K):
                if lots[k] == 0.0:
                    continue
                px = bid_l[t, k] if lots[k] > 0 else ask_h[t, k]
                pnl = (px - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                net = pnl - comm_side[k] * abs(lots[k])
                balance += net
                if track_on:
                    pend[cluster_id[k]] += net
                lots[k] = 0.0
                entry[k] = 0.0
            eq_c[t] = balance
            eq_w[t] = balance
            if track_on:
                account_flattened = True

        # 6b. HOOK D — trailing-window kill + FTMO-visible violation census
        # (AFTER the daily breaker, same minute; the breaker is NOT
        # re-checked post-kill — see TIMING WINDOW in the module docstring).
        # Entirely guarded: with track_on False this whole block is skipped
        # and the kernel is _run_chunk_stop.
        if track_on:
            bal_ref = balance          # SNAPSHOT once: same-minute kills are
            killed_any = False         # order-invariant across clusters
            for c in range(n_clusters):
                # flush this minute's realized into the 60-slot ring
                # (unconditional — full closes on the first minute after a
                # gap and clusters flattened by stop-out/breaker included)
                p = pend[c]
                if p != 0.0:
                    slot = (ts_now // 60_000_000_000) % 60
                    if ring_ts[c, slot] == ts_now:
                        ring_net[c, slot] += p
                        if p < 0.0:
                            ring_loss[c, slot] += p
                    else:
                        ring_ts[c, slot] = ts_now
                        ring_net[c, slot] = p
                        ring_loss[c, slot] = p if p < 0.0 else 0.0
                    cl_flushed[c] += p
                # REAL1H: trailing 60 min, timestamp-based (survives gaps);
                # window = (t-60min, t] so a kill loss at 16:20 ages out
                # exactly at the 17:20 re-entry.
                cutoff = ts_now - window_ns
                r_net = 0.0
                r_loss = 0.0
                for s_ in range(60):
                    if ring_ts[c, s_] > cutoff:
                        r_net += ring_net[c, s_]
                        r_loss += ring_loss[c, s_]
                fl = 0.0 if account_flattened else cl_uw[c]
                dd_net = fl + r_net
                # VIOLATION (FTMO-visible): net-mode IDEA_DD <= -1.0% x
                # balance, once per below-the-line episode.
                if dd_net <= -viol_frac * bal_ref:
                    if cl_violflag[c] == 0:
                        cl_nviol[c] += 1
                        cl_violflag[c] = 1
                else:
                    cl_violflag[c] = 0
                # KILL: only on open exposure (a flat cluster has nothing to
                # cut; re-entry is blocked by the cooldown, not by re-kills,
                # so 16:20 -> 17:20 holds exactly).
                if kill_on and (not account_flattened) and nzc[c] == 1:
                    dd_kill = fl + (r_loss if loss_mode else r_net)
                    if dd_kill <= -kill_frac * bal_ref:
                        fills = 0.0
                        for k in range(K):
                            if cluster_id[k] != c or lots[k] == 0.0:
                                continue
                            px = bid_l[t, k] if lots[k] > 0 else ask_h[t, k]
                            pnl = (px - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                            net = pnl - comm_side[k] * abs(lots[k])
                            balance += net
                            fills += net
                            lots[k] = 0.0
                            entry[k] = 0.0
                        # kill fills enter the SAME ring slot (never dropped)
                        slot = (ts_now // 60_000_000_000) % 60
                        if ring_ts[c, slot] == ts_now:
                            ring_net[c, slot] += fills
                            if fills < 0.0:
                                ring_loss[c, slot] += fills
                        else:
                            ring_ts[c, slot] = ts_now
                            ring_net[c, slot] = fills
                            ring_loss[c, slot] = fills if fills < 0.0 else 0.0
                        cl_flushed[c] += fills
                        cl_nkills[c] += 1
                        cl_cool[c] = ts_now + cooldown_ns
                        killed_any = True
                        # post-flatten violation re-check (same episode —
                        # flag guards double count): float now 0, window
                        # includes the kill fills' overshoot.
                        r_net += fills
                        if r_net <= -viol_frac * bal_ref:
                            if cl_violflag[c] == 0:
                                cl_nviol[c] += 1
                                cl_violflag[c] = 1
                        else:
                            cl_violflag[c] = 0
            if killed_any:
                # recompute joint marks post-kill (daily breaker NOT
                # re-checked this minute — documented timing window)
                u_c = 0.0
                u_w = 0.0
                for k in range(K):
                    if lots[k] == 0.0:
                        continue
                    if lots[k] > 0:
                        u_c += (bid_c[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                        u_w += (bid_l[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                    else:
                        u_c += (ask_c[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                        u_w += (ask_h[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                eq_c[t] = balance + u_c
                eq_w[t] = balance + u_w

        last_close = eq_c[t]

    return (eq_c, eq_w, balance, lots, entry, n_trades,
            anchor, last_close, cur_day, halted, n_stops)


# ---------------------------------------------------------------------------
# Driver — copy of record_engine_ext.simulate_account_1m_ext (607-776) with
# the kill overlay parameters + per-cluster cross-quarter carry state.
# ---------------------------------------------------------------------------
def simulate_account_1m_kill(pos: pd.DataFrame, *, initial: float = 10_000.0,
                             margin_cap: float = 0.9,
                             rebalance_band: float = 0.25,
                             start_quarter: str = BASE_QUARTERS[0],
                             end_quarter: str = BASE_QUARTERS[1],
                             bar_files: Mapping[str, object] | None = None,
                             daily_stop_x: float | None = None,
                             volume_limit: Mapping[str, float] | None = None,
                             kill_pct: float | None = None,
                             real_mode: str = "net",
                             violations_only: bool = False,
                             cooldown_min: int = 60,
                             window_min: int = 60,
                             verbose: bool = True):
    """simulate_account_1m_ext + per-cluster trailing-window kill overlay
    (RULE SPEC v0.2 — see module docstring).

    kill_pct : fraction of CURRENT balance (e.g. 0.008), or None/0 = kill
        trigger OFF. With violations_only also False the overlay is fully
        off and the run is bit-identical to the parent engine (gated).
    real_mode : 'net' (profits offset losses in REAL1H — default, the
        owner's combined rule) or 'loss_only' (conservative variant).
        Violations are ALWAYS counted on the net-mode meter.
    violations_only : True = overlay bookkeeping (rings + violation census)
        with the kill trigger disabled — measures how non-compliant the raw
        book is under the rule. Equity must stay bit-identical to the
        golden (the overlay writes only to its own accumulators).
    cooldown_min / window_min : re-entry cooldown and trailing REAL1H
        window (both 60 in the owner's rule).
    Requires daily_stop_x set (FTMO context); the kernel is a fork of
    _run_chunk_stop, not of the no-stop _run_chunk.
    """
    if daily_stop_x is None:
        raise ValueError("this fork requires daily_stop_x (FTMO context); "
                         "use record_engine_ext for no-breaker runs")
    if real_mode not in ("net", "loss_only"):
        raise ValueError(f"real_mode must be 'net' or 'loss_only', got {real_mode!r}")

    stop_out = float(core.S.ACCOUNT["stop_out_level"])
    if stop_out != 0.5:
        raise AssertionError(
            f"stop_out_level = {stop_out!r}, expected the production 0.50. "
            "This process was probably poisoned by NSF5's lock_v5 import "
            "side-effect (v7 stack sets 1e-9 'noliq'). Never run the record "
            "engine in the same process as engine/v7_bridge or gbandrebal "
            "imports.")

    symbols = [c for c in pos.columns]
    crosses = sorted({_EUR_CROSS[core.S.INSTRUMENTS[s]["quote"]]
                      for s in symbols
                      if core.S.INSTRUMENTS[s]["quote"] != "EUR"})
    load_syms = list(dict.fromkeys(symbols + crosses))
    src = {s: _resolve_bar_files(s, bar_files) for s in load_syms}

    contract = np.array([core.S.INSTRUMENTS[s]["contract_size"] for s in symbols], float)
    comm = np.array([core.S.INSTRUMENTS[s]["commission_side"] for s in symbols], float)
    lev = np.array([core.S.INSTRUMENTS[s]["leverage"] for s in symbols], float)
    step = np.array([core.S.INSTRUMENTS[s]["lot_step"] for s in symbols], float)
    mlot = np.array([core.S.INSTRUMENTS[s]["min_lot"] for s in symbols], float)
    vlim = np.array([(volume_limit.get(s, 0.0) if volume_limit else 0.0) for s in symbols], float)

    # --- kill overlay state (per cluster, carried across quarter chunks) ---
    cluster_id, cluster_names = build_cluster_id(symbols)
    n_clusters = len(cluster_names)
    kill_on = bool(kill_pct)
    track_on = kill_on or bool(violations_only)
    kill_frac = float(kill_pct) if kill_on else 0.0
    loss_mode = (real_mode == "loss_only")
    VIOL_FRAC = 0.010                     # the hard FTMO-visible 1% line
    SENT = np.int64(-4611686018427387904)
    ring_ts = np.full((n_clusters, 60), SENT, dtype=np.int64)
    ring_net = np.zeros((n_clusters, 60))
    ring_loss = np.zeros((n_clusters, 60))
    cl_violflag = np.zeros(n_clusters, dtype=np.int64)
    cl_cool = np.full(n_clusters, SENT, dtype=np.int64)
    cl_nkills = np.zeros(n_clusters, dtype=np.int64)
    cl_nviol = np.zeros(n_clusters, dtype=np.int64)
    cl_flushed = np.zeros(n_clusters)     # sum of ALL ring entries (pend-completeness)
    acct_acc = np.zeros(1)                # [0] = swap carry total
    cooldown_ns = np.int64(cooldown_min) * np.int64(60_000_000_000)
    window_ns = np.int64(window_min) * np.int64(60_000_000_000)
    if window_min > 60:
        raise ValueError("window_min > 60 needs a bigger ring; the 60-slot "
                         "ring only supports window_min <= 60")

    quarters = pd.period_range(start_quarter, end_quarter, freq="Q")
    if len(quarters) == 0:
        raise ValueError(f"empty quarter range {start_quarter}..{end_quarter}")

    for qp in quarters:
        for c in crosses:
            idx_c, _ = _native(src[c])
            if idx_c[-1] < np.int64(qp.start_time.value):
                raise ValueError(
                    f"EUR cross {c} bar source ends "
                    f"{pd.Timestamp(idx_c[-1])} — before {qp} starts. EUR "
                    "conversion would freeze (the NSF5 2026-07-02 FxConverter "
                    f"audit defect). Provide bar_files[{c!r}] covering the "
                    "window.")

    balance = initial
    lots = np.zeros(len(symbols))
    entry = np.zeros(len(symbols))
    eqc_parts, eqw_parts, idx_parts = [], [], []
    total_trades = 0

    stop_frac = float(daily_stop_x) / 100.0
    if not (0.0 < stop_frac):
        raise ValueError(f"daily_stop_x must be a positive percent, "
                         f"got {daily_stop_x!r}")
    ds_anchor, ds_last_close = float(initial), float(initial)
    ds_cur_day, ds_halted = np.int64(-1), False
    total_stops = 0

    for qp in quarters:
        qs, qe = qp.start_time, qp.end_time
        grids = []
        for s in load_syms:
            idx, _ = _native(src[s])
            lo = np.searchsorted(idx, np.int64(qs.value), side="left")
            hi = np.searchsorted(idx, np.int64(qe.value), side="right")
            grids.append(idx[lo:hi])
        grid_ns = np.unique(np.concatenate(grids))
        # ring-slot arithmetic (slot = minute % 60) assumes minute-aligned stamps;
        # a sub-minute offset would silently alias two flushes into one slot.
        assert (grid_ns % 60_000_000_000 == 0).all(), "grid_ns not minute-aligned"
        if grid_ns.size == 0:
            continue

        has = np.zeros((len(grid_ns), len(symbols)), dtype=np.bool_)
        f = {fl: np.zeros((len(grid_ns), len(symbols))) for fl in _FIELDS}
        for k, s in enumerate(symbols):
            hb, out = _densify(src[s], grid_ns)
            has[:, k] = hb
            for fl in _FIELDS:
                f[fl][:, k] = out[fl]
        close_mid = {}
        for c in crosses:
            _, out = _densify(src[c], grid_ns)
            close_mid[c] = 0.5 * (out["bid_c"] + out["ask_c"])

        eurq = _eurq_chunk(symbols, grid_ns, close_mid)
        swap_l, swap_s = _swap_chunk(symbols, grid_ns)

        gidx = pd.DatetimeIndex(grid_ns.astype("datetime64[ns]"))
        prev_hour = gidx.floor("h") - pd.Timedelta(hours=1)
        tgt = pos.reindex(prev_hour, method=None).to_numpy()
        tgt = np.nan_to_num(tgt, nan=0.0)

        day_id = grid_ns // 86_400_000_000_000   # server-day ordinal (ns)
        (eqc, eqw, balance, lots, entry, ntr,
         ds_anchor, ds_last_close, ds_cur_day, ds_halted,
         n_st) = _run_chunk_kill(
            tgt, has, f["bid_o"], f["ask_o"], f["bid_c"], f["ask_c"],
            f["bid_l"], f["ask_h"], eurq, swap_l, swap_s,
            contract, comm, lev, step, mlot, vlim,
            stop_out, float(margin_cap), float(rebalance_band),
            balance, lots, entry,
            day_id, float(stop_frac), ds_anchor, ds_last_close,
            ds_cur_day, ds_halted,
            grid_ns, cluster_id, n_clusters,
            track_on, kill_on, kill_frac, loss_mode, VIOL_FRAC,
            cooldown_ns, window_ns,
            ring_ts, ring_net, ring_loss,
            cl_violflag, cl_cool, cl_nkills, cl_nviol,
            cl_flushed, acct_acc)
        total_stops += int(n_st)
        eqc_parts.append(eqc)
        eqw_parts.append(eqw)
        idx_parts.append(gidx)
        total_trades += ntr
        if verbose:
            print(f"  {qp}: {len(grid_ns):>7,} min | bal €{balance:,.0f} "
                  f"| trades {ntr:,} | kills {int(cl_nkills.sum()):,} "
                  f"| viol {int(cl_nviol.sum()):,}",
                  flush=True)

    if not idx_parts:
        raise ValueError(
            f"no bars at all in {start_quarter}..{end_quarter} for "
            f"{load_syms} — wrong bar_files / empty window?")

    idx = idx_parts[0].append(idx_parts[1:]) if len(idx_parts) > 1 else idx_parts[0]
    eq_c = pd.Series(np.concatenate(eqc_parts), index=idx, name="equity")
    eq_w = pd.Series(np.concatenate(eqw_parts), index=idx, name="worst")
    m = core.compute_metrics(eq_c / initial)
    peak = np.maximum.accumulate(eq_c.to_numpy())
    m["maxdd"] = float(((peak - eq_w.to_numpy()) / np.maximum(peak, 1e-9)).max())
    m["final_equity"] = float(eq_c.iloc[-1])
    m["n_trades"] = int(total_trades)
    m["n_daily_stops"] = int(total_stops)

    # pend-completeness identity (overlay on): every euro that moved the
    # balance is either attributed realized (Σ ring flushes) or swap carry.
    pend_check = None
    if track_on:
        resid = float(balance) - (float(initial) + float(cl_flushed.sum())
                                  + float(acct_acc[0]))
        pend_check = {"sum_real1h_flushed": float(cl_flushed.sum()),
                      "swap_total": float(acct_acc[0]),
                      "identity_residual": resid,
                      "flushed_by_cluster": {cluster_names[i]: float(cl_flushed[i])
                                             for i in range(n_clusters)}}

    m["kill"] = {
        "rule": "v0.2 trailing-window (FLOAT + REAL1H vs current balance)",
        "kill_pct": (float(kill_pct) if kill_on else None),
        "real_mode": real_mode if track_on else None,
        "violations_only": bool(violations_only),
        "ref": "current_balance",
        "cooldown_min": cooldown_min, "window_min": window_min,
        "n_kills_total": int(cl_nkills.sum()),
        "kills_by_cluster": {cluster_names[i]: int(cl_nkills[i])
                             for i in range(n_clusters) if cl_nkills[i] > 0},
        "violations_total": int(cl_nviol.sum()),
        "violations_by_cluster": {cluster_names[i]: int(cl_nviol[i])
                                  for i in range(n_clusters) if cl_nviol[i] > 0},
        "pend_check": pend_check,
        "cluster_names": cluster_names,
    }
    return eq_c, eq_w, m


def run_record_kill(frac_1h: pd.DataFrame, *,
                    start_quarter: str = BASE_QUARTERS[0],
                    end_quarter: str = BASE_QUARTERS[1],
                    bar_files: Mapping[str, object] | None = None,
                    initial: float = 10_000.0,
                    daily_stop_x: float | None = None,
                    volume_limit=None,
                    kill_pct: float | None = None,
                    real_mode: str = "net",
                    violations_only: bool = False,
                    label: str,
                    verbose: bool = True,
                    run_bootstrap: bool = False) -> dict:
    """run_record_ext-shaped wrapper around the kill engine (same result-dict
    contract + a ``kill`` block). run_bootstrap defaults False here."""
    if not isinstance(frac_1h.index, pd.DatetimeIndex) or frac_1h.index.tz is not None:
        raise ValueError("frac_1h must have a tz-naive (server-time) DatetimeIndex")
    q0, q1 = pd.Period(start_quarter, freq="Q"), pd.Period(end_quarter, freq="Q")
    if q0 > q1:
        raise ValueError(f"start_quarter {q0} is after end_quarter {q1}")

    eq_c, eq_w, m = simulate_account_1m_kill(
        frac_1h, initial=initial, start_quarter=str(q0), end_quarter=str(q1),
        bar_files=bar_files, daily_stop_x=daily_stop_x,
        volume_limit=volume_limit, kill_pct=kill_pct, real_mode=real_mode,
        violations_only=violations_only, verbose=verbose)

    peak = np.maximum.accumulate(eq_c.to_numpy())
    maxdd_close = float(((peak - eq_c.to_numpy()) / np.maximum(peak, 1e-9)).max())

    breach = None
    if run_bootstrap:
        curve = pd.DataFrame({"equity": eq_c, "worst": eq_w})
        breach = REX.worst_mark_breach(curve)

    neg_years = sorted(int(y) for y, r in m["yearly"].items() if r < 0)
    neg_quarters = sorted(q for q, r in m["quarterly"].items() if r < 0)

    return {
        "label": label,
        "start_quarter": str(q0),
        "end_quarter": str(q1),
        "initial": float(initial),
        "daily_stop_x": daily_stop_x,
        "n_daily_stops": m["n_daily_stops"],
        "kill": m["kill"],
        "cagr": float(m["cagr"]),
        "maxdd_worst": float(m["maxdd"]),
        "maxdd_close": maxdd_close,
        "sharpe": float(m["sharpe"]),
        "final_equity": float(m["final_equity"]),
        "n_trades": int(m["n_trades"]),
        "years": float(m["years"]),
        "yearly": {int(k): float(v) for k, v in m["yearly"].items()},
        "quarterly": {str(k): float(v) for k, v in m["quarterly"].items()},
        "neg_years": neg_years,
        "neg_quarters": neg_quarters,
        "n_neg_years": int(m["n_neg_years"]),
        "n_neg_quarters": int(m["n_neg_quarters"]),
        "breach": breach,
        "curves": {"equity": eq_c, "worst": eq_w},
        "engine_metrics": m,
    }


if __name__ == "__main__":
    print("kill_engine module OK — fork of record_engine_ext (see manifest.json)")
    print(f"clusters: {list(CLUSTERS)}")
