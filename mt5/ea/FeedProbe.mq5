//+------------------------------------------------------------------+
//| FeedProbe.mq5 — S0 multi-symbol M1 feed probe                     |
//| (FABLEBOOKNATIVE_DESIGN.md, FABLE REVISION v2 item 4)             |
//|                                                                    |
//| PURPOSE: measure whether this terminal can furnish, on a BTCUSD    |
//| M1 clock chart, time-synchronized M1 data for the 33 Fable-book    |
//| symbols + the eurq EUR crosses, in BOTH the 1m-OHLC Strategy      |
//| Tester and on a live chart. ZERO trading calls anywhere.          |
//|                                                                    |
//| WHAT IT DOES (all in OnInit; OnTick/OnTimer only retry until the   |
//| lazy history download completes):                                  |
//|  1. SymbolSelect each of the 34 probe symbols (33 book universe    |
//|     in BROKER names per BookReplay.mqh g_fedCanon: USA500->US500,  |
//|     DAX->DE40 applied at emit; + EURJPY, the only eurq cross not   |
//|     already in the book).                                          |
//|  2. Per symbol: earliest available M1 bar (SERIES_FIRSTDATE, with  |
//|     a CopyRates binary-search fallback) + bar count over the depth |
//|     reference week starting 2020-01-02.                            |
//|  3. Over the FIXED probe window (2024-03-02 00:00 .. 2024-03-10    |
//|     23:59 server time = Mon-Fri week 2024-03-04..08 + both        |
//|     surrounding weekends, to catch crypto weekend bars): CopyRates |
//|     M1 for every symbol and build the per-minute has_bar matrix.   |
//|  4. Write FMA3_feedprobe_<mode>.csv to Common Files                |
//|     (mode = tester|live via MQLInfoInteger(MQL_TESTER)) in the     |
//|     same format as FMA3_feedprobe_golden.csv                       |
//|     (research/bpure/probe/export_probe_golden.py). Judge with      |
//|     research/bpure/probe/judge_feedprobe.py.                       |
//|                                                                    |
//| RUN: tester — any short range AFTER the probe window (recommend    |
//|      2024.03.11..2024.03.15), BTCUSD M1, "1 minute OHLC" model.   |
//|      live  — attach to a BTCUSD M1 chart; it retries on a 5s      |
//|      timer while history downloads, then prints FEEDPROBE DONE.   |
//+------------------------------------------------------------------+
#property copyright "FMA3"
#property version   "1.00"
#property description "S0 feed probe: multi-symbol M1 availability vs golden union. NO trading."

#define NSYM 34

// 33-symbol book universe in broker names (BookReplay.mqh g_fedCanon,
// exporter remap USA500->US500 / DAX->DE40 already applied) + EURJPY
// (eurq cross for JPY quotes; the other 7 crosses are already book symbols).
const string PROBE_SYMBOLS[NSYM] =
  {
   "AUDCAD","AUDJPY","AUDNZD","AUDUSD","BTCUSD","CADCHF","CADJPY","DE40",
   "ETHUSD","EURCAD","EURCHF","EURGBP","EURJPY","EURNOK","EURNZD","EURSEK",
   "EURUSD","GBPJPY","JP225","NZDCAD","NZDJPY","NZDUSD","SOLUSD","UK100",
   "US30","US500","USDCHF","USDJPY","USTEC","XAGUSD","XAUUSD","XBRUSD",
   "XNGUSD","XTIUSD"
  };

input datetime InpWinStart = D'2024.03.02 00:00';  // probe window start (server time)
input datetime InpWinEnd   = D'2024.03.10 23:59';  // probe window end (server time, inclusive)
input datetime InpDepth0   = D'2020.01.02 00:00';  // M1 depth reference (golden cache start)
input int      InpMaxTries = 60;                   // retry attempts before writing partial

