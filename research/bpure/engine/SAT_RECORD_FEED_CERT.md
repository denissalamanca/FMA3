# Sat sleeve — in-terminal RECORD-FEED bit-exact certification

**Why this exists.** The 2026-07-15 reconciliation of the +4.88% Sat `b_h` live-run
drift proved (bit-level, `max|diff|=0.0`) that swap / eurq / commission / engine are
**identical** between the EA and the golden — the drift is the **live-vs-record
price-feed basis**, not a port bug. But it also surfaced a real coverage gap: the
**Core** sleeve has an in-terminal record-feed bit-exact port cert
(`coresim/coresim_mql5_parity.json`, 32/32 segments = 0.0), and the **Sat** sleeve
had **none** — its only in-terminal evidence was the un-re-seeded live run. This
closes that gap: it drives the compiled `Sat/SatEquityNative.mqh` over the **record
feed** and asserts it reproduces the frozen golden Sat curve **bit-exact**, which
exonerates the port and leaves the feed basis as the sole explanation of the live
drift.

## What proves what
| Layer | Artifact | Status |
|---|---|---|
| Offline python twin `bh_stepper.py` vs golden (2.95M bars) | `bh_parity.json` | **PASS** (`max_abs_dequity=0.0`, final €449,707.7452664526) |
| Judge + golden-fixture fidelity vs `curve.parquet` | `sat_judge_selftest.json` | **PASS** (24/24 quarters, full-run gate hits target) |
| **Compiled MQL5 port on the record feed** vs golden | `sat_mql5_parity.json` | **PENDING owner run** |

## Run it (one terminal run — the machinery is pre-staged)
Inputs are already exported to Common Files (24× `FMA3_bh_inputs_<Q>.csv`, `FMA3_bh_golden_<Q>.csv`; no numba needed).

1. In MT5: **Navigator → Scripts → `TestSatEquityChain`**, drag onto **any** chart.
   Inputs: `InpFromQuarter=2020Q1`, `InpToQuarter=2025Q4`, `InpStateIn=""` (fresh 10k).
   It replays all 24 quarters in one run (state carried in memory), writing
   `FMA3_bh_actual_<Q>.csv` per quarter + a per-quarter VERDICT line + a CHAIN SUMMARY.
2. Then (offline judge — bit-exact actual-vs-golden, writes `sat_mql5_parity.json`):
   ```
   python3 research/bpure/engine/validate_mql5_sat.py
   ```
   Expect: `JUDGE PASS: 24 quarter(s) judged, 24 passed`, full-run gate
   `final equity 449707.7452664526 == target`.

A PASS certifies the Sat port bit-exact on the record feed → the Sat sleeve reaches
the same certification bar as Core, and the +4.88% live drift is confirmed as the
record-vs-live feed basis (not the port). Leaves `SAT_EQ` and the €3,872,872 model
headline untouched.

## Phase 2 (same branch, next) — the definitive feed-diff / localization
To nail the feed attribution to 100% and localize *which* price field carries it:
dump the EA's **live** Sat inputs for one quarter (the 289-col
`FMA3_bh_inputs_<Q>.csv` schema) during a tester run, then offline (a) diff live-vs-
record input arrays (expected: the spread-synthesized ask), and (b) feed the live
inputs through `bh_stepper` — it should reproduce the EA `b_h` and diverge +X% from
golden, confirming the price feed is 100% of the cause. Requires a small EA input-
dump mode + one tester run; built after this cert lands.
