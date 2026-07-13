//+------------------------------------------------------------------+
//| FMA3/V7Core.mqh - the VERBATIM v7 transplant (FableFederation_V1) |
//|                                                                    |
//| Source of truth: NSF5 mt5/ea/FableMultiAsset1_V7.mq5 lines 117-1089|
//| (PROVEN: IC real-tick runs 53/54, 2026-07-10). Assembled           |
//| MECHANICALLY by FMA3 scratch assemble_fed.py - the ONLY deviations |
//| from the source are the TRANSPLANT_V7.md allowlist:                |
//|   - 4 runtime file-name renames (STATE/HB/REJ/SKIP -> fma3_fed_*)  |
//|   - SEAM 1 in QuarterRebalance (virtual-book preEquity, G1-gated)  |
//|   - [F3 CHANGE 2..5] exec hardening (2026-07-10): reject-backoff   |
//|     hold + aggregate volume clamp (F3_SendAdd seam), SIZE-SKIP     |
//|     warn, InpSizingBase choke point - inert at defaults (G1).      |
//| ANY other diff vs the v7 source is a defect against gate G1.       |
//| Inputs live in the main .mq5 (MQL5 requires program-scope inputs). |
//+------------------------------------------------------------------+
//====================================================================
// CONSTANTS — sleeve layout
//====================================================================
#define N_SLEEVE 12
// sleeve indices — 0..7 are the V4 core slots (verbatim), 8..11 are V5 additions
#define SL_XAU   0   // BOOK_XAU  (XAUUSD)
#define SL_US5   1   // BOOK_US5  (USA500/USTEC)
#define SL_JPY   2   // S5_JPY    (USDJPY)  jpy_smart
#define SL_ETH   3   // S1_ETH    (ETHUSD)
#define SL_EG    4   // ZC_EG     (EURGBP)
#define SL_AU    5   // ZC_AU     (AUDUSD)   — disabled in core5/V5
#define SL_FEU   6   // FXT_EU    (EURUSD)   — disabled
#define SL_FUJ   7   // FXT_UJ    (USDJPY)   — disabled
#define SL_S6UJ  8   // S6 leg: LONG  USDJPY (opex week)
#define SL_S6AU  9   // S6 leg: SHORT AUDUSD (opex week)
#define SL_S6NZ  10  // S6 leg: SHORT NZDUSD (opex week)
#define SL_BTC   11  // S1_BTC: LONG BTCUSD (financing-hurdle momentum)  [V6: was MAG_XAU gold]
#define IS_DIVERSIFIER(n) ((n)>=SL_S6UJ)

// weights (V4 core-8 full float64 from PORTFOLIO_V33; V5 legs 0 -> set in OnInit)
double W[N_SLEEVE] = {
   0.31611005312960805, // XAU
   0.1843975309922714,  // US5
   0.1317125221373367,  // JPY
   0.1317125221373367,  // ETH
   0.03980645113483954, // EG
   0.01990322556741977, // AU
   0.08817884745059391, // FEU
   0.08817884745059391, // FUJ
   0.0, 0.0, 0.0, 0.0   // S6UJ, S6AU, S6NZ, MAG  (assigned in OnInit)
};

string g_slSym[N_SLEEVE];   // traded symbol per sleeve
string g_slName[N_SLEEVE];  // label for logs
double g_slSign[N_SLEEVE];  // +1/-1 direction for the S6 legs (0 = use computed sign)

// daily-series ids
#define N_SER 10
#define SID_XAU  0
#define SID_US5  1
#define SID_UJ   2
#define SID_ETH  3
#define SID_EG   4   // EURGBP standard (unused for signal, kept for symmetry)
#define SID_AU   5
#define SID_EU   6
#define SID_EG20 7   // EURGBP pre-20:00 series (used by eurgbp_zens)
#define SID_NZD  8   // NZDUSD (S6 leg 3)
#define SID_BTC  9   // BTCUSD (S1_BTC hurdle-momentum sleeve)

//====================================================================
// GLOBALS
//====================================================================
CTrade   trade;

struct Series { double mid[]; datetime day[]; datetime lastDay; };
Series   g_ser[N_SER];
string   g_serSym[N_SER];
bool     g_serPre20[N_SER];

// sub-account ledger
double   g_seed[N_SLEEVE];      // sub-account seed at current quarter start
double   g_realized[N_SLEEVE];  // realized P&L attributed since quarter start
datetime g_quarterStart = 0;
int      g_dealCursor   = 0;    // history-deals already folded into g_realized

// cached daily / stamped signal coefficients (recomputed at their stamp times)
double   g_donchTgt = 0.0;      // XAU: clip(m50,±6)+clip(m100,±6)
double   g_nightLev = 0.0;      // XAU night leverage
double   g_regTgt   = 0.0;      // US500 regime target
double   g_monLev   = 0.0;      // US500 Monday leverage
double   g_jpyM     = 0.0;      // S5_JPY multiple
double   g_ethM     = 0.0;      // S1_ETH multiple
double   g_fxtEuM   = 0.0;      // FXT_EU multiple
double   g_fxtUjM   = 0.0;      // FXT_UJ multiple
double   g_egM      = 0.0;      // ZC_EG multiple (stamp 20:00)
double   g_auM      = 0.0;      // ZC_AU multiple (stamp 07:05)
// --- V5 diversifier daily multiples (signed magnitude; opex/clock gate applied in CurrentTarget) ---
double   g_s6uj     = 0.0;      // S6 LONG  USDJPY  = +clip(vt*R/av,0,cap)
double   g_s6au     = 0.0;      // S6 SHORT AUDUSD  = -clip(vt*R/av,0,cap)
double   g_s6nz     = 0.0;      // S6 SHORT NZDUSD  = -clip(vt*R/av,0,cap)
double   g_btcM     = 0.0;      // S1_BTC LONG BTCUSD = clip(sig*vt*R/av,0,cap), daily-constant

datetime g_curDay   = 0;        // current UTC day being processed
datetime g_lastBar  = 0;
bool     g_did20    = false;    // EURGBP recomputed today (at/after 20:00)
bool     g_did0705  = false;    // AUDUSD recomputed today (at/after 07:05)
bool     g_pendResplit = false; // V7: daily band/harvest re-split check pending (defer to all-markets-open)
long     g_nSplit=0, g_nReject=0, g_nClosed=0;  // 6.01 health counters (written at OnDeinit)
bool     g_deferred[N_SLEEVE];  // reopen-window defer already logged this episode
int      g_logh     = INVALID_HANDLE;

// --- restart-hardening state (persisted across terminal restarts) ---
int      g_lastRebalQ = -1;     // quarter-id of the last rebalance
datetime g_lastHB     = 0;      // last heartbeat write time
bool     g_live       = true;   // false in Strategy Tester -> no persistence/heartbeat, fresh seed
bool     g_skipActive = false;  // P1: a live disconnect/insufficient-history skip episode is active (logged once/episode)
#define  STATE_FILE  "fma3_fed_state.csv"
#define  HB_FILE     "fma3_fed_heartbeat.csv"
#define  HB_PERIOD   900        // heartbeat cadence (seconds)
#define  REJ_FILE    "fma3_fed_rejects.csv"   // P2: order-reject retcode/comment log (live-only)
#define  SKIP_FILE   "fma3_fed_skips.csv"     // P1: disconnect / insufficient-history skip log (live-only)

