#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FMA3 UNIT 3 — reconcile_symbol_meta.py : THE live-vs-record metadata judge.

Reconciles the LIVE broker SymbolInfo dump (SymbolMetaProbe.mq5 ->
Common/Files/FMA3_symbol_meta.csv, 22 columns) against the AUTHORITATIVE
record/engine assumptions (symbol_meta_reference.json, UNIT 2) for the FULL
37 x N (symbol x field) matrix.  NO intersection: both sides MUST cover all
37 core.ALL symbols; a missing symbol on either side is a HARD error, never a
silent skip (Antigravity lesson).

Per (symbol, field) the judge classifies drift and — critically — separates
the HARMLESS DE40-precision class (R2) from the CATASTROPHIC scale/contract
classes (block).  A scale/contract drift misread as precision is the worst
possible failure this file exists to prevent.

DRIFT CLASSES
-------------
  MATCH            identical / within float tol (or field ignored-by-design).
  PRECISION-DRIFT  digits differ but the quote-grid MAGNITUDE is preserved
                   (point*10^digits invariant unchanged) AND contract_size
                   unchanged -> the DE40 1->2 digit case.  HANDLED by using the
                   live SYMBOL_POINT/DIGITS; engine marks unaffected -> R2.
  SCALE-DRIFT      the price-scale invariant (point*10^digits) CHANGED, i.e.
                   the numeric magnitude a lot marks against shifted (an index
                   re-quoted at 1/10, or a tick-grid rescale) -> CRITICAL:
                   marks / P&L wrong.  BLOCKS.
  CONTRACT-DRIFT   SYMBOL_TRADE_CONTRACT_SIZE != the engine's baked value ->
                   CRITICAL: lot->notional wrong, breaks position fidelity +
                   marks.  BLOCKS.
  VOLUME-DRIFT     lot_step / lot_min / lot_max differ.  Severity by direction:
                   a live grid that CANNOT represent the model's lots (coarser
                   step, larger min) -> BLOCK (quantizer diverges); a finer or
                   equal live grid -> HANDLED; a live max ceiling (ref is
                   unbounded) -> HANDLED (respect at exec).
  CCY-DRIFT        SYMBOL_CURRENCY_PROFIT != profit_ccy -> CRITICAL: eurq cross
                   / conversion wrong, marks wrong.  BLOCKS.  (base_ccy is
                   INFO-only: indices carry label bases e.g. DAX->'DAX' vs live
                   'EUR', and base_ccy drives neither marks nor eurq.)
  SWAP             swap is fully SYNTHESIZED (SwapEurq.mqh); broker
                   SYMBOL_SWAP_MODE is not read -> ignored-by-design, MATCH,
                   never blocks.
  SELECT-FAIL      SYMBOL_SELECT failed / row carries an error flag -> the
                   symbol is unavailable live -> CRITICAL: cannot feed/trade.

SEVERITY
  CRITICAL : SCALE-DRIFT, CONTRACT-DRIFT, CCY-DRIFT(profit), VOLUME-DRIFT[block],
             SELECT-FAIL, and any MISSING symbol (HARD).
  HANDLED  : PRECISION-DRIFT, VOLUME-DRIFT[compat/max], (base_ccy INFO).
  OK       : MATCH.

USAGE
  # reconcile the owner's real run:
  python3 reconcile_symbol_meta.py <FMA3_symbol_meta.csv> [symbol_meta_reference.json]
  # run the self-test + the four negative controls on synthetic data (default):
  python3 reconcile_symbol_meta.py --selftest
  # (with no CSV arg it defaults to --selftest)

