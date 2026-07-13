# v3.4 "brain2" refactor — can the book go fully native in MQL5?

**Question ratified for this assessment (2026-07-13):** can the v3.4 book (`brain2`) be *refactored* into a **causal, arithmetically-simple** form that is **fully implementable natively in MQL5** while preserving ~100% of its behavior? If yes, the all-MQL5 "**B-pure**" live architecture ([`DESIGN_COMPARISON.md`](DESIGN_COMPARISON.md) option B) becomes viable and the owner's three objections to the recommended hybrid **D** vanish: (1) no Python in the live loop, (2) fully backtestable in the MT5 Strategy Tester, (3) far less monitoring/integration surface.

This is **not** "how do we integrate the existing pandas brain" — that is option D, already shipped and bit-identical to the pin. This is the narrower and harder question: **can we rewrite the brain so a native MQL5 port is faithful?**

> **One-line verdict:** YES on the **logic/causality axis** — the v3.4 position path is *already causal* and re-pin-free by measurement (Δ = 0 across 1.53M cells). But the "~100% same behavior / no re-pin" headline is an **artifact of byte-identical Python re-execution** and does **not** survive the port: a correct float64 native port carries a discrete-state-flip residual that moves the campaign's gate metrics ~0.06–0.8pp CAGR / ~0.14–0.28pp breach, so the port needs its **own gate-level re-validation**, Python survives as a **permanent reconcile oracle** and a **native `b_h` engine**, and porting a **still-churning** book defeats the maintainability case. **Refactor feasibility: clean-with-care. B-pure viability: doubtful at this time — ship D, revisit B only after the book freezes and "no-Python-live" is confirmed a hard mandate.**

---

## 1. The reframed "100% behavior" — three questions, kept separate

The prompt correctly splits "same behavior" into three axes. Keeping them apart is the whole game, because two are clean and one is not, and the headline number belongs to only one of them.

| # | Axis | Question |
|---|---|---|
| **(i)** | **Logic parity** | On the *same input bars*, can a causal MQL5 port match `build_c2`'s positions? |
| **(ii)** | **Causal re-pin** | How far does *removing the lookahead* (going causal) move v34 positions/equity vs the pin — is a small re-pin acceptable? |
| **(iii)** | **Feed divergence** | Live-broker vs frozen-IC feed — a **separate runtime issue**, excluded from the logic-refactor question. |

The prior assessment ([`DESIGN_OPT1_NATIVE_MQL5.md`](DESIGN_OPT1_NATIVE_MQL5.md) §9/§11/§12) flagged the blockers: (a) **lookahead** in the reference pipeline (`core.universe_frames` does `.ffill().bfill()`; `commission_frac` uses full-sample `px.median()`); (b) **pandas-specific numerics** (`ewm adjust=True`, `ddof=1` std, rolling `min_periods`); (c) a **moving target** (sleeves churn daily, scale just went s11→s10).

This assessment measures (i) and (ii) to the euro and refutes premise (a) at the logic layer, then folds in the adversarial reviews that show why "clean logic" is **not** the same as "B-pure viable."

---

## 2. The headline go/no-go number — causal-delta is measured, not estimated

**The decisive finding.** A full causal rebuild of the book — every sleeve re-derived from its own `make_positions()`, then `combine × SCALE 10 → structural_gold_cap → apply_hard_limits` — diffed against the frozen `build_c2` pin:

- **Position matrix: `0.0` diff across all 1,530,749 cells** (31 traded symbols × 49,379 hours). Per-symbol max|Δfrac| = 0 for all 31 symbols. 0 of 49,379 hours affected (0.000%).
- **Through the engine of record** (`account_engine_1m`, 1m worst-mark, EUR 10k):

  | Metric | Causal rebuild | Δ vs pin |
  |---|---|---|
  | CAGR | 0.8865880763 | **+0.000e+00** |
  | MaxDD_worst | 0.2167488591 | **+0.000e+00** |
  | Sharpe | 1.854317299 | **+0.000e+00** |
  | Final EUR | 449,707.7453 | **+0.000e+00** |
  | negY / negQ | 0 / 1 | 0 / 0 |

**Where the flagged lookahead actually lives.** Transitive-closure audit of `build_c2` found exactly **two** literal non-causal ops, and **both are in `core.py`'s cost/metrics path, which `build_c2` never calls**:

1. `core.py:84` `relsp = relsp.ffill().bfill()` — the `.bfill()` is non-causal, but `rel_spread` is consumed **only** by `core.simulate`'s research cost model.
2. `core.py:107` `commission_frac` / `_median_eur_per` full-sample `.median()` — also cost-only.

**Ablation (Exp A, measured):** patching `core.commission_frac` to *raise* → `build_c2` still succeeds (positions never touch it). Forcing `relsp` to ffill-only and commission to an expanding causal median → **position diff = exactly 0.0** across all 1.53M cells. The one flagged position-path fill, `core.py:82 close = close.ffill()`, is **causal** (past-only — a live stepper holding the last price). The record engine (`account_engine_1m`) charges exact per-fill `comm_side·|lots|` on real 1m bid/ask and has **zero** references to `commission_frac`/`rel_spread`/`.median()`/`.bfill()`.

**Answer to reframe (ii):** going causal moves v34 positions by **exactly 0** and equity by **0 EUR**. The pin is *already a fully causal construction*. `DESIGN_OPT1 §11 Open-Q#2` — "a forward stepper cannot reproduce the lookahead, so a re-pin to a broker-feed `b` is forced" — is **refuted at the logic layer**. The re-pin those ops would force belongs to the **feed** (iii), not the alpha.

> **But read this number for exactly what it is.** Δ = 0 was produced by **re-running the same Python on the same frozen bars**. It proves the *recipe is causal* — it does **not** prove *a second-language port reproduces it*. The moment any numeric difference enters (and one always does — see §5/§7), the discrete state machines flip and the gate metrics move. The refactor's risk therefore collapses from "causality" (solved) to "numeric parity + re-validation" (not solved by this number). This is the single most important framing correction in the document.

---

## 3. Per-sleeve portability

The book is **8 sleeves** (weights are RAW, never renormalized; sum 0.826, cash-park 0.174 is intended) + a trivial ensemble/caps shell.

| Sleeve | Weight | Difficulty | Symbols | Core mechanic | State to persist | Warmup |
|---|---|---|---|---|---|---|
| **seasonal** | 0.18 | TRIVIAL | XAUUSD | wall-clock hold window × inverse-vol | 1 EWMA(720) | ~30d |
| **mag_xau** | 0.05 | TRIVIAL | XAUUSD | $100 round-number magnet, daily | 20-bar daily-ret ring | 20d |
| **ensemble+caps** | — | TRIVIAL | all | pointwise Σ·(w·10) + 2 clips | none | — |
| **intraday** | 0.168 | EASY | USA500, USTEC | NY-open drive, held rows 16–20 | EWMA(60)+EWMA(720)+2 bars | 60d |
| **crypto_smart** | 0.13 | MODERATE | BTC/ETH/SOL | 3-state momentum machine/coin | int state + EWMA(30) + 28/120 rings | 120d |
| **crisis** | 0.10 | MODERATE | XAU+3 JPY | regime convexity, 0.02 grid | windows 10/60/126/50 + EWMA(250/3) + basket cum-max | **~1yr (binding)** |
| **meanrev** | 0.11 | MODERATE-HARD | 10 FX + 6 idx | 2 hysteresis machines, entry-frozen size | int state + frozen size + SMA60/STD60/SMA200 | 200d |
| **trend_v2** | 0.042 | MODERATE | XAU/XAG/XBR/XTI/XNG | 6-lookback tanh ensemble, retrade band | EWMA(20) + 125d ring + held pos | 125d |
| **carry_breakout** | 0.046 | **HARD (tall pole)** | 21 FX + 11 idx/commod | carry rank + hourly Donchian ×11×2 | policy tables + Donchian deque(480/960) + EWMA(480) ATR + rank | 63d |

**Low-risk front block** = seasonal + mag_xau + intraday + crisis ≈ **0.498 raw weight (~60% of the deployed 0.826)** — lowest state-machine content, the natural P1c target. **carry_breakout (0.046)** is the worst effort-to-weight ratio in the book and is the sleeve the reviews single out (see §6).

