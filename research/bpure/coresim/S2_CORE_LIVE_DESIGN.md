# S2_CORE_LIVE_DESIGN — the live Core leg-target source + live band-trigger detection

**Date:** 2026-07-14 · **Track:** S2/S3 item 3 (the S1 scope-pin debt: "live Core leg-target
source"). Design-only — no MQL5 built in this pass. Every claim below is labelled
**[MEASURED]** (probe run in this pass, command/result cited), **[READ]** (quoted from the
cited source file), or **[INFER]** (deduced; flagged for the harness to confirm).

**Context.** S0 resolved `f_core` from CoreSim state (bit-equal 0.0) — the ORIGINAL reason
to refactor CoreEngine died there. What did NOT die: CoreSim **consumes** per-leg per-minute
`tgt` (frozen column in the segment bundles) and **replays** 32 frozen band-trigger segments.
Live, both must be computed forward: (A) the per-leg targets from the Core book's signal
logic, and (B) the segment boundaries from CoreSim's own slot equities. This document designs
both, plus the parity harness that gates them.

---

## 1. REALITY CHECK — the `CTrade` include collision (Q1)

### 1.1 The collision is real, and it is three collisions stacked

CoreEngine.mqh is an include of EA-body functions — it defines **no** `OnInit`/`OnTick`/
`OnDeinit` (grep: only comments mention them; the main .mq5 owns the handlers). The collision
is NOT event handlers. It is:

1. **Duplicate file-scope global** — both files define the same identifier at file scope
   [READ]:
   - `mt5/ea/Include/Core/CoreEngine.mqh:68` → `CTrade   trade;`
   - `mt5/ea/Include/Book/BookExec.mqh:26`  → `CTrade trade;                     // shared order object`
   Including both in one program is a duplicate-definition compile error. (This is the ONLY
   direct symbol collision: every Book/Sat-side function/global is `FED_`/`F3_`-prefixed or
   class-scoped — grep over `RoundLots|SendSplit|CloseAll|HeldNet|MarketOpen|LogRow|SMA|Clip|
   Series|W[|g_seed|g_slSym...` finds no second unprefixed definition outside
   `Include/FMA3/V7Core.mqh`, which FableBook does not include.) [MEASURED grep]

2. **Program-scope input dependency + semantic capture.** CoreEngine reads ~30 `Inp*` inputs
   that live in `FableFederation_V2.mq5` (L50–110): `InpRisk, InpMagVt, InpMagCap, InpBtcVt,
   InpBtcCap, InpBtcHurdle, InpBtcLb, InpBtcRegime, InpHarvestK, InpBandUp, InpBandDownDiv,
   InpBandMinGapDays, InpMinM1Bars, InpSizingBase, InpIndepReseed, InpReseedBalance,
   InpV34EurQuoteFix, InpMagicBase, InpMarginCap, InpRebalBand, InpLog, InpUSDJPY, InpEURJPY,
   InpEURGBP, InpEURUSD, ...` [READ]. `FableBook.mq5` defines SAME-NAMED inputs with
   DIFFERENT meanings/values (`InpMagicBase`=3900000 vs 360000; `InpLog`, `InpMarginCap`,
   `InpRebalBand`, `InpEUR*`) [READ FableBook.mq5 L33–52]. An include would silently bind
   CoreEngine's ledger to FableBook's values — e.g. CoreEngine sleeve magics
   `InpMagicBase+1..12` = 3900001..3900012 would OVERLAP FableBook's per-symbol magics
   `FED_Magic(k)` = 3900001..3900033, corrupting BOTH deal-history sub-ledgers. The missing
   inputs (`InpRisk` etc.) would be undeclared-identifier compile errors.

3. **The F3 dependency tree.** CoreEngine calls `F3_SendAdd, F3_HoldSet/HoldClear/StepOf,
   F3_SizeSkipWarn, F3_IsV7Symbol, F3_EurPerQuoteV34, F3_V7BookEquity/V7BookBalance,
   g_f3FedActive` [READ L459–467, L528, L825–876, L1013–1064] — defined in
   `Core/V34Exec.mqh`/`Core/Federation.mqh`. Including CoreEngine drags the whole v1/v2
   federation execution stack into the book EA.

### 1.2 The collision is MOOT under this design

The design below extracts ONLY the signal layer into a new self-contained class
(`CCoreSignal`, §3) with zero file-scope globals, zero `Inp*` reads (parameters injected via
`Configure`), zero CTrade, zero terminal-account calls. `CoreEngine.mqh` is **never included
in FableBookNative** and is **not modified** (it stays the G1-proven asset of
FableFederation_V2). No collision resolution inside CoreEngine is needed or attempted.

---

## 2. DISSECTION — where the per-leg targets actually come from (Q2)

### 2.1 The normative source is the NSF5 python, with CoreEngine as corroboration only

The frozen `tgt` columns were produced by NSF5 `sim.book("BTC_REP","USTEC")` =
`v52_alternatives.book(kind="BTC_REP", us5="USTEC")` at **`RISK = 8.0`**
[READ v52_alternatives.py L30, L52–66] → `lock_v5.build_sleeves(8.0, ["S6_OPEXUSD","MAG_XAU"],
us5_inst="USTEC")` with MAG_XAU deleted and BTC_REP added. Leg → target-function map
(book append order = the TestCoreSim LEG TABLE):

| leg | inst | frozen target producer [READ] | defer_reopen? |
|---|---|---|---|
| 0 BOOK_XAU | XAUUSD | `gold_book_v31` (portfolio_v33 L66): Σ_{lb∈50,100} `gold_donch(vt=0.125R)`·(0.17/0.36) + `xau_night_va(vt=0.30R)`·(0.19/0.36) | YES (build_signals L133) |
| 1 S5_JPY | USDJPY | `jpy_smart(vt=0.15R, cap=20)` (sleeves L230) | YES |
| 2 S1_ETH | ETHUSD | `crypto_mom(vt=0.40R, cap=1.2)` (sleeves L40) | YES |
| 3 ZC_EG | EURGBP | `eurgbp_zens(vt=0.20R, cap=20)` (sleeves L284) — 20:00-stamped | YES |
| 4 BOOK_USTEC | USTEC | `us500_book_v33(vt=0.85R)` (portfolio_v33 L74): inner-deferred regime·(0.09/0.24) + `monday_us500`·(0.15/0.24), then **OUTER defer_reopen again** (lock_v5 L66) | YES — **double** |
| 5–7 S6 | USDJPY/AUDUSD/NZDUSD | `v5_sleeves._opex_leg(sign=+1/−1/−1, vt=0.15R, cap=6)` (v5_sleeves L46) | no |
| 8 BTC_REP | BTCUSD | `v52_alternatives.btc_hurdle_legs(lb=63, hurdle=0.40, regime=200, vt0=0.40, cap=1.2)` (L42) | no |

`defer_reopen(target, bars)` [READ portfolio_v33.py L54–60]: bars with raw-stamp hour ∈
{21,22} → NaN → ffill (hold the 20:59 target through 22:59; resume at 23:00).

**CoreEngine's `CurrentTarget` is NOT a faithful spec of the frozen tgt.** Three measured/read
divergences:

- **[MEASURED] USTEC Monday exit is 23:00 in the frozen tgt, 21:00 in CoreEngine.** Probe of
  `FMA3_coresim_seg0.csv` leg 4: Monday leverage ON at Mon 01:00 (first Monday bar), OFF at
  **Mon 23:00** every Monday (e.g. `Mon 02-03 23:00  6.25 → 0.0`). Cause: lock_v5 L66 applies
  an OUTER `defer_reopen` over the whole `us500_book_v33` (whose Monday component exits at
  hour ≥ 21) — the 21:00 exit lands inside the 21–22 defer window and is held to 23:00.
  CoreEngine gates `monOn=(dow==1 && hour<21)` and EXEMPTS SL_US5 from `InReopenWindow`
  (ExecSleeve L1033) → drops it at 21:00. The extraction must implement the anchor
  (23:00), not CoreEngine.
- **[MEASURED] Hour basis is the RAW bar stamp (server clock), not ToUtc.** All target
  functions gate `bars.index.hour` on the raw index [READ sleeves.py]; probe: XAU night
  window transitions at raw hours 20:00→08:00 exactly; the frozen grid is tz-naive broker
  server time (CORESIM_SPEC §1) and S0 proved the live terminal's raw stamps reproduce that
  grid bit-exact. CoreEngine converts to UTC (`ToUtc`, L131) before gating — a live
  server-vs-UTC offset would shift every hour gate. The extraction gates on the raw
  bar-stamp hour/day (server), NO ToUtc.
- **[READ] Kernel shapes differ.** Anchor: pandas `rolling(win).std()` (ddof=1, pandas
  roll_var kernel) over `pct_change`, `rolling.max/min().shift(1)` + ffill-from-start
  Donchian state, `sig.shift(1)` daily lag realized by label shifting + `_to_bar_array` ffill.
  CoreEngine: scan-based `RetStd`/`DonchSig` re-derivations. Same intent; bit-parity not
  established anywhere. The port must use pandas-faithful kernels (reuse `Sat/SatMath.mqh`
  primitives, the RECON-8b-proven route), not CoreEngine's scans.

**[MEASURED] `R=8.0` confirmed numerically from the frozen tgt itself:** cold-start XAU
night-only value 3.166667 = cap(6.0)·(0.19/0.36) (nightLev at cap ⇒ clip(0.30·8/av,0,6)=6);
USTEC Monday-only value 6.25 = cap(10.0)·(0.15/0.24). Note the shipped FED preset uses
`InpRisk=8.96` (= 8 × 0.70 × 1.6, run-54 operating point) [READ presets/FED_IC.set] — that
embeds w·s into the REAL-account dial. The idealized CoreSim tgt is R=8.0 **pure**; w and s
are applied downstream (BookBlend / InpScale). Do not copy the preset R into CCoreSignal.

**[MEASURED] Cold start is baked in:** seg-0 XAU tgt ≡ 0 until the daily-series lookbacks
warm (first nonzero early Feb 2020 = night component after ~21 daily bars) — consistent with
the WARMSTART finding that the golden curves cold-start at t0 (memory: the COVID-blindness
artifact). Live use-case A (in-sample reproduction) must init CCoreSignal EMPTY at
2020-01-02, never pre-warmed on 2019.

### 2.2 What the signal path NEEDS — and none of it is account state

Per §2.1 formulas, the complete input inventory:

1. **Daily mid series per instrument** (8 series): XAUUSD, USTEC, USDJPY, ETHUSD,
   EURGBP-pre20, AUDUSD, NZDUSD, BTCUSD. Convention [READ sleeves.py `_daily_mid` L24]:
   `(bid_c+ask_c)/2` at the **last 1m bar of the raw-stamp calendar day**
   (`resample('1D').last().dropna()`); EURGBP variant restricted to bars with raw hour < 20
   [READ eurgbp_zens L291]. NOTE CoreEngine's `BarMid = close + spread·point/2` (bid close +
   half integer spread) equals the six-field mid only where ask ≡ bid+spread·point — true for
   broker M1 rates, an R2-class approximation live; the R1 harness uses `(bid_c+ask_c)/2`
   from the frozen fields.
