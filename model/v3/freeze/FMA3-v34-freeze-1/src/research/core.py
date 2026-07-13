"""Shared research harness for the multi-asset strategy search.

Fast, vectorized hourly portfolio simulator whose cost model mirrors the
NewStrategyFable5 engine (spread crossing, per-lot commission, swap curves
imported from the engine's own cost module, ESMA leverage caps). Used for
hypothesis iteration; final numbers ALWAYS come from the repo's numba engine
at 1m resolution.

Position convention: `pos[t, i]` = signed notional exposure as a fraction of
current portfolio equity, DECIDED on bar t's close and HELD over bar t+1
(next-bar execution, like the engine). Costs are charged on |Δpos|.

TIMEZONE: bar stamps are broker SERVER time (GMT+2 winter / GMT+3 summer,
NY-anchored — the daily CFD break sits at hour 0 year-round = 17:00 ET).
They are NOT UTC. Swap rollover = server midnight. Session math: hour 0 =
17:00 ET; London opens ~hour 10; NY equity cash session = hours 16:30-23.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

FRAMEWORK = Path("/Users/dsalamanca/vs_env/NewStrategyFable5")
if str(FRAMEWORK) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK))

from config import settings as S            # noqa: E402  (execution spec only)
from engine import costs as engine_costs    # noqa: E402  (cost curves only)

CACHE = Path(__file__).resolve().parents[1] / "research_cache"

FX = ["AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
      "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
      "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY"]
CRYPTO = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
INDICES = ["DAX", "JP225", "UK100", "US30", "USA500", "USTEC"]
COMMODITIES = ["XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"]
ALL = FX + CRYPTO + INDICES + COMMODITIES

CLASS_OF: dict[str, str] = {}
for s_ in FX:
    CLASS_OF[s_] = "fx"
for s_ in CRYPTO:
    CLASS_OF[s_] = "crypto"
for s_ in INDICES:
    CLASS_OF[s_] = "index"
for s_ in COMMODITIES:
    CLASS_OF[s_] = "commodity"

YEARS = list(range(2020, 2026))
N_QUARTERS = 24


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def load_hourly(sym: str) -> pd.DataFrame:
    return pd.read_parquet(CACHE / f"{sym}_1h.parquet")


@lru_cache(maxsize=8)
def universe_frames(symbols: tuple[str, ...] = tuple(ALL)) -> dict[str, pd.DataFrame]:
    """close / rel_spread / has_bar matrices on the union hourly index."""
    closes, spreads = {}, {}
    for sym in symbols:
        df = load_hourly(sym)
        closes[sym] = df["c"]
        spreads[sym] = df["rel_spread"]
    close = pd.DataFrame(closes)
    relsp = pd.DataFrame(spreads)
    has_bar = close.notna()
    close = close.ffill()
    # per-bar simple returns (0 while market closed -> equity flat)
    ret = close.pct_change(fill_method=None).fillna(0.0)
    ret = ret.where(close.shift(1).notna(), 0.0)
    # winsorize the pathological single-bar spikes (bad ticks), keep real moves
    ret = ret.clip(-0.30, 0.30)
    relsp = relsp.ffill().bfill()
    return {"close": close, "ret": ret, "rel_spread": relsp,
            "has_bar": has_bar}


# ---------------------------------------------------------------------------
# Cost model (mirrors engine/costs.py + config/settings.py)
# ---------------------------------------------------------------------------
def leverage_of(sym: str) -> float:
    return float(S.INSTRUMENTS[sym]["leverage"])


@lru_cache(maxsize=8)
def commission_frac(symbols: tuple[str, ...] = tuple(ALL)) -> pd.Series:
    """Round-trip-per-side commission as a fraction of notional (approx,
    using median price over the sample; exact engine handles it per-fill)."""
    fr = {}
    for sym in symbols:
        cfg = S.INSTRUMENTS[sym]
        comm = float(cfg["commission_side"])
        if comm == 0.0:
            fr[sym] = 0.0
            continue
        px = float(load_hourly(sym)["c"].median())
        quote = cfg["quote"]
        eur_per_quote = _median_eur_per(quote)
        lot_notional_eur = px * float(cfg["contract_size"]) * eur_per_quote
        fr[sym] = comm / lot_notional_eur
    return pd.Series(fr)


def _median_eur_per(quote: str) -> float:
    if quote == "EUR":
        return 1.0
    pair = f"EUR{quote}"
    return 1.0 / float(load_hourly(pair)["c"].median())


@lru_cache(maxsize=8)
def swap_accrual_matrices(symbols: tuple[str, ...] = tuple(ALL)
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(long, short) swap accrual as fraction of notional, placed on the
    HOURLY grid at the bar where the rollover lands. Bar stamps are broker
    SERVER time (GMT+2/+3, NY-anchored — verified: daily break at hour 0
    year-round), so the 17:00-NY rollover of calendar day d lands on the
    first bar at/after midnight of d+1. Weekend multipliers (triple-Wed FX,
    triple-Fri indices, daily crypto) folded in via the engine's own curves."""
    U = universe_frames(tuple(ALL))
    idx = U["ret"].index
    ts = idx.values.astype("datetime64[ns]")
    # cover the loaded grid, whatever its span (2015-2020 ext cache or 2020-2025
    # IC cache). Rate lookups are floored at the first policy-rate entry
    # (2019-11) — flat-backfill for earlier dates, per the v2.0 pre-registration
    # ("financing approximate pre-2019-11"). Weekend multipliers use the TRUE day.
    days = pd.date_range(idx[0].normalize(), idx[-1].normalize(), freq="D")
    rate_floor = pd.Timestamp("2019-11-01")
    la = np.zeros((len(idx), len(symbols)))
    sa = np.zeros((len(idx), len(symbols)))
    for k, sym in enumerate(symbols):
        ac = S.INSTRUMENTS[sym]["asset_class"]
        for d in days:
            if ac != "crypto" and d.weekday() >= 5:
                continue
            ro = np.datetime64(d + pd.Timedelta(days=1))
            j = int(np.searchsorted(ts, ro, side="left"))
            if j >= len(idx):
                continue
            mult = engine_costs.swap_day_multiplier(sym, d)
            lp, sp = engine_costs.swap_annual_pct(sym, max(d, rate_floor))
            la[j, k] += lp / 100.0 / 365.0 * mult
            sa[j, k] += sp / 100.0 / 365.0 * mult
    return (pd.DataFrame(la, index=idx, columns=list(symbols)),
            pd.DataFrame(sa, index=idx, columns=list(symbols)))


