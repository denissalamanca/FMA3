//+------------------------------------------------------------------+
//| FMA3/V34Exec.mqh - F3_* v3.4 order loop (SPEC par.5.3)            |
//|                                                                    |
//| Per target leg: frac x InpV34Mult x E_v34 -> lots via the VERBATIM |
//| v7 primitives (DesiredLots incl. margin clamp + volume-limit       |
//| guard, RoundLots, SendSplit, CloseAll, ReducePos, HeldNet,         |
//| MarketOpen, OpenDir) - shared library, ZERO duplicated order       |
//| plumbing. Diff-vs-held with the same 0.25 relative band            |
//| (InpRebalBand), mirroring ExecSleeve's reconcile shape.            |
//|                                                                    |
//| Cadence: target swaps on each new H1 boundary of the clock chart   |
//| (replay cursor / live read); the reconcile pass runs on the swap,  |
//| at least once per server hour (forced exits), and every M1 bar     |
//| while any leg is deferred on a closed market.                      |
//| MUST NOT touch any v7 g_* global (TRANSPLANT_V7.md par.4).         |
//+------------------------------------------------------------------+

datetime g_f3LastH1      = 0;
int      g_f3LastPassHr  = -1;    // server hour of the last reconcile pass
bool     g_f3PendExec    = false; // a leg was deferred (closed market) - retry each bar
bool     g_f3LegDeferred[F3_N_SLEEVE34*F3_MAX_SYM];

//====================================================================
// [F3 CHANGE 2+3] EXEC REJECT-BACKOFF + ACCOUNT-AGGREGATE VOLUME CLAMP
// Shared by ExecSleeve (v7 book, marked seam lines in V7Core.mqh - the
// .mq5 carries the prototypes) and F3_ExecPass below.
//
// CHANGE 2: a per-leg hold (keyed magic+symbol) remembers a desired size
// the broker just rejected (aggregate volume cap / "no money") so the
// reconcile loop stops re-sending the IDENTICAL failing order every M1
// bar (observed 49,916 XAUUSD volume rejects + 5,817 margin rejects).
// The hold applies ONLY to same-direction adds/opens - closes, reduces
// and reversal-closes are NEVER suppressed. It clears when desired moves
// >= 1 VOLUME_STEP, flips sign, goes flat (0), or the held position
// changes externally.
//
// CHANGE 3: before any same-direction ADD/OPEN the wanted delta is
// clamped to the remaining ACCOUNT-AGGREGATE per-direction headroom
// under SYMBOL_VOLUME_LIMIT, summed across ALL this EA's magics (v7
// base+1..+N_SLEEVE and v3.4 base34+1..+F3_N_SLEEVE34) - the per-magic
// clamp inside DesiredLots cannot see the sibling book on the same
// broker symbol. An unsendable clamped delta (< VOLUME_MIN) holds the
// leg via the same mechanism (one line, no spin).
//====================================================================
#define F3_HOLD_MAX 64   // distinct (magic,symbol) legs ever held (v7 12 + live v34 legs)

int    g_f3HoldN = 0;
long   g_f3HoldMagic[F3_HOLD_MAX];
string g_f3HoldSym[F3_HOLD_MAX];
bool   g_f3HoldOn[F3_HOLD_MAX];
double g_f3HoldDes[F3_HOLD_MAX];    // the signed desired that failed
double g_f3HoldHeld[F3_HOLD_MAX];   // held at the failure (external-change detection)

double F3_StepOf(string sym)
  {
   double st=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   return (st>0)?st:0.01;
  }

int F3_HoldFind(const string sym,const long magic)
  {
   for(int i=0;i<g_f3HoldN;i++)
      if(g_f3HoldMagic[i]==magic && g_f3HoldSym[i]==sym) return i;
   return -1;
  }

//--- arm the hold: ONE Print line per episode.  why = "reject" | "vol-cap"
void F3_HoldSet(string sym,long magic,double desired,double held,string why)
  {
   int i=F3_HoldFind(sym,magic);
   if(i<0)
     {
      if(g_f3HoldN>=F3_HOLD_MAX) return;   // table full: legacy retry-each-bar (safe fallback)
      i=g_f3HoldN; g_f3HoldN++;
      g_f3HoldMagic[i]=magic; g_f3HoldSym[i]=sym; g_f3HoldOn[i]=false;
     }
   if(g_f3HoldOn[i] && MathAbs(g_f3HoldDes[i]-desired)<F3_StepOf(sym)*0.5) return;  // already armed+logged
   g_f3HoldOn[i]=true; g_f3HoldDes[i]=desired; g_f3HoldHeld[i]=held;
   Print("F3 EXEC HOLD: ",sym," magic ",magic," desired ",DoubleToString(desired,2),
         " held ",DoubleToString(held,2)," (",why,")");
  }

