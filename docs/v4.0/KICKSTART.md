# FMA v4 — kickstart brief (for a fresh session)

*Context for opening FMA v4 in a **separate** session, per the standing decision that v4
work does not happen inside FMA3.*

> **By design, this brief contains no backlog, no findings, and no priorities.** A previous
> pass produced a v4 opportunity list; it was **deliberately removed** so that a fresh
> session forms its **own independent view** from the evidence rather than inheriting an
> anchored one. Do not go looking for it. If your independent assessment happens to converge
> on similar conclusions, that convergence is itself worth more than the original assertion.

---

## Where FMA3 stands (the parent — context only)

A blended book: **NSF5 Core** (band-allocation, capital share w = 0.70) × **FMA2 Satellite**
(v34 ensemble, 0.30), **33 netted symbols**, executed by `FableBookNative` — a native,
live-computing MQL5 EA (no frozen replay). Two dials: **IC s = 1.6** (€10k, 1:30) and
**FTMO s ≈ 0.70** (€100k, 1:100, 3% daily breaker).

Status: the executor is certified (compute bit-exact vs the record engine; position fidelity
~perfect; both sleeve ports bit-exact), both dials are decided and documented, and the
on-broker real-tick crisis certification passed. It is in **demo-launch prep** and carries
**its own open readiness thread** (`docs/v3.0/DEMO_GO_NOGO.md`). **That is FMA3 work — v4 does
not touch it.**

## The evidence base (analyse it yourself)

Everything needed to form an independent view is here — go to the primary data, not to
anyone's summary of it:

| Where | What |
|---|---|
| `docs/v3.0/CURRENT_STATE.md` | the live status layer — the deployable result + the friction decomposition |
| `docs/v3.0/SLEEVE_REGIME_ANALYSIS.md` | trade characteristics + performance by sleeve and regime |
| `model/v3/` | the model of record — `reproduce.py` (asserts both dials to the euro), `MODEL_SPEC.md` |
| `engine/` | the record engine (Python 1-minute worst-mark accounting) |
| `research/outputs/` · `research/baselines/` | the golden curves (Core / Sat / blended) |
| `research/protocol/RECONCILIATION.md` | the full RECON ledger (every EA run's reconciliation) |
| `docs/REGISTRY.md` | every experiment ever run, including the failures |
| `archive/` | **frozen v1/v2 — historical only, not a reference** |

The IC full-window run and its derived per-symbol / per-cycle / drawdown data are the richest
single source; the RECON ledger tells you what has and hasn't been proven.

## Constraints
- v4 is a **fresh program**. FMA3 and its parents (`../NewStrategyFable5`, `../FableMultiAssets2`)
  are **read-only references**, not edit targets, unless v4 explicitly forks something.
- **Decide first, with the owner:** where v4 lives — here under `docs/v4.0/` + a working area,
  or spun out into its own repo (as the validation-engine spinoff was). Don't assume.
- Never deploy / trade / move money; any EA ships trade-disabled.
- Read `MEMORY.md` for the standing project constraints.

---

## ▶ Paste this to open the v4 session

> Kickstart **FMA v4**, the next program after FMA3. Start by reading
> `docs/v4.0/KICKSTART.md` and `MEMORY.md`. FMA3 (the parent blended book) is validated and
> in its own demo-launch prep — it's a separate program; do not work on FMA3 here.
>
> There is deliberately **no backlog** — I want you to build your own from the evidence.
> Your first task is **not to execute**: independently assess FMA3's evidence base (the
> docs, the model of record, the golden curves, the RECON ledger, the experiment registry)
> and **propose a v4 backlog and roadmap** — what you think the highest-ROI directions are,
> with your reasoning, the data behind each, and a rough scope. Be willing to challenge the
> premise that continuing this book is even the right bet.
>
> Also surface the one decision I need to make first: whether v4 lives in this repo or spins
> out into its own. Give me the proposal, then we pick a direction together before any build.
