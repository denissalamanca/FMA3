"""Compare the MQL5 in-terminal replay output (TestV34Native.mq5) against
the frozen golden book.

  actual : FMA3_v34_native_actual.csv written by the terminal Script to the
           Common Files dir (timestamp epoch-seconds + 31 book columns,
           %.17g) — default path is the wine-prefix Common Files; override
           with argv[1].
  golden : model/v3/freeze/FMA3-v34-freeze-1/golden/book.parquet
           (49379 x 31) — read directly, no lossy CSV round-trip.

Reports max|diff|, cells > 1e-12, per-symbol worst, first divergent
(hour, symbol).  Exit 0 iff shapes/timestamps/columns match, no NaNs in
the actual, and NO cell differs by more than 1e-12 (same gate as the
Python-side book parity, research/bpure/parity/book_parity.json).

Usage:
  python3 validate_mql5_book.py [actual_csv]
Writes mql5_book_parity.json next to this file.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
GOLD_BOOK = FMA3 / "model/v3/freeze/FMA3-v34-freeze-1/golden/book.parquet"
COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")
DEFAULT_ACTUAL = COMMON_FILES / "FMA3_v34_native_actual.csv"
OUT_JSON = FMA3 / "research/bpure/mql5/mql5_book_parity.json"

GATE = 1e-12

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def fail(result: dict, reason: str):
    result["pass"] = False
    result["fail_reason"] = reason
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    log(f"FAIL: {reason}")
    print("RESULT " + json.dumps(result, default=str))
    sys.exit(1)


def main():
    actual_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ACTUAL
    result = {"check": "mql5_book_parity", "actual_csv": str(actual_csv),
              "golden": str(GOLD_BOOK), "gate": GATE}

    if not actual_csv.exists():
        fail(result, f"actual csv not found: {actual_csv}")

    golden = pd.read_parquet(GOLD_BOOK)
    grid = golden.index
    g_ts = grid.asi8 // 10 ** 9
    g_np = golden.to_numpy()
    book_syms = list(golden.columns)
    log(f"golden book: {golden.shape} [{grid[0]} .. {grid[-1]}]")

    # float_precision='round_trip': the default C-parser xstrtod is NOT
    # correctly rounded (~1 ulp read noise, measured 4.4e-16 on a lossless
    # %.17g dump of the golden itself) — it would pollute the measurement
    act = pd.read_csv(actual_csv, float_precision="round_trip")
    log(f"actual csv:  {act.shape}")
    result["actual_shape"] = list(act.shape)

    # ---- structure ---------------------------------------------------------
    if list(act.columns)[0] != "timestamp":
        fail(result, f"first column is '{act.columns[0]}', not 'timestamp'")
    if list(act.columns)[1:] != book_syms:
        fail(result, "column names/order != golden book columns: "
             f"{list(act.columns)[1:]} vs {book_syms}")
    if len(act) != len(golden):
        fail(result, f"row count {len(act)} != golden {len(golden)}")
    a_ts = act["timestamp"].to_numpy(np.int64)
    if not np.array_equal(a_ts, g_ts):
        i = int(np.flatnonzero(a_ts != g_ts)[0])
        fail(result, f"timestamp mismatch at row {i}: actual {a_ts[i]} != "
             f"golden {g_ts[i]} ({grid[i]})")
    a_np = act[book_syms].to_numpy(np.float64)
    n_nan = int(np.isnan(a_np).sum())
    result["actual_nan_cells"] = n_nan
    if n_nan:
        ii, jj = np.argwhere(np.isnan(a_np))[0]
        fail(result, f"actual contains {n_nan} NaN cells, first at "
             f"({grid[ii]}, {book_syms[jj]})")

    # ---- diff --------------------------------------------------------------
    diff = np.abs(a_np - g_np)
    maxabs = float(diff.max())
    n_nonzero = int(np.count_nonzero(diff))
    n_gt_gate = int((diff > GATE).sum())
    cells = int(diff.size)

    per_sym = {}
    for j, s in enumerate(book_syms):
        w = float(diff[:, j].max())
        per_sym[s] = w
    worst_sorted = dict(sorted(per_sym.items(), key=lambda kv: -kv[1]))

    first_div = None
    if n_nonzero:
        ii, jj = np.argwhere(diff > 0)[0]
        first_div = {"hour": str(grid[ii]), "symbol": book_syms[jj],
                     "actual": float(a_np[ii, jj]),
                     "golden": float(g_np[ii, jj]),
                     "absdiff": float(diff[ii, jj])}
    first_gt = None
    if n_gt_gate:
        ii, jj = np.argwhere(diff > GATE)[0]
        first_gt = {"hour": str(grid[ii]), "symbol": book_syms[jj],
                    "actual": float(a_np[ii, jj]),
                    "golden": float(g_np[ii, jj]),
                    "absdiff": float(diff[ii, jj])}

    result.update({
        "cells_total": cells,
        "max_absdiff": maxabs,
        "cells_nonzero": n_nonzero,
        "cells_gt_gate": n_gt_gate,
        "per_symbol_worst": worst_sorted,
        "first_divergent": first_div,
        "first_gt_gate": first_gt,
    })
    log(f"max|diff| {maxabs:.3e} | nonzero {n_nonzero}/{cells} | "
        f">"
        f"{GATE:g}: {n_gt_gate}")
    log("worst symbols: " + json.dumps(
        {k: f"{v:.3e}" for k, v in list(worst_sorted.items())[:5]}))
    if first_div:
        log(f"first divergent cell: {first_div}")

    if n_gt_gate:
        fail(result, f"{n_gt_gate} cells exceed the {GATE:g} gate "
             f"(first: {first_gt})")

    result["pass"] = True
    result["runtime_sec"] = round(time.time() - T0, 1)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    log(f"PASS — wrote {OUT_JSON}")
    print("RESULT " + json.dumps(result, default=str))
    sys.exit(0)


if __name__ == "__main__":
    main()
