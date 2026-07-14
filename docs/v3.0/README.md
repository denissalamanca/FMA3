# v3.0 — The faithful-executor release (index)

FMA3 v3.0 is the release where **the model stops being a promise and becomes a
thing that provably runs**. v1.0 shipped the **model** — a Python 1-minute
worst-mark record-engine book (a blended NSF5 Core band book at capital share
**w = 0.70** + FMA2 Satellite fixed-fraction book at 0.30, 33 netted symbols).
v3.0 ships the **EA that provably EXECUTES that model on MT5**
(`FableFederation_V3.ex5`, sha `740da0ff…`), plus the **honest deployable
reality**: two dials, three physical constraints, and the measured friction
between the frictionless record and a real retail account. The canonical model
now lives in its own home — **[`model/v3/`](../../model/v3/README.md)** — and
this page is the one-screen index to the v3.0 doc package that surrounds it.

> **In-sample honesty banner.** Every model figure below is an **in-sample
> RECORD read** (IC 2020-25, engine of record: Python 1-minute worst-mark,
> reproduced to the euro by `model/v3/reproduce.py`, config hash
> **`51a7541cc2aaa593`**, `w_v7 = 0.70`). MT5 real-tick + live demo are the
> remaining falsification tests. Achievable equity is **0.66–0.95× the record**
> by dial/scale — do NOT read a model number as a deployable promise.

---

## Headline (frozen model of record, two shipped dials)

| Preset | Seed | Dial | Final equity | CAGR | MaxDD (worst-mark) | Sharpe |
|---|---:|---|---:|---:|---:|---:|
| **IC** (H-RISK-1) | €10,000 | s = 1.6 compounding | **€3,872,872** | **+170.2%** | **22.58%** | **2.465** |
| **FTMO** (H-RISK-2b) | €100,000 | s = 0.7 + daily breaker x = 3.0% | **€1,332,404** | **+54.02%** | **13.33%** | 26 breaker fires |

Matrix = `static_fed(0.70) × s` through the 1-minute worst-mark record engine.
Both equities are asserted to the euro by `model/v3/reproduce.py` (exits
non-zero on any drift). Full math, engine constants, and the breaker anchor are
in [`model/v3/MODEL_SPEC.md`](../../model/v3/MODEL_SPEC.md); the frozen inputs
are pinned in [`model/v3/PINNED_INPUTS.md`](../../model/v3/PINNED_INPUTS.md).

## The v3 EA — why replay, not compute-live

The blend share weights `fed_frac[h,k] = f7·(w·a_h/j) + f34·((1−w)·b_h/j)`
(with `j = w·a_h + (1−w)·b_h`, `a_h`/`b_h` each book's FROZEN native standalone
equity multiple) depend on **frozen native curves a live s-levered account
cannot reconstruct** — so compute-live (v1/v2) provably diverges whenever s ≠ 1,
and **both shipped dials are s ≠ 1**. v3 discards the whole
VBalance/quarterly-reseed/e34 stack (frozen inside `frac7`) and instead
**replays a precomputed UNIFIED 33-symbol netted `fed_frac` stream**
(`FMA3_fed_frac_v3.csv`, fmt = 3): each symbol sized `fed_frac · InpScale ·
ACCOUNT_BALANCE / unit`, ONE net position + ONE magic per symbol, full-map eurq
(8 quote currencies), FTMO daily breaker on the previous-server-day CLOSE anchor
+ worst-mark `eq_w`. Replay is the **only faithful path**. Design:
[`model/v3/EA_V3_DESIGN.md`](../../model/v3/EA_V3_DESIGN.md).

## RECON-4 verdict (one line)

**v3 holds the model's EXACT target position** (`after/want` median **1.000**,
all 3 MT5 runs, IC Markets acct 11078280, 1m-OHLC) — PARITY s=1.0 €391,873
(0.84×), IC s=1.6 €2,552,962 (0.66×), FTMO s=0.7 €1,265,541 (0.95×), **0
rejects** on all deployable runs — and every equity gap is a **named physical
constraint**, not a defect. Full record:
[`model/v3/RECON4_RESULTS.md`](../../model/v3/RECON4_RESULTS.md).

---

## The doc package + dashboards

