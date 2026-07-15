# v3 — CURRENT STATE (native EA + performance variation)

*Last updated 2026-07-15. This is the live status layer over the v3.0 package; where it
disagrees with the older docs (which describe the superseded `FableFederation_V3` replay
EA / RECON-4), **this doc wins.** Every number here is cited to a session artifact.*

---

## 1. What changed since the v3.0 docs were written

The v3.0 package documents `FableFederation_V3.ex5` — a **CSV-replay** executor (RECON-4,
1m-OHLC, 3 runs). It has been **superseded** by **`FableBookNative.mq5`** — the **native,
live-computing** EA: it computes `f_core / f_sat / a / b / book_frac[33]` **live each bar
from the terminal's own synchronised multi-symbol feed**, no frozen CSV replay. Status:
software-complete, mirror-gated, full-window certified on real broker execution, **ships
trade-disabled** (`InpAllowLiveTrading=false`, zero live orders until explicitly flipped).

- **R1 (compute fidelity)** — the live compute replays the golden `book_frac` curve at
  `max|diff| = 5.06e-13` (= the golden CSV's own 12-dp rounding floor; the genuinely-new
  live Core-target seam is **bit-exact 0.0**). Full 2020-2025, 24/24 quarters.
- Three tester-harness defects were found and fixed this cycle (all **tester-only; the
  live binary is unchanged**): DE40 digits guard (RECON-8i), full-window clock stall on a
  not-yet-listed symbol (RECON-8j), Sat-sleeve `b`-freeze on the same (RECON-8k).

## 2. The model of record — UNCHANGED (frictionless upper bound)

| Preset | Dial | Final equity | CAGR | MaxDD (worst-mark) | Sharpe |
|---|---|---:|---:|---:|---:|
| **IC** | s = 1.6 compounding | **€3,872,872** | +170.2% | 22.58% | 2.465 |

Reproduced to the euro by `model/v3/reproduce.py`, config `51a7541cc2aaa593`, w = 0.70.
**This is a frictionless ceiling, not a forecast** — it applies no swap, spread, or
commission on the final book.

## 3. The deployable reality — full-window native run (the headline that matters)

`FableBookNative` over the **full 2020-2025 window on the real ICMarketsEU M1 feed**
(1-min-OHLC, s = 1.6, fresh €10k, report `ReportTester-11078280_36.xlsx`, RECON-8l):

| Metric | Native EA (real execution) | Golden (frictionless) | Δ |
|---|---:|---:|---|
| Final equity | **€2,934,301** (net +2,917,980) | €3,872,872 | 0.76× |
| CAGR (rate terms) | **+158.0%** | +170.9%¹ | growth-factor retention **95.2%** |
| Worst drawdown | **22.9%** | 22.2% | **+0.7pp** |
| Sharpe · Profit factor | 2.07 · 1.51 | 2.465 · — | — |
| **Position fidelity** | **69 self-check mismatches / 6 yr** | — | ~perfect |
| Trades | 17,145 | — | — |

¹ window-matched golden (2020-01-02…2025-12-30); the 2020-2025 headline golden is +170.2%.

**Read it right:** the engine is *faithful* (Core replay bit-exact, drawdown matches the
golden to **+0.7pp**, position fidelity essentially perfect over six years). The ~€0.94M /
~13pp CAGR gap is **real-execution friction**, decomposed below — not a defect and not a
strategy shortfall.

## 4. The performance variation — where the 12.9pp CAGR gap comes from

Decomposed (multi-agent, adversarially verified; deals reconcile to net profit to the
cent). The gap is **~entirely friction, dominated by swap**, and is **not uniform**
(concentrated in crisis-adjacent 2020 / 2022 / 2025):

| Channel | CAGR pp | Share | Basis |
|---|---:|---:|---|
| **Swap** (overnight financing) | **8.0** | **66%** | MEASURED — €590,436 |
| Spread | ~2.3 | 19% | MODELED — €162k (band 1.2–4.5pp) |
| Commission | 0.6 | 5% | MEASURED — €40,500 |
| **= Execution friction** | **~10.9** | **~86%** | measured €630,936 + modeled spread |
| De-levering (caps/margin/min-lot) | ~0 | 0% | **FALSIFIED** — 99.9996% target fill, gross flat while balance ×35, margin never binds |
| Feed/signal (sleeve drift) | ~0 | 0% | **favorable** — Core bit-exact, blend +1.3% *above* golden |

**Implication for the dial + the validation engine:** swap scales with held notional ∝ s,
so friction erodes the marginal return of leverage — the frictionless optimum `s` is too
high (a second, independent reason after the margin-gate). The golden should be read as an
**upper bound**; the friction-realistic **~€2.9M / +158%** net is the deployment number.

The worst-drawdown +0.7pp is the *same* Oct–Dec 2022 macro episode (Oct-21 BoJ yen
intervention + Nov FTX/CPI) the golden also lives through — real-execution friction on a
shared event, not an EA artifact (no margin call, no feed spike, no single-symbol blowout).

## 5. Reconciliation status (RECON-8 series)

| Ledger | What | Verdict |
|---|---|---|
| RECON-8i | DE40 digits guard + 37-symbol metadata reconcile | fixed; contract/volume drifts handled by BookExec live sizing |
| RECON-8j / 8k | full-window clock stall + Sat `b`-freeze (not-yet-listed symbol) | fixed (tester-only) |
| RECON-8l | clean full-window reconciliation | **RECONCILED** on engine fidelity (DD +0.7pp, 95% retention, fidelity ~perfect) |
| Sat `b_h` +4.88% | live-vs-record **price-feed basis** — swap/eurq/commission/engine all **bit-identical (0.0)**; NOT a port bug; favorable to EA | root-caused |
| Sat record-feed port cert | the coverage gap Core has and Sat lacked | **PASSED** — `TestSatEquityChain` 24/24 quarters bit-exact (`max\|d_eq\|=0`, final balance 434,132.989, 20,403 trades), judged into `sat_mql5_parity.json`. Port faithful → confirms the +4.88% live drift is 100% the feed basis, not the port. |

## 6. Open items (roadmap)

1. ~~Sat record-feed port cert~~ — **DONE** (24/24 quarters bit-exact, `sat_mql5_parity.json`; PR #3 merged).
2. **Real-tick crisis certification** — COVID/2022 on real ticks (the gate 1m-OHLC can't satisfy).
3. **FTMO dial** — deferred; breaker-cadence + warm-validated scale cut (~s0.30-0.35).
4. **RECON-9 adjudication** (Opus) → **deploy decision** (owner, demo-forward first).

## 7. Honest caveats

- All the above is **1-minute OHLC, not real ticks** — generated-tick crisis wicks are
  optimistic; real-tick certification (open item #2) is mandatory before any deploy.
- The ~5%/yr growth-factor haircut (swap-led) is **real and recurring** — the live account
  will run below the frozen model by that margin; it is the physics of holding leveraged
  overnight positions, quantified, not a bug.
- The EA **ships trade-disabled** and sends zero live orders until `InpAllowLiveTrading` is
  explicitly flipped on a live chart — which should not happen until the open items clear.
