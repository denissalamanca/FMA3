# FableBookNative — Lens 3 WARM-START design (the un-golden seam)

**Scope.** How `FableBookNative.mq5` brings every stateful component to the
CORRECT state before it trades a live bar, so the COVID-cold-start-k≈4.7
artifact (memory: `record-engine-covid-warmup-artifact`) does not corrupt early
output. Components (all terminal-proven on frozen replay): 9 Satellite signal
steppers → `f_sat`; `CoreEngine.mqh` → `f_core`; `CoreSim.mqh` → `a`;
`SatEquityNative.mqh` → `b`; `BookBlend.mqh` → `book_frac`.

**Status of this doc:** DESIGN only. Numbers below are READ from the frozen
steppers/specs (cited). Every MT5-behavior uncertainty is flagged, not asserted.

---

## 0. The finding that inverts the naive instinct — READ THIS FIRST

The Lens-3 prompt says "seed all component state from ≥2019 history." **For the
in-sample reproduction that is WRONG and would BREAK parity.** The frozen model
of record (`a`, `b`, `f_core`, `f_sat`, and therefore `book_frac`) was itself
computed by engines that **cold-start at the model t0 = 2020-01-02 00:00** with
EMPTY indicator state (NSF5/record-engine begin their EWMs/Donchians/rings from
the first bar). This is exactly the memory artifact: the record engine is BLIND
in COVID because its indicators are warming up — and that blindness is BAKED
INTO the golden curves the EA must match. A 2019 warm-up would give the EA a
DIFFERENT (arguably better) COVID state than the golden → guaranteed divergence.

Therefore the warm-start splits into two **distinct** use cases that need
opposite treatment:

| Use case | What "warm" means | Pre-2020 data? |
|---|---|---|
| **A — in-sample tester reproduction (RECON-9)** | FRESH/empty state at model t0; begin computing at the first union bar. The cold-start era is part of the golden; matching it *requires* cold-starting too. | **NO — forbidden.** |
| **B — live forward deploy past 2025-12-31, or EA restart mid-run** | Restore the EXACT state the golden path had at boundary D, via state-blob load or chained replay-from-t0. | Only the frozen 2020→D history, never pre-2020. |

The `k≈4.7` corruption the Lens fears is a Use-case-B failure (going live at D
with cold accumulators). The fix is NOT 2019 data — it is **restoring the
golden's own accumulated state at D** (which itself descends from a t0
cold-start). "Warm" here = "continue the golden path," not "pre-train."

---

## 1. Two state classes (they warm-start differently)

### Class-S — bounded-lookback SIGNAL state (9 sat steppers + Core signal)
Sleeve indicators. **Subtlety:** the pandas EWM kernel used everywhere
(`adjust=True, ignore_na=False`) has **INFINITE memory** — `old_wt += 1` grows
without bound, so there is **NO finite window whose truncated warm-up is
bit-exact**. Bit-exactness is only achievable by (i) replay from the symbol's
first bar, or (ii) restoring the exact `(weighted, old_wt, nobs)` triple. A
"≥N-bar warm-up window" gives a *close-but-not-bit-exact* state — admissible
ONLY under the owner-ratified tolerance band and ONLY in a genuine forward
deploy where frozen parity is not the target. (Quoted kernels: `_Ewm` in
`carry_breakout_stepper.py:124`, `EwmMean`/`EwmStd` in `crisis_stepper.py:105/138`,
`_EwmStd` in `consolidate_p1c_stepper.py:77`.)

### Class-P — unbounded PATH-DEPENDENT equity (`a`=CoreSim, `b`=SatEquityNative)
These are NOT indicators and have **no steady state**. `b = eq_close /
eq_close.iloc[0]` and `a = eqc / eqc.iloc[0]` are the running product of every
bar's P&L since t0 (BH_ENGINE_SPEC §1; CORESIM_SPEC §1). `a_h`/`b_h` feed the
blend only as ratios `w·a_h/j`, `(1−w)·b_h/j` (MODEL_SPEC §2), but the
normalization anchor is the t0 value (=10000 exactly = INIT). **The only
warm-starts are: full replay from 2020-01-02, or an exact state blob** (balance
+ per-symbol lots/entry + n_trades for `b`; per-leg balance/pos/entry + segment
cursor + seed chain for `a`). No lookback shortcut exists.

---

## 2. Per-component warm-up requirements (MEASURED from the steppers)

Max-lookback = the longest finite window each component references. For Class-S
this is the *floor* on any tolerance-band warm-up; for bit-parity, replay-from-t0.

