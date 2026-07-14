//+------------------------------------------------------------------+
//| CheckSeasonalCrypto.mq5 — compile/smoke gate for                 |
//| FMA3v34/SeasonalCrypto.mqh.  Instantiates                        |
//| CV34SeasonalCryptoStepper, feeds 60 synthetic hourly bars        |
//| (pre-inception NaN SOL closes + interior NaN ETH closes),        |
//| prints emitted rows, round-trips GetState/SetState (JSON) and    |
//| verifies bit-identical continuation over 20 more bars incl. a    |
//| day rollover, then Finalize().  NO trading functions.            |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <FMA3v34/SeasonalCrypto.mqh>

// bitwise-or-both-NaN equality
bool SameD(const double a, const double b)
  {
   if(a != a && b != b)
      return true;
   return (a == b);
  }

// deterministic synthetic feed for bar i (hourly union grid)
void Feed(const int i, double &xr, double &btc, double &eth, double &sol)
  {
   xr  = 0.0002 * ((i % 7) - 3);              // never NaN (feed contract)
   btc = 40000.0 + 25.0 * i + 300.0 * ((i % 5) - 2);
   eth = 2200.0 + 3.0 * i;
   sol = (i < 6) ? V34Nan() : 95.0 + 0.5 * i; // NaN before inception
   if(i % 13 == 5)
      eth = V34Nan();                         // interior NaN close
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   CV34SeasonalCryptoStepper st;
   const long ts0 = 1704067200;               // 2024.01.01 00:00 UTC
   long   ets;
   double pos[];
   int    emitted = 0;
   for(int i = 0; i < 60; i++)
     {
      double xr, btc, eth, sol;
      Feed(i, xr, btc, eth, sol);
      datetime t = (datetime)(ts0 + (long)i * 3600);
      if(st.Step(t, xr, btc, eth, sol, ets, pos))
        {
         emitted++;
         if(i <= 3 || i >= 57 || (i % 23) == 0)
            PrintFormat("bar %2d emit ts_ns=%I64d XAU=%.12f BTC=%.12f ETH=%.12f SOL=%.12f",
                        i, ets, pos[0], pos[1], pos[2], pos[3]);
        }
      else
         PrintFormat("bar %2d no emit (first call)", i);
     }

   // --- state round-trip: JSON out -> fresh stepper -> JSON out ---
   string s1 = st.GetState();
   CV34SeasonalCryptoStepper st2;
   bool ok = st2.SetState(s1);
   string s2 = st2.GetState();
   PrintFormat("state len=%d setstate_ok=%s json_identical=%s",
               StringLen(s1), ok ? "true" : "false",
               (s1 == s2) ? "true" : "false");
   Print("state head: ", StringSubstr(s1, 0, 160));

   // --- lockstep continuation over 20 more bars (crosses a day) ---
   bool same = true;
   for(int i = 60; i < 80; i++)
     {
      double xr, btc, eth, sol;
      Feed(i, xr, btc, eth, sol);
      datetime t = (datetime)(ts0 + (long)i * 3600);
      long   ta, tb;
      double pa[], pb[];
      bool ea = st.Step(t, xr, btc, eth, sol, ta, pa);
      bool eb = st2.Step(t, xr, btc, eth, sol, tb, pb);
      if(ea != eb)
        {
         same = false;
         break;
        }
      if(ea)
        {
         if(ta != tb)
            same = false;
         for(int k = 0; k < 4; k++)
            if(!SameD(pa[k], pb[k]))
               same = false;
        }
     }

   long   fta, ftb;
   double fa[], fb[];
   bool ha = st.Finalize(fta, fa);
   bool hb = st2.Finalize(ftb, fb);
   bool fsame = (ha && hb && fta == ftb);
   if(fsame)
      for(int k = 0; k < 4; k++)
         if(!SameD(fa[k], fb[k]))
            fsame = false;
   PrintFormat("emitted=%d lockstep_same=%s finalize ts_ns=%I64d row=[%.12f %.12f %.12f %.12f] finalize_same=%s",
               emitted, same ? "true" : "false", fta, fa[0], fa[1], fa[2], fa[3],
               fsame ? "true" : "false");
   PrintFormat("CHECK %s", (same && fsame && ok && s1 == s2) ? "PASS" : "FAIL");
  }
//+------------------------------------------------------------------+
