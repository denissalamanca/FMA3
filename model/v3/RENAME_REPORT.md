# Core / Satellite rename — final sweep + verification report

**Branch:** `rename/core-satellite`  **Date:** 2026-07-14
**Glossary of record:** [`NOMENCLATURE.md`](../../NOMENCLATURE.md) (owner-approved 2026-07-14)
**Arbiter:** the two parity gates below — the rename is accepted only because it
changed **zero numbers**.

This report is the FINAL SWEEP audit over the three parallel rename streams. It
records scope, the residual audit, and the re-measured gate numbers proving the
rename is numerically inert.

---

## 1. Scope — what was renamed

The rename retired the legacy `v7` / `v34` / `federation` lineage on the
**canonical Core/Satellite book chain** and its documentation, per the
`NOMENCLATURE.md` old→new map. It was applied in three streams:

| Stream | Surface | Files changed | Stream gate | Iters |
|---|---|---|---|---|
| 1 — Python + JSON | steppers, parity, engine, scripts, model/v3 canonical, exporters | 46 | book max\|diff\| `4.196643e-14`, 0 cells >1e-12, PASS | 1 |
| 2 — MQL5 + presets | EA includes, EA source, `.set` presets | 42 | 9 `Check*.mq5` + `TestV34Native.mq5` recompiled headless = **0 errors / 0 warnings** each; in-terminal book parity `4.197e-14`, PASS | 1 |
| 3 — docs | `docs/**`, `model/v3/*.md`, `ROADMAP`, `README` | 46 | 550 internal links checked, 0 broken | 3 |

**Representative renames (live identifiers / artifacts):**

- Python: `static_fed`→`static_blend`, `fed_frac`→`book_frac`, `frac7/frac34`→`core_frac/sat_frac`, `f7/f34`→`f_core/f_sat`, `w_v7`→`core_weight` (var), `build_v34_frac_1h`→`build_sat_frac_1h`; files `feed_prov_fed.py`→`feed_prov_book.py`, `export_fed_frac_v3.py`→`export_book_frac_v3.py`, `export_v34_replay.py`→`export_sat_replay.py`.
- MQL5 dirs: `Include/FMA3v2/`→`Include/Core/`, `Include/FMA3v34/`→`Include/Sat/`, `Include/FMA3v3/`→`Include/Book/`; classes `V7Core/V7Sim`→`CoreEngine/CoreSim`, `CV34…`→`CSat…`, `Fed…`→`Book…`; EA `FableFederation_V3.mq5`→`FableBook.mq5`.
- Presets: `FED_V3_IC*/FTMO*`→`FABLE_IC*/FTMO*`, `…_V7ONLY/_V34ONLY`→`…_CORE_ONLY/_SAT_ONLY`.

**Verified clean (0 legacy tokens):** `mt5/ea/FableBook.mq5`, `mt5/ea/Include/Core/**`, `mt5/ea/Include/Sat/**`, `mt5/ea/Include/Book/**`, `mt5/ea/presets/FABLE_*.set`, and the entire gate-covered numeric chain (`research/bpure/steppers/*.py`, `research/bpure/parity/*.py`, `research/bpure/mql5/*.py` + its `.mqh/.mq5`).

---

## 2. Residual audit

`git grep` over the working tree for the living-code legacy token set
(`\bv7\b`, `\bv34\b`, `v3.4`, `brain1/2`, `federation`, `federated`, `fed_frac`,
`static_fed`, `frac7`, `frac34`, `FMA3v34/3/2`, `CV34`, `V7Core`, `V7Sim`) across
`*.py *.mqh *.mq5 *.set` and canonical `*.md`, **excluding** the immutable set
(`freeze/**`, `RECONCILIATION.md`, `MORNING_BRIEF.md`, `ANTIGRAVITY_COMPARISON.md`,
`BPURE_WAVE*`, `V34_REFACTOR_ASSESSMENT.md`, `B_PURE_STAGE0_RESULTS.md`,
`NOMENCLATURE.md`).

**Headline result: the canonical numeric + EA + preset chain is 100% clean
(0 residual tokens).** Remaining occurrences are all **outside the gate chain**
and fall into four buckets:

