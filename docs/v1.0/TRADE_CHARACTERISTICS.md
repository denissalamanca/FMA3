# V1.0 trade characteristics — book-level mixing + inherited sleeve profiles

**Two measurement layers, kept separate on purpose.** FMA3 v1.0 changes NOTHING inside either
parent book — the federation ([`strategy_fma3.py`](../../strategy_fma3.py), config hash
`51a7541cc2aaa593`) freezes the v7.0 band book (w = 0.70) and the v3.4 fixed-fraction book (0.30)
at their shipped configs and mixes them in one cross-margined account at s = 1.1. So:

1. **Per-sleeve trade profile — INHERITED BY CITATION, unchanged.** Which sleeves trade, their
   instruments, params, and per-sleeve sizing are byte-frozen (v7 extraction verified 15/15 anchor
   floats delta 0.0; v3.4 pin byte-reproduced — see [RECONCILIATION.md](RECONCILIATION.md)).
   Because w and s are constant positive multipliers on each sleeve's fraction stream, the
   sleeve-level profile — trades/yr, win%, PF, hold, long% — is **unchanged by federation** and is
   quoted below from the parents' own docs, **confirmed, not recomputed** (Part 2).
2. **Book-level mixing statistics — FMA3-specific, measured.** How the two books stack on shared
   instruments, the joint turnover, gross exposure, overnight gold, and each sub-book's
   contribution are new properties of the merged account. They are measured on pinned artifacts
   only ([`package_data.json`](../../research/outputs/package_data.json) via
   `scripts/build_package_data.py`: the locked matrix rebuilt through
   `eval_fma3_pin.build_locked_matrix` — matrix math over **49,379 hours × 33 instrument columns**,
   no engine run — plus [`hcaps1_analysis.json`](../../research/outputs/hcaps1_analysis.json) and
   [`fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json)). That is Part 1.

**All numbers in this document are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5
real-tick + live demo are the remaining falsification tests.** Performance context in
[PERFORMANCE.md](PERFORMANCE.md); structure in [STRATEGY.md](STRATEGY.md).

---

## Part 1 — Book-level mixing statistics (FMA3-measured)

### Ledger volume — engine fill events

| Metric | Value | Source |
|---|---|---|
| Trades, 2020-25 (record-engine fill events) | **25,869** | [fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json) |
| Mean per quarter | **1,077.9** | total / 24 — the pin carries the total only; no per-quarter split is pinned |
| v3.4 alone, same engine | 20,403 | [composite_benchmark.json](../../research/outputs/composite_benchmark.json) |
| v7.0 @ r8 alone, same engine | 6,406 | [composite_benchmark.json](../../research/outputs/composite_benchmark.json) |

A "trade" here is the record engine's convention: one position-changing execution (open, add,
reduce, or close) after min-lot quantization and the 25% rebalance dead-band. The three rows are
comparable to each other and to nothing else — not to MT5 ledger fills, and not to the FIFO
round-trip counts in Part 2. Note the netting effect: the federation prints **25,869 fills vs
26,809 for the parents run separately** (20,403 + 6,406) — on shared instruments the two books'
targets sum at the account level before quantization, and opposing demands cancel instead of
crossing the spread twice. This is one component of the measured −2.7pp federation friction
([PERFORMANCE.md §Federation friction](PERFORMANCE.md)).

### Turnover and gross exposure (locked matrix, w = 0.70, s = 1.1)

| Metric | Value |
|---|---|
| Turnover — mean daily Σ_instruments \|Δfrac\| | **3.08× equity/day** |
| Turnover — p95 daily | 5.86× |
| Turnover — max daily | 12.47× |
| Gross exposure Σ\|frac\| — p50 | **4.52× equity** |
| Gross exposure — p95 | 7.17× |
| Gross exposure — p99 | 7.95× |
| Gross exposure — max | **9.23× equity** |

Basis: the locked federation fraction matrix (sum over instruments of |Δfrac| per hour, summed per
calendar day; gross = hourly Σ|frac| over all 49,379 hours). These are *target* exposures at the
shipped scale — the engine then applies min-lot rounding, the 0.90 margin cap, and per-instrument
leverage. For the realized margin envelope the only measured datapoint is the forward window: max
margin/balance 0.324, min margin level 3.11 ([PERFORMANCE.md §Forward one-shot](PERFORMANCE.md)).

### Per-instrument profile — 33 active columns

Mean |frac| (average absolute target fraction of joint equity) and active share (share of the
49,379 hours with a non-zero target), locked matrix, sorted by mean |frac|:

| Instrument | mean \|frac\| (×E) | active share | Instrument | mean \|frac\| (×E) | active share |
|---|---|---|---|---|---|
| **EURGBP** | **1.353** | 95.3% | CADJPY | 0.038 | 41.8% |
| **XAUUSD** | **0.865** | 98.3% | AUDJPY | 0.038 | 47.0% |
| **USDJPY** | **0.858** | 69.2% | NZDJPY | 0.037 | 45.4% |
| **USTEC** | **0.291** | 86.1% | AUDUSD | 0.029 | 15.0% |
| BTCUSD | 0.084 | 74.0% | NZDUSD | 0.029 | 15.0% |
| EURNZD | 0.080 | 35.5% | US30 | 0.029 | 59.4% |
| ETHUSD | 0.071 | 72.0% | UK100 | 0.022 | 49.1% |
| NZDCAD | 0.070 | 29.2% | DAX | 0.022 | 54.1% |
| EURCAD | 0.070 | 28.4% | XBRUSD | 0.021 | 82.4% |
| CADCHF | 0.070 | 33.4% | XTIUSD | 0.020 | 84.0% |
| AUDCAD | 0.064 | 23.6% | JP225 | 0.019 | 51.0% |
| USA500 | 0.060 | 68.9% | GBPJPY | 0.017 | 37.4% |
| AUDNZD | 0.049 | 29.5% | XAGUSD | 0.015 | 80.8% |
| EURNOK | 0.047 | 29.2% | SOLUSD | 0.014 | 41.6% |
| EURCHF | 0.046 | 27.5% | XNGUSD | 0.012 | 85.9% |
| EURSEK | 0.046 | 27.4% | USDCHF | 0.007 | 12.2% |
| | | | EURUSD | 0.001 | 1.3% |

The book's risk is concentrated in **four lines**: EURGBP (both parents' mean-reversion workhorse
— v7's ZC_EG plus v3.4's meanrev FX-cross leg — 1.35×E on average, active 95% of hours), XAUUSD
(v7's BOOK_XAU stacked on v3.4's three gold-touching sleeves, 86% co-active hours per the M-0
measurement in [composite_benchmark.json](../../research/outputs/composite_benchmark.json)),
USDJPY (v7's S5_JPY carry + S6 opex-USD leg stacked on v3.4's JPY-cross legs), and USTEC (v7's
BOOK_USTEC + v3.4's index legs — the duplicate-edge concern was measured and cleared, ρ = 0.046 on
co-active hours, M-0). The long tail of ~29 small lines (≤ 0.08×E each) is v3.4's breadth: FX
crosses, indices, metals/energy, SOL.

### Overnight gold — the one measured stack (H-CAPS-1, NO-OP verified)

Three v3.4 sleeves and v7's largest sleeve all touch XAUUSD, so the joint overnight gold line was
measured before any scale-up ([hcaps1_analysis.json](../../research/outputs/hcaps1_analysis.json),
on the w70 matrix at s = 1.0 — multiply fractions by 1.1 for shipped scale; the entitlement scales
identically, so the verdict is scale-invariant):

| Joint overnight \|XAUUSD\| | Value (×E, s = 1.0 basis) |
|---|---|
| p50 | 1.10 |
| p95 | 1.75 |
| p99 | 1.97 |
| max | **2.03 = exactly the inherited entitlement** |
| Hours exceeding entitlement | **0** |

Entitlement = |v7's own gold demand| × its share + **1.80×E** (v3.4's structural overnight gold
cap) × its share. The maximum ever reached sits exactly on the entitlement and never above it —
the parents' per-book caps **compose correctly in the merged account**, which is why H-CAPS-1
adopted no new joint cap (**NO-OP**, [REGISTRY.md FMA3-C1](../REGISTRY.md)). Same analysis for the
managed crosses (all v3.4-only — v7 trades none of them): EURCHF max 0.189 vs entitlement 0.195,
EURSEK 0.187, EURNOK 0.191, AUDNZD 0.187 — all within. Joint USTEC: p99 1.13×E, max 1.78×E.

### Sub-book contribution — who earned the growth

w-weighted native-curve growth (share_i = w_i·(mult_i − 1) / Σ_j w_j·(mult_j − 1), native
multiples from the parents' pinned curves, `package_data.json`):

| Sub-book | Capital share | Native multiple (€10k base) | Contribution to federation growth |
|---|---|---|---|
| v7.0 band book | 0.70 | 53.2× | **73.5%** |
| v3.4 book | 0.30 | 45.0× | **26.5%** |

The v7 leg earns roughly its capital share (73.5% on 70% of capital); v3.4's 26.5% is not the
point — its job is the 2022-shaped complementarity (its +32.1% cushioning v7's worst year) and the
disjoint drawdown troughs that let the federation cut DD to 15.73% while both parents alone sit at
~21% ([PERFORMANCE.md](PERFORMANCE.md)).

---

## Part 2 — Per-sleeve trade profiles (inherited by citation, unchanged)

**Sleeve-level trade characteristics are unchanged by federation — the books are frozen.** The
tables below quote the parents' own shipped docs; FMA3 confirms the inputs byte-exactly
([RECONCILIATION.md](RECONCILIATION.md)) but does not recompute the profiles. Book-level mixing
(Part 1) is the only FMA3-measured layer. Each parent's own conventions and caveats travel with
its table — the two tables use *different* trade definitions and must not be cross-compared.

### v7.0 band book (w = 0.70) — from `NSF5/docs/v7/TRADE_CHARACTERISTICS.md`

Source: `/Users/dsalamanca/vs_env/NewStrategyFable5/docs/v7/TRADE_CHARACTERISTICS.md` Part 1 (per-
sleeve profile inherited there from V6, byte-identical; IC Python engine, "trade" = a
position-reducing deal, FIFO-matched):

| Sleeve | % of net P&L | Trades/yr | Win% | PF | Hold (d) | Long% |
|---|---|---|---|---|---|---|
| BOOK_XAU (gold) | ~43 | 269 | 54 | 1.86 | 24 | 81 |
| BOOK_USTEC (NASDAQ) | ~20 | 55 | 65 | 2.00 | 22 | 100 |
| S5_JPY (carry) | ~10 | 15 | 38 | 1.91 | 21 | 100 |
| S1_ETH (crypto) | ~9 | 6 | 69 | 4.46 | 34 | 100 |
| ZC_EG (EURGBP MR) | ~8 | 80 | 67 | 1.57 | 8 | 47 |
| BTC_REP (BTC hurdle momentum) | ~7 | 8 | 60 | 3.41 | 20 | 100 |
| S6_OPEXUSD (3-leg opex USD) | ~4 | 36 | 59 | 1.97 | 4 | 34 |

Portfolio: **~468 trades/yr, win 58%, PF 1.96, long 75%**; every sleeve PF > 1.2. The shape: gold
and EURGBP are the grinders, the crypto pair (ETH PF 4.46, BTC 3.41) are the low-frequency
hunters, ZC_EG and S6 carry the shorts.

**What FMA3 actually carries of this book:** the R8 band-book *held-exposure matrix*, extracted
and byte-reconciled against the NSF5 anchor — including the band rule's realized behaviour, **31
band triggers / 0 harvest fires over 2020-25**
([v7_extract_verification.json](../../research/outputs/v7_extract_verification.json), all 15
anchor floats delta 0.0). The parent doc's Part 2 (the EA's R10 real-tick re-split
characteristics: 57 triggers, delta-resize, harvest backstop) describes the parent's MT5
deployment, not the extracted R8 matrix — it is cited for context, not carried into FMA3's
numbers.

### v3.4 book (share 0.30) — from `FMA2/docs/v3.4/TRADE_CHARACTERISTICS.md`

Source: `/Users/dsalamanca/vs_env/FableMultiAssets2/docs/v3.4/TRADE_CHARACTERISTICS.md`
(MODEL profile off the hourly position engine, FIFO-on-position convention — counts are an upper
bound vs a real ledger, the *shape* is the deliverable; produced by
`research/trade_chars_v34.py` → `outputs/trade_chars_v34.json`):

| Sleeve | Weight | Book% | Trades/yr | Win% | PF | Mean hold | Long% | Role |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| seasonal | 0.180 | 21.8 | 456.0 | 47.1 | 1.21 | 6.9 h | 100.0 | gold NY→Asia overnight drift |
| intraday | 0.168 | 20.3 | 491.3 | 52.8 | 1.21 | 5.0 h | 52.2 | NY-open continuation, flat o/n |
| crypto_smart | 0.130 | 15.7 | 159.9 | 75.6 | 2.32 | 13.3 d | 56.8 | BTC/ETH/SOL momentum |
| meanrev | 0.110 | 13.3 | 185.3 | 44.1 | 1.96 | 12.2 d | 53.0 | FX-cross z-reversion + index dip |
| crisis | 0.100 | 12.1 | 92.6 | 51.0 | 1.70 | 10.9 d | 49.6 | stress-gated gold + JPY snapback |
| mag_xau | 0.050 | 6.1 | 23.8 | 64.3 | 2.31 | 2.1 d | 100.0 | gold $100 round-number magnet |
| carry_breakout | 0.046 | 5.6 | 724.0 | 72.5 | 1.44 | 18.0 d | 98.6 | FX carry gated by trend + Donchian |
| trend_v2 | 0.042 | 5.1 | 153.4 | 38.0 | 1.24 | 13.2 d | 71.8 | lookback-ensemble TSMOM metals/energy |

Portfolio: **2,286.4 trades/yr, win 57.9%, PF 1.42, long 66.3%** (13,709 trades over ~6.0y). The
shape: a barbell of sub-day workhorses (seasonal, intraday — the cadence) and multi-day hunters
(crypto_smart, meanrev, crisis, mag_xau — the quality, PF 1.70–2.32); the shorts live in
crisis/intraday/meanrev. The parent's own caveats apply verbatim (model-not-fills; thin-sample PF
on mag_xau/crypto_smart; windfall-flattery of 2020-21).

### Why the profiles survive federation unchanged

w = 0.70/0.30 and s = 1.1 multiply every sleeve's fraction stream by a constant positive factor.
Trades/yr, win%, PF, hold, and long% are invariant under constant positive scaling (the same
argument FMA2 used for its scale-11 → scale-10 re-pick), and neither book's signals, params, caps,
nor cadences were touched — v7's band re-splits and v3.4's cash-parking both operate on *shares of
their own sub-book*, which the static federation preserves by construction. What scaling does NOT
preserve is account-level execution: min-lot rounding at €7k/€3k sub-book starting capital and
netting on shared instruments change realized fills — that is the measured book-level layer of
Part 1 (25,869 vs 26,809 fills; −2.7pp friction), not a sleeve-level change.

---

## Monitoring flags for the MT5 demo

- **The gold stack is the concentration to watch.** Joint overnight |XAUUSD| reached its
  entitlement exactly (2.03×E at s = 1.0 basis, 0 hours over) with 86% co-active hours between the
  two books' gold sleeves. The demo must confirm the composed caps behave in MT5 the way the
  matrix says — v3.4's 1.80×E structural overnight cap clipping its *combined* gold, v7's own
  demand riding on top — and that the joint line stays at/under entitlement on gold-shock days.
- **EURGBP is the single largest average line (1.35×E, 95% active).** Two mean-reversion sleeves
  from different programs share it; the netting benefit measured in the record engine (fills
  cancelling before the spread is paid) is exactly what a real EA must reproduce. Watch fill
  counts and spread cost on EURGBP first.
- **Gross exposure p99 ≈ 8×E at target.** The record engine's 0.90 margin cap never bound
  in-sample and the forward window peaked at margin/balance 0.324 — but that is 1m-bar evidence;
  the MT5 margin path on real ticks is unmeasured.
- **Trade counts are conventions, not forecasts.** 25,869 record-engine fills, ~468/yr v7
  round-trips, and 2,286/yr v3.4 model-trades are three different definitions. Do not reconcile
  the demo ledger against any of them numerically; reconcile the *shape* (which lines churn, which
  hunt, who carries the shorts).

---

## Honest caveats

- **Part 1 is matrix math, not fills.** Turnover, gross, active shares, and the gold stack are
  properties of the locked *target* matrix (plus pinned engine outputs for the fill counts); MT5
  real-tick execution is the remaining test of all of them.
- **The three trade-count conventions in this doc are mutually incomparable** (record-engine fill
  events vs v7 FIFO position-reducing deals vs v3.4 FIFO-on-position model trades). Every table
  names its convention; never quote across them.
- **No per-quarter trade split is pinned** — 1,077.9/quarter is the flat mean of the pinned total,
  not a measured series.
- **Overnight gold is measured at s = 1.0** on the w70 matrix; fractions scale by 1.1 for the
  shipped book, the entitlement scales identically, and the 0-hours-exceeding verdict is
  scale-invariant — but the absolute ×E numbers in that table are the s = 1.0 basis.
- **Part 2 is inherited, not recomputed.** The per-sleeve numbers are the parents' own shipped
  figures, quoted with their conventions and caveats; FMA3 verified the *inputs* byte-exactly but
  ran no sleeve-level trade analysis of its own.
- **Everything is in-sample.** The one forward datapoint (2026H1, CONSUMED) tested breakdown bars,
  not trade characteristics; the demo ledger is where this profile gets falsified.

**All numbers above are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick +
live demo are the remaining falsification tests.**
