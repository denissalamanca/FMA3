# v7 → FableFederation_V1 transplant inventory

**Source (READ-ONLY, PROVEN):** NSF5 `mt5/ea/FableMultiAsset1_V7.mq5` (1304 lines, read in full
2026-07-10). Owner ground truth: this EA ran IC real-tick flawlessly twice today (runs 53/54).
**Law: every item marked VERBATIM moves byte-for-byte into `Include/FMA3/V7Core.mqh`.** The
complete list of permitted deviations is §3 (two seams + renames) and §4 (orchestration moves).
Anything else that differs from the source is a defect against gate G1.

Line numbers = the v7 source file.

---

## 1. VERBATIM — moves unchanged into `V7Core.mqh`

### Inputs & constants (lines 54–164)

| Block | Lines | Notes |
|---|---|---|
| All 34 `Inp*` v7 inputs | 57–115 | NAMES + DEFAULTS byte-identical (incl. `InpMagicBase=360000`, `InpInitial=10000.0`). They live in the main .mq5 (MQL5 requires `input` at file scope of the program). **AMENDED 2026-07-10 (§2.1): input comments/ordering/`input group` headers are allowlisted display-only deltas** |
| Sleeve layout defines | 120–134 | `N_SLEEVE`, `SL_*`, `IS_DIVERSIFIER` |
| `W[N_SLEEVE]` float64 weights | 137–147 | full-precision literals untouched |
| `g_slSym/g_slName/g_slSign` | 149–151 | |
| Series ids | 154–164 | `N_SER`, `SID_*` |
| Globals: `trade`, `Series g_ser`, ledger (`g_seed/g_realized/g_quarterStart/g_dealCursor`), signal coefficients, day/bar state, health counters, defer flags, live-state | 169–217 | verbatim incl. `g_live`, `g_skipActive`, `g_pendResplit` |
| Embedded policy rates `USD_D/USD_R/JPY_D/JPY_R` | 220–227 | |

### Functions — all verbatim, none renamed

| Function | Lines | Role |
|---|---|---|
| `ToUtc`, `UtcDayStart`, `BarMid` | 232–234 | time/UTC helpers |
| `PolicyRate` | 236–241 | carry gate input |
| `InOpexWeek` | 246–256 | S6 calendar |
| `AppendDay`, `CommitFromRates`, `ExtendSeries` | 261–302 | daily-series maintenance |
| `SMA`, `PriceStd`, `RetStd`, `AnnVol`, `MaxOf`, `MinOf`, `DonchSig`, `Clip` | 307–349 | rolling stats |
| `FxTrend60`, `S6Leg` | 351–367 | sleeve signal helpers |
| `RecomputeDaily` | 372–462 | all 7 slots' daily signals (XAU donch+night, US5 regime+Monday, JPY smart, ETH mom, FXT legs, S6 magnitudes, BTC hurdle) |
| `RecomputeEURGBP` | 464–484 | 20:00-stamped z-rev |
| `RecomputeAUD` | 486–507 | 07:05-stamped z-rev |
| `CurrentTarget` | 512–548 | per-bar signed multiple incl. opex/night/Monday gates |
| `MidOf`, `EurPerQuote` | 553–561 | EUR conversion |
| `RoundLots`, `SendSplit`, `DesiredLots` | 566–624 | sizing + volume-max chunking + margin/volume-limit clamps — **shared with the v3.4 exec layer as-is** |
| `HeldNet`, `CollectTickets`, `CloseAll`, `ReducePos`, `OpenDir` | 629–688 | position queries/execution — **shared with v3.4 exec + guardian as-is** |
| `InReopenWindow`, `MarketOpen`, `AllMarketsOpen` | 690–720 | session gates (`AllMarketsOpen` iterates `W[n]>0` — v7 sleeves only, correct for gating v7 re-splits; v3.4 uses `MarketOpen` per symbol) |
| `UpdateRealized`, `VBalance`, `FloatingPnL` | 725–757 | the v7 sub-account ledger. NOTE: `UpdateRealized`'s magic-range check (`idx<0 || idx>=N_SLEEVE`, :733–734) already skips v3.4 magics (8400001+) — **verbatim code is federation-safe with no change** |
| `HarvestTriggered` | 763–777 | k=2.5 inert guard |
| `BandTriggered` | 798–829 | BAND_SYM_25 incl. the S6 three-legs-one-slot aggregation — reads per-sleeve `VBalance+FloatingPnL` ratios only, so it is sub-book-pure with no seam |
| `QuarterId` | 831 | |
| `SaveState`, `LoadState` | 833–868 | live restart persistence (file name rename only, §3) |
| `QuarterRebalance` | 870–914 | H9 delta-resize + ledger reseed — **one seam at :872** (§3) |
| `LogRow` | 919–931 | decision CSV writer (account-level columns are log-only; unchanged) |
| `Heartbeat` | 933–958 | live heartbeat (file name rename only) |
| `LogReject`, `LogSkip` | 965–991 | P2/P1 live-only logs (tester byte-neutral by `g_live` gate) |
| `LiveReady` | 1001–1029 | P1 connect/history guard (tester no-op) |
| `ExecSleeve` | 1034–1089 | per-sleeve reconcile-to-target incl. reopen-defer and closed-market defer |

