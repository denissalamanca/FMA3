# FTMO EA v1.x campaign — close the gap to IC without breaking FTMO rules

**Owner goal (2026-07-10, verbatim intent):** *"find the best way to match the
performance as much as possible to the IC's EA but without failing the FTMO
challenge's rules."* IC book/EA is FROZEN (owner instruction; the preset
split). All levers below are FTMO-track only. H-TAIL-1 withdrawn (owner
scope instruction; partial results unread).

**CRITERIA COMMITTED 2026-07-10 before any campaign number.**

## The honest success metric (committed now)

IC compounds on-account (+170.2% CAGR). A funded FTMO account CANNOT compound
on-account — profits are withdrawn and FTMO's limits stay anchored to the
fixed base. The rule-accurate comparison is therefore:

> **FTMO cash yield** = expected annualized withdrawal rate on the funded
> account (fixed €100k base, monthly withdrawal-to-base ops, 80–90% profit
> split, FTMO scaling plan +25% capital / 4 profitable months) — reported
> against IC's on-account CAGR, with the structural difference stated, plus
> the **gap-closed ratio** vs the FMA3-005c baseline (s=0.4, ~+30.7% gross).

Hard constraint for every lever: **P(breach either FTMO rule within 12
months) ≤ 0.05** under the rule-accurate model, with the FULL probe walk-down
(±20% w drift; FMA3-005c standing amendment), 0 historical breaches, negY 0,
negQ ≤ 1.

## Ladder (one lever per ledger entry)

### FMA3-009 — rule-accurate FTMO model v3 (payout-cycle; run FIRST, engine-free)
The 005b static test (peak-relative %DD < 10%) is STRICTER than FTMO's actual
rule (absolute floor: equity ≥ 90% × initial; the buffer grows with unpaid
profits). Model v3, committed: monthly payout-to-base cycle; within each
month, floor = 0.90 × base absolute; daily rule = day dip vs prev close
> 5% of base (fixed-base %, as 005b); bootstrap = 10k × 12-month paths of
month-blocks. Re-score the SAVED curves (s 0.4–0.8 + probes) engine-free.
**Bar:** none to adopt (it is the rule-accurate scoring, replacing 005b's
conservative approximation — the correction is documented either way);
re-ship the FTMO dial at the largest compliant (w,s) already computed.

### FMA3-008 — H-FTMO-1 daily circuit breaker (owner lever)
As ROADMAP.md H-FTMO-1: engine hook (flatten at day-anchor −x%, x ∈ {3.0,
3.5, 4.0}%), bit-identical at x=∞ verification gate, gap-through residual
measured, re-entry spread cost measured. **Bar:** shipped FTMO point must
beat the FMA3-009 ship by ≥ +8pp gross CAGR at the ≤ 0.05 survival bar.

### FMA3-010 — FTMO-specific (w, s) joint grid
The federation w becomes preset-specific (config-only; both parent books
internally unchanged). Evidence seed: the w56 drift probe at s=0.5 PASSED
everything (P(breach) 0.0069) — v3.4-tilt suppresses exactly the dip days
that bind. Pre-registered grid: w ∈ {0.40, 0.50, 0.60, 0.70} × s ∈ {0.5,
0.6, 0.7, 0.8, 0.9, 1.0} evaluated under model v3 + the breaker (if FMA3-008
adopted), top-down by expected yield, full probe walk at the candidate.
**Bar:** ship = max funded cash yield s.t. the hard constraint; adopt only if
≥ +8pp gross over the FMA3-008 ship (else the extra config axis isn't paid).
NOTE: grid cells needing new engine runs are bounded (~12–18 passes); cells
already computed (w70 row) are reused.

### FMA3-011 — phase-specific dials (challenge sprint vs funded steady-state)
The challenge phases (P1 +10%, P2 +5%) optimize a different objective:
maximize P(pass without breach) and minimize days-at-risk — NOT 12-month
survival. Committed: pick the P1/P2 dial by max P(pass) with P(breach during
phase) ≤ 0.05; the funded dial from FMA3-010 takes over after funding.
Config-only. **Bar:** P1 pass probability must improve ≥ +2pp over running
the funded dial through the challenge, else DECLINE (one dial is simpler).

### Deliverables at campaign end
Updated PRESETS.md + registry rows · re-shipped FTMO dial + DASHBOARD_FTMO
regeneration · an FTMO_STRATEGY.md package doc (v7 standard) with the yield-
vs-IC comparison table and the guardian-EA spec (built only on adoption) ·
whitepaper addendum.

## Out of scope (unchanged)
Any IC-track change; any parent-book internal change; anything on the kill
lists; compounding-on-account FTMO fantasies (the rules forbid it — model
reality).
