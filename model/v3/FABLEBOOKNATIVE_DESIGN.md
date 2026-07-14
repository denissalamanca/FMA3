# FableBookNative — build-and-decide design (the live-computing native Fable book)

**What this is.** `FableBookNative.mq5` computes `f_core` / `f_sat` / `a` / `b` **live each
bar** from synchronized multi-symbol 1m data and blends them into `book_frac[33]`, replacing
the frozen-CSV replay in the current `FableBook.mq5`. Every component is already built and
terminal-proven **on frozen replay inputs** (f_sat 4.197e-14; b bitwise over 2,948,650 bars;
a bit-equal 32/32 segments *scalar*; blend bit-exact). The **only un-golden step** is
computing those inputs live from a multi-symbol feed instead of reading a precomputed stream.

**Synthesis of four dissection lenses:** Wiring (`FABLEBOOKNATIVE_WIRING_LENS1.md`),
Data-path (crux), Warm-start (`WARMSTART_DESIGN.md`), Gate+Exec. Facts are labelled
**[VERIFIED]** (read in the cited source), **[INFER]**, or **[RISK/OPEN]**. This is a DESIGN
doc: it specifies what to build and what the owner must decide. No MQL5 is written here.

---

## ⬥ FABLE REVISION v2 (2026-07-14) — decisions replacing options

This revision resolves the adversarial review's three blocking findings and corrects one
stale claim. Where v2 conflicts with the original text below, **v2 wins**.

1. **`f_core` source: RESOLVED by measurement (S0, 2026-07-14) — better than either option.**
   S0 found the frozen parquet's actual producer (`engine/v7_bridge/extract_positions.py`
   L850–860): **`f_core[net] = net_lots(ffilled, seam-carry) × contract × mid_close × eurq
   / book_eqc`** — every quantity CoreSim already tracks. Implemented as
   `CCoreBookSim.ComputeFCore()` (CoreSim.mqh, compiled 0/0) + python reference:
   **bit-equal 0.0 on ALL 8 columns over the full 49,355-row frozen grid**, and the
   MQL5-algorithm python twin also 0.0 across all 32 chained segments. The earlier
   hypotheses were both wrong and are measured dead: naive `tgt` passthrough 1.08–18.2
   max|diff| (lot rounding + rebalance band + margin cap + denominator basis), equity-weighted
   netting 17.2. **The `CCoreSignal` CoreEngine refactor is DELETED from the plan** — no
   CoreEngine.mqh dissection needed; one engine (CoreSim) yields `f_core` *and* `a`.
   Remaining for this piece: the MQL5-language-layer isolation run (`CheckFCore.mq5`,
   staged; needs the ~3.5 GB segment bundles re-exported — fold into the S1 terminal batch).
2. **CoreSim streaming wrapper: DON'T BUILD IT.** The review found `FinishSegment`'s
   bfill-of-first-in-segment-eqc is a **leading-edge lookahead a forward streamer
   structurally cannot compute** — so a "bit-exact incremental streaming `a`" is impossible
   by construction, and chasing it would burn effort on a false target. Resolution by gate:
   - **R1 (frozen-input replay): use the proven segment-batch path verbatim** — full segments
     are available offline, so the exact frozen semantics (incl. the bfill) reproduce for free.
     Nothing new to build for the primary gate.
   - **LIVE / tester: incremental `eqc` with hold-at-segment-cap** until a leg's first bar,
     plus **explicit `a_h` leading-edge divergence telemetry** (32 segment edges over 6y,
     bounded, falls under the ratified band like every other feed effect). Live can never
     know the frozen bfill value at those minutes — this divergence is *structural*, so we
     measure it instead of pretending to eliminate it.
3. **Stale review claim corrected:** CoreSim `a` **does** have in-terminal MQL5 evidence —
   RECON-8d (2026-07-14 16:22): TestCoreSim 32/32 segments bitwise, final eqc
   `532229.8433634703` exact. What remains open is only the **live/hourly access path**
   (item 2 above), not the engine. Original stage S1 ("write the missing exporter") is
   **already done** and is removed from the plan.
4. **Stage order inverted: the multi-symbol feed probe is now S0** (the review is right that
   the original plan back-loaded the product-viability question). The probe tests **both
   modes** — the 1m-OHLC tester *and* a live chart — because tester multi-symbol failure
   would NOT imply live failure; the deploy target is live `CopyRates`. Probe spec: on the
   BTCUSD M1 clock, pull the 33 book symbols + EUR crosses; check M1 history depth to 2020
   per symbol; reproduce one known week's union grid + `has_bar` mask against the golden
   union. **Named fallback if the tester mode fails:** historical certification stays on the
   six-field frozen engine (already the MaxDD plan), R2 gets measured on a demo-forward run
   instead of a tester backtest, and the EA remains deployable.