2. **Deterministic calendars:** opex week = Mon..Fri of each month's 3rd-Friday week
   [READ v5_sleeves `_nth_friday_week(2)` — 0-indexed `fr[2]` = 3rd Friday; CoreEngine
   `InOpexWeek` is the same calendar]; raw-stamp hour/dow per bar; day rollover on raw
   stamps.
3. **Policy-rate step tables** for the JPY carry gate (USD & JPY) — already embedded in
   CoreEngine [READ L119–126] and in NSF5 `engine/costs.py::POLICY_RATES`.
4. **Static params:** R=8.0, per-sleeve vt/cap constants (table §2.1).

**NOT needed:** any broker account state. `VBalance`/`g_seed[]`/`g_realized[]`/`g_dealCursor`
(the deal-history sub-ledger), `HeldNet`, `OrderCalcMargin`, `AccountInfo*` — all of
CoreEngine's account surface exists to SIZE and EXECUTE on the real account and to feed ITS
band trigger. In this design: sizing is CoreSim's own (idealized per-leg balance ×
tgt → lots, already bit-proven), and the trigger consumes CoreSim slot equities (§4). The
per-minute leg target is a pure function
`tgt(leg, t) = defer( gate_hour(t) · daily_coeff(leg, day(t)) )` of price history + calendar.

