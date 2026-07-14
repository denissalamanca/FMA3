# FableFederation_V3 — FORWARD GENERATOR spec (make the frozen replay live)

**Status:** DESIGN, not built. Companion to [`EA_V3_DESIGN.md`](EA_V3_DESIGN.md) (the executor) and [`MODEL_SPEC.md`](MODEL_SPEC.md) (the model). This spec covers the *producer* that keeps the replay stream one hour ahead of the clock so the EA can run a live demo indefinitely.

---

## 1. Goal + the exact problem

v3 does not compute the model live — it **replays** a frozen, precomputed `fed_frac` stream and sizes off it (`EA_V3_DESIGN.md` §2). The stream is `research/outputs/mt5/FMA3_fed_frac_v3.csv`:

```
header : w_v7=0.7,config_hash=51a7541cc2aaa593,fmt=3
last   : 1767222000,XBRUSD,-0.016960832655   # epoch = 2025-12-31 23:00:00 server
```

The file ends at server hour **2025-12-31 23:00** (epoch `1767222000`). On a live demo past that instant the EA's cursor (`FedReplay.mqh:213` `FED_ApplyHour`) walks off the end: `g_fedRepCursor >= g_fedRepRows`, every subsequent hour is treated as *absent* → **keep-last-good** (`FedReplay.mqh:215-219`), and v3 **holds the 2025-12-31 23:00 positions forever**. Stale targets, indefinitely. That is the failure this generator fixes.

**Why we can't just "compute the model in the EA."** The blend weights `w·a_h/j` and `(1−w)·b_h/j` (`reproduce.py:60-74`) use `a_h,b_h` = each parent book's **native standalone** equity multiple — the Core band-book run alone at its own €10k seed, and the Satellite book run alone at its own €10k seed. A live, s-levered, friction-carrying, jointly-margined trading account **cannot reconstruct** those two curves from its own equity (`MODEL_SPEC.md` §1; `EA_V3_DESIGN.md` §2). Hence: replay, and a *separate* producer that tracks the two native curves as shadows.

**The forward generator** = a persistent Python service that, once per closed hour `h`, recomputes `fed[h,·] = static_fed(0.70)[h,·]` from live data and **appends** the fmt=3 rows for hour `h` to the CSV, so the EA always finds the current hour.

---

## 2. Architecture (prose diagram)

```
                      LIVE 1m BID/ASK FEED  (broker, all parent-book symbols + EUR crosses)
                                   │
              ┌────────────────────┴─────────────────────┐
              ▼                                            ▼
   ┌─────────────────────┐                     ┌──────────────────────┐
   │  V7 SHADOW (proc A)  │  lock_v5 poisons    │  V34 SHADOW (proc B)  │
   │  band-book run ALONE │  stop_out=1e-9  ✗   │  v3.4 book run ALONE  │
   │  → f7[h] (8 legs)    │  ─── SEPARATE ───   │  → f34[h] (31 cols)   │
   │  → eq7 native 1m     │      PROCESSES      │  → eq34 native 1m     │
   └──────────┬───────────┘                     └───────────┬──────────┘
              │  a_h = a_last·(eq7[h]/eq7[bnd])              │  b_h = b_last·(eq34[h]/eq34[bnd])
              └──────────────────┬──────────────────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │  BLEND  static_fed(0.70)  │  j = w·a_h+(1−w)·b_h
                    │  fed[h,k]                 │  reproduce.py:60-74, byte-for-byte
                    └────────────┬─────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │  APPENDER (fmt=3)         │  build_rows()/write_csv() in APPEND mode
                    │  broker-map + EPS + 12dp  │  export_book_frac_v3.py:53-86
                    │  __GRID__ for flat hours  │  per-hour <1e-12 reparse self-check
                    │  atomic whole-hour append │  config-hash gate + epoch-ascent gate
                    └────────────┬─────────────┘
                                 ▼
              research/outputs/mt5/FMA3_fed_frac_v3.csv   (append-only, single header)
                                 │
                                 ▼
              ┌──────────────────────────────────────────┐
              │  FableFederation_V3 EA (MT5)              │
              │  FedReplay.mqh HOT-RELOAD/TAIL reader ⚠   │  ← must be BUILT (see §5.6)
              │  FED_ApplyHour(h) → size off net_frac·s   │
              └──────────────────────────────────────────┘
```

