# V1.0 validation analysis

**FMA3 v1.0 = the static federation locked 2026-07-10: one cross-margined €10k IC Markets EU Raw
account carrying the v7.0 band book at capital share w = 0.70 and the v3.4 fixed-fraction book at
0.30 as never-rebalanced virtual sub-accounts, at global scale s = 1.1 — no cross-book rebalance
(H-FED-2 declined), no new caps (H-CAPS-1 no-op), both parents' sleeves frozen.** Sources of
truth: config = [`strategy_fma3.py`](../../strategy_fma3.py) (**config hash `51a7541cc2aaa593`**);
pin = [`fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json) +
`fma3_v1_pin_curve.parquet`, rebuilt from config alone by
[`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py); engine of record = FMA2's 1-minute
worst-mark single cross-margined account engine via the verified
[`engine/record_engine.py`](../../engine/record_engine.py) wrapper (see
[RECONCILIATION.md](RECONCILIATION.md)). Full battery per the pre-registered
[PROTOCOL.md](../../research/protocol/PROTOCOL.md) /
[HYPOTHESES.md](../../research/protocol/HYPOTHESES.md); ledger in
[docs/REGISTRY.md](../REGISTRY.md); research depth in
[../whitepaper/03_SCORECARD.md](../whitepaper/03_SCORECARD.md).

**All numbers are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick + live
demo are the remaining falsification tests.** The 2020–25 window was mined by both parent
programs before FMA3 existed (FMA2 ≈ low-hundreds of design trials; NSF5 ≈ 7,560 prescreens +
~258 engine tests) and FMA3 added 18 ledger configs on top. Regenerate the battery:
`python3 scripts/eval_fma3_pin.py` (the pin), `research/outputs/redteam/` scripts (Tier 3–5),
`scripts/run_forward_oneshot_native.py` (Tier 6 — hard-gated, will refuse to re-run).

---

## Headline (IC 2020-25, engine of record)

| Metric | **FMA3 v1.0 (federation)** | Composite gate (best parent) | Previous holder | Verdict |
|---|---|---|---|---|
| CAGR | **+101.4%** | > 91.5% | v7.0 @ r8 | ✅ |
| Max DD (worst-mark) | **15.73%** (close 15.62%) | < 21.22% | v7.0 @ r8 | ✅ |
| Sharpe | **2.467** | > 2.267 | v7.0 @ r8 | ✅ |
| COVID crisis tail | **5.36%** | ≤ 5.54% | v7.0 @ r8 | ✅ |
| Negative years | **0 / 6** | == 0 | both parents (tied) | ✅ |
| Negative quarters | **0 / 24** (worst 2022Q4 +2.9%) | ≤ 0 | v7.0 @ r8 (v3.4 had 1) | ✅ |
| Breach P(DD>30%) | **0.0020** | < 0.0118 | v7.0 @ r8 (v3.4: 0.121) | ✅ |
| Final equity (€10k init) | **€665,777** | — | 25,869 trades | — |

**All seven composite dimensions dominate BOTH parents in the engine of record — the first
fully-dominant point in the two programs' combined history**
([composite_benchmark.json](../../research/outputs/composite_benchmark.json),
[fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json)). The owner's original six gates
(secondary scoreboard, straddles-two-engines caveat in
[../whitepaper/03_SCORECARD.md §1.1](../whitepaper/03_SCORECARD.md)) also clear 6/6: CAGR
+101.4% > 96.1, DD 15.73 < 20.9, Sharpe 2.467 > 2.03, tail 5.36 ≤ 35.6, negY 0, negQ 0 ≤ 1.
Yearly (pin): 2020 +137.7%, 2021 +110.9%, **2022 +48.8% (worst)**, 2023 +88.7%, 2024 +94.5%,
2025 +129.7%.

**The binding constraint is the probe-robust scale ceiling.** At the shipped s = 1.1 the w+20%
perturbation probe prices the worst-mark DD at 17.97% × 1.1 ≈ **19.8% vs the 20.9% owner
ceiling** — ~1.1pp of headroom; at s = 1.2 the same probe prices ≈ 21.6% and breaches. Ship at
s ≤ 1.1 strictly, never higher: the ceiling-rule pick s = 1.4 (+140.8% CAGR) is compliant at the
locked w but **not probe-robust** (Tier 3 adjudication below).

