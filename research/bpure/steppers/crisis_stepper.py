"""crisis sleeve — scalar one-bar-at-a-time stepper (MQL5-double-faithful proxy).

SPEC = the frozen source model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/crisis.py
(byte-identical to FMA2 live, cmp-verified). Every constant / branch below is
taken from that file, not from the orientation sketch.

DAILY GRID SEMANTICS (verified from the frozen source):
    dcA = core.daily_closes(core.ALL)          # union-hourly ffilled closes,
                                               #   .resample('1D').last() -> CALENDAR days
    dcA = dcA[dcA.index.dayofweek < 5]         # drop Sat/Sun, KEEP Mon-Fri holidays
                                               #   (stale ffilled closes -> exact 0.0 returns)
    rA  = dcA.pct_change()                     # c_t/c_{t-1} - 1
The stepper consumes ONE row of that filtered daily grid per step() call:
the day's closes for the 10 input symbols (6 equity indices + XAUUSD + 3 JPY
crosses), NaN allowed before a symbol's first bar.

PIPELINE (one step per daily bar, all symbols together):
    br    = mean(non-NaN index returns, column order INDICES)
    vr    = (rollstd10(br)*sqrt(252)) / (rollstd60(br)*sqrt(252))      ddof=1
    lev   = cumprod(1 + br.fillna(0));  dd = lev/rollmax126(lev,minp20) - 1
    s_eq  = ewm(span=3, adjust=True).mean() of float((vr>1.25)|(dd<-0.05))
    fr    = mean(JPY-cross returns);  fvr like vr;  flev cumprod
    fma   = rollmean50(flev, minp20)
    s_fx  = ewm(span=3).mean() of float((fvr>1.20)&(flev<fma))
    up_au = float(XAU close > rollmean50(XAU, minp20))
    vol_s = ewmstd(span=250, minp=60, adjust=True, bias-corrected)(r_s)*sqrt(252)
            clipped at 0.05 lower
    w_XAU = (s_eq*up_au) * (0.30/vol_XAU)
    w_jpy = (-s_fx * (0.25/3.0)) / vol_jpy
    grid  : w = banker_round(w/0.02)*0.02  (half-to-even, = numpy rint)
    cap   : clip(-1, 1) per symbol
    gross : scale = min(3.0/gross, 1.0)  (gross = sum|w| skipna, col order SYMS;
            gross==0 -> scale 1.0);  w *= scale;  NaN rows stay NaN
    effective: server-day stamp + 1 day + 13 hours  (core.to_hourly lag_hours=14),
            hourly ffill SKIPS NaN daily targets (pandas reindex-union-ffill:
            a NaN target inherits the previous day's target), leading NaN -> 0.

STYLE: scalar float64 forward loop only. No pandas, no numpy arrays across time,
no future reads. EWM kernels replicate the pandas _libs Cython recurrences
op-for-op (adjust=True, ignore_na=False; ewmcov bias=False debias with
negative-variance->0 zsqrt clamp) so the continuous path is bit-faithful.
Rolling std ddof=1 is two-pass over a ring (P1c convention). Rolling max is an
exact window scan. State is a plain dict of floats/ints/lists -> a live EA can
serialize / warm-start it.
"""
import math

NAN = float("nan")

# ---- frozen parameters (crisis.py) ----------------------------------------
V0 = 1.25
D0 = 0.05
FX_V0 = 1.20
K_AU = 0.30
K_JP = 0.25
SMOOTH_SPAN = 3

_VOL_WIN_S, _VOL_WIN_L = 10, 60
_DD_WIN = 126
_MA_WIN = 50
_MA_MINP = 20
_DD_MINP = 20
_SIZE_SPAN = 250
_SIZE_MINP = 60
_VOL_FLOOR = 0.05
_GRID = 0.02
_TRADE_LAG_H = 14          # effective next day 13:00 UTC (+1d +13h)
_GROSS_CAP = 3.0
_POS_CAP = 1.0

