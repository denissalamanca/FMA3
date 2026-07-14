//+------------------------------------------------------------------+
//| MagXau.mqh — CV34MagXauStepper                                   |
//|                                                                  |
//| 1:1 MQL5 port of research/bpure/steppers/mag_xau_stepper.py      |
//| (Wave-1 validated: state-exact vs frozen goldens, gate           |
//| bit-identical).  Spec = frozen source model/v3/freeze/           |
//| FMA3-v34-freeze-1/src/research/ext_import/mag_xau.py.            |
//|                                                                  |
//| Gold $100 round-number magnet, XAUUSD only, long-only.           |
//|                                                                  |
//| Faithful pipeline replicated per bar (see Python docstring):     |
//|  1. daily mid : per SERVER-calendar-day LAST RAW close, trading  |
//|     days only (days with no XAUUSD bar produce NO daily stamp    |
//|     — mag_xau's daily grid is RAW-trading-days, NOT the ffilled  |
//|     calendar-day union grid).                                    |
//|  2. near      : ((d/STEP - OFFSET).round() + OFFSET) * STEP,     |
//|     .round() = BANKER half-to-even at 0 decimals                 |
//|     (V34BankerRound, same tie test as the Python).               |
//|  3. dist      : (d - near) / STEP                                |
//|  4. sig(SIDE>0): 1.0 if (dist < -MIND && dist > -BAND) else 0.0  |
//|  5. ann       : pct_change().rolling(VOL_WIN).std(ddof=1)        |
//|     * sqrt(252); min_periods = VOL_WIN; the leading pct_change   |
//|     NaN counts as a missing obs -> first valid ann needs         |
//|     VOL_WIN+1 daily mids.  Two-pass ddof=1 std over the ring     |
//|     (NOT naive sum-of-squares) — summation order oldest->newest  |
//|     preserved verbatim for bit-parity.                           |
//|  6. raw target: (sig*VT/ann).clip(-CAP, CAP); NaN while ann NaN. |
//|  7. to_hourly : daily stamp (day 00:00) shifted +1 day + 0 hours |
//|     -> effective at day+1 00:00; step-ffill onto the hourly      |
//|     union grid; a NaN stamped value does NOT overwrite (ffill    |
//|     keeps the previous target); position is 0.0 before the       |
//|     first finite target (.fillna(0.0)).                         |
//|                                                                  |
//| ---------------------------------------------------------------- |
//| PER-BAR API (mirrors MagXauStepper.step(ts_ns, closes); this     |
//| sleeve trades one symbol, so the closes dict collapses to one    |
//| scalar):                                                         |
//|                                                                  |
//|   double StepNs(const long ts_ns, const double close_raw)        |
//|     ts_ns    : bar timestamp in NANOSECONDS (server time, naive) |
//|                on the hourly union grid.  MUST be called for     |
//|                EVERY grid bar in order (even bars where XAUUSD   |
//|                printed no raw bar -> close_raw = NaN), because   |
//|                target effectiveness is a TIME (day+1 00:00),     |
//|                not a bar count.                                  |
//|     close_raw: RAW XAUUSD close for this grid hour, or NaN when  |
//|                the symbol printed no bar — NOT the ffilled       |
//|                close.                                            |
//|     returns  : the position target held over this bar            |
//|                (== Python step()["XAUUSD"]).                     |
//|                                                                  |
//|   double Step(const datetime t, const double close_raw)          |
//|     convenience wrapper: ts_ns = (long)t * 1e9 (MQL5 datetime is |
//|     epoch SECONDS; the Python ns grid is exactly seconds*1e9).   |
//|                                                                  |
//|   void FlushFinalDay()                                           |
//|     validation aid == Python flush_final_day(): finalize the     |
//|     still-open last day (its target stamps BEYOND the fed grid   |
//|     so positions are unaffected).                                |
//|                                                                  |
//| STATE (SV34MagXauState) mirrors the Python state dict            |
//| field-for-field for live warm-start:                             |
//|   version / sleeve            -> version, sleeve                 |
//|   mids                        -> mids[] (chronological, oldest   |
//|                                  first, <= VOL_WIN+1 entries)    |
//|   accum_day (None allowed)    -> has_accum_day + accum_day (ns)  |
//|   accum_close (None allowed)  -> accum_close (NaN encodes None)  |
//|   pending [[t, v-or-None],..] -> pending_ts[] + pending_tgt[]    |
//|                                  (NaN encodes None)              |
//|   current                     -> current                         |
//+------------------------------------------------------------------+
#ifndef FMA3V34_MAGXAU_MQH
#define FMA3V34_MAGXAU_MQH

#include <FMA3v34/V34Math.mqh>

