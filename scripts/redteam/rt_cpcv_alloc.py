#!/usr/bin/env python3
"""rt_cpcv_alloc — PROTOCOL.md §6(d): purged combinatorial CV at the
ALLOCATION level.  No engine — bookkeeping curves only.

What is being cross-validated: NOT the sleeves (frozen, parent-validated)
and NOT the record-engine numbers, but the single structural choice FMA3
actually made — the capital split w — exactly as FMA2's walkforward_cpcv.py
cross-validated its allocation over frozen sleeves.

Method (mirrors FMA2 research/walkforward_cpcv.py fold construction):
  * joint daily-return sample from the parents' bookkeeping curves:
    r_w(t) = pct_change of  J_t = w*A_t + (1-w)*B_t  (static H-FED-1 drift,
    the selection layer under test; cadence variants are exercised by
    rt_fixed_schedule / rt_perturbation instead);
  * 8 contiguous blocks, every C(8,2)=28 combination of k=2 test blocks,
    purge 10d around the test envelope (FMA2 convention: train = rows
    outside [min(test)-10, max(test)+10]);
  * per fold, re-pick w on the TRAIN rows by the H-FED-1 selection rule
    evaluated on the bookkeeping curves — all pre-registered bars pass and
    max Sharpe among passers, with run_hfed2's registered fallback ladder
    (risk-half passers, then max-Sharpe) so every fold yields a pick.  The
    bars are re-derived per fold from the PARENTS' bookkeeping streams on
    the same train rows (record-engine bars are not computable on purged
    subsets): DD < min(parents) - 0.5pp, Sharpe > max(parents) + 0.05,
    negY == 0, negQ <= min(parents), with negY/negQ counted only over
    periods with enough train rows to mean anything (>=40d / >=15d);
  * apply the picked w to the TEST rows; compare with the frozen (winning)
    w on the same test rows.

PRE-REGISTERED THRESHOLD (FMA2 convention, walkforward_cpcv.py's 0.8 rule):
  ROBUST (=> PASS) iff median OOS Sharpe (re-picked w)
                       >= 0.8 x median OOS Sharpe (frozen w).
  If the frozen median is <= 0 the ratio is meaningless; the fallback rule
  is then median(re-picked) >= median(frozen), reported as such.

Usage:
  python3 rt_cpcv_alloc.py <results.json> <grid-key>       # real run
  python3 rt_cpcv_alloc.py --synthetic [--frozen-w 0.5]    # fold-logic smoke

Writes research/outputs/redteam/rt_cpcv_alloc.json (synthetic runs write
rt_cpcv_alloc_synthetic.json so they can never clobber a real result) and
prints one greppable `RT_VERDICT [rt_cpcv_alloc] ...` line.
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rt_lib  # noqa: E402

SCRIPT = "rt_cpcv_alloc"
ANN = 252.0
N_BLOCKS, K_TEST, PURGE_D = 8, 2, 10        # pre-registered (PROTOCOL §6d)
ROBUST_FRAC = 0.80                          # pre-registered (FMA2 convention)
# H-FED-1 bar offsets (mirror of run_hfed1's bar construction)
DD_MARGIN, SHARPE_MARGIN = 0.005, 0.05
MIN_OBS_Y, MIN_OBS_Q = 40, 15               # min train rows for negY/negQ


# ---------------------------------------------------------------------------
# metric helpers on (possibly non-contiguous) daily-return subsets
# ---------------------------------------------------------------------------

def sharpe_ann(r: pd.Series) -> float:
    """Annualized daily-close Sharpe; 0.0 on degenerate input."""
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0


def chained_maxdd(r: pd.Series) -> float:
    """Max drawdown of the CHAINED subset returns (standard CPCV practice:
    non-contiguous rows are compounded as one stream; drawdowns spanning a
    block boundary are approximate, identically so for every candidate)."""
    cum = (1.0 + r).cumprod()
    return float((1.0 - cum / cum.cummax()).max())


def n_neg_periods(r: pd.Series, freq: str, min_obs: int) -> int:
    """Count calendar periods whose chained subset return is negative.

    Periods with fewer than ``min_obs`` train rows are skipped: compounding
    a handful of leftover days into a 'year' would make the negY/negQ bars
    pure noise on purged folds."""
    n = 0
    for _, x in r.groupby(r.index.to_period(freq)):
        if len(x) >= min_obs and float((1.0 + x).prod() - 1.0) < 0.0:
            n += 1
    return n


def block_metrics(r: pd.Series) -> dict[str, float | int]:
    return {"sharpe": sharpe_ann(r), "maxdd": chained_maxdd(r),
            "n_neg_years": n_neg_periods(r, "Y", MIN_OBS_Y),
            "n_neg_quarters": n_neg_periods(r, "Q", MIN_OBS_Q)}


# ---------------------------------------------------------------------------
# inputs: parents' daily bookkeeping curves
# ---------------------------------------------------------------------------

def load_daily_parent_curves() -> tuple[pd.Series, pd.Series]:
    """Daily samples of the parents' native curves, normalized to 1.0 at t0.

    Same artifacts run_hfed1_lib.load_inputs uses, loaded directly so this
    script never triggers the engine bootstrap (no-engine path)."""
    a = pd.read_parquet(
        rt_lib.PATHS.OUTPUTS / "v7_book_equity_1m.parquet")["eqc"]
    b = pd.read_parquet(
        rt_lib.PATHS.BASELINES / "fma2" / "v34_s10_pin_curve.parquet"
    )["equity"]
    a, b = a / a.iloc[0], b / b.iloc[0]
    a_d = a.resample("1D").last().dropna()
    b_d = b.resample("1D").last().dropna()
    ix = a_d.index.intersection(b_d.index)
    return a_d[ix], b_d[ix]


def synthetic_parent_curves(seed: int = 20260709,
                            n_days: int = 1560) -> tuple[pd.Series, pd.Series]:
    """Synthetic stand-ins for the fold-logic smoke test.

    Calibrated to the composite benchmark's shape (v7-like Sharpe ~2.3,
    v3.4-like ~1.85, daily rho ~0.35) so the smoke test exercises realistic
    selection dynamics; seeded with the house seed for reproducibility."""
    rng = np.random.default_rng(seed)
    rho = 0.35
    z0, z1, z2 = (rng.standard_normal(n_days) for _ in range(3))
    mix_a = np.sqrt(rho) * z0 + np.sqrt(1 - rho) * z1
    mix_b = np.sqrt(rho) * z0 + np.sqrt(1 - rho) * z2
    r_a = 0.00172 + 0.012 * mix_a
    r_b = 0.00128 + 0.011 * mix_b
    idx = pd.bdate_range("2020-01-02", periods=n_days)
    a = pd.Series(np.cumprod(1.0 + r_a), index=idx)
    b = pd.Series(np.cumprod(1.0 + r_b), index=idx)
    return a / a.iloc[0], b / b.iloc[0]


# ---------------------------------------------------------------------------
# CPCV core
# ---------------------------------------------------------------------------

def cpcv_folds(n_rows: int, n_blocks: int, k_test: int, purge: int):
    """FMA2 walkforward_cpcv.py fold construction, verbatim semantics."""
    idx = np.array_split(np.arange(n_rows), n_blocks)
    for combo in itertools.combinations(range(n_blocks), k_test):
        test_rows = np.concatenate([idx[b] for b in combo])
        lo, hi = test_rows.min() - purge, test_rows.max() + purge
        train_rows = np.array([i for i in range(n_rows)
                               if i < lo or i > hi])
        yield combo, train_rows, test_rows


def pick_w(train_by_w: dict[float, dict], bars: dict) -> tuple[float, str]:
    """H-FED-1 selection rule + run_hfed2's registered fallback ladder."""
    passers = {w: m for w, m in train_by_w.items()
               if m["maxdd"] < bars["dd_lt"]
               and m["sharpe"] > bars["sharpe_gt"]
               and m["n_neg_years"] == 0
               and m["n_neg_quarters"] <= bars["neg_q_le"]}
    if passers:
        return max(passers, key=lambda w: passers[w]["sharpe"]), "all_bars"
    risk = {w: m for w, m in train_by_w.items()
            if m["maxdd"] < bars["dd_lt"]
            and m["n_neg_years"] == 0
            and m["n_neg_quarters"] <= bars["neg_q_le"]}
    if risk:
        return max(risk, key=lambda w: risk[w]["sharpe"]), "risk_half"
    return (max(train_by_w, key=lambda w: train_by_w[w]["sharpe"]),
            "fallback_max_sharpe")