INDICES = ["DAX", "JP225", "UK100", "US30", "USA500", "USTEC"]   # core.INDICES order
JPX = ["AUDJPY", "NZDJPY", "CADJPY"]
SYMS = ["XAUUSD"] + JPX                                          # output order
INPUT_SYMS = INDICES + ["XAUUSD"] + JPX                          # step() input order

_SQRT252 = math.sqrt(252.0)
_DAY_NS = 86400_000_000_000
_HOUR_NS = 3600_000_000_000
_EFFECT_SHIFT_NS = _DAY_NS + (_TRADE_LAG_H - 1) * _HOUR_NS       # +1d +13h


def _isobs(x):
    """pandas observation test: val == val is False iff NaN."""
    return x == x


def banker_round(x):
    """round-half-to-even on the double value == numpy rint == pandas .round(0).
    Exact for |x| < 2^52 (x - floor(x) is exact there)."""
    if x != x:
        return NAN
    r = math.floor(x)
    d = x - r
    if d > 0.5:
        r += 1.0
    elif d == 0.5:
        if math.fmod(r, 2.0) != 0.0:
            r += 1.0
    return r


# ---------------------------------------------------------------------------
# scalar sub-steppers (each holds an explicit serializable state)
# ---------------------------------------------------------------------------
class EwmMean:
    """pandas .ewm(span=n, adjust=True, ignore_na=False).mean() — exact kernel
    replica (weighted_avg / old_wt recurrence, incl. the `avg != cur` guard)."""

    def __init__(self, span):
        self.f = 1.0 - 2.0 / (span + 1.0)
        self.avg = NAN
        self.old_wt = 1.0
        self.nobs = 0

    def step(self, cur):
        is_obs = cur == cur
        if is_obs:
            self.nobs += 1
        if self.avg == self.avg:
            # ignore_na=False -> decay every position
            self.old_wt *= self.f
            if is_obs:
                if self.avg != cur:
                    self.avg = (self.old_wt * self.avg + 1.0 * cur) \
                        / (self.old_wt + 1.0)
                self.old_wt += 1.0
        elif is_obs:
            self.avg = cur
        return self.avg if self.nobs >= 1 else NAN

    def get_state(self):
        return {"avg": self.avg, "old_wt": self.old_wt, "nobs": self.nobs}

    def set_state(self, s):
        self.avg, self.old_wt, self.nobs = s["avg"], s["old_wt"], s["nobs"]


class EwmStd:
    """pandas .ewm(span=n, min_periods=minp, adjust=True).std() — exact
    ewmcov(x, x, bias=False) kernel replica + zsqrt (negative var -> 0)."""

    def __init__(self, span, minp):
        self.f = 1.0 - 2.0 / (span + 1.0)
        self.minp = minp
        self.mean = NAN
        self.cov = 0.0
        self.sum_wt = 1.0
        self.sum_wt2 = 1.0
        self.old_wt = 1.0
        self.nobs = 0

    def step(self, cur):
        is_obs = cur == cur
        if is_obs:
            self.nobs += 1
        if self.mean == self.mean:
            # ignore_na=False -> decay every position
            self.sum_wt *= self.f
            self.sum_wt2 *= self.f * self.f
            self.old_wt *= self.f
            if is_obs:
                old_mean = self.mean
                if self.mean != cur:
                    self.mean = ((self.old_wt * old_mean) + (1.0 * cur)) \
                        / (self.old_wt + 1.0)
                self.cov = ((self.old_wt *
                             (self.cov + ((old_mean - self.mean)
                                          * (old_mean - self.mean))))
                            + (1.0 * ((cur - self.mean) * (cur - self.mean)))) \
                    / (self.old_wt + 1.0)
                self.sum_wt += 1.0
                self.sum_wt2 += 1.0
                self.old_wt += 1.0
        elif is_obs:
            self.mean = cur
        if self.nobs >= self.minp:
            numerator = self.sum_wt * self.sum_wt
            denominator = numerator - self.sum_wt2
            if denominator > 0.0:
                var = (numerator / denominator) * self.cov
                # pandas zsqrt: sqrt, negatives clamped to 0
                return math.sqrt(var) if var >= 0.0 else 0.0
            return NAN
        return NAN

    def get_state(self):
        return {"mean": self.mean, "cov": self.cov, "sum_wt": self.sum_wt,
                "sum_wt2": self.sum_wt2, "old_wt": self.old_wt,
                "nobs": self.nobs}

    def set_state(self, s):
        self.mean, self.cov = s["mean"], s["cov"]
        self.sum_wt, self.sum_wt2 = s["sum_wt"], s["sum_wt2"]
        self.old_wt, self.nobs = s["old_wt"], s["nobs"]


