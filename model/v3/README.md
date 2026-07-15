# FMA3 — STABLE MODEL OF RECORD (v3)

> **This folder is the single source of truth for the shipped model.**
> If you want to know "what is the FMA3 model and what does it earn," it is defined **here** — not in the scattered `research/outputs/*.json` or `scripts/run_*.py` artifacts. Reproduced to the euro on 2026-07-12.

## What the model is

One blended book, config **`51a7541cc2aaa593`**, `w_v7 = 0.70` (the Core weight), run through the 1-minute worst-mark record engine. Two shipped dials:

| Preset | Seed | Dial | Final equity | CAGR | MaxDD (worst) | Dashboard |
|---|---:|---|---:|---:|---:|---|
| **IC** (H-RISK-1) | €10,000 | s=1.6 compounding | **€3,872,872** | +170.2% | 22.58% | `archive/docs-v1.0/DASHBOARD_IC.html` |
| **FTMO** (H-RISK-2b) | €100,000 | s=0.7 + breaker x=3.0% | **€1,332,404** | +54.02% | 13.33% | `archive/docs-v1.0/DASHBOARD_FTMO.html` |

Full math, engine constants, and the breaker are in [`MODEL_SPEC.md`](MODEL_SPEC.md). The exact frozen inputs are pinned in [`PINNED_INPUTS.md`](PINNED_INPUTS.md).

## Reproduce it (golden reference)

```
python3 model/v3/reproduce.py          # both presets, ~8-9 min — asserts €3,872,872 and €1,332,404
python3 model/v3/reproduce.py --ic     # IC only  (~4 min)
python3 model/v3/reproduce.py --ftmo   # FTMO only (~4 min)
```
`reproduce.py` is **self-contained** — it inlines the blend and depends only on `engine/` + the four frozen input artifacts. Both headline equities are asserted; the script exits non-zero on any drift.

## ⚠ DO NOT confuse this model with these look-alikes

| Look-alike | Why it is NOT the model |
|---|---|
| `hrisk1_results.json` "= Core-alone" | **False.** `hrisk1` **is** the blended book (`static_fed` blends `f7`+`f34`). A prior session mislabeled it Core-alone — that error cost us. |
| `v7_book_frac_1h_ab.parquet` / `v7_book_tgt_1h_ab.parquet` | The **ownjoint Core-ONLY probe** artifacts. Not this model's input. The model's Core input is `v7_book_frac_1h.parquet` (no `_ab`). |
| `global_scale = 1.1` in `strategy_fma3.py` | The config **base point**, not the shipped dial. Shipped dials are IC s=1.6 / FTMO s=0.7. |
| `FED_IC_RESEED_*`, `FED_*` EA presets | EA execution experiments (v1/v2). The **model** is the Python record engine here; the EA only *approximates* it (v1/v2 diverge — see below). |

## Relationship to the EA (v1 → v2 → v3)

The EA is a **separate** artifact that tries to *execute* this model live. It does not yet match it:
- **v1/v2 diverge from the model** because they size Core off `VBalance` (pooled quarterly reseed, floating double-count) and Satellite off `e34` (stagnant own sub-equity) — **not** the model's frozen `w·a/j`, `(1−w)·b/j` share weights. A live account levered by `s` provably cannot reconstruct those weights, so compute-live diverges whenever s≠1 (both dials are s≠1).
- **v3 (built + validated, FMA3-RECON-4)** replays the precomputed unified `fed_frac` stream (all 33 symbols) and reproduces this model **up to real execution constraints**: **0.95×** at the deployable FTMO dial (s0.7, 0 rejects), 0.84× at s1.0, 0.66× at s1.6 (volume limits + margin). Position fidelity is exact (held frac == fed_frac·s, median 1.000). `mt5/ea/FableBook.mq5` + `Include/FMA3v3/`. Full record: [`RECON4_RESULTS.md`](RECON4_RESULTS.md).

## ⚠ Honesty flags (these are in-sample RECORD reads, not deployable claims)

1. **IC s=1.6 is not deployable at retail 1:30** — margin gate binds first; deployable band ≈ s0.6–0.8.
2. IC ship verdict used a raised breach cap (0.15→0.20, FMA3-004c); the original 0.15 gate ships none at s=1.6.
3. **FTMO "fixed-base" is a scoring lens, not a sizing mode** — the €1.33M is compounding.
4. **FTMO compound-vs-withdraw contradiction** — €1.33M is never-withdraw; the 5/5 gates are scored under monthly withdraw-to-base. Both cannot hold at once.
5. **FTMO gates are cold-start in-sample** — warm re-validation breaches COVID; crisis-safe dial ≈ s0.30–0.35.
6. **The record has no position ceiling; a real broker does** — `SYMBOL_VOLUME_LIMIT` (XAUUSD 10 lots on the test account) caps the book past ~€2M/s, so the €3.87M s1.6 record isn't physically reachable on one retail account at scale (FMA3-RECON-4). Achievable equity is **0.66–0.95× the record** by dial/scale.

Details in [`MODEL_SPEC.md` §Honesty flags](MODEL_SPEC.md) and [`RECON4_RESULTS.md`](RECON4_RESULTS.md). MT5 real-tick + live demo remain the falsification tests.

---
*Pinned 2026-07-12. Both presets reproduced to the euro. Config `51a7541cc2aaa593`.*
