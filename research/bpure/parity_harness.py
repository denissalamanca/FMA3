"""
FMA3 P1c KILL-SWITCH part 1 — unit-parity harness.

For each of the 7 shared primitives, compute the pandas reference and the
scalar-double recurrence (scalar_primitives.py) on a REAL series pulled from the
frozen research_cache, and report max RELATIVE error.  Target <= 1e-8.

Also DEMONSTRATE the two failure modes (adjust=False, ddof=0) so the mandatory
conventions are proven by divergence, not merely asserted.

Run:  cd FMA2/research && python3 /path/to/parity_harness.py
(imports pandas/numpy read-only from FMA2 cache; writes nothing there)
"""
import sys
import math
import json
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/dsalamanca/vs_env/FableMultiAssets3/research/bpure")
import scalar_primitives as S

CACHE = "/Users/dsalamanca/vs_env/FableMultiAssets2/research_cache"


def relerr(ref, got, floor=1e-12):
    """Max relative error over positions where BOTH are finite.  Also verifies
    the NaN/finite masks match exactly (a mask mismatch is a hard fail)."""
    ref = np.asarray(ref, dtype=float)
    got = np.asarray(got, dtype=float)
    assert ref.shape == got.shape, (ref.shape, got.shape)
    rnan = ~np.isfinite(ref)
    gnan = ~np.isfinite(got)
    mask_mismatch = int(np.sum(rnan != gnan))
    both = np.isfinite(ref) & np.isfinite(got)
    if both.sum() == 0:
        return dict(max_rel=math.inf, max_abs=math.inf, n=0, mask_mismatch=mask_mismatch)
    a = ref[both]
    b = got[both]
    denom = np.maximum(np.abs(a), floor)
    rel = np.abs(a - b) / denom
    return dict(max_rel=float(rel.max()), max_abs=float(np.abs(a - b).max()),
                n=int(both.sum()), mask_mismatch=mask_mismatch)


# ---------------------------------------------------------------------------
# Real inputs from the frozen cache
# ---------------------------------------------------------------------------
def load_xau_hourly_ret():
    df = pd.read_parquet(f"{CACHE}/XAUUSD_1h.parquet")
    c = df["c"].astype(float)
    ret = c.pct_change(fill_method=None)          # leading NaN preserved
    return ret


def load_xau_hourly_close():
    return pd.read_parquet(f"{CACHE}/XAUUSD_1h.parquet")["c"].astype(float)


def load_xau_daily_ret():
    c = pd.read_parquet(f"{CACHE}/XAUUSD_1h.parquet")["c"].astype(float)
    d = c.resample("1D").last().dropna()
    return d.pct_change().dropna()


