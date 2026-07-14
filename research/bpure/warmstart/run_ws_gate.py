"""run_ws_gate.py — the FMA3-RECON-9-WS gate driver.

Runs the warm-start certifier for real AND proves the certifier is a valid
instrument.  An instrument without a passing NEGATIVE control is not delivered.

  SELF-TEST (positive):  certify(reference, reference) must PASS every
                         sub-check, with n_leaves above the declared floor.
  CERTIFICATION:         certify(B1 blob @ D, B2 frozen-chain replay @ D)
                         with the full check map A/B/E/P/S/C/D.
  NEGATIVE CONTROLS:     each injects ONE known defect into the candidate and
                         RE-SIGNS the file with a fresh fnv64 trailer, so the
                         torn-write/checksum latch CANNOT be what catches it —
                         the certifier's SEMANTIC checks must catch it, and
                         must PINPOINT the field.

    NC1  ewm old_wt  += 1 ulp        (Class-S continuous; rel ~1.6e-16 —
                                      INSIDE the 1e-12 band: a tolerance-only
                                      judge PASSES this. Bitwise must fail it.)
    NC2  meanrev hysteresis int flip (Class-S discrete)
    NC3  CoreSim segment cursor +1   (Class-P; ALSO caught by anchor E2 with
                                      no reference blob at all)
    NC4  a_first += 1e-9, CONSISTENTLY re-based in sampler AND continuity
                                     (slides UNDER the RECON-8f j-splice latch:
                                      rel j jump ~7e-14 << 1e-9 tol. Must be
                                      caught by E6/E7 + the bitwise diff.)
    NC5  a whole sleeve DELETED from BOTH candidate AND reference
                                     (THE ANTIGRAVITY CONTROL: an intersection-
                                      diff judge sees nothing to compare and
                                      reports PASS. The DECLARED manifest must
                                      fail it.)
    NC6  mode=in_sample + a warm blob (WARMSTART_DESIGN §0: must REFUSE)

  NC1 additionally runs the check-C output re-derivation, to MEASURE whether
  960h of golden-stream comparison would have caught a 1-ulp state defect on
  its own (i.e. whether the bitwise state-diff is load-bearing or redundant).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
HERE = FMA3 / "research/bpure/warmstart"
OUT = HERE / "out"
BOOK = FMA3 / "research/bpure/book"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BOOK))

import book_state_mirror as BSM                      # noqa: E402
import certify_warmstart as CW                       # noqa: E402

CAND = BOOK / "out/FMA3_book_state_D.json"           # B1: the RECON-8f blob
REF = OUT / "FMA3_book_state_Dref.json"              # B2: fresh replay t0->D
D = 1656630000
HOURS = 960                                          # >= carry_breakout 960h
T0 = time.time()


def log(m):
    print(f"[ws-gate {time.time() - T0:7.1f}s] {m}", flush=True)


# ---------------------------------------------------------------- mutator
def load_dict(p: Path) -> dict:
    return BSM.load_state_file(p)


def write_mutated(base: Path, dst: Path, mutate) -> dict:
    """Round-trip the blob through jdump, apply `mutate`, RE-SIGN with a fresh
    fnv64 trailer.  Hard self-check: an UNMUTATED round-trip must reproduce the
    source bytes EXACTLY — otherwise the 'negative control' would be measuring
    the mutator's own noise instead of the injected defect."""
    text = base.read_text(encoding="ascii")
    st = BSM.load_state_file(base)
    # load_state_file returns the parsed dict INCLUDING the trailer keys;
    # with_trailer re-appends them, so they must come off first.
    st.pop("fnv64", None)
    st.pop("eof", None)
    body = BSM.jdump(st)
    assert body.endswith("}")
    rt = BSM.with_trailer(body[:-1])
    assert rt == text, ("MUTATOR NOT FAITHFUL: unmutated round-trip differs "
                        "from source bytes — negative controls would be invalid")
    info = mutate(st)
    body = BSM.jdump(st)
    dst.write_text(BSM.with_trailer(body[:-1]), encoding="ascii")
    return info


