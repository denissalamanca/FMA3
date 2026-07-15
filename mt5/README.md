# FMA3 `mt5/` — IC preset pack + sub-book tester protocol

**What this is:** everything needed to run the **Core sub-book MT5 real-tick tester run tonight**
at the IC preset dial, plus the offline blend-combination step. Per the EA split decision
(ROADMAP.md, owner 2026-07-10): **EA-IC = the parents' stock EAs exactly as validated, config-only
— ZERO new EA code.** The EA is NSF5 `mt5/ea/FableMultiAsset1_V7.mq5` (the "PortfolioV7" EA — its
runtime logs are named `portfolio_v7_*`), compiled untouched.

**Why two runs + arithmetic:** the MT5 Strategy Tester runs ONE EA per pass. The Fable book
is operationally two parent stacks (archive/docs-v1.0/DEMO.md), so the tester protocol is **two separate
sub-book runs** (Core now; Satellite pending its EA audit — §d) combined **offline** by
[`scripts/combine_tester_reports.py`](../scripts/combine_tester_reports.py) (deterministic
arithmetic; the construction is already Python-validated — §c).

Files here:

| File | What |
|---|---|
| `presets/V7_FMA3IC_R896.set` | Core sub-book at the **IC dial `InpRisk=8.96`** — byte-identical to NSF5 `mt5/presets/FableMultiAsset1_V7_CORE7BAND_R8_IC.set` except line 1 |
| `presets/V7_FMA3FTMO.set` | Core sub-book at the **current FTMO dial `InpRisk=2.24`** — ⚠️ provisional; the FTMO campaign is re-shipping the dial (FMA3-005c), and see the clip warning in §Dimensional check |
| `../scripts/combine_tester_reports.py` | consumes the tester exports → blend curve + k ratios |

> ⚠️ **Do NOT use `presets/FableMultiAsset1_V7_FMA3IC_R128.set`** (found in this directory,
> other-session artifact). It mixes conventions: `InpRisk=12.8` is the €7k-sub-account dial but
> it keeps `InpInitial=10000.0`. At a €10k deposit it runs the book **1.6× the pin** (should be
> 8.96); at a €7k deposit its internal sleeve seeds (`InpInitial×W[n]`, EA :1169) exceed account
> capital and the margin/ML model breaks. If the isolated-€7k convention is ever wanted, it
> requires `InpInitial=7000.0` AND a €7,000 tester deposit — and note the fixed per-sleeve clips
> bind harder at R12.8 (§Dimensional check). The locked convention here is `V7_FMA3IC_R896.set`
> on €10,000.

---

## The dial arithmetic (and the honest DEMO.md reconciliation)

Formula (archive/docs-v1.0/DEMO.md §"The two risk dials", generic-in-s form in
research/protocol/DEMO_PREREGISTRATION.md §2): **`InpRisk = 8 × 0.70 × s = 5.6·s`**
(Core native R8 anchor × capital share w=0.70 × global scale s).

- DEMO.md derived it at **v1.0's s=1.1 → `InpRisk = 6.16`**. That document predates the preset
  fork and is *not wrong* — same formula, different s.
- The preset fork (research/protocol/PRESETS.md) re-picked s per account: **IC ships s=1.6**
  (FMA3-004c, owner breach-cap Pareto revision 0.15→0.20) → **`InpRisk = 8 × 0.70 × 1.6 = 8.96`**;
  **FTMO ships s=0.4** (FMA3-005c) → **`InpRisk = 8 × 0.70 × 0.4 = 2.24`**.
- No discrepancy to reconcile beyond s itself: the formula verifies against DEMO.md exactly
  (5.6 × 1.1 = 6.16 ✓; 5.6 × 1.6 = 8.96 ✓; 5.6 × 0.4 = 2.24 ✓). Both fork dials remain
  **provisional pending this very run's k measurement** (PRESETS.md standing caveat).

