//+------------------------------------------------------------------+
//| Book/BookExec.mqh - unified per-bar sizing + reconcile loop.     |
//|                                                                    |
//| The v3 core (EA_V3_DESIGN par.4.1 / MODEL_SPEC par.4), replicating |
//| record_engine_ext._run_chunk sizing arithmetic EXACTLY:            |
//|   base = ACCOUNT_BALANCE  (realized cash - NOT equity)             |
//|   per symbol k with net_frac!=0:                                   |
//|     g    = net_frac * InpScale                                     |
//|     dir  = sign(g); px = dir>0?Ask:Bid                            |
//|     unit = px * SYMBOL_TRADE_CONTRACT_SIZE * FED_Eurq(k)          |
//|     raw  = g*base/unit                                             |
//|     lots = floor(|raw|/step + 1e-9)*step, ->0 if < min_lot        |
//|   margin_sum = Sum(|lots|*unit/leverage[k]) using the MODEL        |
//|     per-symbol leverage; if > InpMarginCap*base one UNIFORM        |
//|     shrink = InpMarginCap*base/margin_sum (then RE-FLOOR each leg).|
//|   rebalance band InpRebalBand: retrade a leg ONLY on sign-flip /   |
//|     cross-to-zero / reduce / |want-held|/|held| > band.           |
//|                                                                    |
//| Execution primitives (RoundLots/SendSplit/CloseAll/ReducePos/      |
//| HeldNet/MarketOpen/OpenDir) lifted from FMA3/V7Core.mqh, renamed   |
//| FED_*. ONE net position + ONE magic per symbol (FED_Magic).        |
//| Requires g_fedTrade[]/g_fedLev[]/g_fedTgt[]/FED_NSYM (FedReplay),  |
//| FED_Eurq (FedConvert), and the `trade` CTrade object (here).       |
//+------------------------------------------------------------------+

CTrade trade;                     // shared order object

long g_fedNSplit=0, g_fedNReject=0;
bool g_fedPendExec=false;         // a leg deferred on a closed market -> retry next bar
bool g_fedLegDefer[FED_NSYM];

//--- position-fidelity snapshot (DEMO_GO_NOGO #2): the last FED_Reconcile pass's
//--- want/held per leg, so the hourly telemetry can record held-vs-target.
//--- NOTE these are RAW inputs, not a verdict: held is DESIGNED to differ from
//--- want by up to InpRebalBand (the churn dead-band, line ~276), so "fidelity"
//--- is only definable downstream, with the band in view. Logging the verdict
//--- here would bake one definition into the binary.
double g_fedWant[FED_NSYM];       // target lots this pass (signed, post-InpScale/round/cap)
double g_fedHeld[FED_NSYM];       // net lots actually held at the same instant (signed)
bool   g_fedUnsized[FED_NSYM];    // nonzero target but no price/eurq -> held, not flattened
// WHEN the snapshot above was taken. Without this the telemetry silently lies:
// TelemetryHour() can fire several times per Pump() while FED_Reconcile() runs
// once at the end, so a multi-hour catch-up pass stamps the SAME stale want/held
// onto every hour. Scored naively that reads as a fidelity failure (measured
// 96.75% on run 44) when the book was in fact fine. Log the age; score only fresh.
long   g_fedSnapTs = 0;

//====================================================================
// LOGGING (decisions CSV) - live appends / tester overwrites in OnInit
//====================================================================
int g_fedLogh=INVALID_HANDLE;
void FED_LogRow(string sym,string ev,double frac,double want,double held,double after)
  {
   if(!InpLog || g_fedLogh==INVALID_HANDLE) return;
   FileWrite(g_fedLogh,
             TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
             sym,ev,DoubleToString(frac,12),DoubleToString(want,2),
             DoubleToString(held,2),DoubleToString(after,2),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1));
   if(g_fedLive) FileFlush(g_fedLogh);           // tester: rely on FileClose (per-row flush is heavy I/O)
  }

