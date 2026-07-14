"""Scalar one-bar-at-a-time stepper for the carry_breakout sleeve.

SPEC: model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/carry_breakout.py
(byte-identical to FMA2 live — verified) together with the frozen core.py
(universe_frames / daily_closes / realized_vol / to_hourly).

Style contract (P1c): pure float64 scalar recurrences, one hourly union bar per
step, NO pandas, NO numpy, NO future reads.  math.* and Python float only.
The ewm-mean recurrence is the EXACT pandas 2.x Cython kernel
(window/aggregations.pyx `ewm`, adjust=True, ignore_na=False, normalize=True),
including the `weighted != cur` constant-series guard, so outputs are
bit-identical to pandas.

Two books stepped together each bar:

(A) CARRY (daily, 21 FX = core.FX order):
    - daily grid = SERVER-calendar days that contain >=1 union hourly bar
      (crypto trades weekends, so effectively every calendar day); daily close
      row = ffilled union-grid closes at the last hourly bar of the day
      (core.daily_closes semantics: resample('1D').last() of ffilled closes).
    - diff = POLICY_RATES[base] - POLICY_RATES[quote] (daily step tables),
      net = |diff| - SWAP_MARKUP(1.2); direction = sign(diff) where net > 0.5;
      cross-sectional rank of net among direction!=0 pairs, DESCENDING,
      pandas 'average' tie method; keep rank <= top_k(5);
      momentum gate: sign(dc/dc.shift(63) - 1) == direction (row shift on the
      daily grid, NOT calendar days);
      w = sig * 0.02 / max(vol30_daily, 0.05); NaN -> 0.
    - effectiveness (core.to_hourly, lag_hours=1): signal stamped at day P
      becomes the held target from the first union hourly bar of the next
      grid day.  Implemented causally: on the first bar of a new calendar
      day, the signal is computed from state as of the previous bar (= last
      bar of day P) and applied from this bar on.

(B) BREAKOUT (hourly, long-only Donchian ensemble on BK_UNIV):
    - two systems: n_fast=20d=480 bars (exit 8d=192), n_slow=40d=960
      (exit 16d=384); entry close > prior n-bar rolling close max (shift 1,
      min_periods=n); exit close < prior x-bar rolling close min OR chandelier
      close < best_close_since_entry - 3*ATR, ATR = ewm(|close.diff()|,
      span=480).mean() * 24; size FROZEN at entry
      = min(0.02 / max(vol30_hourly, 0.05), 1); on bars with no real bar or
      NaN hi/ATR the position is held unchanged (no best update, no exits);
    - ensemble = (fast + slow) / 2.

COMBINE per bar: pos = carry*1.35 + breakout*2.05; gross cap: scale by
min(1, 3.0 / gross); clip to [-1, 1].

vol30 (both books) = sqrt(ewm(ret^2, span=720).mean() * 24 * 365.25) on union
hourly returns, ret = clip(ffill_close.pct_change, +-0.30), 0 where the
previous ffilled close is NaN (core.universe_frames + core.realized_vol).

State is explicit and serializable (get_state / set_state -> plain dict of
lists/floats/ints) so a live EA can warm-start.
"""
import math

NAN = float("nan")
_EPOCH_ORD = 719163  # datetime.date(1970,1,1).toordinal()

# universe (source order — CARRY_UNIV == core.FX, BK_UNIV literal)
FX = ["AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
      "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
      "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY"]
BK_UNIV = ["XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD", "XNGUSD",
           "DAX", "JP225", "UK100", "US30", "USA500", "USTEC"]
SYMBOLS = FX + BK_UNIV
N_FX = len(FX)
N_BK = len(BK_UNIV)

# frozen parameters / calibration constants (carry_breakout.py)
SWAP_MARKUP = 1.2
RISK_PER_POS = 0.02
VOL_FLOOR = 0.05
W_CARRY = 1.35
W_BK = 2.05
GROSS_CAP = 3.0
EXIT_RATIO = 0.4
ATR_DAYS = 20
VOL_SPAN_DAYS = 30
CARRY_THR = 0.5
GATE_DAYS = 63
TOP_K = 5
N_FAST = 20
N_SLOW = 40
M_ATR = 3.0

