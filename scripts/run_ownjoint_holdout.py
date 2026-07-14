#!/usr/bin/env python3
"""OWN-vs-JOINT A/B — 2026 HOLDOUT replay (out-of-sample).

Replays F_own_fwd and F_joint_fwd (v7-only, USA500 proxy) through the ext
record engine over 2026Q1..2026Q2 with the Duka forward 1m cache. Reuses the
forward one-shot helpers (fwd_bar_files/restrict) + the UTC->server rule.
Process imports record_engine_ext only (stop_out=0.50); never v7_bridge.

NOTE: this is a SECONDARY read of 2026 for the sizing-basis question; the
primary one-shot blend holdout was already consumed. Reported OOS, short
window (~4 months), wide error bars.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))
sys.path.insert(0, str(_FMA3 / "scripts"))
import record_engine_ext as RX  # noqa: E402
import run_forward_oneshot as OS  # noqa: E402
import core                      # noqa: E402

FWD = RX.PATHS.OUTPUTS / "fwd"
Q = ("2026Q1", "2026Q2")
TRUNC = pd.Timestamp("2026-04-30 23:59:59")


def to_server(obj):
    out = obj.copy()
    out.index = (out.index.tz_localize("UTC").tz_convert("America/New_York")
                 + pd.Timedelta(hours=7)).tz_localize(None)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def peak_load(frac, s, lev, lo, hi):
    m = (frac.index >= lo) & (frac.index <= hi)
    return float((frac.loc[m].abs() * s).div(lev).sum(axis=1).max())


def main():
    tradable = OS.fwd_tradable_symbols("drop")
    bar_files = OS.fwd_bar_files(tradable, "drop")
    f_own = to_server(pd.read_parquet(FWD / "v7_book_frac_1h_fwd_ab.parquet"))
    f_joint = to_server(pd.read_parquet(FWD / "v7_book_tgt_1h_fwd.parquet"))
    f_own = f_own.loc[f_own.index >= "2025-12-01"]
    f_joint = f_joint.loc[f_joint.index >= "2025-12-01"]
    f_own, d7 = OS.restrict_to_forward(f_own, tradable)
    f_joint, dj = OS.restrict_to_forward(f_joint, tradable)
    cols = sorted(set(f_own.columns) | set(f_joint.columns))
    f_own = f_own.reindex(columns=cols, fill_value=0.0)
    f_joint = f_joint.reindex(columns=cols, fill_value=0.0)
    lev = pd.Series({c: float(core.S.INSTRUMENTS[c]["leverage"]) for c in cols})
    lo26, hi26 = pd.Timestamp("2026-01-01"), TRUNC

    res = {"kept_cols": cols, "arms": {}}
    for s in (1.0, 1.6):
        for name, frac in (("own", f_own), ("joint", f_joint)):
            r = RX.run_record_ext(frac * s, start_quarter=Q[0], end_quarter=Q[1],
                                  bar_files=bar_files, initial=10_000.0,
                                  label=f"holdout_{name}_s{int(s*100)}",
                                  verbose=False, run_bootstrap=False)
            ec, ew = r["curves"]["equity"], r["curves"]["worst"]
            k = (ec.index <= TRUNC)
            ec, ew = ec[k], ew[k]
            peak = ec.cummax()
            ddw = float(((peak - ew) / peak).max())
            ret = float(ec.iloc[-1] / 10_000.0 - 1.0)
            row = {"s": s, "total_return": ret, "final_equity": float(ec.iloc[-1]),
                   "maxdd_worst": ddw,
                   "cagr_annualized": r["cagr"], "sharpe": r["sharpe"],
                   "peak_margin_load": peak_load(frac, s, lev, lo26, hi26),
                   "first_bar": str(ec.index[0]), "last_bar": str(ec.index[-1])}
            res["arms"][f"{name}_s{int(s*100)}"] = row
            print(f"[{name} s{s}] ret {ret:+.4f} DDw {ddw:.4f} "
                  f"Sh {r['sharpe']:.3f} load {row['peak_margin_load']:.3f} "
                  f"CAGRann {r['cagr']:+.3f}", flush=True)
    (RX.PATHS.OUTPUTS / "ownjoint_holdout_results.json").write_text(
        json.dumps(res, indent=1, default=str))
    print("DONE -> ownjoint_holdout_results.json", flush=True)


if __name__ == "__main__":
    main()
