//+------------------------------------------------------------------+
//| Core/CoreSignal.mqh — the LIVE Core per-leg target source        |
//| (CCoreSignal) + the causal band/harvest trigger detector LIVE    |
//| mode (CCoreTrigger).  UNIT 3 of the S2 live-Core build.          |
//|                                                                  |
//| 1:1 STATEMENT PORT of                                            |
//|   research/bpure/coresignal/core_signal_reference.py  (targets)  |
//|   research/bpure/coresignal/trigger_detector.py LIVE mode +      |
//|   S2_CORE_LIVE_DESIGN.md section 4.3           (trigger)         |
//| Owner ratifications (S2_PREP_STATUS, 2026-07-14, binding):       |
//|   1. normative source = NSF5 python target functions at          |
//|      R = 8.0 PURE (NEVER the preset InpRisk=8.96 which embeds    |
//|      w*s).  CoreEngine.mqh is NOT extracted, NOT included.       |
//|   2. trigger: anchor-exact (incl. retrospective bfill) lives in  |
//|      the python harness ONLY; this file carries the LIVE mode:   |
//|      causal hold-at-legcap + telemetry.                          |
//|   3. pass criterion when kernels are not bit-zero: ZERO          |
//|      lot-decision flips + <= 1e-12 on targets.                   |
//|                                                                  |
//| WHAT THIS FILE IS NOT: CoreEngine.mqh (the live real-account     |
//| tracker, G1-proven, untouched).  Zero CTrade, zero trading       |
//| calls, zero Inp* reads, zero terminal-account calls, zero        |
//| file-scope mutable globals — pure compute.                       |
//|                                                                  |
//| KERNELS (pandas-3.0.1 aggregations.pyx statement mirrors, the    |
//| P1c discipline — NOT the SatMath two-pass/running-sum flavors):  |
//|   CCsRollMean  roll_mean : Kahan running sum, separate add/rem   |
//|                compensations, neg_ct / num_consecutive_same_value|
//|                guards, minp = window;                            |
//|   CCsRollStd   roll_var  : Welford + Kahan, InvCondTol =         |
//|                eps*1e3 unstable-window recompute, ddof = 1,      |
//|                pandas zsqrt (negative variance -> 0);            |
//|   CSatDonchian (REUSED from Sat/SatMath.mqh): monotonic deque    |
//|                rolling max/min with Query-before-Push = shift(1) |
//|                — exactly the reference RollMax/RollMin .last.    |
//|                                                                  |
//| FMA NOTE (measured, core_signal_reference docstring): the        |
//| shipped pandas 3.0.1 wheel contracts roll_var's                  |
//| `ssqdm + (val-prev_mean)*(val-mean)` into ONE fma (clang         |
//| -ffp-contract=on).  MQL5 exposes no fma intrinsic; a plain       |
//| two-rounding update was MEASURED to breach the ratified 1e-12    |
//| line on leg 3 (EURGBP max|d| 1.069e-12, mirror run 2026-07-15),  |
//| so this port EMULATES the fma exactly via Dekker/TwoProduct      |
//| (CsFmaEmul below) — measured bit-equal to math.fma on every      |
//| realized kernel update by mql5_coresignal_mirror.py, and gated   |
//| in-terminal by TestCoreSignal.mq5 (G-S5).                        |
//| MATHPOW NOTE: leg 8 BTC ann = MathPow(m/d63, 365/63) - 1 feeds   |
//| only the boolean `ann > 0.40`; MathPow is not correctly rounded  |
//| so the mirror measures min|ann-hurdle| (flip-distance telemetry).|
//|                                                                  |
//| STAMP LAW: all hour/dow gates are RAW server-stamp fields        |
//| (NO ToUtc); daily mid = (bid_c+ask_c)/2 of the LAST bar of each  |
//| raw-stamp day, finalized at the first bar of the next bar-day;   |
//| EURGBP daily entry = last raw-hour<20 bar, signal effective at   |
//| day+20:00 with shift(1); defer_reopen holds raw hours {21,22}.   |
//|                                                                  |
//| STATE: GetState/SetState JSON, field-for-field with the python   |
//| mirror steppers, every double %.17g (NaN/Infinity python-json    |
//| tokens) — BookState-compatible.  Includes the two formally       |
//| unbounded Donchian breach flags (b50/b100) explicitly.           |
//+------------------------------------------------------------------+
#ifndef CORE_CORESIGNAL_MQH
#define CORE_CORESIGNAL_MQH

#include <Sat/SatMath.mqh>   // SatNan/SatInf/SatSignBit/SatParseDouble/CSatDonchian

#define CS_RISK        8.0   // owner ratification 1: R = 8.0 PURE
#define CS_I_XAUUSD    0     // instrument feed ids (8 daily-mid series)
#define CS_I_USDJPY    1
#define CS_I_ETHUSD    2
#define CS_I_EURGBP    3
#define CS_I_USTEC     4
#define CS_I_AUDUSD    5
#define CS_I_NZDUSD    6
#define CS_I_BTCUSD    7
#define CS_NINST       8
#define CS_NLEGS       9

// leg -> instrument feed (LEG TABLE, book append order):
//   0 BOOK_XAU/XAUUSD  1 S5_JPY/USDJPY  2 S1_ETH/ETHUSD  3 ZC_EG/EURGBP
//   4 BOOK_USTEC/USTEC 5 S6/USDJPY      6 S6/AUDUSD      7 S6/NZDUSD
//   8 BTC_REP/BTCUSD
int CsLegInst(const int leg)
  {
   switch(leg)
     {
      case 0: return CS_I_XAUUSD;
      case 1: return CS_I_USDJPY;
      case 2: return CS_I_ETHUSD;
      case 3: return CS_I_EURGBP;
      case 4: return CS_I_USTEC;
      case 5: return CS_I_USDJPY;
      case 6: return CS_I_AUDUSD;
      case 7: return CS_I_NZDUSD;
      case 8: return CS_I_BTCUSD;
     }
   return -1;
  }

//==================================================================//
// raw-stamp fields (core_signal_reference._fields, scalar):        //
//   eday = es // 86400; hour = (es % 86400) // 3600;               //
//   dow  = (eday + 3) % 7   (epoch day 0 = Thu; Mon = 0)           //
//==================================================================//
void CsFields(const long ts, long &d, int &h, int &dw)
  {
   d  = ts / 86400;
   h  = (int)((ts % 86400) / 3600);
   dw = (int)((d + 3) % 7);
  }

//------------------------------------------------------------------//
// clip2 (pandas Series.clip scalar): NaN passes through            //
//------------------------------------------------------------------//
double CsClip(const double x, const double lo, const double hi)
  {
   if(x < lo) return lo;
   if(x > hi) return hi;
   return x;
  }

// clip2(x, -inf, hi) == Series.clip(upper=hi): x < -inf never true
double CsClipHi(const double x, const double hi)
  {
   if(x > hi) return hi;
   return x;
  }

//------------------------------------------------------------------//
// JSON number token (BookState convention: %.17g, python-json      //
// non-strict NaN/Infinity/-Infinity)                               //
//------------------------------------------------------------------//
string CsJNum(const double x)
  {
   if(x != x) return "NaN";
   double inf = SatInf();
   if(x == inf)  return "Infinity";
   if(x == -inf) return "-Infinity";
   return StringFormat("%.17g", x);
  }

//------------------------------------------------------------------//
// CsFmaEmul — software fma(a, b, c) = round(a*b + c) via Dekker    //
// splitting + Knuth TwoSum (no fma intrinsic in MQL5):             //
//   a*b     = p + e   EXACTLY (Veltkamp split, 2^27+1 constant);   //
//   c + p   = s + err EXACTLY (TwoSum);                            //
//   result  = s + (err + e)  — one rounded combine.                //
// The `err + e` combine can theoretically double-round a sub-ulp   //
// tie; MEASURED bit-equal to hardware fma on every realized kernel //
// update of this book (mirror gate M-1).  Requires no overflow in  //
// the split (|a|,|b| < ~1e300 — prices/returns, trivially true).   //
//------------------------------------------------------------------//
double CsFmaEmul(const double a, const double b, const double c)
  {
   double p  = a * b;
   double sa = 134217729.0 * a;          // 2^27 + 1
   double ah = sa - (sa - a);
   double al = a - ah;
   double sb = 134217729.0 * b;
   double bh = sb - (sb - b);
   double bl = b - bh;
   double e  = ((ah * bh - p) + ah * bl + al * bh) + al * bl;  // exact prod err
   double s  = c + p;
   double bv = s - c;
   double err = (c - (s - bv)) + (p - bv);                     // exact sum err
   double t  = err + e;
   return s + t;
  }

//==================================================================//
// CCsTok — strict-order state parser (GetState emits a fixed       //
// field order, so SetState literal-matches keys and reads tokens). //
//==================================================================//
class CCsTok
  {
public:
   string            m_s;
   int               m_pos;
   bool              m_ok;
   string            m_err;

   void              Init(const string s) { m_s = s; m_pos = 0; m_ok = true; m_err = ""; }

   bool              Lit(const string t)
     {
      if(!m_ok) return false;
      int n = StringLen(t);
      if(StringSubstr(m_s, m_pos, n) == t) { m_pos += n; return true; }
      m_ok  = false;
      m_err = "expected '" + t + "' at pos " + IntegerToString(m_pos);
      return false;
     }

   // token up to the next ',' / ']' / '}' (not consumed)
   string            Tok(void)
     {
      int n = StringLen(m_s);
      int i = m_pos;
      while(i < n)
        {
         ushort c = StringGetCharacter(m_s, i);
         if(c == ',' || c == ']' || c == '}') break;
         i++;
        }
      string t = StringSubstr(m_s, m_pos, i - m_pos);
      m_pos = i;
      return t;
     }

   double            Num(void)  { return SatParseDouble(Tok()); }
   long              Int(void)  { return StringToInteger(Tok()); }
   bool              Flag(void) { return Int() != 0; }

   bool              PeekIs(const ushort c)
     {
      return (m_pos < StringLen(m_s) &&
              StringGetCharacter(m_s, m_pos) == c);
     }
  };

