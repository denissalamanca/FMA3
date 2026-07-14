"""Full-book parity: run all 8 sleeve scalar steppers over the full hourly
grid, assemble the net book through the pointwise EnsembleStepper shell, and
diff against the frozen golden book.

Run from FMA2/research (pandas 2.3.3 / numpy 2.4.2):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/parity/validate_book.py

Checks:
  (A) constants provenance: ensemble_stepper V2_CAPS/SCALE/MAG_W AST-extracted
      from the frozen eval_v34_pin_s10.py must match; frozen ensemble.py must
      be byte-identical to FMA2 live (the sleeve validators already prove the
      per-sleeve sources).
  (B) each sleeve stepper's hourly matrix vs its golden parquet (per-sleeve
      maxabs — attribution table);
  (C) assembled book vs golden/book.parquet (49379 x 31): max|diff|, n cells
      != 0, n cells > 1e-12; if any nonzero, first divergent (hour, symbol)
      attributed to a sleeve;
  (D) GATE: assembled book through account_engine_1m (EUR 10k): CAGR /
      MaxDD_worst / Sharpe / finalEUR + deltas vs the pin.

Writes book_parity.json next to this file.
"""
import ast
import hashlib
import json
import sys
import time
from pathlib import Path

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
FREEZE = FMA3 / "model/v3/freeze/FMA3-v34-freeze-1"
GOLD = FREEZE / "golden"
STEPPERS = FMA3 / "research/bpure/steppers"
OUT_JSON = FMA3 / "research/bpure/parity/book_parity.json"

for p in (str(FMA2 / "research"), str(FMA2), str(STEPPERS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402

import core                                            # noqa: E402
import account_engine_1m as A1                         # noqa: E402

import ensemble_stepper as ES                          # noqa: E402
from mag_xau_stepper import MagXauStepper, SYM as MAG_SYM          # noqa: E402
from intraday_stepper import IntradayStepper, SYMBOLS as ID_SYMS   # noqa: E402
from meanrev_stepper import MeanrevStepper, SYMBOLS as MR_SYMS     # noqa: E402
from consolidate_p1c_stepper import (ConsolidateP1cStepper,        # noqa: E402
                                     CR_SYMBOLS, SYMBOLS as CP_SYMS)
from carry_breakout_stepper import (CarryBreakoutStepper,          # noqa: E402
                                    SYMBOLS as CB_SYMS, parse_policy_rates)
import crisis_stepper as cs                            # noqa: E402
from crisis_stepper import CrisisStepper, expand_to_hourly         # noqa: E402
from trend_v2_stepper import (TrendV2Stepper, SYMS as TV_SYMS,     # noqa: E402
                              EXEC_HOUR)

# pin (task constants, 10dp/4dp) + full-precision pin from the recorded run
PIN = {"cagr": 0.8865880763, "maxdd": 0.2167488591,
       "sharpe": 1.854317299, "final_eur": 449707.7453}
PIN_FULL_JSON = FMA2 / "research/outputs/v34_s10_pin_1m.json"

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:8.1f}s] {msg}", flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# (A) provenance: constants from the frozen spec, not from memory
# --------------------------------------------------------------------------
def check_constants() -> dict:
    tree = ast.parse((FREEZE / "src/research/eval_v34_pin_s10.py").read_text())
    frozen = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("V2_CAPS", "SCALE", "MAG_W"):
                frozen[name] = ast.literal_eval(node.value)
    assert frozen["V2_CAPS"] == ES.V2_CAPS, "V2_CAPS drifted from frozen spec"
    assert frozen["SCALE"] == ES.SCALE and frozen["MAG_W"] == ES.MAG_W
    # gold cap must be DERIVED and equal the frozen rule
    gcap = ES.structural_gold_cap()
    assert gcap == frozen["V2_CAPS"]["seasonal"] * frozen["SCALE"]
    h_frozen = sha(FREEZE / "src/research/ensemble.py")
    h_live = sha(FMA2 / "research/ensemble.py")
    return {"V2_CAPS": frozen["V2_CAPS"], "SCALE": frozen["SCALE"],
            "MAG_W": frozen["MAG_W"], "gold_cap_derived": gcap,
            "ensemble_py_sha256_frozen": h_frozen,
            "ensemble_py_frozen_eq_live": h_frozen == h_live}


# --------------------------------------------------------------------------
# sleeve drivers — each returns {sym: np.ndarray(n_hours)} (hourly positions)
# exactly as the per-sleeve validators drove them (all 7 confirmed vs golden)
# --------------------------------------------------------------------------
def run_mag(U, grid, ts_ns):
    vals = core.load_hourly(MAG_SYM)["c"].reindex(grid).to_numpy(float)
    stp = MagXauStepper()
    n = len(grid)
    out = np.empty(n)
    for i in range(n):
        out[i] = stp.step(int(ts_ns[i]), {MAG_SYM: float(vals[i])})[MAG_SYM]
    return {MAG_SYM: out}


