# FableFederation_V1 — architecture spec (FMA3 blend EA)

**Status: SPEC, 2026-07-10.** This document is the build contract for the ONE new FMA3 EA that
supersedes the two-parent-EA deployment (owner decision tonight). Companion:
[`TRANSPLANT_V7.md`](TRANSPLANT_V7.md) (the verbatim-transplant inventory + exact seams) and
§9 here (the Wine compile probe — **headless compilation WORKS on this machine**; recipe below).

Ground rules (owner, non-negotiable):

1. **Core sleeves + band logic transplant VERBATIM** from NSF5
   `mt5/ea/FableMultiAsset1_V7.mq5` (PROVEN: IC real-tick runs 53/54 today, €10k→€631k @R12.8 /
   €398k @R8.96). No "improvements". Parity gate **G1**: Core-only mode reproduces run 54.
2. **The Satellite side is a NEW consumption layer only.** Signals STAY IN PYTHON. Tester mode reads a
   frozen-targets replay CSV (hash-gated); live mode reads a Python-brain targets file. The FMA2
   EA/replay stack **never worked correctly** per owner ground truth — it is a REFERENCE for file
   formats only (`FMA3/archive/docs-v1.0/FMA2_EA_AUDIT.md`), never a code base to build on.
3. **Blend bookkeeping = fresh-seed virtual sub-books at w = 0.70/0.30**, each sub-book's
   capital compounding on its own P&L (the FMA3 v1.0 construction —
   `archive/docs-v1.0/STRATEGY.md` §4, `strategy_fma3.py`, PROTOCOL §5.7 anti-coupling).
4. **FTMO guardian module, config-gated** (`InpDailyStopX`, 0 = off). Gate **G4**: off ⇒
   bit-identical behavior.

---

## 1. Module map

```
FMA3/mt5/ea/
  FableFederation_V1.mq5          main: inputs, OnInit/OnTick/OnDeinit orchestration only
  Include/FMA3/
    V7Core.mqh                    the VERBATIM Core transplant (sleeves, signals, band/harvest,
                                  ledger, sizing, execution primitives, logging) — see
                                  TRANSPLANT_V7.md for the function-by-function inventory
    Federation.mqh                F3_* sub-book ledgers: Satellite realized/floating attribution by
                                  magic range, virtual book equities, bookkeeping invariant log
    V34Replay.mqh                 F3_* tester loader: frozen-targets CSV, config-hash gate,
                                  forward cursor, keep-last-good (format §3)
    V34Live.mqh                   F3_* live reader: fma3.targets.v1 JSON, seq/hash/staleness
                                  rules, hold+alert failure behavior (contract §4)
    V34Exec.mqh                   F3_* order loop: frac × sub-book equity → lots → diff-vs-held
                                  per (symbol, magic); calls V7Core's execution primitives
                                  (SendSplit/CloseAll/ReducePos/HeldNet/RoundLots/EurPerQuote/
                                  MarketOpen) — shared library, zero duplicated order plumbing
    Guardian.mqh                  F3_* FTMO daily-stop module (spec §6)
  presets/                        .set files (matrix §7)
```

Naming law: **everything transplanted keeps its Core name and body byte-for-byte** (only the
runtime file-name prefix changes, `portfolio_v7_*` → `fma3_fed_*`, and the two seams in
TRANSPLANT_V7.md §3). **Everything new is `F3_`-prefixed** (functions, globals `g_f3*`, inputs
per §7) so collisions with Core identifiers are impossible without touching Core code.

Driver model (from Core, unchanged): attach to a 24/7 M1 clock chart (ETHUSD or BTCUSD), one pass
per new M1 bar; hedging account required (Core `OnInit` check stays). The Satellite pass appends after
the Core sleeve loop inside the same bar pass. The guardian check is the only per-tick logic and
sits before the new-bar early-return (§6). Magic ranges keep both parents' conventions and
cannot collide: Core `InpMagicBase=360000` → 360001..360012 (verbatim); Satellite
`InpMagicBaseV34=8400000` → 8400001..8400008, sleeve order fixed as FMA2 `brain_config.SLEEVES`:
`meanrev, carry_breakout, seasonal, intraday, crisis, trend_v2, crypto_smart, mag_xau`.

Mode switches (all config, one binary):

