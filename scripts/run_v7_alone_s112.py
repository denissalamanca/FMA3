#!/usr/bin/env python3
"""k-calibration reference #2: v7 sub-book ALONE at the deployment intensity
(x1.12 = 8.96/8), record engine — matches the owner's MT5 run 54."""
import sys, json
from pathlib import Path
_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))
import pandas as pd
import record_engine as RE
from run_hfed1_lib import crisis_tail
frac7 = pd.read_parquet(RE.PATHS.OUTPUTS / "v7_book_frac_1h.parquet")
res = RE.run_record(frac7 * 1.12, label="v7_alone_s112", verbose=False, run_bootstrap=False)
tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
out = {"label": "v7_alone_s112 (record reference for the R8.96 tick run 54)",
       "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
       "crisis_tail": tail, "sharpe": res["sharpe"],
       "final_equity": res["final_equity"]}
(RE.PATHS.OUTPUTS / "v7_alone_s112_record.json").write_text(json.dumps(out, indent=1, default=str))
print(f"[v7_alone_s112] CAGR {res['cagr']:+.4f} | DDworst {res['maxdd_worst']:.4f} | tail {tail:.4f} | final €{res['final_equity']:,.0f}", flush=True)
