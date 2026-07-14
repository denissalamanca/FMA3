"""meanrev sleeve — scalar one-bar-at-a-time stepper (MQL5-faithful proxy).

SPEC: model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/meanrev.py
(byte-identical to FMA2/research/sleeves/meanrev.py, sha256
b23cc5a92dd15c6f364a4e974826681bf947368456772885f54631c1514b5752) plus the
core.py helpers it calls (universe_frames ret construction, realized_vol,
daily_closes, to_hourly).

CONTRACT (bpure shared): pure Python float64 scalars, ONE hourly bar at a
time, no pandas / no numpy / no future reads. All 16 sleeve symbols are
stepped together per bar so the sleeve-internal GROSS_CAP=3.0 cross-symbol
renorm is computed inside the sleeve (it binds a large share of hours).
Explicit serializable STATE (get_state / set_state) so a live EA can
warm-start.

Faithful conventions implemented here (verify-against-source notes):

* Hourly return (core.universe_frames): ffilled union close,
  ret = c_t/c_{t-1} - 1 (0.0 when prev ffilled close is NaN, i.e. before the
  symbol's first bar; 0.0 exactly on stale-ffilled bars), clipped to
  [-0.30, +0.30]. NO NaN ever -> every hourly bar is an ewm observation.

* Sizing vol (core.realized_vol, VOL_SPAN=30 days -> ewm span=720 HOURLY
  bars): pandas ewm(adjust=True, ignore_na=False, min_periods=0) kernel on
  ret^2, replicated op-for-op including pandas' `weighted != cur` skip
  branch (matters while ret==0 pre-first-move):
      alpha  = 1/(1+com), com=(span-1)/2
      first obs:  wavg = x ; old_wt = 1
      each next:  old_wt *= (1-alpha)
                  if wavg != x: wavg = (old_wt*wavg + x); wavg /= (old_wt+1)
                  old_wt += 1
  vol = sqrt(wavg * 24.0 * 365.25)  (same association order as core).

* DAILY grid: a day exists iff the union hourly grid has at least one bar
  stamped in that (server) calendar day AND at least one sleeve symbol has a
  non-NaN ffilled close by day end (mirrors resample('1D').last()
  .dropna(how='all') — empty resample bins are dropped, so weekends with no
  union bars do NOT exist as rows). Daily close = ffilled close at the last
  hourly bar of the day; daily vol = ewm vol at that same bar
  (resample('1D').last().reindex(px.index).ffill()).

* FX leg: z = (px - SMA60)/SD60 with SD ddof=1 two-pass over the 60-day ring
  (window = 60 daily ROWS incl. today; NaN in window -> z NaN). Hysteresis:
  s==0: z>2.25 -> -1, z<-2.25 -> +1;  s==-1 exits when z<0.75, s==+1 exits
  when z>-0.75; transitions only when z is FINITE (inf from sd==0 is
  skipped, numpy isfinite semantics).

* Index leg: z = (px/px[t-5]-1) / (vol_d * sqrt(5/365.25)) with numpy
  division semantics (x/0 -> +-inf, 0/0 -> NaN); trend = px > SMA200
  (False when SMA undefined). s==0: enter +1 iff z<-1.5 AND trend (held=0);
  s==1: held += 1 on each FINITE-z day, exit when z>0.0 or held>=10.
  Non-finite z day: state persists, held NOT incremented.

* Size frozen at entry: on any day where st!=0 and (first daily row or
  st_prev != st): size = K / max(vol_d, 0.05)  (0.07 numerator, VOL_SPAN=30
  vol — NOT 60d). pos_raw = st*size, clipped to [-1, +1] per instrument.

* Sleeve gross cap: gross = sum(|pos|) across the 16 symbols in SYMBOLS
  order; scale = min(1.0, 3.0/gross) (gross==0 -> inf -> 1.0);
  pos_final = pos_clipped * scale. Computed INSIDE the sleeve every day.

* to_hourly EXEC_LAG=14: daily target of day d becomes effective at the
  first union hourly bar stamped >= (d+1) 13:00 and is held (ffill) until
  replaced. Positions before the first effective stamp are 0.0.

Usage:
    stp = MeanrevStepper()
    for ts, closes in hourly_stream:          # ts strictly increasing
        pos = stp.step(ts, closes)            # {sym: fraction of equity}
    stp.finalize()                            # flush trailing day (records)
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

NAN = float("nan")
INF = float("inf")

FX_CROSSES = ["AUDNZD", "EURCHF", "EURGBP", "EURSEK", "EURNOK",
              "AUDCAD", "NZDCAD", "CADCHF", "EURCAD", "EURNZD"]
INDICES = ["DAX", "JP225", "UK100", "US30", "USA500", "USTEC"]
SYMBOLS = FX_CROSSES + INDICES

PARAMS = {
    "L": 60, "Z_IN": 2.25, "Z_OUT": 0.75,
    "D": 5, "Z_ENTRY": 1.5, "K": 0.07,
    "Z_EXIT": 0.0, "TREND_L": 200, "MAX_HOLD": 10,
    "EXEC_LAG": 14, "VOL_FLOOR": 0.05, "POS_CAP": 1.0,
    "GROSS_CAP": 3.0, "VOL_SPAN": 30,
}

_RING = 256  # ring buffer capacity >= max(TREND_L, L) = 200


def _isnan(x: float) -> bool:
    return x != x


def _np_div(a: float, b: float) -> float:
    """numpy elementwise division semantics for scalars."""
    if _isnan(a) or _isnan(b):
        return NAN
    if b == 0.0:
        if a == 0.0:
            return NAN
        pos = (a > 0.0) == (math.copysign(1.0, b) > 0.0)
        return INF if pos else -INF
    return a / b


class MeanrevStepper:
    """Steps all 16 meanrev symbols together, one HOURLY bar at a time."""

    def __init__(self, params: dict | None = None, record: bool = False):
        p = dict(PARAMS)
        if params:
            p.update(params)
        self.p = p
        span = float(p["VOL_SPAN"] * 24)          # 720 hourly bars
        com = (span - 1.0) / 2.0                  # pandas span -> com
        alpha = 1.0 / (1.0 + com)
        self._f = 1.0 - alpha                     # old_wt decay factor
        self._sqrt_d = math.sqrt(p["D"] / 365.25)

        # --- per-symbol hourly state ---
        self.close = {s: NAN for s in SYMBOLS}    # ffilled union close
        self.wavg = {s: NAN for s in SYMBOLS}     # ewm weighted average of ret^2
        self.old_wt = {s: 1.0 for s in SYMBOLS}
        self.nobs = {s: 0 for s in SYMBOLS}

        # --- per-symbol daily state ---
        self.dbuf = {s: [NAN] * _RING for s in SYMBOLS}  # daily close ring
        self.dptr = {s: 0 for s in SYMBOLS}
        self.dcount = 0                            # daily rows pushed (global)
        self.st = {s: 0 for s in SYMBOLS}          # hysteresis / dip state
        self.held = {s: 0 for s in INDICES}        # index holding-day counter
        self.size = {s: 0.0 for s in SYMBOLS}      # frozen entry size

        # --- execution state ---
        self.cur_day: date | None = None
        self.pos = {s: 0.0 for s in SYMBOLS}       # active hourly position
        self.pending: list[tuple[datetime, dict]] = []

        # --- optional per-day records (validation) ---
        self.record = record
        if record:
            self.rec_day: list[date] = []
            self.rec_px: list[list[float]] = []
            self.rec_vol: list[list[float]] = []
            self.rec_w: list[list[float]] = []
            self.rec_z: list[list[float]] = []     # FX z then IDX z, SYMBOLS order
            self.rec_st: list[list[int]] = []
            self.rec_pos: list[list[float]] = []

    # ------------------------------------------------------------------ #
    # hourly step
    # ------------------------------------------------------------------ #
    def step(self, ts: datetime, closes: dict) -> dict:
        """Process ONE hourly union-grid bar. `closes[sym]` is the raw close
        (NaN / missing when the symbol printed no bar this hour). Returns the
        active position {sym: frac of equity} for this bar."""
        d = ts.date()
        if self.cur_day is not None and d != self.cur_day:
            self._finalize_day(self.cur_day)
        self.cur_day = d

        f = self._f
        for s in SYMBOLS:
            c = closes.get(s, NAN)
            prev = self.close[s]
            if not _isnan(c):
                self.close[s] = c
            cc = self.close[s]
            # hourly ret on the ffilled close; 0.0 when prev is NaN
            if _isnan(prev) or _isnan(cc):
                r = 0.0
            else:
                r = cc / prev - 1.0
                if r > 0.30:
                    r = 0.30
                elif r < -0.30:
                    r = -0.30
            x = r * r
            # pandas ewm adjust=True kernel (see module docstring)
            if self.nobs[s] == 0:
                self.wavg[s] = x
                self.old_wt[s] = 1.0
                self.nobs[s] = 1
            else:
                ow = self.old_wt[s] * f
                w = self.wavg[s]
                if w != x:
                    w = ow * w + x
                    w /= ow + 1.0
                    self.wavg[s] = w
                self.old_wt[s] = ow + 1.0
                self.nobs[s] += 1

        # apply any daily targets that have become effective (ffill semantics)
        while self.pending and self.pending[0][0] <= ts:
            self.pos = self.pending.pop(0)[1]
        return dict(self.pos)

    def finalize(self) -> None:
        """Flush the trailing (still-open) day — call once after the stream
        ends if you need its daily state/records or its pending target."""
        if self.cur_day is not None:
            self._finalize_day(self.cur_day)
            self.cur_day = None

    # ------------------------------------------------------------------ #
    # daily close-of-day logic
    # ------------------------------------------------------------------ #
    def _vol_now(self, s: str) -> float:
        if self.nobs[s] == 0:
            return NAN
        return math.sqrt(self.wavg[s] * 24.0 * 365.25)

    def _win(self, s: str, n: int, back: int = 0):
        """Last `n` daily ring values ending `back` rows before the newest
        (back=0 -> includes today). None if fewer than n+back rows exist."""
        if self.dcount < n + back:
            return None
        base = self.dptr[s] - 1 - back
        return [self.dbuf[s][(base - i) % _RING] for i in range(n)]

    def _finalize_day(self, day: date) -> None:
        p = self.p
        px = {s: self.close[s] for s in SYMBOLS}
        # mirror dropna(how='all'): a day with no sleeve close yet is not a row
        if all(_isnan(px[s]) for s in SYMBOLS):
            return
        vol = {s: self._vol_now(s) for s in SYMBOLS}

        first_row = (self.dcount == 0)
        # push today's daily closes into the rings (window includes today);
        # all rings advance together on one global daily-row pointer
        ptr = self.dptr[SYMBOLS[0]]
        for s in SYMBOLS:
            self.dbuf[s][ptr] = px[s]
            self.dptr[s] = (ptr + 1) % _RING
        self.dcount += 1

        z_all = {}
        st_prev = dict(self.st)

        # ---- FX leg: z = (px - SMA_L)/SD_L, hysteresis state machine ----
        L, z_in, z_out = p["L"], p["Z_IN"], p["Z_OUT"]
        for s in FX_CROSSES:
            zt = NAN
            w = self._win(s, L)
            if w is not None and not any(_isnan(v) for v in w):
                tot = 0.0
                for v in w:
                    tot += v
                mean = tot / L
                acc = 0.0
                for v in w:
                    dv = v - mean
                    acc += dv * dv
                sd = math.sqrt(acc / (L - 1))      # ddof=1, two-pass
                zt = _np_div(px[s] - mean, sd)
            z_all[s] = zt
            st = self.st[s]
            if math.isfinite(zt):
                if st == 0:
                    if zt > z_in:
                        st = -1
                    elif zt < -z_in:
                        st = 1
                elif (st == -1 and zt < z_out) or (st == 1 and zt > -z_out):
                    st = 0
            self.st[s] = st

        # ---- Index leg: vol-scaled D-day dip, long-only ----
        D, z_entry, z_exit = p["D"], p["Z_ENTRY"], p["Z_EXIT"]
        trend_L, max_hold = p["TREND_L"], p["MAX_HOLD"]
        for s in INDICES:
            zt = NAN
            w5 = self._win(s, 1, back=D)           # px[t-D]
            if w5 is not None and not _isnan(w5[0]) and not _isnan(px[s]):
                pct = px[s] / w5[0] - 1.0
                zt = _np_div(pct, vol[s] * self._sqrt_d)
            z_all[s] = zt
            tv = False
            wt = self._win(s, trend_L)
            if wt is not None and not any(_isnan(v) for v in wt):
                tot = 0.0
                for v in wt:
                    tot += v
                sma = tot / trend_L
                tv = px[s] > sma
            st = self.st[s]
            if math.isfinite(zt):
                if st == 0:
                    if zt < -z_entry and tv:
                        st, self.held[s] = 1, 0
                else:
                    self.held[s] += 1
                    if zt > z_exit or self.held[s] >= max_hold:
                        st = 0
            self.st[s] = st

        # ---- size frozen at entry, per-inst cap, sleeve gross cap ----
        K, floor, cap, gcap = p["K"], p["VOL_FLOOR"], p["POS_CAP"], p["GROSS_CAP"]
        pos_c = {}
        w_all = {}
        for s in SYMBOLS:
            v = vol[s]
            vc = v if (_isnan(v) or v > floor) else floor   # clip(lower=floor)
            wgt = K / vc
            w_all[s] = wgt
            st = self.st[s]
            if st != 0 and (first_row or st_prev[s] != st):
                self.size[s] = wgt
            pr = st * self.size[s]
            if pr > cap:
                pr = cap
            elif pr < -cap:
                pr = -cap
            pos_c[s] = pr
        gross = 0.0
        for s in SYMBOLS:
            gross += abs(pos_c[s])
        scale = _np_div(gcap, gross)
        if scale > 1.0:                    # clip(upper=1.0): inf -> 1.0, NaN stays
            scale = 1.0
        pos_f = {s: pos_c[s] * scale for s in SYMBOLS}

        # effective at the first hourly bar >= (d+1) 13:00  (EXEC_LAG=14)
        eff = datetime.combine(day, time()) + timedelta(days=1,
                                                        hours=p["EXEC_LAG"] - 1)
        self.pending.append((eff, pos_f))

        if self.record:
            self.rec_day.append(day)
            self.rec_px.append([px[s] for s in SYMBOLS])
            self.rec_vol.append([vol[s] for s in SYMBOLS])
            self.rec_w.append([w_all[s] for s in SYMBOLS])
            self.rec_z.append([z_all[s] for s in SYMBOLS])
            self.rec_st.append([self.st[s] for s in SYMBOLS])
            self.rec_pos.append([pos_f[s] for s in SYMBOLS])

    # ------------------------------------------------------------------ #
    # serializable state (EA warm-start)
    # ------------------------------------------------------------------ #
    def get_state(self) -> dict:
        ptr = self.dptr[SYMBOLS[0]]
        return {
            "version": 1,
            "params": dict(self.p),
            "cur_day": self.cur_day.isoformat() if self.cur_day else None,
            "dcount": self.dcount,
            "dptr": ptr,
            "close": {s: self.close[s] for s in SYMBOLS},
            "wavg": {s: self.wavg[s] for s in SYMBOLS},
            "old_wt": {s: self.old_wt[s] for s in SYMBOLS},
            "nobs": {s: self.nobs[s] for s in SYMBOLS},
            "dbuf": {s: list(self.dbuf[s]) for s in SYMBOLS},
            "st": dict(self.st),
            "held": dict(self.held),
            "size": dict(self.size),
            "pos": dict(self.pos),
            "pending": [[e.isoformat(), dict(v)] for e, v in self.pending],
        }

    def set_state(self, st: dict) -> None:
        self.p = dict(st["params"])
        self.cur_day = (date.fromisoformat(st["cur_day"])
                        if st["cur_day"] else None)
        self.dcount = int(st["dcount"])
        ptr = int(st["dptr"])
        for s in SYMBOLS:
            self.close[s] = float(st["close"][s])
            self.wavg[s] = float(st["wavg"][s])
            self.old_wt[s] = float(st["old_wt"][s])
            self.nobs[s] = int(st["nobs"][s])
            self.dbuf[s] = [float(v) for v in st["dbuf"][s]]
            self.dptr[s] = ptr
            self.st[s] = int(st["st"][s])
            self.size[s] = float(st["size"][s])
        for s in INDICES:
            self.held[s] = int(st["held"][s])
        self.pos = {s: float(st["pos"][s]) for s in SYMBOLS}
        self.pending = [(datetime.fromisoformat(e), {k: float(v)
                                                     for k, v in d.items()})
                        for e, d in st["pending"]]
