# Full-window 2020-2025 IC run — trade characteristics & performance by sleeve and regime

*Source: FableBookNative report #36 (s=1.6, fresh €10k, real ICMarketsEU feed, 1-min-OHLC).
Every figure reconciles to the €2,917,980.40 net to the cent. Three lenses, cross-checked.*

> **Standing docs-battery member — REGENERATE this doc on every `/docs` + dashboard update,**
> from the *then-current* model-of-record run: parse that run's MT5 deals report (trade
> characteristics + regime slices off the `Balance` path), plus the sleeve standalone curves
> `research/outputs/v7_book_equity_1m.parquet` (Core `eqc`) and
> `research/baselines/fma2/v34_s10_pin_curve.parquet` (Sat `equity`), and the blended golden
> `research/outputs/hrisk1_s160_curve.parquet`. Keep the three lenses (trade characteristics
> by sleeve · performance by sleeve · performance by regime) and the **shared-symbol caveat**
> (the 6 shared symbols' P&L is joint/un-attributable — the standalone curves are the only
> faithful per-sleeve view).

---

## Executive read — the five things that matter

1. **Profit is extraordinarily concentrated — in *instruments*, not cleanly in a *sleeve*.** Two symbols, **XAUUSD (+€1.18M, 40%) and USTEC (+€621k, 21%), are 61.6% of the entire book**; the top 5 (add USDJPY, ETH, BTC) are 88.9%. All five are **shared** symbols — traded by *both* sleeves as one netted position — so their P&L is jointly owned and **cannot be attributed Core-vs-Sat from the deals.**
2. **The "Core = 93.5%" headline is a labelling artifact, not signal ownership.** Bucketing by ticker puts 93.5% under "Core-8" — but **91.3% of net sits in the 6 shared symbols** (blended). The only *pure-sleeve* realized numbers are **Core-only €66.8k (2.3%)** and **Sat-only €188.3k (6.5%)**; among un-shared names, Sat actually out-earns Core ~2.8:1.
3. **Standalone, the two sleeves are near-equal earners** — Core 53.2× (CAGR 94%), Sat 45.0× (CAGR 89%) — but Core is the *cleaner* one (Sharpe 2.96 vs 2.53, DD 19.5% vs 21.7%, worst month −9% vs −17%). **Core = ballast, Sat = the risk/vol sleeve.**
4. **The blend's real value is diversification, not either sleeve's raw alpha.** The sleeves are near-orthogonal (**ρ = 0.109**), which cuts blended vol ~22% and lifts Sharpe to 3.62. The book **spends that headroom on leverage (s=1.6 size), not on lower risk** — which is exactly why it runs ~23% DD instead of blowing past it.
5. **The run is a slow build then a gold/Nasdaq explosion.** **2025 alone = +€2.08M = 71% of the entire 6-year net**, driven by XAUUSD + USTEC. The only real stress is early 2022 (worst *realized* DD −21.5%). The worst drawdown is a **Core-instrument event in every measure**; Sat never caused the max DD.

---

## Method & reconciliation
- 29,361 trade deals (12,216 `in` + 17,145 `out`; the "~17,145 trades" = out-deal count) → **5,008 flat-to-flat position cycles**, zero sign-flips, all close.
- Net P&L per deal = Profit + Commission + Swap. **Σ = €3,548,916.31 − €40,500.19 comm − €590,435.72 swap = €2,917,980.40** (final balance €2,927,980.40).
- Worst DD = **equity-DD-relative 23.27%** (report) — the subject's "~22.9%".

---

## A. Trade characteristics by sleeve

| Metric | CORE (8) | SAT-only (25) | WHOLE BOOK |
|---|---:|---:|---:|
| Round-trip cycles | 2,138 | 2,870 | 5,008 |
| Net P&L (€) | **2,729,686** | **188,294** | **2,917,980** |
| Share of P&L / of trades | 93.5% / 42.7% | 6.5% / 57.3% | 100% |
| Win rate | 52.4% | 47.0% | 49.3% |
| Expectancy / trade (€) | 1,276.75 | 65.61 | 582.66 |
| Median P&L / trade (€) | 3.96 | −0.25 | −0.02 |
| Profit factor | **2.96** | **1.16** | 2.13 |
| Total swap (€) | **−507,526** | −82,910 | −590,436 |
| Mean / median holding | 5.2 d / 17 h | 7.8 d / 16 h | 6.7 d / 17 h |
| ≤1-min-hold cycles | 1.0% | **11.5%** | — |
| Long net€ / Short net€ | +2,562,219 / +167,467 | +267,457 / **−79,163** | +2,829,676 / +88,304 |

