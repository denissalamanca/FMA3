# FMA3 federation design — virtual sub-accounts over two frozen books

**FMA3's merge architecture is a FEDERATION: one real cross-margined €10k account carrying both
parent books as virtual sub-accounts, each compounding its own sub-capital with its own native
mechanics, with capital allocation between the books as the only new lever.** Code sources of
truth: [`scripts/run_hfed1.py`](../../scripts/run_hfed1.py) (H-FED-1 static federation; helpers
canonicalized in [`scripts/run_hfed1_lib.py`](../../scripts/run_hfed1_lib.py)) +
[`scripts/run_hfed2.py`](../../scripts/run_hfed2.py) (H-FED-2 rebalanced variants), all executed
through the engine of record via [`engine/record_engine.py`](../../engine/record_engine.py) on the
verified inputs `research/outputs/v7_book_frac_1h.parquet` (from
[`engine/v7_bridge/extract_positions.py`](../../engine/v7_bridge/extract_positions.py), 15/15
anchor floats delta 0.0) and [`engine/books.py`](../../engine/books.py)`::build_v34_frac_1h`
(delegating to the FMA2 pin builder, 41/41 checks delta 0.0). The hypothesis slate and bars are
pre-registered in **[HYPOTHESES.md](../../research/protocol/HYPOTHESES.md)** and
**[PROTOCOL.md](../../research/protocol/PROTOCOL.md)** (committed 2026-07-10, before any merged
number was computed). Parent anatomy is **[01_DECONSTRUCTION.md](01_DECONSTRUCTION.md)**.

> **Results are deliberately absent from this document.** The experiment grid is running under
> the pre-registered protocol; **results sections follow in `03_SCORECARD.md` (post-lock)**.

**All numbers below are in-sample (IC 2020–25). There is no post-2025 holdout in this document —
the pre-registered 2026H1 one-shot and the live demo are the falsification tests.**

---

## 1. Why federation is the licensed open channel

Every sleeve-level path between the parents is formally closed
([01_DECONSTRUCTION.md §3](01_DECONSTRUCTION.md)):

| Channel | Status | Reason |
|---|---|---|
| Band mechanism → v3.4's fixed-fraction book | **CLOSED** (H8) | premium is conditional on slot-equity sizing; **flips −7.31pp** under fixed-notional |
| FMA2 sleeves → NSF5 band book | **EXHAUSTED** (H14/H15) | **0-for-10** book-level tests; crisis inverts −20.9pp on the band cadence; third pass pre-refused as p-hacking by installment |
| NSF5 sleeves → v3.4 | **CONSUMED** | the one-shot 2015-19 OOS gauntlet is spent; sole survivor (mag_xau) already inside v3.4 |

The load-bearing lesson from those closures is that **sleeve value is cadence/structure-
conditional** — verdicts do not transfer across portfolio architectures. The federation is the one
level that *changes neither architecture*: v7.0 keeps its slot-equity band mechanics intact on its
own sub-capital, v3.4 keeps its fixed-fraction cash-parked convention intact on its own
sub-capital. It is also genuinely untested — the firewall forbade it in both parent programs, and
the pre-registered core thesis
([HYPOTHESES.md](../../research/protocol/HYPOTHESES.md)) is structural complementarity: v3.4's
stress-payers (crisis/meanrev/seasonal; 2020 was its best year at +127.6%) should cushion exactly
the crisis tail that caps v7.0's leverage, while v7.0's explosive trend capture (record-engine
Sharpe 2.267) should lift exactly the Sharpe ceiling that v3.4's own allocator studies proved
unreachable from inside (reweighting tops out at Sharpe 1.94). The falsifiable precondition (H0)
— high book correlation (ρ ≥ 0.6) or co-timed drawdowns would materially weaken the thesis — was
measured first (§5).

The slate deliberately contains **zero sleeve-level changes**; the licensed design space is
capital split `w`, federation rebalance mechanics, combined-book exposure limits, and global scale
— few parameters, one lever at a time, DECLINE by default
([PROTOCOL.md §3, §5](../../research/protocol/PROTOCOL.md)).

---

## 2. The mechanics — virtual sub-account bookkeeping

Each book compounds its own sub-capital; **neither book's internal state ever sees the other's
P&L**. The joint target fraction at hour *h* is the capital-weighted blend of the parents' native
fraction matrices (implemented in `run_hfed1.py::build_fed_frac`):

