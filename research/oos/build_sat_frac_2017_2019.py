"""FMA3 OOS — build the Satellite (Sat) sat_frac for 2017-01-01..2019-12-31,
warm-started from 2015, on the FMA2 pre-2020 hourly research engine.

WHY THIS EXISTS (and why it is NOT engine/books.build_sat_frac_1h)
------------------------------------------------------------------
The shipped `books.build_sat_frac_1h()` delegates to FMA2
`eval_v34_pin_s10.build_c2()`, which calls `ensemble.load_sleeves()` — that
loads FROZEN `outputs/{sleeve}_pos.parquet` artifacts. Those parquets span
ONLY 2020-01-02..2025-12-31 (verified). Reindexed onto the 2015-2020 ext grid
they fillna(0.0), so build_c2() yields an ALL-ZERO book before 2020. Useless
for a pre-2020 OOS.

The pre-2020 book must instead RECOMPUTE each sleeve live via
`sleeves.<name>.make_positions()` over the extended cache (mirrors FMA2
`research/run_oos_2015.py`), so every indicator warms from 2015 and is fully
spun-up by 2017. We then apply the Satellite construction (V2_CAPS + MAG@0.05 +
SCALE 10 + structural gold cap + hard limits) exactly as build_c2 does — but
on the LIVE sleeve matrices.

ENGINE CONSTRAINT
-----------------
The engine of record (`account_engine_1m.simulate_account_1m`, wrapped by
FMA3 `engine/record_engine.run_record`) is HARDCODED to 2020Q1..2025Q4 and
raises on any earlier range. Pre-2020 must therefore use the FMA2 hourly
research engine `core.simulate(start=, end=)`, which windows correctly by
slicing the return frame internally (NOT by row-slicing pos — that would
ffill-freeze the last 2019 row across the tail).

TWO-CORE LANDMINE
-----------------
`import core` (top-level) and `mag_xau`'s `import research.core` are DISTINCT
module objects (`core is research.core` == False, verified). Patching only
top-level `core` leaves `research.core.CACHE` pointing at the default
2020-2025 `research_cache`, so the MAG_XAU overlay would silently warm on the
wrong data and contribute zero gold pre-2020. We patch BOTH.

OUTPUTS (what the FMA3 fed_frac blend consumes)
-----------------------------------------------
  research/oos/outputs/sat_frac_v34_2017_2019.parquet
      frac34_h — the FINAL Satellite fraction-of-equity position matrix (scale +
      hard limits baked in), hourly server-time index restricted to
      2017-01-01..2019-12-31, columns = the 34 ext-cache instruments. This is
      the `frac34_h` term of fed_frac_h.
  research/oos/outputs/v34_native_curve_2017_2019.parquet
      B_h — Satellite native hourly equity curve (core.simulate windowed), the `B`
      term of J = w*A + (1-w)*B. Normalize to 1.0 at t0 before blending.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pandas as pd

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
sys.path.insert(0, str(FMA2 / "research"))   # top-level core / ensemble / sleeves
sys.path.insert(0, str(FMA2))                # research.* package + ext_import

import core                                   # noqa: E402  top-level FMA2 core
import research.core as rcore                 # noqa: E402  the one mag_xau uses
import ensemble as E                          # noqa: E402
from ext_import import mag_xau                 # noqa: E402
import eval_v34_pin_s10 as PIN                 # noqa: E402  V2_CAPS/SCALE/MAG_W

EXT = FMA2 / "research_cache_ext"
AVAIL = tuple(sorted(os.path.basename(f)[:-11]
                     for f in glob.glob(str(EXT / "*_1h.parquet"))))
LO, HI = "2017-01-01", "2019-12-31"
OUT = Path(__file__).resolve().parent / "outputs"


def _patch(mod):
    """Point a core module object at the extended 2015-2020 cache/universe."""
    mod.CACHE = EXT
    mod.ALL = AVAIL
    _uf, _sw = mod.universe_frames, mod.swap_accrual_matrices
    mod.universe_frames = lambda symbols=AVAIL: _uf(AVAIL)
    mod.swap_accrual_matrices = lambda symbols=AVAIL: _sw(AVAIL)


def build_sat_book_ext() -> pd.DataFrame:
    """Satellite book recomputed LIVE over the ext cache (build_c2 recipe, live sleeves).

    Returns the FINAL fraction matrix on the FULL 2015-2020 grid — DO NOT
    row-slice before simulate. Slice only the returned ARTIFACT afterwards.
    """
    # patch BOTH core objects (top-level for sleeves/ensemble, research.core
    # for mag_xau) BEFORE any universe frame is materialized/cached.
    _patch(core)
    _patch(rcore)

    grid = core.universe_frames(tuple(core.ALL))["ret"].index

    # --- recompute each V2_CAPS sleeve LIVE (warms from 2015) ---------------
    import importlib
    sleeves: dict[str, pd.DataFrame] = {}
    for name in PIN.V2_CAPS:
        mod = importlib.import_module(f"sleeves.{name}")
        importlib.reload(mod)
        if name == "crypto_smart":
            # SOLUSD/XRPUSD absent pre-2020; BTC from 2017-05, ETH from 2017-12
            pos = mod.make_positions(symbols=["BTCUSD", "ETHUSD"])
        else:
            pos = mod.make_positions()
        sleeves[name] = pos.reindex(grid).fillna(0.0)

    # --- MAG_XAU overlay, warmed on the ext grid via patched research.core --
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)

    # --- Satellite construction (identical to build_c2) -------------------------
    weights = {**PIN.V2_CAPS, "mag": PIN.MAG_W}
    pos = E.combine(sleeves, weights) * PIN.SCALE
    gcap = E.structural_gold_cap(PIN.V2_CAPS, PIN.SCALE)
    return E.apply_hard_limits(pos, gold_cap=gcap)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"ext cache symbols: {len(AVAIL)}/34 | warm-start 2015 | window {LO}..{HI}")

    book_full = build_sat_book_ext()          # full 2015-2020 grid

    # ARTIFACT 1: sat_frac = frac34_h restricted to the OOS window.
    # Row-slicing the ARTIFACT is correct (the blend only consumes these
    # rows); the ffill-freeze hazard is exclusively a simulate() concern.
    sat_frac = book_full.loc[LO:HI]
    sat_frac.to_parquet(OUT / "sat_frac_v34_2017_2019.parquet")
    print(f"sat_frac shape {sat_frac.shape} "
          f"nonzero-cells {int((sat_frac.abs() > 0).values.sum())} "
          f"span {sat_frac.index.min()}..{sat_frac.index.max()}")

    # ARTIFACT 2: native curve B_h. Pass the FULL pos to simulate with
    # start/end — the engine slices the return frame internally; passing a
    # row-sliced pos would ffill-freeze the 2019 row across 2020.
    sim = core.simulate(book_full, start=LO, end=HI)
    B = sim.equity
    B.to_frame("equity").to_parquet(OUT / "v34_native_curve_2017_2019.parquet")
    print(f"Satellite native curve B: {B.index.min()}..{B.index.max()} rows {len(B)} "
          f"final {float(B.iloc[-1]):.4f} | CAGR {sim.metrics['cagr']:+.3f} "
          f"maxDD {sim.metrics['maxdd']:.3f} Sharpe {sim.metrics['sharpe']:.2f}")


if __name__ == "__main__":
    main()
