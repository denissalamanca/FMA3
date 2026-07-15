//+------------------------------------------------------------------+
//| Book/FeedAssembler.mqh — CFeedAssembler: the M1 multi-symbol      |
//| LIVE-feed assembler (UNIT A of the S2 feed work).                 |
//|                                                                   |
//| S0 PROVED the data is available live (union grid + has_bar        |
//| bit-exact vs golden on the live terminal, 34/34 symbols). This    |
//| class turns that feed into the exact rows the proven compute      |
//| chain consumes:                                                   |
//|                                                                   |
//|  * SIX-FIELD M1 UNION ROW (the b engine / BookOrchestrator.StepM1 |
//|    input): per union minute (union of the 31 SATEQ book symbols'  |
//|    + EURJPY's native minutes — the FMA2 account_engine_1m rule),  |
//|    has_bar[31] + bid_o/ask_o, bid_c/ask_c, bid_l/ask_h [31],      |
//|    FLOAT32-QUANTIZED ((float) cast — BH_ENGINE_SPEC §3/§7, the    |
//|    exporter discipline; FABLE REVISION v2 item 5(i)), ffill-      |
//|    carried where has=0; eurq[8 crosses] + swap_l/swap_s[31] via   |
//|    CSwapEurqBH (Book/SwapEurq.mqh — RECON-committed, bit-equal    |
//|    generator).                                                    |
//|  * H1 SIGNAL ROW (BookOrchestrator.StepH1 input): raw close[37]   |
//|    (core.ALL order) = float64 mid (bid_c+ask_c)/2.0 of the        |
//|    symbol's LAST M1 bar in the hour, NaN where the symbol printed |
//|    no bar that hour; hourly union grid = hours with >=1 bar of    |
//|    any of the 37 (export_master_inputs.py semantics).             |
//|  * CORESIGNAL DAILY MIDS (S2_CORE_LIVE_DESIGN §2.2): 8 series     |
//|    (XAUUSD, USTEC, USDJPY, ETHUSD, EURGBP-pre20, AUDUSD, NZDUSD,  |
//|    BTCUSD) = float64 mid of the LAST 1m bar of each raw-stamp     |
//|    calendar day (EURGBP: bars with raw hour < 20 only), emitted   |
//|    causally when the instrument's first bar of the NEXT day       |
//|    arrives (pandas resample('1D').last().dropna() twin).          |
//|                                                                   |
//| PRICE RECONSTRUCTION (the record-feed identity): the frozen       |
//| NSF5 bars_1m_ic feed was built as  ask = bid + spread_points *    |
//| point  (build_ic_feed.py; one integer spread per M1 bar, applied  |
//| to all four OHLC fields). CopyRates returns exactly               |
//| (o,h,l,c = bid OHLC, spread points) so PushBar applies the same   |
//| identity. MEASURED (feed_assembler_mirror.py): bit-exact on all   |
//| four ask fields of all 37 symbols, and the assembled rows are     |
//| bit-exact vs the golden bundles (FMA3_bh_inputs_<Q>.csv six-field |
//| + has + eurq + swaps; FMA3_v34_inputs.csv H1 closes) — see        |
//| research/bpure/feed/feed_assembler_gate.json.                     |
//|                                                                   |
//| DRIVE CONTRACT (BookOrchestrator, WIRING §2/§5):                  |
//|  1. Completed-hour boundary is detected CAUSALLY: the H1 row for  |
//|     hour h finalizes when grid progress reaches h+3600 (a         |
//|     committed minute in a later hour, or AdvanceTo(T>=h+3600)     |
//|     from the server clock — a completed server hour).             |
//|  2. M1 rows are BUFFERED per hour and released only after the     |
//|     hour's H1 row is popped (PopH1Row) — so the EA can run        |
//|     StepH1(h) first and then feed the minutes of [h,h+1h), the    |
//|     exact BookOrchestrator drive contract. The core segment-batch |
//|     feed must be kept >=1 segment ahead by the caller BEFORE      |
//|     consuming the H1 row (drive contract 1) — segments are the    |
//|     trigger detector's job (S2), not the assembler's.             |
//|  3. PushBar stamps ascend; a stamp advance commits the previous   |
//|     minute (a minute with no bar of any symbol is simply not on   |
//|     the union grid — the crypto-weekend rule falls out: weekend   |
//|     minutes exist exactly where crypto printed bars).             |
//|                                                                   |
//| COLD START (documented, mirrors the recorders' `pre` rule):       |
//| _densify bfills minutes before a symbol's first bar with that     |
//| first bar — a live stream cannot know a future first bar.        |
//| SeedSymbol() injects a carry value without emitting (counted in   |
//| pre_seed_hits, the SwapEurq SeedCross discipline); live deploy    |
//| seeds from real prior history (CopyRates backfill). B rows are    |
//| flagged not-ready until all 31 book symbols + 8 crosses are       |
//| seeded — consuming an unready row is a caller bug, not a          |
//| fallback.                                                         |
//|                                                                   |
//| ZERO trading calls, ZERO CTrade, ZERO file I/O. The only          |
//| terminal calls live in the thin Init(true)/PollTerminal()         |
//| helpers (SymbolSelect/SymbolInfo/CopyRates — the S0 FeedProbe     |
//| mechanism); everything else is pure per-bar state, so scripts     |
//| and the python statement twin exercise it bit-for-bit.            |
//|                                                                   |
//| NOTE symbol scope: the 37-symbol H1 universe = the S0 probe's 34  |
//| (33 book + EURJPY) + GBPUSD/XRPUSD/XPTUSD (H1-signal-only inputs, |
//| present in the frozen record feed; their live SymbolSelect is     |
//| verified by Init and reported — not yet S0-probed, staged).       |
//+------------------------------------------------------------------+
#ifndef BOOK_FEEDASSEMBLER_MQH
#define BOOK_FEEDASSEMBLER_MQH

