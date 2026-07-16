"""core_signal_reference.py — CAUSAL one-bar scalar reference of CCoreSignal
(UNIT 1 of the S2 live-Core build; gates G-S1 / G-S2 / G-S4).

WHAT THIS IS
------------
The python statement-mirror of the FUTURE `mt5/ea/Include/Core/CoreSignal.mqh`:
a causal, one-bar-at-a-time scalar stepper that produces the 9 per-leg
per-minute Core targets LIVE-STYLE — daily-mid series accumulated bar by bar,
daily coefficients recomputed at raw-stamp day rollover (EURGBP at its 20:00
knot), raw server-stamp hour/dow gates, defer_reopen hold state, explicit
Donchian breach-state carry — with ZERO vectorized-pandas calls in the target
path.  Owner-ratified normative source (S2_PREP_STATUS "OWNER RATIFICATIONS"
items 1/3): the NSF5 python target functions at R = 8.0 PURE
(v52_alternatives.book("BTC_REP","USTEC") -> lock_v5.build_sleeves ->
strategies/sleeves.py + portfolio_v33.py + v5_sleeves.py), NOT CoreEngine.mqh.

LEG TABLE (book append order == TestCoreSim LEG TABLE)
  0 BOOK_XAU   XAUUSD  gold_donch(50)+gold_donch(100) @vt=0.125*8 (0.17/0.36)
                       + xau_night_va @vt=0.30*8 (0.19/0.36); defer_reopen
  1 S5_JPY     USDJPY  jpy_smart vt=0.15*8 cap=20 (policy-rate carry gate); defer
  2 S1_ETH     ETHUSD  crypto_mom vt=0.40*8 cap=1.2; defer
  3 ZC_EG      EURGBP  eurgbp_zens vt=0.20*8 cap=20 (pre-20:00 daily series,
                       signal effective at day+20:00, shift(1)); defer
  4 BOOK_USTEC USTEC   us500_regime vt=0.25*8 (INNER defer) * (0.09/0.24)
                       + monday_us500 vt=0.60*8 * (0.15/0.24); OUTER defer
                       (the measured Monday-23:00 exit comes from the outer one)
  5 S6_OPEXUSD USDJPY  _opex_leg sign=+1 vt=0.15*8 cap=6 (no defer)
  6 S6_OPEXUSD AUDUSD  _opex_leg sign=-1
  7 S6_OPEXUSD NZDUSD  _opex_leg sign=-1
  8 BTC_REP    BTCUSD  btc_hurdle_legs lb=63 hurdle=0.40 regime=200 vt=0.40*8
                       cap=1.2 (daily fillna(0), no carry, no defer)

PANDAS-FAITHFUL KERNELS (P1c discipline)
----------------------------------------
The daily kernels are statement mirrors of the INSTALLED pandas 3.0.1
`_libs/window/aggregations.pyx` running algorithms (source fetched and ported
verbatim in this pass):
  * roll_mean : Kahan running sum, separate add/remove compensations,
                neg_ct / num_consecutive_same_value guards, minp = window;
  * roll_var  : Welford + Kahan compensation, InvCondTol = eps*1e3
                numerically-unstable window recompute, ddof = 1, then
                pandas zsqrt (negative variance -> 0) for .std();
  * roll_max/min : monotonic deque (exact);
  * pct_change(fill_method=None) = d/d.shift(1) - 1 elementwise;
  * Donchian rolling.max/min().shift(1) with EXPLICIT breach-state carry
    (sig ffill-from-start; the formally unbounded Class-S state).
(No ewm kernels exist in this book; the ewm-adjust=True convention is
inherited from P1c but unused here.)
Gate G-S0 (kernel self-test) bit-compares every kernel against the real
pandas calls on every realized daily series before the target gates run.

MEASURED FMA FINDING (2026-07-14, this pass): the shipped pandas 3.0.1 wheel
compiles roll_var's `ssqdm + (val-prev_mean)*(val-mean)` with clang's default
-ffp-contract=on (arm64), i.e. a FUSED multiply-add — plain python `a + b*c`
differs by ~1e-17 and left every rolling-std kernel non-bit-equal (12/27).
Mirrored here with math.fma (python >= 3.13) / math.fma(-(a), b, s) for the
remove path: 27/27 kernels bit-equal, all 9 leg targets bit-zero.
G-S5 IMPLICATION (flagged, not resolved here): MQL5 exposes no fma intrinsic —
the CoreSignal.mqh roll_var port must either reproduce the contraction (e.g.
compiler-dependent, must be MEASURED in-terminal) or ride the owner-ratified
zero-flip + <=1e-12 criterion for the ~1e-17-class residual.

GATES (this module, all MEASURED)
---------------------------------
  G-S0  kernel selftest: scalar kernels vs pandas rolling ops, bitwise,
        on all realized daily series (diagnostic; not an owner gate).
  G-S1  tgt identity: stepper targets vs (a) the frozen tgt columns of ALL 32
        segment CSVs (FMA3_coresim_seg{J}.csv, the golden) and (b) the
        in-memory book() arrays on the FULL native grid.  Pass: bit-zero or
        <= 1e-12 AND 0 discrete decision differences (sign flips).
  G-S2  lot flips + account passthrough: CoreSim (coresim_reference scalar
        stepper) driven by the LIVE targets vs the frozen-target run —
        per-leg per-bar position flip count MUST be 0; combined eqc/eqw/margin
        bit-equal vs the parity parquet per segment; final eqc bitwise
        532229.8433634703; net lots bit-equal vs v7_book_lots_1m.parquet.
  G-S4  f_core: the H4 identity (net_lots*contract*mid_c*eurq / book eqc,
        hourly last-in-hour sample) computed from the LIVE-target-driven
        CoreSim vs the frozen v7_book_frac_1h.parquet — max|diff| per column,
        pass <= 1e-12 (bit-zero expected when G-S2 is clean).

Owner-ratified pass criterion (S2_PREP_STATUS item 3): bit-zero NOT required;
ZERO lot-decision flips + residual <= 1e-12 on targets is PASS.

Usage (python3 runs from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresignal/core_signal_reference.py \
    [--segments 0 1 ...] [--skip-csv] [--skip-sim] [--skip-selftest]

Writes research/bpure/coresignal/coresignal_gates.json (MEASURED results).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from collections import deque
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()

# --- coresim_reference by FILE (does the whole NSF5 sys.path dance +
#     the lock_v5 stop_out=1e-9 side-effect assert) -------------------------
_spec = importlib.util.spec_from_file_location(
    "coresim_reference", _HERE.parent.parent / "coresim" / "coresim_reference.py")
CR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CR)

# fcore_reference for the position-capturing stepper copy (gate G-d proven)
_spec2 = importlib.util.spec_from_file_location(
    "fcore_reference", _HERE.parent.parent / "coresim" / "fcore_reference.py")
FR = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(FR)

COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")

LOTS_PARQUET = CR.paths.OUTPUTS / "v7_book_lots_1m.parquet"
FRAC_PARQUET = CR.paths.OUTPUTS / "v7_book_frac_1h.parquet"
OUT_JSON = _HERE.parent / "coresignal_gates.json"

FINAL_EQC_TARGET = 532229.8433634703
NAN = float("nan")
SQRT252 = float(np.sqrt(252))
INV_COND_TOL = float(np.finfo(np.float64).eps * 1e3)  # pandas 3.0.1 InvCondTol

# =============================================================================
# 0. Static parameters — R = 8.0 PURE (owner ratification item 1; NEVER the
#    preset InpRisk=8.96 which embeds w*s).  Expression shapes preserved from
#    the anchor call chain so every constant is bit-identical.
# =============================================================================
RISK = 8.0
# gold book (portfolio_v33.gold_book_v31 via build_signals vt=0.55*risk)
_S_G = (0.55 * RISK) / 0.55
VT_GD = 0.125 * _S_G          # gold_donch vt (both lb=50,100)
CAP_GD = 6.0
VT_GN = 0.30 * _S_G           # xau_night_va vt
CAP_GN = 6.0
C_GD = 0.17 / 0.36            # donch ensemble share
C_GN = 0.19 / 0.36            # night share
# jpy_smart (build_signals vt=0.15*risk, cap=20.0 from PORTFOLIO_V33)
VT_J = 0.15 * RISK
CAP_J = 20.0
J_C_LO, J_C_DEN = 0.5, (2.0 - 0.5)
# crypto_mom ETH (vt=0.40*risk, cap=1.2)
VT_E = 0.40 * RISK
CAP_E = 1.2
# eurgbp_zens (vt=0.20*risk, cap=20.0)
VT_EG = 0.20 * RISK
CAP_EG = 20.0
EG_WINDOWS = (20, 40, 60, 80)
EG_ZCLIP = 2.5
# us500_book_v33 (lock_v5: vt=0.85*risk -> s = vt/0.85)
_S_U = (0.85 * RISK) / 0.85
VT_UR = 0.25 * _S_U           # us500_regime vt
CAP_UR = 6.0
VT_UM = 0.60 * _S_U           # monday_us500 vt
CAP_UM = 10.0
C_UR = 0.09 / 0.24
C_UM = 0.15 / 0.24
# S6 opex (v5_sleeves.s6_opexusd: vt = 0.15 * risk * scale, scale=1.0, cap=6.0)
VT_S6 = 0.15 * RISK * 1.0
CAP_S6 = 6.0
# btc_hurdle_legs (v52_alternatives: vt = 0.40 * RISK)
VT_B = 0.40 * RISK
CAP_B = 1.2
BTC_LB = 63
BTC_HURDLE = 0.40
BTC_EXPO = 365.0 / BTC_LB

# policy-rate step tables (NSF5 engine/costs.py POLICY_RATES, USD + JPY only —
# the jpy_smart carry gate is the single policy consumer in this book).
# Embedded live-style (the MQL5 port carries the same table), values verbatim.
_POLICY = {
    "USD": [("2019-11-01", 1.625), ("2020-03-03", 1.125), ("2020-03-15", 0.125),
            ("2022-03-17", 0.375), ("2022-05-05", 0.875), ("2022-06-16", 1.625),
            ("2022-07-28", 2.375), ("2022-09-22", 3.125), ("2022-11-03", 3.875),
            ("2022-12-15", 4.375), ("2023-02-02", 4.625), ("2023-03-23", 4.875),
            ("2023-05-04", 5.125), ("2023-07-27", 5.375),
            ("2024-09-19", 4.875), ("2024-11-08", 4.625), ("2024-12-19", 4.375),
            ("2025-09-18", 4.125), ("2025-10-30", 3.875), ("2025-12-11", 3.625)],
    "JPY": [("2019-11-01", -0.10), ("2024-03-19", 0.10), ("2024-07-31", 0.25),
            ("2025-01-24", 0.50)],
}


def _table_edays(tab):
    return ([(date.fromisoformat(d) - date(1970, 1, 1)).days for d, _ in tab],
            [r for _, r in tab])


_USD_D, _USD_R = _table_edays(_POLICY["USD"])
_JPY_D, _JPY_R = _table_edays(_POLICY["JPY"])


def policy_rate_eday(days, rates, eday):
    """NSF5 costs.policy_rate: last table rate with date <= ts."""
    rate = rates[0]
    for d, r in zip(days, rates):
        if d <= eday:
            rate = r
        else:
            break
    return rate


class _OpexWeeks:
    """v5_sleeves._nth_friday_week(2): Mon..Fri epoch days of every month's
    3rd-Friday week — computed per query, so there is NO upper horizon.

    The parent precomputes this into a set bounded at 2026-02 (its study
    window). Membership against a bounded set answers false forever past the
    last row, which silently flattens the S6 opex legs rather than failing
    (DEMO_GO_NOGO #1) — so the horizon is removed here, not merely re-dated.
    The 2019-12 LOWER bound is kept exactly, so membership is bit-identical to
    the parent's set everywhere the parent had authority.
    """

    LOWER = (2019, 12)

    def __contains__(self, d):
        dt = date(1970, 1, 1) + timedelta(days=int(d))
        if (dt.year, dt.month) < self.LOWER:
            return False
        d1 = date(dt.year, dt.month, 1)
        first_fri = d1 + timedelta(days=(4 - d1.weekday()) % 7)
        fr3 = first_fri + timedelta(days=14)              # 3rd Friday
        mon = fr3 - timedelta(days=fr3.weekday())         # Monday of that week
        e0 = (mon - date(1970, 1, 1)).days
        # the week never crosses a month boundary (3rd Fri is dom 15..21, so
        # its Monday is dom 11..17) -> d's own month is sufficient
        return e0 <= int(d) <= e0 + 4


def opex_week_days():
    """Membership object (was: a set bounded at 2026-02). Kept as a callable so
    existing callers -- `d in opex_week_days()` -- are unaffected."""
    return _OpexWeeks()


OPEX_WK = _OpexWeeks()


# =============================================================================
# 1. Pandas-3.0.1-faithful scalar kernels (aggregations.pyx statement mirrors)
# =============================================================================
def _signbit(x):
    return math.copysign(1.0, x) < 0.0


class RollMean:
    """roll_mean: Kahan running sum, separate add/remove compensations,
    minp = window (rolling(w).mean() default)."""
    __slots__ = ("w", "ring", "i", "nobs", "sum_x", "neg_ct",
                 "comp_add", "comp_rem", "prev_value", "num_consec")

    def __init__(self, w):
        self.w = w
        self.ring = deque()
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
            if _signbit(val):
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
            if _signbit(val):
                self.neg_ct -= 1

    def step(self, val):
        if self.i == 0:
            self.prev_value = val          # pandas setup: prev_value = values[s]
            self.num_consec = 0
            self.sum_x = self.comp_add = self.comp_rem = 0.0
            self.nobs = self.neg_ct = 0
            self._add(val)
        else:
            if self.i >= self.w:
                self._remove(self.ring[0])
            self._add(val)
        self.ring.append(val)
        if len(self.ring) > self.w:
            self.ring.popleft()
        self.i += 1
        # calc_mean
        if self.nobs >= self.w and self.nobs > 0:
            result = self.sum_x / self.nobs
            if self.num_consec >= self.nobs:
                result = self.prev_value
            elif self.neg_ct == 0 and result < 0:
                result = 0.0
            elif self.neg_ct == self.nobs and result > 0:
                result = 0.0
            return result
        return NAN


class RollStd:
    """roll_var (Welford + Kahan, InvCondTol window recompute, ddof=1)
    followed by pandas zsqrt (negative variance -> 0)."""
    __slots__ = ("w", "ddof", "ring", "i", "nobs", "mean_x", "ssqdm_x",
                 "comp_add", "comp_rem", "unstable")

    def __init__(self, w, ddof=1):
        self.w = w
        self.ddof = float(ddof)
        self.ring = deque()
        self.i = 0
        self.nobs = 0.0
        self.mean_x = 0.0
        self.ssqdm_x = 0.0
        self.comp_add = 0.0
        self.comp_rem = 0.0
        self.unstable = False

    def _add(self, val):
        if val != val:
            return
        prev_m2 = self.ssqdm_x
        self.nobs = self.nobs + 1.0
        prev_mean = self.mean_x - self.comp_add
        y = val - self.comp_add
        t = y - self.mean_x
        self.comp_add = t + self.mean_x - y
        delta = t
        if self.nobs:
            self.mean_x = self.mean_x + delta / self.nobs
        else:
            self.mean_x = 0.0
        # the shipped pandas wheel contracts `ssqdm + (a)*(b)` into one fma
        # (clang default -ffp-contract=on for the Cython C) — mirror it
        self.ssqdm_x = math.fma(val - prev_mean, val - self.mean_x,
                                self.ssqdm_x)
        if prev_m2 * INV_COND_TOL > self.ssqdm_x:
            self.unstable = True

    def _remove(self, val):
        if val == val:
            prev_m2 = self.ssqdm_x
            self.nobs = self.nobs - 1.0
            if self.nobs:
                prev_mean = self.mean_x - self.comp_rem
                y = val - self.comp_rem
                t = y - self.mean_x
                self.comp_rem = t + self.mean_x - y
                delta = t
                self.mean_x = self.mean_x - delta / self.nobs
                # fnmsub contraction: ssqdm - (a)*(b) in one rounding
                self.ssqdm_x = math.fma(-(val - prev_mean),
                                        val - self.mean_x, self.ssqdm_x)
                if prev_m2 * INV_COND_TOL > self.ssqdm_x:
                    self.unstable = True
            else:
                self.mean_x = 0.0
                self.ssqdm_x = 0.0
                self.unstable = False

    def step(self, val):
        recompute = self.i == 0
        if not recompute:
            if self.i >= self.w:
                self._remove(self.ring[0])
            self._add(val)
        self.ring.append(val)
        if len(self.ring) > self.w:
            self.ring.popleft()
        if recompute or self.unstable:
            self.nobs = self.mean_x = self.ssqdm_x = 0.0
            self.comp_add = self.comp_rem = 0.0
            for v in self.ring:
                self._add(v)
            self.unstable = False
        self.i += 1
        # calc_var (minp = max(w,1)) + zsqrt
        if self.nobs >= self.w and self.nobs > self.ddof:
            var = self.ssqdm_x / (self.nobs - self.ddof)
        else:
            return NAN
        if var < 0:
            return 0.0
        return math.sqrt(var)


class RollMax:
    """rolling(w).max() — monotonic deque, minp = window (exact)."""
    __slots__ = ("w", "dq", "i", "last")

    def __init__(self, w):
        self.w = w
        self.dq = deque()
        self.i = 0
        self.last = NAN            # output at the PREVIOUS position (shift(1))

    def step(self, val):
        dq = self.dq
        while dq and dq[-1][1] <= val:
            dq.pop()
        dq.append((self.i, val))
        while dq[0][0] <= self.i - self.w:
            dq.popleft()
        self.i += 1
        out = dq[0][1] if self.i >= self.w else NAN
        self.last = out
        return out


class RollMin:
    __slots__ = ("w", "dq", "i", "last")

    def __init__(self, w):
        self.w = w
        self.dq = deque()
        self.i = 0
        self.last = NAN

    def step(self, val):
        dq = self.dq
        while dq and dq[-1][1] >= val:
            dq.pop()
        dq.append((self.i, val))
        while dq[0][0] <= self.i - self.w:
            dq.popleft()
        self.i += 1
        out = dq[0][1] if self.i >= self.w else NAN
        self.last = out
        return out


def clip2(x, lo, hi):
    """pandas Series.clip(lo, hi) scalar: NaN passes through."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


# =============================================================================
# 2. Per-instrument causal one-bar steppers.  Shared conventions:
#    * daily mid = (bid_c + ask_c)/2 of the LAST bar of each raw-stamp day
#      (_daily_mid), finalized at the first bar of the next bar-day;
#    * daily coefficients for bar-day D use signal state through the previous
#      daily entry (sig.shift(1) / _vol_scale shift) + D's calendar, and are
#      NaN-carried (_to_bar_array reindex-ffill: a NaN daily value keeps the
#      previous effective value; leading NaN -> 0.0);
#    * defer_reopen: bars with raw hour in {21,22} hold the last value seen at
#      an unmasked bar (leading edge -> 0.0);
#    * all hour/dow gates are RAW server-stamp fields (NO ToUtc).
# =============================================================================
def _fields(idx):
    es = idx.asi8 // 1_000_000_000
    eday = es // 86400
    hour = (es % 86400) // 3600
    dow = (eday + 3) % 7          # epoch day 0 = Thursday(3); Mon=0 like pandas
    return es, eday, hour, dow


def gen_xau(idx, bid_c, ask_c):
    """Leg 0 BOOK_XAU: gold_donch(50)+gold_donch(100) + xau_night_va, defer."""
    n = len(idx)
    out = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    vol = RollStd(20)
    mx50, mn50 = RollMax(50), RollMin(50)
    mx100, mn100 = RollMax(100), RollMin(100)
    b50 = b100 = 0.0                    # Donchian breach state (ffill-from-start)
    prev_mid = NAN
    s50_P = s100_P = NAN                # sig at the last finalized position
    vol_P = NAN                         # std*sqrt252 at the last finalized position
    eff50 = eff100 = effN = 0.0         # NaN-carried daily coefficients
    held = 0.0
    has_held = False
    cur = eday[0]
    for i in range(n):
        d = eday[i]
        h = hour[i]
        if d != cur:
            m = (bid_c[i - 1] + ask_c[i - 1]) / 2
            hi50, lo50 = mx50.last, mn50.last          # rolling().shift(1)
            hi100, lo100 = mx100.last, mn100.last
            if hi50 == hi50 and m >= hi50:
                b50 = 1.0
            if lo50 == lo50 and m <= lo50:
                b50 = -1.0                              # <=lo assignment wins
            if hi100 == hi100 and m >= hi100:
                b100 = 1.0
            if lo100 == lo100 and m <= lo100:
                b100 = -1.0
            mx50.step(m); mn50.step(m); mx100.step(m); mn100.step(m)
            r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
            vol_P = vol.step(r) * SQRT252
            prev_mid = m
            s50_P, s100_P = b50, b100
            c50 = clip2(s50_P * VT_GD / vol_P, -CAP_GD, CAP_GD)
            c100 = clip2(s100_P * VT_GD / vol_P, -CAP_GD, CAP_GD)
            lv = clip2(VT_GN / vol_P, -math.inf, CAP_GN)   # clip(upper=cap)
            if c50 == c50:
                eff50 = c50
            if c100 == c100:
                eff100 = c100
            if lv == lv:
                effN = lv
            cur = d
        night = effN if (h >= 20 or h < 8) else 0.0
        raw = (eff50 + eff100) * C_GD + night * C_GN
        if h == 21 or h == 22:
            out[i] = held if has_held else 0.0
        else:
            out[i] = raw
            held = raw
            has_held = True
    return out


def gen_ustec(idx, bid_c, ask_c):
    """Leg 4 BOOK_USTEC: inner-deferred regime + Monday, then OUTER defer."""
    n = len(idx)
    out = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    vol = RollStd(20)
    sma200 = RollMean(200)
    prev_mid = NAN
    sig_P = NAN
    vol_P = NAN
    effReg = effMon = 0.0
    heldR = 0.0
    hasR = False
    held = 0.0
    has = False
    cur = eday[0]
    for i in range(n):
        d = eday[i]
        h = hour[i]
        if d != cur:
            m = (bid_c[i - 1] + ask_c[i - 1]) / 2
            ma = sma200.step(m)
            sig_P = 1.0 if (ma == ma and m > ma) else 0.0
            r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
            vol_P = vol.step(r) * SQRT252
            prev_mid = m
            c = clip2(sig_P * VT_UR / vol_P, -CAP_UR, CAP_UR)
            lv = clip2(VT_UM / vol_P, -math.inf, CAP_UM)
            if c == c:
                effReg = c
            if lv == lv:
                effMon = lv
            cur = d
        # inner defer_reopen on the regime component (structurally a no-op —
        # the regime value changes only at midnight — kept for statement parity)
        if h == 21 or h == 22:
            regd = heldR if hasR else 0.0
        else:
            regd = effReg
            heldR = effReg
            hasR = True
        mon = effMon if (dow[i] == 0 and h < 21) else 0.0
        raw = regd * C_UR + mon * C_UM
        if h == 21 or h == 22:
            out[i] = held if has else 0.0
        else:
            out[i] = raw
            held = raw
            has = True
    return out


def gen_jpy(idx, bid_c, ask_c):
    """Legs 1 (S5_JPY jpy_smart, defer) + 5 (S6 opex sign=+1, no defer)."""
    n = len(idx)
    out1 = np.empty(n)
    out5 = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    vol = RollStd(20)
    sma100 = RollMean(100)
    sma20 = RollMean(20)
    prev_mid = NAN
    sigJ_P = NAN
    vol_P = NAN
    effJ = eff6 = 0.0
    held = 0.0
    has = False
    cur = eday[0]
    for i in range(n):
        d = eday[i]
        h = hour[i]
        if d != cur:
            m = (bid_c[i - 1] + ask_c[i - 1]) / 2
            ma1 = sma100.step(m)
            ma2 = sma20.step(m)
            above = ma1 == ma1 and m > ma1
            strong = ma2 == ma2 and m > ma2
            carry = (policy_rate_eday(_USD_D, _USD_R, cur)
                     - policy_rate_eday(_JPY_D, _JPY_R, cur))
            gate = clip2((carry - J_C_LO) / J_C_DEN, 0.0, 1.0)
            sigJ_P = 1.0 if (above and strong) else ((0.5 * gate) if above else 0.0)
            r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
            vol_P = vol.step(r) * SQRT252
            prev_mid = m
            cj = clip2(sigJ_P * VT_J / vol_P, -math.inf, CAP_J)  # clip(upper=)
            if cj == cj:
                effJ = cj
            mask = 1.0 if (d in OPEX_WK and (d + 3) % 7 < 5) else 0.0
            c6 = clip2(mask * 1 * VT_S6 / vol_P, -CAP_S6, CAP_S6)
            if c6 == c6:
                eff6 = c6
            cur = d
        # leg 1 (defer)
        raw = effJ
        if h == 21 or h == 22:
            out1[i] = held if has else 0.0
        else:
            out1[i] = raw
            held = raw
            has = True
        # leg 5 (opex bar gates, no defer)
        v = eff6
        inwk = d in OPEX_WK
        dw = dow[i]
        if inwk and dw == 0 and h < 12:
            v = 0.0
        if inwk and dw == 4 and h >= 20:
            v = 0.0
        if dw == 6 and (d - 2) in OPEX_WK:
            v = 0.0
        out5[i] = v
    return out1, out5


def gen_opex_fx(idx, bid_c, ask_c, sign):
    """Legs 6/7 (AUDUSD/NZDUSD): _opex_leg sign=-1, no defer."""
    n = len(idx)
    out = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    vol = RollStd(20)
    prev_mid = NAN
    vol_P = NAN
    eff = 0.0
    cur = eday[0]
    for i in range(n):
        d = eday[i]
        h = hour[i]
        if d != cur:
            m = (bid_c[i - 1] + ask_c[i - 1]) / 2
            r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
            vol_P = vol.step(r) * SQRT252
            prev_mid = m
            mask = 1.0 if (d in OPEX_WK and (d + 3) % 7 < 5) else 0.0
            c = clip2(mask * sign * VT_S6 / vol_P, -CAP_S6, CAP_S6)
            if c == c:
                eff = c
            cur = d
        v = eff
        inwk = d in OPEX_WK
        dw = dow[i]
        if inwk and dw == 0 and h < 12:
            v = 0.0
        if inwk and dw == 4 and h >= 20:
            v = 0.0
        if dw == 6 and (d - 2) in OPEX_WK:
            v = 0.0
        out[i] = v
    return out


def gen_eth(idx, bid_c, ask_c):
    """Leg 2 S1_ETH crypto_mom (200d regime + 20/60 cross), defer."""
    n = len(idx)
    out = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    vol = RollStd(20)
    sma200 = RollMean(200)
    sma20 = RollMean(20)
    sma60 = RollMean(60)
    prev_mid = NAN
    sig_P = NAN
    vol_P = NAN
    eff = 0.0
    held = 0.0
    has = False
    cur = eday[0]
    for i in range(n):
        d = eday[i]
        h = hour[i]
        if d != cur:
            m = (bid_c[i - 1] + ask_c[i - 1]) / 2
            ma200 = sma200.step(m)
            ma20 = sma20.step(m)
            ma60 = sma60.step(m)
            sig_P = 1.0 if (ma200 == ma200 and m > ma200
                            and ma20 == ma20 and ma60 == ma60
                            and ma20 > ma60) else 0.0
            r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
            vol_P = vol.step(r) * SQRT252
            prev_mid = m
            c = clip2(sig_P * VT_E / vol_P, -math.inf, CAP_E)   # clip(upper=)
            if c == c:
                eff = c
            cur = d
        raw = eff
        if h == 21 or h == 22:
            out[i] = held if has else 0.0
        else:
            out[i] = raw
            held = raw
            has = True
    return out


def gen_btc(idx, bid_c, ask_c):
    """Leg 8 BTC_REP btc_hurdle_legs: fillna(0.0) daily (NO carry), no defer."""
    n = len(idx)
    out = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    vol = RollStd(20)
    sma200 = RollMean(200)
    d_hist = []
    prev_mid = NAN
    sig_P = NAN
    vol_P = NAN
    eff = 0.0
    cur = eday[0]
    for i in range(n):
        d = eday[i]
        if d != cur:
            m = (bid_c[i - 1] + ask_c[i - 1]) / 2
            ma = sma200.step(m)
            if len(d_hist) >= BTC_LB:
                ann = (m / d_hist[-BTC_LB]) ** BTC_EXPO - 1.0
            else:
                ann = NAN
            sig_P = 1.0 if (ma == ma and m > ma
                            and ann == ann and ann > BTC_HURDLE) else 0.0
            r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
            vol_P = vol.step(r) * SQRT252
            prev_mid = m
            d_hist.append(m)
            c = clip2(sig_P * VT_B / vol_P, 0.0, CAP_B)
            eff = c if c == c else 0.0                    # tgt.fillna(0.0)
            cur = d
        out[i] = eff
    return out


def gen_eg(idx, bid_c, ask_c):
    """Leg 3 ZC_EG eurgbp_zens: pre-20:00 daily series, z-ensemble, signal
    stamped at day+20:00 with shift(1); defer."""
    n = len(idx)
    out = np.empty(n)
    es, eday, hour, dow = _fields(idx)
    mz = {w: RollMean(w) for w in EG_WINDOWS}
    sz = {w: RollStd(w) for w in EG_WINDOWS}
    volr = RollStd(20)
    prev_mid = NAN
    egval_prev = NAN            # tgt value at the LAST entry (pre-shift)
    knots = deque()             # (epoch_sec of entry-day 20:00, value)
    eff = 0.0
    held = 0.0
    has = False
    cur = eday[0]
    pre20_i = -1                # index of the last hour<20 bar of the current day
    done = False                # entry finalized for the current day

    def finalize(day_e, j):
        nonlocal prev_mid, egval_prev
        m = (bid_c[j] + ask_c[j]) / 2
        knots.append((day_e * 86400 + 72000, egval_prev))   # tgt.shift(1) @ +20h
        zsum = None
        for w in EG_WINDOWS:
            mean = mz[w].step(m)
            sd = sz[w].step(m)
            z = (m - mean) / sd
            piece = -clip2(z, -EG_ZCLIP, EG_ZCLIP) / EG_ZCLIP
            zsum = piece if zsum is None else zsum + piece
        sig = zsum / len(EG_WINDOWS)
        r = m / prev_mid - 1 if prev_mid == prev_mid else NAN
        annv = volr.step(r) * SQRT252                        # NOT shifted
        egval_prev = clip2(sig * VT_EG / annv, -CAP_EG, CAP_EG)
        prev_mid = m

    for i in range(n):
        d = eday[i]
        h = hour[i]
        if d != cur:
            if pre20_i >= 0 and not done:
                finalize(cur, pre20_i)
            pre20_i = -1
            done = False
            cur = d
        if h < 20:
            pre20_i = i
        elif not done and pre20_i >= 0:
            finalize(d, pre20_i)
            done = True
        t = es[i]
        while knots and knots[0][0] <= t:
            _, v = knots.popleft()
            if v == v:
                eff = v                                       # ffill skips NaN
        raw = eff
        if h == 21 or h == 22:
            out[i] = held if has else 0.0
        else:
            out[i] = raw
            held = raw
            has = True
    return out


def generate_all_targets(arrays):
    """Run every instrument stepper; return {leg_id: np.ndarray on the leg's
    full native index} in LEG TABLE order."""
    tgt = {}
    A = arrays["XAUUSD"]
    tgt[0] = gen_xau(A["idx"], A["bid_c"], A["ask_c"])
    A = arrays["USDJPY"]
    tgt[1], tgt[5] = gen_jpy(A["idx"], A["bid_c"], A["ask_c"])
    A = arrays["ETHUSD"]
    tgt[2] = gen_eth(A["idx"], A["bid_c"], A["ask_c"])
    A = arrays["EURGBP"]
    tgt[3] = gen_eg(A["idx"], A["bid_c"], A["ask_c"])
    A = arrays["USTEC"]
    tgt[4] = gen_ustec(A["idx"], A["bid_c"], A["ask_c"])
    A = arrays["AUDUSD"]
    tgt[6] = gen_opex_fx(A["idx"], A["bid_c"], A["ask_c"], -1)
    A = arrays["NZDUSD"]
    tgt[7] = gen_opex_fx(A["idx"], A["bid_c"], A["ask_c"], -1)
    A = arrays["BTCUSD"]
    tgt[8] = gen_btc(A["idx"], A["bid_c"], A["ask_c"])
    return tgt


# =============================================================================
# 3. Gate G-S0 — kernel selftest: scalar kernels vs the real pandas calls,
#    bitwise, on every realized daily series.
# =============================================================================
def kernel_selftest(arrays):
    res = {}

    def bars_df(inst):
        A = arrays[inst]
        return pd.DataFrame({"bid_c": A["bid_c"], "ask_c": A["ask_c"]},
                            index=A["idx"])

    def check(tag, mine, ref):
        mine = np.asarray(mine)
        ref = np.asarray(ref)
        eq = np.array_equal(mine, ref, equal_nan=True)
        both = np.isfinite(mine) & np.isfinite(ref)
        mx = float(np.abs(mine[both] - ref[both]).max()) if both.any() else 0.0
        res[tag] = dict(bit_equal=bool(eq), max_abs_diff=mx)
        return eq

    specs = {
        "XAUUSD": dict(means=[], stds_price=[], donch=[50, 100]),
        "USTEC": dict(means=[200], stds_price=[], donch=[]),
        "USDJPY": dict(means=[100, 20], stds_price=[], donch=[]),
        "ETHUSD": dict(means=[200, 20, 60], stds_price=[], donch=[]),
        "AUDUSD": dict(means=[], stds_price=[], donch=[]),
        "NZDUSD": dict(means=[], stds_price=[], donch=[]),
        "BTCUSD": dict(means=[200], stds_price=[], donch=[]),
        "EURGBP": dict(means=list(EG_WINDOWS), stds_price=list(EG_WINDOWS),
                       donch=[]),
    }
    all_ok = True
    for inst, sp in specs.items():
        b = bars_df(inst)
        mid = (b.bid_c + b.ask_c) / 2
        if inst == "EURGBP":
            d = mid[b.index.hour < 20].resample("1D").last().dropna()
        else:
            d = mid.resample("1D").last().dropna()
        vals = d.to_numpy()
        for w in sp["means"]:
            k = RollMean(w)
            mine = [k.step(v) for v in vals]
            all_ok &= check(f"{inst}.mean{w}", mine, d.rolling(w).mean())
        for w in sp["stds_price"]:
            k = RollStd(w)
            mine = [k.step(v) for v in vals]
            all_ok &= check(f"{inst}.pstd{w}", mine, d.rolling(w).std())
        for w in sp["donch"]:
            kx, kn = RollMax(w), RollMin(w)
            mine_x = [kx.step(v) for v in vals]
            mine_n = [kn.step(v) for v in vals]
            all_ok &= check(f"{inst}.max{w}", mine_x, d.rolling(w).max())
            all_ok &= check(f"{inst}.min{w}", mine_n, d.rolling(w).min())
        # returns std20 (_vol_scale kernel, pre-shift)
        r = d.pct_change(fill_method=None)
        rv = r.to_numpy()
        k = RollStd(20)
        mine = [k.step(v) for v in rv]
        all_ok &= check(f"{inst}.rstd20", mine, r.rolling(20).std())
    return all_ok, res


# =============================================================================
# 4. Gate G-S1 — tgt identity vs (a) the frozen seg-CSV tgt columns (golden)
#    and (b) the in-memory book() arrays on the full native grid.
# =============================================================================
LEG_INSTS = ["XAUUSD", "USDJPY", "ETHUSD", "EURGBP", "USTEC",
             "USDJPY", "AUDUSD", "NZDUSD", "BTCUSD"]


def diff_stats(a, b):
    d = np.abs(a - b)
    flips = int((np.sign(a) != np.sign(b)).sum())
    return dict(n=int(len(a)),
                bit_equal=bool(np.array_equal(a, b)),
                n_not_bit_equal=int((a != b).sum()),
                max_abs_diff=float(d.max()) if len(d) else 0.0,
                n_gt_1e12=int((d > 1e-12).sum()),
                discrete_flips=flips)


def gate_s1_fullgrid(tgt_live, sleeves):
    """Diff vs the in-memory book() arrays over each leg's FULL native index."""
    out = {}
    leg_id = 0
    for name, legs in sleeves.items():
        for inst, tgt in legs:
            frozen = np.asarray(tgt, dtype=np.float64)
            live = tgt_live[leg_id]
            assert len(frozen) == len(live), (name, inst)
            st = diff_stats(live, frozen)
            st.update(sleeve=name, inst=inst)
            out[str(leg_id)] = st
            leg_id += 1
    return out


def gate_s1_csv(tgt_live, arrays, segdir, n_seg):
    """Diff vs the frozen tgt column of every exported segment CSV (golden)."""
    per_leg = {j: dict(n=0, n_not_bit_equal=0, max_abs_diff=0.0,
                       n_gt_1e12=0, discrete_flips=0) for j in range(9)}
    es_cache = {j: arrays[LEG_INSTS[j]]["idx"].asi8 // 1_000_000_000
                for j in range(9)}
    segs_seen = 0
    for s in range(n_seg):
        p = segdir / f"FMA3_coresim_seg{s}.csv"
        if not p.exists():
            break
        df = pd.read_csv(p, header=None, usecols=[0, 1, 14],
                         names=["leg", "ts", "tgt"],
                         float_precision="round_trip",
                         dtype={"leg": np.int64, "ts": np.int64,
                                "tgt": np.float64})
        lid = df["leg"].to_numpy()
        ts = df["ts"].to_numpy()
        gt = df["tgt"].to_numpy()
        for j in range(9):
            m = lid == j
            if not m.any():
                continue
            es = es_cache[j]
            pos = np.searchsorted(es, ts[m])
            assert (pos < len(es)).all() and (es[pos] == ts[m]).all(), \
                f"seg {s} leg {j}: stamp not on native grid"
            st = diff_stats(tgt_live[j][pos], gt[m])
            pl = per_leg[j]
            pl["n"] += st["n"]
            pl["n_not_bit_equal"] += st["n_not_bit_equal"]
            pl["max_abs_diff"] = max(pl["max_abs_diff"], st["max_abs_diff"])
            pl["n_gt_1e12"] += st["n_gt_1e12"]
            pl["discrete_flips"] += st["discrete_flips"]
        segs_seen += 1
    for j in range(9):
        per_leg[j]["bit_equal"] = per_leg[j]["n_not_bit_equal"] == 0
        per_leg[j]["inst"] = LEG_INSTS[j]
    return segs_seen, {str(j): per_leg[j] for j in range(9)}


# =============================================================================
# 5. Gates G-S2 / G-S4 — CoreSim driven by the live targets: per-leg position
#    flip count vs the frozen-target run, account bit gates vs the parity
#    parquet, net lots vs the lots parquet, f_core vs the frac parquet.
# =============================================================================
def run_segment_capture(sleeves_t, arrays, t0, t1, seed):
    """One committed segment through the position-capturing scalar stepper
    (fcore_reference.run_leg_scalar_pos, gate G-d proven).  sleeves_t is the
    book structure with (inst, tgt_array) legs.  Returns combined curves plus
    per-leg captures in append order."""
    legs_out, legs_cap = [], []
    flat = 0.0
    for name, legs in sleeves_t.items():
        legcap = seed * CR.W7 / len(legs)
        for inst, tgt in legs:
            A = arrays[inst]
            idx = A["idx"]
            i0 = int(np.searchsorted(idx.values, np.datetime64(t0), side="left"))
            i1 = int(np.searchsorted(idx.values, np.datetime64(t1), side="left"))
            if i1 <= i0:
                flat += legcap
                continue
            tgt64 = np.asarray(tgt, dtype=np.float64)
            cfg = A["cfg"]
            eq_c, eq_w, mg, pos, _ = FR.run_leg_scalar_pos(
                A["bid_o"], A["bid_h"], A["bid_l"], A["bid_c"],
                A["ask_o"], A["ask_h"], A["ask_l"], A["ask_c"],
                A["eurq"], A["swap_flag"], A["swap_long"], A["swap_short"],
                tgt64,
                float(cfg["contract_size"]), float(cfg["commission_side"]),
                float(cfg["leverage"]), float(cfg["lot_step"]),
                float(cfg["min_lot"]), float(legcap), i0, i1)
            legs_out.append(dict(idx=idx[i0:i1], eq_c=eq_c, eq_w=eq_w,
                                 margin=mg))
            legs_cap.append(dict(sleeve=name, inst=inst, idx=idx[i0:i1],
                                 pos=pos))
    union, eqc, eqw, mg = CR.combine_legs(legs_out, flat)
    return union, eqc, eqw, mg, legs_cap


def gates_s2_s4(sleeves, tgt_live, arrays, which):
    segs, trig_books = CR.load_segments()
    par = pd.read_parquet(CR.PARITY_PARQUET)
    par_idx = par.index.values

    # live-book structure in the same append order
    sleeves_live = {}
    leg_id = 0
    for name, legs in sleeves.items():
        sleeves_live[name] = []
        for inst, _ in legs:
            sleeves_live[name].append((inst, tgt_live[leg_id]))
            leg_id += 1

    seg_rows = []
    per_inst: dict[str, list[pd.Series]] = {}
    eqc_parts = []
    total_flips = 0
    all_bits = True
    frozen_regression_ok = True
    for j in which:
        t0, t1 = segs[j]
        if j == 0:
            seed = float(CR.INIT)
        else:
            k = int(np.searchsorted(par_idx, np.datetime64(t0), side="left")) - 1
            seed = float(par["eqc"].iloc[k])
            assert seed == trig_books[j - 1], f"seed chain mismatch seg {j}"
        u_f, c_f, w_f, m_f, cap_f = run_segment_capture(
            sleeves, arrays, t0, t1, seed)
        u_l, c_l, w_l, m_l, cap_l = run_segment_capture(
            sleeves_live, arrays, t0, t1, seed)
        # per-leg lot-decision flips (position after fills, every bar)
        flips = 0
        for lf, ll in zip(cap_f, cap_l):
            assert lf["inst"] == ll["inst"] and lf["sleeve"] == ll["sleeve"]
            flips += int((lf["pos"] != ll["pos"]).sum())
        total_flips += flips
        sel = (par_idx >= np.datetime64(t0)) & (par_idx < np.datetime64(t1))
        ps = par[sel]
        idx_eq = bool(u_l.equals(ps.index))
        bit_c = bool(idx_eq and np.array_equal(c_l, ps["eqc"].to_numpy()))
        bit_w = bool(idx_eq and np.array_equal(w_l, ps["eqw"].to_numpy()))
        bit_m = bool(idx_eq and np.array_equal(m_l, ps["margin"].to_numpy()))
        froz_ok = bool(u_f.equals(ps.index)
                       and np.array_equal(c_f, ps["eqc"].to_numpy()))
        frozen_regression_ok &= froz_ok
        all_bits &= idx_eq and bit_c and bit_w and bit_m
        seg_rows.append(dict(segment=j, t0=str(t0), t1=str(t1), seed=seed,
                             bars=int(len(u_l)), flips=flips,
                             live_index_equal=idx_eq,
                             live_bit_eqc=bit_c, live_bit_eqw=bit_w,
                             live_bit_margin=bit_m,
                             frozen_regression_bit_eqc=froz_ok,
                             final_eqc=float(c_l[-1])))
        # captures for G-S4 (live run)
        seg_inst: dict[str, pd.Series] = {}
        for lc in cap_l:
            s = pd.Series(lc["pos"], index=lc["idx"])
            seg_inst[lc["inst"]] = (s if lc["inst"] not in seg_inst
                                    else seg_inst[lc["inst"]] + s)
        for inst, s in seg_inst.items():
            per_inst.setdefault(inst, []).append(s)
        eqc_parts.append(pd.Series(c_l, index=u_l))
        print(f"      seg {j:2d} [{t0.date()} .. {t1.date()}) "
              f"flips={flips} eqc={bit_c} eqw={bit_w} mg={bit_m} "
              f"frozen_ok={froz_ok}", flush=True)

    full_run = list(which) == list(range(len(segs)))
    gs2 = dict(segments=seg_rows, total_lot_flips=total_flips,
               all_live_bit_equal=bool(all_bits),
               frozen_regression_ok=bool(frozen_regression_ok))
    if full_run:
        final_eqc = float(eqc_parts[-1].iloc[-1])
        gs2["final_eqc"] = final_eqc
        gs2["final_eqc_bit_equal"] = bool(final_eqc == FINAL_EQC_TARGET)
        gs2["final_eqc_target"] = FINAL_EQC_TARGET

    gs4 = None
    lots_rep = None
    if full_run:
        lots_par = pd.read_parquet(LOTS_PARQUET)
        frac_par = pd.read_parquet(FRAC_PARQUET)
        union_idx = par.index
        lots_mine = pd.DataFrame(
            {inst: pd.concat(per_inst[inst]).reindex(union_idx)
                     .ffill().fillna(0.0)
             for inst in sorted(per_inst)}, index=union_idx)
        lots_rep = dict(
            bit_equal={c: bool(np.array_equal(lots_mine[c].to_numpy(),
                                              lots_par[c].to_numpy()))
                       for c in lots_par.columns},
            n_diff_rows={c: int((lots_mine[c].to_numpy()
                                 != lots_par[c].to_numpy()).sum())
                         for c in lots_par.columns})
        eqc_mine = pd.concat(eqc_parts)
        assert eqc_mine.index.equals(union_idx)
        # verbatim producer arithmetic (extract_positions.py L850-860 twin,
        # fcore_reference [4/5])
        val_1m = pd.DataFrame(index=union_idx)
        for inst in lots_mine.columns:
            A = arrays[inst]
            mid = pd.Series((A["bid_c"] + A["ask_c"]) * 0.5,
                            index=A["idx"]).reindex(union_idx).ffill()
            e = pd.Series(A["eurq"], index=A["idx"]).reindex(union_idx).ffill()
            c_size = float(A["cfg"]["contract_size"])
            val_1m[inst] = lots_mine[inst] * c_size * mid * e
        eq_h = eqc_mine.resample("1h").last().dropna()
        frac_mine = (val_1m.resample("1h").last().reindex(eq_h.index)
                     .div(eq_h, axis=0).fillna(0.0))
        idx_eq = bool(frac_mine.index.equals(frac_par.index))
        gs4 = dict(
            index_equal=idx_eq,
            max_abs_diff={c: float((frac_mine[c] - frac_par[c]).abs().max())
                          for c in frac_par.columns} if idx_eq else None,
            bit_equal={c: bool(np.array_equal(frac_mine[c].to_numpy(),
                                              frac_par[c].to_numpy()))
                       for c in frac_par.columns} if idx_eq else None)
    return gs2, lots_rep, gs4


# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", type=int, nargs="*", default=None,
                    help="subset of committed segments for G-S2 (default all)")
    ap.add_argument("--skip-selftest", action="store_true")
    ap.add_argument("--skip-csv", action="store_true")
    ap.add_argument("--skip-sim", action="store_true")
    ap.add_argument("--segdir", default=str(COMMON_FILES))
    args = ap.parse_args()

    t_all = time.time()
    print("[1/6] prime IC feed + book('BTC_REP','USTEC') + arrays", flush=True)
    CR.prime_feed("ic")
    sleeves = CR.book("BTC_REP", "USTEC")
    insts = sorted({inst for legs in sleeves.values() for inst, _ in legs})
    arrays = {inst: CR.leg_arrays(inst) for inst in insts}

    report = dict(generated=pd.Timestamp.now().isoformat(),
                  normative_source="NSF5 book('BTC_REP','USTEC') R=8.0 pure",
                  pandas_version=pd.__version__)

    if not args.skip_selftest:
        print("[2/6] G-S0 kernel selftest (scalar vs pandas, bitwise)",
              flush=True)
        t0 = time.time()
        ok0, res0 = kernel_selftest(arrays)
        n_bit = sum(1 for v in res0.values() if v["bit_equal"])
        report["G_S0_kernels"] = dict(
            all_bit_equal=bool(ok0), n_kernels=len(res0), n_bit_equal=n_bit,
            worst=max((v["max_abs_diff"] for v in res0.values()),
                      default=0.0),
            detail={k: v for k, v in res0.items() if not v["bit_equal"]})
        print(f"      {n_bit}/{len(res0)} kernels bit-equal "
              f"({time.time()-t0:.1f}s)", flush=True)

    print("[3/6] causal one-bar stepper: generating 9 leg targets", flush=True)
    t0 = time.time()
    tgt_live = generate_all_targets(arrays)
    for j, a in tgt_live.items():
        assert np.isfinite(a).all(), f"leg {j}: non-finite live target"
    print(f"      done ({time.time()-t0:.1f}s)", flush=True)

    print("[4/6] G-S1(a) full-native-grid diff vs in-memory book() arrays",
          flush=True)
    s1_full = gate_s1_fullgrid(tgt_live, sleeves)
    report["G_S1_fullgrid"] = s1_full
    for j, st in s1_full.items():
        print(f"      leg {j} {st['inst']:6s} bit={st['bit_equal']} "
              f"max|d|={st['max_abs_diff']:.3e} flips={st['discrete_flips']}",
              flush=True)

    if not args.skip_csv:
        print("[5/6] G-S1(b) diff vs the frozen tgt columns of the 32 seg CSVs",
              flush=True)
        t0 = time.time()
        n_seen, s1_csv = gate_s1_csv(tgt_live, arrays, Path(args.segdir), 32)
        report["G_S1_csv"] = dict(segments_compared=n_seen, per_leg=s1_csv)
        for j, st in s1_csv.items():
            print(f"      leg {j} {st['inst']:6s} n={st['n']:>9,} "
                  f"bit={st['bit_equal']} max|d|={st['max_abs_diff']:.3e} "
                  f"flips={st['discrete_flips']}", flush=True)
        print(f"      ({n_seen} segments, {time.time()-t0:.1f}s)", flush=True)

    if not args.skip_sim:
        print("[6/6] G-S2/G-S4: CoreSim live-target vs frozen-target runs",
              flush=True)
        which = (args.segments if args.segments is not None
                 else list(range(32)))
        gs2, lots_rep, gs4 = gates_s2_s4(sleeves, tgt_live, arrays, which)
        report["G_S2"] = gs2
        report["G_S2_lots_vs_frozen_parquet"] = lots_rep
        report["G_S4_fcore"] = gs4

    # verdicts
    s1_pass = all(st["max_abs_diff"] <= 1e-12 and st["discrete_flips"] == 0
                  for st in report["G_S1_fullgrid"].values())
    if "G_S1_csv" in report:
        s1_pass &= all(st["max_abs_diff"] <= 1e-12
                       and st["discrete_flips"] == 0
                       for st in report["G_S1_csv"]["per_leg"].values())
    report["verdicts"] = dict(G_S1_pass=bool(s1_pass))
    if "G_S2" in report:
        g2 = report["G_S2"]
        report["verdicts"]["G_S2_pass"] = bool(
            g2["total_lot_flips"] == 0 and g2["all_live_bit_equal"]
            and g2.get("final_eqc_bit_equal", True))
    if report.get("G_S4_fcore"):
        g4 = report["G_S4_fcore"]
        report["verdicts"]["G_S4_pass"] = bool(
            g4["index_equal"]
            and all(v <= 1e-12 for v in g4["max_abs_diff"].values()))
    report["runtime_s"] = round(time.time() - t_all, 1)
    OUT_JSON.write_text(json.dumps(report, indent=1))
    print(json.dumps(report["verdicts"], indent=1), flush=True)
    print(f"DONE ({OUT_JSON}, {report['runtime_s']}s)", flush=True)
    ok = all(report["verdicts"].values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
