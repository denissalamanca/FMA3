# Option 1 — Native all-MQL5 sub-book sims (the no-CSV dynamic-tester alternative)

**Goal:** run *both* sub-books as standalone SIMULATIONS inside MQL5 — a `.mqh` per book carries that book's logic but keeps an idealized in-memory account instead of reading the broker — so a single `.ex5` reproduces the model `fed[h,k] = f7·(w·a_h/j) + f34·((1−w)·b_h/j)` (w=0.70, j=w·a_h+(1−w)·b_h; [`MODEL_SPEC.md`](MODEL_SPEC.md), [`reproduce.py`](reproduce.py)) **dynamically in the MT5 Strategy Tester with no precomputed CSV**. This is an **alternative to**, not a replacement of, [`FORWARD_GENERATOR_SPEC.md`](FORWARD_GENERATOR_SPEC.md) — that spec is not touched.

This document is deliberately un-triumphant. The headline win is real but **partial and staged**, and the four adversarial reviews below are folded in as first-class constraints, not footnotes. If you only read one section, read §1 (verdict) and §9 (when this is the wrong choice).

---

## 1. Feasibility verdict (per component, v34 decision resolved)

Every assessment converged on one split: **the v7 half is tractable, the v34 half is the wall.** The resolved decision is a **sequence behind one interface**, not port-vs-bridge:

