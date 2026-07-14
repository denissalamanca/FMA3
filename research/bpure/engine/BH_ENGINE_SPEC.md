# BH_ENGINE_SPEC — v34 native standalone account equity (b_h), scalar per-bar spec

Stage 6 of the B-pure port. This document is the field-for-field spec of the
1-minute cross-margined account engine that produces the v34 native standalone
equity curve. The MQL5 `V34EquityNative` must be written from THIS document;
the pure-python scalar reference is `bh_stepper.py` (same directory).

## 1. Lineage / ground truth

* **Engine of record**: `/Users/dsalamanca/vs_env/FableMultiAssets2/research/account_engine_1m.py`
  (`simulate_account_1m` + numba kernel `_run_chunk`, lines 91-208). The kernel
  is already a scalar per-bar loop — it IS the arithmetic spec. Frozen copy:
  `model/v3/freeze/FMA3-v34-freeze-1/src/research/account_engine_1m.py`
  (sha256 `700ea91515b62cd4973d3afb1d507a5d6d602798cad56efc17e19a7dfe9f7240`).
* **NOT in scope**: `FMA3/engine/record_engine_ext.py` adds `vol_limit` (inert
  at 0) and the FTMO daily circuit breaker (`_run_chunk_stop`). Neither exists
  in the b_h engine of record; `_run_chunk_stop` with an unfired stop is gated
  bit-identical to `_run_chunk`. b_h uses the plain kernel — no vol cap, no
  daily stop.
* **Ground truth curve**: `model/v3/freeze/FMA3-v34-freeze-1/golden/curve.parquet`
  — columns `equity` (eq_close) and `worst` (eq_worst), 2,948,650 1m rows,
  2020-01-02 00:00 → 2025-12-31 23:59 (broker server time, tz-naive).
  First row = 10000.0 / 10000.0 exactly (flat first bar).
* **Pin metrics** (FMA2 `research/outputs/v34_s10_pin_1m.json`):
  CAGR `0.8865880762592069`, MaxDD_worst `0.2167488591051508`,
  Sharpe `1.8543172985943566`, final `EUR 449707.7452664526`, n_trades from run.
* **Book input**: `golden/book.parquet` — hourly target matrix, 49,379 rows ×
  31 symbols, values = signed notional exposure as FRACTION OF JOINT ACCOUNT
  EQUITY (scale s=1.0 of the v34 s10 book — scale already baked in).
* **b_h consumption** (`model/v3/reproduce.py::load_inputs/static_fed`):
  `b = eq_close / eq_close.iloc[0]` (normalize to 1.0 at t0 = first 1m bar),
  then `b_h(hour) = b asof-ffilled onto the hourly union grid, fillna 1.0`
  (causal: last 1m close mark ≤ hour). The blend is
  `fed[h,k] = f7*(w*a_h/j) + f34*((1-w)*b_h/j)`, `j = w*a_h + (1-w)*b_h`, w=0.70.

## 2. Static configuration (per-symbol constants)

From FMA2 `core.S.INSTRUMENTS` (NSF5 `config/settings.py`), for the 31 book
symbols. `comm` = commission_side, EUR per lot PER SIDE. Values verified
2026-07-14 against the live config:

