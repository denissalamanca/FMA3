# FMA3 v1.0 Scorecard & Validation

**FMA3 v1.0 = the static federation locked on 2026-07-10: one cross-margined €10k IC Markets EU
Raw account carrying the v7.0 band book at capital share w = 0.70 and the v3.4 fixed-fraction book
at 0.30 as never-rebalanced virtual sub-accounts, at global scale s = 1.1 — no cross-book
rebalancing (H-FED-2 declined), no new caps (H-CAPS-1 no-op), both parents' sleeves frozen.**
Sources of truth: config = [`strategy_fma3.py`](../../strategy_fma3.py) (**config hash
`51a7541cc2aaa593`**); pin script = [`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py)
(rebuilds the locked matrix from `FMA3_CONFIG`, re-runs the engine of record end-to-end, verifies
delta 0.0 against the FMA3-003 grid); official numbers =
[`research/outputs/fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json) + curve
`fma3_v1_pin_curve.parquet`. Engine of record: FMA2's 1-minute worst-mark single cross-margined
account engine via the verified [`engine/record_engine.py`](../../engine/record_engine.py) wrapper
([01_DECONSTRUCTION.md §4](01_DECONSTRUCTION.md)); design and pre-registered ladder in
[02_FEDERATION_DESIGN.md](02_FEDERATION_DESIGN.md).

**Everything in this document is in-sample (IC 2020–25).** The 2020–25 window was mined by both
parent programs before FMA3 existed, and FMA3 added 18 more ledger configs on top of it. There is
no post-2025 holdout here — the pre-registered 2026H1 one-shot (§7, in flight) and the live demo
are the falsification tests, and MT5 real-tick on the owner's machine remains the deployable
arbiter.

---

## 1. The new frontier scorecard

### 1.1 The owner's original six gates (secondary scoreboard)

| Gate | Bar | FMA3 v1.0 | Verdict |
|---|---|---|---|
| CAGR | > 96.1% | **+101.4%** | ✅ PASS |
| Max DD | < 20.9% | **15.73%** (worst-mark; close 15.62%) | ✅ PASS |
| Sharpe | > 2.03 | **2.467** | ✅ PASS |
| Crisis tail (COVID) | ≤ 35.6% | **5.36%** | ✅ PASS* |
| Negative years | 0 | **0 / 6** | ✅ PASS |
| Negative quarters | ≤ 1 | **0 / 24** | ✅ PASS |

