"""coresignal_trigger_py.py — faithful python port of the LIVE causal
segment-boundary detector CCoreTrigger (mt5/ea/Include/Core/CoreSignal.mqh,
class CCoreTrigger). Statement-for-statement transcription of CheckDay /
OnLegBar / BeginSegment plus the exact GetState field set.

Used ONLY by the warm-start resume gate (run_coresignal_ws_gate.py) to
exercise the trigger's slot-equity segment cursor inside the folded warm
blob. Pure arithmetic — no external dependencies.
"""
from __future__ import annotations

import math

NAN = float("nan")


class CoreTriggerPy:
    def __init__(self):
        self.n_slots = 0
        self.n_legs = 0
        self.leg_slot = []
        self.slot_nlegs = []
        self.up = 0.0
        self.down = 0.0
        self.kmult = 0.0
        self.min_gap = 0
        self.W = 0.0
        # segment state
        self.seed = 0.0
        self.seg_start_day = 0
        self.leg_val = []
        self.leg_has = []
        self.slot_day = []
        self.slot_day_has = []
        self.slot_carry = []
        self.slot_carry_has = []
        self.cur_day = 0
        self.day_open = False
        # last-fire outputs
        self.decided_day = 0
        self.act_day = 0
        self.kind = ""
        self.max_share = 0.0
        self.min_share = 0.0
        self.max_slot = -1
        self.min_slot = -1
        # telemetry
        self.rows_scanned = 0
        self.held_rows = 0
        self.err = ""

    def configure(self, n_slots, n_legs, leg_slot, up, down, kmult, min_gap_days):
        self.n_slots = n_slots
        self.n_legs = n_legs
        self.slot_nlegs = [0] * n_slots
        self.leg_slot = list(leg_slot)
        for l in range(n_legs):
            self.slot_nlegs[leg_slot[l]] += 1
        self.up = up
        self.down = down
        self.kmult = kmult
        self.min_gap = min_gap_days
        self.W = 1.0 / n_slots
        self.seed = 0.0
        self.seg_start_day = 0
        self.cur_day = 0
        self.day_open = False
        self.decided_day = 0
        self.act_day = 0
        self.kind = ""
        self.max_share = 0.0
        self.min_share = 0.0
        self.max_slot = -1
        self.min_slot = -1
        self.rows_scanned = 0
        self.held_rows = 0
        self.err = ""
        self._reset_seg_arrays()
        return True

    def _reset_seg_arrays(self):
        self.leg_val = [0.0] * self.n_legs
        self.leg_has = [False] * self.n_legs
        self.slot_day = [0.0] * self.n_slots
        self.slot_day_has = [False] * self.n_slots
        self.slot_carry = [0.0] * self.n_slots
        self.slot_carry_has = [False] * self.n_slots

    def begin_segment(self, seed, act_eday):
        self.seed = seed
        self.seg_start_day = act_eday
        self.cur_day = 0
        self.day_open = False
        self._reset_seg_arrays()
        return True

    def check_day(self, ts):
        """returns fired (bool)."""
        fired = False
        d = ts // 86400
        if not self.day_open:
            self.cur_day = d
            self.day_open = True
            return False
        if d < self.cur_day:
            self.err = "non-ascending day"
            raise AssertionError(self.err)
        if d == self.cur_day:
            return False
        # raw-day rollover: finalize cur_day's frame row
        row = [0.0] * self.n_slots
        held_any = False
        for s in range(self.n_slots):
            if self.slot_day_has[s]:
                self.slot_carry[s] = self.slot_day[s]
                self.slot_carry_has[s] = True
            if self.slot_carry_has[s]:
                row[s] = self.slot_carry[s]
            else:
                row[s] = self.seed * self.W
                held_any = True
        if self.cur_day > self.seg_start_day:
            self.rows_scanned += 1
            if held_any:
                self.held_rows += 1
            tot = 0.0
            for s in range(self.n_slots):
                tot += row[s]
            hi = row[0]
            lo = row[0]
            hi_s = 0
            lo_s = 0
            for s in range(1, self.n_slots):
                if row[s] > hi:
                    hi = row[s]
                    hi_s = s
                if row[s] < lo:
                    lo = row[s]
                    lo_s = s
            sh_hi = hi / tot
            sh_lo = lo / tot
            gap_ok = (self.cur_day - self.seg_start_day) >= self.min_gap
            band_raw = (sh_hi > self.up) or (sh_lo < self.down)
            harv_raw = hi > self.kmult * self.seed * self.W
            fired_band = band_raw and gap_ok
            if fired_band or harv_raw:
                fired = True
                self.decided_day = self.cur_day
                self.act_day = self.cur_day + 1
                self.kind = "band" if fired_band else "harvest"
                self.max_share = sh_hi
                self.min_share = sh_lo
                self.max_slot = hi_s
                self.min_slot = lo_s
        self.cur_day = d
        for s in range(self.n_slots):
            self.slot_day_has[s] = False
        return fired

    def on_leg_bar(self, leg, ts, eq_c):
        if not self.day_open:
            self.cur_day = ts // 86400
            self.day_open = True
        self.leg_val[leg] = eq_c
        self.leg_has[leg] = True
        s = self.leg_slot[leg]
        v = 0.0
        for l in range(self.n_legs):
            if self.leg_slot[l] != s:
                continue
            lc = self.seed * self.W / self.slot_nlegs[s]
            v += self.leg_val[l] if self.leg_has[l] else lc
        self.slot_day[s] = v
        self.slot_day_has[s] = True
        return True
