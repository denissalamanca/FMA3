# FMA3 Nomenclature — Core / Satellite (canonical glossary)

**Adopted 2026-07-14 (owner-approved).** This file is the single source of truth
for how we name the parts of the Fable book. It replaces the legacy `v7` / `v34`
lineage numbers, which came from when these two books were *separate products* and
became misleading once they merged into one book.

---

## The one-sentence model

**The Fable book** is a single blended target per symbol, built from **two
engines**: the **Core** (a band-allocation engine, ~70% weight) and the
**Satellite** (an ensemble of tactical alpha **sleeves**, ~30% weight). Every alpha
component is a **sleeve**; the blend weight is the **core weight**.

- We do **not** call the blend a "federation" anymore — it is *one book*, not a
  treaty of two.
- `v7` / `v34` / `brain1` / `brain2` are **retired** as living names. They survive
  only inside frozen artifacts and the historical ledger (see *Immutable* below).

---

## Old → new map

### Concepts
| Concept | Legacy | New |
|---|---|---|
| The whole blended book | federation / federated / "the FMA3 book" | **the Fable book** |
| Engine 1 (band allocator, 0.70) | v7 / brain1 / the band book | **Core** |
| Engine 2 (sleeve ensemble, 0.30) | v34 / v3.4 / brain2 / the replay book | **Satellite** (short **Sat**) |
| Atomic alpha component | sleeve (v34) / band or leg (v7) | **sleeve** (universal); Core sleeves + Sat sleeves |
| The blend operation | `static_fed` / `static_federation` | `static_blend` / **the blend** |
| Final per-symbol target fraction | `fed_frac` | `book_frac` |
| Blend weight | `w_v7 = 0.70` | `core_weight = 0.70` |

### Python identifiers
| Legacy | New |
|---|---|
| `frac7` / `frac34` | `core_frac` / `sat_frac` |
| `f7` / `f34` (and `f7s`/`f34m`/`f34s`) | `f_core` / `f_sat` (`f_core_s`/`f_sat_m`/`f_sat_s`) |
| `eq7` / `eq34` (`eq7_rw`/`eq34_rw`) | `core_eq` / `sat_eq` (`core_eq_rw`/`sat_eq_rw`) |
| `build_v34_frac_1h` | `build_sat_frac_1h` |
| `v7_book_frac_1h` / `v34_book_equity_1m` / `v7_book_equity_1m` | `core_book_frac_1h` / `sat_book_equity_1m` / `core_book_equity_1m` |
| `frac7_full` `frac34_hyb` `frac34_full` `frac34_pin` `frac7_h` `frac34_h` | `core_frac_full` `sat_frac_hyb` `sat_frac_full` `sat_frac_pin` `core_frac_h` `sat_frac_h` |
| `fed_frac_h` `fed_frac_v3` `fed_frac_1h_fwd` | `book_frac_h` `book_frac_v3` `book_frac_1h_fwd` |
| `a_h` / `b_h` | **kept** — neutral math symbols; `a` = Core native equity, `b` = Sat native equity |

### MQL5
| Legacy | New |
|---|---|
| include dir `Include/FMA3v2/` (V7Core) | `Include/Core/` |
| include dir `Include/FMA3v34/` (sleeves) | `Include/Sat/` |
| include dir `Include/FMA3v3/` (Fed*) | `Include/Book/` |
| class `V7Core` / `V7Sim` | `CoreEngine` / `CoreSim` |
| class prefix `CV34…` (17 classes) | `CSat…` |
| class prefix `Fed…` (FedReplay/FedExec/FedConvert) | `Book…` (BookReplay/BookExec/BookConvert); `Guardian` unchanged |
| const/macro prefix `V34CB_`, `V34…`, guard `FMA3V34_…` | `SATCB_`, `Sat…`, `SAT_…` (and `FMA3V2_`→`CORE_`, `FMA3V3_`→`BOOK_`) |
| EA `FableFederation_V3` | `FableBook` |

### Presets (`mt5/ea/presets/`)
| Legacy | New |
|---|---|
| `FED_V3_IC*` / `FED_V3_FTMO*` / `FED_V3_PARITY_S10` | `FABLE_IC*` / `FABLE_FTMO*` / `FABLE_PARITY_S10` |
| `..._V7ONLY` / `..._V34ONLY` (diagnostics) | `..._CORE_ONLY` / `..._SAT_ONLY` |
| deep-legacy `FED_IC_RESEED_*`, `FED_IC_RUN2_*`, `FED_IC_G3B`, `FED_V2_*` | **kept as-is** (historical run presets) |

---

## Immutable (never renamed — provenance)

These keep their legacy names *by design*; the glossary above is how you read them:

1. **The freeze** `model/v3/freeze/FMA3-v34-freeze-1/` and its `freeze_hash`
   `fc14159f…` / `hermetic_freeze_hash 5785937244cd48db…` — renaming a hashed
   artifact breaks its provenance. Future freezes use the new scheme:
   `fable-sat-freeze-N` (Satellite) / `fable-freeze-N` (full book).
2. **The RECON ledger** (`research/protocol/RECONCILIATION.md`) — append-only
   historical record; existing rows stay as written (they describe what was named
   what, when). New rows use Core/Satellite.
3. **Dated session records** — `MORNING_BRIEF.md`, `ANTIGRAVITY_COMPARISON.md`,
   `BPURE_WAVE*`, `V34_REFACTOR_ASSESSMENT.md`, `B_PURE_STAGE0_RESULTS.md` — kept
   as-written (a rewrite would distort the record); each gets a one-line pointer here.
4. **Git history** and the repo/project name **FableMultiAssets3 / FMA3** — unchanged.

## Not a brain name (leave alone)
- `model/v3`, `docs/v3.0`, EA `V2`/`V3` build numbers, `FMA3-RECON-N` — the "3", "v3",
  "N" here are **model-of-record / EA-build / ledger iteration** numbers, unrelated
  to the two engines. They stay.

---

*Rename applied on branch `rename/core-satellite`; parity gates (Wave-1 book diff,
MQL5 in-terminal comparator) re-run to prove the rename changed **zero numbers**
before merge to `main`.*