**Inputs:** (1) a live 1m **bid+ask** OHLC feed for every parent-book symbol plus the EUR crosses used by `FxConverter`; (2) persisted **parent-book state** (the two shadows' warm internal state + the splice seed) from disk. **Never reads the live MT5 account** — the shadows are account-independent by construction.

**Output:** append-only `epoch,broker_symbol,net_frac` rows under the one existing header. No header re-emit, no rewrite of prior rows.

**Consumer:** the v3 EA, *once its FedReplay is taught to tail the file* (§5.6) — today it loads the whole file once at OnInit (`FED_LoadReplay`, `FedReplay.mqh:120`) and never re-reads, so plain appends are invisible to a running EA. That reader change is a hard prerequisite, not an optimization.

---

## 3. The two sub-generators — exists vs must-build

Streamability is **split 2-and-2** (MAP gen-pipeline). One input has a live producer today; three do not.

### 3.1 Core side — `f7[h]` and `eq7[h]` (the primary blocker)

`frac7` and `eq7` are **co-products of one stateful, path-dependent batch extractor**: `engine/v7_bridge/extract_positions.py::extract()`, driven by `run_extract.py` (IC) / `run_extract_fwd.py` (Duka). It re-runs the entire NSF5 v7.0 band-book: a **triggered equal-capital re-split** (`run_generic_capture`, up=0.25, down=W7/1.75, kmult=2.5, min_gap 5d) with **seed chaining** — every committed segment is re-run exactly from the previous segment's ending equity ("no splice flattery"). The IC anchor is 32 segments / 31 band triggers.

- **Exists:** a *proven forward batch* (`run_extract_fwd.py` re-runs the whole book on an extended feed) and the bit-exact self-test-gated engine (`_run_core_pos` = verbatim NSF5 `_run_core`).
- **Does NOT exist:** any "advance one bar" step. The band re-split triggers and seed chain are **internal state, not a function of the latest bars**. `run_forward_oneshot.py::load_v7_forward_frac()` is the **one permitted `NotImplementedError`** in the codebase precisely because "v7 2026 positions CANNOT be rebuilt in-process."
- **Forward call path (Option A, reuses verified code, re-runs only the open segment)** — from MAP v7-forward: append live 1m bid+ask into `bt._BARS_CACHE[(inst,False)]` + `bt._PREP_CACHE.clear()` (pattern `v51_rig.prime_2026`); rebuild `costs.FxConverter`; `sleeves = v52_alternatives.book('BTC_REP','USTEC')`; `_run_window_pos(sleeves, cur, now, seed)` → book `eqc[now]` + held lots; `f7[now] = lots·contract·mid·eurq/eqc`; `a_h[now]=eqc[now]/10000`; then `sim.earliest_trigger(...)` to advance `(cur,seed)` on a re-split.
- **Persisted Core state between hours:** `cur` (open-segment start), `seed` (equal-capital re-split base = book equity at `cur`), last-trigger act date (min_gap guard), the `eq7[0]=10000` anchor, and the append-only `frac7/eq7` rows already emitted.
- **Interim before a resumable stepper lands:** rolling **full warm re-extraction each hour** (~10-25 min), anchor-gated against `research/baselines/nsf5/engine_reproduce.json` every cycle.

### 3.2 Satellite side — `f34[h]` (mostly solved) and `eq34[h]`/`b_h` (must build)

`f34` is a **pure causal function** of the hourly research cache with no parent internal state — `books.build_v34_frac_1h()` → FMA2 `eval_v34_pin_s10.build_c2()` (7 V2_CAPS sleeves + mag_xau@0.05, ×GLOBAL_SCALE 10, no renormalize, structural gold cap 1.80).

- **`f34[h]` EXISTS live:** the FMA2 brain `/Users/dsalamanca/vs_env/FableMultiAssets2/ea/brain/target_engine.py::build_book(rebuild=True)` already runs hourly (`run.py --once`/`--loop`), stitches live H1 exports onto the frozen research cache, and returns `net_capped` = `f34` — recipe-identical to `build_c2` (measured bit-identical to the pin at 6.66e-16). It needs *wiring* into an FMA3 service, not building. **Caveat:** the brain emits **targets only, never `b_h`**.
- **`eq34[h]`/`b_h` does NOT exist as a live producer.** Batch source is `eval_v34_pin_s10.py` main → `account_engine_1m.simulate_account_1m(build_c2(), initial=10_000)` → `research/baselines/fma2/v34_s10_pin_curve.parquet['equity']`. The engine **hardcodes `pd.period_range('2020Q1','2025Q4')`** (`account_engine_1m.py:228`) and reads a frozen cache ending 2025; the FMA3 wrapper `record_engine.py::run_record` raises `ValueError` past 2025Q4.
- **Good news:** the account kernel is deterministic and reusable **at the FMA3 wrapper boundary without editing read-only FMA2** — `account_engine_1m._run_chunk(tgt, …, balance0, lots0, entry0)` takes and returns carry-state; `_densify/_eurq_chunk/_swap_chunk` are importable. A new forward driver seeds from the 2025-12-31 end-state and steps `_run_chunk` over each new hour's minutes.

### 3.3 Summary table

| input | today | forward path | build effort |
|---|---|---|---|
| `f34[h]` | **live** (FMA2 brain) | wire brain into FMA3 service | wiring only |
| `eq34`→`b_h` | batch only | **new** shadow-account driver over `_run_chunk` | medium |
| `f7[h]` | batch only | Option A re-sim open segment (interim: full re-extract) | high |
| `eq7`→`a_h` | batch only | co-product of the Core re-sim | (with f7) |

---

## 4. Native-equity shadow tracking (the subtle core)

This is the whole reason the service exists. `a_h,b_h` weight **every emitted `net_frac`**, and neither can be read off the live account.

### 4.1 Two account-independent shadows

Run **two standalone shadow accounts**, each decoupled from the real (s-levered, margin-capped, joint-stop-out, friction-carrying) trading account:

- **Core shadow** = the NSF5 band book run ALONE, emitting its own native `eqc` 1m curve (exactly what `extract()` writes to `v7_book_equity_1m.parquet['eqc']`). `a_h = eqc[h]/eqc[0]`.
- **Satellite shadow** = the Satellite frac matrix run ALONE through the standalone 1m account, emitting its own native equity. `b_h = eq34[h]/eq34[0]`.

**"Frictionless" is loose (per MAP v34-forward).** Each standalone curve still charges its **own book-level** spread/commission/swap/margin-shrink/stop-out — it is free only of the *blend's joint* frictions. Do **not** implement a cost-free ideal; that would break reconciliation against the frozen curves.

### 4.2 Seed from the frozen curves' LAST values — chain the ratio, never re-base

Both frozen curves share the 2020 base `eq[0]=10000`. At the frozen boundary hour (2025-12-31 23:00) sample `a_last, b_last` **from `static_fed`'s own asof convention** (§5.3). Forward, **chain each shadow onto its frozen last multiple:**

```
a_h = a_last · (eq7_shadow[h] / eq7_shadow[boundary])
b_h = b_last · (eq34_shadow[h] / eq34_shadow[boundary])
```

**Why chaining and not re-basing to 1.0 (as the one-shot holdout did):** the blend weights `w·a/j` and `(1−w)·b/j` are invariant to a **common** rescale of `(a,b)` but **not** to *independent* re-basing. Re-basing `a` and `b` by different constants changes the `a/b` ratio → changes the weights → changes `fed[h,k]` → a discontinuity in `j` at the splice. Persist a sidecar splice-seed:

```json
{ "a_last": …, "b_last": …, "boundary_stamp": "2025-12-31T23:00:00",
  "eq7_base": 10000, "eq34_base": 10000 }
```

recomputed from `static_fed` at the boundary. If this artifact is lost or re-derived by re-basing, every forward weight is silently wrong **while the file still passes its own <1e-12 self-check** — only the warm batch reconcile (§6) catches it. This is the single most dangerous failure surface in the design.

### 4.3 Warm state is mandatory

Cold-starting a book **skips indicator warmup and fabricates crisis behavior** (memory: record-engine-COVID-warmup; the k≈4.7 artifact). The frozen `a,b` were built warm from 2020. Therefore:

- **Safe baseline:** re-run each book **warm over [2020-01-01, now]** every hour and take the tail. Core extract ~10-25 min; Satellite build ~2-5 min. Heavy but correct.
- **Optimization (Phase 4, gated):** persist each book's internal state and advance one hour — admissible **only** after it is proven **bit-identical** to the warm re-run over an overlap window.

### 4.4 Process isolation (landmine)

Any Core extraction `import sim` sets `lock_v5` `ACCOUNT['stop_out_level']=1e-9`; a record-engine (Satellite) run asserts `stop_out==0.5`. **The two shadows CANNOT share one Python process.** Run proc-A (Core) and proc-B (Satellite) separately; the blend runs in a third (or in whichever consumes their on-disk outputs).

---

## 5. Append / seam protocol

### 5.1 Append contract

- The file carries **exactly one** header (`w_v7=0.7,config_hash=51a7541cc2aaa593,fmt=3`). The generator **never re-emits it** — append data rows only, in `open('a')` mode.
- Reuse `export_book_frac_v3.py::build_rows()` (`:53`) and `write_csv()` (`:78`) **verbatim** in an append variant so the byte format is identical: per symbol `k` with `|fed[h,k]|>EPS(1e-12)` a row `epoch,broker_symbol,net_frac` at `DECIMALS=12` fixed places, broker-mapped via `SYMMAP` (`USA500→US500`, `DAX→DE40`, `:36`).
- **All-flat hour** → a single `epoch,__GRID__,0` sentinel (`:83-84`). Semantics: **present-but-flat ⇒ EA flattens; genuinely absent ⇒ EA keep-last-good** — the distinction is load-bearing (§7).
- `epoch` = the **H1 bar-open server epoch** of hour `h`, and **strictly greater** than the file's current last epoch. First forward append = `1767225600` (= last `1767222000` + 3600 = 2026-01-01 00:00:00). The EA's reparse asserts non-descending ts (`export_book_frac_v3.py:105`; EA `FedReplay.mqh:213`).

### 5.2 Causal delay — when is row `h` computable, and by when must it land

The row **stamped** `h` (hour-open `h:00`) needs data through `h:59` (hour fully closed) plus the equity mark at `h:00` → computable only **after `h+1:00:00` server**, plus a feed-settle delta (~30s-3min).

Two deadlines (MAP seam-and-native-equity):
- **D1 (fidelity, zero-drift):** the EA applies hour `h` on its first M1 tick after `h+1:00:00`. On a 24/7 crypto chart that is *seconds* — a from-scratch recompute **cannot win D1**; some intra-hour lag is irreducible.
- **D2 (correctness, no-skip):** the EA advances its cursor to hour `h+1` at `h+2:00:00`, so row `h` **must** land before `h+2:00:00` or it is never applied (stale-hold).

**Safe operating point:** append row `h` within `Δ_gen` of `h+1:00:00`, target `Δ_gen ≤ 2-3 min`, alarm > 10 min, hard-stop well before `h+1:45`. Row `h` then governs `[h+1:00+Δ_gen, h+2:00)`; only the first `Δ_gen` minutes execute the prior hour (keep-last-good) — a small, **measured** reconciliation deviation. **Do NOT** close the race by adding a second causal hour (execute `h` at `h+2`): that changes the model's 1-hour causal convention and breaks reconciliation with the frozen batch semantics.

### 5.3 Epoch-grid + asof alignment

Replicate `static_fed` semantics exactly (`reproduce.py:65-74`): `cols = sorted(set(f7.cols)|set(f34.cols))`; `f7/f34` reindexed to the hour and `fillna(0.0)`; **`a_h,b_h` reindexed to the H1-OPEN hour stamp with ffill (causal asof) and `fillna(1.0)`**.

**Reconciliation-critical asof detail (confirmed empirically):** `a_h,b_h` are sampled at the hour **OPEN** (`h:00:00`), NOT hour close. At the frozen last hour 23:00 the open-sampled `a_h=53.0979`, while the 23:59 1m mark is 53.2230. Sampling equity at `h:59` instead of `h:00` silently breaks the <1e-12 reconciliation. So: **weighting curves sampled at `h:00`, fractions at ~`h:59`** — both ≤ execution time `h+1:00`, so the construction is causal.

### 5.4 Config-hash gate (before every append)

The appended rows live under the single header hash, so they must come from the **same** model config. Run the identical gate as export/reproduce (`export_book_frac_v3.py:121-123`, `reproduce.py:112-114`): subprocess `strategy_fma3.py`, assert `'51a7541cc2aaa593' in output` AND `reproduce.CONFIG_HASH == that` AND `W_V7 == 0.70`; **additionally** assert the on-disk file's header hash == `51a7541c` **before** appending. Any drift → **hard-refuse the append** (a mixed-hash file is a poisoned stream). Also pin the pipeline *code* (extractor recipe, `build_c2` delegation, `static_fed`) so construction cannot silently fork. **Caveat:** config_hash pins the **model, not the feed** — forward uses different (live/broker) data, so hash-equality is necessary but **not sufficient** for number-equality; reconciliation (§6) proves the rest.

### 5.5 Atomicity + strict ascent

Append the whole hour's rows in **one write ending in a newline** (never a partial line the EA could parse mid-tick). Prefer write-to-temp + atomic rename, or OS append with flush. Enforce `epoch > last_epoch_in_file`. Emit the epoch from the **broker's H1 bar-open convention** (matching the EA's `iTime(H1,1)`), not a naive UTC→server formula — the Duka landmine (TRUE-UTC → NY+7h with fall-back-fold dedup, `run_forward_oneshot_native.to_server_index`) shows tz drift makes the EA keep-last-good forever and trips its `SERVER-TZ MISMATCH` guard after 24 zero-hit misses (`FedReplay.mqh:224`).

### 5.6 EA consumption change (required — else the generator is inert)

`FED_LoadReplay()` loads the entire file into in-memory arrays **once** at OnInit (`FedReplay.mqh:120-125`); `FED_ApplyHour()` reads those arrays and never re-reads the file. A running EA therefore **cannot see appended rows.** The generator MUST be paired with a **FedReplay hot-reload/tail-reader**: on each H1 boundary (before `FED_ApplyHour`) re-open the file, seek past the last-loaded epoch/byte-offset, parse only **complete** new rows, extend the arrays — with the same strict validation (unknown symbol / non-ascending ts / malformed → **reject the new rows, keep prior state**, never corrupt). Model it on the v1/v2 `V34Live.mqh` incremental pattern (mtime cheap-skip, seq/ts monotonic, keep-last-good, HOLD-on-stale, never flatten on data failure). This is a **new `.ex5` build ⇒ a fresh FMA3-RECON-N ledger entry** (RECONCILIATION.md standing clause).

---

## 6. Reconciliation + monitoring (prove a forward hour == batch)

`static_fed` is pure pandas → **forward-hour == batch-hour IFF the four inputs (`f7[h],f34[h],a_h,b_h`) match.** Prove it two ways:

1. **Per-hour intrinsic self-check** (cheap, every hour): the reparse round-trip reproduces the just-written `fed[h]` to **<1e-12** — the exact gate as `export_book_frac_v3.py::reparse` (`:89-111`, `:135`). *Limitation: this cannot catch a wrong-but-consistent input* (e.g. a re-based `a_h`); it only proves the file faithfully encodes whatever was computed.
2. **Periodic warm batch reconcile** (daily): re-run the full warm batch forward pipeline over the last N hours **on the same live feed** and diff regenerated vs appended rows, require `max|net_frac| < 1e-12`. If the incremental shadow diverges beyond tolerance → **reseed the shadow from the batch and quarantine the drift window.**

Plus three targeted monitors:
- **Splice-continuity** on the first forward hour: `a_h,b_h` continuous with `a_last,b_last`; no jump in `j`.
- **EA-hit-vs-append**: watch the EA's `g_fedRepHits` / decisions CSV — appended epochs actually applied. A run of zero hits = tz drift (§5.5).
- **Missing-hour count**: alarm after N consecutive absent hours (stale-position risk the guardian/breaker must bound).

**Reconciliation caveat (feed provenance):** the frozen stream was built on the **IC dev feed**; the forward one-shot used **Duka** (~8pp CAGR divergence documented); live uses the **broker** feed. Reconciliation must compare **forward-live vs batch-recompute on the SAME live feed** — comparing against the IC batch will flag *expected feed physics* as a bug. And keep the pre-net `f7[h],f34[h]` in a sidecar: the netted stream sums the 6 shared symbols, so per-book attribution is otherwise unrecoverable for forensics.

---

## 7. Failure modes + safe degradation

Guiding rule (from `EA_V3_DESIGN.md` build-log fix #1): **never trade a bad target — keep-last-good or flatten, never guess.**

| failure | detection | safe degradation |
|---|---|---|
| **Missed/partial hour** (broker outage, session gap) | hour `h` has no settled all-symbol 1m bars | **Do NOT append a wrong row.** Leave hour ABSENT → EA keep-last-good. Alarm after N misses. Distinguish from a genuine all-flat hour (which emits `__GRID__` to flatten). |
| **Stale prices** (feed frozen) | last M1 bar age > threshold; cross-symbol staleness | Skip the append (absent hour); do not compute off stale marks. Guardian bounds prolonged keep-last-good. |
| **Parent-book desync** (shadow drifts from warm re-run) | daily warm batch reconcile > 1e-12 | Reseed the drifting shadow from the batch; quarantine + re-emit the drift window; alarm. |
| **Config-hash drift** (any model-config change) | `strategy_fma3.py` output ≠ `51a7541c`, or on-disk header ≠ hash | **Hard-refuse the append.** A mixed-hash file is poisoned. The generator stops; EA keep-last-goods on the last valid hour. |
| **Splice-seed lost / re-based** | splice-continuity check; daily warm reconcile | Refuse to start forward emission without a valid sidecar; recompute `a_last/b_last` from `static_fed` at the boundary. |
| **Look-ahead leak** (reads an `h+1` bar) | explicit causal-boundary assertion: all bars ≤ `h:59:59`, equity mark at `h:00:00` | Abort the hour; do not append. |
| **Non-ascending / malformed append** | EA reparse assert (`FedReplay.mqh:213`); generator pre-write assert | Generator refuses; if it ever slips through, EA rejects the new rows and holds prior state. |
| **tz / DST drift** | EA `g_fedRepHits`==0 for 24 bars → `SERVER-TZ MISMATCH` (`FedReplay.mqh:224`) | Fix epoch derivation to broker `iTime(H1,1)`; until then EA keep-last-goods (does not trade garbage). |
| **Generator down entirely** | append heartbeat stops; D2 (`h+2:00`) passes with no row | EA keep-last-good, then the FTMO daily breaker / guardian bounds exposure. Stale-hold is *safe-ish* but must be time-bounded by the owner's guardian policy. |

The EA's existing strictness backstops the generator: any anomaly it can see → `INIT_FAILED` at load or keep-last-good at apply. The generator's job is to **never emit an anomaly in the first place**, and to prefer *absence* (hold) over a *wrong row* (mis-trade).

---

## 8. Phased build plan (smallest first)

**Phase 0 — Replay-past-horizon shim (unblock the EA).**
Teach `FedReplay.mqh` to hot-reload/tail the file (§5.6) and rebuild the `.ex5`. Validate with a *hand-appended* synthetic hour (e.g. copy the last hour's rows at `1767225600`) → confirm the running EA picks it up, sizes off it, and rejects a deliberately malformed append. Log the new `.ex5` sha as **FMA3-RECON-N**. *Nothing downstream matters until appends are consumed.*

**Phase 1 — Single-book forward, Satellite first (the causal one).**
Stand up proc-B: wire the FMA2 brain `build_book(rebuild=True)` for `f34[h]`, and build the **`b_h` shadow-account driver** over `account_engine_1m._run_chunk` seeded from the 2025-12-31 end-state (§3.2, §4). Prove it **byte-reproduces `v34_s10_pin_curve` on the historical overlap** before trusting one forward hour. Emit Satellite-only rows to a *scratch* file (not the live CSV) and reconcile.

**Phase 2 — Core forward + full blend.**
Stand up proc-A (Core Option A re-sim, or interim full warm re-extract), emitting `f7[h]` + `a_h`. Feed both shadows into an incremental `static_fed(0.70)` (§5.3) with the ratio-preserving splice seed (§4.2). Run the config gate + per-hour <1e-12 reparse check. Emit to scratch; run the **warm batch reconcile** (§6) over a multi-day window until `max|net_frac| < 1e-12`.

**Phase 3 — Live demo append.**
Point the appender at the real `FMA3_fed_frac_v3.csv` in `open('a')` mode with atomic whole-hour writes, broker-convention epochs, and the D1/D2 timing schedule (§5.2). Enable all monitors (§6). Extend the two expiring tables first: `v5_sleeves._OPEX_WK` (precomputed only to 2026-02-20) and `costs.POLICY_RATES` (USD to 2025-12-11 / JPY to 2025-01-24) — otherwise the Core S6 sleeve goes silently flat and swaps/carry freeze. Record **FMA3-RECON-N** with the first live forward hours logged as *forward evidence*, not silently trusted.

**Phase 4 — Optimization (gated, optional).**
Replace the hourly warm re-run with a persistent incremental shadow (Core resumable stepper; Satellite carried `_run_chunk`) **only after** proving bit-identity to the warm re-run over an overlap. Do NOT double the causal lag to win the append race.

---

## 9. Open questions for the owner

1. **USTEC vs USA500 pricing.** The frozen stream trades USTEC (IC server-time); the Duka/forward path proxied it with USA500 (corr 0.89). Which does the *live* generator price, and does the broker even quote USTEC? A mismatch is a permanent per-hour divergence, not noise.
2. **Interim Core cost vs a resumable stepper.** Is a ~10-25 min full warm re-extraction **every hour** acceptable for the demo, or is Phase-4 Core statefulness required before go-live? (D2 has 2 hours of slack, so interim is *feasible* — the question is operational cost/heat.)
3. **Broker H1-open epoch convention.** Confirm the live broker's server tz / DST fold so the emitted epoch matches `iTime(H1,1)` exactly. This is the difference between "trades" and "keep-last-goods forever."
4. **Stale-hold time bound.** How long may the EA keep-last-good before the guardian force-flattens? (Generator-down + weekend could be 48h+.) This is a risk policy, not a code default.
5. **Which feed is authoritative** for reconciliation — do we snapshot the broker feed to a bars store so the daily warm reconcile is reproducible, or reconcile live-vs-live?
6. **Reduced deployable dial interaction.** The shipped IC dial is a lower-s band (~0.6-0.8) per the margin gate, not s=1.6. `s` is an EA knob (not in the file), so the generator is dial-agnostic — but confirm the forward stream is validated at the *deployable* dial, not only the reproduction dial.
7. **2026 out-of-sample status.** The forward stream **is** the never-fitted 2026 holdout the campaign treats as a separate mandatory gate. Are live appends logged as forward evidence pending that gate, or does the owner accept them as reconciled?

---

## 10. What makes this hard (honest)

- **Three of the four inputs have no live producer.** Only `f34[h]` streams today. `f7`, `eq7`, and `eq34` are all batch artifacts; two of them (`f7`,`eq7`) come from a **single path-dependent extractor with no resume mode** and the one sanctioned `NotImplementedError` in the repo. The honest baseline is *re-simulate the book every hour*, not *step it*.
- **The native-equity shadows are the crux, and the most dangerous.** `a_h,b_h` weight every emitted number, cannot be read off the live account (the entire reason v3 replays), and a **wrong-but-consistent** seed (re-based instead of ratio-chained) passes the file's own <1e-12 self-check silently. Only a heavy daily warm reconcile catches it. Get the splice seed wrong and every forward hour is confidently, invisibly wrong.
- **Warm-state is non-negotiable and expensive.** Cold-start fabricates crisis artifacts (the COVID k≈4.7 landmine). Correct = re-run warm from 2020 every hour. Cheap = a stateful stepper that is only *admissible after* proving bit-identity — i.e., you pay the expensive path anyway to certify the cheap one.
- **Two shadows can't share a process** (lock_v5 stop_out poisoning), so the service is inherently multi-process with on-disk handoff — more moving parts, more failure surface.
- **The EA can't see appends as built.** The single hardest *plumbing* blocker: `FedReplay` is load-once-at-init. No tail-reader ⇒ the entire generator is inert. And that reader is a new `.ex5`, so it owes its own reconciliation.
- **config_hash pins the model, not the data.** A green hash gate + a green <1e-12 self-check can both pass on a stream that legitimately differs from the IC batch by feed physics (~8pp seen on Duka). "It reconciles" only means something against a *same-feed* batch — the intrinsic checks give false confidence on their own.
- **The race is irreducible.** You cannot both apply hour `h` at `h+1:00:00+ε` (D1) and finish a from-scratch warm recompute in that window. Some minutes of prior-hour keep-last-good are structural; the only wrong fix (a second causal hour) breaks the model definition. The best you get is a *small, measured* deviation from batch, not zero.
- **It's out-of-sample by construction.** This stream is exactly the 2026 holdout the campaign has not fitted and treats as a separate gate. A perfectly-engineered generator still produces numbers the campaign has agreed not to trust blindly.
