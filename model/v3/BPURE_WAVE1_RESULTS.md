# B-pure Wave 1 results — scalar reference steppers (stages 3–5), full-book parity + gate

**Scope.** This document synthesizes the measured results of **Wave 1** of the
B-pure port: **stages 3–5 of the staged plan** (`B_PURE_STAGE0_RESULTS.md` §7)
executed at the **scalar reference level** — pure-Python, bar-by-bar,
scalar-float64 stepper modules for **all 7 shipped sleeves + the `mag_xau`
overlay**, assembled into the full ensemble book and driven through the engine
of record. Everything below is validated against the frozen goldens of
**FMA3-v34-freeze-1** (freeze_hash `fc14159f5352d685…`, config_hash
`48c09199fbf83d82`; ledger FMA3-RECON-5).

- Steppers: `research/bpure/steppers/` (7 sleeve steppers + `ensemble_stepper.py`)
- Validators + result JSONs: `research/bpure/parity/`
- Golden targets: `model/v3/freeze/FMA3-v34-freeze-1/golden/` (8 `*_pos` parquets + book + curve)
- Grid: 49,379 hourly bars, 2020-01-02 00:00 → 2025-12-31 23:00; 31 book symbols
- Env: py 3.13.12 / pandas 2.3.3 / numpy 2.4.2 (pandas only in the *validators*; the steppers themselves are scalar)

**Verdict up front: Wave 1 PASS.** All 7 steppers are position-parity ≤2.5e-14
vs golden with **exact** integer/state sequences and 0 mismatches; the
assembled book is ≤4.20e-14 vs the golden book with **0 cells over the 1e-12
gate**; the full gate run through `account_engine_1m` reproduces the pin to
**full precision** (ΔCAGR = ΔMaxDD = ΔSharpe = 0.0; ΔFinalEUR = 5.8e-11). Each
stepper's parity was independently confirmed by a verifier pass (7/7
`confirmed: true`).

---

## 1. Per-sleeve parity table

One stepper per row; `consolidate_p1c` is a single stepper covering **two**
golden sleeves (seasonal + crypto_smart). "State exact" = the full
integer/hysteresis state sequence bit-matches the frozen pandas reference, with
the mismatch count in parentheses. "Pos maxabs" = max |stepper − golden| over
every (hour, symbol) cell of the sleeve's golden `*_pos` parquet.

| Stepper | Golden sleeve(s) | Continuous max err | State exact (mismatches) | Pos maxabs vs golden | Warm-start | Verifier |
|---|---|---|---|---|---|---|
| `crisis_stepper` | crisis | 1.11e-13 (rel, `vr`; most quantities ≤1.5e-15, `dd`/`s_eq`/`w` exact) | YES (0 of 10,941 checks / 1,563 daily bars) | **0.0 (bit-exact)**, 197,516 cells | roundtrip identical | CONFIRMED |
| `trend_v2_stepper` | trend_v2 | **0.0** (all four quantities exact) | YES (0; move-flag + held both bitwise) | **0.0 (bit-exact)**, 246,895 cells | bitwise roundtrip | CONFIRMED |
| `carry_breakout_stepper` | carry_breakout | **0.0** (vol30 / ATR / carry weights exact; 2,080 carry days) | YES (0, breakout + carry both) | 1.67e-16 (1 ulp; see §3 flag 2) | n/a-noted in validator | CONFIRMED |
| `consolidate_p1c_stepper` | seasonal + crypto_smart | 4.47e-15 rel (worst: `BTCUSD_ma`; abs 3.6e-10 on ~$60k prices) | YES (0 of 6,243 rows, 3-state hysteresis) | 1.50e-15 (seasonal/XAUUSD; crypto ≤1.7e-16) | roundtrip 0.0 | CONFIRMED |
| `meanrev_stepper` | meanrev | 7.99e-10 (`z`; all other quantities ≤3.4e-15) — largest continuous residual in Wave 1, still 12× under the 1e-8 primitive bar and absorbed to 1.9e-15 in positions | YES (0) | 1.89e-15 | roundtrip 0.0, exact | CONFIRMED |
| `mag_xau_stepper` | mag (overlay) | 3.40e-15 rel (`ann`; mid/near/dist exact) | YES (0; sig + near both 0) | 5.33e-15 | tail roundtrip 0.0 | CONFIRMED |
| `intraday_stepper` | intraday | 2.89e-14 rel (`vol30_hourly`) | YES (0 of 98,758 bar states; day-set + clip-state 0) | 2.50e-14 (Wave-1 worst sleeve) | resume 0.0 | CONFIRMED |

