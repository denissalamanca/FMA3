# S2_PREP_STATUS — Track A (live-Core design) + Track B (state serializer) — 2026-07-14

Two parallel S2-preparation tracks, run before the main S2 build. Every claim below is
**[MEASURED]** (probe/gate run in this pass, artifact cited), **[READ]** (quoted from the
cited source), or **[INFER]** (deduced; harness-gated). Terminal-dependent gates are STAGED
and labelled — no terminal was launched from this repo.

- Track A artifact: `research/bpure/coresim/S2_CORE_LIVE_DESIGN.md` (design-only, no MQL5)
- Track B artifacts: `mt5/ea/Include/Book/BookState.mqh`, `research/bpure/book/book_state_mirror.py`,
  `research/bpure/book/run_state_split_gate.py`, gate results `research/bpure/book/book_state_gate.json`
  + `book_state_resume_parity.json`; S1 ledger entry appended to `model/v3/S1_STATUS.md`

---

## Track A — DESIGN of the live Core leg-target source + live band-trigger detection

**Verdict: DESIGN COMPLETE (VERIFIED design pass; implementation not started).**

### A.1 CTrade collision — REAL, three-layered, and MOOT under the design [MEASURED/READ]

The collision blocking "just include CoreEngine.mqh" is real and is three collisions stacked:

1. Duplicate file-scope global `CTrade trade;` — `Core/CoreEngine.mqh:68` vs
   `Book/BookExec.mqh:26` (the ONLY direct unprefixed symbol collision; grep-verified).
2. ~30 program-scope `Inp*` dependencies that `FableBook.mq5` redefines with DIFFERENT
   semantics — e.g. `InpMagicBase` 3900000 vs 360000 would overlap CoreEngine sleeve magics
   3900001–12 with FED per-symbol magics 3900001–33, corrupting BOTH deal-history sub-ledgers.
3. The `F3_*`/Federation dependency tree (V34Exec/Federation execution stack) that an include
   would drag into the book EA.

MOOT because the design extracts ONLY the signal layer into a new self-contained
`CCoreSignal` class (zero file-scope globals, zero `Inp*` reads, zero CTrade, zero account
calls). **CoreEngine.mqh is never included in FableBookNative and never edited — G1
(FableFederation_V2 proven asset) preserved.**

### A.2 Target path dissected to source — CoreEngine is NOT a faithful spec of the frozen tgt

- Normative source of the frozen `tgt` = **NSF5 python** `v52_alternatives.book("BTC_REP","USTEC")`
  at **R = 8.0 pure** — confirmed numerically FROM the frozen tgt values themselves
  (XAU 3.166667 = cap 6.0 × 0.19/0.36; USTEC Monday 6.25 = cap 10.0 × 0.15/0.24) [MEASURED].
  The shipped preset `InpRisk=8.96` embeds w·s downstream factors — do NOT copy into CCoreSignal.
- CoreEngine `CurrentTarget` measurably diverges from the frozen tgt:
  - **USTEC Monday exit 23:00 in frozen tgt vs 21:00 in CoreEngine** [MEASURED] — the outer
    `defer_reopen` (lock_v5.py:66) holds the 21:00 exit through the 21–22 window; CoreEngine
    exempts SL_US5 from the reopen window and drops at 21:00.
  - **Hour gates are RAW server-stamp hours** (XAU night transitions measured at raw
    20:00/08:00) vs CoreEngine's `ToUtc` conversion [MEASURED/READ].
  - **Kernel shapes differ** (pandas roll_var/Donchian-ffill/shift-label vs CoreEngine's
    scan-based RetStd/DonchSig re-derivations); bit-parity never established [READ].
- Signal path needs **ZERO account state**: 8 daily-mid ring series + deterministic calendars
  (opex 3rd-Friday week, raw hour/dow) + policy-rate tables + static params (R=8.0, vt/cap
  table). No VBalance/g_seed/HeldNet/OrderCalcMargin/AccountInfo. CoreSim's idealized state
  supplies everything the trigger needs.
- Warm-start inventory bounded (≤262-day rings) EXCEPT the two XAU Donchian last-breach flags
  (ffill-from-start, formally unbounded) — the warm blob must carry them explicitly.