All six clear ([fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json) `gates.owner`, all
`true`). **Standing caveat (\*): the six numbers straddle two non-comparable engines.** The
96.1 / 20.9 / 35.6 references are v7.0's **MT5 real-tick R10** numbers, while the negQ convention
only exists in Python 1m close-to-close accounting (v7.0 itself scores 3/24 negQ on MT5 tick).
The gap is now *measured*, not assumed:
[COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md) prices v7.0's COVID tail
at **35.6% on MT5 real-tick vs 5.5% (5.54%, r8) in the 1m worst-mark record engine** —
tick-granularity spread blowouts during Mar-2020 do not exist in 1m bars. The 5.36% tail above
therefore clears the 35.6% bar only in the trivial sense; the honest tail comparison is the
composite gate below (5.36% vs the parents' same-engine 5.54%), and the deployable tail number
awaits the MT5 run.

### 1.2 The seven composite dimensions (primary scoreboard, pre-registered)

Gates = dimension-wise best of the two parents measured in the engine of record
([PROTOCOL.md §2](../../research/protocol/PROTOCOL.md), filled by
[composite_benchmark.json](../../research/outputs/composite_benchmark.json)):

| Dimension | Composite gate | Previous holder | FMA3 v1.0 | Verdict |
|---|---|---|---|---|
| CAGR | > 91.5% | v7.0 @ r8 | **+101.4%** | ✅ PASS |
| Max DD (worst-mark) | < 21.22% | v7.0 @ r8 | **15.73%** | ✅ PASS |
| Sharpe | > 2.267 | v7.0 @ r8 | **2.467** | ✅ PASS |
| COVID crisis tail | ≤ 5.54% | v7.0 @ r8 | **5.36%** | ✅ PASS |
| Negative years | 0 | both parents (tied, 0/6) | **0 / 6** | ✅ PASS |
| Negative quarters | ≤ 0 | v7.0 @ r8 (v3.4 had 1) | **0 / 24** | ✅ PASS |
| Breach P(DD>30%) | < 0.012 | v7.0 @ r8 (v3.4: 0.121) | **0.002** | ✅ PASS |

**FMA3 v1.0 at s = 1.1 dominates BOTH parents on ALL SEVEN dimensions in the engine of record —
the first fully-dominant point in the two programs' combined history.** No parent configuration
ever achieved this: in the record accounting v7.0 @ r8 held six of the seven dimension bests
(negY tied) but a simple re-lever to its native r10 buys +30.7pp CAGR at +5.0pp DD, breach
0.012→0.116 and a 2022Q4 negQ ([COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)).
The federation buys **+9.9pp CAGR over the best parent while *cutting* DD by 5.5pp, tail by
0.2pp, and breach by 6×** — CAGR bought cheaper than the leverage dial sells it, which was the
pre-registered job description. Yearly (pin): 2020 +137.7%, 2021 +110.9%, **2022 +48.8%
(worst)**, 2023 +88.7%, 2024 +94.5%, 2025 +129.7%; all 24 quarters positive (worst 2022Q4
+2.9%); €10k → **€665,777**; 25,869 trades.

---

## 2. The experiment trail

Every configuration evaluated, from [docs/REGISTRY.md](../REGISTRY.md); all bars pre-registered
in [PROTOCOL.md](../../research/protocol/PROTOCOL.md) /
[HYPOTHESES.md](../../research/protocol/HYPOTHESES.md) before any merged number existed
(2026-07-10; the H-FED-1 selection rule amended 12:29, pre-results).

| ID | Lever | Pre-registered bars | Result | Verdict |
|---|---|---|---|---|
| **FMA3-000** | Baseline reproduction + composite benchmark + M-0 measurements | exact match to pinned refs | v3.4 pin 41/41 delta 0.0; v7 extract 15/15 delta 0.0; composite gates derived; M-0: ρ +0.351, DD troughs disjoint, USTEC dup-edge cleared (ρ 0.046), gold stacking flagged → H-CAPS-1 | ✅ complete |
| **FMA3-001** | H-FED-1 static federation, grid w ∈ {0.30…0.70} | DD < 20.72% · Sharpe > 2.317 · negY 0 · negQ ≤ 0 | w30 fail (Sh 2.156), w40 fail (Sh 2.305); **w50/w60/w70 PASS**; winner by rule w70: 89.7% / 14.38% / 2.474 / tail 4.96% / negQ 0 / breach 0.0004 (friction −2.7pp); Sharpe still rising at grid edge — w80 NOT tested (grid binding) | ✅ **MECHANISM CONFIRMED** |
| **FMA3-002** | H-FED-2 rebalanced federation at w70 (F2a quarterly; F2b band 0.60/0.65/0.70) | beat static by > +0.5pp CAGR at ≤ +0.3pp DD | F2a +1.12pp / +0.43pp DD (23 ev); F2b60/65 +0.72pp / +0.35pp (418 ev — degenerate at w70: B_up ≤ target share fires every 5d min-gap); F2b70 −0.34pp / +0.02pp (22 ev) — **all miss the DD bar**; cross-book rebalancing couples the disjoint troughs it harvests | ✅ **DECLINE all — static w70 stands** |
| **FMA3-C1** | H-CAPS-1 combined-book exposure limits (measurement) | adoption default-YES unless > 3pp cost | overnight joint gold p50 1.10×E / p99 1.97×E / max 2.03×E = exactly the inherited entitlement, **0 hours exceeding**; managed crosses all within 0.5×E × share (v7 trades none) — per-book caps compose correctly | ✅ **NO-OP (verified)** |
| **FMA3-003** | H-FED-3 scale re-pick on static w70, s ∈ {0.8…1.4} | ship largest s with DD < 20.9% · negQ ≤ 1 · negY 0 · breach ≤ 0.12 · tail ≤ 35.6% | ALL SEVEN compliant (smooth monotone frontier, negQ 0 everywhere); ceiling rule alone → s = 1.4 (140.8% / 19.89%); owner gates all cleared | ✅ gates breached (scale later re-adjudicated, see FMA3-RT) |
| **FMA3-RT** | Red-team battery on the winner (PROTOCOL §6) | thresholds pre-registered in script docstrings before runs | perturbation **FAIL on the w+20% axis only** (§4); coupling / LOO / CPCV-alloc / DSR all PASS; fixed-schedule N/A (static) | ⚠️ battery complete → **adjudicated SHIP s = 1.1** (§3) |

Ledger counters: **16 engine experiments (5 + 4 + 7) + 2 red-team probe configs = 18 merged-book
configs logged**; 2026H1 holdout **UNCONSUMED** at lock ([REGISTRY.md](../REGISTRY.md)).

---

## 3. The scale frontier — why s = 1.1 ships and s = 1.4 is the aggressive frontier

All seven pre-registered H-FED-3 points on the static-w70 winner, engine of record
([hfed3_results.json](../../research/outputs/hfed3_results.json)); every point compliant with the
ceilings (DD < 20.9%, negQ ≤ 1, negY 0, breach ≤ 0.12, tail ≤ 35.6%), negQ 0 everywhere:

| s | CAGR | Max DD (worst-mark) | Sharpe | COVID tail | Breach P(DD>30%) | €10k → | Note |
|---|---|---|---|---|---|---|---|
| 0.8 | +66.8% | 12.21% | 2.475 | 3.73% | 0.000 | €214,623 | |
| 0.9 | +77.2% | 13.04% | 2.452 | 4.47% | 0.000 | €308,682 | |
| 1.0 | +89.7% | 14.38% | 2.474 | 4.96% | 0.0004 | €464,991 | the raw H-FED-1 winner |
| **1.1** | **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0.002** | **€665,777** | **SHIPPED (probe-robust)** |
| 1.2 | +114.4% | 17.17% | 2.470 | 5.88% | 0.0046 | €967,259 | aggressive frontier |
| 1.3 | +127.4% | 18.59% | 2.468 | 6.44% | 0.0138 | €1,378,091 | aggressive frontier |
| 1.4 | +140.8% | 19.89% | 2.466 | 7.09% | 0.0294 | €1,942,739 | H-FED-3 ceiling-rule pick |

**The adjudication.** The pre-committed H-FED-3 rule ("largest compliant s") mechanically
selected **s = 1.4** (FMA3-003) — every ceiling holds at the locked w = 0.70, the frontier is
smooth and monotone, and Sharpe is scale-flat (2.45–2.48 across the whole grid). Then the
red-team parameter-perturbation probe **failed on the w+20% axis** (§4): at w = 0.84 the
worst-mark DD rises from 14.38% to **17.97%** (+3.59pp, over the pre-registered 3.0pp flip
threshold). Because a never-rebalanced federation's realized capital split *drifts* (measured
drift band ~0.63–0.75 between quarterly marks in the H-FED-2 event logs —
[hfed2_results.json](../../research/outputs/hfed2_results.json)), the owner's ceilings must hold
not only at the locked w but across the ±20% probe surface. The adjudicated shipping rule
([REGISTRY.md FMA3-RT](../REGISTRY.md)): **largest s such that all ceilings hold at the locked w
AND at both ±20% w probes.** The binding constraint is the w+20% probe: 17.97% × 1.1 ≈ 19.8% <
20.9% at s = 1.1, but ≈ 21.6% > 20.9% at s = 1.2 → **s = 1.1 ships**. s ∈ {1.2…1.4} are
documented as the **aggressive frontier**: compliant at the locked w, not probe-robust.

