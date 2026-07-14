# V1.0 strategy design — the what & why

The authoritative "what + why" for the locked FMA3 v1.0 blend book.
Code source of truth: [`strategy_fma3.py`](../../strategy_fma3.py) (`FMA3_CONFIG`, config hash
**`51a7541cc2aaa593`**, locked 2026-07-10) ·
[`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py) →
[`research/outputs/fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json) +
`fma3_v1_pin_curve.parquet` (the official pin) ·
[`engine/record_engine.py`](../../engine/record_engine.py) (engine of record — the FMA2
`account_engine_1m` wrapper, verified 41/41 delta 0.0).
Numbers detail lives in **[VALIDATION.md](VALIDATION.md)** (gates + red-team battery),
**[PERFORMANCE.md](PERFORMANCE.md)** (return tables) and
**[TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md)**; the verification chain is
**[RECONCILIATION.md](RECONCILIATION.md)**; the 2026H1 one-shot and deployment path are
**[DEMO.md](DEMO.md)**. The research layer beneath this package is the whitepaper — parent
anatomy in **[../whitepaper/01_DECONSTRUCTION.md](../whitepaper/01_DECONSTRUCTION.md)**,
blend mechanics and the pre-registered ladder in
**[../whitepaper/02_FEDERATION_DESIGN.md](../whitepaper/02_FEDERATION_DESIGN.md)**, the full
scorecard in **[../whitepaper/03_SCORECARD.md](../whitepaper/03_SCORECARD.md)** — cross-linked
here, not duplicated.

**All numbers are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick + live
demo are the remaining falsification tests.**

---

## 1. What v1.0 is

**FMA3 v1.0 = ONE cross-margined €10k account running BOTH frozen parent books side by side as
virtual sub-accounts — the NSF5 Core band book (7 slot-equity sleeves, `BAND_SYM_25` re-split +
H9 delta-resize) at capital share `w = 0.70`, and the FMA2 Satellite fixed-fraction book (8 sleeves ×
scale 10, F3 caps, hard limits, cash-park) at `1 − w = 0.30` — with NO cross-book rebalancing
and a single global scale `s = 1.1` on the blended fraction matrix. The locked config is
`strategy_fma3.py::FMA3_CONFIG` (config hash `51a7541cc2aaa593`); the shipped numbers are pinned
by `scripts/eval_fma3_pin.py` → `fma3_v1_pin.json`.** Neither parent's sleeves, parameters, or
internal mechanics were touched. Only two numbers are new, plus one guard verified as a no-op:

1. **`w = 0.70`** — the capital split, winner of the pre-registered H-FED-1 grid by rule (§5);
2. **`s = 1.1`** — the global scale, H-FED-3's ceiling rule re-picked probe-robust by the
   red-team adjudication FMA3-RT (§7);
3. **H-CAPS-1** — combined-book exposure caps, measured and found unnecessary: the inherited
   per-book limits compose correctly, **0 hours exceeding entitlement** (§8).

| Engine | Config | Headline |
|---|---|---|
| **Record engine (official pin)** | static blend w=0.70, s=1.1, IC 2020-25, €10k | **CAGR +101.4% / 15.73% worst-mark DD / Sharpe 2.467 / COVID tail 5.36% / 0 negY / 0 negQ / breach P(DD>30%) 0.0020 / €10k → €665,777** |
| **2026H1 one-shot** (Duka, USA500-proxy book) | same config, fresh €10k seed 2026-01-01 | **CONFIRM 4/4** — window **+12.34%**, DD **17.67%**, sub-books **+15.99% / +13.59%**, Sharpe 1.17 ([DEMO.md](DEMO.md)) |
| MT5 real-tick | — | **never run for the blend** — the deployable arbiter, pending on the owner's machine |

The owner's six gates (CAGR > 96.1%, DD < 20.9%, Sharpe > 2.03, tail ≤ 35.6%, negY 0, negQ ≤ 1)
**all clear**, and all **seven composite dimensions dominate both parents** — the only
fully-dominant point on the scale frontier ([VALIDATION.md](VALIDATION.md)).

