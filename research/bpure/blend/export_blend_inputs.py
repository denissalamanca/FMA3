#!/usr/bin/env python3
"""Export the FROZEN static_blend(0.70) inputs for the MQL5 blend harness.

Track C validation chain (BookBlend.mqh):
  1. this script  -> FMA3_blend_inputs.csv   (hourly f_core/f_sat/a/b, %.17g)
                  -> FMA3_blend_golden17.csv (full-precision netted stream)
     and verifies the on-disk golden FMA3_fed_frac_v3.csv byte-for-byte
     against a fresh build_rows() of the canonical static_blend matrix.
  2. mt5/ea/scripts/TestBlend.mq5 (or research/bpure/blend/mirror_blend.py,
     the statement mirror) replays FMA3_blend_inputs.csv through CBookBlend
     -> FMA3_blend_actual*.csv.
  3. research/bpure/blend/validate_blend.py diffs actual vs both goldens.

Inputs CSV format (fmt=blendin1, all doubles %.17g so they round-trip
IEEE-754 binary64 exactly):
  line 1 : w=0.7,config_hash=51a7541cc2aaa593,fmt=blendin1,n_core=8,
           n_sat=31,rows=<H>,sumcheck=<%.17g>
  line 2 : epoch,a,b,<8 Core model symbols>,<31 Sat model symbols>
  rows   : ts_server_epoch,a_h,b_h,f_core*8,f_sat*31

sumcheck = plain left-to-right IEEE double sum of every value in file
order (per row: a, b, f_core[0..7], f_sat[0..30]). The MQL5 harness and
the python mirror accumulate the same order and must match BITWISE -
this catches any StringToDouble parse loss in the terminal.

Self-checks (hard-fail):
  * scalar recompute from the exported arrays == model/v3 static_blend
    matrix EXACTLY (max|diff| must be 0.0 - same statements, no fma);
  * re-parse of the written CSV == exported arrays bitwise (%.17g
    round-trip);
  * fresh build_rows(static_blend) byte-identical to the on-disk golden
    research/outputs/mt5/FMA3_fed_frac_v3.csv (regenerate via
    scripts/export_book_frac_v3.py if missing).

FROZEN-SEASONAL GUARD (2026-07-14 drift incident): FMA2's live
research/outputs/seasonal_pos.parquet was regenerated on 2026-07-14 and
differs from the RECON-5 freeze snapshot on 70 weekly XAUUSD rows. The
on-disk golden stream (sha256 d00b614b..., the RECON-4 pinned artifact)
agrees with the FREEZE version. FMA2 is read-only, so this script
detects the drift and, when present, substitutes the freeze snapshot
model/v3/freeze/FMA3-v34-freeze-1/golden/seasonal_pos.parquet into
E.load_sleeves (same reindex/fillna statements) - LOUDLY. The final
byte-identical-golden gate then proves the substituted chain IS the
model of record.

Usage:
  python3 research/bpure/blend/export_blend_inputs.py            # export + checks
  python3 research/bpure/blend/export_blend_inputs.py --install  # + copy inputs to MT5 Common\\Files
"""
from __future__ import annotations
import sys, hashlib, argparse
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
sys.path.insert(0, str(REPO / "model" / "v3"))
sys.path.insert(0, str(REPO / "engine"))
sys.path.insert(0, str(REPO / "scripts"))
import reproduce as M                    # canonical static_blend / load_inputs
import export_book_frac_v3 as X         # canonical build_rows / write_csv / SYMMAP

OUTDIR   = REPO / "research" / "outputs" / "mt5" / "blend"
INPUTS   = OUTDIR / "FMA3_blend_inputs.csv"
GOLD17   = OUTDIR / "FMA3_blend_golden17.csv"
GOLD12   = REPO / "research" / "outputs" / "mt5" / "FMA3_fed_frac_v3.csv"
COMMON   = Path.home() / ("Library/Application Support/net.metaquotes.wine.metatrader5/"
                          "drive_c/users/crossover/AppData/Roaming/MetaQuotes/Terminal/Common/Files")
FMT      = "blendin1"
EPS      = 1e-12                         # exporter emission threshold (build_rows)
FREEZE_SEASONAL = (REPO / "model" / "v3" / "freeze" / "FMA3-v34-freeze-1" /
                   "golden" / "seasonal_pos.parquet")
LIVE_SEASONAL = Path("/Users/dsalamanca/vs_env/FableMultiAssets2/research/"
                     "outputs/seasonal_pos.parquet")