All 7 steppers: **0 state mismatches anywhere, 0 position cells over the 1e-12
per-cell gate, 0 NaN-pattern mismatches**, and every warm-start
(get_state/set_state → tail re-run) round-trip reproduced the cold run exactly.
Sanity anchors: crisis/trend_v2/meanrev/intraday/mag each re-verified the
in-repo pandas reference against the golden parquet at maxabs 0.0 before
comparing the stepper, so the goldens themselves are confirmed live-equal.

## 2. Full book + gate vs the pin

`ensemble_stepper.py` assembles the 7 sleeve steppers with the frozen
provenance constants (V2_CAPS 7-sleeve weights, SCALE = 10.0, MAG_W = 0.05,
gold cap **derived** 1.80 — both RECON-5 source-of-truth landmines re-confirmed;
frozen `ensemble.py` sha `c0c6e441…` verified byte-equal to live).

| Check | Result |
|---|---|
| Book maxabs vs golden book | **4.196643e-14** |
| Cells differing at all (last-ulp) | 132,454 / 1,530,749 (8.65%) |
| Cells over the 1e-12 gate | **0** |
| First divergent cell | 2020-01-06 02:00 XAUUSD, 1 ulp (…7142 vs …7144), attributed to seasonal |

**Gate (engine of record: `account_engine_1m`, EUR 10k, 1m worst-mark) on the
assembled stepper book:**

| Metric | Stepper book | Δ vs pin (full-precision source) | Δ vs 4dp-quoted pin constants |
|---|---|---|---|
| CAGR | **0.8865880762592069** | **0.0** | −4.1e-11 |
| MaxDD_worst | **0.2167488591051508** | **0.0** | +5.2e-12 |
| Sharpe | 1.8543172985943566 | **0.0** | −4.1e-10 |
| Final EUR | **449,707.7452664526** | +5.82e-11 | −3.355e-05 |
| Neg years / neg quarters | 0 / 1 | match | match |

Full-precision pin source:
`/Users/dsalamanca/vs_env/FableMultiAssets2/research/outputs/v34_s10_pin_1m.json`.
**Gate: PASS.** Against the full-precision pin the reproduction is exact to the
last representable digit; the −3.4e-05 EUR delta appears **only** against the
4-decimal-place *quoted* constant (449707.7453) and is purely the quoting
precision of that constant, not a model difference (RECON-5 accepted the same
freeze at Δ3.4e-5 for the identical reason).

## 3. Honest flags — everything not exact or not fully verified

1. **Stretch target of 0 nonzero book cells NOT met.** 132,454 of 1,530,749
   book cells differ from golden at last-ulp level (max 4.20e-14; 0 over the
   1e-12 gate). Inherited from the sleeves' own ≤2.5e-14 residuals (crisis 0,
   trend_v2 0, carry 1.7e-16, crypto 1.7e-16, seasonal 1.5e-15, meanrev
   1.9e-15, mag 5.3e-15, intraday 2.5e-14). Benign — the gate deltas above are
   0.0 — but the book is *not* bit-identical.
2. **carry_breakout 1-ulp associativity residual.** pos_maxabs 1.67e-16 comes
   from the gross-cap sum order: the stepper sums |pos| in FX-then-BK_UNIV
   order, the frozen pandas sums in core.ALL column order; worst bar (US30
   2023-07-13 16:00) has golden gross = 3.000000000000001 with the cap
   binding. 4 orders under the gate; informational.
3. **carry dc-index validator hole (closed by hand).** The validator would
   silently skip dc-index days the stepper never stamped; coverage was
   independently verified complete — 2,081 grid days = 2,081 dc rows, all
   2,080 stampable days stamped and matched exactly, the final day
   unstampable by construction and unable to affect positions.
4. **carry policy-rate re-freeze edge.** The frozen `_policy_rate_daily`
   clips rates to a 2019-12-01…2025-12-31 `date_range`; the stepper uses an
   unbounded step-table lookup. Equivalent on this grid (starts 2020-01-02) —
   a future re-freeze with earlier data must re-check this edge.
5. **meanrev `z` at 7.99e-10** is the largest continuous residual in Wave 1
   (all else ≤1.1e-13). Under the 1e-8 primitive bar and fully absorbed by
   the position quantization (pos 1.9e-15, states exact), but worth knowing
   it is 4+ orders noisier than every other quantity.
6. **Crisis threshold margins are thin** (measured min distances to a state
   flip: |fvr−1.20| = 1.9e-5, |flev−fma| = 1.1e-5, grid-tie = 7.1e-5,
   |dd+0.05| = 7.8e-5). Irrelevant at ~1e-13 scalar residuals, but these are
   the exact cells where Wave 2's in-terminal MathRound/ULP risk (Stage-0
   R1/R1b) can flip a state — the in-terminal replay must watch them.
