//+------------------------------------------------------------------+
//| Ensemble.mqh — FMA3 v34 ensemble shell (CV34EnsembleStepper)     |
//|                                                                  |
//| 1:1 MQL5 port of research/bpure/steppers/ensemble_stepper.py     |
//| (Wave-1 validated: state-exact vs frozen goldens, gate           |
//| bit-identical).  Pointwise scalar combine + hard limits.         |
//|                                                                  |
//| FROZEN SPEC (via the Python stepper, verified line-by-line       |
//| against model/v3/freeze/FMA3-v34-freeze-1):                      |
//|   ensemble.py combine(), structural_gold_cap(),                  |
//|               apply_hard_limits()                                |
//|   eval_v34_pin_s10.py build_c2(): V2_CAPS, SCALE=10.0, MAG_W=0.05|
//|                                                                  |
//| Bit-exact semantics replicated:                                  |
//|  * per (bar, symbol):                                            |
//|      (((p_1*w_1) + p_2*w_2) + ... + p_k*w_k) * 10.0              |
//|    folded over the sleeves that CONTAIN the symbol, in the       |
//|    frozen dict-insertion order: V2_CAPS key order then "mag".    |
//|    The fold reproduces the exact binary-operation association    |
//|    (first contributor ASSIGNS, the rest ADD, final multiply by   |
//|    SCALE post-sum) — NOT p*(w*10), which differs in the last ulp.|
//|  * RAW weights, NO renormalization.                              |
//|  * structural gold cap is DERIVED (never hardcoded):             |
//|      weights["seasonal"] * scale = V2_CAPS["seasonal"] * 10.0    |
//|  * apply_hard_limits (post-scale):                               |
//|     - managed-cross cap: |EURCHF|,|EURSEK|,|EURNOK|,|AUDNZD|     |
//|       <= 0.5 ABSOLUTE at ALL bars (0.5 is NOT multiplied by      |
//|       scale — the Gemini 0.5*scale bug is the counterexample);   |
//|     - overnight-gold cap: |XAUUSD| <= gold_cap on server hours   |
//|       h >= 21 or h < 6 (21,22,23,0,1,2,3,4,5).                   |
//|    Clip order (crosses first, gold second) irrelevant: disjoint  |
//|    columns.  NaN positions pass BOTH clips unchanged (IEEE       |
//|    comparisons with NaN are false — identical to the Python).    |
//|                                                                  |
//| ---------------------------- API -------------------------------|
//| Configuration (mirrors EnsembleStepper.__init__(sleeve_symbols); |
//| pass exactly the golden sleeve parquet columns — e.g.            |
//| carry_breakout's 21 KEPT columns, not the stepper's full 32):    |
//|   AddSleeve(name, symbols[])  for each sleeve present            |
//|                               (unknown name -> false, ValueError)|
//|   Finalize()                  orders sleeves by the frozen       |
//|                               SLEEVE_ORDER, builds the sorted    |
//|                               union book columns and per-symbol  |
//|                               contributor fold lists, derives    |
//|                               gold_cap.                          |
//| Per bar (== Python step(ts_ns, sleeve_rows) -> {sym: pos}):      |
//|   SetSleeveRow(name, pos[])   this sleeve's positions at this    |
//|                               bar, aligned to the symbol list    |
//|                               given in AddSleeve (NaN allowed).  |
//|                               Required for EVERY sleeve EVERY    |
//|                               bar (Python would KeyError).       |
//|   Step(t, out[])              t = server-time datetime of the    |
//|                               bar (seconds; hour == Python       |
//|                               ts_ns//HOUR_NS % 24).  Fills       |
//|                               out[SymbolCount()] in Symbols()    |
//|                               order (sorted union, == pandas     |
//|                               .add union order) and clears the   |
//|                               staged rows.  Returns false if any |
//|                               sleeve row was not staged.         |
//| Introspection: SymbolCount()/SymbolAt(i), SleeveCount()/         |
//|   SleeveNameAt(i)/SleeveWeightAt(i), GoldCap().                  |
//|                                                                  |
//| State (GetState/SetState): the Python stepper is STATELESS across|
//| bars ("the book shell has no memory") — its entire state dict is |
//| the __init__ configuration {order, sleeve_symbols, symbols,      |
//| contrib, gold_cap}.  GetState serializes order + sleeve_symbols  |
//| field-for-field (symbols/contrib/gold_cap are pure derivations   |
//| and are rebuilt by SetState via the same code path, then         |
//| gold_cap is verified against the serialized value).  Staged     |
//| per-bar rows are NOT state and are never serialized.             |
//+------------------------------------------------------------------+
#ifndef FMA3V34_ENSEMBLE_MQH
#define FMA3V34_ENSEMBLE_MQH

