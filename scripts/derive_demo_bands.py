#!/usr/bin/env python3
"""Derive the DEMO_PREREGISTRATION.md fingerprint bands from pinned artifacts.

Reads ONLY frozen curve artifacts (no engine runs). Every number quoted in
research/protocol/DEMO_PREREGISTRATION.md section B3 comes from this script's
output. Reference basis:

  - blend: research/outputs/fma3_v1_pin_curve.parquet  (v1.0, w=0.70, s=1.1)
  - v7 sub-book (native basis, R8 anchor): research/outputs/v7_book_equity_1m.parquet (eqc)
  - v3.4 sub-book (native basis, scale 10): research/baselines/fma2/v34_s10_pin_curve.parquet
  - forward cross-check: research/outputs/forward_oneshot_curve.parquet (+ v34sub)

Band convention (pre-committed): monthly close-basis returns, calendar-month
resample, 72 months 2020-01..2025-12.  99% band = [min(mean - 2.576*sd, realized
min), max(mean + 2.576*sd, realized max)] -- the normal band widened to include
the realized in-sample extreme, so no pinned month is out-of-band by construction.

Usage:
  /opt/homebrew/Caskroom/miniforge/base/bin/python3 scripts/derive_demo_bands.py
"""
import pandas as pd

ROOT = "/Users/dsalamanca/vs_env/FableMultiAssets3"


def monthly(eq: pd.Series) -> pd.Series:
    m = eq.resample("ME").last().pct_change()
    m.iloc[0] = eq.resample("ME").last().iloc[0] / eq.iloc[0] - 1
    return m.dropna()


def report(eq: pd.Series, label: str) -> None:
    m = monthly(eq)
    mu, sd = m.mean(), m.std()
    lo = min(mu - 2.576 * sd, m.min())
    hi = max(mu + 2.576 * sd, m.max())
    print(f"{label}  (n={len(m)} months)")
    print(f"  mean {mu*100:+.2f}%/mo   vol {sd*100:.2f}%   neg {int((m<0).sum())}/{len(m)}")
    print(f"  min {m.min()*100:+.2f}% ({m.idxmin():%Y-%m})   max {m.max()*100:+.2f}% ({m.idxmax():%Y-%m})")
    print(f"  99% band (normal, widened to realized extremes): [{lo*100:+.2f}%, {hi*100:+.2f}%]")


def main() -> None:
    fed = pd.read_parquet(f"{ROOT}/research/outputs/fma3_v1_pin_curve.parquet")["equity"]
    v7 = pd.read_parquet(f"{ROOT}/research/outputs/v7_book_equity_1m.parquet")["eqc"]
    v34 = pd.read_parquet(f"{ROOT}/research/baselines/fma2/v34_s10_pin_curve.parquet")["equity"]

    report(fed, "FEDERATION pin (w=0.70, s=1.1, close-mark)")
    report(v7, "v7 sub-book NATIVE (R8 anchor extraction, eqc)")
    report(v34, "v3.4 sub-book NATIVE (GLOBAL_SCALE 10 pin)")

    # forward cross-checks (must reproduce FORWARD_ONESHOT.md / archive/docs-v1.0/DEMO.md)
    for name, path in [
        ("federation forward", "research/outputs/forward_oneshot_curve.parquet"),
        ("v3.4 sub forward", "research/outputs/forward_oneshot_v34sub_curve.parquet"),
    ]:
        eq = pd.read_parquet(f"{ROOT}/{path}")["equity"]["2026-01-01":"2026-04-30 23:59:59"]
        m = monthly(eq)
        path_str = " / ".join(f"{v*100:+.2f}%" for v in m)
        print(f"{name} monthly path: {path_str}   window {(eq.iloc[-1]/eq.iloc[0]-1)*100:+.2f}%")


if __name__ == "__main__":
    main()
