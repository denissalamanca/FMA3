# Model-vs-MT5 Reconciliation — acceptance criterion (PRE-REGISTRATION)

**CRITERIA COMMITTED 2026-07-11, before any G3b RUN 2 number (real-tick or
clean deals) exists.** This hardens the first-draft 3-gate proposal against
three adversarial critiques (gaming / statistics / decision-usefulness). Ledger:
FMA3-RECON-1. Engine of record per PROTOCOL.md §1 = Python 1-minute worst-mark;
this document does not change that — it defines when an MT5 real-tick run is
allowed to *corroborate* the record engine and set the deployment dial, and when
it must *demote* it.

> **Validation note (FMA3-RECON-1 dry-run, 2026-07-11).** This criterion was
> exercised as a **negative control** on the known-bad G3 run and correctly
> returned **UNRELIABLE / NOT-DEPLOYABLE for the right reasons**, with
> discrimination confirmed (a clean 2024-25 sub-window reconciled at `k≈1`; no
> false pass). The dry-run also exposed one hole — the pre-registered Gate-2
> primary window and all three Gate-3 slices sit **entirely inside the clean,
> margin-unstressed era**, so those two gates *near-pass* the contaminated run
> and the rejection is load-bearing only on Gates 4/5/6. The five fixes below
> close that "measured only where homogeneity is guaranteed" hole; no
> [OWNER TO RATIFY] parameter, frozen-hash/symbols/slices placeholder, or the
> six-gate structure is changed.

> **Naming (binding).** The passing state is **RECONCILED**, never "VALIDATED".
> RECONCILED = the record engine and the MT5 tick engine execute the *same
> frozen model* on the *same data* faithfully (engine fidelity). It is
> structurally **incapable** of detecting overfitting and says nothing about
> out-of-sample generalization — that stays with the never-fitted 2026 holdout
> (FORWARD_TEST.md) as a separate, mandatory gate. RECONCILED binds to a single
> frozen model hash (see the standing clause).

---

## Principle

"Trustworthy" ≠ decimal match. A run RECONCILES if the MT5 result lands inside a
**pre-declared envelope** of (model + friction measured on the clean deals sheet
+ a *quantified* tick allowance) **and** the record→tick drawdown multiplier `k`
is **stable with adequate power** across independent sub-periods **and** the
model survives the two regimes where the engines are *known* to diverge (margin/
leverage under compounding; crisis tails). Two anti-gaming rails:

1. **Friction is objective, not fitted.** The add-back is the *exact*
   swap+commission from the clean G3b RUN 2 deals sheet. Spread stays
   un-credited (embedded in fills) ⇒ the return side is *conservative by
   construction*: `MT5+friction ≤ frictionless model`, so `R ≤ 1` is the
   expected physics and `R > 1.05` is an **anomaly to investigate, not a pass**.
2. **Explicit FAIL and INCONCLUSIVE paths.** Underpowered agreement is not
   agreement: if a gate's bootstrap CI straddles its threshold the verdict is
   **INCONCLUSIVE**, and the loss-asymmetry rule (a false-RECONCILE that deploys
   a mis-calibrated dial is far costlier than a false-fail that keeps MT5 as
   record) resolves INCONCLUSIVE → **demote to MT5 / do not freeze**.

---

## Scope

- **Two protocols, run together, both pre-registered here.**
  - **LAB reconciliation (Gates 1–4):** G3b **FIXED-BASE** (`InpSizingBase=10000`,
    `FED_IC_G3B.set`) vs a **matching fixed-base record curve** (rate / DD% terms,
    not the compounding curve). Fixed-base strips volume-cap / margin /
    leverage-pyramiding — so it is a clean *engine-fidelity* bench and nothing
    more. **A LAB pass certifies the lab run only; it does NOT authorize
    deployment.**
  - **DEPLOYMENT reconciliation (Gates 5–6):** a **COMPOUNDING** run at the
    *candidate dial* (IC s≈0.6–0.8; FTMO s≈0.7 + breaker) where the margin/
    leverage channel re-activates, plus the crisis windows. **Each preset is
    reconciled on its OWN run against its OWN per-preset thresholds** (see the
    Owner-ratify table). This is where deployment safety is actually decided. **Gates 5 and 6 are MANDATORY and
    NON-WAIVABLE** — the stress / crisis / margin discrimination is carried by
    them by design, and **no LAB-gate (1–4) pass may substitute**.
- **Windows.** Primary (gating) = REAL TICKS 2023-07…2025-12 (~30 monthly obs).
  Secondary = 2020…2023-06 (generated ticks; the memory records these smooth
  stop-out wicks ⇒ 2020-22 depths are *optimistic bounds*) — reported, looser,
  and **only** the crisis sub-windows (Gate 5) are gating there.
- **Frozen artifact.** The model under test is pinned by config hash before
  RUN 2 (`RECON_MODEL_HASH = 51a7541cc2aaa593`, **RATIFIED 2026-07-11**). Any
  change re-opens all gates (standing clause).

---

## The hardened gates

Statistics common to all gates: **block bootstrap, 3-month blocks** (covers the
autocorrelation horizon), report **effective N** alongside raw N, and report the
number of *independent drawdown episodes* underlying every `k`. A `k` built on
1–2 episodes is labelled low-power and is diagnostic, not gating.

### Gate 1 — RETURN FIDELITY (net-honest, identifiable)
- **Friction re-measured on the CLEAN G3b RUN 2 deals sheet.** The contaminated
  G3 figure (−€589,259 ≈ 12.3% of gross) is **never** imported; its swap/
  commission composition differs once margin/leverage pyramiding is removed.
- `R_gross = (MT5 net rate + clean friction add-back) / model rate`.
  **PASS band (asymmetric to the spread physics): `R_gross ∈ [0.90, 1.05]`.**
  `R_gross > 1.05` ⇒ **INVESTIGATE** (MT5 beating a frictionless model is a
  modelling error, not a pass).
- `R_net = MT5 net rate / model rate`. **The WINDOWED `R_net` (per-slice /
  per-window) is the PRIMARY return statistic — NOT the full-sample figure.**
  Deployment is gated separately on the **net-CAGR floor** (friction-haircut rule
  below), not on `R_gross`; crediting friction back can never launder a net
  shortfall.
  - **Warning (binding).** A full-sample `R_net ≈ 1` can be a **CANCELLATION of
    two large opposite-signed errors** — a crisis / dead-start hole times a
    leverage overshoot (measured on G3 as **0.478 × 1.785 × 1.332 = 1.08**) — and
    **must never be read as fidelity**. The windowed statistic exposes the offset
    the full-sample product hides.
- **Identifiability guard (kills offsetting-error false passes):** require the
  residual `|model_rate − MT5_net − clean_friction| ≤ tick_allowance_return`.
  The add-back is **capped at the exact deals-sheet value** — no fitted top-up.
  **A NEGATIVE identifiability residual (`MT5 net rate > the frictionless model
  rate`) is a modelling / regime error that friction CANNOT rescue and triggers
  INVESTIGATE regardless of the `R` band** — the MT5 engine cannot honestly beat
  a frictionless model.
- **Tick allowance (quantified, not elastic):** `tick_allowance_return =`
  **±3% of rate (RATIFIED 2026-07-11; shared — see the Owner-ratify table)**,
  applied **only** to the secondary/generated-tick window; the real-tick primary
  window carries a **tight ±1%** allowance. This removes the "it's within tick
  allowance" escape.
