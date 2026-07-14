"""consolidate_p1c stepper: seasonal (XAUUSD) + crypto_smart (BTC/ETH/SOL) in ONE
scalar-double one-bar-at-a-time forward stepper with explicit serializable state.

FROZEN SPEC (byte-verified identical to FMA2 live):
  model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/seasonal.py
  model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/crypto_smart.py
  model/v3/freeze/FMA3-v34-freeze-1/src/research/core.py
    (universe_frames / realized_vol / daily_closes / to_hourly)

CONTRACT (P1c conventions):
  * scalar float64 only inside the stepper: no pandas, no numpy vectorization
    across time, no reading any future index. Python float == C double == MQL5
    double (IEEE-754 binary64), so every recurrence here is a faithful proxy
    for a native MQL5 port.
  * ewm mean: adjust=True, ignore_na=False, pandas Cython weighted/old_wt form
    (decay every position; `if weighted != cur` guard kept verbatim).
  * ewm std: adjust=True, ignore_na=False, bias-corrected Welford-weighted
    ewmcov recurrence, output gated on nobs >= min_periods (obs count, not bar
    index).
  * SMA: ring buffer + running sum, NaN-aware (min_periods == window, so any
    NaN in window -> NaN, exactly pandas semantics at minp==window).
  * daily grid (crypto): the sleeve consumes core.daily_closes = ffilled
    union-grid closes .resample('1D').last().dropna(how='all').  Because the
    union hourly grid has NO weekend bars, this is exactly: one row per
    SERVER-calendar day present in the hourly stream that has >=1 non-NaN
    crypto close; per-symbol value = last non-NaN close within the day (NaN
    for symbols not yet trading).  Weekend/holiday calendar days produced by
    resample are all-NaN and dropped -> they do NOT advance the daily grid.
  * to_hourly: daily stamp d 00:00 -> effective d + 1day + (TRADE_LAG_H-1)h
    = d+1 08:00 UTC, step-function ffill onto the hourly grid, .fillna(0.0).

TIMING / API (strictly causal, no future reads):
  The golden-parquet convention is pos[t] = exposure DECIDED at bar t, held
  over bar t+1.  Seasonal pos[t] = hold(hour of bar t+1) * w[t]
  (hold.shift(-1)), i.e. it is resolved at the OPEN of bar t+1 -- exactly when
  a live EA applies the target.  The stepper therefore emits row t-1 when
  step() is called with bar t (deferred one bar), and finalize() emits the
  last row (shift(-1).fillna(0.0) -> seasonal leg 0 on the final bar).
  Crypto pos[t] is an asof-ffill of already-finalized daily signals, buffered
  one bar to ride along in the same emitted row.

STATE: get_state()/set_state() round-trip a plain dict of floats/ints/lists
(json-serializable with allow_nan) so a live EA can warm-start mid-stream.
"""
import math

NAN = float("nan")
HOUR_NS = 3_600_000_000_000
DAY_NS = 86_400_000_000_000

# ---- seasonal frozen params (sleeves/seasonal.py) --------------------------
SEA_SYMBOL = "XAUUSD"
SEA_ENTRY_HOUR = 23
SEA_END_HOUR = 6
SEA_KAPPA = 0.15
SEA_VOL_FLOOR = 0.05
SEA_SPAN_DAYS = 30
SEA_BARS_PER_DAY = 24.0
SEA_SPAN = int(SEA_SPAN_DAYS * SEA_BARS_PER_DAY)          # 720 (core.realized_vol)
SEA_ANN = SEA_BARS_PER_DAY * 365.25

# ---- crypto_smart frozen params (sleeves/crypto_smart.py) ------------------
CR_SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD"]
L_MOM = 28
Z_LONG = 0.75
Z_SHORT = 0.25
F_EXIT = 0.35
MA_REGIME = 120
VOL_BUDGET = 0.065
VOL_SPAN_D = 30
CAP = 0.5
TRADE_LAG_H = 9