**Capital convention — ONE convention, chosen: initial deposit €10,000 with `InpRisk` carrying
the full `8 × 0.70 × s`** (not €7,000 at `InpRisk = 8·s`). Justification:

1. It is the convention DEMO.md already locked at s=1.1 (`InpRisk=6.16` on the full €10k,
   `InpInitial=10000.0` unchanged) — one convention across v1.0 and the fork.
2. `InpInitial` seeds the EA's *internal* sleeve capital (`g_seed[n] = InpInitial*W[n]`,
   FableMultiAsset1_V7.mq5:1169) and sleeve capital is what sizing multiplies
   (`DesiredLots`: `lots = balance*|m|/unit_eur`, :604, with `balance` = the sleeve's
   `VBalance` :742). `InpInitial` must equal the actual tester deposit or the internal ledger,
   the per-sleeve margin cap (:615) and the health `final_ML` all diverge from account equity.
3. Dimensional identity: notional = m(R) × capital with m linear in R, so
   `8.96 × 10,000 = 12.8 × 7,000` — identical EUR notionals either way. The €10k form wins on
   (2), on k-comparability with the record parquet (seeded €10k), and because the EA's
   *absolute* per-sleeve clips (§Dimensional check) bind **less** at R8.96 than at R12.8 —
   closer to the pin's scaled-fraction construction.

---

## (a) The Core sub-book run — click-by-click (tonight)

1. **Files:** copy `FableMultiAsset1_V7.mq5` (READ-ONLY source: NSF5 `mt5/ea/`) into the MT5
   `MQL5/Experts/`, compile in MetaEditor (F7, 0 errors). Copy `presets/V7_FMA3IC_R896.set`
   somewhere loadable.
2. **Login / account:** IC Markets EU demo, **Raw, EUR, hedging** (`ICMarketsEU-MT5` server
   family) — the tester inherits the hedging margin mode and IC contract specs from the login.
3. **Market Watch:** show all traded + conversion symbols, IC-native names:
   `XAUUSD, USTEC, USDJPY, ETHUSD, EURGBP, BTCUSD, AUDUSD, NZDUSD, EURUSD, EURJPY`
   (⚠️ USTEC, not US500 — `InpUS500=USTEC` in the preset).
4. **Strategy Tester settings:**
   | Setting | Value |
   |---|---|
   | Expert | FableMultiAsset1_V7 |
   | Symbol / TF | a 24/7 clock symbol, **ETHUSD or BTCUSD, M1** (bar stream covers all server anchors — NSF5 `mt5/V72_SETUP.md` convention; the EA trades its whole book off Market Watch regardless of the chart) |
   | Model | **Every tick based on real ticks** |
   | Dates | **2020-01-01 → latest available** |
   | Deposit / currency | **EUR 10,000** |
   | Leverage | as the parents' R-sweep runs (the IC Raw account profile) |
   | Preset | load **`V7_FMA3IC_R896.set`** — verify the inputs dialog shows `InpRisk=8.96`, `InpInitial=10000.0`, band 0.25/1.75/5, `InpEqualWeight=true`, `InpUS500=USTEC` |
   | Optimization / Visual | off / off |
5. **Startup checks** (Journal/Experts tab — NSF5 `docs/v7/DEMO.md` §5): `SLOT-EQUAL over 7
   slots … slotW=0.1429`; `FINAL sleeve weights` shows 7 non-zero slots; the decisions CSV
   trades **USTEC**.
6. **Collect outputs** when the pass ends:
   - right-click the result → **Report → HTML** → save as
     `research/outputs/mt5/v7_ic_tester.html` (this is what the combiner consumes);
   - from `Common\Files` (tester agent writes there via `FILE_COMMON`): copy
     `portfolio_v7_decisions.csv` and `portfolio_v7_health.csv` next to it
     (health row must show **`volume_rejects=0`** — any nonzero is a plumbing STOP, DEMO.md
     rule 7).
