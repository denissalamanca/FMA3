//+------------------------------------------------------------------+
//| TestBook.mq5 — S1 R1 whole-book in-terminal replay harness       |
//| (UNIT 3: the in-terminal twin of                                 |
//| research/bpure/book/book_orchestrator_sim.py).                   |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions — pure FileOpen /       |
//| FileReadString / CBookOrchestrator compute. Drives the FULL      |
//| 2020-2025 grid through Book/BookOrchestrator.mqh on the FROZEN   |
//| Common-Files bundles and emits the book_frac stream with the     |
//| exporter's exact semantics; every emitted row is diffed in-script|
//| against the golden FMA3_fed_frac_v3.csv (structural + numeric,   |
//| the TestBlend sumcheck pattern generalized to a stream diff).    |
//|                                                                  |
//| Files (FILE_COMMON — the terminal Common\Files directory):       |
//|   in : FMA3_v34_inputs.csv          H1 signal closes (37 syms)   |
//|        FMA3_coresim_segments.csv    + FMA3_coresim_seg{0..31}.csv|
//|        FMA3_bh_inputs_<Q>.csv       24 quarters 2020Q1..2025Q4   |
//|        FMA3_fed_frac_v3.csv         golden stream (optional diff)|
//|   out: FMA3_book_actual.csv         epoch,broker_sym,%.17g       |
//|                                                                  |
//| DRIVE SCHEDULE (BookOrchestrator drive contract, general form):  |
//|   1. core feed SEGMENT-BATCH fully ahead: all 32 frozen segments |
//|      leg-major (TestCoreSim pattern), then SetCoreFeedDone();    |
//|   2. per H1 grid stamp h (previous stamp p): FIRST feed all      |
//|      pending M1 rows with ts <= p, then StepH1(h). Feeding a     |
//|      minute in [p+1h, p+2h) only after StepH1(h) is what keeps   |
//|      the held-ring tgt law faithful across GRID GAPS (the ring   |
//|      row of hour p materializes at StepH1(h), the deferred SC    |
//|      lag);                                                       |
//|   3. after the last H1 row: feed ALL remaining minutes, then     |
//|      FinalizeH1() (deferred SC row + trailing core-only hours).  |
//|                                                                  |
//| The M1 quarter parser is TestSatEquity.mq5's, statement for      |
//| statement (sparsity carry, float32 price cast, eurq crosses,     |
//| swaps re-parsed each row) — MINUS the tgt column, which is       |
//| IGNORED: the b tgt comes from the orchestrator's held f_sat ring |
//| (that is the point of the R1 gate).                              |
//|                                                                  |
//| SCOPE PIN (S1): Core leg targets are the FROZEN tgt column of    |
//| the CoreSim segment bundles; live Core targets are S2/S3.        |
//|                                                                  |
//| Run: attach to any chart (Navigator > Scripts). Progress every   |
//| 2000 H1 bars; final line starts with "DONE TestBook". The judge  |
//| for the written stream is                                        |
//| research/bpure/book/validate_book_stream.py (PASS <= 1e-12).     |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property description "FMA3 R1 whole-book replay: frozen bundles -> FMA3_book_actual.csv + in-script golden diff"
#property script_show_inputs false

#include <Book/BookOrchestrator.mqh>

#define TBK_MASTER    "FMA3_v34_inputs.csv"
#define TBK_MANIFEST  "FMA3_coresim_segments.csv"
#define TBK_GOLDEN    "FMA3_fed_frac_v3.csv"
#define TBK_OUT       "FMA3_book_actual.csv"
#define TBK_NSEG      32
#define TBK_NQ        24
#define TBK_PROGRESS  2000
#define TBK_TOL       1e-12     // R1 gate
#define TBK_QUANT     5e-13     // 12dp golden quantization bound

//==================================================================//
// globals                                                          //
//==================================================================//
CBookOrchestrator g_orc;
int    g_out = INVALID_HANDLE;

