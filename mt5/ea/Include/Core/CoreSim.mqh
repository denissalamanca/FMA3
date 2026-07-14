//+------------------------------------------------------------------+
//| Core/CoreSim.mqh — Core IDEALIZED STANDALONE account shadow      |
//| (the a_h engine).                                                |
//|                                                                  |
//| Written from research/bpure/coresim/CORESIM_SPEC.md; the scalar  |
//| reference (coresim_reference.py) is BIT-EQUAL to the parity      |
//| target research/outputs/v7_book_equity_1m.parquet on all 32      |
//| committed segments (measured 2026-07-14, coresim_parity.json).   |
//|                                                                  |
//| WHAT THIS IS NOT: CoreEngine.mqh (the live real-account tracker).|
//| This is the NSF5 anchor account arithmetic — 9 fully separate    |
//| per-leg notional accounts, bar-open fills crossing the spread,   |
//| model commission/swap (both PRE-BAKED into the input arrays),    |
//| NOLIQ (stop-out 1e-9 = never), combined on the union 1m grid,    |
//| segment replay with FROZEN band-trigger dates + seed chaining.   |
//| No terminal calls, no CTrade — pure compute for Script use.      |
//|                                                                  |
//| Float discipline (spec section 5/7): expression groupings are    |
//| NORMATIVE — do not refactor a*b*c/d shapes, keep floor(x+1e-9)   |
//| lot quantizing, one-add balance updates. IEEE-754 binary64.      |
//+------------------------------------------------------------------+
#ifndef CORE_CORESIM_MQH
#define CORE_CORESIM_MQH

#define CORESIM_MARGIN_CAP     0.9
#define CORESIM_REBAL_BAND     0.25
#define CORESIM_STOP_OUT       1e-9      // noliq: guard must never fire
#define CORESIM_GROW           65536     // capture-array growth chunk

//====================================================================
// CCoreLegSim — one leg = one fully separate notional sub-account.
// Scalar port of NSF5 engine/backtest.py::_run_core, notional mode,
// dd_k=0 / throttle off / sl-tp never armed (branches structurally
// dead in the a_h configuration; the noliq stop-out check is kept as
// a hard error, spec section 5).
//====================================================================
class CCoreLegSim
{
private:
   // --- static config ---
   double m_contract, m_comm, m_lev, m_step, m_minlot;
   int    m_slotLegs;                  // legs in my slot (legcap divisor)
   // --- account state (reset every segment) ---
   double m_balance, m_pos, m_entry;
   double m_legcap;
   // --- captured per-bar series (this segment, in-window bars only) ---
   long   m_ts[];
   double m_c[], m_w[], m_m[];
   int    m_n;
   string m_err;

   bool Reserve(void)
     {
      if(m_n < ArraySize(m_ts)) return true;
      int want = ArraySize(m_ts) + CORESIM_GROW;
      if(ArrayResize(m_ts, want) != want) { m_err="ArrayResize ts";  return false; }
      if(ArrayResize(m_c,  want) != want) { m_err="ArrayResize c";   return false; }
      if(ArrayResize(m_w,  want) != want) { m_err="ArrayResize w";   return false; }
      if(ArrayResize(m_m,  want) != want) { m_err="ArrayResize m";   return false; }
      return true;
     }

public:
   void Configure(const int slot_legs, const double contract, const double comm,
                  const double lev, const double lot_step, const double min_lot)
     {
      m_slotLegs=slot_legs; m_contract=contract; m_comm=comm;
      m_lev=lev; m_step=lot_step; m_minlot=min_lot;
      m_n=0; m_balance=0.0; m_pos=0.0; m_entry=0.0; m_legcap=0.0; m_err="";
     }

   int    SlotLegs(void)   const { return m_slotLegs; }
   double LegCap(void)     const { return m_legcap;   }
   int    Bars(void)       const { return m_n;        }
   long   Ts(const int i)  const { return m_ts[i];    }
   double EqC(const int i) const { return m_c[i];     }
   double EqW(const int i) const { return m_w[i];     }
   double Mg(const int i)  const { return m_m[i];     }
   double Balance(void)    const { return m_balance;  }
   string LastError(void)  const { return m_err;      }

   // fresh sub-account at segment start: legcap = (seed*W)/slot_legs,
   // computed by the caller so the float order is owned in ONE place.
   void ResetSegment(const double legcap)
     {
      m_legcap=legcap; m_balance=legcap; m_pos=0.0; m_entry=0.0;
      m_n=0; m_err="";
     }

