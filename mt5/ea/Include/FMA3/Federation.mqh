//+------------------------------------------------------------------+
//| FMA3/Federation.mqh - F3_* virtual sub-book ledgers (SPEC par.5)  |
//|                                                                    |
//| ALL code here is NEW FMA3 code (F3_ prefix / g_f3* globals). It    |
//| READS the transplanted v7 ledger (VBalance/FloatingPnL, W[],       |
//| verbatim in V7Core.mqh) but never WRITES any v7 global             |
//| (TRANSPLANT_V7.md par.4).                                          |
//|                                                                    |
//| Construction (SPEC par.5.2 convention A - SHIPPED): both virtual   |
//| books seed at the FULL InpInitial; the w=0.70/0.30 split is        |
//| carried in the dials (InpRisk=8*w*s, InpV34Mult=(1-w)*s), so       |
//| E_v7 + E_v34 - InpInitial ~= ACCOUNT_EQUITY (G3 invariant 1).      |
//+------------------------------------------------------------------+

#define F3_N_SLEEVE34 8
#define F3_MAX_SYM    64
#define F3_BOOKS_FILE "fma3_fed_books.csv"

// v3.4 sleeve order FIXED as FMA2 brain_config.SLEEVES (magic = InpMagicBaseV34+i+1)
string g_f3SlvName[F3_N_SLEEVE34] =
  {"meanrev","carry_breakout","seasonal","intraday",
   "crisis","trend_v2","crypto_smart","mag_xau"};

bool     g_f3V34On        = false;   // the v3.4 consumption layer runs
bool     g_f3Replay       = false;   // v3.4 source = frozen CSV (tester forces true)
double   g_f3Seed34       = 0.0;     // v3.4 virtual-book seed (= InpInitial, convention A)
double   g_f3Realized34   = 0.0;     // realized P&L of magics [base34+1, base34+8]
datetime g_f3Anchor34     = 0;       // history fold anchor (set once at init, never reseeded)
int      g_f3DealCursor34 = 0;
int      g_f3bookh        = INVALID_HANDLE;
datetime g_f3BooksDay     = 0;

// v3.4 symbol table + current target vector (filled by V34Replay / V34Live)
string   g_f3Sym[F3_MAX_SYM];
int      g_f3NSym = 0;
double   g_f3Tgt[F3_N_SLEEVE34*F3_MAX_SYM];      // current exposure frac (native s10)
bool     g_f3LegSeen[F3_N_SLEEVE34*F3_MAX_SYM];  // (sleeve,sym) ever targeted -> reconcile universe
int      g_f3FlatHour[F3_N_SLEEVE34];            // forced flat server hour (-1 = none)
int      g_f3NoEntHour[F3_N_SLEEVE34];           // no-entry-after server hour (-1 = none)

long F3_V34Magic(const int s){ return InpMagicBaseV34 + s + 1; }

int F3_SleeveIndex(const string name)
  {
   for(int s=0;s<F3_N_SLEEVE34;s++) if(g_f3SlvName[s]==name) return s;
   return -1;
  }

//--- symbol-table lookup; addNew appends (and Market-Watch selects) unseen symbols
int F3_SymIndex(const string sym,const bool addNew)
  {
   for(int j=0;j<g_f3NSym;j++) if(g_f3Sym[j]==sym) return j;
   if(!addNew) return -1;
   if(g_f3NSym>=F3_MAX_SYM){ Print("F3 FATAL: >",F3_MAX_SYM," v3.4 symbols"); return -1; }
   g_f3Sym[g_f3NSym]=sym;
   g_f3NSym++;
   return g_f3NSym-1;
  }

//====================================================================
// VIRTUAL BOOK EQUITIES
//====================================================================
//--- v7 virtual sub-book equity = sum of enabled sleeves' (VBalance + floating).
//--- At seed exactly InpInitial (weights sum 1). Feeds SEAM 1 + the books log.
double F3_V7BookEquity()
  {
   double e=0.0;
   for(int n=0;n<N_SLEEVE;n++)
      if(W[n]>0.0) e += VBalance(n)+FloatingPnL(n);
   return e;
  }

//--- v7 virtual sub-book BALANCE = sum of enabled sleeves' VBalance (realized
//--- only, NO floating). Same enabled-set (W>0) as F3_V7BookEquity, so the two
//--- differ EXACTLY by the enabled sleeves' floating P&L. Feeds the balance-basis
//--- reseed (InpReseedBalance): re-splitting the realized pool is legitimate joint
//--- compounding; excluding floating removes the rebalance double-count.
double F3_V7BookBalance()
  {
   double b=0.0;
   for(int n=0;n<N_SLEEVE;n++)
      if(W[n]>0.0) b += VBalance(n);
   return b;
  }

