//+------------------------------------------------------------------+
//| FableBookNative.mq5 — the LIVE-COMPUTING native Fable book.       |
//|                                                                    |
//| Computes f_core / f_sat / a / b / book_frac[33] LIVE each bar from |
//| the terminal's own synchronized multi-symbol M1 feed, replacing    |
//| the frozen-CSV replay of FableBook.mq5.  One model, two dials:     |
//| InpScale is the ONLY IC<->FTMO difference (IC 1.6 / FTMO 0.7 +     |
//| breaker), exactly as the v3 model of record.                       |
//|                                                                    |
//| THE COMPUTE CHAIN (every component individually gate-proven):      |
//|   feed   : CFeedAssembler (S0-proven data path; f32 six-field b    |
//|            rows + raw H1 closes bit-exact vs the golden bundles)   |
//|   signal : 8 Sat sleeves + Ensemble -> f_sat[31] (RECON-8b) and    |
//|            CCoreSignal live targets (RECON-8g bit-zero) +          |
//|            CCoreTrigger causal segment detector (31/31 measured)   |
//|   equity : CBookOrchestrator M1 clock — b = SatEquityNative on the |
//|            HELD prior-hour f_sat (RECON-8d bitwise); a = live      |
//|            CCoreLiveDrive (CoreSim per-leg accounts, hold-at-      |
//|            legcap live combine per FABLE REVISION v2 item 2)       |
//|   blend  : BookBlend on asof a_h/b_h -> book_frac[33] (RECON-8c);  |
//|            whole chain R1-proven at 5.06e-13 (RECON-8e)            |
//|   exec   : g_fedTgt[33] -> FED_Reconcile — VERBATIM the RECON-4-   |
//|            proven FableBook execution half (margin cap, rebalance  |
//|            band, volume-limit clamp, split send, FTMO Guardian)    |
//|                                                                    |
//| SAFETY (mandatory defaults):                                       |
//|   * InpAllowLiveTrading = false — on a LIVE chart the EA computes  |
//|     and logs EVERYTHING but issues ZERO OrderSend.  The Strategy   |
//|     Tester is auto-enabled via MQLInfoInteger(MQL_TESTER) so the   |
//|     position-fidelity gate runs unmodified; a live chart trades    |
//|     ONLY with the input explicitly set true.                       |
//|   * REFUSE-TO-TRADE latch: any warm-blob validation failure        |
//|     (torn write / checksum / anchor / j-splice), any feed or       |
//|     compute drive-contract violation -> the EA stops sizing and    |
//|     prints the reason every pass.  It never trades through a       |
//|     doubted state (a re-based a/b passes every self-check while    |
//|     silently mis-weighting every trade — the latch is the guard).  |
//|   * catch-up gate: targets computed from pre-wall history are      |
//|     warmup only; FED_Reconcile runs only once the compute clock    |
//|     has caught up with the wall clock.                             |
//|                                                                    |
//| WARM START: version-2 CBookState blob (whole-book ledger +         |
//| CCoreSignal/CCoreTrigger) + a CCoreLiveDrive sidecar (same fnv64/  |
//| eof protocol).  Blob present + validates -> restore and continue   |
//| the golden path; else cold start (tester / first run).             |
//|                                                                    |
//| Attach to a BTCUSD M1 chart (24/7 clock, FableBook L21 law).       |
//| HEDGING account required when trading is enabled.                  |
//+------------------------------------------------------------------+
#property copyright "FableMultiAssets3"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

//====================================================================
// INPUTS
//====================================================================
input group "=== 1. The dial (the ONLY knob that differs IC<->FTMO) ==="
input double InpScale        = 1.60;      // s: global scale dial (IC 1.6 / FTMO 0.7)
input double InpInitial      = 10000.0;   // Seed capital EUR (IC 10000 / FTMO 100000)
input double InpDailyStopX   = 0.0;       // FTMO daily circuit breaker % (0=off)

input group "=== 2. SAFETY (read the header) ==="
input bool   InpAllowLiveTrading = false; // MASTER SWITCH: false = compute+log, ZERO orders on a live chart (tester auto-trades)

input group "=== 3. Universe / magics / logs ==="
input long   InpMagicBase    = 3900000;   // Order magic base (+idx+1 per symbol, 33 symbols)
input string InpV34SymbolMap = "";        // canonical=broker remap (';'-sep)
input string InpExpectAbsent = "";        // broker symbols this broker genuinely lacks (';'-sep, e.g. "EURSEK" on FTMO)
input bool   InpLog          = true;      // decisions CSV to Common\Files
input string InpFedFracFile  = "FMA3_fed_frac_v3.csv"; // UNUSED live (native computes); kept for BookReplay compile unit

input group "=== 4. Engine constants (match the record engine EXACTLY) ==="
input double InpMarginCap    = 0.9;       // Margin utilisation cap
input double InpRebalBand    = 0.25;      // Rebalance dead-band

input group "=== 5. State + telemetry ==="
input string InpStateFile     = "FMA3_native_state.json"; // v2 warm blob ("" = stateless)
input bool   InpSaveState     = true;      // save blob at each completed hour (live)
input bool   InpSaveInTester  = false;     // also save inside the tester (slow)
input string InpSaveStateFrom = "";        // TESTER: save only from this UTC time, e.g. "2025.12.30 00:00" ("" = no periodic save)
// Common\Files is SHARED by every MT5 install of a Windows user, and MT5 allows one
// login per terminal — so the IC and FTMO demos run in two terminals that write to
// the SAME folder. Every per-run output must therefore be namable per account, or
// the two EAs silently clobber each other for 3 months. InpStateFile and
// InpTelemetryFile already are; the decisions CSV was hardcoded until 2026-07-16.
input string InpDecisionsFile = "fma3native_decisions.csv"; // per-account: ..._IC.csv / ..._FTMO.csv
input string InpTelemetryFile = "FMA3_native_hourly.csv"; // per-hour book_frac + a_h/b_h/j
input int    InpMaxMinutesPerPass = 20000; // feed catch-up bound per pump pass
input int    InpHeartbeatSec = 900;       // live heartbeat cadence secs (0=off): logs compute-vs-wall lag + g_histWaits so a weekend/holiday HOLD is visibly distinct from a silent FREEZE (GO_NOGO #4)

