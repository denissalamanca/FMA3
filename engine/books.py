"""Book builders for FMA3 experiments.

Each builder returns a FINAL hourly fraction-of-equity position matrix
(server-time index, FMA2 convention, scale + hard limits already applied),
ready for ``record_engine.run_record``.  Centralizing construction here means
later experiments reference the v3.4 shipped book through ONE function instead
of re-deriving weights/scale/caps and risking drift from the pinned artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Flat-module import of the sibling record_engine (FMA3/engine is deliberately
# NOT a package — see record_engine's docstring on the NSF5 `engine` package
# name collision).  Importing it also performs the FMA2/NSF5 sys.path
# bootstrap that everything below relies on.
_ENGINE_DIR = str(Path(__file__).resolve().parent)
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)
import record_engine  # noqa: E402,F401  (side effect: sys.path bootstrap)


def build_sat_frac_1h() -> pd.DataFrame:
    """The shipped v3.4 book, EXACTLY as the official pin constructs it.

    We deliberately delegate to ``eval_v34_pin_s10.build_c2()`` in read-only
    FMA2 rather than re-implementing the recipe: that function IS the pinned
    construction (V2_CAPS sleeve parquets + freshly built mag_xau overlay,
    combined with RAW weights — cash-parked, never renormalized — x
    GLOBAL_SCALE 10, then ensemble.apply_hard_limits with the structural gold
    cap 0.18 x 10 = 1.80).  Any local copy could drift from the verified
    artifact; a delegation cannot.

    Returns the FINAL hourly fraction-of-equity matrix on FMA2 core's union
    server-time grid (37 columns, 2020-2025).  Feed straight into
    ``record_engine.run_record``.  Takes ~1 min (sleeve parquet loads +
    mag_xau rebuild on the hourly universe).
    """
    import eval_v34_pin_s10 as _pin  # import deferred: pulls FMA2 core/data
    return _pin.build_c2()


def build_v34_variant_frac_1h(crisis_w: float) -> pd.DataFrame:
    """A v3.4' book with ONLY the crisis weight changed (H-TAIL-1, FMA3-006).

    Mirrors ``eval_v34_pin_s10.build_c2()`` line-for-line with the crisis
    weight overridden; the delta is funded from the cash-park (weights are
    RAW / never renormalized, so raising crisis simply shrinks the park:
    0.174 - (crisis_w - 0.10)).  All sleeve internals, MAG@0.05, SCALE=10 and
    the hard-limit machinery are unchanged; the structural gold cap still
    keys off seasonal 0.18 (verified: ``structural_gold_cap`` reads
    ``weights['seasonal']``), so the cap is identical to the pin's 1.80.
    Pre-registered variants: crisis_w in {0.15, 0.20} only.
    """
    import core                      # noqa: F401  FMA2 research core
    import ensemble as E
    import eval_v34_pin_s10 as _pin
    from ext_import import mag_xau
    import core as _core

    caps = dict(_pin.V2_CAPS)
    assert crisis_w in (0.15, 0.20), "pre-registered variants only"
    caps["crisis"] = crisis_w
    sleeves = E.load_sleeves(list(caps))
    grid = _core.universe_frames(tuple(_core.ALL))["ret"].index
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
    weights = {**caps, "mag": _pin.MAG_W}
    pos = E.combine(sleeves, weights) * _pin.SCALE
    gcap = E.structural_gold_cap(caps, _pin.SCALE)
    return E.apply_hard_limits(pos, gold_cap=gcap)
