# FMA2 EA-stack audit — tester-ready punch list for the v3.4 sub-book MT5 run

**Audited 2026-07-10.** Scope: the whole `FableMultiAssets2/ea/` tree (Python brain, MQL5 executor,
tester variant, watchdog, tests, bridge configs), `FMA2/docs/v2.0/EA_MONITORING_SPEC.md`,
`FMA2/docs/v3.4/{DEMO,PREPROD,RECONCILIATION}.md`, and the FMA3 intel
(`research/intel/v34-code.json`, `registries-deadends.json`). Every claim below is cited to a file;
parents were read only. Purpose: answer *"can the v3.4 sub-book run in the MT5 Strategy Tester, and
what exactly stands between here and (a) that run, (b) the live demo"* — the run being the missing
half of the IC k-calibration (`research/protocol/DEMO_PREREGISTRATION.md` §5).

> **SUPERSEDED / PROVISIONAL (2026-07-11).** This doc's dial framing assumes s=1.6 as the shipped IC
> dial (deploy sizings GLOBAL_SCALE 3.0×1.6=4.80, InpRisk 5.6×1.6=8.96). Those are **superseded for
> the owner's confirmed retail 1:30 account**: the margin gate binds before drawdown, so s=1.6 (and the
> 4.80 / 8.96 sizings) is not deployable on that leverage. Deployable band is **s≈0.6–0.8**; the binding
> constraint is retail-1:30 margin feasibility, not k_dd/k_tail. The final IC dial is pending the G3b
> real-tick reconciliation (FMA3-RECON-2); k-calibration is now governed by the new
> `research/protocol/RECONCILIATION.md`, not the DEMO_PREREGISTRATION k-only framing. The tester run
> itself remains valid work — only the dial it is scored against changes.

---

## 0. Headline findings (read this if nothing else)

1. **The tester problem is already solved — and staged.** The generic objection is real (a
   Python-brain bridge cannot run inside the Strategy Tester; the tester has no external process,
   no live comms dir), but FMA2 already built the NSF5-pattern answer: a **tester-replay variant of
   the production executor** (`ea/mt5_tester/FableMultiAsset2_V34.mq5`) that replays a frozen
   hourly-targets CSV through the *identical* live execution pipeline. The frozen replay file is
   already generated and validated (`ea/bridge/replay/FableMA2_V34_replay.csv`, 851,013 data rows,
   2020-01-02→2025-12-31, header `global_scale=10.0,config_hash=48c09199fbf83d82`), the preset
   exists (`FableMultiAsset2_V34_S10_IC.set`, `InpTesterReplay=true`), and the operator run-sheet
   says "Staged (done)" (`ea/mt5_tester/RUNSHEET.md`). **What remains is literally: one GUI compile
   (MetaEditor F7 — headless compile no-ops under the Wine build), symbol-history download, and
   tester wall-clock.** Zero new code is required for the tester run.
2. **The four "owed" guard fixes (OPS-3b / OPS-6a / OPS-8 / MKT-7) are DONE, not owed.** The FMA3
   intel (`v34-code.json` key_facts "guard fixes owed"; `DEMO_PREREGISTRATION.md` §6 repeats it) is
   **stale on this point**: all four are implemented in the compiled EA
   (`ea/mql5/Include/FableGuards.mqh` header + bodies; OPS-3b absolute-bp ring in
   `FableExec.mqh::ProcessDealAdd`), pinned brain-side (`ea/brain/guards_engine.py`,
   `ea/brain/README.md` §"four guard fixes"), and the MAG kill triggers `DUR-mag_xau-sharpe` /
   `DUR-mag_xau-drift` are registered in `research/outputs/guards_config.json` (57 guard ids).
   The **v2.1 `n_ticks` liquidity guard remains genuinely open** — `n_ticks` exists only as a bar
   column (`ea/brain/data_feed.py`), no guard consumes it anywhere.