//--- embedded policy rates (engine/costs.py POLICY_RATES, USD & JPY) ---
string   USD_D[] = {"2019.11.01","2020.03.03","2020.03.15","2022.03.17","2022.05.05",
                    "2022.06.16","2022.07.28","2022.09.22","2022.11.03","2022.12.15",
                    "2023.02.02","2023.03.23","2023.05.04","2023.07.27","2024.09.19",
                    "2024.11.08","2024.12.19","2025.09.18","2025.10.30","2025.12.11"};
double   USD_R[] = {1.625,1.125,0.125,0.375,0.875,1.625,2.375,3.125,3.875,4.375,
                    4.625,4.875,5.125,5.375,4.875,4.625,4.375,4.125,3.875,3.625};
string   JPY_D[] = {"2019.11.01","2024.03.19","2024.07.31","2025.01.24"};
double   JPY_R[] = {-0.10,0.10,0.25,0.50};

//====================================================================
// TIME HELPERS (server -> UTC).  Custom .duka symbols are UTC-stamped.
//====================================================================
datetime ToUtc(datetime server_t){ return server_t - (TimeCurrent() - TimeGMT()); }
datetime UtcDayStart(datetime server_t){ datetime u=ToUtc(server_t); return u-(u%86400); }
double   BarMid(const MqlRates &r, double point){ return r.close + r.spread*point/2.0; }

double PolicyRate(string &dts[], double &rts[], datetime t)
{
   double r = rts[0];
   for(int i=0;i<ArraySize(dts);i++){ if(StringToTime(dts[i])<=t) r=rts[i]; else break; }
   return r;
}

//--- opex week membership: is `utcDay` in the Mon-Fri week that contains the
//--- 3rd Friday of its month? (3rd Fri is dom 15..21 -> its Monday is dom 11..17,
//--- always in-month, so no cross-month edge cases.) Pure deterministic calendar.
bool InOpexWeek(datetime utcDay)
{
   MqlDateTime t; TimeToStruct(utcDay,t);
   datetime first = StringToTime(StringFormat("%04d.%02d.01",t.year,t.mon));
   MqlDateTime ft; TimeToStruct(first,ft);
   int fdow = ft.day_of_week;               // MQL: Sunday=0 .. Saturday=6
   int toFri = (5 - fdow + 7) % 7;          // days from the 1st to the first Friday
   int thirdFri = 1 + toFri + 14;           // day-of-month of the 3rd Friday
   int monday = thirdFri - 4;               // Monday of that week
   return (t.day >= monday && t.day <= thirdFri);
}

//====================================================================
// SERIES MAINTENANCE
//====================================================================
void AppendDay(int sid, datetime day, double mid)
{
   int n=ArraySize(g_ser[sid].mid);
   ArrayResize(g_ser[sid].mid,n+1); ArrayResize(g_ser[sid].day,n+1);
   g_ser[sid].mid[n]=mid; g_ser[sid].day[n]=day; g_ser[sid].lastDay=day;
}

void CommitFromRates(int sid, MqlRates &r[], int got, datetime nowUtcDay)
{
   bool pre20=g_serPre20[sid];
   double point=SymbolInfoDouble(g_serSym[sid],SYMBOL_POINT);
   datetime last=g_ser[sid].lastDay;
   datetime curDay=0; double lastMid=0.0; bool have=false;
   for(int i=0;i<got;i++)
   {
      datetime uday=UtcDayStart(r[i].time);
      if(uday>=nowUtcDay) break;
      if(curDay==0) curDay=uday;
      if(uday!=curDay)
      {
         if(curDay>last && have) AppendDay(sid,curDay,lastMid);
         curDay=uday; have=false; lastMid=0.0;
      }
      bool elig=true;
      if(pre20){ MqlDateTime t; TimeToStruct(ToUtc(r[i].time),t); elig=(t.hour<20); }
      if(elig){ lastMid=BarMid(r[i],point); have=true; }
   }
   if(curDay!=0 && curDay<nowUtcDay && curDay>last && have)
      AppendDay(sid,curDay,lastMid);
}

void ExtendSeries(int sid, datetime nowUtcDay)
{
   string sym=g_serSym[sid];
   datetime last=g_ser[sid].lastDay;
   int gapDays = (last==0) ? 420 : (int)((nowUtcDay-last)/86400)+3;
   int want    = (gapDays+2)*1440;
   MqlRates r[];
   int got=CopyRates(sym,PERIOD_M1,0,want,r);
   if(got<=0) return;
   CommitFromRates(sid,r,got,nowUtcDay);
}

//====================================================================
// ROLLING STATS on a Series (indices into .mid). end_excl exclusive.
//====================================================================
double SMA(int sid,int win,int end_excl)
{
   if(end_excl<win || win<=0) return EMPTY_VALUE;
   double s=0; for(int i=end_excl-win;i<end_excl;i++) s+=g_ser[sid].mid[i];
   return s/win;
}
double PriceStd(int sid,int win,int end_excl)
{
   if(end_excl<win || win<=1) return EMPTY_VALUE;
   double m=SMA(sid,win,end_excl); if(m==EMPTY_VALUE) return EMPTY_VALUE;
   double v=0; for(int i=end_excl-win;i<end_excl;i++){ double d=g_ser[sid].mid[i]-m; v+=d*d; }
   return MathSqrt(v/(win-1));
}
double RetStd(int sid,int win,int end_excl)
{
   if(end_excl<win+1 || win<=1) return EMPTY_VALUE;
   double ret[]; ArrayResize(ret,win);
   for(int k=0;k<win;k++){ int i=end_excl-win+k; ret[k]=g_ser[sid].mid[i]/g_ser[sid].mid[i-1]-1.0; }
   double m=0; for(int k=0;k<win;k++) m+=ret[k]; m/=win;
   double v=0; for(int k=0;k<win;k++){ double d=ret[k]-m; v+=d*d; }
   return MathSqrt(v/(win-1));
}
double AnnVol(int sid,int win,int end_excl)
{
   double sd=RetStd(sid,win,end_excl);
   if(sd==EMPTY_VALUE || sd<=0) return EMPTY_VALUE;
   return sd*MathSqrt(252.0);
}
double MaxOf(int sid,int from,int to){ double m=g_ser[sid].mid[from]; for(int i=from+1;i<=to;i++) if(g_ser[sid].mid[i]>m) m=g_ser[sid].mid[i]; return m; }
double MinOf(int sid,int from,int to){ double m=g_ser[sid].mid[from]; for(int i=from+1;i<=to;i++) if(g_ser[sid].mid[i]<m) m=g_ser[sid].mid[i]; return m; }

int DonchSig(int sid,int lb,int end_idx)
{
   for(int k=end_idx;k>=lb;k--)
   {
      double hi=MaxOf(sid,k-lb,k-1);
      double lo=MinOf(sid,k-lb,k-1);
      if(g_ser[sid].mid[k]>=hi) return +1;
      if(g_ser[sid].mid[k]<=lo) return -1;
   }
   return 0;
}
double Clip(double x,double lo,double hi){ return (x<lo?lo:(x>hi?hi:x)); }