**Read the marks carefully.** All numbers are **in-sample (IC 2020-25)**; the 2026H1 one-shot is
consumed; MT5 real-tick + live demo are the remaining falsification tests. Crisis-tail numbers
live in one engine: the record-engine 5.36% must never be quoted against Core's MT5 real-tick
35.6% — the 1m↔tick gap is documented in
[COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md), and the blend's
tick-granularity tail is *unknown by construction* until the owner's-machine MT5 run (§11).

---

## 2. Design philosophy — a blend of two frozen books

Both parents arrive **frozen**: IC 2020-25 was the development sample of both programs (FMA2 ≈
low-hundreds of design trials; NSF5 ≈ 7,560 prescreens + ~258 engine tests), so re-tuning any
sleeve parameter on the same window would be curve-fitting by installment. The FMA3 protocol
([PROTOCOL.md §3](../../research/protocol/PROTOCOL.md)) licenses a **structural-only** design
space — capital split `w`, blend rebalance mechanics, combined-book exposure limits, global
scale — few parameters, one lever per version, every bar pre-registered before the number
existed, and **DECLINE by default: ties are rejects** (+0.5pp minimum improvement bars, no
complexity for a wash). Every configuration evaluated (including failures) is in
[REGISTRY.md](../REGISTRY.md) — 16 engine configs + 2 red-team probes, ledger 18.

Blend is the *one* open channel because every sleeve-level path between the parents is
formally closed ([../whitepaper/01_DECONSTRUCTION.md §3](../whitepaper/01_DECONSTRUCTION.md)):

| Channel | Status | Reason |
|---|---|---|
| Band mechanism → Satellite's fixed-fraction book | **CLOSED** (H8) | premium is conditional on slot-equity sizing; flips **−7.31pp** under fixed-notional |
| FMA2 sleeves → NSF5 band book | **EXHAUSTED** (H14/H15) | **0-for-10** book-level tests; third pass pre-refused as p-hacking by installment |
| NSF5 sleeves → Satellite | **CONSUMED** | the one-shot 2015-19 OOS gauntlet is spent |

The lesson those closures teach — sleeve value is cadence/structure-conditional — is why the
blend **changes neither architecture**: each book keeps its own mechanics on its own
sub-capital. The thesis is structural complementarity, measured before any merged number existed
(M-0, [../whitepaper/02_FEDERATION_DESIGN.md §5](../whitepaper/02_FEDERATION_DESIGN.md)):
daily-return **ρ = +0.351** between the books, **drawdown troughs disjoint** (Satellite at 0.2% DD
during Core's trough 2021-05-23; Core at 3.9% during Satellite's trough 2022-02-10), and each book's
worst year is the other's relative refuge (2022: Satellite +32.1% vs Core +55.6%, both books' worst).
Quoted honestly: Satellite returns **−2.9%** on average across Core's ten worst days — a *softener,
not a hedge*.

---

## 3. The two sub-books

Two economically distinct, separately validated books. Sleeve-level anatomy, mechanics and
per-parent caveats are deep-dived in
[../whitepaper/01_DECONSTRUCTION.md](../whitepaper/01_DECONSTRUCTION.md); this is the summary.

| Sub-book | Sleeves | Native mechanics (untouched) | Native anchor (byte-verified) | Record-engine reference (gate basis) | Seed share | Share of blend P&L |
|---|---|---|---|---|---|---|
| **Core band book** (NSF5) | 7 | slot-equity sleeves, 1/7 each; `BAND_SYM_25` re-split (share > 0.25 / < 0.0816, 5d min-gap) + H9 delta-resize; R8 anchor extraction | `engine_reproduce.json:harvest_band_sym`, cagr_bd 0.8972 — extraction 15/15 anchor floats delta 0.0 | **+91.5% / 21.22% DD / Sharpe 2.267 / 0 negQ** | **0.70** | **~73.5%** |
| **Satellite book** (FMA2) | 8 | fixed-fraction × `GLOBAL_SCALE` 10, F3 caps, cash-park doctrine, 2 structural hard limits; config hash `48c09199fbf83d82` | `v34_s10_pin_1m.json`, cagr 0.8866 — wrapper 41/41 checks delta 0.0 | **+88.7% / 21.67% DD / Sharpe 1.854 / 1 negQ** | **0.30** | **~26.5%** |

