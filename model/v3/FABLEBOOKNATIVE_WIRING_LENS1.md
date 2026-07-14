# FableBookNative — LENS 1: Component Wiring & Per-Bar Orchestration

**Scope.** How the already-proven components (CoreEngine `f_core`, the 8 Sat sleeves +
Ensemble `f_sat`, CoreSim `a`, SatEquityNative `b`, BookBlend, BookExec) are wired into
one live-computing EA that each bar reproduces the frozen `book_frac[33]` stream the
current `FableBook.mq5` replays. This is a READ of the actual APIs + the validated
orchestration (`research/bpure/mql5/harness_sim.py`, MEASURED 4.197e-14 vs golden book).
It specifies the glue; it does not build MQL5.

Every API quoted below was read from the file cited. Facts are labelled **[VERIFIED]**
(read in source) or **[INFER]** (deduced) or **[RISK]** (open, honest).

---

## 0. The three clocks (the load-bearing structural fact)

The book is computed on **three distinct grids**, and the whole wiring problem is keeping
them coherent:

| Clock | Components | Cadence | Carries between bars |
|---|---|---|---|
| **H1 signal grid** | CoreEngine→`f_core[8]`; 8 sleeves+Ensemble→`f_sat[31]` | one row per hourly union bar | large per-sleeve indicator state |
| **M1 equity grid** | CoreSim→`a` (combined eqc); SatEquityNative→`b` (eq_c) | one step per minute | account balance / lots / entry |
| **Blend + execution** | BookBlend→`book_frac[33]`; BookExec (`FED_Reconcile`) | blend at H1 boundary; **re-size every M1** off `ACCOUNT_BALANCE` | `g_fedTgt[33]`, held positions |

The model of record (`model/v3/reproduce.py::static_blend`, **[VERIFIED]**) is HOURLY:

```
hours = core_frac.index.union(sat_frac.index)          # the H1 union grid
a_h = a.reindex(...).ffill().reindex(hours).fillna(1.0) # 1m eqc sampled asof each hour
b_h = b.reindex(...).ffill().reindex(hours).fillna(1.0) # 1m eq_c sampled asof each hour
j        = w*a_h + (1-w)*b_h
fed[h,k] = f_core*(w*a_h/j) + f_sat*((1-w)*b_h/j)      # w=0.70
```

So `a`,`b` are 1-minute equity curves **sampled asof the hour boundary** (last value ≤ h),
each **normalised by its own first 1m value** (`core_eq/core_eq.iloc[0]`,
`sat_eq/sat_eq.iloc[0]` — **[VERIFIED]** reproduce.py L55–57; NOT by the 10000 seed).

**Key simplification [INFER, load-bearing]:** the blend consumes only `a_h`=**eqc** and
`b_h`=**eq_c**. It never uses CoreSim's `eqw`/`margin` nor SatEquityNative's `eq_w`. Those
worst-marks matter only to each engine's *internal* stop-out (CoreSim noliq guard = 1e-9,
structurally never fires; SatEquityNative 0.50 stop-out, in-sample never fires — EA_V3
§7). The live book therefore needs, per hour, one scalar from each equity engine.

---

## 1. Component APIs (quoted) and what each needs from the others

### 1.1 CoreEngine → `f_core[8]` (H1) — **[VERIFIED, RISK]**
`Core/CoreEngine.mqh` is the **verbatim v7 executing EA body** (FableFederation_V1),
not a pure signal function. It owns a file-scope `CTrade trade;` (L68), globals
`W[N_SLEEVE]`, `g_slSym[]`, the sub-account ledger (`g_seed[]`,`g_realized[]`), and the
band/harvest/quarter-rebalance logic that *sends orders*. The per-leg raw multiple is
`CurrentTarget(int sleeve,int hour,int dow)` (L411), but `f_core` (the model
`v7_book_frac_1h`, "band-book hourly frac-of-own-equity, 8 legs") is the leg's held
fraction *after* equal-capital weighting `W[n]` and the daily band re-split — produced
inside `QuarterRebalance`/`ExecSleeve`, entangled with `DesiredLots`+`OrderSend` (L820–870).

- **Needs:** daily/stamped signal series (its own `g_ser[]` from higher-timeframe closes);
  wall-clock hour/dow.
