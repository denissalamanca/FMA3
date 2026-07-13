//+------------------------------------------------------------------+
//| FMA3/V34Replay.mqh - F3_* tester loader: frozen-targets CSV       |
//| (SPEC par.3). Fresh implementation - the FMA2 loader was used as  |
//| a FILE-FORMAT reference only, never as a code base.               |
//|                                                                    |
//| File (Common\Files, InpV34ReplayFile):                             |
//|   line 1 : global_scale=10.0,config_hash=51a7541cc2aaa593[,fmt=2]  |
//|   rows   : ts_server_epoch,symbol,exposure_frac,sleeve             |
//|            [,flat_at_server_hour,no_entry_after_hour]              |
//|                                                                    |
//| fmt=2 adds FLAT-HOUR SENTINELS: an in-span hour whose frozen book  |
//| is entirely flat carries exactly one row <epoch>,__GRID__,0,flat.  |
//| The sentinel registers its epoch in the row stream (so the exact-  |
//| match cursor finds the hour and the book FLATTENS) but adds no     |
//| leg, interns no symbol and is excluded from the symbol count.      |
//| Hours ABSENT from the file (weekends/warmup) still mean 'no data'  |
//| -> keep-last-good HOLDS, which is correct there. fmt absent =      |
//| fmt=1 legacy: in-span empty hours keep-last-good (WARNed at load). |
//| ts = H1 bar-open SERVER wall clock as epoch (iTime semantics, no   |
//| tz shift), ascending. exposure_frac = signed fraction of the v3.4  |
//| SUB-BOOK equity at native scale 10 (the EA multiplies InpV34Mult   |
//| only - ONE frozen artifact serves every preset).                   |
//|                                                                    |
//| Strictness (beyond FMA2): sleeve column MANDATORY; ANY bad /       |
//| unresolvable / out-of-order row => INIT_FAILED (a frozen file must |
//| be perfect). Header hash != F3_V34_CONFIG_HASH => INIT_FAILED (G2a)|
//|                                                                    |
//| Symbol map (InpV34SymbolMap, "repo=broker;..."): the replay CSV    |
//| carries the REPO symbol names; the map translates repo -> broker   |
//| ONCE here at load time, so V34Exec and every SymbolSelect/order    |
//| path downstream operate purely on BROKER names. Unknown/empty map  |
//| entries = identity. A mapped broker symbol not available via       |
//| SymbolSelect => INIT_FAILED with a journal line naming the symbol. |
//+------------------------------------------------------------------+

// The FMA3 v1.0 federation pin hash (strategy_fma3.config_hash(), fma3_v1_pin.json).
// scripts/export_v34_replay.py stamps the SAME constant and hard-fails if the
// underlying v3.4 brain config drifts - the two checks meet at this string.
#define F3_V34_CONFIG_HASH "51a7541cc2aaa593"

long     g_f3RepTs[];        // per-row H1 server epoch (ascending)
int      g_f3RepSym[];       // symbol-table index
int      g_f3RepSlv[];       // sleeve index 0..7
double   g_f3RepFrac[];      // exposure frac (native s10)
int      g_f3RepRows   = 0;
int      g_f3RepCursor = 0;  // forward cursor (O(rows) total across the run)
int      g_f3RepWarns  = 0;  // keep-last-good episodes logged
double   g_f3RepScale  = 0.0;// header global_scale echo
int      g_f3RepFmt    = 1;  // header fmt token (1=legacy, 2=flat-hour sentinels)
bool     g_f3TgtDirty  = false; // a new target vector was applied (exec pass due)

// repo -> broker symbol map (parsed from InpV34SymbolMap at load time)
string   g_f3MapRepo[];
string   g_f3MapBroker[];
int      g_f3NMap = 0;