class Ring:
    """fixed-size ring of raw values (NaN allowed), oldest->newest scan."""

    def __init__(self, window):
        self.window = window
        self.buf = [NAN] * window
        self.head = 0            # next write slot
        self.count = 0           # rows pushed (capped at window)

    def push(self, x):
        self.buf[self.head] = x
        self.head = (self.head + 1) % self.window
        if self.count < self.window:
            self.count += 1

    def values_oldest_first(self):
        w, h, c = self.window, self.head, self.count
        return [self.buf[(h - c + j) % w] for j in range(c)]

    def get_state(self):
        return {"buf": list(self.buf), "head": self.head, "count": self.count}

    def set_state(self, s):
        self.buf = list(s["buf"])
        self.head, self.count = s["head"], s["count"]


def ring_std_ddof1(ring, window, minp):
    """pandas .rolling(window).std() (ddof=1, min_periods=minp) over the last
    `window` pushed rows — two-pass ring recompute (P1c convention)."""
    vals = ring.values_oldest_first()
    vals = vals[-window:] if len(vals) > window else vals
    s = 0.0
    k = 0
    for v in vals:
        if v == v:
            s += v
            k += 1
    if k < minp or k - 1 <= 0:
        return NAN
    mean = s / k
    ss = 0.0
    for v in vals:
        if v == v:
            d = v - mean
            ss += d * d
    return math.sqrt(ss / (k - 1))


def ring_mean(ring, window, minp):
    """pandas .rolling(window, min_periods=minp).mean() — two-pass ring."""
    vals = ring.values_oldest_first()
    vals = vals[-window:] if len(vals) > window else vals
    s = 0.0
    k = 0
    for v in vals:
        if v == v:
            s += v
            k += 1
    if k < minp:
        return NAN
    return s / k


def ring_max(ring, window, minp):
    """pandas .rolling(window, min_periods=minp).max() — exact window scan."""
    vals = ring.values_oldest_first()
    vals = vals[-window:] if len(vals) > window else vals
    m = NAN
    k = 0
    for v in vals:
        if v == v:
            k += 1
            if not (m == m) or v > m:
                m = v
    if k < minp:
        return NAN
    return m


