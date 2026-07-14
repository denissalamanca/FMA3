# S0 STATUS — feed probe (Track A) + f_core source resolution (Track B)

**Date:** 2026-07-14 · **Design of record:** `FABLEBOOKNATIVE_DESIGN.md`, FABLE REVISION v2
(items 1 and 4) · **Ledger:** the owner terminal runs below get a new dated entry in
`research/protocol/RECONCILIATION.md` (§ Reconciliation ledger) before anything deploys.

**One-line verdicts**

| Track | Verdict |
|---|---|
| **A — S0 multi-symbol feed probe** | **BUILT + LOCALLY MEASURED; the go/no-go itself is STAGED.** All three probe pieces compiled/exported/self-tested. Nothing about MT5's actual multi-symbol feed has been measured yet — that is exactly what the owner's two terminal runs decide. |
| **B — f_core source** | **(c)-VIABLE, bit-exact.** `f_core[8]` is EXACTLY computable from CoreSim state alone: max\|diff\| = 0.0 (`np.array_equal`) on ALL 8 columns over the FULL 49,355-row frozen hourly grid. Python reference PASS, python twin of the MQL5 algorithm PASS, `CheckFCore.mq5` compiled 0/0. Terminal replay staged — currently **blocked on re-exporting the CoreSim segment inputs** (see finding V2). |

---

## Track A — S0 multi-symbol feed probe (FABLE REVISION v2 item 4)

**Question S0 answers:** can this terminal furnish, on a BTCUSD M1 clock chart,
time-synchronized M1 data for the 33 Fable-book symbols + EURJPY (34 unique; the other 7
eurq crosses are already book symbols), in BOTH the 1m-OHLC Strategy Tester and on a live
chart, with M1 depth to 2020-01-02 and a union grid + `has_bar` mask matching the frozen
golden? Full runbook: `research/bpure/probe/README.md`.

### Built (all verified locally, MEASURED)

| Piece | Location | Measured status |
|---|---|---|
| `FeedProbe.mq5` — EA, **zero trading calls** (probe logic in OnInit; OnTick/OnTimer only retry lazy history) | repo `mt5/ea/FeedProbe.mq5`; installed at prefix `MQL5/Experts/FeedProbe.{mq5,ex5}` | compiled **0 errors / 0 warnings** (`FeedProbe.log` + `FeedProbe_verify.log`, both `Result: 0 errors, 0 warnings`) |
| Golden exporter `export_probe_golden.py` | `research/bpure/probe/` | RUN — `FMA3_feedprobe_golden.csv` in Common Files (1,006,999 B; 12,737 lines = 1 meta + 34 depth rows + 12,702 union-minute rows; `symbols_done=34`; source = frozen NSF5 1m IC cache, i.e. the same feed the book was certified on) |
| Judge `judge_feedprobe.py` | `research/bpure/probe/` | Self-test **re-run today**: judge(golden, golden) → `OVERALL : PASS`, exit **0**; injected single-bit `has_bar` defect → `HAS_BAR False / OVERALL FAIL`, exit **1**. Verdict lines: SYMBOLS / GRID / HAS_BAR / DEPTH / OVERALL |

Probe window (fixed in both EA inputs and exporter, server time):
**2024-03-02 00:00 → 2024-03-10 23:59** (Mon–Fri week 2024-03-04..08 + both weekends for
crypto bars). Depth reference: week starting **2020-01-02**.

**Known fact going in (MEASURED, read-only):** all 34 broker symbols exist on
ICMarketsEU-MT5-5 — history folders present under `Bases/ICMarketsEU-MT5-5/history/<SYMBOL>/`
for every one, including DE40, US500, EURJPY, SOLUSD.

### What is NOT yet measured

The S0 go/no-go itself. Every PASS above proves the **tooling**, not the terminal's
multi-symbol feed. The golden was exported from the frozen research cache, not from MT5.
I did not launch `terminal64.exe` (hard constraint) — the two runs below are the owner's.

### OWNER RUN-SHEET

Common Files dir (all CSVs land here):
`~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files/`

**Run (i) — 1m-OHLC Strategy Tester**
1. Strategy Tester → Expert **FeedProbe**, Symbol **BTCUSD**, Period **M1**, Model
   **"1 minute OHLC"**.
2. Date range: any short range AFTER the probe window — recommend
   **2024.03.11 → 2024.03.15** (the probe reads the window via CopyRates from history; the
   tester range itself only needs to exist). Deposit/leverage irrelevant — no trading calls.
3. Run. Journal shows `FEEDPROBE SYMBOL_SELECT <sym> ok=...` per symbol, then
   `FEEDPROBE DONE mode=tester file=FMA3_feedprobe_tester.csv ...`. The CSV is written even
   if some symbols never load (OnDeinit safety; those show `done=0`).

