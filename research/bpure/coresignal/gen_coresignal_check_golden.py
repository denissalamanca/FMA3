"""gen_coresignal_check_golden.py — golden generator for
mt5/ea/scripts/checks/CheckCoreSignal.mq5 (UNIT 3, compile/smoke gate).

Reproduces the .mq5's DETERMINISTIC synthetic bar generator (64-bit LCG,
IEEE-exact price walk — every operation is a rounded binary64 op with the
same shape in both languages), runs the NORMATIVE reference target
functions (core_signal_reference.gen_*) over the synthetic grid, and
prints the MQL5 arrays to embed in CheckCoreSignal.mq5:

  * CSG_SAMPLE_POS[50] — sampled bar positions (stride 18 over the last
    900 bars, ascending);
  * CSG_EXPECT[9][50]  — the reference targets at those bars, %.17g.

Also runs the mql5_coresignal_mirror steppers (no-fma arithmetic — the
compiled-MQL5 prediction) on the same synthetic bars and reports the
expected in-terminal residual class at the sampled positions.

SCHEDULE (must match the .mq5 verbatim):
  240 days from epoch day 19723 (2024-01-01, Monday), bar hours
  {1, 10, 19, 21, 22, 23} at minute 30 -> 1440 bars per instrument,
  all 8 instruments on the same stamp grid.
LCG (must match the .mq5 verbatim):
  seed_i = (0x9E3779B97F4A7C15 * (i+1)) mod 2^64
  s      = (s*6364136223846793005 + 1442695040888963407) mod 2^64
  u      = ((s >> 40) & 0xFFFFFF) / 16777216.0          (exact dyadic)
  m      = m * (1.0 + ((u - 0.5) * 0.02 + 0.0004))
  spr    = m * 0.0003;  bid = m - spr*0.5;  ask = m + spr*0.5

Usage:
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    .../gen_coresignal_check_golden.py > golden_block.txt
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()

_spec = importlib.util.spec_from_file_location(
    "core_signal_reference", _HERE.parent / "core_signal_reference.py")
CS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CS)

_spec2 = importlib.util.spec_from_file_location(
    "mql5_coresignal_mirror", _HERE.parent / "mql5_coresignal_mirror.py")
MM = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(MM)

MASK = (1 << 64) - 1
K_SEED = 0x9E3779B97F4A7C15
K_MUL = 6364136223846793005
K_ADD = 1442695040888963407

N_DAYS = 240
E0 = 19723                      # 2024-01-01 (Monday)
HOURS = (1, 10, 19, 21, 22, 23)
N_BARS = N_DAYS * len(HOURS)    # 1440

BASES = [2000.0, 150.0, 3000.0, 0.85, 18000.0, 0.65, 0.60, 60000.0]
INST = ["XAUUSD", "USDJPY", "ETHUSD", "EURGBP", "USTEC",
        "AUDUSD", "NZDUSD", "BTCUSD"]

N_SAMPLES = 50
STRIDE = 18


def gen_bars(i):
    """The .mq5 synthetic generator, statement-identical."""
    s = (K_SEED * (i + 1)) & MASK
    m = BASES[i]
    ts = np.empty(N_BARS, dtype=np.int64)
    bid = np.empty(N_BARS)
    ask = np.empty(N_BARS)
    k = 0
    for day in range(N_DAYS):
        for h in HOURS:
            s = (s * K_MUL + K_ADD) & MASK
            u = float((s >> 40) & 0xFFFFFF) / 16777216.0
            m = m * (1.0 + ((u - 0.5) * 0.02 + 0.0004))
            spr = m * 0.0003
            ts[k] = (E0 + day) * 86400 + h * 3600 + 1800
            bid[k] = m - spr * 0.5
            ask[k] = m + spr * 0.5
            k += 1
    return ts, bid, ask


def main():
    bars = {}
    for i, name in enumerate(INST):
        ts, bid, ask = gen_bars(i)
        # ns-unit index: gen_* reads idx.asi8 // 1e9 (pandas 3 keeps the
        # [s] unit on asi8, which would collapse every bar onto day 0)
        idx = pd.DatetimeIndex(ts.astype("datetime64[s]").astype("datetime64[ns]"))
        bars[name] = dict(ts=ts, idx=idx, bid=bid, ask=ask)

    # --- reference targets (the golden) --------------------------------
    tgt = {}
    A = bars["XAUUSD"]
    tgt[0] = CS.gen_xau(A["idx"], A["bid"], A["ask"])
    A = bars["USDJPY"]
    tgt[1], tgt[5] = CS.gen_jpy(A["idx"], A["bid"], A["ask"])
    A = bars["ETHUSD"]
    tgt[2] = CS.gen_eth(A["idx"], A["bid"], A["ask"])
    A = bars["EURGBP"]
    tgt[3] = CS.gen_eg(A["idx"], A["bid"], A["ask"])
    A = bars["USTEC"]
    tgt[4] = CS.gen_ustec(A["idx"], A["bid"], A["ask"])
    A = bars["AUDUSD"]
    tgt[6] = CS.gen_opex_fx(A["idx"], A["bid"], A["ask"], -1)
    A = bars["NZDUSD"]
    tgt[7] = CS.gen_opex_fx(A["idx"], A["bid"], A["ask"], -1)
    A = bars["BTCUSD"]
    tgt[8] = CS.gen_btc(A["idx"], A["bid"], A["ask"])

    # --- mirror (no-fma) prediction of the compiled MQL5 ----------------
    mir = {}
    steppers = {
        "XAUUSD": (MM.LegXauM(), ["out"], [0]),
        "USDJPY": (MM.LegJpyM(), ["out1", "out5"], [1, 5]),
        "ETHUSD": (MM.LegEthM(), ["out"], [2]),
        "EURGBP": (MM.LegEgM(), ["out"], [3]),
        "USTEC": (MM.LegUstecM(), ["out"], [4]),
        "AUDUSD": (MM.LegOpexFxM(-1.0), ["out"], [6]),
        "NZDUSD": (MM.LegOpexFxM(-1.0), ["out"], [7]),
        "BTCUSD": (MM.LegBtcM(), ["out"], [8]),
    }
    for name, (st, attrs, legs) in steppers.items():
        A = bars[name]
        bufs = {leg: np.empty(N_BARS) for leg in legs}
        for k in range(N_BARS):
            st.step(int(A["ts"][k]), float(A["bid"][k]), float(A["ask"][k]))
            for a, leg in zip(attrs, legs):
                bufs[leg][k] = getattr(st, a)
        for leg in legs:
            mir[leg] = bufs[leg]

    pos = sorted(N_BARS - 1 - STRIDE * k for k in range(N_SAMPLES))

    # --- report to stderr ----------------------------------------------
    for j in range(9):
        g = tgt[j][pos]
        m = mir[j][pos]
        d = np.abs(g - m)
        nz = int((g != 0).sum())
        flips = int((np.sign(g) != np.sign(m)).sum())
        print(f"# leg {j}: nonzero {nz}/50  mirror max|d| {d.max():.3e} "
              f"flips {flips}  bit {int((g == m).sum())}/50",
              file=sys.stderr)

    # --- MQL5 embed block ------------------------------------------------
    out = []
    out.append("// ---- python-golden block (GENERATED by "
               "gen_coresignal_check_golden.py — do not edit) ----")
    out.append(f"#define CSG_NSAMP {N_SAMPLES}")
    out.append("int CSG_SAMPLE_POS[CSG_NSAMP] =")
    rows = [", ".join(str(p) for p in pos[k:k + 10]) for k in range(0, 50, 10)]
    out.append("  {" + ",\n   ".join(rows) + "};")
    out.append("// reference targets (fma kernels) at the sampled bars, %.17g")
    out.append("double CSG_EXPECT[9][CSG_NSAMP] =")
    leg_rows = []
    for j in range(9):
        vals = [f"{tgt[j][p]:.17g}" for p in pos]
        rows = [", ".join(vals[k:k + 5]) for k in range(0, 50, 5)]
        leg_rows.append("   {" + ",\n    ".join(rows) + "}")
    out.append("  {\n" + ",\n".join(leg_rows) + "\n  };")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
