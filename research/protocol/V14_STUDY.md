# FMA3 v1.4 — 2015–2019 edge-persistence / falsification study (PRE-REGISTRATION)

**CRITERIA COMMITTED 2026-07-10, before any 2015–2019 number has been computed
by any FMA3 code.** FMA3 has produced zero measurements on pre-2020 data as of
this commit; the parents' prior 2015–19 consumption is disclosed in §7. This
document is the complete specification: the study computes EXACTLY the numbers
in §5, evaluates EXACTLY the triggers in §6, and nothing else. No peeking
clauses, no "additional diagnostics", no re-runs after a 2015–19 number has
been seen (crash-grade code defects excepted — any such fix is disclosed in
the report and the affected numbers are recomputed once, from the same spec).

Runner: `scripts/run_v14_study.py` — **UNRUN at commit time** (a long
pre-registered engine queue holds the CPU; ROADMAP.md sequencing puts v1.4
after v1.1–v1.3 anyway). The runner refuses to run unless this file contains
the string CRITERIA COMMITTED and hard-fails if any engine-queue process is
alive.

---

## 1. Study question

The blend's structural premise — that the two parent books are
complementary (daily ρ ≈ 0.35, disjoint drawdown troughs, blend DD
sub-additive in the parents') — is currently evidenced ONLY on 2020–2025 plus
4 forward months (2026H1). **Does the complementarity hold on 2015–2019, five
years that predate every FMA3 design decision?**

This is a **falsification attempt on a structural claim**, not a performance
study. Per ROADMAP.md v1.4: no lever is adopted from this; neither outcome
changes any 2020–25 number.

2020–25 calibration values (already published, `research/outputs/
composite_benchmark.json` M-0 — restated here so the 2015–19 read has a fixed
reference): ρ_full = +0.351; yearly ρ ∈ [0.115, 0.460]; Satellite's DD state at
Core's trough (2021-05-23) = 0.23%; Core's DD state at Satellite's trough (2022-02-10)
= 3.90%; each book's mean return on the other's 10 worst days = −2.93% (Satellite
on Core's) / −1.41% (Core on Satellite's).

## 2. What this study is NOT

- NOT worst-mark accounting. Research-grade feeds only (assigned/synthetic
  spreads); no shippable number can come out of it and none will be quoted as
  one.
- NOT a parent-performance re-evaluation. Parent CAGR/Sharpe on 2015–19 are
  **deliberately excluded** from the committed output set (§5) — the study
  measures co-movement and DD structure only. (Equity curves are necessarily
  computed as intermediates; their performance stats are not part of the
  report.)
- NOT a lever. No adoption decision, no grid, no selection. One evaluation.
- NOT a re-litigation of any parent sleeve verdict (crisis 2015–19 Sharpe
  −0.10, S6 gauntlet −0.32, etc. stand as recorded by their own protocols).

## 3. Data readiness map (measured 2026-07-10, schema-level checks only)

### 3.1 Core book — NSF5 `cache/bars_1m_ext` (10 instruments, `<SYM>_2015_2025_1m.parquet`, Duka schema, tz-naive TRUE UTC)

Feed construction (NSF5 `mt5/reconcile/v72/build_extended_bars.py`): 2015–2019
portion = Duka **bid-only M1** from `/Users/dsalamanca/vs_env/data/extended/`
with a **synthetic ask = bid + constant per-instrument median spread taken
from the real 2020–25 bars**, `n_ticks=1` everywhere, concatenated with the
real 2020–25 Duka bars. Verified 2026-07-10: all 10 files present; pre-2020
portions have `n_ticks` uniformly 1 and a single constant `spread_mean`.

| Core sleeve | Instrument(s) | Ext coverage | Verdict |
|---|---|---|---|
| BOOK_XAU | XAUUSD | 2015-01-01 → | **BUILDABLE-WITH-CAVEAT** (synthetic constant spread) |
| BOOK_USTEC | USTEC → **USA500 proxy** | USA500 2015-01-02 → ; USTEC ABSENT from bars_1m_ext (raw USTEC M1 2015–2020 exists unbuilt in `data/extended/`) | **BUILDABLE-WITH-CAVEAT** (proxy corr 0.89, the NSF5 lock_v5 / FMA3-FWD convention; committed here — no mid-study switch to a fresh USTEC build) |
| S5_JPY | USDJPY | 2015-01-01 → | **BUILDABLE-WITH-CAVEAT** (2015–19 US hiking cycle ≠ 2020–25 regime — disclosed as a thesis feature per NSF5's own plan, not a defect) |
| S1_ETH | ETHUSD | **2017-12-11 →** | **BUILDABLE-WITH-CAVEAT** (2018+ only; absent 2015–2017) |
| ZC_EG | EURGBP | 2015-01-01 → | **BUILDABLE-WITH-CAVEAT** (mean-reversion sleeve = most sensitive to the constant-spread assumption) |
| S6_OPEXUSD | USDJPY, AUDUSD, NZDUSD | 2015-01-01 → | **BUILDABLE-WITH-CAVEAT** |
| BTC_REP | BTCUSD | **2017-05-07 →** | **BUILDABLE-WITH-CAVEAT** (2018+ crypto calendar) |

FX conversion (ICFx EUR book): EURUSD, EURJPY, EURGBP all present full-span → OK.

**Book-level verdict: BLOCKED-PENDING-ANCHOR.** NSF5's extended-history
reconciliation is PAUSED mid-diagnosis (NSF5 `docs/v7/research/
MORNING_BRIEFING.md:80-81`): the ext pipeline's own 2020–2025 anchor row
(FULL-7, `mt5/reconcile/v72/extended_run.py`) produces **71% CAGR / 44% DDrel
vs the real R10 close-mark panel 108.50% / 18.84%** — and the anchor window
uses the REAL 2020–25 bars, so the failure is a **pipeline/convention defect,
not a pre-2020 data defect**. Undiagnosed candidate causes (from reading the
pipeline, no runs): per-sleeve `run_harvest_attrib(kmult=inf)` attribution vs
the pinned `h15/base_matrix.parquet` build; the business-day
resample/ffill/pct_change convention; the extended re-split EDGES calendar;
the 10-instrument ICFx vs the full-feed FX converter; R/BASE_R scaling.
**What is trustworthy pre-2020:** the raw Duka bid M1 prices (depth confirmed
to 2015 for FX/gold/index; the same upstream files feed FMA2's
research_cache_ext, which passed FMA2's own adjudicated pre-period runs).
**What is NOT trustworthy:** (a) pre-2020 execution costs (constant synthetic
spread, `n_ticks=1` — any liquidity-gated logic sees a degenerate feed);
(b) ANY book-level Core number from the ext pipeline until its 2020–25 anchor
reconciles. Diagnosis of the anchor is NSF5-side prerequisite work and is NOT
part of this study; the study simply refuses to produce a Core-side 2015–19
number until the Phase-0 gate (§4) passes.

### 3.2 Satellite book — FMA2 `research_cache_ext` (34 syms, `<SYM>_1h.parquet`, 2015-01-02 → 2020-12-31, tz-naive broker server time, ASSIGNED per-class spreads)

Verified 2026-07-10: 34/37 universe symbols present (missing SOLUSD, XRPUSD,
XPTUSD — none load-bearing pre-2020; SOL launches 2020); USTEC and USA500 both
present 2015+; BTCUSD from 2017-05-08, ETHUSD from 2017-12-12. Spreads are
ASSIGNED per asset class (`build_cache_2015.py` REL_SPREAD) on single-price
sources — edge-persistence grade, explicitly NOT worst-mark.

| Satellite sleeve (F3-cap weight) | Ext coverage | Verdict |
|---|---|---|
| meanrev (0.110) | full | **BUILDABLE-WITH-CAVEAT** (assigned spreads) |
| carry_breakout (0.046) | full | **BUILDABLE-WITH-CAVEAT** |
| seasonal (0.180) | full | **BUILDABLE-WITH-CAVEAT** (known feed-sensitivity: Duka 1.07 → 0.40, H15 flag) |
| intraday (0.168) | full (USTEC present) | **BUILDABLE-WITH-CAVEAT** |
| crisis (0.100) | full | **BUILDABLE-WITH-CAVEAT** (2015–19 documented as thesis-consistent no-crisis window) |
| trend_v2 (0.042) | full | **BUILDABLE-WITH-CAVEAT** |
| crypto_smart (0.130) | BTC/ETH only, ETH 2017-12+ | **BUILDABLE-WITH-CAVEAT** (BTC/ETH-only symbols per the `run_oos_2015.py` convention) |
| mag_xau (0.050) | full | **BUILDABLE-WITH-CAVEAT** (see selection disclosure below) |

Proven path: FMA2 `research/run_oos_2015.py` already ran the sleeve set on
this exact cache (v2.0 pre-period one-shot, book Sharpe 0.93) — the machinery
works; v1.4 re-composes it with the Satellite F3-cap weights (`eval_v34_pin_s10.py`
V2_CAPS + MAG@0.05, `ensemble.combine`, NO renormalise, ×SCALE 10,
`apply_hard_limits`) and the hourly fast-sim `core.simulate` instead of the 1m
engine.

**Selection disclosure (honesty, committed up front):** the Satellite book is not
fully design-blind on 2015–19. (a) `mag_xau` was ADOPTED because of its
2015–19 gauntlet performance (Stage-2 Sharpe 0.62 on this window); (b) the F3
conviction caps that set the Satellite weights used 2015–19 durability evidence
(crisis cap set down on 2015–19 Sharpe −0.10). The study's claims are about
BLEND-LEVEL co-movement, which neither selection targeted, but the
contamination is disclosed in the report verbatim as written here.

### 3.3 Blend coverage windows (committed)

- **W-A (headline) 2015-01-02 → 2019-12-31**: Core = core-5 (no S1_ETH /
  BTC_REP before their data starts; crypto sleeves enter at the 2018-01-01
  crypto re-split calendar); Satellite = 8 sleeves with crypto_smart contributing
  only from its data start. Coverage disclosed in the report as a per-sleeve
  first/last-date table (§5 N6).
- **W-B (secondary) 2018-01-01 → 2019-12-31**: both books at full sleeve
  complement (Core full-7, Satellite full-8).

Refutation triggers (§6) are evaluated on **both** windows; either window can
refute (a falsification attempt maximises its own chance of failing).

## 4. Method

**Convention: research-grade close-mark, NOT worst-mark.** No worst-mark,
breach, tail, or shippable-scale numbers are produced.

- **Phase 0 — anchor gates (prerequisite, already-mined 2020–25 data only;
  iteration on the PIPELINE is allowed here because no 2015–19 number exists
  yet; the instant any 2015–19 number is produced, Phase-1 one-shot discipline
  applies):**
  - **A1 (Core):** the ext pipeline (NSF5 `v72/extended_run.py` conventions,
    read-only reuse) run on the 2020–2025 portion of `bars_1m_ext` must
    reproduce the pinned R10 close-mark panel — CAGR 108.50%, DDrel 18.84% —
    within **|ΔCAGR| ≤ 3pp AND |ΔDDrel| ≤ 2pp**. Known state at commit: FAILS
    (71%/44%); the NSF5-side diagnosis must land first. A1 failure ⇒ the Core
    side and the blend measurements are **BLOCKED**; the study does not
    run and 2015–19 is not consumed by FMA3.
  - **A2 (Satellite):** the Satellite-composition hourly fast-sim on FMA2
    `research_cache` (2020–25, 37 syms) must land in the documented Tier-0
    fast-sim band vs the 1m pin (CAGR 88.66%, maxDD 21.67% worst-mark):
    **CAGR ∈ [0.95×, 1.18×] of pin = [84.2%, 104.6%] AND close-mark daily
    maxDD ∈ 21.67 ± 4pp = [17.67%, 25.67%]**. A2 failure ⇒ BLOCKED, same
    semantics.
  - Tolerances are reconciliation gates, not knobs: a Phase-0 failure is a
    BLOCKED verdict, never a licence to widen the bands.
- **Phase 1 — one shot.** Build both books' 2015–19 daily equity curves in
  the SAME conventions that passed Phase 0 (Core: 10-instrument ext feed, USA500
  proxy, extended re-split EDGES from 2015-01-01, crypto EDGES from
  2018-01-01, R10 close-mark band_sim panel; Satellite: F3-cap composition ×10,
  hard limits, hourly fast-sim on research_cache_ext, daily close resample).
- **Blend bookkeeping (on top, no engine):** static w = 0.70 (the shipped
  v1.0 split), virtual sub-accounts seeded (0.70, 0.30), each compounding its
  own book's daily returns, NO rebalancing (the shipped book is static),
  E_fed = E_v7 + E_v34. Scale/leverage is irrelevant to ρ and to the DD
  *relation*; both books run at their research-native compositions as above.
- Timezone handling: bars_1m_ext is tz-naive TRUE UTC; research_cache_ext is
  tz-naive broker SERVER time. Curves are compared on **calendar-date daily
  closes** only (last observation per date), which the parents' M-0
  measurement already established as the house convention; no intraday
  cross-feed joins (the canonical TZ landmine is intrabar mixing, per
  `data/DO_NOT_USE.md`).

## 5. Pre-committed outputs — the exact numbers, nothing else

All on daily close-to-close returns of the research-grade curves, computed
identically to `scripts/derive_composite.py` M-0:

- **N1** ρ_daily_full between the two parent books, on W-A and on W-B.
- **N2** ρ_daily by calendar year, 2015…2019.
- **N3** On-worst-days: Satellite's mean daily return on Core's 10 worst days and
  vice versa, plus the two 10-day tables (date, both books' returns) — per
  window W-A and W-B.
- **N4** Co-drawdown: each book's own DD state on the date of the other's
  window trough, plus both trough dates — per window.
- **N5** DD relation: maxDD(Core), maxDD(Satellite), maxDD(fed static-w70), the
  weighted-sum reference w·DD_v7 + (1−w)·DD_v34, and the sub-additivity gap
  min(parent DDs) − DD_fed — per window.
- **N6** Coverage table: per sleeve per book, first/last active date and
  days present in each window (the honesty disclosure that scopes every claim).

Explicitly excluded: parent or blend CAGR / Sharpe / quarterly P&L /
breach / tail on 2015–19. If a future question needs them, that is a new
pre-registration.

## 6. Pre-committed outcome semantics (from ROADMAP.md v1.4, sharpened)

Refutation triggers — ANY one, on EITHER window (W-A or W-B):

- **R-a** ρ_daily_full ≥ 0.60.
- **R-b** Co-trough: at either book's window trough date, the other book's
  concurrent DD ≥ 50% of that other book's own window maxDD (both directions
  tested). (2020–25 calibration: the measured ratios are ~1% and ~21% — the
  confirmed regime clears this bar by a wide margin.)
- **R-c** DD super-additivity: DD_fed(static w70) > w·DD_v7 + (1−w)·DD_v34
  (the diversification benefit absent or inverted).

Verdict semantics:

- **CONFIRMATION** (no trigger fires): a robustness paragraph in the
  whitepaper, quoting N1–N6 with the §3 coverage caveats verbatim. No number
  anywhere else changes.
- **REFUTATION** (any trigger fires): an honest downgrade of the blend's
  forward expectation in the whitepaper + a **scale review opened as its own
  versioned item** (the review is a new pre-registration; nothing is re-picked
  inside v1.4). 2020–25 numbers unchanged.
- **YELLOW note** (no trigger, but any single yearly ρ ≥ 0.60): disclosed in
  the robustness paragraph as-is; not a refutation, not silently dropped.
- **BLOCKED** (Phase-0 anchor fails): the study does not run, no 2015–19
  number is produced or looked at, the ledger entry records BLOCKED with the
  failing anchor values, and the NSF5 anchor diagnosis becomes the
  prerequisite work item. Partial unblocking is NOT allowed (no "Satellite-side
  only" study: the study question is the blend, and a one-book run would
  consume the window's one-shot value).

Either result is valuable; neither changes 2020–25 numbers. (ROADMAP.md v1.4,
verbatim commitment.)

## 7. Data-consumption ethics + ledger

2015–2019 was already consumed for training-eligibility by FMA2's protocol
(v2.0 pre-period one-shot CONFIRM; v3.0 import gauntlet) and partially by
NSF5's F3/durability evidence — no fresh-data ethics issue (ROADMAP.md v1.4),
but it is logged: **ledger entry FMA3-007 (reserved)** — measurement /
falsification study, no adoption decision, one Phase-1 evaluation. Engine
ledger cost: Phase 0 = 2 anchor reproductions on already-mined 2020–25 data
(not selection); Phase 1 = 1 blend measurement on 2015–19.

## 8. Runner contract

`scripts/run_v14_study.py` (UNRUN at commit):

1. refuses to start unless this file contains `CRITERIA COMMITTED`;
2. hard-fails if any engine-queue process
   (`run_hrisk1|run_hrisk2|run_htail1|record_engine|account_engine_1m|run_record`)
   is alive;
3. enforces phase order — Phase-1 code is unreachable unless both Phase-0
   anchors pass their §4 tolerances in the same invocation (or a
   `--phase0-only` run is used first; the anchor JSON is then revalidated);
4. writes `research/outputs/v14_study.json` (+ curves parquet) containing
   N1–N6 and the trigger evaluations, and nothing else.

Expected runtime (documented, not yet measured): Phase 0 A2 ≈ 5–15 min
(hourly fast-sim, 37 syms × 6y); Phase 0 A1 ≈ 15–45 min (NSF5 sleeve builds on
10 × 6y 1m bars); Phase 1 ≈ 20–60 min (both books, 2015–19 + ext EDGES);
blend bookkeeping ≈ seconds. Total ≈ 45–120 min, single process, several
GB RAM. **Must not run while the pre-registered H-RISK/H-TAIL queue is
alive.**

---

**CRITERIA COMMITTED 2026-07-10.** Committed before any 2015–2019 number was
computed by FMA3. One Phase-1 shot. DECLINE-by-default discipline does not
apply (nothing is being adopted); the one-shot discipline does.
