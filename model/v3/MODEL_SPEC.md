# FMA3 STABLE MODEL OF RECORD — v3

**One model, two dials.** Config `51a7541cc2aaa593` (`strategy_fma3.py`, `w_v7 = 0.70`, the Core weight). The IC and FTMO dashboards are the **same blended book at different scale dials `s`**. Reproduced exactly by [`reproduce.py`](reproduce.py).

| Preset | Seed | Dial | Extras | Final equity | CAGR | MaxDD (worst) | Notes |
|---|---:|---|---|---:|---:|---:|---|
| **IC** (H-RISK-1) | €10,000 | s = **1.6** | compounding | **€3,872,872** | +170.2% | 22.58% | Sharpe 2.465, crisis tail 8.12% |
| **FTMO** (H-RISK-2b) | €100,000 | s = **0.7** | + daily breaker x=3.0% | **€1,332,404** | +54.02% | 13.33% | 26 breaker fires |

---

## 1. Inputs — all FROZEN, precomputed, account-independent

| Symbol | Artifact | Content |
|---|---|---|
| `frac7` | `research/outputs/v7_book_frac_1h.parquet` | Core band-book hourly **signed fraction-of-own-equity**, 8 net cols: AUDUSD, BTCUSD, ETHUSD, EURGBP, NZDUSD, USDJPY, USTEC, XAUUSD |
| `frac34` | `engine/books.build_v34_frac_1h()` → `eval_v34_pin_s10.build_c2()` | Satellite book, **31 cols**, GLOBAL_SCALE=10, structural gold cap 1.80 **pre-applied** (never renormalize/re-cap) |
| `a` | `research/outputs/v7_book_equity_1m.parquet["eqc"]`, ÷ its t0 | Core **native standalone** 1m equity multiple (=1.0 at t0) |
| `b` | `research/baselines/fma2/v34_s10_pin_curve.parquet["equity"]`, ÷ its t0 | Satellite **native standalone** 1m equity multiple (=1.0 at t0) |

`a` and `b` are each book's **own** standalone equity path — **NOT** the joint account, **NOT** levered by `s`, **NO** blend friction. This is the single most important fact for the EA: a live blended account **cannot** reconstruct them from its own equity.

## 2. The blend (`static_fed`, w = 0.70)

```
hours = frac7.index ∪ frac34.index
a_h, b_h = a, b reindexed onto hours, ffill (causal asof), fillna 1.0
j = w·a_h + (1−w)·b_h                       # w = 0.70
fed[h,k] = f7[h,k]·(w·a_h/j) + f34[h,k]·((1−w)·b_h/j)     # f7,f34 reindexed to hours, fillna 0
```
The two share weights `(w·a_h/j)` and `((1−w)·b_h/j)` sum to 1 each hour and **drift on native relative performance**. Shared symbols (6: BTCUSD, ETHUSD, EURGBP, USDJPY, USTEC, XAUUSD) are **summed into one net column**. Union = **33 distinct symbols**.

## 3. Dial

`final matrix = fed · s`, a uniform scalar on the whole matrix. **IC s=1.6, FTMO s=0.7.** `s` is **not** in the hashed config — `global_scale=1.1` in `strategy_fma3.py` is only the config base point, not a shipped dial.

## 4. Engine (the accounting the EA must match)

`engine/record_engine.run_record` (IC) / `record_engine_ext.run_record_ext` (FTMO) → FMA2 `account_engine_1m`. Single cross-margined **1m worst-mark** account, **compounding**, 2020Q1–2025Q4.

- **Causal lag:** hour-h row executes at hour **h+1** first traded-minute OPEN.
- **Per minute, per symbol:** `dir = sign(g)`; `px = ask_open if g>0 else bid_open`; `unit = px · contract · eurq[t,k]`; `raw = g · balance / unit`; `lots = floor(|raw|/lot_step + 1e-9)·lot_step`, → 0 if `< min_lot`.
- **Margin cap:** `margin_sum = Σ|lots|·unit/leverage`; if `> 0.9·balance`, one uniform `shrink = 0.9·balance/margin_sum`.
- **Rebalance band 0.25:** retrade a leg only on sign-flip / cross-zero / reduce / `|want−lots|/|lots| > 0.25`.
- **Fills cross the spread** (buy@ask_open, sell@bid_open); commission per lot per side; swap accrued daily on balance.
- **Compounding off shared cash BALANCE** (realized P&L + swaps + comm; **excludes floating**).
- **eq_c** = balance + Σ unreal(close); **eq_w** = balance + Σ unreal(worst: bid_low longs / ask_high shorts).
- **Joint stop-out** if `eq_w < 0.50·margin_used` (mid-close basis).
- **eurq[t,k]** = 1 if quote=EUR else `1/EUR-cross-close-mid` (time-varying), full currency map (§6).
- **MaxDD is worst-mark:** `max((running_peak(eq_close) − eq_worst)/peak)`.

## 5. FTMO daily circuit breaker (x = 3.0%, FTMO only)