//--- drop the hold (flat target)
void F3_HoldClear(string sym,long magic)
  {
   int i=F3_HoldFind(sym,magic);
   if(i>=0) g_f3HoldOn[i]=false;
  }

//--- true = this same-direction add/open IS the known-failing order: skip it.
//--- Self-clears when desired moved >= 1 VOLUME_STEP (quantized sizes: not
//--- within 0.5*step <=> >= 1 step away), flipped sign, or the held position
//--- changed externally. NEVER called for closes/reduces.
bool F3_HoldSkip(const string sym,const long magic,const double desired,const double held)
  {
   int i=F3_HoldFind(sym,magic);
   if(i<0 || !g_f3HoldOn[i]) return false;
   double step=F3_StepOf(sym);
   if(desired*g_f3HoldDes[i]>0                        // same direction
      && MathAbs(desired-g_f3HoldDes[i])<step*0.5     // same failed size
      && MathAbs(held-g_f3HoldHeld[i])<step*0.5)      // no external position change
      return true;
   g_f3HoldOn[i]=false;                               // moved/flipped/external -> re-attempt
   return false;
  }

//--- same-direction volume already held on this BROKER symbol across ALL of
//--- this EA's magics (both books). Foreign magics excluded.
double F3_AggSameDir(const string sym,const int dir)
  {
   double v=0.0; int tot=PositionsTotal();
   for(int i=0;i<tot;i++)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
      long magic=PositionGetInteger(POSITION_MAGIC);
      bool ours=(magic>InpMagicBase    && magic<=InpMagicBase+N_SLEEVE) ||
                (magic>InpMagicBaseV34 && magic<=InpMagicBaseV34+F3_N_SLEEVE34);
      if(!ours) continue;
      long pt=PositionGetInteger(POSITION_TYPE);
      if((dir>0 && pt==POSITION_TYPE_BUY) || (dir<0 && pt==POSITION_TYPE_SELL))
         v+=PositionGetDouble(POSITION_VOLUME);
     }
   return v;
  }

//--- guarded same-direction ADD/OPEN of dv lots toward `desired` (signed).
//--- Consults the reject hold (skip the known-failing order), clamps dv to
//--- the aggregate volume-limit headroom, holds the leg (no spin) when the
//--- clamped dv is unsendable. Returns false when held (nothing sent).
bool F3_SendAdd(string sym,long magic,int dir,double dv,double desired,double held)
  {
   if(F3_HoldSkip(sym,magic,desired,held)) return false;       // known-failing order
   double vlim=SymbolInfoDouble(sym,SYMBOL_VOLUME_LIMIT);
   if(vlim>0)
     {
      double capAdd=MathMax(0.0,vlim-F3_AggSameDir(sym,dir));  // [F3 CHANGE 3]
      if(dv>capAdd) dv=capAdd;
     }
   dv=RoundLots(sym,dv);                                       // 0 when < VOLUME_MIN
   if(dv<=0)
     {
      F3_HoldSet(sym,magic,desired,held,"vol-cap");            // one line, no spin
      return false;
     }
   OpenDir(sym,dir*dv);
   return true;
  }

//--- [F3 CHANGE 4] once-per-symbol-per-session guard behind DesiredLots'
//--- px/eurq/contract early-return (marked seam line in V7Core.mqh). SOLUSD
//--- legitimately has no data before 2022-03-14, so this must WARN once,
//--- never abort, never spam (table full -> silent, like before).
#define F3_SKIP_MAX 32
string g_f3SizeSkipSym[F3_SKIP_MAX];
int    g_f3SizeSkipN = 0;
void F3_SizeSkipWarn(string sym)
  {
   for(int i=0;i<g_f3SizeSkipN;i++) if(g_f3SizeSkipSym[i]==sym) return;
   if(g_f3SizeSkipN>=F3_SKIP_MAX) return;
   g_f3SizeSkipSym[g_f3SizeSkipN]=sym; g_f3SizeSkipN++;
   Print("F3 SIZE SKIP: ",sym," px/eurq/contract unavailable");
  }