//==================================================================//
// CCsRollMean — pandas 3.0.1 roll_mean statement mirror            //
// (rolling(w).mean(), minp = window).  Kahan running sum with      //
// SEPARATE add/remove compensations; neg_ct and                    //
// num_consecutive_same_value output guards.                        //
//==================================================================//
class CCsRollMean
  {
public:
   // --- serializable state (public: steppers round-trip it) ---
   int               m_w;
   double            m_buf[];      // ring of the last w values
   int               m_head;       // oldest slot (valid when m_cnt == m_w)
   int               m_cnt;
   long              m_i;
   long              m_nobs;
   double            m_sum_x;
   long              m_neg_ct;
   double            m_comp_add;
   double            m_comp_rem;
   double            m_prev_value;
   long              m_num_consec;

   void              Init(const int w)
     {
      m_w = w;
      ArrayResize(m_buf, w);
      m_head = 0; m_cnt = 0; m_i = 0;
      m_nobs = 0; m_sum_x = 0.0; m_neg_ct = 0;
      m_comp_add = 0.0; m_comp_rem = 0.0;
      m_prev_value = SatNan(); m_num_consec = 0;
     }

private:
   void              AddVal(const double val)
     {
      if(val == val)
        {
         m_nobs++;
         double y = val - m_comp_add;
         double t = m_sum_x + y;
         m_comp_add = t - m_sum_x - y;
         m_sum_x = t;
         if(SatSignBit(val))
            m_neg_ct++;
         if(val == m_prev_value)
            m_num_consec++;
         else
            m_num_consec = 1;
         m_prev_value = val;
        }
     }

   void              RemoveVal(const double val)
     {
      if(val == val)
        {
         m_nobs--;
         double y = -val - m_comp_rem;
         double t = m_sum_x + y;
         m_comp_rem = t - m_sum_x - y;
         m_sum_x = t;
         if(SatSignBit(val))
            m_neg_ct--;
        }
     }

   void              Push(const double v)
     {
      if(m_cnt < m_w) { m_buf[(m_head + m_cnt) % m_w] = v; m_cnt++; }
      else            { m_buf[m_head] = v; m_head = (m_head + 1) % m_w; }
     }

public:
   double            Step(const double val)
     {
      if(m_i == 0)
        {
         m_prev_value = val;          // pandas setup: prev_value = values[s]
         m_num_consec = 0;
         m_sum_x = 0.0; m_comp_add = 0.0; m_comp_rem = 0.0;
         m_nobs = 0; m_neg_ct = 0;
         AddVal(val);
        }
      else
        {
         if(m_i >= m_w)
            RemoveVal(m_buf[m_head]); // ring[0] = oldest of the prior window
         AddVal(val);
        }
      Push(val);
      m_i++;
      // calc_mean
      if(m_nobs >= m_w && m_nobs > 0)
        {
         double result = m_sum_x / (double)m_nobs;
         if(m_num_consec >= m_nobs)
            result = m_prev_value;
         else if(m_neg_ct == 0 && result < 0.0)
            result = 0.0;
         else if(m_neg_ct == m_nobs && result > 0.0)
            result = 0.0;
         return result;
        }
      return SatNan();
     }

   string            StateJson(void) const
     {
      string s = "{\"w\": " + IntegerToString(m_w);
      s += ", \"i\": "    + IntegerToString(m_i);
      s += ", \"nobs\": " + IntegerToString(m_nobs);
      s += ", \"sum_x\": " + CsJNum(m_sum_x);
      s += ", \"neg_ct\": " + IntegerToString(m_neg_ct);
      s += ", \"comp_add\": " + CsJNum(m_comp_add);
      s += ", \"comp_rem\": " + CsJNum(m_comp_rem);
      s += ", \"prev_value\": " + CsJNum(m_prev_value);
      s += ", \"num_consec\": " + IntegerToString(m_num_consec);
      s += ", \"ring\": [";
      for(int j = 0; j < m_cnt; j++)
         s += (j > 0 ? ", " : "") + CsJNum(m_buf[(m_head + j) % m_w]);
      s += "]}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"w\": ")) return false;
      if(p.Int() != m_w) { p.m_ok = false; p.m_err = "rollmean w mismatch"; return false; }
      if(!p.Lit(", \"i\": ")) return false;
      m_i = p.Int();
      if(!p.Lit(", \"nobs\": ")) return false;
      m_nobs = p.Int();
      if(!p.Lit(", \"sum_x\": ")) return false;
      m_sum_x = p.Num();
      if(!p.Lit(", \"neg_ct\": ")) return false;
      m_neg_ct = p.Int();
      if(!p.Lit(", \"comp_add\": ")) return false;
      m_comp_add = p.Num();
      if(!p.Lit(", \"comp_rem\": ")) return false;
      m_comp_rem = p.Num();
      if(!p.Lit(", \"prev_value\": ")) return false;
      m_prev_value = p.Num();
      if(!p.Lit(", \"num_consec\": ")) return false;
      m_num_consec = p.Int();
      if(!p.Lit(", \"ring\": [")) return false;
      m_head = 0; m_cnt = 0;
      while(!p.PeekIs(']'))
        {
         if(m_cnt > 0 && !p.Lit(", ")) return false;
         if(m_cnt >= m_w) { p.m_ok = false; p.m_err = "rollmean ring overflow"; return false; }
         m_buf[m_cnt] = p.Num();
         m_cnt++;
        }
      if(!p.Lit("]}")) return false;
      return p.m_ok;
     }
  };