double FxTrend60(int sid,double R)
{
   int e=ArraySize(g_ser[sid].mid);
   double av=AnnVol(sid,20,e);
   if(e<61 || av==EMPTY_VALUE) return 0.0;
   int s=DonchSig(sid,60,e-1);
   return Clip(s*(0.15*R)/av,-20.0,20.0);
}

//--- one S6 leg daily magnitude = clip(vt*R/av, 0, cap), signed by `sign`.
double S6Leg(int sid,double R,double sign)
{
   int e=ArraySize(g_ser[sid].mid);
   double av=AnnVol(sid,20,e);
   if(e<21 || av==EMPTY_VALUE) return 0.0;
   return sign*Clip((InpMagVt*R)/av,0.0,InpMagCap);
}

//====================================================================
// DAILY / STAMPED SIGNAL RECOMPUTES (at 00:00 rollover; series through D-1)
//====================================================================
void RecomputeDaily()
{
   double R=InpRisk;

   // ---- BOOK_XAU: donch(50,100) L/S + overnight leverage ----
   {
      int e=ArraySize(g_ser[SID_XAU].mid);
      double av=AnnVol(SID_XAU,20,e);
      if(e>=101 && av!=EMPTY_VALUE)
      {
         int s50=DonchSig(SID_XAU,50,e-1);
         int s100=DonchSig(SID_XAU,100,e-1);
         double m50 =Clip(s50 *(0.125*R)/av,-6.0,6.0);
         double m100=Clip(s100*(0.125*R)/av,-6.0,6.0);
         g_donchTgt=m50+m100;
         g_nightLev=Clip((0.30*R)/av,0.0,6.0);
      }
      else { g_donchTgt=0.0; g_nightLev=0.0; }
   }
   // ---- BOOK_US5/USTEC: >200d regime long + Monday leverage ----
   {
      int e=ArraySize(g_ser[SID_US5].mid);
      double av=AnnVol(SID_US5,20,e);
      double sma200=SMA(SID_US5,200,e);
      if(e>=200 && av!=EMPTY_VALUE && sma200!=EMPTY_VALUE)
      {
         double d=g_ser[SID_US5].mid[e-1];
         double sig=(d>sma200)?1.0:0.0;
         g_regTgt=Clip(sig*(0.25*R)/av,-6.0,6.0);
         g_monLev=Clip((0.60*R)/av,0.0,10.0);
      }
      else { g_regTgt=0.0; g_monLev=0.0; }
   }
   // ---- S5_JPY jpy_smart (long-only) ----
   {
      int e=ArraySize(g_ser[SID_UJ].mid);
      double av=AnnVol(SID_UJ,20,e);
      double ma1=SMA(SID_UJ,100,e), maf=SMA(SID_UJ,20,e);
      if(e>=100 && av!=EMPTY_VALUE && ma1!=EMPTY_VALUE && maf!=EMPTY_VALUE)
      {
         double d=g_ser[SID_UJ].mid[e-1];
         datetime td=g_ser[SID_UJ].day[e-1];
         double carry=PolicyRate(USD_D,USD_R,td)-PolicyRate(JPY_D,JPY_R,td);
         double gate=Clip((carry-0.5)/(2.0-0.5),0.0,1.0);
         bool strong=(d>ma1)&&(d>maf);
         bool weak  =(d>ma1)&&!(d>maf);
         double sig=(strong?1.0:0.0)+0.5*gate*(weak?1.0:0.0);
         g_jpyM=Clip(sig*(0.15*R)/av,0.0,20.0);
      }
      else g_jpyM=0.0;
   }
   // ---- S1_ETH crypto_mom (long-only, cap 1.2) ----
   {
      int e=ArraySize(g_ser[SID_ETH].mid);
      double av=AnnVol(SID_ETH,20,e);
      double sma200=SMA(SID_ETH,200,e), sma20=SMA(SID_ETH,20,e), sma60=SMA(SID_ETH,60,e);
      if(e>=200 && av!=EMPTY_VALUE && sma200!=EMPTY_VALUE && sma20!=EMPTY_VALUE && sma60!=EMPTY_VALUE)
      {
         double d=g_ser[SID_ETH].mid[e-1];
         double sig=((d>sma200)&&(sma20>sma60))?1.0:0.0;
         g_ethM=Clip(sig*(0.40*R)/av,0.0,1.2);
      }
      else g_ethM=0.0;
   }
   // ---- FXT_EU / FXT_UJ fx_trend60 ----
   g_fxtEuM=FxTrend60(SID_EU,R);
   g_fxtUjM=FxTrend60(SID_UJ,R);

   // ---- V5: S6 leg daily magnitudes (opex/clock gate applied per-bar) ----
   g_s6uj = S6Leg(SID_UJ, R, +1.0);   // LONG  USDJPY
   g_s6au = S6Leg(SID_AU, R, -1.0);   // SHORT AUDUSD
   g_s6nz = S6Leg(SID_NZD,R, -1.0);   // SHORT NZDUSD

   // ---- V6: S1_BTC financing-hurdle momentum (LONG BTCUSD; daily-constant) ----
   // long only while BTC > regime-MA AND annualized lb-day momentum > hurdle
   // (so it stays FLAT unless the trend clears the ~-20%/yr crypto carry).
   {
      int e=ArraySize(g_ser[SID_BTC].mid);
      double av=AnnVol(SID_BTC,20,e);
      double sma=SMA(SID_BTC,InpBtcRegime,e);
      if(e>=InpBtcRegime && e>InpBtcLb+1 && av!=EMPTY_VALUE && sma!=EMPTY_VALUE)
      {
         double d =g_ser[SID_BTC].mid[e-1];                 // D-1 mid (shift 1)
         double d0=g_ser[SID_BTC].mid[e-1-InpBtcLb];        // D-1-lb mid
         double ann=(d0>0.0)?MathPow(d/d0,365.0/InpBtcLb)-1.0:-1.0;  // annualized lb-day momentum
         double sig=((d>sma)&&(ann>InpBtcHurdle))?1.0:0.0;
         g_btcM=Clip(sig*(InpBtcVt*R)/av,0.0,InpBtcCap);
      }
      else g_btcM=0.0;
   }
}

void RecomputeEURGBP()
{
   double R=InpRisk;
   int sid=SID_EG20;
   int e=ArraySize(g_ser[sid].mid);
   double av=AnnVol(sid,20,e);
   if(e<80 || av==EMPTY_VALUE){ g_egM=0.0; return; }
   double d=g_ser[sid].mid[e-1];
   int wins[4]={20,40,60,80};
   double zsum=0.0;
   for(int j=0;j<4;j++)
   {
      int w=wins[j];
      double sma=SMA(sid,w,e), sd=PriceStd(sid,w,e);
      if(sma==EMPTY_VALUE || sd==EMPTY_VALUE || sd<=0){ g_egM=0.0; return; }
      double z=(d-sma)/sd;
      zsum += -Clip(z,-2.5,2.5)/2.5;
   }
   double sig=zsum/4.0;
   g_egM=Clip(sig*(0.20*R)/av,-20.0,20.0);
}