VOL_SPAN_BARS = VOL_SPAN_DAYS * 24          # 720
ATR_SPAN_BARS = ATR_DAYS * 24               # 480
_N_FAST_BARS = N_FAST * 24                  # 480
_N_SLOW_BARS = N_SLOW * 24                  # 960
_X_FAST_BARS = max(5, int(round(EXIT_RATIO * N_FAST))) * 24   # 192
_X_SLOW_BARS = max(5, int(round(EXIT_RATIO * N_SLOW))) * 24   # 384
_ANNUALIZER = 24.0 * 365.25                 # applied as (var*24.0)*365.25


def _sign(x):
    """np.sign semantics on float64 (NaN -> NaN)."""
    if x != x:
        return NAN
    if x > 0.0:
        return 1.0
    if x < 0.0:
        return -1.0
    return 0.0


def parse_policy_rates(raw):
    """{ccy: [('YYYY-MM-DD', rate), ...]} -> {ccy: [(epoch_day, rate), ...]}
    keeping only 3-letter non-metal currencies (spec: _policy_rate_daily)."""
    import datetime as _dt
    out = {}
    for ccy, steps in raw.items():
        if len(ccy) != 3 or ccy.startswith("X"):
            continue
        rows = []
        for d, r in steps:
            y, m, dd = int(d[0:4]), int(d[5:7]), int(d[8:10])
            rows.append((_dt.date(y, m, dd).toordinal() - _EPOCH_ORD,
                         float(r)))
        rows.sort()
        out[ccy] = rows
    return out


class _Ewm:
    """pandas .ewm(span=N).mean(), adjust=True, ignore_na=False, min_periods=0.

    Exact port of pandas 2.x window/aggregations.pyx `ewm` (normalize=True):
      first call:   weighted = cur; nobs = is_obs; old_wt = 1
      later calls:  if weighted is not NaN:
                        old_wt *= (1 - alpha)            # every position
                        if is_obs:
                            if weighted != cur:          # constant guard
                                weighted = fma(old_wt, weighted, cur)
                                           / (old_wt + 1)
                            old_wt += 1                  # adjust=True
                    elif is_obs: weighted = cur
      output = weighted if nobs >= 1 else NaN

    NOTE (measured, this machine): pandas' compiled kernel contracts
    `old_wt*weighted + new_wt*cur` into an ARM64 fmadd (clang
    -ffp-contract=on), so bit-exactness requires math.fma here — verified
    bit-identical on random series incl. leading NaNs and constant runs,
    while the plain two-rounding form differs by 1 ulp.  An MQL5 port
    without FMA reproduces to ~1e-16 relative instead of exactly.
    """
    __slots__ = ("f", "weighted", "old_wt", "nobs", "started")

    def __init__(self, span):
        self.f = 1.0 - 2.0 / (span + 1.0)
        self.weighted = NAN
        self.old_wt = 1.0
        self.nobs = 0
        self.started = False

    def update(self, cur):
        is_obs = cur == cur
        if not self.started:
            self.started = True
            self.weighted = cur
            self.nobs = 1 if is_obs else 0
        else:
            if is_obs:
                self.nobs += 1
            if self.weighted == self.weighted:
                self.old_wt *= self.f
                if is_obs:
                    if self.weighted != cur:
                        w = math.fma(self.old_wt, self.weighted, cur)
                        self.weighted = w / (self.old_wt + 1.0)
                    self.old_wt += 1.0
            elif is_obs:
                self.weighted = cur

    def value(self):
        return self.weighted if self.nobs >= 1 else NAN

    def state(self):
        return [self.weighted, self.old_wt, self.nobs, 1 if self.started else 0]

    def load(self, st):
        self.weighted, self.old_wt = float(st[0]), float(st[1])
        self.nobs, self.started = int(st[2]), bool(st[3])


