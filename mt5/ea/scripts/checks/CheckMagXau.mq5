//+------------------------------------------------------------------+
//| CheckMagXau.mq5 — compile/behavior gate for                      |
//| Include/FMA3v34/MagXau.mqh (CV34MagXauStepper).                  |
//|                                                                  |
//| Instantiates the stepper, feeds ~60 synthetic hourly bars        |
//| (including NaN closes and weekend gaps), exercises warm-start    |
//| via SetState with a full 21-mid ring, and round-trips            |
//| GetState/SetState checking step-for-step agreement.              |
//| NO trading functions.                                            |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <FMA3v34/MagXau.mqh>

const long CHK_HOUR_NS = (long)3600 * (long)1000000000;

void OnStart()
  {
   double nan = V34Nan();

   //================================================================
   // Phase 1 — COLD START: fresh stepper, 4 server days x 8 hourly
   // bars with NaN holes + one full-NaN day (no daily stamp).
   // Expect position 0.0 throughout (< VOL_WIN+1 daily mids).
   //================================================================
   CV34MagXauStepper st;
   long day0 = V34MAGXAU_DAY_NS * (long)20000;   // arbitrary day boundary
   int  bars = 0;
   int  nonzero1 = 0;
   for(int d = 0; d < 4; d++)
     {
      for(int h = 0; h < 8; h++)
        {
         long ts = day0 + (long)d * V34MAGXAU_DAY_NS + (long)h * CHK_HOUR_NS;
         double c;
         if(d == 2)               c = nan;                       // whole day NaN
         else if(h == 3)          c = nan;                       // hole inside day
         else                     c = 1950.0 + 5.0 * d + 0.5 * h;
         double pos = st.StepNs(ts, c);
         bars++;
         if(pos != 0.0)
            nonzero1++;
        }
     }
   Print("Phase1 cold: bars=", bars,
         " nonzero_positions=", nonzero1,
         " mids_len=", ArraySize(st.m_mids),
         " pending_len=", ArraySize(st.m_pend_ts),
         " current=", DoubleToString(st.m_current, 17));

   //================================================================
   // Phase 2 — WARM START via SetState: 21 finalized daily mids
   // (full vol ring) + an open accum day whose mid sits in the
   // magnet band (1990 -> near 2000, dist -0.10 in (-0.18,-0.03)
   // -> sig 1).  Next-day bar finalizes it and the target becomes
   // effective the same bar (day+1 00:00).
   //================================================================
   SV34MagXauState ws;
   ws.version       = 1;
   ws.sleeve        = "mag_xau";
   ArrayResize(ws.mids, V34MAGXAU_VOL_WIN + 1);
   for(int i = 0; i <= V34MAGXAU_VOL_WIN; i++)
      ws.mids[i] = 1950.0 + 3.0 * (double)(i % 5) + (double)i;   // varying -> ann > 0
   long wday = day0 + (long)10 * V34MAGXAU_DAY_NS;
   ws.has_accum_day = true;
   ws.accum_day     = wday;
   ws.accum_close   = 1990.0;                                    // in-band mid
   ArrayResize(ws.pending_ts, 0);
   ArrayResize(ws.pending_tgt, 0);
   ws.current       = 0.0;

   CV34MagXauStepper w;
   w.SetState(ws);

   // day wday+1: 6 hourly bars (first bar triggers finalize + apply)
   double firstpos = nan, lastpos = nan;
   for(int h = 0; h < 6; h++)
     {
      long ts = wday + V34MAGXAU_DAY_NS + (long)h * CHK_HOUR_NS;
      double c = (h == 2) ? nan : 1991.0 + 0.25 * h;
      double pos = w.StepNs(ts, c);
      if(h == 0)
         firstpos = pos;
      lastpos = pos;
     }
   Print("Phase2 warm: pos@day+1 00:00=", DoubleToString(firstpos, 17),
         " pos@day+1 05:00=", DoubleToString(lastpos, 17),
         " mids_len=", ArraySize(w.m_mids),
         " pending_len=", ArraySize(w.m_pend_ts));

   //================================================================
   // Phase 3 — GetState/SetState ROUND-TRIP: snapshot w, restore
   // into a second stepper, then feed BOTH the same 20 bars (incl.
   // NaN closes and a day rollover). Positions must match bitwise.
   //================================================================
   SV34MagXauState snap;
   w.GetState(snap);
   CV34MagXauStepper r;
   r.SetState(snap);

   int mismatches = 0;
   double pw = 0.0, pr = 0.0;
   for(int k = 0; k < 20; k++)
     {
      long ts = wday + V34MAGXAU_DAY_NS + (long)6 * CHK_HOUR_NS
                + (long)k * CHK_HOUR_NS;                          // crosses into day+2
      double c = (k % 7 == 3) ? nan : 1992.0 - 0.4 * (double)k;
      pw = w.StepNs(ts, c);
      pr = r.StepNs(ts, c);
      bool same = (pw == pr) || (pw != pw && pr != pr);
      if(!same)
         mismatches++;
     }
   Print("Phase3 roundtrip: mismatches=", mismatches,
         " final_pos_orig=", DoubleToString(pw, 17),
         " final_pos_restored=", DoubleToString(pr, 17));

   // datetime-wrapper API + FlushFinalDay compile/behavior touch
   double pdt = w.Step((datetime)((wday + (long)3 * V34MAGXAU_DAY_NS)
                                  / (long)1000000000), 1993.0);
   w.FlushFinalDay();
   Print("Phase4 dt-wrapper pos=", DoubleToString(pdt, 17),
         " post-flush pending_len=", ArraySize(w.m_pend_ts),
         " has_accum_day=", w.m_has_accum_day);

   bool ok = (nonzero1 == 0) && (mismatches == 0)
             && V34IsObs(firstpos) && (firstpos > 0.0);
   Print("CheckMagXau RESULT: ", ok ? "PASS" : "FAIL");
  }
