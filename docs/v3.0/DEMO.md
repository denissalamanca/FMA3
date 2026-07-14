# V3.0 demo deployment + monitoring plan — the faithful executor

**The operator's plan for the MT5 demo forward-test of FMA3 v3.0 — the release where, for the first
time, there IS a single FMA3 EA.** v1.0 shipped the *model* (a Python 1-minute worst-mark record
engine) executed live as two parent EA stacks plus a capital split. v3.0 ships
[`FableFederation_V3`](../../mt5/ea/FableBook.mq5) — one binary that *provably executes that
model* by replaying a precomputed, already-netted 33-symbol `fed_frac` stream and sizing each symbol
off account **balance**. This doc says exactly what to deploy (one EA, two presets, one stream), how
the two shipped dials map onto the single `InpScale` knob, what fingerprints to watch, the
pre-registered decision rules, and the definition of done. Model home / source of truth:
[`model/v3/`](../../model/v3/) — [README](../../model/v3/README.md),
[MODEL_SPEC](../../model/v3/MODEL_SPEC.md), [PINNED_INPUTS](../../model/v3/PINNED_INPUTS.md),
[EA_V3_DESIGN](../../model/v3/EA_V3_DESIGN.md), [RECON4_RESULTS](../../model/v3/RECON4_RESULTS.md).
Reconciliation protocol: [`research/protocol/RECONCILIATION.md`](../../research/protocol/RECONCILIATION.md).

Sibling docs (all `docs/v3.0/`): **DEMO** (this file). Dashboards live at
[`DASHBOARD_IC.html`](DASHBOARD_IC.html) and
[`DASHBOARD_FTMO.html`](DASHBOARD_FTMO.html) — the two presets reproduce those two
dashboards up to friction.

> **⚠ v3 is a REPLAY EA — it does not trade live as-is.** It executes a frozen `fed_frac` stream that ends **2025-12-31**. On a live demo today it would run out of targets and hold stale positions (keep-last-good). Live trading requires the **forward generator** (§ live-horizon caveat) — a service that recomputes the model's targets each hour on live data and appends them. Built for backtest/validation; the live wiring is a known, scoped, not-yet-done item.

> **All model numbers are in-sample RECORD reads (the frictionless 1-minute worst-mark engine, IC
> 2020–25). Achievable equity is 0.66–0.95× the record by dial/scale — every gap is a NAMED physical
> constraint the record engine does not model, not an EA defect.** The 1m-OHLC reconciliation
> (FMA3-RECON-4) is complete and RECONCILED; **MT5 real-tick + live demo are the remaining
> falsification tests.** If live diverges, the first suspect is the EA against its spec, not the
> market (RECONCILIATION §Investigation protocol).

---

## Where we stand (2026-07-12)

**FMA3 v3.0 is BUILT, adversarially reviewed, and 1m-OHLC RECONCILED.** The model is frozen at config
hash **`51a7541cc2aaa593`**, `w_v7 = 0.70`, `matrix = static_fed(0.70) × s`. The EA
`FableFederation_V3.ex5` (sha **`740da0ff…`**, after the volume-limit fix; runs 1–3 were on sha
`d516350b…`) replays the unified stream `FMA3_fed_frac_v3.csv` (sha `d00b614b…`, fmt=3) and holds the
model's exact target position — **position fidelity median `after/want` = 1.000, p10 = 1.000, in all
three RECON-4 runs**. Equity lands at **0.66–0.95× the record** by dial/scale; the gap is three named
physical constraints (below), not a defect.

**The model of record (frozen, reproduced to the euro by `model/v3/reproduce.py`):**

| Preset | Seed | Dial | Final equity | CAGR | MaxDD (worst-mark) | Extras |
|---|---:|---|---:|---:|---:|---|
| **IC** (H-RISK-1) | €10,000 | s = **1.6** compounding | **€3,872,872** | **+170.2%** | **22.58%** | Sharpe 2.465, crisis tail 8.12% |
| **FTMO** (H-RISK-2b) | €100,000 | s = **0.7** + daily breaker x=3.0% | **€1,332,404** | **+54.02%** | **13.33%** | 26 breaker fires |

**The RECON-4 reconciliation (v3 vs model; 3 MT5 runs, IC Markets acct 11078280, 1m-OHLC, HEDGING,
1:500 for reproduction; [RECON4_RESULTS](../../model/v3/RECON4_RESULTS.md)):**