- **Emits (needed by book):** an 8-vector of per-leg frac-of-own-equity for the current
  hour, in the column order of `v7_book_frac_1h.parquet` (model names).
- **[RISK] Glue required:** CoreEngine must run in a **compute-only mode** that yields the
  8-vector *without* sending its own orders (the book's execution is BookExec, off the
  real account). Options in §5.

### 1.2 The 8 Sat sleeves + Ensemble → `f_sat[31]` (H1) — **[VERIFIED]**
Per-sleeve stepper APIs (all in `Include/Sat/`), each carrying heavy indicator state:

| Sleeve | Class · Step signature | Grid | Symbols |
|---|---|---|---|
| meanrev | `CSatMeanRevStepper.Step(datetime ts, closes[16], pos[16])` | hourly | 16 (`SatMR_SYMBOLS`) |
| carry_breakout | `Step(long epoch_day, closes[32], pos[32])` / `StepAt(datetime,…)` | hourly, rolls on day change | 32 emit, **21 kept** (`CB_KEPT`) |
| seasonal+crypto | `CSat…(SeasonalCrypto).StepNs(long ts_ns, xau_ret, btc_c, eth_c, sol_c, &emit_ts_ns, emit_pos[4])` | hourly, **1-bar deferred emit** | 4 (XAUUSD + BTC/ETH/SOL) |
| intraday | `CSatIntradayStepper.Step(datetime t, closes[], pos_out[])` / `StepNs` | hourly | `ID_SYMS` |
| crisis | `CSatCrisisStepper.Step(datetime ts, closes[10], SSatCrisisResult &res)` | **daily**, effective `ts+1d+13h` (`res.effective`) | 4 out (`SatCRISIS…OUT`) |
| trend_v2 | `CSatTrendV2Stepper.Step(closes[5], held_out[5])` | **daily**, effective d+1 05:00 (`EXEC_HOUR=5`) | 5 (`SatTV2_SYMS`) |
| mag | `CSatMagXauStepper.StepNs(long ts_ns, close_raw)` / `Step(datetime,…)` → scalar | hourly, day-accum | 1 (XAUUSD) |
| **shell** | `CSatEnsembleStepper`: `AddSleeve(name,syms[])`×8 → `Finalize()`; per bar `SetSleeveRow(name,pos[])`×8 → `Step(datetime t, out[])` → `out[31]` | hourly | 31 (`Symbols()` sorted union) |

- Ensemble.Step **[VERIFIED Ensemble.mqh L413]** requires **every** sleeve row staged that
  bar (`m_row_set` all true) or returns false; it is **stateless across bars** (the book
  shell has no memory). Its `out[]` is in `Symbols()` order = `f_sat`.
- **Needs:** the sleeve rows. crisis & trend_v2 are DAILY → their rows are ffilled onto the
  hourly grid via pending queues (below). seasonal/crypto is emitted **one bar late**.

### 1.3 CoreSim → `a` (M1 combined eqc) — **[VERIFIED, RISK]**
`Core/CoreSim.mqh`. `CCoreBookSim`: `SetSlots(7)`; `AddLeg(...)`×9; then **segment batch**:
```
BeginSegment(seed);                 // legcap = seed*W/slot_legs per leg
for each leg (BOOK order): for each in-window native bar: StepLegBar(leg, ts, OHLCx2, eurq, swap…, tgt);
FinishSegment();                    // union-grid ffill combine -> EqC[i]/EqW[i]/Mg[i]
seed_next = FinalEqC();             // frozen band-trigger seed chain
```
- **[RISK] This is a segment-batch, leg-major, seed-chained replay engine, not a streaming
  stepper.** `FinishSegment()` rebuilds the whole union from the captured per-leg arrays;
  the seed chain re-seeds legcaps at **frozen band-trigger dates** the *test harness reads
  from segment files* (`FMA3_coresim_segments.csv`) — the v3 replay design explicitly
  **discarded** live band-trigger detection. Advancing `a` live requires new glue (§5).
- **Needs, per leg per minute:** 1m bid/ask OHLC of the leg's symbol, `eurq`, swap fields,
  and `tgt` = that leg's frac-of-own-equity target (== the Core signal for that leg).