- **Precision:** paired block-bootstrap 90% CI on `R_gross`; if width > **0.15**
  → INCONCLUSIVE. Computed on the **aggregate window only** (slice-level R is
  lumpy-month noise; reported as diagnostic).
- **Prior cross-check:** `R` must be consistent with the v7.0 ~96% record→tick
  retention bridge; a gross departure from that prior is a red flag even if in
  band.

### Gate 2 — DRAWDOWN FIDELITY & CALIBRATION (robust, CI-based)
- **Do not gate on a single max-DD order statistic.** Primary statistics:
  **Ulcer-index ratio** (RMS of the whole underwater curve — integrates every
  episode, far lower variance) and **mean-of-top-3 peak-to-trough ratio**.
  Single max-DD ratio and DD *duration* ratio are reported as **diagnostics**.
- **Small-N rule (binding).** When `N` is small (short primary / clean / crisis
  window), gate `k` on the **daily underwater curve** (Ulcer-index,
  mean-of-top-3, and max-DD *ratios* computed from the daily worst-mark path),
  **NOT** on a **monthly-return-reconstructed max-DD** — whose block-bootstrap CI
  is numerically unstable (in the dry-run the upper bound blew to **~121** on
  short up-trending windows, because up-trending resamples produce a near-zero
  model DD in the denominator).
- **Tail companion:** CVaR / 95th-percentile daily worst-mark loss ratio
  (MT5 vs model) ∈ **[0.70, 1.50]**.
- **Evidence-consistent band** (justified from the clean-era prior `k≈0.7–1.1`,
  *not* reverse-engineered from RUN 2): `k_point ∈ [0.70, 1.30]`.
  - **Dangerous direction is `k > 1`** (real DD exceeds model ⇒ model
    understates risk). **Hard REJECT if the 90% CI lower bound on `k` > 1.5.**
  - **Low side is asymmetric:** `k_point < 0.85` does **not** auto-pass — it
    demands a documented mechanism (else INCONCLUSIVE), because a model hiding
    DD is the costly error and a suspiciously low `k` usually signals
    infidelity, not conservatism.
- **Precision:** 90% CI width on `k` ≤ **0.50** else INCONCLUSIVE → MT5 stays
  record (do not freeze).
- **Calibration (the dial):** the multiplier fed to the dial is
  **`k* = the UPPER 90% CI bound of `k` taken across slices/symbols`**
  (conservative direction), **not** the aggregate point estimate. Dial set so
  `model-DD(s) × k* ≤` the owner DD ceiling. **This `k*` is only allowed to set
  the dial after Gate 6's transfer check passes** (fixed-base `k` does not
  transfer across the exposure gap on its own).

### Gate 3 — STABILITY / HOMOGENEITY (multiple-comparison-safe)
- **Pre-register BEFORE RUN 2** (fixed now, no post-hoc DOF; **RATIFIED
  2026-07-11**):
  - Slices = **three consecutive ≈10-month blocks** (equal length — the old
    6/12/12 made the 6-mo slice the noisiest yet dominant); three equal
    ~10-month blocks of the real-tick primary window: `S1 = 2023-07-01 …
    2024-04-30`, `S2 = 2024-05-01 … 2025-02-28`, `S3 = 2025-03-01 …
    2025-12-31`.
  - Symbols = the **exact five**: `USTEC, XAUUSD, USDJPY, BTCUSD, ETHUSD`
    (by 2024-25 gross-contribution rank; fixed here).
- **Intra-era homogeneity (the three registered slices).** **Replace the
  point-spread conjunction** (`max/min ≤ 1.5×` AND `no symbol > 2×`) — a ~56%
  chance of tripping by pure noise on 5 single-symbol extremes — **with a single
  bootstrap homogeneity test**: per-slice `k`'s are consistent with a common `k`
  (Cochran-Q / I²-style dispersion); FAIL only if the heterogeneity CI
  **excludes** a common `k`. Note this tests homogeneity **within the clean era
  only** — all three slices are real-tick 2023-07…2025-12.
- **Cross-boundary homogeneity arm (mandatory).** The intra-era test above cannot
  see a regime the primary window never contains. Additionally compute `k` in the
  **crisis windows of Gate 5** and compare **clean-era `k` vs crisis-era `k`**; a
  large divergence is a **heterogeneity flag**. Because the only 2020–2025 stress
  events (COVID 2020-03, the 2022-05 leverage event) fall in the
  **generated-tick secondary era**, this arm is **DIAGNOSTIC** where it must rely
  on generated ticks and becomes **GATING only if Gate 5's real crisis-tick pull
  succeeds**.
> **Caveat (binding).** The three registered slices, being intra-clean-era,
> cannot by themselves detect the stressed-regime `k≈3.4–4.8` (the 2022-05 event)
> or the `6.5×` COVID tail. A Gate-2 / Gate-3 near-pass on the real-tick primary
> window therefore **NEVER** constitutes deployability — stress / crisis / margin
> discrimination is carried by **Gates 5 and 6, which are mandatory and
> non-waivable**.
- **Symbols are diagnostic, FDR-corrected**: require **≥4 of 5** within the
  Gate-2 band (not all-must-pass); a single thin-liquidity outlier triggers the
  **per-symbol middle branch** (cap/exclude/widen-allowance for that symbol),
  **not** whole-engine demotion. **Per-symbol `k` is UNCOMPUTABLE from the
  current aggregate record curve**, so this arm **MANDATES a per-symbol
  (per-sleeve) MODEL worst-mark curve export for RUN 2** (the record engine holds
  the sleeve decomposition and can produce it; it is also the only way the gates
  can observe the XAUUSD volume-cap pathology). **If that export is not produced,
  the per-symbol arm DROPS to MT5-side diagnostic only and the aggregate
  homogeneity test governs.**
- Any correlation sub-test is computed on the **full window only** (n=6 slice
  correlations are meaningless). Stability *through* a stress boundary is
  carried by **Gate 5**, not by over-tightening this gate on a benign window.

### Gate 4 — PATH TRACKING (new)
Endpoint agreement (same CAGR, same max-DD) can coexist with poor month-to-month
tracking (compensating errors). Add a paired monthly regression on the
**marked-to-market (worst-mark) monthlies**, full window:
`MT5_m = a + b · model_m`.
- **PASS:** slope `b ∈ [0.85, 1.15]` **AND** Fisher-z **90% CI lower bound** on
  the correlation **> 0.60** (must *beat*, via its CI, the contaminated 0.67
  floor — not merely reach a point estimate). Stated as a **directional** check:
  n≈30 cannot cleanly separate 0.67 from 0.80, so this fails a clear mismatch,
  it does not certify a precise correlation.

### Gate 5 — CRISIS SURVIVAL (new; mandatory; SURVIVE not MATCH)
Crisis behaviour — the only losses that can end the account — must not be waved
through on a "generated-tick" excuse in exactly the regime where the engines are
measured to disagree most (v7 COVID tail **35.6% MT5-tick vs 5.5% 1m worst-mark
= 6.5×**; the 2022-05 USDJPY leverage event **same-event k 3.4–4.8×**).
- **Reconcile model vs MT5 on 2020-03 (COVID) and 2022-05 (the leverage event)**
  at the candidate dial. The charter permits new downloads: **pull real tick
  data for the top symbols** rather than accepting generated ticks. Looser band
  is fine; skipping is not.
- This is a **survival** gate: the compounding-at-dial account must **survive** a
  crisis-tail ceiling **per-preset (IC = 30%, RATIFIED 2026-07-11; FTMO deferred;
  see the Owner-ratify table)** with no stop-out.