//==================================================================//
// CCsRollStd — pandas 3.0.1 roll_var statement mirror + zsqrt      //
// (rolling(w).std(), ddof=1, minp=window).  Welford + Kahan        //
// compensation, InvCondTol = eps*1e3 unstable-window recompute.    //
// NO-FMA: ssqdm updates in two roundings (see file header).        //
//==================================================================//
class CCsRollStd
  {
public:
   // --- serializable state ---
   int               m_w;
   double            m_ddof;
   double            m_buf[];
   int               m_head;
   int               m_cnt;
   long              m_i;
   double            m_nobs;      // float in the pyx kernel
   double            m_mean;
   double            m_ssqdm;
   double            m_comp_add;
   double            m_comp_rem;
   bool              m_unstable;
   double            m_invtol;    // eps*1e3 (pandas 3.0.1 InvCondTol)

   void              Init(const int w)
     {
      m_w = w;
      m_ddof = 1.0;
      ArrayResize(m_buf, w);
      m_head = 0; m_cnt = 0; m_i = 0;
      m_nobs = 0.0; m_mean = 0.0; m_ssqdm = 0.0;
      m_comp_add = 0.0; m_comp_rem = 0.0;
      m_unstable = false;
      m_invtol = DBL_EPSILON * 1e3;
     }

private:
   void              AddVal(const double val)
     {
      if(val != val)
         return;
      double prev_m2 = m_ssqdm;
      m_nobs = m_nobs + 1.0;
      double prev_mean = m_mean - m_comp_add;
      double y = val - m_comp_add;
      double t = y - m_mean;
      m_comp_add = t + m_mean - y;
      double delta = t;
      if(m_nobs != 0.0)
         m_mean = m_mean + delta / m_nobs;
      else
         m_mean = 0.0;
      // pandas wheel fuses this into one fma — emulated exactly
      m_ssqdm = CsFmaEmul(val - prev_mean, val - m_mean, m_ssqdm);
      if(prev_m2 * m_invtol > m_ssqdm)
         m_unstable = true;
     }

   void              RemoveVal(const double val)
     {
      if(val == val)
        {
         double prev_m2 = m_ssqdm;
         m_nobs = m_nobs - 1.0;
         if(m_nobs != 0.0)
           {
            double prev_mean = m_mean - m_comp_rem;
            double y = val - m_comp_rem;
            double t = y - m_mean;
            m_comp_rem = t + m_mean - y;
            double delta = t;
            m_mean = m_mean - delta / m_nobs;
            // python: fma(-(val-prev_mean), val-mean, ssqdm) — emulated
            m_ssqdm = CsFmaEmul(-(val - prev_mean), val - m_mean, m_ssqdm);
            if(prev_m2 * m_invtol > m_ssqdm)
               m_unstable = true;
           }
         else
           {
            m_mean = 0.0;
            m_ssqdm = 0.0;
            m_unstable = false;
           }
        }
     }

   void              Push(const double v)
     {
      if(m_cnt < m_w) { m_buf[(m_head + m_cnt) % m_w] = v; m_cnt++; }
      else            { m_buf[m_head] = v; m_head = (m_head + 1) % m_w; }
     }

public:
   double            Step(const double val)
     {
      bool recompute = (m_i == 0);
      if(!recompute)
        {
         if(m_i >= m_w)
            RemoveVal(m_buf[m_head]);
         AddVal(val);
        }
      Push(val);
      if(recompute || m_unstable)
        {
         m_nobs = 0.0; m_mean = 0.0; m_ssqdm = 0.0;
         m_comp_add = 0.0; m_comp_rem = 0.0;
         for(int j = 0; j < m_cnt; j++)
            AddVal(m_buf[(m_head + j) % m_w]);   // oldest -> newest
         m_unstable = false;
        }
      m_i++;
      // calc_var (minp = max(w,1)) + zsqrt
      double var;
      if(m_nobs >= (double)m_w && m_nobs > m_ddof)
         var = m_ssqdm / (m_nobs - m_ddof);
      else
         return SatNan();
      if(var < 0.0)
         return 0.0;
      return MathSqrt(var);
     }

   string            StateJson(void) const
     {
      string s = "{\"w\": " + IntegerToString(m_w);
      s += ", \"i\": "     + IntegerToString(m_i);
      s += ", \"nobs\": "  + CsJNum(m_nobs);
      s += ", \"mean\": "  + CsJNum(m_mean);
      s += ", \"ssqdm\": " + CsJNum(m_ssqdm);
      s += ", \"comp_add\": " + CsJNum(m_comp_add);
      s += ", \"comp_rem\": " + CsJNum(m_comp_rem);
      s += ", \"unstable\": " + (m_unstable ? "1" : "0");
      s += ", \"ring\": [";
      for(int j = 0; j < m_cnt; j++)
         s += (j > 0 ? ", " : "") + CsJNum(m_buf[(m_head + j) % m_w]);
      s += "]}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"w\": ")) return false;
      if(p.Int() != m_w) { p.m_ok = false; p.m_err = "rollstd w mismatch"; return false; }
      if(!p.Lit(", \"i\": ")) return false;
      m_i = p.Int();
      if(!p.Lit(", \"nobs\": ")) return false;
      m_nobs = p.Num();
      if(!p.Lit(", \"mean\": ")) return false;
      m_mean = p.Num();
      if(!p.Lit(", \"ssqdm\": ")) return false;
      m_ssqdm = p.Num();
      if(!p.Lit(", \"comp_add\": ")) return false;
      m_comp_add = p.Num();
      if(!p.Lit(", \"comp_rem\": ")) return false;
      m_comp_rem = p.Num();
      if(!p.Lit(", \"unstable\": ")) return false;
      m_unstable = p.Flag();
      if(!p.Lit(", \"ring\": [")) return false;
      m_head = 0; m_cnt = 0;
      while(!p.PeekIs(']'))
        {
         if(m_cnt > 0 && !p.Lit(", ")) return false;
         if(m_cnt >= m_w) { p.m_ok = false; p.m_err = "rollstd ring overflow"; return false; }
         m_buf[m_cnt] = p.Num();
         m_cnt++;
        }
      if(!p.Lit("]}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// CSatDonchian state round-trip helpers (fields are public).       //
// Serialized: n_pushed, n_valid, deque front->back as [idx, val].  //
//------------------------------------------------------------------//
string CsDonJson(const CSatDonchian &don)
  {
   string s = "{\"w\": " + IntegerToString(don.m_w);
   s += ", \"is_max\": " + (don.m_is_max ? "1" : "0");
   s += ", \"n_pushed\": " + IntegerToString(don.m_n_pushed);
   s += ", \"n_valid\": "  + IntegerToString(don.m_n_valid);
   s += ", \"dq\": [";
   for(int j = 0; j < don.m_dq_len; j++)
     {
      int slot = (don.m_dq_start + j) % don.m_cap;
      s += (j > 0 ? ", " : "") + "[" + IntegerToString(don.m_dq_idx[slot])
           + ", " + CsJNum(don.m_dq_val[slot]) + "]";
     }
   s += "]}";
   return s;
  }

bool CsDonParse(CSatDonchian &don, CCsTok &p)
  {
   if(!p.Lit("{\"w\": ")) return false;
   if(p.Int() != don.m_w) { p.m_ok = false; p.m_err = "donchian w mismatch"; return false; }
   if(!p.Lit(", \"is_max\": ")) return false;
   bool is_max = (p.Int() != 0);
   if(is_max != don.m_is_max) { p.m_ok = false; p.m_err = "donchian is_max mismatch"; return false; }
   if(!p.Lit(", \"n_pushed\": ")) return false;
   don.m_n_pushed = p.Int();
   if(!p.Lit(", \"n_valid\": ")) return false;
   don.m_n_valid = p.Int();
   if(!p.Lit(", \"dq\": [")) return false;
   don.m_dq_start = 0;
   don.m_dq_len = 0;
   while(!p.PeekIs(']'))
     {
      if(don.m_dq_len > 0 && !p.Lit(", ")) return false;
      if(!p.Lit("[")) return false;
      if(don.m_dq_len >= don.m_cap) { p.m_ok = false; p.m_err = "donchian dq overflow"; return false; }
      don.m_dq_idx[don.m_dq_len] = p.Int();
      if(!p.Lit(", ")) return false;
      don.m_dq_val[don.m_dq_len] = p.Num();
      if(!p.Lit("]")) return false;
      don.m_dq_len++;
     }
   if(!p.Lit("]}")) return false;
   return p.m_ok;
  }

//==================================================================//
// CCsOpexCal — v5_sleeves._nth_friday_week(2) deterministic        //
// calendar: Mon..Fri epoch days of every month's 3rd-Friday week.  //
//                                                                  //
// HORIZON-FREE (2026-07-16). This was a PRECOMPUTED TABLE bounded  //
// at 2026-02, inherited verbatim from the parent's study window    //
// (v5_sleeves._nth_friday_week ranges "2019-12-01".."2026-02-01"). //
// Because In() is a SET-MEMBERSHIP test, every date past the last  //
// row answered false forever — so the live Core S6 opex legs       //
// (USDJPY/AUDUSD/NZDUSD) would have gone permanently flat from     //
// 2026-02-21 with no error, no NaN and no refuse, silently         //
// contaminating the demo's OOS measurement (DEMO_GO_NOGO #1).      //
//                                                                  //
// The 3rd-Friday week is computable from any date, so the horizon  //
// is now GONE rather than merely pushed out: a further-out table    //
// would preserve the failure, just re-dated. The LOWER bound is    //
// kept exactly, so in-window behaviour is bit-identical (verified  //
// 0 divergences over 2015-01-01..2026-02-28; matches the real 3rd- //
// Friday weeks with no cross-month spill through 2045).            //
//==================================================================//
long CsDaysFromCivil(const int y_in, const int m_in, const int d_in)
  {
   // Howard Hinnant days_from_civil (proleptic Gregorian)
   int y = y_in;
   if(m_in <= 2) y--;
   int era = (y >= 0 ? y : y - 399) / 400;
   int yoe = y - era * 400;                                   // [0, 399]
   int doy = (153 * (m_in + (m_in > 2 ? -3 : 9)) + 2) / 5 + d_in - 1;
   int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
   return (long)era * 146097 + doe - 719468;
  }

void CsCivilFromDays(const long z_in, int &y_out, int &m_out, int &d_out)
  {
   // Howard Hinnant civil_from_days — exact inverse of CsDaysFromCivil
   long z = z_in + 719468;
   long era = (z >= 0 ? z : z - 146096) / 146097;
   long doe = z - era * 146097;                                  // [0, 146096]
   long yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;  // [0, 399]
   long y   = yoe + era * 400;
   long doy = doe - (365 * yoe + yoe / 4 - yoe / 100);            // [0, 365]
   long mp  = (5 * doy + 2) / 153;                                // [0, 11]
   long d   = doy - (153 * mp + 2) / 5 + 1;                       // [1, 31]
   long m   = mp + (mp < 10 ? 3 : -9);                            // [1, 12]
   y_out = (int)(y + (m <= 2 ? 1 : 0));
   m_out = (int)m;
   d_out = (int)d;
  }

class CCsOpexCal
  {
public:
   void              Init(void) { }   // nothing to build — the rule is computed

   // Is epoch-day `d` inside the Mon..Fri week containing its own month's 3rd
   // Friday? The 3rd Friday is dom 15..21, so its Monday is dom 11..17 — the
   // week never crosses a month boundary, so `d`'s own month is sufficient.
   bool              In(const long d) const
     {
      int y, m, dom;
      CsCivilFromDays(d, y, m, dom);
      // The golden's calendar starts at 2019-12; preserved so that any date
      // before it answers false exactly as the shipped table did.
      if(y < 2019 || (y == 2019 && m < 12)) return false;
      long e1 = CsDaysFromCivil(y, m, 1);
      int  wd = (int)((e1 + 3) % 7);                       // Mon = 0
      long first_fri = e1 + (((4 - wd) % 7) + 7) % 7;      // python (4-wd)%7
      long fr3 = first_fri + 14;                           // 3rd Friday
      long mon = fr3 - 4;                                  // Friday.weekday()==4
      return (d >= mon && d <= mon + 4);
     }

   // Count()/First()/Last() are deliberately gone: they were properties of the
   // precomputed table, and a horizon-free calendar has no last day.
  };

//==================================================================//
// CCsPolicy — NSF5 engine/costs.py POLICY_RATES step tables (USD + //
// JPY, the jpy_smart carry gate's only consumers).  Epoch days     //
// precomputed from the ISO dates (comments), values verbatim.      //
//==================================================================//
class CCsPolicy
  {
public:
   long              m_usd_d[20];
   double            m_usd_r[20];
   long              m_jpy_d[4];
   double            m_jpy_r[4];

   void              Init(void)
     {
      // USD: 2019-11-01 1.625, 2020-03-03 1.125, 2020-03-15 0.125,
      //      2022-03-17 0.375, 2022-05-05 0.875, 2022-06-16 1.625,
      //      2022-07-28 2.375, 2022-09-22 3.125, 2022-11-03 3.875,
      //      2022-12-15 4.375, 2023-02-02 4.625, 2023-03-23 4.875,
      //      2023-05-04 5.125, 2023-07-27 5.375, 2024-09-19 4.875,
      //      2024-11-08 4.625, 2024-12-19 4.375, 2025-09-18 4.125,
      //      2025-10-30 3.875, 2025-12-11 3.625
      long   ud[20] = {18201, 18324, 18336, 19068, 19117, 19159, 19201,
                       19257, 19299, 19341, 19390, 19439, 19481, 19565,
                       19985, 20035, 20076, 20349, 20391, 20433};
      double ur[20] = {1.625, 1.125, 0.125, 0.375, 0.875, 1.625, 2.375,
                       3.125, 3.875, 4.375, 4.625, 4.875, 5.125, 5.375,
                       4.875, 4.625, 4.375, 4.125, 3.875, 3.625};
      // JPY: 2019-11-01 -0.10, 2024-03-19 0.10, 2024-07-31 0.25,
      //      2025-01-24 0.50
      long   jd[4] = {18201, 19801, 19935, 20112};
      double jr[4] = {-0.10, 0.10, 0.25, 0.50};
      for(int i = 0; i < 20; i++) { m_usd_d[i] = ud[i]; m_usd_r[i] = ur[i]; }
      for(int i = 0; i < 4;  i++) { m_jpy_d[i] = jd[i]; m_jpy_r[i] = jr[i]; }
     }

   // costs.policy_rate: last table rate with date <= eday
   double            RateUsd(const long eday) const
     {
      double rate = m_usd_r[0];
      for(int i = 0; i < 20; i++)
        {
         if(m_usd_d[i] <= eday) rate = m_usd_r[i];
         else break;
        }
      return rate;
     }

   double            RateJpy(const long eday) const
     {
      double rate = m_jpy_r[0];
      for(int i = 0; i < 4; i++)
        {
         if(m_jpy_d[i] <= eday) rate = m_jpy_r[i];
         else break;
        }
      return rate;
     }
  };

//==================================================================//
// Leg steppers — streaming twins of the core_signal_reference      //
// gen_* array loops.  Daily finalize uses the STORED previous      //
// bar's (bid_c, ask_c) — the reference's bid_c[i-1]/ask_c[i-1] at  //
// the first bar of the new raw-stamp day.                          //
//==================================================================//

//------------------------------------------------------------------//
// Leg 0 BOOK_XAU / XAUUSD — gen_xau: gold_donch(50)+gold_donch(100)//
// + xau_night_va, defer_reopen.                                    //
//------------------------------------------------------------------//
class CCsLegXau
  {
public:
   // kernels
   CCsRollStd        m_vol;                        // RollStd(20) on returns
   CSatDonchian      m_mx50, m_mn50, m_mx100, m_mn100;
   // gen_xau loop state
   double            m_b50, m_b100;                // breach state (unbounded Class-S)
   double            m_prev_mid;
   double            m_s50_P, m_s100_P, m_vol_P;
   double            m_eff50, m_eff100, m_effN;    // NaN-carried daily coefficients
   double            m_held;
   bool              m_has_held;
   long              m_cur;
   bool              m_started;
   double            m_pb, m_pa;                   // previous bar bid_c/ask_c
   double            m_out;
   // params
   double            m_vt_gd, m_cap_gd, m_vt_gn, m_cap_gn, m_c_gd, m_c_gn;
   double            m_sqrt252;

   void              Configure(void)
     {
      double s_g = (0.55 * CS_RISK) / 0.55;
      m_vt_gd = 0.125 * s_g;   m_cap_gd = 6.0;
      m_vt_gn = 0.30 * s_g;    m_cap_gn = 6.0;
      m_c_gd = 0.17 / 0.36;    m_c_gn = 0.19 / 0.36;
      m_sqrt252 = MathSqrt(252.0);
      m_vol.Init(20);
      m_mx50.Init(50, true);   m_mn50.Init(50, false);
      m_mx100.Init(100, true); m_mn100.Init(100, false);
      m_b50 = 0.0; m_b100 = 0.0;
      m_prev_mid = SatNan();
      m_s50_P = SatNan(); m_s100_P = SatNan(); m_vol_P = SatNan();
      m_eff50 = 0.0; m_eff100 = 0.0; m_effN = 0.0;
      m_held = 0.0; m_has_held = false;
      m_cur = 0; m_started = false;
      m_pb = 0.0; m_pa = 0.0;
      m_out = 0.0;
     }

   void              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         double m = (m_pb + m_pa) / 2.0;
         double hi50  = m_mx50.Query(),  lo50  = m_mn50.Query();  // shift(1)
         double hi100 = m_mx100.Query(), lo100 = m_mn100.Query();
         if(hi50 == hi50 && m >= hi50)     m_b50 = 1.0;
         if(lo50 == lo50 && m <= lo50)     m_b50 = -1.0;          // <=lo wins
         if(hi100 == hi100 && m >= hi100)  m_b100 = 1.0;
         if(lo100 == lo100 && m <= lo100)  m_b100 = -1.0;
         m_mx50.Push(m); m_mn50.Push(m); m_mx100.Push(m); m_mn100.Push(m);
         double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
         m_vol_P = m_vol.Step(r) * m_sqrt252;
         m_prev_mid = m;
         m_s50_P = m_b50;
         m_s100_P = m_b100;
         double c50  = CsClip(m_s50_P  * m_vt_gd / m_vol_P, -m_cap_gd, m_cap_gd);
         double c100 = CsClip(m_s100_P * m_vt_gd / m_vol_P, -m_cap_gd, m_cap_gd);
         double lv   = CsClipHi(m_vt_gn / m_vol_P, m_cap_gn);     // clip(upper=)
         if(c50 == c50)   m_eff50 = c50;
         if(c100 == c100) m_eff100 = c100;
         if(lv == lv)     m_effN = lv;
         m_cur = d;
        }
      double night = (h >= 20 || h < 8) ? m_effN : 0.0;
      double raw = (m_eff50 + m_eff100) * m_c_gd + night * m_c_gn;
      if(h == 21 || h == 22)
         m_out = m_has_held ? m_held : 0.0;
      else
        {
         m_out = raw;
         m_held = raw;
         m_has_held = true;
        }
      m_pb = bid_c;
      m_pa = ask_c;
     }

   string            StateJson(void) const
     {
      string s = "{\"vol\": " + m_vol.StateJson();
      s += ", \"mx50\": "  + CsDonJson(m_mx50);
      s += ", \"mn50\": "  + CsDonJson(m_mn50);
      s += ", \"mx100\": " + CsDonJson(m_mx100);
      s += ", \"mn100\": " + CsDonJson(m_mn100);
      s += ", \"b50\": "  + CsJNum(m_b50);
      s += ", \"b100\": " + CsJNum(m_b100);
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"s50_P\": "  + CsJNum(m_s50_P);
      s += ", \"s100_P\": " + CsJNum(m_s100_P);
      s += ", \"vol_P\": "  + CsJNum(m_vol_P);
      s += ", \"eff50\": "  + CsJNum(m_eff50);
      s += ", \"eff100\": " + CsJNum(m_eff100);
      s += ", \"effN\": "   + CsJNum(m_effN);
      s += ", \"held\": "   + CsJNum(m_held);
      s += ", \"has_held\": " + (m_has_held ? "1" : "0");
      s += ", \"cur\": "    + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pb\": " + CsJNum(m_pb);
      s += ", \"pa\": " + CsJNum(m_pa);
      s += ", \"out\": " + CsJNum(m_out);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"vol\": ") || !m_vol.ParseState(p)) return false;
      if(!p.Lit(", \"mx50\": ")  || !CsDonParse(m_mx50, p))  return false;
      if(!p.Lit(", \"mn50\": ")  || !CsDonParse(m_mn50, p))  return false;
      if(!p.Lit(", \"mx100\": ") || !CsDonParse(m_mx100, p)) return false;
      if(!p.Lit(", \"mn100\": ") || !CsDonParse(m_mn100, p)) return false;
      if(!p.Lit(", \"b50\": "))  return false;
      m_b50 = p.Num();
      if(!p.Lit(", \"b100\": ")) return false;
      m_b100 = p.Num();
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"s50_P\": "))  return false;
      m_s50_P = p.Num();
      if(!p.Lit(", \"s100_P\": ")) return false;
      m_s100_P = p.Num();
      if(!p.Lit(", \"vol_P\": "))  return false;
      m_vol_P = p.Num();
      if(!p.Lit(", \"eff50\": "))  return false;
      m_eff50 = p.Num();
      if(!p.Lit(", \"eff100\": ")) return false;
      m_eff100 = p.Num();
      if(!p.Lit(", \"effN\": "))   return false;
      m_effN = p.Num();
      if(!p.Lit(", \"held\": "))   return false;
      m_held = p.Num();
      if(!p.Lit(", \"has_held\": ")) return false;
      m_has_held = p.Flag();
      if(!p.Lit(", \"cur\": "))    return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pb\": ")) return false;
      m_pb = p.Num();
      if(!p.Lit(", \"pa\": ")) return false;
      m_pa = p.Num();
      if(!p.Lit(", \"out\": ")) return false;
      m_out = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// Legs 1 (S5_JPY jpy_smart, defer) + 5 (S6 opex sign=+1, no defer) //
