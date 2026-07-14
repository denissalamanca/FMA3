# FMA3 parent deconstruction — the two frozen books

**The authoritative "what & why" for the two locked parent books that FableMultiAssets3
federates: NewStrategyFable5's Core (7 equal-capital slot-equity sleeves + `BAND_SYM_25`
concentration-band re-split + H9 delta-resize, R10) and FableMultiAssets2's Satellite
(8 fraction-of-equity sleeves × `GLOBAL_SCALE` 10 with cash-parked weights and two structural
hard limits, in one cross-margined account).** Code sources of truth: Core =
`NSF5/mt5/ea/PortfolioV7.mq5` + preset `V7_CORE7BAND_R10_IC.set` (MT5, live) and the READ-ONLY
Python band engine `NSF5/mt5/reconcile/gbandrebal/sim.run_generic` (= `v51_bandharvest._run_window`);
Satellite = `FMA2/strategy_fable.py` (shipped config, `config_hash 48c09199fbf83d82`) +
`FMA2/research/eval_v34_pin_s10.py` on `FMA2/research/account_engine_1m.py::simulate_account_1m`;
FMA3 measurement bridges = [`engine/record_engine.py`](../../engine/record_engine.py) +
[`engine/v7_bridge/extract_positions.py`](../../engine/v7_bridge/extract_positions.py).
Both parents are **FROZEN** — no sleeve internals change in this campaign
(see [PROTOCOL.md §3](../../research/protocol/PROTOCOL.md)). The blend design built on top
of them is **[02_FEDERATION_DESIGN.md](02_FEDERATION_DESIGN.md)**; the composite benchmark that
prices them in one accounting is
**[COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)**.

**All numbers below are in-sample (IC 2020–25; Core's native MT5 headline additionally includes
2026-H1 real-tick). There is no post-2025 holdout in this document — the pre-registered 2026H1
one-shot and the live demo are the falsification tests.**

---

## 1. Parent A — Core (NewStrategyFable5)

### 1.1 What Core is

**Core = the V6 core-7 book (7 equal-capital sleeves, 1/N, IC Markets EU Raw, €10k) with the
calendar-quarterly re-split replaced by the concentration-band trigger `BAND_SYM_25`, plus the H9
delta-resize on each re-split** (its own definition,
[NSF5 docs/v7/STRATEGY.md §1](../../../NewStrategyFable5/docs/v7/STRATEGY.md)). Design
philosophy: a multi-sleeve, regime-diverse book of economically independent edges, equal-weighted
1/N, always-on and self-gating, with **no market-timing / regime-switching overlay** (de-risking
backfires on a convergent book — every backward throttle NSF5 tried inverted, −2 to −31pp).
Leverage `R` is the single mechanical knob; the re-split is the only active portfolio action.
Sleeves are causal (data through the prior daily close) and inverse-vol sized on **slot equity**
— the property the whole re-split premium is conditional on (§1.5).

### 1.2 The seven sleeves

Equal capital, **1/7 each**. Per
[NSF5 docs/v7/STRATEGY.md §2](../../../NewStrategyFable5/docs/v7/STRATEGY.md):

| # | Sleeve | Instrument | Edge (one-liner) | % of net P&L |
|---|---|---|---|---|
| 1 | **BOOK_XAU** | XAUUSD | Donchian breakout ensemble + overnight value-area | **~43%** |
| 2 | **BOOK_USTEC** | USTEC (NASDAQ-100) | 200-MA equity regime + Monday effect | ~20% |
| 3 | **S5_JPY** | USDJPY | rate-divergence carry, trend-gated | ~10% |
| 4 | **S1_ETH** | ETHUSD | crypto momentum (regime + fast/slow) | ~9% |
| 5 | **ZC_EG** | EURGBP | multi-window z-score mean-reversion (only long/short sleeve) | ~8% |
| 6 | **S6_OPEXUSD** | 3-leg USD basket (UJ/AU/NZ) | opex-week USD calendar basket, ~1/21 each | ~4% |
| 7 | **BTC_REP** | BTCUSD | financing-hurdle momentum (−20%/yr hurdle) | ~7% |

