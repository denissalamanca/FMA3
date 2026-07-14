# B-pure Wave 3 — account engines (b_h, a_h) + live blender in MQL5 — STATUS

**Date:** 2026-07-14 (afternoon session). **Follows:** FMA3-RECON-8 / Wave 2
(`model/v3/BPURE_WAVE2_STATUS.md` — native signal layer PASSED in-terminal,
max|diff| 4.197e-14 vs the golden book). **Frozen artifact:** FMA3-v34-freeze-1,
freeze_hash `fc14159f5352d685214d3a417b0d71117dda300a7c7be02919daa83fd06c1446`.
**Model of record:** `model/v3/` (static_blend(0.70)×s — IC €3,872,872 s=1.6 /
FTMO €1,332,404 s=0.7).

> **BOTTOM LINE: all three Wave-3 tracks are built, compiled 0 errors /
> 0 warnings, installed to the wine prefix, and each one carries a measured
> Python-side parity result at the maximum possible strictness (bitwise /
> bit-exact) — with ZERO blocking verifier findings across all three.**
>
> - **Track A (Satellite b_h account engine):** statement-mirror of the
>   in-terminal harness is **BITWISE (max|diff| 0.0)** vs the golden curve
>   over both exported quarters (185,736 bars), chained warm-start state
>   included. The underlying stepper was already bitwise over all
>   **2,948,650** bars.
> - **Track B (Core a_h idealized shadow):** scalar reference is
>   **BIT-EQUAL** to the parity parquet on **32/32 segments, 2,947,085 bars**
>   (every leg, every seed, eqc/eqw/margin). MQL5 port compiled; its
>   in-terminal input exporter is NOT written yet (staged, honestly open).
> - **Track C (static_blend live blender):** mirror output re-judged during
>   this write-up: **BIT-EXACT (max|diff| 0.0)** vs the full-precision golden
>   over all **805,585** rows, and 5.0e-13 vs the RECON-4 pinned 12-decimal
>   golden — exactly its quantization bound.
>
> **Nothing in this wave has run inside the MT5 terminal yet.** The owner
> run-sheet (§6) stages TestBlend + the chained TestSatEquity quarters; both
> are fully installed and ready. TestCoreSim compiles and self-stages but
> cannot produce numbers until its exporter exists (§4). One install landmine
> was found and FIXED during this write-up (§5: the Track-A bundle had been
> exported to a Common Files directory the terminal has never read).

---

## 1. Track A — SatEquityNative (b_h account engine, MQL5 port)

**Deliverables (all in-repo, all measured):**

| Artifact | What | Evidence |
|---|---|---|
| `mt5/ea/Include/Sat/SatEquityNative.mqh` | 1:1 port of `bh_stepper.py::BHAccountStepper.step` (itself a statement transcription of the engine of record `account_engine_1m.py::_run_chunk`, frozen sha `700ea915…`) | compiles inside TestSatEquity 0/0 |
| `research/bpure/engine/bh_stepper.py` + `BH_ENGINE_SPEC.md` | scalar reference + spec | `bh_parity.json`: **bitwise** vs golden `curve.parquet` over all **2,948,650** bars (stage 2), metrics vs the frozen pin bit-equal — CAGR 0.8865880762592069, MaxDD_worst 0.2167488591051508, final €449,707.7452664526, n_trades 20,403 — and stage-3 warm-start (snapshot after 2022Q2, resume 2022Q3, 1,830,424 tail bars) **bitwise** |
| `research/bpure/engine/export_bh_quarter.py` | per-quarter bundle exporter (289-col inputs, golden slice, state-in/expected JSONs; float32 price round-trip VERIFIED at export) | `bh_export_report.json`: 2020Q1 (92,155 bars) + 2020Q2 (93,581 bars) exported, `chain_bit_equal_golden: true` |
| `mt5/ea/scripts/TestSatEquity.mq5` | in-terminal chained-quarter replay SCRIPT (zero trading functions); prints a `DONE` line with in-script golden diff counters | compile log `Result: 0 errors, 0 warnings, 1348 ms` (verify recompile 1375 ms, 0/0) |
| `research/bpure/engine/sat_equity_harness_sim.py` | python statement-mirror of the harness driving loop (same CSV parse, sparsity/carry rules, float32 cast, eurq mapping, state chaining) | see mirror gate below |

**Mirror gate (run 2026-07-14, `python3 sat_equity_harness_sim.py 2020Q1
2020Q2`, report `…scratchpad/bh_mirror_report.json` — re-read during this
write-up):**

