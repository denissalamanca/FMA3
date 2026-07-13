# FMA3 Roadmap — v1.1 → v1.x

*Committed 2026-07-10, after the v1.0 lock (config `51a7541cc2aaa593`) and the
2026H1 CONFIRM. One lever per version (house rule). Every lever below is
pre-registrable against fresh bars; nothing on either parent's kill list or
FMA3's own declined ledger appears here. Expected values are stated with the
program's honest base rate in mind: across both parents, roughly 1 in 4–6
pre-registered levers survives its bars.*

---

## The organizing insight from v1.0

The red-team adjudication (FMA3-RT) re-picked the shipped scale from s=1.4 to
s=1.1 because the **w+20% probe DD (17.97% native) binds the owner's 20.9%
ceiling** — a **39.4pp CAGR forfeit** (140.8% → 101.4%) paid for robustness to
w drift (quarter-horizon drift 0.63–0.75 measured in the hfed2 F2a event log —
the share just before each quarterly re-split; the shipped static book is never
rebalanced, so its multi-year drift can be wider — that is what the ±20%
probes bound). The probe-robust
rule is mechanical: **any lever that flattens the w-sensitivity of worst-mark
DD converts directly into shippable CAGR.** That is where the value is; most
of this roadmap is ways to buy the forfeit back honestly.

Second insight: the record-engine crisis tail (5.4%) and the MT5 real-tick
tail (v7.0 alone: 35.6%) are different animals. The record engine cannot see
tick-level crisis microstructure — **the MT5 run is not a formality; it is
where the federation's real tail is measured for the first time.**

---

## Preset fork (immediate, in flight) — v1.0-p1 / v1.0-p2 (H-RISK-1/2)

**Owner risk revision 2026-07-10** ("I can stomach 30% DD; flex the breach"),
pre-registered in [research/protocol/PRESETS.md](research/protocol/PRESETS.md)
(FMA3-004/005). The BOOK is unchanged — only the risk dial forks into two
deployment presets:

| Preset | Account | Ceilings (record engine, incl. ±20% w probes) | Expected landing |
|---|---|---|---|
| **v1.0-p1** | Private IC Markets EU | DD<30% · tail≤30% · negY 0 · negQ≤1 · **breach P(DD>30%) ≤ 0.15** | s≈1.6–1.7, CAGR ~160–180% (breach likely binds) |
| **v1.0-p2** | FTMO 2-Step **Swing** (€100k modeled; Swing mandatory — weekend gold/crypto + news) | **P(breach either FTMO rule in 12mo) ≤ 0.05** (daily 5%-of-initial rule expected to bind, not the static 10% floor) · 0 historical breaches · negY 0 · negQ≤1 | s≈0.5–0.6, CAGR ~40–60% record, forward-honest ~25–40%/yr |

