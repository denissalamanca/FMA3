//+------------------------------------------------------------------+
//| V34Math.mqh — FMA3 v34 shared numeric primitives                 |
//|                                                                  |
//| 1:1 MQL5 ports of the inline primitive implementations of the    |
//| Wave-1 validated Python steppers (research/bpure/steppers/*.py,  |
//| state-exact vs frozen goldens, 1e-14 vs pandas).  Every constant,|
//| branch, guard and NaN rule is preserved verbatim.                |
//|                                                                  |
//| Sources (the spec):                                              |
//|   crisis_stepper.py        EwmMean / EwmStd / Ring / ring_* fns  |
//|                            banker_round                          |
//|   consolidate_p1c_stepper  _EwmStd + inline SMA ring (running    |
//|                            sum, minp==window)                    |
//|   carry_breakout_stepper   _Ewm (fma note) / _RollExtreme deque  |
//|   mag_xau_stepper          banker_round (same tie test)          |
//|   intraday/meanrev         numpy division semantics (_np_div)    |
//|   trend_v2_stepper         ewm min_periods gating (nobs >= minp) |
//|                                                                  |
//| FMA NOTE (from carry_breakout_stepper docstring, measured):      |
//| pandas' compiled ewma kernel contracts old_wt*avg + cur into an  |
//| ARM64 fmadd.  MQL5 has no fma, so this port reproduces the ewm   |
//| recurrences to ~1e-16 RELATIVE instead of bit-exact; every other |
//| primitive here is bit-exact by construction.                     |
//+------------------------------------------------------------------+
#ifndef FMA3V34_V34MATH_MQH
#define FMA3V34_V34MATH_MQH

//==================================================================//
// NaN / IEEE-754 helpers                                           //
//==================================================================//

// bit-view of a double (MQL5 union: no reinterpret casts needed)
union V34DoubleBits
  {
   double            d;
   long              l;
  };

// quiet NaN, deterministic bit pattern 0x7FF8000000000000
double V34Nan()
  {
   V34DoubleBits u;
   u.l = 0x7FF8000000000000;
   return u.d;
  }

// +infinity, bit pattern 0x7FF0000000000000
double V34Inf()
  {
   V34DoubleBits u;
   u.l = 0x7FF0000000000000;
   return u.d;
  }

// pandas observation test: x == x is false iff NaN  (steppers' _isobs)
bool V34IsNan(const double x)   { return (x != x); }
bool V34IsObs(const double x)   { return (x == x); }

// math.isfinite: not NaN and not +-inf
bool V34IsFinite(const double x)
  {
   if(x != x) return false;
   double inf = V34Inf();
   return (x < inf && x > -inf);
  }

// sign bit of a double (true for negatives INCLUDING -0.0) — needed to
// replicate math.copysign(1.0, b) on a zero divisor without dividing.
bool V34SignBit(const double x)
  {
   V34DoubleBits u;
   u.d = x;
   return (u.l < 0);
  }

//------------------------------------------------------------------//
// numpy elementwise division semantics for scalars                 //
// (meanrev_stepper._np_div == intraday_stepper._div, verbatim):    //
//   NaN operand      -> NaN                                        //
//   b == +-0:  a==0  -> NaN (0/0)                                  //
//              else  -> +-INF with sign  sign(a) * sign(b)         //
//   otherwise        -> a / b                                      //
// NOTE: never executes a floating divide by zero (MQL5-safe).      //
//------------------------------------------------------------------//
double V34NpDiv(const double a, const double b)
  {
   if(a != a || b != b)
      return V34Nan();
   if(b == 0.0)
     {
      if(a == 0.0)
         return V34Nan();
      // pos = (a > 0) == (copysign(1, b) > 0)
      bool pos = ((a > 0.0) == (!V34SignBit(b)));
      return pos ? V34Inf() : -V34Inf();
     }
   return a / b;
  }

//------------------------------------------------------------------//
// np.sign semantics on float64 (carry_breakout_stepper._sign)      //
//------------------------------------------------------------------//
double V34Sign(const double x)
  {
   if(x != x)   return V34Nan();
   if(x > 0.0)  return 1.0;
   if(x < 0.0)  return -1.0;
   return 0.0;
  }

