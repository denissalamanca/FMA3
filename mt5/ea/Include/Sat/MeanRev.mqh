//+------------------------------------------------------------------+
//| MeanRev.mqh — FMA3 v34 meanrev sleeve stepper (CSatMeanRevStepper)|
//|                                                                  |
//| 1:1 MQL5 port of the Wave-1 validated Python stepper             |
//|   research/bpure/steppers/meanrev_stepper.py                     |
//| (state-exact vs frozen goldens; SPEC = model/v3/freeze/          |
//|  FMA3-v34-freeze-1/src/research/sleeves/meanrev.py + core.py).   |
//| Every constant, branch, guard and NaN rule is preserved verbatim.|
//|                                                                  |
//| SLEEVE (16 symbols, fixed order — SatMR_SYMBOLS):                |
//|   FX crosses (10): AUDNZD EURCHF EURGBP EURSEK EURNOK AUDCAD     |
//|                    NZDCAD CADCHF EURCAD EURNZD                   |
//|   Indices    (6):  DAX JP225 UK100 US30 USA500 USTEC             |
//|                                                                  |
//| PER-BAR API (documented contract):                               |
//|   CSatMeanRevStepper stp;  stp.Init();                           |
//|   stp.Step(ts, closes, pos);   // ONE union-grid HOURLY bar      |
//|     ts      : server time of the union hourly bar, STRICTLY      |
//|               increasing.                                        |
//|     closes[]: >= 16 doubles in SatMR_SYMBOLS order; the RAW      |
//|               close of the bar, SatNan() when the symbol printed |
//|               no bar this hour (the stepper ffills internally).  |
//|     pos[]   : out, >= 16 doubles (resized if dynamic); the       |
//|               ACTIVE position {frac of equity} for this bar.     |
//|   stp.Finalize();   // flush the trailing (still-open) day once  |
//|                     // the stream ends (records its pending      |
//|                     // target exactly like the Python finalize())|
//|                                                                  |
//| TIMING (from the Python docstring):                              |
//|  * a daily row is cut when the FIRST hourly bar of the next      |
//|    (server) calendar day arrives (mirrors resample('1D').last()  |
//|    .dropna(how='all') — a day with no sleeve close yet is NOT a  |
//|    row);                                                         |
//|  * the daily target of day d becomes effective at the first      |
//|    union hourly bar stamped >= (d+1) 13:00 (EXEC_LAG=14) and is  |
//|    held (ffill) until replaced; positions before the first       |
//|    effective stamp are 0.0.                                      |
//|                                                                  |
//| FAITHFUL DETAILS:                                                |
//|  * hourly ret on the ffilled union close, 0.0 when prev close is |
//|    NaN, clipped to [-0.30,+0.30]; NO NaN ever -> every hourly    |
//|    bar is an ewm observation (CSatEwmMean span=720, pandas       |
//|    adjust=True kernel incl. the `weighted != cur` skip branch);  |
//|  * sizing vol = sqrt(wavg * 24.0 * 365.25) (association order    |
//|    preserved), sampled at the last hourly bar of the day;        |
//|  * FX z = (px - SMA60)/SD60, SD ddof=1 TWO-PASS over the 60-row  |
//|    daily window incl. today, summation NEWEST -> OLDEST exactly  |
//|    like Python _win() (order preserved for bit-parity); NaN in   |
//|    window -> z NaN; hysteresis transitions only on FINITE z      |
//|    (inf from sd==0 skipped, numpy isfinite semantics);           |
//|  * Index z = (px/px[t-5]-1)/(vol_d*sqrt(5/365.25)) with numpy    |
//|    division semantics (SatNpDiv); trend = px > SMA200 (false     |
//|    when SMA undefined); held increments only on FINITE-z days;   |
//|  * size FROZEN at entry: st!=0 and (first daily row or st_prev   |
//|    != st) -> size = K / max(vol_d, 0.05) (K=0.07, VOL_SPAN=30    |
//|    vol — NOT 60d); pos_raw = st*size clipped to [-1,+1];         |
//|  * sleeve gross cap INSIDE the sleeve every day: gross =         |
//|    sum(|pos|) in SatMR_SYMBOLS order (order preserved), scale =  |
//|    min(1.0, 3.0/gross) via SatNpDiv (gross==0 -> inf -> 1.0).    |
//|                                                                  |
//| STATE: GetState/SetState mirror the Python get_state/set_state   |
//| dict field-for-field (SSatMeanRevState) for live EA warm-start.  |
//| cur_day is stored as the server day number ts/86400 (-1 = none), |
//| pending as a fixed FIFO of SatMR_MAX_PEND slots (the queue never |
//| holds more than ~2 entries by construction: one target per day,  |
//| popped at the first bar >= (d+1) 13:00).                         |
//|                                                                  |
//| The Python `record=True` validation path is NOT ported (the     |
//| parity harness records on the Python side).                      |
//+------------------------------------------------------------------+
#ifndef SAT_MEANREV_MQH
#define SAT_MEANREV_MQH

