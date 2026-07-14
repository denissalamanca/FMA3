//+------------------------------------------------------------------+
//| SatEquityNative.mqh — FMA3 Satellite native standalone account   |
//| equity engine (b_h), 1m cross-margined, 31-symbol book.          |
//|                                                                  |
//| 1:1 MQL5 port of research/bpure/engine/bh_stepper.py             |
//| (BHAccountStepper.step, itself a statement-level transcription of|
//| the engine of record FMA2/research/account_engine_1m.py::        |
//| _run_chunk lines 108-207, frozen sha256 700ea915... in           |
//| FMA3-v34-freeze-1).  Spec: research/bpure/engine/                |
//| BH_ENGINE_SPEC.md.  bh_stepper.py is MEASURED bitwise-equal to   |
//| the golden curve over all 2,948,650 1m bars (spec §8).           |
//|                                                                  |
//| FLOAT DISCIPLINE (spec §7): IEEE-754 float64 round-to-nearest,   |
//| multiplications left-to-right as written, floor(x + 1e-9) lot    |
//| quantizer, `balance += pnl - comm*lots` is ONE addition of a     |
//| pre-computed rhs.  Do NOT refactor groupings — float64           |
//| associativity is load-bearing for bit parity.                    |
//|                                                                  |
//| State (the ONLY carry between bars) round-trips as JSON field-   |
//| for-field with bh_stepper.get_state()/set_state():               |
//|   {"balance": f, "lots": [f x31], "entry": [f x31],              |
//|    "n_trades": i, "symbols": [s x31]}                            |
//| so a chained-quarter warm start can be mirrored 1:1 in python.   |
//+------------------------------------------------------------------+
#ifndef SAT_SATEQUITYNATIVE_MQH
#define SAT_SATEQUITYNATIVE_MQH

#include <Sat/SatMath.mqh>

#define SATEQ_NSYM 31

//------------------------------------------------------------------//
// Static per-symbol configuration — BH_ENGINE_SPEC.md §2.          //
// Provenance: FMA2 core.S.INSTRUMENTS (NSF5 config/settings.py),   //
// resolved VALUES verified 2026-07-14 against the live config and  //
// re-asserted by export_bh_quarter.py::verify_constants on every   //
// export.  Symbol order = golden book.parquet column order         //
// (alphabetical).                                                  //
//------------------------------------------------------------------//
const string SATEQ_SYMBOLS[SATEQ_NSYM] =
  {
   "AUDCAD", "AUDJPY", "AUDNZD", "BTCUSD", "CADCHF", "CADJPY", "DAX",
   "ETHUSD", "EURCAD", "EURCHF", "EURGBP", "EURNOK", "EURNZD", "EURSEK",
   "EURUSD", "GBPJPY", "JP225",  "NZDCAD", "NZDJPY", "SOLUSD", "UK100",
   "US30",   "USA500", "USDCHF", "USDJPY", "USTEC",  "XAGUSD", "XAUUSD",
   "XBRUSD", "XNGUSD", "XTIUSD"
  };

// contract_size
const double SATEQ_CONTRACT[SATEQ_NSYM] =
  {
   100000.0, 100000.0, 100000.0, 1.0, 100000.0, 100000.0, 1.0,
   1.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0, 100000.0,
   100000.0, 100000.0, 1.0, 100000.0, 100000.0, 1.0, 1.0,
   1.0, 1.0, 100000.0, 100000.0, 1.0, 5000.0, 100.0,
   1000.0, 10000.0, 1000.0
  };

// commission_side — EUR per lot PER SIDE
const double SATEQ_COMM_SIDE[SATEQ_NSYM] =
  {
   3.25, 3.25, 3.25, 0.0, 3.25, 3.25, 0.0,
   0.0, 3.25, 3.25, 3.25, 3.25, 3.25, 3.25,
   3.25, 3.25, 0.0, 3.25, 3.25, 0.0, 0.0,
   0.0, 0.0, 3.25, 3.25, 0.0, 3.25, 3.25,
   0.0, 0.0, 0.0
  };

// leverage
const double SATEQ_LEVERAGE[SATEQ_NSYM] =
  {
   20.0, 20.0, 20.0, 2.0, 20.0, 20.0, 20.0,
   2.0, 20.0, 30.0, 30.0, 20.0, 20.0, 20.0,
   30.0, 20.0, 20.0, 20.0, 20.0, 2.0, 20.0,
   20.0, 20.0, 30.0, 30.0, 20.0, 10.0, 20.0,
   10.0, 10.0, 10.0
  };