//------------------------------------------------------------------//
// BankerRound — round-half-to-even at 0 decimals == numpy rint ==  //
// pandas .round(0).  Exact port of crisis_stepper.banker_round     //
// (same tie test as mag_xau_stepper.banker_round: for |x| < 2^52   //
// x - floor(x) is EXACT, so `d == 0.5` needs no epsilon).          //
// NEVER use MathRound here (half-away-from-zero).                  //
//------------------------------------------------------------------//
double V34BankerRound(const double x)
  {
   if(x != x)
      return V34Nan();
   double r = MathFloor(x);
   double d = x - r;
   if(d > 0.5)
      r += 1.0;
   else if(d == 0.5)
     {
      if(MathMod(r, 2.0) != 0.0)   // fmod: odd floor -> bump to even
         r += 1.0;
     }
   return r;
  }

//==================================================================//
// CV34EwmMean — pandas .ewm(span, adjust=True, ignore_na=False,    //
//               min_periods=minp).mean()                           //
// Exact port of crisis_stepper.EwmMean (== carry _Ewm == trend_v2  //
// inline kernel, all the same aggregations.pyx recurrence):        //
//   decay old_wt EVERY bar once seeded (incl. NaN bars),           //
//   `if avg != cur` constant-series guard kept verbatim,           //
//   old_wt += 1 only on an observation (adjust=True),              //
//   output NaN until nobs >= minp (crisis/carry: minp = 1).        //
//==================================================================//
class CV34EwmMean
  {
public:
   // --- serializable state (public on purpose: steppers round-trip it) ---
   double            m_f;        // 1 - 2/(span+1) = 1 - alpha
   int               m_minp;
   double            m_avg;      // pandas `weighted`
   double            m_old_wt;
   long              m_nobs;

                     CV34EwmMean() { Init(2.0, 1); }

   void              Init(const double span, const int minp = 1)
     {
      m_f      = 1.0 - 2.0 / (span + 1.0);
      m_minp   = minp;
      m_avg    = V34Nan();
      m_old_wt = 1.0;
      m_nobs   = 0;
     }

   // push one value (NaN allowed); returns current mean (NaN if gated)
   double            Step(const double cur)
     {
      bool is_obs = (cur == cur);
      if(is_obs)
         m_nobs++;
      if(m_avg == m_avg)
        {
         // ignore_na=False -> decay every position
         m_old_wt *= m_f;
         if(is_obs)
           {
            if(m_avg != cur)
               m_avg = (m_old_wt * m_avg + 1.0 * cur) / (m_old_wt + 1.0);
            m_old_wt += 1.0;
           }
        }
      else if(is_obs)
         m_avg = cur;
      return (m_nobs >= m_minp) ? m_avg : V34Nan();
     }

   double            Value() const { return (m_nobs >= m_minp) ? m_avg : V34Nan(); }
  };