---

## Scorecard — 6-tier battery vs the gates

| Tier | Test | Result | Gate | Verdict |
|---|---|---|---|---|
| **1** | v3.4 pin, FMA2 native engine | byte-identical re-pin (REGISTRY FMA3-000) | reproduces the parent lock | ✅ PASS |
| **1** | v7.0 anchor, NSF5 native battery (`v7val/tier12.py`) | byte PASS (anchor 89.72% / €532,230 / 31 triggers) | reproduces the parent anchor | ✅ PASS |
| **1** | Record-engine wrapper (v3.4 pin end-to-end) | **41/41 metrics delta 0.0** + minute curves max-abs 0.0 | delta 0.0 | ✅ PASS |
| **1** | v7 anchor extraction (`engine/v7_bridge`) | **15/15 floats delta 0.0** + 9/9 legs bit-exact, consistency < 2.4e-15 | delta 0.0 | ✅ PASS |
| **1** | Ext engine (2026-capable copy) | **38/38 exactly equal**, curves `np.array_equal` | BIT-IDENTICAL, tolerance zero | ✅ PASS |
| **1** | v1.0 pin rebuild from config alone | **5/5 headline delta 0.0** (`PIN OK`, all owner gates true) | delta 0.0 vs FMA3-003 grid | ✅ PASS |
| **2** | H-FED-1 static federation (grid w .30–.70) | w70: DD **14.38%** / Sharpe **2.474** / negQ 0 / breach 0.0004 | DD < 20.72% · Sharpe > 2.317 · negY 0 · negQ ≤ 0 | ✅ MECHANISM CONFIRMED |
| **2** | H-FED-2 rebalanced federation (4 cadences) | best +1.12pp CAGR at **+0.43pp DD** (F2a) | > +0.5pp CAGR at ≤ +0.3pp DD | ✅ DECLINED — static stands |
| **2** | H-CAPS-1 joint exposure caps (measurement) | joint gold max **2.03×E = entitlement, 0/49,379 h exceeding** | adoption default-YES unless > 3pp cost | ✅ NO-OP (verified) |
| **2** | H-FED-3 scale frontier (s 0.8–1.4) | **7/7 compliant**, ceiling rule → s = 1.4 | largest s: DD < 20.9 · negQ ≤ 1 · negY 0 · breach ≤ 0.12 · tail ≤ 35.6 | ⚠️ re-adjudicated → s = 1.1 (Tier 3) |
| **3** | Parameter perturbation (±20% on w) | w+20%: **ΔDD +3.59pp** (w−20%: +1.06pp ✓) | \|ΔDD\| ≤ 3.0pp AND \|ΔSharpe\| ≤ 0.3 | ❌ **FAIL → adjudicated s = 1.1** |
| **3** | Coupling perturbation (±€128 v7 seed) | Δfinal +0.32% / −1.10%, \|ΔDD\| ≤ 0.02pp | \|Δfinal\| < 5% AND \|ΔDD\| < 1pp | ✅ PASS (chaos-stable) |
| **3** | LOO by book (half-strength each) | ΔDD −4.40pp (half-v7) / +0.26pp (half-v3.4), negY 0 | ΔDD ≤ +3.0pp AND negY 0 | ✅ PASS (no keystone) |
| **3** | Fixed-schedule ablation | winner is **static** — no schedule exists | required on schedule-dependent winners | ✅ N/A by construction |
| **4** | Breach bootstrap (5,000 paths, 20d blocks) | P(DD_worst > 30%) = **0.0020** (close 0.0010) | < 0.0118 (composite; ceiling ≤ 0.12) | ✅ PASS |
| **4** | DSR from the ledger | **1.0000** at n = 20 trials; stable at ×2/×4 stress | DSR ≥ 0.95 | ✅ PASS |
| **5** | CPCV allocation robustness (28 purged folds) | median re-picked OOS Sharpe **0.98×** frozen; w70 re-picked 19/28 | ≥ 0.8 × frozen-w median | ✅ PASS |
| **6** | 2026H1 one-shot forward (F1–F4) | **4/4 PASS** — DD 17.67%, return +12.34%, 0 stop-outs, sub-books + | pre-registered FORWARD_TEST.md bars | ✅ CONFIRM (holdout CONSUMED) |

