"""validate_book_stream.py — the R1 whole-book stream judge.

Diffs a produced book_frac replay stream (the python mirror's
FMA3_book_mirror_actual.csv or the in-terminal TestBook.mq5 output
FMA3_book_actual.csv) against the RECON-4-pinned golden stream
research/outputs/mt5/FMA3_fed_frac_v3.csv (sha256 d00b614b650b649a...,
805,585 rows incl. 402 __GRID__ sentinels).

WHAT IS JUDGED
--------------
* STRUCTURE: the (epoch, symbol) row sequence must be IDENTICAL —
  same hours, same emitted legs per hour, same sentinels, same order
  (epoch ascending; broker-name ordinal within the hour). A structural
  mismatch fails regardless of values and is reported with +-3 rows of
  context on both sides.
* VALUES: per data row, |actual - golden| where both sides are parsed
  as float64. PASS requires max|diff| <= 1e-12 (the S1 gate).
  QUANTIZATION AWARENESS: the golden is written %.12f, so a bit-exact
  compute can still differ from the parsed golden by up to 5e-13 (half
  an ulp of the 12th decimal). Rows with diff <= 5e-13 are counted
  separately — a run whose every diff is within the quantization bound
  is as good as bit-exact (Track-C precedent). Sentinel rows compare
  by symbol only (golden value token is the literal '0').

Both streams may carry one header line containing 'config_hash=' —
it is skipped (and NOT compared: the golden says fmt=3, the producers
stamp their src).

Usage:
  python3 validate_book_stream.py <actual.csv> [--golden PATH]
      [--tol 1e-12] [--report out.json]
Exit 0 = PASS, 1 = FAIL. Also importable: parse_stream(), compare().
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
GOLDEN_DEFAULT = REPO / "research/outputs/mt5/FMA3_fed_frac_v3.csv"
QUANT_BOUND = 5e-13          # half-ulp of the 12dp golden quantization
SENTINEL = "__GRID__"


def parse_stream(path):
    """[(epoch:int, symbol:str, value_token:str), ...]; header skipped."""
    rows = []
    with open(path) as fh:
        first = fh.readline().rstrip("\r\n")
        if "config_hash=" not in first and first:
            f = first.split(",")
            if len(f) == 3:
                rows.append((int(f[0]), f[1], f[2]))
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                continue
            f = line.split(",")
            assert len(f) == 3, f"malformed row in {path}: {line[:80]!r}"
            rows.append((int(f[0]), f[1], f[2]))
    return rows


def _context(rows, i, n=3):
    lo, hi = max(0, i - n), min(len(rows), i + n + 1)
    return [f"[{k}] {rows[k][0]},{rows[k][1]},{rows[k][2]}"
            for k in range(lo, hi)]


def compare(actual_rows, golden_rows, tol: float = 1e-12) -> dict:
    """Structural + numeric diff. Returns a MEASURED report dict."""
    na, ng = len(actual_rows), len(golden_rows)
    rep = {"rows_actual": na, "rows_golden": ng,
           "structural_ok": True, "first_divergence": None,
           "max_abs_diff": 0.0, "argmax": None,
           "n_over_tol": 0, "n_over_quant_bound": 0,
           "n_data_rows": 0, "n_sentinels_actual": 0,
           "n_sentinels_golden": 0, "tol": tol,
           "quant_bound": QUANT_BOUND}
    n = min(na, ng)
    for i in range(n):
        ea, sa, va = actual_rows[i]
        eg, sg, vg = golden_rows[i]
        if ea != eg or sa != sg:
            rep["structural_ok"] = False
            rep["first_divergence"] = {
                "row": i,
                "actual": f"{ea},{sa},{va}",
                "golden": f"{eg},{sg},{vg}",
                "context_actual": _context(actual_rows, i),
                "context_golden": _context(golden_rows, i)}
            break
        if sa == SENTINEL:
            rep["n_sentinels_actual"] += 1
            rep["n_sentinels_golden"] += 1
            continue
        d = abs(float(va) - float(vg))
        rep["n_data_rows"] += 1
        if d > rep["max_abs_diff"]:
            rep["max_abs_diff"] = d
            rep["argmax"] = {"row": i, "epoch": ea, "symbol": sa,
                             "actual": va, "golden": vg}
        if d > tol:
            rep["n_over_tol"] += 1
        if d > QUANT_BOUND:
            rep["n_over_quant_bound"] += 1
    if rep["structural_ok"] and na != ng:
        rep["structural_ok"] = False
        i = n
        rep["first_divergence"] = {
            "row": i, "reason": f"row count {na} vs {ng}",
            "context_actual": _context(actual_rows, i),
            "context_golden": _context(golden_rows, i)}
    rep["pass"] = bool(rep["structural_ok"] and rep["max_abs_diff"] <= tol)
    rep["within_quant_bound"] = bool(rep["structural_ok"]
                                     and rep["n_over_quant_bound"] == 0)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("actual")
    ap.add_argument("--golden", default=str(GOLDEN_DEFAULT))
    ap.add_argument("--tol", type=float, default=1e-12)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    actual = parse_stream(Path(args.actual))
    golden = parse_stream(Path(args.golden))
    rep = compare(actual, golden, tol=args.tol)
    rep["actual_path"] = str(args.actual)
    rep["golden_path"] = str(args.golden)

    print(f"validate_book_stream: actual {rep['rows_actual']:,} rows vs "
          f"golden {rep['rows_golden']:,} rows")
    print(f"  structural_ok       : {rep['structural_ok']}")
    if rep["first_divergence"]:
        fd = rep["first_divergence"]
        print(f"  FIRST DIVERGENCE at row {fd['row']}:")
        for k in ("actual", "golden", "reason"):
            if k in fd:
                print(f"    {k:7s}: {fd[k]}")
        print("    context (actual): " + " | ".join(fd["context_actual"]))
        print("    context (golden): " + " | ".join(fd["context_golden"]))
    print(f"  data rows compared  : {rep['n_data_rows']:,} "
          f"(+ {rep['n_sentinels_actual']:,} sentinels)")
    print(f"  max|diff|           : {rep['max_abs_diff']:.6g}"
          + (f"  at {rep['argmax']}" if rep["argmax"] else ""))
    print(f"  rows > tol {rep['tol']:g}   : {rep['n_over_tol']:,}")
    print(f"  rows > quant 5e-13  : {rep['n_over_quant_bound']:,}")
    print(f"  VERDICT             : "
          f"{'PASS' if rep['pass'] else 'FAIL'} (tol {rep['tol']:g}; "
          f"within 12dp quantization bound: {rep['within_quant_bound']})")
    if args.report:
        Path(args.report).write_text(json.dumps(rep, indent=1))
        print(f"  report -> {args.report}")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
