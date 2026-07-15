#!/usr/bin/env python3
"""Offline blend combination of the two MT5 sub-book tester runs.

The MT5 Strategy Tester runs ONE EA per pass. The FMA3 tester protocol is
therefore two separate sub-book runs — the v7 EA (dial carrying w*s) and,
once its EA audit clears, the v3.4 stack — combined OFFLINE by deterministic
arithmetic (mt5/README.md section c). This script consumes the two tester
exports and produces:

  * the blend equity curve (daily, CSV),
  * per-book and joint metrics (CAGR, maxDD, Sharpe, COVID crisis tail),
  * the k ratios of DEMO_PREREGISTRATION.md section 5:
        k_dd   = tick worst-mark maxDD / record worst-mark maxDD
        k_tail = tick COVID tail       / record COVID tail
    computed on the record window (2020-01-02 .. 2025-12-31), same dial.

Combination arithmetic (the deployed two-EA model, archive/docs-v1.0/DEMO.md
"What does NOT exist yet" item 2 — each stack compounds its OWN internal
seeds on the shared account, so EUR P&L is additive):

    E_fed(t) = E_v7(t) + E_v34(t) - initial

Both runs must be seeded with the same initial deposit (default EUR 10,000);
a differently-seeded v3.4 report is rescaled by initial ratio (P&L is linear
in the seed under the fixed-fraction book) and the rescale is logged. This
additive model intentionally matches the DEPLOYED account, not the pin's
native-index construction (strategy_fma3.py) — the gap between the two is a
disclosed, measured quantity (RECONCILIATION.md), not an error.

Inputs per book (auto-detected by extension):
  * .html/.htm — the MT5 Strategy Tester single-run report. The deals-table
    Balance column gives the deal-mark curve; the summary's "Equity Drawdown
    Maximal" percentage (tick-level, floating) is used as the worst-mark
    numerator for k_dd when present.
  * .csv — any time,equity export (e.g. portfolio_v7_decisions.csv columns
    utc_time/acct_equity, or the heartbeat CSV). Curve granularity = row
    cadence; worst-mark then falls back to close-basis (understates; the
    output flags it).

Usage:
  python3 scripts/combine_tester_reports.py --v7 ReportTester-v7.html \
      [--v34 ReportTester-v34.html] [--preset ic|ftmo|native] \
      [--initial 10000] [--outdir research/outputs/mt5]

v7-only mode (no --v34): reports v7 metrics + v7 k ratios and marks the
blend columns "pending v3.4 EA audit" — the pre-registered interim
asymmetry (DEMO_PREREGISTRATION.md section 5.1).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Pinned record-engine references (engine-free derivations; see mt5/README.md
# section b for the arithmetic and provenance — no record-engine pass needed).
# 'v7' rows: v7_book_equity_1m.parquet minute returns x scale, recompounded.
# 'fed' rows: hrisk1_results.json (s=1.6) / hrisk2_results.json (s=0.4) /
# fma3_v1_pin.json (s=1.1 fallback -> 'native' uses the R8 v7 book only).
# ---------------------------------------------------------------------------
RECORD_WINDOW = (pd.Timestamp("2020-01-02"), pd.Timestamp("2025-12-31 23:59"))
COVID_LO, COVID_HI = pd.Timestamp("2020-02-15"), pd.Timestamp("2020-04-15")

RECORD = {
    "ic": {                                    # H-RISK-1, s=1.6 (FMA3-004c)
        "v7":  {"scale": 1.12, "cagr": 1.089, "maxdd_worst": 0.2161,
                "maxdd_close": 0.2135, "tail": 0.1274},
        "v34": None,                           # placeholder pending EA audit
        "fed": {"s": 1.6, "cagr": 1.7016824131883754,
                "maxdd_worst": 0.22583669122811498,
                "tail": 0.08116002067591448},
    },
    "ftmo": {                                  # H-RISK-2, s=0.4 (FMA3-005c)
        "v7":  {"scale": 0.28, "cagr": 0.215, "maxdd_worst": 0.0584,
                "maxdd_close": 0.0576, "tail": 0.0330},
        "v34": None,
        "fed": {"s": 0.4, "cagr": 0.3066769687622055,
                "maxdd_worst": 0.05986772484177472, "tail": None},
    },
    "native": {                                # v7 parent R8 anchor, reference
        "v7":  {"scale": 1.00, "cagr": 0.940, "maxdd_worst": 0.1951,
                "maxdd_close": 0.1927, "tail": 0.1143},
        "v34": None,
        "fed": None,
    },
}

_NUM = re.compile(r"-?[\d \s']*\d(?:[.,]\d+)?")
_TS = re.compile(r"^\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}(?::\d{2})?$")


def _to_float(cell: str) -> float | None:
    cell = cell.replace(" ", "").replace(" ", "").replace("'", "")
    cell = cell.replace(",", ".") if cell.count(",") == 1 and "." not in cell else cell.replace(",", "")
    try:
        return float(cell)
    except ValueError:
        return None


def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_mt5_html(path: Path) -> tuple[pd.Series, dict]:
    """Deal-mark balance curve + summary stats from an MT5 tester report."""
    text = _decode(path.read_bytes())
    stats: dict = {"source": "mt5_html", "equity_dd_max_pct": None,
                   "initial_deposit": None}

    m = re.search(r"Initial Deposit[^<]*(?:</td>|:)\s*<[^>]*>([^<]+)", text, re.I)
    if m:
        stats["initial_deposit"] = _to_float(m.group(1))
    m = re.search(
        r"Equity Drawdown Maximal[^<]*</td>\s*<td[^>]*>[^<(]*\(([\d.,]+)%\)",
        text, re.I)
    if not m:  # some builds render "Drawdown Maximal" under an Equity section
        m = re.search(r"Equity Drawdown Maximal[^(]*\(([\d.,]+)%\)", text, re.I)
    if m:
        stats["equity_dd_max_pct"] = _to_float(m.group(1))

    times, balances = [], []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if len(cells) < 6 or not _TS.match(cells[0]):
            continue
        # Deals table: ... Commission Swap Profit Balance Comment — take the
        # last parseable numeric cell (Comment is usually text/empty).
        bal = None
        for c in reversed(cells[1:]):
            v = _to_float(c)
            if v is not None:
                bal = v
                break
        if bal is None:
            continue
        times.append(pd.to_datetime(cells[0], format="%Y.%m.%d %H:%M:%S",
                                    errors="coerce"))
        balances.append(bal)
    ser = pd.Series(balances, index=pd.DatetimeIndex(times)).dropna()
    ser = ser[~ser.index.isna()].sort_index()
    if ser.empty:
        raise SystemExit(f"{path}: no deals rows parsed — export the FULL "
                         "tester report (right-click result -> Report -> HTML)")
    return ser, stats


def parse_csv(path: Path) -> tuple[pd.Series, dict]:
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    tcol = next((cols[k] for k in ("utc_time", "time", "date", "datetime")
                 if k in cols), df.columns[0])
    ecol = next((cols[k] for k in ("acct_equity", "equity", "eq", "balance")
                 if k in cols), df.columns[1])
    ser = pd.Series(pd.to_numeric(df[ecol], errors="coerce").values,
                    index=pd.to_datetime(df[tcol], errors="coerce")).dropna()
    ser = ser[~ser.index.isna()].sort_index()
    if ser.empty:
        raise SystemExit(f"{path}: could not extract a time,equity curve")
    return ser, {"source": "csv", "equity_dd_max_pct": None,
                 "initial_deposit": None}


def load_curve(path: str) -> tuple[pd.Series, dict]:
    p = Path(path)
    if p.suffix.lower() in (".html", ".htm"):
        return parse_mt5_html(p)
    return parse_csv(p)


def crisis_tail(eq: pd.Series) -> float | None:
    """Pinned formula (run_hfed1_lib.crisis_tail): worst COVID-window mark vs
    the running all-history close peak."""
    peak = eq.cummax()
    win = (eq.index >= COVID_LO) & (eq.index <= COVID_HI)
    if not win.any():
        return None
    dd = (peak[win] - eq[win]) / peak[win]
    return float(dd.max())


def metrics(eq: pd.Series, initial: float, label: str,
            tick_dd_pct: float | None) -> dict:
    daily = eq.resample("1D").last().dropna()
    r = daily.pct_change().dropna()
    yrs = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    ddc = float((1 - eq / eq.cummax()).max())
    out = {
        "label": label,
        "start": str(eq.index[0]), "end": str(eq.index[-1]),
        "final_equity": float(eq.iloc[-1]),
        "cagr": float((eq.iloc[-1] / initial) ** (1 / yrs) - 1),
        "maxdd_close_curve": ddc,
        "maxdd_worst_tick": (tick_dd_pct / 100.0) if tick_dd_pct else None,
        "maxdd_for_k": (tick_dd_pct / 100.0) if tick_dd_pct else ddc,
        "maxdd_for_k_basis": "tester equity-DD (tick, floating)"
                             if tick_dd_pct else
                             "curve close-basis (UNDERSTATES worst-mark)",
        "sharpe_daily": float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 2 else None,
        "crisis_tail": crisis_tail(eq),
    }
    return out


def k_ratios(m: dict, rec: dict | None) -> dict:
    if rec is None:
        return {"k_dd": None, "k_tail": None,
                "note": "no record reference (v3.4 placeholder pending EA audit)"}
    k_dd = m["maxdd_for_k"] / rec["maxdd_worst"] if rec.get("maxdd_worst") else None
    k_tail = (m["crisis_tail"] / rec["tail"]
              if m.get("crisis_tail") and rec.get("tail") else None)
    return {"k_dd": k_dd, "k_tail": k_tail,
            "record_maxdd_worst": rec.get("maxdd_worst"),
            "record_tail": rec.get("tail"),
            "dd_basis": m["maxdd_for_k_basis"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--v7", required=True, help="v7 tester report (.html) or curve CSV")
    ap.add_argument("--v34", help="v3.4 tester report/CSV (omit while its EA audit is open)")
    ap.add_argument("--preset", choices=list(RECORD), default="ic")
    ap.add_argument("--initial", type=float, default=10000.0)
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parents[1]
                                            / "research" / "outputs" / "mt5"))
    a = ap.parse_args()
    rec = RECORD[a.preset]
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    results = {"preset": a.preset, "initial": a.initial, "books": {}, "k": {}}

    core_eq, st7 = load_curve(a.v7)
    # k ratios are computed on the record window only (same-window rule)
    core_eq_rw = core_eq[(core_eq.index >= RECORD_WINDOW[0]) & (core_eq.index <= RECORD_WINDOW[1])]
    m7_full = metrics(core_eq, a.initial, "v7 sub-book (full run)", st7["equity_dd_max_pct"])
    m7_rw = metrics(core_eq_rw, a.initial, "v7 sub-book (record window 2020-2025)",
                    st7["equity_dd_max_pct"])
    results["books"]["v7_full"] = m7_full
    results["books"]["v7_record_window"] = m7_rw
    results["k"]["v7"] = k_ratios(m7_rw, rec["v7"])

    fed_daily = None
    if a.v34:
        sat_eq, st34 = load_curve(a.v34)
        init34 = st34.get("initial_deposit") or a.initial
        if abs(init34 - a.initial) > 1e-6:
            sat_eq = sat_eq * (a.initial / init34)
            results["books"]["v34_rescale"] = f"x{a.initial / init34:.4f} (seed {init34} -> {a.initial})"
        sat_eq_rw = sat_eq[(sat_eq.index >= RECORD_WINDOW[0]) & (sat_eq.index <= RECORD_WINDOW[1])]
        m34_rw = metrics(sat_eq_rw, a.initial, "v3.4 sub-book (record window)",
                         st34["equity_dd_max_pct"])
        results["books"]["v34_record_window"] = m34_rw
        results["k"]["v34"] = k_ratios(m34_rw, rec["v34"])

        d7 = core_eq.resample("1D").last().dropna()
        d34 = sat_eq.resample("1D").last().dropna()
        grid = d7.index.union(d34.index)
        fed_daily = (d7.reindex(grid).ffill().bfill()
                     + d34.reindex(grid).ffill().bfill() - a.initial)
        fed_rw = fed_daily[(fed_daily.index >= RECORD_WINDOW[0])
                           & (fed_daily.index <= RECORD_WINDOW[1])]
        mf = metrics(fed_rw, a.initial, "federation (additive, record window)", None)
        results["books"]["federation_record_window"] = mf
        results["k"]["federation"] = k_ratios(mf, rec["fed"])
        fed_daily.rename("equity").to_csv(outdir / "federation_curve.csv",
                                          header=True, index_label="date")
    else:
        results["k"]["federation"] = {
            "note": "PENDING — v3.4 sub-book tester run not supplied "
                    "(EA audit open, FMA2 docs/v3.4/RECONCILIATION.md §C). "
                    "Interim k measured on the v7 stack only "
                    "(DEMO_PREREGISTRATION.md §5.1, disclosed asymmetry)."}

    (outdir / "combine_results.json").write_text(json.dumps(results, indent=1))

    # ---- paste-ready block ------------------------------------------------
    def fmt(x, pct=True):
        return "n/a" if x is None else (f"{x*100:.2f}%" if pct else f"{x:,.0f}")
    print("\n=== FMA3 tester combination —", a.preset.upper(), "preset ===")
    for key in ("v7_record_window", "v34_record_window", "federation_record_window"):
        m = results["books"].get(key)
        if not m:
            continue
        print(f"\n[{m['label']}]  {m['start'][:10]} -> {m['end'][:10]}")
        print(f"  final €{fmt(m['final_equity'], False)}  CAGR {fmt(m['cagr'])}"
              f"  maxDD(close) {fmt(m['maxdd_close_curve'])}"
              f"  maxDD(tick) {fmt(m['maxdd_worst_tick'])}"
              f"  Sharpe {m['sharpe_daily'] and round(m['sharpe_daily'],3)}"
              f"  COVID tail {fmt(m['crisis_tail'])}")
    print("\n[k ratios — DEMO_PREREGISTRATION.md §5 (record window, same dial)]")
    for book, k in results["k"].items():
        if k.get("k_dd") is None and k.get("k_tail") is None:
            print(f"  {book}: {k.get('note','n/a')}")
        else:
            print(f"  {book}: k_dd = {k['k_dd']:.3f} ({k['dd_basis']})"
                  + (f" · k_tail = {k['k_tail']:.3f}" if k.get("k_tail") else
                     " · k_tail = n/a"))
    print(f"\nWrote {outdir}/combine_results.json"
          + (f" and {outdir}/federation_curve.csv" if fed_daily is not None else ""))
    print("Paste the block above into mt5/README.md §'Results' and the "
          "DEMO_PREREGISTRATION deploy-time addendum.")


if __name__ == "__main__":
    sys.exit(main())
