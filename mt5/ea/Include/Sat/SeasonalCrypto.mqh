//+------------------------------------------------------------------+
//| SeasonalCrypto.mqh — FMA3 v34 seasonal (XAUUSD) + crypto_smart   |
//|                      (BTCUSD/ETHUSD/SOLUSD) forward stepper      |
//|                                                                  |
//| 1:1 MQL5 port of the Wave-1 validated Python stepper             |
//|   research/bpure/steppers/consolidate_p1c_stepper.py             |
//| (state-exact vs frozen goldens).  Every constant, branch, guard  |
//| and NaN rule is preserved verbatim; shared recurrences come from |
//| <Sat/SatMath.mqh> (CSatEwmMean / CSatEwmStd / CSatSma /      |
//| SatNpDiv), which are themselves verbatim ports of the same       |
//| Python primitives.                                               |
//|                                                                  |
//| TIMING CONTRACT (deferred emit, == Python step()/finalize()):    |
//|   The golden convention is pos[t] = exposure DECIDED at bar t,   |
//|   held over bar t+1.  Seasonal pos[t] = hold(hour of bar t+1)    |
//|   * w[t]  (hold.shift(-1)), resolved at the OPEN of bar t+1.     |
//|   Step() called with bar t therefore RETURNS the finalized row   |
//|   of bar t-1 (returns false on the very first call), and         |
//|   Finalize() returns the last row with seasonal leg forced 0     |
//|   (shift(-1).fillna(0.0)).  Crypto pos is an asof-ffill of       |
//|   already-finalized daily signals (effective d+1day+08:00 UTC,   |
//|   TRADE_LAG_H=9 => +1d+(9-1)h), buffered one bar to ride along   |
//|   in the same emitted row.                                       |
//|                                                                  |
//| PER-BAR API (union hourly grid, strictly causal):                |
//|   bool Step(datetime bar_time,      // UTC open time of bar t    |
//|             double xau_ret,         // frozen-feed hourly return |
//|                                     // (contract: never NaN)     |
//|             double btc_close,       // ffilled union-grid closes |
//|             double eth_close,       // (NaN before inception)    |
//|             double sol_close,                                    |
//|             long   &emit_ts_ns,     // OUT: ts of EMITTED row    |
//|             double &emit_pos[])     // OUT: [XAU,BTC,ETH,SOL]    |
//|   returns true when a row was emitted (bar t-1's row), false on  |
//|   the first call.  StepNs() is the exact Python-signature core   |
//|   (int64 UTC epoch ns).  Finalize(&ts,&pos) flushes the last     |
//|   row (and closes the still-open server day: its signal queues   |
//|   but never applies, exactly like the pandas daily grid's last   |
//|   row).  Output order == SYMBOLS = XAUUSD,BTCUSD,ETHUSD,SOLUSD.  |
//|                                                                  |
//| STATE (live warm-start): GetState() returns a JSON string with   |
//|   exactly the Python get_state() dict — same keys, same order,   |
//|   NaN/Infinity tokens as produced by json.dumps(..., allow_nan)  |
//|   — and SetState(json) parses that same format, so a state dump  |
//|   from the Python stepper warm-starts this class field-for-field |
//|   (int64 ns timestamps parsed exactly via StringToInteger; the   |
//|   flat-double conventions of sibling sleeves cannot hold ns).    |
//|   Note: python's dict has no `sea_nobs`; on SetState we restore  |
//|   CSatEwmMean.m_nobs = (sea_weighted==sea_weighted) ? 1 : 0,     |
//|   which is exact because minp==1 and xau_ret is never NaN.       |
//|                                                                  |
//| DAILY GRID (crypto): one row per SERVER-calendar day present in  |
//|   the hourly stream with >=1 non-NaN crypto close; per-symbol    |
//|   value = last non-NaN close within the day.  All-NaN calendar   |
//|   days do NOT advance the grid (dropna(how='all')).              |
//+------------------------------------------------------------------+
#ifndef SAT_SEASONALCRYPTO_MQH
#define SAT_SEASONALCRYPTO_MQH

#include <Sat/SatMath.mqh>

//==================================================================//
// frozen params (verbatim from consolidate_p1c_stepper.py)         //
//==================================================================//

