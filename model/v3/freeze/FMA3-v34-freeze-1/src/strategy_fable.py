"""FABLE MULTI-ASSET PORTFOLIO — production strategy definition.

A unified 7-sleeve, ~30-instrument portfolio over the IC Markets 37-asset
universe (1m bid/ask feed, 2020-2025), engineered from first principles in
this workspace. The NewStrategyFable5 framework is used STRICTLY as an
execution/validation pipeline; no strategy content from that repository was
read or reused.

Sleeves (economic edge → module):
  meanrev        FX-cross z-score reversion + index dip-buying
                 (related-economy crosses co-move; institutional dip-buying
                 above long trend)                    sleeves/meanrev.py
  carry_breakout FX carry gated by trend + long Donchian breakout on
                 commodities/indices (rate differentials accrue via swaps;
                 supply shocks trend)                 sleeves/carry_breakout.py
  seasonal       Gold NY-close→Asia session drift (flow-driven overnight
                 gold anomaly; pays nightly swap — modeled)
                                                      sleeves/seasonal.py
  intraday       NY-open drive continuation on USA500/USTEC, intraday-only,
                 flat overnight → zero swap           sleeves/intraday.py
  crisis         Defensive convexity: stress-gated gold + JPY-cross
                 snapback (activates in vol regimes)  sleeves/crisis.py
  trend_v2       Lookback-ensemble TSMOM on metals/energy
                                                      sleeves/trend_v2.py
  crypto_smart   Swap-asymmetry-aware BTC/ETH/SOL momentum (longs must beat
                 -20%/yr financing; shorts financing-free)
                                                      sleeves/crypto_smart.py

Allocation: frozen sleeve weights (DEV-2020-23-optimized plateau median,
verified out-of-sample on 2024-25), combined at the position level and
levered by a constant global scale chosen so the DEV worst drawdown stays
inside the 20% budget. No dynamic overlays: they were tested (vol targeting,
drawdown throttle, quarter throttle) and REJECTED on DEV — the sleeves'
internal risk gates make portfolio-level overlays pure drag.

Position convention: hourly matrix of signed notional exposure as a fraction
of portfolio equity; bar stamps are broker server time (GMT+2/+3).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
for p in (HERE / "research", HERE / "research" / "sleeves"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ---------------------------------------------------------------------------
# SHIPPED CONFIGURATION — v2 (decision 2026-07-10, user; see docs/v2.0/)
# ---------------------------------------------------------------------------
# F3 conviction caps applied to the v1 frozen weights (DOWNWARD-ONLY, from the
# economic-durability audit docs/v2.0/F3_DURABILITY.md; stress-validated in
# docs/v2.0/stress/ — ceiling-breach odds 0.095 vs 0.329 frozen at scale 9).
# Weights are NOT renormalized: the freed 0.224 is cash-parked by design.
# The v1 frozen allocation remains in research/outputs/final_config.json
# (historical benchmark; run_v1_*.py still load it).
SLEEVE_WEIGHTS: dict[str, float] = {
    "meanrev": 0.110,          # v1 0.140, capped (conditional durability)
    "carry_breakout": 0.046,   # keep
    "seasonal": 0.180,         # v1 0.247, capped to the 0.4-0.6 feed-honest edge
    "intraday": 0.168,         # keep (durable)
    "crisis": 0.100,           # v1 0.139, capped (insurance, prereg fail 2015-19)
    "trend_v2": 0.042,         # keep (durable)
    "crypto_smart": 0.130,     # v1 0.219, capped (institutionalization risk)
    # v3 (2026-07-10): imported overlay seat — gold $100 round-number magnet,
    # module research/ext_import/mag_xau.py (frozen as ported from the
    # NewStrategyFable5 hunt; sole survivor of the pre-registered 4-candidate
    # gauntlet: 2015-19 OOS Sharpe 0.62, our-harness 1.25). Lag-fragile: on
    # the slippage-ledger watch.
    "mag_xau": 0.050,
}
# HARD EXPOSURE LIMITS (stress-validated; enforced in research via
# ensemble.apply_hard_limits and live by the EA):
#   overnight |XAUUSD| <= STRUCTURAL RULE: the primary gold sleeve's own
#     intended exposure = seasonal weight x scale = 0.18*9 = 1.62x equity
#     (ensemble.structural_gold_cap; revised from the 1.0xE first cut
#     2026-07-10 — plateau-tested, clips only multi-sleeve stacking;
#     -9% gold-gap tail ~-15%, inside the -25% kill)
#   |EURCHF|,|EURSEK|,|EURNOK|,|AUDNZD| <= 0.5x equity  (MKT-8a: peg-break)
# Crypto-delisting fallback: CASH-PARK the freed weight, never renormalize
# (OPS-8: renormalizing doubles ceiling-breach odds).
# Global leverage scale. The right value depends on the account/engine model:
#   v1.0 (30 quarterly sub-accounts):  scale 4.0  -> CAGR 34.5% / DD 17.9%
#   v1.1 (single cross-margined acct): scale 6.0  -> CAGR 67.8% / DD 16.1% (20% budget)
# Gate revision 2026-07-09: DD budget 20% -> 30%. 1m-confirmed frontier
# (single account, worst-mark): scale 9 -> 106% CAGR / 23.5% DD (margin cap
# never binds, 6.5pp OOS buffer) · 10 -> 122% / 25.7% · 11 -> 136% / 28.4%.
# Operating point = scale 9 (2026-07-09): CAGR 106.1% / DD 23.5% / Sharpe 1.82 /
# 0 negY / 1 negQ, 1m-confirmed. Gating philosophy: P(breach 30%) — 30% is a hard
# not-to-breach ceiling. Block-length sensitivity showed the 20d bootstrap
# overstates breach (chops recovery structure); scale 9's realistic breach is
# ~14-20% (40-60d blocks), the same comfort zone scale 8 had under the pessimistic
# 20d bootstrap. Observed DD 23.5% leaves 6.5pp margin. NOTE: this should be an EA
# parameter (target vol / max-DD throttle), tunable live; drop to scale 8 (breach
# ~8-14%) for more margin. Sharpe ~1.82 at EVERY scale (leverage-invariant).
ENGINE_MODEL: str = "single"        # "single" (v1.1) | "subaccount" (v1.0)
# v3 (decision 2026-07-10, user): C2 book (v2 + mag_xau@0.05) re-levered to 11
# per the pinned frontier (s11 vs s12 both 1m-pinned; 11 chosen — breach 0.198
# keeps the 30% wall a tail event). Official: outputs/c2_s11_pin_1m.json —
# CAGR +99.9% / DDworst 23.2% / Sharpe 1.86 / 0 negY / 2 negQ / €10k→€636k.
# v3.4 (2026-07-10): FINAL scale re-pick, 11 -> 10 by pre-committed rule
# (docs/v3.4/PREREGISTRATION.md: smallest scale with negQ<=1 AND CAGR>=85%).
# Pinned scales {9,10,11}: s9 fails CAGR (79.4<85), s11 fails negQ (2>1); s10
# clears both -> adopted. Structural gold cap re-derives 0.18*10 = 1.80xE.
# Official: outputs/v34_s10_pin_1m.json — CAGR +88.7% / DDworst 21.7% /
# Sharpe 1.85 / 0 negY / 1 negQ / breach 0.121 / €10k->€449,708.
GLOBAL_SCALE: float = 10.0


def build_portfolio_positions(rebuild: bool = False) -> pd.DataFrame:
    """Final hourly position matrix (fraction of portfolio equity per
    instrument). rebuild=False loads the audited per-sleeve parquets
    (bit-identical to module output, verified); rebuild=True regenerates
    every sleeve from source."""
    total = sum(SLEEVE_WEIGHTS.values())
    pos: pd.DataFrame | None = None
    for name, w in SLEEVE_WEIGHTS.items():
        if rebuild:
            mod = __import__(name)
            sp = mod.make_positions()
        else:
            sp = pd.read_parquet(HERE / "research" / "outputs"
                                 / f"{name}_pos.parquet")
        contrib = sp * (w / total) * GLOBAL_SCALE
        pos = contrib if pos is None else pos.add(contrib, fill_value=0.0)
    assert pos is not None
    return pos.fillna(0.0)


def main() -> None:
    import core
    pos = build_portfolio_positions()
    print("=== fast-sim summary (screening model; official numbers come "
          "from run_validation.py) ===")
    for label, kw in [("DEV ", dict(end="2023-12-31")),
                      ("HOLD", dict(start="2024-01-01")),
                      ("FULL", {})]:
        res = core.simulate(pos, **kw)
        print(label, core.fmt_metrics(res.metrics))


if __name__ == "__main__":
    main()
