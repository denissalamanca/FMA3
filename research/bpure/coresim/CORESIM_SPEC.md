# CORESIM_SPEC — Core idealized standalone account equity (a_h), design + scalar spec

Track B of the B-pure port. This document is (1) the dissection of what the
Core standalone shadow actually is, (2) the field-for-field scalar spec the
MQL5 `CoreSim.mqh` is written from, and (3) the validation-harness plan.
The pure-python scalar reference is `coresim_reference.py` (same directory);
its measured parity results are in section 8.

## 1. What a_h is (parity target + semantics)

* **Parity target**: `research/outputs/v7_book_equity_1m.parquet`
  [legacy on-disk name — this IS the Core book equity artifact], columns
  `eqc` (close-mark combined equity), `eqw` (worst co-timed mark), `margin`
  (summed used margin, EUR). 2,947,085 1m rows on the committed union grid,
  2020-01-02 00:00 → 2025-12-31 23:59, tz-naive broker SERVER time (IC feed).
  First row 10000.0; final eqc 532229.8433634703.
* **Semantics**: NOLIQ (stop_out_level = 1e-9 — the lock_v5 import
  side-effect; the account never liquidates), notional sizing, close-mark
  equity for `eqc`, per-leg intrabar worst co-timed marks for `eqw` (longs at
  bar-low bid, shorts at bar-high ask, off-bar legs contribute their ffilled
  CLOSE mark — the 2026-07-02 phantom-simultaneity audit convention).
  `eqw` is what "worst-mark" means for this curve; the 1m worst-mark
  engine-of-record convention reads MaxDD off `eqw` against the `eqc` peak.
* **Blend consumption** (`model/v3/reproduce.py::static_blend`):
  `a = eqc / eqc.iloc[0]` (normalize to 1.0 at the first bar), then
  `a_h(hour) = a` asof-ffilled onto the hourly union grid, `fillna(1.0)`.
  `j = w*a_h + (1-w)*b_h`, `w = 0.70`; `f_core` rows are multiplied by
  `w*a_h/j`. a_h is a FROZEN native curve: the v3 EA REPLAYS it (computing it
  live at s≠1 diverges — stable-model-v3 canonical rule).
* **Producer / engine of record chain**:
  `engine/v7_bridge/extract_positions.py` (FMA3, gate `status=reconciled` in
  `research/outputs/v7_extract_verification.json`) = bit-exact re-run of the
  NSF5 anchor: `gbandrebal/sim.py::run_generic` →
  `v51_bandharvest._run_window` → `engine/backtest.py::_run_core`
  (numba, strict-FP njit), book `sim.book("BTC_REP","USTEC")`, band triggers
  `up=0.25, down=(1/7)/1.75, kmult=2.5, min_gap_days=5`, window
  [2020-01-01, 2026-01-01), INIT=10000 EUR.

## 2. Dissection: CoreEngine.mqh vs the idealized standalone shadow

`mt5/ea/Include/Core/CoreEngine.mqh` is the G1-proven LIVE-ACCOUNT tracker
(real-tick, proven to the cent at €398,368.75). It is NOT the a_h engine and
CANNOT be forked into one by feeding it offline bars. The differences are
structural, not parametric:

