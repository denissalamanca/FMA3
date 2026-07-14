//+------------------------------------------------------------------+
//| CheckBookState.mq5 — save/load/continue + refuse-latch gate for  |
//| Book/BookState.mqh (the >=12-sig-digit atomic state serializer,  |
//| FABLEBOOKNATIVE_DESIGN v2 item 5(v)).                            |
//|                                                                  |
//| Drives the SAME synthetic 50-hour book as                        |
//| CheckBookOrchestrator.mq5 (deterministic, no market data), then: |
//|   T1  SPLIT/CONTINUE: run A saves its complete ledger after H1   |
//|       bar 30 (atomic tmp+FileMove into Common Files), continues  |
//|       to the end; run B = fresh Init + CBookState::Load + the    |
//|       identical remaining feed. EVERY emitted row of B's tail    |
//|       must be BITWISE (==) identical to A's tail, and the final  |
//|       a/b end-states bit-equal.                                  |
//|   T2  ROUND-TRIP: A and B saved again at the end must produce    |
//|       BYTE-IDENTICAL state files.                                |
//|   T3  TORN WRITE: a truncated state file must refuse to load.    |
//|   T4  BIT-FLIP: a payload byte flip (stale fnv) must refuse.     |
//|   T5  ANCHOR GUARD: continuity a_first corrupted by 1% (fnv      |
//|       recomputed so the checksum passes) must refuse.            |
//|   T6  J-SPLICE LATCH: a CONSISTENT 1% re-base of the a-sampler   |
//|       first_v + continuity a_first (the "passes every self-check |
//|       while silently mis-weighting every trade" scenario) must   |
//|       trip the REFUSE_TO_TRADE latch via the j discontinuity.    |
//|   T7  guards: Save inside an open core segment refused; fresh    |
//|       latch states sane.                                         |
//|                                                                  |
//| The terminal Print output must end with                          |
//| "CheckBookState: ALL PASS".                                      |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Book/BookOrchestrator.mqh>

#define CBS_H0     1578268800   // 2020-01-06 00:00:00 UTC (Monday)
#define CBS_NSATH  50           // sat/H1 grid hours
#define CBS_NCOREH 52           // core grid hours (2 trailing core-only)
#define CBS_MPH    3            // M1 rows per hour
#define CBS_SPLIT  30           // save after this H1 bar's minutes

#define CBS_FILE      "FMA3_bookstate_check.json"
#define CBS_FILE_ENDA "FMA3_bookstate_check_endA.json"
#define CBS_FILE_ENDB "FMA3_bookstate_check_endB.json"
#define CBS_FILE_TMP  "FMA3_bookstate_check_tamper.json"

int g_fail = 0;

void Expect(const bool ok, const string what)
  {
   if(!ok)
     {
      g_fail++;
      Print("CheckBookState FAIL: ", what);
     }
  }

//------------------------------------------------------------------//
// deterministic synthetic feed (== CheckBookOrchestrator.mq5)      //
//------------------------------------------------------------------//
void MakeRaw(const int i, double &raw[])
  {
   double nan = SatNan();
   for(int j = 0; j < 37; j++)
     {
      if(i > 0 && ((i + j) % 17) == 0)
         raw[j] = nan;
      else
         raw[j] = 100.0 + j + 0.5 * MathSin(0.31 * i + 0.7 * j);
     }
  }

bool FeedCore(CBookOrchestrator &orc)
  {
   if(!orc.BeginCoreSegment())
      return false;
   for(int leg = 0; leg < 9; leg++)
      for(int i = 0; i < CBS_NCOREH; i++)
        {
         long ts = CBS_H0 + (long)i * 3600;
         double bo = 1.0, bh = 1.002, bl = 0.999, bc = 1.0005;
         if(!orc.StepCoreLegBar(leg, ts, bo, bh, bl, bc,
                                bo + 0.001, bh + 0.001, bl + 0.001, bc + 0.001,
                                0.9, 0.0, 0.0, 0.0, 0.8))
            return false;
        }
   if(!orc.EndCoreSegment())
      return false;
   return orc.SetCoreFeedDone();
  }