```
fed_frac[h] = fracV7[h] · (w · A[h] / J[h])  +  fracV34[h] · ((1−w) · B[h] / J[h])

J[h] = w · A[h] + (1−w) · B[h]          (the ideal joint bookkeeping curve)
```

where:

- `fracV7` is v7.0's **held-exposure** hourly fraction-of-book-equity matrix, extracted from the
  byte-reconciled anchor re-run (`v7_book_frac_1h.parquet` — a snapshot at the last 1m bar of each
  hour, not a decision signal; the record engine lags row *h* into hour *h+1*'s first traded
  minute, ~1 bar later than the native engine acted);
- `fracV34` is the shipped v3.4 book exactly as the official pin constructs it
  (`books.build_v34_frac_1h()` → `eval_v34_pin_s10.build_c2()`: raw weights, cash-park, ×10,
  hard limits);
- `A`, `B` are the parents' **native** equity curves normalized to 1.0 at t0 — both byte-verified
  artifacts (`v7_book_equity_1m.parquet::eqc`; the pinned `v34_s10_pin_curve.parquet::equity`) —
  sampled **causally** at hour *h* (last known 1m value ≤ *h*).

The record engine then simulates the **actual** combined account on `fed_frac`: joint margin,
joint stop-out, real fills/spreads/commissions/swaps on the blended targets. Cross-book netting on
shared instruments (XAUUSD, USTEC, USDJPY, EURGBP, BTC/ETH) is therefore **real and measured, not
assumed**. The realized joint curve may drift from the ideal `J`; that drift (ideal-vs-realized
CAGR/DD deltas) is reported as the **federation-friction measurement** on every grid point.

Two bookkeeping properties matter for gate integrity:

1. **The blend inputs are the native curves, not the realized joint curve.** The sub-account
   weights `w·A/J` and `(1−w)·B/J` are computed from the parents' own verified equity paths, so
   each book's sizing evolves exactly as it did natively — the anti-coupling guard of §4 holds
   *by construction* in H-FED-1, not by hope.
2. **Every record-engine number is attributable to a named run** (`run_record(label=...)`), and
   the reproduction gate ([PROTOCOL.md §5.6](../../research/protocol/PROTOCOL.md)) requires the
   v3.4 pin and the v7 extract to re-verify before any experiment session.

---

## 3. Scale-invariance — why the blend is exact bookkeeping, not an approximation

The federation formula reproduces each parent's native behavior on its sub-account **exactly** (in
the frictionless limit) because both parents are scale-invariant in return space:

- **v7.0's band triggers are slot *ratios*.** `BAND_SYM_25` fires on
  `share[n] = slot_equity[n] / Σ slots` crossing 0.25 or 0.0816 — shares are invariant to
  multiplying all slot equities by any constant. Sleeve sizing is inverse-vol on slot equity, so
  positions scale linearly with sub-capital. Running the v7 book on `w·€10k` instead of `€10k`
  produces the identical re-split dates, identical slot shares, and an equity path that is the
  native path scaled by `w`.
- **v3.4's positions are equity *fractions*.** The book targets signed notional as a fraction of
  its (sub-)equity at every bar; its return path is independent of starting capital by
  construction.

Hence `w·A[h]` and `(1−w)·B[h]` are the *exact* sub-account equities, `J` is the exact
frictionless federation curve, and `fed_frac` is the exact joint fraction matrix that holds both
books' native exposures simultaneously. What is **not** scale-invariant — min-lot quantization at
small sub-capital (€3k–€7k sub-books in 2020), the 0.9 joint margin cap, the joint stop-out, and
netting/costs on shared instruments — is precisely what the record engine simulates rather than
assumes. The design cleanly separates *exact bookkeeping* (the blend) from *measured friction*
(the engine), so any gap between ideal and realized is evidence, not model error.

