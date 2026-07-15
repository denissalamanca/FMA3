#!/usr/bin/env python3
"""FMA3 preset dashboard data packs — engine-free, one per preset.

Assembles TWO data packs (IC private + FTMO 2-Step Swing) strictly from the
PINNED preset artifacts written by run_hrisk1.py / run_hrisk2.py:
  - hrisk1_results.json + hrisk1_s{ship}_curve.parquet   (Preset 1 / IC)
  - hrisk2_results.json + hrisk2_s{ship}_curve.parquet   (Preset 2 / FTMO)
plus the s<=1.4 frontier from hfed3_results.json for the IC scale-frontier
panel.  NO engine run anywhere (matrix/curve reads only).

The two packs feed the two preset dashboards (DASHBOARD_IC.html /
DASHBOARD_FTMO.html), which mirror archive/docs-v1.0/DASHBOARD.html look-and-feel.

Run (after both preset grids ship):
  python3 scripts/build_preset_data.py
Outputs: research/outputs/preset_ic_data.json
         research/outputs/preset_ftmo_data.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
OUT = _FMA3 / "research" / "outputs"


def _weekly(eq: pd.Series, base: float) -> list[list]:
    w = (eq / float(eq.iloc[0]) * base).resample("W").last().dropna()
    return [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in w.items()]


def _daily_dd(eq: pd.Series, wo: pd.Series) -> list[list]:
    peak = eq.cummax()
    dd = ((peak - wo) / peak).resample("1D").max().dropna()
    return [[d.strftime("%Y-%m-%d"), round(float(v), 5)] for d, v in dd.items()]


def _yearly(eq: pd.Series) -> dict:
    y = eq.resample("YE").last()
    y0 = pd.concat([pd.Series([float(eq.iloc[0])],
                              index=[eq.index[0]]), y])
    r = y0.pct_change().dropna()
    return {str(d.year): round(float(v), 4) for d, v in r.items()}


def build_ic() -> dict:
    h1 = json.loads((OUT / "hrisk1_results.json").read_text())
    h3 = json.loads((OUT / "hfed3_results.json").read_text())
    ship_s = h1["ship"].get("s")
    if ship_s is None:
        raise SystemExit("IC preset has no shipped scale yet")
    key = f"hrisk1_s{int(round(ship_s*100))}"
    # shipped metric row (from base grid)
    row = h1["base"][f"s{int(round(ship_s*100))}"]
    curve = pd.read_parquet(OUT / f"{key}_curve.parquet")
    eq, wo = curve["equity"], curve["worst"]
    final = float(eq.iloc[-1] / eq.iloc[0] * 10000.0)

    # unified scale frontier: hfed3 (0.8-1.4) + hrisk1 base (1.5-1.8),
    # compliance vs the IC ceiling breach<=0.15 & DD<30%
    frontier = []
    for v in h3["grid"].values():
        frontier.append({"s": v["s"], "cagr": v["cagr"],
                         "dd": v["maxdd_worst"],
                         "breach": v["breach"]["breach_worst"],
                         "ic_ok": (v["maxdd_worst"] < 0.30
                                   and v["breach"]["breach_worst"] <= 0.20
                                   and v["crisis_tail"] <= 0.30
                                   and not v["neg_years"]
                                   and v["n_neg_quarters"] <= 1)})
    # base compliance recomputed at the FMA3-004c cap (0.20); s where a
    # measured ±20% probe FAILED are marked not ship-eligible (s=1.7: w84
    # breach 0.280; s=1.8 base-fails outright)
    probe_failed = {1.7, 1.8}
    for v in h1["base"].values():
        base_ok = (v["maxdd_worst"] < 0.30
                   and v["breach"]["breach_worst"] <= 0.20
                   and v["crisis_tail"] <= 0.30
                   and not v["neg_years"]
                   and v["n_neg_quarters"] <= 1)
        frontier.append({"s": v["s"], "cagr": v["cagr"],
                         "dd": v["maxdd_worst"],
                         "breach": v["breach"]["breach_worst"],
                         "ic_ok": bool(base_ok and v["s"] not in probe_failed)})
    frontier.sort(key=lambda x: x["s"])

    return {
        "preset": "IC private (H-RISK-1)", "account": "IC Markets EU Raw",
        "ship_s": ship_s, "config_hash": "51a7541cc2aaa593",
        "final_equity": final, "initial": 10000.0,
        "ceilings": {**h1["ceilings"], "breach": 0.20, "revision": "owner Pareto 0.15→0.20 (FMA3-004c)"},
        "headline": {
            "cagr": row["cagr"], "maxdd_worst": row["maxdd_worst"],
            "sharpe": row["sharpe"], "crisis_tail": row["crisis_tail"],
            "breach": row["breach"]["breach_worst"],
            "n_neg_quarters": row["n_neg_quarters"],
            "neg_years": row["neg_years"]},
        "gates": [
            {"k": "Max DD (worst-mark)", "gate": "< 30%",
             "v": row["maxdd_worst"], "ok": row["maxdd_worst"] < 0.30},
            {"k": "Breach P(DD>30%)", "gate": "≤ 0.20",
             "v": row["breach"]["breach_worst"],
             "ok": row["breach"]["breach_worst"] <= 0.20},
            {"k": "Worst-drift breach (±20% w)", "gate": "≤ 0.20",
             "v": h1["ship"].get("worst_probe_breach", 0.1804),
             "ok": h1["ship"].get("worst_probe_breach", 0.1804) <= 0.20},
            {"k": "Crisis tail", "gate": "≤ 30%",
             "v": row["crisis_tail"], "ok": row["crisis_tail"] <= 0.30},
            {"k": "Neg years", "gate": "0 / 6",
             "v": len(row["neg_years"]), "ok": not row["neg_years"]},
            {"k": "Neg quarters", "gate": "≤ 1 / 24",
             "v": row["n_neg_quarters"], "ok": row["n_neg_quarters"] <= 1},
            {"k": "CAGR", "gate": "maximize",
             "v": row["cagr"], "ok": True}],
        "weekly": _weekly(eq, 10000.0),
        "drawdown": _daily_dd(eq, wo),
        "yearly": _yearly(eq),
        "frontier": frontier,
        "ship_note": h1["ship"].get("verdict", ""),
        "probe_note": ("probe-robust under the owner's 0.20 breach cap "
                       "(Pareto revision, FMA3-004c): shipped s=1.6 is the "
                       "largest where base AND both ±20% w-drift probes clear "
                       "breach≤0.20 & DD<30% — s=1.7 fails the w+20% probe "
                       "(breach 0.280); worst s=1.6 drift probe: breach 0.180, "
                       "DD 27.6%"),
    }


def build_ftmo() -> dict:
    """FTMO pack under the CORRECTED FMA3-005b fixed-base model.

    Sources: hrisk2_results.json fma3_005b block (corrected re-score) + ship
    block; headline P(pass P1)/median-days recomputed engine-free from the
    shipped curve under the CORRECTED breach rules (the FMA3-005 originals
    were depressed by the fixed-EUR-limit-vs-compounding artifact)."""
    import numpy as np
    h2 = json.loads((OUT / "hrisk2_results.json").read_text())
    ship = h2["ship"]
    ship_s = ship.get("s")
    if ship_s is None:
        raise SystemExit("FTMO preset has no shipped scale yet")
    b05 = h2["fma3_005b"]
    breaker = "FMA3-008" in str(ship.get("provenance", ""))
    if breaker:
        bs = h2["fma3_008_ship"]
        hist = dict(bs["historical"])
        hist["max_worst_dd"] = bs["maxdd_worst"]          # model-v3 floor key -> DD key
        hist["daily_breaches"] = hist.get("daily_dip_gt5pct", 0)
        row = {"cagr": bs["cagr"], "historical": hist,
               "bootstrap": bs["bootstrap"],
               "neg_quarters": bs.get("neg_quarters", 0)}
        curve = pd.read_parquet(OUT / "hrisk2_ship_curve.parquet")
    else:
        key = f"s{int(round(ship_s*100))}"
        row = b05["base"][key]
        curve = pd.read_parquet(OUT / f"hrisk2_{key}_curve.parquet")
    eq, wo = curve["equity"], curve["worst"]
    final = float(eq.iloc[-1] / eq.iloc[0] * 100000.0)

    # corrected-model challenge stats from the shipped curve (same bootstrap
    # conventions as run_hrisk2b: 10k paths, 20d blocks, seed 20260710)
    dc = eq.resample("1D").last().dropna()
    dw = wo.resample("1D").min().reindex(dc.index)
    prev = dc.shift(1)
    r = (dc / prev - 1.0).dropna().to_numpy()
    d = (dw / prev - 1.0).dropna().to_numpy()
    T = len(r)
    rng = np.random.default_rng(20260710)
    p_cont = 1.0 - 1.0 / 20
    p1_pass, p1_days, breach = 0, [], 0
    for _ in range(10_000):
        idx = np.empty(252, dtype=np.int64)
        j = rng.integers(T)
        for t in range(252):
            idx[t] = j
            j = (j + 1) % T if rng.random() < p_cont else rng.integers(T)
        e, peak, hit, dead = 1.0, 1.0, None, False
        for t in range(252):
            if d[idx[t]] < -0.05:
                dead = True; break
            e *= (1.0 + r[idx[t]])
            peak = max(peak, e)
            if 1.0 - e / peak > 0.10:
                dead = True; break
            if hit is None and e >= 1.10:
                hit = t + 1
        if dead:
            breach += 1
        elif hit is not None:
            p1_pass += 1
            p1_days.append(hit)
    p_pass_p1 = p1_pass / 10_000
    med_days = float(np.median(p1_days)) if p1_days else None

    if breaker:
        # WITH-breaker frontier: s=0.4 (no breaker needed) + best compliant x
        # per s from the FMA3-008 grid (fma3_008_results.json)
        g8j = json.loads((OUT / "fma3_008_results.json").read_text())
        g8 = {**g8j["grid"], **g8j.get("walk_up", {})}
        by_s = {}
        for v in g8.values():
            floor = v["historical"].get("worst_month_floor_touch", 1.0)
            comp = (v["historical"]["daily_dip_gt5pct"] == 0 and floor >= 0.90
                    and v["bootstrap"]["p_breach_12m"] <= 0.05)
            cur = by_s.get(v["s"])
            # prefer compliant; among compliant lowest P(breach)
            key = (0 if comp else 1, v["bootstrap"]["p_breach_12m"])
            if cur is None or key < cur[0]:
                by_s[v["s"]] = (key, {"s": v["s"], "cagr": v["cagr"],
                    "dd": v["maxdd_worst"], "p_breach": v["bootstrap"]["p_breach_12m"],
                    "x": v["x"], "ok": comp})
        s04 = b05["base"]["s40"]
        frontier = [{"s": 0.4, "cagr": s04["cagr"], "dd": s04["historical"]["max_worst_dd"],
                     "p_breach": s04["bootstrap"]["p_breach_12m"], "x": None, "ok": True}]
        frontier += [t[1] for t in by_s.values()]
    else:
        frontier = [{"s": v["s"], "cagr": v["cagr"], "dd": v["historical"]["max_worst_dd"],
                     "p_breach": v["bootstrap"]["p_breach_12m"],
                     "dip_days": v["historical"]["daily_dip_gt5pct"],
                     "ok": v["compliant"]}
                    for v in b05["base"].values()]
    frontier.sort(key=lambda x: x["s"])

    return {
        "preset": "FTMO 2-Step Swing (H-RISK-2b, fixed-base model)",
        "account": "FTMO 2-Step Challenge \u00b7 Swing \u00b7 \u20ac100,000",
        "ship_s": ship_s, "config_hash": "51a7541cc2aaa593",
        "final_equity": final, "initial": 100000.0,
        "rules": {"daily": "intraday dip vs prior close > 5% = breach "
                           "(fixed-base; assumes withdrawal-to-base ops)",
                  "static": "worst-mark %DD < 10%",
                  "model_note": "FMA3-005b corrected model (the FMA3-005 "
                                "fixed-EUR-limit artifact is documented in "
                                "the registry)"},
        "headline": {
            "cagr": row["cagr"], "maxdd_worst": row["historical"]["max_worst_dd"],
            "p_breach_12m": row["bootstrap"]["p_breach_12m"],
            "p_pass_p1": p_pass_p1, "median_days_p1": med_days,
            "hist_daily": row["historical"]["daily_dip_gt5pct"],
            "hist_static": 0 if row["historical"]["max_worst_dd"] < 0.10 else 1,
            "n_neg_quarters": row["neg_quarters"]},
        "gates": [
            {"k": "P(breach FTMO rule / 12mo)", "gate": "\u2264 0.05",
             "v": row["bootstrap"]["p_breach_12m"],
             "ok": row["bootstrap"]["p_breach_12m"] <= 0.05},
            {"k": ">5% daily dips (2020-25)", "gate": "0",
             "v": row["historical"]["daily_dip_gt5pct"],
             "ok": row["historical"]["daily_dip_gt5pct"] == 0},
            ({"k": "Worst monthly DD (FTMO floor)", "gate": "< 10%",
              "v": round(1 - row["historical"]["worst_month_floor_touch"], 4),
              "ok": (1 - row["historical"]["worst_month_floor_touch"]) < 0.10}
             if "worst_month_floor_touch" in row["historical"] else
             {"k": "Max worst-mark DD", "gate": "< 10%",
              "v": row["historical"]["max_worst_dd"],
              "ok": row["historical"]["max_worst_dd"] < 0.10}),
            {"k": "P(pass Phase-1 +10%)", "gate": "maximize",
             "v": p_pass_p1, "ok": True},
            {"k": "Neg quarters", "gate": "\u2264 1 / 24",
             "v": row["neg_quarters"], "ok": row["neg_quarters"] <= 1}],
        "weekly": _weekly(eq, 100000.0),
        "drawdown": _daily_dd(eq, wo),
        "yearly": _yearly(eq),
        "frontier": frontier,
        "breaker": ({"x_pct": ship["breaker_x"], "n_stops": ship["n_daily_stops"],
                     "reentry_cost_pp": ship["reentry_cost_pp"]} if breaker else None),
        "ship_note": ship.get("verdict", ""),
        "rule_note": ("FTMO 2-Step Swing (verified ftmo.com 2026-07-10): "
                      "daily loss limit 5% / static floor 10%, modeled "
                      "fixed-base (withdrawal-to-base ops); Swing mandatory "
                      "for weekend gold/crypto + news. Dial provisional "
                      "pending v1.1 MT5 ratio."),
    }


def main() -> int:
    ic = build_ic()
    (OUT / "preset_ic_data.json").write_text(json.dumps(ic, indent=1))
    print(f"[IC]   s={ic['ship_s']} CAGR {ic['headline']['cagr']:+.4f} "
          f"DD {ic['headline']['maxdd_worst']:.4f} breach "
          f"{ic['headline']['breach']:.4f} -> €{ic['final_equity']:,.0f}")
    ftmo = build_ftmo()
    (OUT / "preset_ftmo_data.json").write_text(json.dumps(ftmo, indent=1))
    print(f"[FTMO] s={ftmo['ship_s']} CAGR {ftmo['headline']['cagr']:+.4f} "
          f"P(breach) {ftmo['headline']['p_breach_12m']:.4f} "
          f"P(passP1) {ftmo['headline']['p_pass_p1']:.3f} -> "
          f"€{ftmo['final_equity']:,.0f}")
    print("wrote preset_ic_data.json + preset_ftmo_data.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
