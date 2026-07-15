# Symbol-Metadata Reconciliation — Status & Owner Run-Sheet

**Status: READY FOR OWNER PROBE RUN.** Toolkit built and self-proven (probe emits, reference sourced, judge self-tests + 4 negative controls all green, end-to-end live path validated on a synthetic 22-col CSV). The one remaining step is owner-run: attach `SymbolMetaProbe` to a live chart (zero trades) to produce `FMA3_symbol_meta.csv`, then run the judge against it.

- **Broker of record:** `ICMarketsEU-MT5-5`
- **Universe:** the 37 `core.ALL` symbols — 31 b-book + AUDUSD/NZDUSD a-core legs (33 traded/swapped) + EURJPY (eurq cross + H1) + GBPUSD/XRPUSD/XPTUSD (H1-signal-only). This IS `FeedAssembler.mqh` `FA_SYMS` in `core.ALL` order — no append, no intersection.
- **Broker name remap:** MODEL `DAX` → BROKER `DE40`; MODEL `USA500` → BROKER `US500`; all others identity (via `FeedAssembler.FaBrokerName`, matching `BookReplay g_fedCanon`).

## Why this exists — the DE40 lesson

`FeedAssembler.Init(true)` **REFUSED** because live `SYMBOL_DIGITS[DE40]=2` did not equal the record-feed `FA_DIGITS[DAX]=1`. `build_ic_feed.py` had assigned digits per-symbol; the ask was reconstructed as `bid + spread*point`. Rather than silently relax the refuse, the owner chose **Option B: reconcile EVERY symbol's live metadata against record/engine assumptions BEFORE relaxing anything.** This toolkit is that reconciliation, generalized to the full 37×N (symbol × field) matrix and hardened with the Antigravity instrument-discipline lessons:

1. Compare the **full matrix**, never an intersection — a symbol missing on either side is a HARD error, not a silent skip.
2. Classify **PRECISION drift** (harmless → R2) vs **SCALE drift** (catastrophic → block) vs **CONTRACT/VOLUME drift** (breaks sizing/marks → block) **correctly** — a scale/contract drift misread as precision is the worst possible failure, and there is a dedicated negative control that proves the judge does not make it.

---

## The toolkit (3 units)

| Unit | File | Role |
|---|---|---|
| **1 — Probe** | `mt5/ea/SymbolMetaProbe.mq5` | LIVE broker `SymbolInfo` dump. Script (`OnStart`), **ZERO trading calls** — no `CTrade`, no `OrderSend`, no position/history query. Attach to any chart on the live broker; writes `Common\Files\FMA3_symbol_meta.csv` (header + one row per symbol, 22 columns). |
| **2 — Reference** | `research/bpure/meta/symbol_meta_reference.json` | AUTHORITATIVE record/engine assumptions for all 37 symbols, every field sourced to quote file:line. The ground truth the judge reconciles against. |
| **3 — Judge** | `research/bpure/meta/reconcile_symbol_meta.py` | Reconciles live CSV vs reference across the full 37×N matrix; classifies + assigns severity; self-tests + negative controls; emits verdict + exit code. |

### Probe details (`SymbolMetaProbe.mq5`)
- Includes `<Book/FeedAssembler.mqh>` and iterates `FA_SYMS` (never copies the list → cannot drift from the compute path). `FA_NSYM = 37`.
- Per symbol emits 22 columns: `broker_name, model_name, SYMBOL_DIGITS, SYMBOL_POINT, SYMBOL_TRADE_TICK_SIZE, SYMBOL_TRADE_TICK_VALUE, SYMBOL_TRADE_CONTRACT_SIZE, SYMBOL_VOLUME_MIN, SYMBOL_VOLUME_MAX, SYMBOL_VOLUME_STEP, SYMBOL_TRADE_MODE, SYMBOL_SWAP_MODE, SYMBOL_SWAP_LONG, SYMBOL_SWAP_SHORT, SYMBOL_CURRENCY_BASE, SYMBOL_CURRENCY_PROFIT, SYMBOL_CURRENCY_MARGIN, SYMBOL_MARGIN_INITIAL, SYMBOL_TRADE_STOPS_LEVEL, SYMBOL_SELECT_ok, error, record_feed_digits`. **Verified: probe header == judge `CSV_COLUMNS` (22/22, exact).**
- All doubles written `%.17g` (exact round-trip).
- **A symbol is never silently dropped**: if `SymbolSelect` fails, the row is still emitted with `SYMBOL_SELECT_ok=0` and `error=SELECT_FAILED` so the judge sees all 37 and can BLOCK on it.
- `record_feed_digits` (the compute-path `FA_DIGITS[i]`) is appended per row so the judge can flag reference-vs-compute-path digit drift directly.

