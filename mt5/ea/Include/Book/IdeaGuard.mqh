//+------------------------------------------------------------------+
//| Book/IdeaGuard.mqh - FTMO 1%-per-trade-idea circuit breaker.     |
//|                                                                    |
//| Implements the VALIDATED rule (research/ftmo1pct/kill_engine.py,   |
//| PR #48, frozen config): the book's 33 legs group into 14 idea-     |
//| units ("clusters", the measured daily |rho|>=0.7 set). Per cluster |
//| C the meter is                                                     |
//|   IDEA_DD_C = FLOAT_C + REAL1H_C                                   |
//|     FLOAT_C  = worst-marked unrealized P&L of C's OPEN positions   |
//|                from entry, SWAP EXCLUDED (Guardian's                |
//|                FED_WorstMarkEquity per-position pattern: M1 LOW for |
//|                longs / HIGH for shorts, OrderCalcProfit account-ccy |
//|                conversion, fallback POSITION_PROFIT)                |
//|     REAL1H_C = realized P&L (profit+commission, SWAP EXCLUDED) of  |
//|                C's DEAL_ENTRY_OUT deals in the trailing 60 minutes  |
//|                HALF-OPEN (now-60min, now] like the model,           |
//|                RECOMPUTED from MT5 deal history every check (no     |
//|                ring buffer, no persisted window - restart-proof     |
//|                for free)                                            |
//| KILL when IDEA_DD_C <= -InpIdeaStopPct/100 * AccountBalance:       |
//| flatten ONLY that cluster's legs (our magics, FED_MarketOpen retry  |
//| like FED_GuardFlattenAll), stamp a 60-min cooldown, print loudly.  |
//| During cooldown the cluster's targets are ZERO (FED_Reconcile      |
//| pass-1 hook). A VIOLATION line prints (edge-triggered, once per    |
//| excursion) if IDEA_DD_C <= -1.0% * balance - the kill at 0.8%      |
//| should pre-empt it; the cockpit greps for "IDEA_VIOLATION".        |
//|                                                                    |
//| Cooldown stamps live in terminal GlobalVariables                    |
//| ("FMA3_IG_<magicBase>_<clusterIdx>" = kill server-time): they      |
//| survive restarts and are namespaced by magic base (IC and FTMO     |
//| terminals share nothing here anyway). Read/written ONLY when the   |
//| feature is on.                                                     |
//|                                                                    |
//| Config-gated: InpIdeaStopPct (percent of balance, 0 = OFF -> one   |
//| short-circuit branch per call site, no state, no I/O, no           |
//| HistorySelect, no GlobalVariable calls). IC preset 0; FTMO 0.8.    |
//|                                                                    |
//| KNOWN DIVERGENCES vs the validated model (record for RECON-19):    |
//|  1. CHECK CADENCE: the EA meters per pump pass (every M1 clock bar |
//|     + 5 s timer, throttled to InpIdeaCheckSec) - FINER than the    |
//|     model's 1-minute grid. Intra-minute excursions the model only  |
//|     sees at the bar close kill marginally EARLIER here =           |
//|     conservative (never later).                                    |
//|  2. ACCOUNTING GRAIN: live positions are PER-TICKET (each add is   |
//|     its own ticket with its own entry price; FLOAT_C sums worst-   |
//|     mark P&L per ticket) while the model carries one net position  |
//|     per leg at a net average entry. Same net exposure, same total  |
//|     P&L; the split changes nothing in the sum, but per-ticket swap  |
//|     and commission attribution can differ from the model's netted  |
//|     approximation at the cents level.                              |
//|  3. If HistorySelect transiently fails the pass runs FLOAT-only    |
//|     (REAL1H=0) rather than skipping - the cooldown flatten retry   |
//|     must never stall on a history hiccup.                          |
//|  4. SWAP is EXCLUDED from the meter (FLOAT and REAL1H) to match    |
//|     the validated model exactly (kill_engine.py books swap to      |
//|     balance, never the cluster meter). FTMO's own per-position     |
//|     view may include swap - a +/-tens-of-EUR ambiguity vs the      |
//|     ~160 EUR pre-emption buffer, accepted for model parity.        |
//|  5. COOLDOWN RE-ANCHOR: session-gapped legs can only be flattened  |
//|     minutes after the kill; each successful close during cooldown  |
//|     re-stamps the cooldown to close-time+60min ("1 hour from the   |
//|     CLOSE", faithful to the rule) so the kill's own realized loss  |
//|     always ages out of the trailing window before re-entry. A      |
//|     +InpIdeaCheckSec slack on every stamp covers close-fill        |
//|     timestamp latency at the window boundary.                      |
//|  6. WARM-RESTART CATCH-UP (!synced): only cooldown MAINTENANCE     |
//|     runs (expiry lift + flatten retry of already-decided kills) -  |
//|     no new metering/kill decisions until the compute clock catches |
//|     the wall clock (Guardian's synced convention).                 |
//|                                                                    |
//| Requires: InpIdeaStopPct, InpIdeaCooldownMin, InpIdeaCheckSec,     |
//| InpMagicBase, FED_NSYM, g_fedCanon (BookReplay.mqh), FED_MarketOpen |
//| + FED_LogReject + the `trade` object (BookExec.mqh), RefuseLatch   |
//| (FableBookNative.mq5).                                             |
//+------------------------------------------------------------------+

