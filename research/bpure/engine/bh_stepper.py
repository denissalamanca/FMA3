"""b_h scalar reference — v34 native standalone 1m account equity stepper.

SPEC: BH_ENGINE_SPEC.md (this directory), derived line-for-line from the
engine of record FMA2/research/account_engine_1m.py::_run_chunk (numba kernel,
frozen sha256 700ea915... in FMA3-v34-freeze-1). The MQL5 V34EquityNative is
written from the spec; THIS file is the executable cross-check between the
spec and the numba kernel.

DESIGN RULES
------------
* Pure python float64 scalars inside step() — no numba, no numpy vectorization
  across time or symbols. math.floor / a scalar sign() stand in for np.floor /
  np.sign (bit-identical on finite doubles; njit compiles strict IEEE, no
  fastmath, so python float arithmetic in the SAME order reproduces it bit for
  bit).
* Arithmetic statement order is a 1:1 transcription of _run_chunk lines
  108-207. Do not refactor groupings: float64 associativity is load-bearing.
* Inputs are built by account_engine_1m's OWN data-prep code paths
  (_native/_densify/_eurq_chunk/_swap_chunk + the tgt lag lines), imported
  READ-ONLY from FMA2 — nothing is re-derived here (iter_chunks below).
* State (balance, lots, entry, n_trades) is JSON-serializable via
  get_state()/set_state() so a live EA warm-start can be mirrored.

VALIDATION (--selfcheck [Q0 [Q1]]): per quarter, run the stepper bar-by-bar on
the exact _run_chunk input arrays and require np.array_equal (BITWISE) on
eq_c/eq_w plus identical carry state, and bitwise equality against the golden
curve slice model/v3/freeze/FMA3-v34-freeze-1/golden/curve.parquet.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

FMA2 = Path("/Users/dsalamanca/vs_env/FableMultiAssets2")
GOLDEN = Path("/Users/dsalamanca/vs_env/FableMultiAssets3/model/v3/freeze/"
              "FMA3-v34-freeze-1/golden")

for _p in (str(FMA2 / "research"), str(FMA2)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _sign(x: float) -> float:
    """np.sign on finite float64: +1.0 / -1.0 / +-0.0 passthrough."""
    if x > 0.0:
        return 1.0
    if x < 0.0:
        return -1.0
    return x


class BHAccountStepper:
    """One cross-margined EUR account over the 31-symbol v34 book, one 1m bar
    per step() call. Field-for-field mirror of _run_chunk's loop body."""

    def __init__(self, symbols, contract, comm_side, leverage, lot_step,
                 min_lot, *, stop_out_level: float = 0.5,
                 margin_cap: float = 0.9, rebalance_band: float = 0.25,
                 balance: float = 10_000.0) -> None:
        self.symbols = list(symbols)
        K = len(self.symbols)
        self.contract = [float(v) for v in contract]
        self.comm_side = [float(v) for v in comm_side]
        self.leverage = [float(v) for v in leverage]
        self.lot_step = [float(v) for v in lot_step]
        self.min_lot = [float(v) for v in min_lot]
        self.stop_out_level = float(stop_out_level)
        self.margin_cap = float(margin_cap)
        self.rebalance_band = float(rebalance_band)
        # ---- persistent state (the ONLY carry between bars) ----
        self.balance = float(balance)
        self.lots = [0.0] * K
        self.entry = [0.0] * K
        self.n_trades = 0

    # ------------------------------------------------------------ state I/O
    def get_state(self) -> dict:
        return {"balance": self.balance,
                "lots": list(self.lots),
                "entry": list(self.entry),
                "n_trades": self.n_trades,
                "symbols": list(self.symbols)}

    def set_state(self, state: dict) -> None:
        assert list(state["symbols"]) == self.symbols, "symbol order mismatch"
        self.balance = float(state["balance"])
        self.lots = [float(v) for v in state["lots"]]
        self.entry = [float(v) for v in state["entry"]]
        self.n_trades = int(state["n_trades"])

    # ------------------------------------------------------------ one bar
    def step(self, tgt, has_bar, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h,
             eurq, swap_l, swap_s):
        """One union-grid minute. Every argument is a length-K sequence of
        float64 scalars (has_bar: bools). Returns (eq_c, eq_w).

        Transcription of _run_chunk lines 108-207; section numbers match
        BH_ENGINE_SPEC.md section 5."""
        K = len(self.lots)
        lots = self.lots
        entry = self.entry
        balance = self.balance
        contract = self.contract
        comm_side = self.comm_side
        leverage = self.leverage
        lot_step = self.lot_step
        min_lot = self.min_lot

        # 1. swaps at the rollover minute
        for k in range(K):
            if lots[k] != 0.0 and (swap_l[k] != 0.0 or swap_s[k] != 0.0):
                mid = 0.5 * (bid_o[k] + ask_o[k])
                notional = abs(lots[k]) * contract[k] * mid * eurq[k]
                balance += notional * (swap_l[k] if lots[k] > 0 else swap_s[k])

        # 2. desired lots from the shared balance
        desired = [0.0] * K
        margin_sum = 0.0
        for k in range(K):
            g = tgt[k]
            if not has_bar[k]:
                desired[k] = lots[k]
                continue
            if g == 0.0:
                desired[k] = 0.0
                continue
            px = ask_o[k] if g > 0 else bid_o[k]
            unit = px * contract[k] * eurq[k]
            raw = g * balance / unit
            n = float(math.floor(abs(raw) / lot_step[k] + 1e-9))
            L = n * lot_step[k]
            if L < min_lot[k]:
                L = 0.0
            desired[k] = _sign(g) * L
            margin_sum += abs(desired[k]) * unit / leverage[k]

        shrink = 1.0
        cap = balance * self.margin_cap
        if margin_sum > cap and margin_sum > 0.0:
            shrink = cap / margin_sum

        # 3. execute fills (cross the spread), with rebalance band
        for k in range(K):
            if not has_bar[k]:
                continue
            want = desired[k] * shrink
            n = float(math.floor(abs(want) / lot_step[k] + 1e-9))
            want = _sign(want) * n * lot_step[k]
            if abs(want) < min_lot[k]:
                want = 0.0
            if (lots[k] != 0.0 and want != 0.0 and want * lots[k] > 0.0
                    and abs(want - lots[k]) / abs(lots[k]) <= self.rebalance_band):
                continue
            if want == lots[k]:
                continue
            if lots[k] != 0.0 and (want == 0.0 or want * lots[k] < 0.0
                                   or abs(want) < abs(lots[k])):
                close_lots = lots[k] if want * lots[k] <= 0.0 else lots[k] - want
                px = bid_o[k] if lots[k] > 0 else ask_o[k]
                pnl = (px - entry[k]) * close_lots * contract[k] * eurq[k]
                balance += pnl - comm_side[k] * abs(close_lots)
                lots[k] -= close_lots
                self.n_trades += 1
                if lots[k] == 0.0:
                    entry[k] = 0.0
            if want != 0.0 and abs(want) > abs(lots[k]):
                add = want - lots[k]
                px = ask_o[k] if add > 0 else bid_o[k]
                if lots[k] == 0.0:
                    entry[k] = px
                else:
                    entry[k] = (entry[k] * lots[k] + px * add) / (lots[k] + add)
                balance -= comm_side[k] * abs(add)
                lots[k] = want
                self.n_trades += 1

        # 4. joint marks (co-timed at this minute)
        unreal_c = 0.0
        unreal_w = 0.0
        margin_used = 0.0
        for k in range(K):
            if lots[k] == 0.0:
                continue
            if lots[k] > 0:
                unreal_c += (bid_c[k] - entry[k]) * lots[k] * contract[k] * eurq[k]
                unreal_w += (bid_l[k] - entry[k]) * lots[k] * contract[k] * eurq[k]
            else:
                unreal_c += (ask_c[k] - entry[k]) * lots[k] * contract[k] * eurq[k]
                unreal_w += (ask_h[k] - entry[k]) * lots[k] * contract[k] * eurq[k]
            mid_c = 0.5 * (bid_c[k] + ask_c[k])
            margin_used += abs(lots[k]) * contract[k] * mid_c * eurq[k] / leverage[k]
        eq_c = balance + unreal_c
        eq_w = balance + unreal_w

        # 5. joint stop-out on the worst co-timed mark
        if margin_used > 0.0 and eq_w < self.stop_out_level * margin_used:
            for k in range(K):
                if lots[k] == 0.0:
                    continue
                px = bid_l[k] if lots[k] > 0 else ask_h[k]
                pnl = (px - entry[k]) * lots[k] * contract[k] * eurq[k]
                balance += pnl - comm_side[k] * abs(lots[k])
                lots[k] = 0.0
                entry[k] = 0.0
            eq_c = balance
            eq_w = balance

        self.balance = balance
        return eq_c, eq_w