// drive H1 bars [from, to) each followed by its 3 minutes; optionally
// record every emitted row into the tail arrays
bool DriveBars(CBookOrchestrator &orc, const int from, const int to,
               const bool record, long &ets[], string &esym[], double &eval[],
               int &en, string &why)
  {
   double raw[37];
   bool   has[31];
   double bo31[31], ao31[31], bc31[31], ac31[31], bl31[31], ah31[31];
   double eurq_cross[8], swl[31], sws[31];
   for(int k = 0; k < 31; k++)
     {
      has[k]  = true;
      bo31[k] = 1.0;
      ao31[k] = 1.001;
      bc31[k] = 1.0005;
      ac31[k] = 1.0015;
      bl31[k] = 0.999;
      ah31[k] = 1.003;
      swl[k]  = 0.0;
      sws[k]  = 0.0;
     }
   for(int c = 0; c < 8; c++)
      eurq_cross[c] = 0.9;

   for(int i = from; i < to; i++)
     {
      long ts = CBS_H0 + (long)i * 3600;
      MakeRaw(i, raw);
      if(!orc.StepH1(ts, raw))
        {
         why = StringFormat("StepH1 bar %d: %s", i, orc.LastError());
         return false;
        }
      if(record)
         for(int r = 0; r < orc.EmitCount(); r++)
           {
            int cap = ArraySize(ets);
            if(en >= cap)
              {
               ArrayResize(ets, cap + 512);
               ArrayResize(esym, cap + 512);
               ArrayResize(eval, cap + 512);
              }
            ets[en]  = orc.EmitTs(r);
            esym[en] = orc.EmitSymbol(r);
            eval[en] = orc.EmitFrac(r);
            en++;
           }
      for(int m = 0; m < CBS_MPH; m++)
         if(!orc.StepM1(ts + (long)m * 60, has, bo31, ao31, bc31, ac31,
                        bl31, ah31, eurq_cross, swl, sws))
           {
            why = StringFormat("StepM1 hour %d min %d: %s", i, m, orc.LastError());
            return false;
           }
     }
   return true;
  }

bool FinalizeRecord(CBookOrchestrator &orc, long &ets[], string &esym[],
                    double &eval[], int &en, string &why)
  {
   if(!orc.FinalizeH1())
     {
      why = "FinalizeH1: " + orc.LastError();
      return false;
     }
   for(int r = 0; r < orc.EmitCount(); r++)
     {
      int cap = ArraySize(ets);
      if(en >= cap)
        {
         ArrayResize(ets, cap + 512);
         ArrayResize(esym, cap + 512);
         ArrayResize(eval, cap + 512);
        }
      ets[en]  = orc.EmitTs(r);
      esym[en] = orc.EmitSymbol(r);
      eval[en] = orc.EmitFrac(r);
      en++;
     }
   return true;
  }

//------------------------------------------------------------------//
// file helpers (tamper tests)                                      //
//------------------------------------------------------------------//
bool ReadCommonFile(const string fname, string &out)
  {
   int fh = FileOpen(fname, FILE_READ | FILE_BIN | FILE_COMMON);
   if(fh == INVALID_HANDLE)
      return false;
   int n = (int)FileSize(fh);
   uchar b[];
   if(n <= 0 || FileReadArray(fh, b, 0, n) != (uint)n)
     {
      FileClose(fh);
      return false;
     }
   FileClose(fh);
   out = CharArrayToString(b, 0, n, CP_UTF8);
   return true;
  }

