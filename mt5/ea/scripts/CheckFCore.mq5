//+------------------------------------------------------------------+
//| CheckFCore.mq5 — offline replay harness for the f_core extension |
//| of Core/CoreSim.mqh (the Core book's held frac-of-own-equity per  |
//| NET symbol, frozen target v7_book_frac_1h.parquet [legacy name]). |
//|                                                                   |
//| SCRIPT (OnStart), ZERO trading functions. Identical input data    |
//| path to TestCoreSim.mq5 (same manifest + per-segment leg-major    |
//| CSVs from export_coresim_inputs.py); additionally maps each leg   |
//| to its NET symbol column and calls ComputeFCore() after every     |
//| FinishSegment(), accumulating the hourly f_core rows across the   |
//| chained segments (the seam ffill carry lives in CCoreBookSim).    |
//|                                                                   |
//| Identity source (MEASURED, python full grid, bit-exact 0.0 on all |
//| 8 columns): research/bpure/coresim/fcore_identity.json —          |
//|   f_core[net] = net_lots * contract * mid_c * eurq / book_eqc,    |
//|   hourly row at hour start h = last 1m union bar in [h, h+1).     |
//|                                                                   |
//| Files (FILE_COMMON), headerless CSV, doubles %.17g:               |
//|   in : FMA3_coresim_segments.csv + FMA3_coresim_seg{J}.csv        |
//|        (the TestCoreSim inputs, unchanged)                        |
//|   out: FMA3_fcore_actual.csv                                      |
//|        hour_epoch,f_AUDUSD,f_BTCUSD,f_ETHUSD,f_EURGBP,f_NZDUSD,   |
//|        f_USDJPY,f_USTEC,f_XAUUSD   (NET columns ALPHABETICAL —    |
//|        the frozen parquet column order)                           |
//|                                                                   |
//| Judge: validate_mql5_fcore.py compares the actual CSV bitwise     |
//| against research/outputs/v7_book_frac_1h.parquet.                 |
//|                                                                   |
//| NET TABLE (leg -> net col):                                       |
//|   leg 0 XAUUSD->7   leg 1 USDJPY->5   leg 2 ETHUSD->2             |
//|   leg 3 EURGBP->3   leg 4 USTEC ->6   leg 5 USDJPY->5             |
//|   leg 6 AUDUSD->0   leg 7 NZDUSD->4   leg 8 BTCUSD->1             |
//|                                                                   |
//| STAGED: without the exporter inputs this script prints the staged |
//| notice and exits cleanly (compile/deploy is still meaningful).    |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

#include <Sat/SatMath.mqh>      // SatParseDouble (%.17g round-trip)
#include <Core/CoreSim.mqh>

input double InpInitSeed = 10000.0;   // anchor INIT (segment-0 seed)

#define FCORE_MANIFEST  "FMA3_coresim_segments.csv"
#define FCORE_OUT       "FMA3_fcore_actual.csv"
#define FCORE_NSEG_MAX  64
#define FCORE_NLEGS     9
#define FCORE_NNET      8

//--- per-leg static config (the TestCoreSim LEG TABLE, verified vs NSF5)
int    LegSlot[FCORE_NLEGS]     = {1, 1, 1, 1, 1, 3, 3, 3, 1};
double LegContract[FCORE_NLEGS] = {100.0, 100000.0, 1.0, 100000.0, 1.0,
                                   100000.0, 100000.0, 100000.0, 1.0};
double LegComm[FCORE_NLEGS]     = {3.25, 3.25, 0.0, 3.25, 0.0,
                                   3.25, 3.25, 3.25, 0.0};
double LegLev[FCORE_NLEGS]      = {20.0, 30.0, 2.0, 30.0, 20.0,
                                   30.0, 20.0, 20.0, 2.0};
double LegStep[FCORE_NLEGS]     = {0.01, 0.01, 0.01, 0.01, 0.1,
                                   0.01, 0.01, 0.01, 0.01};
double LegMin[FCORE_NLEGS]      = {0.01, 0.01, 0.01, 0.01, 0.1,
                                   0.01, 0.01, 0.01, 0.01};
//--- leg -> net column (parquet columns ALPHABETICAL: 0 AUDUSD, 1 BTCUSD,
//    2 ETHUSD, 3 EURGBP, 4 NZDUSD, 5 USDJPY, 6 USTEC, 7 XAUUSD)
int    LegNet[FCORE_NLEGS]      = {7, 5, 2, 3, 6, 5, 0, 4, 1};
string NetName[FCORE_NNET]      = {"AUDUSD", "BTCUSD", "ETHUSD", "EURGBP",
                                   "NZDUSD", "USDJPY", "USTEC", "XAUUSD"};

