//+------------------------------------------------------------------+
//| TestCoreSim.mq5 — offline replay harness for Core/CoreSim.mqh    |
//| (the a_h idealized standalone Core account shadow).              |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions — pure FileOpen /       |
//| FileReadString / compute, the Track-A chained pattern            |
//| (TestV34Native.mq5). Spec: research/bpure/coresim/CORESIM_SPEC.md|
//| section 7; scalar reference bit-equal on all 32 segments         |
//| (coresim_parity.json, 2026-07-14).                               |
//|                                                                  |
//| Files (FILE_COMMON — the terminal Common\Files directory),       |
//| ALL headerless CSV, doubles %.17g:                               |
//|   in : FMA3_coresim_segments.csv                                 |
//|          j,t0_epoch,t1_epoch,n_rows      (one row per segment,   |
//|          j ascending 0..31; n_rows = leg-bar rows in the seg     |
//|          file, sanity-checked)                                   |
//|        FMA3_coresim_seg{J}.csv                                   |
//|          leg_id,epoch_sec,bid_o,bid_h,bid_l,bid_c,ask_o,ask_h,   |
//|          ask_l,ask_c,eurq,swap_flag,swap_long,swap_short,tgt     |
//|          LEG-MAJOR: grouped by leg_id in BOOK APPEND ORDER,      |
//|          time-ascending within a leg (in-window native bars      |
//|          only). leg_id = 0..8, see LEG TABLE below.              |
//|   out: FMA3_coresim_actual_seg{J}.csv                            |
//|          epoch_sec,eqc,eqw,margin        (combined union grid)   |
//|                                                                  |
//| Seed chain: segment 0 seeds at InpInitSeed (anchor INIT 10000);  |
//| every later segment seeds at the previous segment's final        |
//| combined eqc (spec 6.2). Band-trigger dates are FROZEN into the  |
//| segment files — this harness never detects triggers.            |
//|                                                                  |
//| LEG TABLE (book append order; slot_legs = legcap divisor):       |
//|   0 BOOK_XAU  /XAUUSD  slot 1   1 S5_JPY /USDJPY slot 1          |
//|   2 S1_ETH    /ETHUSD  slot 1   3 ZC_EG  /EURGBP slot 1          |
//|   4 BOOK_USTEC/USTEC   slot 1   5 S6     /USDJPY slot 3          |
//|   6 S6        /AUDUSD  slot 3   7 S6     /NZDUSD slot 3          |
//|   8 BTC_REP   /BTCUSD  slot 1                                    |
//|                                                                  |
//| STAGED: the input exporter (export_coresim_inputs.py) has not    |
//| been run yet — without the inputs this script prints the staged  |
//| notice and exits cleanly (compile/deploy is still meaningful).   |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

#include <Sat/SatMath.mqh>      // SatParseDouble (%.17g round-trip)
#include <Core/CoreSim.mqh>

input double InpInitSeed = 10000.0;   // anchor INIT (segment-0 seed)

#define CORESIM_MANIFEST  "FMA3_coresim_segments.csv"
#define CORESIM_NSEG_MAX  64
#define CORESIM_NLEGS     9

//--- per-leg static config (spec section 3, verified vs NSF5 settings)
//    order: slot_legs, contract, comm_side, leverage, lot_step, min_lot
int    LegSlot[CORESIM_NLEGS]     = {1, 1, 1, 1, 1, 3, 3, 3, 1};
double LegContract[CORESIM_NLEGS] = {100.0, 100000.0, 1.0, 100000.0, 1.0,
                                     100000.0, 100000.0, 100000.0, 1.0};
double LegComm[CORESIM_NLEGS]     = {3.25, 3.25, 0.0, 3.25, 0.0,
                                     3.25, 3.25, 3.25, 0.0};
double LegLev[CORESIM_NLEGS]      = {20.0, 30.0, 2.0, 30.0, 20.0,
                                     30.0, 20.0, 20.0, 2.0};
double LegStep[CORESIM_NLEGS]     = {0.01, 0.01, 0.01, 0.01, 0.1,
                                     0.01, 0.01, 0.01, 0.01};
double LegMin[CORESIM_NLEGS]      = {0.01, 0.01, 0.01, 0.01, 0.1,
                                     0.01, 0.01, 0.01, 0.01};
string LegName[CORESIM_NLEGS]     = {"BOOK_XAU/XAUUSD", "S5_JPY/USDJPY",
                                     "S1_ETH/ETHUSD", "ZC_EG/EURGBP",
                                     "BOOK_USTEC/USTEC", "S6/USDJPY",
                                     "S6/AUDUSD", "S6/NZDUSD",
                                     "BTC_REP/BTCUSD"};