### Bucket A — sanctioned legacy (NOMENCLATURE §Presets / provenance) — KEEP
- `archive/ea-v1-v2/FableFederation_V1.mq5` (15 lines), `FableFederation_V2.mq5` (15 lines) — earlier EA builds, retained on disk, referenced in `mt5/ea/SPEC.md` + `RUNSHEET.md`.
- `mt5/ea/Include/FMA3/**` — 5 files (`V7Core.mqh`, `V34Exec.mqh`, `V34Live.mqh`, `V34Replay.mqh`, `Federation.mqh`): the include set for the V1/V2 EAs, not the current EA.
- `mt5/ea/presets/FED_*.set` — 11 deep-legacy run presets (`FED_IC_RESEED_*`, `FED_IC_RUN2_*`, `FED_IC_G3B`, `FED_V2_*`), explicitly kept as-is by `NOMENCLATURE.md` line 66.

### Bucket B — hash-bound / on-disk / frozen-artifact provenance (STRING-LITERAL CAUTION) — MUST KEEP
Renaming any of these would break a hash, a file path, or a data contract:
- `strategy_fma3.py` config literals — `"structure":"static_federation"`, `"w_v7"`, keys `"v7"/"v34"`, the `fed_frac_h = frac7_h*… + frac34_h*…` formula string. These feed `strategy_fma3.config_hash()`, pinned as `fma3_v1_pin.json` (hash `51a7541cc2aaa593`) and cross-checked inside the EA (`…/V34Replay.mqh:36-38`) and by `model/v3/reproduce.py:114`. Flipping them changes the hash and breaks EA↔model parity.
- On-disk artifact paths: `research/baselines/fma2/v34_s10_pin_curve.parquet`, `research/outputs/v7_book_frac_1h.parquet`, `…/v7_book_equity_1m.parquet`, `research/outputs/fwd/fed_frac_1h_fwd.parquet`, `research/outputs/mt5/FMA3_fed_frac_v3.csv` (Stream 3 explicitly left this data-file name on disk).
- Read-only FMA2 frozen module `eval_v34_pin_s10.build_c2()` (the pinned reference constructor — provenance).
- Forward-bundle JSON keys `federation_window` / `federation_events` (producer `run_forward_oneshot_native.py` ↔ consumer `build_package_data.py` data contract).

### Bucket C — historical / descriptive prose (research + design layer) — low stakes
- `scripts/*.py` — 22 files whose doc-comments describe "the v3.4 book" / the historical "federation" structure or delegate to the frozen FMA2 constructor (analysis/reporting layer, not gate-covered).
- `model/v3/DESIGN_COMPARISON.md`, `DESIGN_OPT1_NATIVE_MQL5.md`, `DESIGN_OPT2_PYTHON_BOT.md` — design-exploration docs discussing the (legitimately still-present) `V7Core.mqh` class and hypothetical `V7Sim/V34Sim` options.
- `archive/docs-v1.0/**`, `docs/v3.0/**`, `archive/whitepaper/**` prose referencing the model lineage.

### Bucket D — genuine, non-gating, optionally-actionable residuals
These are the only occurrences that are neither provenance nor sanctioned-legacy
and could still be flipped. None touch the gate; both gates are green with them
present.
1. `engine/books.py:46` — live function `build_v34_variant_frac_1h()` (called 2× in `scripts/run_htail1.py:125,175`) was not renamed to the `build_sat_…` convention alongside its sibling `build_sat_frac_1h`; plus docstrings "the v3.4 shipped book".
2. `model/v3/reproduce.py:116-117` — local var `fed` and the print label `"fed_frac built: … (8 v7 + 31 v34, 6 shared)"` (cosmetic; the function it calls is already `static_blend`).
3. `docs/v3.0/DEMO.md:113` — stale build instruction "`Include/FMA3v3/`"; the dir is now `Include/Book/` (the current EA `FableBook.mq5` correctly includes `Book/*`).

**Conclusion:** the rename is complete and correct on the canonical Core/Satellite
book chain. Residuals are dominated by intentional provenance (buckets A/B) and
descriptive prose (bucket C); bucket D is three cosmetic/non-binding items an
owner may optionally clean up in a follow-up. **No residual affects the parity
gates.**

---

## 3. Gate re-run (measured, this session)

Both gates were re-run from scratch and reproduce the frozen baseline exactly —
proving the rename changed zero numbers.

### Python book parity — `research/bpure/parity/validate_book.py`
```
book_maxabs_vs_golden = 4.196643033083092e-14      (target 4.196643e-14 — EXACT)
cells_total           = 1530749
cells_nonzero         = 132454
cells_gt_1e-12        = 0
pass_book_le_1e-12    = true
GATE (account_engine_1m, EUR 10k) vs full-precision pin:
   dCAGR = 0.0   dMaxDD_worst = 0.0   dSharpe = 0.0   dFinalEUR = 5.8e-11
per-sleeve maxabs vs golden: crisis 0.0, trend_v2 0.0, meanrev 1.89e-15,
   intraday 2.50e-14, mag 5.33e-15, others ≤1.5e-15
overall pass = true
```

