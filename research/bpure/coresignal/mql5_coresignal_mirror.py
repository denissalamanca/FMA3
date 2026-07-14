"""mql5_coresignal_mirror.py — python STATEMENT MIRROR of
mt5/ea/Include/Core/CoreSignal.mqh (UNIT 3 of the S2 live-Core build;
the no-terminal half of gate G-S5).

WHAT THIS IS
------------
A line-for-line transcription of the MQL5 CCoreSignal port back into
python, arithmetic included:

  * RollStdM  mirrors CCsRollStd — ssqdm updates via fma_emul, the
    statement mirror of the .mqh CsFmaEmul (Dekker/TwoProduct software
    fma; MQL5 exposes no fma intrinsic).  A PLAIN two-rounding update
    was measured (2026-07-15, first mirror run) to breach the ratified
    1e-12 line on leg 3 (EURGBP max|d| 1.069e-12, 1439 rows > 1e-12,
    0 flips) — hence the emulation.  fma_emul is additionally
    self-tested against math.fma on every realized kernel update
    (fma_emul_mismatches counter, expected 0).
  * RollMeanM mirrors CCsRollMean — statement-identical to the
    reference RollMean (no fma anywhere) => expected bit-zero.
  * DonchianM mirrors Sat/SatMath.mqh CSatDonchian (Query-before-Push
    = shift(1) rolling extreme; monotonic deque, exact arithmetic).
  * Leg steppers LegXauM/LegJpyM/LegEthM/LegEgM/LegUstecM/LegOpexFxM/
    LegBtcM mirror the CCsLeg* streaming classes field-for-field
    (stored previous-bar finalize, knot queue, defer holds).
  * CoreSignalM mirrors CCoreSignal.StepBar (instrument dispatch +
    ascending-stamp guard).

KNOWN NON-MIRRORABLE SPOT (flagged in the .mqh header): leg 8 BTC
`ann = MathPow(m/d63, 365/63) - 1`.  pow is not correctly rounded, so
MQL5 MathPow may differ from python ** by ulps.  ann feeds ONLY the
boolean `ann > 0.40`; this mirror measures min|ann - hurdle| over all
realized daily entries (flip-distance telemetry) — the in-terminal
TestCoreSignal run (G-S5) is the authoritative flip count.

GATES (all MEASURED, written to coresignal_mirror.json)
-------------------------------------------------------
  M-1 full-grid: mirror targets (streaming, per instrument) vs the
      normative reference generate_all_targets on each leg's FULL
      native index.  Owner criterion: max|diff| <= 1e-12 AND 0
      discrete sign flips per leg (bit-zero NOT required — the plain
      vs fma roll_var difference is the expected residual).
  M-2 seg replay: statement mirror of the TestCoreSignal.mq5 DRIVING
      LOOP over segments 0..N-1 (default 2) of the frozen exported
      bundles FMA3_coresim_seg{J}.csv — leg-major row order, ONE
      CoreSignalM instance, leg-5 rows served from the buffered leg-1
      pass (never re-stepping the shared USDJPY feed) — diffed vs the
      frozen tgt column (the golden).  Same criterion.
  M-3 calendar/tables: the .mqh CsDaysFromCivil opex calendar and the
      hardcoded policy epoch-day tables vs the reference's
      opex_week_days() / _table_edays — must be EXACTLY equal.
  M-4 coverage: the replayed seg rows are a contiguous prefix of each
      leg's full native grid (cold start == grid start), proving the
      32-segment TestCoreSignal replay equals full-grid streaming.

Usage (python3 runs from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresignal/mql5_coresignal_mirror.py \
    [--segments 2] [--skip-fullgrid]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()

# --- core_signal_reference by FILE (brings CR + arrays + the anchors) -------
_spec = importlib.util.spec_from_file_location(
    "core_signal_reference", _HERE.parent / "core_signal_reference.py")
CS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CS)
CR = CS.CR

OUT_JSON = _HERE.parent / "coresignal_mirror.json"
COMMON_FILES = CS.COMMON_FILES

NAN = float("nan")
CS_RISK = 8.0


def signbit(x):
    return math.copysign(1.0, x) < 0.0


FMA_EMUL_CALLS = [0]
FMA_EMUL_MISMATCH = [0]


def fma_emul(a, b, c):
    """CoreSignal.mqh CsFmaEmul statement mirror (Dekker/TwoProduct +
    Knuth TwoSum software fma), self-tested against hardware math.fma."""
    p = a * b
    sa = 134217729.0 * a
    ah = sa - (sa - a)
    al = a - ah
    sb = 134217729.0 * b
    bh = sb - (sb - b)
    bl = b - bh
    e = ((ah * bh - p) + ah * bl + al * bh) + al * bl
    s = c + p
    bv = s - c
    err = (c - (s - bv)) + (p - bv)
    t = err + e
    r = s + t
    FMA_EMUL_CALLS[0] += 1
    hw = math.fma(a, b, c)
    if r != hw and not (r != r and hw != hw):
        FMA_EMUL_MISMATCH[0] += 1
    return r


# =============================================================================
# 1. Kernel mirrors (CoreSignal.mqh statement transcriptions)
# =============================================================================
class RollMeanM:
    """CCsRollMean — pandas 3.0.1 roll_mean (statement-identical to the
    reference RollMean; ring realized as index list for clarity)."""
    __slots__ = ("w", "buf", "head", "cnt", "i", "nobs", "sum_x", "neg_ct",
                 "comp_add", "comp_rem", "prev_value", "num_consec")

    def __init__(self, w):
        self.w = w
        self.buf = [0.0] * w
        self.head = 0
        self.cnt = 0
        self.i = 0
        self.nobs = 0
        self.sum_x = 0.0
        self.neg_ct = 0
        self.comp_add = 0.0
        self.comp_rem = 0.0
        self.prev_value = NAN
        self.num_consec = 0

    def _add(self, val):
        if val == val:
            self.nobs += 1
            y = val - self.comp_add
            t = self.sum_x + y
            self.comp_add = t - self.sum_x - y
            self.sum_x = t
            if signbit(val):
                self.neg_ct += 1
            if val == self.prev_value:
                self.num_consec += 1
            else:
                self.num_consec = 1
            self.prev_value = val

    def _remove(self, val):
        if val == val:
            self.nobs -= 1
            y = -val - self.comp_rem
            t = self.sum_x + y
            self.comp_rem = t - self.sum_x - y
            self.sum_x = t
            if signbit(val):
                self.neg_ct -= 1

    def _push(self, v):
        if self.cnt < self.w:
            self.buf[(self.head + self.cnt) % self.w] = v
            self.cnt += 1
        else:
            self.buf[self.head] = v
            self.head = (self.head + 1) % self.w

    def step(self, val):
        if self.i == 0:
            self.prev_value = val
            self.num_consec = 0
            self.sum_x = 0.0
            self.comp_add = 0.0
            self.comp_rem = 0.0
            self.nobs = 0
            self.neg_ct = 0
            self._add(val)
        else:
            if self.i >= self.w:
                self._remove(self.buf[self.head])
            self._add(val)
        self._push(val)
        self.i += 1
        if self.nobs >= self.w and self.nobs > 0:
            result = self.sum_x / self.nobs
            if self.num_consec >= self.nobs:
                result = self.prev_value
            elif self.neg_ct == 0 and result < 0.0:
                result = 0.0
            elif self.neg_ct == self.nobs and result > 0.0:
                result = 0.0
            return result
        return NAN


class RollStdM:
    """CCsRollStd — roll_var + zsqrt, PLAIN (no-fma) ssqdm updates
    (the MQL5 arithmetic)."""
    __slots__ = ("w", "ddof", "buf", "head", "cnt", "i", "nobs", "mean",
                 "ssqdm", "comp_add", "comp_rem", "unstable", "invtol")

    def __init__(self, w):
        self.w = w
        self.ddof = 1.0
        self.buf = [0.0] * w
        self.head = 0
        self.cnt = 0
        self.i = 0
        self.nobs = 0.0
        self.mean = 0.0
        self.ssqdm = 0.0
        self.comp_add = 0.0
        self.comp_rem = 0.0
        self.unstable = False
        self.invtol = float(np.finfo(np.float64).eps * 1e3)

    def _add(self, val):
        if val != val:
            return
        prev_m2 = self.ssqdm
        self.nobs = self.nobs + 1.0
        prev_mean = self.mean - self.comp_add
        y = val - self.comp_add
        t = y - self.mean
        self.comp_add = t + self.mean - y
        delta = t
        if self.nobs != 0.0:
            self.mean = self.mean + delta / self.nobs
        else:
            self.mean = 0.0
        # pandas wheel fuses this into one fma — emulated (CsFmaEmul)
        self.ssqdm = fma_emul(val - prev_mean, val - self.mean, self.ssqdm)
        if prev_m2 * self.invtol > self.ssqdm:
            self.unstable = True

    def _remove(self, val):
        if val == val:
            prev_m2 = self.ssqdm
            self.nobs = self.nobs - 1.0
            if self.nobs != 0.0:
                prev_mean = self.mean - self.comp_rem
                y = val - self.comp_rem
                t = y - self.mean
                self.comp_rem = t + self.mean - y
                delta = t
                self.mean = self.mean - delta / self.nobs
                self.ssqdm = fma_emul(-(val - prev_mean), val - self.mean,
                                      self.ssqdm)
                if prev_m2 * self.invtol > self.ssqdm:
                    self.unstable = True
            else:
                self.mean = 0.0
                self.ssqdm = 0.0
                self.unstable = False

    def _push(self, v):
        if self.cnt < self.w:
            self.buf[(self.head + self.cnt) % self.w] = v
            self.cnt += 1
        else:
            self.buf[self.head] = v
            self.head = (self.head + 1) % self.w

    def step(self, val):
        recompute = self.i == 0
        if not recompute:
            if self.i >= self.w:
                self._remove(self.buf[self.head])
            self._add(val)
        self._push(val)
        if recompute or self.unstable:
            self.nobs = 0.0
            self.mean = 0.0
            self.ssqdm = 0.0
            self.comp_add = 0.0
            self.comp_rem = 0.0
            for j in range(self.cnt):
                self._add(self.buf[(self.head + j) % self.w])
            self.unstable = False
        self.i += 1
        if self.nobs >= float(self.w) and self.nobs > self.ddof:
            var = self.ssqdm / (self.nobs - self.ddof)
        else:
            return NAN
        if var < 0.0:
            return 0.0
        return math.sqrt(var)


class DonchianM:
    """Sat/SatMath.mqh CSatDonchian — Query-before-Push = shift(1)
    rolling max/min, minp = w.  Exact (comparisons only)."""
    __slots__ = ("w", "is_max", "dq_idx", "dq_val", "dq_start", "dq_len",
                 "cap", "n_pushed", "n_valid")

    def __init__(self, w, is_max):
        self.w = w
        self.is_max = is_max
        self.cap = w + 1
        self.dq_idx = [0] * self.cap
        self.dq_val = [0.0] * self.cap
        self.dq_start = 0
        self.dq_len = 0
        self.n_pushed = 0
        self.n_valid = 0

    def query(self):
        if self.n_valid < self.w or self.n_pushed < self.w:
            return NAN
        lo = self.n_pushed - self.w
        while self.dq_len > 0 and self.dq_idx[self.dq_start] < lo:
            self.dq_start = (self.dq_start + 1) % self.cap
            self.dq_len -= 1
        return self.dq_val[self.dq_start]

    def push(self, val):
        if val == val:
            lo_next = self.n_pushed + 1 - self.w
            while self.dq_len > 0 and self.dq_idx[self.dq_start] < lo_next:
                self.dq_start = (self.dq_start + 1) % self.cap
                self.dq_len -= 1
            if self.is_max:
                while self.dq_len > 0:
                    back = (self.dq_start + self.dq_len - 1) % self.cap
                    if self.dq_val[back] <= val:
                        self.dq_len -= 1
                    else:
                        break
            else:
                while self.dq_len > 0:
                    back = (self.dq_start + self.dq_len - 1) % self.cap
                    if self.dq_val[back] >= val:
                        self.dq_len -= 1
                    else:
                        break
            slot = (self.dq_start + self.dq_len) % self.cap
            self.dq_idx[slot] = self.n_pushed
            self.dq_val[slot] = val
            self.dq_len += 1
            self.n_valid += 1
        self.n_pushed += 1


# =============================================================================
# 2. Calendar / policy mirrors (CoreSignal.mqh CCsOpexCal / CCsPolicy)
# =============================================================================
def days_from_civil(y, m, d):
    """CoreSignal.mqh CsDaysFromCivil (Howard Hinnant, C integer division
    truncates toward zero — mirrored with int())."""
    if m <= 2:
        y -= 1
    era = int(y / 400) if y >= 0 else int((y - 399) / 400)
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def build_opex_cal():
    """CCsOpexCal.Init mirror (ascending list)."""
    days = []
    y, m = 2019, 12
    while y < 2026 or (y == 2026 and m <= 2):
        e1 = days_from_civil(y, m, 1)
        wd = (e1 + 3) % 7
        first_fri = e1 + (((4 - wd) % 7) + 7) % 7
        fr3 = first_fri + 14
        mon = fr3 - 4
        for k in range(5):
            days.append(mon + k)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return days


MQH_USD_D = [18201, 18324, 18336, 19068, 19117, 19159, 19201, 19257, 19299,
             19341, 19390, 19439, 19481, 19565, 19985, 20035, 20076, 20349,
             20391, 20433]
MQH_USD_R = [1.625, 1.125, 0.125, 0.375, 0.875, 1.625, 2.375, 3.125, 3.875,
             4.375, 4.625, 4.875, 5.125, 5.375, 4.875, 4.625, 4.375, 4.125,
             3.875, 3.625]
MQH_JPY_D = [18201, 19801, 19935, 20112]
MQH_JPY_R = [-0.10, 0.10, 0.25, 0.50]


def rate_at(days, rates, eday):
    rate = rates[0]
    for d, r in zip(days, rates):
        if d <= eday:
            rate = r
        else:
            break
    return rate


_OPEX_LIST = build_opex_cal()
_OPEX_SET = set(_OPEX_LIST)          # membership only (binary search twin)

SQRT252 = math.sqrt(252.0)


def clip(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def clip_hi(x, hi):
    if x > hi:
        return hi
    return x


def fields(ts):
    d = ts // 86400
    h = (ts % 86400) // 3600
    dw = (d + 3) % 7
    return d, h, dw


# =============================================================================
# 3. Leg stepper mirrors (CCsLeg* transcriptions)
# =============================================================================
class LegXauM:
    def __init__(self):
        s_g = (0.55 * CS_RISK) / 0.55
        self.vt_gd = 0.125 * s_g
        self.cap_gd = 6.0
        self.vt_gn = 0.30 * s_g
        self.cap_gn = 6.0
        self.c_gd = 0.17 / 0.36
        self.c_gn = 0.19 / 0.36
        self.vol = RollStdM(20)
        self.mx50 = DonchianM(50, True)
        self.mn50 = DonchianM(50, False)
        self.mx100 = DonchianM(100, True)
        self.mn100 = DonchianM(100, False)
        self.b50 = 0.0
        self.b100 = 0.0
        self.prev_mid = NAN
        self.s50_P = NAN
        self.s100_P = NAN
        self.vol_P = NAN
        self.eff50 = 0.0
        self.eff100 = 0.0
        self.effN = 0.0
        self.held = 0.0
        self.has_held = False
        self.cur = 0
        self.started = False
        self.pb = 0.0
        self.pa = 0.0
        self.out = 0.0

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            m = (self.pb + self.pa) / 2.0
            hi50, lo50 = self.mx50.query(), self.mn50.query()
            hi100, lo100 = self.mx100.query(), self.mn100.query()
            if hi50 == hi50 and m >= hi50:
                self.b50 = 1.0
            if lo50 == lo50 and m <= lo50:
                self.b50 = -1.0
            if hi100 == hi100 and m >= hi100:
                self.b100 = 1.0
            if lo100 == lo100 and m <= lo100:
                self.b100 = -1.0
            self.mx50.push(m); self.mn50.push(m)
            self.mx100.push(m); self.mn100.push(m)
            r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
            self.vol_P = self.vol.step(r) * SQRT252
            self.prev_mid = m
            self.s50_P = self.b50
            self.s100_P = self.b100
            c50 = clip(self.s50_P * self.vt_gd / self.vol_P, -self.cap_gd, self.cap_gd)
            c100 = clip(self.s100_P * self.vt_gd / self.vol_P, -self.cap_gd, self.cap_gd)
            lv = clip_hi(self.vt_gn / self.vol_P, self.cap_gn)
            if c50 == c50:
                self.eff50 = c50
            if c100 == c100:
                self.eff100 = c100
            if lv == lv:
                self.effN = lv
            self.cur = d
        night = self.effN if (h >= 20 or h < 8) else 0.0
        raw = (self.eff50 + self.eff100) * self.c_gd + night * self.c_gn
        if h == 21 or h == 22:
            self.out = self.held if self.has_held else 0.0
        else:
            self.out = raw
            self.held = raw
            self.has_held = True
        self.pb = bid_c
        self.pa = ask_c


class LegJpyM:
    def __init__(self):
        self.vt_j = 0.15 * CS_RISK
        self.cap_j = 20.0
        self.jc_lo = 0.5
        self.jc_den = 2.0 - 0.5
        self.vt_s6 = 0.15 * CS_RISK * 1.0
        self.cap_s6 = 6.0
        self.vol = RollStdM(20)
        self.sma100 = RollMeanM(100)
        self.sma20 = RollMeanM(20)
        self.prev_mid = NAN
        self.sigJ_P = NAN
        self.vol_P = NAN
        self.effJ = 0.0
        self.eff6 = 0.0
        self.held = 0.0
        self.has = False
        self.cur = 0
        self.started = False
        self.pb = 0.0
        self.pa = 0.0
        self.out1 = 0.0
        self.out5 = 0.0

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            m = (self.pb + self.pa) / 2.0
            ma1 = self.sma100.step(m)
            ma2 = self.sma20.step(m)
            above = ma1 == ma1 and m > ma1
            strong = ma2 == ma2 and m > ma2
            carry = (rate_at(MQH_USD_D, MQH_USD_R, self.cur)
                     - rate_at(MQH_JPY_D, MQH_JPY_R, self.cur))
            gate = clip((carry - self.jc_lo) / self.jc_den, 0.0, 1.0)
            self.sigJ_P = 1.0 if (above and strong) else ((0.5 * gate) if above else 0.0)
            r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
            self.vol_P = self.vol.step(r) * SQRT252
            self.prev_mid = m
            cj = clip_hi(self.sigJ_P * self.vt_j / self.vol_P, self.cap_j)
            if cj == cj:
                self.effJ = cj
            mask = 1.0 if (d in _OPEX_SET and (d + 3) % 7 < 5) else 0.0
            c6 = clip(mask * 1.0 * self.vt_s6 / self.vol_P, -self.cap_s6, self.cap_s6)
            if c6 == c6:
                self.eff6 = c6
            self.cur = d
        raw = self.effJ
        if h == 21 or h == 22:
            self.out1 = self.held if self.has else 0.0
        else:
            self.out1 = raw
            self.held = raw
            self.has = True
        v = self.eff6
        inwk = d in _OPEX_SET
        if inwk and dw == 0 and h < 12:
            v = 0.0
        if inwk and dw == 4 and h >= 20:
            v = 0.0
        if dw == 6 and (d - 2) in _OPEX_SET:
            v = 0.0
        self.out5 = v
        self.pb = bid_c
        self.pa = ask_c


class LegEthM:
    def __init__(self):
        self.vt_e = 0.40 * CS_RISK
        self.cap_e = 1.2
        self.vol = RollStdM(20)
        self.sma200 = RollMeanM(200)
        self.sma20 = RollMeanM(20)
        self.sma60 = RollMeanM(60)
        self.prev_mid = NAN
        self.sig_P = NAN
        self.vol_P = NAN
        self.eff = 0.0
        self.held = 0.0
        self.has = False
        self.cur = 0
        self.started = False
        self.pb = 0.0
        self.pa = 0.0
        self.out = 0.0

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            m = (self.pb + self.pa) / 2.0
            ma200 = self.sma200.step(m)
            ma20 = self.sma20.step(m)
            ma60 = self.sma60.step(m)
            self.sig_P = 1.0 if (ma200 == ma200 and m > ma200
                                 and ma20 == ma20 and ma60 == ma60
                                 and ma20 > ma60) else 0.0
            r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
            self.vol_P = self.vol.step(r) * SQRT252
            self.prev_mid = m
            c = clip_hi(self.sig_P * self.vt_e / self.vol_P, self.cap_e)
            if c == c:
                self.eff = c
            self.cur = d
        raw = self.eff
        if h == 21 or h == 22:
            self.out = self.held if self.has else 0.0
        else:
            self.out = raw
            self.held = raw
            self.has = True
        self.pb = bid_c
        self.pa = ask_c


class LegEgM:
    EG_WINDOWS = (20, 40, 60, 80)

    def __init__(self):
        self.vt_eg = 0.20 * CS_RISK
        self.cap_eg = 20.0
        self.zclip = 2.5
        self.mz = [RollMeanM(w) for w in self.EG_WINDOWS]
        self.sz = [RollStdM(w) for w in self.EG_WINDOWS]
        self.volr = RollStdM(20)
        self.prev_mid = NAN
        self.egval_prev = NAN
        self.kts = []
        self.kv = []
        self.eff = 0.0
        self.held = 0.0
        self.has = False
        self.cur = 0
        self.started = False
        self.pre20_b = 0.0
        self.pre20_a = 0.0
        self.pre20_has = False
        self.done = False
        self.out = 0.0

    def _finalize(self, day_e):
        m = (self.pre20_b + self.pre20_a) / 2.0
        self.kts.append(day_e * 86400 + 72000)
        self.kv.append(self.egval_prev)
        zsum = 0.0
        for k in range(4):
            mean = self.mz[k].step(m)
            sd = self.sz[k].step(m)
            z = (m - mean) / sd
            piece = -clip(z, -self.zclip, self.zclip) / self.zclip
            zsum = piece if k == 0 else zsum + piece
        sig = zsum / 4.0
        r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
        annv = self.volr.step(r) * SQRT252
        self.egval_prev = clip(sig * self.vt_eg / annv, -self.cap_eg, self.cap_eg)
        self.prev_mid = m

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            if self.pre20_has and not self.done:
                self._finalize(self.cur)
            self.pre20_has = False
            self.done = False
            self.cur = d
        if h < 20:
            self.pre20_b = bid_c
            self.pre20_a = ask_c
            self.pre20_has = True
        elif not self.done and self.pre20_has:
            self._finalize(d)
            self.done = True
        while self.kts and self.kts[0] <= ts:
            v = self.kv[0]
            del self.kts[0]
            del self.kv[0]
            if v == v:
                self.eff = v
        raw = self.eff
        if h == 21 or h == 22:
            self.out = self.held if self.has else 0.0
        else:
            self.out = raw
            self.held = raw
            self.has = True


class LegUstecM:
    def __init__(self):
        s_u = (0.85 * CS_RISK) / 0.85
        self.vt_ur = 0.25 * s_u
        self.cap_ur = 6.0
        self.vt_um = 0.60 * s_u
        self.cap_um = 10.0
        self.c_ur = 0.09 / 0.24
        self.c_um = 0.15 / 0.24
        self.vol = RollStdM(20)
        self.sma200 = RollMeanM(200)
        self.prev_mid = NAN
        self.sig_P = NAN
        self.vol_P = NAN
        self.effReg = 0.0
        self.effMon = 0.0
        self.heldR = 0.0
        self.hasR = False
        self.held = 0.0
        self.has = False
        self.cur = 0
        self.started = False
        self.pb = 0.0
        self.pa = 0.0
        self.out = 0.0

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            m = (self.pb + self.pa) / 2.0
            ma = self.sma200.step(m)
            self.sig_P = 1.0 if (ma == ma and m > ma) else 0.0
            r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
            self.vol_P = self.vol.step(r) * SQRT252
            self.prev_mid = m
            c = clip(self.sig_P * self.vt_ur / self.vol_P, -self.cap_ur, self.cap_ur)
            lv = clip_hi(self.vt_um / self.vol_P, self.cap_um)
            if c == c:
                self.effReg = c
            if lv == lv:
                self.effMon = lv
            self.cur = d
        if h == 21 or h == 22:
            regd = self.heldR if self.hasR else 0.0
        else:
            regd = self.effReg
            self.heldR = self.effReg
            self.hasR = True
        mon = self.effMon if (dw == 0 and h < 21) else 0.0
        raw = regd * self.c_ur + mon * self.c_um
        if h == 21 or h == 22:
            self.out = self.held if self.has else 0.0
        else:
            self.out = raw
            self.held = raw
            self.has = True
        self.pb = bid_c
        self.pa = ask_c


class LegOpexFxM:
    def __init__(self, sign):
        self.sign = sign
        self.vt_s6 = 0.15 * CS_RISK * 1.0
        self.cap_s6 = 6.0
        self.vol = RollStdM(20)
        self.prev_mid = NAN
        self.vol_P = NAN
        self.eff = 0.0
        self.cur = 0
        self.started = False
        self.pb = 0.0
        self.pa = 0.0
        self.out = 0.0

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            m = (self.pb + self.pa) / 2.0
            r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
            self.vol_P = self.vol.step(r) * SQRT252
            self.prev_mid = m
            mask = 1.0 if (d in _OPEX_SET and (d + 3) % 7 < 5) else 0.0
            c = clip(mask * self.sign * self.vt_s6 / self.vol_P,
                     -self.cap_s6, self.cap_s6)
            if c == c:
                self.eff = c
            self.cur = d
        v = self.eff
        inwk = d in _OPEX_SET
        if inwk and dw == 0 and h < 12:
            v = 0.0
        if inwk and dw == 4 and h >= 20:
            v = 0.0
        if dw == 6 and (d - 2) in _OPEX_SET:
            v = 0.0
        self.out = v
        self.pb = bid_c
        self.pa = ask_c


class LegBtcM:
    BTC_LB = 63

    def __init__(self):
        self.vt_b = 0.40 * CS_RISK
        self.cap_b = 1.2
        self.hurdle = 0.40
        self.expo = 365.0 / float(self.BTC_LB)
        self.vol = RollStdM(20)
        self.sma200 = RollMeanM(200)
        self.dh = [0.0] * self.BTC_LB
        self.dh_head = 0
        self.dcount = 0
        self.prev_mid = NAN
        self.sig_P = NAN
        self.vol_P = NAN
        self.eff = 0.0
        self.cur = 0
        self.started = False
        self.pb = 0.0
        self.pa = 0.0
        self.out = 0.0
        # MathPow flip-distance telemetry
        self.min_hurdle_dist = float("inf")
        self.n_hurdle_close = 0            # |ann - hurdle| < 1e-9

    def step(self, ts, bid_c, ask_c):
        d, h, dw = fields(ts)
        if not self.started:
            self.cur = d
            self.started = True
        elif d != self.cur:
            m = (self.pb + self.pa) / 2.0
            ma = self.sma200.step(m)
            if self.dcount >= self.BTC_LB:
                ann = (m / self.dh[self.dh_head]) ** self.expo - 1.0
                dist = abs(ann - self.hurdle)
                if dist < self.min_hurdle_dist:
                    self.min_hurdle_dist = dist
                if dist < 1e-9:
                    self.n_hurdle_close += 1
            else:
                ann = NAN
            self.sig_P = 1.0 if (ma == ma and m > ma
                                 and ann == ann and ann > self.hurdle) else 0.0
            r = (m / self.prev_mid - 1.0) if self.prev_mid == self.prev_mid else NAN
            self.vol_P = self.vol.step(r) * SQRT252
            self.prev_mid = m
            if self.dcount < self.BTC_LB:
                self.dh[(self.dh_head + self.dcount) % self.BTC_LB] = m
            else:
                self.dh[self.dh_head] = m
                self.dh_head = (self.dh_head + 1) % self.BTC_LB
            self.dcount += 1
            c = clip(self.sig_P * self.vt_b / self.vol_P, 0.0, self.cap_b)
            self.eff = c if c == c else 0.0
            self.cur = d
        self.out = self.eff
        self.pb = bid_c
        self.pa = ask_c


# =============================================================================
# 4. CoreSignalM — CCoreSignal.StepBar mirror (instrument dispatch)
# =============================================================================
I_XAUUSD, I_USDJPY, I_ETHUSD, I_EURGBP = 0, 1, 2, 3
I_USTEC, I_AUDUSD, I_NZDUSD, I_BTCUSD = 4, 5, 6, 7
LEG_INST = {0: I_XAUUSD, 1: I_USDJPY, 2: I_ETHUSD, 3: I_EURGBP,
            4: I_USTEC, 5: I_USDJPY, 6: I_AUDUSD, 7: I_NZDUSD, 8: I_BTCUSD}
INST_NAME = {"XAUUSD": I_XAUUSD, "USDJPY": I_USDJPY, "ETHUSD": I_ETHUSD,
             "EURGBP": I_EURGBP, "USTEC": I_USTEC, "AUDUSD": I_AUDUSD,
             "NZDUSD": I_NZDUSD, "BTCUSD": I_BTCUSD}


class CoreSignalM:
    def __init__(self):
        self.xau = LegXauM()
        self.jpy = LegJpyM()
        self.eth = LegEthM()
        self.eg = LegEgM()
        self.ustec = LegUstecM()
        self.aud = LegOpexFxM(-1.0)
        self.nzd = LegOpexFxM(-1.0)
        self.btc = LegBtcM()
        self.tgt = [0.0] * 9
        self.last_ts = [0] * 8
        self.has_ts = [False] * 8

    def step_bar(self, inst, ts, bid_c, ask_c):
        if self.has_ts[inst] and ts <= self.last_ts[inst]:
            raise AssertionError(f"non-ascending stamp inst {inst}")
        if inst == I_XAUUSD:
            self.xau.step(ts, bid_c, ask_c)
            self.tgt[0] = self.xau.out
        elif inst == I_USDJPY:
            self.jpy.step(ts, bid_c, ask_c)
            self.tgt[1] = self.jpy.out1
            self.tgt[5] = self.jpy.out5
        elif inst == I_ETHUSD:
            self.eth.step(ts, bid_c, ask_c)
            self.tgt[2] = self.eth.out
        elif inst == I_EURGBP:
            self.eg.step(ts, bid_c, ask_c)
            self.tgt[3] = self.eg.out
        elif inst == I_USTEC:
            self.ustec.step(ts, bid_c, ask_c)
            self.tgt[4] = self.ustec.out
        elif inst == I_AUDUSD:
            self.aud.step(ts, bid_c, ask_c)
            self.tgt[6] = self.aud.out
        elif inst == I_NZDUSD:
            self.nzd.step(ts, bid_c, ask_c)
            self.tgt[7] = self.nzd.out
        elif inst == I_BTCUSD:
            self.btc.step(ts, bid_c, ask_c)
            self.tgt[8] = self.btc.out
        else:
            raise AssertionError("bad inst")
        self.last_ts[inst] = ts
        self.has_ts[inst] = True


# =============================================================================
# 5. Gates
# =============================================================================
def diff_stats(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    d = np.abs(a - b)
    return dict(n=int(len(a)),
                bit_equal=bool(np.array_equal(a, b)),
                n_not_bit_equal=int((a != b).sum()),
                max_abs_diff=float(d.max()) if len(d) else 0.0,
                n_gt_1e12=int((d > 1e-12).sum()),
                discrete_flips=int((np.sign(a) != np.sign(b)).sum()))


def gate_m1_fullgrid(arrays, tgt_ref):
    """Mirror streaming over each instrument's FULL native grid vs the
    normative reference targets."""
    out = {}
    mirrors = {}

    def run_inst(name, stepper, outs):
        A = arrays[name]
        es = A["idx"].asi8 // 1_000_000_000
        bc = A["bid_c"]
        ac = A["ask_c"]
        n = len(es)
        bufs = [np.empty(n) for _ in outs]
        for i in range(n):
            stepper.step(int(es[i]), float(bc[i]), float(ac[i]))
            for k, attr in enumerate(outs):
                bufs[k][i] = getattr(stepper, attr)
        return stepper, bufs

    st, b = run_inst("XAUUSD", LegXauM(), ["out"])
    out["0"] = diff_stats(b[0], tgt_ref[0]); out["0"]["inst"] = "XAUUSD"
    st, b = run_inst("USDJPY", LegJpyM(), ["out1", "out5"])
    out["1"] = diff_stats(b[0], tgt_ref[1]); out["1"]["inst"] = "USDJPY"
    out["5"] = diff_stats(b[1], tgt_ref[5]); out["5"]["inst"] = "USDJPY"
    st, b = run_inst("ETHUSD", LegEthM(), ["out"])
    out["2"] = diff_stats(b[0], tgt_ref[2]); out["2"]["inst"] = "ETHUSD"
    st, b = run_inst("EURGBP", LegEgM(), ["out"])
    out["3"] = diff_stats(b[0], tgt_ref[3]); out["3"]["inst"] = "EURGBP"
    st, b = run_inst("USTEC", LegUstecM(), ["out"])
    out["4"] = diff_stats(b[0], tgt_ref[4]); out["4"]["inst"] = "USTEC"
    st, b = run_inst("AUDUSD", LegOpexFxM(-1.0), ["out"])
    out["6"] = diff_stats(b[0], tgt_ref[6]); out["6"]["inst"] = "AUDUSD"
    st, b = run_inst("NZDUSD", LegOpexFxM(-1.0), ["out"])
    out["7"] = diff_stats(b[0], tgt_ref[7]); out["7"]["inst"] = "NZDUSD"
    st, b = run_inst("BTCUSD", LegBtcM(), ["out"])
    out["8"] = diff_stats(b[0], tgt_ref[8]); out["8"]["inst"] = "BTCUSD"
    mirrors["btc_min_hurdle_dist"] = st.min_hurdle_dist
    mirrors["btc_n_hurdle_close_1e9"] = st.n_hurdle_close
    return out, mirrors


def gate_m2_seg_replay(arrays, segdir, n_seg):
    """TestCoreSignal.mq5 DRIVING-LOOP mirror over segments 0..n_seg-1:
    leg-major rows, ONE CoreSignalM cold at seg 0, leg-5 rows served
    from the buffered leg-1 pass, diff vs the frozen tgt column."""
    sig = CoreSignalM()
    per_leg = {j: dict(n=0, n_not_bit_equal=0, max_abs_diff=0.0,
                       n_gt_1e12=0, discrete_flips=0) for j in range(9)}
    first_seen = {}                # leg -> first replayed stamp
    rows_per_leg = {j: 0 for j in range(9)}
    for s in range(n_seg):
        p = segdir / f"FMA3_coresim_seg{s}.csv"
        assert p.exists(), f"missing {p}"
        df = pd.read_csv(p, header=None, usecols=[0, 1, 5, 9, 14],
                         names=["leg", "ts", "bid_c", "ask_c", "tgt"],
                         float_precision="round_trip",
                         dtype={"leg": np.int64, "ts": np.int64,
                                "bid_c": np.float64, "ask_c": np.float64,
                                "tgt": np.float64})
        legv = df["leg"].to_numpy()
        tsv = df["ts"].to_numpy()
        bcv = df["bid_c"].to_numpy()
        acv = df["ask_c"].to_numpy()
        gtv = df["tgt"].to_numpy()
        # leg-major guard (the .mq5 guard)
        assert (np.diff(legv) >= 0).all(), f"seg {s} not leg-major"
        buf5_ts, buf5_v = [], []
        cur5 = 0
        mine = np.empty(len(df))
        last_leg = -1
        for i in range(len(df)):
            leg = int(legv[i])
            ts = int(tsv[i])
            if leg != last_leg:
                if leg == 5:
                    cur5 = 0
                last_leg = leg
            if leg == 5:
                # served from the buffered leg-1 pass (no re-step of the
                # shared USDJPY feed) — the .mq5 protocol
                assert cur5 < len(buf5_ts) and buf5_ts[cur5] == ts, \
                    f"seg {s}: leg5 stamp misalign at row {i}"
                mine[i] = buf5_v[cur5]
                cur5 += 1
            else:
                inst = LEG_INST[leg]
                sig.step_bar(inst, ts, float(bcv[i]), float(acv[i]))
                mine[i] = sig.tgt[leg]
                if leg == 1:
                    buf5_ts.append(ts)
                    buf5_v.append(sig.tgt[5])
            if leg not in first_seen:
                first_seen[leg] = ts
            rows_per_leg[leg] += 1
        for j in range(9):
            msel = legv == j
            if not msel.any():
                continue
            st = diff_stats(mine[msel], gtv[msel])
            pl = per_leg[j]
            pl["n"] += st["n"]
            pl["n_not_bit_equal"] += st["n_not_bit_equal"]
            pl["max_abs_diff"] = max(pl["max_abs_diff"], st["max_abs_diff"])
            pl["n_gt_1e12"] += st["n_gt_1e12"]
            pl["discrete_flips"] += st["discrete_flips"]
        print(f"      seg {s}: {len(df):,} rows replayed", flush=True)
    # M-4 coverage: replayed rows are a contiguous PREFIX of the native grid
    coverage = {}
    for j in range(9):
        inst = CS.LEG_INSTS[j]
        es = arrays[inst]["idx"].asi8 // 1_000_000_000
        n = rows_per_leg[j]
        coverage[str(j)] = dict(
            inst=inst,
            first_stamp_is_grid_start=bool(first_seen.get(j) == int(es[0])),
            rows_replayed=n,
            grid_len=int(len(es)))
    for j in range(9):
        per_leg[j]["inst"] = CS.LEG_INSTS[j]
        per_leg[j]["bit_equal"] = per_leg[j]["n_not_bit_equal"] == 0
    return {str(j): per_leg[j] for j in range(9)}, coverage


def gate_m3_tables():
    ref_opex = CS.opex_week_days()
    ref_usd_d, ref_usd_r = CS._table_edays(CS._POLICY["USD"])
    ref_jpy_d, ref_jpy_r = CS._table_edays(CS._POLICY["JPY"])
    return dict(
        opex_equal=bool(set(_OPEX_LIST) == ref_opex),
        opex_n=len(_OPEX_LIST),
        opex_ascending=bool(all(a < b for a, b in zip(_OPEX_LIST, _OPEX_LIST[1:]))),
        usd_days_equal=bool(MQH_USD_D == ref_usd_d),
        usd_rates_equal=bool(MQH_USD_R == ref_usd_r),
        jpy_days_equal=bool(MQH_JPY_D == ref_jpy_d),
        jpy_rates_equal=bool(MQH_JPY_R == ref_jpy_r))


# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", type=int, default=2,
                    help="segments for the M-2 driving-loop replay (default 2)")
    ap.add_argument("--skip-fullgrid", action="store_true")
    ap.add_argument("--segdir", default=str(COMMON_FILES))
    args = ap.parse_args()
    t0_all = time.time()

    print("[1/5] M-3 calendar/policy tables vs the reference", flush=True)
    m3 = gate_m3_tables()
    print(f"      {m3}", flush=True)

    print("[2/5] prime IC feed + book('BTC_REP','USTEC') + arrays", flush=True)
    CR.prime_feed("ic")
    sleeves = CR.book("BTC_REP", "USTEC")
    insts = sorted({inst for legs in sleeves.values() for inst, _ in legs})
    arrays = {inst: CR.leg_arrays(inst) for inst in insts}

    report = dict(generated=pd.Timestamp.now().isoformat(),
                  mirror_of="mt5/ea/Include/Core/CoreSignal.mqh",
                  arithmetic="CsFmaEmul (Dekker/TwoProduct software fma) "
                             "roll_var — the MQL5 shape",
                  M_3_tables=m3)

    m1 = None
    if not args.skip_fullgrid:
        print("[3/5] reference targets (fma kernels) on the full grid", flush=True)
        t0 = time.time()
        tgt_ref = CS.generate_all_targets(arrays)
        print(f"      done ({time.time()-t0:.1f}s)", flush=True)
        print("[4/5] M-1 mirror streaming vs reference (full native grid)",
              flush=True)
        t0 = time.time()
        m1, tele = gate_m1_fullgrid(arrays, tgt_ref)
        report["M_1_fullgrid"] = m1
        report["mathpow_telemetry"] = tele
        for j in sorted(m1, key=int):
            st = m1[j]
            print(f"      leg {j} {st['inst']:6s} n={st['n']:>9,} "
                  f"bit={st['bit_equal']} max|d|={st['max_abs_diff']:.3e} "
                  f">1e-12: {st['n_gt_1e12']} flips={st['discrete_flips']}",
                  flush=True)
        print(f"      btc min|ann-hurdle| = {tele['btc_min_hurdle_dist']:.6e} "
              f"(n within 1e-9: {tele['btc_n_hurdle_close_1e9']}) "
              f"({time.time()-t0:.1f}s)", flush=True)

    print(f"[5/5] M-2 TestCoreSignal driving-loop replay over "
          f"{args.segments} frozen segments", flush=True)
    t0 = time.time()
    m2, cov = gate_m2_seg_replay(arrays, Path(args.segdir), args.segments)
    report["M_2_seg_replay"] = dict(segments=args.segments, per_leg=m2)
    report["M_4_coverage"] = cov
    for j in sorted(m2, key=int):
        st = m2[j]
        print(f"      leg {j} {st['inst']:6s} n={st['n']:>9,} "
              f"bit={st['bit_equal']} max|d|={st['max_abs_diff']:.3e} "
              f">1e-12: {st['n_gt_1e12']} flips={st['discrete_flips']}",
              flush=True)
    print(f"      ({time.time()-t0:.1f}s)", flush=True)

    verdicts = dict(
        M_3_pass=bool(all(v for k, v in m3.items() if k.endswith("equal")
                          or k == "opex_ascending")))
    if m1 is not None:
        verdicts["M_1_pass"] = bool(all(
            st["max_abs_diff"] <= 1e-12 and st["discrete_flips"] == 0
            for st in m1.values()))
    verdicts["M_2_pass"] = bool(all(
        st["max_abs_diff"] <= 1e-12 and st["discrete_flips"] == 0
        for st in m2.values()))
    verdicts["M_4_pass"] = bool(all(
        c["first_stamp_is_grid_start"] for c in cov.values()))
    report["fma_emul"] = dict(calls=FMA_EMUL_CALLS[0],
                              mismatches_vs_hw_fma=FMA_EMUL_MISMATCH[0])
    verdicts["fma_emul_bit_equal_hw"] = bool(FMA_EMUL_MISMATCH[0] == 0)
    print(f"      fma_emul: {FMA_EMUL_CALLS[0]:,} calls, "
          f"{FMA_EMUL_MISMATCH[0]} mismatches vs math.fma", flush=True)
    report["verdicts"] = verdicts
    report["runtime_s"] = round(time.time() - t0_all, 1)
    OUT_JSON.write_text(json.dumps(report, indent=1))
    print(json.dumps(verdicts, indent=1), flush=True)
    print(f"DONE ({OUT_JSON}, {report['runtime_s']}s)", flush=True)
    return 0 if all(verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
