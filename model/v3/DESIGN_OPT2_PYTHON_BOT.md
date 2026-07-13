# Option 2 — Standalone Python Bot (faithful live executor of the v3 stable model)

**Goal:** ONE deployable Python unit on a VPS that runs both sub-book sims, blends them into the v3 model, and trades MT5 **directly** (MetaTrader5 Python API) — deleting the fragile Python→CSV→MQL5 *target* handoff of [`FORWARD_GENERATOR_SPEC.md`](FORWARD_GENERATOR_SPEC.md). This is an **alternative** to Option 1 (`FableFederation_V3.mq5`) / the hybrid generator, not a replacement of that design. The bot reproduces the model of [`MODEL_SPEC.md`](MODEL_SPEC.md) — `fed[h,k] = f7·(w·a_h/j) + f34·((1−w)·b_h/j)`, `w=0.70`, `j=w·a_h+(1−w)·b_h` — and sizes `lots_k = fed·s·BALANCE/unit_k` on 33 netted symbols. Owner constraints: (a) consume the LIVE feed for the sub-book sims; (b) do not modify the FORWARD_GENERATOR design.

Three framing corrections are load-bearing and are baked into this design rather than argued around:

1. **"ONE process that does everything" is impossible.** `lock_v5` poisons a shared mutable global, so the two shadows physically cannot share an interpreter. The honest unit is **one orchestrator + isolated worker processes**, one deployable, internally 3+ processes.
2. **"No downloaded historical data" is infeasible as worded.** The 2020–2025 warm state is an unavoidable **frozen seed**. Reframe the constraint as *frozen seed + live forward stepping* — which is exactly what `data_feed.py` already does by design.
3. **Collapsing the FTMO breaker + stop-out into the crash-prone bot is a net safety regression.** The design keeps a ~200-line **target-less GuardianEA** on the terminal that watches equity+positions only — it needs no target stream, so it does **not** reintroduce the handoff the owner objects to.

---

## 1. Fidelity criterion (what "reproduce the model" means here)

Identical in spirit to [`EA_V3_DESIGN.md`](EA_V3_DESIGN.md) §1, with one added honesty layer the Python path forces:

> At each hour h, for each symbol k, the bot's held net position as a fraction of BALANCE must equal `fed[h,k]·s` (within lot-step quantization). If that holds every M1 bar, the bot *is* executing the model; any equity gap is friction — measured, not mysterious.

**But the Python bot re-owns a proof the MQL5 EA got for free.** RECON-4 reproduced the record (€3,872,872 IC / €1,332,404 FTMO) in the MQL5 **Strategy Tester** (1m-OHLC → real-tick). A Python bot **cannot drive the Strategy Tester.** Calling `static_fed` + the record kernel in-process proves the *model recipe*; it does **not** prove the *execution path* (spread/commission/margin/volume-limit/fills). That proof can only be earned **forward**, on a live/demo account or a self-built bar-replay harness, and logged as 2026 out-of-sample forward evidence — **never** as a reconciled record. This stream IS the campaign's never-fitted 2026 holdout gate. See §8.

Two stacked, partly-unmeasurable fidelity gaps therefore exist and must be named, not hidden:
- **Feed divergence.** `a_h/eq7/f7` are *defined* on the IC dev feed. The live bot runs a **third feed** (broker), after IC and Duka — which already showed ~8pp CAGR divergence. The blend is deterministic given inputs, but the inputs are feed-dependent, so live numbers legitimately differ.
- **Execution haircut.** RECON-4: real fills haircut equity to ~0.66× at s=1.6 (friction + XAUUSD `SYMBOL_VOLUME_LIMIT` binding above ~€2M/s) and ~0.95× at the deployable FTMO dial. Because the 6 shared symbols net into one column, per-book real P&L is unattributable — you cannot measure which side diverges.

**Consequence for the claim:** "reproduces the model" is true only at the recipe/definition level. Present live output as *2026 forward evidence*, validated only by a **same-feed batch reconcile** (§7), never against the IC batch.

---

## 2. Feasibility verdict (per component)

