# FableFederation_V3 EA audit — the faithful-executor release (v3.0)

> **⚡ SUPERSEDED IN PART (2026-07-15) — see [CURRENT_STATE.md](CURRENT_STATE.md).** This doc describes the RECON-4-era `FableFederation_V3` **CSV-replay** EA. The current executor is the **native, live-computing** `FableBookNative` EA — full-window 2020-2025 real execution net **€2,934,301** (0.76× the frictionless record), **RECONCILED** on engine fidelity (drawdown +0.7pp, position fidelity ~perfect), the −12.9pp CAGR gap being **swap-led execution friction**. `CURRENT_STATE.md` **wins** where they disagree.

**Audited 2026-07-12.** Scope: the shipping EA `mt5/ea/FableBook.mq5` (sha `740da0ff…`)
and its four-file include tree `mt5/ea/Include/FMA3v3/{FedConvert,FedReplay,FedExec,Guardian}.mqh`,
against the model of record in `model/v3/` (`README`, `MODEL_SPEC`, `PINNED_INPUTS`, `EA_V3_DESIGN`,
`RECON4_RESULTS`), the exporter `scripts/export_book_frac_v3.py`, the capacity sweep
`scripts/sweep_s_volcap.py`, and the reconciliation FMA3-RECON-4 (IC Markets 11078280, 1m-OHLC,
HEDGING, 1:500). Every claim is cited to a file. Purpose: answer *"does the v3 EA provably execute
the frozen `static_fed(0.70)` model on MT5, what did the adversarial review change, and what stands
between here and (a) the real-tick run, (b) live deploy."*

> **SUPERSEDES `archive/docs-v1.0/FMA2_EA_AUDIT.md` for the shipping EA.** That audit covered the FMA2 Satellite
> *sub-book* run through the Python-brain bridge (a tester-replay of one sleeve). v3 is a different,
> single-binary architecture: it discards the entire v1/v2 signal+sizing stack and replays ONE
> unified 33-symbol netted `fed_frac` stream. The v1.0 audit remains valid as the record of the Satellite
> sleeve's own tester harness; it is not the executor that ships. Where the two disagree, this doc
> governs the deployed EA.

---

## 0. Headline findings (read this if nothing else)

1. **v3 IS the faithful executor — position-level fidelity is exact.** Across all three RECON-4 runs
   the held-fraction-of-own-balance divided by the model's target fraction (`after/want`) has
   **median 1.000, p10 1.000** (`RECON4_RESULTS.md` §"What is proven"). Where v3 can place the
   order, it holds precisely `fed_frac·s`. The EA is the executor the campaign set out to build.
2. **The equity gap is friction, not defect — 0.66–0.95× the frictionless record by dial/scale.**
   Parity s=1.0 → €391,873 (**0.84×** the €464,991 record), IC s=1.6 → **€2,552,962** (**0.66×** the
   €3,872,872 record) *(RECON-4/FableFederation_V3; superseded — native `FableBookNative` EA: €2.93M / 0.76×, see CURRENT_STATE.md)*, FTMO s=0.7 → **€1,265,541** (**0.95×** the €1,332,404 record). Every gap is a
   *named physical constraint the record engine does not model* (§3): transaction friction, broker
   `SYMBOL_VOLUME_LIMIT`, broker margin. None of them is an EA bug.
3. **The replay decision was correct and is load-bearing.** The model's share weights `w·a_h/j`,
   `(1−w)·b_h/j` are built from the two books' **frozen native standalone** equity multiples; a live
   s-levered account cannot reconstruct them, so compute-live (v1/v2) diverges whenever s≠1 — and
   both shipped dials are s≠1 (`EA_V3_DESIGN.md` §2). Replaying the precomputed netted blend is the
   only faithful path, and it dissolves the v1/v2 reseed / floating-double-count / pooled-redistribution
   divergences by construction.
4. **A 3-reviewer adversarial pass ran on the first build and every finding was fixed** (§4.1). The
   six fixes — unsized-leg HOLD, per-M1-bar re-size, worst-mark breaker, prev-day-close anchor,
   server-tz mismatch guard, gated FileFlush — plus the post-RECON volume-limit cap took the binary
   from `d516350b…` to `740da0ff…`. The single biggest IC-fidelity lever was **re-sizing every M1
   bar** (was once per H1). The compile is clean (0 errors / 0 warnings).
