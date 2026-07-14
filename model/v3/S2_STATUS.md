# S2_STATUS — live Core leg-target source (CCoreSignal) + live band-trigger detector — 2026-07-15

Track A of S2 built and gated. This is the status of the **live Core** path: the per-leg
per-minute target generator (`CCoreSignal`) that replaces the frozen `tgt` column, and the
streaming band-trigger detector that replaces the 32 frozen segment boundaries. Every number
below is **[MEASURED]** (gate run this pass, artifact cited) or **[STAGED]** (compiled, not
yet executed in the terminal). No hand-tuning to the golden; the gates are self-diffs against
the frozen references the S0/S1 chain already proved.

Normative source (owner-ratified, S2_PREP §184): NSF5 python `book('BTC_REP','USTEC')` at
**R=8.0 pure** (preset `InpRisk=8.96` embeds w·s and is NEVER copied), pandas-faithful kernels.
CoreEngine.mqh untouched, never included — G1 undisturbed.

Artifacts:
- python harness: `research/bpure/coresignal/core_signal_reference.py`,
  `trigger_detector.py`, `mql5_coresignal_mirror.py`, `gen_coresignal_check_golden.py`
- gate results: `research/bpure/coresignal/coresignal_gates.json` (G-S1/G-S2/G-S4),
  `trigger_gates.json` (G-S3 + live differential), `coresignal_mirror.json` (MQL5 twin)
- MQL5: `mt5/ea/Include/Core/CoreSignal.mqh` (84 KB), scripts
  `mt5/ea/scripts/checks/TestCoreSignal.mq5` + `CheckCoreSignal.mq5` (both compile 0/0)
- feed (adjacent scope): `mt5/ea/Include/Book/SwapEurq.mqh`,
  `research/bpure/feed/swap_eurq_generator.py`, `research/bpure/feed/swap_eurq_gate.json`

---

## 1. GATE NUMBERS — G-S1..G-S4 (all-python, no terminal) — ALL PASS AT BIT-ZERO

`coresignal_gates.json` verdicts: `G_S1_pass=true, G_S2_pass=true, G_S4_pass=true`;
`trigger_gates.json`: G-S3 all matched. Runtime: gates 85.7 s, triggers 247.7 s. pandas 3.0.1.

### G-S0 — kernel identity (precursor)
27/27 pandas-faithful kernels (roll_var/rolling max-min/Donchian-ffill/shift-label/EG
z-ensemble) bit-equal, worst 0.0. The ≤5e-14 residual class the design flagged as the largest
risk **did not materialize** — the kernels are bit-zero, not merely flip-absorbed.

### G-S1 — tgt identity (live steppers vs frozen `tgt`)
Two diffs, both across all 9 legs:
- **full native grid** (`G_S1_fullgrid`): 9/9 legs `bit_equal=true`, `max_abs_diff=0.0`,
  `n_not_bit_equal=0`, **0 discrete decision flips**, total **20,950,676** rows.
- **all 32 segment CSVs** (`G_S1_csv`): 32 segments compared, per-leg 0 not-bit-equal,
  0 flips.

Per-leg row counts (bit-zero each): XAU 2,123,532 · USDJPY(S5) 2,233,629 · ETH 2,619,688 ·
EURGBP 2,234,313 · USTEC 2,114,245 · USDJPY(S6) 2,233,629 · AUDUSD 2,233,223 ·
NZDUSD 2,232,575 · BTC 2,925,842.

### G-S2 — account passthrough (live-computed tgt through CoreSim arithmetic)
- 32/32 segments: `flips=0`, `live_index_equal`, `live_bit_eqc`, `live_bit_eqw`,
  `live_bit_margin` all true; `frozen_regression_bit_eqc=true` (frozen feed still reproduces).
  **Total lot-decision flips across all segments = 0.**
- net lots vs `v7_book_lots_1m.parquet` (`G_S2_lots_vs_frozen_parquet`): 8/8 symbols
  `bit_equal=true`, `n_diff_rows=0` each.
