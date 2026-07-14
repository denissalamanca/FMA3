//+------------------------------------------------------------------+
//| CarryBreakout.mqh — FMA3 v34 carry_breakout sleeve stepper       |
//|                                                                  |
//| 1:1 MQL5 port of the Wave-1 validated Python stepper             |
//|   research/bpure/steppers/carry_breakout_stepper.py              |
//| (state-exact vs frozen goldens; see research/bpure/parity/       |
//| carry_breakout_parity.json).  Every constant, branch, guard and  |
//| NaN rule is preserved verbatim.                                  |
//|                                                                  |
//| TWO BOOKS stepped together each union hourly bar:                |
//|  (A) CARRY (daily, 21 FX): policy-rate differential step tables  |
//|      (embedded below, byte-for-byte = parse_policy_rates(        |
//|      engine_costs.POLICY_RATES), 10 ccys / 178 rows), net =      |
//|      |diff| - 1.2, direction where net > 0.5, cross-sectional    |
//|      DESCENDING rank with pandas 'average' tie method keep <= 5, |
//|      63-row momentum gate on the daily grid, w = sig*0.02 /      |
//|      max(vol30_daily, 0.05), NaN -> 0.  Signal is stamped at the |
//|      completed day P on the FIRST bar of the next grid day and   |
//|      applied from that bar on (core.to_hourly lag_hours=1).      |
//|  (B) BREAKOUT (hourly, long-only Donchian ensemble, 11 BK_UNIV): |
//|      fast 480/exit 192, slow 960/exit 384 prior-window rolling   |
//|      extremes (shift 1, min_periods=n), chandelier exit at       |
//|      best_close_since_entry - 3*ATR with ATR = ewm(|dclose|,     |
//|      span=480).mean()*24, size FROZEN at entry =                 |
//|      min(0.02/max(vol30,0.05), 1); bars with no real bar or NaN  |
//|      hi/ATR hold the position unchanged; ensemble = (f+s)/2.     |
//| COMBINE: pos = carry*1.35 + breakout*2.05; gross cap 3.0 (scale  |
//|      by min(1, 3/gross), |pos| summed in FX-then-BK_UNIV order — |
//|      summation order preserved for bit-parity); clip [-1, 1].    |
//|                                                                  |
//| PER-BAR API (mirrors CarryBreakoutStepper.step):                 |
//|   CSatCarryBreakoutStepper st;                // Init() implied  |
//|   st.Step(epoch_day, closes, pos);                               |
//|     epoch_day : integer days since 1970-01-01 of the bar's       |
//|                 SERVER timestamp (floor)                         |
//|     closes[32]: raw hourly closes in SATCB_SYMBOLS order         |
//|                 (FX[21] then BK_UNIV[11]), NaN where the symbol  |
//|                 has no bar this hour                             |
//|     pos[32]   : OUT, final target positions after gross cap+clip |
//|   st.StepAt(dt, closes, pos)  — same, epoch_day = (long)dt/86400 |
//| Timing contract: on the first bar of a new epoch day the carry   |
//| signal for the COMPLETED day is computed from state as of the    |
//| previous bar and applied from this bar on (causal, no lookahead).|
//|                                                                  |
//| STATE (live warm-start): GetState() returns a JSON string that   |
//| mirrors the Python get_state() dict FIELD-FOR-FIELD (same keys,  |
//| same nesting, NaN/Infinity literals as emitted by json.dumps     |
//| with allow_nan=True).  SetState() parses the same format, so a   |
//| state produced by the Python stepper (json.dumps(st.get_state()))|
//| loads directly here and vice versa (json.loads -> set_state).    |
//|                                                                  |
//| NUMERIC CAVEAT (SatMath header): pandas' ewma kernel uses an     |
//| ARM64 fmadd; MQL5 has no fma, so the two ewm recurrences         |
//| (vol30, ATR) reproduce to ~1e-16 RELATIVE instead of bit-exact.  |
//| Everything else (Donchian states, rank, gate, cap, clip) is      |
//| bit-exact by construction.                                       |
//|                                                                  |
//| Input contract (same as Python): closes are prices > 0 or NaN.   |
//| The two divisions that Python would crash on for a 0.0 price     |
//| (pct_change, momentum) are guarded to NaN here because MQL5      |
//| raises a fatal "zero divide" even for doubles; the guards are    |
//| unreachable when the contract holds.                             |
//+------------------------------------------------------------------+
#ifndef SAT_CARRYBREAKOUT_MQH
#define SAT_CARRYBREAKOUT_MQH

#include <Sat/SatMath.mqh>

//==================================================================//
// frozen parameters / calibration constants (carry_breakout.py)    //
//==================================================================//
#define SATCB_N_FX        21
#define SATCB_N_BK        11
#define SATCB_N_SYM       32
#define SATCB_N_CCY       10
#define SATCB_N_RATE      178
#define SATCB_GATE_DAYS   63
#define SATCB_DC_CAP      64          // GATE_DAYS + 1
#define SATCB_VOL_SPAN_BARS 720       // 30d * 24
#define SATCB_ATR_SPAN_BARS 480       // 20d * 24
#define SATCB_N_FAST_BARS 480         // 20d * 24
#define SATCB_N_SLOW_BARS 960         // 40d * 24
#define SATCB_X_FAST_BARS 192         // max(5, round(0.4*20)) * 24
#define SATCB_X_SLOW_BARS 384         // max(5, round(0.4*40)) * 24

