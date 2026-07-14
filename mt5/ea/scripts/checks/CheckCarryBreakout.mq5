//+------------------------------------------------------------------+
//| CheckCarryBreakout.mq5 — compile/smoke gate for                  |
//| FMA3v34/CarryBreakout.mqh (CV34CarryBreakoutStepper).            |
//|                                                                  |
//| Instantiates the stepper and feeds synthetic union hourly bars   |
//| (8 bars/day x 66 days = 528 bars) with scattered NaN closes and  |
//| one leading-NaN symbol, so every code path fires:                |
//|  - carry day rolls (65 rolls -> momentum gate active from #64)   |
//|  - policy-rate lookups at epoch days 19300+ (2022-11)            |
//|  - Donchian fast system warm at bar 480 -> long entries on the   |
//|    uptrend -> nonzero breakout positions                         |
//|  - gross cap + clip                                              |
//|  - GetState/SetState JSON round trip: load into a second         |
//|    instance, step both 16 more bars, positions and re-serialized |
//|    states must match exactly.                                    |
//| NO trading functions.                                            |
//|                                                                  |
//| PYTHON GOLDEN (measured 2026-07-14, carry_breakout_stepper.py on |
//| this exact feed) — terminal Print output must match (ewm values  |
//| to ~1e-15 rel, everything else exact):                           |
//|  rate USD@19300=3.875 JPY@19300=-0.1 EUR@18000=nan               |
//|  bar 0   gross=0 (all four pos 0)                                |
//|  bar 100 gross=0    bar 479 gross=0                              |
//|  bar 480 gross=3 USDJPY=0 XAUUSD=0.3 USA500=0.3 USTEC=0          |
//|  bar 527 gross=3 USDJPY=0.2382352941 XAUUSD=0.1808823529         |
//|          USA500=0.1808823529 USTEC=0                             |
//|  last carry roll: day=19364 n_dir=5 n_sig=5                      |
//|          USDJPY net=3.275 dir=1 sig=1 w=0.4                      |
//|  vol_ewm[USDJPY]=1.783591608e-07 atr_ewm[XAUUSD]=0.0008212352946 |
//|  dc_len=64 sysf[XAUUSD] state=1 size=0.4 best=2.482475853        |
//|  round-trip: pos maxdiff=0 nan_mismatch=0 reserialized_equal=1   |
//|  (python json state length for reference: 197456 chars)          |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <FMA3v34/CarryBreakout.mqh>

//+------------------------------------------------------------------+
void MakeCloses(const int i, double &closes[])
  {
   double nan = V34Nan();
   for(int j = 0; j < V34CB_N_SYM; j++)
     {
      double base = 1.0 + 0.05 * j;
      double c = base * (1.0 + 0.0004 * i) + 0.001 * MathSin(0.7 * i + j);
      closes[j] = c;
      if((i + j) % 37 == 0)
         closes[j] = nan;              // scattered missing bars
      if(j == 31 && i < 60)
         closes[j] = nan;              // leading-NaN symbol (USTEC)
     }
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   CV34CarryBreakoutStepper st;
   double closes[V34CB_N_SYM];
   double pos[V34CB_N_SYM];

   const long day0 = 19300;            // 2022-11-04
   const int  bars_per_day = 8;
   const int  n_bars = bars_per_day * 66;   // 528

   // sanity: policy rate lookups (USD 3.875 from 19299; JPY -0.10;
   // NaN before first table row)
   PrintFormat("rate USD@19300=%.10g JPY@19300=%.10g EUR@18000=%.10g",
               st.Rate(0, 19300), st.Rate(3, 19300), st.Rate(1, 18000));

   for(int i = 0; i < n_bars; i++)
     {
      MakeCloses(i, closes);
      st.Step(day0 + i / bars_per_day, closes, pos);
      if(i == 0 || i == 100 || i == 479 || i == 480 || i == n_bars - 1)
        {
         double gross = 0.0;
         for(int j = 0; j < V34CB_N_SYM; j++)
            gross += MathAbs(pos[j]);
         PrintFormat("bar %d gross=%.10g USDJPY=%.10g XAUUSD=%.10g "
                     "USA500=%.10g USTEC=%.10g",
                     i, gross, pos[20], pos[21], pos[30], pos[31]);
        }
     }

   // last carry roll debug (day stamped, live pairs, USDJPY row)
   int n_dir = 0, n_sig = 0;
   for(int j = 0; j < V34CB_N_FX; j++)
     {
      if(st.m_last_dir[j] != 0.0)
         n_dir++;
      if(st.m_last_sig[j] != 0.0)
         n_sig++;
     }
   PrintFormat("last carry roll: day=%s n_dir=%d n_sig=%d "
               "USDJPY net=%.10g dir=%g sig=%g w=%.10g",
               IntegerToString(st.m_last_day), n_dir, n_sig,
               st.m_last_net[20], st.m_last_dir[20], st.m_last_sig[20],
               st.m_last_w[20]);
   PrintFormat("vol_ewm[USDJPY]=%.10g atr_ewm[XAUUSD]=%.10g dc_len=%d "
               "sysf[XAUUSD] state=%d size=%.10g best=%.10g",
               st.m_vol_ewm[20].Value(), st.m_atr_ewm[0].Value(),
               st.m_dc_len, st.m_sys_f[0].m_state, st.m_sys_f[0].m_size,
               st.m_sys_f[0].m_best);

   // ---- state round trip -------------------------------------------
   string s1 = st.GetState();
   PrintFormat("state length=%d prefix=%s...",
               StringLen(s1), StringSubstr(s1, 0, 60));

   CV34CarryBreakoutStepper st2;
   if(!st2.SetState(s1))
     {
      Print("SetState FAILED");
      return;
     }

   double pos2[V34CB_N_SYM];
   double maxdiff = 0.0;
   int nan_mm = 0;
   for(int i = n_bars; i < n_bars + 16; i++)
     {
      MakeCloses(i, closes);
      long day = day0 + i / bars_per_day;
      st.Step(day, closes, pos);
      st2.Step(day, closes, pos2);
      for(int j = 0; j < V34CB_N_SYM; j++)
        {
         bool n1 = (pos[j] != pos[j]);
         bool n2 = (pos2[j] != pos2[j]);
         if(n1 != n2)
            nan_mm++;
         else if(!n1)
           {
            double d = MathAbs(pos[j] - pos2[j]);
            if(d > maxdiff)
               maxdiff = d;
           }
        }
     }
   string s_a = st.GetState();
   string s_b = st2.GetState();
   PrintFormat("round-trip: pos maxdiff=%.3g nan_mismatch=%d "
               "reserialized_equal=%d",
               maxdiff, nan_mm, (int)(s_a == s_b));

   Print("CheckCarryBreakout: done");
  }
//+------------------------------------------------------------------+