| symbol | quote | class  | contract | comm | lev | lot_step | min_lot |
|--------|-------|--------|----------|------|-----|----------|---------|
| AUDCAD | CAD   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| AUDJPY | JPY   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| AUDNZD | NZD   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| BTCUSD | USD   | crypto | 1        | 0.0  | 2   | 0.01     | 0.01    |
| CADCHF | CHF   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| CADJPY | JPY   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| DAX    | EUR   | index  | 1        | 0.0  | 20  | 0.1      | 0.1     |
| ETHUSD | USD   | crypto | 1        | 0.0  | 2   | 0.01     | 0.01    |
| EURCAD | CAD   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| EURCHF | CHF   | fx     | 100000   | 3.25 | 30  | 0.01     | 0.01    |
| EURGBP | GBP   | fx     | 100000   | 3.25 | 30  | 0.01     | 0.01    |
| EURNOK | NOK   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| EURNZD | NZD   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| EURSEK | SEK   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| EURUSD | USD   | fx     | 100000   | 3.25 | 30  | 0.01     | 0.01    |
| GBPJPY | JPY   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| JP225  | JPY   | index  | 1        | 0.0  | 20  | 0.1      | 0.1     |
| NZDCAD | CAD   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| NZDJPY | JPY   | fx     | 100000   | 3.25 | 20  | 0.01     | 0.01    |
| SOLUSD | USD   | crypto | 1        | 0.0  | 2   | 0.01     | 0.01    |
| UK100  | GBP   | index  | 1        | 0.0  | 20  | 0.1      | 0.1     |
| US30   | USD   | index  | 1        | 0.0  | 20  | 0.1      | 0.1     |
| USA500 | USD   | index  | 1        | 0.0  | 20  | 0.1      | 0.1     |
| USDCHF | CHF   | fx     | 100000   | 3.25 | 30  | 0.01     | 0.01    |
| USDJPY | JPY   | fx     | 100000   | 3.25 | 30  | 0.01     | 0.01    |
| USTEC  | USD   | index  | 1        | 0.0  | 20  | 0.1      | 0.1     |
| XAGUSD | USD   | metal  | 5000     | 3.25 | 10  | 0.01     | 0.01    |
| XAUUSD | USD   | metal  | 100      | 3.25 | 20  | 0.01     | 0.01    |
| XBRUSD | USD   | metal  | 1000     | 0.0  | 10  | 0.01     | 0.01    |
| XNGUSD | USD   | metal  | 10000    | 0.0  | 10  | 0.01     | 0.01    |
| XTIUSD | USD   | metal  | 1000     | 0.0  | 10  | 0.01     | 0.01    |

Account constants:

* `initial = 10_000.0` EUR
* `stop_out_level = 0.5` (`core.S.ACCOUNT["stop_out_level"]`; the driver in
  record_engine_ext asserts it is exactly 0.50 — NSF5's lock_v5 import
  side-effect can poison it to 1e-9 in-process)
* `margin_cap = 0.9`
* `rebalance_band = 0.25`

All arithmetic is IEEE-754 float64, round-to-nearest, NO fastmath (numba njit
default). Evaluation order below is normative — float64 associativity matters.

## 3. Per-bar inputs (index t = one union-grid minute; k = symbol 0..30)

The union grid is `np.unique(concat of native 1m stamps)` over the 31 traded
symbols PLUS the EUR crosses (see eurq), per calendar quarter 2020Q1..2025Q4
(quartering exists only for memory; bar-level inputs are chunk-invariant
because ffill indexes the FULL native array). Feed source:
`NSF5/cache/bars_1m_ic/{SYM}_IC_1m.parquet`, tz-naive broker SERVER time.

Per symbol k at minute t the stepper consumes 11 scalars:

| input      | derivation |
|------------|------------|
| `tgt`      | hourly book row at `prev_hour = floor(t,'h') - 1h`, EXACT index match (`reindex`, no ffill), NaN→0.0. I.e. the hour-h signal is held over every minute of hour h+1 — ≥1-minute causal gap. |
| `has_bar`  | True iff the symbol has a NATIVE bar stamped exactly at t. |
| `bid_o, ask_o, bid_c, ask_c, bid_l, ask_h` | native fields of the last native bar ≤ t (forward-fill of stale bars); before the symbol's first-ever bar: the FIRST bar's values. Stored float32 in the parquet, upcast to float64 (`float32 → float64` exact). |
| `eurq`     | EUR value of 1 unit of the symbol's QUOTE currency at t: `1.0` if quote is EUR, else `1.0 / cross_mid_close(t)` where `cross_mid_close = 0.5*(bid_c + ask_c)` of the EUR cross, ffilled on the same grid rule. Crosses: USD→EURUSD, JPY→EURJPY, GBP→EURGBP, CHF→EURCHF, NZD→EURNZD, CAD→EURCAD, NOK→EURNOK, SEK→EURSEK. ONE eurq per bar (from the cross's bar CLOSE) is used for everything in the bar — swaps, sizing, fills, marks. |
| `swap_l, swap_s` | 0.0 except at the ROLLOVER MINUTE: the first grid minute ≥ server midnight (00:00) of each calendar day d. Skipped entirely when d is Sat/Sun and the symbol is non-crypto. Value: `annual_pct/100.0/365.0 * mult` where `mult` = 3 on Wednesday for fx/metal (T+2 triple), 3 on Friday for index, else 1; crypto: 1 every calendar day. `annual_pct` (long, short) from NSF5 `engine/costs.py::swap_annual_pct`: fx/metal `(rb-rq-mk, rq-rb-mk)` with policy-rate step tables and markup mk=1.2 (AUDUSD override 2.0 — not in this book); index `(-(rq+4.3), rq-4.3)`; crypto `(-20.0, 0.0)` %/yr flat. If several calendar days map to the same first grid minute (weekend gap for non-crypto is skipped, but e.g. a Monday whose 00:00 minute is the first bar after Friday), accruals ADD (`+=`) at that minute. |

