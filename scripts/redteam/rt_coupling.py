#!/usr/bin/env python3
"""rt_coupling — PROTOCOL.md §6(g) / §5.7: the anti-coupling chaos probe.

NSF5's V7.1 chaos study established that rebalance timing is chaotically
equity-sensitive: a EUR 128 perturbation on the EUR 10,000 account shifted
the single-account overlay-ring outcome by -EUR 59k.  PROTOCOL §5.7 makes a
±EUR 128 perturbation mandatory for any adopted federation mechanic: the
H-FED bookkeeping isolates each book's internal state by construction, but
the band trigger watches the RELATIVE sub-equities, so a seed perturbation
can shift re-split dates — the chaos channel this probe exercises.

The probe: re-run the winner with ONE sub-book's bookkeeping seed perturbed
by +128/10000 and -128/10000 (the NSF5 chaos-probe convention, both
directions; the re-split TARGET stays the registered (w, 1-w) — only the
seed moves).

PRE-REGISTERED THRESHOLDS (a chaotic federation is undeployable):
  PASS iff BOTH probes satisfy
    |final_equity / final_equity_winner - 1| < 5%      and
    |maxDD_worst  - maxDD_worst_winner|      < 1pp.

Engine passes: 2.

Usage:
  python3 rt_coupling.py <results.json> <grid-key>
                         [--book {v7,v34}] [--skip-bootstrap]

Writes research/outputs/redteam/rt_coupling.json and prints one greppable
`RT_VERDICT [rt_coupling] ...` line.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rt_lib  # noqa: E402

SCRIPT = "rt_coupling"
FINAL_EQUITY_TOL = 0.05   # pre-registered: |relative final-equity shift| < 5%
DD_TOL = 0.01             # pre-registered: |worst-mark DD shift| < 1pp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path,
                    help="H-FED results JSON holding the winner")
    ap.add_argument("key", help="grid key of the winning config")
    ap.add_argument("--book", choices=("v7", "v34"), default="v7",
                    help="which sub-book's seed to perturb (default v7 — "
                         "the band mechanics' chaos-prone side)")
    ap.add_argument("--skip-bootstrap", action="store_true",
                    help="skip the house breach bootstrap per run")
    args = ap.parse_args(argv)
    t0 = time.time()

    cfg, entry, _ = rt_lib.load_winner(args.results, args.key)
    delta = rt_lib.CHAOS_SEED_DELTA
    base_final = float(entry["final_equity"])
    base_dd = float(entry["maxdd_worst"])
    rt_lib.log(SCRIPT, f"winner {args.key}: {dataclasses.asdict(cfg)} | "
               f"final EUR {base_final:,.0f} | DDw {base_dd:.4f} | "
               f"probing {args.book} seed by ±{delta:.4f} (±EUR128/10k)")

    ses = rt_lib.EngineSession()
    probes: dict[str, dict] = {}
    all_ok = True
    for sign, tag in ((+1, "plus128"), (-1, "minus128")):
        if args.book == "v7":
            seed_a, seed_b = cfg.w_v7 + sign * delta, None
        else:
            seed_a, seed_b = None, (1.0 - cfg.w_v7) + sign * delta
        row = ses.run(cfg, label=f"rt_coupling_{args.book}_{tag}",
                      seed_a=seed_a, seed_b=seed_b,
                      run_bootstrap=not args.skip_bootstrap)
        d_final = row["final_equity"] / base_final - 1.0
        d_dd = row["maxdd_worst"] - base_dd
        ok = abs(d_final) < FINAL_EQUITY_TOL and abs(d_dd) < DD_TOL
        row.update({"delta_final_rel": d_final, "delta_dd": d_dd,
                    "within_tolerance": bool(ok)})
        probes[tag] = row
        all_ok &= ok
        rt_lib.log(SCRIPT, f"{tag}: dFinal {d_final:+.2%} | dDD "
                   f"{d_dd * 100:+.2f}pp | events {row['n_events']} | "
                   f"{'ok' if ok else 'CHAOTIC'}")

    if all_ok:
        status = "PASS"
        reason = (f"federation is chaos-stable: both ±EUR128 {args.book}-seed "
                  f"probes within |dFinal|<{FINAL_EQUITY_TOL:.0%} and "
                  f"|dDD|<{DD_TOL * 100:.0f}pp")
    else:
        worst = max(probes.values(),
                    key=lambda r: abs(r["delta_final_rel"]))
        status = "FAIL"
        reason = (f"CHAOTIC coupling: ±EUR128 seed perturbation moves the "
                  f"outcome beyond tolerance (worst dFinal "
                  f"{worst['delta_final_rel']:+.2%}, dDD "
                  f"{worst['delta_dd'] * 100:+.2f}pp) — undeployable per "
                  "NSF5 chaos doctrine")

    rt_lib.write_results(SCRIPT, {
        "script": SCRIPT,
        "args": {"results": str(args.results), "key": args.key,
                 "book": args.book, "skip_bootstrap": args.skip_bootstrap},
        "winner": {"config": dataclasses.asdict(cfg),
                   "final_equity": base_final, "maxdd_worst": base_dd},
        "seed_delta": delta,
        "thresholds": {"final_equity_rel": FINAL_EQUITY_TOL, "dd": DD_TOL},
        "probes": probes,
        "verdict": status, "reason": reason,
        "elapsed_s": time.time() - t0,
    })
    return rt_lib.verdict(SCRIPT, status, reason)


if __name__ == "__main__":
    sys.exit(main())
