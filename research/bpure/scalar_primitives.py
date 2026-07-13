"""
FMA3 P1c KILL-SWITCH part 1 — scalar-double reference implementations of the 7
shared pandas numeric primitives, as an MQL5-faithful proxy.

KEY INSIGHT: IEEE-754 binary64 arithmetic is bit-identical across pandas scalar
ops / C / MQL5 double. Therefore an EXPLICIT SCALAR recurrence — a plain per-bar
Python `for` loop using only Python `float` (== C double) arithmetic, NO numpy
vectorization, NO pandas — is a faithful proxy for what a native MQL5 stepper
would compute. Each function here mirrors the exact pandas convention used by the
shipped book (see SHIPPED-BOOK SOURCE MAP) so that a later MQL5 port can be unit
-paritied against these, and these against pandas.

Conventions locked to the shipped code (FMA2/research):
  * ewm mean : .ewm(span=N).mean()        -> adjust=True, ignore_na=False
               (core.realized_vol, mag_xau, carry_breakout ATR, crisis smoothing)
  * ewm std  : .ewm(span=N).std()         -> adjust=True, ignore_na=False, bias=False
               (crisis _SIZE_SPAN sizing vol)
  * rolling  : .rolling(w).std()          -> ddof=1
               (crisis vol-ratio windows, meanrev)
  * donchian : .rolling(n).max().shift(1) -> min_periods=n, explicit 1-bar shift
               (carry_breakout breakout channel)
  * sma      : .rolling(w).mean()
  * to_hourly: index + lag_d d + (lag_h-1)h; reindex(union).ffill().reindex(hourly)
               (core.to_hourly)
  * daily    : .resample('1D').last()      (server-midnight day boundary)

NaN handling: math.nan is used for "no value". `x == x` is False iff x is NaN,
which is the exact observation test pandas' Cython kernels use.
"""
import math

NAN = float("nan")


def _isobs(x):
    """True iff x is a real observation (not NaN). Mirrors pandas `val == val`."""
    return x == x


# ---------------------------------------------------------------------------
# (1) EWM MEAN — pandas adjust=True, ignore_na=False
# ---------------------------------------------------------------------------
def ewm_mean(x, span):
    """Exponentially-weighted mean, adjust=True, ignore_na=False.

    adjust=True   => mean_t = sum_i f^(t-i) x_i / sum_i f^(t-i)  over observations i<=t
    ignore_na=False => the decay exponent counts EVERY bar position, so an interior
                       NaN still multiplies the running weight by f (decays it) but
                       contributes nothing to numerator/denominator.

    Incremental double recurrence:
        num, den  accumulate  sum f^(t-i) x_i  and  sum f^(t-i)
        every bar:            num *= f ; den *= f            (decay one position)
        on observation:       num += x ; den += 1.0
        output:               num/den   (NaN until first observation)
    """
    alpha = 2.0 / (span + 1.0)
    f = 1.0 - alpha                      # old_wt decay factor per position
    n = len(x)
    out = [NAN] * n
    num = 0.0
    den = 0.0
    seen = False
    for t in range(n):
        # decay every position (this is what makes it ignore_na=False)
        num *= f
        den *= f
        xi = x[t]
        if _isobs(xi):
            num += xi
            den += 1.0
            seen = True
        if seen:
            out[t] = num / den
    return out


def ewm_mean_adjustFALSE(x, span):
    """FAILURE-MODE probe: adjust=False recursive form.  mean_t = alpha*x_t +
    (1-alpha)*mean_{t-1}, seeded mean_0 = x_0.  Included only to DEMONSTRATE
    gross divergence from the mandatory adjust=True convention."""
    alpha = 2.0 / (span + 1.0)
    f = 1.0 - alpha
    n = len(x)
    out = [NAN] * n
    m = NAN
    for t in range(n):
        xi = x[t]
        if _isobs(xi):
            m = xi if not _isobs(m) else (alpha * xi + f * m)
        out[t] = m
    return out