# ---------------------------------------------------------------------------
# Fast portfolio simulator
# ---------------------------------------------------------------------------
@dataclass
class SimResult:
    equity: pd.Series               # hourly equity (multiple of initial)
    metrics: dict
    gross_lev: pd.Series            # sum |pos| per bar
    margin_used: pd.Series          # sum |pos|/lev per bar
    pnl_by_sym: pd.DataFrame        # per-symbol pre-cost pnl contribution
    pos: pd.DataFrame               # effective positions actually held


def simulate(pos: pd.DataFrame, *, symbols: list[str] | None = None,
             cost_mult: float = 1.0, with_swap: bool = True,
             start: str | None = None, end: str | None = None) -> SimResult:
    """pos: fraction-of-equity exposures on the union hourly grid (or a
    subset of symbols). Positions only change on bars where the symbol
    trades; elsewhere the previous position persists.

    start/end restrict the SIMULATION WINDOW: returns, costs and metrics are
    computed on that window only. Always evaluate sub-periods this way —
    passing a row-sliced pos matrix instead would (a) freeze the last row's
    positions across the remaining index via ffill and (b) dilute
    CAGR/Sharpe with flat years (bug caught 2026-07-08)."""
    symbols = list(pos.columns) if symbols is None else symbols
    U = universe_frames(tuple(ALL))
    ret = U["ret"][symbols].loc[start:end]
    relsp = U["rel_spread"][symbols].loc[start:end]
    has_bar = U["has_bar"][symbols].loc[start:end]

    pos = pos.reindex(index=ret.index, columns=symbols).astype(float)
    # freeze position changes while the market is closed
    pos = pos.where(has_bar).ffill().fillna(0.0)

    p = pos.to_numpy()
    r = ret.to_numpy()
    held = np.vstack([np.zeros((1, p.shape[1])), p[:-1]])   # held over bar t
    pnl = held * r

    dpos = np.abs(np.diff(np.vstack([np.zeros((1, p.shape[1])), p]), axis=0))
    unit_cost = (relsp.to_numpy() / 2.0
                 + commission_frac(tuple(ALL))[symbols].to_numpy()[None, :])
    tcost = dpos * unit_cost * cost_mult

    swap = np.zeros_like(pnl)
    if with_swap:
        la, sa = swap_accrual_matrices(tuple(ALL))
        la_m = la[symbols].loc[start:end].to_numpy()
        sa_m = sa[symbols].loc[start:end].to_numpy()
        swap = np.where(held > 0, held * la_m,
                        np.where(held < 0, -held * sa_m, 0.0))

    bar_ret = pnl.sum(axis=1) - tcost.sum(axis=1) + swap.sum(axis=1)
    equity = np.cumprod(1.0 + np.clip(bar_ret, -0.95, None))
    eq = pd.Series(equity, index=ret.index, name="equity")

    lev = pd.Series(np.abs(p).sum(axis=1), index=ret.index)
    margin = pd.Series(
        (np.abs(p) / np.array([leverage_of(s) for s in symbols])[None, :])
        .sum(axis=1), index=ret.index)
    pnl_df = pd.DataFrame(pnl + swap - tcost, index=ret.index, columns=symbols)

    m = compute_metrics(eq, pos=pos)
    return SimResult(eq, m, lev, margin, pnl_df, pos)