//==================================================================//
// CV34EwmStd — pandas .ewm(span, min_periods=minp, adjust=True,    //
//              ignore_na=False).std()                              //
// Exact port of crisis_stepper.EwmStd == consolidate_p1c._EwmStd:  //
// bias-corrected Welford-weighted ewmcov(x, x, bias=False) tracking//
// mean/cov/sum_wt/sum_wt2/old_wt/nobs.                             //
//                                                                  //
// Negative-variance handling (the ONLY spot the two sources        //
// differ):                                                         //
//   crisis_stepper.EwmStd       : var < 0 -> 0.0   (pandas zsqrt)  //
//   consolidate_p1c._EwmStd     : var < 0 -> NaN                   //
// m_clamp_neg_var selects the flavor (default true = crisis/zsqrt);//
// pass false when porting consolidate_p1c.  cov >= 0 analytically, //
// so the branch fires only on ulp-level rounding — but keep both   //
// forms verbatim for bit-parity.                                   //
//==================================================================//
class CV34EwmStd
  {
public:
   // --- serializable state ---
   double            m_f;
   int               m_minp;
   bool              m_clamp_neg_var;
   double            m_mean;
   double            m_cov;
   double            m_sum_wt;
   double            m_sum_wt2;
   double            m_old_wt;
   long              m_nobs;

                     CV34EwmStd() { Init(2.0, 1, true); }

   void              Init(const double span, const int minp,
                          const bool clamp_neg_var = true)
     {
      m_f       = 1.0 - 2.0 / (span + 1.0);
      m_minp    = minp;
      m_clamp_neg_var = clamp_neg_var;
      m_mean    = V34Nan();
      m_cov     = 0.0;
      m_sum_wt  = 1.0;
      m_sum_wt2 = 1.0;
      m_old_wt  = 1.0;
      m_nobs    = 0;
     }

   // push one value (NaN allowed); returns current std (NaN if gated)
   double            Step(const double cur)
     {
      bool is_obs = (cur == cur);
      if(is_obs)
         m_nobs++;
      if(m_mean == m_mean)
        {
         // ignore_na=False -> decay every position
         m_sum_wt  *= m_f;
         m_sum_wt2 *= m_f * m_f;
         m_old_wt  *= m_f;
         if(is_obs)
           {
            double old_mean = m_mean;
            if(m_mean != cur)
               m_mean = ((m_old_wt * old_mean) + (1.0 * cur))
                        / (m_old_wt + 1.0);
            m_cov = ((m_old_wt *
                      (m_cov + ((old_mean - m_mean)
                                * (old_mean - m_mean))))
                     + (1.0 * ((cur - m_mean) * (cur - m_mean))))
                    / (m_old_wt + 1.0);
            m_sum_wt  += 1.0;
            m_sum_wt2 += 1.0;
            m_old_wt  += 1.0;
           }
        }
      else if(is_obs)
         m_mean = cur;
      if(m_nobs >= m_minp)
        {
         double numerator   = m_sum_wt * m_sum_wt;
         double denominator = numerator - m_sum_wt2;
         if(denominator > 0.0)
           {
            double var = (numerator / denominator) * m_cov;
            if(var == var && var >= 0.0)
               return MathSqrt(var);
            // pandas zsqrt clamps negatives to 0 (crisis flavor);
            // consolidate_p1c returns NaN
            return m_clamp_neg_var ? 0.0 : V34Nan();
           }
         return V34Nan();
        }
      return V34Nan();
     }
  };

//==================================================================//
// CV34Ring — fixed-size ring of raw values (NaN allowed),          //
// oldest->newest scan.  Exact port of crisis_stepper.Ring plus its //
// module-level ring_std_ddof1 / ring_mean / ring_max / ring_min    //
// two-pass recomputes (P1c convention: recompute per EMISSION,     //
// summation strictly oldest -> newest — order preserved).          //
//==================================================================//
class CV34Ring
  {
public:
   // --- serializable state ---
   int               m_window;   // capacity
   double            m_buf[];
   int               m_head;     // next write slot
   int               m_count;    // rows pushed (capped at capacity)

                     CV34Ring() { m_window = 0; m_head = 0; m_count = 0; }

   void              Init(const int window)
     {
      m_window = window;
      ArrayResize(m_buf, window);
      double nan = V34Nan();
      for(int i = 0; i < window; i++)
         m_buf[i] = nan;
      m_head  = 0;
      m_count = 0;
     }

   void              Push(const double x)
     {
      m_buf[m_head] = x;
      m_head = (m_head + 1) % m_window;
      if(m_count < m_window)
         m_count++;
     }

   int               Count() const { return m_count; }

   // j-th value (0 = oldest) of the trimmed window of length n
   // (internal indexing helper for the two-pass scans below)
   double            TrimmedAt(const int n, const int j) const
     {
      int idx = m_head - n + j;          // n <= m_count <= m_window
      idx %= m_window;
      if(idx < 0)
         idx += m_window;
      return m_buf[idx];
     }

   // pandas .rolling(window).std() (ddof=1, min_periods=minp) over the
   // last `window` pushed rows — two-pass recompute (ring_std_ddof1)
   double            StdDdof1(const int window, const int minp) const
     {
      int n = (m_count > window) ? window : m_count;
      double s = 0.0;
      int    k = 0;
      for(int j = 0; j < n; j++)
        {
         double v = TrimmedAt(n, j);
         if(v == v)
           {
            s += v;
            k++;
           }
        }
      if(k < minp || k - 1 <= 0)
         return V34Nan();
      double mean = s / k;
      double ss = 0.0;
      for(int j = 0; j < n; j++)
        {
         double v = TrimmedAt(n, j);
         if(v == v)
           {
            double d = v - mean;
            ss += d * d;
           }
        }
      return MathSqrt(ss / (k - 1));
     }

   // pandas .rolling(window, min_periods=minp).mean() — two-pass ring
   double            Mean(const int window, const int minp) const
     {
      int n = (m_count > window) ? window : m_count;
      double s = 0.0;
      int    k = 0;
      for(int j = 0; j < n; j++)
        {
         double v = TrimmedAt(n, j);
         if(v == v)
           {
            s += v;
            k++;
           }
        }
      if(k < minp)
         return V34Nan();
      return s / k;
     }

   // pandas .rolling(window, min_periods=minp).max() — exact window scan
   double            Max(const int window, const int minp) const
     {
      int n = (m_count > window) ? window : m_count;
      double m = V34Nan();
      int    k = 0;
      for(int j = 0; j < n; j++)
        {
         double v = TrimmedAt(n, j);
         if(v == v)
           {
            k++;
            if(!(m == m) || v > m)
               m = v;
           }
        }
      if(k < minp)
         return V34Nan();
      return m;
     }

   // pandas .rolling(window, min_periods=minp).min() — mirror of Max
   double            Min(const int window, const int minp) const
     {
      int n = (m_count > window) ? window : m_count;
      double m = V34Nan();
      int    k = 0;
      for(int j = 0; j < n; j++)
        {
         double v = TrimmedAt(n, j);
         if(v == v)
           {
            k++;
            if(!(m == m) || v < m)
               m = v;
           }
        }
      if(k < minp)
         return V34Nan();
      return m;
     }
  };

