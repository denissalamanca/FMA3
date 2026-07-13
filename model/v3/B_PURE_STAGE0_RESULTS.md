# B-pure Stage-0 results — freeze, feed-provenance, P1c kill-switch, and the port go/no-go

**Scope.** This document synthesizes the measured results of **Stage-0** of the
proposed all-native-MQL5 "**B-pure**" port of the v3.4 book (the `V34_REFACTOR_ASSESSMENT.md`
§9 plan). Stage-0 = the cheap **kill switch**: **Stage 0 (freeze)** + **Stage 1
(primitives)** + **Stage 2 (P1c numeric gate)**, plus the separately-scoped
**feed-provenance probe** (§10 "do now regardless"). These ~6 developer-days are
run *before* committing to the ~28–40-day full port so that a fatal blocker is
found cheaply.

Every number below is **measured** on real frozen-cache series or the record
engine of record (`account_engine_1m`, 1-minute worst-mark, EUR 10k). Where a
quantity could **not** be measured with data on hand, that is stated explicitly
with the exact blocker — nothing is estimated and presented as measured.

Ledger entry for this work: **FMA3-RECON-6** (appended to
`research/protocol/RECONCILIATION.md`). The freeze itself is **FMA3-RECON-5**.

---

## 1. The freeze — `FMA3-v34-freeze-1`

**Freeze hash (source-byte token):**
`fc14159f5352d685214d3a417b0d71117dda300a7c7be02919daa83fd06c1446`
(sha256 over the concat of, for each of 16 sorted source files,
`utf8(relpath) + b'\x00' + raw_file_bytes`).
Snapshot dir: `model/v3/freeze/FMA3-v34-freeze-1/`.
Env: Python 3.13.12 / pandas 2.3.3 / numpy 2.4.2.

### 1.1 Pin reproduction — PASS to ≤ 1e-6

`build_c2() → account_engine_1m` (EUR 10k, 1m worst-mark) reproduced against the
pin targets:

| Metric | Reproduced | Δ vs pin | Tolerance |
|---|---|---|---|
| CAGR | 0.8865880763 | **4.08e-11** | ≤ 1e-6 |
| Final EUR | 449,707.7453 | 3.35e-5 abs / **7.46e-11 rel** | ≤ 1e-6 |
| MaxDD_worst | 0.2167488591 | **5.15e-12** | ≤ 1e-6 |
| Sharpe | 1.8543172986 | — | — |
| negY / negQ | 0 / 1 | 0 / 0 | exact |

**`match: true`.** The frozen source set reproduces the shipped book to machine
precision.

### 1.2 Self-containedness — clean WITH ONE NAMED GAP (not fully hermetic)

16 files frozen (15 declared + 1 transitive dep `ea/tests/reference/targets.py`),
covering the 7 shipped sleeves + `mag_xau` overlay + `ensemble`/`core`/
`account_engine_1m`/`eval_v34_pin_s10` + `strategy_fable` + `ea/brain/{target_engine,
brain_config}`.

**Honest caveat (flagged, not measured-away):** the manifest declares **two
external framework deps that were NOT snapshotted** —
`NewStrategyFable5/config/settings.py` (imported by `core` as `from config import
settings as S`) and `NewStrategyFable5/engine/costs.py` (`from engine import costs`).
The freeze is therefore **not fully hermetic**: if either of those two files in the
read-only parent repo changes, the pin could move and the source-byte freeze hash
**would not catch it**. This is a residual freeze-integrity risk to close before the
port (snapshot or hash those two files too, or prove they are inert on the
`build_c2` path).

### 1.3 Source-of-truth resolution — the two §8 landmines are RESOLVED

- **Renorm helper QUARANTINED — confirmed.** `strategy_fable.build_portfolio_positions`
  divides by `Σweights = 0.826` (a 1/0.826 = **1.2107× hot** renorm). Measured:
  `build_c2` does **NOT** call it and does **NOT** renormalize by the weight sum
  (`build_c2_calls_build_portfolio_positions: false`,
  `build_c2_renormalizes_by_sum_weights: false`). The shipped path uses **RAW**
  weights (sum 0.826, cash-park 0.174 intended). A porter who followed the
  "authoritative"-looking helper would ship a book **21% too hot with no gate to
  catch it** — the freeze pins the correct path.
