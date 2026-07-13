//+------------------------------------------------------------------+
//| FMA3/Guardian.mqh - F3_* FTMO daily-stop module (SPEC par.6)      |
//|                                                                    |
//| Config-gated: InpDailyStopX (percent, 0 = OFF). At x<=0 the ENTIRE |
//| module is one short-circuit branch touching no state and writing   |
//| no files - the G4a bit-identity guarantee.                         |
//|                                                                    |
//| Day anchor: at each SERVER-day rollover,                           |
//|   anchor = max(ACCOUNT_BALANCE, ACCOUNT_EQUITY)  (FTMO convention, |
//|   max() is the conservative side).                                 |
//| Trigger: any tick with equity <= anchor x (1 - x/100):             |
//|   flatten ALL positions owned by this EA (both magic ranges,       |
//|   foreign magics untouched; closed markets retried each tick),     |
//|   latch halted until the next server day (no order path runs; the  |
//|   OnTick seam returns before the bar pass), log GUARD_STOP +       |
//|   Alert(); GUARD_RESUME at rollover.                               |
//| Ledger interaction: the flatten realizes P&L into both books'      |
//|   normal deal attribution - NO reseed, NO band-clock reset         |
//|   (H-FED-2 corollary).                                             |
//| Restart hardening (live): anchor + halt latch persisted so a       |
//|   terminal restart inside a halted day stays halted.               |
//+------------------------------------------------------------------+

#define F3_GUARD_FILE "fma3_fed_guard.csv"

double g_f3DayAnchor = 0.0;
long   g_f3GuardDay  = -1;      // server-day ordinal (TimeCurrent()/86400)
bool   g_f3Halted    = false;

void F3_GuardSave()
  {
   if(!g_live) return;
   int h=FileOpen(F3_GUARD_FILE,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return;
   FileWrite(h,IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)),
             IntegerToString(g_f3GuardDay),
             DoubleToString(g_f3DayAnchor,2),
             IntegerToString(g_f3Halted?1:0));
   FileFlush(h); FileClose(h);
  }

void F3_GuardLoad()
  {
   if(!FileIsExist(F3_GUARD_FILE,FILE_COMMON)) return;
   int h=FileOpen(F3_GUARD_FILE,FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return;
   long login=(long)FileReadNumber(h);
   long day  =(long)FileReadNumber(h);
   double anc=FileReadNumber(h);
   int halted=(int)FileReadNumber(h);
   FileClose(h);
   if(login!=(long)AccountInfoInteger(ACCOUNT_LOGIN)) return;
   long today=(long)(TimeCurrent()/86400);
   if(day!=today) return;                     // stale (previous day) - fresh anchor
   g_f3GuardDay=day; g_f3DayAnchor=anc; g_f3Halted=(halted!=0);
   PrintFormat("F3 GUARD: restored state (day=%d anchor=%.2f halted=%d)",
               (int)day,anc,halted);
  }

void F3_GuardianInit()
  {
   if(InpDailyStopX<=0.0) return;             // OFF: touch nothing
   if(g_live) F3_GuardLoad();
  }

//--- flatten every position owned by this EA (both magic ranges). Positions on
//--- closed markets are skipped and retried on the next tick while halted.
void F3_GuardFlattenAll()
  {
   int tot=PositionsTotal();
   for(int i=tot-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      bool ours=(magic>InpMagicBase    && magic<=InpMagicBase+N_SLEEVE) ||
                (magic>InpMagicBaseV34 && magic<=InpMagicBaseV34+F3_N_SLEEVE34);
      if(!ours) continue;
      string sym=PositionGetString(POSITION_SYMBOL);
      if(!MarketOpen(sym)) continue;          // session gap - retry next tick
      trade.SetExpertMagicNumber(magic);
      trade.SetTypeFillingBySymbol(sym);
      if(!trade.PositionClose(tk) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
         LogReject("GuardFlatten",sym,0,0.0,trade.ResultRetcode(),trade.ResultComment());
     }
  }

//--- first statement of OnTick ([F3 SEAM G]). Returns false while halted.
bool F3_GuardianPass()
  {
   if(InpDailyStopX<=0.0) return(true);       // [G4a] single branch, no state, no I/O

   long day=(long)(TimeCurrent()/86400);      // SERVER day
   if(day!=g_f3GuardDay)
     {
      bool wasHalted=g_f3Halted;
      g_f3GuardDay=day;
      g_f3Halted=false;
      g_f3DayAnchor=MathMax(AccountInfoDouble(ACCOUNT_BALANCE),
                            AccountInfoDouble(ACCOUNT_EQUITY));
      if(wasHalted)
        {
         F3_LogRow("F3PORT","GUARD_RESUME",InpDailyStopX,g_f3DayAnchor,0,0);
         Print("F3 GUARD_RESUME: new server day, trading re-enabled. anchor=",
               DoubleToString(g_f3DayAnchor,2));
        }
      F3_GuardSave();
     }

   if(!g_f3Halted)
     {
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      if(g_f3DayAnchor>0.0 && eq<=g_f3DayAnchor*(1.0-InpDailyStopX/100.0))
        {
         g_f3Halted=true;
         F3_LogRow("F3PORT","GUARD_STOP",InpDailyStopX,g_f3DayAnchor,eq,g_f3DayAnchor-eq);
         Alert("FMA3 GUARD_STOP: equity ",DoubleToString(eq,2)," <= anchor ",
               DoubleToString(g_f3DayAnchor,2)," -",DoubleToString(InpDailyStopX,2),
               "% - flattening ALL and halting until the next server day.");
         F3_GuardSave();
        }
     }

   if(g_f3Halted)
     {
      F3_GuardFlattenAll();                   // retried each tick (session gaps)
      return(false);                          // NO order/signal path runs while halted
     }
   return(true);
  }
