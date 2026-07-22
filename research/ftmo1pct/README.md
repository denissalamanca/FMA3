# FTMO 1%-per-idea kill engine (research fork)

## What
A physical fork of the FMA3 engine of record (`engine/record_engine_ext.py`,
the Python 1m worst-mark engine) that adds a per-CLUSTER trailing-window
loss-kill overlay on top of the FTMO daily circuit breaker:

- `kill_engine.py` — `_run_chunk_kill` (verbatim copy of `_run_chunk_stop`,
  parent lines 444-600, + hooks A-D), `simulate_account_1m_kill` (copy of the
  driver, 607-776), `run_record_kill` (copy of the wrapper, 779-842). Data
  loaders / eurq / swap builders / core are IMPORTED from the parent, never
  copied.
- `run_sweep.py` — the gate + the v0.2 parameter sweep.
- `selftest_kill.py` — unit-style semantics traces (kill/cooldown/window
  boundary, weekend continuity, ts-based expiry, pend-completeness).
- `out/` — results JSON + per-run curves.

## Why
RECON-17 analytics: concentration is the #1 risk (gold 44% of P&L). The FTMO
account needs an idea-level loss cap: no single trade idea may lose more than
1% of the account. This fork measures what such a rule costs (equity
retention) and what it buys, and counts honest 1m-granularity crossings of
the hard 1% line ("violations" — what FTMO would actually see).

## Rule (v0.2 — OWNER-CLARIFIED; supersedes the v0.1 "idea since inception"
## reading, which was a misinterpretation)
Owner's own example, verbatim: gold+silver on a 100k account; combined DD
hits -1,001 = breach; auto-cut at -800 at 16:20; no new gold/silver until
17:20.

For cluster C (13 idea-units + EURSEK singleton; table in
`kill_engine.py::CLUSTERS`, asserted against the live fed columns) at
minute t:

- `FLOAT_C(t)` = worst-marked unrealized P&L of C's OPEN net positions,
  measured from each net position's entry. While a position stays open its
  meter anchors at entry — NO hourly re-anchor for held trades.
- `REAL1H_C(t)` = realized P&L (incl. commissions) booked on C's symbols in
  the trailing 60 minutes, timestamp-based (window `(t-60min, t]`, survives
  union-grid gaps/weekends). `real_mode='net'` (default: profits offset —
  the owner's "1% risk combined") or `'loss_only'` (conservative variant).
- `IDEA_DD_C(t) = FLOAT_C(t) + REAL1H_C(t)`.
- KILL when `IDEA_DD_C(t) <= -kill_pct x BALANCE(t)`; ref = CURRENT balance
  (the owner's example is 1% of the 100k account; in deployment monthly
  withdrawals keep balance near base, so current-balance is the faithful
  frame). The balance is snapshot once per minute before the cluster loop,
  so same-minute kills are order-invariant across clusters.
- On kill: flatten ONLY C at the minute's worst-side prices + commission
  (the existing breaker flatten pattern), then a 60-min cooldown
  (kill 16:20 -> first re-entry 17:20; the kill's realized loss ages out of
  the trailing window exactly at re-entry). The kill check runs AFTER the
  daily breaker (ordering unchanged; the breaker is NOT re-checked
  post-kill inside the same minute — a documented commission/overshoot-
  sized timing window, see the module docstring).
- VIOLATION (the FTMO-visible number): any episode where net-mode
  `IDEA_DD_C <= -1.0% x balance` before/at flatten, counted once per
  episode (one continuous below-the-line excursion; kill/breaker/stop-out
  flatten fills enter REAL1H before the check, so gap overshoot past the
  hard 1% is counted, not erased).
- There is NO months-long idea state: no inception ref freezing, no
  realized-since-inception meter. Cluster bookkeeping = a 60-slot realized
  ring (keyed by absolute minute) + cooldown + the violation-episode flag.

## Labeled approximations
- Per-symbol NETTING with volume-weighted average entry vs the live hedging
  account's per-ticket accounting — FLOAT_C is the netted meter.
- Worst marks are per-leg intraminute extremes summed across legs (each
  leg's own worst print, not one simultaneous timestamp — the engine of
  record's existing convention).
- Swap carry is NOT attributed to REAL1H (balance only); accounted
  separately in the pend-completeness identity.
- `loss_only` aggregates at 1-minute cluster granularity (a minute's fills
  on one cluster net before `min(., 0)`).
- 1-minute granularity: intraminute overshoot past the kill line is kept,
  not erased (honest gap-through, same physics as the daily breaker).

## Gate
Overlay OFF (`kill_pct=None`, `violations_only=False`) must reproduce the
model/v3 FTMO golden BIT-EXACTLY (`fed=static_blend(0.70)`, s=0.70, initial
100k, daily_stop_x=3.0 -> final equity 1,332,404.1921628967, maxdd_worst
0.13326785098278104, n_daily_stops 26) before any kill-on number is
reported. The 80k/31-symbol FTMO-real recipe (golden 1,097,683.8441098437)
was NOT found in scripts/run_hftmo1.py or verify_record_engine_ext.py, so
the sweep runs at the 100k config.

## Evidence (selftest_kill.py)
- 16:20/17:20 trace: kill at the crossing minute, flat through +59 min,
  clean re-entry at +60 with the kill loss aged out of the window exactly
  at re-entry (no instant re-kill), violation counted once per episode.
- Weekend continuity: a held cluster survives a 2-day union-grid gap with
  lots/entry untouched; FLOAT stays anchored at the ORIGINAL entry (a
  post-gap print crossing -1% only from the original entry IS counted).
- Cooldown expiry across gaps is timestamp-based (first post-gap minute may
  re-enter), never "grid minutes elapsed".
- Pend-completeness: initial + sum(all REAL1H ring flushes) + swaps ==
  final balance (exact on the synthetic trace; residual reported per real
  run in `out/sweep_results_v02.json` -> `pend_check`).

## Provenance
`manifest.json` pins sha256 of the parent engine and this fork. Parent is
NEVER modified. Engine of record remains `engine/record_engine_ext.py`;
this directory is research-only. v0.1 (inception-idea) results in
`out/sweep_results.json` are RETIRED — superseded by
`out/sweep_results_v02.json`.

## FROZEN CONFIG — owner decision 2026-07-22
**Kill line = -0.8% of current balance; daily breaker stays 3.0%** (run `ftmo1pct_a_net_80bp`):
retention 75.4% / CAGR 46.9% (-7.1pp) / 66.5 kills/yr / 2.3 desk-visible violations/yr /
0 daily-5% breach days 2020-2025 (worst day 3.22%). Grid also measured 0.9% (6.2 viol/yr,
rejected) and a 4% breaker (retention-neutral, halves crisis headroom, rejected; note the
engine's COVID-blindness understates crisis stress). 0.7% (1.3 viol/yr, same retention as
0.8%) noted as the compliance knee if FTMO ever tightens. Next: EA idea-breaker
(FTMO preset ONLY — IC unaffected), RECON-19 redeploy.
