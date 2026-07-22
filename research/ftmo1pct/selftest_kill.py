#!/usr/bin/env python3
"""Unit-style semantics trace for the v0.2 trailing-window kill kernel.

Drives _run_chunk_kill DIRECTLY on synthetic 1-symbol data (no bar files)
and proves, with printed traces:

  T1  16:20/17:20 kill semantics — kill fires the minute FLOAT crosses
      -kill_pct x balance; the cluster is flattened at worst-side prices;
      re-entry is blocked for exactly 60 minutes (last blocked minute
      KM+59, first re-entry KM+60); the kill's realized loss ages out of
      the trailing REAL1H window EXACTLY at re-entry (no instant re-kill,
      which WOULD fire if the loss were still in the window); the
      violation census counts the episode ONCE.

  T2  Weekend continuity for a HELD cluster — a 2-day union-grid gap with
      open positions: lots/entry persist, FLOAT stays anchored at the
      ORIGINAL entry (no re-anchor at the gap: a post-gap price print that
      crosses -1% only from the original entry IS counted as a violation),
      and the overlay never treats the held cluster as flat/reset.

  T3  Cooldown expiry across a gap is timestamp-based — a kill just before
      a 2-day gap: the first post-gap minute may already re-enter (the
      cooldown expired DURING the gap) and the stale ring slots are aged
      out (no spurious kill).

  T4  Pend attribution — over all chunks of T1, initial + sum(all REAL1H
      ring flushes) + swaps == final balance exactly (nothing realized is
      ever dropped from the window feed, including kill flatten fills).

Run: python3 research/ftmo1pct/selftest_kill.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kill_engine as KE                      # noqa: E402

MIN_NS = 60_000_000_000
SENT = np.int64(-4611686018427387904)


class Acct:
    """Carryable account + overlay state for chunked kernel calls (K=1)."""

    def __init__(self, initial=100_000.0, kill_pct=0.008, loss_mode=False,
                 kill_on=True):
        self.balance = initial
        self.lots = np.zeros(1)
        self.entry = np.zeros(1)
        self.anchor = initial
        self.last_close = initial
        self.cur_day = np.int64(-1)
        self.halted = False
        self.kill_on = kill_on
        self.kill_frac = kill_pct
        self.loss_mode = loss_mode
        self.ring_ts = np.full((1, 60), SENT, dtype=np.int64)
        self.ring_net = np.zeros((1, 60))
        self.ring_loss = np.zeros((1, 60))
        self.cl_violflag = np.zeros(1, dtype=np.int64)
        self.cl_cool = np.full(1, SENT, dtype=np.int64)
        self.cl_nkills = np.zeros(1, dtype=np.int64)
        self.cl_nviol = np.zeros(1, dtype=np.int64)
        self.cl_flushed = np.zeros(1)
        self.acct_acc = np.zeros(1)
        self.swap_hist = 0.0

    def run(self, minutes, bid_c, bid_l, tgt_val=1.0, bid_o=None):
        """One kernel chunk. minutes: absolute-minute ints (gaps allowed).
        bid_c/bid_l: arrays per minute (ask side mirrors at +0 spread;
        opens default 100)."""
        T = len(minutes)
        grid_ns = np.array([m * MIN_NS for m in minutes], dtype=np.int64)
        one = np.ones((T, 1))
        bo = (np.full((T, 1), 100.0) if bid_o is None
              else np.asarray(bid_o, float).reshape(T, 1))
        bc = np.asarray(bid_c, float).reshape(T, 1)
        bl = np.asarray(bid_l, float).reshape(T, 1)
        out = KE._run_chunk_kill(
            np.full((T, 1), tgt_val),                 # tgt
            np.ones((T, 1), dtype=np.bool_),          # has_bar
            bo, bo.copy(),                            # bid_o, ask_o
            bc, bc.copy(),                            # bid_c, ask_c
            bl, bl.copy(),                            # bid_l, ask_h
            one, np.zeros((T, 1)), np.zeros((T, 1)),  # eurq, swap_l, swap_s
            np.array([1.0]), np.array([0.0]),         # contract, comm_side
            np.array([100.0]), np.array([0.01]),      # leverage, lot_step
            np.array([0.01]), np.array([0.0]),        # min_lot, vol_limit
            0.5, 0.9, 0.25,                           # stop_out, mcap, band
            self.balance, self.lots, self.entry,
            grid_ns // 86_400_000_000_000, 0.03,      # day_id, stop_frac
            self.anchor, self.last_close, self.cur_day, self.halted,
            grid_ns, np.zeros(1, dtype=np.int64), 1,  # cluster_id, n_clusters
            True, self.kill_on, self.kill_frac, self.loss_mode, 0.010,
            np.int64(60) * MIN_NS, np.int64(60) * MIN_NS,
            self.ring_ts, self.ring_net, self.ring_loss,
            self.cl_violflag, self.cl_cool, self.cl_nkills, self.cl_nviol,
            self.cl_flushed, self.acct_acc)
        (eq_c, eq_w, self.balance, self.lots, self.entry, ntr,
         self.anchor, self.last_close, self.cur_day, self.halted,
         n_st) = out
        return eq_c, eq_w, ntr, n_st


def ok(cond, msg):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {msg}")
    if not cond:
        raise SystemExit(f"SELFTEST FAILED: {msg}")


def t1_t4():
    print("T1: kill -> 60-min cooldown -> clean window at re-entry "
          "(the 16:20/17:20 trace)")
    B = 28_333_320                # arbitrary minute-aligned base, mid-day
    KM = B + 100                  # 'the 16:20 minute'
    a = Acct(kill_pct=0.008)

    # C1: minutes B..KM. Price 100 flat; at KM the bid low/close print 99.
    n = KM - B + 1
    bc = np.full(n, 100.0); bl = np.full(n, 100.0)
    bc[-1] = 99.0; bl[-1] = 99.0
    a.run(range(B, KM + 1), bc, bl)
    ok(a.lots[0] == 0.0, f"cluster flattened AT the kill minute (lots={a.lots[0]})")
    ok(a.cl_nkills[0] == 1, "exactly one kill recorded")
    ok(a.cl_cool[0] == (KM + 60) * MIN_NS,
       "cooldown expiry stamped at kill_ts + 60 min (17:20)")
    ok(a.balance == 99_000.0,
       f"kill fill at worst-side 99: 1000 lots x -1 = -1000 (bal {a.balance})")
    ok(a.cl_nviol[0] == 1,
       "violation episode counted ONCE (dd hit exactly -1.0% x balance)")

    # C2: minutes KM+1..KM+59 — the whole cooldown must stay flat.
    a.run(range(KM + 1, KM + 60), np.full(59, 100.0), np.full(59, 100.0))
    ok(a.lots[0] == 0.0, "still flat through KM+59 (last blocked minute)")
    ok(a.cl_nkills[0] == 1, "no re-kill while flat/cooling")

    # C3: minutes KM+60.. — first permitted minute; the -1000 kill loss has
    # aged out of the trailing window EXACTLY now. If it were still in the
    # window, IDEA_DD ~= -1000 <= -0.008*99000 = -792 and the kernel would
    # re-kill the fresh entry immediately.
    a.run(range(KM + 60, KM + 71), np.full(11, 100.0), np.full(11, 100.0))
    ok(a.lots[0] == 990.0,
       f"re-entered at 17:20 with 990 lots (0.008 ref=current balance 99k) "
       f"(lots={a.lots[0]})")
    ok(a.cl_nkills[0] == 1,
       "NO instant re-kill at re-entry -> the 16:20 loss aged out of the "
       "window exactly at 17:20")
    ok(a.cl_nviol[0] == 1, "violation count still 1 (episode-once)")

    print("T4: pend attribution identity over T1's three chunks")
    resid = a.balance - (100_000.0 + a.cl_flushed[0] + a.acct_acc[0])
    ok(resid == 0.0,
       f"initial + sum(ring flushes) + swaps == final balance "
       f"(resid={resid!r}; flushed={a.cl_flushed[0]}, incl. kill fills)")


def t2():
    print("T2: weekend continuity — held cluster, entry-anchored FLOAT")
    B = 28_333_320
    a = Acct(kill_pct=0.02)       # kill line -2000: must NOT fire here
    # H1: buy 1000 @100 at minute B; from B+20 the bid prints 99.05
    # (float -950: above both lines). Chunk ends at B+49 holding.
    n = 50
    bc = np.full(n, 100.0); bl = np.full(n, 100.0)
    bc[20:] = 99.05; bl[20:] = 99.05
    a.run(range(B, B + n), bc, bl)
    ok(a.lots[0] == 1000.0 and a.entry[0] == 100.0, "held 1000 lots @100 into the gap")
    ok(a.cl_nviol[0] == 0 and a.cl_nkills[0] == 0,
       "float -950: no violation (line -1000), no kill (line -2000)")

    # H2: 2-day union-grid gap (2880 min), position HELD. First 5 minutes
    # still 99.05, then a 98.95 print: from the ORIGINAL entry that is
    # -1050 <= -1% x balance -> violation. A meter re-anchored at the gap
    # (99.05) would read only -100 and count nothing.
    G = B + 49 + 2880
    n2 = 10
    bc2 = np.full(n2, 99.05); bl2 = np.full(n2, 99.05)
    bc2[5:] = 98.95; bl2[5:] = 98.95
    # keep opens at 99.0 so the band skips re-trades (lots stay 1000)
    a.run(range(G, G + n2), bc2, bl2, bid_o=np.full(n2, 99.0))
    ok(a.lots[0] == 1000.0 and a.entry[0] == 100.0,
       "position and entry survived the gap untouched (never treated as flat)")
    ok(a.cl_nkills[0] == 0, "no spurious kill across the gap")
    ok(a.cl_nviol[0] == 1,
       "post-gap violation counted from the ORIGINAL entry (-1050) -> "
       "FLOAT is entry-anchored across the weekend, no re-anchor")


def t3():
    print("T3: cooldown expiry across a gap is timestamp-based")
    B = 28_333_320
    KM = B + 100
    a = Acct(kill_pct=0.008)
    n = KM - B + 1
    bc = np.full(n, 100.0); bl = np.full(n, 100.0)
    bc[-1] = 99.0; bl[-1] = 99.0
    a.run(range(B, KM + 1), bc, bl)          # kill at KM (as in T1)
    ok(a.cl_nkills[0] == 1 and a.lots[0] == 0.0, "kill just before the gap")

    # gap of 2880 min >> 60-min cooldown: the FIRST post-gap minute may
    # re-enter (grid-minutes-elapsed logic would still block 60 bars) and
    # the ring is fully aged (no re-kill).
    G = KM + 2880
    a.run(range(G, G + 3), np.full(3, 100.0), np.full(3, 100.0))
    ok(a.lots[0] == 990.0,
       "re-entered on the FIRST post-gap minute (cooldown expired during "
       "the gap, ts-based)")
    ok(a.cl_nkills[0] == 1, "stale ring slots aged out — no spurious kill")


if __name__ == "__main__":
    t1_t4()
    t2()
    t3()
    print("\nALL SELFTESTS PASSED")
