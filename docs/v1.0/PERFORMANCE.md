# V1.0 performance analysis

Canonical result: the **pinned engine-of-record run of FMA3 v1.0** — the static federation
carrying the **v7.0 band book at capital share w = 0.70** and the **v3.4 fixed-fraction book at
0.30** as never-rebalanced virtual sub-accounts of ONE cross-margined €10k IC Markets EU Raw
account, at **global scale s = 1.1** — 2020-01-02 → 2025-12-31, IC feed. Config:
[`strategy_fma3.py`](../../strategy_fma3.py) (config hash **`51a7541cc2aaa593`**); pin script
[`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py) → official numbers
[`fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json) + curve `fma3_v1_pin_curve.parquet`
(all 5 headline metrics rebuilt from config with delta 0.0). Engine of record: FMA2's 1-minute
worst-mark single cross-margined account engine (`research/account_engine_1m.py::simulate_account_1m`)
via the verified [`engine/record_engine.py`](../../engine/record_engine.py) wrapper — 41/41
reconciliation checks delta 0.0 (see [RECONCILIATION.md](RECONCILIATION.md)).

**All numbers in this document are in-sample (IC 2020-25); the 2026H1 one-shot is consumed
(§Forward one-shot); MT5 real-tick + live demo are the remaining falsification tests.**
Structure and mechanics in [STRATEGY.md](STRATEGY.md); the full battery in
[VALIDATION.md](VALIDATION.md); trade profile in
[TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md); research layer beneath this package:
[../whitepaper/03_SCORECARD.md](../whitepaper/03_SCORECARD.md) and
[docs/REGISTRY.md](../REGISTRY.md).

---

## Headline (official pin, engine of record)

| Metric | Value |
|---|---|
| CAGR | **+101.4%** |
| Max equity drawdown — worst-mark | **15.73%** |
| Max equity drawdown — close-mark | 15.62% |
| Sharpe | **2.467** |
| COVID crisis tail | **5.36%** (record-engine basis — see §crisis-tail gap) |
| Final equity (€10k init) | **€665,777** |
| Trades (engine fill events) | 25,869 |
| Negative years | **0 / 6** |
| Negative quarters | **0 / 24** (worst 2022Q4 **+2.9%**) |
| Breach P(maxDD > 30%) — worst-mark bootstrap | **0.0020** |

*Worst-mark is the harsher convention: the engine co-times every open position at its worst
1-minute price inside each bar, so 15.73% is the honest floating-equity drawdown, not a daily-close
smoothing (close-mark 15.62%). The bootstrap median max-DD is 16.80% (§breach bootstrap) — the
realized path is a typical draw, not a lucky one.*

*The trade count (25,869) is the record engine's fill-event convention — position-changing
executions after min-lot quantization and the 25% rebalance dead-band — comparable across every
book measured in this engine, and NOT comparable to MT5 ledger fills or the parents' per-sleeve
FIFO round-trip counts (see [TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md)).*

---

## Gates scorecard

### The owner's six gates (secondary scoreboard)

| Gate | Bar | FMA3 v1.0 | Verdict |
|---|---|---|---|
| CAGR | > 96.1% | **+101.4%** | ✅ PASS |
| Max DD | < 20.9% | **15.73%** (worst-mark; close 15.62%) | ✅ PASS |
| Sharpe | > 2.03 | **2.467** | ✅ PASS |
| Crisis tail (COVID) | ≤ 35.6% | **5.36%** | ✅ PASS* |
| Negative years | 0 | **0 / 6** | ✅ PASS |
| Negative quarters | ≤ 1 | **0 / 24** | ✅ PASS |

