# V1.0 demo forward-test plan — deployment + monitoring

**The operator's plan for the MT5 demo forward-test of FMA3 v1.0 — the deployable arbiter that the
2026H1 one-shot CONFIRM explicitly hands off to.** It says exactly what to deploy (two parent EA
stacks, side by side, on ONE cross-margined demo account), how the locked federation config maps onto
each stack's own risk dial, what fingerprints to watch, the pre-registered decision rules if the live
path drifts, and the definition of done. Code sources of truth:
[`strategy_fma3.py`](../../strategy_fma3.py) (static federation w=0.70 / s=1.1, config hash
`51a7541cc2aaa593`) → [`scripts/eval_fma3_pin.py`](../../scripts/eval_fma3_pin.py) →
[`research/outputs/fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json); forward pins
[`research/protocol/FORWARD_TEST.md`](../../research/protocol/FORWARD_TEST.md) →
[`research/outputs/forward_oneshot.json`](../../research/outputs/forward_oneshot.json); deployment
authorities are the **parents' own stacks** — NSF5 `mt5/ea/FableMultiAsset1_V7.mq5` + preset
`mt5/presets/FableMultiAsset1_V7_CORE7BAND_R8_IC.set`, and FMA2 `ea/RUNBOOK.md` (Python brain +
`ea/mql5/FableExecutor.mq5` + off-VPS watchdog).

Sibling docs (all `docs/v1.0/`): [STRATEGY](STRATEGY.md) (what the federation is) ·
[PERFORMANCE](PERFORMANCE.md) (the pinned numbers) · [VALIDATION](VALIDATION.md) (gates, red-team,
forward one-shot) · [RECONCILIATION](RECONCILIATION.md) (pin↔deployment parity status) ·
[TRADE_CHARACTERISTICS](TRADE_CHARACTERISTICS.md) (turnover, exposure, per-instrument) · **DEMO**
(this file). Research layer: [whitepaper](../whitepaper/00_WHITEPAPER.md) ·
[REGISTRY](../REGISTRY.md).

> **All numbers are in-sample (IC 2020-25); the 2026H1 one-shot is consumed; MT5 real-tick + live
> demo are the remaining falsification tests.** The forward CONFIRM below was run on a Duka-feed
> proxy book (USA500 proxying USTEC, 14-symbol coverage) — a directional confirmation, **not** the
> deployed book. The demo is the first time the deployed configuration meets data it was never
> fitted on. If live diverges, the backtest is what's wrong.

---

## Where we stand (2026-07-10)

**FMA3 v1.0 is LOCKED, forward-confirmed, and demo-ready.** V1.0 = both parent books unchanged on
one cross-margined €10k account — 70% the v7.0 band book (R8 anchor extraction), 30% the v3.4
fixed-fraction book — **no cross-book rebalancing** (H-FED-2: all four cadences DECLINED), global
scale **s=1.1** (H-FED-3's ceiling rule gave s=1.4; the FMA3-RT probe-robustness adjudication cut it
to 1.1). All six owner gates clear and all seven composite dimensions dominate both parents
([VALIDATION](VALIDATION.md)). The 2026H1 one-shot returned **CONFIRM 4/4**, whose pre-registered
interpretation is exactly one instruction: *proceed to MT5 demo deployment*.

**Headline (engine of record, 1m worst-mark, IC 2020-25, €10k — in-sample; `fma3_v1_pin.json`):**

| Metric | FMA3 v1.0 (w=0.70, s=1.1) |
|---|---|
| CAGR | **+101.4%** |
| MaxDD (worst-mark) | **15.73%** (close-mark 15.62%) |
| Sharpe | **2.467** |
| COVID tail | 5.36% |
| Neg years / quarters | **0 / 6 · 0 / 24** |
| Breach P(DD>30%) worst-mark | 0.0020 (bootstrap median DD 16.80%, p95 23.28%) |
| €10k → | **€665,777** |
| Trades | 25,869 (~1,078/quarter) |

**Forward one-shot (2026-01-01 → 2026-04-30, fresh €10k, CONSUMED;
[FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md)):**

| # | Pre-registered bar | Value | Result |
|---|---|---|---|
| F1 | window worst-mark DD < 20.9% | **17.67%** | PASS |
| F2 | window return > −10% | **+12.34%** | PASS |
| F3 | no joint stop-out or margin-cap breach | stop-outs 0, cap-binds 0 (max margin/balance 0.324, min ML 311%) | PASS |
| F4 | each sub-book window return > −20% | v7 **+15.99%**, v3.4 **+13.59%** | PASS |

Monthly path **+14.94% / −0.25% / +0.41% / −2.42%**, daily Sharpe 1.17 — that path, not the
in-sample curve, is the first live fingerprint (§Monitoring).

**The honest operational headline: there is no FMA3 EA.** The federation is operationally **two
parent EA stacks plus a capital split** — the v7 EA (self-contained MQL5) and the v3.4 stack (Python
brain + MQL5 executor + watchdog) attached to the same account with disjoint magic numbers, each
carrying its share of w and s in its own risk dial. Everything FMA3-specific that runs live is two
numbers: **InpRisk 6.16** and **GLOBAL_SCALE 3.3** (arithmetic below).

---

## Deployment config (exact)

1. **Open ONE IC Markets EU *demo* account** — **Raw Spread (commission-based)**, **EUR**,
   **hedging**, **€10,000 fresh** (mirrors the forward one-shot's fresh-seed convention), same
   server family as the parents' testers (`ICMarketsEU-MT5`, GMT+2/+3 server time).
2. **Market Watch — the union of both universes, IC-native names.** v7 stack: `XAUUSD, USTEC,
   USDJPY, ETHUSD, EURGBP, BTCUSD` + S6 legs `USDJPY/AUDUSD/NZDUSD` + conversion `EURUSD, EURJPY`
   (⚠️ USTEC, not US500 — `InpUS500=USTEC`). v3.4 stack: the 37-instrument universe of FMA2
   `docs/SPEC.md` §1 (33 instruments are active in the locked matrix —
   [TRADE_CHARACTERISTICS](TRADE_CHARACTERISTICS.md)). Overlapping symbols (XAUUSD, USTEC, USDJPY,
   EURGBP, BTCUSD, ETHUSD) are expected — magic numbers attribute them.
3. **v7 stack (the 70% share).** Compile `FableMultiAsset1_V7.mq5` in MetaEditor (magic base
   **360000**). Create the FMA3 preset by copying
   `FableMultiAsset1_V7_CORE7BAND_R8_IC.set` and changing **exactly one line**: `InpRisk=8.0` →
   **`InpRisk=6.16`** (keep `InpInitial=10000.0`, `InpMarginCap=0.9`, band inputs, symbol map —
   everything else byte-identical; suggested name `FableMultiAsset1_V7_CORE7BAND_FMA3W70_IC.set`).
   Attach to any M1 chart, load the preset, enable AutoTrading. Confirm the NSF5 startup checks
   (NSF5 `docs/v7/DEMO.md`): `SLOT-EQUAL over 7 slots … slotW=0.1429`, 7 non-zero sleeve weights,
   decision log trading USTEC.
4. **v3.4 stack (the 30% share).** Follow FMA2 `ea/RUNBOOK.md` §2 in order — brain offline sanity,
   EA reconcile-only first session, watchdog `--dry-run` on a second host for one full session
   before going live — with **exactly one config change**: `GLOBAL_SCALE = 3.3` in
   `ea/brain/brain_config.py`. ⚠️ This changes the stamped config hash: `48c09199fbf83d82` is the
   *standalone scale-10* hash, and the executor's hash guard will (correctly) reject a 3.3-scale
   `target.json` against it. **Re-pin the EA-side expected hash to the newly stamped FMA3 deploy
   hash and record it in the track record — never bypass the guard.** `pytest ea/tests/ -q` (6095
   passing) on the deploy host; `target_engine.py --dry-run` sanity pass.
5. **Magic-number separation — verify, don't assume.** v7 stack: 360000-range. v3.4 stack: magic
   band **8400001–8400008**, one per sleeve, `mag_xau=8400008` (FMA2 `docs/v3.4/DEMO.md` §2; note
   their `RUNBOOK.md` §1.2 still prints the older v3-era 920001–920007 map — the v3.4 DEMO band is
   the current authority). No overlap either way. Magic attribution is the **only** mechanism that
   splits joint-account P&L back into sub-books — the weekly realized-w number depends on it.
6. **Day-1 checks:** every open position's magic resolves to exactly one stack; v7 health file shows
   `volume_rejects=0`; FMA2 kill-switch `NONE`, heartbeats fresh on the watchdog, no
   `config_hash_mismatch`.
7. **Record in the track record:** deploy date, account id, the v7 preset file (and its checksum),
   the FMA2 stamped deploy hash, and the FMA3 config hash `51a7541cc2aaa593` they jointly implement.

Both stacks keep their own margin defenses live: v7 `InpMarginCap=0.9`; v3.4 in-strategy 90% margin
cap + free-margin buffer + the 60% de-gross guard (MKT-3a).

---

## The two risk dials — s=1.1 mapped onto each stack (the arithmetic)

The pinned federation matrix is `fed_frac = frac7·(w·A/J) + frac34·((1−w)·B/J)`, all `× s`
(`strategy_fma3.py::construction`). At deploy (A=B=J=1) each stack must therefore size at exactly
**its native dial × its capital share × s**. Both parent dials are linear in their risk input, so
the mapping is one multiplication each:

| Stack | Native dial (basis) | × share | × s | **Deployed dial** | Equivalent sub-account view |
|---|---|---|---|---|---|
| v7.0 band book | `InpRisk = 8` (the R8 anchor extraction, `strategy_fma3.py::parents.v7`; Python cagr_bd 89.7%, byte-reconciled) | × 0.70 | × 1.1 | **`InpRisk = 6.16`** on the full €10k | €7,000 sub-account at R = 8×1.1 = **8.8** (6.16 × 10,000 = 8.8 × 7,000) |
| v3.4 book | `GLOBAL_SCALE = 10` (their locked re-pick) | × 0.30 | × 1.1 | **`GLOBAL_SCALE = 3.30`** on the full €10k | €3,000 sub-account at scale 10×1.1 = **11** (3.3 × 10,000 = 11 × 3,000) |

Three honest notes on those dials:

- **The v7 dial reads below the parent's "never run V7 below R8" floor (NSF5 `docs/v7/DEMO.md`) — by
  design, not by accident.** Per unit of *sub-capital* the book runs at R8.8, above the floor; the
  band rule triggers on sleeve *shares*, which are scale-invariant; and the FMA3 pin was computed at
  exactly this sizing (frac7 × 0.70 × 1.1). The floor warning is about the standalone frontier, not
  this configuration.
- **The v3.4 slice runs at an 11-equivalent per sub-capital — above its own standalone ceiling.**
  Their pre-registration rejected scale 11 for failing the negQ gate standalone. The federation pins
  negQ **0/24** at s=1.1 and the forward one-shot confirmed, which is the only license this sizing
  has. Slice-level negative quarters are an explicit demo watch item (§Decision rules).
- **Hard limits rescale with the dial.** v3.4 structural caps are 0.18×scale (overnight gold) and
  fixed fractions of sub-equity: at GLOBAL_SCALE 3.3 that is overnight `|XAUUSD| ≤ 0.594×E_joint`
  and managed crosses `≤ 0.165×E_joint` at deploy (both drift with the realized sub-share — verify
  against `broker_snapshot.json`, not against the standalone 1.80×E figure). H-CAPS-1 verified the
  *joint* gold stack (both stacks' gold summed) never exceeded the sum of entitlements in-sample —
  0 of 49,379 hours (`hcaps1_analysis.json`).

Fallback point, pre-derived: stepping the federation to **s=1.0** means `InpRisk = 5.60` and
`GLOBAL_SCALE = 3.00` (8×0.7×1.0 and 10×0.3×1.0), preserving w=0.70.

---

## What does NOT exist yet (read before trusting the monitoring)

Disclosed up front, in the spirit of the parents' review-item sections. None of these blocks the
demo; all of them shape what the demo can and cannot prove.

1. **No unified FMA3 EA.** Nothing at runtime enforces w or s jointly — they exist only as the two
   dials above. If one stack is accidentally re-configured, the other will not notice.
2. **No virtual sub-account wall.** The pin's construction keeps each book blind to the other's P&L
   (`strategy_fma3.py`, PROTOCOL §5.7). Live: the v7 EA compounds its own internal sleeve seeds
   (`InpInitial`-seeded — a good approximation of the convention), but the v3.4 brain's targets are
   *fractions of account equity* (FMA2 `ea/RUNBOOK.md` §1) — the executor reads **joint** equity, so
   the v3.4 slice's capital base drifts with v7's P&L. This shared-equity coupling is exactly the
   realized-w drift the ±20% probes stress-tested (the reason s=1.1, not 1.4) — bounded, disclosed,
   and measured weekly, not eliminated. Pin↔live divergence measurement is one of the demo's jobs
   ([RECONCILIATION](RECONCILIATION.md)).
3. **FMA2's guards now see joint equity.** Its DD/HWM guards (−25% flatten-and-halt OPS-9a, −18%
   warn) computed off account equity become de facto *joint-account* guards — conservative in
   direction, and adopted here as the federation's kill layer (§Decision rules). But its **€8,000
   equity floor (OPS-6b) and `expect_band` were calibrated for a standalone €10k book** — re-base
   `expect_band` on the FMA3 pin at deploy and treat the €8k floor as a joint floor.
4. **No joint watchdog.** The FMA2 watchdog covers only its own comms files; the v7 EA has no
   watchdog at all (health/heartbeat CSVs only). Joint DD, joint margin, and realized-w are a
   **manual weekly job** until a small joint-monitor script exists (§Before real capital).
5. **The FMA2 EA stack's open hardening items carry over verbatim.** Tick-side reconciliation is
   **OPEN** — no MT5 Strategy Tester run has ever been performed for v3.4, and no live/demo tick has
   been reconciled against the brain (FMA2 `docs/v3.4/RECONCILIATION.md` §C); maker-first stays
   **OFF** (demo-gated, FMA2 `docs/v3.4/DEMO.md` §5.2); mag_xau drift capture must be calibrated on
   its **first 60 demo trades**; the §9 watchdog drills must run before go-live.
6. **NSF5's deferred hardening carries over too:** the EA-reliability pass (append+flush logging,
   restart catch-up) and VPS deployment are pre-real-capital items, not demo items (NSF5
   `docs/v7/DEMO.md`, "Before real capital").
7. **The federation has never run on real ticks.** The pin is 1m Python; the forward CONFIRM was
   Duka-feed with USA500 proxying USTEC at 14-symbol coverage — explicitly *not* the deployed book.
   The 1m↔tick crisis-tail gap is documented in
   [COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md); expect live crisis marks
   deeper than the 1m pin suggests.
8. **Two deploy artifacts must be created** (they do not exist in either repo today): the
   `InpRisk=6.16` preset file and the `GLOBAL_SCALE=3.3` brain config with its re-stamped hash.

---

## Monitoring fingerprints (against the pin + the forward run)

The demo is "healthy" if live behavior tracks these fingerprints. Judge on **execution fidelity and
behavior, not weekly P&L.** Every row is a falsifiable hypothesis with a pinned source.

| Watch | Expected fingerprint (in-sample / forward) | Red flag |
|---|---|---|
| **The first fingerprint: the forward window's actual path** | monthly **+14.94 / −0.25 / +0.41 / −2.42%**, window +12.34%, worst-mark DD 17.67%, daily Sharpe **1.17** — a front-loaded month then flat drift. The live first months should look like *this*, not like the 2.47-Sharpe pin. | a rolling 4-month return < **−10%** (the F2 breakdown bar, ≈ −0.5σ of honest expectations) |
| Monthly cadence | mean **+6.2%/mo**, monthly vol **~6.2%**, 62/72 months positive; worst month −10.7% (2022-01), best +19.9% (2025-10) (pin curve) | months persistently outside ±2σ, or a month materially below −11% |
| **Worst-mark DD envelope** | routine DD ~**16–17%** (pin max 15.73%, bootstrap median 16.80%); the forward window itself marked **17.67%** — deeper-than-pin marks are in-distribution (bootstrap p95 **23.28%**) and expected to recover | worst-mark DD > **20.9%** (the owner ceiling / F1 bar) → rule 1; close-mark −25% is the flatten-and-halt zone |
| Trade cadence | ~**1,078 trades/quarter ≈ 83/week** federation-wide (pin total; the per-stack split is not pinned — establish it from live magic attribution in week 1) | either stack silent for days, or trade counts a multiple of the joint cadence |
| Gross exposure | Σ\|frac\| p50 **4.5×E**, p95 7.2×E, p99 8.0×E, max 9.2×E (locked matrix) | sustained gross above ~9×E — live sizing exceeds the modelled book |
| Turnover | mean Σ\|Δfrac\| ~**3.1/day**, p95 5.9 | persistent turnover ≫ 6/day (churn = execution drag the pin never paid) |
| **Sub-book balance** | long-run growth share **v7 ~73.5% / v3.4 ~26.5%**; forward window natives +15.99% vs +13.59% (v3.4 sub-path +15.50/+5.06/−3.36/−3.13%) | a sub-book < **−20%** on a rolling 4-month native basis (the F4 bar), or realized w outside **0.56–0.84** (the ±20% probe envelope) |
| **Margin** | forward F3 measurements: max margin/balance **0.324** (cap 0.90), min margin level **311%** (stop-out 50%) | margin/balance > **0.60** sustained (the v3.4 de-gross zone, now on joint equity), or ML trending below ~**200%** — the survival signal, not the DD % |
| Joint overnight gold | p50 **1.21×E** / p95 1.92×E / p99 2.16×E / max **2.24×E** (H-CAPS-1 measured at s=1.0, ×1.1 for shipped scale); **0 hours** above combined entitlement in-sample | joint gold above the summed entitlement — a per-book cap not being enforced live |
| v7 stack internals | per NSF5 `docs/v7/DEMO.md`: band re-splits ~5–9/yr with `nSlots=7 / floor≈0.08`, per-sleeve mix (gold ~43% of *stack* P&L), JPY *earns* swap, EURGBP takes shorts | NSF5's red flags apply unchanged to the 70% slice |
| v3.4 stack internals | per FMA2 `docs/v3.4/DEMO.md` §3 + RUNBOOK §8: seasonal slippage ≤ **0.8 bp** (20-day rolling — their single most important demo output), fill rate ≥ **98%**, forced exits 21:05/06:05 every session, mag_xau *banks the drift* | FMA2's red flags apply unchanged to the 30% slice; any unexplained `HALT_FLATTEN` |
| **`volume_rejects` / rejects** | **0 in both stacks** (v7 health file; FMA2 fill ledger) | any nonzero → stop and diagnose (sizing/min-lot at the *smaller* sub-scales is the first suspect — the 3.3-scale slice trades smaller lots than anything FMA2 ever demoed) |

**Where the numbers live:** v7 stack — `portfolio_v7_decisions.csv`, `portfolio_v7_health.csv`,
heartbeat/state CSVs. v3.4 stack — `broker_snapshot.json`, `slippage_ledger.csv`,
`guard_events.jsonl`, `state.json`, watchdog `--status`. Joint — the account itself (equity, ML) +
magic attribution across both.

---

## Decision rules (pre-registered)

The demo is a falsification test, not a tuning loop. These rules deliberately mirror the forward
one-shot's interpretation ladder
([FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md)): each F-bar has a live analog, and each
verdict maps to CONFIRM-keep-going / INVESTIGATE / REJECT-the-scale.

1. **F1 analog — joint worst-mark DD ≥ 20.9%** (the owner ceiling): halt new entries in **both**
   stacks and INVESTIGATE — no scale-up rescue, no re-tune. If close-mark DD reaches **−25% on 2
   marks 5 min apart**, the inherited OPS-9a flatten-and-halt fires (now effectively joint — the
   FMA2 guard reads joint equity); restart requires human post-mortem + written `RESUME`.
2. **F2 analog — rolling 4-month joint return < −10%:** INVESTIGATE. The bar was pre-registered as
   the breakdown-vs-noise boundary (≈ −0.5σ under honest expectations); a negative *window* alone is
   a healthy book's possibility, a sub-−10% window is not.
3. **F3 analog — any margin-cap bind or stop-out proximity** (margin/balance toward 0.90, ML
   collapsing toward the floor, or the 60% de-gross firing repeatedly): **REJECT the locked scale —
   step s 1.1 → 1.0** by re-deriving both dials (`InpRisk 5.60`, `GLOBAL_SCALE 3.00`), preserving
   w=0.70. s=1.0 is a validated frontier point (FMA3-003: all seven composite dimensions dominate
   both parents there too). **Never step s up** — s=1.2–1.4 is the documented aggressive frontier,
   compliant at the locked w but *not probe-robust* (FMA3-RT).
4. **F4 analog — one sub-book < −20% on a rolling 4-month native basis:** investigate **that stack
   under its own parent's DEMO decision rules**; do not touch the other. If a stack (or sleeve) is
   halted, the freed capital **parks in cash — never renormalize into the survivor** (FMA2's
   governance rule, adopted federation-wide).
5. **Realized w outside [0.56, 0.84]:** do **NOT** rebalance back — H-FED-2 declined every rebalance
   cadence because cross-book rebalancing *couples the disjoint troughs it harvests*
   ([REGISTRY](../REGISTRY.md) FMA3-002). Outside the probe-tested envelope the evidence base thins:
   log it, and if the drift is DD-coincident, step s toward 1.0 per rule 3 (the ±20% probe
   constraint is the entire reason s=1.1 exists).
6. **Anything looks better than backtest:** do **not** step s up, do not push w toward the untested
   off-grid w80 (FMA3-001's grid was binding). Upside is not a mandate to add leverage.
7. **Plumbing faults — `volume_rejects` > 0, `config_hash_mismatch`, unexplained `HALT_FLATTEN`:**
   STOP and diagnose before continuing. These are execution faults, not market signals.
8. **A per-stack fingerprint breaks** (band cadence anomaly, JPY paying swap, seasonal slippage >
   0.8 bp, mag_xau missing the drift, missed forced exit…): the parent's own DEMO/RUNBOOK rules
   govern that stack — including FMA2's pre-registered fallback table and sleeve kills. **Every**
   deviation is logged to the track record so the forward evaluation never silently compares a
   degraded live book to the frozen pin.

---

## Honest caveats

- **Everything validated is in-sample (IC 2020-25), and the one shot at 2026H1 is spent.** The
  forward CONFIRM was a Duka-feed proxy book (USA500 for USTEC, 14 symbols, v3.4 at 0.88×-reduced
  breadth) — directionally strong, but *not* the deployed book. This demo and the MT5 real-tick run
  are the only falsification tests left.
- **Judge against the honest band, not the pin.** The pre-stated forward expectation is Sharpe
  **~1.2–1.5** (the forward window realized 1.17); demo success is the live path staying consistent
  with *that*, not reproducing +101.4%/2.47.
- **The v3.4 slice runs above its own standalone ceiling** (11-equivalent per sub-capital vs their
  scale-10 pre-registration). Its license is the federation pin (negQ 0/24) + the ±20% probes + the
  forward CONFIRM — watch slice-level negative quarters as a first-class signal.
- **The deployment only approximates the pinned construction.** Virtual sub-account bookkeeping vs
  two EAs sharing one equity number (§What does NOT exist yet, item 2) is a real, disclosed gap; its
  size is one of the demo's measurements, not an assumption.
- **Both parents' tail caveats carry over, rescaled.** v7's corr-spike and fat-tail×leverage risks
  scale with the dial; v3.4's MKT-3 single p95-hour joint gap (−28.1% standalone at scale 10) maps
  to ≈ **−9.3% of joint equity** at the 3.3 dial (linear-in-scale approximation) and its intraday
  gold stack remains uncapped within the slice. Diluted by federation, not removed.
- **The COVID tail 5.36% is a 1m number.** The documented 1m↔tick crisis-tail gap
  ([COMPOSITE_BENCHMARK.md](../../research/outputs/COMPOSITE_BENCHMARK.md)) means live crisis marks
  will look worse than the pin's tail suggests.

---

## Weekly monitoring

A scheduled Monday check, mirroring both parents' cadence, in three layers: **(a) joint** — realized
w from magic attribution (v7 360000-range vs v3.4 8400001–8400008 across
`broker_snapshot.json` + the v7 decision/health CSVs), joint worst-mark DD vs the envelope, ML and
margin/balance vs the F3 measurements; **(b) v7 stack** — the NSF5 Monday health read
(`portfolio_v7_health.csv`: `volume_rejects`, `final_ML`; band cadence + per-sleeve fingerprint from
the decisions log); **(c) v3.4 stack** — FMA2 RUNBOOK §7 daily/weekly checklists (slippage ledger
20-day rolling, guard false-positive tally, DST checks, watchdog liveness). Judge on execution
fidelity, **not** weekly P&L. The clock starts once both stacks are actually filling.

## Before real capital (deferred hardening — do NOT do during the demo)

Complete the parents' pre-live lists: NSF5's EA-reliability pass + VPS deployment; FMA2's §9 drills
(all six escalation paths), the maker-first activation gate (still OFF), and whatever the tick-side
reconciliation demands. Federation-specific: script the joint monitor (realized w, joint DD, joint
gold vs entitlement) instead of the manual Monday job, and decide deliberately whether a unified
FMA3 EA is worth building or whether two-stacks-plus-a-split *is* the product — that decision should
be made from demo evidence, not now.

## Definition of done for the demo

The demo forward-test is **done** when, after **≥3 months** on the shared IC Markets EU demo (the
stricter parent's bar — FMA2 `docs/v3.4/DEMO.md` §7):

- Runs cleanly throughout: `volume_rejects=0` in both stacks, zero unexplained `HALT_FLATTEN`, hash
  guards green, reconcile integrity clean, forced exits hit every session.
- The joint path stayed legal: worst-mark DD < 20.9%, no rule 1–3 fire, equity consistent with the
  honest ~1.2–1.5 Sharpe band (the forward window's 1.17 is the reference gait).
- Both stacks track their parent fingerprints: v7 band cadence ~5–9/yr with nSlots=7 and healthy
  sleeve mix; v3.4 seasonal slippage ≤ 0.8 bp, fill rate ≥ 98%, mag_xau drift-capture calibrated
  (first 60 trades) and banking — or correctly killed to cash.
- Realized w stayed inside **0.56–0.84** without intervention, and the measured pin↔live divergence
  (shared-equity coupling) is written up in [RECONCILIATION](RECONCILIATION.md).
- Every disclosed deviation is logged to the track record.

Then — and separately — the real-capital decision: a **distinct sign-off** gated additionally on
both parents' own NO-GO lists (FMA2 §5.3; NSF5's pre-live hardening), not an automatic consequence
of a clean demo.

---

*Sources: [`fma3_v1_pin.json`](../../research/outputs/fma3_v1_pin.json) ·
[`forward_oneshot.json`](../../research/outputs/forward_oneshot.json) /
[FORWARD_ONESHOT.md](../../research/outputs/FORWARD_ONESHOT.md) ·
[FORWARD_TEST.md](../../research/protocol/FORWARD_TEST.md) ·
[`hcaps1_analysis.json`](../../research/outputs/hcaps1_analysis.json) ·
[REGISTRY.md](../REGISTRY.md) FMA3-000..FWD · parent stacks: NSF5 `docs/v7/DEMO.md` +
`mt5/presets/FableMultiAsset1_V7_CORE7BAND_R8_IC.set`; FMA2 `docs/v3.4/DEMO.md`, `ea/RUNBOOK.md`,
`docs/v3.4/RECONCILIATION.md`. All numbers are in-sample (IC 2020-25); the 2026H1 one-shot is
consumed; MT5 real-tick + live demo are the remaining falsification tests.*