**Why the perturbation FAIL is a frontier, not a fitted spike (the honesty case).** The full
±20% surface ([rt_perturbation.json](../../research/outputs/redteam/rt_perturbation.json)):

| Probe | CAGR | Max DD | ΔDD | Sharpe | ΔSharpe | Tail | negY / negQ |
|---|---|---|---|---|---|---|---|
| w−20% (w = 0.56) | +88.9% | 15.45% | +1.06pp | 2.422 | −0.05 | 4.85% | 0 / 0 |
| **w = 0.70 (locked)** | **+89.7%** | **14.38%** | — | **2.474** | — | **4.96%** | **0 / 0** |
| w+20% (w = 0.84) | +89.0% | 17.97% | **+3.59pp** ❌ | 2.416 | −0.06 | 5.04% | 0 / 0 |

Every quality metric is stable across the surface (Sharpe −0.05/−0.06, CAGR within 0.8pp, negQ 0
at all three points); only DD moves, and it moves **monotonically toward the measured v7-alone
endpoint** (v7.0 @ r8 alone: DD 21.22% — w = 0.84 sits exactly on the interpolation path to
w = 1.0). This is the geometry of a smooth frontier where w = 0.70 happens to sit near the grid's
Sharpe/DD optimum — not of a fitted seat that collapses off-peak. Supporting evidence: the CPCV
allocation test re-picks **w = 0.70 in 19 of 28 purged folds** with median re-picked OOS Sharpe
at 0.98× the frozen pick ([rt_cpcv_alloc.json](../../research/outputs/redteam/rt_cpcv_alloc.json))
— the w choice is time-stable, not one lucky stretch. The FAIL was therefore not waived: it was
**priced**, by cutting the shipped scale from 1.4 to 1.1 (−39.4pp CAGR paid for probe-robustness).
Both the mechanical FAIL and the adjudication rationale are logged verbatim in
[REGISTRY.md](../REGISTRY.md).

