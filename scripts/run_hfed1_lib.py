"""Shared helpers for the H-FED experiment runners.

Canonical copies of the input-loading and metric helpers used by
run_hfed1.py (which inlines them — it was already running when this module
was factored out; the definitions are identical and covered by the same
verification chain). Import from here in all later runners.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
if str(_FMA3 / "engine") not in sys.path:
    sys.path.insert(0, str(_FMA3 / "engine"))

import record_engine as RE  # noqa: E402
import books                # noqa: E402

COVID_LO, COVID_HI = pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-15")


def crisis_tail(eq_close: pd.Series, eq_worst: pd.Series) -> float:
    """Worst-mark COVID-window drawdown vs the running all-history close peak."""
    peak = eq_close.cummax()
    win = (eq_worst.index >= COVID_LO) & (eq_worst.index <= COVID_HI)
    dd = (peak[win] - eq_worst[win]) / peak[win]
    return float(dd.max())


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Native frac matrices + native equity curves normalized to 1.0 at t0."""
    frac7 = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_frac_1h.parquet")
    frac34 = books.build_v34_frac_1h()
    eq7 = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_equity_1m.parquet")["eqc"]
    eq34 = pd.read_parquet(
        RE.PATHS.BASELINES / "fma2" / "v34_s10_pin_curve.parquet")["equity"]
    return frac7, frac34, eq7 / eq7.iloc[0], eq34 / eq34.iloc[0]


def ideal_metrics(ideal_daily: pd.Series) -> dict:
    """Frictionless bookkeeping-curve metrics (federation friction reference)."""
    r = ideal_daily.pct_change().dropna()
    cum = ideal_daily / ideal_daily.iloc[0]
    yrs = (ideal_daily.index[-1] - ideal_daily.index[0]).days / 365.25
    return {
        "cagr": float(cum.iloc[-1] ** (1 / yrs) - 1),
        "maxdd_close": float((1 - cum / cum.cummax()).max()),
        "sharpe": float(r.mean() / r.std() * np.sqrt(252)),
    }
