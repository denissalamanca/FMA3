"""validate_mql5_coresim.py — the judge for the in-terminal CoreSim run.

Diffs the terminal's per-segment output FMA3_coresim_actual_seg<J>.csv
(written by mt5/ea/scripts/TestCoreSim.mq5: headerless rows
`epoch_sec,eqc,eqw,margin`, doubles %.17g) against the parity parquet
research/outputs/v7_book_equity_1m.parquet sliced to the frozen segment
window [t0, t1) from research/outputs/v7_extract_verification.json.

GATES (per segment found):
  * index gate  — the actual epoch stamps == the parquet slice stamps,
                  same count, same order;
  * bit gate    — eqc / eqw / margin np.array_equal after the %.17g
                  round-trip (0 ULP; the %.17g token parses back to the
                  exact float64, so any mismatch is a real arithmetic fork);
  * on FAIL     — the first divergent row is printed with full-precision
                  reprs of both sides.
FULL-RUN GATE (only when ALL 32 segments are present and pass):
  * final eqc of segment 31 == 532229.8433634703 (bit) == parquet last eqc.
Plus a manifest cross-check (t0/t1 epochs vs the verification json) when
FMA3_coresim_segments.csv is present.

NO NSF5 imports — needs only pandas/numpy + the two FMA3 outputs artifacts.

Usage:
  python3 validate_mql5_coresim.py                 # judge actual files
  python3 validate_mql5_coresim.py --self-test     # judge the GOLDEN slices
        # (golden-vs-parquet: proves the judge + export fidelity; must PASS)
  ... --dir DIR        # where the CSVs live (default: wine Common Files)
  ... --segments 0 1   # restrict; default = all 32, missing files SKIP
Exit 0 iff >=1 segment judged and every judged segment passed.
Writes coresim_mql5_parity.json (or coresim_judge_selftest.json with
--self-test) next to this file.
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

PARITY_PARQUET = paths.OUTPUTS / "v7_book_equity_1m.parquet"
VERIFICATION_JSON = paths.OUTPUTS / "v7_extract_verification.json"
COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")

N_SEG = 32
FINAL_EQC_TARGET = 532229.8433634703
COLS = ["ts", "eqc", "eqw", "margin"]


def read_actual(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, header=None, names=COLS,
                       float_precision="round_trip",
                       dtype={"ts": np.int64, "eqc": np.float64,
                              "eqw": np.float64, "margin": np.float64})


def first_mismatch(exp_ts, act, ps):
    """Return a dict describing the first divergent row (index gate passed)."""
    for col in ("eqc", "eqw", "margin"):
        a = act[col].to_numpy()
        g = ps[col].to_numpy()
        bad = np.flatnonzero(a != g)
        if bad.size:
            i = int(bad[0])
            return dict(column=col, row=i, epoch=int(exp_ts[i]),
                        stamp=str(ps.index[i]),
                        actual=repr(float(a[i])), golden=repr(float(g[i])),
                        abs_diff=float(abs(a[i] - g[i])))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=str(COMMON_FILES))
    ap.add_argument("--segments", type=int, nargs="*", default=None)
    ap.add_argument("--self-test", action="store_true",
                    help="judge FMA3_coresim_golden_seg<J>.csv as the actual")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    t_all = time.time()
    d = Path(args.dir)
    rep = json.loads(VERIFICATION_JSON.read_text())
    assert rep["status"] == "reconciled", rep["status"]
    segs = [(pd.Timestamp(s["t0"]), pd.Timestamp(s["t1"]))
            for s in rep["segments"]]
    assert len(segs) == N_SEG
    par = pd.read_parquet(PARITY_PARQUET)
    par_idx = par.index.values
    assert float(par["eqc"].iloc[-1]) == FINAL_EQC_TARGET, \
        "parity parquet does not end at the frozen full-run target"

    stem = ("FMA3_coresim_golden_seg{j}.csv" if args.self_test
            else "FMA3_coresim_actual_seg{j}.csv")
    which = args.segments if args.segments else list(range(N_SEG))

    # optional manifest cross-check
    man = d / "FMA3_coresim_segments.csv"
    manifest_ok = None
    if man.exists():
        mdf = pd.read_csv(man, header=None, names=["j", "t0", "t1", "n"])
        manifest_ok = True
        for _, r in mdf.iterrows():
            t0e = int(pd.Timestamp(segs[int(r.j)][0]).value // 1_000_000_000)
            t1e = int(pd.Timestamp(segs[int(r.j)][1]).value // 1_000_000_000)
            if int(r.t0) != t0e or int(r.t1) != t1e:
                manifest_ok = False
                print(f"MANIFEST MISMATCH row j={int(r.j)}: "
                      f"({int(r.t0)},{int(r.t1)}) != frozen ({t0e},{t1e})")
        print(f"manifest: {len(mdf)} rows, windows match frozen json: "
              f"{manifest_ok}", flush=True)

    results = []
    judged = 0
    all_pass = True
    passed = set()
    final_eqc_seg31 = None
    for j in which:
        p = d / stem.format(j=j)
        if not p.exists():
            results.append(dict(segment=j, verdict="SKIP (file missing)",
                                file=str(p)))
            continue
        t0, t1 = segs[j]
        sel = ((par_idx >= np.datetime64(t0)) & (par_idx < np.datetime64(t1)))
        ps = par[sel]
        exp_ts = ps.index.asi8 // 1_000_000_000
        act = read_actual(p)
        idx_eq = bool(len(act) == len(ps)
                      and np.array_equal(act["ts"].to_numpy(), exp_ts))
        r = dict(segment=j, file=p.name, t0=str(t0), t1=str(t1),
                 bars_expected=int(len(ps)), bars_actual=int(len(act)),
                 index_equal=idx_eq)
        if idx_eq:
            for col in ("eqc", "eqw", "margin"):
                a = act[col].to_numpy()
                g = ps[col].to_numpy()
                r[f"bit_equal_{col}"] = bool(np.array_equal(a, g))
                r[f"max_abs_d{col}"] = float(np.abs(a - g).max())
            ok = (r["bit_equal_eqc"] and r["bit_equal_eqw"]
                  and r["bit_equal_margin"])
            if not ok:
                r["first_mismatch"] = first_mismatch(exp_ts, act, ps)
        else:
            ok = False
            r["note"] = "index gate failed — bit gate not evaluated"
        r["verdict"] = "PASS" if ok else "FAIL"
        judged += 1
        all_pass &= ok
        if ok:
            passed.add(j)
        if j == N_SEG - 1 and idx_eq:
            final_eqc_seg31 = float(act["eqc"].iloc[-1])
        results.append(r)
        print(f"seg {j:2d}: {r['verdict']}  bars={r['bars_actual']:,} "
              f"idx={idx_eq} "
              f"eqc={r.get('bit_equal_eqc')} eqw={r.get('bit_equal_eqw')} "
              f"mg={r.get('bit_equal_margin')}"
              + (f"  FIRST DIVERGENCE {r['first_mismatch']}"
                 if r.get("first_mismatch") else ""), flush=True)

    # full-run gate
    full = dict(evaluated=False)
    if passed == set(range(N_SEG)):
        hit = (final_eqc_seg31 == FINAL_EQC_TARGET)
        full = dict(evaluated=True, final_eqc_actual=final_eqc_seg31,
                    final_eqc_target=FINAL_EQC_TARGET,
                    bit_equal=bool(hit))
        all_pass &= hit
        print(f"FULL-RUN GATE: final eqc {final_eqc_seg31!r} "
              f"{'==' if hit else '!='} target {FINAL_EQC_TARGET!r} -> "
              f"{'PASS' if hit else 'FAIL'}", flush=True)
    else:
        missing = sorted(set(range(N_SEG)) - passed)
        print(f"FULL-RUN GATE: not evaluated (segments not all present+pass; "
              f"outstanding: {missing})", flush=True)
        full["outstanding_segments"] = missing

    verdict = bool(judged > 0 and all_pass)
    report = dict(generated=pd.Timestamp.now().isoformat(),
                  mode=("self_test_golden_vs_parquet" if args.self_test
                        else "actual_vs_parquet"),
                  dir=str(d), parity_target=str(PARITY_PARQUET),
                  verification_source=str(VERIFICATION_JSON),
                  manifest_windows_match=manifest_ok,
                  segments_judged=judged,
                  segments_passed=sorted(passed),
                  results=results, full_run_gate=full,
                  all_judged_pass=bool(all_pass), judge_pass=verdict,
                  runtime_s=round(time.time() - t_all, 1))
    out = Path(args.report) if args.report else (
        _HERE.parent / ("coresim_judge_selftest.json" if args.self_test
                        else "coresim_mql5_parity.json"))
    out.write_text(json.dumps(report, indent=1))
    print(f"JUDGE {'PASS' if verdict else 'FAIL'}: {judged} segment(s) "
          f"judged, {len(passed)} passed ({out}, {report['runtime_s']}s)",
          flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
