//+------------------------------------------------------------------+
//| TrendV2.mqh — FMA3 v34 trend_v2 sleeve stepper (CV34TrendV2Stepper)
//|
//| 1:1 MQL5 port of the Wave-1 validated Python stepper
//|   research/bpure/steppers/trend_v2_stepper.py
//| (itself state-exact vs frozen goldens of
//|  model/v3/freeze/FMA3-v34-freeze-1/src/research/sleeves/trend_v2.py).
//| Every constant, branch, guard and NaN rule is preserved verbatim.
//|
//| SLEEVE: 5 commodity symbols, 6-lookback tanh momentum ensemble.
//|   SYMS      = XAUUSD, XAGUSD, XBRUSD, XTIUSD, XNGUSD
//|   LOOKBACKS = 15, 25, 40, 65, 95, 125
//|
//| TIMING CONTRACT (Python docstring, verbatim):
//|   * ONE call to Step() per CALENDAR day of the daily grid (crypto in
//|     the ALL universe trades weekends, so every calendar day exists;
//|     these commodity closes arrive FFILLED-STALE on non-trading days:
//|     weekend rows give dret == 0.0 exactly and DO count as ewm
//|     observations; momentum shift(L) is over CALENDAR-day rows).
//|   * All 5 symbols stepped together, closes in SYMS order, NaN
//|     allowed pre-listing / on missing bars.
//|   * Returned held weights are stamped at day d 00:00 and become
//|     effective d+1 05:00 UTC (to_hourly lag_hours = EXEC_HOUR+1 = 6);
//|     the hourly mapping is the CALLER/EA's job, not this class's.
//|
//| PER-BAR RECURRENCE (one symbol):
//|   dret   = c/c_prev - 1                    (pandas pct_change)
//|   ewm of dret^2, span=20, min_periods=10, adjust=True,
//|          ignore_na=False  -> CV34EwmMean (exact aggregations.pyx
//|          recurrence incl. the `weighted != cur` constant guard)
//|   sig_d  = sqrt(ewm_mean); ann_vol = sig_d*sqrt(252)
//|   z_L    = (c/c[t-L] - 1) / (sig_d*sqrt(L));  leg_L = tanh(z_L/K)
//|   s      = (sum legs)/6
//|   agree  = (1/6)*count(sign(leg)==sign(s))   (NaN compares -> 0)
//|   s     *= agree
//|   s      = sign(s)*max(|s|-S0,0)/(1-S0)      (soft deadband)
//|   max_w  = min(V0/ann_vol, 1); XAGUSD max_w *= 0.5
//|   target = clip(s*max_w, -1, 1)
//|   hysteresis: band = DELTA*(max_w if finite else 1); retrade
//|          (held = target) ONLY when isfinite(target) and
//|          |target - held| > band; else hold.  => a NaN target
//|          (missing bar anywhere in a lookback) NEVER moves held —
//|          no scheduled-target leak on missing bars.
//|
//| PARITY NOTE (measured, carried over from the Python docstring and
//| V34Math header): pandas' compiled ewma kernel contracts
//| old_wt*weighted + cur into an ARM64 fma.  MQL5 has no fma, so the
//| ewm reproduces pandas to ~1e-16 RELATIVE (<=1.2e-15 measured), not
//| bit-exact; MathTanh/MathSqrt are the same libm-class double ops the
//| Python used (np.tanh/np.sqrt).  Every other path is exact by
//| construction.
//|
//| API:
//|   CV34TrendV2Stepper st;               // ctor == Python __init__
//|   st.Step(closes, held);               // closes[5] in SYMS order ->
//|                                        // held[5] (resized), the
//|                                        // Python step() return
//|   diagnostics of the LAST step (Python .last dict, field-for-field):
//|     st.m_last_sig_d[i], m_last_s[i], m_last_max_w[i],
//|     st.m_last_target[i], m_last_moved[i], Held(i)
//|   warm-start (Python get_state()/set_state(), field-for-field —
//|   the JSON string is loads/dumps-compatible with the Python dict):
//|     string js = st.GetState();
//|     bool ok   = st2.SetState(js);
//+------------------------------------------------------------------+
#ifndef FMA3V34_TRENDV2_MQH
#define FMA3V34_TRENDV2_MQH

