"""Feed-provenance measurement for the v3.4 s10 book (build_c2).

Finding established separately: research_cache == IC 1m feed resampled (exact,
all 37 symbols), and account_engine_1m reads IC 1m. So the IC-feed provenance
delta is 0 by construction. The only INDEPENDENT broker feed available is
Dukascopy (research_cache_duka), covering 14/37 symbols. This harness measures
the partial (14-symbol) Dukascopy feed-provenance delta with a clean isolation:
identical grid/index to the pin, only the close prices of the 14 Duka symbols
swapped to Dukascopy values.
"""
from __future__ import annotations
import sys
from pathlib import Path
HERE = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
sys.path.insert(0, str(HERE / "research"))
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd
import core
import ensemble as E
from ext_import import mag_xau
from sleeves import (meanrev, carry_breakout, seasonal, intraday, crisis,
                     trend_v2, crypto_smart)

V2_CAPS = {"meanrev": 0.11, "carry_breakout": 0.046, "seasonal": 0.18,
           "intraday": 0.168, "crisis": 0.10, "trend_v2": 0.042,
           "crypto_smart": 0.13}
SCALE = 10.0
MAG_W = 0.05
SLEEVE_MODS = {"meanrev": meanrev, "carry_breakout": carry_breakout,
               "seasonal": seasonal, "intraday": intraday, "crisis": crisis,
               "trend_v2": trend_v2, "crypto_smart": crypto_smart}
DUKA = HERE / "research_cache_duka"
PIN = HERE / "research_cache"
SCRATCH = Path("/private/tmp/claude-501/-Users-dsalamanca-vs-env-FableMultiAssets3/"
               "cb1d44e8-f5e7-4172-a469-abf08e14a819/scratchpad")


def _clear_caches():
    core.load_hourly.cache_clear()
    core.universe_frames.cache_clear()
    core.commission_frac.cache_clear()
    core.swap_accrual_matrices.cache_clear()


def set_cache(path: Path):
    core.CACHE = Path(path)
    _clear_caches()


def build_book_recompute() -> pd.DataFrame:
    """Recompute all 7 sleeves + MAG on the CURRENT core.CACHE, combine exactly
    as eval_v34_pin_s10.build_c2()."""
    sleeves = {n: SLEEVE_MODS[n].make_positions() for n in V2_CAPS}
    grid = core.universe_frames(tuple(core.ALL))["ret"].index
    sleeves = {n: p.reindex(grid).fillna(0.0) for n, p in sleeves.items()}
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
    weights = {**V2_CAPS, "mag": MAG_W}
    pos = E.combine(sleeves, weights) * SCALE
    gcap = E.structural_gold_cap(V2_CAPS, SCALE)
    return E.apply_hard_limits(pos, gold_cap=gcap)


def build_book_frozen() -> pd.DataFrame:
    """Exact build_c2: frozen sleeve parquets via E.load_sleeves + MAG."""
    sleeves = E.load_sleeves(list(V2_CAPS))
    grid = core.universe_frames(tuple(core.ALL))["ret"].index
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
    weights = {**V2_CAPS, "mag": MAG_W}
    pos = E.combine(sleeves, weights) * SCALE
    gcap = E.structural_gold_cap(V2_CAPS, SCALE)
    return E.apply_hard_limits(pos, gold_cap=gcap)


def build_duka_hybrid_cache() -> tuple[Path, list[str]]:
    """Write a 37-symbol hourly cache identical to PIN except the 14 Duka
    symbols' o/h/l/c/rel_spread replaced by Dukascopy values reindexed onto
    the pin symbol's OWN index (grid preserved exactly)."""
    out = SCRATCH / "research_cache_duka_hybrid"
    out.mkdir(parents=True, exist_ok=True)
    duka_syms = sorted(f.name[:-11] for f in DUKA.glob("*_1h.parquet"))
    duka_syms = [s for s in duka_syms if s in core.ALL]
    for s in core.ALL:
        pin = pd.read_parquet(PIN / f"{s}_1h.parquet")
        if s in duka_syms:
            dk = pd.read_parquet(DUKA / f"{s}_1h.parquet")
            # reindex duka onto pin index; ffill within-coverage, fall back to pin
            df = pin.copy()
            for col in ("o", "h", "l", "c", "rel_spread"):
                if col in dk.columns:
                    r = dk[col].reindex(pin.index).ffill()
                    # keep pin where duka has no value (pre-coverage)
                    df[col] = r.where(r.notna(), pin[col])
            df.to_parquet(out / f"{s}_1h.parquet")
        else:
            pin.to_parquet(out / f"{s}_1h.parquet")
    # copy audit.json presence not required
    return out, duka_syms


def frac_delta(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """Per-symbol max|Δ| between two position matrices on their common grid."""
    idx = a.index.intersection(b.index)
    cols = a.columns.union(b.columns)
    aa = a.reindex(index=idx, columns=cols).fillna(0.0)
    bb = b.reindex(index=idx, columns=cols).fillna(0.0)
    return (aa - bb).abs().max().sort_values(ascending=False)


if __name__ == "__main__":
    import json
    # 1) fidelity: recompute-on-PIN vs frozen build_c2
    set_cache(PIN)
    pos_frozen = build_book_frozen()
    set_cache(PIN)
    pos_recomp = build_book_recompute()
    fid = frac_delta(pos_recomp, pos_frozen)
    print("=== FIDELITY recompute-on-PIN vs frozen build_c2 (max|Δ| per sym, top) ===")
    print(fid.head(10).to_string())
    print("max over all symbols:", float(fid.max()))

    # 2) build duka hybrid, recompute book
    hyb, duka_syms = build_duka_hybrid_cache()
    print("\nDuka symbols swapped:", duka_syms, f"({len(duka_syms)}/37)")
    set_cache(hyb)
    pos_hybrid = build_book_recompute()

    # 3) feed delta: hybrid vs recompute-on-PIN (pure feed, same code path)
    set_cache(PIN)
    pos_pin = build_book_recompute()
    fd = frac_delta(pos_hybrid, pos_pin)
    print("\n=== FEED DELTA: Duka-hybrid vs PIN (max|Δ| per sym) ===")
    print(fd[fd > 1e-9].to_string())
    print("max|Δ| overall:", float(fd.max()))

    out = {"fidelity_max": float(fid.max()),
           "fidelity_top": fid.head(10).to_dict(),
           "duka_syms": duka_syms,
           "feed_delta": fd[fd > 1e-9].to_dict(),
           "feed_delta_max": float(fd.max())}
    p = SCRATCH / "feed_prov_positions.json"
    json.dump(out, open(p, "w"), indent=1, default=float)
    # save position matrices for the engine step
    pos_hybrid.to_parquet(SCRATCH / "pos_hybrid.parquet")
    pos_pin.to_parquet(SCRATCH / "pos_pin_recomp.parquet")
    pos_frozen.to_parquet(SCRATCH / "pos_frozen.parquet")
    print("\nsaved", p)
