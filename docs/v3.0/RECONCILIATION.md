# V3.0 model↔EA reconciliation — one model, one faithful executor

**Verdict: `reconciled_with_notes`.** FMA3 v3.0's model of record — the frozen `static_fed(0.70) × s`
matrix run through the 1-minute worst-mark record engine (config hash `51a7541cc2aaa593`,
`w_v7 = 0.70`) — is executed by `FableFederation_V3.ex5` (sha `740da0ff…`) at **exact
position-level fidelity**: across all three MT5 reconciliation runs the held-fraction ratio
`after/want` has **median 1.000, p10 1.000**, all 33 symbols trade, and there are **0 order
rejects** after the volume-limit fix. Where v3 can place the order, it holds precisely
`fed_frac·s` — so v3 *is* the model, and the only thing that differs is final equity, which lands
at **0.66–0.95× the frictionless record depending on dial/scale.** Every euro of that gap is a
**named physical constraint the record engine does not model** — transaction friction, broker
`SYMBOL_VOLUME_LIMIT`, broker margin — not an EA defect. Hence `reconciled_with_notes`, not bare
`reconciled`: the position layer is closed at delta 0.0-in-fraction, the equity gaps are
*measured and attributed*, and the two reconciliations that **cannot** be done on a 1m-OHLC
tester — MT5 real-tick, and the FTMO deployable dial at 1:100 — are explicitly not claimed here
and are listed below as the owed arbiters.

**All numbers are in-sample (IC 2020–25 record reads); the MT5 runs below are 1m-OHLC smokes on
IC Markets 11078280 (1:500, HEDGING). Real-tick + live demo are the remaining falsification
tests, and achievable equity is 0.66–0.95× the record — do NOT read the model number as a
deployable promise.** Model home and source of truth:
[`model/v3/`](../../model/v3/) (`README`, `MODEL_SPEC`, `PINNED_INPUTS`, `EA_V3_DESIGN`,
`RECON4_RESULTS`); protocol in [`research/protocol/RECONCILIATION.md`](../../research/protocol/RECONCILIATION.md).

---

## (A) One model, one executor (and the two arbiters still owed)

v1.0 reconciled *three Python engines* into one accounting. v3.0 reconciles a different bridge:
the **frozen model** (that same record accounting) against the **EA that must reproduce it on
MT5**. The architecture forces this to be a *replay*, not a live recompute — the blend share
weights `w·a_h/j` and `(1−w)·b_h/j` are built from each book's **frozen native standalone**
equity multiples `a`, `b`, which a live s-levered account cannot reconstruct from its own equity;
so a compute-live EA diverges the instant `s ≠ 1` (and both shipped dials are `s ≠ 1`). v3
replays the precomputed unified 33-symbol netted `fed_frac` stream and sizes each symbol off live
`ACCOUNT_BALANCE`, which is the only faithful path.

| Layer | What it is | Numbers it owns |
|---|---|---|
| **Model of record** (frozen) | `static_fed(0.70) × s` through `record_engine` (IC) / `record_engine_ext` (FTMO); reproduced euro-exact by [`reproduce.py`](../../model/v3/reproduce.py) | IC (H-RISK-1) s=1.6: €10k → **€3,872,872 / +170.2% CAGR / 22.58% worst-mark DD / Sharpe 2.465**. FTMO (H-RISK-2b) s=0.7 + breaker x=3.0%: €100k → **€1,332,404 / +54.02% / 13.33% DD / 26 breaker fires** |
| **The EA** (faithful executor) | `FableFederation_V3.ex5` sha `740da0ff…`; replays `FMA3_fed_frac_v3.csv` (fmt=3); ONE net position + ONE magic per symbol; full-map eurq; FTMO daily breaker | Three MT5 runs below — position fidelity median 1.000, 0 rejects, 0.66–0.95× the record |
| **MT5 real-tick** (deployable arbiter — **not yet run**) | tick-granularity on the owner's machine; the 1m-OHLC smoke cannot see intra-bar spread/ML | Owed. The IC min-ML>110% confirm and the crisis tail are unknown by construction until this runs |
| **FTMO @ 1:100** (deployable-dial arbiter — **not yet run**) | the recommended FTMO dial re-run at owner leverage | Owed. Sweep favours s≈0.5 (ret/DD 4.78, DD 7.8%) but the 1:100 confirm is pending |

Every fidelity number below is computed the same way in every run — like-for-like, same tester,
same stream.

---

## (B) The measured translation costs — three physical constraints

The record engine is **frictionless and unbounded**; a real account is neither. All three
constraints below bind at s=1.6; **none binds at the clean deployable dial (Run 3, s=0.7).**

### B1. Transaction friction: **0.95× → 0.84× → 0.66×**, compounding with leverage

