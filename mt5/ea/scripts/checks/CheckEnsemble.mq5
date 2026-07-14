//+------------------------------------------------------------------+
//| CheckEnsemble.mq5 — compile/smoke gate for Sat/Ensemble.mqh  |
//| Instantiates CSatEnsembleStepper (4 sleeves, 5-symbol union),    |
//| steps 50 synthetic hourly bars with interior NaN positions,      |
//| prints outputs + checksum, round-trips GetState/SetState, and    |
//| exercises the error paths.  NO trading functions.                |
//|                                                                  |
//| PYTHON GOLDEN (generated 2026-07-14 by running the validated     |
//| research/bpure/steppers/ensemble_stepper.py on this exact feed — |
//| scratch gen_ens_golden.py).  Terminal Print output must match:   |
//|   symbols: EURCHF EURSEK EURUSD USDJPY XAUUSD                    |
//|   gold_cap: 1.7999999999999998   (DERIVED 0.18*10.0 — one ulp    |
//|             BELOW the literal 1.8: hardcoding would be wrong)    |
//|   bar 00 h00: 0 -0.5 1.21892915181 -0.619791680421 nan           |
//|   bar 01 h01: 0.5 -0.5 1.64926109887 -0.00541501304833 1.8       |
//|   bar 02 h02: 0.5 -0.5 1.85637329324 nan 0.608651917133          |
//|   bar 03 h03: 0.5 nan 1.81223407101 1.14228481766 -1.17440193483 |
//|   bar 04 h04: 0.5 0.5 1.52281746884 1.52027219301 -1.8           |
//|   bar 05 h05: 0.5 0.5 1.02729466612 1.69249785896 nan            |
//|   ...                                                            |
//|   bar 46 h22: nan -0.385660375479 -1.68282585857 -1.37169625844  |
//|              1.8                                                 |
//|   bar 47 h23: -0.5 -0.5 -1.27405674159 -1.6420098622 1.8         |
//|   bar 48 h00: -0.5 -0.5 -0.692850021505 -1.69008513413 1.8       |
//|   bar 49 h01: -0.5 -0.5 -0.0178693013168 -1.50941531171 1.8      |
//|   checksum: -0.038976416288129201  nan_ct: 24                    |
//| (checksum tolerance: the feed uses MathSin — libm sin may differ |
//| from CPython's in the last ulp; positions/clips themselves are   |
//| exact given identical inputs.)                                   |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Sat/Ensemble.mqh>

// deterministic synthetic position, mirrors gen_ens_golden.pos():
// NaN when (bar+si+sym)%13==7, else sin(0.37*bar+1.3*si+0.71*sym)*1.7
double SynthPos(const int sleeve_idx, const int sym_idx, const int bar)
  {
   if((bar + sleeve_idx + sym_idx) % 13 == 7)
      return SatNan();
   return MathSin(0.37 * bar + 1.3 * sleeve_idx + 0.71 * sym_idx) * 1.7;
  }