- **If real crisis ticks are genuinely unavailable**, pre-register that the model
  is **NOT crisis-validated** and force the dial to survive
  `model_tail × f_tail`, where `f_tail =` **6.5× (range 3.4–6.5×), RATIFIED
  2026-07-11 (shared — see the Owner-ratify table)** is the measured record→tick
  tail-underestimate factor.

### Gate 6 — DEPLOYMENT / MARGIN FEASIBILITY (new companion; COMPOUNDING run)
Fixed-base (Gates 1–4) structurally erases the exact failure mode the campaign
cares about; the g3-forensics memory already makes this the standing dial rule.
On a **compounding** MT5 run at the candidate dial:
- **Margin feasibility:** track the **margin-level (ML) minimum**, the **peak
  desired deposit load ≤ 75% (IC, RATIFIED 2026-07-11; FTMO deferred; see the
  Owner-ratify table)** (the g3-forensics ceiling; IC's 70–80% band), and the
  **No-money-reject count**; the MT5 realized-equity path must never touch
  liquidation.
> **"0 tester stop-outs" is a TESTER-OPTIMISM ARTIFACT, not survival.** The MT5
> tester **refuses** orders when funds are short (G3 logged **5,817 No-money
> rejects**) but models **no broker stop-out cascade** — so a **zero stop-out
> count must NOT be read as "survived."** The margin verdict rests on the
> **ML-minimum, the peak deposit-load ceiling, and the No-money-reject count —
> never on stop-out-event count.**
- **k(s) transfer check (licenses Gate-2's `k*`):** a `k` sweep across
  `s ∈ {0.6, 0.7, 1.0}` must show `k` **flat within ±15%** in the deployment
  neighbourhood **before** any `k*` is adopted as the ceiling multiplier. If `k`
  is not flat — or the s≈0.7 run's peak margin utilisation **exceeds** the
  "unstressed" envelope where clean-era `k≈0.7–1.1` held — the **fixed-base `k`
  is VOID**: the DD gate is re-measured *at the dial* and the fixed-base number
  may not be quoted for calibration. **This transfer check is NA for any
  single-`s` run — a fixed-base `k*` may NOT be adopted from a single run.**
> **FTMO preset — this gate changes in KIND.** For the FTMO preset Gate 6 is
> **replaced** by FTMO-**rule** compliance (0 daily-5% breaches, 0 static-10%
> floor touches, `P(breach either rule in 12 mo) ≤ 0.05`), **not** a deposit-load
> ceiling. That full FTMO Gate-5/6 spec is **deferred** — to be fully specified
> when FTMO's own reconciliation run is prepared; see the Owner-ratify table
> (IC vs FTMO).

---

## Friction-haircut rule (binding on the 96.1% CAGR gate)

RECONCILED confirms model **structure** is trustworthy; it **never** converts
gross to net. Gate 1 adds friction back to the *MT5 side* to compare against a
*gross* frictionless model — validation therefore happens in **gross space**,
while the owner's headline gate (CAGR > 96.1%) lives in **net space**. Therefore:

> **Any gate-facing CAGR must be NET.** Use either (a) the MT5 **net** CAGR
> directly, or (b) `model CAGR − measured deals-sheet friction haircut`
> (with spread still un-credited). The friction haircut (memory: ≈6.1pp CAGR
> hard floor, 6–15pp realistic) is **always** applied. RECONCILED never licenses
> quoting the frictionless model's CAGR at the 96.1% gate.

---

## Consequence decision-table

| Gate outcome | Verdict | Action |
|---|---|---|
| Gates 1–6 all PASS with adequate precision | **RECONCILED** (engine fidelity only) | Adopt `k*` (upper-CI, transfer-checked); set the dial via `model-DD(s)×k* ≤ ceiling`; **re-running the *identical frozen model* on refreshed data is not re-litigated** — but this is *not* "strategy validated" and does *not* discharge the 2026 OOS gate. |
| **Any** gate's CI straddles its threshold (underpowered) | **INCONCLUSIVE** | MT5 stays engine of record; **do not freeze / do not deploy on the frictionless number**; extend the real-tick window / collect more data before deciding. (Loss-asymmetry default.) |
| Gate 1 OR Gate 2 point out of band **but** Gate 3 homogeneous (consistent, correctable BIAS) | **RECALIBRATE** | If a *stable* `k` sits outside the band, adopt-with-multiplier-and-caveat (not a wholesale recalibrate); if the *bias is in the return*, recalibrate model + refreeze + document; re-open all gates on the new hash. |
| Gate 3 **heterogeneous** (`k` inconsistent across slices) | **UNRELIABLE** | Frictionless model demoted to a design tool; **HALT deployment, freeze the model as design-only, and ESCALATE to the owner's MT5 machine** for an authoritative real-tick re-run (an in-place "MT5 becomes engine of record" swap is *not executable on this Mac* — MT5 real-tick is deferred per assimilation-findings). |
| Gate 3 per-symbol outlier only, aggregate stable | **RECONCILED w/ symbol caveat** | Cap / exclude / widen-allowance for that one symbol; no whole-engine demotion. |
| Gate 5 crisis-survival FAIL | **NOT crisis-validated** | No deployment at a dial that cannot survive `model_tail × f_tail`; force the dial down until it does, or escalate for real crisis ticks. |
| Gate 6 margin FAIL (ML-min breached / load > ceiling / No-money rejects) | **NOT deployable at that dial** | Reduce `s` and re-run Gate 6; fixed-base LAB pass is irrelevant to this branch. |
| Secondary (2020–22) fail but primary + Gate 5 pass | **RECONCILED, data-limited caveat** | Note 2020-22 generated-tick optimism; no gross-quote of that window. |

> **Gates 5 and 6 are MANDATORY and NON-WAIVABLE.** The stress / crisis / margin
> discrimination is carried by them **by design**; **no LAB-gate (1–4) pass may
> substitute**, and a clean-era Gate-2 / Gate-3 near-pass on the real-tick
> primary window is **not** deployability. A run that skips Gate 5 or Gate 6 is
> **NOT-DEPLOYABLE by default**, regardless of Gates 1–4.

---

## Investigation protocol (a gate FAILs → root cause)

Owner methodology (2026-07-11), with the guardrails that keep it from becoming
its own excuse machine. On any FAIL / INCONCLUSIVE, do **not** reach for "it's
friction/ticks" — work this ladder in order.

**Suspect 0 — is the divergence already *expected*?** Before blaming anyone,
check it against the pre-declared envelope: is this one of the KNOWN, bounded
reality-gaps the gates already price in (friction inside the deals-sheet
add-back; DD inside the `[0.70, 1.30]` band; a 2020-22 depth inside the ±3% tick
allowance)? If yes → expected, the measured `k` absorbs it, **investigate
nothing**. Only a divergence that breaks *out* of the envelope enters the funnel.
This is what stops us "investigating swap".

**Route by signature — don't march blindly.** The divergence fingerprint points
the suspect faster, and with less confirmation bias, than a fixed sequence:
- clean in real ticks, ugly only in 2020-22 → **ticks** (data-limited; pull real
  ticks per Gate 5, else caveat — not a "fix")
- concentrated in one symbol → **EA** (symbol map / spec / lot rounding)
- scales with account size / only under compounding → **margin/caps** (Gate 6)
- uniform across symbols and time → **friction or risk-mapping** (model scope)

**Suspect 1 — the EA (prime suspect).** The EA is the youngest, least-tested,
transplant-heavy artifact; the record engine reproduced both parents to machine
precision (41/41 Δ0.0; v7 byte-parity). Empirically, every divergence driver
found on G3 was EA/pipeline-side. Default to auditing the EA against its intended
design **first**.
> **Anti-overfit guardrail (binding).** An EA change is legitimate ONLY if it
> fixes a *provable mismatch between the EA code and its intended design/spec*.
> "It moved the numbers closer" is a **symptom, never a justification** — a fix
> justified only by improved agreement is overfitting the EA to the model and is
> forbidden. Every G3 fix met this bar (the flat-hour sentinel bug, the reject
> spin — real defects, independent of whether they improved agreement).

**Suspect 2 — the model (second, and *enrich* not merely distrust).** Only after
the EA is exonerated against its spec. The model is not "wrong" — it is
deliberately *scoped* (frictionless; no margin; no ticks). Two rules:
- **A stable `k` often beats model surgery.** If the residual is a *consistent,
  predictable* offset (Gate 3 homogeneous), a measured `k*` multiplier is
  sufficient and cheaper than re-engineering the engine — adopt-with-caveat.
  Enrich the model only when `k` is *unstable* (Gate 3 heterogeneous) or when the
  model's *absolute* number is needed for a gate (the 96.1% net CAGR).
- **MT5 is a proxy for reality, not reality.** When enriching, import only *real*
  effects learned from MT5 (a swap model, a spread model, a margin model) —
  **never** overfit the model to MT5's *own* artifacts (generated-tick roughness,
  a broker-specific fill quirk). The target is live reality; MT5 is the best
  available witness, with its own error bars.

---

## Owner-ratify parameters — IC + shared RATIFIED 2026-07-11; FTMO deferred

The gates run **SEPARATELY per preset**: **IC** and **FTMO** each get their own
reconciliation run and their own threshold evaluation, so IC's aggressive bar is
**not** lowered to accommodate FTMO's strict one (or vice-versa). **Gates 1–4 are
the same machinery with per-preset thresholds; only Gates 5–6 change** — the
ceilings for rows #1/#2 below, and the metric **KIND** for FTMO's row #3
(Gate 6). The IC column and the shared parameters are committed (**RATIFIED
2026-07-11**); the FTMO column remains a proposal, **deferred to FTMO's own
reconciliation run prep**.

**PER-PRESET (risk-appetite / rule-defined — split IC vs FTMO).**

| Parameter (per-preset) | IC preset — **RATIFIED 2026-07-11** | FTMO preset — [OWNER TO RATIFY — deferred to FTMO's own reconciliation run prep] |
|---|---|---|
| **Real-DD ceiling** (the dial) | **30%** — owner tolerance ("I can stomach 30%"), band **20–30%** | **10%** — the **static max-loss rule** (rule-defined, not a preference) |
| **Crisis-survival tail ceiling** (Gate 5) | **30%** | **10%** — must survive the static floor **in crisis** |
| **Feasibility gate** (Gate 6) — *different in kind* | peak deposit-load **≤ 75%** (band **70–80%**; the retail-1:30 binding constraint) | **RULE compliance:** **0** daily-5% breaches, **0** static-10% floor touches, `P(breach either rule in 12 mo) ≤ 0.05` |
| **`R_net` net-CAGR floor** | **≥ 40% net** — provisional low-end of the ~40–50% range (the private return goal; the EA ran hotter than the model, so live may beat it); **explicitly re-confirmed once G3b sets the final dial** | **"match IC as far as the FTMO rules allow"** — judged on **challenge pass-rate + funded expectancy post-profit-split**, not a raw CAGR floor |

> **Gate 6 is different in KIND across presets, not merely a different
> threshold.** IC's feasibility is a **continuous margin-load ceiling** (the
> retail-1:30 binding constraint); FTMO's is **rule compliance** — breach counts
> plus a breach-probability bound. Same Gate-6 slot, a **different metric**.

**SHARED (both presets, one value — RATIFIED 2026-07-11).** These do **not** split
by preset — they are **not** risk-appetite choices but **properties of the engine
/ method**: the record→tick tail gap and the bootstrap statistics are
preset-independent, so IC and FTMO inherit identical numbers.
- **`f_tail` crisis-underestimate factor** — **6.5×** (range **3.4–6.5×**); a
  **measured** record→tick tail-underestimate property (engine fidelity), applied
  to `model_tail` when real crisis ticks are unavailable — not an appetite.
- **INCONCLUSIVE ⇒ demote precision policy** — `k`-CI-width **≤ 0.50**,
  `R`-CI-width **≤ 0.15**; default **demote to MT5 / do not freeze** when a gate
  CI straddles its threshold.
- **Tick allowance** — **±1%** real-tick (primary window) / **±3%** generated-tick
  (secondary window).

> **Owner decision (2026-07-11).** Reconciliation parameters are **per-preset**:
> IC and FTMO reconcile on separate runs against separate thresholds so IC's
> aggressive bar is not diluted to FTMO's strict one; only the engine/method
> parameters (`f_tail`, precision policy, tick allowance) stay shared. **The IC
> column and all shared parameters are RATIFIED 2026-07-11 and this table is the
> source of truth; the FTMO column is deferred to FTMO's own reconciliation run
> prep and remains [OWNER TO RATIFY].**

---

## Standing test for v1.1 → v1.x (anti-drift ratchet)

- **RECONCILED binds to `RECON_MODEL_HASH`.** The "future in-tolerance runs not
  re-litigated" amnesty means **only**: *we do not re-argue that the model↔MT5
  bridge is trustworthy when re-running the **identical** model on refreshed
  data.* It **never** means "a changed model that stays in-band is auto-accepted"
  and it **never** means "the run passes the owner's gates."
- **Per-EA-build reconciliation is MANDATORY (owner directive 2026-07-11).**
  **EVERY new EA build — any new `.ex5` hash — that is given a tester run MUST
  execute the full 6-gate reconciliation and RECORD a dated `FMA3-RECON-N` ledger
  entry BEFORE it may deploy. No EA deploys without a recorded ledger entry.** A
  **RECONCILED** verdict binds to the specific **`.ex5` hash + `RECON_MODEL_HASH`
  pair**; a change to **either** the model hash **or** the EA `.ex5` hash re-opens
  **all** gates on the new pair. The verdict is a property of that exact pair, not
  of the strategy in the abstract.
- **Any model modification re-opens ALL gates** (Gates 1–6 + the 2026 OOS gate)
  on the new hash. A later edit that stays "in tolerance" on the bridge is *not*
  a pass — the bridge only measures return-ratio, DD-ratio, path-tracking and
  margin fidelity, not Sharpe / negative-quarter / per-symbol drift.
- **Explicit re-validation triggers:** material dial move, real-tick data-window
  extension, cost-model change, symbol-set change, **or any new EA `.ex5` hash**
  forces a fresh reconciliation under a new ledger entry.

## Out of scope / anti-rescue

No post-hoc choice of slices or symbols (both fixed above before RUN 2). No
fitted friction top-up beyond the exact deals-sheet value. No quoting a
fixed-base LAB `k` for calibration once Gate 6's transfer check voids it (and
none adopted from a single-`s` run). No quoting frictionless model CAGR at the
96.1% net gate. No reading a full-sample `R_net ≈ 1` as fidelity (it can be
offsetting errors — use the windowed `R_net`). No reading "0 tester stop-outs"
as survival (tester-optimism artifact — judge margin on ML-min / load /
No-money rejects). No substituting a LAB-gate (1–4) pass for the mandatory,
non-waivable Gates 5 and 6. No gating small-N drawdown on a
monthly-return-reconstructed max-DD (use the daily underwater curve). No forcing
an underpowered result into PASS — the home for it is INCONCLUSIVE → demote.