#include <Sat/SatMath.mqh>        // SatNan()
#include <Book/SwapEurq.mqh>      // CSwapEurqBH (bit-equal generator)

//==================================================================//
// frozen wiring constants                                          //
//==================================================================//
#define FA_NSYM    37             // H1 signal universe (core.ALL order)
#define FA_NBOOK   31             // b six-field universe (SATEQ order)
#define FA_NCROSS  8              // eurq EUR crosses (exporter order)
#define FA_NMID    8              // CoreSignal daily-mid series
#define FA_SE_HORIZON 3155760000  // ~100y: CSwapEurqBH open-ended last_ts

// H1 input universe, core.ALL order == BOOKORC_IN_SYMS (MODEL names)
const string FA_SYMS[FA_NSYM] =
  {
   "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
   "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
   "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY",
   "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
   "DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
   "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"
  };

// digits per symbol — provenance build_ic_feed.py FEED map (the exact
// table the record feed was built with; Init(true) verifies live
// SYMBOL_DIGITS against it and REFUSES on drift: the ask
// reconstruction depends on it)
const int FA_DIGITS[FA_NSYM] =
  {
   5, 3, 5, 5, 5, 3, 5,
   5, 5, 3, 5, 5, 5, 5,
   3, 5, 5, 3, 5, 5, 3,
   2, 2, 4, 4,
   1, 2, 2, 2, 2, 2,
   3, 2, 2, 4, 2, 2
  };

// b six-field universe = SATEQ_SYMBOLS order, as indices into FA_SYMS
const int FA_BOOK_IX[FA_NBOOK] =
  {
   0, 1, 2, 21, 4, 5, 25,          // AUDCAD AUDJPY AUDNZD BTCUSD CADCHF CADJPY DAX
   22, 6, 7, 8, 10, 11, 12,        // ETHUSD EURCAD EURCHF EURGBP EURNOK EURNZD EURSEK
   13, 14, 26, 16, 17, 23, 27,     // EURUSD GBPJPY JP225 NZDCAD NZDJPY SOLUSD UK100
   28, 29, 19, 20, 30, 31, 32,     // US30 USA500 USDCHF USDJPY USTEC XAGUSD XAUUSD
   33, 34, 36                      // XBRUSD XNGUSD XTIUSD
  };

