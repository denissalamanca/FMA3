# MORNING BRIEF — 2026-07-15

For the owner, waking up. Overnight run: **the live-computing EA got built, compiled, installed,
and passed its software gate.** No marketing below; where a gate hasn't run, it says STAGED and
leads with it.

---

## 1. TL;DR

**FableBookNative.mq5 is real now.** It computes `f_core / f_sat / a / b / book_frac[33]` LIVE
each bar from the terminal's own synchronized multi-symbol feed — no frozen CSV replay. It
compiles **0 errors / 0 warnings**, the `.ex5` is installed, and the whole live-compute chain was
mirror-tested against the golden book_frac curve.

**The mirror gate PASSED.** The live chain reproduces the R1 curve at `max|diff| = 5.06e-13` —
which is **not** a live error, it is the golden CSV's own 12-decimal-place rounding, the exact
same residual the frozen replay carried at RECON-8e. The one genuinely-new numeric piece — the
live Core target stream — measured **bit-exact 0.0**. So the live-compute path adds no error of
its own; it lands back on the R1 gate to the digit.

**State of the EA:** software-complete, mirror-gated, **safe on a live chart today (zero orders
by default)**, safe in the tester. **NOT cleared for live trading** — that's still your call, and
it's gated on the terminal runs below. Zero blocking findings across all three code reviews; one
non-blocking FTMO breaker-cadence note.

**Your move today:** run the terminal run-sheet in §3. It's ~6 runs; the last one (the Strategy
Tester) is the position-fidelity + R2 gate.

---

## 2. THE FULL HONEST SCOREBOARD

| # | thing | status | the number |
|---|-------|--------|-----------|
| 1 | S2 live Core signal + trigger (G-S0..G-S4) | MEASURED bit-zero | max&#124;diff&#124; = 0.0; 20,950,676 tgt rows, 31/31 triggers, eqc 532229.8433634703 bit-equal |
| 2 | Feed assembler / instruments | MEASURED | 37 symbols recon_ok; 24/24 quarters + H1 + 8 daily-mids all bit_exact; overall_pass |
| 3 | **EA mirror gate (live chain vs golden)** | **MEASURED PASS** | **max&#124;diff&#124; = 5.06e-13 (= CSV 12dp floor); seam bit-exact 0.0; 0 cells > 1e-12; 805,585 rows** |
| 4 | Warm-blob resume (v2 CBookState + CoreSignal) | MEASURED PASS | G1 tail 14 rows bitwise identical; 3 negative controls all diverge; anchors 0.0 |
| 5 | Swap/eurq generator | python PASS / MQL5 deferred | tables match, 2618 DST days, positive controls PASS; `CheckSwapEurq.mq5` NOT compiled |
| 6 | Code reviews (3 lenses) | **0 blocking** | SAFETY clean; SEAM clean (1 non-blocking FTMO note); FEED+WARM clean |
| 7 | EA compile + install | MEASURED | 0 errors / 0 warnings; `.ex5` installed |
| 8 | G-S5 in-terminal (compiled CoreSignal self-diff) | **STAGED** | `TestCoreSignal.mq5` 0/0 — NOT run |
| 9 | Book-state / warm-blob in-terminal battery | **STAGED** | `CheckBookState` / `CheckCoreSignalState` built — NOT run |
| 10 | Position-fidelity + R2 (Strategy Tester) | **STAGED** | not run |

**Read the mirror number right:** the argmax cell is USTEC on 2022-01-10 — `actual
0.51429446766950604` vs `golden 0.514294467669`. The golden is stored truncated to 12 dp; that's
the whole 5.06e-13. The live Core seam underneath it is 0.0 on all 9 legs (2.1M-2.9M bars each),
and the live final equity matches the frozen pin bit-for-bit. This is the same residual RECON-8e
booked. Nothing regressed.

---

## 3. THE CONSOLIDATED TERMINAL RUN-SHEET — run these in order

All scripts are Wine-compiled 0/0 and installed. Do NOT launch anything that sends orders — every
run below is a check/test, and the EA sends zero orders unless you explicitly flip
`InpAllowLiveTrading`. Each run -> a dated `FMA3-RECON-9` ledger entry.

**Batch A — Core signal (G-S5):**
1. **`TestCoreSignal.mq5`** — replays the frozen 2020-2025 bars through the *compiled*
   `CoreSignal.mqh`, self-diffs vs the frozen `tgt` column.
   *Expected:* bit-zero (or ULP-band only, flip-invisible — targets are integer-lot-floored).
   Any lot-decision flip is a real failure — lead with it if it happens.
2. **`CheckCoreSignal.mq5`** — structural smoke: opex/policy tables + `CsDaysFromCivil` + a
   240-day synthetic series vs the embedded python golden.
   *Expected:* all tables equal, synthetic block matches golden, 0 mismatches.