SYMBOLS = [SEA_SYMBOL] + CR_SYMBOLS


class _EwmStd:
    """pandas .ewm(span, adjust=True, ignore_na=False, min_periods=minp).std()
    -- bias-corrected Welford-weighted ewmcov, stepped one value at a time.
    Mirrors pandas/_libs ewmcov(x, x, bias=False) exactly (P1c-validated)."""

    __slots__ = ("f", "minp", "mean", "cov", "sum_wt", "sum_wt2", "old_wt", "nobs")

    def __init__(self, span, minp):
        self.f = 1.0 - 2.0 / (span + 1.0)
        self.minp = minp
        self.mean = NAN
        self.cov = 0.0
        self.sum_wt = 1.0
        self.sum_wt2 = 1.0
        self.old_wt = 1.0
        self.nobs = 0

    def update(self, cur):
        """Push one value (may be NaN); return current std (NaN if gated)."""
        f = self.f
        is_obs = cur == cur
        if self.mean == self.mean:               # already have a value
            # ignore_na=False -> decay EVERY position, including NaN ones
            self.sum_wt *= f
            self.sum_wt2 *= f * f
            self.old_wt *= f
            if is_obs:
                old_mean = self.mean
                if self.mean != cur:
                    self.mean = (self.old_wt * old_mean + cur) / (self.old_wt + 1.0)
                self.cov = ((self.old_wt * (self.cov
                             + (old_mean - self.mean) * (old_mean - self.mean)))
                            + ((cur - self.mean) * (cur - self.mean))) / (self.old_wt + 1.0)
                self.sum_wt += 1.0
                self.sum_wt2 += 1.0
                self.old_wt += 1.0
                self.nobs += 1
        elif is_obs:
            self.mean = cur
            self.cov = 0.0
            self.sum_wt = 1.0
            self.sum_wt2 = 1.0
            self.old_wt = 1.0
            self.nobs = 1
        if self.nobs >= self.minp:
            num = self.sum_wt * self.sum_wt - self.sum_wt2
            if num > 0.0:
                var = self.cov * (self.sum_wt * self.sum_wt / num)
                return math.sqrt(var) if (var == var and var >= 0.0) else NAN
        return NAN

    def get_state(self):
        return {"mean": self.mean, "cov": self.cov, "sum_wt": self.sum_wt,
                "sum_wt2": self.sum_wt2, "old_wt": self.old_wt, "nobs": self.nobs}

    def set_state(self, st):
        self.mean = float(st["mean"])
        self.cov = float(st["cov"])
        self.sum_wt = float(st["sum_wt"])
        self.sum_wt2 = float(st["sum_wt2"])
        self.old_wt = float(st["old_wt"])
        self.nobs = int(st["nobs"])


