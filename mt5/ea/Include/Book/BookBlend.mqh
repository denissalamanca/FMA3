//+------------------------------------------------------------------+
//| Book/BookBlend.mqh - static_blend(w) live blender (model v3).    |
//|                                                                  |
//| 1:1 MQL5 port of the model-of-record blend statement             |
//| (model/v3/reproduce.py::static_blend, verified -> EUR 3,872,872  |
//| IC s=1.6 / EUR 1,332,404 FTMO s=0.7):                            |
//|                                                                  |
//|   j            = w*a_h + (1-w)*b_h                               |
//|   book[h,sym]  = f_core[h,sym]*((w*a_h)/j)                       |
//|                + f_sat[h,sym]*(((1-w)*b_h)/j)                    |
//|                                                                  |
//| where a_h,b_h are the native standalone equity MULTIPLES         |
//| (Core = ex-v7 band engine, Sat = ex-v34 sleeve ensemble), both   |
//| 1.0 at t0, asof-ffilled onto the hourly union grid. The scale    |
//| dial s is NOT applied here (execution-side, like the exporter).  |
//|                                                                  |
//| NETTING (scripts/export_book_frac_v3.py semantics): the output   |
//| column set is the ORDINALLY SORTED UNION of the Core legs (8)    |
//| and the Sat book columns (31); the 6 shared symbols receive      |
//| both terms in ONE addition (identical to pandas reindex          |
//| fill_value=0.0 followed by the elementwise mul/add above - a     |
//| missing leg contributes literal 0.0*coeff to the sum, which is   |
//| what this class computes too, preserving IEEE-754 semantics).    |
//|                                                                  |
//| FLOATING-POINT CONTRACT (bit-exactness vs numpy float64):        |
//|   * (1-w) is computed ONCE at Init as 1.0 - w (Python `1 - w`);  |
//|   * op order per hour/leg is EXACTLY:                            |
//|       j  = (w*a) + (ow*b);   cc = (w*a)/j;   cs = (ow*b)/j;      |
//|       out = fc*cc + fs*cs;                                       |
//|     MQL5 has no FMA contraction and all ops are IEEE-754 binary64|
//|     - same as the numpy elementwise kernels, so the port is      |
//|     bit-exact by construction (validated by TestBlend.mq5 /      |
//|     research/bpure/blend/validate_blend.py vs the golden netted  |
//|     stream FMA3_fed_frac_v3.csv).                                |
//|   * no guard is added on j (the model has none; a_h,b_h > 0 on   |
//|     the frozen curves so j > 0 for w in [0,1]).                  |
//|                                                                  |
//| Symbol names here are MODEL names (USA500, DAX, ...). The        |
//| repo->broker map (USA500=US500, DAX=DE40) is an EMISSION concern |
//| of the caller, exactly like the exporter.                        |
//|                                                                  |
//| SCOPE: this class blends FROZEN/externally-supplied a,b and      |
//| frac rows. Computing a,b LIVE (CoreSim / Sat native equity) is a |
//| separate, still-open EA question - see MEMORY stable-model-v3.   |
//+------------------------------------------------------------------+
#ifndef BOOK_BOOKBLEND_MQH
#define BOOK_BOOKBLEND_MQH