The ensemble/caps shell is ~120 lines and already exists in same-language spec form as `target_engine.build_book`. The **caps are load-bearing, not edge cases** — measured binding frequency over the pin: XAU-overnight 18.1%, EURCHF 23.4%, EURSEK 23.1%, EURNOK 19.7%, AUDNZD 25.0%. Get the server-hour boundary (`GOLD_OVERNIGHT_HOURS = 21..23 ∪ 0..5`) wrong and the book forks.

---

## 4. The refactor design (recurrences, state, caps, re-pin)

### 4.1 The seven shared primitives — build once, parity-gate once

The entire numeric surface of the book reduces to seven bounded recurrences. Measured parity vs pandas in brackets.

1. **`ewm_mean` (pandas `adjust=True`)** — `weighted = (old_wt·weighted + new_wt·cur)/(old_wt+new_wt)`; `old_wt·=(1−α)` **every** step incl. interior NaN under `ignore_na=False`; `old_wt+=new_wt` on an observation. State ≈ {weighted, old_wt, nobs}. **[max rel err 4.8e-15]**. Using the *natural* `adjust=False` recursion instead blows up XAU by **0.675×equity on 34.8% of hours** — **not optional**.
2. **`ewm_std` (bias-corrected)** — track {mean, cov, sum_wt, sum_wt2}; `var = sum_wt²/(sum_wt²−sum_wt2)·cov`, Welford-weighted. **[5.6e-16]**. ~5 doubles/series.
3. **`rstd` rolling sample std `ddof=1`** — ring buffer. Naive sum/sumsq form cancels to ~1e-10, which is *fine* (see below), but **population `ddof=0` flips whole positions by 1.1×equity on 84.6% of hours** — the single biggest trap. `ddof=1` mandatory.
4. **Donchian max/min** — monotonic-deque ring, O(1) amortized, exact (comparisons only). Up to 960 bars × 11 symbols; `min_periods=window`; explicit `.shift(1)`.
5. **`sma`** — ring buffer.
6. **`to_hourly`** — index +`lag_d` days +`(lag_h−1)`h, reindex(union).ffill(); day boundary = broker server-midnight.
7. **daily finalize + combine/scale/cap** — `resample('1D').last()` = last hourly close of server-day; pointwise ensemble.

### 4.2 Ensemble + caps

```
net[sym] = Σ_n sleeve_pos_n[sym] · (weight_n · GLOBAL_SCALE)   // RAW weights, NO renorm, fill 0
GLOBAL_SCALE = 10
structural_gold_cap = weight[seasonal] · scale = 0.18·10 = 1.80   // DERIVED — compute at load, do NOT hardcode
apply_hard_limits:
  |EURCHF|,|EURSEK|,|EURNOK|,|AUDNZD| → ±0.5   (all bars)
  |XAUUSD| → ±1.80  when (hour≥21 OR hour<6)   (overnight only)
```

### 4.3 The six pandas idioms that must be replicated exactly

Silent-drift traps a `<1e-12` self-check won't catch: (a) ewm `ignore_na=False` decays weight *through* interior NaN; (b) `min_periods` gates the *output* to NaN while the recurrence keeps running — gate on nobs, not bar index; (c) `pct_change()` default `fill_method='pad'` pads interior NaN before dividing — a **deprecated** default, so **pin the pandas version**; (d) numpy `round()` is **banker's** (half-to-even) — MQL5 `round()` is half-away-from-zero, a *systematic* mismatch on crisis's 0.02 grid and mag's $100 magnet; (e) `rank(axis=1, ascending=False)` uses the `average` tie method and policy rates tie exactly → a naive argsort includes/excludes the wrong pair at carry top-5; (f) server-midnight resample boundary.

### 4.4 The re-pin decision — three deltas the owner must not conflate

| Delta | Cause | Measured size | Re-pin needed? |
|---|---|---|---|
| **Logic** (causal vs pin) | removing `core.simulate` lookahead | **0.0** positions / **0 EUR** | **No** (proven) |
| **Numeric** (port vs pin) | float64 discrete-state-flip noise | see §5 — **gate moves 0.06–0.8pp CAGR** | **Yes — a port-specific re-pin** |
| **Feed** (live broker vs IC pin) | different M1 union grid, spreads, symbol starts; `b_h` reweights hourly | separate; ~8pp CAGR on Duka, unmeasured for sleeves | **Yes — runtime feed re-pin**, out of scope (iii) |

