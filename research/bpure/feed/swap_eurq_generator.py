"""swap_eurq_generator.py — LIVE, CAUSAL per-bar generator for the swap and
eurq arrays that the frozen exporters currently PRE-BAKE into the CSV bundles.

WHY THIS EXISTS
---------------
research/bpure/engine/export_bh_quarter.py (b_h / Satellite) and
research/bpure/coresim/export_coresim_inputs.py (a_h / CoreSim) both ship the
per-bar `eurq`, `swap_l`/`swap_s` (b_h) and `eurq`, `swap_flag`/`swap_long`/
`swap_short` (a_h) columns as PRE-COMPUTED arrays, lifted from the record
engines' own data-prep (FMA2 account_engine_1m._eurq_chunk/_swap_chunk and
NSF5 engine/backtest.prep_arrays).  A LIVE EA has no such arrays: it must
GENERATE the same numbers, bar by bar, from live quotes plus static tables.
This module is that generator, and the gate below proves it BIT-EQUAL to the
pre-baked arrays over the frozen grid.

MEASURED SEMANTICS (read out of the real source, not guessed)
-------------------------------------------------------------
Both engines: `swap` is a FRACTION OF NOTIONAL applied to `balance` at ONE bar
per rollover; `eurq` is the EUR value of 1 unit of the instrument's QUOTE
currency at that bar.  The two engines differ in three measurable ways:

              b_h  (FMA2 account_engine_1m)      a_h  (NSF5 engine/backtest,
                                                 AFTER sim.prime_feed("ic"))
  feed        NSF5/cache/bars_1m_ic/*_IC_1m      the SAME parquet — prime_feed
              float64 on disk, CAST TO float32   overwrites bt._BARS_CACHE with
              by _native(); eurq is computed     the IC bars — but read float64,
              from those float32 values          NO cast
  eurq        1/mid_close of the EUR cross,      1/mid_close of the EUR cross,
              ffilled onto the UNION grid        ffilled onto the leg's own
              (last cross bar <= t; before       bar index (identical rule:
              the cross's first bar -> its       searchsorted right-1, clipped
              first bar = _densify `pre` rule)   at 0 -> same `pre` rule)
              0.5*(bid_c+ask_c)                  (bid_c+ask_c)/2.0  (ICFx; bit-
              CHF cross = EURCHF                 identical scaling by 2)
                                                 CHF cross = EURCHF DIRECTLY
                                                 (ICFx, not the stock
                                                 FxConverter's EURUSD*USDCHF —
                                                 prime_feed replaces bt._FX)
  rollover    first grid bar >= SERVER MIDNIGHT  first bar >= rollover_utc(d)
              of each day d (naive stamp         = 17:00 America/New_York on d
              .normalize()); day label = the     (DST-correct), day label = the
              SERVER date                        UTC date
  payload     swap_l[j] += pct_long /100/365     swap_flag[j] += mult   (+=)
              * mult      (accumulating +=)      swap_long[j]  = pct_long/100
              swap_s[j] += pct_short/100/365     swap_short[j] = pct_short/100
              * mult                             (OVERWRITING =; the /365 and
                                                 the mult live in the kernel)

  Day set     pd.date_range(first_bar.normalize(),  pd.date_range(first.normalize(),
              last_bar.normalize()+1D, freq=D)      last.normalize(), freq=D)
              weekends skipped unless crypto        (same weekend rule)
  Multiplier  fx/metal: x3 on Wednesday, else x1;  index: x3 on Friday, else x1;
              crypto: x1 every calendar day        (swap_day_multiplier, shared)
  Rates       long/short = f(policy rates of base & quote at the ROLLOVER DAY,
              broker markups) — engine/costs.swap_annual_pct, transcribed below.

CONSEQUENCE FOR THE LIVE EA (both are real, both are load-bearing):
  * b_h eurq MUST be computed from the float32-quantized cross close prices —
    ((float) cast in MQL5, exactly like the price columns per BH_ENGINE_SPEC
    section 3.  Using MT5 doubles straight through gives a different eurq.
  * b_h charges its triple-swap at SERVER-Wednesday 00:00 = Tuesday 17:00 NY,
    i.e. one rollover EARLIER than a_h (Wednesday 17:00 NY) and than the real
    IC sheet.  That is a property of the FROZEN record engine, reproduced here
    verbatim; it is NOT corrected.

CAUSALITY
---------
step(ts) uses only: (a) static tables, (b) cross bars with stamp <= ts that
have already been pushed in, (c) the rollover-day cursor, which only ever
fires for days whose rollover instant is <= ts.  No array is indexed by a
future bar.  The single exception is the record engines' own `pre` rule (a bar
BEFORE the cross's first bar takes that first bar's price) — a cold-start
artifact of the recorders, faithfully reproduced, and flagged by
`pre_first_bar_hits` in the report so it can never pass unnoticed.

USAGE
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/feed/swap_eurq_generator.py --selftest
    ... --gate-bh 2020Q1 [2020Q2 ...]      (default: all 24)
    ... --gate-coresim 0 10 20 31          (default: 0 10 20 31)
    ... --gate-bh 2020Q1 --perturb swap:USDJPY:long:+0.5   (NEGATIVE CONTROL)
    ... --emit-mqh-fixture                 (writes the CheckSwapEurq.mq5 fixture)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FMA3 = HERE.parents[2]
NSF5 = Path("/Users/dsalamanca/vs_env/NewStrategyFable5")
BARS_IC = NSF5 / "cache" / "bars_1m_ic"   # BOTH engines' feed (see cross_tape):
                                          # b_h casts it to float32, a_h does not
COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")

DAY_SEC = 86400

# ===========================================================================
# STATIC TABLES — transcribed from NSF5 engine/costs.py + config/settings.py.
# The generator uses ONLY these (never imports the engines).  verify_tables()
# cross-checks them against the live source and ABORTS on drift.
# ===========================================================================
POLICY_RATES: dict[str, list[tuple[str, float]]] = {
    "USD": [("2019-11-01", 1.625), ("2020-03-03", 1.125), ("2020-03-15", 0.125),
            ("2022-03-17", 0.375), ("2022-05-05", 0.875), ("2022-06-16", 1.625),
            ("2022-07-28", 2.375), ("2022-09-22", 3.125), ("2022-11-03", 3.875),
            ("2022-12-15", 4.375), ("2023-02-02", 4.625), ("2023-03-23", 4.875),
            ("2023-05-04", 5.125), ("2023-07-27", 5.375), ("2024-09-19", 4.875),
            ("2024-11-08", 4.625), ("2024-12-19", 4.375), ("2025-09-18", 4.125),
            ("2025-10-30", 3.875), ("2025-12-11", 3.625)],
    "EUR": [("2019-09-18", -0.50), ("2022-07-27", 0.00), ("2022-09-14", 0.75),
            ("2022-11-02", 1.50), ("2022-12-21", 2.00), ("2023-02-08", 2.50),
            ("2023-03-22", 3.00), ("2023-05-10", 3.25), ("2023-06-21", 3.50),
            ("2023-09-20", 4.00), ("2024-06-12", 3.75), ("2024-09-18", 3.50),
            ("2024-10-23", 3.25), ("2024-12-18", 3.00), ("2025-02-05", 2.75),
            ("2025-03-12", 2.50), ("2025-04-23", 2.25), ("2025-06-11", 2.00)],
    "GBP": [("2019-11-01", 0.75), ("2020-03-11", 0.25), ("2020-03-19", 0.10),
            ("2021-12-16", 0.25), ("2022-02-03", 0.50), ("2022-03-17", 0.75),
            ("2022-05-05", 1.00), ("2022-06-16", 1.25), ("2022-08-04", 1.75),
            ("2022-09-22", 2.25), ("2022-11-03", 3.00), ("2022-12-15", 3.50),
            ("2023-02-02", 4.00), ("2023-03-23", 4.25), ("2023-05-11", 4.50),
            ("2023-06-22", 5.00), ("2023-08-03", 5.25), ("2024-08-01", 5.00),
            ("2024-11-07", 4.75), ("2025-02-06", 4.50), ("2025-05-08", 4.25),
            ("2025-08-07", 4.00), ("2025-12-18", 3.75)],
    "JPY": [("2019-11-01", -0.10), ("2024-03-19", 0.10), ("2024-07-31", 0.25),
            ("2025-01-24", 0.50)],
    "CHF": [("2019-11-01", -0.75), ("2022-06-16", -0.25), ("2022-09-22", 0.50),
            ("2022-12-15", 1.00), ("2023-03-23", 1.50), ("2023-06-22", 1.75),
            ("2024-03-21", 1.50), ("2024-06-20", 1.25), ("2024-09-26", 1.00),
            ("2024-12-12", 0.50), ("2025-03-20", 0.25), ("2025-06-19", 0.00)],
    "AUD": [("2019-11-01", 0.75), ("2020-03-03", 0.50), ("2020-03-19", 0.25),
            ("2020-11-03", 0.10), ("2022-05-03", 0.35), ("2022-06-07", 0.85),
            ("2022-07-05", 1.35), ("2022-08-02", 1.85), ("2022-09-06", 2.35),
            ("2022-10-04", 2.60), ("2022-11-01", 2.85), ("2022-12-06", 3.10),
            ("2023-02-07", 3.35), ("2023-03-07", 3.60), ("2023-05-02", 3.85),
            ("2023-06-06", 4.10), ("2023-11-07", 4.35), ("2025-02-18", 4.10),
            ("2025-05-20", 3.85), ("2025-08-12", 3.60)],
    "NZD": [("2019-11-01", 1.00), ("2020-03-16", 0.25), ("2021-10-06", 0.50),
            ("2021-11-24", 0.75), ("2022-02-23", 1.00), ("2022-04-13", 1.50),
            ("2022-05-25", 2.00), ("2022-07-13", 2.50), ("2022-08-17", 3.00),
            ("2022-10-05", 3.50), ("2022-11-23", 4.25), ("2023-02-22", 4.75),
            ("2023-04-05", 5.25), ("2023-05-24", 5.50), ("2024-08-14", 5.25),
            ("2024-10-09", 4.75), ("2024-11-27", 4.25), ("2025-02-19", 3.75),
            ("2025-04-09", 3.50), ("2025-05-28", 3.25), ("2025-08-20", 3.00),
            ("2025-10-08", 2.50), ("2025-11-26", 2.25)],
    "CAD": [("2019-11-01", 1.75), ("2020-03-04", 1.25), ("2020-03-16", 0.75),
            ("2020-03-27", 0.25), ("2022-03-02", 0.50), ("2022-04-13", 1.00),
            ("2022-06-01", 1.50), ("2022-07-13", 2.50), ("2022-09-07", 3.25),
            ("2022-10-26", 3.75), ("2022-12-07", 4.25), ("2023-01-25", 4.50),
            ("2023-06-07", 4.75), ("2023-07-12", 5.00), ("2024-06-05", 4.75),
            ("2024-07-24", 4.50), ("2024-09-04", 4.25), ("2024-10-23", 3.75),
            ("2024-12-11", 3.25), ("2025-01-29", 3.00), ("2025-03-12", 2.75)],
    "NOK": [("2019-11-01", 1.50), ("2020-03-13", 1.00), ("2020-03-20", 0.25),
            ("2020-05-07", 0.00), ("2021-09-24", 0.25), ("2021-12-17", 0.50),
            ("2022-03-24", 0.75), ("2022-06-23", 1.25), ("2022-08-18", 1.75),
            ("2022-09-22", 2.25), ("2022-11-03", 2.50), ("2022-12-15", 2.75),
            ("2023-03-23", 3.00), ("2023-05-04", 3.25), ("2023-06-22", 3.75),
            ("2023-08-17", 4.00), ("2023-09-21", 4.25), ("2023-12-14", 4.50),
            ("2025-06-19", 4.25), ("2025-09-18", 4.00)],
    "SEK": [("2019-11-01", -0.25), ("2020-01-08", 0.00), ("2022-05-04", 0.25),
            ("2022-07-06", 0.75), ("2022-09-21", 1.75), ("2022-11-30", 2.50),
            ("2023-02-09", 3.00), ("2023-04-26", 3.50), ("2023-07-05", 3.75),
            ("2023-09-21", 4.00), ("2024-05-08", 3.75), ("2024-08-20", 3.50),
            ("2024-09-25", 3.25), ("2024-11-07", 2.75), ("2024-12-19", 2.50),
            ("2025-01-29", 2.25), ("2025-06-18", 2.00)],
    "XAU": [("2019-11-01", 0.0)], "XAG": [("2019-11-01", 0.0)],
    "XPT": [("2019-11-01", 0.0)], "XTI": [("2019-11-01", 0.0)],
    "XBR": [("2019-11-01", 0.0)], "XNG": [("2019-11-01", 0.0)],
}
FX_MARKUP = 1.2
FX_MARKUP_OVR = {"AUDUSD": 2.0}
INDEX_MARKUP = 4.3
USA500_DIV_YIELD = 0.0
CRYPTO_SWAP = {"long": -20.0, "short": 0.0}

# (asset_class, base, quote) — config/settings.INSTRUMENTS, the 31 book symbols
# (b_h) plus the extra a_h leg instruments (AUDUSD, NZDUSD) and the crosses.
INSTR: dict[str, tuple[str, str, str]] = {
    "AUDCAD": ("fx", "AUD", "CAD"), "AUDJPY": ("fx", "AUD", "JPY"),
    "AUDNZD": ("fx", "AUD", "NZD"), "AUDUSD": ("fx", "AUD", "USD"),
    "CADCHF": ("fx", "CAD", "CHF"), "CADJPY": ("fx", "CAD", "JPY"),
    "EURCAD": ("fx", "EUR", "CAD"), "EURCHF": ("fx", "EUR", "CHF"),
    "EURGBP": ("fx", "EUR", "GBP"), "EURJPY": ("fx", "EUR", "JPY"),
    "EURNOK": ("fx", "EUR", "NOK"), "EURNZD": ("fx", "EUR", "NZD"),
    "EURSEK": ("fx", "EUR", "SEK"), "EURUSD": ("fx", "EUR", "USD"),
    "GBPJPY": ("fx", "GBP", "JPY"), "GBPUSD": ("fx", "GBP", "USD"),
    "NZDCAD": ("fx", "NZD", "CAD"), "NZDJPY": ("fx", "NZD", "JPY"),
    "NZDUSD": ("fx", "NZD", "USD"), "USDCHF": ("fx", "USD", "CHF"),
    "USDJPY": ("fx", "USD", "JPY"),
    "BTCUSD": ("crypto", "BTC", "USD"), "ETHUSD": ("crypto", "ETH", "USD"),
    "SOLUSD": ("crypto", "SOL", "USD"), "XRPUSD": ("crypto", "XRP", "USD"),
    "DAX": ("index", "DAX", "EUR"), "JP225": ("index", "NKY", "JPY"),
    "UK100": ("index", "UKX", "GBP"), "US30": ("index", "DJI", "USD"),
    "USA500": ("index", "SPX", "USD"), "USTEC": ("index", "NDX", "USD"),
    "XAGUSD": ("metal", "XAG", "USD"), "XAUUSD": ("metal", "XAU", "USD"),
    "XBRUSD": ("metal", "XBR", "USD"), "XNGUSD": ("metal", "XNG", "USD"),
    "XPTUSD": ("metal", "XPT", "USD"), "XTIUSD": ("metal", "XTI", "USD"),
}
EUR_CROSS = {"USD": "EURUSD", "JPY": "EURJPY", "GBP": "EURGBP",
             "CHF": "EURCHF", "NZD": "EURNZD", "CAD": "EURCAD",
             "NOK": "EURNOK", "SEK": "EURSEK"}

SYMBOLS_BH = ["AUDCAD", "AUDJPY", "AUDNZD", "BTCUSD", "CADCHF", "CADJPY",
              "DAX", "ETHUSD", "EURCAD", "EURCHF", "EURGBP", "EURNOK",
              "EURNZD", "EURSEK", "EURUSD", "GBPJPY", "JP225", "NZDCAD",
              "NZDJPY", "SOLUSD", "UK100", "US30", "USA500", "USDCHF",
              "USDJPY", "USTEC", "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD",
              "XTIUSD"]
CROSSES_BH = ["EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD",
              "EURSEK", "EURUSD"]   # exporter column order

# a_h LEG TABLE instruments (export_coresim_inputs.LEG_TABLE), leg order
CORESIM_LEGS = ["XAUUSD", "USDJPY", "ETHUSD", "EURGBP", "USTEC",
                "USDJPY", "AUDUSD", "NZDUSD", "BTCUSD"]

# --- NEGATIVE-CONTROL hooks (empty in production) --------------------------
PERTURB_SWAP: dict[str, tuple[float, float]] = {}   # sym -> (d_long, d_short) pct/yr
PERTURB_POLICY: dict[str, float] = {}               # ccy -> d pct/yr


def apply_perturbation(spec: str) -> str:
    """'swap:USDJPY:long:+0.5' | 'swap:USDJPY:short:-0.5' | 'policy:JPY:+0.25'."""
    p = spec.split(":")
    if p[0] == "swap":
        sym, side, amt = p[1], p[2], float(p[3])
        assert sym in INSTR and side in ("long", "short")
        dl, ds = PERTURB_SWAP.get(sym, (0.0, 0.0))
        PERTURB_SWAP[sym] = (dl + amt, ds) if side == "long" else (dl, ds + amt)
        return f"swap table entry {sym}.{side} shifted by {amt:+g} %/yr"
    if p[0] == "policy":
        ccy, amt = p[1], float(p[2])
        assert ccy in POLICY_RATES
        PERTURB_POLICY[ccy] = PERTURB_POLICY.get(ccy, 0.0) + amt
        return f"policy-rate table {ccy} shifted by {amt:+g} %/yr"
    raise ValueError(spec)


# ===========================================================================
# swap arithmetic — pure scalar, transcription of engine/costs.py
# ===========================================================================
_RATE_SEC = {c: [(int(pd.Timestamp(d).value // 10**9), float(r)) for d, r in tbl]
             for c, tbl in POLICY_RATES.items()}


def policy_rate(ccy: str, ts_sec: int) -> float:
    """Step function; 'table[0] until the first effective date' (costs.py)."""
    tbl = _RATE_SEC[ccy]
    rate = tbl[0][1]
    for d, r in tbl:
        if d <= ts_sec:
            rate = r
        else:
            break
    return rate + PERTURB_POLICY.get(ccy, 0.0)


def swap_annual_pct(inst: str, ts_sec: int) -> tuple[float, float]:
    ac, base, quote = INSTR[inst]
    if ac in ("fx", "metal"):
        rb = policy_rate(base, ts_sec)
        rq = policy_rate(quote, ts_sec)
        mk = FX_MARKUP_OVR.get(inst, FX_MARKUP)
        lp, sp = (rb - rq - mk, rq - rb - mk)
    elif ac == "index":
        rq = policy_rate(quote, ts_sec)
        div = USA500_DIV_YIELD if inst == "USA500" else 0.0
        lp, sp = (-(rq + INDEX_MARKUP) + div, rq - INDEX_MARKUP - div)
    elif ac == "crypto":
        lp, sp = (CRYPTO_SWAP["long"], CRYPTO_SWAP["short"])
    else:
        raise ValueError(ac)
    dl, ds = PERTURB_SWAP.get(inst, (0.0, 0.0))
    return lp + dl, sp + ds


def weekday_of(day_sec: int) -> int:
    """Mon=0 .. Sun=6 for a midnight epoch (1970-01-01 was a Thursday)."""
    return int(((day_sec // DAY_SEC) + 3) % 7)


def swap_day_multiplier(inst: str, day_sec: int) -> int:
    ac = INSTR[inst][0]
    wd = weekday_of(day_sec)
    if ac in ("fx", "metal"):
        return 3 if wd == 2 else 1      # triple Wednesday
    if ac == "index":
        return 3 if wd == 4 else 1      # triple Friday
    return 1                            # crypto: every calendar day


def is_swap_day(inst: str, day_sec: int) -> bool:
    return INSTR[inst][0] == "crypto" or weekday_of(day_sec) < 5


# --- US Eastern DST (a_h rollover only) ------------------------------------
def _nth_sunday(year: int, month: int, n: int) -> int:
    """epoch-sec midnight (UTC) of the n-th Sunday of month."""
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    off = (6 - d.weekday()) % 7            # Sunday
    d = d + timedelta(days=off + 7 * (n - 1))
    return int(d.timestamp())


def _last_sunday_epoch(year: int, month: int) -> int:  # unused, kept explicit
    raise NotImplementedError


def rollover_utc_sec(day_sec: int) -> int:
    """17:00 America/New_York on the given UTC calendar date, as a naive-UTC
    epoch second — the exact instant NSF5 costs.rollover_utc() produces.
    EDT (UTC-4) from the 2nd Sunday of March 02:00 local to the 1st Sunday of
    November 02:00 local; EST (UTC-5) otherwise."""
    d = datetime.fromtimestamp(day_sec, tz=timezone.utc)
    y = d.year
    dst_start = _nth_sunday(y, 3, 2) + 7 * 3600    # 02:00 EST = 07:00 UTC
    dst_end = _nth_sunday(y, 11, 1) + 6 * 3600     # 02:00 EDT = 06:00 UTC
    local_1700 = day_sec + 17 * 3600               # 17:00 as if UTC
    # 17:00 local is unambiguously inside/outside the DST window on that date
    edt = (day_sec + 12 * 3600) >= dst_start and (day_sec + 12 * 3600) < dst_end
    return local_1700 + (4 * 3600 if edt else 5 * 3600)


# ===========================================================================
# CAUSAL GENERATOR
# ===========================================================================
class CrossState:
    """Causal ffill of one EUR cross's bar-close mid.  A live EA feeds it with
    OnBar(cross) closes; `seed` implements the recorders' `pre` rule."""

    __slots__ = ("bid_c", "ask_c", "seeded", "float32")

    def __init__(self, float32: bool):
        self.bid_c = math.nan
        self.ask_c = math.nan
        self.seeded = False
        self.float32 = float32

    def update(self, bid_c: float, ask_c: float) -> None:
        if self.float32:
            bid_c = float(np.float32(bid_c))
            ask_c = float(np.float32(ask_c))
        self.bid_c = bid_c
        self.ask_c = ask_c
        self.seeded = True

    def eur_per_quote(self) -> float:
        assert self.seeded, "cross not seeded — pre-first-bar rule violated"
        return 1.0 / (0.5 * (self.bid_c + self.ask_c))