//--- entry-suppression window [no_entry_after_hour, flat_at_server_hour) in
//--- server hours, wrap-safe. Shipped schedules: seasonal [5,6), intraday [20,21).
bool F3_InNoEntryWindow(const int s,const int hour)
  {
   int ne=g_f3NoEntHour[s], fl=g_f3FlatHour[s];
   if(ne<0) return false;
   if(fl<0) return (hour>=ne);
   if(ne<fl) return (hour>=ne && hour<fl);
   return (hour>=ne || hour<fl);            // window wraps midnight
  }

//--- [F3 MARGIN GOVERNOR] blind-spot warn: once per symbol when OrderCalcMargin fails
//--- for a leg the governor is projecting (that leg is then INVISIBLE to the aggregate
//--- margin sum but still sizes/trades via DesiredLots, uncapped by the per-leg clamp).
#define F3_MLBLIND_MAX 32
string g_f3MlBlindSym[F3_MLBLIND_MAX];
int    g_f3MlBlindN = 0;
void F3_MlBlindWarn(string sym)
  {
   for(int i=0;i<g_f3MlBlindN;i++) if(g_f3MlBlindSym[i]==sym) return;
   if(g_f3MlBlindN>=F3_MLBLIND_MAX) return;
   g_f3MlBlindSym[g_f3MlBlindN]=sym; g_f3MlBlindN++;
   Print("F3 ML GOVERNOR BLIND: ",sym," OrderCalcMargin failed -> excluded from margin projection");
  }

//--- [F3 MARGIN GOVERNOR] account-aggregate free-margin governor: the MISSING counterpart
//--- to the per-leg InpMarginCap clamp (V7Core.mqh:526) and the VOLUME-only Task-16 clamp.
//--- ~12 per-leg-legal margins can STACK past 100% of equity (the May-2022 ML 90.29% event).
//--- Account-level analogue of account_engine_1m.py:137-140: PROJECT the full desired book's
//--- used-margin across ALL legs (v7 + v34); if that would drop projected ML below
//--- InpMinMarginLevel, derive ONE proportional haircut g_f3MlShrink = cap/margin_sum applied
//--- UNIFORMLY inside DesiredLots. Runs ONCE per bar at OnTick top, BEFORE all three sites.
//--- INERT AT DEFAULT (InpMinMarginLevel<=0 -> returns with g_f3MlShrink==1.0, no extra
//--- calls/prints -> frozen book bit-identical). Only ever DE-RISKS; never blocks close/reduce.
//--- Projection uses MAX(|desired|,|held|)*mpl so a leg that cannot reconcile this bar still
//--- counts its HELD margin.
void F3_MlGovernorPrepass(const int hour,const int dow)
  {
   if(InpMinMarginLevel<=0.0){ g_f3MlShrink=1.0; return; }   // hard inert at default
   g_f3MlShrink=1.0;                                         // size UN-shrunk during projection

   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq<=0.0){ g_f3MlShrink=1.0; return; }                  // blown/degenerate -> Guardian/stop-out

   double margin_sum=0.0;

   // --- v7 book: every enabled sleeve, sized off its VBalance (the Site-B basis).
   for(int n=0;n<N_SLEEVE;n++)
     {
      if(W[n]<=0.0) continue;
      double dl=DesiredLots(g_slSym[n],CurrentTarget(n,hour,dow),VBalance(n));
      if(dl==0.0) continue;                                  // flat target -> leg CLOSES, no margin
      int    dir=(dl>0)?1:-1;
      double px=(dir>0)?SymbolInfoDouble(g_slSym[n],SYMBOL_ASK)
                       :SymbolInfoDouble(g_slSym[n],SYMBOL_BID);
      ENUM_ORDER_TYPE ot=(dir>0)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
      double mpl=0.0;
      if(OrderCalcMargin(ot,g_slSym[n],1.0,px,mpl) && mpl>0)
        {
         double held=HeldNet(g_slSym[n],InpMagicBase+n+1);
         margin_sum+=MathMax(MathAbs(dl),MathAbs(held))*mpl; // conservative: worst of desired/held
        }
      else F3_MlBlindWarn(g_slSym[n]);
     }

   // --- v34 book: every seen (sleeve,sym) leg, sized off the v34 book equity (mirrors F3_ExecPass).
   if(g_f3V34On)
     {
      double e34=F3_V34BookEquity();
      for(int s=0;s<F3_N_SLEEVE34;s++)
         for(int j=0;j<g_f3NSym;j++)
           {
            int k=s*F3_MAX_SYM+j;
            if(!g_f3LegSeen[k]) continue;
            double m=g_f3Tgt[k]*InpV34Mult;
            double dl=DesiredLots(g_f3Sym[j],m,e34);
            if(dl==0.0) continue;
            int    dir=(dl>0)?1:-1;
            double px=(dir>0)?SymbolInfoDouble(g_f3Sym[j],SYMBOL_ASK)
                             :SymbolInfoDouble(g_f3Sym[j],SYMBOL_BID);
            ENUM_ORDER_TYPE ot=(dir>0)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
            double mpl=0.0;
            if(OrderCalcMargin(ot,g_f3Sym[j],1.0,px,mpl) && mpl>0)
              {
               double held=HeldNet(g_f3Sym[j],F3_V34Magic(s));
               margin_sum+=MathMax(MathAbs(dl),MathAbs(held))*mpl;
              }
            else F3_MlBlindWarn(g_f3Sym[j]);
           }
     }

   // ML = equity/used_margin*100. To hold ML >= F (%), require used_margin <= equity*100/F.
   // ONE global proportional shrink, guarded so a non-positive cap/margin_sum can never store
   // a bad factor, and clamped to [0,1].
   double cap = eq*100.0/InpMinMarginLevel;
   double sh  = (cap>0.0 && margin_sum>cap) ? cap/margin_sum : 1.0;
   g_f3MlShrink = MathMax(0.0,MathMin(1.0,sh));

   // HARD floor for the v34 book: F3_ExecPass reconciles v34 at most HOURLY. When the governor
   // binds mid-hour, force THIS bar's v34 pass so v34 legs de-risk DOWN immediately.
   if(g_f3MlShrink<1.0 && g_f3V34On) g_f3TgtDirty=true;
  }