7. **FTMO variant (only if the FTMO campaign asks):** same run with `V7_FMA3FTMO.set` —
   but read the ⚠️ clip warning below first; the dial is being re-shipped.

---

## (b) Expected fingerprints — what the record engine predicts at `InpRisk=8.96`

**Derivation (engine-free — no record-engine pass, no 1m-cache load):** the pinned Core native
curve `research/outputs/v7_book_equity_1m.parquet` (R8 anchor, €10k, byte-reconciled per
fma3_v1_pin.json provenance), minute returns × **1.12** (= 0.70 × 1.6, the same
final-matrix-scaling as `strategy_fma3.py::construction`), recompounded on both close- and
worst-mark columns. Validation of the method: at scale 1.0 it reproduces the
DEMO_PREREGISTRATION §3 B3 Core row **exactly** (mean +5.90%/mo, vol 6.90%, 13/72 neg, worst
−9.22% 2022-05, best +22.92% 2021-03, band [−11.89%, +23.68%]).

**Record-engine prediction, Core sub-book @ dial 8.96, IC 1m, 2020-01-02 → 2025-12-31, €10k:**

| Metric | Record (1m) prediction |
|---|---|
| Final equity | **€827,569** |
| CAGR | **+108.9%** |
| MaxDD worst-mark / close | **21.61% / 21.35%** |
| Sharpe (daily) | **2.219** |
| COVID crisis tail (pinned formula) | **12.74%** |
| Monthly mean / vol | **+6.60% / 7.77%** |
| Neg months | 13/72 · worst **−10.31%** (2022-05) · best **+25.86%** (2021-03) |
| 99% monthly band | **[−13.42%, +26.63%]** |
| Neg quarters | **1/24** (worst −1.93%) |
| Peak margin/equity · min ML | ≈ **0.57** · ≈ **174%** (native 0.513 · 195% × / ÷ 1.12) |

