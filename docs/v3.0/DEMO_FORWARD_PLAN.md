# Demo-forward plan — IC + FTMO demo accounts (v3)

*Authored 2026-07-16. The forward-test charter + production-readiness checklist for running
`FableBookNative` live on **two demo accounts** (IC and FTMO) on the owner's VPS. Decisions
baked in: **3-month** window · **IC €10k / FTMO €80k** · **VPS Windows Server** hosting ·
**1-week trade-disabled shakedown** before enabling.*

---

## 1. Purpose — what the demo proves

The alpha is not on trial; the evidence for the book is strong. The demo is a **de-risking +
generalization** test, four things:

1. **Live plumbing** — the live-computing EA runs 24/5 forward with no stalls; refuse-latches
   fire only on genuine corruption; clean warm-blob resume after restarts; correct
   sizing / netting / breaker on a live feed.
2. **Generalization (OOS)** — the book behaves as modelled on data it has **never seen**.
   *There is no valid prior OOS forward* (the earlier 2026-H1 one-shot was not properly
   conducted and is not used) — **this demo produces the first valid OOS read.**
3. **R2 execution reality** — the live-feed friction (swap / spread / slippage) vs the record
   engine, and the native-EA behaviour on whatever real conditions occur.
4. **Risk behaviour live** — the drawdown path, min-margin-level, and — for FTMO — the rule
   envelope (breaker fires, daily / max-loss headroom) under real ticks.

## 2. What it does NOT prove (state upfront)

- **A real crisis** — unless one happens in-window. A calm 3 months proves plumbing +
  calm-era generalization, **not tail survival** (that remains the RECON-12 real-tick + the
  `f_tail` crisis work).
- **Fills at capital** — demo fills are near-frictionless; real slippage at size is a later step.

## 3. Success criteria — pre-committed, measurable

**IC demo — s=1.6, €10,000, 1:30**
| Metric | Pass line |
|---|---|
| Plumbing | 0 unexplained refuse-latches · 0 crashes · clean warm-resume after ≥1 restart |
| Position fidelity | **✅ REDEFINED + OWNER-APPROVED 2026-07-16 — PRE-COMMITTED, locked before the demo starts.** The original wording ("live position matches the EA's own computed target ≥99% of bars") is **not measurable, because it is not well-defined**: the executor has a rebalance dead-band (`InpRebalBand=0.25`, `BookExec.mqh:~276`) and *deliberately does not retrade* while `‖want\|-\|held‖/\|held\| ≤ 0.25`. Held ≠ target is **designed behaviour** — scored literally, the EA reads ~0%. Replaced with the executor's actual **invariant**, per leg per bar: (a) `want=0 → held flat`; (b) `sign(held) = sign(want)`; (c) drift within the band. Legs legitimately deferred (market closed / no quote) are excluded but **counted separately** — a leg stuck deferred *is* a failure. Pass line: **≥99% of bars with every active leg satisfying the invariant**, 0 sign violations. |
| Drawdown | live worst-mark DD **within the ~22.9% modelled band** (flag if > 28%) |
| Margin | min ML **≥ 110%** at all times |
| Friction | measured swap / spread ≈ the modelled decomposition (within band) |
| Return | **no pre-committed level** — no valid OOS estimate exists. Success = **net-positive with risk inside the bands above**; the demo *establishes* the first valid OOS number. |

**FTMO demo — s≈0.70, €80,000, 1:30, 3% daily breaker**
| Metric | Pass line |
|---|---|
| Rule envelope | **0 max-loss (10%) breaches** · daily-5% breaches ≤ the ≤1/yr-implied rate |
| Breaker | 3% daily breaker **fires correctly** and is net-neutral-to-positive |
| Margin · plumbing | min ML healthy · same plumbing/fidelity criteria as IC |

## 4. Duration & cadence
- **3 months, pre-committed. No mid-run dial changes.**
- **Weekly** reconciliation checkpoint (§6D); a **month-1.5** mid-read.

## 5. Kill / abort criteria (pre-committed)
Halt + investigate on any of: a refuse-latch on **non-corruption**; **min ML < 105%**; live DD
**> 28%** (IC) or **any 10% breach** (FTMO); position fidelity **< 95%** over a day.

---

## 6. Production-readiness checklist