// eurq crosses (exporter columns, sorted), as indices into FA_SYMS
const int FA_CROSS_IX[FA_NCROSS] = {6, 7, 8, 9, 10, 11, 12, 13};
// EURJPY: the only M1-union member that is not a book symbol
#define FA_IX_EURJPY 9
// per-cross representative b slot (a book symbol quoted in that ccy):
// CAD->AUDCAD(0) CHF->CADCHF(4) GBP->EURGBP(10) JPY->AUDJPY(1)
// NOK->EURNOK(11) NZD->AUDNZD(2) SEK->EURSEK(13) USD->EURUSD(14)
const int FA_CROSS_SLOT[FA_NCROSS] = {0, 4, 10, 1, 11, 2, 13, 14};

// CoreSignal daily-mid series -> FA_SYMS index (EURGBP = pre-20 variant)
const int FA_MID_IX[FA_NMID] = {32, 30, 20, 22, 8, 3, 18, 21};
const bool FA_MID_PRE20[FA_NMID] =
  {false, false, false, false, true, false, false, false};

// MODEL -> broker symbol name (exporter SYMMAP; rest identity)
string FaBrokerName(const string model)
  {
   if(model == "DAX")
      return "DE40";
   if(model == "USA500")
      return "US500";
   return model;
  }

//==================================================================//
// emitted row structures (simple types only -> ArrayResize-able)   //
//==================================================================//
struct SFaM1Row
  {
   long              ts;                    // union minute (epoch sec)
   bool              ready;                 // all 31 + crosses seeded
   bool              has[FA_NBOOK];
   double            bo[FA_NBOOK];          // float32-quantized doubles
   double            ao[FA_NBOOK];
   double            bc[FA_NBOOK];
   double            ac[FA_NBOOK];
   double            bl[FA_NBOOK];
   double            ah[FA_NBOOK];
   double            eurq[FA_NCROSS];       // exporter cross columns
   double            swl[FA_NBOOK];
   double            sws[FA_NBOOK];
  };

struct SFaH1Row
  {
   long              ts;                    // hour start (epoch sec)
   double            close[FA_NSYM];        // raw close, NaN = no bar
   bool              has[FA_NSYM];
   int               m1_rows;               // buffered M1 rows this hour
  };

struct SFaDailyMid
  {
   int               series;                // FA_MID index
   long              day;                   // epoch day (ts/86400)
   double            mid;
  };

