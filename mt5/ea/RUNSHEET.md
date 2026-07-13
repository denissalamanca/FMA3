# FableFederation_V1 — owner run sheet (G1 parity first, then the gates)

**Status 2026-07-10:** EA built and **compiled clean headlessly** (0 errors, 0 warnings,
MetaEditor via the SPEC §9 Wine recipe). Everything is already **staged on this machine**:

| Artifact | Where | Check |
|---|---|---|
| `FableFederation_V1.mq5` + `FableFederation_V1.ex5` | terminal `MQL5/Experts/` **ROOT (flat — the owner's tester lists the flat root, no subfolder)** | compiled 0/0 |
| `Include/FMA3/*.mqh` (V7Core, Federation, V34Replay, V34Live, V34Exec, Guardian) | terminal `MQL5/Include/FMA3/` | — |
| `FMA3_v34_replay.csv` (851,013 rows, 2020-01-02→2025-12-31, header `global_scale=10.0,config_hash=51a7541cc2aaa593`) | `Common\Files\` | sha256 `b7fc438a2ca4d6cd9d9025132e3532214537d35cb3ceb6d5e2c1fd52546fe674` |
| Presets `FED_G1_V7ONLY_R896 / FED_G2_V34ONLY_S10 / FED_IC / FED_FTMO` | repo `mt5/ea/presets/` | load via the tester's Load dialog |
| Run-54 reference CSVs (decisions + health) | `research/outputs/mt5/run54_archive/` | decisions sha256 `ba07e44f…f1ecf` |

Transplant verified mechanically: `python3 scripts/check_transplant.py` → *TRANSPLANT CLEAN*
(only the TRANSPLANT_V7.md allowlist differs from the v7 source). Re-run it + the §Rebuild
recipe after ANY source edit.

Unit evidence (off-MT5): `python3 mt5/ea/tests/test_federation_units.py` → **237 passed, 0
failed** (replay parser mirror incl. the real CSV + the repo→broker symbol map cases,
federation bookkeeping vs the `strategy_fma3` construction incl. the anti-coupling property,
guardian trigger paths incl. gap-through).

---

## Rebuild recipe (only needed after a source change)

```bash
export WINEPREFIX="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5"
export WINEDEBUG=-all
WINE='/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64'
MQL5="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MQL5"
cp mt5/ea/FableFederation_V1.mq5 "$MQL5/Experts/"        # Experts ROOT (flat), NOT a subfolder
cp mt5/ea/Include/FMA3/*.mqh     "$MQL5/Include/FMA3/"
"$WINE" 'C:\Program Files\MetaTrader 5\MetaEditor64.exe' \
    '/compile:C:\mql5link\Experts\FableFederation_V1.mq5' \
    '/include:C:\mql5link' '/log:C:\mql5link\Experts\build.log'
# exit code 1 = one file compiled OK; log is UTF-16:
iconv -f UTF-16 -t UTF-8 "$MQL5/Experts/build.log" | tail -3
python3 scripts/check_transplant.py          # must print TRANSPLANT CLEAN
```

Replay regeneration (engine-free, frozen parquets, FMA2 read-only):
`python3 scripts/export_v34_replay.py --install` — must print OVERALL PASS; record the new
sha256 here next to the run that consumes it.

---

## G1 — v7 parity vs run 54 (RUN THIS FIRST)

Everything identical to tonight's run 54 except the EA name.

1. **Login:** IC Markets EU demo (Raw, EUR, **hedging**) — same login as runs 53/54.
2. **Market Watch:** `XAUUSD, USTEC, USDJPY, ETHUSD, EURGBP, BTCUSD, AUDUSD, NZDUSD,
   EURUSD, EURJPY` (v3.4 symbols not needed — the replay file is not even opened at
   `InpV34Mode=0`).
3. **Strategy Tester:**
   | Setting | Value |
   |---|---|
   | Expert | `FableFederation_V1` (Experts flat root) |
   | Symbol / TF | **ETHUSD, M1** (the 24/7 clock chart, as run 54) |
   | Model | **Every tick based on real ticks** |
   | Dates | **2020-01-01 → 2025-12** (run 54's window) |
   | Deposit | **EUR 10,000**, leverage as runs 53/54 |
   | Preset | **`FED_G1_V7ONLY_R896.set`** |
4. **Startup checks (Journal/Experts):** `SLOT-EQUAL over 7 slots … slotW=0.1429`;
   `F3 init: v34mode=0 … v7=on fed=off`; no `F3 REPLAY` lines (v3.4 off).
5. **PASS criteria:**
   - final equity **EUR 398,368.75** — bit-identity is the criterion (same tester build +
     same tick data); the owner acceptance band is **±1%**;
   - MT5 **Relative (equity) DD 33.68% ±1pp** (run 54's COVID mark);
   - `Common\Files\fma3_fed_decisions.csv` **row-for-row identical** to
     `research/outputs/mt5/run54_archive/portfolio_v7_decisions.csv`
     (`diff` them; any diff = transplant defect — fix the EA, never re-interpret the gate);
   - `fma3_fed_health.csv` row: tag `F1.00`, **`volume_rejects=0`** (plumbing STOP
     otherwise, DEMO.md rule 7), `split_events=3` (run 54's count);
   - identical total deal count to run 54's report.
6. **Collect:** HTML report → `research/outputs/mt5/fed_g1_tester.html`; copy
   `fma3_fed_decisions.csv` + `fma3_fed_health.csv` next to it.

## G2 — v3.4 replay consumption layer

- **Symbol map (2026-07-10):** the replay CSV keeps the **repo** symbol names; the EA input
  `InpV34SymbolMap` (default `USA500=US500;DAX=DE40`, `repo=broker` pairs, `;`-separated,
  in every FED_*.set) translates them to the IC **broker** names ONCE at load time —
  everything downstream (SymbolSelect, orders, logs) runs on broker names. Journal at init:
  one `F3 SYMMAP: replay symbol USA500 -> broker US500` line per mapping; a mapped broker
  symbol missing from the terminal = loud `F3 SYMMAP FATAL … INIT_FAILED`.
- **G2a (seconds):** edit one hex digit of the `config_hash` in
  `Common\Files\FMA3_v34_replay.csv` line 1 → start any `InpV34Mode=1` run → the journal
  must print `F3 REPLAY FATAL: config_hash mismatch` and the EA must **fail INIT** (no
  orders). Restore the file (re-run the exporter with `--install`) → INIT succeeds and logs
  the two `F3 SYMMAP` lines +
  `F3 REPLAY: loaded 851013 rows, 31 symbols … hash=51a7541cc2aaa593 scale=10.0`.
- **G2b (long):** preset **`FED_G2_V34ONLY_S10.set`**, window **2020-01-02 → 2025-12-31**,
  Market Watch must additionally hold the **31 replay symbols (BROKER names)**:
  `AUDCAD AUDJPY AUDNZD BTCUSD CADCHF CADJPY DE40 ETHUSD EURCAD EURCHF EURGBP EURNOK EURNZD
  EURSEK EURUSD GBPJPY JP225 NZDCAD NZDJPY SOLUSD UK100 US30 US500 USDCHF USDJPY USTEC
  XAGUSD XAUUSD XBRUSD XNGUSD XTIUSD` — **the owner already verified this Market Watch
  complete against a terminal screenshot (2026-07-10)**: the two mapped names (`US500`,
  `DE40`) plus the 29 that match the repo names verbatim. Download tick history BEFORE the
  long run. PASS: CAGR ≥ **0.85 × 88.66%**; `volume_rejects=0`; equity-DD reported (feeds
  the v3.4 k — the COVID tail is the measurement, not a gate).
- **G2c (minutes):** any 1-week window with `FED_G2_V34ONLY_S10.set`; verify in the journal
  one `F3 REPLAY keep-last-good` on an empty hour, and in the deal list one **seasonal
  06:00** forced flatten and one **intraday 21:00** forced flatten (`FEXIT` rows in the
  decisions CSV).

## G3 — federation run (after G1 + G2 pass) — ~~SUPERSEDED 2026-07-10 by G3b~~

> **SUPERSEDED 2026-07-10:** contaminated run — v3.4 was silent through the COVID window (all-flat in-index hours held stale targets instead of flattening) + gold-cap/margin sizing artifacts (per-minute volume-reject spin, "No money" fills). Use **G3b** below. The dials/PASS invariants here still stand; only the underlying EA behavior was fixed.

1. Preset **`FED_IC.set`**, same account/model, window 2020-01-01 → 2025-12, Market Watch =
   the union (10 v7 symbols + 31 replay symbols; overlap makes 33 total).
2. Startup checks: `F3 init: v34mode=1 … v7=on fed=on V34Mult=0.4800`, replay loaded row.
3. **PASS (from `Common\Files\fma3_fed_books.csv` daily rows):**
   - `|residual| = |E_v7 + E_v34 − 10000 − acct_equity| ≤ 0.5% × acct_equity` at every
     daily mark;
   - every `REBAL` row in `fma3_fed_decisions.csv` has book equity (`extra` col) equal to
     the same-day `E_v7` books value — **no v34 P&L in any v7 seed**;
   - the v7 `REBAL`/`BAND` **dates match the G1 run's dates exactly** (anti-coupling; a
     diff is a FAIL unless traced to a shared-margin order rejection, which must be logged);
   - no (symbol, magic) touched by both layers (magics 360001-360012 vs 8400001-8400008,
     disjoint by construction, asserted at init).
4. **Report read (not pass/fail):** `python3 scripts/combine_tester_reports.py --v7 …`
   conventions vs the s=1.6 federation record (hrisk1: CAGR 170.2%, maxDD 22.58%, tail
   8.12%) → the federation k; `w_realized` drift-band watch (review trigger outside
   0.56–0.84).

## G3b — federation run, COVID-fixed EA (SUPERSEDES G3) — READY 2026-07-10

Independent adversarial review **PASS** (13/13 invariants C1–C13 verified against the ACTUAL
installed source + artifacts, no defects, no recompile needed). G1/G2 parity preserved
(the only sizing addition is strictly guarded by `if(InpSizingBase>0)`, default `0.0`).

### (a) WHAT CHANGED (plain language)
- **COVID silence fixed:** all-flat in-index hours now emit `__GRID__` sentinels (`fmt=2` CSV)
  so the v3.4 book actively **flattens** instead of holding stale targets — v3.4 trades again
  through Feb–Apr 2020.
- **No-money / volume spin killed:** a rejected same-direction add is held once (`F3 EXEC HOLD`)
  and not re-sent every minute until the target actually moves ≥1 step / flips / goes flat.
- **Account-aggregate volume clamp:** adds are sized against the summed same-direction volume
  across all of this EA's magics (foreign positions excluded); closes/reduces are never clamped.
- **Loud px SIZE-SKIP:** an un-priceable leg logs `F3 SIZE SKIP: <sym>` once per symbol/session
  and no-ops that leg (never fails INIT) — e.g. SOLUSD before its 2022 listing.
- **Fixed-base sizing** via `FED_IC_G3B.set` (`InpSizingBase=10000`): lots sized off a fixed
  base instead of live equity, so margin stays sane and P&L compounding can't starve sizing.

### (b) OWNER PRE-RUN ACTIONS
- Confirm the **SOLUSD Symbols-dialog floor at 2022-03-14 is EXPECTED/accepted** — one
  unfixable sleeve (SOL didn't exist pre-2022), excluded from the COVID window. It logs one
  `F3 SIZE SKIP: SOLUSD` and starts trading after 2022-03-14. This is not a defect.
- Ensure the tester uses the **ICMarketsEU-MT5-5 real-account dataset** (full 2020–25 history
  for all 31 symbols; 2020–22 = every-tick-from-M1). **NO bulk re-downloads needed.**
- The installed **`fmt=2` CSV must only be run by the freshly-compiled EA** — the
  **123,796-byte** `FableFederation_V1.ex5` at the Experts flat root. An older .ex5 cannot read
  the sentinels. (`.bak` fmt=1 rollback sits alongside the CSV in `Common\Files\`.)

### (c) RUN 1 — fast 1m-OHLC smoke (run this FIRST)
| Setting | Value |
|---|---|
| Expert | `FableFederation_V1` (Experts flat root, 123,796-byte .ex5) |
| Preset | **`FED_IC_G3B.set`** |
| Symbol / TF | **ETHUSD, M1** |
| Model | **1 minute OHLC** |
| Dates | **2020.01.01 → 2025.12.31** |
| Deposit | **EUR 10,000**, real account |
| Guardian | **OFF** |

Then the smoke checklist below — all items must pass before RUN 2.

### (d) RUN 2 — real-tick G3b (ONLY after RUN 1 passes)
Identical to RUN 1 except **Model = `Every tick based on real ticks`**. This is the deliverable:
federation real-tick DD/tail → fed-level k → final IC dial. Do **not** run this until RUN 1's
checklist is fully green.

### Smoke checklist (concrete, grep-able Journal/Experts checks)
- [ ] Init line shows **`fmt=2`**, and a **`F3 REPLAY span:`** line prints (`<first> .. <last> fmt=2`).
- [ ] **ZERO `keep-last-good` lines in Mar-2020** (allowed ONLY on weekend/warmup hours pre-Jun-2020).
- [ ] **≥1 `F3 REPLAY flat-hour`** line in Mar-2020 (the sentinel flatten firing).
- [ ] **v3.4-distinctive fills EXIST inside Feb–Apr 2020** — XAGUSD / XBRUSD / US30 / XTIUSD /
      DE40 / UK100 (…) trade in the COVID window. **This is the core COVID-fix proof.**
- [ ] **ZERO `[Volume limit reached]` per-minute spam** — any single reject is followed by
      exactly **ONE `F3 EXEC HOLD`** line, not a per-bar repeat.
- [ ] **ZERO `No money` lines** (fixed base).
- [ ] **`F3 SIZE SKIP: SOLUSD` appears exactly once pre-2022**, and SOL trades after 2022-03-14.
- [ ] **Margin Level stays comfortably >100%** throughout (fixed base).
- [ ] **Final equity sane and non-degenerate** (not blown, not flat/zero).

## G4 — guardian

- **G4a (no-op):** window 2020-01 → 2020-06, `FED_IC.set` (x=0) run twice: as shipped, and
  once with `if(!F3_GuardianPass()) return;` commented out in `OnTick` (build-time probe —
  recompile, run, **revert, recompile**, confirm `check_transplant.py` clean). PASS:
  identical `fma3_fed_decisions.csv` + final equity to the cent.
- **G4b (function):** same window, `FED_IC.set` with `InpDailyStopX=2.0`. PASS: on every
  server day where equity ≤ dayAnchor×0.98 — all positions (both magic ranges) flattened on
  that tick, `GUARD_STOP` row (anchor/equity) + `Alert`, zero order sends until the next
  server day, `GUARD_RESUME` at rollover, **no spurious REBAL on the stop day** (the flatten
  realizes P&L into the existing ledgers; band logic self-heals).

---

## Deviations from SPEC.md (deliberate, task-directed — read before auditing)

1. **Config hash = the FMA3 v1.0 pin hash `51a7541cc2aaa593`** (`strategy_fma3.config_hash()`,
   `fma3_v1_pin.json`) in both the replay header and the compiled `F3_V34_CONFIG_HASH` —
   supersedes SPEC §3's FMA2 book hash `48c09199fbf83d82` per the build-task amendment. The
   exporter still **hard-fails** if the FMA2 brain hash drifts from `48c09199fbf83d82` AND
   cross-verifies the matrix against the pinned `engine/books.py::build_v34_frac_1h()`
   (max diff measured 6.66e-16), so both drift guards remain.
2. **`InpV34Mode` enum {0=off, 1=replay, 2=live}** replaces SPEC §1's
   `InpEnableV34`+`InpV34TesterReplay` pair (task input set). The tester still FORCES the
   replay source at any non-off mode. Two file-name inputs are kept
   (`InpV34ReplayFile`/`InpV34LiveFile`) instead of a single `InpV34File` — the two sources
   live in different sandboxes (Common vs terminal Files) with different defaults.
3. **`InpWv7`/`InpScale` are informational**: OnInit logs a dial-consistency check
   (`InpRisk` vs `8·w·s`, `InpV34Mult` vs `(1−w)·s`) and the books log uses `InpWv7` for
   `w_realized`; they never touch sizing (convention A: the set dials govern — run-54
   fidelity).
4. **Seam 4.1 placement corrected** vs TRANSPLANT_V7.md §3: the `InpEnableV7=false` weight
   zeroing sits AFTER the `InpEqualWeight` block, not after the enable-flags block — the
   equal-weight math re-assigns S6/BTC weights from the enable flags, so the documented
   placement would have left S6+BTC trading at half-book each in v34-only mode.
5. **Guardian halt skips signal recomputes** until resume (the OnTick seam returns early,
   per TRANSPLANT §3), so SPEC §6's "signal recomputes still run" is not literal during a
   halt. A halt lasts at most one server day; the day-rollover recompute self-heals on
   resume; a mid-day 20:00/07:05 stamped recompute missed during a halt is recomputed the
   next day (log-visible, sub-day exposure).
~~6. **FTMO preset ships guardian OFF** (`InpDailyStopX=0.0`) pending FMA3-008, per the build~~ **SUPERSEDED 2026-07-10 20:30: FMA3-008 ADOPTED — FED_FTMO ships guardian ON, InpDailyStopX=3.0 (s=0.7, +54.0%, both drift probes clear). The preset is correct as-is.**
   task ("guardian defaults off pending FMA3-008"); SPEC §7's 3.0 was a placeholder. Both
   FTMO dials remain provisional (FMA3-009 walking s down as of tonight's log).
7. **`InpV34SymbolMap` (2026-07-10, owner fix):** new federation input, default
   `USA500=US500;DAX=DE40` — the replay CSV keeps repo symbol names and `V34Replay.mqh`
   translates repo→broker once at load; unknown/empty entries = identity; an unavailable
   mapped broker symbol fails INIT loudly. Mirrored + tested in
   `mt5/ea/tests/test_federation_units.py`.
8. **Input UI amendment (2026-07-10, owner fix):** the EA's ENTIRE input block was
   re-written for humans with `input group` sections and clear label comments
   (TRANSPLANT_V7.md §2.1). Names + defaults byte-identical to the parents (presets bind
   to names; G1 binds to defaults); comments/groups are display metadata with zero logic
   impact. `check_transplant.py` amended accordingly — still prints TRANSPLANT CLEAN.


---

## RESUME STATE (2026-07-10 21:40) — where we paused

- **G1 parity: PASS ×2** (pre- and post-symbolmap/UI patch): €388,368.75 net, RelDD 33.68%, to the digit.
- **G2a replay + symbol map: PASS** on ICMarketsEU-Demo (851013 rows, hash 51a7541cc2aaa593, USA500→US500, DAX→DE40, v3.4 trades fire).
- **BLOCKER for G2b/G3 — MT5 history for 8 v3.4 symbols (31% of the book):**
  history-sync-error on US30, DE40, XAGUSD, UK100, JP225, XTIUSD, XBRUSD, AUDCAD.
  On-disk check: 6 (US30/JP225/XTIUSD/XBRUSD/DE40/AUDCAD) HAVE data cached
  (27–194 MB, Demo base) — a sync/OHLC-mode hiccup; XAGUSD + UK100 genuinely
  lack Demo history (124 KB stubs on the wrong server base).
- **Unblock next session:** (1) restart MT5 (clears the 6 cached ones);
  (2) XAGUSD + UK100 — open M1 chart, Home, scroll to 2020 to force download;
  (3) re-run the G2a smoke — zero sync errors ⇒ run G2b (real ticks, 2020–25),
  then G3 (FED_IC.set) for the federation k → final IC dial.
- Erroring symbols carry trend_v2 + carry_breakout (silver 7%, WTI 6.9%,
  Brent 6.6%, US30 3.5%, DAX 3.2%, JP225 3%, UK100 2.9%, AUDCAD 1.4%) — cannot
  be skipped.


## UPDATE 2026-07-10 21:40 — data unblocked, G3 running

- Demo lacked history for 8 v3.4 symbols (31% of book). SWITCHING TO THE REAL
  ACCOUNT (ICMarketsEU-MT5-5, tester is still simulation-only) gave full 2020-25
  history for all 31 symbols. Real TICK data begins ~2023; 2020-22 uses
  'every tick generation' from M1 bars (same as v7 runs 53/54).
- **G2a PASS (real acct):** full v3.4 book traded, 851013 rows, hash match,
  symbol map (USA500->US500, DAX->DE40) applied, 0 volume_rejects, Jan-2021
  smoke final EUR 11,285.
- **G3 RUNNING:** FED_IC.set (v7+v3.4 fed, s=1.6, guardian off), 2020-01..2025-12,
  real ticks, EUR 10k. This is the deliverable → federation real-tick DD/tail →
  fed-level k → final IC dial re-pick. Compare vs record pin: CAGR +101.4%*/DD
  15.73%/tail 5.36% (*record s=1.1; the record @ s=1.6 = fma3_v1... actually the
  v1.0 pin is s=1.1; the s=1.6 record is in hrisk1 base = +170.2%/22.6%).
- NOTE: cross-server consistency — v7 runs 53/54 were on demo; G3 on real. Minor
  spec differences; the federation k is taken from G3 (self-contained, both books
  in one run) so it is internally consistent.
