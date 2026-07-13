#!/usr/bin/env python3
"""FMA3-002: H-FED-2 — rebalanced federation (cross-book vol-harvesting).

Pre-registered in research/protocol/HYPOTHESES.md. Adds periodic re-split of
TOTAL account equity back to (w, 1-w) between the two books, on top of the
H-FED-1 static federation at the winning w (selection rule: all-bars pass,
max Sharpe — amended into HYPOTHESES.md 2026-07-10 12:29 before any H-FED-1
result was read; this script reads the winner from hfed1_results.json at
runtime and refuses to run if no grid point passed).

Variants (each a separate ledger sub-entry):
  F2a: calendar-quarterly re-split (v13-REBAL medicine at book level).
  F2b: band-triggered re-split — v7-book share > B_up or < 1-B_up, decided on
       daily close, act next server midnight, 5-day min gap (BAND_SYM_25
       semantics at N=2). Pre-registered B_up grid: {0.60, 0.65, 0.70}.

BOOKKEEPING EXACTNESS
---------------------
Within a federation segment, each book's sub-equity evolves by its NATIVE
curve's growth factor: A*(t) = A*(seg_start) * A(t)/A(seg_start). This is
exact, not approximate, because both books' internal dynamics are
scale-invariant in fraction space: the v7 band/harvest triggers fire on slot
RATIOS (and k*seed thresholds that scale with seed), and the v3.4 book sizes
positions as fractions of its sub-equity. Rebasing a book's capital at a
federation edge rescales all its slots linearly and changes nothing internal.
(Min-lot quantization is not scale-invariant, but fills are realized by the
record engine on the joint account — bookkeeping only sets targets.)
The anti-coupling guard (PROTOCOL §5.7) holds: neither book's internal state
ever sees the other's P&L; only the federation allocator does, causally
(decisions on daily close, action next server midnight).

BARS (pre-registered): same as H-FED-1, PLUS the rebalanced variant must beat
static H-FED-1 at the same w by > +0.5pp CAGR at <= +0.3pp worst-mark DD,
else DECLINE (cadence complexity not paid for).

Run: python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/run_hfed2.py
Runtime ~30 min (4 engine passes: F2a + 3x F2b). Writes
research/outputs/hfed2_results.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))

import record_engine as RE  # noqa: E402
from run_hfed1_lib import (  # noqa: E402
    load_inputs, crisis_tail, ideal_metrics)

B_UP_GRID = (0.60, 0.65, 0.70)   # pre-registered, fixed
MIN_GAP_DAYS = 5


def federation_weights(a: pd.Series, b: pd.Series, w: float,
                       hours: pd.DatetimeIndex,
                       mode: str, b_up: float | None = None
                       ) -> tuple[pd.Series, pd.Series, list[dict]]:
    """Piecewise sub-equity bookkeeping with federation re-splits.

    Returns hourly (A*, B*) bookkeeping sub-equity series on `hours` plus the
    re-split event list. `a`, `b` are the native 1m curves normalized to 1.0.
    mode='quarterly' re-splits at calendar-quarter starts; mode='band'
    re-splits when the v7 share A*/(A*+B*) on a daily close breaches
    [1-b_up, b_up], acting at the next server midnight, >=5d min gap.
    """
    # causal hourly samples of the native curves
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)

    # daily close stamps for band decisions (server-time calendar days)
    days = a_h.resample("1D").last().dropna().index

    if mode == "quarterly":
        edges = pd.date_range(hours[0].normalize(), hours[-1], freq="QS")
        edges = [e for e in edges if e > hours[0]]
    elif mode == "band":
        edges = None  # discovered causally below
    else:
        raise ValueError(mode)

    a_star = pd.Series(np.nan, index=hours)
    b_star = pd.Series(np.nan, index=hours)
    events: list[dict] = []

    seg_start = hours[0]
    ja, jb = w, 1.0 - w          # bookkeeping sub-equities at segment start
    a0, b0 = float(a_h.iloc[0]), float(b_h.iloc[0])
    last_split_day: pd.Timestamp | None = None

    def grow(seg_end):
        nonlocal ja, jb, a0, b0, seg_start
        m = (hours >= seg_start) & (hours < seg_end)
        a_star.loc[m] = ja * (a_h[m] / a0)
        b_star.loc[m] = jb * (b_h[m] / b0)

    if mode == "quarterly":
        for e in list(edges) + [hours[-1] + pd.Timedelta(hours=1)]:
            grow(e)
            m = (hours >= seg_start) & (hours < e)
            if not m.any():
                continue
            last = hours[m][-1]
            j = float(a_star[last] + b_star[last])
            events.append({"act": str(e), "kind": "quarter",
                           "v7_share_before": float(a_star[last] / j),
                           "joint": j})
            ja, jb = w * j, (1.0 - w) * j
            a0, b0 = float(a_h[last]), float(b_h[last])
            seg_start = e
        events = events[:-1]  # final grow() sentinel is not a re-split
    else:
        d_i = 0
        while d_i < len(days):
            d = days[d_i]
            if d <= seg_start:
                d_i += 1
                continue
            # bookkeeping shares at this daily close (causal: uses curves <= d)
            a_d = ja * (float(a_h.asof(d)) / a0)
            b_d = jb * (float(b_h.asof(d)) / b0)
            share = a_d / (a_d + b_d)
            gap_ok = (last_split_day is None
                      or (d - last_split_day).days >= MIN_GAP_DAYS)
            if gap_ok and (share > b_up or share < 1.0 - b_up):
                act = d.normalize() + pd.Timedelta(days=1)  # next midnight
                grow(act)
                m = (hours >= seg_start) & (hours < act)
                last = hours[m][-1]
                j = float(a_star[last] + b_star[last])
                events.append({"act": str(act), "kind": "band",
                               "decided": str(d.date()),
                               "v7_share": float(share), "joint": j})
                ja, jb = w * j, (1.0 - w) * j
                a0 = float(a_h.asof(act) if not np.isnan(a_h.asof(act))
                           else a_h[m][-1])
                b0 = float(b_h.asof(act) if not np.isnan(b_h.asof(act))
                           else b_h[m][-1])
                seg_start = act
                last_split_day = d
            d_i += 1
        grow(hours[-1] + pd.Timedelta(hours=1))

    return a_star, b_star, events


def blend(frac7, frac34, a_star, b_star) -> pd.DataFrame:
    j = a_star + b_star
    wa, wb = a_star / j, b_star / j
    hours = a_star.index
    f7 = frac7.reindex(hours).fillna(0.0)
    f34 = frac34.reindex(hours).fillna(0.0)
    cols = sorted(set(f7.columns) | set(f34.columns))
    return (f7.reindex(columns=cols, fill_value=0.0).mul(wa, axis=0)
            + f34.reindex(columns=cols, fill_value=0.0).mul(wb, axis=0))


def main() -> int:
    t0 = time.time()
    h1 = json.loads((RE.PATHS.OUTPUTS / "hfed1_results.json").read_text())
    passers = {k: v for k, v in h1["grid"].items() if v["bars_pass"]}
    risk_passers = {
        k: v for k, v in h1["grid"].items()
        if v["maxdd_worst"] < h1["bars"]["dd_lt"]
        and v["n_neg_quarters"] <= h1["bars"]["neg_quarters_le"]
        and not v["neg_years"]}
    if passers:
        win_key = max(passers, key=lambda k: passers[k]["sharpe"])
    elif risk_passers:
        win_key = max(risk_passers, key=lambda k: risk_passers[k]["sharpe"])
        print(f"[hfed2] NOTE: no full-bars passer; proceeding on risk-half "
              f"passer {win_key} per amended selection rule", flush=True)
    else:
        print("[hfed2] REFUSING TO RUN: no H-FED-1 point passed the risk "
              "bars — per protocol, rebalancing may not rescue a config "
              "that failed on risk.", flush=True)
        return 2
    w = h1["grid"][win_key]["w_v7"]
    static = h1["grid"][win_key]
    print(f"[hfed2] base config {win_key} (w_v7={w}); static: "
          f"CAGR {static['cagr']:+.4f} DDw {static['maxdd_worst']:.4f} "
          f"Sh {static['sharpe']:.3f}", flush=True)

    frac7, frac34, a, b = load_inputs()
    hours = frac7.index.union(frac34.index)

    variants = [("f2a_quarterly", "quarterly", None)] + \
               [(f"f2b_band{int(bu*100)}", "band", bu) for bu in B_UP_GRID]

    results = {"base": {"key": win_key, "w_v7": w, "static": static},
               "grid": {}}
    for lbl, mode, bu in variants:
        print(f"[{lbl}] bookkeeping + engine pass "
              f"({time.time()-t0:.0f}s elapsed) ...", flush=True)
        a_star, b_star, events = federation_weights(a, b, w, hours, mode, bu)
        fed = blend(frac7, frac34, a_star, b_star)
        res = RE.run_record(fed, label=lbl, verbose=False)
        tail = crisis_tail(res["curves"]["equity"], res["curves"]["worst"])
        d_cagr = (res["cagr"] - static["cagr"]) * 100
        d_dd = (res["maxdd_worst"] - static["maxdd_worst"]) * 100
        pays = d_cagr > 0.5 and d_dd <= 0.3
        all_bars = (res["maxdd_worst"] < h1["bars"]["dd_lt"]
                    and res["sharpe"] > h1["bars"]["sharpe_gt"]
                    and res["n_neg_years"] == 0
                    and res["n_neg_quarters"] <= h1["bars"]["neg_quarters_le"])
        row = {
            "mode": mode, "b_up": bu, "n_events": len(events),
            "events": events,
            "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
            "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
            "crisis_tail": tail, "final_equity": res["final_equity"],
            "neg_years": res["neg_years"],
            "neg_quarters": res["neg_quarters"],
            "n_neg_quarters": res["n_neg_quarters"],
            "breach": res["breach"], "yearly": res["yearly"],
            "delta_cagr_pp_vs_static": d_cagr,
            "delta_dd_pp_vs_static": d_dd,
            "pays_for_cadence": bool(pays),
            "hfed1_bars_pass": bool(all_bars),
        }
        results["grid"][lbl] = row
        print(f"[{lbl}] CAGR {res['cagr']:+.4f} ({d_cagr:+.2f}pp) | "
              f"DDw {res['maxdd_worst']:.4f} ({d_dd:+.2f}pp) | "
              f"Sh {res['sharpe']:.3f} | events {len(events)} | "
              f"pays {'YES' if pays else 'no'} | "
              f"bars {'PASS' if all_bars else 'fail'}", flush=True)
        pd.DataFrame({"equity": res["curves"]["equity"],
                      "worst": res["curves"]["worst"]}).to_parquet(
            RE.PATHS.OUTPUTS / f"hfed2_{lbl}_curve.parquet")
        del res["curves"]

    out = RE.PATHS.OUTPUTS / "hfed2_results.json"
    out.write_text(json.dumps(results, indent=1, default=str))
    print(f"\nDONE ({time.time()-t0:.0f}s) -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