| Component | Verdict | Why |
|---|---|---|
| **MT5 execution layer** (order_send, netting, margin, volume caps, filling-mode) | **Feasible, low-risk, mature** | Every v3 exec primitive has a confirmed Python equivalent; ports ~1:1 from `V7Core.mqh`. This is the *small* part of Option 2. |
| **Blend** (`static_fed` / `blend_static`) | **Reusable as-is** | Pure pandas, no state conflict; forward drift of a_h,b_h already supported. |
| **f34[h] live** (`target_engine.build_book(rebuild=True)`) | **Reusable, wiring only** | Runs hourly today, bit-identical to pin, causal by construction. |
| **b_h shadow** (`record_engine_ext._run_chunk`) | **Feasible, incremental ✅** | Pure carry integrator; hour-stepping is arithmetically identical to the quarter batch. Needs terminal-carry capture + bit-identity proof. |
| **f7/eq7 → a_h** (v7 extractor) | **Feasible but heavy, NO incremental step ❌** | Path-dependent band re-splits; the repo's one sanctioned `NotImplementedError`. Interim = full warm re-extract ~10–25 min/hr. **Cost grows without bound** (§4). |
| **Live tick→bar feed** (`copy_ticks_range` → bid+ask 1m OHLC) | **Feasible, real data-engineering cost** | Must be ticks, not `copy_rates` (bid-only cannot reconstruct worst-side extremes). |
| **"ONE process"** | **Infeasible** | `lock_v5` shared-global poisoning → multiprocess mandatory. |
| **"No downloaded history"** | **Infeasible as worded** | Warm seed is unavoidable; reframe to frozen-seed + live-forward. |
| **Sole trader, no on-terminal backstop** | **Doubtful for FTMO / live-money** | Retail MT5 has no passive dead-man; every substitute is an active poller that dies with the bot. GuardianEA required. |
| **Windows/Wine deployment** | **Constraint, not a code choice** | `MetaTrader5` is Windows-only; this mac's Wine terminal cannot `import MetaTrader5`. |

**Net:** the execution layer's feasibility must **not** greenlight Option 2. Every upstream blocker (no live producer for 3 of 4 inputs, the v7 hourly re-sim, warm shadows, silent splice corruption) is inherited **unchanged** from Option 1, and Option 2 *adds* a live-safety layer whose cost equals or exceeds the hybrid's tail-reader.

---

## 3. Architecture

### 3.1 Process / module topology (resolves lock_v5)

`lock_v5.py:38` sets `ACCOUNT['stop_out_level']=1e-9` on import into the **same** `config.settings` object the v34 stack binds; `record_engine_ext.simulate_account_1m_ext` asserts `==0.5`, `extract_positions.py:134` asserts `==1e-9`. The two shadows require **contradictory values of one shared mutable global in one interpreter**. Flipping it mid-process is unsafe (v7 anchor reproduction is gated on `1e-9`; lock_v5 may set further noliq state). Process isolation is therefore **structural, not a discipline choice.**

```
                    ┌──────────────────────────────────────────┐
                    │  ORCHESTRATOR (proc-0)                    │
                    │  - server-clock + H1/M1 boundary detect   │
                    │  - live tick→bid/ask 1m bar ingestion     │
                    │  - splice-seed sidecar (ratio-chain)      │
                    │  - static_fed blend                       │
                    │  - MT5 EXECUTOR — SOLE order writer        │
                    │  - state ledger + reconcile-on-start      │
                    │  - heartbeat → GuardianEA                 │
                    │  - import-blocklist assert (never v7)     │
                    └───┬───────────────┬──────────────┬────────┘
        disk handoff    │               │              │  MT5 IPC (serialized, single thread)
                    ┌───▼────┐     ┌────▼─────┐   ┌────▼──────────┐
                    │proc-A  │     │ proc-B   │   │ MT5 terminal  │
                    │ v7     │     │ v34 brain│   │ + GuardianEA  │
                    │ shadow │     │ + b_h    │   │ (equity-only, │
                    │ →eq7,f7│     │ →f34,b_h │   │  OnTick guard)│
                    └────────┘     └──────────┘   └───────────────┘
                    NSF5+lock_v5     FMA2 brain,
                    stop_out=1e-9    stop_out=0.5

        WATCHDOG (separate host, own MT5 login) — armed independent flatten channel
```

- **proc-A (v7 / a_h):** imports NSF5 (`lock_v5` sets `1e-9` here and *only* here). Full warm re-extract via `extract_positions` → `eq7[h]`, `frac7[h]` (8-leg band book). Writes `v7_out.parquet` + carry `(cur, seed, last-trigger, eqc anchor)`.
- **proc-B (v34 / b_h):** imports FMA2 brain + `record_engine_ext` (`stop_out==0.5`). `target_engine.build_book(rebuild=True)` → `f34[h]`; `_run_chunk(balance0,lots0,entry0, tgt=f34[h])` steps the b_h shadow. Writes `v34_out.parquet` + carry `(balance,lots[],entry[])`.
- **proc-0 (orchestrator):** **never imports the v7 stack** (enforce with an import-blocklist assert at boot — not by convention). Reads both parquets, ratio-chains the seed, runs `static_fed`, and is the **sole MT5 order writer**. MT5 calls are a process-global, non-thread-safe singleton, so **every** `order_send`/read is serialized through one executor thread.
- Handoff is on-disk atomic (tmp+fsync+rename), matching the spec's proc-A/B/C mandate.

**One deployable unit; internally 3 processes + GuardianEA + off-host watchdog. Never present it as "one process."**

### 3.2 Live feed + warmup seed

