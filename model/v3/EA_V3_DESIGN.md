# FableFederation_V3 — EA design (faithful executor of the v3 stable model)

**Goal:** an EA that executes *exactly* the model in [`MODEL_SPEC.md`](MODEL_SPEC.md) — reproduce IC (€3,872,872 @ s=1.6) and FTMO (€1,332,404 @ s=0.7 + breaker) in the MT5 tester, up to execution friction. Decisions ratified by owner 2026-07-12: **net shared symbols**; **design doc → then build**.

## 1. Fidelity criterion (what "match the model" means)

The model sizes off a frictionless record-engine balance; v3 sizes off the live MT5 balance, so the **final equity will drift by the MT5-vs-record friction ratio** (the "record-DD × MT5 ratio", already flagged v1.1-pending on both dashboards). We therefore do **not** demand byte-identical final equity. The real fidelity test is **position-level**:

> At each hour h, for each symbol k, v3's held position as a fraction of its own balance must equal `fed_frac[h,k]·s` (within lot-step quantization). If that holds every bar, v3 *is* executing the model, and any equity gap is pure friction — measured, not mysterious (→ FMA3-RECON-4).

## 2. Architecture: replay ONE unified fed_frac stream

**Decision: replay, do not compute-live.** The share weights `w·a_h/j`, `(1−w)·b_h/j` use the *frozen native standalone* equity multiples `a,b`; a live s-levered account cannot reconstruct them, so compute-live diverges whenever s≠1 (both dials are s≠1). Replaying the precomputed blend also inherits the v7 band re-splits frozen inside `frac7`, dissolving the reseed / floating-double-count / pooled-redistribution divergences by construction.

Consequence: **v3 discards the entire v1/v2 signal+sizing stack** — no `V7Core` band logic, no `QuarterRebalance`, no `VBalance`, no per-book reseed, no `e34`. It keeps only the *execution primitives* (order send/split, reject backoff, lot rounding, margin projection) and adds one unified replay+size loop.

## 3. The exporter — `scripts/export_fed_frac_v3.py`

Emits the unified, **already-netted** fed_frac stream that v3 replays. Extends the proven `export_v34_replay.py` machinery (config-hash gate, fmt sentinels, re-parse assertion).

- **Content:** for every hour h in the model index and every symbol k of the 33-symbol union, the **net** target fraction `fed[h,k] = f7·(w·a_h/j) + f34·((1−w)·b_h/j)` (shared symbols already summed — this is exactly the `static_fed(0.70)` matrix from `model/v3/reproduce.py`). `s` is **not** baked in — it is the EA dial.
- **Format (fmt=3):** header `w_v7=0.70,config_hash=51a7541cc2aaa593,fmt=3` + the frozen input sha256s. Rows `epoch,symbol,net_frac`. One `__GRID__,0` sentinel per all-flat hour (keep-last-good semantics, as fmt=2). Repo→broker map (`USA500=US500;DAX=DE40`) applied at emit.
- **Self-checks (hard-fail):** (a) re-parse → matrix reproduces `static_fed(0.70)` to <1e-12; (b) `record_engine.run_record(parsed·1.6, 10k)` == €3,872,872 and `run_record_ext(parsed·0.7, 100k, 3.0)` == €1,332,404 to the euro. Prints the file sha256 for the RECON row.

*(Per-book attribution note: the netted stream loses v7-vs-v34 split on the 6 shared symbols by construction — that's the owner's ratified choice. Attribution stays recoverable offline from the pre-net `f7`,`f34` rows if ever needed.)*

## 4. The v3 EA — `FableFederation_V3.mq5` + `Include/FMA3v3/`

Minimal, single-account, single-magic-per-symbol.

**Include tree (new, small):**
- `FedReplay.mqh` — reads/holds the unified fed_frac stream (extends `V34Replay.mqh`; same cursor/keep-last-good/hash-gate).
- `FedExec.mqh` — the unified per-bar loop (below).
- `FedConvert.mqh` — the full-map eurq (`F3_EurPerQuoteV34` promoted here, used for **all** symbols, always on).
- `Guardian.mqh` — the FTMO daily breaker (reused from v1, re-anchored per §4.3).
- Execution primitives (`RoundLots`, `SendSplit`, reject backoff, `OrderCalcMargin` projection) lifted verbatim from V7Core/V34Exec — no band logic.

**4.1 Sizing loop (once per new H1 bar, executes hour h at h+1 open):**
```
base = AccountInfoDouble(ACCOUNT_BALANCE)          // realized cash — model sizes off BALANCE, not equity
for each symbol k with fed_frac[h,k] != 0:
    g      = fed_frac[h,k] * InpScale               // InpScale = s (1.6 IC / 0.7 FTMO)
    dir    = sign(g)
    px     = dir>0 ? Ask : Bid
    unit   = px * contract(k) * eurq(k)             // eurq = full-map (§FedConvert), never 1/EURUSD catch-all
    want   = g * base / unit
    lots   = floor(|want|/step + 1e-9)*step ; if lots<min_lot -> 0
margin cap: if Σ|lots|·unit/leverage > 0.9*base, one uniform shrink = 0.9*base/Σ
rebalance band 0.25: retrade leg k only on sign-flip / cross-zero / reduce / |want−held|/|held|>0.25
```
Fills cross the spread; commission per lot/side; **one net position + one magic per symbol** (netting ratified). Compounding is automatic (base grows with realized P&L).

