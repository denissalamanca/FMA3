#!/usr/bin/env python3
"""STANDALONE 2017-2019 fed_frac (t0=2017-01-01). RESILIENCE-GRADE OOS.

Does NOT touch / prepend the 2020-2025 golden. Blends the v7 core (ext Duka feed,
warm from 2015) + v34 satellite (research_cache_ext, warm from 2015) with the SAME
static_fed(0.70) math as model/v3/reproduce.py:66-74, then serializes fmt=3 via the
verbatim export_book_frac_v3.build_rows.

PROVENANCE (label loudly): model feed = Dukascopy ext (v7) + research_cache_ext (v34),
SYNTHETIC/assigned spread, ~30/33 symbols (SOL/XRP/XPT absent; AUD/NZD ~inert via S6;
crypto fades in late-2018). Signal-causality GATE = GO (every sleeve strictly causal;
hyperparameters frozen on 2020-2025 => genuine OOS). NOT the IC worst-mark golden.

NAMING RECONCILIATION (critical): the ext-feed v7 names its single index book "USA500"
(the USTEC/Nasdaq book computed on a USA500 proxy, no Duka USTEC). The 2020-2025 v7
model names that exact book "USTEC". So we RENAME v7 USA500 -> USTEC before the blend,
else build_rows' SYMMAP (USA500->US500) would wrongly land the Nasdaq book on US500.
v34 carries genuine USA500(->US500), DAX(->DE40), USTEC separately; those are untouched.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
sys.path.insert(0, str(REPO / "scripts"))
import export_book_frac_v3 as X                 # build_rows, SYMMAP, EPS, DECIMALS=12, FMT=3

CORE_WEIGHT = 0.70
CONFIG_HASH = "51a7541cc2aaa593"   # cosmetic: header literal; a 2017-2019 stream is semantically distinct
OUT = REPO / "research/outputs/mt5/FMA3_fed_frac_2017_2019.csv"

# ---- ACTUAL 2017-2019 input artifacts (produced by run_extract_ext.py + build_sat_frac_2017_2019.py) ----
CORE_FRAC = REPO / "research/outputs/ext1719/v7_book_frac_1h_ext1719.parquet"     # 8 cols, USA500 = Nasdaq book
CORE_EQ   = REPO / "research/outputs/ext1719/v7_book_equity_1m_ext1719.parquet"   # has 'eqc'
SAT_FRAC  = REPO / "research/oos/outputs/sat_frac_v34_2017_2019.parquet"          # 28 cols, scale+cap baked in
SAT_EQ    = REPO / "research/oos/outputs/v34_native_curve_2017_2019.parquet"      # has 'equity'


def _to_ic_server(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """v7 ext feed is tz-naive TRUE UTC; the v34 research_cache_ext (and the IC
    tester) are tz-naive IC MT5 server time = UTC+2 (EET) / UTC+3 during US DST.
    Broker DST rule VERIFIED empirically against research_cache_ext XAUUSD prices
    (match err 0.0): +3h on 2017-03-15 AND 2017-10-31 — i.e. US DST (2nd Sun Mar ->
    1st Sun Nov), NOT EU. Convert v7 -> server so v7 core + v34 sat align (else the
    DO_NOT_USE.md Duka-UTC/IC-server 2-3h misalignment). DST transitions create a
    duplicate hour (fall-back, dropped keep='last') and a gap (spring-forward,
    fillna'd by the blend) — ~4 hrs/yr, immaterial."""
    east = idx.tz_localize("UTC").tz_convert("US/Eastern").tz_localize(None)
    is_dst = ((east - idx) / pd.Timedelta(hours=1)) == -4.0     # EDT -4 vs EST -5
    return idx + pd.to_timedelta(np.where(is_dst, 3, 2), unit="h")


def _shift_series(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = _to_ic_server(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_inputs_2017():
    """Same contract as reproduce.load_inputs() (reproduce.py:49-57): native frac
    matrices + native equity curves normalised to 1.0 at each series' own t0 —
    with v7 (UTC) converted to the IC server clock so it aligns with v34 (server)."""
    core_frac = pd.read_parquet(CORE_FRAC)
    # v7 'USA500' column is the USTEC/Nasdaq book on a proxy feed -> rename to match
    # the 2020-2025 model + tester canonical (v34 keeps its genuine USA500/DAX).
    if "USA500" in core_frac.columns:
        core_frac = core_frac.rename(columns={"USA500": "USTEC"})
    core_frac.index = _to_ic_server(core_frac.index)
    core_frac = core_frac[~core_frac.index.duplicated(keep="last")].sort_index()
    sat_frac = pd.read_parquet(SAT_FRAC)                     # already IC server
    core_eq  = _shift_series(pd.read_parquet(CORE_EQ)["eqc"])
    sat_eq   = pd.read_parquet(SAT_EQ)["equity"]             # already IC server
    return core_frac, sat_frac, core_eq / core_eq.iloc[0], sat_eq / sat_eq.iloc[0]


def static_blend_2017(w: float) -> pd.DataFrame:
    """VERBATIM copy of reproduce.static_blend body (reproduce.py:66-74)."""
    core_frac, sat_frac, a, b = load_inputs_2017()
    hours = core_frac.index.union(sat_frac.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat  = sat_frac.reindex(hours).fillna(0.0)
    cols = sorted(set(f_core.columns) | set(f_sat.columns))
    return (f_core.reindex(columns=cols, fill_value=0.0).mul(w * a_h / j, axis=0)
            + f_sat.reindex(columns=cols, fill_value=0.0).mul((1 - w) * b_h / j, axis=0))


def write_csv_2017(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(f"w_v7={CORE_WEIGHT},config_hash={CONFIG_HASH},fmt={X.FMT}\n")
        for e, sym, v in rows:
            if sym == "__GRID__":
                fh.write(f"{e},__GRID__,0\n")
            else:
                fh.write(f"{e},{sym},{v:.{X.DECIMALS}f}\n")


if __name__ == "__main__":
    fed  = static_blend_2017(CORE_WEIGHT)
    rows = X.build_rows(fed)   # |v|>EPS -> (epoch, SYMMAP-mapped sym, v); __GRID__ per flat hour; sorted
    write_csv_2017(OUT, rows)
    syms = sorted({r[1] for r in rows if r[1] != "__GRID__"})
    print(f"wrote {OUT}")
    print(f"  {fed.shape[0]} hours x {fed.shape[1]} cols -> {len(rows):,} rows")
    print(f"  span {fed.index.min()} .. {fed.index.max()}")
    print(f"  {len(syms)} symbols: {' '.join(syms)}")