- The record-engine reference rows are the **gate basis** — only Satellite@s10 (pin) and Core@r8
  (exact) are gate-grade; Core r9/r10 rows are linear approximations and set no gates.
- P&L shares are w-weighted native-curve growth (Core multiple 53.2×, Satellite 45.0× on €10k;
  [package_data.json](../../research/outputs/package_data.json) `sub_book_contribution`).
- The merged book trades **33 instruments**, **25,869 trades** over 2020-25 (~1,078/quarter),
  gross exposure p50 **4.52×E** — full profile in
  [TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md).

---

## 4. The blend mechanics (in full)

### 4.1 Virtual sub-account bookkeeping — the exact formula

Each book compounds its own sub-capital; **neither book's internal state ever sees the other's
P&L**. The joint target fraction at hour *h* is the capital-weighted blend of the parents'
native fraction matrices (locked in `FMA3_CONFIG["construction"]`, implemented verbatim in
`eval_fma3_pin.build_locked_matrix`):

```
fed_frac[h] = fracV7[h] · (w · A[h] / J[h])  +  fracV34[h] · ((1−w) · B[h] / J[h])

J[h] = w · A[h] + (1−w) · B[h]          (the ideal joint bookkeeping curve)
final matrix = fed_frac · s
```

- `fracV7` — Core's held-exposure hourly fraction-of-book-equity matrix from the
  byte-reconciled anchor re-run (`v7_book_frac_1h.parquet`);
- `fracV34` — the shipped Satellite book exactly as its official pin constructs it
  (`engine/books.py::build_v34_frac_1h()`: raw weights, cash-park, ×10, hard limits);
- `A`, `B` — the parents' **native** 1m equity curves normalized to 1.0 at t0, both
  byte-verified artifacts.

The record engine then simulates the **actual** combined account on `fed_frac · s`: joint
margin, joint stop-out, real fills/spreads/commissions/swaps on the blended targets. Cross-book
netting on shared instruments (XAUUSD, USTEC, USDJPY, EURGBP, BTC/ETH) is **real and measured,
not assumed** — the realized-vs-ideal drift is reported as blend friction on every grid
point (**−2.7pp CAGR** at the locked point, §5).

### 4.2 Causal hourly sampling

`A` and `B` are sampled **causally** at hour *h* (asof: last known 1m value ≤ *h*), and the
engine holds the hour-*h* target over hour *h+1*'s minutes (≥ 1-minute causal gap). One honest
asymmetry is disclosed: the Core leg replays held-exposure snapshots with a **~1-bar execution lag**
vs its native engine; the cost is priced into the measured Core@r8 record profile, so parent
references and blend candidates are compared like-for-like inside one accounting
([../whitepaper/02_FEDERATION_DESIGN.md §3](../whitepaper/02_FEDERATION_DESIGN.md)).

### 4.3 The fresh-seed convention

Sub-books are seeded at **(w, 1−w) of account equity at t0 and never re-seeded** — the split is
a *seed, not a maintained target*. The realized split then drifts with relative performance
(measured drift band **~0.63–0.75** across 2020-25 from the H-FED-2 event logs); this drift is
exactly why the shipping scale must be probe-robust across the ±20% w surface (§7). A live
deployment begins the same way: the 2026H1 one-shot seeded a **fresh €10k at (0.70, 0.30) on
2026-01-01** with no carry-over of 2020-25 book state
([FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md)).

### 4.4 Scale-invariance — why the blend is exact bookkeeping, not an approximation

The formula reproduces each parent's native behavior on its sub-account **exactly** (in the
frictionless limit) because both parents are scale-invariant in return space:

- **Core's band triggers are slot *ratios*** — `share[n] = slot_equity[n] / Σ slots` crossing
  0.25 / 0.0816 is invariant to scaling all slots by a constant; sleeve sizing is inverse-vol on
  slot equity. Running the Core book on `w·€10k` produces the identical re-split dates and the
  native path scaled by `w`.
- **Satellite's positions are equity *fractions*** — its return path is independent of starting
  capital by construction.

Hence `w·A[h]` and `(1−w)·B[h]` are the *exact* sub-account equities and `fed_frac` is the exact
joint matrix. What is **not** scale-invariant — min-lot quantization at €7k/€3k 2020 sub-books,
the 0.9 joint margin cap, the joint stop-out, netting/costs on shared instruments — is precisely
what the record engine simulates rather than assumes. Any ideal-vs-realized gap is evidence, not
model error.

### 4.5 The anti-coupling guard — and the ±€128 evidence

NSF5's overlay-ring program is the cautionary precedent: when overlay P&L shared one account
with the band core, rebalance timing became chaotically equity-sensitive — **a €128 perturbation
shifted the outcome by −€59k** — and single-account coupling was banned in that program. The
FMA3 protocol hard-codes the lesson ([PROTOCOL.md §5.7](../../research/protocol/PROTOCOL.md)):
any blend bookkeeping must isolate each book's internal trigger state from the other book's
P&L. In the static blend this holds **by construction** — the blend inputs are the parents'
native curves, not the realized joint curve — and the mandatory chaos probe confirms it
([redteam/rt_coupling.json](../../research/outputs/redteam/rt_coupling.json)):

| Probe (Core sub-book seed) | Δ final equity | Δ max DD | Tolerance | Verdict |
|---|---|---|---|---|
| **+€128** | **+0.32%** | **+0.01pp** | \|Δfinal\| < 5%, \|ΔDD\| < 1pp | ✅ within |
| **−€128** | **−1.10%** | **−0.02pp** | \|Δfinal\| < 5%, \|ΔDD\| < 1pp | ✅ within |

**PASS — the blend is chaos-stable**, in sharp contrast to the overlay-ring's −€59k. A
corollary rule carried from H-FED-2: Core's internal band min-gap clock never resets on any
blend-level event.

---

## 5. `w = 0.70` — the pre-registered grid and rule

H-FED-1 bars were committed before any merged number existed
([HYPOTHESES.md](../../research/protocol/HYPOTHESES.md); the selection rule amended 12:29,
*pre-results*): combined worst-mark **DD < 20.72%** (min parent − 0.5pp), **Sharpe > 2.317**
(max parent + 0.05), **negY 0**, **negQ ≤ 0**. CAGR is deliberately **not** a bar here — it is
bought later with scale (§7); DD/Sharpe/negQ are the structural evidence. Selection rule: the
winning `w` passes ALL bars and **maximizes Sharpe among passers**. Grid
([hfed1_results.json](../../research/outputs/hfed1_results.json), engine of record, s = 1.0):

| w (Core share) | CAGR | Max DD (worst-mark) | Sharpe | COVID tail | negY / negQ | All bars |
|---|---|---|---|---|---|---|
| 0.30 | +86.8% | 18.34% | 2.156 | 6.41% | 0 / 0 | ❌ (Sharpe) |
| 0.40 | +88.7% | 17.88% | 2.305 | 5.75% | 0 / 0 | ❌ (Sharpe) |
| 0.50 | +88.1% | 16.41% | 2.371 | 5.53% | 0 / 0 | ✅ |
| 0.60 | +89.3% | 15.20% | 2.458 | 5.39% | 0 / 0 | ✅ |
| **0.70** | **+89.7%** | **14.38%** | **2.474** | **4.96%** | **0 / 0** | ✅ **winner by rule** |

