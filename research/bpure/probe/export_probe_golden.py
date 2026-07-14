"""S0 feed probe — golden union-grid + has_bar export (FABLE REVISION v2 item 4).

Exports the SAME probe week the FeedProbe.mq5 EA measures, but from the frozen
FMA2 research cache (the 1m union the engines of record consume), so
judge_feedprobe.py can compare terminal-furnished data against the golden.

Data prep is REUSED READ-ONLY from FMA2 account_engine_1m (the exact code paths
bh_stepper.iter_chunks uses): A1._native for per-symbol native M1 indices,
A1._densify for the has_bar mask on the union grid, A1._EUR_CROSS for the eurq
cross set. Nothing is re-derived.

Universe: the 33-symbol Fable-book universe (MODEL names) + the eurq EUR
crosses derived exactly as iter_chunks derives them ({A1._EUR_CROSS[quote]}
over the book, quote != EUR) -> 8 crosses, of which only EURJPY is not already
a book symbol -> 34 unique load symbols. Emitted under BROKER names with the
exporter remap (DAX->DE40, USA500->US500; BookReplay.mqh g_fedCanon
convention) so the CSV columns match FeedProbe.mq5 byte-for-byte.

Output: FMA3_feedprobe_golden.csv in the terminal Common Files dir (same
format as FMA3_feedprobe_<mode>.csv written by the EA):
    #meta,mode=golden,window_start=<epoch>,window_end=<epoch>,nsym=34,...
    #depth,<broker_sym>,select=1,done=1,earliest=<epoch>,bars2020=<n>,
           bars_window=<n>,misaligned=0
    #cols,ts,<broker syms...>
    <ts_epoch>,0/1,...          one row per union-grid minute in the window

Timestamps are naive server-time epochs (cache index int64ns // 1e9), the same
convention as MQL5 datetime (iTime semantics), so rows compare directly.

Run:  python3 research/bpure/probe/export_probe_golden.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "engine"
for _p in (str(ENGINE),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bh_stepper as BH  # noqa: E402  (injects FMA2/research sys.path, read-only)

COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")

# 33-symbol Fable-book universe in MODEL names (BookReplay.mqh g_fedCanon with
# the emit remap inverted: DE40->DAX, US500->USA500). Alphabetical in BOTH
# namings (verified: DAX and USA500 sort to the same positions as DE40/US500).
BOOK33 = [
    "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "BTCUSD", "CADCHF", "CADJPY",
    "DAX", "ETHUSD", "EURCAD", "EURCHF", "EURGBP", "EURNOK", "EURNZD",
    "EURSEK", "EURUSD", "GBPJPY", "JP225", "NZDCAD", "NZDJPY", "NZDUSD",
    "SOLUSD", "UK100", "US30", "USA500", "USDCHF", "USDJPY", "USTEC",
    "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XTIUSD",
]
MODEL2BROKER = {"DAX": "DE40", "USA500": "US500"}  # exporter emit remap

# Probe window (server time): Mon-Fri week 2024-03-04..08 + both surrounding
# weekends (crypto weekend bars). MUST match FeedProbe.mq5 InpWinStart/End.
WIN_START = "2024-03-02 00:00:00"
WIN_END = "2024-03-10 23:59:00"
DEPTH_REF = "2020-01-02 00:00:00"   # golden cache start (bh depth requirement)


def export(out_path: Path | None = None) -> Path:
    import numpy as np
    import pandas as pd
    import core                     # noqa: F401  (FMA2 path injected by BH)
    import account_engine_1m as A1

    # eurq crosses EXACTLY as bh_stepper.iter_chunks derives them
    crosses = sorted({A1._EUR_CROSS[core.S.INSTRUMENTS[s]["quote"]]
                      for s in BOOK33
                      if core.S.INSTRUMENTS[s]["quote"] != "EUR"})
    load_syms = list(dict.fromkeys(BOOK33 + crosses))   # 34 unique, book order first
    load_syms = sorted(load_syms)                       # deterministic column order
    brokers = [MODEL2BROKER.get(s, s) for s in load_syms]
    assert brokers == sorted(brokers), "broker naming must preserve sort order"

    t0 = np.int64(pd.Timestamp(WIN_START).value)
    t1 = np.int64(pd.Timestamp(WIN_END).value)
    d0 = np.int64(pd.Timestamp(DEPTH_REF).value)
    d1 = np.int64(pd.Timestamp(DEPTH_REF).value + 7 * 86400 * 10**9)

    # union grid over the window = union of native M1 minutes of ALL load
    # symbols (iter_chunks lines: grids.append(idx[lo:hi]); np.unique(concat))
    grids, earliest, bars2020, nat_idx = [], {}, {}, {}
    for s in load_syms:
        idx, _ = A1._native(s)
        nat_idx[s] = idx
        earliest[s] = int(idx[0] // 10**9)
        lo = np.searchsorted(idx, t0, side="left")
        hi = np.searchsorted(idx, t1, side="right")
        grids.append(idx[lo:hi])
        b0 = np.searchsorted(idx, d0, side="left")
        b1 = np.searchsorted(idx, d1, side="left")
        bars2020[s] = int(b1 - b0)
    grid_ns = np.unique(np.concatenate(grids))
    assert grid_ns.size > 0, "empty probe window"
    assert ((grid_ns // 10**9) % 60 == 0).all(), "non-minute-aligned cache bar"

    # has_bar per symbol on the union grid — A1._densify semantics (read-only)
    has = np.zeros((grid_ns.size, len(load_syms)), dtype=np.bool_)
    for k, s in enumerate(load_syms):
        hb, _ = A1._densify(s, grid_ns)
        has[:, k] = hb
    bars_window = has.sum(axis=0)

    ts = (grid_ns // 10**9).astype(np.int64)
    if out_path is None:
        out_path = COMMON_FILES / "FMA3_feedprobe_golden.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(
        f"#meta,mode=golden,window_start={t0 // 10**9},window_end={t1 // 10**9},"
        f"nsym={len(load_syms)},depth_ref={d0 // 10**9},tries=0,"
        f"symbols_done={len(load_syms)},server=NSF5_cache_bars_1m_ic,"
        f"company=frozen_golden,created={time.strftime('%Y-%m-%dT%H:%M:%S')}")
    for k, s in enumerate(load_syms):
        lines.append(
            f"#depth,{brokers[k]},select=1,done=1,earliest={earliest[s]},"
            f"bars2020={bars2020[s]},bars_window={int(bars_window[k])},misaligned=0")
    lines.append("#cols,ts," + ",".join(brokers))
    body = ["%d,%s" % (ts[i], ",".join("1" if v else "0" for v in has[i]))
            for i in range(grid_ns.size)]
    out_path.write_text("\n".join(lines + body) + "\n")

    print(f"golden written: {out_path}")
    print(f"  window {WIN_START} .. {WIN_END} | union minutes {grid_ns.size:,}")
    print(f"  symbols ({len(load_syms)}): " + ",".join(brokers))
    for k, s in enumerate(load_syms):
        import datetime as _dt
        e = _dt.datetime.utcfromtimestamp(earliest[s]).strftime("%Y-%m-%d %H:%M")
        print(f"  {brokers[k]:<7} earliest={e} bars2020wk={bars2020[s]:>5} "
              f"bars_window={int(bars_window[k]):>6}")
    return out_path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    export(out)