// / USDJPY — gen_jpy.  One instrument feed, two leg outputs.       //
//------------------------------------------------------------------//
class CCsLegJpy
  {
public:
   CCsRollStd        m_vol;
   CCsRollMean       m_sma100, m_sma20;
   CCsOpexCal        m_cal;
   CCsPolicy         m_pol;
   double            m_prev_mid;
   double            m_sigJ_P, m_vol_P;
   double            m_effJ, m_eff6;
   double            m_held;
   bool              m_has;
   long              m_cur;
   bool              m_started;
   double            m_pb, m_pa;
   double            m_out1, m_out5;
   double            m_vt_j, m_cap_j, m_jc_lo, m_jc_den, m_vt_s6, m_cap_s6;
   double            m_sqrt252;

   void              Configure(void)
     {
      m_vt_j = 0.15 * CS_RISK;   m_cap_j = 20.0;
      m_jc_lo = 0.5;             m_jc_den = 2.0 - 0.5;
      m_vt_s6 = 0.15 * CS_RISK * 1.0;
      m_cap_s6 = 6.0;
      m_sqrt252 = MathSqrt(252.0);
      m_vol.Init(20);
      m_sma100.Init(100);
      m_sma20.Init(20);
      m_cal.Init();
      m_pol.Init();
      m_prev_mid = SatNan();
      m_sigJ_P = SatNan(); m_vol_P = SatNan();
      m_effJ = 0.0; m_eff6 = 0.0;
      m_held = 0.0; m_has = false;
      m_cur = 0; m_started = false;
      m_pb = 0.0; m_pa = 0.0;
      m_out1 = 0.0; m_out5 = 0.0;
     }

   void              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         double m = (m_pb + m_pa) / 2.0;
         double ma1 = m_sma100.Step(m);
         double ma2 = m_sma20.Step(m);
         bool above  = (ma1 == ma1 && m > ma1);
         bool strong = (ma2 == ma2 && m > ma2);
         // carry gated at the FINALIZED day (the reference reads `cur`
         // before `cur = d`)
         double carry = m_pol.RateUsd(m_cur) - m_pol.RateJpy(m_cur);
         double gate = CsClip((carry - m_jc_lo) / m_jc_den, 0.0, 1.0);
         m_sigJ_P = (above && strong) ? 1.0 : (above ? (0.5 * gate) : 0.0);
         double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
         m_vol_P = m_vol.Step(r) * m_sqrt252;
         m_prev_mid = m;
         double cj = CsClipHi(m_sigJ_P * m_vt_j / m_vol_P, m_cap_j);  // clip(upper=)
         if(cj == cj)
            m_effJ = cj;
         double mask = (m_cal.In(d) && ((d + 3) % 7) < 5) ? 1.0 : 0.0;
         double c6 = CsClip(mask * 1.0 * m_vt_s6 / m_vol_P, -m_cap_s6, m_cap_s6);
         if(c6 == c6)
            m_eff6 = c6;
         m_cur = d;
        }
      // leg 1 (defer)
      double raw = m_effJ;
      if(h == 21 || h == 22)
         m_out1 = m_has ? m_held : 0.0;
      else
        {
         m_out1 = raw;
         m_held = raw;
         m_has = true;
        }
      // leg 5 (opex bar gates, no defer)
      double v = m_eff6;
      bool inwk = m_cal.In(d);
      if(inwk && dw == 0 && h < 12)  v = 0.0;
      if(inwk && dw == 4 && h >= 20) v = 0.0;
      if(dw == 6 && m_cal.In(d - 2)) v = 0.0;
      m_out5 = v;
      m_pb = bid_c;
      m_pa = ask_c;
     }

   string            StateJson(void) const
     {
      string s = "{\"vol\": " + m_vol.StateJson();
      s += ", \"sma100\": " + m_sma100.StateJson();
      s += ", \"sma20\": "  + m_sma20.StateJson();
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"sigJ_P\": " + CsJNum(m_sigJ_P);
      s += ", \"vol_P\": "  + CsJNum(m_vol_P);
      s += ", \"effJ\": "   + CsJNum(m_effJ);
      s += ", \"eff6\": "   + CsJNum(m_eff6);
      s += ", \"held\": "   + CsJNum(m_held);
      s += ", \"has\": "    + (m_has ? "1" : "0");
      s += ", \"cur\": "    + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pb\": " + CsJNum(m_pb);
      s += ", \"pa\": " + CsJNum(m_pa);
      s += ", \"out1\": " + CsJNum(m_out1);
      s += ", \"out5\": " + CsJNum(m_out5);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"vol\": ") || !m_vol.ParseState(p)) return false;
      if(!p.Lit(", \"sma100\": ") || !m_sma100.ParseState(p)) return false;
      if(!p.Lit(", \"sma20\": ")  || !m_sma20.ParseState(p))  return false;
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"sigJ_P\": ")) return false;
      m_sigJ_P = p.Num();
      if(!p.Lit(", \"vol_P\": "))  return false;
      m_vol_P = p.Num();
      if(!p.Lit(", \"effJ\": "))   return false;
      m_effJ = p.Num();
      if(!p.Lit(", \"eff6\": "))   return false;
      m_eff6 = p.Num();
      if(!p.Lit(", \"held\": "))   return false;
      m_held = p.Num();
      if(!p.Lit(", \"has\": "))    return false;
      m_has = p.Flag();
      if(!p.Lit(", \"cur\": "))    return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pb\": ")) return false;
      m_pb = p.Num();
      if(!p.Lit(", \"pa\": ")) return false;
      m_pa = p.Num();
      if(!p.Lit(", \"out1\": ")) return false;
      m_out1 = p.Num();
      if(!p.Lit(", \"out5\": ")) return false;
      m_out5 = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// Leg 2 S1_ETH / ETHUSD — gen_eth: crypto_mom (200d regime + 20/60 //
// cross), defer.                                                   //
//------------------------------------------------------------------//
class CCsLegEth
  {
public:
   CCsRollStd        m_vol;
   CCsRollMean       m_sma200, m_sma20, m_sma60;
   double            m_prev_mid;
   double            m_sig_P, m_vol_P;
   double            m_eff;
   double            m_held;
   bool              m_has;
   long              m_cur;
   bool              m_started;
   double            m_pb, m_pa;
   double            m_out;
   double            m_vt_e, m_cap_e;
   double            m_sqrt252;

   void              Configure(void)
     {
      m_vt_e = 0.40 * CS_RISK;
      m_cap_e = 1.2;
      m_sqrt252 = MathSqrt(252.0);
      m_vol.Init(20);
      m_sma200.Init(200);
      m_sma20.Init(20);
      m_sma60.Init(60);
      m_prev_mid = SatNan();
      m_sig_P = SatNan(); m_vol_P = SatNan();
      m_eff = 0.0;
      m_held = 0.0; m_has = false;
      m_cur = 0; m_started = false;
      m_pb = 0.0; m_pa = 0.0;
      m_out = 0.0;
     }

   void              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         double m = (m_pb + m_pa) / 2.0;
         double ma200 = m_sma200.Step(m);
         double ma20  = m_sma20.Step(m);
         double ma60  = m_sma60.Step(m);
         m_sig_P = (ma200 == ma200 && m > ma200
                    && ma20 == ma20 && ma60 == ma60
                    && ma20 > ma60) ? 1.0 : 0.0;
         double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
         m_vol_P = m_vol.Step(r) * m_sqrt252;
         m_prev_mid = m;
         double c = CsClipHi(m_sig_P * m_vt_e / m_vol_P, m_cap_e);   // clip(upper=)
         if(c == c)
            m_eff = c;
         m_cur = d;
        }
      double raw = m_eff;
      if(h == 21 || h == 22)
         m_out = m_has ? m_held : 0.0;
      else
        {
         m_out = raw;
         m_held = raw;
         m_has = true;
        }
      m_pb = bid_c;
      m_pa = ask_c;
     }

   string            StateJson(void) const
     {
      string s = "{\"vol\": " + m_vol.StateJson();
      s += ", \"sma200\": " + m_sma200.StateJson();
      s += ", \"sma20\": "  + m_sma20.StateJson();
      s += ", \"sma60\": "  + m_sma60.StateJson();
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"sig_P\": " + CsJNum(m_sig_P);
      s += ", \"vol_P\": " + CsJNum(m_vol_P);
      s += ", \"eff\": "   + CsJNum(m_eff);
      s += ", \"held\": "  + CsJNum(m_held);
      s += ", \"has\": "   + (m_has ? "1" : "0");
      s += ", \"cur\": "   + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pb\": " + CsJNum(m_pb);
      s += ", \"pa\": " + CsJNum(m_pa);
      s += ", \"out\": " + CsJNum(m_out);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"vol\": ") || !m_vol.ParseState(p)) return false;
      if(!p.Lit(", \"sma200\": ") || !m_sma200.ParseState(p)) return false;
      if(!p.Lit(", \"sma20\": ")  || !m_sma20.ParseState(p))  return false;
      if(!p.Lit(", \"sma60\": ")  || !m_sma60.ParseState(p))  return false;
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"sig_P\": ")) return false;
      m_sig_P = p.Num();
      if(!p.Lit(", \"vol_P\": ")) return false;
      m_vol_P = p.Num();
      if(!p.Lit(", \"eff\": "))   return false;
      m_eff = p.Num();
      if(!p.Lit(", \"held\": "))  return false;
      m_held = p.Num();
      if(!p.Lit(", \"has\": "))   return false;
      m_has = p.Flag();
      if(!p.Lit(", \"cur\": "))   return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pb\": ")) return false;
      m_pb = p.Num();
      if(!p.Lit(", \"pa\": ")) return false;
      m_pa = p.Num();
      if(!p.Lit(", \"out\": ")) return false;
      m_out = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// Leg 3 ZC_EG / EURGBP — gen_eg: eurgbp_zens.  Pre-20:00 daily     //
