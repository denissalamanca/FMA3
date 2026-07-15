# S3_STATUS — FableBookNative EA: live-compute chain built, compiled, mirror-gated — 2026-07-15

S3 assembles the whole live-computing EA and closes the software gate on it: **the live-compute
chain reproduces the R1 book_frac curve at the identical 5.06e-13 residual the frozen replay
already carried (RECON-8e)**, with the one genuinely-new numeric seam — the live Core target
stream — measuring **bit-exact 0.0**. Every number below is `[MEASURED]` (gate run this pass,
artifact cited) or `[STAGED]` (compiled 0/0, terminal run pending). No claim here is graded PASS
on the strength of a staged run. If a gate has not run, it says so.

---

## 0. HEADLINE — THE MIRROR GATE NUMBER (front and center, honest)

**`ea_mirror.py` (LIVE CCoreSignal path) vs golden `FMA3_fed_frac_v3.csv` (sha `d00b614b…`):**

| metric | value |
|--------|-------|
| **max &#124;diff&#124; over the whole 33-slot book_frac curve** | **5.060396546241464e-13** |
| cells over the 1e-12 R1 gate | **0** |
| cells over the 5e-13 quantization bound | 38 (of 805,183 data rows) |
| rows compared (incl. 402 sentinels) | 805,585 / 805,585 |
| structural_ok | true |
| **first divergence (book stream / coresignal seam)** | **none / none** |
| **VERDICT** | **PASS** |

**What that number IS — and is not.** The 5.06e-13 is **not** a live-compute divergence. It is
the 12-decimal-place quantization of the golden CSV: the argmax cell is USTEC @ 2022-01-10,
`actual 0.51429446766950604` vs `golden 0.514294467669` (the golden is stored truncated to 12
dp). This is the **same residual, to the digit, that the frozen replay carried at RECON-8e**
(book_frac 5.0604e-13). The live-compute chain therefore reproduces the R1 gate **exactly** — it
adds no error of its own. The proof of that is the seam sub-gate:

- **CoreSignal live-target seam: `max|diff| = 0.0`, bit_equal on all 9 legs (10 slots incl. both
  USDJPY), 0 discrete flips, 0 cells > 1e-12.** Per-leg bit-equal across 2.1M–2.9M leg-bars each.
- **Live final chained eqc = 532229.8433634703 — bit-equal to the frozen pin.**

So the ONLY numeric-path change in the EA (the `g_fedTgt` source: frozen `tgt` column → live
`CCoreSignal`) is bit-exact where it enters, and the whole downstream book collapses back onto
the R1 curve at the pre-existing CSV-quantization floor. `n_over_quant_bound=38` reflects the
golden's 12-dp storage, not the compute.

**Mirror methodology (so the number can be trusted).** `ea_mirror.py`
(`research/bpure/ea/ea_mirror.py`) is the **statement mirror of FableBookNative.mq5's LIVE-mode
OnInit/OnTimer loop** — the live CCoreSignal path, NOT the frozen-target S1 path. It reuses the
S1-proven book machinery (`book_orchestrator_sim`) by import+monkeypatch, replacing **only** the
core phase. Any divergence therefore isolates to the live-target seam — and that seam came out
0.0. Artifacts: `research/bpure/ea/ea_mirror_parity.json`, `.../out/run.log`, runtime 272.1 s.

---

## 1. EA BUILD + COMPILE + INSTALL — `[MEASURED]`

**`mt5/ea/FableBookNative.mq5` — compiles `0 errors, 0 warnings` (10710 ms), `.ex5` installed.**

- Compile log `mt5/ea/FableBookNative.log`: `Result: 0 errors, 0 warnings`.
- `.ex5` present at both `drive_c/mql5link/Experts/FableBookNative.ex5` (460 KB, built
  2026-07-15 02:16) and `MetaTrader 5/MQL5/Experts/FableBookNative.ex5` (installed).

It assembles the full live-compute chain onto the **verbatim RECON-4 execution half**:

- **feed** — `CFeedAssembler` (S0-proven multi-symbol M1 data path), minute-merged `CopyRates`
  poll feeding both the daily-mid derivation and the union grid.