*(CORE here = the 8 Core-membership symbols, incl. the 6 shared — see §B for the caveat.)*

**Style.** **Core is a concentrated, pyramiding trend engine** — 8 symbols, 42.7% of trades, PF 2.96, and it *scales into and holds* trends (only 1% of its cycles are same-bar; 34% run past a day). Its monster positions are visible in the deal structure: the largest single trade is a **213-deal XAUUSD pyramid held 130 days (+€678k)**, and one **XAUUSD position ran 2,247 deals over 651 days** (paying −€229k swap by itself). **Sat is a broad, higher-turnover mean-reversion diversifier** — 25 symbols, 57.3% of trades, but PF 1.16 (barely above break-even); 11.5% of its cycles close within the minute. **Sat carries the trade count; Core carries the P&L. The median trade in every group is ≈ €0 — profit is entirely a right-tail phenomenon.** Sat's weak point is its short book (1,097 shorts at 39.9% win = −€79k).

**Swap concentration.** Total carry −€590,436; **86% falls on Core**, and just **XAUUSD (−€358k) + USTEC (−€167k) = 89% of all swap** (the longest-held, biggest-lot books). Only 6 symbols *earn* swap, led by **USDJPY +€74k** (long-yen carry working for the book).

### Per-symbol (all 33, ranked by net P&L)
| Symbol | Sleeve | Cyc | Win% | Net € | Swap € | Comm € | Hold μ/med | Largest win/loss € |
|---|---|--:|--:|--:|--:|--:|---|--:|
| XAUUSD | CORE(shared) | 796 | 49.4 | **1,177,450** | −357,724 | −15,728 | 2.7d/12h | 678,253 / −9,252 |
| USTEC | CORE(shared) | 825 | 52.2 | **620,788** | −167,076 | 0 | 2.1d/5h | 125,593 / −62,138 |
| USDJPY | CORE(shared) | 60 | 38.3 | 321,323 | +74,275 | −3,841 | 23.9d/4.3d | 184,172 / −5,887 |
| ETHUSD | CORE(shared) | 66 | 42.4 | 263,208 | −17 | 0 | 23.4d/10.6d | 152,233 / −22,104 |
| BTCUSD | CORE(shared) | 75 | 41.3 | 211,290 | 0 | 0 | 21.1d/9.0d | 88,210 / −19,105 |
| XAGUSD | SAT | 70 | 20.0 | 73,557 | −6,120 | −324 | 23.6d/15d | 84,336 / −4,111 |
| EURGBP | CORE(shared) | 174 | 74.7 | 68,839 | −52,746 | −12,935 | 11.8d/6d | 24,023 / −54,749 |
| US500 | SAT | 1,349 | 49.4 | 55,814 | −14,272 | 0 | 25.1h/5h | 29,765 / −44,899 |
| NZDCAD | SAT | 32 | 68.8 | 42,303 | −1,189 | −707 | 19.6d/16d | 11,203 / −3,496 |
| NZDUSD | CORE-only | 71 | 62.0 | 36,473 | +112 | −1,120 | 4.3d/4.3d | 9,920 / −5,570 |
| DE40 | SAT | 106 | 64.2 | 34,428 | −7,208 | 0 | 9.1d/42.5h | 12,432 / −2,734 |
| AUDUSD | CORE-only | 71 | 57.7 | 30,316 | −4,351 | −1,026 | 4.3d/4.3d | 7,634 / −3,806 |
| JP225 | SAT | 61 | 41.0 | 25,551 | −6,532 | 0 | 17.5d/10.5d | 21,175 / −6,517 |
| CADCHF | SAT | 38 | 63.2 | 21,164 | +991 | −870 | 18.5d/15.8d | 18,112 / −6,824 |
| EURCHF | SAT | 30 | 70.0 | 20,504 | −1,111 | −212 | 19.3d/15d | 5,257 / −498 |
| SOLUSD | SAT | 51 | 29.4 | 16,176 | −84 | 0 | 16.8d/12d | 39,248 / −7,854 |
| AUDCAD | SAT | 30 | 83.3 | 14,187 | −3,368 | −532 | 17.0d/13.5d | 8,279 / −5,606 |
| EURNOK | SAT | 29 | 65.5 | 14,009 | −623 | −255 | 20.9d/20d | 4,315 / −3,182 |
| GBPJPY | SAT | 36 | 30.6 | 8,676 | +2,757 | −122 | 21.4d/3.5d | 9,132 / −1,698 |
| US30 | SAT | 298 | 65.8 | 1,097 | −13,811 | 0 | 3.1d/1min | 16,156 / −8,994 |
| EURUSD | SAT | 1 | 100 | 300 | +2 | −0.4 | 27d/27d | 300 / 300 |
| AUDJPY | SAT | 36 | 38.9 | 76 | −1,435 | −416 | 26.7d/11d | 11,883 / −17,833 |
| XNGUSD | SAT | 197 | 13.7 | −975 | −3,278 | 0 | 7.8d/2min | 19,880 / −5,018 |
| AUDNZD | SAT | 27 | 70.4 | −1,491 | −4,024 | −366 | 23.0d/19d | 5,321 / −14,178 |
| EURNZD | SAT | 35 | 62.9 | −3,455 | −1,220 | −459 | 21.6d/21d | 11,663 / −27,346 |
| USDCHF | SAT | 17 | 35.3 | −3,597 | +1,325 | −127 | 14.4d/7d | 2,740 / −2,016 |
| CADJPY | SAT | 40 | 37.5 | −4,372 | −1,806 | −371 | 21.5d/11d | 12,733 / −10,849 |
| EURCAD | SAT | 38 | 65.8 | −4,749 | −1,549 | −392 | 15.8d/12.7d | 5,809 / −13,118 |
| UK100 | SAT | 66 | 43.9 | −13,832 | −11,358 | 0 | 14.3d/7.7d | 2,982 / −15,458 |
| EURSEK | SAT | 26 | 57.7 | −14,788 | −1,225 | −207 | 22.6d/23d | 4,980 / −9,612 |
| NZDJPY | SAT | 50 | 30.0 | −24,961 | −2,005 | −489 | 18.6d/12.5d | 11,370 / −22,933 |
| XBRUSD | SAT | 70 | 14.3 | −30,735 | −2,737 | 0 | 25.3d/16.3d | 1,827 / −10,024 |
| XTIUSD | SAT | 137 | 33.6 | −36,592 | −3,031 | 0 | 12.8d/3.1d | 3,655 / −4,386 |