// series, 4-window z-ensemble, signal stamped at day+20:00 with    //
// shift(1) (knot queue); defer.                                    //
//------------------------------------------------------------------//
#define CS_EG_NW    4
#define CS_EG_KCAP  8

class CCsLegEg
  {
public:
   CCsRollMean       m_mz[CS_EG_NW];      // windows 20/40/60/80
   CCsRollStd        m_sz[CS_EG_NW];
   CCsRollStd        m_volr;
   double            m_prev_mid;
   double            m_egval_prev;        // tgt value at the LAST entry (pre-shift)
   long              m_kts[CS_EG_KCAP];   // knot queue (epoch_sec of day 20:00)
   double            m_kv[CS_EG_KCAP];
   int               m_kn;
   double            m_eff;
   double            m_held;
   bool              m_has;
   long              m_cur;
   bool              m_started;
   double            m_pre20_b, m_pre20_a;
   bool              m_pre20_has;
   bool              m_done;
   double            m_out;
   double            m_vt_eg, m_cap_eg, m_zclip;
   double            m_sqrt252;
   string            m_err;

   void              Configure(void)
     {
      m_vt_eg = 0.20 * CS_RISK;
      m_cap_eg = 20.0;
      m_zclip = 2.5;
      m_sqrt252 = MathSqrt(252.0);
      int wins[CS_EG_NW] = {20, 40, 60, 80};
      for(int k = 0; k < CS_EG_NW; k++)
        {
         m_mz[k].Init(wins[k]);
         m_sz[k].Init(wins[k]);
        }
      m_volr.Init(20);
      m_prev_mid = SatNan();
      m_egval_prev = SatNan();
      m_kn = 0;
      m_eff = 0.0;
      m_held = 0.0; m_has = false;
      m_cur = 0; m_started = false;
      m_pre20_b = 0.0; m_pre20_a = 0.0; m_pre20_has = false;
      m_done = false;
      m_out = 0.0;
      m_err = "";
     }

private:
   bool              Finalize(const long day_e)
     {
      double m = (m_pre20_b + m_pre20_a) / 2.0;
      if(m_kn >= CS_EG_KCAP)                    // structurally impossible:
        {                                       // knots consume same Step
         m_err = "EG knot queue overflow";
         return false;
        }
      m_kts[m_kn] = day_e * 86400 + 72000;      // tgt.shift(1) @ +20h
      m_kv[m_kn]  = m_egval_prev;
      m_kn++;
      double zsum = 0.0;
      for(int k = 0; k < CS_EG_NW; k++)
        {
         double mean = m_mz[k].Step(m);
         double sd   = m_sz[k].Step(m);
         double z = (m - mean) / sd;
         double piece = -CsClip(z, -m_zclip, m_zclip) / m_zclip;
         zsum = (k == 0) ? piece : zsum + piece;
        }
      double sig = zsum / 4.0;
      double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
      double annv = m_volr.Step(r) * m_sqrt252;        // NOT shifted
      m_egval_prev = CsClip(sig * m_vt_eg / annv, -m_cap_eg, m_cap_eg);
      m_prev_mid = m;
      return true;
     }

public:
   bool              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         if(m_pre20_has && !m_done)
            if(!Finalize(m_cur)) return false;
         m_pre20_has = false;
         m_done = false;
         m_cur = d;
        }
      if(h < 20)
        {
         m_pre20_b = bid_c;
         m_pre20_a = ask_c;
         m_pre20_has = true;
        }
      else if(!m_done && m_pre20_has)
        {
         if(!Finalize(d)) return false;
         m_done = true;
        }
      while(m_kn > 0 && m_kts[0] <= ts)
        {
         double v = m_kv[0];
         for(int k = 1; k < m_kn; k++)          // pop front
           {
            m_kts[k - 1] = m_kts[k];
            m_kv[k - 1]  = m_kv[k];
           }
         m_kn--;
         if(v == v)
            m_eff = v;                          // ffill skips NaN
        }
      double raw = m_eff;
      if(h == 21 || h == 22)
         m_out = m_has ? m_held : 0.0;
      else
        {
         m_out = raw;
         m_held = raw;
         m_has = true;
        }
      return true;
     }

   string            StateJson(void) const
     {
      string s = "{\"mz\": [";
      for(int k = 0; k < CS_EG_NW; k++)
         s += (k > 0 ? ", " : "") + m_mz[k].StateJson();
      s += "], \"sz\": [";
      for(int k = 0; k < CS_EG_NW; k++)
         s += (k > 0 ? ", " : "") + m_sz[k].StateJson();
      s += "], \"volr\": " + m_volr.StateJson();
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"egval_prev\": " + CsJNum(m_egval_prev);
      s += ", \"knots\": [";
      for(int k = 0; k < m_kn; k++)
         s += (k > 0 ? ", " : "") + "[" + IntegerToString(m_kts[k]) + ", "
              + CsJNum(m_kv[k]) + "]";
      s += "]";
      s += ", \"eff\": "  + CsJNum(m_eff);
      s += ", \"held\": " + CsJNum(m_held);
      s += ", \"has\": "  + (m_has ? "1" : "0");
      s += ", \"cur\": "  + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pre20_b\": " + CsJNum(m_pre20_b);
      s += ", \"pre20_a\": " + CsJNum(m_pre20_a);
      s += ", \"pre20_has\": " + (m_pre20_has ? "1" : "0");
      s += ", \"done\": " + (m_done ? "1" : "0");
      s += ", \"out\": " + CsJNum(m_out);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"mz\": [")) return false;
      for(int k = 0; k < CS_EG_NW; k++)
        {
         if(k > 0 && !p.Lit(", ")) return false;
         if(!m_mz[k].ParseState(p)) return false;
        }
      if(!p.Lit("], \"sz\": [")) return false;
      for(int k = 0; k < CS_EG_NW; k++)
        {
         if(k > 0 && !p.Lit(", ")) return false;
         if(!m_sz[k].ParseState(p)) return false;
        }
      if(!p.Lit("], \"volr\": ") || !m_volr.ParseState(p)) return false;
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"egval_prev\": ")) return false;
      m_egval_prev = p.Num();
      if(!p.Lit(", \"knots\": [")) return false;
      m_kn = 0;
      while(!p.PeekIs(']'))
        {
         if(m_kn > 0 && !p.Lit(", ")) return false;
         if(!p.Lit("[")) return false;
         if(m_kn >= CS_EG_KCAP) { p.m_ok = false; p.m_err = "eg knots overflow"; return false; }
         m_kts[m_kn] = p.Int();
         if(!p.Lit(", ")) return false;
         m_kv[m_kn] = p.Num();
         if(!p.Lit("]")) return false;
         m_kn++;
        }
      if(!p.Lit("]")) return false;
      if(!p.Lit(", \"eff\": "))  return false;
      m_eff = p.Num();
      if(!p.Lit(", \"held\": ")) return false;
      m_held = p.Num();
      if(!p.Lit(", \"has\": "))  return false;
      m_has = p.Flag();
      if(!p.Lit(", \"cur\": "))  return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pre20_b\": ")) return false;
      m_pre20_b = p.Num();
      if(!p.Lit(", \"pre20_a\": ")) return false;
      m_pre20_a = p.Num();
      if(!p.Lit(", \"pre20_has\": ")) return false;
      m_pre20_has = p.Flag();
      if(!p.Lit(", \"done\": ")) return false;
      m_done = p.Flag();
      if(!p.Lit(", \"out\": ")) return false;
      m_out = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// Leg 4 BOOK_USTEC / USTEC — gen_ustec: inner-deferred regime +    //