One honest asymmetry is disclosed: the v7 leg replays **held exposure** through the record engine
with a ~1-bar execution lag relative to the native anchor (the extractor's snapshot convention).
The cost of that lag is already priced into the measured v7@r8 record profile
([01_DECONSTRUCTION.md §1.8](01_DECONSTRUCTION.md)) — the same matrix, same convention, feeds the
federation — so parent references and federation candidates are compared like-for-like inside one
accounting.

---

## 4. The anti-coupling guard — the overlay-ring lesson

NSF5's overlay-ring program supplies the cautionary precedent
([NSF5 docs/v7/research/V75_DESIGN.md](../../../NewStrategyFable5/docs/v7/research/V75_DESIGN.md),
[V75_CHARTER.md](../../../NewStrategyFable5/docs/v7/research/V75_CHARTER.md),
[ROADMAP.md](../../../NewStrategyFable5/docs/v7/research/ROADMAP.md)): when overlay P&L was allowed
to share a single account with the band core, rebalance timing became **chaotically
equity-sensitive — a €128 perturbation shifted the outcome by −€59k** — and single-account
coupling was banned outright in that program. Rebalance-schedule chaos is also why H15's T-B2
(+1.35pp) was written off as unattributable. The FMA3 protocol hard-codes the lesson
([PROTOCOL.md §5.7](../../research/protocol/PROTOCOL.md)):

- **Isolation requirement:** any federation bookkeeping must isolate each book's internal trigger
  state from the other book's P&L (virtual sub-account accounting). In H-FED-1 this holds by
  construction (§2); in H-FED-2, federation re-splits must respect both books' internal state —
  **v7's band min-gap clock does NOT reset on federation re-splits.**
- **Mandatory falsifier:** a cross-book **coupling perturbation test (±€128 on one book's start
  capital**, à la NSF5's chaos probe) for any adopted federation mechanic.
- **Mandatory discriminator:** any result that depends on rebalance scheduling gets the
  **fixed-schedule ablation** (freeze the trigger dates, re-run) — on winners only, never as a
  rescue for failures.

---

## 5. The M-0 evidence (measurements, no adoption decision)

Pre-registered as measurements — not experiments — in
[HYPOTHESES.md M-0](../../research/protocol/HYPOTHESES.md); computed on the two parent curves in
the engine of record
([composite_benchmark.json](../../research/outputs/composite_benchmark.json) `m0` block,
summarized in [COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)):

| M-0 measurement | Result | Reading |
|---|---|---|
| Daily-return ρ (full 2020-25) | **+0.351** | H0 precondition (ρ ≥ 0.6 would weaken the thesis) **passes** |
| ρ by year | 2020 0.388 · 2021 0.348 · **2022 0.115** · 2023 0.376 · 2024 0.460 · 2025 0.419 | lowest coupling exactly in the stress year |
| Co-drawdown at troughs | v3.4 at **0.2%** DD during v7's trough (2021-05-23); v7 at **3.9%** during v3.4's trough (2022-02-10) | **DD troughs disjoint** |
| v3.4 return on v7's 10 worst days | **−2.9%** average | a softener, not a hedge — quoted honestly |
| v7 return on v3.4's 10 worst days | −1.4% average | symmetric softening |
| BOOK_USTEC ↔ FMA2 `intraday` | co-active 11.0% of hours, **ρ = 0.046** on co-active hours | **duplicate-edge concern CLEARED** (the ρ 0.87 finding was F1↔intraday; BOOK_USTEC is a different sleeve) |
| XAUUSD gross-exposure stacking | v7 **~0.82×E** + v3.4 **~0.81×E** mean abs-fraction, **86% co-active hours** | **gold-stacking flag → H-CAPS-1 is load-bearing before any scale-up** |
| Complementarity of weak years | v3.4's 2022 (+32.1%) vs v7's worst record-engine year 2022 (+55.6% at r8); v7's 2021/2025 (+84%/+123%) vs v3.4's mid years | the structural complementarity the federation monetizes |

Also noted from the same measurement pass: USDJPY (v7 ~1.10×E via S5_JPY+S6 vs v3.4 ~0.05×E) and
EURGBP (v7 ~1.71×E vs v3.4 ~0.15×E) are v7-dominated exposures; USTEC stacks 0.34×E + 0.15×E with
54% co-active hours (the H-CAPS-1 sanity check covers it).

---

## 6. The pre-registered evaluation ladder

All bars were committed **before any merged-book number was computed**
([HYPOTHESES.md](../../research/protocol/HYPOTHESES.md), 2026-07-10; the H-FED-1 selection rule
was amended 2026-07-10 12:29 *before any grid result was read*). Evaluation order:

**M-0 → H-FED-1 → H-FED-2 (only if the H-FED-1 mechanism survives) → H-CAPS-1 → H-FED-3 (scale,
LAST) → red-team battery ([PROTOCOL.md §6](../../research/protocol/PROTOCOL.md)) → lock →
whitepaper → 2026H1 one-shot.**

### H-FED-1 — static federation (no cross-book rebalance)

Capital split `w` to the v7 book / `(1−w)` to v3.4 at t0; each book compounds its own sub-capital
natively; combined account = sum of sub-books, margin/stop-out joint.

| Element | Pre-registered value |
|---|---|
| Grid | `w ∈ {0.30, 0.40, 0.50, 0.60, 0.70}` (v7 share), native operating points (v7 @ R8-anchor extraction, v3.4 @ scale 10); **no off-grid picks** |
| Bar: combined worst-mark DD | `< min(parent DDs) − 0.5pp` = **< 20.72%** |
| Bar: combined Sharpe | `> max(parent Sharpes) + 0.05` = **> 2.317** |
| Bar: negative years | **0** |
| Bar: negative quarters | `≤ min(parents)` = **0** |
| CAGR | **NOT a bar** here — bought later with scale (H-FED-3); DD/Sharpe/negQ are the structural evidence |
| Selection rule (amended pre-result) | the winning `w` passes ALL bars and maximizes Sharpe among passers; if none passes all, the static mechanism FAILS, and H-FED-2 runs only if ≥1 point passed the risk half (DD + negQ) — rebalancing may add the return half, but may not rescue a config that failed on risk |

### H-FED-2 — rebalanced federation (cross-book vol-harvesting)

As H-FED-1 plus periodic re-split of TOTAL account equity back to `(w, 1−w)` between the books —
the H8 mechanism applied at book level, where the two "slots" are high-vol, ρ ≈ 0.35 books.

| Element | Pre-registered value |
|---|---|
| F2a | calendar-quarterly re-split (the v13-REBAL medicine at book level) |
| F2b | band-triggered re-split: book share > `B_up` or < `B_dn = 1 − B_up`, `B_up ∈ {0.60, 0.65, 0.70}`; daily close decision, act next server midnight, 5d min-gap — **exact `BAND_SYM_25` semantics at N = 2 slots** |
| Bar (on top of all H-FED-1 bars) | rebalanced must beat static H-FED-1 at the same `w` by **> +0.5pp CAGR at ≤ +0.3pp DD**, else DECLINE (cadence complexity not paid for) |
| Mandatory | fixed-schedule ablation on any F2 winner; coupling perturbation (±€128) on sub-book seeds; v7's internal band gap clock does not reset on federation re-splits |

### H-CAPS-1 — combined-book structural limits (safety lever, before scale re-pick)

Re-derive v3.4's two hard limits for the combined book: the overnight |XAUUSD| cap must count
**BOOK_XAU + seasonal + mag_xau + crisis** gold stacking (M-0 measured ~0.8×E + ~0.8×E at 86%
co-activity); managed-cross 0.5×E unchanged; add a combined |USTEC| sanity check
(BOOK_USTEC + intraday). **Bar:** caps must not cost > 3pp CAGR at equal DD — and per the v3.4
"structural rule beats fitted pin" doctrine, the rule is kept anyway if free. This lever can only
REDUCE exposure; adoption is default-YES unless it costs > 3pp.

### H-FED-3 — scale re-pick on the winning structure (LAST lever)

Mechanical rule, committed in advance: sweep global scale `s ∈ {0.8, 0.9, 1.0, 1.1, 1.2, 1.3,
1.4} × native` on the winning configuration and **ship the largest s such that: worst-mark DD
< 20.9%, negQ ≤ 1, negY = 0, breach P(DD>30%) ≤ 0.12, crisis tail ≤ 35.6%.** If no `s` clears the
owner's CAGR gate (> 96.1%) under those ceilings, the highest-CAGR compliant `s` is the honest
frontier and is shipped as such (the PROTOCOL §2 honesty rule). Both fraction matrices scale
linearly; caps that bind at higher `s` (gold overnight, managed-cross, margin cap 0.9) bind
naturally inside the engine.

### H-TAIL-1 — conditional (only if H-FED-1 fails on the DD dimension)

If the books' drawdowns prove co-timed, test v3.4's crisis-sleeve weight ×{1.5, 2.0} **inside the
v3.4 sub-book**, funded from its own cash-park (total v3.4 gross unchanged). This is the ONLY
lever licensed to touch a parent weight, it is conditional, and it uses v3.4's own freed-weight
mechanism. **Bars:** combined crisis tail improves ≥ 2pp at ≤ 0.5pp CAGR cost; DECLINE otherwise.

### Red-team battery before lock ([PROTOCOL.md §6](../../research/protocol/PROTOCOL.md))

On the winning configuration, in order: (a) parameter-perturbation grid (±20% structural params);
(b) fixed-schedule ablation where applicable; (c) 20d-block bootstrap breach (5000 paths, seed
20260709); (d) CPCV (8 blocks, k=2, purge 10d) at the allocation level; (e) Duka second-feed
cross-check (14 syms, USA500 proxy for USTEC, documented gaps); (f) LOO by sleeve-family — no
keystone; (g) coupling perturbation ±€128; (h) DSR from the
[experiment registry](../REGISTRY.md) ledger; (i) 2026H1 one-shot per PROTOCOL §4 (criteria
pre-registered in FORWARD_TEST.md before the run); (j) capacity/min-lot feasibility at €10k.

### Explicitly out of scope (graveyard-adjacent, will not be tested)

New sleeves; re-tuned sleeve params; regime switching between the books (dead in both parent
registries); DD-throttles/vol-targeting at any level (inverts, −2 to −31pp); weight optimization
beyond the fixed `w` grid (1/N doctrine + allocator-study kill); carrying FMA2 sleeves as band
slots or the band inside v3.4 (closed channels, [01 §3](01_DECONSTRUCTION.md)); anything on either
parent's kill list.

---

## 7. Honest caveats

- **Everything is in-sample.** IC 2020–25 is heavily mined by both parents; FMA3 uses it only for
  few-parameter, pre-registered structural grids ([PROTOCOL.md §4](../../research/protocol/PROTOCOL.md)
  data ledger). The 2026H1 holdout stays untouched until the one-shot; the live demo is the real
  falsification test.
- **The composite gates are deliberately hard.** In the record accounting v7.0 alone dominates
  v3.4 on five of seven dimensions, so the federation must beat a strong single-book alternative,
  not a weak pair — the H-FED-1 bars (DD < 20.72%, Sharpe > 2.317, negQ 0) already encode this.
  Simple re-levering v7 is the honest null alternative: r8→r10 buys +30.7pp CAGR for +5.0pp DD,
  breach 0.012→0.116 and a 2022Q4 negQ — the federation's job is to buy CAGR cheaper than the
  leverage dial does.
- **Crisis-tail numbers live in one engine.** The record-engine COVID tail (5.5–7.8% for the
  parents) must never be quoted against the MT5 35.6%; the final book's MT5 run on the owner's
  machine is the deployable arbiter of the tail ([01 §4](01_DECONSTRUCTION.md)).
- **v7 r9/r10 rows are linear approximations** (native caps do not rescale) and set no gates;
  only v3.4@s10 (pin) and v7@r8 (exact) are gate-grade parent references.
- **M-0's −2.9% softener is not a hedge.** The federation thesis is complementarity of weak
  *periods* and disjoint troughs, not negative correlation; H-TAIL-1 exists precisely for the
  co-timed-DD contingency.
- **Min-lot quantization at €10k sub-books is real friction** (sub-capital €3k–€7k in 2020) and is
  measured by the engine, not assumed away; it is also why the ideal-vs-realized drift is reported
  on every grid point.

---

*Sources: [HYPOTHESES.md](../../research/protocol/HYPOTHESES.md) +
[PROTOCOL.md](../../research/protocol/PROTOCOL.md) (pre-registered 2026-07-10);
[composite_benchmark.json](../../research/outputs/composite_benchmark.json) /
[COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md) (M-0 + parent records);
[verify_record_engine.json](../../research/outputs/verify_record_engine.json) and
[v7_extract_verification.json](../../research/outputs/v7_extract_verification.json) (bridge
verification); [`scripts/run_hfed1.py`](../../scripts/run_hfed1.py) /
[`run_hfed1_lib.py`](../../scripts/run_hfed1_lib.py) / [`run_hfed2.py`](../../scripts/run_hfed2.py)
(mechanics); NSF5 overlay-ring record:
[docs/v7/research/V75_DESIGN.md](../../../NewStrategyFable5/docs/v7/research/V75_DESIGN.md),
[V75_CHARTER.md](../../../NewStrategyFable5/docs/v7/research/V75_CHARTER.md),
[ROADMAP.md](../../../NewStrategyFable5/docs/v7/research/ROADMAP.md); experiment ledger:
[docs/REGISTRY.md](../REGISTRY.md).*

> **Results sections follow in `03_SCORECARD.md` (post-lock).** Nothing in this document depends
> on the winning configuration; it describes the frozen parents' interface and the pre-committed
> rules by which the winner will be chosen.

**All numbers above are in-sample (IC 2020–25). There is no post-2025 holdout in this document —
the pre-registered 2026H1 one-shot and the live demo are the falsification tests.**