void RecomputeAUD()
{
   double R=InpRisk;
   int sid=SID_AU;
   int e=ArraySize(g_ser[sid].mid);
   double volD=AnnVol(sid,20,e);
   double sma10=SMA(sid,10,e), sd10=PriceStd(sid,10,e);
   if(e<21 || volD==EMPTY_VALUE || sma10==EMPTY_VALUE || sd10==EMPTY_VALUE || sd10<=0){ g_auM=0.0; return; }
   int cnt=e-21+1;
   if(cnt<60){ g_auM=0.0; return; }
   double vser[]; ArrayResize(vser,cnt); int nv=0;
   for(int k=21;k<=e;k++){ double vv=AnnVol(sid,20,k); if(vv!=EMPTY_VALUE){ vser[nv]=vv; nv++; } }
   if(nv<60){ g_auM=0.0; return; }
   ArrayResize(vser,nv);
   ArraySort(vser);
   double med = (nv%2==1) ? vser[nv/2] : 0.5*(vser[nv/2-1]+vser[nv/2]);
   double scale=Clip(med/volD,0.0,1.0);
   double d=g_ser[sid].mid[e-1];
   double z=(d-sma10)/sd10;
   double zc=-Clip(z,-2.0,2.0)/2.0;
   g_auM = zc*(2.0*R)*scale;
}

//====================================================================
// CURRENT (per-bar) SIGNED TARGET MULTIPLE per sleeve
//====================================================================
double CurrentTarget(int sleeve,int hour,int dow)   // dow: MQL Sun=0..Sat=6
{
   switch(sleeve)
   {
      case SL_XAU:
      {
         bool nightOn=(hour>=20 || hour<8);
         double night=nightOn?g_nightLev:0.0;
         return g_donchTgt*(0.17/0.36) + night*(0.19/0.36);
      }
      case SL_US5:
      {
         bool monOn=(dow==1 && hour<21);
         double mon=monOn?g_monLev:0.0;
         return g_regTgt*(0.09/0.24) + mon*(0.15/0.24);
      }
      case SL_JPY: return g_jpyM;
      case SL_ETH: return g_ethM;
      case SL_EG:  return g_egM;
      case SL_AU:  return g_auM;
      case SL_FEU: return g_fxtEuM;
      case SL_FUJ: return g_fxtUjM;
      // ---- V5 S6 legs: active only Mon 12:00 -> Fri 20:00 UTC of the opex week ----
      case SL_S6UJ: case SL_S6AU: case SL_S6NZ:
      {
         if(dow<1 || dow>5) return 0.0;                 // weekend (MQL Mon=1..Fri=5)
         if(!InOpexWeek(UtcDayStart(TimeCurrent()))) return 0.0;
         if(dow==1 && hour<12) return 0.0;              // Monday before 12:00 UTC
         if(dow==5 && hour>=20) return 0.0;             // Friday at/after 20:00 UTC
         if(sleeve==SL_S6UJ) return g_s6uj;
         if(sleeve==SL_S6AU) return g_s6au;
         return g_s6nz;
      }
      case SL_BTC: return g_btcM;                       // daily-constant long-BTC
   }
   return 0.0;
}

//====================================================================
// EUR-per-quote conversion for a traded symbol
//====================================================================
double MidOf(string sym){ double b=SymbolInfoDouble(sym,SYMBOL_BID),a=SymbolInfoDouble(sym,SYMBOL_ASK); return (b>0&&a>0)?0.5*(a+b):0.0; }
double EurPerQuote(string sym)
{
   double m;
   if(sym==InpUSDJPY)      m=MidOf(InpEURJPY);   // quote JPY
   else if(sym==InpEURGBP) m=MidOf(InpEURGBP);   // quote GBP
   else                    m=MidOf(InpEURUSD);   // quote USD (XAU,US5,ETH,AUD,NZD,EURUSD)
   return (m>0)?1.0/m:0.0;
}

//====================================================================
// SIZING — signed desired lots for a sleeve at multiple m and balance
//====================================================================
double RoundLots(string sym,double lots)
{
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   if(step<=0) step=0.01;
   double n=MathFloor(lots/step+1e-9);
   double out=n*step;
   if(out<minl) return 0.0;
   return out;
}

//--- v6.01 FIX (invalid volume): a single order larger than SYMBOL_VOLUME_MAX
//--- is rejected whole by the broker ("Invalid volume"), silently starving the
//--- sleeve (root cause of the R>=15 net-profit plateau; first seen on ETHUSD).
//--- Split any desired size into chunks <= VOLUME_MAX. Safety cap 40 chunks.
void SendSplit(string sym,int dir,double vol)
{
   double vmax=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   if(vmax<=0) vmax=vol;
   double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double rem=vol; int chunks=0;
   for(int i=0;i<40 && rem>=minl;i++)
   {
      double chunk=RoundLots(sym,MathMin(rem,vmax));
      if(chunk<=0) break;
      bool ok=(dir>0)?trade.Buy(chunk,sym):trade.Sell(chunk,sym);
      if(!ok && trade.ResultRetcode()!=TRADE_RETCODE_DONE){
         g_nReject++;
         LogReject("SendSplit",sym,dir,chunk,trade.ResultRetcode(),trade.ResultComment()); // P2 (live-only)
         break;
      }
      chunks++; rem-=chunk;
   }
   if(chunks>1) g_nSplit++;
}

// [F3 MARGIN GOVERNOR] account-aggregate free-margin haircut. Set ONCE per bar by
// F3_MlGovernorPrepass() (V34Exec.mqh) BEFORE any sizing/placement. DesiredLots
// multiplies its per-leg-clamped output by this UNIFORM factor so the whole desired
// book scales down together (relative weights preserved) when projected account ML
// would breach InpMinMarginLevel. 1.0 = no haircut. At InpMinMarginLevel<=0 the
// pre-pass never runs and this stays exactly 1.0, so the guarded multiply in
// DesiredLots is never taken -> bit-identical to the frozen build (G1/G2 parity).
double g_f3MlShrink = 1.0;

