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
   double m_p[], m_mc[], m_qe[];       // f_core capture: pos, mid_c, eurq
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
      if(ArrayResize(m_p,  want) != want) { m_err="ArrayResize p";   return false; }
      if(ArrayResize(m_mc, want) != want) { m_err="ArrayResize mc";  return false; }
      if(ArrayResize(m_qe, want) != want) { m_err="ArrayResize qe";  return false; }
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
   // f_core capture accessors (position AFTER fills — the position whose
   // marks defined EqC(i), the anchor's extraction-capture point)
   double Pos(const int i)  const { return m_p[i];    }
   double MidC(const int i) const { return m_mc[i];   }
   double Eurq(const int i) const { return m_qe[i];   }
   double Contract(void)    const { return m_contract; }
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
      // mid_c hoisted for the f_core capture; the margin expression below is
      // textually unchanged (0.5*(b+a) vs the anchor's (b+a)*0.5 is bit-
      // identical: IEEE-754 multiplication is commutative).
      double mid_c  = 0.5*(bid_c + ask_c);
      double margin = 0.0;
      if(m_pos != 0.0)
        {
         margin = MathAbs(m_pos) * m_contract * mid_c * eurq / m_lev;
         if(eq_w < CORESIM_STOP_OUT*margin)
           { m_err = "noliq stop-out fired (impossible in the anchor)"; return false; }
        }

      // ---- 6. negative balance protection: an a_h leg never dies ----
      if(m_pos == 0.0 && m_balance <= 0.0)
        { m_err = "leg death (impossible in the anchor)"; return false; }

      // ---- capture (incl. f_core triple: pos-after-fills, mid_c, eurq) ----
      if(!Reserve()) return false;
      m_ts[m_n]=ts; m_c[m_n]=eq_c; m_w[m_n]=eq_w; m_m[m_n]=margin;
      m_p[m_n]=m_pos; m_mc[m_n]=mid_c; m_qe[m_n]=eurq; m_n++;
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
   // --- f_core state (net-symbol map, cross-segment carry, hourly rows) ---
   int          m_legNet[];                // leg -> net col (-1 = unmapped)
   int          m_nNet;                    // net symbol count (8 in the book)
   double       m_cPos[], m_cMid[], m_cQe[]; // per-leg last-bar carry (ffill
   bool         m_cValid[];                  //   across segment seams)
   long         m_fts[];                   // hour-start epochs (persistent)
   double       m_fv[];                    // row-major [row*m_nNet + net]
   int          m_fn;                      // emitted hourly rows
   string       m_err;

