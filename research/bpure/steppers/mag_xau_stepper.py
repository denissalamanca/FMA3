"""MAG_XAU scalar one-bar-at-a-time stepper (MQL5-double-faithful proxy).

Spec = frozen source model/v3/freeze/FMA3-v34-freeze-1/src/research/ext_import/
mag_xau.py (byte-identical to FMA2 live, verified). Gold $100 round-number
magnet, XAUUSD only, long-only.

Faithful pipeline being replicated per bar:
  1. daily mid  : core.load_hourly("XAUUSD")["c"].resample("1D").last().dropna()
                  -> per SERVER-calendar-day LAST RAW close, trading days only
                  (days with no XAUUSD bar produce NO daily stamp — mag_xau is
                  the sleeve whose daily grid is RAW-trading-days, NOT the
                  ffilled calendar-day union grid).
  2. near       : ((d/STEP - OFFSET).round() + OFFSET) * STEP
                  pandas .round() = BANKER half-to-even at 0 decimals.
  3. dist       : (d - near) / STEP
  4. sig (SIDE>0): 1.0 if (dist < -MIND) and (dist > -BAND) else 0.0
  5. ann        : d.pct_change().rolling(VOL_WIN).std(ddof=1) * sqrt(252)
                  min_periods = VOL_WIN, leading pct_change NaN counts as a
                  missing obs -> first valid ann at daily index VOL_WIN
                  (needs VOL_WIN+1 daily mids). Two-pass ddof=1 std over the
                  window ring (NOT naive sum-of-squares).
  6. raw target : (sig * VT / ann).clip(-CAP, CAP)   (NaN while ann is NaN)
  7. to_hourly  : daily stamp (day 00:00) shifted +1 day +(lag_hours-1)=0 hours
                  -> effective at day+1 00:00; step-ffill onto the hourly union
                  grid; NaN stamped values do NOT overwrite (ffill keeps the
                  previous target); .fillna(0.0) -> position is 0.0 before the
                  first finite target.

STYLE CONTRACT: scalar float64 only, one bar per step() call, no pandas/numpy
vectorization across time, no future reads. State is explicitly serializable
(get_state / from_state) so a live EA can warm-start.
"""
import math

NAN = float("nan")

SYM = "XAUUSD"
STEP = 100.0
BAND = 0.18
MIND = 0.03
OFFSET = 0.0
SIDE = 1.0
VT = 0.15
CAP = 6.0
VOL_WIN = 20

SQRT252 = math.sqrt(252.0)
DAY_NS = 86_400_000_000_000


def _isobs(x):
    """True iff x is a real observation (not NaN) — pandas `val == val` test."""
    return x == x


def banker_round(x):
    """round-half-to-even at 0 decimals == numpy/pandas .round().

    For x >= 1 (and generally whenever Sterbenz applies), x - floor(x) is an
    EXACT binary64 quantity, so the tie test `diff == 0.5` is exact — no
    epsilon needed. Gold mid/STEP lives in ~[10, 40], well inside that range.
    """
    f = math.floor(x)
    diff = x - f
    if diff > 0.5:
        return float(f) + 1.0
    if diff < 0.5:
        return float(f)
    # exact .5 tie -> even neighbour
    return float(f) if (f % 2 == 0) else float(f) + 1.0


