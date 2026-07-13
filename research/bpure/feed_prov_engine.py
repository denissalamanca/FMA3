"""Propagate the Duka-hybrid book through the record engine (account_engine_1m,
IC 1m pricing, EUR 10k) and compare metrics to the frozen pin."""
from __future__ import annotations
import sys, json, time
from pathlib import Path
HERE = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
sys.path.insert(0, str(HERE / "research"))
sys.path.insert(0, str(HERE))
import pandas as pd
import core
import account_engine_1m as A1

SCRATCH = Path("/private/tmp/claude-501/-Users-dsalamanca-vs-env-FableMultiAssets3/"
               "cb1d44e8-f5e7-4172-a469-abf08e14a819/scratchpad")

PIN = {"cagr": 0.8865880762592069, "maxdd": 0.2167488591051508,
       "sharpe": 1.8543172985943566, "final_equity": 449707.7452664526,
       "n_neg_years": 0, "n_neg_quarters": 1}

if __name__ == "__main__":
    # engine reads IC 1m regardless of core.CACHE; keep core.CACHE at PIN so its
    # helper grids/eurq are the canonical ones.
    core.CACHE = HERE / "research_cache"
    core.load_hourly.cache_clear(); core.universe_frames.cache_clear()

    pos = pd.read_parquet(SCRATCH / "pos_hybrid.parquet")
    t0 = time.time()
    eqc, eqw, m = A1.simulate_account_1m(pos, initial=10_000.0, verbose=True)
    print(f"engine {time.time()-t0:.0f}s")
    print("\n=== Duka-hybrid book (14/37 syms Dukascopy) through IC record engine ===")
    print(f"CAGR {m['cagr']:+.6f} | DDworst {m['maxdd']:.6f} | Sharpe {m['sharpe']:.4f} "
          f"| negY {m['n_neg_years']} negQ {m['n_neg_quarters']} | EUR{m['final_equity']:,.2f}")
    print("\n=== PIN (all-IC) ===")
    print(f"CAGR {PIN['cagr']:+.6f} | DDworst {PIN['maxdd']:.6f} | Sharpe {PIN['sharpe']:.4f} "
          f"| negY {PIN['n_neg_years']} negQ {PIN['n_neg_quarters']} | EUR{PIN['final_equity']:,.2f}")
    d = {"dCAGR_pp": (m['cagr']-PIN['cagr'])*100,
         "dMaxDD_pp": (m['maxdd']-PIN['maxdd'])*100,
         "dFinal_pct": (m['final_equity']/PIN['final_equity']-1)*100,
         "dSharpe": m['sharpe']-PIN['sharpe'],
         "hybrid": {k: (m[k] if not isinstance(m[k], dict) else '') for k in
                    ['cagr','maxdd','sharpe','final_equity','n_neg_years','n_neg_quarters']}}
    print("\n=== DELTA (hybrid - pin) ===")
    print(f"dCAGR {d['dCAGR_pp']:+.3f} pp | dMaxDD {d['dMaxDD_pp']:+.3f} pp | "
          f"dFinal {d['dFinal_pct']:+.2f}% | dSharpe {d['dSharpe']:+.4f}")
    json.dump(d, open(SCRATCH / "feed_prov_engine.json", "w"), indent=1, default=float)
    pd.DataFrame({"equity": eqc, "worst": eqw}).to_parquet(SCRATCH / "hybrid_curve.parquet")
