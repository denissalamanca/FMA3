# B-pure Wave 2 — MQL5 native translation + in-terminal replay harness — STATUS

**Date:** 2026-07-14 (overnight session). **Ledger:** FMA3-RECON-8 (see
`research/protocol/RECONCILIATION.md`). **Follows:** FMA3-RECON-7 / Wave 1
(`model/v3/BPURE_WAVE1_RESULTS.md` — the scalar Python reference that is the
spec for this wave). **Frozen artifact:** FMA3-v34-freeze-1, freeze_hash
`fc14159f5352d685214d3a417b0d71117dda300a7c7be02919daa83fd06c1446`.

> **BOTTOM LINE (updated 2026-07-14 03:32, post-fix): translation + harness
> are built, compiled 0 errors / 0 warnings, installed — and the §3 blocking
> finding is RESOLVED. The 4 wrong CAD policy-rate dates in
> `CarryBreakout.mqh` were corrected (19513→19515, 19548→19550, 20087→20117,
> 20129→20159), the full table was re-verified against the frozen
> `engine/costs.py` parse — 178/178 (day,rate) entries across all 10
> currencies match, 0 mismatches — the fixed include was reinstalled to the
> wine prefix (sha256 `a54cb065d2f6ba82…`, repo and prefix identical), and
> both `CheckCarryBreakout.mq5` and `TestV34Native.mq5` were RECOMPILED to
> `Result: 0 errors, 0 warnings` (fresh `TestV34Native.ex5`, 84,326 B,
> 03:32). The wave is now READY-TO-RUN: the only remaining step is the
> owner's in-terminal replay (§4, step 1 now obsolete — start at step 2).**

> **RESULT (2026-07-14 09:16, RECON-8b): PASS.** Owner ran `TestV34Native` in
> the MT5 terminal (49,379 bars; Experts-log DONE line confirmed).
> `validate_mql5_book.py` vs the frozen golden `book.parquet`: **max|diff|
> 4.197e-14, 0/1,530,749 cells above the 1e-12 gate**, 0 NaN, shapes aligned.
> Worst USA500 4.2e-14 / USTEC 3.6e-14 (last-ULP on the tanh-heavy intraday/
> trend legs). The native MQL5 v34 signal layer reproduces the shipped book
> across the full 6 years — the Stage-0-deferred MathRound/banker-tie and
> transcendental-ULP residuals are measured negligible. Scope: signal-layer
> arithmetic on the frozen (float32-quantized) input CSV; b_h-native, v7/a_h,
> the live blender, execution, and live-tick pricing remain Wave 3.

---

## 1. Translation status (per unit)

Compile = a standalone `Check<unit>.mq5` compiled headless via wine
MetaEditor (`/compile`), log read as UTF-16LE, success = `Result: 0 errors,
0 warnings` (all Result lines below re-read from the logs at
`…/MQL5/Scripts/FMA3v34Checks/*.log`, all dated 2026-07-14 03:10–03:12).
Verifier = the independent adversarial review of the `.mqh` source against
the frozen Wave-1 scalar reference.