| Run | Preset | Dial | v3 equity | Model | v3/model | Rejects | Fidelity (median `after/want`) |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | `FABLE_PARITY_S10` | s=1.0 | **€391,873** | €464,991 | **0.84** | 0 | 1.000 (33/33 symbols) |
| 2 | `FABLE_IC` | s=1.6 | **€2,552,962** | €3,872,872 | **0.66** | 0 (after volume-limit fix) | 1.000 |
| 3 | `FABLE_FTMO` | s=0.7 | **€1,265,541** | €1,332,404 | **0.95** | 0 | 1.000 (0 volume-capped) |

**VERDICT (FMA3-RECON-4): v3 is the faithful executor.** All 33 symbols trade — including the 7
Satellite-sleeve legs (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) that were silently dead in
v1/v2 via the EurPerQuote quote-currency bug — now revived by v3's unconditional full-map eurq. The
FTMO breaker fired **28** times vs the model's 26 (v3's worst-mark is marginally more sensitive —
conservative). Where v3 *can* place the order it holds precisely `fed_frac·s`; every euro of the
0.66–0.95× gap is one of the three physical constraints below.

**The operational headline flip from v1.0: there is now ONE FMA3 EA.** v1.0 was "two parent stacks
plus a capital split, nothing enforces w or s jointly." v3.0 is a **single binary, two presets** —
`InpScale` is the only knob that differs IC↔FTMO; w and the whole band/reseed stack are frozen inside
the replayed stream. The runtime configuration is one number per preset: **`InpScale = 1.6`** (IC) or
**`InpScale = 0.7`** (FTMO).

---

## The three physical constraints (why 0.66–0.95×, not 1.0×)

The record engine is **frictionless and unbounded**; a real account is neither. Every euro of the
equity gap is one of these three — measured, not mysterious. **None bind at the deployable FTMO dial
(Run 3, s=0.7, clean 0.95×).**

1. **Transaction friction** (spread + commission) — always present, compounds with leverage:
   **0.95× @ s0.7 → 0.84× @ s1.0 → 0.66× @ s1.6.**
2. **Broker `SYMBOL_VOLUME_LIMIT`** — a *capacity ceiling* that scales with account size. On this
   account: **XAUUSD 10, SOLUSD 1000, ETHUSD 100 lots.** Cost ~0–6% at €10k, **17–40% at €1M**;
   XAUUSD (tightest) binds first, past **~€2M/s** of book. So **the €3.87M IC-s1.6 record is not
   physically reachable on one retail account at that scale.**
3. **Broker margin** — v3's own cap (`0.9·balance` on the MODEL per-symbol leverage, which ≈ a 1:30
   account's per-symbol grant) self-limits the book. At **1:30, s=1.6** the full 2020–2025 backtest
   ran at **min ML 121%** — far above IC's 50% stop-out, ~11pp over the owner's ML≥110% floor. The
   old "s=1.6 not deployable at 1:30" flag was v1-over-leverage-specific and is **DISPROVEN for v3.**

At 1:30 the **margin** ceiling binds first and keeps the IC book small enough that **volume never
engages** — so margin, not volume, sets the IC dial. Volume is a large-account / high-leverage
capacity concern only; it never binds at FTMO scale (Run 3, 0 volume caps).

---

## Deployment config (exact)

1. **Open the demo account matching the reproduction.** IC path: an **IC Markets** MT5 demo,
   **Raw Spread (commission-based)**, **EUR**, **HEDGING** (the EA aborts on a netting account —
   `OnInit` requires `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`), seed **€10,000** (IC) or **€100,000**
   (FTMO). ⚠️ **Leverage is the reproduction-vs-deployment fork:** the RECON-4 reproduction ran at
   **1:500** so the model's per-symbol margin cap binds before the broker's; the **deployment**
   account is the owner's real leverage — **IC 1:30, FTMO 1:100.** v3's margin cap is
   account-leverage-independent, so s=1.6 gives the **same €2,552,962** at 1:30 as at 1:500 (only the
   min-ML headroom differs; see the dials).