def preexisting_latches(p: Path) -> dict:
    """What the ALREADY-SHIPPED RECON-8f protections say about this file.
    (If these catch a defect, the certifier is not the thing being tested.)"""
    out = {"envelope_fnv64_eof": None, "continuity_latch": None}
    try:
        st = BSM.load_state_file(p)
        out["envelope_fnv64_eof"] = "PASS (file loads — checksum is NOT the catcher)"
    except BSM.StateRefuse as e:
        out["envelope_fnv64_eof"] = f"REFUSE: {e.reason}"
        return out
    try:
        BSM.validate_continuity(st)
        out["continuity_latch"] = "PASS (RECON-8f latch does NOT catch this)"
    except BSM.StateRefuse as e:
        out["continuity_latch"] = f"REFUSE: {e.reason}"
    return out


def pinpoints(rep: dict) -> list[str]:
    """The field paths the certifier named."""
    pp = []
    for sec in ("P_class_p", "S_class_s"):
        for d in rep.get(sec, {}).get("diffs", []):
            pp.append(f"{sec}:{d['path']} [{d['kind']}] "
                      f"cand={d['candidate']!r} ref={d['reference']!r}")
    for k, v in rep.get("E_anchors", {}).items():
        if not v["ok"]:
            pp.append(f"E_anchors:{k} got={v.get('got')!r} "
                      f"want={v.get('want')!r}")
    for e in rep.get("A_manifest", {}).get("errors", []):
        pp.append(f"A_manifest:{e}")
    for e in rep.get("A_manifest", {}).get("reference_errors", []):
        pp.append(f"A_manifest(ref):{e}")
    for k, v in rep.get("R_restore_fidelity", {}).items():
        if not v["ok"]:
            for d in v.get("diffs", []):
                pp.append(f"R_restore_fidelity:{d['path']} [{d['kind']}] "
                          f"restored={d['candidate']!r} blob={d['reference']!r}")
            if "error" in v:
                pp.append(f"R_restore_fidelity:{k}: {v['error']}")
    c = rep.get("C_rederive", {})
    if c.get("ok") is False:
        for s in c.get("streams", []):
            if not s["pass"]:
                pp.append(f"C_rederive:{s['stream']} max|d|="
                          f"{s['max_abs_diff']:.3g} at {s.get('worst_at')}")
        if "error" in c:
            pp.append(f"C_rederive:{c['error']}")
    return pp


# ---------------------------------------------------------------- mutations
def m_ewm_ulp(st):
    v = st["sleeves"]["meanrev"]["old_wt"]["AUDNZD"]
    nv = math.nextafter(float(v), math.inf)
    st["sleeves"]["meanrev"]["old_wt"]["AUDNZD"] = nv
    return {"field": "sleeves.meanrev.old_wt.AUDNZD", "from": v, "to": nv,
            "abs_delta": abs(nv - float(v)),
            "rel_delta": abs(nv - float(v)) / abs(float(v)),
            "note": "1 ulp — INSIDE the 1e-12 tolerance band"}


def m_hyst_flip(st):
    stt = st["sleeves"]["meanrev"]["st"]
    k = sorted(stt)[0]
    v = stt[k]
    nv = int(v) + 1 if int(v) == 0 else 0
    stt[k] = nv
    return {"field": f"sleeves.meanrev.st.{k}", "from": v, "to": nv,
            "note": "meanrev z-score hysteresis state machine"}


def m_core_cursor(st):
    v = int(st["core"]["fc_cursor"])
    st["core"]["fc_cursor"] = v + 1
    return {"field": "core.fc_cursor", "from": v, "to": v + 1,
            "note": "CoreSim f_core segment cursor (a-engine consumption "
                    "position) — desyncs f_core from the emission grid"}


