"""trigger_detector.py — live band-trigger detector, HARNESS + LIVE modes,
gate G-S3 (UNIT 2 of the S2 live-Core build).

WHAT THIS IS
------------
The python statement-mirror of the FUTURE live segment-boundary detector that
replaces CoreSim's frozen-trigger replay (S2_CORE_LIVE_DESIGN.md section 4).
Two modes, per the owner-ratified split (S2_PREP_STATUS "OWNER RATIFICATIONS"
item 2):

  HARNESS mode — anchor-exact semantics, a statement port of the NSF5 anchor
    chain (READ-ONLY imports mirrored at code level, never edited):
      gbandrebal/sim.py::run_generic      (probe loop 6/18/999 months,
                                           exact re-run at the split)
      gbandrebal/sim.py::slot_frame       (union of slot daily indices,
                                           .ffill().bfill() — the retrospective
                                           BACKFILL is deliberate here)
      gbandrebal/sim.py::first_share_trigger
                                          (row-wise shares sf/sf.sum(axis=1),
                                           min-gap (ts-cur).days >= 5 on the
                                           DECISION label, act = ts + 1d,
                                           breach up 0.25 / floor (1/7)/1.75)
      gbandrebal/sim.py::earliest_trigger (band + harvest, earliest act wins,
                                           stable sort => band on ties)
      v51_bandharvest.py::_run_window     (per-slot combine_curves of member
                                           close curves + sflat, day-close =
                                           resample('D').last().dropna())
      v51_bandharvest.py::_first_trigger  (harvest arm: daily cadence, thr =
                                           2.5*seed*W, act next midnight,
                                           NO min-gap, first breach per sleeve)
    driven from CoreSim slot equities: per-leg curves come from the proven
    coresim_reference.run_leg_scalar scalar stepper and the slot/book combines
    from coresim_reference.combine_legs (bit-proven vs the parity parquet
    32/32), with the per-leg targets from core_signal_reference (UNIT 1,
    G-S1 bit-zero vs the frozen tgt).

  LIVE mode — causal streaming semantics (section 4.3/4.4): NO retrospective
    bfill; before a slot's first daily print of a segment the slot is held at
    its legcap seed*W (hold-at-legcap); decisions evaluated day-close by
    day-close in frame order; same thresholds, same min-gap basis, harvest
    tested on the causal carried values.  Divergence telemetry is recorded at
    every leading-edge (held) row: shares under live-hold vs harness-bfill
    valuation and whether the row decision (band raw / band gated / harvest)
    differs.

GATES (all MEASURED, written to trigger_gates.json)
---------------------------------------------------
  G-S3 (harness): over the frozen 2020-2025 grid the harness chain must
    reproduce the frozen trigger chain EXACTLY —
      * 31/31 band act dates == v7_extract_verification.json triggers[].act
        (== segments[1:].t0), decided dates equal too (incl. the one
        Sunday-decided trigger), 0 harvest fires;
      * every chained seed bit-equal to triggers[j].book (float ==, and the
        final committed eqc bit-equal 532229.8433634703).
  LIVE differential: run the LIVE-mode chain over the same grid; report
    trigger-date identity vs harness, seed max|diff|, per-segment max
    slot first-print lag, every held-row decision comparison, and the
    harvest headroom (max slot/thr ratio ever observed).

Usage (python3 runs from FMA2/research per campaign convention):
  cd /Users/dsalamanca/vs_env/FableMultiAssets2/research && python3 \
    /Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure/coresignal/trigger_detector.py

Writes research/bpure/coresignal/trigger_gates.json (MEASURED results).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()

# --- coresim_reference by FILE (does the whole NSF5 sys.path dance +
#     the lock_v5 stop_out=1e-9 side-effect assert) ---------------------------
_spec = importlib.util.spec_from_file_location(
    "coresim_reference", _HERE.parent.parent / "coresim" / "coresim_reference.py")
CR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CR)

# --- core_signal_reference by FILE (UNIT 1: the live target steppers) --------
_spec2 = importlib.util.spec_from_file_location(
    "core_signal_reference", _HERE.parent / "core_signal_reference.py")
CS = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(CS)

OUT_JSON = _HERE.parent / "trigger_gates.json"

# committed-run parameters (gbandrebal/reproduce.py "BAND_SYM_25_harvest",
# reference_key harvest_band_sym in v7_extract_verification.json)
LO = pd.Timestamp("2020-01-01")
HI = pd.Timestamp("2026-01-01")
W7 = CR.W7                       # 1/7
UP = 0.25
DOWN = W7 / 1.75                 # ~0.081633
KMULT = 2.5
MIN_GAP_DAYS = 5
PROBE_MONTHS = (6, 18, 999)
FINAL_EQC_TARGET = CS.FINAL_EQC_TARGET


# =============================================================================
# 1. Window runner — CoreSim-backed twin of v51_bandharvest._run_window.
#    Per-leg curves: CR.run_leg_scalar (bit-proven); slot = combine of the
#    sleeve's member close curves (+ sflat) day-closed at the slot's own last
#    stamp of each raw-stamp day; book tc = combine of all legs + flat.
# =============================================================================
def run_window(sleeves_t, arrays, lo, hi, seed):
    """One equal-slot window [lo,hi) at book seed `seed`.  Returns
    (tc, slot) — tc = combined book close curve (pd.Series), slot = dict
    {sleeve: daily slot-equity Series or None}."""
    legs_all = []
    flat = 0.0
    slot = {}
    for name, legs in sleeves_t.items():
        legcap = seed * W7 / len(legs)
        members, sflat = [], 0.0
        for inst, tgt in legs:
            A = arrays[inst]
            idx = A["idx"]
            i0 = int(np.searchsorted(idx.values, np.datetime64(lo), side="left"))
            i1 = int(np.searchsorted(idx.values, np.datetime64(hi), side="left"))
            if i1 <= i0:
                flat += legcap
                sflat += legcap
                continue
            tgt64 = np.asarray(tgt, dtype=np.float64)
            cfg = A["cfg"]
            eq_c, eq_w, mg, _state = CR.run_leg_scalar(
                A["bid_o"], A["bid_h"], A["bid_l"], A["bid_c"],
                A["ask_o"], A["ask_h"], A["ask_l"], A["ask_c"],
                A["eurq"], A["swap_flag"], A["swap_long"], A["swap_short"],
                tgt64,
                float(cfg["contract_size"]), float(cfg["commission_side"]),
                float(cfg["leverage"]), float(cfg["lot_step"]),
                float(cfg["min_lot"]), float(legcap), i0, i1)
            lg = dict(idx=idx[i0:i1], eq_c=eq_c, eq_w=eq_w, margin=mg)
            members.append(lg)
            legs_all.append(lg)
        if members:
            u, c, _w, _m = CR.combine_legs(members, 0.0)
            sc = pd.Series(c, index=u)
            slot[name] = sc.resample("D").last().dropna() + sflat
        else:
            slot[name] = None
    union, eqc, _eqw, _mg = CR.combine_legs(legs_all, flat)
    tc = pd.Series(eqc, index=union)
    return tc, slot


# =============================================================================
# 2. Anchor detector primitives — statement ports of gbandrebal/sim.py and
#    v51_bandharvest._first_trigger (HARNESS mode).
# =============================================================================
def slot_frame(slot, seed, lo):
    """Per-sleeve daily slot-equity DataFrame (flat legs carried at legcap).
    ANCHOR-EXACT: .ffill().bfill() — retrospective backfill included."""
    cols = {}
    for n, s in slot.items():
        cols[n] = s if s is not None else pd.Series(seed * W7, index=[lo])
    idx = None
    for s in cols.values():
        idx = s.index if idx is None else idx.union(s.index)
    return pd.DataFrame({n: s.reindex(idx) for n, s in cols.items()}).ffill().bfill()


def first_share_trigger(sf, up, down, cur, probe_hi, min_gap_days):
    """First causal band trigger (T6 convention): daily close whose slot shares
    breach [down, up]; act at next midnight. Returns (act_ts, info) or None."""
    sh = sf.div(sf.sum(axis=1), axis=0)
    sh = sh[(sh.index > cur)]
    for ts, row in sh.iterrows():
        act = ts + pd.Timedelta(days=1)
        if (ts - cur).days < min_gap_days:
            continue
        if not (cur < act < probe_hi):
            continue
        hi_s, lo_s = float(row.max()), float(row.min())
        if (up is not None and hi_s > up) or (down is not None and lo_s < down):
            return act, dict(kind="band", decided=str(ts.date()), max_share=hi_s,
                             min_share=lo_s, max_sleeve=str(row.idxmax()),
                             min_sleeve=str(row.idxmin()))
    return None


def _first_trigger(slot, thr, lo, hi, cadence):
    """Earliest causal harvest split t in (lo,hi): first decision point whose
    close shows any slot equity > thr; act at the following boundary.
    (v51_bandharvest._first_trigger, daily cadence only in this book.)"""
    best = None
    for name, d in slot.items():
        if d is None or len(d) < 2:
            continue
        assert cadence == "D", cadence
        pts = d                                     # each day close
        act = pts.index + pd.Timedelta(days=1)      # -> next midnight
        for ts, val in zip(act, pts.values):
            if val > thr:
                if lo < ts < hi and (best is None or ts < best[0]):
                    best = (ts, name, float(val))
                break                    # only the first breach per sleeve matters
    return best


def earliest_trigger(sf, slot, up, down, kmult, seed, W, cur, probe_hi,
                     min_gap_days):
    """Earliest re-split among the band trigger and the shipped harvest trigger."""
    cand = []
    if up is not None or down is not None:
        bhit = first_share_trigger(sf, up, down, cur, probe_hi, min_gap_days)
        if bhit is not None:
            cand.append(bhit)                                   # (act, info)
    if np.isfinite(kmult):
        hhit = _first_trigger(slot, kmult * seed * W, cur, probe_hi, "D")
        if hhit is not None:
            act, name, val = hhit
            cand.append((act, dict(kind="harvest", sleeve=str(name),
                                   slot=float(val),
                                   thr=float(kmult * seed * W))))
    if not cand:
        return None
    cand.sort(key=lambda x: x[0])
    return cand[0]


# =============================================================================
# 3. HARNESS chain — statement port of gbandrebal/sim.py::run_generic on the
#    single band-arm edge pair [LO, HI) (no calendar cadence).
# =============================================================================
def harness_chain(sleeves_t, arrays, verbose=True):
    seed = float(CR.INIT)
    triggers = []
    seeds = [seed]
    harvest_headroom = 0.0     # max over decided rows of max_slot / thr
    cur = LO
    guard = 0
    while cur < HI and guard < 3000:
        hit = None
        tc = sf = slot = None
        for probe_m in PROBE_MONTHS:
            probe_hi = min(HI, cur + pd.DateOffset(months=probe_m))
            tc, slot = run_window(sleeves_t, arrays, cur, probe_hi, seed)
            sf = slot_frame(slot, seed, cur)
            hit = earliest_trigger(sf, slot, UP, DOWN, KMULT, seed, W7,
                                   cur, probe_hi, MIN_GAP_DAYS)
            if hit is not None or probe_hi >= HI:
                break
        # harvest headroom telemetry (diagnostic, outside the anchor): max
        # slot-own day-close / thr over the rows the detector actually SCANS
        # (ts > cur up to the decided label; rows past act never exist in the
        # committed chain and must not contaminate the measurement)
        thr = KMULT * seed * W7
        lim = (hit[0] - pd.Timedelta(days=1)) if hit is not None else HI
        for _n, _d in slot.items():
            if _d is None:
                continue
            v = _d[(_d.index > cur) & (_d.index <= lim)]
            if len(v):
                harvest_headroom = max(harvest_headroom, float(v.max()) / thr)
        if hit is None:                                # no trigger before HI
            sel = tc.index < HI
            seed = float(tc[sel].iloc[-1])
            cur = HI
        else:
            t, info = hit
            tc2, _slot2 = run_window(sleeves_t, arrays, cur, t, seed)  # exact re-run
            sel = tc2.index < t
            newseed = float(tc2[sel].iloc[-1])
            info = dict(info)
            info.update(act=str(t.date()), book=newseed)
            triggers.append(info)
            if verbose:
                print(f"      [harness] trig {len(triggers):>3} {info['kind']:7} "
                      f"decided {info.get('decided','-')} act {t.date()} "
                      f"book -> {newseed:,.2f}", flush=True)
            seeds.append(newseed)
            seed = newseed
            cur = t
            guard += 1
    if guard >= 3000:
        raise RuntimeError("guard exhausted (harness)")
    return dict(triggers=triggers, seeds=seeds, final_eqc=seed,
                harvest_headroom=harvest_headroom)


# =============================================================================
# 4. LIVE chain — causal streaming semantics (design section 4.3/4.4):
#    hold-at-legcap leading edges (NO bfill), decisions in day order, same
#    thresholds/min-gap; probe windows are a pure computational device (the
#    per-leg curves are causal, so any window covering the decided day yields
#    identical day-closes).  Telemetry at every held row.
# =============================================================================
def live_frame(slot, seed, lo):
    """Causal frame: per-slot ffill of own day-closes; rows BEFORE a slot's
    first print held at legcap seed*W (no bfill).  Also returns per-slot
    first-print label for telemetry."""
    cols, first = {}, {}
    for n, s in slot.items():
        cols[n] = s if s is not None else pd.Series(seed * W7, index=[lo])
    idx = None
    for s in cols.values():
        idx = s.index if idx is None else idx.union(s.index)
    df = pd.DataFrame({n: s.reindex(idx) for n, s in cols.items()}).ffill()
    for n in df.columns:
        fv = df[n].first_valid_index()
        first[n] = fv
    held = df.isna()                       # leading-edge rows per slot
    df = df.fillna(seed * W7)              # hold-at-legcap
    return df, held, first


def live_detect(slot, seed, cur, probe_hi, telemetry):
    """Scan day-closes in frame order (ts > cur), causally.  Returns
    ((act, info) or None, headroom) where headroom = max scanned slot
    value / harvest thr.  Appends held-row telemetry rows."""
    lf, held, first = live_frame(slot, seed, cur)
    bf = slot_frame(slot, seed, cur)       # harness valuation for comparison
    thr = KMULT * seed * W7
    headroom = 0.0
    for ts in lf.index:
        if not ts > cur:
            continue
        row = lf.loc[ts]
        tot = float(row.sum())
        hi_s, lo_s = float(row.max()), float(row.min())
        headroom = max(headroom, hi_s / thr)
        sh_hi, sh_lo = hi_s / tot, lo_s / tot
        gap_ok = (ts - cur).days >= MIN_GAP_DAYS
        band_raw = (sh_hi > UP) or (sh_lo < DOWN)
        harv_raw = hi_s > thr
        # ---- telemetry on held (bfill-vs-hold divergent) rows ----
        if bool(held.loc[ts].any()):
            brow = bf.loc[ts]
            btot = float(brow.sum())
            b_hi, b_lo = float(brow.max()) / btot, float(brow.min()) / btot
            b_band = (b_hi > UP) or (b_lo < DOWN)
            b_harv = float(brow.max()) > thr
            telemetry.append(dict(
                seg_start=str(cur.date()), date=str(ts.date()),
                held_slots=[n for n in lf.columns if bool(held.loc[ts, n])],
                live_max_share=sh_hi, live_min_share=sh_lo,
                bfill_max_share=b_hi, bfill_min_share=b_lo,
                band_raw_live=bool(band_raw), band_raw_bfill=bool(b_band),
                band_gated_live=bool(band_raw and gap_ok),
                band_gated_bfill=bool(b_band and gap_ok),
                harvest_live=bool(harv_raw), harvest_bfill=bool(b_harv),
                decision_differs=bool((band_raw and gap_ok) != (b_band and gap_ok)
                                      or harv_raw != b_harv)))
        # ---- live decision ----
        fired_band = band_raw and gap_ok
        if fired_band or harv_raw:
            act = ts + pd.Timedelta(days=1)
            kind = "band" if fired_band else "harvest"   # band wins ties (anchor)
            return (act, dict(kind=kind, decided=str(ts.date()),
                              max_share=sh_hi, min_share=sh_lo,
                              max_sleeve=str(row.idxmax()),
                              min_sleeve=str(row.idxmin()),
                              harvest_also=bool(fired_band and harv_raw))), headroom
    return None, headroom


def live_chain(sleeves_t, arrays, verbose=True):
    seed = float(CR.INIT)
    triggers = []
    seeds = [seed]
    telemetry = []
    lag_rows = []
    harvest_headroom = 0.0
    cur = LO
    guard = 0
    while cur < HI and guard < 3000:
        hit = None
        tc = slot = None
        for probe_m in PROBE_MONTHS:
            probe_hi = min(HI, cur + pd.DateOffset(months=probe_m))
            tc, slot = run_window(sleeves_t, arrays, cur, probe_hi, seed)
            hit, hr = live_detect(slot, seed, cur, probe_hi, telemetry)
            harvest_headroom = max(harvest_headroom, hr)
            if hit is not None or probe_hi >= HI:
                break
        # per-segment first-print lag telemetry
        lf, _held, first = live_frame(slot, seed, cur)
        lags = {n: (int((fv - lf.index[0]).days) if fv is not None else None)
                for n, fv in first.items()}
        lag_rows.append(dict(seg_start=str(cur.date()),
                             max_first_print_lag_days=max(
                                 v for v in lags.values() if v is not None),
                             lags=lags))
        if hit is None:
            sel = tc.index < HI
            seed = float(tc[sel].iloc[-1])
            cur = HI
        else:
            t, info = hit
            tc2, _slot2 = run_window(sleeves_t, arrays, cur, t, seed)
            sel = tc2.index < t
            newseed = float(tc2[sel].iloc[-1])
            info = dict(info)
            info.update(act=str(t.date()), book=newseed)
            triggers.append(info)
            if verbose:
                print(f"      [live]    trig {len(triggers):>3} {info['kind']:7} "
                      f"decided {info['decided']} act {t.date()} "
                      f"book -> {newseed:,.2f}", flush=True)
            seeds.append(newseed)
            seed = newseed
            cur = t
            guard += 1
    if guard >= 3000:
        raise RuntimeError("guard exhausted (live)")
    # dedupe telemetry rows re-scanned by the 6->18->999 probe escalation
    seen, tele = set(), []
    for r in telemetry:
        key = (r["seg_start"], r["date"])
        if key not in seen:
            seen.add(key)
            tele.append(r)
    return dict(triggers=triggers, seeds=seeds, final_eqc=seed,
                telemetry=tele, lag_rows=lag_rows,
                harvest_headroom=harvest_headroom)


# =============================================================================
# 5. Gates
# =============================================================================
def gate_g_s3(harness, frozen_trigs, frozen_segs):
    """32/32 boundary identity: 31 act dates + decided dates + kinds + seeds
    bit-equal + final eqc bit-equal + 0 harvest fires."""
    ht = harness["triggers"]
    rows = []
    n_date_match = 0
    n_decided_match = 0
    seed_maxdiff = 0.0
    for j, ft in enumerate(frozen_trigs):
        mine = ht[j] if j < len(ht) else None
        act_ok = mine is not None and mine["act"] == ft["act"]
        dec_ok = mine is not None and mine.get("decided") == ft["decided"]
        seed_d = abs(mine["book"] - ft["book"]) if mine is not None else float("inf")
        seed_maxdiff = max(seed_maxdiff, seed_d)
        n_date_match += int(act_ok)
        n_decided_match += int(dec_ok)
        rows.append(dict(j=j, frozen_decided=ft["decided"], frozen_act=ft["act"],
                         mine_decided=None if mine is None else mine.get("decided"),
                         mine_act=None if mine is None else mine["act"],
                         act_match=bool(act_ok), decided_match=bool(dec_ok),
                         kind=None if mine is None else mine["kind"],
                         seed_frozen=ft["book"],
                         seed_mine=None if mine is None else mine["book"],
                         seed_bit_equal=bool(seed_d == 0.0)))
    # segment t0 chain (32 = LO + 31 acts)
    t0s_frozen = [str(pd.Timestamp(s["t0"]).date()) for s in frozen_segs]
    t0s_mine = [str(LO.date())] + [t["act"] for t in ht]
    seg_t0_match = sum(int(a == b) for a, b in zip(t0s_frozen, t0s_mine))
    n_harvest = sum(1 for t in ht if t["kind"] == "harvest")
    sunday = [t for t in ht if pd.Timestamp(t.get("decided")).dayofweek == 6]
    final_ok = bool(harness["final_eqc"] == FINAL_EQC_TARGET)
    ok = (len(ht) == len(frozen_trigs)
          and n_date_match == len(frozen_trigs)
          and n_decided_match == len(frozen_trigs)
          and seg_t0_match == len(frozen_segs)
          and seed_maxdiff == 0.0 and n_harvest == 0 and final_ok)
    return dict(n_triggers_frozen=len(frozen_trigs), n_triggers_mine=len(ht),
                act_dates_matched=n_date_match,
                decided_dates_matched=n_decided_match,
                segment_t0_matched=f"{seg_t0_match}/{len(frozen_segs)}",
                seeds_max_abs_diff=seed_maxdiff,
                seeds_all_bit_equal=bool(seed_maxdiff == 0.0),
                final_eqc=harness["final_eqc"],
                final_eqc_bit_equal=final_ok,
                final_eqc_target=FINAL_EQC_TARGET,
                n_harvest_fires=n_harvest,
                sunday_decided_reproduced=[t["decided"] for t in sunday],
                harvest_headroom_max_slot_over_thr=harness["harvest_headroom"],
                per_trigger=rows, PASS=bool(ok))


def live_differential(live, harness):
    lt, ht = live["triggers"], harness["triggers"]
    n = max(len(lt), len(ht))
    date_diffs = []
    for j in range(n):
        a = ht[j] if j < len(ht) else None
        b = lt[j] if j < len(lt) else None
        if a is None or b is None or a["act"] != b["act"] \
                or a.get("decided") != b.get("decided"):
            date_diffs.append(dict(j=j,
                                   harness=None if a is None else
                                   dict(decided=a.get("decided"), act=a["act"]),
                                   live=None if b is None else
                                   dict(decided=b.get("decided"), act=b["act"])))
    seed_maxdiff = 0.0
    for a, b in zip(harness["seeds"], live["seeds"]):
        seed_maxdiff = max(seed_maxdiff, abs(a - b))
    held_rows = live["telemetry"]
    n_decision_diff = sum(1 for r in held_rows if r["decision_differs"])
    max_lag = max(r["max_first_print_lag_days"] for r in live["lag_rows"])
    return dict(n_triggers_harness=len(ht), n_triggers_live=len(lt),
                trigger_dates_identical=bool(not date_diffs),
                date_diffs=date_diffs,
                seeds_max_abs_diff=seed_maxdiff,
                final_eqc_live=live["final_eqc"],
                final_eqc_equal=bool(live["final_eqc"] == harness["final_eqc"]),
                n_held_rows=len(held_rows),
                n_held_rows_decision_differs=n_decision_diff,
                held_rows=held_rows,
                max_first_print_lag_days=max_lag,
                per_segment_lags=live["lag_rows"],
                harvest_headroom_max_slot_over_thr=live["harvest_headroom"])


# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--frozen-tgt", action="store_true",
                    help="drive from the frozen book() targets instead of the "
                         "UNIT-1 live steppers (diagnostic)")
    args = ap.parse_args()
    t_start = time.time()

    print("[1/5] prime IC feed + book('BTC_REP','USTEC') + leg arrays", flush=True)
    CR.prime_feed("ic")
    sleeves = CR.book("BTC_REP", "USTEC")
    insts = sorted({inst for legs in sleeves.values() for inst, _ in legs})
    arrays = {inst: CR.leg_arrays(inst) for inst in insts}
    frozen = json.loads(CR.VERIFICATION_JSON.read_text())
    assert frozen["status"] == "reconciled"
    frozen_trigs = frozen["triggers"]
    frozen_segs = frozen["segments"]

    print("[2/5] UNIT-1 live targets (core_signal_reference steppers)", flush=True)
    if args.frozen_tgt:
        sleeves_t = sleeves
        tgt_regression = "skipped (--frozen-tgt)"
    else:
        tgt_live = CS.generate_all_targets(arrays)
        # G-S1 regression: live targets must still be bit-zero vs book()
        leg_id = 0
        n_bit = 0
        sleeves_t = {}
        for name, legs in sleeves.items():
            sleeves_t[name] = []
            for inst, tgt in legs:
                eq = bool(np.array_equal(tgt_live[leg_id],
                                         np.asarray(tgt, dtype=np.float64)))
                n_bit += int(eq)
                sleeves_t[name].append((inst, tgt_live[leg_id]))
                leg_id += 1
        tgt_regression = f"{n_bit}/9 legs bit-equal vs frozen book()"
        print(f"      {tgt_regression}", flush=True)
        assert n_bit == 9, "UNIT-1 regression: live tgt no longer bit-zero"

    print("[3/5] HARNESS chain (anchor-exact detector)", flush=True)
    harness = harness_chain(sleeves_t, arrays)
    gs3 = gate_g_s3(harness, frozen_trigs, frozen_segs)
    print(f"      G-S3: acts {gs3['act_dates_matched']}/{gs3['n_triggers_frozen']} "
          f"decided {gs3['decided_dates_matched']}/{gs3['n_triggers_frozen']} "
          f"seg_t0 {gs3['segment_t0_matched']} "
          f"seeds max|d|={gs3['seeds_max_abs_diff']} "
          f"harvest={gs3['n_harvest_fires']} "
          f"final_eqc_bit={gs3['final_eqc_bit_equal']} "
          f"PASS={gs3['PASS']}", flush=True)

    diff = None
    if not args.skip_live:
        print("[4/5] LIVE chain (causal hold-at-legcap + telemetry)", flush=True)
        live = live_chain(sleeves_t, arrays)
        diff = live_differential(live, harness)
        print(f"      LIVE: dates identical={diff['trigger_dates_identical']} "
              f"seeds max|d|={diff['seeds_max_abs_diff']} "
              f"held rows={diff['n_held_rows']} "
              f"(decision differs on {diff['n_held_rows_decision_differs']}) "
              f"max first-print lag={diff['max_first_print_lag_days']}d",
              flush=True)

    print("[5/5] writing report", flush=True)
    report = dict(generated=pd.Timestamp.now().isoformat(),
                  params=dict(up=UP, down=DOWN, kmult=KMULT,
                              min_gap_days=MIN_GAP_DAYS,
                              probe_months=list(PROBE_MONTHS),
                              window=[str(LO), str(HI)], W=W7,
                              init=float(CR.INIT)),
                  target_source=("frozen book()" if args.frozen_tgt else
                                 "core_signal_reference live steppers"),
                  tgt_regression=tgt_regression,
                  G_S3=gs3,
                  harness_triggers=harness["triggers"],
                  live_triggers=(None if args.skip_live else live["triggers"]),
                  live_differential=diff,
                  runtime_s=round(time.time() - t_start, 1))
    OUT_JSON.write_text(json.dumps(report, indent=1))
    ok = gs3["PASS"] and (diff is None or (diff["trigger_dates_identical"]
                                           and diff["seeds_max_abs_diff"] == 0.0))
    print(f"PASS={ok}  ({OUT_JSON}, {report['runtime_s']}s)", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