All six clear ([fma3_v1_pin.json](../../research/outputs/fma3_v1_pin.json) `gates.owner`, all
`true`). **Standing caveat (\*): the six reference numbers straddle two non-comparable engines** —
96.1 / 20.9 / 35.6 are v7.0's MT5 real-tick R10 figures, while FMA3 is measured in Python 1m
worst-mark accounting. The 5.36% tail clears the 35.6% bar only in the trivial sense; the honest
tail comparison is the composite gate below (5.36% vs the parents' same-engine 5.54%), and the
deployable tail number awaits the MT5 run (§crisis-tail gap).

### The seven composite dimensions (primary scoreboard, pre-registered)

Gates = dimension-wise best of the two parents measured in the engine of record
([composite_benchmark.json](../../research/outputs/composite_benchmark.json); basis pre-registered
in `research/protocol/PROTOCOL.md` before any merged number existed):

| Dimension | Composite gate | Previous holder | FMA3 v1.0 | Verdict |
|---|---|---|---|---|
| CAGR | > 91.5% | v7.0 @ r8 | **+101.4%** | ✅ PASS |
| Max DD (worst-mark) | < 21.22% | v7.0 @ r8 | **15.73%** | ✅ PASS |
| Sharpe | > 2.267 | v7.0 @ r8 | **2.467** | ✅ PASS |
| COVID crisis tail | ≤ 5.54% | v7.0 @ r8 | **5.36%** | ✅ PASS |
| Negative years | 0 | both parents (tied, 0/6) | **0 / 6** | ✅ PASS |
| Negative quarters | ≤ 0 | v7.0 @ r8 (v3.4 had 1) | **0 / 24** | ✅ PASS |
| Breach P(DD>30%) | < 0.0118 | v7.0 @ r8 (v3.4: 0.121) | **0.0020** | ✅ PASS |

**FMA3 v1.0 at s = 1.1 dominates BOTH parents on ALL SEVEN dimensions in the engine of record —
the first fully-dominant point in the two programs' combined history.** v7.0 @ r8 held six of the
seven dimension bests (negY tied with v3.4); the federation takes all seven, buying **+9.9pp CAGR
over the best parent while *cutting* DD by 5.5pp, tail by 0.2pp, and breach by ~6×** — CAGR bought
cheaper than the leverage dial sells it (see §parents table: re-levering v7 to r10 buys +30.6pp
CAGR at +5.0pp DD, breach 0.012 → 0.116 and a negative quarter).

---

## Yearly, quarterly, monthly (pin + `package_data.json`)

Yearly and quarterly returns from the pin; all mark-to-market on the record curve. **Every year
positive, every quarter positive (24/24):**

| Year | Return | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|
| 2020 | **+137.7%** | +11.1% | +17.6% | +30.5% | +39.6% |
| 2021 | +110.9% | **+55.4%** (best Q) | +19.2% | +8.6% | +10.2% |
| 2022 | **+48.8% (worst)** | +12.0% | +11.8% | +15.3% | **+2.9%** (worst Q) |
| 2023 | +88.7% | +18.8% | +7.7% | +19.2% | +23.7% |
| 2024 | +94.5% | +33.4% | +10.7% | +6.8% | +24.3% |
| 2025 | +129.7% | +25.2% | +12.8% | +20.2% | +35.4% |

Monthly returns, computed from the pinned curve (`package_data.json` — asserted to compound back
to the pinned €665,777 to the cent):

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 | +2.6 | +2.3 | +5.8 | +3.8 | +6.1 | +6.8 | +19.8 | +1.3 | +7.6 | +5.4 | +13.1 | +17.1 |
| 2021 | +18.6 | +12.0 | +16.9 | +9.1 | +2.7 | +6.4 | +5.6 | +4.9 | −1.9 | +7.0 | −1.1 | +4.2 |
| 2022 | **−10.7** | +11.1 | +12.9 | +9.5 | −6.3 | +8.9 | +1.5 | +8.6 | +4.6 | +10.8 | −8.0 | +1.0 |
| 2023 | +10.8 | −1.5 | +8.9 | +7.1 | −4.7 | +5.5 | +2.3 | +8.7 | +7.2 | +6.2 | +8.7 | +7.1 |
| 2024 | +1.0 | +14.8 | +15.1 | +8.5 | −0.1 | +2.1 | +4.7 | −2.0 | +4.1 | +5.3 | +12.8 | +4.6 |
| 2025 | +8.1 | +3.8 | +11.7 | +11.8 | +1.5 | −0.6 | +8.4 | +0.2 | +10.7 | **+19.9** | +9.7 | +2.9 |

*(% per month.)* **10 of 72 months are negative** — worst **−10.7% (Jan-2022)**, best +19.9%
(Oct-2025). The worst year (2022, +48.8%) is the year the two parents' weak years overlap least
badly: v3.4 printed +32.1% and v7 @ r8 +55.6% in the same accounting — the structural
complementarity the federation monetizes (book ρ = +0.351, DD troughs disjoint; measurement M-0 in
[composite_benchmark.json](../../research/outputs/composite_benchmark.json)).

---

## The parents in the record engine — one accounting

Both parent books measured for the first time in ONE accounting (FMA3-000,
[composite_benchmark.json](../../research/outputs/composite_benchmark.json)), plus the shipped
federation:

| Book | CAGR | Max DD (worst-mark) | Sharpe | COVID tail | negY | negQ | Breach P(DD>30%) | €10k → |
|---|---|---|---|---|---|---|---|---|
| v3.4 @ s10 (pin) | +88.7% | 21.67% | 1.854 | 7.84% | 0/6 | 1 (2023Q1) | 0.121 | €449,708 |
| v7.0 @ r8 (exact) | +91.5% | 21.22% | 2.267 | 5.54% | 0/6 | 0 | 0.012 | €492,611* |
| v7.0 @ r9 (approx†) | +106.6% | 23.75% | 2.264 | 6.69% | 0/6 | 1 (2022Q4) | 0.044 | — |
| v7.0 @ r10 (approx†) | +122.2% | 26.21% | 2.260 | 7.15% | 0/6 | 1 (2022Q4) | 0.116 | — |
| **FMA3 v1.0 (w70, s1.1)** | **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0/6** | **0** | **0.0020** | **€665,777** |

\* record-engine execution of the extracted v7 matrix; the native band engine prints €532,230 —
the gap is the record engine's ~1-bar execution lag plus its own cost/margin conventions, the
honest price of one common accounting (applied identically to parents and federation).
† linear scale-up of the R8 fraction matrix; the native book's per-sleeve caps do not rescale, so
r9/r10 are approximations and set no gates.

**The alternative to federating was re-levering the better parent, and it is measurably worse.**
r8 → r10 buys +30.6pp CAGR for +5.0pp DD, a 10× breach jump (0.012 → 0.116) and a 2022Q4 negative
quarter — the same CAGR-per-risk trade both parent programs documented. The federation instead
buys +9.9pp CAGR over v7 @ r8 while cutting DD 21.22% → 15.73%, and its scale dial (below) reaches
+140.8% CAGR before hitting any ceiling — the diversification, not leverage, is doing the work.

---

## Federation friction — measured, −2.7pp

The H-FED-1 grid (static federation, native operating points, s = 1.0;
[hfed1_results.json](../../research/outputs/hfed1_results.json)). Pre-registered bars: DD < 20.72%,
Sharpe > 2.317, negY 0, negQ ≤ 0; winner by rule = max Sharpe among passers:

| w (v7 share) | CAGR | Max DD (worst) | Sharpe | COVID tail | Breach (worst) | Ideal CAGR | Friction | Bars |
|---|---|---|---|---|---|---|---|---|
| 0.30 | +86.8% | 18.34% | 2.156 | 6.41% | 0.0088 | +90.2% | −3.41pp | ❌ (Sharpe) |
| 0.40 | +88.7% | 17.88% | 2.305 | 5.75% | 0.0020 | +90.8% | −2.08pp | ❌ (Sharpe) |
| 0.50 | +88.1% | 16.41% | 2.371 | 5.53% | 0.0008 | +91.3% | −3.28pp | ✅ |
| 0.60 | +89.3% | 15.20% | 2.458 | 5.39% | 0.0004 | +91.9% | −2.60pp | ✅ |
| **0.70** | **+89.7%** | **14.38%** | **2.474** | **4.96%** | **0.0004** | +92.4% | **−2.70pp** | ✅ **winner** |

**Friction is real, measured, and priced by the engine rather than assumed away.** "Ideal" is the
paper bookkeeping w·A + (1−w)·B of the two sub-curves; the realized account gives up **−2.7pp
CAGR at the locked point** (92.4% → 89.7% at s = 1.0) to min-lot quantization (sub-books start at
€7k/€3k in 2020, where 0.01-lot rounding is coarsest), joint margin, and netting/costs on shared
instruments. The same netting shows up in the fill counts: the federation prints 25,869 fills vs
26,809 for the two parents run alone in the same engine (20,403 + 6,406). Sharpe was still rising
at the grid edge — **off-grid w80 was NOT tested; the pre-registered grid is binding**
([REGISTRY.md FMA3-001](../REGISTRY.md)).

**Cross-book rebalancing was tested and declined** (H-FED-2, bar: beat static by > +0.5pp CAGR at
≤ +0.3pp DD; [hfed2_results.json](../../research/outputs/hfed2_results.json)):

| Variant | Result | Why declined |
|---|---|---|
| F2a quarterly | +1.12pp CAGR at **+0.43pp DD** (23 events) | over the +0.3pp DD bar |
| F2b band 0.60/0.65 | +0.72pp at **+0.35pp DD** (418 events) | degenerate at w70 — fires every 5d min-gap; over the bar |
| F2b band 0.70 | **−0.34pp CAGR** (22 events) | pays nothing |

Mechanism reading: **cross-book rebalancing couples the disjoint troughs it harvests** — the
static split is what keeps the two books' drawdowns from synchronizing. Static w70 stands.

---

## The scale frontier — why s = 1.1 ships and s = 1.2–1.4 is the aggressive frontier

All seven pre-registered H-FED-3 points on the static-w70 winner
([hfed3_results.json](../../research/outputs/hfed3_results.json)); every point compliant with the
pre-committed ceilings (DD < 20.9%, negQ ≤ 1, negY 0, breach ≤ 0.12, tail ≤ 35.6%), negQ 0
everywhere, Sharpe scale-flat (2.45–2.48):

| s | CAGR | Max DD (worst-mark) | Sharpe | COVID tail | Breach P(DD>30%) | €10k → | Note |
|---|---|---|---|---|---|---|---|
| 0.8 | +66.8% | 12.21% | 2.475 | 3.73% | 0.000 | €214,623 | |
| 0.9 | +77.2% | 13.04% | 2.452 | 4.47% | 0.000 | €308,682 | |
| 1.0 | +89.7% | 14.38% | 2.474 | 4.96% | 0.0004 | €464,991 | the raw H-FED-1 winner |
| **1.1** | **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0.0020** | **€665,777** | **SHIPPED (probe-robust)** |
| 1.2 | +114.4% | 17.17% | 2.470 | 5.88% | 0.0046 | €967,259 | aggressive frontier |
| 1.3 | +127.4% | 18.59% | 2.468 | 6.44% | 0.0138 | €1,378,091 | aggressive frontier |
| 1.4 | +140.8% | 19.89% | 2.466 | 7.09% | 0.0294 | €1,942,739 | H-FED-3 ceiling-rule pick |

**The adjudication.** The pre-committed H-FED-3 rule ("largest compliant s") mechanically selected
**s = 1.4**. Then the red-team parameter-perturbation probe **failed on the w+20% axis**
([rt_perturbation.json](../../research/outputs/redteam/rt_perturbation.json)):

| Probe | CAGR | Max DD | ΔDD | Sharpe | ΔSharpe | Tail | negY / negQ |
|---|---|---|---|---|---|---|---|
| w−20% (w = 0.56) | +88.9% | 15.45% | +1.06pp | 2.422 | −0.05 | 4.85% | 0 / 0 |
| **w = 0.70 (locked)** | **+89.7%** | **14.38%** | — | **2.474** | — | **4.96%** | **0 / 0** |
| w+20% (w = 0.84) | +89.0% | 17.97% | **+3.59pp** ❌ | 2.416 | −0.06 | 5.04% | 0 / 0 |

Because a never-rebalanced federation's realized split *drifts* (measured band ~0.63–0.75 between
quarterly marks, [hfed2_results.json](../../research/outputs/hfed2_results.json)), the ceilings
must hold across the ±20% probe surface, not only at the locked w. The adjudicated shipping rule
([REGISTRY.md FMA3-RT](../REGISTRY.md)): **largest s with all ceilings at the locked w AND both
±20% probes** — binding at the w+20% probe (17.97% × 1.1 ≈ 19.8% < 20.9%; at s = 1.2 ≈ 21.6% >
20.9%) → **s = 1.1 ships**. The FAIL was not waived: it was **priced**, at −39.4pp CAGR
(s 1.4 → 1.1). Every quality metric is stable across the probe surface (Sharpe −0.05/−0.06, CAGR
within 0.8pp, negQ 0 everywhere); only DD moves, monotonically toward the measured v7-alone
endpoint (21.22% at w = 1.0) — the geometry of a smooth frontier, not a fitted seat (full case in
[VALIDATION.md](VALIDATION.md) and [../whitepaper/03_SCORECARD.md](../whitepaper/03_SCORECARD.md)).