(Native R8 reference from the same parquet: €532,230 final, CAGR 94.0%, maxDD_worst 19.51%,
tail 11.43% on the pinned formula. Note NSF5 quotes the R8 anchor as "cagr_bd 89.7%" —
business-day convention — and its own COVID-tail convention prints 5.5–7.2%; the numbers above
use FMA3's pinned conventions: years = days/365.25 and `run_hfed1_lib.crisis_tail`.)

**What the MT5 tester should *actually* print (honest band, not the pin):**

- **Retention precedent** at matched R8: MT5 ≈ **96%** of Python (89.7% → 86.5%, NSF5
  `docs/v7/PERFORMANCE.md`; the B1 bar is ≥ 0.85). So MT5 CAGR **~93–105%** is in-fingerprint;
  below **~92.6%** (0.85 × 108.9) is a B1 INVESTIGATE.
- **Equity DD** prints deeper than record: R8 measured 21.2% MT5 vs 19.51% record
  (k_dd ≈ 1.09) → expect **~23–24%** tester equity-DD at this dial. Fine vs the 30% ceiling.
- **COVID tail is the number being measured**, not a pass/fail: precedent k_tail ≈ 5–6.5
  (Core @ R10: 35.6% tick vs ~5.5–7.2% record, COMPOSITE_BENCHMARK.md). A tick tail of 30%+ in
  the 2020 window is *expected* and is exactly what feeds the k re-pick — do not panic-stop
  the calibration on it.
- The **2026 portion** of the run (2026-01 → latest) has **no record reference** (record window
  ends 2025-12-31). All k ratios are computed on the record window only; report the 2026 stub
  separately (it doubles as a forward-consistency read, DEMO_PREREGISTRATION §5.2).

**The k ratios (DEMO_PREREGISTRATION.md §5, "two ratios, kept separate"):**

```
k_dd   = tick worst-mark maxDD  ÷ record worst-mark maxDD   = tester_eqDD ÷ 0.2161
k_tail = tick COVID tail        ÷ record COVID tail          = tester_tail ÷ 0.1274
         (tail formula, pinned: dd of worst marks vs the running all-history close peak,
          window 2020-02-15 → 2020-04-15 — run_hfed1_lib.crisis_tail)
```

Same window (2020-01-02 → 2025-12-31), same dial, both sides. The combiner computes them.
**Re-pick rule (§5.3, pre-committed):** final s = the **largest already-registered grid s**
with `record-DD(s) × k_dd ≤ 30%` AND `record-tail(s) × k_tail ≤ 30%`; k can only cut the
dial, never raise it (a measured k < 1 does not license s > 1.6).

**Where to paste results:** save the report + CSVs under `research/outputs/mt5/`, run the
combiner (§c), then fill this table in-place and copy it into the DEMO_PREREGISTRATION §2
deploy-time addendum:

| Measured (MT5 real-tick, dial 8.96) | Record | Ratio |
|---|---|---|
| CAGR (2020–25): ____ | 108.9% | retention = ____ (bar ≥ 0.85) |
| Equity DD max: ____ | 21.61% | k_dd = ____ |
| COVID tail: ____ | 12.74% | k_tail = ____ |
| volume_rejects: ____ (must be 0) · min ML: ____ · trades: ____ | — | — |

---

## (c) Offline blend combination

**Arithmetic** (the deployed two-EA model — each stack compounds its OWN internal seeds on the
shared account, archive/docs-v1.0/DEMO.md "What does NOT exist yet" item 2, so EUR P&L is additive):

```
E_fed(t) = E_v7(t) + E_v34(t) − 10,000        (daily grid, both runs seeded €10k,
                                               each dial already carrying w·s)
```

This intentionally models the *deployment*, not the pin's native-index construction
(`fed_frac = frac7·(w·A/J) + frac34·((1−w)·B/J), × s`) — the gap between the two is the
disclosed shared-equity-coupling measurement (RECONCILIATION.md), not an error.

**Script:**

```bash
# tonight (Core only — federation marked pending):
python3 scripts/combine_tester_reports.py --v7 research/outputs/mt5/v7_ic_tester.html

# once the Satellite tester run exists:
python3 scripts/combine_tester_reports.py \
    --v7  research/outputs/mt5/v7_ic_tester.html \
    --v34 research/outputs/mt5/v34_ic_tester.html          # --preset ic (default)
```

Accepts MT5 HTML tester reports (deals-table balance curve + the summary's tick-level
"Equity Drawdown Maximal" as the k_dd numerator) or any `time,equity` CSV (e.g. the decisions
CSV `utc_time/acct_equity` columns — then worst-mark falls back to close-basis and the output
says so). Writes `research/outputs/mt5/combine_results.json` + `federation_curve.csv` and
prints the paste-ready block. Record references embedded: Core @ 8.96 (table above), the Fable book
@ s=1.6 (hrisk1_results.json: CAGR 170.2%, maxDD_worst 22.58%, tail 8.12%); `--preset ftmo`
switches to the s=0.4 references (hrisk2: CAGR 30.7%, maxDD_worst 5.99%).

---

## (d) Satellite sub-book — PLACEHOLDER (pending the EA audit)

The Satellite stack (FMA2 Python brain + `FableExecutor.mq5`) has **never had a Strategy
Tester/tick run** (FMA2 `docs/v3.4/RECONCILIATION.md` §C — OPEN) and its EA audit is not
cleared. Until it is:

- k is measured on the **Core stack only** — the pre-registered interim asymmetry
  (DEMO_PREREGISTRATION §5.1); the Fable book k completes when the Satellite tick run exists.
- When it clears: Satellite tester run at **`GLOBAL_SCALE = 10 × 0.30 × 1.6 = 4.80`** (IC preset)
  on the same window/account conventions, then re-run the combiner with `--v34`.
- Do NOT approximate the Satellite slice by scaling Core — different book, different tail.

---

## Dimensional check — `InpRisk` semantics from source (line-cited)

Source: NSF5 `mt5/ea/FableMultiAsset1_V7.mq5` (READ-ONLY).

**Linear scaling — yes, at the sizing level.** `R = InpRisk` enters every sleeve target
linearly (`RecomputeDaily` :374, `RecomputeEURGBP` :466, `RecomputeAUD` :488; S6 legs :366),
each target `m` is a notional *fraction of sleeve capital*, and
`DesiredLots` converts it as `lots = balance × |m| / unit_eur` (:604) with `balance` = the
sleeve's virtual capital (`VBalance` :742, seeded `InpInitial × W[n]` :1169). So EUR notional
∝ `InpRisk` × `InpInitial`-seeded compounding — the `8.96 × 10,000 ≡ 12.8 × 7,000` identity
above is exact at the sizing line.

**No input clamp on `InpRisk`.** Declared `input double InpRisk = 5.0` (:57) with no
validation anywhere (`OnInit` :1094 does not check it); the parent's MT5 R-frontier ran it to
R20. 8.96 exceeds nothing. The per-order margin clamp (:615, `maxlots =
balance×InpMarginCap/mpl`) has headroom: predicted peak margin/equity ≈ 0.57 vs cap 0.9.

**BUT: per-sleeve absolute clips do NOT rescale with the dial** — the honest caveat. Each
target is clipped at a *fixed* cap: gold donch components ±6 each (:384, :385), gold overnight
leverage [0, 6] (:387), USTEC ±6 (:400), Monday leverage [0, 10] (:401), S6 legs
[0, `InpMagCap`=6] (:366), **BTC [0, `InpBtcCap`=1.2] (:457)**; the FX ±20 clips (:357, :419)
are wide and effectively never bind. The record-engine pin scales the *already-clipped* R8
fractions by 0.70·s without re-clipping; the EA at `InpRisk = 5.6·s` re-applies the fixed caps:

- **IC dial (8.96): conservative, small.** Where a cap binds at both dials (e.g. overnight
  gold whenever 20d ann vol < 45%; BTC essentially always) the EA holds the cap while the pin
  wants cap × 1.12 — the EA runs those components up to **10.7% lighter** (1/1.12) than the
  record prediction. Direction: lower CAGR and lower DD than the §b table; it lands inside the
  retention band and is quantifiable per-sleeve from `portfolio_v7_decisions.csv`.
- **FTMO dial (2.24): the reverse, and large.** ⚠️ At a low dial the caps stop binding in the
  EA but the record validation still carries the R8-clipped values × 0.28: cap-pinned
  components size up to **1/(0.70×0.4) ≈ 3.6× heavier** than validated (worst case BTC:
  EA holds 1.2 vs record 0.336; overnight gold ≈ 2.7×; S6 ≈ 2.5×). The H-RISK-2 record
  numbers therefore do **not** correspond to the EA at `InpRisk=2.24` where clips bind — the
  divergence is in the dangerous direction for the FTMO daily-loss rule. Flagged in the
  preset header; **hand this note to the FTMO campaign with the dial re-ship.**

---

*Sources: NSF5 `mt5/ea/FableMultiAsset1_V7.mq5` + `mt5/presets/FableMultiAsset1_V7_CORE7BAND_R8_IC.set`
+ `docs/v7/DEMO.md`/`PERFORMANCE.md`; FMA3 `archive/docs-v1.0/DEMO.md` (dial arithmetic),
`research/protocol/PRESETS.md` (FMA3-004c/005c), `research/protocol/DEMO_PREREGISTRATION.md`
(§2 dial table, §3 B1/B3, §5 k protocol), `research/outputs/v7_book_equity_1m.parquet` (the
scaled-prediction source), `hrisk1_results.json` / `hrisk2_results.json` (the Fable book record
references). All record numbers are in-sample IC 2020–25, 1m worst-mark; the tick run this
protocol drives is the falsification test, not a formality.*