#include <Sat/SatMath.mqh>

#define SatMR_NSYM      16
#define SatMR_NFX       10
#define SatMR_NIDX      6
#define SatMR_RING      256   // ring capacity >= max(TREND_L, L) = 200
#define SatMR_MAX_PEND  8     // pending FIFO capacity (worst case ~2)

// sleeve symbols, FX crosses then indices — ORDER IS PART OF THE SPEC
// (gross-cap summation and all per-symbol loops run in this order)
const string SatMR_SYMBOLS[SatMR_NSYM] =
  {
   "AUDNZD", "EURCHF", "EURGBP", "EURSEK", "EURNOK",
   "AUDCAD", "NZDCAD", "CADCHF", "EURCAD", "EURNZD",
   "DAX", "JP225", "UK100", "US30", "USA500", "USTEC"
  };

//==================================================================//
// serializable state — field-for-field mirror of Python get_state  //
//==================================================================//
struct SSatMeanRevState
  {
   int               version;                      // = 1
   // --- params (PARAMS dict) ---
   int               L;                            // 60
   double            z_in;                         // 2.25
   double            z_out;                        // 0.75
   int               D;                            // 5
   double            z_entry;                      // 1.5
   double            K;                            // 0.07
   double            z_exit;                       // 0.0
   int               trend_L;                      // 200
   int               max_hold;                     // 10
   int               exec_lag;                     // 14
   double            vol_floor;                    // 0.05
   double            pos_cap;                      // 1.0
   double            gross_cap;                    // 3.0
   int               vol_span;                     // 30
   // --- day / ring ---
   long              cur_day;                      // ts/86400; -1 = none
   int               dcount;                       // daily rows pushed (global)
   int               dptr;                         // shared ring write ptr
   // --- per-symbol hourly state ---
   double            close[SatMR_NSYM];            // ffilled union close
   double            wavg[SatMR_NSYM];             // ewm weighted avg of ret^2
   double            old_wt[SatMR_NSYM];
   long              nobs[SatMR_NSYM];
   // --- per-symbol daily state ---
   double            dbuf[SatMR_NSYM][SatMR_RING]; // daily close rings
   int               st[SatMR_NSYM];               // hysteresis / dip state
   int               held[SatMR_NIDX];             // index holding-day counter
   double            size[SatMR_NSYM];             // frozen entry size
   // --- execution state ---
   double            pos[SatMR_NSYM];              // active hourly position
   int               pend_count;
   datetime          pend_eff[SatMR_MAX_PEND];
   double            pend_pos[SatMR_MAX_PEND][SatMR_NSYM];
  };