- **[INFER] tgt provenance:** CoreSim's per-leg `tgt` is the same per-leg Core target the
  book's `f_core` derives from — i.e. CoreEngine and CoreSim share the Core signal. The 9
  CoreSim legs (`TestCoreSim` LEG TABLE: XAU, USDJPY, ETH, EURGBP, USTEC, S6×3, BTC) net to
  the 8 `f_core` columns. Pinning the exact leg-`tgt` ↔ `f_core`-column identity is a
  build-input dependency (LENS-2 concern), flagged.

### 1.4 SatEquityNative → `b` (M1 eq_c) — **[VERIFIED]**
`Sat/SatEquityNative.mqh`. `CSatEquityNative.Step(tgt[31], has_bar[31], bid_o/ask_o,
bid_c/ask_c, bid_l/ask_h, eurq[31], swap_l/swap_s[31], &eq_c, &eq_w)` — **one 1m union bar,
all 31 symbols together**, carrying `m_balance`/`m_lots[31]`/`m_entry[31]`. This IS a clean
streaming stepper: call once per minute, read `eq_c`. **No segment/seed problem for `b`.**
- **Needs, per minute:** `tgt` = `f_sat` (the current hour's Satellite book fraction,
  held/ffilled across the minutes of the hour), plus 1m OHLC/eurq/swap for the 31 symbols.

### 1.5 BookBlend → `book_frac[33]` (H1) — **[VERIFIED]**
`Book/BookBlend.mqh`. `Init(w=0.70, core_syms[8], sat_syms[31])` builds the netted sorted
union (`NetCount()==33`, `NetSymbol(k)` model names, `CoreIndexOf`/`SatIndexOf` maps).
Per hour: `Step(f_core[8], f_sat[31], a_h, b_h, out[])` → `out[33]` in `NetSymbol()` order:
```
j=w*a+ (1-w)*b;  cc=w*a/j;  cs=(1-w)*b/j;  out[k]=fc*cc + fs*cs;   // op order is LAW
```
- **Needs from the SAME hour:** `f_core[8]` (Core-leg order given at Init), `f_sat[31]`
  (`shell.Symbols()` order), `a_h`, `b_h`. **s is NOT applied here** — it is BookExec's dial.

### 1.6 BookExec (`FED_Reconcile`) — the execution consumer — **[VERIFIED]**
`Book/BookExec.mqh` sizes off `ACCOUNT_BALANCE`, consuming globals from `BookReplay.mqh`:
`g_fedTgt[33]` (net_frac per symbol, canonical/broker order `g_fedCanon[]`),
`g_fedTrade[33]`, `g_fedLev[33]`, `FED_NSYM=33`. Today `FED_ApplyHour(hourEpoch)`
(BookReplay L211) fills `g_fedTgt[]` from the frozen CSV cursor. **The native EA replaces
`FED_ApplyHour` with a live blend that writes the identical `g_fedTgt[33]` vector.**
Everything downstream of `g_fedTgt` (margin cap, rebalance band, volume-limit cap, split,
FTMO breaker) is unchanged and already RECON-4-proven.

---

## 2. The per-bar orchestration (the schema the build follows)

Attach to an M1 24/7 clock chart (as `FableBook.mq5` L21). `OnTick`:

### 2.1 On every new **M1** bar (advance the two equity clocks)
```
1. Build the M1 union row for the 31 Sat symbols (bid/ask OHLC, eurq, swaps, has_bar).
2. b_engine.Step(f_sat_held[31], …M1 row…, eq_c_b, eq_w_b);   // f_sat_held = current hour's f_sat, ffilled
      b_curr = eq_c_b        (normalise later: b_h = b_curr / b_first)
3. Build the M1 rows for the 9 Core legs (per-leg OHLC, eurq, swap, tgt = current hour's per-leg Core target).
4. For each leg: core_book.StepLegBar(leg, …);               // [RISK §5] streaming wrapper
      a_curr = <combined eqc of the Core book up to this minute>   // needs incremental combine, §5
5. (Capture a_first / b_first on the very first M1 bar for the iloc[0] normalisation.)
6. FED_Reconcile();   // re-size every M1 off ACCOUNT_BALANCE, using g_fedTgt from the last H1 blend
```
`f_sat_held` and the per-leg Core `tgt` are the **prior** H1 boundary's outputs, held
constant across the hour (ffill) — exactly the model's asof semantics.

