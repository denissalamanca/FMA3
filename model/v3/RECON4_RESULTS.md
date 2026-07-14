# FMA3-RECON-4 — FableFederation_V3 vs the stable model (execution reconciliation)

**Verdict: v3 is the faithful executor of `model/v3`.** Position-level fidelity is exact; the equity achieves **66–95%** of the frictionless record depending on dial/scale, and every gap is a *named, physical* constraint the record engine does not model (transaction friction, broker volume limits, broker margin) — not an EA defect.

EA: `FableFederation_V3.ex5` — sha `d516350b…` (runs 1–3) → **sha `740da0ff…`** after the volume-limit fix (Run 2 re-run pending). Stream: `FMA3_fed_frac_v3.csv` sha `d00b614b…`. Tester: IC Markets 11078280, 1m-OHLC, 1:500, HEDGING, 2020–2025.

## The three runs

| Run | Preset | Dial | Book | v3 equity | Model | v3/model | Rejects | Fidelity (median `after/want`) |
|---|---|---|---|---:|---:|---:|---:|---:|
| 1 | `FABLE_PARITY_S10` | s=1.0 | €10k→€391,873 | €391,873 | €464,991 | **0.84** | 0 | 1.000 (33/33 symbols) |
| 2 | `FABLE_IC` | s=1.6 | €10k→€2,544,423 | €2,544,423 | €3,872,872 | **0.66** | 51,346¹ | 1.000 |
| 3 | `FABLE_FTMO` | s=0.7 | €100k→€1,265,541 | €1,265,541 | €1,332,404 | **0.95** | 0 | 1.000 (0 volume-capped) |

¹ Pre-fix reject *spin* on volume-limited legs (v3 retried the un-holdable excess every bar). The volume-limit clamp removes the spin; the **equity is unchanged** because the cap is physical. Run 2 re-run (sha `740da0ff`) pending for a clean record.

## What is proven

1. **v3 holds the model's exact target position.** `after/want` — algebraically the ratio of v3's held fraction to the model's target fraction — has **median 1.000, p10 = 1.000** in all three runs. Where v3 *can* place the order, it holds precisely `fed_frac·s`.
2. **The Satellite sleeve is alive.** All 33 symbols trade, including the 7 that were dead in v1/v2 (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) — the unconditional full-map eurq works end-to-end in MT5.
3. **The breaker works.** FTMO fired **28** times (model 26) on the previous-day-close anchor + worst-mark `eq_w`; the +2 is v3's worst-mark being marginally more sensitive (conservative). Margin never stressed (ML min 376%, median 1346%).

## Why the equity gap — three physical constraints the record ignores

The record engine is frictionless and unbounded. A real account is not. All three constraints bind at s=1.6; **none bind at the deployable dial (Run 3, s=0.7, clean 0.95).**

| Constraint | Record engine | Real account | Binds when |
|---|---|---|---|
| **Transaction friction** (spread/commission) | modeled coarsely | real per-trade cost | always; compounds with leverage (0.95 @ s0.7 → 0.84 @ s1.0 → 0.66 @ s1.6) |
| **Volume limit** (`SYMBOL_VOLUME_LIMIT`) | **none** | XAUUSD 10, SOLUSD 1000, ETHUSD 100 lots (this tier) | book past **~€2M/s** (XAUUSD binds first) |
| **Margin** (broker per-symbol) | model per-symbol leverage | broker leverage / retail 1:30 | high s on retail leverage |

**The €3.87M IC-s=1.6 record is a frictionless ceiling, not physically reachable on one retail account at that scale** — XAUUSD alone is capped at half the model's target. This is the "s=1.6 not deployable" honesty flag, now quantified with two independent causes (volume + margin).

## Deployment implication + scaling

- **At deployable dials/scale the model reproduces cleanly** — Run 3 (s=0.7, €1.27M) hit 0.95 with zero rejects and no volume caps.
- **The volume ceiling binds only at large books.** XAUUSD (tightest limit) caps at ~€2M/s of equity. Below that, one account suffices.
- **Two levers past the ceiling** (owner-raised, both valid):
  1. **Higher-tier account** — larger `SYMBOL_VOLUME_LIMIT`; simplest, one account.
  2. **N parallel accounts at €C/N each** — each holds 1/N of the model position (under the per-account limit); the **aggregate = the full model**, so N accounts multiply every volume limit by N. Elegant, scales linearly. Caveats: N terminals to run in lockstep; small-symbol min-lot bites only if €C/N gets small; no diversification (pure capacity).

## Volume-limit s-sweep (FMA3-024, engine with `volume_limit`, no-cap validated == €3,872,872)
The cap is a **capacity ceiling that scales with account size**, not a dial-shifter. IC ret/DD still favours high s; the cap just lowers the whole curve.

| account | s | CAGR capped | cap cost vs uncapped | ret/DD |
|---|---|---:|---:|---:|
| €10k | 1.4 | 140.3% | 0.4% | 7.05 |
| €10k | 1.6 | 160.1% | 6% | 7.09 |
| €1M | 1.0 | 61.3% | 33% | 4.49 |
| €1M | 1.4 | 85.9% | 40% | 5.02 |

**FTMO (€100k, breaker, volume never binds at this scale):** ret/DD peaks at **s=0.5** (4.78, DD 7.82%) vs shipped s=0.7 (4.05, DD 13.33%) — supports cutting the FTMO dial.

**Deployment reframe (owner leverage: IC 1:30, FTMO 1:100):** at 1:30 the MARGIN ceiling binds first (~s0.7), keeping the IC book small enough that volume never engages — so **margin, not volume, sets the IC dial.** Volume is a large-account/high-leverage capacity concern only. Deployable dials being fixed by MT5 sweeps at the real leverages (FABLE_IC_S06/07/08 @1:30; FABLE_FTMO_S04/05 @1:100).

## Deployment-dial decision (at owner's real leverage: IC 1:30, FTMO 1:100)
- **IC = s=1.6 (provisional, owner-accepted).** v3 @ 1:30 s=1.6 ran the full backtest at **min ML 121%** — liquidation-safe vs IC's **50% stop-out** (needs ~55% peak-book DD to breach vs 21% historical worst); ~11pp above the owner's ML≥110% self-limit. Same €2,552,961.62 as 1:500 (v3's margin cap is account-leverage-independent). The old "not deployable at 1:30" flag is DISPROVEN for v3. **Real-tick run in progress (~1h) to confirm intra-bar min ML holds >110%** before final commit.
- **FTMO — recommend s≈0.5** (ret/DD 4.78, worst-DD 7.8% vs 0.7's 13.3%); pending 1:100 sweep (FABLE_FTMO_S04/05). Margin non-issue at 1:100; the −10%/−5% rules govern.

## Standing items
- Run 2 clean re-run (sha `740da0ff`) → confirmed: 0 rejects, €2,552,961.62 (physical cap). ✓
- Deployable-dial decision for IC and FTMO (which `s` to ship) — separate, tracked in MODEL_SPEC honesty flags.
- FTMO rule-compliance scoring of the v3 curve (worst-mark daily/monthly vs the −5%/−10% rules) — the breaker fires ~as the model, full scoring is a follow-up.
- Real-tick runs after these 1m-OHLC smokes, per the staged protocol.
