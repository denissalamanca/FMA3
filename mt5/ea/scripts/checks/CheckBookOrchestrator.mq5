//+------------------------------------------------------------------+
//| CheckBookOrchestrator.mq5 — compile/smoke gate for               |
//| Book/BookOrchestrator.mqh (UNIT 1 of the S1 R1 whole-book gate). |
//|                                                                  |
//| NO trading functions, NO files. Drives CBookOrchestrator over a  |
//| SYNTHETIC ~50-hour span exercising every seam of the drive       |
//| contract:                                                        |
//|   * one CoreSim segment fed leg-major (9 legs x 52 hourly bars,  |
//|     frozen-style tgt) -> EndCoreSegment -> ComputeFCore rows;    |
//|   * 50 H1 signal bars (37-symbol synthetic closes with NaN       |
//|     holes) through the harness_sim driving loop -> f_sat ->      |
//|     blend -> emission (deferred one-bar SC lag);                 |
//|   * 3 M1 sat rows per hour through SatEquityNative with the      |
//|     HELD prior-hour f_sat tgt;                                   |
//|   * FinalizeH1 flushing the deferred row + 2 trailing core-only  |
//|     hours (core grid extends 2h past the sat grid);              |
//|   * guard checks: non-ascending M1 stamp, unaligned H1 stamp,    |
//|     FinalizeH1 before SetCoreFeedDone.                           |
//|                                                                  |
//| This is a STRUCTURAL gate (wiring, grids, emission shape, state  |
//| plumbing) — numeric parity vs the golden FMA3_fed_frac_v3.csv is |
//| the S1 harness's job (frozen input bundles), not this check's.   |
//|                                                                  |
//| The terminal Print output must end with                          |
//| "CheckBookOrchestrator: ALL PASS".                               |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Book/BookOrchestrator.mqh>

#define CBO_H0     1578268800   // 2020-01-06 00:00:00 UTC (Monday)
#define CBO_NSATH  50           // sat/H1 grid hours
#define CBO_NCOREH 52           // core grid hours (2 trailing core-only)
#define CBO_MPH    3            // M1 rows per hour

int g_fail = 0;

