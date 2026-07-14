# S1 STATUS — R1 whole-book compute gate (TestBook, frozen six-field bundles)

**Date:** 2026-07-14 · **Design of record:** `FABLEBOOKNATIVE_DESIGN.md` (FABLE REVISION v2
block WINS) + `FABLEBOOKNATIVE_WIRING_LENS1.md` + `S0_STATUS.md` · **Ledger:** each owner
terminal run below gets a dated `FMA3-RECON-N` entry in
`research/protocol/RECONCILIATION.md` before anything advances.

---

## THE R1 MIRROR NUMBER

```
max|diff| = 5.0604e-13   (gate: <= 1e-12; rows over gate: 0)
805,585 / 805,585 rows structurally IDENTICAL (805,183 data + 402 __GRID__ sentinels)
```

**R1 MIRROR GATE PASS.** The assembled native compute chain — H1 signals (8 Sat sleeves +
Ensemble → `f_sat[31]`; CoreSim `ComputeFCore` → `f_core[8]`), M1 equity (`a` = CoreSim
combined eqc segment-batch, `b` = SatEquityNative on the HELD prior-hour `f_sat` targets),
H1 blend (BookBlend on asof-sampled `a_h`/`b_h`) — reproduces the golden RECON-4-pinned
stream `research/outputs/mt5/FMA3_fed_frac_v3.csv` (sha256
`d00b614b650b649ac9301b1ffd1eae66af4785ce4417bfa91755d367f8ab452e`, re-verified against the
installed Common-Files copy today) on frozen inputs.

**Honest framing — read before celebrating:**

1. **This number was produced by the python statement mirror**
   (`research/bpure/book/book_orchestrator_sim.py`, UNIT 3 python half, runtime 237.4 s,
   report `research/bpure/book/book_mirror_parity.json`), consuming the SAME installed
   Common-Files bundles the in-terminal twin reads. The MQL5 binary has **not** run the
   assembled chain yet — `TestBook.mq5` is compiled + installed and its run is **STAGED**
   (terminal not launched per constraints). The MQL5 language layer is bounded by sibling
   precedent (RECON-8b/8d: ≤4.2e-14 / bitwise) — precedent, not a measurement of this chain.
2. **38 rows exceed the 5e-13 half-ulp quantization bound** (`within_quant_bound = false`):
   this run passes the 1e-12 gate cleanly but does NOT earn the stricter
   "as-good-as-bit-exact" grade the judge tracks (Track-C precedent). All 38 trace to the
   known **4.2e-14 f_sat harness residual** (RECON-8b) landing next to 12dp golden rounding
   boundaries — the residual tips which side of the rounding step the 12dp golden falls on.
3. argmax row: `epoch 1641837600, USTEC` — actual `0.51429446766950604` vs golden (12dp)
   `0.514294467669`.