| aspect | CoreEngine.mqh (real-account tracker) | a_h idealized standalone (anchor) |
|---|---|---|
| state/inputs | terminal services: `CopyRates` M1 series (rebuilt daily series w/ pre-20:00 EURGBP variant), `SymbolInfoDouble` live bid/ask & contract/step/min/max/limit, `OrderCalcMargin`, `PositionsTotal/HistoryDeals` ledger, `TimeCurrent/TimeGMT`, CTrade order path | pure arrays: per-leg native 1m bid/ask OHLC, precomputed `eurq` (EUR-cross close-mid asof), precomputed swap accrual arrays, precomputed per-minute TARGET arrays; no terminal calls at all |
| signals | recomputed live from its own daily series (donch/SMA/z-score...), stamped 00:00 / 20:00 / 07:05 | baked INTO the target arrays by NSF5 `book()`; the account engine never sees a signal, only targets |
| accounting | ONE shared broker account; per-sleeve VIRTUAL sub-ledger `g_seed+g_realized` from deal history by magic; floating P&L read from broker positions | NINE fully separate per-leg accounts (own balance/pos/entry), each compounding on its own equity; book equity = SUM of leg curves on the union grid |
| fills/costs | broker fills at live tick, broker commission/swap as charged, reject/backoff seams (F3), volume max/limit splits, margin governor | fill at bar OPEN crossing the spread; commission = config `commission_side` EUR/lot/side; swap = policy-rate model at the NY-17:00 rollover minute (triple Wed fx/metal, triple Fri index, daily crypto); no rejects, no volume ceilings (only lot_step/min_lot/margin_cap 0.9 vs balance) |
| liquidation | real broker stop-out (50% ML) is possible | NOLIQ (1e-9): the shadow never liquidates — a_h is deliberately the no-stop-out curve |
| re-split trigger | `BandTriggered()` at UTC-day rollover on VBalance+FloatingPnL slot equity, min-gap vs `g_quarterStart` seconds, S6 legs summed into one slot | daily-close combined-curve slot equity (`resample('D').last()` + flat legcap), share test up 0.25 / floor (1/7)/1.75, decided at day-close label d, ACT at d+1 00:00, min-gap `(d - segment_start).days >= 5`; harvest k=2.5 also armed (never fired: 31/31 triggers are band) |
| reseed | orders to move real positions to equal-capital targets; ledger reseeded from pooled equity | segment ENDS at act date t; every leg is closed implicitly (window end) and a FRESH per-leg account starts at t with `legcap = seed*(1/7)/n_legs`, seed = combined eqc at the last bar < t; window-end close costs are inside the committed curve ("no splice flattery") |

Conclusion of the dissection: the tractable path is NOT to run CoreEngine.mqh
offline; it is a NEW small engine (`CoreSim.mqh`) implementing the anchor's
per-leg account arithmetic + combiner + frozen-trigger segment replay, fed by
exported input arrays. The signal layer stays in Python (targets are inputs),
exactly like Track A's book replay contract.

## 3. Book structure (fixed for a_h)

`sim.book("BTC_REP","USTEC")` = 7 slots, 9 legs, `W = 1.0/7.0`:

| slot | legs (inst) | notes |
|---|---|---|
| BOOK_XAU | XAUUSD | gold donch(50,100) + night VA, defer_reopen |
| S5_JPY | USDJPY | jpy_smart |
| S1_ETH | ETHUSD | crypto momentum |
| ZC_EG | EURGBP | z-score ensemble |
| BOOK_USTEC | USTEC | us500_book_v33 vt=0.85R, defer_reopen |
| S6_OPEXUSD | USDJPY, AUDUSD, NZDUSD | 3 legs — legcap divisor 3 |
| BTC_REP | BTCUSD | financing-hurdle momentum |

USDJPY appears in TWO legs (different target arrays, separate accounts).
`legcap = seed * W / n_legs_in_slot` — evaluation order `(seed*W)/n` is
normative (float64).

Per-symbol constants (NSF5 `config/settings.py::INSTRUMENTS`):

| symbol | quote | class | contract | comm/side | lev | lot_step | min_lot |
|---|---|---|---|---|---|---|---|
| XAUUSD | USD | metal | 100 | 3.25 | 20 | 0.01 | 0.01 |
| USTEC | USD | index | 1 | 0.0 | 20 | 0.1 | 0.1 |
| USDJPY | JPY | fx | 100000 | 3.25 | 30 | 0.01 | 0.01 |
| ETHUSD | USD | crypto | 1 | 0.0 | 2 | 0.01 | 0.01 |
| EURGBP | GBP | fx | 100000 | 3.25 | 30 | 0.01 | 0.01 |
| AUDUSD | USD | fx | 100000 | 3.25 | 20 | 0.01 | 0.01 |
| NZDUSD | USD | fx | 100000 | 3.25 | 20 | 0.01 | 0.01 |
| BTCUSD | USD | crypto | 1 | 0.0 | 2 | 0.01 | 0.01 |

