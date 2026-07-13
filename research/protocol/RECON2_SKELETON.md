# FMA3-RECON-2 — RUN 2 real-tick reconciliation (PRE-FILLED SKELETON)

Prepared 2026-07-11 (autonomous, pending owner RUN 2). Fill the **MEASURED** cells
after each F7. This closes Task #13 (final IC dial) + Gate 6.

## Identity
- **RECON_MODEL_HASH:** `51a7541cc2aaa593` (frozen federation: v7 band w_v7=0.70 + v3.4 replay, cross-margined)
- **EA hash:** `f71bd67d` (RUN 1b binary) → **`1a36fcbf`** (governor build, 127,770 B, 2026-07-11)
- **Governor parity gate: PASSED** — `_59.xlsx` (`FED_IC_G3B`, `InpMinMarginLevel=0`, 1m-OHLC) reproduced RUN 1b **€51,479.93 to the cent** over 17,945 deals → governor provably inert at default; frozen book bit-identical.
- **Friction k (deploy dial multiplier):** **0.96** (~1). Proven: imposing the EA's real COVID
  net-lots on the record engine's IC worst-mark reproduces MT5 to 0.06pp. Gate-2 band
  k_point ∈ [0.70,1.30]; hard-REJECT only if 90% CI lower bound on k > 1.5 → not at risk.

## Candidate dial: **s = 0.70**  (fallback 0.60, upside probe 0.80)
Verify-corrected down from the raw synth pick of 0.8 (which leaned on a record-engine
margin readout known to be a lower bound). Presets ready:
`mt5/ea/presets/FED_IC_RUN2_S070.set` / `_S060.set` / `_S080.set`.

**Dial mapping (CRITICAL — `InpScale`/`InpWv7` are INFORMATIONAL; `InpRisk`/`InpV34Mult` GOVERN):**
| s | InpRisk = 8·w·s | InpV34Mult = (1−w)·s | InpSizingBase |
|---|---|---|---|
| 0.60 | 3.36 | 0.18 | 0 (compound) |
| **0.70** | **3.92** | **0.21** | **0 (compound)** |
| 0.80 | 4.48 | 0.24 | 0 (compound) |

## Gates
- **DD gate:** gated DD = max(warm, COVID) × k ≤ **30%**. *Already comfortable* — COVID (imputed
  EA positions) is the driver; at s=0.7 ≈ 18.6% × 0.96 = **17.8%** (59% of ceiling). NOT the binder.
- **Gate 6 (IC margin, RATIFIED 2026-07-11) — THE BINDER, decided ONLY on this compounding real-tick run:**
  peak desired deposit-load ≤ **75%** (band 70–80%) at retail 1:30; min-ML comfortably >100–125%
  (≫50% stop-out); report No-money-reject count. **Mandatory, non-waivable.**
  - ⚠️ The record engine CANNOT set this — its `margin_cap=0.9` soft-shrinks the very positions
    (May-2022 USDJPY pyramid) that blow up real 1:30 load, so its readout is a **lower bound**.
    True load extrapolated from g3-forensics (1.5–2.0× equity at s=1.6, ∝ s): **~66–88% at s=0.7,
    ~56–75% at s=0.6, ~75–100% at s=0.8.** This run is what decides it.

## PREDICTED at s=0.70 (record-engine warm 2021-25 + linear-imputed COVID; LOWER BOUNDS on stress)
| metric | value | vs gate |
|---|---|---|
| warm full-run max worst-mark DD | 10.43% @2022 | — |
| COVID imputed worst-mark DD | 18.59% | — |
| gated DD (max × 0.96) | **17.8%** | ≤30% ✅ (not binding) |
| warm min margin-level (record, lower bound) | 282% | — |
| warm peak deposit-load (record, **lower bound**) | 36.8% | true ~66–88% vs 75% ⚠️ |
| No-money rejects (record est.) | 0 | — |

## MEASURED — RUN 2a, s=0.70 real ticks  *(TODO after F7)*
- full-run max equity DD %: `____`
- COVID-window (2020-02..04) max equity DD %: `____`
- min margin-level % + timestamp: `____`
- **peak desired deposit-load %: `____`  ← Gate 6 verdict input**
- No-money / reject count: `____`
- stop-out fired? (level 0.50): `____`
- final equity (10k start, compounding): `____`
- k(s) transfer (real-tick DD vs record-engine curve at s=0.7): `____`
- **Gate DD verdict:** `____`  · **Gate 6 verdict:** `____`
- **DEPLOY 0.70 / FALL BACK 0.60 / PROBE 0.80:** `____`

## MEASURED — RUN 2b (only if 2a fails Gate 6): s=0.60  *(TODO)*
- full-run DD / COVID DD / min-ML / **peak load** / rejects: `____`

## MEASURED — RUN 2c (only if 2a clears with room): s=0.80 upside probe  *(TODO)*
- full-run DD / COVID DD / min-ML / **peak load** / rejects: `____`

## Decision rule
1. Run **2a (s=0.70)** first. If **peak load ≤ 75%** and no stop-out/reject → **s=0.70 is the dial** (optionally probe 0.80 for more return).
2. If 2a's peak load > 75% (or a stop-out fires) → run **2b (s=0.60)** and ship the first that clears.
3. Record the shipping s here, then proceed to Task #19 (regenerate IC/FTMO dashboards + refresh v1.0 docs to the final dial).

## What RUN 2 resolves that the pre-scan could not
1. **True unconstrained retail-1:30 load** (the record engine's margin_cap=0.9 hides it) — the Gate-6 verdict.
2. **Real Mar-2020 tick spread/gap/stop-out** (the pre-scan priced COVID on 1m-OHLC worst-mark; the −40%→−18.6% scaled DD leans on a thin post-midnight EURGBP ask_h extreme that real ticks confirm or soften).
Everything else (warm-era pricing k=0.96, warm DD, federation config) is already proven faithful.