5. **Feed-assembler requirements added** (review issues, now binding): (i) in R1 mode the
   assembler must **float32-quantize prices exactly as the exporter** (BH_ENGINE_SPEC §7) or
   b's bit-parity is unreachable; (ii) the live `g_fedTgt` writer must reproduce the
   exporter's **flatten-by-omission / `__GRID__` emission semantics** at the seam; (iii)
   **keep `eqw`/margin in the live hot path** with alerting — dropping them is safe only
   in-sample; a real stop-out on a divergent live feed must be detectable; (iv) log per-hour
   **`a_h`/`b_h` drift telemetry** in S4 — these two scalars are the blend's only live inputs,
   so their feed-drift directly re-weights the book; (v) **refuse-to-trade on any
   `j`-splice discontinuity** + replace the 4-decimal `SaveState` with a **≥12-sig-digit
   atomic state serializer** (a re-based `a`/`b` passes every self-check while silently
   mis-weighting every trade — this is the highest-severity silent failure in the design).

**Revised stage plan (replaces §6):**
- **S0 — feed probe (both modes) + `CCoreSignal` refactor start.** Go/no-go on the probe.
- **S1 — R1 WHOLE-BOOK GATE:** `TestBook` on frozen six-field bundles → `book_frac[33]` vs
  golden (segment-batch `a`, proven paths only). *The crown gate, tester-independent.*
- **S2 — seam + execution on frozen `g_fedTgt`** (RECON-4 position-level reproduction).
- **S3 — tester run (feed mechanics + position fidelity + R2 measured)**, with the ratified
  band as acceptance and the a_h/b_h telemetry from item 5(iv).
- **S4 — warm-start blob + FMA3-RECON-9-WS** state-diff certification.
- **S5 — crisis real-tick cross-check + demo-forward (owner decision) → RECON-9.**

---

## 0. The one-paragraph architecture

