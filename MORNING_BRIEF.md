# FMA3 Morning Brief — 2026-07-14

## TL;DR
- All three overnight waves are **complete and pushed** to `github.com/denissalamanca/FMA3`: the whole v34 book (stages 3–5) has a bitwise/last-ulp scalar reference, the b_h account engine (stage 6 Python side) is **bitwise equal to the golden curve over all 2,948,650 bars**, and the MQL5 native port compiles clean (0/0) and is **ready to run** in-terminal.
- We never launched `terminal64.exe` — deliberately. Compile is not correctness. The one remaining open numeric question (MathRound banker-ties + transcendental ULP inside the terminal) is what **your one action** measures.
- One blocking defect (wrong CAD rate-epoch days in `CarryBreakout.mqh`) was found by our own adversarial audit, fixed, and the full 178-entry rate table re-verified 0 mismatches before commit.

## Your one action this morning
1. Open the usual wine MT5 terminal (`net.metaquotes.wine.metatrader5`).
2. Navigator > Scripts: drag **`TestV34Native`** onto any chart — any symbol, any TF. It reads no market data (pure CSV replay, no trading calls; inputs already installed in Common Files).
3. Watch the Experts log. Progress prints every 5,000 bars; a few minutes total. Wait for:
   `DONE TestV34Native: bars=49379 rows=49379 out=FMA3_v34_native_actual.csv (Common Files)`
4. Then tell Claude **"run the comparator"** (or it will detect the output file).
5. **If any `ROW COUNT MISMATCH` / failed line appears — stop and report that log line.**

**What a PASS proves:** cross-language (MQL5-native vs frozen pin) book parity at the 1e-12 gate over the full 6 years, *including* the MathRound/banker-tie and transcendental-ULP residuals that Stage-0 explicitly deferred to an in-terminal run — i.e., the last open numeric question of the v34 native port's signal layer.

## Overnight scoreboard

| Wave | Scope | Status | Headline measured result | Commit / ledger |
|------|-------|--------|--------------------------|-----------------|
| 1 | Scalar reference, whole v34 book (stages 3–5) | **PASS** | Assembled book vs golden: max\|Δ\| **4.197e-14**, 0 cells > 1e-12 gate; gate-engine CAGR/MaxDD/Sharpe deltas **exactly 0** | `526a426` / FMA3-RECON-7 |
| 3a | b_h account engine, scalar reference (stage 6 Python side) | **PASS (stronger than target)** | **Bitwise equal** to golden curve over all **2,948,650** 1m bars — equity and worst-mark max diff **0** | `6113ad0` |
| 2 | MQL5 native translation + harness | **READY-TO-RUN** (1 defect found + fixed overnight) | All 9 includes wine-compiled **0 errors / 0 warnings**; Python mirror of harness loop reproduces Wave-1 parity exactly | `e731398` / FMA3-RECON-8 |

### Wave 1 — scalar reference of the whole v34 book (stages 3–5) — PASS
All 8 sleeves ported as scalar-float64 one-bar steppers (`research/bpure/steppers/`), each adversarially verified (no-peek / no-hand-tune / re-run).

- **Integer-state sequences: EXACT** — 0 mismatches over the full 2020–2025 grid, every sleeve.
- **Positions vs frozen goldens** (max abs error):

| Sleeve | max\|Δ\| pos | Note |
|--------|-------------|------|
| crisis | 0.0 | bit-exact |
| trend_v2 | 0.0 | bit-exact |
| carry_breakout | 1.665e-16 | both books incl. FX carry, top-5 average-tie rank, chandelier exits — the sleeve Gemini failed on |
| meanrev | 1.887e-15 | |
| seasonal | 1.5e-15 | |
| crypto | 1.7e-16 | |
| mag_xau | 5.3e-15 | |
| intraday | 2.5e-14 | |

- **Assembled book vs golden `book.parquet`:** max\|Δ\| **4.197e-14**, 0 cells > the 1e-12 gate (132,454 / 1,530,749 cells differ at last-ulp only).
- **Gate engine** (`account_engine_1m`, EUR 10k): CAGR / MaxDD / Sharpe deltas **exactly 0** vs the full-precision pin; final **EUR 449,707.7453**.
- Doc: `model/v3/BPURE_WAVE1_RESULTS.md`.

### Wave 3a — b_h account-engine scalar reference (stage 6 Python side) — PASS, stronger than target
`research/bpure/engine/`: `BH_ENGINE_SPEC.md` (the full per-bar spec the MQL5 `V34EquityNative` will be written from) + `bh_stepper.py` (pure-Python, no numba, warm-startable).

- **Bitwise equal to the golden curve over all 2,948,650 1m bars** — equity *and* worst-mark max diff **0**.
- Metrics bit-equal to pin. Warm-start JSON roundtrip **bit-exact** (2022Q2 boundary, 1.83M-bar tail). Runtime ~2.4 min / 6y step loop.
- **Caveat (pinned, do not soften):** the record feed is float32-quantized prices upcast to f64. A live double feed is pricing-faithful but **NOT** bit-identical — bit-parity validation must replay float32-rounded prices.