#include <FMA3v34/V34Math.mqh>

//==================================================================//
// frozen constants (eval_v34_pin_s10.py / ensemble.py)             //
//==================================================================//
#define V34_ENS_NSLEEVES 8

// build_c2 sleeve dict insertion order == combine() accumulation
// order: V2_CAPS key order then "mag"
const string V34_ENS_SLEEVE_ORDER[V34_ENS_NSLEEVES] =
  {
   "meanrev", "carry_breakout", "seasonal", "intraday",
   "crisis", "trend_v2", "crypto_smart", "mag"
  };
// WEIGHTS = {**V2_CAPS, "mag": MAG_W}   (RAW, no renormalization)
const double V34_ENS_WEIGHTS[V34_ENS_NSLEEVES] =
  {
   0.11, 0.046, 0.18, 0.168, 0.10, 0.042, 0.13, 0.05
  };
const int    V34_ENS_SEASONAL_IDX = 2;    // "seasonal" slot above
const double V34_ENS_SCALE        = 10.0; // SCALE
const double V34_ENS_MAG_W        = 0.05; // MAG_W (== WEIGHTS[7])

// ensemble.py apply_hard_limits frozen constants
const string V34_ENS_CROSS_SYMS[4] = {"EURCHF", "EURSEK", "EURNOK", "AUDNZD"};
const double V34_ENS_CROSS_CAP     = 0.5;   // ABSOLUTE post-scale, all bars
const string V34_ENS_GOLD_SYM      = "XAUUSD";
const int    V34_ENS_OVERNIGHT_H_GE = 21;   // (hrs >= 21) | (hrs < 6)
const int    V34_ENS_OVERNIGHT_H_LT = 6;

//------------------------------------------------------------------//
// structural_gold_cap (frozen ensemble.structural_gold_cap):       //
// DERIVED rule — the primary gold sleeve's own intended exposure   //
// = weights[primary] * scale.  build_c2 passes V2_CAPS (no mag)    //
// and SCALE=10.0 -> 0.18 * 10.0.  Same IEEE multiply as Python.    //
//------------------------------------------------------------------//
double V34EnsembleStructuralGoldCap()
  {
   return V34_ENS_WEIGHTS[V34_ENS_SEASONAL_IDX] * V34_ENS_SCALE;
  }

//------------------------------------------------------------------//
// Python `sorted()` string order: per-code-point lexicographic.    //
// (Do NOT trust StringCompare's collation — compare code units.)   //
//------------------------------------------------------------------//
bool V34EnsStrLess(const string a, const string b)
  {
   int la = StringLen(a), lb = StringLen(b);
   int n  = (la < lb) ? la : lb;
   for(int i = 0; i < n; i++)
     {
      ushort ca = StringGetCharacter(a, i);
      ushort cb = StringGetCharacter(b, i);
      if(ca != cb)
         return (ca < cb);
     }
   return (la < lb);
  }