**Adjacent live-feed scope (flagged, same seam):** CoreSim's other pre-baked inputs — `eurq`
(EUR-cross close-mid asof) and the swap triple (`swap_flag/long/short`, 17:00-NY DST
rollover + policy tables + triple-days) — are exported arrays today (CORESIM_SPEC §9.4
makes recompute forks "impossible by construction"; that guarantee dies live). The live
Core feed assembler must generate them forward: eurq from the multi-symbol feed (S0-proven
crosses), swaps from an embedded generator (full policy tables incl. EUR/GBP/AUD/NZD + the
NY-DST calendar). Parity probe: regenerate the 2020–2025 swap columns and diff vs the
exported seg CSVs (gate: bit-equal). This is part of S2's feed work, not of CCoreSignal.

### 2.3 State the live signal carries (the warm-start inventory)

| state | size / bound | class |
|---|---|---|
| 8 daily-mid ring buffers | ≤ 262 days each (max lookback: regime 200 + vol 20 + shift 1 + slack; BTC needs 200 regime & 63+1 momentum) | Class-S bounded — EXCEPT the two Donchian `sig` states (below) |
| Donchian last-breach state (XAU 50/100) | one ±1/0 flag each; the anchor ffills breach state **from series start** — technically unbounded memory; a ring-buffer rescan reproduces it only if a breach occurred inside the ring | Class-S with a caveat: the warm blob must carry the flag explicitly |
| current-day coefficients (donchTgt, nightLev, regTgt, monLev, jpyM, ethM, egM, s6uj/au/nz, btcM) | 11 doubles, recomputed at stamps (00:00 daily; EG at 20:00) | derived |
| defer state | per deferred leg (5): last pre-21:00 target value | 5 doubles |
| in-day bookkeeping | cur_day, did20 flag | trivial |

