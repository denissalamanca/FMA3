#!/usr/bin/env python3
"""rt_dsr — PROTOCOL.md §6(h): Deflated Sharpe Ratio from the FMA3 ledger.

Bailey & Lopez de Prado PSR/DSR with the implementation mirrored from FMA2
research/validate_v1_4.py (``psr`` / ``expected_max_sr`` — same formulas,
same scipy.stats.norm usage, same Euler-Mascheroni constant) so the two
programs' DSR numbers are directly comparable.  No engine.

Inputs
------
* Candidate Sharpe + sample shape: either --curve <parquet> (daily-resampled
  equity; Sharpe/T/skew/kurtosis measured from the curve, the honest path)
  or explicit --sharpe/--n-days [--skew --kurt] for quick what-ifs.
* Trial count: parsed from docs/REGISTRY.md's Counters section (the honest
  multiple-testing ledger, PROTOCOL §5.4) as
  max(engine experiments, merged-book configs); --n-trials OVERRIDES the
  ledger (use it to stress higher effective-trial assumptions — e.g. to
  account for the parents' mining of the same 2020-2025 window).
* Trial-Sharpe variance (the E[max SR] dispersion input): measured from the
  grid Sharpes of the results JSONs passed via --results (mirrors FMA2's
  use of its observed trial Sharpes), or given directly with --var-sr
  (variance of DAILY Sharpe across trials).  No silent default — an assumed
  dispersion would be a hidden dial.

PRE-REGISTERED THRESHOLD: PASS iff DSR >= 0.95 at the ledger (or overridden)
trial count — i.e. >=95% probability that the true Sharpe exceeds the
expected max Sharpe of that many zero-skill trials.  DSR at 2x and 4x the
trial count is reported as stress context (not gating).

Usage:
  python3 rt_dsr.py --curve research/outputs/redteam/<winner>_curve.parquet \
                    --results research/outputs/hfed1_results.json \
                              research/outputs/hfed2_results.json
  python3 rt_dsr.py --sharpe 2.3 --n-days 1500 --n-trials 12 --var-sr 3.6e-4

Writes research/outputs/redteam/rt_dsr.json and prints one greppable
`RT_VERDICT [rt_dsr] ...` line.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rt_lib  # noqa: E402

SCRIPT = "rt_dsr"
ANN = 252.0
DSR_PASS = 0.95          # pre-registered lock bar
STRESS_MULTS = (2, 4)    # reported, not gating


# ---------------------------------------------------------------------------
# Bailey / Lopez de Prado — mirrored from FMA2 research/validate_v1_4.py
# ---------------------------------------------------------------------------

def psr(sr_d: float, sr0_d: float, T: int, skew: float, kurt: float) -> float:
    """Probabilistic Sharpe Ratio: P(true daily SR > sr0_d).

    Verbatim from FMA2 validate_v1_4.py::psr — the denominator corrects the
    SR estimator's variance for skew and (Pearson) kurtosis of the daily
    returns."""
    denom = np.sqrt(1 - skew * sr_d + (kurt - 1) / 4 * sr_d ** 2)
    return float(stats.norm.cdf((sr_d - sr0_d) * np.sqrt(T - 1) / denom))


def expected_max_sr(var_sr_d: float, n_trials: int) -> float:
    """Expected max daily SR under n independent zero-skill trials.

    Verbatim from FMA2 validate_v1_4.py::expected_max_sr (Bailey/LdP
    extreme-value approximation).  n_trials <= 1 has no selection effect;
    callers should use sr0 = 0 there (DSR degenerates to PSR)."""
    g = 0.5772156649  # Euler-Mascheroni
    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_sr_d) * ((1 - g) * z1 + g * z2))


# ---------------------------------------------------------------------------
# ledger / trial harvesting
# ---------------------------------------------------------------------------

def parse_registry_counters(registry_path: Path) -> dict[str, int]:
    """Parse the Counters section of docs/REGISTRY.md.

    Matches the two standing counter lines; the ledger format is
    pre-registered in PROTOCOL §5.4, so a parse failure means the registry
    drifted and should be loud, not defaulted away."""
    text = registry_path.read_text()
    out: dict[str, int] = {}
    for label, pat in (
            ("engine_experiments",
             r"Engine experiments run \(FMA3\):\s*([0-9]+)"),
            ("merged_configs",
             r"Merged-book configs evaluated:\s*([0-9]+)")):
        m = re.search(pat, text)
        if m:
            out[label] = int(m.group(1))
    if not out:
        raise ValueError(
            f"no counters found in {registry_path} — REGISTRY.md format "
            "drifted from the registered ledger layout")
    return out


def harvest_trial_sharpes(paths: list[Path]) -> list[float]:
    """Collect every grid-entry Sharpe from H-FED style results JSONs."""
    sharpes: list[float] = []
    for p in paths:
        data = json.loads(Path(p).read_text())
        for entry in data.get("grid", {}).values():
            if isinstance(entry, dict) and "sharpe" in entry:
                sharpes.append(float(entry["sharpe"]))
    return sharpes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--curve", type=Path,
                    help="equity curve parquet of the candidate (preferred: "
                         "Sharpe/T/skew/kurt measured, not asserted)")
    ap.add_argument("--column", default="equity",
                    help="equity column in --curve (default 'equity')")
    ap.add_argument("--sharpe", type=float,
                    help="annualized Sharpe (required without --curve; "
                         "overrides the curve-measured Sharpe if both given)")
    ap.add_argument("--n-days", type=int,
                    help="daily observations T (required without --curve)")
    ap.add_argument("--skew", type=float, default=0.0,
                    help="daily-return skew if no --curve (default 0)")
    ap.add_argument("--kurt", type=float, default=3.0,
                    help="daily-return Pearson kurtosis if no --curve "
                         "(default 3 = normal)")
    ap.add_argument("--n-trials", type=int,
                    help="trial-count override (default: ledger counters)")
    ap.add_argument("--results", type=Path, nargs="*", default=[],
                    help="results JSONs whose grid Sharpes estimate the "
                         "trial-Sharpe variance")
    ap.add_argument("--var-sr", type=float,
                    help="variance of DAILY Sharpe across trials (overrides "
                         "--results estimation)")
    ap.add_argument("--registry", type=Path,
                    default=rt_lib.PATHS.FMA3 / "docs" / "REGISTRY.md",
                    help="ledger path (default docs/REGISTRY.md)")
    args = ap.parse_args(argv)
    t0 = time.time()

    # --- candidate sample stats -------------------------------------------
    if args.curve:
        eq = pd.read_parquet(args.curve)[args.column]
        d = eq.resample("1D").last().dropna()
        r = d.pct_change().dropna().to_numpy()
        T = len(r)
        sr_d = float(r.mean() / r.std())
        skew = float(stats.skew(r))
        kurt = float(stats.kurtosis(r, fisher=False))
        stats_src = f"measured from {args.curve}"
        if args.sharpe is not None:
            sr_d = args.sharpe / np.sqrt(ANN)
            stats_src += " (Sharpe overridden by --sharpe)"
        if args.n_days is not None:
            T = args.n_days
            stats_src += " (T overridden by --n-days)"
    else:
        if args.sharpe is None or args.n_days is None:
            ap.error("--sharpe and --n-days are required without --curve")
        sr_d = args.sharpe / np.sqrt(ANN)
        T, skew, kurt = args.n_days, args.skew, args.kurt
        stats_src = "CLI (skew/kurt asserted, not measured)"
    sr_ann = sr_d * np.sqrt(ANN)
    rt_lib.log(SCRIPT, f"candidate: Sharpe {sr_ann:.3f} (daily {sr_d:.4f}) | "
               f"T={T} | skew {skew:+.2f} kurt {kurt:.1f} [{stats_src}]")

    # --- trial count from the honest ledger --------------------------------
    counters = parse_registry_counters(args.registry)
    n_ledger = max(counters.values())
    harvested = harvest_trial_sharpes(args.results)
    if args.n_trials is not None:
        n_trials, trials_src = args.n_trials, "--n-trials override"
    else:
        n_trials = max(n_ledger, len(harvested))
        trials_src = (f"ledger {counters} (max={n_ledger}), "
                      f"{len(harvested)} harvested grid sharpes")
    if n_trials < 1:
        print(f"[{SCRIPT}] ERROR: trial count is 0 (ledger counters "
              f"{counters}, nothing harvested) — pass --n-trials", flush=True)
        return 2
    rt_lib.log(SCRIPT, f"n_trials = {n_trials} [{trials_src}]")

    # --- trial-Sharpe dispersion -------------------------------------------
    if args.var_sr is not None:
        var_sr_d, var_src = float(args.var_sr), "--var-sr"
    elif len(harvested) >= 2:
        var_sr_d = float(np.var(np.array(harvested) / np.sqrt(ANN)))
        var_src = f"var of {len(harvested)} grid sharpes from --results"
    else:
        print(f"[{SCRIPT}] ERROR: need --var-sr or --results with >=2 grid "
              "sharpes to estimate trial-Sharpe variance (no silent "
              "default)", flush=True)
        return 2
    rt_lib.log(SCRIPT, f"var(SR_daily) = {var_sr_d:.3e} [{var_src}]")

    # --- DSR ----------------------------------------------------------------
    def dsr_at(n: int) -> dict[str, float]:
        sr0_d = expected_max_sr(var_sr_d, n) if n > 1 else 0.0
        return {"n_trials": n,
                "expected_max_sr_ann": sr0_d * float(np.sqrt(ANN)),
                "dsr": psr(sr_d, sr0_d, T, skew, kurt)}

    main_block = dsr_at(n_trials)
    psr0 = psr(sr_d, 0.0, T, skew, kurt)
    stress = {f"x{m}": dsr_at(n_trials * m) for m in STRESS_MULTS}
    rt_lib.log(SCRIPT, f"PSR(SR>0) {psr0:.4f} | E[maxSR] "
               f"{main_block['expected_max_sr_ann']:.3f}(ann) | "
               f"DSR {main_block['dsr']:.4f}"
               + "".join(f" | DSR@{k} {v['dsr']:.4f}"
                         for k, v in stress.items()))

    dsr = main_block["dsr"]
    if dsr >= DSR_PASS:
        status = "PASS"
        reason = (f"DSR {dsr:.4f} >= {DSR_PASS} at n={n_trials} trials "
                  f"(Sharpe {sr_ann:.2f}, T={T})")
    else:
        status = "FAIL"
        reason = (f"DSR {dsr:.4f} < {DSR_PASS} at n={n_trials} trials — the "
                  "Sharpe does not survive the ledger's multiple-testing "
                  "discount")

    rt_lib.write_results(SCRIPT, {
        "script": SCRIPT,
        "args": {k: (str(v) if isinstance(v, Path) else v)
                 for k, v in vars(args).items()
                 if k != "results"},
        "results_harvested": [str(p) for p in args.results],
        "candidate": {"sharpe_ann": sr_ann, "sr_daily": sr_d, "T": T,
                      "skew": skew, "kurt_pearson": kurt,
                      "source": stats_src},
        "ledger": {"counters": counters, "n_trials": n_trials,
                   "source": trials_src},
        "var_sr_daily": {"value": var_sr_d, "source": var_src,
                         "n_harvested": len(harvested)},
        "psr_vs_zero": psr0,
        "dsr": main_block,
        "dsr_stress": stress,
        "threshold": DSR_PASS,
        "verdict": status, "reason": reason,
        "elapsed_s": time.time() - t0,
    })
    return rt_lib.verdict(SCRIPT, status, reason)


if __name__ == "__main__":
    sys.exit(main())
