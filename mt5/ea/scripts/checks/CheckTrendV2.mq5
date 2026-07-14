//+------------------------------------------------------------------+
//| CheckTrendV2.mq5 — compile/smoke gate for Sat/TrendV2.mqh    |
//| Instantiates CSatTrendV2Stepper, feeds 170 synthetic daily bars  |
//| (>= 125-bar warmup so the full 6-lookback ensemble goes live)    |
//| with pre-listing NaNs (sym 2, t<12) and interior missing bars    |
//| (sym 4 @ t=25, sym 3 @ t=150), prints held/target/sig milestones |
//| plus a GetState/SetState warm-start round-trip.                  |
//| NO trading functions.                                            |
//|                                                                  |
//| PYTHON GOLDEN (generated 2026-07-14 by running the validated     |
//| research/bpure/steppers/trend_v2_stepper.py on this exact feed — |
//| scratchpad/gen_trendv2_golden.py).  Terminal output must match   |
//| (ewm fma residual ~1e-16 rel; invisible at %.6g unless a         |
//| hysteresis comparison sits on a knife edge):                     |
//|  t=  9 held: 0 0 0 0 0        tgt: nan x5   sig: nan x5          |
//|  t= 15 held: 0 0 0 0 0        tgt: nan x5                        |
//|        sig: 0.00614626 0.00429301 nan 0.00192126 0.00130033      |
//|  t= 50 held: 0 0 0 0 0        tgt: nan x5                        |
//|        sig: 0.00633721 0.00400492 0.00244269 0.00187354          |
//|             0.00130754                                           |
//|  t=124 held: 0 0 0 0 0        tgt: nan x5 (125-lb not yet live)  |
//|  t=125 held: 0.454542 0.467169 0 0.333914 0.763272               |
//|        tgt : 0.454542 0.467169 nan 0.333914 0.763272             |
//|  t=130 held: 0.736606 0.374042 0 0.772611 0.920788               |
//|        tgt : 0.736606 0.374042 nan 0.772611 0.949896             |
//|  t=140 held: 0.403203 0.396411 0.893958 0.421593 0.436917        |
//|  t=150 held: 0.755926 0.242284 0.335676 0.775519 0.922338        |
//|        tgt : 0.833974 0.203082 0.459595 nan nan                  |
//|        (sym3 NaN close; sym4 lookback-125 hits the t=25 NaN bar  |
//|         -> BOTH hold: no scheduled-target leak on missing bars)  |
//|  t=151 held: 0.755926 0.242284 0.522782 0.775519 0.922338        |
//|  t=160 held: 0.408367 0.39783 0.949293 0.415991 0.440558         |
//|  t=169 held: 0.775352 0.239989 0.525385 0.927547 0.923847        |
//|  roundtrip A == B held[169], identical: true                     |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Sat/TrendV2.mqh>

#define CTV2_NBARS 170

//+------------------------------------------------------------------+
//| synthetic close feed — MUST stay identical to the golden script  |
//+------------------------------------------------------------------+
double CloseAt(const int i, const int t)
  {
   if(i == 2 && t < 12)
      return SatNan();            // pre-listing NaN run
   if(i == 4 && t == 25)
      return SatNan();            // interior missing bar (warmup era)
   if(i == 3 && t == 150)
      return SatNan();            // interior missing bar (live era)
   return 100.0 * (1.0 + i) + 3.0 * MathSin(0.35 * t + 1.7 * i) + 0.15 * t;
  }

string Row5(const double &v[])
  {
   string s = "";
   for(int i = 0; i < 5; i++)
      s += StringFormat("%.6g ", v[i]);
   return s;
  }

bool IsMark(const int t)
  {
   return (t == 9 || t == 15 || t == 50 || t == 124 || t == 125 ||
           t == 130 || t == 140 || t == 150 || t == 151 ||
           t == 160 || t == 169);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   CSatTrendV2Stepper st;
   double closes[5];
   double held[];
   string snap = "";

   for(int t = 0; t < CTV2_NBARS; t++)
     {
      for(int i = 0; i < 5; i++)
         closes[i] = CloseAt(i, t);
      st.Step(closes, held);
      if(t == 130)
         snap = st.GetState();
      if(IsMark(t))
        {
         PrintFormat("t=%3d held: %s", t, Row5(held));
         PrintFormat("      tgt : %s", Row5(st.m_last_target));
         PrintFormat("      sig : %s", Row5(st.m_last_sig_d));
        }
     }

   // ---- GetState/SetState warm-start round-trip ---------------------
   CSatTrendV2Stepper st2;
   bool ok = st2.SetState(snap);
   PrintFormat("SetState(t=130 snapshot) ok=%d (state len=%d)",
               (int)ok, StringLen(snap));
   double held2[];
   ArrayResize(held2, 5);
   for(int t = 131; t < CTV2_NBARS; t++)
     {
      for(int i = 0; i < 5; i++)
         closes[i] = CloseAt(i, t);
      st2.Step(closes, held2);
     }
   PrintFormat("roundtrip A held[169]: %s", Row5(held));
   PrintFormat("roundtrip B held[169]: %s", Row5(held2));
   bool same = true;
   for(int i = 0; i < 5; i++)
     {
      double a = held[i], b = held2[i];
      bool eq = ((a != a && b != b) || a == b);
      if(!eq)
         same = false;
     }
   PrintFormat("roundtrip identical: %s", same ? "true" : "FALSE");

   // reject a corrupted syms list (Python assert equivalent)
   string bad = snap;
   StringReplace(bad, "XAGUSD", "XXXUSD");
   CSatTrendV2Stepper st3;
   PrintFormat("SetState(bad syms) rejected=%d", (int)!st3.SetState(bad));

   Print("CheckTrendV2: done");
  }
//+------------------------------------------------------------------+
