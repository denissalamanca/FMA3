# Demo pre-launch GO / NO-GO review (2026-07-16)

*Adversarial 3-lens review (config · warm-start/plumbing · logging completeness)
before committing 3 months to the demo. **Verdict: trade-ENABLE is NO-GO until the
must-fixes below clear.** The trade-DISABLED shakedown (§6G.1) *can* start — it is
the right place to observe several of these live — but do not flip
`InpAllowLiveTrading=true` until items 1–3 are done.*

---

## What's confirmed OK
- **All three presets** (IC / FTMO / WARMSTART) match their decided dials exactly, 1:1 vs the EA inputs — no fat-finger. The `AllowLiveTrading=false→true` flip flow (§6G) is correct.
- **Warm-start book-state** roundtrip is bit-exact (endBASE == endRESUME). The native EA does **not** depend on the frozen stream past 2025-12-31 (it computes live) — with the one exception in must-fix #1.
- **Friction (swap + commission)** is capturable from the deal history. Return / net is computable.

## MUST-FIX before trade-ENABLE

### 1. [CODE] The OPEX calendar is hardcoded to 2026-02 → silent signal death in-demo
**→ FIXED IN SOURCE 2026-07-16 (PR #22). Recompile + re-cert still pending — see below.**

`CoreSignal.mqh:630` (`CCsOpexCal`): `while(y < 2026 || (y == 2026 && m <= 2))` — the
options-expiry-week calendar is populated **only through Feb 2026**. It feeds the **live**
Core S6 opex legs (USDJPY long, AUDUSD short, NZDUSD short) via `m_cal.In(d)`
(`CoreSignal.mqh:966,984,987`). From **2026-02-21 onward `In(d)` returns false every day**,
so those three legs are **permanently flat for the entire 2026-07+ demo** — no error, no
NaN, no refuse. It runs on the live compute path (`CoreEngine.mqh:145`'s unbounded variant
is *not* used live). **This silently contaminates the OOS-generalization measurement the demo
exists to produce.** *This is the #1 finding.*

**Root cause — inherited, not introduced.** The bound is the **parent's study window**:
`v5_sleeves._nth_friday_week` (NSF5, read-only) ranges `"2019-12-01".."2026-02-01"`. The
MQL5 port reproduced it faithfully — which is exactly *why* it passed bit-exactness. The
defect is not the date; it is that a **bounded table** answers a **set-membership** test, so
past the last row it degrades to a confident `false` instead of an error.

**The fix — the horizon is removed, not re-dated.** `CCsOpexCal.In()` now *computes* the
3rd-Friday week from the queried date (the same rule `CoreEngine.mqh:145` already used), so
there is no last row to fall off. Pushing the table to 2040 was rejected: it preserves the
failure and merely re-dates it. The **2019-12 lower bound is kept exactly**, so in-window
behaviour is bit-identical. Applied to all three FMA3 copies (EA, `core_signal_reference.py`,
`mql5_coresignal_mirror.py`) so the mirror does not certify a stale model of the EA.

**Evidence:**
- **0 divergences** vs the shipped table over 2015-01-01..2026-02-28 (every day probed) —
  the certified window provably cannot move.
- Past the horizon: old table = **0** opex days through 2045; new rule = **1,190**.
- **0 errors** vs the real 3rd-Friday weeks 2020–2045, no cross-month spill.
- `2026-07-17` (**inside the demo window**): `old=false → new=true`. Those legs would have
  been dead for the whole demo.
- M-3 gate (mirror vs reference): 0 mismatches over 11,323 probed days.
- MQL5 compiles 0 errors / 0 warnings (isolated sandbox — the live tree was not touched
  because the warm-blob run was in flight).

**Still pending (owner):** recompile `FableBookNative.ex5` + run `CheckCoreSignal.mq5` +
re-run the bpure coresignal cert. **Deliberately deferred** — recompiling would have swapped
the binary under the running 15h warm-blob run. That run is unaffected by the fix (it ends
2025-12-31, before the horizon), so its output stays valid.

**The test that pinned the bug is now the test that prevents it.** `CheckCoreSignal.mq5:186`
asserted `cal.Last() == 20504` ("opex last 2026-02-20") — it *encoded the horizon as correct*.
Replaced with membership assertions including `In(20651)` (2026-07-17, in-demo). Likewise the
M-3 gate compared two *sets* that both carried the same bounded table, so it could not have
caught this; it now probes membership day-by-day to 2045.

### 1b. [DATA] The policy-rate tables are also expired — but they go *stale*, not *dead*
Found while fixing #1; `FORWARD_GENERATOR_SPEC.md:234` had already flagged it and the
go/no-go missed it. `CCsPolicy` (`CoreSignal.mqh:667`), `SwapEurq.mqh:336`,
`CarryBreakout.mqh:109` and `CoreEngine.mqh:135` all embed `engine/costs.POLICY_RATES`,
whose last rows are **USD 2025-12-11 (3.625)** and **JPY 2025-01-24 (0.50)**. Both are
already in the past.

**Severity is materially lower than #1, and the difference is the whole point.**
`policy_rate` is *"last table rate with date <= ts"* — a step function **held forward**. Past
the last row it returns the last known rate, so the model quietly assumes rates have not
moved since Dec 2025. That is **input drift, not structural death**: #1 removed three legs
outright; this biases the jpy_smart carry gate (`CoreEngine.mqh:313`:
`PolicyRate(USD) - PolicyRate(JPY)`, frozen at 3.125) and modelled swap/carry by however far
real policy has actually moved. The spec's phrase "swaps/carry freeze" is precise — *freeze*,
not flatten. Do **not** conflate the two.

**Not fixed here, deliberately: this needs real data, and inventing rates would be worse than
leaving them stale.** Correct values require actual central-bank decisions after 2025-12-11
(USD) / 2025-01-24 (JPY), which are not in this repo. **Owner input needed:** supply the
actual rate path, or accept measured carry drift as a known demo caveat. Note live swaps are
charged by the *broker*, so the demo's realised P&L is not affected — the exposure is the
carry **signal** and the record-side swap model used for reconciliation.

### 2. [MEASUREMENT] Three of the §3/§5 criteria are NOT measurable as-built
**→ FIXED IN SOURCE 2026-07-16 (PR #23), together with #3. Recompile pending (batched with #1).**

**The deeper finding: criterion #1 wasn't just unlogged — it was undefined.** "Live position
matches the EA's own computed target ≥99% of bars" cannot be scored, because the executor
has a **rebalance dead-band** (`InpRebalBand=0.25`, `BookExec.mqh:~276`): it *deliberately
does not retrade* while `‖want|-|held‖/|held| ≤ 0.25`. Held ≠ target is **designed
behaviour** (the band is in the certified model — it suppresses churn). Scored literally the
EA reads **~0% by design**; the danger was that someone would then "fix" it by loosening the
metric until it read 99%. §3 now specifies the executor's **invariant** instead — sign-correct
and within-band, deferred legs excluded but counted — and is flagged for owner sign-off,
because it changes a pre-committed criterion.

**So the EA logs raw inputs, not a verdict.** New per-symbol `rec=P` telemetry rows carry
`want` / `held` / `defer` per leg per hour (`g_fedWant/g_fedHeld/g_fedUnsized`, captured in
`FED_Reconcile`, which runs every M1 so the hour-boundary snapshot is fresh). Baking a
fidelity verdict into the binary would have frozen one definition; logging the inputs lets any
definition be computed — and recomputed — downstream.

**Also now in the hourly row:** `n_stops` (the REAL breaker count, `g_fedNStops` — was
deinit-only), `worst_eq` (`FED_WorstMarkEquity` — the §5 28% kill line is a *worst-mark* DD,
and hourly equity understates it), `day_anchor` (Guardian's own daily anchor, so the harness
and the breaker agree on what a "day" is rather than the harness guessing), and `warm` (#3).

`reconcile_demo.py` computes bar/leg fidelity, the FTMO 5%/10% envelope (`--initial`), and the
warm/cold verdict. It stays **backward-compatible**: run against the in-flight run's 18-column
telemetry it reports "predates the 2026-07 build" per section rather than crashing or faking.

### 2-original. [MEASUREMENT] The as-built gaps (retained for the record)
- **Position fidelity ≥99%/bar is un-measurable.** The telemetry `sc_mm`
  (`BookOrchestrator.mqh:1259`, `m_live_sc_mismatch`) is the **SC-sleeve signal self-check**,
  NOT held-position-vs-computed-target. `reconcile_demo.py`/`demo_watch.py` mislabelled it as
  "fidelity" (**fixed in this PR** — relabelled `sc_selfcheck`). True fidelity needs per-bar
  held-vs-target logging, which is **not written** (only in the event-triggered decision CSV).
- **Breaker-fires is mislabelled.** Telemetry `fires` (`CoreLiveDrive.mqh:205`, `m_fires`) =
  CoreTrigger **segment** count, NOT the FTMO breaker. The real breaker count is
  `g_fedNStops` (`Guardian.mqh:102`), printed **only at deinit**. (Harness relabelled
  `core_segments` in this PR; the true breaker count comes from the deinit log.)
- **FTMO 5%-daily / 10%-max-loss envelope is not computed** — the harness does a rolling-peak
  DD only; no daily anchor, no initial-balance anchor, no breach counting.
- *(min-ML is now logged — PR #17 `margin_level` — and read correctly.)*

### 3. [MONITOR] Silent cold-start has no automated alarm
**→ FIXED IN SOURCE 2026-07-16 (PR #23).** The hourly row now carries `warm` (`g_warm`), so
the cold-start is machine-detectable rather than inferable from two Experts-log lines.
`reconcile_demo.py` reports it explicitly ("cold for the WHOLE span — silent cold start" /
"cold until <ts>"). Recompile pending (batched with #1).
Cold-start (blob absent) is surfaced by **two one-time Experts-log lines** only; the telemetry
`trading` flag stays **1** even when nothing is sizing (misleading), and there is **no
warm/cold column**. `demo_watch.py` (PR #19, **needs merge**) scans the Journal for
`COLD START` — but the robust fix is a **warm/cold + synced flag in the hourly telemetry**.
A silent cold-start after an unattended VPS reboot could burn weeks. **Merge #19 and add the
flag before enabling.**

## MUST-MONITOR in the Week-0 shakedown
### 4. [PLUMBING] Live weekend/holiday clock-stall
The not-yet-born-symbol fix (RECON-8j/8k) was applied **tester-only**. On the **live** path,
a closed symbol whose `CopyRates` returns `n<0` **freezes the whole book clock**
(`FableBookNative.mq5:321-324`, `g_histWaits++; return false`) — symptom is stale telemetry
`ts` while the wall clock moves, with **no alert**. Whether this broker returns `n=0` (safe)
or `n<0` (stall) for closed FX/metal/index symbols is **unverified**. Prove it across a full
weekend + a holiday in Week 0; add a heartbeat print of `g_histWaits` + compute-vs-wall lag.

## SHOULD-FIX
- **§6B doc:** tell the owner to **provision each demo account's leverage** (IC 1:30 / FTMO
  1:30) and balance — leverage governs real broker margin/stop-out and is the load-bearing
  omission. (`InpInitial` is functionally inert — the book sizes off `ACCOUNT_BALANCE`; leverage is not.)
- **worst-mark DD** logged is hourly-equity (understates the 28% flag line). `FED_WorstMarkEquity`
  (`Guardian.mqh:35`) already computes the true intra-bar worst-mark for the breaker — **log it
  hourly**, or ingest the tester report's tick-DD in the harness.
- **Restart pair-coherence** (`FableBookNative.mq5:704-708`) refuses only at >24h drive-vs-book
  skew; a 1–23h torn pair passes with a silent small `a_h` offset. Consider a single combined
  blob or tightening toward equality.

---

## Bottom line
The **book and dials are sound**; the gaps are **live-operation correctness + measurability**,
not alpha. Highest-leverage order: **(1) OPEX calendar fix**, **(2) merge #19 + the harness
relabels here + a warm/cold telemetry flag**, then run the **Week-0 disabled shakedown** to
settle the clock-stall question — *then* enable. Until #1 is fixed, the demo's OOS-fidelity
result is contaminated by three dead legs.
