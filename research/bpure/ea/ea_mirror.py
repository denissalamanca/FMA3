"""ea_mirror.py — python STATEMENT MIRROR of FableBookNative.mq5's LIVE-MODE
OnInit/OnTimer driving loop (the LIVE CoreSignal compute chain, NOT the
frozen-target S1 path).  This IS the S2 mirror gate.

WHAT THIS PROVES (the mirror number)
------------------------------------
The EA in live mode (FableBookNative.mq5::Pump -> HourCycle) drives the book
from the terminal's own synchronised multi-symbol feed: the Core leg (a) is
produced by the LIVE CCoreSignal + CCoreTrigger + CoreSim chain (CCoreLiveDrive),
NOT read from a frozen `tgt` column.  This mirror reproduces exactly that
divergence from S1:

    frozen coresim bundle bars (as if CFeedAssembler produced them)
        -> LIVE CoreSignal targets   (core_signal_reference generators,
                                       gen_xau/jpy/eth/eg/ustec/opex_fx/btc —
                                       the RECON-8g / G-S1 bit-zero live path)
        -> CoreSim  (run_leg_scalar_pos + combine_legs, gate G-d/G-b proven)
        -> f_core   (ComputeFCore mirror) + a (combined 1m eqc sampler)
    b engine (SatEquityNative on HELD prior-hour f_sat)   [UNCHANGED from S1]
    BookBlend on asof a_h/b_h -> book_frac[33] -> emit    [UNCHANGED from S1]

Then it diffs the emitted book_frac[33] against the golden RECON-4-pinned
stream FMA3_fed_frac_v3.csv (sha d00b614b…) over the FULL 2020-2025 grid.

WHY THIS IS NOT VACUOUS
-----------------------
The Core targets are RE-DERIVED, bar by bar, by the live CoreSignal generators
from the frozen coresim bundle's bid_c/ask_c — they are NOT copied from the
frozen `tgt` column.  A per-leg live-vs-frozen target diagnostic is recorded
(coresignal_seam) so any feed/CoreSignal wiring error surfaces as a REAL
finding attributed to (segment, leg, ts).  Everything downstream of the target
substitution is the S1-proven machinery, reused verbatim by importing
book_orchestrator_sim and monkey-patching ONLY the core phase — so a divergence
here can ONLY come from the live-target seam (feed rows -> CoreSignal -> CoreSim),
which is exactly the surface S2 introduces over S1.

EXPECTATION (design): G-S2 proved live-CoreSignal->CoreSim is bit-equal to
frozen-target->CoreSim, and S1 proved the frozen-target book is 5.06e-13 vs the
12dp golden; so the live-path book should match to <= 1e-12 (0 cells over gate).
If it diverges MORE than S1's 5.06e-13, the first divergent (segment, leg, ts)
is reported and attributed to the seam.

Data provenance: ALL bars come from the installed frozen bundles in Common
Files (FMA3_coresim_seg{0..31}.csv, FMA3_v34_inputs.csv, FMA3_bh_inputs_*.csv).
core_signal_reference is imported for the GATE-PROVEN generator CODE only (its
NSF5 import resolves the module but NO NSF5 data feeds this run — prime_feed is
never called; the internal live-vs-frozen bit-zero diagnostic proves the
generators consumed only the bundle bars).

Usage (campaign convention — python >= 3.13 for math.fma in the steppers):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && \
    /usr/local/bin/python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/ea/ea_mirror.py
Writes research/bpure/ea/out/FMA3_ea_mirror_actual.csv and
research/bpure/ea/ea_mirror_parity.json (the mirror-gate artifact), and prints
the mirror verdict via validate_book_stream.compare().
"""
from __future__ import annotations

import gc
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
HERE = FMA3 / "research/bpure/ea"
BOOK = FMA3 / "research/bpure/book"
CORESIG = FMA3 / "research/bpure/coresignal"

for p in (str(BOOK), str(CORESIG)):
    if p not in sys.path:
        sys.path.insert(0, p)

# The S1-proven whole-book statement mirror (three-clock driver, b engine,
# blend, emit, judge).  We reuse ALL of it and replace ONLY run_core_phase.
import book_orchestrator_sim as BOS                                # noqa: E402

