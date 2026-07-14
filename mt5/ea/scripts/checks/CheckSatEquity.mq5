//+------------------------------------------------------------------+
//| CheckSatEquity.mq5 — compile/smoke gate for                      |
//| Sat/SatEquityNative.mqh.  NO trading functions.                  |
//|                                                                  |
//| Synthetic 7-bar scenario on 3 active symbols (EURUSD k=14,       |
//| USDJPY k=24, XAUUSD k=27) exercising every branch of the b_h     |
//| step: open, rebalance-band skip, reduce, sign flip (both fill    |
//| branches in one bar), margin-cap shrink + post-shrink re-floor,  |
//| swap accrual, min-lot zeroing close, has_bar=false carry, and    |
//| the joint stop-out (bar 5 -> both marks overwritten with the     |
//| liquidated balance).                                             |
//|                                                                  |
//| PYTHON GOLDEN generated 2026-07-14 by scratchpad                 |
//| gen_check_golden.py running bh_stepper.BHAccountStepper (the     |
//| bitwise-proven reference) on the EXACT literal inputs below —    |
//| the input tables here and in the generator must stay identical.  |
//| Every comparison is EXACT (==, bitwise); expected terminal       |
//| output ends with "CheckSatEquity: FAILURES=0".                   |
//|                                                                  |
//| Also gates the state JSON contract: GetState/SetState roundtrip, |
//| a warm-start split after bar 3 (must be bit-identical to the     |
//| continuous run), and SetState of a PYTHON-formatted state blob   |
//| (json.dumps repr floats) driving bars 4-6.                       |
//+------------------------------------------------------------------+
#property script_show_inputs false
#include <Sat/SatEquityNative.mqh>

#define CSE_NBARS 7
#define CSE_E 14   // EURUSD
#define CSE_U 24   // USDJPY
#define CSE_X 27   // XAUUSD

const double CSE_EURQ_USD = 0.91;
const double CSE_EURQ_JPY = 0.0084;

// per bar: {bo, ao, bc, ac, bl, ah} — keep identical to gen_check_golden.py
const double CSE_PX_E[CSE_NBARS][6] =
  {
     {1.1000, 1.1002, 1.1010, 1.1012, 1.0995, 1.1015},
     {1.1010, 1.1012, 1.1005, 1.1007, 1.1000, 1.1014},
     {1.1005, 1.1007, 1.1008, 1.1010, 1.0998, 1.1012},
     {1.1008, 1.1010, 1.1006, 1.1008, 1.1002, 1.1013},
     {1.1006, 1.1008, 1.1004, 1.1006, 1.1000, 1.1010},
     {1.1004, 1.1006, 1.1005, 1.1007, 1.1001, 1.1010},
     {1.1005, 1.1007, 1.1006, 1.1008, 1.1002, 1.1011}
  };
const double CSE_PX_U[CSE_NBARS][6] =
  {
     {110.00, 110.02, 109.90, 109.92, 109.80, 110.10},
     {109.90, 109.92, 109.95, 109.97, 109.85, 110.00},
     {109.95, 109.97, 110.05, 110.07, 109.90, 110.12},
     {110.05, 110.07, 110.00, 110.02, 109.95, 110.10},
     {110.05, 110.07, 110.00, 110.02, 109.95, 110.10}, // has=false (carry)
     {110.00, 110.02, 109.98, 110.00, 109.90, 110.08},
     {109.98, 110.00, 109.99, 110.01, 109.94, 110.06}
  };
const double CSE_PX_X[CSE_NBARS][6] =
  {
     {1600.0, 1600.5, 1602.0, 1602.5, 1598.0, 1604.0},
     {1602.0, 1602.5, 1601.0, 1601.5, 1600.0, 1603.0},
     {1601.0, 1601.5, 1603.0, 1603.5, 1599.5, 1605.0},
     {1603.0, 1603.5, 1602.0, 1602.5, 1600.5, 1604.5},
     {1602.0, 1602.5, 1601.5, 1602.0, 1600.0, 1603.0},
     {1601.0, 1601.5, 700.0, 700.5, 650.0, 702.0},     // crash -> stop-out
     {700.0, 700.5, 700.2, 700.7, 699.0, 701.5}
  };
const double CSE_TGT[CSE_NBARS][3] =   // {E, U, X}
  {
     {0.5, -0.4, 0.0},
     {0.5, -0.4, 0.0},       // rebalance-band skip
     {0.25, 0.3, 25.0},      // reduce + sign flip + margin-cap shrink
     {0.25, 0.3, 25.0},      // swap minute
     {0.0001, 0.3, 20.0},    // min-lot close (E); U has=false carry
     {0.0, 0.3, 20.0},       // X crash -> joint stop-out
     {0.0, 0.0, 0.0}
  };