### 2.2 On every new **H1** bar (recompute the signal + blend for the just-closed hour h)
Mirrors `harness_sim.py::main` loop, statement-for-statement (**[VERIFIED]** that loop =
golden to 4.197e-14). Let `ts` = closed-hour bar-open epoch (`iTime(H1,1)`, as FableBook L171):
```
A. Update ffill[37] raw-close union for the 37-sym Sat input universe (IN_SYMS).
B. Daily rollover (server day change):
     - trend_cur pending:  held5 = trend_v2.Step(ffill[tv_ix]);  queue (cur_day+1)*86400 + 5*3600 -> held5
     - crisis pending (weekday gate (cur_day+3)%7 < 5):
                          crisis.Step(cur_day 00:00, ffill[cr_in_ix]) -> res;  queue res.effective -> res.w[4]
C. xau_ret = clip(ffill[XAU]/prev_ffill[XAU] - 1, ±0.30)   // prev = value BEFORE this bar's ffill
D. Activate pending targets whose eff <= ts: trend_cur<-queue, crisis_cur<-queue (NaN keeps prev)
E. Current-bar rows for the 7 non-deferred sleeves:
     mag.StepNs, intraday.StepNs, meanrev.Step, carry_breakout.Step(epoch_day)->pick CB_KEPT[21],
     trend_v2 row = trend_cur[5], crisis row = crisis_cur[4] (NaN->0.0)
F. seasonal/crypto: sc.StepNs(ts_ns,xret,btc,eth,sol,&emit_ts,&emit_pos) -> DEFERRED:
     emits the PREVIOUS bar's seasonal+crypto row (emit_ts == prev_ts).
G. If emitted: shell.SetSleeveRow(all 8, using the 7 SAVED prev-bar rows + emit seasonal/crypto);
     shell.Step(prev_ts, f_sat[31])                     // f_sat for hour (prev_ts)
     -> this is the just-closed hour's Satellite book.
H. f_core[8] = CoreEngine compute-only 8-vector for hour (prev_ts)          // §5
I. Sample a_h = a_curr / a_first ; b_h = b_curr / b_first   (asof this boundary)
J. BookBlend.Step(f_core, f_sat, a_h, b_h, out[33])
K. Transcribe out[33] (NetSymbol model names) -> g_fedTgt[33] (g_fedCanon broker names)
     via the DAX->DE40 / USA500->US500 remap; g_fedTgtDirty=true.
L. FED_Reconcile()  (also runs every M1 per 2.1).
```

**One-hour emission lag is intentional and self-consistent** (**[VERIFIED]** harness):
`f_sat[h]` is only produced when bar `h+1` arrives (SeasonalCrypto deferred emit). The
book already applies hour `h` at the `h+1` boundary (FableBook causal lag), so the blend
for hour `h` is computed and applied at `h+1` — the timings coincide. Save `prev_rows`
(the 7 sleeve rows), `prev_ts`, and `f_core`/`a_h`/`b_h` sampled at the same boundary.

---

## 3. Data-dependency graph (who needs whom, same bar vs prior bar)

```
M1 row(31 Sat) ─┬─► SatEquityNative.Step ─► b_curr ──┐  (asof h)
                │            ▲ tgt = f_sat_held (prior H1, ffilled)   │
M1 rows(9 Core)─┴─► CoreSim.StepLegBar ─► a_curr ─────┤  (asof h)     │
                             ▲ tgt = per-leg Core target (prior H1)   │
                                                                      ▼
H1: ffill[37] ─► {7 hourly sleeves + trend/crisis daily queues}       │
                     └─► Ensemble.Step ─► f_sat[31] (hour h, emitted at h+1)
H1: CoreEngine compute-only ─► f_core[8] (hour h)                     │
                                                                      ▼
   BookBlend.Step(f_core, f_sat, a_h=a_curr/a_first, b_h=b_curr/b_first) ─► book_frac[33]
                                                                      ▼
   remap model→broker names ─► g_fedTgt[33] ─► FED_Reconcile (sizes off ACCOUNT_BALANCE, every M1)
```

- **Same-hour coupling:** BookBlend needs `f_core[h]`, `f_sat[h]`, `a_h`, `b_h` all at the
  same boundary. **[VERIFIED reproduce.py]** — no lag between them in the model.
