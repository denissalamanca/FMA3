//+------------------------------------------------------------------+
//| FableBook.mq5 - faithful executor of the v3 stable model. |
//|                                                                    |
//| Replays the precomputed, ALREADY-NETTED unified fed_frac stream    |
//| (FMA3_fed_frac_v3.csv, fmt=3, config-hash 51a7541cc2aaa593) and    |
//| sizes each of the 33 union symbols off ACCOUNT_BALANCE, exactly    |
//| as engine/record_engine(_ext).  One model, two dials: InpScale is  |
//| the ONLY IC<->FTMO difference (IC s=1.6, FTMO s=0.7 + breaker).    |
//|                                                                    |
//| Design of record: model/v3/EA_V3_DESIGN.md + MODEL_SPEC.md.       |
//| v3 DISCARDS the entire v1/v2 signal+sizing stack (no V7Core band   |
//| logic, no sleeves, no reseed): it keeps only the proven execution  |
//| primitives + one unified replay+size loop.                        |
//|                                                                    |
//|   base = ACCOUNT_BALANCE (realized cash, NOT equity)              |
//|   per H1 bar h (executed at h+1 first tick, >=1min causal lag):    |
//|     g=frac*s; unit=px*contract*eurq; want=g*base/unit; floor->lots |
//|     margin cap 0.9 (uniform shrink); rebalance band 0.25          |
//|   ONE net position + ONE magic per symbol (InpMagicBase+idx+1).    |
//|                                                                    |
//| Attach to an M1 24/7 clock chart (ETHUSD / BTCUSD). HEDGING acct.  |
//+------------------------------------------------------------------+
#property copyright "FableMultiAssets3"
#property version   "3.00"
#property strict

#include <Trade/Trade.mqh>

//====================================================================
// INPUTS
//====================================================================
input group "=== 1. The dial (the ONLY knob that differs IC<->FTMO) ==="
input double InpScale        = 1.60;                     // s: global scale dial (IC 1.6 / FTMO 0.7)
input double InpInitial      = 10000.0;                  // Seed capital EUR (IC 10000 / FTMO 100000)
input double InpDailyStopX   = 0.0;                       // FTMO daily circuit breaker % of prev-day close (0=off)

input group "=== 2. Stream + universe ==="
input string InpFedFracFile  = "FMA3_fed_frac_v3.csv";  // Unified fed_frac stream (Common\Files, fmt=3)
input long   InpMagicBase    = 3900000;                  // Order magic base (+idx+1 per symbol, 33 symbols)
input string InpV34SymbolMap = "";                       // canonical=broker remap (';'-sep); stream is already broker-mapped
input bool   InpLog          = true;                     // Write decisions CSV to Common\Files

input group "=== 3. Engine constants (match the record engine EXACTLY - do not change) ==="
input double InpMarginCap    = 0.9;                       // Margin utilisation cap (uniform shrink over 0.9*base)
input double InpRebalBand    = 0.25;                     // Rebalance dead-band (25% lot drift)

input group "=== 4. EUR conversion crosses (eurq full map, always on) ==="
input string InpEURUSD = "EURUSD";
input string InpEURJPY = "EURJPY";
input string InpEURGBP = "EURGBP";
input string InpEURCHF = "EURCHF";
input string InpEURNZD = "EURNZD";
input string InpEURCAD = "EURCAD";
input string InpEURNOK = "EURNOK";
input string InpEURSEK = "EURSEK";

//====================================================================
// INCLUDES (order matters: Convert -> Replay -> Exec -> Guardian)
//====================================================================
#include <Book/BookConvert.mqh>   // FED_MidOf, FED_Eurq (uses InpEUR* above)
#include <Book/BookReplay.mqh>    // universe table + fmt=3 loader (uses InpFedFracFile/Map/MagicBase)
#include <Book/BookExec.mqh>      // `trade`, primitives, FED_Reconcile (uses InpScale/MarginCap/RebalBand/Log)
#include <Book/Guardian.mqh>     // FED_GuardianPass (uses InpDailyStopX/InpInitial)

//====================================================================
// STATE
//====================================================================
datetime g_fedLastBar = 0;         // last processed M1 clock bar
datetime g_fedLastH1  = 0;         // last seen H1 bar-open (new-bar detector)