**Feed must be ticks.** `record_engine_ext._FIELDS = (bid_o, ask_o, bid_c, ask_c, bid_l, ask_h)`; the worst-side extremes `ask_h`/`bid_l` drive worst-mark equity, the joint stop-out, and the FTMO breaker. `copy_rates_range` returns bid-only OHLC + one `spread` point value — it **cannot** reconstruct the worst-side extremes, and the shortcut fails *exactly in the crisis hours the gates care about.* So:
- `copy_ticks_range` → resample per minute → **bid-OHLC and ask-OHLC** for ~40 symbols (37 model + 8 EUR crosses), continuous with gap backfill.
- The **same ticks** reduce to the 1h mid cache (`build_ext_cache.hourly_from_1m`: mid=(bid+ask)/2, `rel_spread=(ask_c−bid_c)/mid_c`, resample 1h) that the FMA2 brain reads. One ingestion feeds *both* the 1m bid/ask shadows and the 1h brain cache — sims and signal share one feed. Genuine strength of the single-unit design.

**Warmup is a FROZEN seed, not live.** Cold-starting fabricates crisis behavior (the COVID k≈4.7 stop-out warmup artifact — *the* landmine). The 2020–2025 warm state ships to the VPS as an immutable asset:
- **v34:** the kernel carry `(balance, lots[], entry[])` at 2025-12-31 23:59. A one-time full warm batch must be run to **surface and persist** this carry — `simulate_account_1m_ext` currently *drops* it.
- **v7:** the ~2.1 GB frozen 1m bid/ask history (needed at runtime for the hourly re-extract) + `(cur, seed, last-trigger, eqc anchor)`.
- **Splice sidecar** `{a_last, b_last, boundary_stamp=2025-12-31T23:00, eq7_base=10000, eq34_base=10000}`, sampled from `static_fed` at the hour-**OPEN** asof (empirically `a_last=53.0979` at 23:00, **not** the 53.2230 23:59 mark — getting this wrong silently corrupts every forward weight).

**Symbol namespaces must reconcile** (three of them): model (`USA500/USTEC/DAX`), broker (`US500/DE40/USTEC`), Duka proxy (`USA500`-for-`USTEC`). The live bot applies the **inverse** broker→model map and prices **real USTEC** — the USA500 proxy is a Duka-holdout artifact and would be a permanent per-hour divergence (corr 0.89). Confirm the broker quotes all 37 + all 8 EUR crosses before capital; a missing EUR cross freezes that currency's `eurq` (the exact FxConverter defect the ext engine now raises on). Confirm **broker server tz == IC-feed server tz** (daily break at hour 0 = 17:00 ET) or the 2025/2026 splice gets a per-bar discontinuity.

### 3.3 Main loop + cadence

Model convention: hour-h signal executes held over hour h+1. A closed M1 bar appears only at `h+1:00:00+` (seconds of settle). Because the bot IS the trader, there is **no CSV append, no FedReplay tail-read, no D2 (h+2) race** — the only irreducible lag is compute latency Δ, dominated by the v7 re-sim, during which the first Δ minutes of h+1 trade on stale `fed[h−1]`.

```
every M1 close (execution cadence, poll ~1-5s):
    pull ticks → update 1m bid/ask bars
    re-size lots on the CURRENT held fed vector      # M1 resize = biggest IC-fidelity lever
    executor.reconcile_to_target()                   # §3.4 primitives, band 0.25
    heartbeat → GuardianEA

on H1 boundary (h+1:00:00 + settle):
    require: ALL 40 symbols have a settled h:59 bar   # atomic gated snapshot; else hour ABSENT
    proc-B: build_book(rebuild=True) → f34[h]; step _run_chunk → b_h     # seconds
    proc-A: full warm re-extract → eq7[h], f7[h]                         # 10-25 min ⚠, bounded window (§4)
    when BOTH land within wall-clock hard-stop:
        orchestrator: ratio-chain a_h,b_h → static_fed → fed[h]
        assert re-derived eq7[boundary] == frozen a_last denominator      # splice hard gate
        atomically publish fed[h] as the new held target
    else → KEEP-LAST-GOOD (monitored miss; alarm on N consecutive)
```