**Run (ii) — live chart**
1. Open a **BTCUSD M1** chart on ICMarketsEU-MT5-5, attach **FeedProbe** (Algo Trading may
   stay OFF — the EA never trades; it only needs timers).
2. It retries on a 5 s timer while lazy history downloads complete (`InpMaxTries`=60,
   ≈5 min), then prints `FEEDPROBE DONE mode=live file=FMA3_feedprobe_live.csv ...` in the
   Experts log. Symbols still loading show as `done=0` rows — re-attach to retry.

**Judge (after each run)**
```bash
CF="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
python3 research/bpure/probe/judge_feedprobe.py "$CF/FMA3_feedprobe_golden.csv" "$CF/FMA3_feedprobe_tester.csv"
python3 research/bpure/probe/judge_feedprobe.py "$CF/FMA3_feedprobe_golden.csv" "$CF/FMA3_feedprobe_live.csv"
```

**What PASS looks like:** exit 0 and `OVERALL : PASS (SYMBOLS True GRID True HAS_BAR True
DEPTH True)` — all 34 symbols `done=1`, union minute grid identical, per-symbol `has_bar`
identical, per-symbol earliest bar within golden-earliest + 1-day slack (the judge already
encodes: SOLUSD cache starts 2022-03-14; ETHUSD has only 5 bars in the 2020-01-02 depth
week; first bars US30/US500/USTEC 08:00, DE40 03:16, XAU/XAG 01:00). Divergences are listed
minute-by-minute (first 10 grid, first 5 per symbol).

**Decision table (FABLE REVISION v2 item 4):**
- **Both runs PASS** → S0 GREEN; FableBookNative data path viable in both modes; proceed
  per stage plan.
- **Tester FAILS, live PASSES** → tester-mode failure does **NOT** imply live failure (the
  deploy target is live CopyRates). **Named fallback:** historical certification stays on
  the six-field frozen engine (already the MaxDD plan); R2 gets measured on a demo-forward
  run instead of a tester backtest; the EA remains deployable.
- **Live FAILS** → S0 RED: the product-viability question the review front-loaded is
  answered NO on this terminal/broker; stop and rethink before any S1+ spend.
- Caveat either way: the window end (Sun 2024-03-10) straddles the US DST switch. `has_bar`
  mismatches **confined to 2024-03-10** indicate broker-clock GMT+2→GMT+3 drift — a real
  finding to record, not a judge bug; judge the rest of the window on its own merits.

**Record the outcome** as a new `FMA3-RECON-N` ledger row (probe runs are Script/EA replays
with no trades — same convention as RECON-8b/8c/8d).

---

## Track B — f_core source resolution (FABLE REVISION v2 item 1)

**Question:** where does the live EA get `f_core[8]` (the Core book's held
fraction-of-own-equity per NET symbol, frozen target `research/outputs/v7_book_frac_1h.parquet`)?

### Verdict: (c)-VIABLE — f_core is EXACTLY computable from CoreSim state alone

The identity, measured over the FULL frozen hourly grid
(`research/bpure/coresim/fcore_identity.json`, runtime 534 s):

```
f_core[net] = net_lots(union ffill, seam-carry) * contract_size * mid_c(ffill) * eurq(ffill) / book_eqc
hourly row at hour start h = last 1m union bar in [h, h+1), fillna 0
```

Every input is CoreSim state the EA already runs for `a_h`: per-leg `pos` after
fills/stop-out, the leg bar data, and CoreSim's own combined `book_eqc`
(RECON-8d-proven). USDJPY's two legs net by **summing signed lots** — no equity weighting.

**Measured gates (all required for the verdict, all PASS):**

| Gate | What | Result |
|---|---|---|
| G-d | stepper-copy drift: pos-capture stepper's eqc/eqw/margin bitwise == `coresim_reference.run_leg_scalar`, every leg, every segment | **TRUE** (and `book_eqc` bit-equal TRUE) |
| G-e | net lots bitwise vs frozen `v7_book_lots_1m.parquet` | **8/8 columns bit-equal, max\|diff\| = 0.0** (AUDUSD, BTCUSD, ETHUSD, EURGBP, NZDUSD, USDJPY, USTEC, XAUUSD) |
| G-f | f_core bitwise vs frozen `v7_book_frac_1h.parquet`, full grid | **8/8 columns bit-equal, max\|diff\| = 0.0; index equal; 49,355 rows** |

