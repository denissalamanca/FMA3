"""run_coresignal_ws_gate.py — MEASURED save->restore->resume split gate for
the version-2 warm blob's FOLDED CoreSignal Class-S state (UNIT B / S2
warm-blob completeness). The no-terminal twin of CheckCoreSignalState.mq5.

WHAT IT PROVES (all MEASURED, written to coresignal_ws_gate.json)
-----------------------------------------------------------------
The live Core signal chain (CoreSignalM = mirror of CCoreSignal;
CoreTriggerPy = port of CCoreTrigger) is driven over a deterministic
synthetic multi-instrument daily feed engineered so the XAU Donchian
50/100 breach flags LATCH (b50=b100=+1) BEFORE a boundary and then a flat
hold keeps them latched (no re-breach) through the tail — so the flags are
strictly LOAD-BEARING across the boundary.

  G1  POSITIVE resume: snapshot the COMPLETE live state at boundary B
      (== the version-2 "coresignal" blob field set: 8 leg rings, XAU
      Donchian deques + b50/b100, defer holds, current-day coefficients,
      the trigger's slot-equity segment cursor), restore into FRESH
      objects, resume B+1..N. The resumed target tail (all 9 legs) AND the
      trigger telemetry tail MUST be BITWISE identical to the uninterrupted
      reference run.

  G2  NEGATIVE CONTROL — drop ONE Donchian breach flag (xau.b50): resume
      MUST DIVERGE (proves the unbounded flag cannot be reconstructed from
      a bounded ring rescan — it must be carried EXPLICITLY, exactly what
      CoreSignal.mqh's GetState does at "b50"/"b100").

  G3  NEGATIVE CONTROL — drop a rolling-window ring (xau.vol RollStd
      state): resume MUST DIVERGE (ring completeness).

  G4  NEGATIVE CONTROL — drop the trigger segment cursor (slot_carry /
      slot_carry_has ffill): the trigger telemetry tail MUST DIVERGE.

A negative control that FAILS TO DIVERGE fails the gate (it would mean the
dropped field is not actually load-bearing, i.e. the gate is not testing
what it claims).

Usage:  python3 run_coresignal_ws_gate.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIRROR = HERE.parent / "coresignal" / "mql5_coresignal_mirror.py"
OUT_JSON = HERE / "coresignal_ws_gate.json"

sys.path.insert(0, str(HERE))
from coresignal_trigger_py import CoreTriggerPy  # noqa: E402


# --- load the self-contained stepper classes without the heavy CS/CR chain --
def _load_mirror():
    nb = types.ModuleType("numba")

    def njit(*a, **k):
        if len(a) == 1 and callable(a[0]) and not k:
            return a[0]

        def deco(f):
            return f
        return deco
    nb.njit = njit
    nb.jit = njit
    nb.prange = range

    def _vec(*a, **k):
        def deco(f):
            return f
        return deco
    nb.vectorize = _vec
    sys.modules["numba"] = nb
    spec = importlib.util.spec_from_file_location("cs_mirror", MIRROR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load_mirror()
CoreSignalM = M.CoreSignalM

# instrument feed ids (== CoreSignal.mqh CS_I_*)
I_XAU, I_JPY, I_ETH, I_EG, I_USTEC, I_AUD, I_NZD, I_BTC = range(8)


# =============================================================================
# Generic COMPLETE-state capture / restore. Walks every mutable field of the
# live objects recursively (__slots__ for the kernels, __dict__ for the legs
# and CoreSignalM) — this IS the warm-blob field set the MQL5 GetState emits
# (leg plain attrs + nested RollStd/RollMean/Donchian rings). Restore writes
# the captured state back into FRESH, Configure'd objects (whose static
# config is already correct), so a bitwise resume proves the carried field
# set is SUFFICIENT.
# =============================================================================
_SCALAR = (int, float, bool, str, type(None))


def _fields(o):
    if hasattr(o, "__slots__"):
        return list(o.__slots__)
    return list(o.__dict__.keys())


def capture(o):
    if isinstance(o, _SCALAR):
        return ("v", o)
    if isinstance(o, list):
        return ("l", [capture(x) for x in o])
    if isinstance(o, tuple):
        return ("t", [capture(x) for x in o])
    return ("o", type(o).__name__, {k: capture(getattr(o, k)) for k in _fields(o)})


def _rebuild(snap, cur):
    tag = snap[0]
    if tag == "v":
        return snap[1]
    if tag == "l":
        out = []
        for i, es in enumerate(snap[1]):
            cv = cur[i] if isinstance(cur, list) and i < len(cur) else None
            out.append(_rebuild(es, cv))
        return out
    if tag == "t":
        return tuple(_rebuild(es, None) for es in snap[1])
    # object: restore into the existing (fresh) instance of matching type
    if cur is None or type(cur).__name__ != snap[1]:
        raise RuntimeError(f"restore: missing/mismatched object slot for {snap[1]}")
    for k, fs in snap[2].items():
        setattr(cur, k, _rebuild(fs, getattr(cur, k)))
    return cur


def restore(dst, snap):
    _rebuild(snap, dst)


# =============================================================================
# deterministic synthetic feed
# =============================================================================
BASE = 1577923200                       # 2020-01-02 00:00:00 UTC
NDAYS = 130
BOUNDARY = 115                          # snapshot at end of this day
HOURS = {I_XAU: 12, I_JPY: 13, I_ETH: 14, I_EG: 15,
         I_USTEC: 16, I_AUD: 17, I_NZD: 18, I_BTC: 19}


def mid_for(inst, d):
    """XAU: ramp up (days<110) then FLAT hold — breach latches early and is
    NOT re-established in the tail (=> b50/b100 strictly load-bearing).
    Other legs: gentle deterministic ramps so their rings populate."""
    if inst == I_XAU:
        return 1800.0 + 3.0 * d if d < 110 else 2000.0
    base = {I_JPY: 150.0, I_ETH: 2000.0, I_EG: 0.85, I_USTEC: 15000.0,
            I_AUD: 0.65, I_NZD: 0.60, I_BTC: 40000.0}[inst]
    scale = {I_JPY: 0.05, I_ETH: 5.0, I_EG: 0.001, I_USTEC: 10.0,
             I_AUD: 0.001, I_NZD: 0.001, I_BTC: 50.0}[inst]
    return base + scale * d


def step_day(sig, trig, d, tgt_out, tel_out):
    """step all 8 instruments for day d, then drive the trigger; append the
    end-of-day target vector and trigger telemetry."""
    for inst in range(8):
        ts = BASE + d * 86400 + HOURS[inst] * 3600
        m = mid_for(inst, d)
        sig.step_bar(inst, ts, m, m)
    tgt_out.append(list(sig.tgt))
    # trigger: one union "day" stamp; leg equity from two legs (2-slot cfg)
    ts_day = BASE + d * 86400 + 20 * 3600
    fired = trig.check_day(ts_day)
    trig.on_leg_bar(0, ts_day, 5000.0 + 30.0 * d)
    # slot-1 leg goes SILENT after day 100 (< boundary): from there on its
    # row value can ONLY come from the ffill slot_carry cursor — making that
    # cursor strictly load-bearing across the boundary (G4).
    if d < 100:
        trig.on_leg_bar(1, ts_day, 5000.0 - 8.0 * d)
    tel_out.append((trig.rows_scanned, trig.held_rows, int(fired),
                    trig.decided_day, trig.act_day, trig.kind,
                    list(trig.slot_carry), list(trig.slot_carry_has)))


def fresh_pair():
    sig = CoreSignalM()
    trig = CoreTriggerPy()
    # 2 slots, 2 legs; thresholds set WIDE so no fire (deterministic telemetry)
    trig.configure(2, 2, [0, 1], up=0.99, down=0.001, kmult=1e9, min_gap_days=5)
    trig.begin_segment(10000.0, BASE // 86400)
    return sig, trig


def run(sig, trig, d0, d1, tgt_out, tel_out):
    for d in range(d0, d1):
        step_day(sig, trig, d, tgt_out, tel_out)


def bit_equal_tgt(a, b):
    if len(a) != len(b):
        return False, -1
    for i in range(len(a)):
        for j in range(9):
            x, y = a[i][j], b[i][j]
            # NaN-aware bitwise: equal only if identical bits (NaN!=NaN => not)
            if not (x == y):
                return False, i
    return True, len(a)


def bit_equal_tel(a, b):
    return (a == b), (len(a) if a == b else
                      next((i for i in range(min(len(a), len(b)))
                            if a[i] != b[i]), -1))


# =============================================================================
def main():
    # ---- reference (uninterrupted) -----------------------------------------
    sig_r, trig_r = fresh_pair()
    ref_tgt, ref_tel = [], []
    run(sig_r, trig_r, 0, NDAYS, ref_tgt, ref_tel)
    ref_tail_tgt = ref_tgt[BOUNDARY + 1:]
    ref_tail_tel = ref_tel[BOUNDARY + 1:]

    # sanity: the XAU breach actually latched by the boundary
    xau_b50_at_boundary = sig_r  # recomputed below via a split snapshot

    # ---- split: drive to boundary, snapshot COMPLETE state -----------------
    sig_a, trig_a = fresh_pair()
    a_tgt, a_tel = [], []
    run(sig_a, trig_a, 0, BOUNDARY + 1, a_tgt, a_tel)
    snap_sig = capture(sig_a)
    snap_trig = capture(trig_a)
    b50_latched = float(sig_a.xau.b50)
    b100_latched = float(sig_a.xau.b100)

    rep = {"gate": "FMA3 UNIT-B CoreSignal warm-blob resume gate",
           "ndays": NDAYS, "boundary_day": BOUNDARY,
           "xau_b50_at_boundary": b50_latched,
           "xau_b100_at_boundary": b100_latched}

    # ---- G1 POSITIVE: restore COMPLETE state, resume -----------------------
    sig_b, trig_b = fresh_pair()
    restore(sig_b, snap_sig)
    restore(trig_b, snap_trig)
    b_tgt, b_tel = [], []
    run(sig_b, trig_b, BOUNDARY + 1, NDAYS, b_tgt, b_tel)
    g1_tgt_ok, g1_tgt_first = bit_equal_tgt(b_tgt, ref_tail_tgt)
    g1_tel_ok, _ = bit_equal_tel(b_tel, ref_tail_tel)
    rep["G1_positive"] = {
        "tail_rows": len(ref_tail_tgt),
        "targets_bitwise_identical": bool(g1_tgt_ok),
        "trigger_telemetry_bitwise_identical": bool(g1_tel_ok),
        "first_divergent_row": g1_tgt_first if not g1_tgt_ok else None,
        "pass": bool(g1_tgt_ok and g1_tel_ok)}

    # ---- G2 NEGATIVE: drop ONE Donchian breach flag (xau.b50) --------------
    sig_n, trig_n = fresh_pair()
    restore(sig_n, snap_sig)
    restore(trig_n, snap_trig)
    sig_n.xau.b50 = 0.0                 # DROP the unbounded flag
    n_tgt, n_tel = [], []
    run(sig_n, trig_n, BOUNDARY + 1, NDAYS, n_tgt, n_tel)
    g2_div, g2_first = bit_equal_tgt(n_tgt, ref_tail_tgt)
    rep["G2_drop_b50"] = {
        "diverged": bool(not g2_div),
        "first_divergent_row": g2_first if not g2_div else None,
        "pass": bool(not g2_div)}       # MUST diverge

    # ---- G3 NEGATIVE: drop the xau.vol rolling-window ring -----------------
    sig_v, trig_v = fresh_pair()
    restore(sig_v, snap_sig)
    restore(trig_v, snap_trig)
    fresh_vol = M.RollStdM(20)           # reset RollStd dynamic state to cold
    for s in fresh_vol.__slots__:
        setattr(sig_v.xau.vol, s, getattr(fresh_vol, s))
    v_tgt, v_tel = [], []
    run(sig_v, trig_v, BOUNDARY + 1, NDAYS, v_tgt, v_tel)
    g3_div, g3_first = bit_equal_tgt(v_tgt, ref_tail_tgt)
    rep["G3_drop_vol_ring"] = {
        "diverged": bool(not g3_div),
        "first_divergent_row": g3_first if not g3_div else None,
        "pass": bool(not g3_div)}

    # ---- G4 NEGATIVE: drop the trigger segment cursor (slot_carry) ---------
    sig_t, trig_t = fresh_pair()
    restore(sig_t, snap_sig)
    restore(trig_t, snap_trig)
    trig_t.slot_carry = [0.0] * trig_t.n_slots
    trig_t.slot_carry_has = [False] * trig_t.n_slots
    t_tgt, t_tel = [], []
    run(sig_t, trig_t, BOUNDARY + 1, NDAYS, t_tgt, t_tel)
    g4_div, _ = bit_equal_tel(t_tel, ref_tail_tel)
    rep["G4_drop_trigger_cursor"] = {
        "diverged": bool(not g4_div),
        "pass": bool(not g4_div)}

    rep["breach_latched_before_boundary"] = bool(b50_latched != 0.0
                                                 and b100_latched != 0.0)
    rep["verdict"] = "PASS" if (rep["G1_positive"]["pass"]
                               and rep["G2_drop_b50"]["pass"]
                               and rep["G3_drop_vol_ring"]["pass"]
                               and rep["G4_drop_trigger_cursor"]["pass"]
                               and rep["breach_latched_before_boundary"]) \
        else "FAIL"

    OUT_JSON.write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