//--- module constants (verbatim from mag_xau_stepper.py) -----------
const string V34MAGXAU_SYM     = "XAUUSD";
const double V34MAGXAU_STEP    = 100.0;
const double V34MAGXAU_BAND    = 0.18;
const double V34MAGXAU_MIND    = 0.03;
const double V34MAGXAU_OFFSET  = 0.0;
const double V34MAGXAU_SIDE    = 1.0;
const double V34MAGXAU_VT      = 0.15;
const double V34MAGXAU_CAP     = 6.0;
const int    V34MAGXAU_VOL_WIN = 20;
// DAY_NS = 86_400_000_000_000 (built by product: literal-safe)
const long   V34MAGXAU_DAY_NS  = (long)86400 * (long)1000000000;

//------------------------------------------------------------------//
// SV34MagXauState — field-for-field mirror of the Python state     //
// dict (get_state / from_state).  NaN encodes Python None for the  //
// nullable doubles; has_accum_day encodes `accum_day is None`.     //
//------------------------------------------------------------------//
struct SV34MagXauState
  {
   int               version;        // == 1
   string            sleeve;         // == "mag_xau"
   double            mids[];         // chronological, oldest first
   bool              has_accum_day;  // Python: accum_day is not None
   long              accum_day;      // day-start ns (valid iff has_accum_day)
   double            accum_close;    // NaN == Python None
   long              pending_ts[];   // effective ns stamps, FIFO order
   double            pending_tgt[];  // raw daily targets (NaN == None)
   double            current;        // live hourly position target
  };