// ---- golden stream diff ----
int    g_gh = INVALID_HANDLE;
bool   g_have_gold = false;
bool   g_struct_ok = true;
string g_struct_msg = "";
long   g_gold_rows = 0;
long   g_cmp_data = 0, g_cmp_sent = 0;
long   g_over_tol = 0, g_over_quant = 0;
double g_max_d = 0.0;
long   g_max_d_epoch = 0;
string g_max_d_sym = "";

// ---- M1 quarter feeder (carried inputs persist across rows/files) ----
string g_quarters[TBK_NQ];
int    g_m1_fh = INVALID_HANDLE;
int    g_m1_qi = 0;              // next quarter index to open
bool   g_m1_pending = false;
bool   g_m1_done = false;
long   g_m1_ts = 0;
bool   g_has[SATEQ_NSYM];
double g_bo[SATEQ_NSYM], g_ao[SATEQ_NSYM], g_bc[SATEQ_NSYM];
double g_ac[SATEQ_NSYM], g_bl[SATEQ_NSYM], g_ah[SATEQ_NSYM];
double g_cross[BOOKORC_NCROSS];
double g_swl[SATEQ_NSYM], g_sws[SATEQ_NSYM];

//------------------------------------------------------------------//
string TBKChomp(const string line_in)
  {
   string line = line_in;
   int n = StringLen(line);
   if(n > 0 && StringGetCharacter(line, n - 1) == 13)
      line = StringSubstr(line, 0, n - 1);
   return line;
  }

// expected M1 input header (TestSatEquity's TSEExpectedHeader)
string TBKExpectedM1Header()
  {
   string px[6] = {"bo", "ao", "bc", "ac", "bl", "ah"};
   string h = "ts,has";
   for(int k = 0; k < SATEQ_NSYM; k++)
      h += ",tgt_" + SATEQ_SYMBOLS[k];
   for(int f = 0; f < 6; f++)
      for(int k = 0; k < SATEQ_NSYM; k++)
         h += "," + px[f] + "_" + SATEQ_SYMBOLS[k];
   for(int c = 0; c < BOOKORC_NCROSS; c++)
      h += ",eurq_" + BOOKORC_CROSSES[c];
   for(int k = 0; k < SATEQ_NSYM; k++)
      h += ",swl_" + SATEQ_SYMBOLS[k];
   for(int k = 0; k < SATEQ_NSYM; k++)
      h += ",sws_" + SATEQ_SYMBOLS[k];
   return h;
  }