input group "=== 6. EUR conversion crosses (eurq full map, always on) ==="
input string InpEURUSD = "EURUSD";
input string InpEURJPY = "EURJPY";
input string InpEURGBP = "EURGBP";
input string InpEURCHF = "EURCHF";
input string InpEURNZD = "EURNZD";
input string InpEURCAD = "EURCAD";
input string InpEURNOK = "EURNOK";
input string InpEURSEK = "EURSEK";

//====================================================================
// INCLUDES (order matters: Convert -> Replay(universe) -> Exec ->
// Guardian, then the compute chain)
//====================================================================
#include <Book/BookConvert.mqh>      // FED_MidOf, FED_Eurq
#include <Book/BookReplay.mqh>       // 33-universe table + g_fedTgt (loader unused)
#include <Book/BookExec.mqh>         // `trade`, primitives, FED_Reconcile (RECON-4)
#include <Book/Guardian.mqh>         // FED_GuardianPass (FTMO breaker)
#include <Book/BookOrchestrator.mqh> // CBookOrchestrator (S1 R1-proven, + live hooks)
#include <Book/FeedAssembler.mqh>    // CFeedAssembler (mirror-gated)
#include <Core/CoreSignal.mqh>       // CCoreSignal + CCoreTrigger (RECON-8g)
#include <Book/CoreSignalState.mqh>  // v2 warm-blob CoreSignal wrapper
#include <Book/CoreLiveDrive.mqh>    // CCoreLiveDrive (live a_h + f_core)

//====================================================================
// WIRING CONSTANTS
//====================================================================
// FA symbol index -> CoreSignal instrument id (-1 = not a core leg)
int FaInstOf(const int i)
  {
   switch(i)
     {
      case 32: return CS_I_XAUUSD;
      case 20: return CS_I_USDJPY;
      case 22: return CS_I_ETHUSD;
      case  8: return CS_I_EURGBP;
      case 30: return CS_I_USTEC;
      case  3: return CS_I_AUDUSD;
      case 18: return CS_I_NZDUSD;
      case 21: return CS_I_BTCUSD;
     }
   return -1;
  }
#define EA_CROSS_FA0   6            // FA indices 6..13 = the 8 EUR crosses
// trigger leg -> slot map (CheckCoreSignal SmokeTrigger / trigger_detector)
const int EA_TRIG_SLOT[9] = {0, 1, 2, 3, 4, 5, 5, 5, 6};

//====================================================================
// STATE
//====================================================================
CBookOrchestrator g_orc;
CFeedAssembler    g_fa;
CCoreSignal       g_sig;
CCoreTrigger      g_trig;
CCoreSignalState  g_css;
CCoreLiveDrive    g_drive;
CBookState        g_bs;             // main v2 blob
CBookState        g_bsDrive;        // core-drive sidecar

class CEaBarBuf
  {
public:
   MqlRates          r[];
   int               pos;
   int               n;
                     CEaBarBuf() { pos = 0; n = 0; }
  };
CEaBarBuf g_buf[FA_NSYM];
long      g_from[FA_NSYM];          // next CopyRates window start
long      g_resolved[FA_NSYM];      // history resolved through (inclusive)
string    g_broker[FA_NSYM];
double    g_point[FA_NSYM];

bool      g_refuse    = false;
string    g_refuseWhy = "";
long      g_refuseLastPrint = 0;
bool      g_canTrade  = false;
bool      g_warm      = false;
long      g_backfillFrom = 0;
long      g_lastCompletedHour = 0;
long      g_unreadyRows = 0;
bool      g_dirtyState = false;
datetime  g_saveFrom  = 0;        // parsed InpSaveStateFrom (tester periodic-save window)
long      g_histWaits = 0;        // CopyRates lazy-download retries
// heartbeat state (GO_NOGO #4 clock-stall visibility) — pure reporting
ulong     g_hbLastTick     = 0;   // GetTickCount64() ms at last heartbeat (REAL elapsed, feed-independent)
long      g_hbLastHours    = 0;   // g_hours at last heartbeat
long      g_hbLastHistWait = 0;   // g_histWaits at last heartbeat
bool      g_inPump    = false;
datetime  g_lastM1Bar = 0;
int       g_teleh     = INVALID_HANDLE;
long      g_hours     = 0;

#define EA_CHUNK 16384              // CopyRates window (bars-equivalent minutes)

//====================================================================
// REFUSE-TO-TRADE latch (loud, never silent)
//====================================================================
void RefuseLatch(const string why)
  {
   if(g_refuse)
      return;
   g_refuse = true;
   g_refuseWhy = why;
   Print("FMA3 NATIVE *** REFUSE-TO-TRADE ***: ", why);
   Print("FMA3 NATIVE: compute halted; no further sizing. Fix the state/feed and restart.");
  }

