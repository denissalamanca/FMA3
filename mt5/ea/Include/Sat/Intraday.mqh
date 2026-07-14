//+------------------------------------------------------------------+
//| Intraday.mqh — FMA3 v34 intraday sleeve stepper (USA500/USTEC)   |
//|                                                                  |
//| 1:1 MQL5 port of the Wave-1 validated Python stepper             |
//|   research/bpure/steppers/intraday_stepper.py                    |
//| (state-exact vs the frozen golden; see research/bpure/parity/).  |
//| Every constant, branch, guard and NaN rule is preserved verbatim.|
//|                                                                  |
//| Sleeve recap (frozen params): USA500 + USTEC "open-drive".       |
//|   entry_hour=16, exit_hour=21 (server GMT+2/+3, NY-anchored)     |
//|   mv  = close[h16]/close[h15] - 1            (per day, real bars)|
//|   sc  = ewm(|mv|, span=60, adjust=True, ignore_na=False,         |
//|         min_periods=20).shift(1)  over the mv DAY index          |
//|   z   = clip(mv/sc, -2, 2) / 2                                   |
//|   w   = clip(0.15 / vol_d, upper=1.0)                            |
//|   sig = clip(z * w * 1.111, -1, 1)                               |
//|   pos = nan_to_num(sig) on grid rows with hour in [16, 21),      |
//|         else 0.0 (set REGARDLESS of has_bar on the hold rows)    |
//|                                                                  |
//| Grid / daily semantics (verbatim from the stepper docstring):    |
//|  * vol30: ret^2 .ewm(span=720, adjust=True, min_periods=0).mean()|
//|    over the ALL-universe UNION hourly grid (ffilled closes;      |
//|    ret=0 on stale/first rows; ret clipped to +-0.30);            |
//|    vol = sqrt(var * 24.0 * 365.25).  EVERY union-grid row is one |
//|    ewm step — including weekend rows created by crypto symbols.  |
//|  * vol_d = vol.resample('1D').last().shift(1): CONTIGUOUS        |
//|    calendar-day grid, so the vol used on day d is the LAST hourly|
//|    vol of calendar day d-1, and it is NaN when day d-1 had no    |
//|    grid rows at all.                                             |
//|  * The mv day index = union of days having an hour-15 bar OR an  |
//|    hour-16 bar.  Every such day is one ewm step for sc; a day    |
//|    with only one of the two bars contributes a NaN step (weights |
//|    decay, nobs unchanged — ignore_na=False).  Days with neither  |
//|    bar are NOT steps.                                            |
//|  * sc.shift(1): the scale used at day d's entry is the ewm state |
//|    BEFORE committing day d — the stepper reads its sc state at   |
//|    the hour-16 bar and commits day d's mv step at day rollover.  |
//|                                                                  |
//| API (per-bar, both symbols together, one union-grid hourly bar): |
//|   CSatIntradayStepper st;                                        |
//|   st.Init(symbols);                 // or InitDefault()          |
//|   st.StepNs(ts_ns, closes, pos);    // ts_ns: int64 nanoseconds  |
//|                                     // since epoch, naive broker |
//|                                     // SERVER time (== the frozen|
//|                                     // grid index.asi8 values)   |
//|   st.Step(dt, closes, pos);         // datetime (server seconds) |
//|                                     // convenience: ts_ns=dt*1e9 |
//|   closes[i]: RAW (un-ffilled) close of m_symbols[i] on this      |
//|     union-grid row, or NaN when the symbol has no bar here       |
//|     (has_bar False).  Missing trailing entries read as NaN       |
//|     (Python closes.get(s, NAN)).                                 |
//|   pos[i]: frozen-matrix position for THIS bar (the harness holds |
//|     pos[t] over bar t+1 — same convention as the golden parquet).|
//|                                                                  |
//| State (GetState/SetState) mirrors the Python state dict          |
//| field-for-field for live warm-start serialization:               |
//|   Python {"cur_day": int|None, "symbols": {s: {...}}}  ==        |
//|   (has_cur_day,cur_day) + SSatIntradaySymState[] in m_symbols    |
//|   order (has_cur_day=false <=> cur_day is None).                 |
//|                                                                  |
//| NOTE: the Python log_entries/entry_log diagnostic (validation    |
//| only, no effect on state or output) is intentionally not ported. |
//+------------------------------------------------------------------+
#ifndef SAT_INTRADAY_MQH
#define SAT_INTRADAY_MQH