//==================================================================//
// CV34RollStd — rolling(window).std(ddof=1, min_periods=minp),     //
// one push per bar, two-pass recompute per emission (the steppers' //
// convention).  Thin stateful wrapper over CV34Ring.               //
//==================================================================//
class CV34RollStd
  {
public:
   CV34Ring          m_ring;
   int               m_window;
   int               m_minp;

                     CV34RollStd() { m_window = 0; m_minp = 0; }

   void              Init(const int window, const int minp)
     {
      m_window = window;
      m_minp   = minp;
      m_ring.Init(window);
     }

   double            Step(const double x)
     {
      m_ring.Push(x);
      return m_ring.StdDdof1(m_window, m_minp);
     }
  };

//==================================================================//
// CV34Sma — pandas .rolling(window, min_periods=window).mean()     //
// via ring buffer + RUNNING sum + NaN counter.  Exact port of the  //
// consolidate_p1c_stepper._CoinState inline `ma` block (minp ==    //
// window, so ANY NaN in the window -> NaN).                        //
// NOTE: this is the running-sum flavor (subtract old / add new);   //
// crisis-style two-pass means live on CV34Ring::Mean instead —     //
// pick the flavor your source stepper used.                        //
//==================================================================//
class CV34Sma
  {
public:
   // --- serializable state ---
   int               m_window;
   double            m_buf[];
   int               m_head;
   int               m_filled;
   double            m_sum;
   int               m_nan_ct;

                     CV34Sma() { m_window = 0; m_head = 0; m_filled = 0; m_sum = 0.0; m_nan_ct = 0; }

   void              Init(const int window)
     {
      m_window = window;
      ArrayResize(m_buf, window);
      double nan = V34Nan();
      for(int i = 0; i < window; i++)
         m_buf[i] = nan;
      m_head   = 0;
      m_filled = 0;
      m_sum    = 0.0;
      m_nan_ct = 0;
     }

   // push one value (NaN allowed); returns mean or NaN (verbatim port)
   double            Step(const double x)
     {
      int j = m_head;
      if(m_filled == m_window)
        {
         double old = m_buf[j];
         if(old != old)
            m_nan_ct--;
         else
            m_sum -= old;
        }
      m_buf[j] = x;
      m_head = (j + 1) % m_window;
      if(m_filled < m_window)
         m_filled++;
      if(x != x)
         m_nan_ct++;
      else
         m_sum += x;
      if(m_filled == m_window && m_nan_ct == 0)
         return m_sum / m_window;
      return V34Nan();
     }
  };