const long   Sat_SC_HOUR_NS = 3600000000000;         // HOUR_NS
const long   Sat_SC_DAY_NS  = 86400000000000;        // DAY_NS

// ---- seasonal frozen params (sleeves/seasonal.py) ----------------
const string Sat_SC_SEA_SYMBOL       = "XAUUSD";
const int    Sat_SC_SEA_ENTRY_HOUR   = 23;
const int    Sat_SC_SEA_END_HOUR     = 6;
const double Sat_SC_SEA_KAPPA        = 0.15;
const double Sat_SC_SEA_VOL_FLOOR    = 0.05;
const int    Sat_SC_SEA_SPAN_DAYS    = 30;
const double Sat_SC_SEA_BARS_PER_DAY = 24.0;
const int    Sat_SC_SEA_SPAN         = 720;          // int(30 * 24.0)
const double Sat_SC_SEA_ANN          = 24.0 * 365.25;// SEA_BARS_PER_DAY*365.25

// ---- crypto_smart frozen params (sleeves/crypto_smart.py) --------
const int    Sat_SC_NCR        = 3;
const string Sat_SC_CR_SYMBOLS[3] = {"BTCUSD", "ETHUSD", "SOLUSD"};
const int    Sat_SC_L_MOM      = 28;
const double Sat_SC_Z_LONG     = 0.75;
const double Sat_SC_Z_SHORT    = 0.25;
const double Sat_SC_F_EXIT     = 0.35;
const int    Sat_SC_MA_REGIME  = 120;
const double Sat_SC_VOL_BUDGET = 0.065;
const int    Sat_SC_VOL_SPAN_D = 30;
const double Sat_SC_CAP        = 0.5;
const int    Sat_SC_TRADE_LAG_H = 9;

const string Sat_SC_SYMBOLS[4] = {"XAUUSD", "BTCUSD", "ETHUSD", "SOLUSD"};

//==================================================================//
// JSON helpers (state codec; format == python json.dumps of the    //
// stepper's get_state() dict, allow_nan=True -> NaN / Infinity /   //
// -Infinity bare tokens)                                           //
//==================================================================//

// emit one double as a JSON number token (17 sig digits round-trips
// IEEE-754 binary64 through a correctly-rounded parser)
string SatScJNum(const double x)
  {
   if(x != x)
      return "NaN";
   double inf = SatInf();
   if(x == inf)
      return "Infinity";
   if(x == -inf)
      return "-Infinity";
   return StringFormat("%.17g", x);
  }

// parse one number token (accepts python-json and lowercase forms)
double SatScTokD(const string t)
  {
   if(t == "NaN" || t == "nan")
      return SatNan();
   if(t == "Infinity" || t == "inf")
      return SatInf();
   if(t == "-Infinity" || t == "-inf")
      return -SatInf();
   return StringToDouble(t);
  }

// minimal strict tokenizer over the fixed state schema
class CSatScJsonTok
  {
public:
   string            m_s;
   int               m_i;
   int               m_n;
   bool              m_err;

   void              Init(const string s)
     {
      m_s   = s;
      m_i   = 0;
      m_n   = StringLen(s);
      m_err = false;
     }

   void              Ws()
     {
      while(m_i < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_i);
         if(c == ' ' || c == '\t' || c == '\r' || c == '\n')
            m_i++;
         else
            break;
        }
     }

   bool              Eat(const ushort c)
     {
      Ws();
      if(m_i < m_n && StringGetCharacter(m_s, m_i) == c)
        {
         m_i++;
         return true;
        }
      m_err = true;
      return false;
     }

   bool              TryEat(const ushort c)
     {
      Ws();
      if(m_i < m_n && StringGetCharacter(m_s, m_i) == c)
        {
         m_i++;
         return true;
        }
      return false;
     }

   // quoted key/string (our schema has no escape sequences)
   string            Str()
     {
      Ws();
      if(m_i >= m_n || StringGetCharacter(m_s, m_i) != '"')
        {
         m_err = true;
         return "";
        }
      m_i++;
      int st = m_i;
      while(m_i < m_n && StringGetCharacter(m_s, m_i) != '"')
         m_i++;
      if(m_i >= m_n)
        {
         m_err = true;
         return "";
        }
      string res = StringSubstr(m_s, st, m_i - st);
      m_i++;
      return res;
     }

   // bare token: number / NaN / Infinity / -Infinity / null / true / false
   string            Tok()
     {
      Ws();
      int st = m_i;
      while(m_i < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_i);
         if((c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.'
            || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))
            m_i++;
         else
            break;
        }
      if(m_i == st)
        {
         m_err = true;
         return "";
        }
      return StringSubstr(m_s, st, m_i - st);
     }

   double            D() { return SatScTokD(Tok()); }
   long              L() { return StringToInteger(Tok()); }
  };