//--- one reconcile pass over every (sleeve,symbol) ever targeted
void F3_ExecPass(const int srvHour)
  {
   double e34=F3_V34BookEquity();
   bool anyDefer=false;
   for(int s=0;s<F3_N_SLEEVE34;s++)
     {
      long magic=F3_V34Magic(s);
      bool forcedFlat=(g_f3FlatHour[s]>=0 && srvHour==g_f3FlatHour[s]);
      bool noEntry=F3_InNoEntryWindow(s,srvHour);
      bool hold=(g_f3Stale && !g_f3Replay);            // live HOLD: no target changes
      for(int j=0;j<g_f3NSym;j++)
        {
         int k=s*F3_MAX_SYM+j;
         if(!g_f3LegSeen[k]) continue;
         string sym=g_f3Sym[j];
         if(hold && !forcedFlat) continue;             // keep positions untouched
         double m=g_f3Tgt[k]*InpV34Mult;
         double desired=forcedFlat?0.0:DesiredLots(sym,m,e34);
         double held=HeldNet(sym,magic);
         int sgnT=(desired>0)?1:((desired<0)?-1:0);
         int sgnP=(held>0)?1:((held<0)?-1:0);
         if(sgnT==0) F3_HoldClear(sym,magic);  // [F3 CHANGE 2] flat target clears any hold
         bool wantChange=false;
         if(sgnT==0)         wantChange=(sgnP!=0);
         else if(sgnT!=sgnP) wantChange=true;
         else
           {
            double drift=MathAbs(MathAbs(desired)-MathAbs(held))/MathAbs(held);
            wantChange=(drift>InpRebalBand);
            // [F3 MARGIN GOVERNOR] HARD floor: force a REDUCE toward the shrunk target
            // inside the dead-band when binding (de-risk only; routes to ReducePos). Inert at 1.0.
            if(g_f3MlShrink<1.0 && MathAbs(desired)<MathAbs(held)) wantChange=true;
           }
         if(!wantChange){ g_f3LegDeferred[k]=false; continue; }
         // no_entry window: suppress opens/adds, allow reductions/closes;
         // a reversal degrades to close-only (risk-reducing).
         if(noEntry && !forcedFlat)
           {
            if(sgnP==0) continue;                                     // no new opens
            if(sgnT==sgnP && MathAbs(desired)>MathAbs(held)) continue; // no adds
            if(sgnT!=0 && sgnT!=sgnP){ desired=0.0; sgnT=0; }          // close only
           }
         if(!MarketOpen(sym))
           {
            if(!g_f3LegDeferred[k])
              {
               F3_LogRow("V34_"+g_f3SlvName[s],"CLOSED",m,desired,held,0);
               g_f3LegDeferred[k]=true;
              }
            anyDefer=true;
            continue;
           }
         g_f3LegDeferred[k]=false;
         trade.SetExpertMagicNumber(magic);
         trade.SetTypeFillingBySymbol(sym);
         // [F3 CHANGE 2+3] same-direction adds/opens go through F3_SendAdd above
         // (reject-backoff hold + account-aggregate volume clamp).
         // Closes/reduces/forced flats/reversal-closes are NEVER suppressed.
         if(sgnT==0)                              CloseAll(sym,magic);
         else if(sgnP==0){ if(!F3_SendAdd(sym,magic,sgnT,MathAbs(desired),desired,held)) continue; }
         else if(sgnT!=sgnP)
           {
            CloseAll(sym,magic);                                     // risk-reducing close always runs
            F3_SendAdd(sym,magic,sgnT,MathAbs(desired),desired,0.0); // reopen clamped/held like any open
           }
         else
           {
            double dv=MathAbs(desired)-MathAbs(held);
            if(dv>0){ if(!F3_SendAdd(sym,magic,sgnT,dv,desired,held)) continue; }
            else     ReducePos(sym,magic,-dv,(sgnP>0)?POSITION_TYPE_BUY:POSITION_TYPE_SELL);
           }
         double after=HeldNet(sym,magic);
         double step=F3_StepOf(sym);
         if(MathAbs(after-held)<step*0.5)
           {
            // [F3 CHANGE 2] change wanted, nothing moved -> rejected/no-op send.
            // Arm the hold ONLY for same-direction adds/opens (closes retry).
            if(sgnT!=0 && (sgnP==0 || (sgnT==sgnP && MathAbs(desired)>MathAbs(held))))
               F3_HoldSet(sym,magic,desired,held,"reject");
            continue;
           }
         string ev = forcedFlat                     ? "FEXIT"  :
                     (MathAbs(after)<1e-9)          ? "CLOSE"  :
                     (MathAbs(held)<1e-9)           ? "OPEN"   :
                     (after*held<0)                 ? "FLIP"   :
                     (MathAbs(after)>MathAbs(held)) ? "ADD"    : "REDUCE";
         F3_LogRow("V34_"+g_f3SlvName[s],ev,m,desired,held,after);
        }
     }
   g_f3TgtDirty=false;
   g_f3PendExec=anyDefer;
  }