// lot_step
const double SATEQ_LOT_STEP[SATEQ_NSYM] =
  {
   0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.1,
   0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
   0.01, 0.01, 0.1,  0.01, 0.01, 0.01, 0.1,
   0.1,  0.1,  0.01, 0.01, 0.1,  0.01, 0.01,
   0.01, 0.01, 0.01
  };

// min_lot
const double SATEQ_MIN_LOT[SATEQ_NSYM] =
  {
   0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.1,
   0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
   0.01, 0.01, 0.1,  0.01, 0.01, 0.01, 0.1,
   0.1,  0.1,  0.01, 0.01, 0.1,  0.01, 0.01,
   0.01, 0.01, 0.01
  };

// Account constants — BH_ENGINE_SPEC.md §2 (core.S.ACCOUNT; the FMA2
// driver asserts stop_out_level == 0.50 exactly).  #define (not const
// double) so SATEQ_INITIAL is usable as a default-parameter constant.
#define SATEQ_INITIAL        10000.0
#define SATEQ_STOP_OUT_LEVEL 0.5
#define SATEQ_MARGIN_CAP     0.9
#define SATEQ_REBALANCE_BAND 0.25

//------------------------------------------------------------------//
// np.sign on finite float64 with +-0.0 PASSTHROUGH — bh_stepper's  //
// _sign (NOT SatSign, which maps -0.0 -> +0.0; the passthrough is  //
// what _run_chunk's np.sign does and keeps -0.0 lot products       //
// bit-faithful).                                                   //
//------------------------------------------------------------------//
double SatEqSign(const double x)
  {
   if(x > 0.0)
      return 1.0;
   if(x < 0.0)
      return -1.0;
   return x;
  }

//------------------------------------------------------------------//
// tiny JSON helpers (only what the state dict needs)               //
//------------------------------------------------------------------//
string SatEqTrim(const string tok_in)
  {
   string tok = tok_in;
   StringTrimLeft(tok);
   StringTrimRight(tok);
   return tok;
  }

// index just past the ':' of "key": in js, or -1
int SatEqJsonValuePos(const string js, const string key)
  {
   string pat = "\"" + key + "\"";
   int p = StringFind(js, pat);
   if(p < 0)
      return -1;
   int c = StringFind(js, ":", p + StringLen(pat));
   if(c < 0)
      return -1;
   return c + 1;
  }

// scalar number after "key": (terminated by ',' or '}')
bool SatEqJsonNumber(const string js, const string key, double &out)
  {
   int p = SatEqJsonValuePos(js, key);
   if(p < 0)
      return false;
   int e1 = StringFind(js, ",", p);
   int e2 = StringFind(js, "}", p);
   int e = (e1 >= 0 && (e2 < 0 || e1 < e2)) ? e1 : e2;
   if(e < 0)
      return false;
   out = StringToDouble(SatEqTrim(StringSubstr(js, p, e - p)));
   return true;
  }

// raw comma-split tokens of the [...] array after "key":
bool SatEqJsonArrayTokens(const string js, const string key, string &toks[])
  {
   int p = SatEqJsonValuePos(js, key);
   if(p < 0)
      return false;
   int lb = StringFind(js, "[", p);
   if(lb < 0)
      return false;
   int rb = StringFind(js, "]", lb);
   if(rb < 0)
      return false;
   string body = StringSubstr(js, lb + 1, rb - lb - 1);
   return (StringSplit(body, ',', toks) > 0);
  }