### MQL5 book parity — `research/bpure/mql5/harness_sim.py` (mirror) → `validate_mql5_book.py`
Harness regenerated `out/harness_sim_actual.csv` (49379 bars) and diffed against
the frozen golden `book.parquet`:
```
max_absdiff   = 4.196643033083092e-14              (identical to the Python side)
cells_total   = 1530749
cells_nonzero = 132454
cells_gt_gate (>1e-12) = 0
actual_nan_cells = 0
worst symbols: USA500 4.197e-14, USTEC 3.60e-14, XAUUSD 3.11e-15, …
pass = true
```

### MQL5 in-terminal recompile (Stream 2 — not relaunched here)
Stream 2 recompiled the 9 `Check*.mq5` + `TestV34Native.mq5` headless via
`wine MetaEditor64` = **0 errors / 0 warnings** each, and the in-terminal book
replay matched golden at `4.197e-14`. Bonus self-verify: `FableFederation_V2`
(Core chain) and `FableBook` (Book chain) both compiled 0/0. The terminal was
**not** relaunched for this report, per instruction.

Both re-run numbers are bit-for-bit the pre-rename baseline and the frozen
target `4.196643e-14`.

---

## 4. What stayed legacy, and why

- **The freeze** `model/v3/freeze/FMA3-v34-freeze-1/` and its hashes — renaming a
  hashed artifact breaks provenance (NOMENCLATURE §Immutable 1).
- **Legacy EAs V1/V2 + `Include/FMA3/`** — earlier builds retained for provenance
  and referenced by `SPEC.md`/`RUNSHEET.md`; the compiled `FableFederation_V3.ex5`
  binary also keeps its old name (its `.mq5` source was renamed to `FableBook.mq5`).
- **Deep-legacy `FED_*.set` presets** and on-disk data files
  (`FMA3_fed_frac_v3.csv`, the `*_pin_curve.parquet` set) — neutrally/historically
  named artifacts; renaming would break path reads (STRING-LITERAL CAUTION).
- **Hash-bound config in `strategy_fma3.py`** — feeds the pinned `config_hash`
  cross-checked by the EA; must stay to preserve EA↔model parity.
- **Dated/historical records** — kept as written (NOMENCLATURE §Immutable 3).

---

## 5. Remaining owner action

1. **Review** branch `rename/core-satellite` (the orchestrator stages + commits;
   no git operations were run by the sweep).
2. **Optional cleanup** of the three bucket-D cosmetic residuals (§2.D) — none
   block merge.
3. **Merge to `main`.** Both parity gates are green and reproduce the frozen
   `4.196643e-14` baseline exactly; the rename is numerically inert.

---

## 6. Independent QA addendum (orchestrator, not the sweep agent)

Per owner instruction ("run QA to ensure no logic changed"), the following was run
**independently** of the rename workflow's self-gates.

**Structural proof — "no logic changed."** For all 91 changed code files, the
pre-rename `main` version was forward-mapped through the rename substitution and
diffed against the branch version. **`line_delta = 0` on every source file** (no
line added/removed anywhere). All residual hunks classified as naming / prose /
regenerated-output; **zero source-logic changes**. Result-JSON gate metrics
byte-identical main vs branch (`book_maxabs 4.196643033083092e-14`, `cells_gt_gate 0`).

**Behavioral proof — re-run fresh on the renamed branch:**

| Gate | Pre-rename | Post-rename (this QA) |
|---|---|---|
| `validate_book.py` max\|diff\| | 4.196643033083092e-14 | **4.196643033083092e-14** (0 > gate; ΔCAGR/ΔMaxDD/ΔSharpe = 0.0) |
| `validate_bh.py` equity+worst over 2,948,650 bars | 0.0 bitwise | **0.0 bitwise** (`max|deq| 0.000e+00 max|dw| 0.000e+00`), warm-start bitwise, PASS |
| `harness_sim` + comparator | 4.197e-14 | **4.197e-14**, 0 > gate, PASS |
| `TestV34Native` recompile (renamed sources) | 0/0 | **0 errors / 0 warnings** |

**Verdict: PASS on both proofs. The rename changed zero logic and zero numbers.**
Bucket-D (§2.D) cosmetic residuals are confirmed non-gating and left as optional
follow-ups (not touched, to preserve the verified-clean state).