---

## Breach bootstrap — P(maxDD > 30%)

House bootstrap (`worst_mark_breach`, inherited from FMA2's pin tooling via
[`engine/record_engine.py`](../../engine/record_engine.py)): **20-day-block stationary bootstrap,
5,000 resampled 6-year paths, seed 20260709**, worst-mark applied through co-timed daily
worst/close dip factors — i.e. each resampled path carries the real intraday marking violence of
the days it draws.

| Book (same engine) | P(maxDD>30%) close | P(maxDD>30%) worst | Median bootstrap max-DD (worst) | p95 |
|---|---|---|---|---|
| **FMA3 v1.0** | **0.0010** | **0.0020** | **16.80%** | **23.28%** |
| v7.0 @ r8 | 0.0052 | 0.0118 | 19.66% | 26.57% |
| v3.4 @ s10 | 0.0932 | 0.1208 | 23.42% | 33.53% |

A 30%+ drawdown appears in **2 of 5,000** resampled histories (composite gate < 0.0118 — cleared
~6× over; the H-FED-3 ceiling was ≤ 0.12). The realized 15.73% sits just under the bootstrap
median (16.80%) — a typical draw — and even the 95th-percentile resampled history (23.28%) stays
far from the 30% breach line. Note what this is *not*: a block bootstrap resamples the realized
2020-25 days, so it prices path-reordering risk, not regime risk — the corr-spike/fat-tail
scenarios live in the parents' own validation batteries and are not re-proven here.

