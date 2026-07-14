"""trend_v2 scalar one-bar stepper — MQL5-faithful proxy.

SPEC: model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/trend_v2.py
(byte-identical to FMA2/research/sleeves/trend_v2.py — verified).

DAILY semantics (verified against core.daily_closes / core.universe_frames):
  dc = universe_frames(tuple(ALL))["close"][SYMS].resample("1D").last()
                                                 .dropna(how="all")
  i.e. CALENDAR days (crypto in ALL trades weekends, so every calendar day is
  present) with FFILLED STALE closes on non-trading days for these commodity
  symbols. Weekend rows therefore produce dret == 0.0 exactly (stale close /
  itself - 1) and DO count as ewm observations, and the momentum shift(L) is
  taken over CALENDAR-day rows, not trading days. The stepper must be fed one
  row per calendar day of that grid, all 5 symbols together.

Per-bar recurrence (one call to step() per daily row, ALL symbols together):
  dret   = c/c_prev - 1                       (pandas pct_change: div - 1)
  ewm of dret^2, span=20, min_periods=10, adjust=True, ignore_na=False —
         implemented with pandas' EXACT aggregations.pyx ewma recurrence
         (weighted/old_wt form, incl. the `weighted != cur` constant-series
         guard) so parity is bitwise, not approximate.
  sig_d  = sqrt(ewm_mean);  ann_vol = sig_d*sqrt(252)
  for L in (15,25,40,65,95,125):
      z_L  = (c/c[t-L] - 1) / (sig_d*sqrt(L));  leg_L = tanh(z_L / k)
  s      = (sum of legs)/6
  agree  = (1/6) * count(sign(leg) == sign(s))   (NaN compares -> 0)
  s     *= agree
  s      = sign(s) * max(|s|-S0, 0) / (1-S0)     (soft deadband, S0=0.15)
  max_w  = min(V0/ann_vol, 1), V0=0.085; XAGUSD max_w *= 0.5
  target = clip(s*max_w, -1, 1)
  hysteresis: band = DELTA*(max_w if finite else 1), DELTA=0.15
      retrade (held = target) only when isfinite(target) and
      |target-held| > band; else hold.
Hourly mapping (done by the caller/EA, not this class): held weights stamped
at day d 00:00 become effective d+1 05:00 UTC (to_hourly lag_hours=EXEC_HOUR+1
= 6), forward-filled onto the hourly union grid, NaN -> 0.

STYLE: scalar float64 only inside step(); no pandas, no numpy vectorization
across time, no future reads. numpy scalar tanh/sqrt allowed (same libm-class
double ops an MQL5 port would use).

STATE is explicitly serializable (get_state/set_state) so a live EA can
warm-start mid-history.
"""
from __future__ import annotations

import math

import numpy as np

NAME = "trend_v2"
SYMS = ("XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD", "XNGUSD")
LOOKBACKS = (15, 25, 40, 65, 95, 125)

# frozen parameters (spec lines 44-50)
K = 1.0
DELTA = 0.15
S0 = 0.15
VOL_SPAN = 20
VOL_MINP = 10
V0 = 0.085
XAG_SHARE = 0.5
EXEC_HOUR = 5          # daily weight effective d+1 05:00 UTC (lag_hours=6)

NAN = float("nan")

_SQRT_252 = float(np.sqrt(252.0))
_SQRT_L = tuple(float(np.sqrt(L)) for L in LOOKBACKS)
_MAX_L = max(LOOKBACKS)

# pandas ewm(span) -> com=(span-1)/2, alpha=1/(1+com)  (bitwise-identical to
# 2/(span+1): both are the correctly-rounded double of the same real number)
_ALPHA = 1.0 / (1.0 + (VOL_SPAN - 1) / 2.0)
_OLD_WT_FACTOR = 1.0 - _ALPHA
_NEW_WT = 1.0  # adjust=True


def _ieee_div(a: float, b: float) -> float:
    """IEEE-754 division on doubles (numpy/pandas semantics): x/0 -> +/-inf,
    0/0 and NaN/0 -> NaN. Python's `/` raises ZeroDivisionError instead."""
    if b == 0.0:
        if a != a or a == 0.0:
            return NAN
        neg = (math.copysign(1.0, a) * math.copysign(1.0, b)) < 0.0
        return -math.inf if neg else math.inf
    return a / b


def _sign(x: float) -> float:
    """np.sign semantics: NaN->NaN, +/-0 preserved."""
    if x != x:
        return NAN
    if x > 0.0:
        return 1.0
    if x < 0.0:
        return -1.0
    return x  # +/-0.0


