#!/usr/bin/env python3
"""Judge for the Track-C blend harness: diff an actual netted stream
(TestBlend.mq5 in-terminal output, or mirror_blend.py's statement-mirror
output) against the golden netted streams.

Goldens:
  * golden12 = research/outputs/mt5/FMA3_fed_frac_v3.csv - THE model-of-
    record artifact (RECON-4 pinned sha256 d00b614b...), values quantized
    to 12 decimals by the exporter. Bit-exact blend arithmetic can differ
    from it by at most the quantization (5e-13), so the PASS bar is
    max|diff| <= 1e-12.
  * golden17 = research/outputs/mt5/blend/FMA3_blend_golden17.csv - the
    same stream at %.17g (binary64 round-trip), written by
    export_blend_inputs.py. Bit-exact arithmetic must hit max|diff| == 0.

Structure is compared exactly: the (epoch, symbol) row sequence - data
rows AND __GRID__ sentinels, in file order - must be IDENTICAL, so the
emission semantics (EPS threshold, broker map, ordering) are validated
along with the arithmetic.

Usage:
  python3 research/bpure/blend/validate_blend.py                 # judge the mirror output
  python3 research/bpure/blend/validate_blend.py --actual <csv>  # judge a terminal output
  (add --from-common to pull FMA3_blend_actual.csv out of MT5 Common\\Files)
"""
from __future__ import annotations
import argparse
from pathlib import Path

REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
MIRROR   = REPO / "research/outputs/mt5/blend/FMA3_blend_actual_mirror.csv"
GOLD12   = REPO / "research/outputs/mt5/FMA3_fed_frac_v3.csv"
GOLD17   = REPO / "research/outputs/mt5/blend/FMA3_blend_golden17.csv"
COMMON_ACTUAL = Path.home() / ("Library/Application Support/net.metaquotes.wine.metatrader5/"
                               "drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/"
                               "Common/Files/FMA3_blend_actual.csv")
PASS12 = 1e-12


def load_stream(path: Path):
    """-> (keys, vals): keys = [(epoch, symbol)] in file order ('__GRID__'
    rows included with value 0.0), vals aligned. Header line skipped."""
    keys, vals = [], []
    with open(path) as fh:
        fh.readline()
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            f = line.split(",")
            assert len(f) == 3, f"bad row in {path.name}: {line!r}"
            keys.append((int(f[0]), f[1]))
            vals.append(float(f[2]))
    return keys, vals


def judge(name: str, akeys, avals, gkeys, gvals, bar: float | None):
    if akeys != gkeys:
        # locate the first structural divergence for the report
        n = min(len(akeys), len(gkeys))
        first = next((i for i in range(n) if akeys[i] != gkeys[i]), n)
        print(f"vs {name}: STRUCTURE MISMATCH - actual {len(akeys)} rows vs "
              f"golden {len(gkeys)}; first divergence at row {first}: "
              f"actual {akeys[first] if first < len(akeys) else '<eof>'} vs "
              f"golden {gkeys[first] if first < len(gkeys) else '<eof>'}")
        return False, float("inf")
    maxd = 0.0
    argmax = None
    for i in range(len(avals)):
        d = abs(avals[i] - gvals[i])
        if d > maxd:
            maxd = d
            argmax = gkeys[i]
    ok = (maxd <= bar) if bar is not None else (maxd == 0.0)
    barstr = f"<= {bar:g}" if bar is not None else "== 0"
    print(f"vs {name}: rows={len(akeys):,} structure=IDENTICAL  "
          f"max|diff|={maxd:.3e} at {argmax}  ({'PASS' if ok else 'FAIL'} {barstr})")
    return ok, maxd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--actual", type=Path, default=MIRROR)
    ap.add_argument("--from-common", action="store_true",
                    help="judge the MT5 Common\\Files TestBlend output")
    a = ap.parse_args()
    actual = COMMON_ACTUAL if a.from_common else a.actual

    print(f"actual  : {actual}")
    akeys, avals = load_stream(actual)
    ok = True
    g12k, g12v = load_stream(GOLD12)
    ok12, d12 = judge("golden12 (FMA3_fed_frac_v3.csv, 12dp)", akeys, avals,
                      g12k, g12v, PASS12)
    ok &= ok12
    if GOLD17.exists():
        g17k, g17v = load_stream(GOLD17)
        ok17, d17 = judge("golden17 (%.17g)", akeys, avals, g17k, g17v, None)
        ok &= ok17
    else:
        print(f"[WARN] {GOLD17} missing - run export_blend_inputs.py first")
        ok = False
    print(f"OVERALL : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