### Wave 2 — MQL5 native translation + harness — READY-TO-RUN
`mt5/ea/Include/FMA3v34/`: `V34Math.mqh` (banker half-to-even round, ewm adjust=True incl. NaN-decay, Welford ewm-std, ddof=1 ring std, Donchian deque, NaN/npdiv helpers) + 8 sleeve/ensemble includes, all 1:1 from the Wave-1 steppers. All wine-compiled headless to **"Result: 0 errors, 0 warnings."**

- Harness: `TestV34Native.mq5` (a Script — **zero trading functions**) + `FMA3_v34_inputs.csv` (49,379 rows, `%.17g` bit-round-trip verified, installed in Common Files) + `validate_mql5_book.py` comparator.
- A statement-for-statement Python mirror of the harness loop (`harness_sim.py`) reproduces the Wave-1 book parity **exactly** (4.197e-14, 0 cells > 1e-12). So residual in-terminal risk is confined to the MQL5 translations themselves + the known no-fma ewm residual (~1e-16 rel) + MathRound/tanh libm ULP effects — which is precisely what the terminal run measures.
- **The defect (found by our own adversarial verifier, then fixed + reverified):** 4 wrong CAD policy-rate epoch days in `CarryBreakout.mqh` (19513/19548/20087/20129 instead of 19515/19550/20117/20159 — dates shifted, values right; measured output-neutral on this grid, but wrong constants). Fixed; re-verified the **full table (178/178 day-rate entries across 10 ccys** match the frozen `engine/costs.py` parse, 0 mismatches); reinstalled; recompiled 0/0 (fresh `TestV34Native.ex5`, 84,326 B).
- Doc: `model/v3/BPURE_WAVE2_STATUS.md` (bottom line updated post-fix).

## Context worth remembering
- This continues **your** decision: B-pure ratified (no hybrid, cost accepted), freeze-now chosen. The Antigravity/Gemini port was assessed yesterday (**measured failing at 44% of cells**) — we salvaged its harness *pattern* and wine-compile recipe, nothing else. Our port hit state-exactness on the first verified pass because the acceptance rigor was front-loaded.
- The freeze that makes all this meaningful: **`FMA3-v34-freeze-1`**, hermetic hash `5785937244cd48db…`, goldens + pin reproduced ≤1e-6.

## What remains after a PASS — Wave 3, the road to the native federated EA
1. `V34EquityNative.mqh` — port b_h from `BH_ENGINE_SPEC.md` (1m cross-margin account; the reference is now bitwise-proven).
2. `V7Sim` / a_h — fork the already-G1-proven `V7Core.mqh` to the idealized standalone account (the v7 half needs no new alpha work).
3. Blender — `static_fed(0.70)` in MQL5: `fed = f7·(w·a/j) + f34·((1−w)·b/j)`. **Standing subtlety:** the validated v3 EA *replays* a frozen fed stream; the native EA *computes the blend live* from native a_h/b_h — this architectural step needs its own gate-level validation + a fresh FMA3-RECON entry before any deploy.
4. EA integration reusing the RECON-4-validated FedExec/Guardian execution layer from `FableFederation_V3` (netting, margin cap, volume-limit cap, breaker).
5. Warm-start cert (≥2019 warm, COVID tail) + gate-level tolerance band ratification (proposed ΔCAGR ≤±1.0pp / ΔMaxDD ≤±0.5pp / ΔBreach ≤±0.5pp — **your ratification still pending**).

## Open items NOT from tonight (carry-forwards)
- **FTMO dial confirm:** s≈0.5 @ 1:100 real-tick (`FED_V3_FTMO_S05.set` staged) — you deferred it.
- **Task #19:** regenerate IC/FTMO dashboards to the final dials.
- **v2.2 context:** FMA2 roadmap schedules an 11-year re-derivation. The freeze protects the port (any churn → hash mismatch → documented re-verify), but a v2.2 landing means re-porting changed sleeves — worth keeping in mind before deploying the native v34.

## Honest risk paragraph
The in-terminal run is genuinely untested execution — we never launched `terminal64.exe`, deliberately. Compile ≠ correctness; the terminal run is the measurement. If it **fails** the 1e-12 gate, the comparator reports the first divergent (hour, symbol) and we trace it. Likeliest suspects, in order: CSV parsing edge cases; the no-fma ewm residual accumulating past 1e-12 somewhere (bounded analysis says it shouldn't); MathTanh/libm last-ULP near a trend_v2 retrade band; or a crisis banker-tie (thin margins measured — nearest tie 7.1e-5, nearest threshold 1.1e-5, both >> the expected noise, so flips are unlikely but not impossible). None of these would invalidate the reference layer — they'd localize exactly where MQL5 arithmetic diverges, which is the point of the harness.
