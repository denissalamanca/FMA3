"""Intraday sleeve — scalar one-bar-at-a-time stepper (FMA3 bpure).

Faithful scalar-float64 replica of the frozen sleeve
    model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/intraday.py
(byte-identical to FMA2 live, diff-verified). NO pandas / NO numpy / NO
future-index reads inside the stepper: plain Python float (IEEE-754 binary64
== MQL5 double) recurrences only, so this is a direct port spec for an EA.

Sleeve recap (frozen params): USA500 + USTEC "open-drive".
    entry_hour=16, exit_hour=21 (server GMT+2/+3, NY-anchored grid)
    mv  = close[h16]/close[h15] - 1                       (per day, real bars)
    sc  = ewm(|mv|, span=60, adjust=True, ignore_na=False, min_periods=20)
          .shift(1)  over the mv DAY index
    z   = clip(mv/sc, -2, 2) / 2
    w   = clip(0.15 / vol_d, upper=1.0)
    sig = clip(z * w * 1.111, -1, 1)
    pos = nan_to_num(sig) on grid rows with hour in [16, 21), else 0.0
          (set REGARDLESS of has_bar on the hold rows — frozen line 105)

Grid / daily semantics verified against the frozen source (the Gemini traps):
  * vol30 = core.realized_vol(ret, span_days=30): ret^2 .ewm(span=720,
    adjust=True, min_periods=0).mean() over the ALL-universe UNION hourly grid
    (ffilled closes; ret=0 on stale/first rows; ret clipped to +-0.30);
    vol = sqrt(var * 24.0 * 365.25). EVERY union-grid row is one ewm step —
    including weekend rows created by crypto symbols, where the index ret is 0.
  * vol_d = vol.resample('1D').last().shift(1): CONTIGUOUS calendar-day grid,
    so the vol used on day d is the LAST hourly vol of calendar day d-1, and it
    is NaN when day d-1 had no grid rows at all (with crypto in the universe
    every calendar day has rows in practice; the first grid day maps to NaN).
  * The mv day index = union of days having an hour-15 bar OR an hour-16 bar
    (has_bar). Every such day is one ewm step for sc; a day with only one of
    the two bars contributes a NaN step (weights decay, nobs unchanged —
    ignore_na=False). Days with neither bar are NOT steps.
  * sc.shift(1): the scale used at day d's entry is the ewm state BEFORE
    committing day d — the stepper therefore reads its sc state at the hour-16
    bar and commits day d's mv step only at the day rollover.

State is a flat dict of floats/ints/bools (get_state/set_state) so a live EA
can serialize and warm-start it.
"""
import math

NAN = float("nan")
INF = float("inf")
DAY_NS = 86_400_000_000_000
HOUR_NS = 3_600_000_000_000

SYMBOLS = ("USA500", "USTEC")
PARAMS = {
    "entry_hour": 16,
    "exit_hour": 21,
    "zcap": 2.0,
    "span_days": 60,
    "ref_vol": 0.15,
    "scale": 1.111,
    "vol_span_days": 30,
    "bars_per_day": 24.0,
    "ret_clip": 0.30,
    "sc_min_periods": 20,
}


def _isobs(x):
    """True iff x is a real observation (pandas' `val == val` test)."""
    return x == x


def _div(a, b):
    """numpy float64 division semantics for scalars (no ZeroDivisionError)."""
    if b == 0.0:
        if not _isobs(a) or a == 0.0:
            return NAN
        return INF if (a > 0.0) == (not math.copysign(1.0, b) < 0.0) else -INF
    return a / b


def _new_sym_state():
    return {
        # ffilled close & realized-vol ewm (span 720, adjust=True) accumulators
        "prev_close": NAN,       # last ffilled close (NaN before first bar)
        "vol_num": 0.0,          # sum f^(t-i) ret_i^2
        "vol_den": 0.0,          # sum f^(t-i)
        "vol": NAN,              # current annualized vol (this bar)
        # vol_d (resample 1D last, shift 1): vol effective for the CURRENT day
        "w_vol": NAN,
        # sc ewm (span 60, adjust=True, ignore_na=False, min_periods=20)
        "sc_num": 0.0,
        "sc_den": 0.0,
        "sc_nobs": 0,
        # intra-day scratch
        "c15": NAN,              # today's hour-15 real-bar close
        "has15": False,          # today has an hour-15 bar (has_bar)
        "has16": False,          # today has an hour-16 bar (has_bar)
        "mv_pending": NAN,       # today's open move (committed at rollover)
        "sig": NAN,              # today's signal (NaN -> position 0)
    }