const double SATCB_SWAP_MARKUP  = 1.2;
const double SATCB_RISK_PER_POS = 0.02;
const double SATCB_VOL_FLOOR    = 0.05;
const double SATCB_W_CARRY      = 1.35;
const double SATCB_W_BK         = 2.05;
const double SATCB_GROSS_CAP    = 3.0;
const double SATCB_CARRY_THR    = 0.5;
const int    SATCB_TOP_K        = 5;
const double SATCB_M_ATR        = 3.0;

//==================================================================//
// universe (source order — CARRY_UNIV == core.FX, BK_UNIV literal) //
//==================================================================//
const string SATCB_SYMBOLS[SATCB_N_SYM] =
  {
   "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
   "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
   "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY",
   "XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD", "XNGUSD",
   "DAX", "JP225", "UK100", "US30", "USA500", "USTEC"
  };

//==================================================================//
// policy-rate step tables — EXACT copy of parse_policy_rates(      //
// engine_costs.POLICY_RATES): 3-letter non-metal ccys only, rows   //
// sorted, day = date.toordinal() - 719163 (days since 1970-01-01). //
// Verified equal to the Python parse (10 ccys, 178 rows).          //
//==================================================================//
const string SATCB_CCY[SATCB_N_CCY] =
   {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "NOK", "SEK"};
const int    SATCB_RATE_OFF[SATCB_N_CCY + 1] =
   {0, 20, 38, 61, 65, 77, 97, 120, 141, 161, 178};
const int    SATCB_RATE_DAY[SATCB_N_RATE] =
  {
    18201, 18324, 18336, 19068, 19117, 19159, 19201, 19257,
    19299, 19341, 19390, 19439, 19481, 19565, 19985, 20035,
    20076, 20349, 20391, 20433, 18157, 19200, 19249, 19298,
    19347, 19396, 19438, 19487, 19529, 19620, 19886, 19984,
    20019, 20075, 20124, 20159, 20201, 20250, 18201, 18332,
    18340, 18977, 19026, 19068, 19117, 19159, 19208, 19257,
    19299, 19341, 19390, 19439, 19488, 19530, 19572, 19936,
    20034, 20125, 20216, 20307, 20440, 18201, 19801, 19935,
    20112, 18201, 19159, 19257, 19341, 19439, 19530, 19803,
    19894, 19992, 20069, 20167, 20258, 18201, 18324, 18340,
    18569, 19115, 19150, 19178, 19206, 19241, 19269, 19297,
    19332, 19395, 19423, 19479, 19514, 19668, 20137, 20228,
    20312, 18201, 18337, 18906, 18955, 19046, 19095, 19137,
    19186, 19221, 19270, 19319, 19410, 19452, 19501, 19949,
    20005, 20054, 20138, 20187, 20236, 20320, 20369, 20418,
    18201, 18325, 18337, 18348, 19053, 19095, 19144, 19186,
    19242, 19291, 19333, 19382, 19515, 19550, 19879, 19928,
    19970, 20019, 20068, 20117, 20159, 18201, 18334, 18341,
    18389, 18894, 18978, 19075, 19166, 19222, 19257, 19299,
    19341, 19439, 19481, 19530, 19586, 19621, 19705, 20258,
    20349, 18201, 18269, 19116, 19179, 19256, 19326, 19397,
    19473, 19543, 19621, 19851, 19955, 19991, 20034, 20076,
    20117, 20257
  };
const double SATCB_RATE_VAL[SATCB_N_RATE] =
  {
    1.625, 1.125, 0.125, 0.375, 0.875, 1.625, 2.375, 3.125,
    3.875, 4.375, 4.625, 4.875, 5.125, 5.375, 4.875, 4.625,
    4.375, 4.125, 3.875, 3.625, -0.500, 0.000, 0.750, 1.500,
    2.000, 2.500, 3.000, 3.250, 3.500, 4.000, 3.750, 3.500,
    3.250, 3.000, 2.750, 2.500, 2.250, 2.000, 0.750, 0.250,
    0.100, 0.250, 0.500, 0.750, 1.000, 1.250, 1.750, 2.250,
    3.000, 3.500, 4.000, 4.250, 4.500, 5.000, 5.250, 5.000,
    4.750, 4.500, 4.250, 4.000, 3.750, -0.100, 0.100, 0.250,
    0.500, -0.750, -0.250, 0.500, 1.000, 1.500, 1.750, 1.500,
    1.250, 1.000, 0.500, 0.250, 0.000, 0.750, 0.500, 0.250,
    0.100, 0.350, 0.850, 1.350, 1.850, 2.350, 2.600, 2.850,
    3.100, 3.350, 3.600, 3.850, 4.100, 4.350, 4.100, 3.850,
    3.600, 1.000, 0.250, 0.500, 0.750, 1.000, 1.500, 2.000,
    2.500, 3.000, 3.500, 4.250, 4.750, 5.250, 5.500, 5.250,
    4.750, 4.250, 3.750, 3.500, 3.250, 3.000, 2.500, 2.250,
    1.750, 1.250, 0.750, 0.250, 0.500, 1.000, 1.500, 2.500,
    3.250, 3.750, 4.250, 4.500, 4.750, 5.000, 4.750, 4.500,
    4.250, 3.750, 3.250, 3.000, 2.750, 1.500, 1.000, 0.250,
    0.000, 0.250, 0.500, 0.750, 1.250, 1.750, 2.250, 2.500,
    2.750, 3.000, 3.250, 3.750, 4.000, 4.250, 4.500, 4.250,
    4.000, -0.250, 0.000, 0.250, 0.750, 1.750, 2.500, 3.000,
    3.500, 3.750, 4.000, 3.750, 3.500, 3.250, 2.750, 2.500,
    2.250, 2.000
  };

