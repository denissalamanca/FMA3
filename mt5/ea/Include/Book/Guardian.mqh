//+------------------------------------------------------------------+
//| Book/Guardian.mqh - FTMO daily circuit breaker (re-anchored).  |
//|                                                                    |
//| EA_V3_DESIGN par.4.3 / MODEL_SPEC par.5, faithful to               |
//| record_engine_ext._run_chunk_stop:                                 |
//|   On SERVER-day rollover: anchor = PREVIOUS server-day CLOSE-mark   |
//|     equity (day 1 = InpInitial); lift the halt.                    |
//|   Each tick (worst-mark traversed by real ticks / 1m-OHLC bar      |
//|     low-longs/high-shorts): if ACCOUNT_EQUITY <= anchor*(1-x/100)   |
//|     -> flatten ALL this EA's positions, halt (targets->0) until the |
//|     next server-day rollover.                                      |
//|                                                                    |
//| Config-gated: InpDailyStopX (percent, 0 = OFF -> one short-circuit  |
//| branch, no state, no I/O). IC preset x=0; FTMO preset x=3.0.        |
//|                                                                    |
//| NOTE the anchor differs from the v1 Guardian (which used           |
//| max(balance,equity)): v3 uses the previous-day CLOSE equity exactly |
//| as the record engine's `last_close` carry, captured live as the    |
//| ACCOUNT_EQUITY at the first tick of the new server day (~ the prior |
//| day's closing mark).                                                |
//|                                                                    |
//| Requires: InpDailyStopX, InpInitial, InpMagicBase, FED_NSYM,        |
//| FED_MarketOpen, the `trade` object (FedExec.mqh).                   |
//+------------------------------------------------------------------+

double g_fedAnchor  = 0.0;
double g_fedPrevClose= 0.0;       // carried prev-server-day CLOSE-mark equity (= engine last_close)
long   g_fedGuardDay= -1;         // server-day ordinal (TimeCurrent()/86400)
bool   g_fedHalted  = false;
int    g_fedNStops  = 0;

//--- WORST-MARK equity = balance + Σ worst-side unrealized over THIS EA's positions
//--- (M1 bar LOW for longs, HIGH for shorts), matching the record engine's eq_w.
//--- OrderCalcProfit does the account-ccy conversion (broker-accurate).
double FED_WorstMarkEquity()
  {
   double eqw=AccountInfoDouble(ACCOUNT_BALANCE);
   int tot=PositionsTotal();
   for(int i=0;i<tot;i++)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      if(magic<=InpMagicBase || magic>InpMagicBase+FED_NSYM) continue;   // ours only
      string sym=PositionGetString(POSITION_SYMBOL);
      long   type=PositionGetInteger(POSITION_TYPE);
      double vol =PositionGetDouble(POSITION_VOLUME);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double swap =PositionGetDouble(POSITION_SWAP);
      double worst=(type==POSITION_TYPE_BUY)?iLow(sym,PERIOD_M1,0):iHigh(sym,PERIOD_M1,0);
      double wp=0.0;
      ENUM_ORDER_TYPE ot=(type==POSITION_TYPE_BUY)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
      if(worst>0.0 && OrderCalcProfit(ot,sym,vol,entry,worst,wp)) eqw += wp + swap;
      else                                                        eqw += PositionGetDouble(POSITION_PROFIT)+swap; // fallback: current mark
     }
   return eqw;
  }

//--- flatten every position owned by this EA (magics InpMagicBase+1..+NSYM).
//--- Foreign magics untouched; closed markets retried next tick.
void FED_GuardFlattenAll()
  {
   int tot=PositionsTotal();
   for(int i=tot-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      if(magic<=InpMagicBase || magic>InpMagicBase+FED_NSYM) continue;   // ours = base+1..base+NSYM
      string sym=PositionGetString(POSITION_SYMBOL);
      if(!FED_MarketOpen(sym)) continue;                 // session gap - retry next tick
      trade.SetExpertMagicNumber(magic);
      trade.SetTypeFillingBySymbol(sym);
      if(!trade.PositionClose(tk) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
         FED_LogReject("GuardFlatten",sym,0.0,trade.ResultRetcode(),trade.ResultComment());
     }
  }

//--- first statement of OnTick. Returns false while halted (no trading pass runs).
bool FED_GuardianPass()
  {
   if(InpDailyStopX<=0.0) return(true);                  // OFF: single branch, no state

   long day=(long)(TimeCurrent()/86400);                // SERVER day
   if(day!=g_fedGuardDay)
     {
      bool wasHalted=g_fedHalted;
      // day 1: anchor = real seed balance (tester deposit, not the InpInitial input);
      // thereafter anchor = the carried PREVIOUS-day CLOSE-mark equity (engine last_close).
      g_fedAnchor = (g_fedGuardDay<0) ? AccountInfoDouble(ACCOUNT_BALANCE) : g_fedPrevClose;
      g_fedGuardDay=day;
      g_fedHalted=false;
      if(wasHalted)
         Print("FED GUARD_RESUME: new server day, trading re-enabled. anchor=",DoubleToString(g_fedAnchor,2));
     }
   // carry the CLOSE-mark equity forward: last value before the NEXT rollover ~ this day's close.
   g_fedPrevClose=AccountInfoDouble(ACCOUNT_EQUITY);

   if(!g_fedHalted)
     {
      double eqw=FED_WorstMarkEquity();                 // WORST-mark (not point-in-time equity)
      if(g_fedAnchor>0.0 && eqw<=g_fedAnchor*(1.0-InpDailyStopX/100.0))
        {
         g_fedHalted=true; g_fedNStops++;
         Print("FED GUARD_STOP: worst-mark eq ",DoubleToString(eqw,2)," <= anchor ",
               DoubleToString(g_fedAnchor,2)," -",DoubleToString(InpDailyStopX,2),
               "% - flattening ALL and halting until the next server day. (stop #",g_fedNStops,")");
        }
     }

   if(g_fedHalted)
     {
      FED_GuardFlattenAll();                             // retried each tick (session gaps)
      return(false);                                     // NO trading pass while halted
     }
   return(true);
  }
//+------------------------------------------------------------------+