- final chained eqc = **532229.8433634703** (bitwise == target).

The owner-ratified fallback ("0 lot-decision flips + ≤1e-12") was **not needed** — the pass is
at bit-zero, the stronger criterion.

### G-S4 — f_core (live chain vs frozen hourly parquet)
All 8 columns (AUDUSD/BTCUSD/ETHUSD/EURGBP/NZDUSD/USDJPY/USTEC/XAUUSD)
`bit_equal=true`, `max_abs_diff=0.0`, `index_equal=true`.

---

## 2. G-S3 — TRIGGER IDENTITY + the LIVE-vs-HARNESS DIFFERENTIAL

### 2.1 Harness mode (anchor-exact, incl. retrospective bfill) — EXACT
`trigger_gates.json.G_S3`:
- 31 triggers frozen / 31 mine; **act dates 31/31 matched**, **decided dates 31/31 matched**,
  **segment t0 32/32 matched**.
- seeds `max_abs_diff=0.0`, `seeds_all_bit_equal=true`; every `per_trigger.seed_bit_equal=true`.
- final eqc 532229.8433634703, `final_eqc_bit_equal=true`.
- **0 harvest fires** (`n_harvest_fires=0`); harvest headroom max slot / threshold = 1.0288 —
  the k=2.5 arm came within 3% of firing but did not, anchor-faithful.
- **Sunday-decided trigger reproduced: 2021-05-23** (the weekend-row evaluation the design
  called out as mandatory).

### 2.2 Live mode (causal hold-at-legcap, no bfill, telemetry) — IDENTICAL to harness
`trigger_gates.json.live_differential`:
- 31 triggers harness / 31 live; **`trigger_dates_identical=true`, `date_diffs=[]`**.
- seeds `max_abs_diff=0.0`; `final_eqc_live=532229.8433634703`, `final_eqc_equal=true`.
- **hold-at-legcap touched 5 rows** (`n_held_rows=5`), and on **0 of them did the decision
  differ** (`n_held_rows_decision_differs=0`). The 5 held rows are the day-after each
  weekend-start segment (2022-09-25, 2023-09-03, 2024-07-28, 2025-04-13, 2025-07-27); at every
  one the live shares sit at the flat 1/7 ≈ 0.14286 and neither band nor harvest fires under
  either the legcap-held or the bfilled value.
- `max_first_print_lag_days=2` (5 weekend-start segments show a 2-day lag on the 5 FX slots;
  the 2 crypto slots print same-day). This is **below the 5-day min-gap**, so a band decision
  can never read a held/bfilled row — the design's fork-#3 argument is now a measurement.

