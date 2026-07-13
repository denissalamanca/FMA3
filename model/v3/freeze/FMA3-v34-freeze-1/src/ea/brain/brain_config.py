"""Single source of truth for the Python-brain half of the v2 demo bridge.

The brain computes hourly TARGET positions from the validated research code and
hands them to the MQL5 executor through the file bridge in ``ea/bridge/``.
Nothing here re-implements a signal — the alpha lives entirely in
``research/sleeves/*`` and ``research/ensemble.py``; this module only pins the
*deployment* constants (paths, the shipped weight/scale/limit config, magic
numbers, guard thresholds incl. the four stress-battery fixes).

CONFIG PROVENANCE
-----------------
The shipped v3 config is the C2 book = v2 F3-capped book + the imported overlay
``mag_xau@0.05`` (gold $100 round-number magnet, research/ext_import/mag_xau.py),
re-levered to GLOBAL_SCALE 10 (v3.4 final scale re-pick, 2026-07-10; official 1m
pin ``outputs/v34_s10_pin_1m.json`` — CAGR +88.7% / DDworst 21.7% / Sharpe 1.85 /
0 negY / 1 negQ / breach 0.121; supersedes s11 by the pre-committed rule
docs/v3.4/PREREGISTRATION.md — smallest scale with negQ<=1 AND CAGR>=85%).
Weights + scale are imported LIVE from ``strategy_fable.py`` so the brain can
never silently drift from the pinned strategy definition. The freed weight
(1 - sum(weights) = 0.174) is CASH-PARKED: the book is deliberately NOT
renormalized (OPS-8). The official 1m pipeline is ``research/eval_c2_pin_s11.py``
(construction mirrors ``run_v2_pin.py``): the 7 v2 sleeves + the ``mag_xau``
overlay, ``combine(sleeves, W) * SCALE`` then ``structural_gold_cap`` +
``apply_hard_limits`` on the COMBINED book. NOTE:
``strategy_fable.build_portfolio_positions`` divides by ``sum(weights)`` (a
v1-era renormalization) which would UNDO the cash-park; the brain therefore does
NOT use that helper — it mirrors ``eval_c2_pin_s11`` exactly. See
``target_engine.py``.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
WORKSPACE = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
RESEARCH = WORKSPACE / "research"
OUTPUTS = RESEARCH / "outputs"
RESEARCH_CACHE = WORKSPACE / "research_cache"          # frozen 2020-2025 hourly

# Make strategy_fable + the research modules importable without side effects.
for _p in (WORKSPACE, RESEARCH, RESEARCH / "sleeves"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# The file bridge shared with the MQL5 executor.
BRIDGE_DIR = WORKSPACE / "ea" / "bridge"
BARS_DIR = BRIDGE_DIR / "bars"                          # executor -> brain (bars)
LEDGER_DIR = BRIDGE_DIR / "ledgers"

TARGETS_PATH = BRIDGE_DIR / "targets.json"             # brain -> executor (PROTOCOL §1)
COMMANDS_PATH = BRIDGE_DIR / "commands.json"           # brain/batch -> executor (PROTOCOL §2)
SEQ_PATH = BRIDGE_DIR / "targets.seq"                  # monotonic sequence store (brain)
CMD_SEQ_PATH = BRIDGE_DIR / "commands.seq"             # monotonic sequence store (commands)
STATE_PATH = BRIDGE_DIR / "state.json"                 # executor -> brain (PROTOCOL §6)
BROKER_SNAPSHOT_PATH = BRIDGE_DIR / "broker_positions.json"   # executor/watchdog snapshot
ALERTS_PATH = BRIDGE_DIR / "alerts.jsonl"              # guards -> watchdog (append-only)
HEARTBEAT_PATH = BRIDGE_DIR / "heartbeat_brain.json"  # BRAIN liveness (distinct from EA heartbeat.json)
GUARD_STATE_PATH = BRIDGE_DIR / "guard_state.json"    # persisted guard memory (OPS-6a change detection)

# Ledgers (CSV; production-quality-bar items 6 & 8). Names per PROTOCOL §8/§9.
SLIPPAGE_LEDGER = LEDGER_DIR / "slippage_ledger.csv"   # go/no-go dataset for seasonal (EA-written)
RETENTION_LEDGER = LEDGER_DIR / "retention_ledger.csv"  # OPS-6 below-min lot drops (EA-written)
SLEEVE_PNL_LEDGER = LEDGER_DIR / "sleeve_daily_pnl.csv"     # batch-Python internal
GROSS_NOTIONAL_LEDGER = LEDGER_DIR / "gross_notional.csv"   # MKT-7 notional ratchet (batch-Python)
BOOK_EQUITY_LEDGER = LEDGER_DIR / "book_equity.csv"         # OPS-6b (batch-Python)

# Slippage-ledger columns the EA appends (PROTOCOL §8). guards_engine reads
# side / slippage_bp / forced; the rest are carried for the go/no-go analysis.
SLIPPAGE_COLUMNS = [
    "ts_server", "ts_utc", "sleeve", "magic", "symbol", "side", "requested_px",
    "filled_px", "bid", "ask", "spread_pts", "spread_bp", "slippage_bp",
    "lots", "ticket", "deal", "forced", "reason",
]

# --------------------------------------------------------------------------- #
# Instrument classes (mirror research/core.py; kept local so importing this
# config does NOT pull in the numba framework).
# --------------------------------------------------------------------------- #
FX = ["AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
      "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
      "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY"]
CRYPTO = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
INDICES = ["DAX", "JP225", "UK100", "US30", "USA500", "USTEC"]
COMMODITIES = ["XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"]
ALL_SYMBOLS = FX + CRYPTO + INDICES + COMMODITIES
CLASS_OF = ({s: "fx" for s in FX} | {s: "crypto" for s in CRYPTO}
            | {s: "index" for s in INDICES} | {s: "commodity" for s in COMMODITIES})

# --------------------------------------------------------------------------- #
# Shipped v3 config — imported LIVE from strategy_fable (never re-typed here).
# v3 = v2 seven sleeves + mag_xau@0.05 overlay, GLOBAL_SCALE 10 (v3.4 re-pick).
# --------------------------------------------------------------------------- #
import strategy_fable as _sf                            # noqa: E402

SLEEVE_WEIGHTS: dict[str, float] = dict(_sf.SLEEVE_WEIGHTS)
GLOBAL_SCALE: float = float(_sf.GLOBAL_SCALE)
ENGINE_MODEL: str = str(_sf.ENGINE_MODEL)
WEIGHT_SUM: float = sum(SLEEVE_WEIGHTS.values())        # 0.826; freed 0.174 = cash
CASH_PARK: float = 1.0 - WEIGHT_SUM

SLEEVES: list[str] = list(SLEEVE_WEIGHTS)               # order matters for magic map

# --------------------------------------------------------------------------- #
# Magic numbers — one per sleeve (EA_MONITORING_SPEC §2.1, pinned in
# ea/bridge/PROTOCOL.md §3). Base 8400000; the [8400001, 8400008] band is the
# reconcile/adopt key (v3 extended the band to 8400008 = mag_xau, the imported
# overlay seat). Static, never reused. MUST match the EA's map (FableCommon.mqh).
# --------------------------------------------------------------------------- #
MAGIC_BASE = 8_400_000
MAGIC_OF: dict[str, int] = {name: MAGIC_BASE + i + 1 for i, name in enumerate(SLEEVES)}
SLEEVE_OF_MAGIC: dict[int, str] = {m: n for n, m in MAGIC_OF.items()}

# --------------------------------------------------------------------------- #
# Hard exposure limits (stress-validated; enforced in research by
# ensemble.apply_hard_limits and live by the EA — brain applies them too so the
# target file is already limit-clean = defense in depth).
# --------------------------------------------------------------------------- #
MANAGED_CROSSES = ["EURCHF", "EURSEK", "EURNOK", "AUDNZD"]
CROSS_CAP_X_EQUITY = 0.5                                # MKT-8a
GOLD_SYMBOL = "XAUUSD"
# The sleeves whose XAUUSD is aggregated for the overnight MKT-4a cap. v3 adds
# mag_xau (the round-number magnet holds gold across the midnight roll — its
# daily target is ffilled hourly, so it stacks on the overnight XAU column and
# must be counted). It carries no fixed exit hour (no SLEEVE_SCHEDULE entry).
GOLD_OVERNIGHT_SLEEVES = ["seasonal", "crisis", "trend_v2", "mag_xau"]  # 4 XAU sleeves
# overnight = server hours [21,24) U [0,6).
GOLD_OVERNIGHT_HOURS = list(range(21, 24)) + list(range(0, 6))
# RECONCILED (2026-07-10): the SHIPPED overnight-gold hard limit is the
# STRUCTURAL RULE = the primary gold sleeve's own intended exposure
# (seasonal_w x scale = 0.18*11 = 1.98xE at v3 scale 11) —
# ensemble.structural_gold_cap. The 1.0xE first cut was superseded (it
# double-counted seasonal's own gold demand, binding 81% of nights; plateau test
# showed a smooth monotone dial — no fitted peak). The official 1m pin
# (outputs/c2_s11_pin_1m.json, CAGR +99.9%) uses this rule on the COMBINED book
# (v2 XAU sleeves + mag_xau); SPEC §9 + VERSION_HISTORY carry the dated decision.
# The cap clips only multi-sleeve STACKING above seasonal's own allocation.
MKT4A_OVERNIGHT_GOLD_CAP_XE = None  # None => use structural rule (no tighter override)

# Per-sleeve intraday exit schedule (server hours), echoed into each target
# record so the EA runs the OPS-2 forced-exit ladder. From F2/SPEC.
SLEEVE_SCHEDULE: dict[str, dict[str, int]] = {
    "seasonal": {"flat_at_server_hour": 6, "no_entry_after_hour": 5},
    "intraday": {"flat_at_server_hour": 21, "no_entry_after_hour": 20},
}

# --------------------------------------------------------------------------- #
# EXECUTION POLICY — v3.2 maker-first (docs/v3.2/, ADOPT 2026-07-10).
# Zero-alpha-trial execution lever: re-prices the SPREAD LEG of the already
# shipped order stream, it does NOT touch weights/scale/limits. Pre-registered
# arrival-price study (docs/v3.2/PREREGISTRATION.md, one run,
# research/outputs/v32_maker.json): net spread-leg reduction 91.67% at T*=60 vs
# a 30% bar -> ACCEPT. The BACKTEST STILL CHARGES FULL TAKER COST (pinned numbers
# unchanged, cost-model conservatism kept); adoption is CONFIG-ONLY and gated on
# the demo slippage ledger (RUNBOOK §8) before any real capital.
#
# Per-sleeve HYBRID map (a sleeve makes iff its own net saving>0 AND fill>=70% in
# the study): all sleeves MAKE except `intraday`, which is a NY-open momentum
# sleeve that maker execution is adversely selected against (net -2136 bp.E
# despite 97.5% touch — the fast winners run away from the resting limit and
# chase). `mag_xau` owns no partition symbol (its gold executes under the XAUUSD
# = seasonal maker policy) but is listed MAKER for clarity + is on the slippage
# watch (lag-fragile). FORCED / RISK / SCHEDULED EXITS ARE ALWAYS TAKER.
MAKER_HORIZON_MIN = 60            # T*: post at touch, chase-to-taker after T min
MAKER_SLEEVES = ["meanrev", "seasonal", "crypto_smart", "crisis", "trend_v2",
                 "carry_breakout", "mag_xau"]
TAKER_SLEEVES = ["intraday"]     # kept taker by the hybrid rule (adverse selection)
FORCED_EXITS_ALWAYS_TAKER = True  # invariant: never rest a limit on a forced/risk exit
# Demo gate: maker-first stays OFF live until the slippage ledger DEMONSTRATES
# the modeled fill rate + spread-leg saving on real demo fills (RUNBOOK §8). The
# EA input InpMakerFirst mirrors this (default false).
MAKER_FIRST_DEMO_GATED = True


def maker_eligible(sleeve: str, *, forced: bool) -> bool:
    """Execution-policy resolver (shared contract with the EA MakerEligible()).
    A sleeve's non-forced entry/rebalance rests a maker limit iff it is in
    MAKER_SLEEVES; forced/risk/scheduled exits ALWAYS cross (taker)."""
    if forced and FORCED_EXITS_ALWAYS_TAKER:
        return False
    return sleeve in MAKER_SLEEVES


# Informational reference equity the brain assumes (exposure is a fraction of
# LIVE equity; the EA multiplies by the real ACCOUNT_EQUITY). PROTOCOL §1.
EQUITY_REF_EUR = 10_000.0

# --------------------------------------------------------------------------- #
# Guard thresholds — the FOUR stress-battery fixes are pinned here explicitly.
# (Do NOT read these four as-written from guards_config.json.)
# --------------------------------------------------------------------------- #
# FIX 1 — OPS-3b: absolute-bp slippage, not ratio-to-backtest.
OPS3B_ALERT_BP = 1.5          # avg one-side |slippage| over the window
OPS3B_KILL_REVIEW_BP = 3.0    # sleeve-kill human review
OPS3B_WINDOW_FILLS = 20       # rolling one-side fill count
# Sleeves whose realized entry cost is the go/no-go gate on the slippage ledger.
# seasonal (NY-close roll) has always been here; v3 adds mag_xau — the magnet's
# edge is LAG-FRAGILE (a +1-day execution lag halves it; PORT_NOTES.md), so its
# live slippage/latency must be watched the same way. The OPS-3b guard already
# aggregates one-side fills across sleeves; this list names the watch set.
SLIPPAGE_WATCH_SLEEVES = ["seasonal", "mag_xau"]

# FIX 2 — OPS-6a: STRUCTURAL min-equity monitor. Report realized/target notional
# retention %, alert only on CHANGE (not a drawdown detector).
OPS6A_MIN_RETENTION = 0.50    # structural floor of interest
OPS6A_CHANGE_EPS = 0.05       # alert only when retention moves >= 5 pts vs last

# FIX 3 — OPS-8: crypto delisting/close-only => CASH-PARK the freed crypto
# weight, NEVER renormalize (renormalizing ~doubles ceiling-breach odds).
OPS8_CASH_PARK = True         # structural invariant, surfaced for clarity

# FIX 4 — MKT-7: friction guard REPLACED by the notional-ratchet cap.
MKT7_RATCHET_MULT = 1.4       # gross > 1.4x trailing-median => clamp
MKT7_MEDIAN_WINDOW_DAYS = 252

# Equity floor (OPS-6b) + margin buffer (production-quality-bar item 4).
OPS6B_EQUITY_FLOOR_EUR = 8000.0
OPS6B_DESCALE_TO = 7.0
FREE_MARGIN_BUFFER = 0.10     # keep >=10% free (executor pre-check)

# Trailing-Sharpe kill windows (F3 durability + MKT-1a), in months.
SLEEVE_SHARPE_TRIGGERS = {
    "crypto_smart": {"window_m": 24, "thresh": 0.0, "freq": "quarterly"},   # DUR
    "crypto_smart_12mo": {"sleeve": "crypto_smart", "window_m": 12, "thresh": -0.5, "freq": "monthly"},  # MKT-1a
    "seasonal": {"window_m": 12, "thresh": -0.5, "freq": "monthly"},        # DUR (needs drift co-condition)
    "intraday": {"window_m": 24, "thresh": -0.25, "freq": "quarterly"},
    "meanrev": {"window_m": 18, "thresh": -0.4, "freq": "quarterly"},
    "crisis": {"window_m": 24, "thresh": -0.8, "freq": "quarterly"},
    "trend_v2": {"window_m": 36, "thresh": -0.3, "freq": "semiannual"},
    "carry_breakout": {"window_m": 24, "thresh": -0.3, "freq": "quarterly"},
}

TRADING_DAYS_YEAR = 252

# --------------------------------------------------------------------------- #
# Config hash — MUST equal what the EA compiles from (weights, scale) so a
# mismatch (config drift) is rejected. Delegated to the SHARED reference
# contract module ea/tests/reference/targets.config_hash(weights, scale) so
# there is exactly one hash implementation across the brain, the EA reference,
# and its test suite. Inline fallback replicates that algorithm verbatim.
# --------------------------------------------------------------------------- #
def _load_ref_config_hash():
    import importlib.util
    path = WORKSPACE / "ea" / "tests" / "reference" / "targets.py"
    if not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_ref_targets", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod           # dataclass needs it registered
        spec.loader.exec_module(mod)           # pure module, no framework import
        return mod.config_hash
    except Exception:
        return None


_REF_CONFIG_HASH = _load_ref_config_hash()
_REF_SCHEMA_FOR_HASH = "2.0"                    # matches ea/tests/reference/targets.SCHEMA_VERSION


def config_hash() -> str:
    if _REF_CONFIG_HASH is not None:
        return _REF_CONFIG_HASH(SLEEVE_WEIGHTS, GLOBAL_SCALE)
    # verbatim fallback of the reference algorithm
    items = sorted((k, round(float(v), 10)) for k, v in SLEEVE_WEIGHTS.items())
    blob = json.dumps({"schema": _REF_SCHEMA_FOR_HASH,
                       "scale": round(float(GLOBAL_SCALE), 10), "weights": items},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def structural_gold_cap() -> float:
    """Rule-derived overnight |XAUUSD| anti-stacking cap (primary gold sleeve
    exposure). Mirrors ensemble.structural_gold_cap(weights, scale) = 1.62."""
    return SLEEVE_WEIGHTS["seasonal"] * GLOBAL_SCALE


def effective_gold_cap() -> float:
    """The SHIPPED overnight |XAUUSD| cap actually enforced: the structural
    rule (1.62xE today), unless a tighter explicit override is configured.
    Matches run_v2_pin.py / the official 1m pin exactly."""
    if MKT4A_OVERNIGHT_GOLD_CAP_XE is None:
        return structural_gold_cap()
    return min(MKT4A_OVERNIGHT_GOLD_CAP_XE, structural_gold_cap())


if __name__ == "__main__":
    print("Fable v3 brain config")
    print(f"  weights sum   : {WEIGHT_SUM:.3f}  (cash-park {CASH_PARK:.3f})")
    print(f"  global scale  : {GLOBAL_SCALE}")
    print(f"  engine model  : {ENGINE_MODEL}")
    print(f"  gold cap xE   : {structural_gold_cap():.3f}")
    print(f"  config hash   : {config_hash()}")
    print("  magic map     :")
    for n, m in MAGIC_OF.items():
        print(f"    {n:16s} {m}  w={SLEEVE_WEIGHTS[n]:.3f}")
