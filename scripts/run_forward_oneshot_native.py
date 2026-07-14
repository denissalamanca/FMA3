#!/usr/bin/env python3
"""FMA3 2026H1 ONE-SHOT forward confirmation — native-curve driver.

WHY THIS DRIVER (and not scripts/run_forward_oneshot.py directly)
------------------------------------------------------------------
The stock driver predates the v7 forward artifacts; its 'simulated'
sub-equity mode would measure the v7 weighting curve A by re-running the v7
fraction matrix through the ext record engine. The LOCKED construction
(strategy_fma3.FMA3_CONFIG['construction'], eval_fma3_pin.build_locked_matrix,
run_hfed1.load_inputs) defines A and B as the parents' NATIVE curves — for
v7 that is its own band-book equity (the extractor artifact), not an
ext-engine replay. This driver implements exactly that, reusing the stock
module's gates and helpers (gate_preregistration, gate_oneshot,
fwd_tradable_symbols, fwd_bar_files, restrict_to_forward, blend_static):

  * A = research/outputs/fwd/v7_book_equity_1m_fwd.parquet 'eqc' (the v7 band
    book's native Duka-feed forward curve), converted TRUE UTC -> broker
    server time (utc.tz_convert('America/New_York') + 7h -> naive; the FMA2
    build_ext_cache rule), re-normalized to 1.0 at the first mark at/after
    2026-01-01 00:00 server — the FORWARD_TEST.md fresh seed.
  * B = the v3.4 book's native forward curve. v3.4 is fixed-fraction and has
    no native 2026 curve artifact, so B comes from ONE ext-engine run of the
    v3.4 forward matrix alone (seeded (1-w)*E0 = EUR 3,000), executed FIRST
    within the same gated one-shot session (documented two-step; the alone
    run and the blend run together are the single consumption — no
    iteration on either).
  * fed = [core_frac*(w*A_h/J_h) + sat_frac*((1-w)*B_h/J_h)] * s with w = 0.70,
    s = 1.1, J = w*A + (1-w)*B, curves sampled causally at hour h
    (run_forward_oneshot.blend_static — the exact H-FED-1 / eval_fma3_pin
    bookkeeping), run through engine/record_engine_ext.py on 2026Q1..2026Q2
    with the Duka forward 1m cache (research/fwd_cache_1m/).

USTEC: both forward matrices already realize FORWARD_TEST.md's USA500-proxy
convention at the COLUMN level — the v7 extraction carries its USTEC-sleeve
exposure in a USA500 column (v51_rig prime_2026 convention) and the v34
matrix has USTEC zeroed on every 2026 row. The traded universe is therefore
the 14 real Duka symbols (fwd_tradable_symbols('drop')); no synthetic
USTEC-priced-on-USA500 instrument is needed.

F3 INSTRUMENTATION: the pre-registered F3 bar ("no joint stop-out or
margin-cap breach event") is measured by an instrumented VERBATIM copy of the
record engine's numba kernel that additionally counts (a) joint stop-out
events and (b) minutes where the 0.9 margin cap binds (shrink < 1), and
tracks the realized margin envelope. The instrumented run must reproduce the
record run's equity curves BIT-EXACTLY (np.array_equal) or the driver aborts:
the counters are trustworthy only because the arithmetic is provably
identical. The extra statements only READ already-computed values into
integer/scalar trackers — no floating-point statement of the engine of
record is reordered or altered.

WINDOW: the engine runs 2026Q1..2026Q2 (12-symbol common window; bars end
server 2026-05-01 02:59, EURUSD/XAUUSD run to June with the book flat because
the fed matrix ends 2026-04-30 23:00 and later hours reindex to zero). ALL
reported window metrics are computed on curves TRUNCATED at server
2026-04-30 23:59:59 — the pre-registered uniform window end (FORWARD_TEST.md,
same convention as the v34 forward matrix build). Open positions at the
truncation stamp are marked to market, not closed.

Modes
-----
  dryrun <out_dir> : full plumbing rehearsal on 2025Q4 (IC bars, fresh
      2025-10-01 seed, outputs to <out_dir>). Computes NO 2026 number:
      quarter range is 2025Q4..2025Q4 and every input is sliced/truncated
      inside 2025. Proves the loaders, the tz conversion, the blend, the
      instrumented-kernel bit-identity, the bar evaluation and the report
      writers end-to-end. Also validates (without running) the 2026 bar-file
      mapping.
  oneshot : the single gated consumption of the 2026H1 holdout. Writes
      research/outputs/forward_oneshot.json (GATE 2 flips permanently),
      forward_oneshot_curve.parquet, forward_oneshot_v34sub_curve.parquet,
      research/outputs/fwd/book_frac_1h_fwd.parquet and
      research/outputs/FORWARD_ONESHOT.md.

CPU etiquette: waits for the verify_record_engine_ext/eval_fma3_pin lock
chain before any engine run.

Run:
  python3 scripts/run_forward_oneshot_native.py dryrun /path/to/scratch
  python3 scripts/run_forward_oneshot_native.py oneshot
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
from numba import njit

_FMA3 = Path(__file__).resolve().parents[1]
for p in (str(_FMA3), str(_FMA3 / "engine"), str(_FMA3 / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_forward_oneshot as OS            # noqa: E402  gates + helpers
import record_engine_ext as RX              # noqa: E402  engine of record (ext)
import core                                 # noqa: E402  FMA2 research core
from strategy_fma3 import FMA3_CONFIG, config_hash  # noqa: E402

FWD_DIR = RX.PATHS.OUTPUTS / "fwd"
OUT_JSON = OS.OUT_JSON                       # research/outputs/forward_oneshot.json
OUT_CURVE = OS.OUT_CURVE                     # research/outputs/forward_oneshot_curve.parquet
OUT_SUB_CURVE = RX.PATHS.OUTPUTS / "forward_oneshot_v34sub_curve.parquet"
OUT_FED_FRAC = FWD_DIR / "fed_frac_1h_fwd.parquet"
OUT_MD = RX.PATHS.OUTPUTS / "FORWARD_ONESHOT.md"

CORE_WEIGHT: float = float(FMA3_CONFIG["w_v7"])            # 0.70
SCALE: float = float(FMA3_CONFIG["global_scale"])   # 1.1
INITIAL: float = 10_000.0                            # house standard, FORWARD_TEST.md

#: Pre-registered bars (FORWARD_TEST.md, committed 2026-07-10 14:10).
F1_DD_CEIL = 0.209      # window worst-mark DD must be < 20.9%
F2_RET_FLOOR = -0.10    # window return must be > -10%
F4_SUB_FLOOR = -0.20    # each sub-book's own window return must be > -20%


# ---------------------------------------------------------------------------
# CPU etiquette
# ---------------------------------------------------------------------------
def wait_for_lock_chain(poll_sec: int = 60) -> None:
    """Block until the verify_record_engine_ext/eval_fma3_pin chain exits."""
    while True:
        r = subprocess.run(
            ["pgrep", "-f", "verify_record_engine|eval_fma3_pin"],
            capture_output=True, text=True)
        if r.returncode != 0:
            return
        print(f"[etiquette] lock chain running (pids {r.stdout.split()}) — "
              f"sleeping {poll_sec}s", flush=True)
        time.sleep(poll_sec)


# ---------------------------------------------------------------------------
# Timezone conversion (Duka TRUE UTC -> broker server time)
# ---------------------------------------------------------------------------
def to_server_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """tz-naive TRUE UTC -> tz-naive broker server time.

    The one sanctioned rule (FMA2 build_ext_cache.to_server, verified in
    research/fwd_cache_1m/MANIFEST.json): UTC -> tz_convert(America/New_York)
    + 7h -> naive. NY fall-back folds create duplicate server stamps; callers
    must dedup keep-last (the later UTC row is the fresher causal value).
    """
    return (idx.tz_localize("UTC").tz_convert("America/New_York")
            + pd.Timedelta(hours=7)).tz_localize(None)


def frame_to_server(obj: pd.DataFrame | pd.Series
                    ) -> tuple[pd.DataFrame | pd.Series, int]:
    """Convert a UTC-indexed frame/series to server time, dedup keep-last."""
    out = obj.copy()
    out.index = to_server_index(out.index)
    ndup = int(out.index.duplicated().sum())
    if ndup:
        out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()
    return out, ndup


# ---------------------------------------------------------------------------
# Native-curve loaders
# ---------------------------------------------------------------------------
def load_v7_native_inputs(seed: pd.Timestamp, slice_from: pd.Timestamp
                          ) -> tuple[pd.DataFrame, pd.Series, dict]:
    """v7 forward fraction matrix (server time, sliced) + native curve A.

    A = the band book's own forward equity ('eqc'), re-normalized to 1.0 at
    its first mark at/after ``seed`` (server) — the fresh-seed weighting
    curve of the locked construction.
    """
    utc_floor = slice_from - pd.Timedelta(hours=12)   # server leads UTC by 2-3h

    f_core = pd.read_parquet(FWD_DIR / "v7_book_frac_1h_fwd.parquet")
    f_core = f_core.loc[f_core.index >= utc_floor]
    f_core_s, dup_f = frame_to_server(f_core)
    f_core_s = f_core_s.loc[f_core_s.index >= slice_from]

    eq = pd.read_parquet(FWD_DIR / "v7_book_equity_1m_fwd.parquet")["eqc"]
    eq = eq.loc[eq.index >= utc_floor]
    eqs, dup_e = frame_to_server(eq)
    eqs = eqs.loc[eqs.index >= seed]
    if eqs.empty:
        raise ValueError(f"v7 native curve has no marks at/after {seed}")
    a = eqs / float(eqs.iloc[0])
    info = {
        "frac_rows": int(len(f_core_s)), "frac_span":
            [str(f_core_s.index[0]), str(f_core_s.index[-1])],
        "curve_first_mark": str(eqs.index[0]),
        "curve_last_mark": str(eqs.index[-1]),
        "curve_norm_base": float(eqs.iloc[0]),
        "fold_dups_dropped": {"frac": dup_f, "curve": dup_e},
        "source": "v7_book_{frac_1h,equity_1m}_fwd.parquet (TRUE UTC) -> server",
    }
    return f_core_s, a, info


def load_v34_forward_matrix(slice_from: pd.Timestamp) -> pd.DataFrame:
    """v3.4 forward fraction matrix (already server time), sliced."""
    f_sat = pd.read_parquet(FWD_DIR / "v34_frac_1h_fwd.parquet")
    if f_sat.index.tz is not None:
        raise ValueError("v34 forward matrix must be tz-naive server time")
    return f_sat.loc[f_sat.index >= slice_from]


# ---------------------------------------------------------------------------
# Instrumented engine copy (F3 measurement, bit-identity gated)
# ---------------------------------------------------------------------------
@njit(cache=True)
def _run_chunk_instr(tgt, has_bar, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
                     eurq, swap_l, swap_s,
                     contract, comm_side, leverage, lot_step, min_lot,
                     stop_out_level, margin_cap, rebalance_band,
                     balance0, lots0, entry0):
    """VERBATIM copy of record_engine_ext._run_chunk + event counters.

    Added statements (marked INSTR) only read already-computed values into
    counters/trackers; every floating-point statement of the original is
    unchanged and in the original order, so eq_c/eq_w are bit-identical.
    """
    T, K = tgt.shape
    balance = balance0
    lots = lots0.copy()
    entry = entry0.copy()
    eq_c = np.empty(T)
    eq_w = np.empty(T)
    n_trades = 0
    n_stopout = 0            # INSTR: joint stop-out liquidations
    n_capbind = 0            # INSTR: minutes the 0.9 margin cap bound sizing
    max_marginfrac = 0.0     # INSTR: max realized margin_used / balance
    min_marginlvl = 1e300    # INSTR: min eq_w / margin_used (stop-out < 0.5)

    for t in range(T):
        # 1. swaps at the rollover minute
        for k in range(K):
            if lots[k] != 0.0 and (swap_l[t, k] != 0.0 or swap_s[t, k] != 0.0):
                mid = 0.5 * (bid_o[t, k] + ask_o[t, k])
                notional = abs(lots[k]) * contract[k] * mid * eurq[t, k]
                balance += notional * (swap_l[t, k] if lots[k] > 0 else swap_s[t, k])

        # 2. desired lots from the shared balance
        desired = np.zeros(K)
        margin_sum = 0.0
        for k in range(K):
            g = tgt[t, k]
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
            n_capbind += 1                                        # INSTR

        # 3. execute fills (cross the spread), with rebalance band
        for k in range(K):
            if not has_bar[t, k]:
                continue
            want = desired[k] * shrink
            n = np.floor(abs(want) / lot_step[k] + 1e-9)
            want = np.sign(want) * n * lot_step[k]
            if abs(want) < min_lot[k]:
                want = 0.0
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
                balance += pnl - comm_side[k] * abs(close_lots)
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
                balance -= comm_side[k] * abs(add)
                lots[k] = want
                n_trades += 1

        # 4. joint marks (co-timed at this minute)
        unreal_c = 0.0
        unreal_w = 0.0
        margin_used = 0.0
        for k in range(K):
            if lots[k] == 0.0:
                continue
            if lots[k] > 0:
                unreal_c += (bid_c[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                unreal_w += (bid_l[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
            else:
                unreal_c += (ask_c[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                unreal_w += (ask_h[t, k] - entry[k]) * lots[k] * contract[k] * eurq[t, k]
            mid_c = 0.5 * (bid_c[t, k] + ask_c[t, k])
            margin_used += abs(lots[k]) * contract[k] * mid_c * eurq[t, k] / leverage[k]
        eq_c[t] = balance + unreal_c
        eq_w[t] = balance + unreal_w

        if margin_used > 0.0:                                     # INSTR
            mf = margin_used / balance                            # INSTR
            if mf > max_marginfrac:                               # INSTR
                max_marginfrac = mf                               # INSTR
            lvl = eq_w[t] / margin_used                           # INSTR
            if lvl < min_marginlvl:                               # INSTR
                min_marginlvl = lvl                               # INSTR

        # 5. joint stop-out on the worst co-timed mark
        if margin_used > 0.0 and eq_w[t] < stop_out_level * margin_used:
            n_stopout += 1                                        # INSTR
            for k in range(K):
                if lots[k] == 0.0:
                    continue
                px = bid_l[t, k] if lots[k] > 0 else ask_h[t, k]
                pnl = (px - entry[k]) * lots[k] * contract[k] * eurq[t, k]
                balance += pnl - comm_side[k] * abs(lots[k])
                lots[k] = 0.0
                entry[k] = 0.0
            eq_c[t] = balance
            eq_w[t] = balance

    return (eq_c, eq_w, balance, lots, entry, n_trades,
            n_stopout, n_capbind, max_marginfrac, min_marginlvl)


def simulate_instrumented(pos: pd.DataFrame, *, initial: float,
                          start_quarter: str, end_quarter: str,
                          bar_files: Mapping[str, object] | None,
                          margin_cap: float = 0.9,
                          rebalance_band: float = 0.25
                          ) -> tuple[pd.Series, pd.Series, dict]:
    """Mirror of RX.simulate_account_1m_ext driving the instrumented kernel.

    Reuses the ext engine's own loaders (_resolve_bar_files/_native/_densify/
    _eurq_chunk/_swap_chunk) so the inputs are the same objects; only the
    kernel differs, and only by event counters. Returns the curves plus the
    event dict; the caller must assert bit-identity against the record run.
    """
    stop_out = float(core.S.ACCOUNT["stop_out_level"])
    if stop_out != 0.5:
        raise AssertionError(f"stop_out_level poisoned: {stop_out!r}")

    symbols = [c for c in pos.columns]
    crosses = sorted({RX._EUR_CROSS[core.S.INSTRUMENTS[s]["quote"]]
                      for s in symbols
                      if core.S.INSTRUMENTS[s]["quote"] != "EUR"})
    load_syms = list(dict.fromkeys(symbols + crosses))
    src = {s: RX._resolve_bar_files(s, bar_files) for s in load_syms}

    contract = np.array([core.S.INSTRUMENTS[s]["contract_size"] for s in symbols], float)
    comm = np.array([core.S.INSTRUMENTS[s]["commission_side"] for s in symbols], float)
    lev = np.array([core.S.INSTRUMENTS[s]["leverage"] for s in symbols], float)
    step = np.array([core.S.INSTRUMENTS[s]["lot_step"] for s in symbols], float)
    mlot = np.array([core.S.INSTRUMENTS[s]["min_lot"] for s in symbols], float)

    quarters = pd.period_range(start_quarter, end_quarter, freq="Q")
    balance = initial
    lots = np.zeros(len(symbols))
    entry = np.zeros(len(symbols))
    eqc_parts, eqw_parts, idx_parts = [], [], []
    ev = {"n_stopout": 0, "n_capbind": 0,
          "max_margin_over_balance": 0.0, "min_margin_level": None}

    for qp in quarters:
        qs, qe = qp.start_time, qp.end_time
        grids = []
        for s in load_syms:
            idx, _ = RX._native(src[s])
            lo = np.searchsorted(idx, np.int64(qs.value), side="left")
            hi = np.searchsorted(idx, np.int64(qe.value), side="right")
            grids.append(idx[lo:hi])
        grid_ns = np.unique(np.concatenate(grids))
        if grid_ns.size == 0:
            continue

        has = np.zeros((len(grid_ns), len(symbols)), dtype=np.bool_)
        f = {fl: np.zeros((len(grid_ns), len(symbols))) for fl in RX._FIELDS}
        for k, s in enumerate(symbols):
            hb, out = RX._densify(src[s], grid_ns)
            has[:, k] = hb
            for fl in RX._FIELDS:
                f[fl][:, k] = out[fl]
        close_mid = {}
        for c in crosses:
            _, out = RX._densify(src[c], grid_ns)
            close_mid[c] = 0.5 * (out["bid_c"] + out["ask_c"])

        eurq = RX._eurq_chunk(symbols, grid_ns, close_mid)
        swap_l, swap_s = RX._swap_chunk(symbols, grid_ns)

        gidx = pd.DatetimeIndex(grid_ns.astype("datetime64[ns]"))
        prev_hour = gidx.floor("h") - pd.Timedelta(hours=1)
        tgt = pos.reindex(prev_hour, method=None).to_numpy()
        tgt = np.nan_to_num(tgt, nan=0.0)

        (eqc, eqw, balance, lots, entry, _ntr,
         nso, ncb, mmf, mml) = _run_chunk_instr(
            tgt, has, f["bid_o"], f["ask_o"], f["bid_c"], f["ask_c"],
            f["bid_l"], f["ask_h"], eurq, swap_l, swap_s,
            contract, comm, lev, step, mlot,
            stop_out, float(margin_cap), float(rebalance_band),
            balance, lots, entry)
        eqc_parts.append(eqc)
        eqw_parts.append(eqw)
        idx_parts.append(gidx)
        ev["n_stopout"] += int(nso)
        ev["n_capbind"] += int(ncb)
        ev["max_margin_over_balance"] = max(ev["max_margin_over_balance"],
                                            float(mmf))
        if mml < 1e299:
            cur = ev["min_margin_level"]
            ev["min_margin_level"] = (float(mml) if cur is None
                                      else min(cur, float(mml)))

    idx = idx_parts[0].append(idx_parts[1:]) if len(idx_parts) > 1 else idx_parts[0]
    eq_c = pd.Series(np.concatenate(eqc_parts), index=idx, name="equity")
    eq_w = pd.Series(np.concatenate(eqw_parts), index=idx, name="worst")
    return eq_c, eq_w, ev


def run_record_with_events(pos: pd.DataFrame, *, quarters: tuple[str, str],
                           bar_files: Mapping[str, object] | None,
                           initial: float, label: str) -> dict:
    """Engine-of-record run + instrumented event pass, bit-identity gated."""
    wait_for_lock_chain()
    print(f"[run] {label}: record engine {quarters[0]}..{quarters[1]} "
          f"(initial €{initial:,.0f}) ...", flush=True)
    res = RX.run_record_ext(
        pos, start_quarter=quarters[0], end_quarter=quarters[1],
        bar_files=bar_files, initial=initial, label=label, verbose=True,
        run_bootstrap=False)
    print(f"[run] {label}: instrumented event pass ...", flush=True)
    eq_i, ew_i, ev = simulate_instrumented(
        pos, initial=initial, start_quarter=quarters[0],
        end_quarter=quarters[1], bar_files=bar_files)
    rec_c, rec_w = res["curves"]["equity"], res["curves"]["worst"]
    if not (rec_c.index.equals(eq_i.index)
            and np.array_equal(rec_c.to_numpy(), eq_i.to_numpy())
            and np.array_equal(rec_w.to_numpy(), ew_i.to_numpy())):
        dmax = float(np.abs(rec_c.to_numpy() - eq_i.to_numpy()).max())
        raise AssertionError(
            f"[{label}] instrumented kernel NOT bit-identical to the record "
            f"engine (max |d| {dmax:.3e}) — event counters are untrustworthy; "
            "aborting before any conclusion is drawn from them.")
    print(f"[run] {label}: bit-identity PASS; events {ev}", flush=True)
    res["events"] = ev
    return res


# ---------------------------------------------------------------------------
# Window metrics (on the truncated curve) + pre-registered bars
# ---------------------------------------------------------------------------
def window_metrics(eq_c: pd.Series, eq_w: pd.Series, initial: float,
                   window_end: pd.Timestamp) -> dict:
    """Official window metrics on the curve truncated at ``window_end``."""
    c = eq_c.loc[eq_c.index <= window_end]
    w = eq_w.loc[eq_w.index <= window_end]
    if c.empty:
        raise ValueError("truncated window is empty")
    peak = np.maximum.accumulate(c.to_numpy())
    dd_w = float(((peak - w.to_numpy()) / np.maximum(peak, 1e-9)).max())
    dd_c = float(((peak - c.to_numpy()) / np.maximum(peak, 1e-9)).max())
    daily = c.resample("1D").last().dropna()
    r = daily.pct_change().dropna()
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 2 else float("nan")
    m_last = daily.groupby(daily.index.to_period("M")).last()
    monthly, base = {}, initial
    for per, v in m_last.items():
        monthly[str(per)] = float(v / base - 1.0)
        base = float(v)
    return {
        "first_mark": str(c.index[0]), "last_mark": str(c.index[-1]),
        "window_return": float(c.iloc[-1] / initial - 1.0),
        "final_equity": float(c.iloc[-1]),
        "maxdd_worst": dd_w, "maxdd_close": dd_c,
        "sharpe_daily_annualized": sharpe,
        "monthly_returns": monthly,
        "n_days": int(len(daily)),
    }


def evaluate_bars(win: dict, events: dict, ret7: float, ret34: float) -> dict:
    """FORWARD_TEST.md F1-F4 + the pre-registered interpretation."""
    f1 = win["maxdd_worst"] < F1_DD_CEIL
    f2 = win["window_return"] > F2_RET_FLOOR
    f3 = (events["n_stopout"] == 0) and (events["n_capbind"] == 0)
    f4 = (ret7 > F4_SUB_FLOOR) and (ret34 > F4_SUB_FLOOR)
    if f1 and f2 and f3 and f4:
        verdict = "CONFIRM"
    elif not f3:
        verdict = "REJECT"
    else:
        verdict = "INVESTIGATE"
    return {
        "F1": {"bar": f"window worst-mark DD < {F1_DD_CEIL:.1%}",
               "value": win["maxdd_worst"], "pass": bool(f1)},
        "F2": {"bar": f"window return > {F2_RET_FLOOR:+.0%}",
               "value": win["window_return"], "pass": bool(f2)},
        "F3": {"bar": "no joint stop-out or margin-cap breach event",
               "value": {"n_stopout": events["n_stopout"],
                         "n_capbind": events["n_capbind"]},
               "pass": bool(f3)},
        "F4": {"bar": f"each sub-book window return > {F4_SUB_FLOOR:+.0%}",
               "value": {"v7_native": ret7, "v34_native": ret34},
               "pass": bool(f4)},
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Shared pipeline (dryrun and oneshot differ only in dates/feeds/sinks)
# ---------------------------------------------------------------------------
def run_pipeline(*, seed: pd.Timestamp, slice_from: pd.Timestamp,
                 window_end: pd.Timestamp, quarters: tuple[str, str],
                 bar_files: Mapping[str, object] | None,
                 label: str) -> dict:
    """Two-step native-curve blend run. Returns the full result bundle."""
    t0 = time.time()
    tradable = OS.fwd_tradable_symbols("drop")   # the 14 real Duka symbols

    # -- inputs -------------------------------------------------------------
    f_core_s, a_curve, v7_info = load_v7_native_inputs(seed, slice_from)
    f_sat_s = load_v34_forward_matrix(slice_from)
    core_frac, drop7 = OS.restrict_to_forward(f_core_s, tradable)
    sat_frac, drop34 = OS.restrict_to_forward(f_sat_s, tradable)

    # -- step 1: v3.4 native forward curve (alone run, (1-w)*E0 seed) --------
    sub_initial = (1.0 - CORE_WEIGHT) * INITIAL
    res34 = run_record_with_events(
        sat_frac, quarters=quarters, bar_files=bar_files,
        initial=sub_initial, label=f"{label}_v34_alone")
    b_curve = res34["curves"]["equity"] / float(
        res34["curves"]["equity"].iloc[0])

    # -- step 2: blend matrix + record run ------------------------------
    fed = OS.blend_static(core_frac, sat_frac, CORE_WEIGHT, a_curve, b_curve) * SCALE
    # internal consistency: at hours before both curves' first marks the
    # blend weights must be exactly (w, 1-w)
    h0 = fed.index[0]
    if h0 < min(a_curve.index[0], b_curve.index[0]):
        c7 = core_frac.reindex([h0]).reindex(columns=fed.columns,
                                         fill_value=0.0).fillna(0.0)
        c34 = sat_frac.reindex([h0]).reindex(columns=fed.columns,
                                           fill_value=0.0).fillna(0.0)
        chk = (c7 * CORE_WEIGHT + c34 * (1 - CORE_WEIGHT)) * SCALE
        if not np.allclose(chk.to_numpy(), fed.loc[[h0]].to_numpy(),
                           atol=1e-12):
            raise AssertionError("seed-row blend weights are not (w, 1-w)")
    resF = run_record_with_events(
        fed, quarters=quarters, bar_files=bar_files,
        initial=INITIAL, label=f"{label}_federation")

    # -- window metrics (truncated) ------------------------------------------
    winF = window_metrics(resF["curves"]["equity"], resF["curves"]["worst"],
                          INITIAL, window_end)
    win34 = window_metrics(res34["curves"]["equity"],
                           res34["curves"]["worst"], sub_initial, window_end)
    a_trunc = a_curve.loc[a_curve.index <= window_end]
    b_trunc = b_curve.loc[b_curve.index <= window_end]
    ret7 = float(a_trunc.iloc[-1] - 1.0)
    ret34 = float(b_trunc.iloc[-1] - 1.0)

    bars = evaluate_bars(winF, resF["events"], ret7, ret34)

    # house 20d-block breach bootstrap on the truncated window (short-window
    # flagged: ~85 daily obs)
    wait_for_lock_chain()
    breach = RX.worst_mark_breach(pd.DataFrame({
        "equity": resF["curves"]["equity"].loc[
            resF["curves"]["equity"].index <= window_end],
        "worst": resF["curves"]["worst"].loc[
            resF["curves"]["worst"].index <= window_end]}))

    bundle = {
        "label": label,
        "config_hash": config_hash(),
        "mechanism": {
            "construction": FMA3_CONFIG["construction"],
            "w_v7": CORE_WEIGHT, "scale": SCALE, "initial": INITIAL,
            "A": "v7 native forward curve (v7_book_equity_1m_fwd.parquet "
                 "eqc, UTC->server), renormalized to 1.0 at first mark >= "
                 f"{seed} server",
            "B": "v3.4 native forward curve (alone run of the v34 forward "
                 f"matrix through record_engine_ext, seed €{sub_initial:,.0f})",
        },
        "window": {"quarters": list(quarters), "seed": str(seed),
                   "metrics_truncated_at": str(window_end),
                   "engine_first_bar": str(resF["curves"]["equity"].index[0]),
                   "engine_last_bar": str(resF["curves"]["equity"].index[-1])},
        "bars": bars,
        "verdict": bars["verdict"],
        "metrics": {
            "federation_window": winF,
            "federation_events": resF["events"],
            "federation_breach_bootstrap_short_window": breach,
            "sub_v7_native_window_return": ret7,
            "sub_v34_native_window_return": ret34,
            "sub_v34_window": win34,
            "sub_v34_events": res34["events"],
            "engine_full_run_reference": {
                "note": "engine metrics over the FULL grid incl. the inert "
                        "post-window tail (positions zero); official window "
                        "numbers are the truncated block above",
                "federation": {k: resF[k] for k in
                               ("cagr", "sharpe", "maxdd_worst", "maxdd_close",
                                "final_equity", "n_trades", "quarterly")},
                "v34_alone": {k: res34[k] for k in
                              ("cagr", "sharpe", "maxdd_worst", "maxdd_close",
                               "final_equity", "n_trades", "quarterly")},
            },
        },
        "inputs": {"v7": v7_info,
                   "v34": {"rows": int(len(f_sat_s)),
                           "span": [str(f_sat_s.index[0]), str(f_sat_s.index[-1])]},
                   "v7_dropped": drop7, "v34_dropped": drop34,
                   "tradable": tradable,
                   "bar_files": ({k: str(v) for k, v in bar_files.items()}
                                 if bar_files else "IC canonical (dryrun)")},
        "runtime_sec": round(time.time() - t0, 1),
        "curves": {"federation": resF["curves"], "v34_alone": res34["curves"],
                   "fed_matrix": fed},
    }
    return bundle


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------
def strip_curves(bundle: dict) -> dict:
    return {k: v for k, v in bundle.items() if k != "curves"}


def write_markdown(bundle: dict, gate_hash: str, path: Path) -> None:
    b, m = bundle["bars"], bundle["metrics"]
    winF = m["federation_window"]
    mark = {True: "PASS", False: "FAIL"}
    lines = [
        "# FMA3-FWD — 2026H1 one-shot forward confirmation (CONSUMED)",
        "",
        f"**Verdict: {bundle['verdict']}** — FMA3 v1.0 "
        f"(config_hash `{bundle['config_hash']}`), static federation w=0.70, "
        "s=1.1, fresh €10,000 seed 2026-01-01, engine of record "
        "`engine/record_engine_ext.py` (verified bit-identical on 2020-25), "
        "Duka forward feed (`research/fwd_cache_1m/`), 14-symbol coverage, "
        "USA500 proxying USTEC. Criteria pre-registered in "
        f"`research/protocol/FORWARD_TEST.md` (sha256 `{gate_hash[:16]}…`) "
        "before any 2026 number existed; window metrics truncated at server "
        f"{bundle['window']['metrics_truncated_at']}.",
        "",
        "## Pre-registered bars (FORWARD_TEST.md — evaluated first, "
        "nothing else)",
        "",
        "| # | Bar | Value | Result |",
        "|---|---|---|---|",
        f"| F1 | {b['F1']['bar']} | {b['F1']['value']:.2%} | "
        f"{mark[b['F1']['pass']]} |",
        f"| F2 | {b['F2']['bar']} | {b['F2']['value']:+.2%} | "
        f"{mark[b['F2']['pass']]} |",
        f"| F3 | {b['F3']['bar']} | stop-outs {b['F3']['value']['n_stopout']}"
        f", cap-binds {b['F3']['value']['n_capbind']} | "
        f"{mark[b['F3']['pass']]} |",
        f"| F4 | {b['F4']['bar']} | v7 {b['F4']['value']['v7_native']:+.2%}, "
        f"v3.4 {b['F4']['value']['v34_native']:+.2%} | "
        f"{mark[b['F4']['pass']]} |",
        "",
        f"Pre-registered interpretation → **{bundle['verdict']}**.",
        "",
        "## Window metrics (2026-01-01 → 2026-04-30, server time)",
        "",
        f"- Window return: **{winF['window_return']:+.2%}** "
        f"(€10,000 → €{winF['final_equity']:,.0f})",
        f"- Worst-mark DD: **{winF['maxdd_worst']:.2%}** "
        f"(close-to-close {winF['maxdd_close']:.2%})",
        f"- Daily Sharpe (annualized, {winF['n_days']} days — wide error "
        f"bars): {winF['sharpe_daily_annualized']:.2f}",
        "- Monthly returns: "
        + ", ".join(f"{k} {v:+.2%}" for k, v in
                    winF["monthly_returns"].items()),
        f"- Sub-books (native curves): v7 "
        f"{m['sub_v7_native_window_return']:+.2%}, v3.4 "
        f"{m['sub_v34_native_window_return']:+.2%}",
        f"- Margin envelope: max margin/balance "
        f"{m['federation_events']['max_margin_over_balance']:.3f} "
        f"(cap 0.90), min margin level "
        f"{m['federation_events']['min_margin_level']} (stop-out at 0.50)",
        f"- Breach bootstrap (20d blocks, P(maxDD>30%), short-window "
        f"caveat): close {m['federation_breach_bootstrap_short_window'].get('breach_close')}, "
        f"worst {m['federation_breach_bootstrap_short_window'].get('breach_worst')}",
        "",
        "## Caveats (disclosed in advance, FORWARD_TEST.md)",
        "",
        "- 4 months ≈ 85 trading days — the bars are breakdown detectors, "
        "not performance targets.",
        "- Duka feed, not the IC dev feed (documented ~8pp CAGR_bd feed "
        "divergence on 2020-25); 14-symbol coverage — the v3.4 book runs at "
        "reduced breadth (mean 0.88x gross fraction of its uncovered legs "
        "zeroed; per-symbol disclosure in v34_frac_1h_fwd_report.json).",
        "- USTEC has no Duka feed: exposure carried on USA500 (corr 0.89, "
        "column-level proxy from the v7 extraction; v3.4's own USTEC leg "
        "zeroed). The proxy book is a directional confirmation, NOT the "
        "deployed book.",
        "- Swap carry = flat extension of last 2025 policy rates (verified "
        "at import, record_engine_ext.ASSUMED_2026H1_POLICY_RATES).",
        "- v3.4's native forward curve B required one pre-registered alone "
        "run of its matrix (two-step single consumption, documented in "
        "forward_oneshot.json).",
        "- Open positions at the window-end stamp are marked to market, not "
        "closed; the engine's post-window tail (flat book) is excluded from "
        "all official numbers.",
        "",
        "## Next step (per pre-registered interpretation)",
        "",
        {"CONFIRM": "- Proceed to MT5 demo deployment on the owner's machine "
                    "(the deployable arbiter).",
         "INVESTIGATE": "- NO deployment until the MT5 real-tick run "
                        "adjudicates; this result is reported as-is in the "
                        "whitepaper.",
         "REJECT": "- The locked scale is rejected; re-open H-FED-3 with the "
                   "forward evidence (new pre-registration, new ledger "
                   "entry)."}[bundle["verdict"]],
        "",
        "Source: `research/outputs/forward_oneshot.json` · curves: "
        "`forward_oneshot_curve.parquet`, "
        "`forward_oneshot_v34sub_curve.parquet` · fed matrix: "
        "`research/outputs/fwd/fed_frac_1h_fwd.parquet` · driver: "
        "`scripts/run_forward_oneshot_native.py` (native-curve variant; "
        "stock `run_forward_oneshot.py` gates + helpers reused).",
        "",
    ]
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------
def main_dryrun(out_dir: Path) -> int:
    """2025Q4 rehearsal: IC bars, fresh 2025-10-01 seed, scratch outputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    gate_hash = OS.gate_preregistration()
    OS.gate_oneshot()
    print(f"[dryrun] gates OK (FORWARD_TEST.md sha256 {gate_hash[:16]}…); "
          "validating 2026 bar-file mapping (no read of 2026 bars)", flush=True)
    files = OS.fwd_bar_files(OS.fwd_tradable_symbols("drop"), "drop")
    print(f"[dryrun] bar-file mapping OK ({len(files)} files exist)",
          flush=True)

    bundle = run_pipeline(
        seed=pd.Timestamp("2025-10-01"),
        slice_from=pd.Timestamp("2025-09-30"),
        window_end=pd.Timestamp("2025-12-31 23:59:59"),
        quarters=("2025Q4", "2025Q4"),
        bar_files=None,                      # IC canonical — 2025 data only
        label="DRYRUN_2025Q4")
    rep = strip_curves(bundle)
    rep["DRYRUN"] = ("2025Q4 plumbing rehearsal on the IC feed — NOT a "
                     "forward number; duka-signal positions executed on IC "
                     "bars, values gate nothing.")
    (out_dir / "forward_oneshot_DRYRUN.json").write_text(
        json.dumps(rep, indent=1, default=str))
    write_markdown(bundle, gate_hash, out_dir / "FORWARD_ONESHOT_DRYRUN.md")
    pd.DataFrame({"equity": bundle["curves"]["federation"]["equity"],
                  "worst": bundle["curves"]["federation"]["worst"]}
                 ).to_parquet(out_dir / "dryrun_fed_curve.parquet")
    print(f"\n[dryrun] DONE ({bundle['runtime_sec']}s) -> {out_dir}")
    print(f"[dryrun] 2025Q4 fed window return "
          f"{bundle['metrics']['federation_window']['window_return']:+.2%}, "
          f"DD {bundle['metrics']['federation_window']['maxdd_worst']:.2%}, "
          f"events {bundle['metrics']['federation_events']}")
    return 0