2. **Install the stream.** The unified fed_frac stream lives at
   [`research/outputs/mt5/FMA3_fed_frac_v3.csv`](../../research/outputs/mt5/FMA3_fed_frac_v3.csv).
   Regenerate + install with `python3 scripts/export_book_frac_v3.py --install` (copies to MT5
   `Common\Files`). The exporter **hard-fails** unless (a) the re-parsed matrix reproduces
   `static_fed(0.70)` to < 1e-12 and (b) `--verify-engine` reproduces €3,872,872 (IC) and €1,332,404
   (FTMO) to the euro. Record the printed file **sha256 `d00b614b…`** in the RECON ledger row — the
   EA's header hash-gate rejects a stream whose config hash ≠ `51a7541cc2aaa593`.
3. **Compile the EA.** Build `FableBook.mq5` + `Include/FMA3v3/` in MetaEditor (expect
   **0 errors / 0 warnings**); confirm the `.ex5` sha256 is **`740da0ff…`** and record it. A changed
   `.ex5` hash re-opens all reconciliation gates (RECONCILIATION §Standing test).
4. **Market Watch — the 33-symbol union + the 8 EUR crosses.** The stream is already broker-mapped
   (`USA500=US500; DAX=DE40` applied at emit); the Core US-index sleeve trades **USTEC** (`InpUS500=USTEC`
   upstream). Ensure the 8 conversion crosses resolve: `EURUSD, EURJPY, EURGBP, EURCHF, EURNZD,
   EURCAD, EURNOK, EURSEK` (the full-map eurq; a missing cross makes any leg quoted in that currency
   skip-loud). Any symbol that fails `SymbolSelect` logs a WARN and simply does not size.
5. **Attach + load the preset.** Attach to an **M1 24/7-clock chart** (ETHUSD or BTCUSD — crypto so
   the H1 causal boundary ticks over weekends), enable AutoTrading, load the preset:
   - **IC:** [`FABLE_IC.set`](../../mt5/ea/presets/FABLE_IC.set) — `InpScale=1.6`,
     `InpInitial=10000`, `InpDailyStopX=0.0` (breaker off).
   - **FTMO:** [`FABLE_FTMO.set`](../../mt5/ea/presets/FABLE_FTMO.set) — `InpScale=0.7`,
     `InpInitial=100000`, `InpDailyStopX=3.0` (daily breaker).
   Both keep the engine constants byte-fixed: `InpMarginCap=0.9`, `InpRebalBand=0.25`,
   `InpMagicBase=3900000` (one magic per symbol, `+idx+1`).
6. **Day-1 checks:** `OnInit` prints `symbols=33`; every symbol resolves (no `SymbolSelect` WARN); the
   config-hash / fmt gate passed (EA did not `INIT_FAILED`); `fma3v3_decisions.csv` is being written
   to `Common\Files`; every open position's magic resolves to exactly one symbol; **rejects = 0.**
7. **Record in the track record (MANDATORY — RECONCILIATION §Standing test):** deploy date, account
   id, leverage, the preset file, the EA `.ex5` sha `740da0ff…`, the stream sha `d00b614b…`, and the
   config hash `51a7541cc2aaa593`. **No EA deploys without a recorded, dated `FMA3-RECON-N` ledger
   entry for its exact `.ex5`+model-hash pair.**

---

## The two dials — one `InpScale` knob (the deployment decision)

There is no per-book arithmetic to do at deploy: w and the entire band/reseed/sleeve stack are frozen
inside the replayed stream, and shared symbols are already netted. **`InpScale = s` is the whole
dial.** The two shipped presets and their deployment status:

| Preset | Ship dial | Account / leverage | Reproduced equity | Margin fingerprint | Status |
|---|---|---|---:|---|---|
| **IC** | **s = 1.6** | €10k / **1:30** | **€2,552,962** (0.66× record) | **min ML 121%** (IC stop-out 50%; ~11pp over the ML≥110% floor); worst-DD 22.6% | **OWNER-ACCEPTED 2026-07-12, PROVISIONAL** — pending a real-tick intra-bar **min-ML > 110%** confirm |
| **FTMO** | **s ≈ 0.5 (recommended)** | €100k / **1:100** | (sweep) ret/DD **4.78**, worst-DD **7.8%** | margin a non-issue at 1:100; the −10%/−5% rules govern | **PROVISIONAL** — pending a 1:100 confirm run (`FABLE_FTMO_S04/05`) |

