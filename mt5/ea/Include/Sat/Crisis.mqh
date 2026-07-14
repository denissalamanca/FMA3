//+------------------------------------------------------------------+
//| Crisis.mqh — FMA3 v34 crisis sleeve stepper (CSatCrisisStepper)  |
//|                                                                  |
//| 1:1 MQL5 port of the Wave-1 validated Python stepper             |
//| research/bpure/steppers/crisis_stepper.py (state-exact vs frozen |
//| goldens; SPEC = model/v3/freeze/FMA3-v34-freeze-1 crisis.py).    |
//| Every constant, branch, guard and NaN rule is preserved verbatim.|
//|                                                                  |
//| DAILY GRID SEMANTICS (caller contract, from the Python spec):    |
//|   The stepper consumes ONE row per Step() of the weekday-filtered|
//|   CALENDAR-day close grid: union-hourly ffilled closes resampled |
//|   1D-last, Sat/Sun dropped, Mon-Fri HOLIDAYS KEPT (their stale   |
//|   ffilled closes produce exact 0.0 returns).  NaN closes are     |
//|   allowed before a symbol's first bar (and propagate as NaN      |
//|   returns; prev_close only updates on an observed close —       |
//|   pandas pct_change pad semantics).                              |
//|                                                                  |
//| PER-BAR API:                                                     |
//|   bool Step(const datetime ts, const double &closes[],           |
//|             SSatCrisisResult &res)                                |
//|     ts       server-day stamp of the daily row (00:00 that day). |
//|     closes[] EXACTLY SatCRISIS_NIN (=10) values in               |
//|              SatCrisisInputSym() order:                          |
//|                0..5  DAX JP225 UK100 US30 USA500 USTEC (INDICES) |
//|                6     XAUUSD                                      |
//|                7..9  AUDJPY NZDJPY CADJPY (JPX)                  |
//|     res.w[]  SatCRISIS_NOUT (=4) target weights in               |
//|              SatCrisisSym() order: XAUUSD AUDJPY NZDJPY CADJPY;  |
//|              NaN = "no target yet: hold previous target".        |
//|     res.effective = ts + 1d + 13h (Python _EFFECT_SHIFT_NS =     |
//|              +1 day + (_TRADE_LAG_H-1) hours, in seconds here):  |
//|              when the target becomes effective on the hourly     |
//|              grid.  pandas ffill semantics = a NaN target is     |
//|              skipped, the previous target persists (see          |
//|              SatCrisisExpandToHourly).                           |
//|     res also carries every Python diag field for parity checks.  |
//|                                                                  |
//| STATE (live warm-start): GetState()/SetState() serialize a flat  |
//| double array mirroring the Python state dict FIELD-FOR-FIELD in  |
//| dict order (layout documented at SatCRISIS_STATE_SIZE below).    |
//| SetState assumes a constructed stepper (ring windows fixed).     |
//+------------------------------------------------------------------+
#ifndef SAT_CRISIS_MQH
#define SAT_CRISIS_MQH

#include <Sat/SatMath.mqh>

//==================================================================//
// frozen parameters (crisis.py — verbatim)                         //
//==================================================================//
#define SatCRISIS_V0            1.25      // vr trigger
#define SatCRISIS_D0            0.05      // dd trigger (dd < -D0)
#define SatCRISIS_FX_V0         1.20      // fvr trigger
#define SatCRISIS_K_AU          0.30      // gold risk budget
#define SatCRISIS_K_JP          0.25      // jpy sleeve risk budget
#define SatCRISIS_SMOOTH_SPAN   3         // ewm span of stress scores

#define SatCRISIS_VOL_WIN_S     10
#define SatCRISIS_VOL_WIN_L     60
#define SatCRISIS_DD_WIN        126
#define SatCRISIS_MA_WIN        50
#define SatCRISIS_MA_MINP       20
#define SatCRISIS_DD_MINP       20
#define SatCRISIS_SIZE_SPAN     250
#define SatCRISIS_SIZE_MINP     60
#define SatCRISIS_VOL_FLOOR     0.05
#define SatCRISIS_GRID          0.02
#define SatCRISIS_TRADE_LAG_H   14        // effective next day 13:00 UTC
#define SatCRISIS_GROSS_CAP     3.0
#define SatCRISIS_POS_CAP       1.0

#define SatCRISIS_NIDX          6         // equity indices
#define SatCRISIS_NJPX          3         // jpy crosses
#define SatCRISIS_NOUT          4         // traded symbols (XAU + JPX)
#define SatCRISIS_NIN           10        // step() input row width

