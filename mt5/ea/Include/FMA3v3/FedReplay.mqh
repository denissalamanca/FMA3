//+------------------------------------------------------------------+
//| FMA3v3/FedReplay.mqh - unified fed_frac stream loader (fmt=3).    |
//|                                                                    |
//| Reads the ALREADY-NETTED unified fed_frac stream that v3 replays   |
//| (EA_V3_DESIGN par.3). Adapted from FMA3/V34Replay.mqh (same cursor,|
//| keep-last-good, __GRID__ sentinel, config-hash gate) but SIMPLER:  |
//|   line 1 : w_v7=0.70,config_hash=51a7541cc2aaa593,fmt=3            |
//|   rows   : ts_server_epoch,broker_symbol,net_frac                 |
//|   flat   : ts_server_epoch,__GRID__,0                             |
//| No sleeve, no schedule columns. net_frac is ALREADY netted across  |
//| v7+v34 (33-symbol union) and does NOT carry the scale dial s (=the  |
//| EA's InpScale). ts = H1 bar-open server epoch (iTime semantics).   |
//|                                                                    |
//| Symbol universe is a FIXED 33-entry table (canonical broker names  |
//| as emitted by the exporter: USA500->US500, DAX->DE40 applied at    |
//| emit) carrying the MODEL leverage per symbol (record_engine        |
//| INSTRUMENTS[.]["leverage"]) so the margin cap reproduces the engine.|
//| Magic-per-symbol = InpMagicBase + table_index + 1 (ONE net position |
//| per symbol). InpV34SymbolMap remaps canonical->this-broker for the  |
//| traded symbol (default empty = identity; the stream is already      |
//| broker-mapped, so the map is only for exotic broker naming).        |
//|                                                                    |
//| Strictness (a frozen file must be perfect): header config_hash !=  |
//| FED_CONFIG_HASH => INIT_FAILED; header fmt != 3 => INIT_FAILED; any |
//| unknown symbol / non-ascending ts / malformed row => INIT_FAILED.  |
//+------------------------------------------------------------------+

#define FED_CONFIG_HASH "51a7541cc2aaa593"
#define FED_NSYM        33

// --- FIXED universe: canonical name + MODEL leverage (record_engine INSTRUMENTS).
//     Order is LAW: it fixes the per-symbol magic (InpMagicBase+idx+1). Do not reorder.
string g_fedCanon[FED_NSYM] =
  {
   "AUDCAD","AUDJPY","AUDNZD","AUDUSD","BTCUSD","CADCHF","CADJPY","DE40","ETHUSD",
   "EURCAD","EURCHF","EURGBP","EURNOK","EURNZD","EURSEK","EURUSD","GBPJPY","JP225",
   "NZDCAD","NZDJPY","NZDUSD","SOLUSD","UK100","US30","US500","USDCHF","USDJPY",
   "USTEC","XAGUSD","XAUUSD","XBRUSD","XNGUSD","XTIUSD"
  };
double g_fedLev[FED_NSYM] =
  {
   20,20,20,20, 2,20,20,20, 2,
   20,30,30,20,20,20,30,20,20,
   20,20,20, 2,20,20,20,30,30,
   20,10,20,10,10,10
  };

string g_fedTrade[FED_NSYM];      // traded (broker) symbol = MapSymbol(canonical)
double g_fedTgt[FED_NSYM];        // current-hour net_frac per symbol (keep-last-good)

// --- row store (ascending) ---
long   g_fedRepTs[];              // per-row H1 server epoch
int    g_fedRepSym[];            // universe index, -1 = __GRID__ sentinel
double g_fedRepFrac[];           // net_frac
int    g_fedRepRows   = 0;
int    g_fedRepCursor = 0;        // forward cursor (O(rows) over the run)
int    g_fedRepWarns  = 0;
int    g_fedRepHits   = 0;        // exact H1-epoch matches (0 for a while => server-tz mismatch)
bool   g_fedTgtDirty  = false;    // a new target vector was applied

// --- canonical -> broker symbol map (parsed from InpV34SymbolMap) ---
string g_fedMapRepo[];
string g_fedMapBroker[];
int    g_fedNMap = 0;

//--- universe lookup by canonical name (-1 if not in the 33-table)
int FED_SymIndex(const string canon)
  {
   for(int i=0;i<FED_NSYM;i++) if(g_fedCanon[i]==canon) return i;
   return -1;
  }