//====================================================================
// INIT
//====================================================================
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagicBase);
   g_fedLive = !MQLInfoInteger(MQL_TESTER);

   if((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)
       != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      Print("FMA3 V3 FATAL: requires a HEDGING account (one net position + one magic per symbol). Aborting.");
      return(INIT_FAILED);
     }

   // load + gate the unified stream (builds the 33-universe table). INIT_FAILED
   // before any order could exist if the config-hash / fmt gate fails.
   if(!FED_LoadReplay()) return(INIT_FAILED);

   // resolve the 33 traded symbols + the 8 EUR-conversion crosses.
   for(int i=0;i<FED_NSYM;i++)
      if(!SymbolSelect(g_fedTrade[i],true))
         Print("FMA3 V3 WARN: symbol '",g_fedTrade[i],"' not available (SymbolSelect failed) - leg will not size/trade.");
   string crosses[8]={InpEURUSD,InpEURJPY,InpEURGBP,InpEURCHF,InpEURNZD,InpEURCAD,InpEURNOK,InpEURSEK};
   for(int i=0;i<8;i++)
      if(!SymbolSelect(crosses[i],true))
         Print("FMA3 V3 WARN: EUR cross '",crosses[i],"' not available - legs quoted in that ccy will skip-loud.");
   SymbolSelect(_Symbol,true);

   for(int i=0;i<FED_NSYM;i++) g_fedLegDefer[i]=false;

   // decisions log
   if(InpLog)
     {
      string hdr[11]={"time","symbol","event","net_frac","want","held","after",
                      "balance","equity","margin_level","reserved"};
      if(g_fedLive)
        {
         g_fedLogh=FileOpen("fma3v3_decisions.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
         if(g_fedLogh!=INVALID_HANDLE)
           {
            if(FileSize(g_fedLogh)==0)
               FileWrite(g_fedLogh,hdr[0],hdr[1],hdr[2],hdr[3],hdr[4],hdr[5],hdr[6],hdr[7],hdr[8],hdr[9]);
            FileSeek(g_fedLogh,0,SEEK_END);
           }
        }
      else
        {
         g_fedLogh=FileOpen("fma3v3_decisions.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
         if(g_fedLogh!=INVALID_HANDLE)
            FileWrite(g_fedLogh,hdr[0],hdr[1],hdr[2],hdr[3],hdr[4],hdr[5],hdr[6],hdr[7],hdr[8],hdr[9]);
        }
     }

   PrintFormat("FMA3 V3 init: s=%.2f initial=%.0f marginCap=%.2f band=%.2f dailyStopX=%.2f magicBase=%d symbols=%d",
               InpScale,InpInitial,InpMarginCap,InpRebalBand,InpDailyStopX,(int)InpMagicBase,FED_NSYM);
   return(INIT_SUCCEEDED);
  }

//====================================================================
// DEINIT
//====================================================================
void OnDeinit(const int reason)
  {
   if(g_fedLogh!=INVALID_HANDLE) FileClose(g_fedLogh);
   int h=FileOpen("fma3v3_health.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h!=INVALID_HANDLE)
     {
      if(FileSize(h)==0) FileWrite(h,"version","scale","split_events","rejects","daily_stops","final_equity","final_ML");
      FileSeek(h,0,SEEK_END);
      FileWrite(h,"V3.00",DoubleToString(InpScale,2),IntegerToString(g_fedNSplit),
                IntegerToString(g_fedNReject),IntegerToString(g_fedNStops),
                DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2),
                DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1));
      FileClose(h);
     }
   PrintFormat("FMA3 V3 deinit: split=%d rejects=%d daily_stops=%d final_eq=%.2f",
               (int)g_fedNSplit,(int)g_fedNReject,g_fedNStops,AccountInfoDouble(ACCOUNT_EQUITY));
  }

//====================================================================
// MAIN LOOP - guardian every tick, reconcile once per new H1 bar
//====================================================================
void OnTick()
  {
   // [SEAM G] daily breaker BEFORE the new-bar gate (tick-granular worst-mark).
   // Inert at InpDailyStopX<=0. Returns false while halted (flatten-retry, no trading).
   if(!FED_GuardianPass()) return;

   datetime bt=iTime(_Symbol,PERIOD_M1,0);
   if(bt==g_fedLastBar) return;                          // one pass per M1 clock bar
   g_fedLastBar=bt;

   // [CAUSAL H1] on a NEW H1 bar (hour h+1 open) apply the JUST-CLOSED hour h's
   // targets (iTime(H1,1) = its bar-open epoch = the CSV ts). >=1min causal lag.
   datetime h1=iTime(_Symbol,PERIOD_H1,0);
   if(h1!=g_fedLastH1)
     {
      if(g_fedLastH1!=0)
        {
         datetime closed=iTime(_Symbol,PERIOD_H1,1);
         if(closed>0) FED_ApplyHour((long)closed);
        }
      g_fedLastH1=h1;
     }

   // [FIDELITY] re-size EVERY M1 bar (not just on a new hour): the record engine
   // recomputes desired = frac*balance/unit and re-derives the uniform margin-cap
   // shrink each MINUTE off current balance/price; the 0.25 band suppresses churn.
   // The hourly FRACTION (g_fedTgt) is causal (updated on the H1 boundary above);
   // the LOTS track balance/price intra-hour, as the engine does. This is the
   // single largest fidelity lever when the margin cap binds (IC s=1.6).
   FED_Reconcile();
  }
//+------------------------------------------------------------------+