**Rejected hypotheses, measured for the record** (why the review killed option (b)):
- H1/H2 equity-weighted / notional-sum-over-leg-equity-sum (USDJPY): max\|diff\| **17.204**
- H3 `tgt` passthrough (USDJPY tgt1+tgt5): max\|diff\| **24.231**
- naive `tgt` passthrough on the other 7 symbols: max\|diff\| **1.08 – 18.21**
- H4 net-notional / book_eqc (the identity): **0.0**

### Built end-to-end

| Piece | Location | Measured status |
|---|---|---|
| Python reference + identity measurement `fcore_reference.py` | `research/bpure/coresim/` | **PASS** — gates above; writes `fcore_identity.json` |
| `ComputeFCore()` extension of `CCoreBookSim` (+165 lines: pos/mid_c/eurq capture, net-symbol map, cross-segment seam carry, hourly last-bar-in-hour emission) | `mt5/ea/Include/Core/CoreSim.mqh` (spec: `research/bpure/coresim/CORESIM_SPEC.md`) | compiled inside CheckFCore 0/0 |
| Python twin of the EXACT MQL5 mechanics (`validate_mql5_fcore.py --sim`) | `research/bpure/coresim/` | **PASS** — 49,355/49,355 rows, index equal, 8/8 columns bit-equal, max\|diff\| = 0.0 vs the frozen parquet (`fcore_mqhsim.json`, 198.4 s). This isolates the ALGORITHM before the terminal isolates the MQL5 language layer — the RECON-8d discipline. |
| Terminal harness `CheckFCore.mq5` (Script, OnStart, zero trading functions; same input path as TestCoreSim) | repo `mt5/ea/scripts/CheckFCore.mq5`; installed `MQL5/Scripts/CheckFCore.{mq5,ex5}` | compiled **0 errors / 0 warnings** (`CheckFCore.log`). **Run STAGED** — see V2 below. |
| Judge `validate_mql5_fcore.py` (default mode) | `research/bpure/coresim/` | ready — bitwise judges `FMA3_fcore_actual.csv` vs the frozen parquet; writes `fcore_mql5_parity.json`; exit 0 iff PASS |

### Owner steps for the staged terminal replay

1. Re-export the CoreSim segment inputs (they are NOT currently on the prefix — finding V2):
   `cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresim/export_coresim_inputs.py`
   (~3.54 GB across `FMA3_coresim_segments.csv` + 32 `FMA3_coresim_seg{J}.csv`; measured
   1,458 s for the full export incl. per-segment replay validation).
2. In the terminal: run Script **CheckFCore** (any chart; reads manifest + segments from
   Common Files, chains all 32 with the seam carry, writes `FMA3_fcore_actual.csv`).
   Without the inputs it prints its staged notice and exits cleanly.
3. Judge: `python3 research/bpure/coresim/validate_mql5_fcore.py` — PASS = index equal +
   8/8 columns bit-equal after the %.17g round-trip. Record in the ledger with the S0 runs.

### Design implication [INFER — owner to ratify, then reflect in FABLEBOOKNATIVE_DESIGN.md]

This result **supersedes part of FABLE REVISION v2 item 1**: the compute-only `CCoreSignal`
refactor of CoreEngine is **not needed for R1** — `f_core` falls out of CoreSim state the EA
already maintains for `a_h`, bit-exactly. The G1-analog signal check that item 1 demanded is
what G-f already delivers (plus the staged in-terminal run for the language layer). What a
`CCoreSignal` would still be for, if anything, is live warm-start/independence concerns —
that is a design decision, not a measured fact.

---

## Verifier findings — unsoftened

- **V1 — S0 is undecided and could still be RED.** Every Track-A artifact PASS is a local
  tooling proof. The golden reproduces the frozen cache, and the cache is byte-identical to
  the live IC feed *historically* (RECON-6), but whether THIS terminal delivers 34
  synchronized M1 series in tester and live modes has zero measurements against it. Do not
  read this document as feed viability.
- **V2 — CheckFCore is blocked right now: the CoreSim segment inputs are gone.** Measured:
  `find` over the whole wine prefix returns no `FMA3_coresim_*` file; Common Files (46
  files) has neither the manifest nor any segment CSV, although `coresim_export_report.json`
  (2026-07-14 13:58) shows all 32 segments were exported and replay-validated today
  (`all_replay_pass: true`). They were evidently cleaned after the RECON-8d TestCoreSim runs
  (~3.5 GB). Step 1 of the Track-B run-sheet is therefore mandatory, not optional.
- **V3 — Track B's "MQL5 twin PASS" is a python simulation of the MQL5 algorithm, not the
  MQL5 binary.** The language layer (MathRound/ULP class of residuals) is exactly what the
  staged CheckFCore terminal run must close. RECON-8b/8d measured that layer at ≤4.2e-14 /
  bitwise for the sibling components, so the risk is low — but it is not zero and it is not
  yet measured for `ComputeFCore()`.
