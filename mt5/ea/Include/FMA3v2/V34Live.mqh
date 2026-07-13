//+------------------------------------------------------------------+
//| FMA3/V34Live.mqh - F3_* live reader: fma3.targets.v1 JSON         |
//| (SPEC par.4). Compiled always, UNREACHABLE in the Strategy Tester |
//| (F3_Init forces the replay source there - mirrors v7's g_live).   |
//|                                                                    |
//| Path: <terminal>/MQL5/Files/<InpV34LiveFile> (EA sandbox; brain    |
//| writes targets.json.tmp -> flush -> rename).                       |
//| Validation on read (cheap mtime check first):                      |
//|   1. schema exact match          -> else reject + CRITICAL alert   |
//|   2. config_hash vs compiled     -> else reject + CRITICAL alert   |
//|   3. seq strictly increasing     -> else ignore silently           |
//| Staleness (bar_time_server older than InpV34StaleMin vs            |
//| TimeTradeServer): HOLD - keep positions, suppress entries/changes, |
//| still honor flat_at_server_hour, alert once per episode.           |
//| NEVER flatten on data failure alone (that is the guardian's job).  |
//+------------------------------------------------------------------+

#define F3_V34_SCHEMA "fma3.targets.v1"

long     g_f3LiveSeq      = -1;     // last ACCEPTED seq
datetime g_f3LiveMtime    = 0;      // last seen file mtime (cheap-skip)
datetime g_f3LiveBarTime  = 0;      // bar_time_server of the last accepted file
bool     g_f3Stale        = false;  // stale/HOLD episode active
bool     g_f3LiveBadEp    = false;  // bad-file episode already alerted
bool     g_f3LiveEverOk   = false;  // at least one file accepted since init

//====================================================================
// minimal JSON scanning helpers (tolerant of whitespace/newlines)
//====================================================================
//--- value substring after "key": within [from,to). Returns "" if absent.
string F3_JRawValue(const string &js,const string key,const int from,const int to)
  {
   string pat="\""+key+"\"";
   int p=StringFind(js,pat,from);
   if(p<0 || (to>0 && p>=to)) return "";
   p=StringFind(js,":",p+StringLen(pat));
   if(p<0) return "";
   p++;
   // skip whitespace
   while(p<StringLen(js))
     {
      ushort c=StringGetCharacter(js,p);
      if(c==' '||c=='\t'||c=='\n'||c=='\r') p++;
      else break;
     }
   if(p>=StringLen(js)) return "";
   if(StringGetCharacter(js,p)=='"')
     {
      int q=StringFind(js,"\"",p+1);
      if(q<0) return "";
      return StringSubstr(js,p+1,q-p-1);
     }
   int e=p;
   while(e<StringLen(js))
     {
      ushort c=StringGetCharacter(js,e);
      if(c==','||c=='}'||c==']'||c=='\n'||c=='\r') break;
      e++;
     }
   string v=StringSubstr(js,p,e-p);
   StringTrimLeft(v); StringTrimRight(v);
   return v;
  }
string F3_JStr(const string &js,const string key){ return F3_JRawValue(js,key,0,-1); }

//--- "YYYY-MM-DD HH:MM:SS" (server) -> datetime
datetime F3_ParseServerTime(string s)
  {
   StringReplace(s,"-",".");
   return StringToTime(s);
  }

//====================================================================
// the read path
//====================================================================
void F3_LiveAlertOnce(const string what)
  {
   if(g_f3LiveBadEp) return;
   g_f3LiveBadEp=true;
   F3_LogRow("F3PORT","V34_BADFILE",0,0,0,0);
   Alert("FMA3 CRITICAL: v3.4 live targets file rejected (",what,
         ") - holding positions, keep-last-good.");
   Print("F3 LIVE CRITICAL: ",what," - HOLD posture (no flatten on data failure).");
  }

