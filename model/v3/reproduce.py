#!/usr/bin/env python3
"""STABLE MODEL OF RECORD v3 — golden reproduction (IC + FTMO).

This is the SINGLE source of truth for the blended model behind
archive/docs-v1.0/DASHBOARD_IC.html and DASHBOARD_FTMO.html. It is self-contained: it
inlines the blend (so it does NOT depend on the scattered
scripts/run_hrisk1.py, run_hfed3.py, run_fma3_008.py, ownjoint_* artifacts) and
depends only on the pinned engine + the four FROZEN input artifacts.

Run:  python3 model/v3/reproduce.py           # ~8-9 min (two full 1m record-engine passes)
      python3 model/v3/reproduce.py --ic      # IC only  (~4 min)
      python3 model/v3/reproduce.py --ftmo    # FTMO only (~4 min)

PASS = both headline equities reproduce to the euro (asserts below).

DO NOT confuse this model with:
  - hrisk1_results.json 'v7-alone'  -> WRONG, hrisk1 IS blended (blends f_core+f_sat).
  - v7_book_frac_1h_ab.parquet      -> the OWNJOINT v7-ONLY probe artifact, NOT this model's input.
  - the s=1.1 'global_scale' in strategy_fma3.py -> the config base point, NOT the shipped dial.
This model = static_blend(w=0.70) * s, s per preset (IC 1.6, FTMO 0.7). See MODEL_SPEC.md.
"""
from __future__ import annotations
import sys, time, argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "engine"))
import pandas as pd
import record_engine as RE
import record_engine_ext as REX
import books

# ---- FROZEN, account-independent model inputs (pin these hashes in PINNED_INPUTS.md) ----
CORE_FRAC = REPO / "research/outputs/v7_book_frac_1h.parquet"          # v7 band-book hourly frac-of-own-equity (8 legs)
CORE_EQ   = REPO / "research/outputs/v7_book_equity_1m.parquet"        # v7 native standalone 1m equity ("eqc")
SAT_EQ  = REPO / "research/baselines/fma2/v34_s10_pin_curve.parquet" # v34 native standalone 1m equity ("equity")
# sat_frac = books.build_sat_frac_1h()  (31 cols, GLOBAL_SCALE=10, gold cap 1.80 pre-applied)

CORE_WEIGHT = 0.70                 # v7 capital share (hashed in config 51a7541cc2aaa593)
CONFIG_HASH = "51a7541cc2aaa593"

# ---- GOLDEN TARGETS (must reproduce exactly) ----
IC_TARGET   = dict(final_equity=3_872_872.0469247998, cagr=1.7016824131883754,
                   maxdd_worst=0.22583669122811498, sharpe=2.465000338806643)
FTMO_TARGET = dict(final_equity=1_332_404.1921628967, cagr=0.5401666489,
                   maxdd_worst=0.1332678510, n_daily_stops=26)


def load_inputs():
    """Native frac matrices + native equity curves normalized to 1.0 at t0.
    Byte-identical to scripts/run_hfed1_lib.load_inputs — inlined so this file
    is the pinned, self-contained definition."""
    core_frac = pd.read_parquet(CORE_FRAC)
    sat_frac = books.build_sat_frac_1h()
    core_eq = pd.read_parquet(CORE_EQ)["eqc"]
    sat_eq = pd.read_parquet(SAT_EQ)["equity"]
    return core_frac, sat_frac, core_eq / core_eq.iloc[0], sat_eq / sat_eq.iloc[0]


def static_blend(w: float) -> pd.DataFrame:
    """The blend: fed[h,k] = f_core*(w*a_h/j) + f_sat*((1-w)*b_h/j),
    j = w*a_h + (1-w)*b_h, where a_h,b_h are the FROZEN native standalone equity
    multiples (=1.0 at t0). Shared symbols are SUMMED into one net column.
    Byte-identical to scripts/run_hrisk1.py::static_blend (verified -> €3,872,872)."""
    core_frac, sat_frac, a, b = load_inputs()
    hours = core_frac.index.union(sat_frac.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    j = w * a_h + (1 - w) * b_h
    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat = sat_frac.reindex(hours).fillna(0.0)
    cols = sorted(set(f_core.columns) | set(f_sat.columns))
    return (f_core.reindex(columns=cols, fill_value=0.0).mul(w * a_h / j, axis=0)
            + f_sat.reindex(columns=cols, fill_value=0.0).mul((1 - w) * b_h / j, axis=0))


def _check(name, got, target, keys, rtol=1e-6):
    ok = True
    print(f"\n=== {name} ===")
    for k in keys:
        g = got[k]; t = target[k]
        if isinstance(t, int):
            good = (int(g) == t); rel = 0.0
        else:
            rel = abs(g - t) / abs(t) if t else abs(g)
            good = rel <= rtol
        ok &= good
        print(f"  {k:14} = {g:>20,.6f}   target {t:>20,.6f}   {'OK' if good else 'MISMATCH'} (rel {rel:.2e})")
    return ok


def run_ic(fed):
    t0 = time.time()
    r = RE.run_record(fed * 1.6, label="v3_IC_s160", verbose=False)   # IC dial s=1.6, initial 10k (engine default)
    print(f"[IC done in {time.time()-t0:.0f}s]")
    return r


def run_ftmo(fed):
    t0 = time.time()
    r = REX.run_record_ext(fed * 0.7, initial=100_000.0, daily_stop_x=3.0,
                           label="v3_FTMO_s70_x30", verbose=False, run_bootstrap=False)  # s=0.7 + breaker 3.0%
    print(f"[FTMO done in {time.time()-t0:.0f}s]")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ic", action="store_true"); ap.add_argument("--ftmo", action="store_true")
    a = ap.parse_args()
    both = not (a.ic or a.ftmo)
    hc = __import__("subprocess").run([sys.executable, str(REPO / "strategy_fma3.py")],
                                      capture_output=True, text=True).stdout
    assert CONFIG_HASH in hc, f"config hash drift! expected {CONFIG_HASH}, strategy_fma3.py said: {hc.strip()}"
    print(f"config_hash {CONFIG_HASH} OK")
    fed = static_blend(CORE_WEIGHT)
    print(f"fed_frac built: {fed.shape[0]} hours x {fed.shape[1]} symbols (8 v7 + 31 v34, 6 shared)")
    ok = True
    if both or a.ic:   ok &= _check("IC (s=1.6, initial €10k, compounding)", run_ic(fed), IC_TARGET,
                                    ["final_equity", "cagr", "maxdd_worst", "sharpe"])
    if both or a.ftmo: ok &= _check("FTMO (s=0.7, initial €100k, breaker x=3.0%)", run_ftmo(fed), FTMO_TARGET,
                                    ["final_equity", "cagr", "maxdd_worst", "n_daily_stops"])
    print(f"\n{'='*60}\nSTABLE MODEL v3 REPRODUCTION: {'PASS' if ok else 'FAIL'}\n{'='*60}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