The refactor itself (row 1) is re-pin-free. But the **port** (row 2) is a *new causal instance*, not a reproduction of the Python pin, and must pass the gates on its **own** output — see §5.

---

## 5. Why "~100% behavior" does not survive the port — the fidelity killers

The adversarial fidelity review ran both books through the engine of record plus the house worst-mark-breach bootstrap and **measured** the sensitivity the Δ=0 headline hides:

- **The Δ=0 headline is an artifact of byte-identical Python re-execution.** A **1e-9** feed perturbation moved CAGR **+0.81pp**, terminal EUR **+2.6%**, breach P(DD>30%) **−0.28pp**. Even the design's own "benign" **float32** floor (maxabs 5.6e-5) still moved terminal EUR **−0.19% (−$846 on $450k)** and the breach gate **+0.14pp** (0.1208→0.1222). **The gate metrics the campaign decides on are not reproducible to the sub-percent resolution at which decisions are made.**

- **"positions within ε≈1e-4" is mischaracterized and insufficient.** The port-vs-pin position error is **discrete-flip-quantized, not a bounded ε**. A 1e-11 perturbation (smaller than any two correct float64 implementations differ by) produces up to **6.08e-2** per-symbol differences, and the magnitude is *identical* at 1e-9 and 1e-11 — the signature of a **persistent state flip**, not drift. Each flip is a hysteresis state that persists **weeks-to-months**, and the breach gate is a path/tail statistic that amplifies it. There is no "ε≈1e-4 regime" for a discrete hysteresis state vector.