Note for MQL5: prices in the record feed are float32-quantized then upcast.
Bit-exact parity against the golden curve therefore requires replaying the
same float32-rounded prices; a live double-precision feed is "pricing
faithful" but not bit-identical.

## 4. Persistent state (the ONLY carry between bars; JSON-serializable)

| field      | type      | init      | meaning |
|------------|-----------|-----------|---------|
| `balance`  | float64   | 10_000.0  | realized cash, EUR (swaps, realized pnl, commissions) |
| `lots[31]` | float64[] | 0.0       | signed open lots per symbol |
| `entry[31]`| float64[] | 0.0       | volume-weighted average entry price (0.0 when flat) |
| `n_trades` | int       | 0         | fill counter (diagnostic; each executed close-branch or open-branch = 1) |

Outputs per bar: `eq_c` (close-mark joint equity) and `eq_w` (worst co-timed
mark). These are NOT state — they are recomputed each bar.

## 5. Per-bar update order (normative, from `_run_chunk` lines 108-207)

### Step 1 — swaps at the rollover minute
For k = 0..30, if `lots[k] != 0` and (`swap_l != 0` or `swap_s != 0`):
```
mid      = 0.5 * (bid_o + ask_o)
notional = abs(lots[k]) * contract[k] * mid * eurq          # left-to-right
balance += notional * (swap_l if lots[k] > 0 else swap_s)
```

### Step 2 — desired lots from the shared balance
For k = 0..30 (`g = tgt[k]`):
* `not has_bar` → `desired[k] = lots[k]` (carry; NO margin contribution), next k.
* `g == 0.0` → `desired[k] = 0.0`, next k.
* else:
```
px    = ask_o if g > 0 else bid_o        # entry side by target sign
unit  = px * contract[k] * eurq          # EUR per lot
raw   = g * balance / unit               # (g*balance) first, then /unit
n     = floor(abs(raw) / lot_step[k] + 1e-9)
L     = n * lot_step[k]
if L < min_lot[k]: L = 0.0
desired[k] = sign(g) * L
margin_sum += abs(desired[k]) * unit / leverage[k]
```
Margin-cap shrink (margin only counts the NEW desired book, sized from
BALANCE not equity):
```
shrink = 1.0
cap    = balance * margin_cap            # 0.9 * balance
if margin_sum > cap and margin_sum > 0.0: shrink = cap / margin_sum
```

### Step 3 — execute fills at this minute's OPEN (cross the spread)
For k = 0..30, skip if `not has_bar`. Then:
```
want = desired[k] * shrink
n    = floor(abs(want) / lot_step[k] + 1e-9)                 # re-floor after shrink
want = sign(want) * n * lot_step[k]
if abs(want) < min_lot[k]: want = 0.0
```
Rebalance band (skip small same-direction adjustments):
`if lots[k] != 0 and want != 0 and want*lots[k] > 0 and abs(want - lots[k]) / abs(lots[k]) <= 0.25: continue`
`if want == lots[k]: continue`

CLOSE/REDUCE branch — `if lots[k] != 0 and (want == 0 or want*lots[k] < 0 or abs(want) < abs(lots[k]))`:
```
close_lots = lots[k] if want*lots[k] <= 0.0 else lots[k] - want
px   = bid_o if lots[k] > 0 else ask_o                       # exit side
pnl  = (px - entry[k]) * close_lots * contract[k] * eurq
balance += pnl - comm[k] * abs(close_lots)                   # rhs first, one add
lots[k] -= close_lots
n_trades += 1
if lots[k] == 0.0: entry[k] = 0.0
```
OPEN/EXTEND branch — `if want != 0 and abs(want) > abs(lots[k])` (a sign flip
runs BOTH branches in the same bar: full close above leaves lots=0, then):
```
add = want - lots[k]
px  = ask_o if add > 0 else bid_o                            # entry side
entry[k] = px                          if lots[k] == 0.0
         = (entry[k]*lots[k] + px*add) / (lots[k] + add)     otherwise
balance -= comm[k] * abs(add)
lots[k]  = want
n_trades += 1
```