**M1-resize honesty:** measured MetaTrader5 round-trip is ~570–670 ms per call, single-terminal, serialized. A full 33-symbol sweep is ~20s+ before chunking and can run to minutes in crisis simultaneity (many-flip bars against XAUUSD's 10-lot cap), which can **blow the 60 s bar** and quietly degrade the exact fidelity RECON-4 proved. Mitigation: lean hard on the **0.25 rebalance band** so only band-crossing legs retrade per bar; measure the real sweep time on the target VPS and **relax the claim to "resize whatever the pipe sustains within the bar," recording the gap as a NAMED deviation** (as RECON-4 named friction/volume/margin). Never present M1-resize as achieved.

### 3.4 Executor — mapping the v3 exec primitives (port from `V7Core.mqh`)

The MQL5 CTrade convenience layer disappears; every primitive ports ~1:1:
- **SendSplit** (`V7Core.mqh:480`) → hand-loop chunks ≤ `symbol_info.volume_max`, retcode-aware backoff. Handle **10009 DONE / 10010 DONE_PARTIAL / requote / no-money** explicitly (`LogReject` backoff ported by hand — a class of rejects CTrade hid).
- **SYMBOL_VOLUME_LIMIT cap** → read `symbol_info.volume_limit` (confirmed present; 0 = unlimited) and clamp `want`. This is why **XAUUSD caps the record above ~€2M/s** (RECON-4) — a real ceiling on the deployable dial, not a bug.
- **DesiredLots / sizing** (`V7Core.mqh:510–550`) → `fed·s·balance/unit` with `order_calc_margin` cap (0.9·base uniform shrink) + `RoundLots` to `volume_step`. Margin binds the IC dial **before** DD at 1:30 (memory: deployable s band **0.6–0.8**, not the shipped 1.6).
- **Netting / hedging bookkeeping** → `HeldNet`/`CollectTickets`/`CloseAll`/`ReducePos` (`:555–620`) over `positions_get`. **One net position + one magic per symbol** — the v3 netting choice *simplifies* attribution vs FMA2's shared-XAUUSD problem: broker net lots per symbol is the truth.
- **Per-symbol filling-mode negotiation** (must-build; CTrade hid this) → `symbol_info.filling_mode` bitmask; pair **IOC + the SendSplit chunk loop** (FOK rejects an un-fillable large order whole). Retcode 10030 = wrong mode.
- **Full-map eurq** (`FedConvert`) → used for **all** symbols, always on.
- **retcode 10027 fail-safe (confirmed live):** "AutoTrading disabled by client" / investor-password / broker EA-block **silently rejects** `order_send` while reads keep succeeding. After every flatten/resize, **re-read `positions_get` and confirm the intended state**; treat any non-DONE retcode or residual position as STILL-EXPOSED, alert + trigger the watchdog, and **never latch a "halted/safe" state on an unverified action.**

### 3.5 Watchdog + on-terminal guardian (the load-bearing safety decision)

The owner's aversion is to the Python→CSV→MQL5 **target** handoff. The safety-critical enforcement needs **only equity + positions, never targets.** So the design keeps a minimal `GuardianEA.mq5` on the terminal:
- fires the worst-mark **daily breaker** on `OnTick` (co-resident with the account — the one thing a polling Python bot structurally cannot match),
- enforces the **joint 0.5·margin stop-out**,
- **flattens-all** on stale bot heartbeat (a *real* dead-man),
- obeys an **off-host kill-switch**.

This recovers ~all on-terminal safety at ~200 lines, needs no target stream, and removes the single sharpest Option-2 failure mode (bot dies mid-drawdown → nobody watching the FTMO 10% floor). **Mandatory for FTMO; strongly recommended for IC.**

Plus an **off-host watchdog** on a separate host with its **own** MT5 login, network path, and short dead-man timeout — an **armed** independent flatten channel (not a read-only monitor), with arbitration so bot and watchdog never fight. Classify it explicitly as **latency-bounded mitigation, not a true dead-man** (it is itself a poller subject to its own AutoTrading flag and a datacenter-wide outage).

### 3.6 State persistence + crash recovery + reconcile

Out-of-process `order_send` introduces ack-loss and split-brain the in-process EA never had. Mandatory:
- **Reconcile-on-start BEFORE any order** — port `reconcile.py` verbatim: broker = truth for WHAT EXISTS, state file = truth for WHO OWNS IT; trim to the **smaller**, **freeze entries on any mismatch**, **never re-derive-and-re-enter.** Cross-check `history_deals_get` to resolve "did my last send fill?".
- **Atomic state ledger** after every fill ack (tmp+fsync+rename). One magic per symbol.
- **Idempotent submission** — client-side dedup tag (comment/deviation) + **post-send `positions_get` verify**, so a retried send after a lost ack does not double the position.
- **Terminal-liveness every loop** — check `terminal_info().connected` / `trade_allowed` / `last_error`; treat any IPC failure as **HOLD, never flat.** The killer bug: reading empty `positions_get` as a flat book and re-entering positions the broker already holds. Watch the silent "Disable automatic trading via external Python API" flag (an update can reset it — reads keep working while `order_send` silently fails).
- **No auto-reconnect** — watchdog `terminal_info().connected`, `initialize()`/`login()`, resync from live `positions_get` on boot.
- **Broker-resident protective SL on EVERY entry** (~3× daily ATR) placed atomically with the position — the *only* guardrail surviving total bot+VPS death. Label it explicitly: it bounds per-position **price** loss, **not** the equity-% daily rule (see §5).

**Deployment:** Windows VPS + native terminal is the clean path (accept porting the numba/pandas stack, de-hardcoding POSIX paths like `/Users/dsalamanca/...`, shipping the 2.1 GB frozen cache). Wine + `mt5linux`/rpyc is the fallback but reintroduces a bridge and defeats the single-unit appeal. Live MT5 stamps are already server wall-clock — this *sidesteps* the Duka `to_server` UTC→NY+7h landmine that broke FedReplay.

---

## 4. The v7 re-sim — cost, bound, and the crisis-correlated killer

The interim full warm re-extract (inject live bars into `bt._BARS_CACHE[(inst,False)]` + `bt._PREP_CACHE.clear()`, the `prime_2026` pattern) is **feasible for launch but not a sane steady state.** Adversarial findings, folded in:

- **Unbounded growth.** `extract()` re-derives the ENTIRE 2020→now band-book every hour, and `self_test_core` runs every leg **twice** (bit-identity) over the full window *before* the band run. Cost is O(history × n_triggers) and only grows: next year is a 7-yr window with more accumulated triggers. There is **no steady state** — duty cycle rises without bound. "Fine for launch" hides that it degrades every hour.
- **Crisis-correlated overrun.** The 10–25 min spread is driven by band re-split triggers (path-dependent on volatility). A volatile hour that fires a **new** re-split adds a whole segment exact-re-run to *that* hour — so the re-sim is **slowest exactly when volatility spikes**, i.e. when the sizing vector matters most and stale keep-last-good is most dangerous. One crisis hour past ~60 min pushes proc-A a full hour behind; sequential + more expensive cycles → **monotonic lag death-spiral**, blind under keep-last-good.
- **Infra is not free.** numba `njit` is single-threaded over a sequential leg loop, so cores don't speed one re-sim. A burstable t3/t4g exhausts CPU credits in ~1–2 h under a 25-min single-core peg → throttled → 25 min balloons to 2 h+ → permanent overrun. **Requires a pinned NON-burstable dedicated vCPU at 17–42%+ continuous duty forever** — an ongoing cost the "reuse existing Python" appeal conceals.
- **Non-atomic 40-symbol snapshot corrupts a path-dependent extractor.** A single late/missing tail bar can flip a band re-split on/off, **retroactively rewriting a_h and eq7 across the whole forward segment** (not just the tail). A missing EUR cross makes FxConverter RAISE and freezes the hour.
- **Splice-base denominator drift.** The ratio-chain recomputes `eq7[boundary]` (the 2025-12-31 mark) every hour. If the historical portion drifts by float noise or a broker back-revision, the boundary denominator moves → a_h moves → every forward weight moves silently, **while the file's own <1e-12 self-check still passes.**

**Resolutions (mandatory, not optional):**
1. **Pin the historical re-run to the FROZEN cache**, not live 2020–2025 broker bars, so `eq7[boundary]` is byte-stable hour-to-hour; only the post-boundary tail uses live bars. Add a **hard assert** each cycle that re-derived `eq7[boundary]` == the frozen `a_last` denominator (make the daily warm reconcile a *gate*, not a monitor).
2. **Bound the re-sim window.** Prove (bit-identity over an overlap) that a fixed-length warm re-run — warm indicator seed from a frozen pre-2020 state + a capped rolling window still covering all live triggers — reproduces the full-from-2020 path. Re-run only that window each hour so cost stops growing.
3. **Atomic gated snapshot.** Freeze one all-40-symbol snapshot at the boundary; refuse to start hour h until every band symbol AND every EUR cross has a settled h:59 bar. On any gap, leave hour h **ABSENT** (keep-last-good) rather than re-sim on an inconsistent tail. Alarm on N consecutive misses.
4. **Size infra honestly + hard wall-clock stop.** Pinned non-burstable vCPU for proc-A; a hard-stop well before the next boundary that aborts to keep-last-good rather than cascade the lag. Instrument per-cycle runtime + trigger-count so overrun is visible before it spirals.
5. **Treat the resumable v7 stepper as a steady-state LAUNCH-BLOCKER-FOR-STEADY-STATE, not an optional nicety.** The interim full re-extract is a demo crutch with a hard replacement mandate; it is not sane past a few months. It must be proven bit-identical before use — you pay the expensive warm path once to certify the cheap one. Keep it OFF the launch critical path but ON the roadmap with a deadline.

---

## 5. Failure modes + safe degradation (the no-on-terminal-backstop problem)

Ranking on safety surface: **on-terminal EA > hybrid CSV >> sole Python bot.** The hybrid's much-discussed fragility (CSV, tail-reader, tz/epoch, splice seed) is a **fidelity/liveness** risk — stale/wrong *targets* that degrade to on-terminal keep-last-good bounded by the still-running breaker/stop-out. Option 2 trades that for a **safety** fragility: it concentrates order authority + account-terminating-rule enforcement in the least reliable component.

| Failure mode | Sole-bot outcome (no guardian) | Required scaffolding |
|---|---|---|
| **Bot dies with open positions** | Terminal holds positions but runs NOTHING — no breaker, no stop-out, no resize. No benign "stale targets" path. | GuardianEA dead-man flatten on stale heartbeat; broker-resident SL per entry; supervised restart (systemd `Restart=always`) + reconcile-on-start. |
| **FTMO daily breaker only in-bot** | Bot dies mid-drawdown → account can breach the daily loss and hard 10% rule with nothing watching. **Sharpest killer.** | Breaker in GuardianEA `OnTick`, redundant breaker in off-host watchdog. |
| **Terminal crash / IPC desync (split-brain)** | `positions_get` returns empty/stale → bot misreads as FLAT → **double-entry** on 33 netted legs. | Terminal-liveness every loop; HOLD-never-flat; idempotent submission + post-send verify. |
| **Silent trade-disable (10027 / API flag)** | `order_send` fails silently; data reads keep working; a naive breaker logs "flattened" and latches false-safe while bleeding. | Poll `trade_allowed`; verify state after every action; escalate to watchdog; never latch on unverified flatten. |
| **Guard-loop starvation** | 10–25 min v7 re-extract (can hang) sharing a process/thread with the guard freezes the time-critical breaker. | Hard process isolation (already forced by lock_v5); guard never shares proc with the re-sim; MT5 calls serialized with backpressure. |
| **Polling-latency breaker miss** | 1–5 s poll misses the worst-mark instant an `OnTick` EA catches → fires late. | Breaker on-terminal (OnTick), not in the poll loop. |
| **24/7 crypto + weekend stranding** | Generator-down + bot death over a weekend = 48h+ unmanaged exposure on netted BTC/ETH/XAU. | Guardian force-flatten on stale-hold beyond a time bound (risk-policy decision). |

**The categorical defect (adversarial, conceded):** **retail MT5 has NO passive dead-man** — no exchange cancel-on-disconnect, no broker-side auto-flatten on client death. *Every* "dead-man" here (in-bot breaker, heartbeat-flatten, off-host watchdog) is an **active poller that must be alive to fire** — and is most likely dead in the crisis that needs it. The only server-resident guardrail surviving total bot+VPS death is the **broker per-position SL**, which enforces the **wrong dimension**: 33 per-leg price stops do not sum to a 10%-of-account cap, and a correlated crisis gaps through all 33 at once. For the rule that **terminates** the account (equity-%), there is **no** server-resident backstop. This is why the equity-% breaker fundamentally wants an always-on process co-located with the account — i.e. the GuardianEA. **For FTMO specifically, sole-bot with the breaker only in-bot is close to unshippable.**

Even a perfect co-resident breaker doesn't fully save FTMO: memory (`ftmo-shipped-dial-unsafe`) establishes the 3% daily breaker is **net-negative vs a COVID-class multi-day grind** (breaches by 7.5–10.8pp; re-anchors every server morning → ~zero cumulative protection). So the dial must be cut to **~s0.30–0.35** and the daily breaker augmented with a genuine cumulative-DD / vol-regime crisis brake — regardless of where it runs.

**If the owner insists on literally-zero MQL5:** do **not** put the funded/FTMO account on this topology at all. Restrict sole-bot to the **own-capital IC preset** (margin-bound s~0.6–0.8) where a rule-breach is not account-terminating, and book the worse-than-intended tail as an explicit risk-tolerance decision, **not** a safety claim.

---

## 6. Reconciliation stance — MONITOR, DO NOT FEED BACK (justified)

The owner's initial view is correct and **structurally forced**, not merely preferred:
- The model is *defined by* the two idealized standalone curves — `a_h,b_h` are each book's native €10k-seed multiple, account-independent **by construction** (MODEL_SPEC §1 — the entire reason v3 *replays* instead of computing from the live account).
- Feeding real fills back would make `a,b` depend on the live s-levered, jointly-margined account = a **different, unvalidated strategy**.
- It is **mechanically unmeasurable** anyway: the 6 shared symbols (BTCUSD, ETHUSD, EURGBP, USDJPY, USTEC, XAUUSD) net into one column, so per-book real P&L cannot be attributed.

The **only** sanctioned feedback is error-correction of a shadow against *its own definition*: if the incremental shadow drifts >1e-12 from a warm batch recompute **on the same live feed**, reseed the shadow FROM THE BATCH and quarantine the window — **never from broker fills.** Reconcile **live-vs-live, never vs the IC batch** (IC dev feed vs Duka already showed ~8pp CAGR divergence; the broker is a third feed — reconciling against IC would flag feed physics as a false bug). `config_hash 51a7541cc2aaa593` pins the MODEL, not the DATA — a green hash + green self-check both pass on a legitimately feed-divergent stream. Keep **pre-net f7[h], f34[h] in a forensic sidecar** (the netted stream is otherwise unattributable).

**Safety consequence:** sim-state and broker-state are two **open-loop** state machines with no self-correcting coupling — which makes reconcile-on-start and desync detection *more* load-bearing, not less.

---

## 7. How it reproduces the model + verification

| input | producer | reuse | statefulness |
|---|---|---|---|
| **f34[h]** | proc-B `target_engine.build_book(rebuild=True)` | as-is, bit-identical to pin | causal, no runtime history once seeded |
| **b_h** | proc-B `record_engine_ext._run_chunk(...tgt=f34[h])` | kernel verbatim + terminal-carry capture | **incremental ✅** |
| **f7 / eq7 → a_h** | proc-A `extract_positions` full warm re-extract | reuse, path-dependent | **NO step ❌** (§4) |
| **blend** | proc-0 `reproduce.static_fed` / `run_forward_oneshot.blend_static` | as-is, pure pandas | drifting a_h,b_h supported |

**Forward seeding = ratio-chain, never re-base.** `a_h = a_last·(eq7[h]/eq7[boundary])`, `b_h = b_last·(eq34[h]/eq34[boundary])`. **The single most dangerous surface in the system:** re-basing to 1.0 instead of chaining onto the frozen last multiples changes the a/b ratio → changes every weight `w·a/j`, `(1−w)·b/j` → *every forward hour is confidently wrong while the file's own <1e-12 self-check still PASSES.* Only the heavy daily warm reconcile catches it. Test it explicitly against the batch and make the boundary-denominator assert (§4.1) a hard gate.

**Verification ladder (Python-only where possible, else forward):**
1. **Blend self-check** — parsed matrix reproduces `static_fed(0.70)` to <1e-12 (as the exporter does today).
2. **b_h bit-identity** — the incremental `_run_chunk` stepper byte-reproduces `v34_s10_pin_curve.parquet` over a historical overlap *before* one live hour is trusted.
3. **v7 bounded-window bit-identity** — the capped re-run reproduces the full-from-2020 path over an overlap.
4. **Splice hard gate** — re-derived `eq7[boundary]` == frozen `a_last` denominator each cycle.
5. **Same-feed daily warm reconcile** — regenerate the last N hours via the warm batch on the SAME broker feed; diff <1e-12; reseed-from-batch on drift. **Never** reconcile against the IC batch.
6. **Forward evidence** — live/demo hours logged as 2026 out-of-sample, NOT as a reconciled record (§8). Extend expiring tables (`v5_sleeves._OPEX_WK` → 2026-02-20, `costs.POLICY_RATES` USD → 2025-12-11) or the v7 S6 sleeve silently goes flat.

**Lost validation gate (accept it):** RECON-4's fast Strategy-Tester reproduction of €3,872,872 / €1,332,404 is **unavailable** to a Python bot. The execution path it newly owns can only be argued **forward**, so a divergence takes weeks of live demo to surface instead of a tester run. Plan a self-built bar-replay harness as the closest substitute.

---

## 8. Build plan (phased; realistic monitored demo ~4–8 weeks)

1. **v34 side first (Phase 1, ~1–2 wk).** Wire brain rebuild for f34; build the b_h forward driver over `_run_chunk` incl. the one-time terminal-carry capture; **prove byte-repro of `v34_s10_pin_curve` on the overlap before trusting one live hour.** Right proving ground — no runtime history once seeded. Emit to scratch.
2. **v7 isolated worker (Phase 2, ~1–2 wk).** Interim full warm re-extract off a live-fed cache (real USTEC, frozen 2020–2025 1m history on disk, pinned historical cache) + the **ratio-chained splice sidecar** (highest-severity item — test against the daily reconcile) + `static_fed` blend + config-hash gate + boundary-denominator assert + atomic gated snapshot + daily warm reconcile.
3. **Live MT5 execution + safety (Option-2-specific, ~1–2 wk+).** Port `V7Core` exec primitives + the **GuardianEA** (equity-only), netting/margin/volume caps, filling-mode negotiation, retcode fail-safe, reconcile-on-start, idempotent submission, terminal-liveness/HOLD-never-flat, watchdog/reconnect, atomic ledger, broker-resident SL per entry. Run the full RUNBOOK §9 drill suite on demo.
4. **Deploy the non-account-terminating IC preset first** (s band 0.6–0.8, margin-bound — **not** s=1.6). Do **not** put the FTMO account on a sole-bot with the breaker only in-bot. Cut the FTMO dial to ~s0.30–0.35 and augment the breaker before any FTMO capital.
5. **Resumable v7 stepper** — separate, hard research item; OFF the launch critical path but ON the roadmap with a deadline (§4 makes it a steady-state blocker).

---

## 9. Open questions

- **Does the live broker quote all 37 model symbols + all 8 EUR crosses, incl. real USTEC / DE40 / US500?** A missing leg silently drops from the shadow; a missing EUR cross freezes `eurq` (FxConverter raises).
- **Broker server timezone == IC-feed server tz (17:00 ET break)?** If not, the 2025/2026 splice has a per-bar discontinuity → book falls into keep-last-good.
- **Does the broker allow API/algo trading on the account tier**, and is the high-leverage (1:500 hedging) login available for the s=1.6 reproduction (deployment stays 1:30 → s 0.6–0.8)?
- **Can a bounded-window v7 re-run be proven bit-identical to the full-from-2020 path?** If not, the unbounded-growth re-sim has no exit and the resumable stepper becomes a hard launch dependency, not a roadmap item.
- **What is the real 33-symbol order-sweep round-trip on the target VPS?** Sets whether M1-resize is achievable or must be relaxed to a named deviation.
- **Windows VPS vs Wine+rpyc** — does the port of the numba/pandas stack + 2.1 GB frozen cache to Windows land cleanly, or does the Wine bridge's added failure surface dominate?
- **Weekend/stranding policy** — does the guardian force-flatten netted crypto after a bounded stale-hold, or hold? (risk-policy decision, not a default).
- **Is this stream ever presentable as anything but 2026 forward evidence?** Per campaign honesty rule, no — but the gate that would upgrade it is undefined here.

---

## 10. What makes this hard / when this is the wrong choice

**What makes it hard** is entirely **upstream and shared with Option 1** — the Python choice deletes only the CSV/MQL5 *target* handoff, not the mountain:
- 3 of 4 model inputs (f7, eq7→a_h, eq34→b_h) have no live producer; the v7 side is path-dependent with the repo's one sanctioned `NotImplementedError`, so the interim is a growing-cost hourly re-sim.
- Warm shadows are non-negotiable (COVID cold-start artifact).
- The ratio-chained splice seed is a silent, catastrophic corruption surface that passes its own self-check.
- Option 2 *adds* a live-safety layer (netting, margin, breaker, fills, volume caps, reconcile, watchdog) whose cost equals or exceeds the hybrid's tail-reader — and most of that cost hides in doing it *safely*.

**When this is the wrong choice:**
- **For the FTMO / any funded live-money account, if the owner refuses the on-terminal GuardianEA.** Retail MT5 has no passive dead-man; a sole-bot leaves the account-terminating rule enforced only by a process that dies in the crisis. Ship an on-terminal EA (Option 1) or keep the GuardianEA — do not run FTMO sole-bot.
- **If the fast Strategy-Tester reproduction gate is considered essential.** A Python bot cannot drive it; you accept forward-only validation and a weeks-long divergence-detection latency.
- **If a bounded v7 re-run cannot be proven** and steady-state CPU duty / lag death-spiral is unacceptable — then the resumable stepper must exist first, which is a hard, open research item.
- **If the deployment cannot be a Windows (or robust Wine) host with a pinned non-burstable vCPU** — the whole brain+executor+breaker stack pins to one Windows terminal, a concentrated failure domain.

**Honest one-liner:** Option 2 is the *right substrate* — the model, blend, target engine, and account kernel are already Python, so a one-unit bot cleanly deletes the handoff the owner wants gone — and its execution layer is the *low-risk* part. But its feasibility must **not** greenlight the project: it inherits every upstream blocker unchanged from Option 1 and adds a live-safety layer whose cost equals or exceeds the hybrid's. Keep a target-less guardian on the terminal, isolate the three model processes, pin the historical re-run and bound the v7 window, ratio-chain the seed, and validate forward.

---

## Key source files for the port
- `mt5/ea/Include/FMA3/V7Core.mqh` — exec primitives (SendSplit L480, DesiredLots L510–550, HeldNet/CollectTickets/CloseAll/ReducePos L555–620); `Guardian.mqh` — breaker (→ GuardianEA)
- `model/v3/EA_V3_DESIGN.md` (sizing 4.1, breaker 4.3), `model/v3/reproduce.py::static_fed`, `model/v3/run_forward_oneshot.py::blend_static` (+ the L402 `NotImplementedError`)
- `engine/record_engine_ext.py` — `_run_chunk`/`_run_chunk_stop` (b_h kernel), `simulate_account_1m_ext`
- `engine/v7_bridge/extract_positions.py` — v7 extractor (path-dependent blocker), `bt._BARS_CACHE`/`_PREP_CACHE` priming
- `engine/build_ext_cache.py::hourly_from_1m` — 1m→1h reduction (shared feed)
- `/Users/dsalamanca/vs_env/FableMultiAssets2/ea/brain/target_engine.py` — f34 live; `ea/bridge/reconcile.py` — reconcile discipline