# ---------------------------------------------------------------------------
# (2) EWM STD — pandas adjust=True, ignore_na=False, bias=False
#     (Welford-weighted online ewmcov with x==y, then debias)
# ---------------------------------------------------------------------------
def ewm_std(x, span, minp=1):
    """Bias-corrected EW std.  Mirrors pandas _libs ewmcov(x,x, bias=False).

    Tracks weighted mean, weighted cov, sum_wt, sum_wt2, old_wt.
    Debiased variance = cov * sum_wt^2 / (sum_wt^2 - sum_wt2).
    """
    alpha = 2.0 / (span + 1.0)
    old_wt_factor = 1.0 - alpha
    new_wt = 1.0                          # adjust=True
    n = len(x)
    out = [NAN] * n

    mean = NAN
    cov = 0.0
    sum_wt = 1.0
    sum_wt2 = 1.0
    old_wt = 1.0
    nobs = 0

    for t in range(n):
        cur = x[t]
        is_obs = _isobs(cur)
        nobs += 1 if is_obs else 0
        if _isobs(mean):
            # decay every position (ignore_na=False -> always decay)
            sum_wt *= old_wt_factor
            sum_wt2 *= old_wt_factor * old_wt_factor
            old_wt *= old_wt_factor
            if is_obs:
                old_mean = mean
                if mean != cur:
                    mean = (old_wt * old_mean + new_wt * cur) / (old_wt + new_wt)
                cov = ((old_wt * (cov + (old_mean - mean) * (old_mean - mean)))
                       + (new_wt * (cur - mean) * (cur - mean))) / (old_wt + new_wt)
                sum_wt += new_wt
                sum_wt2 += new_wt * new_wt
                old_wt += new_wt
        elif is_obs:
            mean = cur

        if nobs >= minp:
            numer = sum_wt * sum_wt - sum_wt2
            if numer > 0.0:
                var = (sum_wt * sum_wt / numer) * cov
                out[t] = math.sqrt(var) if var >= 0.0 else NAN
            else:
                out[t] = NAN
    return out


# ---------------------------------------------------------------------------
# (3) ROLLING STD ddof=1 — ring buffer
# ---------------------------------------------------------------------------
def rolling_std(x, window, ddof=1, minp=None):
    """Windowed sample std, ddof=1, min_periods=window by default.

    Ring buffer of the last `window` raw values; per step compute mean then
    sum of squared deviations (two-pass over the small window) -> cleanest
    parity.  A native port can hold the same fixed ring and two accumulators.
    """
    if minp is None:
        minp = window
    n = len(x)
    out = [NAN] * n
    buf = [0.0] * window
    filled = 0
    head = 0
    for t in range(n):
        xi = x[t]
        buf[head] = xi
        head = (head + 1) % window
        if filled < window:
            filled += 1
        cnt = filled
        # count real observations in current window
        m = min(cnt, window)
        # gather the m most-recent values
        # (ring is buf; the window is the last m entries)
        s = 0.0
        k = 0
        for j in range(m):
            v = buf[(head - 1 - j) % window]
            if _isobs(v):
                s += v
                k += 1
        if k >= minp and k - ddof > 0:
            mean = s / k
            ss = 0.0
            for j in range(m):
                v = buf[(head - 1 - j) % window]
                if _isobs(v):
                    d = v - mean
                    ss += d * d
            out[t] = math.sqrt(ss / (k - ddof))
    return out


def rolling_std_ddof0(x, window):
    """FAILURE-MODE probe: population std (ddof=0). Included to show gross
    divergence from the mandatory ddof=1 convention on small windows."""
    return rolling_std(x, window, ddof=0)


# ---------------------------------------------------------------------------
# (4) DONCHIAN max/min — monotonic deque, min_periods=window, explicit shift(1)
# ---------------------------------------------------------------------------
def donchian_max(x, window):
    """rolling(window).max().shift(1) — the channel top known at bar t is the
    max of [t-window .. t-1].  Monotonic-decreasing deque of indices."""
    n = len(x)
    raw = [NAN] * n          # rolling(window).max() aligned at bar t
    dq = []                  # indices, values monotonically decreasing
    cnt = 0
    for t in range(n):
        xi = x[t]
        # evict out-of-window front
        while dq and dq[0] <= t - window:
            dq.pop(0)
        if _isobs(xi):
            while dq and x[dq[-1]] <= xi:
                dq.pop()
            dq.append(t)
            cnt += 1
        if t >= window - 1 and dq:
            raw[t] = x[dq[0]]
    # explicit shift(1)
    return [NAN] + raw[:-1]


