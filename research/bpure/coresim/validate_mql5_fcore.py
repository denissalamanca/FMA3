"""validate_mql5_fcore.py — the judge for the in-terminal f_core run, plus a
terminal-free mechanical simulation of the MQL5 algorithm.

MODE 1 (default) — judge FMA3_fcore_actual.csv (written by
mt5/ea/scripts/CheckFCore.mq5: headerless rows `hour_epoch,f0..f7`, doubles
%.17g, NET columns alphabetical AUDUSD,BTCUSD,ETHUSD,EURGBP,NZDUSD,USDJPY,
USTEC,XAUUSD) against the frozen research/outputs/v7_book_frac_1h.parquet
[legacy name].  Gates: index (stamps equal, same count/order) and bit
(np.array_equal per column after the %.17g round-trip). NO NSF5 imports.
Writes fcore_mql5_parity.json.

MODE 2 (--sim) — runs the EXACT MECHANICS CheckFCore/CoreSim.mqh implement
(per-leg bar cursor over each segment's captured bars, cross-segment carry
of the last pos/mid_c/eurq triple, per-union-bar f = ((net_pos*contract)*
mid)*eurq / book_eqc, hourly emission by LAST-bar-in-hour overwrite) in
python on top of fcore_reference's captured segment replay, and diffs the
result against the frozen parquet full-grid.  This isolates the ALGORITHM
before the terminal isolates the MQL5 language layer (the CoreSim RECON-8d
discipline).  Needs the NSF5 feed (run from FMA2/research). Writes
fcore_mqhsim.json.

Usage:
  python3 validate_mql5_fcore.py           # judge the terminal CSV
  ... --dir DIR                            # CSV dir (default: wine Common)
  cd FMA2/research && python3 .../validate_mql5_fcore.py --sim
Exit 0 iff the run mode passed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
FMA3 = _HERE.parents[3]
_spec = importlib.util.spec_from_file_location("fma3_paths",
                                               FMA3 / "config" / "paths.py")
paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paths)

FRAC_PARQUET = paths.OUTPUTS / "v7_book_frac_1h.parquet"
COMMON_FILES = Path.home() / (
    "Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/"
    "users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files")
NET_COLS = ["AUDUSD", "BTCUSD", "ETHUSD", "EURGBP",
            "NZDUSD", "USDJPY", "USTEC", "XAUUSD"]
ACTUAL_CSV = "FMA3_fcore_actual.csv"


def judge(csv_dir: Path) -> int:
    frac = pd.read_parquet(FRAC_PARQUET)
    p = csv_dir / ACTUAL_CSV
    if not p.exists():
        print(f"SKIP: {p} not found — run CheckFCore.mq5 in the terminal "
              f"first (inputs: export_coresim_inputs.py --segments 0..31)")
        return 1
    act = pd.read_csv(p, header=None, names=["epoch"] + NET_COLS,
                      float_precision="round_trip")
    exp_epoch = (frac.index.view("int64") // 10**9)
    idx_ok = bool(len(act) == len(frac)
                  and np.array_equal(act["epoch"].to_numpy(), exp_epoch))
    col_bit = {}
    col_diff = {}
    if idx_ok:
        for c in NET_COLS:
            a = act[c].to_numpy()
            e = frac[c].to_numpy()
            col_bit[c] = bool(np.array_equal(a, e))
            col_diff[c] = float(np.abs(a - e).max())
            if not col_bit[c]:
                k = int(np.argmax(a != e))
                print(f"  {c}: FIRST MISMATCH row {k} "
                      f"({frac.index[k]}): actual={a[k]!r} expected={e[k]!r}")
    ok = idx_ok and all(col_bit.values())
    report = dict(generated=pd.Timestamp.now().isoformat(),
                  mode="actual_vs_parquet", file=str(p),
                  parity_target=str(FRAC_PARQUET),
                  rows_actual=int(len(act)), rows_expected=int(len(frac)),
                  index_equal=idx_ok, bit_equal=col_bit,
                  max_abs_diff=col_diff,
                  verdict="PASS" if ok else "FAIL")
    out = _HERE.parent / "fcore_mql5_parity.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0 if ok else 1


def mqh_sim() -> int:
    """Mechanical python twin of CCoreBookSim.ComputeFCore over the full
    frozen segment chain; diffed vs the parquet (measures the ALGORITHM)."""
    t_start = time.time()
    _s = importlib.util.spec_from_file_location(
        "fcore_reference", _HERE.parent / "fcore_reference.py")
    fr = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(fr)
    cr = fr.cr
    from sim import INIT  # noqa: E402

    segs, trig_books = cr.load_segments()
    cr.prime_feed("ic")
    sleeves = cr.book("BTC_REP", "USTEC")
    insts = sorted({inst for legs in sleeves.values() for inst, _ in legs})
    arrays = {inst: cr.leg_arrays(inst) for inst in insts}
    par = pd.read_parquet(cr.PARITY_PARQUET)
    frac_par = pd.read_parquet(FRAC_PARQUET)
    par_idx = par.index.values

    # leg -> net map in book append order (the CheckFCore NET TABLE)
    net_of_inst = {c: i for i, c in enumerate(NET_COLS)}
    n_net = len(NET_COLS)

    carry = {}          # leg_id -> (pos, mid, qe); absent = never traded
    rows_ts: list[int] = []
    rows_f: list[np.ndarray] = []
    for j, (t0, t1) in enumerate(segs):
        if j == 0:
            seed = INIT
        else:
            k = int(np.searchsorted(par_idx, np.datetime64(t0), side="left")) - 1
            seed = float(par["eqc"].iloc[k])
            assert seed == trig_books[j - 1], f"seed chain mismatch seg {j}"
        union, eqc, legs_cap, rep = fr.run_segment_pos(
            sleeves, arrays, t0, t1, seed, drift_gate=False)
        uts = union.view("int64") // 10**9
        # per-leg capture arrays for the cursor walk
        legs = []
        for lid, lc in enumerate(legs_cap):
            A = arrays[lc["inst"]]
            i0 = int(np.searchsorted(A["idx"].values,
                                     np.datetime64(t0), side="left"))
            i1 = i0 + len(lc["idx"])
            mid = 0.5 * (A["bid_c"][i0:i1] + A["ask_c"][i0:i1])
            legs.append(dict(key=(lc["sleeve"], lc["inst"]),
                             net=net_of_inst[lc["inst"]],
                             contract=float(A["cfg"]["contract_size"]),
                             ts=lc["idx"].view("int64") // 10**9,
                             pos=lc["pos"], mid=mid,
                             qe=A["eurq"][i0:i1]))
        q = [-1] * len(legs)
        for i in range(len(uts)):
            t = int(uts[i])
            net_pos = np.zeros(n_net)
            net_mid = np.zeros(n_net)
            net_qe = np.zeros(n_net)
            net_ct = np.zeros(n_net)
            net_has = np.zeros(n_net, dtype=bool)
            for l, lg in enumerate(legs):
                nb = len(lg["ts"])
                while q[l] + 1 < nb and lg["ts"][q[l] + 1] <= t:
                    q[l] += 1
                if q[l] >= 0:
                    p_, mc_, qe_ = (lg["pos"][q[l]], lg["mid"][q[l]],
                                    lg["qe"][q[l]])
                elif lg["key"] in carry:
                    p_, mc_, qe_ = carry[lg["key"]]
                else:
                    continue
                s = lg["net"]
                net_pos[s] = net_pos[s] + p_
                if not net_has[s]:
                    net_mid[s], net_qe[s], net_ct[s] = mc_, qe_, lg["contract"]
                    net_has[s] = True
            fr_row = np.zeros(n_net)
            for s in range(n_net):
                if net_has[s]:
                    val = net_pos[s] * net_ct[s] * net_mid[s] * net_qe[s]
                    fr_row[s] = val / eqc[i]
            hour = t - (t % 3600)
            if rows_ts and rows_ts[-1] == hour:
                rows_f[-1] = fr_row
            else:
                rows_ts.append(hour)
                rows_f.append(fr_row)
        for l, lg in enumerate(legs):
            nb = len(lg["ts"])
            if nb > 0:
                carry[lg["key"]] = (lg["pos"][nb - 1], lg["mid"][nb - 1],
                                    lg["qe"][nb - 1])
        print(f"      seg {j:2d} [{t0.date()} .. {t1.date()}) "
              f"rows={len(rows_ts)}", flush=True)

    sim_ts = np.asarray(rows_ts, dtype=np.int64)
    sim_f = np.vstack(rows_f)
    exp_epoch = (frac_par.index.view("int64") // 10**9)
    idx_ok = bool(len(sim_ts) == len(frac_par)
                  and np.array_equal(sim_ts, exp_epoch))
    col_bit, col_diff = {}, {}
    if idx_ok:
        for s, c in enumerate(NET_COLS):
            e = frac_par[c].to_numpy()
            col_bit[c] = bool(np.array_equal(sim_f[:, s], e))
            col_diff[c] = float(np.abs(sim_f[:, s] - e).max())
    ok = idx_ok and all(col_bit.values())
    report = dict(generated=pd.Timestamp.now().isoformat(),
                  mode="mqh_algorithm_sim_vs_parquet",
                  parity_target=str(FRAC_PARQUET),
                  rows_sim=int(len(sim_ts)), rows_expected=int(len(frac_par)),
                  index_equal=idx_ok, bit_equal=col_bit,
                  max_abs_diff=col_diff,
                  verdict="PASS" if ok else "FAIL",
                  runtime_s=round(time.time() - t_start, 1))
    out = _HERE.parent / "fcore_mqhsim.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=str(COMMON_FILES))
    ap.add_argument("--sim", action="store_true",
                    help="terminal-free mechanical sim of the MQL5 algorithm")
    args = ap.parse_args()
    if args.sim:
        return mqh_sim()
    return judge(Path(args.dir))


if __name__ == "__main__":
    sys.exit(main())