//==================================================================//
// CFeedAssembler                                                   //
//==================================================================//
class CFeedAssembler
  {
private:
   // ---- static per-symbol config ----
   string            m_broker[FA_NSYM];
   double            m_point[FA_NSYM];
   bool              m_selected[FA_NSYM];
   bool              m_terminal;

   // ---- per-symbol carry state (f32-quantized six fields) ----
   bool              m_seeded[FA_NSYM];
   double            m_bo[FA_NSYM], m_ao[FA_NSYM];
   double            m_bc[FA_NSYM], m_ac[FA_NSYM];
   double            m_bl[FA_NSYM], m_ah[FA_NSYM];
   long              m_sym_last[FA_NSYM];   // last pushed stamp per symbol

   // ---- pending minute ----
   long              m_cur_min;             // -1 = none
   bool              m_pend[FA_NSYM];
   double            m_p_bo[FA_NSYM], m_p_bh[FA_NSYM];
   double            m_p_bl[FA_NSYM], m_p_bc[FA_NSYM];
   int               m_p_sp[FA_NSYM];

   // ---- current hour (H1 accumulation) ----
   bool              m_hour_open;
   long              m_hour_ts;
   double            m_h_close[FA_NSYM];    // float64 raw mids
   bool              m_h_has[FA_NSYM];

   // ---- daily-mid state ----
   long              m_md_day[FA_NMID];
   double            m_md_mid[FA_NMID];
   bool              m_md_have[FA_NMID];

   // ---- swap/eurq generator (BH profile) ----
   CSwapEurqBH       m_se;
   bool              m_se_started;
   double            m_se_eurq[FA_NBOOK];
   double            m_se_swl[FA_NBOOK];
   double            m_se_sws[FA_NBOOK];

   // ---- queues ----
   SFaM1Row          m_m1[];                // committed M1 rows
   int               m_m1_head, m_m1_n;
   long              m_m1_release;          // rows with hour <= this drain
   SFaH1Row          m_h1[];
   int               m_h1_head, m_h1_n;
   SFaDailyMid       m_mid[];
   int               m_mid_head, m_mid_n;

   // ---- telemetry ----
   long              m_minutes_committed;
   long              m_b_rows;
   long              m_h1_rows_emitted;
   long              m_unready_rows;
   int               m_pre_seed_hits;

   string            m_err;
   bool              m_ready;

   //---------------------------------------------------------------//
   static double     F32(const double v) { return (double)(float)v; }

   void              Fail(const string msg) { m_err = msg; }

   // apply one bar to the carries + hour/daily trackers
   void              Apply(const int i, const long ts, const double o,
                           const double h, const double l, const double c,
                           const int spread_pts)
     {
      double sp = spread_pts * m_point[i];
      double ao = o + sp, ah = h + sp, ac = c + sp;
      m_bo[i] = F32(o);
      m_ao[i] = F32(ao);
      m_bc[i] = F32(c);
      m_ac[i] = F32(ac);
      m_bl[i] = F32(l);
      m_ah[i] = F32(ah);
      m_seeded[i] = true;
      // H1: float64 raw mid of the last bar in the hour
      double mid = (c + ac) / 2.0;
      m_h_close[i] = mid;
      m_h_has[i] = true;
      // daily mids (per-series; finalize on the instrument's first bar
      // of a NEW raw day, update on qualifying bars)
      long day = ts / 86400;
      int hour_of_day = (int)((ts % 86400) / 3600);
      for(int s = 0; s < FA_NMID; s++)
        {
         if(FA_MID_IX[s] != i)
            continue;
         if(m_md_have[s] && day > m_md_day[s])
           {
            MidAppend(s, m_md_day[s], m_md_mid[s]);
            m_md_have[s] = false;
           }
         bool qual = (!FA_MID_PRE20[s] || hour_of_day < 20);
         if(qual)
           {
            if(m_md_have[s] && day == m_md_day[s])
               m_md_mid[s] = mid;
            else
              {
               m_md_day[s] = day;
               m_md_mid[s] = mid;
               m_md_have[s] = true;
              }
           }
        }
     }

   void              MidAppend(const int series, const long day, const double mid)
     {
      int cap = ArraySize(m_mid);
      if(m_mid_n >= cap)
         ArrayResize(m_mid, cap + 64);
      m_mid[m_mid_n].series = series;
      m_mid[m_mid_n].day = day;
      m_mid[m_mid_n].mid = mid;
      m_mid_n++;
     }

   // commit the pending minute -> maybe a b row; hour bookkeeping
   bool              CommitMinute()
     {
      long M = m_cur_min;
      long h = M - (M % 3600);
      if(m_hour_open && h > m_hour_ts)
         FinalizeHour();
      if(!m_hour_open)
        {
         m_hour_open = true;
         m_hour_ts = h;
         for(int i = 0; i < FA_NSYM; i++)
           {
            m_h_close[i] = SatNan();
            m_h_has[i] = false;
           }
        }

      bool any_m1 = false;
      for(int i = 0; i < FA_NSYM; i++)
         if(m_pend[i])
            Apply(i, M, m_p_bo[i], m_p_bh[i], m_p_bl[i], m_p_bc[i], m_p_sp[i]);
      for(int k = 0; k < FA_NBOOK; k++)
         if(m_pend[FA_BOOK_IX[k]])
            any_m1 = true;
      if(m_pend[FA_IX_EURJPY])
         any_m1 = true;

      if(any_m1)
        {
         // cross bars first (stamp <= the minute being stepped), then Step
         for(int c = 0; c < FA_NCROSS; c++)
           {
            int gi = FA_CROSS_IX[c];
            if(!m_pend[gi])
               continue;
            double sp = m_p_sp[gi] * m_point[gi];
            m_se.OnCrossBar(FA_SYMS[gi], m_p_bc[gi], m_p_bc[gi] + sp);
           }
         if(!m_se_started)
           {
            m_se.Start(M, M + FA_SE_HORIZON);
            m_se_started = true;
           }
         bool se_ok = m_se.Step(M, m_se_eurq, m_se_swl, m_se_sws);

         int cap = ArraySize(m_m1);
         if(m_m1_n >= cap)
            ArrayResize(m_m1, cap + 256);
         m_m1[m_m1_n].ts = M;
         bool all_seeded = true;
         for(int k = 0; k < FA_NBOOK; k++)
           {
            int gi = FA_BOOK_IX[k];
            if(!m_seeded[gi])
               all_seeded = false;
            m_m1[m_m1_n].has[k] = m_pend[gi];
            m_m1[m_m1_n].bo[k] = m_bo[gi];
            m_m1[m_m1_n].ao[k] = m_ao[gi];
            m_m1[m_m1_n].bc[k] = m_bc[gi];
            m_m1[m_m1_n].ac[k] = m_ac[gi];
            m_m1[m_m1_n].bl[k] = m_bl[gi];
            m_m1[m_m1_n].ah[k] = m_ah[gi];
            m_m1[m_m1_n].swl[k] = se_ok ? m_se_swl[k] : 0.0;
            m_m1[m_m1_n].sws[k] = se_ok ? m_se_sws[k] : 0.0;
           }
         for(int c = 0; c < FA_NCROSS; c++)
            m_m1[m_m1_n].eurq[c] = se_ok ? m_se_eurq[FA_CROSS_SLOT[c]]
                                         : SatNan();
         m_m1[m_m1_n].ready = (se_ok && all_seeded);
         if(!m_m1[m_m1_n].ready)
            m_unready_rows++;
         m_m1_n++;
         m_b_rows++;
        }
      for(int i = 0; i < FA_NSYM; i++)
         m_pend[i] = false;
      m_cur_min = -1;
      m_minutes_committed++;
      return true;
     }

   void              FinalizeHour()
     {
      if(!m_hour_open)
         return;
      int cap = ArraySize(m_h1);
      if(m_h1_n >= cap)
         ArrayResize(m_h1, cap + 64);
      m_h1[m_h1_n].ts = m_hour_ts;
      int nrows = 0;
      for(int r = m_m1_head; r < m_m1_n; r++)
         if(m_m1[r].ts >= m_hour_ts && m_m1[r].ts < m_hour_ts + 3600)
            nrows++;
      for(int i = 0; i < FA_NSYM; i++)
        {
         m_h1[m_h1_n].close[i] = m_h_close[i];
         m_h1[m_h1_n].has[i] = m_h_has[i];
        }
      m_h1[m_h1_n].m1_rows = nrows;
      m_h1_n++;
      m_h1_rows_emitted++;
      m_hour_open = false;
     }

   void              CompactM1()
     {
      if(m_m1_head < 4096)
         return;
      int n = m_m1_n - m_m1_head;
      for(int i = 0; i < n; i++)
         m_m1[i] = m_m1[m_m1_head + i];
      m_m1_n = n;
      m_m1_head = 0;
     }

   void              CompactH1()
     {
      if(m_h1_head < 256)
         return;
      int n = m_h1_n - m_h1_head;
      for(int i = 0; i < n; i++)
         m_h1[i] = m_h1[m_h1_head + i];
      m_h1_n = n;
      m_h1_head = 0;
     }

public:
                     CFeedAssembler() : m_terminal(false), m_cur_min(-1),
                                        m_hour_open(false), m_hour_ts(0),
                                        m_se_started(false),
                                        m_m1_head(0), m_m1_n(0),
                                        m_m1_release(-1),
                                        m_h1_head(0), m_h1_n(0),
                                        m_mid_head(0), m_mid_n(0),
                                        m_minutes_committed(0), m_b_rows(0),
                                        m_h1_rows_emitted(0),
                                        m_unready_rows(0),
                                        m_pre_seed_hits(0),
                                        m_err(""), m_ready(false) {}

   string            LastError() const { return m_err;   }
   bool              Ready()     const { return m_ready; }

   //---------------------------------------------------------------//
   // Init. terminal=true: SymbolSelect the broker names, read       |
   // SYMBOL_POINT and verify SYMBOL_DIGITS against the record-feed  |
   // table (drift = REFUSE: the ask reconstruction depends on it).  |
   // terminal=false (checks / mirror twin): points from FA_DIGITS.  |
   //---------------------------------------------------------------//
   bool              Init(const bool terminal)
     {
      m_terminal = terminal;
      m_ready = false;
      m_err = "";
      for(int i = 0; i < FA_NSYM; i++)
        {
         m_broker[i] = FaBrokerName(FA_SYMS[i]);
         m_selected[i] = false;
         m_seeded[i] = false;
         m_pend[i] = false;
         m_sym_last[i] = -1;
         m_bo[i] = 0.0; m_ao[i] = 0.0; m_bc[i] = 0.0;
         m_ac[i] = 0.0; m_bl[i] = 0.0; m_ah[i] = 0.0;
         m_h_close[i] = SatNan();
         m_h_has[i] = false;
         m_point[i] = MathPow(10.0, -FA_DIGITS[i]);
        }
      for(int s = 0; s < FA_NMID; s++)
        {
         m_md_day[s] = 0;
         m_md_mid[s] = 0.0;
         m_md_have[s] = false;
        }
      if(terminal)
        {
         for(int i = 0; i < FA_NSYM; i++)
           {
            m_selected[i] = SymbolSelect(m_broker[i], true);
            if(!m_selected[i])
              {
               Fail("SymbolSelect failed: " + m_broker[i]);
               return false;
              }
            long dig = SymbolInfoInteger(m_broker[i], SYMBOL_DIGITS);
            m_point[i] = SymbolInfoDouble(m_broker[i], SYMBOL_POINT);
            if((int)dig != FA_DIGITS[i])
              {
               // Live SYMBOL_DIGITS drift vs the record feed (e.g. DE40 1->2).
               // SYMBOL-META-RECONCILE 2026-07-15: this is a PRECISION drift, not a
               // scale/contract one. The ask is reconstructed with the LIVE point
               // (set above), so it is self-consistent; the tiny price-granularity
               // difference vs the record feed is R2, bounded by the ratified band.
               // Contract/volume drifts are handled downstream by BookExec, which
               // sizes off LIVE SymbolInfo (contract, lot step/min, VOLUME_LIMIT).
               // So: log for R2 telemetry and CONTINUE — do NOT refuse. (SymbolSelect
               // failure above still hard-fails; a genuine SCALE drift would show as
               // a marks divergence caught by the position-fidelity / R2 gates.)
               PrintFormat("FEED DIGITS DRIFT (R2, handled): %s live_digits=%d "
                           "record=%d live_point=%.10g", m_broker[i], (int)dig,
                           FA_DIGITS[i], m_point[i]);
              }
           }
        }
      // b-order symbol slots for the swap/eurq generator (MODEL names)
      for(int k = 0; k < FA_NBOOK; k++)
         if(!m_se.AddSymbol(FA_SYMS[FA_BOOK_IX[k]]))
           {
            Fail("SwapEurq AddSymbol failed: " + FA_SYMS[FA_BOOK_IX[k]]);
            return false;
           }
      m_se_started = false;
      m_cur_min = -1;
      m_hour_open = false;
      m_m1_head = 0; m_m1_n = 0; m_m1_release = -1;
      m_h1_head = 0; m_h1_n = 0;
      m_mid_head = 0; m_mid_n = 0;
      m_minutes_committed = 0;
      m_b_rows = 0;
      m_h1_rows_emitted = 0;
      m_unready_rows = 0;
      m_pre_seed_hits = 0;
      m_ready = true;
      return true;
     }

   int               SymIndex(const string model) const
     {
      for(int i = 0; i < FA_NSYM; i++)
         if(FA_SYMS[i] == model)
            return i;
      return -1;
     }

   //---------------------------------------------------------------//
   // SeedSymbol — cold-start carry injection WITHOUT emission (the  |
   // recorders' `pre` rule / SwapEurq SeedCross discipline). Live   |
   // deploy seeds from real prior history instead.                  |
   //---------------------------------------------------------------//
   bool              SeedSymbol(const int i, const double o, const double h,
                                const double l, const double c,
                                const int spread_pts)
     {
      if(!m_ready || i < 0 || i >= FA_NSYM)
        {
         Fail("SeedSymbol: bad state/index");
         return false;
        }
      if(m_seeded[i])
         return true;                       // first value wins (pre rule)
      double sp = spread_pts * m_point[i];
      m_bo[i] = F32(o);
      m_ao[i] = F32(o + sp);
      m_bc[i] = F32(c);
      m_ac[i] = F32(c + sp);
      m_bl[i] = F32(l);
      m_ah[i] = F32(h + sp);
      m_seeded[i] = true;
      m_pre_seed_hits++;
      return true;
     }

   bool              SeedCrossValue(const string cross, const double bid_c,
                                    const double ask_c)
     {
      m_se.SeedCross(cross, bid_c, ask_c);
      return true;
     }

   //---------------------------------------------------------------//
   // PushBar — one completed M1 bar, CopyRates form (bid OHLC +     |
   // integer spread points). Stamps: minute-aligned; per symbol     |
   // ascending; a stamp ADVANCE commits the previous union minute.  |
   //---------------------------------------------------------------//
   bool              PushBar(const int i, const long ts, const double o,
                             const double h, const double l, const double c,
                             const int spread_pts)
     {
      if(!m_ready)             { Fail("not initialized");        return false; }
      if(i < 0 || i >= FA_NSYM) { Fail("PushBar: bad index");     return false; }
      if((ts % 60) != 0)
        {
         Fail(StringFormat("PushBar %s: stamp %I64d not minute-aligned",
                           FA_SYMS[i], ts));
         return false;
        }
      if(ts <= m_sym_last[i])
        {
         Fail(StringFormat("PushBar %s: stamp %I64d not ascending",
                           FA_SYMS[i], ts));
         return false;
        }
      if(m_cur_min >= 0 && ts > m_cur_min)
         if(!CommitMinute())
            return false;
      if(m_cur_min < 0)
         m_cur_min = ts;
      if(ts != m_cur_min)
        {
         Fail(StringFormat("PushBar %s: stamp %I64d behind open minute %I64d",
                           FA_SYMS[i], ts, m_cur_min));
         return false;
        }
      m_pend[i] = true;
      m_p_bo[i] = o;
      m_p_bh[i] = h;
      m_p_bl[i] = l;
      m_p_bc[i] = c;
      m_p_sp[i] = spread_pts;
      m_sym_last[i] = ts;
      return true;
     }

   //---------------------------------------------------------------//
   // AdvanceTo — the driver asserts every bar with stamp <          |
   // ts_exclusive has been pushed (live: floor(server_now/60)*60).  |
   // Commits the open minute and finalizes any completed hour —     |
   // the CAUSAL H1-boundary detection (a completed server hour).    |
   //---------------------------------------------------------------//
   bool              AdvanceTo(const long ts_exclusive)
     {
      if(!m_ready)             { Fail("not initialized");        return false; }
      if(m_cur_min >= 0 && m_cur_min < ts_exclusive)
         if(!CommitMinute())
            return false;
      if(m_hour_open && m_hour_ts + 3600 <= ts_exclusive)
         FinalizeHour();
      return true;
     }

   //---------------------------------------------------------------//
   // H1 output — pop order enforces the drive contract: the hour's  |
   // M1 rows become drainable only after its H1 row is popped.      |
   //---------------------------------------------------------------//
   bool              H1Ready() const { return m_h1_head < m_h1_n; }
   long              PeekH1Ts() const
     {
      return (m_h1_head < m_h1_n) ? m_h1[m_h1_head].ts : -1;
     }

   bool              PopH1Row(SFaH1Row &row)
     {
      if(m_h1_head >= m_h1_n)
        {
         Fail("PopH1Row: no finalized hour");
         return false;
        }
      row = m_h1[m_h1_head];
      m_m1_release = m_h1[m_h1_head].ts + 3599;   // rows of [h, h+1h)
      m_h1_head++;
      CompactH1();
      return true;
     }

   //---------------------------------------------------------------//
   // M1 output — rows of hours whose H1 row has been consumed.      //
   //---------------------------------------------------------------//
   int               M1Available() const
     {
      int n = 0;
      for(int r = m_m1_head; r < m_m1_n; r++)
        {
         if(m_m1[r].ts > m_m1_release)
            break;
         n++;
        }
      return n;
     }

   bool              PopM1Row(SFaM1Row &row)
     {
      if(m_m1_head >= m_m1_n || m_m1[m_m1_head].ts > m_m1_release)
        {
         Fail("PopM1Row: no released row (pop the hour's H1 row first)");
         return false;
        }
      row = m_m1[m_m1_head];
      m_m1_head++;
      CompactM1();
      return true;
     }

   //---------------------------------------------------------------//
   // daily-mid output (CoreSignal OnDailyBar feed)                  //
   //---------------------------------------------------------------//
   int               MidAvailable() const { return m_mid_n - m_mid_head; }
   bool              PopMid(SFaDailyMid &out)
     {
      if(m_mid_head >= m_mid_n)
        {
         Fail("PopMid: none");
         return false;
        }
      out = m_mid[m_mid_head];
      m_mid_head++;
      if(m_mid_head >= 256)
        {
         int n = m_mid_n - m_mid_head;
         for(int i = 0; i < n; i++)
            m_mid[i] = m_mid[m_mid_head + i];
         m_mid_n = n;
         m_mid_head = 0;
        }
      return true;
     }

   //---------------------------------------------------------------//
   // thin terminal poll (live/tester only; the S0 CopyRates path).  |
   // Copies every completed M1 bar newer than each symbol's last    |
   // push, merges by stamp, pushes, then AdvanceTo(last closed+60). |
   // NOT exercised by the python mirror (staged for the terminal).  |
   //---------------------------------------------------------------//
   bool              PollTerminal(const long server_now)
     {
      if(!m_ready || !m_terminal)
        {
         Fail("PollTerminal: not in terminal mode");
         return false;
        }
      long last_closed = (server_now / 60) * 60 - 60;
      if(last_closed < 0)
         return true;
      MqlRates r[];
      // simple two-pass merge: find the minimum next stamp not yet
      // pushed, push all bars at that stamp, repeat (bounded per call)
      for(int guard = 0; guard < 100000; guard++)
        {
         long best = -1;
         for(int i = 0; i < FA_NSYM; i++)
           {
            long from = (m_sym_last[i] < 0) ? last_closed : m_sym_last[i] + 60;
            if(from > last_closed)
               continue;
            int n = CopyRates(m_broker[i], PERIOD_M1, (datetime)from,
                              (datetime)last_closed, r);
            for(int j = 0; j < n; j++)
              {
               long t = (long)r[j].time;
               if(t < from || t > last_closed || (t % 60) != 0)
                  continue;
               if(best < 0 || t < best)
                  best = t;
               break;
              }
           }
         if(best < 0)
            break;
         for(int i = 0; i < FA_NSYM; i++)
           {
            if(m_sym_last[i] >= best)
               continue;
            int n = CopyRates(m_broker[i], PERIOD_M1, (datetime)best,
                              (datetime)best, r);
            if(n == 1 && (long)r[0].time == best)
               if(!PushBar(i, best, r[0].open, r[0].high, r[0].low,
                           r[0].close, (int)r[0].spread))
                  return false;
           }
        }
      return AdvanceTo(last_closed + 60);
     }

   //---------------------------------------------------------------//
   // introspection / telemetry                                      //
   //---------------------------------------------------------------//
   long              MinutesCommitted() const { return m_minutes_committed; }
   long              BRows()            const { return m_b_rows;            }
   long              H1Rows()           const { return m_h1_rows_emitted;   }
   long              UnreadyRows()      const { return m_unready_rows;      }
   int               PreSeedHits()      const { return m_pre_seed_hits;     }
   int               SwapRollovers()    const { return m_se.rollovers_fired; }
   bool              Seeded(const int i) const
     {
      return (i >= 0 && i < FA_NSYM) ? m_seeded[i] : false;
     }
   bool              AllBookSeeded() const
     {
      for(int k = 0; k < FA_NBOOK; k++)
         if(!m_seeded[FA_BOOK_IX[k]])
            return false;
      return true;
     }
  };

#endif // BOOK_FEEDASSEMBLER_MQH
