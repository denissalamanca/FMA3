"""certify_warmstart.py — the WARM-START CERTIFIER (gate FMA3-RECON-9-WS).

Adjudicates whether a warm-start state blob at boundary D is the state the
FROZEN CHAIN actually had at D, i.e. whether an EA that loads it continues
the golden path instead of splicing a different one.

This is a MEASURING INSTRUMENT.  It is built so that it cannot report PASS
on something it never looked at:

  * REQUIRED MANIFEST (anti-intersection).  The field manifest is declared
    here, not derived from the inputs.  A section/field missing from BOTH
    candidate and reference is a FAIL, not a silent skip.  (The failure this
    kills: a judge that diffs only the key INTERSECTION of two dicts reports
    PASS while dropping whole sleeves.)
  * TWO-SIDED key-set equality at every dict level (missing AND extra) and
    length equality on every array, cross-checked against `config`.
  * LEAF COUNTING.  Every verdict carries n_leaves_compared; a certification
    with fewer leaves than the declared floor is a FAIL.
  * INDEPENDENT ANCHORS (E1..E9) that need NO reference blob: they pin the
    state against artifacts produced by a DIFFERENT chain (the RECON-4 golden
    blend inputs, the BH golden curve, the CoreSim seed pin).

STRICTNESS — the two comparison modes (both are always computed/reported):
  * BLOB mode (RATIFIED for certification): BITWISE on every leaf, including
    continuous ones.  Both sides descend from the same deterministic frozen
    replay (WARMSTART_DESIGN §3: "the blob is just a cached checkpoint"), so
    any bit difference PROVES the candidate did not descend from the frozen
    chain.  A 1-ulp EWM `old_wt` defect is ~1.6e-16 RELATIVE — it is INSIDE
    the 1e-12 band and a tolerance-only judge PASSES it.  Bitwise is therefore
    mandatory, not optional.
  * TOL mode (REPORT-ONLY here): exact for integer/discrete leaves, <=1e-12
    (S1 band) for continuous ones.  This is the band that applies to the
    MQL5 language layer only (no-FMA residual, WARMSTART_DESIGN §7.1), i.e.
    to a blob produced by the TERMINAL.  It is reported so the gap between
    the two modes is visible, never to soften the python-side verdict.

CHECK MAP (the sub-checks the gate reports):
  A  envelope     torn-write / fnv64 / schema / version  (BookState protocol)
  B  guard        RECON-8f continuity latch (anchors, j_hour, w, j-splice 1e-9)
  E  anchors      E1..E9 independent pins (no reference blob needed)
  P  class-P      shadow accounts: b(balance,lots[31],entry[31],n_trades),
                  a(seed, segment/fc cursor, per-leg carry), samplers
  S  class-S      8 sleeve steppers + ensemble + glue: ewm (weighted,old_wt,
                  nobs) triples, hysteresis ints, ring buffers, Donchian
                  breach flags/state machines
  C  re-derive    f_sat/f_core/a_h/b_h/book_frac for the first N hours after D
                  from the RESTORED state vs the golden stream (band 1e-12)
  D  cold-start   the COVID/in-sample inversion guard (see below)

CHECK D — the inverted finding (WARMSTART_DESIGN §0).  For the IN-SAMPLE
reproduction the golden itself was produced by engines that COLD-START at
model t0 with empty indicator state; pre-warming an in-sample run would give
the EA a DIFFERENT (better) COVID state than the golden and BREAK parity.
So in `--mode=in_sample` this certifier REFUSES any warm blob / boundary != t0
(InSampleWarmStartRefused), and it MEASURES the cold-start signature in the
golden itself (leading all-zero f_sat hours per lookback-bearing sleeve, and
a_h==b_h==1.0 at t0) so the claim is evidence, not assertion.

Usage (python >= 3.13; run from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && /usr/local/bin/python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/warmstart/certify_warmstart.py \
      --candidate=<blob> --reference=<frozen-chain blob at D> [--hours=960] \
      [--no-rederive] [--mode=forward|in_sample] [--report=PATH]

The gate driver (self-test + the 4 negative controls) is run_ws_gate.py.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
HERE = FMA3 / "research/bpure/warmstart"
BOOK = FMA3 / "research/bpure/book"
BLEND_IN = FMA3 / "research/outputs/mt5/blend/FMA3_blend_inputs.csv"
GOLDEN = FMA3 / "research/outputs/mt5/FMA3_fed_frac_v3.csv"
GOLDEN_SHA = "d00b614b650b649ac9301b1ffd1eae66af4785ce4417bfa91755d367f8ab452e"
COMMON = Path("/Users/dsalamanca/Library/Application Support/"
              "net.metaquotes.wine.metatrader5/drive_c/users/crossover/"
              "AppData/Roaming/MetaQuotes/Terminal/Common/Files")

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
for _p in (str(FMA2 / "research"), str(FMA2),
           str(FMA3 / "research/bpure/steppers"),
           str(FMA3 / "research/bpure/engine"),
           str(FMA3 / "research/bpure/blend"), str(BOOK)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import book_state_mirror as BSM                                  # noqa: E402
from mirror_blend import broker_sym                              # noqa: E402

# ----------------------------------------------------------------- pins
MODEL_T0 = 1577923200                 # 2020-01-02 00:00 UTC (a/b norm anchor)
INIT_EQUITY = 10000.0                 # CORE_SEED0 / BH INIT (cold t0 anchor)
FINAL_EQC_PIN = 532229.8433634703     # export_coresim_inputs.py seed-chain pin
S1_BAND = 1e-12                       # S1/R1 gate band (golden is %.12f)
EMIT_EPS = 1e-12                      # BOOKORC_EPS build_rows emission threshold
EXPECT_CONFIG = {"w": 0.70, "nin": 37, "nsat": 31, "nnet": 8, "nbook": 33,
                 "nlegs": 9, "held": 16, "ncross": 8}

# ---- the REQUIRED MANIFEST: declared here, never derived from the inputs ----
# A field missing from BOTH sides fails here instead of vanishing from a diff.
REQ_TOP = ["schema", "version", "config", "sleeves", "b_engine", "core",
           "glue", "samplers", "continuity", "fnv64", "eof"]
REQ_SLEEVES = ["mag", "intraday", "meanrev", "crisis", "seasonal_crypto",
               "carry_breakout", "trend_v2", "ensemble"]
REQ_B_ENGINE = ["balance", "lots", "entry", "n_trades"]      # Class-P shadow b
REQ_CORE = ["n_segs", "seed", "seg_open", "core_done", "fc_cursor",
            "carry_valid", "carry_pos", "carry_mid", "carry_qe",
            "fcore_n", "fcore_ts", "fcore_v"]                # Class-P shadow a
REQ_GLUE = ["ffill", "has_day", "cur_day", "tvq_n", "tvq_eff", "tvq_w",
            "crq_n", "crq_eff", "crq_w", "trend_cur", "crisis_cur",
            "have_prev", "prev_ts", "prev_mr", "prev_cbk", "prev_id",
            "prev_cr", "prev_tv", "prev_mg", "h1_bars", "h1_last_ts",
            "finalized", "m1_last_ts", "m1_bars", "b_eqc", "b_eqw",
            "held_n", "held_ts", "held_rows", "last_emit_hour",
            "total_rows", "total_hours", "total_sentinels",
            "last_ah", "last_bh"]
REQ_SAMPLER = ["have", "base", "first_ts", "first_v", "last_ts", "last_v",
               "n", "v"]
REQ_CONT = ["have", "j_hour", "a_h", "b_h", "w", "j", "a_first", "b_first"]
# Class-S: the stepper fields the design names as load-bearing (ewm triples,
# hysteresis ints, ring buffers, Donchian breach flags).  Each entry must be
# PRESENT in the sleeve's state; the deep diff then covers everything else too.
REQ_SLEEVE_FIELDS = {
    "meanrev":        ["wavg", "old_wt", "nobs", "dbuf", "dptr", "dcount",
                       "st", "held", "size", "pos", "close"],
    "carry_breakout": ["vol_ewm", "atr_ewm", "win_hi_f", "win_lo_f",
                       "win_hi_s", "win_lo_s", "sys_f", "sys_s", "c_ff"],
    "crisis":         ["prev_close", "br_ring", "lev", "lev_ring", "ewm_seq",
                       "fr_ring", "flev", "flev_ring", "vol_ewm", "n_steps"],
    "trend_v2":       ["hist", "ewm_weighted", "ewm_old_wt", "ewm_nobs",
                       "held", "n_rows"],
    "intraday":       ["cur_day", "symbols"],
    "mag":            ["mids", "accum_day", "accum_close", "pending", "current"],
    "seasonal_crypto": ["coins", "cur_day"],
}
# floor on the number of leaves a real certification must compare (a judge
# that silently narrows its scope trips this)
LEAF_FLOOR_P = 100_000     # fcore_v/ts + samplers dominate
LEAF_FLOOR_S = 400         # sleeves + glue


class CertRefuse(Exception):
    """Certification refused (loud, with the pinpointed reason)."""


class InSampleWarmStartRefused(CertRefuse):
    """Caller tried to pre-warm an IN-SAMPLE run (WARMSTART_DESIGN §0)."""


# ==========================================================================
# the deep two-sided comparer
# ==========================================================================
def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _discrete(ref) -> bool:
    """Leaf class taken from the REFERENCE (the trusted side) so a candidate
    cannot dodge classification by changing its own type.  bool/str/None and
    JSON ints (hysteresis ints, nobs, counters, cursors, flags) are DISCRETE
    -> exact even in tol mode; floats are CONTINUOUS -> 1e-12 in tol mode."""
    return isinstance(ref, (bool, str)) or ref is None or isinstance(ref, int)


class Diff:
    __slots__ = ("path", "kind", "cand", "ref", "absd", "reld", "tol_ok")

    def __init__(self, path, kind, cand, ref, absd=None, reld=None, tol_ok=None):
        self.path, self.kind = path, kind
        self.cand, self.ref = cand, ref
        self.absd, self.reld, self.tol_ok = absd, reld, tol_ok

    def as_dict(self):
        d = {"path": self.path, "kind": self.kind,
             "candidate": _j(self.cand), "reference": _j(self.ref)}
        if self.absd is not None:
            d["abs_diff"] = self.absd
            d["rel_diff"] = self.reld
            d["within_1e-12_tol"] = self.tol_ok
        return d


def _j(v):
    if isinstance(v, float):
        if v != v or v in (math.inf, -math.inf):
            return repr(v)
        return float(v)
    if isinstance(v, (list, dict)):
        return f"<{type(v).__name__} len={len(v)}>"
    return v


def deep_compare(cand, ref, path="", diffs=None, stats=None, tol=S1_BAND):
    """Two-sided structural + numeric diff.  BITWISE on every leaf; the 1e-12
    tolerance verdict is recorded alongside (never used to suppress a diff).
    Returns (diffs, stats) with stats = {leaves, discrete, continuous}."""
    if diffs is None:
        diffs = []
    if stats is None:
        stats = {"leaves": 0, "discrete": 0, "continuous": 0, "tol_pass": 0}

    if isinstance(ref, dict) or isinstance(cand, dict):
        if not (isinstance(ref, dict) and isinstance(cand, dict)):
            diffs.append(Diff(path, "TYPE_MISMATCH", type(cand).__name__,
                              type(ref).__name__))
            return diffs, stats
        kc, kr = set(cand), set(ref)
        for k in sorted(kr - kc):                       # missing in candidate
            diffs.append(Diff(f"{path}.{k}", "MISSING_IN_CANDIDATE",
                              None, _j(ref[k])))
        for k in sorted(kc - kr):                       # extra in candidate
            diffs.append(Diff(f"{path}.{k}", "EXTRA_IN_CANDIDATE",
                              _j(cand[k]), None))
        for k in sorted(kc & kr):
            deep_compare(cand[k], ref[k], f"{path}.{k}", diffs, stats, tol)
        return diffs, stats

    if isinstance(ref, list) or isinstance(cand, list):
        if not (isinstance(ref, list) and isinstance(cand, list)):
            diffs.append(Diff(path, "TYPE_MISMATCH", type(cand).__name__,
                              type(ref).__name__))
            return diffs, stats
        if len(cand) != len(ref):
            diffs.append(Diff(path, "LENGTH_MISMATCH", len(cand), len(ref)))
            return diffs, stats
        for i, (c, r) in enumerate(zip(cand, ref)):
            deep_compare(c, r, f"{path}[{i}]", diffs, stats, tol)
        return diffs, stats

    # ---- leaf ----
    stats["leaves"] += 1
    disc = _discrete(ref)
    stats["discrete" if disc else "continuous"] += 1

    if _is_num(cand) and _is_num(ref):
        c, r = float(cand), float(ref)
        # NaN is a legitimate stored value (crisis_cur / ffill): NaN==NaN here
        both_nan = (c != c) and (r != r)
        bit_eq = both_nan or (c == r)
        if bit_eq:
            stats["tol_pass"] += 1
            return diffs, stats
        absd = abs(c - r) if not (c != c or r != r) else float("nan")
        den = abs(r) if abs(r) > 0 else 1.0
        reld = absd / den
        tol_ok = (not disc) and (absd == absd) and (reld <= tol)
        if tol_ok:
            stats["tol_pass"] += 1
        diffs.append(Diff(path, "DISCRETE_NEQ" if disc else "VALUE_NEQ",
                          c, r, absd, reld, tol_ok))
        return diffs, stats

    if cand == ref and type(cand) is type(ref):
        stats["tol_pass"] += 1
        return diffs, stats
    diffs.append(Diff(path, "DISCRETE_NEQ", cand, ref))
    return diffs, stats


# ==========================================================================
# manifest / structural checks (run on BOTH sides independently)
# ==========================================================================
def check_manifest(st: dict, side: str) -> list[str]:
    """Declared-manifest presence + config-driven array lengths.  These fire
    even when candidate and reference AGREE (the intersection trap)."""
    errs: list[str] = []

    def need(d, keys, where):
        for k in keys:
            if k not in d:
                errs.append(f"{side}: MISSING REQUIRED FIELD {where}.{k}")

    need(st, REQ_TOP, "")
    if "config" not in st or "sleeves" not in st:
        return errs
    cfg = st["config"]
    for k, v in EXPECT_CONFIG.items():
        if k not in cfg:
            errs.append(f"{side}: MISSING config.{k}")
        elif float(cfg[k]) != float(v):
            errs.append(f"{side}: config.{k} {cfg[k]!r} != expected {v!r}")
    need(st["sleeves"], REQ_SLEEVES, "sleeves")
    for sl, fields in REQ_SLEEVE_FIELDS.items():
        if sl in st["sleeves"]:
            need(st["sleeves"][sl], fields, f"sleeves.{sl}")
    need(st.get("b_engine", {}), REQ_B_ENGINE, "b_engine")
    need(st.get("core", {}), REQ_CORE, "core")
    need(st.get("glue", {}), REQ_GLUE, "glue")
    need(st.get("continuity", {}), REQ_CONT, "continuity")
    for s in ("a", "b"):
        if s in st.get("samplers", {}):
            need(st["samplers"][s], REQ_SAMPLER, f"samplers.{s}")
        else:
            errs.append(f"{side}: MISSING samplers.{s}")
    if errs:
        return errs

    n = cfg["nsat"]
    lens = [("b_engine.lots", len(st["b_engine"]["lots"]), n),
            ("b_engine.entry", len(st["b_engine"]["entry"]), n),
            ("glue.ffill", len(st["glue"]["ffill"]), cfg["nin"]),
            ("glue.held_ts", len(st["glue"]["held_ts"]), cfg["held"]),
            ("glue.held_rows", len(st["glue"]["held_rows"]), cfg["held"] * n),
            ("core.carry_valid", len(st["core"]["carry_valid"]), cfg["nlegs"]),
            ("core.carry_pos", len(st["core"]["carry_pos"]), cfg["nlegs"]),
            ("core.carry_mid", len(st["core"]["carry_mid"]), cfg["nlegs"]),
            ("core.carry_qe", len(st["core"]["carry_qe"]), cfg["nlegs"]),
            ("core.fcore_ts", len(st["core"]["fcore_ts"]),
             st["core"]["fcore_n"]),
            ("core.fcore_v", len(st["core"]["fcore_v"]),
             st["core"]["fcore_n"] * cfg["nnet"]),
            ("samplers.a.v", len(st["samplers"]["a"]["v"]),
             st["samplers"]["a"]["n"]),
            ("samplers.b.v", len(st["samplers"]["b"]["v"]),
             st["samplers"]["b"]["n"])]
    for name, got, want in lens:
        if got != want:
            errs.append(f"{side}: LENGTH {name} {got} != {want}")
    return errs


# ==========================================================================
# E — independent anchors (NO reference blob needed)
# ==========================================================================
def _blend_inputs_row(epoch: int):
    """(a_h, b_h, f_core[8], f_sat[31]) from the RECON-4 golden blend inputs —
    a chain independent of the orchestrator state blob."""
    with open(BLEND_IN) as fh:
        fh.readline()
        hdr = fh.readline().rstrip("\n").split(",")
        for ln in fh:
            if ln.startswith(f"{epoch},"):
                f = ln.rstrip("\n").split(",")
                return (float(f[1]), float(f[2]),
                        [float(x) for x in f[3:11]],
                        [float(x) for x in f[11:42]], hdr)
    return None


def _bh_golden_equity(ts: int):
    dt = time.gmtime(ts)
    q = f"{dt.tm_year}Q{(dt.tm_mon - 1) // 3 + 1}"
    p = COMMON / f"FMA3_bh_golden_{q}.csv"
    if not p.exists():
        return None
    with open(p) as fh:
        for ln in fh:
            if ln.startswith(f"{ts},"):
                return float(ln.split(",")[1])
    return None


def anchors(st: dict) -> dict:
    """E1..E9 — every one BITWISE, every one independent of the reference."""
    out: dict = {}
    core, glue, cont = st["core"], st["glue"], st["continuity"]
    sa, sb = st["samplers"]["a"], st["samplers"]["b"]

    out["E1_core_seed_pin"] = {
        "ok": core["seed"] == FINAL_EQC_PIN, "got": core["seed"],
        "want": FINAL_EQC_PIN, "src": "export_coresim_inputs.py seed-chain pin"}

    leh = int(glue["last_emit_hour"])
    n_le = sum(1 for t in core["fcore_ts"] if int(t) <= leh)
    out["E2_fcore_cursor_invariant"] = {
        "ok": int(core["fc_cursor"]) == n_le, "got": int(core["fc_cursor"]),
        "want": n_le, "src": "fc_cursor == #{fcore_ts <= last_emit_hour}"}

    jh = int(cont["j_hour"])
    row = _blend_inputs_row(jh)
    if row is None:
        out["E3_a_h_vs_golden"] = {"ok": False, "got": cont["a_h"],
                                   "want": None,
                                   "src": f"j_hour {jh} ABSENT from golden grid"}
        out["E4_b_h_vs_golden"] = dict(out["E3_a_h_vs_golden"])
    else:
        a_g, b_g = row[0], row[1]
        out["E3_a_h_vs_golden"] = {
            "ok": cont["a_h"] == a_g, "got": cont["a_h"], "want": a_g,
            "abs_diff": abs(cont["a_h"] - a_g),
            "src": "FMA3_blend_inputs.csv col a @ j_hour (RECON-4 chain)"}
        out["E4_b_h_vs_golden"] = {
            "ok": cont["b_h"] == b_g, "got": cont["b_h"], "want": b_g,
            "abs_diff": abs(cont["b_h"] - b_g),
            "src": "FMA3_blend_inputs.csv col b @ j_hour (RECON-4 chain)"}

    m1 = int(glue["m1_last_ts"])
    eq = _bh_golden_equity(m1)
    out["E5_b_eqc_vs_bh_golden"] = {
        "ok": (eq is not None) and glue["b_eqc"] == eq, "got": glue["b_eqc"],
        "want": eq, "src": f"FMA3_bh_golden_*.csv equity @ m1_last_ts {m1}"}

    out["E6_cold_t0_anchors"] = {
        "ok": (float(sa["first_v"]) == INIT_EQUITY
               and float(sb["first_v"]) == INIT_EQUITY
               and float(cont["a_first"]) == INIT_EQUITY
               and float(cont["b_first"]) == INIT_EQUITY),
        "got": {"sampler_a.first_v": sa["first_v"],
                "sampler_b.first_v": sb["first_v"],
                "continuity.a_first": cont["a_first"],
                "continuity.b_first": cont["b_first"]},
        "want": INIT_EQUITY,
        "src": "t0 COLD-start INIT anchor (a=b=10000 exactly at model t0)"}

    # E7 — stored continuity must equal a recompute from the state's OWN
    # samplers, BITWISE.  Strictly tighter than the RECON-8f j-splice latch
    # (rel 1e-9): a CONSISTENT re-base of an anchor slides under that latch.
    rec = BSM.recompute_continuity(st)
    bad = [k for k in REQ_CONT
           if not (rec[k] == cont[k] or (isinstance(rec[k], float)
                                         and rec[k] != rec[k]
                                         and cont[k] != cont[k]))]
    out["E7_continuity_recompute_bitwise"] = {
        "ok": not bad, "mismatched_fields": bad,
        "got": {k: rec[k] for k in bad}, "want": {k: cont[k] for k in bad},
        "src": "recompute_continuity(state) == state.continuity, BITWISE"}

    j_rec = cont["w"] * cont["a_h"] + (1.0 - cont["w"]) * cont["b_h"]
    out["E8_j_identity"] = {
        "ok": j_rec == cont["j"], "got": j_rec, "want": cont["j"],
        "src": "j == w*a_h + (1-w)*b_h (bitwise, same statement order)"}

    out["E9_t0_anchor_epoch"] = {
        "ok": int(sa["first_ts"]) == MODEL_T0 and int(sb["first_ts"]) == MODEL_T0,
        "got": {"a.first_ts": sa["first_ts"], "b.first_ts": sb["first_ts"]},
        "want": MODEL_T0, "src": "model t0 = 2020-01-02 00:00 UTC"}
    for v in out.values():
        v["ok"] = bool(v["ok"])
    return out


# ==========================================================================
# D — the COVID / in-sample cold-start inversion guard
# ==========================================================================
def assert_cold_start_in_sample(mode: str, candidate: Path | None,
                                boundary: int) -> None:
    """WARMSTART_DESIGN §0: the in-sample reproduction MUST cold-start at t0.
    Pre-warming it BREAKS parity (the golden itself is cold-started, and the
    COVID blindness is BAKED IN).  Refuse loudly."""
    if mode != "in_sample":
        return
    why = []
    if candidate is not None:
        why.append(f"a warm-state blob was supplied ({candidate.name})")
    if boundary != MODEL_T0:
        why.append(f"boundary {boundary} != model t0 {MODEL_T0}")
    if why:
        raise InSampleWarmStartRefused(
            "COLD-START REQUIRED — REFUSING TO PRE-WARM AN IN-SAMPLE RUN.\n"
            "  " + "; ".join(why) + "\n"
            "  The golden curves (a, b, f_core, f_sat, book_frac) were produced\n"
            "  by engines that COLD-START at model t0 with EMPTY indicator state.\n"
            "  The COVID warm-up blindness is BAKED INTO the golden. Seeding the\n"
            "  EA with pre-t0 or warm state gives it a DIFFERENT state than the\n"
            "  golden -> GUARANTEED divergence. Use mode=forward for a live/\n"
            "  restart deploy at D; use a FRESH cold init for the in-sample run.")


def measure_cold_start_signature() -> dict:
    """MEASURE (not assert) that the golden is cold-started: the leading hours
    where each lookback-bearing sleeve's f_sat columns are still exactly 0
    while its indicators warm up.  A pre-warmed (>=2019-seeded) chain would
    NOT show this transient."""
    with open(BLEND_IN) as fh:
        fh.readline()
        hdr = fh.readline().rstrip("\n").split(",")
        sat = hdr[11:42]
        groups = {  # sleeve -> the f_sat columns it owns (model symbols)
            "carry_breakout(960h Donchian)": ["AUDJPY", "CADCHF", "CADJPY",
                                              "EURCAD", "EURNZD", "EURUSD",
                                              "GBPJPY", "NZDJPY", "USDCHF",
                                              "USDJPY"],
            "crisis(250d EwmStd)": ["DAX", "US30", "USA500", "USTEC"],
            "meanrev(SMA200d)": ["AUDNZD", "EURCHF", "EURGBP", "EURSEK",
                                 "EURNOK", "AUDCAD", "NZDCAD"],
            "trend_v2(125d)": ["XAGUSD", "XPTUSD", "XBRUSD", "XNGUSD",
                               "XTIUSD"],
            "crypto(120d MA)": ["BTCUSD", "ETHUSD", "SOLUSD"],
        }
        idx = {g: [sat.index(s) for s in cols if s in sat]
               for g, cols in groups.items()}
        first_nz = {g: None for g in groups}
        a0 = b0 = None
        h = 0
        for ln in fh:
            f = ln.rstrip("\n").split(",")
            if h == 0:
                a0, b0 = float(f[1]), float(f[2])
            fs = f[11:42]
            for g, cols in idx.items():
                if first_nz[g] is None and any(float(fs[i]) != 0.0
                                               for i in cols):
                    first_nz[g] = h
            h += 1
            if all(v is not None for v in first_nz.values()):
                break
    return {"a_h_at_t0": a0, "b_h_at_t0": b0,
            "a_b_normalized_at_t0": (a0 == 1.0 and b0 == 1.0),
            "leading_zero_hours_until_first_nonzero_f_sat": first_nz,
            "cold_start_signature_present":
                all(v is not None and v > 0 for v in first_nz.values()),
            "src": "FMA3_blend_inputs.csv (RECON-4 golden chain)",
            "meaning": "hours>0 == the sleeve was still warming up from EMPTY "
                       "state at t0 -> the golden IS cold-started; a >=2019 "
                       "pre-warm would have produced a signal here at h=0"}


# ==========================================================================
# R — restore fidelity (the DEAD-STATE-FIELD detector)
# ==========================================================================
def restore_fidelity(st: dict) -> dict:
    """Close the gap between certifying the BLOB and certifying the RESTORED
    OBJECTS.  For every Class-S stepper and the Class-P `b` engine:

        set_state(blob_section)  ->  get_state()  ==  blob_section  (BITWISE)

    A field that is SERIALIZED but never CONSUMED by set_state (dead state)
    comes back as the freshly-constructed default instead of the blob's value,
    so the round-trip diverges and this check names the field.  Without it, a
    warm-start could load a perfect-looking blob and still run on stale state:
    the blob diff would be clean while the live engine silently differed."""
    import core as _core                                          # noqa: F401
    from mag_xau_stepper import MagXauStepper
    from intraday_stepper import IntradayStepper
    from meanrev_stepper import MeanrevStepper
    from consolidate_p1c_stepper import ConsolidateP1cStepper
    from carry_breakout_stepper import CarryBreakoutStepper, parse_policy_rates
    from crisis_stepper import CrisisStepper
    from trend_v2_stepper import TrendV2Stepper
    from sat_equity_harness_sim import make_engine

    builders = {
        "mag": lambda: MagXauStepper(),
        "intraday": lambda: IntradayStepper(),
        "meanrev": lambda: MeanrevStepper(),
        "crisis": lambda: CrisisStepper(),
        "seasonal_crypto": lambda: ConsolidateP1cStepper(),
        "carry_breakout": lambda: CarryBreakoutStepper(
            parse_policy_rates(_core.engine_costs.POLICY_RATES)),
        "trend_v2": lambda: TrendV2Stepper(),
    }
    out: dict = {}
    for name, mk in builders.items():
        blob = st["sleeves"].get(name)
        if blob is None:
            out[name] = {"ok": False, "error": "sleeve absent from blob"}
            continue
        try:
            obj = mk()
            if hasattr(obj, "set_state"):
                obj.set_state(blob)
            else:
                obj = type(obj).from_state(blob)
            back = obj.get_state()
        except Exception as e:                            # noqa: BLE001
            out[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            continue
        d, s = deep_compare(back, blob, f"sleeves.{name}")
        out[name] = {"ok": not d, "n_leaves": s["leaves"], "n_diffs": len(d),
                     "diffs": [x.as_dict() for x in d[:8]]}
    # Class-P b engine
    try:
        be = make_engine()
        be.set_state(st["b_engine"])
        d, s = deep_compare(be.get_state(), st["b_engine"], "b_engine")
        out["b_engine"] = {"ok": not d, "n_leaves": s["leaves"],
                           "n_diffs": len(d),
                           "diffs": [x.as_dict() for x in d[:8]]}
    except Exception as e:                                # noqa: BLE001
        out["b_engine"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


# ==========================================================================
# C — output re-derivation from the RESTORED state
# ==========================================================================
def rederive(candidate: Path, hours: int, scratch: Path) -> dict:
    """Restore the blob in a FRESH orchestrator and re-derive f_sat/f_core/
    a_h/b_h/book_frac for the first `hours` emitted hours after D; diff vs the
    golden blend inputs + the golden fed_frac stream.  Band = S1 1e-12."""
    probe_out = scratch / "rederive_probe.json"
    r = subprocess.run(
        ["/usr/local/bin/python3", str(HERE / "resume_probe.py"),
         f"--state={candidate}", f"--hours={hours}", f"--out={probe_out}"],
        cwd="/Users/dsalamanca/vs_env/FableMultiAssets2/research",
        capture_output=True, text=True)
    if r.returncode != 0:
        return {"ok": False, "error": "resume_probe FAILED",
                "rc": r.returncode, "stderr": r.stderr[-2000:]}
    rec = json.loads(probe_out.read_text())

    # ---- golden grid: the emission hours strictly after the boundary -------
    jh = rec["j_hour"]
    grid, ga, gb, gfc, gfs = [], [], [], [], []
    with open(BLEND_IN) as fh:
        fh.readline()
        hdr = fh.readline().rstrip("\n").split(",")
        for ln in fh:
            f = ln.rstrip("\n").split(",")
            e = int(f[0])
            if e <= jh:
                continue
            grid.append(e)
            ga.append(float(f[1]))
            gb.append(float(f[2]))
            gfc.append([float(x) for x in f[3:11]])
            gfs.append([float(x) for x in f[11:42]])
            if len(grid) >= hours:
                break
    n = min(hours, len(grid), len(rec["hours"]))
    res: dict = {"hours_requested": hours, "hours_compared": n,
                 "first_hour": grid[0] if grid else None,
                 "last_hour": grid[n - 1] if n else None,
                 "band": S1_BAND}
    if n == 0:
        return {**res, "ok": False, "error": "no hours re-derived"}
    if len(rec["hours"]) < n:
        return {**res, "ok": False,
                "error": f"probe produced {len(rec['hours'])} hours < {n}"}

    # ---- COVERAGE: the re-derived hour count must match the golden grid ----
    # (an off-by-one emission would silently shift every comparison)
    if rec["hours"][:n] != grid[:n]:
        k = next(i for i in range(n) if rec["hours"][i] != grid[i])
        return {**res, "ok": False, "error": "EMISSION GRID MISMATCH",
                "first_bad_index": k, "rederived_hour": rec["hours"][k],
                "golden_hour": grid[k]}

    def worst(got, want, label, per_row_len=None):
        m, at = 0.0, None
        for i in range(n):
            g, w = got[i], want[i]
            if per_row_len is None:
                d = abs(g - w)
                if d > m:
                    m, at = d, {"hour": grid[i], "got": g, "want": w}
            else:
                for k in range(per_row_len):
                    d = abs(g[k] - w[k])
                    if d > m:
                        m, at = d, {"hour": grid[i], "col": k,
                                    "got": g[k], "want": w[k]}
        return {"stream": label, "max_abs_diff": m, "pass": m <= S1_BAND,
                "worst_at": at}

    checks = [worst(rec["a_h"], ga, "a_h"),
              worst(rec["b_h"], gb, "b_h"),
              worst(rec["f_core"], gfc, "f_core[8]", 8),
              worst(rec["f_sat"], gfs, "f_sat[31]", 31)]

    # ---- book_frac vs the sha-pinned golden emission stream ----------------
    net = rec["net_syms"]
    bsym = [broker_sym(s) for s in net]
    lo, hi = grid[0], grid[n - 1]
    gold: dict[int, dict[str, float]] = {}
    with open(GOLDEN) as fh:
        fh.readline()
        for ln in fh:
            f = ln.rstrip("\n").split(",")
            e = int(f[0])
            if e < lo:
                continue
            if e > hi:
                break
            if f[1] == "__GRID__":
                gold.setdefault(e, {})
                continue
            gold.setdefault(e, {})[f[1]] = float(f[2])
    mx, at, missing, extra = 0.0, None, [], []
    for i in range(n):
        h = grid[i]
        grow = gold.get(h)
        if grow is None:
            missing.append({"hour": h, "why": "hour absent from golden stream"})
            continue
        seen = set()
        for k in range(len(net)):
            v = rec["book_frac"][i][k]
            b = bsym[k]
            if abs(v) > EMIT_EPS:
                if b not in grow:                 # we emit, golden does not
                    extra.append({"hour": h, "sym": b, "got": v})
                    continue
                seen.add(b)
                d = abs(v - grow[b])
                if d > mx:
                    mx, at = d, {"hour": h, "sym": b, "got": v,
                                 "want": grow[b]}
        for b in grow:                            # golden emits, we do not
            if b not in seen:
                missing.append({"hour": h, "sym": b, "want": grow[b]})
    checks.append({"stream": "book_frac[33] (vs sha-pinned golden)",
                   "max_abs_diff": mx,
                   "pass": mx <= S1_BAND and not missing and not extra,
                   "worst_at": at,
                   "rows_missing_vs_golden": missing[:10],
                   "n_missing": len(missing),
                   "rows_extra_vs_golden": extra[:10], "n_extra": len(extra)})

    res["streams"] = checks
    res["ok"] = all(c["pass"] for c in checks)
    res["probe_seconds"] = rec.get("seconds")
    # no-artifact check (WARMSTART_DESIGN §4.4): a cold-start transient would
    # show up as a large early deviation; the band above already forbids it.
    res["no_cold_start_artifact"] = res["ok"]
    return res


# ==========================================================================
# the certification
# ==========================================================================
def certify(candidate: Path, reference: Path | None, boundary: int,
            hours: int, mode: str, do_rederive: bool,
            scratch: Path) -> dict:
    t0 = time.time()
    rep: dict = {"gate": "FMA3-RECON-9-WS warm-start certifier",
                 "candidate": str(candidate),
                 "reference": str(reference) if reference else None,
                 "boundary_epoch": boundary,
                 "boundary_utc": time.strftime("%Y-%m-%d %H:%M:%S",
                                               time.gmtime(boundary)),
                 "mode": mode, "hours": hours,
                 "strictness": {"blob_mode": "BITWISE (ratified)",
                                "tol_mode": f"discrete exact / continuous "
                                            f"<= {S1_BAND:g} (report-only)"}}

    # ---- D: the in-sample inversion guard runs FIRST (it can refuse) -------
    assert_cold_start_in_sample(mode, candidate, boundary)
    rep["D_cold_start"] = measure_cold_start_signature()
    rep["D_cold_start"]["in_sample_prewarm_guard"] = (
        "ARMED — mode=in_sample + any blob/boundary!=t0 raises "
        "InSampleWarmStartRefused")

    # ---- A: envelope (torn-write / fnv64 / schema) -------------------------
    try:
        cand = BSM.load_state_file(candidate)
        rep["A_envelope"] = {"ok": True,
                             "bytes": candidate.stat().st_size,
                             "note": "fnv64 + eof trailer + schema/version OK"}
    except BSM.StateRefuse as e:
        rep["A_envelope"] = {"ok": False, "refuse_reason": e.reason}
        rep["verdict"] = "FAIL"
        rep["failed_checks"] = ["A_envelope"]
        rep["seconds"] = round(time.time() - t0, 1)
        return rep

    # ---- B: the RECON-8f continuity latch ---------------------------------
    try:
        BSM.validate_continuity(cand)
        rep["B_continuity_latch"] = {
            "ok": True, "j": cand["continuity"]["j"],
            "note": "RECON-8f latch (anchors/j_hour/w/j-splice rel<=1e-9) PASS"}
    except BSM.StateRefuse as e:
        rep["B_continuity_latch"] = {"ok": False, "refuse_reason": e.reason}

    # ---- boundary binding: the blob must BE at D --------------------------
    got_h1 = int(cand["glue"]["h1_last_ts"])
    rep["A_boundary_binding"] = {
        "ok": got_h1 == boundary, "h1_last_ts": got_h1, "want": boundary,
        "j_hour": int(cand["continuity"]["j_hour"]),
        "m1_last_ts": int(cand["glue"]["m1_last_ts"]),
        "note": "the state must be the frozen chain's state AT the boundary"}

    # ---- manifest (fires even when both sides agree) -----------------------
    man = check_manifest(cand, "candidate")
    rep["A_manifest"] = {"ok": not man, "errors": man[:20],
                         "n_errors": len(man),
                         "note": f"{len(REQ_TOP)} top / {len(REQ_SLEEVES)} "
                                 f"sleeves / {len(REQ_GLUE)} glue / "
                                 f"{len(REQ_CORE)} core / "
                                 f"{len(REQ_B_ENGINE)} b_engine required "
                                 f"fields DECLARED (not derived)"}

    # ---- E: independent anchors -------------------------------------------
    rep["E_anchors"] = anchors(cand)
    rep["E_anchors_ok"] = all(v["ok"] for v in rep["E_anchors"].values())

    # ---- P / S: the reference-blob deep diff -------------------------------
    if reference is not None:
        ref = BSM.load_state_file(reference)
        rman = check_manifest(ref, "reference")
        rep["A_manifest"]["reference_errors"] = rman[:20]
        rep["A_manifest"]["ok"] = rep["A_manifest"]["ok"] and not rman

        def sect(names):
            cd = {k: cand[k] for k in names if k in cand}
            rd = {k: ref[k] for k in names if k in ref}
            # two-sided: a section present on ONE side only must surface
            for k in names:
                if (k in cand) != (k in ref):
                    cd.setdefault(k, None)
                    rd.setdefault(k, None)
            return cd, rd

        # Class-P: both shadow accounts + the samplers that carry a_h/b_h
        cP, rP = sect(["b_engine", "core", "samplers", "continuity", "config"])
        dP, sP = deep_compare(cP, rP, "")
        rep["P_class_p"] = {
            "ok": not dP and sP["leaves"] >= LEAF_FLOOR_P,
            "n_leaves": sP["leaves"], "leaf_floor": LEAF_FLOOR_P,
            "n_diffs": len(dP),
            "diffs": [d.as_dict() for d in dP[:12]],
            "covers": "b(balance,lots[31],entry[31],n_trades) + "
                      "a(seed,fc_cursor,seg_open,carry[9]x4,fcore) + "
                      "samplers(a,b) + continuity",
            "strictness": "BITWISE"}

        # Class-S: 8 sleeve steppers + ensemble + the H1 glue they drive
        cS, rS = sect(["sleeves", "glue"])
        dS, sS = deep_compare(cS, rS, "")
        n_tol_only = sum(1 for d in dS if d.tol_ok)
        rep["S_class_s"] = {
            "ok": not dS and sS["leaves"] >= LEAF_FLOOR_S,
            "n_leaves": sS["leaves"], "leaf_floor": LEAF_FLOOR_S,
            "n_discrete": sS["discrete"], "n_continuous": sS["continuous"],
            "n_diffs": len(dS),
            "n_diffs_that_1e-12_TOL_WOULD_HAVE_PASSED": n_tol_only,
            "diffs": [d.as_dict() for d in dS[:12]],
            "covers": "ewm(weighted,old_wt,nobs) triples, hysteresis ints, "
                      "ring buffers, Donchian breach flags/state machines, "
                      "ensemble config, glue queues/rings",
            "strictness": "BITWISE (tol verdict reported per-diff)"}
        rep["reference_diff_ran"] = True
    else:
        rep["P_class_p"] = {"ok": False, "error": "NO REFERENCE BLOB — "
                            "Class-P/Class-S cannot be certified"}
        rep["S_class_s"] = dict(rep["P_class_p"])
        rep["reference_diff_ran"] = False

    # ---- R: restore fidelity (dead-state-field detector) -------------------
    rf = restore_fidelity(cand)
    rep["R_restore_fidelity"] = rf
    rep["R_restore_fidelity_ok"] = all(v["ok"] for v in rf.values())

    # ---- C: output re-derivation ------------------------------------------
    if do_rederive:
        rep["C_rederive"] = rederive(candidate, hours, scratch)
    else:
        rep["C_rederive"] = {"ok": None, "skipped": True}

    # ---- verdict -----------------------------------------------------------
    gates = {"A_envelope": rep["A_envelope"]["ok"],
             "A_boundary_binding": rep["A_boundary_binding"]["ok"],
             "A_manifest": rep["A_manifest"]["ok"],
             "B_continuity_latch": rep["B_continuity_latch"]["ok"],
             "E_anchors": rep["E_anchors_ok"],
             "R_restore_fidelity": rep["R_restore_fidelity_ok"],
             "P_class_p": rep["P_class_p"]["ok"],
             "S_class_s": rep["S_class_s"]["ok"]}
    if do_rederive:
        gates["C_rederive"] = rep["C_rederive"]["ok"]
    rep["sub_checks"] = gates
    failed = [k for k, v in gates.items() if not v]
    rep["failed_checks"] = failed
    rep["verdict"] = "PASS" if not failed else "FAIL"
    rep["seconds"] = round(time.time() - t0, 1)
    return rep


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cand = BOOK / "out/FMA3_book_state_D.json"
    ref = None
    boundary = 1656630000
    hours = 960
    mode = "forward"
    do_rd = True
    report = HERE / "out/warmstart_cert.json"
    for a in args:
        if a.startswith("--candidate="):
            cand = Path(a.split("=", 1)[1])
        elif a.startswith("--reference="):
            ref = Path(a.split("=", 1)[1])
        elif a.startswith("--boundary="):
            boundary = int(a.split("=", 1)[1])
        elif a.startswith("--hours="):
            hours = int(a.split("=", 1)[1])
        elif a.startswith("--mode="):
            mode = a.split("=", 1)[1]
        elif a == "--no-rederive":
            do_rd = False
        elif a.startswith("--report="):
            report = Path(a.split("=", 1)[1])
        else:
            raise SystemExit(f"unknown arg: {a}")
    report.parent.mkdir(parents=True, exist_ok=True)
    scratch = report.parent
    try:
        rep = certify(cand, ref, boundary, hours, mode, do_rd, scratch)
    except InSampleWarmStartRefused as e:
        rep = {"gate": "FMA3-RECON-9-WS warm-start certifier", "mode": mode,
               "verdict": "REFUSED", "refuse_class": "InSampleWarmStartRefused",
               "refuse_reason": str(e)}
        report.write_text(json.dumps(rep, indent=1))
        print(f"\n*** REFUSED ***\n{e}\n")
        return 2
    report.write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("verdict", "sub_checks",
                                          "failed_checks", "seconds")
                      if k in rep}, indent=1))
    print(f"report -> {report}")
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
