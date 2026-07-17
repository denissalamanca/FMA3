# V3.0 performance analysis

> **⚡ SUPERSEDED IN PART (2026-07-15) — see [CURRENT_STATE.md](CURRENT_STATE.md).** This doc describes the RECON-4-era `FableFederation_V3` **CSV-replay** EA. The current executor is the **native, live-computing** `FableBookNative` EA — full-window 2020-2025 real execution net **€2,934,301** (0.76× the frictionless record), **RECONCILED** on engine fidelity (drawdown +0.7pp, position fidelity ~perfect), the −12.9pp CAGR gap being **swap-led execution friction**. `CURRENT_STATE.md` **wins** where they disagree.

**v3.0 is the faithful-executor release.** v1.0 shipped the **model** — a Python record-engine book
(the static blend of the Core band book at capital share w = 0.70 and the Satellite fixed-fraction
book at 0.30, run through FMA2's 1-minute worst-mark single cross-margined account engine). v3.0
ships the **EA that provably executes that model on MT5** (`FableFederation_V3.ex5`, sha
`740da0ff…`), plus the honest deployable reality: the dials, the three physical constraints, and the
measured friction between the frictionless record and a real retail account. The canonical model
home is [`model/v3/`](../../model/v3/) — config hash **`51a7541cc2aaa593`**, `w_v7 = 0.70`, matrix =
`static_fed(0.70) × s` through the 1-minute worst-mark record engine, reproduced to the euro by
[`model/v3/reproduce.py`](../../model/v3/reproduce.py) on 2026-07-12. Cite it as the source of truth
([README](../../model/v3/README.md), [MODEL_SPEC](../../model/v3/MODEL_SPEC.md),
[PINNED_INPUTS](../../model/v3/PINNED_INPUTS.md), [EA_V3_DESIGN](../../model/v3/EA_V3_DESIGN.md),
[RECON4_RESULTS](../../model/v3/RECON4_RESULTS.md)).

**The model figures are in-sample record reads (IC 2020-25, 1m worst-mark). MT5 real-tick + live
demo remain the falsification tests. Achievable equity is 0.66–0.95× the record by dial/scale — do
NOT read a model number as a deployable promise.** Structure and mechanics in
[STRATEGY.md](STRATEGY.md); reconciliation protocol in
[RECONCILIATION.md](../../research/protocol/RECONCILIATION.md).

---

## Headline — the model of record (two dials, frozen)

The IC and FTMO dashboards are the **same blended book at two scale dials `s`** through the same
1m worst-mark engine ([MODEL_SPEC](../../model/v3/MODEL_SPEC.md)):

| Preset | Seed | Dial | Final equity | CAGR | MaxDD (worst-mark) | Sharpe | Extras |
|---|---:|---|---:|---:|---:|---:|---|
| **IC** (H-RISK-1) | €10,000 | s = **1.6**, compounding | **€3,872,872** | **+170.2%** | **22.58%** | **2.465** | crisis tail 8.12% |
| **FTMO** (H-RISK-2b) | €100,000 | s = **0.7** + daily breaker x=3.0% | **€1,332,404** | **+54.02%** | **13.33%** | — | **26** breaker fires |

*Worst-mark is the harsher convention: the engine co-times every open position at its worst
1-minute price inside each bar, so 22.58% (IC) / 13.33% (FTMO) are honest floating-equity
drawdowns, not daily-close smoothings. The FTMO internal 3% breaker is **tighter** than the external
FTMO 5% rule, so the 5% rule is essentially never reached; the breaker cost 5.30pp CAGR (no-breaker
s=0.7 → 59.32%, with breaker → 54.02%).*

**These are frictionless, unbounded record reads.** The record engine sizes `lots = frac·balance/unit`
with no transaction cost beyond its coarse model, no broker volume ceiling, and no retail margin
grant. A real account has all three. §The three physical constraints and §RECON-4 below quantify
exactly what each one costs.

---

## The deployed reality — FMA3-RECON-4 (v3 vs model, 3 MT5 runs)

Three tester runs, IC Markets account 11078280, 1m-OHLC, HEDGING, 1:500 for reproduction
([RECON4_RESULTS](../../model/v3/RECON4_RESULTS.md)). The verdict:
**v3 holds the model's EXACT target position; the equity gap is dial/scale friction, not defect.**

| Run | Preset | Dial | Seed | v3 equity | Model | v3/model | Rejects | Fidelity (median after/want) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `FABLE_PARITY_S10` | s=1.0 | €10k | **€391,873** | €464,991 | **0.84×** | 0 | **1.000** (33/33 symbols) |
| 2 | `FABLE_IC` | s=1.6 | €10k | **€2,552,962** *(RECON-4/FableFederation_V3; superseded — native EA: €2.93M / 0.76×, see CURRENT_STATE.md)* | €3,872,872 | **0.66×** | 0¹ | **1.000** |
| 3 | `FABLE_FTMO` | s=0.7 | €100k | **€1,265,541** | €1,332,404 | **0.95×** | 0 | **1.000** (0 volume-capped) |

¹ After the volume-limit fix (sha `740da0ff…`): 0 rejects, €2,552,961.62 (physical cap). The
pre-fix build spun on volume-limited legs (retried the un-holdable excess every bar); the clamp
removes the spin and the equity is unchanged, because the cap is physical.

**What is proven:**

1. **v3 holds the model's exact target position.** `after/want` — v3's held fraction over the
   model's target fraction — has **median 1.000, p10 = 1.000** in all three runs. Where v3 *can*
   place the order, it holds precisely `fed_frac·s`.
2. **The Satellite sleeve is alive.** All 33 symbols trade, including the 7 that were silently dead in
   v1/v2 via an `EurPerQuote` quote-currency bug (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK,
   EURSEK) — v3's unconditional full-map `eurq` (8 quote currencies) revives them end-to-end.
3. **The breaker works.** FTMO fired **28×** (model 26) on the previous-server-day-close anchor +
   worst-mark `eq_w`; the +2 is v3's worst-mark being marginally more sensitive (conservative).
   Margin never stressed.

**The friction ladder — measured, monotone in leverage:**

| Dial | v3/model | Reading |
|---|---:|---|
| s = 0.7 (FTMO) | **0.95×** | deployable dial: near-clean, 0 rejects, no volume caps |
| s = 1.0 (parity) | **0.84×** | spread/commission compounding at unit scale |
| s = 1.6 (IC) | **0.66×** | friction + volume ceiling + margin all bind |

Transaction friction (spread/commission) **compounds with leverage** — the whole ladder is that one
cost growing as `s` grows, plus the volume ceiling engaging at s=1.6/€10k scale. **At the deployable
FTMO dial the model reproduces cleanly (0.95×, zero rejects, no caps).**

---

## The three physical constraints — why the record is not the account

The record engine is frictionless and unbounded; a real account is not. Every named gap below is a
constraint the record does **not** model, not an EA defect ([RECON4_RESULTS](../../model/v3/RECON4_RESULTS.md),
[MODEL_SPEC §Honesty flags](../../model/v3/MODEL_SPEC.md)):

| # | Constraint | Record engine | Real account | Binds when | Cost |
|---|---|---|---|---|---|
| 1 | **Transaction friction** (spread/commission) | modeled coarsely | real per-trade cost, crosses the spread | **always**; compounds with leverage | 0.95× @ s0.7 → 0.84× @ s1.0 → 0.66× @ s1.6 |
| 2 | **Broker `SYMBOL_VOLUME_LIMIT`** | **none** | XAUUSD **10**, SOLUSD **1000**, ETHUSD **100** lots (this tier) | book past **~€2M/s** (XAUUSD binds first) | ~0–6% @ €10k, **17–40% @ €1M** |
| 3 | **Broker margin** | model per-symbol leverage | broker leverage / retail 1:30 | high `s` on retail leverage | self-limits the book; IC s=1.6 @ 1:30 ran full backtest at min ML 121% |

**Constraint 2 is a capacity ceiling that scales with account size, not a dial-shifter.** The
€3.87M IC-s1.6 record is **not physically reachable on one retail account at that scale** — XAUUSD
alone (the tightest limit) caps at ~half the model's target once the book compounds past ~€2M/s.
Two scaling levers past the ceiling, both owner-raised and valid:

1. **Higher-tier account** — larger `SYMBOL_VOLUME_LIMIT`; simplest, one account, one terminal.
2. **N parallel accounts at €C/N each** — each holds 1/N of the model position (under the
   per-account limit); the **aggregate = the full model**, so N accounts multiply every volume
   limit by N. Scales linearly. Caveats: N terminals in lockstep; small-symbol min-lot bites only
   if €C/N gets small; pure capacity, no diversification.

**Constraint 3 corrected (FMA3-RECON-4, 2026-07-12):** the old "s=1.6 undeployable at 1:30" flag
was v1-over-leverage-specific and is **disproven for v3**. v3's own margin cap (0.9·balance on
MODEL per-symbol leverage, which ≈ a 1:30 account's per-symbol grant) self-limits the book, so
s=1.6 @ 1:30 ran the full 2020–2025 backtest at **min ML 121%** — far above IC's 50% stop-out (a
~55% peak-book DD would be needed to liquidate, vs the 21% historical worst), ~11pp above the
owner's ML≥110% self-limit.