**Composite gates 7/7 PASS + owner gates 6/6 PASS + red-team 5/6 clean with the one FAIL priced
into the shipped scale + forward one-shot 4/4 CONFIRM.** The only OPEN items are MT5-only and
cannot be closed in Python (sign-off below). Artifacts:
[research/outputs/redteam/](../../research/outputs/redteam/) (six battery reports),
[forward_oneshot.json](../../research/outputs/forward_oneshot.json),
[fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json).

---

## Tier 1 — the reproduction chain (why every number is trusted)

Engine-honesty preamble: both parents were imported **READ-ONLY** (NSF5 and FMA2 repos never
modified); the record engine is FMA2's own `account_engine_1m.py` wrapped, not re-implemented;
every bridge is gated at delta 0.0 or bit-identical **before** any experiment ran (PROTOCOL §5.6
requires the first two links to re-verify before any session). The full chain, with exact counts
— reconciliation depth in [RECONCILIATION.md](RECONCILIATION.md):

| Link | What it proves | Measured result | Reproduce |
|---|---|---|---|
| v3.4 pin, FMA2 native engine (REGISTRY FMA3-000) | the v3.4 parent lock still reproduces in its own engine | **byte-identical** (pin `v34_s10_pin_1m.json`, byte-reproduced twice on 2026-07-10) | FMA2 pin script (parent repo) |
| v7.0 anchor, NSF5 native battery (REGISTRY FMA3-000) | the v7.0 parent anchor still reproduces in its own engine | **tier12 byte PASS** — anchor `harvest_band_sym` 89.72% / 15.70% bd / 19.44% tick / Sharpe 2.58 / €532,230 / 31 band + 0 harvest | `NSF5/mt5/reconcile/v7val/tier12.py` (~9 min) |
| Record-engine wrapper ([verify_record_engine.json](../../research/outputs/verify_record_engine.json)) | FMA3's wrapper reproduces the FMA2 v3.4 pin end-to-end | **41/41 metric checks delta 0.0** (cagr, DD, Sharpe, final €449,707.75, 20,403 trades, 6 yearly, 24 quarterly, 4 breach) + minute-level equity/worst **curve max-abs-delta 0.0** | `python3 scripts/verify_record_engine.py` (~6–8 min) |
| v7 anchor extraction ([v7_extract_verification.json](../../research/outputs/v7_extract_verification.json)) | the extracted v7.0 fraction matrix IS the byte-reconciled NSF5 anchor | **15/15 anchor floats delta 0.0** (incl. 31 band + 0 harvest triggers, both half-window sets); **9/9 per-leg self-test bit-exact** vs NSF5's engine; positions→equity consistency **< 2.4e-15 relative** | `python3 engine/v7_bridge/run_extract.py` (~1 min) |
| Ext engine ([verify_record_engine_ext.json](../../research/outputs/verify_record_engine_ext.json)) | the range-parameterized copy (needed for 2026H1) did not drift | **BIT-IDENTICAL gate: 38/38 metrics exactly equal**, equity + worst curves `np.array_equal` true, tolerance zero | `python3 scripts/verify_record_engine_ext.py` (~5 min) |
| v1.0 pin reproduction ([fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json), `fma3_lock.log`) | the shipped numbers rebuild from `FMA3_CONFIG` alone | matrix rebuilt, 24 quarters re-run, 5,000-path bootstrap re-drawn: **all 5 headline metrics delta 0.0** vs the FMA3-003 grid point (`PIN OK`, all owner gates true) | `python3 scripts/eval_fma3_pin.py` (~7 min) |