**MECHANISM CONFIRMED** ([REGISTRY.md FMA3-001](../REGISTRY.md)): the winner beats *both*
parents on DD (14.38% vs 21.22%/21.67%) and Sharpe (2.474 vs 2.267/1.854) simultaneously —
diversification the leverage dial cannot buy (re-levering Core r8→r10 costs +5.0pp DD and a negQ
for +30.6pp CAGR). Measured blend friction at w70: **−2.70pp CAGR** (ideal bookkeeping
92.41% vs realized 89.71%) — min-lot quantization, joint margin, netting/costs, priced by the
engine. Honest boundary note: **Sharpe was still rising at the grid edge — off-grid w80 was NOT
tested**; the pre-registered grid is binding (§10). Robustness of the pick: CPCV at the
allocation level re-selects w = 0.70 in **19 of 28 purged folds** (OOS-Sharpe ratio 0.98,
[VALIDATION.md](VALIDATION.md)).

---

## 6. The no-rebalance decision — all four cadences DECLINED (H-FED-2)

H-FED-2 applied the parents' H8 medicine at book level: periodically re-split TOTAL account
equity back to (0.70, 0.30) — quarterly (F2a) or band-triggered at book share `B_up` with exact
`BAND_SYM_25` semantics at N = 2 slots (F2b). Pre-registered bar: rebalanced must beat static at
the same `w` by **> +0.5pp CAGR at ≤ +0.3pp DD**, else DECLINE — cadence complexity is not paid
for. Results ([hfed2_results.json](../../research/outputs/hfed2_results.json), vs static w70):

| Cadence | Events | ΔCAGR | ΔDD | Bar (>+0.5pp at ≤+0.3pp) | Verdict |
|---|---|---|---|---|---|
| F2a calendar-quarterly | 23 | **+1.12pp** | **+0.43pp** | DD over bar | **DECLINE** |
| F2b band B_up 0.60 | 418 | +0.72pp | +0.35pp | DD over bar (degenerate†) | **DECLINE** |
| F2b band B_up 0.65 | 418 | +0.72pp | +0.35pp | DD over bar (degenerate†) | **DECLINE** |
| F2b band B_up 0.70 | 22 | **−0.34pp** | +0.02pp | pays nothing | **DECLINE** |

† At w = 0.70 a band with `B_up ≤` the target share fires at every 5-day min-gap — 418 events ≈
a 5d calendar, not a concentration trigger. The grid was registered pre-winner and **not
re-registered** per the anti-seat-shopping rule; the degeneracy is disclosed, not repaired.

**Mechanism reading: cross-book rebalancing couples the exact disjoint troughs it tries to
harvest.** The M-0 evidence (§2) shows the books' drawdowns are disjoint in time; a re-split
moves capital *into* the book that is about to draw down, buying ~1pp CAGR at a worse path. The
static blend keeps the trough disjointness intact — **static w70 stands**
([REGISTRY.md FMA3-002](../REGISTRY.md)). This also removes an entire failure class: with no
blend rebalance schedule there is nothing for schedule-chaos to couple to (the
fixed-schedule ablation is **N/A by construction**, [VALIDATION.md](VALIDATION.md)).

---

## 7. Global scale `s = 1.1` — the ceiling rule and the probe-robust adjudication

Scale is set **LAST**, on the winning structure, by a rule committed in advance (H-FED-3):
sweep `s ∈ {0.8 … 1.4}` and **ship the largest s such that worst-mark DD < 20.9%, negQ ≤ 1,
negY = 0, breach P(DD>30%) ≤ 0.12, crisis tail ≤ 35.6%**. The frontier
([hfed3_results.json](../../research/outputs/hfed3_results.json)) is smooth and monotone,
Sharpe is scale-flat, and **every point is compliant** at the locked w (negQ 0 everywhere):