### `OnInit` / `OnDeinit` / `OnTick` bodies (1094–1303)

Move verbatim as the SKELETON of the new EA's handlers, with only the §4 insertions. Every
existing statement, order, and guard stays: symbol table + series wiring (1097–1115), the 11
`SymbolSelect` calls (1117–1118, extended per §4), hedging-account hard check (1120–1126),
enable→W zeroing + `InpEqualWeight` slot math (1129–1156), `g_live` + state
restore-or-fresh-seed (1158–1175 — `g_seed[n]=InpInitial*W[n]` at :1169 **stays verbatim**, see
SPEC §5.2 convention A), series warmup + `RecomputeDaily` (1177–1179), decisions-CSV open
(1181–1205), init banner (1206–1211); `OnDeinit` health append (1213–1229); `OnTick`: new-bar
gate (1236–1238), `LiveReady` skip + heartbeat-on-skip (1257–1261), day-rollover recompute +
`g_pendResplit` (1263–1276), band/harvest re-split at first all-open bar (1285–1289), 07:05/20:00
stamped recomputes (1291–1292), the sleeve loop with per-sleeve magic/filling set (1294–1300),
heartbeat (1302).

---

## 2. Renames (string constants only — zero logic)

| v7 | Federation | Why |
|---|---|---|
| `#property version "7.00"` + header comment | new header, version "1.00" | different program |
| `STATE_FILE "portfolio_v7_state.csv"` | `"fma3_fed_state.csv"` | never share live state with the superseded deployment |
| `HB_FILE "portfolio_v7_heartbeat.csv"` | `"fma3_fed_heartbeat.csv"` | |
| `REJ_FILE`, `SKIP_FILE` | `fma3_fed_rejects.csv`, `fma3_fed_skips.csv` | |
| `"portfolio_v7_decisions.csv"` (:1187/:1199) | `"fma3_fed_decisions.csv"` | G1 compares CONTENT row-for-row vs run 54's file |
| `"portfolio_v7_health.csv"` (:1217) + `"7.00"` row tag (:1222) | `"fma3_fed_health.csv"`, tag `"F1.00"` | keep the append-per-run sweep convention |
| `Print` prefixes "PortfolioV5:" | keep as-is | cosmetic; changing them buys nothing and risks diff noise — **do not touch** |

### 2.1 Input-block display metadata (AMENDMENT 2026-07-10, owner UI request)

The transplanted v7 input comments were cryptic in the tester's Inputs tab. The
ENTIRE input block of `FableFederation_V1.mq5` was re-written for humans with
MQL5 `input group` sections and clear label comments. The amended law:

- **Variable NAMES and DEFAULT VALUES stay byte-identical** to the v7 source —
  presets bind to names; gate G1 parity binds to defaults. Any name/type/default
  delta remains a defect against G1.
