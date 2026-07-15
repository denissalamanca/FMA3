//+------------------------------------------------------------------+
//| Book/CoreLiveDrive.mqh — CCoreLiveDrive: the LIVE Core a_h +      |
//| f_core drive (UNIT C of the FableBookNative build).               |
//|                                                                   |
//| WHAT THIS IS: the live-mode replacement for the S1 segment-batch  |
//| core feed (BeginCoreSegment/StepCoreLegBar/EndCoreSegment on the  |
//| FROZEN tgt column).  Per FABLE REVISION v2 item 2 (owner-ratified |
//| S2_PREP §185/§190), LIVE mode is:                                 |
//|   * per-minute streaming of the 9 CCoreLegSim accounts (the       |
//|     RECON-8d-proven per-leg arithmetic, byte-untouched) on the    |
//|     legs' own native M1 bars, raw float64 prices (the a_h feed    |
//|     discipline — NO float32 cast, unlike the b_h feed);           |
//|   * tgt = CCoreSignal.Tgt(leg) after StepBar of the leg's         |
//|     instrument (RECON-8g bit-zero vs the frozen tgt, 20.95M rows);|
//|   * segments = CCoreTrigger LIVE causal detector (31/31 dates ==  |
//|     anchor-exact harness, measured); on fire: seam-carry f_core,  |
//|     seed = combined eqc at the last bar (spec 6.2 seed chain),    |
//|     legcap = (seed * W) / slot_legs (NORMATIVE float order),      |
//|     BeginSegment at the act midnight;                             |
//|   * combined eqc = participating legs left-to-right + ONE add of  |
//|     the flat/held legcap total (the FinishSegment shape).  Before |
//|     a leg's first print of a segment this is HOLD-AT-LEGCAP — the |
//|     ratified live divergence from the anchor's retrospective      |
//|     first-value backfill (a forward streamer structurally cannot  |
//|     compute it); such minutes are counted in LeadHoldMinutes()    |
//|     telemetry (measured in-sample: 2-day max lag < 5-day gap, so  |
//|     no band decision can read a held row);                        |
//|   * f_core per union bar = net_lots*contract*mid_c*eurq/book_eqc  |
//|     (the S0 (c)-VIABLE identity, bit-equal 0.0 vs the frozen      |
//|     parquet), hourly row = last union bar in [h, h+1), emitted    |
//|     ONLY after the hour completes -> rows are final on append;    |
//|   * swap/eurq = ONE CSwapEurqCore PER INSTRUMENT on its own       |
//|     native tape (the python gate's exact drive shape:             |
//|     run_grid([inst], full_tape, "coresim"), bit-equal gated).     |
//|                                                                   |
//| OWNERSHIP: CCoreSignal + CCoreTrigger are ATTACHED (owned by the  |
//| EA and serialized by the version-2 warm blob via                  |
//| CCoreSignalState).  This class serializes ONLY its own state      |
//| (leg accounts, seam carries, seed chain, generator clocks) via    |
//| the CBookState template peer API (BsWriteState/BsSetState/        |
//| BsContinuity) -> the EA persists it as a SIDECAR file with the    |
//| same fnv64/eof torn-write protocol.                               |
//|                                                                   |
//| ZERO trading calls, ZERO CTrade, ZERO file I/O, ZERO terminal     |
//| calls — pure per-bar state (the FeedAssembler discipline).        |
//+------------------------------------------------------------------+
#ifndef BOOK_CORELIVEDRIVE_MQH
#define BOOK_CORELIVEDRIVE_MQH

#include <Book/BookOrchestrator.mqh>   // BOOKORC leg tables + CoreSim + BookState
#include <Core/CoreSignal.mqh>         // CCoreSignal + CCoreTrigger
#include <Book/SwapEurq.mqh>           // CSwapEurqCore (bit-equal generator)

#define CLD_NLEGS   BOOKORC_NLEGS      // 9 legs, book append order
#define CLD_NINST   CS_NINST           // 8 instrument feeds
#define CLD_NNET    BOOKORC_NNET       // 8 f_core net columns
#define CLD_NCROSS  8                  // EUR crosses (SE_CROSS order)
#define CLD_HORIZON 3155760000         // ~100y open-ended generator window
#define CLD_GROW    4096

// instrument (CS_I_* order) -> symbol name (== SE_SYM / broker MODEL name)
const string CLD_INST_SYM[CLD_NINST] =
  {
   "XAUUSD", "USDJPY", "ETHUSD", "EURGBP",
   "USTEC", "AUDUSD", "NZDUSD", "BTCUSD"
  };