---

## The volume-constrained scale frontier (FMA3-024)

The volume-limit sweep (engine with `volume_limit`; no-cap validated == €3,872,872). The cap
**lowers the whole curve** but does not change where ret/DD is maximized — IC still favours high `s`,
the ceiling just costs more as the account grows ([RECON4_RESULTS](../../model/v3/RECON4_RESULTS.md)):

| Account | s | CAGR (capped) | Cap cost vs uncapped | ret/DD |
|---|---|---:|---:|---:|
| €10k | 1.4 | 140.3% | **0.4%** | 7.05 |
| €10k | 1.6 | 160.1% | **6%** | 7.09 |
| €1M | 1.0 | 61.3% | **33%** | 4.49 |
| €1M | 1.4 | 85.9% | **40%** | 5.02 |

**Read the two scales together.** At €10k the cap is nearly free (0.4–6%) — a small book never
approaches the lot ceilings. At €1M the *same dials* pay 33–40% to the cap, because XAUUSD/SOL/ETH
positions now exceed the broker's per-symbol lot limit and the excess simply cannot be held. This
is the capacity ceiling made numeric: friction is not fixed, it grows with the book.

**FTMO (€100k, breaker, volume never binds at this scale):** ret/DD **peaks at s=0.5** (4.78, worst-DD
7.82%) versus the shipped s=0.7 (4.05, worst-DD 13.33%) — cutting the dial nearly halves the
drawdown for a better risk-adjusted return. Volume never engages at FTMO scale; the −10%/−5% rules
govern.

