"""book_state_mirror.py — python statement-mirror of the MQL5 whole-book
state serializer (mt5/ea/Include/Book/BookState.mqh).

Shared by book_orchestrator_sim.py (--save-at / --load / --save-end) and
run_state_split_gate.py (the RECON-8d-pattern warm-start gate + the
torn-write / refuse-latch unit tests).

SCHEMA (identical top-level envelope on both languages):

  {"schema": "fma3.bookstate", "version": 1,
   "config":   {w, nin, nsat, nnet, nbook, nlegs, held, ncross},
   "sleeves":  {mag, intraday, meanrev, crisis, seasonal_crypto,
                carry_breakout, trend_v2, ensemble},
   "b_engine": <bh_stepper.get_state()>,
   "core":     {n_segs, seed, seg_open, core_done, fc_cursor,
                carry_valid[9], carry_pos[9], carry_mid[9], carry_qe[9],
                fcore_n, fcore_ts[n], fcore_v[n*8]},
   "glue":     {ffill[37], has_day, cur_day, tvq_n, tvq_eff, tvq_w,
                crq_n, crq_eff, crq_w, trend_cur[5], crisis_cur[4],
                have_prev, prev_ts, prev_mr[16], prev_cbk[21], prev_id[2],
                prev_cr[4], prev_tv[5], prev_mg[1], h1_bars, h1_last_ts,
                finalized, m1_last_ts, m1_bars, b_eqc, b_eqw, held_n,
                held_ts[16], held_rows[496], last_emit_hour, total_rows,
                total_hours, total_sentinels, last_ah, last_bh},
   "samplers": {"a": {have, base, first_ts, first_v, last_ts, last_v,
                      n, v[n]},  "b": {...}},
   "continuity": {have, j_hour, a_h, b_h, w, j, a_first, b_first},
   "fnv64": "<16 lowercase hex>", "eof": true}

Doubles are %.17g (binary64 round-trip), NaN/Infinity as python-json
non-strict tokens.  The trailer `, "fnv64": "...", "eof": true}` is the
torn-write marker protocol: fnv64 = FNV-1a 64-bit over every payload
byte before the trailer; a truncated file loses the eof marker, a
corrupted one fails the checksum — both REFUSE.

DOCUMENTED CROSS-LANGUAGE DIVERGENCE (each language round-trips its OWN
files bit-exact; cross-loading is NOT certified): the four struct-state
sleeves (mag / intraday / meanrev / crisis) serialize as each side's
canonical component state — python's stepper get_state() dicts here,
flat field arrays in MQL5.  Envelope, config, core, glue, samplers,
continuity and the trailer protocol are field-for-field identical.

CONTINUITY GUARD (the j-splice REFUSE_TO_TRADE latch, mirrored from
CBookState::Load): after restore, recompute
    j_restored = w*a_h + (1-w)*b_h
from the restored samplers at the saved emission hour; refuse on
  * any bit difference in a_first / b_first (A-ANCHOR / B-ANCHOR),
  * j_hour / have / w mismatch,
  * relative |j_restored - j_saved| > 1e-9 (J-SPLICE DISCONTINUITY).
A consistent re-base of a sampler + its anchor passes the anchor
equality but MUST trip the j-splice check — the "passes every
self-check while silently mis-weighting every trade" failure mode this
serializer exists to kill.
"""
from __future__ import annotations

import math
import os
from bisect import bisect_right
from pathlib import Path

import numpy as np

SCHEMA = "fma3.bookstate"
VERSION = 1
J_TOL = 1e-9
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MASK64 = (1 << 64) - 1
EOF_MARK = '"eof": true}'
FNV_MARK = ', "fnv64": "'


class StateRefuse(Exception):
    """REFUSE_TO_TRADE: the state file failed validation."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------- format
def f17(x: float) -> str:
    """%.17g with python-json non-strict tokens (== BookStateNum)."""
    if isinstance(x, float):
        if x != x:
            return "NaN"
        if x == math.inf:
            return "Infinity"
        if x == -math.inf:
            return "-Infinity"
        return "%.17g" % x
    return "%.17g" % float(x)


def jdump(obj) -> str:
    """Deterministic JSON dump: floats %.17g, dict insertion order,
    ', ' / ': ' separators (the MQL5 writer's spacing)."""
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, np.bool_):
        return "true" if bool(obj) else "false"
    if isinstance(obj, float):
        return f17(obj)
    if isinstance(obj, (int, np.integer)):
        return str(int(obj))
    if isinstance(obj, str):
        # plain ASCII strings only in this schema
        return '"' + obj + '"'
    if isinstance(obj, dict):
        return "{" + ", ".join('"' + str(k) + '": ' + jdump(v)
                               for k, v in obj.items()) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ", ".join(jdump(v) for v in obj) + "]"
    if isinstance(obj, np.floating):
        return f17(float(obj))
    raise TypeError(f"jdump: unsupported type {type(obj)}")


