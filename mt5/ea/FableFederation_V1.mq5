//+------------------------------------------------------------------+
//| FableFederation_V1.mq5 - the ONE FMA3 federation EA               |
//|                                                                    |
//| Supersedes the two-parent-EA deployment (owner decision 2026-07-10)|
//| Build contract: FMA3 mt5/ea/SPEC.md + TRANSPLANT_V7.md.            |
//|                                                                    |
//|  * v7 book: sleeves + BAND_SYM_25 + H9 delta-resize transplanted   |
//|    VERBATIM from NSF5 FableMultiAsset1_V7.mq5 (Include/FMA3/       |
//|    V7Core.mqh; gate G1 = v7-only mode reproduces IC run 54,        |
//|    EUR 398,368.75). Magics 360001..360012 unchanged.               |
//|  * v3.4 book: a NEW consumption layer ONLY - signals stay in       |
//|    Python. Tester: frozen-targets replay CSV, config-hash-gated    |
//|    (FMA3 v1.0 pin hash 51a7541cc2aaa593). Live: fma3.targets.v1    |
//|    JSON. Magics 8400001..8400008 (FMA2 sleeve order).              |
//|  * Federation bookkeeping: fresh-seed VIRTUAL sub-books, each      |
//|    compounding on its own P&L; convention A (SPEC par.5.2): both   |
//|    books seed at the full InpInitial and w=0.70/0.30 is carried in |
//|    the dials (InpRisk=8*w*s, InpV34Mult=(1-w)*s). v7 re-splits     |
//|    reseed from the v7 VIRTUAL book equity only (anti-coupling).    |
//|  * FTMO guardian: config-gated daily stop (InpDailyStopX, 0=OFF =  |
//|    bit-identical behavior, gate G4a). Flatten all at day-anchor    |
//|    -x%, halt until the next server day.                            |
//|                                                                    |
//| Attach to a 24/7 M1 clock chart (ETHUSD or BTCUSD). HEDGING acct.  |
//| Market Watch: the 10 v7 symbols + the v3.4 replay symbol union.    |
//+------------------------------------------------------------------+
#property copyright "FableMultiAssets3"
#property version   "1.00"   // F1.00: verbatim-v7 core + v3.4 consumption + federation books + guardian
#property strict

#include <Trade/Trade.mqh>

//====================================================================
// INPUTS
//====================================================================
// UI amendment 2026-07-10 (TRANSPLANT_V7.md par.2.1): the input COMMENTS,
// ordering and `input group` headers below are DISPLAY METADATA for the
// tester's Inputs tab - the compiler strips them, zero logic impact.
// The variable NAMES and DEFAULT VALUES are LAW and byte-identical to the
// parents (presets bind to names; gate G1 parity binds to defaults) -
// enforced mechanically by scripts/check_transplant.py.

enum F3_V34_MODE
  {
   V34_OFF    = 0,   // 0 = off (v7-only mode - gate G1)
   V34_REPLAY = 1,   // 1 = replay: frozen-targets CSV (tester)
   V34_LIVE   = 2    // 2 = live: Python-brain targets.json
  };

input group "=== 1. Risk dial (the ONLY knobs to change per preset) ==="
input double  InpRisk        = 5.0;     // Portfolio risk multiplier R (v7 book dial)
input double  InpV34Mult     = 0.48;    // v3.4 book dial (0.30 x s)
input double  InpDailyStopX  = 0.0;     // FTMO daily circuit breaker % (0 = off)
input double  InpSizingBase  = 0.0;     // 0 = compound (default, current behavior); >0 = withdraw-to-base modeling: all lot sizing scaled to this constant base
input double  InpMinMarginLevel = 0.0;  // Account min margin-level floor % (0 = OFF; e.g. 110 = hold account ML >= 110%). Governor haircuts ALL desired legs proportionally; lets the dial run higher for return.
input bool    InpIndepReseed   = false;  // false = pooled equal-capital reseed (current, byte-identical); true = INDEPENDENT per-sleeve reseed (each sleeve keeps its OWN compounded equity, no pooled redistribution) — v-next root-cause confirmation / fix prototype.
input bool    InpReseedBalance = false;  // false = reseed off pooled EQUITY (current, byte-identical); true = reseed off pooled BALANCE (realized only, NO floating) — removes the floating double-count while KEEPING equal-capital joint compounding. FEDERATED path only; subsumed when InpIndepReseed=true.