- **Input COMMENTS, declaration ORDER within the file-scope input section, and
  the added `input group` headers are ALLOWLISTED display-only deltas.** MQL5
  input comments and group headers are pure display metadata read by the
  terminal's Inputs tab; the compiler strips them — they have ZERO logic
  impact (an input's comment/group changes neither its identifier, its binding
  in .set files, nor the compiled `.ex5` behavior).
- `scripts/check_transplant.py` enforces this mechanically: it parses every
  `input <type> <name> = <default>;` declaration from v7 source lines 57–115
  (34 declarations) and requires each (type, name, default) triple to appear
  byte-equal in `FableFederation_V1.mq5`; all non-input transplanted code is
  still required verbatim (its checks 2–3 are unchanged). It must still print
  `TRANSPLANT CLEAN`.

`InpMagicBase=360000` is kept (not renamed, not renumbered): magics 360001..360012, identical
attribution to the proven runs. Operational note for the owner: never run the old two-EA
deployment and this EA on the SAME live account simultaneously — same magics would collide;
the federation EA supersedes, it does not coexist.

---

## 3. The seams — the ONLY logic-touching edits (each one line-cited)

### Seam 1 — `QuarterRebalance` book equity (:872)

```mql5
// v7:      double preEquity=AccountInfoDouble(ACCOUNT_EQUITY);
// fed:     double preEquity = g_f3FedActive ? F3_V7BookEquity()
//                                           : AccountInfoDouble(ACCOUNT_EQUITY);
```

`F3_V7BookEquity() = Σ_{n:W[n]>0}(VBalance(n)+FloatingPnL(n))` (`Federation.mqh`). Rationale:
with v3.4 live on the same account, `ACCOUNT_EQUITY` contains v3.4 P&L; reseeding v7 slots from
it violates the anti-coupling law (STRATEGY.md §4.5, the ±€128/−€59k precedent). With
`g_f3FedActive=false` (v7-only mode) the original expression executes — G1 takes the
byte-identical path. This is the ONLY place v7 reads account equity for a decision; its other
`AccountInfoDouble` uses (:927–929, :944–945, :1224–1225) are log/health writes and stay.

### Seam 2 — where sub-book capital replaces `InpInitial`

**Nowhere — by decision.** SPEC §5.2 convention A: both virtual books seed at the full
`InpInitial` and the w=0.70/0.30 split is carried in the dials (`InpRisk=5.6·s`,
`InpV34Mult=0.30·s`). Therefore `:1169 g_seed[n]=InpInitial*W[n]` and the whole `OnInit` seed
path stay verbatim. (The rejected alternative — seeding at `w·InpInitial` with `InpRisk=8·s` —
is documented in SPEC §5.2; it changes clip binding away from the proven run-54 point.)

### Seam 3 — `OnTick` insertions (order matters)

```mql5
void OnTick()
{
   if(!F3_GuardianPass()) return;          // [G] tick-granular; pure no-op when InpDailyStopX<=0
   datetime bt=iTime(_Symbol,PERIOD_M1,0); // ── from here: v7 OnTick verbatim ──
   if(bt==g_lastBar) return;
   ...                                     // v7 lines 1236..1300 unchanged (LiveReady, rollover,
                                           // re-split, stamped recomputes, v7 sleeve loop)
   if(InpEnableV34) F3_V34Pass(bt,hour,dow); // [V] the v3.4 consumption layer, AFTER the v7 loop
   if(g_live && TimeCurrent()-g_lastHB>=HB_PERIOD){ Heartbeat(); g_lastHB=TimeCurrent(); }
}
```

- **[G] guardian** sits BEFORE the new-bar early-return (stop must fire intra-bar). Returns
  false while halted (flatten-retry + no trading). With `InpDailyStopX<=0` it is
  `if(InpDailyStopX<=0.0) return(true);` — no state, no I/O ⇒ G4a bit-identity.
- **v7 pass**: lines 1236–1300 byte-verbatim, including the `W[n]<=0 continue` sleeve loop.
  The v7 sleeve loop must also be skipped when `InpEnableV7=false` (G2 v34-only mode): wrap
  the loop + rollover-resplit block in `if(InpEnableV7)`, implemented by zeroing all `W[n]` in
  `OnInit` when `InpEnableV7=false` — zero weights make every v7 path a natural no-op through
  the EXISTING `W[n]<=0` guards (:718, :768, :809, :885, :1296) with no new branches in
  transplanted code. (`RecomputeDaily`/series still run; harmless and byte-neutral for G1
  since G1 has `InpEnableV7=true`.)
