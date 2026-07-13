# V1.0 engine reconciliation — three engines, one accounting

**Verdict: `reconciled`.** FMA3 v1.0's official numbers live in ONE accounting — the engine of
record (FMA2's 1-minute worst-mark single cross-margined account engine, imported READ-ONLY and
wrapped by [`engine/record_engine.py`](../../engine/record_engine.py)) — and every bridge into
that accounting is verified at **delta 0.0 or bit-identical**: the v3.4 pin reproduces 41/41 +
minute curves 0.0, the v7.0 anchor extraction matches 15/15 + 9/9 legs bit-exact, the
2026-capable ext engine is bit-identical (38/38, tolerance zero), and the shipped pin rebuilds
from config alone at delta 0.0. The residual gaps between the parents' *native* engines and the
record accounting are **measured and attributed, not open**: the v7 native-vs-record equity gap
(€532,230 vs €492,611) is the record engine's ~1-bar execution lag plus its cost/margin
conventions; federation assembly costs a measured −2.7pp CAGR of real friction; and the
MT5↔1m crisis-tail gap is priced at 35.6% vs 5.54% for v7 alone. Zero unexplained mismatches
anywhere in the chain — hence `reconciled`, not `reconciled_with_notes`: the notes are priced,
not pending. The one reconciliation that *cannot* be done in Python — MT5 real-tick of the
federation itself — is explicitly not claimed here and is listed below as the owed arbiter.

**All numbers are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick + live
demo are the remaining falsification tests.** Battery context in [VALIDATION.md](VALIDATION.md)
(Tier 1 is this document's chain); research depth in
[../whitepaper/01_DECONSTRUCTION.md §4](../whitepaper/01_DECONSTRUCTION.md) and
[../whitepaper/03_SCORECARD.md §5](../whitepaper/03_SCORECARD.md).

---

## (A) The three engines (and the fourth that is still owed)

The parents' official numbers were produced by **two mutually incomparable native engines**; the
owner's original six gates straddle them (the 96.1 / 20.9 / 35.6 references are MT5 real-tick
R10; the negQ convention exists only in Python 1m accounting) — no engine ever produced all six
simultaneously, so "beats both parents" was unfalsifiable until FMA3 pinned one accounting
([PROTOCOL.md §1](../../research/protocol/PROTOCOL.md)):

| Engine | What it is | Official numbers it owns |
|---|---|---|
| **Native band engine** (NSF5) | `gbandrebal/sim.run_generic`, R8, IC 2020-25, idealized close-and-reseed, bd-return accounting | v7.0 anchor: **CAGR 89.72% (bd) / 15.70% bd-DD / 19.44% tick-DD / Sharpe 2.58 / €532,230 / 31 band + 0 harvest triggers** (`engine_reproduce.json:harvest_band_sym`, byte-reconciled) |
| **Native FMA2 1m engine** | `research/account_engine_1m.py::simulate_account_1m` — one balance, one margin pool, worst-intrabar mark, full IC cost realism | v3.4 pin @ s10: **CAGR +88.66% / 21.67% worst-mark DD / Sharpe 1.854 / €449,708 / 20,403 trades / 1 negQ (2023Q1 −1.42%)** (`v34_s10_pin_1m.json`) |
| **Record engine** (FMA3 engine of record) | the FMA2 1m engine via the verified `record_engine.py` wrapper — v3.4 runs *identically by construction*; the v7 book is replayed through it via the extracted per-1m-bar position matrix | v7.0 @ r8 in record accounting: **+91.5% / 21.22% / Sharpe 2.267 / €492,611 / 6,406 trades / 0 negQ**; the federation pin: **+101.4% / 15.73% / 2.467 / €665,777** ([composite_benchmark.json](../../research/outputs/composite_benchmark.json), [fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json)) |
| **MT5 real-tick** (deployable arbiter — **not yet run for the federation**) | `PortfolioV7.mq5` R10 in the NSF5 program; nothing exists for v3.4 or the federation | v7.0-only native headline: 96.1% CAGR / 20.9% Maximal eq-DD / **35.6% COVID Relative DD** / Sharpe 2.03 — quoted for the tail gap in (B3), never mixed with record numbers |

Every FMA3 selection, gate, and red-team number was computed in the record engine only —
same-engine comparisons throughout; the composite gates are the dimension-wise best of the two
parents *as measured in it*.

---

## (B) The measured translation costs

