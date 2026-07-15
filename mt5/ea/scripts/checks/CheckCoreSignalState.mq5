//+------------------------------------------------------------------+
//| CheckCoreSignalState.mq5 — the version-2 warm-blob gate for the   |
//| folded LIVE Core signal chain (UNIT B / S2 warm-blob completeness)|
//|                                                                   |
//| Exercises CBookState::SaveWithCoreSignal / LoadWithCoreSignal via |
//| the CCoreSignalState peer (Book/CoreSignalState.mqh), over a real |
//| CCoreSignal + CCoreTrigger driven far enough that the XAU         |
//| Donchian 50/100 breach flags LATCH (b50==+1, b100==+1). Then:     |
//|   T1  v2 Save OK (atomic tmp+FileMove into Common Files).         |
//|   T2  v2 Load into FRESH objects OK (Ready(), no refuse latch).   |
//|   T3  ROUND-TRIP: restored CCoreSignal.GetState() and             |
//|       CCoreTrigger.GetState() BITWISE identical to the saved.     |
//|   T4  COMPLETENESS: the blob carries the two UNBOUNDED Donchian    |
//|       breach flags EXPLICITLY and they are LATCHED (b50/b100==1),  |
//|       so they are load-bearing (not reconstructible from a ring). |
//|   T5  NEGATIVE CONTROL (ring-rescan insufficiency): a COLD sig     |
//|       (Configure only, no history) has b50/b100==0 — its state    |
//|       DIFFERS from the restored state; the restored state matches  |
//|       the saved. Proves the flags MUST be carried, not rescanned. |
//|   T6  TORN/TAMPER: a payload bit-flip (stale fnv) must REFUSE the  |
//|       whole v2 load (the RECON-8f checksum guard is intact on the  |
//|       folded envelope).                                           |
//|                                                                   |
//| Terminal Print output must end with "CheckCoreSignalState: ALL    |
//| PASS".                                                            |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Book/CoreSignalState.mqh>

#define CCS_FILE     "FMA3_coresignalstate_check.json"
#define CCS_FILE_TMP "FMA3_coresignalstate_check_tamper.json"

int g_fail = 0;

void Expect(const bool ok, const string what)
  {
   if(!ok)
     {
      g_fail++;
      Print("CheckCoreSignalState FAIL: ", what);
     }
  }

//------------------------------------------------------------------//
// Minimal BookState peer: a trivial one-field whole-book ledger     //
// (this gate targets the FOLDED coresignal block, not the S1 ledger |
// — that is CheckBookState's job). Round-trips one double and emits  |
// a benign continuity block that passes the guard unchanged.        |
//------------------------------------------------------------------//
class CMiniPeer
  {
private:
   double            m_x;
   string            m_err;
public:
                     CMiniPeer() { m_x = 0.0; m_err = ""; }
   void              Init(const double x) { m_x = x; m_err = ""; }
   string            LastError(void) const { return m_err; }

   bool              BsWriteState(CBookStateWriter &w)
     {
      w.K("mini");
      w.D(m_x);
      return true;
     }
   bool              BsSetState(CBookStateTok &tk)
     {
      if(!tk.Key("mini") || !tk.NumVal(m_x))
        {
         m_err = "mini restore: " + tk.Err();
         return false;
        }
      return true;
     }
   bool              BsContinuity(SBookStateContinuity &c)
     {
      c.have    = false;
      c.j_hour  = -1;
      c.a_h     = 1.0;
      c.b_h     = 1.0;
      c.w       = 0.5;
      c.j       = 1.0;
      c.a_first = 0.0;
      c.b_first = 0.0;
      return true;
     }
  };

//------------------------------------------------------------------//
// Drive a CCoreSignal far enough that XAU Donchian 50/100 latch.    //
// One XAU bar per day, monotone-up daily mid => every rollover past |
// the 100-day window prints m >= rolling max => b50=b100=+1.        |
//------------------------------------------------------------------//
void DriveSig(CCoreSignal &sig, const int ndays)
  {
   long base = 1577923200;                 // 2020-01-02 00:00:00 UTC
   for(int d = 0; d < ndays; d++)
     {
      long ts  = base + (long)d * 86400 + 12 * 3600;   // 12:00 each day
      double mid = 1800.0 + 2.0 * (double)d;           // monotone ramp
      sig.StepBar(CS_I_XAUUSD, ts, mid, mid);
     }
  }

//------------------------------------------------------------------//
// Drive a CCoreTrigger a few days so its segment cursor / slot      //
// day+carry rings hold non-trivial state.                          |
//------------------------------------------------------------------//
void DriveTrig(CCoreTrigger &trig)
  {
   long base = 1577923200;
   trig.BeginSegment(10000.0, base / 86400);
   bool fired = false;
   for(int d = 0; d < 8; d++)
     {
      long ts = base + (long)d * 86400 + 15 * 3600;
      trig.CheckDay(ts, fired);
      trig.OnLegBar(0, ts, 5000.0 + 30.0 * d);
      trig.OnLegBar(1, ts, 5000.0 - 10.0 * d);
     }
  }