def run_intraday(U, grid, ts_ns):
    raw = {s: U["close"][s].where(U["has_bar"][s]).to_numpy() for s in ID_SYMS}
    stp = IntradayStepper()
    n = len(grid)
    out = {s: np.empty(n) for s in ID_SYMS}
    for i in range(n):
        p = stp.step(int(ts_ns[i]), {s: float(raw[s][i]) for s in ID_SYMS})
        for s in ID_SYMS:
            out[s][i] = p[s]
    return out


def run_meanrev(U, grid, ts_ns):
    syms = list(MR_SYMS)
    arr = U["close"][syms].where(U["has_bar"][syms]).to_numpy(np.float64)
    ts_list = grid.to_pydatetime()
    stp = MeanrevStepper()
    n, m = arr.shape
    out = {s: np.empty(n) for s in syms}
    for i in range(n):
        row = arr[i]
        p = stp.step(ts_list[i], {syms[j]: row[j] for j in range(m)})
        for s in syms:
            out[s][i] = p[s]
    stp.finalize()
    return out


def run_consolidate(U, grid, ts_ns):
    """seasonal (XAUUSD) + crypto_smart (BTC/ETH/SOL) — one-bar-deferred."""
    xau_ret = U["ret"]["XAUUSD"].to_numpy()
    closes = {s: U["close"][s].to_numpy() for s in CR_SYMBOLS}
    stp = ConsolidateP1cStepper()
    n = len(grid)
    out = {s: np.empty(n) for s in CP_SYMS}
    i_emit = 0
    for i in range(n):
        o = stp.step(int(ts_ns[i]), float(xau_ret[i]),
                     float(closes["BTCUSD"][i]), float(closes["ETHUSD"][i]),
                     float(closes["SOLUSD"][i]))
        if o is not None:
            t, row = o
            assert t == int(ts_ns[i_emit]), "consolidate emission misaligned"
            for s in CP_SYMS:
                out[s][i_emit] = row[s]
            i_emit += 1
    t, row = stp.finalize()
    assert t == int(ts_ns[i_emit])
    for s in CP_SYMS:
        out[s][i_emit] = row[s]
    i_emit += 1
    assert i_emit == n, f"consolidate emitted {i_emit}/{n} rows"
    return out