void Expect(const bool ok, const string what)
  {
   if(!ok)
     {
      g_fail++;
      Print("CheckBookOrchestrator FAIL: ", what);
     }
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   Print("CheckBookOrchestrator: synthetic 50-bar wiring smoke ...");
   double nan = SatNan();

   CBookOrchestrator orc;
   Expect(orc.Init(), "Init failed: " + orc.LastError());
   if(!orc.Ready())
      return;

   //--- structure -----------------------------------------------------
   Expect(orc.NetCount() == 33, "NetCount != 33");
   Expect(orc.NetSymbolAt(0) == "AUDCAD" && orc.NetSymbolAt(32) == "XTIUSD",
          "net column range");
   int n_us = 0;
   for(int k = 0; k < orc.NetCount(); k++)
      if(orc.NetSymbolAt(k) == "AUDUSD" || orc.NetSymbolAt(k) == "NZDUSD")
         n_us++;
   Expect(n_us == 2, "core-only symbols missing from the net union");
   Print("CheckBookOrchestrator structure: 33 net columns (",
         orc.NetSymbolAt(0), " .. ", orc.NetSymbolAt(32), ")");

   //--- core segment: 9 legs x 52 hourly bars, leg-major ---------------
   Expect(orc.BeginCoreSegment(), "BeginCoreSegment: " + orc.LastError());
   for(int leg = 0; leg < 9; leg++)
      for(int i = 0; i < CBO_NCOREH; i++)
        {
         long ts = CBO_H0 + (long)i * 3600;
         double bo = 1.0, bh = 1.002, bl = 0.999, bc = 1.0005;
         double ao = bo + 0.001, ah = bh + 0.001, al = bl + 0.001, ac = bc + 0.001;
         if(!orc.StepCoreLegBar(leg, ts, bo, bh, bl, bc, ao, ah, al, ac,
                                0.9, 0.0, 0.0, 0.0, 0.8))
           {
            Expect(false, StringFormat("StepCoreLegBar leg %d bar %d: %s",
                                       leg, i, orc.LastError()));
            return;
           }
        }
   Expect(orc.EndCoreSegment(), "EndCoreSegment: " + orc.LastError());
   Expect(orc.CoreSegments() == 1, "CoreSegments != 1");
   Expect(orc.FCoreRows() == CBO_NCOREH,
          StringFormat("FCoreRows %d != %d", orc.FCoreRows(), CBO_NCOREH));
   Expect(orc.AFirst() > 0.0, "a_first not captured");
   PrintFormat("CheckBookOrchestrator core: 1 segment, %d f_core rows, "
               "a_first=%.17g seed_next=%.17g",
               orc.FCoreRows(), orc.AFirst(), orc.CoreSeed());

   //--- guard: FinalizeH1 before SetCoreFeedDone must refuse -----------
   Expect(!orc.FinalizeH1(), "FinalizeH1 before SetCoreFeedDone not refused");
   Expect(orc.SetCoreFeedDone(), "SetCoreFeedDone: " + orc.LastError());

   //--- H1 + M1 interleaved drive --------------------------------------
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

   long hours_emitted = 0;
   long last_emit_ts = -1;
   bool emit_ordered = true;
   for(int i = 0; i < CBO_NSATH; i++)
     {
      long ts = CBO_H0 + (long)i * 3600;
      // synthetic closes: gentle per-symbol wave, NaN holes after bar 0
      for(int j = 0; j < 37; j++)
        {
         if(i > 0 && ((i + j) % 17) == 0)
            raw[j] = nan;                       // symbol printed no bar
         else
            raw[j] = 100.0 + j + 0.5 * MathSin(0.31 * i + 0.7 * j);
        }
      if(!orc.StepH1(ts, raw))
        {
         Expect(false, StringFormat("StepH1 bar %d: %s", i, orc.LastError()));
         return;
        }
      // emissions of the PREVIOUS grid hour (deferred SC lag)
      int ne = orc.EmitCount();
      if(i == 0)
         Expect(ne == 0, "bar 0 must emit nothing (deferred SC)");
      else
        {
         Expect(ne > 0, StringFormat("bar %d emitted nothing", i));
         for(int r = 0; r < ne; r++)
           {
            if(orc.EmitTs(r) < last_emit_ts)
               emit_ordered = false;
            last_emit_ts = orc.EmitTs(r);
           }
         Expect(orc.LastEmitHour() == ts - 3600,
                StringFormat("bar %d emitted hour %I64d, want %I64d",
                             i, orc.LastEmitHour(), ts - 3600));
         hours_emitted++;
        }
      // minutes of hour i (drive contract 2: after StepH1(ts))
      for(int m = 0; m < CBO_MPH; m++)
         if(!orc.StepM1(ts + (long)m * 60, has, bo31, ao31, bc31, ac31,
                        bl31, ah31, eurq_cross, swl, sws))
           {
            Expect(false, StringFormat("StepM1 hour %d min %d: %s",
                                       i, m, orc.LastError()));
            return;
           }
     }
   Expect(hours_emitted == CBO_NSATH - 1,
          StringFormat("emitted %I64d hours during drive, want %d",
                       hours_emitted, CBO_NSATH - 1));

   //--- guards on the live streams --------------------------------------
   Expect(!orc.StepM1(orc.M1Bars() > 0 ? CBO_H0 : 0, has, bo31, ao31,
                      bc31, ac31, bl31, ah31, eurq_cross, swl, sws),
          "non-ascending M1 stamp not refused");
   Expect(!orc.StepH1(CBO_H0 + (long)CBO_NSATH * 3600 + 7, raw),
          "unaligned H1 stamp not refused");

   //--- finalize: deferred last row + 2 trailing core-only hours --------
   if(!orc.FinalizeH1())
     {
      Expect(false, "FinalizeH1: " + orc.LastError());
      return;
     }
   int nf = orc.EmitCount();
   Expect(nf > 0, "FinalizeH1 emitted nothing");
   for(int r = 0; r < nf; r++)
     {
      if(orc.EmitTs(r) < last_emit_ts)
         emit_ordered = false;
      last_emit_ts = orc.EmitTs(r);
     }
   Expect(emit_ordered, "emission stamps not ascending");
   Expect(orc.TotalHours() == CBO_NCOREH,
          StringFormat("TotalHours %I64d != %d (sat 50 + core-only 2)",
                       orc.TotalHours(), CBO_NCOREH));
   Expect(orc.LastEmitHour() == CBO_H0 + (long)(CBO_NCOREH - 1) * 3600,
          "last emitted hour != trailing core-only hour");
   Expect(orc.FCoreCursor() == orc.FCoreRows(), "f_core rows not fully consumed");
   Expect(!orc.FinalizeH1(), "double FinalizeH1 not refused");

   //--- state summary ----------------------------------------------------
   PrintFormat("CheckBookOrchestrator state: h1_bars=%I64d m1_bars=%I64d "
               "hours=%I64d rows=%I64d sentinels=%I64d",
               orc.H1Bars(), orc.M1Bars(), orc.TotalHours(),
               orc.TotalRows(), orc.TotalSentinels());
   PrintFormat("CheckBookOrchestrator equity: a_first=%.17g b_first=%.17g "
               "last a_h=%.17g b_h=%.17g b_bal=%.17g b_trades=%I64d",
               orc.AFirst(), orc.BFirst(), orc.LastAH(), orc.LastBH(),
               orc.BBalance(), orc.BTrades());
   string tail = "";
   int n_show = orc.EmitCount() < 6 ? orc.EmitCount() : 6;
   for(int r = 0; r < n_show; r++)
      tail += StringFormat("%I64d,%s,%.12f ", orc.EmitTs(r),
                           orc.EmitSymbol(r), orc.EmitFrac(r));
   Print("CheckBookOrchestrator final-call rows (first ", n_show, "): ", tail);

   if(g_fail == 0)
      Print("CheckBookOrchestrator: ALL PASS");
   else
      PrintFormat("CheckBookOrchestrator: %d FAILURES", g_fail);
  }
//+------------------------------------------------------------------+