| Component | Grid | Max finite lookback (binding) | Other stateful accumulators | State fields (get_state) |
|---|---|---|---|---|
| **carry_breakout** | hourly union | **960 hourly bars** = 40d (`_N_SLOW_BARS`, Donchian slow entry) + **64 daily FX rows** (`GATE_DAYS+1`, momentum gate) | vol_ewm span 720h; atr_ewm span 480h; 4 Donchian rolling-extreme deques (960/480/384/192); 2 Donchian state machines/sym; `dc_hist`; `w_eff` | `c_ff[32]`, `vol_ewm[32]`, `atr_ewm[11]`, `win_hi/lo_f/s[11]`, `sys_f/s[11]`, `dc_hist`, `w_eff`, `cur_day`, `bar_i` (`carry_breakout_stepper.py:443`) |
| **crisis** | weekday daily | **250 daily rows** (`_SIZE_SPAN` EwmStd, min_periods 60) | DD rolling-max ring 126; vol rings 60; MA rings 50; 2 smoothing EwmMean span 3; `lev`/`flev` cumprods | `prev_close`, `br_ring`, `lev`, `lev_ring`, `ewm_seq`, `fr_ring`, `flev`, `flev_ring`, `ewm_sfx`, `au_ring`, `vol_ewm[4]`, `n_steps` (`crisis_stepper.py:311`) |
| **meanrev** | hourly + daily | **200 daily rows** (`TREND_L` SMA200) | vol ewm span 720h; daily ring 256 (`_RING`); z-score SMA/SD 60d; per-sym hysteresis `st`; index `held`; frozen `size` | `close`, `wavg`, `old_wt`, `nobs`, `dbuf[16]`, `dptr`, `dcount`, `st`, `held`, `size`, `pos`, `pending` (`meanrev_stepper.py:348`) |
| **consolidate_p1c** (seasonal+crypto) | hourly + crypto daily | **120 daily rows** (`MA_REGIME` crypto SMA) | seasonal ewm span 720h; per-coin EwmStd span 30d; L_MOM 28d logp ring; 3-state hysteresis; deferred-emit 1-bar buffer; effective-target queue | `sea_weighted/old_wt/w`, `coins{ewm,prev_logp,logp_ring,logp_n,ma_ring,ma_head,ma_filled,ma_sum,ma_nan_ct,state}`, `cur_day`, `day_last`, `queue`, `cr_current`, `have_prev`, `prev_ts`, `prev_cr_row` (`consolidate_p1c_stepper.py:387`) |
| **trend_v2** | daily (5 metals) | **125 daily rows** (`_MAX_L`) | dret² ewm span 20 (minp 10); price hist ring 125; per-sym hysteresis `held` | `hist[5]`, `ewm_weighted`, `ewm_old_wt`, `ewm_nobs`, `held`, `n_rows` (`trend_v2_stepper.py:242`) |
| **mag_xau** | daily raw trading days (XAU) | **21 daily mids** (`VOL_WIN+1`) | 20d vol ring; effective-target `pending` queue; day accumulator | `mids`, `accum_day`, `accum_close`, `pending`, `current` (`mag_xau_stepper.py:187`) |
| **intraday** | hourly (USA500/USTEC) | **720 hourly** vol ewm; **20 mv-days** min for `sc` (span 60) | per-sym vol num/den ewm; sc ewm span 60 (minp 20) on mv-day index; intraday scratch; `w_vol` shift-1 | per-sym `prev_close,vol_num,vol_den,vol,w_vol,sc_num,sc_den,sc_nobs,c15,has15,has16,mv_pending,sig`; `cur_day` (`intraday_stepper.py:132`) |
| **ensemble** | — | **STATELESS** (pointwise combine + hard limits; `ensemble_stepper.py:82`) | none | none — no warm-up |
| **Core signal** (`CoreEngine.mqh` f_core, 8 legs) | daily series from M1 | **200 daily bars** (SMA200 US500 `:294` / ETH `:326`; donch 100 XAU `:282`; z-score 60 `:255`) | rebuilt daily series (pre-20:00 EURGBP variant); live sub-ledger `g_realized/g_seed` folded from deal history (`:672`) | in-EA daily series + `g_donchTgt`,`g_nightLev`, per-magic realized ledger, `g_dealCursor` |
| **`b` — SatEquityNative** | 1m (31 syms) | **UNBOUNDED** (path-dep. from t0) | balance, lots[31], entry[31], n_trades | JSON `FMA3_bh_state_*.json` (BPURE_WAVE3 §6) |
| **`a` — CoreSim** | 1m (9 legs / 7 slots) | **UNBOUNDED** + 32 frozen segment reseeds | per-leg balance/pos/entry; segment cursor; seed chain `seed_j = eqc at last bar < t0_j` | per-leg state + `seed`/segment index (CORESIM_SPEC §5–6) |

