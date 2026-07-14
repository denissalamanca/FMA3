# FMA3 v1.0 — The Fable Book

**FMA3 v1.0 is the first merged descendant of two independently-derived, firewalled trading
programs: one cross-margined €10k IC Markets EU Raw account carrying NewStrategyFable5's Core
band book (70% of capital) and FableMultiAssets2's Satellite fixed-fraction book (30%) as
never-rebalanced virtual sub-accounts at global scale 1.1 — both parents' sleeves frozen, the
merge alpha purely structural, every decision pre-registered before its number existed.** Config
sources of truth: [`strategy_fma3.py`](../../strategy_fma3.py) (config hash `51a7541cc2aaa593`,
locked 2026-07-10) → [`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py) →
[`research/outputs/fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json).

**Everything in this document is in-sample (IC 2020–25) — a window mined by both parent programs
and by FMA3's own 18-config ledger. The pre-registered 2026H1 one-shot (in flight) and the live
demo are the falsification tests; MT5 real-tick on the owner's machine is the deployable
arbiter.**

---

## Executive summary

**What was built.** A capital blend. Every sleeve-level path between the two parents had
been formally closed by their own experiment records (the band mechanism cannot survive
fixed-fraction sizing; FMA2's sleeves went 0-for-10 inside the band book; the one-shot OOS window
for NSF5→FMA2 imports is spent). The only genuinely untested level left was the one that changes
*neither* architecture: run both books whole, each compounding its own virtual sub-capital with
its own native mechanics, inside one real cross-margined account. That structure — static split
w = 0.70/0.30, no cross-book rebalancing, no new caps, scale 1.1 — is FMA3 v1.0.

**The parents, one line each.** Core (NewStrategyFable5) is a 7-sleeve equal-capital
trend/momentum book whose concentration-band re-split harvests volatility across ~zero-correlated
sleeves — MT5 real-tick 96.1% CAGR / 20.9% DD, with the COVID crisis tail as its known weakness.
Satellite (FableMultiAssets2) is an 8-sleeve fixed-fraction consistency book — 88.7% CAGR / 21.7% DD
with 1 negative quarter in 24, whose crisis/meanrev/seasonal seats *pay* during stress (2020 was
its best year). The blend thesis: Satellite's stress-payers cushion exactly the tail that caps
Core's leverage, and Core's trend capture lifts exactly the Sharpe ceiling Satellite could not raise
from inside. Book correlation was measured first: ρ = +0.351, drawdown troughs disjoint.

**The headline (engine of record, 2020–25, €10k).**

| CAGR | Max DD (worst-mark) | Sharpe | COVID tail | negY | negQ | Breach P(DD>30%) | €10k → |
|---|---|---|---|---|---|---|---|
| **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0/6** | **0/24** | **0.002** | **€665,777** |

All six of the owner's original gates clear, and **all seven pre-registered composite dimensions
dominate both parents in the engine of record — the first fully-dominant point in the two
programs' combined history** ([03_SCORECARD.md §1](03_SCORECARD.md)).

**The honesty framework.** Every bar was pre-registered before its number was computed
([PROTOCOL.md](../../research/protocol/PROTOCOL.md),
[HYPOTHESES.md](../../research/protocol/HYPOTHESES.md), committed 2026-07-10); every config —
including failures — is in the [multiple-testing ledger](../REGISTRY.md); one lever moved at a
time, DECLINE by default (H-FED-2's rebalancing was declined, H-CAPS-1 proved a no-op). The
red-team battery's one FAIL (the w+20% perturbation probe) was not waived but priced: the shipped
scale was cut from the ceiling-rule 1.4 to the probe-robust 1.1, forfeiting 39pp of in-sample
CAGR for robustness ([03_SCORECARD.md §3](03_SCORECARD.md)). All numbers remain in-sample; the
forward-honest Sharpe expectation is ~1.6–2.0 (parents' discount convention), not 2.47; the
2026H1 one-shot was pre-registered before any 2026 number existed and is running now.

---

## Document map

| Doc | What it covers |
|---|---|
| **[01_DECONSTRUCTION.md](01_DECONSTRUCTION.md)** | The two frozen parents — what each book is, why it works, its native numbers in both engines, the firewall history, why every sleeve-level merge channel is closed, and the engine-of-record decision |
| **[02_FEDERATION_DESIGN.md](02_FEDERATION_DESIGN.md)** | The blend architecture — virtual sub-account bookkeeping, scale-invariance proof, the anti-coupling guard, the M-0 measurements, and the full pre-registered evaluation ladder |
| **[03_SCORECARD.md](03_SCORECARD.md)** | The results — the new frontier scorecard, the experiment trail, the scale-frontier adjudication, the red-team battery, reconciliation & reproduction, honest caveats, and the 2026H1 one-shot slot |
| [docs/REGISTRY.md](../REGISTRY.md) | The honest multiple-testing ledger — every config evaluated, incl. failures and the FMA3-RT adjudication |
| [PROTOCOL.md](../../research/protocol/PROTOCOL.md) · [HYPOTHESES.md](../../research/protocol/HYPOTHESES.md) · [FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) | The pre-registrations (all committed before their numbers existed) |
| [COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md) | Both parents measured for the first time in one accounting; the composite gates; the measured MT5↔1m crisis-tail gap |

---

## Definition of done

**DONE (2026-07-10):**

- [x] Recon/assimilation of both parents (7 readers + critique, `research/intel/`)
- [x] Pre-registered protocol + hypothesis slate (committed before any merged number)
- [x] Engine bridges verified — record engine 41/41 delta 0.0 + curves 0.0; Core extract 15/15
      delta 0.0; ext engine bit-identical ([03 §5](03_SCORECARD.md))
- [x] Baselines byte-reproduced (Satellite pin; Core Python anchor)
- [x] Composite benchmark — both parents in the engine of record; gates derived; M-0 measured
- [x] H-FED-1 static blend — mechanism confirmed, winner w = 0.70
- [x] H-FED-2 rebalanced blend — all cadences DECLINED (static stands)
- [x] H-CAPS-1 combined-book caps — verified NO-OP (inherited caps compose)
- [x] H-FED-3 scale re-pick — frontier mapped, all 7 points compliant
- [x] Red-team battery — 6 checks; 1 FAIL adjudicated into the probe-robust scale (s = 1.1)
- [x] v1.0 lock + pin — config-hashed, reproduces delta 0.0 end-to-end

**OPEN:**

- [ ] **2026H1 one-shot forward confirmation — IN FLIGHT** (pre-registered F1–F4 in
      [FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md); results will be appended
      verbatim to [03_SCORECARD.md §7](03_SCORECARD.md))
- [ ] MT5 real-tick run of the locked book on the owner's machine (the deployable arbiter — the
      1m↔tick tail gap makes this non-optional)
- [ ] Live demo (the real falsification test)

---

**In-sample disclosure.** All performance figures in this whitepaper are in-sample (IC 2020–25).
The window was the development sample of both parent programs before FMA3 existed, and FMA3
added 18 ledger configs on top; the DSR 1.0000 at n = 20 bounds only FMA3's own selection, not
the parents' mining. There is no post-2025 holdout in this document — the pre-registered 2026H1
one-shot and the live demo are the falsification tests, and MT5 real-tick on the owner's machine
is the deployable arbiter.