| Quarter | bars | eq exact | eqw exact | max abs diff eq / eqw | end-state bitwise | final balance | n_trades |
|---|---|---|---|---|---|---|---|
| 2020Q1 | 92,155 | 92,155 | 92,155 | **0.0 / 0.0** | YES | 11,984.916325804577 | 307 |
| 2020Q2 | 93,581 | 93,581 | 93,581 | **0.0 / 0.0** | YES | 12,366.578333400847 | 842 |

All 185,736 bars **BITWISE** vs the golden curve slices (gate was ≤1e-12;
measured 0.0). Chained state-in also bitwise (`chain_state_in_bitwise: true`).

**What this proves / does not prove.** Proves the harness loop, CSV
round-trip, eurq mapping, float32 price cast and chained warm-start state
JSON are exact, on top of a stepper already bitwise-proven over the full 6
years. Does NOT prove the MQL5 language layer — that is exactly what the
owner's in-terminal TestSatEquity run (§6) isolates, since the mirror and
the script are statement-for-statement locked.

**Verifier verdict: no blocking findings.**

---

## 2. Track B — CoreSim / a_h (Core idealized standalone shadow)

**Deliverables:** `research/bpure/coresim/CORESIM_SPEC.md` (dissection of
`CoreEngine.mqh` vs the idealized shadow, normative scalar spec, frozen
band-trigger segment design), `coresim_reference.py` (scalar reference),
`mt5/ea/Include/Core/CoreSim.mqh` (`CCoreLegSim`/`CCoreBookSim`) +
`mt5/ea/scripts/TestCoreSim.mq5` (chained segment replay harness, Track-A
pattern) — compile log `Result: 0 errors, 0 warnings, 1074 ms`.

**Measured parity (`python3 coresim_reference.py --all`, run 2026-07-14 from
FMA2/research; raw report `research/bpure/coresim/coresim_parity.json`,
`all_pass: true`, runtime 58.8 s):**

- **32/32 committed segments PASS**, total **2,947,085 bars = every row of
  the parity parquet** `research/outputs/v7_book_equity_1m.parquet` (legacy
  on-disk name; eqc/eqw/margin, noliq stop_out=1e-9, IC server time).
- Gate G-a: every leg of every segment **bit-equal** (`np.array_equal`
  eq_c/eq_w/margin) vs the NSF5 numba `run_backtest`.
- Gate G-b: combined book **bit-equal** eqc/eqw/margin + index equality vs
  the parquet on every segment; max_abs_delta 0.0 everywhere.
- Gate G-c: every segment seed bit-equal to the parquet carry AND to
  `triggers[j-1].book`.
- 0 NaN targets in-window, 0 stop-outs. Full-run final eqc (= the MQL5
  target number): **532,229.8433634703**.

**Honest scope statement:** the MQL5 side of Track B has **zero measured
numbers**. `CoreSim.mqh` compiled 0/0 and its source passed adversarial
review against the spec, but `export_coresim_inputs.py` (per-segment leg
feeds, ~2–6 GB total) and `validate_mql5_coresim.py` are **not written**
— TestCoreSim detects the missing manifest and exits cleanly with a staged
notice. Compile ≠ correctness; the bit gate for the MQL5 run is defined in
CORESIM_SPEC §7 and stays open.

**Verifier verdict: no blocking findings.**

---

## 3. Track C — static_blend live blender (BookBlend.mqh)

**Deliverables:** `mt5/ea/Include/Book/BookBlend.mqh` (1:1 port of
`model/v3/reproduce.py::static_blend` with the documented IEEE-754 op-order
contract and the export_book_frac_v3 netting semantics),
`research/bpure/blend/export_blend_inputs.py` (frozen inputs + %.17g golden;
hard-fail self-checks), `mt5/ea/scripts/TestBlend.mq5` (compile log
`Result: 0 errors, 0 warnings, 1164 ms`), `mirror_blend.py` (statement
mirror), `validate_blend.py` (judge).

**Exporter self-checks (hard-fail, all passed at export):** scalar recompute
from the exported arrays vs the pandas static_blend matrix max|diff| = 0.0
(bitwise) over 49,379 hours; %.17g CSV re-parse bitwise; fresh
`build_rows(static_blend)` byte-identical to the on-disk golden
`research/outputs/mt5/FMA3_fed_frac_v3.csv`.

**Mirror gate — RE-MEASURED during this write-up** (`python3
research/bpure/blend/validate_blend.py`, actual =
`research/outputs/mt5/blend/FMA3_blend_actual_mirror.csv`):