| Doc | What it is |
|---|---|
| **[STRATEGY.md](STRATEGY.md)** | The "what & why" for v3 — the frozen 33-symbol netted book, the `fed_frac` bookkeeping formula, why the a/j·b/j share weights force **replay over compute-live**, the Satellite-sleeve revival (7 symbols the EurPerQuote bug silently killed in v1/v2), and the two-dial (IC / FTMO) split. |
| **[PERFORMANCE.md](PERFORMANCE.md)** | The canonical performance read — both frozen dials, the friction ladder (0.95× @ s0.7 → 0.84× @ s1.0 → 0.66× @ s1.6), the volume-limit s-sweep (FMA3-024, cap cost 0–6% @ €10k, 17–40% @ €1M), and the deployable-dial reframe (margin, not volume, sets the IC dial at 1:30). |
| **[VALIDATION.md](VALIDATION.md)** | The execution-validation battery — the exact reproduction chain (`reproduce.py` to the euro), FMA3-RECON-4 position-level fidelity (after/want median 1.000), the volume-limit sweep, the 1:30 margin finding, and sign-off status. |
| **[RECONCILIATION.md](RECONCILIATION.md)** | The FMA3-RECON-4 map — the 3 MT5 runs, position fidelity (median 1.000, all runs), 0 rejects on deployable dials, the 28-vs-26 breaker-fire delta, and each equity gap attributed to its named physical cause. Standing record per `research/protocol/RECONCILIATION.md`. |
| **[TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md)** | The 33-symbol blended book — composition (8 Core + 31 Satellite, 6 netted), the Satellite revival, per-symbol trade profiles from RECON-4, the volume-capped symbols (XAUUSD/SOLUSD/ETHUSD), and monitoring flags. |
| **[EA_AUDIT.md](EA_AUDIT.md)** | The executor's anatomy — the unified replay stream, per-symbol sizing/magic map, full-map eurq, the FTMO breaker mechanics, the 3-reviewer adversarial pass + fixes, and what v3 **discards** from the v1/v2 stack and why (frozen inside `frac7`). Mirrors `model/v3/EA_V3_DESIGN.md` at package depth. |
| **[DEMO.md](DEMO.md)** | The honest deployable reality + forward-test plan — the three physical constraints (friction, `SYMBOL_VOLUME_LIMIT`, broker margin), the ~€2M/s capacity ceiling, the two scaling levers (higher-tier account · N parallel accounts at €C/N), the owner-leverage dials (IC 1:30 s=1.6 min ML 121%; FTMO 1:100 s≈0.5), and the **live-horizon gap** (v3 replays a frozen stream ending 2025-12-31; live trading needs a forward generator — not yet built). |
| **[DASHBOARD_IC.html](DASHBOARD_IC.html)** · **[DASHBOARD_FTMO.html](DASHBOARD_FTMO.html)** · **[DASHBOARD.html](DASHBOARD.html)** | The visual scorecards — IC + FTMO per-preset (model record **plus** the v3 deployed reality, PROVISIONAL banner) and the combined overview. Self-contained; open in any browser. Ship per update. |

---

## The canonical model home + research layer

The **single source of truth for the model** is now
**[`model/v3/`](../../model/v3/README.md)** — not the scattered
`research/outputs/*.json` or `scripts/run_*.py` artifacts. If you want to know
"what is the FMA3 model and what does it earn," read it there; it reproduces to
the euro and carries its own honesty flags.

| Doc | What it is |
|---|---|
| **[../../model/v3/README.md](../../model/v3/README.md)** | The stable model of record — both dials, the reproduce command, the look-alike warnings, the v1→v2→v3 EA relationship. |
| **[../../model/v3/MODEL_SPEC.md](../../model/v3/MODEL_SPEC.md)** · [PINNED_INPUTS.md](../../model/v3/PINNED_INPUTS.md) | The full blend math + engine constants + breaker · the exact frozen input artifacts. |
| **[../../model/v3/RECON4_RESULTS.md](../../model/v3/RECON4_RESULTS.md)** | The execution reconciliation in research depth — 3 runs, fidelity, the three physical constraints, the scaling levers, the deployment-dial decisions. |
| **[../../research/protocol/RECONCILIATION.md](../../research/protocol/RECONCILIATION.md)** | The standing protocol — every new EA run earns a recorded FMA3-RECON-N entry before deploy. |
| **[../../scripts/export_book_frac_v3.py](../../scripts/export_book_frac_v3.py)** · [sweep_s_volcap.py](../../scripts/sweep_s_volcap.py) | Builds the unified replay stream · the volume-cap s-sweep behind the capacity ceiling. |

**Single source of truth (code):** [`model/v3/reproduce.py`](../../model/v3/reproduce.py)
(self-contained; inlines the blend, depends only on `engine/` + the four frozen
inputs) → asserts €3,872,872 and €1,332,404. Reproduce:
`python3 model/v3/reproduce.py` (~8–9 min, expected delta 0.0 on both dials).

---

## Honest caveats

- **The model figures are in-sample RECORD reads, not deployable promises.**
  Achievable equity is **0.66–0.95× the record** by dial/scale; the €3.87M
  IC-s1.6 record is a **frictionless ceiling**, not physically reachable on one
  retail account at that scale (XAUUSD alone caps at half the model's target).
- **Three physical constraints the record engine does not model.** (1)
  Transaction friction — compounds with leverage. (2) `SYMBOL_VOLUME_LIMIT`
  (this account: XAUUSD 10 / SOLUSD 1000 / ETHUSD 100 lots) — a capacity ceiling
  that binds past ~€2M/s of book. (3) Broker margin — v3's own 0.9·balance cap
  self-limits the book. None bind at the deployable FTMO dial (clean 0.95×).
- **IC = s=1.6 is OWNER-ACCEPTED but PROVISIONAL.** €2.55M @ 1:30, min ML 121%
  (far above IC's 50% stop-out, ~11pp over the owner's ML≥110% floor); the old
  "not deployable at 1:30" flag was v1-over-leverage-specific and is DISPROVEN
  for v3 — but a real-tick intra-bar min-ML confirmation (>110%) is still owed.
- **FTMO = s≈0.5 is RECOMMENDED, not shipped.** The sweep favours s=0.5 (ret/DD
  4.78, worst-DD 7.8% vs s0.7's 13.3%), and the warm-COVID flag says the shipped
  s=0.7 + 3% breaker BREACHES the −10% rule cold-start-blind; a 1:100 confirm
  run is pending before the dial is cut.
- **MT5 real-tick + live demo remain the falsification tests.** RECON-4 is
  1m-OHLC; every number here awaits real-tick and live-demo confirmation.

---

*Last updated: 2026-07-12. All model figures are in-sample RECORD reads (IC
2020-25); achievable equity is 0.66–0.95× the record by dial/scale; MT5
real-tick + live demo are the remaining falsification tests.*