- **signal** — 8 Sat sleeves + Ensemble → `f_sat[31]` (RECON-8b) and `CCoreSignal` live targets
  (RECON-8g bit-zero) + `CCoreTrigger` causal segment detector (31/31 measured).
- **equity** — `CBookOrchestrator` M1 clock: `b` = `SatEquityNative` on held prior-hour `f_sat`
  (RECON-8d bitwise); `a` = live `CCoreLiveDrive` (CoreSim per-leg accounts, **hold-at-legcap
  live combine per the owner-ratified FABLE REVISION v2 item 2** — this is the S2_STATUS §6.1
  "remaining execution-seam build", now implemented in LIVE mode).
- **blend** — `BookBlend` on asof `a_h/b_h` → `book_frac[33]` (RECON-8c); whole chain R1-closed
  at 5.06e-13 (this document).
- **exec** — `g_fedTgt[33]` → `FED_Reconcile` — byte-identical to the RECON-4-proven FableBook
  execution half (margin cap, rebalance band, volume-limit clamp, split send, FTMO Guardian).

**One model, two dials.** `InpScale` (IC 1.6 / FTMO 0.7 + breaker) is the ONLY IC↔FTMO
difference, applied exactly once, uniformly, at `BookExec.mqh:211` (`g = g_fedTgt[k]*InpScale`)
— identical in both EAs.

---

## 2. SAFETY DEFAULTS — verified in source `[MEASURED]`

**A live chart with default inputs computes and logs everything but sends ZERO orders.** Verified
in `FableBookNative.mq5`:

- `input bool InpAllowLiveTrading = false;` (line 65) — master switch defaults OFF.
- `g_fedLive = !MQLInfoInteger(MQL_TESTER); g_canTrade = (!g_fedLive) || InpAllowLiveTrading;`
  (593–594). In the **Strategy Tester** `g_canTrade` is true automatically (so the
  position-fidelity gate runs unmodified); on a **live chart** it is true ONLY if the input is
  explicitly set true. Default live chart → `FED_Reconcile` never called; on init it prints
  "InpAllowLiveTrading=false … COMPUTE+LOG ONLY, zero OrderSend."
- **REFUSE-TO-TRADE latch** (`g_refuse`, 157–183, 540–546): any warm-blob validation failure
  (torn write / fnv64 checksum / a-anchor / j-splice), feed digits drift, or compute
  drive-contract violation latches the EA out of sizing and prints the reason hourly. It never
  trades through a doubted state (a re-based a/b would pass every self-check while silently
  mis-weighting every trade — the latch is the guard).
- **Catch-up gate** (553+): targets computed from pre-wall history are warmup only; sizing is
  held until the compute clock catches up with the wall clock.
- Feed init `g_fa.Init(true)` **refuses on digits drift** (642).

---

## 3. THE THREE REVIEW VERDICTS — blocking findings UNSOFTENED

### LENS 1 — SAFETY — `sound: true`, **blocking: []**
No safety blocker. The zero-order default, tester auto-detect, refuse latch, and catch-up gate
are present and correct as described in §2.

### LENS 2 — SEAM FIDELITY + position gate — `sound: true`, **blocking: []**
The seam claim holds: **the ONLY numeric-path change is the `g_fedTgt` source.** Everything
downstream of `g_fedTgt` (FED_Reconcile sizing, netting, margin cap, volume-limit clamp,
rebalance band, split send) is **byte-identical by construction** — both EAs `#include` the SAME
`Book/BookConvert`, `BookReplay`, `BookExec`, `Guardian` files; `FED_Reconcile()` is one shared
no-arg function; `g_fedTgt` is one shared 33-slot global (`BookReplay.mqh`). `InpScale` is
applied exactly once, uniformly, at `BookExec.mqh:211` in BOTH paths. **No blocker for the IC
position-fidelity gate.**
- **Non-blocking finding (FTMO only): one breaker-cadence divergence flagged.** The FTMO daily
  circuit-breaker (Guardian) cadence can differ from the replay under live minute pacing. It does
  not affect the IC gate and is not a blocker; it is flagged for the FTMO-dial validation (which
  is a separate downstream run, not R1/R2 position fidelity).

### LENS 3 — Feed assembler + warm-blob correctness (the two genuinely-new pieces) — `sound: true`
Both new pieces carry their own passing measured gate (§4.3, §4.4). No blocker raised.

