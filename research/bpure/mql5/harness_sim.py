"""Python mirror of the TestV34Native.mq5 driving loop, statement-for-
statement (streaming ffill / xau_ret / day rollover using ffill-as-of-prev-
bar / trend+crisis pending queues / carry kept-column pick / SC deferred
one-bar emission), driven by the EXPORTED CSV, through the Wave-1 validated
Python steppers, assembled by the pointwise EnsembleStepper shell.

Purpose: prove the HARNESS ALGORITHM end-to-end against the frozen golden
book BEFORE the owner runs the terminal (the MQL5 translation of each
stepper is separately validated; this validates the driving loop).

Run from FMA2/research:
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/mql5/harness_sim.py
Writes out/harness_sim_actual.csv (same format as the MQL5 output) for
validate_mql5_book.py; optional argv[1] overrides the output path.

RECORDED RESULT (2026-07-14, this exact loop): DONE bars=49379 rows=49379;
validate_mql5_book.py on the output: max|diff| 4.197e-14 vs golden book,
cells>1e-12: 0, nonzero 132454/1530749 — numerically identical to the
reference driver run (research/bpure/parity/book_parity.json: 4.1966e-14,
same 132454 nonzero cells).  The MQL5 harness ALGORITHM is therefore
exactly equivalent to the validated Wave-1 driver; any in-terminal
divergence beyond the known no-fma ewm residual is an MQL5-side issue.
"""
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
IN_CSV = FMA3 / "research/bpure/mql5/out/FMA3_v34_inputs.csv"
OUT_CSV = (Path(sys.argv[1]) if len(sys.argv) > 1
           else FMA3 / "research/bpure/mql5/out/harness_sim_actual.csv")

for p in (str(FMA2 / "research"), str(FMA2),
          str(FMA3 / "research/bpure/steppers")):
    if p not in sys.path:
        sys.path.insert(0, p)

import core                                                    # noqa: E402
engine_costs = core.engine_costs
import ensemble_stepper as ES                                  # noqa: E402
from mag_xau_stepper import MagXauStepper                      # noqa: E402
from intraday_stepper import IntradayStepper, SYMBOLS as ID_SYMS  # noqa: E402
from meanrev_stepper import MeanrevStepper, SYMBOLS as MR_SYMS  # noqa: E402
from consolidate_p1c_stepper import ConsolidateP1cStepper, CR_SYMBOLS  # noqa: E402
from carry_breakout_stepper import (CarryBreakoutStepper,      # noqa: E402
                                    SYMBOLS as CB_SYMS, parse_policy_rates)
from crisis_stepper import CrisisStepper, INPUT_SYMS as CR_IN, SYMS as CR_OUT  # noqa: E402
from trend_v2_stepper import TrendV2Stepper, SYMS as TV_SYMS, EXEC_HOUR  # noqa: E402

NAN = float("nan")

IN_SYMS = ["AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY",
           "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD",
           "EURSEK", "EURUSD", "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY",
           "NZDUSD", "USDCHF", "USDJPY",
           "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
           "DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
           "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD"]
CB_KEPT = ["AUDJPY", "CADCHF", "CADJPY", "EURCAD", "EURNZD", "EURUSD",
           "GBPJPY", "NZDJPY", "USDCHF", "USDJPY", "DAX", "JP225", "UK100",
           "US30", "USA500", "USTEC", "XAGUSD", "XAUUSD", "XBRUSD",
           "XNGUSD", "XTIUSD"]

T0 = time.time()


def log(m):
    print(f"[{time.time() - T0:7.1f}s] {m}", flush=True)


