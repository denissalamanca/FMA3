"""
FMA3 P1c KILL-SWITCH part 1 — ENUMERATION of MQL5-specific residuals that a
pure-double scalar proxy CANNOT close, and that require in-terminal confirmation.

The scalar recurrences in scalar_primitives.py prove the RECURRENCE ALGEBRA is
IEEE-754 faithful (max_rel ~1e-14 vs pandas).  What they CANNOT prove is that
the MQL5 standard library's *elementary functions* and *rounding rule* agree
with numpy/libm to the ULP.  Two classes remain:

  R1. MathRound (round-half-AWAY-from-zero) vs numpy .round() (round-half-to-EVEN,
      "banker's").  They differ AT exact ties, and a tie lands one discrete level
      apart on a hysteresis grid.  Two live grids:
        * crisis position grid _GRID=0.02:  ((w/0.02).round()*0.02)
          tie w/0.02 == k+0.5  ->  positions differ by a full 0.02 (one level).
        * mag $100 magnet:  near=((d/100).round())*100
          tie d/100 == k+0.5  ->  nearest-round differs by $100, which FLIPS the
          long/flat band membership (mind=3%..band=18% below the round level) ->
          the whole single-leg gold position turns on/off.
      Exact ties are measure-zero on live float feeds, but MQL5 also *reaches* the
      rounding op from a different last-ULP input (its own MathXxx chain), so a
      value at k+0.5 +/- 1ulp can straddle the tie differently than numpy does.

  R2. Last-ULP differences in MathSqrt / MathPow / MathExp / tanh vs numpy/libm.
      MathSqrt is IEEE-754 correctly-rounded (safe).  MathPow/MathExp/MathLog and
      tanh are ~0.5-1 ULP, platform-libm-dependent, NOT guaranteed bit-identical
      to numpy.  Harmless in continuous outputs (swamped by 1e-14), but if such a
      value feeds a DISCRETE threshold (regime flags vr>v0, dd<-d0, crisis grid
      snap, magnet band edge, Donchian breakout ==), a 1-ULP disagreement can flip
      the boolean/level and cascade.  ewm_std/rolling_std end in MathSqrt (safe);
      the exposed surfaces are pow/exp inside sqrt-of-annualization and any tanh
      squashers.  MUST be confirmed in-terminal against the frozen feed, not proxied.

Run to reproduce the measured tie divergences:
    python3 mql5_residuals.py
"""
import math
import numpy as np


def mathround(x):
    """MQL5 MathRound semantics: round half AWAY from zero."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def demo():
    rows = []
    # R1a crisis 0.02 grid tie
    w, g = 0.05, 0.02
    rows.append(("crisis_grid_0.02  w=0.05 (w/g=2.5)",
                 np.round(w / g) * g, mathround(w / g) * g))
    # R1b mag $100 magnet tie
    d = 1250.0
    rows.append(("mag_magnet_$100   d=1250 (d/100=12.5)",
                 np.round(d / 100.0) * 100.0, mathround(d / 100.0) * 100.0))
    print(f"{'case':<38}{'numpy(even)':>14}{'MQL5(away)':>14}{'delta':>14}")
    for name, a, b in rows:
        print(f"{name:<38}{a:>14.6g}{b:>14.6g}{b - a:>14.6g}")
    print("\nR1: at a tie the two rules land ONE discrete level apart "
          "(0.02 grid step / $100 magnet flip).")
    print("R2: MathSqrt correctly-rounded; MathPow/Exp/tanh ~0.5-1 ULP, "
          "libm-dependent -> confirm in-terminal near any hysteresis threshold.")


if __name__ == "__main__":
    demo()