On server-day rollover: `anchor = previous server-day CLOSE-mark equity` (day 1 = initial); lift halt. Each minute, if **worst-mark** `eq_w ≤ anchor·(1−0.03)`: flatten all legs at worst-side prices, pay commission, set eq=worst=balance, force targets → 0 (halt) until next rollover. Fired **26×**, cost 5.30pp CAGR (no-breaker s=0.7 → 59.32%; with breaker → 54.02%). The internal 3% breaker is **tighter** than the external FTMO 5% rule, so the 5% rule is essentially never reached.

## 6. Currency conversion (eurq)

`eurq = 1` if quote=EUR, else `1/mid(EUR-cross)` with the FULL map: `USD→EURUSD, JPY→EURJPY, GBP→EURGBP, CHF→EURCHF, NZD→EURNZD, CAD→EURCAD, NOK→EURNOK, SEK→EURSEK`. (The v1/v2 EA only had 3 branches with a `1/EURUSD` catch-all → the Satellite-only JPY/NOK/SEK/CHF/CAD legs were mispriced ~117×/~10× below min-lot and never traded — see [`../../.../memory/v34-sleeve-dead-root-cause`].)

## 7. Symbol map & universe

33 symbols. Core US-index sleeve trades **USTEC** (`InpUS500=USTEC`). Repo→broker map applied once at load: `USA500=US500; DAX=DE40`, others identity.

---

## Reproduction

```
python3 model/v3/reproduce.py          # both, ~8-9 min, asserts €3,872,872 and €1,332,404
python3 model/v3/reproduce.py --ic     # IC only
python3 model/v3/reproduce.py --ftmo   # FTMO only
```
Instant cached reads: `research/outputs/hrisk1_results.json['base']['s160']` (IC), `research/outputs/preset_ftmo_data.json` / `hrisk2_ship_curve.parquet` (FTMO).

---

## ⚠ HONESTY FLAGS (carried from the campaign; the numbers above are the in-sample RECORD read)

1. **IC s=1.6 — margin at 1:30 is SAFER than the old flag said (corrected FMA3-RECON-4, 2026-07-12).** The pre-v3 flag claimed s=1.6 is undeployable at 1:30 (margin gate binds, band s0.6–0.8). The v3 EA disproves it: v3's own margin cap (0.9·balance on MODEL per-symbol leverage, which ≈ a 1:30 account's per-symbol grant) self-limits the book, so s=1.6 @ 1:30 ran the full 2020–2025 backtest with **min ML 121%** — far above IC's **50% stop-out** (a ~55% peak-book DD would be needed to liquidate, vs the 21% historical worst). It sits ~11pp above the owner's **ML≥110% self-limit** at the 2025 peak book, so it's near that floor but liquidation-safe. Owner is comfortable with s=1.6; **provisional IC ship dial = s=1.6, pending real-tick min-ML confirmation.** (Volume caps still trim ~6% at €10k scale — see the sweep section.)
2. **IC ship verdict provenance.** The €3.87M metric reproduces, but `run_hrisk1.py` main() (breach ceiling 0.15) would ship **none** — s=1.6 shipped only via the engine-free FMA3-004c re-adjudication that raised the breach cap 0.15→0.20.
3. **FTMO "fixed-base" is a scoring lens, not a sizing mode.** The €1.33M is **compounding** off live balance (`InpSizingBase=0`). "Fixed-base" only describes the offline FTMO rule frame (−€5,000 daily / €90,000 floor on the fixed 100k base), scored separately by `scripts/ftmo_model_v3.score_v3` — it does **not** produce the equity number.
4. **FTMO compound-vs-withdraw inconsistency.** €1.33M is fully-compounded never-withdraw equity, but the 5/5 compliance gates are scored under a **contradictory** monthly withdraw-to-base frame. You cannot both compound to €1.33M and reset to base monthly. €1.33M is an "if-compounded" upper figure.
5. **FTMO gates are COLD-START in-sample.** Warm re-validation shows s0.70 + 3% breaker breaches COVID by 7.5–10.8pp of the 10% rule; crisis-safe dial ≈ s0.30–0.35, not 0.70.
6. **The record has NO position ceiling; a real broker does (FMA3-RECON-4, 2026-07-12).** The engine sizes `lots = frac·balance/unit` with no cap. Real accounts enforce `SYMBOL_VOLUME_LIMIT` per symbol (IC 11078280: XAUUSD **10**, SOLUSD **1000**, ETHUSD **100** lots). As the book compounds past **~€2M/s** of equity, XAUUSD (the tightest) caps at ~half the model's target → **the €3.87M IC-s1.6 record is not physically reachable on one retail account at that scale.** This is a *second, independent* reason s=1.6 isn't deployable (alongside margin). The EA (FableFederation_V3) reproduces the model to **0.95×** at the deployable FTMO dial (s0.7, €1.27M, 0 volume rejects) but only 0.66× at s1.6. Scaling levers: higher-tier account, or N parallel accounts at €C/N (aggregate = model). Full record: `RECON4_RESULTS.md`.

**Both dashboards are in-sample record reads. MT5 real-tick + live demo are the remaining falsification tests. Achievable equity is 0.66–0.95× the record depending on dial/scale (RECON-4).**