double DesiredLots(string sym,double m,double balance)
{
   if(m==0.0 || balance<=0.0) return 0.0;
   int    dir=(m>0)?1:-1;
   double px=(dir>0)?SymbolInfoDouble(sym,SYMBOL_ASK):SymbolInfoDouble(sym,SYMBOL_BID);
   double contract=SymbolInfoDouble(sym,SYMBOL_TRADE_CONTRACT_SIZE);
   double eurq=EurPerQuote(sym);
   // [F3 CHANGE 4] the guard below used to no-op a leg SILENTLY. SOLUSD legitimately
   // has no data before 2022-03-14, so WARN once per symbol per session (V34Exec.mqh
   // helper), never abort, never spam.
   if(px<=0 || eurq<=0 || contract<=0) F3_SizeSkipWarn(sym);   // [F3 CHANGE 4] loud once-per-symbol WARN
   if(px<=0 || eurq<=0 || contract<=0) return 0.0;
   double unit_eur=px*contract*eurq;
   double lots=balance*MathAbs(m)/unit_eur;
   // [F3 CHANGE 5] withdraw-to-base modeling (G3b): InpSizingBase>0 rescales the
   // compounding-balance lots to a CONSTANT base so neither margin nor volume caps
   // bind and k reflects only friction. Scales BOTH books (v7 VBalance-sized, v3.4
   // e34-sized) while preserving each book's internal weight drift (the balance
   // ratio between legs cancels). Degenerate eq<=0 guarded. At the default 0 this
   // line is arithmetically INERT (no multiply -> G1/G2 parity).
   if(InpSizingBase>0){ double f3eq=AccountInfoDouble(ACCOUNT_EQUITY); if(f3eq>0) lots*=InpSizingBase/f3eq; }   // [F3 CHANGE 5]
   double mpl=0.0;
   ENUM_ORDER_TYPE ot=(dir>0)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   if(OrderCalcMargin(ot,sym,1.0,px,mpl) && mpl>0)
   {
      double maxlots=balance*InpMarginCap/mpl;
      if(lots>maxlots) lots=maxlots;
   }
   // v6.01 FIX: respect the broker's AGGREGATE per-symbol volume ceiling
   // (SYMBOL_VOLUME_LIMIT, 0 = unlimited) — orders beyond it are rejected.
   double vlim=SymbolInfoDouble(sym,SYMBOL_VOLUME_LIMIT);
   if(vlim>0 && lots>vlim) lots=vlim;
   // [F3 MARGIN GOVERNOR] uniform account-aggregate haircut on the already per-leg-
   // clamped & volume-clamped lots. FLOOR-then-shrink-then-REFLOOR, matching the record
   // engine account_engine_1m.py:130-148, so realized used-margin <= cap and ML lands
   // slightly ABOVE the floor (conservative). g_f3MlShrink==1.0 at default (OFF, or
   // ON-but-non-binding) so this branch is NEVER taken -> byte-identical to the frozen build.
   if(g_f3MlShrink<1.0) lots=RoundLots(sym,lots)*g_f3MlShrink;
   double rl=RoundLots(sym,lots);
   return dir*rl;
}

//====================================================================
// POSITION QUERIES / EXECUTION (signed, hedging-aware)
//====================================================================
double HeldNet(string sym,long magic)
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
int CollectTickets(string sym,long magic,int wantType,ulong &tks[])
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
void CloseAll(string sym,long magic)
{
   ulong tks[]; int n=CollectTickets(sym,magic,-1,tks);
   for(int i=0;i<n;i++)
      if(!trade.PositionClose(tks[i]) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
         LogReject("CloseAll",sym,0,0.0,trade.ResultRetcode(),trade.ResultComment()); // P2 (live-only)
}
void ReducePos(string sym,long magic,double vol,int heldType)
{
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP); if(step<=0) step=0.01;
   double minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);  if(minl<=0) minl=step;
   double rem=vol; ulong tks[]; int n=CollectTickets(sym,magic,heldType,tks);
   for(int i=0;i<n && rem>=step*0.5;i++)
   {
      if(!PositionSelectByTicket(tks[i])) continue;
      double pv=PositionGetDouble(POSITION_VOLUME);
      double cv=MathMin(pv,rem);
      cv=MathFloor(cv/step+1e-9)*step;      // v6.01: floor, never round UP past pv (invalid close volume)
      if(cv<step*0.5) continue;
      if(cv>=pv-step*0.5){
         if(!trade.PositionClose(tks[i]) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
            LogReject("ReducePos",sym,0,cv,trade.ResultRetcode(),trade.ResultComment());        // P2 (live-only)
      }
      else{
         // v7.01 FIX (invalid volume): a PARTIAL close needs BOTH the closed
         // part AND the remainder >= SYMBOL_VOLUME_MIN. On coarse-min symbols
         // (SOLUSD min=1.0, step=0.01) a sub-min partial is rejected "Invalid
         // volume"; since closes are never held it re-sends every bar (observed:
         // 32 SOLUSD #12039 rejects, 2023-11..12). Defer the un-sendable partial
         // instead: RESULTS-NEUTRAL (the leg was already un-reducible at this
         // size, position stays put exactly as before) and it never fabricates a
         // new close, so the frozen book is bit-unchanged. No-op where min==step
         // (all v7 FX/metal/index legs); bites only coarse-min crypto.
         if(cv<minl-step*0.5 || pv-cv<minl-step*0.5) continue;
         if(!trade.PositionClosePartial(tks[i],cv) && trade.ResultRetcode()!=TRADE_RETCODE_DONE)
            LogReject("ReducePosPartial",sym,0,cv,trade.ResultRetcode(),trade.ResultComment());  // P2 (live-only)
      }
      rem-=cv;
   }
}
void OpenDir(string sym,double signedVol)
{
   if(signedVol>0) SendSplit(sym,+1,signedVol);
   else if(signedVol<0) SendSplit(sym,-1,-signedVol);
}

bool InReopenWindow()
{
   MqlDateTime t; TimeToStruct(ToUtc(TimeCurrent()),t);
   return (t.hour==21 || t.hour==22);
}

//--- v6.01 FIX (market closed): the clock chart (crypto) ticks 24/7, so weekend
//--- day-rollovers and index session breaks previously fired orders into CLOSED
//--- markets ("Market closed" rejects; and a weekend rebalance would reseed the
//--- ledger while CloseAll silently failed = accounting drift). Session check
//--- against the symbol's trade sessions in SERVER time.
bool MarketOpen(string sym)
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
//--- all ENABLED sleeves' markets open (gate for rebalance/harvest re-splits)
bool AllMarketsOpen()
{
   for(int n=0;n<N_SLEEVE;n++)
      if(W[n]>0.0 && !MarketOpen(g_slSym[n])) return false;
   return true;
}

//====================================================================
// SUB-ACCOUNT LEDGER
//====================================================================
void UpdateRealized()
{
   if(!HistorySelect(g_quarterStart,TimeCurrent()+1)) return;
   int tot=HistoryDealsTotal();
   for(int i=g_dealCursor;i<tot;i++)
   {
      ulong tk=HistoryDealGetTicket(i); if(tk==0) continue;
      long magic=HistoryDealGetInteger(tk,DEAL_MAGIC);
      int idx=(int)(magic-(InpMagicBase+1));
      if(idx<0 || idx>=N_SLEEVE) continue;
      double pnl=HistoryDealGetDouble(tk,DEAL_PROFIT)
                +HistoryDealGetDouble(tk,DEAL_SWAP)
                +HistoryDealGetDouble(tk,DEAL_COMMISSION);
      g_realized[idx]+=pnl;
   }
   g_dealCursor=tot;
}
double VBalance(int sleeve){ return g_seed[sleeve]+g_realized[sleeve]; }

//--- floating P&L (profit+swap) of a sleeve's open positions (by magic)
double FloatingPnL(int sleeve)
{
   string sym=g_slSym[sleeve]; long magic=InpMagicBase+sleeve+1;
   double f=0.0; int tot=PositionsTotal();
   for(int i=0;i<tot;i++)
   {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=magic) continue;
      f += PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
   }
   return f;
}

