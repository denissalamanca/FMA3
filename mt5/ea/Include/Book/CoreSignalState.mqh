//+------------------------------------------------------------------+
//| Book/CoreSignalState.mqh — CCoreSignalState: the version-2 warm-  |
//| blob peer that folds the LIVE Core signal chain into CBookState.  |
//|                                                                   |
//| WHY (UNIT B / S2 warm-blob completeness): CBookState's v1 blob    |
//| carries the whole-book replay ledger but NOT the live Core target |
//| source. The live chain adds two Class-S (unbounded-history)       |
//| objects whose future output depends on state that a cold restart  |
//| CANNOT reconstruct from a bounded ring rescan:                    |
//|   * CCoreSignal — 8 daily-mid ring series + BOTH XAU Donchian     |
//|     last-breach flags (b50/b100; formally UNBOUNDED, ffill from   |
//|     2020 — a persisted breach latches the sizing until the next   |
//|     breach, so it MUST be carried EXPLICITLY) + defer_reopen      |
//|     holds + current-day coefficients;                             |
//|   * CCoreTrigger — the causal band/harvest segment detector:      |
//|     slot-equity cursor, seed, seg_start_day, per-slot day/carry   |
//|     rings, telemetry.                                             |
//|                                                                   |
//| This wrapper is the TCs peer for CBookState::SaveWithCoreSignal / |
//| LoadWithCoreSignal. It reuses each object's OWN proven, bit-zero  |
//| (RECON-8g) GetState/SetState — this header adds ZERO new numerics,|
//| only the two-object JSON envelope + strict parse. Attach the live |
//| objects (owned by the EA) before Save/Load.                       |
//+------------------------------------------------------------------+
#ifndef BOOK_CORESIGNALSTATE_MQH
#define BOOK_CORESIGNALSTATE_MQH

#include <Core/CoreSignal.mqh>
#include <Book/BookState.mqh>

class CCoreSignalState
  {
private:
   CCoreSignal      *m_sig;
   CCoreTrigger     *m_trig;
   string            m_err;

public:
                     CCoreSignalState() { m_sig = NULL; m_trig = NULL; m_err = ""; }

   void              Attach(CCoreSignal *sig, CCoreTrigger *trig)
     {
      m_sig  = sig;
      m_trig = trig;
     }

   string            LastError(void) const { return m_err; }

   //---------------------------------------------------------------//
   // BsWriteCoreSignal — emit {"sig": <CCoreSignal.GetState>,       //
   //                           "trig": <CCoreTrigger.GetState>}     //
   //---------------------------------------------------------------//
   bool              BsWriteCoreSignal(CBookStateWriter &w)
     {
      if(m_sig == NULL || m_trig == NULL)
        {
         m_err = "CoreSignalState not attached";
         return false;
        }
      w.Raw("{\"sig\": ");
      w.Raw(m_sig.GetState());
      w.Raw(", \"trig\": ");
      w.Raw(m_trig.GetState());
      w.Raw("}");
      return true;
     }

   //---------------------------------------------------------------//
   // BsSetCoreSignal — strict parse + restore into the live objects //
   // via their own SetState (each validates its own field schema). //
   //---------------------------------------------------------------//
   bool              BsSetCoreSignal(CBookStateTok &tk)
     {
      if(m_sig == NULL || m_trig == NULL)
        {
         m_err = "CoreSignalState not attached";
         return false;
        }
      if(!tk.Eat('{') || !tk.Key("sig"))
        {
         m_err = "coresignal: expected {\"sig\": (" + tk.Err() + ")";
         return false;
        }
      string sig_obj;
      if(!tk.ObjRaw(sig_obj))
        {
         m_err = "coresignal sig object: " + tk.Err();
         return false;
        }
      if(!m_sig.SetState(sig_obj))
        {
         m_err = "CCoreSignal.SetState: " + m_sig.LastError();
         return false;
        }
      if(!tk.CommaKey("trig"))
        {
         m_err = "coresignal: expected , \"trig\": (" + tk.Err() + ")";
         return false;
        }
      string trig_obj;
      if(!tk.ObjRaw(trig_obj))
        {
         m_err = "coresignal trig object: " + tk.Err();
         return false;
        }
      if(!m_trig.SetState(trig_obj))
        {
         m_err = "CCoreTrigger.SetState: " + m_trig.LastError();
         return false;
        }
      if(!tk.Eat('}'))
        {
         m_err = "coresignal: expected closing } (" + tk.Err() + ")";
         return false;
        }
      m_err = "";
      return true;
     }
  };

#endif // BOOK_CORESIGNALSTATE_MQH
