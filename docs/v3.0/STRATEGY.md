# V3.0 strategy design — the what & why

> **⚡ SUPERSEDED IN PART (2026-07-15) — see [CURRENT_STATE.md](CURRENT_STATE.md).** This doc describes the RECON-4-era `FableFederation_V3` **CSV-replay** EA. The current executor is the **native, live-computing** `FableBookNative` EA — full-window 2020-2025 real execution net **€2,934,301** (0.76× the frictionless record), **RECONCILED** on engine fidelity (drawdown +0.7pp, position fidelity ~perfect), the −12.9pp CAGR gap being **swap-led execution friction**. `CURRENT_STATE.md` **wins** where they disagree.

The authoritative "what + why" for the FMA3 **v3.0 — faithful-executor release**. v1.0 shipped the
**model**: a Python record-engine book (blended book, config hash **`51a7541cc2aaa593`**,
locked 2026-07-10). v3.0 ships the **EA that provably executes that model on MT5**, plus the honest
deployable reality — the dials, the three physical constraints, and the friction that separates a
frictionless record from a live account.

Canonical model home (source of truth): **[`model/v3/`](../../model/v3/)** —
[`README.md`](../../model/v3/README.md), [`MODEL_SPEC.md`](../../model/v3/MODEL_SPEC.md) (blend math +
engine constants), [`PINNED_INPUTS.md`](../../model/v3/PINNED_INPUTS.md) (frozen artifact hashes),
[`EA_V3_DESIGN.md`](../../model/v3/EA_V3_DESIGN.md) (the executor design),
[`RECON4_RESULTS.md`](../../model/v3/RECON4_RESULTS.md) (the execution reconciliation). The
strategy-selection decision trail (why two books, why `w = 0.70`, why static, the grids) is
unchanged from v1.0 and lives in **[../../archive/docs-v1.0/STRATEGY.md](../../archive/docs-v1.0/STRATEGY.md)** — cross-linked here,
not re-litigated. The MT5 executor is `mt5/ea/FableBook.mq5`
(`FableFederation_V3.ex5`, sha `740da0ff…`); the stream exporter is
[`scripts/export_book_frac_v3.py`](../../scripts/export_book_frac_v3.py); the reconciliation protocol
is [`research/protocol/RECONCILIATION.md`](../../research/protocol/RECONCILIATION.md).

**All model figures are in-sample record reads (IC 2020-25). MT5 real-tick + live demo are the
remaining falsification tests. Achievable equity is 0.66–0.95× the record depending on dial/scale
(FMA3-RECON-4). *(RECON-4/FableFederation_V3 replay figure; superseded — native `FableBookNative` EA now nets €2.93M / 0.76×, see CURRENT_STATE.md)* Do NOT present the model number as a deployable promise.**

---

## 1. What v3.0 is

**v3.0 = the model of v1.0, now with a proven executor.** The model is unchanged: one blended
blend, config **`51a7541cc2aaa593`**, `w_v7 = 0.70`, the matrix `static_fed(0.70) × s` run through
the 1-minute worst-mark record engine. What is new in v3.0 is `FableFederation_V3` — an EA that
holds the model's **exact** target position on MT5, so every euro of gap between the EA and the
frictionless record is a **named physical constraint**, not a defect.

The model ships as **two dials** (the shipped presets, [`MODEL_SPEC.md`](../../model/v3/MODEL_SPEC.md)):

| Preset | Seed | Dial | Final equity | CAGR | MaxDD (worst-mark) | Extras |
|---|---:|---|---:|---:|---:|---|
| **IC** (H-RISK-1) | €10,000 | s = **1.6** compounding | **€3,872,872** | +170.2% | 22.58% | Sharpe 2.465 |
| **FTMO** (H-RISK-2b) | €100,000 | s = **0.7** + daily breaker x = 3.0% | **€1,332,404** | +54.02% | 13.33% | 26 breaker fires |

The v3 EA reproduces those record reads **up to real execution constraints** — position-level
fidelity is exact (held fraction == `fed_frac·s`, median `after/want` = 1.000, all runs), and the
final equity lands at **0.66–0.95× the record** depending on how hard the dial and scale push
against friction, volume limits, and margin (FMA3-RECON-4):

