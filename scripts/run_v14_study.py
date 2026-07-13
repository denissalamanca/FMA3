"""FMA3 v1.4 — 2015-2019 extended-history falsification study runner.

STATUS: UNRUN (written 2026-07-10 as v1.4 prep; the pre-registered
H-RISK-1/H-RISK-2/H-TAIL-1 engine queue owns the CPU, and ROADMAP.md sequences
v1.4 after v1.1-v1.3). This script has never been executed. Exact command,
to be run ONLY after the queue drains AND the NSF5 extended-history anchor
diagnosis lands:

    cd /Users/dsalamanca/vs_env/FableMultiAssets3
    /opt/homebrew/Caskroom/miniforge/base/bin/python3 scripts/run_v14_study.py --phase0-only
    # inspect research/outputs/v14_phase0.json; if both anchors PASS:
    /opt/homebrew/Caskroom/miniforge/base/bin/python3 scripts/run_v14_study.py

Spec of record: research/protocol/V14_STUDY.md (CRITERIA COMMITTED
2026-07-10). This runner computes EXACTLY N1-N6 and the R-a/R-b/R-c trigger
evaluations on windows W-A (2015-2019) and W-B (2018-2019). Nothing else.

Guards (V14_STUDY.md SS8):
  G1  refuse unless V14_STUDY.md contains 'CRITERIA COMMITTED';
  G2  hard-fail if any engine-queue / record-engine process is alive;
  G3  Phase 1 unreachable unless BOTH Phase-0 anchors pass their tolerances.

Expected runtime (documented estimate, not yet measured):
  Phase 0 A2 (v3.4 fast-sim anchor, FMA2 research_cache 37 syms x 6y hourly):
           ~5-15 min.
  Phase 0 A1 (v7 ext-pipeline anchor, NSF5 bars_1m_ext 10 syms x 6y 1m sleeve
           builds via run_harvest_attrib): ~15-45 min.
  Phase 1  (both books 2015-2019 + extended EDGES + fed bookkeeping):
           ~20-60 min.
  Total ~45-120 min single process, several GB RAM. Do NOT parallelise on the
  shared box; do NOT run alongside any other engine work.

Accounting convention: research-grade close-mark daily curves. NOT worst-mark.
Feeds: NSF5 cache/bars_1m_ext (tz-naive TRUE UTC; pre-2020 = synthetic ask,
n_ticks=1) and FMA2 research_cache_ext (tz-naive broker SERVER time, ASSIGNED
spreads). Curves join on calendar-date daily closes only — never intrabar
(the DO_NOT_USE.md timezone landmine).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
NSF5 = Path("/Users/dsalamanca/vs_env/NewStrategyFable5")
OUT = FMA3 / "research" / "outputs"
SPEC = FMA3 / "research" / "protocol" / "V14_STUDY.md"

# ---- committed constants (V14_STUDY.md SS3-SS6) ----------------------------
W_FED = 0.70                       # shipped v1.0 static split (v7 share)
WIN_A = ("2015-01-02", "2019-12-31")   # headline window W-A
WIN_B = ("2018-01-01", "2019-12-31")   # full-sleeve secondary window W-B
N_WORST = 10

# Phase-0 anchor targets + tolerances (SS4; reconciliation gates, not knobs)
V7_ANCHOR_CAGR, V7_ANCHOR_DDREL = 108.50, 18.84   # R10 close-mark panel, pct
V7_TOL_CAGR_PP, V7_TOL_DD_PP = 3.0, 2.0
V34_PIN_CAGR, V34_PIN_DD = 88.66, 21.67           # 1m worst-mark pin, pct
V34_CAGR_LO, V34_CAGR_HI = 0.95 * V34_PIN_CAGR, 1.18 * V34_PIN_CAGR
V34_DD_LO, V34_DD_HI = V34_PIN_DD - 4.0, V34_PIN_DD + 4.0

QUEUE_PAT = ("run_hrisk1|run_hrisk2|run_htail1|record_engine|"
             "account_engine_1m|run_record")


# =========================== guards =========================================
def guard_criteria() -> None:
    """G1 — the pre-registration must be committed."""
    if not SPEC.exists() or "CRITERIA COMMITTED" not in SPEC.read_text():
        sys.exit("REFUSED: research/protocol/V14_STUDY.md is missing or does "
                 "not contain 'CRITERIA COMMITTED'. Pre-registration first.")


def guard_queue() -> None:
    """G2 — never contend with the pre-registered engine queue."""
    r = subprocess.run(["pgrep", "-fl", QUEUE_PAT], capture_output=True,
                       text=True)
    lines = [l for l in r.stdout.strip().splitlines()
             if l and "run_v14_study" not in l]
    if lines:
        sys.exit("HARD-FAIL: engine-queue / record-engine process(es) alive:\n"
                 + "\n".join("  " + l for l in lines)
                 + "\nv1.4 must wait for the queue to drain (CPU etiquette).")


# =========================== phase 0: anchors ================================
def phase0_v34_anchor() -> dict:
    """A2 — v3.4-composition hourly fast-sim on FMA2 research_cache 2020-25.

    Composition per eval_v34_pin_s10.py (F3 caps + MAG@0.05, combine, NO
    renormalise, x SCALE 10, apply_hard_limits) but simulated with the hourly
    fast-sim core.simulate (research-grade close-mark), NOT account_engine_1m.
    """
    sys.path.insert(0, str(FMA2 / "research"))
    sys.path.insert(0, str(FMA2))
    import core                                    # noqa: E402
    import ensemble as E                           # noqa: E402
    from ext_import import mag_xau                 # noqa: E402

    V2_CAPS = {"meanrev": 0.11, "carry_breakout": 0.046, "seasonal": 0.18,
               "intraday": 0.168, "crisis": 0.10, "trend_v2": 0.042,
               "crypto_smart": 0.13}
    sleeves = E.load_sleeves(list(V2_CAPS))
    grid = core.universe_frames(tuple(core.ALL))["ret"].index
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
    pos = E.combine(sleeves, {**V2_CAPS, "mag": 0.05}) * 10.0
    pos = E.apply_hard_limits(pos, gold_cap=E.structural_gold_cap(V2_CAPS, 10.0))
    eq = core.simulate(pos).equity
    d = eq.resample("1D").last().dropna()
    return _anchor_verdict_v34(d)


def _anchor_verdict_v34(d: pd.Series) -> dict:
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    cagr = 100.0 * ((d.iloc[-1] / d.iloc[0]) ** (1 / yrs) - 1)
    dd = 100.0 * float((1 - d / d.cummax()).max())
    ok = (V34_CAGR_LO <= cagr <= V34_CAGR_HI) and (V34_DD_LO <= dd <= V34_DD_HI)
    return {"anchor": "A2_v34_fastsim_2020_25", "cagr_pct": cagr,
            "maxdd_close_pct": dd,
            "bands": {"cagr": [V34_CAGR_LO, V34_CAGR_HI],
                      "dd": [V34_DD_LO, V34_DD_HI]},
            "pass": bool(ok)}


def phase0_v7_anchor(M: pd.DataFrame) -> dict:
    """A1 — v7 ext pipeline reproduces the pinned 2020-25 close-mark panel.

    Reuses NSF5 v72 extended-run machinery READ-ONLY (prime bars_1m_ext,
    v52_alternatives.book('BTC_REP','USA500') — the committed USA500 proxy —
    per-sleeve run_harvest_attrib, band_sim at R10). Known state at commit
    time: this anchor FAILS (71%/44% vs 108.50%/18.84%) — the NSF5 diagnosis
    (paused, MORNING_BRIEFING.md:80-81) must land before this passes. This
    function measures; it does not diagnose.
    """
    m = _v7_book_metrics(M.loc["2020-01-01":"2025-12-31"])
    ok = (abs(m["cagr"] - V7_ANCHOR_CAGR) <= V7_TOL_CAGR_PP
          and abs(m["ddrel"] - V7_ANCHOR_DDREL) <= V7_TOL_DD_PP)
    return {"anchor": "A1_v7_ext_pipeline_2020_25", **m,
            "target": {"cagr": V7_ANCHOR_CAGR, "ddrel": V7_ANCHOR_DDREL},
            "tol_pp": {"cagr": V7_TOL_CAGR_PP, "ddrel": V7_TOL_DD_PP},
            "pass": bool(ok)}


# =========================== v7 side (NSF5, read-only reuse) =================
def _nsf5_paths() -> None:
    for p in (NSF5, NSF5 / "mt5" / "reconcile", NSF5 / "mt5" / "reconcile" / "v72"):
        sys.path.insert(0, str(p))


def _build_v7_sleeve_matrix(lo: str) -> pd.DataFrame:
    """Per-sleeve daily-return matrix on bars_1m_ext, extended_run.py
    conventions: 10-instrument prime, extended quarterly EDGES from `lo`,
    crypto EDGES from 2018-01-01, kmult=inf attribution, B-day resample."""
    _nsf5_paths()
    import engine.backtest as bt                       # noqa: E402
    from config import settings as S                   # noqa: E402
    from multifeed_optim import ICFx                   # noqa: E402
    from v52_alternatives import book                  # noqa: E402
    import v52_baseline                                # noqa: E402
    from v52_baseline import run_harvest_attrib        # noqa: E402

    EXT = S.CACHE_DIR / "bars_1m_ext"
    INSTS = ["XAUUSD", "USA500", "USDJPY", "EURGBP", "AUDUSD", "NZDUSD",
             "EURUSD", "EURJPY", "BTCUSD", "ETHUSD"]
    bt._BARS_CACHE.clear(); bt._PREP_CACHE.clear()
    d = {}
    for inst in INSTS:
        p = EXT / f"{inst}_2015_2025_1m.parquet"
        if p.exists():
            b = pd.read_parquet(p); d[inst] = b; bt._BARS_CACHE[(inst, False)] = b
    bt._FX = ICFx(d)

    ext_edges = sorted(set([pd.Timestamp(lo)]
                           + list(pd.date_range(lo, "2026-01-01", freq="QS"))[1:]
                           + [pd.Timestamp("2026-01-01")]))
    crypto_edges = sorted(set([pd.Timestamp("2018-01-01")]
                              + list(pd.date_range("2018-01-01", "2026-01-01",
                                                   freq="QS"))[1:]
                              + [pd.Timestamp("2026-01-01")]))
    v52_baseline.EDGES = ext_edges
    CRYPTO = ("S1_ETH", "BTC_REP")
    cols = {}
    for name, legs in book("BTC_REP", "USA500").items():
        ed = crypto_edges if name in CRYPTO else ext_edges
        oo = run_harvest_attrib({name: legs}, kmult=np.inf, edges=ed)
        cols[name] = oo["daily"].resample("B").last().ffill().pct_change()
    idx = None
    for c in cols.values():
        idx = c.index if idx is None else idx.union(c.index)
    return pd.DataFrame({k: v.reindex(idx) for k, v in cols.items()}).fillna(0.0)


def _v7_book_metrics(M: pd.DataFrame) -> dict:
    """band_sim close-mark panel at R10 (the anchor's own convention)."""
    from combined import band_sim, BASE_R              # noqa: E402
    from validate import cagr as _cagr                 # noqa: E402
    Rdf = M.dropna(how="any") * (10.0 / BASE_R)
    E, nreb = band_sim(Rdf)
    r = E.pct_change().dropna().to_numpy()
    peak = np.maximum.accumulate(E.values)
    return {"cagr": 100 * _cagr(r),
            "ddrel": 100 * float(np.max(1 - E.values / peak)),
            "nreb": int(nreb), "n_days": int(len(Rdf))}


def _v7_daily_curve(M: pd.DataFrame, lo: str, hi: str) -> pd.Series:
    from combined import band_sim, BASE_R              # noqa: E402
    Rdf = M.loc[(M.index >= lo) & (M.index <= hi)].dropna(how="any") * (10.0 / BASE_R)
    E, _ = band_sim(Rdf)
    E.index = pd.DatetimeIndex(pd.to_datetime(E.index).date)  # calendar dates
    return E.groupby(E.index).last()


# =========================== v3.4 side (FMA2 ext cache) ======================
def build_v34_ext_curve() -> tuple[pd.Series, dict]:
    """v3.4 composition on research_cache_ext (2015-2020), hourly fast-sim.
    Returns daily-close equity + per-sleeve coverage (N6 input)."""
    import glob, os, importlib                          # noqa: E402
    sys.path.insert(0, str(FMA2 / "research"))
    sys.path.insert(0, str(FMA2))
    import core                                        # noqa: E402
    import ensemble as E                               # noqa: E402
    from ext_import import mag_xau                     # noqa: E402

    EXTC = FMA2 / "research_cache_ext"
    avail = tuple(sorted(os.path.basename(f)[:-11]
                         for f in glob.glob(str(EXTC / "*_1h.parquet"))))
    core.CACHE = EXTC
    core.ALL = avail
    _uf, _sw = core.universe_frames, core.swap_accrual_matrices
    core.universe_frames = lambda symbols=avail: _uf(avail)
    core.swap_accrual_matrices = lambda symbols=avail: _sw(avail)

    V2_CAPS = {"meanrev": 0.11, "carry_breakout": 0.046, "seasonal": 0.18,
               "intraday": 0.168, "crisis": 0.10, "trend_v2": 0.042,
               "crypto_smart": 0.13}
    grid = core.universe_frames(avail)["ret"].index
    sleeves, coverage = {}, {}
    for name in V2_CAPS:
        mod = importlib.import_module(f"sleeves.{name}"); importlib.reload(mod)
        if name == "crypto_smart":     # run_oos_2015.py convention (SOL is 2020+)
            pos = mod.make_positions(symbols=["BTCUSD", "ETHUSD"])
        else:
            pos = mod.make_positions()
        pos = pos.reindex(grid).fillna(0.0)
        sleeves[name] = pos
        act = pos.abs().sum(axis=1) > 1e-9
        coverage[name] = {"first": str(act.idxmax().date()) if act.any() else None,
                          "days_active": int(act.resample("1D").max().sum())}
    sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
    act = sleeves["mag"].abs().sum(axis=1) > 1e-9
    coverage["mag_xau"] = {"first": str(act.idxmax().date()) if act.any() else None,
                           "days_active": int(act.resample("1D").max().sum())}

    pos = E.combine(sleeves, {**V2_CAPS, "mag": 0.05}) * 10.0
    pos = E.apply_hard_limits(pos, gold_cap=E.structural_gold_cap(V2_CAPS, 10.0))
    eq = core.simulate(pos).equity.resample("1D").last().dropna()
    eq.index = pd.DatetimeIndex(pd.to_datetime(eq.index).date)
    return eq.groupby(eq.index).last(), coverage


# =========================== metrics (N1-N5, per window) =====================
def fed_metrics(d7: pd.Series, d34: pd.Series, lo: str, hi: str) -> dict:
    """EXACTLY the committed outputs, mirroring derive_composite.py M-0."""
    d7 = d7.loc[lo:hi]; d34 = d34.loc[lo:hi]
    idx = d7.index.intersection(d34.index)
    d7, d34 = d7[idx], d34[idx]
    r7, r34 = d7.pct_change().dropna(), d34.pct_change().dropna()
    ridx = r7.index.intersection(r34.index)
    r7, r34 = r7[ridx], r34[ridx]

    rho_full = float(np.corrcoef(r34, r7)[0, 1])                       # N1
    rho_yearly = {int(y): float(np.corrcoef(r34[r34.index.year == y],  # N2
                                            r7[r7.index.year == y])[0, 1])
                  for y in sorted(set(r34.index.year))
                  if (r34.index.year == y).sum() > 20}

    w7d, w34d = r7.nsmallest(N_WORST).index, r34.nsmallest(N_WORST).index
    on_worst = {                                                        # N3
        "v34_ret_on_v7_10worst": float(r34[w7d].mean()),
        "v7_ret_on_v34_10worst": float(r7[w34d].mean()),
        "v7_10worst": {str(d.date()): [float(r7[d]), float(r34[d])] for d in w7d},
        "v34_10worst": {str(d.date()): [float(r34[d]), float(r7[d])] for d in w34d},
    }

    dd7 = 1 - d7 / d7.cummax(); dd34 = 1 - d34 / d34.cummax()
    co_dd = {                                                           # N4
        "v34_dd_at_v7_trough": float(dd34.reindex([dd7.idxmax()], method="ffill").iloc[0]),
        "v7_dd_at_v34_trough": float(dd7.reindex([dd34.idxmax()], method="ffill").iloc[0]),
        "v7_trough": str(dd7.idxmax().date()), "v34_trough": str(dd34.idxmax().date()),
        "v7_maxdd": float(dd7.max()), "v34_maxdd": float(dd34.max()),
    }

    # federation bookkeeping: static w70 virtual sub-accounts, NO rebalancing
    e7 = W_FED * (1 + r7.reindex(ridx).fillna(0)).cumprod()
    e34 = (1 - W_FED) * (1 + r34.reindex(ridx).fillna(0)).cumprod()
    efed = e7 + e34
    ddfed = float((1 - efed / efed.cummax()).max())
    dd_rel = {                                                          # N5
        "maxdd_v7": co_dd["v7_maxdd"], "maxdd_v34": co_dd["v34_maxdd"],
        "maxdd_fed_w70": ddfed,
        "weighted_sum_ref": W_FED * co_dd["v7_maxdd"] + (1 - W_FED) * co_dd["v34_maxdd"],
        "subadditivity_gap": min(co_dd["v7_maxdd"], co_dd["v34_maxdd"]) - ddfed,
    }

    triggers = {                                        # SS6, committed
        "R_a_rho_ge_0.60": bool(rho_full >= 0.60),
        "R_b_cotrough": bool(
            co_dd["v34_dd_at_v7_trough"] >= 0.5 * co_dd["v34_maxdd"]
            or co_dd["v7_dd_at_v34_trough"] >= 0.5 * co_dd["v7_maxdd"]),
        "R_c_dd_superadditive": bool(ddfed > dd_rel["weighted_sum_ref"]),
        "yellow_any_year_rho_ge_0.60": bool(any(v >= 0.60 for v in rho_yearly.values())),
    }
    return {"window": [lo, hi], "n_common_days": int(len(ridx)),
            "N1_rho_daily_full": rho_full, "N2_rho_daily_by_year": rho_yearly,
            "N3_on_worst_days": on_worst, "N4_co_drawdown": co_dd,
            "N5_dd_relation": dd_rel, "triggers": triggers}


# =========================== main ===========================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase0-only", action="store_true",
                    help="run anchors only; write v14_phase0.json and stop")
    args = ap.parse_args()

    guard_criteria()
    guard_queue()
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    print("[phase0] A2 v3.4 fast-sim anchor (2020-25) ...", flush=True)
    a2 = phase0_v34_anchor()
    print(f"  A2 {'PASS' if a2['pass'] else 'FAIL'}: "
          f"CAGR {a2['cagr_pct']:.2f}% DDclose {a2['maxdd_close_pct']:.2f}%", flush=True)

    print("[phase0] A1 v7 ext-pipeline anchor (2020-25) ...", flush=True)
    M7 = _build_v7_sleeve_matrix(lo="2015-01-01")
    a1 = phase0_v7_anchor(M7)
    print(f"  A1 {'PASS' if a1['pass'] else 'FAIL'}: "
          f"CAGR {a1['cagr']:.2f}% DDrel {a1['ddrel']:.2f}% "
          f"(target 108.50/18.84)", flush=True)

    phase0 = {"A1": a1, "A2": a2, "both_pass": bool(a1["pass"] and a2["pass"]),
              "elapsed_s": round(time.time() - t0)}
    (OUT / "v14_phase0.json").write_text(json.dumps(phase0, indent=1))

    if args.phase0_only:
        print(f"[phase0-only] wrote {OUT / 'v14_phase0.json'}", flush=True)
        return 0
    if not phase0["both_pass"]:
        # G3: BLOCKED — no 2015-19 number is computed, produced, or printed.
        (OUT / "v14_study.json").write_text(json.dumps(
            {"verdict": "BLOCKED", "phase0": phase0,
             "note": "V14_STUDY.md SS6 BLOCKED semantics: anchors must "
                     "reconcile before the one-shot runs; NSF5 anchor "
                     "diagnosis (paused) is the prerequisite."}, indent=1))
        print("BLOCKED: Phase-0 anchor(s) failed — study did not run; "
              "2015-19 remains unconsumed by FMA3.", flush=True)
        return 2

    # ---- Phase 1 (ONE SHOT) ------------------------------------------------
    print("[phase1] v7 2015-19 daily curve (ext pipeline) ...", flush=True)
    d7 = _v7_daily_curve(M7, *WIN_A)
    print("[phase1] v3.4 2015-19 daily curve (ext fast-sim) ...", flush=True)
    d34, cov34 = build_v34_ext_curve()

    res = {"spec": "research/protocol/V14_STUDY.md (CRITERIA COMMITTED 2026-07-10)",
           "phase0": phase0,
           "W_A": fed_metrics(d7, d34, *WIN_A),
           "W_B": fed_metrics(d7, d34, *WIN_B),
           "N6_coverage": {
               "v34_sleeves": cov34,
               "v7_sleeves": {c: {"first_nonzero": str(M7[c].loc[WIN_A[0]:WIN_A[1]]
                                                       .ne(0).idxmax().date())}
                              for c in M7.columns},
               "notes": ["v7 BOOK_USTEC via USA500 proxy (committed)",
                         "v7 crypto sleeves on the 2018-01-01 crypto EDGES",
                         "v34 crypto_smart BTC/ETH-only (SOL launches 2020)",
                         "research-grade feeds: synthetic/assigned spreads"]}}
    fired = [k for w in ("W_A", "W_B") for k, v in res[w]["triggers"].items()
             if v and k.startswith("R_")]
    res["verdict"] = "REFUTATION" if fired else "CONFIRMATION"
    res["triggers_fired"] = fired
    res["elapsed_s"] = round(time.time() - t0)

    (OUT / "v14_study.json").write_text(json.dumps(res, indent=1, default=str))
    pd.DataFrame({"v7": d7, "v34": d34}).to_parquet(OUT / "v14_curves_daily.parquet")
    print(f"\nDONE ({res['elapsed_s']}s) -> {OUT / 'v14_study.json'}", flush=True)
    print(f"verdict: {res['verdict']}  triggers_fired: {fired}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
