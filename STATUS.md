# FMA3 Status Report — 2026-07-14

## TL;DR

The native Satellite **signal** layer is proven bit-for-bit-within-gate in the real MT5 terminal over 6 years (2020–2025): owner ran `TestV34Native`, comparator vs golden book = max|diff| **4.197e-14**, 0/1,530,749 cells > 1e-12 (RECON-8b). The model is frozen (FMA3-v34-freeze-1) and reproduces the shipped pin to ≤1e-6. Still to build for the native federated EA: `b_h` (Satellite equity) → MQL5, Core standalone shadow (`a_h`), the **live** static blender, and EA integration + warm-start certification. The v7/v34 → Core/Satellite rename is behavioral- and structural-clean but sits in **PR #1, unmerged (not self-merged)**. Work is **paused** at owner's instruction to switch the working model to Fable 5 first — resume Wave 3 only on explicit go-ahead.

---

## Goal (for context)

One fully native, all-MQL5 EA (zero Python in the live loop) for the FMA3 Fable book:

| Component | Formerly | Weight | Role |
|---|---|---|---|
| **Core** | v7 | 0.70 | band-allocation engine |
| **Satellite** | v34 | 0.30 | tactical alpha-sleeve ensemble |

Owner ratified the **"B-pure"** architecture (all-MQL5) over a Python-hybrid alternative, accepting a ~28–40 dev-day cost.

---

## Done (this session — all pushed to github.com/denissalamanca/FMA3, public)

