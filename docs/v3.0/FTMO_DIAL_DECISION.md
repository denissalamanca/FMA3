# FTMO dial decision — s ≈ 0.70 under a ≤1-breach/year policy

*Decided 2026-07-15, grounded in the **native-EA runs** (FableBookNative, FTMO preset:
€100k, 1:100, 3% daily breaker) — not the record engine or memory. This supersedes the
earlier "shipped FTMO dial is unsafe" conclusion, which assumed a **zero-breach** standard
the owner does not hold.*

---

## The policy that sets the dial

**Owner risk model:** cash is **withdrawn monthly**, so the FTMO account stays near its €100k
base rather than compounding. Under that model, an occasional rule breach is **not a
catastrophe — it just means passing a new challenge** and resuming. The objective is therefore
**maximize the dial subject to ≤ 1 breach per year**, not "never breach." A breach = a day
that violates the FTMO **5% daily** loss rule **or** a drawdown that violates the **10%
max-loss** rule.

## The decision

**Ship FTMO at s ≈ 0.70** (the original dial), with **s ≈ 0.65 as the crisis-margin
alternative.** Rationale below.

## The two native-EA runs (full window less H1-2020; see caveat 1)

| | s=0.70 (Run A, `_41`) | s=0.35 (Run B, `_42`) |
|---|---:|---:|
| Net | +€930,208 (~+53% compounding CAGR) | +€264,205 (~+26.5%) |
| Static drawdown (worst %) | 14.11% | 5.53% |
| Worst daily dip | 5.23% (1 day > 5%) | 3.10% (0 days > 5%) |
| Days > 3% (breaker line) | 24 | 1 |
| Margin level · Sharpe · PF | 348% · 1.99 · 1.41 | 723% · 2.14 · 1.48 |

Under a **zero-breach** standard, s=0.70 fails (14.11% > 10%, one 5.23% day) and the safe dial
is ~s=0.35–0.50. But that is not the operative standard here.

## Breach frequency vs dial (Run A distribution scaled ~linearly by s)

| s | daily-5% /yr | 10% max-loss /yr | **total breach/yr** |
|---:|---:|---:|---:|
| 0.60 | 0.00 | 0.18 | **0.18** |
| 0.65 | 0.00 | 0.36 | **0.36** |
| **0.70** | 0.18 | 0.55 | **0.73** |
| 0.73 | 0.18 | ~0.75 | **~0.9** ← ceiling |
| 0.75 | 0.18 | ~0.9 | **~1.1** |
| 0.80 | 0.36 | 1.46 | **1.82** |

- **The 10% max-loss rule binds, not the daily-5%.** The 3% breaker holds daily losses well
  (only 0.18 daily breaches/yr even at s=0.70); it's the *sustained* drawdowns crossing 10%
  that cost a challenge (~3 such episodes over 5.5 years at s=0.70).
- **s ≈ 0.72–0.73 is the ≤1-breach/yr ceiling.** The shipped **s=0.70 sits comfortably inside
  at ~0.7 breaches/yr.** Above ~s=0.75 the rate climbs fast (s=0.80 → ~1.8/yr).

## Caveats (so the ≤1/yr claim isn't oversold)

1. **Both runs exclude COVID** (windows start 2020.07.01). A COVID-class crash would very
   likely add a breach at s=0.70, so the true rate *including crises* is somewhat higher —
   this is why **s ≈ 0.65 (0.36/yr) is the crisis-margin choice**, absorbing one bad crisis
   and still staying under 1/yr in normal years.
2. **Daily dips are hourly-sampled** (slightly optimistic) → treat ~s=0.73 as the aggressive
   edge and **s ≈ 0.70 as the honest ≤1/yr dial**.
3. **Probe status — mechanism parity, not assurance parity** (updated 2026-07-15,
   [FTMO_WEIGHT_PROBE.md](FTMO_WEIGHT_PROBE.md)). The earlier "FTMO has not been probed" is
   corrected: the ±20% **weight** probe DID run (FMA3-008/010, re-confirmed bit-exact by
   FMA3-011 + the s=0.65 dial added) on the same record engine, `static_blend`, and gate as
   IC's FMA3-004c — all six cells (s∈{0.70,0.65} × w∈{0.56,0.70,0.84}) clear every score_v3
   ceiling. But it is **pass-by-construction** (at s=0.70, w=0.70 is a local drawdown *max*:
   static DD 11.6/13.3/13.2% across w56/70/84 — both arms only reduce DD) and **frame-blind**
   (every s=0.70 cell's *static* drawdown 11.6–13.3% exceeds the 10% Max-Loss rule, yet
   score_v3's monthly reset still reports `P(breach12m)=0.0` — the same reset that reads 0.0
   where the native-EA static frame reads ~0.73/yr). The **binding lever is the dial s, not
   w**: on the breach table above, −20% of the dial (s=0.56)→≲0.15/yr but **+20% (s=0.84)→~2/yr,
   decisively past ≤1/yr**; ±20% w never approaches that cliff. **Net:** the dial is robust to
   ±20% *weight* drift, but s=0.70 sits at the *top* of its ≤1/yr band with no upside margin —
   an independent, robustness-based reason to prefer **s≈0.65** (0.36/yr). The higher bar
   **neither preset has cleared** is a native-EA-grade probe over w *and s*, scored on the raw
   non-reset static frame against the absolute €90k floor, over a real-tick crisis window —
   still the open arbiter (score_v3 gate fix tracked: task_03aba9d3).
4. Compounding-CAGR is not the owner's realized return (monthly withdrawal keeps the base
   ~€100k); the dial's value is the **monthly income** it produces, which rises with s — hence
   the appetite to run near the breach-frequency ceiling rather than far below it.

## Bottom line

**FTMO ships at s ≈ 0.70** (≈0.7 breaches/yr, dominated by the 10% rule), or **s ≈ 0.65** for
crisis headroom. The earlier cut to s≈0.35 was correct only under a zero-breach standard; under
the owner's monthly-withdrawal / ≤1-breach-per-year policy, the original dial stands. Open item
before the FTMO preset is as hardened as IC: the ±20% weight-probe pass, and a demo-forward.
