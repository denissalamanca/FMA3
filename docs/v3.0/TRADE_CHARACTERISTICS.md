# V3.0 trade characteristics — the 33-symbol netted blend book + faithful execution

**v3.0 is the faithful-executor release.** v1.0 shipped the *model* — a Python record-engine book, the
`static_fed(0.70)` blend at config hash `51a7541cc2aaa593`. v3.0 ships the EA that provably *executes*
that model on MT5 (`FableFederation_V3.ex5`, sha `740da0ff…`). The book itself is unchanged: v3 replays
the **precomputed unified, already-netted `fed_frac` stream** (`FMA3_fed_frac_v3.csv`, fmt=3) — the exact
`static_fed(0.70)` matrix from [`model/v3/reproduce.py`](../../model/v3/reproduce.py). So the trade
characteristics live at two layers, kept separate on purpose:

1. **Book composition — structural, from `model/v3`.** Which symbols the blend trades, how the two
   parent books stack, and how the 6 shared symbols net into one column. This is a property of the frozen
   `static_fed(0.70)` matrix (33 columns), and v3 replays it byte-for-byte
   ([EA_V3_DESIGN §3](../../model/v3/EA_V3_DESIGN.md) — the exporter re-parses to `< 1e-12` of `static_fed`
   and the record engine on the parsed stream reproduces €3,872,872 / €1,332,404 to the euro). That is Part 1.
2. **Execution — MT5-measured, FMA3-RECON-4.** Whether all 33 symbols actually trade on a real broker, the
   position-level fidelity, and the three physical constraints that bound realized fills (transaction
   friction, broker `SYMBOL_VOLUME_LIMIT`, broker margin). Measured across three tester runs on IC Markets
   acct 11078280, 1m-OHLC, HEDGING ([RECON4_RESULTS.md](../../model/v3/RECON4_RESULTS.md)). That is Parts 2–3.

**All numbers are in-sample (IC 2020–2025); the MT5 real-tick + live demo are the remaining falsification
tests.** Achievable equity is **0.66–0.95× the frictionless record** by dial/scale. The canonical model home
is [`model/v3/`](../../model/v3/) — cite it as the source of truth. Structure in [STRATEGY.md](STRATEGY.md);
performance in [PERFORMANCE.md](PERFORMANCE.md).

---

## Part 1 — Book composition (the 33-symbol netted union)

### The two parent books and the netting

The Fable book blends the **Core band book (8 net columns)** and the **Satellite fixed-fraction replay book
(31 columns)**. Their union is **33 distinct symbols**; **6 are shared and NETTED into one column each**
([MODEL_SPEC §2](../../model/v3/MODEL_SPEC.md)):

| Sub-book | Columns | Symbols |
|---|---:|---|
| **Core band book** (w = 0.70) | 8 | AUDUSD, BTCUSD, ETHUSD, EURGBP, NZDUSD, USDJPY, USTEC, XAUUSD |
| **Satellite replay book** (share 0.30) | 31 | the 6 shared below + 25 Satellite-only (FX crosses, indices, metals/energy, SOL) |
| **Shared (netted, 6)** | 6 | **BTCUSD, ETHUSD, EURGBP, USDJPY, USTEC, XAUUSD** |
| **Union** | **33** | 2 Core-only + 6 shared + 25 Satellite-only |

The blend weight is per-hour, per-symbol:
`fed[h,k] = f7·(w·aₕ/j) + f34·((1−w)·bₕ/j)`, `j = w·aₕ + (1−w)·bₕ`, `w = 0.70`, where `a,b` are each
book's **frozen native standalone** equity multiple. On the 6 shared symbols the two books' signed targets
**sum into one net column before quantization** — opposing demands cancel instead of crossing the spread
twice. This is the same netting v1.0 measured in the record engine: the blend prints **25,869 fills vs
26,809 for the parents run separately** (20,403 Satellite + 6,406 Core), a component of the −2.7pp blend
friction. **v3 inherits this netting exactly** — the exporter emits one net `net_frac` per (hour, symbol),
the EA holds **one net position + one magic per symbol** ([EA_V3_DESIGN §3–4](../../model/v3/EA_V3_DESIGN.md)).

