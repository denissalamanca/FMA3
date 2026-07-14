# Live-architecture decision — 3-way comparison + recommendation

**Question:** how should the frozen `fed_frac` replay become a live system? Three designs on the table:
- **A — Hybrid** ([`FORWARD_GENERATOR_SPEC.md`](FORWARD_GENERATOR_SPEC.md)): Python computes the whole blend → appends a CSV → the MQL5 EA (`FableFederation_V3`) tails it and trades.
- **B — Native all-MQL5** ([`DESIGN_OPT1_NATIVE_MQL5.md`](DESIGN_OPT1_NATIVE_MQL5.md)): both sub-books simulated inside MQL5, blend + trade in-terminal, no CSV.
- **C — Python bot** ([`DESIGN_OPT2_PYTHON_BOT.md`](DESIGN_OPT2_PYTHON_BOT.md)): one VPS bot runs the sims + blend + MT5 execution, no MQL5 EA.

**Recommendation up front: none of the three as-stated — ship the *synthesis* they all point to (call it D).** Rationale below.

---

## 1. Four truths every design shares (architecture-independent)

1. **The Core book is path-dependent.** Its band re-split + seed-chain is internal state, not a function of the latest bars. In **Python** there is no one-bar step (the repo's single sanctioned `NotImplementedError`) → interim is a ~10–25 min full re-extraction *every hour*. **In MQL5 this is already solved** — `V7Core.mqh` *is* that incremental stepper, G1-proven to the cent (€398,368.75).
2. **The Satellite book is the opposite.** Its 8-sleeve pandas alpha is a big, fidelity-fragile port to any non-Python language — but it **already runs live in Python**: the FMA2 brain writes hourly targets bit-identical to the pin (6.66e-16), and the EA already consumes them (`V34Live.mqh`, InpV34Mode=2). Live Satellite is essentially *done*.
3. **The native-equity shadows (`a_h`,`b_h`) are the dangerous core, identical everywhere.** They weight every emitted number, can't be read off the live account, and a re-based (not ratio-chained) splice seed is silently wrong while passing every `<1e-12` self-check. Unavoidable in A, B, C, D.
4. **Live is out-of-sample, on a third feed.** The pin was built on the IC dev feed; live uses the broker feed (~8pp CAGR divergence seen on Duka). No design reproduces €3,872,872 live — all reproduce the model *recipe*, then differ by feed + friction. Live output is 2026 forward evidence, not a reconciled record. **Reconciliation = monitor, don't feed back** (§4).

**Reading 1+2 together:** each language is strong exactly where the other is weak. Core is easy in MQL5 / hard in Python; Satellite is easy in Python / hard in MQL5. A design that forces *both* books into one language pays the port tax on one of them. That is the whole thesis.

---

## 2. The pros/cons matrix

| Dimension | A — Hybrid | B — Native MQL5 | C — Python bot |
|---|---|---|---|
| **Core forward** | ✗ Python re-sim ~10–25 min/hr | ✓✓ V7Core stepper (solved) | ✗ Python re-sim ~10–25 min/hr |
| **Satellite forward** | ✓ Python brain (live, proven) | ✗✗ port 1400-line alpha; may never reach parity | ✓ Python brain (live, proven) |
| **On-terminal safety backstop** | ✓ the EA lives in the terminal | ✓ the EA lives in the terminal | ✗ bot dies holding positions → needs a GuardianEA anyway |
| **Strategy-Tester validation gate** | ✓ (MQL5 tester) | ✓✓ dynamic, no-CSV (Core half now) | ✗ lost — forward-only validation, weeks not minutes |
| **Fragile handoff** | ✗ full-book CSV append race + tail-reader (new, unbuilt) | ✓ none (but blocked on Satellite wall) | ~ no CSV, but the bot *is* the trader |
| **Deploy substrate** | terminal + Python | terminal only | Windows/Wine + terminal + Python (MetaTrader5 is Windows-only) |
| **Net new risky code** | Core re-sim service + CSV race + FedReplay tail-reader | V7Sim `a_h` + **Satellite alpha port** + 3 in-proc ledgers | exec port + watchdog/resync + Core re-sim + GuardianEA |
| **Honest floor it degrades to** | itself | **Core-native + Satellite-Python-bridge** (still a hybrid for half) | itself + GuardianEA |

**What each is actually good for:**
- **A** is the general fallback, but pays the Core Python-re-sim tax and owns a brand-new fragile CSV-append/tail-reader race — the exact fragility you flagged.
- **B pure** dies on the Satellite wall: a bit-perfect pandas→MQL5 port still misses the pin because it runs a *different feed*, and it may never reach parity while the Satellite sleeves are still being tuned. Its **Core-native tester mode**, however, is a genuine low-risk win.
- **C** makes the *easy* part (execution) its headline and inherits every *hard* part unchanged, then adds a safety regression (no passive dead-man) that forces a GuardianEA back onto the terminal — so it isn't even "one unit."

---

## 3. Recommendation — D: Core-native (MQL5) + Satellite-brain-bridge (Python) + on-terminal EA

This is Option 1's own "honest floor," reached deliberately instead of as a fallback. It assigns each book to the language where it's already solved:

```
   ┌─ V7Sim.mqh (in the EA) ──────────┐         ┌─ FMA2 brain (Python, EXISTS) ─┐
   │ V7Core stepper, one bar at a time │         │ build_book(rebuild) hourly    │
   │ → f7[h] + a_h  (native, in-term)  │         │ → f34[h] (+ b_h shadow)       │
   └───────────────┬───────────────────┘         └──────────────┬────────────────┘
                   │                          targets.json (EXISTING V34Live path)
                   └───────────────┬───────────────────────────┘
                                   ▼
                    Blender + Executor + Guardian  (all in the MQL5 EA, on-terminal)
                    fed=f7·(w·a/j)+f34·((1−w)·b/j) → size off BALANCE → trade 33 magics
```

**Why D dominates the three:**
- **Kills the Core blocker** (the hardest upstream item in A and C) — V7Core already steps forward natively; no Python re-extraction, no lock_v5 isolation, no splice-seed re-base for Core.
- **Avoids the Satellite wall** (B's killer) — no pandas→MQL5 alpha port; uses the brain that already produces Satellite live, bit-identical to the pin.
- **Keeps the on-terminal EA** (safety + the Strategy-Tester gate) that C throws away.
- **Shrinks the fragile handoff from the whole book to Satellite-only — over a mechanism that already exists and is proven** (`V34Live.mqh` consuming the brain's `targets.json`). This is *not* A's new, unbuilt full-book CSV-append/tail-reader race; it's the shipped live-Satellite path.
- **Net new risky code is the smallest of any option:** essentially `V7Sim` (V7Core forked to bookkeep an idealized standalone account → `a_h`) + the blend + the native-equity seed. The Satellite side is reused.

**What D honestly costs (no papering over):**
- It is **still a Python→file hybrid for the Satellite half** — the exact shape you object to, just minimized and over a proven channel rather than a new one. If "zero Python in the live loop" is a hard requirement, only B-pure satisfies it, and B-pure is blocked on the Satellite port that may never close.
- `V7Sim`'s `a_h` (idealized worst-mark standalone equity) is **brand-new MQL5, unproven** — V7Core is proven as a *real-account tracker*, not as an idealized-fill shadow. This needs its own parity gate (vs `v7_book_equity_1m.parquet`, noliq).
- `b_h` (Satellite native equity) must be produced somewhere — cleanest is a small Python shadow stepping `account_engine_1m._run_chunk` alongside the brain (so the Satellite bridge carries `f34`+`b_h`), which the maps rate *incremental and tractable*.
- The **splice-seed danger and the OOS/feed-divergence caveats are unchanged** — they belong to the model, not the plumbing.

---

## 4. The reconciliation question — settled (all designs agree)

**Do not feed real fills back into the sub-book sims. Monitor the gap; correct only from a same-feed batch re-run.** Both workflows converged on this as *definitional, not preference*:
1. The model **is** the two idealized, account-independent native curves. A live s-levered, jointly-margined account **cannot reconstruct them** — so a real-equity → sim-balance → frac → real-sizing loop is a *different, unvalidated strategy*.
2. The 6 shared symbols net into one real position each, so **per-book real P&L is physically unmeasurable** — feedback isn't even well-defined.

The one legitimate correction channel is **correction-from-batch**: periodically re-run the frozen pipeline forward *on the same broker feed* and reseed a sim only if it drifts beyond tolerance. The real↔sim gap stays a *monitored friction ratio* (RECON-4 ≈ 0.66–0.95×), never a control input. Consequence to accept: the live system is permanently **shadowed by** a Python batch oracle — the Python pipeline is never fully deleted by any design.

---

## 5. Suggested path (staged, reversible, no premature build)

1. **Now (design only):** ratify D as the target. Nothing is built until the IC/FTMO dials commit — the live stream must be validated at the *deployable* dial and it is the 2026 OOS gate.
2. **Cheap go/no-go first (from B's plan §8.1):** measure the feed-provenance number — run the Satellite brain on broker-exported bars vs the frozen cache, propagate through `static_fed`, and put a real number on "how far does live-feed Satellite land from the pin." This gates *every* design and costs a day.
3. **P0 — V7Sim tester spine:** fork V7Core → idealized standalone account → `a_h`/`f7`, run it dynamically in the tester at position level (B's genuine win, low-risk). Proves the Core half with no CSV.
4. **P1 — Satellite bridge + `b_h` shadow:** wire the existing brain live-path; add the small Python `b_h` stepper; blend in the EA; reconcile same-feed.
5. **P2 — live demo** on the deployable dial, logged as forward/OOS evidence, with the target-less GuardianEA as the on-terminal dead-man. New `.ex5` ⇒ FMA3-RECON-N.

**Fallbacks, ranked:** if the Satellite-brain live-wiring proves fragile, D degrades to **A** (full CSV) with the Core half still native — strictly better than A-as-specified. If "no Python live" becomes a hard mandate, the only door is **B-pure**, gated on the Satellite port passing parity (do not start it while the Satellite sleeves are still being tuned). **C** is not recommended for a live-money path: it discards the tester gate and the on-terminal backstop for a code-reuse win that D captures without those sacrifices.