class CCoreLiveDrive
  {
private:
   // ---- attached live-signal chain (EA-owned, blob-serialized) ----
   CCoreSignal      *m_sig;
   CCoreTrigger     *m_trig;

   // ---- own components ----
   CCoreLegSim       m_leg[CLD_NLEGS];
   CSwapEurqCore     m_se[CLD_NINST];
   bool              m_se_started[CLD_NINST];

   // ---- segment state ----
   double            m_W;                   // 1/7 (CCoreBookSim SetSlots(7))
   bool              m_begun;
   double            m_seed;                // current segment seed
   double            m_seed0;               // the INIT anchor (10000.0 cold)
   int               m_nsegs;
   double            m_legcap[CLD_NLEGS];
   bool              m_has[CLD_NLEGS];      // printed this segment
   double            m_lastEq[CLD_NLEGS];   // last close-mark leg equity

   // ---- f_core current-segment capture + cross-seam carry ----
   bool              m_cvL[CLD_NLEGS];
   double            m_cpL[CLD_NLEGS], m_cmL[CLD_NLEGS], m_cqL[CLD_NLEGS];
   bool              m_caV[CLD_NLEGS];
   double            m_caP[CLD_NLEGS], m_caM[CLD_NLEGS], m_caQ[CLD_NLEGS];
   double            m_comb;                // combined close-mark eqc
   bool              m_comb_have;

   // ---- pending minute (raw float64 fields) ----
   long              m_cur_min;
   bool              m_pend[CLD_NINST];
   double            m_p_o[CLD_NINST], m_p_h[CLD_NINST];
   double            m_p_l[CLD_NINST], m_p_c[CLD_NINST];
   int               m_p_sp[CLD_NINST];
   double            m_point[CLD_NINST];
   long              m_inst_last[CLD_NINST];
   bool              m_px[CLD_NCROSS];
   double            m_px_b[CLD_NCROSS], m_px_a[CLD_NCROSS];
   long              m_cross_last[CLD_NCROSS];

   // ---- pending hour f_core row (overwritten per union bar) ----
   bool              m_hr_have;
   long              m_hr_hour;
   double            m_hr_fc[CLD_NNET];

   // ---- output queues (drained by the EA each cycle) ----
   long              m_qs_ts[];             // combined-eqc 1m samples
   double            m_qs_v[];
   int               m_qs_head, m_qs_n;
   long              m_qh_ts[];             // completed hourly f_core rows
   double            m_qh_v[];              // flattened [row*CLD_NNET + s]
   int               m_qh_head, m_qh_n;
   long              m_last_flush_hour;

   // ---- telemetry ----
   long              m_minutes;             // core union minutes processed
   long              m_bars;                // leg bars stepped
   long              m_skipped_inst_bars;   // generator-not-ready skips
   long              m_lead_hold_minutes;   // hold-at-legcap minutes
   long              m_fires;
   string            m_last_fire;

   string            m_err;
   bool              m_ready;

   //---------------------------------------------------------------//
   void              QueueSample(const long ts, const double v)
     {
      int cap = ArraySize(m_qs_ts);
      if(m_qs_n >= cap)
        {
         ArrayResize(m_qs_ts, cap + CLD_GROW);
         ArrayResize(m_qs_v,  cap + CLD_GROW);
        }
      m_qs_ts[m_qs_n] = ts;
      m_qs_v[m_qs_n]  = v;
      m_qs_n++;
     }

   void              FlushHour()
     {
      if(!m_hr_have)
         return;
      int cap = ArraySize(m_qh_ts);
      if(m_qh_n >= cap)
        {
         ArrayResize(m_qh_ts, cap + 256);
         ArrayResize(m_qh_v, (cap + 256) * CLD_NNET);
        }
      m_qh_ts[m_qh_n] = m_hr_hour;
      for(int s = 0; s < CLD_NNET; s++)
         m_qh_v[m_qh_n * CLD_NNET + s] = m_hr_fc[s];
      m_qh_n++;
      m_last_flush_hour = m_hr_hour;
      m_hr_have = false;
     }

   // NORMATIVE legcap float order (CCoreBookSim::BeginSegment, spec 6.2)
   void              SeedLegcaps()
     {
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         double legcap = m_seed * m_W / (double)BOOKORC_LEG_SLOT[l];
         m_leg[l].ResetSegment(legcap);
         m_legcap[l] = legcap;
         m_has[l] = false;
         m_cvL[l] = false;
        }
     }

   bool              Reseed(const long act_day)
     {
      if(!m_comb_have)
        {
         m_err = "reseed without a combined eqc";
         return false;
        }
      // seam carry: legs that traded this segment update the ffill state
      // (== CCoreBookSim::ComputeFCore's end-of-segment carry update)
      for(int l = 0; l < CLD_NLEGS; l++)
         if(m_cvL[l])
           {
            m_caP[l] = m_cpL[l];
            m_caM[l] = m_cmL[l];
            m_caQ[l] = m_cqL[l];
            m_caV[l] = true;
           }
      m_seed = m_comb;                       // seed chain = FinalEqC (spec 6.2)
      SeedLegcaps();
      if(!m_trig.BeginSegment(m_seed, act_day))
        {
         m_err = "trigger BeginSegment: " + m_trig.LastError();
         return false;
        }
      m_nsegs++;
      m_fires++;
      m_last_fire = StringFormat("%s decided_day=%I64d act_day=%I64d seed=%.17g",
                                 m_trig.Kind(), m_trig.DecidedDay(),
                                 m_trig.ActDay(), m_seed);
      return true;
     }

   // f_core at the current union bar — the S0 (c)-VIABLE identity,
   // statement shape of CCoreBookSim::ComputeFCore's per-bar body
   void              ComputeRow(const long M)
     {
      double net_pos[CLD_NNET], net_mid[CLD_NNET], net_qe[CLD_NNET];
      double net_ct[CLD_NNET];
      bool   net_has[CLD_NNET];
      for(int s = 0; s < CLD_NNET; s++)
        {
         net_pos[s] = 0.0;
         net_mid[s] = 0.0;
         net_qe[s]  = 0.0;
         net_ct[s]  = 0.0;
         net_has[s] = false;
        }
      // net accumulation in LEG INDEX ORDER (the anchor's per_inst order)
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         int s = BOOKORC_LEG_NET[l];
         double p, mc, qe;
         if(m_cvL[l])
           {
            p  = m_cpL[l];
            mc = m_cmL[l];
            qe = m_cqL[l];
           }
         else if(m_caV[l])
           {
            p  = m_caP[l];
            mc = m_caM[l];
            qe = m_caQ[l];
           }
         else
            continue;                        // before the instrument's first bar ever
         net_pos[s] = net_pos[s] + p;        // left-to-right leg order
         if(!net_has[s])
           {
            net_mid[s] = mc;
            net_qe[s]  = qe;
            net_ct[s]  = BOOKORC_LEG_CONTRACT[l];
            net_has[s] = true;
           }
        }
      long hour = M - (M % 3600);
      m_hr_hour = hour;
      m_hr_have = true;
      for(int s = 0; s < CLD_NNET; s++)
        {
         if(!net_has[s])
           {
            m_hr_fc[s] = 0.0;                // fillna(0) case
            continue;
           }
         // NORMATIVE grouping: ((lots * contract) * mid) * eurq / eqc
         double val = net_pos[s] * net_ct[s] * net_mid[s] * net_qe[s];
         m_hr_fc[s] = val / m_comb;
        }
     }

   bool              CommitMinute()
     {
      long M = m_cur_min;

      // 0. flush a completed pending hour row (hour advanced)
      if(m_hr_have && M >= m_hr_hour + 3600)
         FlushHour();

      // lazy segment 0 at the first instrument bar (cold start)
      if(!m_begun)
        {
         bool anyp = false;
         for(int i = 0; i < CLD_NINST; i++)
            if(m_pend[i])
               anyp = true;
         if(anyp)
           {
            SeedLegcaps();
            if(!m_trig.BeginSegment(m_seed, M / 86400))
              {
               m_err = "trigger BeginSegment(0): " + m_trig.LastError();
               return false;
              }
            m_begun = true;
            m_nsegs = 1;
           }
        }

      // 1. trigger day scan FIRST (S2_CORE_LIVE_DESIGN 4.3 contract)
      if(m_begun)
        {
         bool fired = false;
         if(!m_trig.CheckDay(M, fired))
           {
            m_err = "trigger CheckDay: " + m_trig.LastError();
            return false;
           }
         if(fired && !Reseed(m_trig.ActDay()))
            return false;
        }

      // 2. cross bars (stamps <= M) into every per-instrument generator
      for(int c = 0; c < CLD_NCROSS; c++)
         if(m_px[c])
            for(int g = 0; g < CLD_NINST; g++)
               m_se[g].OnCrossBar(SE_CROSS[c], m_px_b[c], m_px_a[c]);

      // 3. per pending instrument: swap/eurq row -> signal StepBar
      double eq1[1], fl1[1], sl1[1], ss1[1];
      double geurq[CLD_NINST], gflag[CLD_NINST];
      double gswl[CLD_NINST], gsws[CLD_NINST];
      bool   gok[CLD_NINST];
      for(int i = 0; i < CLD_NINST; i++)
        {
         gok[i] = false;
         if(!m_pend[i])
            continue;
         if(!m_se_started[i])
           {
            m_se[i].Start(M, M + CLD_HORIZON);
            m_se_started[i] = true;
           }
         if(!m_se[i].Step(M, eq1, fl1, sl1, ss1))
           {
            m_skipped_inst_bars++;           // crosses unseeded (cold pre gap)
            continue;
           }
         geurq[i] = eq1[0];
         gflag[i] = fl1[0];
         gswl[i]  = sl1[0];
         gsws[i]  = ss1[0];
         gok[i]   = true;
         double ac = m_p_c[i] + m_p_sp[i] * m_point[i];
         if(!m_sig.StepBar(i, M, m_p_c[i], ac))
           {
            m_err = "signal: " + m_sig.LastError();
            return false;
           }
        }

      // 4. legs in BOOK APPEND ORDER: account step + trigger equity
      bool any = false;
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         int i = CsLegInst(l);
         if(!m_pend[i] || !gok[i])
            continue;
         double sp = m_p_sp[i] * m_point[i];
         double ao = m_p_o[i] + sp;
         double ah = m_p_h[i] + sp;
         double al = m_p_l[i] + sp;
         double ac = m_p_c[i] + sp;
         double tgt = m_sig.Tgt(l);
         if(!m_leg[l].StepBar(M, m_p_o[i], m_p_h[i], m_p_l[i], m_p_c[i],
                              ao, ah, al, ac,
                              geurq[i], gflag[i], gswl[i], gsws[i], tgt))
           {
            m_err = StringFormat("leg %d: %s", l, m_leg[l].LastError());
            return false;
           }
         int nb = m_leg[l].Bars();
         m_lastEq[l] = m_leg[l].EqC(nb - 1);
         m_cpL[l] = m_leg[l].Pos(nb - 1);
         m_cmL[l] = m_leg[l].MidC(nb - 1);
         m_cqL[l] = m_leg[l].Eurq(nb - 1);
         m_cvL[l] = true;
         m_has[l] = true;
         if(!m_trig.OnLegBar(l, M, m_lastEq[l]))
           {
            m_err = "trigger OnLegBar: " + m_trig.LastError();
            return false;
           }
         m_leg[l].CompactCapture();          // live memory bound
         any = true;
         m_bars++;
        }

      if(any)
        {
         // 5. combined close-mark eqc: participating legs left-to-right,
         // then ONE add of the flat/held legcap total (FinishSegment shape;
         // hold-at-legcap before a leg's first print = ratified live mode)
         double s = 0.0, flat = 0.0;
         bool first = true, held = false;
         for(int l = 0; l < CLD_NLEGS; l++)
           {
            if(m_has[l])
              {
               if(first)
                 {
                  s = m_lastEq[l];
                  first = false;
                 }
               else
                  s = s + m_lastEq[l];
              }
            else
              {
               flat += m_legcap[l];
               held = true;
              }
           }
         m_comb = s + flat;
         m_comb_have = true;
         if(held)
            m_lead_hold_minutes++;
         QueueSample(M, m_comb);
         // 6. f_core row at this union bar (last-in-hour wins)
         ComputeRow(M);
         m_minutes++;
        }

      for(int i = 0; i < CLD_NINST; i++)
         m_pend[i] = false;
      for(int c = 0; c < CLD_NCROSS; c++)
         m_px[c] = false;
      m_cur_min = -1;
      return true;
     }