//--- parse InpV34SymbolMap ("canonical=broker;...") + validate each mapped
//--- broker symbol is available. false => INIT_FAILED.
bool FED_ParseSymbolMap()
  {
   g_fedNMap=0;
   string entries[];
   int ne=StringSplit(InpV34SymbolMap,';',entries);
   ArrayResize(g_fedMapRepo,ne>0?ne:1);
   ArrayResize(g_fedMapBroker,ne>0?ne:1);
   for(int i=0;i<ne;i++)
     {
      if(StringLen(entries[i])==0) continue;
      string kv[];
      if(StringSplit(entries[i],'=',kv)!=2 || StringLen(kv[0])==0 || StringLen(kv[1])==0)
        { Print("FED SYMMAP WARN: malformed entry '",entries[i],"' ignored (want canon=broker)."); continue; }
      if(kv[0]==kv[1]){ Print("FED SYMMAP: ",kv[0]," -> ",kv[1]," (identity, no-op)."); continue; }
      if(!SymbolSelect(kv[1],true))
        {
         Print("FED SYMMAP FATAL: mapped broker symbol '",kv[1],"' (canon '",kv[0],
               "') not available on this terminal. Fix InpV34SymbolMap. INIT_FAILED.");
         return false;
        }
      g_fedMapRepo[g_fedNMap]=kv[0];
      g_fedMapBroker[g_fedNMap]=kv[1];
      g_fedNMap++;
      Print("FED SYMMAP: ",kv[0]," -> broker ",kv[1]);
     }
   return true;
  }

//--- canonical -> broker (identity when unmapped)
string FED_MapSymbol(const string canon)
  {
   for(int i=0;i<g_fedNMap;i++) if(g_fedMapRepo[i]==canon) return g_fedMapBroker[i];
   return canon;
  }

//--- build the traded-symbol table + reset the target vector.
void FED_InitUniverse()
  {
   for(int i=0;i<FED_NSYM;i++){ g_fedTrade[i]=FED_MapSymbol(g_fedCanon[i]); g_fedTgt[i]=0.0; }
  }

//--- per-symbol magic (ONE net position per symbol)
long FED_Magic(const int idx){ return InpMagicBase+idx+1; }

