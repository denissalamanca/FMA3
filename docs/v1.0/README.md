# v1.0 — Shipped version package (index)

FMA3 v1.0 is the shipped federation book — **both frozen parent books side by
side as virtual sub-accounts of ONE cross-margined €10k account**: the NSF5 v7.0
band book at capital share **w = 0.70** and the FMA2 v3.4 fixed-fraction book at
**0.30**, no cross-book rebalancing, global scale **s = 1.1**. This page is the
one-screen index to the **six-doc version package** (plus dashboard) that
documents it, and to the research/process layer beneath. Every headline number
below is transcribed from the canonical pin
(`research/outputs/fma3_v1_pin.json`, built by `scripts/eval_fma3_pin.py`;
config source `strategy_fma3.py`, config hash **`51a7541cc2aaa593`**, locked
2026-07-10).

> **In-sample honesty banner.** All numbers in this package are **in-sample**
> (IC 2020-25, engine of record: Python 1-minute worst-mark, €10k init); the
> 2026H1 one-shot is **consumed** (CONFIRM 4/4); **MT5 real-tick + live demo are
> the remaining falsification tests** ([DEMO.md](DEMO.md)).

---

## Headline (official pin, engine of record)

| CAGR | MaxDD (worst-mark) | Sharpe | COVID tail | Neg years | Neg quarters | Breach P(DD>30%) | €10k → |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0 / 6** | **0 / 24** | **0.0020** | **€665,777** |

Static federation w70/30 (H-FED-1 winner by rule) · no cross-book rebalance
(H-FED-2: all four cadences DECLINED) · no joint caps added (H-CAPS-1 NO-OP,
0 of 49,379 hours over entitlement) · scale s = 1.1 (H-FED-3 ceiling rule
re-picked probe-robust by the FMA3-RT adjudication — the ceiling-rule s = 1.4
failed the w+20% perturbation probe and the FAIL was **priced**, −39.4pp CAGR).
Breach: 5,000-path 20-day-block stationary bootstrap, worst-mark, seed 20260709.

## Gate scorecard — owner 6/6, composite 7/7

| Scoreboard | Result | Where |
|---|---|---|
| Owner's six gates (CAGR > 96.1 · DD < 20.9 · Sharpe > 2.03 · tail ≤ 35.6 · negY 0 · negQ ≤ 1) | **6/6 PASS** (straddles-two-engines caveat disclosed) | [PERFORMANCE.md](PERFORMANCE.md) |
| Seven composite dimensions (dimension-wise best of both parents, same engine, pre-registered) | **7/7 DOMINANT** — the first fully-dominant point in the two programs' combined history | [VALIDATION.md](VALIDATION.md) |
| 2026H1 one-shot forward (F1–F4, pre-registered) | **CONFIRM 4/4** — window +12.34%, DD 17.67%, sub-books +15.99%/+13.59%; holdout CONSUMED | [DEMO.md](DEMO.md) |

---

## The six-doc package + dashboard