//==================================================================//
// JSON number literal (json.dumps allow_nan=True compatible)       //
//==================================================================//
string SatCbJsonNum(const double x)
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

//==================================================================//
// CSatCbJsonReader — minimal cursor parser for the state schema    //
// (objects / arrays / strings without escapes / numbers incl.      //
// NaN, Infinity, -Infinity / null).  Whitespace-tolerant, so it    //
// reads both our own writer output and Python json.dumps output.   //
//==================================================================//
class CSatCbJsonReader
  {
public:
   string            m_s;
   int               m_i;
   int               m_n;
   bool              m_err;

   void              Attach(const string s)
     {
      m_s = s;
      m_i = 0;
      m_n = StringLen(s);
      m_err = false;
     }

   void              SkipWs()
     {
      while(m_i < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_i);
         if(c == ' ' || c == '\t' || c == '\n' || c == '\r')
            m_i++;
         else
            break;
        }
     }

   bool              Expect(const ushort ch)
     {
      SkipWs();
      if(m_i < m_n && StringGetCharacter(m_s, m_i) == ch)
        {
         m_i++;
         return true;
        }
      m_err = true;
      return false;
     }

   bool              TryChar(const ushort ch)
     {
      SkipWs();
      if(m_i < m_n && StringGetCharacter(m_s, m_i) == ch)
        {
         m_i++;
         return true;
        }
      return false;
     }

   bool              TryMatch(const string tok)
     {
      SkipWs();
      int len = StringLen(tok);
      if(m_i + len <= m_n && StringSubstr(m_s, m_i, len) == tok)
        {
         m_i += len;
         return true;
        }
      return false;
     }

   bool              ParseString(string &val)
     {
      if(!Expect('"'))
         return false;
      int start = m_i;
      while(m_i < m_n && StringGetCharacter(m_s, m_i) != '"')
        {
         if(StringGetCharacter(m_s, m_i) == '\\')
            m_i++;                    // schema has no escapes; skip defensively
         m_i++;
        }
      if(m_i >= m_n)
        {
         m_err = true;
         return false;
        }
      val = StringSubstr(m_s, start, m_i - start);
      m_i++;
      return true;
     }

   bool              ParseNumber(double &val)
     {
      SkipWs();
      if(TryMatch("NaN"))         { val = SatNan();  return true; }
      if(TryMatch("Infinity"))    { val = SatInf();  return true; }
      if(TryMatch("-Infinity"))   { val = -SatInf(); return true; }
      int start = m_i;
      while(m_i < m_n)
        {
         ushort c = StringGetCharacter(m_s, m_i);
         if((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.'
            || c == 'e' || c == 'E')
            m_i++;
         else
            break;
        }
      if(m_i == start)
        {
         m_err = true;
         return false;
        }
      val = StringToDouble(StringSubstr(m_s, start, m_i - start));
      return true;
     }

   bool              ParseLong(long &val)
     {
      double d;
      if(!ParseNumber(d))
         return false;
      val = (long)d;
      return true;
     }
  };

//==================================================================//
// CSatCbDonchianSys — one long-only Donchian state machine.        //
// Exact port of carry_breakout_stepper._DonchianSystem: state in   //
// {0,1}, size FROZEN at entry, chandelier best-close trail.        //
//==================================================================//
class CSatCbDonchianSys
  {
public:
   // --- serializable state (Python snap(): [state, size, best]) ---
   int               m_state;
   double            m_size;
   double            m_best;

                     CSatCbDonchianSys() { Reset(); }

   void              Reset()
     {
      m_state = 0;
      m_size  = 0.0;
      m_best  = SatNan();
     }

   // returns position = state*size AFTER processing this bar
   double            Step(const bool has_bar, const double c, const double hi,
                          const double xlo, const double atr, const double vol)
     {
      if(!has_bar || hi != hi || atr != atr)
         return m_state * m_size;
      if(m_state == 0)
        {
         if(c > hi)
           {
            m_state = 1;
            m_best  = c;
            // min(RISK_PER_POS / max(vol, VOL_FLOOR), 1.0) with Python
            // builtin max/min NaN semantics (NaN first arg is kept)
            double mv = vol;
            if(SATCB_VOL_FLOOR > mv)
               mv = SATCB_VOL_FLOOR;
            double sz = SATCB_RISK_PER_POS / mv;   // mv >= 0.05 or NaN: safe
            if(1.0 < sz)
               sz = 1.0;
            m_size = sz;
           }
        }
      else
        {
         if(m_best < c)                 // best = max(best, c) (NaN-free here)
            m_best = c;
         if((xlo == xlo && c < xlo) || c < m_best - SATCB_M_ATR * atr)
           {
            m_state = 0;
            m_size  = 0.0;
           }
        }
      return m_state * m_size;
     }
  };