# ---------------------------------------------------------------------------
# Input construction — REUSES account_engine_1m's own data-prep (read-only).
# ---------------------------------------------------------------------------
def make_stepper(symbols, **kw) -> BHAccountStepper:
    """Stepper with constants pulled from FMA2 core.S (same lookups as
    simulate_account_1m lines 221-226)."""
    import core
    return BHAccountStepper(
        symbols,
        [core.S.INSTRUMENTS[s]["contract_size"] for s in symbols],
        [core.S.INSTRUMENTS[s]["commission_side"] for s in symbols],
        [core.S.INSTRUMENTS[s]["leverage"] for s in symbols],
        [core.S.INSTRUMENTS[s]["lot_step"] for s in symbols],
        [core.S.INSTRUMENTS[s]["min_lot"] for s in symbols],
        stop_out_level=float(core.S.ACCOUNT["stop_out_level"]), **kw)


def iter_chunks(pos, start_quarter: str = "2020Q1", end_quarter: str = "2025Q4"):
    """Yield per-quarter kernel input dicts, built by EXACTLY the code paths of
    simulate_account_1m (lines 235-268): A1._native / A1._densify /
    A1._eurq_chunk / A1._swap_chunk + the tgt lag lines. Nothing re-derived.

    Yields dicts with keys: qp, gidx (DatetimeIndex) and the 2-D float64
    arrays tgt, has, bid_o, ask_o, bid_c, ask_c, bid_l, ask_h, eurq,
    swap_l, swap_s (shape [T, K], K = pos.columns order)."""
    import numpy as np
    import pandas as pd
    import core
    import account_engine_1m as A1

    symbols = [c for c in pos.columns]
    crosses = sorted({A1._EUR_CROSS[core.S.INSTRUMENTS[s]["quote"]]
                      for s in symbols
                      if core.S.INSTRUMENTS[s]["quote"] != "EUR"})
    load_syms = list(dict.fromkeys(symbols + crosses))

    for qp in pd.period_range(start_quarter, end_quarter, freq="Q"):
        qs, qe = qp.start_time, qp.end_time
        grids = []
        for s in load_syms:
            idx, _ = A1._native(s)
            lo = np.searchsorted(idx, np.int64(qs.value), side="left")
            hi = np.searchsorted(idx, np.int64(qe.value), side="right")
            grids.append(idx[lo:hi])
        grid_ns = np.unique(np.concatenate(grids))
        if grid_ns.size == 0:
            continue

        has = np.zeros((len(grid_ns), len(symbols)), dtype=np.bool_)
        f = {fl: np.zeros((len(grid_ns), len(symbols))) for fl in A1._FIELDS}
        for k, s in enumerate(symbols):
            hb, out = A1._densify(s, grid_ns)
            has[:, k] = hb
            for fl in A1._FIELDS:
                f[fl][:, k] = out[fl]
        close_mid = {}
        for c in crosses:
            _, out = A1._densify(c, grid_ns)
            close_mid[c] = 0.5 * (out["bid_c"] + out["ask_c"])

        eurq = A1._eurq_chunk(symbols, grid_ns, close_mid)
        swap_l, swap_s = A1._swap_chunk(symbols, grid_ns)

        gidx = pd.DatetimeIndex(grid_ns.astype("datetime64[ns]"))
        prev_hour = gidx.floor("h") - pd.Timedelta(hours=1)
        tgt = pos.reindex(prev_hour, method=None).to_numpy()
        tgt = np.nan_to_num(tgt, nan=0.0)

        yield {"qp": qp, "gidx": gidx, "tgt": tgt, "has": has,
               "bid_o": f["bid_o"], "ask_o": f["ask_o"],
               "bid_c": f["bid_c"], "ask_c": f["ask_c"],
               "bid_l": f["bid_l"], "ask_h": f["ask_h"],
               "eurq": eurq, "swap_l": swap_l, "swap_s": swap_s}


