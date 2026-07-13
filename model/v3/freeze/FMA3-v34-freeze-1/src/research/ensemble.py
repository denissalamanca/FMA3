"""Ensemble construction: combine sleeve position matrices into one
portfolio, optimize sleeve weights + global scale (+ optional causal
portfolio-vol targeting) on the multi-objective fitness function.

F = Sharpe * (CAGR/MaxDD) * (1 - negQ/24) * (1 - rho_bar) * psi
psi = 0.1 if any negative year else 1.0
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

import core

OUT = Path(__file__).resolve().parent / "outputs"


def load_sleeves(names: list[str]) -> dict[str, pd.DataFrame]:
    sleeves = {}
    U = core.universe_frames(tuple(core.ALL))
    idx = U["ret"].index
    for n in names:
        p = pd.read_parquet(OUT / f"{n}_pos.parquet")
        sleeves[n] = p.reindex(idx).fillna(0.0)
    return sleeves


def sleeve_daily_returns(sleeves: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rets = {}
    for n, pos in sleeves.items():
        res = core.simulate(pos)
        daily = res.equity.resample("1D").last().dropna()
        rets[n] = daily.pct_change()
    return pd.DataFrame(rets)


def combine(sleeves: dict[str, pd.DataFrame], weights: dict[str, float],
            scale: float = 1.0) -> pd.DataFrame:
    tot = None
    for n, pos in sleeves.items():
        w = weights.get(n, 0.0) * scale
        if w == 0.0:
            continue
        contrib = pos * w
        tot = contrib if tot is None else tot.add(contrib, fill_value=0.0)
    return tot.fillna(0.0)


def structural_gold_cap(weights: dict[str, float], scale: float,
                        primary: str = "seasonal") -> float:
    """The v2 overnight-gold cap as a RULE, not a number: 'overnight |XAUUSD|
    may not exceed the primary gold sleeve's own intended exposure'. Derived
    from the shipped config (no free constant; self-adjusts with weights/scale).
    Purpose: clip multi-sleeve STACKING on gold without double-punishing the
    primary sleeve F3 already sized. Plateau-verified (no fitted peak): CAGR/
    Sharpe/negQ vary smoothly and monotonically across the whole cap band."""
    return weights[primary] * scale


def apply_hard_limits(pos_scaled: pd.DataFrame, *, gold_cap: float,
                      cross_cap: float = 0.5) -> pd.DataFrame:
    """v2 hard exposure limits (stress-validated, docs/v2.0/stress/):
    - managed-cross cap: |exposure| <= cross_cap x equity at ALL times on the
      peg-risk crosses (MKT-8a: cuts a -15% gap single-print to ~7%);
    - overnight-gold cap: |XAUUSD exposure| <= gold_cap x equity on positions
      held into/through the server-midnight roll (MKT-4a). Pass
      structural_gold_cap(weights, scale) — the rule-derived value.
    Input is the FINAL scaled position matrix (fraction of equity). Pointwise,
    causal clip on decision-time positions."""
    P = pos_scaled.copy()
    for c in ("EURCHF", "EURSEK", "EURNOK", "AUDNZD"):
        if c in P.columns:
            P[c] = P[c].clip(-cross_cap, cross_cap)
    if "XAUUSD" in P.columns:
        hrs = P.index.hour
        overnight = (hrs >= 21) | (hrs < 6)
        P.loc[overnight, "XAUUSD"] = P.loc[overnight, "XAUUSD"].clip(-gold_cap, gold_cap)
    return P


def vol_target_overlay(pos: pd.DataFrame, *, target: float = 0.12,
                       span_days: int = 20, max_mult: float = 2.0,
                       min_mult: float = 0.3) -> pd.DataFrame:
    """Causal portfolio-level vol targeting: scale positions by
    target / trailing realized vol of the CURRENT book's pnl proxy.
    Uses yesterday's positions with today's returns — no lookahead."""
    U = core.universe_frames(tuple(core.ALL))
    ret = U["ret"][pos.columns]
    pnl = (pos.shift(1) * ret).sum(axis=1)
    rv = np.sqrt(pnl.pow(2).ewm(span=span_days * 24).mean() * 24 * 365.25)
    mult = (target / rv.clip(lower=1e-4)).clip(min_mult, max_mult).shift(1)
    return pos.mul(mult, axis=0).fillna(0.0)


def _proxy_pnl(pos: pd.DataFrame) -> pd.Series:
    """Causal pre-cost book pnl proxy (fraction of equity per bar)."""
    U = core.universe_frames(tuple(core.ALL))
    ret = U["ret"][pos.columns]
    return (pos.shift(1) * ret).sum(axis=1)


def dd_throttle_overlay(pos: pd.DataFrame, *, k: float = 2.0,
                        floor: float = 0.4) -> pd.DataFrame:
    """Scale positions by max(1 - k*dd, floor) where dd is the causal
    drawdown of the pre-overlay proxy book (observable history only)."""
    pnl = _proxy_pnl(pos)
    eq = (1.0 + pnl).cumprod()
    dd = 1.0 - eq / eq.cummax()
    scale = (1.0 - k * dd).clip(lower=floor, upper=1.0).shift(1).fillna(1.0)
    return pos.mul(scale, axis=0)


def quarter_throttle_overlay(pos: pd.DataFrame, *, thr: float = 0.05,
                             f: float = 0.35) -> pd.DataFrame:
    """Once the proxy book's quarter-to-date return breaches -thr, de-gross
    to f for the remainder of the calendar quarter (sticky; resets at the
    next quarter). Trigger uses pre-overlay pnl — causal, engine-replicable
    because the overlay is baked into the final position matrix."""
    pnl = _proxy_pnl(pos)
    q = pnl.index.to_period("Q")
    cum = (1.0 + pnl).groupby(q).cumprod() - 1.0
    breached = (cum < -thr).groupby(q).cummax().shift(1).fillna(False)
    scale = np.where(breached, f, 1.0)
    return pos.mul(pd.Series(scale, index=pos.index), axis=0)


def stream_metrics(dr: pd.Series) -> dict:
    """Metrics from a DAILY return stream (fast weight-search path)."""
    eq = (1.0 + dr.fillna(0.0)).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = float(eq.iloc[-1]) ** (1.0 / yrs) - 1.0
    dd = float((1.0 - eq / eq.cummax()).max())
    sharpe = float(dr.mean() / dr.std() * np.sqrt(252)) if dr.std() > 0 else 0.0
    q = eq.groupby(eq.index.to_period("Q")).last()
    q_ret = q.pct_change()
    q_ret.iloc[0] = float(q.iloc[0]) - 1.0
    y = eq.groupby(eq.index.year).last()
    y_ret = y.pct_change()
    y_ret.iloc[0] = float(y.iloc[0]) - 1.0
    n_neg_q, n_neg_y = int((q_ret < 0).sum()), int((y_ret < 0).sum())
    psi = 0.1 if n_neg_y > 0 else 1.0
    return {"cagr": cagr, "maxdd": dd, "sharpe": sharpe,
            "n_neg_quarters": n_neg_q, "n_neg_years": n_neg_y,
            "fitness_no_rho": sharpe * (cagr / max(dd, 1e-9))
            * (1 - n_neg_q / 24) * psi}


def search_streams(dr: pd.DataFrame, *, n_samples: int = 20000,
                   scale_grid: list[float] | None = None,
                   upto: str = "2023-12-31", dd_budget: float = 0.15,
                   seed: int = 7) -> list[dict]:
    """Dirichlet-sample sleeve weights on DAILY sleeve return streams
    (additive approx of the position-level book), score DEV fitness with a
    DD budget, return sorted candidates."""
    rng = np.random.default_rng(seed)
    names = list(dr.columns)
    dev = dr.loc[:upto].fillna(0.0)
    scale_grid = scale_grid or [1.0]
    rows = []
    W = rng.dirichlet(np.ones(len(names)), size=n_samples)
    for w in W:
        base = dev @ w
        for sc in scale_grid:
            m = stream_metrics(base * sc)
            if m["maxdd"] > dd_budget:
                continue
            rows.append({"weights": dict(zip(names, map(float, w))),
                         "scale": sc, **m})
    rows.sort(key=lambda r: -r["fitness_no_rho"])
    return rows


def grid_weights(names: list[str], steps: list[float]) -> list[dict[str, float]]:
    combos = []
    for ws in itertools.product(steps, repeat=len(names)):
        s = sum(ws)
        if s == 0:
            continue
        combos.append({n: w / s for n, w in zip(names, ws)})
    # dedupe
    seen, out = set(), []
    for c in combos:
        k = tuple(round(c[n], 3) for n in names)
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def evaluate(pos: pd.DataFrame, upto: str | None = None,
             start: str | None = None) -> dict:
    res = core.simulate(pos, start=start, end=upto)
    m = res.metrics
    m["max_margin"] = float(res.margin_used.max())
    m["max_gross"] = float(res.gross_lev.max())
    return m


def search(names: list[str], *, weight_steps: list[float],
           scales: list[float], vol_targets: list[float | None],
           upto: str = "2023-12-31", top_k: int = 15,
           verbose: bool = True) -> list[dict]:
    """Coarse DEV-period search over (weights, scale, vol-target).
    Returns top_k configs by DEV fitness."""
    sleeves = load_sleeves(names)
    rows = []
    wgrids = grid_weights(names, weight_steps)
    n_total = len(wgrids) * len(scales) * len(vol_targets)
    if verbose:
        print(f"search space: {n_total} configs")
    for wi, w in enumerate(wgrids):
        base = combine(sleeves, w)
        for vt in vol_targets:
            pv = vol_target_overlay(base, target=vt) if vt else base
            for sc in scales:
                m = evaluate(pv * sc, upto=upto)
                rows.append({"weights": w, "scale": sc, "vol_target": vt,
                             "fitness": m["fitness"], "cagr": m["cagr"],
                             "maxdd": m["maxdd"], "sharpe": m["sharpe"],
                             "n_neg_q": m["n_neg_quarters"],
                             "n_neg_y": m["n_neg_years"],
                             "max_margin": m["max_margin"]})
        if verbose and (wi + 1) % 20 == 0:
            print(f"  {wi + 1}/{len(wgrids)} weight vectors done", flush=True)
    rows.sort(key=lambda r: -r["fitness"])
    return rows[:top_k]


if __name__ == "__main__":
    import sys
    names = sys.argv[1:] or ["trend", "meanrev", "carry_breakout", "seasonal"]
    sleeves = load_sleeves(names)
    dr = sleeve_daily_returns(sleeves)
    print("sleeve daily-return correlations:")
    print(dr.corr().round(2).to_string())
    for n in names:
        pos = sleeves[n]
        m = evaluate(pos)
        print(f"{n:16s} {core.fmt_metrics(m)}")
