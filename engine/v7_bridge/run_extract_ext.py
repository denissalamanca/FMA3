"""Core band-book position extraction on the EXTENDED-HISTORY feed, 2017-2019.

Purpose (FMA3 fed_frac history extension)
-----------------------------------------
Generate the Core (band-book) hourly book-fractions + 1m core equity for
[2017-01-01, 2020-01-01) so the fed_frac blend can be extended backwards. The
SAME frozen Core band book as the verified IC anchor and the forward feed
(book('BTC_REP','USA500'), up=0.25, down=(1/7)/1.75, kmult=2.5, min_gap 5d,
noliq stop_out=1e-9) is run on the NSF5 EXTENDED Duka cache
(cache/bars_1m_ext/{inst}_2015_2025_1m.parquet, 10 insts, tz-naive TRUE UTC).

WARM-START (the whole point)
----------------------------
The sleeve targets are built from load_bars(inst) over the FULL 2015-start
cache, so every indicator (rolling means, daily-mid vol scale, 200d regime,
63d momentum) is computed on the 2015-2016 prefix as WARMUP. extract() then
runs the numba core over the whole cache and MASKS the desired target to 0
outside the probe windows (all inside [2017,2020]); the output is sliced to
the window with a boolean `sel`. So 2015-2016 = indicator warmup, NOT a row
that is dropped — it is never given a nonzero target and never seeds a book
position (the band runner starts seed=INIT at lo=2017-01-01). This is the
compute-full-then-mask convention, confirmed in extract_positions._run_window_pos
(mask = _mask_from_windows(bars.index,[(lo,hi)]); run_backtest_pos runs full
bars; sel = index in [lo,hi)).

FEED PRIMING (mirror of NSF5 v72/extended_run.py::prime_ext, READ-ONLY source)
------------------------------------------------------------------------------
Clear bt._BARS_CACHE/_PREP_CACHE, load each ext parquet into
bt._BARS_CACHE[(inst,False)], and set bt._FX = ICFx(d) (holdout-free true-UTC
FX converter over the same frames). 'ext' is injected into extract_positions'
feed dispatch by wrapping its module-level prime().

us5='USA500'  — USTEC has no Duka feed; USA500 (corr .89) is the documented
                proxy (same as run_extract_fwd). Directional only.

CAVEATS baked into this window (see findings; NOT bugs, frozen-signal facts)
---------------------------------------------------------------------------
  * Crypto data starts LATE: BTCUSD 2017-05-07, ETHUSD 2017-12-11. There is NO
    2015-2016 crypto warmup, so S1_ETH / BTC_REP indicators (200d regime, 63d
    mom/ann) do not warm until ~mid/late-2018; those sleeves sit flat (legcap
    in cash) until then. The 2017 book is effectively crypto-free.
  * S6_OPEXUSD is FLAT for 2017-2019: its opex-week calendar (_nth_friday_week
    in NSF5 v5_sleeves.py) is hardcoded to pd.date_range('2019-12-01',...), so
    the mask has no dates before 2019-12. Its legs (USDJPY/AUDUSD/NZDUSD) take
    no S6 position pre-2019-12. AUDUSD & NZDUSD enter the book ONLY via S6, so
    they are ~0 in this window. NSF5 is READ-ONLY; not patched here.
  Net: the faithful 2017-2019 Core book is driven mainly by BOOK_XAU (XAUUSD),
  S5_JPY (USDJPY), ZC_EG (EURGBP) and BOOK_USTEC (USA500-proxy), with crypto
  fading in from late-2018. Read the artifacts as resilience/OOS, not as an
  8-sleeve replica of 2020-2025.

Artifacts (research/outputs/ext1719/, index = tz-naive TRUE UTC)
---------------------------------------------------------------
  v7_book_lots_1m_ext1719.parquet    net signed lots per instrument (8 cols)
  v7_book_equity_1m_ext1719.parquet  eqc / eqw / margin
  v7_book_frac_1h_ext1719.parquet    hourly frac-of-book-equity matrix
                                     (this + eqc are what the fed_frac blend
                                      consumes: model/v3/reproduce.py load_inputs
                                      reads CORE_FRAC=v7_book_frac_1h + CORE_EQ
                                      =v7_book_equity_1m['eqc'], normalized /iloc0)
  v7_extract_ext1719_verification.json

Gates that still run (anchor gate is IC-only, SKIPPED here):
  1. bit-exact core self-test vs NSF5 run_backtest, every leg;
  2. positions -> book-equity rebuild < 1e-6 relative.

Usage:
    /opt/homebrew/Caskroom/miniforge/base/bin/python3 \
        /Users/dsalamanca/vs_env/FableMultiAssets3/engine/v7_bridge/run_extract_ext.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_positions as ep                    # noqa: E402
from extract_positions import OUT_DIR, extract     # noqa: E402
from multifeed_optim import ICFx                    # noqa: E402  (NSF5, on sys.path via ep)

#: Extended-history extraction window. 2015-2016 = indicator warmup (never
#: given a nonzero target); book seed starts at INIT on 2017-01-01.
LO_EXT = pd.Timestamp("2017-01-01")
HI_EXT = pd.Timestamp("2020-01-01")

#: NSF5 extended 1m cache (READ-ONLY). Absolute so it does not depend on which
#: `config.settings` won the import race.
EXT_DIR = Path("/Users/dsalamanca/vs_env/NewStrategyFable5/cache/bars_1m_ext")
#: The exact 10 frames the NSF5 prime_ext mirror loads (only the 8 book insts
#: are actually traded; EURJPY/EURUSD are loaded for parity, harmless).
EXT_INSTS = ["XAUUSD", "USA500", "USDJPY", "EURGBP", "AUDUSD", "NZDUSD",
             "EURUSD", "EURJPY", "BTCUSD", "ETHUSD"]


def prime_ext() -> dict:
    """Prime NSF5's module-level caches from the extended 2015-2025 Duka frames.

    Line-for-line mirror of NSF5 mt5/reconcile/v72/extended_run.py::prime_ext:
    clear the bar/prep caches, load each ext parquet into _BARS_CACHE[(inst,
    False)], and install ICFx(d) as the FX converter (prep_arrays reads bt._FX).
    """
    ep.bt._BARS_CACHE.clear()
    ep.bt._PREP_CACHE.clear()
    d: dict = {}
    for inst in EXT_INSTS:
        p = EXT_DIR / f"{inst}_2015_2025_1m.parquet"
        if p.exists():
            b = pd.read_parquet(p)
            d[inst] = b
            ep.bt._BARS_CACHE[(inst, False)] = b
    if not d:
        raise FileNotFoundError(f"no ext frames found under {EXT_DIR}")
    ep.bt._FX = ICFx(d)
    return d


# --- inject 'ext' into extract_positions' feed dispatch ----------------------
_orig_prime = ep.prime


def _prime(feed: str) -> None:
    if feed == "ext":
        prime_ext()
    else:
        _orig_prime(feed)


ep.prime = _prime


if __name__ == "__main__":
    report = extract(
        write_artifacts=True,
        run_self_test=True,          # set False to skip the ~2x bit-exact pass
        verbose=True,
        feed="ext",
        us5="USA500",                # USTEC proxy (no Duka USTEC), corr .89
        lo=LO_EXT,
        hi=HI_EXT,
        anchor_gate=False,           # no IC reference exists on this feed
        out_dir=OUT_DIR / "ext1719",
        artifact_suffix="_ext1719",
        blind_from=None,             # 2017-2019 is not a holdout window
        dev_metrics_hi=HI_EXT,       # report bd_metrics over the full window
    )
    sys.exit(0 if report["status"] == "consistent" else 1)