//--- V5.1 band-triggered harvest: true if any enabled sleeve's slot equity
//--- (VBalance + floating) exceeds InpHarvestK x its window-start seed.
//--- Checked once per UTC day rollover (matches the validated daily cadence:
//--- decision on the day close = the rollover moment, action immediately).
bool HarvestTriggered()
{
   if(InpHarvestK<=0.0) return false;
   for(int n=0;n<N_SLEEVE;n++)
   {
      if(W[n]<=0.0 || g_seed[n]<=0.0) continue;
      double slot=VBalance(n)+FloatingPnL(n);
      if(slot > InpHarvestK*g_seed[n])
      {
         LogRow("HARVEST",n,slot/g_seed[n],0,0,slot);
         return true;
      }
   }
   return false;
}

//--- V7 BAND_SYM_25 concentration-band re-split trigger (REPLACES V6's calendar
//--- quarter cadence). True if any SLOT's share of total book equity exceeds
//--- InpBandUp OR falls below (1/nSlots)/InpBandDownDiv, gated by a minimum gap of
//--- InpBandMinGapDays since the last re-split (g_quarterStart is that state — no new
//--- persisted field). Reuses the harvest's per-sleeve equity read (VBalance +
//--- FloatingPnL, lines above).
//---
//--- SLOT vs SLEEVE: the validated Python rule is a 7-SLOT rule (share vs (1/7)/1.75).
//--- The EA implements the S6_OPEXUSD slot as THREE sleeve indices (SL_S6UJ/AU/NZ, each
//--- ~1/21 of the book). Iterating per-SLEEVE with (1/nEnabled) would put every S6 leg
//--- permanently below any floor and misfire every min-gap. So the 3 S6 legs are SUMMED
//--- into ONE slot before the share test; every other enabled sleeve is its own slot.
//--- This reproduces the validated (1/7)/1.75 = 0.0816 floor exactly for the deployed
//--- 7-slot book. (>>> REVIEW: confirm this slot aggregation against the Python reference
//--- during reconciliation; see docs/V7_GBANDREBAL_RESULTS.md §2 and header. <<<)
//---
//--- NO lookahead: called once per UTC day at the 00:00 rollover; shares are the
//--- day-close equity marks, acted on immediately — the exact cadence validated for the
//--- harvest.
bool BandTriggered()
{
   if(InpBandUp<=0.0) return false;                                  // band disabled
   if((TimeCurrent()-g_quarterStart) < InpBandMinGapDays*86400) return false;  // min-gap

   double slotEq[N_SLEEVE];
   int    nSlots=0;
   double tot=0.0;
   double s6eq=0.0; bool s6on=false;
   for(int n=0;n<N_SLEEVE;n++)
   {
      if(W[n]<=0.0) continue;
      double eq=VBalance(n)+FloatingPnL(n);
      tot+=eq;
      if(n==SL_S6UJ || n==SL_S6AU || n==SL_S6NZ){ s6eq+=eq; s6on=true; } // S6 legs -> one slot
      else { slotEq[nSlots]=eq; nSlots++; }
   }
   if(s6on){ slotEq[nSlots]=s6eq; nSlots++; }
   if(nSlots<=0 || tot<=0.0) return false;

   double floorShare=(1.0/nSlots)/InpBandDownDiv;
   for(int i=0;i<nSlots;i++)
   {
      double share=slotEq[i]/tot;
      if(share>InpBandUp || share<floorShare)
      {
         LogRow("BAND",-1,share,(double)nSlots,floorShare,tot);       // log breaching share + floor + book eq
         return true;
      }
   }
   return false;
}

int QuarterId(datetime utc){ MqlDateTime t; TimeToStruct(utc,t); return t.year*4 + (t.mon-1)/3; }