### Step 4 — joint marks (co-timed at this minute)
Accumulate in k order (0..30), skip `lots[k] == 0`:
```
long : unreal_c += (bid_c - entry[k]) * lots[k] * contract[k] * eurq
       unreal_w += (bid_l - entry[k]) * lots[k] * contract[k] * eurq
short: unreal_c += (ask_c - entry[k]) * lots[k] * contract[k] * eurq
       unreal_w += (ask_h - entry[k]) * lots[k] * contract[k] * eurq
mid_c        = 0.5 * (bid_c + ask_c)
margin_used += abs(lots[k]) * contract[k] * mid_c * eurq / leverage[k]
eq_c = balance + unreal_c
eq_w = balance + unreal_w
```
`eq_w` is the intrabar WORST joint mark under the co-timed assumption: every
long marked at its bar LOW bid, every short at its bar HIGH ask, same minute.

### Step 5 — joint stop-out / liquidation
`if margin_used > 0 and eq_w < stop_out_level * margin_used` (0.5 = 50%
margin level on the worst mark):
```
for k = 0..30 with lots[k] != 0:
    px = bid_l if lots[k] > 0 else ask_h        # liquidate AT the worst-side price
    balance += (px - entry[k]) * lots[k] * contract[k] * eurq  - comm[k]*abs(lots[k])
    lots[k] = 0.0; entry[k] = 0.0
eq_c = balance; eq_w = balance                  # both marks overwritten
```

Return `(eq_c, eq_w)`.

## 6. Metrics tail (for the parity gate, not the stepper)

* CAGR/Sharpe: `core.compute_metrics(eq_c / initial)` on the CLOSE curve.
* `maxdd_worst = max( (peak - eq_w) / max(peak, 1e-9) )` where
  `peak = running max of eq_c` — worst mark against the CLOSE-curve peak.
* `final_equity = eq_c[last]`.

## 7. Float-discipline notes for the MQL5 port

1. Multiplications are left-to-right as written; do not refactor
   `a*b*c*d` groupings or fold `/unit` into a reciprocal.
2. `floor(x + 1e-9)` is the lot quantizer (both in sizing and post-shrink);
   `sign()` must return ±1.0/0.0 (never NaN here — tgt is NaN-scrubbed).
3. `balance += pnl - comm*lots` is ONE addition of a pre-computed rhs.
4. Commission is charged per side, per lot, in EUR, on every open/extend and
   every close/reduce and on stop-out liquidation.
5. The rebalance-band division `abs(want-lots)/abs(lots)` only runs when
   `lots != 0` (guarded).
6. No vol_limit, no daily stop, no spread floor, no slippage model: the only
   costs are spread-crossing at bar open, commission, and swap.
7. Bit parity with the golden curve additionally requires the float32-quantized
   price feed (section 3 note) and the exact swap tables (NSF5 policy-rate
   step tables; flat-extension semantics past the last entry).

## 8. Validation gate (measured 2026-07-14, bh_stepper.py `--selfcheck`)

Per-quarter, the pure-python stepper is run bar-by-bar on THE SAME input
arrays `simulate_account_1m` builds (its own `_native/_densify/_eurq_chunk/
_swap_chunk` code paths, imported read-only) and compared against the numba
kernel `_run_chunk` output with `np.array_equal` (bitwise), plus against the
golden curve slice.

**MEASURED RESULT** (`python3 bh_stepper.py --selfcheck 2020Q1 2025Q4`,
run 2026-07-14): all 24 quarters BIT-EQUAL vs the numba kernel (eq_c, eq_w,
carry balance/lots/entry/n_trades) AND BIT-EQUAL vs the golden curve; total
bars 2,948,650 = the full golden curve (coverage verified); final realized
balance EUR 434,132.98905617336, n_trades 20,403, final eq_close =
golden 449,707.7452664526 (implied by bitwise curve equality); state JSON
roundtrip OK. Scalar throughput ~5-7 s per quarter (~2.4 min total).
Raw log: scratchpad `bh_selfcheck_full.json`.
