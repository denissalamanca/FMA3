"""export_bh_quarter.py — per-quarter b_h engine exports for the MT5 replay.

Chained-quarterly validation design (Track A, SatEquityNative): instead of one
monster 6-year CSV, each calendar quarter gets a self-contained bundle in the
terminal's Common Files directory; the in-terminal script TestSatEquity.mq5
replays one quarter at a time, warm-started from the previous quarter's
end-state JSON.

Per exported quarter <Q> (e.g. 2020Q1) this writes:

  FMA3_bh_inputs_<Q>.csv          per-bar stepper inputs (289 columns, below)
  FMA3_bh_golden_<Q>.csv          golden eq/eq_w slice from curve.parquet
                                  (ts,equity,worst; %.17g)
  FMA3_bh_state_in_<Q>.json       bh_stepper state BEFORE the quarter
                                  (fresh 10k state for 2020Q1)
  FMA3_bh_state_expected_<Q>.json bh_stepper state AFTER the quarter

Inputs are built by bh_stepper.iter_chunks — i.e. by account_engine_1m's OWN
data-prep code paths (read-only import from FMA2), nothing re-derived here.
State chaining always starts at 2020Q1 regardless of which quarters are
exported, so the state JSONs are the true chained states (the scalar stepper
is re-run from 2020Q1 up to the last requested quarter and asserted BITWISE
against the golden curve on the way).

CSV FORMAT — FMA3_bh_inputs_<Q>.csv, 289 columns
-------------------------------------------------
  col 0        ts                 epoch seconds of the union-grid minute
  col 1        has                31-char '0'/'1' bitmask, book-symbol order
  cols 2-32    tgt_<SYM>          hourly-lagged book target (%.17g)
  cols 33-218  bo_/ao_/bc_/ac_/bl_/ah_<SYM>
                                  bid_o ask_o bid_c ask_c bid_l ask_h, 31 each
  cols 219-226 eurq_<CROSS>       EUR value of 1 unit of quote ccy, 8 crosses
                                  (EURCAD EURCHF EURGBP EURJPY EURNOK EURNZD
                                   EURSEK EURUSD), %.17g
  cols 227-288 swl_/sws_<SYM>     swap accrual factors (%.17g)

SPARSITY RULES (both readers — TestSatEquity.mq5 and the statement-mirror
sat_equity_harness_sim.py — implement exactly these):
  * tgt / eurq: empty field = carry previous row's value (row 0 always
    explicit). Emitted only when the float64 CHANGES vs the previous row.
  * prices: emitted iff has-bit == 1 (row 0 always explicit for all 31);
    empty = carry. The exporter ASSERTS the carry property (stale rows are
    bit-identical to the previous row — _densify ffill guarantees it).
  * swaps: empty = 0.0; emitted iff the value is nonzero (rollover minutes).

FLOAT DISCIPLINE
  * Prices are float32-quantized in the record feed (BH_ENGINE_SPEC.md §3
    note). They are emitted %.9g and the exporter VERIFIES the double-rounding
    round-trip used by the readers:  parse-as-float64 -> cast float32 ->
    upcast float64 == original.  Readers MUST apply the float32 cast
    ((float) in MQL5, np.float32 in python).
  * tgt / eurq / swaps are true float64: emitted %.17g, verified exact.
  * State JSONs are python json.dumps of bh_stepper.get_state() — repr floats,
    exact round-trip.

Usage (cwd anywhere; FMA2 paths are injected by bh_stepper):
  python3 export_bh_quarter.py 2020Q1 2020Q2 [--outdir DIR]
Default outdir = the wine-prefix terminal Common Files directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import bh_stepper as BH  # noqa: E402  (injects FMA2 sys.path)

COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")  # wine user is 'crossover' — verified where the terminal reads (RECON-8b run)

CROSSES = ["EURCAD", "EURCHF", "EURGBP", "EURJPY",
           "EURNOK", "EURNZD", "EURSEK", "EURUSD"]
QUOTE2CROSS = {"CAD": "EURCAD", "CHF": "EURCHF", "GBP": "EURGBP",
               "JPY": "EURJPY", "NOK": "EURNOK", "NZD": "EURNZD",
               "SEK": "EURSEK", "USD": "EURUSD"}

# BH_ENGINE_SPEC.md §2 table (provenance: FMA2 core.S.INSTRUMENTS, verified
# 2026-07-14). SatEquityNative.mqh hardcodes the same values; this dict guards
# against silent drift of the live config.
SPEC_CONSTANTS = {
    #  symbol   (quote, contract, comm, lev, lot_step, min_lot)
    "AUDCAD": ("CAD", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "AUDJPY": ("JPY", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "AUDNZD": ("NZD", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "BTCUSD": ("USD", 1.0, 0.0, 2.0, 0.01, 0.01),
    "CADCHF": ("CHF", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "CADJPY": ("JPY", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "DAX":    ("EUR", 1.0, 0.0, 20.0, 0.1, 0.1),
    "ETHUSD": ("USD", 1.0, 0.0, 2.0, 0.01, 0.01),
    "EURCAD": ("CAD", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "EURCHF": ("CHF", 100000.0, 3.25, 30.0, 0.01, 0.01),
    "EURGBP": ("GBP", 100000.0, 3.25, 30.0, 0.01, 0.01),
    "EURNOK": ("NOK", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "EURNZD": ("NZD", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "EURSEK": ("SEK", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "EURUSD": ("USD", 100000.0, 3.25, 30.0, 0.01, 0.01),
    "GBPJPY": ("JPY", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "JP225":  ("JPY", 1.0, 0.0, 20.0, 0.1, 0.1),
    "NZDCAD": ("CAD", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "NZDJPY": ("JPY", 100000.0, 3.25, 20.0, 0.01, 0.01),
    "SOLUSD": ("USD", 1.0, 0.0, 2.0, 0.01, 0.01),
    "UK100":  ("GBP", 1.0, 0.0, 20.0, 0.1, 0.1),
    "US30":   ("USD", 1.0, 0.0, 20.0, 0.1, 0.1),
    "USA500": ("USD", 1.0, 0.0, 20.0, 0.1, 0.1),
    "USDCHF": ("CHF", 100000.0, 3.25, 30.0, 0.01, 0.01),
    "USDJPY": ("JPY", 100000.0, 3.25, 30.0, 0.01, 0.01),
    "USTEC":  ("USD", 1.0, 0.0, 20.0, 0.1, 0.1),
    "XAGUSD": ("USD", 5000.0, 3.25, 10.0, 0.01, 0.01),
    "XAUUSD": ("USD", 100.0, 3.25, 20.0, 0.01, 0.01),
    "XBRUSD": ("USD", 1000.0, 0.0, 10.0, 0.01, 0.01),
    "XNGUSD": ("USD", 10000.0, 0.0, 10.0, 0.01, 0.01),
    "XTIUSD": ("USD", 1000.0, 0.0, 10.0, 0.01, 0.01),
}

PRICE_FIELDS = [("bo", "bid_o"), ("ao", "ask_o"), ("bc", "bid_c"),
                ("ac", "ask_c"), ("bl", "bid_l"), ("ah", "ask_h")]


def verify_constants(symbols) -> None:
    import core
    assert float(core.S.ACCOUNT["stop_out_level"]) == 0.5, \
        f"poisoned stop_out_level {core.S.ACCOUNT['stop_out_level']!r}"
    for s in symbols:
        i = core.S.INSTRUMENTS[s]
        got = (i["quote"], float(i["contract_size"]),
               float(i["commission_side"]), float(i["leverage"]),
               float(i["lot_step"]), float(i["min_lot"]))
        assert got == SPEC_CONSTANTS[s], f"{s}: core.S {got} != spec table"


def fmt_f64(a: np.ndarray) -> np.ndarray:
    """%.17g strings, exact float64 round-trip (asserted)."""
    s = np.char.mod("%.17g", a)
    assert np.array_equal(s.astype(np.float64), a), "f64 round-trip failed"
    return s


def fmt_f32(a: np.ndarray) -> np.ndarray:
    """%.9g strings for float32-exact prices; verifies the READER path
    (parse float64 -> cast float32 -> upcast float64) is bitwise."""
    assert np.array_equal(a.astype(np.float32).astype(np.float64), a), \
        "price feed not float32-exact (spec §3 violated)"
    s = np.char.mod("%.9g", a)
    rt = s.astype(np.float64).astype(np.float32).astype(np.float64)
    assert np.array_equal(rt, a), "f32 double-rounding round-trip failed"
    return s


def changed_mask(a: np.ndarray) -> np.ndarray:
    """True where the value must be emitted (row 0, or != previous row)."""
    m = np.ones(a.shape, dtype=bool)
    m[1:] = a[1:] != a[:-1]
    return m


def sparse_col(strs: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = strs.astype(object)
    out[~mask] = ""
    return out


def export_quarter(outdir: Path, q: str, ch: dict, state_in: dict,
                   state_out: dict, gslice: pd.DataFrame, symbols) -> dict:
    gidx = ch["gidx"]
    asi8 = gidx.asi8
    assert (asi8 % 1_000_000_000 == 0).all(), "non whole-second stamps"
    ts = asi8 // 1_000_000_000
    assert (np.diff(ts) > 0).all(), "grid not strictly increasing"
    T = len(ts)
    has = ch["has"]

    cols: dict[str, object] = {}
    cols["ts"] = np.char.mod("%d", ts).astype(object)
    cols["has"] = ["".join("1" if b else "0" for b in row) for row in has]

    # tgt: emit on change (row 0 explicit)
    tgt = ch["tgt"]
    assert np.isfinite(tgt).all(), "tgt not NaN-scrubbed"
    for k, s in enumerate(symbols):
        a = np.ascontiguousarray(tgt[:, k])
        cols[f"tgt_{s}"] = sparse_col(fmt_f64(a), changed_mask(a))

    # prices: emit iff has (row 0 explicit); assert the carry property
    for short, field in PRICE_FIELDS:
        f = ch[field]
        bad = (~has[1:]) & (f[1:] != f[:-1])
        assert not bad.any(), f"{field}: stale row differs from previous"
        for k, s in enumerate(symbols):
            m = has[:, k].copy()
            m[0] = True
            cols[f"{short}_{s}"] = sparse_col(
                fmt_f32(np.ascontiguousarray(f[:, k])), m)

    # eurq: one column per EUR cross; assert per-quote consistency + DAX==1
    eurq = ch["eurq"]
    import core
    quote_of = {s: core.S.INSTRUMENTS[s]["quote"] for s in symbols}
    for cross in CROSSES:
        ccy = cross[3:]
        ks = [k for k, s in enumerate(symbols) if quote_of[s] == ccy]
        assert ks, f"no symbol quoted in {ccy}"
        a = np.ascontiguousarray(eurq[:, ks[0]])
        for k in ks[1:]:
            assert np.array_equal(eurq[:, k], a), \
                f"eurq mismatch within quote {ccy}"
        cols[f"eurq_{cross}"] = sparse_col(fmt_f64(a), changed_mask(a))
    for k, s in enumerate(symbols):
        if quote_of[s] == "EUR":
            assert (eurq[:, k] == 1.0).all(), f"{s}: EUR-quote eurq != 1.0"

    # swaps: emit iff nonzero
    for short, field in (("swl", "swap_l"), ("sws", "swap_s")):
        f = ch[field]
        for k, s in enumerate(symbols):
            a = np.ascontiguousarray(f[:, k])
            cols[f"{short}_{s}"] = sparse_col(fmt_f64(a), a != 0.0)

    df = pd.DataFrame(cols)
    assert df.shape == (T, 289), f"bad shape {df.shape}"
    in_path = outdir / f"FMA3_bh_inputs_{q}.csv"
    df.to_csv(in_path, index=False, lineterminator="\n")

    # golden slice
    g_path = outdir / f"FMA3_bh_golden_{q}.csv"
    gd = pd.DataFrame({
        "ts": np.char.mod("%d", ts).astype(object),
        "equity": fmt_f64(gslice["equity"].to_numpy()).astype(object),
        "worst": fmt_f64(gslice["worst"].to_numpy()).astype(object)})
    gd.to_csv(g_path, index=False, lineterminator="\n")

    (outdir / f"FMA3_bh_state_in_{q}.json").write_text(json.dumps(state_in))
    (outdir / f"FMA3_bh_state_expected_{q}.json").write_text(
        json.dumps(state_out))
    return {"quarter": q, "bars": T,
            "inputs_bytes": in_path.stat().st_size,
            "golden_bytes": g_path.stat().st_size,
            "ts_first": int(ts[0]), "ts_last": int(ts[-1]),
            "balance_end": state_out["balance"],
            "n_trades_end": state_out["n_trades"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("quarters", nargs="+",
                    help="quarters to export, e.g. 2020Q1 2020Q2")
    ap.add_argument("--outdir", default=str(COMMON_FILES))
    ap.add_argument("--report", default=None,
                    help="optional JSON report path")
    args = ap.parse_args(argv)

    want = [pd.Period(q, freq="Q") for q in args.quarters]
    last = max(want)
    want_set = {str(p) for p in want}
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    pos = pd.read_parquet(BH.GOLDEN / "book.parquet")
    gold = pd.read_parquet(BH.GOLDEN / "curve.parquet")
    symbols = list(pos.columns)
    assert list(SPEC_CONSTANTS) == symbols, "spec table != book column order"
    verify_constants(symbols)

    st = BH.make_stepper(symbols)
    report = {"exported": [], "chain_bit_equal_golden": True}
    for ch in BH.iter_chunks(pos, "2020Q1", str(last)):
        q = str(ch["qp"])
        state_in = st.get_state()
        eq_c, eq_w = BH.run_chunk_scalar(st, ch)
        gslice = gold.loc[ch["gidx"][0]:ch["gidx"][-1]]
        bits = (len(gslice) == len(eq_c)
                and (gslice.index == ch["gidx"]).all()
                and np.array_equal(np.asarray(eq_c),
                                   gslice["equity"].to_numpy())
                and np.array_equal(np.asarray(eq_w),
                                   gslice["worst"].to_numpy()))
        report["chain_bit_equal_golden"] &= bool(bits)
        print(f"{q}: {len(eq_c):,} bars | chain bit-equal golden {bits} | "
              f"bal EUR {st.balance:,.2f} | trades {st.n_trades:,}",
              flush=True)
        assert bits, f"{q}: chained scalar run is NOT bitwise golden"
        if q in want_set:
            info = export_quarter(outdir, q, ch, state_in, st.get_state(),
                                  gslice, symbols)
            report["exported"].append(info)
            print(f"  exported {q}: inputs {info['inputs_bytes']:,} B, "
                  f"golden {info['golden_bytes']:,} B", flush=True)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
    print("EXPORT DONE:", json.dumps(report["exported"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