//====================================================================
// ORDER-REJECT LOG (live-only; tester no-op -> byte-neutral backtest)
//====================================================================
bool   g_fedLive=true;
void FED_LogReject(string where,string sym,double vol,uint rc,string cmt)
  {
   if(!g_fedLive) return;
   int h=FileOpen("fma3v3_rejects.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)==0) FileWrite(h,"time","where","symbol","volume","retcode","comment");
   FileSeek(h,0,SEEK_END);
   FileWrite(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),where,sym,
             DoubleToString(vol,2),IntegerToString((long)rc),cmt);
   FileFlush(h); FileClose(h);
  }

//====================================================================
// SIZE-SKIP WARN (once per symbol per session)
//====================================================================
string g_fedSkipSym[FED_NSYM];
int    g_fedSkipN=0;
void FED_SizeSkipWarn(string sym)
  {
   for(int i=0;i<g_fedSkipN;i++) if(g_fedSkipSym[i]==sym) return;
   if(g_fedSkipN>=FED_NSYM) return;
   g_fedSkipSym[g_fedSkipN]=sym; g_fedSkipN++;
   Print("FED SIZE SKIP: ",sym," px/eurq/contract unavailable -> leg not sized");
  }

//====================================================================
// EXECUTION PRIMITIVES (from V7Core.mqh, renamed FED_*)
//====================================================================
double FED_RoundLots(string sym,double lots)
  {
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   if(step<=0) step=0.01;
   double n=MathFloor(lots/step+1e-9);
   double out=n*step;
   if(out<minl) return 0.0;
   return out;
  }

//--- split any desired size into chunks <= SYMBOL_VOLUME_MAX (invalid-volume guard)
void FED_SendSplit(string sym,int dir,double vol)
  {
   double vmax=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   if(vmax<=0) vmax=vol;
   double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double rem=vol; int chunks=0;
   for(int i=0;i<40 && rem>=minl;i++)
     {
      double chunk=FED_RoundLots(sym,MathMin(rem,vmax));
      if(chunk<=0) break;
      bool ok=(dir>0)?trade.Buy(chunk,sym):trade.Sell(chunk,sym);
      if(!ok && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
        { g_fedNReject++; FED_LogReject("SendSplit",sym,chunk,trade.ResultRetcode(),trade.ResultComment()); break; }
      chunks++; rem-=chunk;
     }
   if(chunks>1) g_fedNSplit++;
  }

void FED_OpenDir(string sym,double signedVol)
  {
   if(signedVol>0)      FED_SendSplit(sym,+1, signedVol);
   else if(signedVol<0) FED_SendSplit(sym,-1,-signedVol);
  }

double FED_HeldNet(string sym,long magic)
  {
   double net=0.0; int tot=PositionsTotal();
   for(int i=0;i<tot;i++)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=magic) continue;
      double v=PositionGetDouble(POSITION_VOLUME);
      net += (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)? v : -v;
     }
   return net;
  }

int FED_CollectTickets(string sym,long magic,int wantType,ulong &tks[])
  {
   int n=0,tot=PositionsTotal();
   for(int i=0;i<tot;i++)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=magic) continue;
      if(wantType>=0 && PositionGetInteger(POSITION_TYPE)!=wantType) continue;
      ArrayResize(tks,n+1); tks[n]=tk; n++;
     }
   return n;
  }

