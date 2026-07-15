//+------------------------------------------------------------------+
//| CheckFeedAssembler.mq5 — synthetic-bar smoke for                  |
//| Book/FeedAssembler.mqh (CFeedAssembler, UNIT A of the S2 feed     |
//| work).                                                            |
//|                                                                   |
//| SCRIPT (OnStart), ZERO trading functions, ZERO CopyRates — every  |
//| bar is synthetic and pushed through the same PushBar/AdvanceTo    |
//| path the live PollTerminal uses, so the whole causal state        |
//| machine is exercised without a feed:                              |
//|   1. ask reconstruction  ask = bid + spread_points*point (bitwise)|
//|   2. float32 price quantization ((float) cast — BH_ENGINE_SPEC §7)|
//|   3. union-grid rule: a minute with no bar of any symbol is NOT a |
//|      row; has_bar mask + ffill carry for absent symbols           |
//|   4. eurq = 1/(0.5*(f32 cross bid_c + f32 cross ask_c)), carried  |
//|   5. swap columns via CSwapEurqBH: server-midnight rollover,      |
//|      Wednesday x3 for FX, crypto every calendar day (bitwise vs   |
//|      the SE_* primitives)                                         |
//|   6. causal H1 boundary: hour h finalizes at grid progress        |
//|      h+3600; H1 close[37] = float64 mid of the LAST bar in the    |
//|      hour, NaN where no bar                                       |
//|   7. drive contract: the hour's M1 rows drain ONLY after PopH1Row |
//|   8. CoreSignal daily mids incl. the EURGBP pre-20:00 variant     |
//|   9. cold-start: unready rows before all 31+crosses seeded;       |
//|      stamp-regression pushes rejected                             |
//|                                                                   |
//| The VALUE-level proof against the frozen record is the python     |
//| mirror (research/bpure/feed/feed_assembler_mirror.py — bit-exact  |
//| vs FMA3_bh_inputs_<Q>.csv x24 + FMA3_v34_inputs.csv); this        |
//| script proves the MQL5 twin's mechanics compile and behave. The   |
//| terminal run of the live path (PollTerminal) is STAGED — owner-   |
//| executed, ledgered FMA3-RECON-N.                                  |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

#include <Book/FeedAssembler.mqh>

int g_pass = 0;
int g_fail = 0;

void Check(const string name, const bool ok)
  {
   if(ok)
      g_pass++;
   else
     {
      g_fail++;
      PrintFormat("CheckFeedAssembler FAIL: %s", name);
     }
  }

bool IsNanD(const double v) { return v != v; }

