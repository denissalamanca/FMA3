"""crisis -- defensive convexity / vol-regime sleeve.

HYPOTHESIS (stated before fitting): volatility expansions cluster and risk
assets underperform during them. Positions that activate ONLY in stress
regimes earn crisis premia: long XAUUSD (safe-haven bid) and short
AUD/NZD/CAD vs JPY (funding-currency snapback), each qualified by the
asset's own direction so the sleeve is not run over by post-spike V-shaped
rebounds (the empirically dominant failure mode of naive stress hedges in
2020-2025).

DESIGN (regime-indicator based, never date/event based):
  * Equity stress score S_eq: binary OR of two triggers on an equal-weight
    equity-index basket (US30, USA500, USTEC, DAX, JP225, UK100):
      - realized-vol expansion: 10d vol / 60d vol > v0
      - drawdown state: basket below its rolling 126d peak by more than d0
    smoothed with a 3-day EWM (values in [0,1]).
  * FX stress score S_fx: JPY-cross basket (AUDJPY, NZDJPY, CADJPY) 10d/60d
    vol ratio > fx_v0 AND basket below its 50d MA (carry unwinding), same
    smoothing.
  * Legs (only active in stress):
      - long XAUUSD:  S_eq * (gold > its 50d MA) * k_au / slow_vol, cap 1.0
      - short each JPY cross: S_fx * (k_jp/3) / slow_vol, cap 1.0
    Slow (250d EWM) vol sizing so crash-day payoff is not shrunk exactly
    when it is needed. Killed in research (documented in the report): short
    equity indices, long XAG, long CHF -- each bled or paid only in one year.
  * Trading: daily signal (UTC close), effective next day 13:00 UTC (away
    from the 21:00-23:00 rollover spread blowout); positions rounded to a
    0.02 grid for hysteresis; sleeve gross capped at 3.

Free parameters (6): V0, D0, FX_V0, K_AU, K_JP, SMOOTH_SPAN.
Everything else is a fixed structural constant chosen a priori.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

NAME = "crisis"

# ---- frozen parameters (tuned on DEV = through 2023-12-31 only) ----------
V0: float = 1.25          # vol-ratio trigger on the equity basket
D0: float = 0.05          # drawdown trigger (fraction below 126d peak)
FX_V0: float = 1.20       # vol-ratio trigger on the JPY-cross basket
K_AU: float = 0.30        # gold leg risk budget (ann. vol when active)
K_JP: float = 0.25        # JPY-snapback leg risk budget (ann. vol, 3 pairs)
SMOOTH_SPAN: int = 3      # EWM span (days) applied to both regime scores

# ---- fixed structural constants (not tuned) -------------------------------
_VOL_WIN_S, _VOL_WIN_L = 10, 60      # regime vol-ratio windows (days)
_DD_WIN = 126                        # drawdown lookback (days)
_MA_WIN = 50                         # trend-qualifier MA (days)
_SIZE_SPAN = 250                     # slow sizing vol EWM span (days)
_VOL_FLOOR = 0.05                    # annualized sizing-vol floor
_GRID = 0.02                         # position rounding grid (hysteresis)
_TRADE_LAG_H = 14                    # effective next day 13:00 UTC
_GROSS_CAP = 3.0
_POS_CAP = 1.0

JPX: list[str] = ["AUDJPY", "NZDJPY", "CADJPY"]
SYMS: list[str] = ["XAUUSD"] + JPX


def make_positions(v0: float = V0, d0: float = D0, fx_v0: float = FX_V0,
                   k_au: float = K_AU, k_jp: float = K_JP,
                   smooth_span: int = SMOOTH_SPAN) -> pd.DataFrame:
    """Build the sleeve's positions on the union hourly grid (2020-2025).

    Returns a DataFrame of signed fraction-of-equity exposures for SYMS,
    causal under core.simulate's held-from-t+1 convention.
    """
    U = core.universe_frames()
    idx = U["ret"].index

    dcA = core.daily_closes(core.ALL)
    dcA = dcA[dcA.index.dayofweek < 5]
    rA = dcA.pct_change()

    # equity stress score
    br = rA[core.INDICES].mean(axis=1)
    vr = (br.rolling(_VOL_WIN_S).std() * np.sqrt(252)) / \
         (br.rolling(_VOL_WIN_L).std() * np.sqrt(252))
    lev = (1.0 + br.fillna(0)).cumprod()
    dd = lev / lev.rolling(_DD_WIN, min_periods=20).max() - 1.0
    s_eq = ((vr > v0) | (dd < -d0)).astype(float).ewm(span=smooth_span).mean()

    # fx stress score (JPY-cross own vol expansion + carry unwinding)
    fr = rA[JPX].mean(axis=1)
    fvr = (fr.rolling(_VOL_WIN_S).std() * np.sqrt(252)) / \
          (fr.rolling(_VOL_WIN_L).std() * np.sqrt(252))
    flev = (1.0 + fr.fillna(0)).cumprod()
    fma = flev.rolling(_MA_WIN, min_periods=20).mean()
    s_fx = ((fvr > fx_v0) & (flev < fma)).astype(float) \
        .ewm(span=smooth_span).mean()

    # gold own-trend qualifier
    au = dcA["XAUUSD"]
    up_au = (au > au.rolling(_MA_WIN, min_periods=20).mean()).astype(float)

    # slow sizing vol
    vol = (rA[SYMS].ewm(span=_SIZE_SPAN, min_periods=60).std()
           * np.sqrt(252)).clip(lower=_VOL_FLOOR)

    w = pd.DataFrame(0.0, index=rA.index, columns=SYMS)
    w["XAUUSD"] = s_eq * up_au * (k_au / vol["XAUUSD"])
    for s in JPX:
        w[s] = -s_fx * (k_jp / 3.0) / vol[s]

    # hysteresis grid, per-instrument cap, gross cap
    w = ((w / _GRID).round() * _GRID).clip(-_POS_CAP, _POS_CAP)
    gross = w.abs().sum(axis=1)
    w = w.mul((_GROSS_CAP / gross).clip(upper=1.0), axis=0)

    pos = core.to_hourly(w, idx, lag_hours=_TRADE_LAG_H)
    return pos.fillna(0.0)


def _slice_metrics(eq: pd.Series, start: str | None = None,
                   end: str | None = None) -> dict:
    """Metrics on a renormalized equity slice (avoids the dilution that
    comes from simulating a sliced position frame on the full grid)."""
    s = eq.loc[start:end]
    return core.compute_metrics(s / s.iloc[0])


if __name__ == "__main__":
    pd.set_option("future.no_silent_downcasting", True)
    pos = make_positions()
    out = Path(__file__).resolve().parents[1] / "outputs" / f"{NAME}_pos.parquet"
    pos.to_parquet(out)
    print(f"saved {out}  shape={pos.shape}")
    res = core.simulate(pos)
    print("DEV :", core.fmt_metrics(_slice_metrics(res.equity, None, "2023-12-31")))
    print("HOLD:", core.fmt_metrics(_slice_metrics(res.equity, "2024-01-01", None)))
    print("FULL:", core.fmt_metrics(res.metrics))
