#!/usr/bin/env python3
"""rt_loo — PROTOCOL.md §6(f): leave-one-out at the book level, federation
edition.

Full leave-one-book-out IS the composite benchmark: dropping v7 leaves the
measured v3.4 parent and vice versa (research/outputs/composite_benchmark
.json holds both parents in the engine of record) — re-running full drops
would measure nothing new.  What the parents CANNOT tell us is whether the
FEDERATION's risk profile leans brittlely on one book's full-strength
presence — a keystone created by the merge itself.  So this probe re-runs
the winner with each book's blend contribution scaled to 0.5x its capital
weight (half-strength, not full drop), 2 engine runs, and reports the full
metric deltas.

Halving one book's exposure mechanically lowers return and gross risk — that
direction of movement is expected and not gated.  The keystone signature is
RISK moving the WRONG way when a book is weakened (the weakened book was
hedging/stabilizing the other).  PRE-REGISTERED heuristics (this is a cheap
sanity probe, not a lock gate; both thresholds echo the battery's other
conventions — the 3pp DD flip from rt_perturbation, the negY==0 bar from
H-FED-1):
  FAIL (NEW KEYSTONE) if either half-strength run
    * raises worst-mark DD by more than 3pp over the winner's, or
    * turns any calendar year negative (the winner has negY == 0 by its
      pre-registered bars).
  PASS otherwise.

Usage:
  python3 rt_loo.py <results.json> <grid-key> [--skip-bootstrap]

Writes research/outputs/redteam/rt_loo.json and prints one greppable
`RT_VERDICT [rt_loo] ...` line.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rt_lib  # noqa: E402

SCRIPT = "rt_loo"
DD_KEYSTONE_PP = 3.0     # pre-registered: half-strength dDD > +3pp => keystone
HALF = 0.5               # half-strength, not full drop (full drop = parent)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path,
                    help="H-FED results JSON holding the winner")
    ap.add_argument("key", help="grid key of the winning config")
    ap.add_argument("--skip-bootstrap", action="store_true",
                    help="skip the house breach bootstrap per run")
    args = ap.parse_args(argv)
    t0 = time.time()

    cfg, entry, _ = rt_lib.load_winner(args.results, args.key)
    base = {k: entry[k] for k in ("cagr", "maxdd_worst", "sharpe")}
    rt_lib.log(SCRIPT, f"winner {args.key}: {dataclasses.asdict(cfg)} | "
               f"CAGR {base['cagr']:+.4f} DDw {base['maxdd_worst']:.4f} "
               f"Sh {base['sharpe']:.3f}")

    ses = rt_lib.EngineSession()
    runs: dict[str, dict] = {}
    keystone_hits: list[str] = []
    for tag, scales in (("half_v7", {"scale_v7": HALF}),
                        ("half_v34", {"scale_v34": HALF})):
        row = ses.run(cfg, label=f"rt_loo_{tag}",
                      run_bootstrap=not args.skip_bootstrap, **scales)
        d_dd = (row["maxdd_worst"] - base["maxdd_worst"]) * 100
        d_sh = row["sharpe"] - base["sharpe"]
        d_cagr = (row["cagr"] - base["cagr"]) * 100
        keystone = d_dd > DD_KEYSTONE_PP or row["n_neg_years"] > 0
        row.update({"delta_dd_pp": d_dd, "delta_sharpe": d_sh,
                    "delta_cagr_pp": d_cagr, "keystone": bool(keystone)})
        runs[tag] = row
        if keystone:
            keystone_hits.append(
                f"{tag}(dDD{d_dd:+.1f}pp,negY{row['n_neg_years']})")
        rt_lib.log(SCRIPT, f"{tag}: dCAGR {d_cagr:+.2f}pp | dDD "
                   f"{d_dd:+.2f}pp | dSh {d_sh:+.3f} | negY "
                   f"{row['n_neg_years']} | "
                   f"{'KEYSTONE' if keystone else 'ok'}")

    if keystone_hits:
        status = "FAIL"
        reason = ("NEW KEYSTONE: " + ", ".join(keystone_hits)
                  + f" — weakening a book moves risk the wrong way "
                    f"(dDD>+{DD_KEYSTONE_PP}pp or negY>0)")
    else:
        status = "PASS"
        reason = ("no new keystone: both half-strength runs keep worst-mark "
                  f"DD within +{DD_KEYSTONE_PP}pp and negY == 0 "
                  "(full-drop LOO = the parents, see composite benchmark)")

    rt_lib.write_results(SCRIPT, {
        "script": SCRIPT,
        "args": {"results": str(args.results), "key": args.key,
                 "skip_bootstrap": args.skip_bootstrap},
        "winner": {"config": dataclasses.asdict(cfg), "metrics": base},
        "thresholds": {"dd_keystone_pp": DD_KEYSTONE_PP,
                       "neg_years_max": 0, "half_strength": HALF},
        "runs": runs,
        "verdict": status, "reason": reason,
        "elapsed_s": time.time() - t0,
    })
    return rt_lib.verdict(SCRIPT, status, reason)


if __name__ == "__main__":
    sys.exit(main())