| Metric (all from `book_mirror_parity.json`, MEASURED) | Value |
|---|---|
| rows actual / golden | 805,585 / 805,585 (structural_ok = true, first_divergence = none) |
| data rows / sentinels | 805,183 / 402 (sentinels match golden exactly) |
| max\|diff\| / gate / rows over | 5.060396546241464e-13 / 1e-12 / **0** |
| rows over 5e-13 quant bound | 38 (see honest framing #2) |
| H1 union bars / hours emitted | 49,379 / 49,379 |
| M1 bars (b engine) / core union bars | 2,948,650 / 2,947,085 |
| f_core rows | 49,355 (matches the S0 frozen hourly grid) |
| a_first / b_first | 10,000 / 10,000 |
| core final eqc | 532,229.8433634703 — **bit-equal to the export-report pin** |
| b final eq / balance / trades | 449,707.7452664526 / 434,132.98905617336 / 20,403 — **endstate bit-equal to the frozen-tgt chain** |
| held-target ring vs frozen tgt column | max\|diff\| 4.196643033083092e-14 (40,905 probes differ; the RECON-8b residual class, diagnostic only — b consumed the HELD ring, not the frozen column) |
| ring depth violations / trailing hazard minutes | 0 / 0 |

---

## Per-unit build & compile results (all wine-compiled, logs kept)

| Unit | Location | Measured status |
|---|---|---|
| **UNIT 1 — `CBookOrchestrator`** (the whole-book per-bar glue: three-clock drive contract, H1 ffill/daily-queue driver, deferred SeasonalCrypto emit, blend, `export_book_frac_v3::build_rows` emission semantics; ZERO trading calls, ZERO CTrade, ZERO file I/O) | `mt5/ea/Include/Book/BookOrchestrator.mqh` | compiled **0 errors / 0 warnings** via `checks/CheckBookOrchestrator.mq5` (18,280 ms; `checks/CheckBookOrchestrator.log`) |
| **UNIT 3 (python half) — statement mirror** | `research/bpure/book/book_orchestrator_sim.py` | **RUN + PASS** — the R1 mirror number above; consumes ONLY the installed bundles (components copied/imported from the individually-proven Wave-1/2/3 code, no NSF5 imports) |
| **UNIT 3 (in-terminal twin) — `TestBook.mq5`** (Script, OnStart, zero trading functions; reads the 4 bundle families from `FILE_COMMON`, writes `FMA3_book_actual.csv`, prints an in-script golden diff) | repo `mt5/ea/scripts/TestBook.mq5`; installed `MQL5/Scripts/TestBook.{mq5,ex5}` | compiled **0 errors / 0 warnings** (3,460 ms; verify recompile 0/0, 3,246 ms — `TestBook.log`, `TestBook_verify.log`). **Run STAGED** |
| **Judge — `validate_book_stream.py`** (structure + values, quantization-aware, exit 0/1) | `research/bpure/book/` | ready; already exercised as the mirror's judge (report above) |
| **`CheckFCore.mq5`** (deferred from S0) | installed `MQL5/Scripts/CheckFCore.{mq5,ex5}` | compiled **0 errors / 0 warnings** (11,734 ms; `CheckFCore.log`). **S0 finding V2 is CLEARED** — the CoreSim segment bundle is back on the prefix (installed 18:20–18:26 today). **Run STAGED** |

## Bundles — PASS (orchestrator-verified, 9.313 GB installed to Common Files)

All 4 bundle families regenerated/verified today with **every built-in bitwise assert
green**; golden sha256 confirmed == RECON-4 pin (independently re-hashed on the installed
copy).

| # | Bundle | Contents | Built-in verification (MEASURED) |
|---|---|---|---|
| 1 | Master H1 signal bundle | `FMA3_v34_inputs.csv` (23,683,879 B) — H1 closes, 37 symbols | header/format asserted by exporter; drives the RECON-8b-proven sleeve chain |
| 2 | CoreSim segment bundle | `FMA3_coresim_segments.csv` manifest + `FMA3_coresim_seg{0..31}.csv` + 32 golden CSVs + 32 expected-state JSONs (20,950,676 input rows) | `coresim_export_report.json`: **all 32 segments** replay_index_equal + bit_equal eqc/eqw/margin + golden_csv_bit_equal_parquet = true, `all_replay_pass: true`; seed chain INIT 10,000 → final_eqc 532,229.8433634703 |
| 3 | b_h quarter bundles | `FMA3_bh_{inputs,golden,state_in,state_expected}_{2020Q1..2025Q4}` (24 quarters, six-field float32-quantized per BH_ENGINE_SPEC §7) | exporter built-in asserts green (v2 item 5(i): assembler f32 quantization == exporter, or b's bit-parity is unreachable) |
| 4 | Golden stream | `FMA3_fed_frac_v3.csv` (26,574,582 B) | sha256 `d00b614b…8ab452e` == RECON-4 pin — **re-verified** |

---

## Verifier verdict — unsoftened

> **R1 MIRROR GATE PASS** — the assembled native chain reproduces the golden
> `FMA3_fed_frac_v3.csv` stream: 805,585/805,585 rows structurally IDENTICAL (incl. all 402
> sentinels), max|diff| = 5.0604e-13 ≤ 1e-12 (0 rows over the gate; 38 rows over the 5e-13
> quantization bound, all traced to the known 4.2e-14 f_sat harness residual landing next
> to 12dp rounding boundaries). TestBook.mq5 wine-compiled 0 errors / 0 warnings and
> installed; the in-terminal run is STAGED (terminal not launched per constraints).

Findings, spelled out:

- **V1 — R1 is mirror-proven, not terminal-proven.** Every number above is python. The
  in-terminal TestBook run is what closes the MQL5 language layer for the *assembled*
  chain. Sibling components measured that layer at ≤4.2e-14/bitwise (RECON-8b/8d), so risk
  is low — but it is not zero and it is not yet measured here.
- **V2 — not "as good as bit-exact."** `within_quant_bound = false` (38 rows > 5e-13). The
  PASS is on the 1e-12 gate. The 38 rows are the f_sat 4.2e-14 residual interacting with
  12dp rounding, not a new error source — but the stricter grade was NOT earned and the
  terminal run inherits the same residual.
- **V3 — internal cross-pins all green:** core final eqc bit-equal to the export-report
  pin; b endstate bit-equal to the frozen-tgt chain; ring depth violations 0; trailing
  hazard minutes 0; held-ring vs frozen-tgt diagnostic at the known 4.2e-14 class.
- **V4 — scope: frozen inputs only.** S1 proves ORCHESTRATION + COMPUTE. It does not prove
  the live feed (S0 proved that), the live Core leg-target source (S2), or execution
  (S2/S3). See the scope pin below.

---

## S1 SCOPE PIN

The Core leg targets consumed in S1 are the **FROZEN `tgt` column of the CoreSim segment
bundles**. The **live** Core leg-target source — CoreEngine's proven live signal path,
running compute-only next to the book (the `CTrade` include collision is deferred there) —
is **S2/S3 work**. Likewise: `a` runs SEGMENT-BATCH per the frozen band-trigger segments
(v2 item 2 — no streaming wrapper; the `FinishSegment` first-value backfill is a
leading-edge lookahead a forward streamer cannot compute), and `b` consumes the HELD
prior-hour `f_sat` targets per the bh_stepper lag law. Nothing in S1 touches execution,
warm-start, or the tester.

---

## OWNER RUN-SHEET (both bundles now staged — no re-export needed)

Common Files dir (all CSVs land here):
`~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files/`

**Run (i) — TestBook (the R1 in-terminal close)**
1. In the terminal: run Script **TestBook** on any chart (OnStart, zero trading calls). It
   reads all 4 bundle families from Common Files, chains the 32 CoreSim segments, streams
   the 24 b_h quarters, drives the H1 chain, and writes `FMA3_book_actual.csv` while
   diffing against the golden in-script. If it prints
   `TestBook: STAGED — input bundles not found` the bundles are missing — stop and report.
2. Expected Journal milestones: `TestBook: core feed done — 32 segments, 49355 f_core rows …`;
   per-quarter `TestBook: M1 quarter <Q> opened (b bal=… trades=…)`; final line
   `DONE TestBook: PASS (structural OK, max|d|=<…> vs tol 1e-12, …)`.
   The python mirror predicts max|d| ≈ 5.06e-13; any additional MQL5-layer drift should be
   in the ≤4.2e-14 class. `FAIL` or `*** STRUCTURAL DIVERGENCE ***` = record verbatim, do
   not rationalize.
3. Judge (authoritative, outside the terminal):
   ```bash
   CF="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
   cd /Users/dsalamanca/vs_env/FableMultiAssets3
   python3 research/bpure/book/validate_book_stream.py "$CF/FMA3_book_actual.csv" \
       --report research/bpure/book/book_terminal_parity.json
   ```
   **PASS = exit 0**: 805,585 rows structurally identical + max|diff| ≤ 1e-12. The report
   JSON is the artifact to ledger.

**Run (ii) — CheckFCore (deferred from S0, now unblocked)**
1. Run Script **CheckFCore** (any chart; reads the manifest + 32 segments from Common
   Files, chains them with the seam carry, writes `FMA3_fcore_actual.csv`).
2. Judge:
   ```bash
   cd /Users/dsalamanca/vs_env/FableMultiAssets3
   python3 research/bpure/coresim/validate_mql5_fcore.py
   ```
   **PASS = exit 0**: index equal + 8/8 f_core columns bit-equal after the %.17g
   round-trip; writes `fcore_mql5_parity.json`.

**Record both outcomes** as dated `FMA3-RECON-N` ledger rows (Script replays, no trades —
RECON-8b/8c/8d convention). Run (ii) closes the last un-terminal-proven component; run (i)
closes R1 in-terminal.

---

## What S2 needs

Per the revised stage plan (FABLE REVISION v2): **S2 = seam + execution on frozen
`g_fedTgt` (RECON-4 position-level reproduction).** Concretely, in order:

1. **Both staged runs above executed and ledgered.** R1 is not closed until the terminal
   twin's number is on record; any structural divergence reopens S1.
2. **Seam wiring:** feed golden `g_fedTgt` into `FED_Reconcile`; reproduce RECON-4 at
   position level (held == `book_frac·s`, median ratio 1.000; execution stack unchanged).
   The live `g_fedTgt` writer must reproduce the exporter's flatten-by-omission /
   `__GRID__` semantics at the seam (v2 item 5(ii)).
3. **Live Core leg-target source** (the S1 scope-pin debt): wire CoreEngine's proven live
   signal path compute-only beside the book, resolving the `CTrade` include collision
   deferred from S1 — replacing the frozen `tgt` column as `a`'s input, with a
   frozen-vs-live tgt parity check before it carries weight.
4. **State-integrity items pulled forward** (v2 item 5(v)): ≥12-sig-digit atomic state
   serializer replacing the 4-decimal `SaveState`, and refuse-to-trade on any `j`-splice
   discontinuity — a re-based `a`/`b` passes every self-check while silently mis-weighting
   every trade; this is the highest-severity silent failure in the design.
5. Each terminal run → dated `FMA3-RECON-N` entry before the next step.
