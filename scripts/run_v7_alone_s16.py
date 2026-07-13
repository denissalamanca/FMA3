#!/usr/bin/env python3
"""k-calibration reference: v7 sub-book ALONE at IC scale (x1.6), record engine.

Matches the owner's MT5 tester run (FableMultiAsset1_V7, InpRisk=12.8 =
R8x1.6, InpInitial=10000, EUR 10k, 2020-2025 real-tick) in the engine of
record. Output feeds k_dd / k_tail / retention per DEMO_PREREGISTRATION.
"""
import sys, json
from pathlib import Path
_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))
import pandas as pd
import record_engine as RE
from run_hfed1_lib import crisis_tail

frac7 = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_frac_1h.parquet")
res = RE.run_record(frac7 * 1.6, label="v7_alone_s16", verbose=False,
                    run_bootstrap=False)
tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
out = {"label": "v7_alone_s16 (record reference for the R12.8 tick run)",
       "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
       "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
       "crisis_tail": tail, "final_equity": res["final_equity"],
       "yearly": res["yearly"], "neg_quarters": res["neg_quarters"]}
pd.DataFrame({"equity": res["curves"]["equity"],
              "worst": res["curves"]["worst"]}).to_parquet(
    RE.PATHS.OUTPUTS / "v7_alone_s16_curve.parquet")
(RE.PATHS.OUTPUTS / "v7_alone_s16_record.json").write_text(
    json.dumps(out, indent=1, default=str))
print(f"[v7_alone_s16] CAGR {res['cagr']:+.4f} | DDworst "
      f"{res['maxdd_worst']:.4f} | tail {tail:.4f} | Sharpe "
      f"{res['sharpe']:.3f} | final €{res['final_equity']:,.0f}", flush=True)
