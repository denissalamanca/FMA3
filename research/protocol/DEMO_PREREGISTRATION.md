# v1.1 — THE DEMO AS AN EXPERIMENT (PRE-REGISTRATION)

**CRITERIA COMMITTED 2026-07-10, before the first live bar exists.** Ledger:
**FMA3-007** (registry row to be added at deploy with account id and chosen
preset). This adopts NSF5's H12 demo-as-experiment protocol
(`NSF5 docs/v7/research/H12_DEMO_PROTOCOL.md`, incl. its Section-F skeptic
calibration) and the H12 backlog instruction ("breach-probability convention …
add to demo pre-registration", `NSF5 docs/v7/research/DISCOVERY_BACKLOG.md`)
for the FMA3 blend. It **extends** [docs/v1.0/DEMO.md](../../docs/v1.0/DEMO.md)
— deployment config, dial arithmetic, fingerprint table, weekly ritual and its
qualitative decision rules all stay authoritative and are not repeated here.
This document hardens them into pre-committed numeric evaluation bars,
kill/pause criteria, the record→tick ratio (k) calibration protocol, and the
graduation gate. **The demo is a falsification test, not a tuning loop.** Any
action it triggers is a risk action (pause, halt, step the dial DOWN along the
pre-derived fallback) — never a re-optimization. The book is frozen (config
`51a7541cc2aaa593`).

---

## 1. The hypothesis (H-DEMO-1)

**Live/demo execution of the two-stack blend reproduces the record-engine
book within the pre-stated bands below.** Specifically: (i) execution fidelity
— fills, sizing, band fires, forced exits and guard behavior reconcile to the
parents' `reconciled_with_notes` standard with **0 unexplained logic
mismatches**; (ii) performance retention — the live curve retains ≥ 85% of the
record-engine CAGR on the same window (§3 B1); (iii) risk shape — the live
curve's recomputed breach probability, sub-book fingerprints and realized-w
stay inside the bands of §3–§4.

Falsification is a real outcome with pre-registered semantics: an execution
break is a plumbing fault (fix before continuing); a retention or risk-shape
break at clean plumbing means **the backtest is what's wrong** — the answer is
the pre-derived dial step-down or a NO-GO on real capital, never a rescue.

Honest expectation, stated up front (ROADMAP v1.1): forward-honest
**~+40–70%/yr at Sharpe ~1.2–1.7** (program band 1.2–1.5 per
[FORWARD_ONESHOT.md](../outputs/FORWARD_ONESHOT.md); the 2026H1 window realized
daily Sharpe 1.17; FMA2's honest forwards ~1.4–1.7) — **NOT** the pin's
+101.4% / 2.47. The first live months should look like the forward window's
gait (+14.94 / −0.25 / +0.41 / −2.42%), not the in-sample curve.

---

## 2. Preset parameterization — the owner chooses at deploy time

The demo runs **ONE** of the two pre-registered presets
([PRESETS.md](PRESETS.md), FMA3-004/005, results pending at commit time). This
pre-registration covers **both** cases; the owner's choice is recorded at
deploy. The dial arithmetic is the DEMO.md formula, generic in s:

| Deployed dial | Formula | v1.0 reference (s=1.1) |
|---|---|---|
| Core stack `InpRisk` | 8 × 0.70 × s = **5.6·s** | 6.16 |
| Satellite stack `GLOBAL_SCALE` | 10 × 0.30 × s = **3.0·s** | 3.30 |

| Case | Account | s* source | DD ceiling for §4 | Breach baseline for §3 B2 |
|---|---|---|---|---|
| **P1** (H-RISK-1) | IC Markets EU demo, €10k convention | FMA3-004 shipped s | worst-mark **30%** | FMA3-004 shipped P(maxDD>30%) (bar ≤ 0.15) |
| **P2** (H-RISK-2) | FTMO 2-Step **Swing** modeled €100k (demo/trial account acceptable; all bands are in % of initial, capital-agnostic) | FMA3-005 shipped s | FTMO composite: daily 5%-of-initial (prev-midnight anchor, incl. floating) + static 10% floor | FMA3-005 shipped P(breach either rule in 12mo) (bar ≤ 0.05) |
| **Fallback** (if a preset's grid returns no compliant s, or the owner defers the fork) | IC Markets EU demo, €10k | v1.0 **s=1.1** (DEMO.md verbatim) | worst-mark **20.9%** (owner ceiling / F1 bar) | pin breach 0.002 vs 30%; kill line 23.0% ≈ pin bootstrap p95 23.28% ([fma3_v1_pin.json](../outputs/fma3_v1_pin.json)) |

**Deploy-time addendum (mandatory, before the clock starts).** A dated
addendum to this file records: chosen preset + shipped s* + its FMA3-004/005
artifact values; the two dial numbers from the formula; the §3 B3 bands
instantiated at s* (scaling rule in B3); the §3 B2 baseline; the §4 kill
lines; account id, Core preset-file checksum, FMA2 re-stamped deploy hash.
Instantiation is arithmetic on already-pinned artifacts — **no new engine
runs, no new numbers may be derived after live data exists.** Changing
anything in the addendum after the first live bar voids the experiment (the
clock restarts).

---

## 3. Pre-registered monthly evaluation bars (the month-end read)

Read at each calendar month-end on top of DEMO.md's Monday ritual. Universal
guards, adopted verbatim from H12-F5: **G1** — no CAGR/return- or
Sharpe-level *decision* before ≥ 2 clean quarters of real fills (earlier reads
are INVESTIGATE-logging only); **G2** — a single bad-but-in-band month is
benign by design; only the sustained patterns in §4 escalate; **G3** — no
depth-based pause at a drawdown trough: "non-recovering" requires ≥ 3 weeks
with no new equity high and the threshold still exceeded.

### B1 — Retention ratio vs the record engine

- **Definition:** retention = live window return ÷ record-engine window return
  on the **identical calendar window**, same dials, same fresh-seed convention,
  IC 1m cache (the "shadow run"). Judged on transfer/deposit-adjusted equity.
- **Cadence:** measured at each **quarter-end** (a window shorter than one
  quarter is noise per G1). Monthly reads are indicative only: live month vs
  the honest-band gait of §1.
- **The shadow run:** one record-engine pass per quarter-end over the elapsed
  demo window — measurement, not selection (FMA3-FWD precedent); logged in the
  registry as such. Runner: to be written at the first quarter-end, mirroring
  `scripts/run_forward_oneshot_native.py` against `engine/record_engine_ext.py`
  on the IC live-period 1m cache at the deployed dials — **UNRUN until the
  pre-registered engine queue (hrisk1/hrisk2/htail1) has drained**; exact
  command goes in the addendum when written.
- **Bar (pre-registered in ROADMAP v1.1):** retention **≥ 0.85** of
  record-engine CAGR.
- **Precedent and the honest unknown:** Core alone at matched R8 retained
  **~96%** of Python in the MT5 tester (Python 89.7% → MT5 86.5%,
  `NSF5 docs/v7/PERFORMANCE.md` — *observed, not guaranteed*). **The
  blend's retention is UNKNOWN** — the Satellite stack has never had a tick
  run reconciled at all (FMA2 `docs/v3.4/RECONCILIATION.md` §C OPEN), and the
  shared-equity coupling (DEMO.md "What does NOT exist yet" §2) has never been
  measured. 96% is the optimistic anchor, not the expectation.
- **Escalation:** retention < 0.85 at a quarter-end with clean plumbing →
  INVESTIGATE with a **one-quarter decision deadline** (H12-F5 pattern): either
  the shortfall is attributed to a documented benign class (feed divergence,
  spread regime, disclosed coupling — written up in
  [RECONCILIATION.md](../../docs/v1.0/RECONCILIATION.md)) or it is treated as
  reconciliation divergence under §4 K3. Retention < **0.70** at any
  quarter-end → §4 K3 clock starts immediately.

### B2 — Rolling breach recomputation on the LIVE curve

- **Convention (H12/H15, house-adopted):** stationary block bootstrap,
  **10,000 paths, 20-day mean blocks, seed 20260709**, on the live daily
  triplets (close return; worst dip vs previous close; for P2 also worst dip
  vs the midnight anchor — the H-RISK-2 convention), reported on **both
  close- and worst-mark**, with **Sharpe/CAGR percentile fans**
  (p5/p25/p50/p75/p95) logged alongside.
- **Target probability:** P1/Fallback: P[maxDD > 30%] (the owner's stomach
  limit); P2: P[breach either FTMO rule within 12 months] (the composite
  H-RISK-2 bar).
- **Cadence:** recomputed at every month-end on the live curve to date.
  **First official read at month-2** (≥ ~40 trading days); the month-1 read is
  logged as indicative (short-window bootstrap caveat, as flagged on the
  forward one-shot's 0.0002).
- **Escalation thresholds (pre-stated):** with baseline b = the same bootstrap
  on the chosen preset's pinned 2020–25 curve (recorded in the addendum;
  b ≤ 0.15 for P1, ≤ 0.05 for P2, 0.002 for the fallback):
  - **PAUSE-AND-INVESTIGATE:** official read ≥ **max(2·b, 0.10)** at **two
    consecutive month-ends** (P1: ≥ 0.30 twice; P2: ≥ 0.10 twice; fallback:
    ≥ 0.10 twice).
  - **DIAL STEP-DOWN** (the pre-derived fallback step, §5 re-pick semantics;
    never up): official read ≥ **max(4·b, 0.20)** confirmed by a one-week
    recheck (P1: ≥ 0.60; P2: ≥ 0.20; fallback: ≥ 0.20).

### B3 — Per-sub-book fingerprint bands (monthly return / vol / trade count)

Derived from the pinned curves by [scripts/derive_demo_bands.py](../../scripts/derive_demo_bands.py)
(close-basis calendar-month returns, 72 months 2020-01..2025-12; band = normal
99% [mean ± 2.576σ] widened to the realized in-sample extreme, so no pinned
month is out-of-band by construction). Sub-books are judged on the **native
basis** (magic-attributed slice P&L over its sub-capital share, the F4/DEMO.md
convention). Reference numbers at the pinned dials:

| Book (basis) | mean/mo | vol/mo | neg months | worst (month) | best (month) | **99% band** |
|---|---|---|---|---|---|---|
| Blend (w=0.70, **s=1.1**) | +6.18% | 6.15% | 10/72 | −10.69% (2022-01) | +19.91% (2025-10) | **[−10.69%, +22.02%]** |
| Core sub-book (native **R8** anchor) | +5.90% | 6.90% | 13/72 | −9.22% (2022-05) | +22.92% (2021-03) | **[−11.89%, +23.68%]** |
| Satellite sub-book (native **scale-10** pin) | +5.72% | 7.82% | 14/72 | −17.14% (2022-01) | +22.83% (2024-11) | **[−17.14%, +25.87%]** |

Forward cross-check (same script): blend +14.94 / −0.25 / +0.41 / −2.42%
(window +12.34%); Satellite sub +15.50 / +5.06 / −3.36 / −3.13% (window +13.59%) —
reproduces [FORWARD_ONESHOT.md](../outputs/FORWARD_ONESHOT.md) and DEMO.md
exactly. January 2026's +14.94% sits inside the blend band — a
front-loaded month is in-fingerprint.

- **Scaling rule (pre-committed):** the blend band scales by
  **s*/1.1**; each sub-book native band scales by **s*** (native basis: the
  sub-account view runs at R 8·s* / scale 10·s*). Linear-in-scale
  approximation, disclosed (error grows with s via vol drag — for P1 at
  s ≈ 1.6–1.7 the bands are approximations, stated as such in the addendum).
- **Return bar:** a sub-book monthly return outside its (scaled) 99% band →
  §4 P1 pause. The blend month outside its band → logged; two consecutive
  → §4 P2.
- **Vol fingerprint:** from month 4 on, trailing 6-month std (or all months if
  fewer than 6) of live monthly returns per book within **[0.4×, 2.0×]** of
  the scaled pin vol. Outside at two consecutive month-ends → §4 P2.
- **Trade-count fingerprint:** counting conventions differ across the three
  ledgers (25,869 record-engine fills ≈ 1,078/quarter blend-wide; Core
  ~468 round-trips/yr; Satellite ~2,286 model-trades/yr —
  [TRADE_CHARACTERISTICS](../../docs/v1.0/TRADE_CHARACTERISTICS.md): "conventions,
  not forecasts"; no per-stack fill split is pinned). Pre-committed
  calibration: the **first full calendar month** of live magic-attributed
  counts per stack is the baseline (recorded in the track record, per DEMO.md
  week-1 instruction); thereafter each stack's monthly count must stay within
  **[0.5×, 2.0×]** its baseline. Outside at two consecutive month-ends → §4
  P2. Counts are scale-free (s changes size, not cadence). Either stack silent
  ≥ 5 trading days when its session/signals should trade → immediate plumbing
  check (DEMO.md red-flag row), not a month-end item.

### B4 — Slippage / maker-first ledger (the v3.2 `InpMakerFirst` decision input)

- **Scope:** the Satellite stack only — `InpMakerFirst` lives in
  `FableExecutor.mq5`; the Core EA has no maker path (always taker; its spread
  cost is watched via the decisions CSV, disclosed, no flip possible).
- **Ledger spec:** per-fill rows in `slippage_ledger.csv` (FMA2 RUNBOOK §1)
  carrying timestamp, symbol, magic/sleeve, side, model price, fill price,
  half-spread at decision, spread paid, maker-eligibility flag,
  requote/reject flag. Monthly aggregation **per sleeve**: modeled maker fill
  rate within the 60-min horizon, net spread-leg saving vs taker half-spread,
  and the 20-day rolling seasonal/mag_xau slippage (bar ≤ 0.8 bp — FMA2's
  single most important demo output).
- **Flip gate (FMA2 `docs/v3.4/DEMO.md` §5.2, adopted verbatim + blend
  additions):** `InpMakerFirst` stays **OFF** until, per adopting sleeve:
  (a) maker fill rate **≥ 70%** in the 60-min horizon, (b) net spread-leg
  saving **> 0** vs taker half-spread, (c) the ≤ 0.8 bp slippage bar still
  met. Blend additions: earliest flip after **two full monthly ledger
  reads AND ≥ 60 fills in that sleeve** (the mag_xau calibration count); flips
  sleeve-by-sleeve, at most one flip batch per month, each logged as a config
  change with the re-stamped hash. **`intraday` never flips; forced exits
  always taker.** Modeled upper bound if it clears: 91.7% of spread legs;
  honest floor ~22% (v3.2 RESULT). If a flipped sleeve's realized fill rate
  drops < 70% or saving ≤ 0 on a monthly read → revert that sleeve to taker
  (FMA2 fallback table row, adopted).

### B5 — Reconciliation read

Monthly: EA↔Python reconciliation status per stack to the parents' standard —
target verdict **`reconciled_with_notes`, 0 unexplained logic mismatches**
(NSF5 precedent: 85.7% rows exact, all residuals attributed to documented
benign classes). Every mismatch gets classified within **two trading weeks**
of detection: benign-documented / plumbing-fixed / **unexplained**.
Unexplained > 2 weeks → §4 K3.

---

## 4. Kill / pause criteria (FMA2-v2.4-style: observable → threshold → action; committed now, no hindsight)

FMA2's v2.4 deployment doctrine (live risk dial + per-book pre-registered kill
criteria, F2_PREMORTEM guard pattern) applied at the blend level. Freed
capital from any pause/kill **parks in cash — never renormalize into the
survivor** (FMA2 governance rule, adopted blend-wide in DEMO.md rule 4).
Inherited hard layers stay live underneath: OPS-9a close-mark −25%
flatten-and-halt on joint equity (2 marks 5 min apart), Core `InpMarginCap=0.9`,
Satellite 60% de-gross, both parents' own DEMO/RUNBOOK sleeve rules. (P2 note: the
FTMO 10% static floor binds long before OPS-9a — the account is its own
hardest kill layer.)

### HARD KILL — halt both stacks, flatten per OPS-9a semantics, full written post-mortem; no redeploy without a new dated addendum

| ID | Observable | Threshold | Action |
|---|---|---|---|
| **K1** | Joint stop-out / margin death | broker stop-out fires, or margin level touches the 50% stop-out line, or the 90% margin cap binds in a forced-liquidation cascade (MKT-3 realized) | **KILL.** The demo has falsified the margin model — the F3 forward measurements (max margin/balance 0.324, min ML 311%) said this should never be approached. |
| **K2** | Worst-mark joint DD beyond the preset ceiling × 1.1 | P1: > **33.0%** (30 × 1.1) · Fallback: > **23.0%** (20.9 × 1.1 ≈ pin bootstrap p95 23.28%) · P2: any FTMO rule breach = account terminated (kill by construction); internal pre-breach flatten when a day consumes **80%** of the daily 5% budget or equity reaches **92%** of initial (80% of the static budget) | **KILL** (P2 internal trigger: flatten and treat as kill for the experiment verdict). Beyond ceiling×1.1 the live curve is outside anything the preset licensed — no scale-down rescue mid-fall. |
| **K3** | Reconciliation divergence unexplained | any B5 mismatch class, or a B1 retention shortfall (< 0.85 unattributed at deadline; < 0.70 immediately), still **unexplained after 2 trading weeks** of diagnosis | **KILL** (halt new entries both stacks; flatten at owner discretion). An unexplained live↔model divergence means the experiment's instrument is broken — no data it produces after that point is evidence. |

### PAUSE-AND-INVESTIGATE — halt new entries in the affected stack (or both), diagnose in writing, resume only with a dated adjudication; dials move only DOWN along §5

| ID | Observable | Threshold | Action |
|---|---|---|---|
| **P1** | Sub-book monthly return outside its 99% band (B3, scaled) | one month outside [−11.89%, +23.68%]·(s*/1.0 on native basis) for Core or [−17.14%, +25.87%]·s* for Satellite (reference at native dials; addendum instantiates) | pause **that stack's** new entries; investigate under its parent's own DEMO/H12 rules; other stack untouched; freed capital to cash. Resume on written benign adjudication; second consecutive out-of-band month after resume → treat as fingerprint drift (P2) with the stack still paused. |
| **P2** | Fingerprint drift, 2 consecutive months | any single B3 dimension (vol band, trade-count band), realized w outside **[0.56, 0.84]** (the ±20% probe envelope), or any DEMO.md fingerprint-table red flag, out of band at **two consecutive month-ends** | pause new entries (affected scope), written diagnosis. Realized-w drift: never rebalance back (H-FED-2 / FMA3-002); if DD-coincident, step the dial down per §5. |
| **P3** | Breach escalation (B2) | ≥ max(2·b, 0.10) at two consecutive official month-ends | pause + diagnose; if the step-down threshold (≥ max(4·b, 0.20), one-week recheck) is also hit → execute the §5 dial step-down. |
| **P4** | Retention shortfall (B1) | < 0.85 at a quarter-end, plumbing clean | INVESTIGATE with one-quarter decision deadline → benign attribution in RECONCILIATION.md, or K3. |

### Explicitly NOT a pause/kill (pre-classified — do not rationalize into failure or panic after the fact)

- A losing month inside its band; a losing quarter on the Satellite slice (an
  explicit DEMO.md watch item — it runs above its standalone ceiling under the
  blend's license); a vol-upshock day or cluster (NSF5 FM-1: expected
  ~1-in-12 days, by design).
- Joint DD inside the preset ceiling — including deeper-than-pin marks
  (fallback: bootstrap p95 23.28% is in-distribution; the forward window
  itself marked 17.67%).
- Rebalance-date/schedule mismatch vs any backtest (FM-8 chaos; judge band
  fires on the four H12 criteria, not dates).
- The month-1 bootstrap read (indicative only), and single-month fingerprint
  wobbles (G2).
- Anything looking **better** than backtest — not a mandate: never step s up,
  never push w (DEMO.md rule 6).

---

## 5. The MT5-ratio (k) calibration protocol — PRESETS.md pre-commitment made concrete

**The pre-commitment being executed** (PRESETS.md standing caveat): both
preset dials are provisional pending the measured record→tick DD ratio; the
final dial re-picks so that record-DD × k respects each account's true limit.
Precedent for why: Core's COVID tail measured **35.6%** on MT5 real-tick vs
**~5.5–7.2%** in 1m record worst-mark (k_tail ≈ 5–6.5,
[COMPOSITE_BENCHMARK.md](../outputs/COMPOSITE_BENCHMARK.md)) while routine DD
and CAGR translate far more faithfully (~96% retention at R8). Crisis
microstructure is the one risk the record engine cannot see.

**Measurement (pre-committed):**

1. **Source runs:** the MT5 Strategy Tester real-tick run(s) of the blend
   on the owner's machine over **2020–25** at the deployed dials — the Core EA
   directly; the Satellite stack via its first-ever tester/tick reconciliation
   (FMA2 §C OPEN — if the Satellite tester harness is not ready at deploy, k is
   measured first on the Core stack + the live demo curve, and the blend k
   is completed when the Satellite tick run exists; the interim asymmetry is
   disclosed in the addendum). These runs are on the owner's machine, not this
   repo's engine queue; **no new record-engine passes are needed** — the
   record side of every ratio is already pinned (fma3_v1_pin, hfed3/hrisk
   grids).
2. **Two ratios, kept separate:**
   **k_dd** = tick worst-mark maxDD ÷ record worst-mark maxDD (same window,
   same dial); **k_tail** = tick crisis-tail (2020 COVID window relative
   floating DD) ÷ record crisis-tail. Reported per stack and joint. The demo's
   own live window supplies a third, forward-looking consistency check (its
   realized worst-mark vs the shadow run's), not the primary k (too short, no
   guaranteed crisis).
3. **The re-pick rule (concrete):** the final dial is the **largest s on the
   chosen preset's already-registered grid** (P1: {1.5…1.8} + the pinned
   ≤ 1.4 points; P2: {0.4…0.8}; no new grid, no off-grid picks) such that,
   using the preset's own pinned record numbers per s:
   - P1/Fallback: record-worst-DD(s) × k_dd ≤ 30% **and** record-tail(s) ×
     k_tail ≤ 30% (fallback: ≤ 20.9% with k_dd only, its registered
     ceilings);
   - P2: the H-RISK-2 composite bootstrap re-run with the daily dip legs of
     each triplet **multiplied by k_dd** (tail legs by k_tail where the crisis
     window is in-block) must still clear **P ≤ 0.05**, and the k-inflated
     historical path shows 0 breaches.
4. **Asymmetry (pre-committed):** k can only cut the dial, never raise it —
   a measured k < 1 does **not** license s above the preset's shipped point
   (consistent with "never step s up", DEMO.md rule 3/6). If the re-pick
   lands below the deployed s, the dials step down mid-demo via the formula
   (5.6·s / 3.0·s) and **the graduation clock restarts** at the new dial (the
   experiment continues; the window before the step is reported but does not
   count toward §6).
5. **Timing:** k is measured **before real capital**, target before or in the
   first month of the demo. The k values, the re-picked s, and the arithmetic
   go in a dated addendum.

---

## 6. Duration + graduation (pre-stated)

**Clock:** starts when **both stacks are actually filling** (DEMO.md). Short
EA restarts do not reset it; a dial step (§5) or any addendum change resets
the graduation clock (not the ledger).

**Duration:** minimum **3 clean months** = the operational "demo done" read
(the stricter parent's bar, FMA2 `docs/v3.4/DEMO.md` §7, as adopted in
DEMO.md's definition of done). Graduation to real capital requires **≥ 2 clean
quarters (~6 months)** of real fills (H12(E) minimum; G1 makes any
CAGR/Sharpe-level verdict earlier than that unsound), **target 4 quarters** —
long enough to span at least one Core band-cadence cycle and, ideally, one vol
spike.

**Graduation gate — graded, H12-F6 style (making money is NOT success;
the presets' leverage can print a positive number over a decayed book):**

- **FULL PASS → the real-capital decision opens at the deployed preset size.**
  ALL of: no K-trigger; ≥ 2 clean quarters (`volume_rejects=0` both stacks,
  zero unexplained `HALT_FLATTEN`, hash guards green, forced exits every
  session); retention ≥ 0.85 at every quarter-end read; every official B2 read
  below the pause threshold; live Sharpe (≥126d) ≥ 1.0 and consistent with
  the honest 1.2–1.7 band by trend; B3 fingerprints in band; realized w inside
  [0.56, 0.84] without intervention; k measured and the deployed s compliant
  under §5.3; every P-item adjudicated benign in writing; maker-first ledger
  delivered (flip decision made, either way); RECONCILIATION.md updated with
  the measured pin↔live divergence.
- **CONDITIONAL PASS → real capital only at a reduced dial** (one preset grid
  step down, or the v1.0 s=1.1 fallback dial) **and/or extend the demo one
  quarter.** Survived with clean plumbing but delivered only the lower band
  (retention 0.70–0.85 benign-attributed, or Sharpe 0.8–1.0, or fingerprints
  repeatedly at band edges).
- **NOT CONFIRMED → no real capital.** Any K-trigger; or persistent Sharpe
  < 0.8 / retention < 0.70 across the window; or unadjudicated P-items at
  window end. Post-mortem against this frozen document.

**The real-capital decision is a distinct sign-off even on FULL PASS** —
additionally gated on both parents' pre-live lists (NSF5 EA_RELIABILITY P1/P2
hardening + VPS; FMA2 §9 watchdog drills, all six escalation paths; the four
owed guard fixes OPS-3b/OPS-6a/OPS-8/MKT-7 + the v2.1 `n_ticks` liquidity
guard) and the FMA2 §5.3 NO-GO list. A clean demo is necessary, never
sufficient.

---

## 7. Scope guards / anti-rescue

No book change from anything the demo shows (weights, sleeves, w, blend
mechanics — frozen). No upward dial move on any evidence. No re-registration
of bands after live data exists (the addendum instantiates, before the clock).
No renormalization of freed capital, ever. No third preset invented mid-demo.
If the demo falsifies, the result is a NO-GO and a post-mortem — the parents'
base rate says most levers die; a demo that catches a break before real
capital **is the experiment succeeding.**

---

*CRITERIA COMMITTED 2026-07-10 (Europe/Madrid), before any live bar and before
the FMA3-004/005 preset results existed. Sources of every number:
[fma3_v1_pin.json](../outputs/fma3_v1_pin.json) ·
[fma3_v1_pin_curve.parquet](../outputs/fma3_v1_pin_curve.parquet) /
[v7_book_equity_1m.parquet](../outputs/v7_book_equity_1m.parquet) /
`research/baselines/fma2/v34_s10_pin_curve.parquet` via
[scripts/derive_demo_bands.py](../../scripts/derive_demo_bands.py) ·
[FORWARD_ONESHOT.md](../outputs/FORWARD_ONESHOT.md) + forward curve parquets ·
[PRESETS.md](PRESETS.md) (FMA3-004/005) ·
[COMPOSITE_BENCHMARK.md](../outputs/COMPOSITE_BENCHMARK.md) ·
[docs/v1.0/DEMO.md](../../docs/v1.0/DEMO.md) · NSF5
`docs/v7/research/H12_DEMO_PROTOCOL.md` + `DISCOVERY_BACKLOG.md` +
`docs/v7/PERFORMANCE.md` (~96% retention) · FMA2 `docs/v2.0/F2_PREMORTEM.md`
(v2.4-style guard pattern), `docs/v3.2/RESULT.md` + `docs/v3.4/DEMO.md` §5.2
(maker-first gate), `ea/RUNBOOK.md` (OPS-9a/OPS-6b).*
