//+------------------------------------------------------------------+
//| TestSatEquity.mq5 — FMA3 b_h account-engine in-terminal replay   |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions — pure FileOpen /       |
//| FileReadString / compute.  Replays ONE calendar quarter of the   |
//| Satellite native standalone account (CSatEquityNative) from the  |
//| per-quarter bundle exported by                                   |
//| research/bpure/engine/export_bh_quarter.py; full 6y coverage is  |
//| achieved by CHAINING quarters through the end-state JSON         |
//| (InpStateIn = previous quarter's state-out / state-in file).     |
//|                                                                  |
//| Files (FILE_COMMON — the terminal Common\Files directory):       |
//|   in : FMA3_bh_inputs_<Q>.csv     289-col per-bar inputs         |
//|        FMA3_bh_golden_<Q>.csv     golden eq/eq_w (optional diff) |
//|        <InpStateIn>.json          warm-start state (optional)    |
//|   out: FMA3_bh_actual_<Q>.csv     ts,equity,worst (%.17g)        |
//|        FMA3_bh_state_out_<Q>.json end state (bh_stepper format)  |
//|                                                                  |
//| INPUT CSV SPARSITY CONTRACT (export_bh_quarter.py docstring):    |
//|   tgt/eurq empty = carry previous row; prices empty = carry      |
//|   (emitted iff the has-bit is 1; row 0 fully explicit); swaps    |
//|   empty = 0.0.  PRICES ARE float32-QUANTIZED: parse then cast    |
//|   (float) — the exporter verified this double-rounding path is   |
//|   bitwise against the record feed.                               |
//|                                                                  |
//| The python statement-mirror of THIS loop is                      |
//| research/bpure/engine/sat_equity_harness_sim.py — keep the two   |
//| in lockstep, statement for statement.                            |
//|                                                                  |
//| Run: attach to any chart (Navigator > Scripts); progress every   |
//| 10000 bars; final line starts with "DONE".                       |
//+------------------------------------------------------------------+
#property version     "1.00"
#property script_show_inputs true
#property description "FMA3 b_h quarter replay: FMA3_bh_inputs_<Q>.csv -> FMA3_bh_actual_<Q>.csv (Common Files)"

#include <Sat/SatEquityNative.mqh>

input string InpQuarter = "2020Q1"; // quarter to replay (e.g. 2020Q1)
input string InpStateIn = "";       // warm-start state JSON in Common Files ("" = fresh 10k)

#define TSE_NCROSS   8
#define TSE_NCOLS    289
#define TSE_PROGRESS 10000

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

//+------------------------------------------------------------------+
void OnStart()
  {
   string in_file     = "FMA3_bh_inputs_"    + InpQuarter + ".csv";
   string golden_file = "FMA3_bh_golden_"    + InpQuarter + ".csv";
   string out_file    = "FMA3_bh_actual_"    + InpQuarter + ".csv";
   string state_file  = "FMA3_bh_state_out_" + InpQuarter + ".json";
   Print("TestSatEquity: replaying ", InpQuarter, " (state_in='",
         InpStateIn, "') ...");

   //--- engine + optional warm start --------------------------------
   CSatEquityNative eng;
   if(StringLen(InpStateIn) > 0)
     {
      string js = "";
      if(!TSEReadJson(InpStateIn, js) || !eng.SetState(js))
        {
         Print("TestSatEquity: cannot load state '", InpStateIn, "'");
         return;
        }
      PrintFormat("TestSatEquity: warm start balance=%.17g n_trades=%I64d",
                  eng.Balance(), eng.NTrades());
     }

   //--- input file ---------------------------------------------------
   int fh = FileOpen(in_file, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      Print("TestSatEquity: cannot open ", in_file, " in Common Files, error ",
            GetLastError());
      return;
     }
   string header = TSEChomp(FileReadString(fh));
   if(header != TSEExpectedHeader())
     {
      Print("TestSatEquity: input header mismatch — wrong exporter version?");
      FileClose(fh);
      return;
     }

   //--- optional golden file ------------------------------------------
   int gh = FileOpen(golden_file, FILE_READ | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   bool have_gold = (gh != INVALID_HANDLE);
   if(have_gold)
     {
      string ghead = TSEChomp(FileReadString(gh));
      if(ghead != "ts,equity,worst")
        {
         Print("TestSatEquity: bad golden header, disabling diff");
         FileClose(gh);
         have_gold = false;
        }
     }

   //--- output file -----------------------------------------------------
   int oh = FileOpen(out_file, FILE_WRITE | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   if(oh == INVALID_HANDLE)
     {
      Print("TestSatEquity: cannot open ", out_file, " for writing, error ",
            GetLastError());
      FileClose(fh);
      if(have_gold)
         FileClose(gh);
      return;
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

   long   bars = 0, gold_rows = 0, eq_exact = 0, eqw_exact = 0;
   double max_d_eq = 0.0, max_d_eqw = 0.0;
   bool   gold_ts_ok = true;
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
         Print("TestSatEquity: bad has bitmask at bar ", bars);
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
      if(have_gold && !FileIsEnding(gh))
        {
         string gline = TSEChomp(FileReadString(gh));
         string gp[];
         if(StringSplit(gline, ',', gp) == 3)
           {
            gold_rows++;
            if(StringToInteger(gp[0]) != ts)
               gold_ts_ok = false;
            double ge  = StringToDouble(gp[1]);
            double gw  = StringToDouble(gp[2]);
            double de  = MathAbs(eq_c - ge);
            double dw  = MathAbs(eq_w - gw);
            if(eq_c == ge)
               eq_exact++;
            else if(de > max_d_eq)
               max_d_eq = de;
            if(eq_w == gw)
               eqw_exact++;
            else if(dw > max_d_eqw)
               max_d_eqw = dw;
           }
        }

      bars++;
      if(bars % TSE_PROGRESS == 0)
        {
         PrintFormat("TestSatEquity: bar %I64d (%s) bal=%.6f trades=%I64d",
                     bars, TimeToString((datetime)ts), eng.Balance(),
                     eng.NTrades());
         FileFlush(oh);
        }
     }
   FileClose(fh);
   if(have_gold)
      FileClose(gh);
   FileFlush(oh);
   FileClose(oh);

   //--- end state -----------------------------------------------------
   int sh = FileOpen(state_file, FILE_WRITE | FILE_TXT | FILE_ANSI |
                     FILE_COMMON);
   if(sh != INVALID_HANDLE)
     {
      FileWriteString(sh, eng.GetState());
      FileClose(sh);
     }
   else
      Print("TestSatEquity: cannot write ", state_file);

   PrintFormat("DONE TestSatEquity %s: bars=%I64d final_balance=%.17g "
               "n_trades=%I64d last_eq=%.17g last_eqw=%.17g",
               InpQuarter, bars, eng.Balance(), eng.NTrades(), eq_c, eq_w);
   if(have_gold)
      PrintFormat("DONE golden diff %s: rows=%I64d ts_aligned=%d "
                  "eq_exact=%I64d eqw_exact=%I64d max|d_eq|=%.3g "
                  "max|d_eqw|=%.3g",
                  InpQuarter, gold_rows, (int)gold_ts_ok, eq_exact,
                  eqw_exact, max_d_eq, max_d_eqw);
   else
      Print("DONE golden diff: no golden file, skipped");
  }
//+------------------------------------------------------------------+
