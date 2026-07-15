# FMA v4 — Hypotheses & Opportunities backlog

*Opened 2026-07-15. Sourced from the deep-dive on the **IC 1-minute 2020-2025 run
(#36, `FableBookNative`, s=1.6, net €2.92M)**. This is a **prioritised backlog for a
potential v4**, not committed work — each item is a hypothesis with the preliminary
data that motivates it and an honest priority. Nothing here changes v3.*

**Provenance / caveats that apply throughout:** numbers are from the 1m-OHLC #36 run and
the standalone golden sleeve curves; 6 of 8 Core symbols are netted with Sat, so per-symbol
P&L for those is a blended figure; the COVID-crash window is cold-started (book held ~0).

---

## Priority summary

| # | Item | Type | Priority | One-line |
|---|---|---|---|---|
| B1 | Home-run dependence | risk | **HIGH** | 25 of 5,008 trades = 95% of net; median trade = −€0 |
| B2 | Diversification decay under stress | risk | **HIGH** | Core-Sat corr rises to +0.76 in the Apr-25 shock |
| A1 | Historical-regime robustness | test-method | MEDIUM | low-vol chop / grind-bear the window never saw |
| A2 | Symbol cull/keep (LOO ablation) | test-method | MEDIUM | test dead-weight by portfolio ΔSharpe, not P&L |
| B3 | Swap-killed legs | return | MEDIUM | €590k mostly unrecoverable; ~€78k on 3 legs is |
| B4 | Margin-efficiency reallocation | return | MEDIUM | fold into A2 (same ablation) |
| B5 | Dynamic regime-tilt | return | LOW | naive tilt underperforms static; parked |

---

## A. Deferred test-methods (agreed 2026-07-15 — record, don't run yet)

### A1 — Historical-regime robustness (the regimes 2020-2025 never contained)
**Hypothesis.** The 6-year window is lopsided — 5 of 6 non-crisis regimes are liquidity bulls,
the one bear (2022) still netted +63%/+42%, and all 3 crises were **sharp V-shapes that
recovered in weeks**. The book has **never** faced (a) a **slow grinding multi-year bear**
(2000-02, 2008), or (b) a **prolonged low-vol chop bull** (2013-19) — the two regimes most
dangerous to a levered trend-follower — or (c) **stagflation** (1970s).

**Feasibility (Dukascopy / synthetic).**
- **Low-vol chop 2015-2019 = best real candidate** — FX/metals/indices/energy covered; run
  through the **Python record engine** on a symbol subset.
- **Hard limits:** crypto legs can't run pre-2020 (SOL never; BTC/ETH from ~2017) → a
  crypto-less *partial* book; index CFDs are a **cross-broker proxy**; 2008 too partial
  (no indices/energy/crypto); **stagflation impossible** (no data — 2022 is the only proxy,
  already in-sample).
- **Real cost:** the NSF5 Core + v34 Sat signal pipelines must *run on the new bars* (compute
  targets, not replay a curve) — a genuine wiring project.
- **Cheaper complement:** a **synthetic-regime** exercise — bootstrap/stretch the existing
  2020-25 return blocks into a low-vol grind and a slow-bear path — zero data gaps; do this
  first, then decide if the Dukascopy pull is worth it.

### A2 — Symbol cull/keep via leave-one-out (LOO) ablation
**Hypothesis.** Some legs are dead weight (oil XTI+XBR −€68k, NZDJPY −€25k, EURUSD 1 trade in
6y); some low-trade legs are cheap diversifiers worth keeping (NZDCAD +€42k/69% win, AUDCAD
+€14k/83% win, USDJPY carry +€321k).

**Method (P&L alone is the wrong test).** Re-run the book with each candidate's target column
**zeroed**, through the account engine, and gate on **portfolio ΔSharpe / ΔmaxDD**, not the
symbol's own P&L — cull only if removal *improves* the portfolio; keep if removal *hurts*
(it was hedging). Layer: (1) regime-conditional P&L (does it lose everywhere, or hedge in
stress?); (2) swap-vs-alpha split (UK100's loss is 82% swap — a cost fix, not a delete);
(3) marginal risk contribution. **Fold B4 (margin-efficiency) into this same ablation.**

---

## B. Data-backed opportunities (from the #36 deep-dive)

### B1 — Home-run dependence — **HIGH (risk)**
**Data.** Of 5,008 cycles: top-1 trade (the €678k gold capture) = **23.2%** of net; top-5 =
57.1%; top-10 = 71.0%; **top-25 = 95.1%.** Net *without* the top-10 = €847k; *without* top-25
= **€142k.** Win rate 49.3%, **median trade = −€0**, mean +€583.
**Read.** The +€2.92M is **25 home runs carrying 5,000 coin-flips** — not broad alpha. This is
the mechanical explanation for "+158% in-sample vs +12.34% OOS forward." **v4 questions:** is
the home-run capture robust (do the big trend-captures recur OOS)? does position-sizing
over-rely on a few legs (gold/Nasdaq)? what is the book's return if the tail is trimmed by
regime? — a fragility audit, the highest-value item here.

### B2 — Diversification decays under stress — **HIGH (risk)**
**Data.** Core-Sat **daily** return correlation by regime: COVID crash **−0.16** (true hedge),
2022 bear +0.14, but Aug-24 carry unwind **+0.51**, **Apr-25 tariff +0.76**, and the bulls
+0.4–0.5. Full-period daily avg **+0.35** (the +0.109 quoted elsewhere is the *monthly* avg).
**Read.** The ballast thesis (low Core-Sat correlation) holds *on average* but **evaporates in
the most recent crises** — exactly when it's needed. COVID's anti-correlation looks like the
exception. **v4 questions:** is the rising correlation structural (both sleeves crowding into
the same macro trades) or regime-noise? does the Sat 30% weight still earn its keep if crises
increasingly look like Apr-25 (correlated) rather than COVID (hedged)? Directly tests the v3
diversification premise under modern conditions.

### B3 — Swap-killed legs — **MEDIUM (return)**
**Data.** Total swap −€590k, but **89% is XAUUSD (−€358k) + USTEC (−€167k)** — the two biggest
winners, where the overnight hold *is* the alpha → **not recoverable.** Genuine targets are the
legs swap *kills*: **EURGBP** (−€53k swap = 77% of its net), **US30** (−€14k on +€1k net →
strongly positive without swap), **UK100** (−€11k = 82% of its loss). Carry earners (USDJPY
+€74k, GBPJPY +€3k) must be left alone.
**Read.** Reframe from "recover €590k" (impossible) to "fix the ~€78k of **swap-killed legs**"
— a rollover-aware exit or reduced overnight hold on EURGBP/US30/UK100, if the signal survives.
Narrow but real; verify the signal isn't itself the overnight move before changing it.

### B4 — Margin-efficiency reallocation — **MEDIUM (fold into A2)**
**Data.** Worst capital-efficiency legs (crude footprint proxy = cycles × hold × lots) are the
same SAT losers — EURSEK, USDCHF, NZDJPY, EURCAD, CADJPY, XTIUSD — tying up margin-time for
negative return. **The proxy is too crude to size** (EURUSD ranks "best" only because it has 1
trade). Margin (not volume) is what caps the IC dial at s=1.6 (min-ML 121%), so freeing it from
dead legs *could* lift the deployable s-ceiling.
**Read.** Real idea, but it **is** the A2 ablation with a margin lens — do them together; a
proper margin model / LOO re-run is required to know if reallocation actually raises the dial.

### B5 — Dynamic regime-tilt — **LOW (parked)**
**Data.** Unlevered monthly Sharpe: static 70/30 = **3.62**; a naive high-vol→Core tilt = **3.55
(worse)**; hindsight oracle = 5.22.
**Read.** The clean Core-wins-stress / Sat-wins-bull split (from the regime table) *suggests* a
tilt, but the naive rule **underperforms** the static blend, and the static book is already
strong. There's a theoretical ceiling (oracle) but no evidence a realizable, non-lookahead
signal captures it. **Park** unless a genuine regime detector emerges — low expected payoff.

---

## Note on the regime evidence behind all of this

The sleeve-by-regime table (Core wins 2022-bear / disinflation / Aug-24-unwind / 2025; Sat wins
reflation / 2024-AI / the grind; crisis-complementary hedging) lives in
[`../v3.0/SLEEVE_REGIME_ANALYSIS.md`](../v3.0/SLEEVE_REGIME_ANALYSIS.md) and the 2026-07-15
deep-dive. B1 and B2 are the risk-side reading of that same evidence and are the recommended
first work if v4 opens.
