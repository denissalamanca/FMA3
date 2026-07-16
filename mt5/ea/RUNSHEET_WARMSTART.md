# RUNSHEET — warm-start the demo (the one real prerequisite)

*Prepared 2026-07-16 (autonomous). The warm-start bootstraps the live demo so it
trades from **day 1** instead of holding ~0 positions for ~1 year while indicators
cold-warm. This is the load-bearing prerequisite in
[`docs/v3.0/DEMO_FORWARD_PLAN.md`](../../docs/v3.0/DEMO_FORWARD_PLAN.md) §6A.*

---

## The mechanism (why it's structured this way)

`FableBookNative` OnInit either **cold-starts** (computes from *now*, catch-up gate
holds sizing ~250 weekdays ≈ ~1 yr — a demo-killer) or **warm-resumes** from a saved
state. Warm-resume needs **two coherent files** in `Common\Files`:

| File | Content | Producer |
|---|---|---|
| `FMA3_native_state.json` | the book state — 8 sleeve steppers, `b`=SatEquityNative, `a`=CoreSim, glue, continuity anchors | EA `g_bs.Save` (Python mirror bit-equal) |
| `FMA3_native_state.json.coredrive` | the CoreLiveDrive sidecar (live `a_h` + `f_core` per-leg accounts) | **EA `g_bsDrive.Save` only** |

On resume the EA cross-checks the two for coherence (drive hour vs book hour) and
**refuses to trade** on any mismatch — so **both files must come from the same run.**

## What's already proven (autonomous, 2026-07-16)

- The **2025-12-31 book-state blob exists** and its **save → load → resume roundtrip
  is bit-exact**: `FMA3_book_state_endBASE.json` == `endRESUME.json` (7.84 MB
  identical body; `b`-balance **434,132.989**, CoreSim seed **532,229.843**,
  `a_h/b_h` = **53.098 / 44.916** all match). The hard, path-dependent half is done.
- The `.coredrive` sidecar is **EA-only** (no Python producer, and building an
  unverified one is worse than letting the EA emit it). So the complete,
  coherent pair is produced by **one EA run** — Step 1 below.

---

## STEP 1 — produce the warm blob (owner-run, ~fast)

A **1-minute-OHLC** tester run is enough — the book state is M1-close-deterministic
(real ticks are irrelevant to the state), so this is fast and needs no disk headroom.

| Field | Value |
|---|---|
| Expert | `FableBookNative` (load preset `FABLE_IC_REALTICK_P1`) |
| Symbol · Period | BTCUSD · M1 |
| **Modelling** | **1 minute OHLC** (fast — *not* real ticks here) |
| Date | `2020.01.01 → 2025.12.31` (full path from t0 is required — the state is path-dependent) |
| Deposit · Leverage | 10000 EUR · 1:30 |
| **Inputs to change** | **`InpSaveInTester = true`** · `InpSaveState = true` · `InpStateFile = FMA3_native_state.json` (rest per preset) |

**Result:** the EA writes `FMA3_native_state.json` + `FMA3_native_state.json.coredrive`
to `Common\Files`, holding the **2025-12-31** state.
**Verify:** both files exist; the Journal shows state-save lines and **no refuse-latch**.
**Send me both files** — I'll confirm `FMA3_native_state.json` matches the proven
`endBASE.json` **bit-for-bit** (independent check that the blob is the golden state).

> Note: `InpSaveInTester=true` saves each completed hour (overwriting), so the run
> is slower than a normal pass — let it finish; the final file is the 2025-12-31 state.

## STEP 2 — the live-resume test (owner-run, ~30 min — the actual certification)

Attach the EA to a **demo chart, trade-DISABLED**, seeded with the blob:

| Field | Value |
|---|---|
| Chart | a **demo** BTCUSD chart (IC demo account) |
| Inputs | `InpAllowLiveTrading = false` · `InpStateFile = FMA3_native_state.json` · `InpSaveState = true` (rest per IC preset) |
| Pre-req | `FMA3_native_state.json` + `.coredrive` (from Step 1) present in `Common\Files` |

**Watch the Experts/Journal log for — PASS if:**
1. `FMA3 NATIVE WARM START: blob validated (j=… at hour …); resuming from 2025-12-31 …`
   — **not** `COLD START`.
2. **No** `REFUSE-TO-TRADE` latch (coherence/continuity all clear).
3. Within minutes it **backfills 2026-01 → present** and holds **real positions**
   (non-zero book_frac) — i.e. it is *warm*, not ramping from empty.
4. `a_h / b_h` continue from ~**53.1 / 44.9** (the boundary values), not from 1.0.

**FAIL signatures + what they mean:** `COLD START` → the blob wasn't found/loaded;
`A/B-ANCHOR MISMATCH` or `j-splice` refuse → the two files aren't coherent (re-do
Step 1 as one run); `state incoherence: core-drive hour vs book hour` → same.

---

## What this certifies + what's next
- **PASS** = the EA warm-resumes and trades from day 1 → the demo can start (the
  1-week trade-disabled shakedown, then enable). This clears the **§6A blocker.**
- Then the small items: margin/ML in telemetry, the reconciliation harness, the VPS
  log-archival/deal-export.
- **Honest flag (WARMSTART_DESIGN §7.4):** this seeds the state at the frozen horizon
  (2025-12-31) and the EA computes *live* forward from there — there is **no golden to
  certify against past 2025-12-31**, which is fine (the demo *is* the forward test),
  but it means the warm-resume's forward path is trusted, not gate-proven. The Step-2
  live-resume test is what validates it in practice.