#include <Sat/SatMath.mqh>

// integer nanosecond grid constants (Python DAY_NS / HOUR_NS)
const long Sat_INTRADAY_DAY_NS  = 86400000000000;   // 86_400_000_000_000
const long Sat_INTRADAY_HOUR_NS = 3600000000000;    //  3_600_000_000_000

//------------------------------------------------------------------//
// per-symbol state — field-for-field mirror of _new_sym_state()    //
//------------------------------------------------------------------//
struct SSatIntradaySymState
  {
   // ffilled close & realized-vol ewm (span 720, adjust=True) accumulators
   double            prev_close;   // last ffilled close (NaN before first bar)
   double            vol_num;      // sum f^(t-i) ret_i^2
   double            vol_den;      // sum f^(t-i)
   double            vol;          // current annualized vol (this bar)
   // vol_d (resample 1D last, shift 1): vol effective for the CURRENT day
   double            w_vol;
   // sc ewm (span 60, adjust=True, ignore_na=False, min_periods=20)
   double            sc_num;
   double            sc_den;
   long              sc_nobs;
   // intra-day scratch
   double            c15;          // today's hour-15 real-bar close
   bool              has15;        // today has an hour-15 bar (has_bar)
   bool              has16;        // today has an hour-16 bar (has_bar)
   double            mv_pending;   // today's open move (committed at rollover)
   double            sig;          // today's signal (NaN -> position 0)
  };

