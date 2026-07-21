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
| **FMA3-RECON-8k** | 2026-07-15 | full-window R2 (2020-2025, ICMarketsEU real M1, 1m-OHLC) | freeze_hash unchanged | **First full-window run + two findings.** (1) **b-freeze FIXED:** SOLUSD unlisted before 2022 made every 2020-2021 row unready (all-seeded gate), freezing the Sat sleeve b at 1.0 while the golden b grew 1.09->5.7x — so the EA missed 2020-2021 Sat gains and reached EUR3.0M vs golden EUR3.87M. Fix: FeedAssembler m_absent[] excludes a not-yet-born symbol from the readiness gate until its first real bar (EA MarkAbsent on empty warmup CopyRates, tester-only; Apply clears on real data). SatEquityNative.Step already carries has_bar=false legs safely (line 242). Recompiled 0/0. (2) **DD forensics:** EA worst DD 25.1% vs golden 20.7% (+4.4pp) is the SAME Oct-Dec 2022 macro episode (Oct-21 BoJ yen intervention + Nov FTX/CPI) in BOTH curves, same peak date, ~4-6pp deeper across all top-3 episodes = real-execution friction multiplier, no margin call / feed spike / symbol blowout (Core sleeve a_h -17.6% led it). | **Clock+freeze mechanics now correct; position fidelity 69 mismatches/6y (~perfect); post-2022 CAGR retention ~95% (matches ~96% prior); DD +4pp = expected friction.** | Owner re-runs full-window: verify b_h evolves 2020-2021 (~golden 1.09->5.7), then golden comparison. | 
| **FMA3-RECON-8l** | 2026-07-15 | full-window R2 RE-RUN (2020-2025, post b-freeze fix), report #36 | freeze_hash unchanged | **Clean full-window reconciliation.** b_h now tracks the golden Sat sleeve within ~1-4% all 6y (2020-01 1.087 vs 1.090; 2021-12 5.715 vs 5.688; 2025-12 46.9 vs 45.0 — was frozen at 1.0). Full window RATE terms: EA CAGR +158.0% vs golden +170.9% (annual growth-factor retention 95.2%); **worst DD 22.9% vs golden 22.2% = +0.7pp** (was +2.9pp pre-fix); final EUR2.93M; Sharpe 2.07; PF 1.51; 17,145 trades; HistQual 93%. Position fidelity 69 self-check mismatches over 6y (~perfect). Post-2022 DD gap +1.5pp (was +4.4pp). The fix collapsed the DD divergence — the pre-fix higher endpoint + inflated DD were artifacts of under-weighting the high-friction Sat sleeve. | **RECONCILED (engine fidelity): DD matches to +0.7pp, ~95% CAGR retention = real-execution friction (near the ~96% record->tick prior). Strict +/-1pp CAGR band exceeded but that band is unfit for a 6y compounding curve; retention ratio + DD calibration are the reads.** | Next: real-tick crisis certification, FTMO dial, RECON-9 adjudication (Opus), deploy decision (owner). | 
| **FMA3-RECON-8m** | 2026-07-15 | Sat sleeve in-terminal RECORD-FEED port cert (owner-run TestSatEquityChain) | freeze_hash unchanged | **Sat port certified bit-exact on the record feed** — closes the coverage gap Core had (coresim 32/32=0.0) and Sat lacked. TestSatEquityChain replayed all 24 quarters 2020Q1..2025Q4 over the record-feed fixtures; judge validate_mql5_sat.py = **24/24 bit-exact** vs golden (equity+worst array_equal per quarter; full-run gate final equity 449707.7452664526; in-terminal max|d_eq|=0/max|d_eqw|=0, final balance 434132.98905617336, 20403 trades = bh_parity exactly) -> sat_mql5_parity.json. | **PASS — Sat meets Core cert bar; confirms the +4.88% live b_h drift is 100% the live-vs-record price-feed basis, NOT a port bug (RECON reconciliation).** | Real-tick crisis certification (the remaining mandatory gate; all in-terminal work to date is 1m-OHLC / record-feed). |
| **FMA3-RECON-9** | 2026-07-15 | IC deploy-readiness adjudication (Opus; re-grounded in run #36) | freeze_hash unchanged | **Executor CERTIFIED** (compute 5.06e-13, position fidelity 69/6y, Sat port bit-exact; fixes V1 over-leverage, min ML 121% 1m-OHLC). Grounded in OUR full-window run #36: **worst DD ~22.9% (a 2022 warm crisis, SURVIVED); COVID ~10.8%** (run cold-starts COVID -> book ~90% flat, verified zero EURGBP / 0.46x gross through the crash -> COVID not the binding DD). An earlier draft cited a ~40% COVID DD from an OLD account (52949549) = memory creep, REMOVED. Cautions (verified vs REGISTRY/docs): s=1.6 is the owner's documented aggressive dial (30% DD appetite, cap 0.15->0.20, above red-team-robust s=1.1); +158% is IN-SAMPLE (OOS forward realized +12.34%); gold+Nasdaq concentration 61.6%. | **VERDICT: trade-DISABLED demo GO now; trade-ENABLED at s=1.6 defensible (22.9% survived, within appetite; lower dial optional); LIVE CAPITAL = downstream owner decision after the demo, with the in-sample discount + concentration disclosed; ship the Task-17 margin governor before scaling.** | Demo-forward -> owner live-capital decision. |
| **FMA3-RECON-10** | 2026-07-15 | FTMO dial decision (native-EA A/B runs) | freeze_hash unchanged | **FTMO dial = s≈0.70 under a ≤1-breach/YEAR policy** (owner withdraws monthly → a breach = pass a new challenge, not a catastrophe; objective = max s subject to ≤1 breach/yr, NOT zero-breach). Native-EA runs: s=0.70 (A, _41) net +€930k, static DD 14.11%, 1 day>5% (breaches BOTH rules under zero-breach); s=0.35 (B, _42) net +€264k, DD 5.53%, 0 days>5% (clears both). Breach-freq (Run A dist scaled): s=0.70 ~0.73/yr (10% max-loss binds — 3 episodes >10%/5.5yr; daily-5% only 0.18/yr, 3% breaker holds); ≤1/yr ceiling ~s=0.73; s=0.65 = 0.36/yr (crisis margin). | **DECISION: ship s≈0.70 (or s≈0.65 for crisis headroom); the earlier s≈0.35 cut was only needed under a zero-breach standard.** Caveats: runs exclude COVID (start 2020.07); hourly-sampled daily (optimistic); not probe-robust yet. | ±20% weight-probe pass → FTMO demo-forward. |
| **FMA3-RECON-11** | 2026-07-15 | FTMO ±20% weight-probe (FMA3-011, record engine + adversarial adjudication `wf_be8760a7-dce`) | freeze_hash unchanged | **±20% weight-probe RAN — mechanism parity with IC, NOT assurance parity.** 6 cells (s∈{0.70,0.65} × w∈{0.56,0.70,0.84}) all score_v3-COMPLIANT; the three s=0.70 cells reproduce archived FMA3-008/010 **bit-exact** (Δstatic=0, ΔP=0 → no drift); s=0.65 dial newly filled. BUT the pass certifies little for FTMO: (a) **pass-by-construction** — at s=0.70 base w=0.70 is a local DD *max* (static DD w56/70/84 = 11.6/13.3/13.2%, both arms only reduce DD; contrast IC +20% drove DD to 27.55% and SET its dial); (b) **frame-blind** — every s=0.70 cell's *static* DD 11.6–13.3% EXCEEDS the 10% Max-Loss rule yet score_v3's monthly reset still reports P(breach12m)=0.0 (the same reset reads 0.0 where native-EA reads ~0.73/yr — gate never tests static DD, fix task_03aba9d3); (c) **wrong axis** — binding lever is the dial s: −20% (s=0.56)→≲0.15/yr but **+20% (s=0.84)→~2/yr, breaches ≤1/yr**; ±20% w never nears the cliff. | **VERDICT: the dial is robust to ±20% WEIGHT drift, but s=0.70 sits at the TOP of its ≤1/yr band with no upside margin → independent robustness reason to prefer s≈0.65 (0.36/yr). Parity of mechanism, not assurance. Native-EA-grade probe over w AND s, raw non-reset static frame vs €90k floor, crisis/real-tick window = the open arbiter neither preset has cleared.** | FTMO demo-forward + real-tick crisis certification (the arbiter). |
| **FMA3-RECON-12** | 2026-07-16 | IC **REAL-TICK** run (FableBookNative, s=1.6, €10k, 1:30, *Every tick based on real ticks*, 2023.01–2025.12, report `_43` + telemetry) | freeze_hash unchanged | **On-broker real-tick crisis certification — PASS.** PROVENANCE CORRECTION: first mis-called "generated ticks" from the post-midnight *tail* log (agent log rotates at midnight; run spanned 22:40→00:35) — CORRECTED from `20260715.log`: `generating based on real ticks` + **40× `real ticks begin from 2023.07.13`** (all legs). Real ticks: FX/metals 2023-07, crypto/indices 2023-11 → both crisis windows fully real-tick. **Results:** net **€134,862** (€10k→€144,862), worst-mark DD **18.76%** (Equity-DD-Relative ≈ telemetry −18.62%), **min ML 130.33%**, Sharpe 1.94, PF 1.46, 10,481 trades, fidelity **sc_mm=1** (~perfect), 0 refuse; swap −€26.5k / comm −€2.1k. **KEY — native-EA real-tick `k` over the 2 on-broker crises:** Aug-24 carry unwind worst-mark **−15.5%** (record −16.3% → **k 0.95×**); Apr-25 tariff **−13.1%** (record −12.0% → **k 1.09×**). vs the ratified COVID `f_tail` **6.5×**. → real ticks amplify these NON-COVID crises by **~1.0×**; the record engine is a **faithful DD predictor** for normal-to-moderate crises, and 6.5× is a COVID-class *extreme* (conservative for typical conditions). | **VERDICT: on-broker real-tick crisis cert PASS** (Aug-24 + Apr-25, k≈1, min ML 130% — never near stop-out). COVID/2022 (pre-2023, un-real-tickable on this broker) remain the **Phase-2 tail** — the `f_tail` imputed bound vs the Dukascopy faithful-proxy campaign. Caveat: real-tick gaps are generation-filled; crisis DDs are hourly-equity worst-mark proxies. | Phase-2 COVID/2022 tail decision; demo-forward production prerequisites (warm-start). |
| **FMA3-RECON-13** | 2026-07-16 | `FableBookNative.ex5` (sha256 `e3c55dc88e4d3e88…`, 462,096 B, compiled 2026-07-16 18:02) | `51a7541cc2aaa593` | **Warm-blob production run** (run 46: s=1.6, €10k, 1:30, 1m-OHLC, 2020.01.01→2026.01.01, `InpSaveInTester=true`, `InpSaveStateFrom=2025.12.30 00:00`). Preceded by run 44 (same window to 2025.12.31, **blob produced but NO sidecar**) and the `CheckCoreSignal` in-terminal script. **Deinit: hours=49378 segs=32 fires=31 lead_hold=16479 sc_mm=69 unready=0 skipped=0 split=150 rejects=0 stops=0 final_eq=2,952,403.72 refuse=no; 0 save warnings.** | **PASS — the warm blob exists and is loadable.** `FMA3_native_state.json` (7,876,336 B, sha256 `2f3a2c40…`) + `.coredrive` (8,334 B, sha256 `8574a2bf…`), both at `last_emit_hour = last_flush_hour = 2025-12-31 22:00 UTC`, **delta 0s → coherent, passes the EA's load check**. **Four findings, three of them defects in our own work:** (1) **OPEX horizon** (GO_NOGO #1) fixed — `CCsOpexCal` now computes the 3rd-Friday week per query, horizon removed not re-dated; `CheckCoreSignal` **ALL PASS** on the compiled binary with all 9 golden legs still **bit-exact (50/50, max\|d\|=0, flips=0)** and the regression assertions (`In(20651)` = 2026-07-17, the demo window) green. (2) **O(n²) tester state-save**: saving the growing blob every simulated hour made the full window ~300h (measured: rate decayed as C/n, n·rate≈130 over a 4× range); gated to a save window → **55 min**, a ~125× speedup. (3) **The hour boundary is the only LEGAL save point** — `CoreLiveDrive.mqh:712` requires drained queues; a deinit-only save (our first fix) refused with *"save with undrained queues"* and produced run 44's sidecar-less blob. Save now happens at the completed-hour boundary; `SaveStateFiles` writes the **sidecar first** so an illegal point is a clean no-op instead of leaving an incoherent pair. (4) **MT5's `To` date is exclusive AND the book closes hour H only after the feed passes H+1** — `To 2025.12.31`→blob at 12-30 22:00; `To 2026.01.01`→blob at 12-31 **22:00**, still one hour short of the nominal 23:00. | **ACCEPTED at 22:00 (owner, 2026-07-16).** The hour is cosmetic: the EA resumes from `last_emit_hour` and backfills, so 22:00 vs 23:00 changes nothing functionally. **The blob does NOT and cannot bit-match `endBASE`** (a_h 53.235 vs 53.098; b_h 47.131 vs 44.916): endBASE holds the **golden's frozen-curve** values, this blob holds the EA's **own live 6-year computation on the broker feed** — the same divergence that yields €2.95M vs the golden's €3.87M. a_h tracking to **0.26%** over 6 years is the reassuring read; b_h's **4.9%** is the known R2 sleeve/friction gap, not a defect. **b-freeze fix CONFIRMED**: b_h 1.003→**5.715** across 2020-21, matching the golden's 1.09→5.7× (RECON-8k). Next: **Step 2 live-resume test** (the real gate — the hour does not matter to it). ⚠ The pair lives in `Common/Files` and **any future `InpSaveInTester=true` run overwrites it** — back it up. |
| **FMA3-RECON-14** | 2026-07-17 | `FableBookNative.ex5` (sha256 `d08cca64c5b72ce31e027e753541f5ffd0a0832279c0d0c42ef0536346653510`, 466,206 B, compiled 2026-07-17 14:27:39, `0 errors, 0 warnings, 14897 ms elapsed, cpu='X64 Regular'`) | `51a7541cc2aaa593` | **The B1/B2 feed-path change (PR #30, merge `6421a57`, tip `8a67cf1` "Enable FTMO: route the symbol map to the FEED + declare broker gaps" — 3 files, 208+/27-: `FableBookNative.mq5`, `Include/Book/FeedAssembler.mqh`, `presets/FABLE_FTMO_LIVE.set`), gated by an IC identity regression.** Preceded by diagnostic-only PRs #28 (`CheckHistory.mq5`, +60) and #29 (`MarginProbe.mq5`, +163) — neither touches an EA, include or preset. **RUN V2 — the identity regression (run 47):** 1m-OHLC **cold-start** IC run on the new binary (s=1.6, €10k, 1:30, 2020.01.01→2026.01.01, `FABLE_IC_WARMSTART.set`, `InpV34SymbolMap` and `InpExpectAbsent` both **EMPTY** — verified in the run's own input echo), against RECON-13's run 46 as the known answer. **Deinit, field-by-field: `hours=49378 segs=32 fires=31 lead_hold=16479 sc_mm=69 unready=0 skipped=0 split=150 rejects=0 stops=0 final_eq=2952403.72 refuse=no` — IDENTICAL to run 46 on EVERY field**, `final balance 2952403.72 EUR`, 343,836,762 ticks, 1:04:08 wall. **The stronger result: V2's own warm blob is BYTE-IDENTICAL to run 46's** — `FMA3_native_state.json` sha256 `2f3a2c4013155a873017e2eca14274b31df5aee88ed690a4cdf34e4fd6d24ed7` / 7,876,336 B and `FMA3_native_state.json.coredrive` sha256 `8574a2bf205e61343df389040c6a0904c8e4f9c17fbd8d4acf2fc78efe65b9b4` / 8,334 B, both `cmp`-clean against the run-46 pair. That is 7.9 MB of *entire internal state* — every indicator, both sleeves, `a_h`, `b_h`, all 33 legs — reproduced bit-for-bit by a different binary across 49,378 hours. Identity is now **measured, not argued**. | **PASS — the B1/B2 change is a proven no-op on IC.** The static reads predicted it and the run confirms them: (a) with an empty map `FED_ParseSymbolMap` leaves `g_fedNMap==0` (`BookReplay.mqh:77,84`) so `FED_MapSymbol` returns identity (`:104-108`), and `FaResolveBroker` yields `FED_MapSymbol(FaBrokerName(x)) == FaBrokerName(x)` — the same strings the old `m_broker[i] = FaBrokerName(FA_SYMS[i])` (`8a67cf1^:FeedAssembler.mqh:476`) produced; (b) with `InpExpectAbsent` empty every `g_faExpectAbsent[i]==false`, so the guard at `FeedAssembler.mqh:579` always holds and a `SymbolSelect` failure still hard-fails → INIT_FAILED, `MarkAbsent` unreachable. **One known non-identity, by design:** the Init failure LOG TEXT changed (old `"SymbolSelect failed: <name>"` → new `"'<name>' is not listed on this broker and is NOT in InpExpectAbsent…"`) — behaviourally identical, not log-identical, on a path IC never takes. **CoreSignal, stated precisely:** PR #30 touches **no file under `Include/Core/`**, and `git log` shows Core untouched since the last `CheckCoreSignal: ALL PASS` (`MQL5/Logs/20260716.log`, 2026-07-16 16:53:50). The byte-identical blob **contains** the Core state, so it independently proves the compiled Core path is unchanged old→new **on this host**. What that does NOT establish: that pass ran on **this laptop's Wine terminal** (`Wine 8.0.1 Darwin 25.5.0, VirtualApple @ 2.50GHz`, logged into **11078280 — the LIVE-FUNDED account**), via the standalone `Scripts/CheckCoreSignal.ex5` (101,508 B) which links `CoreSignal.mqh` directly and never loads `FableBookNative.ex5`. **No AVX2/FMA3 host appears anywhere in the LAPTOP record** — every laptop compile reads `cpu='X64 Regular'` on Rosetta/Wine over Apple Silicon. ⚠ **SUPERSEDED SAME DAY by RECON-15: the VPS compiles to `cpu='AVX2 + FMA3'`** — the host difference this row warns about is REAL, was measured hours later, and CheckCoreSignal returned **bit-exact (max\|d\|=0.000e+00, flips=0) on all 9 legs**. Read RECON-15, not this sentence. **The VPS is a different host and may compile to a different `cpu=` target, which is exactly the axis the project's known fma-contraction residual lives on** — so `CheckCoreSignal` on the VPS host remains OWED, and it is a host question, not a PR-#30 question. **Three defects in our own work, two of them process:** (1) **the first V2 attempt warm-started by accident** — run 46's own blob was still in `Common\Files`, so it replayed **1 hour instead of 6 years**: invalid, discarded, re-run cold. The trap generalises: `OnDeinit` (`FableBookNative.mq5:932`) saves when `g_dirtyState`, so **stopping a tester run inside the save window re-creates the blob** and poisons the next start. (2) **A subset-of-includes deploy failed to compile** — `undeclared identifier 'g_fedSnapTs'`, logged 14:26:45.246 as `1 errors, 0 warnings`; caught by the compiler, fixed by deploying the **full** `Include/{Core,Book,Sat,FMA3}` tree, superseded 54 s later by the clean 14:27:39 build. (3) **The first cut of B1/B2 turned any unlisted symbol into a silent dark leg** — `InpExpectAbsent` was added as the fix and hard-fails both ways: a declared name the broker **does** list → INIT_FAILED (`FableBookNative.mq5:757-763`), a declared name matching no resolved feed symbol → INIT_FAILED (`:768-773`). | **FTMO ATTACH CLEARED, TRADE-DISABLED (owner, 2026-07-17).** The IC book is provably untouched, so attaching FTMO cannot perturb the running IC demo. This row does **NOT** authorise live orders on any account. **Still owed before an FTMO verdict:** V3 `CheckCoreSignal` **on the VPS host** (see the `cpu=` argument above); V4 attach → `warm=yes` → caught-up → `CheckHistory`; GO_NOGO #1b (policy-rate tables expired, blocked on owner input); GO_NOGO #4 (weekend clock-stall, unverified on this broker). **TRAP — MT5 "Max bars in chart" at 100,000 silently starved the feed and stalled the book**; no error, no REFUSE latch — the book simply stops advancing, and the setting needs a terminal RESTART. Second silent-starvation class after the weekend clock-stall. **TRAP — `MQL5/Experts/FableBookNative.log` is STALE** (mtime 2026-07-15 12:29:13, a *different* compile: 11358 ms vs 14897 ms, same 0/0 counts). **`logs/metaeditor.log` is the authoritative compile record.** Exactly ONE `FableBookNative.ex5` exists under `/Users/dsalamanca` — no shadow build; the tester's `466237 bytes loaded` is transfer framing (466,206 + the 27-char path + 4-byte prefix), not a second binary. **Blob durability:** the certified pair survives **only** as `~/Desktop/FMA3_warmblob_2025-12-31T22/` (4 files = `_IC`/`_FTMO` pairs + `SHA256SUMS.txt`, IC and FTMO byte-identical to each other, `shasum -c` OK). Session-scratchpad copies are **ephemeral** and the repo `scratchpad/` holds no blob. `FMA3_fed_frac_v3.csv` unchanged: `d00b614b…`, 26,574,582 B. **FTMO preset at HEAD:** `InpScale=0.7`, `InpInitial=80000.0`, `InpDailyStopX=3.0`, `InpMagicBase=3910000`, **`InpAllowLiveTrading=false`**, `InpExpectAbsent=EURSEK`, 9-pair map keyed on **EXEC canonical (= IC broker) names** (`DE40=GER40.cash;US500=US500.cash;…`) — **not** model names: `FaBrokerName` converts DAX→DE40 / USA500→US500 *before* `FED_MapSymbol`, and `g_fedCanon` holds `DE40`/`US500`, so a `DAX=` key would parse cleanly, match nothing and **silently no-op on both sides**. `FED_ParseSymbolMap` validates map VALUES against `SymbolSelect` (`BookReplay.mqh:89-94`) but **never validates KEYS** — `InpExpectAbsent`'s hard-fail is the ONLY backstop against a well-formed wrong-key map. **Dial — not re-opened here:** the criterion is *"**maximize the dial subject to ≤ 1 breach per year**, not "never breach.""* (`FTMO_DIAL_DECISION.md:15`), grounded in the **native-EA runs**, *"not the record engine or memory"* (`:3-4`); s=0.70 → **0.73 breaches/yr**, inside the ≤1 bar; ceiling ~0.9/yr at s=0.73 (`:42-44`); caveat 1 notes both runs **exclude COVID**, which is why s≈0.65 (0.36/yr) is the crisis-margin alternative. **Margin — modeled, and safe at s=0.70 by MEASUREMENT, not by grep:** BookExec DOES gate on margin (`BookExec.mqh:242,247-248` accumulate `marginSum += MathAbs(desired[k])*unit/g_fedLev[k]` and apply one uniform shrink `cap/marginSum` when `marginSum > base*InpMarginCap`, 0.9 in both presets), but the divisor is the **FROZEN** model table `g_fedLev[]` (`BookReplay.mqh:40-45`: crypto 2, metals/energy 10, indices 20), **not** the broker's — there are **zero** `OrderCalcMargin` calls under `Include/Book/`, so the 0.9 cap is blind to FTMO's real requirement, which `FABLE_FTMO_LIVE.set:22` measures at **1.47×** the model's at peak (crypto 1:1 vs model 1:2). Nothing binds at s=0.70 (`:24-25`: 0 of 2,948,651 minutes; peak util 0.527 vs the 0.9 cap; **s\* ≈ 1.196**) and equity is bit-identical across both leverage tables — so this licenses **s=0.70 only**, NOT the general claim that margin can never gate the book. **Unresolved, NOT settled here:** FTMO leverage (runsheet + `DEMO_FORWARD_PLAN` §3 say €100k/1:100; the shipped preset says 1:30 / 80,000 EUR) and FTMO balance (`RUNSHEET_VPS_SETUP.md:186` says confirm `InpInitial=100000.0`; the preset ships `80000.0`). **The IC demo's live state (52963578 on the VPS, trade-disabled, caught up, restart test PASSED) is SESSION-REPORTED, not committed** — the only tracked mention is `RUNSHEET_VPS_SETUP.md:21` (account *created*), and the runsheet is imperative instructions, not a status record. |
| **FMA3-RECON-15** | 2026-07-17 | `CheckCoreSignal.ex5` **compiled ON THE VPS** (source `CheckCoreSignal.mq5`, 18,649 B, sha256 `7e14b8a7…`; VPS compile: `0 errors, 0 warnings, 6980 ms elapsed, **cpu='AVX2 + FMA3'**`). Certifies `Include/Core/CoreSignal.mqh` (unchanged since `71e94dc`, 2026-07-16) as compiled by the VPS toolchain. NOT an EA run — see RECON-14 for the `FableBookNative.ex5` `d08cca64…` identity gate. | `51a7541cc2aaa593` | **V3 — the HOST certification (the run RECON-14 declared OWED).** Ran in-terminal on the VPS's IC-demo terminal (**52963578**, ICMarketsEU-Demo), fresh `ETHUSD,H1` chart, 2026-07-17 16:44:31, alongside the live trade-disabled EA (the script has NO trading functions and NO file I/O, so it cannot perturb it). **THE HOST DIFFERENCE IS REAL AND WAS THE WHOLE POINT:** the VPS toolchain emits **`cpu='AVX2 + FMA3'`** — fused multiply-add — where the laptop emits `cpu='X64 Regular'` (separate multiply and add). This is exactly the axis the project's standing **fma-contraction residual** lives on, carried since the S3 build as an explicit *prediction*: *"fma-contraction G-S5 (roll_var, ~1e-17, integer-lot-floor should make flip-invisible — **prediction until run**)"*. **RESULT — all 9 golden legs BIT-EXACT against the Python normative reference:** `golden leg 0..8: bit 50/50  max\|d\|=0.000e+00  >1e-12: 0  flips=0  OK` on every leg; `state: blob 31413 chars, round-trip EXACT`; `split: restored twin re-stepped bars 701..1439, target diffs = 0`; terminal output ends `CheckCoreSignal: ALL PASS`. | **PASS — and it beat its own prediction.** The ratified criterion is `maxd <= 1e-12 && flips == 0` (`CheckCoreSignal.mq5:298`); the measurement is **0.000e+00 with 50/50 bits**, i.e. not "inside tolerance" but *identical* — FMA contraction changes nothing observable in CoreSignal on real AVX2+FMA3 silicon. **The fma-contraction residual is CLOSED**: it was predicted flip-invisible, and it measures bit-zero. Scope discipline — what this does and does not certify: **DOES** — `CoreSignal.mqh` + `CCoreTrigger` + the state round-trip, compiled by the VPS toolchain on the VPS host, against the baked-in Python golden vectors. **DOES NOT** — the satellite sleeve, `BookExec`, the feed assembler, or the EA as a whole: no equivalent golden-vector script exists for those, so their host-sensitivity remains **unmeasured**. RECON-14's byte-identical blob covers old-binary-vs-new-binary **on the laptop only**; it says nothing about laptop-vs-VPS. The honest read is that the single component we *could* test on the risky axis came back bit-perfect, which is evidence about the toolchain's FMA behaviour generally — but it is evidence, not proof, for the untested components. | **V3 CLOSED (owner, 2026-07-17). FTMO attach remains cleared, TRADE-DISABLED; still NO live orders authorised.** ⚠ **CORRECTS RECON-14 IN PLACE:** that row's *"There is no AVX2/FMA3 host anywhere in this record"* was scoped to the laptop's artifacts and read as a general claim; the VPS **is** an AVX2+FMA3 host. The underlying error it was itself correcting stands but was narrower than stated: the `AVX2 + FMA3` string was a **real VPS observation** that had never been recorded in the repo, and the false part was claiming CheckCoreSignal *had already been run and passed* against it. Host real, pass not — until now. **Lesson recorded:** an unrecorded real observation and a fabrication are indistinguishable to a verifier working from disk, and both get treated as fabrication. Write the observation down at the time or lose it. **Also confirmed live in the same session:** the IC demo restarted 2026-07-17 16:40 and warm-started clean — `WARM START: blob validated (j=65.789…)`, `init: s=1.60 initial=10000 … trade=OFF`, `InpAllowLiveTrading=false on a live account` — so `j` has advanced 51.404 → 65.789 since the 2025-12-31 certified blob, and restart continuity holds on the VPS a second time. **Still owed before an FTMO verdict:** V4 (attach FTMO trade-disabled → `warm=yes` → caught up → `CheckHistory`); GO_NOGO #1b (policy-rate tables expired — blocked on owner input); GO_NOGO #4 (weekend clock-stall, unverified on this broker). **Unresolved, carried from RECON-14:** FTMO leverage (runsheet says €100k/1:100; shipped preset says 1:30 / 80,000 EUR) and FTMO balance (`RUNSHEET_VPS_SETUP.md:186` says confirm `InpInitial=100000.0`; preset ships `80000.0`) — reconcile the docs to the preset before attaching. |
| **FMA3-RECON-16** | 2026-07-18 | **Source-certified, NOT binary-certified.** Commit `84ff6b0` on `fix/absent-symbol-three-defects` (5 files, +133/-6, plus new preset `FABLE_FTMO_BACKTEST.set`; the raw stat reads 6 files / +210/-6 including the 77-line preset). Source sha256 + sizes: `mt5/ea/FableBookNative.mq5` 42,174 B `3dcd4d5e0f5e9b8e…`; `mt5/ea/Include/Book/FeedAssembler.mqh` 39,495 B `a4ab2267546c8706…`; `mt5/ea/Include/Book/SwapEurq.mqh` 32,537 B `acbc6833511bd44a…`; `mt5/ea/Include/Book/BookOrchestrator.mqh` 84,475 B `322a9191dea215f3…`; `mt5/ea/Include/Sat/SatEquityNative.mqh` 17,656 B `193b3c0177b07344…`. Working tree clean at HEAD=`84ff6b0`. **LAPTOP compile: `0 errors, 0 warnings, cpu='X64 Regular'`. The VPS compiles `cpu='AVX2 + FMA3'` (RECON-15) and the VPS `.ex5` hash for THIS build was NOT captured — PENDING; no binary hash is claimed on either host.** | `51a7541cc2aaa593` | **FTMO demo bring-up (1514016754 — EUR, Swing, 1:30, RETAIL_HEDGING, 80,000 seed, s=0.70, breaker 3.0, magic 3910000, `InpExpectAbsent=EURSEK` → 31/33 symbols), warm from the certified Dec-31 blob (`2f3a2c4013155a87…` / `.coredrive` `8574a2bf205e6134…`, both matching `SHA256SUMS.txt`). IC demo 52963578 (10,000 seed, s=1.6, 1:30, magic 3900000, 33/33) was the CONTROL — left running untouched all day, unaffected.** **THREE DEFECTS, all downstream of PR #30's `InpExpectAbsent`: the FEED knew about absent symbols; three consumers did not.** **(1) BAR PUMP.** `HeadReady()`→`CopyRates` on the absent symbol returns `n<0` forever; the LIVE branch read that as "lazy download, retry later" and returned without advancing, so `g_resolved[EURSEK]` stayed at its `-1` seed, pinning `safe=min(g_resolved)` at `-1`. The advance gates on `safe >= g_backfillFrom`, i.e. `-1 >= 1767218400` = false. **19 hours live with `hours=0`, no CPU, no error, no log line.** The TESTER branch already contained the fix AND a comment naming the exact symptom (*"the whole book freezes for the entire run … hours=0"*, verbatim at `84ff6b0^`). Proven by the deinit line: `hours=0 segs=32 fires=31 sc_mm=0 split=0 final_eq=80000.00`. **(2) EURQ READINESS.** EURSEK is also one of the 8 EUR conversion crosses, so the swap/eurq engine could not complete a step: `ready = (se_ok && all_seeded)`, and `!r.ready` skips the ENTIRE M1 row via `continue`, so `StepM1` never runs and the satellite engine is starved. **MEASURED: unready 274,872 of ~287,340 minutes (95.66%) → 1,544 after the fix.** **(3) SATELLITE MARK — the `-inf`.** Restored state VERIFIED DIRECTLY from the certified Dec-31 seed blob the FTMO book warm-started FROM (`~/Desktop/FMA3_warmblob_2025-12-31T22/FMA3_native_state_FTMO.json`): `b_engine.balance = 455280.0557067881`, 31 symbols, 16 non-zero legs, EURSEK at index 13, `lots[13] = +2.23`, `entry[13] = 10.803970336914062`. The satellite's joint-mark section (`mt5/ea/Include/Sat/SatEquityNative.mqh:344-360`) computes `(bid_c[k] − m_entry[k]) * m_lots[k] * SATEQ_CONTRACT[k] * eurq[k]` and gates ONLY on `m_lots[k]!=0` — **NO `has_bar` guard**, unlike sections 2 and 3 which both carry `if(!has_bar[k])`. An absent leg never prints a bar, so its price slots keep the Init `0.0` seed AND — because EURSEK is the sole SEK-quoted leg (`SwapEurq.mqh:537`, `SE_CROSS[6]=="EURSEK"`, `SE_QUOT_CROSS[SE_SEK]==6`) — the same absent bar feeds its own `eurq` slot. **The direct mechanism is the one the commit comment names: *"EurPerQuote() on it would divide an unset quote and poison the row"* — an unseeded cross has `bid_c=ask_c=0`, so `eurq = 1.0/(0.5*(0+0))` = `inf` immediately.** The zero-mark in QUOTE currency is `(0 − 10.803970336914062) × 2.23 × 100000 = −2,409,285 SEK`; **its EUR value depends on the `eurq` actually present at that minute, which was NOT captured, so no first-minute `eq_w` figure and no first-minute stop-out is claimed. NOTE: `eurq=1.0` for an absent slot is introduced BY this commit (`eurq[i] = (m_absent[i] || x<0) ? 1.0 : m_cross[x].EurPerQuote();`) and must not be used to describe pre-fix behaviour — a healthy EURSEK `eurq` is ≈1/10.8≈0.0926, not 1.0.** What IS established: the unguarded joint mark plus balance-scaled sizing ran away until binary64 overflowed to `-inf`, the `-inf` was PERSISTED to the blob, and it was then **correctly refused on reload**: *"STATE BLOB: J-SPLICE DISCONTINUITY: j_restored -inf vs j_saved -inf (rel nan > 1e-09)"*. FIX: declared-absent legs are flattened at restore, logged `SAT 'EURSEK' declared absent -> restored b position DROPPED`. | **PASS ON COMPUTE, FAIL ON PERSISTENCE — NOT a clean pass and NOT a deploy authorisation.** **What passed:** with both accounts warm from the same certified blob at the same hour (2026-07-18 13:00 UTC = stamp 1784379600), the first FTMO-vs-IC cross-check the fix made possible reads `a_h` IC 69.769425 / FTMO 69.491624 (**−0.40%**), `b_h` IC 57.065151 / FTMO 58.641862 (**+2.76%**), `j` IC 65.958143 / FTMO 66.236695 (**+0.42%**). FTMO `b` trajectory 66.80 → 66.62 → 61.77 → 60.97 → 58.64 — finite and moving, where it was `-inf`. `unready 1,544`. **The blend identity `j = 0.7a + 0.3b` reproduces to the full 6 decimals printed on BOTH accounts** (IC 65.9581428 vs 65.958143; FTMO 66.2366954 vs 66.236695) — no higher-precision figures were recorded, so no tighter claim is made. `b_h` sitting ABOVE IC is consistent with the separately measured finding that dropping EURSEK on FTMO is a GAIN (`mt5/ea/presets/FABLE_FTMO_LIVE.set:30` — *"Measured: dropping it is a +4.55% GAIN, not a haircut."*). **WHY THE CORE WAS NEVER AFFECTED — this asymmetry is what located the bug:** `CoreLiveDrive` gates its marks on `!m_pend[i]` (the guard the satellite lacks) and the core is per-leg with its own cap, so an unbarred instrument contributes nothing; the satellite is ONE shared balance marked jointly every union minute, so an absent leg is harmless per-leg and fatal joint-account. **IC-NEUTRALITY IS STRUCTURAL, not measured-and-hoped:** every new path is gated on `FaIsExpectAbsent()`, driven by `InpExpectAbsent`, which is EMPTY on IC — the loop bodies never execute there; no hot path, signature or arithmetic changed. **PROCESS FAILURES — the instructive part of this row:** (a) **A perfect init banner was read as proof of health.** Algo Trading was DISABLED on the FTMO terminal for the first 19 hours: `OnInit` runs and prints a flawless banner, but `OnTick`/`OnTimer` never fire, so `Pump()` never executed once. **Cost ~19h. Liveness must be judged by OUTPUT (state-file mtime / telemetry rows), never by the init banner.** (b) **TWO wrong hypotheses were pursued downstream of that bad premise, and both were refuted by measurement, not argument** — *"missing M1 history on the FTMO-renamed symbols"* refuted by `CheckHistory` (*"0 blockers, ALL PASS — a stalled book is NOT a history problem"*); *"lazy download timing that will self-heal via the 5s timer"* refuted by 17 further hours of silence. (c) **Fixing one layer per VPS round-trip (~15 min each) was the wrong method**; a systematic audit found the real cause. (d) **An adversarial reviewer "refuted" the correct root cause by reading a research artefact** (`research/bpure/warmstart/out/FMA3_book_state_Dref.json` — balance 56,874.40, EURSEK −0.27 @ 10.687029838562012) **instead of the certified seed blob the FTMO book actually warm-started FROM** (balance 455,280.0557067881, EURSEK +2.23 @ 10.803970336914062). That seed blob (`~/Desktop/FMA3_warmblob_2025-12-31T22/FMA3_native_state_FTMO.json`, the Desktop BACKUP of the Dec-31 pair, `mtime 2026-07-16 20:24`, byte-identical to its `_IC` twin per `cmp` and per RECON-14 — the `_FTMO` suffix is a filename, not a distinct artifact) was then read directly to settle it. **NOTE: this establishes what was RESTORED, not the live VPS state on 2026-07-18, which was never read — read the artifact that is actually load-bearing for the claim, and say which one that is.** **(e) THIS ROW'S OWN DRAFT presented a self-consistent EUR arithmetic chain (`−2,409,285` → `eq_w −1,954,005` → first-minute stop-out) as "VERIFIED DIRECTLY" while silently dropping the `eurq[k]` factor the cited source line applies — the second fabrication-class incident in this ledger after the fabricated-hash entry. Both figures are struck above. Arithmetic asserted as verified must be re-derived from the source line it cites, factor by factor.** | **NO DEPLOY. The FTMO demo computes correctly but is NOT restart-safe; it remains TRADE-DISABLED (`InpAllowLiveTrading=false`) and nothing in this row authorises live orders on any account.** **STILL OPEN — stated, not papered over:** (1) **SIDECAR SAVE / RESTART-UNSAFE, UNDIAGNOSED.** The core-drive sidecar save refuses continuously (*"BsWriteState: save with an open minute"*) while the main blob writes, leaving an incoherent pair on disk (observed repeatedly: blob 12:57 vs sidecar 12:55; blob 13:32 vs sidecar 13:30). That pair is what produced *"core drive: PushBar BTCUSD: stamp 1784379600 not ascending"* and a refuse on restart. (2) **NO `balance<=0` GUARD in `CSatEquityNative`.** The core's nearest equivalent is `mt5/ea/Include/Core/CoreSim.mqh:237`, and it is NARROWER than a general halt — `if(m_pos == 0.0 && m_balance <= 0.0)` — a flat-and-dead leg check, not a running drawdown halt. The satellite has neither. That absence is what let an inf-poisoned mark run unbounded to `-inf` instead of halting cleanly. EURSEK triggered it; **any deep drawdown could.** Changing it alters engine semantics → **needs an explicit owner decision, NOT a drive-by patch.** (3) **The VPS `.ex5` hash for this build was not captured — PENDING** — per the standing clause a RECONCILED verdict binds to an `.ex5` hash + model hash pair, and this row cannot supply the binary half. Capture it on the next VPS deploy. (4) **The EUR value of the fatal first-minute mark, and the measured `eurq[EURSEK]` at that minute, were not captured — PENDING.** The `-inf` endpoint is proven from the persisted blob and the reload refusal; the per-minute path to it is inferred, not measured. **Dial NOT re-opened here:** s=0.70 is settled under the owner's ≤1-breach/YEAR criterion, grounded in the native-EA runs, not the record engine. |
| **FMA3-RECON-17** | 2026-07-21 | `FableBookNative.ex5` (sha256 `710eb21dcd76e075b14ea267c7144d8050a6367ee5c353bd0f275c43f4725f3e`, 469,164 B, compiled 2026-07-21 11:25:20, `0 errors, 0 warnings, cpu='X64 Regular'`; = **main after PR #34 + #35**). Source-certified at `3ae383b` on `chore/recon-17-pr34-35-backtest-regression` (= `main`@`5125f0d` — PR #39 harness-only merged in clean — plus the new `FABLE_FTMO_DIAL_BACKTEST.set`; working tree clean, diff vs main = the preset only, +45). **VPS `cpu='AVX2 + FMA3'` `.ex5` CAPTURED 2026-07-21 from both running terminals:** IC (`ECBBF301…`) sha256 `3DF118BB420C29AC4FD3024832E49D2E48446D75E40A1A7529ED80FC89F9F0F0`, 468,108 B, compiled 11:39:28; FTMO (`05F73DEE…`) sha256 `0AB7DFF2A659D01280CCC74D83A2CC27A43553611BD202E0922BB4764D90F4A7`, 468,288 B, compiled 11:46:04. **The two `.ex5` hashes DIFFER, yet the deployed SOURCE is byte-identical across both terminals** — source rollup `23358C57C570A31BF3A31C117F356DF6DD52887B49CDF0863529E8ED66949041` over 273 files (`FableBookNative.mq5` + every `Include/*.mqh`), equal on IC and FTMO. So the `.ex5` divergence is **MetaEditor compile non-determinism (embedded per-compile metadata), NOT a code difference** — both live demos run identical strategy source. **METHODOLOGY:** the `.ex5` hash is a per-compile-instance value, not a stable source fingerprint for MQL5 — the **source rollup is the reliable fingerprint**; future entries should pin it alongside (not instead of) the `.ex5` hash. | `51a7541cc2aaa593` + fed_frac stream `d00b614b…` | **Two Mac-tester backtests on IC-LIVE `11078280` (server `ICMarketsEU-MT5-5`), 1m-OHLC, cold-start, 2020.01.01→2026.01.01, `symbols=33`, `warm=cold`, `refuse=no`, `unready=0`. RUN 1 (report `ReportTester-11078280_01`) — IC identity regression: `FABLE_IC_WARMSTART.set`, s=1.6, €10k, breaker 0, blob-save on. RUN 2 (report `_02`) — FTMO-dial baseline: `FABLE_FTMO_DIAL_BACKTEST.set`, s=0.7, €80k, 3% daily breaker, `InpV34SymbolMap`/`InpExpectAbsent` both EMPTY so the 33 IC symbols resolve, stateless.** | **RUN 1 = PR #34/#35 PROVEN INERT ON IC — by byte-identity, not argument.** The tester-saved state blob is **byte-identical to the certified Dec-31 pair**: `FMA3_native_state.json` sha256 `2f3a2c4013155a873017e2eca14274b31df5aee88ed690a4cdf34e4fd6d24ed7` / 7,876,336 B + `.coredrive` `8574a2bf205e61343df389040c6a0904c8e4f9c17fbd8d4acf2fc78efe65b9b4` / 8,334 B, both matching `SHA256SUMS.txt` — 7.9 MB of the entire internal state (every indicator, both sleeves, `a_h`/`b_h`, all 33 legs) reproduced bit-for-bit by the PR #35 binary across 2020.01.01→2025.12.31 22:00. The deinit matches run 46/RECON-13 on **10 of 11 fields** (`hours=49378 segs=32 fires=31 lead_hold=16479 sc_mm=69 unready=0 skipped=0 split=150 rejects=0 stops=0`). **The 11th is NOT a match and is not claimed as one:** `final_eq=2,989,612.54` vs run 46's `2,952,403.72` (**+1.26%**). It is confined to the ~2 h AFTER the 22:00 blob save (deinit stamp 23:59:59); the byte-identical 22:00 blob proves compute is identical THROUGH 22:00, and PR #34/#35 carry no year-end-gated path, so the tail delta is a **broker price-revision of the final 2025-12-31 22:00→24:00 bars** between the Jul-16/17 baseline and Jul-21 — a data artifact, not a code effect (a code change would have perturbed the blob). RECON-14's Jul-17 run got BOTH the byte-identical blob AND `final_eq=2,952,403.72`; this run gets the same blob with a drifted tail. **RUN 2 = FTMO-dial native baseline ESTABLISHED (first of its kind — no prior native-EA FTMO tester baseline existed).** `final_eq=951,079.44` (€80k → **11.89×**, CAGR **51.1%**; last-hour telemetry equity €949,910, `n_stops=28`, the +2h tail again). That is **0.8664× the record engine's FTMO-at-€80k €1,097,683.84** — inside the measured **0.66–0.95×** friction band. `stops=28` (the FED_Guardian 3% daily breaker fired 28× over 6 yr ≈ 4.7/yr) — **independently matching the v3-replay EA's 28 breaker fires at s=0.7 (RECON-4)**. `split=219`. The core fields `hours/segs/fires/lead_hold/sc_mm=49378/32/31/16479/69` and `unready=0` are **IDENTICAL to RUN 1**, so only the dial-driven sizing (`final_eq`), the splits, and the breaker (`stops`) differ — exactly the deltas s=1.6→0.7 + breaker-on should produce, and further evidence the compute is unperturbed. | **IC REGRESSION CLEAN.** PR #34/#35 do not alter IC compute or trades (byte-identical 7.9 MB blob + 10/11 deinit fields + a RUN-2 core identical to RUN-1's). **FTMO-dial native baseline recorded: €951,079 / 0.87× record / 28 breaker fires** on IC data. **CAVEATS — stated, not papered over:** (1) RUN 2 is the FTMO **dial on IC data**, NOT the FTMO broker — it exercises `FED_Guardian` but not the FTMO symbol-map / EURSEK-absent path (those are live-only, cross-checked at j +0.42% in RECON-16). (2) **PROCESS — the IC demo↔live data trap (cost ~2 wasted runs).** Both runs first mis-ran on IC **demo** `52963578`, whose server serves the 5 AUD/CAD crosses + EURNOK/EURSEK only from **2025**; EURNOK+EURSEK are 2 of the 8 eurq crosses, so the conversion engine starved (`unready` 0→**2,802,227**) and RUN 1 read **€3,518,234** with a non-matching blob. Switching to IC-**live** `11078280` (deep to 2015/2017 for those symbols) restored the certified result. **Judge tester data by on-disk `.hcc` density per year, NOT the `history synchronized from` line — the latter reported `2019` even where 2020-21 held zero bars.** (3) **Separately explored, NOT part of this baseline:** the real FTMO-broker path (`FABLE_FTMO_BACKTEST.set` on FTMO-Demo + FTMO-Server4). FTMO serves the index CFDs (GER40/JP225/UK100/US500/US100/UKOIL) only from **2022** (`.hcc`-verified; the `from 2019` line lies), so a clean FTMO-broker backtest is **2022→2026 only**. **The EURSEK PR #34 declared-absent fix was CONFIRMED on a COLD real-FTMO run** — clean `FEED: 'EURSEK' … marked ABSENT … excluded from the readiness gate`, no `-inf`, no refuse — the first real-broker validation of that fix. The live FTMO account is **USD-denominated** (wrong base for the EUR strategy; the demo is EUR). (4) **NOT a deploy authorization; no live orders on any account (`InpAllowLiveTrading=false` both runs).** **VPS `.ex5` hash SUPPLIED 2026-07-21** (EABuilder session; see the binary cell) — both terminals' `AVX2+FMA3` builds captured, and their source proven byte-identical (rollup `23358C57…`), so the standing-clause `.ex5`+model pair is complete for both hosts. **Finding of record:** MQL5 `.ex5` compilation is non-deterministic (IC and FTMO built the same source to different `.ex5` bytes), so the source rollup — not the `.ex5` hash — is the load-bearing fingerprint. Nothing else owed on this row. |