---

## The measured MT5 ↔ 1m crisis-tail gap — never cross-quote

The two accounting worlds price the COVID crash **6.5× apart, and both are honest**
([COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)):

| v7.0 COVID tail | Engine | Value |
|---|---|---|
| MT5 real-tick @ R10 | tick, real spread blowouts | **35.6%** |
| Record engine @ r8–r10 | Python 1m worst-mark, IC bars | **5.5–7.2%** (5.54% at r8) |

Tick-granularity spread blowouts of Mar-2020 simply do not exist in 1m bars — the same book, the
same crash, 35.6% vs 5.5%. Consequences, stated as rules:

- **Crisis-tail numbers from the record engine must never be quoted against MT5 numbers.** FMA3's
  5.36% is comparable to the parents' 5.54% / 7.84% (same engine), and to nothing else.
- **The federation's tick-granularity tail is unknown by construction.** v3.4 has never had a tick
  run at all; the federation has only the 1m record accounting. The owner's-machine MT5 real-tick
  run is the deployable arbiter of the tail — it is the next falsification test after the consumed
  one-shot, before the live demo.
- The same gap explains the negQ conventions: v7.0 scores 0/24 negQ in this engine but 3/24 on MT5
  real-tick (its −21.8% COVID quarter is a tick artifact of the same event). FMA3's 0/24 is a
  record-engine statement.