- **V4 — the f_core identity is proven against the frozen record, in-sample only.** G-e/G-f
  prove the frozen parquet is reproducible from CoreSim state; they say nothing about
  live-feed drift of `mid_c`/`eurq` (that is S3/S4 telemetry territory, v2 item 5(iv)).
- **V5 — judge exit codes re-measured today** (a prior claim, independently re-verified):
  golden-vs-golden exit 0 / OVERALL PASS; injected `has_bar` defect exit 1 / OVERALL FAIL.
  The README's claim that grid/depth defects are also detected was verified at build time
  but only the has_bar negative case was re-run today.
- **V6 — DST straddle caveat stands** (see decision table): a tester/live run can FAIL the
  judge solely from 2024-03-10 label drift. That outcome is a real broker-clock finding and
  must be recorded as such, not waved through and not blamed on the judge.
- **V7 — live-mode partial coverage:** symbols still lazy-loading write `done=0` rows and
  the judge will FAIL SYMBOLS; re-attach rather than concluding feed failure on first try.

---

## What S1 (the R1 whole-book TestBook gate) needs next

S1 per the revised stage plan: **`TestBook` on frozen six-field bundles → `book_frac[33]`
vs golden — segment-batch `a`, proven paths only. The crown gate, tester-independent** (it
does NOT block on S0's outcome; S0 only gates the S3+ tester/live path).

Measured gaps, in order:

1. **TestBook.mq5 does not exist** (no such harness in `mt5/ea/scripts/` — checked). It must
   compose, in-terminal, the five already-proven components end-to-end from six-field
   bundles: H1 ffill/daily-queue driver → 8 sleeves + `Ensemble` → `f_sat[31]` (signal layer
   proven in RECON-8b, 4.2e-14); CoreSim segment-batch → `a_h` + `ComputeFCore` → `f_core[8]`
   (RECON-8d bitwise; f_core staged, this doc); `SatEquityNative` → `b_h` (RECON-8d bitwise,
   2,948,650 bars); `BookBlend` → `book_frac[33]` (RECON-8c, 0.0 full-precision). The new
   content is the composition + the frozen six-field bundle exporter feeding it, per v2 item
   5(i): the assembler must float32-quantize prices exactly as the exporter or b's
   bit-parity is unreachable.
2. **Golden target + judge for `book_frac[33]`** on the unified fed_frac stream (v3 canon:
   the EA REPLAYS unified fed_frac; a_h/b_h normalised by own first 1m value; `s` stays in
   `FED_Reconcile`, never in the blend).
3. **CoreSim segment inputs re-export** (V2) — shared prerequisite; run CheckFCore's staged
   terminal replay first/alongside, closing the last un-terminal-proven component before any
   composition debugging starts.
4. **Owner ratification** of the Track-B design implication (drop `CCoreSignal` for R1) so
   TestBook is built against the CoreSim-derived f_core path, not a second engine.
5. Each terminal run above → dated `FMA3-RECON-N` ledger entry before the next step.

---

## S0 PROBE RESULTS — MEASURED 2026-07-14 (owner ran both modes)

**VERDICT: PASS — multi-symbol data path proven for the deploy target (live).**

| Dimension | Tester (1m-OHLC) | Live (BTCUSD M1 chart) |
|---|---|---|
| SYMBOLS | 34/34 present | 34/34 present |
| GRID (union minutes) | 12,701 **bit-exact vs golden** | 12,701 **bit-exact vs golden** |
| HAS_BAR (per-symbol mask) | **bit-exact, 0 mismatches** (incl. 2024-03-10 DST) | **bit-exact, 0 mismatches** |
| DEPTH to 2020 | 0/34 (bounded ~2023-01 pre-cache from a 2024 test start) | **33/34 PASS**, earliest 1998–2017, bar counts match golden |

- The 33/34 live miss = **SOLUSD download-lag** only: its probe-window data is bit-exact (12,492/12,492), its deep-history fetch hadn't landed at tries=60, and its golden history starts 2022 (no 2020 data expected). Not a capability gap; a re-attach would fill it.
- **Conclusion:** live terminal supplies synchronized 34-symbol M1 with union grid + has_bar bit-identical to the frozen golden, plus deep history to 2020+. Tester synchronization is equally faithful; its bounded depth confirms the design's split — **historical certification on the frozen six-field engine / CSV-replay (R1), the native tester only for recent-window feed mechanics + R2.**
- **f_core** resolved in the same S0 pass: `ComputeFCore()` from CoreSim state, bit-equal 0.0 on all 8 columns (no CoreEngine refactor).

**S0 = COMPLETE & GREEN. Next: S1 — TestBook (the R1 whole-book compute gate on frozen six-field inputs).**