def main_oneshot() -> int:
    """The single gated consumption of the 2026H1 holdout."""
    gate_hash = OS.gate_preregistration()
    OS.gate_oneshot()
    bar_files = OS.fwd_bar_files(OS.fwd_tradable_symbols("drop"), "drop")
    print(f"[oneshot] gates passed (FORWARD_TEST.md sha256 {gate_hash[:16]}…) "
          f"— consuming the 2026H1 holdout NOW (one attempt).", flush=True)

    bundle = run_pipeline(
        seed=pd.Timestamp("2026-01-01"),
        slice_from=pd.Timestamp("2025-12-31"),
        window_end=pd.Timestamp("2026-04-30 23:59:59"),
        quarters=("2026Q1", "2026Q2"),
        bar_files=bar_files,
        label="fma3_v1_fwd_2026H1")

    manifest = json.loads((OS.FWD_1M / "MANIFEST.json").read_text())
    rep = strip_curves(bundle)
    rep["generated"] = pd.Timestamp.now().isoformat()
    rep["preregistration"] = {"file": str(OS.GATE_FILE), "sha256": gate_hash}
    rep["driver"] = ("scripts/run_forward_oneshot_native.py (native-curve "
                     "variant; stock run_forward_oneshot.py gates/helpers "
                     "reused; two-step single consumption: v34-alone native "
                     "curve then federation)")
    rep["data_end_summary"] = manifest.get("end_date_summary")
    rep["caveats"] = [
        "USA500 proxies USTEC (corr 0.89) at the column level; the proxy "
        "book is a directional confirmation, not the deployed book.",
        "14-symbol Duka coverage: v3.4 runs at reduced breadth (mean 0.88x "
        "gross of uncovered legs zeroed; see v34_frac_1h_fwd_report.json).",
        "Duka feed, not IC (documented ~8pp CAGR_bd 2020-25 divergence).",
        "Swap carry = flat extension of last 2025 policy rates.",
        "4 months — statistically weak by construction; bars are breakdown "
        "detectors.",
        "Window metrics truncated at server 2026-04-30 23:59:59; open "
        "positions marked, not closed; post-window engine tail is flat and "
        "excluded.",
    ]

    # persist artifacts (curves saved in full, incl. inert tail)
    pd.DataFrame({"equity": bundle["curves"]["federation"]["equity"],
                  "worst": bundle["curves"]["federation"]["worst"]}
                 ).to_parquet(OUT_CURVE)
    pd.DataFrame({"equity": bundle["curves"]["v34_alone"]["equity"],
                  "worst": bundle["curves"]["v34_alone"]["worst"]}
                 ).to_parquet(OUT_SUB_CURVE)
    bundle["curves"]["fed_matrix"].to_parquet(OUT_FED_FRAC)
    OUT_JSON.write_text(json.dumps(rep, indent=1, default=str))
    write_markdown(bundle, gate_hash, OUT_MD)

    b = bundle["bars"]
    print("\n" + "=" * 72)
    print(f"[oneshot] VERDICT: {bundle['verdict']}")
    for f in ("F1", "F2", "F3", "F4"):
        print(f"  {f}: {'PASS' if b[f]['pass'] else 'FAIL'}  "
              f"({b[f]['bar']} — value {b[f]['value']})")
    w = bundle["metrics"]["federation_window"]
    print(f"  window return {w['window_return']:+.2%} | worst-mark DD "
          f"{w['maxdd_worst']:.2%} | monthly "
          + ", ".join(f"{k}:{v:+.1%}" for k, v in
                      w["monthly_returns"].items()))
    print(f"  sub-books: v7 {bundle['metrics']['sub_v7_native_window_return']:+.2%}"
          f" | v3.4 {bundle['metrics']['sub_v34_native_window_return']:+.2%}")
    print(f"  -> {OUT_JSON}\n  -> {OUT_MD}")
    print("The 2026H1 holdout is now CONSUMED. Log FMA3-FWD in "
          "docs/REGISTRY.md and flip the holdout counter.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "dryrun":
        if len(sys.argv) != 3:
            sys.exit("usage: run_forward_oneshot_native.py dryrun <out_dir>")
        sys.exit(main_dryrun(Path(sys.argv[2])))
    elif len(sys.argv) == 2 and sys.argv[1] == "oneshot":
        sys.exit(main_oneshot())
    else:
        sys.exit("usage: run_forward_oneshot_native.py dryrun <out_dir> | oneshot")