No number in this package has a provenance outside this chain: curves and matrices are pinned
artifacts, and the writer data pack
([package_data.json](../../research/outputs/package_data.json)) was built engine-free from them.

---

## Tier 2 — the pre-registered experiment ladder

All bars registered in [HYPOTHESES.md](../../research/protocol/HYPOTHESES.md) /
[PROTOCOL.md](../../research/protocol/PROTOCOL.md) before any merged number existed (2026-07-10;
the H-FED-1 selection rule amended 12:29, pre-results). Every configuration is in the ledger
([REGISTRY.md](../REGISTRY.md)): **16 engine experiments (5 + 4 + 7) + 2 red-team probes = 18
merged-book configs.**

**(A) H-FED-1 — static federation, grid w ∈ {0.30…0.70} (v7 share).** Bars: DD < 20.72% ·
Sharpe > 2.317 · negY 0 · negQ ≤ 0; winner by pre-amended rule = max Sharpe among passers
([hfed1_results.json](../../research/outputs/hfed1_results.json)):

| w (v7 share) | CAGR | Max DD (worst) | Sharpe | COVID tail | negQ | Breach | Friction | Bars |
|---|---|---|---|---|---|---|---|---|
| 0.30 | +86.8% | 18.34% | 2.156 | 6.41% | 0 | 0.0088 | −3.41pp | ❌ (Sharpe) |
| 0.40 | +88.7% | 17.88% | 2.305 | 5.75% | 0 | 0.0020 | −2.08pp | ❌ (Sharpe) |
| 0.50 | +88.1% | 16.41% | 2.371 | 5.53% | 0 | 0.0008 | −3.28pp | ✅ |
| 0.60 | +89.3% | 15.20% | 2.458 | 5.39% | 0 | 0.0004 | −2.60pp | ✅ |
| **0.70** | **+89.7%** | **14.38%** | **2.474** | **4.96%** | **0** | **0.0004** | **−2.70pp** | ✅ **winner** |

**MECHANISM CONFIRMED** — the federation cuts DD below both parents while keeping the better
parent's CAGR; friction is measured, not assumed (−2.1 to −3.4pp across the grid; §Honest
caveats). *Honesty point:* Sharpe was still rising at the grid edge; the off-grid w = 0.80 was
**NOT tested** — the pre-registered grid is binding (anti-seat-shopping rule).

**(B) H-FED-2 — rebalanced federation at w70.** Bar: beat static by > +0.5pp CAGR at ≤ +0.3pp DD
([hfed2_results.json](../../research/outputs/hfed2_results.json)):

| Cadence | Events / 6y | CAGR | ΔCAGR | Max DD | ΔDD | Verdict |
|---|---|---|---|---|---|---|
| F2a calendar-quarterly | 23 | +90.8% | +1.12pp | 14.81% | **+0.43pp** | ❌ DD bar |
| F2b band B_up = 0.60 | 418 | +90.4% | +0.72pp | 14.73% | **+0.35pp** | ❌ DD bar (degenerate†) |
| F2b band B_up = 0.65 | 418 | +90.4% | +0.72pp | 14.73% | **+0.35pp** | ❌ DD bar (degenerate†) |
| F2b band B_up = 0.70 | 22 | +89.4% | **−0.34pp** | 14.40% | +0.02pp | ❌ pays nothing |

† B_up ≤ the 0.70 target share ⇒ the band fires every 5-day min-gap ≈ a 5d calendar; the grid was
registered pre-winner and not re-registered (anti-seat-shopping). **DECLINE all — static w70
stands.** Mechanism reading: cross-book rebalancing **couples the disjoint troughs it harvests**
(M-0: daily ρ +0.351; v3.4's DD at the v7 trough 0.2%, v7's at the v3.4 trough 3.9% —
[composite_benchmark.json](../../research/outputs/composite_benchmark.json) `m0`).

**(C) H-CAPS-1 — combined-book exposure analysis (measurement, no engine).** Guard lever,
adoption default-YES unless > 3pp cost
([hcaps1_analysis.json](../../research/outputs/hcaps1_analysis.json), 49,379 hours at the
s = 1.0 basis):

