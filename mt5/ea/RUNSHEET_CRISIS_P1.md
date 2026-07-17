# RUNSHEET — Phase 1: native-EA on-broker crisis real-tick certification

*Prepared 2026-07-15. Owner-executed (I cannot launch terminal64.exe). Goal: the
**first-ever real-tick run of `FableBookNative`** (account 11078280), on the
crisis windows the broker **does** have real ticks for, to (a) prove the native
EA survives a real crisis on real ticks and (b) **measure the record→tick
drawdown multiplier `k` for the current book** — which today is only known from
the OLD account / OLD EA / v7-Core sub-book.*

---

## Why this run (the scope in five lines)

- The two crises that bind the book — **COVID 2020-03** and **2022 Oct-Dec** —
  **predate this broker's real-tick history (~2023)**, so they cannot be
  real-ticked from account 11078280 at all. That is a later, separate campaign.
- But the broker **does** have real ticks for two genuine post-2023 vol events:
  **Aug-2024 (yen carry unwind, VIX ~65)** and **Apr-2025 (tariff shock)**. Both
  stress the book's concentrated legs (JPY-crosses, USTEC/indices, gold, crypto).
- `FableBookNative` has **never** run on real ticks — every report (`_36`, `_41`,
  `_42`) is 1-minute-OHLC. 1m-OHLC fabricates the intra-bar ask path and
  **understates crisis drawdown**.
- The ratified record→tick crisis multiplier **`f_tail = 6.5×` (range 3.4–6.5×)**
  is measured on the **v7-Core sub-book, old account 52949549** — NOT this EA.
  This run gives the **native EA's own `k`** on a real crisis.
- **PROVENANCE RULE:** every number from this run is `FableBookNative` / account
  **11078280**. **Never** merge or compare it with the old-account 52949549 /
  `FableFederation` numbers (e.g. the ~40% COVID figure) — a prior draft did that
  and it was struck as an error.

---

## The runs to execute

Two presets. For each, one **real-tick** run — the OHLC reference already exists
(`_36` for IC, `_41` for FTMO), and the only change from those is the **tick
model**, so the warm-up is matched.

### Run 1 — IC preset, real ticks (PRIMARY)
| Field | Value |
|---|---|
| Expert | `FableBookNative` |
| Symbol (chart clock) | `BTCUSD` (same as `_36`; the EA drives all 33 legs from its own feed) |
| Period | **M1** |
| **Modelling** | **Every tick based on real ticks** ← the only change vs `_36` |
| Date range | `2020.01.01 → 2025.12.31` (identical to `_36`) |
| Deposit | **10000 EUR** |
| Leverage | **1:30** |
| Optimization | off |
| **Inputs** | `InpScale=1.60` · `InpInitial=10000.0` · `InpDailyStopX=0.0` · `InpAllowLiveTrading=false` · `InpSaveInTester=false` · `InpLog=true` (rest = defaults) |

### Run 2 — FTMO preset, real ticks
| Field | Value |
|---|---|
| Expert | `FableBookNative` |
| Symbol | `BTCUSD` |
| Period | **M1** |
| **Modelling** | **Every tick based on real ticks** |
| Date range | `2020.07.01 → 2025.12.31` (matches `_41`) |
| Deposit | **80000 EUR** |
| Leverage | **1:30** |
| Inputs | `InpScale=0.70` · `InpInitial=80000.0` · `InpDailyStopX=3.0` · `InpAllowLiveTrading=false` · `InpSaveInTester=false` · `InpLog=true` |

> **If the full 6-year real-tick run is too slow** (a 33-leg every-real-tick pass
> can run for many hours): use the **faster windowed variant** — date range
> `2023.01.01 → 2025.12.31` for BOTH the real-tick run AND a matched **1-minute
> OHLC** run of the same window/preset (4 runs total). The book cold-starts at
> 2023-01 and is fully warm (~250 weekdays) well before Aug-2024; the matched
> OHLC run over the same window is then the clean `k` reference instead of
> `_36`/`_41`. Tell me which variant you ran so I slice/compare correctly.

---

## The two crisis windows I will slice out

I compute `k` inside these sub-windows (they sit in the real-tick era):

| Crisis | Slice window | Peak stress | Legs stressed |
|---|---|---|---|
| **Aug-2024 yen carry unwind** | `2024-07-29 → 2024-08-16` | **Aug 5** (Nikkei −12.4%, VIX ~65) | USDJPY / JPY-crosses, USTEC/indices, BTC/ETH |
| **Apr-2025 tariff shock** | `2025-03-31 → 2025-04-16` | ~Apr 8 trough, Apr 9 reversal | indices, gold, FX, crypto |

---

## Before you run — three mechanical checks

1. **Confirm real ticks are actually used, not generated.** After the run, open
   the tester **Journal** and check it downloaded/used *real ticks* for the
   crisis dates (look for tick-download lines and a high modelling-quality bar).
   *A run that silently falls back to generated ticks is no better than `_36`.*
   If the broker has no real ticks for a leg in-window, note which.
2. **Clean init on the chosen start.** Watch the first Journal lines for a clean
   init (no refuse-latch, no stall). The full-window init bugs are fixed
   (RECON-8j/8k), but the real-tick model + (if used) the 2023 start are new
   config — flag any stall.
3. **Safety.** `InpAllowLiveTrading=false` stays false (the tester auto-trades
   regardless; on a live chart it would send zero orders). Zero risk.

---

## What to send me after each run

- The **report file** name (`ReportTester-11078280_NN.xlsx`) — I copy it before
  the next run overwrites, same as the `_36`/`_41` flow.
- The **hourly telemetry CSV** (`FMA3_native_hourly.csv` in `Common\Files`) if it
  is written — gives the per-hour equity/worst-mark path for a clean DD slice.
- One line on the **modelling quality** / any leg without real ticks in-window.

## What I will compute + deliver

- **Native-EA `k_dd`** = real-tick max-mark DD ÷ OHLC max-mark DD, per crisis
  window, per preset — and compare to the ratified **6.5×** (old-account/v7-Core).
  If native `k` ≪ 6.5×, the imputed COVID bound is **conservative** (reassuring);
  if ≈ or ≥, it **validates or tightens** it.
- **Retention** (real-tick CAGR ÷ OHLC CAGR) over the real-tick era, **min margin
  level**, **position fidelity**, and the FTMO daily-breaker fire count on real
  ticks.
- A **RECON-12** ledger entry + a short results doc — the first real-tick evidence
  for the native EA, provenance-clean.
- **Then** the informed call on the historical tail (COVID/2022): accept the
  `f_tail` imputed bound, or mount the external-data (Dukascopy) faithful-proxy
  campaign — decided **with the native-EA `k` in hand**, not before.