//+------------------------------------------------------------------+
bool RunSegment(CCoreBookSim &book, const int j, const double seed,
                const long nrows_expect, double &final_eqc)
  {
   string fin = StringFormat("FMA3_coresim_seg%d.csv", j);
   int h = FileOpen(fin, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
     { PrintFormat("TestCoreSim: FAIL cannot open %s (err %d)", fin, GetLastError()); return false; }

   if(!book.BeginSegment(seed))
     { PrintFormat("TestCoreSim: FAIL BeginSegment: %s", book.LastError()); FileClose(h); return false; }

   long nrows = 0;
   int  last_leg = -1;
   while(!FileIsEnding(h))
     {
      string tok = FileReadString(h);
      if(tok == "" && FileIsEnding(h)) break;             // trailing newline
      int  leg = (int)StringToInteger(tok);
      long ts  = (long)StringToInteger(FileReadString(h));
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
      if(leg < last_leg)
        { PrintFormat("TestCoreSim: FAIL seg %d not leg-major at row %I64d", j, nrows); FileClose(h); return false; }
      last_leg = leg;
      if(!book.StepLegBar(leg, ts, bo, bh, bl, bc, ao, ah, al, ac,
                          eurq, sflag, slong, sshort, tgt))
        { PrintFormat("TestCoreSim: FAIL seg %d row %I64d: %s", j, nrows, book.LastError()); FileClose(h); return false; }
      nrows++;
     }
   FileClose(h);
   if(nrows_expect > 0 && nrows != nrows_expect)
     { PrintFormat("TestCoreSim: FAIL seg %d rows %I64d != manifest %I64d", j, nrows, nrows_expect); return false; }

   if(!book.FinishSegment())
     { PrintFormat("TestCoreSim: FAIL FinishSegment seg %d: %s", j, book.LastError()); return false; }

   string fout = StringFormat("FMA3_coresim_actual_seg%d.csv", j);
   int ho = FileOpen(fout, FILE_WRITE|FILE_ANSI|FILE_COMMON);
   if(ho == INVALID_HANDLE)
     { PrintFormat("TestCoreSim: FAIL cannot write %s (err %d)", fout, GetLastError()); return false; }
   int un = book.UnionBars();
   for(int i=0;i<un;i++)
      FileWriteString(ho, StringFormat("%I64d,%.17g,%.17g,%.17g\n",
                      book.UnionTs(i), book.EqC(i), book.EqW(i), book.Mg(i)));
   FileClose(ho);

   final_eqc = book.FinalEqC();
   PrintFormat("TestCoreSim: seg %2d rows=%I64d union=%d flat=%.17g final_eqc=%.17g -> %s",
               j, nrows, un, book.Flat(), final_eqc, fout);
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   if(!FileIsExist(CORESIM_MANIFEST, FILE_COMMON))
     {
      Print("TestCoreSim: STAGED — ", CORESIM_MANIFEST, " not found in Common\\Files. ",
            "Run export_coresim_inputs.py first (CORESIM_SPEC.md section 7). ",
            "Nothing executed; exiting cleanly.");
      return;
     }
   int hm = FileOpen(CORESIM_MANIFEST, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(hm == INVALID_HANDLE)
     { PrintFormat("TestCoreSim: FAIL cannot open manifest (err %d)", GetLastError()); return; }
   int  seg_j[CORESIM_NSEG_MAX];
   long seg_t0[CORESIM_NSEG_MAX], seg_t1[CORESIM_NSEG_MAX], seg_n[CORESIM_NSEG_MAX];
   int  nseg = 0;
   while(!FileIsEnding(hm) && nseg < CORESIM_NSEG_MAX)
     {
      string tok = FileReadString(hm);
      if(tok == "" && FileIsEnding(hm)) break;
      seg_j[nseg]  = (int)StringToInteger(tok);
      seg_t0[nseg] = (long)StringToInteger(FileReadString(hm));
      seg_t1[nseg] = (long)StringToInteger(FileReadString(hm));
      seg_n[nseg]  = (long)StringToInteger(FileReadString(hm));
      nseg++;
     }
   FileClose(hm);
   PrintFormat("TestCoreSim: manifest %d segments", nseg);

   CCoreBookSim book;
   if(!book.SetSlots(7)) { Print("TestCoreSim: FAIL SetSlots"); return; }
   for(int i=0;i<CORESIM_NLEGS;i++)
      if(book.AddLeg(LegSlot[i], LegContract[i], LegComm[i],
                     LegLev[i], LegStep[i], LegMin[i]) != i)
        { PrintFormat("TestCoreSim: FAIL AddLeg %s: %s", LegName[i], book.LastError()); return; }

   double seed = InpInitSeed;                 // anchor INIT
   for(int s=0;s<nseg;s++)
     {
      if(seg_j[s] != s)
        { PrintFormat("TestCoreSim: FAIL manifest order (row %d has j=%d)", s, seg_j[s]); return; }
      double final_eqc = 0.0;
      if(!RunSegment(book, s, seed, seg_n[s], final_eqc)) return;
      seed = final_eqc;                       // spec 6.2 seed chain
     }
   PrintFormat("TestCoreSim: DONE %d segments, final combined eqc = %.17g", nseg, seed);
  }
//+------------------------------------------------------------------+
