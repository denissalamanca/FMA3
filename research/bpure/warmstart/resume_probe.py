"""resume_probe.py — check-C instrument: RE-DERIVE the model streams from a
RESTORED warm-start state.

Restores a state blob into a FRESH CBookOrchestrator mirror (the same
`--load` path the live EA's OnInit uses) and captures, for the first N
EMITTED hours after the boundary, the five streams the certifier must judge:

    a_h, b_h, f_core[8], f_sat[31], book_frac[33]

It does this WITHOUT touching book_orchestrator_sim.py (S1/R1 gate code is
frozen): it wraps `BookBlendMirror.step` — the single choke point every
emitted hour passes through, called as blend.step(f_core, f_sat, a_h, b_h)
from CBookOrchestrator::EmitHour — records its inputs and its return, and
aborts the run once N hours are captured (so the probe costs seconds, not
the full 194s tail resume).

HOUR LABELLING (and why it is safe).  EmitHour does not pass the hour to
the blend, so the k-th capture is labelled with the k-th epoch of the
GOLDEN union grid (FMA3_blend_inputs.csv) strictly after the boundary's
last emitted hour.  This is NOT circular: the certifier independently
verifies (i) the captured hour COUNT against the golden grid, and (ii)
a_h/b_h against that same grid — an off-by-one emission would shift every
a_h/b_h by a whole hour and blow the 1e-12 band by orders of magnitude.
The labelling is therefore self-falsifying, not assumed.

Writes {out}: {"j_hour", "hours"[N], "a_h"[N], "b_h"[N], "f_core"[N][8],
"f_sat"[N][31], "book_frac"[N][33], "net_syms"[33], "seconds"}.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
BOOK = FMA3 / "research/bpure/book"
BLEND_IN = FMA3 / "research/outputs/mt5/blend/FMA3_blend_inputs.csv"
sys.path.insert(0, str(BOOK))


class _Done(Exception):
    """captured N hours — unwind the driving loop."""


def main() -> int:
    state = hours = out = None
    for a in sys.argv[1:]:
        if a.startswith("--state="):
            state = Path(a.split("=", 1)[1])
        elif a.startswith("--hours="):
            hours = int(a.split("=", 1)[1])
        elif a.startswith("--out="):
            out = Path(a.split("=", 1)[1])
    assert state and hours and out, "need --state --hours --out"

    import book_state_mirror as BSM
    st = BSM.load_state_file(state)
    j_hour = int(st["continuity"]["j_hour"])

    # golden union grid strictly after the boundary -> the hour labels
    grid: list[int] = []
    with open(BLEND_IN) as fh:
        fh.readline()
        fh.readline()
        for ln in fh:
            e = int(ln.split(",", 1)[0])
            if e > j_hour:
                grid.append(e)
                if len(grid) >= hours:
                    break

    import book_orchestrator_sim as SIM
    orig_step = SIM.BookBlendMirror.step
    rec: dict = {"a_h": [], "b_h": [], "f_core": [], "f_sat": [],
                 "book_frac": [], "net_syms": None}

    def probe_step(self, f_core, f_sat, a, b):
        res = orig_step(self, f_core, f_sat, a, b)
        if rec["net_syms"] is None:
            rec["net_syms"] = list(self.net)
        rec["a_h"].append(float(a))
        rec["b_h"].append(float(b))
        rec["f_core"].append([float(v) for v in f_core])
        rec["f_sat"].append([float(v) for v in f_sat])
        rec["book_frac"].append([float(v) for v in res])
        if len(rec["a_h"]) >= hours:
            raise _Done
        return res

    SIM.BookBlendMirror.step = probe_step
    t0 = time.time()
    scratch = out.parent / "_probe_tail.csv"
    try:
        SIM.main(argv=[f"--load={state}", f"--tail-csv={scratch}"])
    except _Done:
        pass
    finally:
        SIM.BookBlendMirror.step = orig_step
    dt = round(time.time() - t0, 1)

    n = len(rec["a_h"])
    rec["j_hour"] = j_hour
    rec["hours"] = grid[:n]
    rec["seconds"] = dt
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec))
    print(f"[probe] captured {n} emitted hours after {j_hour} "
          f"({dt}s) -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
