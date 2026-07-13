# FMA3 v1.0 — 2026H1 one-shot forward confirmation (PRE-REGISTRATION)

**CRITERIA COMMITTED: 2026-07-10 14:10, before any FMA3 code has computed any
number on any 2026 data.** This window is consumed by this test regardless of
outcome (PROTOCOL.md §4); there is no second look, no re-run with fixes, no
"the data was bad" rescue beyond the caveats disclosed below.

## Configuration under test

FMA3 v1.0 exactly as locked (`strategy_fma3.py`, static federation w=0.70,
s=1.1, config-hashed) — **fresh start**: sub-books seeded at (0.70, 0.30) of
€10,000 on 2026-01-01, mirroring how a live deployment would begin. No
carry-over of 2020–25 book state (beyond signal warm-up from history, which
the fwd caches provide by construction).

## Window & feed (disclosed limitations, committed in advance)

- 2026-01-01 → 2026-04-30 (the 12-symbol common window; EURUSD/XAUUSD extend
  to 05-31 but the test ends 04-30 for uniformity).
- Duka-feed based (`NSF5/cache/bars_1m_holdout` via `research/fwd_cache_1m/`),
  **USTEC replaced by the USA500 proxy** (corr 0.89, the NSF5 v51_rig
  convention) — the proxy book is NOT the deployed book; this is a
  directional confirmation, not a reconciliation.
- Engine: `engine/record_engine_ext.py` (must be verified bit-identical on
  2020–25 before this test runs).
- 4 months ≈ 85 trading days — statistically weak by construction. The bars
  below are breakdown detectors, not performance targets.

## Honest expectations (stated before looking)

In-sample CAGR +101.4% would imply ≈ +26% over the window; the honest forward
discount (v3.4's own retired-selection convention, Sharpe ~1.2–1.5 vs 2.47
in-sample) implies ≈ +10–20%; 4-month volatility at s=1.1 ≈ ±24%. A negative
window is therefore entirely possible for a healthy book.

## Pre-registered bars

| # | Bar | Rationale |
|---|---|---|
| F1 | Window worst-mark DD < 20.9% | The owner ceiling must hold out-of-sample |
| F2 | Window return > −10% | ≈ −0.5σ under honest expectations; deeper signals breakdown, not noise |
| F3 | No joint stop-out or margin-cap breach event | Deployability |
| F4 | Each sub-book's own window return > −20% | No single-book breakdown masked by the other |

## Pre-registered interpretation

- **4/4 → CONFIRM**: proceed to MT5 demo deployment (owner's machine, the
  deployable arbiter).
- **F1 or F2 fails → INVESTIGATE**: no deployment until the MT5 real-tick run
  adjudicates; the failure is reported as-is in the whitepaper.
- **F3 fails → REJECT** the locked scale; re-open H-FED-3 with the forward
  evidence (a new pre-registration, new ledger entry).
- Any outcome: results go in docs/REGISTRY.md and the whitepaper verbatim.
  The 2026H1 window is marked CONSUMED.

## Execution plan (after the v1.0 pin reproduces)

1. Re-extract the v7 band book on the fwd feed (Duka + USA500 proxy,
   2020→2026-04, warm-started) — its 2026 native curve + fraction matrix.
2. Rebuild FMA2 sleeves on `research_cache_fwd` (their own forward-
   confirmation harness convention) — the v3.4 2026 fraction matrix.
3. Federation matrix for 2026H1 at (0.70, 0.30) fresh seed, s=1.1.
4. One run of `scripts/run_forward_oneshot.py` (gated on this file).
5. Verdict against F1–F4, registry entry, whitepaper section.