//--- the per-bar v3.4 pass ([F3 SEAM V] call site, AFTER the v7 sleeve loop)
void F3_V34Pass(const datetime bt)
  {
   F3_UpdateRealized34();
   if(g_f3FedActive) F3_BooksDaily(bt);

   // ---- source refresh ----
   if(g_f3Replay)
     {
      datetime h1=iTime(_Symbol,PERIOD_H1,0);
      if(h1!=g_f3LastH1)
        {
         // apply the rows stamped with the JUST-CLOSED hour (1-bar causal lag,
         // matching the record engine + the FMA2 replay semantics)
         if(g_f3LastH1!=0)
           {
            datetime closed=iTime(_Symbol,PERIOD_H1,1);
            if(closed>0) F3_ReplayApplyHour((long)closed);
           }
         g_f3LastH1=h1;
        }
     }
   else F3_LiveRefresh();

   // ---- reconcile cadence ----
   MqlDateTime st;
   TimeToStruct(TimeCurrent(),st);          // SERVER clock (forced exits are server-hour)
   bool hourTick=(st.hour!=g_f3LastPassHr);
   if(g_f3TgtDirty || g_f3PendExec || hourTick)
     {
      g_f3LastPassHr=st.hour;
      F3_ExecPass(st.hour);
     }
  }