**Net: zero blocking findings across all three lenses.** One non-blocking FTMO breaker-cadence
item is carried to the FTMO-dial work.

---

## 4. THE HONEST SCOREBOARD

### 4.1 S2 live Core signal + trigger — `[MEASURED]` bit-zero
G-S0..G-S4 all PASS at **bit-zero** (max|diff| = 0.0, literally — not flip-absorbed, not ≤1e-12):
kernels 27/27 (G-S0); tgt identity 9/9 legs / 20,950,676 rows, 0 flips (G-S1); account passthrough
32/32 segments, net lots 8/8 symbols, final eqc 532229.8433634703 bit-equal (G-S2); trigger
31/31 act+decided+t0, 0 harvest fires, 0 live-vs-harness date diffs (G-S3); f_core 8/8 columns
bit-equal (G-S4). Software-fma MQL5 twin (`coresignal_mirror.json`) confirms the MQL5 arithmetic
shape (78,088 fma calls, 0 mismatches vs hardware). Source: `coresignal_gates.json`,
`trigger_gates.json`. **G-S5 (compiled-binary self-diff in terminal) is STAGED.**

### 4.2 Instruments / feed data path — `[MEASURED]`
`feed_assembler_gate.json` — `overall_pass: true`, runtime 129.6 s:
- **37 symbols** reconstructed, all `recon_ok: true` (ask = bid + spread_points·point, digits
  verified per symbol).
- **24/24 quarters bit_exact** (`value_cells_mismatched = 0`, `max_abs_diff = 0.0`, union-grid
  and has-bar OK each).
- **H1 stream bit_exact** (49,379 rows, 0 mismatch).
- **8/8 daily-mid series bit_exact** (XAUUSD/USTEC/USDJPY/ETHUSD/EURGBP-pre20/AUDUSD/NZDUSD/
  BTCUSD; `all_bit_exact: true`), incl. the EURGBP pre-2020 EG variant.
- **Streaming replay bit_exact** (20,160 rows, 0 m1/h1/daily-mid cells mismatched).
- `CheckFeedAssembler.mq5` compiles **0/0** (1247 ms). Terminal run STAGED.

### 4.3 EA mirror gate — `[MEASURED]` — see §0
`max|diff| = 5.06e-13` (CSV-quantization floor, = RECON-8e), 0 over 1e-12, seam bit-exact 0.0,
live eqc bit-equal. VERDICT PASS. `ea_mirror_parity.json`.

### 4.4 Warm-blob (CoreSignal + trigger folded into v2 CBookState) — `[MEASURED]`
`coresignal_ws_gate.json` — **verdict PASS**, save→restore→resume gate BITWISE:
- **G1 positive**: 14 tail rows after restore, `targets_bitwise_identical: true`,
  `trigger_telemetry_bitwise_identical: true`, `first_divergent_row: null`.
- **3 negative controls all diverge (as required)**: G2 drop-b50-flag → diverges at row 0; G3
  drop-vol-ring → diverges at row 0; G4 drop-trigger-cursor → diverges. Each `pass: true`
  (divergence is the expected control result).
- `breach_latched_before_boundary: true` — the XAU Donchian last-breach flags (formally
  unbounded, ffill-from-2020) are carried explicitly, so the resume does not silently mis-warm.

`warmstart_cert.json` (RECON-9-WS certifier, forward mode, 960 h): envelope fnv64+eof OK,
continuity latch OK (j=5.9356), boundary binding OK, manifest 0 errors, anchors E1 core-seed pin
532229.8433634703 (0.0), E2 fcore cursor 18675, E3 a_h 5.908491316914911 (0.0), E4 b_h
5.998775400712066 (0.0). In-sample pre-warm guard ARMED (`InSampleWarmStartRefused`). v1 path
byte-unchanged — RECON-8e/8f reproducible.
- `CheckCoreSignalState.mq5` / `CheckBookState.mq5` in-terminal batteries are **STAGED** (built;
  the T1–T7 + 5-latch MQL5 battery has not executed in the terminal — the python gate is the
  measured evidence to date).