const bool CSE_HAS[CSE_NBARS][3] =
  {
     {true, true, true},
     {true, true, true},
     {true, true, true},
     {true, true, true},
     {true, false, true},
     {true, true, true},
     {true, true, true}
  };
const double CSE_SWL[CSE_NBARS][3] =
  {
     {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0},
     {-0.0001, -0.00012, -0.0002},
     {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}
  };
const double CSE_SWS[CSE_NBARS][3] =
  {
     {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0},
     {0.00005, 0.00003, 0.0001},
     {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}
  };

// expected eq_c / eq_w per bar (python golden, %.17g)
const double CSE_EXP_EQC[CSE_NBARS] =
  {
   10005.340000000002, 10001.840000000002, 10164.397000000001,
   10017.636165640002, 9962.5486656400026, -94812.793834359996,
   -94812.793834359996
  };
const double CSE_EXP_EQW[CSE_NBARS] =
  {
   9993.8320000000022, 9999.0120000000024, 9775.5820000000003,
   9851.2671656400016, 9796.5436656400016, -94812.793834359996,
   -94812.793834359996
  };
const double CSE_EXP_BAL = -94812.793834359996;
const long   CSE_EXP_NTR = 7;

// python json.dumps state after bar 3 (gen_check_golden.py) — feeds the
// cross-format SetState test for bars 4-6
const string CSE_PY_STATE_BAR3 =
   "{\"balance\": 9961.713165640002, \"lots\": [0.0, 0.0, 0.0, 0.0, 0.0, "
   "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.010000000000000002, "
   "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.02, 0.0, 0.0, 1.21, "
   "0.0, 0.0, 0.0], \"entry\": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
   "0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.1002, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "
   "0.0, 0.0, 0.0, 109.97, 0.0, 0.0, 1601.5, 0.0, 0.0, 0.0], "
   "\"n_trades\": 6, \"symbols\": [\"AUDCAD\", \"AUDJPY\", \"AUDNZD\", "
   "\"BTCUSD\", \"CADCHF\", \"CADJPY\", \"DAX\", \"ETHUSD\", \"EURCAD\", "
   "\"EURCHF\", \"EURGBP\", \"EURNOK\", \"EURNZD\", \"EURSEK\", "
   "\"EURUSD\", \"GBPJPY\", \"JP225\", \"NZDCAD\", \"NZDJPY\", "
   "\"SOLUSD\", \"UK100\", \"US30\", \"USA500\", \"USDCHF\", \"USDJPY\", "
   "\"USTEC\", \"XAGUSD\", \"XAUUSD\", \"XBRUSD\", \"XNGUSD\", "
   "\"XTIUSD\"]}";

int g_failures = 0;

void CSECheck(const bool ok, const string what)
  {
   if(!ok)
     {
      g_failures++;
      Print("CheckSatEquity FAIL: ", what);
     }
  }

// assemble the 31-wide input arrays for synthetic bar t
void CSEBarInputs(const int t, double &tgt[], bool &has[],
                  double &bo[], double &ao[], double &bc[], double &ac[],
                  double &bl[], double &ah[], double &eurq[],
                  double &swl[], double &sws[])
  {
   for(int k = 0; k < SATEQ_NSYM; k++)
     {
      tgt[k] = 0.0;
      has[k] = false;
      bo[k] = 1.0;
      ao[k] = 1.0;
      bc[k] = 1.0;
      ac[k] = 1.0;
      bl[k] = 1.0;
      ah[k] = 1.0;
      eurq[k] = 1.0;
      swl[k] = 0.0;
      sws[k] = 0.0;
     }
   int  syms[3];
   syms[0] = CSE_E;
   syms[1] = CSE_U;
   syms[2] = CSE_X;
   for(int j = 0; j < 3; j++)
     {
      int k = syms[j];
      tgt[k] = CSE_TGT[t][j];
      has[k] = CSE_HAS[t][j];
      swl[k] = CSE_SWL[t][j];
      sws[k] = CSE_SWS[t][j];
     }
   bo[CSE_E] = CSE_PX_E[t][0];
   ao[CSE_E] = CSE_PX_E[t][1];
   bc[CSE_E] = CSE_PX_E[t][2];
   ac[CSE_E] = CSE_PX_E[t][3];
   bl[CSE_E] = CSE_PX_E[t][4];
   ah[CSE_E] = CSE_PX_E[t][5];
   bo[CSE_U] = CSE_PX_U[t][0];
   ao[CSE_U] = CSE_PX_U[t][1];
   bc[CSE_U] = CSE_PX_U[t][2];
   ac[CSE_U] = CSE_PX_U[t][3];
   bl[CSE_U] = CSE_PX_U[t][4];
   ah[CSE_U] = CSE_PX_U[t][5];
   bo[CSE_X] = CSE_PX_X[t][0];
   ao[CSE_X] = CSE_PX_X[t][1];
   bc[CSE_X] = CSE_PX_X[t][2];
   ac[CSE_X] = CSE_PX_X[t][3];
   bl[CSE_X] = CSE_PX_X[t][4];
   ah[CSE_X] = CSE_PX_X[t][5];
   eurq[CSE_E] = CSE_EURQ_USD;
   eurq[CSE_X] = CSE_EURQ_USD;
   eurq[CSE_U] = CSE_EURQ_JPY;
  }

