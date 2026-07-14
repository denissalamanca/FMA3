"""S0 feed probe judge — compare a FeedProbe.mq5 CSV against the golden.

Usage:
    python3 judge_feedprobe.py <golden.csv> <probe.csv> [out.json]
    python3 judge_feedprobe.py --selftest [golden.csv]     # judge(golden,golden)

Both files share the format written by FeedProbe.mq5 / export_probe_golden.py:
    #meta,mode=...,window_start=...,window_end=...,nsym=...
    #depth,<sym>,select=..,done=..,earliest=..,bars2020=..,bars_window=..,misaligned=..
    #cols,ts,<sym1>,...
    <ts>,<0/1>,...

Checks (verdicts):
  SYMBOLS : identical symbol set + column order.
  GRID    : identical union-grid minute set (lists first divergences each way).
  HAS_BAR : per-symbol has_bar equality on the common grid (per-symbol
            bar-count table + first divergent minutes).
  DEPTH   : per symbol, probe earliest M1 bar <= golden earliest + 1 day slack
            (M1 history reaches 2020-01-02); select/done flags; misaligned=0.
  OVERALL : PASS iff SYMBOLS+GRID+HAS_BAR+DEPTH all PASS. Exit code 0/1.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")
DEPTH_SLACK = 86400          # 1 day: golden earliest is the requirement anchor
FIRST_N = 10                 # divergences listed per section


def _ts(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M")


def parse(path: Path) -> dict:
    meta, depth, cols, ts_list, rows = {}, {}, None, [], []
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("#meta,"):
                for kv in line[6:].split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        meta[k] = v
            elif line.startswith("#depth,"):
                p = line.split(",")
                sym = p[1]
                d = {}
                for kv in p[2:]:
                    k, v = kv.split("=", 1)
                    d[k] = int(v)
                depth[sym] = d
            elif line.startswith("#cols,"):
                p = line.split(",")
                assert p[1] == "ts", f"bad #cols header in {path}"
                cols = p[2:]
            else:
                p = line.split(",")
                ts_list.append(int(p[0]))
                rows.append([c == "1" for c in p[1:]])
    assert cols is not None, f"no #cols header in {path}"
    for r in rows:
        assert len(r) == len(cols), f"ragged row in {path}"
    return {"path": str(path), "meta": meta, "depth": depth, "cols": cols,
            "ts": ts_list, "rows": rows}


def judge(golden_path: Path, probe_path: Path) -> dict:
    g = parse(golden_path)
    p = parse(probe_path)
    rep = {"golden": g["path"], "probe": p["path"],
           "golden_mode": g["meta"].get("mode"), "probe_mode": p["meta"].get("mode")}

    # ---- SYMBOLS ----
    sym_ok = g["cols"] == p["cols"]
    rep["symbols"] = {
        "pass": sym_ok,
        "golden_only": sorted(set(g["cols"]) - set(p["cols"])),
        "probe_only": sorted(set(p["cols"]) - set(g["cols"])),
        "order_mismatch": (not sym_ok and set(g["cols"]) == set(p["cols"]))}
    print(f"SYMBOLS : {'PASS' if sym_ok else 'FAIL'} "
          f"(golden {len(g['cols'])}, probe {len(p['cols'])})")
    if not sym_ok:
        print(f"  golden-only: {rep['symbols']['golden_only']}")
        print(f"  probe-only : {rep['symbols']['probe_only']}")

    # ---- GRID ----
    gset, pset = set(g["ts"]), set(p["ts"])
    miss = sorted(gset - pset)      # golden minutes the probe lacks
    extra = sorted(pset - gset)     # probe minutes not in golden
    grid_ok = not miss and not extra and g["ts"] == sorted(g["ts"]) \
        and p["ts"] == sorted(p["ts"])
    rep["grid"] = {
        "pass": grid_ok,
        "golden_minutes": len(g["ts"]), "probe_minutes": len(p["ts"]),
        "missing_in_probe": len(miss), "extra_in_probe": len(extra),
        "first_missing": [(m, _ts(m)) for m in miss[:FIRST_N]],
        "first_extra": [(m, _ts(m)) for m in extra[:FIRST_N]]}
    print(f"GRID    : {'PASS' if grid_ok else 'FAIL'} "
          f"(golden {len(g['ts']):,} min, probe {len(p['ts']):,} min, "
          f"missing {len(miss)}, extra {len(extra)})")
    for m, t in rep["grid"]["first_missing"]:
        print(f"  probe MISSING minute {m} = {t}")
    for m, t in rep["grid"]["first_extra"]:
        print(f"  probe EXTRA   minute {m} = {t}")

    # ---- HAS_BAR (on the common grid, common symbols) ----
    common_ts = sorted(gset & pset)
    gi = {t: i for i, t in enumerate(g["ts"])}
    pi = {t: i for i, t in enumerate(p["ts"])}
    common_syms = [s for s in g["cols"] if s in set(p["cols"])]
    gk = {s: g["cols"].index(s) for s in common_syms}
    pk = {s: p["cols"].index(s) for s in common_syms}
    has_ok = True
    per_sym = {}
    print("HAS_BAR per-symbol (common grid "
          f"{len(common_ts):,} min, {len(common_syms)} syms):")
    print(f"  {'sym':<7} {'gold_bars':>9} {'probe_bars':>10} "
          f"{'mismatch':>8}  first divergences")
    for s in common_syms:
        gcol = gk[s]; pcol = pk[s]
        mism = [t for t in common_ts
                if g["rows"][gi[t]][gcol] != p["rows"][pi[t]][pcol]]
        gbars = sum(1 for t in common_ts if g["rows"][gi[t]][gcol])
        pbars = sum(1 for t in common_ts if p["rows"][pi[t]][pcol])
        ok = not mism
        has_ok = has_ok and ok
        per_sym[s] = {"golden_bars": gbars, "probe_bars": pbars,
                      "mismatches": len(mism),
                      "first": [(t, _ts(t),
                                 "golden" if g["rows"][gi[t]][gcol] else "probe")
                                for t in mism[:5]]}
        flag = "" if ok else " <-- " + "; ".join(
            f"{t}({side} has bar)" for t, _, side in per_sym[s]["first"])
        print(f"  {s:<7} {gbars:>9} {pbars:>10} {len(mism):>8}{flag}")
    has_ok = has_ok and sym_ok        # a lost symbol is a has_bar failure too
    rep["has_bar"] = {"pass": has_ok, "per_symbol": per_sym}
    print(f"HAS_BAR : {'PASS' if has_ok else 'FAIL'}")

    # ---- DEPTH ----
    depth_ok = True
    rows = []
    print("DEPTH   per-symbol (probe earliest M1 vs golden, slack "
          f"{DEPTH_SLACK}s):")
    print(f"  {'sym':<7} {'golden_earliest':<17} {'probe_earliest':<17} "
          f"{'bars2020 g/p':>13} sel done misal ok")
    for s in common_syms:
        gd, pd = g["depth"].get(s, {}), p["depth"].get(s, {})
        ge, pe = gd.get("earliest", 0), pd.get("earliest", 0)
        ok = (pe > 0 and ge > 0 and pe <= ge + DEPTH_SLACK
              and pd.get("select", 0) == 1 and pd.get("done", 0) == 1
              and pd.get("misaligned", 1) == 0)
        depth_ok = depth_ok and ok
        rows.append({"sym": s, "golden_earliest": ge, "probe_earliest": pe,
                     "golden_bars2020": gd.get("bars2020"),
                     "probe_bars2020": pd.get("bars2020"),
                     "select": pd.get("select"), "done": pd.get("done"),
                     "misaligned": pd.get("misaligned"), "pass": ok})
        print(f"  {s:<7} {_ts(ge) if ge else '-':<17} "
              f"{_ts(pe) if pe else '-':<17} "
              f"{str(gd.get('bars2020', '-')) + '/' + str(pd.get('bars2020', '-')):>13} "
              f"{pd.get('select', '-'):>3} {pd.get('done', '-'):>4} "
              f"{pd.get('misaligned', '-'):>5} {'PASS' if ok else 'FAIL'}")
    depth_ok = depth_ok and sym_ok
    rep["depth"] = {"pass": depth_ok, "per_symbol": rows}
    print(f"DEPTH   : {'PASS' if depth_ok else 'FAIL'}")

    overall = sym_ok and grid_ok and has_ok and depth_ok
    rep["overall"] = "PASS" if overall else "FAIL"
    print(f"OVERALL : {rep['overall']}  (SYMBOLS {sym_ok} GRID {grid_ok} "
          f"HAS_BAR {has_ok} DEPTH {depth_ok})")
    return rep


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        gpath = Path(argv[1]) if len(argv) > 1 else \
            COMMON_FILES / "FMA3_feedprobe_golden.csv"
        rep = judge(gpath, gpath)
        ok = rep["overall"] == "PASS"
        print(f"SELF-TEST judge(golden,golden): {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    if len(argv) < 2:
        print(__doc__)
        return 2
    rep = judge(Path(argv[0]), Path(argv[1]))
    if len(argv) > 2:
        Path(argv[2]).write_text(json.dumps(rep, indent=1))
        print(f"report written: {argv[2]}")
    return 0 if rep["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