// input-row index of XAUUSD / first JPX symbol
#define SatCRISIS_IX_XAU        6
#define SatCRISIS_IX_JPX0       7

// Python: _EFFECT_SHIFT_NS = 1 day + (_TRADE_LAG_H - 1) hours (ns).
// MQL5 datetime is seconds: +1d +13h = 133200 s.
#define SatCRISIS_EFFECT_SHIFT_SEC  (86400 + (SatCRISIS_TRADE_LAG_H - 1) * 3600)

// sqrt(252) — MathSqrt is exact/deterministic, same double as Python's
// module-level math.sqrt(252.0)
double SatCrisisSqrt252() { return MathSqrt(252.0); }

// symbol-name helpers (fixed orders from the Python spec)
string SatCrisisInputSym(const int i)
  {
   string names[SatCRISIS_NIN] =
     {"DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
      "XAUUSD", "AUDJPY", "NZDJPY", "CADJPY"};
   return names[i];
  }
string SatCrisisSym(const int j)
  {
   string names[SatCRISIS_NOUT] =
     {"XAUUSD", "AUDJPY", "NZDJPY", "CADJPY"};
   return names[j];
  }

//==================================================================//
// serialized state layout (flat double array, Python dict order):  //
//   [  0.. 9]  prev_close (INPUT_SYMS order, 10)                   //
//   [ 10.. 71] br_ring    buf[60] raw, head, count                 //
//   [ 72]      lev                                                 //
//   [ 73..200] lev_ring   buf[126] raw, head, count                //
//   [201..203] ewm_seq    avg, old_wt, nobs                        //
//   [204..265] fr_ring    buf[60] raw, head, count                 //
//   [266]      flev                                                //
//   [267..318] flev_ring  buf[50] raw, head, count                 //
//   [319..321] ewm_sfx    avg, old_wt, nobs                        //
//   [322..373] au_ring    buf[50] raw, head, count                 //
//   [374..397] vol_ewm    4 x (mean, cov, sum_wt, sum_wt2,         //
//                              old_wt, nobs)  SYMS order           //
//   [398]      n_steps                                             //
//==================================================================//
#define SatCRISIS_STATE_SIZE  (SatCRISIS_NIN                        \
                               + (SatCRISIS_VOL_WIN_L + 2)          \
                               + 1                                  \
                               + (SatCRISIS_DD_WIN + 2)             \
                               + 3                                  \
                               + (SatCRISIS_VOL_WIN_L + 2)          \
                               + 1                                  \
                               + (SatCRISIS_MA_WIN + 2)             \
                               + 3                                  \
                               + (SatCRISIS_MA_WIN + 2)             \
                               + SatCRISIS_NOUT * 6                 \
                               + 1)                        /* 399 */

//==================================================================//
// SSatCrisisResult — Step() output: w + effective stamp + the      //
// full Python diag dict (field-for-field) for parity checks.       //
// Python's level[s] = None maps to has_level[j] = false.           //
//==================================================================//
struct SSatCrisisResult
  {
   double            w[SatCRISIS_NOUT];        // target weights, SYMS order
   datetime          effective;                // ts + 1d + 13h
   // ---- diag (same names/values as the Python diag dict) ----
   double            br;
   double            vr;
   double            lev;
   double            dd;
   int               trig_eq;
   double            s_eq;
   double            fr;
   double            fvr;
   double            flev;
   double            fma;
   int               trig_fx;
   double            s_fx;
   double            au_ma;
   int               up_au;
   double            vol[SatCRISIS_NOUT];
   double            w_pre[SatCRISIS_NOUT];
   long              level[SatCRISIS_NOUT];    // valid iff has_level[j]
   bool              has_level[SatCRISIS_NOUT];
   double            gross;
   double            scale;
  };