// parse a JSON array of numbers into a dynamic double array
bool SatScParseDArr(CSatScJsonTok &tk, double &res[])
  {
   if(!tk.Eat('['))
      return false;
   ArrayResize(res, 0);
   if(tk.TryEat(']'))
      return true;
   while(true)
     {
      int n = ArraySize(res);
      ArrayResize(res, n + 1);
      res[n] = tk.D();
      if(tk.m_err)
         return false;
      if(tk.TryEat(','))
         continue;
      return tk.Eat(']');
     }
   return false;
  }

//==================================================================//
// CSatScCoin — per-coin daily-grid state (== _CoinState):          //
// log-price diffs, EW vol (span 30, minp 30, NaN neg-var flavor),  //
// 120d SMA regime, 3-state hysteresis machine.  Advanced once per  //
// EMITTED daily-grid row.                                          //
//==================================================================//
class CSatScCoin
  {
public:
   // --- serializable state (mirrors python _CoinState slots) ---
   CSatEwmStd        m_ewm;        // _EwmStd(VOL_SPAN_D, VOL_SPAN_D), var<0 -> NaN
   double            m_prev_logp;  // logp of previous grid row
   double            m_logp_ring[];// last <= L_MOM logp values (python list)
   long              m_logp_n;     // rows pushed so far
   CSatSma           m_ma;         // == python ma_ring/head/filled/sum/nan_ct
   int               m_state;
   // --- diagnostics only (not part of python get_state) ---
   double            m_last_sig_d;
   double            m_last_z;
   double            m_last_ma;

                     CSatScCoin() { Init(); }

   void              Init()
     {
      m_ewm.Init(Sat_SC_VOL_SPAN_D, Sat_SC_VOL_SPAN_D, false); // NaN flavor
      m_prev_logp = SatNan();
      ArrayResize(m_logp_ring, 0);
      m_logp_n = 0;
      m_ma.Init(Sat_SC_MA_REGIME);
      m_state = 0;
      m_last_sig_d = SatNan();
      m_last_z     = SatNan();
      m_last_ma    = SatNan();
     }

   // Advance one daily-grid row with this coin's day close (may be NaN).
   // Returns the coin's daily position (state * inverse-vol weight).
   double            StepDay(const double close)
     {
      double logp = (close == close && close > 0.0) ? MathLog(close) : SatNan();
      // lr = logp.diff()
      double lr = (logp == logp && m_prev_logp == m_prev_logp)
                  ? (logp - m_prev_logp) : SatNan();
      m_prev_logp = logp;
      double sig_d = m_ewm.Step(lr);
      // d28 = logp.diff(L_MOM): needs the logp L_MOM rows back (positional)
      double d28;
      if(m_logp_n >= Sat_SC_L_MOM)
        {
         double old0 = m_logp_ring[0];
         d28 = (logp == logp && old0 == old0) ? (logp - old0) : SatNan();
        }
      else
         d28 = SatNan();
      int rn = ArraySize(m_logp_ring);
      ArrayResize(m_logp_ring, rn + 1);
      m_logp_ring[rn] = logp;
      if(rn + 1 > Sat_SC_L_MOM)                    // python list pop(0)
        {
         for(int i = 0; i < rn; i++)
            m_logp_ring[i] = m_logp_ring[i + 1];
         ArrayResize(m_logp_ring, rn);
        }
      m_logp_n++;
      // z = d28 / (sig_d * sqrt(L_MOM)); frozen spec is numpy-vectorized,
      // so a zero divisor yields +-inf (SatNpDiv), never an MQL5 zero-divide.
      double z = (d28 == d28 && sig_d == sig_d)
                 ? SatNpDiv(d28, sig_d * MathSqrt((double)Sat_SC_L_MOM))
                 : SatNan();
      // ma = D.rolling(MA_REGIME, min_periods=MA_REGIME).mean()
      // (CSatSma is the verbatim port of this exact ring+running-sum block)
      double ma = m_ma.Step(close);
      // state machine (verbatim from sleeves/crypto_smart.py make_positions)
      bool ab = (close == close && ma == ma && close > ma);   // D > ma
      bool ok = (SatIsFinite(z) && SatIsFinite(ma));
      int state = m_state;
      if(!ok)
         state = 0;
      else
        {
         if(state == 0)
           {
            if(z >= Sat_SC_Z_LONG)
               state = 1;
            else if(z <= -Sat_SC_Z_SHORT && !ab)
               state = -1;
           }
         else if(state == 1)
           {
            if(z < Sat_SC_F_EXIT * Sat_SC_Z_LONG)
              {
               state = 0;
               if(z <= -Sat_SC_Z_SHORT && !ab)
                  state = -1;
              }
           }
         else // state == -1
           {
            if(z > -Sat_SC_F_EXIT * Sat_SC_Z_SHORT || ab)
              {
               state = 0;
               if(z >= Sat_SC_Z_LONG)
                  state = 1;
              }
           }
        }
      m_state = state;
      // |w| = min(CAP, VOL_BUDGET / (sig_d*sqrt(365))); non-finite -> 0
      double w;
      if(sig_d == sig_d)
        {
         double sig_ann = sig_d * MathSqrt(365.0);
         w = SatNpDiv(Sat_SC_VOL_BUDGET, sig_ann);   // inf if sig_ann == 0
         if(w > Sat_SC_CAP)                          // np.minimum(CAP, inf) == CAP
            w = Sat_SC_CAP;
         if(!SatIsFinite(w))                         // np.where(isfinite(w), w, 0)
            w = 0.0;
        }
      else
         w = 0.0;
      m_last_sig_d = sig_d;
      m_last_z     = z;
      m_last_ma    = ma;
      return((double)state * w);
     }

   // --- JSON state (== python _CoinState.get_state dict, same order) ---
   string            GetStateJson()
     {
      string s = "{\"ewm\": {";
      s += "\"mean\": "     + SatScJNum(m_ewm.m_mean);
      s += ", \"cov\": "    + SatScJNum(m_ewm.m_cov);
      s += ", \"sum_wt\": " + SatScJNum(m_ewm.m_sum_wt);
      s += ", \"sum_wt2\": " + SatScJNum(m_ewm.m_sum_wt2);
      s += ", \"old_wt\": " + SatScJNum(m_ewm.m_old_wt);
      s += ", \"nobs\": "   + IntegerToString(m_ewm.m_nobs) + "}";
      s += ", \"prev_logp\": " + SatScJNum(m_prev_logp);
      s += ", \"logp_ring\": [";
      int rn = ArraySize(m_logp_ring);
      for(int i = 0; i < rn; i++)
         s += (i > 0 ? ", " : "") + SatScJNum(m_logp_ring[i]);
      s += "]";
      s += ", \"logp_n\": " + IntegerToString(m_logp_n);
      s += ", \"ma_ring\": [";
      for(int i = 0; i < m_ma.m_window; i++)
         s += (i > 0 ? ", " : "") + SatScJNum(m_ma.m_buf[i]);
      s += "]";
      s += ", \"ma_head\": "   + IntegerToString(m_ma.m_head);
      s += ", \"ma_filled\": " + IntegerToString(m_ma.m_filled);
      s += ", \"ma_sum\": "    + SatScJNum(m_ma.m_sum);
      s += ", \"ma_nan_ct\": " + IntegerToString(m_ma.m_nan_ct);
      s += ", \"state\": "     + IntegerToString(m_state);
      s += "}";
      return s;
     }

   bool              SetStateJson(CSatScJsonTok &tk)
     {
      Init();
      if(!tk.Eat('{'))
         return false;
      if(tk.TryEat('}'))
         return true;
      while(true)
        {
         string key = tk.Str();
         if(tk.m_err || !tk.Eat(':'))
            return false;
         if(key == "ewm")
           {
            if(!tk.Eat('{'))
               return false;
            while(true)
              {
               string k2 = tk.Str();
               if(tk.m_err || !tk.Eat(':'))
                  return false;
               if(k2 == "mean")         m_ewm.m_mean    = tk.D();
               else if(k2 == "cov")     m_ewm.m_cov     = tk.D();
               else if(k2 == "sum_wt")  m_ewm.m_sum_wt  = tk.D();
               else if(k2 == "sum_wt2") m_ewm.m_sum_wt2 = tk.D();
               else if(k2 == "old_wt")  m_ewm.m_old_wt  = tk.D();
               else if(k2 == "nobs")    m_ewm.m_nobs    = tk.L();
               else
                  return false;
               if(tk.m_err)
                  return false;
               if(tk.TryEat(','))
                  continue;
               if(!tk.Eat('}'))
                  return false;
               break;
              }
           }
         else if(key == "prev_logp")
            m_prev_logp = tk.D();
         else if(key == "logp_ring")
           {
            if(!SatScParseDArr(tk, m_logp_ring))
               return false;
           }
         else if(key == "logp_n")
            m_logp_n = tk.L();
         else if(key == "ma_ring")
           {
            double tmp[];
            if(!SatScParseDArr(tk, tmp))
               return false;
            if(ArraySize(tmp) != m_ma.m_window)
               return false;
            for(int i = 0; i < m_ma.m_window; i++)
               m_ma.m_buf[i] = tmp[i];
           }
         else if(key == "ma_head")
            m_ma.m_head = (int)tk.L();
         else if(key == "ma_filled")
            m_ma.m_filled = (int)tk.L();
         else if(key == "ma_sum")
            m_ma.m_sum = tk.D();
         else if(key == "ma_nan_ct")
            m_ma.m_nan_ct = (int)tk.L();
         else if(key == "state")
            m_state = (int)tk.L();
         else
            return false;
         if(tk.m_err)
            return false;
         if(tk.TryEat(','))
            continue;
         return tk.Eat('}');
        }
      return false;
     }
  };

