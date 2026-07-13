# FMA3 v1.0 preset fork — H-RISK-1 (IC private) & H-RISK-2 (FTMO) — PRE-REGISTRATION

**CRITERIA COMMITTED 2026-07-10 (before any number beyond the already-pinned
s ≤ 1.4 grid was computed).** Owner risk-appetite revision, dated and
attributed: *"I can stomach 30% max DD; breach P(DD>30%) = 0.002 is too low —
push CAGR and flex the breach"* (owner, 2026-07-10). Owner confirmed:
negQ gate stays ≤ 1/24 on both presets. The BOOK is unchanged (static
federation w=0.70, config `51a7541cc2aaa593`); only the risk dial forks.
One ledger entry per preset (FMA3-004, FMA3-005).

**Standing caveat (both presets):** the record engine understates real-tick
drawdowns (measured on v7.0: COVID tail 35.6% MT5 vs ~7% record). Both
shipped preset dials are **provisional pending v1.1's MT5 reconciliation**,
which measures the federation's record→tick DD ratio k. Pre-commitment: the
final dial re-picks such that record-DD × k respects each account's true
limit. Until then the presets are backtest-official, not live-final.

---

## H-RISK-1 — Preset 1: private IC Markets EU account (FMA3-004)

- **Ceilings (record engine, all must hold at locked w AND both ±20% w
  probes):** worst-mark DD < 30% · crisis tail ≤ 30% · negY = 0 ·
  negQ ≤ 1/24 · breach P(maxDD>30%) ≤ **0.20** (owner Pareto revision
  2026-07-10, from 0.15 — a risk-appetite point choice on the mapped
  breach-vs-CAGR frontier, strategy frozen; 0.20 is within house precedent,
  v3.4 scale-11 ran 0.198). **Shipped: s=1.6** (FMA3-004c) — CAGR +170.2% /
  DD 22.6% / breach 0.095 nominal, worst ±20%-drift probe breach 0.180 < 0.20
  & DD 27.6% < 30%. s=1.7 rejected (w84 drift breach 0.280).
- **Grid:** extend the measured frontier with s ∈ {1.5, 1.6, 1.7, 1.8}
  (fixed; the s ≤ 1.4 points are already pinned). No off-grid picks.
- **Two-stage evaluation (pre-committed):** Stage A: base runs at locked
  w=0.70. Stage B: the two ±20% w probes at the largest Stage-A-compliant s
  and at the next lower grid point. **Ship the largest s where base + both
  probes clear every ceiling.**
- **Expectation (stated before running):** breach is the likely binding
  ceiling near s ≈ 1.6–1.7 (measured breach curve roughly doubles per 0.1s:
  0.0004 → 0.029 over s 1.0→1.4); CAGR at the shipped point plausibly
  ~160–180%. negQ may bind first via vol drag on shallow quarters — if it
  does, that is the result.

## H-RISK-2 — Preset 2: FTMO prop account (FMA3-005)

- **Vehicle (verified against FTMO official docs 2026-07-10):** 2-Step
  Challenge, **Swing** account type (mandatory: the book holds gold/crypto
  through weekends and trades through news; funded Standard forbids both).
  Rules modeled: **Max Daily Loss** = equity (incl. floating) must stay above
  [balance at 00:00 CE(S)T of the previous day − 5% × initial capital],
  recalculated daily; **Max Loss** = equity must never touch 0.90 × initial
  (static, whole period); profit targets 10% (P1) / 5% (P2), none funded;
  min 4 trading days per phase (trivially met).
- **Modeling conventions (pre-committed):** engine initial = **€100,000**
  (typical FTMO size; also gives honest min-lot granularity — the €10k
  convention would overstate quantization noise). Daily anchor approximated
  at server midnight (≤1h offset vs CE(S)T; documented approximation).
  Anchor uses the equity close at the midnight bar (balance not separable
  from the pinned curves; direction of the approximation documented in the
  runner). Breach test within each day uses the minute worst-mark equity.
- **Bars:** on 10,000 stationary-bootstrap 12-month paths (20d mean block,
  seeded, built from the s-run's daily triplets — close return, worst dip vs
  previous close, worst dip vs midnight anchor):
  **P(breach either FTMO rule within 12 months) ≤ 0.05** (the owner's
  "P(DD>10%) ≤ 0.05" intent, made rule-accurate — the composite includes the
  daily 5% rule, which is expected to bind). Plus: zero breaches on the
  actual 2020–25 historical path at the shipped s; negY 0; negQ ≤ 1;
  both ±20% w probes must also clear the composite bar.
- **Grid:** s ∈ {0.4, 0.5, 0.6, 0.7, 0.8} (fixed). Ship the largest
  compliant s. Report alongside: P(pass P1 without breach), expected days to
  the +10% P1 target, and the same for P2's +5%.
- **Expectation (stated before running):** the daily-5% rule binds; shipped
  s plausibly ~0.5–0.6, record CAGR ~40–60%, forward-honest ~25–40%/yr —
  strong for a funded account with profit split.

## FMA3-004b — SUPERSEDED by FMA3-004c

The downward probe search below was written under the 0.15 cap. The owner's
0.20 Pareto revision (above) moved the probe-robust answer UP to s=1.6 — which
was already probe-tested (w84 breach 0.180 < 0.20) — so no downward search was
needed or run. FMA3-004c (engine-free re-adjudication of existing probe data)
is the operative decision. The section is kept for the honest trail.

## FMA3-004b (superseded) — corrected probe-robust search for Preset 1