//--- fold new history deals with v3.4 magics into g_f3Realized34 (same cursor
//--- pattern as v7's UpdateRealized, own anchor/cursor; v7 magics fall outside
//--- the range check and are skipped - the two ledgers cannot double-count).
void F3_UpdateRealized34()
  {
   if(!HistorySelect(g_f3Anchor34,TimeCurrent()+1)) return;
   int tot=HistoryDealsTotal();
   for(int i=g_f3DealCursor34;i<tot;i++)
     {
      ulong tk=HistoryDealGetTicket(i); if(tk==0) continue;
      long magic=HistoryDealGetInteger(tk,DEAL_MAGIC);
      int idx=(int)(magic-(InpMagicBaseV34+1));
      if(idx<0 || idx>=F3_N_SLEEVE34) continue;
      double pnl=HistoryDealGetDouble(tk,DEAL_PROFIT)
                +HistoryDealGetDouble(tk,DEAL_SWAP)
                +HistoryDealGetDouble(tk,DEAL_COMMISSION);
      g_f3Realized34+=pnl;
     }
   g_f3DealCursor34=tot;
  }

//--- floating P&L (profit+swap) of ALL open v3.4-magic positions
double F3_V34Floating()
  {
   double f=0.0; int tot=PositionsTotal();
   for(int i=0;i<tot;i++)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      int idx=(int)(magic-(InpMagicBaseV34+1));
      if(idx<0 || idx>=F3_N_SLEEVE34) continue;
      f += PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
     }
   return f;
  }

//--- v3.4 virtual sub-book equity. NEVER reseeded (fixed-fraction book - no
//--- re-split exists in v3.4 by construction).
double F3_V34BookEquity(){ return g_f3Seed34+g_f3Realized34+F3_V34Floating(); }

//====================================================================
// F3 LOGGING - same decisions CSV, disjoint name space ("V34_*"/"F3PORT")
//====================================================================
void F3_LogRow(const string nm,const string ev,double m,double desired,double held,double extra)
  {
   if(!InpLog || g_logh==INVALID_HANDLE) return;
   FileWrite(g_logh,TimeToString(ToUtc(TimeCurrent()),TIME_DATE|TIME_MINUTES),
             nm,ev,DoubleToString(m,4),DoubleToString(desired,2),
             DoubleToString(held,2),DoubleToString(extra,2),
             DoubleToString(F3_V34BookEquity(),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1));
   FileFlush(g_logh);
  }

