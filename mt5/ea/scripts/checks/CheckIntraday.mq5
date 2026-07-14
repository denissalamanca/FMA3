//+------------------------------------------------------------------+
//| CheckIntraday.mq5 — compile/smoke gate for FMA3v34/Intraday.mqh  |
//|                                                                  |
//| Instantiates CV34IntradayStepper, feeds ~96 synthetic hourly     |
//| union-grid bars (4 days) including NaN closes (missing-bar rows),|
//| prints hold-window positions, and round-trips GetState/SetState  |
//| mid-stream into a second instance verifying identical outputs.   |
//| NO trading functions.                                            |
//+------------------------------------------------------------------+
#property script_show_inputs false
#property strict

#include <FMA3v34/Intraday.mqh>

// synthetic raw closes (deterministic); NaN = symbol has no bar
double SynClose(const int sym, const int i)
  {
   if(sym == 0)
     {
      if(i == 20 || i == 63)                      // missing bars (incl. an h15)
         return V34Nan();
      return 5000.0 + 10.0 * MathSin(i * 0.7) + 0.5 * i;
     }
   if(i % 7 == 3)                                 // periodic missing bars
      return V34Nan();
   return 15000.0 + 30.0 * MathSin(i * 0.9) + 1.0 * i;
  }

void OnStart()
  {
   string syms[2];
   syms[0] = "USA500";
   syms[1] = "USTEC";

   // sc_min_periods=1 override so the signal activates inside the smoke
   // window (frozen value is 20 mv-days; every other param frozen).
   CV34IntradayStepper stepper;
   stepper.Init(syms, 16, 21, 2.0, 60.0, 0.15, 1.111, 30.0, 24.0, 0.30, 1);

   CV34IntradayStepper replay;                    // warm-start clone
   replay.Init(syms, 16, 21, 2.0, 60.0, 0.15, 1.111, 30.0, 24.0, 0.30, 1);

   const datetime t0 = D'2024.01.02 00:00:00';
   const int nbars = 96;                          // 4 days x 24 union rows
   const int snap_at = 40;                        // state round-trip point

   bool   snap_has_day = false;
   long   snap_day = 0;
   SV34IntradaySymState snap_syms[];

   double closes[2];
   double pos[];
   double rpos[];
   double checksum = 0.0;
   int    nonzero = 0;
   bool   replay_ok = true;

   for(int i = 0; i < nbars; i++)
     {
      datetime t = (datetime)((long)t0 + (long)i * 3600);
      closes[0] = SynClose(0, i);
      closes[1] = SynClose(1, i);
      stepper.Step(t, closes, pos);

      if(i == snap_at)
        {
         // serialize state field-for-field and warm-start the clone
         stepper.GetState(snap_has_day, snap_day, snap_syms);
         replay.SetState(snap_has_day, snap_day, snap_syms);
        }
      if(i >= snap_at)
        {
         if(i > snap_at)                          // clone steps bars after snap
           {
            replay.Step(t, closes, rpos);
            for(int k = 0; k < 2; k++)
               if(pos[k] != rpos[k])              // positions never NaN
                  replay_ok = false;
           }
        }

      for(int k = 0; k < 2; k++)
        {
         checksum += MathAbs(pos[k]);
         if(pos[k] != 0.0)
            nonzero++;
        }
      long hour = ((long)t / 3600) % 24;
      if(hour >= 16 && hour < 21)
         PrintFormat("bar %2d  %s  h%02d  USA500 pos=%.17g  USTEC pos=%.17g",
                     i, TimeToString(t, TIME_DATE|TIME_MINUTES), (int)hour,
                     pos[0], pos[1]);
     }

   PrintFormat("CheckIntraday: bars=%d nonzero_pos=%d checksum=%.17g",
               nbars, nonzero, checksum);
   PrintFormat("CheckIntraday: state round-trip (snap@bar %d) %s",
               snap_at, replay_ok ? "OK" : "MISMATCH");

   // frozen-default instantiation sanity (min_periods=20 -> all pos 0 here)
   CV34IntradayStepper frozen;
   frozen.InitDefault();
   double fpos[];
   double sum0 = 0.0;
   for(int i = 0; i < nbars; i++)
     {
      datetime t = (datetime)((long)t0 + (long)i * 3600);
      closes[0] = SynClose(0, i);
      closes[1] = SynClose(1, i);
      frozen.Step(t, closes, fpos);
      sum0 += MathAbs(fpos[0]) + MathAbs(fpos[1]);
     }
   PrintFormat("CheckIntraday: frozen-default warmup gate sum=%.17g (expect 0)",
               sum0);
  }