   // One in-window native bar. All costs (eurq, swap accrual fields) are
   // PRE-BAKED inputs — this method never recomputes calendars or crosses.
   bool StepBar(const long ts,
                const double bid_o, const double bid_h, const double bid_l, const double bid_c,
                const double ask_o, const double ask_h, const double ask_l, const double ask_c,
                const double eurq,  const double swap_flag,
                const double swap_long, const double swap_short,
                const double tgt)
     {
      double mid_o = 0.5*(bid_o + ask_o);

      // ---- 1. swap at the rollover minute ----
      if(swap_flag > 0.0 && m_pos != 0.0)
        {
         double frac     = (m_pos > 0.0) ? swap_long : swap_short;
         double notional = MathAbs(m_pos) * m_contract * mid_o;
         m_balance += notional * frac / 365.0 * swap_flag * eurq;
        }

      // ---- 2. sizing at open (notional mode) ----
      double sgn_t = (tgt == 0.0) ? 0.0 : ((tgt > 0.0) ? 1.0 : -1.0);
      double sgn_p = (m_pos == 0.0) ? 0.0 : ((m_pos > 0.0) ? 1.0 : -1.0);
      double desired = 0.0;
      bool   want_change;
      if(sgn_t == 0.0)
         want_change = (m_pos != 0.0);
      else
        {
         double px       = (sgn_t > 0.0) ? ask_o : bid_o;
         double unit_eur = px * m_contract * eurq;
         // dd_scale/thr_scale kept literal 1.0 (bit-exact no-ops, spec s.5)
         double lots     = m_balance * MathAbs(tgt) * 1.0 * 1.0 / unit_eur;
         double max_lots = (m_balance * m_lev * CORESIM_MARGIN_CAP) / unit_eur;
         if(lots > max_lots) lots = max_lots;
         double nn = MathFloor(lots/m_step + 1e-9);          // _round_lots
         lots = nn * m_step;
         if(lots < m_minlot) lots = 0.0;
         if(sgn_t != sgn_p)
           { want_change = true; desired = sgn_t * lots; }
         else if(m_pos != 0.0 && MathAbs(lots - MathAbs(m_pos))/MathAbs(m_pos) > CORESIM_REBAL_BAND)
           { want_change = true; desired = sgn_t * lots; }
         else
            want_change = false;
        }

      // ---- 3. fills at this bar's open (cross the spread) ----
      if(want_change && (desired - m_pos) != 0.0)
        {
         // close/reduce part
         if(m_pos != 0.0 && (desired == 0.0 || desired*m_pos < 0.0
                             || MathAbs(desired) < MathAbs(m_pos)))
           {
            double close_lots = (desired*m_pos <= 0.0) ? m_pos : m_pos - desired;
            double px  = (m_pos > 0.0) ? bid_o : ask_o;
            double pnl = (px - m_entry) * close_lots * m_contract * eurq;
            m_balance += pnl - m_comm*MathAbs(close_lots);   // ONE add
            m_pos -= close_lots;
           }
         // open/extend part (a sign flip runs BOTH in the same bar)
         if(desired != 0.0 && MathAbs(desired) > MathAbs(m_pos))
           {
            double add = desired - m_pos;
            double px  = (add > 0.0) ? ask_o : bid_o;
            if(m_pos == 0.0) m_entry = px;
            else             m_entry = (m_entry*m_pos + px*add)/(m_pos + add);
            m_balance -= m_comm*MathAbs(add);
            m_pos = desired;
           }
        }

      // ---- 4. marks (co-timed at this minute) ----
      double unreal_c, unreal_w;
      if(m_pos > 0.0)
        {
         unreal_c = (bid_c - m_entry) * m_pos * m_contract * eurq;
         unreal_w = (bid_l - m_entry) * m_pos * m_contract * eurq;
        }
      else if(m_pos < 0.0)
        {
         unreal_c = (ask_c - m_entry) * m_pos * m_contract * eurq;
         unreal_w = (ask_h - m_entry) * m_pos * m_contract * eurq;
        }
      else { unreal_c = 0.0; unreal_w = 0.0; }
      double eq_c = m_balance + unreal_c;
      double eq_w = m_balance + unreal_w;

      // ---- 5. margin (+ noliq stop-out guard: MUST never fire) ----
      double margin = 0.0;
      if(m_pos != 0.0)
        {
         double mid_c = 0.5*(bid_c + ask_c);
         margin = MathAbs(m_pos) * m_contract * mid_c * eurq / m_lev;
         if(eq_w < CORESIM_STOP_OUT*margin)
           { m_err = "noliq stop-out fired (impossible in the anchor)"; return false; }
        }

      // ---- 6. negative balance protection: an a_h leg never dies ----
      if(m_pos == 0.0 && m_balance <= 0.0)
        { m_err = "leg death (impossible in the anchor)"; return false; }

      // ---- capture ----
      if(!Reserve()) return false;
      m_ts[m_n]=ts; m_c[m_n]=eq_c; m_w[m_n]=eq_w; m_m[m_n]=margin; m_n++;
      return true;
     }
};

