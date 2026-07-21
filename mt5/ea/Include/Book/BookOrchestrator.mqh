//+------------------------------------------------------------------+
//| Book/BookOrchestrator.mqh — CBookOrchestrator: the S1 whole-book |
//| compute glue (UNIT 1 of the R1 gate).                             |
//|                                                                   |
//| Wires the individually-proven components into ONE per-bar chain   |
//| per model/v3/FABLEBOOKNATIVE_WIRING_LENS1.md §2–§5 and the        |
//| FABLE REVISION v2 decisions (FABLEBOOKNATIVE_DESIGN.md):          |
//|                                                                   |
//|   H1 signals : 8 Sat sleeve steppers + CSatEnsembleStepper        |
//|                -> f_sat[31]   (the RECON-8b chain; driving loop = |
//|                research/bpure/mql5/harness_sim.py semantics:      |
//|                ffill[37], daily queues for trend_v2/crisis        |
//|                effective times, deferred SeasonalCrypto emit,     |
//|                xau_ret clip ±0.30)                                |
//|                f_core[8] = CCoreBookSim.ComputeFCore()            |
//|                (S0-proven bit-equal, Core/CoreSim.mqh)            |
//|   M1 equity  : a = CoreSim combined eqc — SEGMENT-BATCH per the   |
//|                frozen band-trigger segments, FROZEN leg-target    |
//|                feeds (v2 item 2: no streaming wrapper — the       |
//|                FinishSegment first-value backfill is a leading-   |
//|                edge lookahead a forward streamer cannot compute); |
//|                b = CSatEquityNative.Step on the HELD prior-hour   |
//|                f_sat targets (NOT the frozen tgt column) — the    |
//|                bh_stepper.iter_chunks lag law:                    |
//|                  tgt(minute m) = f_sat row at EXACTLY             |
//|                  floor(m,1h)-1h, absent row -> 0.0 (reindex       |
//|                  method=None + nan_to_num, NOT asof-ffill)        |
//|   H1 blend   : a_h = a/a_first, b_h = b/b_first (FIRST 1m value,  |
//|                not the 10000 seed; hours before the first value   |
//|                -> 1.0 = the model's fillna), asof-sampled at the  |
//|                hour boundary (last 1m stamp <= h);                |
//|                CBookBlend.Step -> book_frac[33]                   |
//|   emission   : scripts/export_book_frac_v3.py::build_rows EXACT   |
//|                semantics — per grid hour (= sat grid ∪ f_core     |
//|                grid, model reproduce.py static_blend union):      |
//|                one row per symbol with |net_frac| > 1e-12,        |
//|                BROKER names (DAX->DE40, USA500->US500), rows      |
//|                sorted (epoch, broker name ordinal); an all-flat   |
//|                present hour emits ONE __GRID__ sentinel           |
//|                (flatten-by-omission); absent hours emit nothing   |
//|                (EA keep-last-good).                               |
//|                Hours in f_core's grid but not the sat grid are    |
//|                emitted with f_sat = 0 (static_blend fillna(0.0)); |
//|                sat hours without an f_core row use f_core = 0.    |
//|                                                                   |
//| SCOPE PIN (S1): this class proves ORCHESTRATION + COMPUTE on      |
//| FROZEN inputs. The Core leg targets are the FROZEN tgt column of  |
//| the CoreSim segment bundles (the live Core leg-target source =    |
//| CoreEngine's proven live signal path, wired in S2/S3 — the CTrade |
//| include collision is deferred there). It does NOT prove the live  |
//| feed (S0 proved that) nor execution (S2/S3).                      |
//| ZERO trading calls, ZERO CTrade, ZERO file I/O — pure compute.    |
//|                                                                   |
//| DRIVE CONTRACT (the R1 harness obeys; violations return false     |
//| with LastError set, never silently degrade):                      |
//|  1. Core feed is SEGMENT-BATCH and must run AHEAD of the H1       |
//|     clock: BeginCoreSegment / StepCoreLegBar× / EndCoreSegment    |
//|     per frozen segment (leg-major like the seg CSVs, or           |
//|     time-major — each leg only needs its own stamps ascending),   |
//|     then SetCoreFeedDone() after the last segment. A blend hour   |
//|     may only consume the LAST accumulated f_core row once the     |
//|     NEXT segment is finished or the feed is done (the segment-    |
//|     seam straddle row is healed by the next ComputeFCore).        |
//|  2. M1 sat rows (StepM1) strictly ascending; feed the minutes of  |
//|     [h, h+1h) after StepH1(h) so hour h-1h's blend sees b asof    |
//|     h-1h and the minutes see the f_sat row emitted at StepH1(h).  |
//|  3. H1 rows (StepH1) on the hourly union grid, stamps 3600-       |
//|     aligned ascending; FinalizeH1() once after the last row       |
//|     (flushes the deferred SeasonalCrypto row + trailing           |
//|     core-only hours).                                             |
//|                                                                   |
//| Emission lag is the model's own (WIRING §2.2): f_sat for hour h   |
//| is produced when bar h+1 arrives (SeasonalCrypto deferred emit),  |
//| so StepH1(ts) returns the rows of the PREVIOUS grid hour.         |
//+------------------------------------------------------------------+
#ifndef BOOK_BOOKORCHESTRATOR_MQH
#define BOOK_BOOKORCHESTRATOR_MQH

#include <Sat/SatMath.mqh>
#include <Sat/MagXau.mqh>
#include <Sat/Intraday.mqh>
#include <Sat/MeanRev.mqh>
#include <Sat/SeasonalCrypto.mqh>
#include <Sat/CarryBreakout.mqh>
#include <Sat/Crisis.mqh>
#include <Sat/TrendV2.mqh>
#include <Sat/Ensemble.mqh>
#include <Sat/SatEquityNative.mqh>
#include <Core/CoreSim.mqh>
#include <Book/BookBlend.mqh>
#include <Book/BookState.mqh>

//==================================================================//
// frozen wiring constants                                          //
//==================================================================//
#define BOOKORC_NIN      37       // H1 signal input universe (core.ALL)
#define BOOKORC_NKEEP    21       // carry_breakout KEPT columns
#define BOOKORC_NLEGS    9        // CoreSim legs (TestCoreSim LEG TABLE)
#define BOOKORC_NNET     8        // f_core net symbols (alphabetical)
#define BOOKORC_NBOOK    33       // netted blend output columns
#define BOOKORC_NCROSS   8        // eurq EUR crosses (exporter order)
#define BOOKORC_HELD     16       // f_sat held-row ring depth
#define BOOKORC_EPS      1e-12    // build_rows emission threshold
#define BOOKORC_W        0.70     // model v3 Core capital share

// H1 input CSV symbol order == core.ALL (TestV34Native, RECON-8b)
const string BOOKORC_IN_SYMS[BOOKORC_NIN] =
  {
   "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
   "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
   "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY",
   "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
   "DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
   "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"
  };

// carry_breakout golden parquet columns (21 KEPT of 32 stepper outputs)
const string BOOKORC_CB_KEPT[BOOKORC_NKEEP] =
  {
   "AUDJPY", "CADCHF", "CADJPY", "EURCAD", "EURNZD", "EURUSD", "GBPJPY",
   "NZDJPY", "USDCHF", "USDJPY", "DAX", "JP225", "UK100", "US30",
   "USA500", "USTEC", "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XTIUSD"
  };
const string BOOKORC_SEA_SYMS[1] = {"XAUUSD"};
const string BOOKORC_MAG_SYMS[1] = {"XAUUSD"};
const string BOOKORC_ID_SYMS[2]  = {"USA500", "USTEC"};

// CoreSim leg static config (TestCoreSim/CheckFCore LEG TABLE, book
// append order; verified vs NSF5 settings):
//   0 BOOK_XAU/XAUUSD  1 S5_JPY/USDJPY  2 S1_ETH/ETHUSD  3 ZC_EG/EURGBP
//   4 BOOK_USTEC/USTEC 5 S6/USDJPY  6 S6/AUDUSD  7 S6/NZDUSD  8 BTC_REP/BTCUSD
const int    BOOKORC_LEG_SLOT[BOOKORC_NLEGS]     = {1, 1, 1, 1, 1, 3, 3, 3, 1};
const double BOOKORC_LEG_CONTRACT[BOOKORC_NLEGS] = {100.0, 100000.0, 1.0, 100000.0, 1.0,
                                                    100000.0, 100000.0, 100000.0, 1.0};
const double BOOKORC_LEG_COMM[BOOKORC_NLEGS]     = {3.25, 3.25, 0.0, 3.25, 0.0,
                                                    3.25, 3.25, 3.25, 0.0};
const double BOOKORC_LEG_LEV[BOOKORC_NLEGS]      = {20.0, 30.0, 2.0, 30.0, 20.0,
                                                    30.0, 20.0, 20.0, 2.0};
const double BOOKORC_LEG_STEP[BOOKORC_NLEGS]     = {0.01, 0.01, 0.01, 0.01, 0.1,
                                                    0.01, 0.01, 0.01, 0.01};
const double BOOKORC_LEG_MIN[BOOKORC_NLEGS]      = {0.01, 0.01, 0.01, 0.01, 0.1,
                                                    0.01, 0.01, 0.01, 0.01};
// leg -> f_core net column (parquet columns ALPHABETICAL)
const int    BOOKORC_LEG_NET[BOOKORC_NLEGS]      = {7, 5, 2, 3, 6, 5, 0, 4, 1};
const string BOOKORC_NET_SYMS[BOOKORC_NNET]      =
  {
   "AUDUSD", "BTCUSD", "ETHUSD", "EURGBP",
   "NZDUSD", "USDJPY", "USTEC", "XAUUSD"
  };

// eurq cross columns, exporter order (sorted), + per-Sat-symbol quote
// cross index (-1 = EUR quote) — the TestSatEquityChain table (RECON-8d)
const string BOOKORC_CROSSES[BOOKORC_NCROSS] =
  {
   "EURCAD", "EURCHF", "EURGBP", "EURJPY",
   "EURNOK", "EURNZD", "EURSEK", "EURUSD"
  };
const int BOOKORC_CROSS_IX[SATEQ_NSYM] =
  {
   0, 3, 5, 7, 1, 3, -1, 7, 0, 1, 2, 4, 5, 6, 7, 3,
   3, 0, 3, 7, 2, 7, 7, 1, 3, 7, 7, 7, 7, 7, 7
  };

// model -> broker symbol name (exporter SYMMAP; rest identity)
string BookOrcBrokerName(const string model)
  {
   if(model == "DAX")
      return "DE40";
   if(model == "USA500")
      return "US500";
   return model;
  }