public:
                     CCoreLiveDrive() : m_sig(NULL), m_trig(NULL),
                                        m_W(0.0), m_begun(false),
                                        m_seed(0.0), m_seed0(0.0), m_nsegs(0),
                                        m_comb(0.0), m_comb_have(false),
                                        m_cur_min(-1),
                                        m_hr_have(false), m_hr_hour(0),
                                        m_qs_head(0), m_qs_n(0),
                                        m_qh_head(0), m_qh_n(0),
                                        m_last_flush_hour(0),
                                        m_minutes(0), m_bars(0),
                                        m_skipped_inst_bars(0),
                                        m_lead_hold_minutes(0),
                                        m_fires(0), m_last_fire(""),
                                        m_err(""), m_ready(false) {}

   string            LastError() const { return m_err;   }
   bool              Ready()     const { return m_ready; }

   //---------------------------------------------------------------//
   bool              Init(CCoreSignal *sig, CCoreTrigger *trig)
     {
      m_ready = false;
      m_err = "";
      if(sig == NULL || trig == NULL)
        {
         m_err = "Init: signal/trigger not attached";
         return false;
        }
      m_sig  = sig;
      m_trig = trig;
      m_W = 1.0 / (double)7;                 // == CCoreBookSim::SetSlots(7)
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         m_leg[l].Configure(BOOKORC_LEG_SLOT[l], BOOKORC_LEG_CONTRACT[l],
                            BOOKORC_LEG_COMM[l], BOOKORC_LEG_LEV[l],
                            BOOKORC_LEG_STEP[l], BOOKORC_LEG_MIN[l]);
         m_legcap[l] = 0.0;
         m_has[l] = false;
         m_lastEq[l] = 0.0;
         m_cvL[l] = false;
         m_cpL[l] = 0.0;
         m_cmL[l] = 0.0;
         m_cqL[l] = 0.0;
         m_caV[l] = false;
         m_caP[l] = 0.0;
         m_caM[l] = 0.0;
         m_caQ[l] = 0.0;
        }
      for(int i = 0; i < CLD_NINST; i++)
        {
         if(!m_se[i].AddSymbol(CLD_INST_SYM[i]))
           {
            m_err = "SwapEurqCore AddSymbol failed: " + CLD_INST_SYM[i];
            return false;
           }
         m_se_started[i] = false;
         m_pend[i] = false;
         m_p_o[i] = 0.0;
         m_p_h[i] = 0.0;
         m_p_l[i] = 0.0;
         m_p_c[i] = 0.0;
         m_p_sp[i] = 0;
         m_point[i] = 0.0;
         m_inst_last[i] = -1;
        }
      for(int c = 0; c < CLD_NCROSS; c++)
        {
         m_px[c] = false;
         m_px_b[c] = 0.0;
         m_px_a[c] = 0.0;
         m_cross_last[c] = -1;
        }
      m_begun = false;
      m_seed = 0.0;
      m_seed0 = 0.0;
      m_nsegs = 0;
      m_comb = 0.0;
      m_comb_have = false;
      m_cur_min = -1;
      m_hr_have = false;
      m_hr_hour = 0;
      m_qs_head = 0;
      m_qs_n = 0;
      m_qh_head = 0;
      m_qh_n = 0;
      m_last_flush_hour = 0;
      m_minutes = 0;
      m_bars = 0;
      m_skipped_inst_bars = 0;
      m_lead_hold_minutes = 0;
      m_fires = 0;
      m_last_fire = "";
      m_ready = true;
      return true;
     }

   // cold start: seg-0 seed (the INIT anchor, 10000.0 in the frozen chain).
   // Segment 0 opens lazily at the first instrument bar.
   bool              ColdStart(const double seed)
     {
      if(!m_ready)
        {
         m_err = "not initialized";
         return false;
        }
      m_seed  = seed;
      m_seed0 = seed;
      m_begun = false;
      m_nsegs = 0;
      return true;
     }

   // `pre` rule: cross carry BEFORE its first live bar (warm/cold seeding)
   void              SeedCross(const int c, const double bid_c, const double ask_c)
     {
      if(c < 0 || c >= CLD_NCROSS)
         return;
      for(int g = 0; g < CLD_NINST; g++)
         m_se[g].SeedCross(SE_CROSS[c], bid_c, ask_c);
     }

   //---------------------------------------------------------------//
   // PushBar — one completed RAW M1 bar of a core instrument        //
   // (CopyRates form: bid OHLC + integer spread points + point).    //
   //---------------------------------------------------------------//
   bool              PushBar(const int inst, const long ts, const double o,
                             const double h, const double l, const double c,
                             const int spread_pts, const double point)
     {
      if(!m_ready)                    { m_err = "not initialized";     return false; }
      if(inst < 0 || inst >= CLD_NINST) { m_err = "PushBar: bad inst"; return false; }
      if((ts % 60) != 0)
        {
         m_err = StringFormat("PushBar %s: stamp %I64d not minute-aligned",
                              CLD_INST_SYM[inst], ts);
         return false;
        }
      if(ts <= m_inst_last[inst])
        {
         m_err = StringFormat("PushBar %s: stamp %I64d not ascending",
                              CLD_INST_SYM[inst], ts);
         return false;
        }
      if(m_cur_min >= 0 && ts > m_cur_min)
         if(!CommitMinute())
            return false;
      if(m_cur_min < 0)
         m_cur_min = ts;
      if(ts != m_cur_min)
        {
         m_err = StringFormat("PushBar %s: stamp %I64d behind open minute %I64d",
                              CLD_INST_SYM[inst], ts, m_cur_min);
         return false;
        }
      m_pend[inst] = true;
      m_p_o[inst] = o;
      m_p_h[inst] = h;
      m_p_l[inst] = l;
      m_p_c[inst] = c;
      m_p_sp[inst] = spread_pts;
      m_point[inst] = point;
      m_inst_last[inst] = ts;
      return true;
     }

   // one completed RAW EUR-cross M1 close (c index = SE_CROSS order)
   bool              PushCross(const int c, const long ts, const double bid_c,
                               const double ask_c)
     {
      if(!m_ready)                  { m_err = "not initialized";       return false; }
      if(c < 0 || c >= CLD_NCROSS)  { m_err = "PushCross: bad index";  return false; }
      if((ts % 60) != 0)            { m_err = "PushCross: unaligned";  return false; }
      if(ts <= m_cross_last[c])     { m_err = "PushCross: stale";      return false; }
      if(m_cur_min >= 0 && ts > m_cur_min)
         if(!CommitMinute())
            return false;
      if(m_cur_min < 0)
         m_cur_min = ts;
      if(ts != m_cur_min)
        {
         m_err = StringFormat("PushCross %d: stamp %I64d behind open minute %I64d",
                              c, ts, m_cur_min);
         return false;
        }
      m_px[c] = true;
      m_px_b[c] = bid_c;
      m_px_a[c] = ask_c;
      m_cross_last[c] = ts;
      return true;
     }

   // commit the open minute + flush any completed hour (causal clock)
   bool              AdvanceTo(const long ts_exclusive)
     {
      if(!m_ready)
        {
         m_err = "not initialized";
         return false;
        }
      if(m_cur_min >= 0 && m_cur_min < ts_exclusive)
         if(!CommitMinute())
            return false;
      if(m_hr_have && m_hr_hour + 3600 <= ts_exclusive)
         FlushHour();
      return true;
     }

   //---------------------------------------------------------------//
   // outputs                                                        //
   //---------------------------------------------------------------//
   int               Samples() const { return m_qs_n - m_qs_head; }
   bool              PopSample(long &ts, double &eqc)
     {
      if(m_qs_head >= m_qs_n)
        {
         m_err = "PopSample: none";
         return false;
        }
      ts  = m_qs_ts[m_qs_head];
      eqc = m_qs_v[m_qs_head];
      m_qs_head++;
      if(m_qs_head >= CLD_GROW)
        {
         int n = m_qs_n - m_qs_head;
         for(int i = 0; i < n; i++)
           {
            m_qs_ts[i] = m_qs_ts[m_qs_head + i];
            m_qs_v[i]  = m_qs_v[m_qs_head + i];
           }
         m_qs_n = n;
         m_qs_head = 0;
        }
      return true;
     }

   int               HourRows() const { return m_qh_n - m_qh_head; }
   bool              PopHourRow(long &hour, double &fc[])
     {
      if(m_qh_head >= m_qh_n)
        {
         m_err = "PopHourRow: none";
         return false;
        }
      hour = m_qh_ts[m_qh_head];
      if(ArraySize(fc) < CLD_NNET)
         ArrayResize(fc, CLD_NNET);
      for(int s = 0; s < CLD_NNET; s++)
         fc[s] = m_qh_v[m_qh_head * CLD_NNET + s];
      m_qh_head++;
      if(m_qh_head >= 256)
        {
         int n = m_qh_n - m_qh_head;
         for(int i = 0; i < n; i++)
           {
            m_qh_ts[i] = m_qh_ts[m_qh_head + i];
            for(int s = 0; s < CLD_NNET; s++)
               m_qh_v[i * CLD_NNET + s] = m_qh_v[(m_qh_head + i) * CLD_NNET + s];
           }
         m_qh_n = n;
         m_qh_head = 0;
        }
      return true;
     }

   //---------------------------------------------------------------//
   // introspection / telemetry                                      //
   //---------------------------------------------------------------//
   bool              Begun()          const { return m_begun;            }
   double            Seed()           const { return m_seed;             }
   double            Seed0()          const { return m_seed0;            }
   int               Segments()       const { return m_nsegs;            }
   double            CombEqC()        const { return m_comb;             }
   long              LastFlushHour()  const { return m_last_flush_hour;  }
   long              Minutes()        const { return m_minutes;          }
   long              Bars()           const { return m_bars;             }
   long              SkippedBars()    const { return m_skipped_inst_bars; }
   long              LeadHoldMinutes() const { return m_lead_hold_minutes; }
   long              Fires()          const { return m_fires;            }
   string            LastFire()       const { return m_last_fire;        }

   //================================================================//
   // CBookState peer API — the SIDECAR state file.  Save is legal    //
   // only with the minute machine idle and the queues drained (the   //
   // EA saves at the end of a completed hour cycle).                 //
   //================================================================//
   bool              BsWriteState(CBookStateWriter &w)
     {
      if(!m_ready)      { m_err = "not initialized";           return false; }
      if(m_cur_min >= 0) { m_err = "save with an open minute"; return false; }
      if(m_qs_head < m_qs_n || m_qh_head < m_qh_n)
        {
         m_err = "save with undrained queues";
         return false;
        }
      w.Raw("\"config\": {\"nlegs\": ");
      w.I(CLD_NLEGS);
      w.KI("ninst", CLD_NINST);
      w.KI("nnet", CLD_NNET);
      w.KD("W", m_W);
      w.Raw("}");

      w.CK("legs");
      w.Raw("[");
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         if(l > 0)
            w.Raw(", ");
         w.Raw("{\"bal\": ");
         w.D(m_leg[l].Balance());
         w.KD("pos",    m_leg[l].CurPos());
         w.KD("entry",  m_leg[l].CurEntry());
         w.KD("legcap", m_leg[l].LegCap());
         w.KB("has", m_has[l]);
         w.KD("last_eq", m_lastEq[l]);
         w.KB("cv", m_cvL[l]);
         w.KD("cp", m_cpL[l]);
         w.KD("cm", m_cmL[l]);
         w.KD("cq", m_cqL[l]);
         w.KB("cav", m_caV[l]);
         w.KD("cap", m_caP[l]);
         w.KD("cam", m_caM[l]);
         w.KD("caq", m_caQ[l]);
         w.Raw("}");
        }
      w.Raw("]");

      w.CK("seg");
      w.Raw("{\"begun\": ");
      w.B(m_begun);
      w.KD("seed",  m_seed);
      w.KD("seed0", m_seed0);
      w.KI("nsegs", m_nsegs);
      w.KD("comb",  m_comb);
      w.KB("comb_have", m_comb_have);
      w.Raw("}");

      w.CK("se");
      w.Raw("[");
      for(int i = 0; i < CLD_NINST; i++)
        {
         if(i > 0)
            w.Raw(", ");
         w.Raw("{\"started\": ");
         w.B(m_se_started[i]);
         w.KI("next_day",  m_se_started[i] ? m_se[i].NextDay() : 0);
         w.KI("inst_last", m_inst_last[i]);
         w.KD("point",     m_point[i]);
         w.CK("cross");
         w.Raw("[");
         for(int c = 0; c < CLD_NCROSS; c++)
           {
            double cb = 0.0, ca = 0.0;
            bool sd = false;
            m_se[i].CrossGet(c, cb, ca, sd);
            if(c > 0)
               w.Raw(", ");
            w.Raw("{\"b\": ");
            w.D(cb);
            w.KD("a", ca);
            w.KB("sd", sd);
            w.Raw("}");
           }
         w.Raw("]}");
        }
      w.Raw("]");

      w.CK("cross_last");
      w.ArrL(m_cross_last, CLD_NCROSS);

      w.CK("hr");
      w.Raw("{\"have\": ");
      w.B(m_hr_have);
      w.KI("hour", m_hr_hour);
      w.CK("fc");
      w.ArrD(m_hr_fc, CLD_NNET);
      w.Raw("}");

      w.CK("clock");
      w.Raw("{\"last_flush_hour\": ");
      w.I(m_last_flush_hour);
      w.KI("minutes", m_minutes);
      w.KI("bars",    m_bars);
      w.KI("skipped", m_skipped_inst_bars);
      w.KI("lead_hold", m_lead_hold_minutes);
      w.KI("fires",   m_fires);
      w.Raw("}");
      return true;
     }

   bool              BsSetState(CBookStateTok &tk)
     {
      if(!m_ready)
        {
         m_err = "not initialized (Init before restore)";
         return false;
        }
      long nlegs = 0, ninst = 0, nnet = 0;
      double wv = 0.0;
      bool ok = tk.Key("config") && tk.Eat('{');
      ok = ok && tk.Key("nlegs") && tk.IntVal(nlegs);
      ok = ok && tk.CommaKey("ninst") && tk.IntVal(ninst);
      ok = ok && tk.CommaKey("nnet")  && tk.IntVal(nnet);
      ok = ok && tk.CommaKey("W")     && tk.NumVal(wv);
      ok = ok && tk.Eat('}');
      if(!ok)
        {
         m_err = "config: " + tk.Err();
         return false;
        }
      if(nlegs != CLD_NLEGS || ninst != CLD_NINST || nnet != CLD_NNET
         || !(wv == m_W))
        {
         m_err = "config mismatch";
         return false;
        }

      ok = tk.CommaKey("legs") && tk.Eat('[');
      if(!ok) { m_err = "legs: " + tk.Err(); return false; }
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         double bal = 0.0, pos = 0.0, entry = 0.0, legcap = 0.0;
         if(l > 0 && !tk.Eat(','))
           { m_err = "legs sep: " + tk.Err(); return false; }
         ok = tk.Eat('{') && tk.Key("bal") && tk.NumVal(bal);
         ok = ok && tk.CommaKey("pos")    && tk.NumVal(pos);
         ok = ok && tk.CommaKey("entry")  && tk.NumVal(entry);
         ok = ok && tk.CommaKey("legcap") && tk.NumVal(legcap);
         ok = ok && tk.CommaKey("has")    && tk.BoolVal(m_has[l]);
         ok = ok && tk.CommaKey("last_eq") && tk.NumVal(m_lastEq[l]);
         ok = ok && tk.CommaKey("cv")  && tk.BoolVal(m_cvL[l]);
         ok = ok && tk.CommaKey("cp")  && tk.NumVal(m_cpL[l]);
         ok = ok && tk.CommaKey("cm")  && tk.NumVal(m_cmL[l]);
         ok = ok && tk.CommaKey("cq")  && tk.NumVal(m_cqL[l]);
         ok = ok && tk.CommaKey("cav") && tk.BoolVal(m_caV[l]);
         ok = ok && tk.CommaKey("cap") && tk.NumVal(m_caP[l]);
         ok = ok && tk.CommaKey("cam") && tk.NumVal(m_caM[l]);
         ok = ok && tk.CommaKey("caq") && tk.NumVal(m_caQ[l]);
         ok = ok && tk.Eat('}');
         if(!ok)
           {
            m_err = StringFormat("leg %d: %s", l, tk.Err());
            return false;
           }
         m_leg[l].RestoreAccount(bal, pos, entry, legcap);
         m_legcap[l] = legcap;
        }
      if(!tk.Eat(']'))
        { m_err = "legs close: " + tk.Err(); return false; }

      long nsegs = 0;
      ok = tk.CommaKey("seg") && tk.Eat('{');
      ok = ok && tk.Key("begun") && tk.BoolVal(m_begun);
      ok = ok && tk.CommaKey("seed")  && tk.NumVal(m_seed);
      ok = ok && tk.CommaKey("seed0") && tk.NumVal(m_seed0);
      ok = ok && tk.CommaKey("nsegs") && tk.IntVal(nsegs);
      ok = ok && tk.CommaKey("comb")  && tk.NumVal(m_comb);
      ok = ok && tk.CommaKey("comb_have") && tk.BoolVal(m_comb_have);
      ok = ok && tk.Eat('}');
      if(!ok)
        { m_err = "seg: " + tk.Err(); return false; }
      m_nsegs = (int)nsegs;

      ok = tk.CommaKey("se") && tk.Eat('[');
      if(!ok) { m_err = "se: " + tk.Err(); return false; }
      for(int i = 0; i < CLD_NINST; i++)
        {
         bool started = false;
         long next_day = 0, inst_last = 0;
         double pt = 0.0;
         if(i > 0 && !tk.Eat(','))
           { m_err = "se sep: " + tk.Err(); return false; }
         ok = tk.Eat('{') && tk.Key("started") && tk.BoolVal(started);
         ok = ok && tk.CommaKey("next_day")  && tk.IntVal(next_day);
         ok = ok && tk.CommaKey("inst_last") && tk.IntVal(inst_last);
         ok = ok && tk.CommaKey("point")     && tk.NumVal(pt);
         ok = ok && tk.CommaKey("cross")     && tk.Eat('[');
         if(!ok)
           { m_err = StringFormat("se %d: %s", i, tk.Err()); return false; }
         if(started)
           {
            m_se[i].Start(next_day, next_day + CLD_HORIZON);
            m_se[i].RestoreClock(next_day);
           }
         m_se_started[i] = started;
         m_inst_last[i] = inst_last;
         m_point[i] = pt;
         for(int c = 0; c < CLD_NCROSS; c++)
           {
            double cb = 0.0, ca = 0.0;
            bool sd = false;
            if(c > 0 && !tk.Eat(','))
              { m_err = "se cross sep: " + tk.Err(); return false; }
            ok = tk.Eat('{') && tk.Key("b") && tk.NumVal(cb);
            ok = ok && tk.CommaKey("a")  && tk.NumVal(ca);
            ok = ok && tk.CommaKey("sd") && tk.BoolVal(sd);
            ok = ok && tk.Eat('}');
            if(!ok)
              { m_err = "se cross: " + tk.Err(); return false; }
            m_se[i].CrossRestore(c, cb, ca, sd);
           }
         if(!tk.Eat(']') || !tk.Eat('}'))
           { m_err = "se close: " + tk.Err(); return false; }
        }
      if(!tk.Eat(']'))
        { m_err = "se array close: " + tk.Err(); return false; }

      ok = tk.CommaKey("cross_last") && tk.ArrL(m_cross_last, CLD_NCROSS);
      if(!ok)
        { m_err = "cross_last: " + tk.Err(); return false; }

      long hrh = 0;
      double fc[];
      ok = tk.CommaKey("hr") && tk.Eat('{');
      ok = ok && tk.Key("have") && tk.BoolVal(m_hr_have);
      ok = ok && tk.CommaKey("hour") && tk.IntVal(hrh);
      ok = ok && tk.CommaKey("fc") && tk.ArrD(fc, CLD_NNET);
      ok = ok && tk.Eat('}');
      if(!ok)
        { m_err = "hr: " + tk.Err(); return false; }
      m_hr_hour = hrh;
      for(int s = 0; s < CLD_NNET; s++)
         m_hr_fc[s] = fc[s];

      long lfh = 0, mins = 0, bars = 0, skip = 0, lead = 0, fires = 0;
      ok = tk.CommaKey("clock") && tk.Eat('{');
      ok = ok && tk.Key("last_flush_hour") && tk.IntVal(lfh);
      ok = ok && tk.CommaKey("minutes") && tk.IntVal(mins);
      ok = ok && tk.CommaKey("bars")    && tk.IntVal(bars);
      ok = ok && tk.CommaKey("skipped") && tk.IntVal(skip);
      ok = ok && tk.CommaKey("lead_hold") && tk.IntVal(lead);
      ok = ok && tk.CommaKey("fires")   && tk.IntVal(fires);
      ok = ok && tk.Eat('}');
      if(!ok)
        { m_err = "clock: " + tk.Err(); return false; }
      m_last_flush_hour = lfh;
      m_minutes = mins;
      m_bars = bars;
      m_skipped_inst_bars = skip;
      m_lead_hold_minutes = lead;
      m_fires = fires;

      m_cur_min = -1;
      m_qs_head = 0;
      m_qs_n = 0;
      m_qh_head = 0;
      m_qh_n = 0;
      for(int i = 0; i < CLD_NINST; i++)
         m_pend[i] = false;
      for(int c = 0; c < CLD_NCROSS; c++)
         m_px[c] = false;
      m_err = "";
      return true;
     }

   // ratio-chain snapshot: the combined eqc is RECOMPUTED from the
   // restored per-leg fields so a spliced/re-based sidecar fails the
   // CBookState j-guard (the fnv64 checksum catches raw corruption).
   bool              BsContinuity(SBookStateContinuity &c)
     {
      if(!m_ready)
        {
         m_err = "not initialized";
         return false;
        }
      double s = 0.0, flat = 0.0;
      bool first = true;
      for(int l = 0; l < CLD_NLEGS; l++)
        {
         if(m_has[l])
           {
            if(first)
              {
               s = m_lastEq[l];
               first = false;
              }
            else
               s = s + m_lastEq[l];
           }
         else
            flat += m_legcap[l];
        }
      double comb = s + flat;
      c.have   = m_begun;
      c.j_hour = m_begun ? m_last_flush_hour : -1;
      c.a_h    = m_begun ? comb : 1.0;
      c.b_h    = m_begun ? m_seed : 1.0;
      c.w      = BOOKORC_W;
      c.j      = c.w * c.a_h + (1.0 - c.w) * c.b_h;
      c.a_first = m_seed0;
      c.b_first = m_seed0;
      return true;
     }
  };

#endif // BOOK_CORELIVEDRIVE_MQH