| Input | Meaning |
|---|---|
| `InpEnableV7` (default true) | run the Core book |
| `InpEnableV34` (default true) | run the Satellite consumption layer |
| `InpV34TesterReplay` (auto-true in tester) | Satellite source = frozen CSV vs live brain file |
| `InpDailyStopX` (default 0 = off) | FTMO guardian |

`g_f3FedActive = (InpEnableV34 && InpEnableV7)` — the single flag that switches the Core
book-equity seam (§5.3). With `InpEnableV34=false` the EA takes the byte-identical Core code path
(G1).

---

## 2. The four gates — exact pass criteria and tester runs

All runs: IC Markets EU demo login (Raw, EUR, hedging), model **every tick based on real
ticks**, deposit **EUR 10,000**, clock chart ETHUSD M1, per `mt5/README.md` §(a). Collect the
HTML report + `Common\Files` CSVs for each.

### G1 — Core parity (the transplant is verbatim)

- **Preset:** `FED_G1_V7ONLY_R896.set` = run 54's exact config re-expressed
  (`InpEnableV34=false`, `InpDailyStopX=0`, `InpRisk=8.96`, `InpInitial=10000.0`, band
  0.25/1.75/5, `InpEqualWeight=true`, `InpUS500=USTEC`, all other Core inputs as
  `presets/V7_FMA3IC_R896.set`).
- **Run:** one full pass 2020-01-01 → 2025-12 (same window as run 54).
- **PASS:** final equity equals run 54 **to the cent (€398,368.75)**; identical total deal
  count; the decisions CSV (`fma3_fed_decisions.csv`) is row-for-row identical to run 54's
  `portfolio_v7_decisions.csv` (same tester build + same tick data ⇒ bit-identity is the
  criterion, not a tolerance). Any diff = transplant defect; fix the EA, never re-interpret
  the gate.
- Health row: `volume_rejects=0` (plumbing STOP otherwise, DEMO.md rule 7).

### G2 — Satellite replay consumption layer

Three parts:

- **G2a (hash gate, seconds):** tamper one hex digit of the CSV header's `config_hash` → the EA
  must print the mismatch and return `INIT_FAILED` (no orders, no files written besides the
  journal). Restore file → INIT succeeds and logs `loaded N rows … hash=… scale=…`.
- **G2b (full replay, long):** preset `FED_G2_V34ONLY_S10.set` (`InpEnableV7=false`,
  `InpV34Mult=1.0` i.e. native scale-10 file unscaled), window 2020-01-02 → 2025-12-31.
  **PASS:** run completes; tester CAGR ≥ **0.85 × 88.66%** (the Satellite record pin,
  `v34_s10_pin_1m.json` — the parents' B1 retention bar); `volume_rejects=0`; equity-DD
  reported (feeds the Satellite k, no pass/fail on it — the COVID tail is the measurement, not a
  gate, cf. `k_calibration_v7.json` note).
- **G2c (loader semantics, minutes on a 1-week window):** an hour with no rows keeps the
  last-good target vector (logged `REPLAY keep-last-good`); within a populated hour a symbol
  absent from the rows is flattened; `flat_at_server_hour`/`no_entry_after_hour` honored
  (verify one seasonal 06:00 flatten and one intraday 21:00 flatten in the deal list).

### G3 — blend bookkeeping

- **Preset:** `FED_IC.set` (§7), both books on, guardian off. One full pass 2020→2025-12.
- **PASS (bookkeeping invariants, checked from `fma3_fed_books.csv` daily rows):**
  1. `E_v7_virtual + E_v34_virtual − InpInitial = ACCOUNT_EQUITY` within **±0.5%** of equity at
     every daily mark (the residual = margin/stop-out coupling the record engine prices; a
     drift beyond that is an attribution bug);
  2. Core re-split (`REBAL`) events reseed **only** Core sleeves from **Core virtual book equity** —
     no Satellite P&L in any Core seed (grep: every REBAL row's book equity equals the same row's
     `E_v7_virtual`);
  3. the Core band re-split **dates** match the G1 run's dates exactly (anti-coupling: Core's
     trigger state never sees Satellite P&L — the ±€128 chaos lesson, STRATEGY.md §4.5). A date
     diff is a FAIL unless traced to a shared-margin order rejection, which must be logged;
  4. no (symbol, magic) is ever touched by both layers (magic ranges disjoint by
     construction; assert in `OnInit`).