class TrendV2Stepper:
    """Steps ALL 5 symbols together, one calendar-day close row per call."""

    def __init__(self) -> None:
        n = len(SYMS)
        # price history ring per symbol: closes of the previous rows,
        # newest last, capacity _MAX_L (125). hist[-L] == close at t-L.
        self._hist: list[list[float]] = [[] for _ in range(n)]
        # pandas-exact ewma state per symbol (on dret^2)
        self._ewm_weighted = [NAN] * n
        self._ewm_old_wt = [1.0] * n
        self._ewm_nobs = [0] * n
        # hysteresis
        self._held = [0.0] * n
        self._n_rows = 0
        # last-step intermediates (diagnostics / parity)
        self.last = {}

    # ------------------------------------------------------------------ step
    def step(self, closes) -> list[float]:
        """closes: sequence of 5 floats (NaN allowed pre-listing), in SYMS
        order — the daily-grid close row for this calendar day.
        Returns the held weight per symbol (fraction of sleeve equity),
        stamped at this day d 00:00, effective d+1 05:00 UTC."""
        n = len(SYMS)
        sig_d = [NAN] * n
        s_out = [NAN] * n
        mw_out = [NAN] * n
        tgt_out = [NAN] * n
        moved = [False] * n

        for i in range(n):
            c = float(closes[i])
            hist = self._hist[i]

            # ---- dret = pct_change: c/prev - 1 ------------------------------
            prev = hist[-1] if hist else NAN
            if c == c and prev == prev:
                dret = c / prev - 1.0
            else:
                dret = NAN
            x = dret * dret  # NaN propagates; npy_pow(a,2)==a*a

            # ---- ewm(span=20, min_periods=10).mean() on dret^2 --------------
            # pandas _libs/window/aggregations.pyx ewma, adjust=True,
            # ignore_na=False, normalize=True — exact recurrence.
            weighted = self._ewm_weighted[i]
            old_wt = self._ewm_old_wt[i]
            nobs = self._ewm_nobs[i]
            is_obs = x == x
            if is_obs:
                nobs += 1
            if weighted == weighted:
                # is_obs or not ignore_na  -> always True (ignore_na=False)
                old_wt *= _OLD_WT_FACTOR
                if is_obs:
                    if weighted != x:  # constant-series numerical guard
                        # pandas' compiled kernel (clang/arm64, default
                        # -ffp-contract) contracts `old_wt*weighted + new_wt*x`
                        # to fma(old_wt, weighted, new_wt*x) — measured: fma
                        # is bitwise-identical to pandas 2.3.3, the plain
                        # two-op form differs by <=1.2e-15 rel. An MQL5 port
                        # without fma inherits only that ulp-level residual.
                        weighted = math.fma(old_wt, weighted, _NEW_WT * x)
                        weighted /= old_wt + _NEW_WT
                    old_wt += _NEW_WT  # adjust=True
            elif is_obs:
                weighted = x
            self._ewm_weighted[i] = weighted
            self._ewm_old_wt[i] = old_wt
            self._ewm_nobs[i] = nobs
            ewm_mean = weighted if nobs >= VOL_MINP else NAN

            sig = float(np.sqrt(ewm_mean)) if ewm_mean == ewm_mean else NAN
            sig_d[i] = sig
            ann_vol = sig * _SQRT_252

            # ---- ensemble of vol-normalized momentum legs -------------------
            legs = []
            for j, L in enumerate(LOOKBACKS):
                p_l = hist[-L] if len(hist) >= L else NAN
                if c == c and p_l == p_l:
                    num = c / p_l - 1.0
                else:
                    num = NAN
                z = _ieee_div(num, sig * _SQRT_L[j])  # NaN/inf per IEEE
                legs.append(float(np.tanh(z / K)))

            acc = 0.0
            for leg in legs:
                acc += leg
            s = acc / 6.0

            # consensus gate: fraction of legs agreeing in sign with s
            sgn_s = _sign(s)
            agree_cnt = 0.0
            for leg in legs:
                if _sign(leg) == sgn_s:  # NaN==NaN is False -> contributes 0
                    agree_cnt += 1.0
            agree = agree_cnt / 6.0
            s = s * agree

            # soft zero-deadband: sign(s)*(|s|-S0).clip(0)/(1-S0)
            a = abs(s) - S0  # NaN propagates (abs(NaN)=NaN)
            if a < 0.0:
                a = 0.0  # NaN stays NaN (comparison False)
            s = (_sign(s) * a) / (1.0 - S0)
            s_out[i] = s

            # ---- inverse-vol sizing with per-instrument cap -----------------
            mw = _ieee_div(V0, ann_vol)  # ann_vol==0 -> inf -> clipped to 1
            if mw > 1.0:
                mw = 1.0  # clip(upper=1): NaN stays NaN
            if SYMS[i] == "XAGUSD":
                mw = mw * XAG_SHARE
            mw_out[i] = mw

            tgt = s * mw
            if tgt > 1.0:
                tgt = 1.0
            elif tgt < -1.0:
                tgt = -1.0
            tgt_out[i] = tgt

            # ---- hysteresis -------------------------------------------------
            band = DELTA * (mw if math.isfinite(mw) else 1.0)
            if math.isfinite(tgt) and abs(tgt - self._held[i]) > band:
                self._held[i] = tgt
                moved[i] = True

            # ---- roll price history ----------------------------------------
            hist.append(c)
            if len(hist) > _MAX_L:
                del hist[0]

        self._n_rows += 1
        self.last = {"sig_d": sig_d, "s": s_out, "max_w": mw_out,
                     "target": tgt_out, "moved": moved,
                     "held": list(self._held)}
        return list(self._held)

    # ------------------------------------------------------------- state I/O
    def get_state(self) -> dict:
        """JSON-serializable full state for EA warm-start."""
        return {
            "name": NAME,
            "syms": list(SYMS),
            "n_rows": self._n_rows,
            "hist": [list(h) for h in self._hist],
            "ewm_weighted": list(self._ewm_weighted),
            "ewm_old_wt": list(self._ewm_old_wt),
            "ewm_nobs": list(self._ewm_nobs),
            "held": list(self._held),
        }

    def set_state(self, st: dict) -> None:
        assert list(st["syms"]) == list(SYMS)
        self._n_rows = int(st["n_rows"])
        self._hist = [list(map(float, h)) for h in st["hist"]]
        self._ewm_weighted = [float(v) for v in st["ewm_weighted"]]
        self._ewm_old_wt = [float(v) for v in st["ewm_old_wt"]]
        self._ewm_nobs = [int(v) for v in st["ewm_nobs"]]
        self._held = [float(v) for v in st["held"]]