// stage all four sleeve rows for one bar; returns false on any failure
bool StageBar(CSatEnsembleStepper &shell, const int bar)
  {
   double mr[3], se[1], cr[2], mg[1];
   for(int j = 0; j < 3; j++) mr[j] = SynthPos(0, j, bar);
   se[0] = SynthPos(2, 0, bar);
   for(int j = 0; j < 2; j++) cr[j] = SynthPos(4, j, bar);
   mg[0] = SynthPos(7, 0, bar);
   bool ok = true;
   ok = ok && shell.SetSleeveRow("meanrev", mr);
   ok = ok && shell.SetSleeveRow("seasonal", se);
   ok = ok && shell.SetSleeveRow("crisis", cr);
   ok = ok && shell.SetSleeveRow("mag", mg);
   return ok;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   // ---- build the shell (mirrors EnsembleStepper(sleeve_symbols)) --
   string mr_syms[3] = {"EURCHF", "EURUSD", "XAUUSD"};
   string se_syms[1] = {"XAUUSD"};
   string cr_syms[2] = {"EURSEK", "USDJPY"};
   string mg_syms[1] = {"XAUUSD"};

   CSatEnsembleStepper shell;
   bool ok = true;
   // add out of canonical order on purpose — Finalize must reorder
   ok = ok && shell.AddSleeve("mag", mg_syms);
   ok = ok && shell.AddSleeve("meanrev", mr_syms);
   ok = ok && shell.AddSleeve("crisis", cr_syms);
   ok = ok && shell.AddSleeve("seasonal", se_syms);
   ok = ok && shell.Finalize();
   if(!ok)
     {
      Print("FAIL: shell construction");
      return;
     }

   string syms = "";
   for(int i = 0; i < shell.SymbolCount(); i++)
      syms += (i > 0 ? " " : "") + shell.SymbolAt(i);
   Print("symbols: ", syms);
   Print("sleeves(canonical): ", shell.SleeveNameAt(0), " ",
         shell.SleeveNameAt(1), " ", shell.SleeveNameAt(2), " ",
         shell.SleeveNameAt(3));
   PrintFormat("gold_cap: %.17g", shell.GoldCap());

   // ---- 50 hourly bars from 2026.01.05 00:00 (epoch 1767571200) ---
   datetime t0 = D'2026.01.05 00:00:00';
   double   chk = 0.0;
   int      nan_ct = 0;
   double   out[];
   for(int bar = 0; bar < 50; bar++)
     {
      datetime t = t0 + bar * 3600;
      if(!StageBar(shell, bar))
        {
         Print("FAIL: staging bar ", bar);
         return;
        }
      if(!shell.Step(t, out))
        {
         Print("FAIL: step bar ", bar);
         return;
        }
      string line = "";
      for(int q = 0; q < shell.SymbolCount(); q++)
        {
         double v = out[q];
         if(v == v)
            chk += v;
         else
            nan_ct++;
         line += (q > 0 ? " " : "") + StringFormat("%.12g", v);
        }
      long hour = ((long)t / 3600) % 24;
      if(bar < 6 || bar >= 46)
         PrintFormat("bar %02d h%02d: %s", bar, (int)hour, line);
     }
   PrintFormat("checksum: %.17g  nan_ct: %d", chk, nan_ct);

   // ---- GetState/SetState round-trip -------------------------------
   string state = shell.GetState();
   Print("state: ", state);
   CSatEnsembleStepper shell2;
   if(!shell2.SetState(state))
     {
      Print("FAIL: SetState");
      return;
     }
   if(!StageBar(shell, 47) || !StageBar(shell2, 47))
     {
      Print("FAIL: staging roundtrip bar");
      return;
     }
   double a[], b[];
   datetime t47 = t0 + 47 * 3600;
   if(!shell.Step(t47, a) || !shell2.Step(t47, b))
     {
      Print("FAIL: roundtrip step");
      return;
     }
   bool same = (ArraySize(a) == ArraySize(b));
   for(int q = 0; same && q < ArraySize(a); q++)
     {
      bool eq = (a[q] == b[q]) || (a[q] != a[q] && b[q] != b[q]);
      if(!eq)
         same = false;
     }
   Print("state roundtrip identical: ", same ? "OK" : "FAIL");

   // ---- error paths (all must return false, no crash) --------------
   CSatEnsembleStepper bad;
   string dummy[1] = {"EURUSD"};
   bool e1 = !bad.AddSleeve("not_a_sleeve", dummy);   // ValueError
   bool e2 = !bad.Finalize();                          // no sleeves added
   double eo[];
   bool e3 = !shell.Step(t0, eo);   // rows were cleared by last Step
   double wrong[2] = {0.0, 0.0};
   bool e4 = !shell.SetSleeveRow("mag", wrong);        // size mismatch
   PrintFormat("error paths: unknown=%d nosleeves=%d missingrow=%d badsize=%d",
               (int)e1, (int)e2, (int)e3, (int)e4);

   Print("CheckEnsemble done.");
  }
//+------------------------------------------------------------------+