def frozen_seasonal_guard() -> bool:
    """If FMA2's live seasonal_pos.parquet drifted from the RECON-5 freeze
    snapshot, patch E.load_sleeves to use the freeze copy (the model of
    record). Returns True when the patch was applied."""
    import books  # noqa: F401  side effect: FMA2 sys.path bootstrap
    live = pd.read_parquet(LIVE_SEASONAL)
    froz = pd.read_parquet(FREEZE_SEASONAL)
    if live.equals(froz):
        return False
    n_bad = int((live.reindex(froz.index) != froz).to_numpy().sum())
    print(f"*** FMA2 seasonal_pos.parquet DRIFTED from the RECON-5 freeze "
          f"({n_bad} cells differ) - substituting the FREEZE snapshot ***")
    import ensemble as E
    orig = E.load_sleeves

    def load_sleeves_frozen(names):
        sleeves = orig(names)
        if "seasonal" in sleeves:
            import core
            idx = core.universe_frames(tuple(core.ALL))["ret"].index
            p = pd.read_parquet(FREEZE_SEASONAL)
            sleeves["seasonal"] = p.reindex(idx).fillna(0.0)  # == load_sleeves stmts
        return sleeves

    E.load_sleeves = load_sleeves_frozen
    return True


def g17(v: float) -> str:
    return f"{v:.17g}"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_aligned():
    """The exact alignment statements of reproduce.static_blend, kept
    separate so the raw aligned arrays can be exported."""
    core_frac, sat_frac, a, b = M.load_inputs()
    hours = core_frac.index.union(sat_frac.index)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat = sat_frac.reindex(hours).fillna(0.0)
    return hours, a_h, b_h, f_core, f_sat


