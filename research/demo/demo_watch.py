#!/usr/bin/env python3
"""demo_watch.py — live status + kill-criteria alerting for the demo (DEMO_FORWARD_PLAN §6E).

Reads the live per-hour telemetry and reports the CURRENT status against the
§3 success criteria and the §5 kill criteria, flagging any breach. Meant to be
run on-demand (or on a schedule) during the demo — it is the automated eye on
"is anything going wrong right now", complementary to the weekly reconcile_demo.py.

Handles the trade-DISABLED shakedown correctly: with no open positions
margin_level is 0, so the margin/DD criteria are marked N/A and the checks focus
on plumbing (fidelity, warm-resume, refuse-latches, telemetry freshness).

Kill criteria (§5): min ML < 105% · worst-mark DD > 28% (IC) · fidelity mismatch
run-rate implying < 95%/day · a refuse-latch on non-corruption.
Success bands (§3, IC): min ML >= 110% · DD within ~22.9% (flag > 28%) · fidelity
>= 99% of bars.

Usage:
  demo_watch.py --telemetry FMA3_native_hourly.csv [--journal <log>] \
                [--preset ic|ftmo] [--json out.json]
Exit code: 0 = OK, 1 = a KILL criterion is breached (usable in a scheduled alert).
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconcile_demo import load_telemetry, position_fidelity, worst_mark_dd  # reuse the harness helpers

# per-preset thresholds (§3 / §5)
BANDS = {
    "ic":   {"ml_kill": 105.0, "ml_ok": 110.0, "dd_flag": 0.28},
    "ftmo": {"ml_kill": 105.0, "ml_ok": 110.0, "dd_flag": 0.28},  # + the 10% max-loss rule (checked on balance)
}


def status(telemetry: str, journal: str | None, preset: str) -> dict:
    # load_telemetry returns (hourly H rows, per-symbol P rows) since the
    # per-symbol telemetry landed (PR #23) — this watcher predated that and
    # crashed on the tuple until 2026-07-21.
    h, p = load_telemetry(telemetry)
    b = BANDS[preset]
    last = h.iloc[-1]
    alerts, flags = [], []

    # --- freshness (is the EA still writing?) ---
    # NOTE: telemetry `dt` is BROKER SERVER time (≈EET), so vs UTC now this
    # reads ~2-3h optimistic — fine as a coarse "still writing?" signal.
    age_h = (pd.Timestamp.now("UTC").tz_localize(None) - h["dt"].iloc[-1]).total_seconds() / 3600
    st = {"last_row_server_time": str(h["dt"].iloc[-1]), "hours_since_approx": round(age_h, 1),
          "n_hours": int(len(h)), "trading": int(last["trading"]) if "trading" in h else None}

    # --- plumbing (always checked) ---
    # sc_mm is the SC-sleeve SIGNAL self-check, NOT position fidelity, and
    # `fires` is the CoreTrigger SEGMENT count, NOT the breaker (go/no-go #2
    # relabel — the real breaker count is n_stops).
    sc = int(h["sc_mm"].max()) if "sc_mm" in h else None
    st["sc_selfcheck_max"] = sc
    # rough daily mismatch rate: sc_mm is cumulative; per-day proxy = sc / days
    days = max(1.0, (h["dt"].iloc[-1] - h["dt"].iloc[0]).total_seconds() / 86400)
    if sc is not None and sc / days > 0.05 * 24:   # >5% of a day's ~24 bars
        alerts.append(f"SC-SELFCHECK: sc_mm={sc} over {days:.0f}d — signal self-check mismatch rate high")
    st["core_segments_max"] = int(h["fires"].max()) if "fires" in h else None
    st["breaker_stops"] = (int(pd.to_numeric(h["n_stops"], errors="coerce").dropna().iloc[-1])
                           if "n_stops" in h and pd.to_numeric(h["n_stops"], errors="coerce").notna().any()
                           else None)
    st["unready_now"] = int(last["unready"]) if "unready" in h else None

    # --- position fidelity (the ACTUAL §3/§5 criterion; needs P rows) ---
    if p is not None and len(p):
        fid = position_fidelity(p, 0.25)
        if "status" in fid:
            st["bar_fidelity"] = fid.get("status")
        else:
            st["bar_fidelity"] = round(fid["bar_fidelity"], 4)
            if fid["n_sign_violations"] or fid["bar_fidelity"] < 0.95:
                alerts.append(f"FIDELITY: bar {fid['bar_fidelity']:.2%}, "
                              f"sign violations {fid['n_sign_violations']} (§5 kill line 95%)")
            elif fid["bar_fidelity"] < 0.99:
                flags.append(f"fidelity: bar {fid['bar_fidelity']:.2%} below the 99% §3 band")
    else:
        st["bar_fidelity"] = "no P rows — telemetry predates the 2026-07 build"

    # --- margin / drawdown (only meaningful with open positions) ---
    ml_col = next((c for c in h.columns if c.lower() in ("margin_level", "ml", "marginlevel")), None)
    if ml_col:
        ml = pd.to_numeric(h[ml_col], errors="coerce")
        active = ml[ml > 0]
        if len(active):
            st["min_ML"] = round(float(active.min()), 1)
            st["current_ML"] = round(float(ml.iloc[-1]), 1) if ml.iloc[-1] > 0 else "flat"
            if active.min() < b["ml_kill"]:
                alerts.append(f"MARGIN KILL: min ML {active.min():.1f}% < {b['ml_kill']}%")
            elif active.min() < b["ml_ok"]:
                flags.append(f"margin: min ML {active.min():.1f}% below the {b['ml_ok']}% comfort line")
        else:
            st["min_ML"] = "no positions yet (trade-disabled / warming)"
    else:
        st["min_ML"] = "not logged — recompile with the margin/ML telemetry (§6C.1)"

    dd = worst_mark_dd(h["equity"])
    st["worst_mark_dd"] = round(dd, 4)
    if dd < -b["dd_flag"]:
        alerts.append(f"DRAWDOWN: worst-mark {dd:.1%} beyond the {b['dd_flag']:.0%} flag line")

    # --- refuse-latch scan (optional; needs the Journal/Experts log) ---
    if journal and Path(journal).exists():
        txt = Path(journal).read_text(errors="ignore")
        n_ref = txt.count("REFUSE") + txt.lower().count("refuse-to-trade")
        n_cold = txt.count("COLD START")
        st["journal_refuse_hits"] = n_ref
        st["journal_cold_start_hits"] = n_cold
        if n_ref:
            alerts.append(f"REFUSE-LATCH: {n_ref} refuse mention(s) in the log — inspect (kill if non-corruption)")
        if n_cold:
            flags.append(f"COLD START seen {n_cold}× — warm-resume may have failed on a restart")

    st["alerts"] = alerts       # §5 kill-worthy
    st["flags"] = flags         # §3 comfort-band
    st["verdict"] = "KILL-REVIEW" if alerts else ("WATCH" if flags else "OK")
    return st


def _fmt(s: dict) -> str:
    L = [f"DEMO WATCH — {s['verdict']}  ({s['n_hours']:,} hrs, last row {s['last_row_server_time']} "
         f"server time, ~{s['hours_since_approx']}h ago, trading={s['trading']})"]
    L.append(f"  min ML: {s['min_ML']}  ·  worst-mark DD: {s['worst_mark_dd']:.2%}  ·  "
             f"bar fidelity: {s['bar_fidelity']}  ·  sc-selfcheck: {s['sc_selfcheck_max']}  ·  "
             f"breaker stops: {s['breaker_stops']}")
    if "journal_refuse_hits" in s:
        L.append(f"  journal: refuse={s['journal_refuse_hits']} · cold-start={s['journal_cold_start_hits']}")
    for a in s["alerts"]:
        L.append(f"  🔴 ALERT  {a}")
    for f in s["flags"]:
        L.append(f"  🟡 flag   {f}")
    if not s["alerts"] and not s["flags"]:
        L.append("  ✅ all criteria within band")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Demo live status + kill-criteria watcher")
    ap.add_argument("--telemetry", required=True)
    ap.add_argument("--journal", help="MT5 Journal/Experts log (for refuse/cold-start scan)")
    ap.add_argument("--preset", choices=["ic", "ftmo"], default="ic")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    s = status(a.telemetry, a.journal, a.preset)
    print(_fmt(s))
    if a.json:
        import json
        Path(a.json).write_text(json.dumps(s, indent=1, default=str))
    return 1 if s["alerts"] else 0


if __name__ == "__main__":
    sys.exit(main())