class MagXauStepper:
    """Steps ALL sleeve symbols together per hourly bar (this sleeve = XAUUSD
    only; the cross-symbol contract is trivially satisfied).

    step(ts_ns, closes) -> {"XAUUSD": position}
      ts_ns  : int, bar timestamp in ns (server time, naive) on the hourly
               union grid. MUST be called for EVERY grid bar in order (even
               bars where XAUUSD has no raw bar -> close NaN), because target
               effectiveness is a time (day+1 00:00) not a bar count.
      closes : dict {"XAUUSD": raw_close_or_NaN} — RAW close (NaN when the
               symbol printed no bar in this grid hour), NOT the ffilled close.
    """

    SYMBOLS = (SYM,)

    def __init__(self, log_daily=False):
        # --- serializable state ---
        self.mids = []            # last VOL_WIN+1 finalized daily mids (chronological)
        self.accum_day = None     # day-start ns of the in-progress server day
        self.accum_close = NAN    # last raw close seen inside accum_day
        self.pending = []         # [(effective_ts_ns, raw_daily_target)] not yet applied
        self.current = 0.0        # live hourly position target (post ffill + fillna(0))
        # --- debug/validation only (not part of EA state) ---
        self.log_daily = log_daily
        self.daily_log = []       # (day_ns, mid, near, dist, sig, ann, raw_target)

    # ------------------------------------------------------------------ core
    def _finalize_day(self):
        """Close out the in-progress server day: compute the RAW daily target
        and stamp it effective at day+1 00:00 (core.to_hourly lag_hours=1)."""
        mid = self.accum_close
        day = self.accum_day
        self.mids.append(mid)
        if len(self.mids) > VOL_WIN + 1:
            self.mids.pop(0)

        # magnet signal off the day's own mid
        near = (banker_round(mid / STEP - OFFSET) + OFFSET) * STEP
        dist = (mid - near) / STEP
        if SIDE > 0:
            sig = 1.0 if (dist < -MIND and dist > -BAND) else 0.0
        else:
            sig = -1.0 if (dist > MIND and dist < BAND) else 0.0

        # ann vol: rolling(VOL_WIN).std(ddof=1) of daily pct_change, two-pass
        if len(self.mids) >= VOL_WIN + 1:
            mean = 0.0
            base = len(self.mids) - VOL_WIN - 1
            rets = [0.0] * VOL_WIN
            for i in range(VOL_WIN):
                r = self.mids[base + i + 1] / self.mids[base + i] - 1.0
                rets[i] = r
                mean += r
            mean /= float(VOL_WIN)
            ss = 0.0
            for i in range(VOL_WIN):
                dv = rets[i] - mean
                ss += dv * dv
            ann = math.sqrt(ss / float(VOL_WIN - 1)) * SQRT252
        else:
            ann = NAN

        # raw daily target = (sig*VT/ann).clip(-CAP, CAP); NaN propagates
        if not _isobs(ann):
            tgt = NAN
        elif ann == 0.0:
            # pandas float semantics: x/0 -> +-inf (then clipped), 0/0 -> NaN
            tgt = NAN if sig * VT == 0.0 else (CAP if sig * VT > 0.0 else -CAP)
        else:
            tgt = sig * VT / ann
            if tgt > CAP:
                tgt = CAP
            elif tgt < -CAP:
                tgt = -CAP

        self.pending.append((day + DAY_NS, tgt))
        if self.log_daily:
            self.daily_log.append((day, mid, near, dist, sig, ann, tgt))
        self.accum_day = None
        self.accum_close = NAN

    def step(self, ts_ns, closes):
        """Advance one hourly union-grid bar; returns {sym: position}."""
        day = (ts_ns // DAY_NS) * DAY_NS

        # 1) a bar on a LATER day proves the accumulated day has closed
        if self.accum_day is not None and day > self.accum_day:
            self._finalize_day()

        # 2) apply any daily target whose effective stamp has been reached
        #    (ffill semantics: a NaN stamped value does NOT overwrite)
        while self.pending and self.pending[0][0] <= ts_ns:
            tgt = self.pending.pop(0)[1]
            if _isobs(tgt):
                self.current = tgt

        # 3) accumulate this bar's RAW close into the current server day
        c = closes[SYM]
        if _isobs(c):
            self.accum_day = day
            self.accum_close = c

        # 4) held position over this bar
        return {SYM: self.current}

    # -------------------------------------------------------- validation aid
    def flush_final_day(self):
        """Finalize the still-open last day (its target stamps BEYOND the fed
        grid so positions are unaffected). Validation-only, to compare the full
        daily intermediate series against pandas."""
        if self.accum_day is not None and _isobs(self.accum_close):
            self._finalize_day()

    # ------------------------------------------------------------- EA state
    def get_state(self):
        return {
            "version": 1,
            "sleeve": "mag_xau",
            "mids": list(self.mids),
            "accum_day": self.accum_day,
            "accum_close": None if not _isobs(self.accum_close) else self.accum_close,
            "pending": [[t, (None if not _isobs(v) else v)] for t, v in self.pending],
            "current": self.current,
        }

    @classmethod
    def from_state(cls, state, log_daily=False):
        obj = cls(log_daily=log_daily)
        obj.mids = [float(v) for v in state["mids"]]
        obj.accum_day = state["accum_day"]
        obj.accum_close = NAN if state["accum_close"] is None else float(state["accum_close"])
        obj.pending = [(int(t), (NAN if v is None else float(v)))
                       for t, v in state["pending"]]
        obj.current = float(state["current"])
        return obj