void SaveState()
{
   int h=FileOpen(STATE_FILE,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE){ Print("PortfolioV5: WARN could not write state file"); return; }
   FileWrite(h,IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)),
             IntegerToString((long)g_quarterStart),IntegerToString(g_lastRebalQ),
             IntegerToString(g_dealCursor),
             DoubleToString(g_seed[0],4),DoubleToString(g_seed[1],4),
             DoubleToString(g_seed[2],4),DoubleToString(g_seed[3],4),
             DoubleToString(g_seed[4],4),DoubleToString(g_seed[5],4),
             DoubleToString(g_seed[6],4),DoubleToString(g_seed[7],4),
             DoubleToString(g_seed[8],4),DoubleToString(g_seed[9],4),
             DoubleToString(g_seed[10],4),DoubleToString(g_seed[11],4));
   FileFlush(h); FileClose(h);
}
bool LoadState()
{
   if(!FileIsExist(STATE_FILE,FILE_COMMON)) return false;
   int h=FileOpen(STATE_FILE,FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return false;
   long login=(long)FileReadNumber(h);
   long qs   =(long)FileReadNumber(h);
   int  lq   =(int) FileReadNumber(h);
   int  dc   =(int) FileReadNumber(h);
   double sd[N_SLEEVE];
   for(int n=0;n<N_SLEEVE;n++) sd[n]=FileReadNumber(h);
   FileClose(h);
   if(login!=(long)AccountInfoInteger(ACCOUNT_LOGIN))
   { Print("PortfolioV5: state file is for a different login -> starting fresh."); return false; }
   double ss=0.0; for(int n=0;n<N_SLEEVE;n++) ss+=sd[n];
   if(qs<=0 || ss<=0.0)
   { Print("PortfolioV5: state file invalid (qs=",qs," seedSum=",ss,") -> starting fresh."); return false; }
   g_quarterStart=(datetime)qs; g_lastRebalQ=lq; g_dealCursor=dc;
   for(int n=0;n<N_SLEEVE;n++) g_seed[n]=sd[n];
   return true;
}

void QuarterRebalance(int hour,int dow)
{
   // [F3 SEAM 1] federation: reseed v7 slots from the v7 VIRTUAL sub-book equity,
   // never the shared account (anti-coupling, STRATEGY.md par.4.5). v7-only mode
   // (g_f3FedActive=false) takes the byte-identical original expression (gate G1).
   // [F3 RESEED-BASIS] InpReseedBalance swaps the FEDERATED pooled basis from the
   // floating-INCLUSIVE virtual equity (F3_V7BookEquity) to the realized-only pooled
   // BALANCE (F3_V7BookBalance). This is the PRE-loop sizing basis (B_before); the
   // ledger reseed below RECOMPUTES the balance AFTER folding this bar's own closes.
   // At InpReseedBalance=false the expression is the original -> byte-identical (G1).
   double preEquity = g_f3FedActive
                      ? (InpReseedBalance ? F3_V7BookBalance() : F3_V7BookEquity())
                      : AccountInfoDouble(ACCOUNT_EQUITY);
   // --- H9 delta-resize: move each ENABLED sleeve to its EXACT new equal-capital
   // target. When the new target is the SAME sign as the held position, OrderSend
   // ONLY the delta (add or partial-reduce) — refunding the boundary spread+commission
   // that V6's close-all+reopen-flat paid twice (+~1.5pp, V4 cost search). A sign flip
   // (reversal) or a flat target (=0) still CloseAll — a reversal cannot be a same-sign
   // delta. The target is sized off the NEW equal capital (preEquity*W[n]) exactly as
   // the V6 reopen would size it off the reseeded VBalance, so the same-bar ExecSleeve
   // pass sees no drift (no churn) and the forward sizing basis / Python reconciliation
   // are unchanged — only the ORDER PATH to the target is cheaper.
   // Callers gate on AllMarketsOpen(), so these OrderSends never hit a closed market.
   for(int n=0;n<N_SLEEVE;n++)
   {
      if(W[n]<=0.0) continue;
      string sym=g_slSym[n]; long magic=InpMagicBase+n+1;
      trade.SetExpertMagicNumber(magic);
      trade.SetTypeFillingBySymbol(sym);
      double m=CurrentTarget(n,hour,dow);
      // [F3 RESEED MODE] independent per-sleeve reseed (v-next test): size off the sleeve's
      // OWN carried equity (g_seed+g_realized = VBalance) instead of the pooled equal-capital
      // preEquity*W[n]. At InpIndepReseed=false this is byte-identical to the pooled expression.
      double reseedEq = InpIndepReseed ? (g_seed[n]+g_realized[n]) : preEquity*W[n];
      double target=DesiredLots(sym,m,reseedEq);                // signed new_lots
      double held=HeldNet(sym,magic);
      int sgnT=(target>0)?1:((target<0)?-1:0);
      int sgnP=(held>0)?1:((held<0)?-1:0);
      if(sgnT==0)                        CloseAll(sym,magic);                       // target flat
      else if(sgnP==0)                   OpenDir(sym,target);                       // from flat
      else if(sgnT!=sgnP){ CloseAll(sym,magic); OpenDir(sym,target); }             // reversal: close+reopen
      else                                                                         // SAME SIGN: delta only
      {
         double dv=MathAbs(target)-MathAbs(held);
         if(dv>0)      OpenDir(sym,sgnT*dv);                                        // add up to target
         else if(dv<0) ReducePos(sym,magic,-dv,(sgnP>0)?POSITION_TYPE_BUY:POSITION_TYPE_SELL); // trim to target
         // dv==0: already at target -> no order
      }
   }
   // --- ledger reseed. POOLED (default, InpIndepReseed=false): BYTE-IDENTICAL to V6
   // (seed=preEquity*W[n], realized reset). INDEP: carry each sleeve's own VBalance forward
   // (no pooled redistribution -> no floating double-count). Fold THIS rebalance's own
   // close/trim deals FIRST so indep VBalance captures them (byte-neutral in POOLED mode:
   // g_seed uses preEquity not g_realized, g_realized is reset to 0 either way, and the deal
   // cursor is advanced to HistoryDealsTotal below regardless).
   UpdateRealized();
   // [F3 RESEED-BASIS] Pooled ledger reseed basis. EQUITY variant (default): reuse the
   // pre-loop preEquity -> BYTE-IDENTICAL to the frozen build. BALANCE variant: RECOMPUTE
   // the pooled balance AFTER UpdateRealized so THIS rebalance's own close/trim realized
   // P&L is folded in (B_after) -> the re-split conserves the realized pool exactly (no
   // P&L dropped when g_realized resets) and E_v7 tracks the real account (residual ~0).
   double reseedBasis = (g_f3FedActive && InpReseedBalance) ? F3_V7BookBalance() : preEquity;
   for(int n=0;n<N_SLEEVE;n++){ g_seed[n] = InpIndepReseed ? (g_seed[n]+g_realized[n]) : reseedBasis*W[n]; g_realized[n]=0.0; }
   g_quarterStart=TimeCurrent();
   if(HistorySelect(g_quarterStart,TimeCurrent()+1)) g_dealCursor=HistoryDealsTotal();
   g_lastRebalQ=QuarterId(UtcDayStart(TimeCurrent()));            // now log-only (no calendar trigger)
   if(g_live) SaveState();
   LogRow("REBAL",-1,0,0,0,preEquity);
}

//====================================================================
// LOGGING
//====================================================================
void LogRow(string ev,int sleeve,double m,double desired,double held,double extra)
{
   if(!InpLog || g_logh==INVALID_HANDLE) return;
   string nm=(sleeve>=0)?g_slName[sleeve]:"PORT";
   FileWrite(g_logh,TimeToString(ToUtc(TimeCurrent()),TIME_DATE|TIME_MINUTES),
             nm,ev,DoubleToString(m,4),DoubleToString(desired,2),
             DoubleToString(held,2),DoubleToString(extra,2),
             DoubleToString((sleeve>=0)?VBalance(sleeve):0.0,2),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1));
   FileFlush(g_logh);
}

void Heartbeat(string status="OK")
{
   int h=FileOpen(HB_FILE,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)==0)
      FileWrite(h,"utc_time","balance","equity","margin_level","n_positions",
                "net_XAU","net_US5","net_JPY","net_ETH","net_EG",
                "net_S6UJ","net_S6AU","net_S6NZ","net_BTC","status");
   FileSeek(h,0,SEEK_END);
   FileWrite(h,TimeToString(ToUtc(TimeCurrent()),TIME_DATE|TIME_MINUTES),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2),
             DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),1),
             IntegerToString(PositionsTotal()),
             DoubleToString(HeldNet(g_slSym[SL_XAU],InpMagicBase+SL_XAU+1),2),
             DoubleToString(HeldNet(g_slSym[SL_US5],InpMagicBase+SL_US5+1),2),
             DoubleToString(HeldNet(g_slSym[SL_JPY],InpMagicBase+SL_JPY+1),2),
             DoubleToString(HeldNet(g_slSym[SL_ETH],InpMagicBase+SL_ETH+1),2),
             DoubleToString(HeldNet(g_slSym[SL_EG], InpMagicBase+SL_EG+1),2),
             DoubleToString(HeldNet(g_slSym[SL_S6UJ],InpMagicBase+SL_S6UJ+1),2),
             DoubleToString(HeldNet(g_slSym[SL_S6AU],InpMagicBase+SL_S6AU+1),2),
             DoubleToString(HeldNet(g_slSym[SL_S6NZ],InpMagicBase+SL_S6NZ+1),2),
             DoubleToString(HeldNet(g_slSym[SL_BTC], InpMagicBase+SL_BTC+1),2),
             status);
   FileFlush(h); FileClose(h);
}

//====================================================================
// P2 — ORDER-REJECT LOGGING (retcode + comment).  LIVE-ONLY: a hard no-op
// in the Strategy Tester (returns before any file I/O), so backtest output
// is byte-identical. Append+flush, following the Heartbeat/SaveState pattern.
//====================================================================
void LogReject(string where,string sym,int dir,double vol,uint rc,string cmt)
{
   if(!g_live) return;                       // TESTER: no-op (byte-neutral)
   int h=FileOpen(REJ_FILE,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)==0)
      FileWrite(h,"utc_time","where","symbol","dir","volume","retcode","comment");
   FileSeek(h,0,SEEK_END);
   FileWrite(h,TimeToString(ToUtc(TimeCurrent()),TIME_DATE|TIME_MINUTES),
             where,sym,IntegerToString(dir),DoubleToString(vol,2),
             IntegerToString((long)rc),cmt);
   FileFlush(h); FileClose(h);
}