// Monday leverage, then OUTER defer (the Monday-23:00 exit).       //
//------------------------------------------------------------------//
class CCsLegUstec
  {
public:
   CCsRollStd        m_vol;
   CCsRollMean       m_sma200;
   double            m_prev_mid;
   double            m_sig_P, m_vol_P;
   double            m_effReg, m_effMon;
   double            m_heldR;
   bool              m_hasR;
   double            m_held;
   bool              m_has;
   long              m_cur;
   bool              m_started;
   double            m_pb, m_pa;
   double            m_out;
   double            m_vt_ur, m_cap_ur, m_vt_um, m_cap_um, m_c_ur, m_c_um;
   double            m_sqrt252;

   void              Configure(void)
     {
      double s_u = (0.85 * CS_RISK) / 0.85;
      m_vt_ur = 0.25 * s_u;   m_cap_ur = 6.0;
      m_vt_um = 0.60 * s_u;   m_cap_um = 10.0;
      m_c_ur = 0.09 / 0.24;   m_c_um = 0.15 / 0.24;
      m_sqrt252 = MathSqrt(252.0);
      m_vol.Init(20);
      m_sma200.Init(200);
      m_prev_mid = SatNan();
      m_sig_P = SatNan(); m_vol_P = SatNan();
      m_effReg = 0.0; m_effMon = 0.0;
      m_heldR = 0.0; m_hasR = false;
      m_held = 0.0; m_has = false;
      m_cur = 0; m_started = false;
      m_pb = 0.0; m_pa = 0.0;
      m_out = 0.0;
     }

   void              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         double m = (m_pb + m_pa) / 2.0;
         double ma = m_sma200.Step(m);
         m_sig_P = (ma == ma && m > ma) ? 1.0 : 0.0;
         double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
         m_vol_P = m_vol.Step(r) * m_sqrt252;
         m_prev_mid = m;
         double c  = CsClip(m_sig_P * m_vt_ur / m_vol_P, -m_cap_ur, m_cap_ur);
         double lv = CsClipHi(m_vt_um / m_vol_P, m_cap_um);
         if(c == c)   m_effReg = c;
         if(lv == lv) m_effMon = lv;
         m_cur = d;
        }
      // inner defer_reopen on the regime component (structural no-op,
      // kept for statement parity with the reference)
      double regd;
      if(h == 21 || h == 22)
         regd = m_hasR ? m_heldR : 0.0;
      else
        {
         regd = m_effReg;
         m_heldR = m_effReg;
         m_hasR = true;
        }
      double mon = (dw == 0 && h < 21) ? m_effMon : 0.0;
      double raw = regd * m_c_ur + mon * m_c_um;
      if(h == 21 || h == 22)
         m_out = m_has ? m_held : 0.0;
      else
        {
         m_out = raw;
         m_held = raw;
         m_has = true;
        }
      m_pb = bid_c;
      m_pa = ask_c;
     }

   string            StateJson(void) const
     {
      string s = "{\"vol\": " + m_vol.StateJson();
      s += ", \"sma200\": " + m_sma200.StateJson();
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"sig_P\": " + CsJNum(m_sig_P);
      s += ", \"vol_P\": " + CsJNum(m_vol_P);
      s += ", \"effReg\": " + CsJNum(m_effReg);
      s += ", \"effMon\": " + CsJNum(m_effMon);
      s += ", \"heldR\": " + CsJNum(m_heldR);
      s += ", \"hasR\": "  + (m_hasR ? "1" : "0");
      s += ", \"held\": "  + CsJNum(m_held);
      s += ", \"has\": "   + (m_has ? "1" : "0");
      s += ", \"cur\": "   + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pb\": " + CsJNum(m_pb);
      s += ", \"pa\": " + CsJNum(m_pa);
      s += ", \"out\": " + CsJNum(m_out);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"vol\": ") || !m_vol.ParseState(p)) return false;
      if(!p.Lit(", \"sma200\": ") || !m_sma200.ParseState(p)) return false;
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"sig_P\": ")) return false;
      m_sig_P = p.Num();
      if(!p.Lit(", \"vol_P\": ")) return false;
      m_vol_P = p.Num();
      if(!p.Lit(", \"effReg\": ")) return false;
      m_effReg = p.Num();
      if(!p.Lit(", \"effMon\": ")) return false;
      m_effMon = p.Num();
      if(!p.Lit(", \"heldR\": ")) return false;
      m_heldR = p.Num();
      if(!p.Lit(", \"hasR\": "))  return false;
      m_hasR = p.Flag();
      if(!p.Lit(", \"held\": "))  return false;
      m_held = p.Num();
      if(!p.Lit(", \"has\": "))   return false;
      m_has = p.Flag();
      if(!p.Lit(", \"cur\": "))   return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pb\": ")) return false;
      m_pb = p.Num();
      if(!p.Lit(", \"pa\": ")) return false;
      m_pa = p.Num();
      if(!p.Lit(", \"out\": ")) return false;
      m_out = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// Legs 6/7 S6 / AUDUSD/NZDUSD — gen_opex_fx (sign = -1), no defer. //
//------------------------------------------------------------------//
class CCsLegOpexFx
  {
public:
   CCsRollStd        m_vol;
   CCsOpexCal        m_cal;
   double            m_sign;
   double            m_prev_mid;
   double            m_vol_P;
   double            m_eff;
   long              m_cur;
   bool              m_started;
   double            m_pb, m_pa;
   double            m_out;
   double            m_vt_s6, m_cap_s6;
   double            m_sqrt252;

   void              Configure(const double sign)
     {
      m_sign = sign;
      m_vt_s6 = 0.15 * CS_RISK * 1.0;
      m_cap_s6 = 6.0;
      m_sqrt252 = MathSqrt(252.0);
      m_vol.Init(20);
      m_cal.Init();
      m_prev_mid = SatNan();
      m_vol_P = SatNan();
      m_eff = 0.0;
      m_cur = 0; m_started = false;
      m_pb = 0.0; m_pa = 0.0;
      m_out = 0.0;
     }

   void              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         double m = (m_pb + m_pa) / 2.0;
         double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
         m_vol_P = m_vol.Step(r) * m_sqrt252;
         m_prev_mid = m;
         double mask = (m_cal.In(d) && ((d + 3) % 7) < 5) ? 1.0 : 0.0;
         double c = CsClip(mask * m_sign * m_vt_s6 / m_vol_P, -m_cap_s6, m_cap_s6);
         if(c == c)
            m_eff = c;
         m_cur = d;
        }
      double v = m_eff;
      bool inwk = m_cal.In(d);
      if(inwk && dw == 0 && h < 12)  v = 0.0;
      if(inwk && dw == 4 && h >= 20) v = 0.0;
      if(dw == 6 && m_cal.In(d - 2)) v = 0.0;
      m_out = v;
      m_pb = bid_c;
      m_pa = ask_c;
     }

   string            StateJson(void) const
     {
      string s = "{\"vol\": " + m_vol.StateJson();
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"vol_P\": " + CsJNum(m_vol_P);
      s += ", \"eff\": "   + CsJNum(m_eff);
      s += ", \"cur\": "   + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pb\": " + CsJNum(m_pb);
      s += ", \"pa\": " + CsJNum(m_pa);
      s += ", \"out\": " + CsJNum(m_out);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"vol\": ") || !m_vol.ParseState(p)) return false;
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"vol_P\": ")) return false;
      m_vol_P = p.Num();
      if(!p.Lit(", \"eff\": "))   return false;
      m_eff = p.Num();
      if(!p.Lit(", \"cur\": "))   return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pb\": ")) return false;
      m_pb = p.Num();
      if(!p.Lit(", \"pa\": ")) return false;
      m_pa = p.Num();
      if(!p.Lit(", \"out\": ")) return false;
      m_out = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//------------------------------------------------------------------//
// Leg 8 BTC_REP / BTCUSD — gen_btc: btc_hurdle_legs lb=63          //
// hurdle=0.40 regime=200; daily fillna(0), NO carry, no defer.     //
//------------------------------------------------------------------//
#define CS_BTC_LB 63

class CCsLegBtc
  {
public:
   CCsRollStd        m_vol;
   CCsRollMean       m_sma200;
   double            m_dh[CS_BTC_LB];     // ring of the last 63 daily mids
   int               m_dh_head;
   long              m_dcount;            // total daily entries appended
   double            m_prev_mid;
   double            m_sig_P, m_vol_P;
   double            m_eff;
   long              m_cur;
   bool              m_started;
   double            m_pb, m_pa;
   double            m_out;
   double            m_vt_b, m_cap_b, m_hurdle, m_expo;
   double            m_sqrt252;

   void              Configure(void)
     {
      m_vt_b = 0.40 * CS_RISK;
      m_cap_b = 1.2;
      m_hurdle = 0.40;
      m_expo = 365.0 / (double)CS_BTC_LB;
      m_sqrt252 = MathSqrt(252.0);
      m_vol.Init(20);
      m_sma200.Init(200);
      for(int i = 0; i < CS_BTC_LB; i++)
         m_dh[i] = 0.0;
      m_dh_head = 0;
      m_dcount = 0;
      m_prev_mid = SatNan();
      m_sig_P = SatNan(); m_vol_P = SatNan();
      m_eff = 0.0;
      m_cur = 0; m_started = false;
      m_pb = 0.0; m_pa = 0.0;
      m_out = 0.0;
     }

   void              Step(const long ts, const double bid_c, const double ask_c)
     {
      long d; int h, dw;
      CsFields(ts, d, h, dw);
      if(!m_started)
        {
         m_cur = d;
         m_started = true;
        }
      else if(d != m_cur)
        {
         double m = (m_pb + m_pa) / 2.0;
         double ma = m_sma200.Step(m);
         double ann;
         if(m_dcount >= CS_BTC_LB)
           {
            // d_hist[-63] = oldest ring slot (ring holds exactly the
            // last 63 entries once dcount >= 63).
            // MATHPOW NOTE: feeds only the boolean ann > hurdle; the
            // python mirror measures min|ann - hurdle| (file header).
            ann = MathPow(m / m_dh[m_dh_head], m_expo) - 1.0;
           }
         else
            ann = SatNan();
         m_sig_P = (ma == ma && m > ma
                    && ann == ann && ann > m_hurdle) ? 1.0 : 0.0;
         double r = (m_prev_mid == m_prev_mid) ? (m / m_prev_mid - 1.0) : SatNan();
         m_vol_P = m_vol.Step(r) * m_sqrt252;
         m_prev_mid = m;
         // d_hist.append(m)
         if(m_dcount < CS_BTC_LB)
            m_dh[(m_dh_head + (int)m_dcount) % CS_BTC_LB] = m;
         else
           {
            m_dh[m_dh_head] = m;
            m_dh_head = (m_dh_head + 1) % CS_BTC_LB;
           }
         m_dcount++;
         double c = CsClip(m_sig_P * m_vt_b / m_vol_P, 0.0, m_cap_b);
         m_eff = (c == c) ? c : 0.0;                       // tgt.fillna(0.0)
         m_cur = d;
        }
      m_out = m_eff;
      m_pb = bid_c;
      m_pa = ask_c;
     }

   string            StateJson(void) const
     {
      string s = "{\"vol\": " + m_vol.StateJson();
      s += ", \"sma200\": " + m_sma200.StateJson();
      s += ", \"dcount\": " + IntegerToString(m_dcount);
      s += ", \"dh\": [";
      int n = (m_dcount < CS_BTC_LB) ? (int)m_dcount : CS_BTC_LB;
      for(int j = 0; j < n; j++)
         s += (j > 0 ? ", " : "") + CsJNum(m_dh[(m_dh_head + j) % CS_BTC_LB]);
      s += "]";
      s += ", \"prev_mid\": " + CsJNum(m_prev_mid);
      s += ", \"sig_P\": " + CsJNum(m_sig_P);
      s += ", \"vol_P\": " + CsJNum(m_vol_P);
      s += ", \"eff\": "   + CsJNum(m_eff);
      s += ", \"cur\": "   + IntegerToString(m_cur);
      s += ", \"started\": " + (m_started ? "1" : "0");
      s += ", \"pb\": " + CsJNum(m_pb);
      s += ", \"pa\": " + CsJNum(m_pa);
      s += ", \"out\": " + CsJNum(m_out);
      s += "}";
      return s;
     }

   bool              ParseState(CCsTok &p)
     {
      if(!p.Lit("{\"vol\": ") || !m_vol.ParseState(p)) return false;
      if(!p.Lit(", \"sma200\": ") || !m_sma200.ParseState(p)) return false;
      if(!p.Lit(", \"dcount\": ")) return false;
      m_dcount = p.Int();
      if(!p.Lit(", \"dh\": [")) return false;
      m_dh_head = 0;
      int n = 0;
      while(!p.PeekIs(']'))
        {
         if(n > 0 && !p.Lit(", ")) return false;
         if(n >= CS_BTC_LB) { p.m_ok = false; p.m_err = "btc dh overflow"; return false; }
         m_dh[n] = p.Num();
         n++;
        }
      if(!p.Lit("]")) return false;
      int expect = (m_dcount < CS_BTC_LB) ? (int)m_dcount : CS_BTC_LB;
      if(n != expect) { p.m_ok = false; p.m_err = "btc dh count mismatch"; return false; }
      if(!p.Lit(", \"prev_mid\": ")) return false;
      m_prev_mid = p.Num();
      if(!p.Lit(", \"sig_P\": ")) return false;
      m_sig_P = p.Num();
      if(!p.Lit(", \"vol_P\": ")) return false;
      m_vol_P = p.Num();
      if(!p.Lit(", \"eff\": "))   return false;
      m_eff = p.Num();
      if(!p.Lit(", \"cur\": "))   return false;
      m_cur = p.Int();
      if(!p.Lit(", \"started\": ")) return false;
      m_started = p.Flag();
      if(!p.Lit(", \"pb\": ")) return false;
      m_pb = p.Num();
      if(!p.Lit(", \"pa\": ")) return false;
      m_pa = p.Num();
      if(!p.Lit(", \"out\": ")) return false;
      m_out = p.Num();
      if(!p.Lit("}")) return false;
      return p.m_ok;
     }
  };

