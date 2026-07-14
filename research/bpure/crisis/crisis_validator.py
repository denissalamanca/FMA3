#!/usr/bin/env python3
"""INSTRUMENT 2 — CRISIS / MaxDD VALIDATOR (the gate that protects capital).

Takes a book_frac stream (the RECON-4 golden, or a candidate EA-produced replay
stream in the same fmt=3 long CSV), a dial `s`, and runs it through the CAMPAIGN
ENGINE OF RECORD (FMA2 `account_engine_1m.simulate_account_1m`, true 1-minute
co-timed worst mark, via `engine/record_engine.py`).  It then grades the
candidate against the golden on the RATIFIED tolerance band.

================================================================================
WHY THE 1m-OHLC STRATEGY TESTER IS **DISALLOWED** FOR THIS GATE  (do not rewire)
================================================================================
This gate MUST run on the FROZEN SIX-FIELD ENGINE (bid_o/ask_o/bid_c/ask_c/
bid_l/ask_h — a real, per-minute, per-side ask series), and must NEVER be run on
the MT5 Strategy Tester in "1 minute OHLC" mode, for one measurable reason:

  * In 1m-OHLC mode the tester has NO ask series.  It FABRICATES the ask as
    `ask = bid + spread`, with `spread` an INTEGER number of points held
    constant across the synthesized sub-bar path (and, on most 1m-OHLC feeds,
    equal to the symbol's stored/typical spread, not the realized one).
  * The headline number of this gate is `maxdd_worst`: the worst CO-TIMED mark
    of the whole book.  A SHORT leg is marked at `ask_h` — the HIGH of the ask.
    With a fabricated ask, `ask_h == bid_h + const`, so every short's worst mark
    is exactly the bid high plus a constant — the actual COVID ask blow-out
    (spreads on XAUUSD/indices/crypto widened by multiples, and the ask high ran
    far above `bid_h + typical_spread`) is ERASED.
  * Net effect: the tester MIS-MARKS the COVID short worst-mark and reports a
    SHALLOWER crisis drawdown than the account really took.  An instrument that
    under-reports the worst mark on the one window it exists to police is not a
    conservative instrument — it is a broken one.  The tester is fine for
    ORDER-FLOW / execution fidelity (R2); it is not admissible evidence for
    MaxDD / crisis.  This file therefore only ever touches the record engine.

(The dual of this rule: the record engine is NOT admissible for execution
fidelity — it has no broker volume limits/rejects. Each instrument in its lane.)

================================================================================
WHAT IS MEASURED
================================================================================
Band components (RATIFIED band, graded PASS/FAIL each):
    dCAGR         <= +-1.0 pp     (0.010 absolute, CAGR is a fraction)
    dMaxDD_worst  <= +-0.5 pp     (0.005 absolute)
    dBreach       <= +-0.5 pp     (0.005 absolute; house 20d-block worst-mark
                                   stationary bootstrap P(maxDD > 30%),
                                   seed 20260709 / 5000 paths / block 20,
                                   imported from the FMA2 pin script itself)
STRUCTURE (hard gate, graded PASS/FAIL, NEVER silently reconciled):
    the candidate's symbol set and hour grid must be IDENTICAL to the golden's.
    A missing symbol / missing hour is a FAIL that NAMES the symbol / hour.
    (This is the Antigravity failure mode: a judge that compares only the
    column intersection reports PASS on a book it never measured.)
COVID sub-metrics (window 2020-02-15 .. 2020-04-30, reported as DIAGNOSTICS —
the ratified band does not define a tolerance for them, so they are NOT graded):
    covid_trough_worst_dd  worst-mark drawdown attained inside the window
                           (vs the running high-water of the close mark)
    covid_trough_equity    minimum worst-mark equity inside the window
    covid_days_underwater  length of the UNDERWATER EPISODE containing the
                           window's worst-mark trough: from the day the
                           preceding close-mark high-water was set, to the day
                           the close mark regains it (recovery date reported;
                           may fall outside the window; None/censored if the
                           sample ends first).  NOTE: this is deliberately NOT
                           "first day the pre-window peak is re-crossed" — that
                           earlier definition returned a recovery date BEFORE
                           the trough (measured: 2020-02-19 vs a 2020-03-12
                           trough) and was discarded as meaningless.
    covid_days_in_dd       count of days inside the window whose close mark is
                           below the running high-water
    covid_worst_day_mark   worst single-day mark: min over days in the window of
                           (that day's worst-mark minimum / previous day's close
                           mark - 1), with its date

!! HONESTY PIN on the COVID sub-metrics !!
The record engine starts COLD at 2020Q1 (indicator warmup), so the book it holds
INTO the crash is not the book a warm account would have held (memory record:
the cold start skips the EURGBP short).  The absolute COVID depth this
instrument reports is therefore an UNDERSTATEMENT of a warm account's crisis
draw.  That does not impair its job here — it is a COMPARATOR: candidate and
golden are run through the SAME engine, so the deltas it grades are honest.  But
nobody may quote its absolute COVID trough as the crisis truth.  A warm-start
crisis read is separate work.

================================================================================
USAGE
================================================================================
  python3 crisis_validator.py baseline [--dial 1.6 --dial 1.0] [--model-selftest]
      Run the golden through the engine at each dial; cache the metric blocks;
      print the reference rows.  --model-selftest additionally rebuilds the
      golden matrix straight from the model of record (model/v3/reproduce.py
      static_blend(0.70)) and runs it as an INDEPENDENT candidate -> the judge
      must return all-zero deltas (positive self-test through two independent
      load paths, not a tautological compare of one object to itself).

  python3 crisis_validator.py judge --candidate <stream.csv> --dial 1.6
      Grade a candidate stream against the golden.  Exit 0 = PASS, 1 = FAIL.

  python3 crisis_validator.py negctl [--dial 1.6] [--with-stream-defect]
      NEGATIVE CONTROLS.  Injects (a) +1.5pp CAGR, (b) +0.8pp MaxDD_worst,
      (c) +0.7pp breach into a candidate metric block; the validator MUST FAIL
      each and NAME the broken component.  --with-stream-defect additionally
      builds a real defective STREAM (a whole symbol dropped) and drives the
      FULL path (parse -> structure -> record engine -> grade), which must FAIL
      on STRUCTURE (naming the dropped symbol) and on the band.

Run from anywhere; all paths are absolute.  python3 = /usr/local/bin/python3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
OUTDIR = Path(__file__).resolve().parent / "out"
GOLDEN_CSV = FMA3 / "research/outputs/mt5/FMA3_fed_frac_v3.csv"
GOLDEN_SHA = "d00b614b650b649ac9301b1ffd1eae66af4785ce4417bfa91755d367f8ab452e"

# repo(model) <-> broker symbol map, identical to scripts/export_book_frac_v3.py
SYMMAP = {"USA500": "US500", "DAX": "DE40"}
INVMAP = {v: k for k, v in SYMMAP.items()}
SENTINEL = "__GRID__"

# --- RATIFIED tolerance band (absolute, on fractions; 1.0 pp == 0.010) --------
BAND = {"cagr": 0.010, "maxdd_worst": 0.005, "breach_worst": 0.005}
BAND_EPS = 1e-12                      # float slack so |d| == band grades PASS

COVID_START = pd.Timestamp("2020-02-15")
COVID_END = pd.Timestamp("2020-04-30 23:59:59")
COVID_SCHEMA = 2      # v1 (first-recross underwater) was WRONG; see covid_submetrics

INITIAL = 10_000.0                    # engine-of-record default seed (IC preset)


# ----------------------------------------------------------------------------
# engine of record (imported, never copied)
# ----------------------------------------------------------------------------
def _engine():
    """Import the engine of record + the model of record, lazily.

    Path order mirrors scripts/export_book_frac_v3.py exactly (model/v3 then
    engine/); record_engine.py itself bootstraps the FMA2/NSF5 sys.path.  The
    FMA3 repo ROOT is never placed on sys.path (see record_engine docstring).
    """
    for p in (str(FMA3 / "model" / "v3"), str(FMA3 / "engine")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import record_engine as RE          # noqa: E402
    import reproduce as M               # noqa: E402
    return RE, M


# ----------------------------------------------------------------------------
# stream I/O — parse + STRUCTURE (the anti-Antigravity guard)
# ----------------------------------------------------------------------------
def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_stream(path: Path) -> dict:
    """Parse a fmt=3 long stream -> {epochs, rows, symbols, ...}.  No matrix yet.

    Rows: `epoch,broker_symbol,net_frac`; `epoch,__GRID__,0` marks an all-flat
    hour.  A single `config_hash=` header line is tolerated (and recorded).
    Duplicate (epoch, symbol) rows are SUMMED (exporter semantics: `+=`) and
    counted — a duplicate is reported, never hidden.
    """
    path = Path(path)
    rows: list[tuple[int, str, float]] = []
    header = None
    with open(path) as fh:
        first = fh.readline().rstrip("\r\n")
        if "config_hash=" in first:
            header = first
        elif first:
            f = first.split(",")
            rows.append((int(f[0]), f[1], float(f[2])))
        for line in fh:
            line = line.rstrip("\r\n")
            if not line:
                continue
            f = line.split(",")
            if len(f) != 3:
                raise ValueError(f"malformed row in {path.name}: {line[:80]!r}")
            rows.append((int(f[0]), f[1], float(f[2])))

    epochs = np.unique(np.array([r[0] for r in rows], dtype=np.int64))
    seen = Counter((r[0], r[1]) for r in rows)
    dups = [k for k, c in seen.items() if c > 1]
    sym_counts = Counter(r[1] for r in rows if r[1] != SENTINEL)
    return {
        "path": str(path),
        "sha256": sha256(path),
        "header": header,
        "rows": rows,
        "n_rows": len(rows),
        "n_data": sum(1 for r in rows if r[1] != SENTINEL),
        "n_sentinels": sum(1 for r in rows if r[1] == SENTINEL),
        "epochs": epochs,
        "n_hours": int(epochs.size),
        "symbols_broker": sorted(sym_counts),
        "sym_counts": dict(sym_counts),
        "n_dup_keys": len(dups),
        "dup_keys": [f"{e},{s}" for e, s in sorted(dups)[:10]],
    }


def structure_report(cand: dict, gold: dict) -> dict:
    """Compare candidate vs golden STRUCTURE.  Shapes are NEVER intersected.

    A symbol present in one and absent in the other, or an hour present in one
    and absent in the other, is a hard FAIL that names the offender.  (Value
    differences are NOT judged here — they flow through the engine and are
    graded by the band.)
    """
    cs, gs = set(cand["symbols_broker"]), set(gold["symbols_broker"])
    missing = sorted(gs - cs)
    extra = sorted(cs - gs)
    ce, ge = set(cand["epochs"].tolist()), set(gold["epochs"].tolist())
    miss_h, extra_h = sorted(ge - ce), sorted(ce - ge)

    def _ts(e):
        return str(pd.Timestamp(int(e), unit="s"))

    ok = not (missing or extra or miss_h or extra_h or cand["n_dup_keys"])
    return {
        "ok": bool(ok),
        "symbols_candidate": len(cs), "symbols_golden": len(gs),
        "symbols_missing": missing, "symbols_extra": extra,
        "hours_candidate": cand["n_hours"], "hours_golden": gold["n_hours"],
        "hours_missing": len(miss_h), "hours_extra": len(extra_h),
        "hours_missing_first5": [_ts(e) for e in miss_h[:5]],
        "hours_extra_first5": [_ts(e) for e in extra_h[:5]],
        "duplicate_keys": cand["n_dup_keys"], "duplicate_keys_first10": cand["dup_keys"],
        "rows_candidate": cand["n_rows"], "rows_golden": gold["n_rows"],
        "sentinels_candidate": cand["n_sentinels"], "sentinels_golden": gold["n_sentinels"],
    }


def stream_matrix(parsed: dict, grid: np.ndarray, model_cols: list[str]) -> pd.DataFrame:
    """Rebuild the hourly fraction matrix on a FIXED (grid, model_cols) frame.

    The frame is imposed by the GOLDEN (never taken from the candidate) so that a
    candidate missing a symbol yields a ZERO column that the engine actually
    trades (flat) and the metrics move — instead of the symbol silently
    disappearing from the comparison.  Rows off the grid are dropped and counted
    by structure_report (they are already a FAIL there).
    """
    row_of = {int(e): i for i, e in enumerate(grid)}
    col_of = {c: j for j, c in enumerate(model_cols)}
    R = np.zeros((len(grid), len(model_cols)))
    for e, sym, v in parsed["rows"]:
        if sym == SENTINEL:
            continue
        msym = INVMAP.get(sym, sym)
        i, j = row_of.get(int(e)), col_of.get(msym)
        if i is None or j is None:
            continue                    # off-frame: reported by structure_report
        R[i, j] += v
    idx = pd.to_datetime(grid, unit="s")
    return pd.DataFrame(R, index=idx, columns=model_cols)


def golden_frame(gold_parsed: dict) -> tuple[np.ndarray, list[str]]:
    """The canonical (hour grid, model column list) taken from the golden."""
    cols = sorted(INVMAP.get(s, s) for s in gold_parsed["symbols_broker"])
    return gold_parsed["epochs"], cols


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------
def covid_submetrics(eq_c: pd.Series, eq_w: pd.Series) -> dict:
    """COVID-window sub-metrics off the 1m close/worst curves (DIAGNOSTIC).

    `covid_days_underwater` is the length of the underwater EPISODE that
    CONTAINS the window's worst-mark trough: high-water day -> recovery day.
    (An earlier draft counted days until the pre-window peak was first
    re-crossed; on the golden that returned a 2020-02-19 "recovery" for a
    2020-03-12 trough — a metric that answers a question nobody asked.  It was
    replaced, not patched.)
    """
    c = eq_c.to_numpy()
    peak = np.maximum.accumulate(c)                     # global high-water (close mark)
    w = eq_w.to_numpy()
    dd_w = (peak - w) / np.maximum(peak, 1e-9)          # worst-mark DD at every minute
    m = (eq_c.index >= COVID_START) & (eq_c.index <= COVID_END)
    if not m.any():
        raise ValueError("COVID window is empty on this curve index")
    i_tr = int(np.argmax(np.where(m, dd_w, -np.inf)))   # deepest worst mark in window
    trough_ts = eq_c.index[i_tr]

    dc = eq_c.resample("1D").last().dropna()            # daily close mark
    dw = eq_w.resample("1D").min().reindex(dc.index)    # daily worst mark
    rpk = dc.cummax()                                   # running close-mark high-water

    # the underwater episode containing the trough
    tday = dc.index[dc.index.searchsorted(trough_ts.normalize(), side="right") - 1]
    P = float(rpk.loc[tday])                            # high-water in force at the trough
    at_hw = dc.index[(dc.index <= tday) & (dc.to_numpy() >= P)]
    hw_day = at_hw[-1] if len(at_hw) else dc.index[0]   # day that high-water was set
    post = dc[dc.index > tday]
    rec = post[post >= P]
    if len(rec):
        rec_day = rec.index[0]
        underwater = int((rec_day - hw_day).days)
        rec_s, censored = str(rec_day.date()), False
    else:
        underwater = int((dc.index[-1] - hw_day).days)  # never recovered in sample
        rec_s, censored = None, True

    win = (dc.index >= COVID_START) & (dc.index <= COVID_END)
    days_in_dd = int((dc[win] < rpk[win]).sum())
    prev_c = dc.shift(1)
    day_mark = (dw / prev_c - 1.0)[win].dropna()
    wd_i = day_mark.idxmin()
    return {
        "covid_trough_worst_dd": float(dd_w[i_tr]),
        "covid_trough_ts": str(trough_ts),
        "covid_trough_equity": float(np.min(np.where(m, w, np.inf))),
        "covid_highwater_at_trough": P,
        "covid_highwater_day": str(hw_day.date()),
        "covid_days_underwater": underwater,
        "covid_recovery_date": rec_s,
        "covid_recovery_censored": censored,
        "covid_days_in_dd": days_in_dd,
        "covid_worst_day_mark": float(day_mark.min()),
        "covid_worst_day_date": str(wd_i.date()),
    }


def metric_block(fed: pd.DataFrame, s: float, label: str, *,
                 initial: float = INITIAL, verbose: bool = False,
                 curve_path: Path | None = None) -> dict:
    """FULL record-engine pass -> the metric block this instrument grades on.

    The 1m close/worst curves are persisted (parquet) when `curve_path` is
    given, so a sub-metric definition can be revised and RE-DERIVED without
    re-running the ~6.5-minute engine pass (and so any number here can be
    re-audited from the curve it came from).
    """
    RE, _ = _engine()
    t0 = time.time()
    r = RE.run_record(fed * s, label=label, initial=initial,
                      verbose=verbose, run_bootstrap=True)
    eq_c, eq_w = r["curves"]["equity"], r["curves"]["worst"]
    if curve_path is not None:
        curve_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"equity": eq_c, "worst": eq_w}).to_parquet(curve_path)
    blk = {
        "label": label, "dial_s": float(s), "initial": float(initial),
        "engine": "FMA2 account_engine_1m.simulate_account_1m (1m co-timed worst mark)",
        "cagr": r["cagr"],
        "maxdd_worst": r["maxdd_worst"],
        "maxdd_close": r["maxdd_close"],
        "breach_worst": r["breach"]["breach_worst"],
        "breach_close": r["breach"]["breach_close"],
        "median_dd_worst": r["breach"]["median_dd_worst"],
        "p95_dd_worst": r["breach"]["p95_dd_worst"],
        "final_equity": r["final_equity"],
        "sharpe": r["sharpe"], "n_trades": r["n_trades"],
        "runtime_s": round(time.time() - t0, 1),
    }
    blk.update(covid_submetrics(eq_c, eq_w))
    return blk


def cached_metric_block(fed_builder, s: float, label: str, cache_key: str,
                        *, initial: float = INITIAL, force: bool = False,
                        verbose: bool = False) -> dict:
    """metric_block with a JSON cache keyed on (stream identity, dial, seed).

    If the cached block predates the current sub-metric definitions but its 1m
    curve parquet is on disk, the sub-metrics are RE-DERIVED from that curve
    (no engine re-run).  Band components (cagr / maxdd_worst / breach_worst)
    always come from the engine pass that produced the curve.
    """
    OUTDIR.mkdir(parents=True, exist_ok=True)
    tag = f"{cache_key}_s{s:g}_i{int(initial)}"
    f = OUTDIR / f"metrics_{tag}.json"
    cf = OUTDIR / f"curve_{tag}.parquet"
    if f.exists() and not force:
        blk = json.loads(f.read_text())
        if blk.get("covid_schema") != COVID_SCHEMA and cf.exists():
            cur = pd.read_parquet(cf)
            blk.update(covid_submetrics(cur["equity"], cur["worst"]))
            blk["covid_schema"] = COVID_SCHEMA
            f.write_text(json.dumps(blk, indent=2))
        if blk.get("covid_schema") == COVID_SCHEMA:
            blk["_cache"] = str(f)
            return blk                                  # else: fall through, re-run
    blk = metric_block(fed_builder(), s, label, initial=initial, verbose=verbose,
                       curve_path=cf)
    blk["cache_key"] = cache_key
    blk["covid_schema"] = COVID_SCHEMA
    blk["curve"] = str(cf)
    f.write_text(json.dumps(blk, indent=2))
    blk["_cache"] = str(f)
    return blk


# ----------------------------------------------------------------------------
# the judge
# ----------------------------------------------------------------------------
def grade(cand: dict, gold: dict, struct: dict | None = None) -> dict:
    """Grade candidate vs golden on the RATIFIED band (+ the STRUCTURE gate)."""
    comps = []
    for k in ("cagr", "maxdd_worst", "breach_worst"):
        d = float(cand[k]) - float(gold[k])
        band = BAND[k]
        comps.append({
            "component": k, "golden": float(gold[k]), "candidate": float(cand[k]),
            "delta": d, "delta_pp": d * 100.0,
            "band_pp": band * 100.0,
            "pass": bool(abs(d) <= band + BAND_EPS),
        })
    if struct is not None:
        comps.insert(0, {
            "component": "structure", "golden": struct["symbols_golden"],
            "candidate": struct["symbols_candidate"],
            "delta": None, "delta_pp": None, "band_pp": None,
            "pass": bool(struct["ok"]),
            "detail": {k: struct[k] for k in
                       ("symbols_missing", "symbols_extra", "hours_missing",
                        "hours_extra", "duplicate_keys")},
        })
    broken = [c["component"] for c in comps if not c["pass"]]
    diag = {k: {"golden": gold.get(k), "candidate": cand.get(k),
                "delta": (cand[k] - gold[k])
                if isinstance(gold.get(k), (int, float)) and isinstance(cand.get(k), (int, float))
                else None}
            for k in ("covid_trough_worst_dd", "covid_trough_equity",
                      "covid_days_underwater", "covid_days_in_dd",
                      "covid_worst_day_mark", "maxdd_close", "final_equity",
                      "sharpe")}
    return {
        "verdict": "PASS" if not broken else "FAIL",
        "broken_components": broken,
        "components": comps,
        "covid_diagnostics": diag,
        "band": {k: v * 100.0 for k, v in BAND.items()},
        "dial_s": cand.get("dial_s"),
    }


def print_grade(g: dict, title: str) -> None:
    print(f"\n=== {title} ===")
    for c in g["components"]:
        if c["component"] == "structure":
            d = c["detail"]
            print(f"  STRUCTURE        {'PASS' if c['pass'] else 'FAIL'}   "
                  f"sym_missing={d['symbols_missing']} sym_extra={d['symbols_extra']} "
                  f"hours_missing={d['hours_missing']} hours_extra={d['hours_extra']} "
                  f"dup_keys={d['duplicate_keys']}")
        else:
            print(f"  {c['component']:<16} {'PASS' if c['pass'] else 'FAIL'}   "
                  f"golden {c['golden']:+.6f}  cand {c['candidate']:+.6f}  "
                  f"delta {c['delta_pp']:+.4f}pp   band +-{c['band_pp']:.1f}pp")
    d = g["covid_diagnostics"]
    print("  -- COVID diagnostics (not band-graded) --")
    for k in ("covid_trough_worst_dd", "covid_days_underwater", "covid_days_in_dd",
              "covid_worst_day_mark"):
        v = d[k]
        print(f"     {k:<22} golden {v['golden']}  cand {v['candidate']}  d {v['delta']}")
    print(f"  VERDICT: {g['verdict']}"
          + (f"  (broken: {', '.join(g['broken_components'])})" if g["broken_components"] else ""))


# ----------------------------------------------------------------------------
# reference-row printing
# ----------------------------------------------------------------------------
def print_reference(blk: dict) -> None:
    print(f"\n--- REFERENCE ROW  [{blk['label']}]  s={blk['dial_s']}  "
          f"seed EUR {blk['initial']:,.0f} ---")
    for k in ("cagr", "maxdd_worst", "maxdd_close", "breach_worst", "breach_close",
              "median_dd_worst", "p95_dd_worst", "final_equity", "sharpe", "n_trades",
              "covid_trough_worst_dd", "covid_trough_equity", "covid_trough_ts",
              "covid_highwater_day", "covid_days_underwater", "covid_recovery_date",
              "covid_recovery_censored", "covid_days_in_dd",
              "covid_worst_day_mark", "covid_worst_day_date"):
        v = blk[k]
        print(f"  {k:<22} {v:,.6f}" if isinstance(v, float) else f"  {k:<22} {v}")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def _golden_parsed():
    gp = parse_stream(GOLDEN_CSV)
    if gp["sha256"] != GOLDEN_SHA:
        raise SystemExit(f"GOLDEN SHA DRIFT: {gp['sha256']} != pinned {GOLDEN_SHA}")
    return gp


def cmd_baseline(a) -> int:
    gp = _golden_parsed()
    grid, cols = golden_frame(gp)
    print(f"golden {GOLDEN_CSV.name}  sha256 OK  rows {gp['n_rows']:,} "
          f"(data {gp['n_data']:,} + sentinels {gp['n_sentinels']:,})  "
          f"hours {gp['n_hours']:,}  symbols {len(cols)}")

    blocks = {}
    for s in a.dial:
        blk = cached_metric_block(lambda: stream_matrix(gp, grid, cols), s,
                                  f"golden_csv_s{s:g}", "goldencsv",
                                  force=a.force, verbose=a.verbose)
        blocks[s] = blk
        print_reference(blk)

    # POSITIVE SELF-TEST 1: judge(golden, golden) -> all-zero deltas.
    ok = True
    for s in a.dial:
        g = grade(blocks[s], blocks[s], structure_report(gp, gp))
        print_grade(g, f"SELF-TEST judge(golden, golden) s={s:g}  [must be PASS, zero deltas]")
        zero = all(c["delta"] == 0.0 for c in g["components"] if c["delta"] is not None)
        ok &= (g["verdict"] == "PASS") and zero
        print(f"  all deltas exactly 0.0: {zero}")

    # POSITIVE SELF-TEST 2 (independent load path): rebuild the golden matrix
    # straight from the MODEL OF RECORD (static_blend(0.70)) and judge it as a
    # candidate.  Proves the CSV->matrix reconstruction is faithful AND the
    # engine is deterministic — a self-test that could actually fail.
    if a.model_selftest:
        RE, M = _engine()
        import subprocess
        hc = subprocess.run([sys.executable, str(FMA3 / "strategy_fma3.py")],
                            capture_output=True, text=True).stdout
        assert M.CONFIG_HASH in hc, f"config hash drift: {hc.strip()}"
        print(f"\nconfig_hash {M.CONFIG_HASH} OK (model of record un-drifted)")
        fed_model = M.static_blend(M.CORE_WEIGHT)
        fed_csv = stream_matrix(gp, grid, cols)
        mx = float((fed_model.reindex(index=fed_csv.index, columns=fed_csv.columns)
                    - fed_csv).abs().to_numpy().max())
        print(f"matrix check   : max|static_blend - reparsed_golden| = {mx:.3e} "
              f"({'PASS' if mx < 1e-12 else 'FAIL'} < 1e-12)")
        ok &= mx < 1e-12
        s = a.dial[0]
        mblk = cached_metric_block(lambda: fed_model, s, f"golden_model_s{s:g}",
                                   "goldenmodel", force=a.force, verbose=a.verbose)
        print_reference(mblk)
        g = grade(mblk, blocks[s], structure_report(gp, gp))
        print_grade(g, f"SELF-TEST judge(golden_from_MODEL, golden_from_CSV) s={s:g}")
        ok &= g["verdict"] == "PASS"

    print(f"\nBASELINE: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_judge(a) -> int:
    gp = _golden_parsed()
    grid, cols = golden_frame(gp)
    cp = parse_stream(Path(a.candidate))
    st = structure_report(cp, gp)
    s = a.dial[0]
    gblk = cached_metric_block(lambda: stream_matrix(gp, grid, cols), s,
                               f"golden_csv_s{s:g}", "goldencsv", verbose=a.verbose)
    key = "cand" + cp["sha256"][:12]
    cblk = cached_metric_block(lambda: stream_matrix(cp, grid, cols), s,
                               f"candidate_s{s:g}", key, force=a.force, verbose=a.verbose)
    g = grade(cblk, gblk, st)
    print_reference(gblk)
    print_reference(cblk)
    print_grade(g, f"JUDGE  candidate={Path(a.candidate).name}  s={s:g}")
    rep = OUTDIR / f"grade_{key}_s{s:g}.json"
    rep.write_text(json.dumps({"candidate": cblk, "golden": gblk,
                               "structure": st, "grade": g}, indent=2, default=str))
    print(f"report -> {rep}")
    return 0 if g["verdict"] == "PASS" else 1


def _defective_stream(gp: dict, drop_symbol: str, out: Path) -> Path:
    """Write a REAL defective candidate stream: one symbol dropped entirely."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        fh.write((gp["header"] or "w_v7=0.7,config_hash=51a7541cc2aaa593,fmt=3") + "\n")
        for e, sym, v in gp["rows"]:
            if sym == drop_symbol:
                continue
            fh.write(f"{e},{sym},0\n" if sym == SENTINEL else f"{e},{sym},{v:.12f}\n")
    return out