---

## Reference table — per-symbol record digits + contract sizes (sourced)

Source of record (from `symbol_meta_reference.json._field_provenance`):
- **digits/point** — `build_ic_feed.py:22-39` (FEED) **==** `FeedAssembler.mqh:110-118` (FA_DIGITS), verified AGREE; `point = 10^-digits`.
- **contract** — `SatEquityNative.mqh:50-57` (b) / `CORESIM_SPEC.md §3` (a) / `BH_ENGINE_SPEC.md:42-74` / `settings.py:36-137`.
- **lot_step/min** — `SatEquityNative.mqh:80-97` (b) / `CORESIM_SPEC.md §3` (a) / `settings.py`. `lot_max = null` (model has NO volume ceiling — only lot_step/min + margin_cap 0.9; a live-only exec concern).
- **profit ccy** — `settings.py` quote ccy; deposit/account ccy EUR (`BookConvert.mqh FED_Eurq`).
- **swap** — synthesized (`SwapEurq.mqh`); broker `SYMBOL_SWAP_MODE` is **not read** → ignored-by-design.

| MODEL | BROKER | role | digits | point | contract | lot_min | profit_ccy | eurq_cross |
|---|---|---|--:|--:|--:|--:|---|---|
| AUDCAD | AUDCAD | book | 5 | 1e-05 | 100000 | 0.01 | CAD | EURCAD |
| AUDJPY | AUDJPY | book | 3 | 0.001 | 100000 | 0.01 | JPY | EURJPY |
| AUDNZD | AUDNZD | book | 5 | 1e-05 | 100000 | 0.01 | NZD | EURNZD |
| AUDUSD | AUDUSD | core-leg | 5 | 1e-05 | 100000 | 0.01 | USD | EURUSD |
| CADCHF | CADCHF | book | 5 | 1e-05 | 100000 | 0.01 | CHF | EURCHF |
| CADJPY | CADJPY | book | 3 | 0.001 | 100000 | 0.01 | JPY | EURJPY |
| EURCAD | EURCAD | book | 5 | 1e-05 | 100000 | 0.01 | CAD | EURCAD |
| EURCHF | EURCHF | book | 5 | 1e-05 | 100000 | 0.01 | CHF | EURCHF |
| EURGBP | EURGBP | book+core-leg | 5 | 1e-05 | 100000 | 0.01 | GBP | EURGBP |
| EURJPY | EURJPY | signal-only | 3 | 0.001 | 100000 | 0.01 | JPY | EURJPY |
| EURNOK | EURNOK | book | 5 | 1e-05 | 100000 | 0.01 | NOK | EURNOK |
| EURNZD | EURNZD | book | 5 | 1e-05 | 100000 | 0.01 | NZD | EURNZD |
| EURSEK | EURSEK | book | 5 | 1e-05 | 100000 | 0.01 | SEK | EURSEK |
| EURUSD | EURUSD | book | 5 | 1e-05 | 100000 | 0.01 | USD | EURUSD |
| GBPJPY | GBPJPY | book | 3 | 0.001 | 100000 | 0.01 | JPY | EURJPY |
| GBPUSD | GBPUSD | signal-only | 5 | 1e-05 | 100000 | 0.01 | USD | EURUSD |
| NZDCAD | NZDCAD | book | 5 | 1e-05 | 100000 | 0.01 | CAD | EURCAD |
| NZDJPY | NZDJPY | book | 3 | 0.001 | 100000 | 0.01 | JPY | EURJPY |
| NZDUSD | NZDUSD | core-leg | 5 | 1e-05 | 100000 | 0.01 | USD | EURUSD |
| USDCHF | USDCHF | book | 5 | 1e-05 | 100000 | 0.01 | CHF | EURCHF |
| USDJPY | USDJPY | book+core-leg | 3 | 0.001 | 100000 | 0.01 | JPY | EURJPY |
| BTCUSD | BTCUSD | book+core-leg | 2 | 0.01 | 1 | 0.01 | USD | EURUSD |
| ETHUSD | ETHUSD | book+core-leg | 2 | 0.01 | 1 | 0.01 | USD | EURUSD |
| SOLUSD | SOLUSD | book | 4 | 0.0001 | 1 | 0.01 | USD | EURUSD |
| XRPUSD | XRPUSD | signal-only | 4 | 0.0001 | 1 | 0.01 | USD | EURUSD |
| DAX | **DE40** | book | 1 | 0.1 | 1 | 0.1 | EUR | — |
| JP225 | JP225 | book | 2 | 0.01 | 1 | 0.1 | JPY | EURJPY |
| UK100 | UK100 | book | 2 | 0.01 | 1 | 0.1 | GBP | EURGBP |
| US30 | US30 | book | 2 | 0.01 | 1 | 0.1 | USD | EURUSD |
| USA500 | **US500** | book | 2 | 0.01 | 1 | 0.1 | USD | EURUSD |
| USTEC | USTEC | book+core-leg | 2 | 0.01 | 1 | 0.1 | USD | EURUSD |
| XAGUSD | XAGUSD | book | 3 | 0.001 | 5000 | 0.01 | USD | EURUSD |
| XAUUSD | XAUUSD | book+core-leg | 2 | 0.01 | 100 | 0.01 | USD | EURUSD |
| XBRUSD | XBRUSD | book | 2 | 0.01 | 1000 | 0.01 | USD | EURUSD |
| XNGUSD | XNGUSD | book | 4 | 0.0001 | 10000 | 0.01 | USD | EURUSD |
| XPTUSD | XPTUSD | signal-only | 2 | 0.01 | 100 | 0.01 | USD | EURUSD |
| XTIUSD | XTIUSD | book | 2 | 0.01 | 1000 | 0.01 | USD | EURUSD |

