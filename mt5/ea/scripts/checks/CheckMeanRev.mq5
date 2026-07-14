//+------------------------------------------------------------------+
//| CheckMeanRev.mq5 — compile/smoke gate for Sat/MeanRev.mqh    |
//| Instantiates CSatMeanRevStepper, streams synthetic hourly bars   |
//| (70 days x 24 bars incl. NaN closes: one late-start symbol, one  |
//| symbol with periodic missing bars, plus a +3% level shift on     |
//| AUDNZD after day 63 to fire the FX hysteresis short), prints the |
//| resulting positions, and round-trips GetState/SetState mid-      |
//| stream verifying the clone tracks the original bit-for-bit.      |
//| NO trading functions.                                            |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Sat/MeanRev.mqh>

//+------------------------------------------------------------------+
//| deterministic synthetic close for symbol i at bar t (hour index) |
//+------------------------------------------------------------------+
double SynthClose(const int i, const int t)
  {
   double nan = SatNan();
   int day = t / 24;
   // symbol 2 (EURGBP): late start — no bars for the first 3 days
   if(i == 2 && day < 3)
      return nan;
   // symbol 5 (AUDCAD): prints no bar every 7th hour (stale ffill)
   if(i == 5 && (t % 7) == 3)
      return nan;
   double base = (i < SatMR_NFX) ? (1.0 + 0.1 * i) : (5000.0 + 1000.0 * i);
   double px = base * (1.0 + 0.0015 * MathSin(0.71 * t + 1.3 * i)
                           + 0.0008 * MathSin(0.173 * t));
   // AUDNZD: +3% level shift on days 64..69 -> 60d z-score > Z_IN
   if(i == 0 && day >= 64)
      px *= 1.03;
   return px;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   CSatMeanRevStepper stp;
   stp.Init();

   CSatMeanRevStepper clone;
   SSatMeanRevState snap;

   datetime base_ts = D'2024.01.01 00:00';
   int      n_days  = 70;
   int      split_t = 66 * 24;          // state round-trip point
   double   closes[SatMR_NSYM];
   double   pos[SatMR_NSYM];
   double   pos2[SatMR_NSYM];
   ArrayInitialize(pos, 0.0);
   ArrayInitialize(pos2, 0.0);

   bool   cloned  = false;
   double max_dif = 0.0;

   for(int t = 0; t < n_days * 24; t++)
     {
      datetime ts = base_ts + t * 3600;
      for(int i = 0; i < SatMR_NSYM; i++)
         closes[i] = SynthClose(i, t);

      stp.Step(ts, closes, pos);

      if(!cloned && t == split_t)
        {
         stp.GetState(snap);
         clone.SetState(snap);
         cloned = true;
         PrintFormat("state snapshot at t=%d: cur_day=%I64d dcount=%d "
                     "dptr=%d pend=%d st0=%d size0=%.10g pos0=%.10g",
                     t, snap.cur_day, snap.dcount, snap.dptr,
                     snap.pend_count, snap.st[0], snap.size[0],
                     snap.pos[0]);
        }
      if(cloned)
        {
         clone.Step(ts, closes, pos2);
         if(t > split_t)                 // clone stepped from t+1 on
            for(int i = 0; i < SatMR_NSYM; i++)
              {
               double dif = MathAbs(pos[i] - pos2[i]);
               if(dif == dif && dif > max_dif)
                  max_dif = dif;
              }
        }

      // print positions right after the day-64 target goes live
      // (finalized at day-65 00:00, effective day-65 13:00)
      if(t == 65 * 24 + 13 || t == n_days * 24 - 1)
        {
         double gross = 0.0;
         string s = StringFormat("pos @t=%d (%s): ", t,
                                 TimeToString(ts, TIME_DATE | TIME_MINUTES));
         for(int i = 0; i < SatMR_NSYM; i++)
           {
            gross += MathAbs(pos[i]);
            if(pos[i] != 0.0)
               s += StringFormat("%s=%.10g ", SatMR_SYMBOLS[i], pos[i]);
           }
         s += StringFormat(" gross=%.10g", gross);
         Print(s);
        }
     }

   // flush the trailing open day on both instances
   stp.Finalize();
   clone.Finalize();

   SSatMeanRevState fin1;
   SSatMeanRevState fin2;
   stp.GetState(fin1);
   clone.GetState(fin2);
   double st_dif = 0.0;
   for(int i = 0; i < SatMR_NSYM; i++)
     {
      double d1 = MathAbs(fin1.wavg[i] - fin2.wavg[i]);
      double d2 = MathAbs(fin1.size[i] - fin2.size[i]);
      double d3 = MathAbs(fin1.pos[i] - fin2.pos[i]);
      if(d1 == d1 && d1 > st_dif) st_dif = d1;
      if(d2 == d2 && d2 > st_dif) st_dif = d2;
      if(d3 == d3 && d3 > st_dif) st_dif = d3;
     }
   PrintFormat("round-trip: max pos diff=%.17g, final state diff=%.17g, "
               "pend1=%d pend2=%d st0=%d/%d dcount=%d/%d",
               max_dif, st_dif, fin1.pend_count, fin2.pend_count,
               fin1.st[0], fin2.st[0], fin1.dcount, fin2.dcount);

   // NaN plumbing spot checks
   PrintFormat("nan plumbing: close2(EURGBP)=%.10g wavg5(AUDCAD)=%.10g "
               "vol-floor wgt cap: K/floor=%.10g",
               fin1.close[2], fin1.wavg[5], 0.07 / 0.05);

   Print("CheckMeanRev: done");
  }
//+------------------------------------------------------------------+