- **Report read (not pass/fail):** combined curve vs the blend record reference at s=1.6
  (`hrisk1_results.json`: CAGR 170.2%, maxDD_worst 22.58%, tail 8.12%) → the blend k, via
  `scripts/combine_tester_reports.py` conventions.

### G4 — guardian no-op + function

- **G4a (no-op, short):** window 2020-01 → 2020-06, preset `FED_IC.set` with `InpDailyStopX=0`,
  run twice: once as shipped, once with the guardian call sites commented out (build-time
  probe, not shipped). **PASS:** identical decisions CSV + final equity to the cent. (The
  guardian's only permitted footprint at x=0 is a single short-circuit branch — §6.)
- **G4b (function, short):** same window, `InpDailyStopX=2.0`. **PASS:** on every server day
  where equity ≤ dayAnchor×0.98: all positions (both books' magics) flattened on that tick,
  `GUARD_STOP` logged with anchor/equity, zero order sends until the next server day, and a
  `GUARD_RESUME` row at the rollover. Core ledger seeds are NOT reseeded by the guardian (the
  flatten realizes P&L into the existing quarter ledger; band logic self-heals next bar —
  verify no spurious REBAL on the stop day).

---

## 3. Satellite replay-file format (tester mode) — the FMA3 version

Format is carried over from the FMA2 tester loader **as a file format** (audit §1.3; loader
semantics re-implemented fresh in `V34Replay.mqh` — no FMA2 code reuse).

```
Line 1 (header):  global_scale=10.0,config_hash=48c09199fbf83d82
Data rows:        ts_server_epoch,symbol,exposure_frac,sleeve[,flat_at_server_hour,no_entry_after_hour]
```

- **Location:** `Common\Files\FMA3_v34_replay.csv` (`FILE_COMMON` — tester agents see it).
  Input `InpV34ReplayFile` for the name.
- **Header:** key=value tokens, order-free. `config_hash` MUST equal the compiled constant
  `F3_V34_CONFIG_HASH = "48c09199fbf83d82"` (the Satellite book hash, `strategy_fma3.py` parents.v34)
  or `OnInit` hard-fails (`INIT_FAILED`) — G2a. `global_scale` is an echo, logged; the file is
  ALWAYS the native scale-10 book — the deployment dial lives in the EA (`InpV34Mult`, §5.2),
  so ONE frozen artifact serves every preset (this deliberately supersedes the FMA2 Run-2
  "regenerate + restamp per dial" pattern, audit §3).
- **Rows:** ts-ascending. `ts_server_epoch` = the H1 bar-open **server wall clock interpreted as
  seconds-since-1970 with NO timezone shift** (matches `iTime()` semantics exactly; e.g.
  2020-01-02 00:00 server = 1577923200). `exposure_frac` = signed fraction of the Satellite
  **sub-book equity**, already ×10 and hard-limit/cap-distributed by the Python book — the EA
  never re-derives, only multiplies by `InpV34Mult`. `sleeve` (mandatory in the FMA3 version —
  no `DefaultSleeveForSymbol` guessing; XAUUSD is 4-way ambiguous) maps to magic via the fixed
  §1 table; unresolvable sleeve ⇒ row skipped WITH a counted warning, >0 skips at load ⇒
  INIT_FAILED (stricter than FMA2: a frozen file must be perfect). Optional cols 5/6 = forced
  server-hour exits; absent = −1 = none.
- **Consumption:** on each new H1 boundary of the clock chart, swap in all rows stamped with the
  just-closed hour (O(rows) forward cursor). Empty hour = keep-last-good + WARN. Within a
  populated hour, a (symbol, sleeve) not listed = target 0 (flatten-by-omission).
- **12-decimal fracs** (`%.12f`) so leg sums re-verify against the Python book at 1e-9.

**Regeneration script contract** (`FMA3/scripts/export_sat_replay.py`, NEW, FMA3-side):

1. Reads the pinned Python book ONLY — `FMA2 ea/brain/target_engine.build_book(rebuild=False)`
   on frozen parquets via read-only import (exactly the audited exporter's data path; no 1m
   cache, no record engine — busy-engine-safe). FMA2 stays read-only: the script lives in FMA3
   and imports the parent.
2. Emits one row per (hour, sleeve, symbol) with |frac| > 1e-9; exit metadata from
   `brain_config.SLEEVE_SCHEDULE` verbatim (`seasonal` 6/5, `intraday` 21/20); sleeve names
   from `brain_config.SLEEVES`.
3. Stamps header `global_scale=10.0,config_hash=48c09199fbf83d82`; **re-parses its own output**
   and asserts per-(hour,symbol) leg sums reproduce `net_capped` to <1e-9; hard-fails on any
   config drift (recomputed brain hash ≠ 48c09199fbf83d82).
4. Prints the file sha256 → recorded in the FMA3 run sheet next to the tester run that consumed
   it.

---

## 4. Live brain-file contract — `fma3.targets.v1` (ONE clean interface)

- **Path:** `<terminal data>/MQL5/Files/fma3/targets.json` (EA sandbox; the brain writes
  `targets.json.tmp` → `FileFlush` → rename. Readers seeing missing/partial JSON keep
  last-good). Input `InpV34LiveFile="fma3\\targets.json"`.
- **Schema (all fields required unless marked opt):**

```json
{
  "schema": "fma3.targets.v1",
  "seq": 12873,
  "generated_server": "2026-07-11 01:00:05",
  "bar_time_server": "2026-07-11 01:00:00",
  "global_scale": 10.0,
  "config_hash": "48c09199fbf83d82",
  "targets": [
    {"sleeve": "seasonal", "symbol": "XAUUSD", "exposure": 0.180,
     "flat_at_server_hour": 6, "no_entry_after_hour": 5},
    {"sleeve": "crypto_smart", "symbol": "BTCUSD", "exposure": 0.065}
  ]
}
```

  `exposure` = signed fraction of the Satellite sub-book equity at native scale 10 (identical
  convention to the replay CSV; the EA applies `InpV34Mult`). Magic derived EA-side from the
  fixed sleeve table — the file carries no magics (one fewer thing to drift).
- **Validation on read (every M1 pass, cheap mtime check first):**
  1. `schema` string exact match, else reject file (keep-last-good) + CRITICAL alert;
  2. `config_hash` vs compiled `F3_V34_CONFIG_HASH` — mismatch ⇒ reject + CRITICAL alert.
     (This closes FMA2's D1 gap — the audited live executor never checked the hash; here the
     check is in the ONE shared parse path used by both tester and live.)
  3. `seq` must strictly increase; ≤ last-accepted ⇒ ignore silently (normal re-read).
- **Staleness rule:** if `bar_time_server` is older than `InpV34StaleMin` (default **150**
  minutes = 2 signal bars + slack) against `TimeTradeServer()`:
  **HOLD** — keep all held Satellite positions untouched, suppress new entries and target changes,
  still honor `flat_at_server_hour` forced exits (risk-reducing), and alert once per episode
  (`V34_STALE` row + `Alert()`), with a `V34_RESUME` row when a fresh file lands. The Core book
  is unaffected.
- **Failure behavior (missing file at init, unparseable, hash-rejected):** same HOLD + alert
  posture. **Never flatten on data failure alone** — flattening is the guardian's job (§6) or
  the owner's. No halt-latch: recovery is automatic on the next valid file.

Tester note: in the Strategy Tester `InpV34TesterReplay` forces the CSV source; the live reader
is compiled but unreachable (mirrors Core's `g_live` pattern).

---

## 5. Blend bookkeeping — algorithm and the dial reconciliation

### 5.1 The construction being implemented

FMA3 v1.0 (STRATEGY.md §4): two virtual sub-books on one cross-margined account, fresh-seeded
at (w, 1−w) = (0.70, 0.30) of starting capital, **each compounding on its own P&L only**, no
cross-book rebalancing ever, and neither book's internal trigger state may see the other's P&L
(PROTOCOL §5.7 — the ±€128 chaos guard).

### 5.2 How the (w, 1−w) split is carried — the reconciliation (READ THIS)

The transplanted Core code seeds its sleeve ledger as `g_seed[n] = InpInitial × W[n]`
(`FableMultiAsset1_V7.mq5:1169`) and sizes as `lots = VBalance(n) × |m(R)| / unit_eur`
(`:604,:610` with `:742`), i.e. notional ∝ `InpRisk × InpInitial`. Two mathematically
equivalent ways to put the Core book on a 0.70 sub-account at global scale s
(dimensional identity `R·E` invariant: **8.96 × 10,000 ≡ 12.8 × 7,000**):

| Convention | Seeds | Core dial | Satellite frac multiplier | Status |
|---|---|---|---|---|
| **(A) w-in-the-dial** (SHIPPED) | both virtual books seed at the FULL `InpInitial` | `InpRisk = 8·w·s = 5.6·s` (= **8.96** @ IC s=1.6) | `InpV34Mult = (1−w)·s` (= **0.48** @ IC) | proven — run 54 IS this operating point |
| (B) w-in-the-seed | Core book `w·InpInitial` = €7k, Satellite book `(1−w)·InpInitial` = €3k | `InpRisk = 8·s` (= 12.8 @ IC) | `InpV34Mult = s` (= 1.6) | REJECTED for shipping |

**(A) ships.** Reasons, in force order:

1. **Run-54 fidelity.** Core's per-sleeve clips are ABSOLUTE and do not rescale with the dial
   (gold donch ±6 `:384-385`, night [0,6] `:387`, USTEC ±6/Monday [0,10] `:400-401`, S6
   [0,6] `:366`, BTC [0,1.2] `:457` — `mt5/README.md` "Dimensional check"). (A) at R8.96
   reproduces the exact clip-binding behavior the owner just validated twice; (B) at R12.8
   binds the caps harder and diverges from both run 54 and the record pin (which scales
   already-clipped R8 fracs by w·s without re-clipping).
2. **G1 is free.** Core-only parity mode and blend mode use the SAME seeds and dial — the
   Core book in the blend is behaviorally run 54 modulo shared margin.
3. It is the deployment convention the FMA3 v1.0 package already locked
   (`archive/docs-v1.0/DEMO.md` deployment item 2; `mt5/README.md` §c: both stacks seeded €10k, "each
   dial already carrying w·s", `E_fed = E_v7 + E_v34 − 10,000`).

Scale-invariance (STRATEGY.md §4.4: Core band triggers are slot RATIOS; Satellite positions are
equity FRACTIONS) is what makes (A) ≡ (B) in return space; what is NOT invariant (clip
binding, min-lot quantization) is exactly why the proven point (A) wins. The w=0.70/0.30
fresh-seed split of the v1.0 construction is thus carried **in the dials, in return space**,
not in the seed EUR amounts — with virtual books overlapping the same account capital, which
is why the guardian and margin reality read the REAL account (§5.4, §6).

### 5.3 The ledgers (exact)

**Core book — the transplanted ledger, untouched:** `g_seed[]/g_realized[]` per sleeve,
`UpdateRealized()` folds history deals by magic (`:725-741`; Satellite magics fall outside
`InpMagicBase+1..+12` and are skipped by the existing range check `:733-734` — verbatim code
already blend-safe). Sleeve capital = `VBalance(n) = g_seed[n]+g_realized[n]`.

**Core virtual book equity** (new, `Federation.mqh`):
`E_v7 = Σ_{n: W[n]>0} (VBalance(n) + FloatingPnL(n))` — at seed exactly `InpInitial`.

**THE ONE SEAM:** Core's re-split reseeds from `preEquity = AccountInfoDouble(ACCOUNT_EQUITY)`
(`QuarterRebalance` `:872`). In the blend the account contains Satellite P&L ⇒ using it would couple
the books (banned). Replacement:

```mql5
double preEquity = g_f3FedActive ? F3_V7BookEquity()            // virtual sub-book
                                 : AccountInfoDouble(ACCOUNT_EQUITY); // G1 byte-path
```

`BandTriggered()`/`HarvestTriggered()` already read per-sleeve `VBalance+FloatingPnL` ratios —
no seam, verbatim, and invariant to the convention choice.

**Satellite book (new):** `g_f3Seed34 = InpInitial` (convention A), `g_f3Realized34` accumulated
from history deals with magic ∈ [8400001, 8400008] (same cursor pattern as `UpdateRealized`,
own cursor), `F3_V34Floating()` by magic range.
`E_v34 = g_f3Seed34 + g_f3Realized34 + F3_V34Floating()`. Never reseeded (no re-split exists in
the Satellite book; fixed-fraction by construction).

**Satellite sizing (the order loop, `V34Exec.mqh`):** per target leg
`desired_lots = sign(frac) × RoundLots(sym, |frac × InpV34Mult| × E_v34 / unit_eur)` with
`unit_eur = px × contract × EurPerQuote(sym)` (Core's `:601-624` primitives, incl. the
`InpMarginCap` margin clamp and `SYMBOL_VOLUME_LIMIT` guard, reused as-is with
`balance = E_v34`); diff vs `HeldNet(sym, magic)` with the same 0.25 relative band
(`InpRebalBand`); same-sign delta / reversal-close+reopen / flatten logic mirroring
`ExecSleeve` shape; `MarketOpen(sym)` defer; forced exits (`flat_at_server_hour`) close
regardless of band; `no_entry_after_hour` suppresses adds/opens but allows reductions.

**Daily book log** (`fma3_fed_books.csv`): `utc_time, E_v7, E_v34, acct_equity, residual,
w_realized` — feeds G3 invariants and the drift-band watch (review trigger if realized w
leaves 0.56–0.84, STRATEGY.md §11).

### 5.4 What stays REAL-account

Broker margin, stop-out, and the guardian (§6) operate on real `ACCOUNT_EQUITY` — the joint
margin is precisely what the record engine simulated (H-CAPS-1 verified the inherited caps
compose; no joint cap added). The virtual books are attribution + trigger isolation only.

---

## 6. Guardian spec — FTMO daily stop (`Guardian.mqh`)

Config: `InpDailyStopX` (percent, **0 = off**), `InpGuardAnchorMode` (fixed: FTMO convention).

- **Placement:** first statement in `OnTick`, BEFORE the M1 new-bar early-return — the stop
  must be tick-granular, not bar-granular. At `InpDailyStopX <= 0` the entire module is one
  short-circuit branch (`if(InpDailyStopX<=0.0) …skip…`) touching no state, writing no files —
  the G4a bit-identity guarantee.
- **Day anchor:** at each SERVER-day rollover (first tick of the day),
  `g_f3DayAnchor = MathMax(AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY))`
  — FTMO counts daily loss from max(balance, equity) at midnight server time; max() is the
  conservative side.
- **Trigger:** any tick where `ACCOUNT_EQUITY <= g_f3DayAnchor × (1 − InpDailyStopX/100)`:
  1. flatten ALL positions owned by this EA (both magic ranges; foreign magics untouched) via
     the transplanted `CloseAll` per (symbol, magic) — market-closed symbols retried each tick
     while halted (crypto is 24/7; FX session gaps are the only wait);
  2. latch `g_f3Halted = true` until the next server-day rollover — while halted NO order path
     runs (Core sleeve loop and Satellite exec both gated), signal recomputes still run (state stays
     warm);
  3. log `GUARD_STOP` (anchor, equity, x) to the decisions CSV + `Alert()`; `GUARD_RESUME` at
     rollover.
- **Ledger interaction:** the flatten realizes P&L into both books' normal deal attribution
  (Core's `UpdateRealized` + F3 Satellite cursor) — NO reseed, NO band-clock reset (H-FED-2 corollary:
  Core's min-gap clock never resets on a blend-level event). Next day the Core sleeves re-open
  toward their targets through the verbatim `ExecSleeve` path; Satellite re-opens on its next target
  application.
- **Restart hardening (live):** anchor + halt latch persisted in the F3 state file so a
  terminal restart inside a halted day stays halted.

Dial guidance (preset matrix): FTMO 10% account daily loss ⇒ ship `InpDailyStopX` well inside
it (e.g. 3–5%); exact x is the FTMO campaign's call (dial re-ship in flight, FMA3-009 walking
s below 0.5 as of tonight's log).

---

## 7. Preset matrix

All presets share the Core core block verbatim from `presets/V7_FMA3IC_R896.set` (band 0.25/1.75/5,
`InpEqualWeight=true`, sleeve enables FXTUJ/AU/EU=false + S6/BTC=true, `InpUS500=USTEC`, IC
symbol names) unless stated.

| Preset | `InpEnableV7` | `InpEnableV34` | `InpRisk` | `InpV34Mult` | `InpDailyStopX` | Purpose |
|---|---|---|---|---|---|---|
| `FED_G1_V7ONLY_R896.set` | true | false | 8.96 | — | 0 | **G1** parity vs run 54 |
| `FED_G2_V34ONLY_S10.set` | false | true | — | 1.00 | 0 | **G2** replay vs the 88.66% pin |
| `FED_IC.set` | true | true | **8.96** (=5.6×1.6) | **0.48** (=0.30×1.6) | 0 | **G3/G4**, IC deploy candidate |
| `FED_FTMO.set` | true | true | **2.24** (=5.6×0.4) ⚠️ | **0.12** (=0.30×0.4) ⚠️ | 3.0 (placeholder) | FTMO deploy candidate |

⚠️ FTMO dials are **provisional twice over**: (1) FMA3-005c s=0.4 is being re-shipped
(`ftmo_campaign.log` tonight: s=0.5 not probe-robust, walking down); (2) the Core low-dial clip
divergence stands — at `InpRisk=2.24` cap-pinned components run up to ~3.6× heavier than the
scaled-frac record validation (`mt5/README.md` "Dimensional check", carried in the preset header
comment). Do not deploy FTMO before the campaign re-ships the dial AND sets `InpDailyStopX`.

IC dials verify against the locked formula (`DEMO_PREREGISTRATION` §2): Core `8×0.70×s`, Satellite
`10×0.30×s` with the ×10 native already in the file ⇒ `InpV34Mult = 0.30×s`. Both fork dials
remain provisional pending the k re-pick (the Satellite tick leg of `k_calibration_v7.json` is what
G2b/G3 finally measure).

---

## 8. Transplant inventory

See [`TRANSPLANT_V7.md`](TRANSPLANT_V7.md) — function-by-function disposition (verbatim /
renamed-constant / seam), with the three integration seams line-cited: sub-book capital vs
`InpInitial` (§5.2 resolution: `InpInitial` stays — convention A), the `QuarterRebalance`
preEquity seam, and the guardian + Satellite insertion points in `OnTick`.

---

## 9. Compile probe verdict — headless Wine compilation WORKS

**Probed 2026-07-10 on this machine, with the owner's MT5 terminal live in the same Wine
prefix (FTMO campaign) — no interference observed.**

- MetaEditor: `…/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe` ✔
- Wine binary: **no system wine**; the app bundle ships one:
  `/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64` ✔
- Trivial EA: compiles headlessly, `.ex5` produced, `Result: 0 errors, 0 warnings` ✔
- **The real `FableMultiAsset1_V7.mq5` compiles headlessly: 0 errors, 0 warnings, 1.5 s,
  77 KB `.ex5`** (with `<Trade/Trade.mqh>` resolved) ✔

**The one trap (this is why the FMA2 audit believed headless "no-ops"):** MetaEditor's
switch parser truncates paths at the first SPACE under this Wine build —
`/compile:C:\Program Files\…` silently compiles nothing (exit 0, no log), and
`/include:C:\Program Files\…\MQL5` errors as `C:\Program\Include\Trade\Trade.mqh not found`.
**Fix: a space-free symlink inside drive_c** (created, persistent):
`drive_c/mql5link → drive_c/Program Files/MetaTrader 5/MQL5`.

**The build recipe (use for EVERY iteration):**

```bash
export WINEPREFIX="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5"
export WINEDEBUG=-all
WINE='/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64'
# stage: cp EA + Include/FMA3/* under "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MQL5/..."
"$WINE" 'C:\Program Files\MetaTrader 5\MetaEditor64.exe' \
    '/compile:C:\mql5link\Experts\FMA3\FableFederation_V1.mq5' \
    '/include:C:\mql5link' \
    '/log:C:\mql5link\Experts\FMA3\build.log'
# exit code = number of successfully compiled files: 1 = OK, 0 = FAILED (read the log)
# log is UTF-16: iconv -f UTF-16 -t UTF-8 ".../build.log"
```

The exe path itself MAY contain spaces (wine resolves it); only MetaEditor's own `/compile`,
`/include`, `/log` arguments must be space-free. Probe evidence archived in the session
scratchpad (`compiletest/*.log.txt`); probe artifacts removed from the owner's MQL5 tree; the
`mql5link` symlink was left in place (required by the recipe).