**4.2 Engine constants (match the record engine exactly):** margin_cap 0.9, rebalance_band 0.25, stop-out 0.5·margin_used, lot eps 1e-9, causal lag = hour-h row at h+1 first traded minute.

**4.3 FTMO daily breaker (`InpDailyStopX`, 0=off for IC, 3.0 for FTMO):** on server-day rollover, `anchor = previous server-day CLOSE-mark equity` (day 1 = initial); each tick, if worst-mark `ACCOUNT_EQUITY ≤ anchor·(1−x/100)` → flatten all, halt (targets→0) until next rollover. (Worst-mark on 1m-OHLC = feed bar low/high; real-tick traverses it.)

**4.4 Dial-agnostic:** `InpScale` is the only knob that differs IC↔FTMO. One binary, two presets.

**Removed vs v1/v2 (and why safe):** all v7 band/harvest/reseed (frozen in `frac7`), `e34` (replaced by shared balance), `InpReseedBalance`/`InpIndepReseed`/`InpV34JointSizing` (obsolete), `InpV34EurQuoteFix` (now unconditional).

## 5. Presets (`mt5/ea/presets/`)
- `FED_V3_IC.set` — s=1.6, InpInitial=10000, breaker off. Reproduces DASHBOARD_IC up to friction.
- `FED_V3_FTMO.set` — s=0.7, InpInitial=100000, InpDailyStopX=3.0. Reproduces DASHBOARD_FTMO up to friction.
- `FED_V3_PARITY_S10.set` — s=1.0 sanity point (fraction=exposure) for the position-level check.

## 6. Validation plan (staged, per campaign protocol)
1. **Exporter self-check** — stream reproduces `static_fed` to 1e-12 AND record engine on the stream = €3,872,872 / €1,332,404 (pure Python, no MT5).
2. **Compile** v3 headless (0/0), sha256 → FMA3-RECON-4 row.
3. **1m-OHLC smoke, IC** (`FED_V3_IC`): dump held-fraction vs `fed_frac·s` per bar per symbol → assert position-level match; record final equity + the friction ratio vs €3,872,872.
4. **1m-OHLC smoke, FTMO** (`FED_V3_FTMO`): same, + confirm breaker fires ~26× and anchors on prev-day close.
5. **Real-tick** only after smoke passes; then RECON-4 verdict (v3 .ex5 sha + friction ratio per preset).

## 7. Open items (NOT build-blockers — surfaced for the record)
- **Tester leverage (critical for the IC reproduction).** The record engine's margin cap uses the MODEL per-symbol leverage (FX 30, index/gold 20, energy/silver 10, crypto 2), baked into `g_fedLev[]`. To reproduce the IC s=1.6 record, run the tester on a **high-leverage login (e.g. 1:500)** so the model's cap binds before the broker's margin — otherwise the broker rejects/shrinks and v3 undershoots. **Retail 1:30 is the deployment constraint, not the reproduction constraint** (this is exactly the "s=1.6 not deployable at 1:30" honesty flag). Set the tester initial deposit == `InpInitial` and use a HEDGING login.
- **Joint 0.5·margin_used stop-out — deferred, not implemented.** The engine flattens if worst-mark `eq_w < 0.5·margin_used`. In-sample this never triggers (IC worst DD 22.6%, FTMO 13.3% — nowhere near the ~50% it needs), so it cannot affect the reproduction. Rather than add an unvalidated mechanism that could fire spuriously, v3 delegates to the broker stop-out and **RECON-4 asserts `eq_w` never falls below 0.5·margin_used** in either preset (proving the omission immaterial). Add the exact engine stop-out later if live-crisis fidelity demands it.
- **Deployable dial** — s=1.6 breaches retail 1:30 margin; the shippable IC preset is a lower-s point (band ~0.6–0.8), decided after v3 validates. v3 is dial-agnostic so this is a preset edit, not a rebuild.
- **FTMO cold-vs-warm** (crisis-safe ~s0.30–0.35) and **compound-vs-withdraw** — deployment questions, tracked in MODEL_SPEC honesty flags.
- **Live horizon** — the frozen stream ends 2025-12-31; live trading past it needs a forward v7-signal recompute + stream extension (documented, not built now).

## 8. Build log
- **2026-07-12 — built + adversarially reviewed + fixed.** `FableFederation_V3.ex5` sha256 `d516350b2db885c96cae298f662dd4b9e8cc70b18b607aaf7279f78d991fd117` (compiles 0/0). Fixes from the 3-reviewer pass applied: (1) unsized-leg HOLD (never flatten a held leg on a transient missing quote); (2) **re-size every M1 bar** (was once per H1 — the biggest IC-fidelity lever); (3) breaker trips on **worst-mark `eq_w`** (M1 low/high via OrderCalcProfit), not point-in-time equity; (4) breaker anchor = carried **prev-day CLOSE** equity (day-1 = real balance); (5) OnInit-ish server-tz mismatch guard; (6) tester FileFlush gated. Deferred: the joint stop-out (§7). Pending: staged 1m-OHLC smoke (IC/FTMO) → real-tick → RECON-4.