**Campaign-quoted maxima (Lens prompt) confirmed:** carry_breakout 960-bar
hourly Donchian and the crisis 250-day EwmStd are the two longest finite
windows. In *calendar* terms the binding warm-up for Class-S is ≈ **250 weekday
trading days ≈ 12 months** (crisis vol-sizing EWM to converge to its
min_periods-60 regime and beyond), with meanrev SMA200 close behind.

---

## 3. Design of record — chained replay-from-t0 == a checkpoint blob

**Core identity:** the EA's warm-start replaying the frozen 2020→D history bar
by bar through every stepper and both shadow engines produces the SAME state as
loading a blob captured from that same replay. The blob is just a cached
checkpoint. Both are already proven by the component harnesses:
- `b`: BH stepper **stage-3 warm-start** — snapshot after 2022Q2, resume 2022Q3,
  1,830,424 tail bars **bitwise** (BPURE_WAVE3 §1; BH_ENGINE_SPEC §8).
  `TestSatEquity` Step 3 chains 2020Q2 from the terminal's OWN `state_out` file
  and matches `state_expected` field-for-field.
- `a`: CoreSim seed chain `seed_j == triggers[j-1].book` **bit-equal at 32/32
  segment boundaries** (CORESIM_SPEC §6.2/§8, gate G-c).
- Class-S steppers: every one exposes `get_state()/set_state()` explicitly "so a
  live EA can warm-start" (docstrings, all 9 files).

### Recommended: dual-path, both hash-gated
- **B1 (primary) — WARM-STATE BLOB.** A pre-exported, config-hash + sha256
  gated bundle captured at boundary D from the frozen replay: one
  `get_state()` JSON per Class-S stepper + Core-signal daily-series seed +
  `b` state JSON + `a` per-leg state & seed/segment cursor. `OnInit` loads it,
  `set_state()`s every component, then trades from D forward. Fast; the exact
  golden state by construction.
- **B2 (fallback / certifier) — FULL REPLAY at OnInit.** Drive all 9 steppers,
  Core signal, CoreSim and SatEquityNative from 2020-01-02 through D inside
  `OnInit`. Slower (Python scalar ref: `b`≈2.4 min, `a`≈1 min for the full 6y;
  MQL5 faster) but needs no blob. **Use B2 to regenerate/verify B1.**

### Use-case-A (in-sample RECON-9): neither blob nor replay
Just init every component FRESH at model t0 and start at the first union bar.
The cold-start era is inside the tolerance band because the golden shares it.

---

## 4. Certification — the state-diff gate (FMA3-RECON-9-WS)

Warm-start is CORRECT iff the warm-started state at boundary D equals the
frozen-cache state at D. Concretely, at a chosen boundary D (recommend a
quarter/segment edge so both caches exist, e.g. 2022Q2→Q3, already exported):

1. **State-diff (Class-P):** `b` state JSON == `FMA3_bh_state_expected_{Q}.json`
   field-for-field (balance, lots[31], entry[31], n_trades) — the existing BH
   gate. `a`: per-leg (balance,pos,entry) and `seed`/segment cursor == the
   CoreSim parquet carry and `triggers[j-1].book` at D.
2. **State-diff (Class-S):** each stepper `get_state()` == the reference
   `get_state()` at D, exact for non-EWM fields; EWM `(weighted, old_wt, nobs)`
   equal to the ratified tolerance (bit-exact under replay-from-t0; ≤ the
   Wave-2 1e-12 signal band under the MQL5 language layer).
3. **Output re-derivation:** with state loaded at D, the FIRST live bars'
   `f_sat`, `f_core`, `a_h`, `b_h`, and blended `book_frac[33]` reproduce the
   golden `FMA3_fed_frac_v3.csv` rows for D+ within the owner-ratified residual
   band **ΔCAGR ≤ ±1.0pp / ΔMaxDD_worst ≤ ±0.5pp / ΔBreach ≤ ±0.5pp**.
4. **No-artifact check:** confirm the k≈4.7-style blow-up is ABSENT in the
   first ≥ max-lookback (960h / 250d) live bars — i.e. warm-loaded output does
   NOT show the cold-start transient the Use-case-A curve shows at t0.

This gate reuses the machinery that already passed (`TestSatEquity` chained
quarters, CoreSim seed-chain assertion); it adds the Class-S stepper state-diff
and the blended-output re-derivation. It slots into the standing "every new EA
run gets a recorded FMA3-RECON entry before deploy" rule.

---

## 5. History the EA must have available (and the honest MT5 uncertainty)

- **B1 blob path:** needs only the blob file in `FILE_COMMON` + enough live
  history forward of D to keep computing (≈ 960 hourly bars rolling for the
  Donchians). Minimal terminal-history demand. **Preferred for this reason.**