input group "=== 2. Federation ==="
input bool        InpEnableV7      = true;                  // Run the v7 book (false = v3.4-only)
input F3_V34_MODE InpV34Mode       = V34_REPLAY;            // v3.4 source: 0=off 1=replay(tester) 2=live(brain)
input string      InpV34ReplayFile = "FMA3_v34_replay.csv"; // Replay CSV name (in Common\Files)
input string      InpV34LiveFile   = "fma3\\targets.json";  // Live brain file (in MQL5\Files)
input int         InpV34StaleMin   = 150;                   // Live targets stale after N minutes (HOLD)
input long        InpMagicBaseV34  = 8400000;               // v3.4 order magic base (+1..+8)
input double      InpWv7           = 0.70;                  // v7 capital share w (informational)
input double      InpScale         = 1.60;                  // Global scale s (informational)
input string      InpV34SymbolMap  = "USA500=US500;DAX=DE40"; // repo=broker symbol map (';'-separated)

input group "=== 3. v7 book internals (validated - do not change) ==="
input double  InpInitial     = 10000.0; // Seed capital EUR (all validation at 10000)
input double  InpRebalBand   = 0.25;    // Rebalance dead-band (0.25 = 25% lot drift)
input double  InpMarginCap   = 0.9;     // Margin utilisation cap (0.9 = 90% max)
input long    InpMagicBase   = 360000;  // v7 order magic base (+1..+12)
input bool    InpLog         = true;    // Write decisions CSV to Common\Files
input bool    InpEnableFXTUJ = true;    // Enable FXT_UJ sleeve (ships OFF in presets)
input bool    InpEnableAU    = true;    // Enable ZC_AU sleeve (ships OFF in presets)
input bool    InpEnableEU    = true;    // Enable FXT_EU sleeve (ships OFF in presets)
input bool    InpEnableS6    = true;    // Enable S6 opex-basket sleeve (ships ON)
input bool    InpEnableBTC   = true;    // Enable BTC momentum sleeve (ships ON)
input bool    InpEqualWeight = false;   // Equal capital per slot (ships ON: 7 slots)
input double  InpMagCap      = 6.0;     // S6 leg notional cap
input double  InpMagVt       = 0.15;    // S6 leg vol target (scaled by InpRisk)
input double  InpBtcVt       = 0.40;    // BTC vol target (scaled by InpRisk)
input double  InpBtcCap       = 1.2;    // BTC notional cap
input double  InpBtcHurdle    = 0.40;   // BTC min annualized momentum to hold
input int     InpBtcLb        = 63;     // BTC momentum lookback (trading days)
input int     InpBtcRegime    = 200;    // BTC regime MA (long only above it)
input double  InpHarvestK    = 2.5;     // Harvest re-split: slot equity > k x seed
input double  InpBandUp        = 0.25;   // Band re-split: max slot share (0 = off)
input double  InpBandDownDiv   = 1.75;   // Band re-split: floor = (1/slots)/this
input int     InpBandMinGapDays= 5;      // Band re-split: min days between events
input int     InpMinM1Bars     = 1000;   // Live-only: min synced M1 bars (0 = off)
input string  InpXAU     = "XAUUSD";    // v7 symbol: gold
input string  InpUS500   = "USA500";    // v7 symbol: US index (presets use USTEC)
input string  InpUSDJPY  = "USDJPY";    // v7 symbol: USDJPY
input string  InpETH     = "ETHUSD";    // v7 symbol: Ethereum
input string  InpEURGBP  = "EURGBP";    // v7 symbol: EURGBP
input string  InpAUD     = "AUDUSD";    // v7 symbol: AUDUSD
input string  InpEURUSD  = "EURUSD";    // v7 symbol: EURUSD
input string  InpEURJPY  = "EURJPY";    // v7 symbol: EURJPY (conversion only)
input string  InpNZD     = "NZDUSD";    // v7 symbol: NZDUSD (S6 leg 3)
input string  InpBTC     = "BTCUSD";    // v7 symbol: Bitcoin

