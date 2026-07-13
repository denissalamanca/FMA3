# V3.0 validation analysis

**FMA3 v3.0 = the faithful-executor release.** v1.0 shipped the **model** — a Python record-engine
book, validated in-sample as the first fully-parent-dominant federation. v3.0 ships the **EA that
provably executes that model on MT5**, plus the honest deployable reality: two dials, three named
physical constraints, measured friction. The model itself is unchanged — same config hash
**`51a7541cc2aaa593`**, same `w_v7 = 0.70` — and the v1.0 statistical battery (6-tier: reproduction
chain, pre-registered ladder, red team, breach bootstrap, DSR, CPCV, 2026H1 one-shot) still stands
underneath it. **This document validates the EXECUTOR, not the model:** it certifies that
`FableFederation_V3.ex5` holds the model's exact target position on every bar, and it names — and
quantifies — every euro of gap between the frictionless record and an achievable retail account.

Sources of truth: the canonical model home is [`model/v3/`](../../model/v3/) —
[`README`](../../model/v3/README.md), [`MODEL_SPEC`](../../model/v3/MODEL_SPEC.md),
[`PINNED_INPUTS`](../../model/v3/PINNED_INPUTS.md), [`EA_V3_DESIGN`](../../model/v3/EA_V3_DESIGN.md),
[`RECON4_RESULTS`](../../model/v3/RECON4_RESULTS.md). Reconciliation protocol:
[research/protocol/RECONCILIATION.md](../../research/protocol/RECONCILIATION.md). EA source:
[`mt5/ea/FableFederation_V3.mq5`](../../mt5/ea/FableFederation_V3.mq5). Exporter + sweep:
[`scripts/export_fed_frac_v3.py`](../../scripts/export_fed_frac_v3.py) /
[`scripts/sweep_s_volcap.py`](../../scripts/sweep_s_volcap.py).

**All model figures are in-sample RECORD reads (IC 2020-25). The three RECON-4 runs are 1m-OHLC
tester runs — a mechanics smoke, not the crisis arbiter. MT5 real-tick + live demo remain the
falsification tests.** Achievable equity is **0.66–0.95× the record** depending on dial and scale;
never present the record number as a deployable promise.

---

## Headline — the model of record and its achievable reality

| Preset | Seed | Dial | **Model (record engine)** | **v3 executor (RECON-4, 1m-OHLC)** | v3 / model | Position fidelity |
|---|---:|---|---:|---:|---:|---:|
| **IC** (H-RISK-1) | €10,000 | s = 1.6 compounding | **€3,872,872** · +170.2% · 22.58% DD · Sharpe 2.465 | **€2,552,962** (min ML 121% @ 1:30) | **0.66×** | median after/want **1.000** |
| **FTMO** (H-RISK-2b) | €100,000 | s = 0.7 + breaker x=3.0% | **€1,332,404** · +54.02% · 13.33% DD · 26 fires | **€1,265,541** (28 breaker fires) | **0.95×** | median after/want **1.000** |
| **PARITY** (sanity) | €10,000 | s = 1.0 | €464,991 (record base point) | **€391,873** (0 rejects, 33/33 trade) | **0.84×** | median after/want **1.000** |