| s | CAGR | Max DD (worst-mark) | Sharpe | COVID tail | Breach P(DD>30%) | €10k → | Note |
|---|---|---|---|---|---|---|---|
| 0.8 | +66.8% | 12.21% | 2.475 | 3.73% | 0.0000 | €214,623 | |
| 0.9 | +77.2% | 13.04% | 2.452 | 4.47% | 0.0000 | €308,682 | |
| 1.0 | +89.7% | 14.38% | 2.474 | 4.96% | 0.0004 | €464,991 | the raw H-FED-1 winner |
| **1.1** | **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0.0020** | **€665,777** | **SHIPPED (probe-robust)** |
| 1.2 | +114.4% | 17.17% | 2.470 | 5.88% | 0.0046 | €967,259 | aggressive frontier |
| 1.3 | +127.4% | 18.59% | 2.468 | 6.44% | 0.0138 | €1,378,091 | aggressive frontier |
| 1.4 | +140.8% | 19.89% | 2.466 | 7.09% | 0.0294 | €1,942,739 | H-FED-3 ceiling-rule pick |

**The adjudication.** The mechanical ceiling rule selected **s = 1.4** (FMA3-003, "SHIP s=1.4 —
GATES BREACHED"). Then the red-team perturbation probe **FAILED on the w+20% axis only**
([redteam/rt_perturbation.json](../../research/outputs/redteam/rt_perturbation.json)): at
w = 0.84 the worst-mark DD rises **14.38% → 17.97% (+3.59pp)**, over the pre-registered 3.0pp
threshold (w−20% is clean at +1.06pp; all quality metrics stable — ΔSharpe −0.06, negQ 0 at all
three points). Because a never-rebalanced blend's realized w **drifts** (measured band
0.63–0.75, §4.3), the adjudicated shipping rule (FMA3-RT) requires **all ceilings to hold at the
locked w AND at both ±20% w probes**. The binding constraint is the w+20% probe:
**17.97% × 1.1 ≈ 19.8% < 20.9%**, but × 1.2 ≈ 21.6% > 20.9% ⇒ **s = 1.1 ships**. The FAIL was
priced, not waived: **−39.4pp CAGR paid for probe-robustness**; `s ∈ {1.2 … 1.4}` remain
documented as the **aggressive frontier** (compliant at the locked w, not probe-robust). The
FAIL is a smooth frontier toward the measured Core-alone endpoint (DD 21.22% at w = 1.0), not a
fitted spike — the full honesty case is in
[../whitepaper/03_SCORECARD.md §3](../whitepaper/03_SCORECARD.md).

**s = 1.1 is also the only fully-dominant point on the frontier**: all seven composite
dimensions beat the dimension-wise best of both parents (below 1.1, CAGR misses the Core@r8 91.5%
bar; above it, the COVID tail exceeds the 5.54% bar). See [VALIDATION.md](VALIDATION.md).

---

## 8. Inherited hard limits — and the H-CAPS-1 no-op

Each sub-book's structural limits arrive **pre-applied inside its own fraction matrix**: Satellite's
overnight |XAUUSD| ≤ 1.80×E_sub and managed-cross ≤ 0.5×E_sub (plus its F3 per-sleeve caps and
cash-park), and Core's per-sleeve caps. The open question M-0 flagged was *stacking*: both books
are gold-heavy (~0.82×E + ~0.81×E mean abs-fraction, 86% co-active hours). H-CAPS-1 measured the
joint book directly on `hfed1_w70` — **49,379 hours**, no engine run, adoption default-YES
unless it cost > 3pp ([hcaps1_analysis.json](../../research/outputs/hcaps1_analysis.json),
measured at the s = 1.0 basis; entitlements scale identically with s, so the verdict is
scale-invariant):

| Joint exposure | p50 | p95 | p99 | max | Entitlement | Hours exceeding |
|---|---|---|---|---|---|---|
| Overnight \|XAUUSD\| | 1.10×E | 1.75×E | 1.97×E | **2.03×E** | **2.03×E** (= \|Core own gold\|×share + 1.80×Satellite share) | **0** |
| Managed crosses (EURCHF/EURSEK/EURNOK/AUDNZD) | — | — | — | 0.187–0.191×E | 0.1945×E (0.5×E×Satellite share; Core trades none of them) | **0** |
| \|USTEC\| sanity | — | — | 1.13×E | 1.78×E | (sanity check, no cap) | — |

