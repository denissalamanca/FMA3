#!/usr/bin/env python3
"""Mechanical verbatim-ness check for the FableFederation_V1 v7 transplant
(TRANSPLANT_V7.md §5). Run before every G1 submission and in the build loop.

Verifies against the READ-ONLY v7 source (NSF5 FableMultiAsset1_V7.mq5):

  * every v7 input declaration (source lines 57-115, 34 of them) appears in
    FableFederation_V1.mq5 with byte-identical (type, name, default). Input
    COMMENTS, declaration ORDER and `input group` headers are ALLOWLISTED
    display-only deltas (TRANSPLANT_V7.md par.2.1 amendment, 2026-07-10):
    presets bind to names, gate G1 parity binds to defaults, and MQL5 input
    comments/groups are display metadata the compiler strips - no logic impact;
  * Include/FMA3/V7Core.mqh differs from source lines 117-1089 ONLY by the
    allowlisted removals (4 file-name defines + the SEAM-1 preEquity line);
  * the OnInit/OnDeinit/OnTick block differs from source lines 1091-end ONLY by
    the allowlisted removals (2 decisions-CSV opens, health CSV name, health
    row tag, the OnDeinit closing braces);
  * every ADDED line is F3-marked (contains F3/fma3_fed_/F1.00, or is a blank/
    comment line inside a marked seam) - no unmarked new code can hide.

Exit 0 = transplant clean. Any other diff = a defect against gate G1.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

V7 = Path("/Users/dsalamanca/vs_env/NewStrategyFable5/mt5/ea/FableMultiAsset1_V7.mq5")
EA_DIR = Path("/Users/dsalamanca/vs_env/FableMultiAssets3/mt5/ea")
MAIN = EA_DIR / "FableFederation_V1.mq5"
CORE = EA_DIR / "Include/FMA3/V7Core.mqh"

ALLOWED_REMOVALS_CORE = {
    '#define  STATE_FILE  "portfolio_v7_state.csv"',
    '#define  HB_FILE     "portfolio_v7_heartbeat.csv"',
    '#define  REJ_FILE    "portfolio_v7_rejects.csv"   // P2: order-reject retcode/comment log (live-only)',
    '#define  SKIP_FILE   "portfolio_v7_skips.csv"     // P1: disconnect / insufficient-history skip log (live-only)',
    "   double preEquity=AccountInfoDouble(ACCOUNT_EQUITY);",
    # [F3 CHANGE 2+3] exec hardening (2026-07-10 changeset): the three ExecSleeve
    # order lines whose same-direction adds/opens now route through the F3-marked
    # F3_SendAdd seam (reject-backoff hold + account-aggregate volume clamp,
    # FMA3/V34Exec.mqh). Closes/reduces keep the verbatim path; inert at defaults.
    "   else if(sgnP==0)                         OpenDir(sym,desired);",
    "   else if(sgnT!=sgnP){ CloseAll(sym,magic); OpenDir(sym,desired); }",
    "      if(dv>0) OpenDir(sym,sgnT*dv);",
}
ALLOWED_REMOVALS_HANDLERS = {
    '         g_logh=FileOpen("portfolio_v7_decisions.csv",',
    '   int h=FileOpen("portfolio_v7_health.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,\',\');',
    '      FileWrite(h,"7.00",DoubleToString(InpRisk,1),IntegerToString(g_nSplit),',
    "   } }",
}
ADD_MARKERS = ("F3", "fma3_fed_", "F1.00")
# Exact seam lines that carry no F3 marker of their own (continuations of
# marked seam statements - see TRANSPLANT_V7.md par.3):
ALLOWED_ADDITIONS = {
    "                                    : AccountInfoDouble(ACCOUNT_EQUITY);",  # SEAM 1 line 2
    "   if(!InpEnableV7){ for(int n=0;n<N_SLEEVE;n++) W[n]=0.0;",                # SEAM 4.1
    "   }",                                                                      # OnDeinit re-brace
    "}",                                                                         # (SEAM 4.8)
}


# `input <type> <name> = <default>;` - default captured byte-exact up to the
# first ';' (no v7 default contains one). `input group "..."` lines don't match.
INPUT_RE = re.compile(r"^input\s+(\w+)\s+(\w+)\s*=\s*(.+?)\s*;")


def parse_inputs(lines: list) -> dict:
    """name -> (type, default-literal) for every input declaration."""
    out = {}
    for l in lines:
        m = INPUT_RE.match(l)
        if m:
            out[m.group(2)] = (m.group(1), m.group(3))
    return out


def added_line_ok(line: str) -> bool:
    if not line.strip():
        return True
    if line in ALLOWED_ADDITIONS:
        return True
    if any(m in line for m in ADD_MARKERS):
        return True
    # pure comment lines belonging to a marked seam block
    return line.lstrip().startswith("//")


def check_block(name: str, ref: list, out: list, allowed_removals: set) -> int:
    bad = 0
    for line in difflib.unified_diff(ref, out, lineterm="", n=0):
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("-"):
            if line[1:] not in allowed_removals:
                print(f"[{name}] UNALLOWED removal: {line[1:]!r}")
                bad += 1
        elif line.startswith("+"):
            if not added_line_ok(line[1:]):
                print(f"[{name}] UNMARKED addition: {line[1:]!r}")
                bad += 1
    return bad


def main() -> int:
    src = V7.read_text().splitlines()
    main_txt = MAIN.read_text().splitlines()
    core_txt = CORE.read_text().splitlines()

    bad = 0

    # 1. v7 input declarations: (type, name, default) byte-equal. Comments,
    #    order and `input group` headers are allowlisted display-only deltas
    #    (TRANSPLANT_V7.md par.2.1 amendment) - presets bind to NAMES, gate G1
    #    parity binds to DEFAULTS, so those two are what the check pins.
    ref_inputs = parse_inputs(src[56:115])         # lines 57..115 (the input lines)
    main_inputs = parse_inputs(main_txt)
    if len(ref_inputs) != 34:                      # 24 params + 10 symbol names
        print(f"[inputs] expected 34 v7 input declarations in the source, parsed {len(ref_inputs)}")
        bad += 1
    for name, (typ, dflt) in ref_inputs.items():
        if name not in main_inputs:
            print(f"[inputs] v7 input MISSING from the main EA: {name}")
            bad += 1
        elif main_inputs[name] != (typ, dflt):
            print(f"[inputs] v7 input CHANGED: {name}: source ({typ}, {dflt!r}) "
                  f"vs EA {main_inputs[name]!r}")
            bad += 1

    # 2. V7Core.mqh vs source lines 117-1089 (strip the 12-line FMA3 header)
    core_ref = src[116:1089]
    hdr_end = next(i for i, l in enumerate(core_txt)
                   if l.startswith("//===="))      # first v7 banner line
    bad += check_block("V7Core", core_ref, core_txt[hdr_end:], ALLOWED_REMOVALS_CORE)

    # 3. handlers block vs source lines 1091-end
    handlers_ref = src[1090:]
    idx = next(i for i, l in enumerate(main_txt) if l == "// INIT") - 1
    bad += check_block("handlers", handlers_ref, main_txt[idx:],
                       ALLOWED_REMOVALS_HANDLERS)

    if bad == 0:
        print("TRANSPLANT CLEAN: only allowlisted removals + F3-marked additions.")
        return 0
    print(f"TRANSPLANT DIRTY: {bad} violation(s) - a defect against gate G1.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
