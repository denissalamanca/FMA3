"""FMA3 engine-of-record wrapper around FMA2's true 1-minute account engine.

The campaign's ENGINE OF RECORD is FableMultiAssets2's single cross-margined
1-minute worst-mark account engine
(``FMA2/research/account_engine_1m.py::simulate_account_1m``), exactly as it is
driven by the official pin script ``FMA2/research/eval_v34_pin_s10.py``.  Every
shipped FMA3 number must come from that engine — this module IMPORTS it from
the read-only parent repo rather than copying it, because the FMA2 copy is the
verified artifact (byte-reproducing the pinned v3.4 reference); a copy would
silently fork the source of truth.

WHY the import gymnastics below
-------------------------------
FMA2's ``research/core.py`` inserts NewStrategyFable5 (NSF5) onto ``sys.path``
and imports NSF5's top-level ``config`` and ``engine`` packages.  FMA3 has its
own ``config/`` and ``engine/`` directories, so FMA3's repo root must NEVER be
placed on ``sys.path`` in a process that also runs FMA2 code — otherwise
``sys.modules['config']`` / ``sys.modules['engine']`` can resolve to the wrong
repo and the parent imports break (NSF5's ``config`` is a namespace package,
which makes the collision silent rather than loud).  We therefore load FMA3's
canonical paths module (``config/paths.py``) by FILE LOCATION under the
private name ``fma3_paths``, and only put the two FMA2 entries the pin script
itself uses onto ``sys.path``.

QUARTER-RANGE BOUNDARY (documented limitation)
----------------------------------------------
``simulate_account_1m`` hardcodes ``pd.period_range('2020Q1', '2025Q4')``
internally (account_engine_1m.py line 228).  Per campaign rules FMA2 is
read-only, so this wrapper parameterizes the quarter range AT THE WRAPPER
BOUNDARY instead of inside the engine:

* the requested ``[start_quarter, end_quarter]`` must be a sub-range of
  2020Q1..2025Q4 (a ``ValueError`` is raised otherwise — extending the sample
  would require editing FMA2);
* for a strict sub-range, positions outside the range are zeroed BEFORE the
  engine runs (the engine still iterates all 24 quarters, holding no positions
  and hence flat equity outside the range — a pure runtime cost, not a
  correctness one), and the returned curves are trimmed to the range before
  metrics are computed;
* for the full default range the engine's own metric dict is used unchanged,
  which is what guarantees bit-identical reproduction of the pinned reference.

INPUT CONVENTION (FMA2 book convention)
---------------------------------------
``frac_1h``: hourly position matrix, tz-naive broker SERVER time index,
instrument columns from FMA2 ``core.ALL``, values = signed notional exposure
as a fraction of joint account equity decided at hour h.  The engine maps the
hour-h row onto hour h+1's minutes (``prev_hour = minute.floor('h') - 1h``),
so the signal executes at hour h+1's first traded minute's OPEN — a >=1-minute
causal gap.  This is the FINAL matrix: any global scale and hard limits
(``ensemble.apply_hard_limits``) must already be baked in by the caller.

The house bootstrap (``worst_mark_breach``) is imported from the pin script
itself — same function object, zero replication drift: stationary 20d-block
bootstrap, 5000 paths, seed 20260709, co-timed daily worst/close dip factors.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]


def _load_fma3_paths():
    """Load FMA3/config/paths.py by file location under a collision-free name.

    See module docstring: importing it as ``config.paths`` would poison
    ``sys.modules['config']`` for FMA2/NSF5 code running in this process.
    """
    if "fma3_paths" in sys.modules:
        return sys.modules["fma3_paths"]
    spec = importlib.util.spec_from_file_location(
        "fma3_paths", _FMA3 / "config" / "paths.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fma3_paths"] = mod
    spec.loader.exec_module(mod)
    return mod


PATHS = _load_fma3_paths()

# sys.path bootstrap, mirroring eval_v34_pin_s10.py exactly: FMA2/research
# first (top-level modules core / ensemble / account_engine_1m), then FMA2
# root (packages research.*, ext_import via research).  FMA2's core.py adds
# NSF5 itself for config.settings / engine.costs.
for _p in (str(PATHS.FMA2), str(PATHS.FMA2 / "research")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core                          # noqa: E402  FMA2 research core
import account_engine_1m as A1       # noqa: E402  THE engine of record
from eval_v34_pin_s10 import worst_mark_breach  # noqa: E402  house bootstrap

__all__ = ["run_record", "worst_mark_breach", "ENGINE_QUARTERS", "PATHS"]

# Mirror of the range hardcoded inside simulate_account_1m (read-only FMA2).
ENGINE_QUARTERS = pd.period_range("2020Q1", "2025Q4", freq="Q")


def _close_mark_maxdd(eq_close: np.ndarray) -> float:
    """Max drawdown of the close-mark equity curve (peak-to-trough on closes).

    This is what ``core.compute_metrics`` computes BEFORE the engine overrides
    ``maxdd`` with the worst-mark version; we report both explicitly so the
    two conventions are never conflated downstream.
    """
    peak = np.maximum.accumulate(eq_close)
    return float(((peak - eq_close) / np.maximum(peak, 1e-9)).max())


def run_record(frac_1h: pd.DataFrame, *,
               start_quarter: str = "2020Q1",
               end_quarter: str = "2025Q4",
               initial: float = 10_000.0,
               label: str,
               verbose: bool = True,
               run_bootstrap: bool = True) -> dict:
    """Run an hourly fraction-of-equity book through the engine of record.

    Parameters
    ----------
    frac_1h : hourly position matrix (server-time index, instrument columns,
        fraction-of-equity values; FMA2 convention — hour-h signal executes at
        hour h+1's first traded minute open).  Must be the FINAL matrix
        (scale + hard limits already applied).
    start_quarter, end_quarter : calendar-quarter labels; must lie within the
        engine's baked-in 2020Q1..2025Q4 sample (see module docstring).
    initial : starting balance in EUR.
    label : required run tag, echoed into the result (bookkeeping — every
        record-engine number in FMA3 must be attributable to a named run).
    verbose : per-quarter progress lines from the engine.
    run_bootstrap : compute the house 20d-block worst-mark breach bootstrap
        (~1 min); disable only for throwaway screens.

    Returns
    -------
    dict with the standard metric block —
        cagr, maxdd_worst (co-timed minute worst-mark DD, the headline
        convention), maxdd_close (close-mark DD), sharpe (daily close, 252),
        final_equity, n_trades, years, yearly (per-year returns),
        quarterly (calendar-quarter close-to-close M2M returns),
        neg_years / neg_quarters (lists), n_neg_years / n_neg_quarters,
        breach (breach_close, breach_worst, median_dd_worst, p95_dd_worst),
        curves {'equity': eq_close 1m Series, 'worst': eq_worst 1m Series},
        engine_metrics (the raw metric dict, incl. gates/fitness).
    """
    q0 = pd.Period(start_quarter, freq="Q")
    q1 = pd.Period(end_quarter, freq="Q")
    if q0 > q1:
        raise ValueError(f"start_quarter {q0} is after end_quarter {q1}")
    if q0 < ENGINE_QUARTERS[0] or q1 > ENGINE_QUARTERS[-1]:
        raise ValueError(
            f"requested range {q0}..{q1} exceeds the engine-of-record sample "
            f"{ENGINE_QUARTERS[0]}..{ENGINE_QUARTERS[-1]} (baked into FMA2 "
            "account_engine_1m.simulate_account_1m; FMA2 is read-only)")
    if not isinstance(frac_1h.index, pd.DatetimeIndex) or frac_1h.index.tz is not None:
        raise ValueError("frac_1h must have a tz-naive (server-time) DatetimeIndex")

    full_range = (q0 == ENGINE_QUARTERS[0]) and (q1 == ENGINE_QUARTERS[-1])

    pos = frac_1h
    if not full_range:
        # Zero positions outside the requested range so the engine (which
        # always runs 2020Q1..2025Q4) holds nothing and stays flat there.
        pos = frac_1h.copy()
        outside = (pos.index < q0.start_time) | (pos.index > q1.end_time)
        pos.loc[outside, :] = 0.0

    eq_c, eq_w, m_eng = A1.simulate_account_1m(
        pos, initial=initial, verbose=verbose)

    if full_range:
        m = m_eng
    else:
        keep = (eq_c.index >= q0.start_time) & (eq_c.index <= q1.end_time)
        eq_c, eq_w = eq_c[keep], eq_w[keep]
        # Recompute metrics on the trimmed curve.  The balance is exactly
        # `initial` at range start (zero positions => no trades/swaps before),
        # so normalizing by `initial` matches the engine's own convention.
        m = core.compute_metrics(eq_c / initial)
        peak = np.maximum.accumulate(eq_c.to_numpy())
        m["maxdd"] = float(((peak - eq_w.to_numpy())
                            / np.maximum(peak, 1e-9)).max())
        m["final_equity"] = float(eq_c.iloc[-1])
        # All trades occur inside the range (flat outside by construction).
        m["n_trades"] = int(m_eng["n_trades"])

    maxdd_close = _close_mark_maxdd(eq_c.to_numpy())

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