No deal-history ledger, no quarter/band ledger — those belong to the trigger detector (§4),
whose state is CoreSim's own (per-leg balance/pos/entry + seed + segment-start date).

### 2.4 Stamp/lag law (normative, from the anchor)

- Daily-coefficient recompute uses the daily series **through D−1** and takes effect at the
  first bar with raw-stamp day D (anchor: `sig.shift(1)` + `_to_bar_array` ffill from the
  midnight label). Vol is `_vol_scale` = rolling-std-of-returns **shifted one more day**
  inside the helper — i.e. effective-day-D vol uses returns ending D−1. [READ sleeves L35]
- EURGBP: signal from D−1's pre-20:00 close, effective from D's first bar at/after raw
  20:00 (label +20h + ffill); between 00:00 and 20:00 of D the D−2-based value holds.
  [READ eurgbp_zens L299–305]
- S6: calendar mask needs no shift (deterministic); magnitude vol is shift-1; bar-level
  gates Monday <12h, Friday ≥20h, and the Sunday-after-opex zeroing [READ _opex_leg L57–63].
- defer_reopen LAST, at bar level (raw hour ∈ {21,22} → hold), applied to legs 0–4 (USTEC
  twice — inner regime-only + outer whole-book; the outer one is what makes Monday exit
  23:00).

