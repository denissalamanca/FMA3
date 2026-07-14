//+------------------------------------------------------------------+
//| TestCoreSignal.mq5 — GATE G-S5: offline replay of the frozen     |
//| 2020-2025 bars through the compiled Core/CoreSignal.mqh, self-   |
//| diffed against the frozen tgt column of the exported segment     |
//| bundles (the golden the python chain is bit-zero against).       |
//|                                                                  |
//| SCRIPT (OnStart), ZERO trading functions — the TestCoreSim /     |
//| CheckFCore chained input pattern.  Spec:                         |
//| S2_CORE_LIVE_DESIGN.md section 5 (G-S5) + the owner-ratified     |
//| pass criterion (S2_PREP_STATUS item 3): per-leg max|diff|        |
//| <= 1e-12 AND 0 discrete sign flips (bit-zero NOT required; the   |
//| roll_var fma emulation is expected bit-equal — mirror-measured). |
//|                                                                  |
//| Files (FILE_COMMON), headerless CSV, doubles %.17g:              |
//|   in : FMA3_coresim_segments.csv   j,t0,t1,n_rows                |
//|        FMA3_coresim_seg{J}.csv     leg_id,epoch,bid_o,bid_h,     |
//|          bid_l,bid_c,ask_o,ask_h,ask_l,ask_c,eurq,swap_flag,     |
//|          swap_long,swap_short,tgt  (LEG-MAJOR, time-ascending    |
//|          within a leg; leg_id 0..8 in BOOK APPEND ORDER)         |
//|   out: FMA3_coresignal_gs5.csv     per-leg stats + verdict       |
//|                                                                  |
//| DRIVING CONTRACT (mirrored statement-for-statement in python by  |
//| mql5_coresignal_mirror.py gate M-2, measured over segs 0-1):     |
//|   * ONE CCoreSignal, Configure() once, COLD at segment 0 (the    |
//|     anchor's baked-in warmup — never pre-warm on 2019);          |
//|   * segments replayed 0..N-1 in manifest order (state carries    |
//|     across segment seams — the signal object is segment-blind);  |
//|   * legs 0,2,3,4,6,7,8: StepBar(inst, ts, bid_c, ask_c) then     |
//|     compare Tgt(leg);                                            |
//|   * leg 1 (USDJPY): StepBar once — compare Tgt(1) AND buffer     |
//|     (ts, Tgt(5)) for this segment;                               |
//|   * leg 5 rows: served from the leg-1 buffer (the shared USDJPY  |
//|     feed is NEVER re-stepped); stamps must align exactly.        |
//|                                                                  |
//| STAGED: without the exporter inputs this script prints the       |
//| staged notice and exits cleanly (compile/deploy still            |
//| meaningful).  Terminal run = owner, ledgered as FMA3-RECON-N.    |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

#include <Sat/SatMath.mqh>      // SatParseDouble (%.17g round-trip)
#include <Core/CoreSignal.mqh>

input int InpMaxSegments = 64;  // replay at most this many manifest rows

#define CSG5_MANIFEST  "FMA3_coresim_segments.csv"
#define CSG5_OUT       "FMA3_coresignal_gs5.csv"
#define CSG5_NSEG_MAX  64
#define CSG5_GROW      65536

//--- per-leg accumulated stats
long   g_n[CS_NLEGS];
long   g_nbit[CS_NLEGS];        // rows NOT bit-equal
double g_maxd[CS_NLEGS];
long   g_ngt[CS_NLEGS];         // rows with |diff| > 1e-12
long   g_flips[CS_NLEGS];       // sign(mine) != sign(golden)

//--- leg-5 per-segment buffer (filled on the leg-1 pass)
long   g_b5ts[];
double g_b5v[];
int    g_b5n = 0;
int    g_b5cur = 0;

double CsgSign(const double x)
  {
   if(x > 0.0) return 1.0;
   if(x < 0.0) return -1.0;
   return 0.0;                   // frozen targets are finite
  }