//+------------------------------------------------------------------+
void OnStart()
  {
   CFeedAssembler fa;
   Check("Init(synthetic)", fa.Init(false));

   int iEU  = fa.SymIndex("EURUSD");
   int iBTC = fa.SymIndex("BTCUSD");
   int iXAU = fa.SymIndex("XAUUSD");
   int iEG  = fa.SymIndex("EURGBP");
   Check("symbol map", iEU == 13 && iBTC == 21 && iXAU == 32 && iEG == 8);

   //--- seed every symbol + cross (cold-start pre rule injection) ----
   for(int i = 0; i < FA_NSYM; i++)
      Check("seed", fa.SeedSymbol(i, 1.0 + i, 1.5 + i, 0.5 + i, 1.25 + i, 10));
   const string crosses[FA_NCROSS] =
     {"EURCAD", "EURCHF", "EURGBP", "EURJPY",
      "EURNOK", "EURNZD", "EURSEK", "EURUSD"};
   for(int c = 0; c < FA_NCROSS; c++)
      fa.SeedCrossValue(crosses[c], 1.1 + c * 0.01, 1.1 + c * 0.01 + 0.0002);
   Check("all book seeded", fa.AllBookSeeded());
   Check("pre_seed_hits == 37", fa.PreSeedHits() == FA_NSYM);

   //--- synthetic timeline: 2024.01.02 (Tue) -> 2024.01.03 (Wed) -----
   long ts0 = (long)D'2024.01.02 00:00';      // Tuesday
   double ptEU  = MathPow(10.0, -5);
   double ptBTC = MathPow(10.0, -2);
   double ptXAU = MathPow(10.0, -2);
   double ptEG  = MathPow(10.0, -5);

   // minute ts0: EURUSD + BTCUSD
   Check("push EU ts0",
         fa.PushBar(iEU, ts0, 1.10501, 1.10577, 1.10444, 1.10555, 12));
   Check("push BTC ts0",
         fa.PushBar(iBTC, ts0, 42000.50, 42050.25, 41900.75, 42010.10, 1500));
   // duplicate stamp for the same symbol must be rejected
   Check("dup stamp rejected",
         !fa.PushBar(iBTC, ts0, 1.0, 1.0, 1.0, 1.0, 1));
   // minute ts0+60: BTC only (EURUSD carries)
   Check("push BTC +60",
         fa.PushBar(iBTC, ts0 + 60, 42010.10, 42031.00, 42000.00, 42020.20, 1500));
   // minute ts0+120: NO bars (must not become a union row)
   // minute ts0+180: EURUSD + BTCUSD
   Check("push EU +180",
         fa.PushBar(iEU, ts0 + 180, 1.10556, 1.10561, 1.10540, 1.10560, 10));
   Check("push BTC +180",
         fa.PushBar(iBTC, ts0 + 180, 42020.20, 42044.00, 42015.50, 42033.30, 1500));
   // 10:00 XAU + BTC
   long ts10 = ts0 + 10 * 3600;
   Check("push XAU 10:00",
         fa.PushBar(iXAU, ts10, 2064.80, 2066.10, 2064.20, 2065.55, 25));
   Check("push BTC 10:00",
         fa.PushBar(iBTC, ts10, 42100.00, 42130.00, 42080.00, 42111.10, 1500));
   // 19:30 XAU
   long ts1930 = ts0 + 19 * 3600 + 30 * 60;
   Check("push XAU 19:30",
         fa.PushBar(iXAU, ts1930, 2069.90, 2070.60, 2069.10, 2070.15, 25));
   // 19:59 EURGBP (pre-20 qualifying)
   long ts1959 = ts0 + 19 * 3600 + 59 * 60;
   Check("push EG 19:59",
         fa.PushBar(iEG, ts1959, 0.86670, 0.86681, 0.86660, 0.86677, 9));
   // 20:30 EURGBP (NOT pre-20)
   long ts2030 = ts0 + 20 * 3600 + 30 * 60;
   Check("push EG 20:30",
         fa.PushBar(iEG, ts2030, 0.86690, 0.86711, 0.86685, 0.86700, 9));
   // Jan 3 00:00 (Wednesday): EURUSD + XAU + EG
   long ts1d = ts0 + 86400;
   Check("push EU d2", fa.PushBar(iEU, ts1d, 1.10460, 1.10470, 1.10430, 1.10444, 11));
   Check("push XAU d2", fa.PushBar(iXAU, ts1d, 2070.90, 2071.40, 2070.50, 2071.00, 30));
   Check("push EG d2", fa.PushBar(iEG, ts1d, 0.86685, 0.86695, 0.86675, 0.86690, 9));
   Check("advance", fa.AdvanceTo(ts1d + 60));

   //--- counters ------------------------------------------------------
   Check("8 union minutes committed", fa.MinutesCommitted() == 8);
   Check("8 b rows", fa.BRows() == 8);
   Check("4 H1 rows (Jan2 00,10,19,20)", fa.H1Rows() == 4);
   Check("no unready rows (fully seeded)", fa.UnreadyRows() == 0);

   //--- drive contract: nothing drains before the hour is popped ------
   Check("M1 held before PopH1", fa.M1Available() == 0);
   SFaM1Row mr;
   Check("PopM1 refused before PopH1", !fa.PopM1Row(mr));

   //--- hour 00 --------------------------------------------------------
   SFaH1Row h1;
   Check("H1 ready", fa.H1Ready() && fa.PeekH1Ts() == ts0);
   Check("PopH1 hour00", fa.PopH1Row(h1) && h1.ts == ts0);
   double euMid = (1.10560 + (1.10560 + 10 * ptEU)) / 2.0;   // last EU bar of h00
   double btcMid = (42033.30 + (42033.30 + 1500 * ptBTC)) / 2.0;
   Check("h00 close EURUSD = last f64 mid", h1.close[iEU] == euMid);
   Check("h00 close BTCUSD = last f64 mid", h1.close[iBTC] == btcMid);
   Check("h00 XAU close NaN (no bar)", IsNanD(h1.close[iXAU]) && !h1.has[iXAU]);
   Check("h00 has EU/BTC", h1.has[iEU] && h1.has[iBTC]);
   Check("h00 buffered 3 m1 rows", h1.m1_rows == 3);

   //--- m1 rows of hour 00 ---------------------------------------------
   Check("M1Available == 3", fa.M1Available() == 3);
   Check("pop m1 ts0", fa.PopM1Row(mr) && mr.ts == ts0 && mr.ready);
   // slot indices in SATEQ order: EURUSD=14, BTCUSD=3
   double spEU = 12 * ptEU;
   Check("f32 quantization bo",
         mr.bo[14] == (double)(float)1.10501);
   Check("ask recon + f32 ao",
         mr.ao[14] == (double)(float)(1.10501 + spEU));
   Check("ask recon + f32 ah",
         mr.ah[14] == (double)(float)(1.10577 + spEU));
   Check("has mask ts0", mr.has[14] && mr.has[3] && !mr.has[26]);
   // eurq[7] = EURUSD cross from THIS minute's close
   double eurqEU = 1.0 / (0.5 * ((double)(float)1.10555
                                 + (double)(float)(1.10555 + spEU)));
   Check("eurq EURUSD from cross close", mr.eurq[7] == eurqEU);
   // seeded cross carry for EURJPY (index 3 in cross order)
   double eurqJP = 1.0 / (0.5 * ((double)(float)(1.1 + 3 * 0.01)
                                 + (double)(float)(1.1 + 3 * 0.01 + 0.0002)));
   Check("eurq EURJPY from seed", mr.eurq[3] == eurqJP);
   // swap at the first bar >= midnight Tuesday: FX mult 1, crypto fires
   SE_InitTables();
   double lp, sp;
   SE_SwapAnnualPct(SE_SymId("EURUSD"), ts0, lp, sp);
   Check("swap EURUSD Tue x1",
         mr.swl[14] == lp / 100.0 / 365.0 * 1.0
         && mr.sws[14] == sp / 100.0 / 365.0 * 1.0);
   SE_SwapAnnualPct(SE_SymId("BTCUSD"), ts0, lp, sp);
   Check("swap BTCUSD crypto", mr.swl[3] == lp / 100.0 / 365.0 * 1.0);

   Check("pop m1 ts0+60", fa.PopM1Row(mr) && mr.ts == ts0 + 60);
   Check("carry EURUSD when has=0",
         !mr.has[14] && mr.bc[14] == (double)(float)1.10555
         && mr.ao[14] == (double)(float)(1.10501 + spEU));
   Check("eurq carried", mr.eurq[7] == eurqEU);
   Check("swap zero off-rollover", mr.swl[14] == 0.0 && mr.sws[3] == 0.0);
   Check("pop m1 ts0+180 (00:02 skipped)",
         fa.PopM1Row(mr) && mr.ts == ts0 + 180);
   Check("m1 drained", fa.M1Available() == 0 && !fa.PopM1Row(mr));

   //--- hours 10 / 19 / 20 ----------------------------------------------
   Check("PopH1 hour10", fa.PopH1Row(h1) && h1.ts == ts0 + 10 * 3600);
   double xauMid = (2065.55 + (2065.55 + 25 * ptXAU)) / 2.0;
   Check("h10 XAU close", h1.close[iXAU] == xauMid && h1.has[iXAU]);
   Check("h10 EU NaN", IsNanD(h1.close[iEU]));
   Check("h10 m1 rows drain", fa.M1Available() == 1 && fa.PopM1Row(mr)
         && mr.ts == ts10 && mr.has[27] && mr.has[3] && !mr.has[14]);
   Check("PopH1 hour19", fa.PopH1Row(h1) && h1.ts == ts0 + 19 * 3600);
   double egMid1959 = (0.86677 + (0.86677 + 9 * ptEG)) / 2.0;
   Check("h19 EG close = 19:59 mid", h1.close[iEG] == egMid1959);
   Check("h19 rows", fa.M1Available() == 2);
   Check("pop 19:30", fa.PopM1Row(mr) && mr.ts == ts1930);
   Check("pop 19:59", fa.PopM1Row(mr) && mr.ts == ts1959);
   Check("PopH1 hour20", fa.PopH1Row(h1) && h1.ts == ts0 + 20 * 3600);
   double egMid2030 = (0.86700 + (0.86700 + 9 * ptEG)) / 2.0;
   Check("h20 EG close = 20:30 mid", h1.close[iEG] == egMid2030);
   Check("pop 20:30", fa.PopM1Row(mr) && mr.ts == ts2030);
   Check("Jan3 hour not finalized yet", !fa.H1Ready());

   //--- daily mids (emitted at the Jan3 00:00 commits) -------------------
   Check("2 daily mids emitted", fa.MidAvailable() == 2);
   SFaDailyMid md;
   bool gotXau = false, gotEg = false;
   while(fa.MidAvailable() > 0 && fa.PopMid(md))
     {
      if(md.series == 0)          // XAUUSD
        {
         gotXau = (md.day == ts0 / 86400
                   && md.mid == (2070.15 + (2070.15 + 25 * ptXAU)) / 2.0);
        }
      if(md.series == 4)          // EURGBP pre-20
        {
         gotEg = (md.day == ts0 / 86400 && md.mid == egMid1959);
        }
     }
   Check("XAU daily mid = 19:30 bar (last of day)", gotXau);
   Check("EG daily mid = 19:59 bar (pre-20 rule)", gotEg);

   //--- Wednesday triple swap on the Jan3 00:00 row -----------------------
   // finalize the Jan3 hour so its row can drain
   Check("advance to Jan3 01:00", fa.AdvanceTo(ts1d + 3600));
   Check("PopH1 Jan3 00", fa.PopH1Row(h1) && h1.ts == ts1d);
   Check("pop Jan3 00:00 row", fa.PopM1Row(mr) && mr.ts == ts1d);
   SE_SwapAnnualPct(SE_SymId("EURUSD"), ts1d, lp, sp);
   Check("swap EURUSD Wed x3",
         mr.swl[14] == lp / 100.0 / 365.0 * 3.0
         && mr.sws[14] == sp / 100.0 / 365.0 * 3.0);
   SE_SwapAnnualPct(SE_SymId("BTCUSD"), ts1d, lp, sp);
   Check("swap BTC Wed x1 (crypto)", mr.swl[3] == lp / 100.0 / 365.0 * 1.0);

   //--- cold-start refusal on a fresh, unseeded assembler ------------------
   CFeedAssembler fb;
   Check("fb init", fb.Init(false));
   Check("fb push", fb.PushBar(iEU, ts0, 1.1, 1.1, 1.1, 1.1, 10));
   Check("fb advance", fb.AdvanceTo(ts0 + 60));
   Check("fb row is unready (not all seeded)",
         fb.BRows() == 1 && fb.UnreadyRows() == 1 && !fb.AllBookSeeded());
   // stamp regression across minutes must be rejected
   Check("fb regression rejected", !fb.PushBar(iEU, ts0 - 60, 1, 1, 1, 1, 1));

   PrintFormat("CheckFeedAssembler: %s — %d passed, %d failed",
               g_fail == 0 ? "PASS" : "FAIL", g_pass, g_fail);
  }
//+------------------------------------------------------------------+
