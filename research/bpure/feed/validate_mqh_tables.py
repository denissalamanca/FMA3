"""validate_mqh_tables.py — READ BACK the static tables that were codegen'd
into mt5/ea/Include/Book/SwapEurq.mqh and prove they still encode exactly the
python tables that the bit-equal gate validated.

A compile of 0/0 says nothing about whether SE_SYM_QUOT[k] points at the right
currency: a wrong index compiles perfectly and silently mis-prices one symbol
forever.  This parses the HEADER AS SHIPPED and re-derives, per symbol:
asset class, base ccy, quote ccy, markup, EUR cross — and per currency: the
full policy-rate step function — comparing against swap_eurq_generator's
tables (themselves drift-guarded against the live NSF5 source).

  python3 validate_mqh_tables.py            # PASS/FAIL + json
  python3 validate_mqh_tables.py --negative  # NEGATIVE CONTROL: corrupt one
                                             # table entry in a COPY of the
                                             # header; the check must FAIL and
                                             # name the symbol/currency.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swap_eurq_generator as G  # noqa: E402

MQH = HERE.parents[2] / "mt5" / "ea" / "Include" / "Book" / "SwapEurq.mqh"
CCY = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "NOK", "SEK",
       "XAU", "XAG", "XPT", "XTI", "XBR", "XNG"]
AC = {0: "fx", 1: "metal", 2: "index", 3: "crypto"}


def _arr(txt: str, name: str) -> list[str]:
    m = re.search(re.escape(name) + r"\s*\[[^\]]*\]\s*=\s*\{(.*?)\}\s*;",
                  txt, re.S)
    assert m, f"{name} not found in {MQH.name}"
    return [v.strip().strip('"') for v in m.group(1).split(",")]


def check(mqh_text: str) -> tuple[bool, list[str]]:
    bad: list[str] = []
    sym = _arr(mqh_text, "SE_SYM")
    ac = [int(v) for v in _arr(mqh_text, "SE_SYM_AC")]
    base = [int(v) for v in _arr(mqh_text, "SE_SYM_BASE")]
    quot = [int(v) for v in _arr(mqh_text, "SE_SYM_QUOT")]
    mkup = [float(v) for v in _arr(mqh_text, "SE_SYM_MKUP")]
    cross = _arr(mqh_text, "SE_CROSS")
    qcross = [int(v) for v in _arr(mqh_text, "SE_QUOT_CROSS")]

    want_syms = G.SYMBOLS_BH + ["AUDUSD", "NZDUSD"]
    if sym != want_syms:
        bad.append(f"SE_SYM order/content != python symbol table: {sym}")
        return False, bad
    if cross != G.CROSSES_BH:
        bad.append(f"SE_CROSS != exporter cross order: {cross}")

    for k, s in enumerate(sym):
        p_ac, p_base, p_quote = G.INSTR[s]
        if AC[ac[k]] != p_ac:
            bad.append(f"{s}: asset_class {AC[ac[k]]} != {p_ac}")
        if p_ac in ("fx", "metal"):
            if base[k] < 0 or CCY[base[k]] != p_base:
                bad.append(f"{s}: base ccy id {base[k]} != {p_base}")
        if quot[k] < 0 or CCY[quot[k]] != p_quote:
            bad.append(f"{s}: quote ccy id {quot[k]} != {p_quote}")
        want_mk = G.FX_MARKUP_OVR.get(s, G.FX_MARKUP)
        if mkup[k] != want_mk:
            bad.append(f"{s}: markup {mkup[k]} != {want_mk}")
        # the cross the header will use for this symbol's eurq
        xi = qcross[quot[k]] if quot[k] >= 0 else -1
        want_x = -1 if p_quote == "EUR" else G.CROSSES_BH.index(G.EUR_CROSS[p_quote])
        if xi != want_x:
            got = cross[xi] if xi >= 0 else "EUR(1.0)"
            bad.append(f"{s}: eurq cross {got} != "
                       f"{G.EUR_CROSS.get(p_quote, 'EUR(1.0)')}")

    # policy-rate step functions
    rn = dict(re.findall(r"SE_RN\[SE_(\w+)\]\s*=\s*(\d+)\s*;", mqh_text))
    rows = re.findall(
        r"SE_RDATE\[SE_(\w+)\]\[(\d+)\]\s*=\s*\(long\)D'([\d.]+)';\s*"
        r"SE_RRATE\[SE_\w+\]\[\d+\]\s*=\s*([-\d.e+]+);", mqh_text)
    got: dict[str, list] = {}
    for c, i, d, r in rows:
        got.setdefault(c, []).append((int(i), d.replace(".", "-"), float(r)))
    for c, want in G.POLICY_RATES.items():
        g = sorted(got.get(c, []))
        if int(rn.get(c, -1)) != len(want):
            bad.append(f"policy {c}: SE_RN {rn.get(c)} != {len(want)}")
        if [(d, r) for _, d, r in g] != [(d, float(r)) for d, r in want]:
            bad.append(f"policy {c}: step table differs from python "
                       f"({len(g)} rows read)")
    return (len(bad) == 0), bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--negative", action="store_true")
    ap.add_argument("--report", default=str(HERE / "mqh_tables_check.json"))
    args = ap.parse_args()

    txt = MQH.read_text()
    ok, bad = check(txt)
    rep = {"mqh": str(MQH), "PASS": ok, "findings": bad,
           "tables_drift_guard": G.verify_tables()}
    print(f"MQH TABLE READBACK: {'PASS' if ok else 'FAIL'} "
          f"({len(bad)} findings)")
    for b in bad[:10]:
        print("   ", b)

    if args.negative:
        # NEGATIVE CONTROL 1: point USDJPY's quote ccy at CHF (id 4) instead of
        # JPY (id 3) — a one-character table typo that compiles perfectly.
        q = _arr(txt, "SE_SYM_QUOT")
        k = (G.SYMBOLS_BH + ["AUDUSD", "NZDUSD"]).index("USDJPY")
        q2 = list(q)
        q2[k] = "4"
        m = re.search(r"(SE_SYM_QUOT\[SE_NSYM\]\s*=\s*)\{.*?\}", txt, re.S)
        t2 = txt[:m.start()] + m.group(1) + "{" + ", ".join(q2) + "}" + \
            txt[m.end():]
        ok2, bad2 = check(t2)
        # NEGATIVE CONTROL 2: corrupt one JPY policy-rate step
        t3 = txt.replace("SE_RRATE[SE_JPY][2] = 0.25;",
                         "SE_RRATE[SE_JPY][2] = 0.35;")
        assert t3 != txt, "NC2 anchor not found"
        ok3, bad3 = check(t3)
        rep["negative_control_1"] = {
            "injected": "SE_SYM_QUOT[USDJPY] = CHF (was JPY)",
            "FAILED_as_required": not ok2, "findings": bad2}
        rep["negative_control_2"] = {
            "injected": "SE_RRATE[SE_JPY][2] 0.25 -> 0.35",
            "FAILED_as_required": not ok3, "findings": bad3}
        print(f"NEG-CONTROL 1 (USDJPY quote ccy -> CHF): "
              f"{'FAILED as required' if not ok2 else 'DID NOT FAIL — BAD'}")
        for b in bad2:
            print("   ", b)
        print(f"NEG-CONTROL 2 (JPY policy step 0.25 -> 0.35): "
              f"{'FAILED as required' if not ok3 else 'DID NOT FAIL — BAD'}")
        for b in bad3:
            print("   ", b)
        assert not ok2 and not ok3, "NEGATIVE CONTROL DID NOT FAIL"

    Path(args.report).write_text(json.dumps(rep, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
