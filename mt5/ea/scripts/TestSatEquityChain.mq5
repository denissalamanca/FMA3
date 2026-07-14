//+------------------------------------------------------------------+
//| TestSatEquityChain.mq5 — FMA3 b_h chained multi-quarter replay   |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions — pure FileOpen /       |
//| FileReadString / compute.  Chains ALL quarters InpFromQuarter..  |
//| InpToQuarter of the Satellite native standalone account          |
//| (CSatEquityNative) in ONE run: the engine STATE IS CARRIED IN    |
//| MEMORY between quarters (no intermediate state files needed),    |
//| replacing 20+ manual per-quarter TestSatEquity.mq5 runs.         |
//|                                                                  |
//| Per quarter (identical logic to TestSatEquity.mq5, the proven    |
//| single-quarter reference — RECON-8c bitwise on 2020Q1+2020Q2):   |
//|   in : FMA3_bh_inputs_<Q>.csv     289-col per-bar inputs         |
//|        FMA3_bh_golden_<Q>.csv     golden eq/eq_w (optional diff) |
//|   out: FMA3_bh_actual_<Q>.csv     ts,equity,worst (%.17g)        |
//|        FMA3_bh_state_out_<Q>.json end state (audit; the chain    |
//|                                   itself does NOT re-read it)    |
//| All files in FILE_COMMON (terminal Common\Files directory).      |
//|                                                                  |
//| A missing input CSV prints "MISSING ..." and STOPS the chain     |
//| (never silently continues).  Each quarter prints one VERDICT     |
//| line; the run ends with one CHAIN SUMMARY line.                  |
//|                                                                  |
//| INPUT CSV SPARSITY CONTRACT (export_bh_quarter.py docstring):    |
//|   tgt/eurq empty = carry previous row; prices empty = carry      |
//|   (emitted iff the has-bit is 1; row 0 fully explicit); swaps    |
//|   empty = 0.0.  PRICES ARE float32-QUANTIZED: parse then cast    |
//|   (float).  Row 0 of EVERY quarter is fully explicit, so the     |
//|   carry arrays reset per quarter exactly as in per-quarter runs. |
//|                                                                  |
//| Run: attach to any chart (Navigator > Scripts); progress every   |
//| 10000 bars; final line starts with "CHAIN SUMMARY".              |
//+------------------------------------------------------------------+
#property version     "1.00"
#property script_show_inputs true
#property description "FMA3 b_h chained replay: all quarters From..To in one run, state carried in memory"

#include <Sat/SatEquityNative.mqh>

input string InpFromQuarter = "2020Q1"; // first quarter (e.g. 2020Q1)
input string InpToQuarter   = "2025Q4"; // last quarter (inclusive)
input string InpStateIn     = "";       // warm-start state JSON in Common Files ("" = fresh 10k)

#define TSE_NCROSS   8
#define TSE_NCOLS    289
#define TSE_PROGRESS 10000

// ReplayQuarter status codes
#define TSE_OK            0
#define TSE_MISSING_INPUT 1
#define TSE_ERROR         2

// eurq cross columns, exporter order (sorted)
const string TSE_CROSSES[TSE_NCROSS] =
  {
   "EURCAD", "EURCHF", "EURGBP", "EURJPY",
   "EURNOK", "EURNZD", "EURSEK", "EURUSD"
  };

// symbol k -> index into TSE_CROSSES for its QUOTE ccy, -1 = EUR quote
// (quotes from BH_ENGINE_SPEC.md §2, SATEQ_SYMBOLS order)
const int TSE_CROSS_IX[SATEQ_NSYM] =
  {
   0, 3, 5, 7, 1, 3, -1, 7, 0, 1, 2, 4, 5, 6, 7, 3,
   3, 0, 3, 7, 2, 7, 7, 1, 3, 7, 7, 7, 7, 7, 7
  };

// price field block order in the CSV (base column 33, stride 31)
const string TSE_PX_SHORT[6] = {"bo", "ao", "bc", "ac", "bl", "ah"};

// per-quarter replay statistics (for the VERDICT + summary lines)
struct TSEQuarterStats
  {
   long              bars;
   long              gold_rows;
   long              eq_exact;
   long              eqw_exact;
   double            max_d_eq;
   double            max_d_eqw;
   bool              gold_ts_ok;
   bool              have_gold;
   double            last_eq;
   double            last_eqw;
  };

//------------------------------------------------------------------//
// strip a trailing CR (files are LF; be safe under wine)           //
//------------------------------------------------------------------//
string TSEChomp(const string line_in)
  {
   string line = line_in;
   int n = StringLen(line);
   if(n > 0 && StringGetCharacter(line, n - 1) == 13)
      line = StringSubstr(line, 0, n - 1);
   return line;
  }

