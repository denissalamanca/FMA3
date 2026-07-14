#!/usr/bin/env python3
"""Stage-6 validation of the b_h scalar stepper (bh_stepper.py).

Three stages, fail-fast:
  1. SUBWINDOW 2020-01..2020-06 (2020Q1+2020Q2): scalar stepper vs numba
     _run_chunk on identical inputs, per-bar eq_close/eq_worst compare.
     Any relative diff > 1e-9 -> print the first divergent bar and STOP.
  2. FULL RUN 2020Q1..2025Q4 through the scalar stepper only (~2.9M bars,
     pure python), per-bar compare vs the golden curve.parquet, plus derived
     metrics (CAGR / MaxDD_worst / final EUR) vs the frozen pin.
  3. WARM-START: the account state serialized to JSON right after the 2022Q2
     chunk (during stage 2) is loaded into a FRESH stepper which replays
     2022Q3..2025Q4; the tail must be bit-identical to the stage-2 curve.

Writes bh_parity.json next to this file. All numbers are MEASURED.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

import bh_stepper as B  # noqa: E402  (also injects FMA2/research into sys.path)

import numpy as np      # noqa: E402
import pandas as pd     # noqa: E402
import core             # noqa: E402
import account_engine_1m as A1  # noqa: E402

GOLDEN = B.GOLDEN
PIN_PATH = Path("/Users/dsalamanca/vs_env/FableMultiAssets2/research/outputs/"
                "v34_s10_pin_1m.json")
OUT_JSON = ENGINE_DIR / "bh_parity.json"

WARM_SNAPSHOT_AFTER = "2022Q2"      # serialize state after this chunk
WARM_RESUME_FROM = "2022Q3"


def rel_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """|a-b| / max(|b|, 1e-12) elementwise (b = reference)."""
    return np.abs(a - b) / np.maximum(np.abs(b), 1e-12)


def sig_digits_agree(x: float, ref: float) -> float:
    """Number of significant digits of agreement (inf if bit-equal)."""
    if x == ref:
        return float("inf")
    if ref == 0.0:
        return 0.0
    return -np.log10(abs(x - ref) / abs(ref))


# --------------------------------------------------------------------- stage 1
def stage1_subwindow(pos, symbols, consts):
    contract, comm, lev, lstep, mlot, stop_out = consts
    st = B.make_stepper(symbols)
    nb_bal = 10_000.0
    nb_lots = np.zeros(len(symbols))
    nb_entry = np.zeros(len(symbols))
    nb_trades = 0

    max_rel_c = 0.0
    max_rel_w = 0.0
    max_abs_c = 0.0
    max_abs_w = 0.0
    bars = 0
    t0 = time.time()
    for ch in B.iter_chunks(pos, "2020Q1", "2020Q2"):
        sc_c, sc_w = B.run_chunk_scalar(st, ch)
        nb_c, nb_w, nb_bal, nb_lots, nb_entry, ntr = A1._run_chunk(
            ch["tgt"], ch["has"], ch["bid_o"], ch["ask_o"], ch["bid_c"],
            ch["ask_c"], ch["bid_l"], ch["ask_h"], ch["eurq"],
            ch["swap_l"], ch["swap_s"], contract, comm, lev, lstep, mlot,
            stop_out, 0.9, 0.25, nb_bal, nb_lots, nb_entry)
        nb_trades += ntr
        sc_c = np.asarray(sc_c)
        sc_w = np.asarray(sc_w)
        rc = rel_diff(sc_c, nb_c)
        rw = rel_diff(sc_w, nb_w)
        bad = np.flatnonzero((rc > 1e-9) | (rw > 1e-9))
        if bad.size:
            i = int(bad[0])
            ts = ch["gidx"][i]
            print(f"STAGE1 FAIL: first divergent bar {ts} "
                  f"(chunk {ch['qp']} row {i})")
            print(f"  eq_close scalar={sc_c[i]!r} numba={nb_c[i]!r} "
                  f"rel={rc[i]:.3e}")
            print(f"  eq_worst scalar={sc_w[i]!r} numba={nb_w[i]!r} "
                  f"rel={rw[i]:.3e}")
            return {"pass": False, "first_divergent_bar": str(ts),
                    "chunk": str(ch["qp"]), "row": i,
                    "eq_close": [float(sc_c[i]), float(nb_c[i])],
                    "eq_worst": [float(sc_w[i]), float(nb_w[i])],
                    "bars_checked": bars + i}
        max_rel_c = max(max_rel_c, float(rc.max()) if rc.size else 0.0)
        max_rel_w = max(max_rel_w, float(rw.max()) if rw.size else 0.0)
        max_abs_c = max(max_abs_c, float(np.abs(sc_c - nb_c).max()))
        max_abs_w = max(max_abs_w, float(np.abs(sc_w - nb_w).max()))
        bars += len(sc_c)
        print(f"  stage1 {ch['qp']}: {len(sc_c):,} bars OK "
              f"(bit-equal close={np.array_equal(sc_c, nb_c)} "
              f"worst={np.array_equal(sc_w, nb_w)})", flush=True)
    state_match = (st.balance == nb_bal
                   and np.array_equal(np.asarray(st.lots), nb_lots)
                   and np.array_equal(np.asarray(st.entry), nb_entry)
                   and st.n_trades == nb_trades)
    out = {"pass": True, "bars": bars,
           "max_abs_dclose": max_abs_c, "max_abs_dworst": max_abs_w,
           "max_rel_dclose": max_rel_c, "max_rel_dworst": max_rel_w,
           "carry_state_equal": bool(state_match),
           "seconds": round(time.time() - t0, 1)}
    print(f"STAGE1 PASS: {bars:,} bars, max rel dclose {max_rel_c:.3e}, "
          f"max rel dworst {max_rel_w:.3e}, carry state equal {state_match}",
          flush=True)
    return out


# --------------------------------------------------------------------- stage 2
def stage2_full(pos, symbols, gold):
    st = B.make_stepper(symbols)
    idx_parts, c_parts, w_parts = [], [], []
    warm_state_json = None
    t0 = time.time()
    for ch in B.iter_chunks(pos, "2020Q1", "2025Q4"):
        tq = time.time()
        c, w = B.run_chunk_scalar(st, ch)
        idx_parts.append(ch["gidx"])
        c_parts.append(np.asarray(c))
        w_parts.append(np.asarray(w))
        print(f"  stage2 {ch['qp']}: {len(c):>7,} bars in "
              f"{time.time()-tq:5.1f}s | bal EUR {st.balance:,.2f} "
              f"| trades {st.n_trades:,}", flush=True)
        if str(ch["qp"]) == WARM_SNAPSHOT_AFTER:
            warm_state_json = json.dumps(st.get_state())
            print(f"  [warm snapshot serialized after {WARM_SNAPSHOT_AFTER}: "
                  f"balance {st.balance:.6f}, trades {st.n_trades}]",
                  flush=True)
    idx = idx_parts[0].append(idx_parts[1:])
    eq_c = pd.Series(np.concatenate(c_parts), index=idx, name="equity")
    eq_w = pd.Series(np.concatenate(w_parts), index=idx, name="worst")
    runtime = time.time() - t0

    # ---- per-bar compare vs golden ----
    g_eq = gold["equity"].to_numpy()
    g_w = gold["worst"].to_numpy()
    index_equal = bool(len(gold) == len(eq_c)
                       and np.array_equal(gold.index.values, idx.values))
    a_eq = eq_c.to_numpy()
    a_w = eq_w.to_numpy()
    d_eq = np.abs(a_eq - g_eq)
    d_w = np.abs(a_w - g_w)
    r_eq = rel_diff(a_eq, g_eq)
    r_w = rel_diff(a_w, g_w)
    bit_eq = bool(np.array_equal(a_eq, g_eq))
    bit_w = bool(np.array_equal(a_w, g_w))

    # ---- derived metrics, same code paths as the pin ----
    m = core.compute_metrics(eq_c / 10_000.0)
    peak = np.maximum.accumulate(a_eq)
    maxdd_worst = float(((peak - a_w) / np.maximum(peak, 1e-9)).max())
    final_eur = float(eq_c.iloc[-1])

    out = {
        "bars": int(len(eq_c)),
        "index_equal_vs_golden": index_equal,
        "bit_equal_equity": bit_eq,
        "bit_equal_worst": bit_w,
        "max_abs_dequity": float(d_eq.max()),
        "max_abs_dworst": float(d_w.max()),
        "max_rel_dequity": float(r_eq.max()),
        "max_rel_dworst": float(r_w.max()),
        "cagr": m["cagr"],
        "maxdd_worst": maxdd_worst,
        "final_eur": final_eur,
        "n_trades": st.n_trades,
        "final_balance": st.balance,
        "scalar_runtime_s": round(runtime, 1),
    }
    print(f"STAGE2 done in {runtime:.1f}s | bit_eq equity {bit_eq} worst "
          f"{bit_w} | max|deq| {d_eq.max():.3e} max|dw| {d_w.max():.3e}",
          flush=True)
    return out, eq_c, eq_w, warm_state_json


# --------------------------------------------------------------------- stage 3
def stage3_warm(pos, symbols, warm_state_json, eq_c_full, eq_w_full):
    st2 = B.make_stepper(symbols)
    st2.set_state(json.loads(warm_state_json))
    t0 = time.time()
    idx_parts, c_parts, w_parts = [], [], []
    for ch in B.iter_chunks(pos, WARM_RESUME_FROM, "2025Q4"):
        c, w = B.run_chunk_scalar(st2, ch)
        idx_parts.append(ch["gidx"])
        c_parts.append(np.asarray(c))
        w_parts.append(np.asarray(w))
        print(f"  stage3 {ch['qp']}: {len(c):>7,} bars | bal EUR "
              f"{st2.balance:,.2f}", flush=True)
    idx = idx_parts[0].append(idx_parts[1:])
    warm_c = np.concatenate(c_parts)
    warm_w = np.concatenate(w_parts)
    tail_c = eq_c_full.loc[idx[0]:].to_numpy()
    tail_w = eq_w_full.loc[idx[0]:].to_numpy()
    tail_idx = eq_c_full.loc[idx[0]:].index
    index_equal = bool(len(tail_idx) == len(idx)
                       and np.array_equal(tail_idx.values, idx.values))
    bit_c = bool(index_equal and np.array_equal(warm_c, tail_c))
    bit_w = bool(index_equal and np.array_equal(warm_w, tail_w))
    out = {
        "snapshot_after": WARM_SNAPSHOT_AFTER,
        "resume_from": WARM_RESUME_FROM,
        "tail_bars": int(len(warm_c)),
        "index_equal": index_equal,
        "bit_equal_equity": bit_c,
        "bit_equal_worst": bit_w,
        "max_abs_dequity": float(np.abs(warm_c - tail_c).max()) if index_equal else None,
        "max_abs_dworst": float(np.abs(warm_w - tail_w).max()) if index_equal else None,
        "resume_final_balance": st2.balance,
        "seconds": round(time.time() - t0, 1),
    }
    print(f"STAGE3: tail {len(warm_c):,} bars | bit_eq equity {bit_c} "
          f"worst {bit_w}", flush=True)
    return out


# ------------------------------------------------------------------------ main
def main() -> int:
    t_all = time.time()
    pin = json.loads(PIN_PATH.read_text())["pin"]
    pos = pd.read_parquet(GOLDEN / "book.parquet")
    gold = pd.read_parquet(GOLDEN / "curve.parquet")
    symbols = [c for c in pos.columns]

    contract = np.array([core.S.INSTRUMENTS[s]["contract_size"] for s in symbols], float)
    comm = np.array([core.S.INSTRUMENTS[s]["commission_side"] for s in symbols], float)
    lev = np.array([core.S.INSTRUMENTS[s]["leverage"] for s in symbols], float)
    lstep = np.array([core.S.INSTRUMENTS[s]["lot_step"] for s in symbols], float)
    mlot = np.array([core.S.INSTRUMENTS[s]["min_lot"] for s in symbols], float)
    stop_out = float(core.S.ACCOUNT["stop_out_level"])
    assert stop_out == 0.5, f"poisoned stop_out_level {stop_out!r}"

    report = {"generated": pd.Timestamp.now().isoformat(),
              "golden": str(GOLDEN / "curve.parquet"),
              "pin_source": str(PIN_PATH)}

    print("=== STAGE 1: subwindow 2020-01..2020-06 scalar vs numba ===",
          flush=True)
    s1 = stage1_subwindow(pos, symbols,
                          (contract, comm, lev, lstep, mlot, stop_out))
    report["stage1_subwindow"] = s1
    if not s1["pass"]:
        report["pass"] = False
        OUT_JSON.write_text(json.dumps(report, indent=1))
        print("ABORT: subwindow divergence — full run not attempted.")
        return 1

    print("=== STAGE 2: full 2020Q1..2025Q4 scalar run vs golden ===",
          flush=True)
    s2, eq_c, eq_w, warm_json = stage2_full(pos, symbols, gold)
    report["stage2_full"] = s2

    # metric comparison vs pin
    pin_cmp = {}
    for key, mine, ref in (("cagr", s2["cagr"], pin["cagr"]),
                           ("maxdd_worst", s2["maxdd_worst"], pin["maxdd"]),
                           ("final_eur", s2["final_eur"], pin["final_equity"])):
        sd = sig_digits_agree(mine, ref)
        pin_cmp[key] = {"stepper": mine, "pin": ref,
                        "bit_equal": mine == ref,
                        "sig_digits": ("inf" if sd == float("inf")
                                       else round(sd, 1))}
    pin_cmp["n_trades"] = {"stepper": s2["n_trades"],
                           "pin": pin["n_trades"],
                           "equal": s2["n_trades"] == pin["n_trades"]}
    report["metrics_vs_pin"] = pin_cmp

    print("=== STAGE 3: warm-start JSON roundtrip + tail replay ===",
          flush=True)
    if warm_json is None:
        report["stage3_warm"] = {"error": "no warm snapshot captured"}
        report["pass"] = False
    else:
        s3 = stage3_warm(pos, symbols, warm_json, eq_c, eq_w)
        report["stage3_warm"] = s3

    metrics_ok = all(v["bit_equal"] or (isinstance(v.get("sig_digits"), float)
                                        and v["sig_digits"] >= 10.0)
                     for k, v in pin_cmp.items() if k != "n_trades") \
        and pin_cmp["n_trades"]["equal"]
    ok = (s1["pass"]
          and s2["bit_equal_equity"] and s2["bit_equal_worst"]
          and s2["index_equal_vs_golden"]
          and metrics_ok
          and report["stage3_warm"].get("bit_equal_equity") is True
          and report["stage3_warm"].get("bit_equal_worst") is True)
    report["pass"] = bool(ok)
    report["total_runtime_s"] = round(time.time() - t_all, 1)
    OUT_JSON.write_text(json.dumps(report, indent=1))
    print(f"OVERALL PASS: {ok} | total {report['total_runtime_s']}s | "
          f"wrote {OUT_JSON}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