| vs golden | rows | structure | max abs diff | verdict |
|---|---|---|---|---|
| golden12 `FMA3_fed_frac_v3.csv` (12 dp, **sha256 `d00b614b650b…8ab452e` — re-hashed today, == the RECON-4 pinned stream sha**) | 805,585 | IDENTICAL (row sequence incl. all 402 `__GRID__` sentinels — count re-verified on all three files) | **5.000e-13** at (1593154800, EURGBP) | **PASS** ≤ 1e-12 — 5.0e-13 is exactly the 12-decimal quantization bound, i.e. bit-exact arithmetic |
| golden17 `FMA3_blend_golden17.csv` (%.17g) | 805,585 | IDENTICAL | **0.0** | **PASS — BIT-EXACT** |

Structural equality of the (epoch, symbol) row sequence means the emission
semantics (EPS threshold, broker map, ordering) are validated together with
the arithmetic, not just the values.

**Frozen-seasonal guard (landmine, handled):** FMA2's live
`seasonal_pos.parquet` was regenerated 2026-07-14 and drifted from the
RECON-5 freeze on 70 weekly XAUUSD rows. The exporter detects the drift and
substitutes the freeze snapshot; the on-disk golden (RECON-4 sha) agrees
with the FREEZE version. Any future regeneration of blend inputs must keep
this guard.

**Honest scope statement:** this gate validates the blender on **FROZEN
inputs** — `a_h`/`b_h` are the frozen native standalone curves replayed from
the exporter (the v3 lesson: the EA must REPLAY the unified `book_frac` /
frozen curves; compute-live diverges at s≠1). Live in-EA computation of
`a` (Track B) and `b` (Track A) feeding this blender is precisely what the
remaining waves assemble; nothing here certifies that seam yet.

**Verifier verdict: no blocking findings.**

---

## 4. Aggregate verifier verdict

All three tracks were independently adversarially reviewed: **zero blocking
findings** (Track A: none; Track B: none — with the explicit caveat that no
MQL5 numeric evidence exists yet; Track C: none). Unlike Wave 2 there is no
constant-table defect to fix before running. "Compiled 0/0" remains a
measured fact about compilation only.

---

## 5. Install state (all measured 2026-07-14)

**Prefix scripts** (`…/MQL5/Scripts/`):

| File | .ex5 size / time | Compile log |
|---|---|---|
| `TestBlend.mq5` | 24,812 B, 12:58 | `0 errors, 0 warnings, 1164 ms` |
| `TestSatEquity.mq5` | 33,154 B, 13:00 | `0 errors, 0 warnings, 1348 ms` |
| `TestCoreSim.mq5` | 25,046 B, 13:04 | `0 errors, 0 warnings, 1074 ms` |

**Prefix includes** (`diff -rq` repo vs prefix, run during this write-up):
`Include/Sat/` — **all 11 files identical**; `Include/Core/CoreSim.mqh` and
`Include/Book/BookBlend.mqh` — **identical** (the other repo-side
Core/Book EA files are not needed by these scripts and are not claimed
installed; prefix `Book/` also contains unrelated legacy FableMA2 files).

**Common Files data** (terminal dir =
`…/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files/`):

| File | Measured |
|---|---|
| `FMA3_blend_inputs.csv` | 22,459,655 B, sha256 `78887da8adb3…a7fe040` — **identical hash to the repo source** `research/outputs/mt5/blend/FMA3_blend_inputs.csv` |
| `FMA3_bh_inputs_2020Q1.csv` | 190,436,789 B, sha `3042dd7c9f8d…2200ab` |
| `FMA3_bh_inputs_2020Q2.csv` | 194,283,604 B, sha `14e6e9204abb…52d90a` |
| `FMA3_bh_golden_2020Q1.csv` / `_2020Q2.csv` | 4,492,534 B / 4,564,739 B, shas verified |
| `FMA3_bh_state_in_*.json`, `FMA3_bh_state_expected_*.json` | 4 files, present |

**FIXED install landmine:** `export_bh_quarter.py`'s `COMMON_FILES` constant
points at `drive_c/users/dsalamanca/…/Common/Files` — a directory **created
fresh today (12:46) that the terminal has never read**; every artifact any
in-terminal run has actually consumed (Wave-2 `FMA3_v34_inputs.csv`, the
replay CSVs, `FMA3_blend_inputs.csv`) lives under `drive_c/users/crossover/…`.
All 8 Track-A files were **copied to the crossover Common Files during this
write-up and hash-verified identical** (table above). Without this fix,
TestSatEquity would have printed "cannot open FMA3_bh_inputs_2020Q1.csv" and
exited. Follow-up: fix the constant in `export_bh_quarter.py` before the next
export (open item §7).

