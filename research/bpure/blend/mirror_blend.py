#!/usr/bin/env python3
"""Statement mirror of mt5/ea/scripts/TestBlend.mq5 (+ Book/BookBlend.mqh).

Runs the EXACT statement sequence of the MQL5 harness in Python over the
same FMA3_blend_inputs.csv and writes FMA3_blend_actual_mirror.csv in the
same format, so BookBlend's arithmetic can be validated against the golden
netted stream TODAY (no terminal needed). Every arithmetic statement below
is a 1:1 transcription:

  CBookBlend::Init  -> BookBlendMirror.__init__ (sorted union, ordinal
                       insertion sort, per-column source indices)
  CBookBlend::Step  -> BookBlendMirror.step:
                          j  = w*a + ow*b        (ow = 1.0 - w, once)
                          cc = w*a/j
                          cs = ow*b/j
                          out[k] = fc*cc + fs*cs (missing leg -> 0.0)
  TestBlend OnStart -> main(): same header checks, same left-to-right
                       sumcheck accumulation, same |v| > 1e-12 emission,
                       same broker map/order, same %.17g cells.

Python floats ARE IEEE-754 binary64 and CPython does not fuse a*b+c, so a
bitwise match to numpy is expected; the judge is validate_blend.py.

Usage: python3 research/bpure/blend/mirror_blend.py
"""
from __future__ import annotations
from pathlib import Path

REPO = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
IN_FILE  = REPO / "research/outputs/mt5/blend/FMA3_blend_inputs.csv"
OUT_FILE = REPO / "research/outputs/mt5/blend/FMA3_blend_actual_mirror.csv"
CONFIG_HASH = "51a7541cc2aaa593"
EPS = 1e-12

MAP_MODEL  = ["USA500", "DAX"]
MAP_BROKER = ["US500", "DE40"]


def broker_sym(model_sym: str) -> str:            # TBL_BrokerSym
    for i in range(2):
        if MAP_MODEL[i] == model_sym:
            return MAP_BROKER[i]
    return model_sym


def cell(v: float) -> str:                        # TBL_Cell
    return f"{v:.17g}"


def cmp_ordinal(a: str, b: str) -> int:           # CBookBlend::CmpOrdinal
    la, lb = len(a), len(b)
    n = la if la < lb else lb
    for i in range(n):
        ca, cb = ord(a[i]), ord(b[i])
        if ca != cb:
            return -1 if ca < cb else 1
    if la == lb:
        return 0
    return -1 if la < lb else 1


class BookBlendMirror:
    """CBookBlend, statement for statement."""

    def __init__(self, w: float, core_syms: list[str], sat_syms: list[str]):
        ncore, nsat = len(core_syms), len(sat_syms)
        assert ncore > 0 and nsat > 0
        assert len(set(core_syms)) == ncore and len(set(sat_syms)) == nsat
        # union then insertion sort, ordinal ascending
        net = list(core_syms)
        for s in sat_syms:
            if s not in net:
                net.append(s)
        for i in range(1, len(net)):
            key = net[i]
            k = i - 1
            while k >= 0 and cmp_ordinal(net[k], key) > 0:
                net[k + 1] = net[k]
                k -= 1
            net[k + 1] = key
        self.net = net
        self.core_ix = [core_syms.index(c) if c in core_syms else -1 for c in net]
        self.sat_ix = [sat_syms.index(c) if c in sat_syms else -1 for c in net]
        self.w = w
        self.ow = 1.0 - w                          # ONCE, Python (1 - w)

    def step(self, f_core: list[float], f_sat: list[float],
             a: float, b: float) -> list[float]:
        # ---- op order is LAW (BookBlend.mqh header) ----
        j = self.w * a + self.ow * b               # (w*a) + ((1-w)*b)
        cc = self.w * a / j                        # (w*a)/j
        cs = self.ow * b / j                       # ((1-w)*b)/j
        out = []
        for k in range(len(self.net)):
            fc = f_core[self.core_ix[k]] if self.core_ix[k] >= 0 else 0.0
            fs = f_sat[self.sat_ix[k]] if self.sat_ix[k] >= 0 else 0.0
            out.append(fc * cc + fs * cs)          # core term + sat term
        return out


def main() -> int:
    with open(IN_FILE) as fh:
        # --- header 1 ---
        kv = dict(t.split("=", 1) for t in fh.readline().rstrip("\n").split(","))
        assert kv["config_hash"] == CONFIG_HASH, "config_hash mismatch"
        assert kv["fmt"] == "blendin1", "bad fmt"
        w = float(kv["w"])                         # StringToDouble
        n_core, n_sat = int(kv["n_core"]), int(kv["n_sat"])
        n_rows = int(kv["rows"])
        sumcheck_str = kv["sumcheck"]
        sumcheck_ref = float(sumcheck_str)

        # --- header 2 ---
        cols = fh.readline().rstrip("\n").split(",")
        assert len(cols) == 3 + n_core + n_sat
        assert cols[0] == "epoch" and cols[1] == "a" and cols[2] == "b"
        core_syms = cols[3:3 + n_core]
        sat_syms = cols[3 + n_core:]

        blend = BookBlendMirror(w, core_syms, sat_syms)
        nnet = len(blend.net)
        print(f"mirror: w={cell(w)}  n_core={n_core}  n_sat={n_sat}  "
              f"net_cols={nnet}  rows={n_rows}")

        # --- emission order: broker-name ordinal insertion sort ---
        perm = list(range(nnet))
        bsym = [broker_sym(blend.net[k]) for k in range(nnet)]
        for i in range(1, nnet):
            pk = perm[i]
            j = i - 1
            while j >= 0 and cmp_ordinal(bsym[perm[j]], bsym[pk]) > 0:
                perm[j + 1] = perm[j]
                j -= 1
            perm[j + 1] = pk

        # --- main loop ---
        acc = 0.0
        hours = data_rows = sentinels = 0
        out_lines = [f"w_v7={cell(w)},config_hash={kv['config_hash']},"
                     f"fmt=3,prec=17,src=mirror_blend"]
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            f = line.split(",")
            assert len(f) == 3 + n_core + n_sat, f"bad row at hour {hours}"
            ep = int(f[0])
            a = float(f[1])
            b = float(f[2])
            acc += a
            acc += b
            f_core = []
            for i in range(n_core):
                f_core.append(float(f[3 + i]))
                acc += f_core[i]
            f_sat = []
            for i in range(n_sat):
                f_sat.append(float(f[3 + n_core + i]))
                acc += f_sat[i]

            out = blend.step(f_core, f_sat, a, b)

            any_leg = False
            for k in range(nnet):
                v = out[perm[k]]
                if abs(v) > EPS:
                    out_lines.append(f"{ep},{bsym[perm[k]]},{cell(v)}")
                    data_rows += 1
                    any_leg = True
            if not any_leg:
                out_lines.append(f"{ep},__GRID__,0")
                sentinels += 1
            hours += 1

    OUT_FILE.write_text("\n".join(out_lines) + "\n")

    sum_ok = (acc == sumcheck_ref) and (cell(acc) == sumcheck_str)
    print(f"mirror: sumcheck computed {cell(acc)} vs header {sumcheck_str} -> "
          f"{'BITWISE MATCH' if sum_ok else '*** MISMATCH ***'}")
    print(f"DONE mirror_blend: hours={hours} (header {n_rows}) "
          f"data_rows={data_rows} sentinels={sentinels} out={OUT_FILE}")
    return 0 if (sum_ok and hours == n_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