//==================================================================//
// CBookOrcHourSampler — asof hour-boundary sampler of a 1m curve.  //
// Reproduces pandas reindex(union).ffill().reindex(hours):         //
// sample at H (multiple of 3600) = value at the LAST 1m stamp <= H.//
// Feed points strictly ascending; boundaries in [ts_i, ts_{i+1})   //
// materialize with v_i, so coverage is contiguous and queries are  //
// O(1). Queries at H >= last stamp return the live last value      //
// (trailing ffill); H < first stamp returns false (model fillna).  //
//==================================================================//
class CBookOrcHourSampler
  {
private:
   double            m_v[];       // materialized boundary samples
   int               m_n;
   long              m_base;      // stamp of m_v[0] (multiple of 3600)
   bool              m_have;      // any point fed
   long              m_firstTs;
   double            m_firstV;
   long              m_lastTs;
   double            m_lastV;

public:
                     CBookOrcHourSampler() { Reset(); }

   void              Reset()
     {
      ArrayResize(m_v, 0);
      m_n = 0;
      m_base = 0;
      m_have = false;
      m_firstTs = 0;
      m_firstV = 0.0;
      m_lastTs = 0;
      m_lastV = 0.0;
     }

   bool              Have()    const { return m_have;    }
   long              FirstTs() const { return m_firstTs; }
   double            FirstV()  const { return m_firstV;  }
   long              LastTs()  const { return m_lastTs;  }
   double            LastV()   const { return m_lastV;   }
   int               Samples() const { return m_n;       }

   // one 1m point, stamps strictly ascending
   bool              Add(const long ts, const double v)
     {
      if(!m_have)
        {
         m_have = true;
         m_firstTs = ts;
         m_firstV = v;
         m_lastTs = ts;
         m_lastV = v;
         return true;
        }
      if(ts <= m_lastTs)
         return false;                       // stamps must ascend
      // materialize boundaries H in [m_lastTs, ts) with m_lastV
      long h0 = m_lastTs - (m_lastTs % 3600);
      if(h0 < m_lastTs)
         h0 += 3600;                         // smallest multiple >= lastTs
      for(long h = h0; h < ts; h += 3600)
        {
         if(m_n == 0)
            m_base = h;
         int cap = ArraySize(m_v);
         if(m_n >= cap)
            ArrayResize(m_v, cap + 4096);
         m_v[m_n] = m_lastV;
         m_n++;
        }
      m_lastTs = ts;
      m_lastV = v;
      return true;
     }

   // asof sample at hour boundary h (h % 3600 == 0). false = before
   // the first 1m stamp (caller applies the model fillna).
   bool              Query(const long h, double &out) const
     {
      if(!m_have || h < m_firstTs)
         return false;
      if(h >= m_lastTs)
        {
         out = m_lastV;
         return true;
        }
      // h in [m_firstTs, m_lastTs): every multiple of 3600 in that
      // range is materialized (contiguous tiling)
      int i = (int)((h - m_base) / 3600);
      if(i < 0 || i >= m_n)
         return false;                       // h not 3600-aligned / hole
      out = m_v[i];
      return true;
     }

   //--- BookState additive hooks (serialize/restore; no compute) ----
   long              BaseTs() const { return m_base; }
   double            SampleAt(const int i) const
     {
      return (i >= 0 && i < m_n) ? m_v[i] : 0.0;
     }

   bool              Restore(const bool have, const long base,
                             const long firstTs, const double firstV,
                             const long lastTs, const double lastV,
                             const double &v[], const int n)
     {
      Reset();
      if(!have)
        {
         if(n != 0)
            return false;
         return true;
        }
      if(n < 0 || ArraySize(v) < n)
         return false;
      if(n > 0 && (base % 3600) != 0)
         return false;
      if(lastTs < firstTs)
         return false;
      if(n > 0)
        {
         if(ArrayResize(m_v, n) != n)
            return false;
         for(int i = 0; i < n; i++)
            m_v[i] = v[i];
        }
      m_n       = n;
      m_base    = base;
      m_have    = true;
      m_firstTs = firstTs;
      m_firstV  = firstV;
      m_lastTs  = lastTs;
      m_lastV   = lastV;
      return true;
     }
  };

