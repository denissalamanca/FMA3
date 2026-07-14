# Pinned model inputs — v3 stable model

The model is a deterministic function of **4 frozen artifacts + 2 scalars (w, s)**. Any change to a hash below re-opens the model. Verified 2026-07-12.

## Config
| Item | Value |
|---|---|
| `strategy_fma3.config_hash()` | `51a7541cc2aaa593` |
| `w_v7` (capital share) | `0.70` |
| IC dial `s` | `1.6` (compounding, seed €10,000) |
| FTMO dial `s` | `0.7` (+ daily breaker x=3.0%, seed €100,000) |

## Frozen input artifacts (sha256 prefix / size)
| Symbol | Path | sha256[:16] | bytes |
|---|---|---|---:|
| `frac7` | `research/outputs/v7_book_frac_1h.parquet` | `450e65bee7307d09` | 2,402,982 |
| `a` (eq7) | `research/outputs/v7_book_equity_1m.parquet` | `ccb0335df45d9a03` | 86,394,345 |
| `b` (eq34) | `research/baselines/fma2/v34_s10_pin_curve.parquet` | `a5787993a3413108` | 68,173,535 |
| `frac34` | `engine/books.build_v34_frac_1h()` → `eval_v34_pin_s10.build_c2()` (read-only FMA2 pin) | *(code, deterministic)* | — |

`frac34` is generated in code from the read-only FMA2 v3.4 pin; it is deterministic (31 cols, GLOBAL_SCALE=10, gold cap 1.80 pre-applied). The exporter `scripts/export_sat_replay.py` hard-fails if the brain path drifts from `books.build_v34_frac_1h()` beyond 1e-12 — that gate is the frac34 pin.

## To re-verify the pins
```
python3 strategy_fma3.py | grep config_hash        # -> 51a7541cc2aaa593
shasum -a 256 research/outputs/v7_book_frac_1h.parquet
shasum -a 256 research/outputs/v7_book_equity_1m.parquet
shasum -a 256 research/baselines/fma2/v34_s10_pin_curve.parquet
python3 model/v3/reproduce.py                       # asserts both headline equities
```