The judge's reconcile() takes PARSED dicts (broker_name -> field dict) for both
sides, so it drives identically on real CSV rows and on synthetic rows built
from the reference (self-test / negative controls).
"""

import sys
import os
import csv
import json
import math

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REF = os.path.join(HERE, "symbol_meta_reference.json")

# ---- tolerances -----------------------------------------------------------
FTOL_REL = 1e-9      # relative tol for contract / point / volume doubles
FTOL_ABS = 1e-12     # absolute floor
PROD_TOL = 1e-6      # tol on the point*10^digits scale invariant

# ---- severity buckets -----------------------------------------------------
SEV_CRITICAL = "CRITICAL"
SEV_HANDLED  = "HANDLED"
SEV_OK       = "OK"

# ---- the 22 CSV columns emitted by SymbolMetaProbe.mq5 --------------------
CSV_COLUMNS = [
    "broker_name", "model_name", "SYMBOL_DIGITS", "SYMBOL_POINT",
    "SYMBOL_TRADE_TICK_SIZE", "SYMBOL_TRADE_TICK_VALUE",
    "SYMBOL_TRADE_CONTRACT_SIZE", "SYMBOL_VOLUME_MIN", "SYMBOL_VOLUME_MAX",
    "SYMBOL_VOLUME_STEP", "SYMBOL_TRADE_MODE", "SYMBOL_SWAP_MODE",
    "SYMBOL_SWAP_LONG", "SYMBOL_SWAP_SHORT", "SYMBOL_CURRENCY_BASE",
    "SYMBOL_CURRENCY_PROFIT", "SYMBOL_CURRENCY_MARGIN", "SYMBOL_MARGIN_INITIAL",
    "SYMBOL_TRADE_STOPS_LEVEL", "SYMBOL_SELECT_ok", "error", "record_feed_digits",
]


# ===========================================================================
# float helpers
# ===========================================================================
def _f(x):
    """Parse a double; None/'' -> None."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "" or s.lower() in ("none", "nan", "null"):
        return None
    return float(s)


