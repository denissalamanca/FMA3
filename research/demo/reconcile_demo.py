#!/usr/bin/env python3
"""reconcile_demo.py — the weekly demo-forward reconciliation harness (DEMO_FORWARD_PLAN §6D).

Ingests a FableBookNative run's own outputs — the per-hour telemetry CSV
(FMA3_native_hourly.csv) and the Strategy-Tester deals report (.xlsx) — and
produces the weekly checkpoint: plumbing health, worst-mark drawdown path +
crisis windows, friction decomposition, and (when a matched record reference is
supplied) growth-factor retention + native record->tick k.

Design notes (honest scope):
  * Self-contained metrics (plumbing / DD / friction) need ONLY the run's own
    output — they work for the LIVE demo period.
  * The 'vs record' block (retention, k) needs a matched record curve. Past the
    frozen horizon (2025-12-31) there is no golden to compare against
    (WARMSTART_DESIGN §7.4), so --record is optional; without it those rows are
    skipped, not faked.
  * min-ML is read from the telemetry IF the margin/ML field has been added
    (DEMO_FORWARD_PLAN §6C.1); until then it reports 'not logged'.

Usage:
  reconcile_demo.py --telemetry FMA3_native_hourly.csv --report ReportTester-*.xlsx \
                    [--record hrisk1_s160_curve.parquet] [--window 2024-07-29:2024-08-16 ...] \
                    [--json out.json]

Validated 2026-07-16 against report _43 (real-tick IC 2023-2025): net €134,862,
worst-mark DD 18.76%, swap -€26.5k, crisis DDs Aug-24 -15.5% / Apr-25 -13.1%.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd


def load_telemetry(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    h = df[df["rec"] == "H"].copy()
    h["dt"] = pd.to_datetime(h["ts"], unit="s")
    return h.sort_values("dt").reset_index(drop=True)


def load_deals(path: str) -> pd.DataFrame:
    import openpyxl  # lazy: only needed when a report is passed
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    hi = next((i for i, r in enumerate(rows)
               if r and "Deal" in [str(x) for x in r]
               and "Swap" in [str(x) for x in r] and "Balance" in [str(x) for x in r]), None)
    if hi is None:
        raise ValueError("deals table header (Deal/Swap/Balance) not found in report")
    cols = [str(x) for x in rows[hi]]
    body = []
    for r in rows[hi + 1:]:
        if r[0] is None:
            break
        body.append(r)
    d = pd.DataFrame(body, columns=cols[:len(body[0])])
    d = d[pd.to_numeric(d["Deal"], errors="coerce").notna()].copy()
    for c in ("Commission", "Swap", "Profit", "Balance"):
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["dt"] = pd.to_datetime(d["Time"], errors="coerce")
    return d


def worst_mark_dd(eq: pd.Series) -> float:
    """Worst peak-to-trough on an hourly-equity series (mark-to-market proxy)."""
    if len(eq) < 2:
        return float("nan")
    peak = np.maximum.accumulate(eq.values)
    return float(((eq.values - peak) / peak).min())


def window_slice(h: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    return h[(h["dt"] >= pd.Timestamp(a)) & (h["dt"] <= pd.Timestamp(b))]


def reconcile(telemetry: str, report: str | None, record: str | None,
              windows: list[str]) -> dict:
    h = load_telemetry(telemetry)
    out: dict = {"span": [str(h["dt"].iloc[0]), str(h["dt"].iloc[-1])],
                 "n_hours": int(len(h))}

    # --- plumbing health (self-contained) ---
    out["plumbing"] = {
        "fidelity_sc_mm_max": int(h["sc_mm"].max()) if "sc_mm" in h else None,
        "breaker_fires_max": int(h["fires"].max()) if "fires" in h else None,
        "unready_max": int(h["unready"].max()) if "unready" in h else None,
        "trading_from": (str(h[h["trading"] == 1]["dt"].min())
                         if "trading" in h and (h["trading"] == 1).any() else "NEVER"),
    }

    # --- equity + drawdown (self-contained) ---
    eq = h["equity"]
    out["equity"] = {
        "start": float(eq.iloc[0]), "end": float(eq.iloc[-1]),
        "return": float(eq.iloc[-1] / eq.iloc[0] - 1),
        "worst_mark_dd_hourly": worst_mark_dd(eq),
    }
    # min-ML if the margin field was added (§6C.1)
    ml_col = next((c for c in h.columns if c.lower() in ("margin_level", "ml", "marginlevel")), None)
    out["equity"]["min_ML"] = (float(h[ml_col].min()) if ml_col else "not logged (add margin/ML to telemetry — §6C.1)")

    # --- crisis / weekly windows ---
    out["windows"] = {}
    for w in windows:
        a, b = w.split(":")
        ws = window_slice(h, a, b)
        if len(ws) < 2:
            out["windows"][w] = {"n_hours": int(len(ws)), "note": "insufficient data"}
            continue
        we = ws["equity"]
        out["windows"][w] = {
            "n_hours": int(len(ws)),
            "return": float(we.iloc[-1] / we.iloc[0] - 1),
            "worst_mark_dd": worst_mark_dd(we),
        }

    # --- friction (needs the deals report) ---
    if report:
        d = load_deals(report)
        swap, comm = float(d["Swap"].sum()), float(d["Commission"].sum())
        prof = float(d["Profit"].sum())
        out["friction"] = {
            "n_deals": int(len(d)),
            "swap": swap, "commission": comm,
            "gross_profit_col_sum": prof,
            "net_incl_swap_comm": prof + swap + comm,
            "swap_pct_of_gross": (swap / prof * 100 if prof else None),
        }

    # --- vs record (optional; skipped past the frozen horizon) ---
    if record:
        rc = pd.read_parquet(record)
        eqcol = "equity" if "equity" in rc else rc.columns[0]
        rl = rc[eqcol].resample("1h").last().dropna()
        rl = rl[(rl.index >= h["dt"].iloc[0]) & (rl.index <= h["dt"].iloc[-1])]
        if len(rl) > 1:
            run_gf = eq.iloc[-1] / eq.iloc[0]
            rec_gf = rl.iloc[-1] / rl.iloc[0]
            out["vs_record"] = {
                "run_growth_factor": float(run_gf),
                "record_growth_factor": float(rec_gf),
                "growth_retention": float(run_gf / rec_gf),
            }
            # native k per window (run worst-mark DD / record worst-mark DD)
            wc = "worst" if "worst" in rc else eqcol
            rw = rc[wc].resample("1h").min().dropna()
            out["vs_record"]["k_by_window"] = {}
            for w in windows:
                a, b = w.split(":")
                run_dd = out["windows"].get(w, {}).get("worst_mark_dd")
                rws = rw[(rw.index >= pd.Timestamp(a)) & (rw.index <= pd.Timestamp(b))]
                rls = rl[(rl.index >= pd.Timestamp(a)) & (rl.index <= pd.Timestamp(b))]
                if run_dd and len(rls) > 1:
                    peak = rls.cummax()
                    rec_dd = float(((rws.reindex(rls.index) - peak) / peak).min())
                    out["vs_record"]["k_by_window"][w] = {
                        "run_dd": run_dd, "record_dd": rec_dd,
                        "k": (run_dd / rec_dd if rec_dd else None)}
        else:
            out["vs_record"] = "record does not overlap the run window (past the frozen horizon — expected for the live demo)"
    else:
        out["vs_record"] = "no --record supplied (skipped, not faked)"

    return out


def _fmt(out: dict) -> str:
    L = []
    L.append(f"DEMO RECONCILIATION — span {out['span'][0]} → {out['span'][1]} ({out['n_hours']:,} hrs)")
    p = out["plumbing"]
    L.append(f"  PLUMBING: fidelity sc_mm max={p['fidelity_sc_mm_max']} · breaker fires={p['breaker_fires_max']} · trading from {p['trading_from']}")
    e = out["equity"]
    L.append(f"  EQUITY:   {e['start']:,.0f} → {e['end']:,.0f}  ret {e['return']:+.1%}  worst-mark DD {e['worst_mark_dd_hourly']:.2%}  min ML {e['min_ML']}")
    if "friction" in out:
        f = out["friction"]
        L.append(f"  FRICTION: {f['n_deals']:,} deals · swap {f['swap']:,.0f} · comm {f['commission']:,.0f} · net {f['net_incl_swap_comm']:,.0f}")
    for w, v in out["windows"].items():
        if "worst_mark_dd" in v:
            L.append(f"  WINDOW {w}: ret {v['return']:+.1%}  worst-mark DD {v['worst_mark_dd']:.2%}")
    if isinstance(out.get("vs_record"), dict):
        vr = out["vs_record"]
        L.append(f"  vs RECORD: growth retention {vr.get('growth_retention', float('nan')):.2f}×")
        for w, k in vr.get("k_by_window", {}).items():
            L.append(f"     k[{w}] = {k['k']:.2f}× (run {k['run_dd']:.2%} / record {k['record_dd']:.2%})")
    else:
        L.append(f"  vs RECORD: {out['vs_record']}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Demo-forward weekly reconciliation harness")
    ap.add_argument("--telemetry", required=True, help="FMA3_native_hourly.csv")
    ap.add_argument("--report", help="ReportTester-*.xlsx (for friction)")
    ap.add_argument("--record", help="matched record curve parquet (optional; omit past the frozen horizon)")
    ap.add_argument("--window", action="append", default=[], help="A:B window(s), e.g. 2024-07-29:2024-08-16")
    ap.add_argument("--json", help="also write the full result as JSON")
    a = ap.parse_args(argv)
    out = reconcile(a.telemetry, a.report, a.record, a.window)
    print(_fmt(out))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, default=str))
        print(f"\n[full JSON -> {a.json}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