// expected input header, built from the include-level symbol table
string TSEExpectedHeader()
  {
   string h = "ts,has";
   for(int k = 0; k < SATEQ_NSYM; k++)
      h += ",tgt_" + SATEQ_SYMBOLS[k];
   for(int f = 0; f < 6; f++)
      for(int k = 0; k < SATEQ_NSYM; k++)
         h += "," + TSE_PX_SHORT[f] + "_" + SATEQ_SYMBOLS[k];
   for(int c = 0; c < TSE_NCROSS; c++)
      h += ",eurq_" + TSE_CROSSES[c];
   for(int k = 0; k < SATEQ_NSYM; k++)
      h += ",swl_" + SATEQ_SYMBOLS[k];
   for(int k = 0; k < SATEQ_NSYM; k++)
      h += ",sws_" + SATEQ_SYMBOLS[k];
   return h;
  }

// read one whole (single-line) JSON file from Common Files
bool TSEReadJson(const string fname, string &out)
  {
   int fh = FileOpen(fname, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
      return false;
   out = "";
   while(!FileIsEnding(fh))
      out += FileReadString(fh);
   FileClose(fh);
   return (StringLen(out) > 0);
  }

//------------------------------------------------------------------//
// quarter-string arithmetic: "YYYYQn"                              //
//------------------------------------------------------------------//
bool TSEParseQuarter(const string q, int &year, int &qn)
  {
   if(StringLen(q) != 6 || StringGetCharacter(q, 4) != 'Q')
      return false;
   for(int i = 0; i < 4; i++)
     {
      ushort ch = StringGetCharacter(q, i);
      if(ch < '0' || ch > '9')
         return false;
     }
   ushort qc = StringGetCharacter(q, 5);
   if(qc < '1' || qc > '4')
      return false;
   year = (int)StringToInteger(StringSubstr(q, 0, 4));
   qn   = (int)(qc - '0');
   return true;
  }

string TSEQuarterName(const int year, const int qn)
  {
   return IntegerToString(year) + "Q" + IntegerToString(qn);
  }

//------------------------------------------------------------------//
// replay ONE quarter on the (possibly warm) engine — body is the   //
// TestSatEquity.mq5 OnStart main section, verbatim, with the       //
// counters routed into TSEQuarterStats                             //
//------------------------------------------------------------------//
int TSEReplayQuarter(CSatEquityNative &eng, const string quarter,
                     TSEQuarterStats &st)
  {
   string in_file     = "FMA3_bh_inputs_"    + quarter + ".csv";
   string golden_file = "FMA3_bh_golden_"    + quarter + ".csv";
   string out_file    = "FMA3_bh_actual_"    + quarter + ".csv";
   string state_file  = "FMA3_bh_state_out_" + quarter + ".json";

   st.bars = 0;
   st.gold_rows = 0;
   st.eq_exact = 0;
   st.eqw_exact = 0;
   st.max_d_eq = 0.0;
   st.max_d_eqw = 0.0;
   st.gold_ts_ok = true;
   st.have_gold = false;
   st.last_eq = 0.0;
   st.last_eqw = 0.0;

   //--- input file ---------------------------------------------------
   int fh = FileOpen(in_file, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      Print("MISSING ", in_file, " in Common Files (error ", GetLastError(),
            ") — chain stopped, later quarters NOT replayed");
      return TSE_MISSING_INPUT;
     }
   string header = TSEChomp(FileReadString(fh));
   if(header != TSEExpectedHeader())
     {
      Print("TestSatEquityChain: ", quarter,
            " input header mismatch — wrong exporter version?");
      FileClose(fh);
      return TSE_ERROR;
     }

   //--- optional golden file ------------------------------------------
   int gh = FileOpen(golden_file, FILE_READ | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   st.have_gold = (gh != INVALID_HANDLE);
   if(st.have_gold)
     {
      string ghead = TSEChomp(FileReadString(gh));
      if(ghead != "ts,equity,worst")
        {
         Print("TestSatEquityChain: ", quarter,
               " bad golden header, disabling diff");
         FileClose(gh);
         st.have_gold = false;
        }
     }

   //--- output file -----------------------------------------------------
   int oh = FileOpen(out_file, FILE_WRITE | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   if(oh == INVALID_HANDLE)
     {
      Print("TestSatEquityChain: cannot open ", out_file,
            " for writing, error ", GetLastError());
      FileClose(fh);
      if(st.have_gold)
         FileClose(gh);
      return TSE_ERROR;
     }
   FileWriteString(oh, "ts,equity,worst\n");

   //--- per-bar carried inputs (row 0 is fully explicit) ----------------
   double tgt[SATEQ_NSYM], eurq_sym[SATEQ_NSYM];
   double bo[SATEQ_NSYM], ao[SATEQ_NSYM], bc[SATEQ_NSYM];
   double ac[SATEQ_NSYM], bl[SATEQ_NSYM], ah[SATEQ_NSYM];
   double eurq_cross[TSE_NCROSS];
   double swl[SATEQ_NSYM], sws[SATEQ_NSYM];
   bool   has[SATEQ_NSYM];
   for(int k = 0; k < SATEQ_NSYM; k++)
     {
      tgt[k] = 0.0;
      bo[k] = 0.0;
      ao[k] = 0.0;
      bc[k] = 0.0;
      ac[k] = 0.0;
      bl[k] = 0.0;
      ah[k] = 0.0;
      swl[k] = 0.0;
      sws[k] = 0.0;
      has[k] = false;
     }
   for(int c = 0; c < TSE_NCROSS; c++)
      eurq_cross[c] = 1.0;

   double eq_c = 0.0, eq_w = 0.0;

   //--- main loop ---------------------------------------------------------
   while(!FileIsEnding(fh))
     {
      string line = TSEChomp(FileReadString(fh));
      if(StringLen(line) == 0)
         continue;
      string parts[];
      int np = StringSplit(line, ',', parts);
      if(np < 2)
         continue;
      long ts = StringToInteger(parts[0]);
      // has bitmask (31 chars, '1' = native bar stamped at this minute)
      if(StringLen(parts[1]) != SATEQ_NSYM)
        {
         Print("TestSatEquityChain: ", quarter, " bad has bitmask at bar ",
               st.bars);
         break;
        }
      for(int k = 0; k < SATEQ_NSYM; k++)
         has[k] = (StringGetCharacter(parts[1], k) == '1');
      // tgt: empty = carry
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         int j = 2 + k;
         string s = (j < np) ? parts[j] : "";
         if(StringLen(s) > 0)
            tgt[k] = StringToDouble(s);
        }
      // prices: empty = carry; float32-quantized feed -> (float) cast
      for(int f = 0; f < 6; f++)
         for(int k = 0; k < SATEQ_NSYM; k++)
           {
            int j = 33 + f * SATEQ_NSYM + k;
            string s = (j < np) ? parts[j] : "";
            if(StringLen(s) > 0)
              {
               double v = (float)StringToDouble(s);
               switch(f)
                 {
                  case 0: bo[k] = v; break;
                  case 1: ao[k] = v; break;
                  case 2: bc[k] = v; break;
                  case 3: ac[k] = v; break;
                  case 4: bl[k] = v; break;
                  default: ah[k] = v; break;
                 }
              }
           }
      // eurq crosses: empty = carry
      for(int c = 0; c < TSE_NCROSS; c++)
        {
         int j = 219 + c;
         string s = (j < np) ? parts[j] : "";
         if(StringLen(s) > 0)
            eurq_cross[c] = StringToDouble(s);
        }
      // swaps: empty = 0.0 (re-parsed every row)
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         int j = 227 + k;
         string s = (j < np) ? parts[j] : "";
         swl[k] = (StringLen(s) > 0) ? StringToDouble(s) : 0.0;
         j = 258 + k;
         s = (j < np) ? parts[j] : "";
         sws[k] = (StringLen(s) > 0) ? StringToDouble(s) : 0.0;
        }
      // per-symbol eurq from its quote-ccy cross (EUR quote -> 1.0)
      for(int k = 0; k < SATEQ_NSYM; k++)
         eurq_sym[k] = (TSE_CROSS_IX[k] < 0)
                       ? 1.0 : eurq_cross[TSE_CROSS_IX[k]];

      eng.Step(tgt, has, bo, ao, bc, ac, bl, ah,
               eurq_sym, swl, sws, eq_c, eq_w);
      FileWriteString(oh, IntegerToString(ts) + ","
                      + StringFormat("%.17g", eq_c) + ","
                      + StringFormat("%.17g", eq_w) + "\n");

      //--- golden diff -----------------------------------------------
      if(st.have_gold && !FileIsEnding(gh))
        {
         string gline = TSEChomp(FileReadString(gh));
         string gp[];
         if(StringSplit(gline, ',', gp) == 3)
           {
            st.gold_rows++;
            if(StringToInteger(gp[0]) != ts)
               st.gold_ts_ok = false;
            double ge  = StringToDouble(gp[1]);
            double gw  = StringToDouble(gp[2]);
            double de  = MathAbs(eq_c - ge);
            double dw  = MathAbs(eq_w - gw);
            if(eq_c == ge)
               st.eq_exact++;
            else if(de > st.max_d_eq)
               st.max_d_eq = de;
            if(eq_w == gw)
               st.eqw_exact++;
            else if(dw > st.max_d_eqw)
               st.max_d_eqw = dw;
           }
        }

      st.bars++;
      if(st.bars % TSE_PROGRESS == 0)
        {
         PrintFormat("TestSatEquityChain: %s bar %I64d (%s) bal=%.6f "
                     "trades=%I64d",
                     quarter, st.bars, TimeToString((datetime)ts),
                     eng.Balance(), eng.NTrades());
         FileFlush(oh);
        }
     }
   FileClose(fh);
   if(st.have_gold)
      FileClose(gh);
   FileFlush(oh);
   FileClose(oh);
   st.last_eq  = eq_c;
   st.last_eqw = eq_w;

   //--- end state (audit only — the chain carries state in memory) ----
   int sh = FileOpen(state_file, FILE_WRITE | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   if(sh != INVALID_HANDLE)
     {
      FileWriteString(sh, eng.GetState());
      FileClose(sh);
     }
   else
      Print("TestSatEquityChain: cannot write ", state_file);

   return TSE_OK;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   int y0 = 0, q0 = 0, y1 = 0, q1 = 0;
   if(!TSEParseQuarter(InpFromQuarter, y0, q0)
      || !TSEParseQuarter(InpToQuarter, y1, q1))
     {
      Print("TestSatEquityChain: bad quarter input(s) '", InpFromQuarter,
            "' / '", InpToQuarter, "' — expected YYYYQn (e.g. 2020Q1)");
      return;
     }
   if(y0 * 4 + q0 > y1 * 4 + q1)
     {
      Print("TestSatEquityChain: InpFromQuarter is after InpToQuarter");
      return;
     }
   Print("TestSatEquityChain: chaining ", InpFromQuarter, " .. ",
         InpToQuarter, " (state_in='", InpStateIn, "') ...");

   //--- engine + optional warm start --------------------------------
   CSatEquityNative eng;
   if(StringLen(InpStateIn) > 0)
     {
      string js = "";
      if(!TSEReadJson(InpStateIn, js) || !eng.SetState(js))
        {
         Print("TestSatEquityChain: cannot load state '", InpStateIn, "'");
         return;
        }
      PrintFormat("TestSatEquityChain: warm start balance=%.17g "
                  "n_trades=%I64d", eng.Balance(), eng.NTrades());
     }

   //--- chained quarter loop -----------------------------------------
   long total_bars = 0;
   int  n_run = 0, n_pass = 0, n_fail = 0, n_nogold = 0;
   bool stopped = false;
   int  y = y0, q = q0;
   while(y * 4 + q <= y1 * 4 + q1 && !IsStopped())
     {
      string quarter = TSEQuarterName(y, q);
      TSEQuarterStats st;
      int rc = TSEReplayQuarter(eng, quarter, st);
      if(rc != TSE_OK)
        {
         stopped = true;
         break;
        }
      n_run++;
      total_bars += st.bars;

      string verdict;
      if(!st.have_gold)
        {
         verdict = "NOGOLD";
         n_nogold++;
        }
      else if(st.gold_ts_ok && st.gold_rows == st.bars
              && st.eq_exact == st.gold_rows
              && st.eqw_exact == st.gold_rows)
        {
         verdict = "PASS";
         n_pass++;
        }
      else
        {
         verdict = "FAIL";
         n_fail++;
        }
      PrintFormat("VERDICT %s: %s bars=%I64d gold_rows=%I64d ts_aligned=%d "
                  "eq_exact=%I64d eqw_exact=%I64d max|d_eq|=%.3g "
                  "max|d_eqw|=%.3g balance=%.17g n_trades=%I64d",
                  quarter, verdict, st.bars, st.gold_rows,
                  (int)st.gold_ts_ok, st.eq_exact, st.eqw_exact,
                  st.max_d_eq, st.max_d_eqw, eng.Balance(), eng.NTrades());

      // next quarter
      q++;
      if(q > 4)
        {
         q = 1;
         y++;
        }
     }
   if(!stopped && y * 4 + q <= y1 * 4 + q1)
     {
      Print("TestSatEquityChain: stopped by user before ",
            TSEQuarterName(y, q));
      stopped = true;
     }

   PrintFormat("CHAIN SUMMARY %s..%s: %s quarters_run=%d passed=%d failed=%d "
               "nogold=%d total_bars=%I64d final_balance=%.17g "
               "n_trades=%I64d",
               InpFromQuarter, InpToQuarter,
               (stopped ? "INCOMPLETE" : "COMPLETE"),
               n_run, n_pass, n_fail, n_nogold, total_bars,
               eng.Balance(), eng.NTrades());
  }
//+------------------------------------------------------------------+
