#!/usr/bin/env python3
"""Export the UNIFIED fed_frac replay stream for FableFederation_V3.

Emits the netted static_fed(0.70) matrix (33 symbols, the model/v3 stable model)
as a fmt=3 replay CSV. v3 replays it and sizes: lots = net_frac * ACCOUNT_BALANCE
* s / unit_eur, where s is the EA dial (InpScale) — s is NOT baked into the file,
so ONE file serves IC (s=1.6) and FTMO (s=0.7).

Format (fmt=3, simpler than the v34 fmt=2 — pure position replay, no sleeve schedule):
  line 1 : w_v7=0.70,config_hash=51a7541cc2aaa593,fmt=3
  rows   : ts_server_epoch,broker_symbol,net_frac        (net_frac 12 decimals)
  flat   : ts_server_epoch,__GRID__,0                     (one per all-flat hour;
           absent hours => keep-last-good, present-but-flat => flatten)

Self-checks (hard-fail):
  * re-parse -> matrix reproduces static_fed(0.70) to < 1e-12 (always).
  * --verify-engine: record engine on the parsed stream == EUR 3,872,872 (IC s=1.6)
    and EUR 1,332,404 (FTMO s=0.7 breaker 3.0) to the euro (~8 min).

Usage:
  python3 scripts/export_fed_frac_v3.py                 # export + fast (matrix) self-check
  python3 scripts/export_fed_frac_v3.py --verify-engine # + full record-engine reproduction
  python3 scripts/export_fed_frac_v3.py --install        # + copy to MT5 Common\\Files
"""
from __future__ import annotations
import sys, hashlib, argparse
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
sys.path.insert(0, str(REPO / "model" / "v3"))
sys.path.insert(0, str(REPO / "engine"))
import reproduce as M   # canonical static_fed / load_inputs / targets / CONFIG_HASH / W_V7

SYMMAP = {"USA500": "US500", "DAX": "DE40"}          # repo -> broker (others identity)
OUT = REPO / "research" / "outputs" / "mt5" / "FMA3_fed_frac_v3.csv"
COMMON = Path.home() / ("Library/Application Support/net.metaquotes.wine.metatrader5/"
                        "drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files")
EPS = 1e-12
FMT = 3
DECIMALS = 12


def _epochs(idx: pd.DatetimeIndex) -> np.ndarray:
    return (idx.astype("int64") // 10**9).to_numpy()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_rows(fed: pd.DataFrame):
    """One row per (hour, symbol) with |net_frac| > EPS (broker-mapped), plus a
    __GRID__ sentinel for every all-flat hour. Sorted by (epoch, symbol)."""
    ep = _epochs(fed.index)
    cols = list(fed.columns)
    arr = fed.to_numpy()
    rows = []
    emitted = set()
    for i in range(len(ep)):
        e = int(ep[i])
        any_leg = False
        for j, sym in enumerate(cols):
            v = float(arr[i, j])
            if abs(v) > EPS:
                rows.append((e, SYMMAP.get(sym, sym), v))
                any_leg = True
        if any_leg:
            emitted.add(e)
    for e in ep:
        if int(e) not in emitted:
            rows.append((int(e), "__GRID__", 0.0))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(f"w_v7={M.W_V7},config_hash={M.CONFIG_HASH},fmt={FMT}\n")
        for e, sym, v in rows:
            if sym == "__GRID__":
                fh.write(f"{e},__GRID__,0\n")
            else:
                fh.write(f"{e},{sym},{v:.{DECIMALS}f}\n")


def reparse(path: Path, index: pd.DatetimeIndex, model_cols) -> pd.DataFrame:
    """Re-parse EXACTLY as the EA will (single header, epoch,symbol,frac rows,
    __GRID__ sentinels) and rebuild the matrix on the model's (index, cols) in
    MODEL symbol names (invert the broker map) for a like-for-like compare."""
    inv = {v: k for k, v in SYMMAP.items()}
    row_of = {int(e): i for i, e in enumerate(_epochs(index))}
    col_of = {c: j for j, c in enumerate(model_cols)}
    R = np.zeros((len(index), len(model_cols)))
    last_ts = -1
    with open(path) as fh:
        hdr = fh.readline().strip()
        kv = dict(t.split("=", 1) for t in hdr.split(","))
        assert kv["config_hash"] == M.CONFIG_HASH and kv["fmt"] == str(FMT) and float(kv["w_v7"]) == M.W_V7, hdr
        for line in fh:
            f = line.rstrip("\n").split(",")
            e = int(f[0])
            assert e >= last_ts, "epochs not ascending"
            last_ts = e
            if f[1] == "__GRID__":
                continue
            msym = inv.get(f[1], f[1])
            R[row_of[e], col_of[msym]] += float(f[2])
    return pd.DataFrame(R, index=index, columns=model_cols)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-engine", action="store_true")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()

    # config gate
    import subprocess
    hc = subprocess.run([sys.executable, str(REPO / "strategy_fma3.py")], capture_output=True, text=True).stdout
    assert M.CONFIG_HASH in hc, f"config hash drift: {hc.strip()}"

    fed = M.static_fed(M.W_V7)
    print(f"static_fed(0.70): {fed.shape[0]} hours x {fed.shape[1]} symbols")
    rows = build_rows(fed)
    n_data = sum(1 for r in rows if r[1] != "__GRID__")
    n_sent = len(rows) - n_data
    write_csv(OUT, rows)
    sha = _sha(OUT)

    # --- fast self-check: re-parse reproduces static_fed to < 1e-12 ---
    R = reparse(OUT, fed.index, list(fed.columns))
    max_abs = float((R - fed).abs().to_numpy().max())
    ok = max_abs < 1e-12
    print(f"\n=== fed_frac v3 export ===")
    print(f"file          : {OUT}")
    print(f"size          : {OUT.stat().st_size:,} bytes   sha256 {sha}")
    print(f"rows          : {len(rows):,}  (data {n_data:,} + sentinels {n_sent:,})")
    print(f"reparse check : max|reparsed - static_fed| = {max_abs:.2e}  ({'PASS' if ok else 'FAIL'} < 1e-12)")

    # --- optional full engine reproduction on the PARSED stream ---
    if a.verify_engine:
        import record_engine as RE, record_engine_ext as REX
        # rebuild in broker cols is irrelevant to the engine (it needs the model matrix);
        # use R (model-named) so the specs/eurq resolve — identical values, model names.
        ic = RE.run_record(R * 1.6, label="v3_export_IC", verbose=False)
        ft = REX.run_record_ext(R * 0.7, initial=100_000.0, daily_stop_x=3.0,
                                label="v3_export_FTMO", verbose=False, run_bootstrap=False)
        ic_ok = abs(ic["final_equity"] - M.IC_TARGET["final_equity"]) < 1.0
        ft_ok = abs(ft["final_equity"] - M.FTMO_TARGET["final_equity"]) < 1.0
        print(f"engine IC     : EUR {ic['final_equity']:,.2f}  (target 3,872,872)  {'PASS' if ic_ok else 'FAIL'}")
        print(f"engine FTMO   : EUR {ft['final_equity']:,.2f}  (target 1,332,404)  {'PASS' if ft_ok else 'FAIL'}")
        ok = ok and ic_ok and ft_ok

    if a.install and ok:
        if COMMON.is_dir():
            (COMMON / OUT.name).write_bytes(OUT.read_bytes())
            print(f"installed -> {COMMON / OUT.name}")
        else:
            print(f"[WARN] Common\\Files not found: {COMMON}")

    print(f"OVERALL       : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