| Engine | Config | Headline |
|---|---|---|
| **Record engine (model of record)** | `static_fed(0.70) × 1.6`, IC 2020-25, €10k | **€10,000 → €3,872,872 / +170.2% CAGR / 22.58% worst-mark DD / Sharpe 2.465** |
| **Record engine (FTMO dial)** | `static_fed(0.70) × 0.7` + breaker 3.0%, €100k | **€100,000 → €1,332,404 / +54.02% CAGR / 13.33% DD / 26 breaker fires** |
| **v3 EA (FMA3-RECON-4)** | same stream, MT5 tester, 1m-OHLC | **position fidelity 1.000; equity 0.66× (IC s1.6) → 0.95× (FTMO s0.7) of the record** *(RECON-4/FableFederation_V3 replay; superseded — native EA: €2.93M / 0.76× IC s1.6, see CURRENT_STATE.md)* |
| MT5 real-tick / live demo | — | **the deployable arbiter — the remaining falsification test** |

**Read the marks carefully.** The model figures are **in-sample record reads**. The record engine is
frictionless and unbounded; a real retail account is neither. v3.0's contribution is to make that gap
*legible* — to prove the EA executes the model exactly, and then to name every reason the achievable
equity is less than the record (§8).

---

## 2. Design philosophy — a blend of two frozen books

The strategy design is **inherited from v1.0 unchanged** and is summarized here; the full grids,
red-team battery, and selection rules are in **[../../archive/docs-v1.0/STRATEGY.md](../../archive/docs-v1.0/STRATEGY.md)**.

**FMA3 = ONE cross-margined account running BOTH frozen parent books side by side as virtual
sub-accounts** — the NSF5 **Core band book** at capital share `w = 0.70`, and the FMA2 **Satellite
fixed-fraction book** at `1 − w = 0.30` — with NO cross-book rebalancing and a single global scale
`s` on the blended fraction matrix. Neither parent's sleeves, parameters, or internal mechanics were
touched. Both parents arrive **frozen** (IC 2020-25 was their development sample); the FMA3 protocol
therefore licenses a **structural-only** design space — capital split `w`, rebalance mechanics,
combined caps, global scale — one lever per version, every bar pre-registered, **DECLINE by
default**.

Blend is the *one* open channel because every sleeve-level path between the parents is formally
closed (band → Satellite flips −7.31pp under fixed-notional; FMA2 → Core is 0-for-10). The thesis is
**structural complementarity, not correlation**: daily-return ρ = +0.351, drawdown troughs disjoint,
each book's worst year the other's relative refuge. Quoted honestly, Satellite returns **−2.9%** across
Core's ten worst days — **a softener, not a hedge**. The single number `w = 0.70` is the pre-registered
H-FED-1 grid winner (beats *both* parents on DD and Sharpe simultaneously — diversification the
leverage dial cannot buy), and the no-rebalance decision keeps the disjoint troughs intact (all four
rebalance cadences DECLINED). All of that is v1.0 material; v3.0 changes none of it.

---

## 3. The two sub-books and the blend

Two economically distinct, separately validated books, blended into one netted target matrix.

| Sub-book | Cols | Native mechanics (untouched) | Native standalone anchor | Seed share |
|---|---|---|---|---|
| **Core band book** (NSF5) | **8 net** | slot-equity sleeves, `BAND_SYM_25` re-split, H9 delta-resize; R8 anchor extraction | `a` = `v7_book_equity_1m.parquet` native 1m equity multiple | **0.70** |
| **Satellite book** (FMA2) | **31** | fixed-fraction × GLOBAL_SCALE 10, F3 caps, structural gold cap 1.80 pre-applied, cash-park | `b` = `v34_s10_pin_curve.parquet` native 1m equity multiple | **0.30** |

- Core's 8 net cols: AUDUSD, BTCUSD, ETHUSD, EURGBP, NZDUSD, USDJPY, USTEC, XAUUSD.
- The union is **33 distinct symbols**; **6 are shared** (BTCUSD, ETHUSD, EURGBP, USDJPY, USTEC,
  XAUUSD) and are **NETTED** into one net column each.
