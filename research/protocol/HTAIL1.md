# v1.2 candidate — H-TAIL-1: crisis reinforcement from the cash-park (PRE-REGISTRATION)

**CRITERIA COMMITTED 2026-07-10, before any H-TAIL-1 number was computed.**
Ledger: FMA3-006. One lever: the v3.4 sub-book's crisis sleeve weight is
raised from 0.100 to **×1.5 (0.150)** and **×2.0 (0.200)**, funded from the
0.174 cash-park (remaining park 0.124 / 0.074; all other weights, sleeve
internals, hard-limit rules unchanged — `structural_gold_cap` still keys off
seasonal 0.18). Two variants, one evaluation, DECLINE by default.

**Why (evidence-led):** FMA3-RT's binding constraint is the w+20% probe DD
(17.97% native). Crisis is v3.4's native stress-payer (H14: pays on non-band
cadence; NSF5's band-book kill does not transfer per the cadence-
conditionality ruling — verified in the roadmap red-team). A stronger
stress-payer in the v3.4 residual attacks dDD/dw exactly where it binds.
Honest prior leaning against: crisis's F3 cap was set downward on durability
evidence (2015–19 standalone Sharpe −0.10); program base rate ~1-in-4/6.

## Method (pre-committed)

Per variant m ∈ {1.5, 2.0}:
1. Rebuild the v3.4' book: `combine(sleeves, weights_m) × 10` +
   `apply_hard_limits` (FMA2 machinery, read-only).
2. Run v3.4' ALONE in the record engine (€10k) → its native curve B'_m and
   own metric block (reported for context; no bar on it).
3. Federation blend at w = 0.70 with A (v7 native, unchanged) and B'_m,
   fresh-seed formula identical to v1.0. Native run (s = 1.0) + both ±20% w
   probes.
4. If the mechanism bars (below) pass for a variant, run the shippable
   re-pick for that variant under BOTH preset rule-sets:
   - **P1 track (IC private):** pre-registered fine grid s ∈ {1.30, 1.35,
     …, 2.00} (0.05 steps — the finer step the roadmap red-team required
     for any claim past the 0.1 grid), ceilings = PRESETS.md H-RISK-1
     (DD<30% · tail≤30% · negY 0 · negQ≤1 · breach≤0.15, at locked w AND
     both probes, two-stage).
   - **P2 track (FTMO Swing):** grid s ∈ {0.40 … 0.80} (0.1 steps),
     bars = PRESETS.md H-RISK-2 composite.
5. If both variants pass the mechanism bars, the higher-Sharpe variant at
   w=0.70 native is the candidate (committed tie-break).

## Bars (ALL must pass; DECLINE on any miss)

- **M1 (mechanism):** w_up20 probe worst-mark DD (native s=1.0) improves by
  ≥ 1.5pp vs the v1.0 baseline 17.97%.
- **M2 (cost):** w=0.70 native CAGR cost ≤ 0.5pp vs baseline 89.71%.
- **M3 (no regression):** all FMA3-001 bars still pass at w=0.70 native
  (DD < 20.72%, Sharpe > 2.317, negY 0, negQ 0).
- **A1 (adoption):** the P1-track shippable CAGR improves by ≥ +8pp vs the
  P1 baseline (FMA3-004's shipped point), at no regression of the P2-track
  shippable point (its shipped s and P(breach) no worse).

## Out of scope / anti-rescue

No other weight moves; no crisis-internal changes; no third variant if 1.5
and 2.0 both fail (that is the answer); no re-running FMA3-004/005 grids —
their shipped points are the fixed baselines A1 compares against.