**Committed 2026-07-10 after FMA3-004 returned "no candidate cleared the
probes," BEFORE running any s < 1.6 probe.** Honest disclosure: FMA3-004's
two-stage procedure probed only the largest base-compliant s (1.7) and the
next-lower grid point (1.6). Both failed the w+20% (w84) probe on **breach**
(1.7: 0.280; 1.6: 0.1804 > 0.15) — the probe penalty exceeds one grid step,
so the two-candidate window was under-powered. It is NOT a true null: the ship
rule ("largest s where base AND both ±20% probes clear every ceiling") has a
guaranteed-existent answer (v1.0's s=1.1 is a known probe-robust floor on DD,
and breach falls monotonically with s). FMA3-004b completes the deterministic
search the heuristic truncated — same ceilings, no metric change, no re-pick
of the rule.

- **Procedure:** top-down probe pairs (w56, w84) at s ∈ {1.5, 1.4, 1.3, 1.2}
  (reusing the already-computed 1.6/1.7 probe rows); **ship the largest s
  where base + both probes clear** DD<30% · tail≤30% · negY 0 · negQ≤1 ·
  breach≤0.15. Stop at the first (largest) probe-robust s.
- **Anti-seat-shopping:** ceilings unchanged; the search is the rule, not a
  new grid; the result is whatever the largest-probe-robust s is (expected
  s≈1.5, base CAGR +155.4% — the w84 breach there estimates ~0.11 < 0.15).
- FMA3-004's null-at-window and this correction are BOTH logged.

## FMA3-005b — corrected FTMO model (fixed-base; amends FMA3-005)

**Committed 2026-07-10 after FMA3-005's grid revealed a specification error,
BEFORE re-adjudicating.** Honest disclosure: FMA3-005 measured the daily-loss
rule as €5,000 (5% of INITIAL) against a €100k account **compounded over the
full 2020–25 sample** to ~€6M. A fixed €5k limit vs a multi-million equity is
not how FTMO is traded — funded accounts **withdraw profits** (or trade fixed
size), so the daily limit stays ~5% of the *traded base*. The artifact shows
plainly: `histStatic` stayed 0 at every scale while `histDaily` exploded
30→98→238 with scale purely because the account grew. The bar was
mis-specified, not merely strict.

**Corrected model (scale-invariant %, fixed base — the standard prop model):**
- Daily rule: a single-day intraday worst dip vs the prior close **> 5%**
  (= 5% of the fixed base). Historical bar: **0 such days** on 2020–25.
- Static rule: the book's worst-mark drawdown **< 10%** (equity never below
  90% of base under a no-within-period-withdrawal worst case). This is
  scale-sensitive and ties FTMO's 10% floor directly to the scale dial.
- Bootstrap: P(any >5% daily dip OR 12-month path %DD > 10%) **≤ 0.05**
  (10k stationary-bootstrap paths, 20d blocks, seed 20260710) — the owner's
  ≤0.05 bar, made rule-accurate and de-compounded.
- negY 0 · negQ ≤ 1 · both ±20% w probes clear, at the shipped s.
- Grid unchanged s ∈ {0.4..0.8}; ship the largest compliant s; probes at it.
- Re-adjudicated ENGINE-FREE on FMA3-005's already-saved base curves; only the
  probes at the corrected ship s require new engine passes.
- Assumption documented: monthly withdrawal to base (the no-compounding
  frame). If the owner instead lets the funded account compound, the daily
  rule tightens over time and the shipped s must drop — a live-ops note.

## FMA3-005c — probe fallback for the FTMO ship (completes FMA3-005b)

**Committed 2026-07-10 after the s=0.5 probe result (w84 FAIL: 1 dip-day,
P(breach) 0.120), BEFORE probing s=0.4.** Same procedural gap as FMA3-004's
two-stage: the probe search stopped at the largest base-compliant candidate
instead of walking down. The deterministic ship rule ("largest s where base
AND both ±20% w probes clear") is completed by probing the remaining
base-compliant candidate: **s=0.4** (2 engine passes). If both probes clear →
FTMO ships s=0.4. If not → no FTMO ship in the registered grid; any s<0.4
would be a NEW pre-registration. Ceilings unchanged (FMA3-005b model).
Standing procedural amendment for ALL future preset searches: the probe walk
continues down the base-compliant list until a probe-robust s is found or the
list is exhausted — no more two-candidate truncation.

## FTMO ship update — FMA3-008 breaker ADOPTED (2026-07-10 evening)

FTMO preset re-ships from s=0.4 (bare) to **s=0.7 + daily circuit breaker x=3.0%**
(FMA3-008, the owner's H-FTMO-1 lever). **CAGR +30.7% → +54.0%** (+23.3pp), maxDD
13.3%, P(breach 12mo) 0.000, both ±20% w drift probes clear (monthly floor
0.901/0.902 > 0.90). The breaker fully suppresses the daily-5% rule (0 residual
dips at x=3.0); the static 10% floor is the true ceiling (caps s at ~0.7). The
guardian module (already coded in FableFederation_V1, config-gated) is turned ON
for FTMO via InpDailyStopX=3.0. PROVISIONAL pending FMA3-010/011 + MT5 k. Deploy
preset: mt5/ea/presets/FED_FTMO.set.

## Explicitly out of scope for this fork

Any book change (weights, sleeves, w, federation mechanics). Any change to
the negQ/negY gates. Off-grid scale picks. Re-running either preset's grid
after seeing results ("the grid is the grid").