//==================================================================//
// CSatCarryBreakoutStepper — steps ALL 32 sleeve symbols together, //
// one union hourly bar per call.  See file header for the API and  //
// state contract.                                                  //
//==================================================================//
class CSatCarryBreakoutStepper
  {
public:
   // --- serializable state (mirrors Python get_state field-for-field) ---
   long              m_bar_i;
   bool              m_has_cur_day;              // Python cur_day is None
   long              m_cur_day;
   double            m_c_ff[SATCB_N_SYM];        // ffilled closes
   CSatEwmMean       m_vol_ewm[SATCB_N_SYM];     // span 720
   bool              m_vol_started[SATCB_N_SYM]; // Python _Ewm.started
   CSatEwmMean       m_atr_ewm[SATCB_N_BK];      // span 480
   bool              m_atr_started[SATCB_N_BK];
   CSatDonchian      m_win_hi_f[SATCB_N_BK];     // 480 max
   CSatDonchian      m_win_hi_s[SATCB_N_BK];     // 960 max
   CSatDonchian      m_win_lo_f[SATCB_N_BK];     // 192 min
   CSatDonchian      m_win_lo_s[SATCB_N_BK];     // 384 min
   CSatCbDonchianSys m_sys_f[SATCB_N_BK];
   CSatCbDonchianSys m_sys_s[SATCB_N_BK];
   double            m_dc_hist[SATCB_DC_CAP][SATCB_N_FX];
   int               m_dc_len;                   // <= 64 daily FX close rows
   double            m_w_eff[SATCB_N_FX];        // effective carry w (pre 1.35)

   // --- derived (rebuilt by Init, not serialized) ---
   int               m_pair_base[SATCB_N_FX];    // ccy index of s[:3]
   int               m_pair_quote[SATCB_N_FX];   // ccy index of s[3:]

   // --- debug capture of the most recent carry roll (NOT state) ---
   bool              m_last_valid;
   long              m_last_day;
   double            m_last_net[SATCB_N_FX];
   double            m_last_dir[SATCB_N_FX];
   double            m_last_sig[SATCB_N_FX];
   double            m_last_w[SATCB_N_FX];

                     CSatCarryBreakoutStepper() { Init(); }

   void              Init()
     {
      double nan = SatNan();
      for(int j = 0; j < SATCB_N_SYM; j++)
        {
         m_c_ff[j] = nan;
         m_vol_ewm[j].Init((double)SATCB_VOL_SPAN_BARS, 1);
         m_vol_started[j] = false;
        }
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         m_atr_ewm[k].Init((double)SATCB_ATR_SPAN_BARS, 1);
         m_atr_started[k] = false;
         m_win_hi_f[k].Init(SATCB_N_FAST_BARS, true);
         m_win_hi_s[k].Init(SATCB_N_SLOW_BARS, true);
         m_win_lo_f[k].Init(SATCB_X_FAST_BARS, false);
         m_win_lo_s[k].Init(SATCB_X_SLOW_BARS, false);
         m_sys_f[k].Reset();
         m_sys_s[k].Reset();
        }
      m_has_cur_day = false;
      m_cur_day = 0;
      m_dc_len = 0;
      for(int j = 0; j < SATCB_N_FX; j++)
        {
         m_w_eff[j] = 0.0;
         m_pair_base[j]  = CcyIndex(StringSubstr(SATCB_SYMBOLS[j], 0, 3));
         m_pair_quote[j] = CcyIndex(StringSubstr(SATCB_SYMBOLS[j], 3, 3));
         m_last_net[j] = nan;
         m_last_dir[j] = 0.0;
         m_last_sig[j] = 0.0;
         m_last_w[j] = 0.0;
        }
      m_bar_i = 0;
      m_last_valid = false;
      m_last_day = 0;
     }

   //---------------------------------------------------------------//
   // policy rate step lookup: last row with row.day <= day, NaN     //
   // before the first row (exact port of _rate binary search)       //
   //---------------------------------------------------------------//
   double            Rate(const int ccy, const long day) const
     {
      if(ccy < 0)
         return SatNan();
      int lo = SATCB_RATE_OFF[ccy];
      int hi = SATCB_RATE_OFF[ccy + 1];
      if(lo >= hi || SATCB_RATE_DAY[lo] > day)
         return SatNan();
      while(hi - lo > 1)
        {
         int mid = (lo + hi) / 2;
         if(SATCB_RATE_DAY[mid] <= day)
            lo = mid;
         else
            hi = mid;
        }
      return SATCB_RATE_VAL[lo];
     }

   //---------------------------------------------------------------//
   // one union hourly bar (exact port of step())                    //
   //---------------------------------------------------------------//
   void              Step(const long epoch_day, const double &closes[],
                          double &pos[])
     {
      if(m_has_cur_day && epoch_day != m_cur_day)
         RollDay(m_cur_day);
      m_has_cur_day = true;
      m_cur_day = epoch_day;

      for(int j = 0; j < SATCB_N_SYM; j++)
        {
         double raw  = closes[j];
         bool   has  = (raw == raw);
         double prev = m_c_ff[j];
         double c    = has ? raw : prev;
         // ret: 0 where prev ffilled close is NaN; clip +-0.30
         double r;
         if(prev != prev)
            r = 0.0;
         else if(prev == 0.0)
            r = SatNan();       // unreachable per contract (see file header)
         else
           {
            r = c / prev - 1.0;
            if(r > 0.30)
               r = 0.30;
            else if(r < -0.30)
               r = -0.30;
           }
         m_c_ff[j] = c;
         m_vol_ewm[j].Step(r * r);
         m_vol_started[j] = true;

         if(j < SATCB_N_FX)
           {
            pos[j] = m_w_eff[j] * SATCB_W_CARRY;
            continue;
           }

         // ---- breakout symbol ----
         int k = j - SATCB_N_FX;
         double d = c - prev;               // close.diff(): NaN propagates
         m_atr_ewm[k].Step((d == d) ? MathAbs(d) : SatNan());
         m_atr_started[k] = true;
         double av  = m_atr_ewm[k].Value();
         double atr = (av == av) ? av * 24.0 : SatNan();
         double vv  = m_vol_ewm[j].Value();
         double vol = MathSqrt((vv * 24.0) * 365.25);   // NaN -> NaN

         double hi_f  = m_win_hi_f[k].Query();
         double hi_s  = m_win_hi_s[k].Query();
         double xlo_f = m_win_lo_f[k].Query();
         double xlo_s = m_win_lo_s[k].Query();

         double of  = m_sys_f[k].Step(has, c, hi_f, xlo_f, atr, vol);
         double osl = m_sys_s[k].Step(has, c, hi_s, xlo_s, atr, vol);
         pos[j] = ((of + osl) / 2.0) * SATCB_W_BK;

         m_win_hi_f[k].Push(c);
         m_win_hi_s[k].Push(c);
         m_win_lo_f[k].Push(c);
         m_win_lo_s[k].Push(c);
        }

      // sleeve gross cap + unit clip (|pos| summed FX-then-BK order)
      double gross = 0.0;
      for(int j = 0; j < SATCB_N_SYM; j++)
         gross += MathAbs(pos[j]);
      double scale = (gross > 0.0) ? SATCB_GROSS_CAP / gross : 1.0;
      if(scale > 1.0)
         scale = 1.0;
      for(int j = 0; j < SATCB_N_SYM; j++)
        {
         double p = pos[j] * scale;
         if(p > 1.0)
            p = 1.0;
         else if(p < -1.0)
            p = -1.0;
         pos[j] = p;
        }
      m_bar_i++;
     }

   // convenience wrapper: server datetime -> epoch day (floor; server
   // timestamps are seconds since 1970-01-01, always >= 0 here)
   void              StepAt(const datetime t, const double &closes[],
                            double &pos[])
     {
      Step((long)t / 86400, closes, pos);
     }

   //---------------------------------------------------------------//
   // carry daily roll — signal stamped at completed day P           //
   // (exact port of _roll_day)                                      //
   //---------------------------------------------------------------//
   void              RollDay(const long day_p)
     {
      double dc_row[SATCB_N_FX];
      for(int j = 0; j < SATCB_N_FX; j++)
         dc_row[j] = m_c_ff[j];

      // dc_hist.append(dc_row); trim to GATE_DAYS+1 rows
      int row;
      if(m_dc_len == SATCB_DC_CAP)
        {
         for(int r = 0; r < SATCB_DC_CAP - 1; r++)
            for(int j = 0; j < SATCB_N_FX; j++)
               m_dc_hist[r][j] = m_dc_hist[r + 1][j];
         row = SATCB_DC_CAP - 1;
        }
      else
        {
         row = m_dc_len;
         m_dc_len++;
        }
      for(int j = 0; j < SATCB_N_FX; j++)
         m_dc_hist[row][j] = dc_row[j];

      double direction[SATCB_N_FX];
      double net[SATCB_N_FX];
      for(int j = 0; j < SATCB_N_FX; j++)
        {
         double d = Rate(m_pair_base[j], day_p) - Rate(m_pair_quote[j], day_p);
         double n = MathAbs(d) - SATCB_SWAP_MARKUP;   // fabs(NaN) = NaN
         net[j] = n;
         direction[j] = 0.0;
         if(n > SATCB_CARRY_THR)                      // false for NaN
            direction[j] = SatSign(d);
        }

      // cross-sectional descending rank, 'average' ties, keep <= TOP_K
      // (stable insertion sort == Python stable list.sort(key=-net))
      double lv_net[SATCB_N_FX];
      int    lv_j[SATCB_N_FX];
      int    n_live = 0;
      for(int j = 0; j < SATCB_N_FX; j++)
        {
         if(direction[j] == 0.0)
            continue;
         int p = n_live;
         while(p > 0 && lv_net[p - 1] < net[j])
           {
            lv_net[p] = lv_net[p - 1];
            lv_j[p]   = lv_j[p - 1];
            p--;
           }
         lv_net[p] = net[j];
         lv_j[p]   = j;
         n_live++;
        }
      int i = 0;
      while(i < n_live)
        {
         int k2 = i;
         while(k2 < n_live && lv_net[k2] == lv_net[i])
            k2++;
         double rk = (i + 1 + k2) / 2.0;
         if(rk > SATCB_TOP_K)
           {
            for(int m = i; m < k2; m++)
               direction[lv_j[m]] = 0.0;
           }
         i = k2;
        }

      // momentum gate: row-shift GATE_DAYS on the daily grid
      bool have63 = (m_dc_len > SATCB_GATE_DAYS);
      double sig[SATCB_N_FX];
      for(int j = 0; j < SATCB_N_FX; j++)
        {
         sig[j] = 0.0;
         if(direction[j] == 0.0)
            continue;
         double mom = SatNan();
         if(have63)
           {
            double denom = m_dc_hist[0][j];   // dc_hist[-(GATE_DAYS+1)]
            if(denom == 0.0)
               mom = SatNan();  // unreachable per contract (Python raises)
            else
               mom = dc_row[j] / denom - 1.0;
           }
         if(SatSign(mom) == direction[j])     // NaN == x is false
            sig[j] = direction[j];
        }

      for(int j = 0; j < SATCB_N_FX; j++)
        {
         double v = m_vol_ewm[j].Value();     // vol at day P's last bar
         double vol_d = (v == v) ? MathSqrt((v * 24.0) * 365.25) : SatNan();
         if(vol_d < SATCB_VOL_FLOOR)          // pandas clip(lower=): NaN kept
            vol_d = SATCB_VOL_FLOOR;
         double wj = sig[j] * SATCB_RISK_PER_POS / vol_d;
         if(wj != wj)                          // w.fillna(0.0)
            wj = 0.0;
         m_w_eff[j] = wj;
        }

      // debug capture (not part of state)
      m_last_valid = true;
      m_last_day = day_p;
      for(int j = 0; j < SATCB_N_FX; j++)
        {
         m_last_net[j] = net[j];
         m_last_dir[j] = direction[j];
         m_last_sig[j] = sig[j];
         m_last_w[j]   = m_w_eff[j];
        }
     }

   //---------------------------------------------------------------//
   // serializable state — JSON mirroring Python get_state()         //
   //---------------------------------------------------------------//
   string            GetState()
     {
      string s = "{\"version\": 1, \"symbols\": [";
      for(int j = 0; j < SATCB_N_SYM; j++)
        {
         s += "\"" + SATCB_SYMBOLS[j] + "\"";
         if(j < SATCB_N_SYM - 1)
            s += ", ";
        }
      s += "], \"bar_i\": " + IntegerToString(m_bar_i);
      s += ", \"cur_day\": ";
      s += m_has_cur_day ? IntegerToString(m_cur_day) : "null";

      s += ", \"c_ff\": [";
      for(int j = 0; j < SATCB_N_SYM; j++)
        {
         s += SatCbJsonNum(m_c_ff[j]);
         if(j < SATCB_N_SYM - 1)
            s += ", ";
        }
      s += "]";

      s += ", \"vol_ewm\": [";
      for(int j = 0; j < SATCB_N_SYM; j++)
        {
         s += EwmJson(m_vol_ewm[j], m_vol_started[j]);
         if(j < SATCB_N_SYM - 1)
            s += ", ";
        }
      s += "], \"atr_ewm\": [";
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         s += EwmJson(m_atr_ewm[k], m_atr_started[k]);
         if(k < SATCB_N_BK - 1)
            s += ", ";
        }
      s += "]";

      s += ", \"win_hi_f\": " + DonchianArrJson(m_win_hi_f);
      s += ", \"win_hi_s\": " + DonchianArrJson(m_win_hi_s);
      s += ", \"win_lo_f\": " + DonchianArrJson(m_win_lo_f);
      s += ", \"win_lo_s\": " + DonchianArrJson(m_win_lo_s);

      s += ", \"sys_f\": [";
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         s += SysJson(m_sys_f[k]);
         if(k < SATCB_N_BK - 1)
            s += ", ";
        }
      s += "], \"sys_s\": [";
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         s += SysJson(m_sys_s[k]);
         if(k < SATCB_N_BK - 1)
            s += ", ";
        }
      s += "]";

      s += ", \"dc_hist\": [";
      for(int r = 0; r < m_dc_len; r++)
        {
         s += "[";
         for(int j = 0; j < SATCB_N_FX; j++)
           {
            s += SatCbJsonNum(m_dc_hist[r][j]);
            if(j < SATCB_N_FX - 1)
               s += ", ";
           }
         s += "]";
         if(r < m_dc_len - 1)
            s += ", ";
        }
      s += "]";

      s += ", \"w_eff\": [";
      for(int j = 0; j < SATCB_N_FX; j++)
        {
         s += SatCbJsonNum(m_w_eff[j]);
         if(j < SATCB_N_FX - 1)
            s += ", ";
        }
      s += "]}";
      return s;
     }

   bool              SetState(const string st)
     {
      CSatCbJsonReader rd;
      rd.Attach(st);
      if(!rd.Expect('{'))
         return false;
      if(!rd.TryChar('}'))
        {
         while(true)
           {
            string key;
            if(!rd.ParseString(key))
               return false;
            if(!rd.Expect(':'))
               return false;
            if(!ParseStateField(rd, key))
               return false;
            if(rd.TryChar(','))
               continue;
            if(!rd.Expect('}'))
               return false;
            break;
           }
        }
      return !rd.m_err;
     }