def cmd_negctl(a) -> int:
    """NEGATIVE CONTROLS — the instrument must FAIL each and name the component."""
    gp = _golden_parsed()
    grid, cols = golden_frame(gp)
    s = a.dial[0]
    gblk = cached_metric_block(lambda: stream_matrix(gp, grid, cols), s,
                               f"golden_csv_s{s:g}", "goldencsv", verbose=a.verbose)
    st_ok = structure_report(gp, gp)

    controls = [("a", "cagr", 0.015, "+1.5pp CAGR shift"),
                ("b", "maxdd_worst", 0.008, "+0.8pp MaxDD_worst shift"),
                ("c", "breach_worst", 0.007, "+0.7pp breach shift")]
    results, ok = [], True
    for tag, key, shift, desc in controls:
        cblk = dict(gblk)
        cblk[key] = gblk[key] + shift
        cblk["label"] = f"NEGCTL_{tag}_{key}+{shift}"
        g = grade(cblk, gblk, st_ok)
        print_grade(g, f"NEGATIVE CONTROL ({tag}) {desc}  [must FAIL on '{key}']")
        good = (g["verdict"] == "FAIL" and g["broken_components"] == [key])
        ok &= good
        print(f"  control ({tag}) detected correctly: {good}"
              f"  (broken={g['broken_components']}, expected=['{key}'])")
        results.append({"control": tag, "injected": key, "shift_pp": shift * 100,
                        "verdict": g["verdict"], "broken": g["broken_components"],
                        "detected": good})

    if a.with_stream_defect:
        # (d) REAL STREAM DEFECT — the Antigravity failure mode, end to end.
        sc = Path(a.scratch) / f"NEGCTL_drop_{a.drop_symbol}.csv"
        _defective_stream(gp, a.drop_symbol, sc)
        cp = parse_stream(sc)
        stb = structure_report(cp, gp)
        key = "negdrop" + cp["sha256"][:12]
        cblk = cached_metric_block(lambda: stream_matrix(cp, grid, cols), s,
                                   f"NEGCTL_d_drop_{a.drop_symbol}_s{s:g}", key,
                                   force=a.force, verbose=a.verbose)
        g = grade(cblk, gblk, stb)
        print_reference(cblk)
        print_grade(g, f"NEGATIVE CONTROL (d) REAL STREAM: {a.drop_symbol} dropped "
                       f"[must FAIL structure + band]")
        good = (g["verdict"] == "FAIL" and "structure" in g["broken_components"]
                and stb["symbols_missing"] == [a.drop_symbol])
        ok &= good
        print(f"  control (d) detected correctly: {good}  "
              f"(named the dropped symbol: {stb['symbols_missing']})")
        results.append({"control": "d", "injected": f"drop {a.drop_symbol}",
                        "verdict": g["verdict"], "broken": g["broken_components"],
                        "named": stb["symbols_missing"], "detected": good})

    rep = OUTDIR / f"negctl_s{s:g}.json"
    rep.write_text(json.dumps({"golden": gblk, "controls": results,
                               "all_detected": ok}, indent=2, default=str))
    print(f"\nNEGATIVE CONTROLS: {'ALL DETECTED (instrument is live)' if ok else 'FAILED TO DETECT — INSTRUMENT NOT DELIVERABLE'}")
    print(f"report -> {rep}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["baseline", "judge", "negctl"])
    ap.add_argument("--candidate")
    ap.add_argument("--dial", type=float, action="append")
    ap.add_argument("--model-selftest", action="store_true")
    ap.add_argument("--with-stream-defect", action="store_true")
    ap.add_argument("--drop-symbol", default="XAUUSD")
    ap.add_argument("--scratch", default="/private/tmp/claude-501/-Users-dsalamanca-vs-env-FableMultiAssets3/cb1d44e8-f5e7-4172-a469-abf08e14a819/scratchpad")
    ap.add_argument("--force", action="store_true", help="ignore metric cache")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if not a.dial:
        a.dial = [1.6]
    if a.cmd == "judge" and not a.candidate:
        ap.error("judge requires --candidate")
    return {"baseline": cmd_baseline, "judge": cmd_judge, "negctl": cmd_negctl}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
