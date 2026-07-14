//+------------------------------------------------------------------+
//| CheckSwapEurq.mq5 — in-terminal smoke for Book/SwapEurq.mqh, the  |
//| live swap/eurq generator (MQL5 twin of                            |
//| research/bpure/feed/swap_eurq_generator.py).                      |
//|                                                                   |
//| SCRIPT (OnStart), ZERO trading functions.                         |
//|                                                                   |
//| The python twin is already BIT-EQUAL (max|diff| = 0.0) against the |
//| PRE-BAKED eurq/swap arrays of all 24 b_h quarters and CoreSim      |
//| segments 0/10/20/31 (research/bpure/feed/swap_eurq_gate.json).     |
//| This script judges the MQL5 twin against that same generator via a |
//| fixture the generator emits (--emit-mqh-fixture):                  |
//|                                                                    |
//|   FMA3_swapeurq_fixture.csv  (FILE_COMMON, headerless, %.17g)      |
//|     BH,SYM,day_epoch,active,mult,swap_l,swap_s                     |
//|       -> b_h payload at a SERVER-MIDNIGHT rollover: pct/100/365*m  |
//|     CORE,SYM,rollover_epoch,active,mult,long_pct,short_pct         |
//|       -> a_h payload at 17:00 New York: flag=mult, pct/100         |
//|     ROLL,-,day_epoch,0,0,expected_rollover_epoch,0                 |
//|       -> the US-DST rollover rule (incl. both 2024 transitions)    |
//|     EURQF32,CROSS,bid_c_raw,ask_c_raw,expected_eurq                |
//|       -> b_h eurq: the (float) cast on the cross close is          |
//|          LOAD-BEARING (the record feed is float32-quantized)       |
//|     EURQF64,CROSS,bid_c,ask_c,expected_eurq                        |
//|       -> a_h eurq: float64, no cast                                |
//|                                                                    |
//| Comparison is BITWISE (==) on doubles. Output:                     |
//|   FMA3_swapeurq_actual.csv  kind,key,expected,actual,ok            |
//|                                                                    |
//| STAGED: with no fixture present the script prints the staged       |
//| notice and exits cleanly (compile/deploy is still meaningful).     |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

#include <Sat/SatMath.mqh>       // SatParseDouble (%.17g exact round-trip)
#include <Book/SwapEurq.mqh>

#define SE_FIXTURE "FMA3_swapeurq_fixture.csv"
#define SE_ACTUAL  "FMA3_swapeurq_actual.csv"