Both dials are **provisional pending v1.1's MT5 record→tick DD ratio** —
pre-committed: the final dial re-picks so record-DD × measured-ratio respects
each account's true limit. FTMO rules verified against ftmo.com 2026-07-10
(2-Step: 5% daily from prev-midnight anchor incl. floating; 10% static floor;
1-Step's trailing 10% avoided deliberately).

---

## H-FTMO-1 — FTMO daily circuit breaker (owner priority: tonight)

**Owner intuition (2026-07-10):** the FTMO preset's binding constraint is the
daily >5% dip rule. A pre-set intraday stop — flatten the whole book when the
day's dip touches x% (x < 5) and stay flat until the next server day — caps
the daily-rule breach by construction and should unlock a larger s.

| Item | Detail |
|---|---|
| Lever | FTMO-preset-ONLY execution guard: intraday equity floor at day-anchor −x%, x ∈ pre-registered grid {3.0, 3.5, 4.0}%; on touch, flatten all positions, resume next server day. Never applied to the IC book. |
| Not a re-litigation | The parents' throttle graveyard (6 overlays, −2 to −31pp, "cut at the trough") killed *return-improving* throttles. This is a **compliance guard vs an external hard rule** — the objective is P(account death) ≤ 0.05 at max CAGR, not raw book quality. Cite the graveyard; scope the intent. |
| Engineering | The record engine has no intraday conditional flattening — extend `record_engine_ext` (daily-stop hook, verified bit-identical at x=∞ against the no-stop engine before use). This is the real cost of the lever. |
| Honest physics (pre-stated) | (a) **Gap risk**: a 1m bar can jump through x straight past 5% — the stop truncates, not eliminates, the breach tail; measure the residual. (b) **Re-entry cost**: flatten+reopen pays the full book's spreads each trigger. (c) **Crystallization**: stopped days convert intraday dips into realized losses. (d) **The static 10% %DD floor becomes the next binding constraint** — it already bites at s≈0.7 (DD 10.3%); the breaker lifts the daily rule but only partially relieves maxDD, so the realistic unlock is s≈0.55–0.70 (CAGR ~45–60%), not unbounded. |
| Bars (to pre-register before running) | P(breach either FTMO rule in 12mo) ≤ 0.05 incl. gap-through residual · 0 historical breaches · both ±20% w probes (full walk-down, per the FMA3-005c standing amendment) · CAGR at the shipped s must beat the no-breaker FTMO ship by ≥ +8pp (else the breaker's complexity isn't paid for). |
| Sequencing | Tonight, after H-TAIL-1 completes (engine queue). Ledger: FMA3-008 when pre-registered. |

**EA split decision (owner, 2026-07-10): the two presets deploy as SEPARATE
EA configurations, optimized separately — IC has priority.**

- **EA-IC (priority):** the parents' stock EAs exactly as validated
  (PortfolioV7.mq5 + the FMA2 stack), preset via config/.set only. ZERO new
  EA code — preserves the v7 EA's reconciliation + reliability audit status.
  The IC demo proceeds on this immediately and is blocked by nothing
  FTMO-related.
- **EA-FTMO:** the same stock EAs byte-identical, plus a separate **guardian
  EA** implementing the H-FTMO-1 circuit breaker (day-anchor equity watch →
  flatten all magics at −x% → halt flag until next server day). The ONLY
  shared touch is a dormant ~5-line halt-flag check in each stack (inert
  unless the flag exists; never set on IC accounts). Full-fork alternative
  rejected: doubles maintenance forever for zero IC benefit.
- The guardian is built ONLY if H-FTMO-1's backtest bars pass — no EA
  engineering for a lever that may DECLINE.
- Consequence for v1.1: the demo pre-registration's per-preset
  parameterization becomes two separate deploy-time addenda (IC first);
  retention battery for IC, compliance battery for FTMO.

---

## v1.1 — MT5 reconciliation & demo (deployment version; no book change)

**The owed arbiter.** Everything else on this roadmap is gated behind it.

| Item | Detail |
|---|---|
| Lever | None (book frozen). Operational version. |
| Work | (a) MT5 real-tick run of the federation on the owner's machine: PortfolioV7.mq5 @ 70% sub-allocation + the FMA2 EA stack @ 30%, magic-separated, one demo account, s=1.1 dial arithmetic per docs/v1.0/DEMO.md. (b) Finish the FMA2 EA stack (Python-brain + MQL5-executor, in progress — the *actual* deployment blocker). (c) The four FMA2 guard fixes owed (OPS-3b, OPS-6a, OPS-8, MKT-7) plus the v2.1 `n_ticks` liquidity guard for live ops. (d) NSF5 EA_RELIABILITY P1/P2 hardening before real capital. (e) Run the demo AS an experiment per NSF5's H12 protocol (DISCOVERY_BACKLOG): pre-register the demo with the 20d-block bootstrap breach convention (P[maxDD>30%], both close- and worst-mark, Sharpe/CAGR percentile fans) plus FMA2-v2.4-style per-book live kill criteria. |
| Measures | The federation's first real-tick numbers: retention ratio vs the record engine (v7 alone was ~96% at R8 — the federation's is UNKNOWN), the real crisis-tail proxy, EA↔Python reconciliation to the parents' standard (`reconciled_with_notes` bar). |
| Gates (pre-register before the run) | Retention ≥ 85% of record-engine CAGR; no unexplained logic mismatches; demo monthly fingerprints within the pin envelope (docs/v1.0/DEMO.md table). |
| Expected value | Enables everything; measures the one risk the record engine cannot. Forward-honest expectation on demo: ~+40–70%/yr at a Sharpe ~1.2–1.7 band — anchored to the program's own pre-stated honest-discount band (1.2–1.5, FORWARD_ONESHOT; the 2026H1 window measured daily Sharpe 1.17) and the parents' honest forwards (FMA2 ~1.4–1.7) — NOT 101%, pre-stated so nobody panics. |
| Cost / risk | Owner's machine + EA engineering. No data consumed. |

