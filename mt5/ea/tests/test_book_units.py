#!/usr/bin/env python3
"""Off-MT5 unit tests for FableFederation_V1 (SPEC.md deliverable: everything
testable without the Strategy Tester).

Three suites, each a Python MIRROR of the corresponding MQL5 module's logic:

  1. V34Replay.mqh parser/cursor mirror — header hash gate, mandatory sleeve
     column, ascending-ts strictness, keep-last-good, flatten-by-omission,
     and the repo->broker symbol map (InpV34SymbolMap: load-time translation,
     identity fallthrough, INIT_FAILED on an unavailable broker symbol) —
     property-tested on random books AND smoke-tested on the real exported CSV.
  2. Federation.mqh bookkeeping mirror — virtual sub-book arithmetic vs the
     strategy_fma3 v1.0 construction on synthetic days: the G3 invariants
     (E_v7 + E_v34 − E0 == acct equity, frictionless), SEAM-1 anti-coupling
     (v7 reseeds/band dates blind to v34 P&L), w_realized formula.
  3. Guardian.mqh trigger mirror — day anchors, gap-through triggers, halt
     latch/resume, x=0 no-op, restart-restore semantics.

Run:  python3 mt5/ea/tests/test_federation_units.py
Exit 0 = all pass. No pytest dependency (plain asserts).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

FMA3 = Path("/Users/dsalamanca/vs_env/FableMultiAssets3")
REPLAY_CSV = FMA3 / "research" / "outputs" / "mt5" / "FMA3_v34_replay.csv"

CONFIG_HASH = "51a7541cc2aaa593"          # == EA F3_V34_CONFIG_HASH
SLEEVES = ["meanrev", "carry_breakout", "seasonal", "intraday",
           "crisis", "trend_v2", "crypto_smart", "mag_xau"]
SCHEDULE = {"seasonal": (6, 5), "intraday": (21, 20)}   # (flat, no_entry)
DEFAULT_SYMBOL_MAP = "USA500=US500;DAX=DE40"            # == EA InpV34SymbolMap default

PASSED = FAILED = 0


def check(name, cond):
    global PASSED, FAILED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        print(f"  FAIL: {name}")


# =====================================================================
# 1. V34Replay.mqh mirror
# =====================================================================
def parse_symbol_map(map_str: str, available=None):
    """Mirror of F3_ParseSymbolMap: 'repo=broker;...' -> {repo: broker}.

    Semantics (== the EA): empty/malformed entries = identity (warned,
    ignored); repo==broker = identity no-op; a mapped broker symbol not
    available on the terminal (SymbolSelect fails) => None = INIT_FAILED.
    available=None mirrors a terminal where every symbol exists.
    """
    out = {}
    for entry in map_str.split(";"):
        if not entry:
            continue                              # empty entry = identity
        kv = entry.split("=")
        if len(kv) != 2 or not kv[0] or not kv[1]:
            continue                              # malformed = identity (WARN in EA)
        if kv[0] == kv[1]:
            continue                              # identity no-op
        if available is not None and kv[1] not in available:
            return None                           # SymbolSelect fail => INIT_FAILED
        out[kv[0]] = kv[1]
    return out


class ReplayMirror:
    """Line-for-line semantic mirror of F3_LoadReplay + F3_ReplayApplyHour."""

    def __init__(self, symbol_map: str = "", available=None):
        self.rows = []                 # (ts, sym, slv, frac) - sym = BROKER name
        self.flat = {s: -1 for s in range(8)}
        self.noent = {s: -1 for s in range(8)}
        self.tgt = {}                  # (slv, sym) -> frac (current vector)
        self.leg_seen = set()
        self.cursor = 0
        self.keep_last_good = 0
        self.symbol_map = symbol_map
        self.available = available

    def load(self, lines) -> bool:
        smap = parse_symbol_map(self.symbol_map, self.available)
        if smap is None:
            return False                          # INIT_FAILED (broker sym missing)
        header = lines[0].rstrip("\n")
        kv = {}
        for tok in header.split(","):
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[k] = v
        if kv.get("config_hash") != CONFIG_HASH:
            return False                                   # INIT_FAILED (G2a)
        n_bad = 0
        last_ts = 0
        for line in lines[1:]:
            line = line.rstrip("\n")
            if not line:
                continue
            f = line.split(",")
            if len(f) < 4 or not f[3]:                     # sleeve MANDATORY
                n_bad += 1
                continue
            ts = int(f[0])
            if f[3] not in SLEEVES:                        # unresolvable sleeve
                n_bad += 1
                continue
            slv = SLEEVES.index(f[3])
            if ts < last_ts:                               # ascending ts
                n_bad += 1
                continue
            last_ts = ts
            flat = int(f[4]) if len(f) >= 5 and f[4] != "" else -1
            noent = int(f[5]) if len(f) >= 6 and f[5] != "" else -1
            if flat >= 0:
                if self.flat[slv] >= 0 and self.flat[slv] != flat:
                    n_bad += 1
                else:
                    self.flat[slv] = flat
            if noent >= 0:
                if self.noent[slv] >= 0 and self.noent[slv] != noent:
                    n_bad += 1
                else:
                    self.noent[slv] = noent
            sym = smap.get(f[1], f[1])            # repo -> BROKER at intern (load time)
            self.rows.append((ts, sym, slv, float(f[2])))
            self.leg_seen.add((slv, sym))
        if n_bad > 0 or not self.rows:                     # a frozen file must be perfect
            return False
        return True

    def apply_hour(self, hour_epoch: int):
        while self.cursor < len(self.rows) and self.rows[self.cursor][0] < hour_epoch:
            self.cursor += 1
        if self.cursor >= len(self.rows) or self.rows[self.cursor][0] != hour_epoch:
            self.keep_last_good += 1                       # keep-last-good + WARN
            return
        self.tgt = {}                                      # flatten-by-omission
        while self.cursor < len(self.rows) and self.rows[self.cursor][0] == hour_epoch:
            _, sym, slv, frac = self.rows[self.cursor]
            self.tgt[(slv, sym)] = frac
            self.cursor += 1


def serialize(book: dict) -> list:
    """Exporter-format serialization of {hour_epoch: {(slv,sym): frac}}."""
    out = [f"global_scale=10.0,config_hash={CONFIG_HASH}\n"]
    for ts in sorted(book):
        legs = sorted(book[ts].items(), key=lambda kv: (kv[0][0], kv[0][1]))
        for (slv, sym), frac in legs:
            name = SLEEVES[slv]
            if name in SCHEDULE:
                fl, ne = SCHEDULE[name]
                out.append(f"{ts},{sym},{frac:.12f},{name},{fl},{ne}\n")
            else:
                out.append(f"{ts},{sym},{frac:.12f},{name}\n")
    return out


def suite_replay_parser():
    print("[1] V34Replay parser/cursor mirror")
    rng = random.Random(20260710)
    syms = ["XAUUSD", "EURUSD", "BTCUSD", "USTEC", "USDJPY", "AUDNZD"]

    # --- property test: 50 random books round-trip exactly ---
    for trial in range(50):
        hours = sorted(rng.sample(range(1577923200, 1577923200 + 400 * 3600, 3600),
                                  rng.randint(5, 40)))
        book = {}
        for ts in hours:
            legs = {}
            for _ in range(rng.randint(0, 10)):
                slv = rng.randrange(8)
                sym = rng.choice(syms)
                v = rng.uniform(-2, 2)
                if abs(v) > 1e-9:
                    legs[(slv, sym)] = round(v, 12)
            book[ts] = legs
        mir = ReplayMirror()
        ok = mir.load(serialize(book))
        check(f"trial{trial} load", ok)
        state = {}
        klg = 0
        grid = range(min(hours), max(hours) + 3600, 3600)
        for h in grid:
            mir.apply_hour(h)
            if h in book:
                if book[h]:                       # populated hour: full swap
                    state = dict(book[h])
                else:                             # hour with zero legs = absent = keep-last
                    klg += 1
            else:
                klg += 1
            live = {k: v for k, v in mir.tgt.items() if abs(v) > 0}
            want = {k: v for k, v in state.items() if abs(v) > 0}
            if live != want:
                check(f"trial{trial} hour {h} vector", False)
                break
        else:
            check(f"trial{trial} vectors", True)
        check(f"trial{trial} keep-last-good count", mir.keep_last_good == klg)

    # --- G2a: tampered hash rejected ---
    lines = serialize({1577923200: {(0, "EURUSD"): 0.5}})
    bad = [lines[0].replace(CONFIG_HASH[0], "f" if CONFIG_HASH[0] != "f" else "e", 1)] + lines[1:]
    check("tampered hash -> INIT_FAILED", ReplayMirror().load(bad) is False)
    # --- missing sleeve column rejected (stricter than FMA2) ---
    bad = [lines[0], "1577923200,EURUSD,0.5\n"]
    check("missing sleeve col -> INIT_FAILED", ReplayMirror().load(bad) is False)
    # --- unresolvable sleeve rejected ---
    bad = [lines[0], "1577923200,EURUSD,0.5,not_a_sleeve\n"]
    check("unresolvable sleeve -> INIT_FAILED", ReplayMirror().load(bad) is False)
    # --- descending ts rejected ---
    bad = [lines[0], "1577930400,EURUSD,0.5,meanrev\n", "1577923200,EURUSD,0.5,meanrev\n"]
    check("descending ts -> INIT_FAILED", ReplayMirror().load(bad) is False)
    # --- empty file rejected ---
    check("no data rows -> INIT_FAILED", ReplayMirror().load([lines[0]]) is False)

    # --- repo->broker symbol map (InpV34SymbolMap mirror) ---
    ts0 = 1577923200
    mapped_book = serialize({ts0: {(0, "USA500"): 0.4, (1, "DAX"): -0.3,
                                   (2, "EURUSD"): 0.2}})
    # default map: USA500->US500, DAX->DE40, everything else identity
    mir = ReplayMirror(symbol_map=DEFAULT_SYMBOL_MAP)
    check("default map loads", mir.load(mapped_book))
    mir.apply_hour(ts0)
    check("default map: USA500 -> US500 at load", (0, "US500") in mir.tgt)
    check("default map: DAX -> DE40 at load", (1, "DE40") in mir.tgt)
    check("default map: unmapped EURUSD identity", (2, "EURUSD") in mir.tgt)
    check("default map: no repo names survive load",
          all(sym not in ("USA500", "DAX") for _, sym, _, _ in mir.rows))
    check("default map: fracs carried through",
          mir.tgt[(0, "US500")] == 0.4 and mir.tgt[(1, "DE40")] == -0.3)
    # identity: empty map + repo names not in the map stay verbatim
    mir = ReplayMirror(symbol_map="")
    check("empty map loads", mir.load(mapped_book))
    mir.apply_hour(ts0)
    check("empty map: all symbols identity",
          {(0, "USA500"), (1, "DAX"), (2, "EURUSD")} == set(mir.tgt))
    # identity: map entries for symbols absent from the file are inert;
    # self-maps and empty/malformed entries fall through to identity
    mir = ReplayMirror(symbol_map="GBPJPY=GBPJPY.x;;EURUSD=EURUSD;garbage")
    check("inert/self/malformed entries load", mir.load(mapped_book))
    mir.apply_hour(ts0)
    check("inert map entries: file symbols untouched",
          {(0, "USA500"), (1, "DAX"), (2, "EURUSD")} == set(mir.tgt))
    # unknown symbol failure: a mapped broker symbol the terminal does not
    # offer (SymbolSelect fails) must FAIL INIT loudly
    avail = {"USA500", "DAX", "EURUSD", "US500"}          # no DE40 on this "terminal"
    mir = ReplayMirror(symbol_map=DEFAULT_SYMBOL_MAP, available=avail)
    check("unavailable broker symbol -> INIT_FAILED", mir.load(mapped_book) is False)
    # ...and with the full broker set present, the same map loads clean
    avail = {"USA500", "DAX", "EURUSD", "US500", "DE40"}
    mir = ReplayMirror(symbol_map=DEFAULT_SYMBOL_MAP, available=avail)
    check("available broker symbols -> loads", mir.load(mapped_book))

    # --- smoke test on the REAL exported artifact ---
    if REPLAY_CSV.exists():
        mir = ReplayMirror()
        with open(REPLAY_CSV) as fh:
            ok = mir.load(fh.readlines())
        check("real CSV loads clean", ok)
        check("real CSV row count", len(mir.rows) == 851013)
        check("real CSV seasonal schedule 6/5",
              mir.flat[SLEEVES.index("seasonal")] == 6 and
              mir.noent[SLEEVES.index("seasonal")] == 5)
        check("real CSV intraday schedule 21/20",
              mir.flat[SLEEVES.index("intraday")] == 21 and
              mir.noent[SLEEVES.index("intraday")] == 20)
        # replay the first 500 grid hours and cross-check against a direct index
        from collections import defaultdict
        by_hour = defaultdict(dict)
        for ts, sym, slv, frac in mir.rows[:200000]:
            by_hour[ts][(slv, sym)] = frac
        hours = sorted(by_hour)[:500]
        mir2 = ReplayMirror()
        with open(REPLAY_CSV) as fh:
            mir2.load(fh.readlines())
        ok_all = True
        state = {}
        for h in hours:
            mir2.apply_hour(h)
            state = by_hour[h]
            if mir2.tgt != state:
                ok_all = False
                break
        check("real CSV first-500-hours replay parity", ok_all)
        # default symbol map on the REAL artifact: repo names USA500/DAX must
        # come out as broker US500/DE40, everything else untouched
        mir4 = ReplayMirror(symbol_map=DEFAULT_SYMBOL_MAP)
        with open(REPLAY_CSV) as fh:
            check("real CSV loads clean under the default map", mir4.load(fh.readlines()))
        syms_raw = {s for _, s, _, _ in mir.rows}
        syms_map = {s for _, s, _, _ in mir4.rows}
        check("real CSV has repo names USA500+DAX",
              {"USA500", "DAX"} <= syms_raw and not {"US500", "DE40"} & syms_raw)
        check("default map: US500/DE40 in, USA500/DAX out",
              {"US500", "DE40"} <= syms_map and not {"USA500", "DAX"} & syms_map)
        check("default map: symbol count preserved (31)",
              len(syms_map) == len(syms_raw) == 31)
        check("default map: row count preserved", len(mir4.rows) == len(mir.rows))
    else:
        print("  (real CSV not found - smoke test skipped)")


# =====================================================================
# 2. Federation.mqh bookkeeping mirror (vs strategy_fma3 construction)
# =====================================================================
def suite_federation_books():
    print("[2] Federation bookkeeping mirror")
    sys.path.insert(0, str(FMA3))
    import strategy_fma3
    w = strategy_fma3.FMA3_CONFIG["w_v7"]
    check("strategy_fma3 lock hash", strategy_fma3.config_hash() == CONFIG_HASH)
    check("w_v7 = 0.70", abs(w - 0.70) < 1e-12)

    rng = random.Random(7)
    E0 = 10_000.0
    N7 = 7                                     # v7 slots (band book)

    for trial in range(20):
        # v7 ledger mirror (convention A: seeds sum to FULL E0)
        seed7 = [E0 / N7] * N7
        realized7 = [0.0] * N7
        seed34, realized34 = E0, 0.0
        acct_realized = 0.0
        resplit_dates_fed = []

        # identical v7 P&L stream replayed twice: once with v34 P&L, once without
        pnl7_days = [[rng.uniform(-0.03, 0.05) for _ in range(N7)] for _ in range(10)]
        pnl34_days = [rng.uniform(-0.04, 0.06) for _ in range(10)]

        def run(with_v34: bool):
            s7 = list(seed7)
            r7 = [0.0] * N7
            s34, r34 = seed34, 0.0
            acct = E0
            dates = []
            for d in range(10):
                # daily P&L realization (frictionless synthetic; floating = 0 at marks)
                for n in range(N7):
                    p = (s7[n] + r7[n]) * pnl7_days[d][n]
                    r7[n] += p
                    acct += p
                if with_v34:
                    p34 = (s34 + r34) * pnl34_days[d]
                    r34 += p34
                    acct += p34
                e7 = sum(s7[n] + r7[n] for n in range(N7))
                e34 = s34 + r34
                # G3 invariant 1 (frictionless: exact)
                assert abs(e7 + e34 - E0 - acct) < 1e-6, "invariant 1 broke"
                # band trigger on SLOT RATIOS (v7-book-pure by construction)
                slots = [s7[n] + r7[n] for n in range(N7)]
                tot = sum(slots)
                if any(sl / tot > 0.25 or sl / tot < (1 / N7) / 1.75 for sl in slots):
                    dates.append(d)
                    # SEAM 1: reseed from the v7 VIRTUAL book equity, never acct
                    pre_equity = e7
                    for n in range(N7):
                        s7[n] = pre_equity / N7
                        r7[n] = 0.0
                # w_realized (books-row formula) vs strategy_fma3 construction
                A, B = e7 / E0, e34 / E0
                w_row = w * e7 / (w * e7 + (1 - w) * e34)
                w_strat = w * A / (w * A + (1 - w) * B)
                assert abs(w_row - w_strat) < 1e-12, "w_realized formula mismatch"
            return dates, sum(s7[n] + r7[n] for n in range(N7))

        dates_fed, e7_fed = run(with_v34=True)
        dates_v7, e7_only = run(with_v34=False)
        # G3 invariant 3 (anti-coupling): v7 re-split DATES identical with and
        # without the v34 P&L stream; v7 book equity path identical too.
        check(f"trial{trial} anti-coupling: re-split dates identical",
              dates_fed == dates_v7)
        check(f"trial{trial} anti-coupling: v7 book path identical",
              abs(e7_fed - e7_only) < 1e-9)

    # negative control: coupling the reseed to ACCT equity must CHANGE the v7 path
    # (this is what SEAM 1 prevents) - build one case where it provably differs.
    s7 = [E0 / N7] * N7
    coupled = [E0 / N7] * N7
    acct = E0
    diverged = False
    rng2 = random.Random(11)
    for d in range(10):
        for n in range(N7):
            g = 0.30 if n == 0 else 0.02                     # slot 0 runs hot
            prev = s7[n]
            s7[n] *= (1 + g)
            coupled[n] *= (1 + g)
            acct += prev * g
        acct += 800.0                                        # v34 P&L lands on acct
        tot = sum(s7)
        if any(sl / tot > 0.25 for sl in s7):
            e7 = sum(s7)
            s7 = [e7 / N7] * N7
            coupled = [acct / N7] * N7                       # the BANNED coupled reseed
        if abs(sum(s7) - sum(coupled)) > 1e-9:
            diverged = True
    check("negative control: acct-coupled reseed diverges (SEAM 1 is load-bearing)",
          diverged)


# =====================================================================
# 3. Guardian.mqh trigger mirror
# =====================================================================
class GuardianMirror:
    """Semantic mirror of F3_GuardianPass (server-day anchor, halt latch)."""

    def __init__(self, x: float):
        self.x = x
        self.day = -1
        self.anchor = 0.0
        self.halted = False
        self.stops = []
        self.resumes = []
        self.state_touched = False

    def tick(self, t: int, balance: float, equity: float) -> bool:
        """Returns True if the bar pass may run (mirror of the OnTick seam)."""
        if self.x <= 0.0:
            return True                          # G4a: single branch, no state
        self.state_touched = True
        day = t // 86400
        if day != self.day:
            was = self.halted
            self.day = day
            self.halted = False
            self.anchor = max(balance, equity)
            if was:
                self.resumes.append(t)
        if not self.halted:
            if self.anchor > 0.0 and equity <= self.anchor * (1 - self.x / 100.0):
                self.halted = True
                self.stops.append(t)
        if self.halted:
            return False                         # flatten-retry + no trading
        return True


def suite_guardian():
    print("[3] Guardian trigger mirror")
    DAY = 86400

    # x=0: pure no-op on every path, no state ever touched
    g = GuardianMirror(0.0)
    ran = all(g.tick(t, 10000, 3000 + 100 * t / DAY) for t in range(0, 3 * DAY, 600))
    check("x=0 always passes, zero state", ran and not g.state_touched
          and g.stops == [] and g.resumes == [])

    # basic trigger: -2% from the day anchor
    g = GuardianMirror(2.0)
    t0 = 5 * DAY
    check("first tick of day passes", g.tick(t0, 10000, 10000))
    check("-1.9% no trigger", g.tick(t0 + 600, 10000, 9810))
    check("-2.0% exact triggers", not g.tick(t0 + 1200, 10000, 9800))
    check("still halted same day", not g.tick(t0 + 1800, 10000, 9900))
    check("halted through day end", not g.tick(t0 + DAY - 1, 10000, 10500))
    check("resumes at next server day", g.tick(t0 + DAY, 9800, 9800))
    check("one stop, one resume", len(g.stops) == 1 and len(g.resumes) == 1)
    check("new anchor from resume-day balance/equity", g.anchor == 9800)

    # gap-through: equity gaps far below the threshold in a single tick
    g = GuardianMirror(3.0)
    g.tick(0, 10000, 10000)
    check("gap-through -9% in one tick triggers", not g.tick(600, 10000, 9100))
    check("gap-through logged once", len(g.stops) == 1)

    # anchor = max(balance, equity): floating profit raises the anchor
    g = GuardianMirror(2.0)
    g.tick(10 * DAY, 10000, 10400)               # equity > balance at midnight
    check("anchor takes the max side", g.anchor == 10400)
    check("-2% from EQUITY anchor triggers", not g.tick(10 * DAY + 600, 10000, 10192))

    # trigger from a mid-day attach (anchor = attach-time snapshot)
    g = GuardianMirror(5.0)
    g.tick(int(2.5 * DAY), 8000, 8000)
    check("mid-day attach anchors at attach", g.anchor == 8000)

    # multi-day path with a stop on day 2 of 3 and clean days around it
    g = GuardianMirror(2.0)
    path = [(0, 10000, 10000), (0 + 3600, 10000, 9950),
            (DAY, 9950, 9950), (DAY + 3600, 9950, 9700),      # -2.5% -> stop
            (DAY + 7200, 9700, 9800),
            (2 * DAY, 9700, 9700), (2 * DAY + 3600, 9700, 9650)]
    results = [g.tick(*p) for p in path]
    check("multi-day: stop only on day 2",
          results == [True, True, True, False, False, True, True]
          and len(g.stops) == 1 and g.stops[0] == DAY + 3600)

    # restart-restore semantics: same-day restore keeps the halt latch
    g = GuardianMirror(2.0)
    g.tick(DAY, 10000, 10000)
    g.tick(DAY + 600, 10000, 9700)
    g2 = GuardianMirror(2.0)                     # "restarted terminal"
    g2.day, g2.anchor, g2.halted = g.day, g.anchor, g.halted   # F3_GuardLoad
    check("restart inside a halted day stays halted",
          not g2.tick(DAY + 1200, 9700, 9750))
    check("restarted instance resumes next day", g2.tick(2 * DAY, 9700, 9700))


# =====================================================================
if __name__ == "__main__":
    suite_replay_parser()
    suite_federation_books()
    suite_guardian()
    print(f"\n{PASSED} passed, {FAILED} failed")
    sys.exit(0 if FAILED == 0 else 1)
