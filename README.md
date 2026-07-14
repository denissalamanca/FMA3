# FableMultiAssets3 — unified Core × Satellite book (IC Markets EU Raw, EUR)

Campaign to merge the structural edges of two independently-derived books into a
new frontier strategy, validated in the strictest common accounting.

**Current status: FMA3 v1.0 is LOCKED** (2026-07-10, config hash `51a7541cc2aaa593`) —
static blend, core weight = 0.70 Core / 0.30 Satellite, global scale 1.1, no cross-book
rebalancing. All six owner gates clear and **all seven composite dimensions
dominate both parents in the engine of record** — the first fully-dominant
point in either program's history. The 2026H1 one-shot forward confirmation
returned **CONFIRM 4/4** and is consumed; MT5 real-tick on the owner's machine
remains the deployable arbiter, then the live demo.

## Official v1.0 numbers (engine of record — Python 1m worst-mark, IC feed, 2020–25, €10k)

| CAGR | Max DD (worst-mark) | Sharpe | COVID tail | negY | negQ | Breach P(DD>30%) | €10k → |
|---|---|---|---|---|---|---|---|
| **+101.4%** | **15.73%** | **2.467** | **5.36%** | **0/6** | **0/24** | **0.002** | **€665,777** |

Pin: `research/outputs/fma3_v1_pin.json` (reproduce:
`python3 scripts/eval_fma3_pin.py`, ~7 min, expected delta 0.0). **All numbers
are in-sample**; the honest forward Sharpe expectation is ~1.6–2.0, not 2.47
(see the whitepaper's caveats).

## Parents

| Engine | Source repo | Architecture | Official (native engine) |
|---|---|---|---|
| **Core** (formerly v7.0) | `../NewStrategyFable5` (docs in `docs/v7/`) | 7 equal-capital slot-equity sleeves + BAND_SYM_25 re-split + H9 delta-resize, R10 | MT5 real-tick: CAGR 96.1% / Max eq-DD 20.9% / Relative (COVID) 35.6% / Sharpe 2.03 / 0 negY / 3 negQ. Python anchor (R8): 89.7% bd / 19.44% tick-DD / Sharpe 2.58 |
| **Satellite** (formerly v3.4) | `../FableMultiAssets2` | 8 fraction-of-equity sleeves × scale 10, hard limits, cash-park, single cross-margined account | Python 1m worst-mark: CAGR 88.7% / DD 21.7% / Sharpe 1.85 / 0 negY / 1 negQ / €449,708 / breach 0.121 |

**Note:** the Satellite parent (formerly v3.4) was built under an alpha firewall against NewStrategyFable5.
The owner has explicitly lifted that firewall for this project (2026-07-10).

## Charter (locked 2026-07-10)

- **Engine of record:** Python 1-minute worst-mark, single cross-margined account
  (Satellite-style `simulate_account_1m`). MT5 real-tick confirmation deferred to the
  owner's MT5 machine. Composite gates are re-derived in this engine — the
  original six gate numbers straddle two non-comparable engines.
- **Honesty rule:** honest frontier wins. Pre-committed bars, one lever at a
  time, DECLINE by default, full multiple-testing ledger. If the gates cannot be
  breached without fragility, the deliverable is the best honest frontier plus
  the evidence for why the ceiling holds.
- **Data perimeter:** read-only from `../NewStrategyFable5/cache/*` and
  `../FableMultiAssets2/research_cache*` (in place, not copied). 2026 data
  (`bars_1m_holdout`, `research_cache_fwd` tail, `../data/2026_ytd`) is
  never-fitted holdout. New downloads permitted when a hypothesis requires.

## Closed merge channels (do not re-litigate)

1. FMA2 sleeves as band slots — EXHAUSTED (H14/H15, 0-for-10 book-level tests).
2. Band mechanism into the fixed-fraction book — NOT IMPORTABLE (H8: premium
   flips −7.31pp under fixed-notional sizing).
3. FMA2 `intraday` ≡ NSF5 F1 (ρ 0.87) — a merged book must not carry both.
4. NSF5→FMA2 sleeve imports — one-shot 2015–19 OOS consumed.

## Repo layout

```
research/intel/       recon sweep over both parents (7 readers + critique)
research/baselines/   pinned reference artifacts backed up from both parents
research/protocol/    pre-registered evaluation bars (written before numbers)
research/outputs/     run outputs
config/               paths + account/instrument bridge
engine/               unified engine work
docs/                 v1.0/ shipped package + whitepaper/ research layer + REGISTRY.md
scripts/  tests/
```

## 📚 Documentation — start here

**The shipped v1.0 package lives in [docs/v1.0/](docs/v1.0/README.md)** (index +
six docs + dashboard, mirroring the parents' shipped-version convention); the
whitepaper is the research layer beneath it.

| Doc | What it covers |
|---|---|
| **[docs/v1.0/README.md](docs/v1.0/README.md)** | **The shipped v1.0 package (start here)** — one-page index: headline, gate scoreboards, the six docs + dashboard, the research layer |
| [docs/v1.0/STRATEGY.md](docs/v1.0/STRATEGY.md) | What v1.0 is & why — the blend mechanics, core weight = 0.70, s = 1.1, everything declined |
| [docs/v1.0/PERFORMANCE.md](docs/v1.0/PERFORMANCE.md) | The canonical performance read — pin, gates, tables, friction, scale frontier, forward one-shot |
| [docs/v1.0/VALIDATION.md](docs/v1.0/VALIDATION.md) | The 6-tier battery & sign-off — reproduction chain, pre-registered ladder, red team, CPCV/DSR, one-shot |
| [docs/v1.0/RECONCILIATION.md](docs/v1.0/RECONCILIATION.md) | Three engines, one accounting — every bridge at delta 0.0; the measured translation costs |
| [docs/v1.0/TRADE_CHARACTERISTICS.md](docs/v1.0/TRADE_CHARACTERISTICS.md) | Book-level mixing (measured) + per-sleeve profiles (inherited by citation) |
| [docs/v1.0/DEMO.md](docs/v1.0/DEMO.md) · [docs/v1.0/DASHBOARD.html](docs/v1.0/DASHBOARD.html) | The demo deployment/monitoring plan · the one-page visual scorecard |
| **[docs/whitepaper/00_WHITEPAPER.md](docs/whitepaper/00_WHITEPAPER.md)** | **The Fable Book** (research layer) — executive summary, document map, definition of done |
| [docs/whitepaper/01_DECONSTRUCTION.md](docs/whitepaper/01_DECONSTRUCTION.md) | The two frozen parents, the firewall history, the engine-of-record decision |
| [docs/whitepaper/02_FEDERATION_DESIGN.md](docs/whitepaper/02_FEDERATION_DESIGN.md) | Blend mechanics, anti-coupling guard, the pre-registered evaluation ladder |
| [docs/whitepaper/03_SCORECARD.md](docs/whitepaper/03_SCORECARD.md) | Results — the frontier scorecard, experiment trail, red-team battery, honest caveats |
| [docs/REGISTRY.md](docs/REGISTRY.md) | Every experiment ever run (incl. failures) — the honest multiple-testing ledger |
| [research/protocol/PROTOCOL.md](research/protocol/PROTOCOL.md) · [HYPOTHESES.md](research/protocol/HYPOTHESES.md) · [FORWARD_TEST.md](research/protocol/FORWARD_TEST.md) | The pre-registrations (committed before their numbers existed) |
| [research/outputs/COMPOSITE_BENCHMARK.md](research/outputs/COMPOSITE_BENCHMARK.md) | Both parents in one accounting; composite gates; the measured MT5↔1m tail gap |

**Single source of truth (code):** `strategy_fma3.py` (locked config) →
`scripts/eval_fma3_pin.py` → `research/outputs/fma3_v1_pin.json`.

## Status

- [x] Recon/assimilation of both parents (2026-07-10)
- [x] Baseline reproduction (Satellite pin + Core Python anchor) — byte-exact
- [x] Unified engine + both baselines in the engine of record (41/41 + 15/15 delta 0.0; ext engine bit-identical)
- [x] Pre-registered protocol + hypothesis slate (committed before any merged number)
- [x] Hypothesis loop — H-FED-1 confirmed (w = 0.70) · H-FED-2 declined · H-CAPS-1 no-op · H-FED-3 frontier mapped
- [x] Red-team battery — 6 checks; the one FAIL (w+20% perturbation) adjudicated into the probe-robust scale s = 1.1
- [x] Production lock + pin (config hash `51a7541cc2aaa593`, reproduces delta 0.0) + whitepaper
- [x] **2026H1 one-shot forward confirmation — CONFIRM, 4/4 bars** (window +12.34%, DD 17.67% < 20.9%, both sub-books positive, 0 margin events; holdout CONSUMED; see whitepaper §7)
- [ ] MT5 real-tick run on the owner's machine (deployable arbiter)
- [ ] Live demo