// F3 shared state + prototypes the transplanted V7Core seam references.
bool   g_f3FedActive = false;      // (v34 on && v7 on) - switches SEAM 1 only
double F3_V7BookEquity();
// [F3 CHANGE 2..4] exec-hardening prototypes (definitions in FMA3/V34Exec.mqh;
// V7Core's marked seam lines call them - same pattern as F3_V7BookEquity).
double F3_StepOf(string sym);
void   F3_SizeSkipWarn(string sym);
void   F3_HoldSet(string sym,long magic,double desired,double held,string why);
void   F3_HoldClear(string sym,long magic);
bool   F3_SendAdd(string sym,long magic,int dir,double dv,double desired,double held);

#include <FMA3/V7Core.mqh>
#include <FMA3/Federation.mqh>
#include <FMA3/V34Replay.mqh>
#include <FMA3/V34Live.mqh>
#include <FMA3/V34Exec.mqh>
#include <FMA3/Guardian.mqh>

//====================================================================
// INIT
//====================================================================
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicBase);
   g_slSym[SL_XAU]=InpXAU;   g_slName[SL_XAU]="BOOK_XAU";
   g_slSym[SL_US5]=InpUS500; g_slName[SL_US5]="BOOK_US5";
   g_slSym[SL_JPY]=InpUSDJPY;g_slName[SL_JPY]="S5_JPY";
   g_slSym[SL_ETH]=InpETH;   g_slName[SL_ETH]="S1_ETH";
   g_slSym[SL_EG] =InpEURGBP;g_slName[SL_EG] ="ZC_EG";
   g_slSym[SL_AU] =InpAUD;   g_slName[SL_AU] ="ZC_AU";
   g_slSym[SL_FEU]=InpEURUSD;g_slName[SL_FEU]="FXT_EU";
   g_slSym[SL_FUJ]=InpUSDJPY;g_slName[SL_FUJ]="FXT_UJ";
   g_slSym[SL_S6UJ]=InpUSDJPY;g_slName[SL_S6UJ]="S6_UJ";
   g_slSym[SL_S6AU]=InpAUD;   g_slName[SL_S6AU]="S6_AU";
   g_slSym[SL_S6NZ]=InpNZD;   g_slName[SL_S6NZ]="S6_NZ";
   g_slSym[SL_BTC] =InpBTC;   g_slName[SL_BTC] ="S1_BTC";

   g_serSym[SID_XAU]=InpXAU;   g_serSym[SID_US5]=InpUS500; g_serSym[SID_UJ]=InpUSDJPY;
   g_serSym[SID_ETH]=InpETH;   g_serSym[SID_EG]=InpEURGBP; g_serSym[SID_AU]=InpAUD;
   g_serSym[SID_EU]=InpEURUSD; g_serSym[SID_EG20]=InpEURGBP; g_serSym[SID_NZD]=InpNZD;
   g_serSym[SID_BTC]=InpBTC;
   for(int s=0;s<N_SER;s++){ g_serPre20[s]=false; g_ser[s].lastDay=0; }
   g_serPre20[SID_EG20]=true;

   string need[11]={InpXAU,InpUS500,InpUSDJPY,InpETH,InpEURGBP,InpAUD,InpEURUSD,InpEURJPY,InpNZD,InpBTC,_Symbol};
   for(int i=0;i<11;i++) SymbolSelect(need[i],true);

   if((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)
       != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
   {
      Print("PortfolioV5 FATAL: requires a HEDGING account (multiple sleeves share ",
            "USDJPY/AUDUSD/XAUUSD as independent sub-accounts). Aborting.");
      return(INIT_FAILED);
   }

   // sleeve enable/disable -> weight 0 (never trades)
   if(!InpEnableFXTUJ) W[SL_FUJ]=0.0;
   if(!InpEnableAU)    W[SL_AU] =0.0;
   if(!InpEnableEU)    W[SL_FEU]=0.0;
   if(!InpEnableS6){ W[SL_S6UJ]=0.0; W[SL_S6AU]=0.0; W[SL_S6NZ]=0.0; }
   if(!InpEnableBTC) W[SL_BTC]=0.0;

   if(InpEqualWeight)
   {
      // V5 SLOT model: each enabled CORE sleeve = one slot; S6 (if enabled) = ONE
      // slot split across its 3 legs (1/3 each); MAG (if enabled) = one slot.
      int coreCnt=0;
      for(int n=0;n<=SL_FUJ;n++) if(W[n]>0.0) coreCnt++;   // enabled core sleeves
      int slots=coreCnt + (InpEnableS6?1:0) + (InpEnableBTC?1:0);
      double slotW=(slots>0)?1.0/slots:0.0;
      for(int n=0;n<=SL_FUJ;n++) W[n]=(W[n]>0.0)?slotW:0.0;
      if(InpEnableS6){ W[SL_S6UJ]=slotW/3.0; W[SL_S6AU]=slotW/3.0; W[SL_S6NZ]=slotW/3.0; }
      if(InpEnableBTC) W[SL_BTC]=slotW;
      Print("PortfolioV5: SLOT-EQUAL over ",slots," slots (core ",coreCnt,
            ", S6=",(InpEnableS6?1:0),", BTC=",(InpEnableBTC?1:0),"); slotW=",DoubleToString(slotW,4));
   }
   else
   {
      double sw=0.0; for(int n=0;n<N_SLEEVE;n++) sw+=W[n];
      if(sw>0.0) for(int n=0;n<N_SLEEVE;n++) W[n]/=sw;
      Print("PortfolioV5: renormalized weights to sum 1.0.");
   }
   { string ws=""; for(int n=0;n<N_SLEEVE;n++) if(W[n]>0.0) ws+=g_slName[n]+"="+DoubleToString(W[n],4)+" ";
     Print("PortfolioV5: FINAL sleeve weights -> ",ws); }

   // [F3 SEAM 4.1] InpEnableV7=false (G2 v34-only mode): zero ALL v7 weights AFTER
   // the weight math, so every v7 path no-ops through the EXISTING W[n]<=0 guards
   // (no new branches inside transplanted code). NOTE: placed after the
   // InpEqualWeight block - it re-assigns S6/BTC weights from the enable flags,
   // so zeroing before it (TRANSPLANT par.3 first suggestion) would be overwritten.
   if(!InpEnableV7){ for(int n=0;n<N_SLEEVE;n++) W[n]=0.0;
      Print("F3: v7 book DISABLED (InpEnableV7=false) - all v7 sleeve weights zeroed."); }

   g_live = !MQLInfoInteger(MQL_TESTER);
   for(int n=0;n<N_SLEEVE;n++) g_deferred[n]=false;
   if(g_live && LoadState())
   {
      for(int n=0;n<N_SLEEVE;n++) g_realized[n]=0.0;
      UpdateRealized();
      PrintFormat("PortfolioV5: RESTORED state (qStart=%s lastRebalQ=%d qNow=%d) — mid-quarter recovery.",
                  TimeToString(g_quarterStart),g_lastRebalQ,QuarterId(UtcDayStart(TimeCurrent())));
   }
   else
   {
      for(int n=0;n<N_SLEEVE;n++){ g_seed[n]=InpInitial*W[n]; g_realized[n]=0.0; }
      g_quarterStart=TimeCurrent();
      g_lastRebalQ=QuarterId(UtcDayStart(TimeCurrent()));
      if(HistorySelect(g_quarterStart,TimeCurrent()+1)) g_dealCursor=HistoryDealsTotal();
      if(g_live) SaveState();
      Print("PortfolioV5: FRESH seed (no prior state file).");
   }

   datetime nowDay=UtcDayStart(TimeCurrent());
   for(int s=0;s<N_SER;s++) ExtendSeries(s,nowDay);
   RecomputeDaily();

   if(InpLog)
   {
      string hdr[11]={"utc_time","sleeve","event","m","desired","held",
                      "extra","vbalance","acct_balance","acct_equity","margin_level"};
      if(g_live)
      {
         g_logh=FileOpen("fma3_fed_decisions.csv",
                         FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
         if(g_logh!=INVALID_HANDLE)
         {
            if(FileSize(g_logh)==0)
               FileWrite(g_logh,hdr[0],hdr[1],hdr[2],hdr[3],hdr[4],hdr[5],
                         hdr[6],hdr[7],hdr[8],hdr[9],hdr[10]);
            FileSeek(g_logh,0,SEEK_END);
         }
      }
      else
      {
         g_logh=FileOpen("fma3_fed_decisions.csv",
                         FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
         if(g_logh!=INVALID_HANDLE)
            FileWrite(g_logh,hdr[0],hdr[1],hdr[2],hdr[3],hdr[4],hdr[5],
                      hdr[6],hdr[7],hdr[8],hdr[9],hdr[10]);
      }
   }
   PrintFormat("PortfolioV5 init: R=%.1f initial=%.0f | series XAU=%d US5=%d UJ=%d ETH=%d EG20=%d AU=%d EU=%d NZD=%d",
               InpRisk,InpInitial,ArraySize(g_ser[SID_XAU].mid),ArraySize(g_ser[SID_US5].mid),
               ArraySize(g_ser[SID_UJ].mid),ArraySize(g_ser[SID_ETH].mid),
               ArraySize(g_ser[SID_EG20].mid),ArraySize(g_ser[SID_AU].mid),
               ArraySize(g_ser[SID_EU].mid),ArraySize(g_ser[SID_NZD].mid));
   // [F3 SEAM 4.2-4.7] federation init: magic disjointness assert, v34 ledger seed,
   // replay load + config-hash gate (INIT_FAILED before any order could exist - G2a),
   // live first read (missing file = HOLD posture), books log, guardian init.
   if(!F3_Init()) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){ if(g_logh!=INVALID_HANDLE) FileClose(g_logh);
   // v6.01: APPEND (read+write, seek end) so every tester run adds a row
   // instead of overwriting — full R-sweep history in one file. Delete the
   // file to start a fresh sweep.
   int h=FileOpen("fma3_fed_health.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h!=INVALID_HANDLE){
      bool fresh=(FileSize(h)==0);
      if(fresh) FileWrite(h,"version","risk","split_events","volume_rejects","closed_defers","final_equity","final_ML");
      FileSeek(h,0,SEEK_END);
      FileWrite(h,"F1.00",DoubleToString(InpRisk,1),IntegerToString(g_nSplit),
               IntegerToString(g_nReject),IntegerToString(g_nClosed),
               DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2),
               DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1));
      FileClose(h);
      PrintFormat("HEALTH v7.00 R=%.0f: split_events=%d volume_rejects=%d closed_defers=%d",
                  InpRisk,(int)g_nSplit,(int)g_nReject,(int)g_nClosed);
   }
   // [F3 SEAM 4.8] federation deinit: final fma3_fed_books.csv row (G3 evidence)
   // + close the F3 handles. No change inside the v7 block above.
   F3_Deinit();
}

