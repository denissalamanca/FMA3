#!/usr/bin/env python3
"""FMA3 v1.0 package data pack — every number a writer needs, engine-free.

Assembles research/outputs/package_data.json strictly from PINNED artifacts
(fma3_v1_pin.json + fma3_v1_pin_curve.parquet, composite_benchmark.json,
hfed1/2/3_results.json, hcaps1_analysis.json, redteam/rt_perturbation.json,
forward_oneshot.json, docs/REGISTRY.md decisions) plus pure matrix math on
the locked blend matrix (build_locked_matrix imported from
scripts/eval_fma3_pin.py — NO engine run anywhere in this script).

Blocks (consumed by archive/docs-v1.0/* writers and the dashboard):
  1. weekly equity series (pin curve, W-last close-mark) + both parents'
     native curves normalized to EUR 10k (overlay context; v7 = band engine)
  2. daily worst-mark drawdown series (dd_t = 1 - worst_t/cummax(close_t),
     daily max — engine convention)
  3. gate tiles: six owner gates + seven composite dimensions
  4. yearly/quarterly return tables (pin JSON) + monthly returns (curve)
  5. trade/exposure characteristics (turnover, per-instrument profile,
     gross percentiles, overnight gold, sub-book contribution shares)
  6. lever cards (how v1.0 was reached — REGISTRY.md one-liners)
  7. rejected extensions ('stress-tested after' chips)
  8. forward one-shot block (F1-F4 + monthly path)

Run: python3 scripts/build_package_data.py            (~1-2 min: the v3.4
matrix delegate rebuilds sleeve parquet loads; matrix math only)
Outputs: research/outputs/package_data.json
         research/outputs/package_data_weekly_preview.txt
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3))
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))

OUT = _FMA3 / "research" / "outputs"
BASE = _FMA3 / "research" / "baselines"

TOL = 1e-9


# ------------------------------------------------------------------ helpers --
def _series_pairs(s: pd.Series, nd: int) -> list[list]:
    """[ISO-date, value] pairs, rounded."""
    return [[d.strftime("%Y-%m-%d"), round(float(v), nd)]
            for d, v in s.items()]


def _weekly_10k(eq: pd.Series) -> pd.Series:
    """Close-mark weekly (W last), normalized to EUR 10k at the first mark."""
    return (eq / float(eq.iloc[0]) * 10000.0).resample("W").last().dropna()


# --------------------------------------------------------------------- main --
def main() -> int:
    t0 = time.time()
    pin = json.loads((OUT / "fma3_v1_pin.json").read_text())
    comp = json.loads((OUT / "composite_benchmark.json").read_text())
    hfed1 = json.loads((OUT / "hfed1_results.json").read_text())
    hfed2 = json.loads((OUT / "hfed2_results.json").read_text())
    hfed3 = json.loads((OUT / "hfed3_results.json").read_text())
    hcaps = json.loads((OUT / "hcaps1_analysis.json").read_text())
    rt_pert = json.loads((OUT / "redteam" / "rt_perturbation.json").read_text())
    fwd = json.loads((OUT / "forward_oneshot.json").read_text())

    curve = pd.read_parquet(OUT / "fma3_v1_pin_curve.parquet")
    close, worst = curve["equity"], curve["worst"]

    # ---- 1. weekly equity (pin + both parents' record curves @ EUR 10k) ----
    wk_fed = _weekly_10k(close)
    wk_v34 = _weekly_10k(
        pd.read_parquet(BASE / "fma2" / "v34_s10_pin_curve.parquet")["equity"])
    wk_v7 = _weekly_10k(
        pd.read_parquet(OUT / "v7_book_equity_1m.parquet")["eqc"])
    assert abs(float(wk_fed.iloc[-1]) - pin["pin"]["final_equity"]) < 1.0, \
        "weekly last mark != pinned final equity"

    # ---- 2. daily worst-mark drawdown (engine convention) -------------------
    dd_1m = 1.0 - worst / close.cummax()
    dd_daily = dd_1m.resample("D").max().dropna()
    assert abs(float(dd_daily.max()) - pin["pin"]["maxdd_worst"]) < 1e-12, \
        "daily dd max != pinned maxdd_worst"

    # ---- 3. gate tiles ------------------------------------------------------
    p = pin["pin"]
    breach_worst = pin["breach"]["breach_worst"]
    owner_gates = [
        {"id": "cagr", "label": "CAGR", "bar": "> 96.1%",
         "value": p["cagr"], "display": f"+{p['cagr']*100:.1f}%",
         "pass": pin["gates"]["owner"]["cagr>0.961"]},
        {"id": "maxdd", "label": "Max DD (worst-mark)", "bar": "< 20.9%",
         "value": p["maxdd_worst"], "display": f"{p['maxdd_worst']*100:.2f}%",
         "pass": pin["gates"]["owner"]["maxdd<0.209"]},
        {"id": "sharpe", "label": "Sharpe", "bar": "> 2.03",
         "value": p["sharpe"], "display": f"{p['sharpe']:.3f}",
         "pass": pin["gates"]["owner"]["sharpe>2.03"]},
        {"id": "tail", "label": "COVID tail", "bar": "<= 35.6%",
         "value": p["crisis_tail"], "display": f"{p['crisis_tail']*100:.2f}%",
         "pass": pin["gates"]["owner"]["tail<=0.356"]},
        {"id": "negy", "label": "Negative years", "bar": "== 0",
         "value": len(p["neg_years"]), "display": f"{len(p['neg_years'])}/6",
         "pass": pin["gates"]["owner"]["negY==0"]},
        {"id": "negq", "label": "Negative quarters", "bar": "<= 1",
         "value": len(p["neg_quarters"]),
         "display": f"{len(p['neg_quarters'])}/24",
         "pass": pin["gates"]["owner"]["negQ<=1"]},
    ]
    cg = comp["composite_gates"]
    composite_dims = [
        {"id": "cagr", "label": "CAGR", "bar": f"> {cg['cagr_gt']*100:.2f}% (v7@r8)",
         "threshold": cg["cagr_gt"], "value": p["cagr"],
         "pass": p["cagr"] > cg["cagr_gt"]},
        {"id": "maxdd", "label": "Max DD (worst-mark)",
         "bar": f"< {cg['maxdd_worst_lt']*100:.2f}% (v7@r8)",
         "threshold": cg["maxdd_worst_lt"], "value": p["maxdd_worst"],
         "pass": p["maxdd_worst"] < cg["maxdd_worst_lt"]},
        {"id": "sharpe", "label": "Sharpe", "bar": f"> {cg['sharpe_gt']:.3f} (v7@r8)",
         "threshold": cg["sharpe_gt"], "value": p["sharpe"],
         "pass": p["sharpe"] > cg["sharpe_gt"]},
        {"id": "tail", "label": "COVID tail",
         "bar": f"<= {cg['crisis_tail_le']*100:.2f}% (v7@r8)",
         "threshold": cg["crisis_tail_le"], "value": p["crisis_tail"],
         "pass": p["crisis_tail"] <= cg["crisis_tail_le"]},
        {"id": "negy", "label": "Negative years", "bar": "== 0 (both parents)",
         "threshold": cg["neg_years_eq"], "value": len(p["neg_years"]),
         "pass": len(p["neg_years"]) == cg["neg_years_eq"]},
        {"id": "negq", "label": "Negative quarters", "bar": "<= 0 (v7@r8)",
         "threshold": cg["neg_quarters_le"], "value": len(p["neg_quarters"]),
         "pass": len(p["neg_quarters"]) <= cg["neg_quarters_le"]},
        {"id": "breach", "label": "Breach P(DD>30%)",
         "bar": f"< {cg['breach_lt']} (v7@r8)",
         "threshold": cg["breach_lt"], "value": breach_worst,
         "pass": breach_worst < cg["breach_lt"]},
    ]
    assert all(t["pass"] for t in owner_gates), "owner gate regression"
    assert all(t["pass"] for t in composite_dims), \
        "composite dominance regression (REGISTRY: all 7 dominate at s=1.1)"

    # ---- 4. yearly / quarterly (pin) + monthly (curve) ----------------------
    eq_m = close.resample("ME").last().dropna()
    prev = pd.concat([pd.Series([10000.0]), eq_m.iloc[:-1]])
    monthly = {d.strftime("%Y-%m"): round(float(v / pv - 1.0), 6)
               for d, v, pv in zip(eq_m.index, eq_m.values, prev.values)}
    growth = float(np.prod([1 + r for r in monthly.values()]))
    assert abs(growth * 10000.0 - p["final_equity"]) < 1.0, \
        "monthly returns do not compound to the pinned final equity"

    # ---- 5. trade / exposure characteristics (matrix math only) -------------
    from eval_fma3_pin import build_locked_matrix  # noqa: E402 (no engine run)
    fed = build_locked_matrix()          # locked matrix incl. s=1.1
    dfrac = fed.diff().abs()
    dfrac.iloc[0] = 0.0
    turn_daily = dfrac.sum(axis=1).groupby(fed.index.date).sum()
    gross = fed.abs().sum(axis=1)
    inst = {
        c: {"mean_absfrac": round(float(fed[c].abs().mean()), 6),
            "active_share": round(float((fed[c].abs() > 0).mean()), 6)}
        for c in fed.columns if float(fed[c].abs().mean()) > 0
    }
    n_q = len(p["quarterly"])
    a_end = float(wk_v7.iloc[-1]) / 10000.0     # native growth multiples
    b_end = float(wk_v34.iloc[-1]) / 10000.0
    w = 0.70
    g7, g34 = a_end - 1.0, b_end - 1.0
    denom = w * g7 + (1 - w) * g34
    characteristics = {
        "n_trades": p["n_trades"],
        "trades_per_quarter_mean": round(p["n_trades"] / n_q, 1),
        "trades_per_quarter_note": (
            "pin JSON carries the total only (no per-quarter split is "
            "pinned); mean = n_trades / 24 quarters"),
        "turnover": {
            "mean_daily_sum_abs_dfrac": round(float(turn_daily.mean()), 4),
            "p95_daily": round(float(turn_daily.quantile(0.95)), 4),
            "max_daily": round(float(turn_daily.max()), 4),
            "basis": ("locked federation matrix (w=0.70, s=1.1) rebuilt via "
                      "eval_fma3_pin.build_locked_matrix — sum over "
                      "instruments of |delta frac| per hour, summed per "
                      "calendar day, averaged over days"),
        },
        "gross_exposure_frac_of_equity": {
            "p50": round(float(gross.quantile(0.50)), 4),
            "p95": round(float(gross.quantile(0.95)), 4),
            "p99": round(float(gross.quantile(0.99)), 4),
            "max": round(float(gross.max()), 4),
            "n_hours": int(len(gross)),
        },
        "per_instrument": inst,
        "n_instruments_active": len(inst),
        "overnight_gold": {
            "source": "hcaps1_analysis.json (H-CAPS-1, measured on hfed1_w70 "
                      "at s=1.0; multiply by s=1.1 for shipped-scale "
                      "fractions — entitlement scales identically, so the "
                      "0-hours-exceeding verdict is scale-invariant)",
            "joint_abs_p50": hcaps["overnight_gold"]["joint_abs_p50"],
            "joint_abs_p95": hcaps["overnight_gold"]["joint_abs_p95"],
            "joint_abs_p99": hcaps["overnight_gold"]["joint_abs_p99"],
            "joint_abs_max": hcaps["overnight_gold"]["joint_abs_max"],
            "entitlement_at_max": hcaps["overnight_gold"]["entitlement_at_max"],
            "hours_exceeding_entitlement":
                hcaps["overnight_gold"]["hours_exceeding_entitlement"],
            "verdict": hcaps["verdict"],
        },
        "sub_book_contribution": {
            "method": ("w-weighted native record-curve growth: share_i = "
                       "w_i*(mult_i - 1) / sum_j w_j*(mult_j - 1); native "
                       "multiples from the parents' NATIVE curves (EUR 10k "
                       "base)"),
            "v7_native_multiple": round(a_end, 3),
            "v34_native_multiple": round(b_end, 3),
            "v7_share": round(w * g7 / denom, 4),
            "v34_share": round((1 - w) * g34 / denom, 4),
        },
    }

    # ---- 6. lever cards (REGISTRY.md decisions) ------------------------------
    w70 = hfed1["grid"]["hfed1_w70"]
    f2a, f2b70 = hfed2["grid"]["f2a_quarterly"], hfed2["grid"]["f2b_band70"]
    s11, s14 = hfed3["grid"]["hfed3_s110"], hfed3["grid"]["hfed3_s140"]
    up20 = rt_pert["surface"]["w_up20"]
    lever_cards = [
        {"id": "FMA3-001", "verdict": "ADOPTED",
         "lever": "Static federation, w = 0.70 v7 share",
         "evidence": (f"Pre-registered grid w in {{.30..70}}: w50/w60/w70 pass "
                      f"all H-FED-1 bars; winner by rule (max Sharpe among "
                      f"passers) w70 = CAGR +{w70['cagr']*100:.2f}% / DD "
                      f"{w70['maxdd_worst']*100:.2f}% / Sharpe "
                      f"{w70['sharpe']:.3f} / negQ 0 (friction "
                      f"{hfed2['base']['static']['friction_cagr_pp']:.1f}pp)"),
         "source": "docs/REGISTRY.md FMA3-001 · hfed1_results.json"},
        {"id": "FMA3-002", "verdict": "DECLINED",
         "lever": "Cross-book rebalancing (quarterly + 3 band cadences)",
         "evidence": (f"All four cadences miss the <=+0.3pp DD bar (F2a "
                      f"+{f2a['delta_cagr_pp_vs_static']:.2f}pp CAGR at "
                      f"+{f2a['delta_dd_pp_vs_static']:.2f}pp DD; band70 "
                      f"{f2b70['delta_cagr_pp_vs_static']:.2f}pp) — "
                      f"rebalancing couples the disjoint troughs it "
                      f"harvests; static w70 stands"),
         "source": "docs/REGISTRY.md FMA3-002 · hfed2_results.json"},
        {"id": "FMA3-C1", "verdict": "NO-OP",
         "lever": "Joint exposure caps on the merged book",
         "evidence": (f"Overnight joint gold p50 "
                      f"{hcaps['overnight_gold']['joint_abs_p50']:.2f}x / p99 "
                      f"{hcaps['overnight_gold']['joint_abs_p99']:.2f}x / max "
                      f"{hcaps['overnight_gold']['joint_abs_max']:.2f}x equity "
                      f"= exactly entitlement, 0 hours exceeding; inherited "
                      f"per-book caps compose correctly — no joint cap needed"),
         "source": "docs/REGISTRY.md FMA3-C1 · hcaps1_analysis.json"},
        {"id": "FMA3-003 + FMA3-RT", "verdict": "ADOPTED",
         "lever": "Global scale s = 1.1 (probe-robust re-pick of s = 1.4)",
         "evidence": (f"Ceiling rule alone gave s=1.4 (CAGR "
                      f"+{s14['cagr']*100:.1f}% / DD "
                      f"{s14['maxdd_worst']*100:.2f}%); red-team perturbation "
                      f"FAILED on the w+20% axis only (dDD "
                      f"+{up20['delta_dd_pp']:.2f}pp) — adjudicated "
                      f"probe-robust rule (ceilings must hold at both ±20% w "
                      f"probes) binds at w_up20 DD "
                      f"{up20['maxdd_worst']*100:.2f}% x 1.1 < 20.9% ⇒ s=1.1, "
                      f"the only fully parent-dominant point (7/7)"),
         "source": ("docs/REGISTRY.md FMA3-003, FMA3-RT · hfed3_results.json "
                    "· redteam/rt_perturbation.json")},
    ]

    # ---- 7. rejected extensions ('stress-tested after' chips) ----------------
    s12, s13 = hfed3["grid"]["hfed3_s120"], hfed3["grid"]["hfed3_s130"]
    f2b60 = hfed2["grid"]["f2b_band60"]
    rejected_extensions = {
        "headline": ("Stress-tested during lock — every richer variant "
                     "rejected with cause, so static w70 @ s=1.1 is the "
                     "frontier"),
        "chips": [
            {"name": "Quarterly rebalance (F2a)",
             "reason": (f"+{f2a['delta_cagr_pp_vs_static']:.1f}pp CAGR costs "
                        f"+{f2a['delta_dd_pp_vs_static']:.2f}pp DD — over the "
                        f"+0.3pp bar")},
            {"name": "Band rebalance B_up .60/.65 (F2b)",
             "reason": (f"degenerate at w70 (418 events ≈ every 5d); "
                        f"+{f2b60['delta_dd_pp_vs_static']:.2f}pp DD — over "
                        f"the bar")},
            {"name": "Band rebalance B_up .70 (F2b)",
             "reason": (f"{f2b70['delta_cagr_pp_vs_static']:.2f}pp CAGR — "
                        f"pays nothing")},
            {"name": "s = 1.2 aggressive frontier",
             "reason": (f"DD {s12['maxdd_worst']*100:.2f}% at locked w, but "
                        f"not probe-robust at w+20%")},
            {"name": "s = 1.3 aggressive frontier",
             "reason": (f"DD {s13['maxdd_worst']*100:.2f}% at locked w, but "
                        f"not probe-robust at w+20%")},
            {"name": "s = 1.4 ceiling-rule pick",
             "reason": (f"CAGR +{s14['cagr']*100:.0f}% mirage — perturbation "
                        f"FAIL (w+20% dDD +{up20['delta_dd_pp']:.1f}pp) "
                        f"adjudicated it down to s=1.1")},
            {"name": "Off-grid w80",
             "reason": ("Sharpe still rising at the grid edge — NOT tested; "
                        "the pre-registered grid is binding")},
        ],
        "perturbation_adjudication": {
            "verdict": rt_pert["verdict"],
            "reason": rt_pert["reason"],
            "w_up20": {"dDD_pp": round(up20["delta_dd_pp"], 2),
                       "dSharpe": round(up20["delta_sharpe"], 3),
                       "maxdd_worst": round(up20["maxdd_worst"], 4),
                       "fragile": up20["fragile"]},
            "w_down20": {
                "dDD_pp": round(
                    rt_pert["surface"]["w_down20"]["delta_dd_pp"], 2),
                "fragile": rt_pert["surface"]["w_down20"]["fragile"]},
            "consequence": ("ship scale re-picked with the probe-robustness "
                            "constraint ⇒ s=1.1 (REGISTRY FMA3-RT)"),
        },
    }

    # ---- 8. forward one-shot block -------------------------------------------
    fw = fwd["metrics"]["federation_window"]
    forward = {
        "label": fwd["label"],
        "verdict": fwd["verdict"],
        "status": "2026H1 holdout CONSUMED (2026-07-10)",
        "window": "2026-01-01 → 2026-04-30 (server), fresh EUR 10k seed, "
                  "Duka feed, 14-symbol coverage, USA500 proxies USTEC",
        "bars": [
            {"id": "F1", "bar": fwd["bars"]["F1"]["bar"],
             "value": round(fwd["bars"]["F1"]["value"], 4),
             "display": f"{fwd['bars']['F1']['value']*100:.2f}%",
             "pass": fwd["bars"]["F1"]["pass"]},
            {"id": "F2", "bar": fwd["bars"]["F2"]["bar"],
             "value": round(fwd["bars"]["F2"]["value"], 4),
             "display": f"+{fwd['bars']['F2']['value']*100:.2f}%",
             "pass": fwd["bars"]["F2"]["pass"]},
            {"id": "F3", "bar": fwd["bars"]["F3"]["bar"],
             "value": fwd["bars"]["F3"]["value"],
             "display": "stop-outs 0, cap-binds 0",
             "pass": fwd["bars"]["F3"]["pass"]},
            {"id": "F4", "bar": fwd["bars"]["F4"]["bar"],
             "value": {k: round(v, 4)
                       for k, v in fwd["bars"]["F4"]["value"].items()},
             "display": (f"v7 +{fwd['bars']['F4']['value']['v7_native']*100:.2f}%, "
                         f"v3.4 +{fwd['bars']['F4']['value']['v34_native']*100:.2f}%"),
             "pass": fwd["bars"]["F4"]["pass"]},
        ],
        "window_metrics": {
            "window_return": round(fw["window_return"], 6),
            "final_equity": round(fw["final_equity"], 2),
            "maxdd_worst": round(fw["maxdd_worst"], 6),
            "maxdd_close": round(fw["maxdd_close"], 6),
            "sharpe_daily_annualized": round(fw["sharpe_daily_annualized"], 4),
            "n_days": fw["n_days"],
        },
        "monthly_path": {k: round(v, 6)
                         for k, v in fw["monthly_returns"].items()},
        "sub_v34_monthly_path": {
            k: round(v, 6) for k, v in
            fwd["metrics"]["sub_v34_window"]["monthly_returns"].items()},
        "margin_envelope": {
            "max_margin_over_balance": round(
                fwd["metrics"]["federation_events"]
                ["max_margin_over_balance"], 4),
            "margin_cap": 0.90,
            "min_margin_level": round(
                fwd["metrics"]["federation_events"]["min_margin_level"], 3),
            "stopout_level": 0.50,
        },
        "caveats": fwd["caveats"],
        "source": "research/outputs/forward_oneshot.json · FORWARD_ONESHOT.md",
    }

    # ---- assemble -------------------------------------------------------------
    data = {
        "meta": {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "builder": "scripts/build_package_data.py (engine-free: pinned "
                       "artifacts + locked-matrix math only)",
            "version": pin["version"],
            "config_hash": pin["config_hash"],
            "locked": pin["locked"],
            "sample": pin["sample"],
            "engine_of_record": pin["engine"],
            "disclosure": ("All numbers are in-sample (IC 2020-25); the "
                           "2026H1 one-shot is consumed; MT5 real-tick + "
                           "live demo are the remaining falsification tests."),
            "sources": [
                "research/outputs/fma3_v1_pin.json",
                "research/outputs/fma3_v1_pin_curve.parquet",
                "research/outputs/composite_benchmark.json",
                "research/outputs/hfed1_results.json",
                "research/outputs/hfed2_results.json",
                "research/outputs/hfed3_results.json",
                "research/outputs/hcaps1_analysis.json",
                "research/outputs/redteam/rt_perturbation.json",
                "research/outputs/forward_oneshot.json",
                "research/baselines/fma2/v34_s10_pin_curve.parquet",
                "research/outputs/v7_book_equity_1m.parquet",
                "docs/REGISTRY.md",
            ],
        },
        "headline": {
            "cagr": p["cagr"], "maxdd_worst": p["maxdd_worst"],
            "maxdd_close": p["maxdd_close"], "sharpe": p["sharpe"],
            "crisis_tail": p["crisis_tail"],
            "final_equity": p["final_equity"], "n_trades": p["n_trades"],
            "neg_years": len(p["neg_years"]),
            "neg_quarters": len(p["neg_quarters"]),
            "breach_close": pin["breach"]["breach_close"],
            "breach_worst": breach_worst,
            "median_dd_worst": pin["breach"]["median_dd_worst"],
            "p95_dd_worst": pin["breach"]["p95_dd_worst"],
        },
        "weekly_equity": {
            "note": "close-mark, W-resampled last, EUR 10k base",
            "fma3_v1": _series_pairs(wk_fed, 2),
            "v7_native_band": _series_pairs(wk_v7, 2),  # NATIVE band-engine curve (532k), not the record execution (493k)
            "v34_s10_record": _series_pairs(wk_v34, 2),
        },
        "daily_drawdown_worst": {
            "note": ("dd_t = 1 - worst_t/cummax(close_t) at 1m, daily max — "
                     "engine worst-mark convention; max equals the pinned "
                     "15.73%"),
            "series": _series_pairs(dd_daily, 6),
        },
        "gates": {
            "owner": owner_gates,
            "composite": {
                "basis": cg["basis"],
                "dimensions": composite_dims,
                "all_dominant": all(t["pass"] for t in composite_dims),
            },
        },
        "returns": {
            "yearly": {k: round(v, 6) for k, v in p["yearly"].items()},
            "quarterly": {k: round(v, 6) for k, v in p["quarterly"].items()},
            "monthly": monthly,
        },
        "characteristics": characteristics,
        "lever_cards": lever_cards,
        "rejected_extensions": rejected_extensions,
        "forward": forward,
    }
    out_path = OUT / "package_data.json"
    out_path.write_text(json.dumps(data, indent=1))

    # ---- weekly preview for the writers ---------------------------------------
    prev_lines = ["FMA3 v1.0 weekly equity preview (close-mark, W last, "
                  "EUR 10k base) — full series in package_data.json",
                  f"{'week':<12}{'fma3_v1':>14}{'v7_r8':>14}{'v34_s10':>14}"]
    def _row(i: int) -> str:
        v7v = wk_v7.iloc[i] if i < len(wk_v7) else float("nan")
        v34v = wk_v34.iloc[i] if i < len(wk_v34) else float("nan")
        return (f"{wk_fed.index[i].strftime('%Y-%m-%d'):<12}"
                f"{wk_fed.iloc[i]:>14,.2f}{v7v:>14,.2f}{v34v:>14,.2f}")

    prev_lines += [_row(i) for i in range(3)]
    prev_lines.append(f"{'...':<12}{'...':>14}{'...':>14}{'...':>14}")
    prev_lines += [_row(i) for i in range(len(wk_fed) - 3, len(wk_fed))]
    prev_lines.append(f"n_weeks={len(wk_fed)}  final fma3={wk_fed.iloc[-1]:,.2f} "
                      f"v7={wk_v7.iloc[-1]:,.2f} v34={wk_v34.iloc[-1]:,.2f}")
    (OUT / "package_data_weekly_preview.txt").write_text(
        "\n".join(prev_lines) + "\n")

    # ---- sanity prints ---------------------------------------------------------
    print(f"[data] package_data.json written "
          f"({out_path.stat().st_size/1024:.0f} KiB, {time.time()-t0:.0f}s)")
    print(f"  weekly points: fma3 {len(wk_fed)}, v7 {len(wk_v7)}, "
          f"v34 {len(wk_v34)} "
          f"({wk_fed.index[0].date()} .. {wk_fed.index[-1].date()})")
    print(f"  weekly equity range: {wk_fed.min():,.0f} .. {wk_fed.max():,.0f} "
          f"(final {wk_fed.iloc[-1]:,.2f} vs pin "
          f"{p['final_equity']:,.2f})")
    print(f"  daily dd points: {len(dd_daily)}, max "
          f"{dd_daily.max()*100:.4f}% (pin {p['maxdd_worst']*100:.4f}%), "
          f"median {dd_daily.median()*100:.2f}%")
    print(f"  monthly returns: {len(monthly)} months, range "
          f"{min(monthly.values())*100:+.2f}% .. "
          f"{max(monthly.values())*100:+.2f}%, compound -> "
          f"{growth*10000:,.0f}")
    print(f"  gates: owner {sum(t['pass'] for t in owner_gates)}/6, "
          f"composite {sum(t['pass'] for t in composite_dims)}/7 dominant")
    ch = characteristics
    print(f"  matrix: {fed.shape[0]} hours x {fed.shape[1]} cols, "
          f"{ch['n_instruments_active']} active; turnover mean daily "
          f"{ch['turnover']['mean_daily_sum_abs_dfrac']:.3f} "
          f"(p95 {ch['turnover']['p95_daily']:.3f})")
    g = ch["gross_exposure_frac_of_equity"]
    print(f"  gross |frac| p50/p95/p99/max: {g['p50']:.3f}/{g['p95']:.3f}/"
          f"{g['p99']:.3f}/{g['max']:.3f}")
    sc = ch["sub_book_contribution"]
    print(f"  sub-book shares: v7 {sc['v7_share']:.1%} / "
          f"v34 {sc['v34_share']:.1%} "
          f"(native multiples {sc['v7_native_multiple']}x / "
          f"{sc['v34_native_multiple']}x)")
    print(f"  lever cards: {len(lever_cards)}; rejected chips: "
          f"{len(rejected_extensions['chips'])}; forward bars: "
          f"{sum(b['pass'] for b in forward['bars'])}/4 PASS "
          f"({forward['verdict']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