- **Gold cap DERIVED, not hardcoded — confirmed 1.80.** `structural_gold_cap =
  seasonal_weight × scale = 0.18 × 10 = **1.7999999999999998**`. Both the structural
  and effective brain cap read **1.80**; it is computed at load from frozen
  weights/scale, not hardcoded. The 4 stale `1.62`/`1.98` strings in the source are
  **COMMENTS only** (scale-9/11 era); the CODE computes `0.18×10=1.80` correctly.
- **Freeze token fixed the `config_hash` blindness.** The §8 critique was that
  `config_hash` (`48c09199fbf83d82`) hashes only `{schema, scale, sorted(weights)}`
  and is **blind** to the ~40+ per-sleeve indicator constants. The freeze correctly
  uses the **sha256-over-source-bytes** hash as the binding token, which *does*
  capture indicator-param drift. `config_hash` is retained only as a secondary
  descriptor.

**Verdict (§1):** freeze reproduces the pin to ≤1e-6, both source-of-truth
landmines resolved, freeze token correct — **with one open item**: the two
un-snapshotted parent-repo framework files must be pinned for a truly hermetic
freeze.

---

## 2. Feed-provenance — measured; NOT a blocker for IC record-reproduction

**The question B-pure's value hinges on:** does the record's reproduction depend on
the specific IC broker feed it was built and priced on? If a different broker's
feed moves the book materially, then a *bit-perfect* port still misses the record
(it runs a different live feed), and B-pure's "reproduces the record" value
collapses regardless of port quality.

### 2.1 IC feed-provenance delta = ZERO by construction

The PIN feed (`research_cache`) is **byte-identical** to the live IC 1m feed
(`bars_1m_ic`) resampled to hourly across all 37 symbols
(`mean|Δprice| = 0.0`, return corr = 1.0000), and `account_engine_1m` prices on that
same IC feed. The v34 book is **already built AND priced on the live IC broker
feed** — so for IC, feed provenance does **not** gate B-pure's record reproduction.

### 2.2 Independent-broker robustness probe (14/37 symbols, measured)

Swapping the **14** symbols that have Dukascopy coverage (of 37) for an
independent-broker feed and re-running through the engine of record:

| Metric | Hybrid (Duka-swap) | Δ vs pin |
|---|---|---|
| CAGR | 0.87972 | **−0.686 pp** |
| MaxDD_worst | 0.21769 | **+0.094 pp** |
| Final EUR | 439,985 | **−2.16 %** |
| Sharpe | 1.8329 | −0.021 |
| negY / negQ | 0 / 1 | gates intact |

The federation `fed[h,k]` moved by at most **11.1 %** of peak exposure
(`fed_delta_maxabs 0.421` vs `fed_pin_maxabs 3.804`). Position-reconstruction
fidelity on the swap was **0.0** (the pipeline rebuilds positions faithfully on the
swapped feed; the delta is entirely the price feed, not a pipeline bug).

**On the measured evidence the record is feed-robust — feed provenance is NOT a
Stage-0 blocker for B-pure.**

### 2.3 Honest blocker on the FULL-book measurement

A **full 37-symbol** independent-broker measurement is **not possible with data on
hand**. Only `research_cache_duka` (Dukascopy hourly, 2020–2025) is a genuinely
different broker feed, and it covers **14/37** symbols: AUDUSD, BTCUSD, DAX, ETHUSD,
EURGBP, EURJPY, EURUSD, GBPUSD, NZDUSD, USA500, USDCHF, USDJPY, XAGUSD, XAUUSD.
The remaining **23** symbols (all JPY crosses, EUR-Scandi, SOLUSD, XRPUSD, JP225,
UK100, US30, USTEC, XPTUSD, XTIUSD, XBRUSD, XNGUSD, AUDCAD, AUDNZD, CADCHF, CADJPY,
EURCAD, EURCHF, EURNOK, EURNZD, EURSEK, GBPJPY, NZDCAD, NZDJPY) have **no
independent feed**. `data/extended/*_M1_DUKA.parquet` cannot fill the gap — 11
symbols, only 2015–2020 (pin window is 2020–2025), no spread column.

