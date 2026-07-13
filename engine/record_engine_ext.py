"""FMA3-owned generalization of FMA2's true 1-minute account engine.

WHY THIS FILE EXISTS (and why record_engine.py is not enough)
-------------------------------------------------------------
``record_engine.run_record`` wraps FMA2's verified
``research/account_engine_1m.py::simulate_account_1m`` by import, which is the
right call for every 2020-2025 number: the FMA2 copy is the pinned, verified
artifact. But that engine hardcodes two things the 2026H1 ONE-SHOT forward
confirmation (PROTOCOL.md paragraph 4) cannot live with, and FMA2 is read-only
so they cannot be parameterized in place:

1. ``quarters = pd.period_range("2020Q1", "2025Q4")``   (source line 228);
2. ``SRC = NSF5/cache/bars_1m_ic`` + ``{s}_IC_1m.parquet``  (lines 25-26) —
   the IC feed ends 2025-12-31; 2026H1 exists only as converted Duka bars.

This module is a FAITHFUL COPY of that engine, generalized minimally:

* SOURCE COPIED: /Users/dsalamanca/vs_env/FableMultiAssets2/research/
  account_engine_1m.py (mtime 2026-07-xx, the file that produced the pinned
  v34_s10_pin_1m.json). Line map of the copied units:
    - ``_native``            <- lines 32-38   (generalized to a path tuple)
    - ``_densify``           <- lines 41-53   (unchanged logic)
    - ``_eurq_chunk``        <- lines 56-64   (unchanged)
    - ``_swap_chunk``        <- lines 67-88   (unchanged)
    - ``_run_chunk``         <- lines 91-208  (VERBATIM, same numba njit)
    - ``simulate_account_1m``<- lines 211-292 (quarter range + bar source
                                               parameterized; arithmetic,
                                               loop order, metric tail
                                               unchanged)
* Every floating-point statement is kept in the original order so a run over
  the default range/source is BIT-IDENTICAL to FMA2's engine (gate enforced
  by scripts/verify_record_engine_ext.py against the pinned curve + metrics).

WHAT IS GENERALIZED
-------------------
(a) ``start_quarter``/``end_quarter`` — arbitrary calendar-quarter range
    (default 2020Q1..2025Q4 = the FMA2 behaviour). 2026 quarters are legal:
    that is the whole point.
(b) ``bar_files`` — per-symbol bar-source override, mapping symbol ->
    parquet path or ordered sequence of paths (concatenated, de-duplicated
    keep-first, sorted). Every file must be IC-schema (bid/ask OHLC + n_ticks)
    with a tz-naive broker-SERVER-time index. The 2026H1 forward cache built
    by scripts/build_fwd_cache.py (Duka UTC -> server time) plugs in here.
    Symbols absent from the mapping fall back to the canonical IC path —
    so a mixed run (IC 2020-2025 history + fwd 2026 tail per symbol) is
    expressed as ``{sym: (IC_path, fwd_path)}``.
(c) Swap rates through 2026-06 — see the section below.

SWAP-RATE EXTENSION THROUGH 2026-06 (documented assumption)
-----------------------------------------------------------
Swaps come from NSF5 ``engine/costs.py``: central-bank policy-rate STEP TABLES
(``POLICY_RATES``) + constant broker markups. The step-function lookup
``policy_rate(ccy, ts)`` returns the last entry whose effective date <= ts,
so any date after the final entry ALREADY resolves to the last known rate —
i.e. the table semantics natively extend the last policy rate FORWARD FLAT.
The last encoded decisions are all in 2025 (USD 3.625 eff 2025-12-11, EUR 2.00
eff 2025-06-11, GBP 3.75 eff 2025-12-18, JPY 0.50, CHF 0.00, AUD 3.60,
NZD 2.25, CAD 2.75, NOK 4.00, SEK 2.00; metals/energy 0; crypto flat -20%/0%;
index markup constant), so for 2026H1 this module ASSUMES NO 2026 POLICY
CHANGES: each currency's swap carry is the flat extension of its last 2025
rate. The residual error of a missed 25-50bp decision is second-order next to
the 1.2-4.3%/yr broker markups that dominate the swap. Because FMA2/NSF5 are
read-only we do not edit the tables; instead ``_verify_swap_flat_extension``
(run at import) asserts, for every currency, that the upstream lookup really
returns the documented last-known rate on probe dates through 2026-06-30 —
if anyone ever changes the upstream semantics (e.g. adds an end-of-table
error), this module fails LOUDLY instead of silently mispricing carry.

INPUT CONVENTION (unchanged from FMA2)
--------------------------------------
``pos``: hourly matrix of signed notional exposure as a fraction of joint
account equity, tz-naive broker SERVER time index. The hour-h row is held
over hour h+1's minutes (``prev_hour = minute.floor('h') - 1h``), executing
at h+1's first traded minute's open — a >=1-minute causal gap. Scale and
hard limits must already be baked in by the caller.

FORWARD-WINDOW GUARDS (new, error out instead of silently drifting)
-------------------------------------------------------------------
* EUR-conversion crosses: if a needed cross's bar source ends BEFORE a
  requested quarter starts, every EUR conversion in that quarter would
  silently freeze at the last known rate (the exact defect NSF5 audited on
  2026-07-02 in costs.FxConverter). We raise instead: give the cross a
  ``bar_files`` entry that covers the window.
* stop_out_level must be the production 0.50. NSF5's v7 stack (lock_v5 import
  side-effect) sets it to 1e-9 in-process; running the record engine in a
  process poisoned that way would disable the joint stop-out. Asserted per run.

FTMO DAILY CIRCUIT BREAKER (FMA3-008, ``daily_stop_x``)
-------------------------------------------------------
``daily_stop_x`` (percent; ``None`` = off, the default) arms an FTMO-preset
execution guard inside the minute loop (H-FTMO-1, ROADMAP.md):

* day-anchor = the PREVIOUS server-day's closing equity (close-mark equity of
  the previous calendar day's last minute, server time); day 1's anchor is
  ``initial``. Server days are calendar days of the bar grid — weekends with
  only crypto bars are their own server days, matching the 1D-resample
  convention of the FTMO scorers.
* when the minute's co-timed WORST-mark equity <= anchor * (1 - x/100): all
  positions are closed AT THAT MINUTE'S WORST-SIDE PRICES (bid_l for longs,
  ask_h for shorts — the same prices the worst mark and the joint stop-out
  use), paying commission per lot; the crossing minute's recorded
  equity/worst both become the post-flatten balance.
* targets are forced to zero (no re-entry) until the first minute of the
  next server day, when the book re-opens from the ``pos`` matrix, paying
  the full book's spreads again (the re-entry cost the FMA3-008 scoring
  measures as pp CAGR vs the no-breaker cell).

GAP-THROUGH SEMANTICS (honest physics, pre-stated): the trigger is evaluated
on 1-minute worst marks, so the crossing minute's worst mark can ALREADY be
far below the stop level — a 1m bar can jump straight through x% past the 5%
FTMO daily limit. The stop TRUNCATES the daily-loss tail at
(x% + the crossing minute's overshoot + commissions); it does not eliminate
it. The residual >5%-dip days left in the stopped curve are exactly what the
FMA3-008 scoring measures (score_v3 historical block + raw-frame scan).

``daily_stop_x=None`` routes through the UNTOUCHED original ``_run_chunk``
kernel (bit-identity with the no-stop engine is structural); any float x uses
``_run_chunk_stop``, a verbatim copy whose extra branches never fire when the
stop never triggers — gated bit-identical at x=10.0 on the FTMO ship config
by scripts/run_hftmo1.py before any FMA3-008 number.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from numba import njit

# Sibling import bootstrap (FMA3/engine is deliberately NOT a package — see
# record_engine.py on the NSF5 `engine`/`config` name collision). Importing
# record_engine also puts FMA2 core on sys.path and loads fma3 paths.
_ENGINE_DIR = str(Path(__file__).resolve().parent)
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
import record_engine as _RE            # noqa: E402  (bootstrap + PATHS)

import core                            # noqa: E402  FMA2 research core

PATHS = _RE.PATHS
worst_mark_breach = _RE.worst_mark_breach   # house bootstrap, same object

__all__ = ["simulate_account_1m_ext", "run_record_ext", "PATHS",
           "worst_mark_breach", "SWAP_EXTENSION_END", "BASE_QUARTERS"]

# ---------------------------------------------------------------------------
# Constants copied from FMA2 account_engine_1m.py lines 25-29
# ---------------------------------------------------------------------------
_IC_SRC = PATHS.BARS_1M_IC                       # NSF5/cache/bars_1m_ic
_FIELDS = ("bid_o", "ask_o", "bid_c", "ask_c", "bid_l", "ask_h")
_EUR_CROSS = {"USD": "EURUSD", "JPY": "EURJPY", "GBP": "EURGBP",
              "CHF": "EURCHF", "NZD": "EURNZD", "CAD": "EURCAD",
              "NOK": "EURNOK", "SEK": "EURSEK"}

# The range FMA2 hardcodes (its full data sample); kept as the default so the
# zero-argument behaviour of this engine IS the FMA2 engine.
BASE_QUARTERS = ("2020Q1", "2025Q4")

# ---------------------------------------------------------------------------
# Swap-rate flat extension through 2026H1 (see module docstring)
# ---------------------------------------------------------------------------
SWAP_EXTENSION_END = pd.Timestamp("2026-06-30")


def _verify_swap_flat_extension() -> dict[str, float]:
    """Assert NSF5's policy-rate lookup flat-extends every currency to 2026-06.

    WHY: the 2026H1 forward window prices swaps beyond the last encoded policy
    decision. The upstream step-table lookup extends the last rate forward by
    construction; this check pins that behaviour (and the documented
    'no 2026 policy changes' assumption) so an upstream edit cannot silently
    change forward carry. Returns {ccy: assumed 2026H1 rate} for reporting.
    """
    ec = core.engine_costs
    assumed: dict[str, float] = {}
    probes = (pd.Timestamp("2026-01-02"), pd.Timestamp("2026-03-31"),
              SWAP_EXTENSION_END)
    for ccy, table in ec.POLICY_RATES.items():
        last_eff, last_rate = pd.Timestamp(table[-1][0]), float(table[-1][1])
        if last_eff > pd.Timestamp("2025-12-31"):
            raise AssertionError(
                f"POLICY_RATES[{ccy!r}] now contains a 2026 entry "
                f"({last_eff.date()}): the flat-extension documentation in "
                "record_engine_ext.py is stale — re-derive and re-verify.")
        for ts in probes:
            got = float(ec.policy_rate(ccy, ts))
            if got != last_rate:
                raise AssertionError(
                    f"policy_rate({ccy!r}, {ts.date()}) = {got}, expected the "
                    f"flat-extended last known rate {last_rate} (eff "
                    f"{last_eff.date()}). Upstream semantics changed — the "
                    "2026H1 swap extension assumption no longer holds.")
        assumed[ccy] = last_rate
    return assumed


#: Rates assumed to hold flat over 2026H1 (verified against NSF5 at import).
ASSUMED_2026H1_POLICY_RATES: dict[str, float] = _verify_swap_flat_extension()


# ---------------------------------------------------------------------------
# Bar loading — FMA2 _native (lines 32-38) generalized to a path tuple
# ---------------------------------------------------------------------------
def _resolve_bar_files(sym: str,
                       bar_files: Mapping[str, object] | None
                       ) -> tuple[str, ...]:
    """Resolve a symbol to its ordered tuple of bar parquet paths.

    Fallback (symbol not in the mapping) is the canonical IC file — so the
    default run reads exactly what FMA2's engine reads.
    """
    if bar_files is not None and sym in bar_files:
        v = bar_files[sym]
        if isinstance(v, (str, Path)):
            paths: Iterable[Path] = (Path(v),)
        else:
            paths = tuple(Path(p) for p in v)
        out = tuple(str(p) for p in paths)
        if not out:
            raise ValueError(f"bar_files[{sym!r}] is empty")
    else:
        out = (str(_IC_SRC / f"{sym}_IC_1m.parquet"),)
    for p in out:
        if not Path(p).exists():
            raise FileNotFoundError(f"bar source for {sym}: {p}")
    return out


@lru_cache(maxsize=128)
def _native(files: tuple[str, ...]):
    """Native 1m arrays for one instrument: int64-ns index + float32 fields.

    Single file: byte-for-byte the FMA2 load path (read the six fields,
    int64 index, float32 arrays — copied from account_engine_1m.py:32-38).
    Multiple files: concatenated in the given order, duplicate stamps dropped
    keep-FIRST (the earlier file wins — history files take precedence over a
    forward tail on any overlap), then sorted. The single-file path applies
    no sort/dedup, exactly like FMA2 (its IC parquets are already clean).
    """
    if len(files) == 1:
        df = pd.read_parquet(files[0], columns=list(_FIELDS))
    else:
        parts = [pd.read_parquet(f, columns=list(_FIELDS)) for f in files]
        df = pd.concat(parts)
        df = df[~df.index.duplicated(keep="first")].sort_index()
    idx = df.index.values.astype("datetime64[ns]").astype(np.int64)
    arrs = {f: df[f].to_numpy(np.float32) for f in _FIELDS}
    return idx, arrs


def _densify(files: tuple[str, ...], grid_ns: np.ndarray):
    """Map an instrument's native bars onto a union grid: ffilled fields +
    has_bar mask (True only where the instrument actually has that minute).

    Copied from account_engine_1m.py:41-53 (only the cache key changed)."""
    idx, arrs = _native(files)
    j = np.searchsorted(idx, grid_ns, side="right") - 1      # last bar <= t
    has = (j >= 0) & (idx[np.clip(j, 0, len(idx) - 1)] == grid_ns)
    jc = np.clip(j, 0, len(idx) - 1)
    out = {f: arrs[f][jc].astype(np.float64) for f in _FIELDS}
    pre = j < 0                                              # before first bar
    if pre.any():
        for f in _FIELDS:
            out[f][pre] = arrs[f][0]
    return has, out


def _eurq_chunk(symbols, grid_ns, close_mid):
    """EUR value of 1 quote unit per instrument, on the chunk grid.
    Copied verbatim from account_engine_1m.py:56-64."""
    out = np.ones((len(grid_ns), len(symbols)))
    for k, s in enumerate(symbols):
        q = core.S.INSTRUMENTS[s]["quote"]
        if q == "EUR":
            continue
        out[:, k] = 1.0 / close_mid[_EUR_CROSS[q]]
    return out


def _swap_chunk(symbols, grid_ns):
    """Swap accrual (long, short) placed at the first minute >= server-midnight
    of each day, on the chunk grid.

    Copied verbatim from account_engine_1m.py:67-88. For 2026 dates the
    engine_costs lookups resolve to the flat-extended last known policy rates
    (verified at import — see ASSUMED_2026H1_POLICY_RATES)."""
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


# ---------------------------------------------------------------------------
# Numba core — VERBATIM copy of account_engine_1m.py:91-208. Any edit here
# (other than this comment) breaks bit-identity with the engine of record.
# ---------------------------------------------------------------------------
@njit(cache=True)
def _run_chunk(tgt, has_bar, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
               eurq, swap_l, swap_s,
               contract, comm_side, leverage, lot_step, min_lot, vol_limit,
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


# ---------------------------------------------------------------------------
# FMA3-008 kernel — VERBATIM copy of _run_chunk plus the daily circuit
# breaker (module docstring, "FTMO DAILY CIRCUIT BREAKER"). The additions are
# strictly branch-guarded: when the stop never fires (and halted stays False)
# every pre-existing floating-point statement executes in the original order,
# so an unfired stop is bit-identical to _run_chunk (gate: run_hftmo1.py).
# ---------------------------------------------------------------------------
@njit(cache=True)
def _run_chunk_stop(tgt, has_bar, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
                    eurq, swap_l, swap_s,
                    contract, comm_side, leverage, lot_step, min_lot, vol_limit,
                    stop_out_level, margin_cap, rebalance_band,
                    balance0, lots0, entry0,
                    day_id, stop_frac, anchor0, last_close0, cur_day0,
                    halted0):
    """_run_chunk + FTMO daily stop. day_id[t] = server-day ordinal of minute
    t; anchor/last_close/cur_day/halted carry across chunk boundaries.
    Returns the _run_chunk tuple + (anchor, last_close, cur_day, halted,
    n_stops)."""
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

    for t in range(T):
        # 0. server-day rollover: re-anchor at prev day's close, lift halt
        if day_id[t] != cur_day:
            anchor = last_close
            halted = False
            cur_day = day_id[t]

        # 1. swaps at the rollover minute
        for k in range(K):
            if lots[k] != 0.0 and (swap_l[t, k] != 0.0 or swap_s[t, k] != 0.0):
                mid = 0.5 * (bid_o[t, k] + ask_o[t, k])
                notional = abs(lots[k]) * contract[k] * mid * eurq[t, k]
                balance += notional * (swap_l[t, k] if lots[k] > 0 else swap_s[t, k])

        # 2. desired lots from the shared balance (halt forces zero targets)
        desired = np.zeros(K)
        margin_sum = 0.0
        for k in range(K):
            g = tgt[t, k]
            if halted:
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
                balance += pnl - comm_side[k] * abs(lots[k])
                lots[k] = 0.0
                entry[k] = 0.0
            eq_c[t] = balance
            eq_w[t] = balance

        last_close = eq_c[t]

    return (eq_c, eq_w, balance, lots, entry, n_trades,
            anchor, last_close, cur_day, halted, n_stops)


# ---------------------------------------------------------------------------
# Driver — account_engine_1m.py:211-292 with quarter range + bar source
# parameterized. Arithmetic and loop order unchanged.
# ---------------------------------------------------------------------------
def simulate_account_1m_ext(pos: pd.DataFrame, *, initial: float = 10_000.0,
                            margin_cap: float = 0.9,
                            rebalance_band: float = 0.25,
                            start_quarter: str = BASE_QUARTERS[0],
                            end_quarter: str = BASE_QUARTERS[1],
                            bar_files: Mapping[str, object] | None = None,
                            daily_stop_x: float | None = None,
                            volume_limit: Mapping[str, float] | None = None,
                            verbose: bool = True):
    """Run ``pos`` (hourly target matrix) through the true-1m single account.

    Generalized copy of FMA2 account_engine_1m.simulate_account_1m (lines
    211-292 — see module docstring for the full line map). With default
    ``start_quarter``/``end_quarter``/``bar_files`` this is arithmetically
    IDENTICAL to the FMA2 engine (bit-identity gated by
    scripts/verify_record_engine_ext.py).

    Parameters (beyond the FMA2 originals)
    --------------------------------------
    start_quarter, end_quarter : calendar-quarter labels, e.g. "2026Q1",
        "2026Q2". The account starts at ``initial`` at range start; there is
        no warmup simulation before it (signals in ``pos`` may of course be
        computed from earlier history — that is the caller's job).
    bar_files : per-symbol bar-source override — path or ordered sequence of
        IC-schema, server-time parquet paths (see _resolve_bar_files /
        _native). Applies to traded symbols AND EUR-conversion crosses.
    daily_stop_x : FTMO daily circuit breaker in PERCENT of the day anchor
        (e.g. 3.5 => flatten at anchor * 0.965), or None = off. See the
        module docstring section "FTMO DAILY CIRCUIT BREAKER" for the exact
        semantics (day anchor, worst-side flatten, halt-to-next-server-day,
        gap-through). None routes through the untouched _run_chunk kernel.

    Returns (eq_close, eq_worst, metrics) exactly like the FMA2 engine;
    metrics additionally carries ``n_daily_stops`` (0/None when off).
    """
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
    vlim = np.array([(volume_limit.get(s, 0.0) if volume_limit else 0.0) for s in symbols], float)  # broker VOLUME_LIMIT; 0=no cap

    quarters = pd.period_range(start_quarter, end_quarter, freq="Q")
    if len(quarters) == 0:
        raise ValueError(f"empty quarter range {start_quarter}..{end_quarter}")

    # Forward-window guard: a cross whose data ends before a quarter begins
    # would silently freeze EUR conversion at its last known rate.
    for qp in quarters:
        for c in crosses:
            idx_c, _ = _native(src[c])
            if idx_c[-1] < np.int64(qp.start_time.value):
                raise ValueError(
                    f"EUR cross {c} bar source ends "
                    f"{pd.Timestamp(idx_c[-1])} — before {qp} starts. EUR "
                    "conversion would freeze (the NSF5 2026-07-02 FxConverter "
                    f"audit defect). Provide bar_files[{c!r}] covering the "
                    "window (build_fwd_cache.py emits 2026H1 cross files, "
                    "including the synthetic EURCHF).")

    balance = initial
    lots = np.zeros(len(symbols))
    entry = np.zeros(len(symbols))
    eqc_parts, eqw_parts, idx_parts = [], [], []
    total_trades = 0

    # FMA3-008 daily-stop carry state (only used when daily_stop_x is set):
    # day 1's anchor is `initial`; anchor/halt state carries across chunks.
    stop_frac = None if daily_stop_x is None else float(daily_stop_x) / 100.0
    if stop_frac is not None and not (0.0 < stop_frac):
        raise ValueError(f"daily_stop_x must be a positive percent or None, "
                         f"got {daily_stop_x!r}")
    ds_anchor, ds_last_close = float(initial), float(initial)
    ds_cur_day, ds_halted = np.int64(-1), False
    total_stops = 0

    for qp in quarters:
        qs, qe = qp.start_time, qp.end_time
        # chunk union grid = union of all load_syms' minutes in [qs, qe]
        grids = []
        for s in load_syms:
            idx, _ = _native(src[s])
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

        # target held over each minute = hourly signal from the PREVIOUS hour
        gidx = pd.DatetimeIndex(grid_ns.astype("datetime64[ns]"))
        prev_hour = gidx.floor("h") - pd.Timedelta(hours=1)
        tgt = pos.reindex(prev_hour, method=None).to_numpy()
        tgt = np.nan_to_num(tgt, nan=0.0)

        if stop_frac is None:
            eqc, eqw, balance, lots, entry, ntr = _run_chunk(
                tgt, has, f["bid_o"], f["ask_o"], f["bid_c"], f["ask_c"],
                f["bid_l"], f["ask_h"], eurq, swap_l, swap_s,
                contract, comm, lev, step, mlot, vlim,
                stop_out, float(margin_cap), float(rebalance_band),
                balance, lots, entry)
        else:
            day_id = grid_ns // 86_400_000_000_000   # server-day ordinal (ns)
            (eqc, eqw, balance, lots, entry, ntr,
             ds_anchor, ds_last_close, ds_cur_day, ds_halted,
             n_st) = _run_chunk_stop(
                tgt, has, f["bid_o"], f["ask_o"], f["bid_c"], f["ask_c"],
                f["bid_l"], f["ask_h"], eurq, swap_l, swap_s,
                contract, comm, lev, step, mlot, vlim,
                stop_out, float(margin_cap), float(rebalance_band),
                balance, lots, entry,
                day_id, float(stop_frac), ds_anchor, ds_last_close,
                ds_cur_day, ds_halted)
            total_stops += int(n_st)
        eqc_parts.append(eqc)
        eqw_parts.append(eqw)
        idx_parts.append(gidx)
        total_trades += ntr
        if verbose:
            print(f"  {qp}: {len(grid_ns):>7,} min | bal €{balance:,.0f} "
                  f"| trades {ntr:,}", flush=True)

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
    m["n_daily_stops"] = None if stop_frac is None else int(total_stops)
    return eq_c, eq_w, m


def run_record_ext(frac_1h: pd.DataFrame, *,
                   start_quarter: str = BASE_QUARTERS[0],
                   end_quarter: str = BASE_QUARTERS[1],
                   bar_files: Mapping[str, object] | None = None,
                   initial: float = 10_000.0,
                   daily_stop_x: float | None = None,
                   volume_limit=None,
                   label: str,
                   verbose: bool = True,
                   run_bootstrap: bool = True) -> dict:
    """``record_engine.run_record``-shaped wrapper around the ext engine.

    Same result-dict contract as record_engine.run_record (cagr,
    maxdd_worst/maxdd_close, sharpe, yearly/quarterly, breach, curves, ...)
    so downstream reporting code is interchangeable, but backed by
    ``simulate_account_1m_ext`` — i.e. arbitrary quarter ranges and injected
    bar sources are first-class instead of being emulated by zeroing.
    """
    if not isinstance(frac_1h.index, pd.DatetimeIndex) or frac_1h.index.tz is not None:
        raise ValueError("frac_1h must have a tz-naive (server-time) DatetimeIndex")
    q0, q1 = pd.Period(start_quarter, freq="Q"), pd.Period(end_quarter, freq="Q")
    if q0 > q1:
        raise ValueError(f"start_quarter {q0} is after end_quarter {q1}")

    eq_c, eq_w, m = simulate_account_1m_ext(
        frac_1h, initial=initial, start_quarter=str(q0), end_quarter=str(q1),
        bar_files=bar_files, daily_stop_x=daily_stop_x,
        volume_limit=volume_limit, verbose=verbose)

    peak = np.maximum.accumulate(eq_c.to_numpy())
    maxdd_close = float(((peak - eq_c.to_numpy()) / np.maximum(peak, 1e-9)).max())

    breach = None
    if run_bootstrap:
        curve = pd.DataFrame({"equity": eq_c, "worst": eq_w})
        breach = worst_mark_breach(curve)   # seed 20260709, 5000 paths, 20d

    neg_years = sorted(int(y) for y, r in m["yearly"].items() if r < 0)
    neg_quarters = sorted(q for q, r in m["quarterly"].items() if r < 0)

    return {
        "label": label,
        "start_quarter": str(q0),
        "end_quarter": str(q1),
        "initial": float(initial),
        "daily_stop_x": daily_stop_x,
        "n_daily_stops": m["n_daily_stops"],
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
    print("record_engine_ext module OK; assumed 2026H1 policy rates:")
    for ccy, r in sorted(ASSUMED_2026H1_POLICY_RATES.items()):
        print(f"  {ccy}: {r:+.3f} %/yr (flat extension, verified)")
