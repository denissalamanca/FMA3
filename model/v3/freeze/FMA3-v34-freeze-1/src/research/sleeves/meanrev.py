"""meanrev — statistical mean-reversion sleeve (day-to-week horizon).

Hypothesis (stated before fitting):
  (a) Related-economy / managed FX crosses (AUD-NZ, EUR-CH/GB/SE/NO,
      commodity-bloc crosses) mean-revert at multi-day horizons because
      their fundamentals co-move: multi-week divergences of price from a
      rolling anchor tend to close over the following days.  Fade z-score
      extremes with entry/exit hysteresis.
  (b) Equity indices in established uptrends attract institutional
      dip-buying: after a sharp multi-day selloff while above a long-run
      trend filter, go long-only and exit on recovery or a holding cap.

Frozen parameters (tuned on DEV = data through 2023-12-31 only):
  FX leg   : L=60 (z-score anchor, days), Z_IN=2.25, Z_OUT=0.75
  Index leg: D=5 (dip lookback, days), Z_ENTRY=1.5
  Sizing   : K=0.07 (inverse-vol numerator -> ~10% ann sleeve vol on DEV)
Structural (convention, not tuned): Z_EXIT=0.0, TREND_L=200, MAX_HOLD=10,
  EXEC_LAG=14 (positions change at 13:00 UTC, the liquid London/NY overlap
  -- 00:00 UTC rollover spreads are ~15x wider), vol floor 5%,
  |pos| cap 1.0 per instrument, portfolio gross cap 3.0.

Rejected on DEV: trend-strength entry filter (aligned-trend extremes
actually revert BETTER; filter dropped, not inverted), realized-vol regime
filter (no improvement), L=10..40 anchors (too fast, cost- and
whipsaw-heavy), daily vol-tracking position resizing (needless turnover;
size is frozen at entry instead).

Causality: signals use daily closes stamped day d (data through d 23:59),
mapped with core.to_hourly to be effective d+1 12:00 close -> first held
over the 13:00 bar (simulate applies one further bar of lag).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_RESEARCH = Path(__file__).resolve().parents[1]
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

import core  # noqa: E402

NAME = "meanrev"

FX_CROSSES: list[str] = ["AUDNZD", "EURCHF", "EURGBP", "EURSEK", "EURNOK",
                         "AUDCAD", "NZDCAD", "CADCHF", "EURCAD", "EURNZD"]
INDICES: list[str] = list(core.INDICES)
SYMBOLS: list[str] = FX_CROSSES + INDICES

DEV_END = "2023-12-31"
HOLD_START = "2024-01-01"

PARAMS: dict = {
    # --- tuned on DEV (6 free parameters) ---
    "L": 60,            # FX z-score anchor window (days)
    "Z_IN": 2.25,       # FX entry threshold |z|
    "Z_OUT": 0.75,      # FX exit threshold |z| (hysteresis)
    "D": 5,             # index dip lookback (days)
    "Z_ENTRY": 1.5,     # index dip entry threshold (vol-scaled return z)
    "K": 0.07,          # inverse-vol sizing numerator (~10% DEV sleeve vol)
    # --- structural conventions (not tuned) ---
    "Z_EXIT": 0.0,      # index exit when dip z recovers above this
    "TREND_L": 200,     # index long-run trend filter (days)
    "MAX_HOLD": 10,     # index max holding days
    "EXEC_LAG": 14,     # to_hourly lag -> position changes at 13:00 UTC
    "VOL_FLOOR": 0.05,  # annualized vol floor for sizing
    "POS_CAP": 1.0,     # per-instrument |exposure| cap
    "GROSS_CAP": 3.0,   # portfolio sum|exposure| cap
    "VOL_SPAN": 30,     # EWMA vol span (days) for sizing
}


def _fx_states(px: pd.DataFrame, L: int, z_in: float,
               z_out: float) -> pd.DataFrame:
    """Hysteresis state machine on z = (px - SMA_L) / SD_L. -1/0/+1."""
    ma = px.rolling(L).mean()
    sd = px.rolling(L).std()
    z = ((px - ma) / sd).to_numpy()
    T, N = z.shape
    st = np.zeros((T, N))
    for j in range(N):
        s = 0
        for t in range(T):
            zt = z[t, j]
            if np.isfinite(zt):
                if s == 0:
                    if zt > z_in:
                        s = -1
                    elif zt < -z_in:
                        s = 1
                elif (s == -1 and zt < z_out) or (s == 1 and zt > -z_out):
                    s = 0
            st[t, j] = s
    return pd.DataFrame(st, index=px.index, columns=px.columns)


def _idx_states(px: pd.DataFrame, vol_d: pd.DataFrame, D: int,
                z_entry: float, z_exit: float, trend_L: int,
                max_hold: int) -> pd.DataFrame:
    """Long-only dip states: enter after a D-day vol-scaled selloff while
    above the trend_L-day mean; exit on recovery or holding cap."""
    z = (px.pct_change(D) / (vol_d * np.sqrt(D / 365.25))).to_numpy()
    tv = (px > px.rolling(trend_L).mean()).to_numpy()
    T, N = z.shape
    st = np.zeros((T, N))
    for j in range(N):
        s, held = 0, 0
        for t in range(T):
            zt = z[t, j]
            if np.isfinite(zt):
                if s == 0:
                    if zt < -z_entry and tv[t, j]:
                        s, held = 1, 0
                else:
                    held += 1
                    if zt > z_exit or held >= max_hold:
                        s = 0
            st[t, j] = s
    return pd.DataFrame(st, index=px.index, columns=px.columns)


def _freeze_size(states: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    """Position = state x entry-day weight, held constant during the trade
    (avoids daily vol-tracking churn)."""
    sv, wv = states.to_numpy(), w.to_numpy()
    T, N = sv.shape
    out = np.zeros((T, N))
    for j in range(N):
        size = 0.0
        for t in range(T):
            if sv[t, j] != 0 and (t == 0 or sv[t - 1, j] != sv[t, j]):
                size = wv[t, j]
            out[t, j] = sv[t, j] * size
    return pd.DataFrame(out, index=states.index, columns=states.columns)


def make_positions(params: dict | None = None) -> pd.DataFrame:
    """Build the sleeve's hourly position frame (fraction of equity,
    FULL 2020-2025 sample) with the frozen defaults."""
    p = dict(PARAMS)
    if params:
        p.update(params)

    U = core.universe_frames()
    h_idx = U["ret"].index
    px = core.daily_closes(SYMBOLS)
    vol_d = (core.realized_vol(U["ret"][SYMBOLS], span_days=p["VOL_SPAN"])
             .resample("1D").last().reindex(px.index).ffill())

    st_fx = _fx_states(px[FX_CROSSES], p["L"], p["Z_IN"], p["Z_OUT"])
    st_ix = _idx_states(px[INDICES], vol_d[INDICES], p["D"], p["Z_ENTRY"],
                        p["Z_EXIT"], p["TREND_L"], p["MAX_HOLD"])
    states = pd.concat([st_fx, st_ix], axis=1)

    w = p["K"] / vol_d[SYMBOLS].clip(lower=p["VOL_FLOOR"])
    pos_d = _freeze_size(states, w).clip(-p["POS_CAP"], p["POS_CAP"])

    gross = pos_d.abs().sum(axis=1)
    pos_d = pos_d.mul((p["GROSS_CAP"] / gross).clip(upper=1.0), axis=0)

    return core.to_hourly(pos_d, h_idx,
                          lag_hours=p["EXEC_LAG"]).fillna(0.0).astype(float)


def window_metrics(pos: pd.DataFrame, start: str | None = None,
                   end: str | None = None, cost_mult: float = 1.0,
                   with_swap: bool = True) -> tuple[dict, core.SimResult]:
    """Metrics over a sub-window with positions zeroed outside it and the
    equity curve sliced to the window (avoids ffill of stale positions)."""
    p = pos.copy()
    if end is not None:
        p.loc[pd.Timestamp(end) + pd.Timedelta(hours=1):] = 0.0
    if start is not None:
        p.loc[:pd.Timestamp(start) - pd.Timedelta(hours=1)] = 0.0
    res = core.simulate(p, cost_mult=cost_mult, with_swap=with_swap)
    eq = res.equity
    if end is not None:
        eq = eq.loc[:end]
    if start is not None:
        eq = eq.loc[start:]
        eq = eq / eq.iloc[0]
    return core.compute_metrics(eq, pos=res.pos.loc[eq.index[0]:eq.index[-1]]), res


def turnover_cost_share(pos: pd.DataFrame) -> float:
    """Fraction of gross (pre-cost, pre-swap) pnl consumed by spread +
    commission over the full sample."""
    res = core.simulate(pos)
    eff = res.pos
    syms = list(eff.columns)
    U = core.universe_frames()
    held = eff.shift(1).fillna(0.0)
    gross = float((held * U["ret"][syms]).sum().sum())
    dpos = eff.diff().abs().fillna(eff.abs())
    unit = U["rel_spread"][syms] / 2.0 + core.commission_frac(tuple(core.ALL))[syms]
    tc = float((dpos * unit).sum().sum())
    return tc / gross if gross > 0 else float("nan")


if __name__ == "__main__":
    import json

    out_dir = _RESEARCH / "outputs"
    out_dir.mkdir(exist_ok=True)

    pos = make_positions()
    pos.to_parquet(out_dir / f"{NAME}_pos.parquet")

    m_dev, _ = window_metrics(pos, end=DEV_END)
    m_hold, _ = window_metrics(pos, start=HOLD_START)
    m_full, res_full = window_metrics(pos)

    print(f"DEV  2020-2023: {core.fmt_metrics(m_dev)}")
    print(f"HOLD 2024-2025: {core.fmt_metrics(m_hold)}")
    print(f"FULL 2020-2025: {core.fmt_metrics(m_full)}")

    share = turnover_cost_share(pos)
    print(f"turnover cost share of gross pnl (FULL): {share:.1%}")

    pnl_sym = (res_full.pnl_by_sym.sum() * 100).sort_values()
    report = {
        "name": NAME,
        "hypothesis": {
            "fx": "Related-economy/managed FX crosses mean-revert at "
                  "multi-day horizons; fade 60d z-score extremes with "
                  "hysteresis.",
            "indices": "Indices in uptrends (>200d MA) attract dip-buying "
                       "after sharp 5-day vol-scaled selloffs; long-only, "
                       "exit on recovery or 10-day cap.",
        },
        "symbols": SYMBOLS,
        "params": PARAMS,
        "metrics": {
            win: {
                "cagr": m["cagr"], "maxdd": m["maxdd"], "sharpe": m["sharpe"],
                "n_neg_years": m["n_neg_years"],
                "n_neg_quarters": m["n_neg_quarters"],
                "yearly": m["yearly"],
            }
            for win, m in [("dev", m_dev), ("hold", m_hold), ("full", m_full)]
        },
        "per_symbol_pnl_pct_full": {
            "top5": pnl_sym.tail(5).round(2).to_dict(),
            "bottom5": pnl_sym.head(5).round(2).to_dict(),
        },
        "turnover_cost_share": round(share, 4),
        "sensitivity_notes": (
            "DEV +/-30% neighbors (one param at a time, others frozen; "
            "base DEV Sharpe 0.96): L 42/78 -> 0.44/0.71; Z_IN 1.575/2.925 "
            "-> 0.53/0.93; Z_OUT 0.525/0.975 -> 0.71/0.99; D 4/6 -> "
            "0.90/0.97; Z_ENTRY 1.05/1.95 -> 0.66/0.89; K 0.049/0.091 -> "
            "1.03/0.94. All neighbors positive; FX leg params are the most "
            "sensitive (degrade toward faster/looser settings), index leg "
            "robust. Rejected on DEV: trend-strength entry filter, "
            "realized-vol regime filter, fast anchors (L<=40), daily "
            "vol-tracking resizing."
        ),
    }
    with open(out_dir / f"{NAME}_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"wrote {out_dir / f'{NAME}_pos.parquet'} and "
          f"{out_dir / f'{NAME}_report.json'}")