public:
                     CCoreBookSim(void) : m_nLegs(0), m_nSlots(0), m_W(0.0),
                                          m_flat(0.0), m_un(0),
                                          m_nNet(0), m_fn(0), m_err("") {}
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
      if(ArrayResize(m_legNet, idx+1) != idx+1) { m_err="ArrayResize legNet"; return -1; }
      if(ArrayResize(m_cPos,   idx+1) != idx+1) { m_err="ArrayResize cPos";   return -1; }
      if(ArrayResize(m_cMid,   idx+1) != idx+1) { m_err="ArrayResize cMid";   return -1; }
      if(ArrayResize(m_cQe,    idx+1) != idx+1) { m_err="ArrayResize cQe";    return -1; }
      if(ArrayResize(m_cValid, idx+1) != idx+1) { m_err="ArrayResize cValid"; return -1; }
      m_legNet[idx] = -1;
      m_cPos[idx] = 0.0; m_cMid[idx] = 0.0; m_cQe[idx] = 0.0;
      m_cValid[idx] = false;
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

   //=================================================================
   // f_core — the Core book's held fraction-of-own-equity per NET
   // symbol, the frozen v7_book_frac_1h.parquet [legacy name] series.
   // Identity PROVEN bit-exact over the full hourly grid in python
   // (research/bpure/coresim/fcore_identity.json, verdict (c)-VIABLE):
   //
   //   f_core[net] = net_lots * contract * mid_c * eurq / book_eqc
   //
   //   net_lots  = sum of member-leg pos (leg index order), forward-
   //               filled on the union grid INCLUDING segment seams;
   //   mid_c/eurq forward-filled from the instrument's own bars;
   //   book_eqc  = the combined close-mark equity (incl. flat legcap);
   //   hourly row stamped at hour start h = snapshot at the LAST 1m
   //   union bar with stamp in [h, h+1).
   //
   // Usage: SetNets(n) once, AssignLegNet(leg, net) per leg, then call
   // ComputeFCore() after EVERY FinishSegment() in chain order. Rows
   // accumulate across segments (the seam carry lives in this object).
   //=================================================================
   bool SetNets(const int n_net)
     {
      if(n_net <= 0) { m_err="bad n_net"; return false; }
      m_nNet = n_net;
      m_fn = 0;
      return true;
     }

   bool AssignLegNet(const int leg, const int net)
     {
      if(leg < 0 || leg >= m_nLegs)  { m_err="AssignLegNet leg";  return false; }
      if(net < 0 || net >= m_nNet)   { m_err="AssignLegNet net";  return false; }
      m_legNet[leg] = net;
      return true;
     }

   bool ComputeFCore(void)
     {
      if(m_nNet <= 0)  { m_err="f_core: SetNets not called"; return false; }
      if(m_un <= 0)    { m_err="f_core: no finished segment"; return false; }
      // per-leg cursor over this segment's captured bars
      int q[];
      if(ArrayResize(q, m_nLegs) != m_nLegs) { m_err="ArrayResize q"; return false; }
      for(int l=0;l<m_nLegs;l++) q[l] = -1;
      double fr[];
      if(ArrayResize(fr, m_nNet) != m_nNet) { m_err="ArrayResize fr"; return false; }
      double net_pos[], net_mid[], net_qe[], net_ct[];
      bool   net_has[];
      if(ArrayResize(net_pos, m_nNet) != m_nNet ||
         ArrayResize(net_mid, m_nNet) != m_nNet ||
         ArrayResize(net_qe,  m_nNet) != m_nNet ||
         ArrayResize(net_ct,  m_nNet) != m_nNet ||
         ArrayResize(net_has, m_nNet) != m_nNet)
        { m_err="ArrayResize net scratch"; return false; }

      for(int i=0;i<m_un;i++)
        {
         long t = m_uts[i];
         // net accumulation in LEG INDEX ORDER (the anchor's per_inst
         // accumulation order); one net's legs share the instrument, so
         // mid/eurq come from the first member leg that has data.
         for(int s=0;s<m_nNet;s++)
           { net_pos[s]=0.0; net_mid[s]=0.0; net_qe[s]=0.0; net_ct[s]=0.0; net_has[s]=false; }
         for(int l=0;l<m_nLegs;l++)
           {
            int s = m_legNet[l];
            if(s < 0) continue;
            CCoreLegSim *lg = m_legs[l];
            int nb = lg.Bars();
            while(q[l]+1 < nb && lg.Ts(q[l]+1) <= t) q[l]++;
            double p, mc, qe;
            if(q[l] >= 0)
              { p = lg.Pos(q[l]);  mc = lg.MidC(q[l]); qe = lg.Eurq(q[l]); }
            else if(m_cValid[l])
              { p = m_cPos[l];     mc = m_cMid[l];     qe = m_cQe[l];      }
            else
               continue;           // before the instrument's first bar ever
            net_pos[s] = net_pos[s] + p;          // left-to-right leg order
            if(!net_has[s])
              { net_mid[s]=mc; net_qe[s]=qe; net_ct[s]=lg.Contract(); net_has[s]=true; }
           }
         double eqc = m_eqc[i];
         for(int s=0;s<m_nNet;s++)
           {
            if(!net_has[s]) { fr[s] = 0.0; continue; }   // fillna(0) case
            // NORMATIVE grouping: ((lots * contract) * mid) * eurq / eqc
            double val = net_pos[s] * net_ct[s] * net_mid[s] * net_qe[s];
            fr[s] = val / eqc;
           }
         // hourly emit: keep only the LAST union bar of each hour bucket;
         // same-hour rows overwrite (also heals a segment-seam straddle)
         long hour = t - (t % 3600);
         int  row  = m_fn;
         if(m_fn > 0 && m_fts[m_fn-1] == hour) row = m_fn - 1;
         if(row == m_fn)
           {
            int cap = ArraySize(m_fts);
            if(m_fn >= cap)
              {
               int want = cap + CORESIM_GROW;
               if(ArrayResize(m_fts, want) != want) { m_err="ArrayResize fts"; return false; }
               if(ArrayResize(m_fv, want*m_nNet) != want*m_nNet) { m_err="ArrayResize fv"; return false; }
              }
            m_fn++;
           }
         m_fts[row] = hour;
         for(int s=0;s<m_nNet;s++) m_fv[row*m_nNet + s] = fr[s];
        }

      // seam carry: legs that traded this segment update their ffill state
      for(int l=0;l<m_nLegs;l++)
        {
         CCoreLegSim *lg = m_legs[l];
         int nb = lg.Bars();
         if(nb <= 0) continue;
         m_cPos[l] = lg.Pos(nb-1);
         m_cMid[l] = lg.MidC(nb-1);
         m_cQe[l]  = lg.Eurq(nb-1);
         m_cValid[l] = true;
        }
      return true;
     }

   int    FCoreRows(void)           const { return m_fn;     }
   long   FCoreTs(const int k)      const { return m_fts[k]; }
   double FCoreAt(const int k, const int net) const { return m_fv[k*m_nNet + net]; }
};

#endif // CORE_CORESIM_MQH
