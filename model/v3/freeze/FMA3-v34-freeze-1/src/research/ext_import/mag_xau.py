"""MAG_XAU — external import (v3.0), ported from NewStrategyFable5.

Authoritative spec: FABLE_DISCOVERY_LOG.md "NEW STRONG ADD — MAG_XAU" + the
from-scratch reimplementation cand_verify3.my_magnet (base cell wc_mag_b18m3).

Alpha (gold $100 round-number magnet): LONG XAUUSD while the prior daily mid sits
between mind=3% and band=18% of a $100 step BELOW its nearest $100 round level
(breakout-bid / stop-cluster / option-barrier magnet pulls price up through the
round number). Single-leg gold, 100% long, ~18-22% active.

Sizing = vt / sigma_ann, vt=0.15, sigma_ann = 20d daily-return std x sqrt(252),
capped 6x. Causal: distance uses the PRIOR daily mid (shift 1); vol shifted 1.
Base spec = step $100, band 0.18, mind 0.03, offset 0, side +1 (long).

Reproduced exactly in their both-feeds gauntlet (verify/reproduction.json):
    v_mag_repro  duka Sh 1.10 / ic 1.38   (ADD)
and every control dies (placebo offsets, side-flip short, silver $2 grid).

LIVE-EXECUTION CAVEAT (their skeptic note): the drift is FAST (1-2 days) — a
lag+1d variant halves to +0.049 (watch). Base spec (shift(1) + next-bar-open) is
fine, but execution must NOT be slow.

CONVENTIONS / port notes (see PORT_NOTES.md):
  * Their "notional multiple of balance" == OUR "fraction of equity".
  * Both the signal and the vol denominator are shifted 1 day (sig.shift(1),
    _vol_scale.shift(1)); this is reproduced by building the RAW daily target
    (no manual shift) and mapping it with core.to_hourly(lag_hours=1), whose +1
    day offset applies the same one-day causal delay.
  * Bar stamps are broker SERVER time in both repos.

make_positions() -> hourly position DataFrame on core's server-time grid.
NOTE: builds positions only; per governance NOT evaluated on our research_cache.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import research.core as core

SYM = "XAUUSD"
STEP = 100.0
BAND = 0.18
MIND = 0.03
OFFSET = 0.0
SIDE = 1.0
VT = 0.15
CAP = 6.0
VOL_WIN = 20


def _daily_mid(sym: str) -> pd.Series:
    return core.load_hourly(sym)["c"].resample("1D").last().dropna()


def magnet_daily(d: pd.Series, *, step: float = STEP, band: float = BAND,
                 mind: float = MIND, offset: float = OFFSET, side: float = SIDE,
                 vt: float = VT, cap: float = CAP, vol_win: int = VOL_WIN
                 ) -> pd.Series:
    """RAW daily target (pre one-day-shift) — matches cand_verify3.my_magnet with
    the shifts factored out so core.to_hourly applies them."""
    near = ((d / step - offset).round() + offset) * step
    dist = (d - near) / step
    if side > 0:
        sig = ((dist < -mind) & (dist > -band)).astype(float)
    else:
        sig = -((dist > mind) & (dist < band)).astype(float)
    ann = d.pct_change().rolling(vol_win).std() * np.sqrt(252)
    return (sig * vt / ann).clip(-cap, cap)


def make_positions() -> pd.DataFrame:
    hgrid = core.universe_frames(tuple(core.ALL))["ret"].index
    raw = magnet_daily(_daily_mid(SYM)).to_frame(SYM)
    # core.to_hourly applies the +1-day causal shift + ffill onto the hourly grid
    pos = core.to_hourly(raw, hgrid, lag_hours=1).fillna(0.0)
    return pos.reindex(columns=[SYM])


if __name__ == "__main__":
    pos = make_positions()
    active = (pos.abs().sum(axis=1) > 0)
    print("MAG_XAU:", pos.shape, "active-bar fraction",
          round(float(active.mean()), 3))