// step bars [t0, t1) of the scenario on eng, recording eq_c/eq_w
void CSERun(CSatEquityNative &eng, const int t0, const int t1,
            double &out_c[], double &out_w[])
  {
   double tgt[SATEQ_NSYM], bo[SATEQ_NSYM], ao[SATEQ_NSYM];
   double bc[SATEQ_NSYM], ac[SATEQ_NSYM], bl[SATEQ_NSYM], ah[SATEQ_NSYM];
   double eurq[SATEQ_NSYM], swl[SATEQ_NSYM], sws[SATEQ_NSYM];
   bool   has[SATEQ_NSYM];
   for(int t = t0; t < t1; t++)
     {
      CSEBarInputs(t, tgt, has, bo, ao, bc, ac, bl, ah, eurq, swl, sws);
      double eq_c = 0.0, eq_w = 0.0;
      eng.Step(tgt, has, bo, ao, bc, ac, bl, ah, eurq, swl, sws,
               eq_c, eq_w);
      out_c[t] = eq_c;
      out_w[t] = eq_w;
     }
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   Print("CheckSatEquity: SatEquityNative smoke starting ...");

   //--- 1. continuous run vs python golden (EXACT doubles) ----------
   CSatEquityNative eng;
   double eqc[CSE_NBARS], eqw[CSE_NBARS];
   CSERun(eng, 0, CSE_NBARS, eqc, eqw);
   for(int t = 0; t < CSE_NBARS; t++)
     {
      PrintFormat("bar %d: eq_c=%.17g eq_w=%.17g", t, eqc[t], eqw[t]);
      CSECheck(eqc[t] == CSE_EXP_EQC[t],
               StringFormat("bar %d eq_c %.17g != %.17g", t, eqc[t],
                            CSE_EXP_EQC[t]));
      CSECheck(eqw[t] == CSE_EXP_EQW[t],
               StringFormat("bar %d eq_w %.17g != %.17g", t, eqw[t],
                            CSE_EXP_EQW[t]));
     }
   CSECheck(eng.Balance() == CSE_EXP_BAL, "final balance");
   CSECheck(eng.NTrades() == CSE_EXP_NTR, "final n_trades");
   string final_json = eng.GetState();

   //--- 2. GetState/SetState roundtrip -------------------------------
   CSatEquityNative rt;
   CSECheck(rt.SetState(final_json), "roundtrip SetState parse");
   CSECheck(rt.GetState() == final_json, "roundtrip GetState identical");

   //--- 3. warm-start split after bar 3 == continuous run -------------
   CSatEquityNative ea;
   double ac2[CSE_NBARS], aw2[CSE_NBARS];
   CSERun(ea, 0, 4, ac2, aw2);
   string mid_json = ea.GetState();
   CSatEquityNative eb;
   CSECheck(eb.SetState(mid_json), "split SetState parse");
   CSERun(eb, 4, CSE_NBARS, ac2, aw2);
   bool split_ok = true;
   for(int t = 0; t < CSE_NBARS; t++)
      if(ac2[t] != eqc[t] || aw2[t] != eqw[t])
         split_ok = false;
   CSECheck(split_ok, "warm-start split bit-identical");
   CSECheck(eb.GetState() == final_json, "split final state identical");

   //--- 4. PYTHON-formatted state blob drives bars 4-6 ----------------
   CSatEquityNative ec;
   CSECheck(ec.SetState(CSE_PY_STATE_BAR3), "python state blob parse");
   double pc[CSE_NBARS], pw[CSE_NBARS];
   CSERun(ec, 4, CSE_NBARS, pc, pw);
   bool py_ok = true;
   for(int t = 4; t < CSE_NBARS; t++)
      if(pc[t] != eqc[t] || pw[t] != eqw[t])
         py_ok = false;
   CSECheck(py_ok, "python-blob warm start bit-identical");
   CSECheck(ec.GetState() == final_json, "python-blob final state");

   //--- 5. malformed state must be rejected ----------------------------
   CSatEquityNative ed;
   CSECheck(!ed.SetState("{\"balance\": 1.0}"), "reject truncated json");

   PrintFormat("CheckSatEquity: FAILURES=%d", g_failures);
  }
//+------------------------------------------------------------------+