def run_cpcv(a_d: pd.Series, b_d: pd.Series, frozen_w: float
             ) -> dict:
    """Full CPCV analysis; returns the results payload block."""
    w_set = sorted(set(rt_lib.W_GRID) | {frozen_w})
    streams: dict[float, pd.Series] = {}
    for w in w_set:
        streams[w] = (w * a_d + (1.0 - w) * b_d).pct_change().dropna()
    ix = streams[w_set[0]].index
    r_a, r_b = a_d.pct_change().dropna(), b_d.pct_change().dropna()
    n = len(ix)
    rt_lib.log(SCRIPT, f"{n} joint daily returns | grid {w_set} | "
               f"frozen w={frozen_w}")

    folds = []
    for combo, train_rows, test_rows in cpcv_folds(
            n, N_BLOCKS, K_TEST, PURGE_D):
        pa = block_metrics(r_a.iloc[train_rows])
        pb = block_metrics(r_b.iloc[train_rows])
        bars = {
            "dd_lt": min(pa["maxdd"], pb["maxdd"]) - DD_MARGIN,
            "sharpe_gt": max(pa["sharpe"], pb["sharpe"]) + SHARPE_MARGIN,
            "neg_q_le": min(pa["n_neg_quarters"], pb["n_neg_quarters"]),
        }
        train_by_w = {w: block_metrics(streams[w].iloc[train_rows])
                      for w in rt_lib.W_GRID}
        w_star, rule = pick_w(train_by_w, bars)
        oos_pick = sharpe_ann(streams[w_star].iloc[test_rows])
        oos_frozen = sharpe_ann(streams[frozen_w].iloc[test_rows])
        folds.append({"test_blocks": list(combo), "n_train": len(train_rows),
                      "w_pick": w_star, "rule": rule,
                      "oos_sharpe_pick": oos_pick,
                      "oos_sharpe_frozen": oos_frozen})
        rt_lib.log(SCRIPT, f"fold {combo}: pick w={w_star} ({rule}) | "
                   f"OOS Sh pick {oos_pick:.2f} vs frozen {oos_frozen:.2f}")

    picks = np.array([f["oos_sharpe_pick"] for f in folds])
    frozen = np.array([f["oos_sharpe_frozen"] for f in folds])
    med_p, med_f = float(np.median(picks)), float(np.median(frozen))
    if med_f > 0:
        robust = med_p >= ROBUST_FRAC * med_f
        rule_used = f"median(pick) >= {ROBUST_FRAC} x median(frozen)"
    else:
        robust = med_p >= med_f
        rule_used = ("median(frozen) <= 0 — ratio meaningless; fallback "
                     "median(pick) >= median(frozen)")

    q = lambda x, p: float(np.percentile(x, p))     # noqa: E731
    return {
        "n_daily_obs": n,
        "cpcv": {"n_blocks": N_BLOCKS, "k_test": K_TEST, "purge_d": PURGE_D,
                 "n_folds": len(folds)},
        "frozen_w": frozen_w,
        "folds": folds,
        "pick_histogram": {str(w): int(sum(1 for f in folds
                                           if f["w_pick"] == w))
                           for w in rt_lib.W_GRID},
        "rule_histogram": {r: int(sum(1 for f in folds if f["rule"] == r))
                           for r in ("all_bars", "risk_half",
                                     "fallback_max_sharpe")},
        "oos_pick": {"p5": q(picks, 5), "p25": q(picks, 25), "p50": med_p,
                     "p75": q(picks, 75), "p95": q(picks, 95)},
        "oos_frozen": {"p5": q(frozen, 5), "p25": q(frozen, 25),
                       "p50": med_f, "p75": q(frozen, 75),
                       "p95": q(frozen, 95)},
        "median_ratio": (med_p / med_f) if med_f != 0 else None,
        "robust_rule": rule_used,
        "robust": bool(robust),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", nargs="?", type=Path,
                    help="H-FED results JSON holding the winner")
    ap.add_argument("key", nargs="?",
                    help="grid key of the winning config (frozen w source)")
    ap.add_argument("--synthetic", action="store_true",
                    help="run the fold logic on seeded synthetic curves "
                         "(smoke test; writes a separate _synthetic.json)")
    ap.add_argument("--frozen-w", type=float, default=0.50,
                    help="frozen w for --synthetic mode (default 0.50)")
    args = ap.parse_args(argv)
    t0 = time.time()

    if args.synthetic:
        a_d, b_d = synthetic_parent_curves()
        frozen_w = args.frozen_w
        winner_block: dict = {"synthetic": True, "frozen_w": frozen_w}
        out_name = f"{SCRIPT}_synthetic"
    else:
        if not (args.results and args.key):
            ap.error("results JSON and key are required unless --synthetic")
        cfg, _, _ = rt_lib.load_winner(args.results, args.key)
        frozen_w = cfg.w_v7
        winner_block = {"results": str(args.results), "key": args.key,
                        "config": {"kind": cfg.kind, "w_v7": cfg.w_v7,
                                   "b_up": cfg.b_up,
                                   "min_gap_days": cfg.min_gap_days}}
        a_d, b_d = load_daily_parent_curves()
        out_name = SCRIPT

    block = run_cpcv(a_d, b_d, frozen_w)

    if block["robust"]:
        status = "PASS"
        reason = (f"ROBUST: median OOS Sharpe (re-picked w) "
                  f"{block['oos_pick']['p50']:.2f} >= {ROBUST_FRAC} x frozen "
                  f"{block['oos_frozen']['p50']:.2f} over "
                  f"{block['cpcv']['n_folds']} purged folds")
    else:
        status = "FAIL"
        reason = (f"NOT robust: median OOS Sharpe (re-picked w) "
                  f"{block['oos_pick']['p50']:.2f} < {ROBUST_FRAC} x frozen "
                  f"{block['oos_frozen']['p50']:.2f} — the frozen w does not "
                  "survive allocation-level re-selection")
    if args.synthetic:
        reason = "[SYNTHETIC smoke, not a battery result] " + reason

    rt_lib.write_results(out_name, {
        "script": SCRIPT, "synthetic": args.synthetic,
        "winner": winner_block,
        "threshold_robust_frac": ROBUST_FRAC,
        **block,
        "verdict": status, "reason": reason,
        "elapsed_s": time.time() - t0,
    })
    return rt_lib.verdict(SCRIPT, status, reason)


if __name__ == "__main__":
    sys.exit(main())