Attach to an M1 24/7 clock chart (BTCUSD, as `FableBook.mq5` L21). **Three clocks**
[VERIFIED Lens 1]. Each **M1**: assemble a synchronized six-field union row and advance the
two shadow-equity engines — `b`=`SatEquityNative.Step(...)` and `a`=`CoreSim` streaming — on
the **held** prior-hour targets, then `FED_Reconcile()` re-sizes off `ACCOUNT_BALANCE`. Each
**H1** (for the just-closed hour, applied at the next open, matching the model's causal lag):
run the `harness_sim` ffill/daily-queue loop → 8 sleeve rows → `Ensemble.Step`=`f_sat[31]`;
get `f_core[8]`; sample `a_h=a/a_first`, `b_h=b/b_first`; `BookBlend.Step`→`book_frac[33]`;
remap MODEL→broker names into `g_fedTgt[33]`. **Everything downstream of `g_fedTgt` is
verbatim RECON-4-proven execution.** The genuinely new code is: the CoreSim streaming
wrapper + its in-terminal exporter (the least-proven seam), the `f_core` compute-only source,
the M1 multi-symbol feed assembler, and the H1 ffill/queue driver.

---

## 1. Recommended EA architecture

### 1.1 The three clocks (load-bearing structural fact) [VERIFIED Lens 1]

| Clock | Components | Cadence | Carry between bars |
|---|---|---|---|
| **H1 signal** | `CoreEngine`→`f_core[8]`; 8 sleeves+`Ensemble`→`f_sat[31]` | one row / hourly union bar | large per-sleeve indicator state |
| **M1 equity** | `CoreSim`→`a` (combined `eqc`); `SatEquityNative`→`b` (`eq_c`) | one step / minute | account balance, lots[], entry[] |
| **Blend + exec** | `BookBlend`→`book_frac[33]`; `FED_Reconcile` | blend at H1 boundary; **re-size every M1** off `ACCOUNT_BALANCE` | `g_fedTgt[33]`, held positions |

Model of record is HOURLY (`reproduce.py::static_blend`, MODEL_SPEC §2) [VERIFIED]:
`a_h`,`b_h` are the 1m equity curves **sampled asof the hour boundary** (last ≤ h), each
**normalised by its OWN first 1m value** (`iloc[0]`), NOT by the 10000 seed. `j=w·a_h+(1−w)·b_h`;
`fed[h,k]=f_core·(w·a_h/j)+f_sat·((1−w)·b_h/j)`; `w=0.70`; **`s` is NOT applied in the blend
— it is `FED_Reconcile`'s `InpScale` dial** [VERIFIED BookBlend.mqh L168-176; BookExec L211].

### 1.2 Key simplification the blend permits [INFER, load-bearing]

The blend consumes ONLY `a_h`=`eqc` and `b_h`=`eq_c`. It never uses CoreSim's `eqw`/`margin`
nor SatEquityNative's `eq_w`. Those worst-marks feed only each engine's internal stop-out
(CoreSim noliq 1e-9, SatEquityNative 0.50), both of which **structurally never fire in-sample**
(EA_V3 §7; worst DD 22.6% IC / 13.3% FTMO vs ~50% needed). → The live book needs exactly
**one scalar per hour from each equity engine**, so the CoreSim streaming combiner can drop
`eqw`/`margin`/union-worst from the hot path. (The six-field feed is still needed because the
worst-mark marks longs at own `bid_low` and shorts at own `ask_high` — §2.)

### 1.3 Component ownership + state inventory [VERIFIED Lens 1 §4]

Top-level `FableBookNative` owns one instance of each, plus glue state:

| Instance | Persistent carry |
|---|---|
| 8 sleeve steppers (meanrev, carry_breakout, seasonal+crypto, intraday, crisis, trend_v2, mag) | ring buffers, EWM accumulators, pending FIFOs, `cur_day`; **all expose `GetState`/`SetState`** [VERIFIED] |
| `CSatEnsembleStepper` | config only — **stateless across bars**; per-bar staging cleared each `Step` [VERIFIED Ensemble.mqh L413] |
| `CSatEquityNative` (`b`) | `m_balance`, `m_lots[31]`, `m_entry[31]`, `m_n_trades` — clean streaming stepper [VERIFIED] |
| `CCoreBookSim` (`a`) | per-leg balance/pos/entry + segment seed chain — **segment-batch replay, not streaming** [RISK §5] |
| Core-signal (`f_core`) | daily series + band/quarter ledger [RISK §1.4] |
| top-level glue | `ffill[37]`, `cur_day`, trend/crisis pending queues, `trend_cur[5]`, `crisis_cur[4]`, `prev_rows`(7 sleeves), `prev_ts`, `f_sat_held[31]`, per-leg Core `tgt_held`, `a_first`/`b_first`, `g_fedTgt[33]` |

### 1.4 The `f_core` source — the include-graph decision [SUPERSEDED by FABLE REVISION v2 item 1: option (a) DECIDED — option (b) measured non-bit-exact (USDJPY 2-leg netting)]

`CoreEngine.mqh` is the **verbatim v7 executing-EA body**: file-scope `CTrade trade;`,
order-sending `QuarterRebalance`/`ExecSleeve`. It **cannot be `#include`d beside `BookExec.mqh`**
(symbol collisions). `f_core` is the leg's held frac-of-own-equity **after** equal-capital
weighting `W[n]` and the daily band re-split — entangled with `OrderSend`. Two honest options:

- **(a) Refactor CoreEngine → a compute-only signal class** emitting `f_core[8]` for
  `(hour,dow,series)` with no `trade`/no order sends. Clean, larger surface, must re-prove G1.
- **(b) Reuse CoreSim's per-leg `tgt`** (net 9 legs → 8 `f_core` cols) if that `tgt` IS the
  `f_core` the blend needs. Then one engine yields both `f_core` and `a`, and CoreEngine.mqh
  is not included at all.

**Recommendation:** pursue **(a)** — a compute-only Core signal class shared by both `f_core`
and CoreSim's per-leg `tgt` — but **gated on a leg↔column identity check against
`v7_book_frac_1h.parquet`** (8 net cols: AUDUSD, BTCUSD, ETHUSD, EURGBP, NZDUSD, USDJPY,
USTEC, XAUUSD). If (b)'s identity holds bit-for-bit, (b) is cheaper and preferred. This check
is a Stage-0 gate, not an assumption.

### 1.5 Per-bar orchestration (the schema the build follows) [VERIFIED Lens 1 §2]

**Each M1** — advance the two equity clocks on the held prior-hour targets:
`b.Step(f_sat_held, six-field row, eq_c, eq_w)` → `b_curr`;
`a` streaming `StepLegBar` per leg with `tgt`=held per-leg Core target → `a_curr`;
capture `a_first`/`b_first` on the very first processed minute; `FED_Reconcile()`.

**Each H1** — mirror `harness_sim.py::main` statement-for-statement (MEASURED 4.197e-14 vs
golden): update `ffill[37]`; on server-day rollover queue `trend_v2` (eff d+1 05:00) and
`crisis` (eff `ts+1d+13h`, weekday gate `(cur_day+3)%7<5`); `xau_ret=clip(ffill[XAU]/prev−1,±0.30)`;
activate pending; build 7 non-deferred sleeve rows; `seasonal/crypto.StepNs` **emits the
PREVIOUS bar's row** (1-bar deferral); on emit `shell.SetSleeveRow`(all 8)+`shell.Step(prev_ts,
f_sat[31])`; compute `f_core[8]`; sample `a_h=a_curr/a_first`, `b_h=b_curr/b_first`;
`BookBlend.Step`→`out[33]`; remap MODEL→broker → `g_fedTgt[33]`. The one-hour emission lag is
self-consistent with the book's `h→h+1` causal lag [VERIFIED harness].

---

## 2. The data-path decision (LIVE) + the validation-vehicle call — LOAD-BEARING

### 2.1 The per-bar schema is SIX independent price fields per symbol [MEASURED, the crux]

`SatEquityNative.Step` (L214-219) and `BH_ENGINE_SPEC §3/§4` require, per union minute per
symbol k: `has_bar`, `bid_o`, `ask_o`, `bid_c`, `ask_c`, `bid_l`, `ask_h`, `eurq`, `swap_l`,
`swap_s`. The worst-mark marks **longs at own `bid_low`, shorts at own `ask_high`,
independently, same minute**. → the model needs a **true independent ask-high series**, not
bid-OHLC-plus-a-spread. All costs are **hermetic / pre-baked** (contract/commission/leverage/
lot_step/min_lot are frozen tables; `eurq` derived from EUR-cross close-mids; swaps from a
cost-model port) — the feed's ONLY job is the six price fields + `has_bar`; broker
`SymbolInfoDouble` is irrelevant to the equity math [MEASURED CoreSim.mqh:13].

### 2.2 The two residuals bundled inside "compute live" — SEPARATE THEM

The word "live" hides two very different errors. **The whole design hinges on not conflating them.**

- **R1 — the COMPUTE/orchestration residual.** Given the *exact same six-field inputs*, does
  the EA's include code + the new orchestration glue reproduce the golden `book_frac`? This is
  **already ~closed**: f_sat 4.197e-14, b bitwise, blend bit-exact, a scalar bit-equal 32/32.
  What remains un-golden in R1 is purely the **new glue** (three-clock wiring, CoreSim
  streaming wrapper, `f_core` source, feed assembler). R1 is **deterministic and certifiable
  to the golden on frozen inputs** — it does NOT need a broker feed to measure.
- **R2 — the FEED residual.** Does the broker/tester M1 feed equal the frozen IC bars the
  golden was built on? **It does not, by construction** — different bars; in the 1m-OHLC
  tester the ask is fabricated (§2.4); the reference pipeline itself contains lookahead
  (`ffill().bfill()`, full-sample `median` commission) a forward stepper cannot reproduce.
  R2 is **irreducible and un-golden**. The owner-ratified band **ΔCAGR≤±1.0pp /
  ΔMaxDD_worst≤±0.5pp / ΔBreach≤±0.5pp** is the acceptance frame for R2, not R1.

### 2.3 LIVE data path — RESOLVED

**Live is the easy case for the six-field schema.** A live terminal accumulates real bid AND
real ask ticks, so a *true independent* `ask_high` series exists per symbol per minute. The
EA pulls each symbol's completed M1 bar (`CopyRates`, the mechanism `CoreEngine.mqh:198`
already uses in-tester for non-chart symbols, G1-proven for Core's 8 legs), builds the
`has_bar` mask, ffills absent bars, and marks worst on the real ask-high. **Live sizing is the
deliverable and is sound.** The seed problem is relocated to `OnInit` (§3), not eliminated.

### 2.4 The tester ask-series killer [MEASURED, decisive]

MT5 **1m-OHLC** mode fabricates `ask = bid_OHLC + one integer spread`; there is **no
independent ask series**, so `ask_high` is forced to `bid_high + spread·point`. This
mis-marks the **short worst-mark exactly in the crisis tail (COVID)** where spreads blow out
and where the campaign's MaxDD lives. **Real-tick** over-resolves *below* the 1m worst-mark
model (over-marks) and also diverges. → **`a`/`b` MaxDD and crisis claims are NOT certifiable
inside the 1m-OHLC tester.**

### 2.5 THE VALIDATION VEHICLE — recommend BOTH, with a strict division of labor

Neither vehicle alone certifies the whole thing. The honest split:

| Vehicle | Certifies | Grade | Does NOT certify |
|---|---|---|---|
| **Full-pipeline frozen-input replay harness** (extend the passed `TestSatEquity`/`TestBlend`/`TestCoreSim` scripts into a whole-book `TestBook` reading six-field bundles) | **R1** — the compute chain vs golden `book_frac` at **component tolerance** (bit-exact-ish) | `book_frac[33]` diff vs `FMA3_fed_frac_v3.csv` | nothing about the broker feed |
| **1m-OHLC tester on the broker feed** (native compute end-to-end) | multi-symbol feed mechanics (`has_bar`/ffill union grid), execution, **position-level fidelity**, and **measures R2** | held fraction == `book_frac·s` (median 1.000, as RECON-4) | `a`/`b` worst-mark, MaxDD, crisis (fabricated ask) |
| **Real-tick tester + six-field frozen engine** | crisis/MaxDD **cross-check only** | COVID-window worst-mark vs six-field IC parquet | not the primary `a`/`b` oracle |

**The call:** certify **R1 to the strictest component tolerance on FROZEN six-field inputs,
OFF the tester, BEFORE any execution** (Stage 2); then run native compute **inside** the
tester to validate feed mechanics + position fidelity and to **measure R2 as a known number**
(Stage 4); keep **MaxDD/crisis certification on the six-field frozen engine + a real-tick
cross-check, never on the 1m-OHLC tester**. This is the load-bearing recommendation and it
needs owner ratification (§7). The honest tradeoff: the tester delivers the no-CSV
dynamic-sizing win and position parity but **cannot** be the oracle for the numbers the
campaign cares most about (MaxDD, crisis); those stay on the frozen six-field engine.

### 2.6 Universe + reproducibility [MEASURED]

~34 symbols at 1m: 31 Satellite (`SATEQ_SYMBOLS`) + Core-unique legs + EURJPY as a
conversion-only cross (EURJPY is NOT in the 31 traded; union traded = 33, MODEL_SPEC §7).
`eurq` needs the full 8-cross map (EURUSD/EURJPY/EURGBP/EURCHF/EURNZD/EURCAD/EURNOK/EURSEK).
The tester rebuilds its cache from the terminal's mutable broker M1 base → a run is
**reproducible only as pinned custom symbols** with a recorded sha of the full bar set. Owner
decision §7. **[RISK/OPEN]** multi-symbol *synchronized* 1m for 34 symbols is CORROBORATED for
Core's 8 legs (G1) and **ASSUMED-scalable** to 34 — validate on the 1m-OHLC smoke before
trusting real-tick (staged protocol).

---

## 3. Warm-start design + certification

### 3.1 The finding that inverts the naive instinct [Lens 3, load-bearing]

"Seed from ≥2019 history" is **WRONG for the in-sample reproduction and would BREAK parity.**
The golden `a`/`b`/`f_core`/`f_sat` were themselves computed by engines that **cold-start at
model t0 = 2020-01-02 with empty indicator state**. That COVID blindness (memory: k≈4.7
artifact — the record skips the −1,586 EURGBP short) is **baked into the golden the EA must
match**. A 2019 warm-up gives the EA a *different/better* COVID state → guaranteed divergence.
"Warm" = "continue the golden's own accumulated path," NOT "pre-train on 2019."

### 3.2 Two use cases, opposite treatment

| Use case | "Warm" means | Pre-2020 data? |
|---|---|---|
| **A — in-sample tester reproduction (RECON-9)** | FRESH/empty state at t0; begin at first union bar. Cold-start era is inside the band because the golden shares it. | **NO — forbidden** |
| **B — live deploy past 2025-12-31, or EA restart mid-run** | Restore the EXACT golden-path state at boundary D | only frozen 2020→D history, never pre-2020 |

### 3.3 Two state classes [Lens 3]

- **Class-S (bounded-lookback SIGNAL state, 8 sleeves + Core signal):** the pandas EWM kernel
  (`adjust=True, ignore_na=False`) has **infinite memory** (`old_wt += 1`), so **no finite
  window is bit-exact** — only replay-from-first-bar or restoring the exact
  `(weighted, old_wt, nobs)` triple is bit-exact; a finite window is admissible only under the
  ratified tolerance in a genuine forward deploy. Binding finite lookbacks: carry_breakout
  960 hourly (Donchian) + crisis 250 daily (EwmStd) ≈ 12 calendar months.
- **Class-P (unbounded path-dependent equity, `a`,`b`):** NOT indicators, no steady state —
  running product of every bar's P&L since t0, normalized to the t0 anchor. **Only
  warm-starts: full replay from 2020-01-02, or an exact state blob.** No lookback shortcut.

### 3.4 Design of record — dual-path, both hash-gated [Lens 3 §3]

- **B1 (primary) — WARM-STATE BLOB.** Pre-exported, config-hash + sha256 gated bundle at
  boundary D from the frozen replay: one `get_state()` per Class-S stepper + Core-signal seed
  + `b` state JSON + `a` per-leg state & seed/segment cursor. `OnInit` `set_state`s all, then
  trades from D. Fast; exact golden state by construction. **Mandatory if secondary-symbol 1m
  history back to 2020 is not reliably available in the run mode** (§2.6 RISK).
- **B2 (certifier) — FULL REPLAY at OnInit** from 2020-01-02 through D. Slower; needs no blob;
  used to regenerate/verify B1.
- **Use-case A:** neither — init FRESH at t0, start at first union bar.

Blob schema, exporter self-check (re-derived `book_frac` at D must match golden bit-for-bit),
and the full field inventory are in `WARMSTART_DESIGN.md §6`.

### 3.5 Certification — the state-diff gate FMA3-RECON-9-WS [Lens 3 §4]

At a boundary D where both caches exist (recommend **2022Q2→Q3**, already bitwise-proven for
`b` via chained `TestSatEquity`): (1) **Class-P state-diff** — `b` JSON field-for-field ==
`FMA3_bh_state_expected_{Q}.json`; `a` per-leg + seed cursor == CoreSim carry. (2) **Class-S
state-diff** — each `get_state()` == reference (exact non-EWM; EWM triple within tolerance).
(3) **Output re-derivation** — first live bars' `book_frac[33]` reproduce the golden rows for
D+ within the ratified band. (4) **No-artifact check** — the k≈4.7 transient is ABSENT in the
first ≥ max-lookback (960h/250d) live bars. **[RISK/OPEN]** Core-signal warm-start is the
least-proven seam: no `CoreEngine` state-export exists yet; whether its daily-series seed
round-trips into a blob field-for-field is UNVERIFIED — flag, do not assert.

### 3.6 Ratio-chain, never re-base [Lens 3 / DESIGN_OPT1 §5, safety-critical]

Live restore is `a_h = a_last·(sim_eq[h]/sim_eq[D])`, same for `b`. **Re-basing `a` and `b`
independently to 1.0** changes the `a/b` ratio and therefore **every** blend weight while
passing all `<1e-12` self-checks — the single highest-severity silent-wrong surface. The
serializer must be full-ledger, ≥12 sig-digit, atomic (tmp+rename); today's `SaveState`
(12 values at 4dp) is catastrophic for a ratio-chained multiple. Boot self-reconcile mandatory.

---

## 4. The designed gate (what's logged, judges, the two comparisons, where the band applies)

### 4.1 What is logged (per bar, both vehicles)

Per H1: `f_core[8]`, `f_sat[31]`, `a_curr`/`a_h`, `b_curr`/`b_h`, `book_frac[33]` (pre-`s`),
the `has_bar[34]` mask, and the union-grid minute. Per M1 in the tester: `FED_LogRow` already
emits `sym,ev,frac,want,held,after,balance` [VERIFIED BookExec L36-43] — the RECON-4
position-level oracle. Plus the warm-start state blob at D.

### 4.2 The two comparisons (map cleanly to R1 and R2)

- **Comparison 1 (R1, the compute gate):** EA `book_frac[33]` on FROZEN six-field bundles vs
  golden `FMA3_fed_frac_v3.csv`. **Judge: bit-exact-ish at component tolerance** (f_sat
  4.2e-14, b/blend bitwise, a bit-equal). This is the strict gate and it runs **before any
  execution**. The ratified ±band does NOT relax this — R1 is expected to essentially match.
- **Comparison 2 (R2, the feed gate):** native compute inside the tester on the broker feed
  vs golden, graded at **position level** (`held == book_frac·s`, median 1.000 target as
  RECON-4) and summarized as **ΔCAGR / ΔMaxDD_worst / ΔBreach**. **Judge: the owner-ratified
  band ΔCAGR≤±1.0pp / ΔMaxDD_worst≤±0.5pp / ΔBreach≤±0.5pp.** This is where the band lives.

### 4.3 The judges

- **R1 judge:** Python-side statement-mirror of the whole-book orchestrator (extend the
  passed `sat_equity_harness_sim.py` / `harness_sim.py` mirrors) diffing every stream row.
- **R2 judge:** RECON-4-style position-level reconciliation + the ΔCAGR/ΔMaxDD/ΔBreach
  summary; **plus** the union-grid/`has_bar` diff vs `record_engine`'s `np.unique` union
  (alarm on any grid-minute mismatch — a clock-chart grid misses minutes where only a
  non-BTC symbol printed).
- **MaxDD/crisis judge:** the six-field frozen engine + a real-tick COVID-window cross-check —
  **never** the 1m-OHLC tester's fabricated ask.

Every new `.ex5` gets a recorded **FMA3-RECON-N** entry before deploy (standing rule).

---

## 5. Execution reuse — VERBATIM except one seam + one remap

The entire execution stack downstream of `g_fedTgt[33]` is **unchanged and RECON-4-proven**:
`FED_Reconcile` sizes `g=g_fedTgt[k]*InpScale` off `ACCOUNT_BALANCE` [VERIFIED BookExec L199-211],
applies the margin cap, rebalance band 0.25, `SYMBOL_VOLUME_LIMIT` clamp [L249-255], split
send, reject backoff, and the FTMO breaker (Guardian) — all verbatim. `BookConvert` (full-map
eurq) and `Guardian` are reused as-is.

**The entire un-golden change is exactly one function:** replace `FED_ApplyHour(hourEpoch)`
(BookReplay L211, which fills `g_fedTgt[]` from the frozen CSV cursor) with the live blend
that writes the **identical** `g_fedTgt[33]` vector. Set `g_fedTgtDirty=true` and `FED_Reconcile`
does the rest.

**Plus one remap [VERIFIED Lens 4, REQUIRED].** `BookBlend.NetSymbol(k)` emits 33 cols in
**MODEL-name** sorted order (DAX, USA500, JP225 …); `g_fedCanon[33]` is fixed **broker-name**
order (DE40, US500 …). USA500/DAX vs US500/DE40 sort to **different positions** → a fixed
model→broker map (`USA500→US500`, `DAX→DE40`, identity else) + `FED_SymIndex(canon)` lookup
[VERIFIED BookReplay L67-69] is required to wire `NetSymbol(k)` into the correct `g_fedTgt[idx]`.
This replaces the exporter's emit-time remap. Keep-last-good / `__GRID__` all-flat-hour
semantics [VERIFIED BookReplay L208-234] must be reproduced by the live writer (a present hour
zero-inits then writes; an absent hour holds).

---

## 6. Staged build plan [SUPERSEDED by the FABLE REVISION v2 stage plan at the top — key changes: feed probe moved to S0 (both tester AND live modes, with a named fallback), original S1 deleted (CoreSim in-terminal gate ALREADY PASSED, RECON-8d), no streaming wrapper built (structural lookahead — see v2 item 2)]

Each stage is a go/no-go. **The compute chain is fully validated against golden on frozen
inputs BEFORE any execution or tester run.**

- **S0 — spine + include-graph resolution.** Resolve the `f_core` source (§1.4): run the
  leg↔column identity check vs `v7_book_frac_1h.parquet`; refactor CoreEngine → compute-only
  signal class if needed. Fix the model→broker name remap (§5). **Checkpoint:** whole include
  tree compiles 0/0, no `CTrade` collision, remap unit-verified on the 4 divergent-sort names.
- **S1 — close the one open in-terminal gate: CoreSim `a`.** Write CoreSim's **in-terminal
  input exporter** (missing today — BPURE_WAVE3 Track B) + the streaming wrapper (interleave
  `StepLegBar` time-major; incremental combined `eqc` without the O(all-bars) `FinishSegment`;
  embed the frozen band-trigger dates for live re-seed). **Checkpoint:** `a` bit-equal to the
  32/32 parity parquet **in MQL5, in-terminal** (currently only scalar-proven).
- **S2 — WHOLE-BOOK COMPUTE CHAIN vs golden on FROZEN six-field inputs (closes R1).** Extend
  `TestSatEquity`/`TestBlend`/`TestCoreSim` into `TestBook`: drive the full orchestrator on
  frozen bundles → `book_frac[33]`, diff vs `FMA3_fed_frac_v3.csv`. **Checkpoint: ≤ component
  tolerance (bit-exact-ish). This is the primary correctness gate and it runs before any
  execution.**
- **S3 — wire the seam + name remap on frozen `g_fedTgt`.** Feed `g_fedTgt=golden` into
  `FED_Reconcile`; reproduce RECON-4 position-level. **Checkpoint:** held == `book_frac·s`,
  median 1.000 (matches RECON-4), execution stack unchanged.
- **S4 — native compute INSIDE the 1m-OHLC tester on the broker feed (measures R2).** Grade
  position level; diff union-grid/`has_bar` vs the golden union; report ΔCAGR/ΔMaxDD/ΔBreach.
  **Checkpoint:** within the ratified band at position level; feed residual R2 is now a **known
  number**, not an assumption.
- **S5 — warm-start.** Export the B1 blob + run FMA3-RECON-9-WS at 2022Q2→Q3 (state-diff +
  re-derivation + no-artifact). **Checkpoint:** all four sub-gates pass.
- **S6 — crisis + deploy readiness.** Real-tick COVID-window MaxDD cross-check on the
  six-field engine; **demo-forward run if the owner requires it (§7)**; record FMA3-RECON-N.

---

## 7. Owner decisions (explicit — needs ratification)

1. **The data-path / validation-vehicle call (§2.5) — the load-bearing decision.** Ratify
   **BOTH** with the strict split: frozen-input replay certifies the compute chain (R1); the
   1m-OHLC tester certifies feed mechanics + position fidelity and measures R2; **MaxDD/crisis
   stay on the six-field engine + real-tick, NOT the tester.** Accept that no single vehicle
   certifies the whole book.
2. **`f_core` source (§1.4).** ~~Approve (a) vs (b)~~ **RESOLVED by FABLE REVISION v2:
   option (a) — compute-only `CCoreSignal` refactor. Option (b) was measured non-bit-exact
   (USDJPY two-leg equity-weighted netting). No owner decision needed.**
3. **Is a demo-forward (out-of-sample live) run REQUIRED before capital deploy?** The 2026
   stream is the unfitted holdout; a perfect sim still produces numbers the campaign agreed
   not to trust blindly.
4. **R2 governance.** Ratify the feed residual as a **MONITORED** number with a
   **correction-from-batch** reseed channel (re-run the frozen Python batch on the SAME broker
   feed; reseed on drift) — categorically NOT feedback from the live account. Who owns the
   pinned custom-symbol tester history + its sha?
5. **Warm-start.** Accept the B1 blob as primary (B2 full-replay as certifier). Note that
   live **past 2025-12-31** needs the separate Core-signal recompute + stream extension
   (EA_V3 §7) — out of scope here.
6. **Acceptance frame for R2.** The reference pipeline contains lookahead (`ffill().bfill()`,
   full-sample `median` commission) a forward stepper **cannot** reproduce, so a same-feed
   native run diverges from the reference **by construction**. Decide: **re-pin the model of
   record to a broker-feed `b`**, or **accept the ratified band as the acceptance frame** and
   keep the frozen curves as the reference.

---

## 8. Honest risks + what remains genuinely un-golden

- **R2 (feed residual) is irreducible and un-golden.** The broker feed ≠ the frozen IC bars by
  construction; the 1m-OHLC tester fabricates the ask, mis-marking the COVID short worst-mark
  **exactly where MaxDD lives** → tester MaxDD/crisis are **not certifiable**. This is the
  campaign's honest floor; the ratified band bounds it, it does not close it.
- **CoreSim `a` is the least-proven-in-terminal component.** Scalar bit-equal 32/32, but the
  **MQL5 in-terminal exporter is not yet written** (BPURE_WAVE3 Track B) and the live streaming
  wrapper + live band-trigger re-seed is **genuinely new code**. If the incremental-combine
  residual is material, fall back to re-`FinishSegment` at each H1 boundary over the current
  segment's buffered minutes (correct but heavier). Re-measure the band after the wrapper exists.
- **Multi-symbol tester synchronization for 34 symbols is ASSUMED-scalable** from the 8-leg
  Core G1 proof, not verified. `has_bar`/ffill union-grid must reproduce the golden
  `np.unique` union exactly — the single largest correctness surface for R2. Validate on the
  1m-OHLC smoke before real-tick.
- **Normalisation anchor.** `a_h`/`b_h` divide by the **first 1m value** (`iloc[0]`), not
  10000. The EA must capture `a_first`/`b_first` on the first processed minute or the blend is
  off by a constant factor on every hour.
- **Ratio-chain seed is safety-critical (live).** Re-basing `a`/`b` independently silently
  mis-weights every blend term while passing all `<1e-12` self-checks → REFUSE-TO-TRADE on any
  splice-continuity jump in `j`.
- **Core-signal warm-start round-trip is UNVERIFIED** — no CoreEngine state-export exists yet.
- **Dual-language subordination.** The only correctness oracle for the compute chain remains
  the frozen Python batch; the native EA stays shadowed by and subordinate to the pipeline it
  was meant to replace. The CSV/Python producer is not deleted — it becomes the reference
  oracle and the reseed source.

**What is genuinely un-golden after all stages pass:** only R2 — the broker-feed-vs-frozen-IC
divergence, bounded (not eliminated) by ΔCAGR≤±1.0pp / ΔMaxDD_worst≤±0.5pp / ΔBreach≤±0.5pp,
plus the fabricated-ask crisis tail which must be certified off-tester. R1 (the live
computation itself, on faithful inputs) is closeable to the components' proven tolerance and
is the thing Stage 2 nails before any execution runs.