//--- parse InpV34SymbolMap ("repo=broker;...") + validate every mapped broker
//--- symbol is available on this terminal. Logs each mapping applied.
//--- false => INIT_FAILED (a mapped broker symbol is missing - trading the
//--- repo name would silently under-fill the whole book).
bool F3_ParseSymbolMap()
  {
   g_f3NMap=0;
   string entries[];
   int ne=StringSplit(InpV34SymbolMap,';',entries);
   ArrayResize(g_f3MapRepo,ne>0?ne:1);
   ArrayResize(g_f3MapBroker,ne>0?ne:1);
   for(int i=0;i<ne;i++)
     {
      if(StringLen(entries[i])==0) continue;             // empty entry = identity
      string kv[];
      if(StringSplit(entries[i],'=',kv)!=2 || StringLen(kv[0])==0 || StringLen(kv[1])==0)
        {
         Print("F3 SYMMAP WARN: malformed map entry '",entries[i],
               "' ignored (want repo=broker) - identity mapping applies.");
         continue;
        }
      if(kv[0]==kv[1])
        {
         Print("F3 SYMMAP: ",kv[0]," -> ",kv[1]," (identity, no-op).");
         continue;
        }
      if(!SymbolSelect(kv[1],true))
        {
         Print("F3 SYMMAP FATAL: mapped broker symbol '",kv[1],"' (repo '",kv[0],
               "') is NOT available on this terminal (SymbolSelect failed). ",
               "Fix InpV34SymbolMap or ask the broker for the symbol. INIT_FAILED.");
         return false;
        }
      g_f3MapRepo[g_f3NMap]=kv[0];
      g_f3MapBroker[g_f3NMap]=kv[1];
      g_f3NMap++;
      Print("F3 SYMMAP: replay symbol ",kv[0]," -> broker ",kv[1]);
     }
   return true;
  }

//--- repo -> broker translation (identity when unmapped)
string F3_MapSymbol(const string sym)
  {
   for(int i=0;i<g_f3NMap;i++) if(g_f3MapRepo[i]==sym) return g_f3MapBroker[i];
   return sym;
  }