class _CoinState:
    """Per-coin daily-grid state: log-price diffs, EW vol, 120d SMA regime,
    3-state hysteresis machine.  Advanced once per EMITTED daily-grid row."""

    __slots__ = ("ewm", "prev_logp", "logp_ring", "logp_n",
                 "ma_ring", "ma_head", "ma_filled", "ma_sum", "ma_nan_ct",
                 "state", "last_sig_d", "last_z", "last_ma")

    def __init__(self):
        self.ewm = _EwmStd(VOL_SPAN_D, VOL_SPAN_D)
        self.prev_logp = NAN                     # logp of previous grid row
        self.logp_ring = []                      # last <=L_MOM logp values
        self.logp_n = 0                          # rows pushed so far
        self.ma_ring = [NAN] * MA_REGIME
        self.ma_head = 0
        self.ma_filled = 0
        self.ma_sum = 0.0
        self.ma_nan_ct = 0
        self.state = 0
        self.last_sig_d = NAN                    # diagnostics only
        self.last_z = NAN
        self.last_ma = NAN

    def step_day(self, close):
        """Advance one daily-grid row with this coin's day close (may be NaN).
        Returns the coin's daily position (state * inverse-vol weight)."""
        logp = math.log(close) if (close == close and close > 0.0) else NAN
        # lr = logp.diff()
        lr = (logp - self.prev_logp) if (logp == logp and
                                         self.prev_logp == self.prev_logp) else NAN
        self.prev_logp = logp
        sig_d = self.ewm.update(lr)
        # d28 = logp.diff(L_MOM): needs the logp L_MOM rows back (positional)
        if self.logp_n >= L_MOM:
            old = self.logp_ring[0]
            d28 = (logp - old) if (logp == logp and old == old) else NAN
        else:
            d28 = NAN
        self.logp_ring.append(logp)
        if len(self.logp_ring) > L_MOM:
            self.logp_ring.pop(0)
        self.logp_n += 1
        z = (d28 / (sig_d * math.sqrt(L_MOM))) if (d28 == d28 and
                                                   sig_d == sig_d) else NAN
        # ma = D.rolling(MA_REGIME, min_periods=MA_REGIME).mean()
        # ring + running sum; minp == window -> any NaN in window => NaN
        j = self.ma_head
        if self.ma_filled == MA_REGIME:
            old = self.ma_ring[j]
            if old != old:
                self.ma_nan_ct -= 1
            else:
                self.ma_sum -= old
        self.ma_ring[j] = close
        self.ma_head = (j + 1) % MA_REGIME
        if self.ma_filled < MA_REGIME:
            self.ma_filled += 1
        if close != close:
            self.ma_nan_ct += 1
        else:
            self.ma_sum += close
        ma = (self.ma_sum / MA_REGIME) if (self.ma_filled == MA_REGIME and
                                           self.ma_nan_ct == 0) else NAN
        # state machine (verbatim from sleeves/crypto_smart.py make_positions)
        ab = (close == close and ma == ma and close > ma)      # D > ma
        ok = math.isfinite(z) and math.isfinite(ma)
        state = self.state
        if not ok:
            state = 0
        else:
            if state == 0:
                if z >= Z_LONG:
                    state = 1
                elif z <= -Z_SHORT and not ab:
                    state = -1
            elif state == 1:
                if z < F_EXIT * Z_LONG:
                    state = 0
                    if z <= -Z_SHORT and not ab:
                        state = -1
            else:  # state == -1
                if z > -F_EXIT * Z_SHORT or ab:
                    state = 0
                    if z >= Z_LONG:
                        state = 1
        self.state = state
        # |w| = min(CAP, VOL_BUDGET / (sig_d*sqrt(365))); non-finite -> 0
        if sig_d == sig_d:
            sig_ann = sig_d * math.sqrt(365.0)
            w = VOL_BUDGET / sig_ann             # inf if sig_ann == 0
            if w > CAP:                          # np.minimum(CAP, inf) == CAP
                w = CAP
            if not math.isfinite(w):             # np.where(isfinite(w), w, 0)
                w = 0.0
        else:
            w = 0.0
        self.last_sig_d = sig_d
        self.last_z = z
        self.last_ma = ma
        return state * w

    def get_state(self):
        return {"ewm": self.ewm.get_state(), "prev_logp": self.prev_logp,
                "logp_ring": list(self.logp_ring), "logp_n": self.logp_n,
                "ma_ring": list(self.ma_ring), "ma_head": self.ma_head,
                "ma_filled": self.ma_filled, "ma_sum": self.ma_sum,
                "ma_nan_ct": self.ma_nan_ct, "state": self.state}

    def set_state(self, st):
        self.ewm.set_state(st["ewm"])
        self.prev_logp = float(st["prev_logp"])
        self.logp_ring = [float(v) for v in st["logp_ring"]]
        self.logp_n = int(st["logp_n"])
        self.ma_ring = [float(v) for v in st["ma_ring"]]
        self.ma_head = int(st["ma_head"])
        self.ma_filled = int(st["ma_filled"])
        self.ma_sum = float(st["ma_sum"])
        self.ma_nan_ct = int(st["ma_nan_ct"])
        self.state = int(st["state"])