- Adjacent S2 feed scope flagged: live `eurq` + swap triple generation (currently exported
  arrays; CORESIM_SPEC §9.4's "impossible by construction" guarantee dies live) — gated by a
  bit-equal regeneration probe vs the exported seg CSVs.

### A.3 Trigger detector — designed from CoreSim slot equities; all 5 CORESIM_SPEC §6.3 forks resolved

Streaming causal detector on CoreSim's own captured per-leg eq_c (no broker reads); leg→slot
map {0:0,1:1,2:2,3:3,4:4,5:5,6:5,7:5,8:6}; band max>0.25 / min<(1/7)/1.75; harvest 2.5·seed/7
armed; act = next midnight; reseed is VIRTUAL (no AllMarketsOpen gate). Three forks measured
slack in-sample [MEASURED over the 32 frozen segments]:

- min decided-gap **12 days** (vs the 5-day gate) — zero pressure, anchor basis implemented exactly;
- max slot first-bar lag **2 days** (weekend-start segments) < 5-day min-gap → band decisions
  can never read a bfilled row in-sample; harvest never fired in-sample;
- **one frozen trigger decided on a Sunday** (decided-dow Mon..Sun = 12/3/4/6/5/0/1) →
  weekend rows MUST be evaluated.

Mode split (mirrors FABLE REVISION v2 item 2): R1 harness = exact anchor semantics including
retrospective bfill (segment-batch); LIVE = hold-at-legcap streaming + edge telemetry. The
999-month-probe equivalence is [INFER + harness-gated] — G-S3 converts it into a measurement.

### A.4 Parity gates specified (the gate before the live source carries weight)

G-S1 tgt identity (mirror vs frozen tgt, all 32 bundles) → G-S2 account passthrough
(bit-equal OR zero lot-decision flips — a nonzero flip count is a FAIL escalation, not a
tolerance) → G-S3 trigger identity (**32/32 act dates exact + every chained seed bit-equal +
0 harvest fires**; any 1-day fork = FAIL, it re-times every later segment) → G-S4 f_core →
G-S5 MQL5-vs-mirror bitwise (`CheckCoreSignal.mq5`, STAGED terminal run, owner-executed,
ledgered FMA3-RECON-N). All-python G-S1..G-S4 first; no terminal until G-S5.

### A.5 OWNER DECISIONS surfaced by Track A (unsoftened — these block the S2 build)

1. **Ratify the normative-source call:** CCoreSignal is ported from the NSF5 python target
   functions (pandas-faithful kernels via SatMath), NOT extracted verbatim from
   CoreEngine.mqh — because the frozen tgt PROVABLY diverges from CoreEngine's live
   conventions (USTEC Monday 23:00 defer, raw-hour vs ToUtc). CoreEngine stays untouched.
2. **Ratify the trigger-mode split:** exact anchor semantics (incl. retrospective bfill) in
   the R1 harness; hold-at-legcap streaming live with telemetry (backed by the measured
   2-day-lag / 5-day-gap slack). Rejected alternative on the table if the owner prefers
   deploy safety over one code path: freeze the 2020–2025 trigger dates in the EA and detect
   only new ones — simpler, but the two-path seam is itself a fork surface.
3. **G-S2/G-S4 pass criterion if G-S1 is not bit-zero:** accept "0 lot-decision flips +
   residual ≤ 1e-12" as PASS, or require investing in bit-zero kernels first.
4. **Harvest arm:** keep k=2.5 armed live (anchor-faithful, never fired in-sample; the
   2-day leading-edge caveat measured immaterial), or demand a min-gap on harvest too — a
   DELIBERATE divergence from the anchor, not recommended.
5. **Scope confirmation:** the live swap/eurq generator is S2 feed work riding this track's
   harness (bit-equal regeneration gate), not a separate design pass.

---

## Track B — whole-book state serializer BUILT + warm-start gate PASS (v2 item 5(v), S2 item 4 pulled forward)

**Verdict: BUILT + python gate MEASURED PASS; MQL5-side terminal gate STAGED.**

### B.1 What was built [READ repo; MQL5 compiles per S1_STATUS Track-B ledger entry]

- `mt5/ea/Include/Book/BookState.mqh` — `CBookState`: complete-ledger JSON at **%.17g**
  (binary64 round-trip, never truncated — the legacy 4-decimal SaveState re-basing failure
  mode is the design target); atomic publish (tmp → `FileDelete`+`FileMove`); **fnv64/eof
  torn-write marker protocol** (FNV-1a 64 over the payload + trailing eof marker — any
  partial/interleaved/bit-flipped write is detectable on load regardless of rename-atomicity,
  which is NOT certifiable from this repo); validating load (schema/version, fixed-width
  array enforcement, NaN/Infinity-aware parsing); **continuity guard**: recompute
  `j_restored = w·a_h + (1−w)·b_h` from the restored samplers and REFUSE_TO_TRADE latch
  (`Ready()/RefuseToTrade()/RefuseReason()`) on any a_first/b_first bit difference, j_hour
  mismatch, or relative j jump > 1e-9.
- Additive `BsWriteState/BsSetState/BsContinuity` hooks in `BookOrchestrator.mqh` + sampler
  `Restore` + CoreSim carry/f_core restore hooks — compute paths untouched; TestBook,
  CheckBookOrchestrator, CheckFCore, TestCoreSim recompiled 0/0 (S1 gate intact).
- `research/bpure/book/book_state_mirror.py` — python statement-mirror (same envelope,
  trailer, continuity law). **Documented divergence:** the four struct-state sleeve inner
  payloads are language-canonical — each side round-trips its OWN files bit-exact;
  cross-language state exchange is NOT certified.
- `mt5/ea/scripts/checks/CheckBookState.mq5` — synthetic split/continue + refuse battery,
  compiled 0/0, **terminal run STAGED** (owner-executed, to be ledgered FMA3-RECON-N).

### B.2 MEASURED warm-start gate (RECON-8d split pattern) — `book_state_gate.json` PASS

- Baseline regression guard: uninterrupted S1 mirror still PASSES R1 vs golden
  (max|diff| 5.06e-13, 0 rows > 1e-12, 805,585 rows) — the sim edits changed nothing.
- Split at 2022-06-30 23:00 UTC (epoch 1656630000): state saved (7,233,148 bytes,
  rows_offset 251,354, j = 5.935576542054057); FRESH mirror restored (guard passes,
  a_first/b_first bit-equal 10000.0) and continued to end:
  - **tail 554,231 rows BITWISE IDENTICAL** to the uninterrupted baseline (exact %.17g
    strings, 0 diffs, first_divergence = null);
  - tail also passes vs the GOLDEN tail: max|diff| 5.05e-13, 0 rows > 1e-12;
  - **end states byte-identical** (7,845,417 bytes) — endRESUME ≡ endBASE.
- Runtime 230.4 s total (resume leg 224.8 s).

### B.3 MEASURED refuse-latch unit-test battery (all on the boundary file)

| test | tamper | result |
|---|---|---|
| t_pass | none (control) | loads, guard passes, j = 5.935576542054057 |
| t_torn | truncation | **REFUSED** — "TORN WRITE: eof marker missing" |
| t_flip | payload bit-flip, stale fnv | **REFUSED** — "CHECKSUM MISMATCH" (fnv64) |
| t_anchor | continuity a_first ×1.01, fresh trailer | **REFUSED** — "A-ANCHOR MISMATCH: 10000 != 10100" |
| t_splice | CONSISTENT re-base (sampler first_v AND anchor ×1.01, fresh trailer) | **REFUSED** — "J-SPLICE DISCONTINUITY: rel 0.0069 > 1e-9 — REFUSE TO TRADE" |

t_splice is the design-critical case: a consistent re-base passes the anchor equality and
every sub-checksum yet silently mis-weights every trade — the j-splice latch is the ONLY
thing that catches it, and it does [MEASURED].

---

## What the full S2 build needs next

1. **Owner rulings on the five Track-A decisions (§A.5)** — items 1–3 block CCoreSignal
   implementation; 4–5 block detector/feed finalization.
2. **Build the Track-A harness chain (all-python, no terminal):**
   `coresignal_reference.py` → G-S1 (tgt identity vs all 32 frozen bundles) → G-S2 (account
   passthrough, flip-count discipline) → G-S3 (trigger 32/32 + seeds bit-equal, both modes)
   → G-S4 (f_core). Then `Core/CoreSignal.mqh` + `CheckCoreSignal.mq5` to 0/0 and G-S5.
3. **Live feed assembler extensions:** daily-mid derivation from the union M1 stream
   (last-bar-of-raw-day `(bid_c+ask_c)/2`; EG pre-20 variant) shared by harness and live;
   live eurq + swap-triple generator with the bit-equal regeneration probe vs exported segs.
4. **Staged terminal runs (owner-executed, each → FMA3-RECON-N):** CheckBookState (Track B
   MQL5 split/refuse gate) and later CheckCoreSignal (G-S5). Wine `FileMove` rename-atomicity
   remains uncertified from this repo — the marker protocol is the load-time backstop either way.
5. **Wire live mode in BookOrchestrator** (per §3 of the design): frozen-CSV feed →
   per-union-bar `StepLegBar(..., tgt = signal.TgtAt(leg, ts))` + detector-driven
   FinishSegment/ComputeFCore/BeginSegment — only AFTER G-S1..G-S5 pass.
6. **Warm-blob completeness check** for CCoreSignal state (incl. the two unbounded Donchian
   breach flags) folded into the Track-B serializer schema (version bump when added).
