"""trend_v2 — robustified time-series momentum on metals + energy.

Universe: XAUUSD, XAGUSD, XBRUSD, XTIUSD, XNGUSD (XPTUSD excluded: 27bp spread).

Hypothesis (stated before fitting): supply/demand shocks in commodities create
multi-week trends because short-run supply and consumption are inelastic; an
ENSEMBLE of vol-normalized momentum lookbacks spanning ~3 weeks to ~6 months
is robust where any single lookback is fragile.

Signal (daily, from UTC-day closes):
  z_L   = (P_t / P_{t-L} - 1) / (sigma_daily * sqrt(L)),  L in LOOKBACKS
  s     = mean_L tanh(z_L / K)                      (continuous, saturating)
  s    *= fraction of legs agreeing in sign with s  (consensus conviction gate)
  s     = soft zero-deadband: sign(s) * max(|s|-S0, 0) / (1-S0)
Sizing: w = s * min(V0 / ann_vol, 1), XAG risk share halved (worst DEV trender,
highest-cost metal), |w| <= 1 per instrument.
Hysteresis: only retrade when |target - held| > DELTA * per-asset max weight.
Execution: daily at 05:00 UTC (early plateau — trend alpha decays intraday;
far from the 21:00-23:00 rollover spread widening).

Tuned on DEV (<= 2023-12-31) only; 6 free parameters, all frozen below.
De-risk overlay (halve gross on 20d vol doubling) was tested and REJECTED
(hurt DEV: vol spikes are when commodity trends pay).
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

NAME = "trend_v2"
SYMS: list[str] = ["XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD", "XNGUSD"]
LOOKBACKS: tuple[int, ...] = (15, 25, 40, 65, 95, 125)  # trading days (fixed design)

# ---- frozen parameters (tuned on DEV <= 2023-12-31 only) --------------------
K: float = 1.0          # tanh scale on the vol-normalized momentum z-score
DELTA: float = 0.15     # hysteresis deadband, fraction of per-asset max weight
S0: float = 0.15        # zero-signal soft deadband (conviction floor)
VOL_SPAN: int = 20      # EWMA span (trading days) for daily vol estimate
V0: float = 0.085       # per-asset annualized vol budget at full signal
XAG_SHARE: float = 0.5  # risk share multiplier for XAGUSD
EXEC_HOUR: int = 5      # UTC hour: new weights effective 05:00, trade bar 06:00

DEV_END = "2023-12-31"
HOLD_START = "2024-01-01"


def make_positions(k: float = K, delta: float = DELTA, s0: float = S0,
                   vol_span: int = VOL_SPAN, v0: float = V0,
                   xag_share: float = XAG_SHARE, exec_hour: int = EXEC_HOUR,
                   lookbacks: tuple[int, ...] = LOOKBACKS,
                   syms: list[str] | None = None) -> pd.DataFrame:
    """Build hourly positions (fraction of sleeve equity) on the union grid."""
    syms = SYMS if syms is None else syms
    U = core.universe_frames()
    idx = U["ret"].index
    dc = core.daily_closes(syms)               # UTC-day closes (through d 23:59)
    dret = dc.pct_change()

    sig_d = np.sqrt(dret.pow(2).ewm(span=vol_span, min_periods=10).mean())
    ann_vol = sig_d * np.sqrt(252.0)

    # ensemble of vol-normalized momentum legs
    legs = []
    for L in lookbacks:
        z = (dc / dc.shift(L) - 1.0) / (sig_d * np.sqrt(L))
        legs.append(np.tanh(z / k))
    s = sum(legs) / len(legs)
    # consensus conviction gate: scale by fraction of legs agreeing in sign
    agree = sum((np.sign(leg) == np.sign(s)).astype(float) for leg in legs) / len(legs)
    s = s * agree
    # soft zero-deadband: no position on weak, mixed signals
    if s0 > 0:
        s = np.sign(s) * (s.abs() - s0).clip(lower=0.0) / (1.0 - s0)

    # inverse-vol sizing with per-instrument cap
    max_w = (v0 / ann_vol).clip(upper=1.0)
    if "XAGUSD" in max_w.columns:
        max_w["XAGUSD"] = max_w["XAGUSD"] * xag_share
    target = (s * max_w).clip(-1.0, 1.0)

    # hysteresis: retrade only when the move exceeds delta * per-asset max weight
    tgt = target.to_numpy()
    mw = max_w.to_numpy()
    w = np.zeros_like(tgt)
    held = np.zeros(tgt.shape[1])
    for i in range(tgt.shape[0]):
        row_t, row_m = tgt[i], mw[i]
        valid = np.isfinite(row_t)
        band = delta * np.where(np.isfinite(row_m), row_m, 1.0)
        move = valid & (np.abs(row_t - held) > band)
        held = np.where(move, row_t, held)
        w[i] = held
    w = pd.DataFrame(w, index=dc.index, columns=list(syms))

    # daily weights (data through day d 23:59) -> effective d+1 at EXEC_HOUR,
    # traded on the next bar. Causal via core.to_hourly.
    pos = core.to_hourly(w, idx, lag_hours=exec_hour + 1)
    return pos.fillna(0.0)


def _slice_metrics(res: core.SimResult, start=None, end=None) -> dict:
    eq = res.equity.loc[start:end]
    eq = eq / eq.iloc[0]
    return core.compute_metrics(eq, pos=res.pos.loc[start:end])


if __name__ == "__main__":
    import json

    pos = make_positions()
    out_dir = _RESEARCH / "outputs"
    out_dir.mkdir(exist_ok=True)
    pos.to_parquet(out_dir / f"{NAME}_pos.parquet")

    res = core.simulate(pos)
    res0 = core.simulate(pos, cost_mult=0.0)

    m_dev = _slice_metrics(res, end=DEV_END)
    m_hold = _slice_metrics(res, start=HOLD_START)
    m_full = _slice_metrics(res)

    print(f"{NAME} — frozen params")
    print("DEV  (2020..2023):", core.fmt_metrics(m_dev))
    print("HOLD (2024..2025):", core.fmt_metrics(m_hold))
    print("FULL (2020..2025):", core.fmt_metrics(m_full))

    gross = res0.pnl_by_sym.sum().sum()
    net = res.pnl_by_sym.sum().sum()
    cost_share = float((gross - net) / abs(gross)) if gross != 0 else float("nan")
    print(f"turnover cost share (FULL, gross pnl basis): {cost_share:.1%}")
    print("net pnl by symbol (FULL):",
          {s_: round(float(v), 4) for s_, v in res.pnl_by_sym.sum().items()})

    report = {
        "name": NAME,
        "hypothesis": ("Inelastic short-run supply/demand makes commodity price "
                       "shocks persist for weeks-to-months; an ensemble of "
                       "vol-normalized momentum lookbacks (3w-6m) on metals+energy "
                       "captures this robustly where single lookbacks are fragile."),
        "universe": SYMS,
        "params": {"lookbacks": list(LOOKBACKS), "k": K, "delta": DELTA, "s0": S0,
                   "vol_span": VOL_SPAN, "v0": V0, "xag_share": XAG_SHARE,
                   "exec_hour_utc": EXEC_HOUR, "consensus_gate": True,
                   "derisk_overlay": "tested, rejected (hurt DEV)"},
        "dev": m_dev, "hold": m_hold, "full": m_full,
        "per_symbol_pnl": {
            "full_net": {s_: float(v) for s_, v in res.pnl_by_sym.sum().items()},
            "dev_net": {s_: float(v) for s_, v in
                        res.pnl_by_sym.loc[:DEV_END].sum().items()},
            "hold_net": {s_: float(v) for s_, v in
                         res.pnl_by_sym.loc[HOLD_START:].sum().items()},
        },
        "turnover_cost_share": cost_share,
        "sensitivity_notes": (
            "DEV Sharpe at frozen point 0.42; all +-30% perturbations stay in "
            "0.42-0.49: k 0.7->0.45, 1.3->0.48; vol_span 14->0.44, 26->0.43; "
            "delta 0.105->0.42, 0.195->0.49; s0=0->0.41; no-consensus->0.45; "
            "xag full-risk->0.35. Frozen point sits at the LOW edge of its own "
            "plateau (not a mined peak). Exec hour plateau 01:00-09:00 UTC; "
            "alpha decays if executed after ~13:00 (skip-recent momentum killed "
            "the signal => alpha concentrated in most recent days)."),
    }
    with open(out_dir / f"{NAME}_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"wrote {out_dir / f'{NAME}_pos.parquet'} and {NAME}_report.json")