//==================================================================//
// CSatCrisisStepper — one Step() per weekday calendar-day row      //
//==================================================================//
class CSatCrisisStepper
  {
public:
   // --- state (public: mirrors the Python attributes 1:1) ---
   double            m_prev_close[SatCRISIS_NIN];
   // equity stress
   CSatRing          m_br_ring;                // window 60
   double            m_lev;
   CSatRing          m_lev_ring;               // window 126
   CSatEwmMean       m_ewm_seq;                // span 3, minp 1
   // fx stress
   CSatRing          m_fr_ring;                // window 60
   double            m_flev;
   CSatRing          m_flev_ring;              // window 50
   CSatEwmMean       m_ewm_sfx;                // span 3, minp 1
   // gold trend
   CSatRing          m_au_ring;                // window 50
   // sizing vols (SYMS order)
   CSatEwmStd        m_vol_ewm[SatCRISIS_NOUT];// span 250, minp 60, zsqrt
   long              m_n_steps;

                     CSatCrisisStepper() { Reset(); }

   void              Reset()
     {
      double nan = SatNan();
      for(int i = 0; i < SatCRISIS_NIN; i++)
         m_prev_close[i] = nan;
      m_br_ring.Init(SatCRISIS_VOL_WIN_L);
      m_lev = 1.0;
      m_lev_ring.Init(SatCRISIS_DD_WIN);
      m_ewm_seq.Init((double)SatCRISIS_SMOOTH_SPAN, 1);
      m_fr_ring.Init(SatCRISIS_VOL_WIN_L);
      m_flev = 1.0;
      m_flev_ring.Init(SatCRISIS_MA_WIN);
      m_ewm_sfx.Init((double)SatCRISIS_SMOOTH_SPAN, 1);
      m_au_ring.Init(SatCRISIS_MA_WIN);
      for(int j = 0; j < SatCRISIS_NOUT; j++)
         m_vol_ewm[j].Init((double)SatCRISIS_SIZE_SPAN,
                           SatCRISIS_SIZE_MINP, true); // crisis zsqrt flavor
      m_n_steps = 0;
     }

   //---------------------------------------------------------------
   // one daily bar, ALL symbols together (verbatim Python step())
   // closes[] = SatCRISIS_NIN values in SatCrisisInputSym() order.
   // Returns false only on a malformed closes[] size.
   //---------------------------------------------------------------
   bool              Step(const datetime ts, const double &closes[],
                          SSatCrisisResult &res)
     {
      if(ArraySize(closes) < SatCRISIS_NIN)
         return false;
      double nan = SatNan();
      double sqrt252 = SatCrisisSqrt252();
      m_n_steps++;

      // daily simple returns  r = c/prev - 1  (NaN if either side missing)
      double r[SatCRISIS_NIN];
      for(int i = 0; i < SatCRISIS_NIN; i++)
        {
         double c = closes[i];
         double p = m_prev_close[i];
         r[i] = (c == c && p == p) ? (c / p - 1.0) : nan;
         if(c == c)                       // pct_change pad semantics
            m_prev_close[i] = c;
        }

      // ---- equity stress score ----
      // br = row mean over INDICES (skipna, column order)
      double sm = 0.0;
      int    k  = 0;
      for(int i = 0; i < SatCRISIS_NIDX; i++)
        {
         double v = r[i];
         if(v == v)
           {
            sm += v;
            k++;
           }
        }
      double br = (k > 0) ? (sm / k) : nan;

      m_br_ring.Push(br);
      double s10 = m_br_ring.StdDdof1(SatCRISIS_VOL_WIN_S, SatCRISIS_VOL_WIN_S);
      double s60 = m_br_ring.StdDdof1(SatCRISIS_VOL_WIN_L, SatCRISIS_VOL_WIN_L);
      double vr = (s10 == s10 && s60 == s60)
                  ? ((s10 * sqrt252) / (s60 * sqrt252)) : nan;

      m_lev = m_lev * (1.0 + ((br == br) ? br : 0.0));
      m_lev_ring.Push(m_lev);
      double lmax = m_lev_ring.Max(SatCRISIS_DD_WIN, SatCRISIS_DD_MINP);
      double dd = (lmax == lmax) ? (m_lev / lmax - 1.0) : nan;

      double trig_eq = ((vr == vr && vr > SatCRISIS_V0)
                        || (dd == dd && dd < -SatCRISIS_D0)) ? 1.0 : 0.0;
      double s_eq = m_ewm_seq.Step(trig_eq);

      // ---- fx stress score ----
      sm = 0.0;
      k  = 0;
      for(int i = SatCRISIS_IX_JPX0; i < SatCRISIS_IX_JPX0 + SatCRISIS_NJPX; i++)
        {
         double v = r[i];
         if(v == v)
           {
            sm += v;
            k++;
           }
        }
      double fr = (k > 0) ? (sm / k) : nan;

      m_fr_ring.Push(fr);
      double f10 = m_fr_ring.StdDdof1(SatCRISIS_VOL_WIN_S, SatCRISIS_VOL_WIN_S);
      double f60 = m_fr_ring.StdDdof1(SatCRISIS_VOL_WIN_L, SatCRISIS_VOL_WIN_L);
      double fvr = (f10 == f10 && f60 == f60)
                   ? ((f10 * sqrt252) / (f60 * sqrt252)) : nan;

      m_flev = m_flev * (1.0 + ((fr == fr) ? fr : 0.0));
      m_flev_ring.Push(m_flev);
      double fma = m_flev_ring.Mean(SatCRISIS_MA_WIN, SatCRISIS_MA_MINP);

      double trig_fx = ((fvr == fvr && fvr > SatCRISIS_FX_V0)
                        && (fma == fma && m_flev < fma)) ? 1.0 : 0.0;
      double s_fx = m_ewm_sfx.Step(trig_fx);

      // ---- gold own-trend qualifier ----
      double au = closes[SatCRISIS_IX_XAU];
      m_au_ring.Push(au);
      double au_ma = m_au_ring.Mean(SatCRISIS_MA_WIN, SatCRISIS_MA_MINP);
      double up_au = (au == au && au_ma == au_ma && au > au_ma) ? 1.0 : 0.0;

      // ---- slow sizing vol ----
      double vol[SatCRISIS_NOUT];
      for(int j = 0; j < SatCRISIS_NOUT; j++)
        {
         // SYMS order = input indices 6..9 (XAUUSD then JPX)
         double v = m_vol_ewm[j].Step(r[SatCRISIS_IX_XAU + j]);
         if(v == v)
           {
            v = v * sqrt252;
            if(v < SatCRISIS_VOL_FLOOR)          // clip(lower=0.05)
               v = SatCRISIS_VOL_FLOOR;
           }
         vol[j] = v;
        }

      // ---- raw weights (exact source op order) ----
      double w_pre[SatCRISIS_NOUT];
      double vx = vol[0];
      w_pre[0] = (vx == vx) ? ((s_eq * up_au) * (SatCRISIS_K_AU / vx)) : nan;
      double c_jp = SatCRISIS_K_JP / 3.0;
      for(int j = 1; j < SatCRISIS_NOUT; j++)
        {
         double v = vol[j];
         w_pre[j] = (v == v) ? (((-s_fx) * c_jp) / v) : nan;
        }

      // ---- hysteresis grid (banker), per-instrument cap ----
      for(int j = 0; j < SatCRISIS_NOUT; j++)
        {
         double x = w_pre[j];
         if(x == x)
           {
            double g = SatBankerRound(x / SatCRISIS_GRID);
            res.level[j]     = (long)g;
            res.has_level[j] = true;
            double y = g * SatCRISIS_GRID;
            if(y > SatCRISIS_POS_CAP)
               y = SatCRISIS_POS_CAP;
            else if(y < -SatCRISIS_POS_CAP)
               y = -SatCRISIS_POS_CAP;
            res.w[j] = y;
           }
         else
           {
            res.level[j]     = 0;                // Python: None
            res.has_level[j] = false;
            res.w[j] = nan;
           }
        }

      // ---- sleeve gross cap (skipna sum, column order SYMS) ----
      double gross = 0.0;
      for(int j = 0; j < SatCRISIS_NOUT; j++)
        {
         double y = res.w[j];
         if(y == y)
            gross += MathAbs(y);
        }
      double scale = (gross > 0.0) ? (SatCRISIS_GROSS_CAP / gross) : 1.0;
      if(scale > 1.0)
         scale = 1.0;
      for(int j = 0; j < SatCRISIS_NOUT; j++)
        {
         if(res.w[j] == res.w[j])
            res.w[j] = res.w[j] * scale;
        }

      // ---- assemble result / diag ----
      res.effective = (datetime)((long)ts + SatCRISIS_EFFECT_SHIFT_SEC);
      res.br      = br;
      res.vr      = vr;
      res.lev     = m_lev;
      res.dd      = dd;
      res.trig_eq = (int)trig_eq;
      res.s_eq    = s_eq;
      res.fr      = fr;
      res.fvr     = fvr;
      res.flev    = m_flev;
      res.fma     = fma;
      res.trig_fx = (int)trig_fx;
      res.s_fx    = s_fx;
      res.au_ma   = au_ma;
      res.up_au   = (int)up_au;
      for(int j = 0; j < SatCRISIS_NOUT; j++)
        {
         res.vol[j]   = vol[j];
         res.w_pre[j] = w_pre[j];
        }
      res.gross = gross;
      res.scale = scale;
      return true;
     }

   //---------------------------------------------------------------
   // GetState / SetState — flat double array, Python dict order
   // (layout at SatCRISIS_STATE_SIZE).  nobs/head/count/n_steps are
   // stored as doubles (exact for |v| < 2^53).
   //---------------------------------------------------------------
   int               GetState(double &st[]) const
     {
      ArrayResize(st, SatCRISIS_STATE_SIZE);
      int p = 0;
      for(int i = 0; i < SatCRISIS_NIN; i++)
         st[p++] = m_prev_close[i];
      PutRing(m_br_ring, st, p);
      st[p++] = m_lev;
      PutRing(m_lev_ring, st, p);
      PutEwmMean(m_ewm_seq, st, p);
      PutRing(m_fr_ring, st, p);
      st[p++] = m_flev;
      PutRing(m_flev_ring, st, p);
      PutEwmMean(m_ewm_sfx, st, p);
      PutRing(m_au_ring, st, p);
      for(int j = 0; j < SatCRISIS_NOUT; j++)
         PutEwmStd(m_vol_ewm[j], st, p);
      st[p++] = (double)m_n_steps;
      return p;                                  // == SatCRISIS_STATE_SIZE
     }

   bool              SetState(const double &st[])
     {
      if(ArraySize(st) < SatCRISIS_STATE_SIZE)
         return false;
      int p = 0;
      for(int i = 0; i < SatCRISIS_NIN; i++)
         m_prev_close[i] = st[p++];
      TakeRing(m_br_ring, st, p);
      m_lev = st[p++];
      TakeRing(m_lev_ring, st, p);
      TakeEwmMean(m_ewm_seq, st, p);
      TakeRing(m_fr_ring, st, p);
      m_flev = st[p++];
      TakeRing(m_flev_ring, st, p);
      TakeEwmMean(m_ewm_sfx, st, p);
      TakeRing(m_au_ring, st, p);
      for(int j = 0; j < SatCRISIS_NOUT; j++)
         TakeEwmStd(m_vol_ewm[j], st, p);
      m_n_steps = (long)st[p++];
      return true;
     }

private:
   static void       PutRing(const CSatRing &rg, double &st[], int &p)
     {
      for(int i = 0; i < rg.m_window; i++)
         st[p++] = rg.m_buf[i];                  // raw buffer, Python list(buf)
      st[p++] = (double)rg.m_head;
      st[p++] = (double)rg.m_count;
     }
   static void       TakeRing(CSatRing &rg, const double &st[], int &p)
     {
      for(int i = 0; i < rg.m_window; i++)
         rg.m_buf[i] = st[p++];
      rg.m_head  = (int)st[p++];
      rg.m_count = (int)st[p++];
     }
   static void       PutEwmMean(const CSatEwmMean &e, double &st[], int &p)
     {
      st[p++] = e.m_avg;
      st[p++] = e.m_old_wt;
      st[p++] = (double)e.m_nobs;
     }
   static void       TakeEwmMean(CSatEwmMean &e, const double &st[], int &p)
     {
      e.m_avg    = st[p++];
      e.m_old_wt = st[p++];
      e.m_nobs   = (long)st[p++];
     }
   static void       PutEwmStd(const CSatEwmStd &e, double &st[], int &p)
     {
      st[p++] = e.m_mean;
      st[p++] = e.m_cov;
      st[p++] = e.m_sum_wt;
      st[p++] = e.m_sum_wt2;
      st[p++] = e.m_old_wt;
      st[p++] = (double)e.m_nobs;
     }
   static void       TakeEwmStd(CSatEwmStd &e, const double &st[], int &p)
     {
      e.m_mean    = st[p++];
      e.m_cov     = st[p++];
      e.m_sum_wt  = st[p++];
      e.m_sum_wt2 = st[p++];
      e.m_old_wt  = st[p++];
      e.m_nobs    = (long)st[p++];
     }
  };

//==================================================================//
// SatCrisisExpandToHourly — verbatim port of expand_to_hourly:     //
// map daily targets (ALREADY shifted to their effective stamps)    //
// onto the hourly grid with pandas reindex-union-ffill semantics:  //
// at hour h the value is the LAST NON-NaN target with effective    //
// stamp <= h (NaN targets are skipped -> previous persists), NaN   //
// before the first -> 0.0 (fillna).  Stamps are opaque longs       //
// (seconds or ns — only <= comparisons are used).                  //
//==================================================================//
void SatCrisisExpandToHourly(const long &daily_eff[], const double &daily_w[],
                             const long &hourly[], double &out[])
  {
   int nh = ArraySize(hourly);
   int nd = ArraySize(daily_eff);
   ArrayResize(out, nh);
   int j = 0;
   double cur = SatNan();
   for(int i = 0; i < nh; i++)
     {
      while(j < nd && daily_eff[j] <= hourly[i])
        {
         double v = daily_w[j];
         if(v == v)
            cur = v;
         j++;
        }
      out[i] = (cur == cur) ? cur : 0.0;
     }
  }

#endif // SAT_CRISIS_MQH
