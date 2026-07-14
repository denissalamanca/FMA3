//+------------------------------------------------------------------+
//| CheckBlend.mq5 - compile/smoke gate for Book/BookBlend.mqh       |
//|                                                                  |
//| NO trading functions, NO files. Three layers:                    |
//|  1. structure: netted union build (sorted, shared-symbol source  |
//|     maps) on a synthetic 3-core/4-sat universe with 2 shared;    |
//|  2. arithmetic: 3 Step() cases compared BITWISE against the      |
//|     python golden (research/bpure/blend/mirror_blend.py          |
//|     BookBlendMirror on the same inputs, 2026-07-14):             |
//|       case a=1 b=1:                                              |
//|         0.024000000000000004 0.036000000000000004 0.378          |
//|         -0.07599999999999997 0.96999999999999986                 |
//|       case a=2.3456788999999998 b=0.87654321000000002:           |
//|         0.055217111813139041 -0.082825667719708562               |
//|         0.086195722046715245 0.35521711181313903                 |
//|         -0.10337005432700669                                     |
//|       case a=417.93900000000002 b=0.031415899999999997:          |
//|         -3.2214087256195115e-18 0 9.9996778591274387e-14         |
//|         1.9998711436509753 3.2214087256195115e-09                |
//|  3. StringToDouble exponent-notation gauntlet: the TestBlend     |
//|     input stream is %.17g, which uses e-notation below 1e-4 -    |
//|     every token must parse to the same binary64 as CPython's     |
//|     float() (expected value embedded as a second spelling) and   |
//|     survive a %.17g round-trip bit-exactly. NOTE: %.17g TEXT is  |
//|     not unique (17 sig digits over-specify), so all compares     |
//|     here are on PARSED DOUBLES, never on strings.                |
//|                                                                  |
//| The terminal Print output must end with "CheckBlend: ALL PASS".  |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Book/BookBlend.mqh>

int g_fail = 0;

void Expect(const bool ok, const string what)
  {
   if(!ok)
     {
      g_fail++;
      Print("CheckBlend FAIL: ", what);
     }
  }

//--- one Step case vs embedded python golden (bitwise on doubles)
void StepCase(CBookBlend &bl, const string label,
              const double &fc[], const double &fs[],
              const double a, const double b, const string &want[])
  {
   double out[];
   Expect(bl.Step(fc, fs, a, b, out), label + ": Step returned false");
   int n = ArraySize(out);
   Expect(n == ArraySize(want), label + ": out size");
   string got = "";
   bool ok = true;
   for(int k = 0; k < n; k++)
     {
      double w = StringToDouble(want[k]);
      if(!(out[k] == w))                       // bitwise for non-NaN doubles
         ok = false;
      got += StringFormat("%.17g ", out[k]);
     }
   Print(label, ": ", got, ok ? "(bitwise match)" : "*** MISMATCH ***");
   Expect(ok, label + ": value mismatch vs python golden");
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   // ---- 1. structure -----------------------------------------------
   string core_syms[3] = {"EURUSD", "XAUUSD", "USA500"};
   string sat_syms[4]  = {"BTCUSD", "XAUUSD", "DAX", "USA500"};
   CBookBlend bl;
   Expect(bl.Init(0.7, core_syms, sat_syms), "Init failed");
   Expect(bl.NetCount() == 5, "NetCount != 5");
   string want_net[5] = {"BTCUSD", "DAX", "EURUSD", "USA500", "XAUUSD"};
   int want_core[5] = {-1, -1, 0, 2, 1};
   int want_sat[5]  = {0, 2, -1, 3, 1};
   for(int k = 0; k < 5; k++)
     {
      Expect(bl.NetSymbol(k) == want_net[k],
             StringFormat("net[%d]='%s' want '%s'", k, bl.NetSymbol(k), want_net[k]));
      Expect(bl.CoreIndexOf(k) == want_core[k], StringFormat("core_ix[%d]", k));
      Expect(bl.SatIndexOf(k) == want_sat[k], StringFormat("sat_ix[%d]", k));
     }
   Print("CheckBlend structure: net = BTCUSD DAX EURUSD USA500 XAUUSD (2 shared)");

   // ---- refusals ------------------------------------------------------
   CBookBlend bad;
   string dup[3] = {"EURUSD", "EURUSD", "XAUUSD"};
   Expect(!bad.Init(0.7, dup, sat_syms), "duplicate core syms not refused");
   double wrong[2] = {0.0, 0.0}, fs4[4] = {0, 0, 0, 0}, dummy[];
   Expect(!bl.Step(wrong, fs4, 1.0, 1.0, dummy), "wrong f_core size not refused");

   // ---- 2. arithmetic vs python golden --------------------------------
   double fc1[3] = {0.54, 1.6, -0.25};
   double fs1[4] = {0.08, -0.5, 0.12, 0.33};
   string w1[5] = {"0.024000000000000004", "0.036000000000000004", "0.378",
                   "-0.07599999999999997", "0.96999999999999986"};
   StepCase(bl, "case1 (a=1 b=1)", fc1, fs1, 1.0, 1.0, w1);

   double fc2[3] = {0.1, -0.2, 0.3};
   double fs2[4] = {0.4, 0.5, -0.6, 0.7};
   string w2[5] = {"0.055217111813139041", "-0.082825667719708562",
                   "0.086195722046715245", "0.35521711181313903",
                   "-0.10337005432700669"};
   StepCase(bl, "case2 (a=2.3456789 b=0.87654321)", fc2, fs2,
            2.3456789, 0.87654321, w2);

   double fc3[3] = {1e-13, 0.0, 2.0};
   double fs3[4] = {-1e-13, 1e-4, 0.0, -2.0};
   string w3[5] = {"-3.2214087256195115e-18", "0", "9.9996778591274387e-14",
                   "1.9998711436509753", "3.2214087256195115e-09"};
   StepCase(bl, "case3 (a=417.939 b=0.0314159)", fc3, fs3,
            417.939, 0.0314159, w3);

   // ---- 3. StringToDouble e-notation gauntlet --------------------------
   // token, then CPython float(token) respelled by python's '%.17g'
   string tok[6]  = {"1e-05", "6.0221408569999997e-05", "-1.23e-13",
                     "0.54091650228199997", "417.93899999999996",
                     "2.2250738585072014e-308"};
   string pyg[6]  = {"1.0000000000000001e-05", "6.0221408569999994e-05",
                     "-1.2300000000000001e-13", "0.54091650228199994",
                     "417.93899999999996", "2.2250738585072014e-308"};
   for(int i = 0; i < 6; i++)
     {
      double v  = StringToDouble(tok[i]);
      double vp = StringToDouble(pyg[i]);
      Expect(v == vp, StringFormat("parse gauntlet: '%s' != '%s' (%.17g vs %.17g)",
                                   tok[i], pyg[i], v, vp));
      double rt = StringToDouble(StringFormat("%.17g", v));
      Expect(rt == v, StringFormat("round-trip gauntlet: '%s' -> %.17g -> reparse drift",
                                   tok[i], v));
     }
   Print("CheckBlend gauntlet: 6 e-notation tokens parse == CPython, %.17g round-trip stable");

   if(g_fail == 0)
      Print("CheckBlend: ALL PASS");
   else
      PrintFormat("CheckBlend: %d FAILURES", g_fail);
  }
//+------------------------------------------------------------------+