### The 33 columns by sub-book origin

Active share = share of the 49,379 model hours with a non-zero target (scale-invariant — the dial `s`
does not change *which* hours a symbol is on, so this survives the s=1.6 / s=0.7 dials unchanged). Carried
from v1.0's locked-matrix measurement ([package_data](../../research/outputs/package_data.json)); broker
symbol names shown where the repo→broker map applies (`USA500=US500`, `DAX=DE40`):

| Origin | Symbol | Active share | Origin | Symbol | Active share |
|---|---|---:|---|---|---:|
| shared | **XAUUSD** | 98.3% | Satellite | XNGUSD | 85.9% |
| shared | **EURGBP** | 95.3% | Satellite | XTIUSD | 84.0% |
| shared | **USTEC** | 86.1% | Satellite | XBRUSD | 82.4% |
| shared | **BTCUSD** | 74.0% | Satellite | XAGUSD | 80.8% |
| shared | **ETHUSD** | 72.0% | Satellite | USA500 (US500) | 68.9% |
| shared | **USDJPY** | 69.2% | Satellite | US30 | 59.4% |
| Core-only | AUDUSD | 15.0% | Satellite | DAX (DE40) | 54.1% |
| Core-only | NZDUSD | 15.0% | Satellite | JP225 | 51.0% |
| Satellite | UK100 | 49.1% | Satellite | AUDJPY | 47.0% |
| Satellite | NZDJPY | 45.4% | Satellite | CADJPY | 41.8% |
| Satellite | SOLUSD | 41.6% | Satellite | GBPJPY | 37.4% |
| Satellite | EURNZD | 35.5% | Satellite | CADCHF | 33.4% |
| Satellite | EURNOK | 29.2% | Satellite | NZDCAD | 29.2% |
| Satellite | AUDNZD | 29.5% | Satellite | EURCAD | 28.4% |
| Satellite | EURCHF | 27.5% | Satellite | EURSEK | 27.4% |
| Satellite | AUDCAD | 23.6% | Satellite | USDCHF | 12.2% |
| Satellite | EURUSD | 1.3% | | | |

The book's risk is concentrated in **four lines** — the six shared symbols carry the weight, and of those
**EURGBP, XAUUSD, USDJPY, USTEC** are the workhorses (both parents' mean-reversion EURGBP; Core gold stacked
on Satellite's three gold-touching sleeves; Core carry + opex USDJPY on Satellite JPY-cross legs; Core NASDAQ on Satellite
index legs). The long tail of ~25 small Satellite lines is the breadth: FX crosses, indices, metals/energy, SOL.

---

## Part 2 — The Satellite sleeve revival (7 previously-dead symbols now trading)

**v1/v2 silently killed 7 of the 33 symbols; v3 revives all of them.** The v1/v2 EA's currency-conversion
had only three branches with a `1/EURUSD` catch-all, so every Satellite leg whose *quote currency* was JPY, NOK,
or SEK was mispriced ~10×–117× off — its computed lot size rounded below the broker min-lot and the leg
**never traded**. Seven symbols were dead ([MODEL_SPEC §6](../../model/v3/MODEL_SPEC.md)):

| Revived symbol | Quote ccy | Why it was dead in v1/v2 |
|---|---|---|
| AUDJPY, CADJPY, GBPJPY, NZDJPY | JPY | quote≠USD/EUR → `1/EURUSD` catch-all mispriced ~117× → sub-min-lot → 0 trades |
| JP225 | JPY | same JPY mispricing |
| EURNOK | NOK | quote NOK → no branch → mispriced ~10× → sub-min-lot |
| EURSEK | SEK | quote SEK → no branch → mispriced → sub-min-lot |