---

## 3. EXTRACTION PLAN — what moves where

**New file `mt5/ea/Include/Core/CoreSignal.mqh`** (compute-only, self-contained):

- `class CCoreSignal` — members: the §2.3 state; API:
  - `Configure(double R=8.0)` (+ vt/cap table as constants; NO `Inp*` reads),
  - `OnDailyBar(int inst, long day_epoch, double mid)` — append a completed daily mid
    (inst ∈ the 8-series enum; EG-pre20 is its own series),
  - `RecomputeDaily(long day_epoch)` / `RecomputeEG20()` — the §2.1 formulas via SatMath
    pandas-faithful kernels (rolling mean/std/max/min; the EG expanding-median z-ensemble
    per eurgbp_zens; policy-rate tables embedded),
  - `TgtAt(int leg, long ts)` — per-minute target: hour/dow gates on RAW stamp + defer-hold
    logic (per-leg held value across the 21–22 window; USTEC double-defer),
  - `GetState/SetState` (JSON, ≥12 sig digits) for the warm blob incl. the Donchian flags.
- **Daily-series feed** has two drivers sharing `OnDailyBar`:
  - R1/harness: derived from the same six-field 1m stream the assembler already carries
    (last bar of raw day per instrument, `(bid_c+ask_c)/2`; EG pre-20 variant) — NO separate
    export needed;
  - live: identical derivation from the live M1 feed (not CoreEngine's `CopyRates`/`BarMid`
    path; the assembler is the single source of bars).
- **CoreEngine.mqh: UNTOUCHED.** The formulas are ported from the NSF5 python (normative),
  with CoreEngine used as a cross-read. Rationale: §2.1 shows CoreEngine deviates from the
  frozen tgt (USTEC defer, ToUtc, kernel shapes) — "extract CoreEngine verbatim" would port
  those deviations into the book. G1 stays intact because FableFederation_V2 is not edited.
- **Integration (BookOrchestrator):** today the orchestrator drives CoreSim segment-batch
  from frozen seg CSVs [READ BookOrchestrator.mqh L17–63, L286–332]. Live mode replaces the
  file feed with: per M1 union bar, for each of the 9 legs with a bar this minute →
  `StepLegBar(leg, ..., tgt = signal.TgtAt(leg, ts))`; segment boundaries from the §4
  detector (FinishSegment → ComputeFCore → BeginSegment on trigger); the straddle-row guard
  and `a` leading-edge semantics stay per FABLE REVISION v2 item 2 (segment-batch exact in
  R1; hold-at-legcap incremental live with telemetry).

---

## 4. LIVE TRIGGER DETECTION — design + fork-by-fork resolution (Q3)

### 4.1 The anchor's semantics, pinned at code level [READ gbandrebal/sim.py]

- Slot equity series (`_run_window` L66–97): per slot = `combine_curves` of the slot's
  member-leg **close** curves (union of member stamps, ffill + first-in-window-value
  backfill) **+ the slot's flat legcap** (legs with no in-window bars), then
  `resample('D').last().dropna()` — the value at the slot's OWN last stamp of each raw-stamp
  calendar day. Slots with NO active legs → constant `seed·W` at the window start.
- Frame (`slot_frame` L55–63): union of the 7 slots' daily indices; `.ffill().bfill()`.
- Band test (`first_share_trigger` L67–83): `shares = sf / sf.sum(axis=1)` row-wise; scan
  daily rows with label `> cur` in order; skip a row if `(ts − cur).days < 5` (min-gap on the
  DECISION label vs segment start); skip if not `cur < act < probe_hi` (act = ts + 1 day);
  fire if `max_share > 0.25` or `min_share < (1/7)/1.75 ≈ 0.081633`.
- Harvest test (armed, never fired): `_first_trigger(slot, 2.5·seed·W, cur, probe_hi, 'D')`
  — first day-close with any slot equity > 2.5·seed/7, act next midnight, **no min-gap**;
  earliest of band/harvest wins (`earliest_trigger` L87–103).