//------------------------------------------------------------------//
// core phase: 32 frozen segments, leg-major (TestCoreSim pattern)  //
//------------------------------------------------------------------//
bool RunCorePhase()
  {
   int hm = FileOpen(TBK_MANIFEST, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(hm == INVALID_HANDLE)
     { PrintFormat("TestBook: FAIL cannot open %s (err %d)", TBK_MANIFEST, GetLastError()); return false; }
   int  seg_j[TBK_NSEG];
   long seg_n[TBK_NSEG];
   int  nseg = 0;
   while(!FileIsEnding(hm) && nseg < TBK_NSEG)
     {
      string tok = FileReadString(hm);
      if(tok == "" && FileIsEnding(hm))
         break;
      seg_j[nseg] = (int)StringToInteger(tok);
      FileReadString(hm);                        // t0 (unused)
      FileReadString(hm);                        // t1 (unused)
      seg_n[nseg] = StringToInteger(FileReadString(hm));
      nseg++;
     }
   FileClose(hm);
   if(nseg != TBK_NSEG)
     { PrintFormat("TestBook: FAIL manifest has %d segments, want %d", nseg, TBK_NSEG); return false; }

   for(int s = 0; s < nseg; s++)
     {
      if(seg_j[s] != s)
        { PrintFormat("TestBook: FAIL manifest order (row %d has j=%d)", s, seg_j[s]); return false; }
      string fin = StringFormat("FMA3_coresim_seg%d.csv", s);
      int h = FileOpen(fin, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(h == INVALID_HANDLE)
        { PrintFormat("TestBook: FAIL cannot open %s (err %d)", fin, GetLastError()); return false; }
      if(!g_orc.BeginCoreSegment())
        { PrintFormat("TestBook: FAIL BeginCoreSegment seg %d: %s", s, g_orc.LastError()); FileClose(h); return false; }
      long nrows = 0;
      while(!FileIsEnding(h))
        {
         string tok = FileReadString(h);
         if(tok == "" && FileIsEnding(h))
            break;                               // trailing newline
         int  leg = (int)StringToInteger(tok);
         long ts  = StringToInteger(FileReadString(h));
         double bo = SatParseDouble(FileReadString(h));
         double bh = SatParseDouble(FileReadString(h));
         double bl = SatParseDouble(FileReadString(h));
         double bc = SatParseDouble(FileReadString(h));
         double ao = SatParseDouble(FileReadString(h));
         double ah = SatParseDouble(FileReadString(h));
         double al = SatParseDouble(FileReadString(h));
         double ac = SatParseDouble(FileReadString(h));
         double eurq   = SatParseDouble(FileReadString(h));
         double sflag  = SatParseDouble(FileReadString(h));
         double slong  = SatParseDouble(FileReadString(h));
         double sshort = SatParseDouble(FileReadString(h));
         double tgt    = SatParseDouble(FileReadString(h));
         if(!g_orc.StepCoreLegBar(leg, ts, bo, bh, bl, bc, ao, ah, al, ac,
                                  eurq, sflag, slong, sshort, tgt))
           { PrintFormat("TestBook: FAIL seg %d row %I64d: %s", s, nrows, g_orc.LastError()); FileClose(h); return false; }
         nrows++;
        }
      FileClose(h);
      if(nrows != seg_n[s])
        { PrintFormat("TestBook: FAIL seg %d rows %I64d != manifest %I64d", s, nrows, seg_n[s]); return false; }
      if(!g_orc.EndCoreSegment())
        { PrintFormat("TestBook: FAIL EndCoreSegment seg %d: %s", s, g_orc.LastError()); return false; }
      PrintFormat("TestBook: core seg %2d rows=%I64d fcore_rows=%d seed_next=%.17g",
                  s, nrows, g_orc.FCoreRows(), g_orc.CoreSeed());
     }
   if(!g_orc.SetCoreFeedDone())
     { PrintFormat("TestBook: FAIL SetCoreFeedDone: %s", g_orc.LastError()); return false; }
   return true;
  }

//------------------------------------------------------------------//
// M1 feeder: parse one row of the current quarter into the carried //
// buffers (TestSatEquity parse, tgt column IGNORED). false = all    //
// quarters exhausted.                                               //
//------------------------------------------------------------------//
bool ReadNextM1()
  {
   while(true)
     {
      if(g_m1_fh == INVALID_HANDLE)
        {
         if(g_m1_qi >= TBK_NQ)
           {
            g_m1_done = true;
            return false;
           }
         string fname = "FMA3_bh_inputs_" + g_quarters[g_m1_qi] + ".csv";
         g_m1_fh = FileOpen(fname, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
         if(g_m1_fh == INVALID_HANDLE)
           {
            PrintFormat("TestBook: FAIL cannot open %s (err %d)", fname, GetLastError());
            g_m1_done = true;
            return false;
           }
         string header = TBKChomp(FileReadString(g_m1_fh));
         if(header != TBKExpectedM1Header())
           {
            PrintFormat("TestBook: FAIL %s header mismatch", fname);
            FileClose(g_m1_fh);
            g_m1_fh = INVALID_HANDLE;
            g_m1_done = true;
            return false;
           }
         PrintFormat("TestBook: M1 quarter %s opened (b bal=%.2f trades=%I64d)",
                     g_quarters[g_m1_qi], g_orc.BBalance(), g_orc.BTrades());
         g_m1_qi++;
        }
      if(FileIsEnding(g_m1_fh))
        {
         FileClose(g_m1_fh);
         g_m1_fh = INVALID_HANDLE;
         continue;                               // next quarter
        }
      string line = TBKChomp(FileReadString(g_m1_fh));
      if(StringLen(line) == 0)
         continue;
      string parts[];
      int np = StringSplit(line, ',', parts);
      if(np < 2)
         continue;
      g_m1_ts = StringToInteger(parts[0]);
      if(StringLen(parts[1]) != SATEQ_NSYM)
        {
         Print("TestBook: FAIL bad has bitmask in M1 row");
         g_m1_done = true;
         return false;
        }
      for(int k = 0; k < SATEQ_NSYM; k++)
         g_has[k] = (StringGetCharacter(parts[1], k) == '1');
      // tgt columns 2..32 IGNORED (held-ring law inside the orchestrator)
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
                  case 0: g_bo[k] = v; break;
                  case 1: g_ao[k] = v; break;
                  case 2: g_bc[k] = v; break;
                  case 3: g_ac[k] = v; break;
                  case 4: g_bl[k] = v; break;
                  default: g_ah[k] = v; break;
                 }
              }
           }
      // eurq crosses: empty = carry
      for(int c = 0; c < BOOKORC_NCROSS; c++)
        {
         int j = 219 + c;
         string s = (j < np) ? parts[j] : "";
         if(StringLen(s) > 0)
            g_cross[c] = StringToDouble(s);
        }
      // swaps: empty = 0.0 (re-parsed every row)
      for(int k = 0; k < SATEQ_NSYM; k++)
        {
         int j = 227 + k;
         string s = (j < np) ? parts[j] : "";
         g_swl[k] = (StringLen(s) > 0) ? StringToDouble(s) : 0.0;
         j = 258 + k;
         s = (j < np) ? parts[j] : "";
         g_sws[k] = (StringLen(s) > 0) ? StringToDouble(s) : 0.0;
        }
      g_m1_pending = true;
      return true;
     }
   return false;
  }