| Unit (`mt5/ea/Include/FMA3v34/`) | Compile 0 err / 0 warn | Verifier verdict |
|---|---|---|
| `SeasonalCrypto.mqh` | YES | no blocking finding |
| `MagXau.mqh` (mag_xau overlay) | YES | no blocking finding |
| `Intraday.mqh` | YES | no blocking finding |
| `Crisis.mqh` | YES | no blocking finding |
| `MeanRev.mqh` | YES | no blocking finding |
| `TrendV2.mqh` | YES | no blocking finding |
| `CarryBreakout.mqh` | YES | **BLOCKING — 4 wrong CAD policy-rate dates (§3)** |
| `Ensemble.mqh` | YES | no blocking finding |
| `V34Math.mqh` (shared helpers: banker's rounding, ewm, Welford std, NaN) | YES | (helper — covered by the unit reviews) |

Aggregate verifier verdict: **confirmed = NO.** One blocking finding
(CarryBreakout), zero blocking findings elsewhere. "Compile YES" is a
measured fact; it does **not** imply numerical correctness — that is what
the in-terminal replay (§5) is for, and it may only run after the §3 fix.

---

## 2. Harness — description + install state (all measured 2026-07-14)

**Script:** `mt5/ea/scripts/TestV34Native.mq5` — a SCRIPT (`OnStart`), zero
trading functions. Adopts the proven Gemini `TestBrain2` pattern: CSV in
the terminal Common Files dir → step every union-grid hour through the 8
native units → CSV out.

- **Input contract:** `FMA3_v34_inputs.csv` = 49,379 rows × (epoch-seconds
  timestamp + 37 RAW close columns in `core.ALL` order), EMPTY field where a
  symbol printed no bar. **No injected vols / has_bar / day_valid** — the
  steppers own all ffill / return / daily-grid / NaN semantics.
- **Every derivation the harness performs from raw closes was PROVEN
  BITWISE in Python** by `research/bpure/mql5/export_master_inputs.py`
  against the frozen U matrices: streaming ffill == `U["close"]`; streaming
  clipped `xau_ret` == `U["ret"]`; the day-close rule (calendar day closes at
  the first bar of the next grid day, closes = ffilled values as of the
  previous bar) == `resample('1D').last()`; trend_v2 / crisis effective-hour
  stamping; the seasonal one-bar deferred-emit assembly.
- **Output:** `FMA3_v34_native_actual.csv` — timestamp + the 31 golden
  `book.parquet` columns, doubles printed `%.17g`. Final log line starts
  with `DONE`; progress every 5,000 bars.
- **Dry-run of the full pipeline in Python:** `research/bpure/mql5/
  harness_sim.py` (a Python simulation of the harness assembly) already
  passed the validator gate — `mql5_book_parity.json`: max|diff|
  4.196e-14, **0 / 1,530,749 cells > 1e-12** vs the golden book. The
  in-terminal run replaces the Python compute with the compiled MQL5 units.

**Install state (measured — sizes/hashes from `ls` / `shasum` tonight):**

| Artifact | Location | Measured |
|---|---|---|
| Harness `.mq5` | wine prefix `…/MQL5/Scripts/TestV34Native.mq5` | 20,774 B, **byte-identical to the repo copy** (`diff` clean) |
| Harness `.ex5` | wine prefix `…/MQL5/Scripts/TestV34Native.ex5` | **83,932 B**, compiled 2026-07-14 03:11, log `Result: 0 errors, 0 warnings, 3655 ms` |
| Includes | wine prefix `…/MQL5/Include/FMA3v34/` (9 files) | `diff -rq` vs `mt5/ea/Include/FMA3v34/` → **identical** |
| Inputs CSV | `…/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files/FMA3_v34_inputs.csv` | 23,683,879 B, sha256 `a96a4971e88f1928e584ee1eb1212050bcc6599235e69474b08592f0721eb70c` — **identical hash to the repo source** `research/bpure/mql5/out/FMA3_v34_inputs.csv` |
| Validator | `research/bpure/mql5/validate_mql5_book.py` | reads the Common-Files actual + `model/v3/freeze/FMA3-v34-freeze-1/golden/book.parquet`; PASS iff shapes/timestamps match, no NaN, 0 cells > 1e-12 |

*Bookkeeping note:* an earlier build note quoted the harness `.ex5` as
85,770 B; the binary was recompiled at 03:11 after a late source edit — the
current measured size is **83,932 B**. The number that matters is the
compile log's `0 errors, 0 warnings`, re-read tonight. (The `.ex5` is stale
against the pending §3 fix anyway and must be recompiled tomorrow.)

---

## 3. Verifier findings — BLOCKING (verbatim substance, not softened)

**BLOCKING — `CarryBreakout.mqh` CAD policy-rate table: 4 wrong epoch
days vs spec.** Spec = `parse_policy_rates` over the frozen `costs.py`
(byte-identical to the live `NewStrategyFable5/engine/costs.py`). The MQL
`V34CB_RATE_DAY` CAD rows contain **19513, 19548, 20087, 20129** where the
spec gives **19515** (2023-06-07), **19550** (2023-07-12), **20117**
(2025-01-29), **20159** (2025-03-12) — effective dates shifted EARLY by
2 / 2 / 30 / 30 days. Rate **values** are correct; only the dates are wrong.

Independently re-confirmed during this write-up: the spec's CAD list in
`NewStrategyFable5/engine/costs.py` has `("2023-06-07", 4.75),
("2023-07-12", 5.00) … ("2025-01-29", 3.00), ("2025-03-12", 2.75)`
(= epoch days 19515 / 19550 / 20117 / 20159), and the CAD block in the MQL
table (`mt5/ea/Include/FMA3v34/CarryBreakout.mqh`, lines ~136–137) reads
`…, 19382, 19513, 19548, 19879, …, 20068, 20087, 20129, …`.

- **MEASURED impact:** 128 (day, pair) net-carry-value rows wrong across 64
  days — but **zero** carry direction changes and **zero** TOP_K kept-set
  changes over the whole 2020-01-02…2025-12-31 grid (the position weight
  `w = sig*0.02/vol_d` never reads `net`), so the replay output **happens**
  to be unaffected on this dataset.
- **Why it still blocks:** the constants are wrong vs spec; the header claim
  in the file — "Verified equal to the Python parse" — is **false**; and the
  built-in smoke check (day0 = 19300, 66 days) ends before the first wrong
  date, so it is structurally incapable of catching this. "Happens to be
  unaffected on this dataset" is not correctness — a different window or a
  future carry-net-reading change would expose it silently.