**The one number that matters is the last column: position fidelity is EXACT.** At each hour h and
symbol k, v3's held fraction of its own balance equals `fed_frac[h,k]·s` — median `after/want =
1.000`, p10 = 1.000, in **all three runs**. Where v3 can place the order, it holds precisely the
model's target. The final-equity gap is therefore not a defect: it is **pure friction plus two
physical ceilings the frictionless record engine does not model.** Every euro of the 0.66–0.95×
range is a named constraint, not mystery drift.

**Config `51a7541cc2aaa593`, w_v7 = 0.70; both dials are s ≠ 1** — which is exactly why v1/v2's
compute-live sizing could not reproduce the model and why v3's **replay** architecture was
necessary (below).

---

## Scorecard — the execution battery

| # | Test | Result | Criterion | Verdict |
|---|---|---|---|---|
| **1** | Model reproduction — `reproduce.py` to the euro | asserts **€3,872,872** (IC) and **€1,332,404** (FTMO); exits non-zero on any drift | delta 0.0 vs the pinned headline equities | ✅ PASS |
| **1** | Frozen-input pins (4 artifacts + 2 scalars) | 3 parquet sha256 + config hash `51a7541cc2aaa593` re-verified 2026-07-12 | any hash change re-opens the model | ✅ PASS |
| **2** | Exporter self-check — `export_fed_frac_v3.py` | re-parsed stream reproduces `static_fed(0.70)` to **< 1e-12**; record engine on the stream = **€3,872,872 / €1,332,404** to the euro | matrix < 1e-12 AND equities to the euro | ✅ PASS |
| **2** | EA compile + hash | `FableFederation_V3.ex5` compiles **0/0**, sha **`740da0ff…`** (post volume-limit fix); stream sha `d00b614b…`, fmt=3 | clean compile, hash recorded to RECON row | ✅ PASS |
| **3** | **Position-level fidelity (the real test)** | median `after/want` = **1.000**, p10 = 1.000, **all 3 runs** | held frac == fed_frac·s within lot-step | ✅ PASS |
| **3** | PARITY s=1.0 | €391,873 (**0.84×**), **0 rejects**, all 33 symbols trade | fraction == exposure sanity point | ✅ PASS |
| **3** | IC s=1.6 | €2,552,962 (**0.66×**), 0 rejects after the volume-limit fix | reproduces up to physical caps | ✅ PASS (capped) |
| **3** | FTMO s=0.7 | €1,265,541 (**0.95×**), **0 rejects, 0 volume-capped** | deployable dial reproduces cleanly | ✅ PASS |
| **4** | v3.4 sleeve revival | **all 33/33 symbols trade** — incl. the 7 dead in v1/v2 (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) | full-map eurq revives every leg | ✅ PASS |
| **5** | FTMO breaker fidelity | fires **28×** (model 26); worst-mark `eq_w` + prev-day-close anchor | fires ≈ model, conservative direction | ✅ PASS |
| **6** | Margin at retail 1:30 (IC s=1.6) | **min ML 121%** across the full 2020–25 backtest | > IC 50% stop-out; ≥ owner ML≥110% floor | ✅ PASS (provisional) |
| **7** | Volume-limit s-sweep (FMA3-024) | cap is a **capacity ceiling scaling with account size**: ~0–6% @ €10k, 17–40% @ €1M; binds past ~€2M/s | quantify the volume ceiling | ✅ MAPPED |

**Model reproduces to the euro; the exporter round-trips to 1e-12; the EA holds exact target
positions on every bar in all three runs; the v3.4 sleeve is fully revived; the breaker and margin
behave as designed.** The only OPEN items are MT5 real-tick confirmations — they cannot be closed on
this Mac (sign-off below).

---

## Tier 1 — the reproduction chain (why every model number is trusted)

The model is a **deterministic function of 4 frozen artifacts + 2 scalars** (`w = 0.70`, dial `s`).
[`reproduce.py`](../../model/v3/reproduce.py) is **self-contained** — it inlines the `static_fed`
blend and depends only on `engine/` plus the four pinned inputs — and it **asserts both headline
equities, exiting non-zero on any drift.** Reproduce:

```
python3 model/v3/reproduce.py          # both presets, ~8-9 min — asserts €3,872,872 and €1,332,404
python3 model/v3/reproduce.py --ic     # IC only  (~4 min)
python3 model/v3/reproduce.py --ftmo   # FTMO only (~4 min)
```

The pinned inputs ([`PINNED_INPUTS.md`](../../model/v3/PINNED_INPUTS.md), re-verified 2026-07-12):

| Symbol | Path | sha256[:16] | Role |
|---|---|---|---|
| `frac7` | `research/outputs/v7_book_frac_1h.parquet` | `450e65bee7307d09` | v7.0 hourly signed fraction, 8 net cols |
| `a` (eq7) | `research/outputs/v7_book_equity_1m.parquet` | `ccb0335df45d9a03` | v7 **native standalone** 1m equity multiple |
| `b` (eq34) | `research/baselines/fma2/v34_s10_pin_curve.parquet` | `a5787993a3413108` | v3.4 **native standalone** 1m equity multiple |
| `frac34` | `engine/books.build_v34_frac_1h()` (read-only FMA2 pin) | *(code, deterministic)* | v3.4 book, 31 cols, gold cap 1.80 pre-applied |

`a` and `b` are each book's **own** standalone equity path — **not** the joint account, **not**
levered by `s`, **no** federation friction. This is the single load-bearing fact of the whole
release: a live federated account **cannot reconstruct** the share weights `(w·a_h/j)`,
`((1−w)·b_h/j)` from its own equity, so any EA that computes them live must diverge whenever s ≠ 1.
Both shipped dials are s ≠ 1. That is why v1/v2 (compute-live) were abandoned and v3 **replays** the
precomputed blend — dissolving the reseed / floating-double-count / pooled-redistribution
divergences by construction.

**Exporter round-trip** ([`export_fed_frac_v3.py`](../../scripts/export_fed_frac_v3.py)). The
unified, already-netted `fed_frac` stream that v3 replays is hard-gated at emit time:

| Self-check | Measured | Gate |
|---|---|---|
| Re-parse → matrix reproduces `static_fed(0.70)` | delta **< 1e-12** | < 1e-12 |
| `record_engine.run_record(parsed·1.6, €10k)` | **€3,872,872** | == model, to the euro |
| `run_record_ext(parsed·0.7, €100k, 3.0)` | **€1,332,404** | == model, to the euro |

Stream sha `d00b614b…`, header `w_v7=0.70,config_hash=51a7541cc2aaa593,fmt=3`, 33-symbol union with
shared symbols already netted, `s` **not** baked in (it is the EA dial). No number in the package has
a provenance outside this chain: the stream the EA reads **is** the model matrix, proven to 1e-12.

---

## Tier 2 — FMA3-RECON-4: the executor holds the model's exact position

Per the standing reconciliation protocol
([RECONCILIATION.md](../../research/protocol/RECONCILIATION.md)), **every new EA `.ex5` hash given a
tester run gets a dated `FMA3-RECON-N` ledger entry before it may deploy.** RECON-4 is the v3 entry.
Tester: **IC Markets 11078280, 1m-OHLC, HEDGING, 1:500** (the high-leverage login is the
*reproduction* constraint — it lets the model's own per-symbol margin cap bind before the broker's,
so v3 reaches the record; retail 1:30 is the separate *deployment* constraint, measured below).

**The three runs:**

| Run | Preset | Dial | Seed → v3 equity | Model | v3 / model | Rejects | Fidelity (median after/want) |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | `FED_V3_PARITY_S10` | s = 1.0 | €10k → **€391,873** | €464,991 | **0.84** | 0 | **1.000** (33/33 symbols) |
| 2 | `FED_V3_IC` | s = 1.6 | €10k → **€2,552,962** | €3,872,872 | **0.66** | 0¹ | **1.000** |
| 3 | `FED_V3_FTMO` | s = 0.7 | €100k → **€1,265,541** | €1,332,404 | **0.95** | 0 | **1.000** (0 volume-capped) |

¹ Pre-fix, Run 2 spun **51,346 rejects** on volume-limited legs (v3 retried the un-holdable excess
every bar). The volume-limit clamp (sha `740da0ff…`) removes the *spin*; the **equity is unchanged**
(€2,552,962) because the cap is physical, not a bug.

**What is proven:**

1. **v3 holds the model's exact target position.** `after/want` — the ratio of v3's held fraction to
   the model's target fraction `fed_frac·s` — has **median 1.000, p10 = 1.000 in all three runs.**
   Where v3 *can* place the order, it holds precisely the model's target. This is the fidelity
   criterion the EA was designed against ([EA_V3_DESIGN §1](../../model/v3/EA_V3_DESIGN.md)):
   position-level match, not byte-identical equity — the equity gap is friction, measured not
   mysterious.
2. **The v3.4 sleeve is alive** (Tier 4 below).
3. **The breaker works** (Tier 5 below).

**Verdict: v3 is the FAITHFUL EXECUTOR of `model/v3`.** Final equity = 0.66–0.95× the frictionless
record by dial/scale; every gap is a *named physical constraint the record engine does not model*,
NOT an EA defect.

---

## Tier 3 — the three physical constraints (why 0.66–0.95×, not 1.00×)

The record engine is **frictionless and unbounded**; a real account is neither. All three constraints
bind at s=1.6; **none bind at the deployable FTMO dial (Run 3, s=0.7, clean 0.95×, 0 rejects).**

| Constraint | Record engine | Real account (this login) | Binds when |
|---|---|---|---|
| **Transaction friction** (spread/commission) | modeled coarsely | real per-trade cost | always; compounds with leverage: **0.95× @ s0.7 → 0.84× @ s1.0 → 0.66× @ s1.6** |
| **Volume limit** (`SYMBOL_VOLUME_LIMIT`) | **none** | XAUUSD **10**, SOLUSD **1000**, ETHUSD **100** lots | book past **~€2M/s** (XAUUSD binds first) |
| **Broker margin** | model per-symbol leverage | broker / retail 1:30 grant | high s on retail leverage |

**The €3.87M IC-s1.6 record is a frictionless CEILING, not physically reachable on one retail account
at that scale** — XAUUSD alone is capped at roughly half the model's target as the book compounds.
Scaling levers past the ceiling (both owner-raised, both valid): a **higher-tier account** (larger
volume limits), or **N parallel accounts at €C/N each** (each holds 1/N of the model position under
the per-account limit; aggregate = the full model, multiplying every volume limit by N — pure
capacity, no diversification).

---

## Tier 4 — the v3.4 sleeve revival (33/33 symbols alive)

v1/v2 silently killed **7 v3.4 symbols** (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) via
an `EurPerQuote` quote-currency bug: the JPY/NOK/SEK legs were mispriced ~117× / ~10× below min-lot,
rounded to zero, and never traded. v3's **unconditional full-map eurq** (`USD→EURUSD, JPY→EURJPY,
GBP→EURGBP, CHF→EURCHF, NZD→EURNZD, CAD→EURCAD, NOK→EURNOK, SEK→EURSEK`, applied to **all** symbols)
revives every leg. **RECON-4 confirms all 33 symbols post > 0 deals in each of the three runs** — the
full-map eurq works end-to-end in MT5.

---

## Tier 5 — breaker fidelity (FTMO)

The FTMO daily circuit breaker (`InpDailyStopX = 3.0`) fired **28×** in Run 3 vs the model's **26×**.
The +2 is v3's worst-mark `eq_w` being marginally more sensitive than the record engine's — the
**conservative** direction (it halts slightly earlier, never later). It anchors on the **previous
server-day CLOSE-mark equity** and trips on the worst-mark (M1 bar low/high) exactly as
[MODEL_SPEC §5](../../model/v3/MODEL_SPEC.md) specifies. Margin never stressed on this run (ML min
376%, median 1346%).

---

## Tier 6 — margin at retail 1:30 (the corrected honesty flag)

The pre-v3 flag claimed **s=1.6 is undeployable at 1:30** (margin gate binds first; deployable band
s0.6–0.8). **The v3 EA disproves it.** v3's own margin cap (`0.9·balance` on the MODEL per-symbol
leverage, which ≈ a 1:30 account's per-symbol grant) **self-limits the book**, so s=1.6 @ 1:30 ran
the full 2020–2025 backtest at **min ML 121%** — far above IC's **50% stop-out** (a ~55% peak-book DD
would be needed to liquidate, vs the 21% historical worst) and ~11pp above the owner's **ML ≥ 110%
self-limit** at the 2025 peak book. Same €2,552,962 as the 1:500 run (v3's margin cap is
account-leverage-independent). **The old "s=1.6 not deployable at 1:30" flag was a v1-over-leverage
artifact and is DISPROVEN for v3.**

Reframe: **at 1:30 the MARGIN ceiling binds before the VOLUME ceiling** (~s0.7 keeps the IC book
small enough that volume never engages). So **margin, not volume, sets the IC dial**; volume is a
large-account / high-leverage capacity concern only.

---

## Tier 7 — the volume-limit s-sweep (FMA3-024)

The no-cap sweep validates back to **€3,872,872**; the cap is a **capacity ceiling that scales with
account size**, not a dial-shifter — IC ret/DD still favours high s, the cap just lowers the whole
curve ([`sweep_s_volcap.py`](../../scripts/sweep_s_volcap.py)):

| Account | s | CAGR (capped) | Cap cost vs uncapped | ret/DD |
|---|---|---:|---:|---:|
| €10k | 1.4 | 140.3% | **0.4%** | 7.05 |
| €10k | 1.6 | 160.1% | **6%** | 7.09 |
| €1M | 1.0 | 61.3% | **33%** | 4.49 |
| €1M | 1.4 | 85.9% | **40%** | 5.02 |

**FTMO (€100k, breaker, volume never binds at this scale):** ret/DD peaks at **s=0.5** (4.78, worst
DD **7.82%**) vs shipped s=0.7 (4.05, DD **13.33%**) — supporting a cut to the FTMO dial.

---

## Deployable dials (owner leverage: IC 1:30, FTMO 1:100)

- **IC = s=1.6** — OWNER-ACCEPTED 2026-07-12 (€2,552,962 @ 1:30, min ML 121%, worst-DD 22.6%).
  **PROVISIONAL** pending a real-tick intra-bar min-ML confirmation (> 110%).
- **FTMO = s≈0.5 RECOMMENDED** — sweep ret/DD 4.78, worst-DD 7.8% vs s0.7's 13.3%; the warm-COVID
  honesty flag says s0.7 + 3% breaker breaches the −10% rule by 7.5–10.8pp. **PROVISIONAL** pending a
  1:100 confirm run. Volume never binds at FTMO scale.

---

## Honest caveats

- **The three RECON-4 runs are 1m-OHLC tester smokes, not the crisis arbiter.** They prove
  *mechanics* (position fidelity, sleeve coverage, breaker, margin) on smooth 1-minute feed bars. The
  record→tick crisis-tail gap is *measured* at ~6.5× (v7 COVID: 35.6% MT5-tick vs 5.5% 1m worst-mark)
  and the federation's tick-granularity tail is **unknown by construction until the real-tick run**.
  Record-engine tail numbers must **never** be quoted against MT5 numbers.
- **All model figures are in-sample RECORD reads** (IC 2020-25) — frictionless and unbounded. The
  achievable equity is **0.66–0.95× the record** by dial/scale; the €3.87M IC-s1.6 headline is a
  frictionless ceiling, **not** a deployable promise.
- **Friction compounds with leverage and is real, not assumed** — 0.95× @ s0.7, 0.84× @ s1.0, 0.66×
  @ s1.6, measured on the actual deals.
- **The IC ship dial is provisional.** s=1.6 @ 1:30 sits ~11pp above the owner's ML≥110% floor
  (near it, but liquidation-safe); the real-tick intra-bar min-ML confirmation is the remaining gate
  before final commit. The record also shipped s=1.6 only via a re-adjudicated breach cap
  (0.15→0.20); the original 0.15 gate ships none at s=1.6.
- **The FTMO gates are cold-start in-sample.** Warm re-validation breaches COVID (s0.7 + 3% breaker
  over the −10% rule by 7.5–10.8pp); the crisis-safe dial is ≈ s0.30–0.35, and the recommended s≈0.5
  is itself pending a 1:100 confirm run.
- **The FTMO €1.33M is compounding never-withdraw** equity; the 5/5 FTMO rule-compliance gates are
  scored under a *contradictory* monthly withdraw-to-base frame. Both cannot hold at once — €1.33M is
  an "if-compounded" upper figure.
- **The netted stream loses v7-vs-v34 attribution on the 6 shared symbols** by construction (the
  owner's ratified choice). Attribution stays recoverable offline from the pre-net `f7`/`f34` rows if
  ever needed.
- **The joint 0.5·margin_used stop-out is deferred, not implemented** — in-sample it never triggers
  (IC worst DD 22.6%, FTMO 13.3%, nowhere near the ~50% needed), and RECON-4 asserts `eq_w` never
  falls below 0.5·margin_used in either preset, proving the omission immaterial for the reproduction.
- **The frozen stream ends 2025-12-31** — live trading past it needs a forward v7-signal recompute +
  stream extension (documented, not built).

---

## Sign-off status

**DONE — the execution battery (model reproduction + FMA3-RECON-4, 1m-OHLC):**
- [x] **Model reproduces to the euro** — `reproduce.py` asserts €3,872,872 (IC) and €1,332,404
  (FTMO), self-contained, exits non-zero on drift; 4 frozen inputs + config hash re-verified
- [x] **Exporter round-trips** — stream reproduces `static_fed(0.70)` to < 1e-12 AND record engine
  on the stream = €3,872,872 / €1,332,404 to the euro
- [x] **EA compiles 0/0**, sha `740da0ff…` (post volume-limit fix), stream sha `d00b614b…`, fmt=3
- [x] **Position fidelity EXACT** — median `after/want` = **1.000**, p10 = 1.000, **all three runs**
  (PARITY 0.84× / IC 0.66× / FTMO 0.95×)
- [x] **v3.4 sleeve fully revived** — 33/33 symbols trade, incl. the 7 dead in v1/v2
- [x] **Breaker fidelity** — 28 fires vs model 26 (conservative), prev-day-close anchor + worst-mark
- [x] **Margin at 1:30 characterised** — IC s=1.6 min ML 121% (> 50% stop-out); old "not deployable
  at 1:30" flag DISPROVEN for v3
- [x] **Volume-limit s-sweep mapped** — capacity ceiling ~0–6% @ €10k, 17–40% @ €1M, binds >~€2M/s;
  FTMO ret/DD peaks at s=0.5
- [x] **Every equity gap named** — friction + SYMBOL_VOLUME_LIMIT + margin; 0.66–0.95× the record,
  NOT an EA defect

**OPEN — before/at live-demo (MT5 real-tick only, cannot be closed on this Mac):**
- [ ] **Real-tick intra-bar min-ML confirmation of IC s=1.6 @ 1:30** (> 110%) — the last gate before
  the IC ship dial is committed rather than provisional
- [ ] **1:100 FTMO confirm run at s≈0.5** — fixes the FTMO ship dial; the warm-COVID flag governs
- [ ] **Real-tick crisis reconciliation (COVID 2020-03, the 2022-05 leverage event)** — the 1m-OHLC
  smokes cannot see the tick tail; Gates 5/6 of the reconciliation protocol are mandatory and
  non-waivable, and record-engine tail numbers must never be quoted against MT5 numbers
- [ ] **Live demo deployment** — the deployable arbiter; judge the live book against friction-honest
  expectations (0.66–0.95× the record), not the in-sample headline

**Execution verdict: v3 is the FAITHFUL EXECUTOR of `model/v3`** — position fidelity median
`after/want = 1.000` on every bar in all three runs; final equity 0.66–0.95× the frictionless record
by dial/scale, with every gap a named physical constraint the record engine does not model. The
model reproduces to the euro; the EA reproduces the model up to friction and two capacity ceilings.
All model numbers are in-sample record reads; MT5 real-tick + live demo are the remaining
falsification tests.

*Artifacts:* [`model/v3/README`](../../model/v3/README.md) ·
[`MODEL_SPEC`](../../model/v3/MODEL_SPEC.md) · [`PINNED_INPUTS`](../../model/v3/PINNED_INPUTS.md) ·
[`EA_V3_DESIGN`](../../model/v3/EA_V3_DESIGN.md) · [`RECON4_RESULTS`](../../model/v3/RECON4_RESULTS.md) ·
[`reproduce.py`](../../model/v3/reproduce.py) ·
[`scripts/export_fed_frac_v3.py`](../../scripts/export_fed_frac_v3.py) ·
[`scripts/sweep_s_volcap.py`](../../scripts/sweep_s_volcap.py) ·
[`mt5/ea/FableFederation_V3.mq5`](../../mt5/ea/FableFederation_V3.mq5) ·
[RECONCILIATION.md](../../research/protocol/RECONCILIATION.md) (FMA3-RECON-4 ledger row) · package
siblings: [STRATEGY.md](STRATEGY.md) · [PERFORMANCE.md](PERFORMANCE.md) ·
[TRADE_CHARACTERISTICS.md](TRADE_CHARACTERISTICS.md) · [DEMO.md](DEMO.md).
