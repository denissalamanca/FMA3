#!/usr/bin/env python3
"""Sweep the scale dial s WITH the broker volume-limit constraint, to find the
optimal deployable s. The volume cap flattens the return(s) curve at high s (the
big symbols cap out) while DD keeps rising -> return/DD peaks below the
unconstrained optimum. We map that here.

Engine: record_engine_ext.run_record_ext with the new `volume_limit` kwarg
(inert when None). First validates NO-cap reproduces the frozen record
(€3,872,872 / €1,332,404) so the engine edits are proven byte-safe.
"""
import sys, time, json
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, "/Users/dsalamanca/vs_env/FableMultiAssets3/engine")
sys.path.insert(0, "/Users/dsalamanca/vs_env/FableMultiAssets3/model/v3")

# Broker per-symbol SYMBOL_VOLUME_LIMIT (IC 11078280, from v3 Run 4 plateaus).
# Only the binding ones matter; 0/absent = no cap.
VOLCAP = {"XAUUSD": 10.0, "SOLUSD": 1000.0, "ETHUSD": 100.0, "US30": 12.0, "EURCAD": 10.0}


def _one(args):
    s, initial, stop, cap = args
    import record_engine_ext as REX
    from reproduce import static_blend
    fed = static_blend(0.70)
    r = REX.run_record_ext(fed * s, initial=initial, daily_stop_x=stop,
                           volume_limit=(VOLCAP if cap else None),
                           label=f"sweep_s{s}_{'cap' if cap else 'raw'}",
                           verbose=False, run_bootstrap=False)
    return dict(s=s, initial=initial, stop=stop, cap=cap,
                cagr=float(r["cagr"]), maxdd=float(r["maxdd_worst"]),
                eq=float(r["final_equity"]), sharpe=float(r.get("sharpe", 0.0)),
                stops=int(r.get("n_daily_stops") or 0))


def main():
    t0 = time.time()
    # ---- validation: NO-cap must reproduce the frozen record ----
    print("validating engine edits (no-cap reproduction)...", flush=True)
    val = _one((1.6, 10000.0, None, False))
    ok_ic = abs(val["eq"] - 3_872_872.05) < 5.0
    print(f"  IC s1.6 no-cap: €{val['eq']:,.0f}  (target 3,872,872)  {'OK' if ok_ic else 'MISMATCH — ABORT'}", flush=True)
    if not ok_ic:
        print("ENGINE EDIT BROKE THE REPRODUCTION — aborting sweep."); return 1

    # ---- the sweep (parallel) ----
    IC_S   = [0.8, 1.0, 1.2, 1.4, 1.6]         # IC €10k, no breaker
    FTMO_S = [0.4, 0.5, 0.6, 0.7, 0.8]         # FTMO €100k, breaker 3.0%
    jobs = ([(s, 10000.0, None, True) for s in IC_S]
            + [(s, 10000.0, None, False) for s in (1.0, 1.4, 1.6)]   # uncapped ref
            + [(s, 100000.0, 3.0, True) for s in FTMO_S])
    print(f"\nrunning {len(jobs)} engine passes (parallel)...", flush=True)
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(_one, jobs))

    ic_cap  = sorted([r for r in res if r["initial"] == 10000 and r["cap"]], key=lambda x: x["s"])
    ic_raw  = sorted([r for r in res if r["initial"] == 10000 and not r["cap"]], key=lambda x: x["s"])
    ftmo    = sorted([r for r in res if r["initial"] == 100000], key=lambda x: x["s"])

    def tbl(title, rows):
        print(f"\n=== {title} ===")
        print(f"{'s':>5}{'CAGR%':>9}{'MaxDD%':>9}{'ret/DD':>8}{'final_eq':>13}{'stops':>7}")
        for r in rows:
            rd = r["cagr"] / r["maxdd"] if r["maxdd"] > 0 else 0
            print(f"{r['s']:>5.1f}{r['cagr']*100:>9.1f}{r['maxdd']*100:>9.2f}{rd:>8.2f}{r['eq']:>13,.0f}{r['stops']:>7}")
    tbl("IC (€10k, VOLUME-CAPPED)", ic_cap)
    tbl("IC (€10k, uncapped ref)", ic_raw)
    tbl("FTMO (€100k, breaker 3.0%, VOLUME-CAPPED)", ftmo)

    # optimal s = max return/DD
    for name, rows in [("IC-capped", ic_cap), ("FTMO-capped", ftmo)]:
        best = max(rows, key=lambda r: (r["cagr"] / r["maxdd"] if r["maxdd"] > 0 else 0))
        print(f"\noptimal (max ret/DD) {name}: s={best['s']}  CAGR={best['cagr']*100:.1f}%  DD={best['maxdd']*100:.2f}%  ret/DD={best['cagr']/best['maxdd']:.2f}")

    json.dump(res, open("/Users/dsalamanca/vs_env/FableMultiAssets3/research/outputs/sweep_s_volcap.json", "w"), indent=1)
    print(f"\ntotal {time.time()-t0:.0f}s  -> research/outputs/sweep_s_volcap.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