//==================================================================//
// CSatMeanRevStepper — steps all 16 symbols together, one HOURLY   //
// union-grid bar at a time                                         //
//==================================================================//
class CSatMeanRevStepper
  {
public:
   // --- params (public on purpose: mirror of self.p) ---
   int               m_L;
   double            m_z_in;
   double            m_z_out;
   int               m_D;
   double            m_z_entry;
   double            m_K;
   double            m_z_exit;
   int               m_trend_L;
   int               m_max_hold;
   int               m_exec_lag;
   double            m_vol_floor;
   double            m_pos_cap;
   double            m_gross_cap;
   int               m_vol_span;
   // --- derived (recomputed from params, __init__ style) ---
   double            m_sqrt_d;                     // sqrt(D/365.25)
   // --- per-symbol hourly state ---
   double            m_close[SatMR_NSYM];          // ffilled union close
   CSatEwmMean       m_ewm[SatMR_NSYM];            // ret^2 ewm (span=720)
   // --- per-symbol daily state ---
   double            m_dbuf[SatMR_NSYM][SatMR_RING];
   int               m_dptr;                       // shared write ptr
   int               m_dcount;                     // daily rows pushed
   int               m_st[SatMR_NSYM];
   int               m_held[SatMR_NIDX];           // INDICES only (i-10)
   double            m_size[SatMR_NSYM];
   // --- execution state ---
   bool              m_have_day;                   // cur_day is not None
   long              m_cur_day;                    // ts/86400
   double            m_pos[SatMR_NSYM];
   int               m_pend_count;
   datetime          m_pend_eff[SatMR_MAX_PEND];
   double            m_pend_pos[SatMR_MAX_PEND][SatMR_NSYM];

                     CSatMeanRevStepper() { Init(); }

   //---------------------------------------------------------------//
   // Init — frozen v34 spec constants (PARAMS dict verbatim)        //
   //---------------------------------------------------------------//
   void              Init()
     {
      m_L         = 60;
      m_z_in      = 2.25;
      m_z_out     = 0.75;
      m_D         = 5;
      m_z_entry   = 1.5;
      m_K         = 0.07;
      m_z_exit    = 0.0;
      m_trend_L   = 200;
      m_max_hold  = 10;
      m_exec_lag  = 14;
      m_vol_floor = 0.05;
      m_pos_cap   = 1.0;
      m_gross_cap = 3.0;
      m_vol_span  = 30;
      Reset();
     }

   //---------------------------------------------------------------//
   // Reset — cold-start state from the current params               //
   //---------------------------------------------------------------//
   void              Reset()
     {
      // Python: span = VOL_SPAN*24; com=(span-1)/2; alpha=1/(1+com);
      // f = 1-alpha.  CSatEwmMean computes f = 1 - 2/(span+1) which
      // is the SAME real number -> the SAME double (span=720).
      double span = (double)(m_vol_span * 24);     // 720 hourly bars
      m_sqrt_d = MathSqrt((double)m_D / 365.25);
      double nan = SatNan();
      for(int i = 0; i < SatMR_NSYM; i++)
        {
         m_close[i] = nan;
         m_ewm[i].Init(span, 1);                   // minp=1: NaN iff nobs==0
         for(int j = 0; j < SatMR_RING; j++)
            m_dbuf[i][j] = nan;
         m_st[i]   = 0;
         m_size[i] = 0.0;
         m_pos[i]  = 0.0;
        }
      for(int i = 0; i < SatMR_NIDX; i++)
         m_held[i] = 0;
      m_dptr       = 0;
      m_dcount     = 0;
      m_have_day   = false;
      m_cur_day    = 0;
      m_pend_count = 0;
     }

   //---------------------------------------------------------------//
   // Step — process ONE hourly union-grid bar.                      //
   // closes[i] is the RAW close of SatMR_SYMBOLS[i] (NaN when the   //
   // symbol printed no bar this hour).  Fills pos_out with the      //
   // active position (frac of equity) for this bar.                 //
   //---------------------------------------------------------------//
   void              Step(const datetime ts, const double &closes[],
                          double &pos_out[])
     {
      long d = (long)ts / 86400;                   // server calendar day
      if(m_have_day && d != m_cur_day)
         FinalizeDay(m_cur_day);
      m_have_day = true;
      m_cur_day  = d;

      for(int i = 0; i < SatMR_NSYM; i++)
        {
         double c    = closes[i];
         double prev = m_close[i];
         if(c == c)
            m_close[i] = c;
         double cc = m_close[i];
         // hourly ret on the ffilled close; 0.0 when prev is NaN
         double r;
         if(prev != prev || cc != cc)
            r = 0.0;
         else
           {
            r = cc / prev - 1.0;
            if(r > 0.30)
               r = 0.30;
            else if(r < -0.30)
               r = -0.30;
           }
         double x = r * r;
         // pandas ewm adjust=True kernel — x is never NaN, so
         // CSatEwmMean::Step reproduces the meanrev kernel verbatim
         // (seed wavg=x/old_wt=1 on nobs==0; decay, `w != x` skip
         // branch, old_wt += 1 otherwise).
         m_ewm[i].Step(x);
        }

      // apply any daily targets that have become effective (ffill)
      while(m_pend_count > 0 && m_pend_eff[0] <= ts)
         PopPending();

      if(ArraySize(pos_out) < SatMR_NSYM)
         ArrayResize(pos_out, SatMR_NSYM);
      for(int i = 0; i < SatMR_NSYM; i++)
         pos_out[i] = m_pos[i];
     }

   //---------------------------------------------------------------//
   // Finalize — flush the trailing (still-open) day; call once      //
   // after the stream ends if you need its pending target.          //
   //---------------------------------------------------------------//
   void              Finalize()
     {
      if(m_have_day)
        {
         FinalizeDay(m_cur_day);
         m_have_day = false;
        }
     }

   //---------------------------------------------------------------//
   // serializable state (EA warm-start) — field-for-field mirror    //
   //---------------------------------------------------------------//
   void              GetState(SSatMeanRevState &out) const
     {
      out.version   = 1;
      out.L         = m_L;
      out.z_in      = m_z_in;
      out.z_out     = m_z_out;
      out.D         = m_D;
      out.z_entry   = m_z_entry;
      out.K         = m_K;
      out.z_exit    = m_z_exit;
      out.trend_L   = m_trend_L;
      out.max_hold  = m_max_hold;
      out.exec_lag  = m_exec_lag;
      out.vol_floor = m_vol_floor;
      out.pos_cap   = m_pos_cap;
      out.gross_cap = m_gross_cap;
      out.vol_span  = m_vol_span;
      out.cur_day   = m_have_day ? m_cur_day : -1;
      out.dcount    = m_dcount;
      out.dptr      = m_dptr;
      for(int i = 0; i < SatMR_NSYM; i++)
        {
         out.close[i]  = m_close[i];
         out.wavg[i]   = m_ewm[i].m_avg;
         out.old_wt[i] = m_ewm[i].m_old_wt;
         out.nobs[i]   = m_ewm[i].m_nobs;
         for(int j = 0; j < SatMR_RING; j++)
            out.dbuf[i][j] = m_dbuf[i][j];
         out.st[i]   = m_st[i];
         out.size[i] = m_size[i];
         out.pos[i]  = m_pos[i];
        }
      for(int i = 0; i < SatMR_NIDX; i++)
         out.held[i] = m_held[i];
      int n = m_pend_count;
      if(n > SatMR_MAX_PEND)
         n = SatMR_MAX_PEND;                       // never happens (<~2)
      out.pend_count = n;
      for(int k = 0; k < n; k++)
        {
         out.pend_eff[k] = m_pend_eff[k];
         for(int i = 0; i < SatMR_NSYM; i++)
            out.pend_pos[k][i] = m_pend_pos[k][i];
        }
     }

   void              SetState(const SSatMeanRevState &in)
     {
      m_L         = in.L;
      m_z_in      = in.z_in;
      m_z_out     = in.z_out;
      m_D         = in.D;
      m_z_entry   = in.z_entry;
      m_K         = in.K;
      m_z_exit    = in.z_exit;
      m_trend_L   = in.trend_L;
      m_max_hold  = in.max_hold;
      m_exec_lag  = in.exec_lag;
      m_vol_floor = in.vol_floor;
      m_pos_cap   = in.pos_cap;
      m_gross_cap = in.gross_cap;
      m_vol_span  = in.vol_span;
      // derived (Python __init__ recomputes these from params)
      double span = (double)(m_vol_span * 24);
      m_sqrt_d = MathSqrt((double)m_D / 365.25);
      m_have_day = (in.cur_day >= 0);
      m_cur_day  = m_have_day ? in.cur_day : 0;
      m_dcount   = in.dcount;
      m_dptr     = in.dptr;
      for(int i = 0; i < SatMR_NSYM; i++)
        {
         m_close[i] = in.close[i];
         m_ewm[i].Init(span, 1);
         m_ewm[i].m_avg    = in.wavg[i];
         m_ewm[i].m_old_wt = in.old_wt[i];
         m_ewm[i].m_nobs   = in.nobs[i];
         for(int j = 0; j < SatMR_RING; j++)
            m_dbuf[i][j] = in.dbuf[i][j];
         m_st[i]   = in.st[i];
         m_size[i] = in.size[i];
         m_pos[i]  = in.pos[i];
        }
      for(int i = 0; i < SatMR_NIDX; i++)
         m_held[i] = in.held[i];
      m_pend_count = in.pend_count;
      for(int k = 0; k < m_pend_count; k++)
        {
         m_pend_eff[k] = in.pend_eff[k];
         for(int i = 0; i < SatMR_NSYM; i++)
            m_pend_pos[k][i] = in.pend_pos[k][i];
        }
     }

private:
   //---------------------------------------------------------------//
   // helpers                                                        //
   //---------------------------------------------------------------//
   // Python-style modulo into the ring (always non-negative)
   int               Wrap(const int i) const
     {
      int r = i % SatMR_RING;
      if(r < 0)
         r += SatMR_RING;
      return r;
     }

   // core.realized_vol at the current hourly bar (self._vol_now)
   double            VolNow(const int i) const
     {
      if(m_ewm[i].m_nobs == 0)
         return SatNan();
      // association order preserved: (wavg * 24.0) * 365.25
      return MathSqrt(m_ewm[i].m_avg * 24.0 * 365.25);
     }

   void              PopPending()
     {
      for(int i = 0; i < SatMR_NSYM; i++)
         m_pos[i] = m_pend_pos[0][i];
      for(int k = 1; k < m_pend_count; k++)
        {
         m_pend_eff[k - 1] = m_pend_eff[k];
         for(int i = 0; i < SatMR_NSYM; i++)
            m_pend_pos[k - 1][i] = m_pend_pos[k][i];
        }
      m_pend_count--;
     }

   //---------------------------------------------------------------//
   // daily close-of-day logic (self._finalize_day, verbatim)        //
   //---------------------------------------------------------------//
   void              FinalizeDay(const long day)
     {
      double px[SatMR_NSYM];
      double vol[SatMR_NSYM];
      // mirror dropna(how='all'): a day with no sleeve close yet is
      // not a row
      bool all_nan = true;
      for(int i = 0; i < SatMR_NSYM; i++)
        {
         px[i] = m_close[i];
         if(px[i] == px[i])
            all_nan = false;
        }
      if(all_nan)
         return;
      for(int i = 0; i < SatMR_NSYM; i++)
         vol[i] = VolNow(i);

      bool first_row = (m_dcount == 0);
      // push today's daily closes into the rings (window includes
      // today); all rings advance together on one global pointer
      int ptr = m_dptr;
      for(int i = 0; i < SatMR_NSYM; i++)
         m_dbuf[i][ptr] = px[i];
      m_dptr = (ptr + 1) % SatMR_RING;
      m_dcount++;

      int st_prev[SatMR_NSYM];
      for(int i = 0; i < SatMR_NSYM; i++)
         st_prev[i] = m_st[i];

      int base = m_dptr - 1;                       // newest daily row

      // ---- FX leg: z = (px - SMA_L)/SD_L, hysteresis machine ----
      for(int i = 0; i < SatMR_NFX; i++)
        {
         double zt = SatNan();
         if(m_dcount >= m_L)                       // _win(s, L) exists
           {
            // pass 1: NaN check over the 60-row window incl. today
            bool has_nan = false;
            for(int j = 0; j < m_L; j++)
              {
               double v = m_dbuf[i][Wrap(base - j)];
               if(v != v)
                 {
                  has_nan = true;
                  break;
                 }
              }
            if(!has_nan)
              {
               // two-pass mean/sd, summation NEWEST -> OLDEST
               // (Python iterates the newest-first _win list)
               double tot = 0.0;
               for(int j = 0; j < m_L; j++)
                  tot += m_dbuf[i][Wrap(base - j)];
               double mean = tot / m_L;
               double acc = 0.0;
               for(int j = 0; j < m_L; j++)
                 {
                  double dv = m_dbuf[i][Wrap(base - j)] - mean;
                  acc += dv * dv;
                 }
               double sd = MathSqrt(acc / (m_L - 1));  // ddof=1
               zt = SatNpDiv(px[i] - mean, sd);
              }
           }
         int st = m_st[i];
         if(SatIsFinite(zt))                       // inf (sd==0) skipped
           {
            if(st == 0)
              {
               if(zt > m_z_in)
                  st = -1;
               else if(zt < -m_z_in)
                  st = 1;
              }
            else if((st == -1 && zt < m_z_out) ||
                    (st == 1 && zt > -m_z_out))
               st = 0;
           }
         m_st[i] = st;
        }

      // ---- Index leg: vol-scaled D-day dip, long-only ----
      for(int gi = SatMR_NFX; gi < SatMR_NSYM; gi++)
        {
         int hi = gi - SatMR_NFX;                  // held index
         double zt = SatNan();
         if(m_dcount >= 1 + m_D)                   // _win(s,1,back=D)
           {
            double p5 = m_dbuf[gi][Wrap(base - m_D)];   // px[t-D]
            if(p5 == p5 && px[gi] == px[gi])
              {
               double pct = px[gi] / p5 - 1.0;
               zt = SatNpDiv(pct, vol[gi] * m_sqrt_d);
              }
           }
         bool tv = false;                          // trend = px > SMA200
         if(m_dcount >= m_trend_L)
           {
            bool has_nan = false;
            for(int j = 0; j < m_trend_L; j++)
              {
               double v = m_dbuf[gi][Wrap(base - j)];
               if(v != v)
                 {
                  has_nan = true;
                  break;
                 }
              }
            if(!has_nan)
              {
               double tot = 0.0;
               for(int j = 0; j < m_trend_L; j++)
                  tot += m_dbuf[gi][Wrap(base - j)];
               double sma = tot / m_trend_L;
               tv = (px[gi] > sma);
              }
           }
         int st = m_st[gi];
         if(SatIsFinite(zt))
           {
            if(st == 0)
              {
               if(zt < -m_z_entry && tv)
                 {
                  st = 1;
                  m_held[hi] = 0;
                 }
              }
            else
              {
               m_held[hi]++;
               if(zt > m_z_exit || m_held[hi] >= m_max_hold)
                  st = 0;
              }
           }
         m_st[gi] = st;
        }

      // ---- size frozen at entry, per-inst cap, sleeve gross cap ----
      double pos_c[SatMR_NSYM];
      for(int i = 0; i < SatMR_NSYM; i++)
        {
         double v  = vol[i];
         // clip(lower=floor): NaN passes through
         double vc = (v != v || v > m_vol_floor) ? v : m_vol_floor;
         double wgt = m_K / vc;
         int st = m_st[i];
         if(st != 0 && (first_row || st_prev[i] != st))
            m_size[i] = wgt;                       // FROZEN at entry
         double pr = st * m_size[i];
         if(pr > m_pos_cap)
            pr = m_pos_cap;
         else if(pr < -m_pos_cap)
            pr = -m_pos_cap;
         pos_c[i] = pr;
        }
      double gross = 0.0;
      for(int i = 0; i < SatMR_NSYM; i++)          // SatMR_SYMBOLS order
         gross += MathAbs(pos_c[i]);
      double scale = SatNpDiv(m_gross_cap, gross);
      if(scale > 1.0)                    // clip(upper=1): inf -> 1, NaN stays
         scale = 1.0;

      // effective at the first hourly bar >= (d+1) 13:00 (EXEC_LAG=14)
      datetime eff = (datetime)((day + 1) * 86400
                                + (long)(m_exec_lag - 1) * 3600);
      if(m_pend_count < SatMR_MAX_PEND)            // never binds (<~2)
        {
         int k = m_pend_count;
         m_pend_eff[k] = eff;
         for(int i = 0; i < SatMR_NSYM; i++)
            m_pend_pos[k][i] = pos_c[i] * scale;
         m_pend_count++;
        }
     }
  };

#endif // SAT_MEANREV_MQH