---

## 6. Owner run-sheet (in-terminal, in this order)

No step here launches trading — all three are Scripts with zero trading
functions. Start MT5, open any chart, run from Navigator → Scripts.

**Step 1 — TestBlend (blender, ~805k output rows).**
1. Drag `TestBlend` onto a chart. Wait for the Experts-log line starting
   `DONE` (it prints the row count and the bitwise `sumcheck` verdict — the
   sumcheck catches any `StringToDouble` parse loss in the terminal).
2. Judge:
   ```
   python3 /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/blend/validate_blend.py --from-common
   ```
   **PASS bars:** structure IDENTICAL on both goldens; max|diff| ≤ 1e-12 vs
   golden12 AND == 0.0 vs golden17 (the mirror achieved exactly this — the
   terminal must match it; any excess is the MQL5 language layer, which is
   the thing this run measures).

**Step 2 — TestSatEquity 2020Q1 (fresh start).**
1. Drag `TestSatEquity` onto a chart; inputs: `InpQuarter=2020Q1`,
   `InpStateIn=""` (fresh 10k). ~92k bars, progress every 10,000.
2. Acceptance (printed in the `DONE` lines, in-script golden diff):
   `bars=92155`, `final_balance=11984.916325804577`, `n_trades=307`,
   `eq_exact=92155 eqw_exact=92155 max|d_eq|=0 max|d_eqw|=0`.
3. Cross-check the written state: `FMA3_bh_state_out_2020Q1.json` in Common
   Files must equal `FMA3_bh_state_expected_2020Q1.json` field-for-field
   (and equal the mirror's `…scratchpad/FMA3_bh_mirror_state_out_2020Q1.json`).

**Step 3 — TestSatEquity 2020Q2 (CHAINED — this is the warm-start proof).**
1. Run again with `InpQuarter=2020Q2`,
   `InpStateIn=FMA3_bh_state_out_2020Q1.json` (the file Step 2 just wrote —
   chaining from the terminal's own output, not the exporter's, is the
   point).
2. Acceptance: `bars=93581`, `final_balance=12366.578333400847`,
   `n_trades=842`, `eq_exact=93581 eqw_exact=93581 max|d_eq|=0
   max|d_eqw|=0`; state-out equals `FMA3_bh_state_expected_2020Q2.json`.

**Step 4 — record.** Report the verdicts for a new FMA3-RECON-N entry in
`research/protocol/RECONCILIATION.md` (append is the orchestrator's job).
If any diff is nonzero: the first divergent (ts, field) is in the actual
CSV vs the golden slice — investigate per the standing ladder; **no fix
justified only by "it moved the numbers closer"**.

**TestCoreSim is NOT runnable yet** — it self-stages ("input exporter has
not been run yet") and exits cleanly. Do not count it as a gate.

---

## 7. What remains after these gates (Wave 4+)

1. **Track B in-terminal chain:** write `export_coresim_inputs.py`
   (per-segment leg feeds; watch the multi-GB volume — per-segment export)
   and `validate_mql5_coresim.py` (bit gate vs the parity parquet slices;
   full-run final eqc 532,229.8433634703), then the owner's TestCoreSim run.
2. **Fix `COMMON_FILES` in `export_bh_quarter.py`** (points at the wrong
   wine user dir — §5) and export/replay the remaining b_h quarters beyond
   2020Q1–Q2 (the chained design is quarter-by-quarter through 2025Q4).
3. **Full EA assembly (`FableBookNative`):** live `a` (CoreSim) + live `b`
   (SatEquityNative) feeding `BookBlend` — closing the frozen-inputs scope
   limit of §3 — plus execution and the Guardian, ending in a trading `.ex5`.
4. **Warm-start certification** vs ≥2019 data (record-engine COVID cold-start
   artifact is the standing reason — the record engine is BLIND in COVID;
   trust MT5 real-tick for the crisis gate).
5. **Tolerance ratification by the owner:** the Python-side gates in this
   wave are bitwise/bit-exact; the owner must ratify what the ACCEPTED
   in-terminal bars are (Wave 2 precedent: 1e-12 on the signal book) before
   any gate is declared passed on softer numbers.
6. **FMA3-RECON-9:** the full 6-gate reconciliation entry on the final
   trading binary before any tester/deploy step — per the standing record,
   every new EA run gets a recorded RECON entry before deploy. Staged MT5
   validation order stands: 1m-OHLC smoke first, real-tick only after
   mechanics pass; two preset dashboards (IC + FTMO) per update.