**Batch B — warm-blob / state (T1-T7):**
3. **`CheckBookState.mq5`** — the in-terminal split/continue + 5-latch refuse battery (torn-write
   eof, fnv64 checksum, a-anchor re-base, j-splice discontinuity).
   *Expected:* T1-T7 pass; tail bitwise identical after restore; all 5 latches fire on their
   negative controls. (Python split gate already PASSED; this is the missing binary certification.)
4. **`CheckCoreSignalState.mq5`** — the v2 warm-blob completeness for the folded live Core signal
   + trigger cursor + XAU breach flags.
   *Expected:* restore->resume tail bitwise identical; the 3 drop-controls diverge.

**Batch C — feed + swap:**
5. **`CheckFeedAssembler.mq5`** — assembler reconstruction in-terminal (union grid + has-bar +
   six-field b rows vs the golden bundles).
   *Expected:* bit_exact per quarter, matching the python gate (24/24 + H1 + daily-mids).
6. **`CheckSwapEurq.mq5`** — **only if you decide to ratify the live swap/eurq generator.**
   It is currently NOT compiled (deferred, S2_PREP §194). Skip unless you're moving swap/eurq
   into deploy this pass.
   *Expected (if run):* tables match + rollover-DST reproduced, matching `swap_eurq_gate.json`.

**Batch D — the big one:**
7. **`FableBookNative` Strategy-Tester run** — the **position-fidelity gate + R2**. Attach to a
   BTCUSD M1 chart in the tester (it auto-detects the tester and auto-enables trading there).
   - *Grade against the ratified R2 band, NOT R1 bit-zero:* **DeltaCAGR <= +/-1.0pp /
     DeltaMaxDD_worst <= +/-0.5pp / DeltaBreach <= +/-0.5pp.**
   - *This is a RECENT-WINDOW run* — the tester feed only reaches back as far as the broker's M1
     history, so it does NOT cover the full 2020-2025 golden window. Position fidelity is the
     primary read; R2 CAGR/DD is graded on the window you actually get.
   - Live-feed bars != the frozen IC bars by construction, so exact match is not expected and not
     the bar — the band is.

---

## 4. BLOCKING FINDINGS — and what they mean

**None.** All three code-review lenses returned `blocking: []`.

- **LENS 1 (SAFETY):** clean. Zero-order default, tester auto-detect, refuse latch, catch-up gate
  all present and correct.
- **LENS 2 (SEAM FIDELITY + position gate):** clean for the IC gate — the only numeric change is
  the `g_fedTgt` source; everything downstream is byte-identical by construction (shared includes,
  one shared `FED_Reconcile`, `InpScale` applied once at `BookExec.mqh:211`). **One NON-blocking
  finding:** the FTMO daily-breaker (Guardian) cadence can differ under live minute pacing —
  irrelevant to IC, carried to the FTMO-dial work.
- **LENS 3 (feed assembler + warm-blob):** clean; both new pieces carry their own passing gate.

---

## 5. KNOWN RESIDUAL RISK (so nothing surprises you)

1. **Staged != run.** The compiled-binary bit-zero rests on the software-fma *emulation*. The
   terminal can add ULP-band noise the mirror lacks (seen at RECON-8b..8e). CoreSignal targets are
   integer-lot-floored so that noise should be flip-invisible — but that's a prediction until
   `TestCoreSignal` (G-S5) actually runs. **This is the single most important gap.**
2. **Two trigger sub-mechanisms are not in-sample-binding:** the k=2.5 harvest arm came within 3%
   of firing and never did (0/31); the 999-month probe collapsed to `act<hi` with no in-sample
   constraint. Contained by live telemetry + the refuse latch, not proven forward.
3. **fma-contraction (G-S5):** whether the compiled roll_var contracts exactly as the emulation
   predicts is precisely what G-S5 settles.
4. **R2 feed residual is irreducible:** the reference pipeline has lookahead (`ffill().bfill()`,
   full-sample median commission) a forward stepper can't reproduce; the band bounds it, doesn't
   close it.

---

## 6. WHAT REMAINS AFTER TOMORROW

- **Terminal certification** — the §3 run-sheet (G-S5, state batteries, feed, and the tester
  position/R2 run) -> recorded as `FMA3-RECON-9`.
- **Crisis certification** — real-tick COVID/crisis window per the standing MT5-validation
  protocol (the record engine is blind in COVID cold-start; trust real-tick here).
- **FTMO dial** — resolve the breaker-cadence divergence and re-validate the FTMO scale/breaker
  (MEMORY: shipped FTMO dial is unsafe cold; needs warm re-validation + a cut to ~s0.30-0.35).
- **Swap/eurq ratification** — decide whether to compile/run `CheckSwapEurq.mq5` and fold the live
  generator into deploy.
- **RECON-9** — the full 6-gate reconciliation ledger entry.
- **Deploy** — **owner decision only.** The EA will not send a live order until you flip
  `InpAllowLiveTrading` on a live chart, and it should not be flipped until the above clears.

---

*Overnight work by Opus. Every number here is measured against a cited artifact or labelled
STAGED. Detail: `model/v3/S3_STATUS.md`.*