| Doc | What it is |
|---|---|
| **[STRATEGY.md](STRATEGY.md)** | The "what & why" — the two frozen sub-books, the exact federation bookkeeping formula, the fresh-seed/no-rebalance convention, the anti-coupling guard (±€128 probe), how w = 0.70 and s = 1.1 were picked by pre-registered rule, and everything tried and declined. |
| **[PERFORMANCE.md](PERFORMANCE.md)** | The canonical performance read — official pin, both gate scoreboards, yearly/quarterly/monthly tables, the parents in one accounting, measured federation friction (−2.7pp), the scale frontier and the probe-robust adjudication, breach bootstrap, the MT5↔1m crisis-tail gap, the forward one-shot. |
| **[VALIDATION.md](VALIDATION.md)** | The 6-tier battery & sign-off — the delta-0.0 reproduction chain, the pre-registered H-FED-1/2/3 + H-CAPS-1 ladder, the red-team battery with the one FAIL priced into the shipped scale, breach bootstrap + DSR 1.0000, CPCV allocation robustness (w70 re-picked 19/28 folds), the consumed one-shot, DONE/OPEN sign-off. |
| **[RECONCILIATION.md](RECONCILIATION.md)** | The three-engines-one-accounting map — verdict `reconciled`: 41/41 + curves 0.0, 15/15 + 9/9 legs bit-exact, ext engine 38/38 bit-identical, pin rebuild delta 0.0; the measured translation costs (v7 native €532,230 vs record €492,611; −2.7pp friction; 35.6% vs 5.54% tick↔1m tail) and the owed MT5 arbiter. |
| **[TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md)** | The trade profile — FMA3-measured book-level mixing (25,869 fills, turnover 3.1×/day, gross p50 4.5×E, the 33-instrument map, the verified gold stack) + both parents' per-sleeve profiles inherited by citation, with the three-conventions warning. |
| **[DEMO.md](DEMO.md)** | The demo forward-test plan — two parent EA stacks on one account (`InpRisk 6.16` / `GLOBAL_SCALE 3.3`), what does NOT exist yet, monitoring fingerprints against the pin + the forward path, pre-registered decision rules, definition of done. |
| **[DASHBOARD.html](DASHBOARD.html)** | The one-page visual scorecard — hero €665,777, six gate tiles, equity/drawdown charts from the pinned curve (314 weekly points, parents faint), the four levers, the rejected strip, the CONFIRM 4/4 forward strip. Self-contained; open in any browser. |

---

## Research / process layer (the lab beneath the package)

The working records the package is built on — the architectural whitepaper, the
honest multiple-testing ledger, and the pre-registrations committed before their
numbers existed. They stay as the research layer; the seven artifacts above are
the shipped version package.

| Doc | What it is |
|---|---|
| **[../whitepaper/00_WHITEPAPER.md](../whitepaper/00_WHITEPAPER.md)** | The Federation Book — executive summary, document map, definition of done. |
| **[../whitepaper/01_DECONSTRUCTION.md](../whitepaper/01_DECONSTRUCTION.md)** | The two frozen parents — anatomy, firewall history, closed import channels, the engine-of-record decision. |
| **[../whitepaper/02_FEDERATION_DESIGN.md](../whitepaper/02_FEDERATION_DESIGN.md)** | Federation mechanics — the bookkeeping formula, scale-invariance, the anti-coupling guard, the pre-registered evaluation ladder. |
| **[../whitepaper/03_SCORECARD.md](../whitepaper/03_SCORECARD.md)** | Results in research depth — the frontier scorecard, experiment trail, red-team battery, honest caveats. |
| **[../REGISTRY.md](../REGISTRY.md)** | Every configuration ever evaluated, including failures — 16 engine configs + 2 red-team probes, ledger 18 (FMA3-000 … FMA3-FWD). |
| **[../../research/protocol/PROTOCOL.md](../../research/protocol/PROTOCOL.md)** · [HYPOTHESES.md](../../research/protocol/HYPOTHESES.md) · [FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) | The pre-registrations — bars, selection rules, and the one-shot forward criteria, all committed before their numbers existed. |
| **[../../research/outputs/COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)** · [FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md) | Both parents in one accounting (the composite gates + the measured MT5↔1m tail gap) · the consumed 2026H1 one-shot report. |

**Single source of truth (code):** [`strategy_fma3.py`](../../strategy_fma3.py)
(locked config) → [`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py) →
[`research/outputs/fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json)
(+ `fma3_v1_pin_curve.parquet`). Reproduce: `python3 scripts/eval_fma3_pin.py`
(~7 min, expected delta 0.0 on all 5 headline metrics).

---

*Last updated: 2026-07-10. All numbers are in-sample (IC 2020-25); the 2026H1
one-shot is consumed; MT5 real-tick + live demo are the remaining falsification
tests.*