- `a` and `b` are each book's **own standalone** equity path — **NOT** the joint account, **NOT**
  levered by `s`, **NO** blend friction. This is the single most load-bearing fact for the
  executor (§5.2).

**The blend (`static_fed`, w = 0.70)** — the exact joint target fraction at hour *h*, symbol *k*:

```
j        = w·a_h + (1−w)·b_h                              # w = 0.70; a,b = frozen native multiples
fed[h,k] = f7[h,k]·(w·a_h/j)  +  f34[h,k]·((1−w)·b_h/j)   # shared symbols already summed (netted)
final    = fed · s                                        # s = the dial (IC 1.6 / FTMO 0.7)
```

The two share weights `(w·a_h/j)` and `((1−w)·b_h/j)` sum to 1 each hour and **drift on native
relative performance**. `s` is **not** in the hashed config — `global_scale = 1.1` in
`strategy_fma3.py` is only the config base point, not a shipped dial; the shipped dials are IC s=1.6
and FTMO s=0.7.

---

## 4. The record engine — the accounting the EA must match

The model number is whatever `engine/record_engine.run_record` (IC) /
`record_engine_ext.run_record_ext` (FTMO) prints on `fed · s`: a single cross-margined **1-minute
worst-mark** account, **compounding**, 2020Q1–2025Q4. The constants the EA must reproduce exactly
([`MODEL_SPEC.md §4`](../../model/v3/MODEL_SPEC.md)):

- **Causal lag:** hour-*h* row executes at hour *h+1* first traded-minute OPEN.
- **Sizing:** `unit = px · contract · eurq[t,k]`; `raw = g · balance / unit`;
  `lots = floor(|raw|/step + 1e-9)·step`, → 0 if `< min_lot`.
- **Margin cap 0.9:** `margin_sum = Σ|lots|·unit/leverage`; if `> 0.9·balance`, one uniform
  `shrink = 0.9·balance/margin_sum`.
- **Rebalance band 0.25:** retrade a leg only on sign-flip / cross-zero / reduce / `|want−lots|/|lots| > 0.25`.
- **Fills cross the spread**, commission per lot/side, swap daily; **compounding off shared cash
  BALANCE** (realized only, excludes floating).
- **Joint stop-out** if worst-mark `eq_w < 0.50·margin_used`.
- **eurq** = 1 if quote=EUR else `1/mid(EUR-cross)`, **full currency map** (USD/JPY/GBP/CHF/NZD/CAD/NOK/SEK).
- **FTMO breaker** (x = 3.0%, FTMO only): anchor = previous server-day CLOSE-mark equity; each
  minute, if worst-mark `eq_w ≤ anchor·(1−0.03)` → flatten all, halt until next rollover. Fired 26×,
  cost 5.30pp CAGR.

This is the target. Everything in §5 exists to hold *this* position on a live MT5 account.

---

## 5. The v3 execution architecture — replay, not compute-live

*(RECON-4/`FableFederation_V3`; superseded — the current executor `FableBookNative` computes the blend **live/native** on MT5, not by CSV replay; the blend/sizing math below is unchanged, only the execution path is. See CURRENT_STATE.md.)*

**The one decision that defines v3: replay a precomputed unified `fed_frac` stream — do NOT compute
the blend live.** This is why v1/v2 diverged and v3 does not.

### 5.1 What v3 does

The exporter [`scripts/export_book_frac_v3.py`](../../scripts/export_book_frac_v3.py) emits the
unified, **already-netted** `fed_frac` stream — for every hour *h* and every symbol *k* of the
33-symbol union, the net target fraction `fed[h,k] = f7·(w·a_h/j) + f34·((1−w)·b_h/j)`, i.e. exactly
the `static_fed(0.70)` matrix from `model/v3/reproduce.py`. `s` is **not** baked in — it is the EA
dial. Format `fmt=3`: header `w_v7=0.70,config_hash=51a7541cc2aaa593,fmt=3` + frozen input sha256s,
rows `epoch,symbol,net_frac`, one `__GRID__,0` sentinel per all-flat hour (keep-last-good), repo→broker
map (`USA500=US500; DAX=DE40`) applied at emit. The exporter **hard-fails** unless (a) the re-parsed
matrix reproduces `static_fed(0.70)` to <1e-12 and (b) the record engine on the stream prints
€3,872,872 at s=1.6 and €1,332,404 at s=0.7 — the file is provably the model or it does not ship.

