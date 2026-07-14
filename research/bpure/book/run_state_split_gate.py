"""run_state_split_gate.py — the Track-B state-serializer GATE
(RECON-8d warm-start pattern, python mirror of BookState.mqh).

WHAT IT PROVES (all MEASURED, written to book_state_gate.json):
  G1  BASELINE: the uninterrupted S1 mirror run still PASSES R1 vs the
      golden (regression guard for the sim edits) and serializes its
      end state (endBASE).
  G2  SPLIT: a run that stops at the mid-grid boundary D = 2022-06-30
      23:00 UTC (epoch 1656630000, first grid stamp >= D) and
      serializes the COMPLETE ledger; a FRESH mirror restores it
      (validating load + continuity guard) and continues to the end.
      The resumed run's emitted stream tail must be BITWISE IDENTICAL
      (exact %.17g strings) to the uninterrupted baseline's tail, and
      the resumed end state byte-identical to endBASE.
  G3  TORN-WRITE UNIT TESTS on the boundary file:
        t_pass     untampered file loads + guard passes (control)
        t_torn     truncated file -> refuse (eof marker)
        t_flip     payload bit-flip, stale fnv -> refuse (checksum)
        t_anchor   continuity a_first * 1.01, FRESH trailer -> refuse
                   (A-ANCHOR bit-equality guard)
        t_splice   CONSISTENT re-base: sampler-a first_v AND continuity
                   a_first * 1.01, fresh trailer — passes the anchor
                   equality, must trip the J-SPLICE REFUSE latch (the
                   silent mis-weighting scenario the serializer kills)

Usage (python >= 3.13):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && \
    /usr/local/bin/python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/book/run_state_split_gate.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))

import book_state_mirror as BSM  # noqa: E402

PY = "/usr/local/bin/python3"
SIM = HERE / "book_orchestrator_sim.py"
D_EPOCH = 1656630000                       # 2022-06-30 23:00:00 UTC

BASE_CSV = OUT / "FMA3_book_mirror_actual.csv"
BASE_JSON = HERE / "book_mirror_parity.json"
TAIL_CSV = OUT / "FMA3_book_mirror_tail.csv"
TAIL_JSON = HERE / "book_state_resume_parity.json"
STATE_D = OUT / "FMA3_book_state_D.json"
END_BASE = OUT / "FMA3_book_state_endBASE.json"
END_RESUME = OUT / "FMA3_book_state_endRESUME.json"
GATE_JSON = HERE / "book_state_gate.json"

T0 = time.time()


def log(m):
    print(f"[gate {time.time() - T0:7.1f}s] {m}", flush=True)


def run_sim(args: list[str], tag: str) -> float:
    t = time.time()
    log(f"{tag}: {PY} {SIM.name} {' '.join(args)}")
    r = subprocess.run([PY, str(SIM)] + args, cwd=FMA2 / "research")
    dt = time.time() - t
    if r.returncode != 0:
        raise SystemExit(f"{tag} FAILED rc={r.returncode}")
    log(f"{tag} done ({dt:.1f}s)")
    return round(dt, 1)


# ---------------------------------------------------------------- tamper
def payload_of(text: str) -> str:
    mp = text.rfind(BSM.FNV_MARK)
    assert mp > 0, "trailer missing"
    return text[:mp]


def tamper_number(s: str, from_pos: int, key: str, mul: float) -> str:
    pat = f'"{key}": '
    p = s.find(pat, from_pos)
    assert p > 0, f"key {key} not found"
    v0 = p + len(pat)
    v1 = v0
    while s[v1] not in ",}]":
        v1 += 1
    v = float(s[v0:v1])
    return s[:v0] + BSM.f17(v * mul) + s[v1:]


def expect_refuse(path: Path, want: str, do_guard: bool) -> str:
    try:
        st = BSM.load_state_file(path)
        if do_guard:
            BSM.validate_continuity(st)
    except BSM.StateRefuse as e:
        assert want in e.reason, f"want '{want}' in refuse reason: {e.reason}"
        return e.reason
    raise AssertionError(f"file {path.name} LOADED (wanted {want} refuse)")


def unit_tests() -> dict:
    text = STATE_D.read_text(encoding="ascii")
    payload = payload_of(text)
    res = {}

    # t_pass — control: untampered file loads and the guard passes
    st = BSM.load_state_file(STATE_D)
    rc = BSM.validate_continuity(st)
    res["t_pass"] = {"ok": True, "j": rc["j"],
                     "a_first": rc["a_first"], "b_first": rc["b_first"]}
    log(f"t_pass: guard PASS (j={rc['j']!r})")

    tmp = OUT / "FMA3_book_state_tamper.json"

    # t_torn — truncated file (no eof marker)
    tmp.write_text(text[:-60], encoding="ascii")
    res["t_torn"] = {"refused": True,
                     "reason": expect_refuse(tmp, "TORN", False)}
    log(f"t_torn: {res['t_torn']['reason']}")

    # t_flip — flip one payload char, keep the stale fnv
    fp = text.find('"b_eqc": ')
    assert fp > 0
    cp = fp + 12
    flipped = text[:cp] + ("2" if text[cp] == "1" else "1") + text[cp + 1:]
    tmp.write_text(flipped, encoding="ascii")
    res["t_flip"] = {"refused": True,
                     "reason": expect_refuse(tmp, "CHECKSUM", False)}
    log(f"t_flip: {res['t_flip']['reason']}")

    # t_anchor — continuity a_first * 1.01, FRESH (valid) trailer
    t5 = tamper_number(payload, payload.find('"continuity": {'),
                       "a_first", 1.01)
    tmp.write_text(BSM.with_trailer(t5), encoding="ascii")
    res["t_anchor"] = {"refused": True,
                       "reason": expect_refuse(tmp, "A-ANCHOR", True)}
    log(f"t_anchor: {res['t_anchor']['reason']}")

    # t_splice — CONSISTENT 1% re-base (sampler first_v + anchor):
    # anchor equality passes, the j-splice latch MUST fire
    t6 = tamper_number(payload, payload.find('"samplers": {"a": '),
                       "first_v", 1.01)
    t6 = tamper_number(t6, t6.find('"continuity": {'), "a_first", 1.01)
    tmp.write_text(BSM.with_trailer(t6), encoding="ascii")
    res["t_splice"] = {"refused": True,
                       "reason": expect_refuse(tmp, "J-SPLICE", True)}
    log(f"t_splice: {res['t_splice']['reason']}")
    tmp.unlink()
    return res


# ------------------------------------------------------------------ main
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # --reuse-baseline / --reuse-save: reuse artifacts already on disk
    # (SAVE-side outputs are loader-independent — legitimate when only
    # load-side code changed since they were produced)
    reuse_base = "--reuse-baseline" in sys.argv[1:]
    reuse_save = "--reuse-save" in sys.argv[1:]
    rep: dict = {"gate": "FMA3 Track-B state-serializer split gate",
                 "boundary_epoch": D_EPOCH,
                 "boundary_utc": "2022-06-30 23:00:00",
                 "reused_baseline": reuse_base, "reused_save": reuse_save}

    # G1 baseline (uninterrupted) + end-state
    if reuse_base and BASE_CSV.exists() and END_BASE.exists():
        log("G1 baseline: REUSING existing artifacts")
        rep["t_baseline_s"] = 0.0
    else:
        rep["t_baseline_s"] = run_sim([f"--save-end={END_BASE}"], "G1 baseline")
    base_parity = json.loads(BASE_JSON.read_text())
    assert base_parity["pass"], "G1: baseline R1 verdict FAILED"
    rep["baseline_r1_pass"] = True
    rep["baseline_max_abs_diff"] = base_parity["max_abs_diff"]
    rep["baseline_rows"] = base_parity["rows_actual"]

    # G2a split run: save at D and stop
    if reuse_save and STATE_D.exists():
        log("G2a split-save: REUSING existing state file")
        rep["t_split_save_s"] = 0.0
    else:
        rep["t_split_save_s"] = run_sim(
            [f"--save-at={D_EPOCH}", f"--state={STATE_D}"], "G2a split-save")
    st_d = BSM.load_state_file(STATE_D)
    rows_offset = int(st_d["glue"]["total_rows"])
    rep["state_file_bytes"] = STATE_D.stat().st_size
    rep["rows_at_save"] = rows_offset
    rep["save_h1_last_ts"] = int(st_d["glue"]["h1_last_ts"])
    rep["save_j"] = st_d["continuity"]["j"]
    log(f"G2a: state {STATE_D.name} ({rep['state_file_bytes']:,} bytes, "
        f"rows_offset {rows_offset:,}, h1_last {rep['save_h1_last_ts']})")

    # G3 torn-write / refuse-latch unit tests (before the long resume run)
    rep["unit_tests"] = unit_tests()

    # G2b resume run: fresh mirror + load + continue to the end
    rep["t_resume_s"] = run_sim(
        [f"--load={STATE_D}", f"--save-end={END_RESUME}",
         f"--tail-csv={TAIL_CSV}"], "G2b resume")
    tail_parity = json.loads(TAIL_JSON.read_text())
    assert tail_parity["resumed"] and tail_parity["rows_offset"] == rows_offset
    rep["resume_tail_vs_golden_pass"] = bool(tail_parity["pass"])
    rep["resume_tail_max_abs_diff"] = tail_parity["max_abs_diff"]

    # ---- THE BITWISE TAIL COMPARISON (baseline vs resumed) -------------
    base_lines = BASE_CSV.read_text().splitlines()
    tail_lines = TAIL_CSV.read_text().splitlines()
    want_tail = base_lines[1 + rows_offset:]      # skip header + head rows
    got_tail = tail_lines[1:]
    rep["tail_rows_expected"] = len(want_tail)
    rep["tail_rows_resumed"] = len(got_tail)
    n_diff = 0
    first_div = None
    for i, (a, b) in enumerate(zip(want_tail, got_tail)):
        if a != b:
            if first_div is None:
                first_div = {"row": i + rows_offset, "baseline": a,
                             "resumed": b}
            n_diff += 1
    if len(want_tail) != len(got_tail):
        n_diff += abs(len(want_tail) - len(got_tail))
    rep["tail_bitwise_identical"] = (n_diff == 0)
    rep["tail_n_diff"] = n_diff
    rep["tail_first_divergence"] = first_div

    # ---- end-state byte identity ----------------------------------------
    eb = END_BASE.read_bytes()
    er = END_RESUME.read_bytes()
    rep["end_state_bytes"] = len(eb)
    rep["end_state_byte_identical"] = (eb == er)

    ok = (rep["baseline_r1_pass"] and rep["tail_bitwise_identical"]
          and rep["end_state_byte_identical"]
          and rep["resume_tail_vs_golden_pass"]
          and all(v.get("ok", v.get("refused", False))
                  for v in rep["unit_tests"].values()))
    rep["pass"] = bool(ok)
    rep["runtime_s"] = round(time.time() - T0, 1)
    GATE_JSON.write_text(json.dumps(rep, indent=1))
    log("=== STATE-SERIALIZER GATE ===")
    log(f"tail rows {rep['tail_rows_resumed']:,} vs expected "
        f"{rep['tail_rows_expected']:,} | bitwise_identical="
        f"{rep['tail_bitwise_identical']} | end-state byte-identical="
        f"{rep['end_state_byte_identical']} ({rep['end_state_bytes']:,} B)")
    if first_div:
        log(f"FIRST DIVERGENCE: {first_div}")
    log(f"VERDICT: {'PASS' if ok else 'FAIL'} (report -> {GATE_JSON}, "
        f"{rep['runtime_s']}s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