- **B2 full-replay path:** needs synchronized multi-symbol **1-minute** history
  back to **2020-01-02** for all 33 book symbols **plus every EUR cross** used
  by `eurq` (EURUSD/EURJPY/EURGBP/EURCHF/EURNZD/EURCAD/EURNOK/EURSEK —
  MODEL_SPEC §6) and the crypto weekend bars that define the union grid.
- **UNCERTAIN — must be measured, not asserted:** whether the MT5 Strategy
  Tester (or a live terminal) can furnish 33+8 symbols of **time-synchronized**
  1m bars back to 2020 on the *single-symbol* tester clock. The tester drives
  one chart symbol; secondary-symbol `CopyRates` availability and alignment on
  the union grid is the classic multi-symbol tester risk. The staged-validation
  rule stands: **1m-OHLC smoke first, real-tick only after mechanics pass.**
  If secondary-symbol 1m history is not reliably available to 2020 in the
  chosen run mode, **B1 (blob) is mandatory, not optional** — this is the
  decisive reason the blob is the primary path.

---

## 6. Warm-state blob SCHEMA (B1)

```
FMA3_warmstate_{D}.json           # D = boundary date (e.g. 20220701T000000)
{
  "version": 1,
  "boundary_utc_ns": <int>,        # first live bar the EA trades AT
  "model_t0_utc_ns": 1577923200e9, # 2020-01-02 00:00 (anchor for a,b norm)
  "config_hash": "51a7541cc2aaa593",
  "freeze_hash":  "fc14159f…c1446",           # FMA3-v34-freeze-1
  "golden_frac_sha256": "d00b614b650b…8ab452e",# RECON-4 pinned stream
  "sat_signal": {                  # Class-S — one get_state() per stepper
    "carry_breakout": {…},         # carry_breakout_stepper.get_state()
    "crisis":        {…},
    "meanrev":       {…},
    "consolidate_p1c": {…},        # seasonal + crypto_smart
    "trend_v2":      {…},
    "mag_xau":       {…},
    "intraday":      {…}
    // ensemble: STATELESS — omitted
  },
  "core_signal": {                 # CoreEngine f_core warm seed
    "daily_series_seed": {…},      // ≥200 daily bars per SID, pre-20:00 EURGBP variant
    "g_donchTgt": <f64>, "g_nightLev": <f64>,
    "ledger": { "<magic>": {"seed":<f64>,"realized":<f64>}, … },
    "deal_cursor": <int>
  },
  "shadow_b": {                    # SatEquityNative (b) — BH state JSON
    "balance": <f64>, "lots": [31×f64], "entry": [31×f64], "n_trades": <int>
  },
  "shadow_a": {                    # CoreSim (a)
    "segment_index": <int>, "seed": <f64>,          // seed_j at D
    "legs": [ {"balance":<f64>,"pos":<f64>,"entry":<f64>}, … 9 ]
  },
  "expected": {                    # certification targets at D (state-diff gate)
    "a_h_at_D": <f64>, "b_h_at_D": <f64>,           // normalized multiples
    "book_frac_at_D": { "<sym>": <f64>, … }         // first live row, pre-s
  }
}
```
Export it with a `export_warmstate.py` that (a) runs the frozen replay to D,
(b) dumps every `get_state()` + `a`/`b` state, (c) hard-fails unless the
re-derived `book_frac` at D matches the golden stream row bit-for-bit (same
self-check discipline as `export_book_frac_v3.py` / `export_blend_inputs.py`).

---

## 7. Open items / honest flags
1. **Class-S EWM bit-exactness vs MQL5-no-FMA.** The steppers rely on
   `math.fma` for pandas parity (carry/trend docstrings). MQL5 without FMA
   inherits a ~1e-16-relative residual per step; over a full replay this is
   inside the ratified band but is NOT bit-exact — the state-diff gate for
   EWM fields must use the tolerance, not `==`.
2. **Core-signal warm-start is the least-proven seam.** `CoreEngine.mqh` is the
   G1-proven LIVE tracker; its signal recompute needs ≥200 daily bars AND its
   deal-history sub-ledger reconstruction (`g_realized`) is a restart concern
   distinct from indicator warm-up. Whether f_core’s daily-series seed round-trips
   into a blob field-for-field is UNVERIFIED (no CoreEngine state-export exists
   yet) — flag, do not assert.
3. **Boundary choice.** Certify at a segment/quarter edge where both `a` and `b`
   caches already exist (2022Q2→Q3 is exported and bitwise-proven for `b`).
4. **Forward past 2025-12-31** still needs the separate Core-signal recompute +
   stream extension (EA_V3_DESIGN §7) before any true-live warm-start beyond the
   frozen horizon — out of scope here.
```