- Probe loop (`run_generic` L119–127): re-run windows of 6/18/999 months until a hit with
  `act < probe_hi` or the probe covers `hi`.
- On fire: truncate at `index < act`, seed = last close < act, re-seed, `cur = act`.

### 4.2 Fork-by-fork (CORESIM_SPEC §6.3), each resolved with a measurement

| # | fork | resolution in this design | evidence |
|---|---|---|---|
| 1 | **min-gap basis** (EA fires 1 day early: `TimeCurrent()−g_quarterStart ≥ 5d` at ACT vs anchor `(decided−cur).days ≥ 5`) | Detector uses the ANCHOR basis: integer day count from the segment-start (act) date to the DECISION day label, `≥ 5`; a breach on a skipped day does NOT latch — each later day is re-tested on its own shares (the anchor `continue`s row by row) | [MEASURED] frozen run min gap = **12 days** (probe over the 31 triggers; no gap ≤ 7) — zero in-sample pressure, but the basis is still implemented exactly |
| 2 | **slot-mark basis** (anchor daily-close combined curves vs EA broker VBalance+FloatingPnL) | Slot equities computed from **CoreSim's own captured per-leg eq_c** — per slot: member-leg union, leg ffill + first-value backfill, left-to-right sum, + slot flat legcap, day-close at the slot's own last stamp of the raw day. No broker reads whatsoever | CoreSim already captures per-leg (ts, eq_c) [READ CoreSim.mqh m_ts/m_c]; identical combine semantics already bit-proven at book level (32/32) |
| 3 | **slot_frame `.bfill()`** (leading-edge lookahead) | R1/parity mode: retrospective backfill is available (segment-batch) → exact. LIVE streaming: hold-at-legcap before a slot's first daily point + telemetry | [MEASURED] max first-bar lag of ANY slot in ANY of the 32 frozen segments = **2 days** (weekend-start segments 18/20/24/29/30; probe over all seg CSVs) < the 5-day min-gap → band decisions can never read a bfilled row in-sample; harvest (no min-gap) could read the 2 leading days, but needs 2.5× seed·W within 2 days of an equal-capital reseed — and the anchor fired 0 harvests ever |
| 4 | **S6 aggregation** | Explicit leg→slot map `{0:0, 1:1, 2:2, 3:3, 4:4, 5:5, 6:5, 7:5, 8:6}` (7 slots); the 3 S6 legs sum into slot 5 BEFORE the share test; floor uses nSlots=7 | matches the anchor's slot dict and the EA's proven aggregation note [READ CoreEngine L731–741] |
| 5 | **probe-window act constraint** | No probe structure live. Equivalence argument: the slot values over overlapping days are probe-invariant (causal sim, same seed; bfill touches only the leading edge, same first values), so the 6/18/999-month escalation reduces to the single constraint `act < hi` with hi = 2026-01-01 (band arm edges = [LO,HI], no calendar cadence) — i.e. no constraint in-sample. The parity harness (§5) is the proof-by-measurement: 32/32 dates or the argument is wrong | [INFER + harness-gated] |

Additional anchor details the detector must keep: decisions are evaluated on EVERY day label
in the frame — **including weekends** (crypto slots print Sat/Sun; FX slots ffill) — and act
is next midnight even into a weekend. [MEASURED] one frozen trigger was decided on a
**Sunday** (act Monday); decided-dow histogram Mon..Sun = 12/3/4/6/5/0/1. The CoreSim reseed
is VIRTUAL (pure arithmetic) — no `AllMarketsOpen` deferral applies (unlike CoreEngine's
`g_pendResplit`); the real account repositions only through the normal f_core→blend→
`FED_Reconcile` path.

### 4.3 The detector algorithm (streaming, causal)

State: `seg_start_date` (act date of last reseed), `seed`, per-slot {per-leg cursor/ffill
value, first-value-seen flag, flat legcap}, per-slot daily-close ring (current + previous
day), the slot_frame ffill carry (last known day-close per slot), day-of-frame counter.