7. **dFinalEUR vs the 4dp-quoted pin constant is −3.355e-05, above 1e-9** —
   quoting precision of the constant only (see §2); the full-precision delta
   is 5.8e-11.

## 4. What this proves — and what it does not

**Proves.**
- **The scalar reference IS the MQL5 spec.** Every sleeve of the shipped book
  is now expressed as an explicit bar-by-bar scalar recurrence — no pandas, no
  vector semantics — that reproduces the frozen golden to ≤2.5e-14 positions,
  **exact** state sequences, and an **exactly pin-matching** gate. This is the
  line-by-line document a `.mqh` translation is written against.
- **Stages 3–5 logic is complete at reference level.** The front block
  (seasonal, mag_xau, intraday, crisis), the state-machine sleeves
  (crypto_smart, meanrev, trend_v2), and carry_breakout (full Donchian ×11×2 +
  policy rank + ties, **exact — no approximation**, so the "~100% behavior"
  claim stands) all pass their stage go/no-go criteria (state parity +
  warm-start), and the ensemble assembly (weights, gold cap, gross cap,
  mag overlay) is verified end-to-end through the gate.
- **Warm-start machinery works** at reference level: every stepper serializes
  and resumes bit-/0.0-identically mid-grid.

**Does NOT prove.**
- **No MQL5 exists yet.** Nothing has been translated, compiled, or executed
  in a terminal; Wave 1 is Python-only.
- **No `b_h` engine.** The account/margin/1m-intrabar engine (stage 6) is
  untouched; the gate above still runs on the *Python* `account_engine_1m`.
- **No in-terminal MathRound/ULP confirmation.** Stage-0's R1 (half-away vs
  banker's rounding on the crisis 0.02 grid + mag $100 magnet), R1b
  (tie-straddle-via-ULP), and transcendental last-ULP risks are *not*
  measurable on this Mac and remain open until the Wave-2 in-terminal replay —
  flag 6 lists exactly where the margins are thinnest.
- **No warm-start certification against real ≥2019 warm data** (stage 7; the
  COVID cold-start k≈4.7 record artifact is still un-re-certified).
- Wave 1 says nothing new about friction, margin, volume limits, or
  deployability — those remain governed by FMA3-RECON-4 and the
  reconciliation criterion.

## 5. Wave 2 plan — MQL5 translation + in-terminal replay

1. **Per-stepper `.mqh` translation.** One MQL5 include per stepper, written
   mechanically against the scalar reference (same variable names, same
   recurrence order, same summation order — flag 2 shows order matters at the
   ulp level).
2. **Wine compile** on this Mac (MetaEditor CLI under wine) for syntax/type
   verification; no tester runs are trusted from wine.
3. **In-terminal replay harness, Gemini-pattern, with CORRECT inputs.** Port
   the replay-harness pattern from the FableMultiAssets3-Gemini repo
   (read-only reference): the terminal-side harness is driven from the
   **frozen golden parquets' input series exported as CSV** — not from broker
   history — so the MQL5 stepper consumes byte-identical inputs and every
   divergence is attributable to MQL5 arithmetic (MathRound, transcendentals,
   ULP ties), not to feed differences. Acceptance per sleeve: state sequence
   exact vs golden; positions inside the owner-ratified band; explicit report
   on the flag-6 thin-margin cells.
4. **Kill criteria carried over from Stage-0:** a systematic MathRound
   grid-flip or a transcendental divergence that breaks state parity fires
   the same investigate-then-decide path — no silent band-widening.

## 6. Wave 3 plan — engine + integration

1. **`b_h` native engine** (stage 6): port `account_engine_1m` (31-symbol
   cross-margined, 1m intrabar worst-mark); parity target =
   `v34_book_equity_1m.parquet` golden export (**still to be produced** —
   owner-input item from Stage-0).
2. **V7Sim / `a_h`**: the v7 side of the federation at the same reference →
   native discipline.
3. **Blender**: the static_fed(0.70)×s federation of `model/v3` — must REPLAY
   the unified fed_frac (stable-model-v3 rule: a/j, b/j frozen native curves;
   compute-live diverges at s≠1).
4. **EA integration + full Strategy-Tester regression** (stage 8), then the
   mandatory 6-gate reconciliation under a new FMA3-RECON-N entry for the
   resulting `.ex5` hash — a Wave-1/2/3 parity pass never substitutes for
   Gates 5–6.

---
*Measured 2026-07-14 on freeze FMA3-v34-freeze-1 (`fc14159f…`), py 3.13.12 /
pandas 2.3.3 / numpy 2.4.2. Engine of record: `account_engine_1m`, EUR 10k, 1m
worst-mark. Result JSONs: `research/bpure/parity/*_parity.json` (7 sleeves) +
`book_parity.json` (book + gate). Ledger: FMA3-RECON-7.*