Three honest notes on those dials:

- **IC = s=1.6 is owner-accepted but PROVISIONAL.** The reproduction proves the *margin* channel is
  survivable at 1:30 (min ML 121% across the full 2020–2025 backtest, same €2,552,962 as 1:500 because
  v3's cap is leverage-independent). It is *near* the owner's ML≥110% self-limit (~11pp over), so the
  remaining test is whether **intra-bar** real-tick min-ML holds > 110% — a 1m-OHLC bar can hide a
  deeper wick than its low/high marks. Until that real-tick run confirms, s=1.6 is provisional.
- **FTMO's shipped s=0.7 is a scoring dial, not the recommended live dial.** The volume-cap s-sweep
  puts ret/DD at its peak **s=0.5** (4.78, worst-DD 7.82%) vs s=0.7's (4.05, 13.33%); the warm-COVID
  honesty flag says s=0.7 + the 3% breaker **breaches the −10% rule by 7.5–10.8pp** in a warm-start
  crisis (crisis-safe dial ≈ s0.30–0.35). So the demo runs **s≈0.5** — safer DD, same clean 0.95×
  fidelity class, and volume never binds at €100k. `FABLE_FTMO.set` (s=0.7) stays the *dashboard-
  reproduction* preset; `FABLE_FTMO_S05.set` is the deployment candidate.
- **The stream is dial-agnostic — `s` is NOT baked into the file.** One `FMA3_fed_frac_v3.csv` serves
  both presets; changing the dial is a one-line preset edit, never a re-export or rebuild. The
  s-sweep presets already exist: `FABLE_IC_S06/07/08.set`, `FABLE_FTMO_S04/05.set`.

---

## Staged validation status (per campaign protocol)

The staged plan (EA_V3_DESIGN §6) is: exporter self-check → compile → 1m-OHLC smoke IC → 1m-OHLC smoke
FTMO → real-tick → RECON-4 verdict. **1m-OHLC smoke first; real-tick only after mechanics pass.**

| Stage | Gate | Status |
|---|---|---|
| 1. Exporter self-check | stream reproduces `static_fed` to 1e-12 AND record engine on the stream = €3,872,872 / €1,332,404 (pure Python) | **PASS** |
| 2. Compile | v3 headless 0/0, sha256 → RECON row | **PASS** (`740da0ff…`) |
| 3. 1m-OHLC smoke, IC | per-bar held-fraction == `fed_frac·s` assert; final equity + friction ratio vs €3.87M | **PASS** (0.66×, fidelity 1.000, 0 rejects after volume-limit fix) |
| 4. 1m-OHLC smoke, FTMO | same + breaker fires ~26× on prev-day-close anchor | **PASS** (0.95×, fidelity 1.000, 28 fires) |
| 5. Real-tick | after smoke passes; then the RECON-4 dial verdict | **IN PROGRESS** — IC 1:30 real-tick run (~1h) for the intra-bar min-ML > 110% confirm; FTMO 1:100 sweep (`S04/05`) pending |
| 6. Live demo | this document — the first data v3 was never fitted on | **NOT STARTED** |

The **1m-OHLC reconciliation is complete and the verdict is RECONCILED** (FMA3-RECON-4, deployable):
v3 faithful, position fidelity 1.000 all runs, 33/33 symbols, equity 0.66–0.95× by the three physical
constraints. The **real-tick and live-demo falsification tests remain.**

---

## Scaling past the volume ceiling (the €2M/s capacity wall)

The IC record compounds past the point where **XAUUSD's 10-lot limit** caps its target at ~half the
model — the €3.87M is a frictionless ceiling, not reachable on one retail account at that scale. Two
owner-raised levers, both valid, decided *before* the book grows into the wall — not during a crisis:

1. **Higher-tier account** — a larger `SYMBOL_VOLUME_LIMIT` per symbol; simplest, one terminal, one
   monitor. The capacity ceiling scales with the tier's limits.
2. **N parallel accounts at €C/N each** — each account holds **1/N** of the model position (under its
   per-account limit); the **aggregate = the full model**, so N accounts multiply every volume limit
   by N. Scales linearly; caveats: N terminals to run in lockstep, small-symbol min-lot bites only if
   €C/N gets small, and it's **pure capacity — no diversification** (all N run the identical stream).

The ceiling is a *capacity* problem, not a *dial* problem — the s-sweep shows ret/DD still favours
high s under the cap; the cap just lowers the whole curve (€1M/s1.4: 40% cap cost, ret/DD still 5.02).
**Below ~€2M/s, one account suffices** and this section is moot.

---

## Monitoring fingerprints (against the model + the RECON-4 runs)

The demo is "healthy" if live behavior tracks these fingerprints. **Judge on execution fidelity and
behavior, not weekly P&L.** The three monitoring fingerprints that make v3 unique — **position
fidelity, ML trough, reject count** — are first-class.

| Watch | Expected fingerprint (RECON-4 / model) | Red flag |
|---|---|---|
| **Position fidelity** (the defining v3 test) | per bar, per symbol, `after/want` ≈ **1.000** (RECON-4 median 1.000, p10 1.000, all 3 runs) — v3 holds precisely `fed_frac·s` | sustained `after/want` drift off 1.0 on a symbol that is NOT volume-capped → the EA is not executing the model; audit the EA vs spec **first** (RECONCILIATION §Suspect 1) |
| **ML trough** (the survival signal, not DD%) | IC s=1.6 @ 1:30: **min ML 121%** across the whole backtest (stop-out 50%). FTMO s=0.7: min ML **376%**, median **1346%** | IC live min ML trending toward the owner's **110%** floor → the intra-bar wick the real-tick run is checking; ML toward 50% is liquidation proximity |
| **Reject count** | **0** at both deployable dials (Runs 1 & 3, and Run 2 after the volume-limit clamp) | ANY nonzero `rejects` in `fma3v3_health.csv` → STOP and diagnose. Volume-limited spin (the pre-fix Run 2 pathology, 51,346 reject spins) or min-lot at small scale are the first suspects |
| **Symbol coverage** (Satellite revival) | all **33** symbols place ≥1 deal — including the 7 revived legs (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) | any of the 33 silent for the session → a `SymbolSelect` / eurq-cross failure (the exact v1/v2 dead-sleeve signature) |
| **FTMO breaker cadence** | fires **~26–28×** over the sample, on the **previous server-day CLOSE** anchor + worst-mark `eq_w`; flatten-all + halt to next rollover | breaker firing far more/less often, or anchoring on the wrong day → the Guardian re-anchor logic; a fire that does not flatten every leg |
| **Equity vs the friction class** | IC **0.66×**, PARITY **0.84×**, FTMO **0.95×** of the record — the friction ratio is the honest yardstick, NOT the €3.87M | live equity materially *above* its friction class (e.g. IC > 0.66×) → an over-leveraging or accounting error, investigate — a real account cannot beat a frictionless model (RECONCILIATION Gate 1) |
| **Compounding base** | sizing tracks `ACCOUNT_BALANCE` (realized cash), re-derived every M1 bar; the 0.25 band suppresses churn | sizing off equity (floating included) or failing to re-size intra-hour → the biggest IC-fidelity lever (EA build-log fix #2) |

**Where the numbers live:** `fma3v3_decisions.csv` (per-bar `net_frac / want / held / after / balance /
equity / margin_level`), `fma3v3_health.csv` (`version, scale, split_events, rejects, daily_stops,
final_equity, final_ML`), both in MT5 `Common\Files`; plus the account itself (equity, ML) and magic
attribution (`InpMagicBase 3900000 + idx + 1`).

---

## Decision rules (pre-registered)

The demo is a falsification test, not a tuning loop. These map onto the RECONCILIATION gates (which are
per-preset; IC and FTMO reconcile on separate runs against separate thresholds).

1. **Position fidelity breaks** (`after/want` drifts off 1.0 on a non-volume-capped symbol): STOP.
   This is v3's defining invariant — if it fails, v3 is no longer executing the model. **Audit the EA
   against its design first** (RECONCILIATION §Suspect 1, the anti-overfit guardrail: an EA change is
   legitimate ONLY if it fixes a provable code-vs-spec mismatch — "it moved the numbers closer" is a
   symptom, never a justification).
2. **`rejects` > 0, `config_hash_mismatch`, or the HEDGING `INIT_FAILED` guard fires:** STOP and
   diagnose. These are execution/plumbing faults, not market signals.
3. **IC — min ML approaches the owner's 110% floor** (the real-tick intra-bar test): this is the
   *provisional* condition on s=1.6. If real-tick min ML holds > 110%, s=1.6 is confirmed; if it
   dips below, **step the IC dial down** the pre-built ladder (`FABLE_IC_S08/07/06.set`, s=0.8→0.7→0.6)
   — a one-line preset edit, no rebuild. **Never step s up.**
4. **IC — worst-mark DD ≥ the owner's 30% ceiling** (band 20–30%; model worst 22.58%): halt new
   entries and INVESTIGATE — no scale-up rescue, no re-tune.
5. **FTMO — any daily-rule proximity** (worst-mark day approaching the −5% daily or −10% static rule):
   the internal 3% breaker should fire first (it is *tighter* than the FTMO 5% rule by design). If the
   breaker is not protecting the account, **cut the dial toward the crisis-safe s0.30–0.35 band** — the
   warm-COVID flag is explicit that s=0.7 breaches −10% in a warm crisis. Recommended demo dial is
   already s≈0.5.
6. **Anything looks better than the model:** do **not** step s up. A real account beating a
   frictionless record is a modelling/accounting error to investigate (RECONCILIATION Gate 1,
   `R > 1.05` ⇒ INVESTIGATE), not a mandate to add leverage.
7. **The volume ceiling engages** (XAUUSD capping as the book grows past ~€2M/s): do NOT force the
   order or re-tune the dial — execute the **scaling decision** (higher tier / N accounts) made ahead
   of time, or accept the capped curve. The cap is physical; retrying it is the Run-2 spin pathology.
8. **Any deviation is logged to the track record** so the forward evaluation never silently compares a
   degraded live book to the frozen model. **Every new `.ex5` hash re-opens all six reconciliation
   gates** under a new `FMA3-RECON-N` entry before it may deploy.

---

## Honest caveats

- **Everything validated is in-sample (IC 2020–25), on a frictionless 1-minute worst-mark engine.**
  The model equities (€3.87M IC, €1.33M FTMO) are RECORD reads, **not deployable promises.**
  Achievable equity is **0.66–0.95× the record** by dial/scale — and the RECON-4 reconciliation itself
  was **1m-OHLC, not real-tick.** MT5 real-tick + the live demo are the only falsification tests left.
- **IC s=1.6 is owner-accepted but PROVISIONAL.** It is disproven-undeployable on the *margin* channel
  (min ML 121% at 1:30) but sits only ~11pp above the ML≥110% floor; the intra-bar real-tick min-ML
  confirm is outstanding. A 1m-OHLC bar can hide a deeper wick than its marks — real-tick traverses it.
- **The €3.87M IC-s1.6 record is not physically reachable on one retail account at scale.** XAUUSD's
  10-lot limit caps it past ~€2M/s. The deployable IC figure is **€2,552,962** (0.66×), and reaching
  the model aggregate needs the higher-tier or N-account scaling lever — a deliberate decision, not an
  assumption.
- **FTMO carries a compound-vs-withdraw contradiction and a cold-start crisis gap.** The €1.33M is
  fully-compounded never-withdraw equity; the 5/5 rule-compliance gates are scored under a contradictory
  monthly withdraw-to-base frame — both cannot hold at once. And the gates are cold-start in-sample:
  **warm re-validation breaches COVID by 7.5–10.8pp of the 10% rule**, which is why the demo dial is
  s≈0.5, not the dashboard's 0.7.
- **The joint 0.5·margin_used stop-out is delegated to the broker, not implemented in v3.** In-sample
  `eq_w` never falls below 0.5·margin_used (IC worst DD 22.6%, FTMO 13.3% — nowhere near ~50%), so the
  omission is immaterial to the reproduction; RECON-4 asserts it. Live-crisis fidelity may later demand
  the exact engine stop-out be added.
- **The frozen stream ends 2025-12-31.** Live trading past it needs a forward Core-signal recompute +
  stream extension (documented, not built) — the demo runs on the frozen 2020–2025 replay until then.
- **RECONCILED ≠ VALIDATED.** RECON-4 certifies *engine fidelity* (the record engine and the MT5
  engine execute the same frozen model faithfully). It is structurally incapable of detecting
  overfitting and says nothing about out-of-sample generalization — that stays with the never-fitted
  2026 holdout and this demo as separate, mandatory gates.

---

## Weekly monitoring

A scheduled Monday check: **(a)** position fidelity — `after/want` distribution per symbol from
`fma3v3_decisions.csv` (median must hold ≈1.000 on non-capped legs); **(b)** survival — the ML
trough and `rejects` count from `fma3v3_health.csv` against the RECON-4 fingerprints (IC min ML vs the
110% floor; FTMO breaker fire count and anchoring); **(c)** coverage — all 33 symbols placing deals,
the 7 revived legs alive; **(d)** the friction ratio — live equity vs its 0.66/0.84/0.95× class, never
vs the €3.87M record. Judge on execution fidelity, **not** weekly P&L. The clock starts once the EA is
actually filling on the demo.

## Before real capital (deferred hardening — do NOT do during the demo)

- **Complete the real-tick stage** (staged validation #5): the IC 1:30 intra-bar min-ML > 110% confirm
  and the FTMO 1:100 sweep (`FABLE_FTMO_S04/05`) — each a fresh `FMA3-RECON-N` ledger entry.
- **Fix the stale `FABLE_IC_S07/S06/S08` preset header comments** (they carry the s=1.6 IC header text
  while setting a lower `InpScale`) so a live operator is never misled by a preset banner.
- **Decide the scaling lever** (higher tier vs N parallel accounts) *before* the book approaches
  ~€2M/s, not during it.
- **Consider adding the exact engine 0.5·margin_used stop-out** if the real-tick crisis runs show the
  broker stop-out is not a faithful proxy.
- **EA-reliability pass** (append+flush logging, restart catch-up) and VPS deployment are pre-real-
  capital items, not demo items.

## Definition of done for the demo

The demo forward-test is **done** when, after **≥3 months** on the shared MT5 demo:

- **Runs cleanly throughout:** `rejects = 0` in `fma3v3_health.csv`, HEDGING guard never tripped, the
  config-hash / fmt stream gate green, `fma3v3_decisions.csv` written every bar, all 33 symbols
  (incl. the 7 revived legs) placing deals.
- **Position fidelity held:** per-bar `after/want` median ≈ **1.000** on every non-volume-capped
  symbol for the whole window — v3 provably executed the model live, not just in the tester.
- **The account stayed legal at its dial:** IC min ML held **> 110%** (real-tick confirmed) with
  worst-mark DD < the owner's 30% ceiling; FTMO's breaker protected the −5%/−10% rules with 0
  breaches; live equity tracked its friction class (0.66× IC / 0.95× FTMO), not the frictionless
  record.
- **Every disclosed deviation logged** to the track record, and the demo's `FMA3-RECON-N` ledger
  entries recorded for the exact `.ex5` sha `740da0ff…` + model hash `51a7541cc2aaa593` pair.

Then — and separately — the real-capital decision: a **distinct sign-off**, gated additionally on the
outstanding real-tick confirms and the scaling decision, not an automatic consequence of a clean demo.

---

*Sources: [`model/v3/README.md`](../../model/v3/README.md) ·
[`MODEL_SPEC.md`](../../model/v3/MODEL_SPEC.md) · [`PINNED_INPUTS.md`](../../model/v3/PINNED_INPUTS.md)
· [`EA_V3_DESIGN.md`](../../model/v3/EA_V3_DESIGN.md) ·
[`RECON4_RESULTS.md`](../../model/v3/RECON4_RESULTS.md) ·
[`research/protocol/RECONCILIATION.md`](../../research/protocol/RECONCILIATION.md) (FMA3-RECON-4) ·
[`mt5/ea/FableBook.mq5`](../../mt5/ea/FableBook.mq5) (`.ex5` sha `740da0ff…`) ·
[`scripts/export_book_frac_v3.py`](../../scripts/export_book_frac_v3.py) (stream sha `d00b614b…`) ·
[`scripts/sweep_s_volcap.py`](../../scripts/sweep_s_volcap.py) · presets `mt5/ea/presets/FED_V3_*.set`.
Config `51a7541cc2aaa593`, `w_v7 = 0.70`. All model numbers are in-sample RECORD reads; MT5 real-tick +
live demo are the remaining falsification tests; achievable equity is 0.66–0.95× the record by
dial/scale.*
</content>
</invoke>
