//+------------------------------------------------------------------+
//| CheckCrisis.mq5 — compile/smoke gate for FMA3v34/Crisis.mqh      |
//| Instantiates CV34CrisisStepper, feeds 80 synthetic daily bars    |
//| (leading NaNs, one interior NaN, two stale-holiday rows), prints |
//| weights + diag, round-trips GetState/SetState and verifies bit-  |
//| identical continuation, and smokes V34CrisisExpandToHourly.      |
//| NO trading functions.                                            |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <FMA3v34/Crisis.mqh>

// deterministic LCG in [0,1): x = (1103515245 x + 12345) mod 2^31
long   g_seed = 42;
double Rnd()
  {
   g_seed = (1103515245 * g_seed + 12345) % 2147483648;
   if(g_seed < 0)
      g_seed += 2147483648;
   return (double)g_seed / 2147483648.0;
  }

// bitwise-or-both-NaN equality
bool SameD(const double a, const double b)
  {
   if(a != a && b != b)
      return true;
   return (a == b);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   double nan = V34Nan();
   const int NBARS = 80;

   // ---- synthetic daily close grid: 10 symbols x 80 bars -----------
   // start levels per V34CrisisInputSym order
   double base[V34CRISIS_NIN] =
     {15000.0, 28000.0, 7500.0, 34000.0, 4500.0, 15500.0,   // indices
      1900.0,                                               // XAUUSD
      95.0, 88.0, 108.0};                                   // JPY crosses
   double closes[80][V34CRISIS_NIN];
   double lvl[V34CRISIS_NIN];
   for(int i = 0; i < V34CRISIS_NIN; i++)
      lvl[i] = base[i];

   for(int t = 0; t < NBARS; t++)
     {
      bool holiday = (t == 12 || t == 40);      // stale ffilled closes
      for(int i = 0; i < V34CRISIS_NIN; i++)
        {
         if(!holiday)
           {
            double shock = (Rnd() - 0.5) * 0.02;            // +-1%
            if(t >= 25 && t <= 35)
               shock -= 0.008;                              // stress window
            lvl[i] = lvl[i] * (1.0 + shock);
           }
         closes[t][i] = lvl[i];
        }
      // leading NaNs: JP225 (idx 1) starts bar 5, CADJPY (idx 9) bar 8
      if(t < 5)
         closes[t][1] = nan;
      if(t < 8)
         closes[t][9] = nan;
      // one interior NaN close: UK100 (idx 2) at bar 30
      if(t == 30)
         closes[t][2] = nan;
     }

   datetime t0 = D'2024.01.01 00:00';

   // ---- main run: print selected bars -------------------------------
   CV34CrisisStepper st;
   SV34CrisisResult  res;
   double            row[V34CRISIS_NIN];
   for(int t = 0; t < NBARS; t++)
     {
      for(int i = 0; i < V34CRISIS_NIN; i++)
         row[i] = closes[t][i];
      datetime ts = (datetime)((long)t0 + (long)t * 86400);
      if(!st.Step(ts, row, res))
        {
         Print("CheckCrisis: FAIL step returned false at bar ", t);
         return;
        }
      if(t == 0 || t == 5 || t == 12 || t == 21 || t == 30 || t == 41
         || t == 61 || t == 65 || t == 79)
        {
         PrintFormat("bar %2d  w=[%.10g %.10g %.10g %.10g]  eff=%s",
                     t, res.w[0], res.w[1], res.w[2], res.w[3],
                     TimeToString(res.effective, TIME_DATE | TIME_MINUTES));
         PrintFormat("        br=%.10g vr=%.10g lev=%.10g dd=%.10g "
                     "trig_eq=%d s_eq=%.10g",
                     res.br, res.vr, res.lev, res.dd, res.trig_eq, res.s_eq);
         PrintFormat("        fr=%.10g fvr=%.10g flev=%.10g fma=%.10g "
                     "trig_fx=%d s_fx=%.10g au_ma=%.10g up_au=%d",
                     res.fr, res.fvr, res.flev, res.fma, res.trig_fx,
                     res.s_fx, res.au_ma, res.up_au);
         PrintFormat("        vol=[%.10g %.10g %.10g %.10g] "
                     "w_pre=[%.10g %.10g %.10g %.10g]",
                     res.vol[0], res.vol[1], res.vol[2], res.vol[3],
                     res.w_pre[0], res.w_pre[1], res.w_pre[2], res.w_pre[3]);
         PrintFormat("        level=[%s %s %s %s] gross=%.10g scale=%.10g",
                     res.has_level[0] ? (string)res.level[0] : "None",
                     res.has_level[1] ? (string)res.level[1] : "None",
                     res.has_level[2] ? (string)res.level[2] : "None",
                     res.has_level[3] ? (string)res.level[3] : "None",
                     res.gross, res.scale);
        }
     }

   // ---- warm-start round trip: B(40 bars) -> state -> C, then both
   //      step bars 40..79 and every w must be bit-identical ----------
   CV34CrisisStepper sb;
   SV34CrisisResult  rb, rc;
   for(int t = 0; t < 40; t++)
     {
      for(int i = 0; i < V34CRISIS_NIN; i++)
         row[i] = closes[t][i];
      sb.Step((datetime)((long)t0 + (long)t * 86400), row, rb);
     }
   double state[];
   int n = sb.GetState(state);
   PrintFormat("state size: %d (expect %d)", n, V34CRISIS_STATE_SIZE);

   CV34CrisisStepper sc;
   if(!sc.SetState(state))
     {
      Print("CheckCrisis: FAIL SetState rejected state");
      return;
     }
   bool ok = true;
   for(int t = 40; t < NBARS; t++)
     {
      for(int i = 0; i < V34CRISIS_NIN; i++)
         row[i] = closes[t][i];
      datetime ts = (datetime)((long)t0 + (long)t * 86400);
      sb.Step(ts, row, rb);
      sc.Step(ts, row, rc);
      for(int j = 0; j < V34CRISIS_NOUT; j++)
        {
         if(!SameD(rb.w[j], rc.w[j]) || !SameD(rb.s_eq, rc.s_eq)
            || !SameD(rb.vol[j], rc.vol[j]))
           {
            PrintFormat("MISMATCH bar %d sym %d: %.17g vs %.17g",
                        t, j, rb.w[j], rc.w[j]);
            ok = false;
           }
        }
     }
   Print("warm-start round trip: ", ok ? "PASS" : "FAIL");

   // ---- expand_to_hourly smoke --------------------------------------
   // daily effective stamps 10, 20, 30 with w = 0.5, NaN, -0.25;
   // hours 5..45 step 5 -> 0 0 .5 .5 .5(NaN skipped) .5 -.25 -.25 -.25
   long   deff[3];
   double dw[3];
   deff[0] = 10; dw[0] = 0.5;
   deff[1] = 20; dw[1] = nan;
   deff[2] = 30; dw[2] = -0.25;
   long hrs[9];
   for(int i = 0; i < 9; i++)
      hrs[i] = 5 + 5 * i;
   double hw[];
   V34CrisisExpandToHourly(deff, dw, hrs, hw);
   string s = "expand_to_hourly: ";
   for(int i = 0; i < 9; i++)
      s += StringFormat("%g ", hw[i]);
   Print(s);
   bool eok = (hw[0] == 0.0 && hw[1] == 0.0 && hw[2] == 0.5 && hw[3] == 0.5
               && hw[4] == 0.5 && hw[5] == 0.5 && hw[6] == -0.25
               && hw[7] == -0.25 && hw[8] == -0.25);
   Print("expand_to_hourly: ", eok ? "PASS" : "FAIL");

   Print("CheckCrisis: done");
  }
//+------------------------------------------------------------------+