//====================================================================
// CCoreBookSim — the 7-slot / 9-leg book: legcap seeding, per-leg
// capture, the combine_curves-faithful union combiner (+ flat legcap),
// frozen-trigger segment replay via seed chaining (spec section 6).
// Usage per segment:
//   BeginSegment(seed);                  // seed_0 = 10000.0 (INIT)
//   for each leg (book order), for each in-window native bar:
//       StepLegBar(leg, ...);            // leg-major streaming
//   FinishSegment();                     // combine; outputs ready
//   seed_next = FinalEqC();
//====================================================================
class CCoreBookSim
{
private:
   CCoreLegSim *m_legs[];
   int          m_nLegs;
   int          m_nSlots;
   double       m_W;                       // 1.0/n_slots
   double       m_flat;                    // summed legcap of bar-less legs
   // combined outputs (this segment)
   long         m_uts[];
   double       m_eqc[], m_eqw[], m_mg[];
   int          m_un;
   string       m_err;

public:
                     CCoreBookSim(void) : m_nLegs(0), m_nSlots(0), m_W(0.0),
                                          m_flat(0.0), m_un(0), m_err("") {}
                    ~CCoreBookSim(void)
     {
      for(int i=0;i<m_nLegs;i++) if(CheckPointer(m_legs[i])==POINTER_DYNAMIC) delete m_legs[i];
     }

   string LastError(void) const { return m_err; }

   // n_slots FIRST (defines W), then legs in BOOK APPEND ORDER.
   bool SetSlots(const int n_slots)
     {
      if(n_slots <= 0) { m_err="bad n_slots"; return false; }
      m_nSlots = n_slots;
      m_W = 1.0/(double)n_slots;
      return true;
     }

   // returns the leg index, -1 on failure
   int AddLeg(const int slot_legs, const double contract, const double comm,
              const double lev, const double lot_step, const double min_lot)
     {
      int idx = m_nLegs;
      if(ArrayResize(m_legs, idx+1) != idx+1) { m_err="ArrayResize legs"; return -1; }
      m_legs[idx] = new CCoreLegSim();
      if(CheckPointer(m_legs[idx]) != POINTER_DYNAMIC) { m_err="new leg"; return -1; }
      m_legs[idx].Configure(slot_legs, contract, comm, lev, lot_step, min_lot);
      m_nLegs = idx+1;
      return idx;
     }

   int NLegs(void) const { return m_nLegs; }

   bool BeginSegment(const double seed)
     {
      if(m_nSlots <= 0 || m_nLegs <= 0) { m_err="book not configured"; return false; }
      m_flat = 0.0; m_un = 0; m_err="";
      for(int i=0;i<m_nLegs;i++)
        {
         // NORMATIVE float order: (seed * W) / slot_legs   (spec 6.2)
         double legcap = seed * m_W / (double)m_legs[i].SlotLegs();
         m_legs[i].ResetSegment(legcap);
        }
      return true;
     }

   bool StepLegBar(const int leg, const long ts,
                   const double bid_o, const double bid_h, const double bid_l, const double bid_c,
                   const double ask_o, const double ask_h, const double ask_l, const double ask_c,
                   const double eurq, const double swap_flag,
                   const double swap_long, const double swap_short, const double tgt)
     {
      if(leg < 0 || leg >= m_nLegs) { m_err="bad leg index"; return false; }
      if(!m_legs[leg].StepBar(ts, bid_o, bid_h, bid_l, bid_c,
                              ask_o, ask_h, ask_l, ask_c,
                              eurq, swap_flag, swap_long, swap_short, tgt))
        { m_err = "leg "+IntegerToString(leg)+": "+m_legs[leg].LastError(); return false; }
      return true;
     }