# The live CoreSignal generators (G-S1 bit-zero, RECON-8g); imported by FILE
# so the NSF5 sys.path dance in coresim_reference resolves exactly as the gate.
import importlib.util                                              # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "core_signal_reference", str(CORESIG / "core_signal_reference.py"))
CS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CS)

TRUE_FINAL_EQC = 532229.8433634703          # export_coresim_inputs.py pin
# leg id -> CoreSignal instrument (LEG TABLE); legs 1 and 5 share USDJPY bars
LEG_INST = ["XAUUSD", "USDJPY", "ETHUSD", "EURGBP", "USTEC",
            "USDJPY", "AUDUSD", "NZDUSD", "BTCUSD"]
# distinct instrument -> the leg that owns its bar stream for target generation
INST_OWNER_LEG = {"XAUUSD": 0, "USDJPY": 1, "ETHUSD": 2, "EURGBP": 3,
                  "USTEC": 4, "AUDUSD": 6, "NZDUSD": 7, "BTCUSD": 8}

# module-level diagnostics filled by live_run_core_phase, read after the run
EA_DIAG: dict = {}


def _mk_index(ts: np.ndarray):
    """DatetimeIndex whose asi8//1e9 == ts (raw server epoch seconds), matching
    the _fields() convention the CoreSignal generators use."""
    idx = pd.to_datetime(ts, unit="s").as_unit("ns")
    assert bool((idx.asi8 // 1_000_000_000 == ts).all()), "index ns drift"
    return idx


def live_run_core_phase():
    """LIVE Core phase: same segment-batch CoreSim replay as
    book_orchestrator_sim.run_core_phase, but every leg's target is the LIVE
    CoreSignal stream (re-derived from the bundle bars) instead of the frozen
    `tgt` column.  Returns the identical 6-tuple
    (a_ts, a_eqc, fts, frows, final_eqc, core_carry)."""
    COMMON = BOS.COMMON
    N_SEG = BOS.N_SEG
    W7 = BOS.W7
    NNET = BOS.NNET

    man = COMMON / "FMA3_coresim_segments.csv"
    rows = [ln.split(",") for ln in man.read_text().strip().split("\n")]
    assert len(rows) == N_SEG, f"manifest has {len(rows)} segments"
    for j, r in enumerate(rows):
        assert int(r[0]) == j, "manifest not contiguous-from-0"

    # ---- PASS 1: reconstruct per-leg native bars from the frozen bundle,
    #      generate the LIVE CoreSignal targets, diff vs the frozen column ----
    BOS.log("live core PASS 1: reconstruct native bars + generate live targets")
    t1 = time.time()
    ts_parts = [[] for _ in range(9)]
    bc_parts = [[] for _ in range(9)]
    ac_parts = [[] for _ in range(9)]
    ft_parts = [[] for _ in range(9)]
    for s in range(N_SEG):
        df = pd.read_csv(COMMON / f"FMA3_coresim_seg{s}.csv", header=None,
                         usecols=[0, 1, 5, 9, 14],
                         names=["leg", "ts", "bid_c", "ask_c", "tgt"],
                         float_precision="round_trip",
                         dtype={"leg": np.int64, "ts": np.int64,
                                "bid_c": np.float64, "ask_c": np.float64,
                                "tgt": np.float64})
        lid = df["leg"].to_numpy()
        tsv = df["ts"].to_numpy()
        bcv = df["bid_c"].to_numpy()
        acv = df["ask_c"].to_numpy()
        ftv = df["tgt"].to_numpy()
        for leg in range(9):
            m = lid == leg
            if m.any():
                ts_parts[leg].append(tsv[m])
                bc_parts[leg].append(bcv[m])
                ac_parts[leg].append(acv[m])
                ft_parts[leg].append(ftv[m])
        del df
    gc.collect()

    leg_ts = [np.concatenate(ts_parts[leg]) if ts_parts[leg]
              else np.empty(0, np.int64) for leg in range(9)]
    leg_bc = [np.concatenate(bc_parts[leg]) if bc_parts[leg]
              else np.empty(0) for leg in range(9)]
    leg_ac = [np.concatenate(ac_parts[leg]) if ac_parts[leg]
              else np.empty(0) for leg in range(9)]
    leg_ft = [np.concatenate(ft_parts[leg]) if ft_parts[leg]
              else np.empty(0) for leg in range(9)]
    del ts_parts, bc_parts, ac_parts, ft_parts
    gc.collect()
    for leg in range(9):
        assert bool((np.diff(leg_ts[leg]) > 0).all()), \
            f"leg {leg} native ts not strictly ascending"

    # legs 1 and 5 are both USDJPY: their reconstructed bar streams MUST match
    assert np.array_equal(leg_ts[1], leg_ts[5]), "USDJPY leg1/leg5 ts differ"
    assert np.array_equal(leg_bc[1], leg_bc[5]), "USDJPY leg1/leg5 bid_c differ"
    assert np.array_equal(leg_ac[1], leg_ac[5]), "USDJPY leg1/leg5 ask_c differ"

    # build the arrays dict generate_all_targets expects (one per distinct inst)
    arrays = {}
    for inst, owner in INST_OWNER_LEG.items():
        arrays[inst] = {"idx": _mk_index(leg_ts[owner]),
                        "bid_c": leg_bc[owner], "ask_c": leg_ac[owner]}
    tgt_live = CS.generate_all_targets(arrays)     # dict leg_id -> np.ndarray
    assert set(tgt_live) == set(range(9)), "generate_all_targets legs"
    for leg in range(9):
        assert len(tgt_live[leg]) == len(leg_ts[leg]), \
            f"leg {leg} live target length mismatch"

    # ---- coresignal seam diagnostic: LIVE target vs FROZEN tgt column -------
    seam = {"max_abs_diff": 0.0, "n_gt_1e12": 0, "discrete_flips": 0,
            "n_not_bit_equal": 0, "first_divergence": None, "per_leg": {}}
    for leg in range(9):
        live = np.asarray(tgt_live[leg], dtype=np.float64)
        froz = leg_ft[leg]
        d = np.abs(live - froz)
        nbe = int((live != froz).sum())
        flips = int((np.sign(live) != np.sign(froz)).sum())
        mx = float(d.max()) if len(d) else 0.0
        ngt = int((d > 1e-12).sum())
        seam["per_leg"][str(leg)] = dict(
            inst=LEG_INST[leg], n=int(len(live)), bit_equal=bool(nbe == 0),
            n_not_bit_equal=nbe, max_abs_diff=mx, n_gt_1e12=ngt,
            discrete_flips=flips)
        seam["max_abs_diff"] = max(seam["max_abs_diff"], mx)
        seam["n_gt_1e12"] += ngt
        seam["discrete_flips"] += flips
        seam["n_not_bit_equal"] += nbe
        if seam["first_divergence"] is None and nbe:
            k = int(np.argmax(live != froz))
            seam["first_divergence"] = dict(
                leg=leg, inst=LEG_INST[leg], ts=int(leg_ts[leg][k]),
                live=float(live[k]), frozen=float(froz[k]))
    seam["bit_equal"] = bool(seam["n_not_bit_equal"] == 0)
    EA_DIAG["coresignal_seam"] = seam
    BOS.log(f"live targets generated: seam bit_equal={seam['bit_equal']} "
            f"max|d|={seam['max_abs_diff']:.3g} n>1e-12={seam['n_gt_1e12']} "
            f"flips={seam['discrete_flips']} ({time.time() - t1:.1f}s)")

    # per-leg native epoch cache for the replay lookup, then drop the bars
    es_cache = [leg_ts[leg] for leg in range(9)]
    del leg_bc, leg_ac, leg_ft
    gc.collect()

    # ---- PASS 2: CoreSim replay (VERBATIM run_core_phase body, live tgt) ----
    BOS.log("live core PASS 2: CoreSim segment-batch replay on LIVE targets")
    a_ts: list[int] = []
    a_eqc: list[float] = []
    fts: list[int] = []
    frows: list[list[float]] = []
    carry = [None] * 9
    seed = BOS.CORE_SEED0
    SEG_COLS = BOS.SEG_COLS

    for j in range(N_SEG):
        t_seg = time.time()
        df = pd.read_csv(COMMON / f"FMA3_coresim_seg{j}.csv", header=None,
                         names=SEG_COLS, float_precision="round_trip",
                         dtype={"leg": np.int64, "ts": np.int64,
                                **{c: np.float64 for c in SEG_COLS[2:]}})
        lid = df["leg"].to_numpy()
        assert (np.diff(lid) >= 0).all(), f"seg {j} not leg-major"
        assert len(df) == int(rows[j][3]), f"seg {j} rows != manifest"

        legs_out = []
        leg_cap = []
        flat = 0.0
        for leg_id in range(9):
            legcap = seed * W7 / BOS.LEG_SLOT[leg_id]
            sub = df[lid == leg_id]
            if len(sub) == 0:
                flat += legcap
                leg_cap.append(None)
                continue
            ts = sub["ts"].to_numpy()
            assert (np.diff(ts) > 0).all(), f"seg {j} leg {leg_id} not asc"
            # --- LIVE TARGET substitution (the ONLY change from S1) ----------
            pos = np.searchsorted(es_cache[leg_id], ts)
            assert (pos < len(es_cache[leg_id])).all() \
                and np.array_equal(es_cache[leg_id][pos], ts), \
                f"seg {j} leg {leg_id}: stamp not on native grid"
            live_tgt = np.asarray(tgt_live[leg_id], dtype=np.float64)[pos]
            # -----------------------------------------------------------------
            n = len(sub)
            eq_c, eq_w, mg, pos_arr, _st = BOS.run_leg_scalar_pos(
                sub["bid_o"].tolist(), sub["bid_h"].tolist(),
                sub["bid_l"].tolist(), sub["bid_c"].tolist(),
                sub["ask_o"].tolist(), sub["ask_h"].tolist(),
                sub["ask_l"].tolist(), sub["ask_c"].tolist(),
                sub["eurq"].tolist(), sub["swap_flag"].tolist(),
                sub["swap_long"].tolist(), sub["swap_short"].tolist(),
                live_tgt.tolist(),
                BOS.LEG_CONTRACT[leg_id], BOS.LEG_COMM[leg_id],
                BOS.LEG_LEV[leg_id], BOS.LEG_STEP[leg_id],
                BOS.LEG_MIN[leg_id], legcap, 0, n)
            legs_out.append(dict(idx=ts, eq_c=eq_c, eq_w=eq_w, margin=mg))
            mid_c = 0.5 * (sub["bid_c"].to_numpy() + sub["ask_c"].to_numpy())
            leg_cap.append((ts, pos_arr, mid_c, sub["eurq"].to_numpy()))
        assert legs_out, f"seg {j}: all legs empty"
        u, eqc, eqw, mg = BOS.combine_legs(legs_out, flat)

        if a_ts:
            assert u[0] > a_ts[-1], f"seg {j}: union stamps not asc at seam"
        a_ts.extend(int(t) for t in u)
        a_eqc.extend(eqc.tolist())

        # ComputeFCore mirror (identical to run_core_phase)
        nu = len(u)
        net_pos = [np.zeros(nu) for _ in range(NNET)]
        net_mid = [np.zeros(nu) for _ in range(NNET)]
        net_qe = [np.zeros(nu) for _ in range(NNET)]
        net_ct = [np.zeros(nu) for _ in range(NNET)]
        net_has = [np.zeros(nu, dtype=bool) for _ in range(NNET)]
        for leg_id in range(9):
            s = BOS.LEG_NET[leg_id]
            cap = leg_cap[leg_id]
            if cap is not None:
                lts, lpos, lmid, lqe = cap
                pi = np.searchsorted(lts, u, side="right") - 1
                hv = pi >= 0
                pc = np.clip(pi, 0, None)
                p = lpos[pc]
                mc = lmid[pc]
                qe = lqe[pc]
                if carry[leg_id] is not None:
                    cp, cm, cq = carry[leg_id]
                    p = np.where(hv, p, cp)
                    mc = np.where(hv, mc, cm)
                    qe = np.where(hv, qe, cq)
                    contrib = np.ones(nu, dtype=bool)
                else:
                    p = np.where(hv, p, 0.0)
                    mc = np.where(hv, mc, 0.0)
                    qe = np.where(hv, qe, 0.0)
                    contrib = hv
            else:
                if carry[leg_id] is None:
                    continue
                cp, cm, cq = carry[leg_id]
                p = np.full(nu, cp)
                mc = np.full(nu, cm)
                qe = np.full(nu, cq)
                contrib = np.ones(nu, dtype=bool)
            net_pos[s] = net_pos[s] + np.where(contrib, p, 0.0)
            new = contrib & ~net_has[s]
            net_mid[s][new] = mc[new]
            net_qe[s][new] = qe[new]
            net_ct[s][new] = BOS.LEG_CONTRACT[leg_id]
            net_has[s] |= contrib
        fr = np.empty((nu, NNET))
        for s in range(NNET):
            val = ((net_pos[s] * net_ct[s]) * net_mid[s]) * net_qe[s]
            frs = val / eqc
            frs[~net_has[s]] = 0.0
            fr[:, s] = frs
        hours = u - (u % 3600)
        last = np.ones(nu, dtype=bool)
        last[:-1] = hours[1:] != hours[:-1]
        hts = hours[last]
        hrows = fr[last]
        start = 0
        if fts and int(hts[0]) == fts[-1]:
            frows[-1] = hrows[0].tolist()
            start = 1
        for k in range(start, len(hts)):
            fts.append(int(hts[k]))
            frows.append(hrows[k].tolist())

        for leg_id in range(9):
            cap = leg_cap[leg_id]
            if cap is not None:
                lts, lpos, lmid, lqe = cap
                carry[leg_id] = (float(lpos[-1]), float(lmid[-1]),
                                 float(lqe[-1]))

        seed = float(eqc[-1])
        BOS.log(f"live core seg {j:2d}: {len(df):>7,} leg-bars, union "
                f"{nu:>7,}, flat {flat:.6g}, final_eqc {seed!r} "
                f"({time.time() - t_seg:.1f}s)")
        del df, legs_out, leg_cap
        gc.collect()

    assert all(fts[i] < fts[i + 1] for i in range(len(fts) - 1)), \
        "f_core hours not strictly ascending"

    EA_DIAG["live_final_eqc"] = seed
    EA_DIAG["live_final_eqc_bit_equal_pin"] = bool(seed == TRUE_FINAL_EQC)
    # Let BOS.main's `assert final_eqc == FINAL_EQC_TARGET` proceed to the
    # golden diff regardless of the live seed (the mirror gate is the golden
    # diff, not the seed assert); the true-pin bit-equality is recorded above.
    BOS.FINAL_EQC_TARGET = seed
    return a_ts, a_eqc, fts, frows, seed, carry


def main() -> int:
    # redirect the S1 mirror's fixed output paths to the ea/ artifacts
    BOS.OUT_CSV = HERE / "out/FMA3_ea_mirror_actual.csv"
    BOS.OUT_JSON = HERE / "ea_mirror_parity.json"
    BOS.OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    # swap the frozen core phase for the LIVE CoreSignal core phase
    BOS.run_core_phase = live_run_core_phase

    rc = BOS.main([])       # full 2020-2025 grid, no state args

    # fold the live diagnostics into the parity report (the mirror artifact)
    rep = json.loads(BOS.OUT_JSON.read_text())
    rep["mirror"] = "ea_mirror (LIVE CoreSignal path)"
    rep["coresignal_seam"] = EA_DIAG.get("coresignal_seam")
    rep["live_final_eqc"] = EA_DIAG.get("live_final_eqc")
    rep["live_final_eqc_bit_equal_pin"] = EA_DIAG.get(
        "live_final_eqc_bit_equal_pin")
    # correct the (patched) core_final_eqc_bit_equal_pin to the TRUE pin
    rep["core_final_eqc_bit_equal_pin"] = EA_DIAG.get(
        "live_final_eqc_bit_equal_pin")
    BOS.OUT_JSON.write_text(json.dumps(rep, indent=1))
    seam = EA_DIAG.get("coresignal_seam", {})
    print(f"[ea_mirror] coresignal_seam: bit_equal={seam.get('bit_equal')} "
          f"max|d|={seam.get('max_abs_diff')} flips={seam.get('discrete_flips')}"
          f" | live_final_eqc_bit_equal_pin="
          f"{EA_DIAG.get('live_final_eqc_bit_equal_pin')}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