| Component | Verdict | Why |
|---|---|---|
| **v7 signal layer** (targets, band re-split stepper, seed chain) | **GREEN** | Already exists in `V7Core.mqh`, G1-proven to the cent (EUR 398,368.75). It IS the resumable one-bar stepper the Python path lacks (its `load_v7_forward_frac` is the repo's one sanctioned `NotImplementedError`). |
| **v7 standalone account `a_h`/`eqc`** | **YELLOW** | Brand-new MQL5. V7Core is G1-proven as a tracker of the **real** account (`UpdateRealized` folds `HistoryDealGetDouble`, band trigger fires on real `VBalance`). The idealized worst-mark equity that produces `a_h` has **never** been computed in MQL5. Moderate build, but unproven — see §5 killer. |
| **1m worst-mark account kernel** (`Acct1m`) | **GREEN-ish** | ~120-line 1:1 port of `record_engine_ext._run_chunk`. But **two flavors** exist (see below) — not one shared primitive. |
| **v34 alpha `f34`** (8 pandas sleeves + ensemble + hard-limits) | **RED / the wall** | Python-only, ~1400 lines, never in MQL5, bit-parity to `build_c2` required or it silently redefines the model. Feed-provenance makes even a perfect port miss the pin. |
| **v34 account `b_h`** | **YELLOW** | `f34` → `account_engine_1m._run_chunk`. The account port is tractable; it is gated on the alpha above. |
| **Tester dynamism (no-CSV)** | **GREEN for v7, RED for v34 until port lands** | Multi-symbol dynamic tester access is proven in this codebase (V7Core reads M1 for 8+ non-chart symbols in-tester). But "no CSV for the full book" is false until V34Sim retires the bridge. |

**Resolved v34 decision — bridge first, port incrementally behind one interface, and treat the bridge as possibly permanent.**

```
interface ISimBook {
   void   StepMinute(const MinuteFrame &f);   // advance the idealized 1m account
   double NativeEquityMult();                  // a_h or b_h  (hour-OPEN sample)
   void   EmitFrac(int h, double &frac[]);     // f7[h] or f34[h]  (last-1m sample)
   bool   LoadSeed(...);  void SaveCheckpoint(...);
}
```

`V7Sim`, `V34Sim` (native) and `V34Bridge` (thin file reader) all implement `ISimBook` identically. The blender and executor never know which backs v34.

- **Ship v7 fully native** (`V7Sim`) — delivers the no-CSV dynamic-tester win for the tractable half now.
- **Back v34 with `V34Bridge` at first** — a thin reader of the existing Python-produced `f34`/`b_h`. You lose *only* the v34 tester-dynamism; you keep everything else and do **not** modify `FORWARD_GENERATOR_SPEC`.
- **Port v34 sleeve-by-sleeve into `V34Sim`**, each parity-gated to `build_c2`, low-risk sleeves first (seasonal, mag_xau, intraday, crisis ≈ 57% of weight). Retire the bridge **only** when all 8 sleeves + `b_h` pass parity.
- **The fully-native, no-CSV, tester-and-live end state is real but gated on that port completing and passing parity.** Per the `v34-port-fidelity` review, that gate may never close for a record-matching path (see §9). Do not promise it as if it will.

---

## 2. Module layout (`.mqh`)

| Module | Role | Origin / risk |
|---|---|---|
| `FableNative.mq5` | Main EA: clock, per-bar orchestration, tester/live mode switch | new, thin |
| `Feed.mqh` | Per-symbol M1 pull, `has_bar` mask, ffill, ask-OHLC reconstruction, union-grid clock | new, bounded |
| `SymbolConst.mqh` | **Frozen** 33/37-symbol table: contract, commission, leverage, lot_step, min_lot | port of `core.S.INSTRUMENTS`; **hermetic** |
| `CostModel.mqh` | NSF5 swap (markups, triple-day, NY-17:00 rollover) + eurq (bar-close-mid, 8-cross map) | port of `engine/costs.py`; subtle |
| `Acct1m.mqh` | Worst-mark 1m account primitive: `{balance, lots[K], entry[K]}`, fill-across-spread, reband, uniform shrink, worst-mark equity, stop-out | port of `record_engine_ext._run_chunk` |
| `AcctNoliq.mqh` | v7 account flavor: same primitive at **stop_out=1e-9 (noliq)** + DD throttle | port of NSF5 `backtest._run_core` |
| `V7Sim.mqh` | v7 band book → `f7[h]` + `a_h`. Fork of V7Core signal layer; per-sleeve equal-capital **re-split** ledger | fork of V7Core; **moderate, unproven equity** |
| `V34Sim.mqh` | Native v34 alpha → `f34[h]` (8 sleeves + ensemble/hard-limits) driving `Acct1m` → `b_h` | **TALL POLE**, staged |
| `V34Bridge.mqh` | Thin reader: consumes existing Python `f34`/`b_h` behind `ISimBook` | trivial; interim, maybe permanent |
| `Blender.mqh` | `fed[h,k]=f7·(w·a/j)+f34·((1−w)·b/j)`, union-ffill, net shared symbols | port of `reproduce.py` |
| `Executor.mqh` | Real sizing `fed·InpScale·BALANCE/unit`; delta-trade (live) / record (tester) | reuse FMA3v3 `FedExec`/`FedReplay`/`FedConvert` |
| `SeedState.mqh` | Ratio-chained splice-seed load; hourly full-ledger checkpoint save/restore | template = V7Core `SaveState`/`LoadState`, hardened |

**Two account flavors, not one.** The `native-sim-mql5` design collapsed these into "one `Acct1m` shared by both sims"; the `tester-determinism-cost` review is right that this is wrong. `a_h` (`=eqc`, `research/outputs/v7_book_equity_1m.parquet`) is produced by NSF5 `_run_core` under **stop_out=1e-9 (noliq)** (asserted at `extract_positions.py:134`). `b_h` and the real record account use `account_engine_1m._run_chunk` under **stop_out=0.5**. Two independently-written engines with different stop-out/margin/fill code. `V7Sim` must reproduce `_run_core`; hence `AcctNoliq.mqh` is a **second, separately parity-gated port** — do not merge it into `Acct1m`.

---

## 3. Per-bar control flow

Clock chart = a 24/7 symbol (**BTCUSD**) so the account steps every minute; FX/index gaps handled by `has_bar`+ffill. On each completed M1 bar of the clock:

1. **Feed.mqh** pulls each symbol's completed M1 bar → `MinuteFrame{bid_o,bid_c,bid_l, ask_o,ask_c,ask_h, has_bar}`. Absent bar ⇒ `has_bar=false`, hold position, mark at last close (mirror `record_engine_ext._densify`, lines 254-268/345-349).
2. **CostModel** — at NY-17:00 rollover accrue swap on notional (triple-Wed FX / triple-Fri index / daily crypto).
3. **V7Sim.StepMinute** — on UTC-day rollover: extend daily series, `RecomputeDaily`, `BandTriggered` check, `QuarterRebalance` reseed if fired. Every minute: size sleeves off `VBalance`, fill across spread with 0.25 reband, worst-mark (noliq), update the equal-capital re-split ledger → v7 book equity.
4. **V34 book.StepMinute** — *native:* recompute `f34` **once per H1** (warm rolling state), step `Acct1m` every minute → b-equity. *bridge:* no per-minute work; equity/positions arrive at the H1 boundary from file.
5. **At H1 boundary** (`iTime(H1,1)` closed hour) — honor the sampling contract **exactly** (`FORWARD_GENERATOR_SPEC` §5.3):
   - **`a_h`, `b_h` sampled at hour-OPEN (h:00)**
   - **`f7[h]`, `f34[h]` sampled at the LAST 1m bar of `[h,h+1)` (~h:59)**
   - Sampling `a_h`/`b_h` at h:59 silently breaks reconciliation — hard rule.
6. **Blender** — `j=w·a+(1−w)·b`, `fed[h,k]=f7·(w·a/j)+f34·((1−w)·b/j)`, w=0.70; union `frac7`/`frac34` indices, causal-asof ffill a/b with `fillna(1.0)`, `fillna(0.0)` fractions; **net the 6 shared symbols** (v7 `USDJPY = SL_JPY+SL_S6UJ`, then cross-book netting to the 33-symbol universe).
7. **Executor** — `lots_k = fed[h,k]·InpScale·ACCOUNT_BALANCE/unit_k`; delta-resize each of 33 magics (live) or step the real-trade worst-mark record (tester).
8. **Checkpoint** (live only) — persist all three sim ledgers hourly (§6.2, §7).

Three worst-mark accounts advance per minute: a-shadow (v7, 8 legs, noliq), b-shadow (v34, 31 legs, 0.5), real/record (33 legs, 0.5). The only compute bomb is a non-incremental v34 — native `f34` **must** be a bounded per-hour stepper, never a from-2020 re-run per hour (that is the v7-extractor failure mode; `FORWARD_GENERATOR_SPEC` §3.1/§4.3).

---

## 4. Standalone-account bookkeeping (the sound core)

Compute worst-mark **explicitly** — do **not** lean on `OrderCalcProfit` (its conversion uses deposit currency at the current tester-tick rate and the broker's contract size, both wrong vs the model). Use it only as a cross-check.

```
eq_w = balance + Σ_k (worst_px_k − entry_k)·lots_k·contract_k·eurq_k
worst_px_k = bid_low_k  if lots_k > 0     // long marked at its own worst
           = ask_high_k if lots_k < 0     // short marked at its own worst
```

Fill/close mechanics (1:1 port of `_run_chunk` / `_run_core`, `record_engine_ext.py:315-434`):
- **Open/add** — cross spread (ask long / bid short) + commission on `|Δlots|`, volume-averaged entry.
- **Close/reduce** — realize `(px−entry)·lots·contract·eurq` + commission → balance.
- **One uniform margin shrink** across legs (`0.9·balance`); **0.25 rebalance band**; min-lot drop + lot-step rounding with the `+1e-9` epsilon.
- **Joint stop-out** on the co-timed worst mark (v7: `1e-9` noliq; v34/real: `0.5·margin_used`).
- Mark on **completed M1 bars only** — the 1m worst-mark IS the engine of record; tick-driving over-marks and diverges.

**Hermetic constants** — `SymbolConst.mqh` supplies contract/commission/leverage/lot_step/min_lot; the accounting path must **never** read `SymbolInfoDouble`. Only bid/ask **prices** come from the feed. (V7Core's entire execution layer — `OrderCalcMargin`, `SYMBOL_VOLUME_LIMIT`, `SymbolInfoSessionTrade`, reject-backoff — is broker-coupled and must be **gutted** from the accounting path; only the signal layer is reusable. See §5 killer.)

v7 reuses V7Core's equal-capital re-split ledger: at a band trigger `g_seed[n]=book_equity·W[n]`, `g_realized` reset, per-sleeve `{lots,entry}` **delta-resized (not flattened)** across the reseed — "no splice flattery," done incrementally.

---

## 5. Native-equity warmup / seed

Two distinct seeds — do not conflate:

- **Signal warmup** — donch/SMA200/AnnVol (v7), and v34's 250d/200d/125d/63d lookbacks + hysteresis state. Solved for v7 by `ExtendSeries` (~420 days, `V7Core.mqh:191-201`). For v34, cold-starting mid-stream gives wrong hysteresis for *months* → the COVID cold-start **k≈4.7 artifact** (MEMORY: `record-engine-COVID-warmup`). **Tester fix: start ≥2019**, anchor the equity base at 2020 t0 = 1.0. This needs ~1yr pre-2020 M1 for the full ~37-symbol universe on the broker feed — a real data-depth constraint (crypto/index depth is where retail brokers fail).
- **Account/band carry-state** (live only) — export **once** from the frozen 2020-2025 Python batch: v7 `{g_seed[], g_quarterStart, g_realized[], a_last}`; v34 `{balance, lots[K], entry[K], b_last}` at 2025-12-31 23:59.

**Ratio-chain, never re-base:** `a_h = a_last·(sim_eq[h]/sim_eq[boundary])`, same for b. Re-basing a and b independently to 1.0 changes the a/b ratio and therefore **every** blend weight `w·a/j`, `(1−w)·b/j` while passing all internal `<1e-12` self-checks — the single highest-severity, silent-wrong surface, identical in both architectures. `SeedState.mqh` is **safety-critical**.

**The `reliability-maintainability` killer on seeding, folded in:** today's `SaveState()` (`V7Core.mqh:770-782`) persists only 12 `g_seed` values at `DoubleToString(...,4)` — 4 decimal places, no `lots`/`entry`, no warm state. That is fine for a euro seed and **catastrophic** for a ratio-chained multiple that weights the whole book. A full-ledger, high-precision (≥12 sig-digit), atomic (tmp+rename), all-three-accounts checkpoint is a **new safety-critical serialization path** with no equivalent today. A restart that drops the in-memory ledger without it re-triggers the COVID cold-start artifact. Boot self-reconcile (§7) is mandatory.

**Tester** rebuilds from 2020 → no splice seed (its structural advantage). **Live** cannot re-sim 6 years at OnInit → must load the seed. **The seeding problem is relocated to OnInit, not eliminated.**

---

## 6. Tester dynamic mode vs live mode

### 6.1 Tester (the headline win — v7 now, v34 after port)

- **"1 minute OHLC" mode.** Real-tick over-resolves below the 1m worst-mark model and diverges; OHLC mode is faithful **by construction**. But see the `tester-determinism-cost` killer: in OHLC mode the tester **fabricates** ticks from bid OHLC + one integer spread — there is **no ask series**, so `ask_high` is forced to `bid_high + spread·point`. Real ask-tick accumulation only exists *live*. This mis-marks the short worst-mark exactly in the crisis tail (COVID) where spreads blow out and where the campaign's MaxDD lives. **Consequence: 1m-OHLC tester MaxDD/crisis claims are not certifiable here** — keep tail certification on the six-field Python engine + real-tick (§8, §9).
- BTCUSD 24/7 chart; **pinned M1 history** starting ≥2019 for the full ~37-symbol universe. MT5 has no native history freeze — the tester rebuilds its cache from the terminal's mutable broker M1 base. **Freeze explicitly as custom symbols** (import per-symbol M1 CSVs into a dedicated pinned terminal, pin the build, record a sha of the full ~41-symbol bar set in the RECON entry) or the run is not reproducible across terminals/refreshes and cannot be a gate.
- Deterministic **only** within one terminal + pinned custom-symbol history. `a_h`/`b_h` depend on the entire path from 2020; any secondary-symbol history change shifts the whole curve.
- **Grade at POSITION level** (`held fraction == fed_frac·s` per bar), **not equity** — the tester runs the broker feed, not the frozen IC parquet (~8pp CAGR divergence documented, `FORWARD_GENERATOR_SPEC` §6). It will **not** reproduce EUR 3,872,872 and shouldn't be expected to. RECON4 already proves the *easier* CSV-driven hybrid lands at 0.66×–0.95× the record and fires the breaker 28× vs the model's 26×; a fully-native version adds reconstruction error **on top of** that gap, never closes it.
- Delivers the owner's goal for v7: one `.ex5`, dynamic, **no precomputed CSV** — for v7 today, for the whole book only once v34 is ported.

### 6.2 Live

- OnInit loads the ratio-chained seed (no 6-year backfill), runs forward, **hourly full-ledger checkpoint** for restart durability.
- Executor delta-trades the 33 netted magics.
- The live 2026 stream remains the **un-fitted out-of-sample holdout** — a perfect sim still produces numbers the campaign has agreed not to trust blindly.
- **The no-CSV win is tester-scoped.** Live still needs a seed at OnInit; the seeding problem the forward generator solves is relocated, not removed.

---

## 7. Reconciliation stance — MONITOR, DON'T FEED BACK (confirmed under pressure)

Definitional, not a preference:
1. The model **is** the idealized, account-independent curves a,b (a live account cannot reconstruct them; `MODEL_SPEC` §1). Feeding real fills back creates a circular real-equity → sim-balance → frac → real-sizing loop = a different, unvalidated strategy.
2. The 6 shared symbols are **netted** into one position each in the real account, so per-book real P&L on them is **physically unmeasurable** (`MODEL_SPEC` §2/§7) — feedback isn't even well-defined.

So the sims live in their own idealized world, keeping their **own** spread-cross/fill model identical to `account_engine_1m`/`_run_core` — never borrowing the real account's fills (borrowing drifts `b_h`/`a_h` off the record-engine references the pin was validated against).

**One authoritative correction channel that is NOT feedback:** periodically re-run the **frozen Python batch forward on the SAME broker feed** and, on drift beyond tolerance, **reseed** the sim from the batch. This is *correction-from-batch*, categorically different from feedback-from-live-account. The real-vs-sim gap stays a monitored **friction ratio** (RECON-4 ≈ 0.66–0.95×), not a control input.

**The `reliability-maintainability` consequence, stated honestly:** because the only correctness oracle for the sims is that daily warm Python batch reconcile-and-reseed (a file handoff), the "all-MQL5" system is **permanently shadowed by and subordinate to** the Python pipeline it was meant to replace. Two implementations of one model that must agree forever, the harder one (MQL5) with no unit tests and no step-debugger over a 3M-minute run. This is a cost, not a bug — but it means the CSV/Python producer is never actually deleted (§9).

---

## 8. How it reproduces the model + how it is verified

`fed[h,k] = f7·(w·a_h/j) + f34·((1−w)·b_h/j)`, w=0.70, j=w·a_h+(1−w)·b_h.

Validation is against a **same-feed Python re-run of the same kernel on the same broker-exported bars**, at **~1e-6 relative, position-level** — *not* against the frozen IC curves (that flags expected feed physics as a bug), and *not* at the model's 1e-12 (that gate belongs to the pandas BLEND encoding, not the a_h/f7 physics; numba float64 vs MQL5 double differ below cent level). The harness exports the EA's reconstructed 1m bid/ask bars and re-runs `record_engine_ext`/`_run_core_pos` on **those same bars**. Validation is **not** CSV-free; the no-CSV win is live sizing, not the reconciliation loop.

**Gating sequence (retire the dominant risk first):**
1. **Feed-provenance number FIRST, before any sleeve port** (the `v34-port-fidelity` decisive cheap experiment): run `books.build_v34_frac_1h` on broker-exported H1 bars vs the frozen `research_cache/*_1h.parquet`, measure the `f34` divergence, propagate through `static_fed`, report the resulting `fed[h,k]` and final-equity delta vs the €-exact pin. Make "how far from the pin does live-feed v34 land" a **known number**, not an assumption.
2. **v34 account kernel first** — build only `Acct1m` + `b_h`, reconcile `b_h` against `v34_s10_pin_curve.parquet` using the **same 1m IC bars the pin used** (`NewStrategyFable5/cache/bars_1m_ic`) with the **frozen `f34` matrix supplied verbatim**. This is the one piece that CAN reach true pin parity (frozen, suppliable inputs) — it validates the whole accounting mechanic independent of both the alpha port and feed provenance.
3. **v34 alpha parity on identical inputs** — port only `core.realized_vol` / `ewm-mean` / `ewm-std` / `rolling-std` and reconcile ONE sleeve's vol series + full position matrix on the **same frozen `research_cache/*_1h.parquet` bars** (not broker bars). If `ewm(adjust=True)` and `ddof=1` std cannot hit ~1e-6 on identical inputs, **the port is dead before feed noise enters — stop there.** Then port remaining sleeves, low-risk first; carry_breakout (weight 0.046, hardest mechanics) last or with an approved small approximation.
4. **v7:** `V7Sim` tester run vs same-feed `extract_positions.py` re-extraction → ~1e-6, cent-level, against `v7_book_equity_1m.parquet` (noliq), **not** `_run_chunk`. Re-reconcile the band re-split trigger **DATE** — V7Core's own open `REVIEW` flag (`V7Core.mqh:729`, the 3-into-1 S6 slot aggregation) is a **hard blocker**; a single divergent trigger forks the entire seed chain and every downstream `a_h`.
5. **Union-grid gate** — emit the EA's per-minute grid + `has_bar` mask, diff against `record_engine`'s `np.unique` union over all ~41 symbols on the same bars; alarm on any grid-minute mismatch (a clock-chart minute grid misses minutes where only a non-BTC symbol printed).
6. Retire `V34Bridge` **only** after all 8 sleeves + `b_h` pass parity. **All-native LIVE is gated on this + a warm-start proof + a real-tick MaxDD cross-check.**

---

## 9. Failure modes + safe degradation

| Failure mode | Detection | Safe degradation |
|---|---|---|
| **Splice-seed re-based instead of ratio-chained** (silent, passes all self-checks) | same-feed batch reconcile; OnInit splice-continuity assertion (hard-fail on any jump in `j`) | REFUSE TO TRADE (`INIT_FAILED`); never trust a restarted ledger unreconciled |
| **v34 alpha bit-drift** compounding over 6y | per-sleeve parity to `build_c2` on identical inputs | keep `V34Bridge` (Python producer) as the live path for v34; do not retire |
| **Ask-OHLC fabricated from one spread int** mis-marks crisis tail | COVID-window diff of worst-mark/MaxDD vs six-field IC parquet | restrict tester claims to position-parity/CAGR-shape; certify MaxDD on six-field Python + real-tick only |
| **Missing EUR cross** (EURNOK/EURSEK/EURCHF) freezes/mis-scales a currency | OnInit assert all 8 crosses quoted (guard at `record_engine_ext.py:669-682`) | synthesize EURCHF (the batch did); hard-fail if unresolvable |
| **Broker-spec bleed** (SymbolInfo in accounting path) | code audit: no `SymbolInfoDouble` in `Acct1m`/`AcctNoliq` | hermetic `SymbolConst` only; prices-only from feed |
| **Wrong-but-consistent state corruption** across 3 in-process ledgers | per-account struct/namespace, zero shared globals; boot self-reconcile vs batch | INIT_FAILED on mismatch; the lock_v5 poisoning that forced OS-process isolation in Python is *re-introduced* by collapsing to one process — mitigate with strict struct isolation |
| **Terminal restart drops in-memory ledger** = cold-start k≈4.7 | hourly atomic full-ledger checkpoint (≥12 sig-digit) | OnInit replays checkpoint, refuses to trade if it doesn't match batch |
| **v7 band-trigger DATE forks** the seed chain | trigger-date diff vs Python probe-loop; V7Core `:729` REVIEW | hard blocker before `a_h` is used anywhere |
| **Non-incremental v34 re-run** per hour = compute bomb | design invariant: bounded per-hour stepper only | if a sleeve can't be made incremental+warm-parity-proven, it stays on the bridge |

**Safe-degradation principle:** every native component has a bridge/Python fallback. The system degrades to "v7-native + v34-Python-bridge" — which is *still a Python→file hybrid for half the book*. That is the honest floor, and per §9 it may be the ceiling too.

---

## 10. Build plan (phased)

- **P0 — mechanical spine, low cost.** Fork V7Core signal layer → `V7Sim`; build `AcctNoliq`; stand up `Acct1m` + `V34Bridge` behind `ISimBook`; wire `Blender` + `Executor`. Run the **v7 half fully dynamic** in the tester (position-level graded). Validates the whole spine cheaply.
- **P1 — the decisive cheap experiments (do BEFORE committing to the alpha port).** (a) feed-provenance number (§8.1); (b) `Acct1m` + `b_h` vs `v34_s10_pin_curve` on frozen IC bars (§8.2); (c) one-sleeve vol+position parity on identical inputs (§8.3). **Any of these failing is a go/no-go stop.**
- **P2 — v7 fidelity.** `V7Sim`/`a_h` vs `v7_book_equity_1m.parquet` (noliq) on broker overlap; re-reconcile band-trigger dates; close the `V7Core:729` REVIEW.
- **P3 — v34 alpha sleeve-by-sleeve.** seasonal → mag_xau → intraday → crisis (≈57% weight, low fidelity risk), each parity-gated to `build_c2`; then meanrev, crypto_smart, trend_v2; carry_breakout last.
- **P4 — seed + live hardening.** `SeedState` ratio-chain exporter (safety-critical); atomic full-ledger hourly checkpoint; OnInit boot self-reconcile + splice-continuity assertion.
- **P5 — retire bridge (only if P3 fully passes) + all-native live.** Gated on: all 8 sleeves + `b_h` parity, warm-start bit-parity proof over a 2020 overlap, real-tick MaxDD cross-check.

**Freeze-before-port gate:** the v3.4 sleeve set + weights + scale must be **versioned-frozen** (file mtimes show sleeves + config churning daily 2026-07-08..10, `sleeves/` holds 15 files while 8 ship, scale just went s11→s10). Porting a target research is still moving guarantees perpetual dual-language re-verification and defeats the maintainability case on its own. Log every new `.ex5` as a fresh **FMA3-RECON-N** entry per the standing reconciliation clause.

Do **not** touch `FORWARD_GENERATOR_SPEC.md`. Keep the CSV/forward-generator as the live path of record until — and only until — the native v34 stepper is proven bit-identical warm.

---

## 11. Open questions

1. **Does `ewm(adjust=True)` + `ddof=1` std actually reach ~1e-6 in hand-rolled MQL5 doubles on identical inputs?** P1(c) answers this. If no, native v34 is dead and the bridge is permanent.
2. **What is the feed-provenance `fed[h,k]` delta** (P1a)? Until this number exists, "native v34 reproduces the model" is an assumption. The reference pipeline also contains **lookahead** (`core.universe_frames` does `.ffill().bfill()`; `commission_frac` uses full-sample `px.median()`) that a forward stepper *cannot* reproduce — so a same-feed native run may diverge from the reference by construction. Decide: re-pin the model of record to a broker-feed `b`, or accept the bridge.
3. **Does the broker quote all 8 EUR crosses with ≥2019 M1 depth** for the full ~37-symbol universe? Blocks both warmup and eurq.
4. **Is a custom-symbol pinned tester terminal acceptable** as the reproducibility substrate, and who owns the sha-pinned bar set?
5. **carry_breakout:** port faithfully (worst effort-to-weight, hourly Donchian on 11 symbols) or take an approved small approximation? Weight 0.046 makes approximation tempting.
6. **Warm-start bit-parity:** can the native v34 hysteresis state at the 2020 boundary be shown bit-identical to the record's warm build? If not, the COVID tail (which dominates MaxDD) is fabricated.

---

## 12. What makes this hard / when this is the wrong choice

**What makes it hard (folding the four adversarial reviews in explicitly):**

- **The "green half" is not green where it counts** (`reliability-maintainability`). V7Core is G1-proven as a tracker of the **real** account; `a_h` is brand-new MQL5 (idealized fill ledger + new worst-mark accumulator + a re-split trigger that must now fire on *idealized* book equity). Only the signal math is reused, not the account that produces `a_h`. The v7 equity curve is as unproven as the v34 half until P2 closes.
- **Fidelity is dataset-defined, not code-defined** (`v34-port-fidelity`). `b` = a frozen parquet built once from the frozen 1m IC feed; the native path consumes the live broker feed. A **bit-perfect** algorithm port still cannot reproduce the pin because the *bars* differ, and `b_h` reweights every hour of *both* books. Going native re-derives `b` from a different feed **by construction**.
- **The tester structurally cannot feed the record engine's inputs** (`tester-determinism-cost`). Six bid/ask fields per symbol-minute are needed; MT5 stores bid OHLC + one spread int. The short worst-mark and fills-across-spread diverge exactly in the crisis tail the campaign cares about. RECON4 already shows the *easier* hybrid drifts to 0.66×; native adds error on top.
- **The system cannot certify its own correctness** (`reliability-maintainability`). The only oracle is the daily warm Python batch. The "all-MQL5" system is permanently subordinate to the Python pipeline it meant to replace — two implementations that must agree forever, the harder one untested.
- **Wrong-but-consistent corruption is undetectable** — three mutable worst-mark accounts in one `.ex5` address space over ~3M minutes as global arrays, no MQL5 memory isolation, no in-language tests (the only test asset is a Python *mirror* that a faithfully-copied bug passes). A single index/aliasing slip silently mis-weights `a_h`/`b_h` and mis-sizes all 33 live legs while passing the `<1e-12` self-check.

**When this is the wrong choice:**

- **If the deliverable is "reproduce the record numbers,"** this is the wrong tool — the tester runs the broker feed and will not reproduce EUR 3,872,872; keep the six-field Python engine as the engine of record.
- **If MaxDD / crisis-tail certification is the goal**, do it on the six-field Python engine + real-tick, not the 1m-OHLC tester (ask fabrication mis-marks the tail).
- **If the v34 alpha is still being tuned**, do not port — dual-language re-verification debt swamps any win.
- **If the honest steady state (v7-native + v34-Python-bridge) is unacceptable** — because it is *still a Python→file hybrid for half the book*, the exact fragility Option 1 set out to delete, relocated rather than removed — then Option 1 does not deliver its headline and the hybrid `FORWARD_GENERATOR` is the better path.

**When this IS the right choice:** as a **tester-only, position-level v7 cross-check** that runs dynamically with no CSV for the v7 sizing path, validating the mechanical spine cheaply, while the CSV/forward-generator stays the live path of record. That win is real, low-risk, and genuinely superior to the hybrid *in the tester* — it deletes the CSV append pipeline, the D1/D2 causal-append race, the FedReplay tail-reader, and the multi-process `lock_v5` landmine, and it sidesteps the hybrid's single hardest blocker (the no-resume v7 extractor). Scope the deliverable to that, and treat everything past it as a contained, reversible, parity-gated follow-on — not a bet-the-option rewrite.