//--- load + validate the fmt=3 unified stream. false => INIT_FAILED.
bool FED_LoadReplay()
  {
   if(!FED_ParseSymbolMap()) return false;
   FED_InitUniverse();

   int h=FileOpen(InpFedFracFile,FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
     { Print("FED REPLAY FATAL: cannot open Common\\Files\\",InpFedFracFile," (err=",GetLastError(),")"); return false; }

   // ---- header: order-free key=value tokens ----
   string header=FileReadString(h);
   StringReplace(header,"\r","");
   string hashv="",fmtv="",wv="";
   string toks[];
   int nt=StringSplit(header,',',toks);
   for(int i=0;i<nt;i++)
     {
      string kv[];
      if(StringSplit(toks[i],'=',kv)!=2) continue;
      if(kv[0]=="config_hash") hashv=kv[1];
      else if(kv[0]=="fmt")    fmtv=kv[1];
      else if(kv[0]=="w_v7")   wv=kv[1];
     }
   if(hashv!=FED_CONFIG_HASH)
     {
      Print("FED REPLAY FATAL: config_hash mismatch - file '",hashv,"' vs compiled '",
            FED_CONFIG_HASH,"'. Refusing to trade a drifted stream.");
      FileClose(h); return false;
     }
   if((int)StringToInteger(fmtv)!=3)
     { Print("FED REPLAY FATAL: header fmt='",fmtv,"' - this build reads fmt=3 only. INIT_FAILED."); FileClose(h); return false; }

   // ---- data rows: epoch,symbol,net_frac ----
   int cap=0, nBad=0;
   long lastTs=0;
   while(!FileIsEnding(h))
     {
      string line=FileReadString(h);
      if(StringLen(line)==0) continue;
      StringReplace(line,"\r","");
      string f[];
      int nf=StringSplit(line,',',f);
      if(nf<3)
        { nBad++; if(nBad<=10) Print("FED REPLAY: short row: ",line); continue; }
      long   ts=StringToInteger(f[0]);
      string sym=f[1];
      if(ts<lastTs)
        { nBad++; if(nBad<=10) Print("FED REPLAY: ts not ascending at ",ts); continue; }
      lastTs=ts;

      int sj;
      double fr;
      if(sym=="__GRID__"){ sj=-1; fr=0.0; }               // all-flat hour sentinel
      else
        {
         sj=FED_SymIndex(sym);
         if(sj<0){ nBad++; if(nBad<=10) Print("FED REPLAY: symbol '",sym,"' not in the 33-universe: ",line); continue; }
         fr=StringToDouble(f[2]);
        }
      if(g_fedRepRows>=cap)
        {
         cap+=262144;
         ArrayResize(g_fedRepTs,cap); ArrayResize(g_fedRepSym,cap); ArrayResize(g_fedRepFrac,cap);
        }
      g_fedRepTs[g_fedRepRows]=ts;
      g_fedRepSym[g_fedRepRows]=sj;
      g_fedRepFrac[g_fedRepRows]=fr;
      g_fedRepRows++;
     }
   FileClose(h);

   if(nBad>0){ Print("FED REPLAY FATAL: ",nBad," bad rows - a frozen stream must be perfect. INIT_FAILED."); return false; }
   if(g_fedRepRows<=0){ Print("FED REPLAY FATAL: no data rows in ",InpFedFracFile); return false; }

   PrintFormat("FED REPLAY: loaded %d rows, span %s .. %s, hash=%s fmt=3 w_v7=%s",
               g_fedRepRows,
               TimeToString((datetime)g_fedRepTs[0],TIME_DATE|TIME_MINUTES),
               TimeToString((datetime)g_fedRepTs[g_fedRepRows-1],TIME_DATE|TIME_MINUTES),
               hashv,wv);
   if((long)TimeCurrent()<g_fedRepTs[0])
      Print("FED REPLAY WARN: COVERAGE GAP - tester start ",
            TimeToString(TimeCurrent(),TIME_DATE|TIME_MINUTES),
            " precedes first replay epoch ",
            TimeToString((datetime)g_fedRepTs[0],TIME_DATE|TIME_MINUTES));
   return true;
  }

//--- swap in the target vector for the JUST-CLOSED hour (causal h -> h+1).
//--- Empty hour => keep-last-good (hold g_fedTgt). A present hour zero-inits the
//--- vector then writes each symbol's frac; __GRID__ sentinel (idx -1) writes no
//--- leg so an all-flat hour zeroes the whole book.
void FED_ApplyHour(const long hourEpoch)
  {
   while(g_fedRepCursor<g_fedRepRows && g_fedRepTs[g_fedRepCursor]<hourEpoch)
      g_fedRepCursor++;
   if(g_fedRepCursor>=g_fedRepRows || g_fedRepTs[g_fedRepCursor]!=hourEpoch)
     {
      g_fedRepWarns++;
      if(g_fedRepWarns<=1000)
         Print("FED REPLAY keep-last-good: no rows for hour ",
               TimeToString((datetime)hourEpoch,TIME_DATE|TIME_MINUTES));
      // [GUARD] many consecutive misses with ZERO matches => the broker server
      // timezone differs from the record feed grid; v3 will never trade. Loud once.
      if(g_fedRepHits==0 && g_fedRepWarns==24)
         Print("FED REPLAY *** SERVER-TZ MISMATCH LIKELY *** 24 H1 bars matched NO stream epoch. ",
               "The tester/broker server timezone differs from the record feed. v3 is not trading. ",
               "First stream epoch=",(long)g_fedRepTs[0]," current H1=", (long)hourEpoch);
      return;
     }
   g_fedRepHits++;
   for(int i=0;i<FED_NSYM;i++) g_fedTgt[i]=0.0;          // present hour => flatten-by-omission
   while(g_fedRepCursor<g_fedRepRows && g_fedRepTs[g_fedRepCursor]==hourEpoch)
     {
      int sj=g_fedRepSym[g_fedRepCursor];
      if(sj>=0) g_fedTgt[sj]=g_fedRepFrac[g_fedRepCursor];   // -1 = __GRID__, no leg
      g_fedRepCursor++;
     }
   g_fedTgtDirty=true;
  }
//+------------------------------------------------------------------+