Cross-sleeve correlations ~0 (mean absolute ~0.05–0.15); the only correlated pair is ETH↔BTC
(ρ 0.54) at ~15% of the book. Portfolio profile: **~468 trades/yr, win 58%, PF 1.96, ~75% long;
every sleeve PF > 1.2**. Gold at **~43% of P&L** is the single concentration the parent program
monitors (and the direct motivation for FMA3's H-CAPS-1 combined gold cap).

### 1.3 `BAND_SYM_25` mechanics — the exact rule

The rule below is load-bearing and must be implemented **exactly** in any re-derivation
([NSF5 docs/v7/STRATEGY.md §4](../../../NewStrategyFable5/docs/v7/STRATEGY.md)):

1. **Trigger check — once per day at the server-midnight rollover.** Compute each slot's share of
   total book equity, `share[n] = (realized balance + floating P&L)[n] / Σ slots`. Re-split the
   *whole* book to equal capital if **any** slot's share is:
   - **above the up-band:** `share > 0.25` (`InpBandUp`), or
   - **below the down-band:** `share < (1/N)/1.75 = 0.0816` at N = 7 (`InpBandDownDiv = 1.75`).

   *Timezone caveat (verified against the code, not the prose):* the parent docs say "00:00 UTC",
   but `gbandrebal/sim.py::first_share_trigger` resamples the tz-naive **broker server-time** bar
   index (UTC+2/+3, hour 0 = 17:00 ET). The boundary is **server midnight**, decided at the daily
   close and acted at the **next** server midnight (the FMA3 extraction's trigger ledger shows
   `decided 2020-03-16 → act 2020-03-17`, etc.). An implementation on UTC calendar days diverges
   from both the Python anchor and the EA.
2. **Minimum gap: 5 days between re-splits** (`InpBandMinGapDays = 5`). Quoted verbatim from the
   parent: load-bearing, "in every validated run, and must be implemented exactly, not
   approximated."
3. **N-slot floor, computed at runtime.** The down-band floor is `(1/N)/1.75` from the
   **enabled-sleeve count**, never hardcoded 0.0816 — knockout runs rescale it (e.g. a 6-sleeve
   book uses `(1/6)/1.75 = 0.0952`).
4. **S6 three-leg → one-slot aggregation.** The three S6 legs (S6_UJ / AU / NZ, ~1/21 each) are
   **summed into ONE slot before the share test**, so the book is scored as **7 slots** with floor
   0.0816. Iterating the legs separately would give 9 slots (floor 0.0635) and misfire the
   down-band.
5. **k = 2.5 harvest backstop (retained, subsumed).** V6's re-seed of any slot > 2.5× its
   window-start seed stays configured (`InpHarvestK = 2.5`). Under the symmetric band it fires
   **0 of 31** triggers in the idealized Python book; in MT5 real-tick it fired **5×** in six
   years, all legitimate — **4 of the 5 fired inside the 5-day band min-gap** (where
   `BandTriggered()` is muted but `HarvestTriggered()` is not; BTC Jan-2021, S5_JPY Apr/May-2022).

The band is symmetric because concentration is a two-sided risk: the **up-band caps a runaway
winner** (in the no-rebalance counterfactual ZC_EG compounded to **53% of book equity**), and the
**down-band re-seeds a starved loser** — on the realized Python R10 path the book is meaningfully
down-band-heavy (16 of 27 triggers). The validated R8 Python book fired **31 re-splits in six
years** (~5/yr); the MT5 EA fires ~2× the idealized count **by design** (realized slot equity +
floating P&L carried across delta-resizes drift more), with **0 non-genuine fires** in
reconciliation.

### 1.4 H9 delta-resize

At each re-split, **same-sign sleeves ADD/REDUCE to the exact new equal-capital target** instead
of close-all-and-reopen, refunding the boundary spread + commission; **reversals still
close + reopen**. In the EA↔Python reconciliation, **98.9% (266/269)** of held-and-active resizes
used the delta path (266 delta + 3 reversal, plus 253 flat-target closes, over 58 re-splits × 9
enabled sleeve-slots). **Honest scope:** the **+1.5pp** benefit exists **only in MT5** — the
validated Python band book close-and-reseeds and does not model it
([NSF5 docs/v7/RECONCILIATION.md](../../../NewStrategyFable5/docs/v7/RECONCILIATION.md)).

### 1.5 Why the re-split premium exists — the H8 science

The band is the operational form of a *measured* mechanism, not a tuned curve-fit
([NSF5 docs/v7/research/H8_REBALANCE_SCIENCE.md](../../../NewStrategyFable5/docs/v7/research/H8_REBALANCE_SCIENCE.md)):

| H8 finding | Number |
|---|---|
| Re-split premium (quarterly vs never) | **+26.36pp CAGR / +7.63pp DD** (no-rebalance book: 53.5% CAGR / 33.7% tick-DD) |
| Ordering (timing luck) refuted | all **600** block-shuffled re-runs keep a positive premium; ordering contribution ~0pp (worst ≤ +5.7pp) |
| Conservative **structural share** | **78%** — distributional (fat-tail concentration harvest), not temporal |
| Band vs calendar (T6 frontier) | `BAND_SYM_25` **+9.8pp CAGR / −1.6pp DD** vs the quarterly incumbent (15.70% bd / 19.44% tick vs 17.31% / 20.74%) |
| Band width 0.25 | widest band on the plateau still satisfying the <20% tick-DD goal (breaches at up = 0.28) — **a deployable center by constraint, not a tuned peak** |

The premium is **carried by the high-vol, ~0-correlation sleeves** (annualized standalone vol at
base R8: BOOK_XAU 85%, ZC_EG 83%, USTEC 78%, S5_JPY 74%) and **diluted by low-vol streams**
(S6 22.9%; the FMA2 imports crisis 10.5% and seasonal 4.6% — see §3.3). Removal deltas on the
premium: BOOK_XAU −4.72pp, S5_JPY −4.35pp, ZC_EG −2.86pp, USTEC −1.50pp (carriers) vs S6 +9.53pp,
BTC_REP +3.93pp, S1_ETH +3.26pp (diluters).

**The premium is conditional on slot-equity sizing.** Under fixed-notional sizing the DD benefit
**flips to −7.31pp** — rebalancing re-grosses instead of de-risking (H8 M2×M4). This single fact
is the structural firewall of §3.2: the band cannot be imported into Satellite's fixed-fraction
convention, and any change of the sizing anchor voids the measured benefit.

### 1.6 The leverage frontier (native MT5 real-tick, reports `_32`–`_37`)

| R | CAGR | Maximal eq-DD (€-worst) | Relative eq-DD (crisis %-worst) | Sharpe | min ML | note |
|---|---|---|---|---|---|---|
| 5 | 70.9% | 17.0% | 20.9% | 1.98 | 225% | band *worse* than V6 here — never run below R8 |
| 8 | 86.5% | 21.2% | 30.4% | 1.97 | 210% | pre-validated fallback |
| **10** | **96.1%** | **20.9%** | **35.6%** | **2.03** | **190%** | **live — Sharpe peak, lowest DD of the high-R points** |
| 12 | 99.8% | 21.4% | 39.2% | 2.00 | 200% | CAGR knee (flat beyond) |
| 15 | 99.8% | 25.8% | 39.7% | 1.90 | 186% | DD climbing |
| 20 | 99.6% | 26.3% | 39.3% | 1.85 | 187% | discard |

The Maximal (€-worst) DD is ~R-invariant; the Relative (crisis-tail) DD scales sharply with R —
this is why R stopped at 10, below the R12 knee. The band is what makes high R viable: V6's
calendar re-split blew to ~37% eq-DD at R15/R20 while Core held ~26%. The later V8 re-lever study
confirmed tick CAGR saturates (R10→R12 = only +3.7pp at ~1:1 crisis-tail cost) and shipped
**R10 / m=0 unchanged**.

### 1.7 Native official numbers (two engines, never conflated)

| Engine | Config | Headline |
|---|---|---|
| **MT5 real-tick** (deployable arbiter) | `PortfolioV7.mq5`, R10, IC-native costs, 2020-01→2026-06 crash-inclusive | **CAGR 96.1% / Maximal eq-DD 20.9% / Relative (COVID) 35.6% / Sharpe 2.03 / PF 1.67 / min ML 190% / 0 negY / 3 negQ M2M** (2020Q1 −21.8%, 2021Q3 −1.4%, 2022Q4 −6.3%) |
| **Python band engine** (validation anchor) | `gbandrebal/sim.run_generic`, R8, IC 2020-25, idealized close-and-reseed | **CAGR 89.7% (bd) / 15.70% bd-DD / 19.44% tick-DD / Sharpe 2.58 / €532,230 / 31 band + 0 harvest triggers** — the run on which the 7/7 hard-gate battery passed |

At matched R8 the MT5 tester retains ~96% of the Python CAGR (86.5/89.7) — "observed, not
guaranteed."

### 1.8 Measured record-engine profile (this campaign's accounting)

FMA3 re-executed the Core book **for the first time in the engine of record** (§4). The extractor
re-ran the exact anchor pipeline capturing per-1m-bar lots
(`engine/v7_bridge/extract_positions.py`; **all 15 anchor floats delta 0.0** vs the pinned
`engine_reproduce.json`, including 31 band + 0 harvest triggers —
[v7_extract_verification.json](../../research/outputs/v7_extract_verification.json)). Source:
[composite_benchmark.json](../../research/outputs/composite_benchmark.json):

| Core in record engine | CAGR | Max DD (worst-mark) | Max DD (close) | Sharpe | COVID tail | negY | negQ | Breach P(DD>30%) | n_trades |
|---|---|---|---|---|---|---|---|---|---|
| **r8 (exact)** | **+91.5%** | **21.22%** | 20.91% | **2.267** | **5.54%** | 0/6 | **0/24** | **0.012** | 6,406 |
| r9 (linear approx†) | +106.6% | 23.75% | 23.40% | 2.264 | 6.69% | 0/6 | 1 (2022Q4) | 0.044 | 5,951 |
| r10 (linear approx†) | +122.2% | 26.21% | 25.83% | 2.260 | 7.15% | 0/6 | 1 (2022Q4) | 0.116 | 6,104 |

† linear scale-up of the R8 fraction matrix; the native book's per-sleeve caps do not rescale, so
r9/r10 are approximations and **set no gates**. Per-year at r8 (record engine): 2020 +119.9%,
2021 +83.8%, 2022 +55.6% (worst), 2023 +78.0%, 2024 +87.7%, 2025 +123.3%. The pinned r8 record
run prints final equity **€492,611** (`composite_benchmark.json`); its CAGR/DD/Sharpe row above
is the gate basis. In this accounting Core's 2020Q1 is **not even negative** — the −21.8% MT5
quarter is a real-tick artifact of the engine gap quantified in §4.

### 1.9 Honest caveats (Core, carried forward)

- **Everything is in-sample**; the 2026-H1 window was already consumed by NSF5 for reporting.
- The DD-halving is a **slot-equity-sizing × re-split product**, not a market anomaly; changing
  the sizing anchor voids it (−7.31pp flip under fixed-notional).
- Ship the band strictly at up ≤ 0.25 (tick-DD breaches the 20% goal at 0.28); never run below R8
  (the R5 anomaly); the 5-day min-gap and the 7-slot S6 aggregation are exact-implementation
  requirements.
- Band-width sensitivity is real (family CAGR spread 79.3–89.7%) — a weaker robustness guarantee
  than a calendar-offset grid.
- Corr-spike (ρ = 0.8 → ~35% DD at R8) and tail ×2 (~36%) scale ~linearly with R; the #1 hidden
  risk is the sleeves co-moving.
- Gold is ~43% of P&L; the book survives without it (drop-gold 70.7% CAGR) but a persistent
  gold-regime failure is the largest degradation path.

---

## 2. Parent B — Satellite (FableMultiAssets2)

### 2.1 What Satellite is

**Satellite = the shipped v3 composition — 8 alpha sleeves in ONE cross-margined €10k IC Markets EU
Raw account (`ENGINE_MODEL="single"`) — mechanically re-levered from `GLOBAL_SCALE` 11 to 10 by a
pre-registered rule** ([FMA2 docs/v3.4/STRATEGY.md](../../../FableMultiAssets2/docs/v3.4/STRATEGY.md),
config authoritative in `FMA2/strategy_fable.py:60-110`). Each sleeve emits an hourly matrix of
signed notional exposure **as a fraction of joint account equity**; there are no per-sleeve
sub-accounts — one balance, one margin pool, one joint stop-out. It is a consistency-first book:
its native headline is **1/24 negative quarters (worst −1.42%)**, and its crisis/meanrev/seasonal
seats *pay* during stress (2020 was its best year, +127.6%).

### 2.2 The eight sleeves (signal logic, weights, F3 caps)

Weights are the **F3 downward-only conviction caps** applied to the v1 frozen weights
(`FMA2/docs/v2.0/F3_DURABILITY.md`; stress-validated — breach probability 0.095 capped vs 0.329
frozen at scale 9):

| Sleeve | Instruments | Signal (one-liner) | v1 frozen → F3 cap | Standalone Sharpe | LOO ΔSharpe |
|---|---|---|---|---|---|
| **meanrev** | 10 FX crosses + 6 indices | 60d z-score hysteresis reversion (enter \|z\|>2.25, exit 0.75) + index dip-buy above the 200d MA | 0.140 → **0.110** | 1.109 | **+0.367 (#1)** |
| **carry_breakout** | 21 FX + commodities/indices | rate-differential carry (top-5 net, 63d momentum-gated) + long-only Donchian breakout ensemble | keep **0.046** | 0.854 | +0.056 |
| **seasonal** | XAUUSD | gold NY→Asia overnight drift, server hours 23–05 (zero swap; 06:05 hard-flat) | 0.247 → **0.180** | 1.257 | +0.169 |
| **intraday** | USA500/USTEC | NY-open drive continuation, held rows 16–20, flat overnight (21:05 hard-flat) | keep **0.168** | 0.92 | +0.14 |
| **crisis** | XAUUSD + JPY crosses | stress-gated long gold (gold > 50d MA gate) + short JPY-cross snapback | 0.139 → **0.100** | 0.516 | +0.004 |
| **trend_v2** | metals/energy | 6-lookback TSMOM tanh ensemble with consensus gate | keep **0.042** | 0.383 | −0.025 (kept: tail-DD diversifier — removal DECLINED, v3.1) |
| **crypto_smart** | BTC/ETH/SOL | asymmetric momentum (longs pay −20%/yr financing, shorts pay zero) | 0.219 → **0.130** | 1.023 | +0.214 |
| **mag_xau** | XAUUSD | gold $100 round-number magnet (long while 3–18% below the level) — the sole v3.0 import survivor | **0.050** (new) | 1.25 / 1.463 (dual-cited recipes) | +0.096 |

Weights sum **0.826**. Diversification: mean pairwise |corr| 0.088, ENB 7.28/8.

### 2.3 The cash-park doctrine

**The freed 0.174 of weight is CASH-PARKED, never renormalized** (OPS-8: renormalizing doubles
ceiling-breach odds; the Sharpe ladder shows the park costs exactly 0 Sharpe — CAGR is recouped
via `GLOBAL_SCALE`, never by re-inflating survivor weights). On any sleeve kill the freed weight
goes to cash, not to the survivors. **Implementation trap, disclosed in the parent and re-verified
here:** `strategy_fable.py::build_portfolio_positions` (line 127) *renormalizes* by the 0.826 sum
(effective ×12.1) — it is the fast-sim screening printer only. The official construction is
`eval_v34_pin_s10.build_c2()` = `ensemble.combine(sleeves, RAW weights) × 10` then
`apply_hard_limits`, and FMA3's [`engine/books.py`](../../engine/books.py) **delegates to
`build_c2()`** rather than re-deriving it, precisely so no drift is possible.

### 2.4 The two structural hard limits

Both are **rules, not fitted constants**, applied to the final scaled matrix
(`FMA2/research/ensemble.py::apply_hard_limits`) and both are stress-load-bearing:

| Limit | Rule | Uncapped stress | Capped stress |
|---|---|---|---|
| **HL-1 overnight gold** | combined \|XAUUSD\| ≤ `seasonal_weight × scale` = 0.18 × 10 = **1.80×E** on server hours ≥21 or <6 (self-adjusts with scale: 1.62×E@s9, 1.98×E@s11) | stack maxes **4.24×E**; −9% Monday gap marks **−33.3%** | **−17.7%** |
| **HL-2 managed crosses** | \|EURCHF/EURSEK/EURNOK/AUDNZD\| ≤ **0.5×E** at ALL hours (nominal meanrev demand 1.10×E at s10 — the cap binds) | −15% peg break → **18–23%** | **8.2–14.0%** |

Disclosed residual: **intraday-session gold is uncapped at 3.68×E** (~−18% on a −5% mid-session
shock) — a declared future-version item in the parent, and one input to FMA3's H-CAPS-1.

### 2.5 `GLOBAL_SCALE` mechanics and the pre-registered re-pick

The official book = `Σ(sleeve_pos × raw_weight) × GLOBAL_SCALE(10)`, then hard limits. Scale is
the **single leverage knob**; Sharpe is leverage-invariant (~1.85 at every scale — a frictionless
build scores 2.248; the −0.388 execution drag loses the Sharpe-2 gate). Negative quarters are
**vol-drag artifacts of leverage** (drag ~scale²), fixable only by scale, never by composition —
which is the entire rationale for Satellite. The re-pick rule was committed verbatim in
[FMA2 docs/v3.4/PREREGISTRATION.md](../../../FableMultiAssets2/docs/v3.4/PREREGISTRATION.md):
*"Pin scales {9,10,11}. ADOPT the SMALLEST scale with negQ ≤ 1 AND CAGR ≥ 85%. If none satisfies
both, KEEP scale 11."*

| Scale | CAGR | DD (worst-mark) | Sharpe | negQ | Breach | Verdict |
|---|---|---|---|---|---|---|
| 9 | 79.4% | 19.9% | 1.88 | 1 | 0.061 | fails CAGR ≥ 85% |
| **10** | **88.7%** | **21.7%** | **1.85** | **1** | **0.121** | **ADOPTED** |
| 11 | 99.9% | 23.2% | 1.86 | 2 | 0.198 | fails negQ ≤ 1 |

Pre-committed demo rule: on drift, step scale DOWN toward 9 preserving ratios; **never scale up
on good performance** (s11 fails negQ — upside is not a mandate for leverage).

### 2.6 The 1-minute worst-mark engine conventions

`FMA2/research/account_engine_1m.py::simulate_account_1m` — the file, not `core.py`
(a misattribution in the parent-doc prose corrected during FMA3 recon). These conventions ARE the
FMA3 engine of record (§4), so they are itemized:

- **Single cross-margined EUR account**, €10,000 initial, quarters 2020Q1..2025Q4 run as chunks on
  the union 1m grid with balance/lots/entry chained across chunks.
- **Per-minute loop order:** (1) swap accrual at the first minute ≥ server midnight (triple-Wed FX,
  triple-Fri indices, daily crypto; policy-rate step model + markup); (2) desired lots =
  `fraction × balance / (price × contract × EURquote)`, floored to `lot_step`; (3) **margin cap
  0.9×balance** with proportional shrink of ALL positions; (4) fills at the minute's bid/ask OPEN
  crossing the full spread + **€3.25/lot/side commission on FX & metals** (index/crypto free); a
  25% rebalance band skips small same-sign changes; (5) co-timed marks — close equity on
  bid_c/ask_c and **worst equity marking longs at bar low (bid_l) and shorts at bar high (ask_h)**;
  (6) joint stop-out closing everything at worst marks if worst equity < 0.5 × margin used.
- **Worst-mark MaxDD** = max over minutes of (running peak of close equity − worst equity)/peak —
  the headline DD convention.
- **Causality:** the hour-h hourly target is held over hour h+1's minutes (≥1-minute causal gap).
- **negY/negQ:** close-to-close mark-to-market on full equity by calendar year/quarter.
- **House breach bootstrap:** stationary Politis–Romano block bootstrap, **20-day mean blocks**
  (the deliberately non-flattering convention), 5,000 paths, seed 20260709, resampling daily close
  returns jointly with each day's co-timed worst/close dip factor → P(maxDD > 30%).

### 2.7 Record-engine profile (the official pin — native and record engine coincide)

Satellite's native pin **is** a record-engine number by construction. Pin:
`FMA2/research/outputs/v34_s10_pin_1m.json`, byte-reproduced through the FMA3 wrapper **twice**
(41/41 reconciliation checks delta 0.0, curve max-abs-delta 0.0 —
[verify_record_engine.json](../../research/outputs/verify_record_engine.json)):

| CAGR | Max DD (worst-mark) | Sharpe | COVID tail | negY | negQ | Breach worst / close | €10k → | n_trades |
|---|---|---|---|---|---|---|---|---|
| **+88.66%** | **21.67%** | 1.854 | **7.84%** | 0/6 | **1 (2023Q1 −1.42%)** | **0.121** / 0.093 | **€449,708** | 20,403 |

Per-year: 2020 +127.6%, 2021 +136.6%, 2022 +32.1% (worst — and exactly the year that cushions
Core, whose record-engine 2022 is its own worst at +55.6%), 2023 +76.9%, 2024 +80.5%,
2025 +86.7%. Native gate score 4/5 (only the non-blocking Sharpe > 2 misses; leverage-invariant).

### 2.8 Honest caveats (Satellite, carried forward)

- **All in-sample 2020–25**; the DEV/HOLD split was consumed by the v1 program; DSR 0.394 at
  honest cumulative N≈474 trials is a standing yellow flag (mitigated by trial correlation, band
  0.39–0.59).
- The headline is flattered by the 2020-21 windfall (rolling Sharpe ~3.5); the durable 2022-25
  regime is ~1.76, and the parent's **disclosed forward band is Sharpe ~1.2–1.5** (honest ≈1.45)
  — the merged book must be judged against that band, not 1.85.
- Satellite has **no MT5 real-tick run ever** — its reconciliation verdict is PARTIAL by construction
  (headless brain↔pin parity is 6.66e-16, but broker fills are demo-only evidence).
- Chop-fragility: Sharpe 0.76 in chop vs 2.31 in trend; only meanrev/intraday are chop-positive.
- MKT-3 joint-gap stress touches the −25% kill region at s10 (−28.1% worst, ×1.5 cliff 41.2%);
  MKT-4 gold-bear margin is thin (28.2% vs the 30% ceiling).

---

## 3. The firewall history — and why both single-book import channels are CLOSED

The two books were built **firewalled from each other** (Satellite under an explicit alpha firewall
against NewStrategyFable5; the owner lifted it for this campaign on 2026-07-10). The firewall was
breached exactly twice, in opposite directions, under pre-registered gauntlets — and both channels
are now formally closed. This is the negative space that defines FMA3's licensed design space.

### 3.1 Channel A — the band mechanism into Satellite: NOT IMPORTABLE (H8)

**Closed on structural incompatibility, not on a failed backtest.** The H8 rebalance science
([NSF5 docs/v7/research/H8_REBALANCE_SCIENCE.md](../../../NewStrategyFable5/docs/v7/research/H8_REBALANCE_SCIENCE.md))
proved the re-split premium is **78% structural vol-harvesting across ~0-corr high-vol sleeves,
conditional on slot-equity sizing**: under fixed-notional sizing the DD benefit **flips to
−7.31pp** because rebalancing re-grosses. Satellite's fixed-fraction single account *continuously*
rebalances to fractions by construction — it already sits at the continuously-rebalanced limit,
and there are no slot equities for a band to measure. FMA2's own import review reached the same
verdict independently
([FMA2 docs/v3.0/RECON.md](../../../FableMultiAssets2/docs/v3.0/RECON.md): band/H8 mechanism
"NOT IMPORTABLE").

### 3.2 Channel B — FMA2 sleeves into the NSF5 book: EXHAUSTED, 0-for-10 (H14/H15)

Seven byte-identical FMA2 sleeve streams were evaluated twice
([H14_FABLE_RESULTS.md](../../../NewStrategyFable5/docs/v7/research/H14_FABLE_RESULTS.md),
[H15_FABLE2_RESULTS.md](../../../NewStrategyFable5/docs/v7/research/H15_FABLE2_RESULTS.md)):

| Test | Book structure | Result |
|---|---|---|
| H14 crisis ADD | V6-era **quarterly** book | **+4.00pp** matched-DD (banked at the time) |
| H14 seasonal ADD | V6-era quarterly book | +1.43pp (banked at the time) |
| H15 T-A crisis ADD | **Core band** book | **−20.89pp raw / −23.40pp matched-DD — INVERTED** |
| H15 T-B1 carry replaces S6 | Core band book | −13.47pp |
| H15 T-B2 crisis replaces S6 | Core band book | +1.35pp < +3pp gate; "plausibly 100% rebalance-schedule chaos"; **banned from re-litigation** |

Final tally: **2 evaluations, 10 book-level tests, 0 adoptions.** The channel is declared
EXHAUSTED; a third pass on the same seven streams is pre-refused as "p-hacking by installment"
(md5-check the position parquets before any claimed "new" evaluation). The H14 +5.57pp
crisis+seasonal figure was formally **RETIRED** as a quarterly-cadence relic
(`NSF5/docs/v8/research/V8_RELEVER_POLICY.md`).

### 3.3 Channel C — NSF5 sleeves into Satellite: the one-shot 2015-19 window is CONSUMED

FMA2's v3.0 gauntlet ([FMA2 docs/v3.0/RECON.md](../../../FableMultiAssets2/docs/v3.0/RECON.md))
ran four frozen NSF5 ports through three pre-registered stages, using the clean 2015-19 pre-period
as one-shot OOS: **S6_OPEXUSD killed** (2015-19 Sharpe −0.32), **VOLSTRUCT killed** (−0.64),
**F1 failed** the overlay corr bar (ρ 0.685 to intraday) and lost the head-to-head on both
windows; **MAG_XAU was the sole survivor** (Stage-2 Sharpe 0.62) and is already inside Satellite at
weight 0.050. That OOS window is spent for these candidates — it cannot be reused without
converting it into in-sample data.

### 3.4 The load-bearing lesson

The same crisis stream is **+4.00pp on a quarterly equal-capital book and −20.9pp on a band
book**: sleeve value is **cadence/structure-conditional**, and no verdict transfers across
portfolio architectures without re-testing under the target structure. Consequently the only
genuinely untested level left between these two programs is the one that **changes neither
book's internal structure**: capital blend of the two books as wholes —
[02_FEDERATION_DESIGN.md](02_FEDERATION_DESIGN.md). A related standing rule: FMA2's `intraday`
sleeve and NSF5's F1 are the **same edge** (ρ 0.87 on shared active days); a merged entity must
never carry both. (`BOOK_USTEC` is a *different* USTEC sleeve — measured against `intraday` in
M-0 at ρ 0.046, cleared.)

---

## 4. The engine-of-record decision — and the measured two-engines problem

The owner's original six goal numbers (CAGR > 96.1 / DD < 20.9 / Sharpe > 2.03 / crisis ≤ 35.6 /
0 negY / ≤1 negQ) **straddle two non-comparable engines**: the first four are MT5 real-tick R10
numbers, while the negQ convention is only satisfied in Python 1m close-to-close accounting (Core
itself scores 3/24 negQ on MT5 tick). No engine ever produced all six simultaneously — so
"beats both parents" was unfalsifiable until FMA3 pinned ONE accounting.

**Decision ([PROTOCOL.md §1](../../research/protocol/PROTOCOL.md)):** the FMA3 engine of record is
**FMA2's 1-minute worst-mark single cross-margined account engine** (§2.6), imported read-only and
wrapped by [`engine/record_engine.py`](../../engine/record_engine.py). Verification, both sides:

| Bridge | Check | Result |
|---|---|---|
| `engine/record_engine.py` (Satellite pin re-run) | 41 metric/curve checks vs the pinned reference | **41/41 delta 0.0**, curve max-abs-delta 0.0 ([verify_record_engine.json](../../research/outputs/verify_record_engine.json)) |
| `engine/v7_bridge/extract_positions.py` (Core anchor re-run + lots capture) | 15 anchor floats + trigger counts vs `engine_reproduce.json`; bit-identical core self-test; book rebuilt from captured positions | **15/15 delta 0.0**; 31 band + 0 harvest; consistency < 2.4e-15 relative ([v7_extract_verification.json](../../research/outputs/v7_extract_verification.json)) |

MT5 real-tick confirmation of the final locked book is **deferred to the owner's MT5 machine** —
it cannot be run from Python, and Satellite has never had a tick run at all.

**The measured MT5-vs-1m crisis-tail gap.** Putting both parents in one accounting produced the
first *measurement* of the gap that was previously only an assumption
([COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)):

| Core COVID crisis tail (2020-02-15 → 2020-04-15, worst-mark peak-to-trough) | Value |
|---|---|
| MT5 real-tick, R10 (native headline) | **35.6%** |
| Record engine (1m worst-mark, IC bars), r8 | **5.54%** |
| Record engine, r9 / r10 (approx) | 6.69% / 7.15% |

Tick-granularity spread blowouts during Mar-2020 **do not exist in 1m bars**. Consequences,
standing for the whole campaign: (1) **crisis-tail numbers from the record engine must never be
quoted against MT5 numbers** — same-engine comparisons only; (2) the final book's MT5 run on the
owner's machine **remains the deployable arbiter of the tail**; (3) Core's −21.8% MT5 2020Q1 is a
real-tick artifact of the same gap (not negative in record accounting), so the composite negQ gate
is a 1m-convention gate by construction.

The resulting **composite gates** (primary scoreboard: dimension-wise best of the two measured
parents — Satellite pin, Core r8 exact) are pre-registered in
[PROTOCOL.md §2](../../research/protocol/PROTOCOL.md) and filled by
[composite_benchmark.json](../../research/outputs/composite_benchmark.json):

| CAGR | Max DD (worst-mark) | Sharpe | COVID tail | negY | negQ | Breach P(DD>30%) |
|---|---|---|---|---|---|---|
| **> 91.5%** | **< 21.22%** | **> 2.267** | **≤ 5.54%** | **0** | **0** | **< 0.012** |

The owner's original six numbers remain the **secondary** scoreboard, reported with the standing
straddles-two-engines caveat.

**Honest note (bookkeeping discrepancy — found and RESOLVED during assembly):**
an early draft of [COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)'s parent
table printed Core@r8 final equity €532,251 (the native band-engine figure), while the pinned
[composite_benchmark.json](../../research/outputs/composite_benchmark.json) `v7_record.r8` block —
the artifact the gates are derived from — prints **€492,611** with CAGR +91.5% (consistent
internally: 49.26× over 5.996y). The MD cell was reconciled to the JSON on 2026-07-10; the
remaining native-vs-record gap (€532,230 vs €492,611) is the record engine's ~1-bar execution
lag plus its own cost/margin conventions — the honest price of one common accounting, disclosed
in the composite doc. Gate dimensions were identical in both files throughout.

---

*Sources: [NSF5 docs/v7/](../../../NewStrategyFable5/docs/v7/STRATEGY.md) (STRATEGY, PERFORMANCE,
VALIDATION, RECONCILIATION, TRADE_CHARACTERISTICS, DEMO),
[NSF5 docs/v7/research/H8_REBALANCE_SCIENCE.md](../../../NewStrategyFable5/docs/v7/research/H8_REBALANCE_SCIENCE.md),
H14/H15 results, `NSF5/docs/v8/research/V8_RELEVER_POLICY.md`;
[FMA2 docs/v3.4/](../../../FableMultiAssets2/docs/v3.4/STRATEGY.md) (STRATEGY, PERFORMANCE,
VALIDATION, PREREGISTRATION, RESULT), [FMA2 docs/v3.0/RECON.md](../../../FableMultiAssets2/docs/v3.0/RECON.md),
`FMA2/research/outputs/v34_s10_pin_1m.json`;
FMA3: [composite_benchmark.json](../../research/outputs/composite_benchmark.json),
[COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md),
[verify_record_engine.json](../../research/outputs/verify_record_engine.json),
[v7_extract_verification.json](../../research/outputs/v7_extract_verification.json),
[research/intel/](../../research/intel/) recon digests.*

**All numbers above are in-sample (IC 2020–25; Core's native MT5 headline additionally includes
2026-H1 real-tick). There is no post-2025 holdout in this document — the pre-registered 2026H1
one-shot and the live demo are the falsification tests.**