//====================================================================
// P1 — DISCONNECT / INSUFFICIENT-HISTORY SKIP LOGGING.  LIVE-ONLY.
//====================================================================
void LogSkip(string reason,string detail)
{
   if(!g_live) return;                       // TESTER: no-op (byte-neutral)
   int h=FileOpen(SKIP_FILE,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE) return;
   if(FileSize(h)==0) FileWrite(h,"utc_time","reason","detail");
   FileSeek(h,0,SEEK_END);
   FileWrite(h,TimeToString(ToUtc(TimeCurrent()),TIME_DATE|TIME_MINUTES),reason,detail);
   FileFlush(h); FileClose(h);
}

//--- P1 live-reliability gate. TESTER: returns true IMMEDIATELY (TERMINAL_CONNECTED
//--- is always true and history is always present there anyway) -> the skip paths are
//--- UNREACHABLE in the Strategy Tester, so this is byte-neutral. LIVE: returns false
//--- (skip this bar's reconcile/trade pass) while the terminal is disconnected OR an
//--- enabled traded symbol's M1 series is not synced / has < InpMinM1Bars bars. The
//--- reason is logged ONCE per contiguous skip episode (g_skipActive), with a RESUME
//--- line when the EA recovers. The reconcile-every-bar core self-heals on the next
//--- ready bar (g_curDay/g_quarterStart are untouched while skipping).
bool LiveReady()
{
   if(!g_live) return true;                                  // TESTER: always ready (no-op)
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      if(!g_skipActive){ LogSkip("DISCONNECT","terminal not connected"); g_skipActive=true; }
      return false;
   }
   if(InpMinM1Bars>0)
   {
      for(int n=0;n<N_SLEEVE;n++)
      {
         if(W[n]<=0.0) continue;
         string sym=g_slSym[n];
         bool synced=(SeriesInfoInteger(sym,PERIOD_M1,SERIES_SYNCHRONIZED)!=0);
         long nb=Bars(sym,PERIOD_M1);
         if(!synced || nb<InpMinM1Bars)
         {
            if(!g_skipActive){
               LogSkip("HIST_INSUFF",sym+" bars="+IntegerToString(nb)+" synced="+(synced?"1":"0"));
               g_skipActive=true;
            }
            return false;
         }
      }
   }
   if(g_skipActive){ LogSkip("RESUME","connected & history synced"); g_skipActive=false; }
   return true;
}

//====================================================================
// PER-SLEEVE EXECUTION toward the current target
//====================================================================
void ExecSleeve(int n,int hour,int dow)
{
   string sym=g_slSym[n]; long magic=InpMagicBase+n+1;
   double m=CurrentTarget(n,hour,dow);
   double bal=VBalance(n);
   double desired=DesiredLots(sym,m,bal);
   double held=HeldNet(sym,magic);

   int sgnT=(desired>0)?1:((desired<0)?-1:0);
   int sgnP=(held>0)?1:((held<0)?-1:0);
   if(sgnT==0) F3_HoldClear(sym,magic);   // [F3 CHANGE 2] flat target clears any hold

   bool wantChange=false;
   if(sgnT==0)        wantChange=(sgnP!=0);
   else if(sgnT!=sgnP) wantChange=true;
   else
   {
      double drift=MathAbs(MathAbs(desired)-MathAbs(held))/MathAbs(held);
      wantChange=(drift>InpRebalBand);
      // [F3 MARGIN GOVERNOR] HARD floor: when the governor is binding (shrink<1), force a
      // REDUCE toward the shrunk target even INSIDE the dead-band. Fires ONLY when
      // |desired|<|held| (a de-risking trim; adds stay band-gated), routing to ReducePos
      // (never F3_SendAdd, never suppressed). Inert at g_f3MlShrink==1.0.
      if(g_f3MlShrink<1.0 && MathAbs(desired)<MathAbs(held)) wantChange=true;
   }
   if(!wantChange){ g_deferred[n]=false; return; }

   // reopen filter: defer any change 21:00-22:59 UTC, EXCEPT BOOK_US5 and the
   // V5 diversifiers (their Python legs carry no defer_reopen; a no-op here since
   // they never change in that window, but exempting is exact).
   if(n!=SL_US5 && !IS_DIVERSIFIER(n) && InReopenWindow())
   {
      if(!g_deferred[n]){ LogRow("DEFER",n,m,desired,held,0); g_deferred[n]=true; }
      return;
   }
   // v6.01: never fire orders into a closed market (weekends/session breaks) —
   // defer to the next bar where this symbol's market is open.
   if(!MarketOpen(sym))
   {
      if(!g_deferred[n]){ LogRow("CLOSED",n,m,desired,held,0); g_deferred[n]=true; g_nClosed++; }
      return;
   }
   g_deferred[n]=false;

   // [F3 CHANGE 2+3] same-direction adds/opens route through the F3_SendAdd seam
   // (V34Exec.mqh: reject-backoff hold + account-aggregate volume clamp; returns
   // false = leg held, nothing sent). Closes/reduces/reversal-CLOSES are NEVER
   // suppressed - they keep the verbatim v7 order path.
   if(sgnT==0)                              CloseAll(sym,magic);
   else if(sgnP==0){ if(!F3_SendAdd(sym,magic,sgnT,MathAbs(desired),desired,held)) return; }             // [F3 CHANGE 2+3]
   else if(sgnT!=sgnP){ CloseAll(sym,magic); F3_SendAdd(sym,magic,sgnT,MathAbs(desired),desired,0.0); }  // [F3 CHANGE 2+3] close always runs
   else
   {
      double dv=MathAbs(desired)-MathAbs(held);
      if(dv>0){ if(!F3_SendAdd(sym,magic,sgnT,dv,desired,held)) return; }                                // [F3 CHANGE 2+3]
      else     ReducePos(sym,magic,-dv,(sgnP>0)?POSITION_TYPE_BUY:POSITION_TYPE_SELL);
   }

   double after=HeldNet(sym,magic);
   // [F3 CHANGE 2] a change was wanted but nothing moved -> the send was rejected/
   // no-op: arm the hold ONLY for same-direction adds/opens (closes/reduces retry).
   if(MathAbs(after-held)<F3_StepOf(sym)*0.5 && sgnT!=0 && (sgnP==0 || (sgnT==sgnP && MathAbs(desired)>MathAbs(held)))) F3_HoldSet(sym,magic,desired,held,"reject");   // [F3 CHANGE 2]
   if(MathAbs(after-held) < 1e-9) return;
   string ev = (MathAbs(after)<1e-9)      ? "CLOSE" :
               (MathAbs(held)<1e-9)       ? "OPEN"  :
               (after*held<0)             ? "FLIP"  :
               (MathAbs(after)>MathAbs(held)) ? "ADD" : "REDUCE";
   LogRow(ev,n,m,desired,held,after);
}
