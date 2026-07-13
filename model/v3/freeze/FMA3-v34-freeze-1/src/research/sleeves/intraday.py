"""Intraday sleeve: US-index NY-open session continuation ("open-drive").

Hypothesis (stated before fitting): order-flow around the 9:30 ET cash open
ignites session-length momentum -- the direction and (vol-normalized)
magnitude of the 9:00-10:00 ET move predicts continued drift through the
session (10:00-15:00 ET).  Driver: informed positioning at the open plus
intraday momentum/hedging flows (Gao-Han-Li-Zhou-style first-interval
predictability).  The effect concentrates in the beta/growth indices
(USA500, USTEC); US30 showed no edge on DEV (t=0.34) and was dropped.

Candidates enumerated and killed on DEV 2020-2023 (tested in isolation,
required t>=2.5 and >=3/4 positive years): overnight-gap continuation,
afternoon/MOC momentum, lunch reversion, FX post-Asia unwind (4 majors),
FX London-move reversion in NY, XAU London-hours drift, XAU open-drive,
opening-range-breakout variants.  None survived; the z-weighted open-drive
on USA500/USTEC was the only configuration positive in all 4 DEV years.

Positions are INTRADAY ONLY: nonzero exclusively on rows 16:00-20:00 of the
data's server-time grid (GMT+2/+3, NY-anchored: row 16 contains the 9:30 ET
open), flat from the 21:00 row onward -> zero swap at the harness's >=22:00
charge row, no overnight gap risk, entries/exits far from the wide-spread
rollover window (23:00-01:00).

Timestamp note: the research grid is stamped in broker server time
(GMT+2/+3 tracking US DST, daily break at hour 0 = 17:00 NY), so NY-session
hours are stable in grid-hour terms year-round.

Frozen parameters (tuned on DEV = through 2023-12-31 only):
    symbols     = (USA500, USTEC)   ultra-cheap: ~1.1bp median spread
    entry_hour  = 16                signal = close[16] / close[15] - 1
    exit_hour   = 21                flat at the 21:00 row
    zcap        = 2.0               signal z clipped at +-2 then /2 -> [-1,1]
    span_days   = 60                EWMA span for |move| scale (causal, lag 1d)
    ref_vol     = 0.15              inverse-vol weight = min(1, 0.15/vol_30d)
    scale       = 1.111             sizes DEV weekday ann vol to ~11%
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core  # noqa: E402

NAME = "intraday"
SYMBOLS: tuple[str, ...] = ("USA500", "USTEC")
PARAMS: dict = {
    "symbols": list(SYMBOLS),
    "entry_hour": 16,
    "exit_hour": 21,
    "zcap": 2.0,
    "span_days": 60,
    "ref_vol": 0.15,
    "scale": 1.111,
}


def make_positions(symbols: tuple[str, ...] = SYMBOLS,
                   entry_hour: int = 16,
                   exit_hour: int = 21,
                   zcap: float = 2.0,
                   span_days: int = 60,
                   ref_vol: float = 0.15,
                   scale: float = 1.111) -> pd.DataFrame:
    """Full-period (2020-2025) hourly positions, fraction of sleeve equity.

    Causality: the position on row `entry_hour` of day d uses closes of rows
    entry_hour-1 and entry_hour of day d (both known at that row's close; the
    simulator holds pos[t] over bar t+1), an EWMA |move| scale lagged one day,
    and 30d EWMA vol through the end of day d-1.
    """
    U = core.universe_frames()
    idx = U["ret"].index
    close, hasb = U["close"], U["has_bar"]
    hours = idx.hour
    dates = idx.normalize()

    vol = core.realized_vol(U["ret"][list(symbols)], span_days=30)
    vol_d = vol.resample("1D").last().shift(1)          # known at day start

    hold = (hours >= entry_hour) & (hours < exit_hour)
    out: dict[str, np.ndarray] = {}
    for s in symbols:
        m_pre = (hours == entry_hour - 1) & hasb[s].to_numpy()
        c_pre = close[s][m_pre]
        c_pre.index = c_pre.index.normalize()
        c_pre = c_pre.groupby(c_pre.index).last()
        m_open = (hours == entry_hour) & hasb[s].to_numpy()
        c_open = close[s][m_open]
        c_open.index = c_open.index.normalize()
        c_open = c_open.groupby(c_open.index).last()

        mv = c_open / c_pre - 1.0                        # 9-10 ET open move
        sc = mv.abs().ewm(span=span_days, min_periods=20).mean().shift(1)
        z = (mv / sc).clip(-zcap, zcap) / zcap           # in [-1, 1]
        w = (ref_vol / vol_d[s]).clip(upper=1.0).reindex(z.index)
        sig = (z * w * scale).clip(-1.0, 1.0)            # per-instrument cap
        out[s] = np.where(hold, np.nan_to_num(sig.reindex(dates).to_numpy()),
                          0.0)
    return pd.DataFrame(out, index=idx)


def _window_metrics(eq: pd.Series, pos: pd.DataFrame,
                    lo: str | None, hi: str | None) -> dict:
    eq_w = eq.loc[lo:hi]
    eq_w = eq_w / eq_w.iloc[0]
    return core.compute_metrics(eq_w, pos=pos.loc[lo:hi])


def main() -> None:
    pos = make_positions()
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    pos.to_parquet(out_dir / f"{NAME}_pos.parquet")

    res = core.simulate(pos)
    res0 = core.simulate(pos, cost_mult=0.0)
    dev = _window_metrics(res.equity, pos, None, "2023-12-31")
    hold = _window_metrics(res.equity, pos, "2024-01-01", None)
    full = res.metrics
    print("DEV  :", core.fmt_metrics(dev))
    print("HOLD :", core.fmt_metrics(hold))
    print("FULL :", core.fmt_metrics(full))
    g, n = res0.metrics["cagr"], full["cagr"]
    print(f"FULL cost share of gross CAGR: {(g - n) / g:.2f}")
    print("per-symbol net pnl (FULL, frac of equity):",
          res.pnl_by_sym.sum().round(4).to_dict())


if __name__ == "__main__":
    main()