**Non-100000 contracts to watch** (the sizing/marks-critical rows — a live drift here BLOCKS): crypto (BTC/ETH/SOL/XRP) = 1; all indices (DE40/JP225/UK100/US30/US500/USTEC) = 1; XAGUSD = 5000; XAUUSD/XPTUSD = 100; XBRUSD/XTIUSD = 1000; XNGUSD = 10000.

**DE40 is the known live-vs-record digit split**: record digits = 1 (point 0.1); live was observed at digits = 2. Under the judge this is a **PRECISION-DRIFT** *iff* the live `point*10^digits` invariant is preserved (0.01 × 10² = 1 == 0.1 × 10¹ = 1) — HANDLED, relax the refuse, R2. If instead the invariant is broken, it is SCALE-DRIFT and BLOCKS. The judge decides from the probe's actual numbers; it is not pre-assumed.

**Reference self-proof (embedded in the JSON):**
- `_self_test`: **PASS** — cross-engine digits/contract/point agreement, 0 findings (all engines agree on every symbol).
- `_negative_control`: **PASS** — injected XAUUSD contract 100→10000 (×100 scale drift) into the `a` engine; the cross-engine check flagged it as CONTRACT/CROSS-ENGINE DRIFT (required).
- `_internal_inconsistencies_found`: `[]` — none.

> Verbatim reference verdict: **"PASS — 37/37 symbols emitted, each field sourced (quote file:line); cross-engine self-test 0 findings (all engines agree); negative control flags an injected x100 scale drift. No internal inconsistency found."**

---

## Drift classes — what each means for the EA

The judge classifies every (symbol, field) and assigns severity. This is the whole point: distinguishing the harmless from the catastrophic **correctly**.