//====================================================================
// TELEMETRY (per-hour book_frac + a_h/b_h/j + fills context)
//====================================================================
void TeleOpen()
  {
   // FILE_SHARE_READ is REQUIRED, not cosmetic. Without it MQL5 takes an EXCLUSIVE
   // lock and NOTHING can read the file while the EA runs — which is every hour of
   // a 3-month unattended demo. demo_watch.py (the live kill-criteria alerter) and
   // reconcile_demo.py (the weekly reconciliation) both read this file; the whole
   // monitoring layer of DEMO_FORWARD_PLAN §6D/§6E is dead without it. Found
   // 2026-07-16 on the VPS: even `Get-Content` was refused with "the process cannot
   // access the file because it is being used by another process".
   // rec=F per-symbol book_frac | rec=H hourly book | rec=P per-symbol position
   // (DEMO_GO_NOGO #2/#3: warm, n_stops, worst_eq, day_anchor, want/held/defer)
   string hdr = "ts,rec,sym,val,a_h,b_h,j,core_seed,n_segs,fires,lead_hold,sc_mm,unready,skipped,balance,equity,margin_level,trading,warm,n_stops,worst_eq,day_anchor,want,held,defer,snap_ts";
   if(g_fedLive)
     {
      g_teleh = FileOpen(InpTelemetryFile, FILE_READ|FILE_WRITE|FILE_SHARE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(g_teleh != INVALID_HANDLE)
        {
         if(FileSize(g_teleh) == 0)
            FileWriteString(g_teleh, hdr + "\n");
         FileSeek(g_teleh, 0, SEEK_END);
        }
     }
   else
     {
      g_teleh = FileOpen(InpTelemetryFile, FILE_WRITE|FILE_SHARE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(g_teleh != INVALID_HANDLE)
         FileWriteString(g_teleh, hdr + "\n");
     }
  }

void TelemetryHour(const long H)
  {
   if(g_teleh == INVALID_HANDLE)
      return;
   double a_h = g_orc.LastAH();
   double b_h = g_orc.LastBH();
   double j   = BOOKORC_W * a_h + (1.0 - BOOKORC_W) * b_h;
   // per-symbol book_frac rows of the last emission (broker names, pre-s)
   int n = g_orc.EmitCount();
   for(int i = 0; i < n; i++)
      FileWriteString(g_teleh, StringFormat("%I64d,F,%s,%.17g,,,,,,,,,,,,,,,,,,,,,,\n",
                      g_orc.EmitTs(i), g_orc.EmitSymbol(i), g_orc.EmitFrac(i)));
   // per-symbol POSITION rows: the last FED_Reconcile pass's want vs actually-held.
   // Raw inputs only — held is designed to sit within InpRebalBand of want, so the
   // fidelity VERDICT belongs downstream (reconcile_demo.py), not in the binary.
   // snap_ts says WHEN the pair was taken: this function can run several times per
   // Pump() while FED_Reconcile() runs once, so on a catch-up pass the same snapshot
   // is stamped onto many hours. Only rows whose snap_ts falls inside their own hour
   // are measured; the rest are stale and must NOT be scored (run 44: scoring them
   // read 96.75% "fidelity" that was pure artifact).
   for(int k = 0; k < FED_NSYM; k++)
      FileWriteString(g_teleh, StringFormat("%I64d,P,%s,,,,,,,,,,,,,,,,,,,,%.2f,%.2f,%d,%I64d\n",
                      H, g_fedTrade[k], g_fedWant[k], g_fedHeld[k],
                      (g_fedLegDefer[k] ? 1 : 0) + (g_fedUnsized[k] ? 2 : 0),
                      g_fedSnapTs));
   FileWriteString(g_teleh, StringFormat(
      "%I64d,H,,%d,%.17g,%.17g,%.17g,%.17g,%d,%I64d,%I64d,%I64d,%I64d,%I64d,%.2f,%.2f,%.2f,%d,%d,%d,%.2f,%.2f,,,,\n",
      H, n, a_h, b_h, j, g_drive.Seed(), g_drive.Segments(), g_drive.Fires(),
      g_drive.LeadHoldMinutes(), g_orc.LiveScMismatches(), g_unreadyRows,
      g_drive.SkippedBars(),
      AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoDouble(ACCOUNT_MARGIN_LEVEL),
      (g_canTrade && !g_refuse) ? 1 : 0,
      g_warm ? 1 : 0,          // #3: cold-start alarm — `trading` alone lies
      g_fedNStops,             // #2: the REAL breaker count (was deinit-only)
      FED_WorstMarkEquity(),   // the 28% kill line is worst-mark, not hourly equity
      g_fedAnchor));           // FTMO daily anchor (0 when the breaker is disarmed)
   if(g_fedLive)
      FileFlush(g_teleh);
  }

//====================================================================
// STATE PERSISTENCE (v2 blob + core-drive sidecar, atomic + fnv64)
//====================================================================
// Is this a legal AND wanted save point?
//  * The core-drive sidecar may ONLY be written at the end of a completed hour
//    cycle — minute machine idle, queues drained (CoreLiveDrive.mqh:712). The
//    g_dirtyState boundary is exactly that. OnDeinit is NOT legal: it lands
//    mid-minute, BsWriteState refuses "save with undrained queues", and the run
//    ends with a blob and no sidecar (proven on the 2026-07-16 warm-blob run).
//  * But saving EVERY simulated hour is O(n^2): the blob grows with history
//    (7.9 MB by 2025-12-31) and the full window has ~49,354 hours -> ~300h of
//    runtime instead of ~55min (measured: rate decayed as C/n).
// So: live saves at every completed hour (there n grows one day per day, the
// cost is trivial, and restart continuity depends on it). The tester saves only
// from InpSaveStateFrom onward — a few clean, legal saves at the end of the
// window, the last of which is the blob we actually want.
bool SaveDue()
  {
   if(!MQLInfoInteger(MQL_TESTER))
      return true;                                  // live: every completed hour
   if(g_saveFrom == 0)
      return false;                                 // tester: no window -> no periodic save
   return ((datetime)g_lastCompletedHour >= g_saveFrom);
  }

void SaveStateFiles()
  {
   if(!InpSaveState || StringLen(InpStateFile) == 0 || g_refuse)
      return;
   if(MQLInfoInteger(MQL_TESTER) && !InpSaveInTester)
      return;
   // Sidecar FIRST: it is the write that can legally refuse. Writing the blob
   // first (as this did) meant an illegal save point left a NEW blob paired with
   // a STALE sidecar — an incoherent pair on disk. The load-time coherence check
   // catches it and refuses to trade, but that turns a skipped save into a
   // dead EA. Ordering it this way makes an illegal save point a clean no-op.
   if(!g_bsDrive.Save(g_drive, InpStateFile + ".coredrive"))
     {
      Print("FMA3 NATIVE WARN: core-drive sidecar save skipped (blob left intact): ",
            g_bsDrive.LastError());
      return;
     }
   if(!g_bs.SaveWithCoreSignal(g_orc, g_css, InpStateFile))
      Print("FMA3 NATIVE WARN: state save failed (restart will cold-start): ",
            g_bs.LastError());
  }

//====================================================================
// FEED SEEDING (warm restart / live start: carries from real history)
//====================================================================
void SeedFromHistory()
  {
   MqlRates r[];
   for(int i = 0; i < FA_NSYM; i++)
     {
      int n = CopyRates(g_broker[i], PERIOD_M1,
                        (datetime)(g_backfillFrom - 60 * 4320),
                        (datetime)(g_backfillFrom - 60), r);
      if(n <= 0)
        {
         if(!g_fedLive)          // tester: no history in the warmup window =>
            g_fa.MarkAbsent(i);  // not-yet-born; must not gate book readiness
         continue;
        }
      MqlRates b = r[n - 1];
      g_fa.SeedSymbol(i, b.open, b.high, b.low, b.close, (int)b.spread);
      if(i >= EA_CROSS_FA0 && i < EA_CROSS_FA0 + FA_NCROSS)
        {
         double sp = (int)b.spread * g_point[i];
         g_fa.SeedCrossValue(FA_SYMS[i], b.close, b.close + sp);
         g_drive.SeedCross(i - EA_CROSS_FA0, b.close, b.close + sp);
        }
     }
  }

//====================================================================
// FEED PUMP — minute-merged CopyRates poll into BOTH consumers
//====================================================================
bool HeadReady(const int i, const long last_closed)
  {
   while(true)
     {
      while(g_buf[i].pos < g_buf[i].n)
        {
         long t = (long)g_buf[i].r[g_buf[i].pos].time;
         if((t % 60) != 0 || t > last_closed)
           {
            g_buf[i].pos++;
            continue;
           }
         return true;
        }
      if(g_from[i] > last_closed)
         return false;                        // resolved through last_closed
      // clamp to the symbol's actual first available M1 bar (tester
      // pre-cache floor; nothing exists before it, so it is resolved)
      long fd = 0;
      if(SeriesInfoInteger(g_broker[i], PERIOD_M1, SERIES_FIRSTDATE, fd)
         && fd > 0)
        {
         long fda = (fd / 60) * 60;
         if(fda > g_from[i])
           {
            g_from[i] = fda;
            if(fda - 60 > g_resolved[i])
               g_resolved[i] = fda - 60;
            if(g_from[i] > last_closed)
               return false;
           }
        }
      long to = g_from[i] + 60 * (EA_CHUNK - 1);
      if(to > last_closed)
         to = last_closed;
      int n = CopyRates(g_broker[i], PERIOD_M1, (datetime)g_from[i],
                        (datetime)to, g_buf[i].r);
      if(n < 0)
        {
         // LIVE, symbol genuinely listed: n<0 means "not downloaded yet".
         // Retry on the next pump pass; the CopyRates call itself drives the
         // fetch. A DECLARED-ABSENT symbol is the opposite case — it has no
         // data on this broker and never will, so retrying pins g_resolved[i]
         // at its -1 seed forever, which pins the min-front `safe` clock, and
         // the whole book freezes at hours=0 with no error, no CPU and no log.
         // That is precisely how the FTMO demo stalled (EURSEK, 2026-07-17/18):
         // the tester branch below already had the cure, the live path did not.
         if(g_fedLive && !FaIsExpectAbsent(i))
           {
            g_histWaits++;                    // live: a lazy download — retry later
            return false;
           }
         // Falls through here for TESTER (any symbol) and for LIVE declared-
         // absent symbols. Both mean the same thing: this range yields no bars.
         // TESTER: all symbol history is fully pre-synchronized in OnInit (the
         // "history synchronized" journal lines), so n<0 here is NEVER a pending
         // download — it means the range has no bars, e.g. a symbol not yet born
         // (SOLUSD before 2022). The SERIES_FIRSTDATE clamp above cannot rescue
         // it when the birth date is still in the future relative to modeled
         // time. Treat as an empty range and advance the cursor so this leg
         // never pins the min-front `safe` clock below backfillFrom — otherwise
         // the whole book freezes for the entire run (the full-window 2020 start
         // hit exactly this: hours=0). The leg emits not-ready rows until its
         // real first bar, matching the record engine (no pre-birth data either).
         n = 0;
        }
      g_buf[i].n = n;
      g_buf[i].pos = 0;
      g_from[i] = to + 60;
      g_resolved[i] = to;
     }
   return false;
  }

bool PushDrive(const int i, const long t, const MqlRates &rr)
  {
   int inst = FaInstOf(i);
   if(inst >= 0)
      if(!g_drive.PushBar(inst, t, rr.open, rr.high, rr.low, rr.close,
                          (int)rr.spread, g_point[i]))
        {
         RefuseLatch("core drive: " + g_drive.LastError());
         return false;
        }
   if(i >= EA_CROSS_FA0 && i < EA_CROSS_FA0 + FA_NCROSS)
     {
      double sp = (int)rr.spread * g_point[i];
      if(!g_drive.PushCross(i - EA_CROSS_FA0, t, rr.close, rr.close + sp))
        {
         RefuseLatch("core drive cross: " + g_drive.LastError());
         return false;
        }
     }
   return true;
  }

bool PollBars(const long now)
  {
   long last_closed = (now / 60) * 60 - 60;
   if(last_closed < g_backfillFrom)
      return true;
   int steps = 0;
   while(steps < InpMaxMinutesPerPass)
     {
      // safe front: minute up to which EVERY symbol's history is resolved
      long safe = last_closed;
      for(int i = 0; i < FA_NSYM; i++)
        {
         HeadReady(i, last_closed);           // refills + updates g_resolved
         if(g_resolved[i] < safe)
            safe = g_resolved[i];
        }
      long best = -1;
      for(int i = 0; i < FA_NSYM; i++)
        {
         if(g_buf[i].pos >= g_buf[i].n)
            continue;
         long t = (long)g_buf[i].r[g_buf[i].pos].time;
         if(t > safe)
            continue;
         if(best < 0 || t < best)
            best = t;
        }
      if(best < 0)
        {
         // drained to the safe front: advance both causal clocks
         if(safe >= g_backfillFrom)
           {
            if(!g_fa.AdvanceTo(safe + 60))
              {
               RefuseLatch("feed AdvanceTo: " + g_fa.LastError());
               return false;
              }
            if(!g_drive.AdvanceTo(safe + 60))
              {
               RefuseLatch("drive AdvanceTo: " + g_drive.LastError());
               return false;
              }
           }
         return true;
        }
      for(int i = 0; i < FA_NSYM; i++)
        {
         if(g_buf[i].pos >= g_buf[i].n)
            continue;
         if((long)g_buf[i].r[g_buf[i].pos].time != best)
            continue;
         MqlRates rr = g_buf[i].r[g_buf[i].pos];
         if(!g_fa.PushBar(i, best, rr.open, rr.high, rr.low, rr.close,
                          (int)rr.spread))
           {
            RefuseLatch("feed: " + g_fa.LastError());
            return false;
           }
         if(!PushDrive(i, best, rr))
            return false;
         g_buf[i].pos++;
        }
      steps++;
     }
   return true;                                // bounded pass; continue next tick
  }

//====================================================================
// HOUR CYCLE — the model law: fed[h] computed+applied at h+1h
//====================================================================
bool ApplyEmitted()
  {
   int n = g_orc.EmitCount();
   if(n == 0)
      return true;
   long cur = -1;
   for(int i = 0; i < n; i++)
     {
      long ts = g_orc.EmitTs(i);
      if(ts != cur)
        {
         for(int k = 0; k < FED_NSYM; k++)
            g_fedTgt[k] = 0.0;                 // present hour: flatten-by-omission
         cur = ts;
        }
      string sym = g_orc.EmitSymbol(i);
      if(sym == "__GRID__")
         continue;                             // all-flat sentinel: no leg
      int idx = FED_SymIndex(sym);
      if(idx < 0)
        {
         RefuseLatch("emitted symbol not in the 33-universe: " + sym);
         return false;
        }
      g_fedTgt[idx] = g_orc.EmitFrac(i);
     }
   g_fedTgtDirty = true;
   return true;
  }

bool HourCycle()
  {
   while(g_fa.H1Ready())
     {
      long H = g_fa.PeekH1Ts();
      SFaH1Row hr;
      if(!g_fa.PopH1Row(hr))
        {
         RefuseLatch("PopH1Row: " + g_fa.LastError());
         return false;
        }
      // 1. the hour's released M1 rows -> b engine (held-tgt lag law)
      while(g_fa.M1Available() > 0)
        {
         SFaM1Row r;
         if(!g_fa.PopM1Row(r))
           {
            RefuseLatch("PopM1Row: " + g_fa.LastError());
            return false;
           }
         if(!r.ready)
           {
            g_unreadyRows++;                   // cold pre-seed gap: skip-loud
            continue;
           }
         if(!g_orc.StepM1(r.ts, r.has, r.bo, r.ao, r.bc, r.ac, r.bl, r.ah,
                          r.eurq, r.swl, r.sws))
           {
            RefuseLatch("StepM1: " + g_orc.LastError());
            return false;
           }
        }
      // 2. live core products -> orchestrator (a samples + f_core rows)
      long ts;
      double eqc;
      double fc[];
      while(g_drive.Samples() > 0)
        {
         if(!g_drive.PopSample(ts, eqc) || !g_orc.LiveCoreSample(ts, eqc))
           {
            RefuseLatch("live a-sample: " + g_orc.LastError());
            return false;
           }
        }
      while(g_drive.HourRows() > 0)
        {
         long fh;
         if(!g_drive.PopHourRow(fh, fc) || !g_orc.LiveCoreAppend(fh, fc))
           {
            RefuseLatch("live f_core append: " + g_orc.LastError());
            return false;
           }
        }
      g_orc.LiveCoreAdvance(H + 3600);
      // 3. H1 signal chain (raw closes; NaN = symbol printed no bar)
      if(!g_orc.StepH1(H, hr.close))
        {
         RefuseLatch("StepH1: " + g_orc.LastError());
         return false;
        }
      if(!ApplyEmitted())                      // catch-up edge emissions
         return false;
      // 4. EARLY-EMIT hour H now — the record book applies fed[H] at
      // H+1h, which is exactly this wall instant (deferring to the
      // next H1 bar would cost one extra hour of application lag)
      long next_ts = g_fa.H1Ready() ? g_fa.PeekH1Ts() : H + 3600;
      if(!g_orc.LiveEmitStaged(next_ts))
        {
         RefuseLatch("LiveEmitStaged: " + g_orc.LastError());
         return false;
        }
      if(!ApplyEmitted())
         return false;
      TelemetryHour(H);
      g_lastCompletedHour = H;
      g_hours++;
      g_dirtyState = true;
     }
   return true;
  }

//====================================================================
// THE PUMP — guardian, feed, hour cycle, reconcile, persist
//====================================================================
void Pump()
  {
   if(g_inPump)
      return;
   g_inPump = true;

   if(g_refuse)
     {
      long now0 = (long)TimeCurrent();
      if(now0 - g_refuseLastPrint >= 3600)
        {
         Print("FMA3 NATIVE REFUSE-TO-TRADE (latched): ", g_refuseWhy);
         g_refuseLastPrint = now0;
        }
      g_inPump = false;
      return;
     }

   long now = (long)TimeCurrent();
   // compute clock vs wall clock: trade only when caught up (warmup
   // history must never be traded at today's prices)
   bool synced = (g_lastCompletedHour >= (now / 3600) * 3600 - 3600);

   // HEARTBEAT (GO_NOGO #4): a weekend/holiday HOLD and a silent FREEZE both
   // just stop moving on the telemetry `ts`. This surfaces them.
   //
   // CADENCE is gated on GetTickCount64() (REAL monotonic ms), NOT on
   // TimeCurrent(): TimeCurrent is the last-quote time and FREEZES when the
   // feed is quiet, so a TimeCurrent-gated beat would go silent during the
   // very total-feed-death it must report. OnTimer (EventSetTimer(5)) fires
   // every 5 real seconds with or without ticks, so a real-time gate always
   // beats.
   //
   // The line prints REAL wall time (TimeGMT) AND feed time (TimeCurrent) side
   // by side. Their divergence is the freeze signal that needs NO assumption
   // about CopyRates' return convention:
   //   real advancing, feed advancing, lag growing        -> weekend/holiday HOLD
   //   real advancing, feed FROZEN                         -> feed dead / disconnected
   //   real advancing, feed advancing, hours climbing, lag~0 -> caught up
   // hours/histWaits deltas corroborate and let us READ this broker's
   // convention (n==0 keeps histWaits flat through a hold; n<0 climbs it) —
   // reported, never relied on alone. Live only (g_fedLive) — a tester
   // identity run never reaches here and is byte-for-byte unchanged. Placed
   // before PollBars so it still beats when a stall makes PollBars a no-op.
   // Pure report: no compute, state, or sizing is touched.
   if(InpHeartbeatSec > 0 && g_fedLive)
     {
      ulong hbTick = GetTickCount64();
      if(hbTick - g_hbLastTick >= (ulong)InpHeartbeatSec * 1000)
        {
         double lag_h = (g_lastCompletedHour > 0)
                        ? (now - g_lastCompletedHour) / 3600.0 : -1.0;
         PrintFormat("FMA3 NATIVE HB: real=%s feed=%s compute=%s lag=%.1fh "
                     "hours=%I64d(+%I64d) histWaits=%I64d(+%I64d) synced=%s",
                     TimeToString(TimeGMT(), TIME_DATE|TIME_MINUTES),
                     TimeToString((datetime)now, TIME_DATE|TIME_MINUTES),
                     TimeToString((datetime)g_lastCompletedHour, TIME_DATE|TIME_MINUTES),
                     lag_h, g_hours, g_hours - g_hbLastHours,
                     g_histWaits, g_histWaits - g_hbLastHistWait,
                     synced ? "yes" : "no");
         g_hbLastTick     = hbTick;
         g_hbLastHours    = g_hours;
         g_hbLastHistWait = g_histWaits;
        }
     }

   // [SEAM G] FTMO daily breaker BEFORE anything (inert at x<=0)
   if(g_canTrade && synced && !FED_GuardianPass())
     {
      g_inPump = false;
      return;
     }

   if(!PollBars(now))
     {
      g_inPump = false;
      return;
     }
   if(!HourCycle())
     {
      g_inPump = false;
      return;
     }

   // b-sleeve balance sanity — the guard CSatEquityNative lacks (the core has
   // its own at CoreSim.mqh:237). A non-finite or non-positive satellite
   // balance is "impossible in the anchor": the 0.5 stop-out floors equity
   // above zero in every valid run, so this can only be a corrupt mark — as
   // EURSEK's absent 0.0-price leg was, before it compounded to -inf and
   // poisoned the blob. Refuse BEFORE the save below (g_refuse blocks
   // SaveStateFiles), so the bad state never reaches disk. Runs in backfill
   // too — that is when EURSEK struck. Never fires on a healthy book, so it is
   // parity- and tester-neutral (a valid identity run is byte-for-byte
   // unchanged); it only diverges on an already-invalid run.
   double bBal = g_orc.BBalance();
   if(!MathIsValidNumber(bBal) || bBal <= 0.0)
     {
      RefuseLatch(StringFormat("b-sleeve balance non-finite/non-positive (%.2f)"
                               " — corrupt mark; refusing before save", bBal));
      g_inPump = false;
      return;
     }

   synced = (g_lastCompletedHour >= (now / 3600) * 3600 - 3600);
   if(g_canTrade && synced && !g_refuse)
      FED_Reconcile();                         // re-size every M1 (RECON-4 law)

   // Persist at the completed-hour boundary — the only legal save point for the
   // core-drive sidecar. SaveDue() keeps this every-hour live but end-of-window
   // only in the tester (see its comment: legality vs O(n^2)).
   if(g_dirtyState && SaveDue())
     {
      SaveStateFiles();
      g_dirtyState = false;
     }
   g_inPump = false;
  }

//====================================================================
// INIT
//====================================================================
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagicBase);
   g_fedLive  = !MQLInfoInteger(MQL_TESTER);
   g_canTrade = (!g_fedLive) || InpAllowLiveTrading;

   if(_Period != PERIOD_M1)
     {
      Print("FMA3 NATIVE FATAL: attach to an M1 chart (24/7 clock law). Aborting.");
      return(INIT_FAILED);
     }
   if(_Symbol != "BTCUSD")
      Print("FMA3 NATIVE WARN: clock chart is '", _Symbol,
            "' — BTCUSD M1 is the deployment law (24/7 clock).");

   if(g_canTrade
      && (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)
         != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     {
      Print("FMA3 NATIVE FATAL: trading enabled but the account is not HEDGING ",
            "(one net position + one magic per symbol). Aborting.");
      return(INIT_FAILED);
     }
   if(!g_canTrade)
      Print("FMA3 NATIVE: InpAllowLiveTrading=false on a live chart — ",
            "COMPUTE+LOG ONLY, zero OrderSend. Set the input true to trade.");

   // 33-universe + broker map (BookReplay tables; the CSV loader is NOT used)
   if(!FED_ParseSymbolMap())
      return(INIT_FAILED);
   FED_InitUniverse();
   for(int i = 0; i < FED_NSYM; i++)
      if(!SymbolSelect(g_fedTrade[i], true))
         Print("FMA3 NATIVE WARN: symbol '", g_fedTrade[i],
               "' not available - leg will not size/trade.");
   string crosses[8] = {InpEURUSD, InpEURJPY, InpEURGBP, InpEURCHF,
                        InpEURNZD, InpEURCAD, InpEURNOK, InpEURSEK};
   for(int i = 0; i < 8; i++)
      if(!SymbolSelect(crosses[i], true))
         Print("FMA3 NATIVE WARN: EUR cross '", crosses[i], "' not available.");
   SymbolSelect(_Symbol, true);
   for(int i = 0; i < FED_NSYM; i++)
      g_fedLegDefer[i] = false;

   // --- FEED broker names: apply InpV34SymbolMap to the FEED too -----------
   // MUST run after FED_ParseSymbolMap() (above) and BEFORE g_fa.Init() (below),
   // which snapshots the names. Until 2026-07-17 the map reached only the EXEC
   // side (FED_MapSymbol -> g_fedTrade), while BOTH feed tables — this g_broker[]
   // and FeedAssembler's own m_broker[] — were built straight from FaBrokerName,
   // hardcoded to the IC universe. On a broker that renames (FTMO: DE40 ->
   // GER40.cash, XTIUSD -> USOIL.cash, ...) the feed asked for names that do not
   // exist, so FeedAssembler::Init hard-failed and the EA could not start at all.
   // Compose the same way the exec side does — FaBrokerName first (model -> IC
   // canonical: DAX->DE40, USA500->US500), then the map — so BOTH sides key off
   // the SAME canonical names and one InpV34SymbolMap drives everything.
   // Empty map => FED_MapSymbol is identity => IC is bit-for-bit unchanged.
   for(int i = 0; i < FA_NSYM; i++)
      FaSetBrokerOverride(i, FED_MapSymbol(FaBrokerName(FA_SYMS[i])));

   // --- declare the symbols this broker genuinely lacks ---------------------
   // Everything NOT declared still hard-fails in FeedAssembler::Init, so a bad
   // map cannot degrade into silent dark legs. Validate the declaration itself:
   // a name that does not match a resolved feed symbol is a typo, and a symbol
   // that IS listed must never be declared absent — both would arm the wrong leg.
   for(int i = 0; i < FA_NSYM; i++)
      FaSetExpectAbsent(i, false);
   if(StringLen(InpExpectAbsent) > 0)
     {
      string want[];
      int nw = StringSplit(InpExpectAbsent, ';', want);
      for(int k = 0; k < nw; k++)
        {
         string w = want[k];
         StringTrimLeft(w); StringTrimRight(w);
         if(StringLen(w) == 0)
            continue;
         bool hit = false;
         for(int i = 0; i < FA_NSYM; i++)
            if(FaResolveBroker(i) == w)
              {
               if(SymbolSelect(w, true))
                 {
                  PrintFormat("FMA3 NATIVE FATAL: InpExpectAbsent lists '%s' but this "
                              "broker DOES list it. Remove it — declaring a live symbol "
                              "absent would silently dark a real leg.", w);
                  return(INIT_FAILED);
                 }
               FaSetExpectAbsent(i, true);
               hit = true;
               PrintFormat("FMA3 NATIVE: '%s' declared EXPECT-ABSENT on this broker.", w);
              }
         if(!hit)
           {
            PrintFormat("FMA3 NATIVE FATAL: InpExpectAbsent lists '%s', which is not a "
                        "resolved feed symbol. Typo, or it needs an InpV34SymbolMap entry.", w);
            return(INIT_FAILED);
           }
        }
     }

   // --- compute chain --------------------------------------------------
   if(!g_orc.Init(BOOKORC_W, 10000.0))
     {
      Print("FMA3 NATIVE FATAL: orchestrator Init: ", g_orc.LastError());
      return(INIT_FAILED);
     }
   g_orc.EnableLiveCore();

   if(!g_fa.Init(true))                        // digits gate REFUSES on drift
     {
      Print("FMA3 NATIVE FATAL: feed assembler Init: ", g_fa.LastError());
      return(INIT_FAILED);
     }

   g_sig.Configure();
   if(!g_trig.Configure(7, 9, EA_TRIG_SLOT, 0.25, (1.0 / 7.0) / 1.75, 2.5, 5))
     {
      Print("FMA3 NATIVE FATAL: trigger Configure: ", g_trig.LastError());
      return(INIT_FAILED);
     }
   g_css.Attach(&g_sig, &g_trig);
   if(!g_drive.Init(&g_sig, &g_trig))
     {
      Print("FMA3 NATIVE FATAL: core drive Init: ", g_drive.LastError());
      return(INIT_FAILED);
     }

   // --- feed poll tables -------------------------------------------------
   for(int i = 0; i < FA_NSYM; i++)
     {
      g_broker[i] = FaResolveBroker(i);   // same map the FeedAssembler resolved
      g_point[i]  = SymbolInfoDouble(g_broker[i], SYMBOL_POINT);
      g_buf[i].pos = 0;
      g_buf[i].n = 0;
      g_resolved[i] = -1;
     }

   // --- tester periodic-save window ----------------------------------------
   g_saveFrom = 0;
   if(StringLen(InpSaveStateFrom) > 0)
     {
      g_saveFrom = StringToTime(InpSaveStateFrom);
      // A typo here would silently skip every save and waste the whole run, so
      // refuse to start rather than discover it at deinit.
      if(g_saveFrom == 0)
        {
         Print("FMA3 NATIVE FATAL: InpSaveStateFrom unparseable: '",
               InpSaveStateFrom, "' (expected e.g. \"2025.12.30 00:00\")");
         return(INIT_FAILED);
        }
      PrintFormat("FMA3 NATIVE: tester state-save window opens at %s",
                  TimeToString(g_saveFrom, TIME_DATE | TIME_MINUTES));
     }

   // --- warm start (blob + sidecar) or cold start --------------------------
   g_warm = false;
   if(StringLen(InpStateFile) > 0 && FileIsExist(InpStateFile, FILE_COMMON))
     {
      if(!g_bs.LoadWithCoreSignal(g_orc, g_css, InpStateFile))
         RefuseLatch("STATE BLOB: " + g_bs.RefuseReason());
      else
        {
         string side = InpStateFile + ".coredrive";
         if(!FileIsExist(side, FILE_COMMON))
            RefuseLatch("state blob present but core-drive sidecar missing: " + side);
         else if(!g_bsDrive.Load(g_drive, side))
            RefuseLatch("CORE-DRIVE SIDECAR: " + g_bsDrive.RefuseReason());
         else
           {
            long oj = g_orc.LastEmitHour();
            long dj = g_drive.LastFlushHour();
            if(dj > oj || dj < oj - 86400)
               RefuseLatch(StringFormat("state incoherence: core-drive hour %I64d "
                                        "vs book hour %I64d", dj, oj));
            else
              {
               g_warm = true;
               g_lastCompletedHour = oj;
               g_backfillFrom = oj + 3600;
               PrintFormat("FMA3 NATIVE WARM START: blob validated (j=%.17g at hour %I64d, "
                           "rel_jump=%.3g); resuming from %s",
                           g_bs.JRestored(), g_bs.JHour(), g_bs.RelJump(),
                           TimeToString((datetime)g_backfillFrom, TIME_DATE|TIME_MINUTES));
              }
           }
        }
     }
   if(!g_warm && !g_refuse)
     {
      if(!g_drive.ColdStart(10000.0))
        {
         Print("FMA3 NATIVE FATAL: core drive ColdStart: ", g_drive.LastError());
         return(INIT_FAILED);
        }
      if(!g_fedLive)
         g_backfillFrom = (long)D'2020.01.01'; // tester: from the pre-cache floor
      else
         g_backfillFrom = ((long)TimeCurrent() / 3600) * 3600 + 3600; // next hour
      PrintFormat("FMA3 NATIVE COLD START (%s): grid from %s — indicator warmup "
                  "period, targets are computed but the catch-up gate holds sizing "
                  "until the compute clock reaches the wall clock.",
                  g_fedLive ? "live" : "tester",
                  TimeToString((datetime)g_backfillFrom, TIME_DATE|TIME_MINUTES));
     }
   // A declared-absent leg never prints a bar on this broker, so its feed
   // price slots keep the 0.0 seed for the whole run. The satellite marks
   // open lots on lots!=0 alone (SatEquityNative.mqh section 4) — never on
   // has_bar — so any position the warm blob restored on such a leg is
   // marked to ZERO on the first stepped minute. On FTMO that is a carried
   // +2.23 EURSEK @ 10.803970 => -2,409,285 EUR against a 455,280 balance:
   // instant negative equity, stop-out, and because sizing scales with
   // balance the sign inversion compounds to -inf. Drop the position: the
   // leg cannot be priced, closed or traded here, so flat is the only
   // coherent state. MUST run after BOTH the warm and cold branches so no
   // restore path can re-arm it.
   if(!g_refuse)
      for(int i = 0; i < FA_NSYM; i++)
         if(FaIsExpectAbsent(i) && g_orc.BForceFlatSymbol(FA_SYMS[i]))
            PrintFormat("FMA3 NATIVE: SAT '%s' declared absent -> restored b "
                        "position DROPPED (leg is unpriceable/untradeable on "
                        "this broker; its carried P&L is forfeit).", FA_SYMS[i]);
   for(int i = 0; i < FA_NSYM; i++)
     {
      g_from[i] = g_backfillFrom;
      g_resolved[i] = g_backfillFrom - 60;
     }
   if(!g_refuse)
      SeedFromHistory();

   // --- decisions log (verbatim FableBook block, native filename) ----------
   if(InpLog)
     {
      string hdr[11] = {"time", "symbol", "event", "net_frac", "want", "held",
                        "after", "balance", "equity", "margin_level", "reserved"};
      if(g_fedLive)
        {
         g_fedLogh = FileOpen(InpDecisionsFile,
                              FILE_READ|FILE_WRITE|FILE_SHARE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
         if(g_fedLogh != INVALID_HANDLE)
           {
            if(FileSize(g_fedLogh) == 0)
               FileWrite(g_fedLogh, hdr[0], hdr[1], hdr[2], hdr[3], hdr[4],
                         hdr[5], hdr[6], hdr[7], hdr[8], hdr[9]);
            FileSeek(g_fedLogh, 0, SEEK_END);
           }
        }
      else
        {
         g_fedLogh = FileOpen(InpDecisionsFile,
                              FILE_WRITE|FILE_SHARE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
         if(g_fedLogh != INVALID_HANDLE)
            FileWrite(g_fedLogh, hdr[0], hdr[1], hdr[2], hdr[3], hdr[4],
                      hdr[5], hdr[6], hdr[7], hdr[8], hdr[9]);
        }
     }
   TeleOpen();

   PrintFormat("FMA3 NATIVE init: s=%.2f initial=%.0f marginCap=%.2f band=%.2f "
               "dailyStopX=%.2f magicBase=%d symbols=%d trade=%s warm=%s refuse=%s",
               InpScale, InpInitial, InpMarginCap, InpRebalBand, InpDailyStopX,
               (int)InpMagicBase, FED_NSYM,
               g_canTrade ? "ON" : "OFF(compute-only)",
               g_warm ? "yes" : "cold",
               g_refuse ? ("YES: " + g_refuseWhy) : "no");

   EventSetTimer(5);                            // live lazy-history poll cadence
   return(INIT_SUCCEEDED);
  }

//====================================================================
// DEINIT
//====================================================================
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_dirtyState)
      SaveStateFiles();
   if(g_fedLogh != INVALID_HANDLE)
      FileClose(g_fedLogh);
   if(g_teleh != INVALID_HANDLE)
      FileClose(g_teleh);
   PrintFormat("FMA3 NATIVE deinit: hours=%I64d segs=%d fires=%I64d "
               "lead_hold=%I64d sc_mm=%I64d unready=%I64d skipped=%I64d "
               "split=%d rejects=%d stops=%d final_eq=%.2f refuse=%s",
               g_hours, g_drive.Segments(), g_drive.Fires(),
               g_drive.LeadHoldMinutes(), g_orc.LiveScMismatches(),
               g_unreadyRows, g_drive.SkippedBars(),
               (int)g_fedNSplit, (int)g_fedNReject, g_fedNStops,
               AccountInfoDouble(ACCOUNT_EQUITY),
               g_refuse ? g_refuseWhy : "no");
  }

//====================================================================
// MAIN LOOP — pump on every new M1 clock bar + on the 5 s timer
//====================================================================
void OnTick()
  {
   datetime bt = iTime(_Symbol, PERIOD_M1, 0);
   if(bt == g_lastM1Bar && !g_fedPendExec)
      return;
   g_lastM1Bar = bt;
   Pump();
  }

void OnTimer()
  {
   Pump();
  }
//+------------------------------------------------------------------+