void OnStart()
  {
   Print("=== CheckCoreSignalState (v2 warm-blob fold) ===");

   //--- build + drive the live objects ---------------------------------
   CCoreSignal  sig;
   sig.Configure();
   DriveSig(sig, 130);

   CCoreTrigger trig;
   int leg_slot[2];
   leg_slot[0] = 0;
   leg_slot[1] = 1;
   Expect(trig.Configure(2, 2, leg_slot, 0.60, 0.20, 3.0, 5),
          "trigger Configure: " + trig.LastError());
   DriveTrig(trig);

   string saved_sig  = sig.GetState();
   string saved_trig = trig.GetState();

   //--- T4 completeness: the two unbounded flags are present + latched -
   Expect(StringFind(saved_sig, "\"b50\": 1")  >= 0,
          "b50 not latched to +1 in blob (breach did not fire)");
   Expect(StringFind(saved_sig, "\"b100\": 1") >= 0,
          "b100 not latched to +1 in blob (breach did not fire)");

   //--- T1 save v2 ------------------------------------------------------
   CMiniPeer        peerA;
   peerA.Init(1234.5);
   CCoreSignalState csA;
   csA.Attach(GetPointer(sig), GetPointer(trig));
   CBookState bsA;
   Expect(bsA.SaveWithCoreSignal(peerA, csA, CCS_FILE),
          "T1 v2 Save: " + bsA.LastError());

   //--- T2 load v2 into FRESH objects -----------------------------------
   CCoreSignal  sig2;
   sig2.Configure();
   CCoreTrigger trig2;
   Expect(trig2.Configure(2, 2, leg_slot, 0.60, 0.20, 3.0, 5),
          "trig2 Configure: " + trig2.LastError());
   CMiniPeer        peerB;
   peerB.Init(0.0);
   CCoreSignalState csB;
   csB.Attach(GetPointer(sig2), GetPointer(trig2));
   CBookState bsB;
   bool loaded = bsB.LoadWithCoreSignal(peerB, csB, CCS_FILE);
   Expect(loaded, "T2 v2 Load: " + bsB.LastError());
   Expect(bsB.Ready(), "T2 Ready() false after load");

   //--- T3 bitwise round-trip ------------------------------------------
   Expect(sig2.GetState()  == saved_sig,  "T3 CCoreSignal state not bit-identical");
   Expect(trig2.GetState() == saved_trig, "T3 CCoreTrigger state not bit-identical");

   //--- T5 negative control: cold rescan is insufficient ---------------
   CCoreSignal cold;
   cold.Configure();
   Expect(cold.GetState() != saved_sig,
          "T5 cold sig state must DIFFER from restored (else carry moot)");
   Expect(StringFind(cold.GetState(), "\"b50\": 0")  >= 0,
          "T5 cold sig b50 must be 0 (no history)");
   Expect(sig2.GetState() == saved_sig,
          "T5 restored sig must equal saved (carry is authoritative)");

   //--- T6 torn/tamper: bit-flip one payload byte, keep stale fnv -------
     {
      int fh = FileOpen(CCS_FILE, FILE_READ | FILE_BIN | FILE_COMMON);
      Expect(fh != INVALID_HANDLE, "T6 reopen saved file");
      int n = (int)FileSize(fh);
      uchar buf[];
      FileReadArray(fh, buf, 0, n);
      FileClose(fh);
      // flip a byte inside the payload (well before the trailer)
      int pos = n / 2;
      buf[pos] = (uchar)(buf[pos] == '1' ? '2' : '1');
      int wh = FileOpen(CCS_FILE_TMP, FILE_WRITE | FILE_BIN | FILE_COMMON);
      Expect(wh != INVALID_HANDLE, "T6 open tamper file");
      FileWriteArray(wh, buf, 0, n);
      FileClose(wh);

      CCoreSignal  sig3;  sig3.Configure();
      CCoreTrigger trig3; trig3.Configure(2, 2, leg_slot, 0.60, 0.20, 3.0, 5);
      CMiniPeer    peerC; peerC.Init(0.0);
      CCoreSignalState csC;
      csC.Attach(GetPointer(sig3), GetPointer(trig3));
      CBookState bsC;
      bool bad = bsC.LoadWithCoreSignal(peerC, csC, CCS_FILE_TMP);
      Expect(!bad, "T6 tampered v2 blob LOADED (checksum guard failed)");
      Expect(bsC.RefuseToTrade(), "T6 refuse latch not set on tamper");
      Print("CheckCoreSignalState T6 refuse: ", bsC.RefuseReason());
     }

   if(g_fail == 0)
      Print("CheckCoreSignalState: ALL PASS");
   else
      Print("CheckCoreSignalState: ", g_fail, " FAILURE(S)");
  }
//+------------------------------------------------------------------+