| Exposure | p50 | p95 | p99 | max | Entitlement | Hours exceeding |
|---|---|---|---|---|---|---|
| Overnight joint gold (×equity) | 1.10 | 1.75 | 1.97 | **2.03** | **2.03 (exactly)** | **0** |
| Managed crosses (EURCHF/EURSEK/EURNOK/AUDNZD) | — | — | — | ≤ 0.191 | 0.195 | 0 (v7 trades none) |
| USTEC joint | — | — | 1.13 | 1.78 | — (dup-edge cleared, ρ 0.046) | — |

**NO-OP (verified)** — the inherited per-book caps compose correctly; no joint cap was added.

**(D) H-FED-3 — scale re-pick on static w70, s ∈ {0.8…1.4}.** Pre-committed rule: largest s with
DD < 20.9% · negQ ≤ 1 · negY 0 · breach ≤ 0.12 · tail ≤ 35.6%
([hfed3_results.json](../../research/outputs/hfed3_results.json)); all seven points compliant,
negQ 0 everywhere, Sharpe scale-flat (2.45–2.48):

| s | CAGR | Max DD (worst) | Sharpe | COVID tail | Breach | €10k → | Note |
|---|---|---|---|---|---|---|---|
| 0.8 | +66.8% | 12.21% | 2.475 | 3.73% | 0.000 | €214,623 | |
| 0.9 | +77.2% | 13.04% | 2.452 | 4.47% | 0.000 | €308,682 | |
| 1.0 | +89.7% | 14.38% | 2.474 | 4.96% | 0.0004 | €464,991 | raw H-FED-1 winner |
| **1.1** | **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0.0020** | **€665,777** | **SHIPPED (probe-robust)** |
| 1.2 | +114.4% | 17.17% | 2.470 | 5.88% | 0.0046 | €967,259 | aggressive frontier |
| 1.3 | +127.4% | 18.59% | 2.468 | 6.44% | 0.0138 | €1,378,091 | aggressive frontier |
| 1.4 | +140.8% | 19.89% | 2.466 | 7.09% | 0.0294 | €1,942,739 | ceiling-rule pick, **not probe-robust** |

The mechanical rule selected **s = 1.4** ("GATES BREACHED", REGISTRY FMA3-003) — then the Tier-3
perturbation FAIL re-adjudicated the shipped scale to **s = 1.1**.

---

## Tier 3 — red-team battery (6 checks; thresholds pre-registered in script docstrings)

Four checks are summarized here; two are broken out as Tiers 4–5. Artifacts:
[research/outputs/redteam/](../../research/outputs/redteam/). The battery's Duka second-feed item
is carried by the Tier-6 forward test (which runs on Duka by construction); min-lot feasibility
is measured inside every engine run.

**The perturbation FAIL and its adjudication** — the honest centerpiece
([rt_perturbation.json](../../research/outputs/redteam/rt_perturbation.json)). ±20% probes on w,
the one structural parameter (thresholds |ΔDD| ≤ 3.0pp, |ΔSharpe| ≤ 0.3):

| Probe | CAGR | Max DD (worst) | ΔDD | Sharpe | ΔSharpe | Tail | negY / negQ |
|---|---|---|---|---|---|---|---|
| w−20% (w = 0.56) | +88.9% | 15.45% | +1.06pp ✓ | 2.422 | −0.05 ✓ | 4.85% | 0 / 0 |
| **w = 0.70 (locked)** | **+89.7%** | **14.38%** | — | **2.474** | — | **4.96%** | **0 / 0** |
| w+20% (w = 0.84) | +89.0% | **17.97%** | **+3.59pp** ❌ | 2.416 | −0.06 ✓ | 5.04% | 0 / 0 |