- **Fix:** 4 integers in the CAD block at
  `mt5/ea/Include/FMA3v34/CarryBreakout.mqh` lines ~136–137
  (19513→19515, 19548→19550, 20087→20117, 20129→20159 — CAD block only;
  20117 legitimately appears once more in a later currency block, do not
  touch it), then re-copy to the prefix and recompile the harness + the
  CarryBreakout/Ensemble check scripts. This is a provable code-vs-spec
  mismatch, so the fix is legitimate under the anti-overfit guardrail.

No other blocking findings were reported. Non-blocking residuals carried
over from Wave 1 stand unchanged (1-ulp carry gross-cap summation order,
meanrev `z` 8.0e-10 absorbed residual, thin crisis threshold margins
1.1e-5–7.8e-5 = the in-terminal watchpoints).

---

## 4. Morning run procedure (owner)

Step 0 is mandatory; do not skip to step 3.

1. **Fix the constants.** Edit
   `/Users/dsalamanca/vs_env/FableMultiAssets3/mt5/ea/Include/FMA3v34/CarryBreakout.mqh`
   lines ~136–137, CAD block only: `19513`→`19515`, `19548`→`19550`,
   `20087`→`20117`, `20129`→`20159`. Also fix the (now false) "Verified
   equal to the Python parse" header claim or re-verify after the edit.
2. **Reinstall + recompile.** Copy the edited file to
   `"…net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Include/FMA3v34/CarryBreakout.mqh"`,
   then:
   ```
   WINE64="/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64"
   export WINEPREFIX="/Users/dsalamanca/Library/Application Support/net.metaquotes.wine.metatrader5"
   "$WINE64" "C:\\Program Files\\MetaTrader 5\\MetaEditor64.exe" \
     /compile:"C:\\mql5link\\Scripts\\TestV34Native.mq5" \
     /log:"C:\\mql5link\\Scripts\\TestV34Native.log"
   python3 -c "import codecs;print(codecs.open('/Users/dsalamanca/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Scripts/TestV34Native.log',encoding='utf-16').read())"
   ```
   Require `Result: 0 errors, 0 warnings`. (Optionally recompile
   `C:\mql5link\Scripts\FMA3v34Checks\CheckCarryBreakout.mq5` the same way.)
3. **Run in the terminal** (owner action — the overnight session does not
   launch `terminal64.exe`): start MT5, open any chart, Navigator → Scripts
   → drag `TestV34Native` onto the chart. Progress prints every 5,000 bars
   (~49k grid hours total); wait for the log line starting with **`DONE`**.
   Output lands in Common Files as `FMA3_v34_native_actual.csv`.
4. **Validate:**
   ```
   python3 /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/mql5/validate_mql5_book.py
   ```
   PASS iff exit 0: shapes/timestamps/columns match the golden
   `book.parquet` (49,379 × 31), no NaNs, **0 cells > 1e-12**. It reports
   max|diff|, per-symbol worst, and the first divergent (hour, symbol), and
   writes `research/bpure/mql5/mql5_book_parity.json`.
5. **Record:** update the FMA3-RECON-8 ledger row in
   `research/protocol/RECONCILIATION.md` with the run verdict (PASS /
   FAIL + first divergence). If it FAILs, follow the investigation ladder —
   the printed first-divergent (hour, symbol) plus the Wave-1 watchpoints
   (§5) route the suspect; **no fix justified only by "it moved the numbers
   closer"**.

---

## 5. What the in-terminal run proves — and what it does not

**Proves (the whole point of Wave 2):**
- **Cross-language book parity:** the 8 native MQL5 units, compiled and
  executed by the real MT5 runtime, reproduce the frozen golden book
  (49,379 hours × 31 columns) within 1e-12 — the same gate the Python
  scalar reference passed (4.2e-14, 0 cells over).
- **The Stage-0 deferred numeric residuals, unmeasurable on the Mac side,
  finally get measured on the real runtime:** R1 (`MathRound` half-away vs
  numpy banker's — systematic risk on the crisis 0.02 grid and the mag $100
  magnet; the ports use the banker's helper, this run proves it), R1b
  (tie-straddle-via-ULP), and transcendental last-ULP (tanh/exp library
  differences). The thin crisis threshold margins from Wave 1
  (1.1e-5–7.8e-5) are the exact watchpoints where these would surface as a
  discrete state flip.

**Does NOT prove:** no account engine ran (no CAGR/DD/EUR claims), no
trading path, no warm-start certification vs ≥2019 data, nothing about the
`b_h`/blender layers, and — per the standing protocol — nothing about
deployment (this is not a RECON gate run; no `.ex5` here is a trading EA).

**Remains after (= Wave 3):** the `b_h` engine (needs the
`v34_book_equity_1m.parquet` golden export), `V7Sim`/`a_h`, the blender
(REPLAY of the unified `fed_frac` — the v3 lesson: compute-live diverges at
s≠1), and EA integration — ending in a new `.ex5` and a full 6-gate
FMA3-RECON-N entry on that binary before any tester/deploy step.