3. **Three demo-blocking glue gaps exist that do NOT affect the tester run** (details §2/§4):
   the live MQL5 executor **never checks `config_hash`** (the guard everyone cites exists only in
   the Python reference contract and in the tester-replay loader); the EA **never exports bars**
   (the brain's live data feed input, `ea/bridge/bars/`, is empty and its format marked
   "provisional"); and the EA **never reads `kill_switch.json`** (the watchdog's only write channel
   is unconsumed). Plus a comms-filename mismatch set between EA ↔ watchdog ↔ brain.
4. **6095 tests verified** (counted from `ea/.pytest_cache/v/cache/nodeids`) — but per FMA2's own
   RECONCILIATION caveat 2, they validate the *Python reference spec*, not the MQL5 code or broker
   fills. Real-tick parity is §C-OPEN by FMA2's own admission; the tester run is what closes it.

---

## 1. Architecture map — how the bridge works

### 1.1 Components (all paths under `/Users/dsalamanca/vs_env/FableMultiAssets2/ea/`)

```
brain/ (Python, hourly)                      mql5/ (MQL5, live executor)
  brain_config.py  config/paths/magic/hash     FableExecutor.mq5   OnTimer 30s driver
  target_engine.py combine×scale+hard limits   Include/FableCommon.mqh  magic map, enums
  data_feed.py     bars in (EA→brain) [GAP]    Include/FableJson.mqh    JSON parser
  guards_engine.py Tier-C batch guards         Include/FableBridge.mqh  atomic file I/O, ledgers
  reconcile.py     restart/desync protocol     Include/FableExec.mqh    order pipeline
  run.py           cron/loop orchestrator      Include/FableGuards.mqh  Tier-A guards + 4 fixes
bridge/  targets.json · commands.json ·      mt5_tester/ (tester-replay variant)
  state.json · heartbeat*.json · ledgers/      FableMultiAsset2_V34.mq5 + Include/FableMA2/*
  bars/ [EMPTY] · replay/FableMA2_V34_...csv   FableMultiAsset2_V34_S10_IC.set · RUNSHEET.md
watchdog/watchdog.py (915 ln, off-VPS)       tests/ 6095 cases + tests/reference/* (contract)
```

### 1.2 Decision flow (live mode)

- **Brain (hourly, `run.py --once` cron):** reconcile gate → `target_engine.build_targets()`
  (research-parity: frozen sleeve parquets → `combine × GLOBAL_SCALE` → `structural_gold_cap` +
  `apply_hard_limits`, cash-park, per-sleeve magic distribution) → atomic write
  `bridge/targets.json` (`fable.targets.v1`, monotonic `seq`, stamped `config_hash`) + brain
  heartbeat. Tier-C guards run daily and translate fires into `commands.json`
  (`fable.commands.v1`: de-gross-only overrides, sleeve kills, crypto close-only, cash-park
  fallback). Contract authority: `ea/bridge/PROTOCOL.md`.
- **Executor (`FableExecutor.mq5::OnTimer`, 30 s):** `LoadCommands` (act on seq increase) →
  `LoadTargets` (ignore stale seq) → always-on guards (`CheckDST`, `PollCryptoTradeMode`,
  `CheckMarginGuards`, `CheckMarginSchedule`, `CheckDDFloor`) → 15-min OPS-1a reconcile →
  `RunForcedExits` (21:05 intraday / 06:05 seasonal fire-and-confirm, escalation at T+5) →
  `Rebalance()`: copy target vector → `ApplyCommandsAndCrossCap` (kills/scales/MKT-8a cross cap) →
  `ApplyPortfolioCaps` (MKT-4a overnight-gold aggregate, MKT-7b notional ratchet) → per leg
  `LotsFromExposure` (exposure × live equity ÷ px·contract·EUR-conv) → `NormalizeVolume` (the one
  volume path: step/min/max/limit, drop+log with OPS-6a retention) → reduce-only clamps
  (halt/freeze/no-entry/DST/crypto-close-only) → `ExecTarget` diff-vs-held with 0.25 rebalance
  band → flatten-by-omission of uncovered (symbol,magic) → `RetryPending` → `WriteState` (atomic,
  write-after-ack) + `WriteHeartbeat`.
