"""Export the master input CSV for the in-terminal MQL5 replay harness
(mt5/ea/scripts/TestV34Native.mq5).

WHAT IS EXPORTED (and deliberately NOTHING else):
  * the union hourly grid 2020-2025 (49379 rows) as epoch SECONDS, and
  * the RAW close per 37 symbols (core.ALL order) — EMPTY field where the
    symbol printed no bar that hour.  The steppers own ALL ffill / return /
    daily-grid / NaN semantics internally (no vols, no day_valid — the
    Gemini TestBrain2 input contract injected those and is NOT adopted).

Doubles are printed with %.17g so MQL5 StringToDouble reconstructs the
bit-identical IEEE-754 binary64.

The golden expected book stays as the frozen parquet
(model/v3/freeze/FMA3-v34-freeze-1/golden/book.parquet); the comparator
(validate_mql5_book.py) reads it directly — no lossy CSV round-trip.

Run from FMA2/research (pandas 2.3.3 / numpy 2.4.2):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/mql5/export_master_inputs.py

Besides exporting, this script PROVES (bitwise, in Python) the exact
derivation recipes that TestV34Native.mq5 re-implements from the raw
closes, so any harness bug is a translation bug, not a recipe bug:
  (1) streaming ffill of raw closes  == U["close"] (the frozen ffilled matrix)
  (2) streaming xau_ret (prev-NaN->0, clip +-0.30) == U["ret"]["XAUUSD"]
  (3) the day set of the hourly grid == core.daily_closes(ALL).index
      == core.daily_closes(TREND_SYMS).index  (trend steps EVERY grid day)
  (4) ffilled close at the LAST grid row of each day == core.daily_closes()
      for the 14 daily-driven symbols (crisis 10-input row + trend 5, dedup)
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
OUT_DIR = FMA3 / "research/bpure/mql5/out"
OUT_CSV = OUT_DIR / "FMA3_v34_inputs.csv"
OUT_MANIFEST = OUT_DIR / "FMA3_v34_inputs_manifest.json"

for p in (str(FMA2 / "research"), str(FMA2)):
    if p not in sys.path:
        sys.path.insert(0, p)

import core  # noqa: E402

TREND_SYMS = ["XAUUSD", "XAGUSD", "XBRUSD", "XTIUSD", "XNGUSD"]
CRISIS_INPUT_SYMS = ["DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
                     "XAUUSD", "AUDJPY", "NZDJPY", "CADJPY"]

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def bitwise_eq(a: np.ndarray, b: np.ndarray) -> bool:
    """exact equality treating NaN == NaN."""
    return bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def main():
    U = core.universe_frames(tuple(core.ALL))
    grid = U["ret"].index
    n = len(grid)
    ts_sec = grid.asi8 // 10 ** 9
    assert np.all(grid.asi8 == ts_sec * 10 ** 9), "grid not second-aligned"
    log(f"grid: {n} hours [{grid[0]} .. {grid[-1]}], {len(core.ALL)} symbols")

    close_ff = U["close"].to_numpy()                     # ffilled matrix
    raw = U["close"].where(U["has_bar"]).to_numpy()      # raw (NaN = no bar)

    # ---- (1) streaming ffill recipe == frozen ffilled matrix --------------
    ff_stream = np.empty_like(raw)
    cur = np.full(raw.shape[1], np.nan)
    for i in range(n):
        row = raw[i]
        m = ~np.isnan(row)
        cur[m] = row[m]
        ff_stream[i] = cur
    assert bitwise_eq(ff_stream, close_ff), "streaming ffill != U[close]"
    log("recipe (1) streaming ffill == U['close']  (bitwise)")

    # ---- (2) streaming xau_ret recipe == U['ret']['XAUUSD'] ---------------
    xau = close_ff[:, core.ALL.index("XAUUSD")]
    ret_stream = np.zeros(n)
    for i in range(1, n):
        prev = xau[i - 1]
        if prev == prev:                                  # not NaN
            r = xau[i] / prev - 1.0
            if r < -0.30:
                r = -0.30
            elif r > 0.30:
                r = 0.30
            ret_stream[i] = r
    golden_ret = U["ret"]["XAUUSD"].to_numpy()
    assert bitwise_eq(ret_stream, golden_ret), "streaming xau_ret != U['ret']"
    assert not np.isnan(golden_ret).any(), "xau_ret contains NaN"
    log("recipe (2) streaming xau_ret == U['ret']['XAUUSD']  (bitwise)")

    # ---- (3) day sets ------------------------------------------------------
    epoch_day = ts_sec // 86400
    day_change = np.flatnonzero(np.diff(epoch_day)) + 1   # first row of new day
    day_first = np.concatenate([[0], day_change])
    day_last = np.concatenate([day_change - 1, [n - 1]])
    grid_days = epoch_day[day_first]
    assert np.all(np.diff(grid_days) > 0), "grid days not increasing"

    dc_all = core.daily_closes(core.ALL)
    dc_trend = core.daily_closes(TREND_SYMS)
    dc_all_days = dc_all.index.asi8 // (86400 * 10 ** 9)
    dc_trend_days = dc_trend.index.asi8 // (86400 * 10 ** 9)
    assert np.array_equal(grid_days, dc_all_days), \
        "grid day set != daily_closes(ALL) day set"
    assert np.array_equal(grid_days, dc_trend_days), \
        "grid day set != daily_closes(TREND) day set — trend must NOT " \
        "step every grid day; harness recipe invalid"
    log(f"recipe (3) day sets identical: {len(grid_days)} grid days == "
        f"daily_closes(ALL) == daily_closes(TREND)")

    # weekday split (crisis steps Mon-Fri only; dow: Mon=0 via (d+3)%7)
    dow = (grid_days + 3) % 7
    n_weekdays = int((dow < 5).sum())
    dc_all_wd = dc_all[dc_all.index.dayofweek < 5]
    assert n_weekdays == len(dc_all_wd), "weekday recipe mismatch"
    log(f"recipe (3b) weekday filter (d+3)%7<5: {n_weekdays} crisis days "
        f"== pandas dayofweek<5")

    # ---- (4) day-last-row ffilled close == daily_closes --------------------
    daily_syms = list(dict.fromkeys(CRISIS_INPUT_SYMS + TREND_SYMS))
    for s in daily_syms:
        mine = close_ff[day_last, core.ALL.index(s)]
        gold = dc_all[s].to_numpy()
        assert bitwise_eq(mine, gold), f"day-last-row close != daily_closes: {s}"
    log(f"recipe (4) ffilled close at day-last row == daily_closes "
        f"({len(daily_syms)} daily-driven symbols, bitwise)")

    # ---- write the CSV ------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"writing {OUT_CSV} ...")
    with open(OUT_CSV, "w", newline="\n") as f:
        f.write("timestamp," + ",".join(core.ALL) + "\n")
        for i in range(n):
            row = raw[i]
            cells = [str(int(ts_sec[i]))]
            for v in row:
                cells.append("" if v != v else "%.17g" % v)
            f.write(",".join(cells) + "\n")

    size = OUT_CSV.stat().st_size
    sha = hashlib.sha256(OUT_CSV.read_bytes()).hexdigest()
    n_cells = int(raw.size)
    n_empty = int(np.isnan(raw).sum())

    # round-trip self-check: parse the file back, must be bit-identical
    log("round-trip parse check ...")
    import csv as _csv
    with open(OUT_CSV) as f:
        rd = _csv.reader(f)
        header = next(rd)
        assert header == ["timestamp"] + core.ALL
        for i, line in enumerate(rd):
            assert int(line[0]) == ts_sec[i]
            for j, c in enumerate(line[1:]):
                v = raw[i, j]
                if c == "":
                    assert v != v, f"row {i} col {j}: empty but golden {v}"
                else:
                    p = float(c)
                    assert p == v and np.float64(p).tobytes() == \
                        np.float64(v).tobytes(), f"row {i} col {j} not bitwise"
        assert i == n - 1
    log("round-trip parse check OK (bit-identical)")

    manifest = {
        "csv": str(OUT_CSV),
        "sha256": sha,
        "bytes": size,
        "rows": n,
        "symbols": core.ALL,
        "n_symbols": len(core.ALL),
        "grid_start": str(grid[0]),
        "grid_end": str(grid[-1]),
        "n_days": int(len(grid_days)),
        "n_weekdays": n_weekdays,
        "cells": n_cells,
        "empty_cells": n_empty,
        "format": "timestamp epoch-seconds; raw close %.17g; empty = no bar",
        "recipes_proven_bitwise": [
            "streaming ffill == U['close']",
            "streaming xau_ret == U['ret']['XAUUSD'] (never NaN)",
            "grid day set == daily_closes(ALL).index == daily_closes(TREND).index",
            "weekday filter (epoch_day+3)%7 < 5 == pandas dayofweek<5",
            "ffilled close at day-last row == daily_closes (14 daily symbols)",
        ],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2))
    log(f"wrote {OUT_MANIFEST}")
    print("RESULT " + json.dumps({k: manifest[k] for k in
                                  ("rows", "n_symbols", "bytes", "sha256",
                                   "n_days", "n_weekdays", "empty_cells")}))


if __name__ == "__main__":
    main()