def m_a_first(st):
    d = 1e-9
    v1 = float(st["samplers"]["a"]["first_v"])
    v2 = float(st["continuity"]["a_first"])
    st["samplers"]["a"]["first_v"] = v1 + d
    st["continuity"]["a_first"] = v2 + d
    return {"field": "samplers.a.first_v + continuity.a_first",
            "from": v1, "to": v1 + d, "abs_delta": d,
            "rel_delta": d / v1,
            "note": "CONSISTENT re-base: passes the A-ANCHOR equality check; "
                    "implied j jump ~7e-14 rel, far under the 1e-9 j-splice "
                    "latch -> the shipped latch does NOT catch it"}


def m_drop_sleeve(st):
    st["sleeves"].pop("trend_v2", None)
    return {"field": "sleeves.trend_v2", "note": "whole sleeve DELETED from "
            "BOTH candidate and reference — an intersection-diff judge has "
            "nothing to compare and reports PASS"}


def m_b_balance(st):
    v = float(st["b_engine"]["balance"])
    st["b_engine"]["balance"] = v + 1.0
    return {"field": "b_engine.balance", "from": v, "to": v + 1.0,
            "note": "SENSITIVITY CONTROL for check C: a defect that MUST move "
                    "the re-derived b_h stream (~1e-4 rel, 1e8x the band). If "
                    "C_rederive still PASSED, check C would be a no-op that "
                    "never actually reads the candidate."}