Biggest losers are all Sat energy/JPY-cross names (XTIUSD −37k, XBRUSD −31k, NZDJPY −25k). Commission hits only FX + precious metals; index/crypto/energy are spread-only.

---

## B. Performance by sleeve

### Lens 1 — standalone sleeve alpha (frictionless golden curves, €10k base, s=1.0)
| Metric | CORE (v7) | SAT (v34) |
|---|---:|---:|
| Total return multiple | **53.2×** | **45.0×** |
| CAGR | **94.0%** | **88.6%** |
| MaxDD (worst-mark) | **19.5%** | **21.7%** |
| Annualized vol | 23.9% | 27.1% |
| Sharpe (rf=0) | **2.96** | **2.53** |
| Worst month | −9.2% (May-22) | **−17.1% (Jan-22)** |
| **Monthly correlation** | **ρ = 0.109** | |

Near-equal earners; **Core is the cleaner, lower-risk sleeve** (ballast), **Sat is the higher-vol, deeper-tail sleeve** (risk). At ρ=0.109 the static 0.70/0.30 blend cuts vol from a naive 24.9% to **19.4% (−22%)** and lifts Sharpe to **3.62**. That diversification is the book's edge.

**Capital tilt auto-rotates toward the winner** (w·a/j vs (1−w)·b/j): 70/30 at t0 → **64/36 at YE-2021** (Sat led 2020-21) → **73/27 at YE-2025** (Core led every year 2022→2025). The blend mechanically overweights whichever sleeve is compounding faster.

### Lens 2 — realized in-book attribution (the honest three-way split)
The 2 **Core-only** symbols are **AUDUSD, NZDUSD**; the 6 **shared** are **BTCUSD, ETHUSD, EURGBP, USDJPY, USTEC, XAUUSD**.

| Group | #sym | Net € | % of net | Attribution |
|---|--:|--:|--:|---|
| Core-only (AUDUSD, NZDUSD) | 2 | **66,788** | 2.3% | **pure Core** |
| Shared (XAU, USTEC, USDJPY, ETH, BTC, EURGBP) | 6 | **2,662,898** | **91.3%** | **JOINT — un-attributable** |
| Sat-only | 25 | **188,294** | 6.5% | **pure Sat** |

> **⚠ The critical caveat:** "Core-8 = 93.5%" over-credits Core, because **91.3% of the book lives in the 6 shared symbols whose one netted position is fed by *both* sleeves** (w·a/j from Core **plus** (1−w)·b/j from Sat). That P&L cannot be split from the deals. The only faithful per-sleeve view is the **standalone curves (Lens 1)** — where the sleeves are near-equal. Among *un-shared* names, Sat (€188k) out-earns Core (€67k) ~2.8:1.

