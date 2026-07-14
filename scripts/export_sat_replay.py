#!/usr/bin/env python3
"""Export the FMA3 v3.4 frozen-targets replay CSV for FableFederation_V1.mq5
(``Include/FMA3/V34Replay.mqh``) — SPEC.md §3, FMA3-side regeneration contract.

WHAT THIS PRODUCES
------------------
``Common\\Files\\FMA3_v34_replay.csv`` (staged via --install; the repo copy lands
in ``research/outputs/mt5/``):

    line 1 :  global_scale=10.0,config_hash=51a7541cc2aaa593,fmt=2
    rows   :  ts_server_epoch,symbol,exposure_frac,sleeve[,flat_at_server_hour,no_entry_after_hour]
    flat   :  <epoch>,__GRID__,0,flat   (fmt=2 sentinel: one per hour PRESENT in
              the brain's hourly index whose legs are ALL zero; hours ABSENT
              from the index — weekends/warmup — get NO row, so absence keeps
              meaning 'no data' and the EA's keep-last-good correctly holds)

ONE native scale-10 file serves every preset — the deployment dial lives in the
EA (``InpV34Mult``), deliberately superseding the FMA2 "regenerate + restamp per
dial" pattern (FMA2_EA_AUDIT.md §3).

PROVENANCE / FAITHFULNESS
-------------------------
* Legs come from the READ-ONLY FMA2 brain path
  ``ea/brain/target_engine.build_book(rebuild=False)`` on frozen parquets — the
  audited exporter's exact data path (no 1m cache, no record engine:
  busy-engine-safe). ``per_sleeve_capped`` sums to ``net_capped`` by
  construction (pro-rata hard-limit distribution).
* The net book is cross-verified against the PINNED FMA3 artifact
  ``engine/books.py::build_sat_frac_1h()`` (the fma3_v1_pin.json v34 positions
  reference) — any drift between the brain path and the pin hard-fails.
* Config drift hard-fails twice: the FMA2 brain hash must equal
  ``48c09199fbf83d82`` (the v3.4 book lock) AND the FMA3 blend hash
  (``strategy_fma3.config_hash()``) must equal ``51a7541cc2aaa593`` — the value
  stamped in the header and compiled into the EA (``F3_V34_CONFIG_HASH``).
* Exit metadata verbatim from ``brain_config.SLEEVE_SCHEDULE`` (seasonal 6/5,
  intraday 21/20); sleeve names/order from ``brain_config.SLEEVES`` (the EA's
  fixed magic map 8400001..8400008).
* ``ts_server_epoch`` = the H1 bar-open server wall clock interpreted as
  seconds-since-1970 with NO timezone shift (``iTime()`` semantics;
  2020-01-02 00:00 server = 1577923200).
* 12-decimal fracs; the script RE-PARSES its own output and asserts per-(hour,
  symbol) leg sums reproduce ``net_capped`` to < 1e-9.
* The file sha256 is printed — record it in mt5/ea/RUNSHEET.md next to the
  tester run that consumed it.

Usage:
    python3 scripts/export_v34_replay.py            # export + validate
    python3 scripts/export_v34_replay.py --install  # + copy to MT5 Common\\Files
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA2_BRAIN = FMA2 / "ea" / "brain"

OUT_CSV = FMA3 / "research" / "outputs" / "mt5" / "FMA3_v34_replay.csv"
COMMON_FILES = Path.home() / (
    "Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
)

# The two locks (SPEC §3 as amended: the header carries the FMA3 v1.0 pin hash,
# which is also the EA's compiled F3_V34_CONFIG_HASH; the FMA2 brain hash is
# still asserted as the v3.4-book drift guard).
FMA3_PIN_HASH = "51a7541cc2aaa593"
FMA2_BOOK_HASH = "48c09199fbf83d82"

EPS = 1e-9
GLOBAL_SCALE_ECHO = 10.0        # native scale-10 book; EA dial = InpV34Mult
CSV_FMT = 2                     # fmt=2: flat-hour __GRID__ sentinels (SPEC CHANGE 1)
SENTINEL_SYM = "__GRID__"       # fmt=2 flat-hour marker; never a tradable symbol


def _epochs(index: pd.DatetimeIndex) -> np.ndarray:
    """Naive server-time stamps -> seconds-since-1970 (the integer MT5 stores)."""
    return (index.astype("int64") // 10**9).to_numpy()


def build_rows(net: pd.DataFrame, per: dict, C) -> list:
    """One row per (hour, sleeve, symbol) with |frac| > 1e-9, sorted by
    (hour, sleeve rank, symbol). Exit metadata verbatim from C.SLEEVE_SCHEDULE.

    fmt=2: every hour PRESENT in the brain's hourly index (net.index) that got
    ZERO leg rows (all legs flat) gets exactly ONE ``__GRID__`` sentinel row so
    the EA's exact-match cursor finds the hour and flattens instead of
    keep-last-good. Hours ABSENT from the index get nothing."""
    epochs = _epochs(net.index)
    rank = {n: i for i, n in enumerate(C.SLEEVES)}
    rows = []
    for n in C.SLEEVES:
        df = per[n]
        sched = C.SLEEVE_SCHEDULE.get(n, {})
        flat = sched.get("flat_at_server_hour")
        noent = sched.get("no_entry_after_hour")
        arr = df.to_numpy()
        for j, sym in enumerate(df.columns):
            col = arr[:, j]
            for i in np.nonzero(np.abs(col) > EPS)[0]:
                rows.append((int(epochs[i]), rank[n], sym, n,
                             float(col[i]), flat, noent))
    emitted = {r[0] for r in rows}
    for ep in epochs:
        if int(ep) not in emitted:
            rows.append((int(ep), -1, SENTINEL_SYM, "flat", 0.0, None, None))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return rows


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(f"global_scale={GLOBAL_SCALE_ECHO:.1f},"
                 f"config_hash={FMA3_PIN_HASH},fmt={CSV_FMT}\n")
        for epoch, _rank, sym, sleeve, frac, flat, noent in rows:
            if sym == SENTINEL_SYM:
                fh.write(f"{epoch},{SENTINEL_SYM},0,flat\n")
                continue
            fs = f"{frac:.12f}"
            if flat is None and noent is None:
                fh.write(f"{epoch},{sym},{fs},{sleeve}\n")
            else:
                fa = "" if flat is None else str(flat)
                ne = "" if noent is None else str(noent)
                fh.write(f"{epoch},{sym},{fs},{sleeve},{fa},{ne}\n")


def reparse_and_validate(path: Path, net: pd.DataFrame, C) -> dict:
    """Re-parse exactly as the EA would (V34Replay.mqh semantics: mandatory
    sleeve col, ascending ts, hash gate) and reconstruct net per (hour,symbol)."""
    row_of = {int(e): i for i, e in enumerate(_epochs(net.index))}
    col_of = {c: j for j, c in enumerate(net.columns)}
    R = np.zeros(net.shape)
    n_rows = 0
    last_ts = 0
    symbols, sleeves = set(), set()
    data_eps, sent_eps = set(), set()
    sched_ok = True
    asc_ok = True
    sent_shape_ok = True
    with open(path) as fh:
        header = fh.readline().rstrip("\n")
        hkv = dict(tok.split("=", 1) for tok in header.split(","))
        assert hkv["config_hash"] == FMA3_PIN_HASH, f"header hash {hkv['config_hash']!r}"
        assert float(hkv["global_scale"]) == GLOBAL_SCALE_ECHO
        assert hkv.get("fmt") == str(CSV_FMT), f"header fmt token: {header!r}"
        for line in fh:
            f = line.rstrip("\n").split(",")
            if len(f) < 4 or not f[3]:
                raise AssertionError(f"row without mandatory sleeve col: {line!r}")
            ep = int(f[0])
            if ep < last_ts:
                asc_ok = False
            last_ts = ep
            if f[1] == SENTINEL_SYM:
                # fmt=2 flat-hour sentinel: exactly <epoch>,__GRID__,0,flat
                if len(f) != 4 or f[2] != "0" or f[3] != "flat" \
                        or ep in sent_eps or ep not in row_of:
                    sent_shape_ok = False
                sent_eps.add(ep)
                n_rows += 1
                continue
            flat = int(f[4]) if len(f) >= 5 and f[4] != "" else -1
            noent = int(f[5]) if len(f) >= 6 and f[5] != "" else -1
            sc = C.SLEEVE_SCHEDULE.get(f[3], {})
            if flat != sc.get("flat_at_server_hour", -1) or \
               noent != sc.get("no_entry_after_hour", -1):
                sched_ok = False
            R[row_of[ep], col_of[f[1]]] += float(f[2])
            symbols.add(f[1]); sleeves.add(f[3])
            data_eps.add(ep)
            n_rows += 1
    # fmt=2 coverage: sentinels and data rows are disjoint and together cover
    # EVERY hour of the brain index (absent hours stay absent by construction).
    sent_cover_ok = (sent_shape_ok
                     and not (sent_eps & data_eps)
                     and (sent_eps | data_eps) == set(row_of))
    return {
        "n_rows": n_rows,
        "n_sentinels": len(sent_eps),
        "n_data": n_rows - len(sent_eps),
        "symbols": sorted(symbols),
        "sleeves": sorted(sleeves),
        "max_diff": float(np.abs(R - net.to_numpy()).max()),
        "sched_ok": sched_ok,
        "asc_ok": asc_ok,
        "sent_ok": sent_cover_ok,
        "min_ep": int(_epochs(net.index).min()),
        "max_ep": last_ts,
    }


def main() -> int:
    install = "--install" in sys.argv[1:]

    # ---- FMA3 blend lock (the stamped hash) ----
    sys.path.insert(0, str(FMA3))
    import strategy_fma3
    fh3 = strategy_fma3.config_hash()
    if fh3 != FMA3_PIN_HASH:
        print(f"[FATAL] FMA3 pin hash drift: got {fh3!r}, expected {FMA3_PIN_HASH!r}")
        return 2

    # ---- FMA2 brain (READ-ONLY import; frozen parquets; no engine) ----
    sys.path.insert(0, str(FMA2_BRAIN))
    import brain_config as C
    import target_engine as T
    bh = C.config_hash()
    if bh != FMA2_BOOK_HASH:
        print(f"[FATAL] FMA2 v3.4 book hash drift: got {bh!r}, expected {FMA2_BOOK_HASH!r}")
        return 2

    print("Building the frozen v3.4 book via FMA2 target_engine.build_book(rebuild=False) ...")
    net, per = T.build_book(rebuild=False)

    # (a) structural: legs sum to net_capped (pre-CSV, unrounded)
    recon = None
    for df in per.values():
        recon = df.copy() if recon is None else recon.add(df, fill_value=0.0)
    recon = recon.reindex(index=net.index, columns=net.columns).fillna(0.0)
    struct_max = float((recon - net).abs().to_numpy().max())

    # (b) cross-verify vs the PINNED FMA3 artifact books.build_sat_frac_1h()
    sys.path.insert(0, str(FMA3 / "engine"))
    import books
    print("Cross-verifying vs the FMA3 pinned artifact books.build_v34_frac_1h() ...")
    net_pin = books.build_sat_frac_1h()
    cols = net.columns.union(net_pin.columns)
    idx = net.index.union(net_pin.index)
    a = net.reindex(index=idx, columns=cols).fillna(0.0)
    b = net_pin.reindex(index=idx, columns=cols).fillna(0.0)
    pin_max = float((a - b).abs().to_numpy().max())
    print(f"pin cross-check  max|brain net - build_v34_frac_1h| = {pin_max:.3e}")
    if pin_max > 1e-12:
        print("[FATAL] the brain path drifted from the FMA3 pinned v3.4 matrix.")
        return 2

    rows = build_rows(net, per, C)
    write_csv(OUT_CSV, rows)
    v = reparse_and_validate(OUT_CSV, net, C)
    sha = hashlib.sha256(OUT_CSV.read_bytes()).hexdigest()

    ok = (v["max_diff"] < 1e-9 and v["sched_ok"] and v["asc_ok"]
          and v["sent_ok"] and len(rows) == v["n_rows"] and struct_max < 1e-9)

    print("\n================ FMA3 v3.4 REPLAY EXPORT ================")
    print(f"file                : {OUT_CSV}")
    print(f"size                : {OUT_CSV.stat().st_size:,} bytes")
    print(f"sha256              : {sha}")
    print(f"header              : global_scale={GLOBAL_SCALE_ECHO:.1f},"
          f"config_hash={FMA3_PIN_HASH},fmt={CSV_FMT}")
    print(f"FMA2 book hash      : {bh}  (drift guard PASS)")
    print(f"total rows          : {v['n_rows']:,}")
    print(f"data rows           : {v['n_data']:,}")
    print(f"flat sentinels      : {v['n_sentinels']:,}  (__GRID__; "
          f"coverage {'PASS' if v['sent_ok'] else 'FAIL'})")
    print(f"distinct symbols({len(v['symbols'])}): {v['symbols']}")
    print(f"distinct sleeves({len(v['sleeves'])}): {v['sleeves']}")
    print(f"server span         : {pd.Timestamp(v['min_ep'], unit='s')} -> {pd.Timestamp(v['max_ep'], unit='s')}")
    print(f"ts ascending        : {v['asc_ok']}")
    print(f"exit-metadata match : {v['sched_ok']}  (== brain_config.SLEEVE_SCHEDULE)")
    print(f"structural sum      : max|sum(legs)-net| = {struct_max:.3e}")
    print(f"SUMS-TO-NET (CSV)   : max|reparsed-net| = {v['max_diff']:.3e}  "
          f"({'PASS' if v['max_diff'] < 1e-9 else 'FAIL'} < 1e-9)")
    print(f"OVERALL             : {'PASS' if ok else 'FAIL'}")
    print("=========================================================")
    if not ok:
        print("[STOP] validation failed - NOT a shippable replay.")
        return 1

    if install:
        if COMMON_FILES.is_dir():
            dst = COMMON_FILES / OUT_CSV.name
            shutil.copy2(OUT_CSV, dst)
            print(f"installed -> {dst}")
        else:
            print(f"[WARN] Common\\Files not found at {COMMON_FILES} - install skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