#define IG_NCLUST 14

//--- cluster names (index = cluster id; 8..13 = the singletons)
string g_igClustName[IG_NCLUST] =
  {
   "IDX","DBLOC","JPYX","CRYPTO","EURCADX","EURUSDX","PMET","OIL",
   "AUDNZD","EURCHF","EURGBP","EURNOK","XNGUSD","EURSEK"
  };

//--- canonical symbol -> cluster id (PR #48 frozen table). Keyed by the EA's
//--- OWN canonical names and listed in g_fedCanon ORDER for eyeball diffing;
//--- IG_Init verifies full coverage and RefuseLatches on any gap.
//---   IDX(0)    = DE40,JP225,UK100,US30,US500,USTEC
//---   DBLOC(1)  = AUDCAD,AUDUSD,EURNZD,NZDCAD,NZDUSD
//---   JPYX(2)   = AUDJPY,CADJPY,GBPJPY,NZDJPY,USDJPY
//---   CRYPTO(3) = BTCUSD,ETHUSD,SOLUSD
//---   EURCADX(4)= CADCHF,EURCAD    EURUSDX(5)= EURUSD,USDCHF
//---   PMET(6)   = XAGUSD,XAUUSD    OIL(7)    = XBRUSD,XTIUSD
//---   singletons 8..13 = AUDNZD,EURCHF,EURGBP,EURNOK,XNGUSD,EURSEK
string g_igMapSym[FED_NSYM] =
  {
   "AUDCAD","AUDJPY","AUDNZD","AUDUSD","BTCUSD","CADCHF","CADJPY","DE40","ETHUSD",
   "EURCAD","EURCHF","EURGBP","EURNOK","EURNZD","EURSEK","EURUSD","GBPJPY","JP225",
   "NZDCAD","NZDJPY","NZDUSD","SOLUSD","UK100","US30","US500","USDCHF","USDJPY",
   "USTEC","XAGUSD","XAUUSD","XBRUSD","XNGUSD","XTIUSD"
  };
int g_igMapClust[FED_NSYM] =
  {
   1, 2, 8, 1, 3, 4, 2, 0, 3,
   4, 9,10,11, 1,13, 5, 2, 0,
   1, 2, 1, 3, 0, 0, 0, 5, 2,
   0, 6, 6, 7,12, 7
  };

int  g_igClust[FED_NSYM];        // FED symbol index -> cluster id (built by IG_Init)
long g_igCoolUntil[IG_NCLUST];   // cluster blocked until this server time (0 = free)
long g_igLastCheck = 0;          // last full check (InpIdeaCheckSec throttle)
bool g_igViolLatch[IG_NCLUST];   // edge trigger for the VIOLATION line
int  g_igKills = 0;              // cluster kills this session
int  g_igViol  = 0;              // -1% violation entries this session

//--- restart-proof cooldown stamp name, namespaced by magic base
string IG_GvName(const int c)
  {
   return StringFormat("FMA3_IG_%I64d_%d",InpMagicBase,c);
  }

//--- canonical name -> cluster id (-1 = unmapped)
int IG_ClusterOfCanon(const string canon)
  {
   for(int i=0;i<FED_NSYM;i++) if(g_igMapSym[i]==canon) return g_igMapClust[i];
   return -1;
  }

