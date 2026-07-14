# FMA3 Evaluation Protocol — pre-registered 2026-07-10

**Committed BEFORE any merged-book number was computed.** The engine-bridge
work (Core extraction + record-engine wrapper + composite benchmark of the two
*parents*) runs concurrently with this commit; no merged/blended/blended
configuration has been simulated at commit time.

## 1. Engine of record

Python 1-minute worst-mark, single cross-margined EUR account
(`FMA2/research/account_engine_1m.py::simulate_account_1m`, wrapped by
`FMA3/engine/record_engine.py`), IC feed, 2020-01-02 → 2025-12-31, €10,000,
IC Markets EU Raw costs. Every shipped number comes from this engine.
Hourly fast-sim may screen; **panel nominates, record engine confirms; a
record-engine FAIL is decisive.**

## 2. Gates (composite benchmark)

Primary scoreboard — **dimension-wise best of the two parents measured in the
engine of record** (values filled by `research/outputs/composite_benchmark.json`
— parent measurements, not merged-book numbers):

| Dimension | Rule |
|---|---|
| CAGR | > max(parent CAGRs in record engine) |
| Max DD (worst-mark) | < min(parent worst-mark DDs) |
| Sharpe (daily close, 252) | > max(parent Sharpes) |
| Crisis tail (2020-02-15→2020-04-15 worst-mark peak-to-trough) | ≤ min(parents) |
| Negative years | 0 / 6 |
| Negative quarters (close-to-close M2M) | ≤ min(parents) |
| Breach P(maxDD>30%) (20d-block, 5000 paths, seed 20260709) | < min(parents) |

Secondary scoreboard — the owner's original six numbers (CAGR>96.1 · DD<20.9 ·
Sharpe>2.03 · crisis≤35.6 · 0 negY · ≤1/24 negQ), reported with the standing
caveat that they straddle two non-comparable engines (MT5 real-tick vs 1m
worst-mark).

**Honesty rule (owner decision 2026-07-10): honest frontier wins.** If the
gates prove unreachable without fragility, ship the best honest frontier and
the evidence for the ceiling.

## 3. What is licensed to vary — and what is frozen

- **Sleeve internals of both parents are FROZEN.** No re-tuning of any sleeve
  parameter of either book. Both parents' sleeves are locked, validated
  artifacts; 2020–2025 is heavily mined in both programs and re-tuning would
  be curve-fitting by installment.
- **The licensed design space is STRUCTURAL:** capital allocation between the
  two books, blend rebalance mechanics, combined-book exposure limits,
  global scale. Few parameters, tested one lever at a time.
- **Closed channels (never re-litigated):** FMA2 sleeves as band slots
  (H14/H15 exhausted); band mechanism inside the fixed-fraction convention
  (H8); duplicate edges — before any config carries both `BOOK_USTEC` and
  FMA2 `intraday`, their overlap must be measured (NB: the ρ0.87 F1 finding
  was F1↔intraday; BOOK_USTEC is a different USTEC sleeve — measure, don't
  assume either way).

## 4. Data-consumption ledger

| Window | Status | FMA3 use |
|---|---|---|
| IC 2020–2025 1m | Heavily mined by both parents | DEV for structural levers only (few-parameter, pre-registered grids) |
| 2015–2019 (h1, assigned spreads) | Consumed once by FMA2 v3.0 gauntlet (for imported candidates); FMA2 sleeves untested there except via v2.0 one-shot | Edge-persistence sanity check for STRUCTURAL findings (not worst-mark accounting; research-grade only) |
| 2026H1 holdout (Duka, 14 syms, USA500 proxy for USTEC) | Partially consumed by NSF5 (reporting, not fitting); never fitted by FMA2 | **ONE-SHOT forward confirmation of the final locked FMA3 book only.** Criteria pre-registered in FORWARD_TEST.md before the run. Consumed = logged. |
| Live demo 2026H2+ | Never touched | The real falsification test (owner's MT5 machine) |

## 5. Decision rules (inherited from both parents' house discipline)

1. **Pre-registration:** every experiment's bars are written in
   `research/protocol/` BEFORE the number is computed. Grids are fixed and
   tiny; selection rules stated in advance; no off-grid interpolation.
2. **One lever per version.** ADOPT only if ALL pre-committed bars pass
   (strict all-bars rule). **DECLINE by default; ties are rejects** — no
   complexity for a wash (+0.5pp minimum improvement bars).
3. **Mandatory discriminators:** any result that depends on rebalance
   scheduling gets the fixed-schedule ablation (freeze the trigger dates,
   re-run) — on WINNERS only, never as a rescue for failures. Any adopted
   lever gets parameter-perturbation (±20% on structural params) and the
   20d-block breach test.
4. **Multiple-testing ledger:** every config evaluated (including failures)
   is logged in `docs/REGISTRY.md` with a running count; DSR/selection
   discount computed from the ledger at lock time.
5. **Scale is set LAST** on the winning structure, by pre-committed rule
   (see HYPOTHESES.md H-FED-3), never tuned alongside other levers.
6. **Reproduction gate:** before any experiment session, the record engine
   must reproduce the Satellite pin and the Core-extract must match its anchor —
   drift means stop and diagnose.
7. Guard against the known overlay-ring failure: any blend bookkeeping
   must isolate each book's internal trigger state from the other book's
   P&L (virtual sub-account accounting). A cross-book coupling perturbation
   test (±€128 on one book's start capital, à la NSF5's chaos probe) is
   mandatory for any adopted blend mechanic.

## 6. Red-team battery (before lock)

On the winning configuration, in order: (a) parameter perturbation grid;
(b) fixed-schedule ablation where applicable; (c) 20d-block bootstrap breach;
(d) CPCV (8 blocks, k=2, purge 10d) on the *allocation* level;
(e) Duka second-feed cross-check (14 syms, USA500 proxy, documented gaps);
(f) LOO by sleeve-family to verify no keystone;
(g) coupling perturbation (±€128); (h) DSR from the ledger;
(i) 2026H1 one-shot forward confirmation per §4;
(j) capacity/min-lot feasibility at €10k (min_lot 0.01 quantization).

## 7. Registry

Experiment counter starts at FMA3-001. Format per entry: id, date, lever,
pre-registered bars (link), result, verdict, data consumed.