# ---------------------------------------------------------------------------
# the sleeve stepper
# ---------------------------------------------------------------------------
class CrisisStepper:
    """One step() per row of the weekday-filtered calendar-day close grid.

    step(ts_ns, closes) with closes = dict {sym: float} (NaN ok) covering
    INPUT_SYMS, or a list in INPUT_SYMS order. Returns a dict:
        w          : {sym: target weight}  (NaN = 'no target yet: hold prev')
        effective_ns : ts_ns + 1d + 13h  (when the target becomes effective
                       on the hourly grid; pandas ffill semantics = a NaN
                       target is skipped, previous target persists)
        diag       : intermediate values + integer states for parity checks
    """

    def __init__(self):
        self.prev_close = {s: NAN for s in INPUT_SYMS}
        # equity stress
        self.br_ring = Ring(_VOL_WIN_L)
        self.lev = 1.0
        self.lev_ring = Ring(_DD_WIN)
        self.ewm_seq = EwmMean(SMOOTH_SPAN)
        # fx stress
        self.fr_ring = Ring(_VOL_WIN_L)
        self.flev = 1.0
        self.flev_ring = Ring(_MA_WIN)
        self.ewm_sfx = EwmMean(SMOOTH_SPAN)
        # gold trend
        self.au_ring = Ring(_MA_WIN)
        # sizing vols
        self.vol_ewm = {s: EwmStd(_SIZE_SPAN, _SIZE_MINP) for s in SYMS}
        self.n_steps = 0

    # -- state (serializable: plain dict of floats/ints/lists) --------------
    def get_state(self):
        return {
            "prev_close": dict(self.prev_close),
            "br_ring": self.br_ring.get_state(),
            "lev": self.lev,
            "lev_ring": self.lev_ring.get_state(),
            "ewm_seq": self.ewm_seq.get_state(),
            "fr_ring": self.fr_ring.get_state(),
            "flev": self.flev,
            "flev_ring": self.flev_ring.get_state(),
            "ewm_sfx": self.ewm_sfx.get_state(),
            "au_ring": self.au_ring.get_state(),
            "vol_ewm": {s: self.vol_ewm[s].get_state() for s in SYMS},
            "n_steps": self.n_steps,
        }

    def set_state(self, st):
        self.prev_close = dict(st["prev_close"])
        self.br_ring.set_state(st["br_ring"])
        self.lev = st["lev"]
        self.lev_ring.set_state(st["lev_ring"])
        self.ewm_seq.set_state(st["ewm_seq"])
        self.fr_ring.set_state(st["fr_ring"])
        self.flev = st["flev"]
        self.flev_ring.set_state(st["flev_ring"])
        self.ewm_sfx.set_state(st["ewm_sfx"])
        self.au_ring.set_state(st["au_ring"])
        for s in SYMS:
            self.vol_ewm[s].set_state(st["vol_ewm"][s])
        self.n_steps = st["n_steps"]

    # -- one daily bar, ALL symbols together --------------------------------
    def step(self, ts_ns, closes):
        if not isinstance(closes, dict):
            closes = {s: closes[i] for i, s in enumerate(INPUT_SYMS)}
        self.n_steps += 1

        # daily simple returns  r = c/prev - 1  (NaN if either side missing)
        r = {}
        for s in INPUT_SYMS:
            c = closes[s]
            p = self.prev_close[s]
            r[s] = (c / p - 1.0) if (c == c and p == p) else NAN
            if c == c:                       # pct_change pad semantics
                self.prev_close[s] = c

        # ---- equity stress score ----
        # br = row mean over INDICES (skipna, column order)
        sm = 0.0
        k = 0
        for s in INDICES:
            v = r[s]
            if v == v:
                sm += v
                k += 1
        br = (sm / k) if k > 0 else NAN

        self.br_ring.push(br)
        s10 = ring_std_ddof1(self.br_ring, _VOL_WIN_S, _VOL_WIN_S)
        s60 = ring_std_ddof1(self.br_ring, _VOL_WIN_L, _VOL_WIN_L)
        vr = ((s10 * _SQRT252) / (s60 * _SQRT252)) \
            if (s10 == s10 and s60 == s60) else NAN

        self.lev = self.lev * (1.0 + (br if br == br else 0.0))
        self.lev_ring.push(self.lev)
        lmax = ring_max(self.lev_ring, _DD_WIN, _DD_MINP)
        dd = (self.lev / lmax - 1.0) if lmax == lmax else NAN

        trig_eq = 1.0 if ((vr == vr and vr > V0)
                          or (dd == dd and dd < -D0)) else 0.0
        s_eq = self.ewm_seq.step(trig_eq)

        # ---- fx stress score ----
        sm = 0.0
        k = 0
        for s in JPX:
            v = r[s]
            if v == v:
                sm += v
                k += 1
        fr = (sm / k) if k > 0 else NAN

        self.fr_ring.push(fr)
        f10 = ring_std_ddof1(self.fr_ring, _VOL_WIN_S, _VOL_WIN_S)
        f60 = ring_std_ddof1(self.fr_ring, _VOL_WIN_L, _VOL_WIN_L)
        fvr = ((f10 * _SQRT252) / (f60 * _SQRT252)) \
            if (f10 == f10 and f60 == f60) else NAN

        self.flev = self.flev * (1.0 + (fr if fr == fr else 0.0))
        self.flev_ring.push(self.flev)
        fma = ring_mean(self.flev_ring, _MA_WIN, _MA_MINP)

        trig_fx = 1.0 if ((fvr == fvr and fvr > FX_V0)
                          and (fma == fma and self.flev < fma)) else 0.0
        s_fx = self.ewm_sfx.step(trig_fx)

        # ---- gold own-trend qualifier ----
        au = closes["XAUUSD"]
        self.au_ring.push(au)
        au_ma = ring_mean(self.au_ring, _MA_WIN, _MA_MINP)
        up_au = 1.0 if (au == au and au_ma == au_ma and au > au_ma) else 0.0

        # ---- slow sizing vol ----
        vol = {}
        for s in SYMS:
            v = self.vol_ewm[s].step(r[s])
            if v == v:
                v = v * _SQRT252
                if v < _VOL_FLOOR:           # clip(lower=0.05)
                    v = _VOL_FLOOR
            vol[s] = v

        # ---- raw weights (exact source op order) ----
        w_pre = {}
        vx = vol["XAUUSD"]
        w_pre["XAUUSD"] = (s_eq * up_au) * (K_AU / vx) if vx == vx else NAN
        c_jp = K_JP / 3.0
        for s in JPX:
            v = vol[s]
            w_pre[s] = ((-s_fx) * c_jp) / v if v == v else NAN

        # ---- hysteresis grid (banker), per-instrument cap ----
        w = {}
        level = {}
        for s in SYMS:
            x = w_pre[s]
            if x == x:
                g = banker_round(x / _GRID)
                level[s] = int(g)
                y = g * _GRID
                if y > _POS_CAP:
                    y = _POS_CAP
                elif y < -_POS_CAP:
                    y = -_POS_CAP
                w[s] = y
            else:
                level[s] = None
                w[s] = NAN

        # ---- sleeve gross cap (skipna sum, column order SYMS) ----
        gross = 0.0
        for s in SYMS:
            y = w[s]
            if y == y:
                gross += abs(y)
        scale = (_GROSS_CAP / gross) if gross > 0.0 else 1.0
        if scale > 1.0:
            scale = 1.0
        for s in SYMS:
            if w[s] == w[s]:
                w[s] = w[s] * scale

        return {
            "w": w,
            "effective_ns": int(ts_ns) + _EFFECT_SHIFT_NS,
            "diag": {
                "br": br, "vr": vr, "lev": self.lev, "dd": dd,
                "trig_eq": int(trig_eq), "s_eq": s_eq,
                "fr": fr, "fvr": fvr, "flev": self.flev, "fma": fma,
                "trig_fx": int(trig_fx), "s_fx": s_fx,
                "au_ma": au_ma, "up_au": int(up_au),
                "vol": dict(vol), "w_pre": dict(w_pre),
                "level": dict(level), "gross": gross, "scale": scale,
            },
        }


def expand_to_hourly(daily_eff_ns, daily_w, hourly_ns):
    """Map daily targets (already shifted to their effective stamps) onto the
    hourly grid with pandas reindex-union-ffill semantics: at hour h the value
    is the LAST NON-NaN target with effective stamp <= h (NaN targets are
    skipped -> previous persists), NaN before the first -> 0.0 (fillna)."""
    out = [0.0] * len(hourly_ns)
    j = 0
    nd = len(daily_eff_ns)
    cur = NAN
    for i, h in enumerate(hourly_ns):
        while j < nd and daily_eff_ns[j] <= h:
            v = daily_w[j]
            if v == v:
                cur = v
            j += 1
        out[i] = cur if cur == cur else 0.0
    return out
