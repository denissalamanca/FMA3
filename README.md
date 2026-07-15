# FableMultiAssets3 — unified Core × Satellite book (IC Markets EU, EUR)

A blended trading book: **NSF5 Core** (v7 band-allocation, weight 0.70) × **FMA2
Satellite** (v34 ensemble, 0.30), 33 netted symbols, executed by a native,
live-computing MQL5 EA. **This README is the one-screen map of the current (v3)
project.** Everything from v1.0/v2 is frozen in [`archive/`](archive/) and is
**not** a reference for current work.

---

## Current status (2026-07)

- **Both dials decided & documented:** IC **s = 1.6** (RECON-9), FTMO **s ≈ 0.70**
  under a ≤1-breach/year policy (RECON-10/11).
- **Executor certified:** `FableBookNative` computes the blend live each bar,
  bit-exact vs the record engine (R1 = 5.06e-13), position fidelity ~perfect,
  both sleeve ports bit-exact. Ships **trade-disabled** until explicitly enabled.
- **Next:** real-tick crisis certification (**RECON-12**) → a **3-month
  demo-forward** on IC + FTMO demo accounts. Plan:
  [`docs/v3.0/DEMO_FORWARD_PLAN.md`](docs/v3.0/DEMO_FORWARD_PLAN.md).
- **No valid OOS forward exists yet** — the demo produces the first. (The old
  2026-H1 one-shot was not properly conducted; it is archived, not used.)

## Where everything lives

| Path | What it is |
|---|---|
| **[`docs/v3.0/`](docs/v3.0/README.md)** | **The current doc package — start here.** Live status (`CURRENT_STATE.md`), the two dial decisions, the weight-probe, the sleeve/regime analysis, the demo-forward plan, dashboards. |
| **[`model/v3/`](model/v3/README.md)** | The **model of record** — `reproduce.py` (asserts both dials to the euro), `MODEL_SPEC.md`, `PINNED_INPUTS.md`, the RECON-9 deploy adjudication. |
| `engine/` | The **record engine** (`record_engine.py` / `record_engine_ext.py`) — the Python 1-minute worst-mark accounting of record. |
| **`mt5/ea/`** | The **live EA** — `FableBookNative.mq5` + the `Include/` headers + the `presets/` (`FABLE_*_REALTICK_P1.set`). This is what runs on MT5. |
| `research/bpure/` | The native-EA **port certifications** (blend / book / coresignal / coresim / crisis) — bit-exact mirror gates. |
| **[`research/protocol/RECONCILIATION.md`](research/protocol/RECONCILIATION.md)** | The **RECON ledger** (RECON-1 … 11) — every EA run's reconciliation record. |
| `research/protocol/` | Pre-registered protocols + `PRESETS.md` (the dial pre-registration). |
| `research/outputs/` · `research/baselines/` | Golden curves + pinned reference artifacts. |
| `scripts/` | Research + build scripts (probes, dashboards, dial runs). *Note: still tangled with some v1-era libs — a deferred reorg.* |
| `strategy_fma3.py` | The **config source** (hash `51a7541cc2aaa593`, w_v7 = 0.70). |
| `NOMENCLATURE.md` | The naming conventions (single source of truth). |
| [`docs/v4.0/`](docs/v4.0/OPPORTUNITIES.md) | **Parked** v4 hypotheses backlog — opened only in a *separate* session, not pursued here. |
| **[`archive/`](archive/)** | **Frozen v1/v2 historical record — NOT a current reference.** |

## Reproduce the model of record

```
python3 model/v3/reproduce.py      # asserts IC €3,872,872 (s=1.6) + FTMO €1,332,404 (s=0.7) to the euro
```

## Parents (read-only)

- **Core** — `../NewStrategyFable5` (NSF5 v7 band book)
- **Satellite** — `../FableMultiAssets2` (v34 ensemble)

Both are read-only upstreams; FMA3 consumes their frozen curves, never edits them.