void FED_CloseAll(string sym,long magic)
  {
   ulong tks[]; int n=FED_CollectTickets(sym,magic,-1,tks);
   for(int i=0;i<n;i++)
      if(!trade.PositionClose(tks[i]) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
         FED_LogReject("CloseAll",sym,0.0,trade.ResultRetcode(),trade.ResultComment());
  }

void FED_ReducePos(string sym,long magic,double vol,int heldType)
  {
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP); if(step<=0) step=0.01;
   double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);  if(minl<=0) minl=step;
   double rem=vol; ulong tks[]; int n=FED_CollectTickets(sym,magic,heldType,tks);
   for(int i=0;i<n && rem>=step*0.5;i++)
     {
      if(!PositionSelectByTicket(tks[i])) continue;
      double pv=PositionGetDouble(POSITION_VOLUME);
      double cv=MathMin(pv,rem);
      cv=MathFloor(cv/step+1e-9)*step;                  // floor, never round UP past pv
      if(cv<step*0.5) continue;
      if(cv>=pv-step*0.5)
        {
         if(!trade.PositionClose(tks[i]) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
            FED_LogReject("ReducePos",sym,cv,trade.ResultRetcode(),trade.ResultComment());
        }
      else
        {
         if(cv<minl-step*0.5 || pv-cv<minl-step*0.5) continue;   // sub-min partial: defer (results-neutral)
         if(!trade.PositionClosePartial(tks[i],cv) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
            FED_LogReject("ReducePosPartial",sym,cv,trade.ResultRetcode(),trade.ResultComment());
        }
      rem-=cv;
     }
  }

//--- session check in SERVER time (the clock chart ticks 24/7; FX/index legs
//--- must never fire into a closed market).
bool FED_MarketOpen(string sym)
  {
   MqlDateTime t; TimeToStruct(TimeCurrent(),t);
   int now=t.hour*3600+t.min*60+t.sec;
   datetime from,to;
   for(int i=0;i<8 && SymbolInfoSessionTrade(sym,(ENUM_DAY_OF_WEEK)t.day_of_week,i,from,to);i++)
     {
      int f=(int)((long)from%86400);
      int o=(int)MathMin((long)to,86400);
      if(now>=f && now<o) return true;
     }
   return false;
  }

//====================================================================
// THE UNIFIED SIZING + RECONCILE PASS (once per new H1 bar / defer retry)
//====================================================================
void FED_Reconcile()
  {
   double base=AccountInfoDouble(ACCOUNT_BALANCE);      // realized cash - model sizes off BALANCE
   if(base<=0.0){ g_fedPendExec=false; return; }

   // --- pass 1: desired lots off the shared balance + margin projection ---
   double desired[FED_NSYM];
   bool   unsized[FED_NSYM];       // nonzero target but px/eurq/contract unavailable -> HOLD, never flatten
   double marginSum=0.0;
   for(int k=0;k<FED_NSYM;k++)
     {
      desired[k]=0.0; unsized[k]=false;
      double g=g_fedTgt[k]*InpScale;
      if(g==0.0) continue;
      string sym=g_fedTrade[k];
      int dir=(g>0)?1:-1;
      double px=(dir>0)?SymbolInfoDouble(sym,SYMBOL_ASK):SymbolInfoDouble(sym,SYMBOL_BID);
      double contract=SymbolInfoDouble(sym,SYMBOL_TRADE_CONTRACT_SIZE);
      double eurq=FED_Eurq(sym);
      if(px<=0.0 || contract<=0.0 || eurq<=0.0){ FED_SizeSkipWarn(sym); unsized[k]=true; continue; }
      double unit=px*contract*eurq;
      double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP); if(step<=0) step=0.01;
      double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
      double raw=g*base/unit;
      double L=MathFloor(MathAbs(raw)/step+1e-9)*step;
      if(L<minl) L=0.0;
      desired[k]=dir*L;
      marginSum += MathAbs(desired[k])*unit/g_fedLev[k];
     }

   // --- margin cap: ONE uniform shrink (record_engine_ext lines 361-364) ---
   double shrink=1.0;
   double cap=base*InpMarginCap;
   if(marginSum>cap && marginSum>0.0) shrink=cap/marginSum;

   // --- pass 2: execute fills with the rebalance band ---
   bool anyDefer=false;
   for(int k=0;k<FED_NSYM;k++)
     {
      string sym=g_fedTrade[k];
      long   magic=FED_Magic(k);
      double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP); if(step<=0) step=0.01;
      double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);

      // want = shrunk desired, RE-FLOORED to the step (record_engine lines 370-374)
      double want=desired[k]*shrink;
      int wdir=(want>0)?1:((want<0)?-1:0);
      want=wdir*MathFloor(MathAbs(want)/step+1e-9)*step;
      if(MathAbs(want)<minl) want=0.0;

      // [FIX] respect the broker's per-symbol TOTAL-volume cap (SYMBOL_VOLUME_LIMIT).
      // The frictionless record has no such ceiling; a real account does (e.g. XAUUSD 10,
      // SOLUSD 1000 lots). Cap the PHYSICAL position here so v3 stops retrying the
      // un-holdable excess every bar (the 51k reject spin) and the volume-limited
      // under-holding is explicit. The margin shrink above is computed on the UNCAPPED
      // desired (matches the model exactly); only the un-fillable overflow is dropped.
      double vlim=SymbolInfoDouble(sym,SYMBOL_VOLUME_LIMIT);
      if(vlim>0.0 && MathAbs(want)>vlim) want=wdir*MathFloor(vlim/step+1e-9)*step;

      double held=FED_HeldNet(sym,magic);

      // fidelity snapshot: record want/held for EVERY leg (incl. flat + unsized)
      // before any of the early-continues below, so the hourly row is complete.
      g_fedWant[k]=want; g_fedHeld[k]=held; g_fedUnsized[k]=unsized[k];
      g_fedSnapTs=(long)TimeCurrent();          // stamp: this pair is live as of NOW

      // [FIX] transient missing quote on a NONZERO-target leg: HOLD the position,
      // never let want=0 be read as a cross-to-zero close. Retry next bar.
      if(unsized[k])
        {
         if(MathAbs(held)>step*0.5){ g_fedLegDefer[k]=true; anyDefer=true; }
         continue;
        }

      int sgnT=(want>0)?1:((want<0)?-1:0);
      int sgnP=(held>0)?1:((held<0)?-1:0);

      bool wantChange=false;
      if(sgnT==0)         wantChange=(sgnP!=0);          // cross-to-zero
      else if(sgnT!=sgnP) wantChange=true;               // sign-flip / open
      else
        {
         double drift=MathAbs(MathAbs(want)-MathAbs(held))/MathAbs(held);
         wantChange=(drift>InpRebalBand);                // reduce/add only past the band
        }
      if(!wantChange){ g_fedLegDefer[k]=false; continue; }

      if(!FED_MarketOpen(sym))
        {
         if(!g_fedLegDefer[k]){ FED_LogRow(sym,"CLOSED",g_fedTgt[k],want,held,0); g_fedLegDefer[k]=true; }
         anyDefer=true;
         continue;
        }
      g_fedLegDefer[k]=false;

      trade.SetExpertMagicNumber(magic);
      trade.SetTypeFillingBySymbol(sym);

      if(sgnT==0)                        FED_CloseAll(sym,magic);                 // target flat
      else if(sgnP==0)                   FED_OpenDir(sym,want);                   // from flat
      else if(sgnT!=sgnP){ FED_CloseAll(sym,magic); FED_OpenDir(sym,want); }      // reversal: close+reopen
      else
        {
         double dv=MathAbs(want)-MathAbs(held);
         if(dv>0)      FED_OpenDir(sym,sgnT*dv);                                  // add toward target
         else if(dv<0) FED_ReducePos(sym,magic,-dv,(sgnP>0)?POSITION_TYPE_BUY:POSITION_TYPE_SELL); // trim
        }

      double after=FED_HeldNet(sym,magic);
      g_fedHeld[k]=after;                                // post-fill: what we ACTUALLY hold
      if(MathAbs(after-held)<step*0.5) continue;         // rejected / no-op
      string ev = (MathAbs(after)<1e-9)              ? "CLOSE" :
                  (MathAbs(held)<1e-9)               ? "OPEN"  :
                  (after*held<0)                     ? "FLIP"  :
                  (MathAbs(after)>MathAbs(held))     ? "ADD"   : "REDUCE";
      FED_LogRow(sym,ev,g_fedTgt[k],want,held,after);
     }

   g_fedTgtDirty=false;
   g_fedPendExec=anyDefer;
  }
//+------------------------------------------------------------------+
