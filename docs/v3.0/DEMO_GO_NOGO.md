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
`CoreSignal.mqh:630` (`CCsOpexCal`): `while(y < 2026 || (y == 2026 && m <= 2))` — the
options-expiry-week calendar is populated **only through Feb 2026**. It feeds the **live**
Core S6 opex legs (USDJPY long, AUDUSD short, NZDUSD short) via `m_cal.In(d)`
(`CoreSignal.mqh:966,984,987`). From **2026-02-21 onward `In(d)` returns false every day**,
so those three legs are **permanently flat for the entire 2026-07+ demo** — no error, no
NaN, no refuse. It runs on the live compute path (`CoreEngine.mqh:145`'s unbounded variant
is *not* used live). **This silently contaminates the OOS-generalization measurement the demo
exists to produce.** Fix: extend/**dynamically generate** the calendar past the horizon,
recompile, re-cert. *This is the #1 finding.*

### 2. [MEASUREMENT] Three of the §3/§5 criteria are NOT measurable as-built
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
  1:100) and balance — leverage governs real broker margin/stop-out and is the load-bearing
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