Account constants: `INIT=10000.0`, `stop_out=1e-9` (noliq), `margin_cap=0.9`,
`rebalance_band=0.25`. All arithmetic IEEE-754 float64, no fastmath. The NSF5
IC bar caches are float64 (verified — no float32 quantization landmine here,
unlike the Satellite record feed).

## 4. Per-leg inputs (all precomputed, exported to the MQL5 side)

Per leg, on the leg's NATIVE 1m bar index restricted to the segment window
[t0, t1) (`index >= t0 & index < t1`; masking outside the window is
equivalent to starting flat at t0 with balance=legcap — proven exact, see
§5 note):

| input | derivation (NSF5 `engine/backtest.prep_arrays`) |
|---|---|
| `bid_o..ask_c` | native float64 bar fields |
| `eurq` | EUR per quote-ccy unit: 1/cross close-mid, last cross bar ≤ t (`searchsorted right -1`, clip ≥ 0). Crosses: USD→EURUSD, JPY→EURJPY, GBP→EURGBP. ONE eurq per bar for swap, sizing, fills, marks, margin. |
| `swap_flag, swap_long, swap_short` | at the first native bar ≥ 17:00-New-York (DST-correct) of each calendar day d: `flag += mult` (mult = 3 Wed fx/metal, 3 Fri index, else 1; crypto every day incl. weekends; non-crypto weekend days skipped), `swap_long/short = annual_pct/100.0` from the policy-rate step tables (fx/metal `(rb-rq-1.2, rq-rb-1.2)`; index `(-(rq+4.3), rq-4.3)`; crypto `(-20,0)`). NOTE: rollover is 17:00 NY — NOT the server-midnight convention of the Satellite b_h engine. |
| `target` | per-minute signed notional multiple of leg balance, from `sim.book()`; float64, NaN-free in every committed window (measured: 0 NaNs across all 32 segments). |

## 5. Per-leg stepper (normative scalar spec — `CCoreLegSim::StepBar`)

Statement-for-statement port of NSF5 `_run_core`, NOTIONAL mode, with the
structurally-dead branches stripped but guarded: sl/tp never armed (NaN),
`dd_k=0`, `throttle_thr=0`, stop-out threshold 1e-9 (test retained,
liquidation is an assertion failure in the shadow).

State per leg (reset to `balance=legcap, pos=0, entry=0` at every segment
start): `balance, pos, entry` float64.

Per bar (in-window bars only):

```
mid_o = 0.5*(bid_o + ask_o)
# 1. swap
if swap_flag > 0 and pos != 0:
    frac      = swap_long if pos > 0 else swap_short
    notional  = abs(pos) * contract * mid_o                 # left-to-right
    balance  += notional * frac / 365.0 * swap_flag * eurq
# 2. sizing (notional)
tgt   = target
sgn_t = 0 if tgt==0 else sign(tgt); sgn_p = 0 if pos==0 else sign(pos)
desired = 0.0
if sgn_t == 0: want_change = (pos != 0)
else:
    px       = ask_o if sgn_t > 0 else bid_o
    unit_eur = px * contract * eurq
    lots     = balance * abs(tgt) * 1.0 * 1.0 / unit_eur    # dd/thr scales kept literal
    max_lots = (balance * leverage * 0.9) / unit_eur
    if lots > max_lots: lots = max_lots
    n = floor(lots/lot_step + 1e-9); lots = n*lot_step
    if lots < min_lot: lots = 0.0
    if sgn_t != sgn_p:                      want_change = True; desired = sgn_t*lots
    elif pos != 0 and abs(lots-abs(pos))/abs(pos) > 0.25:
                                            want_change = True; desired = sgn_t*lots
    else:                                   want_change = False
# 3. fills at open
if want_change and (desired - pos) != 0:
    if pos != 0 and (desired==0 or desired*pos<0 or abs(desired)<abs(pos)):
        close_lots = pos if desired*pos <= 0 else pos - desired
        px  = bid_o if pos > 0 else ask_o
        pnl = (px - entry) * close_lots * contract * eurq
        balance += pnl - comm*abs(close_lots)               # ONE add of pre-built rhs
        pos -= close_lots
    if desired != 0 and abs(desired) > abs(pos):
        add = desired - pos
        px  = ask_o if add > 0 else bid_o
        entry = px if pos == 0 else (entry*pos + px*add)/(pos + add)
        balance -= comm*abs(add)
        pos = desired
# 4. marks
long : unreal_c=(bid_c-entry)*pos*contract*eurq ; unreal_w=(bid_l-entry)*...
short: unreal_c=(ask_c-entry)*pos*contract*eurq ; unreal_w=(ask_h-entry)*...
flat : 0 / 0
eq_c = balance + unreal_c ; eq_w = balance + unreal_w
# 5. margin (+ noliq stop-out guard, must never fire)
if pos != 0:
    mid_c  = 0.5*(bid_c + ask_c)
    margin = abs(pos) * contract * mid_c * eurq / leverage
    if eq_w < 1e-9*margin: ASSERT-FAIL (never in the anchor)
else margin = 0
```

