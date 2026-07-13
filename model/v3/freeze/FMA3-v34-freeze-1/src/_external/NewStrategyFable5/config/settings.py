"""Project-wide configuration: paths, account, instrument specs.

All timestamps in this project are tz-naive UTC.
Contract specs model IC Markets EU retail Raw account under ESMA rules.
Index/crypto contract details are best-effort IC Markets approximations
(flagged per-instrument); refine before final lock if they become material.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT.parent / "data"
YEARLY_DIR = DATA_DIR / "yearly"
YTD_DIR = DATA_DIR / "2026_ytd"

CACHE_DIR = PROJECT_ROOT / "cache"
BARS_DIR = CACHE_DIR / "bars_1m"                # in-sample bar cache 2020-2025
BARS_HOLDOUT_DIR = CACHE_DIR / "bars_1m_holdout"  # 2026 YTD — final holdout only
AUDIT_DIR = CACHE_DIR / "audit"
LOG_DIR = CACHE_DIR / "logs"

IS_YEARS = list(range(2020, 2026))  # 2020..2025 inclusive — the goal period

ACCOUNT = {
    "ccy": "EUR",
    "initial": 10_000.0,
    "margin_call_level": 1.00,   # fraction of required margin
    "stop_out_level": 0.50,
    "negative_balance_protection": True,
}

# Commission per lot per side, in account currency (EUR account on IC Markets Raw).
# Reconciled 2026-07-03 to IC MT5 actual: "3.25 EUR per lot, in/out deals"
# = EUR3.25 per side (was 2.75). Index & crypto commission-free (confirmed).
_COMM_FX_METALS = 3.25

INSTRUMENTS = {
    # ---- FX (contract = 100k base units) ----
    "EURUSD": dict(asset_class="fx", base="EUR", quote="USD", contract_size=100_000,
                   pip=1e-4, leverage=30, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "GBPUSD": dict(asset_class="fx", base="GBP", quote="USD", contract_size=100_000,
                   pip=1e-4, leverage=30, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "USDJPY": dict(asset_class="fx", base="USD", quote="JPY", contract_size=100_000,
                   pip=1e-2, leverage=30, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "USDCHF": dict(asset_class="fx", base="USD", quote="CHF", contract_size=100_000,
                   pip=1e-4, leverage=30, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "EURJPY": dict(asset_class="fx", base="EUR", quote="JPY", contract_size=100_000,
                   pip=1e-2, leverage=30, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "EURGBP": dict(asset_class="fx", base="EUR", quote="GBP", contract_size=100_000,
                   pip=1e-4, leverage=30, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "AUDUSD": dict(asset_class="fx", base="AUD", quote="USD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "NZDUSD": dict(asset_class="fx", base="NZD", quote="USD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    # ---- Range-bound crosses (z-rev expansion) + EUR converters ----
    "AUDNZD": dict(asset_class="fx", base="AUD", quote="NZD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "EURCHF": dict(asset_class="fx", base="EUR", quote="CHF", contract_size=100_000,
                   pip=1e-4, leverage=30, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "AUDCAD": dict(asset_class="fx", base="AUD", quote="CAD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "NZDCAD": dict(asset_class="fx", base="NZD", quote="CAD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "CADCHF": dict(asset_class="fx", base="CAD", quote="CHF", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "EURNOK": dict(asset_class="fx", base="EUR", quote="NOK", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "EURSEK": dict(asset_class="fx", base="EUR", quote="SEK", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "EURNZD": dict(asset_class="fx", base="EUR", quote="NZD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "EURCAD": dict(asset_class="fx", base="EUR", quote="CAD", contract_size=100_000,
                   pip=1e-4, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    # ---- Carry pairs (jpy_smart expansion), JPY-quote pip=1e-2 ----
    "AUDJPY": dict(asset_class="fx", base="AUD", quote="JPY", contract_size=100_000,
                   pip=1e-2, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "NZDJPY": dict(asset_class="fx", base="NZD", quote="JPY", contract_size=100_000,
                   pip=1e-2, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "GBPJPY": dict(asset_class="fx", base="GBP", quote="JPY", contract_size=100_000,
                   pip=1e-2, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    "CADJPY": dict(asset_class="fx", base="CAD", quote="JPY", contract_size=100_000,
                   pip=1e-2, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01),
    # ---- Metals ----
    "XAUUSD": dict(asset_class="metal", base="XAU", quote="USD", contract_size=100,
                   pip=0.01, leverage=20, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    "XAGUSD": dict(asset_class="metal", base="XAG", quote="USD", contract_size=5_000,
                   pip=0.001, leverage=10, commission_side=_COMM_FX_METALS,
                   min_lot=0.01, lot_step=0.01),
    # ---- Crypto (ESMA retail 2:1; commission-free, cost in spread+financing) ----
    "BTCUSD": dict(asset_class="crypto", base="BTC", quote="USD", contract_size=1,
                   pip=0.01, leverage=2, commission_side=0.0,
                   min_lot=0.01, lot_step=0.01, approx_spec=True),
    "ETHUSD": dict(asset_class="crypto", base="ETH", quote="USD", contract_size=1,
                   pip=0.01, leverage=2, commission_side=0.0,
                   min_lot=0.01, lot_step=0.01, approx_spec=True),
    # ---- Index CFDs (1 lot = 1 index unit per point; commission-free) ----
    "DAX":    dict(asset_class="index", base="DAX", quote="EUR", contract_size=1,
                   pip=0.1, leverage=20, commission_side=0.0,
                   min_lot=0.1, lot_step=0.1, approx_spec=True),
    "USA500": dict(asset_class="index", base="SPX", quote="USD", contract_size=1,
                   pip=0.1, leverage=20, commission_side=0.0,
                   min_lot=0.1, lot_step=0.1, approx_spec=True),
    "US30":   dict(asset_class="index", base="DJI", quote="USD", contract_size=1,
                   pip=1.0, leverage=20, commission_side=0.0,
                   min_lot=0.1, lot_step=0.1, approx_spec=True),
    "USTEC":  dict(asset_class="index", base="NDX", quote="USD", contract_size=1,
                   pip=0.1, leverage=20, commission_side=0.0,
                   min_lot=0.1, lot_step=0.1, approx_spec=True),
    "JP225":  dict(asset_class="index", base="NKY", quote="JPY", contract_size=1,
                   pip=1.0, leverage=20, commission_side=0.0,
                   min_lot=0.1, lot_step=0.1, approx_spec=True),
    "UK100":  dict(asset_class="index", base="UKX", quote="GBP", contract_size=1,
                   pip=0.1, leverage=20, commission_side=0.0,
                   min_lot=0.1, lot_step=0.1, approx_spec=True),
    # ---- Energy / commodity (Donchian breakout family); metal-swap, spread-cost (comm 0) ----
    "XTIUSD": dict(asset_class="metal", base="XTI", quote="USD", contract_size=1000,
                   pip=0.01, leverage=10, commission_side=0.0, min_lot=0.01, lot_step=0.01, approx_spec=True),
    "XBRUSD": dict(asset_class="metal", base="XBR", quote="USD", contract_size=1000,
                   pip=0.01, leverage=10, commission_side=0.0, min_lot=0.01, lot_step=0.01, approx_spec=True),
    "XNGUSD": dict(asset_class="metal", base="XNG", quote="USD", contract_size=10_000,
                   pip=0.001, leverage=10, commission_side=0.0, min_lot=0.01, lot_step=0.01, approx_spec=True),
    "XPTUSD": dict(asset_class="metal", base="XPT", quote="USD", contract_size=100,
                   pip=0.01, leverage=20, commission_side=_COMM_FX_METALS, min_lot=0.01, lot_step=0.01, approx_spec=True),
    # ---- Additional crypto (crypto_mom family), ESMA 2:1, commission-free ----
    "SOLUSD": dict(asset_class="crypto", base="SOL", quote="USD", contract_size=1,
                   pip=0.01, leverage=2, commission_side=0.0, min_lot=0.01, lot_step=0.01, approx_spec=True),
    "XRPUSD": dict(asset_class="crypto", base="XRP", quote="USD", contract_size=1,
                   pip=0.0001, leverage=2, commission_side=0.0, min_lot=0.01, lot_step=0.01, approx_spec=True),
}


def yearly_tick_path(inst: str, year: int) -> Path:
    return YEARLY_DIR / f"{inst}_{year}_DUKASCOPY.parquet"


def ytd_tick_paths(inst: str) -> list[Path]:
    return sorted(YTD_DIR.glob(f"{inst}_2026-01-01_*_DUKASCOPY.parquet"))


def bars_path(inst: str, holdout: bool = False) -> Path:
    d = BARS_HOLDOUT_DIR if holdout else BARS_DIR
    suffix = "2026H1" if holdout else "2020_2025"
    return d / f"{inst}_{suffix}_1m.parquet"