//====================================================================
// DAILY BOOKS LOG (fma3_fed_books.csv) - feeds the G3 invariants
//====================================================================
void F3_BooksOpen()
  {
   if(!InpLog) return;
   if(g_live)
     {
      g_f3bookh=FileOpen(F3_BOOKS_FILE,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
      if(g_f3bookh!=INVALID_HANDLE)
        {
         if(FileSize(g_f3bookh)==0)
            FileWrite(g_f3bookh,"utc_time","E_v7","E_v34","acct_equity","residual","w_realized");
         FileSeek(g_f3bookh,0,SEEK_END);
        }
     }
   else
     {
      g_f3bookh=FileOpen(F3_BOOKS_FILE,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
      if(g_f3bookh!=INVALID_HANDLE)
         FileWrite(g_f3bookh,"utc_time","E_v7","E_v34","acct_equity","residual","w_realized");
     }
  }

void F3_BooksRow()
  {
   if(g_f3bookh==INVALID_HANDLE) return;
   double e7=F3_V7BookEquity();
   double e34=F3_V34BookEquity();
   double acct=AccountInfoDouble(ACCOUNT_EQUITY);
   double resid=e7+e34-InpInitial-acct;               // G3 invariant 1: |resid| <= 0.5% of acct
   double denom=InpWv7*e7+(1.0-InpWv7)*e34;           // realized w in RETURN space (conv. A:
   double wreal=(denom>0.0)?InpWv7*e7/denom:0.0;      //  both books seeded at InpInitial)
   FileWrite(g_f3bookh,TimeToString(ToUtc(TimeCurrent()),TIME_DATE|TIME_MINUTES),
             DoubleToString(e7,2),DoubleToString(e34,2),DoubleToString(acct,2),
             DoubleToString(resid,2),DoubleToString(wreal,4));
   FileFlush(g_f3bookh);
  }

void F3_BooksDaily(const datetime bt)
  {
   if(g_f3bookh==INVALID_HANDLE) return;
   datetime d=UtcDayStart(bt);
   if(d>g_f3BooksDay){ F3_BooksRow(); g_f3BooksDay=d; }
  }

//====================================================================
// INIT / DEINIT (called from the OnInit/OnDeinit seams)
//====================================================================
void F3_SelectSymbols()
  {
   for(int j=0;j<g_f3NSym;j++)
      if(!SymbolSelect(g_f3Sym[j],true))
         Print("F3 WARN: SymbolSelect failed for '",g_f3Sym[j],
               "' - its v3.4 legs will under-fill with logged rejects.");
  }

bool F3_Init()
  {
   // mode resolution (SPEC par.1): tester forces the CSV source (the live reader
   // is compiled but unreachable in the Strategy Tester, mirroring v7's g_live).
   g_f3V34On  = (InpV34Mode!=V34_OFF);
   g_f3Replay = (InpV34Mode==V34_REPLAY) ||
                (g_f3V34On && MQLInfoInteger(MQL_TESTER));
   g_f3FedActive = (g_f3V34On && InpEnableV7);
   if(g_f3V34On && InpV34Mode==V34_LIVE && MQLInfoInteger(MQL_TESTER))
      Print("F3: Strategy Tester detected - v3.4 source FORCED to replay CSV.");

   // magic-range disjointness assert (belt-and-braces vs a mis-set input)
   long v7lo=InpMagicBase+1,       v7hi=InpMagicBase+N_SLEEVE;
   long v34lo=InpMagicBaseV34+1,   v34hi=InpMagicBaseV34+F3_N_SLEEVE34;
   if(v34lo<=v7hi && v7lo<=v34hi)
     {
      Print("F3 FATAL: v7 magics [",v7lo,",",v7hi,"] overlap v3.4 magics [",
            v34lo,",",v34hi,"] - attribution would corrupt. Aborting.");
      return false;
     }

   // dial-consistency echo (INFORMATIONAL ONLY - InpRisk/InpV34Mult govern; this
   // is the SPEC par.5.2 convention-A arithmetic surfaced for the operator).
   double impliedR=8.0*InpWv7*InpScale;
   double impliedM=(1.0-InpWv7)*InpScale;
   if(MathAbs(impliedR-InpRisk)>1e-6 || MathAbs(impliedM-InpV34Mult)>1e-6)
      PrintFormat("F3 NOTE: dial check - InpRisk=%.4f vs 8*w*s=%.4f; InpV34Mult=%.4f vs (1-w)*s=%.4f "
                  "(w=%.2f s=%.2f informational; the dials as set govern).",
                  InpRisk,impliedR,InpV34Mult,impliedM,InpWv7,InpScale);

   // v3.4 virtual ledger: fresh seed at the FULL InpInitial (convention A)
   g_f3Seed34=InpInitial; g_f3Realized34=0.0;
   g_f3Anchor34=TimeCurrent();
   if(HistorySelect(g_f3Anchor34,TimeCurrent()+1)) g_f3DealCursor34=HistoryDealsTotal();

   for(int s=0;s<F3_N_SLEEVE34;s++){ g_f3FlatHour[s]=-1; g_f3NoEntHour[s]=-1; }
   ArrayInitialize(g_f3Tgt,0.0);
   for(int k=0;k<F3_N_SLEEVE34*F3_MAX_SYM;k++) g_f3LegSeen[k]=false;

   if(g_f3V34On)
     {
      if(g_f3Replay)
        {
         if(!F3_LoadReplay()) return false;     // hash gate: INIT_FAILED (G2a)
        }
      else
        {
         F3_LiveInitialLoad();                  // missing/invalid file = HOLD posture, init OK
        }
      F3_SelectSymbols();
     }

   if(g_f3FedActive) F3_BooksOpen();
   F3_GuardianInit();

   PrintFormat("F3 init: v34mode=%d (replay=%s) v7=%s fed=%s V34Mult=%.4f staleMin=%d "
               "guardianX=%.2f | magics v7 %d..%d, v34 %d..%d | v34 symbols=%d",
               (int)InpV34Mode,(g_f3Replay?"yes":"no"),(InpEnableV7?"on":"off"),
               (g_f3FedActive?"on":"off"),InpV34Mult,InpV34StaleMin,InpDailyStopX,
               (int)v7lo,(int)v7hi,(int)v34lo,(int)v34hi,g_f3NSym);
   return true;
  }

void F3_Deinit()
  {
   if(g_f3bookh!=INVALID_HANDLE)
     {
      F3_BooksRow();                            // final G3 evidence row
      FileClose(g_f3bookh);
      g_f3bookh=INVALID_HANDLE;
     }
  }