//------------------------------------------------------------------//
// CSatIntradayStepper — steps BOTH sleeve symbols together, one    //
// union-grid hourly bar at a time (IntradayStepper 1:1).           //
//------------------------------------------------------------------//
class CSatIntradayStepper
  {
public:
   // --- config (frozen PARAMS; public for inspection) ---
   string            m_symbols[];
   int               m_nsym;
   int               m_entry_hour;
   int               m_exit_hour;
   double            m_zcap;
   double            m_ref_vol;
   double            m_scale;
   double            m_ret_clip;
   int               m_sc_min_periods;
   double            m_f_vol;      // 1 - 2/(720+1)
   double            m_f_sc;       // 1 - 2/(60+1)
   double            m_ann;        // bars_per_day = 24.0
   // --- serializable state ---
   bool              m_has_day;    // false <=> Python cur_day is None
   long              m_cur_day;    // int ts_ns // DAY_NS
   SSatIntradaySymState m_st[];

                     CSatIntradayStepper() { m_nsym = 0; m_has_day = false; m_cur_day = 0; }

   //--------------------------------------------------------------- init
   // Defaults == frozen PARAMS of intraday_stepper.py (overridable
   // exactly like the Python **overrides kwargs).
   void              Init(const string &symbols[],
                          const int    entry_hour      = 16,
                          const int    exit_hour       = 21,
                          const double zcap            = 2.0,
                          const double span_days       = 60.0,
                          const double ref_vol         = 0.15,
                          const double scale           = 1.111,
                          const double vol_span_days   = 30.0,
                          const double bars_per_day    = 24.0,
                          const double ret_clip        = 0.30,
                          const int    sc_min_periods  = 20)
     {
      m_nsym = ArraySize(symbols);
      ArrayResize(m_symbols, m_nsym);
      for(int i = 0; i < m_nsym; i++)
         m_symbols[i] = symbols[i];
      m_entry_hour     = entry_hour;
      m_exit_hour      = exit_hour;
      m_zcap           = zcap;
      m_ref_vol        = ref_vol;
      m_scale          = scale;
      m_ret_clip       = ret_clip;
      m_sc_min_periods = sc_min_periods;
      int vol_span = (int)(vol_span_days * bars_per_day);          // 720
      m_f_vol = 1.0 - 2.0 / (vol_span + 1.0);
      m_f_sc  = 1.0 - 2.0 / (span_days + 1.0);
      m_ann   = bars_per_day;                                      // 24.0
      m_has_day = false;                                           // cur_day = None
      m_cur_day = 0;
      ArrayResize(m_st, m_nsym);
      for(int i = 0; i < m_nsym; i++)
         ResetSymState(m_st[i]);
     }

   // frozen sleeve universe: SYMBOLS = ("USA500", "USTEC")
   void              InitDefault()
     {
      string syms[2];
      syms[0] = "USA500";
      syms[1] = "USTEC";
      Init(syms);
     }

   //-------------------------------------------------------------- state
   // Python get_state(): {"cur_day": ..., "symbols": {...}}
   void              GetState(bool &has_cur_day, long &cur_day,
                              SSatIntradaySymState &syms[]) const
     {
      has_cur_day = m_has_day;
      cur_day     = m_cur_day;
      ArrayResize(syms, m_nsym);
      for(int i = 0; i < m_nsym; i++)
         syms[i] = m_st[i];
     }

   // Python set_state(d) — syms[] must be in m_symbols order
   void              SetState(const bool has_cur_day, const long cur_day,
                              const SSatIntradaySymState &syms[])
     {
      m_has_day = has_cur_day;
      m_cur_day = cur_day;
      for(int i = 0; i < m_nsym; i++)
         m_st[i] = syms[i];
     }

   //--------------------------------------------------------------- step
   // datetime convenience wrapper (server-time seconds -> ns)
   void              Step(const datetime t, const double &closes[],
                          double &pos_out[])
     {
      StepNs(((long)t) * 1000000000, closes, pos_out);
     }

   // step(ts_ns, closes) -> {sym: position}
   void              StepNs(const long ts_ns, const double &closes[],
                            double &pos_out[])
     {
      long day  = ts_ns / Sat_INTRADAY_DAY_NS;    // ts_ns >= 0 on the grid
      long hour = (ts_ns - day * Sat_INTRADAY_DAY_NS) / Sat_INTRADAY_HOUR_NS;
      if(!m_has_day)
        {
         m_cur_day = day;
         m_has_day = true;
        }
      else if(day != m_cur_day)
        {
         RollDay(day);
         m_cur_day = day;
        }

      ArrayResize(pos_out, m_nsym);
      int ncl = ArraySize(closes);
      for(int i = 0; i < m_nsym; i++)
        {
         double raw = (i < ncl) ? closes[i] : SatNan();   // closes.get(s, NAN)
         bool has_bar = SatIsObs(raw);
         double cf = has_bar ? raw : m_st[i].prev_close;

         // ret on the union grid: 0 before the first bar, else clipped
         // pct-change of the ffilled close (0 on stale rows by identity).
         double prev = m_st[i].prev_close;
         double r;
         if(SatIsObs(prev))
           {
            r = cf / prev - 1.0;
            if(r > m_ret_clip)
               r = m_ret_clip;
            else if(r < -m_ret_clip)
               r = -m_ret_clip;
           }
         else
            r = 0.0;
         m_st[i].prev_close = cf;

         // realized-vol ewm: EVERY grid row is one observation (ret never
         // NaN in the frozen frame). adjust=True num/den recurrence.
         m_st[i].vol_num = m_st[i].vol_num * m_f_vol + r * r;
         m_st[i].vol_den = m_st[i].vol_den * m_f_vol + 1.0;
         double var = m_st[i].vol_num / m_st[i].vol_den;
         m_st[i].vol = MathSqrt(var * m_ann * 365.25);

         if(has_bar)
           {
            if(hour == m_entry_hour - 1)
              {
               m_st[i].c15   = raw;
               m_st[i].has15 = true;
              }
            else if(hour == m_entry_hour)
              {
               m_st[i].has16 = true;
               double mv = m_st[i].has15 ? (raw / m_st[i].c15 - 1.0) : SatNan();
               m_st[i].mv_pending = mv;
               // sc.shift(1): ewm state BEFORE today's commit, gated on
               // min_periods (nobs as of the end of the previous mv day).
               double sc;
               if(m_st[i].sc_nobs >= m_sc_min_periods && m_st[i].sc_den > 0.0)
                  sc = m_st[i].sc_num / m_st[i].sc_den;
               else
                  sc = SatNan();
               double z_raw = (SatIsObs(mv) && SatIsObs(sc)) ? SatNpDiv(mv, sc)
                                                             : SatNan();
               double z;
               if(SatIsObs(z_raw))
                 {
                  double zc = z_raw;
                  if(zc > m_zcap)
                     zc = m_zcap;
                  else if(zc < -m_zcap)
                     zc = -m_zcap;
                  z = zc / m_zcap;
                 }
               else
                  z = SatNan();
               double wv = m_st[i].w_vol;
               double w;
               if(SatIsObs(wv))
                 {
                  double q = SatNpDiv(m_ref_vol, wv);   // inf when wv == 0
                  w = (q <= 1.0) ? q : 1.0;             // clip(upper=1.0)
                 }
               else
                  w = SatNan();
               double sig;
               if(SatIsObs(z) && SatIsObs(w))
                 {
                  double sv = (z * w) * m_scale;
                  sig = (sv < -1.0) ? -1.0 : ((sv > 1.0) ? 1.0 : sv);
                 }
               else
                  sig = SatNan();
               m_st[i].sig = sig;
              }
           }

         // position matrix value for THIS bar: hold rows get
         // nan_to_num(sig) irrespective of has_bar; all others 0.
         if(m_entry_hour <= hour && hour < m_exit_hour)
           {
            double v = m_st[i].sig;
            pos_out[i] = SatIsObs(v) ? v : 0.0;
           }
         else
            pos_out[i] = 0.0;
        }
     }

private:
   //----------------------------------------------------------- internals
   void              ResetSymState(SSatIntradaySymState &st)
     {
      double nan = SatNan();
      st.prev_close = nan;
      st.vol_num    = 0.0;
      st.vol_den    = 0.0;
      st.vol        = nan;
      st.w_vol      = nan;
      st.sc_num     = 0.0;
      st.sc_den     = 0.0;
      st.sc_nobs    = 0;
      st.c15        = nan;
      st.has15      = false;
      st.has16      = false;
      st.mv_pending = nan;
      st.sig        = nan;
     }

   // _roll_day(new_day): finalize the day that just ended, every symbol
   void              RollDay(const long new_day)
     {
      bool gap1 = (new_day == m_cur_day + 1);
      double nan = SatNan();
      for(int i = 0; i < m_nsym; i++)
        {
         // (a) commit the ended day's mv ewm step (iff it was an mv-index
         //     day: had an hour-15 or hour-16 bar). ignore_na=False: decay
         //     weights on every step; add only on a real mv observation.
         if(m_st[i].has15 || m_st[i].has16)
           {
            m_st[i].sc_num *= m_f_sc;
            m_st[i].sc_den *= m_f_sc;
            double mv = m_st[i].mv_pending;
            if(SatIsObs(mv))
              {
               m_st[i].sc_num += MathAbs(mv);
               m_st[i].sc_den += 1.0;
               m_st[i].sc_nobs++;
              }
           }
         // (b) vol_d = resample('1D').last().shift(1): vol effective on the
         //     new day = last hourly vol of the immediately preceding
         //     CALENDAR day (NaN if that day had no grid rows).
         m_st[i].w_vol = gap1 ? m_st[i].vol : nan;
         // (c) reset intra-day scratch
         m_st[i].c15        = nan;
         m_st[i].has15      = false;
         m_st[i].has16      = false;
         m_st[i].mv_pending = nan;
         m_st[i].sig        = nan;
        }
     }
  };

#endif // SAT_INTRADAY_MQH