//==================================================================//
// CCoreSignal — the 8-instrument / 9-leg live target source.       //
// Feed one completed M1 bar per instrument via StepBar (raw server //
// stamp, six-field close mids: bid_c/ask_c); read the leg targets  //
// via Tgt(leg).  Cold start = the anchor's baked-in warmup: init   //
// EMPTY at 2020-01-02 for in-sample reproduction (design 2.1).     //
//==================================================================//
class CCoreSignal
  {
private:
   CCsLegXau         m_xau;
   CCsLegJpy         m_jpy;
   CCsLegEth         m_eth;
   CCsLegEg          m_eg;
   CCsLegUstec       m_ustec;
   CCsLegOpexFx      m_aud;
   CCsLegOpexFx      m_nzd;
   CCsLegBtc         m_btc;
   double            m_tgt[CS_NLEGS];
   long              m_lastTs[CS_NINST];
   bool              m_hasTs[CS_NINST];
   string            m_err;

public:
   void              Configure(void)
     {
      m_xau.Configure();
      m_jpy.Configure();
      m_eth.Configure();
      m_eg.Configure();
      m_ustec.Configure();
      m_aud.Configure(-1.0);
      m_nzd.Configure(-1.0);
      m_btc.Configure();
      for(int j = 0; j < CS_NLEGS; j++)
         m_tgt[j] = 0.0;
      for(int i = 0; i < CS_NINST; i++)
        {
         m_lastTs[i] = 0;
         m_hasTs[i] = false;
        }
      m_err = "";
     }

   string            LastError(void) const { return m_err; }

   bool              StepBar(const int inst, const long ts,
                             const double bid_c, const double ask_c)
     {
      if(inst < 0 || inst >= CS_NINST)
        {
         m_err = "bad inst " + IntegerToString(inst);
         return false;
        }
      if(m_hasTs[inst] && ts <= m_lastTs[inst])
        {
         m_err = StringFormat("non-ascending stamp inst %d: %I64d <= %I64d",
                              inst, ts, m_lastTs[inst]);
         return false;
        }
      switch(inst)
        {
         case CS_I_XAUUSD:
            m_xau.Step(ts, bid_c, ask_c);
            m_tgt[0] = m_xau.m_out;
            break;
         case CS_I_USDJPY:
            m_jpy.Step(ts, bid_c, ask_c);
            m_tgt[1] = m_jpy.m_out1;
            m_tgt[5] = m_jpy.m_out5;
            break;
         case CS_I_ETHUSD:
            m_eth.Step(ts, bid_c, ask_c);
            m_tgt[2] = m_eth.m_out;
            break;
         case CS_I_EURGBP:
            if(!m_eg.Step(ts, bid_c, ask_c))
              {
               m_err = "EG: " + m_eg.m_err;
               return false;
              }
            m_tgt[3] = m_eg.m_out;
            break;
         case CS_I_USTEC:
            m_ustec.Step(ts, bid_c, ask_c);
            m_tgt[4] = m_ustec.m_out;
            break;
         case CS_I_AUDUSD:
            m_aud.Step(ts, bid_c, ask_c);
            m_tgt[6] = m_aud.m_out;
            break;
         case CS_I_NZDUSD:
            m_nzd.Step(ts, bid_c, ask_c);
            m_tgt[7] = m_nzd.m_out;
            break;
         case CS_I_BTCUSD:
            m_btc.Step(ts, bid_c, ask_c);
            m_tgt[8] = m_btc.m_out;
            break;
        }
      m_lastTs[inst] = ts;
      m_hasTs[inst] = true;
      return true;
     }

   double            Tgt(const int leg) const
     {
      return (leg >= 0 && leg < CS_NLEGS) ? m_tgt[leg] : SatNan();
     }

   //---------------------------------------------------------------
   // warm-blob state (BookState convention: %.17g, fixed key order)
   //---------------------------------------------------------------
   string            GetState(void)
     {
      string s = "{\"xau\": " + m_xau.StateJson();
      s += ", \"jpy\": "   + m_jpy.StateJson();
      s += ", \"eth\": "   + m_eth.StateJson();
      s += ", \"eg\": "    + m_eg.StateJson();
      s += ", \"ustec\": " + m_ustec.StateJson();
      s += ", \"aud\": "   + m_aud.StateJson();
      s += ", \"nzd\": "   + m_nzd.StateJson();
      s += ", \"btc\": "   + m_btc.StateJson();
      s += ", \"tgt\": [";
      for(int j = 0; j < CS_NLEGS; j++)
         s += (j > 0 ? ", " : "") + CsJNum(m_tgt[j]);
      s += "]";
      s += ", \"last_ts\": [";
      for(int i = 0; i < CS_NINST; i++)
         s += (i > 0 ? ", " : "") + IntegerToString(m_lastTs[i]);
      s += "]";
      s += ", \"has_ts\": [";
      for(int i = 0; i < CS_NINST; i++)
         s += (i > 0 ? ", " : "") + (m_hasTs[i] ? "1" : "0");
      s += "]}";
      return s;
     }

   bool              SetState(const string state)
     {
      CCsTok p;
      p.Init(state);
      if(!p.Lit("{\"xau\": ")   || !m_xau.ParseState(p))   { m_err = "SetState xau: "   + p.m_err; return false; }
      if(!p.Lit(", \"jpy\": ")  || !m_jpy.ParseState(p))   { m_err = "SetState jpy: "   + p.m_err; return false; }
      if(!p.Lit(", \"eth\": ")  || !m_eth.ParseState(p))   { m_err = "SetState eth: "   + p.m_err; return false; }
      if(!p.Lit(", \"eg\": ")   || !m_eg.ParseState(p))    { m_err = "SetState eg: "    + p.m_err; return false; }
      if(!p.Lit(", \"ustec\": ")|| !m_ustec.ParseState(p)) { m_err = "SetState ustec: " + p.m_err; return false; }
      if(!p.Lit(", \"aud\": ")  || !m_aud.ParseState(p))   { m_err = "SetState aud: "   + p.m_err; return false; }
      if(!p.Lit(", \"nzd\": ")  || !m_nzd.ParseState(p))   { m_err = "SetState nzd: "   + p.m_err; return false; }
      if(!p.Lit(", \"btc\": ")  || !m_btc.ParseState(p))   { m_err = "SetState btc: "   + p.m_err; return false; }
      if(!p.Lit(", \"tgt\": [")) { m_err = "SetState tgt: " + p.m_err; return false; }
      for(int j = 0; j < CS_NLEGS; j++)
        {
         if(j > 0 && !p.Lit(", ")) { m_err = "SetState tgt sep"; return false; }
         m_tgt[j] = p.Num();
        }
      if(!p.Lit("], \"last_ts\": [")) { m_err = "SetState last_ts: " + p.m_err; return false; }
      for(int i = 0; i < CS_NINST; i++)
        {
         if(i > 0 && !p.Lit(", ")) { m_err = "SetState last_ts sep"; return false; }
         m_lastTs[i] = p.Int();
        }
      if(!p.Lit("], \"has_ts\": [")) { m_err = "SetState has_ts: " + p.m_err; return false; }
      for(int i = 0; i < CS_NINST; i++)
        {
         if(i > 0 && !p.Lit(", ")) { m_err = "SetState has_ts sep"; return false; }
         m_hasTs[i] = p.Flag();
        }
      if(!p.Lit("]}")) { m_err = "SetState tail: " + p.m_err; return false; }
      if(!p.m_ok) { m_err = "SetState: " + p.m_err; return false; }
      m_err = "";
      return true;
     }
  };

//==================================================================//
// CCoreTrigger — the band/harvest segment-boundary detector, LIVE  //
// mode (design section 4.3; owner ratification 2).  Causal         //
// streaming: NO retrospective backfill — before a slot's first     //
// print of a segment the slot is held at seed*W (hold-at-legcap;   //
// per-leg legcap-hold inside multi-leg slots), with held-row       //
// telemetry counters.  The anchor-exact harness (incl. bfill)      //
// lives in python (trigger_detector.py) ONLY.                      //
//                                                                  //
// Anchor semantics kept exactly (measured slack: 12-day min gap    //
// vs the 5-day gate, 2-day max bfill lag):                         //
//  * day rows = each slot's value at its OWN last stamp of the raw //
//    day; missing day -> ffill carry; never printed -> seed*W;     //
//  * decisions on EVERY day label in frame order (incl. weekends), //
//    scanned strictly AFTER the segment-start (act) day;           //
//  * band: shares = slot/sum, fire if max > up OR min < down,      //
//    gated by (decided_day - act_day) >= min_gap (a breach on a    //
//    skipped day does NOT latch);                                  //
//  * harvest: any slot > kmult*seed*W, NO min-gap (ratification 4);//
//  * band wins a same-day tie; act = decided day + 1 (midnight,    //
//    even into a weekend).                                         //
//                                                                  //
// Driving contract per M1 union bar (BookOrchestrator live mode):  //
//   1. CheckDay(ts, fired) FIRST — on a raw-day rollover this      //
//      finalizes the previous day's row and tests it; if fired,    //
//      the caller runs FinishSegment/ComputeFCore over bars < act, //
//      reseeds CoreSim, then calls BeginSegment(new_seed, ActDay());//
//   2. step the bar into CoreSim;                                  //
//   3. OnLegBar(leg, ts, eq_c) for every leg with a bar this       //
//      minute (close-mark equity from CCoreLegSim::EqC).           //
//==================================================================//
#define CT_MAXSLOTS 16
#define CT_MAXLEGS  16