class _RollExtreme:
    """rolling(w).max()/min().shift(1), min_periods=w, on a series whose NaNs
    are leading-only (ffilled closes).  Monotonic deque of (push_idx, value);
    query at bar i covers pushes [i-w, i-1] (push AFTER query each bar)."""
    __slots__ = ("w", "is_max", "dq", "n_pushed", "n_valid")

    def __init__(self, w, is_max):
        self.w = w
        self.is_max = is_max
        self.dq = []          # list used as deque of [idx, val]
        self.n_pushed = 0
        self.n_valid = 0

    def query(self):
        # window = pushes [n_pushed - w, n_pushed - 1]
        if self.n_valid < self.w or self.n_pushed < self.w:
            return NAN
        lo = self.n_pushed - self.w
        dq = self.dq
        k = 0
        while dq[k][0] < lo:
            k += 1
        if k:
            del dq[:k]
        return dq[0][1]

    def push(self, val):
        if val == val:
            dq = self.dq
            if self.is_max:
                while dq and dq[-1][1] <= val:
                    dq.pop()
            else:
                while dq and dq[-1][1] >= val:
                    dq.pop()
            dq.append([self.n_pushed, val])
            self.n_valid += 1
        self.n_pushed += 1

    def state(self):
        return {"dq": [list(p) for p in self.dq],
                "n_pushed": self.n_pushed, "n_valid": self.n_valid}

    def load(self, st):
        self.dq = [[int(a), float(b)] for a, b in st["dq"]]
        self.n_pushed = int(st["n_pushed"])
        self.n_valid = int(st["n_valid"])


class _DonchianSystem:
    """One long-only Donchian state machine (frozen loop of
    _donchian_long_only): state in {0,1}, size frozen at entry, chandelier
    best-close trail."""
    __slots__ = ("state", "size", "best")

    def __init__(self):
        self.state = 0
        self.size = 0.0
        self.best = NAN

    def step(self, has_bar, c, hi, xlo, atr, vol):
        """Returns position = state*size AFTER processing this bar."""
        if (not has_bar) or (hi != hi) or (atr != atr):
            return self.state * self.size
        if self.state == 0:
            if c > hi:
                self.state = 1
                self.best = c
                self.size = min(RISK_PER_POS / max(vol, VOL_FLOOR), 1.0)
        else:
            if self.best < c:          # best = max(best, c) (NaN-free here)
                self.best = c
            if (xlo == xlo and c < xlo) or c < self.best - M_ATR * atr:
                self.state = 0
                self.size = 0.0
        return self.state * self.size

    def snap(self):
        return [self.state, self.size, self.best]

    def load(self, st):
        self.state, self.size, self.best = int(st[0]), float(st[1]), float(st[2])


