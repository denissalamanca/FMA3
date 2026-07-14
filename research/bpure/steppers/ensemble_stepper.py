"""Ensemble shell stepper — pointwise scalar combine + hard limits.

FROZEN SPEC (verified line-by-line against):
  model/v3/freeze/FMA3-v34-freeze-1/src/research/ensemble.py
      combine(), structural_gold_cap(), apply_hard_limits()
  model/v3/freeze/FMA3-v34-freeze-1/src/research/eval_v34_pin_s10.py
      build_c2(): V2_CAPS, SCALE = 10.0, MAG_W = 0.05

Bit-exact semantics replicated:
  * build_c2 computes  pos = combine(sleeves, weights) * SCALE  with
    combine() called at scale=1.0.  Per (bar, symbol) that is
        (((p_1*w_1) + p_2*w_2) + ... + p_k*w_k) * 10.0
    folded over the sleeves that CONTAIN the symbol, in dict-insertion
    order: V2_CAPS key order then "mag".  The fold below reproduces that
    exact binary-operation association (first contributor assigns, the
    rest add, final multiply by SCALE) — NOT p*(w*10), which differs in
    the last ulp.
  * RAW weights, NO renormalization.
  * structural_gold_cap is DERIVED (never hardcoded):
        weights[primary]*scale = V2_CAPS["seasonal"] * 10.0
    (build_c2 passes V2_CAPS — WITHOUT mag — and SCALE).
  * apply_hard_limits (frozen ensemble.py):
      - managed-cross cap: |EURCHF|, |EURSEK|, |EURNOK|, |AUDNZD| <= 0.5
        ABSOLUTE, post-scale, at ALL bars (cross_cap=0.5 default is not
        multiplied by scale — the Gemini 0.5*scale bug is the
        counterexample);
      - overnight-gold cap: |XAUUSD| <= gold_cap on server hours
        h >= 21 or h < 6 (i.e. 21,22,23,0,1,2,3,4,5) — from
        `overnight = (hrs >= 21) | (hrs < 6)`.
    Clip order (crosses first, gold second) is irrelevant: disjoint
    columns.

Scalar float64, one bar at a time: no pandas, no numpy vectorization
across time, no future reads.  Python float == IEEE-754 binary64.
"""

# ---- frozen constants (eval_v34_pin_s10.py) --------------------------------
V2_CAPS = {"meanrev": 0.11, "carry_breakout": 0.046, "seasonal": 0.18,
           "intraday": 0.168, "crisis": 0.10, "trend_v2": 0.042,
           "crypto_smart": 0.13}
SCALE = 10.0
MAG_W = 0.05

# build_c2 sleeve dict insertion order == combine() accumulation order
SLEEVE_ORDER = ("meanrev", "carry_breakout", "seasonal", "intraday",
                "crisis", "trend_v2", "crypto_smart", "mag")
WEIGHTS = {**V2_CAPS, "mag": MAG_W}

# ---- frozen constants (ensemble.py apply_hard_limits) ----------------------
CROSS_SYMS = ("EURCHF", "EURSEK", "EURNOK", "AUDNZD")
CROSS_CAP = 0.5                      # ABSOLUTE post-scale, all bars
GOLD_SYM = "XAUUSD"
OVERNIGHT_H_GE = 21                  # (hrs >= 21) | (hrs < 6)
OVERNIGHT_H_LT = 6

HOUR_NS = 3_600_000_000_000
DAY_NS = 86_400_000_000_000


def structural_gold_cap(weights=None, scale=SCALE, primary="seasonal"):
    """DERIVED rule (frozen ensemble.structural_gold_cap): the primary gold
    sleeve's own intended exposure = weights[primary] * scale.  build_c2
    passes V2_CAPS (no mag) and SCALE=10.0 -> 0.18 * 10.0."""
    if weights is None:
        weights = V2_CAPS
    return weights[primary] * scale


class EnsembleStepper:
    """Pointwise scalar shell.

    Construct with {sleeve_name: iterable_of_symbols} describing exactly the
    columns each sleeve position matrix carries (the golden sleeve parquet
    columns — e.g. carry_breakout's 21 kept columns, NOT the stepper's full
    32-symbol output whose extra 11 columns are identically zero and were
    dropped from the frozen sleeve parquet before combine()).

    step(ts_ns, sleeve_rows) with sleeve_rows[name][sym] = that sleeve's
    position at this bar returns {sym: net book position} after weighting,
    scaling and hard limits.  Stateless across bars (the book shell has no
    memory); ts_ns is only used for the server-hour gold window.
    """

    def __init__(self, sleeve_symbols):
        unknown = set(sleeve_symbols) - set(SLEEVE_ORDER)
        if unknown:
            raise ValueError(f"unknown sleeves: {sorted(unknown)}")
        self.order = tuple(n for n in SLEEVE_ORDER if n in sleeve_symbols)
        self.sleeve_symbols = {n: tuple(sleeve_symbols[n]) for n in self.order}
        syms = set()
        for n in self.order:
            syms.update(self.sleeve_symbols[n])
        self.symbols = tuple(sorted(syms))     # pandas .add union is sorted
        # per-symbol contributor fold list [(sleeve, weight), ...] in order
        self.contrib = {
            s: tuple((n, WEIGHTS[n]) for n in self.order
                     if s in self.sleeve_symbols[n])
            for s in self.symbols
        }
        self.gold_cap = structural_gold_cap()  # derived, never hardcoded

    def step(self, ts_ns, sleeve_rows):
        hour = (ts_ns // HOUR_NS) % 24
        overnight = (hour >= OVERNIGHT_H_GE) or (hour < OVERNIGHT_H_LT)
        out = {}
        for sym in self.symbols:
            acc = 0.0
            first = True
            for name, w in self.contrib[sym]:
                v = sleeve_rows[name][sym] * w
                if first:
                    acc = v          # `tot = contrib if tot is None`
                    first = False
                else:
                    acc = acc + v    # tot.add(contrib)
            acc = acc * SCALE        # combine(...) * SCALE, post-sum
            # hard limits (frozen apply_hard_limits), post-scale
            if sym in CROSS_SYMS:
                if acc > CROSS_CAP:
                    acc = CROSS_CAP
                elif acc < -CROSS_CAP:
                    acc = -CROSS_CAP
            if overnight and sym == GOLD_SYM:
                g = self.gold_cap
                if acc > g:
                    acc = g
                elif acc < -g:
                    acc = -g
            out[sym] = acc
        return out