| Class | Severity | What it means | EA action |
|---|---|---|---|
| **MATCH** | OK | live == baked (within float tol), or field ignored-by-design | Use baked value; no action. |
| **PRECISION-DRIFT** | HANDLED | digits/point differ but the price-scale invariant `point*10^digits` is **preserved** and contract unchanged (the DE40 1→2 case) | **→ R2.** FeedAssembler uses the live `SYMBOL_POINT/DIGITS`; engine marks unaffected (magnitude preserved). Relax the `FA_DIGITS` refuse for that symbol. |
| **SCALE-DRIFT** | **CRITICAL** | the `point*10^digits` invariant **CHANGED** — the numeric magnitude a lot marks against shifted | **→ BLOCK.** Marks/P&L wrong. Do NOT relax. Fix feed scaling or halt the symbol. |
| **CONTRACT-DRIFT** | **CRITICAL** | live `SYMBOL_TRADE_CONTRACT_SIZE` != baked | **→ BLOCK.** lot→notional wrong; breaks position fidelity + marks. Rebake engine contract or halt. |
| **VOLUME-DRIFT [block]** | **CRITICAL** | live step coarser/incompatible, or live min > model min (model's lots unrepresentable) | **→ BLOCK.** Quantizer diverges → sizing wrong. Align grid or halt. |
| **VOLUME-DRIFT [handled]** | HANDLED | live step finer/equal, or live carries a max ceiling (reference is unbounded) | Respect the live grid/ceiling at exec (split oversized orders). |
| **CCY-DRIFT** (profit) | **CRITICAL** | live `SYMBOL_CURRENCY_PROFIT` != assumed quote ccy | **→ BLOCK.** eurq cross / conversion wrong → marks wrong. Fix mapping or halt. |
| **CCY-INFO** (base) | HANDLED | base ccy differs (indices carry label bases, e.g. DE40 → 'EUR') | INFO only: drives neither marks nor eurq; verify mapping is intended. |
| **SWAP** | OK (by design) | broker `SYMBOL_SWAP_MODE` — never read (swap synthesized in `SwapEurq.mqh`) | Ignored-by-design; never blocks. |
| **SELECT-FAIL** | **CRITICAL** | `SYMBOL_SELECT` failed / error flag set | **→ BLOCK.** Symbol unavailable live; cannot feed/trade. Resolve broker availability first. |
| **REFERENCE-INCONSISTENCY** | **CRITICAL** | CSV-embedded `FA_DIGITS` disagrees with reference `digits_record` | **→ BLOCK.** Reference drifted from the compute path; re-derive it before trusting any verdict. |
| **MISSING symbol** (either side) | **HARD** | a reference symbol absent from live, or a live symbol not in reference, or count != 37 | **→ HARD error (raised, exit 4).** Never a silent skip. |

**One-line rule for the EA:** PRECISION → R2 (relax + use live grid); everything CRITICAL/HARD → BLOCK and fix before any `Init(true)` relax.

---

## Judge self-test + negative controls — UNSOFTENED RESULTS

`python3 reconcile_symbol_meta.py --selftest` — re-run in this session, **exit 0, all green:**

| Check | What it proves | Result |
|---|---|---|
| **self_test** | `reconcile(reference-as-live, reference)` → all 37 MATCH, verdict PASS, 0 critical, 0 drift | **PASS** (clean_match=37) |
| **NC (i) precision** | inject DE40 digits 1→2 with magnitude preserved → classified **PRECISION-DRIFT**, HANDLED, **does NOT block** | **PASS** (verdict PASS) |
| **NC (ii) contract** | inject EURUSD contract 100000→10000 → **CONTRACT-DRIFT CRITICAL**, verdict **BLOCK** | **PASS** |
| **NC (iii) scale** | inject US500 price-scale /10 (invariant broken) → **SCALE-DRIFT CRITICAL**, **NOT misread as precision**, verdict **BLOCK** | **PASS** ← the load-bearing control: the worst-failure guard |
| **NC (iv) missing** | drop XAUUSD from live → **HARD coverage error raised**, not a silent pass | **PASS** (raised, names XAUUSD) |

> Verbatim judge verdict: **"PASS — all self-tests + 4 negative controls green; full report path validated end-to-end on a synthetic 22-col CSV; exit-code semantics correct (0 clean / 2 live-BLOCK / 4 HARD-missing)."**

**End-to-end live-path validation** (this session, synthetic 22-col CSV built from the reference):
- clean CSV → verdict **PASS**, 37/37 clean-MATCH, CLI **exit 0**.
- CSV with an injected US500 ×10 scale drift → verdict **BLOCK**, critical = `[(US500, SCALE-DRIFT)]`, CLI **exit 2**.
- HARD-missing path → **exit 4** (per `main()` semantics).

**Header contract check:** probe's emitted CSV header == judge `CSV_COLUMNS`, 22/22 exact — the two units cannot silently disagree on schema.

**Independent verify:** `{"c": true, "b": []}` — confirmed, no blocking findings.

---

## OWNER RUN-SHEET

The probe is **owner-run** (I do not launch `terminal64.exe`). Two steps:

### Step 1 — Owner: run the probe on a live chart (zero trades)
1. Ensure `SymbolMetaProbe.mq5` is compiled (MetaEditor, 0 errors / 0 warnings) and the terminal is logged into **`ICMarketsEU-MT5-5`**.
2. Drag **`SymbolMetaProbe`** onto **any** chart (the symbol does not matter — it iterates all 37 internally). It is a Script, not an EA/indicator.
3. It runs once (`OnStart`), places **zero** trades, and writes **`Common\Files\FMA3_symbol_meta.csv`**.
4. Confirm the Experts log line: `SymbolMetaProbe DONE: wrote 37 symbol rows ... (N selected, M select-failed)`. Expect **37 selected, 0 select-failed**; any select-failed row is captured and will BLOCK at Step 2 — that is intended, not an error to hide.
5. **Expected probe hand-off:** `{"ok": true}` with the 37-row CSV present.

### Step 2 — I run the judge against the owner's real CSV
```
python3 research/bpure/meta/reconcile_symbol_meta.py <path>/FMA3_symbol_meta.csv
```
(defaults the reference to `research/bpure/meta/symbol_meta_reference.json`; always runs the self-test + 4 negative controls first, then the live reconciliation.)

**Exit-code / verdict semantics:**
| Exit | Meaning | Next action |
|--:|---|---|
| **0** | self-tests pass **and** (no live CSV, or live reconciliation clean = PASS) | Safe to proceed to the targeted `FA_DIGITS`/`Init(true)` relax for any PRECISION-DRIFT symbol (→ R2). |
| **2** | live reconciliation **BLOCK** (≥1 CRITICAL: scale/contract/volume-block/ccy/select-fail/reference-inconsistency) | **STOP.** Fix or halt the flagged symbol(s) before any relax. Read the CRITICAL section of the report. |
| **3** | self-test/negative-control regression (toolkit itself broke) | Fix the judge before trusting any verdict. |
| **4** | **HARD** coverage error (missing/extra symbol, or count != 37) | The probe did not emit all 37 (or emitted an unknown symbol). Re-run the probe; do not proceed. |

The report prints: class counts, the CRITICAL list (must block/fix, with per-symbol notes), the HANDLED-precision list (the DE40-class → R2 candidates), HANDLED-other (volume ceilings / base-ccy info), and the recommended per-symbol resolution.

---

## Artifacts (absolute paths)

- Probe: `/Users/dsalamanca/vs_env/FableMultiAssets3/mt5/ea/SymbolMetaProbe.mq5`
- Reference: `/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/meta/symbol_meta_reference.json`
- Judge: `/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/meta/reconcile_symbol_meta.py`
- This status: `/Users/dsalamanca/vs_env/FableMultiAssets3/model/v3/SYMBOL_META_RECONCILE_STATUS.md`
- Probe output (owner-produced, Step 1): `Common\Files\FMA3_symbol_meta.csv`

**No `.mqh` compute path or S1/R1 gate script was modified. New file only.**