//==================================================================//
// CSatSeasonalCryptoStepper — == ConsolidateP1cStepper.            //
// Steps XAUUSD + BTCUSD + ETHUSD + SOLUSD together, one hourly bar //
// at a time.  Step() emits the finalized position row for the      //
// PREVIOUS bar (false on the first call); Finalize() emits the     //
// last row.                                                        //
//==================================================================//
class CSatSeasonalCryptoStepper
  {
public:
   // --- seasonal ewm(720) of ret^2, pandas weighted/old_wt form ---
   // CSatEwmMean(span=720, minp=1) IS this recurrence verbatim
   // (m_avg == python _sea_weighted, m_old_wt == _sea_old_wt); the
   // python inline form has no NaN-input branch because xau_ret is
   // never NaN by feed contract (identical on the valid domain).
   CSatEwmMean       m_sea;
   double            m_sea_w;          // w[t] pending hold(hour t+1)
   double            m_sea_vol;        // diagnostic
   // --- crypto daily machinery ---
   CSatScCoin        m_coins[3];       // BTCUSD, ETHUSD, SOLUSD
   bool              m_has_cur_day;    // python: _cur_day is None
   long              m_cur_day;        // day index (ts_ns // DAY_NS)
   double            m_day_last[3];    // last non-NaN close today
   long              m_q_eff[];        // queue: effective ts (ns)
   double            m_q_row[];        // queue: rows, flattened 3 per entry
   double            m_cr_current[3];  // asof value at current bar
   // --- deferred emission ---
   bool              m_have_prev;
   long              m_prev_ts;
   double            m_prev_cr_row[3];

                     CSatSeasonalCryptoStepper() { Init(); }

   void              Init()
     {
      m_sea.Init((double)Sat_SC_SEA_SPAN, 1);
      m_sea_w   = 0.0;
      m_sea_vol = SatNan();
      for(int k = 0; k < Sat_SC_NCR; k++)
        {
         m_coins[k].Init();
         m_day_last[k]    = SatNan();
         m_cr_current[k]  = SatNan();
         m_prev_cr_row[k] = 0.0;
        }
      m_has_cur_day = false;
      m_cur_day     = 0;
      ArrayResize(m_q_eff, 0);
      ArrayResize(m_q_row, 0);
      m_have_prev = false;
      m_prev_ts   = 0;
     }

   //---------------------------------------------------------------
   // main per-bar step (int64 UTC epoch ns == python step signature)
   //---------------------------------------------------------------
   bool              StepNs(const long ts_ns, const double xau_ret,
                            const double btc_close, const double eth_close,
                            const double sol_close,
                            long &emit_ts_ns, double &emit_pos[])
     {
      int hour = (int)((ts_ns / Sat_SC_HOUR_NS) % 24);
      bool emitted = false;
      if(m_have_prev)
        {
         double hold_next = (hour == Sat_SC_SEA_ENTRY_HOUR
                             || hour < Sat_SC_SEA_END_HOUR) ? 1.0 : 0.0;
         ArrayResize(emit_pos, 4);
         emit_pos[0] = hold_next * m_sea_w;
         for(int k = 0; k < Sat_SC_NCR; k++)
            emit_pos[1 + k] = m_prev_cr_row[k];
         emit_ts_ns = m_prev_ts;
         emitted = true;
        }

      // --- crypto: server-day rollover finalizes the previous day ---
      long day_idx = ts_ns / Sat_SC_DAY_NS;
      if(!m_has_cur_day)
        {
         m_cur_day = day_idx;
         m_has_cur_day = true;
        }
      else if(day_idx != m_cur_day)
        {
         FinalizeDay(m_cur_day);
         m_cur_day = day_idx;
        }
      double closes[3];
      closes[0] = btc_close;
      closes[1] = eth_close;
      closes[2] = sol_close;
      for(int k = 0; k < Sat_SC_NCR; k++)
         if(closes[k] == closes[k])
            m_day_last[k] = closes[k];

      // --- crypto: asof-ffill of effective daily targets onto this bar ---
      while(ArraySize(m_q_eff) > 0 && m_q_eff[0] <= ts_ns)
        {
         for(int k = 0; k < Sat_SC_NCR; k++)
            m_cr_current[k] = m_q_row[k];
         QueuePopFront();
        }
      double cr_row[3];
      for(int k = 0; k < Sat_SC_NCR; k++)                     // .fillna(0.0)
         cr_row[k] = (m_cr_current[k] == m_cr_current[k]) ? m_cr_current[k] : 0.0;

      // --- seasonal: ewm(720) var of ret^2, inverse-vol weight ---
      double sq = xau_ret * xau_ret;
      double var = m_sea.Step(sq);                            // == _sea_weighted
      double vol = (var == var) ? MathSqrt(var * Sat_SC_SEA_ANN) : SatNan();
      m_sea_vol = vol;
      if(vol == vol)
        {
         double vc = (vol > Sat_SC_SEA_VOL_FLOOR)
                     ? vol : Sat_SC_SEA_VOL_FLOOR;            // clip(lower)
         double w = Sat_SC_SEA_KAPPA / vc;                    // vc >= 0.05 > 0
         if(w > 1.0)                                          // clip(upper)
            w = 1.0;
         m_sea_w = w;
        }
      else
         m_sea_w = 0.0;                                       // .fillna(0.0)

      // --- defer this bar's row ---
      for(int k = 0; k < Sat_SC_NCR; k++)
         m_prev_cr_row[k] = cr_row[k];
      m_prev_ts   = ts_ns;
      m_have_prev = true;
      return emitted;
     }

   // convenience wrapper: MT5 datetime (UTC epoch seconds) -> ns core
   bool              Step(const datetime bar_time, const double xau_ret,
                          const double btc_close, const double eth_close,
                          const double sol_close,
                          long &emit_ts_ns, double &emit_pos[])
     {
      return StepNs((long)bar_time * 1000000000, xau_ret,
                    btc_close, eth_close, sol_close, emit_ts_ns, emit_pos);
     }

   //---------------------------------------------------------------
   // End of stream: close the still-open server day (its signal
   // queues but never applies), then emit the final bar's row with
   // seasonal leg 0 (hold.shift(-1).fillna(0.0)).
   //---------------------------------------------------------------
   bool              Finalize(long &emit_ts_ns, double &emit_pos[])
     {
      if(!m_have_prev)
         return false;
      if(m_has_cur_day)
        {
         FinalizeDay(m_cur_day);
         m_has_cur_day = false;                               // _cur_day = None
        }
      ArrayResize(emit_pos, 4);
      emit_pos[0] = 0.0;
      for(int k = 0; k < Sat_SC_NCR; k++)
         emit_pos[1 + k] = m_prev_cr_row[k];
      emit_ts_ns = m_prev_ts;
      m_have_prev = false;
      return true;
     }

   //---------------------------------------------------------------
   // GetState / SetState — JSON string, keys/order == python
   // get_state() dict (round-trips json.dumps(..., allow_nan=True))
   //---------------------------------------------------------------
   string            GetState()
     {
      string s = "{";
      s += "\"sea_weighted\": " + SatScJNum(m_sea.m_avg);
      s += ", \"sea_old_wt\": " + SatScJNum(m_sea.m_old_wt);
      s += ", \"sea_w\": "      + SatScJNum(m_sea_w);
      s += ", \"coins\": {";
      for(int k = 0; k < Sat_SC_NCR; k++)
         s += (k > 0 ? ", " : "") + "\"" + Sat_SC_CR_SYMBOLS[k] + "\": "
              + m_coins[k].GetStateJson();
      s += "}";
      s += ", \"cur_day\": " + (m_has_cur_day ? IntegerToString(m_cur_day)
                                              : "null");
      s += ", \"day_last\": {";
      for(int k = 0; k < Sat_SC_NCR; k++)
         s += (k > 0 ? ", " : "") + "\"" + Sat_SC_CR_SYMBOLS[k] + "\": "
              + SatScJNum(m_day_last[k]);
      s += "}";
      s += ", \"queue\": [";
      int qn = ArraySize(m_q_eff);
      for(int i = 0; i < qn; i++)
        {
         s += (i > 0 ? ", " : "") + "[" + IntegerToString(m_q_eff[i]) + ", ["
              + SatScJNum(m_q_row[3 * i])     + ", "
              + SatScJNum(m_q_row[3 * i + 1]) + ", "
              + SatScJNum(m_q_row[3 * i + 2]) + "]]";
        }
      s += "]";
      s += ", \"cr_current\": ["
           + SatScJNum(m_cr_current[0]) + ", "
           + SatScJNum(m_cr_current[1]) + ", "
           + SatScJNum(m_cr_current[2]) + "]";
      s += ", \"have_prev\": ";
      s += (m_have_prev ? "true" : "false");
      s += ", \"prev_ts\": " + IntegerToString(m_prev_ts);
      s += ", \"prev_cr_row\": ["
           + SatScJNum(m_prev_cr_row[0]) + ", "
           + SatScJNum(m_prev_cr_row[1]) + ", "
           + SatScJNum(m_prev_cr_row[2]) + "]";
      s += "}";
      return s;
     }

   bool              SetState(const string json)
     {
      Init();
      CSatScJsonTok tk;
      tk.Init(json);
      if(!tk.Eat('{'))
         return false;
      while(true)
        {
         string key = tk.Str();
         if(tk.m_err || !tk.Eat(':'))
            return false;
         if(key == "sea_weighted")
           {
            m_sea.m_avg  = tk.D();
            // python state carries no nobs; exact because minp==1 and
            // the seasonal input (ret^2) is never NaN by feed contract
            m_sea.m_nobs = (m_sea.m_avg == m_sea.m_avg) ? 1 : 0;
           }
         else if(key == "sea_old_wt")
            m_sea.m_old_wt = tk.D();
         else if(key == "sea_w")
            m_sea_w = tk.D();
         else if(key == "coins")
           {
            if(!tk.Eat('{'))
               return false;
            while(true)
              {
               string sym = tk.Str();
               if(tk.m_err || !tk.Eat(':'))
                  return false;
               int idx = -1;
               for(int k = 0; k < Sat_SC_NCR; k++)
                  if(sym == Sat_SC_CR_SYMBOLS[k])
                     idx = k;
               if(idx < 0)
                  return false;
               if(!m_coins[idx].SetStateJson(tk))
                  return false;
               if(tk.TryEat(','))
                  continue;
               if(!tk.Eat('}'))
                  return false;
               break;
              }
           }
         else if(key == "cur_day")
           {
            string t = tk.Tok();
            if(tk.m_err)
               return false;
            if(t == "null")
              {
               m_has_cur_day = false;
               m_cur_day = 0;
              }
            else
              {
               m_has_cur_day = true;
               m_cur_day = StringToInteger(t);
              }
           }
         else if(key == "day_last")
           {
            if(!tk.Eat('{'))
               return false;
            while(true)
              {
               string sym = tk.Str();
               if(tk.m_err || !tk.Eat(':'))
                  return false;
               int idx = -1;
               for(int k = 0; k < Sat_SC_NCR; k++)
                  if(sym == Sat_SC_CR_SYMBOLS[k])
                     idx = k;
               if(idx < 0)
                  return false;
               m_day_last[idx] = tk.D();
               if(tk.m_err)
                  return false;
               if(tk.TryEat(','))
                  continue;
               if(!tk.Eat('}'))
                  return false;
               break;
              }
           }
         else if(key == "queue")
           {
            if(!tk.Eat('['))
               return false;
            ArrayResize(m_q_eff, 0);
            ArrayResize(m_q_row, 0);
            if(!tk.TryEat(']'))
              {
               while(true)
                 {
                  if(!tk.Eat('['))
                     return false;
                  long eff = tk.L();
                  if(tk.m_err || !tk.Eat(','))
                     return false;
                  double row[];
                  if(!SatScParseDArr(tk, row))
                     return false;
                  if(ArraySize(row) != 3)
                     return false;
                  if(!tk.Eat(']'))
                     return false;
                  QueuePush(eff, row);
                  if(tk.TryEat(','))
                     continue;
                  if(!tk.Eat(']'))
                     return false;
                  break;
                 }
              }
           }
         else if(key == "cr_current")
           {
            double a[];
            if(!SatScParseDArr(tk, a) || ArraySize(a) != 3)
               return false;
            for(int k = 0; k < Sat_SC_NCR; k++)
               m_cr_current[k] = a[k];
           }
         else if(key == "have_prev")
           {
            string t = tk.Tok();
            if(t == "true")
               m_have_prev = true;
            else if(t == "false")
               m_have_prev = false;
            else
               return false;
           }
         else if(key == "prev_ts")
            m_prev_ts = tk.L();
         else if(key == "prev_cr_row")
           {
            double a[];
            if(!SatScParseDArr(tk, a) || ArraySize(a) != 3)
               return false;
            for(int k = 0; k < Sat_SC_NCR; k++)
               m_prev_cr_row[k] = a[k];
           }
         else
            return false;
         if(tk.m_err)
            return false;
         if(tk.TryEat(','))
            continue;
         return tk.Eat('}');
        }
      return false;
     }

private:
   //---------------------------------------------------------------
   // Close the just-ended server day.  Emits a daily-grid row only
   // if any coin had a non-NaN close (== dropna(how='all')).
   //---------------------------------------------------------------
   void              FinalizeDay(const long day_idx)
     {
      bool anyv = false;
      for(int k = 0; k < Sat_SC_NCR; k++)
         if(m_day_last[k] == m_day_last[k])
            anyv = true;
      if(anyv)
        {
         double row[3];
         for(int k = 0; k < Sat_SC_NCR; k++)
            row[k] = m_coins[k].StepDay(m_day_last[k]);
         long eff = day_idx * Sat_SC_DAY_NS + Sat_SC_DAY_NS
                    + (long)(Sat_SC_TRADE_LAG_H - 1) * Sat_SC_HOUR_NS;
         QueuePush(eff, row);
        }
      for(int k = 0; k < Sat_SC_NCR; k++)
         m_day_last[k] = SatNan();
     }

   void              QueuePush(const long eff, const double &row[])
     {
      int n = ArraySize(m_q_eff);
      ArrayResize(m_q_eff, n + 1);
      ArrayResize(m_q_row, 3 * (n + 1));
      m_q_eff[n] = eff;
      for(int k = 0; k < Sat_SC_NCR; k++)
         m_q_row[3 * n + k] = row[k];
     }

   void              QueuePopFront()
     {
      int n = ArraySize(m_q_eff);
      for(int i = 1; i < n; i++)
        {
         m_q_eff[i - 1] = m_q_eff[i];
         for(int k = 0; k < Sat_SC_NCR; k++)
            m_q_row[3 * (i - 1) + k] = m_q_row[3 * i + k];
        }
      ArrayResize(m_q_eff, n - 1);
      ArrayResize(m_q_row, 3 * (n - 1));
     }
  };

#endif // SAT_SEASONALCRYPTO_MQH