# --------------------------------------------------------------- fnv/io
def fnv1a64(data: bytes, h: int = FNV_OFFSET) -> int:
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & MASK64
    return h


def with_trailer(payload: str) -> str:
    """payload = full JSON object text MINUS its closing brace."""
    h = fnv1a64(payload.encode("ascii"))
    return payload + f'{FNV_MARK}{h:016x}", "eof": true}}'


def save_state_file(path, state: dict) -> None:
    """Atomic: write <path>.tmp then os.replace (rename) into place."""
    path = Path(path)
    body = jdump(state)
    assert body.endswith("}")
    text = with_trailer(body[:-1])
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_state_file(path) -> dict:
    """Read + torn-write marker + checksum + schema validation.
    Raises StateRefuse (reasons mirror CBookState::Load)."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise StateRefuse(f"state file '{path}' missing/unreadable: {e}")
    if len(raw) == 0:
        raise StateRefuse("state file empty / short read")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise StateRefuse("TORN WRITE: non-ascii bytes in state file")
    if not text.endswith(EOF_MARK):
        raise StateRefuse("TORN WRITE: eof marker missing (partial/failed save)")
    mp = text.rfind(FNV_MARK)
    if mp < 0:
        raise StateRefuse("TORN WRITE: fnv64 trailer missing")
    hex_at = mp + len(FNV_MARK)
    hex_s = text[hex_at:hex_at + 16]
    try:
        want = int(hex_s, 16)
    except ValueError:
        raise StateRefuse("TORN WRITE: fnv64 trailer malformed")
    got = fnv1a64(raw[:mp])
    if got != want:
        raise StateRefuse(f"CHECKSUM MISMATCH: fnv64 {got:016x} != stored "
                          f"{hex_s} (torn/corrupted state file)")
    import json
    try:
        state = json.loads(text)      # NaN/Infinity parse natively
    except ValueError as e:
        raise StateRefuse(f"state json malformed: {e}")
    if state.get("schema") != SCHEMA:
        raise StateRefuse(f"schema '{state.get('schema')}' != '{SCHEMA}'")
    if state.get("version") != VERSION:
        raise StateRefuse(f"state version {state.get('version')} != {VERSION}")
    if state.get("eof") is not True:
        raise StateRefuse("TORN WRITE: eof field not true")
    return state


# ------------------------------------------------------------- samplers
def sampler_state(ts_list, v_list) -> dict:
    """Derive the CBookOrcHourSampler state from a 1m (ts, v) stream:
    materialized hour boundaries H in [ceil(first_ts), last_ts) with the
    asof value, plus the live first/last points (the exact MQL5 Add law)."""
    if not ts_list:
        return {"have": False, "base": 0, "first_ts": 0, "first_v": 0.0,
                "last_ts": 0, "last_v": 0.0, "n": 0, "v": []}
    first_ts, last_ts = int(ts_list[0]), int(ts_list[-1])
    base = first_ts - (first_ts % 3600)
    if base < first_ts:
        base += 3600
    if base >= last_ts:
        n = 0
        vals: list[float] = []
    else:
        n = (last_ts - 1 - base) // 3600 + 1
        bounds = np.arange(base, base + n * 3600, 3600, dtype=np.int64)
        idx = np.searchsorted(np.asarray(ts_list, dtype=np.int64), bounds,
                              side="right") - 1
        assert (idx >= 0).all()
        vv = np.asarray(v_list, dtype=np.float64)
        vals = [float(x) for x in vv[idx]]
    return {"have": True, "base": base, "first_ts": first_ts,
            "first_v": float(v_list[0]), "last_ts": last_ts,
            "last_v": float(v_list[-1]), "n": n, "v": vals}


def sampler_arrays(sp: dict):
    """Reconstruct a (ts, v) point list whose hour-boundary asof queries
    are bitwise-identical to the original stream's.

    The FIRST reconstructed point is ALWAYS (first_ts, first_v) — the
    first_v FIELD is the normalization anchor, exactly like the MQL5
    sampler's m_firstV (AFirst()/BFirst() read the field, not the
    materialized array).  When base == first_ts the base boundary is
    therefore skipped (on any legitimate file its value IS first_v; on a
    tampered file the field is authoritative, mirroring MQL5, so a
    re-based anchor propagates into a_h and trips the j-splice latch
    instead of hiding)."""
    if not sp["have"]:
        return [], []
    ts: list[int] = [int(sp["first_ts"])]
    v: list[float] = [float(sp["first_v"])]
    for i in range(int(sp["n"])):
        h = int(sp["base"]) + i * 3600
        if h == ts[0]:
            continue                      # base == first_ts: field wins
        ts.append(h)
        v.append(float(sp["v"][i]))
    if int(sp["last_ts"]) > ts[-1]:
        ts.append(int(sp["last_ts"]))
        v.append(float(sp["last_v"]))
    return ts, v


# ----------------------------------------------------------- continuity
def recompute_continuity(state: dict) -> dict:
    """Recompute the continuity block from the state's OWN samplers/glue
    (== what a restored orchestrator would answer)."""
    glue = state["glue"]
    w = float(state["config"]["w"])
    a_ts, a_v = sampler_arrays(state["samplers"]["a"])
    b_ts, b_v = sampler_arrays(state["samplers"]["b"])

    def q(ts_l, v_l, h):
        i = bisect_right(ts_l, h) - 1
        if i < 0:
            return 1.0
        return v_l[i] / v_l[0]

    have = int(glue["total_hours"]) > 0
    j_hour = int(glue["last_emit_hour"]) if have else -1
    a_h = q(a_ts, a_v, j_hour) if have else 1.0
    b_h = q(b_ts, b_v, j_hour) if have else 1.0
    return {"have": have, "j_hour": j_hour, "a_h": a_h, "b_h": b_h,
            "w": w, "j": w * a_h + (1.0 - w) * b_h,
            "a_first": (a_v[0] if a_v else 0.0),
            "b_first": (b_v[0] if b_v else 0.0)}


def continuity_guard(saved: dict, restored: dict, tol: float = J_TOL) -> None:
    """Mirror of CBookState::Load's guard chain. Raises StateRefuse."""
    if not (restored["a_first"] == saved["a_first"]):
        raise StateRefuse(
            f"A-ANCHOR MISMATCH: restored a_first {f17(restored['a_first'])} "
            f"!= saved {f17(saved['a_first'])} — state re-based/corrupted")
    if not (restored["b_first"] == saved["b_first"]):
        raise StateRefuse(
            f"B-ANCHOR MISMATCH: restored b_first {f17(restored['b_first'])} "
            f"!= saved {f17(saved['b_first'])} — state re-based/corrupted")
    if bool(restored["have"]) != bool(saved["have"]) \
            or int(restored["j_hour"]) != int(saved["j_hour"]):
        raise StateRefuse(f"J-HOUR MISMATCH: restored {restored['j_hour']} "
                          f"!= saved {saved['j_hour']}")
    if not (restored["w"] == saved["w"]):
        raise StateRefuse(f"W MISMATCH: restored {f17(restored['w'])} != "
                          f"saved {f17(saved['w'])}")
    den = abs(saved["j"])
    if den < 1e-300:
        den = 1e-300
    rel = abs(restored["j"] - saved["j"]) / den
    if not (rel <= tol):                    # NaN-safe: NaN refuses
        raise StateRefuse(
            f"J-SPLICE DISCONTINUITY: j_restored {f17(restored['j'])} vs "
            f"j_saved {f17(saved['j'])} (rel {rel:.3g} > {tol:g}) — "
            f"REFUSE TO TRADE")


def validate_continuity(state: dict, tol: float = J_TOL) -> dict:
    """load-time guard from the state dict alone (used by the unit tests;
    the sim additionally recomputes from its restored live objects)."""
    restored = recompute_continuity(state)
    continuity_guard(state["continuity"], restored, tol)
    return restored