---

## Forward one-shot — 2026H1, CONSUMED, verdict CONFIRM

The one pre-registered out-of-sample shot has been taken
([FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md),
[forward_oneshot.json](../../research/outputs/forward_oneshot.json); criteria committed in
`research/protocol/FORWARD_TEST.md`, sha256 `c40ab6fdf4de2eab…`, before any 2026 number existed).
Fresh €10,000 seed 2026-01-01 at (0.70, 0.30), s = 1.1, engine `record_engine_ext` (bit-identity
gate passed), Duka forward feed, 14-symbol coverage, USA500 proxying USTEC; window truncated at
server 2026-04-30 23:59:59. Results verbatim:

| # | Bar | Value | Result |
|---|---|---|---|
| F1 | window worst-mark DD < 20.9% | 17.67% | PASS |
| F2 | window return > −10% | +12.34% | PASS |
| F3 | no joint stop-out or margin-cap breach event | stop-outs 0, cap-binds 0 | PASS |
| F4 | each sub-book window return > −20% | v7 +15.99%, v3.4 +13.59% | PASS |

**4/4 PASS → pre-registered interpretation: CONFIRM** (proceed to MT5 demo deployment, the
deployable arbiter). Window metrics (2026-01-01 → 2026-04-30, server time):

- Window return: **+12.34%** (€10,000 → €11,234)
- Worst-mark DD: **17.67%** (close-to-close 17.58%)
- Daily Sharpe (annualized, 120 days — wide error bars): **1.17**
- Monthly returns: 2026-01 **+14.94%**, 2026-02 −0.25%, 2026-03 +0.41%, 2026-04 −2.42%
- Sub-books (native curves): v7 +15.99%, v3.4 +13.59%
- Margin envelope: max margin/balance 0.324 (cap 0.90), min margin level 3.11 (stop-out at 0.50)
- Breach bootstrap (20d blocks, short-window caveat): close 0.0002, worst 0.0002