**Export needed (owner action):** to measure full-book feed-provenance, export a
second independent broker's 1m or 1h bars for **all 37 symbols over 2020–2025**,
server-time stamped (GMT+2/+3 NY-anchored, hour-0 daily break), with o/h/l/c +
spread. Until then, feed-robustness is **established on 14/37 symbols, extrapolated
un-measured for the other 23**.

---

## 3. P1c kill-switch — PASS

**The make-or-break question:** can hand-rolled scalar float64 (== C/MQL5 `double`)
reproduce the pandas recurrences the book depends on, on **real** frozen-cache
series? If not, no faithful native port is possible and the whole port is a no-go.

### 3.1 Continuous recurrences reproduced to ~1e-14 (target was ~1e-8)

| Primitive | Max rel err | Verdict |
|---|---|---|
| `ewm_mean` (adjust=True, ignore_na=False, span 720, incl. interior NaN) | **4.50e-14** | PASS |
| `ewm_std` (adjust=True, bias=False, Welford-weighted, span 250) | **1.21e-15** | PASS |
| rolling `rstd` ddof=1 ring buffer (w=10/30/60, worst) | **1.44e-14** | PASS |
| `sma` rolling(w).mean() (w=50/200) | 4.82e-15 | PASS |

The EWM `adjust=True` path was verified against a copy with **4 injected interior
NaNs**, so the `ignore_na=False` decay-through-NaN branch is exercised, not just the
no-gap path.

### 3.2 Integer / discrete-state primitives reproduced EXACTLY (0 error)

| Primitive | Max rel err | Verdict |
|---|---|---|
| Donchian max/min (monotonic deque, min_periods=w, shift(1), n=20/55) | **0** | PASS (exact) |
| `to_hourly` (+1d shift, reindex(union).ffill(), lag1d) | **0** | PASS (exact) |
| daily finalize `resample('1D').last()` (contiguous grid) | **0** | PASS (exact) |

**So, to the task's precise question:** hand-rolled float64 reproduced
`ewm(adjust=True)` + `ddof=1` to **~1e-14 (better than the ~1e-8 target)**, and the
integer/monotonic-deque/resample state **exactly (0)**.

### 3.3 The two mandatory conventions are PROVEN by divergence, not asserted

The FAILMODE controls confirm these conventions are make-or-break, not cosmetic:

- `ewm_mean` with the natural **`adjust=False`** diverges **93.4 %** (max rel 0.934)
  from the required `adjust=True`.
- rolling std with **`ddof=0`** understates `ddof=1` by exactly `sqrt(9/10) = 5.13 %`
  on w=10.

Cross-checked against the full-book position impact (`numerics_audit`): getting
`adjust=False` wrong blows XAUUSD position by **0.675×equity on 17,160 rows**;
getting `ddof=0` wrong blows CADCHF/NZDCAD/EURCAD by **1.1×equity on 41,777 rows**.
The conventions are the single biggest traps and they are provably reproducible.

### 3.4 The MEASURED achievable gate residual (this sets the acceptance tolerance)

The continuous math is reproducible to ~1e-14 (≈ zero). The **irreducible**
residual is the **discrete-state-flip** channel: a correct float64 port and pandas
can land one discrete level apart at a tie (hysteresis states, the crisis 0.02
grid, the mag $100 magnet), and each flip is a state that persists weeks-to-months
and is amplified by the path/tail breach statistic.

To bound that channel we ran a **conservative feed-level proxy** (a 1e-9
multiplicative close-price perturbation — ~**5 orders of magnitude LARGER** than the
true ~1e-14 recurrence residual, injected upstream of everything) through the engine
of record + the house worst-mark-breach bootstrap:

| Gate metric | PIN | PORT-PROXY (1e-9) | Δ (measured) |
|---|---|---|---|
| CAGR | 0.88659 | 0.89466 | **+0.807 pp** |
| MaxDD_worst | 0.21675 | 0.21418 | **−0.257 pp** |
| Breach P(DD>30%) | 0.1208 | 0.1180 | **−0.28 pp** |
| p95 DD_worst | 0.33528 | 0.33365 | −0.163 pp |
| Final EUR | 449,708 | 461,372 | +2.6 % |