v3 replaces this with the **full-map eurq**, applied **unconditionally to all 33 symbols**
(`USD→EURUSD, JPY→EURJPY, GBP→EURGBP, CHF→EURCHF, NZD→EURNZD, CAD→EURCAD, NOK→EURNOK, SEK→EURSEK`;
[EA_V3_DESIGN §4 `FedConvert.mqh`](../../model/v3/EA_V3_DESIGN.md)). **FMA3-RECON-4 Run 1 confirmed all 7
revived symbols trade (> 0 deals each)** on MT5 — the unconditional full-map eurq works end-to-end. These
are all Satellite-only lines, so their revival adds the crosses/index the blend's breadth was designed to
carry but had been silently missing under v1/v2.

---

## Part 3 — Execution reconciliation (FMA3-RECON-4, all 33 symbols trade)

**v3 holds the model's exact target position, and all 33 symbols trade.** Across the three tester runs
([RECON4_RESULTS.md](../../model/v3/RECON4_RESULTS.md)), the position-level fidelity — the ratio of v3's
held fraction to the model's target `fed_frac·s` — has **median `after/want` = 1.000 in every run**:

| Run | Preset | Dial | Seed → v3 equity | v3/model | Rejects | Fidelity (median after/want) |
|---|---|---|---|---:|---:|---:|
| 1 | `FABLE_PARITY_S10` | s=1.0 | €10k → €391,873 | **0.84** | 0 | 1.000 (**33/33 symbols**) |
| 2 | `FABLE_IC` | s=1.6 | €10k → €2,552,962 | **0.66** | 0 (after volume-limit fix) | 1.000 |
| 3 | `FABLE_FTMO` | s=0.7 | €100k → €1,265,541 | **0.95** | 0 | 1.000 (0 volume-capped) |

**Run 1 (parity, s=1.0) is the composition proof:** all 33 symbols trade, 0 rejects, fidelity 1.000. Where
v3 can place the order it holds precisely `fed_frac·s` — so any equity gap is pure, named friction, not an
execution defect. The equity reaches **0.66–0.95× the frictionless record** by dial/scale.

### The volume-capped symbols — a capacity ceiling, not a defect

The record engine sizes `lots = frac·balance/unit` with **no position ceiling**. A real broker enforces
`SYMBOL_VOLUME_LIMIT` per symbol. On IC acct 11078280 the binding caps are:

| Symbol | `SYMBOL_VOLUME_LIMIT` (this tier) | Binds when |
|---|---:|---|
| **XAUUSD** | **10 lots** | first to bind — caps the book past **~€2M/s** of equity |
| **ETHUSD** | 100 lots | large books only |
| **SOLUSD** | 1000 lots | large books only |

This is a **capacity ceiling that scales with account size**, not a dial-shifter: cost ~0–6% at €10k, but
17–40% at €1M (XAUUSD alone caps at ~half the model target). So **the €3.87M IC-s1.6 record is NOT physically
reachable on one retail account at that scale** — XAUUSD binds first. Run 1 (s=1.0, €10k) and Run 3 (FTMO,
€100k) had **0 volume-capped symbols** — volume never engages at those scales. Run 2 (s=1.6, €10k → €2.55M)
is where the clamp first bit; the volume-limit fix removed the pre-fix reject *spin* (v3 had retried the
un-holdable excess every bar) and the **equity is unchanged** because the cap is physical, not a bug.

Scaling past the ceiling (both owner-ratified): a **higher-tier account** (larger limits, one account), or
**N parallel accounts at €C/N each** — each holds 1/N of the model position under its own limit, aggregate =
the full model. At the deployable FTMO scale volume never binds.

---

## Monitoring flags for the MT5 demo

- **All 33 symbols must keep trading — watch the 7 revived lines first.** RECON-4 Run 1 confirmed AUDJPY,
  CADJPY, GBPJPY, NZDJPY, JP225, EURNOK, EURSEK all trade (> 0 deals) on the full-map eurq. The demo must
  confirm they stay alive on real ticks — a regression to the v1/v2 mispricing would silently zero them
  again, and the record engine (which prices them faithfully) would not warn you.
