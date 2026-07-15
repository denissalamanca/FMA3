"""validate_mql5_sat.py — the judge for the in-terminal Sat (b_h) replay.

The Sat analog of coresim/validate_mql5_coresim.py. Certifies that the compiled
MQL5 Sat engine (Sat/SatEquityNative.mqh), driven over the RECORD feed by
mt5/ea/scripts/TestSatEquityChain.mq5, reproduces the frozen golden Sat curve
BIT-EXACT — the in-terminal port certification the Sat sleeve was missing
(RECON reconciliation, 2026-07-15: the +4.88% live-run drift is the live-vs-
record price-feed basis, NOT a port bug; this proves the port on the record
feed and leaves that attribution as the only remaining explanation).

Diffs, per quarter Q in 2020Q1..2025Q4:
  actual  FMA3_bh_actual_<Q>.csv   (TestSatEquityChain output: ts,equity,worst %.17g)
  golden  FMA3_bh_golden_<Q>.csv   (export_bh_quarter.py: ts,equity,worst %.17g,
                                    the curve.parquet slice)
both in the terminal Common\Files directory.

GATES (per quarter present):
  * index gate — actual ts == golden ts, same count, same order;
  * bit gate   — equity / worst np.array_equal after the %.17g round-trip
                 (0 ULP; the token parses back to the exact float64, so any
                 mismatch is a real arithmetic fork);
  * on FAIL    — the first divergent row is printed, full-precision both sides.
FULL-RUN GATE (only when ALL 24 quarters present + pass):
  * final equity of 2025Q4 == 449707.7452664526 (bit) — the bh_parity.json
    stage2_full final_eur.

--self-test judges the GOLDEN fixtures against curve.parquet (proves the
export + judge fidelity without any terminal run; must PASS).

NO NSF5/numba imports — needs only pandas/numpy + the CSV fixtures.

Usage:
  python3 validate_mql5_sat.py                 # judge actual files
  python3 validate_mql5_sat.py --self-test     # judge golden vs curve.parquet
  ... --dir DIR         # where the CSVs live (default: wine Common Files)
  ... --quarters 2020Q1 2020Q2   # restrict; default = all 24, missing = SKIP
Exit 0 iff >=1 quarter judged and every judged quarter passed.
Writes sat_mql5_parity.json (or sat_judge_selftest.json with --self-test).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")
# frozen golden curve (from bh_parity.json 'golden'); used only by --self-test
CURVE_PARQUET = _HERE.parents[3] / "model/v3/freeze/FMA3-v34-freeze-1/golden/curve.parquet"

QUARTERS = [f"{y}Q{q}" for y in range(2020, 2026) for q in range(1, 5)]  # 24
FINAL_EQUITY_TARGET = 449707.7452664526  # bh_parity.json stage2_full.final_eur
COLS = ["ts", "equity", "worst"]


def read_csv(p: Path) -> pd.DataFrame:
    # both golden and actual carry the header row "ts,equity,worst"
    return pd.read_csv(p, float_precision="round_trip",
                       dtype={"ts": np.int64, "equity": np.float64,
                              "worst": np.float64})


def first_mismatch(ts, act, gold):
    for col in ("equity", "worst"):
        a = act[col].to_numpy()
        g = gold[col].to_numpy()
        bad = np.flatnonzero(a != g)
        if bad.size:
            i = int(bad[0])
            return dict(column=col, row=i, epoch=int(ts[i]),
                        actual=repr(float(a[i])), golden=repr(float(g[i])),
                        abs_diff=float(abs(a[i] - g[i])))
    return None


def golden_from_parquet(q_ts):
    """--self-test: rebuild the golden (equity,worst) at the fixture's stamps
    from curve.parquet, proving the exported golden CSV is a faithful slice."""
    par = pd.read_parquet(CURVE_PARQUET)
    # curve.parquet columns: equity/close + worst (name-tolerant)
    ecol = "equity" if "equity" in par.columns else (
        "close" if "close" in par.columns else par.columns[0])
    wcol = "worst" if "worst" in par.columns else par.columns[-1]
    idx = par.index.asi8 // 1_000_000_000
    m = pd.Series(np.arange(len(par)), index=idx)
    pos = m.reindex(q_ts)
    if pos.isna().any():
        return None
    pos = pos.to_numpy().astype(np.int64)
    return pd.DataFrame({"ts": q_ts,
                         "equity": par[ecol].to_numpy()[pos],
                         "worst": par[wcol].to_numpy()[pos]})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=str(COMMON_FILES))
    ap.add_argument("--quarters", nargs="*", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    t_all = time.time()
    d = Path(args.dir)
    which = args.quarters if args.quarters else QUARTERS

    results, judged, passed, all_pass = [], 0, set(), True
    final_equity_q4 = None
    for q in which:
        gp = d / f"FMA3_bh_golden_{q}.csv"
        ap_ = d / f"FMA3_bh_actual_{q}.csv"
        if not gp.exists():
            results.append(dict(quarter=q, verdict="SKIP (golden missing)"))
            continue
        gold = read_csv(gp)
        if args.self_test:
            act = golden_from_parquet(gold["ts"].to_numpy())
            if act is None:
                results.append(dict(quarter=q,
                                    verdict="SKIP (parquet stamps missing)"))
                continue
        else:
            if not ap_.exists():
                results.append(dict(quarter=q, verdict="SKIP (actual missing)",
                                    file=str(ap_)))
                continue
            act = read_csv(ap_)

        ts = gold["ts"].to_numpy()
        idx_eq = bool(len(act) == len(gold)
                      and np.array_equal(act["ts"].to_numpy(), ts))
        r = dict(quarter=q, bars_golden=int(len(gold)),
                 bars_actual=int(len(act)), index_equal=idx_eq)
        if idx_eq:
            for col in ("equity", "worst"):
                a = act[col].to_numpy(); g = gold[col].to_numpy()
                r[f"bit_equal_{col}"] = bool(np.array_equal(a, g))
                r[f"max_abs_d{col}"] = float(np.abs(a - g).max())
            ok = r["bit_equal_equity"] and r["bit_equal_worst"]
            if not ok:
                r["first_mismatch"] = first_mismatch(ts, act, gold)
        else:
            ok = False
            r["note"] = "index gate failed — bit gate not evaluated"
        r["verdict"] = "PASS" if ok else "FAIL"
        judged += 1
        all_pass &= ok
        if ok:
            passed.add(q)
        if q == "2025Q4" and idx_eq:
            final_equity_q4 = float(act["equity"].iloc[-1])
        results.append(r)
        print(f"{q}: {r['verdict']}  bars={r['bars_actual']:,} idx={idx_eq} "
              f"eq={r.get('bit_equal_equity')} w={r.get('bit_equal_worst')}"
              + (f"  FIRST DIVERGENCE {r['first_mismatch']}"
                 if r.get("first_mismatch") else ""), flush=True)

    full = dict(evaluated=False)
    if passed == set(QUARTERS):
        hit = (final_equity_q4 == FINAL_EQUITY_TARGET)
        full = dict(evaluated=True, final_equity_actual=final_equity_q4,
                    final_equity_target=FINAL_EQUITY_TARGET, bit_equal=bool(hit))
        all_pass &= hit
        print(f"FULL-RUN GATE: final equity {final_equity_q4!r} "
              f"{'==' if hit else '!='} {FINAL_EQUITY_TARGET!r} -> "
              f"{'PASS' if hit else 'FAIL'}", flush=True)
    else:
        missing = [q for q in QUARTERS if q not in passed]
        full["outstanding_quarters"] = missing
        print(f"FULL-RUN GATE: not evaluated (outstanding: {missing})",
              flush=True)

    verdict = bool(judged > 0 and all_pass)
    report = dict(generated=pd.Timestamp.now().isoformat(),
                  mode=("self_test_golden_vs_parquet" if args.self_test
                        else "actual_vs_golden"),
                  dir=str(d), curve_parquet=str(CURVE_PARQUET),
                  final_equity_target=FINAL_EQUITY_TARGET,
                  quarters_judged=judged, quarters_passed=sorted(passed),
                  results=results, full_run_gate=full,
                  all_judged_pass=bool(all_pass), judge_pass=verdict,
                  runtime_s=round(time.time() - t_all, 1))
    out = Path(args.report) if args.report else (
        _HERE.parent / ("sat_judge_selftest.json" if args.self_test
                        else "sat_mql5_parity.json"))
    out.write_text(json.dumps(report, indent=1))
    print(f"JUDGE {'PASS' if verdict else 'FAIL'}: {judged} quarter(s) judged, "
          f"{len(passed)} passed ({out}, {report['runtime_s']}s)", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