def main():
    results = {}

    # ---- input series (real) ------------------------------------------------
    ret_h = load_xau_hourly_ret()             # hourly XAU returns (has NaN[0])
    close_h = load_xau_hourly_close()
    dret = load_xau_daily_ret()               # daily XAU returns

    # inject a few interior NaNs into a copy to exercise ignore_na=False decay
    ret_h_gap = ret_h.copy()
    gi = [1000, 1001, 5000, 12345]
    ret_h_gap.iloc[gi] = np.nan

    # =====================================================================
    # (1) ewm_mean  adjust=True, ignore_na=False   (realized_vol span=720)
    # =====================================================================
    span = 720
    ref = ret_h_gap.pow(2).ewm(span=span).mean()          # pandas
    got = S.ewm_mean(list(ret_h_gap.pow(2).values), span)  # scalar
    results["1_ewm_mean_span720_adjTrue"] = relerr(ref.values, got)

    # also the realized_vol composite (ewm mean of squared ret) at span=30d*24
    span2 = 30 * 24
    ref2 = ret_h.pow(2).ewm(span=span2).mean()
    got2 = S.ewm_mean(list(ret_h.pow(2).values), span2)
    results["1b_ewm_mean_span720_nogap"] = relerr(ref2.values, got2)

    # FAILURE MODE: adjust=False
    ref_aT = ret_h.pow(2).ewm(span=span).mean()
    got_aF = S.ewm_mean_adjustFALSE(list(ret_h.pow(2).values), span)
    results["1_FAILMODE_adjustFalse_vs_pandas_adjTrue"] = relerr(ref_aT.values, got_aF)
    # confirm scalar adjust=False matches pandas adjust=False (sanity)
    ref_pF = ret_h.pow(2).ewm(span=span, adjust=False).mean()
    results["1_sanity_adjustFalse_scalar_vs_pandasFalse"] = relerr(ref_pF.values, got_aF)

    # =====================================================================
    # (2) ewm_std  adjust=True, ignore_na=False, bias=False  (crisis span=250)
    # =====================================================================
    span_s = 250
    ref = dret.ewm(span=span_s).std()                     # pandas bias-corrected
    got = S.ewm_std(list(dret.values), span_s, minp=1)
    results["2_ewm_std_span250_biasFalse"] = relerr(ref.values, got)

    # with min_periods=60 (crisis actual)
    ref_mp = dret.ewm(span=span_s, min_periods=60).std()
    got_mp = S.ewm_std(list(dret.values), span_s, minp=60)
    results["2b_ewm_std_span250_minp60"] = relerr(ref_mp.values, got_mp)

    # =====================================================================
    # (3) rolling std ddof=1  (meanrev / crisis vol windows)
    # =====================================================================
    for w in (10, 30, 60):
        ref = dret.rolling(w).std()                       # ddof=1 default
        got = S.rolling_std(list(dret.values), w, ddof=1)
        results[f"3_rolling_std_w{w}_ddof1"] = relerr(ref.values, got)

    # FAILURE MODE: ddof=0
    w = 10
    ref_d1 = dret.rolling(w).std()                        # ddof=1
    got_d0 = S.rolling_std_ddof0(list(dret.values), w)    # ddof=0
    results["3_FAILMODE_ddof0_vs_pandas_ddof1"] = relerr(ref_d1.values, got_d0)
    ref_pd0 = dret.rolling(w).std(ddof=0)
    results["3_sanity_ddof0_scalar_vs_pandas_ddof0"] = relerr(ref_pd0.values, got_d0)

    # =====================================================================
    # (4) Donchian max/min, rolling(n).max().shift(1)  (carry_breakout)
    # =====================================================================
    for n in (20, 55):
        ref_hi = close_h.rolling(n).max().shift(1)
        got_hi = S.donchian_max(list(close_h.values), n)
        results[f"4_donchian_max_n{n}"] = relerr(ref_hi.values, got_hi)
        ref_lo = close_h.rolling(n).min().shift(1)
        got_lo = S.donchian_min(list(close_h.values), n)
        results[f"4_donchian_min_n{n}"] = relerr(ref_lo.values, got_lo)

    # =====================================================================
    # (5) sma  rolling(w).mean()
    # =====================================================================
    for w in (50, 200):
        ref = close_h.rolling(w).mean()
        got = S.sma(list(close_h.values), w)
        results[f"5_sma_w{w}"] = relerr(ref.values, got)

    # =====================================================================
    # (6) to_hourly  (core.to_hourly, +1d lag, ffill onto hourly grid)
    # =====================================================================
    daily_sig = dret                                       # a real daily signal
    hourly_index = close_h.index
    # pandas reference (exact core.to_hourly)
    s = daily_sig.copy()
    s.index = s.index + pd.Timedelta(days=1) + pd.Timedelta(hours=0)  # lag_hours=1 -> +0h
    ref = s.reindex(hourly_index.union(s.index)).ffill().reindex(hourly_index)
    # scalar
    daily_ts = daily_sig.index.view("int64").tolist()
    daily_val = list(daily_sig.values)
    hourly_ts = hourly_index.view("int64").tolist()
    got = S.to_hourly(daily_ts, daily_val, hourly_ts, lag_days=1, lag_hours=1)
    results["6_to_hourly_lag1d"] = relerr(ref.values, got)

    # =====================================================================
    # (7) daily finalize  resample('1D').last()
    # =====================================================================
    ser = close_h                                          # hourly series
    ref = ser.resample("1D").last()
    ts = ser.index.view("int64").tolist()
    val = list(ser.values)
    out_ts, out_val = S.resample_1d_last(ts, val)
    # align on timestamps
    ref_ts = ref.index.view("int64").tolist()
    ts_match = (ref_ts == out_ts)
    results["7_resample_1d_last"] = relerr(ref.values, out_val)
    results["7_resample_1d_last"]["ts_index_match"] = bool(ts_match)

    # ---- report -------------------------------------------------------------
    print(json.dumps(results, indent=2, default=str))

    print("\n" + "=" * 72)
    print("PARITY SUMMARY (target max_rel <= 1e-8 for real primitives)")
    print("=" * 72)
    fails = []
    for k, v in results.items():
        rel = v["max_rel"]
        mm = v.get("mask_mismatch", 0)
        is_fail_probe = "FAILMODE" in k
        ok = (rel <= 1e-8 and mm == 0)
        tag = "PASS" if ok else ("DIVERGES(expected)" if is_fail_probe else "FAIL")
        if (not ok) and (not is_fail_probe):
            fails.append(k)
        print(f"  {tag:>18}  {k:<48} max_rel={rel:.3e}  max_abs={v['max_abs']:.3e}  "
              f"mask_mm={mm}  n={v['n']}")
    print("=" * 72)
    print("HARD FAILS:", fails if fails else "NONE")
    return results, fails


if __name__ == "__main__":
    main()