**Deployment reframe (owner leverage: IC 1:30, FTMO 1:30 — the FTMO demo is 80,000 EUR / 1:30; leverage was proven a non-event, so no higher-leverage variant is owed):** at 1:30 the **margin** ceiling binds
first (~s0.7), keeping the IC book small enough that **volume never engages** — so *margin, not
volume, sets the IC dial*. Volume is a large-account / high-leverage capacity concern only.

---

## Deployable dials (owner leverage: IC 1:30, FTMO 1:30 — the FTMO demo is 80,000 EUR / 1:30; leverage proven a non-event)

| Preset | Ship dial | Basis | Status |
|---|---|---|---|
| **IC** | **s = 1.6** | EUR 2.55M @ 1:30 *(RECON-4/FableFederation_V3; superseded — native EA: €2.93M / 0.76×, see CURRENT_STATE.md)*, min ML **121%** (vs IC's 50% stop-out, owner's ML≥110% floor), worst-DD 22.6% | **OWNER-ACCEPTED 2026-07-12; PROVISIONAL** pending real-tick intra-bar min-ML confirm (>110%) |
| **FTMO** | **s ≈ 0.5** RECOMMENDED | sweep ret/DD 4.78, worst-DD **7.8%** vs s0.7's 13.3%; warm-COVID flag says s0.7 breaches the −10% rule | **PROVISIONAL** pending a real-tick confirm run (FABLE_FTMO_S04/05); leverage was proven a non-event (bit-identical equity), so no 1:100 run is owed — the demo is 80,000 EUR / 1:30 |