class CBookBlend
  {
private:
   double            m_w;         // Core capital share (w=0.70 in model v3)
   double            m_ow;        // 1.0 - m_w, computed once at Init
   int               m_ncore;     // Core leg count (8 in model v3)
   int               m_nsat;      // Sat book column count (31 in model v3)
   int               m_nnet;      // netted union column count (33 in model v3)
   string            m_net[];     // union symbols, ordinal ascending (MODEL names)
   int               m_core_ix[]; // per net col: index into f_core[] or -1
   int               m_sat_ix[];  // per net col: index into f_sat[]  or -1
   bool              m_ready;

public:
   // ordinal (code-unit) string compare == Python str '<' for these
   // all-ASCII symbol names; avoids any locale/collation surprises.
   // Public: emission harnesses reuse it for broker-name row ordering.
   static int        CmpOrdinal(const string a, const string b)
     {
      int la = StringLen(a), lb = StringLen(b);
      int n = (la < lb) ? la : lb;
      for(int i = 0; i < n; i++)
        {
         ushort ca = StringGetCharacter(a, i);
         ushort cb = StringGetCharacter(b, i);
         if(ca != cb)
            return (ca < cb) ? -1 : 1;
        }
      if(la == lb)
         return 0;
      return (la < lb) ? -1 : 1;
     }

private:
   static int        IndexOf(const string &arr[], const int n, const string s)
     {
      for(int i = 0; i < n; i++)
         if(arr[i] == s)
            return i;
      return -1;
     }

public:
                     CBookBlend() : m_w(0.0), m_ow(0.0), m_ncore(0),
                                    m_nsat(0), m_nnet(0), m_ready(false) {}

   //--- build the netted union = sorted(set(core)|set(sat)) and the
   //--- per-column source indices. false on empty/duplicate inputs.
   bool              Init(const double w, const string &core_syms[],
                          const string &sat_syms[])
     {
      m_ready = false;
      m_ncore = ArraySize(core_syms);
      m_nsat  = ArraySize(sat_syms);
      if(m_ncore <= 0 || m_nsat <= 0)
         return false;
      // duplicates WITHIN one list would make the pandas column
      // reindex semantics ambiguous - refuse.
      for(int i = 0; i < m_ncore; i++)
         if(IndexOf(core_syms, i, core_syms[i]) >= 0)
            return false;
      for(int i = 0; i < m_nsat; i++)
         if(IndexOf(sat_syms, i, sat_syms[i]) >= 0)
            return false;

      // union (order of collection irrelevant - sorted below)
      ArrayResize(m_net, m_ncore + m_nsat);
      int n = 0;
      for(int i = 0; i < m_ncore; i++)
         m_net[n++] = core_syms[i];
      for(int i = 0; i < m_nsat; i++)
         if(IndexOf(m_net, n, sat_syms[i]) < 0)
            m_net[n++] = sat_syms[i];
      ArrayResize(m_net, n);
      m_nnet = n;

      // insertion sort, ordinal ascending (== Python sorted())
      for(int i = 1; i < m_nnet; i++)
        {
         string key = m_net[i];
         int k = i - 1;
         while(k >= 0 && CmpOrdinal(m_net[k], key) > 0)
           {
            m_net[k + 1] = m_net[k];
            k--;
           }
         m_net[k + 1] = key;
        }

      ArrayResize(m_core_ix, m_nnet);
      ArrayResize(m_sat_ix,  m_nnet);
      for(int k = 0; k < m_nnet; k++)
        {
         m_core_ix[k] = IndexOf(core_syms, m_ncore, m_net[k]);
         m_sat_ix[k]  = IndexOf(sat_syms,  m_nsat,  m_net[k]);
        }

      m_w  = w;
      m_ow = 1.0 - w;         // Python's (1 - w), ONCE (1-0.70 is NOT 0.30 in binary64)
      m_ready = true;
      return true;
     }

   int               NetCount()                  const { return m_nnet; }
   string            NetSymbol(const int k)      const { return (k >= 0 && k < m_nnet) ? m_net[k] : ""; }
   int               CoreIndexOf(const int k)    const { return (k >= 0 && k < m_nnet) ? m_core_ix[k] : -1; }
   int               SatIndexOf(const int k)     const { return (k >= 0 && k < m_nnet) ? m_sat_ix[k] : -1; }
   double            CoreWeight()                const { return m_w; }
   bool              Ready()                     const { return m_ready; }

   //--- ONE hour: f_core (Core-leg order given at Init), f_sat (Sat
   //--- order given at Init), a/b = native equity multiples asof this
   //--- hour. out[] resized to NetCount(), NetSymbol() order.
   bool              Step(const double &f_core[], const double &f_sat[],
                          const double a, const double b, double &out[])
     {
      if(!m_ready || ArraySize(f_core) != m_ncore || ArraySize(f_sat) != m_nsat)
         return false;
      // ---- op order is LAW (see header) ----
      double j  = m_w * a + m_ow * b;      // j  = (w*a) + ((1-w)*b)
      double cc = m_w * a / j;             // cc = (w*a)/j
      double cs = m_ow * b / j;            // cs = ((1-w)*b)/j
      ArrayResize(out, m_nnet);
      for(int k = 0; k < m_nnet; k++)
        {
         double fc = (m_core_ix[k] >= 0) ? f_core[m_core_ix[k]] : 0.0;
         double fs = (m_sat_ix[k]  >= 0) ? f_sat[m_sat_ix[k]]   : 0.0;
         out[k] = fc * cc + fs * cs;       // core term + sat term, one add
        }
      return true;
     }
  };

#endif // BOOK_BOOKBLEND_MQH