**Reconciliation vs the frictionless ceiling:** golden blend €3,872,872 vs realized €2,927,980 = **€944,892 (24%) haircut** — ~€631k identifiable friction (94% swap) + ~€314k execution/1m-OHLC-fills/lost-compounding. The blended golden's worst-mark DD (22.58%) ≈ realized equity DD (23.27%) — consistent.

---

## C. Performance by regime

| Regime | EA ret% | EA DD% | Sharpe | net €P&L | swap € | Core-8 € | Sat-25 € | dominant |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| COVID crash (Feb19–Mar23'20) | +2.5 | −10.8 | 0.8 | +258 | −144 | +270 | −12 | Core FX/gold (USTEC −586 the drag) |
| Reflation (Mar24–Dec'20) | +110.9 | −12.3 | 3.8 | +11,825 | −3,058 | +9,973 | +1,852 | Core (USTEC, EURGBP, BTC/ETH) |
| 2021 risk-on bull | +317.2 | −8.9 | 3.6 | +71,321 | −17,010 | +56,682 | +14,639 | **Core crypto** (ETH+BTC; *not* Sat) |
| 2022 H1 hike+LUNA | +16.8 | **−21.5** | 1.0 | +15,789 | −11,056 | +20,247 | **−4,457** | Core USDJPY carry saves it |
| 2022 H2 bear+FTX | +43.0 | −14.7 | 2.7 | +47,089 | −9,654 | +42,950 | +4,139 | USDJPY + **US500 (Sat's best)** |
| 2023 chop | +107.9 | −21.3 | 2.7 | +169,010 | −66,844 | +147,608 | +21,402 | Core USTEC/USDJPY/XAU |
| 2024 bull+Aug unwind | +161.1 | −9.6 | 3.7 | +524,653 | −196,252 | +489,099 | +35,554 | **gold breakout** (XAU +196k) |
| 2025 late-cycle | +244.3 | −12.9 | 4.1 | **+2,077,632** | −286,253 | +1,962,563 | +115,069 | **XAU +972k, USTEC +454k** |

**Worst drawdown depends entirely on the measure — three different regimes:**
- **Realized balance −21.5%** → trough **Jan-2022** (Core USTEC + gold giveback).
- **Golden worst-mark −22.5%** → **Feb-2021** (crypto-bull mark).
- **Live M2M equity ~−25%** → **2022 H2**. Report headline ≈ 22.9% (worst-mark family).

**Quarterly backbone (EA realized ret% / DD%):** only **2 negative quarters in 24** — 22Q1 (−0.9% / −21.5%) and 23Q2 (−4.7% / −20.6%), both the deep-DD windows. The rest is a compounding staircase, accelerating hard in 24-25.

**Narrative.** A Core-instrument story throughout: survive COVID flat-to-up (haven FX/gold offset the Nasdaq hit), compound the 2020-21 reflation on USTEC/EURGBP/crypto, take the *only* real bruise in early 2022 (rate-hike/LUNA, −21.5%, rescued by the USDJPY carry trend), then run a clean 2023 chop into a **gold-and-Nasdaq regime that dominates 2024-25** — 2025 alone is 71% of the whole run. Sat is a small, near-orthogonal breadth overlay that absorbs most single-symbol drags (oil, JPY crosses, SOL) and only earns real alpha in the 2022-H2 index mean-reversion.

---

## D. What this implies
1. **Return & risk both concentrate in a handful of shared instruments (XAUUSD, USTEC), driven by both sleeves.** Neither sleeve "owns" the P&L; the standalone alpha is near-even and the realized book is 91% joint.
2. **Core is ballast, Sat is the risk/breadth overlay.** The blend's value is the ρ=0.109 diversification, which the s=1.6 dial converts into *leverage headroom* — the reason ~23% DD buys +158% CAGR.
3. **Concentration is the standing risk.** 61.6% of P&L in two instruments (both gold/Nasdaq, both leveraged-long, both the biggest swap payers) means the book is effectively a **levered long gold + Nasdaq trend** with a diversifying overlay. A regime that breaks *both* (a simultaneous gold + tech reversal) is the tail the historical window didn't test.
4. **Swap is the scaling headwind** (−€286k in 2025 alone, 86% on the two big Core longs) — it grows with the book and is the leverage-coupled cost that argues (again) for a more conservative dial than the frictionless optimum.
