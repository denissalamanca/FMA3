# Antigravity (Gemini) Brain2 MQL5 port — assessment & comparison vs the FMA3 B-pure staged plan

**Date:** 2026-07-14. **Assessed:** `/Users/dsalamanca/vs_env/FableMultiAssets3-Gemini` (read-only) via 4-lens measured dissection (workflow `wf_9d639ef7-11a`: parity-state, numerics, book-fidelity, system-completeness). Every claim below marked *measured* was produced by running code/diffs during the assessment, not read from the handover.

---

## 1. Headline

Antigravity independently converged on the **same architecture** the FMA3 campaign ratified for B-pure: causal one-bar steppers, a Python-stepper intermediate, and cross-language diffing against a pandas ground truth. That is genuine, independent validation of the approach. **But the handover's endpoint claims are not achieved**: the only recorded master cross-language parity run **fails at max|Δ| = 1.89 position units with 44.4% of all 1.53M cells differing >1e-6** (*measured* — I ran their own `validate_master_parity.py`), driven not by float noise but by **three structural omissions and three sprung numerics traps**. Roughly: **~40% of the handover verified, ~25% plausible-but-unverified, ~35% contradicted** (*measured*).

## 2. What Antigravity got right (real credit)

- **The harness aims at exactly the right book** (*measured*): their `master_expected.parquet` (49,379h × 31 symbols, full 2020–2025 pin grid) is **bit-identical to our frozen golden `book.parquet`** (0 of 1,530,749 cells differ). Generated from the real FMA2 `build_book` — not a re-derivation. (By timing luck, not by pin — see §4 governance — but correct today.)
- **6 of 8 Python validators import the true FMA2 sleeves** (quoted imports verified); 3 of them re-run by us pass at ≤5e-9 (meanrev 4.8e-9, trend_v2 0.0, intraday 2.5e-14) (*measured*).
- **`Math.mqh` CEWMMean is a genuinely correct pandas `adjust=True`/`ignore_na=False` port** — decays weight through interior NaN exactly like pandas (*code-verified*). `ddof=1` respected everywhere rolling std is used; `min_periods` gated on nobs; Donchian uses the prior window (shift(1) trap avoided); **MagXau even hand-implements a banker's-rounding emulator**.
- **Avoided the renorm landmine**: RAW V2_CAPS × 10, no ÷0.826; gold cap 1.80 with the correct overnight window; meanrev/crypto constants match the frozen sleeves (*code-verified*).
- **Working wine-compile + terminal-replay pipeline**: `TestBrain2.ex5` compiles 0/0 (verified in compile.log) and runs in the terminal writing `master_actual.csv` — a functioning **in-terminal cross-language test harness**, which is exactly the artifact class FMA3's Stage-0 flagged as still needed (MathRound/transcendental confirmation).
- **Breadth**: all 8 sleeves attempted in MQL5 within ~3 days, with real edge-case discoveries (missing-bar rollover, calendar-day windowing) that are genuinely the right problems.

## 3. What is broken (all *measured* or *code-verified*)

**Master parity is failing, structurally.** `validate_master_parity.py` on the artifacts on disk: max|Δ| 1.8934 (XAUUSD), 680,152/1,530,749 cells >1e-6 (44.4%), 30/31 symbols failing (only SOLUSD passes), uniform across all six years (34–49%/yr — not a warmup artifact). Seven FX crosses differ by **exactly 1.100 = the full meanrev cap (0.11×10)** — whole-sleeve state divergence.

Causes found in source:
1. **Managed-cross hard cap 10× too loose**: `m_cross_cap = 0.5 * m_scale` = 5.0 vs the frozen **absolute 0.5** post-scale. Golden binds this cap 20–25% of all hours on EURCHF/EURSEK/EURNOK/AUDNZD; their output reaches |1.1|.
2. **The FX carry book is entirely missing**: `carry_breakout` ported breakout-only — no policy-rate carry, no W_CARRY=1.35/W_BK=2.05, no sleeve gross cap, no clip(±1) — and the breakout stepper is wrongly instantiated on 10 carry-only FX symbols the true breakout book never trades (63% of bars differ on USDJPY).
3. **Sleeve GROSS_CAP 3.0 unimplemented** for meanrev (binds 36.4% of hours in the shipped sleeve) and carry (9.6%). Their per-symbol stepper architecture cannot compute a cross-symbol gross; their own validator comments "Do not apply GROSS_CAP for this component test!".
4. **MeanRev driven by the wrong vol**: harness injects 60-day realized vol; the frozen sleeve is `VOL_SPAN=30`. Enters both the frozen-at-entry sizing **and** the index-leg z denominator → **entry/exit states flip**, not just sizes.
5. **Crisis sleeve springs both proven traps**: its stress smoothers use the banned `adjust=False` EWM recursion (divergence window lands on COVID onset), and its 0.02-grid snap uses `MathRound` (half-away) vs numpy banker's — the documented systematic tie bias on the gate-dominating sleeve.
6. **TrendV2 leaks look-ahead**: on missing bars it returns `m_scheduled_pos` — the *next* day's not-yet-effective target — up to a day early.
7. **Day-universe wrong in both directions**: python daily windows include ffilled weekend/holiday rows (calendar days); their MQL5 suppresses them for trend/meanrev (trading days, ~40% longer horizons) while MagXau receives an always-1 `day_valid` and appends stale weekend closes the real sleeve drops.
8. **Two of eight "validated" sleeves are self-referential**: seasonal and crypto_smart expecteds are generated by Gemini's *own* steppers, never compared to the FMA2 pandas. Independently replayed, their seasonal Python stepper diverges from the frozen golden sleeve by up to **1.0 position unit on 12.8% of hours** (67 of the 70 worst on Saturdays).
9. Minor but real: seasonal annualizes with 365.0 vs core's 365.25; naive `m2−m²` EWMStd (cancellation-class) on two paths; debug `Print` statements in production includes; the handover's "45 symbols" appears nowhere in the repo (37 in / 31 out).