Mechanical verdict: **FAIL** (fragile on the w+20% axis only). Why it is a frontier, not a fitted
spike: every quality metric is stable across the surface (CAGR within 0.8pp, ΔSharpe ≤ 0.06,
negQ 0 everywhere) and DD moves **monotonically toward the measured v7-alone endpoint** (v7 @ r8:
21.22%) — the geometry of a smooth frontier, corroborated by CPCV re-picking w = 0.70 in 19/28
folds (Tier 5). Because the never-rebalanced split *drifts* (measured band ~0.63–0.75 between
quarterly marks, `hfed2_results.json` event logs), the ceilings must hold across the ±20% probe
surface, not only at the locked w. **Adjudication (REGISTRY FMA3-RT): largest s with all ceilings
at the locked w AND both ±20% probes ⇒ s = 1.1** (binding: w+20% DD 17.97% × 1.1 ≈ 19.8% < 20.9%;
× 1.2 ≈ 21.6% breaches). The FAIL was not waived — it was **priced**, at −39.4pp CAGR vs s = 1.4.

The other three checks:

| Check | Threshold | Measured | Verdict |
|---|---|---|---|
| Coupling (±€128 on the v7 sub-book seed — the NSF5 chaos probe) | \|Δfinal\| < 5% AND \|ΔDD\| < 1pp | +€128: **+0.32% / +0.01pp** · −€128: **−1.10% / −0.02pp** | ✅ PASS — chaos-stable |
| LOO by book (half-strength each sub-book; full drop = the parents themselves) | ΔDD ≤ +3.0pp AND negY 0 | half-v7: CAGR +49.6%, DD 9.98% (**ΔDD −4.40pp**), negY 0 · half-v3.4: CAGR +71.2%, DD 14.65% (**+0.26pp**), negY 0 | ✅ PASS — no keystone |
| Fixed-schedule ablation | required on schedule-dependent winners | the winner is **static**: no federation rebalance schedule exists to freeze | ✅ N/A by construction |

---

## Tier 4 — breach bootstrap + DSR (path-bias and selection-bias)

**Breach bootstrap** (5,000 20d-block bootstrap paths of the pinned daily curve,
[fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json) `breach`):

| | Measured | Gate | Verdict |
|---|---|---|---|
| P(MaxDD_worst > 30%) | **0.0020** | < 0.0118 (composite; H-FED-3 ceiling ≤ 0.12) | ✅ PASS |
| P(MaxDD_close > 30%) | 0.0010 | — | reported |
| Bootstrap median DD (worst) | 16.80% | — | realized 15.73% ≈ a typical draw |
| Bootstrap p95 DD (worst) | **23.28%** | — | re-rolls can reach ~23%, still < 30% |

The realized 15.73% sits slightly *below* the bootstrap median — the pinned path is typical, not
lucky; the p95 says a re-roll of the same daily returns can print ~23% DD with breach mass still
at 0.2%.

**DSR** ([rt_dsr.json](../../research/outputs/redteam/rt_dsr.json)): candidate Sharpe **2.466**
measured from the shipped curve (T = 2,080 daily obs, skew +0.06, Pearson kurtosis 7.38 — fat
tails priced in), Sharpe variance from the 16 harvested grid Sharpes, ledger n = 20 trials:

| n trials | E[max SR] (ann.) | DSR | Gate | Verdict |
|---|---|---|---|---|
| 20 (ledger) | 0.163 | **1.0000** | ≥ 0.95 | ✅ PASS |
| 40 (×2 stress) | 0.188 | 1.0000 | — | stable |
| 80 (×4 stress) | 0.210 | 1.0000 | — | stable |

**Meaning and limits (honest):** the DSR says the *federation's own* few-parameter selection —
one w grid, one cadence family, one scale grid — cannot explain Sharpe 2.47 by luck within FMA3's
ledger. **It says nothing about the parents' mining of 2020–25** (FMA2 ≈ low-hundreds of trials,
NSF5 ≈ 7,560 prescreens); the sleeves' alpha is assumed from the parents' validation records, not
re-proven. That is why the licensed design space was structural-only and why Tier 6 + the live
demo carry the real burden of proof.

---

## Tier 5 — CPCV allocation robustness (is w = 0.70 one lucky stretch?)