//--- try to read+accept the live file. Returns true if a NEW target vector
//--- was applied (g_f3Tgt refreshed).
bool F3_LiveTryRead()
  {
   if(!FileIsExist(InpV34LiveFile))
     {
      F3_LiveAlertOnce("file missing");
      return false;
     }
   datetime mt=(datetime)FileGetInteger(InpV34LiveFile,FILE_MODIFY_DATE);
   if(mt==g_f3LiveMtime) return false;          // unchanged - cheap skip
   int h=FileOpen(InpV34LiveFile,FILE_READ|FILE_TXT|FILE_ANSI);
   if(h==INVALID_HANDLE) return false;          // mid-rename; retry next pass
   string js="";
   while(!FileIsEnding(h)) js+=FileReadString(h)+"\n";
   FileClose(h);
   g_f3LiveMtime=mt;

   // 1. schema
   if(F3_JStr(js,"schema")!=F3_V34_SCHEMA){ F3_LiveAlertOnce("schema mismatch"); return false; }
   // 2. config hash (closes FMA2's D1 gap - checked in BOTH consumption paths)
   if(F3_JStr(js,"config_hash")!=F3_V34_CONFIG_HASH){ F3_LiveAlertOnce("config_hash mismatch"); return false; }
   // 3. seq strictly increasing (<= last accepted: normal re-read, silent)
   long seq=StringToInteger(F3_JStr(js,"seq"));
   if(seq<=g_f3LiveSeq) return false;

   datetime barT=F3_ParseServerTime(F3_JStr(js,"bar_time_server"));
   if(barT<=0){ F3_LiveAlertOnce("bad bar_time_server"); return false; }

   // ---- targets array: zero the vector, fill from records ----
   int a=StringFind(js,"\"targets\"");
   if(a<0){ F3_LiveAlertOnce("no targets array"); return false; }
   a=StringFind(js,"[",a);
   int b=StringFind(js,"]",a);
   if(a<0||b<0){ F3_LiveAlertOnce("malformed targets array"); return false; }

   ArrayInitialize(g_f3Tgt,0.0);
   int p=a;
   int nRec=0,nBad=0;
   while(true)
     {
      int o=StringFind(js,"{",p);
      if(o<0 || o>b) break;
      int c=StringFind(js,"}",o);
      if(c<0 || c>b) break;
      string sleeve=F3_JRawValue(js,"sleeve",o,c);
      string sym   =F3_JRawValue(js,"symbol",o,c);
      string expo  =F3_JRawValue(js,"exposure",o,c);
      string flats =F3_JRawValue(js,"flat_at_server_hour",o,c);
      string noes  =F3_JRawValue(js,"no_entry_after_hour",o,c);
      int slv=F3_SleeveIndex(sleeve);
      if(slv<0 || StringLen(sym)==0 || StringLen(expo)==0) nBad++;
      else
        {
         int sj=F3_SymIndex(sym,true);
         if(sj>=0)
           {
            g_f3Tgt[slv*F3_MAX_SYM+sj]=StringToDouble(expo);
            g_f3LegSeen[slv*F3_MAX_SYM+sj]=true;
            if(StringLen(flats)>0) g_f3FlatHour[slv]=(int)StringToInteger(flats);
            if(StringLen(noes)>0)  g_f3NoEntHour[slv]=(int)StringToInteger(noes);
            nRec++;
           }
        }
      p=c+1;
     }
   if(nBad>0) Print("F3 LIVE WARN: ",nBad," unresolvable target records ignored.");

   g_f3LiveSeq=seq;
   g_f3LiveBarTime=barT;
   g_f3LiveEverOk=true;
   g_f3LiveBadEp=false;                     // healthy file ends any bad episode
   g_f3TgtDirty=true;
   F3_SelectSymbols();                      // new symbols may have appeared
   if(g_f3Stale)
     {
      g_f3Stale=false;
      F3_LogRow("F3PORT","V34_RESUME",0,(double)seq,0,0);
      Print("F3 LIVE: fresh targets accepted (seq=",seq,") - stale episode ended.");
     }
   return true;
  }

//--- once at init: a missing/invalid file is a HOLD posture, INIT still succeeds
void F3_LiveInitialLoad()
  {
   if(FileIsExist(InpV34LiveFile)) F3_LiveTryRead();
   else Print("F3 LIVE: no targets file at init (",InpV34LiveFile,
              ") - HOLD posture until the brain writes one.");
  }

//--- every M1 pass in live mode: read attempt + staleness state machine
void F3_LiveRefresh()
  {
   F3_LiveTryRead();
   bool stale;
   if(!g_f3LiveEverOk) stale=true;                         // nothing valid yet
   else stale=(TimeTradeServer()-g_f3LiveBarTime > (long)InpV34StaleMin*60);
   if(stale && !g_f3Stale)
     {
      g_f3Stale=true;
      F3_LogRow("F3PORT","V34_STALE",0,(double)g_f3LiveSeq,0,0);
      Alert("FMA3: v3.4 targets STALE (>",InpV34StaleMin,
            " min) - holding v3.4 positions, entries suppressed, forced exits still honored.");
     }
   else if(!stale && g_f3Stale)
     {
      g_f3Stale=false;
      F3_LogRow("F3PORT","V34_RESUME",0,(double)g_f3LiveSeq,0,0);
     }
  }