def run_carry(U, grid, ts_ns):
    syms = list(CB_SYMS)
    rows = U["close"][syms].where(U["has_bar"][syms]).to_numpy().tolist()
    epoch_days = (grid.asi8 // (86400 * 10**9)).tolist()
    stp = CarryBreakoutStepper(parse_policy_rates(core.engine_costs.POLICY_RATES))
    n = len(grid)
    out = {s: np.empty(n) for s in syms}
    for i in range(n):
        p = stp.step(epoch_days[i], rows[i])
        for j, s in enumerate(syms):
            out[s][i] = p[j]
        if i % 10000 == 0:
            log(f"  carry_breakout bar {i}/{n}")
    return out


def run_crisis(U, grid, ts_ns):
    dcA = core.daily_closes(core.ALL)
    dcA = dcA[dcA.index.dayofweek < 5]        # trading weekdays only
    closes_mat = dcA[cs.INPUT_SYMS].to_numpy()
    day_ns = dcA.index.view("int64")
    stp = CrisisStepper()
    rows_w, rows_eff = [], []
    for i in range(len(dcA)):
        o = stp.step(int(day_ns[i]), [float(x) for x in closes_mat[i]])
        rows_w.append([o["w"][s] for s in cs.SYMS])
        rows_eff.append(o["effective_ns"])
    hourly_ns = [int(t) for t in ts_ns]
    return {s: np.asarray(expand_to_hourly(rows_eff,
                                           [r[k] for r in rows_w], hourly_ns))
            for k, s in enumerate(cs.SYMS)}


def run_trend_v2(U, grid, ts_ns):
    syms = list(TV_SYMS)
    dc = core.daily_closes(syms)
    dc_np = dc.to_numpy()
    stp = TrendV2Stepper()
    n_days = len(dc.index)
    held = np.empty((n_days, len(syms)))
    for t in range(n_days):
        held[t] = stp.step(dc_np[t])
    # daily stamp d 00:00 -> effective d+1 05:00 UTC (lag_hours = EXEC_HOUR+1)
    eff = (dc.index + pd.Timedelta(days=1)
           + pd.Timedelta(hours=EXEC_HOUR + 1 - 1)).asi8
    j = np.searchsorted(eff, grid.asi8, side="right") - 1
    pos = np.zeros((len(grid), len(syms)))
    valid = j >= 0
    pos[valid] = held[j[valid]]
    return {s: pos[:, k] for k, s in enumerate(syms)}


# --------------------------------------------------------------------------
def main():
    prov = check_constants()
    log(f"constants OK: {prov['V2_CAPS']} SCALE={prov['SCALE']} "
        f"MAG_W={prov['MAG_W']} gold_cap={prov['gold_cap_derived']!r} "
        f"frozen==live ensemble.py: {prov['ensemble_py_frozen_eq_live']}")

    U = core.universe_frames(tuple(core.ALL))
    grid = U["ret"].index
    ts_ns = grid.asi8
    n = len(grid)
    log(f"grid: {n} hours [{grid[0]} .. {grid[-1]}]")

    # ---- run the 8 sleeves (7 stepper modules) ----------------------------
    sleeve_out = {}
    runs = [("mag", run_mag), ("intraday", run_intraday),
            ("meanrev", run_meanrev), ("consolidate", run_consolidate),
            ("crisis", run_crisis), ("trend_v2", run_trend_v2),
            ("carry_breakout", run_carry)]
    for name, fn in runs:
        t1 = time.time()
        sleeve_out[name] = fn(U, grid, ts_ns)
        log(f"sleeve {name} done in {time.time() - t1:.1f}s")

    # split consolidate into the two book sleeves
    cons = sleeve_out.pop("consolidate")
    sleeve_out["seasonal"] = {"XAUUSD": cons["XAUUSD"]}
    sleeve_out["crypto_smart"] = {s: cons[s] for s in CR_SYMBOLS}

    # ---- (B) per-sleeve attribution vs golden parquets --------------------
    golden_files = {"meanrev": "meanrev_pos.parquet",
                    "carry_breakout": "carry_breakout_pos.parquet",
                    "seasonal": "seasonal_pos.parquet",
                    "intraday": "intraday_pos.parquet",
                    "crisis": "crisis_pos.parquet",
                    "trend_v2": "trend_v2_pos.parquet",
                    "crypto_smart": "crypto_smart_pos.parquet",
                    "mag": "mag_pos.parquet"}
    sleeve_maxabs, sleeve_cols, g_sleeve = {}, {}, {}
    for name, f in golden_files.items():
        g = pd.read_parquet(GOLD / f)
        assert g.index.equals(grid), f"{name}: golden index != grid"
        g_sleeve[name] = g
        sleeve_cols[name] = list(g.columns)
        mx = 0.0
        for s in g.columns:
            mx = max(mx, float(np.max(np.abs(sleeve_out[name][s]
                                             - g[s].to_numpy()))))
        sleeve_maxabs[name] = mx
    log("per-sleeve maxabs vs golden: "
        + json.dumps({k: f"{v:.3e}" for k, v in sleeve_maxabs.items()}))

    # carry stepper emits 32 symbols; the frozen sleeve parquet kept 21 —
    # the 11 dropped columns must be identically zero in the stepper output
    carry_extra = [s for s in CB_SYMS if s not in sleeve_cols["carry_breakout"]]
    extra_nonzero = {s: int(np.count_nonzero(sleeve_out["carry_breakout"][s]))
                     for s in carry_extra}
    assert all(v == 0 for v in extra_nonzero.values()), \
        f"carry dropped columns not all-zero: {extra_nonzero}"
    log(f"carry dropped columns all-zero OK ({len(carry_extra)} cols)")

    # ---- assemble the book through the pointwise shell ---------------------
    shell = ES.EnsembleStepper(sleeve_cols)
    book_syms = list(shell.symbols)
    golden_book = pd.read_parquet(GOLD / "book.parquet")
    assert golden_book.index.equals(grid), "golden book index != grid"
    assert list(golden_book.columns) == book_syms, (
        f"book column mismatch: shell {book_syms} vs golden "
        f"{list(golden_book.columns)}")

    t1 = time.time()
    book = np.empty((n, len(book_syms)))
    col_ix = {s: k for k, s in enumerate(book_syms)}
    sleeve_names = list(sleeve_cols)
    for i in range(n):
        rows = {nm: {s: sleeve_out[nm][s][i] for s in sleeve_cols[nm]}
                for nm in sleeve_names}
        net = shell.step(int(ts_ns[i]), rows)
        for s, v in net.items():
            book[i, col_ix[s]] = v
    log(f"ensemble shell assembled in {time.time() - t1:.1f}s")

    # ---- (C) book diff ------------------------------------------------------
    g_np = golden_book.to_numpy()
    diff = np.abs(book - g_np)
    maxabs = float(diff.max())
    n_nonzero = int(np.count_nonzero(diff))
    n_gt_1e12 = int((diff > 1e-12).sum())
    cells_total = int(diff.size)
    first_div = None
    if n_nonzero:
        ii, jj = np.argwhere(diff > 0)[0]
        sym = book_syms[jj]
        contribs = {nm: {"mine": float(sleeve_out[nm][sym][ii]),
                         "golden": float(g_sleeve[nm][sym].iloc[ii])}
                    for nm in sleeve_names if sym in sleeve_cols[nm]}
        blame = [nm for nm, d in contribs.items()
                 if d["mine"] != d["golden"]]
        first_div = {"hour": str(grid[ii]), "symbol": sym,
                     "mine": float(book[ii, jj]), "golden": float(g_np[ii, jj]),
                     "sleeve_contribs": contribs, "attributed_sleeves": blame}
        log(f"FIRST DIVERGENT CELL: {first_div}")
    log(f"BOOK max|diff| {maxabs:.3e} | nonzero cells {n_nonzero}/{cells_total}"
        f" | cells >1e-12: {n_gt_1e12}")

    # ---- (D) gate: account_engine_1m on the assembled book -----------------
    book_df = pd.DataFrame(book, index=grid, columns=book_syms)
    log("running account_engine_1m (EUR 10k) on assembled book ...")
    eqc, eqw, m = A1.simulate_account_1m(book_df, initial=10_000.0,
                                         verbose=True)
    pin_full = None
    if PIN_FULL_JSON.exists():
        pin_full = json.load(open(PIN_FULL_JSON))["pin"]
    gate = {
        "cagr": float(m["cagr"]), "maxdd_worst": float(m["maxdd"]),
        "sharpe": float(m["sharpe"]), "final_eur": float(m["final_equity"]),
        "n_neg_years": int(m["n_neg_years"]),
        "n_neg_quarters": int(m["n_neg_quarters"]),
        "delta_vs_pin_quoted": {
            "dCAGR": float(m["cagr"]) - PIN["cagr"],
            "dMaxDD_worst": float(m["maxdd"]) - PIN["maxdd"],
            "dSharpe": float(m["sharpe"]) - PIN["sharpe"],
            "dFinalEUR": float(m["final_equity"]) - PIN["final_eur"],
        },
    }
    if pin_full:
        gate["delta_vs_pin_fullprec"] = {
            "dCAGR": float(m["cagr"]) - pin_full["cagr"],
            "dMaxDD_worst": float(m["maxdd"]) - pin_full["maxdd"],
            "dSharpe": float(m["sharpe"]) - pin_full["sharpe"],
            "dFinalEUR": float(m["final_equity"]) - pin_full["final"] * 10_000.0,
        }
    log("GATE " + json.dumps(gate, indent=1))

    dq = gate["delta_vs_pin_quoted"]
    gate_pass_quoted = all(abs(v) <= 1e-9 for v in
                           (dq["dCAGR"], dq["dMaxDD_worst"], dq["dFinalEUR"]))
    gate_pass_full = None
    if pin_full:
        df_ = gate["delta_vs_pin_fullprec"]
        gate_pass_full = all(abs(v) <= 1e-9 for v in
                             (df_["dCAGR"], df_["dMaxDD_worst"],
                              df_["dFinalEUR"]))
    book_pass = maxabs <= 1e-12
    # overall gate comparison: the full-precision pin from the recorded run
    # (outputs/v34_s10_pin_1m.json) when available — the task constants are
    # quoted at 10dp/4dp, so a 1e-9 tolerance on finalEUR is below the quoting
    # precision of the 4dp constant (449707.7453 vs actual 449707.7452664526).
    # Both comparisons are recorded; nothing is relaxed — the engine output is
    # bit-identical to the pin run (dCAGR/dMaxDD/dSharpe exactly 0.0).
    overall = bool(book_pass and (gate_pass_full if gate_pass_full is not None
                                  else gate_pass_quoted))

    result = {
        "check": "full_book_parity",
        "provenance": prov,
        "grid": {"n_hours": n, "n_symbols": len(book_syms),
                 "start": str(grid[0]), "end": str(grid[-1])},
        "sleeve_maxabs_vs_golden": sleeve_maxabs,
        "carry_dropped_cols_all_zero": True,
        "book_maxabs_vs_golden": maxabs,
        "cells_total": cells_total,
        "cells_nonzero": n_nonzero,
        "cells_gt_1e-12": n_gt_1e12,
        "first_divergent": first_div,
        "gate": gate,
        "pin_quoted": PIN,
        "pass_book_le_1e-12": book_pass,
        "pass_gate_deltas_le_1e-9_vs_quoted_pin": gate_pass_quoted,
        "pass_gate_deltas_le_1e-9_vs_fullprec_pin": gate_pass_full,
        "pass": overall,
        "runtime_sec": round(time.time() - T0, 1),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    log(f"wrote {OUT_JSON}")
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
