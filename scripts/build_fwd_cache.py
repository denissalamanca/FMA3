#!/usr/bin/env python3
"""Build FMA3's 2026H1 forward 1m cache (IC schema, broker server time).

WHY
---
The engine of record consumes IC-schema 1m parquets (bid/ask OHLC + n_ticks,
tz-naive broker SERVER time). The only 2026H1 price data in existence is
NSF5/cache/bars_1m_holdout/{SYM}_2026H1_1m.parquet — Dukascopy schema (adds
volume + spread_mean), tz-naive TRUE UTC. This script converts those files
into engine-ready parquets under FMA3/research/fwd_cache_1m/ so the ONE-SHOT
2026H1 forward confirmation (PROTOCOL.md paragraph 4) can inject them into
record_engine_ext via its ``bar_files`` override.

TIMEZONE (the canonical landmine — see config/paths.py + data/DO_NOT_USE.md)
----------------------------------------------------------------------------
Duka UTC -> broker server time ONLY via the verified conversion:
    utc.tz_localize("UTC").tz_convert("America/New_York") + 7h
    -> tz_localize(None)
(DST-correct; daily break lands at server hour 0 = 17:00 ET). This is the
exact ``to_server`` used by FMA2 research/build_ext_cache.py:30-35, whose
output (research_cache_fwd) FMA2 already validated. As an independent gate,
this script resamples its own converted 1m bars to hourly mid closes and
reconciles them against FMA2's research_cache_fwd 2026 tail per symbol.
Within 2026-01..2026-05 there is no NY DST fall-back (next: 2026-11-01), so
the converted index has no folded duplicates; spring-forward (2026-03-08)
only skips a wall-clock hour. Monotonicity/uniqueness are asserted anyway.

SPECIAL FILES (consumers must OPT IN — nothing is silently aliased)
-------------------------------------------------------------------
USTEC_PROXY_USA500_1m.parquet
    USTEC has NO Duka feed. This file contains USA500 prices, verbatim,
    under a name that screams proxy. A consumer that wants to keep USTEC
    exposure alive in the forward window must explicitly map
    bar_files["USTEC"] to this file, accepting that 2026 USTEC P&L is
    measured on USA500 (S&P 500) dynamics, not NASDAQ-100. There is NO
    USTEC_1m.parquet, so nothing can pick a proxy up by accident.
EURCHF_SYNTH_EURUSDxUSDCHF_1m.parquet
    CONVERSION-ONLY synthetic cross. The engine needs an EURCHF mid close to
    convert CHF-quoted P&L (USDCHF is in the forward set) to EUR; no 2026
    EURCHF feed exists. Synthesized bid = EURUSD_bid * USDCHF_bid, ask =
    ask * ask on the intersection of the two converted server-time grids —
    the same triangulation NSF5 engine/costs.FxConverter uses for CHF. The
    engine only ever reads 0.5*(bid_c+ask_c) from crosses; the OHLC extremes
    here are element-wise products (NOT true extremes of the product
    process). NEVER trade this file.

PER-SYMBOL END DATES are captured in fwd_cache_1m/MANIFEST.json: 12 symbols
end 2026-04-30, EURUSD/XAUUSD end 2026-05-31 (so any cross-symbol result
after 2026-05-01 is a 2-symbol result). Coverage vs the 37-instrument
universe: only these 14 (+proxy) exist — 2026 quarters can only trade them.

Run:  python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/build_fwd_cache.py
Cheap (~14 small parquets, no engine, no 1m IC cache loads).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
# Load canonical paths by file location (never `import config`: FMA3's config/
# would shadow NSF5's package for any parent code in this process).
_spec = importlib.util.spec_from_file_location("fma3_paths",
                                               _FMA3 / "config" / "paths.py")
PATHS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PATHS)

OUT_DIR = PATHS.RESEARCH / "fwd_cache_1m"

#: IC engine schema, in IC column order (n_ticks int64, unnamed index).
IC_COLS = ["bid_o", "bid_h", "bid_l", "bid_c",
           "ask_o", "ask_h", "ask_l", "ask_c", "n_ticks"]

#: The 14 instruments with a Duka 2026H1 holdout feed.
HOLDOUT_SYMS = ["AUDUSD", "BTCUSD", "DAX", "ETHUSD", "EURGBP", "EURJPY",
                "EURUSD", "GBPUSD", "NZDUSD", "USA500", "USDCHF", "USDJPY",
                "XAGUSD", "XAUUSD"]


def to_server(df: pd.DataFrame) -> pd.DataFrame:
    """Duka tz-naive TRUE-UTC index -> tz-naive broker server time.

    Verbatim rule from FMA2 research/build_ext_cache.py::to_server (the
    validated conversion; produces the daily break at server hour 0)."""
    idx = (df.index.tz_localize("UTC").tz_convert("America/New_York")
           + pd.Timedelta(hours=7))
    out = df.copy()
    out.index = idx.tz_localize(None)
    return out


def convert_one(sym: str) -> pd.DataFrame:
    """One holdout symbol -> IC-schema server-time frame, with sanity gates."""
    src = PATHS.BARS_1M_HOLDOUT / f"{sym}_2026H1_1m.parquet"
    raw = pd.read_parquet(src)
    missing = [c for c in IC_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"{sym}: holdout file lacks {missing}")
    df = to_server(raw)[IC_COLS].copy()
    df["n_ticks"] = df["n_ticks"].astype(np.int64)   # IC stores int64
    df.index.name = None                              # IC index is unnamed
    df = df.sort_index()
    if not df.index.is_unique:
        raise AssertionError(f"{sym}: duplicate server-time stamps after "
                             "conversion (unexpected before Nov-2026 DST)")
    if len(df) != len(raw):
        raise AssertionError(f"{sym}: row count changed in conversion")
    n_crossed = int((df["ask_c"] < df["bid_c"]).sum())
    if n_crossed > 0.001 * len(df):
        raise AssertionError(f"{sym}: {n_crossed} crossed closes (>0.1%)")
    return df


def reconcile_hourly(sym: str, df_1m: pd.DataFrame) -> float:
    """Gate the conversion against FMA2's already-validated hourly fwd cache.

    research_cache_fwd = IC hourly + the SAME holdout converted by FMA2's own
    to_server + hourly_from_1m. If our 1m server-time mid closes resample to
    the same hourly closes, the timezone conversion cannot be wrong.
    Returns max abs relative delta over the 2026 overlap."""
    ref = pd.read_parquet(PATHS.FMA2_CACHE_FWD / f"{sym}_1h.parquet")["c"]
    ref = ref[ref.index >= "2026-01-01"]
    mid_c = 0.5 * (df_1m["bid_c"] + df_1m["ask_c"])
    mine = mid_c.resample("1h").last().dropna()
    common = ref.index.intersection(mine.index)
    if len(common) < 0.99 * len(ref):
        raise AssertionError(
            f"{sym}: hourly grids diverge from research_cache_fwd "
            f"({len(common)}/{len(ref)} rows shared) — conversion drift?")
    d = float((mine[common] - ref[common]).abs().max()
              / ref[common].abs().median())
    if d > 1e-9:
        raise AssertionError(f"{sym}: hourly close mismatch vs "
                             f"research_cache_fwd (max rel {d:.3e})")
    return d


def build_eurchf_synth(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Conversion-only synthetic EURCHF = EURUSD x USDCHF (see header)."""
    eu, uc = frames["EURUSD"], frames["USDCHF"]
    common = eu.index.intersection(uc.index)
    out = pd.DataFrame(index=common)
    for f in ("bid_o", "bid_h", "bid_l", "bid_c"):
        out[f] = eu.loc[common, f] * uc.loc[common, f]
    for f in ("ask_o", "ask_h", "ask_l", "ask_c"):
        out[f] = eu.loc[common, f] * uc.loc[common, f]
    out["n_ticks"] = np.minimum(eu.loc[common, "n_ticks"].to_numpy(),
                                uc.loc[common, "n_ticks"].to_numpy())
    out["n_ticks"] = out["n_ticks"].astype(np.int64)
    out.index.name = None
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "built": pd.Timestamp.now().isoformat(),
        "source": str(PATHS.BARS_1M_HOLDOUT),
        "schema": "IC engine schema: " + ", ".join(IC_COLS)
                  + "; unnamed tz-naive broker SERVER time index",
        "tz_rule": "UTC -> tz_convert(America/New_York) + 7h -> naive "
                   "(FMA2 build_ext_cache.to_server, verified)",
        "files": {},
    }
    frames: dict[str, pd.DataFrame] = {}

    for sym in HOLDOUT_SYMS:
        df = convert_one(sym)
        rel = reconcile_hourly(sym, df)
        dst = OUT_DIR / f"{sym}_2026H1_1m.parquet"
        df.to_parquet(dst)
        frames[sym] = df
        manifest["files"][dst.name] = {
            "symbol": sym, "rows": len(df),
            "first_server": str(df.index[0]), "last_server": str(df.index[-1]),
            "source_file": f"{sym}_2026H1_1m.parquet",
            "hourly_reconcile_max_rel": rel,
            "note": "real Duka feed, converted",
        }
        print(f"  {sym:7s} {len(df):>7,} rows  {df.index[0]} -> "
              f"{df.index[-1]}  (hourly reconcile ok, {rel:.1e})", flush=True)

    # --- USTEC proxy (opt-in by loud filename; see header) -------------------
    proxy = OUT_DIR / "USTEC_PROXY_USA500_1m.parquet"
    frames["USA500"].to_parquet(proxy)
    manifest["files"][proxy.name] = {
        "symbol": "USTEC", "rows": len(frames["USA500"]),
        "first_server": str(frames["USA500"].index[0]),
        "last_server": str(frames["USA500"].index[-1]),
        "source_file": "USA500_2026H1_1m.parquet",
        "note": "PROXY — USTEC has no Duka feed; these are USA500 prices "
                "verbatim. Consumers must explicitly map "
                "bar_files['USTEC'] to this file (never auto-discovered).",
    }
    print(f"  USTEC   proxy -> {proxy.name} (USA500 prices, opt-in)")

    # --- synthetic EURCHF for EUR conversion of CHF quotes -------------------
    synth = build_eurchf_synth(frames)
    synth_p = OUT_DIR / "EURCHF_SYNTH_EURUSDxUSDCHF_1m.parquet"
    synth.to_parquet(synth_p)
    manifest["files"][synth_p.name] = {
        "symbol": "EURCHF", "rows": len(synth),
        "first_server": str(synth.index[0]),
        "last_server": str(synth.index[-1]),
        "source_file": "EURUSD x USDCHF (converted, intersected grids)",
        "note": "SYNTHETIC, CONVERSION-ONLY (engine reads mid closes for "
                "EUR/CHF conversion). OHLC extremes are element-wise "
                "products, not true extremes. NEVER trade this file.",
    }
    print(f"  EURCHF  synth -> {synth_p.name} ({len(synth):,} rows, "
          "conversion-only)")

    # per-symbol end-date summary (the uneven-window pitfall, documented).
    # NB: a UTC end of Apr-30 23:59 lands at server 2026-05-01 02:59 (UTC+3),
    # so the May/April split point in server time is 2026-05-02.
    ends = {v["symbol"]: v["last_server"] for v in manifest["files"].values()}
    manifest["end_date_summary"] = {
        "through_2026-05-31_utc": sorted(s for s, e in ends.items()
                                         if e >= "2026-05-02"),
        "through_2026-04-30_utc": sorted(s for s, e in ends.items()
                                         if e < "2026-05-02"),
        "warning": "after 2026-05-01 only EURUSD/XAUUSD (and the synthetic "
                   "EURCHF via EURUSD∩USDCHF ending 04-30) have data",
    }
    (OUT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    print(f"\nwrote {len(manifest['files'])} parquets + MANIFEST.json "
          f"-> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