//==================================================================//
// CSatEquityNative — one cross-margined EUR account over the 31-   //
// symbol Satellite book, one 1m union-grid bar per Step() call.    //
//==================================================================//
class CSatEquityNative
  {
public:
   // ---- persistent state (the ONLY carry between bars) ----
   double            m_balance;
   double            m_lots[SATEQ_NSYM];
   double            m_entry[SATEQ_NSYM];
   long              m_n_trades;

                     CSatEquityNative() { Reset(); }

   void              Reset(const double balance = SATEQ_INITIAL)
     {
      m_balance = balance;
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         m_lots[k]  = 0.0;
         m_entry[k] = 0.0;
        }
      m_n_trades = 0;
     }

   double            Balance() const  { return m_balance; }
   long              NTrades() const  { return m_n_trades; }

   //---------------------------------------------------------------//
   // One union-grid minute.  Every argument is a length-31 array   //
   // in SATEQ_SYMBOLS order; eurq = EUR value of 1 unit of the     //
   // symbol's quote ccy at this bar (ONE value per bar, used for   //
   // everything).  Returns (eq_close, eq_worst) by reference.      //
   // Transcription of bh_stepper.BHAccountStepper.step ==          //
   // _run_chunk lines 108-207; section numbers = spec §5.          //
   //---------------------------------------------------------------//
   void              Step(const double &tgt[], const bool &has_bar[],
                          const double &bid_o[], const double &ask_o[],
                          const double &bid_c[], const double &ask_c[],
                          const double &bid_l[], const double &ask_h[],
                          const double &eurq[], const double &swap_l[],
                          const double &swap_s[],
                          double &eq_c, double &eq_w)
     {
      double balance = m_balance;

      // 1. swaps at the rollover minute
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         if(m_lots[k] != 0.0 && (swap_l[k] != 0.0 || swap_s[k] != 0.0))
           {
            double mid = 0.5 * (bid_o[k] + ask_o[k]);
            double notional = MathAbs(m_lots[k]) * SATEQ_CONTRACT[k]
                              * mid * eurq[k];
            balance += notional * (m_lots[k] > 0 ? swap_l[k] : swap_s[k]);
           }
        }

      // 2. desired lots from the shared balance
      double desired[SATEQ_NSYM];
      double margin_sum = 0.0;
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         double g = tgt[k];
         if(!has_bar[k])
           {
            desired[k] = m_lots[k];      // carry; NO margin contribution
            continue;
           }
         if(g == 0.0)
           {
            desired[k] = 0.0;
            continue;
           }
         double px   = (g > 0) ? ask_o[k] : bid_o[k];
         double unit = px * SATEQ_CONTRACT[k] * eurq[k];
         double raw  = g * balance / unit;
         double n    = MathFloor(MathAbs(raw) / SATEQ_LOT_STEP[k] + 1e-9);
         double L    = n * SATEQ_LOT_STEP[k];
         if(L < SATEQ_MIN_LOT[k])
            L = 0.0;
         desired[k] = SatEqSign(g) * L;
         margin_sum += MathAbs(desired[k]) * unit / SATEQ_LEVERAGE[k];
        }

      double shrink = 1.0;
      double cap = balance * SATEQ_MARGIN_CAP;
      if(margin_sum > cap && margin_sum > 0.0)
         shrink = cap / margin_sum;

      // 3. execute fills at this minute's open (cross the spread)
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         if(!has_bar[k])
            continue;
         double want = desired[k] * shrink;
         double n = MathFloor(MathAbs(want) / SATEQ_LOT_STEP[k] + 1e-9);
         want = SatEqSign(want) * n * SATEQ_LOT_STEP[k];
         if(MathAbs(want) < SATEQ_MIN_LOT[k])
            want = 0.0;
         // rebalance band: skip small same-direction adjustments
         if(m_lots[k] != 0.0 && want != 0.0 && want * m_lots[k] > 0.0
            && MathAbs(want - m_lots[k]) / MathAbs(m_lots[k])
               <= SATEQ_REBALANCE_BAND)
            continue;
         if(want == m_lots[k])
            continue;
         // CLOSE / REDUCE branch
         if(m_lots[k] != 0.0 && (want == 0.0 || want * m_lots[k] < 0.0
                                 || MathAbs(want) < MathAbs(m_lots[k])))
           {
            double close_lots = (want * m_lots[k] <= 0.0)
                                ? m_lots[k] : m_lots[k] - want;
            double px  = (m_lots[k] > 0) ? bid_o[k] : ask_o[k];
            double pnl = (px - m_entry[k]) * close_lots
                         * SATEQ_CONTRACT[k] * eurq[k];
            balance += pnl - SATEQ_COMM_SIDE[k] * MathAbs(close_lots);
            m_lots[k] -= close_lots;
            m_n_trades++;
            if(m_lots[k] == 0.0)
               m_entry[k] = 0.0;
           }
         // OPEN / EXTEND branch (a sign flip runs BOTH in the same bar)
         if(want != 0.0 && MathAbs(want) > MathAbs(m_lots[k]))
           {
            double add = want - m_lots[k];
            double px  = (add > 0) ? ask_o[k] : bid_o[k];
            if(m_lots[k] == 0.0)
               m_entry[k] = px;
            else
               m_entry[k] = (m_entry[k] * m_lots[k] + px * add)
                            / (m_lots[k] + add);
            balance -= SATEQ_COMM_SIDE[k] * MathAbs(add);
            m_lots[k] = want;
            m_n_trades++;
           }
        }

      // 4. joint marks (co-timed at this minute)
      double unreal_c = 0.0;
      double unreal_w = 0.0;
      double margin_used = 0.0;
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         if(m_lots[k] == 0.0)
            continue;
         if(m_lots[k] > 0)
           {
            unreal_c += (bid_c[k] - m_entry[k]) * m_lots[k]
                        * SATEQ_CONTRACT[k] * eurq[k];
            unreal_w += (bid_l[k] - m_entry[k]) * m_lots[k]
                        * SATEQ_CONTRACT[k] * eurq[k];
           }
         else
           {
            unreal_c += (ask_c[k] - m_entry[k]) * m_lots[k]
                        * SATEQ_CONTRACT[k] * eurq[k];
            unreal_w += (ask_h[k] - m_entry[k]) * m_lots[k]
                        * SATEQ_CONTRACT[k] * eurq[k];
           }
         double mid_c = 0.5 * (bid_c[k] + ask_c[k]);
         margin_used += MathAbs(m_lots[k]) * SATEQ_CONTRACT[k]
                        * mid_c * eurq[k] / SATEQ_LEVERAGE[k];
        }
      eq_c = balance + unreal_c;
      eq_w = balance + unreal_w;

      // 5. joint stop-out on the worst co-timed mark
      if(margin_used > 0.0 && eq_w < SATEQ_STOP_OUT_LEVEL * margin_used)
        {
         for(int k = 0; k < SATEQ_NSYM; k++)
           {
            if(m_lots[k] == 0.0)
               continue;
            double px  = (m_lots[k] > 0) ? bid_l[k] : ask_h[k];
            double pnl = (px - m_entry[k]) * m_lots[k]
                         * SATEQ_CONTRACT[k] * eurq[k];
            balance += pnl - SATEQ_COMM_SIDE[k] * MathAbs(m_lots[k]);
            m_lots[k]  = 0.0;
            m_entry[k] = 0.0;
           }
         eq_c = balance;
         eq_w = balance;
        }

      m_balance = balance;
     }

   //---------------------------------------------------------------//
   // state JSON — field-for-field with bh_stepper.get_state():     //
   // {"balance": f, "lots": [..], "entry": [..], "n_trades": i,    //
   //  "symbols": [..]}.  Doubles %.17g (binary64 round-trip).      //
   //---------------------------------------------------------------//
   string            GetState() const
     {
      string s = "{\"balance\": " + StringFormat("%.17g", m_balance)
                 + ", \"lots\": [";
      for(int k = 0; k < SATEQ_NSYM; k++)
         s += (k > 0 ? ", " : "") + StringFormat("%.17g", m_lots[k]);
      s += "], \"entry\": [";
      for(int k = 0; k < SATEQ_NSYM; k++)
         s += (k > 0 ? ", " : "") + StringFormat("%.17g", m_entry[k]);
      s += "], \"n_trades\": " + IntegerToString(m_n_trades)
           + ", \"symbols\": [";
      for(int k = 0; k < SATEQ_NSYM; k++)
         s += (k > 0 ? ", " : "") + "\"" + SATEQ_SYMBOLS[k] + "\"";
      s += "]}";
      return s;
     }

   // parse a bh_stepper/GetState JSON blob; false on any shape or
   // symbol-order mismatch (mirrors set_state's assert)
   bool              SetState(const string js)
     {
      double bal = 0.0;
      if(!SatEqJsonNumber(js, "balance", bal))
         return false;
      string ltoks[], etoks[], stoks[];
      if(!SatEqJsonArrayTokens(js, "lots", ltoks)
         || ArraySize(ltoks) != SATEQ_NSYM)
         return false;
      if(!SatEqJsonArrayTokens(js, "entry", etoks)
         || ArraySize(etoks) != SATEQ_NSYM)
         return false;
      if(!SatEqJsonArrayTokens(js, "symbols", stoks)
         || ArraySize(stoks) != SATEQ_NSYM)
         return false;
      double ntr = 0.0;
      if(!SatEqJsonNumber(js, "n_trades", ntr))
         return false;
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         string sym = SatEqTrim(stoks[k]);
         // strip surrounding quotes
         if(StringLen(sym) < 2 || StringGetCharacter(sym, 0) != '"'
            || StringGetCharacter(sym, StringLen(sym) - 1) != '"')
            return false;
         sym = StringSubstr(sym, 1, StringLen(sym) - 2);
         if(sym != SATEQ_SYMBOLS[k])
            return false;                 // symbol order mismatch
        }
      m_balance = bal;
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         m_lots[k]  = StringToDouble(SatEqTrim(ltoks[k]));
         m_entry[k] = StringToDouble(SatEqTrim(etoks[k]));
        }
      m_n_trades = (long)ntr;
      return true;
     }
  };

#endif // SAT_SATEQUITYNATIVE_MQH