5. **The Satellite sleeve is alive again.** All 33 union symbols trade, including the **7** that v1/v2
   silently killed via a quote-currency bug (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) —
   the unconditional full-map `eurq` revives them end-to-end (`RECON4_RESULTS.md` proof #2).
6. **One mechanism is deliberately deferred, not implemented: the joint 0.5·margin_used stop-out**
   (§4.3). In-sample it never triggers (IC worst DD 22.58%, FTMO 13.33% — nowhere near the ~50% it
   needs), so it cannot affect the reproduction; RECON-4 asserts `eq_w` never approaches it. Adding an
   unvalidated crisis mechanism was judged worse than delegating to the broker stop-out.

---

## 1. Architecture map — how the executor works

*(This section describes the superseded `FableFederation_V3` **CSV-replay** design. The current executor is the native, **compute-live** `FableBookNative` EA — see `model/v3/` and CURRENT_STATE.md.)*

### 1.1 Components (all under `mt5/ea/`, single binary, no external process)

```
FableBook.mq5            OnTick driver: guardian → new-M1 gate → causal H1 apply → resize
  Include/FMA3v3/
    FedConvert.mqh   eurq: full 8-currency EUR-cross map, ALWAYS on (no gate)   [~55 ln]
    FedReplay.mqh    fmt=3 loader + FIXED 33-universe table + model leverage      [~240 ln]
    Guardian.mqh     FTMO daily breaker: prev-day-close anchor + worst-mark eq_w  [~117 ln]
    FedExec.mqh      the unified per-bar size+reconcile loop + exec primitives     [~315 ln]
```

There is **no brain, no bridge, no comms dir, no watchdog** — the entire v1.0 bridge stack is gone.
Signals were computed once, offline, and are frozen inside the stream. The EA is pure execution.

### 1.2 The four modules

- **FedReplay** (`FedReplay.mqh`) — reads `FMA3_fed_frac_v3.csv` from `Common\Files`. Header
  `w_v7=0.70,config_hash=51a7541cc2aaa593,fmt=3`; rows `epoch,broker_symbol,net_frac`; `__GRID__,0`
  sentinel per all-flat hour. The 33-symbol universe is a **FIXED compiled table** whose order is law
  (it fixes each symbol's magic = `InpMagicBase+idx+1`) and which carries the **model per-symbol
  leverage** (`g_fedLev[]` = record_engine `INSTRUMENTS[.].leverage`: FX 30, index/gold 20,
  energy/silver 10, crypto 2) so the margin cap reproduces the engine. Strictness is total: header
  hash ≠ compiled `51a7541cc2aaa593` → `INIT_FAILED`; `fmt≠3` → `INIT_FAILED`; any unknown symbol,
  non-ascending timestamp, or malformed row → `INIT_FAILED` (**"a frozen file must be perfect"**).
  `FED_ApplyHour` advances an O(rows) forward cursor; a present hour flattens-by-omission then writes
  each leg; an empty hour keeps-last-good.
- **FedConvert** (`FedConvert.mqh`) — `FED_Eurq(sym)`: `1` if profit-ccy = EUR, else `1/mid(EUR-cross)`
  over the full map `{USD,JPY,GBP,CHF,NZD,CAD,NOK,SEK}`, matching `record_engine_ext._eurq_chunk`.
  Fallback = terminal tick-value primitive; `0.0` → the caller **skips the leg loudly**, never a
  silent mis-size. Unconditional (no `InpV34EurQuoteFix` gate — the v1/v2 3-branch `1/EURUSD`
  catch-all that mispriced the JP/NOK/SEK/CHF/CAD legs below min-lot is gone).
- **Guardian** (`Guardian.mqh`) — the FTMO daily circuit breaker, config-gated on `InpDailyStopX`
  (0 = OFF, a single short-circuit branch with no state/IO; FTMO preset 3.0). On server-day rollover
  `anchor = previous-day CLOSE-mark equity` (day 1 = real seed balance), carried forward as the last
  `ACCOUNT_EQUITY` before the next rollover (= the engine's `last_close`). Each tick, if **worst-mark**
  `eq_w ≤ anchor·(1−x/100)` → flatten all this-EA positions, halt (targets→0) until the next rollover.
  `eq_w` is `FED_WorstMarkEquity`: balance + Σ worst-side unrealized (M1 low for longs, high for
  shorts) via `OrderCalcProfit` for broker-accurate account-ccy conversion.
- **FedExec** (`FedExec.mqh`) — the unified sizing + reconcile pass and all execution primitives.

### 1.3 The sizing loop (`FED_Reconcile`, `FedExec.mqh` — the heart of the executor)

Replicates `record_engine_ext._run_chunk` arithmetic exactly:

```
base = ACCOUNT_BALANCE                            // realized cash, NOT equity (model compounds off balance)
pass 1 (desired + margin projection), per symbol k with g=fed_frac[k]·InpScale != 0:
    dir  = sign(g);  px = dir>0 ? Ask : Bid
    unit = px · SYMBOL_TRADE_CONTRACT_SIZE · FED_Eurq(k)     // full-map eurq, never a catch-all
    raw  = g·base/unit ;  L = floor(|raw|/step + 1e-9)·step ;  L→0 if < min_lot
    marginSum += |desired|·unit / g_fedLev[k]                // MODEL leverage, not broker leverage
margin cap: if marginSum > InpMarginCap·base  →  one UNIFORM shrink = InpMarginCap·base / marginSum
pass 2 (execute), per symbol: want = re-floor(desired·shrink);  cap |want| at SYMBOL_VOLUME_LIMIT
    rebalance band 0.25: retrade leg k ONLY on sign-flip / cross-to-zero / reduce / |want−held|/|held|>0.25
```

Engine constants match the record exactly: `InpMarginCap=0.9`, `InpRebalBand=0.25`, lot eps `1e-9`.
Fills cross the spread (buy@Ask, sell@Bid); **one net position + one magic per symbol** (HEDGING
account is enforced at `OnInit` — netting → `INIT_FAILED` by design). Compounding is automatic.

### 1.4 Execution primitives (lifted from `V7Core`, renamed `FED_*`, no band logic)

`FED_RoundLots` (floor-to-step, →0 below min-lot); `FED_SendSplit` (chunks any size ≤
`SYMBOL_VOLUME_MAX`, ≤40 iterations, reject-logged); `FED_OpenDir`; `FED_HeldNet`;
`FED_CollectTickets`; `FED_CloseAll`; `FED_ReducePos` (floor, never round up past held; sub-min
partials deferred results-neutral); `FED_MarketOpen` (server-time session check so FX/index legs
never fire into a closed market while the 24/7 clock chart ticks). Reject accounting: `g_fedNReject`,
`g_fedNSplit`, `g_fedNStops`, plus a live-only `fma3v3_rejects.csv` (tester no-op → byte-neutral
backtest) and a `fma3v3_decisions.csv` per-leg audit trail.

### 1.5 Decision flow (`OnTick`)

`FED_GuardianPass()` first (tick-granular worst-mark breaker; returns false while halted → no trading
pass) → new-M1-bar gate (one pass per M1 clock bar) → on a **new H1 bar**, apply the **just-closed**
hour's targets (`iTime(H1,1)` bar-open epoch = the CSV timestamp, ≥1 min causal lag) → **`FED_Reconcile`
every M1 bar** so the lots track balance/price intra-hour exactly as the engine re-derives them each
minute (the fraction is causal; only the lot count moves). The 0.25 band suppresses intra-hour churn.

### 1.6 The exporter (`scripts/export_book_frac_v3.py`)

Emits the already-netted stream v3 replays and **hard-fails** unless (a) the re-parsed matrix
reproduces `static_fed(0.70)` to <1e-12 and (b) the record engine on the parsed stream returns
**€3,872,872** (IC, ×1.6, €10k) and **€1,332,404** (FTMO, ×0.7, €100k, breaker 3.0) to the euro. `s`
is **not** baked in — it is the EA's `InpScale` dial. Shared symbols are summed at emit; the repo→broker
map (`USA500=US500; DAX=DE40`) is applied once. Stream sha `d00b614b…`.

---

## 2. Completeness matrix

| Component | State | Evidence |
|---|---|---|
| **Stream replay + universe** | **DONE** | `FedReplay.mqh` fmt=3 loader, fixed 33-table, hash/fmt/row gates → `INIT_FAILED` on any drift; O(rows) cursor; keep-last-good / flatten-by-omission. |
| **Config-hash guard (LIVE + tester)** | **DONE** | `FED_LoadReplay` compares header `config_hash` to compiled `FED_CONFIG_HASH="51a7541cc2aaa593"` and refuses to trade a drifted stream. *(This is the exact guard the v1.0 audit flagged as MISSING in the live FMA2 executor — v3 has it unconditionally, at INIT, before any order can exist.)* |
| **Sizing (model-exact)** | **DONE** | `FED_Reconcile` replicates `record_engine_ext._run_chunk`: balance-based `raw=g·base/unit`, floor-to-step, min-lot drop, uniform 0.9 margin shrink on model leverage, re-floor. RECON-4 `after/want` median 1.000. |
| **eurq (full currency map)** | **DONE** | `FedConvert.mqh` 8-cross map, always on, tick-value fallback, skip-loud on failure. Revives the 7 Satellite legs v1/v2 killed. |
| **FTMO daily breaker** | **DONE** | `Guardian.mqh` prev-day-close anchor + worst-mark `eq_w` via `OrderCalcProfit`. RECON-4: **28** fires (model 26; the +2 is v3's worst-mark being marginally more sensitive → conservative). |
| **Order execution primitives** | **DONE** | `FED_SendSplit` volume-max chunking, reject backoff+log, `FED_ReducePos` floor-safe trims, `FED_MarketOpen` session gate, HEDGING-account INIT guard. |
| **Volume-limit cap** | **DONE (post-RECON fix)** | `want` capped at `SYMBOL_VOLUME_LIMIT` in pass 2; the margin shrink is still computed on the *uncapped* desired (matches the model) — only un-fillable overflow is dropped. Removes the 51,346-reject spin; equity unchanged (the cap is physical). |
| **Server-tz mismatch guard** | **DONE** | `FED_ApplyHour`: 24 consecutive H1 bars with zero stream-epoch matches → loud one-shot "SERVER-TZ MISMATCH LIKELY / v3 is not trading" (catches a silent no-trade before a wasted run). |
| **Decisions / health / reject logging** | **DONE** | `fma3v3_decisions.csv` (per-leg time/frac/want/held/after/balance/eq/ML), `fma3v3_health.csv` at deinit, live-only `fma3v3_rejects.csv`; FileFlush gated to live so the tester stays byte-neutral. |
| **Dial-agnostic presets** | **DONE** | `InpScale` is the only IC↔FTMO knob. `FABLE_IC` (s=1.6, breaker off), `FABLE_FTMO` (s=0.7, breaker 3.0), `FABLE_PARITY_S10` (s=1.0 sanity). |
| **Compile** | **DONE** | `FableFederation_V3.ex5` sha `740da0ff…`, 0 errors / 0 warnings. |
| **1m-OHLC reconciliation (RECON-4)** | **DONE** | 3 runs, IC Markets 11078280, 1:500, HEDGING, 2020–2025; position fidelity exact; friction ratios measured. |
| **Joint 0.5·margin_used stop-out** | **DEFERRED (by design)** | Not implemented; RECON-4 asserts `eq_w` never approaches 0.5·margin_used in either preset (worst DD 22.58% / 13.33% vs the ~50% needed). See §4.3. |
| **Real-tick runs** | **OPEN** | Per the staged protocol, real-tick follows the 1m-OHLC smokes; IC min-ML>110% confirm is the remaining falsification test (the FTMO demo deploys at 80,000 EUR / 1:30; leverage was proven a non-event — bit-identical equity across the model vs FTMO real leverage tables — so no 1:100 confirm is owed). |
| **Live-horizon extension** | **NOT BUILT** | The frozen stream ends 2025-12-31; live trading past it needs a forward Core-signal recompute + stream extension (documented, not built). |

---

## 3. Tester-readiness — the honest assessment

**Does v3 execute the model in the MT5 tester?** Yes, and RECON-4 proves it at the position level.
There is no bridge problem to solve (the v1.0 audit's central obstacle): v3 is a single binary that
replays a frozen CSV, so it runs natively in the Strategy Tester with no external process. The
open work is *measurement of the friction*, not engineering.

**The three physical constraints — why final equity is 0.66–0.95× the record.** The record engine is
frictionless and unbounded; a real account is neither. All three bind at s=1.6; **none bind at the
deployable FTMO dial** (Run 3, s=0.7, clean 0.95× with zero rejects):

| Constraint | Record engine | Real account | Binds when | RECON-4 cost |
|---|---|---|---|---|
| **Transaction friction** (spread/commission) | modeled coarsely | real per-trade cost | always; compounds with leverage | 0.95× @ s0.7 → 0.84× @ s1.0 → 0.66× @ s1.6 |
| **`SYMBOL_VOLUME_LIMIT`** | **none** | XAUUSD 10, SOLUSD 1000, ETHUSD 100 lots (this tier) | book past **~€2M/s** (XAUUSD binds first) | ~0–6% @ €10k, 17–40% @ €1M |
| **Broker margin** | model per-symbol leverage | broker / retail 1:30 grant | high s on retail leverage | self-limits the book (see §Honest caveats) |

**The €3,872,872 IC-s1.6 record is a frictionless ceiling, not physically reachable on one retail
account at that scale** — XAUUSD alone caps at ~half the model's target past ~€2M/s. This is the
long-standing "s=1.6 not deployable" honesty flag, now decomposed into two independent causes
(volume + margin) and *quantified*. Scaling levers (both owner-raised, both valid): a higher-tier
account (larger `SYMBOL_VOLUME_LIMIT`), or N parallel accounts at €C/N each whose aggregate = the
full model position (multiplies every volume limit by N; pure capacity, no diversification).

**The margin picture is better than the pre-v3 flag claimed.** v3's own margin cap (0.9·balance on
*model* per-symbol leverage, which ≈ a 1:30 account's per-symbol grant) self-limits the book, so
s=1.6 @ 1:30 ran the full 2020–2025 backtest at **min ML 121%** — far above IC's 50% stop-out and
~11pp over the owner's ML≥110% floor. The old "s=1.6 not deployable at 1:30" flag was v1-over-leverage
-specific and is **disproven for v3** (`MODEL_SPEC.md` honesty flag #1).

---

## 4. Punch lists

### 4.1 The 3-reviewer adversarial pass — findings and the fixes applied (all DONE)

The first build (`d516350b…`) went through a three-reviewer adversarial read before any tester run.
Every finding was fixed; the binary is now `740da0ff…` after the additional post-RECON volume fix.

| # | Finding | Fix | Where |
|---|---|---|---|
| R1 | A transient missing quote on a **nonzero-target** leg would size `want=0` and be read as a cross-to-zero **close** — flattening a held position on a data hiccup | **Unsized-leg HOLD**: `unsized[k]` flag; if a nonzero target can't be priced, hold the position and defer, never flatten | `FedExec.mqh` pass 1 `unsized[]`, pass 2 `if(unsized[k]) …continue` |
| R2 | Sizing ran **once per H1** — but the engine re-derives desired lots and the uniform margin shrink **every minute** off current balance/price; at s=1.6 (margin cap binding) this is the single largest fidelity error | **Re-size every M1 bar**: `FED_Reconcile` runs each M1 clock bar; the fraction stays causal (H1 boundary), only the lot count tracks intra-hour | `FableBook.mq5` `OnTick` `[FIDELITY]` |
| R3 | Breaker tested point-in-time `ACCOUNT_EQUITY`, but the engine trips on **worst-mark** `eq_w` (bar low-longs / high-shorts) | **Worst-mark breaker**: `FED_WorstMarkEquity` via `OrderCalcProfit` on M1 low/high | `Guardian.mqh` |
| R4 | Breaker anchor used `max(balance,equity)` (v1 Guardian); the engine anchors on the **previous-day CLOSE-mark** equity (`last_close`) | **Prev-day-close anchor**: carry the last `ACCOUNT_EQUITY` before rollover; day 1 = real seed balance | `Guardian.mqh` `g_fedPrevClose` |
| R5 | A broker-server timezone offset vs the record feed grid would silently match no stream epoch → v3 trades nothing, undetected until the run is wasted | **TZ guard**: 24 consecutive H1 misses with zero hits → loud one-shot warning | `FedReplay.mqh` `FED_ApplyHour` |
| R6 | Per-row `FileFlush` in the tester is heavy I/O and could perturb timing | **Gated FileFlush**: flush live-only; tester relies on `FileClose` → byte-neutral backtest | `FedExec.mqh` `FED_LogRow` |
| R7 *(post-RECON)* | At s=1.6, volume-limited legs (XAUUSD etc.) retried the un-holdable excess **every bar** — a 51,346-reject spin | **Volume-limit cap**: cap `want` at `SYMBOL_VOLUME_LIMIT`; margin shrink still on uncapped desired; equity unchanged (physical cap) | `FedExec.mqh` `[FIX]` vlim clamp |

### 4.2 To FULLY-RECONCILED (the remaining falsification tests) — ordered

| # | Item | Effort | Where |
|---|---|---|---|
| T1 | **IC real-tick min-ML confirm.** Re-run `FABLE_IC` @ 1:30 on real ticks; assert intra-bar min ML stays **>110%** (1m-OHLC showed 121%, but real ticks traverse the bar interior). Gates the s=1.6 IC ship commit | M (wall-clock) | owner MT5 |
| T2 | **FTMO dial confirm (leverage MOOT).** The FTMO demo deploys at 80,000 EUR / 1:30; leverage was proven a non-event (bit-identical final equity across the model vs FTMO real leverage tables), so no 1:100 confirm run is owed. Sweep says ret/DD peaks at **s≈0.5** (4.78, DD 7.82%) vs shipped s0.7 (4.05, DD 13.33%) | M | owner MT5 |
| T3 | **FTMO rule-compliance scoring** of the v3 curve: worst-mark daily/monthly vs the −5%/−10% rules. The internal 3% breaker is tighter than the external 5% rule, but warm-COVID scoring is the open question (see §Honest caveats) | S–M | FMA3-side |
| T4 | **Run-2 clean-record refresh.** RECON-4 Run 2's headline was captured pre-fix (spin); the clean re-run (sha `740da0ff`) confirmed €2,552,961.62 / 0 rejects — fold into the standing RECON row | S | FMA3-side |

### 4.3 The deferred joint stop-out — the one honest omission

The record engine flattens if worst-mark `eq_w < 0.50·margin_used` (mid-close basis). v3 does **not**
implement it. Rationale: in-sample it never triggers (IC worst DD 22.58%, FTMO 13.33% — the mechanism
needs ~50%), so it cannot affect the reproduction; adding an unvalidated crisis mechanism that could
fire *spuriously* was judged worse than delegating to the broker stop-out. RECON-4 asserts `eq_w`
never approaches 0.5·margin_used in either preset, proving the omission immaterial to the record read.
**It must be added before any live-crisis claim** — the in-sample window contains no event that
exercises it, so its absence is untested against a real tail, not proven safe.

---

## 5. Recommendation — shortest honest path to deploy

1. **Ship the executor verdict now.** v3 provably holds the model's exact target position (`after/want`
   median 1.000, all runs); the equity gap is fully attributed to three named physical constraints.
   This is the release: *the model is v1.0's deliverable; v3.0 is the EA that faithfully executes it.*
2. **Run T1 (IC real-tick min-ML) and T2 (FTMO dial — deploys 80k/1:30; leverage proven a non-event, no 1:100 confirm owed)** — the two provisional dials
   (IC s=1.6 owner-accepted, FTMO s≈0.5 recommended) are both explicitly *pending* these confirms.
   Neither is a rebuild; v3 is dial-agnostic, so each is a preset edit.
3. **Do not present any record number as a deployable promise.** Achievable equity is **0.66–0.95×**
   the record by dial/scale. The €3,872,872 IC figure is a frictionless ceiling; the honest deployable
   IC reproduction on one retail account is ~€2.55M @ s1.6 *(RECON-4/FableFederation_V3; superseded — native `FableBookNative` EA: €2.93M / 0.76×, see CURRENT_STATE.md)* (or lower at a volume-safe scale), and the
   clean FTMO reproduction is €1,265,541 @ s0.7 (0.95×, zero rejects).
4. **Add the joint stop-out before any live-crisis fidelity claim** (§4.3), and **score the FTMO
   curve warm** (T3) before trusting s0.7 against the −10% rule — the cold-start gates understate
   COVID.
5. **Do not revive the v1/v2 compute-live path.** It provably diverges at s≠1; replay is the only
   faithful architecture and every open item above is a measurement, not a redesign.

---

## Honest caveats

1. **The model figures are IN-SAMPLE record reads.** €3,872,872 (IC) and €1,332,404 (FTMO) are
   1-minute worst-mark record-engine outputs over 2020Q1–2025Q4, reproduced to the euro by
   `model/v3/reproduce.py` — not live results. MT5 real-tick and a live demo remain the falsification
   tests; RECON-4 (1m-OHLC) is the first, not the last, of them.
2. **Achievable equity is 0.66–0.95× the record, always below it.** Friction compounds with leverage;
   the volume ceiling and margin both bite at high s. The IC s=1.6 record is a *frictionless,
   unbounded-capacity* number and is **not physically reachable on one retail account at that scale**
   (XAUUSD caps at ~half the target past ~€2M/s). Deploy the dial you can actually hold, or split
   across N accounts.
3. **Both deployable dials are PROVISIONAL.** IC s=1.6 is owner-accepted (min ML 121% @ 1:30 on
   1m-OHLC) but pending a real-tick intra-bar min-ML>110% confirm — real ticks traverse the bar
   interior the OHLC feed skips. FTMO s≈0.5 is *recommended from the sweep* (the FTMO demo deploys at 80,000 EUR / 1:30; leverage was proven a non-event, so no 1:100 run is owed).
4. **The FTMO gates are cold-start in-sample.** Warm re-validation shows s0.7 + 3% breaker breaches
   COVID by 7.5–10.8pp of the −10% rule; the crisis-safe dial is ≈ s0.30–0.35, not 0.7. The €1.33M
   FTMO figure is also a fully-compounded never-withdraw upper number that is scored under a
   *contradictory* monthly withdraw-to-base compliance frame — you cannot both compound to €1.33M and
   reset to base monthly.
5. **The joint 0.5·margin_used stop-out is not implemented** (§4.3). It is immaterial to the in-sample
   reproduction (asserted), but its absence is *untested against a real tail*, not proven safe. Add it
   before any live-crisis claim.
6. **The breaker fires +2 vs the model (28 vs 26).** This is v3's worst-mark being marginally more
   sensitive than the engine's — conservative, not a defect — but it means the FTMO curve is not
   byte-identical to the record even before friction.
7. **The frozen stream ends 2025-12-31.** Live trading past it needs a forward Core-signal recompute and
   a stream extension that is documented but **not built**. v3 as shipped is a faithful *replayer* of a
   finite frozen decision file, not a live signal generator.
8. **v3 supersedes the v1/v2 EA stack and the v1.0 FMA2 audit for the shipping EA** — but the v1/v2
   binaries, the VBalance/quarterly-reseed/e34 machinery, and their presets still exist in the tree.
   Deploy only `FableFederation_V3.ex5` (sha `740da0ff…`) with a fmt=3 stream; the compute-live path
   provably diverges at s≠1 and must not be used.

*Sources: `mt5/ea/FableBook.mq5`, `mt5/ea/Include/FMA3v3/{FedConvert,FedReplay,FedExec,Guardian}.mqh`,
`model/v3/{README,MODEL_SPEC,PINNED_INPUTS,EA_V3_DESIGN,RECON4_RESULTS}.md`,
`scripts/{export_fed_frac_v3,sweep_s_volcap}.py`, `research/protocol/RECONCILIATION.md`,
`archive/docs-v1.0/FMA2_EA_AUDIT.md` (superseded for the shipping EA). All numbers are canonical to the v3
model of record; none recomputed here.*