- **Genuine ties make bit-identical positions impossible in principle.** meanrev-FX closest z-to-threshold is **9.8e-5** (the design's "2.7e-4, 0 flips" is understated and unbacked by a scratchpad script); crypto_smart is **8.3e-6**; meanrev **index** exit `z>0` sits **exactly on 0.0** on ≥1 bar (`pct_change(5)=0` when price equals its value 5 days prior); crisis rounds to a 0.02 grid with banker's rounding vs MQL5 half-away-from-zero — a **systematic** rule mismatch on the gate-dominating convexity sleeve.

- **Warm-start "within ε≈1e-4 at the 2020 boundary" is incoherent** for a discrete state vector and lands on the worst region: the COVID crisis tail dominates MaxDD_worst and is the most state-dense + warm-sensitive part of the book (the memory'd cold-start k≈4.7 artifact). A single flipped crisis/meanrev/carry state at the boundary **fabricates the gate-dominating tail** — consistent with the float32 result moving the breach gate even when the single worst-mark bar did not.

**Consequence — the parity criterion must be rewritten:**

1. **Continuous-quantity parity** (vol, ewm mean/std, z-scores) to **~1e-8** on frozen bars — the right unit test, achievable.
2. **Discrete-state-sequence parity** — require **identical integer state / Donchian state / grid value at every bar**, and treat any mismatch as a *finding to trace*, never averaged into an ε. Report as "N state-sequence mismatches over the 6y×instrument grid **plus the resulting gate delta**."
3. **Gate-level acceptance** — push the port through `account_engine_1m` + the breach bootstrap and gate on **ΔCAGR / ΔMaxDD_worst / ΔBreach**, not on positions. Measured bracket of the likely residual: **~[0.06, 0.8]pp CAGR** and **~[0.14, 0.28]pp breach**. The owner accepts only inside a **pre-agreed gate-level tolerance**. The campaign makes calls at that resolution.

---

## 6. Does B-pure become viable? — explicit verdict: **doubtful (not now)**

Granting the logic ports cleanly, the effort-vs-payoff review shows **none of the owner's three downsides is fully eliminated**, and Python survives by architectural necessity:

1. **The reconcile oracle survives — decisive.** `DESIGN_COMPARISON §4` states as *definitional*: the only legitimate correction channel is correction-from-batch — periodically re-run the **frozen Python pipeline** on the broker feed and reseed on drift. Verbatim: *"the Python pipeline is never fully deleted by any design."* A native MQL5 replay **cannot be its own oracle** (same code can't catch its own port bugs). So B-pure removes Python from the hourly **loop** but not from the **system**; `build_c2` + `account_engine_1m` remain the ground-truth parity oracle **forever**, plus you *add* a permanent dual-language drift monitor. **Downside 3 is only partially won.**

2. **`b_h` is a second engine, not a gate.** For B-pure, the v34 worst-mark equity `b_h` (which reweights `f34` every hour in the blend) must go native too, or Python survives in the loop through the equity shadow. `account_engine_1m` is a **296-line 1-minute cross-margined account over 31 symbols**: per-fill commission, per-symbol swap tables at rollover minutes, EUR-quote per bar, margin_cap shrink, lot-step floor, 0.25 rebalance band, intrabar worst co-timed mark on bid_l/ask_h, joint stop-out/liquidation. `a_h` (v7, single book) proves the *pattern* but `b_h` adds full cross-margin + 31-symbol cost tables + 1-minute intrabar bid/ask across the universe. **This is an uncosted second port** with its own multi-piece parity problem and a 1-minute full-universe data path.

3. **carry_breakout breaks the premise either way.** Keep it on the bridge → Python stays in the live loop → **not B-pure**. Approximate it → the model changed → **the "~100% behavior" claim is violated** and it needs its own re-pin. To *actually* reach B-pure you must port exactly the single fiddliest, worst-ROI sleeve (0.046 weight). The design's own fallback ("keep it on the bridge indefinitely") quietly concedes it is not worth it — an argument **against** B-pure. You cannot hold both "B-pure" and "carry_breakout on the bridge."

4. **"Fully backtestable" over-promises.** The Strategy-Tester win is a real *debug-cycle* speedup, but live runs a **third feed** (broker), ~8pp CAGR divergence on Duka, and *no design reproduces the record*. B-pure "dies on the v34 wall: a bit-perfect port still misses the pin because it runs a different feed." So the ST **cannot certify fidelity-to-record** — that still needs the frozen `research_cache` parquets + Python parity harness. **Downside 2 is half-won** (faster mechanics), not fully won.

5. **The parity certification quietly downgrades the gate metric.** The engine of record is the 1m worst-mark MaxDD — **discontinuous in discrete state flips**. Only meanrev-FX was shown flip-free; **crisis — which dominates the COVID MaxDD tail — was not**. Certifying as "positions within ε and CAGR-shape" silently swaps the real gate metric for a shape metric.

**Verdict:** the **logic refactor is viable (clean-with-care)** and genuinely unblocks B-pure's *alpha wall*. But **whole-system B-pure viability is doubtful** at this time: it removes Python from the hourly loop but not from the system, requires a second full account-engine port, forces the worst-ROI sleeve, cannot self-certify fidelity, and re-validates a book that keeps moving. **Ship D; revisit B only if (a) the book genuinely freezes and (b) "no Python in the live loop" is a hard owner mandate, not a preference.**

---

## 7. What survives that keeps a Python dependency

Even a perfect logic port does **not** delete Python. Three pieces remain:

1. **The reconcile/parity oracle** — `build_c2` + `account_engine_1m` on the broker feed, permanent per `DESIGN_COMPARISON §4` (correction-from-batch). Dev/monitoring Python, not live-loop Python — but not gone.
2. **`b_h` until it is separately ported** — a 296-line cross-margined 1m account engine. Until `V34EquityNative` exists and passes its own parity gate against `v34_book_equity_1m.parquet`, Python survives in the loop through the equity shadow.
3. **carry_breakout if it stays on the bridge** — if the 0.046 tall pole is left on `V34Bridge`, that *is* Python in the live loop, and the honest label is "v7-native + v34-mostly-native + carry_breakout bridge," i.e. **D-minus-one-sleeve**, not B-pure.

Score downside 3 honestly as **"live-loop Python removed, dev/monitoring Python retained,"** not "less monitoring surface."

---

## 8. The moving-target freeze requirement — the real programmatic blocker

The book churns daily (15 sleeve files, 8 ship; `GLOBAL_SCALE` s11→s10 within a single morning 08:17–09:41 on 07-10; sleeve bench edited daily). Porting a moving target guarantees perpetual dual-language re-verification and **defeats the maintainability case**. `DESIGN_COMPARISON §5`: *"do not start [B-pure] while the v34 sleeves are still being tuned."* They are still being tuned.

The freeze is also **defective as currently conceived**, and the moving-target review found five governance killers:

- **Roadmap-scheduled obsolescence.** The FMA2 roadmap schedules **v2.2 = an 11-year re-derivation** on the full 2015–2025 sample plus a 2015–2020 pre-registered OOS program that promotes/demotes sleeves — a wholesale re-fit, not a tweak. Porting v3.4 now amortizes a large native investment against a **scheduled replacement**. Port **after** v2.2 lands, or don't.
- **`config_hash` is the wrong freeze token.** It hashes only `{schema, scale, sorted(weights)}` — **blind** to the ~40+ per-sleeve indicator constants that are the actual tuning surface (crisis `_SIZE_SPAN=250`/`_GRID=0.02`/`_DD_WIN=126`; meanrev `Z_IN=2.25`/`Z_OUT=0.75`/`L=60`; crypto `MA_REGIME=120`). A shipped-sleeve internal retune leaves `config_hash` byte-identical while the book moves → **the freeze passes GREEN on a stale book.** Replace it with a **sha256 over the exact source bytes** of the 8 sleeves + `mag_xau` + `ensemble` + weights/scale.
- **The port's parity gate is 8 orders looser than the Python freeze gate.** FMA3's real freeze (`PINNED_INPUTS.md`) gates `books.build_v34_frac_1h()` against the FMA2 brain at **1e-12**. The port's gate must be **~1e-4** (D3). Within that band, a small shipped-sleeve retune is **invisible** to the port's position check while the 1e-12 Python gate would reject it. **Position parity green ≠ still frozen** — the source hash is what polices param drift.
- **No version control in the target.** FMA2 is not a git repo; §5's "pin sleeve modules @ git SHA" has **no SHA to pin**. Adopt git (or an immutable snapshot) before any freeze.
- **Source-of-truth ambiguity.** `strategy_fable.build_portfolio_positions` **renormalizes** by `sum(weights)=0.826`; the shipped path (`build_c2`/`target_engine.build_book`) does **not**. The two differ by **1/0.826 = 1.21× gross**. A porter who ports the "authoritative" file ships a book **21% too hot** with no gate to catch it. Nominate `build_c2`/`target_engine.build_book` as the sole reference and quarantine the renormalizing helper.
- **Derived-cap hardcode trap.** `structural_gold_cap = seasonal_weight × scale` is a binding risk limit (binds ~18% of overnight bars) that silently moved 1.62→1.98→1.80 as scale moved; three source files disagree in stale comments. **Compute it at load from frozen weights/scale — never hardcode 1.80.**

**Freeze-then-port protocol (`FMA3-v34-freeze-1`):** git-snapshot FMA2 → sha256 the source bytes → emit golden parquets (8 `*_pos` + book + `account_engine_1m` curve) at that hash → gate the port on **BOTH** the source hash **AND** the ~1e-4 position parity → log an `FMA3-RECON-N` entry → standing rule: any edit to a frozen sleeve/weight/scale/cap requires a new hash + full dual-language re-verification before it ships live.

---

## 9. Effort estimate

Sequenced, low-risk-first, each stage a hard go/no-go. Rough order-of-magnitude, single developer.

| Stage | Work | Effort |
|---|---|---|
| **0. Freeze** | git-snapshot FMA2, source-hash, emit golden parquets, RECON entry | ~0.5 day |
| **1. Primitives** | 7 shared recurrences (§4.1), unit-parity each to pandas at ~1e-8 | ~3–4 days |
| **2. P1c gate** | port `realized_vol`+ewm_mean+ewm_std+rstd, reconcile ONE sleeve's vol AND full integer-state matrix to `build_c2`. **KILL SWITCH.** | ~2 days |
| **3. Front block** | seasonal → mag_xau → intraday → crisis (~57% weight), each state-sequence + gate-delta parity-gated | ~4–5 days |
| **4. State-machine sleeves** | crypto_smart → meanrev → trend_v2, hysteresis-state parity + warm-start | ~5–7 days |
| **5. carry_breakout** | Donchian ×11×2 + policy rank + ties (or approved approximation) | ~4–6 days |
| **6. `b_h` native engine** | port `account_engine_1m` (31-sym cross-margin, 1m intrabar), parity vs `v34_book_equity_1m.parquet` | **~5–8 days (uncosted in prior plans)** |
| **7. Warm-state cert** | ≥2019 full-universe warm, 2020-boundary state diff, COVID MaxDD re-cert | ~2–3 days |
| **8. Blender + ST regression** | wire into Option-D blender, full Strategy-Tester regression | ~2–3 days |

**Total ~28–40 developer-days** for full B-pure, *assuming the book is frozen throughout*. The dominant hidden costs are **stage 6 (`b_h`, a whole second engine)** and the fact that any un-frozen research edit re-fires stages 3–8. Stages 0–2 (~6 days) are the cheap **kill switch** — run them before committing to anything downstream.

---

## 10. Does this change the DESIGN_COMPARISON recommendation from D to B?

**No — not at this time.** The refactor is feasible and clean on the logic axis, and it genuinely retires the objection that "the v34 alpha can never go native." But it does **not** move the recommendation, because:

- D already captures the **largest wins** (v7 native stepper, on-terminal dead-man safety, ST gate for the v7 half) at a fraction of the cost, and reuses the **proven, bit-identical (6.66e-16) `targets.json` v34 path**.
- B-pure's incremental delta over D is **only the v34 alpha** — which is exactly the part the ST **cannot fidelity-validate** (feed divergence) and the part still **being tuned** (freeze conflict) and the part that drags in the **uncosted `b_h` second engine** and the **worst-ROI carry_breakout**.
- Python is **not eliminated** — the reconcile oracle is permanent by definition.

**Recommendation stands at D.** Promote to B only when **both** bind: (a) the v34 book is genuinely frozen — sleeve churn stopped, a stable production tag held for a defined window, ideally after v2.2's re-derivation lands — and (b) "zero Python in the live loop" is ratified as a **hard mandate**, not a preference, with the sunk `b_h`/carry_breakout re-port accepted.

**Do now regardless of the B/D decision** (genuine low-risk wins, shared by both, cheap optionality): build `V7Sim`/`a_h`; lift the trivial ensemble+caps+netting shell (validates the mechanical spine, gives `V34Sim` its blender); run the **P1c one-sleeve numeric-parity kill switch**; and run the separately-scoped **feed-provenance number** (broker-feed v34 vs pin, `DESIGN_COMPARISON §5.2`, ~1 day) — if feed divergence is large, B-pure's record-reproduction value collapses regardless of a perfect port, and the full sleeve + `b_h` port should not be started.

---

## 11. Honest "what makes this hard"

Not causality — that is solved (Δ=0, proven). The hard parts, in descending order of how likely each is to sink the effort:

1. **The gate metric is discontinuous.** 1m worst-mark MaxDD flips on discrete state changes. A correct float64 port carries an irreducible state-flip residual (measured: gate moves 0.06–0.8pp CAGR, 0.14–0.28pp breach). You cannot certify "bit-identical" — you must negotiate a **gate-level tolerance up front** and prove the port lands inside it *on the tail*, especially COVID crisis.
2. **`b_h` is a second engine.** A 296-line cross-margined 1m account over 31 symbols with its own data path and parity problem — routinely mis-scoped as "a small gate like `a_h`."
3. **The book is a moving target with a defective freeze token.** `config_hash` is blind to indicator-param churn; FMA2 has no VCS; two builders disagree by 1.21×; a v2.2 re-derivation is on the roadmap. Freeze discipline, not math, is the governance blocker.
4. **Exact pandas numerics are mandatory, not "with care."** `adjust=True` EWMA and `ddof=1` std are hard requirements — the wrong-but-natural convention blows up positions 0.68–1.1×equity on 35–85% of hours. Six deprecated/subtle idioms (banker's rounding, `pct_change` pad, rank ties, `ignore_na`, `min_periods`, server-midnight) each silently compound over 6 years.
5. **carry_breakout is the worst-ROI sleeve you cannot skip.** 0.046 weight, hardest mechanics (hourly Donchian ×11×2 + policy-rate cross-sectional rank with tie handling). Porting it exactly is low-value; not porting it means it's not B-pure.
6. **Warm-state seeding.** Every stateful sleeve is wrong for months if cold-started (COVID k≈4.7). Requires ≥2019 full-universe warm and a boundary-state certification that cannot be "within ε" for a discrete vector.
7. **Python never fully leaves.** The reconcile oracle is permanent by definition — the maintainability payoff is "live-loop Python removed," not "Python removed."