- **Order lifecycle (`FableExec.mqh::SendOne` — every order goes through it):** spread guard
  (per-hour 30-d median, forced exits exempt) → `OrderCalcMargin` pre-check with free-margin buffer
  → full retcode matrix (REQUOTE/PRICE backoff, INVALID_FILL filling-mode rotation, NO_MONEY
  stepwise halving, MARKET_CLOSED → pending queue + escalation if forced, INVALID_STOPS drop-SL,
  partial-fill remainder re-issue) → catastrophic broker-resident SL ≈ 3×ATR(14) at entry →
  `OnTradeTransaction`/`ProcessDealAdd` appends the slippage ledger and feeds the OPS-3b ring,
  detects OPS-9c stop-outs, and persists state on every fill ack.
- **Tick handling:** live mode is `OnTimer`-driven; `OnTick` is a deliberate no-op
  (`FableExecutor.mq5` line ~368). All schedule logic is `TimeTradeServer()` (OPS-5a).
- **Watchdog (`watchdog/watchdog.py`, second host):** reads a mirrored comms dir, checks EA/brain
  heartbeat staleness, forced-exit windows, DD ladder, transport health; its only write is
  `kill_switch.json` (dry-run and drill support built in).

### 1.3 Tester-replay variant (`mt5_tester/`)

Same executor, byte-equivalent live path (verified by diff: the 5 includes differ only in include
guards/namespacing, the `FableMA2_V34_` runtime-file prefix, a compiled
`FABLE_MA2_CONFIG_HASH "48c09199fbf83d82"` constant, an `MQL_TESTER` DST shim, and two benign
compile fixes). When `InpTesterReplay=true`: `OnInit` loads the frozen CSV from `Common/Files`
(**hard-fails INIT on config-hash mismatch**), seeds `CommandsDefault` + the shipped v3.4 hard-limit
caps; `OnTick` detects new H1 bars and swaps in the just-closed hour's frozen rows
(O(rows) forward cursor; empty hour = keep-last-good, mirroring live), then runs the *exact same*
guard + rebalance + persistence sequence as live `OnTimer`. Diagnostics: one crash-safe
append+flush run-log at a fixed Common path (`FableMA2_V34_tester_run.log`) with an `OnTester`
RESULT line (profit, eqDD, trades, Sharpe, PF, final ML). Signals are never computed in MQL5 — the
"signals computed once, in Python" invariant survives the tester.

The replay CSV is produced by `research/export_mt5_replay.py`, which **reuses the production brain
path** (`target_engine.build_book(rebuild=False)` on frozen parquets — no 1m cache, no record
engine), takes exit metadata and magics verbatim from `brain_config`, writes server-wall-clock
epochs matching `iTime()` semantics, and re-parses/validates its own output (leg sums vs
`net_capped`, header hash/scale asserts). It hard-fails on config-hash drift.

---

## 2. Completeness matrix