def feq(a, b):
    """Relative-tol double equality; None==None True, None vs x False."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a == b:
        return True
    return abs(a - b) <= max(FTOL_REL * max(abs(a), abs(b)), FTOL_ABS)


def scale_prod(point, digits):
    """point * 10^digits  — the price-scale invariant (==1 for a self-
    consistent MT5 grid; a change here is a genuine value-scale shift)."""
    if point is None or digits is None:
        return None
    return point * (10.0 ** digits)


# ===========================================================================
# loaders
# ===========================================================================
def load_live_csv(path):
    """Parse FMA3_symbol_meta.csv -> {broker_name: fielddict}. Header enforced."""
    rows = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd, None)
        if header is None:
            raise ValueError("live CSV is empty")
        header = [h.strip() for h in header]
        if header != CSV_COLUMNS:
            raise ValueError(
                "live CSV header mismatch.\n  expected %d cols: %s\n  got      %d cols: %s"
                % (len(CSV_COLUMNS), CSV_COLUMNS, len(header), header))
        for raw in rd:
            if not raw or all(c.strip() == "" for c in raw):
                continue
            if len(raw) != len(CSV_COLUMNS):
                raise ValueError("live CSV row has %d cols, expected %d: %r"
                                 % (len(raw), len(CSV_COLUMNS), raw))
            r = dict(zip(CSV_COLUMNS, [c for c in raw]))
            broker = r["broker_name"].strip()
            rows[broker] = live_fields_from_csvrow(r)
    return rows


def live_fields_from_csvrow(r):
    """Normalize a raw CSV row dict into the internal live-field schema."""
    return {
        "broker_name": r["broker_name"].strip(),
        "model_name":  r["model_name"].strip(),
        "digits":      int(float(r["SYMBOL_DIGITS"])),
        "point":       _f(r["SYMBOL_POINT"]),
        "tick_size":   _f(r["SYMBOL_TRADE_TICK_SIZE"]),
        "tick_value":  _f(r["SYMBOL_TRADE_TICK_VALUE"]),
        "contract":    _f(r["SYMBOL_TRADE_CONTRACT_SIZE"]),
        "vol_min":     _f(r["SYMBOL_VOLUME_MIN"]),
        "vol_max":     _f(r["SYMBOL_VOLUME_MAX"]),
        "vol_step":    _f(r["SYMBOL_VOLUME_STEP"]),
        "trade_mode":  int(float(r["SYMBOL_TRADE_MODE"])),
        "swap_mode":   int(float(r["SYMBOL_SWAP_MODE"])),
        "ccy_base":    r["SYMBOL_CURRENCY_BASE"].strip(),
        "ccy_profit":  r["SYMBOL_CURRENCY_PROFIT"].strip(),
        "ccy_margin":  r["SYMBOL_CURRENCY_MARGIN"].strip(),
        "margin_ini":  _f(r["SYMBOL_MARGIN_INITIAL"]),
        "stops_level": int(float(r["SYMBOL_TRADE_STOPS_LEVEL"])),
        "select_ok":   int(float(r["SYMBOL_SELECT_ok"])),
        "error":       r["error"].strip(),
        "record_feed_digits": int(float(r["record_feed_digits"])),
    }


def load_reference(path):
    """Parse symbol_meta_reference.json -> (ref_by_broker, meta)."""
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    ref = {}
    for s in doc["symbols"]:
        broker = s["broker_name"]
        ref[broker] = {
            "broker_name": broker,
            "model_name":  s["model_name"],
            "role":        s.get("role"),
            "asset_class": s.get("asset_class"),
            "digits":      int(s["digits_record"]),
            "point":       float(s["point_record"]),
            "contract":    float(s["contract_size"]),
            "lot_step":    float(s["lot_step"]),
            "lot_min":     float(s["lot_min"]),
            "lot_max":     None if s.get("lot_max") is None else float(s["lot_max"]),
            "base_ccy":    s.get("base_ccy"),
            "profit_ccy":  s.get("profit_ccy"),
            "margin_account_ccy": s.get("margin_account_ccy"),
            "eurq_cross":  s.get("eurq_cross"),
            "swap_generated": s.get("swap_generated"),
        }
    meta = {"n_symbols": doc.get("n_symbols"), "broker": doc.get("_broker")}
    return ref, meta


def live_from_reference(ref):
    """Build a synthetic 'live' side that mirrors the reference EXACTLY, so
    reconcile(live_from_reference(ref), ref) must yield all-MATCH.  This is the
    substrate the self-test asserts and the negative controls mutate."""
    live = {}
    for broker, r in ref.items():
        live[broker] = {
            "broker_name": broker,
            "model_name":  r["model_name"],
            "digits":      r["digits"],
            "point":       r["point"],
            "tick_size":   r["point"],                 # MT5: tick_size==point (fx/most)
            "tick_value":  r["contract"] * r["point"], # nominal; internal-only
            "contract":    r["contract"],
            "vol_min":     r["lot_min"],
            "vol_max":     r["lot_max"],                # None == ref unbounded -> MATCH
            "vol_step":    r["lot_step"],
            "trade_mode":  4,                           # SYMBOL_TRADE_MODE_FULL
            "swap_mode":   1,                           # ignored-by-design
            "ccy_base":    r["base_ccy"],
            "ccy_profit":  r["profit_ccy"],
            "ccy_margin":  r["base_ccy"],
            "margin_ini":  0.0,
            "stops_level": 0,
            "select_ok":   1,
            "error":       "",
            "record_feed_digits": r["digits"],
        }
    return live


# ===========================================================================
# the reconciliation core
# ===========================================================================
def _finding(field, klass, sev, live, rec, note):
    return {"field": field, "class": klass, "severity": sev,
            "live": live, "record": rec, "note": note}


def reconcile_symbol(broker, live, ref):
    """Reconcile ONE symbol across all reconciled fields.
    Returns list of per-field findings (only non-trivial + a MATCH summary is
    left to the caller)."""
    F = []

    # --- 0. availability -----------------------------------------------------
    if live.get("select_ok", 1) == 0 or (live.get("error") or "") != "":
        F.append(_finding(
            "SYMBOL_SELECT", "SELECT-FAIL", SEV_CRITICAL,
            "select_ok=%s err=%r" % (live.get("select_ok"), live.get("error")),
            "must select", "symbol unavailable live -> cannot feed/trade; metadata "
            "may be zero-filled -> treat all downstream fields as unverified"))
        # do not trust the rest of this row's numbers; still run so counts show,
        # but the SELECT-FAIL already blocks.

    # --- 1. record_feed_digits internal consistency (CSV FA_DIGITS vs ref) ---
    if live.get("record_feed_digits") is not None and \
       live["record_feed_digits"] != ref["digits"]:
        F.append(_finding(
            "record_feed_digits", "REFERENCE-INCONSISTENCY", SEV_CRITICAL,
            live["record_feed_digits"], ref["digits"],
            "CSV-embedded FA_DIGITS disagrees with reference digits_record -> "
            "the reference has drifted from the compute path; fix before trusting judge"))

    # --- 2. quote grid: digits + point (precision vs scale) ------------------
    dl, dr = live.get("digits"), ref["digits"]
    pl, pr = live.get("point"), ref["point"]
    prod_l, prod_r = scale_prod(pl, dl), scale_prod(pr, dr)
    prod_ok = (prod_l is not None and prod_r is not None
               and abs(prod_l - prod_r) <= PROD_TOL * max(abs(prod_r), 1.0))
    if not prod_ok:
        # the price-scale invariant moved -> genuine value-scale change.
        F.append(_finding(
            "SYMBOL_DIGITS/POINT", "SCALE-DRIFT", SEV_CRITICAL,
            "digits=%s point=%.17g (point*10^d=%s)" % (dl, pl if pl is not None else float('nan'), prod_l),
            "digits=%s point=%.17g (point*10^d=%s)" % (dr, pr, prod_r),
            "price-scale invariant point*10^digits changed -> the numeric magnitude "
            "a lot marks against shifted -> marks/P&L WRONG.  BLOCK."))
    elif dl == dr and feq(pl, pr):
        pass  # MATCH (grid identical)
    else:
        # invariant preserved but digits/point differ -> pure decimal refinement.
        F.append(_finding(
            "SYMBOL_DIGITS/POINT", "PRECISION-DRIFT", SEV_HANDLED,
            "digits=%s point=%.17g" % (dl, pl if pl is not None else float('nan')),
            "digits=%s point=%.17g" % (dr, pr),
            "DE40-class: quote-grid magnitude preserved, only decimal places differ "
            "-> HANDLED by using live SYMBOL_POINT/DIGITS; relax FA_DIGITS refuse -> R2"))

    # --- 3. contract size ----------------------------------------------------
    cl, cr = live.get("contract"), ref["contract"]
    if not feq(cl, cr):
        ratio = (cl / cr) if (cl and cr) else None
        F.append(_finding(
            "SYMBOL_TRADE_CONTRACT_SIZE", "CONTRACT-DRIFT", SEV_CRITICAL,
            cl, cr,
            "live contract_size != baked (ratio=%s) -> lot->notional wrong, breaks "
            "position fidelity + marks.  BLOCK." % (
                ("%.6g" % ratio) if ratio is not None else "n/a")))

    # --- 4. volume grid: step / min / max ------------------------------------
    # step
    sl, sr = live.get("vol_step"), ref["lot_step"]
    if not feq(sl, sr):
        # can the live step represent the model's step? model lots are multiples
        # of model step; live step must divide model step evenly (live finer/equal).
        block = True
        if sl and sr:
            q = sr / sl
            block = not (q >= 1.0 - 1e-9 and abs(q - round(q)) <= 1e-6)
        F.append(_finding(
            "SYMBOL_VOLUME_STEP",
            "VOLUME-DRIFT", SEV_CRITICAL if block else SEV_HANDLED,
            sl, sr,
            ("live step CANNOT represent model lots (coarser/incompatible) -> "
             "quantizer diverges -> sizing wrong.  BLOCK."
             if block else
             "live step is finer/compatible -> model lots representable -> HANDLED (note)")))
    # min
    ml, mr = live.get("vol_min"), ref["lot_min"]
    if not feq(ml, mr):
        block = (ml is not None and mr is not None and ml > mr + FTOL_ABS)
        F.append(_finding(
            "SYMBOL_VOLUME_MIN",
            "VOLUME-DRIFT", SEV_CRITICAL if block else SEV_HANDLED,
            ml, mr,
            ("live min LARGER than model min -> model's smallest lots rejected -> "
             "sizing diverges.  BLOCK." if block else
             "live min <= model min -> model lots accepted -> HANDLED (note)")))
    # max: reference is None (unbounded, live-only exec concern)
    xl, xr = live.get("vol_max"), ref["lot_max"]
    if xr is None:
        if xl not in (None, 0, 0.0):
            F.append(_finding(
                "SYMBOL_VOLUME_MAX", "VOLUME-DRIFT", SEV_HANDLED,
                xl, "unbounded (None)",
                "reference imposes NO max; live carries a ceiling -> HANDLED: "
                "respect live SYMBOL_VOLUME_MAX at exec (split oversized orders)"))
    elif not feq(xl, xr):
        F.append(_finding(
            "SYMBOL_VOLUME_MAX", "VOLUME-DRIFT", SEV_HANDLED,
            xl, xr, "max ceiling differs -> HANDLED at exec"))

    # --- 5. profit ccy (drives eurq / marks) -> CRITICAL ---------------------
    plc, prc = live.get("ccy_profit"), ref["profit_ccy"]
    if plc is not None and prc is not None and plc != prc:
        F.append(_finding(
            "SYMBOL_CURRENCY_PROFIT", "CCY-DRIFT", SEV_CRITICAL,
            plc, prc,
            "live profit ccy != assumed quote ccy -> eurq cross (%s) & conversion "
            "wrong -> marks WRONG.  BLOCK." % ref.get("eurq_cross")))

    # --- 6. base ccy -> INFO only (indices carry label bases; no mark impact) -
    blc, brc = live.get("ccy_base"), ref["base_ccy"]
    if blc is not None and brc is not None and blc != brc:
        F.append(_finding(
            "SYMBOL_CURRENCY_BASE", "CCY-INFO", SEV_HANDLED,
            blc, brc,
            "base ccy differs (e.g. index label base) -> INFO: drives neither marks "
            "nor eurq; verify symbol mapping is intended"))

    # --- 7. swap mode: ignored-by-design (swap synthesized) -> never blocks --
    #   No finding: SwapEurq.mqh synthesizes swap; broker SYMBOL_SWAP_MODE is
    #   not read.  Recorded as MATCH-by-design in the resolution table.

    return F


def resolution_for(klass):
    return {
        "MATCH":                  "use baked value; no action",
        "PRECISION-DRIFT":        "FeedAssembler: use live SYMBOL_POINT/DIGITS for the "
                                  "quote grid; engine marks unaffected (magnitude preserved). "
                                  "Relax the FA_DIGITS refuse for this symbol -> R2.",
        "SCALE-DRIFT":            "BLOCK. Do NOT relax. Live price scale differs; marks/P&L "
                                  "wrong. Fix feed scaling or halt the symbol.",
        "CONTRACT-DRIFT":         "BLOCK. Live contract_size != baked; lot->notional wrong. "
                                  "Rebake engine contract or halt the symbol.",
        "VOLUME-DRIFT":           "If block: align lot_step/min or halt (quantizer diverges). "
                                  "If handled: respect live grid/ceiling at exec.",
        "CCY-DRIFT":              "BLOCK. Profit ccy drives eurq/marks; conversion wrong. "
                                  "Fix mapping/eurq cross or halt.",
        "CCY-INFO":               "INFO. Verify symbol mapping; no mark impact.",
        "SELECT-FAIL":            "BLOCK. Symbol unavailable live; cannot feed/trade. "
                                  "Resolve broker symbol availability first.",
        "REFERENCE-INCONSISTENCY":"BLOCK. Reference drifted from compute-path FA_DIGITS; "
                                  "re-derive the reference before trusting any verdict.",
        "SWAP":                   "HANDLED-by-design. Swap synthesized (SwapEurq.mqh); broker "
                                  "SYMBOL_SWAP_MODE not read.",
    }.get(klass, "review")


def reconcile(live_rows, ref_rows):
    """FULL 37xN reconciliation.  live_rows / ref_rows : broker_name -> fielddict.

    Coverage is asserted BOTH ways: a reference symbol with no live row (or vice
    versa) is a HARD error (raised), never an intersection/skip.
    """
    ref_keys = set(ref_rows.keys())
    live_keys = set(live_rows.keys())

    missing_in_live = sorted(ref_keys - live_keys)   # reference symbol never dumped
    extra_in_live   = sorted(live_keys - ref_keys)   # live symbol not in reference
    if missing_in_live:
        raise HardCoverageError(
            "HARD: %d reference symbol(s) absent from live CSV (missing, not skipped): %s"
            % (len(missing_in_live), missing_in_live))
    if extra_in_live:
        raise HardCoverageError(
            "HARD: %d live symbol(s) not in reference universe: %s"
            % (len(extra_in_live), extra_in_live))
    if len(ref_keys) != 37:
        raise HardCoverageError("HARD: reference covers %d symbols, expected 37"
                                % len(ref_keys))
    if len(live_keys) != 37:
        raise HardCoverageError("HARD: live covers %d symbols, expected 37"
                                % len(live_keys))

    per_symbol = {}
    for broker in sorted(ref_keys):
        findings = reconcile_symbol(broker, live_rows[broker], ref_rows[broker])
        per_symbol[broker] = findings

    # ---- summary ----
    class_counts = {}
    critical, handled_precision, handled_other = [], [], []
    resolution_table = {}
    for broker in sorted(per_symbol):
        findings = per_symbol[broker]
        if not findings:
            class_counts["MATCH"] = class_counts.get("MATCH", 0) + 1
            resolution_table[broker] = {"top_class": "MATCH",
                                        "severity": SEV_OK,
                                        "action": resolution_for("MATCH")}
            continue
        # rank findings: CRITICAL first
        sev_rank = {SEV_CRITICAL: 0, SEV_HANDLED: 1, SEV_OK: 2}
        findings_sorted = sorted(findings, key=lambda f: sev_rank[f["severity"]])
        top = findings_sorted[0]
        resolution_table[broker] = {
            "top_class": top["class"], "severity": top["severity"],
            "action": resolution_for(top["class"]),
            "fields": [f["field"] for f in findings_sorted],
        }
        for f in findings:
            class_counts[f["class"]] = class_counts.get(f["class"], 0) + 1
            item = {"symbol": broker, **f}
            if f["severity"] == SEV_CRITICAL:
                critical.append(item)
            elif f["class"] == "PRECISION-DRIFT":
                handled_precision.append(item)
            else:
                handled_other.append(item)

    n_match_symbols = sum(1 for b in per_symbol if not per_symbol[b])
    return {
        "n_symbols": len(ref_keys),
        "coverage_ok": True,
        "n_clean_match_symbols": n_match_symbols,
        "class_counts": class_counts,
        "critical": critical,
        "handled_precision": handled_precision,
        "handled_other": handled_other,
        "per_symbol": per_symbol,
        "resolution_table": resolution_table,
        "verdict": "BLOCK" if critical else "PASS",
    }


class HardCoverageError(Exception):
    pass


# ===========================================================================
# reporting
# ===========================================================================
def print_report(rep, title="RECONCILIATION"):
    print("=" * 78)
    print("%s — 37xN live-vs-record symbol metadata" % title)
    print("=" * 78)
    print("symbols=%d  coverage_ok=%s  clean-MATCH symbols=%d  verdict=%s"
          % (rep["n_symbols"], rep["coverage_ok"],
             rep["n_clean_match_symbols"], rep["verdict"]))
    print("\nclass counts:")
    for k in sorted(rep["class_counts"]):
        print("   %-24s %d" % (k, rep["class_counts"][k]))

    print("\nCRITICAL (must block / fix)  [%d]" % len(rep["critical"]))
    if not rep["critical"]:
        print("   (none)")
    for it in rep["critical"]:
        print("   [%s] %-7s %-26s live=%r rec=%r"
              % (it["symbol"], it["class"], it["field"], it["live"], it["record"]))
        print("        -> %s" % it["note"])

    print("\nHANDLED — precision (DE40 class, becomes R2)  [%d]"
          % len(rep["handled_precision"]))
    if not rep["handled_precision"]:
        print("   (none)")
    for it in rep["handled_precision"]:
        print("   [%s] %-26s live=%r rec=%r"
              % (it["symbol"], it["field"], it["live"], it["record"]))

    if rep["handled_other"]:
        print("\nHANDLED — other (volume ceiling / base-ccy info)  [%d]"
              % len(rep["handled_other"]))
        for it in rep["handled_other"]:
            print("   [%s] %-12s %-26s live=%r rec=%r"
                  % (it["symbol"], it["class"], it["field"], it["live"], it["record"]))

    print("\nRECOMMENDED per-symbol resolution (non-MATCH only):")
    for broker in sorted(rep["resolution_table"]):
        e = rep["resolution_table"][broker]
        if e["top_class"] == "MATCH":
            continue
        print("   %-8s [%s/%s] %s"
              % (broker, e["severity"], e["top_class"], e["action"]))
    n_match = sum(1 for b in rep["resolution_table"]
                  if rep["resolution_table"][b]["top_class"] == "MATCH")
    print("   (+ %d symbols MATCH: use baked value, no action)" % n_match)
    print("")


# ===========================================================================
# self-test + negative controls (synthetic data)
# ===========================================================================
def run_selftests(ref):
    """Returns (all_ok, results dict) with per-check pass/fail."""
    results = {}
    ok_all = True

    # -- SELF-TEST: reference-as-live -> all MATCH --------------------------
    live = live_from_reference(ref)
    rep = reconcile(live, ref)
    st_ok = (rep["verdict"] == "PASS"
             and not rep["critical"]
             and not rep["handled_precision"]
             and not rep["handled_other"]
             and rep["n_clean_match_symbols"] == 37)
    results["self_test"] = {
        "desc": "reconcile(reference-as-live, reference) == all 37 MATCH",
        "pass": st_ok,
        "verdict": rep["verdict"],
        "clean_match_symbols": rep["n_clean_match_symbols"],
        "n_critical": len(rep["critical"]),
        "n_drift": len(rep["handled_precision"]) + len(rep["handled_other"]),
    }
    ok_all &= st_ok

    # -- NC (i): DE40 digits 1->2, same magnitude -> PRECISION --------------
    live = live_from_reference(ref)
    live["DE40"]["digits"] = 2
    live["DE40"]["point"] = 0.01          # point*10^2 = 1  == record 0.1*10^1 = 1
    live["DE40"]["tick_size"] = 0.01
    live["DE40"]["record_feed_digits"] = ref["DE40"]["digits"]  # FA_DIGITS unchanged
    rep = reconcile(live, ref)
    de40 = rep["per_symbol"]["DE40"]
    nc_i_ok = (len(de40) == 1
               and de40[0]["class"] == "PRECISION-DRIFT"
               and de40[0]["severity"] == SEV_HANDLED
               and rep["verdict"] == "PASS")           # precision alone must NOT block
    results["nc_i_precision"] = {
        "desc": "inject DE40 digits 1->2 (magnitude preserved) -> PRECISION-DRIFT, HANDLED, no block",
        "pass": nc_i_ok,
        "classified": de40[0]["class"] if de40 else None,
        "verdict": rep["verdict"],
    }
    ok_all &= nc_i_ok

    # -- NC (ii): contract 100000 -> 10000 -> CONTRACT-DRIFT CRITICAL -------
    live = live_from_reference(ref)
    victim = "EURUSD"
    assert ref[victim]["contract"] == 100000.0
    live[victim]["contract"] = 10000.0
    rep = reconcile(live, ref)
    v = rep["per_symbol"][victim]
    nc_ii_ok = (any(f["class"] == "CONTRACT-DRIFT" and f["severity"] == SEV_CRITICAL
                    for f in v)
                and rep["verdict"] == "BLOCK")
    results["nc_ii_contract"] = {
        "desc": "inject %s contract 100000->10000 -> CONTRACT-DRIFT CRITICAL, BLOCK" % victim,
        "pass": nc_ii_ok,
        "classes": [f["class"] for f in v],
        "verdict": rep["verdict"],
    }
    ok_all &= nc_ii_ok

    # -- NC (iii): price-scale /10 -> SCALE-DRIFT CRITICAL ------------------
    #   A genuine value-scale change breaks the point*10^digits invariant: the
    #   quote grid is re-scaled by 10x WITHOUT a compensating digit change
    #   (digits held, point /10) -> point*10^digits shifts 1 -> 0.1.
    live = live_from_reference(ref)
    victim3 = "US500"
    live[victim3]["point"] = ref[victim3]["point"] / 10.0   # digits held at 2
    live[victim3]["tick_size"] = live[victim3]["point"]
    rep = reconcile(live, ref)
    v3 = rep["per_symbol"][victim3]
    nc_iii_ok = (any(f["class"] == "SCALE-DRIFT" and f["severity"] == SEV_CRITICAL
                     for f in v3)
                 and not any(f["class"] == "PRECISION-DRIFT" for f in v3)  # NOT misread as precision
                 and rep["verdict"] == "BLOCK")
    results["nc_iii_scale"] = {
        "desc": "inject %s price-scale /10 (invariant broken) -> SCALE-DRIFT CRITICAL, "
                "NOT misread as precision, BLOCK" % victim3,
        "pass": nc_iii_ok,
        "classes": [f["class"] for f in v3],
        "verdict": rep["verdict"],
    }
    ok_all &= nc_iii_ok

    # -- NC (iv): drop a symbol from live -> HARD error, not silent pass ----
    live = live_from_reference(ref)
    dropped = "XAUUSD"
    del live[dropped]
    hard_raised = False
    hard_msg = ""
    try:
        reconcile(live, ref)
    except HardCoverageError as e:
        hard_raised = True
        hard_msg = str(e)
    nc_iv_ok = hard_raised and dropped in hard_msg
    results["nc_iv_missing"] = {
        "desc": "drop %s from live -> HARD coverage error (not silent pass)" % dropped,
        "pass": nc_iv_ok,
        "raised": hard_raised,
        "msg": hard_msg[:120],
    }
    ok_all &= nc_iv_ok

    return ok_all, results


def print_selftests(ok_all, results):
    print("=" * 78)
    print("SELF-TEST + NEGATIVE CONTROLS (synthetic data)")
    print("=" * 78)
    for k in ["self_test", "nc_i_precision", "nc_ii_contract",
              "nc_iii_scale", "nc_iv_missing"]:
        r = results[k]
        print("[%s] %-16s %s" % ("PASS" if r["pass"] else "FAIL", k, r["desc"]))
        for kk, vv in r.items():
            if kk in ("desc", "pass"):
                continue
            print("        %s=%r" % (kk, vv))
    print("-" * 78)
    print("ALL SELF-TESTS + NEGATIVE CONTROLS: %s"
          % ("PASS" if ok_all else "FAIL"))
    print("")


# ===========================================================================
# main
# ===========================================================================
def main(argv):
    ref_path = DEFAULT_REF
    live_path = None
    args = [a for a in argv[1:]]
    selftest_only = False
    rest = []
    for a in args:
        if a in ("--selftest", "--self-test", "-s"):
            selftest_only = True
        else:
            rest.append(a)
    if rest:
        live_path = rest[0]
        if len(rest) > 1:
            ref_path = rest[1]

    ref, meta = load_reference(ref_path)

    # always run self-test + negative controls (the real CSV is owner-run)
    ok_all, results = run_selftests(ref)
    print_selftests(ok_all, results)

    exit_code = 0 if ok_all else 3

    if live_path and not selftest_only:
        try:
            live = load_live_csv(live_path)
            rep = reconcile(live, ref)
            print_report(rep, title="LIVE RECONCILIATION")
            if rep["verdict"] == "BLOCK":
                exit_code = max(exit_code, 2)
        except HardCoverageError as e:
            print("HARD COVERAGE ERROR: %s" % e)
            exit_code = max(exit_code, 4)
    else:
        print("(no live CSV supplied — ran self-test + negative controls only; "
              "pass FMA3_symbol_meta.csv to reconcile the owner's run)")

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