// --- state ---
int    g_nmin      = 0;        // minutes in window (inclusive)
uchar  g_hasArr[];             // NSYM * g_nmin has_bar matrix
bool   g_selOk[NSYM];
bool   g_symDone[NSYM];
long   g_earliest[NSYM];       // epoch of earliest available M1 bar (0 = unknown)
int    g_bars2020[NSYM];       // M1 bars in [InpDepth0, InpDepth0+7d)
int    g_barsWin[NSYM];        // M1 bars inside the probe window
int    g_misalign[NSYM];       // bars whose time is not :00-aligned on the minute grid
int    g_tries    = 0;
bool   g_written  = false;
string g_mode     = "live";

//+------------------------------------------------------------------+
bool AllDone()
  {
   for(int k=0;k<NSYM;k++) if(!g_symDone[k]) return false;
   return true;
  }
//+------------------------------------------------------------------+
//| Earliest M1 bar via bounded binary search on CopyRates counts.    |
//| Only used when SERIES_FIRSTDATE returns 0. Day resolution, then   |
//| refined to the exact first bar time.                              |
//+------------------------------------------------------------------+
long BinSearchEarliest(const string sym)
  {
   MqlRates r[];
   long lo=(long)D'2008.01.01';
   long hi=(long)TimeCurrent();
   int n=CopyRates(sym,PERIOD_M1,(datetime)lo,(datetime)(lo+7*86400),r);
   if(n>0) return (long)r[0].time;
   while(hi-lo>86400)
     {
      long mid=(lo+hi)/2;
      n=CopyRates(sym,PERIOD_M1,(datetime)mid,(datetime)(mid+7*86400),r);
      if(n>0) hi=mid; else lo=mid;
     }
   n=CopyRates(sym,PERIOD_M1,(datetime)(hi-2*86400),(datetime)(hi+8*86400),r);
   if(n>0) return (long)r[0].time;
   return 0;
  }
//+------------------------------------------------------------------+
//| One symbol's full probe. false = history not ready yet (retry).   |
//+------------------------------------------------------------------+
bool TryOne(const int k)
  {
   const string sym=PROBE_SYMBOLS[k];
   MqlRates r[];
   // --- probe-window bars -> has_bar row ---
   int n=CopyRates(sym,PERIOD_M1,InpWinStart,InpWinEnd,r);
   if(n<0) return false;                       // lazy download pending
   if(n==0 && g_tries<InpMaxTries) return false; // give the download a chance
   int cnt=0;
   for(int i=0;i<n;i++)
     {
      long t=(long)r[i].time;
      if(t<(long)InpWinStart || t>(long)InpWinEnd) continue;
      long off=t-(long)InpWinStart;
      if(off%60!=0){ g_misalign[k]++; continue; }
      g_hasArr[k*g_nmin+(int)(off/60)]=1;
      cnt++;
     }
   g_barsWin[k]=cnt;
   // --- depth reference week ---
   int n2=CopyRates(sym,PERIOD_M1,InpDepth0,(datetime)((long)InpDepth0+7*86400),r);
   if(n2<0) return false;
   g_bars2020[k]=n2;
   // --- earliest available M1 bar ---
   long fd=(long)SeriesInfoInteger(sym,PERIOD_M1,SERIES_FIRSTDATE);
   if(fd<=0) fd=BinSearchEarliest(sym);
   g_earliest[k]=fd;
   g_symDone[k]=true;
   PrintFormat("FEEDPROBE %s: bars_window=%d bars2020wk=%d earliest=%s misaligned=%d",
               sym,g_barsWin[k],g_bars2020[k],
               TimeToString((datetime)fd,TIME_DATE|TIME_MINUTES),g_misalign[k]);
   return true;
  }
//+------------------------------------------------------------------+
void TryAll()
  {
   g_tries++;
   for(int k=0;k<NSYM;k++)
      if(!g_symDone[k]) TryOne(k);
  }
