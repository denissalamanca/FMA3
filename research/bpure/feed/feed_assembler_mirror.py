"""feed_assembler_mirror.py — terminal-independent gate for CFeedAssembler
(mt5/ea/Include/Book/FeedAssembler.mqh), the M1 multi-symbol live-feed
assembler (UNIT A of the S2 feed work).

WHAT IT PROVES (all bitwise, no terminal):

  1. CopyRates SIMULATION IS FAITHFUL — the frozen record feed
     (NSF5/cache/bars_1m_ic/<SYM>_IC_1m.parquet) was built by
     build_ic_feed.py as  ask = bid + spread_points * point  (one integer
     spread per M1 bar, applied to all four OHLC fields).  A live EA gets
     exactly (o,h,l,c=bid, spread_points) from CopyRates.  This mirror
     recovers spread_points = rint((ask_c-bid_c)/point) per bar and asserts
     the reconstruction  bid_* + spread_points*point == frozen ask_*  is
     BIT-EXACT on all four fields of all 37 symbols.  That is the entire
     information content of the frozen feed: a terminal CopyRates row
     reproduces it exactly (given the same bars — RECON-6/S0 territory).

  2. THE ASSEMBLY RULE IS EXACT — from those simulated CopyRates bars this
     script re-assembles, per quarter, the M1 union grid (union of the 31
     book symbols' + EURJPY's native minutes), the 31-char has mask, the
     SIX-FIELD float32-quantized price rows (bid_o/ask_o, bid_c/ask_c,
     bid_l/ask_h; ffill carry, `pre` first-bar rule), the 8 eurq columns
     (1/f32-cross-close-mid, ffilled) and the 62 swap columns (server-
     midnight rollover, policy tables via swap_eurq_generator), and diffs
     them against the INSTALLED golden bundle FMA3_bh_inputs_<Q>.csv
     (Common Files) after applying the documented reader semantics
     (%.9g -> float64 -> float32 -> float64; empty=carry / =0 for swaps).
     GATE: bit-exact (np.array_equal), union grid identical.

  3. THE H1 SIGNAL FEED RULE IS EXACT — hourly raw close per the 37
     core.ALL symbols = float64 mid (bid_c+ask_c)/2.0 of the symbol's LAST
     M1 bar in the hour, on the union hourly grid (hours with >=1 bar of
     any symbol), EMPTY where the symbol printed no bar that hour — diffed
     bitwise against research/bpure/mql5/out/FMA3_v34_inputs.csv
     (49,379 x 37, the RECON-8b master input).

  4. THE STREAMING STATE MACHINE == THE BATCH RULE — a statement twin of
     CFeedAssembler's causal per-bar path (PushBar spread reconstruction,
     minute commit, ffill carries, f32 cast, hour finalization, daily-mid
     emission incl. the EURGBP pre-20:00 variant, CSwapEurqBH twin) is run
     over a sample window and asserted bit-identical to the vectorized
     reconstruction of items 2/3 (prices/has/eurq/swaps/H1 closes) plus
     the pandas-independent daily-mid derivation.

  5. CORE-SIGNAL DAILY MIDS — the 8 daily-mid series (XAUUSD, USTEC,
     USDJPY, ETHUSD, EURGBP-pre20, AUDUSD, NZDUSD, BTCUSD; S2 design
     S2_CORE_LIVE_DESIGN.md section 2.2: (bid_c+ask_c)/2 at the last 1m
     bar of the raw-stamp day; EG restricted to raw hour < 20) derived by
     the assembler rule are asserted bitwise against an independent pandas
     resample('1D').last().dropna() derivation.

COLD-START `pre` RULE (documented divergence, RECON class): _densify fills
minutes BEFORE a symbol's first bar with that first bar's values (a
retrospective bfill the recorders baked in; SOLUSD's whole pre-2022 span is
bfilled from 2022-03-14).  The batch mirror reproduces it exactly (it has
the file); the STREAMING assembler cannot know a future first bar — it
takes an explicit SeedSymbol injection (mirrored here), counts the hits
(pre_seed_hits), and in live deploy is seeded from real prior history.
Economically inert in-record: a has=0 symbol's price is only read when
lots != 0, and lots are 0 before the first bar (tgt 0).

USAGE (frozen parquets are read-only; goldens read from Common Files):
  /usr/local/bin/python3 feed_assembler_mirror.py                 # full gate
  ... --quarters 2020Q1 2023Q3                                    # subset
  ... --skip-stream / --skip-h1 / --skip-quarters                 # partials
Writes research/bpure/feed/feed_assembler_gate.json; exit 0 iff ALL exact.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swap_eurq_generator as SEG  # noqa: E402  (policy tables, proven bit-equal)

SRC = Path("/Users/dsalamanca/vs_env/NewStrategyFable5/cache/bars_1m_ic")
COMMON_FILES = Path(
    "/Users/dsalamanca/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/users/crossover/AppData/"
    "Roaming/MetaQuotes/Terminal/Common/Files")
FMA3 = HERE.parents[2]
V34_INPUTS = FMA3 / "research/bpure/mql5/out/FMA3_v34_inputs.csv"
REPORT = HERE / "feed_assembler_gate.json"

# --- universes (MODEL names) ------------------------------------------------
# H1 signal universe = core.ALL order (37) — BOOKORC_IN_SYMS
SYMS37 = [
    "AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "EURCAD",
    "EURCHF", "EURGBP", "EURJPY", "EURNOK", "EURNZD", "EURSEK", "EURUSD",
    "GBPJPY", "GBPUSD", "NZDCAD", "NZDJPY", "NZDUSD", "USDCHF", "USDJPY",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD",
    "DAX", "JP225", "UK100", "US30", "USA500", "USTEC",
    "XAGUSD", "XAUUSD", "XBRUSD", "XNGUSD", "XPTUSD", "XTIUSD",
]
# b six-field universe = SATEQ_SYMBOLS / golden book.parquet column order (31)
BOOK31 = [
    "AUDCAD", "AUDJPY", "AUDNZD", "BTCUSD", "CADCHF", "CADJPY", "DAX",
    "ETHUSD", "EURCAD", "EURCHF", "EURGBP", "EURNOK", "EURNZD", "EURSEK",
    "EURUSD", "GBPJPY", "JP225", "NZDCAD", "NZDJPY", "SOLUSD", "UK100",
    "US30", "USA500", "USDCHF", "USDJPY", "USTEC", "XAGUSD", "XAUUSD",
    "XBRUSD", "XNGUSD", "XTIUSD",
]
CROSSES8 = ["EURCAD", "EURCHF", "EURGBP", "EURJPY",
            "EURNOK", "EURNZD", "EURSEK", "EURUSD"]
# M1 union universe = book symbols + their eurq crosses (dedup) = 31 + EURJPY
M1_SYMS = BOOK31 + ["EURJPY"]
# CoreSignal daily-mid series (S2_CORE_LIVE_DESIGN §2.2; EG = pre-20 variant)
MID_SERIES = ["XAUUSD", "USTEC", "USDJPY", "ETHUSD",
              "EURGBP", "AUDUSD", "NZDUSD", "BTCUSD"]  # EURGBP == pre-20

# digits per MODEL symbol — provenance build_ic_feed.py FEED map (the exact
# table the record feed was built with; FeedAssembler.mqh embeds the same
# and verifies live SYMBOL_DIGITS against it)
DIGITS = {
    "XAUUSD": 2, "USA500": 2, "USDJPY": 3, "ETHUSD": 2, "EURGBP": 5,
    "AUDUSD": 5, "EURUSD": 5, "EURJPY": 3, "BTCUSD": 2, "DAX": 1,
    "GBPUSD": 5, "NZDUSD": 5, "USDCHF": 5, "XAGUSD": 3, "AUDNZD": 5,
    "EURCHF": 5, "AUDCAD": 5, "NZDCAD": 5, "CADCHF": 5, "EURNOK": 5,
    "EURSEK": 5, "EURNZD": 5, "EURCAD": 5, "AUDJPY": 3, "NZDJPY": 3,
    "GBPJPY": 3, "CADJPY": 3, "US30": 2, "USTEC": 2, "JP225": 2,
    "UK100": 2, "XTIUSD": 2, "XBRUSD": 2, "XNGUSD": 4, "XPTUSD": 2,
    "SOLUSD": 4, "XRPUSD": 4,
}

PRICE_FIELDS = [("bo", "bid_o"), ("ao", "ask_o"), ("bc", "bid_c"),
                ("ac", "ask_c"), ("bl", "bid_l"), ("ah", "ask_h")]
QUARTERS = [str(p) for p in pd.period_range("2020Q1", "2025Q4", freq="Q")]


def parse_f64(col: pd.Series) -> np.ndarray:
    """empty -> NaN, else CORRECTLY-ROUNDED string->float64 (numpy astype;
    pd.to_numeric's legacy xstrtod is 1-ulp imprecise and must NOT be used
    on %.17g goldens)."""
    a = col.to_numpy()
    out = np.full(len(a), np.nan)
    m = a != ""
    out[m] = a[m].astype(np.float64)
    return out

T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:8.1f}s] {msg}", flush=True)


# ===========================================================================
# 1. load + CopyRates-simulation (spread recovery, reconstruction assert)
# ===========================================================================
class Sym:
    __slots__ = ("name", "ts", "f32", "spread_pts", "point",
                 "hour_ts", "hclose", "recon_ok", "n")

    def __init__(self, name: str):
        self.name = name
        df = pd.read_parquet(SRC / f"{name}_IC_1m.parquet")
        idx = df.index.values.astype("datetime64[ns]").astype(np.int64)
        assert (idx % (60 * 10**9) == 0).all(), f"{name}: non-minute stamps"
        assert (np.diff(idx) > 0).all(), f"{name}: stamps not increasing"
        self.ts = idx // 10**9
        self.n = len(self.ts)
        self.point = 10.0 ** (-DIGITS[name])
        b = {f: df[f].to_numpy() for f in
             ("bid_o", "bid_h", "bid_l", "bid_c",
              "ask_o", "ask_h", "ask_l", "ask_c")}
        p = np.rint((b["ask_c"] - b["bid_c"]) / self.point)
        sp = p * self.point
        ok = True
        for x in ("o", "h", "l", "c"):
            ok &= bool(np.array_equal(b["bid_" + x] + sp, b["ask_" + x]))
        self.recon_ok = ok
        self.spread_pts = p.astype(np.int64)
        # six-field b feed: float32-quantized (the _native cast)
        self.f32 = {short: b[field].astype(np.float32)
                    for short, field in PRICE_FIELDS}
        # H1 raw close: float64 mid of the LAST bar of each hour
        mid = (b["bid_c"] + b["ask_c"]) / 2.0
        hrs = self.ts // 3600
        last = np.flatnonzero(np.diff(hrs) != 0)
        last = np.concatenate([last, [self.n - 1]])
        self.hour_ts = hrs[last] * 3600
        self.hclose = mid[last]


def daily_mids(sym: Sym, pre20: bool):
    """(day_epoch[], mid[]) — last qualifying bar of each raw-stamp day."""
    ts, hcl = sym.ts, None
    # recompute float64 mids for qualifying bars only (memory-light)
    df = pd.read_parquet(SRC / f"{sym.name}_IC_1m.parquet",
                         columns=["bid_c", "ask_c"])
    mid = (df["bid_c"].to_numpy() + df["ask_c"].to_numpy()) / 2.0
    if pre20:
        m = (ts % 86400) // 3600 < 20
        ts, mid = ts[m], mid[m]
    day = ts // 86400
    last = np.flatnonzero(np.diff(day) != 0)
    last = np.concatenate([last, [len(day) - 1]])
    return day[last], mid[last]


# ===========================================================================
# 2. vectorized batch assembly per quarter + golden diff
# ===========================================================================
def densify(sym: Sym, grid: np.ndarray):
    """assembler ffill rule onto a union grid: last bar <= t; `pre` rule
    before the first bar (first bar's values); has = exact-minute match."""
    j = np.searchsorted(sym.ts, grid, side="right") - 1
    has = (j >= 0) & (sym.ts[np.clip(j, 0, sym.n - 1)] == grid)
    jc = np.clip(j, 0, sym.n - 1)
    out = {k: a[jc].astype(np.float64) for k, a in sym.f32.items()}
    pre = j < 0
    if pre.any():
        for k, a in sym.f32.items():
            out[k][pre] = np.float64(a[0])
    return has, out, int(pre.sum())


def parse_golden_quarter(q: str):
    path = COMMON_FILES / f"FMA3_bh_inputs_{q}.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False, engine="c")
    exp_cols = (["ts", "has"] + [f"tgt_{s}" for s in BOOK31]
                + [f"{sh}_{s}" for sh, _ in PRICE_FIELDS for s in BOOK31]
                + [f"eurq_{c}" for c in CROSSES8]
                + [f"swl_{s}" for s in BOOK31] + [f"sws_{s}" for s in BOOK31])
    assert list(df.columns) == exp_cols, f"{q}: unexpected column layout"
    ts = df["ts"].to_numpy().astype(np.int64)
    has = df["has"].to_numpy()
    dense = {}
    for sh, _ in PRICE_FIELDS:
        for s in BOOK31:
            v = parse_f64(df[f"{sh}_{s}"])
            assert v[0] == v[0], f"{q}:{sh}_{s} row0 not explicit"
            # reader rule: parse f64 -> cast f32 -> upcast f64, then carry
            v = v.astype(np.float32).astype(np.float64)
            dense[f"{sh}_{s}"] = pd.Series(v).ffill().to_numpy()
    for c in CROSSES8:
        v = parse_f64(df[f"eurq_{c}"])
        assert v[0] == v[0], f"{q}:eurq_{c} row0 not explicit"
        dense[f"eurq_{c}"] = pd.Series(v).ffill().to_numpy()
    for pre in ("swl", "sws"):
        for s in BOOK31:
            dense[f"{pre}_{s}"] = np.nan_to_num(parse_f64(df[f"{pre}_{s}"]))
    return ts, has, dense


def swap_columns(grid: np.ndarray):
    """_swap_chunk twin via swap_eurq_generator's proven tables: accrual at
    the first grid bar >= server midnight of each day, day range
    normalize(first)..normalize(last)+1D, weekends skipped unless crypto,
    payload pct/100/365*mult accumulating."""
    T = len(grid)
    la = np.zeros((T, len(BOOK31)))
    sa = np.zeros((T, len(BOOK31)))
    d0 = (int(grid[0]) // 86400) * 86400
    d1 = (int(grid[-1]) // 86400) * 86400 + 86400
    for k, s in enumerate(BOOK31):
        for day in range(d0, d1 + 1, 86400):
            if not SEG.is_swap_day(s, day):
                continue
            j = int(np.searchsorted(grid, day, side="left"))
            if j >= T:
                continue
            mult = SEG.swap_day_multiplier(s, day)
            lp, sp = SEG.swap_annual_pct(s, day)
            la[j, k] += lp / 100.0 / 365.0 * mult
            sa[j, k] += sp / 100.0 / 365.0 * mult
    return la, sa


def run_quarter(q: str, syms: dict, findings: list) -> dict:
    per = pd.Period(q, freq="Q")
    qs = per.start_time.value // 10**9
    qe = per.end_time.value // 10**9
    grids = []
    for s in M1_SYMS:
        t = syms[s].ts
        lo = np.searchsorted(t, qs, side="left")
        hi = np.searchsorted(t, qe, side="right")
        grids.append(t[lo:hi])
    grid = np.unique(np.concatenate(grids))

    g_ts, g_has, g_dense = parse_golden_quarter(q)
    rep = {"quarter": q, "rows": int(len(grid)), "golden_rows": int(len(g_ts))}
    grid_ok = bool(np.array_equal(grid, g_ts))
    rep["union_grid_ok"] = grid_ok
    if not grid_ok:
        d = np.setdiff1d(grid, g_ts)[:5].tolist()
        e = np.setdiff1d(g_ts, grid)[:5].tolist()
        findings.append(f"{q}: UNION GRID MISMATCH mine-only {d} golden-only {e}")
        rep["mine_only_first"] = d
        rep["golden_only_first"] = e
        return rep  # value diffs meaningless off-grid

    has_rows = np.zeros((len(grid), len(BOOK31)), dtype=bool)
    mine = {}
    pre_hits = 0
    for k, s in enumerate(BOOK31):
        h, out, pre = densify(syms[s], grid)
        pre_hits += pre
        has_rows[:, k] = h
        for sh, _ in PRICE_FIELDS:
            mine[f"{sh}_{s}"] = out[sh]
    # eurq: 1 / (0.5*(f32 bid_c + f32 ask_c)) of the cross, same ffill rule
    for c in CROSSES8:
        _, out, pre = densify(syms[c], grid)
        pre_hits += pre
        mine[f"eurq_{c}"] = 1.0 / (0.5 * (out["bc"] + out["ac"]))
    la, sa = swap_columns(grid)
    for k, s in enumerate(BOOK31):
        mine[f"swl_{s}"] = la[:, k]
        mine[f"sws_{s}"] = sa[:, k]

    mine_has = np.array(["".join("1" if b else "0" for b in row)
                         for row in has_rows])
    has_ok = bool(np.array_equal(mine_has, g_has))
    rep["has_ok"] = has_ok
    if not has_ok:
        bad = np.flatnonzero(mine_has != g_has)
        findings.append(f"{q}: HAS mismatch at {len(bad)} rows, first ts "
                        f"{int(grid[bad[0]])}")
        rep["has_bad_rows"] = int(len(bad))

    maxd = 0.0
    n_mismatch = 0
    worst = None
    for name, a in mine.items():
        b = g_dense[name]
        if np.array_equal(a, b):
            continue
        neq = a != b
        n_mismatch += int(neq.sum())
        d = float(np.max(np.abs(a[neq] - b[neq])))
        if d >= maxd:
            maxd = d
            i = int(np.flatnonzero(neq)[0])
            worst = {"col": name, "ts": int(grid[i]),
                     "mine": float(a[i]), "golden": float(b[i])}
    rep["pre_rule_hits"] = int(pre_hits)
    rep["value_cells_mismatched"] = n_mismatch
    rep["max_abs_diff"] = maxd
    rep["bit_exact"] = bool(grid_ok and has_ok and n_mismatch == 0)
    if worst:
        rep["worst"] = worst
        findings.append(f"{q}: {n_mismatch} cells differ, max|diff| {maxd:.3e}"
                        f" at {worst['col']} ts {worst['ts']}")
    log(f"{q}: rows {len(grid):,} grid_ok {grid_ok} has_ok {has_ok} "
        f"cells_mismatched {n_mismatch} max|diff| {maxd:.3e} "
        f"pre_hits {pre_hits}")
    return rep


# ===========================================================================
# 3. H1 signal feed vs FMA3_v34_inputs.csv
# ===========================================================================
def run_h1(syms: dict, findings: list) -> dict:
    union = np.unique(np.concatenate([syms[s].hour_ts for s in SYMS37]))
    cols = {}
    for s in SYMS37:
        v = np.full(len(union), np.nan)
        pos = np.searchsorted(union, syms[s].hour_ts)
        v[pos] = syms[s].hclose
        cols[s] = v

    df = pd.read_csv(V34_INPUTS, dtype=str, keep_default_na=False, engine="c")
    assert list(df.columns) == ["timestamp"] + SYMS37, "v34 header mismatch"
    g_ts = df["timestamp"].to_numpy().astype(np.int64)
    rep = {"rows": int(len(union)), "golden_rows": int(len(g_ts))}
    grid_ok = bool(np.array_equal(union, g_ts))
    rep["union_grid_ok"] = grid_ok
    if not grid_ok:
        findings.append("H1: union hourly grid mismatch "
                        f"({len(union)} vs {len(g_ts)})")
        return rep
    n_mismatch = 0
    maxd = 0.0
    worst = None
    for s in SYMS37:
        g = parse_f64(df[s])
        a = cols[s]
        eq = (a == g) | (np.isnan(a) & np.isnan(g))
        if eq.all():
            continue
        neq = ~eq
        n_mismatch += int(neq.sum())
        both = neq & ~np.isnan(a) & ~np.isnan(g)
        d = float(np.max(np.abs(a[both] - g[both]))) if both.any() else float("inf")
        if d >= maxd:
            maxd = d
            i = int(np.flatnonzero(neq)[0])
            worst = {"sym": s, "ts": int(union[i]),
                     "mine": float(a[i]), "golden": float(g[i])}
    rep["value_cells_mismatched"] = n_mismatch
    rep["max_abs_diff"] = maxd
    rep["bit_exact"] = bool(grid_ok and n_mismatch == 0)
    if worst:
        rep["worst"] = worst
        findings.append(f"H1: {n_mismatch} cells differ, max {maxd:.3e} "
                        f"at {worst['sym']} ts {worst['ts']}")
    log(f"H1: {len(union):,} hours grid_ok {grid_ok} "
        f"cells_mismatched {n_mismatch} max|diff| {maxd:.3e}")
    return rep


# ===========================================================================
# 4. daily-mid series vs independent pandas derivation
# ===========================================================================
def run_daily_mids(syms: dict, findings: list) -> dict:
    rep = {}
    ok_all = True
    for s in MID_SERIES:
        pre20 = (s == "EURGBP")
        day, mid = daily_mids(syms[s], pre20)
        # independent derivation: pandas resample last + dropna
        df = pd.read_parquet(SRC / f"{s}_IC_1m.parquet",
                             columns=["bid_c", "ask_c"])
        ser = (df["bid_c"] + df["ask_c"]) / 2.0
        if pre20:
            ser = ser[ser.index.hour < 20]
        d = ser.resample("1D").last().dropna()
        gday = d.index.values.astype("datetime64[ns]").astype(np.int64) \
            // (86400 * 10**9)
        ok = bool(np.array_equal(day, gday)
                  and np.array_equal(mid, d.to_numpy()))
        ok_all &= ok
        rep[s + ("_pre20" if pre20 else "")] = {"days": int(len(day)),
                                                "bit_exact": ok}
        if not ok:
            findings.append(f"daily mid {s}: NOT bit-exact vs pandas")
    rep["all_bit_exact"] = ok_all
    log(f"daily mids: 8 series, all bit-exact {ok_all}")
    return rep


# ===========================================================================
# 5. streaming twin (statement mirror of CFeedAssembler) over a window
# ===========================================================================
class StreamTwin:
    """Causal per-bar twin of CFeedAssembler: PushBar (spread recon +
    f32 cast), minute commit on stamp advance, ffill carries, per-minute
    b row (has/six-field/eurq/swaps), hour finalization (H1 closes), and
    daily-mid emission.  Swap/eurq path mirrors CSwapEurqBH (f32 cross
    state, server-midnight day cursor, accumulating payload)."""

    def __init__(self):
        n37 = len(SYMS37)
        self.i37 = {s: i for i, s in enumerate(SYMS37)}
        self.book_ix = [self.i37[s] for s in BOOK31]
        self.m1_ix = set(self.i37[s] for s in M1_SYMS)
        self.cross_ix = [self.i37[c] for c in CROSSES8]
        self.point = [10.0 ** (-DIGITS[s]) for s in SYMS37]
        self.seeded = [False] * n37
        self.f = {sh: [0.0] * n37 for sh, _ in PRICE_FIELDS}  # f32 carries
        self.raw_bc = [0.0] * n37
        self.raw_ac = [0.0] * n37
        # cross f32 state (CSECross, f32=True) — per cross
        self.x_bid = [0.0] * 8
        self.x_ask = [0.0] * 8
        self.x_seeded = [False] * 8
        self.next_day = None            # swap day cursor
        self.cur_min = None
        self.pending = {}               # i -> (bo,bh,bl,bc, spread_pts)
        self.hour_ts = None
        self.h_close = [float("nan")] * n37
        self.h_has = [False] * n37
        self.m1_rows = []
        self.h1_rows = []
        self.mids = []                  # (series_idx, day, mid)
        self.md_day = [None] * len(MID_SERIES)
        self.md_mid = [0.0] * len(MID_SERIES)
        self.md_have = [False] * len(MID_SERIES)
        self.mid_ix = {self.i37[s]: k for k, s in enumerate(MID_SERIES)}
        self.pre_seed_hits = 0

    # -- SeedSymbol: the documented cold-start injection (pre rule) --------
    def seed_symbol(self, i, bo, bh, bl, bc, spread_pts):
        if self.seeded[i]:
            return
        sp = spread_pts * self.point[i]
        vals = {"bo": bo, "ao": bo + sp, "bc": bc, "ac": bc + sp,
                "bl": bl, "ah": bh + sp}
        for sh, _ in PRICE_FIELDS:
            self.f[sh][i] = float(np.float64(np.float32(vals[sh])))
        self.raw_bc[i] = bc
        self.raw_ac[i] = bc + sp
        self.seeded[i] = True
        self.pre_seed_hits += 1

    def seed_cross(self, c, bid_c, ask_c):
        if self.x_seeded[c]:
            return
        self.x_bid[c] = float(np.float64(np.float32(bid_c)))
        self.x_ask[c] = float(np.float64(np.float32(ask_c)))
        self.x_seeded[c] = True

    def push(self, i, ts, o, h, l, c, spread_pts):
        assert ts % 60 == 0
        if self.cur_min is not None and ts > self.cur_min:
            self._commit()
        if self.cur_min is None:
            self.cur_min = ts
        assert ts == self.cur_min, "stamps must not go backwards"
        self.pending[i] = (o, h, l, c, spread_pts)

    def advance_to(self, ts_exclusive):
        if self.cur_min is not None and self.cur_min < ts_exclusive:
            self._commit()
        if self.hour_ts is not None and self.hour_ts + 3600 <= ts_exclusive:
            self._finalize_hour()

    def _commit(self):
        M = self.cur_min
        h = M - M % 3600
        if self.hour_ts is not None and h > self.hour_ts:
            self._finalize_hour()
        if self.hour_ts is None:
            self.hour_ts = h
        hour_of_day = (M % 86400) // 3600
        day = M // 86400
        for i, (o, hi_, l, c, pts) in self.pending.items():
            sp = pts * self.point[i]
            ao, ah, ac = o + sp, hi_ + sp, c + sp
            vals = {"bo": o, "ao": ao, "bc": c, "ac": ac, "bl": l, "ah": ah}
            for sh, _ in PRICE_FIELDS:
                self.f[sh][i] = float(np.float64(np.float32(vals[sh])))
            self.raw_bc[i] = c
            self.raw_ac[i] = ac
            self.seeded[i] = True
            mid = (c + ac) / 2.0
            self.h_close[i] = mid
            self.h_has[i] = True
            # daily-mid hook
            k = self.mid_ix.get(i)
            if k is not None:
                qual = (hour_of_day < 20) if MID_SERIES[k] == "EURGBP" else True
                if self.md_have[k] and day > self.md_day[k]:
                    self.mids.append((k, self.md_day[k], self.md_mid[k]))
                    self.md_have[k] = False
                if qual:
                    if self.md_have[k] and day == self.md_day[k]:
                        self.md_mid[k] = mid
                    else:
                        self.md_day[k] = day
                        self.md_mid[k] = mid
                        self.md_have[k] = True
        # b row iff any M1-universe symbol printed this minute
        if any(i in self.m1_ix for i in self.pending):
            for cix, gi in enumerate(self.cross_ix):
                if gi in self.pending:
                    o, hi_, l, c, pts = self.pending[gi]
                    sp = pts * self.point[gi]
                    self.x_bid[cix] = float(np.float64(np.float32(c)))
                    self.x_ask[cix] = float(np.float64(np.float32(c + sp)))
                    self.x_seeded[cix] = True
            if self.next_day is None:
                self.next_day = (M // 86400) * 86400
            eurq = [1.0 / (0.5 * (self.x_bid[c] + self.x_ask[c]))
                    if self.x_seeded[c] else float("nan") for c in range(8)]
            swl = [0.0] * len(BOOK31)
            sws = [0.0] * len(BOOK31)
            while self.next_day <= M:
                for k, s in enumerate(BOOK31):
                    if not SEG.is_swap_day(s, self.next_day):
                        continue
                    mult = SEG.swap_day_multiplier(s, self.next_day)
                    lp, sp_ = SEG.swap_annual_pct(s, self.next_day)
                    swl[k] += lp / 100.0 / 365.0 * mult
                    sws[k] += sp_ / 100.0 / 365.0 * mult
                self.next_day += 86400
            row = {"ts": M,
                   "has": "".join("1" if gi in self.pending else "0"
                                  for gi in self.book_ix),
                   "ready": all(self.seeded[gi] for gi in self.book_ix)
                            and all(self.x_seeded),
                   "eurq": eurq, "swl": swl, "sws": sws}
            for sh, _ in PRICE_FIELDS:
                row[sh] = [self.f[sh][gi] for gi in self.book_ix]
            self.m1_rows.append(row)
        self.pending = {}
        self.cur_min = None

    def _finalize_hour(self):
        self.h1_rows.append({"ts": self.hour_ts,
                             "close": list(self.h_close),
                             "has": list(self.h_has)})
        self.h_close = [float("nan")] * len(SYMS37)
        self.h_has = [False] * len(SYMS37)
        self.hour_ts = None


def run_stream(syms: dict, findings: list,
               w0: str = "2020-01-02", w1: str = "2020-01-22") -> dict:
    t0 = int(pd.Timestamp(w0).value // 10**9)
    t1 = int(pd.Timestamp(w1).value // 10**9)
    # pre-rule seeds: each 37-universe symbol's FIRST-EVER bar (mirrors
    # _densify `pre`); symbols first-printing inside/after the window
    # (SOLUSD 2022) get their future first bar — the documented artifact.
    tw = StreamTwin()
    for s in SYMS37:
        sy = syms[s]
        i = tw.i37[s]
        # reconstruct the first bar's CopyRates form from the frozen arrays
        df = pd.read_parquet(SRC / f"{s}_IC_1m.parquet").iloc[[0]]
        o = float(df["bid_o"].iloc[0]); h = float(df["bid_h"].iloc[0])
        l = float(df["bid_l"].iloc[0]); c = float(df["bid_c"].iloc[0])
        pts = int(sy.spread_pts[0])
        tw.seed_symbol(i, o, h, l, c, pts)
    for cix, cname in enumerate(CROSSES8):
        df = pd.read_parquet(SRC / f"{cname}_IC_1m.parquet",
                             columns=["bid_c", "ask_c"]).iloc[[0]]
        tw.seed_cross(cix, float(df["bid_c"].iloc[0]),
                      float(df["ask_c"].iloc[0]))

    # merged push tape over the window (all 37 symbols)
    tapes = []
    for s in SYMS37:
        sy = syms[s]
        lo = np.searchsorted(sy.ts, t0, side="left")
        hi = np.searchsorted(sy.ts, t1, side="left")
        if lo >= hi:
            continue
        df = pd.read_parquet(SRC / f"{s}_IC_1m.parquet").iloc[lo:hi]
        tapes.append((sy.ts[lo:hi], tw.i37[s],
                      df["bid_o"].to_numpy(), df["bid_h"].to_numpy(),
                      df["bid_l"].to_numpy(), df["bid_c"].to_numpy(),
                      sy.spread_pts[lo:hi]))
    events = []
    for ts, i, o, h, l, c, p in tapes:
        for j in range(len(ts)):
            events.append((int(ts[j]), i, float(o[j]), float(h[j]),
                           float(l[j]), float(c[j]), int(p[j])))
    events.sort(key=lambda e: (e[0], e[1]))
    for e in events:
        tw.push(e[1], e[0], e[2], e[3], e[4], e[5], e[6])
    tw.advance_to(t1)

    # ---- reference: vectorized rules over the same window ----------------
    grids = [syms[s].ts[(syms[s].ts >= t0) & (syms[s].ts < t1)]
             for s in M1_SYMS]
    grid = np.unique(np.concatenate(grids))
    ref = {}
    has_rows = np.zeros((len(grid), len(BOOK31)), dtype=bool)
    for k, s in enumerate(BOOK31):
        h, out, _ = densify(syms[s], grid)
        has_rows[:, k] = h
        for sh, _f in PRICE_FIELDS:
            ref[f"{sh}_{s}"] = out[sh]
    for c in CROSSES8:
        _, out, _ = densify(syms[c], grid)
        ref[f"eurq_{c}"] = 1.0 / (0.5 * (out["bc"] + out["ac"]))
    la, sa = swap_columns(grid)

    rep = {"window": [w0, w1], "rows_stream": len(tw.m1_rows),
           "rows_ref": int(len(grid))}
    ok = len(tw.m1_rows) == len(grid)
    if not ok:
        findings.append("stream: row count mismatch "
                        f"{len(tw.m1_rows)} vs {len(grid)}")
    n_bad = 0
    if ok:
        for r, (gi, t) in zip(tw.m1_rows, enumerate(grid)):
            if r["ts"] != int(t):
                n_bad += 1
                continue
            row_has = "".join("1" if b else "0" for b in has_rows[gi])
            if r["has"] != row_has:
                n_bad += 1
                continue
            for sh, _f in PRICE_FIELDS:
                for k, s in enumerate(BOOK31):
                    if r[sh][k] != ref[f"{sh}_{s}"][gi]:
                        n_bad += 1
            for cix, c in enumerate(CROSSES8):
                if r["eurq"][cix] != ref[f"eurq_{c}"][gi]:
                    n_bad += 1
            for k in range(len(BOOK31)):
                if r["swl"][k] != la[gi, k] or r["sws"][k] != sa[gi, k]:
                    n_bad += 1
    rep["m1_cells_mismatched"] = n_bad
    ok = ok and n_bad == 0

    # H1 rows vs vectorized hourly closes (window interior hours)
    union_h = np.unique(np.concatenate(
        [syms[s].hour_ts for s in SYMS37]))
    union_h = union_h[(union_h >= t0) & (union_h + 3600 <= t1)]
    h_bad = 0
    h_cnt = min(len(tw.h1_rows), len(union_h))
    if len(tw.h1_rows) != len(union_h):
        findings.append(f"stream: H1 rows {len(tw.h1_rows)} vs "
                        f"{len(union_h)}")
        ok = False
    for r, ht in zip(tw.h1_rows[:h_cnt], union_h[:h_cnt]):
        if r["ts"] != int(ht):
            h_bad += 1
            continue
        for s in SYMS37:
            sy = syms[s]
            j = np.searchsorted(sy.hour_ts, ht)
            gv = (float(sy.hclose[j])
                  if j < len(sy.hour_ts) and sy.hour_ts[j] == ht
                  else float("nan"))
            mv = r["close"][tw.i37[s]]
            if not (mv == gv or (mv != mv and gv != gv)):
                h_bad += 1
    rep["h1_cells_mismatched"] = h_bad
    ok = ok and h_bad == 0

    # daily mids emitted in-window vs batch derivation
    md_bad = 0
    md_cnt = 0
    for k, s in enumerate(MID_SERIES):
        day, mid = daily_mids(syms[s], s == "EURGBP")
        got = [(d, m) for (kk, d, m) in tw.mids if kk == k]
        # twin only FINALIZES a day when the next day's bar arrives inside
        # the window; compare the overlap
        exp = [(int(d), float(m)) for d, m in zip(day, mid)
               if t0 // 86400 <= d]
        exp = exp[:len(got)]
        md_cnt += len(got)
        for (gd, gm), (ed, em) in zip(got, exp):
            if gd != ed or gm != em:
                md_bad += 1
    rep["daily_mids_checked"] = md_cnt
    rep["daily_mids_mismatched"] = md_bad
    ok = ok and md_bad == 0
    rep["pre_seed_hits"] = tw.pre_seed_hits
    rep["bit_exact"] = bool(ok)
    if not ok:
        findings.append(f"stream twin NOT bit-exact: m1_bad {n_bad} "
                        f"h1_bad {h_bad} mid_bad {md_bad}")
    log(f"stream twin [{w0}..{w1}): {len(tw.m1_rows):,} m1 rows, "
        f"{len(tw.h1_rows):,} h1 rows, {md_cnt} daily mids — "
        f"bit_exact {ok} (m1_bad {n_bad} h1_bad {h_bad} mid_bad {md_bad})")
    return rep


# ===========================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quarters", nargs="*", default=QUARTERS)
    ap.add_argument("--skip-quarters", action="store_true")
    ap.add_argument("--skip-h1", action="store_true")
    ap.add_argument("--skip-stream", action="store_true")
    ap.add_argument("--report", default=str(REPORT))
    args = ap.parse_args(argv)

    findings: list[str] = []
    report = {"generated": pd.Timestamp.now().isoformat(timespec="seconds"),
              "recon_assert": {}, "quarters": [], "h1": {}, "daily_mids": {},
              "stream": {}, "findings": findings}

    log("loading 37 symbols + CopyRates-simulation assert ...")
    syms = {}
    for s in SYMS37:
        sy = Sym(s)
        syms[s] = sy
        report["recon_assert"][s] = {"bars": sy.n, "recon_ok": sy.recon_ok,
                                     "digits": DIGITS[s]}
        if not sy.recon_ok:
            findings.append(f"{s}: ask != bid + spread*point (recon FAIL)")
        log(f"  {s:8s} {sy.n:>9,} bars recon_ok {sy.recon_ok} "
            f"spread_pts max {int(sy.spread_pts.max())}")
    recon_all = all(v["recon_ok"] for v in report["recon_assert"].values())

    report["daily_mids"] = run_daily_mids(syms, findings)

    if not args.skip_h1:
        report["h1"] = run_h1(syms, findings)

    if not args.skip_stream:
        report["stream"] = run_stream(syms, findings)

    if not args.skip_quarters:
        for q in args.quarters:
            report["quarters"].append(run_quarter(q, syms, findings))

    q_ok = all(r.get("bit_exact", False) for r in report["quarters"]) \
        if report["quarters"] else None
    overall = bool(
        recon_all
        and report["daily_mids"].get("all_bit_exact", False)
        and (args.skip_h1 or report["h1"].get("bit_exact", False))
        and (args.skip_stream or report["stream"].get("bit_exact", False))
        and (args.skip_quarters or q_ok))
    report["overall_pass"] = overall
    report["runtime_seconds"] = round(time.time() - T0, 1)
    Path(args.report).write_text(json.dumps(report, indent=1))
    log(f"report -> {args.report}")
    print(f"FEED ASSEMBLER MIRROR: {'PASS' if overall else 'FAIL'} "
          f"(recon {recon_all}, mids {report['daily_mids'].get('all_bit_exact')}, "
          f"h1 {report['h1'].get('bit_exact')}, "
          f"stream {report['stream'].get('bit_exact')}, "
          f"quarters {q_ok})")
    for f in findings:
        print("  FINDING:", f)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