Float discipline identical to the b_h spec: no regrouping, `floor(x+1e-9)`
quantizer, one-add balance updates, commission per side per lot in EUR.

**Window-start exactness note**: the anchor runs each leg over its FULL bar
array with targets masked to 0 outside [t0,t1). Pre-window the leg is
provably inert (pos=0 → no swap, no fill, no forced exit), so starting the
loop at the first in-window bar with fresh state is bit-exact. Measured:
gate G-a below.

## 6. Combiner + segment replay (normative)

### 6.1 Combine (per segment)

Legs are appended in book order (slot dict order, legs in list order),
SKIPPING legs with no bars in the window (each contributes `flat += legcap`
instead). On the union of the appended legs' in-window stamps:

* close: `c_f(t)` = leg's last own-bar eq_c ≤ t; BEFORE the leg's first
  in-window bar: the leg's FIRST in-window eq_c (`fillna(c.iloc[0])` —
  deliberate anchor semantics; a streaming implementation must buffer, which
  is why CoreSim combines leg-major, not time-major).
* worst: leg's own eq_w ONLY at its own bar stamps; elsewhere `c_f(t)`.
* margin: leg's own margin ffilled, 0.0 before the leg's first bar.
* Summation order is PER-ELEMENT LEFT-TO-RIGHT in leg append order
  (`((l0+l1)+l2)+...`); margin starts from 0.0 (`0+m0+m1...`).
* Finally `eqc += flat`, `eqw += flat` (single add; margin gets no flat).

### 6.2 Segment replay with FROZEN triggers

The committed run is 32 segments (t0/t1 in
`v7_extract_verification.json:segments`; 31 band triggers, 0 harvest).
Seed chain: `seed_0 = 10000.0`; `seed_j` = combined eqc at the LAST union bar
< t0_j (== `triggers[j-1].book`, asserted bit-equal in the reference).
`legcap = seed * (1.0/7.0) / n_legs` per slot.

**CoreSim REPLAYS the frozen act dates. It does NOT re-detect triggers.**

### 6.3 Band-trigger DATE fork risk (why detection is out of scope)

Re-deriving the trigger dates live is a known fork surface — any 1-day fork
re-times every later segment and destroys parity. Documented forks between
the anchor (`sim.first_share_trigger`) and the EA (`CoreEngine.BandTriggered`):

1. **min-gap basis**: anchor requires `(decision_day d - segment_start).days
   >= 5`; the EA tests `TimeCurrent() - g_quarterStart >= 5*86400` at the ACT
   moment (≈ d+1) — the EA can fire ONE DAY earlier.
2. **slot-equity marks**: anchor uses daily `resample('D').last()` of the
   per-leg combined CLOSE curves + flat legcap; the EA uses broker
   VBalance+FloatingPnL at the rollover tick. Same intent, different marks.