### B1. v7 native → record: **€532,230 vs €492,611** (~1-bar lag + conventions)

The v7 leg enters the federation as a held-exposure snapshot: the extraction re-ran the exact
NSF5 anchor pipeline capturing per-1m-bar lots (**15/15 anchor floats delta 0.0**, incl. 31 band
+ 0 harvest triggers), and the record engine replays that matrix, lagging each hourly row into
the next hour's first traded minute and applying its own cost/margin/stop-out conventions. The
price of one common accounting, measured on the same book:

| v7.0 @ R8, same book | Native band engine | Record engine (r8, exact) |
|---|---|---|
| Final equity (€10k) | **€532,230** | **€492,611** |
| CAGR | 89.72% (bd convention) | +91.5% (calendar convention, internally consistent: 49.26× over 5.996y) |
| Max DD | 15.70% bd / 19.44% tick | 21.22% worst-mark / 20.91% close |
| Sharpe | 2.58 (bd) | 2.267 (daily) |

This cost applies **identically to parent references and federation candidates** — every
comparison in the package is like-for-like, but the absolute record-engine level is not the
native book's. *Bookkeeping note (found and RESOLVED during assembly):* an early
`COMPOSITE_BENCHMARK.md` draft printed the native €532,251 figure in the v7@r8 record row; the
MD cell was reconciled to the pinned JSON (€492,611) on 2026-07-10 — gate dimensions were
identical in both files throughout
([../whitepaper/01_DECONSTRUCTION.md §4](../whitepaper/01_DECONSTRUCTION.md)).

### B2. Federation assembly friction: **−2.7pp CAGR**, priced not assumed

Putting both books in ONE €10k cross-margined account (sub-book seeds €7k/€3k in 2020) costs
real friction the ideal weighted-sum bookkeeping does not see — min-lot 0.01 quantization
(coarsest at the small early seeds), joint margin, netting/costs on shared instruments:

| At the locked point (w70, s=1.0) | Ideal bookkeeping | Realized in engine | Friction |
|---|---|---|---|
| CAGR | 92.4% | **89.7%** | **−2.7pp** |

Grid-wide the friction spans −2.1 to −3.4pp
([hfed1_results.json](../../research/outputs/hfed1_results.json) `friction_cagr_pp`). It is
inside every reported number — the federation's +9.9pp CAGR over the best parent is *net* of it.

### B3. The MT5 ↔ 1m crisis-tail gap: **35.6% vs 5.54%** (v7-only measured, standing for the campaign)

Putting both parents in one accounting produced the first *measurement* of the gap that was
previously only an assumption
([COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)):

| v7.0 COVID crisis tail (2020-02-15 → 04-15, peak-to-trough) | Value |
|---|---|
| MT5 real-tick, R10 (native headline) | **35.6%** |
| Record engine (1m worst-mark, IC bars), r8 exact | **5.54%** |
| Record engine, r9 / r10 (linear approx) | 6.69% / 7.15% |

Tick-granularity spread blowouts during Mar-2020 **do not exist in 1m bars**. Standing
consequences: (1) record-engine tail numbers must **never** be quoted against MT5 numbers —
same-engine comparisons only; (2) the federation's MT5 run on the owner's machine remains the
deployable arbiter of the tail; (3) v7.0's −21.8% MT5 2020Q1 is a real-tick artifact of this
same gap (it is *not even negative* in record accounting), so the composite negQ gate is a
1m-convention gate by construction.

---

## (C) The verification chain

Exact counts and deltas under every number in the package; the first two links re-verify before
any experiment session (PROTOCOL §5.6):