#include <FMA3v34/V34Math.mqh>

//------------------------------------------------------------------//
// frozen parameters (trend_v2_stepper.py lines 51-75, spec 44-50)   //
//------------------------------------------------------------------//
#define V34TV2_NSYM 5
#define V34TV2_NLB  6

string V34TV2_SYMS[V34TV2_NSYM] =
  {"XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD", "XNGUSD"};
int    V34TV2_LOOKBACKS[V34TV2_NLB] = {15, 25, 40, 65, 95, 125};

#define V34TV2_K         1.0
#define V34TV2_DELTA     0.15
#define V34TV2_S0        0.15
#define V34TV2_VOL_SPAN  20
#define V34TV2_VOL_MINP  10
#define V34TV2_V0        0.085
#define V34TV2_XAG_SHARE 0.5
#define V34TV2_EXEC_HOUR 5      // held effective d+1 05:00 UTC (lag 6h)
#define V34TV2_MAX_L     125
#define V34TV2_XAG_IDX   1      // SYMS[1] == "XAGUSD"

//------------------------------------------------------------------//
// np.tanh semantics: NaN->NaN, +-inf->+-1, else libm tanh.          //
// (explicit guards so MQL5's MathTanh corner behavior is irrelevant)//
//------------------------------------------------------------------//
double V34TV2Tanh(const double z)
  {
   if(z != z)
      return V34Nan();
   double inf = V34Inf();
   if(z == inf)
      return 1.0;
   if(z == -inf)
      return -1.0;
   return MathTanh(z);
  }

//------------------------------------------------------------------//
// JSON number token, round-trip precision; NaN/Infinity tokens match//
// python json.dumps (non-strict) so the state string is loads-able. //
//------------------------------------------------------------------//
string V34TV2Num(const double x)
  {
   if(x != x)
      return "NaN";
   if(!V34IsFinite(x))
      return (x > 0.0) ? "Infinity" : "-Infinity";
   return StringFormat("%.17g", x);
  }

//------------------------------------------------------------------//
// minimal fixed-schema JSON helpers for GetState/SetState           //
//------------------------------------------------------------------//

// position just after the ':' of "key": ...   (-1 if absent)
int V34TV2JsonValuePos(const string js, const string key)
  {
   int p = StringFind(js, "\"" + key + "\"");
   if(p < 0)
      return -1;
   p = StringFind(js, ":", p);
   if(p < 0)
      return -1;
   return p + 1;
  }

// parse the FLAT array starting at the first '[' at/after pos;
// fills vals[] (resized), returns count, -1 on malformed input.
// on return, pos is advanced past the closing ']'.
int V34TV2JsonFlatArray(const string js, int &pos, double &vals[])
  {
   int lb = StringFind(js, "[", pos);
   if(lb < 0)
      return -1;
   int rb = StringFind(js, "]", lb);
   if(rb < 0)
      return -1;
   pos = rb + 1;
   string body = StringSubstr(js, lb + 1, rb - lb - 1);
   StringTrimLeft(body);
   StringTrimRight(body);
   if(StringLen(body) == 0)
     {
      ArrayResize(vals, 0);
      return 0;
     }
   string toks[];
   int n = StringSplit(body, ',', toks);
   ArrayResize(vals, n);
   for(int i = 0; i < n; i++)
      vals[i] = V34ParseDouble(toks[i]);   // handles NaN/Infinity tokens
   return n;
  }

// scalar number (int-valued fields parse through double exactly)
double V34TV2JsonNumber(const string js, const string key, bool &ok)
  {
   int p = V34TV2JsonValuePos(js, key);
   if(p < 0)
     {
      ok = false;
      return V34Nan();
     }
   // token runs until , } ]
   int e = p;
   int len = StringLen(js);
   while(e < len)
     {
      ushort ch = StringGetCharacter(js, e);
      if(ch == ',' || ch == '}' || ch == ']')
         break;
      e++;
     }
   ok = true;
   return V34ParseDouble(StringSubstr(js, p, e - p));
  }