The design's own **float32 floor** (a benign, in-scope perturbation; maxabs 5.6e-5
position) still moved terminal EUR **−0.19 %** and the breach gate **+0.14 pp**
(0.1208→0.1222). The perturbation signature is a **persistent state flip, not
drift**: max per-symbol position delta is **identical (6.08e-2, XTIUSD) at 1e-9 and
1e-11**, and **0 "big" cell flips** at both.

**Measured residual bracket:** **ΔCAGR ≈ [0.06, 0.8] pp**, **ΔBreach ≈ [0.14, 0.28]
pp**, **ΔMaxDD_worst ≈ 0.26 pp**. The gate metrics the campaign decides on are
**not** reproducible to below this resolution — the port needs its **own** gate-level
re-validation, and "positions within ε" is the wrong criterion (there is no bounded-ε
regime for a discrete hysteresis vector).

**Critical honesty flag on this proxy:** the 1e-9 feed proxy conservatively bounds
the **continuous-accumulation** channel, but it does **NOT** bound the **MathRound
discrete-tie** channel (§6). A random feed nudge rarely lands *exactly* on a tie,
whereas MQL5's `MathRound` (half-away-from-zero) vs numpy's banker's (half-to-even)
disagree **systematically at exact ties** on the crisis grid and mag magnet. The
proxy therefore **under-samples** the one bias only an in-terminal run can measure.
The tolerance band in §5 is a *proposal*, valid only until an actual MQL5 run
confirms the residual on the tail.

---

## 4. GO/NO-GO on committing the full ~28–40 dev-day port

### 4.1 Stage-0 kill-switch: **GREEN (PASS)**

The three technical questions Stage-0 exists to answer all cleared:

1. **Freeze reproduces the pin** to ≤1e-6, source-of-truth landmines resolved. ✅
   (with the two un-snapshotted framework files as an open item)
2. **Feed provenance is not a blocker for IC** — the book is already built/priced on
   the live IC feed; the independent-broker probe moves it only −0.69 pp CAGR. ✅
   (full-book confirmation blocked on a 37-symbol export)
3. **Numerics are portable** — every make-or-break recurrence reproducible in scalar
   float64 to ~1e-14, integer state exact, both mandatory conventions proven. ✅

**No fatal technical blocker was found.** The numeric kill-switch did **not** fire.

### 4.2 Decision on the full port: **NO-GO / HOLD at this time**

Stage-0 passing removes the *technical-feasibility* risk. It does **not** flip the
strategic recommendation, which stays at **Option D** (`V34_REFACTOR_ASSESSMENT.md`
§10). Committing the ~28–40 dev-day B-pure port now is a **NO-GO**, gated on
**owner-input blockers that Stage-0 cannot resolve**:

- **The book is not frozen for production.** The FMA2 roadmap schedules **v2.2 = an
  11-year re-derivation** (2015–2025) with a pre-registered OOS promote/demote
  program — a wholesale re-fit, not a tweak. Porting now amortizes a large native
  investment against a **scheduled replacement**, and any un-frozen research edit
  re-fires port stages 3–8.
- **"Zero Python in the live loop" is not ratified as a hard mandate.** B-pure's
  *only* incremental win over the already-shipped, bit-identical Option D is the v34
  alpha — which is exactly the part the Strategy Tester **cannot fidelity-validate**
  (feed divergence) and which drags in the **uncosted `b_h` second engine** (a 296-
  line cross-margined 1m account, port stage 6) and the **worst-ROI carry_breakout**
  sleeve (0.046 weight, hardest mechanics).
- **Python is not eliminated even by a perfect port** — the reconcile/parity oracle
  (`build_c2` + `account_engine_1m` on the broker feed) is permanent by definition; a
  native replay cannot be its own oracle.