| # | Item | Verified result |
|---|---|---|
| 1 | **Model frozen** — FMA3-v34-freeze-1 (hermetic hash `5785937244cd48db…`) | Reproduces shipped pin to ≤1e-6: CAGR 0.8865880763, €449,707.7453, MaxDD 21.67%. Source-of-truth landmines resolved (1.21×-hot renorm helper confirmed off-path; gold cap derived 1.80, not hardcoded). |
| 2 | **Stage 0 (kill-switch) GREEN** | (a) Feed-provenance: frozen pin feed byte-identical to live IC 1m feed → IC feed-divergence risk = 0 by construction (assessment's "~8pp Duka divergence" was a different vendor). (b) Numeric kill-switch: hand-rolled scalar float64 reproduces pandas `ewm(adjust=True)`+`ddof=1` to ~1e-14; integer states exact. |
| 3 | **Wave 1** — all 8 Satellite sleeves ported as scalar-float64 one-bar steppers (`research/bpure/steppers/`) | Each adversarially verified; integer-state-sequence EXACT vs frozen goldens over full 2020–2025 grid. Assembled book max|diff| **4.197e-14** (0 cells > 1e-12); gate-engine deltas EXACTLY 0.0 vs pin. First-pass pass came from front-loaded acceptance rigor — the parallel Antigravity/Gemini all-MQL5 attempt measured FAILING at 44% of cells; only its wine-compile harness pattern was salvaged. |
| 4 | **Wave 3a** — `b_h` engine scalar reference (`research/bpure/engine/BH_ENGINE_SPEC.md` + `bh_stepper.py`) | Bitwise-equal to golden curve over ALL **2,948,650** 1-minute bars (equity AND worst-mark, diff 0); warm-start bitwise. Caveat: record feed is float32-quantized — a live double feed is pricing-faithful but not bit-identical. |
| 5 | **Wave 2** — full MQL5 native translation (`mt5/ea/Include/Sat/` + `Core/` + `Book/`, incl. banker's-rounding emulator) | Wine-compiled 0 errors / 0 warnings. Owner ran `TestV34Native` in the real MT5 terminal → comparator vs golden book = max|diff| **4.197e-14**, 0/1,530,749 cells > 1e-12. Closed the last deferred numeric question (MathRound banker-tie + transcendental-ULP residuals — measured negligible). Ledger **RECON-8b**. Native MQL5 reproduces the shipped Satellite SIGNAL layer bit-for-bit-within-gate over 6 years, in-terminal. |
| 6 | **Nomenclature** — full internal rename v7/v34 → Core/Satellite (`NOMENCLATURE.md`; `model/v3/RENAME_REPORT.md`) | QA'd two ways: **structural** (every code file forward-maps main→branch with line_delta 0 → 0 source-logic changes) + **behavioral** (book 4.196643e-14 identical, b_h bitwise-0 over 2.9M bars, harness 4.197e-14, MQL5 recompile 0/0). Zero numbers moved. |

---

## In-flight

- **PR #1** (https://github.com/denissalamanca/FMA3/pull/1) — the nomenclature rename. Open, **awaiting owner review + merge. NOT self-merged.**

---

## Remaining (Wave 3 — the road to the native federated EA)

| # | Task | Notes |
|---|---|---|
| 1 | **`SatEquityNative.mqh`** — port `b_h` to MQL5 | From the bitwise-proven `BH_ENGINE_SPEC` (296-line 1m cross-margin account). Proven reference exists. |
| 2 | **CoreSim / `a_h`** — standalone-account shadow | Fork the already-G1-proven `CoreEngine.mqh` (formerly V7Core, proven to the cent) to an idealized standalone-account shadow. No new alpha work. |
| 3 | **`static_blend` live blender in MQL5** | `fed = f_core·(w·a/j) + f_sat·((1−w)·b/j)`, w=0.70. **Architecturally new step + the main remaining risk:** the shipped/validated v3 EA REPLAYS a frozen fed stream; the native EA COMPUTES the blend live from native a/b shadows → needs its OWN gate-level validation + a fresh RECON entry before any deploy. |
| 4 | **EA integration** | Reuse the RECON-4-validated BookExec/Guardian execution layer (netting, balance sizing, margin cap, volume-limit cap, FTMO breaker). |
| 5 | **Warm-start certification** | ≥2019 warm, COVID tail + owner ratification of the gate-level tolerance band (proposed below). |

---

## Dials / deployment

| Account | Dial | Status |
|---|---|---|
| **IC** | s = **1.6** | COMMITTED. Real-tick confirmed, min ML 120% at 1:30, 0 rejects. |
| **FTMO** | s ≈ **0.5** @ 1:100 | Recommended, but **real-tick run pending** (owner deferred). |

Physical constraints already characterized: friction, `SYMBOL_VOLUME_LIMIT` (binds >~€2M/s on one retail account), broker margin.

---

## Open owner decisions / items

- **Merge PR #1.**
- **Ratify the gate-level tolerance band** — proposed: ΔCAGR ≤ ±1.0pp / ΔMaxDD_worst ≤ ±0.5pp / ΔBreach ≤ ±0.5pp.
- **v2.2 sequencing risk** — the FMA2 roadmap schedules an 11-year re-derivation (v2.2). The freeze protects the port (any sleeve churn → hash mismatch → documented re-verify), but if v2.2 lands, changed sleeves must be re-ported. Owner chose "freeze current book now" — worth re-confirming timing before sinking the full Wave-3 build.
- **Task #19 (open)** — refresh IC/FTMO dashboards to the committed dials.
- **FTMO real-tick dial confirmation.**

---

## Risk note (honest)

Almost everything shipped this session rests on a proven reference: the Satellite signal layer is verified bit-for-bit-within-gate in-terminal over 6 years, `b_h` is bitwise-equal over 2.9M bars, Core is proven to the cent, and the execution layer is RECON-4-validated. The **one genuinely-new architectural step is the live blender** (Remaining #3): the shipped/validated v3 EA replays a frozen federated stream, whereas the native EA will compute the blend live from native Core/Satellite shadows. That path has no prior validation and carries its own gate-level risk — it must clear its own gate check and a fresh RECON entry before any deploy. The `b_h` float32-quantization caveat (live double feed is pricing-faithful but not bit-identical) and the unconfirmed FTMO real-tick dial are the remaining known unknowns.

---

## Current pause

Owner explicitly paused before Wave 3 to switch the working model to **Fable 5** first. **Resume only on explicit go-ahead.**