---

## 4. Red-team battery scorecard

Six checks (PROTOCOL §6), thresholds pre-registered in the script docstrings before any run;
artifacts in [research/outputs/redteam/](../../research/outputs/redteam/):

| # | Check | Threshold (pre-registered) | Result | Verdict |
|---|---|---|---|---|
| 1 | Parameter perturbation (±20% on w, the one structural param) | \|ΔDD\| ≤ 3.0pp AND \|ΔSharpe\| ≤ 0.3 on both probes | w−20%: ΔDD +1.06pp, ΔSh −0.05 ✓ · w+20%: **ΔDD +3.59pp** ✗, ΔSh −0.06 ✓ | ❌ **FAIL** → adjudicated: scale re-picked probe-robust, s = 1.1 (§3) |
| 2 | Coupling perturbation (±€128 on the v7 sub-book seed, the NSF5 chaos probe) | \|Δfinal equity\| < 5% AND \|ΔDD\| < 1pp | +€128: +0.32% / +0.01pp · −€128: −1.10% / −0.02pp | ✅ PASS (chaos-stable) |
| 3 | LOO by book (half-strength each sub-book) | ΔDD ≤ +3.0pp AND negY = 0 | half-v7: ΔDD −4.40pp, negY 0 · half-v3.4: ΔDD +0.26pp, negY 0 | ✅ PASS (no keystone; full-drop LOO = the parents themselves, see composite benchmark) |
| 4 | CPCV at the allocation level (8 blocks, k = 2, purge 10d, 28 folds) | median re-picked OOS Sharpe ≥ 0.8 × frozen-w median | 2.36 vs 2.41 = **ratio 0.98**; w = 0.70 re-picked 19/28 folds | ✅ PASS |
| 5 | DSR from the ledger | DSR ≥ 0.95 | **1.0000** at n = 20 trials (Sharpe 2.47, T = 2080); stable at ×2 (n = 40) and ×4 (n = 80) stress | ✅ PASS (meaning and limits in §6) |
| 6 | Fixed-schedule ablation | required on any schedule-dependent winner | the winner is **static** — there is no federation rebalance schedule to freeze | ✅ N/A by construction |

Battery items (e) Duka second-feed cross-check and (i) the 2026H1 one-shot are carried by the
forward test (§7), which runs on the Duka feed with the USA500 proxy by construction; item (j)
min-lot feasibility is measured inside every engine run and disclosed in §6.

---

## 5. Reconciliation & reproduction

The verification chain under every number in this document. All four gates are re-runnable with
one command each; PROTOCOL §5.6 requires the first two to re-verify before any experiment
session.

| Link | What it proves | Result | Reproduce |
|---|---|---|---|
| v7 anchor extraction ([v7_extract_verification.json](../../research/outputs/v7_extract_verification.json)) | the extracted v7.0 fraction matrix is the byte-reconciled NSF5 anchor | **15/15 anchor floats delta 0.0** (incl. 31 band + 0 harvest triggers); 9/9 per-leg self-test vs NSF5's engine bit-exact; positions→equity consistency < 2.4e-15 relative | `python3 engine/v7_bridge/run_extract.py` (~1 min) |
| Record-engine wrapper ([verify_record_engine.json](../../research/outputs/verify_record_engine.json)) | FMA3's wrapper reproduces the FMA2 v3.4 pin end-to-end | **41/41 metric checks delta 0.0** + minute-level equity/worst **curve max-abs-delta 0.0** | `python3 scripts/verify_record_engine.py` (~6–8 min) |
| Ext engine ([verify_record_engine_ext.json](../../research/outputs/verify_record_engine_ext.json)) | the range-parameterized copy (needed for 2026H1) did not drift | **BIT-IDENTICAL** gate: 38/38 metrics exactly equal, equity + worst curves `np.array_equal` true, tolerance zero | `python3 scripts/verify_record_engine_ext.py` (~5 min) |
| v1.0 pin reproduction ([fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json)) | the shipped numbers rebuild from config alone | rebuilds the matrix from `FMA3_CONFIG`, re-runs engine + 5000-path bootstrap; **all 5 headline metrics delta 0.0** vs the FMA3-003 grid point at the adjudicated scale (`fma3_lock.log`: `PIN OK`, all owner gates true) | `python3 scripts/eval_fma3_pin.py` (~7 min) |

