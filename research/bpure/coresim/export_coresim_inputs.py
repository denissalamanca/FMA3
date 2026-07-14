"""export_coresim_inputs.py — per-SEGMENT input bundles for TestCoreSim.mq5
(the a_h CoreSim in-terminal validation data path, CORESIM_SPEC.md section 7).

Per exported committed segment <J> (0..31, windows frozen in
research/outputs/v7_extract_verification.json) this writes to the terminal
Common Files directory:

  FMA3_coresim_seg<J>.csv             leg-major stepper inputs, HEADERLESS,
                                      exactly the 15 fields TestCoreSim.mq5
                                      parses per row:
                                        leg_id,epoch_sec,bid_o,bid_h,bid_l,
                                        bid_c,ask_o,ask_h,ask_l,ask_c,eurq,
                                        swap_flag,swap_long,swap_short,tgt
                                      grouped by leg_id in BOOK APPEND ORDER
                                      (0..8, the TestCoreSim LEG TABLE),
                                      time-ascending within a leg, in-window
                                      native bars only. Doubles %.17g,
                                      bitwise round-trip ASSERTED at write.
  FMA3_coresim_golden_seg<J>.csv      golden combined slice from the parity
                                      parquet [t0,t1): epoch_sec,eqc,eqw,
                                      margin (%.17g, round-trip asserted) —
                                      the SAME format TestCoreSim writes to
                                      FMA3_coresim_actual_seg<J>.csv, so the
                                      judge can be self-tested golden-vs-
                                      golden.
  FMA3_coresim_state_expected_seg<J>.json
                                      expected end state AFTER the segment,
                                      computed by REPLAYING THE WRITTEN CSV
                                      through the scalar reference stepper
                                      (coresim_reference.run_leg_scalar +
                                      combine_legs): seed, legcap/rows/final
                                      balance/pos/entry/n_trades per leg,
                                      flat, union_bars, final eqc/eqw/margin.
  FMA3_coresim_segments.csv           the TestCoreSim manifest: one row
                                      j,t0_epoch,t1_epoch,n_rows per segment,
                                      REGENERATED after every export as the
                                      CONTIGUOUS-FROM-0 prefix of segment
                                      files present in the outdir (the
                                      harness requires j == row index and
                                      runs ALL manifest rows, chaining the
                                      seed — a gap would abort it).

ROUND-TRIP GATE (default ON, --no-replay to skip): after writing, each
segment CSV is re-read from disk (pandas float_precision="round_trip" — the
same value StringToDouble produces from the %.17g token) and replayed
through the scalar reference stepper using ONLY the file contents plus the
TestCoreSim static LEG TABLE constants; the combined eqc/eqw/margin must be
BIT-EQUAL (np.array_equal) to the parity-parquet slice and the union stamps
must match exactly. This proves the file, as the terminal will read it,
drives the CoreSim arithmetic to the golden curve — the in-terminal run then
isolates the MQL5 language layer only.

Seed chain: seg 0 seeds at INIT (10000.0); seg j>0 at triggers[j-1].book,
cross-asserted against the parquet eqc at the last bar < t0 (gate G-c).

Usage (python3 runs from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresim/export_coresim_inputs.py \
    --segments 0                 # measure-first protocol: seg 0, report size
  ... --segments 1 31            # stage more segments
  ... --all                      # full 32-segment export (multi-GB)
  ... --measure-only             # row counts + size estimate, no files
Default --outdir is the wine-prefix terminal Common Files directory.
Writes research/bpure/coresim/coresim_export_report.json (MEASURED numbers).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "coresim_reference", _HERE / "coresim_reference.py")
CR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CR)  # NSF5 sys.path dance + stop_out=1e-9 assert

COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")  # wine user 'crossover' — the
    # directory the terminal actually reads (RECON-8b lesson, Track A).

N_SEG = 32
FINAL_EQC_TARGET = 532229.8433634703

# TestCoreSim.mq5 LEG TABLE — leg_id = row index; order and static config are
# NORMATIVE (asserted below against both sim.book() and NSF5 settings).
#            sleeve        inst      n  contract  comm  lev   step  minlot
LEG_TABLE = [
    ("BOOK_XAU",   "XAUUSD", 1, 100.0,    3.25, 20.0, 0.01, 0.01),
    ("S5_JPY",     "USDJPY", 1, 100000.0, 3.25, 30.0, 0.01, 0.01),
    ("S1_ETH",     "ETHUSD", 1, 1.0,      0.0,  2.0,  0.01, 0.01),
    ("ZC_EG",      "EURGBP", 1, 100000.0, 3.25, 30.0, 0.01, 0.01),
    ("BOOK_USTEC", "USTEC",  1, 1.0,      0.0,  20.0, 0.1,  0.1),
    ("S6_OPEXUSD", "USDJPY", 3, 100000.0, 3.25, 30.0, 0.01, 0.01),
    ("S6_OPEXUSD", "AUDUSD", 3, 100000.0, 3.25, 20.0, 0.01, 0.01),
    ("S6_OPEXUSD", "NZDUSD", 3, 100000.0, 3.25, 20.0, 0.01, 0.01),
    ("BTC_REP",    "BTCUSD", 1, 1.0,      0.0,  2.0,  0.01, 0.01),
]

CSV_FIELDS = ["bid_o", "bid_h", "bid_l", "bid_c",
              "ask_o", "ask_h", "ask_l", "ask_c",
              "eurq", "swap_flag", "swap_long", "swap_short"]  # + tgt


def fmt_f64(a: np.ndarray) -> np.ndarray:
    """%.17g strings, exact float64 round-trip (asserted, bh pattern)."""
    a = np.ascontiguousarray(a, dtype=np.float64)
    assert np.isfinite(a).all(), "non-finite value in export column"
    s = np.char.mod("%.17g", a)
    assert np.array_equal(s.astype(np.float64), a), "f64 round-trip failed"
    return s.astype(object)


def epoch_of(idx: pd.DatetimeIndex) -> np.ndarray:
    a = idx.asi8
    assert (a % 1_000_000_000 == 0).all(), "non whole-second stamps"
    return a // 1_000_000_000


def count_lines(p: Path) -> int:
    n = 0
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 24)
            if not b:
                break
            n += b.count(b"\n")
    return n


# =============================================================================
# preparation: book legs (asserted vs LEG_TABLE), per-instrument arrays,
# parity parquet, frozen segment windows + seed chain
# =============================================================================
def prepare():
    segs, trig_books = CR.load_segments()
    assert len(segs) == N_SEG and len(trig_books) == N_SEG - 1
    CR.prime_feed("ic")
    sleeves = CR.book("BTC_REP", "USTEC")

    legs = []  # (sleeve, inst, slot_legs, tgt64) in book append order
    for name, lgs in sleeves.items():
        for inst, tgt in lgs:
            legs.append((name, inst, len(lgs),
                         np.asarray(tgt, dtype=np.float64)))
    got = [(nm, inst, n) for nm, inst, n, _ in legs]
    want = [(r[0], r[1], r[2]) for r in LEG_TABLE]
    assert got == want, f"book() legs != TestCoreSim LEG TABLE:\n{got}\n{want}"
    for _, inst, _, contract, comm, lev, step, mn in LEG_TABLE:
        c = CR.S.INSTRUMENTS[inst]
        gotc = (float(c["contract_size"]), float(c["commission_side"]),
                float(c["leverage"]), float(c["lot_step"]),
                float(c["min_lot"]))
        assert gotc == (contract, comm, lev, step, mn), \
            f"{inst}: NSF5 settings {gotc} != LEG TABLE constants"

    insts = sorted({inst for _, inst, _, _ in legs})
    arrays = {inst: CR.leg_arrays(inst) for inst in insts}
    par = pd.read_parquet(CR.PARITY_PARQUET)
    return segs, trig_books, legs, arrays, par


def seed_for_seg(j, segs, trig_books, par):
    """Gate G-c: seed = triggers[j-1].book == parquet eqc at last bar < t0."""
    if j == 0:
        return float(CR.INIT), "INIT"
    t0 = segs[j][0]
    k = int(np.searchsorted(par.index.values, np.datetime64(t0),
                            side="left")) - 1
    seed_pq = float(par["eqc"].iloc[k])
    tb = float(trig_books[j - 1])
    assert seed_pq == tb, \
        f"seed chain mismatch seg {j}: parquet {seed_pq!r} vs json {tb!r}"
    return tb, f"triggers[{j-1}].book==parquet@{par.index[k]}"


# =============================================================================
# export one segment (leg-major CSV + golden slice), streaming per leg block
# =============================================================================
def rows_per_segment(segs, legs, arrays):
    """Exact leg-bar row counts per segment (cheap: searchsorted only)."""
    out = []
    for t0, t1 in segs:
        tot = 0
        for _, inst, _, _ in legs:
            iv = arrays[inst]["idx"].values
            i0 = int(np.searchsorted(iv, np.datetime64(t0), side="left"))
            i1 = int(np.searchsorted(iv, np.datetime64(t1), side="left"))
            tot += max(0, i1 - i0)
        out.append(tot)
    return out


def export_segment(outdir: Path, j: int, segs, legs, arrays, par) -> dict:
    t0, t1 = segs[j]
    in_path = outdir / f"FMA3_coresim_seg{j}.csv"
    g_path = outdir / f"FMA3_coresim_golden_seg{j}.csv"

    n_rows = 0
    leg_rows = []
    with open(in_path, "w", newline="") as f:
        for leg_id, (name, inst, n_slot, tgt64) in enumerate(legs):
            A = arrays[inst]
            iv = A["idx"].values
            i0 = int(np.searchsorted(iv, np.datetime64(t0), side="left"))
            i1 = int(np.searchsorted(iv, np.datetime64(t1), side="left"))
            if i1 <= i0:
                leg_rows.append(0)  # flat leg: contributes legcap only
                continue
            n = i1 - i0
            ts = epoch_of(A["idx"][i0:i1])
            assert (np.diff(ts) > 0).all(), f"{inst}: bars not increasing"
            seg_tgt = tgt64[i0:i1]
            assert np.isfinite(seg_tgt).all(), f"{inst}: NaN target in-window"
            cols = [np.full(n, str(leg_id), dtype=object),
                    np.char.mod("%d", ts).astype(object)]
            for fld in CSV_FIELDS:
                cols.append(fmt_f64(A[fld][i0:i1]))
            cols.append(fmt_f64(seg_tgt))
            block = np.stack(cols, axis=1)
            f.write("\n".join(",".join(r) for r in block) + "\n")
            n_rows += n
            leg_rows.append(n)

    # golden combined slice from the parity parquet (round-trip asserted)
    sel = ((par.index.values >= np.datetime64(t0))
           & (par.index.values < np.datetime64(t1)))
    ps = par[sel]
    gts = epoch_of(ps.index)
    gcols = [np.char.mod("%d", gts).astype(object),
             fmt_f64(ps["eqc"].to_numpy()),
             fmt_f64(ps["eqw"].to_numpy()),
             fmt_f64(ps["margin"].to_numpy())]
    gblock = np.stack(gcols, axis=1)
    with open(g_path, "w", newline="") as f:
        f.write("\n".join(",".join(r) for r in gblock) + "\n")

    return dict(segment=j, t0=str(t0), t1=str(t1),
                t0_epoch=int(pd.Timestamp(t0).value // 1_000_000_000),
                t1_epoch=int(pd.Timestamp(t1).value // 1_000_000_000),
                n_rows=n_rows, leg_rows=leg_rows,
                union_bars=int(sel.sum()),
                inputs_bytes=in_path.stat().st_size,
                golden_bytes=g_path.stat().st_size)


# =============================================================================
# round-trip replay gate: re-read the WRITTEN files, replay through the scalar
# reference using ONLY file contents + LEG TABLE constants, bit-compare vs the
# parity parquet slice. Mirrors TestCoreSim/CoreSim.mqh statement flow.
# =============================================================================
COL_NAMES = ["leg", "ts", "bid_o", "bid_h", "bid_l", "bid_c",
             "ask_o", "ask_h", "ask_l", "ask_c",
             "eurq", "swap_flag", "swap_long", "swap_short", "tgt"]


def replay_segment(outdir: Path, j: int, seed: float, segs, par) -> dict:
    t0, t1 = segs[j]
    df = pd.read_csv(outdir / f"FMA3_coresim_seg{j}.csv", header=None,
                     names=COL_NAMES, float_precision="round_trip",
                     dtype={"leg": np.int64, "ts": np.int64,
                            **{c: np.float64 for c in COL_NAMES[2:]}})
    lid = df["leg"].to_numpy()
    assert (np.diff(lid) >= 0).all(), "segment file not leg-major"

    legs_out = []
    flat = 0.0
    states = []
    for leg_id, (name, inst, n_slot, contract, comm, lev, step, mn) \
            in enumerate(LEG_TABLE):
        legcap = seed * CR.W7 / n_slot          # NORMATIVE order (seed*W)/n
        sub = df[lid == leg_id]
        if len(sub) == 0:
            flat += legcap
            states.append(dict(leg_id=leg_id, sleeve=name, inst=inst,
                               slot_legs=n_slot, legcap=legcap, rows=0,
                               flat=True))
            continue
        ts = sub["ts"].to_numpy()
        assert (np.diff(ts) > 0).all(), f"leg {leg_id} not time-ascending"
        n = len(sub)
        eq_c, eq_w, mg, st = CR.run_leg_scalar(
            sub["bid_o"].to_numpy(), sub["bid_h"].to_numpy(),
            sub["bid_l"].to_numpy(), sub["bid_c"].to_numpy(),
            sub["ask_o"].to_numpy(), sub["ask_h"].to_numpy(),
            sub["ask_l"].to_numpy(), sub["ask_c"].to_numpy(),
            sub["eurq"].to_numpy(), sub["swap_flag"].to_numpy(),
            sub["swap_long"].to_numpy(), sub["swap_short"].to_numpy(),
            sub["tgt"].to_numpy(),
            contract, comm, lev, step, mn, legcap, 0, n)
        legs_out.append(dict(idx=pd.DatetimeIndex(
            (ts * 1_000_000_000).view("datetime64[ns]")),
            eq_c=eq_c, eq_w=eq_w, margin=mg))
        states.append(dict(leg_id=leg_id, sleeve=name, inst=inst,
                           slot_legs=n_slot, legcap=legcap, rows=n,
                           balance=st["balance"], pos=st["pos"],
                           entry=st["entry"], n_trades=st["n_trades"]))
    union, eqc, eqw, mg = CR.combine_legs(legs_out, flat)

    sel = ((par.index.values >= np.datetime64(t0))
           & (par.index.values < np.datetime64(t1)))
    ps = par[sel]
    idx_eq = bool(union.equals(ps.index))
    bit_c = bool(idx_eq and np.array_equal(eqc, ps["eqc"].to_numpy()))
    bit_w = bool(idx_eq and np.array_equal(eqw, ps["eqw"].to_numpy()))
    bit_m = bool(idx_eq and np.array_equal(mg, ps["margin"].to_numpy()))

    # golden CSV fidelity: parse the written golden, bit-compare vs parquet
    gd = pd.read_csv(outdir / f"FMA3_coresim_golden_seg{j}.csv", header=None,
                     names=["ts", "eqc", "eqw", "margin"],
                     float_precision="round_trip",
                     dtype={"ts": np.int64, "eqc": np.float64,
                            "eqw": np.float64, "margin": np.float64})
    g_ok = bool(np.array_equal(gd["ts"].to_numpy(), epoch_of(ps.index))
                and np.array_equal(gd["eqc"].to_numpy(), ps["eqc"].to_numpy())
                and np.array_equal(gd["eqw"].to_numpy(), ps["eqw"].to_numpy())
                and np.array_equal(gd["margin"].to_numpy(),
                                   ps["margin"].to_numpy()))

    rep = dict(replay_index_equal=idx_eq, replay_bit_equal_eqc=bit_c,
               replay_bit_equal_eqw=bit_w, replay_bit_equal_margin=bit_m,
               golden_csv_bit_equal_parquet=g_ok,
               flat=flat, final_eqc=float(eqc[-1]), final_eqw=float(eqw[-1]),
               final_margin=float(mg[-1]),
               replay_pass=bool(idx_eq and bit_c and bit_w and bit_m and g_ok))

    state_json = dict(segment=j, t0=str(t0), t1=str(t1), seed=seed,
                      flat=flat, union_bars=int(len(union)),
                      final_eqc=float(eqc[-1]), final_eqw=float(eqw[-1]),
                      final_margin=float(mg[-1]), legs=states)
    (outdir / f"FMA3_coresim_state_expected_seg{j}.json").write_text(
        json.dumps(state_json, indent=1))
    return rep


# =============================================================================
# manifest: contiguous-from-0 prefix of segment files present in outdir
# =============================================================================
def write_manifest(outdir: Path, segs) -> dict:
    rows = []
    for j in range(N_SEG):
        f = outdir / f"FMA3_coresim_seg{j}.csv"
        if not f.exists():
            break
        t0e = int(pd.Timestamp(segs[j][0]).value // 1_000_000_000)
        t1e = int(pd.Timestamp(segs[j][1]).value // 1_000_000_000)
        rows.append(f"{j},{t0e},{t1e},{count_lines(f)}")
    mpath = outdir / "FMA3_coresim_segments.csv"
    if rows:
        mpath.write_text("\n".join(rows) + "\n")
    staged_noncontig = [j for j in range(len(rows), N_SEG)
                        if (outdir / f"FMA3_coresim_seg{j}.csv").exists()]
    return dict(manifest_path=str(mpath), manifest_segments=len(rows),
                staged_but_not_in_manifest=staged_noncontig)


# =============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--segments", type=int, nargs="*", default=None,
                    help="0-based committed segments to export")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--measure-only", action="store_true",
                    help="row counts + size estimate only, write nothing")
    ap.add_argument("--outdir", default=str(COMMON_FILES))
    ap.add_argument("--no-replay", action="store_true",
                    help="skip the round-trip replay bit gate (NOT advised)")
    args = ap.parse_args()

    t_all = time.time()
    outdir = Path(args.outdir)
    which = (list(range(N_SEG)) if args.all
             else (args.segments if args.segments else [0]))
    assert all(0 <= j < N_SEG for j in which)

    print("[1/4] prime IC feed + book() + per-instrument arrays", flush=True)
    segs, trig_books, legs, arrays, par = prepare()
    assert float(par["eqc"].iloc[-1]) == FINAL_EQC_TARGET

    print("[2/4] exact per-segment row counts", flush=True)
    seg_rows = rows_per_segment(segs, legs, arrays)
    total_rows = sum(seg_rows)
    print(f"      total leg-bar rows across 32 segments: {total_rows:,}",
          flush=True)

    report = dict(generated=pd.Timestamp.now().isoformat(),
                  outdir=str(outdir),
                  parity_target=str(CR.PARITY_PARQUET),
                  verification_source=str(CR.VERIFICATION_JSON),
                  total_rows_32seg=total_rows,
                  seg_rows=seg_rows, exported=[], all_replay_pass=True)

    if args.measure_only:
        print(json.dumps(dict(seg_rows=seg_rows, total_rows=total_rows),
                         indent=1))
        return 0

    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[3/4] exporting segments {which}", flush=True)
    for j in sorted(which):
        ts = time.time()
        seed, seed_src = seed_for_seg(j, segs, trig_books, par)
        info = export_segment(outdir, j, segs, legs, arrays, par)
        info.update(seed=seed, seed_src=seed_src)
        if not args.no_replay:
            info.update(replay_segment(outdir, j, seed, segs, par))
            report["all_replay_pass"] &= info["replay_pass"]
        info["seconds"] = round(time.time() - ts, 1)
        report["exported"].append(info)
        print(f"      seg {j:2d} [{segs[j][0].date()} .. {segs[j][1].date()}) "
              f"rows={info['n_rows']:,} inputs={info['inputs_bytes']:,}B "
              f"golden={info['golden_bytes']:,}B "
              f"replay_pass={info.get('replay_pass', 'skipped')} "
              f"final_eqc={info.get('final_eqc', float('nan'))!r} "
              f"({info['seconds']}s)", flush=True)
        assert args.no_replay or info["replay_pass"], \
            f"seg {j}: round-trip replay NOT bit-equal — export unusable"

    # size estimate for the full 32-segment export from measured bytes/row
    b_per_row = (report["exported"][0]["inputs_bytes"]
                 / max(1, report["exported"][0]["n_rows"]))
    est_inputs = int(total_rows * b_per_row)
    g0 = report["exported"][0]
    est_golden = int(2947085 * g0["golden_bytes"] / max(1, g0["union_bars"]))
    report["bytes_per_input_row_measured"] = round(b_per_row, 2)
    report["estimated_full32_inputs_bytes"] = est_inputs
    report["estimated_full32_golden_bytes"] = est_golden
    print(f"      measured {b_per_row:.1f} B/row -> full-32 estimate: "
          f"inputs {est_inputs/1e9:.2f} GB + golden {est_golden/1e9:.2f} GB",
          flush=True)

    print("[4/4] manifest (contiguous prefix) + report", flush=True)
    report.update(write_manifest(outdir, segs))
    report["runtime_s"] = round(time.time() - t_all, 1)
    out_json = _HERE / "coresim_export_report.json"
    out_json.write_text(json.dumps(report, indent=1))
    print(f"EXPORT DONE: manifest covers segments 0..{report['manifest_segments']-1}; "
          f"staged-not-in-manifest {report['staged_but_not_in_manifest']}; "
          f"all_replay_pass={report['all_replay_pass']} "
          f"({out_json}, {report['runtime_s']}s)", flush=True)
    return 0 if report["all_replay_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