---

## Reconciliation ledger (FMA3-RECON-N)

Standing record of every 6-gate reconciliation run (owner directive 2026-07-11).
**No EA deploys without a recorded, dated entry here**; a **RECONCILED** verdict
binds to the specific `.ex5` hash + `RECON_MODEL_HASH` pair on its row, and a
changed model **or** EA hash re-opens all gates under a new entry.

| Entry | Date | EA .ex5 (sha / size, compile date) | Model hash | Run | Verdict | Decision |
|---|---|---|---|---|---|---|
| **FMA3-RECON-1** | 2026-07-11 | *n/a — the criterion itself* | `51a7541cc2aaa593` | G3 negative-control dry-run (report _56) | **CRITERION VALIDATED** — correctly returned **G3 = UNRELIABLE / NOT-DEPLOYABLE for the right reasons**; discrimination confirmed at `k≈1` on the clean 2024-25 sub-window; no false pass | Criterion committed + hardened (5 dry-run fixes applied) |
| **FMA3-RECON-2** | PENDING | `FableFederation_V1.ex5` (sha256 `d096b875e0a98b5bef5f4fa6142872cb3f91fa3858f3c4692c7e4efab4973d8b`, 123,796 B, compiled 2026-07-10) | `51a7541cc2aaa593` | G3b (fixed-base RUN 1 smoke → RUN 2 real-tick) | **PENDING** | Awaiting run |
| **FMA3-RECON-3** | SUPERSEDED | `FableFederation_V2.ex5` (sha256 `4ac781d8…`, 132,060 B, 2026-07-12) | `51a7541cc2aaa593` | v2 v34-sleeve fix (cause A eurq + cause B live joint-share) | **SUPERSEDED by v3** | v2's cause-B (compute-live joint share) proven to diverge from the model at s≠1 (both shipped dials are s≠1). v2 not run; superseded by the v3 replay EA. v2's cause-A eurq fix carried forward into v3 (all symbols, unconditional). |
| **FMA3-RECON-4** | RECONCILED (deployable) | `FableFederation_V3.ex5` (sha `d516350b…` runs 1-3 → `740da0ff…` after volume-limit fix) | `51a7541cc2aaa593` + stream sha `d00b614b…` | v3 = faithful executor of `model/v3` (replays 33-symbol netted fed_frac, sizes off BALANCE, InpScale dial). Runs (1m-OHLC, 1:500, HEDGING): PARITY s1.0 €391,873 (0.84× model, 0 rej); IC s1.6 €2,544,423 (0.66×, 51,346 volume-limit rejects); FTMO s0.7 €1,265,541 (**0.95×**, 0 rej, 28 breaker fires vs 26). | **v3 FAITHFUL — position fidelity median after/want=1.000 all runs; 33/33 symbols (v34 revived).** Equity 0.66-0.95× the record by dial, gaps = 3 physical constraints the frictionless engine ignores (friction; SYMBOL_VOLUME_LIMIT XAUUSD 10/SOLUSD 1000/ETHUSD 100, binds >~€2M/s; margin). €3.87M IC-s1.6 = frictionless ceiling, not reachable at scale on 1 retail account. Deployable dials reproduce cleanly (FTMO 0.95). Full record: `model/v3/RECON4_RESULTS.md`. Pending: Run 2 clean re-run; deployable-dial ship decision. |
| **FMA3-RECON-5** | 2026-07-14 | *n/a — SOURCE FREEZE, no `.ex5`* | freeze_hash `fc14159f5352d685214d3a417b0d71117dda300a7c7be02919daa83fd06c1446` (sha256 over 16 sorted source files; config_hash `48c09199fbf83d82`) | **FMA3-v34-freeze-1** — physical snapshot of the shipped-book source set (7 sleeves + `mag_xau` overlay + `ensemble`/`core`/`account_engine_1m`/`eval_v34_pin_s10` + `strategy_fable` + `ea/brain/{target_engine,brain_config}` + transitive dep `ea/tests/reference/targets.py`) into `model/v3/freeze/FMA3-v34-freeze-1/`. | **FROZEN — PIN reproduced to ≤1e-6.** `build_c2()→account_engine_1m` (EUR10k, 1m): CAGR **+0.8865880763** (Δ4.1e-11), final **€449,707.7453** (Δ3.4e-5, rel 7.5e-11), MaxDD_worst **0.2167488591** (Δ5.2e-12), Sharpe 1.8543, negY 0 / negQ 1. Source-of-truth verified: `strategy_fable.SLEEVE_WEIGHTS` 7 sleeves == `V2_CAPS`, `GLOBAL_SCALE`==`SCALE`==10.0, `structural_gold_cap(V2_CAPS,10)`==**1.80**; renorm helper `build_portfolio_positions` (÷Σw=0.826, 1.2107× hot) confirmed **NOT** on the `build_c2` path (quarantined). 4 stale `1.62`/`1.98` scale COMMENTS flagged (code is correct, comments lag scale-9/11 era). | Book frozen; golden parquets (8 sleeve `*_pos` + `book` + `curve`) + `manifest.json` written under the freeze dir. Env: py 3.13.12 / pandas 2.3.3 / numpy 2.4.2. Owner directive "freeze the current book now" satisfied. |
| **FMA3-RECON-6** | 2026-07-14 | *n/a — B-pure Stage-0 numeric kill-switch + probes, no `.ex5`* | freeze_hash `fc14159f5352…` (same as RECON-5) | **B-pure Stage-0** (freeze + primitives + P1c numeric gate + feed-provenance probe) — the ~6-day cheap kill-switch before any ~28–40-day native-MQL5 port commitment. Full record: `model/v3/B_PURE_STAGE0_RESULTS.md`. | **KILL-SWITCH GREEN (did not fire).** (1) Freeze reproduces pin ≤1e-6, SoT landmines resolved (renorm quarantined, gold cap derived 1.80); open item = 2 un-snapshotted parent framework files (`NewStrategyFable5/config/settings.py`, `engine/costs.py`) → freeze not fully hermetic. (2) Feed-provenance: IC delta = **0 by construction** (research_cache byte-identical to live IC feed, book built+priced on IC); 14/37-symbol Duka robustness probe moves book only **−0.69pp CAGR / +0.09pp MaxDD / −2.16% EUR**, fed[h,k] ≤11% of peak, gates intact → **NOT a blocker for IC**; full-book blocked on a 37-symbol independent export. (3) P1c: scalar float64 reproduces `ewm_mean`(adjust=True) **4.5e-14**, `ewm_std`(Welford,ddof-corr) **1.2e-15**, `rstd`(ddof=1) **1.4e-14**; Donchian/`to_hourly`/daily-resample **EXACT (0)**; both mandatory conventions PROVEN by divergence (adjust=False 93.4%, ddof=0 5.13%). Measured achievable **gate residual** (conservative 1e-9 feed proxy): **ΔCAGR ~[0.06,0.8]pp, ΔMaxDD_worst ~0.26pp, ΔBreach ~[0.14,0.28]pp** — discrete-state-flip, not drift (identical maxabs 6.08e-2 at 1e-9 & 1e-11, 0 big flips). | **Stage-0 technical PASS, but full port = NO-GO / HOLD.** Not a technical blocker — governance gates stand: book not frozen for production (v2.2 re-derivation on roadmap), "no Python in live loop" not a ratified hard mandate. **Ship Option D; do not start B-pure.** Proposed port-vs-record accept band **[OWNER TO RATIFY]**: ΔCAGR ≤±1.0pp, ΔMaxDD_worst ≤±0.5pp, ΔBreach ≤±0.5pp; hard sub-gates: continuous ≤1e-8, integer/Donchian/grid state EXACT, tail-cert on COVID. Residual risks needing in-terminal MT5 confirmation: **R1 MathRound** (half-away vs banker's, systematic on crisis 0.02 grid + mag $100 magnet), **R1b** tie-straddle-via-ULP, **transcendental last-ULP** (tanh/exp) — none measurable on Mac. Stages 3–8 BLOCKED on owner input (D→B ratification, tolerance ratification, 37-sym feed export, `v34_book_equity_1m.parquet` for stage-6 `b_h`, ≥2019 warm data for stage-7). |
| **FMA3-RECON-7** | 2026-07-14 | *n/a — B-pure Wave 1 scalar reference, no `.ex5`* | freeze_hash `fc14159f5352…` (FMA3-v34-freeze-1, same as RECON-5/6) | **B-pure Wave 1** (stages 3–5 at scalar reference level) — pure-Python bar-by-bar scalar steppers for all 7 sleeves + `mag_xau` overlay (`research/bpure/steppers/`), validated per-sleeve vs the frozen goldens, assembled via `ensemble_stepper.py` into the full book, gated on `account_engine_1m` (EUR 10k, 1m worst-mark). Full record: `model/v3/BPURE_WAVE1_RESULTS.md`; result JSONs `research/bpure/parity/*.json`. | **WAVE 1 PASS — scalar reference = the MQL5 spec.** 7/7 steppers verifier-CONFIRMED: state sequences **EXACT** (0 mismatches; crisis 10,941 checks, intraday 98,758 bar states), positions ≤2.5e-14 vs golden (crisis + trend_v2 bit-exact 0), all warm-start roundtrips identical. Book maxabs 4.20e-14, **0/1,530,749 cells over the 1e-12 gate** (132,454 last-ulp cells differ; stretch bit-identity not met). Gate vs full-precision pin: ΔCAGR = ΔMaxDD = ΔSharpe = **0.0**, ΔFinalEUR 5.8e-11 (CAGR 0.8865880763, MaxDD_worst 0.2167488591, €449,707.7453, negY 0 / negQ 1); −3.4e-5 vs the 4dp-quoted constant is quoting precision only. carry_breakout exact (no approximation — "~100%" claim stands). Honest flags: 1-ulp gross-cap summation-order residual (carry); dc-index validator hole closed by independent coverage check; policy-rate date_range re-freeze edge; meanrev `z` 8.0e-10 (largest cont. residual, absorbed in positions); thin crisis threshold margins (1.1e-5–7.8e-5) = the exact in-terminal MathRound/ULP watchpoints. | **NOT a deployment event** — proves stages 3–5 logic complete at reference level only; no MQL5, no `b_h`, no in-terminal MathRound/ULP confirmation, no warm-start cert vs ≥2019 data. Wave 2 = per-stepper `.mqh` + wine compile + Gemini-pattern in-terminal replay driven from frozen-golden inputs; Wave 3 = `b_h` engine (needs `v34_book_equity_1m.parquet` golden), V7Sim/`a_h`, blender (replay unified fed_frac), EA integration → new RECON-N on the resulting `.ex5`. |
| **FMA3-RECON-8** | 2026-07-14 | *n/a — B-pure Wave 2 replay harness; `TestV34Native.ex5` is a Script (83,932 B, compiled 2026-07-14 03:11), NOT a trading EA* | freeze_hash `fc14159f5352…` (FMA3-v34-freeze-1, same as RECON-5/6/7) | **B-pure Wave 2** — native MQL5 port of all 8 units (`mt5/ea/Include/FMA3v34/`) + in-terminal replay harness `TestV34Native.mq5`. All 9 check scripts + harness compiled **0 errors / 0 warnings** (wine MetaEditor, logs re-read UTF-16). Installed at the wine prefix: includes `diff`-identical to repo; inputs CSV 23,683,879 B sha256 `a96a4971…` identical to repo source; every raw-close→derived recipe proven bitwise by `export_master_inputs.py`; Python harness-sim passes the book gate (maxabs 4.2e-14, 0/1,530,749 cells > 1e-12). Full record: `model/v3/BPURE_WAVE2_STATUS.md`. | **BLOCKED-BEFORE-RUN (verifier confirmed=NO).** `CarryBreakout.mqh` CAD policy-rate table holds 4 wrong epoch days vs the frozen `costs.py` spec — 19513/19548/20087/20129 should be 19515/19550/20117/20159 (dates early by 2/2/30/30 d; VALUES correct; independently re-confirmed vs spec). Measured impact: 128 (day,pair) net rows wrong over 64 days, **0** carry-sign and **0** TOP_K changes on this grid — output happens to be unaffected, but the constants are wrong vs spec, the file's "Verified equal to the Python parse" claim is false, and the day0=19300/66-day smoke check ends before the first bad date. No other blocking finding; 7/8 units clean. | Fix the 4 integers (CAD block, `CarryBreakout.mqh` lines ~136–137) + recompile BEFORE the in-terminal run; owner then runs the Script in the terminal and gates with `validate_mql5_book.py` (1e-12). Not a deployment event; Wave 3 (b_h, V7Sim/a_h, blender replay, EA) still ahead → its `.ex5` gets its own full 6-gate RECON-N. |
| **FMA3-RECON-8b** | 2026-07-14 09:16 | *n/a — Script replay, no trades* | freeze_hash `fc14159f5352…` | **RESOLUTION of RECON-8.** CAD rate table FIXED (19515/19550/20117/20159), full table re-verified **178/178** entries vs frozen `engine/costs.py` (0 mismatches), reinstalled + recompiled **0/0** (`TestV34Native.ex5` 84,326 B). Owner ran `TestV34Native` in the MT5 terminal (ETHUSD H1, 09:16:23–24; Experts log DONE `bars=49379 rows=49379`). `validate_mql5_book.py` vs golden `book.parquet`: **PASS — max\|diff\| 4.197e-14, 0/1,530,749 cells > 1e-12**, 0 NaN, shapes/timestamps/columns aligned. Worst symbols USA500 4.2e-14 / USTEC 3.6e-14 (last-ULP on the tanh-heavy intraday/trend legs); first divergence 2020-01-06 02:00 XAUUSD 2.2e-16. | **PASS.** The MathRound/banker-tie + transcendental-ULP residuals Stage-0 deferred to an in-terminal run are now MEASURED ≤4.2e-14 — negligible. Native MQL5 reproduces the shipped v34 book over the full 2020-2025 grid within gate. SCOPE: validates the v34 SIGNAL layer arithmetic on the frozen (float32-quantized) input CSV; does NOT cover b_h-native, v7/a_h, live blender, execution, or live-tick pricing (Wave 3). | Proceed to Wave 3; the native v34 signal layer is validated. `mql5_book_parity.json` records the run. |
| **FMA3-RECON-8c** | 2026-07-14 13:36–13:42 | *n/a — Script replays, no trades* | freeze_hash `fc14159f5352…` | **Wave-3 component in-terminal gates.** Owner ran 5 scripts (ETHUSD H1): CheckBlend **ALL PASS** (3 blend cases bitwise, e-notation StringToDouble gauntlet == CPython); CheckSatEquity **FAILURES=0** (7-bar synthetic incl. margin-cap shrink, sign flip, min-lot close, swap, joint stop-out, python-JSON warm start); TestBlend 49,379 hours → 805,183 rows + 402 sentinels, sumcheck **BITWISE MATCH**, judge `validate_blend.py`: vs golden17 **max\|diff\| 0.0**, vs 12dp pinned stream 5.0e-13 (quantization bound), structure IDENTICAL, OVERALL PASS; TestSatEquity 2020Q1 **92,155/92,155 eq+eqw exact, max\|d\|=0** (final_balance 11984.916325804577, 307 trades == mirror); TestSatEquity 2020Q2 warm-started from Q1 state_out **93,581/93,581 exact, max\|d\|=0** (12366.578333400847, 842 trades == mirror); chained end-states double-bitwise vs expected (0 mismatches; JSON text differs only as MQL5 `0` vs python `0.0`). | **PASS.** BookBlend arithmetic+netting and SatEquityNative (b_h engine) are terminal-proven — blend full-precision-exact on all 805,585 stream rows; b_h bitwise over 185,736 real 1m bars incl. the COVID 2020Q1+Q2 tail with a chained warm start. SCOPE: frozen inputs; live a/b computation + execution remain (EA assembly). CoreSim in-terminal chain not yet run (input export pending). | Next: remaining b_h quarters (single chained all-quarters run), CoreSim input export + TestCoreSim, then FableBookNative EA assembly → full 6-gate RECON-9. |
| **FMA3-RECON-8d** | 2026-07-14 16:15–16:22 | *n/a — Script replays, no trades* | freeze_hash `fc14159f5352…` | **Wave-3 FULL component gates (final two).** Owner ran TestSatEquityChain (all 24 quarters chained, in-memory state): **24/24 PASS, 0 fail/missing, total_bars=2,948,650, every quarter eq_exact+eqw_exact with max\|d\|=0**, final_balance 434,132.98905617336 / 20,403 trades == the bitwise-proven reference. Owner ran TestCoreSim (32 segments, auto seed-chain, ~20.9M leg-bar rows): judge `validate_mql5_coresim.py` **PASS 32/32 segments** (idx/eqc/eqw/margin bitwise per segment), full-run final eqc **532229.8433634703 == target**. | **PASS — the reference-gated phase is COMPLETE.** All four native components are terminal-proven: Satellite signal book (RECON-8b, 4.2e-14), BookBlend (RECON-8c, 0.0 full-precision), SatEquityNative b_h (bitwise over the FULL 2,948,650-bar curve in-terminal), CoreSim a_h (bitwise 32/32 segments, exact final eqc). SCOPE: frozen replay inputs; live-feed computation + execution = EA assembly. | Next: FableBookNative EA assembly (live a/b → BookBlend → BookExec/Guardian), warm-start cert, tolerance ratification → full 6-gate RECON-9. |
| **FMA3-RECON-8e** | 2026-07-14 20:53–21:00 | *n/a — Script replays, no trades* | freeze_hash `fc14159f5352…` | **S1: R1 WHOLE-BOOK COMPUTE GATE CLOSED IN-TERMINAL.** Owner ran 3 scripts (BTCUSD M1). (1) `CheckBookOrchestrator` **ALL PASS** (wiring smoke; log confirms a_first=9955.541862 ≠ b_first=10000 → own-first-value normalisation, not the 10000 seed). (2) `TestBook` — the ASSEMBLED native chain (ComputeFCore + 8 sleeves→f_sat + a/b equity engines + BookBlend + build_rows emission, driven by BookOrchestrator.mqh) over the full grid (h1=49,379, m1=2,948,650, f_core consumed 49,355/49,355) vs the RECON-4-pinned golden `FMA3_fed_frac_v3.csv` (sha d00b614b…): **805,585/805,585 rows structurally identical (805,183 data + 402 sentinels), max\|diff\| 5.0604e-13 @ (1641837600, USTEC), 0 rows > 1e-12** → PASS. Independent judge `validate_book_stream.py` reproduced the same max + argmax. b-engine final **bit-equal**: bal 434,132.98905617336 / 20,403 trades. 41 rows in the 5e-13–1e-12 quant band (mirror had 38; +3 = MQL5 no-FMA/ULP noise, inside gate). (3) `CheckFCore` — f_core MQL5 layer vs frozen parquet: **bit-equal 0.0 on all 8 columns**, final eqc 532,229.84336347028 == pin. | **PASS.** The native EA's ENTIRE COMPUTE PATH is terminal-proven end-to-end — no Python in the compute chain. R1 (compute residual) is CLOSED at 5.06e-13. SCOPE: frozen replay inputs + FROZEN Core leg targets; live Core leg-target source, execution, live feed (S0-proven) and R2 remain. | Next: S2 execution seam (live blend → g_fedTgt[33], RECON-4 position fidelity) + the live Core leg-target source (CoreEngine CTrade collision); then S3 tester/R2, S4 warm-start RECON-9-WS, S5 crisis real-tick → full 6-gate RECON-9. |
| **FMA3-RECON-8f** | 2026-07-14 22:45 | *n/a — python gate + compile, no trades* | freeze_hash `fc14159f5352…` | **S2-prep: BookState safety serializer (independently verified).** BookState.mqh (%.17g full-ledger atomic serializer + j-splice refuse-to-trade latch) + CheckBookState.mq5, all wine-compiled **0/0** (TestBook re-compiled 0/0 = no S1 regression). Independent re-run of the split gate (reused_baseline=false, reused_save=false): save at 2022-06-30 23:00 (rows 251,354, j 5.9356), restore into a FRESH mirror, resume to end — **tail BITWISE identical (0 diffs), end-state BYTE-identical, baseline R1 unchanged 5.060396546…e-13**. All 5 refuse-latch unit tests fire: clean-load OK; torn-write (eof marker), checksum (fnv64), a-anchor re-base (10000≠10100), and J-SPLICE discontinuity (rel 0.0069>1e-9) all → REFUSE TO TRADE. Verifier confirmed: compiles 0/0, edits additive-only (baseline reproduced bit-for-bit), %.17g-only (no silent truncation), atomic-load never assumes rename atomicity, latch cannot be silently cleared (only ResetLatch, and Ready() still requires a validated load). | **PASS.** The silent-catastrophe failure mode (a re-based a/b passing every <1e-12 self-check while mis-weighting every trade) is now guarded: the EA refuses to trade on any j-splice/anchor discontinuity. Warm-start restore is bitwise. SCOPE: python gate + compile proven; the MQL5 CheckBookState T1-T7 in-terminal battery is STAGED (compiled, not yet run in terminal). | Owner run-sheet: add CheckBookState to the next terminal batch. Then S2 build proper (CCoreSignal from NSF5 python + live trigger detector + exec seam) — needs the 5 Track-A owner decisions ratified first. |
| **FMA3-RECON-8g** | 2026-07-15 | *n/a — python gates + compile, no trades* | freeze_hash `fc14159f5352…` | **S2: CCoreSignal (live Core leg-target source) BIT-ZERO, Opus-verified.** Ported per the owner-ratified path (NSF5 python target functions at R=8.0 PURE, raw server-hour gates, USTEC outer-defer 23:00, EURGBP 20:00 knot, Donchian breach-state carry). Gates: G-S0 27/27 kernels bit-equal vs pandas 3.0.1; **G-S1 all 9 legs max|diff|=0.0, 0 discrete flips over all 32 segments (20,950,676 rows) + full grid**; **G-S2 0 lot-flips (measured per-leg per-bar, not inferred), live-target CoreSim bit-equal eqc/eqw/margin, net_lots bit-equal 8/8, final eqc 532229.8433634703 bitwise**; G-S4 f_core bit-equal 0.0 all 8 cols; **G-S3 31/31 act+decided trigger dates (incl. Sunday-decided 2021-05-23), 32/32 segment t0, seeds bit-equal, LIVE mode identical to harness** (hold-at-legcap touched 5 rows/6y, 0 decision-changing). MQL5 twin (software-fma mirror) bit-zero M-1/M-2 (20.9M rows), CoreSignal.mqh + CheckCoreSignal.mq5 compile 0/0. Opus verify confirmed, no blocking. | **PASS.** The live Core signal computes bit-identically to the frozen targets — CoreEngine refactor avoided (G1 preserved), CTrade collision moot. MEASURED CAVEAT for G-S5: pandas roll_var uses clang FMA contraction (arm64); MQL5 has no fma intrinsic, so the terminal roll_var carries a ~1e-17-class residual that the ratified 0-flip+≤1e-12 criterion covers (bit-zero not guaranteed in-terminal). | Owner terminal G-S5: run TestCoreSignal + CheckCoreSignal (staged, compiled 0/0). Then FableBookNative EA assembly (exec seam + M1 feed assembler + warm blob) → RECON-9. |
| **FMA3-RECON-8h** | 2026-07-15 09:22–09:32 | *n/a — Script checks, no trades* | freeze_hash `fc14159f5352…` | **IC in-terminal COMPONENT certification (6/6 bit-perfect).** Owner ran 6 Scripts (BTCUSD M1): TestCoreSignal **G-S5 PASS bit-zero** (20,950,676 rows, all 9 legs n_not_bit_equal=0/max|d|=0/flips=0 — the fma-contraction question RESOLVED: compiled roll_var contracts exactly as the software-fma twin predicted); CheckCoreSignal **ALL PASS** (embedded golden legs bit 50/50, max|d|=0); CheckBookState **ALL PASS** (T1 132 tail rows bitwise, T2 byte-identical, T3-T7 all 5 refuse-latches FIRE: torn-write/checksum/a-anchor-rebase/j-splice 0.00735>1e-9/open-segment); CheckCoreSignalState **ALL PASS** (v2 warm-blob fold; folded state carries XAU vol ring + mx50 Donchian breach flags; corroborated by the overnight python resume gate = bitwise + 3 drop-controls diverge); CheckFeedAssembler **111 passed, 0 failed**; CheckSwapEurq **PASS bit-equal** (33 syms + 8 crosses + 16 policy ccys, 336 fixtures worst|diff|=0). | **PASS.** Every native component of FableBookNative is now certified on the COMPILED BINARY in-terminal, not just the software mirror. Safety serializer proven to refuse-to-trade on corruption/re-base/j-splice. | Next: Run 7 = FableBookNative Strategy-Tester run (position fidelity + R2, recent window, ratified band) → RECON-9. Then crisis real-tick. |
| **FMA3-RECON-8i** | 2026-07-15 | *n/a — probe + judge, no trades* | freeze_hash `fc14159f5352…` | **Symbol-metadata reconciliation (Option B) + DE40 digits fix.** Owner ran SymbolMetaProbe (37/37 selected). Judge (4 neg-controls green) found: 3 CONTRACT drifts (XAGUSD 1000 vs baked 5000; XBRUSD/XTIUSD 100 vs 1000) — **HANDLED**: BookExec.mqh:216 sizes off LIVE SYMBOL_TRADE_CONTRACT_SIZE so notional is correct (prices same magnitude ⇒ not a scale drift; shadow a/b keep baked contract for golden-matching multiples); VOLUME-grid drifts (JP225/SOL/XRP) HANDLED by live VOLUME_STEP/MIN/LIMIT; DE40 digits 1→2 = PRECISION → FIXED (FeedAssembler live branch: log + use live SYMBOL_POINT, offline FA_DIGITS path untouched); all 37 trade-mode FULL. EA + CheckFeedAssembler recompiled 0/0; offline feed mirror re-verified BIT-EXACT (max|diff| 0.0, all 24 quarters). | **PASS — no scale/contract corruption; the audit proved the exec layer already covers contract/volume via live SymbolInfo, isolating the digits guard as the sole real change.** | Owner re-runs the FableBookNative Strategy-Tester (now passes the digits guard) → position fidelity (fraction/notional) + R2. |
| **FMA3-RECON-8j** | 2026-07-15 | *n/a — tester harness fix, no trades* | freeze_hash unchanged | **Full-window R2 run (2020.01.01→2025.12.31) produced ZERO trades — diagnosed + fixed.** Log: init OK (refuse=no), full window elapsed, but `hours=0 unready=0 segs=0` — the per-hour book handler never fired once. Root cause (tester-only): cold-start floors the poll cursor at D'2020.01.01' (FableBookNative.mq5:712); PollBars advances the book only when the min-front `safe`=min(g_resolved) over all 33 symbols reaches that floor; **SOLUSD has no data before 2022** (Solana not yet born), and the SERIES_FIRSTDATE skip-clamp cannot fire when a symbol's birth is in the FUTURE vs modeled time → CopyRates(SOL,2020)=n<0 → SOL's cursor pinned below the floor → `safe` never reaches it → AdvanceTo never called → hours=0 for the whole run. (H2-2025 worked because SOL's 2022 birth was in the past, so the clamp fired.) FIX: in the tester (all history pre-synced in OnInit), treat CopyRates n<0 as an empty range and advance the cursor (crawl) so a not-yet-born leg never pins the front; live path (g_fedLive) unchanged. Recompiled 0 errors/0 warnings. | **BLOCKED → FIXED (compile-clean); empirical re-run pending.** | Owner re-runs the full-window ST; expect hours>0, SOL absent 2020-2021 (matches the record engine), trades from 2020. | 
| **FMA3-RECON-8k** | 2026-07-15 | full-window R2 (2020-2025, ICMarketsEU real M1, 1m-OHLC) | freeze_hash unchanged | **First full-window run + two findings.** (1) **b-freeze FIXED:** SOLUSD unlisted before 2022 made every 2020-2021 row unready (all-seeded gate), freezing the Sat sleeve b at 1.0 while the golden b grew 1.09->5.7x — so the EA missed 2020-2021 Sat gains and reached EUR3.0M vs golden EUR3.87M. Fix: FeedAssembler m_absent[] excludes a not-yet-born symbol from the readiness gate until its first real bar (EA MarkAbsent on empty warmup CopyRates, tester-only; Apply clears on real data). SatEquityNative.Step already carries has_bar=false legs safely (line 242). Recompiled 0/0. (2) **DD forensics:** EA worst DD 25.1% vs golden 20.7% (+4.4pp) is the SAME Oct-Dec 2022 macro episode (Oct-21 BoJ yen intervention + Nov FTX/CPI) in BOTH curves, same peak date, ~4-6pp deeper across all top-3 episodes = real-execution friction multiplier, no margin call / feed spike / symbol blowout (Core sleeve a_h -17.6% led it). | **Clock+freeze mechanics now correct; position fidelity 69 mismatches/6y (~perfect); post-2022 CAGR retention ~95%% (matches ~96%% prior); DD +4pp = expected friction.** | Owner re-runs full-window: verify b_h evolves 2020-2021 (~golden 1.09->5.7), then golden comparison. | 