### A. Warm-start — ✅ THE BLOB EXISTS (2026-07-16, RECON-13)
**Produced and accepted.** `FMA3_native_state.json` (7,876,336 B, sha256 `2f3a2c40…`) +
`.coredrive` (8,334 B, sha256 `8574a2bf…`) in `Common\Files`, both at
`last_emit_hour = last_flush_hour = 2025-12-31 22:00 UTC`, delta 0s → **coherent, passes the
EA's load check**. Run 46: 55 min, `hours=49378`, `refuse=no`, 0 save warnings.

**Accepted at 22:00, not the nominal 23:00** — the hour is cosmetic: the EA resumes from
`last_emit_hour` and backfills, so it changes nothing functionally. Do **not** expect it to
bit-match `endBASE` (a_h 53.235 vs 53.098; b_h 47.131 vs 44.916): endBASE holds the *golden's
frozen-curve* values, the blob holds the EA's *own live 6-year computation on the broker
feed* — the same divergence that gives €2.95M vs the golden's €3.87M. a_h to **0.26%** over
6 years is the reassuring read; b_h's **4.9%** is the known R2 gap.

**⚠ The pair lives in `Common\Files` and ANY future `InpSaveInTester=true` run overwrites it.
Back it up.**

**Remaining: the Step 2 live-resume test** — the real gate, and indifferent to the hour.

*(original scoping retained below)*

### A-orig. Warm-start — the one real prerequisite
A live **cold** start is a demo-killer: the EA computes from *now* and the catch-up gate holds
sizing until indicators warm (~250 weekdays ≈ ~1 year of ~0 trading) — `FableBookNative.mq5`
live cold path. The **only** way to trade from day 1 is the **warm-blob resume**: load the v2
state blob + `.coredrive` sidecar → resume from its last hour and backfill forward.
**SCOPED (2026-07-16) → [`mt5/ea/RUNSHEET_WARMSTART.md`](../../mt5/ea/RUNSHEET_WARMSTART.md).** The
EA needs **two coherent files**: the book-state blob + a `.coredrive` sidecar, cross-checked on
resume (refuses on mismatch). Findings:
- The **2025-12-31 book-state blob already exists and its save→load→resume roundtrip is bit-exact**
  (`endBASE` == `endRESUME`: b-balance 434,133 / CoreSim seed 532,229.843 / a_h·b_h 53.098·44.916).
  The hard, path-dependent half is proven.
- The `.coredrive` sidecar is **EA-only** (no Python producer), and the pair must be coherent → the
  complete blob is produced by **one owner EA run** (Step 1: a fast 1m-OHLC 2020→2025-12-31 pass with
  `InpSaveInTester=true`), then the **live-resume test** (Step 2) certifies it in practice.
- Forward-past-2025-12-31 has **no golden to certify against** (WARMSTART_DESIGN §7.4) — fine (the
  demo *is* the forward test); the Step-2 live-resume is the practical validation. Sanctioned forward
  (out-of-sample-boundary) warm-start, *not* the design-forbidden in-sample pre-warming.

### B. Live config, per account
`InpAllowLiveTrading = true` (demo only) · `InpSaveState = true` (restart continuity) ·
`InpLog = true` · telemetry file on · dials per preset (IC 1.6 / €10k / breaker 0;
FTMO 0.7 / €80k / breaker 3.0). Two chart instances (one per account), each on its demo login.

### C. Logging spec (audit result — 2026-07-16)
**Already captured (keep on):** per-hour telemetry — `book_frac` per symbol, `a_h/b_h/j`,
balance, equity, trading-flag, breaker `fires`, fidelity mismatches (`sc_mm`), unready/skipped;
the per-decision CSV; refuse-latch / feed-gap / warm-resume events → Experts log.
**Add / capture for the demo:**
1. **Margin & min-ML in the hourly telemetry row** — small EA add; it is a *primary* success
   criterion and is not currently logged. *(the one code change)*
2. **Archive the Journal + Experts logs** on the VPS — they rotate daily and carry the
   refuse / feed / restart events. Daily copy to a retained folder.
3. **Periodic deal-history export** (per-trade Profit / Swap / Commission) — the input to the
   friction decomposition and the native `k`. Weekly export.

