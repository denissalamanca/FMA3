"""FMA3 federation propagation of the Duka-hybrid v34 feed.

static_fed: fed[h,k] = f7*(w*a/j) + f34*((1-w)*b/j), j = w*a + (1-w)*b, w=0.70.
Swapping the v34 feed changes BOTH f34 (build_c2 positions) and b (v34 standalone
equity). f7 and a (v7) are unchanged. We recompute fed with hybrid f34+b and
compare to pin fed[h,k]."""
from __future__ import annotations
import sys, json
from pathlib import Path
REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
sys.path.insert(0, str(REPO / "engine"))
sys.path.insert(0, str(REPO / "model" / "v3"))
import numpy as np
import pandas as pd
import reproduce as M

SCRATCH = Path("/private/tmp/claude-501/-Users-dsalamanca-vs-env-FableMultiAssets3/"
               "cb1d44e8-f5e7-4172-a469-abf08e14a819/scratchpad")
W = M.W_V7


def fed_from(frac34: pd.DataFrame, b_curve: pd.Series, w: float = W) -> pd.DataFrame:
    """Replicate M.static_fed but with injected frac34 + b (v34 equity multiple).
    frac7 and a (v7 equity) come from the frozen pin inputs."""
    frac7, _frac34_pin, a, _b_pin = M.load_inputs()
    b = b_curve / b_curve.iloc[0]
    hours = frac7.index.union(frac34.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    f7 = frac7.reindex(hours).fillna(0.0)
    f34 = frac34.reindex(hours).fillna(0.0)
    cols = sorted(set(f7.columns) | set(f34.columns))
    return (f7.reindex(columns=cols, fill_value=0.0).mul(w * a_h / j, axis=0)
            + f34.reindex(columns=cols, fill_value=0.0).mul((1 - w) * b_h / j, axis=0))


if __name__ == "__main__":
    # PIN fed (canonical)
    fed_pin = M.static_fed(W)

    # hybrid inputs
    frac34_hyb = pd.read_parquet(SCRATCH / "pos_hybrid.parquet")
    b_hyb = pd.read_parquet(SCRATCH / "hybrid_curve.parquet")["equity"]
    fed_hyb = fed_from(frac34_hyb, b_hyb)

    # align
    cols = fed_pin.columns.union(fed_hyb.columns)
    idx = fed_pin.index.intersection(fed_hyb.index)
    A = fed_pin.reindex(index=idx, columns=cols).fillna(0.0)
    B = fed_hyb.reindex(index=idx, columns=cols).fillna(0.0)
    dperc = (B - A).abs().max().sort_values(ascending=False)
    maxabs = float((B - A).abs().to_numpy().max())
    # fraction of the max-abs fed exposure that the delta represents
    scale_ref = float(A.abs().to_numpy().max())
    print("=== fed[h,k] delta: Duka-hybrid v34 feed vs pin (fed cols) ===")
    print(dperc[dperc > 1e-9].head(25).to_string())
    print(f"\nmax|Δ fed[h,k]| overall = {maxabs:.6f}")
    print(f"max|fed_pin| (reference scale) = {scale_ref:.6f}")
    print(f"frac of max exposure = {maxabs/scale_ref:.4f}")
    # mean abs delta over nonzero cells
    nz = A.to_numpy() != 0
    print(f"mean|Δ| over nonzero pin cells = {float(np.abs((B-A).to_numpy()[nz]).mean()):.6e}")
    out = {"fed_delta_maxabs": maxabs, "fed_pin_maxabs": scale_ref,
           "frac_of_maxabs": maxabs/scale_ref,
           "per_symbol_maxabs": dperc[dperc > 1e-9].to_dict()}
    json.dump(out, open(SCRATCH / "feed_prov_fed.json", "w"), indent=1, default=float)
    print("saved feed_prov_fed.json")