class CCoreTrigger
  {
private:
   // --- static config ---
   int               m_nSlots, m_nLegs;
   int               m_legSlot[CT_MAXLEGS];
   int               m_slotNLegs[CT_MAXSLOTS];
   double            m_up, m_down, m_kmult;
   int               m_minGap;
   double            m_W;
   // --- segment state ---
   double            m_seed;
   long              m_segStartDay;
   double            m_legVal[CT_MAXLEGS];
   bool              m_legHas[CT_MAXLEGS];
   double            m_slotDay[CT_MAXSLOTS];
   bool              m_slotDayHas[CT_MAXSLOTS];
   double            m_slotCarry[CT_MAXSLOTS];
   bool              m_slotCarryHas[CT_MAXSLOTS];
   long              m_curDay;
   bool              m_dayOpen;
   // --- last-fire outputs ---
   long              m_decidedDay, m_actDay;
   string            m_kind;
   double            m_maxShare, m_minShare;
   int               m_maxSlot, m_minSlot;
   // --- telemetry (cumulative) ---
   long              m_rowsScanned;
   long              m_heldRows;
   string            m_err;

public:
   bool              Configure(const int n_slots, const int n_legs,
                               const int &leg_slot[],
                               const double up, const double down,
                               const double kmult, const int min_gap_days)
     {
      if(n_slots <= 0 || n_slots > CT_MAXSLOTS) { m_err = "bad n_slots"; return false; }
      if(n_legs <= 0 || n_legs > CT_MAXLEGS)    { m_err = "bad n_legs";  return false; }
      if(ArraySize(leg_slot) < n_legs)          { m_err = "leg_slot short"; return false; }
      m_nSlots = n_slots;
      m_nLegs = n_legs;
      for(int s = 0; s < n_slots; s++)
         m_slotNLegs[s] = 0;
      for(int l = 0; l < n_legs; l++)
        {
         int s = leg_slot[l];
         if(s < 0 || s >= n_slots) { m_err = "bad slot for leg " + IntegerToString(l); return false; }
         m_legSlot[l] = s;
         m_slotNLegs[s]++;
        }
      for(int s2 = 0; s2 < n_slots; s2++)
         if(m_slotNLegs[s2] == 0) { m_err = "empty slot " + IntegerToString(s2); return false; }
      m_up = up; m_down = down; m_kmult = kmult;
      m_minGap = min_gap_days;
      m_W = 1.0 / (double)n_slots;
      m_seed = 0.0;
      m_segStartDay = 0;
      m_curDay = 0; m_dayOpen = false;
      m_decidedDay = 0; m_actDay = 0; m_kind = "";
      m_maxShare = 0.0; m_minShare = 0.0; m_maxSlot = -1; m_minSlot = -1;
      m_rowsScanned = 0; m_heldRows = 0;
      m_err = "";
      ResetSegArrays();
      return true;
     }

private:
   void              ResetSegArrays(void)
     {
      for(int l = 0; l < m_nLegs; l++)
        {
         m_legVal[l] = 0.0;
         m_legHas[l] = false;
        }
      for(int s = 0; s < m_nSlots; s++)
        {
         m_slotDay[s] = 0.0;     m_slotDayHas[s] = false;
         m_slotCarry[s] = 0.0;   m_slotCarryHas[s] = false;
        }
     }

public:
   // fresh segment at act_eday (act = the reseed midnight's epoch day)
   bool              BeginSegment(const double seed, const long act_eday)
     {
      if(m_nSlots <= 0) { m_err = "not configured"; return false; }
      m_seed = seed;
      m_segStartDay = act_eday;
      m_curDay = 0;
      m_dayOpen = false;
      ResetSegArrays();
      return true;
     }

   // call FIRST per union M1 bar; fired=true -> read DecidedDay/ActDay/
   // Kind/MaxShare/MinShare, then reseed via BeginSegment.
   bool              CheckDay(const long ts, bool &fired)
     {
      fired = false;
      long d = ts / 86400;
      if(!m_dayOpen)
        {
         m_curDay = d;
         m_dayOpen = true;
         return true;
        }
      if(d < m_curDay) { m_err = "non-ascending day"; return false; }
      if(d == m_curDay)
         return true;
      // ---- raw-day rollover: finalize m_curDay's frame row ----
      double row[CT_MAXSLOTS];
      bool   held_any = false;
      for(int s = 0; s < m_nSlots; s++)
        {
         if(m_slotDayHas[s])
           {
            m_slotCarry[s] = m_slotDay[s];        // pandas ffill carry
            m_slotCarryHas[s] = true;
           }
         if(m_slotCarryHas[s])
            row[s] = m_slotCarry[s];
         else
           {
            row[s] = m_seed * m_W;                // hold-at-legcap (LIVE)
            held_any = true;
           }
        }
      // ---- test the row (scan strictly after the act day) ----
      if(m_curDay > m_segStartDay)
        {
         m_rowsScanned++;
         if(held_any)
            m_heldRows++;
         double tot = 0.0;
         for(int s = 0; s < m_nSlots; s++)
            tot = tot + row[s];
         double hi = row[0], lo = row[0];
         int hiS = 0, loS = 0;
         for(int s = 1; s < m_nSlots; s++)
           {
            if(row[s] > hi) { hi = row[s]; hiS = s; }
            if(row[s] < lo) { lo = row[s]; loS = s; }
           }
         double sh_hi = hi / tot;
         double sh_lo = lo / tot;
         bool gap_ok = (m_curDay - m_segStartDay) >= m_minGap;
         bool band_raw = (sh_hi > m_up) || (sh_lo < m_down);
         bool harv_raw = (hi > m_kmult * m_seed * m_W);
         bool fired_band = band_raw && gap_ok;
         if(fired_band || harv_raw)
           {
            fired = true;
            m_decidedDay = m_curDay;
            m_actDay = m_curDay + 1;
            m_kind = fired_band ? "band" : "harvest";   // band wins ties
            m_maxShare = sh_hi; m_minShare = sh_lo;
            m_maxSlot = hiS;    m_minSlot = loS;
           }
        }
      // open the new day
      m_curDay = d;
      for(int s = 0; s < m_nSlots; s++)
         m_slotDayHas[s] = false;
      return true;
     }

   // after CoreSim stepped this leg's bar: eq_c = close-mark leg equity
   bool              OnLegBar(const int leg, const long ts, const double eq_c)
     {
      if(leg < 0 || leg >= m_nLegs) { m_err = "bad leg"; return false; }
      if(!m_dayOpen)
        {
         m_curDay = ts / 86400;      // first bar of a fresh segment
         m_dayOpen = true;
        }
      m_legVal[leg] = eq_c;
      m_legHas[leg] = true;
      int s = m_legSlot[leg];
      // slot value at this stamp: member ffill, legcap-hold for members
      // that have not printed yet this segment (leg index order)
      double v = 0.0;
      for(int l = 0; l < m_nLegs; l++)
        {
         if(m_legSlot[l] != s)
            continue;
         double lc = m_seed * m_W / (double)m_slotNLegs[s];  // CoreSim legcap shape
         v = v + (m_legHas[l] ? m_legVal[l] : lc);
        }
      m_slotDay[s] = v;
      m_slotDayHas[s] = true;
      return true;
     }

   // ---- accessors ----
   string            LastError(void)  const { return m_err; }
   long              DecidedDay(void) const { return m_decidedDay; }
   long              ActDay(void)     const { return m_actDay; }
   string            Kind(void)       const { return m_kind; }
   double            MaxShare(void)   const { return m_maxShare; }
   double            MinShare(void)   const { return m_minShare; }
   int               MaxSlot(void)    const { return m_maxSlot; }
   int               MinSlot(void)    const { return m_minSlot; }
   long              RowsScanned(void) const { return m_rowsScanned; }
   long              HeldRows(void)   const { return m_heldRows; }
   double            Seed(void)       const { return m_seed; }
   long              SegStartDay(void) const { return m_segStartDay; }

   //---------------------------------------------------------------
   string            GetState(void)
     {
      string s = "{\"seed\": " + CsJNum(m_seed);
      s += ", \"seg_start_day\": " + IntegerToString(m_segStartDay);
      s += ", \"cur_day\": " + IntegerToString(m_curDay);
      s += ", \"day_open\": " + (m_dayOpen ? "1" : "0");
      s += ", \"leg_val\": [";
      for(int l = 0; l < m_nLegs; l++)
         s += (l > 0 ? ", " : "") + CsJNum(m_legVal[l]);
      s += "], \"leg_has\": [";
      for(int l = 0; l < m_nLegs; l++)
         s += (l > 0 ? ", " : "") + (m_legHas[l] ? "1" : "0");
      s += "], \"slot_day\": [";
      for(int q = 0; q < m_nSlots; q++)
         s += (q > 0 ? ", " : "") + CsJNum(m_slotDay[q]);
      s += "], \"slot_day_has\": [";
      for(int q = 0; q < m_nSlots; q++)
         s += (q > 0 ? ", " : "") + (m_slotDayHas[q] ? "1" : "0");
      s += "], \"slot_carry\": [";
      for(int q = 0; q < m_nSlots; q++)
         s += (q > 0 ? ", " : "") + CsJNum(m_slotCarry[q]);
      s += "], \"slot_carry_has\": [";
      for(int q = 0; q < m_nSlots; q++)
         s += (q > 0 ? ", " : "") + (m_slotCarryHas[q] ? "1" : "0");
      s += "], \"rows_scanned\": " + IntegerToString(m_rowsScanned);
      s += ", \"held_rows\": " + IntegerToString(m_heldRows);
      s += "}";
      return s;
     }

   bool              SetState(const string state)
     {
      CCsTok p;
      p.Init(state);
      if(!p.Lit("{\"seed\": ")) { m_err = p.m_err; return false; }
      m_seed = p.Num();
      if(!p.Lit(", \"seg_start_day\": ")) { m_err = p.m_err; return false; }
      m_segStartDay = p.Int();
      if(!p.Lit(", \"cur_day\": ")) { m_err = p.m_err; return false; }
      m_curDay = p.Int();
      if(!p.Lit(", \"day_open\": ")) { m_err = p.m_err; return false; }
      m_dayOpen = p.Flag();
      if(!p.Lit(", \"leg_val\": [")) { m_err = p.m_err; return false; }
      for(int l = 0; l < m_nLegs; l++)
        {
         if(l > 0 && !p.Lit(", ")) { m_err = p.m_err; return false; }
         m_legVal[l] = p.Num();
        }
      if(!p.Lit("], \"leg_has\": [")) { m_err = p.m_err; return false; }
      for(int l = 0; l < m_nLegs; l++)
        {
         if(l > 0 && !p.Lit(", ")) { m_err = p.m_err; return false; }
         m_legHas[l] = p.Flag();
        }
      if(!p.Lit("], \"slot_day\": [")) { m_err = p.m_err; return false; }
      for(int q = 0; q < m_nSlots; q++)
        {
         if(q > 0 && !p.Lit(", ")) { m_err = p.m_err; return false; }
         m_slotDay[q] = p.Num();
        }
      if(!p.Lit("], \"slot_day_has\": [")) { m_err = p.m_err; return false; }
      for(int q = 0; q < m_nSlots; q++)
        {
         if(q > 0 && !p.Lit(", ")) { m_err = p.m_err; return false; }
         m_slotDayHas[q] = p.Flag();
        }
      if(!p.Lit("], \"slot_carry\": [")) { m_err = p.m_err; return false; }
      for(int q = 0; q < m_nSlots; q++)
        {
         if(q > 0 && !p.Lit(", ")) { m_err = p.m_err; return false; }
         m_slotCarry[q] = p.Num();
        }
      if(!p.Lit("], \"slot_carry_has\": [")) { m_err = p.m_err; return false; }
      for(int q = 0; q < m_nSlots; q++)
        {
         if(q > 0 && !p.Lit(", ")) { m_err = p.m_err; return false; }
         m_slotCarryHas[q] = p.Flag();
        }
      if(!p.Lit("], \"rows_scanned\": ")) { m_err = p.m_err; return false; }
      m_rowsScanned = p.Int();
      if(!p.Lit(", \"held_rows\": ")) { m_err = p.m_err; return false; }
      m_heldRows = p.Int();
      if(!p.Lit("}")) { m_err = p.m_err; return false; }
      if(!p.m_ok) { m_err = p.m_err; return false; }
      m_err = "";
      return true;
     }
  };

#endif // CORE_CORESIGNAL_MQH