def donchian_min(x, window):
    """rolling(window).min().shift(1) — monotonic-increasing deque."""
    n = len(x)
    raw = [NAN] * n
    dq = []
    for t in range(n):
        xi = x[t]
        while dq and dq[0] <= t - window:
            dq.pop(0)
        if _isobs(xi):
            while dq and x[dq[-1]] >= xi:
                dq.pop()
            dq.append(t)
        if t >= window - 1 and dq:
            raw[t] = x[dq[0]]
    return [NAN] + raw[:-1]


# ---------------------------------------------------------------------------
# (5) SMA — rolling(window).mean()
# ---------------------------------------------------------------------------
def sma(x, window, minp=None):
    """Simple moving average; running sum add/remove over a ring."""
    if minp is None:
        minp = window
    n = len(x)
    out = [NAN] * n
    buf = [0.0] * window
    head = 0
    s = 0.0
    k = 0
    filled = 0
    for t in range(n):
        # remove value leaving the window
        if filled == window:
            old = buf[head]
            if _isobs(old):
                s -= old
                k -= 1
        xi = x[t]
        buf[head] = xi
        head = (head + 1) % window
        if filled < window:
            filled += 1
        if _isobs(xi):
            s += xi
            k += 1
        if k >= minp and k > 0:
            out[t] = s / k
    return out


# ---------------------------------------------------------------------------
# (6) to_hourly — daily signal mapped onto the hourly grid, causal +lag shift
# ---------------------------------------------------------------------------
def to_hourly(daily_ts, daily_val, hourly_ts, lag_days=1, lag_hours=1):
    """Mirror core.to_hourly.

    Shift each daily stamp by +lag_days days +(lag_hours-1) hours, then step-
    function forward-fill onto the hourly grid: hourly value at time h is the
    most recent shifted daily value with stamp <= h (NaN before the first).

    All timestamps are integer nanoseconds (or any monotone int/float epoch).
    Both arrays assumed sorted ascending.
    """
    shift = lag_days * 86400_000_000_000 + (lag_hours - 1) * 3600_000_000_000
    shifted = [ts + shift for ts in daily_ts]
    n = len(hourly_ts)
    out = [NAN] * n
    j = 0
    nd = len(shifted)
    cur = NAN
    for i in range(n):
        h = hourly_ts[i]
        while j < nd and shifted[j] <= h:
            cur = daily_val[j]
            j += 1
        out[i] = cur
    return out


# ---------------------------------------------------------------------------
# (7) daily finalize — resample('1D').last()
# ---------------------------------------------------------------------------
def resample_1d_last(ts, val):
    """resample('1D').last() on a server-midnight day boundary.

    Returns (day_start_ns, last_value) for each calendar day that has >=1 bar,
    where last_value is the last non-NaN observation within [day, day+1).
    pandas '1D' bins on the floor-to-midnight of each timestamp.
    """
    DAY = 86400_000_000_000
    if not ts:
        return [], []
    # per-day last observation into a dict keyed by day-start ns
    day_last = {}
    for i in range(len(ts)):
        day = (ts[i] // DAY) * DAY
        v = val[i]
        if _isobs(v):
            day_last[day] = v            # later bar overwrites -> keeps the last
        elif day not in day_last:
            day_last[day] = NAN
    # pandas emits a CONTIGUOUS daily grid from first to last day (gaps -> NaN)
    first = (ts[0] // DAY) * DAY
    last = (ts[-1] // DAY) * DAY
    out_ts = []
    out_val = []
    d = first
    while d <= last:
        out_ts.append(d)
        out_val.append(day_last.get(d, NAN))
        d += DAY
    return out_ts, out_val