CPCV at the allocation level ([rt_cpcv_alloc.json](../../research/outputs/redteam/rt_cpcv_alloc.json)):
8 blocks, k = 2, 10d purge ⇒ **28 purged folds** over 2,080 daily obs; each fold re-picks w on
train and is scored OOS vs the frozen w = 0.70:

| OOS Sharpe | p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|---|
| Frozen w = 0.70 | 1.79 | 2.10 | **2.41** | 2.72 | 3.27 |
| Re-picked per fold | 1.60 | 2.07 | **2.36** | 2.71 | 3.27 |

Median ratio **0.98** (gate ≥ 0.8) → ✅ PASS. Re-pick histogram: **w = 0.70 in 19/28 folds**,
w = 0.60 in 6, other values only in 3 low-train fallback folds. The w choice is time-stable
across purged sub-periods — corroborating the Tier-3 reading that the perturbation FAIL is
frontier geometry, not a fitted seat.

---

## Tier 6 — the 2026H1 one-shot forward confirmation (CONSUMED)

Criteria pre-registered in [FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) (sha256
`c40ab6fdf4de2eab…`, committed 14:10 **before any 2026 number existed**); fresh €10k seed
2026-01-01 at (0.70, 0.30), s = 1.1; Duka forward feed, 14-symbol coverage, USA500 proxying
USTEC; engine `record_engine_ext` (bit-identity gate passed, Tier 1); driver hard-gated against
re-runs. Full report: [FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md) /
[forward_oneshot.json](../../research/outputs/forward_oneshot.json); ledger row FMA3-FWD.

| # | Pre-registered bar | Measured | Verdict |
|---|---|---|---|
| F1 | window worst-mark DD < 20.9% | **17.67%** (close 17.58%) | ✅ PASS |
| F2 | window return > −10% | **+12.34%** (€10,000 → €11,234) | ✅ PASS |
| F3 | no joint stop-out or margin-cap breach | **0 / 0** (max margin/balance 0.324 vs cap 0.90; min margin level 3.11 vs stop-out 0.50; bit-identity-gated instrumented kernel) | ✅ PASS |
| F4 | each sub-book window return > −20% | **v7 +15.99% · v3.4 +13.59%** | ✅ PASS |

**4/4 → CONFIRM** per the pre-registered interpretation → proceed to MT5 demo deployment (the
deployable arbiter). Window 2026-01-01 → 2026-04-30 (server), monthly **+14.94 / −0.25 / +0.41 /
−2.42%**; daily Sharpe (120 obs, wide error bars) **1.17** — marginally below the pre-stated
honest-discount band 1.2–1.5 (expectation prose, not a bar; disclosed as-is); short-window breach
bootstrap 0.0002. Caveats disclosed in advance: USA500-proxy book ≠ deployed book (corr 0.89,
directional confirmation only); v3.4 at ~0.88× reduced breadth (uncovered legs zeroed); Duka ≠ IC
feed (~8pp CAGR_bd documented 2020–25 divergence); 4 months ≈ 85 trading days — the bars are
breakdown detectors, not performance targets. The 2026H1 holdout is now permanently **CONSUMED**.

---

## Honest caveats

- **Everything is in-sample on a twice-mined window** (parents' programs + FMA3's 18 configs);
  the DSR's reach is FMA3's own ledger only (Tier 4).
- **Federation friction is real and measured: −2.7pp CAGR** at the locked point (ideal
  bookkeeping 92.4% vs realized 89.7% at s = 1.0) — min-lot quantization at €10k sub-book seeds,
  joint margin, netting/costs on shared instruments.
- **The v7 leg carries a ~1-bar execution lag vs its native engine** — priced identically into
  references and candidates; comparisons are like-for-like but absolute levels are not the native
  book's ([RECONCILIATION.md](RECONCILIATION.md)).
- **The capital split drifts** (~0.63–0.75 band); the probe-robust scale rule exists precisely to
  absorb this — all ceilings hold across w 0.56–0.84 at s = 1.1.
- **Forward-honest Sharpe expectation is 1.2–1.5**, not the pinned 2.47 (v3.4's disclosed
  in-sample→forward ratio ≈ 0.65–0.81 applied as-is); the 2026H1 window printed 1.17 on 120 obs.