class ConsolidateP1cStepper:
    """Steps XAUUSD + BTCUSD + ETHUSD + SOLUSD together, one hourly bar at a
    time.  step() returns the finalized position row for the PREVIOUS bar
    (None on the first call); finalize() returns the last row."""

    SYMBOLS = SYMBOLS

    def __init__(self):
        # seasonal ewm(720) of ret^2 -- pandas weighted/old_wt form
        self._sea_f = 1.0 - 2.0 / (SEA_SPAN + 1.0)
        self._sea_weighted = NAN
        self._sea_old_wt = 1.0
        self._sea_w = 0.0                        # w[t] pending hold(hour t+1)
        self._sea_vol = NAN                      # diagnostic
        # crypto daily machinery
        self._coins = {s: _CoinState() for s in CR_SYMBOLS}
        self._cur_day = None                     # day index (ts_ns // DAY_NS)
        self._day_last = {s: NAN for s in CR_SYMBOLS}   # last non-NaN close today
        self._queue = []                         # [(eff_ts_ns, [pos_btc,eth,sol])]
        self._cr_current = [NAN, NAN, NAN]       # asof value at current bar
        # deferred emission
        self._have_prev = False
        self._prev_ts = 0
        self._prev_cr_row = [0.0, 0.0, 0.0]
        # optional validation hook: when not None, one dict appended per
        # emitted daily-grid row (intermediates + states).  NOT part of the
        # EA state; purely for parity instrumentation.
        self.debug_daily = None

    # -- crypto daily-grid finalization --------------------------------------
    def _finalize_day(self, day_idx):
        """Close the just-ended server day.  Emits a daily-grid row only if
        any coin had a non-NaN close (== dropna(how='all'))."""
        if any(v == v for v in self._day_last.values()):
            row = [self._coins[s].step_day(self._day_last[s]) for s in CR_SYMBOLS]
            eff = day_idx * DAY_NS + DAY_NS + (TRADE_LAG_H - 1) * HOUR_NS
            self._queue.append((eff, row))
            if self.debug_daily is not None:
                self.debug_daily.append({
                    "day_ns": day_idx * DAY_NS,
                    "sig_d": {s: self._coins[s].last_sig_d for s in CR_SYMBOLS},
                    "z": {s: self._coins[s].last_z for s in CR_SYMBOLS},
                    "ma": {s: self._coins[s].last_ma for s in CR_SYMBOLS},
                    "state": {s: self._coins[s].state for s in CR_SYMBOLS},
                    "pos_d": {s: row[k] for k, s in enumerate(CR_SYMBOLS)},
                })
        self._day_last = {s: NAN for s in CR_SYMBOLS}

    # -- main per-bar step ----------------------------------------------------
    def step(self, ts_ns, xau_ret, btc_close, eth_close, sol_close):
        """One union-grid hourly bar.  ts_ns: int UTC epoch ns of the bar.
        xau_ret: frozen-feed hourly return (never NaN); *_close: ffilled
        union-grid closes (NaN before symbol inception).
        Returns (prev_ts_ns, {sym: pos}) for the PREVIOUS bar, or None."""
        hour = (ts_ns // HOUR_NS) % 24
        emitted = None
        if self._have_prev:
            hold_next = 1.0 if (hour == SEA_ENTRY_HOUR or hour < SEA_END_HOUR) else 0.0
            row = {SEA_SYMBOL: hold_next * self._sea_w}
            for k, s in enumerate(CR_SYMBOLS):
                row[s] = self._prev_cr_row[k]
            emitted = (self._prev_ts, row)

        # --- crypto: server-day rollover finalizes the previous day ---------
        day_idx = ts_ns // DAY_NS
        if self._cur_day is None:
            self._cur_day = day_idx
        elif day_idx != self._cur_day:
            self._finalize_day(self._cur_day)
            self._cur_day = day_idx
        closes = (btc_close, eth_close, sol_close)
        for s, v in zip(CR_SYMBOLS, closes):
            if v == v:
                self._day_last[s] = float(v)

        # --- crypto: asof-ffill of effective daily targets onto this bar ----
        while self._queue and self._queue[0][0] <= ts_ns:
            self._cr_current = self._queue.pop(0)[1]
        cr_row = [v if v == v else 0.0 for v in self._cr_current]   # .fillna(0.0)

        # --- seasonal: ewm(720) var of ret^2, inverse-vol weight ------------
        sq = float(xau_ret) * float(xau_ret)
        if self._sea_weighted == self._sea_weighted:
            self._sea_old_wt *= self._sea_f
            if self._sea_weighted != sq:
                self._sea_weighted = ((self._sea_old_wt * self._sea_weighted + sq)
                                      / (self._sea_old_wt + 1.0))
            self._sea_old_wt += 1.0
        else:
            self._sea_weighted = sq
        var = self._sea_weighted
        vol = math.sqrt(var * SEA_ANN) if var == var else NAN
        self._sea_vol = vol
        if vol == vol:
            vc = vol if vol > SEA_VOL_FLOOR else SEA_VOL_FLOOR   # clip(lower)
            w = SEA_KAPPA / vc
            if w > 1.0:                                          # clip(upper)
                w = 1.0
        else:
            w = 0.0                                              # .fillna(0.0)
        self._sea_w = w

        # --- defer this bar's row --------------------------------------------
        self._prev_cr_row = cr_row
        self._prev_ts = ts_ns
        self._have_prev = True
        return emitted

    def finalize(self):
        """End of stream: close the still-open server day (its signal would
        become effective beyond the grid, so it queues but never applies --
        exactly like the last row of the pandas daily grid), then emit the
        final bar's row: hold.shift(-1).fillna(0.0) -> seasonal leg 0."""
        if not self._have_prev:
            return None
        if self._cur_day is not None:
            self._finalize_day(self._cur_day)
            self._cur_day = None
        row = {SEA_SYMBOL: 0.0}
        for k, s in enumerate(CR_SYMBOLS):
            row[s] = self._prev_cr_row[k]
        self._have_prev = False
        return (self._prev_ts, row)

    # -- serializable state ----------------------------------------------------
    def get_state(self):
        return {
            "sea_weighted": self._sea_weighted,
            "sea_old_wt": self._sea_old_wt,
            "sea_w": self._sea_w,
            "coins": {s: self._coins[s].get_state() for s in CR_SYMBOLS},
            "cur_day": self._cur_day,
            "day_last": {s: self._day_last[s] for s in CR_SYMBOLS},
            "queue": [[int(t), list(r)] for t, r in self._queue],
            "cr_current": list(self._cr_current),
            "have_prev": self._have_prev,
            "prev_ts": int(self._prev_ts),
            "prev_cr_row": list(self._prev_cr_row),
        }

    def set_state(self, st):
        self._sea_weighted = float(st["sea_weighted"])
        self._sea_old_wt = float(st["sea_old_wt"])
        self._sea_w = float(st["sea_w"])
        for s in CR_SYMBOLS:
            self._coins[s].set_state(st["coins"][s])
        self._cur_day = None if st["cur_day"] is None else int(st["cur_day"])
        self._day_last = {s: float(st["day_last"][s]) for s in CR_SYMBOLS}
        self._queue = [(int(t), [float(v) for v in r]) for t, r in st["queue"]]
        self._cr_current = [float(v) for v in st["cr_current"]]
        self._have_prev = bool(st["have_prev"])
        self._prev_ts = int(st["prev_ts"])
        self._prev_cr_row = [float(v) for v in st["prev_cr_row"]]