//==================================================================//
// CV34Donchian — rolling(w).max()/min().shift(1), min_periods=w.   //
// Exact port of carry_breakout_stepper._RollExtreme: monotonic     //
// deque of (push_idx, value); per bar call Query() FIRST (window = //
// pushes [n_pushed-w, n_pushed-1], i.e. the PRIOR window / shift-1 //
// read), THEN Push(val).  NaNs are skipped on push but still       //
// advance n_pushed (leading-NaN / ffilled-close contract).         //
//==================================================================//
class CV34Donchian
  {
public:
   // --- serializable state ---
   int               m_w;
   bool              m_is_max;
   long              m_dq_idx[];   // deque ring: push indices
   double            m_dq_val[];   // deque ring: values
   int               m_dq_start;   // front slot
   int               m_dq_len;
   int               m_cap;        // = m_w + 1 (bounded by front-prune in Push)
   long              m_n_pushed;
   long              m_n_valid;

                     CV34Donchian() { m_w = 0; m_is_max = true; m_dq_start = 0; m_dq_len = 0; m_cap = 0; m_n_pushed = 0; m_n_valid = 0; }

   void              Init(const int w, const bool is_max)
     {
      m_w      = w;
      m_is_max = is_max;
      m_cap    = w + 1;
      ArrayResize(m_dq_idx, m_cap);
      ArrayResize(m_dq_val, m_cap);
      m_dq_start = 0;
      m_dq_len   = 0;
      m_n_pushed = 0;
      m_n_valid  = 0;
     }

   // rolling extreme over pushes [n_pushed - w, n_pushed - 1]
   // (call BEFORE Push on each bar -> shift(1) semantics)
   double            Query()
     {
      if(m_n_valid < m_w || m_n_pushed < m_w)
         return V34Nan();
      long lo = m_n_pushed - m_w;
      while(m_dq_len > 0 && m_dq_idx[m_dq_start] < lo)
        {
         m_dq_start = (m_dq_start + 1) % m_cap;
         m_dq_len--;
        }
      return m_dq_val[m_dq_start];
     }

   void              Push(const double val)
     {
      if(val == val)
        {
         // front-prune entries dead for EVERY future query
         // (idx < (n_pushed+1) - w); keeps deque size <= w. Identical
         // behavior to the Python (which prunes lazily in query()).
         long lo_next = m_n_pushed + 1 - m_w;
         while(m_dq_len > 0 && m_dq_idx[m_dq_start] < lo_next)
           {
            m_dq_start = (m_dq_start + 1) % m_cap;
            m_dq_len--;
           }
         // back-pop dominated entries (monotonic deque)
         if(m_is_max)
           {
            while(m_dq_len > 0)
              {
               int back = (m_dq_start + m_dq_len - 1) % m_cap;
               if(m_dq_val[back] <= val)
                  m_dq_len--;
               else
                  break;
              }
           }
         else
           {
            while(m_dq_len > 0)
              {
               int back = (m_dq_start + m_dq_len - 1) % m_cap;
               if(m_dq_val[back] >= val)
                  m_dq_len--;
               else
                  break;
              }
           }
         int slot = (m_dq_start + m_dq_len) % m_cap;
         m_dq_idx[slot] = m_n_pushed;
         m_dq_val[slot] = val;
         m_dq_len++;
         m_n_valid++;
        }
      m_n_pushed++;
     }
  };

//==================================================================//
// tiny CSV helpers for validation harnesses                        //
//==================================================================//

// split a CSV line on ','; returns the field count
int V34CsvSplit(const string line, string &fields[])
  {
   return StringSplit(line, ',', fields);
  }

// parse a numeric token; "", "nan", "NaN", "NAN" -> NaN;
// "inf"/"+inf"/"-inf" handled; otherwise StringToDouble
double V34ParseDouble(const string tok_in)
  {
   string tok = tok_in;
   StringTrimLeft(tok);
   StringTrimRight(tok);
   if(StringLen(tok) == 0)
      return V34Nan();
   string low = tok;
   StringToLower(low);
   if(low == "nan" || low == "+nan" || low == "-nan")
      return V34Nan();
   if(low == "inf" || low == "+inf" || low == "infinity")
      return V34Inf();
   if(low == "-inf" || low == "-infinity")
      return -V34Inf();
   return StringToDouble(tok);
  }

#endif // FMA3V34_V34MATH_MQH