class CarryBreakoutStepper:
    """Steps ALL 32 sleeve symbols together, one union hourly bar per call.

    step(epoch_day, closes) -> list of 32 target positions (SYMBOLS order),
      epoch_day: integer days since 1970-01-01 of the bar's SERVER timestamp,
      closes:    raw hourly closes, NaN where the symbol has no bar this hour.
    """

    def __init__(self, policy_rates):
        """policy_rates: {ccy: [(epoch_day:int, rate:float), ...]} sorted —
        see parse_policy_rates()."""
        self.rates = policy_rates
        self._pair_ccy = [(s[:3], s[3:]) for s in FX]

        self.c_ff = [NAN] * len(SYMBOLS)          # ffilled closes
        self.vol_ewm = [_Ewm(VOL_SPAN_BARS) for _ in SYMBOLS]
        self.atr_ewm = [_Ewm(ATR_SPAN_BARS) for _ in BK_UNIV]
        self.win_hi_f = [_RollExtreme(_N_FAST_BARS, True) for _ in BK_UNIV]
        self.win_hi_s = [_RollExtreme(_N_SLOW_BARS, True) for _ in BK_UNIV]
        self.win_lo_f = [_RollExtreme(_X_FAST_BARS, False) for _ in BK_UNIV]
        self.win_lo_s = [_RollExtreme(_X_SLOW_BARS, False) for _ in BK_UNIV]
        self.sys_f = [_DonchianSystem() for _ in BK_UNIV]
        self.sys_s = [_DonchianSystem() for _ in BK_UNIV]

        self.cur_day = None            # epoch_day of the bar being processed
        self.dc_hist = []              # last <=GATE_DAYS+1 daily FX close rows
        self.w_eff = [0.0] * N_FX      # effective carry weights (pre W_CARRY)
        self.bar_i = 0

        # debug capture of the most recent carry roll (not part of state)
        self.last_carry = None

    # -- policy rate step lookup ------------------------------------------
    def _rate(self, ccy, day):
        rows = self.rates[ccy]
        lo, hi = 0, len(rows)
        if not rows or rows[0][0] > day:
            return NAN
        while hi - lo > 1:              # binary search: last row.day <= day
            mid = (lo + hi) // 2
            if rows[mid][0] <= day:
                lo = mid
            else:
                hi = mid
        return rows[lo][1]

    # -- carry daily roll (signal stamped at completed day P) -------------
    def _roll_day(self, day_p):
        dc_row = [self.c_ff[j] for j in range(N_FX)]
        self.dc_hist.append(dc_row)
        if len(self.dc_hist) > GATE_DAYS + 1:
            del self.dc_hist[0]

        direction = [0.0] * N_FX
        net = [NAN] * N_FX
        for j in range(N_FX):
            b, q = self._pair_ccy[j]
            d = self._rate(b, day_p) - self._rate(q, day_p)
            n = abs(d) - SWAP_MARKUP
            net[j] = n
            if n > CARRY_THR:           # False for NaN
                direction[j] = _sign(d)

        # cross-sectional descending rank, 'average' ties, keep <= TOP_K
        live = [(net[j], j) for j in range(N_FX) if direction[j] != 0.0]
        live.sort(key=lambda t: -t[0])
        i = 0
        while i < len(live):
            k = i
            while k < len(live) and live[k][0] == live[i][0]:
                k += 1
            r = (i + 1 + k) / 2.0
            if r > TOP_K:
                for m in range(i, k):
                    direction[live[m][1]] = 0.0
            i = k

        # momentum gate: row-shift GATE_DAYS on the daily grid
        have63 = len(self.dc_hist) > GATE_DAYS
        sig = [0.0] * N_FX
        for j in range(N_FX):
            if direction[j] == 0.0:
                continue
            mom = NAN
            if have63:
                mom = dc_row[j] / self.dc_hist[-(GATE_DAYS + 1)][j] - 1.0
            if _sign(mom) == direction[j]:
                sig[j] = direction[j]

        w = [0.0] * N_FX
        for j in range(N_FX):
            v = self.vol_ewm[j].value()          # vol at day P's last bar
            vol_d = math.sqrt((v * 24.0) * 365.25) if v == v else NAN
            if vol_d < VOL_FLOOR:                # pandas clip(lower=): NaN kept
                vol_d = VOL_FLOOR
            wj = sig[j] * RISK_PER_POS / vol_d
            if wj != wj:                          # w.fillna(0.0)
                wj = 0.0
            w[j] = wj
        self.w_eff = w
        self.last_carry = {"day": day_p, "net": net, "direction": direction,
                           "sig": sig, "w": w}

    # -- one union hourly bar ---------------------------------------------
    def step(self, epoch_day, closes):
        if self.cur_day is not None and epoch_day != self.cur_day:
            self._roll_day(self.cur_day)
        self.cur_day = epoch_day

        pos = [0.0] * len(SYMBOLS)

        for j in range(len(SYMBOLS)):
            raw = closes[j]
            has = raw == raw
            prev = self.c_ff[j]
            c = raw if has else prev
            # ret: 0 where prev ffilled close is NaN; clip +-0.30
            if prev != prev:
                r = 0.0
            else:
                r = c / prev - 1.0
                if r > 0.30:
                    r = 0.30
                elif r < -0.30:
                    r = -0.30
            self.c_ff[j] = c
            self.vol_ewm[j].update(r * r)

            if j < N_FX:
                pos[j] = self.w_eff[j] * W_CARRY
                continue

            # ---- breakout symbol ----
            k = j - N_FX
            d = c - prev                      # close.diff(): NaN propagates
            self.atr_ewm[k].update(abs(d) if d == d else NAN)
            av = self.atr_ewm[k].value()
            atr = av * 24.0 if av == av else NAN
            vv = self.vol_ewm[j].value()
            vol = math.sqrt((vv * 24.0) * 365.25)

            hi_f = self.win_hi_f[k].query()
            hi_s = self.win_hi_s[k].query()
            xlo_f = self.win_lo_f[k].query()
            xlo_s = self.win_lo_s[k].query()

            of = self.sys_f[k].step(has, c, hi_f, xlo_f, atr, vol)
            os_ = self.sys_s[k].step(has, c, hi_s, xlo_s, atr, vol)
            pos[j] = ((of + os_) / 2.0) * W_BK

            self.win_hi_f[k].push(c)
            self.win_hi_s[k].push(c)
            self.win_lo_f[k].push(c)
            self.win_lo_s[k].push(c)

        # sleeve gross cap + unit clip
        gross = 0.0
        for p in pos:
            gross += abs(p)
        scale = GROSS_CAP / gross if gross > 0.0 else 1.0
        if scale > 1.0:
            scale = 1.0
        for j in range(len(SYMBOLS)):
            p = pos[j] * scale
            if p > 1.0:
                p = 1.0
            elif p < -1.0:
                p = -1.0
            pos[j] = p

        self.bar_i += 1
        return pos

    # -- serializable state -------------------------------------------------
    def get_state(self):
        return {
            "version": 1,
            "symbols": list(SYMBOLS),
            "bar_i": self.bar_i,
            "cur_day": self.cur_day,
            "c_ff": list(self.c_ff),
            "vol_ewm": [e.state() for e in self.vol_ewm],
            "atr_ewm": [e.state() for e in self.atr_ewm],
            "win_hi_f": [wnd.state() for wnd in self.win_hi_f],
            "win_hi_s": [wnd.state() for wnd in self.win_hi_s],
            "win_lo_f": [wnd.state() for wnd in self.win_lo_f],
            "win_lo_s": [wnd.state() for wnd in self.win_lo_s],
            "sys_f": [s.snap() for s in self.sys_f],
            "sys_s": [s.snap() for s in self.sys_s],
            "dc_hist": [list(r) for r in self.dc_hist],
            "w_eff": list(self.w_eff),
        }

    def set_state(self, st):
        assert st["symbols"] == list(SYMBOLS)
        self.bar_i = int(st["bar_i"])
        self.cur_day = st["cur_day"]
        self.c_ff = [float(x) for x in st["c_ff"]]
        for e, s in zip(self.vol_ewm, st["vol_ewm"]):
            e.load(s)
        for e, s in zip(self.atr_ewm, st["atr_ewm"]):
            e.load(s)
        for w, s in zip(self.win_hi_f, st["win_hi_f"]):
            w.load(s)
        for w, s in zip(self.win_hi_s, st["win_hi_s"]):
            w.load(s)
        for w, s in zip(self.win_lo_f, st["win_lo_f"]):
            w.load(s)
        for w, s in zip(self.win_lo_s, st["win_lo_s"]):
            w.load(s)
        for d, s in zip(self.sys_f, st["sys_f"]):
            d.load(s)
        for d, s in zip(self.sys_s, st["sys_s"]):
            d.load(s)
        self.dc_hist = [[float(x) for x in r] for r in st["dc_hist"]]
        self.w_eff = [float(x) for x in st["w_eff"]]