**Also in v1.1 (free, demo-gated):** the maker-first ledger. FMA2's v3.2
ACCEPT shipped `InpMakerFirst=off` pending a demo slippage ledger (realized
fill ≥ 70% + saving > 0 per sleeve). The demo produces that ledger for free;
if it clears, the flip is config-only spread savings (modeled upper bound
91.7% of spread legs, honest floor ~22%).

---

## v1.2 — H-TAIL-1: crisis reinforcement from the cash-park (the forfeit lever)

**Highest-value book lever available.** The conditional hypothesis registered
in v1.0 (HYPOTHESES.md H-TAIL-1) never triggered because H-FED-1 passed its
DD bar. The probe-binding evidence re-justifies it with a sharper target.

| Item | Detail |
|---|---|
| Lever | v3.4 sub-book crisis sleeve weight × {1.5, 2.0}, funded from the 0.174 cash-park (v3.4's own freed-weight mechanism; total v3.4 gross unchanged; sleeve internals untouched). One evaluation. |
| Not a re-litigation | NSF5's H15/V8 kill was crisis as a seat on the BAND book, where "the DD-channel that carried the quarterly +5.57pp does not exist" (V8_RELEVER_POLICY §1) — the band already supplies it. This lever re-weights crisis INSIDE v3.4's fixed-fraction book, where crisis is a native shipped seat and pays in stress (H14 confirmed crisis pays on non-band cadence; FMA2's own COVID/2022 record). Per the parents' cadence-conditionality ruling, the band-book verdict does not transfer; no H14/H15 stream is re-imported. |
| Mechanism | The w+20% probe DD is dominated by the v7 book's own drawdown structure at high w. A stronger stress-payer in the v3.4 residual directly cushions exactly those hours — flattening dDD/dw where it binds. |
| Bars (pre-register) | w_up20 probe DD improves ≥ 1.5pp at ≤ 0.5pp CAGR cost at native scale; all H-FED-1 bars still pass at w=0.70; then re-run the probe-robust scale rule — adopt only if the shippable point improves ≥ +8pp CAGR at unchanged ceilings. DECLINE on any miss. |
| Expected value | If the probe DD falls 17.97 → ~16.3%, the linear probe-robust scale limit is 20.9/16.3 ≈ 1.28. On the registered 0.1-step grid the re-pick lands at **s=1.2 ⇒ ≈ +13pp shippable CAGR** (hfed3 slope is ~+13pp per 0.1s: 101.4 → 114.4). Reaching ~+19pp requires pre-registering a finer scale step (e.g. s=1.25; linear-scaled probe 20.4% < 20.9%) in the v1.2 protocol — decide the grid BEFORE the run. Probability of adoption: low-to-moderate (program base rate ~1 in 4–6) — crisis is a proven stress-payer in this structure, but weight increases have failed elsewhere, and honesty note: crisis's F3 conviction cap was set downward on durability evidence (2015–19 Sharpe −0.10, thesis-consistent no-crisis window); this lever leans against that prior. |
| Cost / risk | ~4 engine runs on mined 2020–25 data (ledger +4). No holdout touched. |

---

## v1.3 — (w, s) joint re-pick on the plateau (composed rule, tiny grid)

| Item | Detail |
|---|---|
| Lever | New pre-registered grid **straddling the shipped point**, w ∈ {0.66, 0.72, 0.75}, with the **probe-robust (w, s) pair picked jointly** by the FMA3-RT rule — scale is still last, but the rule is applied per-w so the pick optimizes the shippable point, not the native one. |
| Prior evidence | Sharpe rose into the v1.0 grid edge (w60 2.458 → w70 2.474) but the w=0.84 probe measured 2.416 — so the measured points only bracket the peak in **(0.60, 0.84)**, and a quadratic through the three points puts it near **w ≈ 0.68, i.e. possibly at or below the shipped 0.70** (hence the straddling grid, not an upward-only one). Worst-mark DD is locally minimized near w70 (w56: 15.4%, w70: 14.4%, w84: 18.0%) and the probe-robust scale falls as probe DD rises: the shippable optimum may not move at all. |
| Bars | Adopt only if the shippable point beats v1.0's (or v1.2's) by > +3pp CAGR at all ceilings incl. probes; ties reject. |
| Expected value | Modest: +0–5pp. Honest note: this is refinement, not discovery — run it after v1.2, at whichever base config stands. |
| Cost | ~9 engine runs (3 w points × {native, ±20% probes}; ledger +9). |

---

## v1.4 — 2015–2019 edge-persistence study (robustness, not performance)

| Item | Detail |
|---|---|
| Lever | None adopted from this — it is a **falsification attempt** on the federation's structural premise (disjoint troughs, ρ≈0.35), currently evidenced only on 2020–25 + 4 forward months. |
| Work | Research-grade (assigned spreads, NOT worst-mark): the full FMA2 book + the 10-instrument v7 subset on `bars_1m_ext` / `research_cache_ext`, federation bookkeeping on top; measure ρ, co-trough structure, and the fed-vs-parents DD relation on 2015–19. |
| Known blocker | NSF5's extended-history reconciliation is **PAUSED mid-diagnosis** (anchor 71%/44% vs real 108%/19% — the hybrid pre-2020 feed does not reconcile). Scope to what provably reconciles; report coverage honestly. |
| Outcome semantics (pre-commit) | Confirmation → a robustness paragraph in the whitepaper. Refutation (ρ ≥ 0.6 or co-troughs pre-2020) → an honest downgrade of the federation's forward expectation and a scale review. Either result is valuable; neither changes 2020–25 numbers. |
| Cost | Data prep + research runs; 2015–19 was already consumed for training-eligibility by FMA2's protocol, so no fresh-data ethics issue — but log it. |

---

## v1.5 — Capital-ladder unlocks (as the account compounds)

Mechanical thresholds from the parents' capital-ladder studies — each becomes
a one-lever version when equity crosses its gate:

| Equity gate | Unlock | Measured prior |
|---|---|---|
| €14–16k | Sleeve completion (min-lot quantization stops truncating the smallest seats) | ~+0.33pp genuinely capital-gated (NSF5 V8_CAPITAL_LADDER) |
| €33–90k | Overlay fidelity shape (finer sub-allocations become feasible) | shape improvement, not CAGR |
| ~€50k | Re-evaluate XSEC-FX at scale — **with eyes open**: measured standalone Sharpe 0.44 at €50k and a capacity-ladder dilution finding; the honest prior is DECLINE again | low |

---

## Research track (parallel, gated — not version-numbered until unblocked)

| Candidate | Gate | Why it is still alive | Honest prior |
|---|---|---|---|
| **Options-convexity tail overlay** (G-CONVEXITY-OPTIONS) | Options data acquisition (CBOE VX dataset banked; needs option chains) | The ONLY tail-insurance structure not killed by either program (futures VIX hedge: killed; tranche/option payoffs went to backlog explicitly). Matters for the **MT5-tick tail**, which the record engine cannot see — pairs naturally with v1.1's first real-tick tail measurement. | Unknown; the parents' insurance graveyard is large. Evaluate only with real quotes, never modeled vol. |
| **Energy-tsmom thesis** | Live 2026H2+ data (accumulating now) or pre-2020 energy data | Parked-not-falsified in NSF5 V7.6 (thesis intact; 2020 mirage killed the specific cells) | Low-moderate |
| **Upstream parent evolution — NSF5** (G-CRYPTO-FUNDING, G-MOC-IMBALANCE, G-OVERLAY-C1 pre-FOMC drift) | NSF5-side V8 work by the owner's program, each with its own specified retest condition | If NSF5 ever ships an improved band book, FMA3 re-pins via a NEW import evaluation (fresh pre-registration; the v1.0 federation formula accepts any frozen v7-successor artifact) | Per NSF5 backlog priors |
| **Upstream parent evolution — FMA2 v2.2 11y re-derivation** (nested-WF weight refit on 2015–2025; the explicitly RESERVED pre-registered one-shot vol-targeting/dynamic-scale retest, now with 4+ vol regimes; chop-sleeve clean-OOS retest of xsec_reversion/reversion_intraday; gold-beta cap study; crypto_smart on 11y) + the F1 design spike (novel alpha targeting chop/negative-carry/low-gold-corr gaps) + session_flow leg-A clean-holdout | FMA2-side work; pairs naturally with v1.4's extended-history prep (same `research_cache_ext` data) | These are FMA2's reserved open items (FMA2 ROADMAP v2.2/F1), not FMA3 levers — if FMA2 ships an improved v3.x, FMA3 re-pins via a NEW federation evaluation, same as the NSF5 row | Per FMA2 roadmap; vol-targeting carries the both-programs invert prior against it |
| **Seasonal dual-feed re-derivation** | None — "free to run now" per FMA2's ledger | Feed-sensitivity hardening of the largest v3.4 seat (Duka 1.07→0.40 flagged in H15) | Robustness, not CAGR |
| **Unified FMA3 EA** | After v1.1 proves the two-EA federation on demo | Removes the two-stack operational risk; single magic-space, single dial | Engineering only |
| **G-DUALFEED** (2nd feed for IC-only sleeves) | Before real size | Feed-quality risk on USTEC/index seats | Risk reduction |

---

## Explicitly NOT on this roadmap (the inherited graveyard, do not re-litigate)

DD-throttles / vol-targeting / regime switching at the federation or book
level (inverts, both programs — with one honest carve-out: FMA2 explicitly
RESERVED a pre-registered 11y one-shot vol-targeting retest as its own v2.2
item; that retest lives upstream in FMA2, tracked in the research track above,
and is not an FMA3 lever) · weight optimization beyond tiny pre-registered grids (1/N doctrine
+ allocator study) · cross-book rebalancing in any tested cadence (FMA3-002:
couples the disjoint troughs) · tight federation bands (degenerate at w70) ·
re-tuning any frozen sleeve internal · third passes on the H8/H14/H15 import
channels · 24/24 positive quarters (LP-infeasible) · gold share ≤ 33%
(infeasible floor ~38–40%) · silver / energy-carrier / VIX-futures seats
(killed with cause).

---

## Sequencing and the honest arc

```
v1.1 MT5 + demo  ──────►  the real-tick tail + retention numbers exist
      │
      ├─► maker-first flip (if the demo ledger clears — free bps)
      │
v1.2 H-TAIL-1 (crisis × cash-park)  ──►  probe-robust scale re-pick
      │                                   (target: ≈+13pp of the 39.4pp forfeit on
      │                                    the 0.1-step grid; ~+19pp only with a
      │                                    pre-registered finer scale step)
v1.3 (w,s) joint plateau refinement ──►  +0–5pp, ties reject
      │
v1.4 2015–19 falsification attempt ──►  robustness paragraph OR honest downgrade
      │
v1.5+ capital-ladder unlocks as equity compounds · research track as gates open
```

The program's discipline is unchanged: pre-registration before numbers, one
lever per version, DECLINE by default, every experiment on the ledger, the
demo/live data as the only true OOS. **v1.0 needs nothing from this roadmap
to be deployable — every item above is upside or robustness, not a repair.**