//--- init: build the FED-index -> cluster map + carry restart cooldowns.
//--- Called from OnInit AFTER FED_InitUniverse. OFF: single branch, no state.
void IG_Init()
  {
   if(InpIdeaStopPct<=0.0) return;                      // OFF: single branch, no state
   for(int k=0;k<FED_NSYM;k++)
     {
      g_igClust[k]=IG_ClusterOfCanon(g_fedCanon[k]);
      if(g_igClust[k]<0)
        {
         RefuseLatch("IdeaGuard: canonical symbol '"+g_fedCanon[k]+
                     "' has no cluster mapping - fix g_igMapSym before arming the idea breaker");
         return;
        }
     }
   long now=(long)TimeCurrent();
   int carried=0;
   for(int c=0;c<IG_NCLUST;c++)
     {
      g_igCoolUntil[c]=0;
      g_igViolLatch[c]=false;
      string gv=IG_GvName(c);
      if(!GlobalVariableCheck(gv)) continue;
      long until=(long)GlobalVariableGet(gv)+(long)InpIdeaCooldownMin*60+(long)InpIdeaCheckSec;
      if(until>now)
        {
         g_igCoolUntil[c]=until;
         carried++;
         PrintFormat("FED IDEA_COOLDOWN carried over restart: cluster %s blocked until %s",
                     g_igClustName[c],
                     TimeToString((datetime)until,TIME_DATE|TIME_MINUTES|TIME_SECONDS));
        }
      else
         GlobalVariableDel(gv);                          // expired stamp: clean up
     }
   PrintFormat("FMA3 NATIVE idea-breaker ARMED: stop=%.2f%% of balance (VIOLATION line at "
               "1.00%%), cooldown=%d min, check<=%d s, clusters=%d, carried cooldowns=%d",
               InpIdeaStopPct,InpIdeaCooldownMin,InpIdeaCheckSec,IG_NCLUST,carried);
  }

//--- is leg k's cluster cooldown-blocked? (FED_Reconcile pass-1 hook;
//--- the caller guards with InpIdeaStopPct>0 so g_igClust is always built)
bool IG_Blocked(const int k)
  {
   int c=g_igClust[k];
   if(c<0) return false;                                 // defensive: table not built
   return (g_igCoolUntil[c] > (long)TimeCurrent());
  }

//--- flatten every position of ONE cluster (our magics base+1..base+NSYM).
//--- Foreign magics untouched; closed markets retried next pass (like
//--- FED_GuardFlattenAll; FED_Reconcile's cooldown-zeroed targets also close).
//--- Returns the number of positions successfully closed THIS call so the
//--- caller can re-anchor the cooldown on late (session-gapped) fills.
int IG_FlattenCluster(const int c)
  {
   int n=0;
   int tot=PositionsTotal();
   for(int i=tot-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      if(magic<=InpMagicBase || magic>InpMagicBase+FED_NSYM) continue;   // ours only
      if(g_igClust[(int)(magic-InpMagicBase-1)]!=c) continue;            // this cluster only
      string sym=PositionGetString(POSITION_SYMBOL);
      if(!FED_MarketOpen(sym)) continue;                 // session gap - retry next pass
      trade.SetExpertMagicNumber(magic);
      trade.SetTypeFillingBySymbol(sym);
      if(trade.PositionClose(tk) || trade.ResultRetcode()==TRADE_RETCODE_DONE)
         n++;
      else
         FED_LogReject("IdeaFlatten",sym,0.0,trade.ResultRetcode(),trade.ResultComment());
     }
   return n;
  }

//--- stamp/extend a cluster's cooldown from `now` ("1 hour from the CLOSE"):
//--- +InpIdeaCheckSec slack so a close fill stamped seconds after `now` can
//--- never still sit inside the half-open trailing window at re-entry.
void IG_StampCooldown(const int c,const long now)
  {
   g_igCoolUntil[c]=now+(long)InpIdeaCooldownMin*60+(long)InpIdeaCheckSec;
   GlobalVariableSet(IG_GvName(c),(double)now);
  }