| Component | State | Evidence |
|---|---|---|
| **Signal computation (brain)** | **DONE** (frozen-parquet path) / **PARTIAL** (live recompute) | `target_engine.py` mirrors `run_v2_pin`/`eval_v34_pin` construction (research parity, cash-park, structural gold cap); `--rebuild` recompute path exists. PARTIAL because the live feed input is missing (see "bar export" below) — on a live demo the brain would compute off the frozen 2020-25 cache until bars flow. |
| **Position sizing** | **DONE** | `FableExec.mqh::LotsFromExposure` + `NormalizeVolume` (clamp/step/split/limit/drop+log); property-fuzzed (`tests/test_volume_fuzz.py`, `test_volume_normalization.py`); OPS-6a retention ledger on drops. |
| **Hard limits (defense-in-depth)** | **DONE** | MKT-4a overnight-gold aggregate + MKT-7b ratchet in `FableGuards.mqh::ApplyPortfolioCaps`; MKT-8a cross cap in `ApplyCommandsAndCrossCap`; brain clips first (`target_engine`); tester seeds the same caps in `OnInit` (`FableMultiAsset2_V34.mq5` ~392-397); `tests/test_hard_limits.py`. |
| **Order execution** | **DONE** | `SendOne` full retcode matrix, filling-mode rotation, margin pre-check, session queue, partial-fill handling, catastrophic SL, maker-first policy compiled but `InpMakerFirst=false` (demo-gated). |
| **Reconciliation logging** | **DONE** (EA-side) | `state.json` atomic write-after-ack; `slippage_ledger.csv` per fill (`ProcessDealAdd`); `retention_ledger.csv`; `events.csv`; `escalations.json` for forced-exit-into-closed-market. |
| **Restart recovery** | **DONE** (unit-proven) | `OnInit`: HWM restore from persisted state, OPS-1a reconcile-don't-recompute (reduce-only excess close, 4 h entry freeze, adopt-clean), OPS-9c stop-out → desync; brain-side `reconcile.py` mirrors it. Never exercised against a real broker restart (FMA2 §C-OPEN, disclosed). |
| **Guards — Tier A (EA)** | **DONE incl. the 4 fixes** | OPS-1a/2/3a/3b/4/5b/6a/7c/8a/8b/9a/9b/9c, MKT-3a/3b/3c/4a/7b/8a all present in `FableGuards.mqh`/`FableExec.mqh`; OPS-3b absolute-bp ring; OPS-6a change-only retention; OPS-8 cash-park latch (never renormalize); MKT-7b ratchet. `tests/test_guards.py`. |
| **Guards — Tier C (batch)** | **DONE** | `guards_engine.py` (546 ln): durability kills, MKT-1/2/5, OPS-6b equity floor → `commands.json` de-gross-only; `DUR-mag_xau-*` registered in `guards_config.json`. |
| **Guards — `n_ticks` liquidity (v2.1 owed)** | **MISSING** | `n_ticks` is only a schema column (`data_feed.py:38,77`); no consumer in `guards_engine.py` or the EA. Pre-real-capital item per `DEMO_PREREGISTRATION.md` §6. |
| **Config-hash guard — tester** | **DONE** | `LoadReplayFile` vs compiled `FABLE_MA2_CONFIG_HASH` → `INIT_FAILED` on mismatch. |
| **Config-hash guard — LIVE executor** | **MISSING** | `FableBridge.mqh::LoadTargets` (lines 132-184) parses `seq/global_scale/hard_limits/targets` and **never reads `config_hash`**; no hash constant exists in the live includes. The `config_hash_mismatch` rejection lives only in `tests/reference/targets.py::accept` (Python). PREPROD §4, `protocol_notes.md` ("A drifted hash ⇒ the EA rejects the target") and **FMA3 `docs/v1.0/DEMO.md` step 4** all assert a live guard that is not in the MQL5. |
| **Bar export EA→brain** | **MISSING** | `ea/bridge/bars/` contains only `.gitkeep`; no `bars` writer anywhere in `mql5/`; `data_feed.py` header says format "provisional". |
| **Kill-switch consumption** | **MISSING** | `kill_switch.json` written by `watchdog.py` (KillSwitch class); zero reads in `mql5/` or `mt5_tester/`. RUNBOOK §1 ("the EA polls it on its timer and obeys") is unimplemented. |
| **Comms filename contract** | **PARTIAL** | Watchdog expects `heartbeat_ea.json`, `broker_snapshot.json`, `guard_events.jsonl` (`watchdog.py:63-70`); EA writes `heartbeat.json`, `state.json`, `events.csv` (`FableBridge.mqh` F_ defines); brain guards write `alerts.jsonl`; brain `reconcile.py` reads `broker_positions.json` which **nothing writes**. As wired, the watchdog would see the EA as permanently dead and the brain reconcile as position-less. |
| **Watchdog** | **DONE standalone / PARTIAL integrated** | 915 ln, alert ladder, DD/forced-exit/transport checks, dry-run, drills — but see filename row and kill-switch row. |
| **Tester harness** | **DONE, staged, UNRUN** | `mt5_tester/*` + replay CSV + preset + `RUNSHEET.md` + `COMPILE-CHECKLIST.md`; run never executed (RECONCILIATION §C OPEN). |
| **Tests** | **DONE (reference-level)** | 6095 node-ids in `.pytest_cache`; targets protocol/hash, retcode matrix, volume, hard limits, guards, reconcile. Caveat (FMA2's own): they prove the *spec*, not the MQL5. Also `protocol_notes.md` #2: `tests/reference/targets.py` still carries a simpler v2.0 dict schema vs the authority `fable.targets.v1` list (hash function is shared and schema-independent — the one part the brain borrows). |
| **Docs** | **PARTIAL (known drift)** | `RUNBOOK.md` §1.2 still prints the v3-era 920001-7 magic map and §4 the old 1.0×E gold cap / "scale 9→7" line; `tests/README.md` says "94 tests". All flagged in RECONCILIATION §"Honest caveats" #4 — prose drift, not code. |

---

## 3. Tester-readiness — the honest assessment

**Can the current stack run in the MT5 Strategy Tester at all?** The *live bridge* cannot — the
tester has no external Python process, no shared live comms loop, and `OnTimer`-driven file polling
against a brain that isn't running would produce nothing. FMA2 knew this and built around it. The
three options, assessed:

**(a) Pure-MQL5 port of the v3.4 signal set — REJECT.**
Effort **L** (weeks: 7 sleeves + mag_xau, EWMA/Donchian/z-machinery, cross-sleeve grid semantics,
then a *second* reconciliation of MQL5-signals-vs-Python-signals before you can even measure
execution). It violates the architecture invariant ("signals are computed once, in Python" —
`PROTOCOL.md` header) and creates a permanently divergent second implementation. Nothing about the
k-calibration needs it.

**(b) Tester-replay EA executing a pre-computed decision file — EXISTS, STAGED. Effort S.**
This is exactly the NSF5 pattern (PortfolioV7 ↔ decisions.csv reference reconciliation), already
implemented in the parent: `FableMultiAsset2_V34.mq5` + `Include/FableMA2/*` + validated exporter
(`research/export_mt5_replay.py`) + frozen CSV (851,013 rows, sha256-recorded in `RUNSHEET.md`) +
preset + run-sheet + compile checklist. The replay path exercises the full production pipeline
(NormalizeVolume, session queue, hard-limit re-clip, Tier-A guards, forced exits, slippage ledger)
on real IC ticks — which is precisely what the k-calibration wants to measure. Remaining effort is
operational, not engineering: **GUI compile (F7), Market-Watch symbol prep, tester wall-clock (6y ×
30 symbols × every-tick — expect a long run), log collection.** No FMA2 code changes; the parents
stay read-only.

**(c) Skip the tester; calibrate the v3.4 slice's k on demo data — LEGAL INTERIM, NOT THE ANSWER.**
`DEMO_PREREGISTRATION.md` §5.1 pre-authorizes exactly this asymmetry ("if the v3.4 tester harness
is not ready at deploy, k is measured first on the v7 stack + the live demo curve, and the
federation k is completed when the v3.4 tick run exists"). But: the demo window has no guaranteed
crisis, so **k_tail — the number the whole exercise exists for** (v7 precedent: 35.6% tick vs ~7%
record) — is unmeasurable from a calm demo; and the harness *is* ready, so invoking the fallback
buys almost nothing. Effort saved ≈ one compile + one long tester run. Use (c) only as the
pre-registered interim if the tester run drags past deploy day.

**Verdict: option (b), which is not a build but a run.**

**One open decision — the dial.** The staged run is at the v3.4 *native* scale 10 (hash-gated to
`48c09199fbf83d82`, matching the official pin `v34_s10_pin_1m.json`, DD 21.67%). The FMA3 protocol
(§5.1) says "at the deployed dials" — for the IC preset (s=1.6, FMA3-004c) the v3.4 stack deploys
at `GLOBAL_SCALE = 3.0×1.6 = 4.80` (a 16-equivalent per sub-capital). Two defensible routes:

- **Run-1 (do now): staged scale-10.** Zero new artifacts; k_dd = tick-worst-DD ÷ 21.67% and k_tail
  vs the pin's COVID window are ratios against the *official* record pin — the cleanest per-stack k.
  Disclose in the §5 addendum that the per-stack k was measured at the native dial (a
  dial-invariance approximation; k is not exactly scale-free because margin/stop-out/min-lot
  effects are nonlinear).
- **Run-2 (optional, strict-protocol): deployed-dial 4.80.** Requires regenerating the replay in a
  *deploy copy* of the ea/brain tree (scale change → `config_hash` restamps automatically →
  update `FABLE_MA2_CONFIG_HASH` in `FableCommon.mqh` + `EXPECTED_HASH` in the exporter → re-export
  → recompile). Effort **M**; uses only frozen parquets (no 1m-cache, no record engine — compatible
  with the busy-engine rule). Bonus: it exercises **min-lot truncation at the actual deployed
  sizing** — FMA3 DEMO.md's own first suspect for `volume_rejects` ("the 3.3-scale slice trades
  smaller lots than anything FMA2 ever demoed"; 4.8 is better but the point stands). Because the
  parents are read-only for this campaign, Run-2's edits happen in the owner's MT5 deploy copy (or
  are owed to the FMA2 side), not in the FMA2 repo.

Recommended sequencing: Run-1 immediately (it is the FMA2 §C reconciliation the parent itself owes,
and it produces a usable k); decide on Run-2 after seeing Run-1's retention and reject counts.

---

## 4. Punch lists

### 4.1 To TESTER-READY (the k-calibration blocker) — ordered

| # | Item | Effort | Where |
|---|---|---|---|
| T1 | Stage files into the MT5 terminal: `mt5_tester/FableMultiAsset2_V34.mq5` → `MQL5/Experts/`, `mt5_tester/Include/FableMA2/*` → `MQL5/Include/FableMA2/`, preset → `MQL5/Presets/`, `bridge/replay/FableMA2_V34_replay.csv` → **`Common/Files/`** (per `COMPILE-CHECKLIST.md`; RUNSHEET says already done on the owner's terminal — verify) | S | owner machine / FMA3-side ops |
| T2 | Compile in MetaEditor (**GUI F7**; headless `metaeditor64 /compile` no-ops under this Wine build). Expect 0 errors per `COMPILE-CHECKLIST.md` | S | owner machine |
| T3 | Market Watch: all 30 book symbols selected with real-tick history downloadable (list: `awk -F, 'NR>1{print $2}' FableMA2_V34_replay.csv \| sort -u`); a missing symbol under-fills rather than crashes — check coverage BEFORE the long run | S–M (download wall time) | owner machine |
| T4 | Run: Expert `FableMultiAsset2_V34`, symbol EURUSD H1 (chart only), model **every tick based on real ticks**, 2020.01.01–2025.12.31, deposit €10,000 EUR, **hedging** account (EA hard-fails INIT on netting — by design), preset `FableMultiAsset2_V34_S10_IC.set` | M (wall-clock heavy: 6y × 30 sym × every-tick) | owner machine |
| T5 | Collect: `Common/Files/FableMA2_V34_tester_run.log` (INIT banner, WARN/ALERT stream, `OnTester` RESULT line), agent-sandbox `FableMA2_V34_events.csv`, tester HTML/XML report + deal history | S | owner machine → FMA3 |
| T6 | Reconcile the run into the retention read: retention vs the 88.66% pin, `volume_rejects` (must be 0), forced-exit hit rate, guard fires, margin profile. Write-up lands FMA3-side (parents read-only): extend `FMA3/docs/v1.0/RECONCILIATION.md` + the DEMO_PREREGISTRATION §5 addendum; flag to the owner that FMA2's own `docs/v3.4/RECONCILIATION.md` §C wants the same content when FMA2 is writable | M | FMA3-side |
| T7 | Compute the v3.4-stack **k_dd** (tick worst-mark maxDD ÷ 0.2167) and **k_tail** (tick COVID-window relative DD ÷ record crisis tail) from the report/deal history; may need a small equity-curve rebuild script from the exported deals | S–M | FMA3-side wrapper (`scripts/`) |
| T8 | *(Optional, strict deployed-dial)* Regenerate replay at `GLOBAL_SCALE=4.80` in a deploy copy: scale change → new stamped hash → update `FABLE_MA2_CONFIG_HASH` (FableCommon.mqh, tester copy) + `EXPECTED_HASH` (export_mt5_replay.py) → re-export (frozen parquets only) → recompile → rerun T4–T7 at the deployed sizing | M | owner deploy copy (FMA2-repo change if parents become writable) |

**Nothing in T1–T7 touches FMA2 source, the record engine, or the 1m cache.** The tester run is on
the owner's MT5, which the busy-engine rule does not constrain.

### 4.2 To DEMO-READY (different list — the glue gaps) — ordered by risk

| # | Item | Effort | Where |
|---|---|---|---|
| D1 | **Live config-hash guard in the executor.** Add a compiled expected-hash input/constant and reject `targets.json` whose stamped `config_hash` differs (CRITICAL event + keep-last-good/halt-entries). Today nothing EA-side stops a stale scale-10 target file from trading at ~3× the deployed FMA3 size — and FMA3 `docs/v1.0/DEMO.md` step 4's safety argument assumes this guard exists. ~20 lines in `FableBridge.mqh::LoadTargets` + a `FableCommon.mqh` constant + tests | S | **FMA2-repo engineering** |
| D2 | **EA bar exporter** (closed H1 bars per symbol → `ea/bridge/bars/<SYM>_1h.csv` per `data_feed.py`'s provisional schema), or an equivalent VPS-side feed writer. Without it the live brain cannot compute fresh targets past the frozen cache — the demo would trade an increasingly stale book | M | **FMA2-repo engineering** |
| D3 | **Kill-switch consumption in the EA** (poll `kill_switch.json` on timer; obey `HALT_FLATTEN` / `HALT_NO_NEW_ENTRIES` / `RESUME`-only-clears-halt semantics per RUNBOOK §1.1). The entire watchdog escalation ladder (fallbacks #3/#4, drills §9) is inert until this exists | S–M | **FMA2-repo engineering** |
| D4 | **Comms contract alignment**: EA heartbeat filename (`heartbeat.json` → `heartbeat_ea.json` or watchdog config), a `broker_snapshot.json`/`broker_positions.json` writer (EA-side; also unblocks brain `reconcile.py`'s broker leg), and one guard-event stream the watchdog actually reads (`events.csv`/`alerts.jsonl` vs expected `guard_events.jsonl`) | M | **FMA2-repo engineering** (+ watchdog config) |
| D5 | **FMA3 deploy artifacts** (DEMO.md "What does NOT exist yet" #8, updated to the shipped preset): v7 preset copy with `InpRisk = 5.6×1.6 = 8.96`; v3.4 deploy copy with `GLOBAL_SCALE = 4.80`; record the re-stamped deploy hash; dated DEMO_PREREGISTRATION §2 addendum (preset, s*, bands, k arithmetic) | S | **FMA3-side** |
| D6 | **`n_ticks` liquidity guard** (v2.1 owed; consumes D2's bars in `guards_engine.py`) — pre-real-capital, not demo-start | S–M (after D2) | FMA2-repo |
| D7 | Doc-drift pass: RUNBOOK magic map 920001-7 → 8400001-8, gold cap 1.0×E → structural 1.80×E, "scale 9→7" wording; `tests/README.md` count; `EA_MONITORING_SPEC.md` §3 OPS-8 "re-normalized" → cash-park (code already cash-parks) | S | FMA2-repo housekeeping |
| D8 | Watchdog §9 drills (all six escalation paths), reference-schema upgrade (`protocol_notes.md` #2), NSF5 EA-reliability P1/P2 — **pre-live, not pre-demo** (both parents' standing lists) | M | FMA2/NSF5-repo |

Demo-run items that are *measurements, not engineering* (stay as-is): maker-first OFF until the
ledger clears (§5.2 gates), mag_xau drift calibration on the first 60 trades, seasonal ≤0.8 bp
slippage bar, weekly realized-w attribution.

### 4.3 What is NOT owed (stale-intel corrections)

- OPS-3b / OPS-6a / OPS-8 / MKT-7 fixes: **implemented** (EA + brain + guards_config). Update
  `research/intel/*` and the DEMO_PREREGISTRATION §6 wording when next touched.
- MAG kill triggers: **registered** (`DUR-mag_xau-sharpe`, `DUR-mag_xau-drift` in
  `guards_config.json`) — PREPROD's old blocker is closed, as FMA2 `docs/v3.4/DEMO.md` §5.3 records.
- A replay/decision-file harness: **does not need to be built** — it exists and is staged.

---

## 5. Recommendation — shortest honest path to the full IC k-calibration

1. **Run the staged scale-10 tester-replay now** (T1–T5). It is one GUI compile plus tester
   wall-clock; the four guard fixes are already in the compiled EA; the config-hash gate is active
   in replay mode; no parent-repo writes, no record-engine time, no 1m-cache loads.
2. **Extract k from it** (T6–T7): per-stack `k_dd = tick_worstDD / 0.2167`, `k_tail` on the 2020Q1
   window, against the official pin — the cleanest ratio the protocol allows. Pair with the v7
   stack's own tester numbers (NSF5's presets exist; that side is the parents' standard practice)
   for the joint k, then run the §5.3 re-pick on the registered IC grid (s ∈ {…1.6…}: largest s
   with record-DD(s)×k_dd ≤ 30% and record-tail(s)×k_tail ≤ 30%). k can only cut the dial — if
   s=1.6 survives, the IC preset deploys as shipped; if not, the grid step-down is mechanical.
3. **Decide Run-2 (deployed-dial 4.80) from Run-1's evidence**: if retention is high and
   `volume_rejects=0` at scale 10, the dial-invariance disclosure in the addendum is defensible and
   Run-2 is optional rigor; if min-lot truncation or margin nonlinearity shows, do Run-2 before
   trusting k at s=1.6.
4. **In parallel, not blocking k**: the four demo glue items D1–D4 (live hash guard, bar exporter,
   kill-switch read, comms filenames) are the real pre-demo engineering — roughly one focused
   FMA2-repo pass. D1 is the highest-risk-per-line item: FMA3's whole "config-only, stock EAs"
   deployment leans on a hash rejection that today only exists in Python and in the tester.
5. **Do not** build a pure-MQL5 signal port, and **do not** burn the demo's k-fallback (§5.1
   interim) while the staged run sits one compile away.

*Sources: `FableMultiAssets2/ea/**` (all files cited inline), `FMA2/docs/v3.4/{DEMO,PREPROD,RECONCILIATION}.md`,
`FMA2/docs/v2.0/EA_MONITORING_SPEC.md`, `FMA2/ea/bridge/PROTOCOL.md`, `FMA2/ea/RUNBOOK.md`,
`FMA3/docs/v1.0/DEMO.md`, `FMA3/research/protocol/{DEMO_PREREGISTRATION,PRESETS}.md`, `FMA3/ROADMAP.md`,
`FMA3/research/intel/{v34-code,registries-deadends}.json`. Parents read-only; no engine passes run.*