bool WriteCommonFile(const string fname, const string content)
  {
   int fh = FileOpen(fname, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(fh == INVALID_HANDLE)
      return false;
   uchar b[];
   int n = StringToCharArray(content, b, 0, WHOLE_ARRAY, CP_UTF8) - 1;
   if(n < 0)
      n = 0;
   bool ok = (n == 0 || FileWriteArray(fh, b, 0, n) == (uint)n);
   FileClose(fh);
   return ok;
  }

// split full state text into payload (before trailer) — false if none
bool SplitPayload(const string s, string &payload)
  {
   string mark = ", \"fnv64\": \"";
   int mp = -1, sp = 0;
   while(true)
     {
      int q = StringFind(s, mark, sp);
      if(q < 0)
         break;
      mp = q;
      sp = q + 1;
     }
   if(mp < 0)
      return false;
   payload = StringSubstr(s, 0, mp);
   return true;
  }

// payload -> full state text with a FRESH valid trailer
string WithFreshTrailer(const string payload)
  {
   uchar b[];
   int n = StringToCharArray(payload, b, 0, WHOLE_ARRAY, CP_UTF8) - 1;
   if(n < 0)
      n = 0;
   ulong h = BookStateFnv1a(b, n, BOOKSTATE_FNV_OFFSET);
   return payload + StringFormat(", \"fnv64\": \"%016I64x\", \"eof\": true}", h);
  }

// multiply the number after `"key": ` (searching at/after from) by mul
bool TamperNumber(string &s, const int from, const string key, const double mul)
  {
   string pat = "\"" + key + "\": ";
   int p = StringFind(s, pat, from);
   if(p < 0)
      return false;
   int v0 = p + StringLen(pat);
   int v1 = v0;
   int n = StringLen(s);
   while(v1 < n)
     {
      ushort c = StringGetCharacter(s, v1);
      if(c == ',' || c == '}' || c == ']')
         break;
      v1++;
     }
   double v = SatParseDouble(StringSubstr(s, v0, v1 - v0));
   s = StringSubstr(s, 0, v0) + BookStateNum(v * mul) + StringSubstr(s, v1);
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   Print("CheckBookState: split/continue + refuse-latch gate ...");
   string why = "";
   long   ets_a[], ets_b[];
   string esym_a[], esym_b[];
   double eval_a[], eval_b[];
   int    en_a = 0, en_b = 0;

   //=== run A: drive to the split, save, continue to the end ===========
   CBookOrchestrator orcA;
   Expect(orcA.Init(), "A Init: " + orcA.LastError());
   if(!orcA.Ready())
      return;
   Expect(FeedCore(orcA), "A core feed: " + orcA.LastError());
   if(!DriveBars(orcA, 0, CBS_SPLIT + 1, false, ets_a, esym_a, eval_a, en_a, why))
     {
      Expect(false, "A pre-split drive: " + why);
      return;
     }
   CBookState bsA;
   Expect(!bsA.Ready() && !bsA.RefuseToTrade(), "fresh latch state not sane");
   Expect(bsA.Save(orcA, CBS_FILE), "A Save: " + bsA.LastError());
   PrintFormat("CheckBookState: saved at H1 bar %d (h1_bars=%I64d m1=%I64d "
               "hours=%I64d) -> %s", CBS_SPLIT, orcA.H1Bars(), orcA.M1Bars(),
               orcA.TotalHours(), CBS_FILE);
   if(!DriveBars(orcA, CBS_SPLIT + 1, CBS_NSATH, true,
                 ets_a, esym_a, eval_a, en_a, why)
      || !FinalizeRecord(orcA, ets_a, esym_a, eval_a, en_a, why))
     {
      Expect(false, "A post-split drive: " + why);
      return;
     }

   //=== T1: run B = fresh Init + Load + identical remaining feed ========
   CBookOrchestrator orcB;
   Expect(orcB.Init(), "B Init: " + orcB.LastError());
   CBookState bsB;
   bool loaded = bsB.Load(orcB, CBS_FILE);
   Expect(loaded, "B Load: " + bsB.LastError());
   Expect(bsB.Ready() && !bsB.RefuseToTrade(), "B latch not READY after load");
   if(!loaded)
      return;
   PrintFormat("CheckBookState T1: restored (j_hour=%I64d j_saved=%.17g "
               "j_restored=%.17g rel_jump=%.3g)",
               bsB.JHour(), bsB.JSaved(), bsB.JRestored(), bsB.RelJump());
   Expect(orcB.H1Bars() == CBS_SPLIT + 1, "B h1_bars restored wrong");
   Expect(orcB.CoreFeedDone(), "B core_done not restored");
   Expect(orcB.AFirst() == orcA.AFirst(), "B a_first != A a_first (bitwise)");
   Expect(orcB.BFirst() == orcA.BFirst(), "B b_first != A b_first (bitwise)");
   if(!DriveBars(orcB, CBS_SPLIT + 1, CBS_NSATH, true,
                 ets_b, esym_b, eval_b, en_b, why)
      || !FinalizeRecord(orcB, ets_b, esym_b, eval_b, en_b, why))
     {
      Expect(false, "B post-load drive: " + why);
      return;
     }
   Expect(en_a == en_b, StringFormat("tail row count A %d != B %d", en_a, en_b));
   int n_cmp = (en_a < en_b) ? en_a : en_b;
   int n_diff = 0;
   for(int r = 0; r < n_cmp; r++)
      if(ets_a[r] != ets_b[r] || esym_a[r] != esym_b[r]
         || !(eval_a[r] == eval_b[r]))
        {
         if(n_diff == 0)
            PrintFormat("first tail divergence row %d: A(%I64d,%s,%.17g) "
                        "B(%I64d,%s,%.17g)", r, ets_a[r], esym_a[r], eval_a[r],
                        ets_b[r], esym_b[r], eval_b[r]);
         n_diff++;
        }
   Expect(n_diff == 0, StringFormat("T1: %d tail rows NOT bitwise-identical", n_diff));
   Expect(orcA.BEqC() == orcB.BEqC(),         "T1: final b eq_c differs");
   Expect(orcA.BBalance() == orcB.BBalance(), "T1: final b balance differs");
   Expect(orcA.BTrades() == orcB.BTrades(),   "T1: final b n_trades differs");
   Expect(orcA.LastAH() == orcB.LastAH(),     "T1: final a_h differs");
   Expect(orcA.LastBH() == orcB.LastBH(),     "T1: final b_h differs");
   Expect(orcA.TotalRows() == orcB.TotalRows(), "T1: total_rows differs");
   PrintFormat("CheckBookState T1: %d tail rows bitwise-identical; final "
               "b_eq=%.17g a_h=%.17g b_h=%.17g", n_cmp, orcB.BEqC(),
               orcB.LastAH(), orcB.LastBH());

   //=== T2: end-state files byte-identical ==============================
   Expect(bsA.Save(orcA, CBS_FILE_ENDA), "A end Save: " + bsA.LastError());
   Expect(bsB.Save(orcB, CBS_FILE_ENDB), "B end Save: " + bsB.LastError());
   string endA = "", endB = "";
   Expect(ReadCommonFile(CBS_FILE_ENDA, endA), "read endA");
   Expect(ReadCommonFile(CBS_FILE_ENDB, endB), "read endB");
   Expect(StringLen(endA) > 0 && endA == endB,
          StringFormat("T2: end-state files differ (lenA %d lenB %d)",
                       StringLen(endA), StringLen(endB)));
   PrintFormat("CheckBookState T2: end-state round-trip byte-identical "
               "(%d bytes)", StringLen(endA));

   //=== T3/T4/T5/T6: tamper battery on the mid-save file =================
   string full = "";
   Expect(ReadCommonFile(CBS_FILE, full), "read mid-save file");
   string payload = "";
   Expect(SplitPayload(full, payload), "trailer split");

   // T3 torn write (truncated file)
     {
      string torn = StringSubstr(full, 0, StringLen(full) - 60);
      Expect(WriteCommonFile(CBS_FILE_TMP, torn), "T3 write");
      CBookOrchestrator o3;
      Expect(o3.Init(), "T3 Init");
      CBookState b3;
      Expect(!b3.Load(o3, CBS_FILE_TMP), "T3: truncated file LOADED");
      Expect(b3.RefuseToTrade(), "T3: refuse latch not set");
      Expect(StringFind(b3.RefuseReason(), "TORN") >= 0,
             "T3: reason not TORN: " + b3.RefuseReason());
      Print("CheckBookState T3 refuse: ", b3.RefuseReason());
     }

   // T4 payload bit-flip, stale fnv
     {
      string flip = full;
      int fp = StringFind(flip, "\"b_eqc\": ");
      Expect(fp > 0, "T4 anchor key");
      // replace the char 12 positions after the key start (a digit)
      int cp = fp + 12;
      string flipped = StringSubstr(flip, 0, cp)
                       + ((StringGetCharacter(flip, cp) == '1') ? "2" : "1")
                       + StringSubstr(flip, cp + 1);
      Expect(WriteCommonFile(CBS_FILE_TMP, flipped), "T4 write");
      CBookOrchestrator o4;
      Expect(o4.Init(), "T4 Init");
      CBookState b4;
      Expect(!b4.Load(o4, CBS_FILE_TMP), "T4: bit-flipped file LOADED");
      Expect(b4.RefuseToTrade()
             && StringFind(b4.RefuseReason(), "CHECKSUM") >= 0,
             "T4: reason not CHECKSUM: " + b4.RefuseReason());
      Print("CheckBookState T4 refuse: ", b4.RefuseReason());
     }

   // T5 continuity a_first corrupted 1% (valid fnv) -> anchor guard
     {
      string t5 = payload;
      int cpos = StringFind(t5, "\"continuity\": {");
      Expect(cpos > 0, "T5 continuity block");
      Expect(TamperNumber(t5, cpos, "a_first", 1.01), "T5 tamper");
      Expect(WriteCommonFile(CBS_FILE_TMP, WithFreshTrailer(t5)), "T5 write");
      CBookOrchestrator o5;
      Expect(o5.Init(), "T5 Init");
      CBookState b5;
      Expect(!b5.Load(o5, CBS_FILE_TMP), "T5: corrupt a_first LOADED");
      Expect(b5.RefuseToTrade()
             && StringFind(b5.RefuseReason(), "A-ANCHOR") >= 0,
             "T5: reason not A-ANCHOR: " + b5.RefuseReason());
      Print("CheckBookState T5 refuse: ", b5.RefuseReason());
     }

   // T6 consistent 1% re-base (sampler first_v + continuity a_first):
   // passes the anchor equality, MUST trip the j-splice latch
     {
      string t6 = payload;
      int spos = StringFind(t6, "\"samplers\": {\"a\": ");
      Expect(spos > 0, "T6 sampler block");
      Expect(TamperNumber(t6, spos, "first_v", 1.01), "T6 tamper sampler");
      int cpos = StringFind(t6, "\"continuity\": {");
      Expect(cpos > 0, "T6 continuity block");
      Expect(TamperNumber(t6, cpos, "a_first", 1.01), "T6 tamper continuity");
      Expect(WriteCommonFile(CBS_FILE_TMP, WithFreshTrailer(t6)), "T6 write");
      CBookOrchestrator o6;
      Expect(o6.Init(), "T6 Init");
      CBookState b6;
      Expect(!b6.Load(o6, CBS_FILE_TMP), "T6: re-based state LOADED");
      Expect(b6.RefuseToTrade()
             && StringFind(b6.RefuseReason(), "J-SPLICE") >= 0,
             "T6: reason not J-SPLICE: " + b6.RefuseReason());
      Print("CheckBookState T6 refuse: ", b6.RefuseReason());
     }

   //=== T7: Save inside an open core segment must refuse =================
     {
      CBookOrchestrator o7;
      Expect(o7.Init(), "T7 Init");
      Expect(o7.BeginCoreSegment(), "T7 BeginCoreSegment");
      CBookState b7;
      Expect(!b7.Save(o7, CBS_FILE_TMP), "T7: mid-segment Save not refused");
      Print("CheckBookState T7 refuse: ", b7.LastError());
     }

   if(g_fail == 0)
      Print("CheckBookState: ALL PASS");
   else
      PrintFormat("CheckBookState: %d FAILURES", g_fail);
  }
//+------------------------------------------------------------------+
