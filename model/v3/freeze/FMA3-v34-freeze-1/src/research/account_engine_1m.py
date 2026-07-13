"""True 1-minute single cross-margined account engine (v1.1.1 validation).

The v1.1 engine runs on hourly execution bars. This runs the SAME single-account
logic on the raw 1-minute IC feed, to (a) confirm the CAGR isn't inflated by the
hourly rebalance cadence and (b) replace the pessimistic hourly sum-of-worst
drawdown with a true co-timed minute-level worst mark.

Memory-safe by construction: instrument 1m arrays are held at native length; the
account is run quarter-by-quarter on each chunk's union grid, chaining state
(balance, lots, entry) across chunks. Targets are pre-shifted so every bar is
self-contained — the hour-h signal is held over hour h+1's minutes, executed at
the first minute's open (causal, ≥1-minute gap).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

import core

SRC = Path("/Users/dsalamanca/vs_env/NewStrategyFable5/cache/bars_1m_ic")
_FILE = {s: f"{s}_IC_1m.parquet" for s in core.ALL}
_FIELDS = ("bid_o", "ask_o", "bid_c", "ask_c", "bid_l", "ask_h")
_EUR_CROSS = {"USD": "EURUSD", "JPY": "EURJPY", "GBP": "EURGBP", "CHF": "EURCHF",
              "NZD": "EURNZD", "CAD": "EURCAD", "NOK": "EURNOK", "SEK": "EURSEK"}


@lru_cache(maxsize=64)
def _native(sym: str):
    """Native 1m arrays for one instrument: int64-ns index + float32 fields."""
    df = pd.read_parquet(SRC / _FILE[sym], columns=list(_FIELDS))
    idx = df.index.values.astype("datetime64[ns]").astype(np.int64)
    arrs = {f: df[f].to_numpy(np.float32) for f in _FIELDS}
    return idx, arrs


def _densify(sym: str, grid_ns: np.ndarray):
    """Map an instrument's native bars onto a union grid: ffilled fields +
    has_bar mask (True only where the instrument actually has that minute)."""
    idx, arrs = _native(sym)
    j = np.searchsorted(idx, grid_ns, side="right") - 1      # last bar ≤ t
    has = (j >= 0) & (idx[np.clip(j, 0, len(idx) - 1)] == grid_ns)
    jc = np.clip(j, 0, len(idx) - 1)
    out = {f: arrs[f][jc].astype(np.float64) for f in _FIELDS}
    pre = j < 0                                              # before first bar
    if pre.any():
        for f in _FIELDS:
            out[f][pre] = arrs[f][0]
    return has, out


def _eurq_chunk(symbols, grid_ns, close_mid):
    """EUR value of 1 quote unit per instrument, on the chunk grid."""
    out = np.ones((len(grid_ns), len(symbols)))
    for k, s in enumerate(symbols):
        q = core.S.INSTRUMENTS[s]["quote"]
        if q == "EUR":
            continue
        out[:, k] = 1.0 / close_mid[_EUR_CROSS[q]]
    return out


def _swap_chunk(symbols, grid_ns):
    """Swap accrual (long, short) placed at the first minute ≥ server-midnight
    of each day, on the chunk grid."""
    la = np.zeros((len(grid_ns), len(symbols)))
    sa = np.zeros((len(grid_ns), len(symbols)))
    d0 = pd.Timestamp(grid_ns[0]).normalize()
    d1 = pd.Timestamp(grid_ns[-1]).normalize() + pd.Timedelta(days=1)
    days = pd.date_range(d0, d1, freq="D")
    for k, s in enumerate(symbols):
        ac = core.S.INSTRUMENTS[s]["asset_class"]
        for d in days:
            if ac != "crypto" and d.weekday() >= 5:
                continue
            m = np.int64(d.value)
            j = int(np.searchsorted(grid_ns, m, side="left"))
            if j >= len(grid_ns):
                continue
            mult = core.engine_costs.swap_day_multiplier(s, d)
            lp, sp = core.engine_costs.swap_annual_pct(s, d)
            la[j, k] += lp / 100.0 / 365.0 * mult
            sa[j, k] += sp / 100.0 / 365.0 * mult
    return la, sa


@njit(cache=True)
def _run_chunk(tgt, has_bar, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
               eurq, swap_l, swap_s,
               contract, comm_side, leverage, lot_step, min_lot,
               stop_out_level, margin_cap, rebalance_band,
               balance0, lots0, entry0):
    """Single cross-margined account over one chunk. tgt[t,k] = target notional
    fraction of joint equity to HOLD over bar t (already lagged by the caller).
    Returns close/worst equity for the chunk + carry state."""
    T, K = tgt.shape
    balance = balance0
    lots = lots0.copy()
    entry = entry0.copy()
    eq_c = np.empty(T)
    eq_w = np.empty(T)
    n_trades = 0

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

        # 5. joint stop-out on the worst co-timed mark
        if margin_used > 0.0 and eq_w[t] < stop_out_level * margin_used:
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

    return eq_c, eq_w, balance, lots, entry, n_trades


def simulate_account_1m(pos: pd.DataFrame, *, initial: float = 10_000.0,
                        margin_cap: float = 0.9, rebalance_band: float = 0.25,
                        verbose: bool = True):
    """Run `pos` (hourly target matrix) through the true-1m single account."""
    symbols = [c for c in pos.columns]
    crosses = sorted({_EUR_CROSS[core.S.INSTRUMENTS[s]["quote"]]
                      for s in symbols
                      if core.S.INSTRUMENTS[s]["quote"] != "EUR"})
    load_syms = list(dict.fromkeys(symbols + crosses))

    contract = np.array([core.S.INSTRUMENTS[s]["contract_size"] for s in symbols], float)
    comm = np.array([core.S.INSTRUMENTS[s]["commission_side"] for s in symbols], float)
    lev = np.array([core.S.INSTRUMENTS[s]["leverage"] for s in symbols], float)
    step = np.array([core.S.INSTRUMENTS[s]["lot_step"] for s in symbols], float)
    mlot = np.array([core.S.INSTRUMENTS[s]["min_lot"] for s in symbols], float)
    stop_out = float(core.S.ACCOUNT["stop_out_level"])

    quarters = pd.period_range("2020Q1", "2025Q4", freq="Q")
    balance = initial
    lots = np.zeros(len(symbols))
    entry = np.zeros(len(symbols))
    eqc_parts, eqw_parts, idx_parts = [], [], []
    total_trades = 0

    for qp in quarters:
        qs, qe = qp.start_time, qp.end_time
        # chunk union grid = union of all load_syms' minutes in [qs, qe]
        grids = []
        for s in load_syms:
            idx, _ = _native(s)
            lo = np.searchsorted(idx, np.int64(qs.value), side="left")
            hi = np.searchsorted(idx, np.int64(qe.value), side="right")
            grids.append(idx[lo:hi])
        grid_ns = np.unique(np.concatenate(grids))
        if grid_ns.size == 0:
            continue

        # densify traded instruments + eur crosses
        has = np.zeros((len(grid_ns), len(symbols)), dtype=np.bool_)
        f = {fl: np.zeros((len(grid_ns), len(symbols))) for fl in _FIELDS}
        for k, s in enumerate(symbols):
            hb, out = _densify(s, grid_ns)
            has[:, k] = hb
            for fl in _FIELDS:
                f[fl][:, k] = out[fl]
        close_mid = {}
        for c in crosses:
            _, out = _densify(c, grid_ns)
            close_mid[c] = 0.5 * (out["bid_c"] + out["ask_c"])

        eurq = _eurq_chunk(symbols, grid_ns, close_mid)
        swap_l, swap_s = _swap_chunk(symbols, grid_ns)

        # target held over each minute = hourly signal from the PREVIOUS hour
        gidx = pd.DatetimeIndex(grid_ns.astype("datetime64[ns]"))
        prev_hour = gidx.floor("h") - pd.Timedelta(hours=1)
        tgt = pos.reindex(prev_hour, method=None).to_numpy()
        tgt = np.nan_to_num(tgt, nan=0.0)

        eqc, eqw, balance, lots, entry, ntr = _run_chunk(
            tgt, has, f["bid_o"], f["ask_o"], f["bid_c"], f["ask_c"],
            f["bid_l"], f["ask_h"], eurq, swap_l, swap_s,
            contract, comm, lev, step, mlot,
            stop_out, float(margin_cap), float(rebalance_band),
            balance, lots, entry)
        eqc_parts.append(eqc)
        eqw_parts.append(eqw)
        idx_parts.append(gidx)
        total_trades += ntr
        if verbose:
            print(f"  {qp}: {len(grid_ns):>7,} min | bal €{balance:,.0f} "
                  f"| trades {ntr:,}", flush=True)

    idx = idx_parts[0].append(idx_parts[1:]) if len(idx_parts) > 1 else idx_parts[0]
    eq_c = pd.Series(np.concatenate(eqc_parts), index=idx, name="equity")
    eq_w = pd.Series(np.concatenate(eqw_parts), index=idx, name="worst")
    m = core.compute_metrics(eq_c / initial)
    peak = np.maximum.accumulate(eq_c.to_numpy())
    m["maxdd"] = float(((peak - eq_w.to_numpy()) / np.maximum(peak, 1e-9)).max())
    m["final_equity"] = float(eq_c.iloc[-1])
    m["n_trades"] = int(total_trades)
    return eq_c, eq_w, m


if __name__ == "__main__":
    print("1m single-account engine module OK")