def run_chunk_scalar(stepper: BHAccountStepper, ch) -> tuple[list, list]:
    """Step every bar of one iter_chunks dict. .tolist() converts the float64
    arrays to python floats (exact — same doubles), keeping the inner loop
    pure-scalar and ~5x faster than numpy row indexing."""
    tgt = ch["tgt"].tolist();   has = ch["has"].tolist()
    bo = ch["bid_o"].tolist();  ao = ch["ask_o"].tolist()
    bc = ch["bid_c"].tolist();  ac = ch["ask_c"].tolist()
    bl = ch["bid_l"].tolist();  ah = ch["ask_h"].tolist()
    eq = ch["eurq"].tolist()
    sl = ch["swap_l"].tolist(); ss = ch["swap_s"].tolist()
    eq_c, eq_w = [], []
    step = stepper.step
    for t in range(len(tgt)):
        c, w = step(tgt[t], has[t], bo[t], ao[t], bc[t], ac[t],
                    bl[t], ah[t], eq[t], sl[t], ss[t])
        eq_c.append(c)
        eq_w.append(w)
    return eq_c, eq_w


def run_bh_reference(pos, start_quarter: str = "2020Q1",
                     end_quarter: str = "2025Q4", *, initial: float = 10_000.0,
                     verbose: bool = True):
    """Full pure-scalar reference run. Returns (eq_c, eq_w) pandas Series on
    the 1m union grid — the b_h source curve (normalize by eq_c.iloc[0] and
    asof-ffill onto hours for the federation blend)."""
    import numpy as np
    import pandas as pd
    st = make_stepper([c for c in pos.columns], balance=initial)
    idx_parts, c_parts, w_parts = [], [], []
    for ch in iter_chunks(pos, start_quarter, end_quarter):
        c, w = run_chunk_scalar(st, ch)
        idx_parts.append(ch["gidx"])
        c_parts.append(np.asarray(c))
        w_parts.append(np.asarray(w))
        if verbose:
            print(f"  {ch['qp']}: {len(c):>7,} min | bal EUR {st.balance:,.0f} "
                  f"| trades {st.n_trades:,}", flush=True)
    idx = idx_parts[0].append(idx_parts[1:]) if len(idx_parts) > 1 else idx_parts[0]
    return (pd.Series(np.concatenate(c_parts), index=idx, name="equity"),
            pd.Series(np.concatenate(w_parts), index=idx, name="worst"))