//==================================================================//
// CBookOrchestrator                                                //
//==================================================================//
class CBookOrchestrator
  {
private:
   // ---- components ----
   CSatMagXauStepper         m_mag;
   CSatIntradayStepper       m_intr;
   CSatMeanRevStepper        m_mr;
   CSatSeasonalCryptoStepper m_sc;
   CSatCarryBreakoutStepper  m_cb;
   CSatCrisisStepper         m_crisis;
   CSatTrendV2Stepper        m_tv;
   CSatEnsembleStepper       m_shell;
   CSatEquityNative          m_beng;      // b (M1 eq_c)
   CCoreBookSim              m_core;      // a (M1 combined eqc) + f_core
   CBookBlend                m_blend;

   // ---- H1 signal glue (harness_sim.py state, WIRING §4) ----
   double            m_ffill[BOOKORC_NIN];
   bool              m_has_day;
   long              m_cur_day;
   long              m_tvq_eff[];             // trend queue (stride 5)
   double            m_tvq_w[];
   long              m_crq_eff[];             // crisis queue (stride 4)
   double            m_crq_w[];
   double            m_trend_cur[SatTV2_NSYM];
   double            m_crisis_cur[SatCRISIS_NOUT];
   bool              m_have_prev;
   long              m_prev_ts;
   double            m_prev_mr[SatMR_NSYM];
   double            m_prev_cbk[BOOKORC_NKEEP];
   double            m_prev_id[2];
   double            m_prev_cr[SatCRISIS_NOUT];
   double            m_prev_tv[SatTV2_NSYM];
   double            m_prev_mg[1];
   long              m_h1_bars;               // H1 input bars processed
   long              m_h1_last_ts;
   bool              m_finalized;

   // ---- symbol index maps (H1 input columns) ----
   int               m_mr_ix[SatMR_NSYM];
   int               m_cb_ix[SATCB_N_SYM];
   int               m_id_ix[2];
   int               m_tv_ix[SatTV2_NSYM];
   int               m_cr_in_ix[SatCRISIS_NIN];
   int               m_cb_keep_ix[BOOKORC_NKEEP];
   int               m_ix_xau, m_ix_btc, m_ix_eth, m_ix_sol;

   // ---- equity sampling ----
   CBookOrcHourSampler m_aS;                  // a: fed at EndCoreSegment
   CBookOrcHourSampler m_bS;                  // b: fed at StepM1
   long              m_m1_last_ts;
   long              m_m1_bars;
   double            m_b_eqc, m_b_eqw;

   // ---- core segment-batch state ----
   bool              m_seg_open;
   int               m_n_segs;
   double            m_seed;
   bool              m_core_done;
   int               m_fc_cursor;             // next unconsumed f_core row

   // ---- LIVE-CORE mode (FableBookNative.mq5; INERT in batch replay:
   // every field below is dead until EnableLiveCore() is called, so
   // the S1 R1 gate path is numerically and structurally unchanged) ----
   bool              m_live_core;             // EnableLiveCore() latch
   long              m_live_core_through;     // live core clock (exclusive)
   long              m_live_sc_mismatch;      // early-emit SC row mismatches
   bool              m_live_have_emit4;       // early-emitted row pending check
   double            m_live_emit4[4];

   // ---- f_sat held-row ring (the b tgt source) ----
   long              m_held_ts[BOOKORC_HELD];
   double            m_held_row[BOOKORC_HELD][SATEQ_NSYM];
   int               m_held_n;

   // ---- emission buffers (reset each StepH1 / FinalizeH1) ----
   long              m_emit_ts[];
   string            m_emit_sym[];
   double            m_emit_val[];
   int               m_emit_n;
   long              m_last_emit_hour;
   long              m_total_rows;
   long              m_total_hours;
   long              m_total_sentinels;
   double            m_last_ah, m_last_bh;

   string            m_err;
   bool              m_ready;

   //---------------------------------------------------------------//
   // helpers                                                       //
   //---------------------------------------------------------------//
   static int        InSymIndex(const string name)
     {
      for(int i = 0; i < BOOKORC_NIN; i++)
         if(BOOKORC_IN_SYMS[i] == name)
            return i;
      return -1;
     }

   bool              MapSyms(const string &names[], int &ix[], const int n)
     {
      for(int i = 0; i < n; i++)
        {
         ix[i] = InSymIndex(names[i]);
         if(ix[i] < 0)
           {
            m_err = "unknown H1 input symbol '" + names[i] + "'";
            return false;
           }
        }
      return true;
     }

   void              QPush(long &eff[], double &w[], const long e,
                           const double &row[], const int stride)
     {
      int n = ArraySize(eff);
      ArrayResize(eff, n + 1);
      eff[n] = e;
      int m = ArraySize(w);
      ArrayResize(w, m + stride);
      for(int j = 0; j < stride; j++)
         w[m + j] = row[j];
     }

   void              QPop(long &eff[], double &w[], const int stride)
     {
      int n = ArraySize(eff);
      for(int i = 1; i < n; i++)
         eff[i - 1] = eff[i];
      ArrayResize(eff, n - 1);
      int m = ArraySize(w);
      for(int i = stride; i < m; i++)
         w[i - stride] = w[i];
      ArrayResize(w, m - stride);
     }

   void              EmitAppend(const long ts, const string sym, const double v)
     {
      int cap = ArraySize(m_emit_ts);
      if(m_emit_n >= cap)
        {
         ArrayResize(m_emit_ts,  cap + 64);
         ArrayResize(m_emit_sym, cap + 64);
         ArrayResize(m_emit_val, cap + 64);
        }
      m_emit_ts[m_emit_n]  = ts;
      m_emit_sym[m_emit_n] = sym;
      m_emit_val[m_emit_n] = v;
      m_emit_n++;
     }

   // may the f_core row at index k be consumed yet? The LAST accumulated
   // row is the potential segment-seam straddle row: the NEXT segment's
   // ComputeFCore overwrites it in place (the heal). Consuming it before
   // the next segment is finished (or the feed is done) reads a value
   // that may still change — a drive-contract violation, not a fallback.
   bool              FCoreConsumable(const int k)
     {
      // LIVE-CORE: rows are appended by LiveCoreAppend only AFTER their
      // hour completed on the union clock (final by construction; the
      // batch same-hour straddle heal cannot occur), so every row is
      // immediately consumable.  INERT in batch mode.
      if(m_live_core)
         return true;
      if(k < m_core.FCoreRows() - 1)
         return true;
      if(m_core_done && !m_seg_open)
         return true;
      m_err = StringFormat("f_core row %d (hour %I64d) is the straddle-guarded "
                           "last row: core feed must run >=1 segment ahead of "
                           "the H1 clock (or SetCoreFeedDone first)",
                           k, m_core.FCoreTs(k));
      return false;
     }

   // one blend-grid hour: blend f_core/f_sat with the asof-sampled
   // a_h/b_h and append the exporter-semantics rows
   bool              EmitHour(const long h, const double &fc[], const double &fs[])
     {
      if(m_total_hours > 0 && h <= m_last_emit_hour)
        {
         m_err = StringFormat("emission hour %I64d not ascending (last %I64d)",
                              h, m_last_emit_hour);
         return false;
        }
      // a_h/b_h: multiple of own FIRST 1m value; before it -> 1.0 (fillna)
      double av = 0.0, bv = 0.0;
      double a_h = 1.0, b_h = 1.0;
      if(m_aS.Query(h, av))
         a_h = av / m_aS.FirstV();
      if(m_bS.Query(h, bv))
         b_h = bv / m_bS.FirstV();
      m_last_ah = a_h;
      m_last_bh = b_h;

      double out[];
      if(!m_blend.Step(fc, fs, a_h, b_h, out))
        {
         m_err = "BookBlend.Step failed";
         return false;
        }

      // build_rows: rows with |v| > EPS, broker names, sorted by broker
      // name within the hour (epochs already ascend across hours);
      // all-flat present hour -> ONE __GRID__ sentinel
      string syms[BOOKORC_NBOOK];
      double vals[BOOKORC_NBOOK];
      int nr = 0;
      for(int k = 0; k < BOOKORC_NBOOK; k++)
        {
         double v = out[k];
         if(MathAbs(v) > BOOKORC_EPS)
           {
            syms[nr] = BookOrcBrokerName(m_blend.NetSymbol(k));
            vals[nr] = v;
            nr++;
           }
        }
      // insertion sort by broker name, ordinal (== python sort key)
      for(int i = 1; i < nr; i++)
        {
         string ks = syms[i];
         double kv = vals[i];
         int j = i - 1;
         while(j >= 0 && CBookBlend::CmpOrdinal(syms[j], ks) > 0)
           {
            syms[j + 1] = syms[j];
            vals[j + 1] = vals[j];
            j--;
           }
         syms[j + 1] = ks;
         vals[j + 1] = kv;
        }
      if(nr == 0)
        {
         EmitAppend(h, "__GRID__", 0.0);
         m_total_sentinels++;
        }
      else
         for(int i = 0; i < nr; i++)
            EmitAppend(h, syms[i], vals[i]);
      m_total_rows += (nr == 0 ? 1 : nr);
      m_total_hours++;
      m_last_emit_hour = h;
      return true;
     }

   // blend + emit for sat hour h: first drain pending core-only hours
   // (< h) with f_sat = 0, then hour h itself with its f_core row (or 0)
   bool              BlendAndEmit(const long h, const double &fsat[])
     {
      double zeros_sat[SATEQ_NSYM];
      double fc[BOOKORC_NNET];
      ArrayInitialize(zeros_sat, 0.0);

      while(m_fc_cursor < m_core.FCoreRows() && m_core.FCoreTs(m_fc_cursor) < h)
        {
         if(!FCoreConsumable(m_fc_cursor))
            return false;
         for(int s = 0; s < BOOKORC_NNET; s++)
            fc[s] = m_core.FCoreAt(m_fc_cursor, s);
         if(!EmitHour(m_core.FCoreTs(m_fc_cursor), fc, zeros_sat))
            return false;
         m_fc_cursor++;
        }

      bool have_fc = (m_fc_cursor < m_core.FCoreRows()
                      && m_core.FCoreTs(m_fc_cursor) == h);
      if(have_fc)
        {
         if(!FCoreConsumable(m_fc_cursor))
            return false;
         for(int s = 0; s < BOOKORC_NNET; s++)
            fc[s] = m_core.FCoreAt(m_fc_cursor, s);
         m_fc_cursor++;
        }
      else
        {
         // static_blend: core_frac.reindex(hours).fillna(0.0). If the
         // core feed simply has not reached h yet (cursor exhausted,
         // feed not done), a zero here would silently corrupt — refuse.
         // LIVE-CORE exception: when the live core clock has verifiably
         // advanced past the whole hour (LiveCoreAdvance(h+1h)) and no
         // core union bar printed in [h, h+1h), fillna(0.0) IS the
         // exact static_blend semantics, not a corruption.
         if(m_fc_cursor >= m_core.FCoreRows() && !m_core_done)
           {
            if(!(m_live_core && m_live_core_through >= h + 3600))
              {
               m_err = StringFormat("core feed behind the H1 clock at hour %I64d "
                                    "(f_core rows exhausted, feed not done)", h);
               return false;
              }
           }
         for(int s = 0; s < BOOKORC_NNET; s++)
            fc[s] = 0.0;
        }
      return EmitHour(h, fc, fsat);
     }

   // stage the 8 sleeve rows for hour ts and produce f_sat[31], then
   // record it in the held ring and blend/emit the hour
   bool              StageStepEmit(const long ts_sec,
                                   const double &mr[], const double &cbk[],
                                   const double &id[], const double &cr[],
                                   const double &tv[], const double &mg[],
                                   const double &emit4[])
     {
      double se[1], cs3[3];
      se[0]  = emit4[0];
      cs3[0] = emit4[1];
      cs3[1] = emit4[2];
      cs3[2] = emit4[3];
      bool ok = true;
      ok = ok && m_shell.SetSleeveRow("meanrev",        mr);
      ok = ok && m_shell.SetSleeveRow("carry_breakout", cbk);
      ok = ok && m_shell.SetSleeveRow("seasonal",       se);
      ok = ok && m_shell.SetSleeveRow("intraday",       id);
      ok = ok && m_shell.SetSleeveRow("crisis",         cr);
      ok = ok && m_shell.SetSleeveRow("trend_v2",       tv);
      ok = ok && m_shell.SetSleeveRow("crypto_smart",   cs3);
      ok = ok && m_shell.SetSleeveRow("mag",            mg);
      if(!ok)
        {
         m_err = "Ensemble SetSleeveRow failed";
         return false;
        }
      double fsat[];
      if(!m_shell.Step((datetime)ts_sec, fsat))
        {
         m_err = "Ensemble Step failed";
         return false;
        }
      // held ring: the b engine's tgt source (raw f_sat, model book row)
      int slot = m_held_n % BOOKORC_HELD;
      m_held_ts[slot] = ts_sec;
      for(int k = 0; k < SATEQ_NSYM; k++)
         m_held_row[slot][k] = fsat[k];
      m_held_n++;
      return BlendAndEmit(ts_sec, fsat);
     }

public:
                     CBookOrchestrator() : m_has_day(false), m_cur_day(0),
                                           m_have_prev(false), m_prev_ts(0),
                                           m_h1_bars(0), m_h1_last_ts(-1),
                                           m_finalized(false),
                                           m_ix_xau(-1), m_ix_btc(-1),
                                           m_ix_eth(-1), m_ix_sol(-1),
                                           m_m1_last_ts(-1), m_m1_bars(0),
                                           m_b_eqc(0.0), m_b_eqw(0.0),
                                           m_seg_open(false), m_n_segs(0),
                                           m_seed(0.0), m_core_done(false),
                                           m_fc_cursor(0),
                                           m_live_core(false),
                                           m_live_core_through(0),
                                           m_live_sc_mismatch(0),
                                           m_live_have_emit4(false),
                                           m_held_n(0),
                                           m_emit_n(0), m_last_emit_hour(0),
                                           m_total_rows(0), m_total_hours(0),
                                           m_total_sentinels(0),
                                           m_last_ah(1.0), m_last_bh(1.0),
                                           m_err(""), m_ready(false) {}

   string            LastError() const { return m_err;   }
   bool              Ready()     const { return m_ready; }

   //---------------------------------------------------------------//
   // Init — build every component and the wiring maps.             //
   // core_seed = the anchor INIT (10000.0, CoreSim segment-0 seed).//
   //---------------------------------------------------------------//
   bool              Init(const double w = BOOKORC_W,
                          const double core_seed = 10000.0)
     {
      m_ready = false;
      m_err = "";

      // --- H1 input column maps -----------------------------------
      if(!MapSyms(SatMR_SYMBOLS,   m_mr_ix, SatMR_NSYM))    return false;
      if(!MapSyms(SATCB_SYMBOLS,   m_cb_ix, SATCB_N_SYM))   return false;
      if(!MapSyms(BOOKORC_ID_SYMS, m_id_ix, 2))             return false;
      if(!MapSyms(SatTV2_SYMS,     m_tv_ix, SatTV2_NSYM))   return false;
      for(int i = 0; i < SatCRISIS_NIN; i++)
        {
         m_cr_in_ix[i] = InSymIndex(SatCrisisInputSym(i));
         if(m_cr_in_ix[i] < 0)
           {
            m_err = "crisis input symbol unmapped";
            return false;
           }
        }
      for(int k = 0; k < BOOKORC_NKEEP; k++)
        {
         m_cb_keep_ix[k] = -1;
         for(int j = 0; j < SATCB_N_SYM; j++)
            if(SATCB_SYMBOLS[j] == BOOKORC_CB_KEPT[k])
              {
               m_cb_keep_ix[k] = j;
               break;
              }
         if(m_cb_keep_ix[k] < 0)
           {
            m_err = "carry kept column unmapped: " + BOOKORC_CB_KEPT[k];
            return false;
           }
        }
      m_ix_xau = InSymIndex("XAUUSD");
      m_ix_btc = InSymIndex("BTCUSD");
      m_ix_eth = InSymIndex("ETHUSD");
      m_ix_sol = InSymIndex("SOLUSD");
      if(m_ix_xau < 0 || m_ix_btc < 0 || m_ix_eth < 0 || m_ix_sol < 0)
        {
         m_err = "xau/btc/eth/sol unmapped";
         return false;
        }

      // --- sleeves + ensemble shell -------------------------------
      m_intr.InitDefault();
      string cr_syms[SatCRISIS_NOUT];
      for(int j = 0; j < SatCRISIS_NOUT; j++)
         cr_syms[j] = SatCrisisSym(j);
      m_shell.Reset();
      bool ok = true;
      ok = ok && m_shell.AddSleeve("meanrev",        SatMR_SYMBOLS);
      ok = ok && m_shell.AddSleeve("carry_breakout", BOOKORC_CB_KEPT);
      ok = ok && m_shell.AddSleeve("seasonal",       BOOKORC_SEA_SYMS);
      ok = ok && m_shell.AddSleeve("intraday",       BOOKORC_ID_SYMS);
      ok = ok && m_shell.AddSleeve("crisis",         cr_syms);
      ok = ok && m_shell.AddSleeve("trend_v2",       SatTV2_SYMS);
      ok = ok && m_shell.AddSleeve("crypto_smart",   Sat_SC_CR_SYMBOLS);
      ok = ok && m_shell.AddSleeve("mag",            BOOKORC_MAG_SYMS);
      ok = ok && m_shell.Finalize();
      if(!ok || m_shell.SymbolCount() != SATEQ_NSYM)
        {
         m_err = StringFormat("ensemble shell build failed (symbols=%d, want %d)",
                              m_shell.SymbolCount(), SATEQ_NSYM);
         return false;
        }
      // the b engine consumes f_sat positionally: shell order MUST equal
      // SATEQ_SYMBOLS (both are the sorted golden book columns)
      for(int k = 0; k < SATEQ_NSYM; k++)
         if(m_shell.SymbolAt(k) != SATEQ_SYMBOLS[k])
           {
            m_err = StringFormat("shell symbol %d '%s' != SATEQ '%s'",
                                 k, m_shell.SymbolAt(k), SATEQ_SYMBOLS[k]);
            return false;
           }

      // --- CoreSim book (a + f_core) ------------------------------
      if(!m_core.SetSlots(7))
        {
         m_err = "CoreSim SetSlots: " + m_core.LastError();
         return false;
        }
      for(int i = 0; i < BOOKORC_NLEGS; i++)
         if(m_core.AddLeg(BOOKORC_LEG_SLOT[i], BOOKORC_LEG_CONTRACT[i],
                          BOOKORC_LEG_COMM[i], BOOKORC_LEG_LEV[i],
                          BOOKORC_LEG_STEP[i], BOOKORC_LEG_MIN[i]) != i)
           {
            m_err = "CoreSim AddLeg: " + m_core.LastError();
            return false;
           }
      if(!m_core.SetNets(BOOKORC_NNET))
        {
         m_err = "CoreSim SetNets: " + m_core.LastError();
         return false;
        }
      for(int i = 0; i < BOOKORC_NLEGS; i++)
         if(!m_core.AssignLegNet(i, BOOKORC_LEG_NET[i]))
           {
            m_err = "CoreSim AssignLegNet: " + m_core.LastError();
            return false;
           }

      // --- b engine + blend ----------------------------------------
      m_beng.Reset();
      string sat_syms[SATEQ_NSYM];
      for(int k = 0; k < SATEQ_NSYM; k++)
         sat_syms[k] = SATEQ_SYMBOLS[k];
      if(!m_blend.Init(w, BOOKORC_NET_SYMS, sat_syms))
        {
         m_err = "BookBlend Init failed";
         return false;
        }
      if(m_blend.NetCount() != BOOKORC_NBOOK)
        {
         m_err = StringFormat("blend NetCount %d != %d",
                              m_blend.NetCount(), BOOKORC_NBOOK);
         return false;
        }

      // --- glue state ----------------------------------------------
      double nan = SatNan();
      for(int i = 0; i < BOOKORC_NIN; i++)
         m_ffill[i] = nan;
      m_has_day = false;
      m_cur_day = 0;
      ArrayResize(m_tvq_eff, 0);
      ArrayResize(m_tvq_w, 0);
      ArrayResize(m_crq_eff, 0);
      ArrayResize(m_crq_w, 0);
      for(int j = 0; j < SatTV2_NSYM; j++)
         m_trend_cur[j] = 0.0;
      for(int j = 0; j < SatCRISIS_NOUT; j++)
         m_crisis_cur[j] = nan;
      m_have_prev = false;
      m_prev_ts = 0;
      m_h1_bars = 0;
      m_h1_last_ts = -1;
      m_finalized = false;
      m_aS.Reset();
      m_bS.Reset();
      m_m1_last_ts = -1;
      m_m1_bars = 0;
      m_b_eqc = 0.0;
      m_b_eqw = 0.0;
      m_seg_open = false;
      m_n_segs = 0;
      m_seed = core_seed;
      m_core_done = false;
      m_fc_cursor = 0;
      m_live_core = false;
      m_live_core_through = 0;
      m_live_sc_mismatch = 0;
      m_live_have_emit4 = false;
      for(int i = 0; i < BOOKORC_HELD; i++)
         m_held_ts[i] = -1;
      m_held_n = 0;
      m_emit_n = 0;
      m_last_emit_hour = 0;
      m_total_rows = 0;
      m_total_hours = 0;
      m_total_sentinels = 0;
      m_last_ah = 1.0;
      m_last_bh = 1.0;
      m_ready = true;
      return true;
     }

   //---------------------------------------------------------------//
   // Core feed (segment-batch, FROZEN leg tgt — drive contract 1)  //
   //---------------------------------------------------------------//
   bool              BeginCoreSegment()
     {
      if(!m_ready)     { m_err = "not initialized";           return false; }
      if(m_seg_open)   { m_err = "segment already open";      return false; }
      if(m_core_done)  { m_err = "core feed already done";    return false; }
      if(!m_core.BeginSegment(m_seed))
        {
         m_err = "BeginSegment: " + m_core.LastError();
         return false;
        }
      m_seg_open = true;
      return true;
     }

   bool              StepCoreLegBar(const int leg, const long ts,
                                    const double bid_o, const double bid_h,
                                    const double bid_l, const double bid_c,
                                    const double ask_o, const double ask_h,
                                    const double ask_l, const double ask_c,
                                    const double eurq, const double swap_flag,
                                    const double swap_long, const double swap_short,
                                    const double tgt)
     {
      if(!m_seg_open)  { m_err = "no open segment";           return false; }
      if(!m_core.StepLegBar(leg, ts, bid_o, bid_h, bid_l, bid_c,
                            ask_o, ask_h, ask_l, ask_c,
                            eurq, swap_flag, swap_long, swap_short, tgt))
        {
         m_err = "StepLegBar: " + m_core.LastError();
         return false;
        }
      return true;
     }

   bool              EndCoreSegment()
     {
      if(!m_seg_open)  { m_err = "no open segment";           return false; }
      if(!m_core.FinishSegment())
        {
         m_err = "FinishSegment: " + m_core.LastError();
         return false;
        }
      // harvest the combined 1m eqc into the asof hour sampler (a_first
      // = the very first union value of segment 0, the iloc[0] anchor)
      int un = m_core.UnionBars();
      for(int i = 0; i < un; i++)
         if(!m_aS.Add(m_core.UnionTs(i), m_core.EqC(i)))
           {
            m_err = StringFormat("a-sampler: non-ascending union stamp at %d", i);
            return false;
           }
      if(!m_core.ComputeFCore())
        {
         m_err = "ComputeFCore: " + m_core.LastError();
         return false;
        }
      m_seed = m_core.FinalEqC();              // spec 6.2 seed chain
      m_seg_open = false;
      m_n_segs++;
      return true;
     }

   bool              SetCoreFeedDone()
     {
      if(m_seg_open)   { m_err = "segment still open";        return false; }
      m_core_done = true;
      return true;
     }

   //---------------------------------------------------------------//
   // StepM1 — one 1m union-grid Sat row (drive contract 2).        //
   // Arrays in SATEQ_SYMBOLS order; eurq passed as the 8 EUR cross //
   // values (exporter columns), mapped per-symbol internally.      //
   // The b tgt is the HELD f_sat row at exactly floor(ts,1h)-1h    //
   // (absent row -> 0.0) — the iter_chunks lag law.                //
   //---------------------------------------------------------------//
   bool              StepM1(const long ts, const bool &has[],
                            const double &bid_o[], const double &ask_o[],
                            const double &bid_c[], const double &ask_c[],
                            const double &bid_l[], const double &ask_h[],
                            const double &eurq_cross[],
                            const double &swap_l[], const double &swap_s[])
     {
      if(!m_ready)          { m_err = "not initialized";      return false; }
      if(ts <= m_m1_last_ts) { m_err = "M1 stamps must ascend"; return false; }

      // held f_sat -> tgt (exact-hour match, NaN scrub, else flat)
      long wanted = ts - (ts % 3600) - 3600;
      double tgt[SATEQ_NSYM];
      int slot = -1;
      for(int i = 0; i < BOOKORC_HELD; i++)
         if(m_held_ts[i] == wanted)
           {
            slot = i;
            break;
           }
      if(slot >= 0)
         for(int k = 0; k < SATEQ_NSYM; k++)
           {
            double v = m_held_row[slot][k];
            tgt[k] = (v == v) ? v : 0.0;       // np.nan_to_num
           }
      else
         for(int k = 0; k < SATEQ_NSYM; k++)
            tgt[k] = 0.0;                      // reindex method=None miss

      // per-symbol eurq from its quote-ccy cross (EUR quote -> 1.0)
      double eurq_sym[SATEQ_NSYM];
      for(int k = 0; k < SATEQ_NSYM; k++)
         eurq_sym[k] = (BOOKORC_CROSS_IX[k] < 0)
                       ? 1.0 : eurq_cross[BOOKORC_CROSS_IX[k]];

      m_beng.Step(tgt, has, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
                  eurq_sym, swap_l, swap_s, m_b_eqc, m_b_eqw);
      if(!m_bS.Add(ts, m_b_eqc))
        {
         m_err = "b-sampler: non-ascending stamp";
         return false;
        }
      m_m1_last_ts = ts;
      m_m1_bars++;
      return true;
     }

   //---------------------------------------------------------------//
   // StepH1 — one hourly union-grid signal row (raw closes, NaN =  //
   // symbol printed no bar this hour). Statement port of the       //
   // TestV34Native.mq5 / harness_sim.py driving loop; on the       //
   // deferred SeasonalCrypto emission the PREVIOUS grid hour is    //
   // assembled, blended and emitted (read via Emit* accessors).    //
   //---------------------------------------------------------------//
   bool              StepH1(const long ts, const double &raw[])
     {
      if(!m_ready)          { m_err = "not initialized";        return false; }
      if(m_finalized)       { m_err = "already finalized";      return false; }
      if(ArraySize(raw) != BOOKORC_NIN)
        {
         m_err = "raw[] must be 37 wide";
         return false;
        }
      if(ts <= m_h1_last_ts) { m_err = "H1 stamps must ascend";  return false; }
      if((ts % 3600) != 0)
        {
         m_err = StringFormat("H1 stamp %I64d not hour-aligned", ts);
         return false;
        }
      m_emit_n = 0;
      long ts_ns = ts * (long)1000000000;

      //--- daily rollover: close the previous grid day ---------------
      long day = ts / 86400;
      if(!m_has_day)
        {
         m_has_day = true;
         m_cur_day = day;
        }
      else if(day != m_cur_day)
        {
         double tvcl[SatTV2_NSYM], held[];
         for(int j = 0; j < SatTV2_NSYM; j++)
            tvcl[j] = m_ffill[m_tv_ix[j]];
         m_tv.Step(tvcl, held);
         QPush(m_tvq_eff, m_tvq_w,
               (m_cur_day + 1) * 86400 + SatTV2_EXEC_HOUR * 3600,
               held, SatTV2_NSYM);
         if(((m_cur_day + 3) % 7) < 5)          // Mon..Fri only
           {
            double crcl[SatCRISIS_NIN];
            for(int j = 0; j < SatCRISIS_NIN; j++)
               crcl[j] = m_ffill[m_cr_in_ix[j]];
            SSatCrisisResult res;
            if(!m_crisis.Step((datetime)(m_cur_day * 86400), crcl, res))
              {
               m_err = StringFormat("crisis step failed at day %I64d", m_cur_day);
               return false;
              }
            QPush(m_crq_eff, m_crq_w, (long)res.effective, res.w,
                  SatCRISIS_NOUT);
           }
         m_cur_day = day;
        }

      //--- xau ret (prev ffill) then streaming ffill ------------------
      double prev_x = m_ffill[m_ix_xau];
      for(int j = 0; j < BOOKORC_NIN; j++)
         if(raw[j] == raw[j])
            m_ffill[j] = raw[j];
      double xret = 0.0;
      if(prev_x == prev_x)
        {
         double r = m_ffill[m_ix_xau] / prev_x - 1.0;
         if(r < -0.30)
            r = -0.30;
         else if(r > 0.30)
            r = 0.30;
         xret = r;
        }

      //--- activate pending daily targets -----------------------------
      while(ArraySize(m_tvq_eff) > 0 && m_tvq_eff[0] <= ts)
        {
         for(int j = 0; j < SatTV2_NSYM; j++)
            m_trend_cur[j] = m_tvq_w[j];
         QPop(m_tvq_eff, m_tvq_w, SatTV2_NSYM);
        }
      while(ArraySize(m_crq_eff) > 0 && m_crq_eff[0] <= ts)
        {
         for(int j = 0; j < SatCRISIS_NOUT; j++)
           {
            double v = m_crq_w[j];
            if(v == v)                          // NaN never overwrites
               m_crisis_cur[j] = v;
           }
         QPop(m_crq_eff, m_crq_w, SatCRISIS_NOUT);
        }

      //--- current-bar rows for the 7 non-deferred sleeves -------------
      double cur_mg[1], idcl[2], cur_id[], mrcl[SatMR_NSYM], cur_mr[];
      double cbcl[SATCB_N_SYM], cb32[SATCB_N_SYM], cur_cbk[BOOKORC_NKEEP];
      double cur_tv[SatTV2_NSYM], cur_cr[SatCRISIS_NOUT];
      cur_mg[0] = m_mag.StepNs(ts_ns, raw[m_ix_xau]);
      idcl[0] = raw[m_id_ix[0]];
      idcl[1] = raw[m_id_ix[1]];
      m_intr.StepNs(ts_ns, idcl, cur_id);
      for(int j = 0; j < SatMR_NSYM; j++)
         mrcl[j] = raw[m_mr_ix[j]];
      m_mr.Step((datetime)ts, mrcl, cur_mr);
      for(int j = 0; j < SATCB_N_SYM; j++)
         cbcl[j] = raw[m_cb_ix[j]];
      m_cb.Step(ts / 86400, cbcl, cb32);
      for(int k = 0; k < BOOKORC_NKEEP; k++)
         cur_cbk[k] = cb32[m_cb_keep_ix[k]];
      for(int j = 0; j < SatTV2_NSYM; j++)
         cur_tv[j] = m_trend_cur[j];
      for(int j = 0; j < SatCRISIS_NOUT; j++)   // 0.0 before first target
         cur_cr[j] = (m_crisis_cur[j] == m_crisis_cur[j]) ? m_crisis_cur[j] : 0.0;

      //--- seasonal/crypto: deferred one-bar emission --------------------
      long emit_ts_ns = 0;
      double emit4[];
      bool emitted = m_sc.StepNs(ts_ns, xret, m_ffill[m_ix_btc],
                                 m_ffill[m_ix_eth], m_ffill[m_ix_sol],
                                 emit_ts_ns, emit4);
      if(emitted)
        {
         if(!m_have_prev || emit_ts_ns != m_prev_ts * (long)1000000000)
           {
            m_err = StringFormat("SC emission misaligned at H1 bar %I64d", m_h1_bars);
            return false;
           }
         // LIVE-CORE: hour m_prev_ts may have been EARLY-emitted by
         // LiveEmitStaged at the h+1h boundary (the record book applies
         // fed[h] at h+1 — deferring emission to this bar would cost a
         // full extra hour live).  Skip the duplicate stage; verify the
         // SC stepper's ACTUAL row matches the assumed-next-hour row
         // (mismatch = a grid-gap hour; telemetry, not silent).
         bool live_dup = (m_live_core && m_total_hours > 0
                          && m_last_emit_hour >= m_prev_ts);
         if(live_dup)
           {
            if(m_live_have_emit4)
              {
               for(int q4 = 0; q4 < 4; q4++)
                  if(emit4[q4] != m_live_emit4[q4])
                    {
                     m_live_sc_mismatch++;
                     break;
                    }
               m_live_have_emit4 = false;
              }
           }
         else if(!StageStepEmit(m_prev_ts, m_prev_mr, m_prev_cbk, m_prev_id,
                                m_prev_cr, m_prev_tv, m_prev_mg, emit4))
            return false;
        }
      else if(m_h1_bars > 0)
        {
         m_err = StringFormat("expected SC emission at H1 bar %I64d", m_h1_bars);
         return false;
        }

      //--- buffer this bar's rows for the next emission -------------------
      for(int j = 0; j < SatMR_NSYM; j++)
         m_prev_mr[j] = cur_mr[j];
      for(int k = 0; k < BOOKORC_NKEEP; k++)
         m_prev_cbk[k] = cur_cbk[k];
      m_prev_id[0] = cur_id[0];
      m_prev_id[1] = cur_id[1];
      for(int j = 0; j < SatCRISIS_NOUT; j++)
         m_prev_cr[j] = cur_cr[j];
      for(int j = 0; j < SatTV2_NSYM; j++)
         m_prev_tv[j] = cur_tv[j];
      m_prev_mg[0] = cur_mg[0];
      m_prev_ts = ts;
      m_have_prev = true;
      m_h1_last_ts = ts;
      m_h1_bars++;
      return true;
     }

   //---------------------------------------------------------------//
   // FinalizeH1 — once, after the last H1 row: flush the deferred  //
   // SeasonalCrypto row (== sc.finalize()) and drain any trailing  //
   // core-only hours. Requires SetCoreFeedDone() first.            //
   //---------------------------------------------------------------//
   bool              FinalizeH1()
     {
      if(!m_ready)      { m_err = "not initialized";           return false; }
      if(m_finalized)   { m_err = "already finalized";         return false; }
      if(!m_core_done)  { m_err = "SetCoreFeedDone before FinalizeH1"; return false; }
      m_emit_n = 0;
      long emit_ts_ns = 0;
      double emit4[];
      if(m_sc.Finalize(emit_ts_ns, emit4))
        {
         if(!m_have_prev || emit_ts_ns != m_prev_ts * (long)1000000000)
           {
            m_err = "FINAL SC emission misaligned";
            return false;
           }
         if(!StageStepEmit(m_prev_ts, m_prev_mr, m_prev_cbk, m_prev_id,
                           m_prev_cr, m_prev_tv, m_prev_mg, emit4))
            return false;
        }
      // trailing core-only hours (core grid beyond the last sat hour)
      double zeros_sat[SATEQ_NSYM], fc[BOOKORC_NNET];
      ArrayInitialize(zeros_sat, 0.0);
      while(m_fc_cursor < m_core.FCoreRows())
        {
         for(int s = 0; s < BOOKORC_NNET; s++)
            fc[s] = m_core.FCoreAt(m_fc_cursor, s);
         if(!EmitHour(m_core.FCoreTs(m_fc_cursor), fc, zeros_sat))
            return false;
         m_fc_cursor++;
        }
      m_finalized = true;
      return true;
     }

   //---------------------------------------------------------------//
   // emitted rows of the LAST StepH1 / FinalizeH1 call             //
   //---------------------------------------------------------------//
   int               EmitCount() const { return m_emit_n; }
   long              EmitTs(const int i)  const { return (i >= 0 && i < m_emit_n) ? m_emit_ts[i]  : 0;   }
   string            EmitSymbol(const int i) const { return (i >= 0 && i < m_emit_n) ? m_emit_sym[i] : ""; }
   double            EmitFrac(const int i) const { return (i >= 0 && i < m_emit_n) ? m_emit_val[i] : 0.0; }

   //---------------------------------------------------------------//
   // introspection                                                 //
   //---------------------------------------------------------------//
   long              H1Bars()         const { return m_h1_bars;         }
   long              M1Bars()         const { return m_m1_bars;         }
   int               CoreSegments()   const { return m_n_segs;          }
   bool              CoreSegmentOpen() const { return m_seg_open;       }
   bool              CoreFeedDone()   const { return m_core_done;       }
   int               FCoreRows()      const { return m_core.FCoreRows(); }
   int               FCoreCursor()    const { return m_fc_cursor;       }
   double            CoreSeed()       const { return m_seed;            }
   long              TotalHours()     const { return m_total_hours;     }
   long              TotalRows()      const { return m_total_rows;      }
   long              TotalSentinels() const { return m_total_sentinels; }
   long              LastEmitHour()   const { return m_last_emit_hour;  }
   double            LastAH()         const { return m_last_ah;         }
   double            LastBH()         const { return m_last_bh;         }
   double            BEqC()           const { return m_b_eqc;           }
   double            BEqW()           const { return m_b_eqw;           }
   double            BBalance()       const { return m_beng.Balance();  }
   long              BTrades()        const { return m_beng.NTrades();  }

   // Flatten a restored b-sleeve position on a symbol the broker does not
   // list.  Model-name lookup; returns true only if a live lot was dropped
   // (so the caller can log it loudly).  See CSatEquityNative::ForceFlat.
   bool              BForceFlatSymbol(const string model)
     {
      for(int k = 0; k < SATEQ_NSYM; k++)
         if(SATEQ_SYMBOLS[k] == model)
            return m_beng.ForceFlat(k);
      return false;
     }
   double            AFirst()         const { return m_aS.Have() ? m_aS.FirstV() : 0.0; }
   double            BFirst()         const { return m_bS.Have() ? m_bS.FirstV() : 0.0; }
   int               NetCount()       const { return m_blend.NetCount(); }
   string            NetSymbolAt(const int k) const { return m_blend.NetSymbol(k); }

   // asof-normalized equity multiples at hour h (diagnostics; the
   // blend uses exactly these values)
   double            AH(const long h) const
     {
      double v = 0.0;
      if(m_aS.Query(h, v))
         return v / m_aS.FirstV();
      return 1.0;
     }
   double            BH(const long h) const
     {
      double v = 0.0;
      if(m_bS.Query(h, v))
         return v / m_bS.FirstV();
      return 1.0;
     }

   //================================================================//
   // LIVE-CORE additive hooks (FableBookNative.mq5 / CoreLiveDrive). //
   // INERT unless EnableLiveCore() — the S1 batch replay path (Begin//
   // CoreSegment/StepCoreLegBar/EndCoreSegment + TestBook) is       //
   // byte-for-byte the same behavior with the flag off (default).   //
   //================================================================//
   void              EnableLiveCore()        { m_live_core = true;        }
   bool              LiveCoreOn()      const { return m_live_core;        }
   long              LiveScMismatches() const { return m_live_sc_mismatch; }
   long              LiveCoreThrough() const { return m_live_core_through; }

   // one live combined-eqc 1m sample (the a-curve; strictly ascending)
   bool              LiveCoreSample(const long ts, const double eqc)
     {
      if(!m_live_core)  { m_err = "live-core mode off"; return false; }
      if(!m_aS.Add(ts, eqc))
        {
         m_err = "a-sampler: non-ascending live core stamp";
         return false;
        }
      return true;
     }

   // one COMPLETED hour's live f_core row (values final by construction)
   bool              LiveCoreAppend(const long hour, const double &fc[])
     {
      if(!m_live_core)  { m_err = "live-core mode off"; return false; }
      if(!m_core.AppendFCoreRow(hour, fc))
        {
         m_err = "AppendFCoreRow: " + m_core.LastError();
         return false;
        }
      return true;
     }

   // advance the live core clock (exclusive): asserts every core union
   // bar with stamp < through has been sampled/appended
   void              LiveCoreAdvance(const long through_exclusive)
     {
      if(through_exclusive > m_live_core_through)
         m_live_core_through = through_exclusive;
     }

   // LiveEmitStaged — emit the JUST-CLOSED hour's blend row NOW.
   // The record book applies fed[h] at h+1 (data through h+1h is
   // exactly what exists at that wall instant); the batch chain defers
   // emission to the NEXT H1 bar (SeasonalCrypto deferred emit), which
   // live would cost one extra hour of application lag.  This method
   // reproduces the deferred SC emission arithmetic (hold.shift(-1) *
   // m_sea_w, prev crypto row) with the hold gate taken from the
   // ASSUMED next grid hour; when the real next bar arrives StepH1
   // verifies the assumption (mismatch -> m_live_sc_mismatch).
   bool              LiveEmitStaged(const long assumed_next_ts)
     {
      if(!m_live_core)  { m_err = "live-core mode off"; return false; }
      if(!m_have_prev)  { m_err = "nothing staged";     return false; }
      if(!m_sc.m_have_prev
         || m_sc.m_prev_ts != m_prev_ts * (long)1000000000)
        {
         m_err = "SC staged row misaligned with glue prev_ts";
         return false;
        }
      if(m_total_hours > 0 && m_last_emit_hour >= m_prev_ts)
        {
         m_err = StringFormat("hour %I64d already emitted", m_prev_ts);
         return false;
        }
      m_emit_n = 0;
      // == the StepNs emission path: hold_next from the next bar's hour
      int hh = (int)((assumed_next_ts % 86400) / 3600);
      double hold_next = (hh == Sat_SC_SEA_ENTRY_HOUR
                          || hh < Sat_SC_SEA_END_HOUR) ? 1.0 : 0.0;
      double emit4[4];
      emit4[0] = hold_next * m_sc.m_sea_w;
      for(int k = 0; k < 3; k++)
         emit4[1 + k] = m_sc.m_prev_cr_row[k];
      for(int q = 0; q < 4; q++)
         m_live_emit4[q] = emit4[q];
      m_live_have_emit4 = true;
      return StageStepEmit(m_prev_ts, m_prev_mr, m_prev_cbk, m_prev_id,
                           m_prev_cr, m_prev_tv, m_prev_mg, emit4);
     }

   //================================================================//
   // BookState hooks (Book/BookState.mqh) — ADDITIVE serialization  //
   // of the COMPLETE live ledger.  ZERO compute-path change: these  //
   // methods only read/write existing fields and call the           //
   // components' own proven GetState/SetState.                      //
   // Save is only legal BETWEEN core segments (seg_open refused).   //
   // On a failed BsSetState the orchestrator may be PARTIALLY       //
   // restored: the caller must Init() again before any other use    //
   // (CBookState latches REFUSE_TO_TRADE in that case).             //
   //================================================================//
private:
   void              BsWriteSampler(CBookStateWriter &w,
                                    const CBookOrcHourSampler &sp)
     {
      w.Raw("{\"have\": ");
      w.B(sp.Have());
      w.KI("base",     sp.BaseTs());
      w.KI("first_ts", sp.FirstTs());
      w.KD("first_v",  sp.FirstV());
      w.KI("last_ts",  sp.LastTs());
      w.KD("last_v",   sp.LastV());
      w.KI("n", sp.Samples());
      w.CK("v");
      w.Raw("[");
      int n = sp.Samples();
      for(int i = 0; i < n; i++)
        {
         if(i > 0)
            w.Raw(", ");
         w.D(sp.SampleAt(i));
        }
      w.Raw("]}");
     }

   bool              BsReadSampler(CBookStateTok &tk, CBookOrcHourSampler &sp,
                                   const string what)
     {
      bool   have = false;
      long   base = 0, fts = 0, lts = 0, n = 0;
      double fv = 0.0, lv = 0.0;
      bool ok = tk.Eat('{') && tk.Key("have") && tk.BoolVal(have);
      ok = ok && tk.CommaKey("base")     && tk.IntVal(base);
      ok = ok && tk.CommaKey("first_ts") && tk.IntVal(fts);
      ok = ok && tk.CommaKey("first_v")  && tk.NumVal(fv);
      ok = ok && tk.CommaKey("last_ts")  && tk.IntVal(lts);
      ok = ok && tk.CommaKey("last_v")   && tk.NumVal(lv);
      ok = ok && tk.CommaKey("n")        && tk.IntVal(n);
      double v[];
      ok = ok && tk.CommaKey("v") && tk.ArrD(v, (int)n) && tk.Eat('}');
      if(!ok)
        {
         m_err = what + " sampler: " + tk.Err();
         return false;
        }
      if(!sp.Restore(have, base, fts, fv, lts, lv, v, (int)n))
        {
         m_err = what + " sampler: Restore rejected (inconsistent fields)";
         return false;
        }
      return true;
     }

public:
   //---------------------------------------------------------------//
   // BsWriteState — serialize everything (root members "config"     //
   // through "samplers"; CBookState adds envelope + continuity +    //
   // trailer).  Doubles %.17g via the writer, NEVER truncated.      //
   //---------------------------------------------------------------//
   bool              BsWriteState(CBookStateWriter &w)
     {
      if(!m_ready)   { m_err = "not initialized";                return false; }
      if(m_seg_open) { m_err = "save inside an open core segment"; return false; }

      // ---- config (verified on restore: component-count anchors) ---
      w.Raw("\"config\": {\"w\": ");
      w.D(m_blend.CoreWeight());
      w.KI("nin",    BOOKORC_NIN);
      w.KI("nsat",   SATEQ_NSYM);
      w.KI("nnet",   BOOKORC_NNET);
      w.KI("nbook",  BOOKORC_NBOOK);
      w.KI("nlegs",  BOOKORC_NLEGS);
      w.KI("held",   BOOKORC_HELD);
      w.KI("ncross", BOOKORC_NCROSS);
      w.Raw("}");

      // ---- sleeves ---------------------------------------------------
      w.Raw(", \"sleeves\": {");

      // mag (struct state)
      SSatMagXauState mg;
      m_mag.GetState(mg);
      w.Raw("\"mag\": {\"mids\": ");
      w.ArrD(mg.mids, ArraySize(mg.mids));
      w.KB("has_accum_day", mg.has_accum_day);
      w.KI("accum_day",     mg.accum_day);
      w.KD("accum_close",   mg.accum_close);
      w.CK("pend_ts");
      w.ArrL(mg.pending_ts,  ArraySize(mg.pending_ts));
      w.CK("pend_tgt");
      w.ArrD(mg.pending_tgt, ArraySize(mg.pending_tgt));
      w.KD("current", mg.current);
      w.Raw("}");

      // intraday (2 syms x 13 doubles, documented flat order)
        {
         bool hd = false;
         long cd = 0;
         SSatIntradaySymState isy[];
         m_intr.GetState(hd, cd, isy);
         if(ArraySize(isy) != 2)
           {
            m_err = "intraday state width != 2";
            return false;
           }
         double fl[26];
         for(int k = 0; k < 2; k++)
           {
            int o = k * 13;
            fl[o + 0]  = isy[k].prev_close;
            fl[o + 1]  = isy[k].vol_num;
            fl[o + 2]  = isy[k].vol_den;
            fl[o + 3]  = isy[k].vol;
            fl[o + 4]  = isy[k].w_vol;
            fl[o + 5]  = isy[k].sc_num;
            fl[o + 6]  = isy[k].sc_den;
            fl[o + 7]  = (double)isy[k].sc_nobs;
            fl[o + 8]  = isy[k].c15;
            fl[o + 9]  = isy[k].has15 ? 1.0 : 0.0;
            fl[o + 10] = isy[k].has16 ? 1.0 : 0.0;
            fl[o + 11] = isy[k].mv_pending;
            fl[o + 12] = isy[k].sig;
           }
         w.Raw(", \"intraday\": {\"has_day\": ");
         w.B(hd);
         w.KI("cur_day", cd);
         w.CK("flat");
         w.ArrD(fl, 26);
         w.Raw("}");
        }

      // meanrev (struct state, field arrays)
        {
         SSatMeanRevState ms;
         m_mr.GetState(ms);
         double par[14];
         par[0]  = (double)ms.L;
         par[1]  = ms.z_in;
         par[2]  = ms.z_out;
         par[3]  = (double)ms.D;
         par[4]  = ms.z_entry;
         par[5]  = ms.K;
         par[6]  = ms.z_exit;
         par[7]  = (double)ms.trend_L;
         par[8]  = (double)ms.max_hold;
         par[9]  = (double)ms.exec_lag;
         par[10] = ms.vol_floor;
         par[11] = ms.pos_cap;
         par[12] = ms.gross_cap;
         par[13] = (double)ms.vol_span;
         w.Raw(", \"meanrev\": {\"params\": ");
         w.ArrD(par, 14);
         w.KI("cur_day", ms.cur_day);
         w.KI("dcount",  ms.dcount);
         w.KI("dptr",    ms.dptr);
         w.CK("close");
         w.ArrD(ms.close, SatMR_NSYM);
         w.CK("wavg");
         w.ArrD(ms.wavg, SatMR_NSYM);
         w.CK("old_wt");
         w.ArrD(ms.old_wt, SatMR_NSYM);
         w.CK("nobs");
         w.ArrL(ms.nobs, SatMR_NSYM);
         w.CK("dbuf");
         w.Raw("[");
         for(int i = 0; i < SatMR_NSYM; i++)
            for(int j = 0; j < SatMR_RING; j++)
              {
               if(i + j > 0)
                  w.Raw(", ");
               w.D(ms.dbuf[i][j]);
              }
         w.Raw("]");
         long st16[SatMR_NSYM], hd6[SatMR_NIDX];
         for(int i = 0; i < SatMR_NSYM; i++)
            st16[i] = (long)ms.st[i];
         for(int i = 0; i < SatMR_NIDX; i++)
            hd6[i] = (long)ms.held[i];
         w.CK("st");
         w.ArrL(st16, SatMR_NSYM);
         w.CK("held");
         w.ArrL(hd6, SatMR_NIDX);
         w.CK("size");
         w.ArrD(ms.size, SatMR_NSYM);
         w.CK("pos");
         w.ArrD(ms.pos, SatMR_NSYM);
         w.KI("pend_count", ms.pend_count);
         w.CK("pend_eff");
         w.Raw("[");
         for(int k = 0; k < ms.pend_count; k++)
           {
            if(k > 0)
               w.Raw(", ");
            w.I((long)ms.pend_eff[k]);
           }
         w.Raw("]");
         w.CK("pend_pos");
         w.Raw("[");
         for(int k = 0; k < ms.pend_count; k++)
            for(int i = 0; i < SatMR_NSYM; i++)
              {
               if(k + i > 0)
                  w.Raw(", ");
               w.D(ms.pend_pos[k][i]);
              }
         w.Raw("]}");
        }

      // crisis (flat double array, python dict order)
        {
         double cst[];
         int nc = m_crisis.GetState(cst);
         if(nc != SatCRISIS_STATE_SIZE)
           {
            m_err = "crisis state size drift";
            return false;
           }
         w.CK("crisis");
         w.ArrD(cst, nc);
        }

      // JSON-string components (their own proven %.17g serializers)
      w.CK("seasonal_crypto");
      w.Raw(m_sc.GetState());
      w.CK("carry_breakout");
      w.Raw(m_cb.GetState());
      w.CK("trend_v2");
      w.Raw(m_tv.GetState());
      // ensemble is config-only (stateless across bars): stored for the
      // component-config check on restore
      w.CK("ensemble");
      w.Q(m_shell.GetState());
      w.Raw("}");

      // ---- b engine ---------------------------------------------------
      w.CK("b_engine");
      w.Raw(m_beng.GetState());

      // ---- core (CoreSim seam carry + f_core ledger + cursor/seed) ----
      w.Raw(", \"core\": {\"n_segs\": ");
      w.I(m_n_segs);
      w.KD("seed", m_seed);
      w.KB("seg_open",  m_seg_open);
      w.KB("core_done", m_core_done);
      w.KI("fc_cursor", m_fc_cursor);
        {
         long   cvl[BOOKORC_NLEGS];
         double cps[BOOKORC_NLEGS], cmd[BOOKORC_NLEGS], cqe[BOOKORC_NLEGS];
         for(int l = 0; l < BOOKORC_NLEGS; l++)
           {
            cvl[l] = m_core.CarryValid(l) ? 1 : 0;
            cps[l] = m_core.CarryPos(l);
            cmd[l] = m_core.CarryMid(l);
            cqe[l] = m_core.CarryQe(l);
           }
         w.CK("carry_valid");
         w.ArrL(cvl, BOOKORC_NLEGS);
         w.CK("carry_pos");
         w.ArrD(cps, BOOKORC_NLEGS);
         w.CK("carry_mid");
         w.ArrD(cmd, BOOKORC_NLEGS);
         w.CK("carry_qe");
         w.ArrD(cqe, BOOKORC_NLEGS);
        }
      int fn = m_core.FCoreRows();
      w.KI("fcore_n", fn);
      w.CK("fcore_ts");
      w.Raw("[");
      for(int k = 0; k < fn; k++)
        {
         if(k > 0)
            w.Raw(", ");
         w.I(m_core.FCoreTs(k));
        }
      w.Raw("]");
      w.CK("fcore_v");
      w.Raw("[");
      for(int k = 0; k < fn; k++)
         for(int s = 0; s < BOOKORC_NNET; s++)
           {
            if(k + s > 0)
               w.Raw(", ");
            w.D(m_core.FCoreAt(k, s));
           }
      w.Raw("]}");

      // ---- glue --------------------------------------------------------
      w.Raw(", \"glue\": {\"ffill\": ");
      w.ArrD(m_ffill, BOOKORC_NIN);
      w.KB("has_day", m_has_day);
      w.KI("cur_day", m_cur_day);
      int ntv = ArraySize(m_tvq_eff);
      int ncr = ArraySize(m_crq_eff);
      w.KI("tvq_n", ntv);
      w.CK("tvq_eff");
      w.ArrL(m_tvq_eff, ntv);
      w.CK("tvq_w");
      w.ArrD(m_tvq_w, ntv * SatTV2_NSYM);
      w.KI("crq_n", ncr);
      w.CK("crq_eff");
      w.ArrL(m_crq_eff, ncr);
      w.CK("crq_w");
      w.ArrD(m_crq_w, ncr * SatCRISIS_NOUT);
      w.CK("trend_cur");
      w.ArrD(m_trend_cur, SatTV2_NSYM);
      w.CK("crisis_cur");
      w.ArrD(m_crisis_cur, SatCRISIS_NOUT);
      w.KB("have_prev", m_have_prev);
      w.KI("prev_ts",   m_prev_ts);
      w.CK("prev_mr");
      w.ArrD(m_prev_mr, SatMR_NSYM);
      w.CK("prev_cbk");
      w.ArrD(m_prev_cbk, BOOKORC_NKEEP);
      w.CK("prev_id");
      w.ArrD(m_prev_id, 2);
      w.CK("prev_cr");
      w.ArrD(m_prev_cr, SatCRISIS_NOUT);
      w.CK("prev_tv");
      w.ArrD(m_prev_tv, SatTV2_NSYM);
      w.CK("prev_mg");
      w.ArrD(m_prev_mg, 1);
      w.KI("h1_bars",    m_h1_bars);
      w.KI("h1_last_ts", m_h1_last_ts);
      w.KB("finalized",  m_finalized);
      w.KI("m1_last_ts", m_m1_last_ts);
      w.KI("m1_bars",    m_m1_bars);
      w.KD("b_eqc", m_b_eqc);
      w.KD("b_eqw", m_b_eqw);
      w.KI("held_n", m_held_n);
      w.CK("held_ts");
      w.ArrL(m_held_ts, BOOKORC_HELD);
      w.CK("held_rows");
      w.Raw("[");
      for(int i = 0; i < BOOKORC_HELD; i++)
         for(int k = 0; k < SATEQ_NSYM; k++)
           {
            if(i + k > 0)
               w.Raw(", ");
            w.D(m_held_row[i][k]);
           }
      w.Raw("]");
      w.KI("last_emit_hour",  m_last_emit_hour);
      w.KI("total_rows",      m_total_rows);
      w.KI("total_hours",     m_total_hours);
      w.KI("total_sentinels", m_total_sentinels);
      w.KD("last_ah", m_last_ah);
      w.KD("last_bh", m_last_bh);
      w.Raw("}");

      // ---- a/b hour samplers -------------------------------------------
      w.Raw(", \"samplers\": {\"a\": ");
      BsWriteSampler(w, m_aS);
      w.CK("b");
      BsWriteSampler(w, m_bS);
      w.Raw("}");
      return true;
     }

   //---------------------------------------------------------------//
   // BsSetState — parse + validate + restore ("config" through      //
   // "samplers"; the tokenizer is left positioned for CBookState's  //
   // continuity block).  Requires a fresh Init() first (component   //
   // wiring/config is rebuilt by Init, verified here).              //
   //---------------------------------------------------------------//
   bool              BsSetState(CBookStateTok &tk)
     {
      if(!m_ready)
        {
         m_err = "not initialized (Init before restore)";
         return false;
        }

      // ---- config: verify against the live wiring ---------------------
      double cw = 0.0;
      long nin = 0, nsat = 0, nnet = 0, nbook = 0, nlegs = 0, held = 0, ncross = 0;
      bool ok = tk.Key("config") && tk.Eat('{');
      ok = ok && tk.Key("w") && tk.NumVal(cw);
      ok = ok && tk.CommaKey("nin")    && tk.IntVal(nin);
      ok = ok && tk.CommaKey("nsat")   && tk.IntVal(nsat);
      ok = ok && tk.CommaKey("nnet")   && tk.IntVal(nnet);
      ok = ok && tk.CommaKey("nbook")  && tk.IntVal(nbook);
      ok = ok && tk.CommaKey("nlegs")  && tk.IntVal(nlegs);
      ok = ok && tk.CommaKey("held")   && tk.IntVal(held);
      ok = ok && tk.CommaKey("ncross") && tk.IntVal(ncross);
      ok = ok && tk.Eat('}');
      if(!ok)
        {
         m_err = "config: " + tk.Err();
         return false;
        }
      if(!(cw == m_blend.CoreWeight()) || nin != BOOKORC_NIN
         || nsat != SATEQ_NSYM || nnet != BOOKORC_NNET
         || nbook != BOOKORC_NBOOK || nlegs != BOOKORC_NLEGS
         || held != BOOKORC_HELD || ncross != BOOKORC_NCROSS)
        {
         m_err = StringFormat("config mismatch (w %.17g vs %.17g, nin %I64d, "
                              "nsat %I64d, nnet %I64d, nbook %I64d, nlegs %I64d, "
                              "held %I64d, ncross %I64d)",
                              cw, m_blend.CoreWeight(), nin, nsat, nnet,
                              nbook, nlegs, held, ncross);
         return false;
        }

      // ---- sleeves ------------------------------------------------------
      ok = tk.CommaKey("sleeves") && tk.Eat('{');
      if(!ok) { m_err = "sleeves: " + tk.Err(); return false; }

      // mag
        {
         SSatMagXauState mg;
         mg.version = 1;
         mg.sleeve  = "mag_xau";
         int nm = 0, np1 = 0, np2 = 0;
         ok = tk.Key("mag") && tk.Eat('{');
         ok = ok && tk.Key("mids") && tk.ArrDVar(mg.mids, nm);
         ok = ok && tk.CommaKey("has_accum_day") && tk.BoolVal(mg.has_accum_day);
         ok = ok && tk.CommaKey("accum_day")     && tk.IntVal(mg.accum_day);
         ok = ok && tk.CommaKey("accum_close")   && tk.NumVal(mg.accum_close);
         ok = ok && tk.CommaKey("pend_ts")  && tk.ArrLVar(mg.pending_ts, np1);
         ok = ok && tk.CommaKey("pend_tgt") && tk.ArrDVar(mg.pending_tgt, np2);
         ok = ok && tk.CommaKey("current")  && tk.NumVal(mg.current);
         ok = ok && tk.Eat('}');
         if(!ok || np1 != np2)
           {
            m_err = "mag: " + (ok ? "pending count mismatch" : tk.Err());
            return false;
           }
         ArrayResize(mg.mids, nm);
         ArrayResize(mg.pending_ts, np1);
         ArrayResize(mg.pending_tgt, np2);
         m_mag.SetState(mg);
        }

      // intraday
        {
         bool hd = false;
         long cd = 0;
         double fl[];
         ok = tk.CommaKey("intraday") && tk.Eat('{');
         ok = ok && tk.Key("has_day") && tk.BoolVal(hd);
         ok = ok && tk.CommaKey("cur_day") && tk.IntVal(cd);
         ok = ok && tk.CommaKey("flat") && tk.ArrD(fl, 26) && tk.Eat('}');
         if(!ok) { m_err = "intraday: " + tk.Err(); return false; }
         SSatIntradaySymState isy[];
         ArrayResize(isy, 2);
         for(int k = 0; k < 2; k++)
           {
            int o = k * 13;
            isy[k].prev_close = fl[o + 0];
            isy[k].vol_num    = fl[o + 1];
            isy[k].vol_den    = fl[o + 2];
            isy[k].vol        = fl[o + 3];
            isy[k].w_vol      = fl[o + 4];
            isy[k].sc_num     = fl[o + 5];
            isy[k].sc_den     = fl[o + 6];
            isy[k].sc_nobs    = (long)fl[o + 7];
            isy[k].c15        = fl[o + 8];
            isy[k].has15      = (fl[o + 9]  != 0.0);
            isy[k].has16      = (fl[o + 10] != 0.0);
            isy[k].mv_pending = fl[o + 11];
            isy[k].sig        = fl[o + 12];
           }
         m_intr.SetState(hd, cd, isy);
        }

      // meanrev
        {
         SSatMeanRevState ms;
         ms.version = 1;
         double par[];
         long cur_day = 0, dcount = 0, dptr = 0, pend_count = 0;
         ok = tk.CommaKey("meanrev") && tk.Eat('{');
         ok = ok && tk.Key("params") && tk.ArrD(par, 14);
         ok = ok && tk.CommaKey("cur_day") && tk.IntVal(cur_day);
         ok = ok && tk.CommaKey("dcount")  && tk.IntVal(dcount);
         ok = ok && tk.CommaKey("dptr")    && tk.IntVal(dptr);
         double cl[], wa[], ow[], db[], sz[], ps[];
         long   nb[], st16[], hd6[];
         ok = ok && tk.CommaKey("close")  && tk.ArrD(cl, SatMR_NSYM);
         ok = ok && tk.CommaKey("wavg")   && tk.ArrD(wa, SatMR_NSYM);
         ok = ok && tk.CommaKey("old_wt") && tk.ArrD(ow, SatMR_NSYM);
         ok = ok && tk.CommaKey("nobs")   && tk.ArrL(nb, SatMR_NSYM);
         ok = ok && tk.CommaKey("dbuf")   && tk.ArrD(db, SatMR_NSYM * SatMR_RING);
         ok = ok && tk.CommaKey("st")     && tk.ArrL(st16, SatMR_NSYM);
         ok = ok && tk.CommaKey("held")   && tk.ArrL(hd6, SatMR_NIDX);
         ok = ok && tk.CommaKey("size")   && tk.ArrD(sz, SatMR_NSYM);
         ok = ok && tk.CommaKey("pos")    && tk.ArrD(ps, SatMR_NSYM);
         ok = ok && tk.CommaKey("pend_count") && tk.IntVal(pend_count);
         if(ok && (pend_count < 0 || pend_count > SatMR_MAX_PEND))
           {
            m_err = "meanrev: pend_count out of range";
            return false;
           }
         long   pe[];
         double pp[];
         ok = ok && tk.CommaKey("pend_eff") && tk.ArrL(pe, (int)pend_count);
         ok = ok && tk.CommaKey("pend_pos")
                 && tk.ArrD(pp, (int)pend_count * SatMR_NSYM);
         ok = ok && tk.Eat('}');
         if(!ok) { m_err = "meanrev: " + tk.Err(); return false; }
         ms.L         = (int)par[0];
         ms.z_in      = par[1];
         ms.z_out     = par[2];
         ms.D         = (int)par[3];
         ms.z_entry   = par[4];
         ms.K         = par[5];
         ms.z_exit    = par[6];
         ms.trend_L   = (int)par[7];
         ms.max_hold  = (int)par[8];
         ms.exec_lag  = (int)par[9];
         ms.vol_floor = par[10];
         ms.pos_cap   = par[11];
         ms.gross_cap = par[12];
         ms.vol_span  = (int)par[13];
         ms.cur_day   = cur_day;
         ms.dcount    = (int)dcount;
         ms.dptr      = (int)dptr;
         for(int i = 0; i < SatMR_NSYM; i++)
           {
            ms.close[i]  = cl[i];
            ms.wavg[i]   = wa[i];
            ms.old_wt[i] = ow[i];
            ms.nobs[i]   = nb[i];
            for(int j = 0; j < SatMR_RING; j++)
               ms.dbuf[i][j] = db[i * SatMR_RING + j];
            ms.st[i]   = (int)st16[i];
            ms.size[i] = sz[i];
            ms.pos[i]  = ps[i];
           }
         for(int i = 0; i < SatMR_NIDX; i++)
            ms.held[i] = (int)hd6[i];
         ms.pend_count = (int)pend_count;
         for(int k = 0; k < (int)pend_count; k++)
           {
            ms.pend_eff[k] = (datetime)pe[k];
            for(int i = 0; i < SatMR_NSYM; i++)
               ms.pend_pos[k][i] = pp[k * SatMR_NSYM + i];
           }
         m_mr.SetState(ms);
        }

      // crisis
        {
         double cst[];
         ok = tk.CommaKey("crisis") && tk.ArrD(cst, SatCRISIS_STATE_SIZE);
         if(!ok) { m_err = "crisis: " + tk.Err(); return false; }
         if(!m_crisis.SetState(cst))
           {
            m_err = "crisis: SetState rejected";
            return false;
           }
        }

      // JSON-string components
        {
         string js;
         if(!tk.CommaKey("seasonal_crypto") || !tk.ObjRaw(js))
           { m_err = "seasonal_crypto: " + tk.Err(); return false; }
         if(!m_sc.SetState(js))
           { m_err = "seasonal_crypto: SetState rejected"; return false; }
         if(!tk.CommaKey("carry_breakout") || !tk.ObjRaw(js))
           { m_err = "carry_breakout: " + tk.Err(); return false; }
         if(!m_cb.SetState(js))
           { m_err = "carry_breakout: SetState rejected"; return false; }
         if(!tk.CommaKey("trend_v2") || !tk.ObjRaw(js))
           { m_err = "trend_v2: " + tk.Err(); return false; }
         if(!m_tv.SetState(js))
           { m_err = "trend_v2: SetState rejected"; return false; }
         // ensemble: config-only — verify identity with the live shell
         string ens;
         if(!tk.CommaKey("ensemble") || !tk.StrVal(ens))
           { m_err = "ensemble: " + tk.Err(); return false; }
         if(ens != m_shell.GetState())
           { m_err = "ensemble config mismatch (stored != live shell)"; return false; }
         if(!tk.Eat('}'))
           { m_err = "sleeves close: " + tk.Err(); return false; }
        }

      // ---- b engine -------------------------------------------------
        {
         string js;
         if(!tk.CommaKey("b_engine") || !tk.ObjRaw(js))
           { m_err = "b_engine: " + tk.Err(); return false; }
         if(!m_beng.SetState(js))
           { m_err = "b_engine: SetState rejected"; return false; }
        }

      // ---- core -------------------------------------------------------
        {
         long n_segs = 0, fc_cursor = 0, fn = 0;
         double seed = 0.0;
         bool seg_open = false, core_done = false;
         ok = tk.CommaKey("core") && tk.Eat('{');
         ok = ok && tk.Key("n_segs") && tk.IntVal(n_segs);
         ok = ok && tk.CommaKey("seed") && tk.NumVal(seed);
         ok = ok && tk.CommaKey("seg_open")  && tk.BoolVal(seg_open);
         ok = ok && tk.CommaKey("core_done") && tk.BoolVal(core_done);
         ok = ok && tk.CommaKey("fc_cursor") && tk.IntVal(fc_cursor);
         long   cvl[];
         double cps[], cmd[], cqe[];
         ok = ok && tk.CommaKey("carry_valid") && tk.ArrL(cvl, BOOKORC_NLEGS);
         ok = ok && tk.CommaKey("carry_pos")   && tk.ArrD(cps, BOOKORC_NLEGS);
         ok = ok && tk.CommaKey("carry_mid")   && tk.ArrD(cmd, BOOKORC_NLEGS);
         ok = ok && tk.CommaKey("carry_qe")    && tk.ArrD(cqe, BOOKORC_NLEGS);
         ok = ok && tk.CommaKey("fcore_n")     && tk.IntVal(fn);
         if(!ok) { m_err = "core: " + tk.Err(); return false; }
         if(seg_open)
           {
            m_err = "core: state saved inside an open segment (unsupported)";
            return false;
           }
         if(fn < 0 || fc_cursor < 0 || fc_cursor > fn)
           {
            m_err = "core: fc_cursor/fcore_n inconsistent";
            return false;
           }
         long   fts[];
         double fv[];
         ok = tk.CommaKey("fcore_ts") && tk.ArrL(fts, (int)fn);
         ok = ok && tk.CommaKey("fcore_v")
                 && tk.ArrD(fv, (int)fn * BOOKORC_NNET);
         ok = ok && tk.Eat('}');
         if(!ok) { m_err = "core arrays: " + tk.Err(); return false; }
         for(int l = 0; l < BOOKORC_NLEGS; l++)
            if(!m_core.SetCarry(l, cvl[l] != 0, cps[l], cmd[l], cqe[l]))
              {
               m_err = "core: " + m_core.LastError();
               return false;
              }
         if(!m_core.RestoreFCoreRows(fts, fv, (int)fn))
           {
            m_err = "core: " + m_core.LastError();
            return false;
           }
         m_n_segs    = (int)n_segs;
         m_seed      = seed;
         m_seg_open  = false;
         m_core_done = core_done;
         m_fc_cursor = (int)fc_cursor;
        }

      // ---- glue ---------------------------------------------------------
        {
         ok = tk.CommaKey("glue") && tk.Eat('{');
         ok = ok && tk.Key("ffill") && tk.ArrD(m_ffill, BOOKORC_NIN);
         ok = ok && tk.CommaKey("has_day") && tk.BoolVal(m_has_day);
         long cd = 0;
         ok = ok && tk.CommaKey("cur_day") && tk.IntVal(cd);
         long ntv = 0, ncr = 0;
         ok = ok && tk.CommaKey("tvq_n") && tk.IntVal(ntv);
         ok = ok && tk.CommaKey("tvq_eff") && tk.ArrL(m_tvq_eff, (int)ntv);
         ok = ok && tk.CommaKey("tvq_w")
                 && tk.ArrD(m_tvq_w, (int)ntv * SatTV2_NSYM);
         ok = ok && tk.CommaKey("crq_n") && tk.IntVal(ncr);
         ok = ok && tk.CommaKey("crq_eff") && tk.ArrL(m_crq_eff, (int)ncr);
         ok = ok && tk.CommaKey("crq_w")
                 && tk.ArrD(m_crq_w, (int)ncr * SatCRISIS_NOUT);
         ok = ok && tk.CommaKey("trend_cur")  && tk.ArrD(m_trend_cur, SatTV2_NSYM);
         ok = ok && tk.CommaKey("crisis_cur") && tk.ArrD(m_crisis_cur, SatCRISIS_NOUT);
         ok = ok && tk.CommaKey("have_prev") && tk.BoolVal(m_have_prev);
         long pts = 0;
         ok = ok && tk.CommaKey("prev_ts") && tk.IntVal(pts);
         ok = ok && tk.CommaKey("prev_mr")  && tk.ArrD(m_prev_mr, SatMR_NSYM);
         ok = ok && tk.CommaKey("prev_cbk") && tk.ArrD(m_prev_cbk, BOOKORC_NKEEP);
         ok = ok && tk.CommaKey("prev_id")  && tk.ArrD(m_prev_id, 2);
         ok = ok && tk.CommaKey("prev_cr")  && tk.ArrD(m_prev_cr, SatCRISIS_NOUT);
         ok = ok && tk.CommaKey("prev_tv")  && tk.ArrD(m_prev_tv, SatTV2_NSYM);
         ok = ok && tk.CommaKey("prev_mg")  && tk.ArrD(m_prev_mg, 1);
         long h1b = 0, h1l = 0, m1l = 0, m1b = 0, hn = 0;
         ok = ok && tk.CommaKey("h1_bars")    && tk.IntVal(h1b);
         ok = ok && tk.CommaKey("h1_last_ts") && tk.IntVal(h1l);
         ok = ok && tk.CommaKey("finalized")  && tk.BoolVal(m_finalized);
         ok = ok && tk.CommaKey("m1_last_ts") && tk.IntVal(m1l);
         ok = ok && tk.CommaKey("m1_bars")    && tk.IntVal(m1b);
         ok = ok && tk.CommaKey("b_eqc") && tk.NumVal(m_b_eqc);
         ok = ok && tk.CommaKey("b_eqw") && tk.NumVal(m_b_eqw);
         ok = ok && tk.CommaKey("held_n") && tk.IntVal(hn);
         ok = ok && tk.CommaKey("held_ts") && tk.ArrL(m_held_ts, BOOKORC_HELD);
         double hr[];
         ok = ok && tk.CommaKey("held_rows")
                 && tk.ArrD(hr, BOOKORC_HELD * SATEQ_NSYM);
         long ler = 0, trw = 0, thr = 0, tse = 0;
         ok = ok && tk.CommaKey("last_emit_hour")  && tk.IntVal(ler);
         ok = ok && tk.CommaKey("total_rows")      && tk.IntVal(trw);
         ok = ok && tk.CommaKey("total_hours")     && tk.IntVal(thr);
         ok = ok && tk.CommaKey("total_sentinels") && tk.IntVal(tse);
         ok = ok && tk.CommaKey("last_ah") && tk.NumVal(m_last_ah);
         ok = ok && tk.CommaKey("last_bh") && tk.NumVal(m_last_bh);
         ok = ok && tk.Eat('}');
         if(!ok) { m_err = "glue: " + tk.Err(); return false; }
         m_cur_day    = cd;
         m_prev_ts    = pts;
         m_h1_bars    = h1b;
         m_h1_last_ts = h1l;
         m_m1_last_ts = m1l;
         m_m1_bars    = m1b;
         m_held_n     = (int)hn;
         for(int i = 0; i < BOOKORC_HELD; i++)
            for(int k = 0; k < SATEQ_NSYM; k++)
               m_held_row[i][k] = hr[i * SATEQ_NSYM + k];
         m_last_emit_hour  = ler;
         m_total_rows      = trw;
         m_total_hours     = thr;
         m_total_sentinels = tse;
        }

      // ---- samplers -------------------------------------------------------
      ok = tk.CommaKey("samplers") && tk.Eat('{') && tk.Key("a");
      if(!ok) { m_err = "samplers: " + tk.Err(); return false; }
      if(!BsReadSampler(tk, m_aS, "a"))
         return false;
      if(!tk.CommaKey("b"))
        { m_err = "samplers: " + tk.Err(); return false; }
      if(!BsReadSampler(tk, m_bS, "b"))
         return false;
      if(!tk.Eat('}'))
        { m_err = "samplers close: " + tk.Err(); return false; }

      // per-call transients
      m_emit_n = 0;
      m_err = "";
      return true;
     }

   //---------------------------------------------------------------//
   // BsContinuity — the ratio-chain anchor snapshot: recomputable    //
   // identically from a restored state (the CBookState j-splice      //
   // guard compares save-time vs restore-time values).               //
   //---------------------------------------------------------------//
   bool              BsContinuity(SBookStateContinuity &c)
     {
      if(!m_ready)
        {
         m_err = "not initialized";
         return false;
        }
      c.have   = (m_total_hours > 0);
      c.j_hour = c.have ? m_last_emit_hour : -1;
      c.a_h    = c.have ? AH(m_last_emit_hour) : 1.0;
      c.b_h    = c.have ? BH(m_last_emit_hour) : 1.0;
      c.w      = m_blend.CoreWeight();
      c.j      = c.w * c.a_h + (1.0 - c.w) * c.b_h;
      c.a_first = AFirst();
      c.b_first = BFirst();
      return true;
     }
  };

#endif // BOOK_BOOKORCHESTRATOR_MQH