   // ---- combine (spec 6.1): union grid, close ffill + FIRST-VALUE backfill,
   // worst only on own bars, margin ffill 0-filled, left-to-right leg order,
   // + flat. Legs with zero in-window bars contribute flat += legcap.
   bool FinishSegment(void)
     {
      // 1. flat accounting + participating legs (book append order kept)
      int part[]; int npart=0;
      ArrayResize(part, m_nLegs);
      m_flat = 0.0;
      for(int i=0;i<m_nLegs;i++)
        {
         if(m_legs[i].Bars() == 0) { m_flat += m_legs[i].LegCap(); continue; }
         part[npart]=i; npart++;
        }
      if(npart == 0) { m_err="all legs empty"; return false; }

      // 2. union of stamps: concat -> sort -> unique
      int tot=0;
      for(int p=0;p<npart;p++) tot += m_legs[part[p]].Bars();
      long all[];
      if(ArrayResize(all, tot) != tot) { m_err="ArrayResize union concat"; return false; }
      int w=0;
      for(int p=0;p<npart;p++)
        {
         CCoreLegSim *lg = m_legs[part[p]];
         int nb = lg.Bars();
         for(int i=0;i<nb;i++) { all[w]=lg.Ts(i); w++; }
        }
      ArraySort(all);
      if(ArrayResize(m_uts, tot) != tot) { m_err="ArrayResize uts"; return false; }
      m_un=0;
      for(int i=0;i<tot;i++)
        {
         if(m_un > 0 && all[i] == m_uts[m_un-1]) continue;
         m_uts[m_un]=all[i]; m_un++;
        }

      // 3. accumulate legs left-to-right (per-element ((l0+l1)+l2)+...)
      if(ArrayResize(m_eqc, m_un) != m_un) { m_err="ArrayResize eqc"; return false; }
      if(ArrayResize(m_eqw, m_un) != m_un) { m_err="ArrayResize eqw"; return false; }
      if(ArrayResize(m_mg,  m_un) != m_un) { m_err="ArrayResize mg";  return false; }
      for(int i=0;i<m_un;i++) { m_mg[i]=0.0; }        // margin: builtin-sum 0 start
      for(int p=0;p<npart;p++)
        {
         CCoreLegSim *lg = m_legs[part[p]];
         int nb = lg.Bars();
         int q  = -1;                                  // last own bar <= uts[i]
         double first_c = lg.EqC(0);
         for(int i=0;i<m_un;i++)
           {
            long t = m_uts[i];
            while(q+1 < nb && lg.Ts(q+1) <= t) q++;
            bool has_bar = (q >= 0 && lg.Ts(q) == t);
            double c_f = (q >= 0) ? lg.EqC(q) : first_c;         // ffill + backfill-first
            double w_e = has_bar ? lg.EqW(q) : c_f;              // worst only on own bars
            double m_f = (q >= 0) ? lg.Mg(q) : 0.0;              // margin ffill, 0 before
            if(p == 0) { m_eqc[i] = c_f;            m_eqw[i] = w_e;            }
            else       { m_eqc[i] = m_eqc[i] + c_f; m_eqw[i] = m_eqw[i] + w_e; }
            m_mg[i] = m_mg[i] + m_f;
           }
        }

      // 4. + flat legcap (single add per element; margin gets no flat)
      for(int i=0;i<m_un;i++) { m_eqc[i] = m_eqc[i] + m_flat; m_eqw[i] = m_eqw[i] + m_flat; }
      return true;
     }

   // ---- combined outputs of the finished segment ----
   int    UnionBars(void)    const { return m_un;      }
   long   UnionTs(const int i) const { return m_uts[i]; }
   double EqC(const int i)   const { return m_eqc[i];  }
   double EqW(const int i)   const { return m_eqw[i];  }
   double Mg(const int i)    const { return m_mg[i];   }
   double Flat(void)         const { return m_flat;    }
   // seed for the NEXT frozen segment (spec 6.2 seed chain)
   double FinalEqC(void)     const { return (m_un > 0) ? m_eqc[m_un-1] : 0.0; }
};

#endif // CORE_CORESIM_MQH