private:
   int               CcyIndex(const string c) const
     {
      for(int i = 0; i < SATCB_N_CCY; i++)
         if(SATCB_CCY[i] == c)
            return i;
      return -1;
     }

   //--- JSON writers -------------------------------------------------
   string            EwmJson(const CSatEwmMean &e, const bool started) const
     {
      // Python _Ewm.state(): [weighted, old_wt, nobs, started]
      return "[" + SatCbJsonNum(e.m_avg) + ", " + SatCbJsonNum(e.m_old_wt)
             + ", " + IntegerToString(e.m_nobs) + ", "
             + (started ? "1" : "0") + "]";
     }

   string            SysJson(const CSatCbDonchianSys &d) const
     {
      // Python _DonchianSystem.snap(): [state, size, best]
      return "[" + IntegerToString(d.m_state) + ", "
             + SatCbJsonNum(d.m_size) + ", " + SatCbJsonNum(d.m_best) + "]";
     }

   string            DonchianJson(const CSatDonchian &w) const
     {
      // Python _RollExtreme.state(): {"dq": [[idx,val],...],
      //                               "n_pushed": N, "n_valid": V}
      string s = "{\"dq\": [";
      for(int t = 0; t < w.m_dq_len; t++)
        {
         int slot = (w.m_dq_start + t) % w.m_cap;
         s += "[" + IntegerToString(w.m_dq_idx[slot]) + ", "
              + SatCbJsonNum(w.m_dq_val[slot]) + "]";
         if(t < w.m_dq_len - 1)
            s += ", ";
        }
      s += "], \"n_pushed\": " + IntegerToString(w.m_n_pushed)
           + ", \"n_valid\": " + IntegerToString(w.m_n_valid) + "}";
      return s;
     }

   string            DonchianArrJson(const CSatDonchian &arr[]) const
     {
      string s = "[";
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         s += DonchianJson(arr[k]);
         if(k < SATCB_N_BK - 1)
            s += ", ";
        }
      s += "]";
      return s;
     }

   //--- JSON parsers -------------------------------------------------
   bool              ParseEwm(CSatCbJsonReader &rd, CSatEwmMean &e,
                              bool &started)
     {
      if(!rd.Expect('['))
         return false;
      double w, ow;
      long nobs, st;
      if(!rd.ParseNumber(w))    return false;
      if(!rd.Expect(','))       return false;
      if(!rd.ParseNumber(ow))   return false;
      if(!rd.Expect(','))       return false;
      if(!rd.ParseLong(nobs))   return false;
      if(!rd.Expect(','))       return false;
      if(!rd.ParseLong(st))     return false;
      if(!rd.Expect(']'))       return false;
      e.m_avg    = w;
      e.m_old_wt = ow;
      e.m_nobs   = nobs;
      started    = (st != 0);
      return true;
     }

   bool              ParseSys(CSatCbJsonReader &rd, CSatCbDonchianSys &d)
     {
      if(!rd.Expect('['))
         return false;
      long st;
      double sz, best;
      if(!rd.ParseLong(st))     return false;
      if(!rd.Expect(','))       return false;
      if(!rd.ParseNumber(sz))   return false;
      if(!rd.Expect(','))       return false;
      if(!rd.ParseNumber(best)) return false;
      if(!rd.Expect(']'))       return false;
      d.m_state = (int)st;
      d.m_size  = sz;
      d.m_best  = best;
      return true;
     }

   bool              ParseDonchian(CSatCbJsonReader &rd, CSatDonchian &w)
     {
      if(!rd.Expect('{'))
         return false;
      bool got_dq = false, got_np = false, got_nv = false;
      if(!rd.TryChar('}'))
        {
         while(true)
           {
            string key;
            if(!rd.ParseString(key))
               return false;
            if(!rd.Expect(':'))
               return false;
            if(key == "dq")
              {
               if(!rd.Expect('['))
                  return false;
               w.m_dq_start = 0;
               w.m_dq_len   = 0;
               if(!rd.TryChar(']'))
                 {
                  while(true)
                    {
                     long idx;
                     double val;
                     if(!rd.Expect('['))      return false;
                     if(!rd.ParseLong(idx))   return false;
                     if(!rd.Expect(','))      return false;
                     if(!rd.ParseNumber(val)) return false;
                     if(!rd.Expect(']'))      return false;
                     if(w.m_dq_len >= w.m_cap)
                        return false;         // cannot happen for valid states
                     w.m_dq_idx[w.m_dq_len] = idx;
                     w.m_dq_val[w.m_dq_len] = val;
                     w.m_dq_len++;
                     if(rd.TryChar(','))
                        continue;
                     if(!rd.Expect(']'))
                        return false;
                     break;
                    }
                 }
               got_dq = true;
              }
            else if(key == "n_pushed")
              {
               if(!rd.ParseLong(w.m_n_pushed))
                  return false;
               got_np = true;
              }
            else if(key == "n_valid")
              {
               if(!rd.ParseLong(w.m_n_valid))
                  return false;
               got_nv = true;
              }
            else
               return false;
            if(rd.TryChar(','))
               continue;
            if(!rd.Expect('}'))
               return false;
            break;
           }
        }
      return got_dq && got_np && got_nv;
     }

   bool              ParseEwmArray(CSatCbJsonReader &rd, CSatEwmMean &arr[],
                                   bool &started[], const int n)
     {
      if(!rd.Expect('['))
         return false;
      for(int i = 0; i < n; i++)
        {
         if(i > 0 && !rd.Expect(','))
            return false;
         if(!ParseEwm(rd, arr[i], started[i]))
            return false;
        }
      return rd.Expect(']');
     }

   bool              ParseDonchianArray(CSatCbJsonReader &rd,
                                        CSatDonchian &arr[])
     {
      if(!rd.Expect('['))
         return false;
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         if(k > 0 && !rd.Expect(','))
            return false;
         if(!ParseDonchian(rd, arr[k]))
            return false;
        }
      return rd.Expect(']');
     }

   bool              ParseSysArray(CSatCbJsonReader &rd,
                                   CSatCbDonchianSys &arr[])
     {
      if(!rd.Expect('['))
         return false;
      for(int k = 0; k < SATCB_N_BK; k++)
        {
         if(k > 0 && !rd.Expect(','))
            return false;
         if(!ParseSys(rd, arr[k]))
            return false;
        }
      return rd.Expect(']');
     }

   bool              ParseDoubleVec(CSatCbJsonReader &rd, double &out[],
                                    const int n)
     {
      if(!rd.Expect('['))
         return false;
      for(int i = 0; i < n; i++)
        {
         if(i > 0 && !rd.Expect(','))
            return false;
         if(!rd.ParseNumber(out[i]))
            return false;
        }
      return rd.Expect(']');
     }

   bool              ParseStateField(CSatCbJsonReader &rd, const string key)
     {
      if(key == "version")
        {
         long v;
         if(!rd.ParseLong(v))
            return false;
         return (v == 1);
        }
      if(key == "symbols")
        {
         if(!rd.Expect('['))
            return false;
         for(int j = 0; j < SATCB_N_SYM; j++)
           {
            if(j > 0 && !rd.Expect(','))
               return false;
            string sym;
            if(!rd.ParseString(sym))
               return false;
            if(sym != SATCB_SYMBOLS[j])     // Python: assert symbols match
               return false;
           }
         return rd.Expect(']');
        }
      if(key == "bar_i")
         return rd.ParseLong(m_bar_i);
      if(key == "cur_day")
        {
         if(rd.TryMatch("null"))
           {
            m_has_cur_day = false;
            m_cur_day = 0;
            return true;
           }
         m_has_cur_day = true;
         return rd.ParseLong(m_cur_day);
        }
      if(key == "c_ff")
         return ParseDoubleVec(rd, m_c_ff, SATCB_N_SYM);
      if(key == "vol_ewm")
         return ParseEwmArray(rd, m_vol_ewm, m_vol_started, SATCB_N_SYM);
      if(key == "atr_ewm")
         return ParseEwmArray(rd, m_atr_ewm, m_atr_started, SATCB_N_BK);
      if(key == "win_hi_f")
         return ParseDonchianArray(rd, m_win_hi_f);
      if(key == "win_hi_s")
         return ParseDonchianArray(rd, m_win_hi_s);
      if(key == "win_lo_f")
         return ParseDonchianArray(rd, m_win_lo_f);
      if(key == "win_lo_s")
         return ParseDonchianArray(rd, m_win_lo_s);
      if(key == "sys_f")
         return ParseSysArray(rd, m_sys_f);
      if(key == "sys_s")
         return ParseSysArray(rd, m_sys_s);
      if(key == "dc_hist")
        {
         if(!rd.Expect('['))
            return false;
         m_dc_len = 0;
         if(rd.TryChar(']'))
            return true;
         while(true)
           {
            if(m_dc_len >= SATCB_DC_CAP)
               return false;
            if(!rd.Expect('['))
               return false;
            for(int j = 0; j < SATCB_N_FX; j++)
              {
               if(j > 0 && !rd.Expect(','))
                  return false;
               if(!rd.ParseNumber(m_dc_hist[m_dc_len][j]))
                  return false;
              }
            if(!rd.Expect(']'))
               return false;
            m_dc_len++;
            if(rd.TryChar(','))
               continue;
            if(!rd.Expect(']'))
               return false;
            break;
           }
         return true;
        }
      if(key == "w_eff")
         return ParseDoubleVec(rd, m_w_eff, SATCB_N_FX);
      return false;                     // unknown key: schema is fixed
     }
  };

#endif // SAT_CARRYBREAKOUT_MQH