### D. Reconciliation harness (how we *learn*)
A **weekly** script that ingests the demo's telemetry + deal history and compares to the
**record engine run forward on the same live period** → retention, per-bar fidelity, friction
decomposition, native `k`, margin path. This turns "it ran" into "here is what we learned." The
demo's `a_h/b_h/j` telemetry vs the record is the direct R2 (live-feed-basis) measurement.

### E. Monitoring
A live watch view of the §3 success-criteria metrics + alerts on the §5 kill criteria (min ML,
DD, refuse events, fidelity).

### F. Hosting
Owner's **VPS Windows Server**, 24/5 uninterrupted. Warm-blob resume covers restarts, but a
gap loses live data — so keep the terminal always-on and the logs archived (§6C.2).

### G. Graduated rollout
1. **Week 0 — trade-DISABLED shakedown (1 week):** `InpAllowLiveTrading=false` on both demos.
   Compute + log only, **zero orders** — proves plumbing, warm-resume, telemetry, and collects
   OOS signal risk-free.
2. **Week 1 — flip trade-ENABLED** on both demos → the 3-month clock starts.

---

## 7. Open items to clear before start — and the GO/NO-GO verdict

**Verdict (go/no-go review 2026-07-16 → [DEMO_GO_NOGO.md](DEMO_GO_NOGO.md)): trade-ENABLE is
NO-GO until the must-fixes below clear.** The trade-disabled shakedown may start.

Done: ~~margin/ML telemetry~~ ✅ (PR #17) · ~~reconciliation harness~~ ✅ · ~~live watcher +
VPS runbook~~ ✅ (PR #19). In progress: warm blob (§6A, producing).

**MUST-FIX before enable** (full detail in DEMO_GO_NOGO.md):
1. ~~**[CODE] OPEX calendar hardcoded to 2026-02**~~ → **FIXED IN SOURCE** (PR #22): the
   calendar now *computes* the 3rd-Friday week per query, so the horizon is gone rather than
   re-dated; in-window behaviour is bit-identical (0 divergences, every day probed). The
   root cause was inherited from the read-only parent's study window, which is why it passed
   bit-exactness. **Still owed: recompile + `CheckCoreSignal.mq5` + bpure re-cert** — deferred
   so as not to swap the binary under the in-flight warm-blob run (that run ends 2025-12-31,
   before the horizon, so it stays valid). *Not closed until the re-cert passes.*
1b. **[DATA] Policy-rate tables expired** (USD 2025-12-11 / JPY 2025-01-24) — these *hold the
   last rate forward* rather than dying, so this is carry/swap **drift**, not signal death.
   Needs the real rate path from the owner; not inventable. See DEMO_GO_NOGO §1b.
2. ~~**[MEASUREMENT]** position fidelity, breaker-fires, FTMO envelope not captured~~ →
   **FIXED IN SOURCE** (PR #23). New per-symbol `rec=P` rows (`want`/`held`/`defer`) plus
   `n_stops`, `worst_eq` and `day_anchor` in the hourly row; `reconcile_demo.py` computes
   fidelity + the 5%/10% envelope. **⚠ The fidelity criterion itself was undefined** (the
   0.25 rebalance band means held ≠ target *by design*) — §3 redefines it against the
   executor's invariant and **needs owner sign-off**.
3. ~~**[MONITOR]** silent cold-start has no alarm~~ → **FIXED IN SOURCE** (PR #23): `warm`
   is now an hourly telemetry column, not just two Experts-log lines.

**Recompile is owed once — and once only.** #1, #2 and #3 are all batched into the single
post-warm-blob-run recompile + re-cert. None are closed until that re-cert passes.

**MUST-MONITOR (Week-0 shakedown):** the live weekend/holiday **clock-stall** — the RECON-8j/8k
fix was tester-only; prove this broker's `CopyRates` returns `n=0` (not `n<0`) for closed symbols.

**SHOULD-FIX:** §6B must tell the owner to **provision account leverage** (IC 1:30 / FTMO 1:30);
log `FED_WorstMarkEquity` hourly (the current DD is hourly-equity, understates the 28% line).

*Graduation to live capital remains a separate, downstream owner decision after the demo clears
the §3 criteria — made with the in-sample discount in full view, starting small and scaling
slowly. That is out of scope for this plan.*