- **[V] v3.4 pass** (`V34Exec.mqh`): H1-boundary target swap (replay cursor or live-file read),
  then per-leg reconcile-to-target via the shared primitives, per-leg
  `trade.SetExpertMagicNumber(v34magic)` + `SetTypeFillingBySymbol` exactly like the v7 loop
  does at :1297–1298. Placed AFTER the v7 loop so v7's bar pass is untouched by construction;
  it never writes any `g_*` v7 global (compile-enforced: `V34Exec.mqh` includes only
  `Federation.mqh` + the primitive prototypes).

### Seam 4 — `OnInit` insertions (appended, never interleaved)

After the verbatim v7 `OnInit` body (before the final `return(INIT_SUCCEEDED)`):

1. `if(!InpEnableV7){ for(n) W[n]=0; }` — see Seam 3 note (placed right after the v7
   enable-flags block :1129–1133 so the `InpEqualWeight` math sees it consistently; when
   `InpEnableV7=false` skip the slot-equal print);
2. `SymbolSelect` the v3.4 symbol set (from the loaded replay/live file after parse — select
   the union of symbols found; a missing Market-Watch symbol under-fills with a logged reject,
   never crashes);
3. `F3_LedgersInit()` — v34 seed/cursor init (`g_f3Seed34=InpInitial`, deal cursor to now);
4. tester: `if(InpEnableV34 && MQLInfoInteger(MQL_TESTER)) if(!F3_LoadReplay()) return(INIT_FAILED);`
   — the hash gate (G2a) fails init BEFORE any order could exist;
5. live: parse `fma3/targets.json` once (missing file = HOLD posture, INIT succeeds — SPEC §4);
6. magic-range disjointness assert (360001..360012 vs 8400001..8400008) — belt-and-braces,
   `INIT_FAILED` on overlap (covers a user mis-setting `InpMagicBaseV34`);
7. guardian: `F3_GuardianInit()` (anchor persistence restore, live only, no-op at x=0).

`OnDeinit`: after the verbatim health append, `F3_BooksFinalRow()` writes the last
`fma3_fed_books.csv` row (G3 evidence). No change inside the v7 block.

---

## 4. What the v3.4 layer may and may not call

**MAY call (shared primitives, verbatim v7):** `RoundLots`, `SendSplit`, `DesiredLots`*,
`HeldNet`, `CollectTickets`, `CloseAll`, `ReducePos`, `OpenDir`, `MarketOpen`, `EurPerQuote`,
`MidOf`, `ToUtc`, `UtcDayStart`.
*`DesiredLots(sym, m, balance)` is called with `m = frac × InpV34Mult` and
`balance = E_v34` — it is already a pure function of its arguments (reads only symbol
properties + `InpMarginCap`), so reuse is seamless.

**MUST NOT touch:** any `g_*` v7 global (`g_seed`, `g_realized`, `g_quarterStart`,
`g_dealCursor`, `g_ser`, signal coefficients, `g_curDay/g_lastBar/g_pendResplit`, defer flags),
`trade` state outside its own per-leg `SetExpertMagicNumber` window, and the v7 log handle
`g_logh` except through `LogRow`-style F3 wrappers writing to the SAME decisions CSV with
sleeve names `V34_<sleeve>` (one audit stream, disjoint name space).

---

## 5. Verbatim-ness verification (build-time, cheap)

Before every G1 submission: extract the transplanted block from `V7Core.mqh` + the main file
and diff against `FableMultiAsset1_V7.mq5` with a 12-line allowlist (the §2 renamed string
constants + Seam 1's two lines + the §3/§4 marked insertions). The diff must show NOTHING else.
Suggested: `scripts/check_transplant.py` (FMA3-side) that mechanically strips the allowlist and
requires an empty residual diff — run it in the build loop next to the §9 compile recipe (SPEC.md).