The IC decision reverses the pre-v3 "not deployable at 1:30" flag: v3's self-limiting margin cap
makes s=1.6 liquidation-safe at retail 1:30 (min ML 121%, ~11pp over the owner's floor). The final
commit awaits a real-tick run confirming the intra-bar min ML holds above 110%. The FTMO
recommendation cuts the shipped s=0.7 dial toward s≈0.5 on both the ret/DD sweep and the warm-COVID
crisis flag; margin is a non-issue at 1:30 (leverage was proven a non-event), so the FTMO −10%/−5% rules do the governing.

---

## Honest caveats

- **The model figures are in-sample record reads, not deployable promises.** €3,872,872 (IC) and
  €1,332,404 (FTMO) are 1m worst-mark record-engine equities on IC 2020-25 — the development window
  of both parent programs. Achievable equity is **0.66–0.95× the record** by dial and scale, as
  RECON-4 measured directly. Do not quote a model number as a live target.
- **The €3.87M IC-s1.6 record is a frictionless ceiling, not physically reachable on one retail
  account at scale.** XAUUSD's 10-lot limit caps the position at ~half the model's target past
  ~€2M/s of book. Reaching the model requires a higher-tier account or N parallel accounts at €C/N;
  a single retail account tops out well below €3.87M.
- **Both deployable dials are PROVISIONAL.** IC s=1.6 is owner-accepted but awaits a real-tick
  intra-bar min-ML confirmation (>110%); FTMO s≈0.5 awaits a real-tick confirm run (leverage proven a non-event, so no 1:100 run is owed; the demo is 80,000 EUR / 1:30). Both were adjudicated
  on 1m-OHLC smoke tests per the staged validation protocol — real-tick is the next arbiter.
- **The FTMO shipped dial (s=0.7) is unsafe on warm re-validation.** The RECON-4 s0.7 run reproduces
  the model at 0.95×, but the warm-COVID flag shows s0.7 + 3% breaker breaches the −10% rule by
  7.5–10.8pp of the crisis; the crisis-safe dial is ≈ s0.30–0.35, and the ret/DD sweep independently
  favours s=0.5. Do not deploy s=0.7 on FTMO on the strength of the 0.95× reproduction alone.
- **The crisis tail is engine-relative and the deployable tail is unknown.** The 8.12% IC crisis
  tail is a 1m worst-mark number; the parents' measured tick↔1m gap on COVID is ~6.5× (35.6% vs
  ~5.5% for Core). No tick run of the blend exists — MT5 real-tick on the owner's machine is the
  arbiter, not this document.
- **Friction compounds with leverage and is real.** The 0.95× → 0.84× → 0.66× ladder is spread,
  commission, volume caps, and margin — priced by the tester, not assumed away. Every gap is a named
  physical constraint; none is an EA defect (position fidelity median 1.000 across all three runs).
- **v3 discards the entire v1/v2 VBalance/quarterly-reseed/e34 stack.** v1/v2 sized off share weights
  a live s-levered account cannot reconstruct, so they diverge whenever s≠1 (both dials are s≠1).
  v3 replays a precomputed unified 33-symbol netted `fed_frac` stream — the only faithful path — and
  RECON-4 confirms it holds the model's exact target position.

**All model numbers above are in-sample (IC 2020-25, 1m worst-mark); achievable equity is 0.66–0.95×
the record by dial/scale; MT5 real-tick + live demo are the remaining falsification tests.**