// StepM1 for every pending row with ts <= limit
bool FeedM1(const long limit)
  {
   while(!g_m1_done)
     {
      if(!g_m1_pending && !ReadNextM1())
         break;
      if(g_m1_ts > limit)
         return true;
      if(!g_orc.StepM1(g_m1_ts, g_has, g_bo, g_ao, g_bc, g_ac, g_bl, g_ah,
                       g_cross, g_swl, g_sws))
        {
         PrintFormat("TestBook: FAIL StepM1 at %I64d: %s", g_m1_ts, g_orc.LastError());
         return false;
        }
      g_m1_pending = false;
     }
   return true;
  }

//------------------------------------------------------------------//
// golden stream diff (one emitted row vs the next golden row)      //
//------------------------------------------------------------------//
void CompareGolden(const long e, const string sym, const double v)
  {
   if(!g_have_gold || !g_struct_ok)
      return;
   if(FileIsEnding(g_gh))
     {
      g_struct_ok = false;
      g_struct_msg = StringFormat("golden ended before actual at %I64d,%s", e, sym);
      return;
     }
   string gline = TBKChomp(FileReadString(g_gh));
   string gp[];
   if(StringSplit(gline, ',', gp) != 3)
     {
      g_struct_ok = false;
      g_struct_msg = "malformed golden row: " + StringSubstr(gline, 0, 60);
      return;
     }
   g_gold_rows++;
   long   ge = StringToInteger(gp[0]);
   if(ge != e || gp[1] != sym)
     {
      g_struct_ok = false;
      g_struct_msg = StringFormat("row %I64d: actual %I64d,%s vs golden %I64d,%s",
                                  g_gold_rows, e, sym, ge, gp[1]);
      return;
     }
   if(sym == "__GRID__")
     {
      g_cmp_sent++;
      return;
     }
   double d = MathAbs(v - StringToDouble(gp[2]));
   g_cmp_data++;
   if(d > g_max_d)
     {
      g_max_d = d;
      g_max_d_epoch = e;
      g_max_d_sym = sym;
     }
   if(d > TBK_TOL)
      g_over_tol++;
   if(d > TBK_QUANT)
      g_over_quant++;
  }

