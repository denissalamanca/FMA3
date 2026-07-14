//+------------------------------------------------------------------+
//| CheckV34Math.mq5 — compile/smoke gate for Sat/SatMath.mqh    |
//| Instantiates every primitive, steps synthetic sequences with     |
//| interior NaNs, prints values.  NO trading functions.             |
//|                                                                  |
//| PYTHON GOLDEN (generated 2026-07-14 from the validated steppers  |
//| crisis_stepper / consolidate_p1c_stepper / carry_breakout_stepper|
//| on the exact seq below) — the terminal Print output must match:  |
//|  ewm_mean(span=3): 1 1.666666667 1.666666667 3.363636364         |
//|    3.148148148 3.148148148 4.450549451 4.771689498 3.277894737   |
//|    4.689969605                                                   |
//|  ewm_mean(span=20,minp=4): nan nan nan nan 2.645282258           |
//|    2.645282258                                                   |
//|  ewm_std(span=5,minp=3) BOTH flavors: nan nan nan 1.619457165    |
//|    1.105882889 1.105882889 1.461967381 1.214448768 1.670109856   |
//|    1.913119397                                                   |
//|  ring std/mean/max(w=4,minp=2): [nan nan nan] [0.707107 1.5 2]   |
//|    [0.707107 1.5 2] [1.52753 2.33333 4] [1 3 4] [0.707107 3.5 4] |
//|    [1 4 5] [1.1547 4.33333 5] [1.73205 4 5] [1.73205 4.5 6]      |
//|  roll_std(w=3,minp=3): nan x7 then 1.732050808 2.081665999       |
//|  sma(w=3): nan x8 then 4 4.333333333                             |
//|  donchian(w=3) hi/lo prior-window: [nan nan] x4 [4 2] [4 3]      |
//|    [4 3] [5 3] [5 5] [5 2]                                       |
//|  banker: 0.5->0 1.5->2 2.5->2 3.5->4 -0.5->-0 -1.5->-2           |
//|    2.4->2 2.6->3                                                 |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Sat/SatMath.mqh>

//+------------------------------------------------------------------+
void OnStart()
  {
   double nan = SatNan();
   double inf = SatInf();

   // ---- NaN / IEEE helpers ----------------------------------------
   PrintFormat("nan: isnan=%d isobs=%d isfinite=%d  inf: isfinite=%d",
               (int)SatIsNan(nan), (int)SatIsObs(nan),
               (int)SatIsFinite(nan), (int)SatIsFinite(inf));
   PrintFormat("npdiv: 1/0=%g -1/0=%g 1/-0=%g 0/0=%g nan/2=%g 6/3=%g",
               SatNpDiv(1.0, 0.0), SatNpDiv(-1.0, 0.0),
               SatNpDiv(1.0, -0.0), SatNpDiv(0.0, 0.0),
               SatNpDiv(nan, 2.0), SatNpDiv(6.0, 3.0));
   PrintFormat("sign: (-3)=%g (0)=%g (2)=%g (nan)=%g",
               SatSign(-3.0), SatSign(0.0), SatSign(2.0), SatSign(nan));

   // ---- BankerRound: ties go to even, never half-away --------------
   PrintFormat("banker: 0.5=%g 1.5=%g 2.5=%g 3.5=%g -0.5=%g -1.5=%g 2.4=%g 2.6=%g nan=%g",
               SatBankerRound(0.5), SatBankerRound(1.5),
               SatBankerRound(2.5), SatBankerRound(3.5),
               SatBankerRound(-0.5), SatBankerRound(-1.5),
               SatBankerRound(2.4), SatBankerRound(2.6),
               SatBankerRound(nan));

   // ---- synthetic sequence with interior NaN ------------------------
   double seq[10];
   seq[0] = 1.0;  seq[1] = 2.0;  seq[2] = nan;  seq[3] = 4.0;  seq[4] = 3.0;
   seq[5] = nan;  seq[6] = 5.0;  seq[7] = 5.0;  seq[8] = 2.0;  seq[9] = 6.0;

   // ---- CSatEwmMean (span=3, minp=1) --------------------------------
   CSatEwmMean em;
   em.Init(3.0, 1);
   string s = "ewm_mean(span=3): ";
   for(int i = 0; i < 10; i++)
      s += StringFormat("%.10g ", em.Step(seq[i]));
   Print(s);

   // ---- CSatEwmMean minp gating (trend_v2 style, minp=4) ------------
   CSatEwmMean em2;
   em2.Init(20.0, 4);
   s = "ewm_mean(span=20,minp=4): ";
   for(int i = 0; i < 6; i++)
      s += StringFormat("%.10g ", em2.Step(seq[i]));
   Print(s);

   // ---- CSatEwmStd (span=5, minp=3), both neg-var flavors -----------
   CSatEwmStd es;
   es.Init(5.0, 3, true);       // crisis flavor (zsqrt clamp)
   CSatEwmStd es2;
   es2.Init(5.0, 3, false);     // consolidate flavor
   s = "ewm_std(span=5,minp=3): ";
   string s2 = "ewm_std(consolidate flavor): ";
   for(int i = 0; i < 10; i++)
     {
      s  += StringFormat("%.10g ", es.Step(seq[i]));
      s2 += StringFormat("%.10g ", es2.Step(seq[i]));
     }
   Print(s);
   Print(s2);

   // ---- CSatRing + two-pass scans (window=4, minp=2) ----------------
   CSatRing ring;
   ring.Init(4);
   s = "ring std/mean/max/min(w=4,minp=2): ";
   for(int i = 0; i < 10; i++)
     {
      ring.Push(seq[i]);
      s += StringFormat("[%.6g %.6g %.6g %.6g] ",
                        ring.StdDdof1(4, 2), ring.Mean(4, 2),
                        ring.Max(4, 2), ring.Min(4, 2));
     }
   Print(s);

   // ---- CSatRollStd wrapper (window=3, minp=3) -----------------------
   CSatRollStd rs;
   rs.Init(3, 3);
   s = "roll_std(w=3,minp=3): ";
   for(int i = 0; i < 10; i++)
      s += StringFormat("%.10g ", rs.Step(seq[i]));
   Print(s);

   // ---- CSatSma (window=3, minp==window, NaN poisons window) --------
   CSatSma sma;
   sma.Init(3);
   s = "sma(w=3): ";
   for(int i = 0; i < 10; i++)
      s += StringFormat("%.10g ", sma.Step(seq[i]));
   Print(s);

   // ---- CSatDonchian (w=3): Query BEFORE Push each bar (shift-1) ----
   CSatDonchian dmax;
   dmax.Init(3, true);
   CSatDonchian dmin;
   dmin.Init(3, false);
   s = "donchian(w=3) hi/lo prior-window: ";
   for(int i = 0; i < 10; i++)
     {
      double hi = dmax.Query();
      double lo = dmin.Query();
      dmax.Push(seq[i]);
      dmin.Push(seq[i]);
      s += StringFormat("[%.6g %.6g] ", hi, lo);
     }
   Print(s);

   // ---- CSV helpers --------------------------------------------------
   string fields[];
   int nf = SatCsvSplit("1.25,nan,,-inf,7", fields);
   s = StringFormat("csv nf=%d vals: ", nf);
   for(int i = 0; i < nf; i++)
      s += StringFormat("%g ", SatParseDouble(fields[i]));
   Print(s);

   Print("CheckV34Math: done");
  }
//+------------------------------------------------------------------+