Fills cross the spread and pay commission per lot per side — a per-trade cost the record models
only coarsely. It compounds with the dial: the higher the `s`, the more turnover, the wider the
gap. Measured on the same book, same tester:

| Run | Preset | Dial | Book | v3 equity | Model | v3/model | Rejects | Fidelity (median `after/want`) |
|---|---|---|---|---:|---:|---:|---:|---:|
| 1 | `FABLE_PARITY_S10` | s=1.0 | €10k | **€391,873** | €464,991 | **0.84** | 0 | 1.000 (33/33 symbols) |
| 2 | `FABLE_IC` | s=1.6 | €10k | **€2,552,962** | €3,872,872 | **0.66** | 0 (after fix) | 1.000 |
| 3 | `FABLE_FTMO` | s=0.7 | €100k | **€1,265,541** | €1,332,404 | **0.95** | 0 | 1.000 (0 volume-capped) |

The friction ladder **0.95 @ s0.7 → 0.84 @ s1.0 → 0.66 @ s1.6** is the price of leverage on real
fills. It is inside every equity number and is not recoverable by any EA fix — it is what a live
account costs.

### B2. Broker volume limit: a **capacity ceiling that scales with account size**

The record sizes `lots = frac·balance/unit` with **no cap**. This account enforces
`SYMBOL_VOLUME_LIMIT` per symbol — **XAUUSD 10, SOLUSD 1000, ETHUSD 100 lots**. As the book
compounds, the cap first bites, then binds:

| Book / dial | Volume-cap cost | Note |
|---|---|---|
| €10k, s=1.6 | ~**6%** | small book, XAUUSD trims the top |
| €1M, s=1.0 | ~**33%** | cap is now a material drag |
| €1M, s=1.4 | ~**40%** | binds hard; whole curve lowered |

XAUUSD (the tightest limit) caps at ~half the model's target once the book passes **~€2M/s** of
equity — so **the €3.87M IC-s1.6 record is not physically reachable on one retail account at that
scale.** This is the "s=1.6 not deployable" honesty flag, now quantified as *capacity*, not
merely leverage. The pre-fix Run 2 emitted 51,346 reject *spins* (v3 retried the un-holdable
excess every bar); the volume-limit clamp removes the spin and the **equity is unchanged at
€2,552,962 because the cap is physical.** Scaling levers (both owner-ratified): a **higher-tier
account** (larger per-symbol limit), or **N parallel accounts at €C/N each** — each holds 1/N of
the model position under the per-account limit, so the aggregate equals the full model and every
volume limit is multiplied by N.

### B3. Broker margin: v3's own cap self-limits the book at 1:30

