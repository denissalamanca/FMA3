"""Seasonal sleeve: gold Asian-session long (XAUUSD, 23:00 -> 06:00 UTC).

Hypothesis (stated before fitting)
----------------------------------
Persistent flow-driven intraday seasonality in gold: physical/retail
accumulation during Asian trading hours (Tokyo 09:00-15:00 JST, Shanghai
morning session) pushes spot gold up overnight, while London/NY hours are
flat-to-negative (producer hedging, fix-related selling). Documented in the
literature as the "overnight gold drift" / gold-fixing intraday pattern.

Implementation
--------------
Long XAUUSD from the 23:00 UTC bar through the 05:00 UTC bar (earning bar
returns for hours 23:00-06:00 UTC), flat otherwise. The window:
  * starts AFTER the 22:00 UTC swap roll -> the position pays zero swap;
  * captures the 00:00-01:00 UTC exchange break gap (Tokyo open);
  * a Friday 23:00 entry stays frozen (no weekend bars) until the Monday
    01:00 UTC reopen, capturing the weekend Asia-demand gap - part of the
    same driver and of the originally registered 23-07 window.
Sizing is inverse-vol: w = min(1, kappa / max(vol, vol_floor)) with a 30-day
EWMA annualized vol, capped at |pos| <= 1.

Anti-overfit protocol
---------------------
All selection done on DEV (2020-01..2023-12-31). Candidate effects tested in
isolation (equity overnight / intraday short / turn-of-month, gold Asia long
and London-day short, FX local-hours depreciation for EUR/GBP/JPY/AUD, BTC
US-hours and weekend) - only this effect passed DEV pre-cost t >= 2.5 with a
plausible driver and positive pnl in every DEV year. HOLD (2024-2025) was
evaluated once with the frozen parameters below.

Frozen parameters (5): entry_hour=23, end_hour=6, kappa=0.15,
vol_floor=0.05, span_days=30.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import core

NAME = "seasonal"
SYMBOL = "XAUUSD"
DEV_END = "2023-12-31"
HOLD_START = "2024-01-01"


def make_positions(entry_hour: int = 23,
                   end_hour: int = 6,
                   kappa: float = 0.15,
                   vol_floor: float = 0.05,
                   span_days: int = 30) -> pd.DataFrame:
    """Build the sleeve's positions on the union hourly grid (FULL sample).

    Returns a DataFrame with a single column ``XAUUSD`` whose value at bar t
    is the signed fraction-of-equity exposure DECIDED at t (held over t+1,
    per the harness convention). The schedule is a deterministic function of
    the clock, so shifting it back one bar is causal; the vol scalar at t
    uses returns through bar t only.
    """
    U = core.universe_frames()
    idx = U["ret"].index
    h = idx.hour
    # hold-over-bar indicator: earn bar returns for hours {entry_hour, 0..end_hour-1}
    hold = pd.Series(((h == entry_hour) | (h < end_hour)).astype(float), index=idx)
    vol = core.realized_vol(U["ret"][[SYMBOL]], span_days=span_days)[SYMBOL]
    w = (kappa / vol.clip(lower=vol_floor)).clip(upper=1.0).fillna(0.0)
    pos = (hold.shift(-1).fillna(0.0) * w).to_frame(SYMBOL)
    return pos


def _window_metrics(res: core.SimResult, start=None, end=None) -> dict:
    eq = res.equity.loc[start:end]
    eq = eq / eq.iloc[0]
    return core.compute_metrics(eq, pos=res.pos.loc[start:end])


def _weekday_tstat(res: core.SimResult, start=None, end=None) -> float:
    dr = res.equity.resample("1D").last().dropna().pct_change().dropna()
    dr = dr.loc[start:end]
    dr = dr[dr.index.dayofweek < 5]
    return float(dr.mean() / dr.std() * np.sqrt(len(dr)))


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "outputs"
    out_dir.mkdir(exist_ok=True)

    pos = make_positions()
    pos.to_parquet(out_dir / f"{NAME}_pos.parquet")

    res = core.simulate(pos)
    res0 = core.simulate(pos, cost_mult=0.0)

    windows = {"dev": (None, DEV_END), "hold": (HOLD_START, None),
               "full": (None, None)}
    mets = {}
    for tag, (a, b) in windows.items():
        m = _window_metrics(res, a, b)
        mets[tag] = m
        print(f"{tag.upper():4s}: {core.fmt_metrics(m)}  "
              f"(weekday t-stat {_weekday_tstat(res, a, b):+.2f})")

    gross_full = res0.equity.iloc[-1] - 1.0
    net_full = res.equity.iloc[-1] - 1.0
    m0 = core.compute_metrics(res0.equity)
    cost_share = (m0["cagr"] - mets["full"]["cagr"]) / abs(m0["cagr"])

    pnl_sym = res.pnl_by_sym.sum().sort_values(ascending=False)
    report = {
        "name": NAME,
        "hypothesis": ("Gold accumulates during Asian trading hours "
                       "(physical/retail demand, Tokyo/Shanghai sessions) and is "
                       "flat-to-negative in London/NY hours; hold XAUUSD long "
                       "23:00->06:00 UTC only. Window starts after the 22:00 UTC "
                       "swap roll (zero swap) and holds Fri->Mon over the weekend "
                       "to capture the Monday Asia-open gap."),
        "params": {"entry_hour": 23, "end_hour": 6, "kappa": 0.15,
                   "vol_floor": 0.05, "span_days": 30},
        "metrics": {tag: {"cagr": m["cagr"], "maxdd": m["maxdd"],
                          "sharpe": m["sharpe"],
                          "n_neg_years": m["n_neg_years"],
                          "n_neg_quarters": m["n_neg_quarters"],
                          "yearly": m["yearly"]}
                    for tag, m in mets.items()},
        "per_symbol_pnl": {"top5": {k: float(v) for k, v in pnl_sym.head(5).items()},
                           "bottom5": {k: float(v) for k, v in pnl_sym.tail(5).items()}},
        "sensitivity_notes": (
            "DEV weekday t-stats (net), frozen elsewhere: end_hour 5/6/7 -> "
            "2.86/3.03/2.51; kappa 0.10/0.12/0.15/0.18 -> 3.24/3.18/3.03/3.02; "
            "span_days 20/30/40 -> 2.95/3.03/3.08. Entry hour is structural: "
            "starting at 22:00 UTC instead (before the swap roll, wider spreads, "
            "negative 22:00 bar) drops DEV t to 0.76; dropping the 23:00 entry "
            "bar (enter 01:00) kills the effect entirely (t -0.71) because the "
            "Tokyo-open break gap carries much of the return. Weekend-flat "
            "variant (no Fri->Mon hold) drops DEV Sharpe from 1.49 to ~1.1."),
        "turnover_cost_share": float(cost_share),
        "dev_selection": ("Effects tested in isolation on DEV and rejected: "
                          "equity overnight long ET16-09 (t 0.76), equity cash-session "
                          "short (negative), equity turn-of-month (t 1.31), equity "
                          "European-hours drift ET02-09 (t 2.30, 2023 negative), gold "
                          "London/NY-day short (t 0.25), USDJPY Tokyo-hours long "
                          "(t 1.07), EURUSD European-hours short (t 2.04), GBPUSD "
                          "local-hours short (t 0.80), AUDUSD local-hours short "
                          "(negative), EURUSD US-hours long (negative), BTC US-hours "
                          "long (t 1.14, 2022 -58%), BTC weekend short (negative)."),
    }
    with open(out_dir / f"{NAME}_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"gross(full) {gross_full:+.1%}  net(full) {net_full:+.1%}  "
          f"cost share of gross CAGR {cost_share:.1%}")
    print(f"wrote {out_dir / f'{NAME}_pos.parquet'} and "
          f"{out_dir / f'{NAME}_report.json'}")


if __name__ == "__main__":
    main()