**Staleness caveat (fairness):** `master_actual.csv` (00:17) predates two uncommitted `.mqh` edits (00:40, never compiled or run). Those edits cannot fix #2/#3 (missing components in both languages) but might address others — unverifiable without a terminal re-run.

## 4. What the plan doesn't cover (vs the FMA3 goal)

- **Federation: absent.** Zero hits for `static_fed`/`fed_frac`/`a_h`/`b_h` in Gemini-authored code. The plan builds a **standalone Brain2 EA** — no w=0.70 blend, no native-equity shadows, no shared-symbol netting. Ironically, the complete FMA3 federation stack (FableFederation_V3 + FMA3v3 includes + V7Core.mqh + 25 presets) sits **byte-identical and unreferenced** inside their own repo copy.
- **Brain 1 misconceived**: Phase 3 targets "sleeves in `FableMultiAssets1/research`" — a repo that **does not exist**; v7 is a path-dependent band/seed-chain machine with no sleeves, and its MQL5 stepper (V7Core, G1-proven to the cent) is already done.
- **No gate-level acceptance**: validation is a 1e-6 position diff only — no integer-state-sequence check, no `account_engine_1m`, no worst-mark MaxDD, no breach bootstrap, no warm-start/COVID plan. The campaign has *measured* why that bar is insufficient (1e-9 upstream → +0.81pp gate CAGR via persistent state flips).
- **Execution EA unstarted** (no `mt5/Experts/`), and its 4-line spec omits netting, margin, volume-limit caps, rejects, lot-step, swap, breaker, dials, recon ledger — all already implemented + RECON-4-validated in FableFederation_V3.
- **No governance**: no freeze, no hash pin, no ledger; the parity target is regenerated live from the churning FMA2 tree and equals the frozen book **by timing luck of the copy date** (post s11→s10).

## 5. Pros / cons

| | **Antigravity port** | **FMA3 staged B-pure plan** |
|---|---|---|
| **Pros** | Right target book (bit-identical expected); right architecture (converged independently); breadth — all 8 sleeves attempted fast; correct CEWMMean/ddof=1/min_periods/Donchian core primitives; MagXau banker's emulator; avoided renorm trap; **working wine-compile + in-terminal replay harness**; real edge-case discoveries | Freeze-first governance (hermetic hash, golden parquets, RECON ledger); acceptance = state-sequence exactness + gate-level engine re-run (the *proven-necessary* bar); every claim adversarially verified (2/7 sleeves at **0/6243 state mismatches, gate Δ=0**); primitives at 1e-14; feed-provenance settled (IC=0); federation/v7/execution already built + validated (RECON-4); measured tolerance band ready to ratify |
| **Cons** | Master parity **failing 44.4%** with whole-sleeve flips; carry book missing; gross caps missing; cross cap 10× loose; wrong meanrev vol; crisis springs adjust=False + MathRound traps; TrendV2 look-ahead; 2/8 validators circular; no state/gate acceptance; no federation/brain-1/execution/governance; handover overstates ("achieve parity", "1e-8 every sleeve", "45 symbols") | Slower breadth by design (2/7 sleeves so far); ~28–40 dev-day full-port estimate; carries the same in-terminal residuals (MathRound/ULP) — though it *identified* them in advance rather than shipping them |

## 6. Recommendation

**Continue the FMA3 staged plan as the trunk. Do not adopt the Gemini port as a base. Salvage four specific assets from it:**

1. **The in-terminal test-harness pattern** (`master_inputs.csv → TestBrain2.mq5 → master_actual.csv` + the wine-compile automation). This is exactly the vehicle FMA3 Stage-0 still needs for the MathRound/transcendental in-terminal confirmation — adopt the pattern (regenerating inputs from the frozen cache with the **correct 30d meanrev vol**), not their stepper code.
2. **Their bug discoveries as test cases**: missing-bar rollover, calendar-vs-trading-day windows, the injected-vol pitfall — encode each as an explicit parity test in stages 3–5.
3. **`Math.mqh` CEWMMean as a cross-check reference** (it is independently correct) — never as the only implementation; our 1e-14-validated scalar recurrences remain the spec.
4. **The failure catalogue itself**: every one of their divergences is a concrete demonstration of why the FMA3 acceptance bar (frozen golden parquets + state-sequence exactness + gate-level re-run + freeze governance) exists. Their strongest sleeves (crisis/trend_v2 "0.0 recorded") still carry sprung traps in source — proof that recorded position parity on thin windows is not fidelity.

**What their speed honestly signals:** raw sleeve translation is fast (~days, not weeks). The FMA3 28–40-day estimate is dominated by the *acceptance rigor* they skipped — and their current 44%-failing parity chase is a live demonstration of where the time actually goes when that rigor is deferred rather than front-loaded.

---
*Measured artifacts: master parity run (their validator, their data), golden-vs-expected bit-diff, per-sleeve replays vs frozen goldens, source quotes for every trap. Full lens outputs: workflow `wf_9d639ef7-11a` journal.*