// write + diff every row the last StepH1/FinalizeH1 emitted
void DrainEmissions()
  {
   int ne = g_orc.EmitCount();
   for(int r = 0; r < ne; r++)
     {
      long   e = g_orc.EmitTs(r);
      string s = g_orc.EmitSymbol(r);
      double v = g_orc.EmitFrac(r);
      if(s == "__GRID__")
         FileWriteString(g_out, IntegerToString(e) + ",__GRID__,0\n");
      else
         FileWriteString(g_out, IntegerToString(e) + "," + s + ","
                         + StringFormat("%.17g", v) + "\n");
      CompareGolden(e, s, v);
     }
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   Print("TestBook: S1 R1 whole-book replay starting ...");
   for(int y = 0; y < 6; y++)
      for(int q = 0; q < 4; q++)
         g_quarters[y * 4 + q] = StringFormat("%dQ%d", 2020 + y, q + 1);

   if(!FileIsExist(TBK_MASTER, FILE_COMMON) ||
      !FileIsExist(TBK_MANIFEST, FILE_COMMON))
     {
      Print("TestBook: STAGED — input bundles not found in Common\\Files ",
            "(need ", TBK_MASTER, " + ", TBK_MANIFEST, " + seg/quarter files). ",
            "Nothing executed; exiting cleanly.");
      return;
     }

   //--- orchestrator ---------------------------------------------------
   if(!g_orc.Init())
     {
      Print("TestBook: FAIL Init: ", g_orc.LastError());
      return;
     }

   //--- golden (optional) ------------------------------------------------
   g_gh = FileOpen(TBK_GOLDEN, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   g_have_gold = (g_gh != INVALID_HANDLE);
   if(g_have_gold)
     {
      string ghead = TBKChomp(FileReadString(g_gh));   // "w_v7=...,fmt=3"
      if(StringFind(ghead, "config_hash=51a7541cc2aaa593") < 0)
        {
         Print("TestBook: golden header unexpected, disabling diff: ", ghead);
         FileClose(g_gh);
         g_have_gold = false;
        }
     }
   else
      Print("TestBook: golden ", TBK_GOLDEN, " not found — writing stream without diff");

   //--- core phase (drive contract 1: fully ahead of the H1 clock) ------
   if(!RunCorePhase())
      return;
   PrintFormat("TestBook: core feed done — %d segments, %d f_core rows, "
               "a_first=%.17g final_seed=%.17g",
               g_orc.CoreSegments(), g_orc.FCoreRows(), g_orc.AFirst(),
               g_orc.CoreSeed());

   //--- output -----------------------------------------------------------
   g_out = FileOpen(TBK_OUT, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(g_out == INVALID_HANDLE)
     {
      Print("TestBook: FAIL cannot open ", TBK_OUT, " for writing, error ", GetLastError());
      return;
     }
   FileWriteString(g_out, "w_v7=" + StringFormat("%.17g", BOOKORC_W)
                   + ",config_hash=51a7541cc2aaa593,fmt=3,prec=17,src=TestBook\n");

   //--- H1 master loop (drive contract 2/3) -------------------------------
   int fh = FileOpen(TBK_MASTER, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      Print("TestBook: FAIL cannot open ", TBK_MASTER, ", error ", GetLastError());
      FileClose(g_out);
      return;
     }
   string exp_hdr = "timestamp";
   for(int j = 0; j < BOOKORC_NIN; j++)
      exp_hdr += "," + BOOKORC_IN_SYMS[j];
   string header = TBKChomp(FileReadString(fh));
   if(header != exp_hdr)
     {
      Print("TestBook: FAIL master input header mismatch");
      FileClose(fh);
      FileClose(g_out);
      return;
     }

   double nan = SatNan();
   double raw[BOOKORC_NIN];
   long   prev_ts = -1;
   long   h1 = 0;
   bool   failed = false;
   while(!FileIsEnding(fh))
     {
      string line = TBKChomp(FileReadString(fh));
      if(StringLen(line) == 0)
         continue;
      string parts[];
      int np = StringSplit(line, ',', parts);
      if(np < 1)
         continue;
      long ts = StringToInteger(parts[0]);
      for(int j = 0; j < BOOKORC_NIN; j++)
        {
         // trailing empty fields may be dropped by StringSplit — pad
         string s = (j + 1 < np) ? parts[j + 1] : "";
         raw[j] = (StringLen(s) == 0) ? nan : StringToDouble(s);
        }
      // feed pending minutes ts <= previous grid stamp FIRST (the ring
      // row of hour prev only materializes at StepH1(ts) below)
      if(prev_ts >= 0 && !FeedM1(prev_ts))
        {
         failed = true;
         break;
        }
      if(!g_orc.StepH1(ts, raw))
        {
         PrintFormat("TestBook: FAIL StepH1 bar %I64d (%I64d): %s",
                     h1, ts, g_orc.LastError());
         failed = true;
         break;
        }
      DrainEmissions();
      prev_ts = ts;
      h1++;
      if(h1 % TBK_PROGRESS == 0)
        {
         PrintFormat("TestBook: H1 bar %I64d (%s) m1=%I64d hours=%I64d "
                     "rows=%I64d maxd=%.3g",
                     h1, TimeToString((datetime)ts), g_orc.M1Bars(),
                     g_orc.TotalHours(), g_orc.TotalRows(), g_max_d);
         FileFlush(g_out);
        }
     }
   FileClose(fh);

   if(!failed)
     {
      //--- trailing minutes, then FinalizeH1 ------------------------------
      if(!FeedM1(LONG_MAX))
         failed = true;
      else if(!g_orc.FinalizeH1())
        {
         Print("TestBook: FAIL FinalizeH1: ", g_orc.LastError());
         failed = true;
        }
      else
         DrainEmissions();
     }
   if(g_m1_fh != INVALID_HANDLE)
      FileClose(g_m1_fh);
   FileFlush(g_out);
   FileClose(g_out);

   //--- golden must be exhausted too --------------------------------------
   if(g_have_gold && g_struct_ok && !failed)
     {
      while(!FileIsEnding(g_gh))
        {
         string extra = TBKChomp(FileReadString(g_gh));
         if(StringLen(extra) > 0)
           {
            g_struct_ok = false;
            g_struct_msg = "golden has extra rows after actual ended: "
                           + StringSubstr(extra, 0, 60);
            break;
           }
        }
     }
   if(g_have_gold)
      FileClose(g_gh);

   //--- verdict --------------------------------------------------------------
   PrintFormat("TestBook: emitted hours=%I64d rows=%I64d sentinels=%I64d "
               "h1_bars=%I64d m1_bars=%I64d fcore consumed %d/%d",
               g_orc.TotalHours(), g_orc.TotalRows(), g_orc.TotalSentinels(),
               g_orc.H1Bars(), g_orc.M1Bars(), g_orc.FCoreCursor(),
               g_orc.FCoreRows());
   PrintFormat("TestBook: b engine final bal=%.17g trades=%I64d | last a_h=%.17g b_h=%.17g",
               g_orc.BBalance(), g_orc.BTrades(), g_orc.LastAH(), g_orc.LastBH());
   if(g_have_gold)
     {
      if(!g_struct_ok)
         Print("TestBook: *** STRUCTURAL DIVERGENCE *** ", g_struct_msg);
      PrintFormat("TestBook golden diff: rows=%I64d (data %I64d + sentinels %I64d) "
                  "max|d|=%.6g at %I64d,%s | >1e-12: %I64d | >5e-13: %I64d",
                  g_gold_rows, g_cmp_data, g_cmp_sent, g_max_d, g_max_d_epoch,
                  g_max_d_sym, g_over_tol, g_over_quant);
      bool pass = (!failed && g_struct_ok && g_max_d <= TBK_TOL);
      PrintFormat("DONE TestBook: %s (structural %s, max|d|=%.6g vs tol 1e-12, "
                  "quant-bound rows %I64d) out=%s (Common Files)",
                  pass ? "PASS" : "FAIL", g_struct_ok ? "OK" : "DIVERGED",
                  g_max_d, g_over_quant, TBK_OUT);
     }
   else
      PrintFormat("DONE TestBook: stream written, NO GOLDEN DIFF%s out=%s "
                  "(judge: validate_book_stream.py)",
                  failed ? " *** RUN FAILED ***" : "", TBK_OUT);
  }
//+------------------------------------------------------------------+