NEGATIVES = [
    ("NC1_ewm_old_wt_1ulp", m_ewm_ulp, "candidate", True),
    ("NC2_meanrev_hysteresis_int", m_hyst_flip, "candidate", False),
    ("NC3_coresim_segment_cursor", m_core_cursor, "candidate", False),
    ("NC4_a_first_shift_1e-9", m_a_first, "candidate", False),
    ("NC5_sleeve_dropped_BOTH_SIDES", m_drop_sleeve, "both", False),
    ("NC7_C_sensitivity_b_balance", m_b_balance, "candidate", True),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    assert CAND.exists() and REF.exists(), "need both blobs"
    rep: dict = {"gate": "FMA3-RECON-9-WS", "boundary_epoch": D,
                 "boundary_utc": "2022-06-30 23:00:00 UTC",
                 "hours_rederived": HOURS,
                 "candidate_blob": str(CAND), "reference_blob": str(REF)}

    # ---- the B1==B2 identity (WARMSTART_DESIGN §3 core claim) --------------
    import hashlib
    hc = hashlib.sha256(CAND.read_bytes()).hexdigest()
    hr = hashlib.sha256(REF.read_bytes()).hexdigest()
    rep["B1_vs_B2_replay"] = {
        "candidate_sha256": hc, "reference_sha256": hr,
        "byte_identical": hc == hr, "bytes": CAND.stat().st_size,
        "claim": "WARMSTART_DESIGN §3: chained replay-from-t0 == a checkpoint "
                 "blob. MEASURED: a fresh B2 replay t0->D reproduces the B1 "
                 "blob BYTE-FOR-BYTE."}
    log(f"B1 vs B2 byte-identical: {hc == hr} ({hc[:16]}...)")

    # ---- SELF-TEST: judge(reference, reference) must PASS ------------------
    log("SELF-TEST: certify(reference, reference) ...")
    s = CW.certify(REF, REF, D, HOURS, "forward", False, OUT)
    rep["self_test"] = {
        "verdict": s["verdict"], "sub_checks": s["sub_checks"],
        "n_leaves_class_p": s["P_class_p"]["n_leaves"],
        "n_leaves_class_s": s["S_class_s"]["n_leaves"],
        "n_discrete_class_s": s["S_class_s"]["n_discrete"],
        "n_continuous_class_s": s["S_class_s"]["n_continuous"],
        "pass": s["verdict"] == "PASS"}
    log(f"SELF-TEST: {s['verdict']} "
        f"(Class-P {s['P_class_p']['n_leaves']:,} leaves, "
        f"Class-S {s['S_class_s']['n_leaves']:,} leaves)")

    # ---- CERTIFICATION (the real run, with check C) ------------------------
    log(f"CERTIFY: candidate vs reference @ D, re-deriving {HOURS}h ...")
    c = CW.certify(CAND, REF, D, HOURS, "forward", True, OUT)
    (OUT / "warmstart_cert.json").write_text(json.dumps(c, indent=1))
    rep["certification"] = c
    log(f"CERTIFY: {c['verdict']}  failed={c['failed_checks']}")

    # ---- NEGATIVE CONTROLS -------------------------------------------------
    negs: dict = {}
    for name, fn, where, do_rd in NEGATIVES:
        log(f"NEGATIVE {name} ...")
        mc = OUT / f"neg_{name}_cand.json"
        info = write_mutated(CAND, mc, fn)
        mr = REF
        if where == "both":
            mr = OUT / f"neg_{name}_ref.json"
            write_mutated(REF, mr, fn)
        latch = preexisting_latches(mc)
        try:
            r = CW.certify(mc, mr, D, HOURS, "forward", do_rd, OUT)
            verdict, failed = r["verdict"], r["failed_checks"]
            pp = pinpoints(r)
            crd = r.get("C_rederive", {})
        except BSM.StateRefuse as e:
            verdict, failed, pp, crd = "REFUSED", ["A_envelope"], [e.reason], {}
        ok = verdict == "FAIL" and bool(pp)
        if name.startswith("NC7"):
            # the sensitivity control is only satisfied if check C ITSELF fired
            ok = ok and crd.get("ok") is False
        negs[name] = {
            "injected": info,
            "file": str(mc),
            "resigned_fresh_fnv64": True,
            "preexisting_RECON8f_latches": latch,
            "certifier_verdict": verdict,
            "failed_sub_checks": failed,
            "pinpointed": pp[:6],
            "control_ok": ok,
        }
        if do_rd and crd:
            streams = crd.get("streams", [])
            negs[name]["C_rederive_would_have_caught_it"] = (
                crd.get("ok") is False)
            negs[name]["C_rederive_stream_bands"] = {
                s0["stream"]: {"max_abs_diff": s0["max_abs_diff"],
                               "pass": s0["pass"]} for s0 in streams}
        log(f"  {name}: {verdict} failed={failed} "
            f"control_ok={negs[name]['control_ok']}")
        for p in pp[:2]:
            log(f"    pinpoint: {p}")

    # ---- NC6: the in-sample pre-warm refusal -------------------------------
    log("NEGATIVE NC6_in_sample_prewarm ...")
    try:
        CW.certify(CAND, REF, D, HOURS, "in_sample", False, OUT)
        negs["NC6_in_sample_prewarm"] = {
            "certifier_verdict": "PASS", "control_ok": False,
            "error": "certifier ACCEPTED a pre-warmed in-sample run"}
    except CW.InSampleWarmStartRefused as e:
        negs["NC6_in_sample_prewarm"] = {
            "injected": {"field": "mode=in_sample + warm blob @ D != t0",
                         "note": "WARMSTART_DESIGN §0 inverted finding"},
            "certifier_verdict": "REFUSED",
            "refuse_class": "InSampleWarmStartRefused",
            "refuse_reason": str(e).splitlines()[0],
            "control_ok": True}
    log(f"  NC6: {negs['NC6_in_sample_prewarm']['certifier_verdict']}")

    rep["negative_controls"] = negs
    rep["negative_controls_all_ok"] = all(v["control_ok"]
                                          for v in negs.values())
    rep["pass"] = bool(rep["self_test"]["pass"]
                       and c["verdict"] == "PASS"
                       and rep["negative_controls_all_ok"])
    rep["runtime_s"] = round(time.time() - T0, 1)
    (OUT / "ws_gate.json").write_text(json.dumps(rep, indent=1))
    log("=== FMA3-RECON-9-WS ===")
    log(f"self-test={rep['self_test']['verdict']}  "
        f"certification={c['verdict']}  "
        f"negatives_all_ok={rep['negative_controls_all_ok']}")
    log(f"VERDICT: {'PASS' if rep['pass'] else 'FAIL'} "
        f"(-> {OUT / 'ws_gate.json'}, {rep['runtime_s']}s)")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