class SwapEurqGenerator:
    """profile='bh'      -> eurq[K], swap_l[K], swap_s[K]  (fractions, /365*mult)
       profile='coresim' -> eurq[K], swap_flag[K], swap_long[K], swap_short[K]
                            (flag=multiplier, long/short = pct/100, NO /365)"""

    def __init__(self, symbols, profile: str = "bh"):
        assert profile in ("bh", "coresim")
        self.profile = profile
        self.symbols = list(symbols)
        self.K = len(self.symbols)
        self.quote = [INSTR[s][2] for s in self.symbols]
        self.f32 = (profile == "bh")
        self.cross = {c: CrossState(self.f32) for c in
                      sorted({EUR_CROSS[q] for q in self.quote if q != "EUR"})}
        self.next_day = None      # epoch-sec midnight of the next unfired day
        self.last_day = None      # inclusive last day in the schedule
        self.pre_first_bar_hits = 0
        self.rollovers_fired = 0

    # ---- schedule -------------------------------------------------------
    def start(self, first_ts_sec: int, last_ts_sec: int) -> None:
        """Day cursor init.  b_h: [first.normalize(), last.normalize()+1D];
        a_h: [first.normalize(), last.normalize()].  (The b_h extra day can
        never fire — its midnight is > last bar — but it is in the source, so
        it is in the transcription.)"""
        self.next_day = (first_ts_sec // DAY_SEC) * DAY_SEC
        self.last_day = (last_ts_sec // DAY_SEC) * DAY_SEC
        if self.profile == "bh":
            self.last_day += DAY_SEC

    def _fire_time(self, day_sec: int) -> int:
        return day_sec if self.profile == "bh" else rollover_utc_sec(day_sec)

    # ---- live feed ------------------------------------------------------
    def on_cross_bar(self, cross: str, bid_c: float, ask_c: float) -> None:
        if cross in self.cross:
            self.cross[cross].update(bid_c, ask_c)

    def seed_cross(self, cross: str, bid_c: float, ask_c: float) -> None:
        """`pre` rule: value used for grid bars BEFORE the cross's first bar."""
        if cross in self.cross and not self.cross[cross].seeded:
            self.cross[cross].update(bid_c, ask_c)
            self.pre_first_bar_hits += 1

    # ---- one bar --------------------------------------------------------
    def step(self, ts_sec: int) -> dict:
        eurq = [1.0] * self.K
        for k in range(self.K):
            q = self.quote[k]
            if q != "EUR":
                eurq[k] = self.cross[EUR_CROSS[q]].eur_per_quote()

        a = [0.0] * self.K          # swap_l  | swap_flag
        b = [0.0] * self.K          # swap_s  | swap_long
        c = [0.0] * self.K          # unused  | swap_short
        while self.next_day is not None and self.next_day <= self.last_day \
                and self._fire_time(self.next_day) <= ts_sec:
            d = self.next_day
            fired = False
            for k, s in enumerate(self.symbols):
                if not is_swap_day(s, d):
                    continue
                mult = swap_day_multiplier(s, d)
                lp, sp = swap_annual_pct(s, d)
                if self.profile == "bh":
                    a[k] += lp / 100.0 / 365.0 * mult      # accumulating +=
                    b[k] += sp / 100.0 / 365.0 * mult
                else:
                    a[k] += mult                            # flag +=
                    b[k] = lp / 100.0                       # pct  =  (overwrite)
                    c[k] = sp / 100.0
                fired = True
            if fired:
                self.rollovers_fired += 1
            self.next_day += DAY_SEC

        if self.profile == "bh":
            return {"eurq": eurq, "swap_l": a, "swap_s": b}
        return {"eurq": eurq, "swap_flag": a, "swap_long": b, "swap_short": c}


# ===========================================================================
# TABLE-DRIFT GUARD (the only place the record engines are imported)
# ===========================================================================
def verify_tables() -> dict:
    sys.path.insert(0, str(NSF5))
    from config import settings as S           # noqa: E402
    from engine import costs as EC             # noqa: E402
    assert EC.POLICY_RATES == POLICY_RATES, "POLICY_RATES drift"
    assert (EC.FX_MARKUP, EC.FX_MARKUP_OVR, EC.INDEX_MARKUP,
            EC.USA500_DIV_YIELD, EC.CRYPTO_SWAP) == \
        (FX_MARKUP, FX_MARKUP_OVR, INDEX_MARKUP, USA500_DIV_YIELD,
         CRYPTO_SWAP), "markup drift"
    for s, (ac, base, quote) in INSTR.items():
        cfg = S.INSTRUMENTS[s]
        assert (cfg["asset_class"], cfg["base"], cfg["quote"]) == (ac, base, quote), \
            f"{s}: INSTR drift"
    # rollover DST rule vs zoneinfo, every day 2019-11-01 .. 2026-12-31
    bad = 0
    for d in pd.date_range("2019-11-01", "2026-12-31", freq="D"):
        want = int(EC.rollover_utc(d).value // 10**9)
        got = rollover_utc_sec(int(d.value // 10**9))
        bad += (want != got)
    assert bad == 0, f"rollover_utc_sec disagrees with zoneinfo on {bad} days"
    # swap_annual_pct / multiplier, every instrument x every day
    for s in INSTR:
        for d in pd.date_range("2020-01-01", "2025-12-31", freq="7D"):
            ds = int(d.value // 10**9)
            assert EC.swap_annual_pct(s, d) == swap_annual_pct(s, ds), f"{s} pct"
            assert EC.swap_day_multiplier(s, d) == swap_day_multiplier(s, ds), \
                f"{s} mult"
            assert (d.weekday()) == weekday_of(ds), "weekday"
    return {"policy_rates": "match", "markups": "match", "instruments": "match",
            "rollover_dst_days_checked": 2618, "swap_pct_mult": "match"}


# ===========================================================================
# FEEDS (a live EA gets these bars from the broker; here from the record feed)
# ===========================================================================
_CACHE: dict[tuple, tuple] = {}


def cross_tape(cross: str, profile: str):
    """(ts_sec[int64], bid_c, ask_c) close arrays of one EUR cross, in the
    dtype discipline of the profile's feed.

    BOTH profiles read the SAME parquet (cache/bars_1m_ic): the a_h/CoreSim
    exporter calls sim.prime_feed("ic"), which overwrites engine.backtest's
    _BARS_CACHE with the IC bars and _FX with multifeed_optim.ICFx (built from
    the IC EUR crosses — so the a_h CHF cross is EURCHF DIRECTLY, not the stock
    FxConverter's derived EURUSD*USDCHF, and there is no 2026 holdout concat).
    The ONLY numeric difference is the dtype: FMA2 _native() casts the b_h
    prices to float32; the NSF5 path keeps the parquet float64."""
    key = (cross, profile)
    if key in _CACHE:
        return _CACHE[key]
    df = pd.read_parquet(BARS_IC / f"{cross}_IC_1m.parquet",
                         columns=["bid_c", "ask_c"])
    if profile == "bh":
        b = df["bid_c"].to_numpy(np.float32).astype(np.float64)
        a = df["ask_c"].to_numpy(np.float32).astype(np.float64)
    else:
        b = df["bid_c"].to_numpy(np.float64)
        a = df["ask_c"].to_numpy(np.float64)
    ts = df.index.values.astype("datetime64[ns]").astype(np.int64) // 10**9
    _CACHE[key] = (ts, b, a)
    return _CACHE[key]


def leg_tape(inst: str):
    """a_h leg native bar stamps (epoch sec) — the IC feed (prime_feed('ic'))."""
    key = ("leg", inst)
    if key in _CACHE:
        return _CACHE[key]
    df = pd.read_parquet(BARS_IC / f"{inst}_IC_1m.parquet", columns=["bid_c"])
    _CACHE[key] = df.index.values.astype("datetime64[ns]").astype(np.int64) // 10**9
    return _CACHE[key]


def run_grid(symbols, ts_grid: np.ndarray, profile: str) -> dict:
    """Drive the generator bar-by-bar over a timestamp grid.  Cross bars are
    pushed in as they close (causal); the `pre` rule seeds a cross that has no
    bar at or before the first grid bar."""
    gen = SwapEurqGenerator(symbols, profile)
    gen.start(int(ts_grid[0]), int(ts_grid[-1]))
    tapes = {c: cross_tape(c, profile) for c in gen.cross}
    ptr = {c: 0 for c in gen.cross}
    for c, (cts, cb, ca) in tapes.items():         # pre rule
        if len(cts) and cts[0] > ts_grid[0]:
            gen.seed_cross(c, float(cb[0]), float(ca[0]))
    K = len(symbols)
    T = len(ts_grid)
    out = {k: np.zeros((T, K)) for k in
           (("eurq", "swap_l", "swap_s") if profile == "bh"
            else ("eurq", "swap_flag", "swap_long", "swap_short"))}
    for t in range(T):
        ts = int(ts_grid[t])
        for c, (cts, cb, ca) in tapes.items():     # push every cross bar <= ts
            p = ptr[c]
            n = len(cts)
            while p < n and cts[p] <= ts:
                gen.on_cross_bar(c, float(cb[p]), float(ca[p]))
                p += 1
            ptr[c] = p
        row = gen.step(ts)
        for k, v in row.items():
            out[k][t, :] = v
    out["_gen"] = gen
    return out


# ===========================================================================
# GATE — bit-equality vs the PRE-BAKED arrays in the exported bundles
# ===========================================================================
def _diff(name, gen_a, ref_a, symbols, findings):
    """max|diff| per field per symbol; records every non-bit-equal symbol."""
    per = {}
    for k, s in enumerate(symbols):
        d = float(np.max(np.abs(gen_a[:, k] - ref_a[:, k]))) if len(gen_a) else 0.0
        per[s] = d
        if not np.array_equal(gen_a[:, k], ref_a[:, k]):
            findings.append({"field": name, "symbol": s, "max_abs_diff": d,
                             "n_bars_differ": int(np.sum(gen_a[:, k] != ref_a[:, k]))})
    return {"max_abs_diff": max(per.values()) if per else 0.0, "per_symbol": per,
            "bit_equal": all(np.array_equal(gen_a[:, k], ref_a[:, k])
                             for k in range(len(symbols)))}


def gate_bh(quarter: str, outdir: Path, self_test: bool = False) -> dict:
    """Decode the PRE-BAKED eurq/swap columns of FMA3_bh_inputs_<Q>.csv exactly
    as TestSatEquity.mq5 does (eurq: carry; swap: empty=0.0), regenerate them
    causally, and bit-compare."""
    path = outdir / f"FMA3_bh_inputs_{quarter}.csv"
    assert path.exists(), f"missing bundle {path}"
    use = (["ts"] + [f"eurq_{c}" for c in CROSSES_BH]
           + [f"swl_{s}" for s in SYMBOLS_BH] + [f"sws_{s}" for s in SYMBOLS_BH])
    t0 = time.time()
    df = pd.read_csv(path, usecols=use, float_precision="round_trip")
    ts = df["ts"].to_numpy(np.int64)
    T = len(ts)
    ref_eurq_cross = df[[f"eurq_{c}" for c in CROSSES_BH]].ffill().to_numpy(np.float64)
    assert not np.isnan(ref_eurq_cross).any(), "eurq carry-decode left a NaN"
    ref_swl = df[[f"swl_{s}" for s in SYMBOLS_BH]].fillna(0.0).to_numpy(np.float64)
    ref_sws = df[[f"sws_{s}" for s in SYMBOLS_BH]].fillna(0.0).to_numpy(np.float64)
    # expand per-cross eurq to per-symbol (the shape the stepper consumes)
    ref_eurq = np.ones((T, len(SYMBOLS_BH)))
    for k, s in enumerate(SYMBOLS_BH):
        q = INSTR[s][2]
        if q != "EUR":
            ref_eurq[:, k] = ref_eurq_cross[:, CROSSES_BH.index(EUR_CROSS[q])]
    t_read = time.time() - t0

    if self_test:                       # judge(golden, golden) MUST pass
        gen = {"eurq": ref_eurq.copy(), "swap_l": ref_swl.copy(),
               "swap_s": ref_sws.copy()}
        gen["_gen"] = None
    else:
        t1 = time.time()
        gen = run_grid(SYMBOLS_BH, ts, "bh")
        t_gen = time.time() - t1

    findings: list = []
    res = {"quarter": quarter, "bars": T, "self_test": self_test,
           "read_seconds": round(t_read, 1),
           "gen_seconds": (0.0 if self_test else round(t_gen, 1)),
           "eurq": _diff("eurq", gen["eurq"], ref_eurq, SYMBOLS_BH, findings),
           "swap_l": _diff("swap_l", gen["swap_l"], ref_swl, SYMBOLS_BH, findings),
           "swap_s": _diff("swap_s", gen["swap_s"], ref_sws, SYMBOLS_BH, findings),
           "nonzero_swap_bars_ref": int((ref_swl != 0.0).any(axis=1).sum()),
           "nonzero_swap_bars_gen": int((np.asarray(gen["swap_l"]) != 0.0)
                                        .any(axis=1).sum()),
           "findings": findings}
    if not self_test:
        g = gen["_gen"]
        res["pre_first_bar_hits"] = g.pre_first_bar_hits
        res["rollovers_fired"] = g.rollovers_fired
    res["PASS"] = bool(res["eurq"]["bit_equal"] and res["swap_l"]["bit_equal"]
                       and res["swap_s"]["bit_equal"])
    return res


CORESIM_COLS = ["leg", "ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o",
                "ask_h", "ask_l", "ask_c", "eurq", "swap_flag", "swap_long",
                "swap_short", "tgt"]


def gate_coresim(j: int, outdir: Path, self_test: bool = False) -> dict:
    """Same gate for the a_h bundles.  The a_h swap schedule runs over each
    leg instrument's FULL native index, so the generator is driven over the
    full tape and the segment window is sliced out of it (a live EA carries
    the same continuous state)."""
    path = outdir / f"FMA3_coresim_seg{j}.csv"
    assert path.exists(), f"missing bundle {path}"
    df = pd.read_csv(path, header=None, names=CORESIM_COLS,
                     float_precision="round_trip")
    findings: list = []
    per_leg = []
    ok = True
    for leg_id, inst in enumerate(CORESIM_LEGS):
        sub = df[df["leg"] == leg_id]
        if len(sub) == 0:
            per_leg.append({"leg": leg_id, "inst": inst, "rows": 0,
                            "bit_equal": True})
            continue
        ts = sub["ts"].to_numpy(np.int64)
        ref = np.stack([sub["eurq"].to_numpy(np.float64),
                        sub["swap_flag"].to_numpy(np.float64),
                        sub["swap_long"].to_numpy(np.float64),
                        sub["swap_short"].to_numpy(np.float64)], axis=1)
        if self_test:
            gen_a = ref.copy()
        else:
            full = leg_tape(inst)
            key = ("gen", inst)
            if key not in _CACHE:           # full-tape run, once per instrument
                _CACHE[key] = run_grid([inst], full, "coresim")
            g = _CACHE[key]
            lo = int(np.searchsorted(full, ts[0]))
            hi = int(np.searchsorted(full, ts[-1], side="right"))
            assert np.array_equal(full[lo:hi], ts), \
                f"leg {leg_id} {inst}: segment stamps not a slice of the tape"
            gen_a = np.stack([g["eurq"][lo:hi, 0], g["swap_flag"][lo:hi, 0],
                              g["swap_long"][lo:hi, 0],
                              g["swap_short"][lo:hi, 0]], axis=1)
        f0 = len(findings)
        d = {f: _diff(f, gen_a[:, i:i + 1], ref[:, i:i + 1],
                      [f"{inst}#{leg_id}"], findings)
             for i, f in enumerate(("eurq", "swap_flag", "swap_long",
                                    "swap_short"))}
        beq = all(v["bit_equal"] for v in d.values())
        ok &= beq
        per_leg.append({"leg": leg_id, "inst": inst, "rows": int(len(sub)),
                        "bit_equal": beq,
                        "max_abs_diff": {f: v["max_abs_diff"] for f, v in d.items()},
                        "new_findings": len(findings) - f0})
    return {"segment": j, "self_test": self_test, "rows": int(len(df)),
            "per_leg": per_leg, "findings": findings, "PASS": bool(ok)}


# ===========================================================================
def emit_mqh_fixture(outdir: Path) -> dict:
    """Fixture for CheckSwapEurq.mq5: expected swap/eurq values from THIS
    generator (already gated bit-equal), so the MQL5 twin can be judged
    in-terminal without any python at run time."""
    rows = []
    for s in SYMBOLS_BH:
        for d in ("2020-01-02", "2020-03-18", "2021-06-30", "2022-11-02",
                  "2023-03-22", "2024-07-31", "2025-01-24", "2025-12-31"):
            ds = int(pd.Timestamp(d).value // 10**9)
            lp, sp = swap_annual_pct(s, ds)
            m = swap_day_multiplier(s, ds)
            act = 1 if is_swap_day(s, ds) else 0
            rows.append(f"BH,{s},{ds},{act},{m},{lp / 100.0 / 365.0 * m:.17g},"
                        f"{sp / 100.0 / 365.0 * m:.17g}")
    for s in sorted(set(CORESIM_LEGS)):
        for d in ("2020-01-02", "2022-11-02", "2024-07-31", "2025-12-31"):
            ds = int(pd.Timestamp(d).value // 10**9)
            lp, sp = swap_annual_pct(s, ds)
            m = swap_day_multiplier(s, ds)
            act = 1 if is_swap_day(s, ds) else 0
            rows.append(f"CORE,{s},{rollover_utc_sec(ds)},{act},{m},"
                        f"{lp / 100.0:.17g},{sp / 100.0:.17g}")
    # ROLL: the US-DST rollover rule, incl. both 2024 transition weekends
    for d in ("2020-01-02", "2024-03-09", "2024-03-10", "2024-03-11",
              "2024-11-02", "2024-11-03", "2024-11-04", "2025-06-30"):
        ds = int(pd.Timestamp(d).value // 10**9)
        rows.append(f"ROLL,-,{ds},0,0,{rollover_utc_sec(ds)},0")
    # EURQ: raw feed doubles -> eurq.  Both profiles read the SAME IC parquet;
    # F32 rows gate the (float) cast the b_h record feed applies, F64 rows gate
    # the a_h path (prime_feed('ic') + ICFx: same bars, no cast).
    for c in CROSSES_BH:
        df = pd.read_parquet(BARS_IC / f"{c}_IC_1m.parquet",
                             columns=["bid_c", "ask_c"])
        for i in (0, len(df) // 2, len(df) - 1):
            b, a = float(df["bid_c"].iloc[i]), float(df["ask_c"].iloc[i])
            e = 1.0 / (0.5 * (float(np.float32(b)) + float(np.float32(a))))
            rows.append(f"EURQF32,{c},{b:.17g},{a:.17g},{e:.17g}")
            rows.append(f"EURQF64,{c},{b:.17g},{a:.17g},"
                        f"{1.0 / (0.5 * (b + a)):.17g}")
    p = outdir / "FMA3_swapeurq_fixture.csv"
    p.write_text("\n".join(rows) + "\n")
    return {"fixture": str(p), "rows": len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true",
                    help="table-drift guard + judge(golden,golden) positive control")
    ap.add_argument("--gate-bh", nargs="*", default=None)
    ap.add_argument("--gate-coresim", nargs="*", type=int, default=None)
    ap.add_argument("--perturb", default=None,
                    help="NEGATIVE CONTROL, e.g. swap:USDJPY:long:+0.5")
    ap.add_argument("--emit-mqh-fixture", action="store_true")
    ap.add_argument("--outdir", default=str(COMMON_FILES))
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    outdir = Path(args.outdir)

    rep: dict = {"generated": pd.Timestamp.now().isoformat(),
                 "outdir": str(outdir), "perturbation": None}
    if args.perturb:
        rep["perturbation"] = apply_perturbation(args.perturb)
        print(f"NEGATIVE CONTROL: {rep['perturbation']}", flush=True)

    if args.selftest:
        rep["tables"] = "SKIPPED (perturbed)" if args.perturb else verify_tables()
        print(f"[selftest] table-drift guard: {rep['tables']}", flush=True)
        st = gate_bh("2020Q1", outdir, self_test=True)
        rep["positive_control_bh"] = {"PASS": st["PASS"], "bars": st["bars"]}
        stc = gate_coresim(0, outdir, self_test=True)
        rep["positive_control_coresim"] = {"PASS": stc["PASS"], "rows": stc["rows"]}
        print(f"[selftest] judge(golden,golden) bh={st['PASS']} "
              f"coresim={stc['PASS']}", flush=True)
        assert st["PASS"] and stc["PASS"], "POSITIVE CONTROL FAILED"

    if args.gate_bh is not None:
        qs = args.gate_bh or [str(q) for q in pd.period_range("2020Q1", "2025Q4",
                                                              freq="Q")]
        rep["bh"] = []
        allp = True
        for q in qs:
            r = gate_bh(q, outdir)
            allp &= r["PASS"]
            rep["bh"].append(r)
            print(f"  bh {q}: bars={r['bars']:,} PASS={r['PASS']} "
                  f"max|d| eurq={r['eurq']['max_abs_diff']:.3g} "
                  f"swap_l={r['swap_l']['max_abs_diff']:.3g} "
                  f"swap_s={r['swap_s']['max_abs_diff']:.3g} "
                  f"| rollovers={r.get('rollovers_fired')} "
                  f"pre_hits={r.get('pre_first_bar_hits')} "
                  f"({r['read_seconds']}s read + {r['gen_seconds']}s gen)",
                  flush=True)
            if not r["PASS"]:
                for f in r["findings"][:12]:
                    print(f"      FAIL {f['field']} {f['symbol']}: "
                          f"max|diff|={f['max_abs_diff']:.6g} on "
                          f"{f['n_bars_differ']:,} bars", flush=True)
        rep["bh_all_pass"] = allp

    if args.gate_coresim is not None:
        js = args.gate_coresim or [0, 10, 20, 31]
        rep["coresim"] = []
        allp = True
        for j in js:
            r = gate_coresim(j, outdir)
            allp &= r["PASS"]
            rep["coresim"].append(r)
            print(f"  coresim seg{j}: rows={r['rows']:,} PASS={r['PASS']}",
                  flush=True)
            for L in r["per_leg"]:
                if not L["bit_equal"]:
                    print(f"      FAIL leg {L['leg']} {L['inst']}: "
                          f"{L['max_abs_diff']}", flush=True)
            for f in r["findings"][:8]:
                print(f"      FAIL {f['field']} {f['symbol']}: "
                      f"max|diff|={f['max_abs_diff']:.6g} on "
                      f"{f['n_bars_differ']:,} bars", flush=True)
        rep["coresim_all_pass"] = allp

    if args.emit_mqh_fixture:
        rep["fixture"] = emit_mqh_fixture(outdir)
        print(f"  fixture: {rep['fixture']}", flush=True)

    out = Path(args.report) if args.report else (HERE / "swap_eurq_gate.json")
    out.write_text(json.dumps(rep, indent=1))
    fails = [k for k in ("bh_all_pass", "coresim_all_pass")
             if k in rep and not rep[k]]
    print(f"GATE {'PASS' if not fails else 'FAIL ' + str(fails)}  -> {out}",
          flush=True)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