---

## 6. Honest caveats

- **Everything is in-sample, on a window mined twice over.** IC 2020–25 was the development
  sample of both parent programs (FMA2 ≈ low-hundreds of design trials; NSF5 ≈ 7,560 prescreens +
  ~258 engine tests), and FMA3 added 18 ledger configs on top. The **DSR 1.0000 at n = 20**
  (stable at n = 80) says the *federation's own* few-parameter selection — one w grid, one
  cadence family, one scale grid — cannot explain a Sharpe of 2.47 by luck **within FMA3's
  ledger**. It says nothing about the parents' mining: the sleeves' alpha is assumed from the
  parents' own validation records, not re-proven here. That is exactly why the licensed design
  space was structural-only and why the 2026H1 one-shot and live demo carry the real burden of
  proof.
- **Federation friction is real and measured: −2.7pp CAGR** at the locked point (ideal
  bookkeeping 92.4% vs realized 89.7% at s = 1.0) — min-lot quantization, joint margin, and
  netting/costs on shared instruments, priced by the engine rather than assumed away
  ([hfed1_results.json](../../research/outputs/hfed1_results.json)).
- **The v7 leg carries a ~1-bar execution lag vs its native engine.** The extracted fraction
  matrix is a held-exposure snapshot replayed through the record engine, which lags each hourly
  row into the next hour's first traded minute ([02_FEDERATION_DESIGN.md §3](02_FEDERATION_DESIGN.md)).
  The cost is priced into the measured v7@r8 record profile and applies identically to parent
  references and federation candidates — comparisons are like-for-like, but the absolute level is
  not the native book's.
- **Min-lot quantization at €10k is genuine friction.** Sub-books start at €7k/€3k (2020), where
  0.01-lot rounding is coarsest; it is simulated, not assumed away, and it is one component of
  the −2.7pp friction above.
- **The capital split w is never rebalanced and drifts.** Measured drift band ~0.63–0.75 across
  2020–25 (quarterly share-before-reset logs in
  [hfed2_results.json](../../research/outputs/hfed2_results.json)). The probe-robust scale rule
  (§3) exists precisely to absorb this: all owner ceilings hold across the ±20% w surface
  (w 0.56–0.84) at the shipped s = 1.1.
- **Forward-honest Sharpe expectation.** By the parents' own convention, in-sample Sharpe does
  not survive contact with forward data at face value: v3.4 shipped with a disclosed
  forward-honest band of **1.2–1.5 vs 1.85 in-sample** (ratio ≈ 0.65–0.81). Applying the same
  ratio reasoning to the pinned 2.47 gives a forward-honest expectation of roughly **Sharpe
  1.6–2.0**; [FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) budgets the more
  conservative 1.2–1.5 band outright. Judge the live book against those bands, not against 2.47.
- **MT5 real-tick is the deployable arbiter, and it has not been run for the federation.** The
  1m↔tick crisis-tail gap is measured at 35.6% vs 5.5% for v7.0 alone (§1.1); v3.4 has never had
  a tick run at all. The federation's tick-granularity tail is therefore *unknown by
  construction* until the owner's-machine MT5 run — the record-engine tail numbers in this
  document must never be quoted against MT5 numbers.

---

## 7. 2026H1 one-shot forward confirmation (in flight)

[FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) pre-registered the criteria on
**2026-07-10 14:10, before any FMA3 code had computed any number on any 2026 data**: fresh-start
sub-books at (0.70, 0.30) of €10k on 2026-01-01, s = 1.1, window 2026-01-01 → 04-30 on the Duka
feed (USA500 proxy for USTEC, corr 0.89 — directional confirmation, not reconciliation), engine
`record_engine_ext` (bit-identity gate already passed, §5). Bars: **F1** window worst-mark DD
< 20.9% · **F2** window return > −10% · **F3** no joint stop-out / margin-cap breach · **F4**
each sub-book > −20%. Interpretation was committed with the bars: 4/4 → CONFIRM (proceed to MT5
demo); F1/F2 fail → INVESTIGATE (no deployment until MT5 adjudicates); F3 fail → REJECT the
locked scale and re-open H-FED-3 with a new pre-registration. Honest expectation, stated before
looking: ≈ +10–20% over the window under the forward-discounted band, with 4-month volatility
≈ ±24% — **a negative window is entirely possible for a healthy book**. The driver
(`scripts/run_forward_oneshot.py`) is hard-gated on the pre-registration and refuses to run
twice; the window is consumed regardless of outcome.

**RESULT (2026-07-10, appended verbatim per pre-registration): VERDICT = CONFIRM — 4/4 bars PASS.**
Full report: [FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md) ·
[forward_oneshot.json](../../research/outputs/forward_oneshot.json) · ledger row FMA3-FWD.

| Bar | Pre-registered | Measured | Verdict |
|---|---|---|---|
| F1 window worst-mark DD | < 20.9% | **17.67%** | ✅ |
| F2 window return | > −10% | **+12.34%** (€10,000 → €11,234) | ✅ |
| F3 joint stop-out / margin-cap events | 0 | **0** (max margin/balance 0.324 vs cap 0.90; min margin level 3.11 vs stop-out 0.50; instrumented kernel bit-exact vs engine) | ✅ |
| F4 each sub-book return | > −20% | **v7 +15.99% · v3.4 +13.59%** | ✅ |

Window 2026-01-01 → 2026-04-30, fresh €10k seed at (0.70, 0.30), s=1.1, config hash
`51a7541cc2aaa593`. Monthly: **+14.94 / −0.25 / +0.41 / −2.42%**; daily Sharpe (120 obs) **1.17**
— marginally below the pre-stated honest-discount expectation band 1.2–1.5 (expectation prose,
not a bar; disclosed as-is). Per the pre-registered interpretation, 4/4 → **CONFIRM: proceed to
MT5 demo deployment (the deployable arbiter, owner's machine).**

**Honest caveats carried with the verdict (from the pre-registration + run report):** Duka feed,
not IC (~8pp CAGR_bd known 2020–25 divergence); USA500 proxies USTEC — the proxy book is a
directional confirmation, not the deployed book; v3.4 ran at ~0.88× reduced breadth (uncovered
2026 legs zeroed, disclosed in `v34_frac_1h_fwd_report.json`); 4 months is statistically weak by
construction — the bars are breakdown detectors, not performance targets. The 2026H1 holdout is
now permanently **CONSUMED**.

---

*Sources: [fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json) (the pin) ·
[composite_benchmark.json](../../research/outputs/composite_benchmark.json) /
[COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md) (parents + gates) ·
[hfed1_results.json](../../research/outputs/hfed1_results.json) /
[hfed2_results.json](../../research/outputs/hfed2_results.json) /
[hfed3_results.json](../../research/outputs/hfed3_results.json) (the grids) ·
[hcaps1_analysis.json](../../research/outputs/hcaps1_analysis.json) (caps) ·
[research/outputs/redteam/](../../research/outputs/redteam/) (six battery reports) ·
[verify_record_engine.json](../../research/outputs/verify_record_engine.json) /
[verify_record_engine_ext.json](../../research/outputs/verify_record_engine_ext.json) /
[v7_extract_verification.json](../../research/outputs/v7_extract_verification.json)
(reconciliation) · [docs/REGISTRY.md](../REGISTRY.md) (ledger + adjudication) ·
[PROTOCOL.md](../../research/protocol/PROTOCOL.md) /
[HYPOTHESES.md](../../research/protocol/HYPOTHESES.md) /
[FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) (pre-registrations).*

**All numbers above are in-sample (IC 2020–25), on a window mined by both parent programs and by
FMA3's own 18-config ledger. There is no post-2025 holdout in this document — the pre-registered
2026H1 one-shot and the live demo are the falsification tests, and MT5 real-tick on the owner's
machine is the deployable arbiter.**
