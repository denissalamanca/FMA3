#!/usr/bin/env python3
"""rt_fixed_schedule — PROTOCOL.md §6(b) / §5.3: the fixed-schedule ablation.

The NSF5 house discriminator for schedule-dependent winners, run on WINNERS
only (never as a rescue for failures): freeze the federation re-split dates
from the winner's recorded events list and re-run the record engine with
those dates as UNCONDITIONAL edges — no band-trigger logic.

PRE-REGISTERED RULE: if the frozen-schedule variant reproduces >= 80% of the
winner's CAGR rebalancing benefit over the static H-FED-1 baseline at the
same w, the trigger CONDITIONALITY is not the edge (the value is the
schedule/cadence itself — rebalance-chaos territory) and the
conditional-trigger story must be dropped from the whitepaper.  Reported
honestly either way:  ratio >= 0.80 => FAIL, ratio < 0.80 => PASS.

WHY TWO FROZEN RUNS (an FMA3-specific subtlety, documented up front):
H-FED-2's band trigger fires on the BOOKKEEPING sub-equities, which are pure
functions of the two parents' native curves — there is NO feedback from the
realized joint account into the trigger.  A literal replay of the winner's
own event dates through unconditional edges is therefore bit-identical to
the winner by construction (unlike NSF5's in-engine band book, where
re-splits move real capital and feed back).  So this script runs:

  (1) "frozen_replay"  — the literal ablation, kept as a MECHANICS IDENTITY
      CHECK (must reproduce the winner's numbers; a mismatch means the
      bookkeeping replication is broken => hard FAIL).  Skippable with
      --skip-replay to save an engine pass.
  (2) "matched_cadence" — the DISCRIMINATING frozen schedule: the same
      NUMBER of unconditional edges placed evenly across the sample at
      server midnights, chosen blind to any trajectory.  The pre-registered
      80% rule is applied to THIS run: if a trajectory-blind schedule of the
      same cadence reproduces the benefit, the trigger's conditionality
      (dates chosen by watching book divergence) is not the edge.

Engine passes: 2 (1 with --skip-replay).

Usage:
  python3 rt_fixed_schedule.py <hfed2_results.json> <grid-key>
                               [--skip-replay] [--skip-bootstrap]

Writes research/outputs/redteam/rt_fixed_schedule.json and prints one
greppable `RT_VERDICT [rt_fixed_schedule] ...` line (NOT_APPLICABLE for
static/quarterly winners — nothing conditional to freeze).
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rt_lib  # noqa: E402

SCRIPT = "rt_fixed_schedule"
BENEFIT_REPRO = 0.80    # pre-registered: frozen benefit ratio >= 80% => FAIL
# identity-check tolerances for the literal replay (identical float paths
# should match exactly; these absorb benign re-association only)
REPLAY_RTOL_EQUITY = 1e-6
REPLAY_ATOL_DD = 1e-6


def matched_cadence_edges(hours: pd.DatetimeIndex, n: int) -> list[pd.Timestamp]:
    """n unconditional re-split dates, evenly spaced, trajectory-blind.

    Server midnights (the band's own act-time convention), positioned at
    k/(n+1) fractions of the sample span — a schedule anyone could have
    written down at t0 without looking at any curve.
    """
    t_lo = hours[0].normalize() + pd.Timedelta(days=1)
    t_hi = hours[-1].normalize()
    span = t_hi - t_lo
    return [(t_lo + span * ((k + 1) / (n + 1))).normalize()
            for k in range(n)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path,
                    help="hfed2_results.json holding the rebalanced winner")
    ap.add_argument("key", help="grid key of the winning variant")
    ap.add_argument("--skip-replay", action="store_true",
                    help="skip the literal-replay identity check "
                         "(saves one engine pass)")
    ap.add_argument("--skip-bootstrap", action="store_true",
                    help="skip the house breach bootstrap per run")
    args = ap.parse_args(argv)
    t0 = time.time()

    cfg, entry, data = rt_lib.load_winner(args.results, args.key)
    payload: dict = {
        "script": SCRIPT,
        "args": {"results": str(args.results), "key": args.key,
                 "skip_replay": args.skip_replay,
                 "skip_bootstrap": args.skip_bootstrap},
        "winner": {"config": dataclasses.asdict(cfg)},
        "threshold_benefit_repro": BENEFIT_REPRO,
    }

    if cfg.kind != "band":
        reason = (f"winner kind {cfg.kind!r} has no conditional trigger to "
                  "freeze (static: no schedule; quarterly: already "
                  "unconditional)")
        payload.update({"verdict": "NOT_APPLICABLE", "reason": reason})
        rt_lib.write_results(SCRIPT, payload)
        return rt_lib.verdict(SCRIPT, "NOT_APPLICABLE", reason)

    events = entry.get("events") or []
    if not events:
        reason = "winner fired 0 re-splits; nothing to freeze"
        payload.update({"verdict": "NOT_APPLICABLE", "reason": reason})
        rt_lib.write_results(SCRIPT, payload)
        return rt_lib.verdict(SCRIPT, "NOT_APPLICABLE", reason)

    static = data["base"]["static"]     # H-FED-1 baseline at the same w
    benefit = entry["cagr"] - static["cagr"]
    payload["winner"].update({
        "cagr": entry["cagr"], "maxdd_worst": entry["maxdd_worst"],
        "sharpe": entry["sharpe"], "n_events": len(events)})
    payload["static_baseline"] = {k: static[k] for k in
                                  ("cagr", "maxdd_worst", "sharpe")}
    payload["benefit_cagr_pp"] = benefit * 100
    if benefit <= 0:
        reason = (f"winner shows no CAGR benefit over static "
                  f"({benefit * 100:+.2f}pp) — nothing to attribute")
        payload.update({"verdict": "NOT_APPLICABLE", "reason": reason})
        rt_lib.write_results(SCRIPT, payload)
        return rt_lib.verdict(SCRIPT, "NOT_APPLICABLE", reason)

    acts = [pd.Timestamp(e["act"]) for e in events]
    rt_lib.log(SCRIPT, f"winner {args.key}: {len(acts)} re-splits, benefit "
               f"{benefit * 100:+.2f}pp CAGR over static")
    ses = rt_lib.EngineSession()

    if not args.skip_replay:
        replay = ses.run(cfg, "rt_fixedsched_replay", fixed_edges=acts,
                         run_bootstrap=not args.skip_bootstrap)
        payload["frozen_replay"] = replay
        eq_ok = (abs(replay["final_equity"] / entry["final_equity"] - 1.0)
                 < REPLAY_RTOL_EQUITY)
        dd_ok = (abs(replay["maxdd_worst"] - entry["maxdd_worst"])
                 < REPLAY_ATOL_DD)
        if not (eq_ok and dd_ok):
            reason = ("REPLAY_MISMATCH: literal frozen replay of the "
                      "winner's own dates does not reproduce the winner "
                      f"(final {replay['final_equity']:.2f} vs "
                      f"{entry['final_equity']:.2f}, DDw "
                      f"{replay['maxdd_worst']:.6f} vs "
                      f"{entry['maxdd_worst']:.6f}) — bookkeeping "
                      "replication broken, ablation numbers untrustworthy")
            payload.update({"verdict": "FAIL", "reason": reason})
            rt_lib.write_results(SCRIPT, payload)
            return rt_lib.verdict(SCRIPT, "FAIL", reason)
        rt_lib.log(SCRIPT, "replay identity check OK (bookkeeping replica "
                   "reproduces the winner)")

    sched = matched_cadence_edges(ses.hours, len(acts))
    frozen = ses.run(cfg, "rt_fixedsched_matched_cadence", fixed_edges=sched,
                     run_bootstrap=not args.skip_bootstrap)
    payload["matched_cadence"] = frozen

    ratio = (frozen["cagr"] - static["cagr"]) / benefit
    payload["benefit_ratio"] = ratio
    if ratio >= BENEFIT_REPRO:
        status = "FAIL"
        reason = (f"trigger CONDITIONALITY is NOT the edge: a trajectory-"
                  f"blind schedule of the same cadence reproduces "
                  f"{ratio:.0%} (>= {BENEFIT_REPRO:.0%}) of the "
                  f"{benefit * 100:+.2f}pp rebalancing benefit")
    else:
        status = "PASS"
        reason = (f"trigger conditionality carries the edge: matched-cadence "
                  f"unconditional schedule reproduces only {ratio:.0%} "
                  f"(< {BENEFIT_REPRO:.0%}) of the benefit")

    payload.update({"verdict": status, "reason": reason,
                    "elapsed_s": time.time() - t0})
    rt_lib.write_results(SCRIPT, payload)
    return rt_lib.verdict(SCRIPT, status, reason)


if __name__ == "__main__":
    sys.exit(main())
