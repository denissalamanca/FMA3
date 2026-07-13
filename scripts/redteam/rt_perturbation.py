#!/usr/bin/env python3
"""rt_perturbation — PROTOCOL.md §6(a): parameter-perturbation grid.

Takes the winning federation config out of an H-FED results JSON, perturbs
each STRUCTURAL parameter one at a time (PROTOCOL §5.3: any adopted lever
gets ±20% parameter perturbation), and re-runs the engine of record per
perturbation.  Reports the full metric surface.

PRE-REGISTERED THRESHOLDS (fixed here, before any lock candidate exists):
  FRAGILE (=> FAIL) if ANY single perturbation moves the winner's
    * worst-mark DD by more than 3pp   (|delta maxdd_worst| > 0.03), or
    * Sharpe (daily close, 252) by more than 0.3 (|delta sharpe| > 0.3).
  Deltas are measured against the winner's recorded metric block in the
  results JSON (same engine of record — re-running the baseline would
  reproduce it bit-for-bit), in ABSOLUTE value: a perturbation that IMPROVES
  the pick by more than the threshold is equally damning, because it means
  the pre-registered selection sat on a knife edge.

PERTURBATION SET (structural params only, one at a time):
  w (v7 capital share):        x0.8 and x1.2
  band variants additionally:
    B_up:                      x0.8 and x1.2 (a perturbed value outside the
                               valid open interval (0.5, 1.0) — where
                               B_dn = 1-B_up crosses B_up — is recorded as an
                               explicit SKIPPED row, never silently clamped)
    min_gap_days:              the pre-registered probe set {4, 5, 6}d
                               (baseline 5 => probes 4d and 6d)

Engine passes: 2 (static / quarterly winner) or 6 (band winner).

Usage:
  python3 rt_perturbation.py <results.json> <grid-key> [--skip-bootstrap]
e.g.
  python3 rt_perturbation.py research/outputs/hfed1_results.json hfed1_w50

Writes research/outputs/redteam/rt_perturbation.json (+ per-run 1m curve
parquets) and prints one greppable `RT_VERDICT [rt_perturbation] ...` line.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rt_lib  # noqa: E402
from rt_lib import FedConfig  # noqa: E402

SCRIPT = "rt_perturbation"
DD_FLIP_PP = 3.0        # pre-registered: |delta worst-mark DD| > 3pp => FRAGILE
SHARPE_FLIP = 0.3       # pre-registered: |delta Sharpe| > 0.3       => FRAGILE
MIN_GAP_PROBES = (4, 5, 6)   # pre-registered min-gap set (baseline 5)


def build_perturbations(cfg: FedConfig
                        ) -> list[tuple[str, FedConfig | None, str]]:
    """One-at-a-time structural perturbations of the winner.

    Returns (tag, perturbed config or None, skip-note).  A None config is an
    invalid perturbation (e.g. B_up leaving (0.5, 1.0)) that is REPORTED
    rather than clamped — clamping would silently shrink the perturbation and
    flatter the fragility verdict.
    """
    out: list[tuple[str, FedConfig | None, str]] = []
    for tag, w2 in (("w_down20", cfg.w_v7 * 0.8), ("w_up20", cfg.w_v7 * 1.2)):
        if 0.0 < w2 < 1.0:
            out.append((tag, replace(cfg, w_v7=w2), ""))
        else:
            out.append((tag, None, f"w'={w2:.4f} outside (0, 1)"))
    if cfg.kind == "band":
        assert cfg.b_up is not None
        for tag, bu2 in (("b_up_down20", cfg.b_up * 0.8),
                         ("b_up_up20", cfg.b_up * 1.2)):
            if 0.5 < bu2 < 1.0:
                out.append((tag, replace(cfg, b_up=bu2), ""))
            else:
                out.append((tag, None,
                            f"B_up'={bu2:.4f} outside (0.5, 1.0)"))
        for g in MIN_GAP_PROBES:
            if g != cfg.min_gap_days:
                out.append((f"min_gap_{g}d",
                            replace(cfg, min_gap_days=g), ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path,
                    help="H-FED results JSON holding the winner")
    ap.add_argument("key", help="grid key of the winning config")
    ap.add_argument("--skip-bootstrap", action="store_true",
                    help="skip the ~1min house breach bootstrap per run "
                         "(the fragility thresholds only need DD/Sharpe)")
    args = ap.parse_args(argv)
    t0 = time.time()

    cfg, entry, _ = rt_lib.load_winner(args.results, args.key)
    base = {k: entry[k] for k in ("cagr", "maxdd_worst", "sharpe")}
    rt_lib.log(SCRIPT, f"winner {args.key}: {dataclasses.asdict(cfg)} | "
               f"CAGR {base['cagr']:+.4f} DDw {base['maxdd_worst']:.4f} "
               f"Sh {base['sharpe']:.3f}")

    perts = build_perturbations(cfg)
    n_engine = sum(1 for _, c, _ in perts if c is not None)
    rt_lib.log(SCRIPT, f"{len(perts)} perturbations ({n_engine} engine "
               f"passes) ...")

    ses = rt_lib.EngineSession()
    surface: dict[str, dict] = {}
    fragile_hits: list[str] = []
    for tag, pcfg, note in perts:
        if pcfg is None:
            surface[tag] = {"skipped": True, "note": note}
            rt_lib.log(SCRIPT, f"{tag}: SKIPPED ({note})")
            continue
        row = ses.run(pcfg, label=f"rt_perturb_{tag}",
                      run_bootstrap=not args.skip_bootstrap)
        d_dd = (row["maxdd_worst"] - base["maxdd_worst"]) * 100
        d_sh = row["sharpe"] - base["sharpe"]
        d_cagr = (row["cagr"] - base["cagr"]) * 100
        fragile = abs(d_dd) > DD_FLIP_PP or abs(d_sh) > SHARPE_FLIP
        row.update({"delta_dd_pp": d_dd, "delta_sharpe": d_sh,
                    "delta_cagr_pp": d_cagr, "fragile": bool(fragile)})
        surface[tag] = row
        if fragile:
            fragile_hits.append(f"{tag}(dDD{d_dd:+.1f}pp,dSh{d_sh:+.2f})")
        rt_lib.log(SCRIPT, f"{tag}: dCAGR {d_cagr:+.2f}pp | dDD "
                   f"{d_dd:+.2f}pp | dSh {d_sh:+.3f} | "
                   f"{'FRAGILE' if fragile else 'ok'}")

    if fragile_hits:
        status = "FAIL"
        reason = ("FRAGILE: " + ", ".join(fragile_hits)
                  + f" exceed |dDD|>{DD_FLIP_PP}pp or |dSh|>{SHARPE_FLIP}")
    else:
        status = "PASS"
        reason = (f"ROBUST: all {n_engine} perturbations within "
                  f"|dDD|<={DD_FLIP_PP}pp and |dSharpe|<={SHARPE_FLIP}")

    rt_lib.write_results(SCRIPT, {
        "script": SCRIPT,
        "args": {"results": str(args.results), "key": args.key,
                 "skip_bootstrap": args.skip_bootstrap},
        "winner": {"config": dataclasses.asdict(cfg), "metrics": base},
        "thresholds": {"dd_flip_pp": DD_FLIP_PP, "sharpe_flip": SHARPE_FLIP,
                       "min_gap_probes": MIN_GAP_PROBES},
        "surface": surface,
        "verdict": status, "reason": reason,
        "elapsed_s": time.time() - t0,
    })
    return rt_lib.verdict(SCRIPT, status, reason)


if __name__ == "__main__":
    sys.exit(main())