//==================================================================//
// CV34EnsembleStepper                                              //
//==================================================================//
class CV34EnsembleStepper
  {
public:
   // ---- configuration == the Python stepper's ENTIRE state ----
   // (public on purpose: field-for-field mirror of __init__ attrs)
   int               m_nsleeves;         // len(self.order)
   int               m_sleeve_ord[];     // canonical slot in SLEEVE_ORDER
   string            m_sleeve_name[];    // self.order (canonical order)
   double            m_sleeve_w[];       // WEIGHTS[name]
   int               m_sl_sym_start[];   // self.sleeve_symbols[name] ...
   int               m_sl_sym_count[];   //   flattened: [start, start+count)
   string            m_sl_syms[];        //   into this pool
   int               m_nsym;             // len(self.symbols)
   string            m_symbols[];        // self.symbols (sorted union)
   bool              m_is_cross[];       // sym in CROSS_SYMS
   bool              m_is_gold[];        // sym == GOLD_SYM
   int               m_ct_start[];       // self.contrib[sym] flattened:
   int               m_ct_count[];       //   [(sleeve, weight), ...]
   int               m_ct_sleeve[];      //   sleeve index (canonical)
   int               m_ct_pos[];         //   symbol slot within that sleeve
   double            m_ct_w[];           //   weight
   double            m_gold_cap;         // self.gold_cap (DERIVED)
   bool              m_finalized;

   // ---- per-bar staging (NOT persistent state, never serialized) ----
   double            m_row_val[];        // flattened sleeve rows
   bool              m_row_set[];        // per sleeve: staged this bar?

                     CV34EnsembleStepper() { Reset(); }

   void              Reset()
     {
      m_nsleeves  = 0;
      ArrayResize(m_sleeve_ord, 0);
      ArrayResize(m_sleeve_name, 0);
      ArrayResize(m_sleeve_w, 0);
      ArrayResize(m_sl_sym_start, 0);
      ArrayResize(m_sl_sym_count, 0);
      ArrayResize(m_sl_syms, 0);
      m_nsym = 0;
      ArrayResize(m_symbols, 0);
      ArrayResize(m_is_cross, 0);
      ArrayResize(m_is_gold, 0);
      ArrayResize(m_ct_start, 0);
      ArrayResize(m_ct_count, 0);
      ArrayResize(m_ct_sleeve, 0);
      ArrayResize(m_ct_pos, 0);
      ArrayResize(m_ct_w, 0);
      m_gold_cap  = V34Nan();
      m_finalized = false;
      ArrayResize(m_row_val, 0);
      ArrayResize(m_row_set, 0);
     }

   //---------------------------------------------------------------//
   // AddSleeve — one entry of the __init__ sleeve_symbols mapping. //
   // Unknown sleeve name -> false (Python: ValueError).  Duplicate //
   // AddSleeve for the same name -> false (a dict has unique keys).//
   // Call order is irrelevant: Finalize() orders canonically.      //
   //---------------------------------------------------------------//
   bool              AddSleeve(const string name, const string &symbols[])
     {
      if(m_finalized)
        {
         Print("CV34EnsembleStepper: AddSleeve after Finalize");
         return false;
        }
      int slot = -1;
      for(int i = 0; i < V34_ENS_NSLEEVES; i++)
         if(V34_ENS_SLEEVE_ORDER[i] == name) { slot = i; break; }
      if(slot < 0)
        {
         Print("CV34EnsembleStepper: unknown sleeve '", name, "'");
         return false;
        }
      for(int i = 0; i < m_nsleeves; i++)
         if(m_sleeve_ord[i] == slot)
           {
            Print("CV34EnsembleStepper: duplicate sleeve '", name, "'");
            return false;
           }
      int k = m_nsleeves;
      ArrayResize(m_sleeve_ord,   k + 1);
      ArrayResize(m_sleeve_name,  k + 1);
      ArrayResize(m_sleeve_w,     k + 1);
      ArrayResize(m_sl_sym_start, k + 1);
      ArrayResize(m_sl_sym_count, k + 1);
      m_sleeve_ord[k]   = slot;
      m_sleeve_name[k]  = name;
      m_sleeve_w[k]     = V34_ENS_WEIGHTS[slot];
      int nsym = ArraySize(symbols);
      int base = ArraySize(m_sl_syms);
      m_sl_sym_start[k] = base;
      m_sl_sym_count[k] = nsym;
      ArrayResize(m_sl_syms, base + nsym);
      for(int j = 0; j < nsym; j++)
         m_sl_syms[base + j] = symbols[j];
      m_nsleeves = k + 1;
      return true;
     }

   //---------------------------------------------------------------//
   // Finalize — the rest of __init__: canonical sleeve order,      //
   // sorted union symbol list, per-symbol contributor fold lists   //
   // in sleeve order, derived gold cap.                            //
   //---------------------------------------------------------------//
   bool              Finalize()
     {
      if(m_finalized)
         return true;
      if(m_nsleeves <= 0)
        {
         Print("CV34EnsembleStepper: Finalize with no sleeves");
         return false;
        }
      // self.order = tuple(n for n in SLEEVE_ORDER if n in sleeve_symbols)
      // -> sort the added sleeves by canonical slot (insertion sort)
      for(int i = 1; i < m_nsleeves; i++)
        {
         int    o = m_sleeve_ord[i];
         string nm = m_sleeve_name[i];
         double w = m_sleeve_w[i];
         int    st = m_sl_sym_start[i];
         int    ct = m_sl_sym_count[i];
         int j = i - 1;
         while(j >= 0 && m_sleeve_ord[j] > o)
           {
            m_sleeve_ord[j + 1]   = m_sleeve_ord[j];
            m_sleeve_name[j + 1]  = m_sleeve_name[j];
            m_sleeve_w[j + 1]     = m_sleeve_w[j];
            m_sl_sym_start[j + 1] = m_sl_sym_start[j];
            m_sl_sym_count[j + 1] = m_sl_sym_count[j];
            j--;
           }
         m_sleeve_ord[j + 1]   = o;
         m_sleeve_name[j + 1]  = nm;
         m_sleeve_w[j + 1]     = w;
         m_sl_sym_start[j + 1] = st;
         m_sl_sym_count[j + 1] = ct;
        }
      // self.symbols = tuple(sorted(union))  (pandas .add union is sorted)
      m_nsym = 0;
      ArrayResize(m_symbols, 0);
      int pool = ArraySize(m_sl_syms);
      for(int p = 0; p < pool; p++)
        {
         string s = m_sl_syms[p];
         bool dup = false;
         for(int q = 0; q < m_nsym; q++)
            if(m_symbols[q] == s) { dup = true; break; }
         if(dup)
            continue;
         // sorted insert (Python code-point order)
         int at = m_nsym;
         for(int q = 0; q < m_nsym; q++)
            if(V34EnsStrLess(s, m_symbols[q])) { at = q; break; }
         ArrayResize(m_symbols, m_nsym + 1);
         for(int q = m_nsym; q > at; q--)
            m_symbols[q] = m_symbols[q - 1];
         m_symbols[at] = s;
         m_nsym++;
        }
      // hard-limit column flags
      ArrayResize(m_is_cross, m_nsym);
      ArrayResize(m_is_gold, m_nsym);
      for(int q = 0; q < m_nsym; q++)
        {
         bool xc = false;
         for(int c = 0; c < 4; c++)
            if(m_symbols[q] == V34_ENS_CROSS_SYMS[c]) { xc = true; break; }
         m_is_cross[q] = xc;
         m_is_gold[q]  = (m_symbols[q] == V34_ENS_GOLD_SYM);
        }
      // self.contrib[sym] = [(sleeve, weight) for sleeve in order
      //                      if sym in sleeve_symbols[sleeve]]
      ArrayResize(m_ct_start, m_nsym);
      ArrayResize(m_ct_count, m_nsym);
      ArrayResize(m_ct_sleeve, 0);
      ArrayResize(m_ct_pos, 0);
      ArrayResize(m_ct_w, 0);
      int nct = 0;
      for(int q = 0; q < m_nsym; q++)
        {
         m_ct_start[q] = nct;
         int cnt = 0;
         for(int i = 0; i < m_nsleeves; i++)
           {
            int st = m_sl_sym_start[i];
            int n  = m_sl_sym_count[i];
            int pos = -1;
            for(int j = 0; j < n; j++)
               if(m_sl_syms[st + j] == m_symbols[q]) { pos = j; break; }
            if(pos < 0)
               continue;
            ArrayResize(m_ct_sleeve, nct + 1);
            ArrayResize(m_ct_pos,    nct + 1);
            ArrayResize(m_ct_w,      nct + 1);
            m_ct_sleeve[nct] = i;
            m_ct_pos[nct]    = pos;
            m_ct_w[nct]      = m_sleeve_w[i];
            nct++;
            cnt++;
           }
         m_ct_count[q] = cnt;
        }
      // self.gold_cap = structural_gold_cap()  (derived, never hardcoded)
      m_gold_cap = V34EnsembleStructuralGoldCap();
      // per-bar staging buffers
      ArrayResize(m_row_val, pool);
      double nan = V34Nan();
      for(int p = 0; p < pool; p++)
         m_row_val[p] = nan;
      ArrayResize(m_row_set, m_nsleeves);
      for(int i = 0; i < m_nsleeves; i++)
         m_row_set[i] = false;
      m_finalized = true;
      return true;
     }

   // ---- introspection ----
   bool              Finalized()   const { return m_finalized; }
   int               SymbolCount() const { return m_nsym; }
   string            SymbolAt(const int i) const { return m_symbols[i]; }
   int               SleeveCount() const { return m_nsleeves; }
   string            SleeveNameAt(const int i) const { return m_sleeve_name[i]; }
   double            SleeveWeightAt(const int i) const { return m_sleeve_w[i]; }
   int               SleeveSymbolCount(const int i) const { return m_sl_sym_count[i]; }
   string            SleeveSymbolAt(const int i, const int j) const
     { return m_sl_syms[m_sl_sym_start[i] + j]; }
   double            GoldCap() const { return m_gold_cap; }

   //---------------------------------------------------------------//
   // SetSleeveRow — stage sleeve_rows[name] for the coming Step(). //
   // positions[] aligned to the AddSleeve symbol list (NaN allowed;//
   // NaN propagates through the fold and passes the clips, exactly //
   // as in Python).  Length must match; unknown name -> false.     //
   //---------------------------------------------------------------//
   bool              SetSleeveRow(const string name, const double &positions[])
     {
      if(!m_finalized)
        {
         Print("CV34EnsembleStepper: SetSleeveRow before Finalize");
         return false;
        }
      int i = -1;
      for(int k = 0; k < m_nsleeves; k++)
         if(m_sleeve_name[k] == name) { i = k; break; }
      if(i < 0)
        {
         Print("CV34EnsembleStepper: SetSleeveRow unknown sleeve '", name, "'");
         return false;
        }
      int n = m_sl_sym_count[i];
      if(ArraySize(positions) != n)
        {
         Print("CV34EnsembleStepper: SetSleeveRow '", name, "' size ",
               ArraySize(positions), " != ", n);
         return false;
        }
      int st = m_sl_sym_start[i];
      for(int j = 0; j < n; j++)
         m_row_val[st + j] = positions[j];
      m_row_set[i] = true;
      return true;
     }

   //---------------------------------------------------------------//
   // Step — Python step(ts_ns, sleeve_rows) -> {sym: net position}.//
   // t: bar server-time (datetime, seconds).  Python computes      //
   //   hour = (ts_ns // HOUR_NS) % 24                              //
   // on nanoseconds; on seconds that is (t // 3600) % 24 — same    //
   // value for the same server timestamp (t >= 0 always in MT5).   //
   // Fills out[SymbolCount()] in Symbols() order, clears staged    //
   // rows (each bar must re-stage EVERY sleeve, like the Python    //
   // dict lookup which would KeyError on a missing sleeve).        //
   //---------------------------------------------------------------//
   bool              Step(const datetime t, double &out[])
     {
      if(!m_finalized)
        {
         Print("CV34EnsembleStepper: Step before Finalize");
         return false;
        }
      for(int i = 0; i < m_nsleeves; i++)
         if(!m_row_set[i])
           {
            Print("CV34EnsembleStepper: Step missing sleeve row '",
                  m_sleeve_name[i], "'");
            return false;
           }
      long hour = ((long)t / 3600) % 24;
      bool overnight = (hour >= V34_ENS_OVERNIGHT_H_GE) ||
                       (hour <  V34_ENS_OVERNIGHT_H_LT);
      ArrayResize(out, m_nsym);
      for(int q = 0; q < m_nsym; q++)
        {
         // exact fold: first contributor ASSIGNS, the rest ADD
         double acc   = 0.0;
         bool   first = true;
         int    st    = m_ct_start[q];
         int    ne    = m_ct_count[q];
         for(int k = 0; k < ne; k++)
           {
            int    si = m_ct_sleeve[st + k];
            double v  = m_row_val[m_sl_sym_start[si] + m_ct_pos[st + k]]
                        * m_ct_w[st + k];
            if(first)
              {
               acc   = v;        // `tot = contrib if tot is None`
               first = false;
              }
            else
               acc = acc + v;    // tot.add(contrib)
           }
         acc = acc * V34_ENS_SCALE;   // combine(...) * SCALE, post-sum
         // hard limits (frozen apply_hard_limits), post-scale.
         // NaN acc: every comparison false -> passes through, as in Python.
         if(m_is_cross[q])
           {
            if(acc > V34_ENS_CROSS_CAP)
               acc = V34_ENS_CROSS_CAP;
            else if(acc < -V34_ENS_CROSS_CAP)
               acc = -V34_ENS_CROSS_CAP;
           }
         if(overnight && m_is_gold[q])
           {
            double g = m_gold_cap;
            if(acc > g)
               acc = g;
            else if(acc < -g)
               acc = -g;
           }
         out[q] = acc;
        }
      // clear staging: the shell is stateless across bars
      for(int i = 0; i < m_nsleeves; i++)
         m_row_set[i] = false;
      return true;
     }

   //---------------------------------------------------------------//
   // GetState — serialize the configuration (== the Python state:  //
   // the stepper is stateless across bars).  Format:               //
   //   FMA3ENSv1|<name>:<sym>;<sym>;...|...|gold_cap=<%.17g>       //
   // symbols/contrib are pure derivations, rebuilt by SetState.    //
   //---------------------------------------------------------------//
   string            GetState() const
     {
      if(!m_finalized)
         return "";
      string s = "FMA3ENSv1";
      for(int i = 0; i < m_nsleeves; i++)
        {
         s += "|" + m_sleeve_name[i] + ":";
         int st = m_sl_sym_start[i], n = m_sl_sym_count[i];
         for(int j = 0; j < n; j++)
           {
            if(j > 0)
               s += ";";
            s += m_sl_syms[st + j];
           }
        }
      s += "|gold_cap=" + StringFormat("%.17g", m_gold_cap);
      return s;
     }

   bool              SetState(const string state)
     {
      string parts[];
      int np = StringSplit(state, '|', parts);
      if(np < 2 || parts[0] != "FMA3ENSv1")
        {
         Print("CV34EnsembleStepper: SetState bad header");
         return false;
        }
      Reset();
      double gc_in = V34Nan();
      bool   gc_seen = false;
      for(int p = 1; p < np; p++)
        {
         if(StringFind(parts[p], "gold_cap=") == 0)
           {
            gc_in   = StringToDouble(StringSubstr(parts[p], 9));
            gc_seen = true;
            continue;
           }
         int colon = StringFind(parts[p], ":");
         if(colon < 0)
           {
            Print("CV34EnsembleStepper: SetState bad sleeve entry '",
                  parts[p], "'");
            Reset();
            return false;
           }
         string name = StringSubstr(parts[p], 0, colon);
         string rest = StringSubstr(parts[p], colon + 1);
         string syms[];
         int n = 0;
         if(StringLen(rest) > 0)
            n = StringSplit(rest, ';', syms);
         else
            ArrayResize(syms, 0);
         if(!AddSleeve(name, syms))
           {
            Reset();
            return false;
           }
        }
      if(!Finalize())
        {
         Reset();
         return false;
        }
      // gold_cap is derived; verify against the serialized value
      if(gc_seen && gc_in == gc_in && gc_in != m_gold_cap)
        {
         Print("CV34EnsembleStepper: SetState gold_cap mismatch ",
               StringFormat("%.17g", gc_in), " != ",
               StringFormat("%.17g", m_gold_cap));
         Reset();
         return false;
        }
      return true;
     }
  };

#endif // FMA3V34_ENSEMBLE_MQH