//====================================================================
// MAIN LOOP — one pass per clock M1 bar
//====================================================================
void OnTick()
{
   // [F3 SEAM G] guardian BEFORE the new-bar early-return (the daily stop must be
   // tick-granular). At InpDailyStopX<=0 this is ONE short-circuit branch touching
   // no state and writing no files - the G4a bit-identity guarantee. Returns false
   // while halted (flatten-retry + no trading until the next server day).
   if(!F3_GuardianPass()) return;

   datetime bt=iTime(_Symbol,PERIOD_M1,0);
   if(bt==g_lastBar) return;
   g_lastBar=bt;

   // --- P1 live-reliability guard (LIVE-ONLY): skip this bar's reconcile/rebalance/trade
   // pass while the terminal is disconnected or a traded symbol's M1 history is not yet
   // synced (post-restart). Placed AFTER the new-bar gate and BEFORE any reconcile/trade
   // action; the day-rollover recompute, band re-split and per-sleeve exec all run only on
   // a ready bar. g_curDay / g_quarterStart are left untouched here so the pass simply
   // re-runs on the next connected/synced bar (clean automatic resume). LiveReady() is a
   // hard no-op in the Strategy Tester (returns true when !g_live) -> byte-neutral backtest.
   //
   // HEARTBEAT-ON-SKIP (monitoring refinement): while the pass is skipped (e.g. a legit
   // post-restart history-resync — connected, ticks flowing, M1 not yet synced), the P0
   // heartbeat must still fire on its NORMAL cadence, else the CSV goes stale and the H12
   // live monitor (heartbeat = liveness ground truth) misreads a skipping-but-alive EA as
   // crashed. Emit it with status="SKIP" (vs the "OK" trading heartbeat) so the monitor can
   // tell degraded-liveness apart from healthy trading. Same g_live + HB_PERIOD gate as the
   // normal write -> UNREACHABLE in the Strategy Tester (LiveReady()==true when !g_live, so
   // this branch is never taken, and Heartbeat's only call sites stay g_live-gated) => the
   // backtest stays byte-identical.
   if(!LiveReady())
   {
      if(g_live && TimeCurrent()-g_lastHB>=HB_PERIOD){ Heartbeat("SKIP"); g_lastHB=TimeCurrent(); }
      return;
   }

   datetime utcDay=UtcDayStart(bt);
   MqlDateTime t; TimeToStruct(ToUtc(TimeCurrent()),t);
   int hour=t.hour, minute=t.min, dow=t.day_of_week;

   UpdateRealized();

   if(utcDay>g_curDay)
   {
      for(int s=0;s<N_SER;s++) ExtendSeries(s,utcDay);
      RecomputeDaily();
      g_did20=false; g_did0705=false;
      g_pendResplit=true;                    // one re-split check per day (band OR harvest)
      g_curDay=utcDay;
   }
   // [F3 MARGIN GOVERNOR] compute the account-aggregate haircut ONCE per bar, BEFORE
   // Site A (band re-split), Site B (sleeve loop) and Site C (v34), so all three inherit
   // the same uniform shrink. Self-returns inert (g_f3MlShrink=1.0) at InpMinMarginLevel<=0
   // -> frozen book unchanged (mirrors the F3_GuardianPass / LiveReady inert-at-default pattern).
   F3_MlGovernorPrepass(hour,dow);

   // V7: the concentration BAND replaces V6's calendar-quarter re-split cadence.
   // Evaluated once per UTC day at the first all-markets-open bar (retried each bar
   // until markets open — re-splits must never fire into a closed market, or CloseAll
   // silently fails while the ledger reseeds = accounting drift). BandTriggered()
   // enforces the 5-day min-gap via g_quarterStart; the k=2.5 HarvestTriggered() stays
   // as an INERT guard (fired 0x under the SYM band in six years — the band always
   // crosses share>InpBandUp first) so it changes nothing in-sample but covers
   // degenerate states. g_lastRebalQ is now log-only (no calendar trigger).
   if(g_pendResplit && AllMarketsOpen())
   {
      g_pendResplit=false;                   // checked once today, at first all-open bar
      if(BandTriggered() || HarvestTriggered()) QuarterRebalance(hour,dow);
   }

   if(!g_did0705 && (hour>7 || (hour==7 && minute>=5))){ RecomputeAUD();    g_did0705=true; }
   if(!g_did20   &&  hour>=20)                          { RecomputeEURGBP(); g_did20=true;   }

   for(int n=0;n<N_SLEEVE;n++)
   {
      if(W[n]<=0.0) continue;
      trade.SetExpertMagicNumber(InpMagicBase+n+1);
      trade.SetTypeFillingBySymbol(g_slSym[n]);
      ExecSleeve(n,hour,dow);
   }

   // [F3 SEAM V] the v3.4 consumption layer - AFTER the v7 sleeve loop, so the v7
   // bar pass above is untouched by construction. F3_V34Pass never writes any v7
   // global (TRANSPLANT_V7.md par.4).
   if(g_f3V34On) F3_V34Pass(bt);

   if(g_live && TimeCurrent()-g_lastHB>=HB_PERIOD){ Heartbeat(); g_lastHB=TimeCurrent(); }
}
//+------------------------------------------------------------------+