//--- load + validate the frozen CSV. false => INIT_FAILED (no orders exist yet).
bool F3_LoadReplay()
  {
   if(!F3_ParseSymbolMap()) return false;   // repo->broker map (one pass, load-time)
   int h=FileOpen(InpV34ReplayFile,FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h==INVALID_HANDLE)
     {
      Print("F3 REPLAY FATAL: cannot open Common\\Files\\",InpV34ReplayFile,
            " (err=",GetLastError(),")");
      return false;
     }
   // ---- header: key=value tokens, order-free ----
   string header=FileReadString(h);
   StringReplace(header,"\r","");
   string hashv="",scalev="",fmtv="";
   string toks[];
   int nt=StringSplit(header,',',toks);
   for(int i=0;i<nt;i++)
     {
      string kv[];
      if(StringSplit(toks[i],'=',kv)!=2) continue;
      if(kv[0]=="config_hash")  hashv=kv[1];
      else if(kv[0]=="global_scale") scalev=kv[1];
      else if(kv[0]=="fmt")          fmtv=kv[1];
     }
   if(hashv!=F3_V34_CONFIG_HASH)
     {
      Print("F3 REPLAY FATAL: config_hash mismatch - file '",hashv,
            "' vs compiled '",F3_V34_CONFIG_HASH,
            "'. Refusing to trade a drifted frozen book (G2a).");
      FileClose(h);
      return false;
     }
   g_f3RepScale=StringToDouble(scalev);
   g_f3RepFmt=(StringLen(fmtv)>0)?(int)StringToInteger(fmtv):1;
   if(g_f3RepFmt!=1 && g_f3RepFmt!=2)
     {
      Print("F3 REPLAY FATAL: unsupported header fmt='",fmtv,
            "' (this build reads fmt=1 legacy or fmt=2). INIT_FAILED.");
      FileClose(h);
      return false;
     }
   if(g_f3RepFmt<2)
      Print("F3 REPLAY WARN: fmt=1 legacy replay: in-span empty hours will keep-last-good.");

   // ---- data rows ----
   int cap=0, nBad=0;
   long lastTs=0;
   int lastSymIdx=-1; string lastSymStr="";
   while(!FileIsEnding(h))
     {
      string line=FileReadString(h);
      if(StringLen(line)==0) continue;
      StringReplace(line,"\r","");
      string f[];
      int nf=StringSplit(line,',',f);
      if(nf<4 || StringLen(f[3])==0)
        { nBad++; if(nBad<=10) Print("F3 REPLAY: bad row (sleeve col mandatory): ",line); continue; }
      long   ts=StringToInteger(f[0]);
      string sym=f[1];
      if(g_f3RepFmt>=2 && sym=="__GRID__")
        {
         // fmt=2 flat-hour sentinel (<epoch>,__GRID__,0,flat): registers the
         // epoch so the exact-match cursor finds the hour (book flattens by
         // zero-initialize). No leg, no symbol intern, not a bad row.
         if(ts<lastTs)
           { nBad++; if(nBad<=10) Print("F3 REPLAY: ts not ascending at ",ts); continue; }
         lastTs=ts;
         if(g_f3RepRows>=cap)
           {
            cap+=262144;
            ArrayResize(g_f3RepTs,cap); ArrayResize(g_f3RepSym,cap);
            ArrayResize(g_f3RepSlv,cap); ArrayResize(g_f3RepFrac,cap);
           }
         g_f3RepTs[g_f3RepRows]=ts;
         g_f3RepSym[g_f3RepRows]=-1;   // -1 = sentinel, apply pass writes no leg
         g_f3RepSlv[g_f3RepRows]=-1;
         g_f3RepFrac[g_f3RepRows]=0.0;
         g_f3RepRows++;
         continue;
        }
      double fr=StringToDouble(f[2]);
      int    slv=F3_SleeveIndex(f[3]);
      if(slv<0)
        { nBad++; if(nBad<=10) Print("F3 REPLAY: unresolvable sleeve '",f[3],"' - row skipped"); continue; }
      if(ts<lastTs)
        { nBad++; if(nBad<=10) Print("F3 REPLAY: ts not ascending at ",ts); continue; }
      lastTs=ts;
      int flat =(nf>=5 && StringLen(f[4])>0)?(int)StringToInteger(f[4]):-1;
      int noent=(nf>=6 && StringLen(f[5])>0)?(int)StringToInteger(f[5]):-1;
      if(flat>=0)
        {
         if(g_f3FlatHour[slv]>=0 && g_f3FlatHour[slv]!=flat)
           { nBad++; if(nBad<=10) Print("F3 REPLAY: inconsistent flat hour for ",f[3]); }
         else g_f3FlatHour[slv]=flat;
        }
      if(noent>=0)
        {
         if(g_f3NoEntHour[slv]>=0 && g_f3NoEntHour[slv]!=noent)
           { nBad++; if(nBad<=10) Print("F3 REPLAY: inconsistent no-entry hour for ",f[3]); }
         else g_f3NoEntHour[slv]=noent;
        }
      int sj;
      if(sym==lastSymStr && lastSymIdx>=0) sj=lastSymIdx;         // hot-path cache (repo name)
      else { sj=F3_SymIndex(F3_MapSymbol(sym),true);              // repo -> BROKER at intern
             lastSymStr=sym; lastSymIdx=sj; }
      if(sj<0){ nBad++; continue; }
      if(g_f3RepRows>=cap)
        {
         cap+=262144;
         ArrayResize(g_f3RepTs,cap); ArrayResize(g_f3RepSym,cap);
         ArrayResize(g_f3RepSlv,cap); ArrayResize(g_f3RepFrac,cap);
        }
      g_f3RepTs[g_f3RepRows]=ts;
      g_f3RepSym[g_f3RepRows]=sj;
      g_f3RepSlv[g_f3RepRows]=slv;
      g_f3RepFrac[g_f3RepRows]=fr;
      g_f3LegSeen[slv*F3_MAX_SYM+sj]=true;
      g_f3RepRows++;
     }
   FileClose(h);
   if(nBad>0)
     {
      Print("F3 REPLAY FATAL: ",nBad," bad rows at load - a frozen file must be perfect. INIT_FAILED.");
      return false;
     }
   if(g_f3RepRows<=0)
     {
      Print("F3 REPLAY FATAL: no data rows in ",InpV34ReplayFile);
      return false;
     }
   PrintFormat("F3 REPLAY: loaded %d rows, %d symbols, span %s .. %s, hash=%s scale=%s",
               g_f3RepRows,g_f3NSym,
               TimeToString((datetime)g_f3RepTs[0],TIME_DATE|TIME_MINUTES),
               TimeToString((datetime)g_f3RepTs[g_f3RepRows-1],TIME_DATE|TIME_MINUTES),
               hashv,scalev);
   Print("F3 REPLAY span: ",
         TimeToString((datetime)g_f3RepTs[0],TIME_DATE|TIME_MINUTES)," .. ",
         TimeToString((datetime)g_f3RepTs[g_f3RepRows-1],TIME_DATE|TIME_MINUTES),
         " fmt=",g_f3RepFmt);
   if((long)TimeCurrent()<g_f3RepTs[0])
      Print("F3 REPLAY WARN: COVERAGE GAP - tester start ",
            TimeToString(TimeCurrent(),TIME_DATE|TIME_MINUTES),
            " precedes first replay epoch ",
            TimeToString((datetime)g_f3RepTs[0],TIME_DATE|TIME_MINUTES),
            " - the v3.4 book has NO frozen targets until then.");
   return true;
  }

