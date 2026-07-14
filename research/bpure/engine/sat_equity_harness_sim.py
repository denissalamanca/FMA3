"""sat_equity_harness_sim.py — python statement-mirror of TestSatEquity.mq5.

MIRROR VALIDATION (Track A step 3, no terminal needed): this file re-implements
the DRIVING LOOP of mt5/ea/scripts/TestSatEquity.mq5 statement for statement —
same CSV columns, same sparsity/carry rules, same (float32) price cast, same
per-symbol eurq mapping — and steps the bitwise-proven BHAccountStepper
(bh_stepper.py; CSatEquityNative.mqh is a 1:1 transcription of its step()).
Running the exported quarter bundles through this mirror and diffing against
the golden slices proves the HARNESS + ARITHMETIC pipeline end to end; the
in-terminal run then proves only the MQL5 language layer.

Keep in lockstep with TestSatEquity.mq5:
  * input : FMA3_bh_inputs_<Q>.csv   (289 cols; header asserted)
  *         FMA3_bh_golden_<Q>.csv   (ts,equity,worst golden slice)
  *         state-in JSON            (chained warm start)
  * output: mirror actual CSV + end-state JSON (same formats), plus a
            machine-readable parity report.

Chaining: quarters are replayed in the order given; each quarter warm-starts
from the previous quarter's produced end state (the first from
FMA3_bh_state_in_<Q>.json if present, else fresh 10k), and the produced start
state is cross-checked against the exporter's FMA3_bh_state_in_<Q>.json.

Usage:
  python3 sat_equity_harness_sim.py 2020Q1 2020Q2 \
      [--datadir COMMON_FILES] [--outdir DIR] [--report out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from bh_stepper import BHAccountStepper           # noqa: E402
from export_bh_quarter import (COMMON_FILES, CROSSES, QUOTE2CROSS,  # noqa: E402
                               SPEC_CONSTANTS, PRICE_FIELDS)

NSYM = 31
SYMBOLS = list(SPEC_CONSTANTS)

# symbol k -> index into CROSSES for its quote ccy, -1 = EUR quote
# (mirror of TSE_CROSS_IX in TestSatEquity.mq5)
CROSS_IX = [(-1 if SPEC_CONSTANTS[s][0] == "EUR"
             else CROSSES.index(QUOTE2CROSS[SPEC_CONSTANTS[s][0]]))
            for s in SYMBOLS]

PX_SHORT = [short for short, _ in PRICE_FIELDS]   # bo ao bc ac bl ah


def expected_header() -> str:
    """Mirror of TSEExpectedHeader()."""
    h = "ts,has"
    h += "".join(f",tgt_{s}" for s in SYMBOLS)
    for short in PX_SHORT:
        h += "".join(f",{short}_{s}" for s in SYMBOLS)
    h += "".join(f",eurq_{c}" for c in CROSSES)
    h += "".join(f",swl_{s}" for s in SYMBOLS)
    h += "".join(f",sws_{s}" for s in SYMBOLS)
    return h


def make_engine() -> BHAccountStepper:
    """BHAccountStepper with the SAME hardcoded constants as
    SatEquityNative.mqh (spec §2 table, re-asserted vs core.S at export)."""
    return BHAccountStepper(
        SYMBOLS,
        [SPEC_CONSTANTS[s][1] for s in SYMBOLS],
        [SPEC_CONSTANTS[s][2] for s in SYMBOLS],
        [SPEC_CONSTANTS[s][3] for s in SYMBOLS],
        [SPEC_CONSTANTS[s][4] for s in SYMBOLS],
        [SPEC_CONSTANTS[s][5] for s in SYMBOLS])


def f32(s: str) -> float:
    """Mirror of MQL5 `(float)StringToDouble(s)` (double-rounding path)."""
    return float(np.float32(float(s)))


def run_quarter(q: str, eng: BHAccountStepper, datadir: Path,
                outdir: Path) -> dict:
    in_path = datadir / f"FMA3_bh_inputs_{q}.csv"
    gold_path = datadir / f"FMA3_bh_golden_{q}.csv"
    out_path = outdir / f"FMA3_bh_mirror_actual_{q}.csv"
    state_path = outdir / f"FMA3_bh_mirror_state_out_{q}.json"

    # carried inputs (row 0 fully explicit) — mirror of the .mq5 locals
    tgt = [0.0] * NSYM
    px = [[0.0] * NSYM for _ in range(6)]         # bo ao bc ac bl ah
    eurq_cross = [1.0] * len(CROSSES)
    swl = [0.0] * NSYM
    sws = [0.0] * NSYM

    bars = 0
    eq_exact = eqw_exact = 0
    max_d_eq = max_d_eqw = 0.0
    gold_ts_ok = True
    gold_rows = 0

    fin = in_path.open("r")
    header = fin.readline().rstrip("\r\n")
    assert header == expected_header(), f"{q}: input header mismatch"
    gin = gold_path.open("r")
    ghead = gin.readline().rstrip("\r\n")
    assert ghead == "ts,equity,worst", f"{q}: bad golden header"
    fout = out_path.open("w")
    fout.write("ts,equity,worst\n")

    for line in fin:
        line = line.rstrip("\r\n")
        if not line:
            continue
        parts = line.split(",")
        assert len(parts) == 289, f"{q}: bad column count {len(parts)}"
        ts = int(parts[0])
        hs = parts[1]
        assert len(hs) == NSYM, f"{q}: bad has bitmask"
        has = [c == "1" for c in hs]
        for k in range(NSYM):                     # tgt: empty = carry
            s = parts[2 + k]
            if s:
                tgt[k] = float(s)
        for f in range(6):                        # prices: empty = carry
            base = 33 + f * NSYM
            row = px[f]
            for k in range(NSYM):
                s = parts[base + k]
                if s:
                    row[k] = f32(s)               # float32-quantized feed
        for c in range(len(CROSSES)):             # eurq: empty = carry
            s = parts[219 + c]
            if s:
                eurq_cross[c] = float(s)
        for k in range(NSYM):                     # swaps: empty = 0.0
            s = parts[227 + k]
            swl[k] = float(s) if s else 0.0
            s = parts[258 + k]
            sws[k] = float(s) if s else 0.0
        eurq_sym = [1.0 if CROSS_IX[k] < 0 else eurq_cross[CROSS_IX[k]]
                    for k in range(NSYM)]

        eq_c, eq_w = eng.step(tgt, has, px[0], px[1], px[2], px[3],
                              px[4], px[5], eurq_sym, swl, sws)
        fout.write(f"{ts},{eq_c:.17g},{eq_w:.17g}\n")

        gp = gin.readline().rstrip("\r\n").split(",")
        assert len(gp) == 3, f"{q}: golden row {bars} malformed"
        gold_rows += 1
        if int(gp[0]) != ts:
            gold_ts_ok = False
        ge, gw = float(gp[1]), float(gp[2])
        if eq_c == ge:
            eq_exact += 1
        else:
            max_d_eq = max(max_d_eq, abs(eq_c - ge))
        if eq_w == gw:
            eqw_exact += 1
        else:
            max_d_eqw = max(max_d_eqw, abs(eq_w - gw))
        bars += 1

    assert gin.readline() == "", f"{q}: golden file has extra rows"
    fin.close()
    gin.close()
    fout.close()

    state = eng.get_state()
    state_path.write_text(json.dumps(state))

    # end-state vs the exporter's expected chained state — bitwise
    exp = json.loads((datadir / f"FMA3_bh_state_expected_{q}.json")
                     .read_text())
    state_bits = (state["balance"] == exp["balance"]
                  and state["lots"] == exp["lots"]
                  and state["entry"] == exp["entry"]
                  and state["n_trades"] == exp["n_trades"]
                  and state["symbols"] == exp["symbols"])

    res = {"quarter": q, "bars": bars, "golden_rows": gold_rows,
           "gold_ts_aligned": gold_ts_ok,
           "eq_exact": eq_exact, "eqw_exact": eqw_exact,
           "eq_bitwise": eq_exact == bars, "eqw_bitwise": eqw_exact == bars,
           "max_abs_diff_eq": max_d_eq, "max_abs_diff_eqw": max_d_eqw,
           "within_1e12": max(max_d_eq, max_d_eqw) <= 1e-12,
           "end_state_bitwise_vs_expected": state_bits,
           "final_balance": state["balance"],
           "n_trades": state["n_trades"]}
    print(f"{q}: bars={bars} eq_exact={eq_exact} eqw_exact={eqw_exact} "
          f"max|d_eq|={max_d_eq:.3g} max|d_eqw|={max_d_eqw:.3g} "
          f"state_bitwise={state_bits}", flush=True)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("quarters", nargs="+", help="chained order, e.g. "
                    "2020Q1 2020Q2")
    ap.add_argument("--datadir", default=str(COMMON_FILES))
    ap.add_argument("--outdir", default=None,
                    help="mirror outputs dir (default = datadir)")
    ap.add_argument("--report", default=None)
    args = ap.parse_args(argv)
    datadir = Path(args.datadir)
    outdir = Path(args.outdir) if args.outdir else datadir
    outdir.mkdir(parents=True, exist_ok=True)

    eng = make_engine()
    # warm start of the FIRST quarter from the exporter's state-in
    first_in = datadir / f"FMA3_bh_state_in_{args.quarters[0]}.json"
    if first_in.exists():
        eng.set_state(json.loads(first_in.read_text()))

    report = {"quarters": [], "all_bitwise": True, "all_within_1e12": True,
              "chain_state_in_bitwise": True}
    for q in args.quarters:
        # cross-check the chained start state vs the exporter's state-in
        sin = datadir / f"FMA3_bh_state_in_{q}.json"
        if sin.exists():
            exp_in = json.loads(sin.read_text())
            cur = eng.get_state()
            ok_in = (cur["balance"] == exp_in["balance"]
                     and cur["lots"] == exp_in["lots"]
                     and cur["entry"] == exp_in["entry"]
                     and cur["n_trades"] == exp_in["n_trades"])
            report["chain_state_in_bitwise"] &= ok_in
            if not ok_in:
                print(f"{q}: WARNING chained start state != exporter "
                      f"state-in", flush=True)
        res = run_quarter(q, eng, datadir, outdir)
        report["quarters"].append(res)
        report["all_bitwise"] &= (res["eq_bitwise"] and res["eqw_bitwise"]
                                  and res["end_state_bitwise_vs_expected"]
                                  and res["gold_ts_aligned"])
        report["all_within_1e12"] &= res["within_1e12"]
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
    print("MIRROR RESULT: all_bitwise =", report["all_bitwise"],
          "| all_within_1e12 =", report["all_within_1e12"],
          "| chain_state_in_bitwise =", report["chain_state_in_bitwise"])
    return 0 if report["all_bitwise"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