//+------------------------------------------------------------------+
int SplitCsv(const string line, string &out[])
  {
   return StringSplit(line, (ushort)',', out);
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   SE_InitTables();
   PrintFormat("CheckSwapEurq: %d symbols, %d crosses, %d policy ccys",
               SE_NSYM, SE_NCROSS, SE_NCCY);

   //--- unconditional table sanity (runs even without the fixture) --------
   int bad_static=0;
   if(SE_SymId("USDJPY")<0 || SE_SymId("DAX")<0 || SE_SymId("BTCUSD")<0)
      bad_static++;
   if(SE_WeekdayOf((long)D'2024.07.31')!=2)          // a Wednesday
      bad_static++;
   if(SE_SwapDayMultiplier(SE_SymId("USDJPY"), (long)D'2024.07.31')!=3)
      bad_static++;                                   // fx triple Wednesday
   if(SE_SwapDayMultiplier(SE_SymId("USTEC"),  (long)D'2024.08.02')!=3)
      bad_static++;                                   // index triple Friday
   if(SE_SwapDayMultiplier(SE_SymId("BTCUSD"), (long)D'2024.07.31')!=1)
      bad_static++;                                   // crypto never triples
   if(SE_IsSwapDay(SE_SymId("USDJPY"), (long)D'2024.08.03'))
      bad_static++;                                   // fx: no Saturday
   if(!SE_IsSwapDay(SE_SymId("BTCUSD"), (long)D'2024.08.03'))
      bad_static++;                                   // crypto: every day
   PrintFormat("static table checks: %s (%d bad)",
               bad_static==0 ? "PASS" : "FAIL", bad_static);

   //--- fixture -----------------------------------------------------------
   if(!FileIsExist(SE_FIXTURE, FILE_COMMON))
     {
      Print("STAGED: ", SE_FIXTURE, " not in Common\\Files — emit it with "
            "swap_eurq_generator.py --emit-mqh-fixture. Static checks done.");
      return;
     }
   int fh=FileOpen(SE_FIXTURE, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh==INVALID_HANDLE)
     {
      Print("FAIL: cannot open ", SE_FIXTURE, " err=", GetLastError());
      return;
     }
   int oh=FileOpen(SE_ACTUAL, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(oh==INVALID_HANDLE)
     {
      FileClose(fh);
      Print("FAIL: cannot write ", SE_ACTUAL, " err=", GetLastError());
      return;
     }
   FileWriteString(oh, "kind,key,expected,actual,ok\n");

   int n=0, nbad=0;
   double worst=0.0;
   string worst_key="-";
   string f[];
   while(!FileIsEnding(fh))
     {
      string line=FileReadString(fh);
      StringTrimRight(line);
      StringTrimLeft(line);
      if(StringLen(line)==0)
         continue;
      int nf=SplitCsv(line, f);
      if(nf<5)
         continue;
      string kind=f[0];
      string key=f[1];
      string tag=kind+":"+key;

      if(kind=="BH" || kind=="CORE")
        {
         int    k    = SE_SymId(key);
         long   day  = (long)StringToInteger(f[2]);
         int    act  = (int)StringToInteger(f[3]);
         int    mult = (int)StringToInteger(f[4]);
         double e_l  = SatParseDouble(f[5]);
         double e_s  = SatParseDouble(f[6]);
         if(k<0)
           {
            nbad++;
            FileWriteString(oh, StringFormat("%s,%s,-,UNKNOWN_SYMBOL,0\n", kind, key));
            continue;
           }
         //--- CORE rows carry the 17:00-NY instant; recover the day label
         long dlab = (kind=="BH") ? day : SE_MidnightOf(day);
         if(kind=="CORE")
            tag=tag+"@"+IntegerToString(day);
         int    g_act  = SE_IsSwapDay(k, dlab) ? 1 : 0;
         int    g_mult = SE_SwapDayMultiplier(k, dlab);
         double lp, sp;
         SE_SwapAnnualPct(k, dlab, lp, sp);
         double g_l = (kind=="BH") ? lp/100.0/365.0*g_mult : lp/100.0;
         double g_s = (kind=="BH") ? sp/100.0/365.0*g_mult : sp/100.0;
         bool ok=(g_act==act && g_mult==mult && g_l==e_l && g_s==e_s);
         if(!ok)
           {
            nbad++;
            double d=MathMax(MathAbs(g_l-e_l), MathAbs(g_s-e_s));
            if(d>worst) { worst=d; worst_key=tag; }
           }
         n++;
         FileWriteString(oh, StringFormat("%s,%s,%.17g|%.17g|%d|%d,%.17g|%.17g|%d|%d,%d\n",
                                          kind, tag, e_l, e_s, mult, act,
                                          g_l, g_s, g_mult, g_act, ok?1:0));
         continue;
        }

      if(kind=="ROLL")
        {
         long day=(long)StringToInteger(f[2]);
         long e_r=(long)StringToInteger(f[5]);
         long g_r=SE_RolloverUtcSec(day);
         bool ok=(g_r==e_r);
         if(!ok)
            nbad++;
         n++;
         FileWriteString(oh, StringFormat("ROLL,%d,%d,%d,%d\n", day, e_r, g_r, ok?1:0));
         continue;
        }

      if(kind=="EURQF32" || kind=="EURQF64")
        {
         double b=SatParseDouble(f[2]);
         double a=SatParseDouble(f[3]);
         double e=SatParseDouble(f[4]);
         CSECross x;
         x.f32=(kind=="EURQF32");
         x.Update(b, a);
         double g=x.EurPerQuote();
         bool ok=(g==e);
         if(!ok)
           {
            nbad++;
            double d=MathAbs(g-e);
            if(d>worst) { worst=d; worst_key=tag; }
           }
         n++;
         FileWriteString(oh, StringFormat("%s,%s,%.17g,%.17g,%d\n",
                                          kind, key, e, g, ok?1:0));
         continue;
        }
     }
   FileClose(fh);
   FileClose(oh);

   PrintFormat("CheckSwapEurq: %d fixture rows, %d BAD, worst |diff| %.6g at %s -> %s",
               n, nbad, worst, worst_key, SE_ACTUAL);
   PrintFormat("VERDICT: %s", (nbad==0 && bad_static==0) ? "PASS (bit-equal)" : "FAIL");
  }
//+------------------------------------------------------------------+
