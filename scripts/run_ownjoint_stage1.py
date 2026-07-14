#!/usr/bin/env python3
"""OWN-vs-JOINT A/B — STAGE 1: generate F_own (regenerated) + F_joint matrices.

Single anchor pass (imports engine/v7_bridge -> lock_v5 stop_out=1e-9). NEVER
co-import record_engine here. Route A of the design: from ONE capturing anchor
pass build BOTH frac matrices sharing the same tgt signals / eq_joint / COVID
path, so the warmup cascade cancels in the OWN-vs-JOINT difference.

  F_own[inst,h]   = sum_legs lots_leg*contract*mid*eurq / eq_joint      (existing
                    v7_book_frac_1h convention: standalone-equity leverage,
                    each leg carries only its own accumulated sub-account).
  F_joint[inst,h] = sum_legs lots_leg*contract*mid*eurq * W_leg / eqc_leg
                    (constant blended leverage: each leg sized off its share
                    W_leg of JOINT equity, eq_joint cancels).

The only structural difference is the equity DENOMINATOR per leg (standalone
eqc_leg vs its constant share W_leg of joint equity). Ratio
R = F_joint/F_own = W_leg*eq_joint/eqc_leg = the under-carry factor
(=1 right after a reseed; >1 when a leg's standalone equity lags its joint
share, e.g. JPY carry after other sleeves compounded).

The F_joint tgt_leg is recovered from HELD lots (lots_leg/eqc_leg = the
realized notional-fraction the leg actually carried), which is more faithful
than the raw input target: it inherits the anchor's band/round/SL/blocked
execution. Both matrices are then replayed through the SAME record engine in
Stage 2, so the record engine's band/round/stop-out/margin-cap hit both arms
identically and the sizing basis is the sole contrast.

Additive to the frozen extractor: subclasses PositionAccumulator, reuses
EP.run_generic_capture / book / anchor gate verbatim. extract_positions.py is
READ-ONLY (imported, never edited); F_own is regenerated and gated == the
existing artifact to prove the capture did not perturb generation.

Feeds:
  ic       -> research/outputs/v7_book_{frac_1h,tgt_1h}_ab.parquet (default)
  duka2026 -> research/outputs/fwd/v7_book_tgt_1h_fwd.parquet (holdout JOINT;
              F_own_fwd already exists as v7_book_frac_1h_fwd.parquet)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
_FMA3 = _HERE.parents[1]
sys.path.insert(0, str(_FMA3 / "engine" / "v7_bridge"))

import extract_positions as EP  # noqa: E402  (lock_v5 side-effect: stop_out=1e-9)
import engine.backtest as bt    # noqa: E402
from config import settings as S  # noqa: E402
from sim import HI, LO, W7, book, pack  # noqa: E402

assert S.ACCOUNT["stop_out_level"] == 1e-9, "lock_v5 stop_out side-effect missing"


class OwnJointAccumulator(EP.PositionAccumulator):
    """PositionAccumulator + per-leg JOINT-frac numerator G[inst] =
    sum_legs lots_leg * W_leg / eqc_leg (contract*mid*eurq applied later,
    per instrument, exactly as F_own's val_1m)."""

    def __init__(self, nlegs: dict[str, int], n_sleeves: int) -> None:
        super().__init__()
        self._nlegs = nlegs
        self._n_sleeves = n_sleeves
        self.gsum: dict[str, list[pd.Series]] = {}

    def __call__(self, t0, t1, tc_seg, legs_cap, flat) -> None:
        super().__call__(t0, t1, tc_seg, legs_cap, flat)   # verify + net lots
        per_inst_g: dict[str, pd.Series] = {}
        for lc in legs_cap:
            m = lc["pos"].index < t1
            pos = lc["pos"][m]
            eqc = lc["eqc"][m]
            if len(pos) == 0:
                continue
            w_leg = (1.0 / self._n_sleeves) / self._nlegs[lc["sleeve"]]
            e = eqc.to_numpy()
            g = np.where(e > 0.0, pos.to_numpy() * w_leg / np.maximum(e, 1e-12), 0.0)
            gs = pd.Series(g, index=pos.index)
            inst = lc["inst"]
            per_inst_g[inst] = (gs if inst not in per_inst_g
                                else per_inst_g[inst].add(gs, fill_value=0.0))
        for inst, s in per_inst_g.items():
            self.gsum.setdefault(inst, []).append(s)

    def g_matrix(self, union_idx: pd.DatetimeIndex) -> pd.DataFrame:
        cols = {}
        for inst in sorted(self.gsum):
            s = pd.concat(self.gsum[inst])
            assert s.index.is_monotonic_increasing and s.index.is_unique, inst
            cols[inst] = s.reindex(union_idx).ffill().fillna(0.0)
        return pd.DataFrame(cols, index=union_idx)


def run(feed: str, us5: str, lo, hi, anchor_gate: bool, out_dir: Path,
        own_name: str, joint_name: str, blind_from=None) -> dict:
    t_start = time.time()
    print(f"[stage1] prime {feed!r} + book('BTC_REP',{us5!r})", flush=True)
    EP.prime(feed)
    sleeves = book("BTC_REP", us5)
    nlegs = {name: len(legs) for name, legs in sleeves.items()}
    n_sleeves = len(sleeves)
    print(f"      sleeves ({n_sleeves}): "
          f"{[(k, nlegs[k]) for k in sleeves]}", flush=True)

    acc = OwnJointAccumulator(nlegs, n_sleeves)
    print("[stage1] band-book run + OWN/JOINT capture", flush=True)
    out, triggers = EP.run_generic_capture(
        sleeves, [lo, hi], up=0.25, down=W7 / 1.75, kmult=2.5,
        label="ownjoint", verbose=False, sink=acc, print_before=blind_from)

    exact = None
    if anchor_gate:
        reference = json.loads(
            EP.REFERENCE_JSON.read_text())["results"][EP.REFERENCE_KEY]
        m = pack(out, triggers)
        rf, ref = EP._flatten(m), EP._flatten(reference)
        exact = all(rf.get(k) == v for k, v in ref.items())
        print(f"[stage1] anchor gate exact={exact}", flush=True)

    # internal-consistency rebuild gate (positions -> book equity)
    book_rebuilt = pd.concat(acc.rebuilt)
    assert book_rebuilt.index.equals(out["eqc"].index)
    relerr = float(((book_rebuilt - out["eqc"]).abs() / out["eqc"].abs()).max())
    print(f"[stage1] consistency relerr {relerr:.3e} | leg {acc.max_leg_relerr:.3e}"
          f" | segments {acc.n_segments}", flush=True)

    idx = out["eqc"].index
    lots_df = acc.lots_matrix(idx)          # net lots (F_own numerator)
    g_df = acc.g_matrix(idx)                # JOINT numerator (per-leg W/eqc)

    eq_h = out["eqc"].resample("1h").last().dropna()
    own_val = pd.DataFrame(index=idx)
    joint_val = pd.DataFrame(index=idx)
    cols = sorted(set(lots_df.columns) | set(g_df.columns))
    for inst in cols:
        bars = bt.load_bars(inst)
        mid = ((bars["bid_c"] + bars["ask_c"]) * 0.5).reindex(idx).ffill()
        e = acc._eurq_series(inst).reindex(idx).ffill()
        c_size = float(S.INSTRUMENTS[inst]["contract_size"])
        if inst in lots_df.columns:
            own_val[inst] = lots_df[inst] * c_size * mid * e
        if inst in g_df.columns:
            joint_val[inst] = g_df[inst] * c_size * mid * e

    frac_own = (own_val.resample("1h").last().reindex(eq_h.index)
                .div(eq_h, axis=0).fillna(0.0))
    frac_joint = (joint_val.resample("1h").last().reindex(eq_h.index)
                  .fillna(0.0))            # eq_joint already cancelled in G

    out_dir.mkdir(parents=True, exist_ok=True)
    p_own = out_dir / own_name
    p_joint = out_dir / joint_name
    frac_own.to_parquet(p_own)
    frac_joint.to_parquet(p_joint)
    print(f"[stage1] wrote {p_own}\n[stage1] wrote {p_joint}", flush=True)

    # cross-check regenerated F_own vs existing artifact (IC only)
    own_check = None
    if feed == "ic":
        existing = pd.read_parquet(EP.OUT_DIR / "v7_book_frac_1h.parquet")
        common = [c for c in existing.columns if c in frac_own.columns]
        al = frac_own[common].reindex(existing.index)
        d = float((al[common] - existing[common]).abs().to_numpy().max())
        own_check = d
        print(f"[stage1] F_own regen vs existing max|delta| {d:.3e}", flush=True)

    rep = dict(feed=feed, us5=us5, window=[str(lo), str(hi)],
               anchor_exact=exact, consistency_relerr=relerr,
               n_segments=acc.n_segments, own_artifact=str(p_own),
               joint_artifact=str(p_joint), own_regen_vs_existing=own_check,
               nlegs=nlegs, runtime_min=(time.time() - t_start) / 60.0)
    (out_dir / f"ownjoint_stage1_{feed}.json").write_text(
        json.dumps(rep, indent=1, default=str))
    print(f"[stage1] DONE {feed} ({rep['runtime_min']:.1f} min)", flush=True)
    return rep


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ic"
    if mode == "ic":
        run("ic", "USTEC", LO, HI, anchor_gate=True, out_dir=EP.OUT_DIR,
            own_name="v7_book_frac_1h_ab.parquet",
            joint_name="v7_book_tgt_1h_ab.parquet")
    elif mode == "fwd":
        run("duka2026", "USA500", pd.Timestamp("2020-01-01"),
            pd.Timestamp("2026-05-01"), anchor_gate=False,
            out_dir=EP.OUT_DIR / "fwd",
            own_name="v7_book_frac_1h_fwd_ab.parquet",
            joint_name="v7_book_tgt_1h_fwd.parquet",
            blind_from=pd.Timestamp("2026-01-01"))
    else:
        sys.exit(f"unknown mode {mode!r} (ic|fwd)")