# ---------------------------------------------------------------------------
# Metrics + fitness
# ---------------------------------------------------------------------------
def compute_metrics(eq: pd.Series, pos: pd.DataFrame | None = None) -> dict:
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    final = float(eq.iloc[-1])
    cagr = final ** (1.0 / yrs) - 1.0 if final > 0 else -1.0
    peak = np.maximum.accumulate(eq.to_numpy())
    maxdd = float(((peak - eq.to_numpy()) / peak).max())
    daily = eq.resample("1D").last().dropna()
    dr = daily.pct_change().dropna()
    sharpe = float(dr.mean() / dr.std() * np.sqrt(252)) if dr.std() > 0 else 0.0

    yearly = daily.groupby(daily.index.year).last() / \
        daily.groupby(daily.index.year).first() - 1.0
    q_last = daily.groupby(daily.index.to_period("Q")).last()
    q_ret = q_last.pct_change()
    q_ret.iloc[0] = q_last.iloc[0] / float(eq.iloc[0]) - 1.0
    n_neg_y = int((yearly < 0).sum())
    n_neg_q = int((q_ret < 0).sum())

    rho = np.nan
    if pos is not None and pos.shape[1] > 1:
        act = pos.loc[:, pos.abs().sum() > 0]
        if act.shape[1] > 1:
            cm = act.resample("1D").mean().corr().abs().to_numpy()
            iu = np.triu_indices_from(cm, k=1)
            rho = float(np.nanmean(cm[iu]))

    psi = 0.1 if n_neg_y > 0 else 1.0
    rho_term = 1.0 - (rho if np.isfinite(rho) else 0.0)
    fitness = (sharpe * (cagr / max(maxdd, 1e-9))
               * (1.0 - n_neg_q / N_QUARTERS) * rho_term * psi)
    return {
        "cagr": cagr, "maxdd": maxdd, "sharpe": sharpe,
        "final": final, "years": yrs,
        "yearly": {int(k): float(v) for k, v in yearly.items()},
        "quarterly": {str(k): float(v) for k, v in q_ret.items()},
        "n_neg_years": n_neg_y, "n_neg_quarters": n_neg_q,
        "mean_abs_corr": rho, "fitness": float(fitness),
        # Gates revised 2026-07-09: DD budget raised 20%->30% (user's real risk
        # tolerance, benchmarked to their live book); CAGR floor 85%->80% with
        # CAGR maximized within the DD budget.
        "gates": {
            "cagr_ge_80": cagr >= 0.80, "maxdd_lt_30": maxdd < 0.30,
            "sharpe_gt_2": sharpe > 2.0, "neg_years_0": n_neg_y == 0,
            "neg_quarters_le_1": n_neg_q <= 1,
        },
    }


def fmt_metrics(m: dict) -> str:
    g = m["gates"]
    ok = lambda b: "PASS" if b else "fail"       # noqa: E731
    return (f"CAGR {m['cagr']:+7.1%} [{ok(g['cagr_ge_80'])}] | "
            f"MaxDD {m['maxdd']:6.1%} [{ok(g['maxdd_lt_30'])}] | "
            f"Sharpe {m['sharpe']:5.2f} [{ok(g['sharpe_gt_2'])}] | "
            f"negY {m['n_neg_years']} [{ok(g['neg_years_0'])}] | "
            f"negQ {m['n_neg_quarters']}/24 [{ok(g['neg_quarters_le_1'])}] | "
            f"rho {m['mean_abs_corr'] if m['mean_abs_corr'] == m['mean_abs_corr'] else float('nan'):.2f} | "
            f"F {m['fitness']:.2f}")


# ---------------------------------------------------------------------------
# Signal utilities (causal, shared)
# ---------------------------------------------------------------------------
def daily_closes(symbols: list[str] | None = None) -> pd.DataFrame:
    """UTC-day closes on the union grid (last hourly close of each day)."""
    symbols = ALL if symbols is None else symbols
    U = universe_frames(tuple(ALL))
    return U["close"][list(symbols)].resample("1D").last().dropna(how="all")


def realized_vol(ret: pd.DataFrame, span_days: int = 30,
                 bars_per_day: float = 24.0) -> pd.DataFrame:
    """EWMA annualized vol from hourly returns."""
    var = ret.pow(2).ewm(span=int(span_days * bars_per_day)).mean()
    return np.sqrt(var * bars_per_day * 365.25)


def to_hourly(sig_daily: pd.DataFrame, hourly_index: pd.DatetimeIndex,
              lag_hours: int = 1) -> pd.DataFrame:
    """Map a daily signal (stamped at day d 00:00 by resample('1D'), computed
    from data up to d's 23:59 close) onto the hourly grid, effective from
    d+1 00:00 (+ optional extra lag). With the sim's held-from-t+1
    convention this executes at the first tradable open of d+1 — causal."""
    s = sig_daily.copy()
    s.index = s.index + pd.Timedelta(days=1) + pd.Timedelta(hours=lag_hours - 1)
    out = s.reindex(hourly_index.union(s.index)).ffill().reindex(hourly_index)
    return out