**The 999-month-probe equivalence (design §4.2 #5, INFER) is converted to a measurement:** live
and harness produce the identical 31 triggers, so the probe escalation collapsed to `act < hi`
with no in-sample constraint, exactly as argued.

---

## 3. MQL5 TWIN + MIRROR — the language layer

Two independent MQL5-side checks. **Both prove the ARITHMETIC SHAPE, not yet the compiled
binary in the terminal.**

### 3.1 Software-fma twin mirror (`mql5_coresignal_mirror.py` → `coresignal_mirror.json`)
A python re-expression of `CoreSignal.mqh`'s exact arithmetic shape — `CsFmaEmul`
(Dekker/TwoProduct software fma) roll_var, the MQL5 kernel shape — diffed against the same
frozen references. Verdicts `M_1_pass, M_2_pass, M_3_pass, M_4_pass, fma_emul_bit_equal_hw` all
true:
- **M_3 tables**: opex calendar (375 days, ascending) equal; USD & JPY policy day/rate tables
  equal.
- **M_1 full grid**: 9 legs (10 entries incl. both USDJPY slots) all `bit_equal`, `max_abs_diff
  0.0`, 0 flips — same 20.95M rows.
- **M_2 seg replay**: 32 segments, per-leg 0 not-bit-equal.
- **M_4 coverage**: every leg `first_stamp_is_grid_start=true`, `rows_replayed==grid_len`.
- **fma emulation fidelity**: 78,088 software-fma calls, **0 mismatches vs hardware fma**;
  BTC hurdle-distance telemetry min 0.00370, 0 rows within 1e-9 of the hurdle (no knife-edge).

### 3.2 Compiled MQL5 scripts (0/0, terminal run STAGED)
- `CheckCoreSignal.mq5` — compile/smoke + python-golden block (opex/policy tables + a
  deterministic 240-day synthetic series vs the python golden). **Compiles 0 errors / 0
  warnings** (3325 ms). Terminal run STAGED.
- `TestCoreSignal.mq5` — the true G-S5: replays the frozen 2020–2025 bars through the compiled
  `CoreSignal.mqh` and self-diffs vs the frozen `tgt` column (the golden the python chain is
  bit-zero against). **Compiles 0/0** (1173 ms). Terminal run STAGED.

---

## 4. VERIFIER VERDICT — unsoftened

**What is PROVEN (all-python + software-fma twin):** the CCoreSignal design reproduces the
frozen Core leg-target and the entire 32-segment trigger schedule at **bit-zero** — not
flip-absorbed, not ≤1e-12, literally 0.0 — across 20,950,676 leg-bar targets, 8-symbol net
lots, f_core on 8 columns, the full chained eqc, and all 31 triggers in BOTH the anchor-exact
and the causal-live detector modes. The three risks the design ranked highest are retired by
measurement: kernel bit-parity is exact (G-S0 27/27), trigger detection is all-or-nothing and
came out 31/31 with 0 harvest fires and 0 live-vs-harness date diffs, and the 2-day leading-edge
lag is provably below the 5-day gate so it can never move a band decision in-sample.

**What is NOT yet proven — do not grade it as done:**
1. **G-S5 in-terminal is STAGED, not run.** The compiled `TestCoreSignal.mq5` /
   `CheckCoreSignal.mq5` are 0/0 but have not executed in the terminal. The bit-zero claim for
   the *compiled* CoreSignal.mqh rests on the software-fma *emulation*, which is a faithful
   model of MQL5's arithmetic but is not the binary. Prior components (RECON-8b..8e) showed the
   compiled terminal can add ULP-band noise the mirror lacks (e.g. TestBook +3 rows in the
   5e-13–1e-12 band). CoreSignal's targets are integer-lot-floored, so ULP noise is expected to
   be flip-invisible — but that is a prediction until TestCoreSignal runs.
2. **Live daily-mid drift is R2, out of the R1 gate.** Every G-S* number uses the frozen
   `(bid_c+ask_c)/2` fields. Live broker mids will differ by construction; the live daily
   coefficients drift within the ratified band. Nobody should read the R1 bit-zero as a live
   guarantee.
3. **Forward triggers (2026+) can land in genuinely new regimes** — gap=5 edges, leading-edge
   segments. The in-sample slack (12-day min gap, 2-day max lag) is comfortable but is an
   in-sample fact; the live-mode telemetry + refuse-to-trade-on-j-splice latch is the
   containment, not a proof of forward correctness.
4. **Swap/eurq live generator is built but owner-DEFERRED (S2_PREP §194).** `SwapEurq.mqh` +
   `swap_eurq_generator.py` exist and the python gate (`swap_eurq_gate.json`) PASSES — tables
   (policy_rates/markups/instruments/swap_pct_mult) all "match", 2618 rollover-DST days checked,
   positive controls PASS (b_h 92,155 bars, coresim 599,565 rows). But it is NOT ratified into
   this track; the gates above run on the **pre-baked exported arrays**, and `CheckSwapEurq.mq5`
   is not yet compiled/run. Treat the generator as a live-deploy prerequisite, tracked
   separately.

**Verdict:** Track A (live Core signal + trigger) is **R1-CLOSED in python at bit-zero and
mirror-confirmed at the MQL5 arithmetic shape**, pending the single STAGED terminal
certification (G-S5). The design's five owner decisions are all ratified and all held up under
measurement.

---

## 5. OWNER TERMINAL RUNSHEET (each run → dated FMA3-RECON-N ledger entry)

Wine-compiled 0/0, awaiting owner terminal execution. Judge scripts named per run.

| # | script | what it proves | judge | ledger |
|---|--------|----------------|-------|--------|
| 1 | `TestCoreSignal.mq5` | **G-S5**: compiled `CoreSignal.mqh` tgt stream over frozen 2020–2025 bars == frozen `tgt` (bit-zero target: the 20.95M-row golden) | self-diff in-script; cross-check `validate_mql5_coresim.py` pattern | FMA3-RECON-9 (new) |
| 2 | `CheckCoreSignal.mq5` | structural smoke (opex/policy tables, CsDaysFromCivil) + python-golden 240-day synthetic block | in-script vs embedded golden | folded into RECON-9 |
| 3 | `CheckBookState.mq5` | **STILL PENDING from S2-prep (RECON-8f):** the T1–T7 in-terminal split/continue + 5-latch refuse battery (torn-write eof, fnv64 checksum, a-anchor re-base, j-splice discontinuity) | in-script battery | FMA3-RECON-9-WS |

Notes:
- Runs 1–2 are the same terminal batch (both Core signal). Run 3 (`CheckBookState`) carries
  over from the S2-prep runsheet — compiled 0/0 at RECON-8f, never executed; the python split
  gate PASSED (tail bitwise identical, end-state byte identical, all 5 latches fire) but the
  MQL5 in-terminal battery is the missing certification.
- Wine `FileMove` rename-atomicity remains uncertified from this repo; the fnv64/eof marker
  protocol is the load-time backstop regardless.
- NOT on this runsheet (deferred): `CheckSwapEurq.mq5` — compile + run gated behind the owner's
  decision to ratify the live swap/eurq generator into deploy.

---

## 6. WHAT REMAINS FOR THE FULL EA ASSEMBLY

Track A closes the live Core *signal + trigger*. The remaining S2/S3 build:

1. **Execution seam** — wire the detector-driven `FinishSegment → ComputeFCore → BeginSegment`
   and per-union-bar `StepLegBar(leg, ..., tgt = signal.TgtAt(leg, ts))` into
   `BookOrchestrator.mqh` live mode (today it drives frozen-CSV batches); then live
   blend → `g_fedTgt[33]` → `FED_Reconcile` with RECON-4 position fidelity. Only AFTER G-S5
   passes in terminal.
2. **M1 live-feed assembler** — the single source of bars feeding both the daily-mid derivation
   (last-bar-of-raw-day `(bid_c+ask_c)/2`, EG pre-20 variant) and the union grid. Shared by
   harness and live; NOT CoreEngine's `CopyRates`/`BarMid` path. Includes the live swap/eurq
   generator (built, python-gated, terminal-staged) once ratified.
3. **Warm blob** — fold CCoreSignal state into the Track-B `CBookState` schema (version bump):
   8 daily-mid rings (≤262 days) **plus the two XAU Donchian last-breach flags** (formally
   unbounded, ffill-from-2020 — must be carried explicitly, a ring rescan is not guaranteed
   bit-exact after a long breach-free stretch) + defer state + current-day coefficients.
4. **S3 tester / R2** — 1m-OHLC smoke then real-tick; grade against the R2 band, not the R1
   bit-zero gate (live daily-mid drift is R2 by construction). Warm-start RECON-9-WS + crisis
   real-tick per the standing MT5-validation protocol → full 6-gate RECON-9.

---

*Engine of record: Python 1-minute worst-mark (MEMORY campaign-charter). This document records
MEASURED gate numbers and STAGED terminal dependencies only; no claim here is graded PASS on the
strength of a staged run.*