# ---------------------------------------------------------------------------
# Self-check: bitwise parity vs the numba kernel AND the golden curve slice.
# ---------------------------------------------------------------------------
def selfcheck(start_quarter: str = "2020Q1", end_quarter: str = "2020Q1",
              out_json: str | None = None) -> dict:
    import time
    import numpy as np
    import pandas as pd
    import core
    import account_engine_1m as A1

    pos = pd.read_parquet(GOLDEN / "book.parquet")
    gold = pd.read_parquet(GOLDEN / "curve.parquet")
    symbols = [c for c in pos.columns]

    contract = np.array([core.S.INSTRUMENTS[s]["contract_size"] for s in symbols], float)
    comm = np.array([core.S.INSTRUMENTS[s]["commission_side"] for s in symbols], float)
    lev = np.array([core.S.INSTRUMENTS[s]["leverage"] for s in symbols], float)
    lstep = np.array([core.S.INSTRUMENTS[s]["lot_step"] for s in symbols], float)
    mlot = np.array([core.S.INSTRUMENTS[s]["min_lot"] for s in symbols], float)
    stop_out = float(core.S.ACCOUNT["stop_out_level"])
    assert stop_out == 0.5, f"poisoned stop_out_level {stop_out!r}"

    st = make_stepper(symbols)
    nb_balance, nb_lots, nb_entry = 10_000.0, np.zeros(len(symbols)), np.zeros(len(symbols))
    nb_trades = 0
    report = {"quarters": {}, "start": start_quarter, "end": end_quarter}
    all_bits = True
    for ch in iter_chunks(pos, start_quarter, end_quarter):
        t0 = time.time()
        sc_c, sc_w = run_chunk_scalar(st, ch)
        t_sc = time.time() - t0
        nb_c, nb_w, nb_balance, nb_lots, nb_entry, ntr = A1._run_chunk(
            ch["tgt"], ch["has"], ch["bid_o"], ch["ask_o"], ch["bid_c"],
            ch["ask_c"], ch["bid_l"], ch["ask_h"], ch["eurq"],
            ch["swap_l"], ch["swap_s"], contract, comm, lev, lstep, mlot,
            stop_out, 0.9, 0.25, nb_balance, nb_lots, nb_entry)
        nb_trades += ntr
        gslice = gold.loc[ch["gidx"][0]:ch["gidx"][-1]]
        bits_kernel = (np.array_equal(np.asarray(sc_c), nb_c)
                       and np.array_equal(np.asarray(sc_w), nb_w)
                       and st.balance == nb_balance
                       and np.array_equal(np.asarray(st.lots), nb_lots)
                       and np.array_equal(np.asarray(st.entry), nb_entry)
                       and st.n_trades == nb_trades)
        bits_golden = (len(gslice) == len(sc_c)
                       and np.array_equal(np.asarray(sc_c), gslice["equity"].to_numpy())
                       and np.array_equal(np.asarray(sc_w), gslice["worst"].to_numpy()))
        all_bits = all_bits and bits_kernel and bits_golden
        q = str(ch["qp"])
        report["quarters"][q] = {
            "bars": len(sc_c), "scalar_seconds": round(t_sc, 1),
            "bit_equal_vs_kernel": bool(bits_kernel),
            "bit_equal_vs_golden": bool(bits_golden),
            "balance_end": st.balance, "n_trades": st.n_trades}
        print(f"{q}: {len(sc_c):,} bars | scalar {t_sc:.1f}s | "
              f"kernel bit-equal {bits_kernel} | golden bit-equal {bits_golden} "
              f"| bal EUR {st.balance:,.2f} | trades {st.n_trades:,}", flush=True)
    report["all_bit_equal"] = bool(all_bits)
    report["final_balance"] = st.balance
    report["n_trades"] = st.n_trades
    report["state_roundtrip_ok"] = _state_roundtrip(st)
    if out_json:
        Path(out_json).write_text(json.dumps(report, indent=1))
    print(f"ALL BIT-EQUAL: {all_bits} | state JSON roundtrip: "
          f"{report['state_roundtrip_ok']}")
    return report


def _state_roundtrip(st: BHAccountStepper) -> bool:
    blob = json.dumps(st.get_state())
    st2 = BHAccountStepper(st.symbols, st.contract, st.comm_side, st.leverage,
                           st.lot_step, st.min_lot)
    st2.set_state(json.loads(blob))
    return (st2.balance == st.balance and st2.lots == st.lots
            and st2.entry == st.entry and st2.n_trades == st.n_trades)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--selfcheck":
        q0 = args[1] if len(args) > 1 else "2020Q1"
        q1 = args[2] if len(args) > 2 else q0
        out = args[3] if len(args) > 3 else None
        selfcheck(q0, q1, out)
    else:
        print("bh_stepper module OK. Usage: bh_stepper.py --selfcheck [Q0 [Q1 [out.json]]]")