void Accumulate(const int leg, const double mine, const double golden)
  {
   g_n[leg]++;
   if(mine != golden)
      g_nbit[leg]++;
   double d = MathAbs(mine - golden);
   if(d > g_maxd[leg])
      g_maxd[leg] = d;
   if(d > 1e-12)
      g_ngt[leg]++;
   if(CsgSign(mine) != CsgSign(golden))
      g_flips[leg]++;
  }

//+------------------------------------------------------------------+
bool RunSegment(CCoreSignal &sig, const int j, const long nrows_expect)
  {
   string fin = StringFormat("FMA3_coresim_seg%d.csv", j);
   int h = FileOpen(fin, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
     { PrintFormat("TestCoreSignal: FAIL cannot open %s (err %d)", fin, GetLastError()); return false; }

   g_b5n = 0;
   g_b5cur = 0;
   long nrows = 0;
   int  last_leg = -1;
   while(!FileIsEnding(h))
     {
      string tok = FileReadString(h);
      if(tok == "" && FileIsEnding(h)) break;             // trailing newline
      int  leg = (int)StringToInteger(tok);
      long ts  = (long)StringToInteger(FileReadString(h));
      // bid_o,bid_h,bid_l read+discarded; bid_c kept
      FileReadString(h); FileReadString(h); FileReadString(h);
      double bc = SatParseDouble(FileReadString(h));
      // ask_o,ask_h,ask_l discarded; ask_c kept
      FileReadString(h); FileReadString(h); FileReadString(h);
      double ac = SatParseDouble(FileReadString(h));
      // eurq,swap_flag,swap_long,swap_short discarded (not signal inputs)
      FileReadString(h); FileReadString(h); FileReadString(h); FileReadString(h);
      double golden = SatParseDouble(FileReadString(h));
      if(leg < last_leg)
        { PrintFormat("TestCoreSignal: FAIL seg %d not leg-major at row %I64d", j, nrows); FileClose(h); return false; }
      last_leg = leg;
      if(leg < 0 || leg >= CS_NLEGS)
        { PrintFormat("TestCoreSignal: FAIL seg %d bad leg %d", j, leg); FileClose(h); return false; }

      double mine;
      if(leg == 5)
        {
         // served from the buffered leg-1 pass (shared USDJPY feed)
         if(g_b5cur >= g_b5n || g_b5ts[g_b5cur] != ts)
           {
            PrintFormat("TestCoreSignal: FAIL seg %d leg5 stamp misalign row %I64d "
                        "(cur %d of %d)", j, nrows, g_b5cur, g_b5n);
            FileClose(h);
            return false;
           }
         mine = g_b5v[g_b5cur];
         g_b5cur++;
        }
      else
        {
         int inst = CsLegInst(leg);
         if(!sig.StepBar(inst, ts, bc, ac))
           {
            PrintFormat("TestCoreSignal: FAIL seg %d row %I64d: %s",
                        j, nrows, sig.LastError());
            FileClose(h);
            return false;
           }
         mine = sig.Tgt(leg);
         if(leg == 1)
           {
            if(g_b5n >= ArraySize(g_b5ts))
              {
               int want = ArraySize(g_b5ts) + CSG5_GROW;
               if(ArrayResize(g_b5ts, want) != want ||
                  ArrayResize(g_b5v, want) != want)
                 { Print("TestCoreSignal: FAIL leg5 buffer resize"); FileClose(h); return false; }
              }
            g_b5ts[g_b5n] = ts;
            g_b5v[g_b5n]  = sig.Tgt(5);
            g_b5n++;
           }
        }
      Accumulate(leg, mine, golden);
      nrows++;
     }
   FileClose(h);
   if(nrows_expect > 0 && nrows != nrows_expect)
     { PrintFormat("TestCoreSignal: FAIL seg %d rows %I64d != manifest %I64d", j, nrows, nrows_expect); return false; }
   if(g_b5cur != g_b5n)
     { PrintFormat("TestCoreSignal: FAIL seg %d leg5 rows %d != leg1 rows %d", j, g_b5cur, g_b5n); return false; }
   PrintFormat("TestCoreSignal: seg %2d rows=%I64d replayed", j, nrows);
   return true;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   if(!FileIsExist(CSG5_MANIFEST, FILE_COMMON))
     {
      Print("TestCoreSignal: STAGED — ", CSG5_MANIFEST, " not found in Common\\Files. ",
            "Run export_coresim_inputs.py first (CORESIM_SPEC.md section 7). ",
            "Nothing executed; exiting cleanly.");
      return;
     }
   int hm = FileOpen(CSG5_MANIFEST, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(hm == INVALID_HANDLE)
     { PrintFormat("TestCoreSignal: FAIL cannot open manifest (err %d)", GetLastError()); return; }
   int  seg_j[CSG5_NSEG_MAX];
   long seg_t0[CSG5_NSEG_MAX], seg_t1[CSG5_NSEG_MAX], seg_n[CSG5_NSEG_MAX];
   int  nseg = 0;
   while(!FileIsEnding(hm) && nseg < CSG5_NSEG_MAX)
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
   if(nseg > InpMaxSegments)
      nseg = InpMaxSegments;
   PrintFormat("TestCoreSignal: manifest %d segments (replaying %d)", nseg, nseg);

   for(int l = 0; l < CS_NLEGS; l++)
     {
      g_n[l] = 0; g_nbit[l] = 0; g_maxd[l] = 0.0; g_ngt[l] = 0; g_flips[l] = 0;
     }

   CCoreSignal sig;
   sig.Configure();                          // COLD start (anchor warmup)

   for(int s = 0; s < nseg; s++)
     {
      if(seg_j[s] != s)
        { PrintFormat("TestCoreSignal: FAIL manifest order (row %d has j=%d)", s, seg_j[s]); return; }
      if(!RunSegment(sig, s, seg_n[s]))
         return;
     }

   //--- per-leg report + verdict (owner criterion) --------------------
   bool pass = true;
   long tot_rows = 0, tot_flips = 0;
   int ho = FileOpen(CSG5_OUT, FILE_WRITE|FILE_ANSI|FILE_COMMON);
   if(ho == INVALID_HANDLE)
     { PrintFormat("TestCoreSignal: FAIL cannot write %s (err %d)", CSG5_OUT, GetLastError()); return; }
   FileWriteString(ho, "leg,n,n_not_bit_equal,max_abs_diff,n_gt_1e12,flips\n");
   for(int l2 = 0; l2 < CS_NLEGS; l2++)
     {
      bool leg_ok = (g_maxd[l2] <= 1e-12 && g_flips[l2] == 0);
      pass = pass && leg_ok;
      tot_rows += g_n[l2];
      tot_flips += g_flips[l2];
      PrintFormat("TestCoreSignal: leg %d n=%I64d bit_diff=%I64d max|d|=%.3e "
                  ">1e-12: %I64d flips=%I64d %s",
                  l2, g_n[l2], g_nbit[l2], g_maxd[l2], g_ngt[l2], g_flips[l2],
                  leg_ok ? "OK" : "FAIL");
      FileWriteString(ho, StringFormat("%d,%I64d,%I64d,%.17g,%I64d,%I64d\n",
                      l2, g_n[l2], g_nbit[l2], g_maxd[l2], g_ngt[l2], g_flips[l2]));
     }
   FileWriteString(ho, StringFormat("verdict,%s\n", pass ? "PASS" : "FAIL"));
   FileClose(ho);
   PrintFormat("TestCoreSignal: G-S5 %s — %I64d rows, %I64d flips, "
               "criterion max|d|<=1e-12 + 0 flips -> %s",
               pass ? "PASS" : "FAIL", tot_rows, tot_flips, CSG5_OUT);
  }
//+------------------------------------------------------------------+