3. **slot_frame `.ffill().bfill()`**: the anchor BACKFILLS slot columns whose
   first daily point is later than the frame start — an edge-of-frame
   convention a live detector cannot reproduce causally.
4. **S6 slot aggregation**: the EA sums 3 S6 legs into one slot (correct vs
   the 7-slot rule) — any per-sleeve iteration would misfire the floor.
5. **probe-window act constraint**: anchor requires `cur < act < probe_hi`
   — act dates landing exactly on a probe edge are re-found by the longer
   probe; a live detector has no probe structure.

These are recorded so a FUTURE live-detection mode can be reconciled
deliberately; for a_h parity they are moot — frozen replay only.

## 7. MQL5 deliverable + validation harness plan

* **`mt5/ea/Include/Core/CoreSim.mqh`** (this pass, compiled 0/0):
  `CCoreLegSim` (the §5 stepper), `CCoreBookSim` (leg registry, legcap
  seeding `(seed*W)/n`, per-leg series capture, §6.1 combiner, flat handling,
  final-eqc exposure for seed chaining). No terminal trading calls — pure
  compute, usable from a Script.
* **`mt5/ea/scripts/TestCoreSim.mq5`** (this pass, compiled 0/0): offline
  replay harness, Track-A chained pattern. Reads per-segment input files
  from FILE_COMMON (`FMA3_coresim_seg{J}.csv` — leg-major rows
  `leg_id,epoch_sec,bid_o,bid_h,bid_l,bid_c,ask_o,ask_h,ask_l,ask_c,eurq,
  swap_flag,swap_long,swap_short,tgt`, doubles %.17g; plus a manifest
  `FMA3_coresim_segments.csv` = `j,t0_epoch,t1_epoch,n_rows`), runs segments
  in order chaining the seed internally, writes
  `FMA3_coresim_actual_seg{J}.csv` (`epoch_sec,eqc,eqw,margin`, %.17g).
* **STILL MISSING to run the harness** (staged, not claimed):
  1. `export_coresim_inputs.py` — exports the per-segment leg feeds from
     `prep_arrays` + `book()` (the §4 arrays; ~2-6 GB CSV total across 32
     segments, or per-segment on demand);
  2. `validate_mql5_coresim.py` — compares actual CSVs to the parity parquet
     slices (target: 0 ULP, i.e. bit-equal after %.17g round-trip);
  3. a terminal run (owner-gated; scripts only, no trading).
* **Parity gates for the MQL5 run**: per segment — index equality, bit
  equality of eqc/eqw/margin vs the parquet slice; chained seed must
  reproduce `triggers[j].book` at every boundary; full-run final eqc
  532229.8433634703.

## 8. Measured validation (coresim_reference.py, run 2026-07-14)

`cd FMA2/research && python3 coresim_reference.py --all` (gates G-a/G-b/G-c
per segment; raw JSON: `coresim_parity.json`):

* **ALL 32/32 committed segments PASS.** Total bars 2,947,085 = the full
  parity parquet (coverage complete).
* G-a: every leg of every segment BIT-EQUAL (np.array_equal) vs the NSF5
  numba `run_backtest` on eq_c / eq_w / margin.
* G-b: combined eqc / eqw / margin BIT-EQUAL vs
  `v7_book_equity_1m.parquet` on every segment; index equality on every
  segment (max_abs_d* = 0.0 everywhere).
* G-c: every seed bit-equal to the parquet carry AND to the recorded
  `triggers[j-1].book`.
* 0 NaN targets in-window; 0 stop-outs; 0 leg deaths. Runtime 58.8 s
  (scalar ~1-2 s per segment).

## 9. Risks / open items

1. **MQL5 FP parity**: MQL5 doubles are IEEE-754 binary64 and the port keeps
   expression shapes; residual risk is compiler re-association — mitigate
   with the same %.17g CSV round-trip discipline as Track A and the
   per-segment bit gate.