//+------------------------------------------------------------------+
bool RunSegment(CCoreBookSim &book, const int j, const double seed,
                const long nrows_expect, double &final_eqc)
  {
   string fin = StringFormat("FMA3_coresim_seg%d.csv", j);
   int h = FileOpen(fin, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
     { PrintFormat("CheckFCore: FAIL cannot open %s (err %d)", fin, GetLastError()); return false; }

   if(!book.BeginSegment(seed))
     { PrintFormat("CheckFCore: FAIL BeginSegment: %s", book.LastError()); FileClose(h); return false; }

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
        { PrintFormat("CheckFCore: FAIL seg %d not leg-major at row %I64d", j, nrows); FileClose(h); return false; }
      last_leg = leg;
      if(!book.StepLegBar(leg, ts, bo, bh, bl, bc, ao, ah, al, ac,
                          eurq, sflag, slong, sshort, tgt))
        { PrintFormat("CheckFCore: FAIL seg %d row %I64d: %s", j, nrows, book.LastError()); FileClose(h); return false; }
      nrows++;
     }
   FileClose(h);
   if(nrows_expect > 0 && nrows != nrows_expect)
     { PrintFormat("CheckFCore: FAIL seg %d rows %I64d != manifest %I64d", j, nrows, nrows_expect); return false; }

   if(!book.FinishSegment())
     { PrintFormat("CheckFCore: FAIL FinishSegment seg %d: %s", j, book.LastError()); return false; }
   if(!book.ComputeFCore())
     { PrintFormat("CheckFCore: FAIL ComputeFCore seg %d: %s", j, book.LastError()); return false; }

   final_eqc = book.FinalEqC();
   PrintFormat("CheckFCore: seg %2d rows=%I64d union=%d fcore_rows=%d final_eqc=%.17g",
               j, nrows, book.UnionBars(), book.FCoreRows(), final_eqc);
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   if(!FileIsExist(FCORE_MANIFEST, FILE_COMMON))
     {
      Print("CheckFCore: STAGED — ", FCORE_MANIFEST, " not found in Common\\Files. ",
            "Run export_coresim_inputs.py first (CORESIM_SPEC.md section 7). ",
            "Nothing executed; exiting cleanly.");
      return;
     }
   int hm = FileOpen(FCORE_MANIFEST, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(hm == INVALID_HANDLE)
     { PrintFormat("CheckFCore: FAIL cannot open manifest (err %d)", GetLastError()); return; }
   int  seg_j[FCORE_NSEG_MAX];
   long seg_t0[FCORE_NSEG_MAX], seg_t1[FCORE_NSEG_MAX], seg_n[FCORE_NSEG_MAX];
   int  nseg = 0;
   while(!FileIsEnding(hm) && nseg < FCORE_NSEG_MAX)
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
   PrintFormat("CheckFCore: manifest %d segments", nseg);

   CCoreBookSim book;
   if(!book.SetSlots(7)) { Print("CheckFCore: FAIL SetSlots"); return; }
   for(int i=0;i<FCORE_NLEGS;i++)
      if(book.AddLeg(LegSlot[i], LegContract[i], LegComm[i],
                     LegLev[i], LegStep[i], LegMin[i]) != i)
        { PrintFormat("CheckFCore: FAIL AddLeg %d: %s", i, book.LastError()); return; }
   if(!book.SetNets(FCORE_NNET)) { Print("CheckFCore: FAIL SetNets"); return; }
   for(int i=0;i<FCORE_NLEGS;i++)
      if(!book.AssignLegNet(i, LegNet[i]))
        { PrintFormat("CheckFCore: FAIL AssignLegNet %d: %s", i, book.LastError()); return; }

   double seed = InpInitSeed;                 // anchor INIT
   for(int s=0;s<nseg;s++)
     {
      if(seg_j[s] != s)
        { PrintFormat("CheckFCore: FAIL manifest order (row %d has j=%d)", s, seg_j[s]); return; }
      double final_eqc = 0.0;
      if(!RunSegment(book, s, seed, seg_n[s], final_eqc)) return;
      seed = final_eqc;                       // spec 6.2 seed chain
     }

   int ho = FileOpen(FCORE_OUT, FILE_WRITE|FILE_ANSI|FILE_COMMON);
   if(ho == INVALID_HANDLE)
     { PrintFormat("CheckFCore: FAIL cannot write %s (err %d)", FCORE_OUT, GetLastError()); return; }
   int rows = book.FCoreRows();
   for(int k=0;k<rows;k++)
     {
      string line = StringFormat("%I64d", book.FCoreTs(k));
      for(int s=0;s<FCORE_NNET;s++)
         line += StringFormat(",%.17g", book.FCoreAt(k, s));
      FileWriteString(ho, line + "\n");
     }
   FileClose(ho);
   PrintFormat("CheckFCore: DONE %d segments, %d hourly f_core rows -> %s",
               nseg, rows, FCORE_OUT);
  }
//+------------------------------------------------------------------+