- **Prior-bar coupling:** SatEquityNative's `tgt` and each CoreSim leg's `tgt` are the
  **held** (ffilled) targets from the last H1 blend/signal, applied across the hour's
  minutes. `f_sat` itself is one-bar-lagged in emission (SeasonalCrypto), handled by the
  `prev_rows`/`prev_ts` save.
- **Independence:** the 8 sleeves are mutually independent per bar; they only meet in the
  Ensemble. CoreSim and SatEquityNative are independent of each other and of the sleeves;
  they consume held targets, not live signal.

---

## 4. State each component carries between bars (the glue owner's inventory)

The top-level `FableBookNative` must own one instance of each and their state:

| Instance | Persistent state (the carry) |
|---|---|
| `CSatMeanRevStepper` | ring buffers, ewm, pending FIFO, `cur_day` |
| `CSatCarryBreakoutStepper` | `m_c_ff[32]`, vol/atr ewm, donchian windows, dc_hist, `cur_day` |
| `CSat…SeasonalCrypto` | seasonal ewm(720), crypto day-accum, effective queue, **deferred prev row/ts** |
| `CSatIntradayStepper` | per-sym intraday state, `cur_day` |
| `CSatCrisisStepper` | prev closes, vol rings, ewm, `n_steps` |
| `CSatTrendV2Stepper` | per-sym hist rings, ewm, last target/moved |
| `CSatMagXauStepper` | `m_mids[]`, day accum, pending FIFO, `current` |
| `CSatEnsembleStepper` | config only (**stateless across bars**); per-bar staging cleared each Step |
| `CSatEquityNative` (b) | `m_balance`, `m_lots[31]`, `m_entry[31]`, `m_n_trades` |
| `CCoreBookSim` (a) | per-leg sub-account balance/pos/entry + captured series; segment seed |
| CoreEngine (f_core) | its full v7 ledger (`g_seed[]`,`g_realized[]`, quarter/band state) |
| top-level glue | `ffill[37]`, `has_day/cur_day`, `tvq`/`crq` pending queues, `trend_cur[5]`, `crisis_cur[4]`, `prev_rows`(7 sleeves), `prev_ts`, `f_sat_held[31]`, per-leg Core `tgt_held`, `a_first`/`b_first`, `g_fedTgt[33]` |

All Sat steppers and `b` expose `GetState`/`SetState` (JSON/string) for warm restart —
**[VERIFIED]** — so a live restart can rehydrate; the top-level queues/ffill/prev must be
serialized too (new glue).

---

## 5. Glue code that must be written (the un-golden work)

1. **`FableBookNative.mqh` top-level orchestrator** — owns all instances + the §4 glue
   state; runs §2.1 each M1 and §2.2 each H1; writes `g_fedTgt[33]`. Replaces
   `FED_ApplyHour`; keeps all of BookExec/Guardian/BookConvert intact.