### 4.5 Swap/eurq live generator — `[MEASURED]` python, MQL5 DEFERRED
`swap_eurq_gate.json` PASSES: tables (policy_rates/markups/instruments/swap_pct_mult) all match,
2618 rollover-DST days checked, positive controls PASS (b_h 92,155 bars, coresim 599,565 rows).
**`CheckSwapEurq.mq5` is NOT compiled/run** — owner-DEFERRED (S2_PREP §194); the S3 gates run on
pre-baked exported arrays. Live-deploy prerequisite, tracked separately.

---

## 5. EA DEPLOYABLE STATE

**State: SOFTWARE-COMPLETE and mirror-gated; terminal-certification PENDING; NOT cleared for
live orders.**

- The EA is **built, compiled 0/0, installed**, and its live-compute chain is **mirror-proven to
  reproduce the R1 book_frac curve at the RECON-8e floor with a bit-exact live-target seam**.
- It is **safe to attach to a live chart today** with default inputs — it will compute and log
  and send **zero** orders. It is **safe to run in the Strategy Tester** (the position-fidelity /
  R2 gate).
- It is **NOT cleared for live trading.** Deploy remains an **owner** decision, gated on: the
  staged terminal certifications below passing, the FTMO dial + breaker-cadence resolution, the
  swap/eurq generator ratification, crisis real-tick, and a recorded RECON-9.

---

## 6. WHAT IS STAGED (compiled 0/0, terminal run PENDING) — not graded as done

| gate | script | proves | status |
|------|--------|--------|--------|
| G-S5 | `TestCoreSignal.mq5` (0/0) | compiled `CoreSignal.mqh` tgt vs frozen 20.95M-row golden | STAGED |
| G-S5 smoke | `CheckCoreSignal.mq5` (0/0) | opex/policy tables + 240-day synthetic vs python golden | STAGED |
| T1–T7 | `CheckBookState.mq5` (built) | save/continue + 5 refuse latches in terminal | STAGED |
| warm v2 | `CheckCoreSignalState.mq5` (built) | folded CoreSignal/trigger warm-blob in terminal | STAGED |
| feed | `CheckFeedAssembler.mq5` (0/0) | assembler reconstruction in terminal | STAGED |
| position/R2 | `FableBookNative` Strategy-Tester run | position fidelity + R2 band (recent window) | STAGED |
| DEFERRED | `CheckSwapEurq.mq5` (not compiled) | live swap/eurq — gated behind owner ratification | DEFERRED |

**R2 acceptance frame (owner-ratified, DESIGN §2.2):** ΔCAGR ≤ ±1.0pp / ΔMaxDD_worst ≤ ±0.5pp /
ΔBreach ≤ ±0.5pp — the tester run is graded against this band (NOT the R1 bit-zero gate), and it
is a **recent-window** run (live-feed history bound), not the full 2020–2025 golden window.

---

## 7. KNOWN RESIDUAL RISK (measured, not hand-waved)

1. **Staged ≠ run.** The compiled-binary bit-zero claim rests on the software-fma emulation; prior
   components (RECON-8b..8e) showed the terminal can add ULP-band noise the mirror lacks.
   CoreSignal targets are integer-lot-floored so ULP noise is expected flip-invisible — a
   prediction until `TestCoreSignal` runs (G-S5).
2. **Two trigger sub-mechanisms are not in-sample-binding.** The k=2.5 harvest arm came within 3%
   of firing (never fired, 0/31); the 999-month probe collapsed to `act<hi` with no in-sample
   constraint. Both are contained by live telemetry + the refuse latch, not proven forward.
3. **fma-contraction (G-S5) question.** Whether the compiled CoreSignal's roll_var contracts
   exactly as the emulation predicts is the open item G-S5 answers.
4. **R2 feed residual is irreducible.** Live/tester bars ≠ the frozen IC bars the golden was built
   on (the reference pipeline itself contains `ffill().bfill()` + full-sample median commission a
   forward stepper cannot reproduce). The ratified band bounds it; it does not close it.
5. **FTMO breaker-cadence** (LENS 2 non-blocking) — resolve in the FTMO-dial work.

---

*Engine of record: Python 1-minute worst-mark (MEMORY campaign-charter). This document records
MEASURED gate numbers and STAGED terminal dependencies only.*