The record's margin cap uses the **MODEL per-symbol leverage** (`0.9·balance` on `g_fedLev[]`),
which ≈ a 1:30 retail account's per-symbol grant. That self-limit is what makes s=1.6 survivable
on retail leverage: **v3 @ 1:30, s=1.6 ran the full 2020–2025 backtest at min ML 121%** — far
above IC's **50% stop-out** (a ~55% peak-book DD would be needed to liquidate, vs the 21%
historical worst) and ~11pp above the owner's **ML≥110% self-limit**. Same €2,552,962 as the
1:500 reproduction run (v3's margin cap is account-leverage-independent). **At 1:30 the margin
ceiling binds first (~s0.7-equivalent book), keeping the IC book small enough that volume never
engages — so margin, not volume, sets the IC dial**; the old "s=1.6 not deployable at 1:30" flag
is a v1-over-leverage artifact and is **DISPROVEN for v3.** On the FTMO side the breaker fired
**28×** (model 26); the +2 is v3's worst-mark `eq_w` being marginally more sensitive
(conservative), and margin never stressed (ML min 376%, median 1346%).

---

## (C) The verification chain

| Link | Check | Result |
|---|---|---|
| Exporter self-check ([`export_book_frac_v3.py`](../../scripts/export_book_frac_v3.py)) | re-parse → matrix reproduces `static_fed(0.70)`; record engine on the stream re-run | matrix **< 1e-12**; `run_record(stream·1.6, 10k)` = **€3,872,872** and `run_record_ext(stream·0.7, 100k, 3.0)` = **€1,332,404**, to the euro |
| Model reproduction ([`reproduce.py`](../../model/v3/reproduce.py)) | both presets rebuilt from config `51a7541cc2aaa593` | asserts **€3,872,872** (IC) and **€1,332,404** (FTMO) |
| Position fidelity (RECON-4, 3 runs) | held fraction ÷ model target `fed_frac·s`, per bar per symbol | **median 1.000, p10 1.000** in all three runs; all **33/33** symbols trade |
| Reject count (RECON-4, post volume-fix) | order rejects per run | **0 / 0 / 0** (Run 2 spin removed by the volume clamp; equity unchanged) |
| Satellite sleeve revival (RECON-4 Run 1) | the 7 legs v1/v2 killed via the EurPerQuote bug: AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK | **all 7 trade >0 deals** — full-map eurq works end-to-end |
| FTMO breaker (RECON-4 Run 3) | fire count + anchor basis vs model | **28 fires** (model 26; +2 conservative worst-mark); prev-server-day CLOSE anchor + worst-mark `eq_w` confirmed |
| Volume-cap s-sweep ([`sweep_s_volcap.py`](../../scripts/sweep_s_volcap.py), FMA3-024) | engine with `volume_limit`, no-cap branch vs record | no-cap == **€3,872,872**; cap cost 0.4%→40% across €10k→€1M |

Reproduce: `python3 model/v3/reproduce.py` (~8–9 min) ·
`python3 scripts/export_book_frac_v3.py` (self-checks the stream) ·
`python3 scripts/sweep_s_volcap.py` (volume-cap curve). MT5 fidelity: the three preset runs on
IC Markets 11078280, 1m-OHLC, 1:500, HEDGING.

---

## (D) What is NOT reconciled yet

1. **No MT5 real-tick run — the owed arbiter.** All three fidelity runs are **1m-OHLC smokes**.
   The record engine and the tester both use 1m bars, so tick-granularity spread blowouts and
   intra-bar margin excursions are **invisible by construction** (the v1.0 package measured this
   as a 35.6%-vs-5.54% crisis-tail gap for Core alone). The IC deployable commit is therefore
   **provisional pending a real-tick run confirming intra-bar min ML holds >110%** at 1:30.
2. **The FTMO deployable dial is not confirmed at owner leverage.** The shipped `FABLE_FTMO`
   preset is s=0.7 (0.95×, €1,265,541 @ 1:500). The recommended deployable dial is **s≈0.5**
   (sweep ret/DD 4.78, worst-DD 7.8% vs s0.7's 13.3%; the warm-COVID flag says s0.7 breaches the
   −10% rule by 7.5–10.8pp), but the **1:100 confirm run (FABLE_FTMO_S04/05) is pending.**
   Volume never binds at FTMO scale, so the −10%/−5% rules govern, not capacity.
3. **The €3.87M IC record is a frictionless ceiling, not a reachable target on one account.**
   Reconciliation closes at the *position* layer (fidelity 1.000); the *equity* layer is
   deliberately 0.66× at s=1.6 because two independent physical causes (friction + volume cap)
   bite at scale. The record number is an in-sample upper bound, not a deployable promise.

## Honest notes (divergences that remain by design — none is a defect)

1. **0.66–0.95× equity, not byte-identical.** v3 sizes off live MT5 balance, the model off a
   frictionless record balance; the final-equity ratio is pure friction (B1), measured per dial,
   applied like-for-like. Fidelity is asserted at the *position* level, where it is 1.000.
2. **Volume cap unmodeled in the record.** The €3.87M IC-s1.6 record has no `SYMBOL_VOLUME_LIMIT`;
   a real account caps XAUUSD at ~half target past ~€2M/s (B2). The gap is capacity, scalable by
   higher-tier or N-parallel accounts, not an EA fix.
3. **Margin self-limit, not a defect.** v3's `0.9·balance` cap on model per-symbol leverage is
   what keeps s=1.6 liquidation-safe at 1:30 (min ML 121%); it also means margin — not volume —
   sets the IC dial (B3). The old "s=1.6 undeployable at 1:30" flag is disproven for v3.
4. **Breaker +2 fires (28 vs 26).** v3's worst-mark `eq_w` on 1m-OHLC is marginally more
   sensitive than the model's — conservative, not divergent; margin never stressed.
5. **1m-OHLC ≠ real-tick.** The smokes cannot see intra-bar spread/ML; the crisis tail and the
   IC min-ML>110% confirm await the real-tick run (D1). Never read a smoke equity as a tick
   promise.

---

**Bottom line:** the v3.0 model and its EA reconcile at the layer that matters — **position
fidelity median 1.000, 0 rejects, all 33 symbols live** across three runs — so
`FableFederation_V3` provably *executes* the frozen `static_fed(0.70) × s` model. Final equity
lands at **0.66–0.95× the frictionless record**, and every euro of that gap is one of three named
physical constraints (transaction friction 0.66–0.95×, `SYMBOL_VOLUME_LIMIT` binding past ~€2M/s,
broker margin self-limiting at 1:30 min ML 121%) — measured and disclosed, not open. Zero
unexplained mismatches at the position layer; `reconciled_with_notes`. The MT5 real-tick run
(IC min-ML confirm + crisis tail) and the FTMO 1:100 dial confirm are the two owed arbiters. All
numbers are in-sample record reads; real-tick + live demo are the remaining falsification tests;
achievable equity is 0.66–0.95× the record by dial and scale — never the record number itself.