//------------------------------------------------------------------//
// CV34MagXauStepper — see header comment for the API contract.     //
//------------------------------------------------------------------//
class CV34MagXauStepper
  {
public:
   // --- serializable state (public on purpose, like the primitives) ---
   double            m_mids[];          // last VOL_WIN+1 finalized daily mids
   bool              m_has_accum_day;   // accum_day is not None
   long              m_accum_day;       // day-start ns of the in-progress day
   double            m_accum_close;     // last raw close seen inside accum_day
   long              m_pend_ts[];       // pending effective stamps (FIFO)
   double            m_pend_tgt[];      // pending raw daily targets
   double            m_current;         // live hourly position target

                     CV34MagXauStepper() { Reset(); }

   void              Reset()
     {
      ArrayResize(m_mids, 0);
      m_has_accum_day = false;
      m_accum_day     = 0;
      m_accum_close   = V34Nan();
      ArrayResize(m_pend_ts, 0);
      ArrayResize(m_pend_tgt, 0);
      m_current       = 0.0;
     }

   //--- core: advance one hourly union-grid bar ---------------------
   double            StepNs(const long ts_ns, const double close_raw)
     {
      long day = (ts_ns / V34MAGXAU_DAY_NS) * V34MAGXAU_DAY_NS;

      // 1) a bar on a LATER day proves the accumulated day has closed
      if(m_has_accum_day && day > m_accum_day)
         FinalizeDay();

      // 2) apply any daily target whose effective stamp has been
      //    reached (ffill semantics: NaN stamped value does NOT
      //    overwrite)
      while(ArraySize(m_pend_ts) > 0 && m_pend_ts[0] <= ts_ns)
        {
         double tgt = m_pend_tgt[0];
         PopPendingFront();
         if(V34IsObs(tgt))
            m_current = tgt;
        }

      // 3) accumulate this bar's RAW close into the current server day
      if(V34IsObs(close_raw))
        {
         m_has_accum_day = true;
         m_accum_day     = day;
         m_accum_close   = close_raw;
        }

      // 4) held position over this bar
      return m_current;
     }

   // datetime convenience wrapper (MQL5 datetime = epoch seconds)
   double            Step(const datetime t, const double close_raw)
     {
      return StepNs((long)t * (long)1000000000, close_raw);
     }

   //--- validation aid == Python flush_final_day() ------------------
   void              FlushFinalDay()
     {
      if(m_has_accum_day && V34IsObs(m_accum_close))
         FinalizeDay();
     }

   //--- EA state (mirrors get_state / from_state) -------------------
   void              GetState(SV34MagXauState &out) const
     {
      out.version       = 1;
      out.sleeve        = "mag_xau";
      ArrayResize(out.mids, ArraySize(m_mids));
      if(ArraySize(m_mids) > 0)
         ArrayCopy(out.mids, m_mids);
      out.has_accum_day = m_has_accum_day;
      out.accum_day     = m_accum_day;
      out.accum_close   = m_accum_close;   // NaN encodes None
      ArrayResize(out.pending_ts,  ArraySize(m_pend_ts));
      ArrayResize(out.pending_tgt, ArraySize(m_pend_tgt));
      if(ArraySize(m_pend_ts) > 0)
        {
         ArrayCopy(out.pending_ts,  m_pend_ts);
         ArrayCopy(out.pending_tgt, m_pend_tgt);
        }
      out.current       = m_current;
     }

   void              SetState(const SV34MagXauState &in)
     {
      Reset();
      ArrayResize(m_mids, ArraySize(in.mids));
      if(ArraySize(in.mids) > 0)
         ArrayCopy(m_mids, in.mids);
      m_has_accum_day = in.has_accum_day;
      m_accum_day     = in.accum_day;
      m_accum_close   = in.accum_close;    // NaN == None
      ArrayResize(m_pend_ts,  ArraySize(in.pending_ts));
      ArrayResize(m_pend_tgt, ArraySize(in.pending_tgt));
      if(ArraySize(in.pending_ts) > 0)
        {
         ArrayCopy(m_pend_ts,  in.pending_ts);
         ArrayCopy(m_pend_tgt, in.pending_tgt);
        }
      m_current       = in.current;
     }

private:
   //--- close out the in-progress server day: compute the RAW daily
   //    target and stamp it effective at day+1 00:00
   //    (core.to_hourly lag_hours=1) — verbatim _finalize_day()
   void              FinalizeDay()
     {
      double mid = m_accum_close;
      long   day = m_accum_day;

      // mids.append(mid); if len > VOL_WIN+1: pop(0)
      int n = ArraySize(m_mids);
      ArrayResize(m_mids, n + 1);
      m_mids[n] = mid;
      n++;
      if(n > V34MAGXAU_VOL_WIN + 1)
        {
         for(int i = 0; i < n - 1; i++)
            m_mids[i] = m_mids[i + 1];
         n--;
         ArrayResize(m_mids, n);
        }

      // magnet signal off the day's own mid
      double near_lvl = (V34BankerRound(mid / V34MAGXAU_STEP - V34MAGXAU_OFFSET)
                         + V34MAGXAU_OFFSET) * V34MAGXAU_STEP;
      double dist = (mid - near_lvl) / V34MAGXAU_STEP;
      double sig;
      if(V34MAGXAU_SIDE > 0.0)
         sig = (dist < -V34MAGXAU_MIND && dist > -V34MAGXAU_BAND) ? 1.0 : 0.0;
      else
         sig = (dist > V34MAGXAU_MIND && dist < V34MAGXAU_BAND) ? -1.0 : 0.0;

      // ann vol: rolling(VOL_WIN).std(ddof=1) of daily pct_change,
      // TWO-PASS over the mids ring, oldest -> newest (order preserved)
      double ann;
      if(n >= V34MAGXAU_VOL_WIN + 1)
        {
         double mean = 0.0;
         int    base = n - V34MAGXAU_VOL_WIN - 1;
         double rets[];
         ArrayResize(rets, V34MAGXAU_VOL_WIN);
         for(int i = 0; i < V34MAGXAU_VOL_WIN; i++)
           {
            double r = m_mids[base + i + 1] / m_mids[base + i] - 1.0;
            rets[i] = r;
            mean += r;
           }
         mean /= (double)V34MAGXAU_VOL_WIN;
         double ss = 0.0;
         for(int i = 0; i < V34MAGXAU_VOL_WIN; i++)
           {
            double dv = rets[i] - mean;
            ss += dv * dv;
           }
         ann = MathSqrt(ss / (double)(V34MAGXAU_VOL_WIN - 1))
               * MathSqrt(252.0);
        }
      else
         ann = V34Nan();

      // raw daily target = (sig*VT/ann).clip(-CAP, CAP); NaN propagates
      double tgt;
      if(!V34IsObs(ann))
         tgt = V34Nan();
      else if(ann == 0.0)
        {
         // pandas float semantics: x/0 -> +-inf (then clipped),
         // 0/0 -> NaN
         double sv = sig * V34MAGXAU_VT;
         if(sv == 0.0)
            tgt = V34Nan();
         else
            tgt = (sv > 0.0) ? V34MAGXAU_CAP : -V34MAGXAU_CAP;
        }
      else
        {
         tgt = sig * V34MAGXAU_VT / ann;
         if(tgt > V34MAGXAU_CAP)
            tgt = V34MAGXAU_CAP;
         else if(tgt < -V34MAGXAU_CAP)
            tgt = -V34MAGXAU_CAP;
        }

      // pending.append((day + DAY_NS, tgt))
      int p = ArraySize(m_pend_ts);
      ArrayResize(m_pend_ts,  p + 1);
      ArrayResize(m_pend_tgt, p + 1);
      m_pend_ts[p]  = day + V34MAGXAU_DAY_NS;
      m_pend_tgt[p] = tgt;

      // accum_day = None; accum_close = NaN
      m_has_accum_day = false;
      m_accum_day     = 0;
      m_accum_close   = V34Nan();
     }

   //--- pending.pop(0) ----------------------------------------------
   void              PopPendingFront()
     {
      int p = ArraySize(m_pend_ts);
      for(int i = 0; i < p - 1; i++)
        {
         m_pend_ts[i]  = m_pend_ts[i + 1];
         m_pend_tgt[i] = m_pend_tgt[i + 1];
        }
      ArrayResize(m_pend_ts,  p - 1);
      ArrayResize(m_pend_tgt, p - 1);
     }
  };

#endif // FMA3V34_MAGXAU_MQH