- **Crisis-tail numbers from the record engine must never be quoted against MT5 numbers** — the
  measured 1m↔tick gap is 5.54% vs 35.6% for v7 alone; the federation's tick tail is unknown by
  construction until the MT5 run ([RECONCILIATION.md](RECONCILIATION.md)).

---

## Sign-off status

**DONE — Python battery (in-sample IC 2020-25, engine of record):**
- [x] Tier 1 reproduction chain — parents byte-reproduced in their native engines (v3.4 pin
  identical; v7 tier12 byte PASS); record wrapper **41/41 delta 0.0** + minute curves 0.0; v7
  extract **15/15 delta 0.0** + 9/9 legs bit-exact; ext engine **BIT-IDENTICAL (38/38)**; v1.0
  pin rebuilds from config at **delta 0.0**
- [x] Tier 2 ladder — H-FED-1 **MECHANISM CONFIRMED** (w70: 14.38% DD / 2.474 Sharpe); H-FED-2
  **all 4 cadences DECLINED** (every one misses the ≤+0.3pp DD bar); H-CAPS-1 **NO-OP verified**
  (0 hours over entitlement); H-FED-3 frontier mapped 7/7 compliant
- [x] Tier 3 red team — coupling / LOO / fixed-schedule clean; perturbation **FAIL on w+20%
  (ΔDD +3.59pp) priced into the adjudicated ship scale s = 1.1** (only fully parent-dominant
  point, 7/7)
- [x] Tier 4 breach bootstrap **0.0020** (< 0.0118 ✓) + DSR **1.0000** at n = 20 (≥ 0.95 ✓,
  stable ×4)
- [x] Tier 5 CPCV allocation — ratio **0.98** (≥ 0.8 ✓), w = 0.70 re-picked 19/28 purged folds
- [x] Tier 6 2026H1 one-shot — **4/4 PASS → CONFIRM**; holdout CONSUMED; €10k → €11,234
- [x] Compared to incumbents — **v1.0 dominates BOTH parents on all 7 composite dimensions**
  (+9.9pp CAGR over the best parent at −5.5pp DD, −0.2pp tail, breach ÷6)

**OPEN — before/at live-demo (MT5-only, cannot be closed in Python):**
- [ ] **MT5 real-tick run of the federation book on the owner's machine** — the deployable
  arbiter. The 1m↔tick crisis-tail gap is *measured* at 35.6% vs 5.54% for v7.0 alone; the
  federation's tick-granularity tail is **unknown by construction**, and v3.4 has never had a
  tick run at all. Record-engine tail numbers must never be quoted against MT5 numbers.
- [ ] **Live demo deployment** — the pre-registered forward interpretation (CONFIRM → MT5 demo)
  authorizes it; judge the live book against the forward-honest Sharpe band **1.2–1.5**, not the
  in-sample 2.47.

**Automated gates: composite 7/7 PASS + owner 6/6 PASS; 6-tier battery clear with one
pre-registered red-team FAIL priced into the shipped scale; forward one-shot CONFIRM.** All
numbers are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick + live demo
are the remaining falsification tests.

*Artifacts:* [fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json) + curve ·
[hfed1](../../research/outputs/hfed1_results.json) / [hfed2](../../research/outputs/hfed2_results.json) /
[hfed3](../../research/outputs/hfed3_results.json) ·
[hcaps1_analysis.json](../../research/outputs/hcaps1_analysis.json) ·
[redteam/](../../research/outputs/redteam/) (rt_perturbation, rt_coupling, rt_loo, rt_cpcv_alloc,
rt_dsr) · [forward_oneshot.json](../../research/outputs/forward_oneshot.json) ·
[composite_benchmark.json](../../research/outputs/composite_benchmark.json) ·
[REGISTRY.md](../REGISTRY.md) · package siblings: [STRATEGY.md](STRATEGY.md) ·
[PERFORMANCE.md](PERFORMANCE.md) · [TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md) ·
[RECONCILIATION.md](RECONCILIATION.md) · [DEMO.md](DEMO.md).