Per M1 union bar with raw-stamp day d:
1. If d > cur_day (rollover): for each slot, finalize cur_day's day-close (slot value at its
   own last stamp in cur_day; if the slot had no bar that day, carry the previous frame value
   — pandas ffill; if never seen: R1 mode = deferred backfill, live = legcap-hold). Then run
   the TESTS on cur_day's row:
   - band: shares = slot/Σ; fire if max > 0.25 or min < (1/7)/1.75, gated by
     `(cur_day − seg_start_date).days ≥ 5`;
   - harvest: any slot > 2.5·seed/7 (no gap gate);
   - if fired → act = d (the new day's midnight): `FinishSegment()` over bars < act,
     `ComputeFCore()`, `seed = FinalEqC()`, `BeginSegment(seed)`, `seg_start_date = act`,
     log the trigger row (decided, act, shares, seed).
2. Step the bar into the (possibly fresh) segment.

Because act is always a midnight and the first bar of day d is processed AFTER the rollover
test, the boundary is causal and lands exactly on the anchor's `index < act` truncation.

### 4.4 R1 mode vs LIVE mode (the honest split, mirroring FABLE REVISION v2 item 2)

- **R1 / parity harness (frozen bars):** segment-batch with exact anchor semantics —
  including slot-level first-value backfill — reproduced retrospectively. Target: EXACT
  (32/32 dates, seeds bit-equal).
- **LIVE / tester:** hold-at-legcap leading edges (slot daily curves AND the a-curve),
  plus divergence telemetry at the ≤2-day segment edges. Structural, measured, bounded by
  the ratified band — same treatment as the a_h leading edge. The harness ALSO runs the
  detector in live mode over the frozen bars and diffs the 32 dates: [MEASURED-ARGUED]
  expected identical (fork #3 evidence); if not, the delta is quantified before anything
  ships.

---

## 5. PARITY HARNESS SPEC (the gate before the live source carries weight)

Extend the S1 mirror chain (`research/bpure/book/book_orchestrator_sim.py` pattern):

1. **`research/bpure/coresim/coresignal_reference.py`** — python statement-mirror of
   `CCoreSignal` (pandas kernels = the anchor's own; consumes the frozen per-leg 1m bars
   from the seg CSVs or NSF5 `load_bars` READ-ONLY). Emits per-leg per-minute tgt on each
   leg's native in-window index.
   - **G-S1 (tgt identity):** diff vs the frozen `tgt` column of all 32 segment bundles,
     per leg. Report max|diff| + count-not-bit-equal. Expected residual class: the pandas
     EWM/rolling precedent (≤ ~4.2e-14) where kernels are re-implemented; 0.0 where the
     mirror literally calls pandas.
2. **G-S2 (account passthrough):** run `coresim_reference.py` account arithmetic on the
   LIVE-computed tgt (frozen trigger dates) → diff eqc/eqw/margin vs the parity parquet.
   Gate: bit-equal, OR (if G-S1 residual ≠ 0) zero **lot-decision flips** (the
   floor(x+1e-9)/band tests absorb eps or they don't — count the flips explicitly; a
   nonzero flip count is a FAIL escalation, not a tolerance).
3. **G-S3 (trigger identity):** run the §4.3 detector (both modes) on the live-tgt chain's
   slot equities over 2020–2025. Gate: **32/32 act dates exact** + every chained seed
   bit-equal to `triggers[j].book` + 0 harvest fires. Any 1-day fork = FAIL (it re-times
   every later segment).
4. **G-S4 (f_core):** `ComputeFCore` on the live chain vs the frozen hourly parquet — gate
   bit-equal (or bounded by G-S1's residual with the same flip-count discipline).
5. **G-S5 (MQL5 language layer):** `mt5/ea/scripts/CheckCoreSignal.mq5` — feed the same
   daily series into the compiled `CCoreSignal`, write the tgt stream, judge vs the python
   mirror (`validate_coresignal.py`) — bitwise, the RECON-8b/8d isolation discipline.
   Terminal run staged, owner-executed, ledgered as FMA3-RECON-N.

Gate ordering: G-S1 → G-S2 → G-S3 → G-S4 all-python first (no terminal); G-S5 after compile;
only then does the live source replace the frozen `tgt` feed in BookOrchestrator's live mode.

---

## 6. HONEST RISKS

1. **Kernel bit-parity is not free.** pandas `rolling.std` (roll_var kernel), `expanding
   median` (EG vol scale in fx_zrev is out of book, but eurgbp_zens uses rolling std),
   and the Donchian ffill state must be ported statement-faithfully; the f_sat precedent
   says expect a ≤5e-14 residual class, and §5's flip-count gates decide whether that
   residual is invisible (likely: lot flooring absorbs it) or fatal (a single flipped fill
   near a band edge). This is the largest genuine risk; it is measured, not assumed, by G-S2.
2. **Trigger detection is all-or-nothing.** One forked date re-times every later segment
   (CORESIM_SPEC §6.3 preamble). Mitigation: the G-S3 exact gate + the fork table §4.2 with
   in-sample slack measured (min gap 12 d, max slot lag 2 d). Residual risk: FORWARD
   (2026+) triggers can land in genuinely new regimes (gap=5 edges, leading-edge segments);
   the live-mode telemetry + refuse-to-trade-on-j-splice guard (v2 item 5(v)) is the
   containment.
3. **Deep-history dependence.** The Donchian breach state is formally unbounded (ffill from
   2020); the warm blob must carry it explicitly (§2.3) — a ring rescan alone is NOT
   guaranteed bit-exact after a long breach-free stretch.
4. **Live daily-mid vs frozen daily-mid (R2-class).** Live `(bid_c+ask_c)/2` from the broker
   feed ≠ frozen IC mids by construction → live daily coefficients drift within the ratified
   band. Not an R1 concern (harness uses frozen fields); listed so nobody grades the tester
   run against the R1 gate.
5. **Swap/eurq recompute forks return** the moment inputs are generated live (§2.2 adjacent
   scope) — mitigated by the bit-equal regeneration probe vs the exported arrays before the
   live generator is trusted.
6. **The 999-month-probe equivalence (§4.2 #5) is an argument, not yet a measurement** —
   G-S3 converts it into one.

## 7. OWNER DECISIONS

1. **Ratify the normative-source call:** CCoreSignal is ported from the NSF5 python target
   functions (with pandas-faithful kernels), NOT extracted verbatim from CoreEngine.mqh —
   because the frozen tgt provably diverges from CoreEngine's live conventions (USTEC
   Monday 23:00 defer, raw-hour vs ToUtc). CoreEngine stays untouched; G1 undisturbed.
2. **Ratify the trigger-mode split:** exact-semantics detection for the R1 harness;
   hold-at-legcap streaming live with telemetry, backed by the measured 2-day-lag /
   5-day-gap slack. Alternative (rejected): freezing 2020–2025 triggers in the EA and
   detecting only new ones — simpler, but creates two code paths whose seam is itself a
   fork surface; decide if the owner prefers it anyway for deploy safety.
3. **G-S2/G-S4 pass criterion** if G-S1 is not bit-zero: accept "0 lot-decision flips +
   residual ≤ 1e-12" as PASS, or require investing in bit-zero kernels first.
4. **Harvest arm:** keep k=2.5 armed live (anchor-faithful; never fired in-sample) — the
   leading-edge caveat (§4.2 #3) is accepted as measured-immaterial, or the owner may demand
   a min-gap on harvest too (would be a DELIBERATE divergence from the anchor; not
   recommended).
5. **Scope confirmation:** the live swap/eurq generator (adjacent §2.2) is S2 feed work —
   confirm it rides this track's harness (bit-equal regeneration gate) rather than a
   separate design pass.