//--- the per-pump idea check. Called from Pump() AFTER the FED_GuardianPass
//--- gate, BEFORE FED_Reconcile; the caller guards with InpIdeaStopPct>0 &&
//--- g_canTrade and passes `synced`. UNSYNCED (warm-restart catch-up): only
//--- cooldown MAINTENANCE runs - expiry lift + flatten retry of already-
//--- decided kills - never a new metering/kill decision (divergence 6).
void IG_Pass(const bool synced)
  {
   long now=(long)TimeCurrent();
   if(now-g_igLastCheck<(long)InpIdeaCheckSec) return;   // bound the history scans
   g_igLastCheck=now;

   // ---- cooldown maintenance (runs even unsynced) ----
   for(int c=0;c<IG_NCLUST;c++)
     {
      if(g_igCoolUntil[c]>0 && g_igCoolUntil[c]<=now)
        {
         // lift an expired cooldown (lazy; clears the restart stamp too)
         g_igCoolUntil[c]=0;
         string gv=IG_GvName(c);
         if(GlobalVariableCheck(gv)) GlobalVariableDel(gv);
         PrintFormat("FED IDEA_RESUME: cluster %s cooldown expired, trading re-enabled.",
                     g_igClustName[c]);
        }
      else if(g_igCoolUntil[c]>now)
        {
         // residual legs (session gaps): retry, and RE-ANCHOR the cooldown on
         // any late fill - "1 hour from the CLOSE" (divergence 5) - so the
         // kill's own realized loss ages out of the window before re-entry.
         if(IG_FlattenCluster(c)>0)
            IG_StampCooldown(c,now);
        }
     }
   if(!synced) return;                                  // catch-up: no new decisions

   double bal=AccountInfoDouble(ACCOUNT_BALANCE);
   if(bal<=0.0) return;

   double floatC[IG_NCLUST];
   double realC[IG_NCLUST];
   for(int c=0;c<IG_NCLUST;c++){ floatC[c]=0.0; realC[c]=0.0; }

   // ---- FLOAT_C: worst-mark unrealized per OPEN position, per cluster
   // (swap EXCLUDED - divergence 4: the validated meter books swap to
   // balance, never the cluster meter)
   int tot=PositionsTotal();
   for(int i=0;i<tot;i++)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      if(magic<=InpMagicBase || magic>InpMagicBase+FED_NSYM) continue;   // ours only
      int c=g_igClust[(int)(magic-InpMagicBase-1)];
      if(c<0) continue;                                  // defensive: table not built
      string sym=PositionGetString(POSITION_SYMBOL);
      long   type=PositionGetInteger(POSITION_TYPE);
      double vol =PositionGetDouble(POSITION_VOLUME);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double worst=(type==POSITION_TYPE_BUY)?iLow(sym,PERIOD_M1,0):iHigh(sym,PERIOD_M1,0);
      double wp=0.0;
      ENUM_ORDER_TYPE ot=(type==POSITION_TYPE_BUY)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
      if(worst>0.0 && OrderCalcProfit(ot,sym,vol,entry,worst,wp)) floatC[c] += wp;
      else                                                        floatC[c] += PositionGetDouble(POSITION_PROFIT); // fallback: current mark
     }

   // ---- REAL1H_C: realized (profit+commission, swap EXCLUDED) of
   // DEAL_ENTRY_OUT deals in the HALF-OPEN trailing window (now-3600, now],
   // recomputed from history (restart-proof for free)
   if(HistorySelect((datetime)(now-3600),(datetime)(now+60)))
     {
      int nd=HistoryDealsTotal();
      for(int i=0;i<nd;i++)
        {
         ulong dt=HistoryDealGetTicket(i); if(dt==0) continue;
         long magic=HistoryDealGetInteger(dt,DEAL_MAGIC);
         if(magic<=InpMagicBase || magic>InpMagicBase+FED_NSYM) continue; // ours only
         if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(dt,DEAL_ENTRY)!=DEAL_ENTRY_OUT) continue;
         if((long)HistoryDealGetInteger(dt,DEAL_TIME)<=now-3600) continue; // half-open (model parity)
         int c=g_igClust[(int)(magic-InpMagicBase-1)];
         if(c<0) continue;                               // defensive: table not built
         realC[c] += HistoryDealGetDouble(dt,DEAL_PROFIT)
                    +HistoryDealGetDouble(dt,DEAL_COMMISSION);
        }
     }
   // else: FLOAT-only pass (header divergence 3) - never stall the retry loop

   double stopLvl=-InpIdeaStopPct/100.0*bal;
   double violLvl=-0.01*bal;
   for(int c=0;c<IG_NCLUST;c++)
     {
      double dd=floatC[c]+realC[c];

      // the FTMO -1% rule line itself (edge-triggered; cockpit greps this)
      if(dd<=violLvl)
        {
         if(!g_igViolLatch[c])
           {
            g_igViolLatch[c]=true; g_igViol++;
            PrintFormat("FED IDEA_VIOLATION: cluster %s idea-dd %.2f <= -1.00%% of balance "
                        "(%.2f) - the per-idea rule line was reached (the %.2f%% kill should "
                        "have pre-empted this). (violation #%d)",
                        g_igClustName[c],dd,violLvl,InpIdeaStopPct,g_igViol);
           }
        }
      else
         g_igViolLatch[c]=false;

      if(g_igCoolUntil[c]>now) continue;                 // cooling: maintenance above owns it

      if(dd<=stopLvl)
        {
         g_igKills++;
         IG_StampCooldown(c,now);                        // restart-proof stamp = kill time
         PrintFormat("FED IDEA_STOP: cluster %s idea-dd %.2f (float %.2f + real1h %.2f) <= "
                     "%.2f (-%.2f%% of balance %.2f) - flattening the cluster and blocking "
                     "its targets for %d min. (kill #%d)",
                     g_igClustName[c],dd,floatC[c],realC[c],stopLvl,InpIdeaStopPct,bal,
                     InpIdeaCooldownMin,g_igKills);
         IG_FlattenCluster(c);
        }
     }
  }
//+------------------------------------------------------------------+
