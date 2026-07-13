"""IC Markets EU retail Raw account cost model.

Components
----------
1. Commission: €2.75 per lot per side on FX + metals (EUR-denominated Raw
   account table); zero on indices and crypto (cost lives in the spread).
2. Spread: NOT modeled here — the backtester fills at the actual tick-derived
   bid/ask from the bar data (buy at ask, sell at bid).
3. Swaps: reconstructed from historical central-bank policy-rate step
   functions plus a broker markup (1%/yr each side for FX/metals; 2.5%/yr for
   index financing; punitive flat rates for crypto). Policy-rate tables are
   public knowledge encoded below; residual error (±25bp for days around a
   decision) is immaterial next to the markup. Rollover occurs at 17:00
   America/New_York (DST-correct). FX/metals: triple swap Wednesday.
   Indices: triple swap Friday. Crypto: charged every calendar day.
4. USA500 dividend adjustment: approximated as a continuous 1.5%/yr credit to
   longs / debit to shorts (S&P 500 price index pays holders of long CFDs).
   DAX is a performance (total-return) index — no dividend adjustment.
5. EUR conversion: cross rates derived from our own bar caches
   (EURUSD, EURJPY, EURGBP, EURUSD*USDCHF).

All timestamps tz-naive UTC.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config import settings as S

# ---------------------------------------------------------------------------
# Central-bank policy rates, percent per year, effective-date step functions.
# USD = Fed funds target midpoint; EUR = ECB deposit facility; GBP = BoE Bank
# Rate; JPY = BoJ policy rate; CHF = SNB policy rate; AUD = RBA cash rate;
# NZD = RBNZ OCR.
# ---------------------------------------------------------------------------
POLICY_RATES: dict[str, list[tuple[str, float]]] = {
    "USD": [
        ("2019-11-01", 1.625), ("2020-03-03", 1.125), ("2020-03-15", 0.125),
        ("2022-03-17", 0.375), ("2022-05-05", 0.875), ("2022-06-16", 1.625),
        ("2022-07-28", 2.375), ("2022-09-22", 3.125), ("2022-11-03", 3.875),
        ("2022-12-15", 4.375), ("2023-02-02", 4.625), ("2023-03-23", 4.875),
        ("2023-05-04", 5.125), ("2023-07-27", 5.375),
        ("2024-09-19", 4.875), ("2024-11-08", 4.625), ("2024-12-19", 4.375),
        ("2025-09-18", 4.125), ("2025-10-30", 3.875), ("2025-12-11", 3.625),
    ],
    "EUR": [
        ("2019-09-18", -0.50),
        ("2022-07-27", 0.00), ("2022-09-14", 0.75), ("2022-11-02", 1.50),
        ("2022-12-21", 2.00), ("2023-02-08", 2.50), ("2023-03-22", 3.00),
        ("2023-05-10", 3.25), ("2023-06-21", 3.50), ("2023-09-20", 4.00),
        ("2024-06-12", 3.75), ("2024-09-18", 3.50), ("2024-10-23", 3.25),
        ("2024-12-18", 3.00), ("2025-02-05", 2.75), ("2025-03-12", 2.50),
        ("2025-04-23", 2.25), ("2025-06-11", 2.00),
    ],
    "GBP": [
        ("2019-11-01", 0.75), ("2020-03-11", 0.25), ("2020-03-19", 0.10),
        ("2021-12-16", 0.25), ("2022-02-03", 0.50), ("2022-03-17", 0.75),
        ("2022-05-05", 1.00), ("2022-06-16", 1.25), ("2022-08-04", 1.75),
        ("2022-09-22", 2.25), ("2022-11-03", 3.00), ("2022-12-15", 3.50),
        ("2023-02-02", 4.00), ("2023-03-23", 4.25), ("2023-05-11", 4.50),
        ("2023-06-22", 5.00), ("2023-08-03", 5.25),
        ("2024-08-01", 5.00), ("2024-11-07", 4.75), ("2025-02-06", 4.50),
        ("2025-05-08", 4.25), ("2025-08-07", 4.00), ("2025-12-18", 3.75),
    ],
    "JPY": [
        ("2019-11-01", -0.10), ("2024-03-19", 0.10), ("2024-07-31", 0.25),
        ("2025-01-24", 0.50),
    ],
    "CHF": [
        ("2019-11-01", -0.75), ("2022-06-16", -0.25), ("2022-09-22", 0.50),
        ("2022-12-15", 1.00), ("2023-03-23", 1.50), ("2023-06-22", 1.75),
        ("2024-03-21", 1.50), ("2024-06-20", 1.25), ("2024-09-26", 1.00),
        ("2024-12-12", 0.50), ("2025-03-20", 0.25), ("2025-06-19", 0.00),
    ],
    "AUD": [
        ("2019-11-01", 0.75), ("2020-03-03", 0.50), ("2020-03-19", 0.25),
        ("2020-11-03", 0.10),
        ("2022-05-03", 0.35), ("2022-06-07", 0.85), ("2022-07-05", 1.35),
        ("2022-08-02", 1.85), ("2022-09-06", 2.35), ("2022-10-04", 2.60),
        ("2022-11-01", 2.85), ("2022-12-06", 3.10), ("2023-02-07", 3.35),
        ("2023-03-07", 3.60), ("2023-05-02", 3.85), ("2023-06-06", 4.10),
        ("2023-11-07", 4.35),
        ("2025-02-18", 4.10), ("2025-05-20", 3.85), ("2025-08-12", 3.60),
    ],
    "NZD": [
        ("2019-11-01", 1.00), ("2020-03-16", 0.25),
        ("2021-10-06", 0.50), ("2021-11-24", 0.75), ("2022-02-23", 1.00),
        ("2022-04-13", 1.50), ("2022-05-25", 2.00), ("2022-07-13", 2.50),
        ("2022-08-17", 3.00), ("2022-10-05", 3.50), ("2022-11-23", 4.25),
        ("2023-02-22", 4.75), ("2023-04-05", 5.25), ("2023-05-24", 5.50),
        ("2024-08-14", 5.25), ("2024-10-09", 4.75), ("2024-11-27", 4.25),
        ("2025-02-19", 3.75), ("2025-04-09", 3.50), ("2025-05-28", 3.25),
        ("2025-08-20", 3.00), ("2025-10-08", 2.50), ("2025-11-26", 2.25),
    ],
    # CAD = Bank of Canada overnight rate
    "CAD": [
        ("2019-11-01", 1.75), ("2020-03-04", 1.25), ("2020-03-16", 0.75),
        ("2020-03-27", 0.25), ("2022-03-02", 0.50), ("2022-04-13", 1.00),
        ("2022-06-01", 1.50), ("2022-07-13", 2.50), ("2022-09-07", 3.25),
        ("2022-10-26", 3.75), ("2022-12-07", 4.25), ("2023-01-25", 4.50),
        ("2023-06-07", 4.75), ("2023-07-12", 5.00),
        ("2024-06-05", 4.75), ("2024-07-24", 4.50), ("2024-09-04", 4.25),
        ("2024-10-23", 3.75), ("2024-12-11", 3.25), ("2025-01-29", 3.00),
        ("2025-03-12", 2.75),
    ],
    # NOK = Norges Bank policy rate
    "NOK": [
        ("2019-11-01", 1.50), ("2020-03-13", 1.00), ("2020-03-20", 0.25),
        ("2020-05-07", 0.00), ("2021-09-24", 0.25), ("2021-12-17", 0.50),
        ("2022-03-24", 0.75), ("2022-06-23", 1.25), ("2022-08-18", 1.75),
        ("2022-09-22", 2.25), ("2022-11-03", 2.50), ("2022-12-15", 2.75),
        ("2023-03-23", 3.00), ("2023-05-04", 3.25), ("2023-06-22", 3.75),
        ("2023-08-17", 4.00), ("2023-09-21", 4.25), ("2023-12-14", 4.50),
        ("2025-06-19", 4.25), ("2025-09-18", 4.00),
    ],
    # SEK = Riksbank policy rate
    "SEK": [
        ("2019-11-01", -0.25), ("2020-01-08", 0.00), ("2022-05-04", 0.25),
        ("2022-07-06", 0.75), ("2022-09-21", 1.75), ("2022-11-30", 2.50),
        ("2023-02-09", 3.00), ("2023-04-26", 3.50), ("2023-07-05", 3.75),
        ("2023-09-21", 4.00), ("2024-05-08", 3.75), ("2024-08-20", 3.50),
        ("2024-09-25", 3.25), ("2024-11-07", 2.75), ("2024-12-19", 2.50),
        ("2025-01-29", 2.25), ("2025-06-18", 2.00),
    ],
    # Zero-yield "currencies" for the generic swap formula
    "XAU": [("2019-11-01", 0.0)],
    "XAG": [("2019-11-01", 0.0)],
    "XPT": [("2019-11-01", 0.0)],   # platinum
    "XTI": [("2019-11-01", 0.0)],   # WTI crude
    "XBR": [("2019-11-01", 0.0)],   # Brent crude
    "XNG": [("2019-11-01", 0.0)],   # natural gas
}

# Markups recalibrated 2026-07-03 to IC Markets' actual MT5 swap sheet (see
# docs/MT5_SPEC_RECONCILIATION.md). The time-varying policy-rate carry was
# validated near-exact on XAU/JPY/EURGBP/EURUSD; only the constant markups
# (broker spread over benchmark, assumed stationary) needed adjusting.
FX_MARKUP = 1.2      # %/yr each side, FX & metals majors (was 1.0; IC ~1.1-1.3)
FX_MARKUP_OVR = {"AUDUSD": 2.0}  # AUD funding markup runs ~2%/side at IC
INDEX_MARKUP = 4.3   # %/yr each side (was 2.5; IC index financing ~benchmark+4.3)
USA500_DIV_YIELD = 0.0   # dividends treated as separate cash (conservative:
                         # IC likely credits ~+1.8%/yr to longs -> modeled upside)
CRYPTO_SWAP = {"long": -20.0, "short": 0.0}  # MT5: long -20% exact, short 0

_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


def policy_rate(ccy: str, ts: pd.Timestamp) -> float:
    """Policy rate (percent/yr) for a currency at a given time."""
    table = POLICY_RATES[ccy]
    rate = table[0][1]
    for d, r in table:
        if pd.Timestamp(d) <= ts:
            rate = r
        else:
            break
    return rate


def swap_annual_pct(inst: str, ts: pd.Timestamp) -> tuple[float, float]:
    """Annualized swap (percent of notional per year) for (long, short).

    Negative = you pay. FX/metals: rate differential minus markup each side.
    """
    cfg = S.INSTRUMENTS[inst]
    ac = cfg["asset_class"]
    if ac in ("fx", "metal"):
        rb = policy_rate(cfg["base"], ts)
        rq = policy_rate(cfg["quote"], ts)
        mk = FX_MARKUP_OVR.get(inst, FX_MARKUP)
        return (rb - rq - mk, rq - rb - mk)
    if ac == "index":
        rq = policy_rate(cfg["quote"], ts)
        div = USA500_DIV_YIELD if inst == "USA500" else 0.0
        return (-(rq + INDEX_MARKUP) + div, rq - INDEX_MARKUP - div)
    if ac == "crypto":
        return (CRYPTO_SWAP["long"], CRYPTO_SWAP["short"])
    raise ValueError(ac)


def rollover_utc(date: pd.Timestamp) -> pd.Timestamp:
    """17:00 New York on `date`, expressed as tz-naive UTC (DST-correct)."""
    local = pd.Timestamp(year=date.year, month=date.month, day=date.day,
                         hour=17, tz=_NY)
    return local.tz_convert(_UTC).tz_localize(None)


def swap_day_multiplier(inst: str, rollover_date: pd.Timestamp) -> int:
    """Days of swap charged at this rollover (weekend catch-up)."""
    ac = S.INSTRUMENTS[inst]["asset_class"]
    wd = rollover_date.weekday()  # Mon=0
    if ac in ("fx", "metal"):
        return 3 if wd == 2 else 1          # triple Wednesday (T+2)
    if ac == "index":
        return 3 if wd == 4 else 1          # triple Friday
    return 1                                 # crypto: every calendar day


class FxConverter:
    """Quote-currency → EUR conversion from our own 1m bar caches."""

    def __init__(self) -> None:
        self._idx: dict[str, np.ndarray] = {}
        self._rate: dict[str, np.ndarray] = {}
        # ccy -> (instrument(s), transform to get EUR per ccy unit)
        eurusd = self._mid("EURUSD")
        eurjpy = self._mid("EURJPY")
        eurgbp = self._mid("EURGBP")
        usdchf = self._mid("USDCHF")
        self._store("USD", eurusd.index, 1.0 / eurusd.to_numpy())
        self._store("JPY", eurjpy.index, 1.0 / eurjpy.to_numpy())
        self._store("GBP", eurgbp.index, 1.0 / eurgbp.to_numpy())
        eurchf = (eurusd * usdchf.reindex(eurusd.index).ffill()).dropna()
        self._store("CHF", eurchf.index, 1.0 / eurchf.to_numpy())

    @staticmethod
    def _mid(inst: str) -> pd.Series:
        """2020-2025 rates plus the 2026 holdout when present, so holdout
        backtests convert at live rates (audit 2026-07-02: previously froze
        2026 conversions at the last Dec-2025 rate)."""
        cols = ["bid_c", "ask_c"]
        df = pd.read_parquet(S.bars_path(inst), columns=cols)
        hp = S.bars_path(inst, holdout=True)
        if hp.exists():
            dh = pd.read_parquet(hp, columns=cols)
            df = pd.concat([df, dh])
            df = df[~df.index.duplicated(keep="first")].sort_index()
        return (df["bid_c"] + df["ask_c"]) / 2.0

    def _store(self, ccy: str, idx: pd.DatetimeIndex, rates: np.ndarray) -> None:
        self._idx[ccy] = idx.to_numpy()
        self._rate[ccy] = rates

    def eur_per(self, ccy: str, ts: pd.Timestamp | np.datetime64) -> float:
        """EUR value of 1 unit of `ccy` at the last known rate <= ts."""
        if ccy == "EUR":
            return 1.0
        i = np.searchsorted(self._idx[ccy], np.datetime64(ts), side="right") - 1
        return float(self._rate[ccy][max(i, 0)])

    def to_eur(self, amount: float, ccy: str,
               ts: pd.Timestamp | np.datetime64) -> float:
        return amount * self.eur_per(ccy, ts)


def commission_eur(inst: str, lots: float) -> float:
    """Commission per SIDE in EUR."""
    return S.INSTRUMENTS[inst]["commission_side"] * lots


def margin_eur(inst: str, lots: float, price: float, fx: FxConverter,
               ts: pd.Timestamp) -> float:
    """Required margin in EUR: notional(quote ccy)/leverage, converted."""
    cfg = S.INSTRUMENTS[inst]
    notional_quote = price * cfg["contract_size"] * lots
    return fx.to_eur(notional_quote / cfg["leverage"], cfg["quote"], ts)


def swap_eur(inst: str, side: int, lots: float, price: float,
             rollover_date: pd.Timestamp, fx: FxConverter) -> float:
    """Swap cash flow in EUR for holding through one rollover.

    side: +1 long, -1 short. Negative return = charge.
    """
    cfg = S.INSTRUMENTS[inst]
    long_pct, short_pct = swap_annual_pct(inst, rollover_date)
    pct = long_pct if side > 0 else short_pct
    mult = swap_day_multiplier(inst, rollover_date)
    notional_quote = price * cfg["contract_size"] * lots
    flow_quote = notional_quote * (pct / 100.0) / 365.0 * mult
    return fx.to_eur(flow_quote, cfg["quote"], rollover_date)