| Link | Check | Result |
|---|---|---|
| Parents' native anchors (REGISTRY [FMA3-000](../REGISTRY.md)) | v3.4 pin re-run in FMA2's engine; v7 anchor re-run via NSF5 `v7val/tier12.py` | v3.4 pin **byte-identical** (byte-reproduced twice); v7 tier12 **byte PASS** (89.72% / €532,230 / 31 triggers) |
| Record-engine wrapper ([verify_record_engine.json](../../research/outputs/verify_record_engine.json)) | 41 metric checks + minute-level equity/worst curves vs the pinned v3.4 reference | **41/41 delta 0.0**; curve max-abs-delta **0.0** (index match true) |
| v7 anchor extraction ([v7_extract_verification.json](../../research/outputs/v7_extract_verification.json)) | 15 anchor floats + trigger counts vs `engine_reproduce.json`; per-leg self-test vs NSF5's engine; positions→equity rebuild | **15/15 delta 0.0** (incl. 31 band + 0 harvest, both half-windows); **9/9 legs bit-exact**; consistency **< 2.4e-15 relative** |
| Ext engine ([verify_record_engine_ext.json](../../research/outputs/verify_record_engine_ext.json)) | the range-parameterized copy (needed for 2026H1) vs the same pin, tolerance zero | **BIT-IDENTICAL: 38/38 metrics exactly equal**; equity + worst curves `np.array_equal` true |
| v1.0 pin reproduction ([fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json), `fma3_lock.log`) | matrix rebuilt from `FMA3_CONFIG`, 24 quarters re-run, 5,000-path bootstrap re-drawn, vs the FMA3-003 grid point | **5/5 headline metrics delta 0.0** (cagr / maxdd_worst / sharpe / final_equity / crisis_tail) — `PIN OK`, all owner gates true |
| Forward margin instrumentation (REGISTRY [FMA3-FWD](../REGISTRY.md), [forward_oneshot.json](../../research/outputs/forward_oneshot.json)) | the instrumented kernel that measured F3 (stop-outs / cap-binds) vs the stock engine | **bit-identity-gated** — instrumentation proven inert before the one-shot ran |

Reproduce: `python3 scripts/verify_record_engine.py` (~6–8 min) ·
`python3 engine/v7_bridge/run_extract.py` (~1 min) ·
`python3 scripts/verify_record_engine_ext.py` (~5 min) ·
`python3 scripts/eval_fma3_pin.py` (~7 min).

---

## (D) What is NOT reconciled yet

1. **No MT5 run of the federation book — the owed arbiter.** The record engine is a 1m-bar
   worst-mark model; the deployable truth is MT5 real-tick on the owner's machine, and the
   federation has never been run there. The v7-only measured tail gap (35.6% vs 5.54%, B3) shows
   how large the translation *can* be in a crisis window; the federation's tick-granularity tail
   is therefore **unknown by construction**. v3.4 has never had a tick run at all — its 21.67%
   worst-mark DD has no tick counterpart to reconcile against.
2. **The 2026H1 forward book is a directional confirmation, not a reconciliation.** It ran on
   the Duka feed (documented ~8pp CAGR_bd 2020-25 divergence vs IC), 14-symbol coverage (v3.4 at
   ~0.88× breadth, uncovered legs zeroed), with USA500 proxying USTEC (corr 0.89) — the proxy
   book ≠ the deployed book, disclosed in advance
   ([FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md)).
3. **The owner's six original gates still straddle two engines** (secondary scoreboard). The
   federation's 5.36% record-engine tail clears the 35.6% MT5-derived bar only in the trivial
   sense; the honest tail comparison is composite (5.36% vs the parents' same-engine 5.54%), and
   the deployable tail number awaits the MT5 run.

## Honest notes (divergences that remain by design — none is a defect)

1. **€532,230 vs €492,611 (v7 native vs record)** — ~1-bar execution lag + cost/margin
   conventions; measured, attributed, applied like-for-like to every comparison (B1).
2. **−2.7pp federation friction** — real min-lot/margin/netting costs of one account; priced by
   the engine rather than assumed away (B2).
3. **Record ≠ tick in the tails** — 1m bars cannot see tick spread blowouts; never cross-quote
   (B3).
4. **CAGR/Sharpe conventions differ between the native band engine (bd-return) and the record
   engine (calendar/daily)** — each engine's figures are internally consistent and are only ever
   compared within-engine.

---

**Bottom line:** every number in the v1.0 package traces to one verified accounting — parents
byte-reproduced in their native engines, both bridges into the engine of record at delta 0.0
(41/41 + curves, 15/15 + 9/9 legs), the ext engine bit-identical (38/38), the shipped pin
rebuilt from config at delta 0.0, and the forward kernel bit-identity-gated — with the three
cross-engine gaps (~1-bar lag €532,230→€492,611, −2.7pp federation friction, 35.6%-vs-5.54%
tick↔1m tail) measured and disclosed rather than open. Zero unexplained mismatches;
`reconciled`. The MT5 real-tick run of the federation on the owner's machine is the one owed
reconciliation and the deployable arbiter. All numbers are in-sample (IC 2020-25); the 2026H1
one-shot is consumed; MT5 real-tick + live demo are the remaining falsification tests.