**Verdict: NO-OP (verified)** — the inherited per-book caps compose correctly; joint exposure
never exceeds the sum of entitlements, so **no joint cap was added**
([REGISTRY.md FMA3-C1](../REGISTRY.md)). The guard lever existed, was measured, and was shown
unnecessary — which is itself evidence the blend does not manufacture hidden leverage.

---

## 9. Locked configuration & parameters

The entire shipped configuration ([`strategy_fma3.py`](../../strategy_fma3.py), hash
**`51a7541cc2aaa593`**, locked **2026-07-10**):

| Parameter | Value | Meaning / provenance |
|---|---|---|
| `structure` | **static_federation** | H-FED-1 winner; H-FED-2 declined (§6) |
| `w_v7` | **0.70** | Core band-book capital share, grid winner by rule (§5) |
| `global_scale` | **1.1** | H-FED-3 ceiling rule + FMA3-RT probe-robust re-pick (§7) |
| parent A operating point | Core core7 band, **R8 anchor extraction** | `v7_book_frac_1h.parquet` from the byte-reconciled anchor (15/15 delta 0.0) |
| parent B operating point | Satellite @ **GLOBAL_SCALE 10** | `books.py::build_v34_frac_1h()` = the FMA2 pin construction (41/41 delta 0.0) |
| cross-book rebalance | **none** | the split is a seed; realized w drifts (band 0.63–0.75) |
| joint caps | **none added** | H-CAPS-1 NO-OP (§8) |
| engine of record | FMA2 `account_engine_1m::simulate_account_1m` via `engine/record_engine.py` | joint margin cap 0.9, joint stop-out 0.5, worst-mark DD convention |
| sample | IC 2020Q1–2025Q4, **€10,000** | the pin sample (`fma3_v1_pin.json`) |

There is no EA yet: v1.0 ships as the locked Python book + pinned artifacts; MT5 real-tick on
the owner's machine is the deployable arbiter and next step ([DEMO.md](DEMO.md)).

---

## 10. What was tried and declined

The full multiple-testing ledger is [REGISTRY.md](../REGISTRY.md) (FMA3-000 … FMA3-FWD, 18
configs; DSR from the ledger 1.0000 at n = 20, stable at ×4 stress). Every richer variant was
stress-tested and rejected **with cause** — static w70 @ s = 1.1 is the frontier:

| Tried | Result | Why declined |
|---|---|---|
| Quarterly cross-book rebalance (F2a) | +1.12pp CAGR / +0.43pp DD | over the ≤ +0.3pp DD bar |
| Band rebalance B_up 0.60 / 0.65 (F2b) | +0.72pp / +0.35pp, 418 events | degenerate at w70 (fires every 5d min-gap); DD over bar |
| Band rebalance B_up 0.70 (F2b) | −0.34pp CAGR | pays nothing |
| s = 1.2 / 1.3 (aggressive frontier) | DD 17.17% / 18.59% at locked w | not probe-robust at w+20% (§7) |
| s = 1.4 (ceiling-rule pick) | CAGR +140.8% / DD 19.89% | the +141% mirage — perturbation FAIL (w+20% ΔDD +3.59pp) adjudicated it down to s = 1.1 |
| Off-grid w = 0.80 | **never run** | Sharpe still rising at the grid edge, but the pre-registered grid is binding — no off-grid picks |
| Joint exposure caps (H-CAPS-1) | measured, 0 hours exceeding | NO-OP — inherited caps compose correctly (§8) |

Explicitly out of scope (graveyard-adjacent, never tested): new sleeves; re-tuned sleeve params;
regime switching between the books (dead in both parent registries); DD-throttles/vol-targeting
at any level (inverts, −2 to −31pp in the parents); weight optimization beyond the fixed w grid;
the closed import channels of §2
([../whitepaper/02_FEDERATION_DESIGN.md §6](../whitepaper/02_FEDERATION_DESIGN.md)).

---

## 11. Honest caveats