2. **CoreEngine compute-only extraction [RISK].** CoreEngine.mqh is a full executing EA
   body with its own `CTrade trade;`, `MidOf`, `EurPerQuote`, `g_nSplit`, ledger, and
   order-sending rebalance. It **cannot be `#include`d beside BookExec.mqh** without symbol
   collisions (both declare `CTrade trade;` at file scope, plus name clashes). Two honest
   options:
   - (a) **Refactor CoreEngine to a signal class** exposing `f_core[8]` for a given
     (hour,dow,series) with NO order sends and NO `trade` object — the clean path, larger
     surface, must re-prove G1 equivalence.
   - (b) **Reuse CoreSim as the Core signal+equity source together** if the per-leg `tgt`
     that CoreSim already consumes IS the `f_core` the blend needs (net the 9 legs → 8
     columns). Then `f_core` and `a` come from one engine and CoreEngine.mqh is not
     included at all. **[INFER]** this is likely the intended v3 path (CoreSim is "the a_h
     engine" and already carries the per-leg targets) — must be confirmed against
     `v7_book_frac_1h.parquet` column identity in LENS-2. **Preferred if it holds.**

3. **CoreSim live-streaming wrapper [RISK].** Add to `CCoreBookSim` (or wrap) the ability
   to: (i) interleave `StepLegBar` time-major (one minute across all 9 legs) — the class
   permits this (each leg only needs time-ascending order within itself); (ii) expose
   **incremental combined eqc** at the current minute WITHOUT the O(all-bars)
   `FinishSegment` rebuild — a running per-leg-ffill + flat sum; (iii) detect the **frozen
   band-trigger dates live** and `BeginSegment` (re-seed legcaps from combined eqc). The
   trigger date list is frozen (CORESIM_SPEC) and must be embedded. Only **eqc** is needed
   (§0), which removes eqw/margin/union-worst bookkeeping from the hot path.

4. **M1 multi-symbol feed assembler.** Build synchronized per-minute union rows for 31 Sat
   symbols and 9 Core legs (bid/ask OHLC via `CopyRates`, `eurq` via BookConvert/`FED_Eurq`,
   swaps, `has_bar` = did the symbol print this minute). This is the single largest
   correctness surface for the live residual (missing-bar ffill must match the golden
   union-grid semantics).

5. **H1 ffill[37] + daily-queue driver.** Direct port of `harness_sim.py` L129–203 into the
   H1 branch (the algorithm is MEASURED-equivalent to golden). Includes the SeasonalCrypto
   one-bar deferral bookkeeping and the trend/crisis pending queues.

6. **model→broker name remap** at book_frac→`g_fedTgt` transcription (DAX→DE40,
   USA500→US500; rest identity), replacing the exporter's emit-time remap.

---

## 6. Honest open questions / risks (not build-blockers, must be resolved in LENS-2/3)

- **[RISK-A] CoreSim as a streaming online engine.** Built + validated as a segment-batch
  replay (leg-major CSV, frozen segment files, seed chain). Live per-minute streaming with
  live band-trigger re-seed is genuinely new code; the tolerance band (ΔCAGR≤±1.0pp etc.)
  must be re-measured after the wrapper exists. If the incremental-combine residual is
  material, fall back to a **coarser but faithful** scheme (re-`FinishSegment` at each H1
  boundary over the current segment's buffered minutes — correct but heavier).
- **[RISK-B] `f_core` source.** Whether the 8-vector comes from a refactored compute-only
  CoreEngine (option 2a) or from CoreSim's own per-leg targets netted to 8 (option 2b) is
  unresolved and gates the include graph. Confirm leg↔column identity against
  `v7_book_frac_1h.parquet`.
- **[RISK-C] MT5 multi-symbol bar synchronisation.** The tester's behavior feeding 31+9
  non-chart symbols' M1 bars in lockstep with the clock chart is **uncertain** — if a
  symbol's M1 bar is not yet available at the clock tick, `has_bar=false`/ffill must
  reproduce the golden union grid exactly. This is the classic multi-symbol-tester
  hazard; validate on the 1m-OHLC smoke before trusting real-tick (per campaign protocol).
- **[RISK-D] Normalisation anchor.** `a_h`,`b_h` divide by the **first 1m equity value**
  (`iloc[0]`), not the 10000 seed. The EA must capture `a_first`/`b_first` on the first
  processed minute of the model span, else the blend is off by a constant factor.
- **[RISK-E] Grid alignment.** The model `hours` grid is `core_frac.index ∪ sat_frac.index`;
  the live H1 bars must coincide with those epochs (same server-tz concern
  `FED_ApplyHour` already guards with its hit counter). An all-flat/absent hour must
  reproduce keep-last-good vs flatten-by-omission semantics.

---

## 7. One-line summary of the wiring

> Each M1: advance `b`=SatEquityNative and `a`=CoreSim on synchronized 1m union rows using
> the held prior-hour targets. Each H1 (for the just-closed hour, applied at the next open):
> drive the `harness_sim` ffill/daily-queue loop → 8 sleeve rows → `Ensemble.Step`=`f_sat[31]`;
> get `f_core[8]` (from CoreSim's netted leg targets, pending LENS-2 confirmation);
> sample `a_h=a/ a_first`, `b_h=b/b_first`; `BookBlend.Step`→`book_frac[33]`; remap
> model→broker names into `g_fedTgt[33]`; `FED_Reconcile` sizes it off `ACCOUNT_BALANCE`
> every M1. The only genuinely new code is the CoreSim streaming wrapper, the `f_core`
> source decision, and the M1 multi-symbol feed assembler.