`FableBook.mq5` then replays that stream. **The per-bar sizing loop** (re-sized every M1
bar, executing hour *h*'s row):

```
base = AccountInfoDouble(ACCOUNT_BALANCE)        // realized cash — model sizes off BALANCE, not equity
for each symbol k with fed_frac[h,k] != 0:
    g    = fed_frac[h,k] * InpScale              // InpScale = s (1.6 IC / 0.7 FTMO)
    dir  = sign(g);  px = dir>0 ? Ask : Bid
    unit = px * contract(k) * eurq(k)            // eurq = full currency map, always on
    want = g * base / unit
    lots = floor(|want|/step + 1e-9)*step ; if lots < min_lot -> 0
margin cap:      if Σ|lots|·unit/leverage > 0.9*base, one uniform shrink = 0.9*base/Σ
rebalance band:  retrade leg k only on sign-flip / cross-zero / reduce / |want−held|/|held| > 0.25
```

Key properties, all matching the record engine (§4):
- **Sizes off `ACCOUNT_BALANCE`** (realized cash), not equity — compounding is automatic as the base
  grows with realized P&L.
- **`InpScale` is the dial** — the *only* knob that differs IC↔FTMO. One binary, two presets
  (`FABLE_IC.set` s=1.6; `FABLE_FTMO.set` s=0.7 + breaker; `FABLE_PARITY_S10.set` s=1.0 sanity).
- **ONE net position + ONE magic per symbol** (netting ratified by owner) — the 6 shared symbols are
  already summed in the stream, so the EA holds a single net order per symbol.
- **Full-map eurq, unconditional** — the promoted `F3_EurPerQuoteV34` prices *every* symbol via the
  full EUR-cross map; this revived the 7 Satellite legs that v1/v2 silently killed (§7).
- **FTMO daily breaker** (`InpDailyStopX`, 0=off for IC, 3.0 for FTMO): on server-day rollover,
  anchor = carried **previous-day CLOSE** equity (day 1 = balance); each M1 bar, if worst-mark `eq_w`
  (via `OrderCalcProfit` bar low/high) ≤ `anchor·(1−x/100)` → flatten all, halt (targets→0) until
  next rollover.

### 5.2 WHY replay — compute-live provably diverges at s≠1

The share weights `(w·a_h/j)` and `((1−w)·b_h/j)` are built from the **frozen native standalone**
equity multiples `a` and `b` — each book's *own* path, un-levered, friction-free. **A live account
levered by `s` cannot reconstruct those weights from its own equity.** Its realized equity is the
*joint, levered, friction-bearing* curve — a different object from `a` and `b`. So any EA that tries
to compute the blend live must *estimate* `a`,`b` from account state, and that estimate drifts from
the frozen truth the instant `s ≠ 1` — and **both shipped dials are s≠1** (1.6 and 0.7).

Replaying the precomputed blend sidesteps this entirely: the frozen `a`,`b` and the Core band re-splits
are all baked into the stream offline, at s=1, once. Replay is therefore the **only faithful path** —
it dissolves the reseed / floating-double-count / pooled-redistribution divergence classes *by
construction*, not by tuning.

### 5.3 What v3 discards (the entire v1/v2 machinery)

Because it replays a precomputed blend, v3 **throws away the entire v1/v2 signal + sizing stack**:

- **No `V7Core` band logic** — the band re-splits are frozen inside `frac7`.
- **No `QuarterRebalance` / per-book reseed / `VBalance`** — v1/v2 sized Core off a pooled quarterly
  `VBalance` with a floating double-count; gone.
- **No `e34`** — v1/v2 sized Satellite off a stagnant own-sub-equity `e34`; replaced by the shared
  `ACCOUNT_BALANCE`.
- **No `InpReseedBalance` / `InpIndepReseed` / `InpV34JointSizing`** — obsolete.
- **`InpV34EurQuoteFix` → unconditional** — the full-map eurq is now always on.

v3 keeps only the **execution primitives** (order send/split, reject backoff, lot rounding,
`OrderCalcMargin` projection) and adds one unified replay + size loop. The architecture is minimal,
single-account, single-magic-per-symbol, dial-agnostic.

---

## 6. Locked configuration

The shipped model configuration (`strategy_fma3.py`, hash **`51a7541cc2aaa593`**, locked
2026-07-10) plus the v3 executor:

| Parameter | Value | Meaning / provenance |
|---|---|---|
| `structure` | **static_federation** | H-FED-1 winner; H-FED-2 declined (v1.0 §6) |
| `w_v7` | **0.70** | Core band-book capital share, grid winner by rule (v1.0 §5) |
| dial `s` (IC) | **1.6** | InpScale IC preset — compounding, seed €10,000 |
| dial `s` (FTMO) | **0.7** | InpScale FTMO preset — + daily breaker x=3.0%, seed €100,000 |
| parent A operating point | Core core7 band, **R8 anchor extraction** | `frac7`/`a` frozen inputs |
| parent B operating point | Satellite @ **GLOBAL_SCALE 10** | `frac34`/`b`, gold cap 1.80 pre-applied |
| cross-book rebalance | **none** | the split is a seed; realized share drifts |
| shared-symbol handling | **NETTED** | 6 shared symbols summed to one net col each; 33 union |
| executor | **replay** `FMA3_fed_frac_v3.csv` (fmt=3) | `FableFederation_V3.ex5` sha `740da0ff…` |
| engine constants (matched) | margin cap 0.9, rebalance band 0.25, stop-out 0.5·margin_used, causal h→h+1 | record engine of record |
| frozen inputs | `frac7`, `a`, `b`, `frac34` (+ w, s) | hashes pinned in [`PINNED_INPUTS.md`](../../model/v3/PINNED_INPUTS.md) |

The stream is the deterministic function of **4 frozen artifacts + 2 scalars (w, s)**; any change to a
pinned hash re-opens the model.

---

## 7. What was tried and declined

The strategy-level ledger (rebalance cadences, aggressive-frontier scales, off-grid `w`, joint caps)
is v1.0 material — see **[../../archive/docs-v1.0/STRATEGY.md §10](../../archive/docs-v1.0/STRATEGY.md)**. The **execution-level**
declines new to v3:

| Tried | Result | Why declined |
|---|---|---|
| **v1/v2 compute-live sizing** | Core off `VBalance` (pooled quarterly reseed, floating double-count), Satellite off `e34` (stagnant own sub-equity) | **DECLINED** — cannot reconstruct the frozen `w·a/j`, `(1−w)·b/j` share weights; provably diverges whenever s≠1, and both dials are s≠1 |
| **Per-book / Core-only compute-live probe** (`_ab` artifacts) | separate own-joint probe curves | not the model's input; the model's Core input is `v7_book_frac_1h.parquet` (no `_ab`) |
| **3-branch eurq with `1/EURUSD` catch-all** (v1/v2) | 7 Satellite legs (AUDJPY, CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK) mispriced ~117×/~10× below min-lot and never traded | **replaced** by the unconditional full-map eurq; RECON-4 confirms all 33 symbols now trade |
| **Per-symbol split of shared legs** | keep Core-vs-Satellite attribution on the 6 shared symbols | **declined (owner-ratified)** — v3 nets to one position/magic per symbol; attribution stays recoverable offline from the pre-net `f7`,`f34` rows if ever needed |
| **Joint 0.5·margin_used stop-out in the EA** | never triggers in-sample (IC worst DD 22.6%, FTMO 13.3% vs the ~50% it needs) | **deferred** — v3 delegates to the broker stop-out; RECON-4 asserts `eq_w` never falls below 0.5·margin_used, proving the omission immaterial |

---

## 8. FMA3-RECON-4 — the execution reconciliation

**Verdict: v3 is the faithful executor of `model/v3`.** Position-level fidelity is exact; the equity
achieves 66–95% of the frictionless record depending on dial/scale, and every gap is a *named,
physical* constraint the record engine does not model — not an EA defect. Tester: IC Markets acct
11078280, 1m-OHLC, HEDGING, 1:500 (for the s=1.6 reproduction), 2020–2025.

| Run | Preset | Dial | v3 equity | Model | v3/model | Rejects | Fidelity (median `after/want`) |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | PARITY | s=1.0 | €391,873 | €464,991 | **0.84** | 0 | 1.000 (33/33 symbols) |
| 2 | IC | s=1.6 | €2,552,962 *(RECON-4/FableFederation_V3 replay; superseded — native EA: €2.93M / 0.76×, see CURRENT_STATE.md)* | €3,872,872 | **0.66** | 0 (after volume-limit fix) | 1.000; min ML 121% at 1:30 |
| 3 | FTMO | s=0.7 | €1,265,541 | €1,332,404 | **0.95** | 0 | 1.000; 28 breaker fires (model 26) |

**What is proven:**
1. **v3 holds the model's EXACT target position** — `after/want` median 1.000 in all three runs.
   Where v3 can place the order, it holds precisely `fed_frac·s`.
2. **The Satellite sleeve is alive** — all 33 symbols trade, including the 7 that were dead in v1/v2; the
   unconditional full-map eurq works end-to-end.
3. **The breaker works** — FTMO fired 28× on the previous-day-close anchor + worst-mark `eq_w` (the
   +2 vs the model's 26 is v3's worst-mark being marginally more conservative).

### The three physical constraints (the record is frictionless & unbounded; a real account is not)

| Constraint | Record engine | Real account | Binds when | Cost |
|---|---|---|---|---|
| **Transaction friction** (spread/commission) | modeled coarsely | real per-trade cost | always; compounds with leverage | 0.95× @ s0.7 → 0.84× @ s1.0 → 0.66× @ s1.6 |
| **`SYMBOL_VOLUME_LIMIT`** | **none** | XAUUSD 10, SOLUSD 1000, ETHUSD 100 lots (this tier) | book past ~€2M/s (XAUUSD binds first) | ~0–6% at €10k → 17–40% at €1M |
| **Broker margin** (per-symbol) | model per-symbol leverage | broker leverage / retail 1:30 | high s on retail leverage | self-limits book; s=1.6 @ 1:30 ran full backtest at min ML 121% |

**The €3.87M IC-s=1.6 record is a frictionless ceiling, not physically reachable on one retail
account at that scale** — XAUUSD alone caps at ~half the model's target past ~€2M/s. Two scaling
levers past the ceiling (owner-raised, both valid): a **higher-tier account** (larger volume limits),
or **N parallel accounts at €C/N each** (each holds 1/N of the model position; aggregate = the full
model, multiplying every volume limit by N — pure capacity, no diversification).

---

## 9. Deployable dials (owner leverage: IC 1:30, FTMO 1:100)

The model figures are frictionless record reads; the **deployable** dials are set at the owner's real
leverages, and this is where the "s=1.6 not deployable at 1:30" flag was re-adjudicated:

- **IC = s=1.6** (OWNER-ACCEPTED 2026-07-12; **PROVISIONAL** pending real-tick min-ML confirm). v3 @
  1:30 s=1.6 ran the full 2020–2025 backtest at **min ML 121%** — liquidation-safe vs IC's 50%
  stop-out (a ~55% peak-book DD would be needed to breach, vs the 21% historical worst), ~11pp above
  the owner's ML≥110% floor. v3's own margin cap (0.9·balance on MODEL per-symbol leverage, ≈ a 1:30
  account's per-symbol grant) self-limits the book, so **margin, not volume, sets the IC dial** — at
  1:30 the book stays small enough that the volume ceiling never engages. The old "s=1.6 undeployable
  at 1:30" flag was a v1-over-leverage artifact and is **DISPROVEN for v3**.
- **FTMO ≈ s=0.5 RECOMMENDED** (**PROVISIONAL** pending a 1:100 confirm run). The volume-cap s-sweep
  shows FTMO ret/DD peaks at s=0.5 (4.78, worst-DD 7.82%) vs shipped s=0.7 (4.05, worst-DD 13.33%);
  volume never binds at FTMO scale, so the −10%/−5% rules govern. The warm-COVID re-validation flag
  (§10) is the reason to cut below 0.7.

---

## 10. How to reproduce it

Every shipped number rebuilds from config + frozen artifacts; the executor is verified against the
same golden reference (per [`RECONCILIATION.md`](../../research/protocol/RECONCILIATION.md)):

| Command | What it proves | Expected |
|---|---|---|
| `python3 strategy_fma3.py \| grep config_hash` | prints the locked config hash | `51a7541cc2aaa593` |
| `python3 model/v3/reproduce.py` (~8–9 min) | the model rebuilds from the blend + frozen inputs | asserts **€3,872,872** (IC) and **€1,332,404** (FTMO), exits non-zero on any drift |
| `python3 scripts/export_book_frac_v3.py` | the replay stream *is* the model | re-parse reproduces `static_fed(0.70)` to <1e-12 **and** record engine on the stream = €3,872,872 / €1,332,404 |
| MT5 tester on `FableFederation_V3.ex5` (sha `740da0ff…`) + presets | the EA holds the model's exact position | FMA3-RECON-4: position fidelity median 1.000; equity 0.66–0.95× the record |

The staged validation protocol runs exporter self-check → headless compile (0/0) → 1m-OHLC smoke
(IC, then FTMO with breaker-fire confirmation) → real-tick, then the RECON-4 verdict. Real-tick is
run **only after** the 1m-OHLC smoke passes.

---

## 11. Honest caveats

- **Everything model-side is in-sample, on a twice-mined window.** IC 2020-25 was both parents'
  development sample; FMA3 added its own selection ledger. The model figures are **record reads**, not
  deployable promises. **MT5 real-tick + live demo are the remaining falsification tests.**
- **Achievable equity is 0.66–0.95× the record** by dial/scale (FMA3-RECON-4) *(RECON-4/FableFederation_V3 replay; superseded — native `FableBookNative` EA nets €2.93M / 0.76× IC s1.6, see CURRENT_STATE.md)*. The €3.87M IC-s=1.6
  figure is a **frictionless ceiling, not physically reachable on one retail account at that scale** —
  volume limits and margin both bind. Do not quote €3.87M as a deployable target.
- **The IC s=1.6 deployable dial is PROVISIONAL.** Owner-accepted 2026-07-12 at min ML 121% (1:30),
  but pending a **real-tick intra-bar min-ML confirmation** that it stays >110%. The 1m-OHLC backtest
  can under-sample intra-bar margin stress; real-tick traverses the bar.
- **The FTMO dashboard is a cold-start in-sample read.** Warm re-validation shows s=0.7 + 3% breaker
  **breaches COVID by 7.5–10.8pp of the FTMO −10% rule**; the crisis-safe dial is ≈ s0.30–0.35, not
  0.70 — the recommended s≈0.5 (or lower) reflects this, and remains PROVISIONAL pending a 1:100
  confirm run.
- **FTMO compound-vs-withdraw is contradictory.** The €1.33M is fully-compounded never-withdraw
  equity, but the 5/5 compliance gates are scored under a monthly withdraw-to-base frame. You cannot
  both compound to €1.33M and reset to base monthly — €1.33M is an "if-compounded" upper figure.
- **The netted stream loses per-book attribution on the 6 shared symbols** by construction
  (owner-ratified). It stays recoverable offline from the pre-net `f7`,`f34` rows if ever needed, but
  the live EA holds one net position per symbol.
- **The joint 0.5·margin_used stop-out is not implemented in the EA** — v3 delegates to the broker
  stop-out; RECON-4 asserts `eq_w` never falls below the threshold in either preset, proving the
  omission immaterial in-sample. Live-crisis fidelity may require adding the exact engine stop-out
  later.
- **The frozen stream ends 2025-12-31.** Live trading past it needs a forward Core-signal recompute +
  stream extension (documented, not built).
- **The −2.9% softener is not a hedge** (inherited from v1.0). The thesis is disjoint weak periods,
  not negative correlation; a regime that correlates the books removes the DD benefit.
