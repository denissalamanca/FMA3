#!/usr/bin/env python3
"""FMA3-008: H-FTMO-1 daily circuit breaker — identity gate, x-grid, verdict.

Pre-registered: research/protocol/FTMO_CAMPAIGN.md (FMA3-008) + ROADMAP.md
H-FTMO-1 (bars committed before any number). Engine hook:
engine/record_engine_ext.py::daily_stop_x (see its "FTMO DAILY CIRCUIT
BREAKER" docstring section for the exact semantics incl. gap-through).
Scoring: scripts/ftmo_model_v3.py::score_v3 UNCHANGED (the FMA3-009
rule-accurate model — the sole scorer for every x-grid cell).

PROCEDURE (in order, all engine passes SEQUENTIAL)
--------------------------------------------------
0. IDENTITY GATE (non-negotiable, before any x-grid pass): on the FTMO ship
   config (static fed w=0.70, s=0.4, initial 100k) BOTH
     (a) run_record_ext(daily_stop_x=None)   [untouched _run_chunk kernel]
     (b) run_record_ext(daily_stop_x=10.0)   [_run_chunk_stop, never fires]
   must reproduce the saved no-stop curve hrisk2_s40_curve.parquet
   BIT-IDENTICALLY (np.array_equal on equity AND worst, index included).
   Any mismatch aborts the experiment — fix, never relax.
1. X-GRID: (w=0.70) x s in {0.5, 0.6, 0.7} x x in {3.0, 3.5, 4.0}% — 9
   passes. Per cell: full score_v3 blocks, trigger count (n_daily_stops),
   re-entry cost in pp CAGR vs the no-breaker cell (FMA3-009 base block),
   residual >5%-dip days in BOTH frames (v3 month-reset historical block +
   raw prev-day-close frame = the gap-through residual).
   s=0.4 needs no breaker (already compliant); the breaker's value is
   unlocking HIGHER s.
2. WALK-UP: if any cell is v3-compliant, try s in {0.8, 0.9} at the best
   compliant cell's x, stopping at the first non-compliant s. (s=0.9 has no
   saved no-breaker cell; a no-breaker reference pass is run only if s=0.9
   is reached, so its re-entry cost is measured against a real cell.)
3. PROBE WALK at the best compliant (s, x) — both +-20% w probes (w56, w84)
   with the breaker armed, full walk-down over the compliant cell list in
   descending CAGR order per the FMA3-005c standing amendment (no
   truncation).
4. VERDICT vs the pre-registered bar (FTMO_CAMPAIGN.md): the best
   probe-robust breaker point must beat the FMA3-009 ship (s=0.4, +30.7%
   gross CAGR) by >= +8pp gross CAGR at P(breach 12m) <= 0.05.
   ADOPT -> re-ship + guardian-EA module goes into the unified EA.
   DECLINE -> honest record; no guardian EA is built.
5. hrisk2_results.json: fma3_008 block always; ship block ONLY on ADOPT.

Run: python3 scripts/run_hftmo1.py   (~85 min: up to ~16 engine passes)
Log: research/outputs/ftmo_campaign.log (append, flush).
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
sys.path.insert(0, str(_FMA3 / "scripts"))

import record_engine_ext as RX  # noqa: E402
from run_hrisk1 import static_blend  # noqa: E402
from ftmo_model_v3 import score_v3  # noqa: E402

W_LOCKED, W_PROBES = 0.70, (0.56, 0.84)
S_GRID = (0.5, 0.6, 0.7)
S_WALKUP = (0.8, 0.9)
X_GRID = (3.0, 3.5, 4.0)
INITIAL = 100_000.0
SHIP_CAGR_009 = None            # loaded from hrisk2_results.json ship block
BAR_PP = 0.08                   # >= +8pp gross CAGR over the FMA3-009 ship
IC_CAGR = 1.702                 # FMA3-004c IC ship, on-account CAGR
LOG = _FMA3 / "research" / "outputs" / "ftmo_campaign.log"
OUT = RX.PATHS.OUTPUTS


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [FMA3-008] {msg}"
    print(line, flush=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")
        fh.flush()


def raw_dip_days(eq: pd.Series, wo: pd.Series, lim: float = 0.05) -> int:
    """Days whose worst mark dips > lim vs previous server-day close, on the
    RAW (compounding) curve — the engine's own trigger frame. With the
    breaker armed, any such day is a gap-through past the FTMO 5% line."""
    dc = eq.resample("1D").last().dropna()
    dw = wo.resample("1D").min().reindex(dc.index)
    d = (dw / dc.shift(1) - 1.0).dropna()
    return int((d < -lim).sum())


def fmt(sc: dict) -> str:
    h, b, c = sc["historical"], sc["bootstrap"], sc["challenge"]
    return (f"dip>5%base {h['daily_dip_gt5pct']} | monthFloorLo "
            f"{h['worst_month_floor_touch']:.4f} | P(breach12m) "
            f"{b['p_breach_12m']:.4f} | P(passP1) {c['p_pass_p1']:.3f} "
            f"med {c['median_days_p1']} | negY {sc['neg_years']} negQ "
            f"{sc['neg_quarters']} | "
            f"{'COMPLIANT' if sc['compliant'] else 'fails'}")


def run_cell(fed: pd.DataFrame, s: float, x: float | None, label: str,
             nobreak_cagr: float | None) -> dict:
    """One engine pass (breaker at x% or None) + v3 score + FMA3-008 extras."""
    cp = OUT / f"{label}_curve.parquet"
    r = RX.run_record_ext(fed * s, label=label, verbose=False,
                          initial=INITIAL, daily_stop_x=x,
                          run_bootstrap=False)
    eq, wo = r["curves"]["equity"], r["curves"]["worst"]
    pd.DataFrame({"equity": eq, "worst": wo}).to_parquet(cp)
    sc = score_v3(eq, wo)
    row = {"s": s, "x": x, "cagr": r["cagr"],
           "maxdd_worst": r["maxdd_worst"],
           "sharpe": r["sharpe"],
           "final_equity": r["final_equity"],
           "n_triggers": r["n_daily_stops"],
           "nobreak_cagr": nobreak_cagr,
           "reentry_cost_pp": (None if nobreak_cagr is None
                               else (nobreak_cagr - r["cagr"]) * 100.0),
           "raw_dip_days_gt5pct": raw_dip_days(eq, wo),
           **sc}
    cost = ("n/a" if row["reentry_cost_pp"] is None
            else f"{row['reentry_cost_pp']:+.2f}pp")
    log(f"{label}: CAGR {r['cagr']:+.4f} (cost {cost}) | triggers "
        f"{r['n_daily_stops']} | rawDip>5% {row['raw_dip_days_gt5pct']} | "
        f"DDw {r['maxdd_worst']:.4f} | {fmt(sc)}")
    return row


def main() -> int:
    t0 = time.time()
    res = json.loads((OUT / "hrisk2_results.json").read_text())
    base009 = res["fma3_009"]["base"]
    ship_cagr = float(res["ship"]["cagr"])          # FMA3-009 ship s=0.4
    bar_cagr = ship_cagr + BAR_PP
    log("start — H-FTMO-1 daily circuit breaker (engine hook daily_stop_x)")
    log(f"bar: probe-robust breaker CAGR >= {bar_cagr:+.4f} "
        f"(FMA3-009 ship {ship_cagr:+.4f} + 8pp) at P(breach12m) <= 0.05")

    b08 = {"hook": "record_engine_ext.daily_stop_x (flatten at day-anchor "
                   "-x% on minute worst mark, worst-side prices + "
                   "commission, halt to next server day; gap-through "
                   "truncates, not eliminates)",
           "model": "ftmo_model_v3.score_v3 (FMA3-009, unchanged)",
           "gate": {}, "grid": {}, "walkup": {}, "probes": {},
           "verdict": None}

    # ---- 0. IDENTITY GATE ------------------------------------------------
    ref = pd.read_parquet(OUT / "hrisk2_s40_curve.parquet")
    fed70 = static_blend(W_LOCKED)
    for tag, xval in (("none", None), ("x10", 10.0)):
        r = RX.run_record_ext(fed70 * 0.4, label=f"hftmo1_gate_{tag}",
                              verbose=False, initial=INITIAL,
                              daily_stop_x=xval, run_bootstrap=False)
        eq, wo = r["curves"]["equity"], r["curves"]["worst"]
        idx_ok = eq.index.equals(ref.index)
        eq_ok = idx_ok and np.array_equal(eq.to_numpy(),
                                          ref["equity"].to_numpy())
        wo_ok = idx_ok and np.array_equal(wo.to_numpy(),
                                          ref["worst"].to_numpy())
        ok = bool(eq_ok and wo_ok)
        b08["gate"][tag] = {"daily_stop_x": xval, "index_equal": bool(idx_ok),
                            "equity_bit_identical": bool(eq_ok),
                            "worst_bit_identical": bool(wo_ok),
                            "n_triggers": r["n_daily_stops"], "pass": ok}
        log(f"GATE daily_stop_x={xval}: index {idx_ok} | equity bit-id "
            f"{eq_ok} | worst bit-id {wo_ok} | triggers "
            f"{r['n_daily_stops']} | {'PASS' if ok else 'FAIL'}")
        if not ok:
            b08["verdict"] = "ABORTED — identity gate FAILED (fix, never relax)"
            res["fma3_008"] = b08
            (OUT / "hrisk2_results.json").write_text(
                json.dumps(res, indent=1, default=str))
            log("identity gate FAILED — experiment aborted before any "
                "x-grid number")
            return 1
    log(f"identity gate PASSED both paths ({time.time()-t0:.0f}s)")

    # ---- 1. X-GRID ---------------------------------------------------------
    nobreak = {round(v["s"], 2): float(v["cagr"]) for v in base009.values()}
    for s in S_GRID:
        for x in X_GRID:
            lbl = f"hftmo1_s{int(round(s*100))}_x{int(round(x*10))}"
            b08["grid"][lbl] = run_cell(fed70, s, x, lbl, nobreak.get(s))

    # ---- 2. WALK-UP --------------------------------------------------------
    cells = dict(b08["grid"])
    compliant = [k for k, v in cells.items() if v["compliant"]]
    if compliant:
        best = max(compliant, key=lambda k: cells[k]["cagr"])
        best_x = cells[best]["x"]
        log(f"best compliant grid cell: {best} (s={cells[best]['s']}, "
            f"x={best_x}) — walking UP at x={best_x}")
        for s in S_WALKUP:
            if s not in nobreak:
                # measure the no-breaker reference cell first (honest cost)
                lbl0 = f"hftmo1_s{int(round(s*100))}_nobreak"
                row0 = run_cell(fed70, s, None, lbl0, None)
                nobreak[s] = row0["cagr"]
                b08["walkup"][lbl0] = row0
            lbl = f"hftmo1_s{int(round(s*100))}_x{int(round(best_x*10))}"
            row = run_cell(fed70, s, best_x, lbl, nobreak[s])
            b08["walkup"][lbl] = row
            cells[lbl] = row
            if not row["compliant"]:
                log(f"walk-up stops: s={s} non-compliant at x={best_x}")
                break
    else:
        log("NO compliant grid cell — walk-up skipped")

    # ---- 3. PROBE WALK (full walk-down, FMA3-005c standing amendment) ------
    cand = sorted((k for k, v in cells.items() if v["compliant"]),
                  key=lambda k: cells[k]["cagr"], reverse=True)
    log(f"probe walk-down order (compliant cells by CAGR): {cand}")
    ship_cell = None
    for k in cand:
        s, x = cells[k]["s"], cells[k]["x"]
        probe_ok = True
        for wp in W_PROBES:
            lbl = (f"hftmo1_probe_w{int(wp*100)}_s{int(round(s*100))}"
                   f"_x{int(round(x*10))}")
            row = run_cell(static_blend(wp), s, x, lbl, None)
            b08["probes"][lbl] = row
            probe_ok = probe_ok and row["compliant"]
            if not probe_ok:
                break
        if probe_ok:
            ship_cell = k
            break
        log(f"cell {k} NOT probe-robust — walking down")

    # ---- 4. VERDICT ---------------------------------------------------------
    if ship_cell is not None:
        c = cells[ship_cell]
        beats = c["cagr"] >= bar_cagr
        gap_total = IC_CAGR - ship_cagr
        gap_closed = (c["cagr"] - ship_cagr) / gap_total
        b08["best_probe_robust"] = {
            "cell": ship_cell, **{k2: c[k2] for k2 in
                                  ("s", "x", "cagr", "n_triggers",
                                   "reentry_cost_pp", "raw_dip_days_gt5pct",
                                   "maxdd_worst")},
            "p_breach_12m": c["bootstrap"]["p_breach_12m"],
            "beats_plus8pp_bar": bool(beats),
            "cagr_bar": bar_cagr,
            "gap_to_ic_pp": gap_total * 100.0,
            "gap_closed_ratio": gap_closed}
        if beats:
            b08["verdict"] = (
                f"ADOPT — s={c['s']} x={c['x']}% probe-robust, CAGR "
                f"{c['cagr']:+.4f} >= bar {bar_cagr:+.4f} "
                f"(+{(c['cagr']-ship_cagr)*100:.1f}pp over FMA3-009 ship) at "
                f"P(breach12m) {c['bootstrap']['p_breach_12m']:.4f} <= 0.05. "
                "Guardian module goes into the unified EA.")
            res["ship"] = {
                "s": c["s"], "daily_stop_x": c["x"],
                "provenance": "FMA3-008/daily-breaker+model-v3",
                "cagr": c["cagr"],
                "n_triggers": c["n_triggers"],
                "reentry_cost_pp": c["reentry_cost_pp"],
                "p_breach_12m": c["bootstrap"]["p_breach_12m"],
                "daily_dip_gt5pct": c["historical"]["daily_dip_gt5pct"],
                "worst_month_floor_touch":
                    c["historical"]["worst_month_floor_touch"],
                "p_pass_p1": c["challenge"]["p_pass_p1"],
                "median_days_p1": c["challenge"]["median_days_p1"],
                "gap_closed_ratio": gap_closed,
                "verdict": f"SHIP s={c['s']} + daily breaker x={c['x']}% "
                           "(FMA3-008: base + both +-20% w probes clear "
                           "model v3)"}
            src = OUT / f"{ship_cell}_curve.parquet"
            (OUT / "hrisk2_ship_curve.parquet").write_bytes(src.read_bytes())
            log(f"ADOPT — ship re-pointed to {ship_cell}; ship curve copied")
        else:
            b08["verdict"] = (
                f"DECLINE — best probe-robust cell {ship_cell} CAGR "
                f"{c['cagr']:+.4f} < bar {bar_cagr:+.4f} "
                f"(+{(c['cagr']-ship_cagr)*100:.1f}pp < +8pp). Re-entry cost "
                "+ gap residual ate the edge; FMA3-009 ship s=0.4 stands; "
                "NO guardian EA is built.")
            log("DECLINE — probe-robust cell exists but misses the +8pp bar; "
                "ship unchanged")
    else:
        b08["verdict"] = ("DECLINE — no probe-robust compliant (s,x) cell "
                          "(walk-down exhausted). FMA3-009 ship s=0.4 "
                          "stands; NO guardian EA is built.")
        log("DECLINE — no probe-robust cell; ship unchanged")

    res["fma3_008"] = b08
    (OUT / "hrisk2_results.json").write_text(
        json.dumps(res, indent=1, default=str))
    log(f"DONE ({time.time()-t0:.0f}s) | {b08['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
