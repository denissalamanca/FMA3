"""FMA3 v1.0 — the locked federation book (AUTHORITATIVE CONFIG).

One cross-margined EUR account running BOTH parent books side by side as
virtual sub-accounts, each with its native mechanics untouched:

  * v7.0 band book (NewStrategyFable5, 7 slot-equity sleeves, BAND_SYM_25
    re-split + H9 delta-resize) — sub-capital share w = 0.70;
  * v3.4 fixed-fraction book (FableMultiAssets2, 8 sleeves x scale 10,
    F3 caps, hard limits, cash-park) — sub-capital share 1 - w = 0.30;
  * NO cross-book rebalancing (H-FED-2: all cadences DECLINED — rebalancing
    couples the disjoint troughs it tries to harvest);
  * global scale s = 1.1 on the blended fraction matrix. H-FED-3's ceiling
    rule alone gave s=1.4; the red-team adjudication (FMA3-RT) added the
    probe-robustness constraint — all ceilings must also hold at both +-20%
    w probes (a never-rebalanced federation's realized w drifts) — which
    binds at w_up20: DD 17.97% x s < 20.9% => s = 1.1. s in {1.2..1.4}
    remain documented as the aggressive frontier (compliant at the locked w,
    not probe-robust).

Decision trail: FMA3-000..003 in docs/REGISTRY.md; pre-registered bars in
research/protocol/PROTOCOL.md + HYPOTHESES.md (committed before any merged
number existed). Official pin: scripts/eval_fma3_pin.py ->
research/outputs/fma3_v1_pin.json.

Official numbers (engine of record — Python 1m worst-mark, single
cross-margined account, IC feed, 2020-2025, EUR 10k):

    CAGR +101.4% | maxDD (worst-mark) 15.73% | Sharpe 2.467
    COVID tail 5.36% | negY 0/6 | negQ 0/24 | breach P(DD>30%) 0.0020

The owner's six gates (CAGR>96.1, DD<20.9, Sharpe>2.03, tail<=35.6,
negY 0, negQ<=1) ALL clear, and all SEVEN composite dimensions dominate
both parents (the only fully-dominant point on the scale frontier).
MT5 real-tick confirmation on the owner's machine remains the deployable
arbiter (the 1m<->tick crisis-tail gap is documented in
research/outputs/COMPOSITE_BENCHMARK.md).
"""
from __future__ import annotations

import hashlib
import json

# ----------------------------------------------------------------- config ---
FMA3_CONFIG: dict = {
    "version": "1.0",
    "locked": "2026-07-10",
    "structure": "static_federation",       # H-FED-1 winner; H-FED-2 declined
    "w_v7": 0.70,                            # v7.0 band-book capital share
    "global_scale": 1.1,                     # H-FED-3 + FMA3-RT probe-robust re-pick
    "parents": {
        "v7": {
            "repo": "/Users/dsalamanca/vs_env/NewStrategyFable5",
            "book": "V7.0 core7 band (BTC_REP, USTEC), R8 anchor extraction",
            "anchor": "engine_reproduce.json:harvest_band_sym "
                      "(cagr_bd 0.8972225987059659, byte-reconciled)",
            "positions": "research/outputs/v7_book_frac_1h.parquet",
            "equity": "research/outputs/v7_book_equity_1m.parquet",
        },
        "v34": {
            "repo": "/Users/dsalamanca/vs_env/FableMultiAssets2",
            "book": "v3.4 (8 sleeves @ GLOBAL_SCALE 10, hard limits, "
                    "config hash 48c09199fbf83d82)",
            "anchor": "research/outputs/v34_s10_pin_1m.json "
                      "(cagr 0.8865880, byte-reproduced)",
            "positions": "engine/books.py::build_v34_frac_1h()",
            "equity": "research/baselines/fma2/v34_s10_pin_curve.parquet",
        },
    },
    "construction": (
        "fed_frac_h = frac7_h * (w*A_h/J_h) + frac34_h * ((1-w)*B_h/J_h); "
        "A,B = native 1m curves normalized to 1.0 at t0, sampled causally at "
        "hour h (asof); J = w*A + (1-w)*B; final matrix = fed_frac * s. "
        "Virtual sub-account bookkeeping — neither book's internal state sees "
        "the other's P&L (PROTOCOL §5.7)."
    ),
    "inherited_limits": (
        "Each sub-book's own structural limits arrive pre-applied in its "
        "fraction matrix (v3.4 gold overnight 1.80xE_sub + managed-cross "
        "0.5xE_sub; v7 sleeve caps). H-CAPS-1 verified joint exposures never "
        "exceed the sum of entitlements (0 hours; hcaps1_analysis.json)."
    ),
    "engine_of_record": (
        "FMA2 research/account_engine_1m.py::simulate_account_1m via FMA3 "
        "engine/record_engine.py (verified 41/41 delta 0.0)"
    ),
}


def config_hash(cfg: dict = FMA3_CONFIG) -> str:
    """Deterministic 16-hex config hash (FMA2 house convention)."""
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


if __name__ == "__main__":
    print(json.dumps(FMA3_CONFIG, indent=2))
    print(f"\nconfig_hash: {config_hash()}")