**Caveats disclosed in advance (FORWARD_TEST.md), carried with the verdict:** 4 months ≈ 85
trading days — the bars are breakdown detectors, not performance targets; **Duka feed, not IC**
(documented ~8pp CAGR_bd feed divergence on 2020-25); **v3.4 ran at ~0.88× reduced breadth**
(uncovered legs zeroed, per-symbol disclosure in `v34_frac_1h_fwd_report.json`); **USA500 proxies
USTEC** (corr 0.89, column-level; v3.4's own USTEC leg zeroed) — the proxy book is a directional
confirmation, NOT the deployed book; swap carry = flat extension of last 2025 policy rates; open
positions at the window-end stamp marked, not closed. The 2026H1 holdout is now permanently
**CONSUMED** ([REGISTRY.md FMA3-FWD](../REGISTRY.md)).

---

## Honest caveats

- **Everything is in-sample, on a window mined twice over.** IC 2020-25 was the development sample
  of both parent programs (FMA2 ≈ low-hundreds of design trials; NSF5 ≈ 7,560 prescreens + ~258
  engine tests) and FMA3 added 18 ledger configs on top. **DSR 1.0000 at n = 20 trials** (stable
  at ×4 stress, n = 80; [rt_dsr.json](../../research/outputs/redteam/rt_dsr.json)) says only that
  *FMA3's own* few-parameter selection — one w grid, one cadence family, one scale grid — cannot
  explain a Sharpe of 2.47 by luck **within FMA3's ledger**. It says nothing about the parents'
  mining: the sleeves' alpha is assumed from the parents' validation records, not re-proven here.
- **Forward-honest Sharpe expectation: ~1.6–2.0, not 2.47.** v3.4 shipped with a disclosed
  forward-honest band of 1.2–1.5 vs 1.85 in-sample (ratio ≈ 0.65–0.81); the same ratio on the
  pinned 2.467 gives roughly **1.6–2.0**, and `FORWARD_TEST.md` budgeted the more conservative
  1.2–1.5 band outright. The consumed one-shot printed **1.17 on 120 days** — marginally below the
  conservative band, on a window too short to settle it. Judge the live book against the bands,
  not against 2.467.
- **The crisis tail is engine-relative and the deployable tail is unknown.** 5.36% is a 1m
  worst-mark number; the measured v7 tick↔1m gap is 35.6% vs 5.5%. No tick run of the federation
  exists — MT5 on the owner's machine is the arbiter.
- **The forward CONFIRM is a Duka-feed, proxy-book confirmation.** ~8pp known feed divergence,
  0.88× v3.4 breadth, USA500-for-USTEC — directional, not a reconciliation. It clears breakdown
  bars; it does not certify the in-sample level.
- **Federation friction (−2.7pp CAGR) and min-lot coarseness at €10k are genuine** and priced in;
  the v7 leg additionally carries a ~1-bar execution lag vs its native engine (identical across
  all compared configs — like-for-like, but absolute levels are not the native book's).
- **The capital split drifts (~0.63–0.75 measured band) and is never rebalanced.** The
  probe-robust scale rule exists precisely to absorb this: all ceilings hold across w 0.56–0.84 at
  s = 1.1. The aggressive frontier s 1.2–1.4 is documented, compliant at the locked w, and NOT
  probe-robust — do not deploy it on the strength of this document.

**All numbers above are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick +
live demo are the remaining falsification tests.**