- **XAUUSD is the concentration AND the capacity ceiling.** It is the highest active-share line (98.3%),
  the stacked gold position of both parents, and the first symbol to hit `SYMBOL_VOLUME_LIMIT` (10 lots,
  binds ~€2M/s). Watch its held lots against the 10-lot cap as the book compounds; on IC at s=1.6 it caps
  at ~half target past ~€2M.
- **The netting on the 6 shared symbols is what a real EA must reproduce.** EURGBP (95.3% active), XAUUSD,
  USDJPY, USTEC and the two crypto lines carry one net position + one magic each. Watch fill counts and
  spread cost on EURGBP and XAUUSD first — the record-engine netting benefit (25,869 vs 26,809 fills) only
  materializes if the two books' opposing targets actually cancel before the spread is paid.
- **The volume clamp must clamp cleanly, not spin.** Run 2's pre-fix reject spin (51,346 retries, equity
  unchanged) is fixed in sha `740da0ff`; on real ticks confirm the clamp holds the cap without re-issuing
  the un-holdable excess.
- **Trade counts are conventions, not forecasts.** 25,869 is the record-engine netted fill count (open/add/
  reduce/close after quantization + the 0.25 dead-band); MT5 ledger fills use a different convention. Do not
  reconcile the demo ledger numerically against 25,869 — reconcile the *shape* (which lines churn, which
  hunt, that all 33 are alive and the 6 shared ones net).

---

## Honest caveats

- **Part 1 is matrix structure, not fills.** Active shares are properties of the frozen `static_fed(0.70)`
  *target* matrix; the 25,869 vs 26,809 netted-fill counts are pinned record-engine outputs. Both are
  in-sample; MT5 real-tick execution is the remaining test.
- **Active share is carried from v1.0's locked matrix (measured at s=1.1) and is scale-invariant** — the
  dial changes fraction *magnitudes*, not *which hours* a symbol is on, so the active-share column holds at
  the s=1.6 / s=0.7 dials. The mean |frac| magnitudes are NOT reproduced here because they scale with the
  dial; see [v1.0 TRADE_CHARACTERISTICS](../v1.0/TRADE_CHARACTERISTICS.md) for the s=1.1 magnitudes.
- **No per-symbol trade-count table is pinned from RECON-4.** Run 1 confirmed all 33 symbols trade and the
  7 revived ones each trade > 0 deals, with position fidelity median 1.000 — it did **not** pin a per-symbol
  ledger-fill count. Do not quote a per-symbol number; the canonical facts are "33/33 trade" and ">0 deals
  each" for the revived seven.
- **The volume caps are this account's tier only.** XAUUSD 10 / ETHUSD 100 / SOLUSD 1000 lots are IC acct
  11078280's `SYMBOL_VOLUME_LIMIT`; a higher-tier or N-account deployment changes them. The `sweep_s_volcap`
  engine additionally clamps US30 (12) and EURCAD (10) from the Run-4 plateaus — the three above are the
  headline binders (XAUUSD first). These caps do not bind at €10k or FTMO €100k scale.
- **v3 discards the entire v1/v2 sizing stack.** No `VBalance`, no quarterly reseed, no `e34` — those
  divergences are dissolved by replaying the netted stream, but that means v3's fidelity claim rests on the
  *stream* being correct (the exporter self-checks reproduce `static_fed` to `<1e-12` and the record engine
  to the euro), not on re-deriving the blend live.
- **The equity gap is friction, not defect — but it is real.** 0.66× at s=1.6, 0.84× at s=1.0, 0.95× at the
  deployable FTMO dial. The €3.87M IC-s1.6 record is a frictionless ceiling; do not present it as a
  deployable promise.
- **Everything is in-sample (IC 2020–2025).** RECON-4 ran on 1m-OHLC; real-tick + live demo are where this
  composition and its execution get falsified.

**All numbers above are in-sample (IC 2020–2025); MT5 real-tick + live demo are the remaining falsification
tests. Achievable equity is 0.66–0.95× the record by dial/scale (FMA3-RECON-4).**