2. **Combiner memory**: largest segment (seg 19, 2022-12→2023-09) is 370,993
   union bars, ~3.3M leg-bar rows — dynamic-array sized, fine for a Script;
   the harness must size-check `ArrayResize` returns.
3. **Input volume**: full-run CSV export is multi-GB; per-segment export (or
   binary doubles) keeps peak disk sane. The reference validates the
   arithmetic regardless.
4. **eurq/swap export fidelity**: the MQL5 side consumes the EXPORTED arrays
   (never recomputes rollover/policy tables) — recompute forks (17:00-NY DST,
   policy step dates) are thereby impossible by construction.
5. **a_h consumption seam**: the blend divides by `eqc.iloc[0]` = 10000.0
   exactly and asof-ffills hourly with fillna(1.0) — trivial, but belongs to
   the blend track, not CoreSim.

## 10. f_core extension (TRACK B, FABLE REVISION v2 item 1 — option (c))

**Identity (MEASURED, (c)-VIABLE).** The frozen
`research/outputs/v7_book_frac_1h.parquet` [legacy name] — the Core book's
held frac-of-own-equity per NET symbol, 8 alphabetical columns AUDUSD,
BTCUSD, ETHUSD, EURGBP, NZDUSD, USDJPY, USTEC, XAUUSD, 49,355 hourly rows —
is EXACTLY reproducible from CoreSim state (fcore_identity.json,
fcore_reference.py, 2026-07-14):

    f_core[net] = net_lots * contract * mid_c * eurq / book_eqc

* `net_lots` — sum of member-leg positions in LEG APPEND ORDER (USDJPY =
  legs 1 and 5), position captured AFTER fills (the anchor's
  `_run_core_pos` capture point), forward-filled on the union grid
  INCLUDING segment seams (the previous segment's final position carries
  until the leg's first bar of the new segment);
* `mid_c` = (bid_c+ask_c)*0.5 and `eurq` — forward-filled from the
  instrument's own bars (the carry triple at seams);
* `book_eqc` — the combined close-mark book equity incl. flat legcap
  (section 6), i.e. division by the BOOK, not by any leg-equity sum;
* hourly row at hour start h = snapshot at the LAST 1m union bar in
  [h, h+1); symbols before their first-ever bar contribute 0.
* NORMATIVE grouping: `((net_lots * contract) * mid_c) * eurq / eqc`.

Measured verdicts on the full grid (max |diff| vs the frozen parquet):
H4 net-notional/book-eqc **0.0 on all 8 columns (bit-equal)**;
equity-weighted / notional-sum-over-leg-equity-sum (USDJPY) 17.2 — DEAD;
tgt-sum (USDJPY) 24.2 — DEAD; naive single-leg tgt passthrough 1.08–18.2
per symbol — DEAD (lot rounding + 25% rebalance band + margin cap + the
open-time leg-equity vs close-time book-equity denominators).

**MQL5 implementation** (`Core/CoreSim.mqh`): `CCoreLegSim` captures the
per-bar triple (pos, mid_c, eurq); `CCoreBookSim` adds `SetNets` /
`AssignLegNet` / `ComputeFCore` (call after EVERY `FinishSegment` in chain
order) with cross-segment carry per leg and last-bar-in-hour overwrite
emission; accessors `FCoreRows/FCoreTs/FCoreAt`. Harness:
`mt5/ea/scripts/CheckFCore.mq5` (same exporter inputs as TestCoreSim,
writes `FMA3_fcore_actual.csv`), compiled 0 errors / 0 warnings
(TestCoreSim regression also 0/0).

**Gates.** The MQL5 ALGORITHM (cursor + carry + hourly overwrite) has a
mechanical python twin: `validate_mql5_fcore.py --sim` — PASS, bit-equal
0.0 on all 8 columns over the full grid (fcore_mqhsim.json). STAGED for the
terminal: run CheckFCore.mq5 on the export_coresim_inputs.py inputs, then
judge with `validate_mql5_fcore.py` (writes fcore_mql5_parity.json) — that
run isolates only the MQL5 language layer, exactly the RECON-8d discipline.