//==================================================================//
// CV34TrendV2Stepper — steps ALL 5 symbols together, one calendar- //
// day close row per call.  Exact port of TrendV2Stepper.           //
//==================================================================//
class CV34TrendV2Stepper
  {
public:
   // --- serializable state (mirrors the Python state dict) ----------
   // hist: price ring per symbol, capacity 125, newest last;
   //       ring.TrimmedAt(count, count-L) == Python hist[-L]
   CV34Ring          m_hist[V34TV2_NSYM];
   // pandas-exact ewma of dret^2 per symbol (span=20, minp=10);
   // CV34EwmMean fields m_avg/m_old_wt/m_nobs == Python
   // ewm_weighted/ewm_old_wt/ewm_nobs
   CV34EwmMean       m_ewm[V34TV2_NSYM];
   double            m_held[V34TV2_NSYM];
   long              m_n_rows;

   // --- last-step intermediates (Python .last, diagnostics/parity) --
   double            m_last_sig_d[V34TV2_NSYM];
   double            m_last_s[V34TV2_NSYM];
   double            m_last_max_w[V34TV2_NSYM];
   double            m_last_target[V34TV2_NSYM];
   bool              m_last_moved[V34TV2_NSYM];

                     CV34TrendV2Stepper() { Reset(); }

   //---------------------------------------------------------------//
   void              Reset()
     {
      double nan = V34Nan();
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         m_hist[i].Init(V34TV2_MAX_L);
         m_ewm[i].Init((double)V34TV2_VOL_SPAN, V34TV2_VOL_MINP);
         m_held[i]        = 0.0;
         m_last_sig_d[i]  = nan;
         m_last_s[i]      = nan;
         m_last_max_w[i]  = nan;
         m_last_target[i] = nan;
         m_last_moved[i]  = false;
        }
      m_n_rows = 0;
     }

   int               NSymbols() const { return V34TV2_NSYM; }
   string            SymbolName(const int i) const { return V34TV2_SYMS[i]; }
   double            Held(const int i) const { return m_held[i]; }
   long              NRows() const { return m_n_rows; }

   //---------------------------------------------------------------//
   // Python hist[-k] (k=1 -> previous close).  Caller checks count. //
   //---------------------------------------------------------------//
   double            HistBack(const int i, const int k) const
     {
      int cnt = m_hist[i].Count();
      return m_hist[i].TrimmedAt(cnt, cnt - k);
     }

   //---------------------------------------------------------------//
   // Step — one daily-grid close row (closes[5], SYMS order, NaN    //
   // allowed).  Fills held_out[5] (resized) with the held weight per//
   // symbol (fraction of sleeve equity), stamped at this day d 00:00,//
   // effective d+1 05:00 UTC.  Verbatim port of Python step().      //
   //---------------------------------------------------------------//
   void              Step(const double &closes[], double &held_out[])
     {
      double nan = V34Nan();
      double sqrt252 = MathSqrt(252.0);        // == np.sqrt(252.0)

      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         double c = closes[i];
         int hist_len = m_hist[i].Count();

         // ---- dret = pct_change: c/prev - 1 -------------------------
         double prev = (hist_len > 0) ? HistBack(i, 1) : nan;
         double dret;
         if(c == c && prev == prev)
            dret = c / prev - 1.0;
         else
            dret = nan;
         double x = dret * dret;   // NaN propagates; npy_pow(a,2)==a*a

         // ---- ewm(span=20, min_periods=10).mean() on dret^2 ---------
         // CV34EwmMean == the pandas aggregations.pyx recurrence the
         // Python inlines (decay every bar once seeded, `avg != cur`
         // constant guard, old_wt += 1 on obs, NaN until nobs >= 10)
         double ewm_mean = m_ewm[i].Step(x);

         double sig = (ewm_mean == ewm_mean) ? MathSqrt(ewm_mean) : nan;
         m_last_sig_d[i] = sig;
         double ann_vol = sig * sqrt252;

         // ---- ensemble of vol-normalized momentum legs --------------
         double legs[V34TV2_NLB];
         for(int j = 0; j < V34TV2_NLB; j++)
           {
            int L = V34TV2_LOOKBACKS[j];
            double p_l = (hist_len >= L) ? HistBack(i, L) : nan;
            double num;
            if(c == c && p_l == p_l)
               num = c / p_l - 1.0;
            else
               num = nan;
            // _ieee_div == V34NpDiv: NaN/inf per IEEE, no fp divide by 0
            double z = V34NpDiv(num, sig * MathSqrt((double)L));
            legs[j] = V34TV2Tanh(z / V34TV2_K);
           }

         double acc = 0.0;
         for(int j = 0; j < V34TV2_NLB; j++)
            acc += legs[j];                    // summation order preserved
         double s = acc / 6.0;

         // consensus gate: fraction of legs agreeing in sign with s
         double sgn_s = V34Sign(s);
         double agree_cnt = 0.0;
         for(int j = 0; j < V34TV2_NLB; j++)
           {
            if(V34Sign(legs[j]) == sgn_s)     // NaN==NaN false -> adds 0
               agree_cnt += 1.0;
           }
         double agree = agree_cnt / 6.0;
         s = s * agree;

         // soft zero-deadband: sign(s)*(|s|-S0).clip(0)/(1-S0)
         double a = MathAbs(s) - V34TV2_S0;   // NaN propagates
         if(a < 0.0)
            a = 0.0;                          // NaN stays NaN (cmp false)
         s = (V34Sign(s) * a) / (1.0 - V34TV2_S0);
         m_last_s[i] = s;

         // ---- inverse-vol sizing with per-instrument cap ------------
         double mw = V34NpDiv(V34TV2_V0, ann_vol); // ann_vol==0 -> inf
         if(mw > 1.0)
            mw = 1.0;                         // clip(upper=1): NaN stays
         if(i == V34TV2_XAG_IDX)              // SYMS[i] == "XAGUSD"
            mw = mw * V34TV2_XAG_SHARE;
         m_last_max_w[i] = mw;

         double tgt = s * mw;
         if(tgt > 1.0)
            tgt = 1.0;
         else if(tgt < -1.0)
            tgt = -1.0;
         m_last_target[i] = tgt;

         // ---- hysteresis --------------------------------------------
         // NO retrade on non-finite target: a missing bar anywhere in
         // the chain NEVER leaks a scheduled target into held.
         double band = V34TV2_DELTA * (V34IsFinite(mw) ? mw : 1.0);
         m_last_moved[i] = false;
         if(V34IsFinite(tgt) && MathAbs(tgt - m_held[i]) > band)
           {
            m_held[i] = tgt;
            m_last_moved[i] = true;
           }

         // ---- roll price history (push AFTER use, incl. NaN) --------
         m_hist[i].Push(c);
        }

      m_n_rows++;
      ArrayResize(held_out, V34TV2_NSYM);
      for(int i = 0; i < V34TV2_NSYM; i++)
         held_out[i] = m_held[i];
     }

   //---------------------------------------------------------------//
   // GetState — JSON string, field-for-field the Python get_state() //
   // dict (json.loads-compatible, incl. NaN tokens).                //
   //---------------------------------------------------------------//
   string            GetState() const
     {
      string js = "{\"name\": \"trend_v2\", \"syms\": [";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            js += ", ";
         js += "\"" + V34TV2_SYMS[i] + "\"";
        }
      js += "], \"n_rows\": " + StringFormat("%I64d", m_n_rows);
      js += ", \"hist\": [";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            js += ", ";
         js += "[";
         int cnt = m_hist[i].Count();
         for(int k = 0; k < cnt; k++)
           {
            if(k > 0)
               js += ", ";
            js += V34TV2Num(m_hist[i].TrimmedAt(cnt, k));  // oldest->newest
           }
         js += "]";
        }
      js += "], \"ewm_weighted\": [";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            js += ", ";
         js += V34TV2Num(m_ewm[i].m_avg);
        }
      js += "], \"ewm_old_wt\": [";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            js += ", ";
         js += V34TV2Num(m_ewm[i].m_old_wt);
        }
      js += "], \"ewm_nobs\": [";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            js += ", ";
         js += StringFormat("%I64d", m_ewm[i].m_nobs);
        }
      js += "], \"held\": [";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            js += ", ";
         js += V34TV2Num(m_held[i]);
        }
      js += "]}";
      return js;
     }

   //---------------------------------------------------------------//
   // SetState — parse the GetState()/python-json state string.      //
   // Mirrors Python set_state incl. the syms assertion.  Returns    //
   // false (state untouched) on schema mismatch.                    //
   //---------------------------------------------------------------//
   bool              SetState(const string js)
     {
      // name / syms assertions (Python: assert st["syms"] == SYMS)
      if(StringFind(js, "\"trend_v2\"") < 0)
         return false;
      int sp = V34TV2JsonValuePos(js, "syms");
      if(sp < 0)
         return false;
      int slb = StringFind(js, "[", sp);
      int srb = StringFind(js, "]", slb);
      if(slb < 0 || srb < 0)
         return false;
      string sbody = StringSubstr(js, slb + 1, srb - slb - 1);
      StringReplace(sbody, " ", "");
      string want = "";
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         if(i > 0)
            want += ",";
         want += "\"" + V34TV2_SYMS[i] + "\"";
        }
      if(sbody != want)
         return false;

      bool ok = true;
      double n_rows_d = V34TV2JsonNumber(js, "n_rows", ok);
      if(!ok || !(n_rows_d == n_rows_d))
         return false;

      // hist: 5 nested flat arrays inside the outer [ ... ]
      int hp = V34TV2JsonValuePos(js, "hist");
      if(hp < 0)
         return false;
      int outer = StringFind(js, "[", hp);
      if(outer < 0)
         return false;
      int    cursor = outer + 1;
      double hist_vals[V34TV2_NSYM][V34TV2_MAX_L];
      int    hist_cnt[V34TV2_NSYM];
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         double vals[];
         int n = V34TV2JsonFlatArray(js, cursor, vals);
         if(n < 0 || n > V34TV2_MAX_L)
            return false;
         hist_cnt[i] = n;
         for(int k = 0; k < n; k++)
            hist_vals[i][k] = vals[k];
        }

      // flat arrays: ewm_weighted / ewm_old_wt / ewm_nobs / held
      double w[], ow[], nb[], hd[];
      int p;
      p = V34TV2JsonValuePos(js, "ewm_weighted");
      if(p < 0 || V34TV2JsonFlatArray(js, p, w) != V34TV2_NSYM)
         return false;
      p = V34TV2JsonValuePos(js, "ewm_old_wt");
      if(p < 0 || V34TV2JsonFlatArray(js, p, ow) != V34TV2_NSYM)
         return false;
      p = V34TV2JsonValuePos(js, "ewm_nobs");
      if(p < 0 || V34TV2JsonFlatArray(js, p, nb) != V34TV2_NSYM)
         return false;
      p = V34TV2JsonValuePos(js, "held");
      if(p < 0 || V34TV2JsonFlatArray(js, p, hd) != V34TV2_NSYM)
         return false;

      // ---- commit ---------------------------------------------------
      m_n_rows = (long)n_rows_d;
      for(int i = 0; i < V34TV2_NSYM; i++)
        {
         m_hist[i].Init(V34TV2_MAX_L);
         for(int k = 0; k < hist_cnt[i]; k++)
            m_hist[i].Push(hist_vals[i][k]);   // oldest -> newest
         m_ewm[i].Init((double)V34TV2_VOL_SPAN, V34TV2_VOL_MINP);
         m_ewm[i].m_avg    = w[i];
         m_ewm[i].m_old_wt = ow[i];
         m_ewm[i].m_nobs   = (long)nb[i];
         m_held[i]         = hd[i];
        }
      return true;
     }
  };

#endif // FMA3V34_TRENDV2_MQH