class IntradayStepper:
    """Steps BOTH sleeve symbols together, one union-grid hourly bar at a time.

    step(ts_ns, closes) -> {sym: position}
      ts_ns  : bar timestamp, integer nanoseconds since epoch, naive broker
               SERVER time (exactly the frozen grid's index.asi8 values).
      closes : {sym: raw close or NaN} — RAW (un-ffilled) close; NaN means the
               symbol has no bar on this union-grid row (has_bar False).
    The returned position is the frozen-matrix value for THIS bar (the harness
    holds pos[t] over bar t+1 — same convention as the golden parquet).
    """

    def __init__(self, symbols=SYMBOLS, log_entries=False, **overrides):
        p = dict(PARAMS)
        p.update(overrides)
        self.symbols = tuple(symbols)
        self.entry_hour = int(p["entry_hour"])
        self.exit_hour = int(p["exit_hour"])
        self.zcap = float(p["zcap"])
        self.ref_vol = float(p["ref_vol"])
        self.scale = float(p["scale"])
        self.ret_clip = float(p["ret_clip"])
        self.sc_min_periods = int(p["sc_min_periods"])
        vol_span = int(p["vol_span_days"] * p["bars_per_day"])   # 720
        self.f_vol = 1.0 - 2.0 / (vol_span + 1.0)
        self.f_sc = 1.0 - 2.0 / (float(p["span_days"]) + 1.0)
        self.ann = float(p["bars_per_day"])                       # 24.0
        self.cur_day = None                                       # int ts//DAY
        self.state = {s: _new_sym_state() for s in self.symbols}
        self.log_entries = bool(log_entries)
        self.entry_log = {s: [] for s in self.symbols}            # validation

    # ------------------------------------------------------------------ state
    def get_state(self):
        return {
            "cur_day": self.cur_day,
            "symbols": {s: dict(self.state[s]) for s in self.symbols},
        }

    def set_state(self, d):
        self.cur_day = d["cur_day"]
        for s in self.symbols:
            self.state[s] = dict(d["symbols"][s])

    # ------------------------------------------------------------------- step
    def _roll_day(self, new_day):
        """Finalize the day that just ended, for every symbol."""
        gap1 = (new_day == self.cur_day + 1)
        for s in self.symbols:
            st = self.state[s]
            # (a) commit the ended day's mv ewm step (iff it was an mv-index
            #     day: had an hour-15 or hour-16 bar). ignore_na=False: decay
            #     weights on every step; add only on a real mv observation.
            if st["has15"] or st["has16"]:
                st["sc_num"] *= self.f_sc
                st["sc_den"] *= self.f_sc
                mv = st["mv_pending"]
                if _isobs(mv):
                    st["sc_num"] += abs(mv)
                    st["sc_den"] += 1.0
                    st["sc_nobs"] += 1
            # (b) vol_d = resample('1D').last().shift(1): vol effective on the
            #     new day = last hourly vol of the immediately preceding
            #     CALENDAR day (NaN if that day had no grid rows).
            st["w_vol"] = st["vol"] if gap1 else NAN
            # (c) reset intra-day scratch
            st["c15"] = NAN
            st["has15"] = False
            st["has16"] = False
            st["mv_pending"] = NAN
            st["sig"] = NAN

    def step(self, ts_ns, closes):
        day = ts_ns // DAY_NS
        hour = (ts_ns - day * DAY_NS) // HOUR_NS
        if self.cur_day is None:
            self.cur_day = day
        elif day != self.cur_day:
            self._roll_day(day)
            self.cur_day = day

        out = {}
        for s in self.symbols:
            st = self.state[s]
            raw = closes.get(s, NAN)
            has_bar = _isobs(raw)
            cf = raw if has_bar else st["prev_close"]

            # ret on the union grid: 0 before the first bar, else clipped
            # pct-change of the ffilled close (0 on stale rows by identity).
            prev = st["prev_close"]
            if _isobs(prev):
                r = cf / prev - 1.0
                if r > self.ret_clip:
                    r = self.ret_clip
                elif r < -self.ret_clip:
                    r = -self.ret_clip
            else:
                r = 0.0
            st["prev_close"] = cf

            # realized-vol ewm: EVERY grid row is one observation (ret never
            # NaN in the frozen frame). adjust=True num/den recurrence.
            st["vol_num"] = st["vol_num"] * self.f_vol + r * r
            st["vol_den"] = st["vol_den"] * self.f_vol + 1.0
            var = st["vol_num"] / st["vol_den"]
            st["vol"] = math.sqrt(var * self.ann * 365.25)

            if has_bar:
                if hour == self.entry_hour - 1:
                    st["c15"] = raw
                    st["has15"] = True
                elif hour == self.entry_hour:
                    st["has16"] = True
                    mv = (raw / st["c15"] - 1.0) if st["has15"] else NAN
                    st["mv_pending"] = mv
                    # sc.shift(1): ewm state BEFORE today's commit, gated on
                    # min_periods (nobs as of the end of the previous mv day).
                    if st["sc_nobs"] >= self.sc_min_periods and st["sc_den"] > 0.0:
                        sc = st["sc_num"] / st["sc_den"]
                    else:
                        sc = NAN
                    z_raw = _div(mv, sc) if (_isobs(mv) and _isobs(sc)) else NAN
                    if _isobs(z_raw):
                        zc = z_raw
                        if zc > self.zcap:
                            zc = self.zcap
                        elif zc < -self.zcap:
                            zc = -self.zcap
                        z = zc / self.zcap
                    else:
                        z = NAN
                    wv = st["w_vol"]
                    if _isobs(wv):
                        q = _div(self.ref_vol, wv)      # inf when wv == 0
                        w = q if q <= 1.0 else 1.0      # clip(upper=1.0)
                    else:
                        w = NAN
                    if _isobs(z) and _isobs(w):
                        sv = (z * w) * self.scale
                        sig = -1.0 if sv < -1.0 else (1.0 if sv > 1.0 else sv)
                    else:
                        sv = NAN
                        sig = NAN
                    st["sig"] = sig
                    if self.log_entries:
                        self.entry_log[s].append({
                            "day_ns": day * DAY_NS,
                            "mv": mv, "sc": sc, "z_raw": z_raw, "z": z,
                            "w_vol": wv, "w": w, "sig_pre": sv, "sig": sig,
                        })

            # position matrix value for THIS bar: hold rows get
            # nan_to_num(sig) irrespective of has_bar; all others 0.
            if self.entry_hour <= hour < self.exit_hour:
                v = st["sig"]
                out[s] = v if _isobs(v) else 0.0
            else:
                out[s] = 0.0
        return out