//+------------------------------------------------------------------+
//| Write FMA3_feedprobe_<mode>.csv to Common Files and report.       |
//+------------------------------------------------------------------+
void Finish()
  {
   if(g_written) return;
   g_written=true;
   EventKillTimer();
   int done=0;
   for(int k=0;k<NSYM;k++) if(g_symDone[k]) done++;
   string fname="FMA3_feedprobe_"+g_mode+".csv";
   int h=FileOpen(fname,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
     {
      PrintFormat("FEEDPROBE ERROR: FileOpen(%s) failed, err=%d",fname,GetLastError());
      return;
     }
   FileWriteString(h,StringFormat(
      "#meta,mode=%s,window_start=%I64d,window_end=%I64d,nsym=%d,depth_ref=%I64d,"
      "tries=%d,symbols_done=%d,server=%s,company=%s\n",
      g_mode,(long)InpWinStart,(long)InpWinEnd,NSYM,(long)InpDepth0,
      g_tries,done,AccountInfoString(ACCOUNT_SERVER),AccountInfoString(ACCOUNT_COMPANY)));
   for(int k=0;k<NSYM;k++)
      FileWriteString(h,StringFormat(
         "#depth,%s,select=%d,done=%d,earliest=%I64d,bars2020=%d,bars_window=%d,misaligned=%d\n",
         PROBE_SYMBOLS[k],g_selOk[k]?1:0,g_symDone[k]?1:0,
         g_earliest[k],g_bars2020[k],g_barsWin[k],g_misalign[k]));
   string cols="#cols,ts";
   for(int k=0;k<NSYM;k++) cols+=","+PROBE_SYMBOLS[k];
   FileWriteString(h,cols+"\n");
   int unionMin=0;
   for(int m=0;m<g_nmin;m++)
     {
      bool any=false;
      for(int k=0;k<NSYM;k++) if(g_hasArr[k*g_nmin+m]!=0){ any=true; break; }
      if(!any) continue;
      unionMin++;
      string row=StringFormat("%I64d",(long)InpWinStart+(long)m*60);
      for(int k=0;k<NSYM;k++) row+=(g_hasArr[k*g_nmin+m]!=0)?",1":",0";
      FileWriteString(h,row+"\n");
     }
   FileClose(h);
   PrintFormat("FEEDPROBE DONE mode=%s file=%s union_minutes=%d symbols_done=%d/%d tries=%d",
               g_mode,fname,unionMin,done,NSYM,g_tries);
  }
//+------------------------------------------------------------------+
int OnInit()
  {
   g_mode=(MQLInfoInteger(MQL_TESTER)!=0)?"tester":"live";
   g_nmin=(int)(((long)InpWinEnd-(long)InpWinStart)/60)+1;
   if(g_nmin<=0){ Print("FEEDPROBE ERROR: bad window"); return INIT_PARAMETERS_INCORRECT; }
   ArrayResize(g_hasArr,NSYM*g_nmin);
   ArrayInitialize(g_hasArr,0);
   for(int k=0;k<NSYM;k++)
     {
      g_selOk[k]=SymbolSelect(PROBE_SYMBOLS[k],true);
      g_symDone[k]=false; g_earliest[k]=0;
      g_bars2020[k]=0; g_barsWin[k]=0; g_misalign[k]=0;
      PrintFormat("FEEDPROBE SYMBOL_SELECT %s ok=%d",PROBE_SYMBOLS[k],g_selOk[k]?1:0);
     }
   TryAll();
   if(AllDone()) Finish();
   else if(g_mode=="live") EventSetTimer(5);
   return INIT_SUCCEEDED;
  }
//+------------------------------------------------------------------+
void OnTimer()          // live retry path while history downloads
  {
   if(g_written) return;
   TryAll();
   if(AllDone() || g_tries>=InpMaxTries) Finish();
  }
//+------------------------------------------------------------------+
void OnTick()           // tester retry path; NO trading calls
  {
   if(g_written) return;
   TryAll();
   if(AllDone() || g_tries>=InpMaxTries) Finish();
  }
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(!g_written) Finish();   // tester run ends -> always leave a file
  }
//+------------------------------------------------------------------+
