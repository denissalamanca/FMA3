//+------------------------------------------------------------------+
//| CheckHistory.mq5 — which symbol is stalling the live book?        |
//|                                                                    |
//| The live catch-up advances the book only when the MIN front over   |
//| ALL symbols passes the target hour. One symbol without M1 history  |
//| back to the warm blob's hour therefore pins the whole book — and   |
//| the EA waits silently (g_histWaits), which is correct live (absent |
//| history means "not downloaded yet", not "not born") but invisible. |
//|                                                                    |
//| This probes every SELECTED symbol (the EA SymbolSelect()s all 33 + |
//| crosses at init) for M1 history back to the blob hour, and names   |
//| the blockers. CopyRates itself REQUESTS the download, so running   |
//| this repeatedly also drives the fetch: expect later runs to show   |
//| more bars. NO trading, NO files.                                   |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property script_show_inputs

input datetime InpFrom = D'2025.12.31 22:00';   // the warm blob's hour — the book must reach back to here

void OnStart()
  {
   datetime to = TimeCurrent();
   int n = SymbolsTotal(true);
   PrintFormat("CheckHistory: %d selected symbols; need M1 back to %s (now %s)",
               n, TimeToString(InpFrom, TIME_DATE|TIME_MINUTES),
               TimeToString(to, TIME_DATE|TIME_MINUTES));

   int blockers = 0, downloading = 0;
   for(int i = 0; i < n; i++)
     {
      string s = SymbolName(i, true);
      MqlRates r[];
      int got = CopyRates(s, PERIOD_M1, InpFrom, to, r);   // also REQUESTS the download
      datetime first = (datetime)SeriesInfoInteger(s, PERIOD_M1, SERIES_FIRSTDATE);
      long     bars  = SeriesInfoInteger(s, PERIOD_M1, SERIES_BARS_COUNT);
      bool     sync  = (bool)SeriesInfoInteger(s, PERIOD_M1, SERIES_SYNCHRONIZED);

      string flag = "";
      if(got < 0)            { flag = "  <<< BLOCKS: CopyRates<0 (not ready / downloading)"; blockers++; downloading++; }
      else if(got == 0)      { flag = "  <<< BLOCKS: zero bars in range";                    blockers++; }
      else if(first > InpFrom){ flag = StringFormat("  <<< BLOCKS: history starts %s, AFTER the blob hour",
                                                    TimeToString(first, TIME_DATE|TIME_MINUTES)); blockers++; }
      else if(!sync)         { flag = "  (not synchronized yet — may resolve)";              downloading++; }

      PrintFormat("%-10s copy=%8d  first=%s  bars=%I64d  sync=%s%s",
                  s, got, TimeToString(first, TIME_DATE|TIME_MINUTES), bars,
                  sync ? "yes" : "NO", flag);
     }

   PrintFormat("CheckHistory: %d blocker(s), %d still downloading.", blockers, downloading);
   if(blockers == 0)
      Print("CheckHistory: ALL PASS — every symbol has M1 back to the blob hour; "
            "a stalled book is NOT a history problem.");
   else
      Print("CheckHistory: the blockers above pin the min-front, so the book cannot advance. "
            "CopyRates has now REQUESTED their history — wait a few minutes and re-run; "
            "if a symbol never fills, its history simply is not available on this account.");
  }