def main():
    ix = {s: i for i, s in enumerate(IN_SYMS)}
    mr_ix = [ix[s] for s in MR_SYMS]
    cb_ix = [ix[s] for s in CB_SYMS]
    id_ix = [ix[s] for s in ID_SYMS]
    tv_ix = [ix[s] for s in TV_SYMS]
    cr_in_ix = [ix[s] for s in CR_IN]
    cb_keep_ix = [list(CB_SYMS).index(s) for s in CB_KEPT]
    ix_xau, ix_btc, ix_eth, ix_sol = (ix["XAUUSD"], ix["BTCUSD"],
                                      ix["ETHUSD"], ix["SOLUSD"])

    mag = MagXauStepper()
    intr = IntradayStepper()
    mr = MeanrevStepper()
    sc = ConsolidateP1cStepper()
    cb = CarryBreakoutStepper(parse_policy_rates(engine_costs.POLICY_RATES))
    crisis = CrisisStepper()
    tv = TrendV2Stepper()
    sleeve_cols = {"meanrev": list(MR_SYMS), "carry_breakout": CB_KEPT,
                   "seasonal": ["XAUUSD"], "intraday": list(ID_SYMS),
                   "crisis": list(CR_OUT), "trend_v2": list(TV_SYMS),
                   "crypto_smart": list(CR_SYMBOLS), "mag": ["XAUUSD"]}
    shell = ES.EnsembleStepper(sleeve_cols)
    book_syms = list(shell.symbols)
    assert len(book_syms) == 31

    ffill = [NAN] * 37
    has_day, cur_day = False, 0
    tvq = []            # (eff_sec, [5])
    crq = []            # (eff_sec, [4])
    trend_cur = [0.0] * 5
    crisis_cur = [NAN] * 4
    have_prev, prev_ts, prev_rows = False, 0, None
    bars = rows = 0

    out_f = open(OUT_CSV, "w", newline="\n")
    out_f.write("timestamp," + ",".join(book_syms) + "\n")

    def stage_and_write(ts_sec, saved, emit_row):
        nonlocal rows
        srows = dict(saved)
        srows["seasonal"] = {"XAUUSD": emit_row["XAUUSD"]}
        srows["crypto_smart"] = {s: emit_row[s] for s in CR_SYMBOLS}
        net = shell.step(ts_sec * 10 ** 9, srows)
        out_f.write(str(ts_sec) + ","
                    + ",".join("%.17g" % net[s] for s in book_syms) + "\n")
        rows += 1

    rd = csv.reader(open(IN_CSV))
    header = next(rd)
    assert header == ["timestamp"] + IN_SYMS

    for line in rd:
        ts = int(line[0])
        ts_ns = ts * 10 ** 9
        raw = [NAN if c == "" else float(c) for c in line[1:]]

        # --- daily rollover (ffill still as-of the previous bar) --------
        day = ts // 86400
        if not has_day:
            has_day, cur_day = True, day
        elif day != cur_day:
            tvcl = np.array([ffill[j] for j in tv_ix])
            held = list(tv.step(tvcl))
            tvq.append(((cur_day + 1) * 86400 + EXEC_HOUR * 3600, held))
            if (cur_day + 3) % 7 < 5:
                crcl = [ffill[j] for j in cr_in_ix]
                res = crisis.step(cur_day * 86400 * 10 ** 9, crcl)
                crq.append((res["effective_ns"] // 10 ** 9,
                            [res["w"][s] for s in CR_OUT]))
            cur_day = day

        # --- xau ret (prev ffill), then streaming ffill ------------------
        prev_x = ffill[ix_xau]
        for j in range(37):
            if raw[j] == raw[j]:
                ffill[j] = raw[j]
        xret = 0.0
        if prev_x == prev_x:
            r = ffill[ix_xau] / prev_x - 1.0
            xret = -0.30 if r < -0.30 else (0.30 if r > 0.30 else r)

        # --- activate pending daily targets -------------------------------
        while tvq and tvq[0][0] <= ts:
            trend_cur = list(tvq.pop(0)[1])
        while crq and crq[0][0] <= ts:
            w = crq.pop(0)[1]
            for j in range(4):
                if w[j] == w[j]:
                    crisis_cur[j] = w[j]

        # --- current-bar rows for the 7 non-deferred sleeves --------------
        cur = {}
        cur["mag"] = mag.step(ts_ns, {"XAUUSD": raw[ix_xau]})
        cur["intraday"] = intr.step(ts_ns,
                                    {s: raw[id_ix[k]]
                                     for k, s in enumerate(ID_SYMS)})
        cur["meanrev"] = mr.step(
            datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None),
            {s: raw[mr_ix[k]] for k, s in enumerate(MR_SYMS)})
        cb32 = cb.step(ts // 86400, [raw[j] for j in cb_ix])
        cur["carry_breakout"] = {s: cb32[cb_keep_ix[k]]
                                 for k, s in enumerate(CB_KEPT)}
        cur["trend_v2"] = {s: trend_cur[k] for k, s in enumerate(TV_SYMS)}
        cur["crisis"] = {s: (crisis_cur[k] if crisis_cur[k] == crisis_cur[k]
                             else 0.0) for k, s in enumerate(CR_OUT)}

        # --- seasonal/crypto deferred emission -----------------------------
        o = sc.step(ts_ns, xret, ffill[ix_btc], ffill[ix_eth], ffill[ix_sol])
        if o is not None:
            emit_t, emit_row = o
            assert have_prev and emit_t == prev_ts * 10 ** 9, \
                f"emission misaligned at bar {bars}"
            stage_and_write(prev_ts, prev_rows, emit_row)
        else:
            assert bars == 0, f"expected emission at bar {bars}"

        prev_rows = cur
        prev_ts = ts
        have_prev = True
        bars += 1
        if bars % 5000 == 0:
            log(f"bar {bars}, rows {rows}")

    emit_t, emit_row = sc.finalize()
    assert emit_t == prev_ts * 10 ** 9, "FINAL emission misaligned"
    stage_and_write(prev_ts, prev_rows, emit_row)
    out_f.close()
    log(f"DONE bars={bars} rows={rows} -> {OUT_CSV}")
    assert bars == rows


if __name__ == "__main__":
    main()
