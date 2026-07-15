//+------------------------------------------------------------------+
//| SymbolMetaProbe.mq5 — UNIT 1 of the live-metadata reconciliation. |
//|                                                                   |
//| SCRIPT (OnStart), ZERO trading calls (no CTrade, no OrderSend,    |
//| no position/history query). Attach to ANY chart on the LIVE      |
//| ICMarketsEU-MT5-5 broker; it dumps EVERY execution-relevant      |
//| SymbolInfo field for the 37 core.ALL symbols so the judge (Unit  |
//| 2) can reconcile live broker metadata against the record/engine  |
//| assumptions BEFORE any FeedAssembler.Init(true) relax — the      |
//| DE40 lesson: live SYMBOL_DIGITS=2 vs record FA_DIGITS[DAX]=1     |
//| must be SEEN, not silently discovered at REFUSE time.            |
//|                                                                   |
//| UNIVERSE (canonical): FeedAssembler.mqh FA_SYMS (MODEL names) in  |
//| core.ALL order, remapped to BROKER names via FaBrokerName        |
//| (DAX->DE40, USA500->US500, rest identity). The three H1-only     |
//| signal symbols GBPUSD / XRPUSD / XPTUSD are ALREADY members of    |
//| FA_SYMS (indices 15, 24, 35), so the 37 == FA_SYMS — no append.   |
//| The list is included, never copied, so it can never drift from    |
//| the compute path.                                                 |
//|                                                                   |
//| OUTPUT: Common\Files\FMA3_symbol_meta.csv — a header row + one    |
//| row per symbol (never silently dropped: a symbol that will not    |
//| SymbolSelect still emits its row with select_ok=0 and an error    |
//| flag so the judge sees all 37). All doubles %.17g (exact          |
//| round-trip). record_feed_digits (FA_DIGITS) is appended so the    |
//| judge can flag digit drift against the ask-reconstruction table   |
//| directly, without re-deriving it.                                 |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs
#property description "UNIT 1: dump live broker metadata for the 37 core.ALL symbols. ZERO trading."

// FA_SYMS / FA_DIGITS / FA_NSYM / FaBrokerName — the canonical universe.
#include <Book/FeedAssembler.mqh>

#define SMP_OUT "FMA3_symbol_meta.csv"

//+------------------------------------------------------------------+
//| Read one symbol's metadata and format its CSV row.                |
//| select_ok reflects SymbolSelect; metadata is read regardless (a   |
//| symbol already known to the terminal answers even if select      |
//| fails), so the judge always gets whatever the broker exposes.     |
//+------------------------------------------------------------------+
string BuildRow(const int i, bool &sel_out)
  {
   string model  = FA_SYMS[i];
   string broker = FaBrokerName(model);

   bool   sel    = SymbolSelect(broker, true);
   sel_out       = sel;
   string err    = sel ? "" : "SELECT_FAILED";
   if(!sel)
      PrintFormat("SymbolMetaProbe WARN: SymbolSelect(%s) failed err=%d "
                  "— row still emitted with error flag", broker, GetLastError());

   // integer metadata
   long digits      = SymbolInfoInteger(broker, SYMBOL_DIGITS);
   long trade_mode  = SymbolInfoInteger(broker, SYMBOL_TRADE_MODE);
   long swap_mode   = SymbolInfoInteger(broker, SYMBOL_SWAP_MODE);
   long stops_level = SymbolInfoInteger(broker, SYMBOL_TRADE_STOPS_LEVEL);

   // double metadata
   double point      = SymbolInfoDouble(broker, SYMBOL_POINT);
   double tick_size  = SymbolInfoDouble(broker, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(broker, SYMBOL_TRADE_TICK_VALUE);
   double contract   = SymbolInfoDouble(broker, SYMBOL_TRADE_CONTRACT_SIZE);
   double vol_min    = SymbolInfoDouble(broker, SYMBOL_VOLUME_MIN);
   double vol_max    = SymbolInfoDouble(broker, SYMBOL_VOLUME_MAX);
   double vol_step   = SymbolInfoDouble(broker, SYMBOL_VOLUME_STEP);
   double swap_long  = SymbolInfoDouble(broker, SYMBOL_SWAP_LONG);
   double swap_short = SymbolInfoDouble(broker, SYMBOL_SWAP_SHORT);
   double margin_ini = SymbolInfoDouble(broker, SYMBOL_MARGIN_INITIAL);

   // string metadata
   string ccy_base = "", ccy_profit = "", ccy_margin = "";
   SymbolInfoString(broker, SYMBOL_CURRENCY_BASE,   ccy_base);
   SymbolInfoString(broker, SYMBOL_CURRENCY_PROFIT, ccy_profit);
   SymbolInfoString(broker, SYMBOL_CURRENCY_MARGIN, ccy_margin);

   // Two-part format: the arg count is large, so split for safety.
   string a = StringFormat("%s,%s,%I64d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,",
                           broker, model, digits, point,
                           tick_size, tick_value, contract,
                           vol_min, vol_max, vol_step);
   string b = StringFormat("%I64d,%I64d,%.17g,%.17g,%s,%s,%s,%.17g,%I64d,%d,%s,%d\n",
                           trade_mode, swap_mode, swap_long, swap_short,
                           ccy_base, ccy_profit, ccy_margin,
                           margin_ini, stops_level, sel ? 1 : 0,
                           err, FA_DIGITS[i]);
   return a + b;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   int oh = FileOpen(SMP_OUT, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(oh == INVALID_HANDLE)
     {
      PrintFormat("SymbolMetaProbe FAIL: cannot open %s err=%d",
                  SMP_OUT, GetLastError());
      return;
     }

   FileWriteString(oh,
      "broker_name,model_name,SYMBOL_DIGITS,SYMBOL_POINT,"
      "SYMBOL_TRADE_TICK_SIZE,SYMBOL_TRADE_TICK_VALUE,"
      "SYMBOL_TRADE_CONTRACT_SIZE,SYMBOL_VOLUME_MIN,SYMBOL_VOLUME_MAX,"
      "SYMBOL_VOLUME_STEP,SYMBOL_TRADE_MODE,SYMBOL_SWAP_MODE,"
      "SYMBOL_SWAP_LONG,SYMBOL_SWAP_SHORT,SYMBOL_CURRENCY_BASE,"
      "SYMBOL_CURRENCY_PROFIT,SYMBOL_CURRENCY_MARGIN,SYMBOL_MARGIN_INITIAL,"
      "SYMBOL_TRADE_STOPS_LEVEL,SYMBOL_SELECT_ok,error,record_feed_digits\n");

   int nsel = 0, nfail = 0;
   for(int i = 0; i < FA_NSYM; i++)
     {
      bool ok = false;
      FileWriteString(oh, BuildRow(i, ok));
      if(ok)
         nsel++;
      else
         nfail++;
     }
   FileClose(oh);

   PrintFormat("SymbolMetaProbe DONE: wrote %d symbol rows to Common\\Files\\%s "
               "(%d selected, %d select-failed)",
               FA_NSYM, SMP_OUT, nsel, nfail);
  }
//+------------------------------------------------------------------+