- **Everything is in-sample, on a window mined twice over.** IC 2020-25 was both parents'
  development sample; FMA3 added 18 ledger configs. DSR 1.0000 covers *FMA3's own*
  few-parameter selection only — the sleeves' alpha is assumed from the parents' validation
  records, not re-proven here. The 2026H1 one-shot is consumed (CONFIRM 4/4,
  [DEMO.md](DEMO.md)); **MT5 real-tick + live demo are the remaining falsification tests.**
- **Crisis-tail numbers live in one engine.** Record-engine tail 5.36% vs Core's MT5 real-tick
  35.6% is an engine-granularity gap, not a risk reduction; the blend's tick-level tail is
  unknown until the owner's-machine MT5 run.
- **The capital split drifts by design** (never rebalanced; measured band 0.63–0.75). The
  probe-robust scale rule exists precisely to absorb this — all owner ceilings hold across
  w 0.56–0.84 at s = 1.1 — but a drift *beyond* ±20% has no coverage and should trigger review.
- **Blend friction is real: −2.7pp CAGR** at the locked point (ideal 92.4% vs realized
  89.7% at s = 1.0) — min-lot quantization at €7k/€3k 2020 sub-books, joint margin, netting;
  measured by the engine, not assumed away.
- **The Core leg carries a ~1-bar execution lag** vs its native engine (held-exposure snapshot
  convention). Comparisons in this package are like-for-like, but the absolute level is not the
  native book's.
- **Forward-honest Sharpe is not 2.47.** By the parents' own convention the budgeted band is
  **1.2–1.5** (Satellite's disclosed ratio); the 2026H1 one-shot printed **1.17** on 4 months —
  within tolerance of that band, and 4 months is statistically weak by construction. Judge the
  live book against the band, not the pin.
- **The 2026H1 CONFIRM is a proxy-book confirmation, not a reconciliation**: USA500 proxies
  USTEC (corr 0.89), Satellite ran at 0.88× reduced breadth on 14-symbol Duka coverage, Duka ≠ IC
  feed. Directional evidence only ([DEMO.md](DEMO.md)).
- **The −2.9% softener is not a hedge** (§2). The thesis is disjoint weak periods, not negative
  correlation; a regime that correlates the books (ρ → 0.6+) removes the DD benefit — the ρ
  by-year band is 0.115–0.460 in-sample.

---

## 12. How to reproduce it

Every shipped number rebuilds from config + pinned artifacts; no heavy engine run is needed to
*read* the package (all curves and matrices are pinned). The verification chain, one command per
link ([RECONCILIATION.md](RECONCILIATION.md)):

| Command | What it proves | Expected |
|---|---|---|
| `python3 strategy_fma3.py` | prints the locked config + hash | `config_hash: 51a7541cc2aaa593` |
| `python3 engine/v7_bridge/run_extract.py` (~1 min) | Core fraction matrix = the byte-reconciled NSF5 anchor | **15/15 anchor floats delta 0.0** |
| `python3 scripts/verify_record_engine.py` (~6–8 min) | record engine reproduces the FMA2 Satellite pin | **41/41 checks delta 0.0**, curve max-abs-delta 0.0 |
| `python3 scripts/eval_fma3_pin.py` (~7 min) | the shipped numbers rebuild from `FMA3_CONFIG` alone (engine + 5000-path bootstrap) | **all 5 headline metrics delta 0.0** vs `hfed3_results.json[hfed3_s110]`; `PIN OK`, all owner gates true |

The decision trail re-runs with `scripts/run_hfed1.py` / `run_hfed2.py` / `run_hfed3.py`
(H-FED-1/2/3), `scripts/analyze_caps.py` (H-CAPS-1), `scripts/redteam/rt_*.py` (the six-check
battery) and `scripts/run_forward_oneshot_native.py` (the consumed 2026H1 one-shot — do not
re-run for selection; the window is spent). Validation status: owner gates **6/6**, composite
dimensions **7/7 dominant**, red-team **5 PASS / 1 FAIL-adjudicated / 1 N/A**, forward one-shot
**CONFIRM 4/4** — see [VALIDATION.md](VALIDATION.md) and [DEMO.md](DEMO.md).

**All numbers are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick + live
demo are the remaining falsification tests.**