def scalar_blend(w, a_h, b_h, f_core_row, f_sat_row, cols, core_pos, sat_pos):
    """Statement-for-statement scalar version of static_blend for ONE hour
    (mirrors CBookBlend::Step). Returns the netted row in cols order."""
    ow = 1.0 - w
    j = w * a_h + ow * b_h
    cc = w * a_h / j
    cs = ow * b_h / j
    out = np.empty(len(cols))
    for k in range(len(cols)):
        fc = f_core_row[core_pos[k]] if core_pos[k] >= 0 else 0.0
        fs = f_sat_row[sat_pos[k]] if sat_pos[k] >= 0 else 0.0
        out[k] = fc * cc + fs * cs
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()

    # config gate (same as the golden exporter)
    import subprocess
    hc = subprocess.run([sys.executable, str(REPO / "strategy_fma3.py")],
                        capture_output=True, text=True).stdout
    assert M.CONFIG_HASH in hc, f"config hash drift: {hc.strip()}"

    patched = frozen_seasonal_guard()
    print(f"frozen-seasonal guard         : "
          f"{'PATCH APPLIED (live FMA2 seasonal drifted)' if patched else 'live == freeze, no patch'}")

    w = M.CORE_WEIGHT
    hours, a_h, b_h, f_core, f_sat = build_aligned()
    core_cols = list(f_core.columns)
    sat_cols = list(f_sat.columns)
    ncore, nsat = len(core_cols), len(sat_cols)
    H = len(hours)
    ep = (hours.astype("int64") // 10**9).to_numpy()
    A = a_h.to_numpy()
    B = b_h.to_numpy()
    FC = f_core.to_numpy()
    FS = f_sat.to_numpy()

    # ---- canonical matrix + netted union bookkeeping ----
    fed = M.static_blend(w)
    cols = list(fed.columns)                      # sorted union (33)
    assert list(fed.index) == list(hours)
    core_pos = [core_cols.index(c) if c in core_cols else -1 for c in cols]
    sat_pos = [sat_cols.index(c) if c in sat_cols else -1 for c in cols]

    # ---- SELF-CHECK 1: scalar statements == pandas static_blend, bitwise ----
    FEDV = fed.to_numpy()
    max_scalar = 0.0
    for i in range(H):
        row = scalar_blend(w, A[i], B[i], FC[i], FS[i], cols, core_pos, sat_pos)
        d = np.abs(row - FEDV[i]).max()
        if d > max_scalar:
            max_scalar = d
    print(f"scalar-vs-pandas static_blend : max|diff| = {max_scalar:.3g}  "
          f"({'PASS' if max_scalar == 0.0 else 'FAIL'} == 0.0)")
    assert max_scalar == 0.0, "scalar statement order does NOT reproduce the model"

    # ---- write inputs CSV (with left-to-right sumcheck) ----
    OUTDIR.mkdir(parents=True, exist_ok=True)
    acc = 0.0
    lines = []
    for i in range(H):
        vals = [A[i], B[i]] + [FC[i, j] for j in range(ncore)] + [FS[i, j] for j in range(nsat)]
        for v in vals:
            acc += v
        lines.append(str(int(ep[i])) + "," + ",".join(g17(v) for v in vals))
    hdr1 = (f"w={g17(w)},config_hash={M.CONFIG_HASH},fmt={FMT},n_core={ncore},"
            f"n_sat={nsat},rows={H},sumcheck={g17(acc)}")
    hdr2 = "epoch,a,b," + ",".join(core_cols) + "," + ",".join(sat_cols)
    INPUTS.write_text(hdr1 + "\n" + hdr2 + "\n" + "\n".join(lines) + "\n")

    # ---- SELF-CHECK 2: re-parse round-trip is bitwise ----
    max_rt = 0.0
    acc2 = 0.0
    with open(INPUTS) as fh:
        fh.readline(); fh.readline()
        for i, line in enumerate(fh):
            f = line.rstrip("\n").split(",")
            assert int(f[0]) == int(ep[i])
            vals = [float(x) for x in f[1:]]
            for v in vals:
                acc2 += v
            ref = [A[i], B[i]] + [FC[i, j] for j in range(ncore)] + [FS[i, j] for j in range(nsat)]
            d = max(abs(x - y) for x, y in zip(vals, ref))
            if d > max_rt:
                max_rt = d
    print(f"inputs %.17g round-trip       : max|diff| = {max_rt:.3g}  "
          f"({'PASS' if max_rt == 0.0 else 'FAIL'} == 0.0)   sumcheck "
          f"{'PASS' if acc2 == acc else 'FAIL'} ({g17(acc)})")
    assert max_rt == 0.0 and acc2 == acc

    # ---- golden17: full-precision netted stream (build_rows emission
    #      semantics: |v|>EPS rows broker-mapped, __GRID__ sentinels,
    #      sorted (epoch, broker_symbol)) ----
    rows = X.build_rows(fed)
    with open(GOLD17, "w") as fh:
        fh.write(f"w_v7={g17(w)},config_hash={M.CONFIG_HASH},fmt=3,prec=17\n")
        for e, sym, v in rows:
            if sym == "__GRID__":
                fh.write(f"{e},__GRID__,0\n")
            else:
                fh.write(f"{e},{sym},{g17(v)}\n")
    n_data = sum(1 for r in rows if r[1] != "__GRID__")
    n_sent = len(rows) - n_data

    # ---- SELF-CHECK 3: on-disk 12dp golden is byte-identical to a fresh
    #      write_csv(build_rows(static_blend)) ----
    if not GOLD12.exists():
        print(f"[WARN] {GOLD12} missing - regenerate with scripts/export_book_frac_v3.py")
        gold_ok = False
    else:
        tmp = OUTDIR / "_gold12_rebuild.tmp"
        X.write_csv(tmp, rows)
        gold_ok = tmp.read_bytes() == GOLD12.read_bytes()
        tmp.unlink()
    print(f"on-disk FMA3_fed_frac_v3.csv  : byte-identical rebuild = "
          f"{'PASS' if gold_ok else 'FAIL'}")
    assert gold_ok

    print(f"\n=== blend inputs export ===")
    print(f"inputs   : {INPUTS}  ({INPUTS.stat().st_size:,} B)  sha256 {_sha(INPUTS)[:16]}")
    print(f"golden17 : {GOLD17}  ({GOLD17.stat().st_size:,} B)  sha256 {_sha(GOLD17)[:16]}")
    print(f"golden12 : {GOLD12}  sha256 {_sha(GOLD12)[:16]}")
    print(f"hours={H}  n_core={ncore}  n_sat={nsat}  net_cols={len(cols)}  "
          f"stream rows={len(rows):,} (data {n_data:,} + sentinels {n_sent:,})")
    print(f"sumcheck = {g17(acc)}")

    if args.install:
        if COMMON.is_dir():
            (COMMON / INPUTS.name).write_bytes(INPUTS.read_bytes())
            print(f"installed -> {COMMON / INPUTS.name}")
        else:
            print(f"[WARN] Common\\Files not found: {COMMON}")

    print("OVERALL  : PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