**Recommendation:** ship **D**; **do not start** the full B-pure port. Revisit B only
when **both** bind: (a) the v34 book genuinely freezes (sleeve churn stopped, stable
production tag, ideally after v2.2 lands), **and** (b) "no Python in the live loop" is
ratified as a hard mandate with the `b_h`/carry_breakout re-port cost accepted.

---

## 5. Recommended gate-level tolerance band — for the owner to RATIFY

Derived from the measured Stage-0 residual (§3.4). This is the **port-vs-record
numeric-equivalence** band (distinct from, and tighter than, the model-vs-MT5
reconciliation band in `RECONCILIATION.md`). It is a **proposal to RATIFY**, not a
ratified value.

| Gate metric | Measured worst (proxy) | Proposed accept band | Dangerous direction |
|---|---|---|---|
| **ΔCAGR** | +0.81 pp | **≤ ±1.0 pp (abs)** | either |
| **ΔMaxDD_worst** | −0.26 pp | **≤ ±0.5 pp (abs)** | **+** (port under-states DD) |
| **ΔBreach** P(DD>30%) | −0.28 pp | **≤ ±0.5 pp (abs)** | **+** (port under-states breach) |

Plus **hard sub-gates the port must pass before the above are even evaluated:**

- **Continuous-quantity parity** (vol, ewm mean/std, z-scores) ≤ **1e-8** on frozen
  bars (achieved 1e-14 in P1c — comfortable).
- **Integer / Donchian / grid / resample state:** **EXACT (0 tolerance)**; every
  state-sequence mismatch is a **finding to trace**, never averaged into an ε.
  Report as "N state-sequence mismatches over the 6y × instrument grid **plus the
  resulting gate delta**."
- **Tail cert:** the port must land inside the band **specifically on the COVID
  crisis tail** (the state-densest, most warm-sensitive region that dominates
  MaxDD_worst).

**Ratification caveat (binding on the owner):** the band above bounds the
continuous channel via an oversized proxy. It must be **re-confirmed against an
actual in-terminal MQL5 run** before it is treated as the true achievable residual,
because the Mac proxy cannot see the systematic MathRound tie bias (§6). If the
in-terminal run exceeds the band on the tail, the band is not "widened to fit" — the
port is a finding to trace.

---

## 6. Residual risks that STILL need in-terminal MetaTrader confirmation

The pure-double proxy is faithful for the recurrence algebra (§3), but **cannot**
close these — they require a real MQL5 terminal run:

- **R1 — MathRound tie-break (systematic).** numpy `.round()` is round-half-to-EVEN
  (banker's); MQL5 `MathRound` is round-half-AWAY-from-zero. They disagree **at exact
  ties**, one discrete level apart. **Measured** on frozen series: crisis `_GRID=0.02`
  snap at w=0.05 → numpy 0.04 vs MQL5 0.06 (a full 0.02 position-level flip); mag $100
  magnet at d=1250 → numpy 1200 vs MQL5 1300 (a $100 shift that flips long/flat band
  membership). This is a **systematic rule mismatch on the gate-dominating convexity
  sleeve** — confirm in-terminal.
- **R1b — tie-straddle via upstream ULP.** A value that "should" sit exactly on a tie
  lands just off it due to accumulated ULP differences in the upstream recurrence, so
  which way it rounds flips. Not reproducible on the Mac proxy.
- **Transcendental last-ULP.** `tanh` (trend_v2 6-lookback ensemble), `exp`/`pow` in
  the EWMA decay — MQL5's libm may differ from the platform libm in the last ULP,
  which near a discrete threshold can flip a state. Unmeasurable on Mac; must be
  observed in-terminal.

**None of these is a Stage-0 gate failure** — they are the reason the port carries a
mandatory **gate-level re-validation** rather than a "bit-identical" claim, and the
reason §5's band is provisional until an in-terminal run exists.

---

## 7. Staged next plan — each a hard go/no-go

Sequenced low-risk-first (`V34_REFACTOR_ASSESSMENT.md` §9). Stages 0–2 (this
document) are **DONE and GREEN**. Stages 3–8 are the ~28–40-day commitment and are
**BLOCKED on §4.2 owner-input** — do not start until the D→B gate is ratified.

| Stage | Work | Go/no-go criterion | Status / blocked on |
|---|---|---|---|
| **0 Freeze** | source-hash, golden parquets, RECON entry | pin ≤1e-6, SoT resolved | **DONE (green)** — open: snapshot 2 parent framework files |
| **1 Primitives** | 7 shared recurrences, unit-parity ~1e-8 | all primitives ≤1e-8 | **DONE (green)** — achieved 1e-14 |
| **2 P1c gate** | one-sleeve vol + full integer-state vs `build_c2` — **KILL SWITCH** | recurrences pass + state exact | **DONE (green)** — kill-switch did not fire |
| **3 Front block** | seasonal → mag_xau → intraday → crisis (~57% wt) | each state-sequence + gate-delta inside §5 band | **BLOCKED** on §4.2 + §5 ratification |
| **4 State-machine sleeves** | crypto_smart → meanrev → trend_v2 | hysteresis-state parity + warm-start | **BLOCKED** on stage 3 |
| **5 carry_breakout** | Donchian ×11×2 + policy rank + ties (or approved approx) | state-sequence parity; **or owner-approved approximation** (which re-opens the "~100% behavior" claim) | **BLOCKED** on stage 4 + owner decision on approximate-vs-exact |
| **6 `b_h` native engine** | port `account_engine_1m` (31-sym cross-margin, 1m intrabar) | parity vs `v34_book_equity_1m.parquet` | **BLOCKED** — needs the equity-1m golden export as its parity target; uncosted in prior plans |
| **7 Warm-state cert** | ≥2019 full-universe warm, 2020-boundary state diff, COVID MaxDD re-cert | boundary state diff traced; tail inside §5 band | **BLOCKED** on ≥2019 full-universe warm data availability (COVID cold-start k≈4.7 artifact) |
| **8 Blender + ST regression** | wire into Option-D blender, full Strategy-Tester regression | full-system gate pass | **BLOCKED** on stages 3–7 |

**Explicitly blocked on owner input (summary):**
1. **The D→B commitment itself** (§4.2): ratify (a) book-frozen-for-production window,
   (b) "zero Python live" hard mandate.
2. **The §5 gate-level tolerance band** — ratify before stage 3, re-confirm in-terminal.
3. **Full-book feed-provenance** — export a 37-symbol independent broker feed
   (2020–2025, server-time, o/h/l/c + spread) if full-book confirmation is required.
4. **Stage 6 `b_h`** — produce the `v34_book_equity_1m.parquet` golden parity target.
5. **Stage 7** — provide ≥2019 full-universe warm data.
6. **Stage 5** — decide exact-port vs approximation for carry_breakout (approximation
   voids the "~100% behavior" claim and forces a re-pin).

---

## 8. Bottom line

Stage-0 is **GREEN**: the freeze reproduces the pin to ≤1e-6 with both
source-of-truth landmines resolved, feed-provenance is not a blocker for the IC
record, and every make-or-break numeric primitive is faithfully reproducible in
scalar float64 (recurrences ~1e-14, integer state exact) with both mandatory pandas
conventions proven by divergence. The technical kill-switch **did not fire**.

But **GO on the full ~28–40-day port is NO-GO / HOLD** — not for a technical reason,
but because the governance gates stand: the book is not frozen for production (v2.2
re-derivation on the roadmap) and "no Python in the live loop" is not a ratified hard
mandate. **Ship Option D now; revisit B-pure only when both of those bind.** The
achievable gate residual (ΔCAGR ~[0.06,0.8]pp, ΔBreach ~[0.14,0.28]pp) and the
MathRound/transcendental last-ULP risks mean any future port carries a **mandatory
gate-level re-validation on its own output, on the COVID tail, in-terminal** — never
a "bit-identical" claim.

---
*Measured on: freeze `fc14159f…`, config_hash `48c09199fbf83d82`, py3.13.12 /
pandas2.3.3 / numpy2.4.2. Engine of record: `account_engine_1m` 1m worst-mark, EUR
10k. All Stage-0 result JSONs under the session scratchpad
(`fidelity_kill_result.json`, `feed_prov_*.json`, `measure_gate_result.json`,
`numerics_audit_result.json`, `summary.json`).*