//--- swap in all rows stamped with the just-closed H1 hour. Empty hour =>
//--- keep-last-good + WARN. Within a populated hour a (sleeve,symbol) absent
//--- from the rows = target 0 (flatten-by-omission). fmt=2 __GRID__
//--- sentinels (sym idx -1) match the hour but write no leg => all-flat
//--- hours zero the whole book instead of holding stale targets.
void F3_ReplayApplyHour(const long hourEpoch)
  {
   while(g_f3RepCursor<g_f3RepRows && g_f3RepTs[g_f3RepCursor]<hourEpoch)
      g_f3RepCursor++;
   if(g_f3RepCursor>=g_f3RepRows || g_f3RepTs[g_f3RepCursor]!=hourEpoch)
     {
      g_f3RepWarns++;
      if(g_f3RepWarns<=1000)
         Print("F3 REPLAY keep-last-good: no rows for hour ",
               TimeToString((datetime)hourEpoch,TIME_DATE|TIME_MINUTES));
      return;
     }
   bool wasNonzero=false;
   for(int k=0;k<F3_N_SLEEVE34*F3_MAX_SYM;k++)
      if(g_f3Tgt[k]!=0.0){ wasNonzero=true; break; }
   ArrayInitialize(g_f3Tgt,0.0);
   bool anyLeg=false;
   while(g_f3RepCursor<g_f3RepRows && g_f3RepTs[g_f3RepCursor]==hourEpoch)
     {
      int slv=g_f3RepSlv[g_f3RepCursor];
      int sj =g_f3RepSym[g_f3RepCursor];
      if(sj>=0)                    // sj==-1 = fmt=2 __GRID__ sentinel, no leg
        {
         g_f3Tgt[slv*F3_MAX_SYM+sj]=g_f3RepFrac[g_f3RepCursor];
         if(g_f3RepFrac[g_f3RepCursor]!=0.0) anyLeg=true;
        }
      g_f3RepCursor++;
     }
   if(wasNonzero && !anyLeg)
      Print("F3 REPLAY flat-hour: v34 book flattened @ ",
            TimeToString((datetime)hourEpoch,TIME_DATE|TIME_MINUTES));
   g_f3TgtDirty=true;
  }
