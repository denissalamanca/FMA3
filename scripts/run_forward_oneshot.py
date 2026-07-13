#!/usr/bin/env python3
"""FMA3 2026H1 ONE-SHOT forward confirmation driver (PROTOCOL.md §4). UNRUN.

THIS SCRIPT MUST NOT BE RUN until the final FMA3 book is LOCKED and the
forward-test criteria are pre-registered. Two hard gates enforce that:

  GATE 1 (pre-registration): research/protocol/FORWARD_TEST.md must exist and
     contain the literal string 'CRITERIA COMMITTED'. Absent that, the script
     sys.exit()s without touching any data.
  GATE 2 (one-shot): if research/outputs/forward_oneshot.json already exists,
     the holdout has been consumed — the script refuses to run again.
     Consumed = logged (PROTOCOL.md §4); there is no --force.

WHAT IT DOES (when finally run)
-------------------------------
1. Loads the LOCKED configuration from the CLI-supplied JSON (nothing about
   the winning federation is hardcoded here — the winner is decided by the
   pre-registered experiment ladder and frozen into the config file).
2. Builds the 2026H1 federation matrix from the PARENTS' forward positions:
     v3.4 side — rebuilt in-process (see FMA2-SIDE LOADER below) or loaded
                 from a parquet named in the config;
     v7 side  — loaded from a parquet named in the config (see V7 SIDE).
3. Blends them with the locked mechanism/weights, restricts to the symbols
   that actually have 2026 data (loudly reporting what was dropped), and runs
   engine/record_engine_ext.py over 2026Q1..2026Q2 with the forward 1m cache
   built by scripts/build_fwd_cache.py.
4. Writes research/outputs/forward_oneshot.json + forward_oneshot_curve.parquet.

CONFIG SCHEMA (all load-bearing keys REQUIRED — no silent defaults)
-------------------------------------------------------------------
{
  "label":            str, run tag,
  "mechanism":        "static"            # the only implemented mechanism.
                                          # If the locked book adopts an
                                          # H-FED-2 rebalanced variant, extend
                                          # blend_forward() BEFORE writing
                                          # FORWARD_TEST.md — this driver
                                          # exits on unknown mechanisms.
  "w_v7":             float in [0,1],     # capital share of the v7 book
  "scale_mult":       float,              # H-FED-3 global scale multiplier
  "subequity_weighting": "constant" | "simulated",
      # constant : blend weights fixed at (w, 1-w) across 2026H1
      # simulated: each parent's forward matrix is first run ALONE through
      #            the ext engine on 2026H1 (seeded w*initial / (1-w)*initial)
      #            and blend weights drift with the realized sub-curves —
      #            the exact H-FED-1 bookkeeping (run_hfed1.build_fed_frac)
  "ustec_policy":     "proxy" | "drop",   # USTEC has no Duka 2026 feed.
      # proxy: keep USTEC exposure, priced on USTEC_PROXY_USA500_1m.parquet
      #        (USA500 prices — an explicit, documented approximation)
      # drop : zero USTEC exposure in the forward window
  "initial":          float, EUR starting balance (10000.0 = house standard),
  "v34_forward":      {"mode": "rebuild"}                      # FMA2-side loader
                    | {"mode": "parquet", "path": "<hourly frac parquet>"},
  "v7_forward":       {"frac_parquet": "<path>" | null},       # null -> v7 hook
  "combined_hard_limits": null | {"gold_cap": float, "cross_cap": float},
      # optional H-CAPS-1 result, applied to the blended+scaled matrix via
      # FMA2 ensemble.apply_hard_limits (same clip the parents shipped with)
  "run_bootstrap":    bool  # house 20d-block breach bootstrap on the curve
                            # (~85 daily obs in 2026H1 — flagged short-window)
}

FMA2-SIDE LOADER (v3.4 forward positions — implemented)
-------------------------------------------------------
FMA2's frozen sleeve parquets end 2025-12-31, but every shipped sleeve is a
pure CAUSAL function of the hourly research cache (the interface contract's
truncation test: rebuilding on extended data must leave history bit-identical).
So the loader:
  a. materializes a 37-symbol forward hourly cache in research/fwd_cache_1h/:
     the 14 Duka-covered symbols come from FMA2 research_cache_fwd (IC
     2020-2025 + validated 2026 tail, built by FMA2 build_ext_cache.py),
     the other 23 are byte-copies of research_cache (they end 2025-12-31 —
     their 2026 closes forward-fill and their returns are 0, so causal
     signals on them decay/freeze; their forward exposure is dropped anyway
     at the coverage restriction, and reported);
  b. repoints FMA2 core.CACHE (BOTH module instances: flat `core` and
     `research.core` — mag_xau imports the latter) at that directory,
     clears the lru caches, re-RUNS every shipped sleeve's make_positions()
     with frozen defaults + the mag overlay, and combines them exactly as
     eval_v34_pin_s10.build_c2 does (V2_CAPS + mag@0.05, x SCALE 10,
     apply_hard_limits with the structural gold cap);
  c. GATES the rebuild: on the 2020-2025 grid the re-run matrix must match
     the pinned construction (books.build_v34_frac_1h) to <=1e-9 — proving
     both that the re-run reproduces the frozen artifacts and that the 2026
     extension did not perturb history. Aborts otherwise;
  d. restores core.CACHE and clears the caches again.

V7 SIDE (documented stub — the ONE permitted NotImplementedError)
-----------------------------------------------------------------
The v7 band-book's 2026 positions DO NOT EXIST as artifacts:
research/outputs/v7_book_frac_1h.parquet ends 2025-12-31 because the NSF5
anchor (and the FMA3 extractor that reproduces it bit-exactly) runs on the IC
feed which ends there. Unlike the FMA2 side, v7 positions cannot be rebuilt
here: the band re-split triggers are path-dependent state of the extractor
pipeline, not a pure function of bars. Producing them requires RE-RUNNING the
extractor (engine/v7_bridge/) on a forward-extended feed — see
load_v7_forward_frac() for the exact recipe. Until that artifact exists, the
config must point "v7_forward.frac_parquet" at it, or this driver raises the
loud NotImplementedError below. DO NOT import the v7 stack in THIS process:
NSF5 lock_v5's import side-effect sets stop_out_level=1e-9, which would
poison the record engine (record_engine_ext asserts against it).

COVERAGE (documented limitation, from research/fwd_cache_1m/MANIFEST.json)
---------------------------------------------------------------------------
2026 data exists for 14 instruments only (+ the USA500-proxied USTEC);
12 end 2026-04-30 (UTC), EURUSD/XAUUSD end 2026-05-31. Every other column of
the parents' matrices is DROPPED for the forward window and the dropped 2026
gross exposure is reported in the output JSON. 2026Q2 is therefore a partial
quarter; after 2026-05-01 the book is effectively EURUSD+XAUUSD only.

Run (after lock + pre-registration, queue idle):
  python3 /Users/dsalamanca/vs_env/FableMultiAssets3/scripts/run_forward_oneshot.py \
      /path/to/locked_forward_config.json
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_FMA3 / "engine"))

import record_engine_ext as RX  # noqa: E402  (also bootstraps FMA2 imports)
import books                    # noqa: E402
import core                     # noqa: E402  FMA2 research core (flat)
import ensemble as E            # noqa: E402  FMA2 ensemble (combine/limits)
import eval_v34_pin_s10 as PIN  # noqa: E402  V2_CAPS / SCALE / MAG_W source

PATHS = RX.PATHS
FWD_1M = PATHS.RESEARCH / "fwd_cache_1m"
FWD_1H = PATHS.RESEARCH / "fwd_cache_1h"
GATE_FILE = PATHS.PROTOCOL / "FORWARD_TEST.md"
GATE_STRING = "CRITERIA COMMITTED"
OUT_JSON = PATHS.OUTPUTS / "forward_oneshot.json"
OUT_CURVE = PATHS.OUTPUTS / "forward_oneshot_curve.parquet"

FWD_QUARTERS = ("2026Q1", "2026Q2")

#: Instruments with a REAL Duka 2026H1 feed (matches build_fwd_cache.py).
FWD_REAL_SYMS = ("AUDUSD", "BTCUSD", "DAX", "ETHUSD", "EURGBP", "EURJPY",
                 "EURUSD", "GBPUSD", "NZDUSD", "USA500", "USDCHF", "USDJPY",
                 "XAGUSD", "XAUUSD")


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
def gate_preregistration() -> str:
    """GATE 1: refuse to run before the forward criteria are committed.

    Returns the sha256 of FORWARD_TEST.md so the output JSON pins exactly
    WHICH criteria document this run was executed under."""
    if not GATE_FILE.exists():
        sys.exit(
            f"REFUSED: {GATE_FILE} does not exist.\n"
            "The 2026H1 holdout is a ONE-SHOT (PROTOCOL.md §4). Write "
            "FORWARD_TEST.md with the pre-registered pass/fail criteria for "
            f"the LOCKED book, include the line '{GATE_STRING}', commit it, "
            "and only then run this driver.")
    text = GATE_FILE.read_text()
    if GATE_STRING not in text:
        sys.exit(
            f"REFUSED: {GATE_FILE} exists but does not contain "
            f"'{GATE_STRING}'.\nFinish and commit the criteria first — this "
            "gate is what makes the forward test a confirmation instead of "
            "another fitting pass.")
    return hashlib.sha256(text.encode()).hexdigest()


def gate_oneshot() -> None:
    """GATE 2: the holdout can be consumed exactly once."""
    if OUT_JSON.exists():
        sys.exit(
            f"REFUSED: {OUT_JSON} already exists — the 2026H1 holdout has "
            "been consumed and logged. There is no re-run flag by design "
            "(PROTOCOL.md §4: consumed = logged). If this is a genuine "
            "infrastructure failure, the owner must adjudicate and remove "
            "the artifact manually, and the registry must record the event.")


def load_config(argv: list[str]) -> dict:
    if len(argv) != 2:
        sys.exit("usage: run_forward_oneshot.py <locked_forward_config.json>")
    cfg_path = Path(argv[1])
    if not cfg_path.exists():
        sys.exit(f"config not found: {cfg_path}")
    cfg = json.loads(cfg_path.read_text())
    required = ("label", "mechanism", "w_v7", "scale_mult",
                "subequity_weighting", "ustec_policy", "initial",
                "v34_forward", "v7_forward", "combined_hard_limits",
                "run_bootstrap")
    missing = [k for k in required if k not in cfg]
    if missing:
        sys.exit(f"config is missing required keys: {missing} — every "
                 "load-bearing choice must be explicit in the locked config.")
    if cfg["mechanism"] != "static":
        sys.exit(
            f"mechanism {cfg['mechanism']!r} is not implemented in this "
            "driver (only 'static'). If the locked book adopted an H-FED-2 "
            "variant, extend blend_forward() to reproduce the adopted "
            "mechanics EXACTLY, re-verify against the locked 2020-2025 run, "
            "and only then pre-register FORWARD_TEST.md.")
    if not (0.0 <= float(cfg["w_v7"]) <= 1.0):
        sys.exit(f"w_v7 = {cfg['w_v7']} outside [0,1]")
    if cfg["ustec_policy"] not in ("proxy", "drop"):
        sys.exit(f"ustec_policy must be 'proxy' or 'drop', got "
                 f"{cfg['ustec_policy']!r}")
    if cfg["subequity_weighting"] not in ("constant", "simulated"):
        sys.exit("subequity_weighting must be 'constant' or 'simulated'")
    cfg["_config_path"] = str(cfg_path)
    return cfg


# ---------------------------------------------------------------------------
# FMA2-side loader
# ---------------------------------------------------------------------------
def _core_modules() -> list:
    """All loaded instances of FMA2's research core.

    The flat `core` module and the `research.core` package module are
    DISTINCT module objects when both import paths have been used (mag_xau
    uses `research.core`; everything else uses flat `core`). Cache patching
    must hit every instance or the mag overlay would silently keep reading
    the unpatched cache."""
    mods = []
    for name in ("core", "research.core"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "CACHE"):
            mods.append(m)
    return mods


def _clear_core_caches() -> None:
    for m in _core_modules():
        for fn in ("load_hourly", "universe_frames", "commission_frac",
                   "swap_accrual_matrices"):
            getattr(m, fn).cache_clear()


def _set_core_cache(path: Path) -> None:
    for m in _core_modules():
        m.CACHE = path
    _clear_core_caches()


def build_fwd_hourly_cache(force: bool = False) -> Path:
    """Materialize the 37-symbol forward hourly cache (see header, step a).

    Byte-copies keep the 2020-2025 content bit-identical to what the frozen
    sleeves were built from — the overlap gate in build_v34_forward_frac
    depends on that."""
    import shutil
    FWD_1H.mkdir(parents=True, exist_ok=True)
    built = []
    for sym in core.ALL:
        dst = FWD_1H / f"{sym}_1h.parquet"
        if dst.exists() and not force:
            continue
        fwd_src = PATHS.FMA2_CACHE_FWD / f"{sym}_1h.parquet"
        base_src = PATHS.FMA2_CACHE_1H / f"{sym}_1h.parquet"
        src = fwd_src if fwd_src.exists() else base_src
        if not src.exists():
            raise FileNotFoundError(f"no hourly cache for {sym}: {src}")
        shutil.copyfile(src, dst)
        built.append(sym)
    if built:
        print(f"[v34-loader] fwd hourly cache: copied {len(built)} symbols "
              f"-> {FWD_1H}", flush=True)
    return FWD_1H


_SLEEVE_MODULES: dict[str, object] = {}


def _sleeve_module(name: str):
    """Load a shipped FMA2 sleeve module by FILE (research/sleeves is not a
    package). Its internal `import core` resolves to the already-loaded (and
    at call time, cache-patched) flat core module."""
    if name not in _SLEEVE_MODULES:
        p = PATHS.FMA2 / "research" / "sleeves" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(
            f"fma3_fwd_sleeve_{name}", p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _SLEEVE_MODULES[name] = mod
    return _SLEEVE_MODULES[name]


def build_v34_forward_frac() -> tuple[pd.DataFrame, dict]:
    """Rebuild the SHIPPED v3.4 book on the forward-extended hourly cache.

    Mirrors eval_v34_pin_s10.build_c2 statement-for-statement, except sleeves
    are re-RUN from their frozen make_positions() defaults instead of read
    from the (2025-ending) frozen parquets. Gated: the 2020-2025 prefix must
    reproduce the pinned construction to <=1e-9 (see header, step c).

    Returns (final hourly frac matrix incl. 2026 rows, overlap report)."""
    t0 = time.time()
    print("[v34-loader] pinned 2020-2025 construction (baseline for the "
          "overlap gate) ...", flush=True)
    baseline = books.build_v34_frac_1h()

    build_fwd_hourly_cache()
    standard_cache = core.CACHE
    _set_core_cache(FWD_1H)
    try:
        grid = core.universe_frames(tuple(core.ALL))["ret"].index
        sleeves: dict[str, pd.DataFrame] = {}
        for name in PIN.V2_CAPS:
            print(f"[v34-loader]   re-running sleeve {name} on extended "
                  "cache ...", flush=True)
            mod = _sleeve_module(name)
            sleeves[name] = mod.make_positions().reindex(grid).fillna(0.0)
        mag_xau = importlib.import_module("ext_import.mag_xau")
        print("[v34-loader]   re-running mag_xau overlay ...", flush=True)
        sleeves["mag"] = mag_xau.make_positions().reindex(grid).fillna(0.0)
        weights = {**PIN.V2_CAPS, "mag": PIN.MAG_W}
        pos = E.combine(sleeves, weights) * PIN.SCALE
        gcap = E.structural_gold_cap(PIN.V2_CAPS, PIN.SCALE)
        fwd = E.apply_hard_limits(pos, gold_cap=gcap)
    finally:
        _set_core_cache(standard_cache)

    # --- overlap gate --------------------------------------------------------
    n = len(baseline.index)
    prefix_ok = fwd.index[:n].equals(baseline.index)
    if not prefix_ok:
        sys.exit("[v34-loader] ABORT: extended union grid's 2020-2025 prefix "
                 "differs from the pinned grid — the forward hourly cache "
                 "changed history (it must be a byte-copy + appended tail).")
    common_cols = [c for c in baseline.columns if c in fwd.columns]
    delta = (fwd.iloc[:n][common_cols] - baseline[common_cols]).abs()
    max_delta = float(delta.to_numpy().max())
    if max_delta > 1e-9:
        worst = delta.max().sort_values(ascending=False).head(5)
        sys.exit(
            f"[v34-loader] ABORT: re-run book deviates from the pinned "
            f"construction on 2020-2025 (max |d| {max_delta:.3e} > 1e-9). "
            f"Worst columns:\n{worst}\nA sleeve is not truncation-stable or "
            "the fwd cache perturbed history — diagnose before ANY forward "
            "number is produced.")
    n_2026 = int((fwd.index >= "2026-01-01").sum())
    report = {"overlap_rows": n, "overlap_max_abs_delta": max_delta,
              "rows_2026": n_2026, "grid_end": str(fwd.index[-1]),
              "build_sec": round(time.time() - t0, 1)}
    print(f"[v34-loader] overlap gate PASS (max|d| {max_delta:.1e} over "
          f"{n:,} rows); {n_2026:,} rows of 2026 positions, grid ends "
          f"{fwd.index[-1]}", flush=True)
    return fwd, report


def load_v34_forward_frac(cfg: dict) -> tuple[pd.DataFrame, dict]:
    spec = cfg["v34_forward"]
    if spec["mode"] == "rebuild":
        return build_v34_forward_frac()
    if spec["mode"] == "parquet":
        p = Path(spec["path"])
        df = pd.read_parquet(p)
        if df.index.tz is not None:
            sys.exit(f"{p}: index must be tz-naive server time")
        if not (df.index >= "2026-01-01").any():
            sys.exit(f"{p}: no 2026 rows — not a forward matrix")
        return df, {"loaded_from": str(p), "rows_2026":
                    int((df.index >= "2026-01-01").sum())}
    sys.exit(f"v34_forward.mode {spec['mode']!r} unknown "
             "(use 'rebuild' or 'parquet')")


# ---------------------------------------------------------------------------
# v7 side — the ONE permitted stub
# ---------------------------------------------------------------------------
def load_v7_forward_frac(cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Load the v7 band-book's 2026H1 hourly fraction matrix.

    The artifact does not exist yet (2026-07-10): the extractor output
    research/outputs/v7_book_frac_1h.parquet ends 2025-12-31. The locked
    config must point at a forward-extended extraction; absent that, this
    raises with the exact production recipe.
    """
    p = cfg["v7_forward"].get("frac_parquet")
    if p:
        path = Path(p)
        if not path.exists():
            sys.exit(f"v7_forward.frac_parquet not found: {path}")
        df = pd.read_parquet(path)
        if df.index.tz is not None:
            sys.exit(f"{path}: index must be tz-naive server time")
        if not (df.index >= "2026-01-01").any():
            sys.exit(f"{path}: no 2026 rows — this is the 2020-2025 "
                     "extraction, not a forward-extended one.")
        return df, {"loaded_from": str(path), "rows_2026":
                    int((df.index >= "2026-01-01").sum())}

    raise NotImplementedError(
        "v7 2026H1 positions do not exist as an artifact and CANNOT be "
        "rebuilt inside this driver: the band-book's re-split triggers are "
        "path-dependent extractor state, not a pure function of bars.\n"
        "To produce research/outputs/v7_book_frac_1h_fwd.parquet:\n"
        "  1. Build a forward-extended 1m bid/ask feed for every band-book "
        "instrument + EUR crosses: IC 2020-2025 history concatenated with "
        "FMA3/research/fwd_cache_1m/ 2026H1 tails (opt-in USTEC proxy "
        "decision REQUIRED for the BOOK_USTEC sleeve — keep it consistent "
        "with this config's 'ustec_policy'), exposed to NSF5's "
        "prime_feed/load_bars machinery (multifeed hot-swap path).\n"
        "  2. Re-run the FMA3 extractor (engine/v7_bridge/extract_positions"
        ".py::extract) with the window extended from HI to 2026-06-01, in a "
        "SEPARATE PROCESS from any record-engine run (importing the v7 "
        "stack sets stop_out_level=1e-9 via lock_v5 — record_engine_ext "
        "asserts against that poisoning).\n"
        "  3. The extractor's anchor gate must still reconcile the 2020-2025 "
        "window bit-exactly against research/baselines/nsf5/"
        "engine_reproduce.json BEFORE the 2026 tail is trusted (drift means "
        "stop, PROTOCOL.md §5.6).\n"
        "  4. Save the hourly fraction matrix (same convention as "
        "v7_book_frac_1h.parquet) to research/outputs/"
        "v7_book_frac_1h_fwd.parquet and set v7_forward.frac_parquet in the "
        "locked config.\n"
        "This NotImplementedError is the ONE permitted stub in the forward "
        "infrastructure (task charter 2026-07-10); it guards an unrun path.")


# ---------------------------------------------------------------------------
# Forward coverage + bar sources
# ---------------------------------------------------------------------------
def fwd_tradable_symbols(ustec_policy: str) -> list[str]:
    syms = list(FWD_REAL_SYMS)
    if ustec_policy == "proxy":
        syms.append("USTEC")
    return syms


def fwd_bar_files(symbols: list[str], ustec_policy: str) -> dict[str, str]:
    """bar_files mapping for record_engine_ext: traded symbols + the EUR
    crosses their quote currencies need. Everything explicit — an unmapped
    symbol would silently fall back to the (2025-ending) IC feed."""
    files: dict[str, str] = {}
    for s in symbols:
        if s == "USTEC":
            if ustec_policy != "proxy":
                raise ValueError("USTEC requested but policy is not 'proxy'")
            files[s] = str(FWD_1M / "USTEC_PROXY_USA500_1m.parquet")
        else:
            files[s] = str(FWD_1M / f"{s}_2026H1_1m.parquet")
    for s in symbols:
        q = core.S.INSTRUMENTS[s]["quote"]
        if q == "EUR":
            continue
        cross = RX._EUR_CROSS[q]
        if cross in files:
            continue
        if cross == "EURCHF":
            files[cross] = str(FWD_1M
                               / "EURCHF_SYNTH_EURUSDxUSDCHF_1m.parquet")
        elif (FWD_1M / f"{cross}_2026H1_1m.parquet").exists():
            files[cross] = str(FWD_1M / f"{cross}_2026H1_1m.parquet")
        else:
            raise ValueError(
                f"quote currency {q} of {s} needs cross {cross}, which has "
                "no 2026 bar source — extend build_fwd_cache.py or drop "
                f"{s} from the forward book.")
    for f in files.values():
        if not Path(f).exists():
            raise FileNotFoundError(
                f"{f} missing — run scripts/build_fwd_cache.py first")
    return files


def restrict_to_forward(frac: pd.DataFrame, tradable: list[str]
                        ) -> tuple[pd.DataFrame, dict]:
    """Keep only 2026-covered symbols; report the dropped 2026 exposure so
    the coverage haircut is an explicit, logged number (not a silent zero)."""
    w26 = frac.loc[frac.index >= "2026-01-01"]
    kept = [c for c in frac.columns if c in tradable]
    dropped = [c for c in frac.columns if c not in tradable]
    drop_gross = w26[dropped].abs().mean() if dropped else pd.Series(dtype=float)
    drop_gross = drop_gross[drop_gross > 0].sort_values(ascending=False)
    total_gross = float(w26.abs().mean().sum()) if len(w26) else float("nan")
    report = {
        "kept_symbols": kept,
        "dropped_nonzero_mean_gross_2026":
            {k: float(v) for k, v in drop_gross.items()},
        "dropped_gross_share_2026":
            (float(drop_gross.sum() / total_gross)
             if total_gross and total_gross > 0 else 0.0),
    }
    return frac[kept], report


# ---------------------------------------------------------------------------
# Federation blend (static — the H-FED-1 bookkeeping)
# ---------------------------------------------------------------------------
def blend_static(frac7: pd.DataFrame, frac34: pd.DataFrame, w: float,
                 a: pd.Series | None = None, b: pd.Series | None = None
                 ) -> pd.DataFrame:
    """Capital-weighted blend of the parents' fraction matrices.

    Port of scripts/run_hfed1.py::build_fed_frac (the pre-registered H-FED-1
    mechanics): joint target = frac7 * (w*A_h/J_h) + frac34 * ((1-w)*B_h/J_h)
    with A/B the parents' normalized sub-curves sampled causally at hour h
    and J = w*A + (1-w)*B. With a=b=None the weights are constant (A=B=1)."""
    hours = frac7.index.union(frac34.index)
    if a is None or b is None:
        wa = pd.Series(w, index=hours)
        wb = pd.Series(1.0 - w, index=hours)
    else:
        a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
        b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)
        j_h = w * a_h + (1.0 - w) * b_h
        wa = w * a_h / j_h
        wb = (1.0 - w) * b_h / j_h
    f7 = frac7.reindex(hours).fillna(0.0)
    f34 = frac34.reindex(hours).fillna(0.0)
    cols = sorted(set(f7.columns) | set(f34.columns))
    return (f7.reindex(columns=cols, fill_value=0.0).mul(wa, axis=0)
            + f34.reindex(columns=cols, fill_value=0.0).mul(wb, axis=0))


def monthly_returns(eq: pd.Series) -> dict[str, float]:
    d = eq.resample("1D").last().dropna()
    m_last = d.groupby(d.index.to_period("M")).last()
    r = m_last.pct_change()
    r.iloc[0] = float(m_last.iloc[0]) / float(eq.iloc[0]) - 1.0
    return {str(k): float(v) for k, v in r.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    gate_hash = gate_preregistration()
    gate_oneshot()
    cfg = load_config(argv)
    t0 = time.time()
    w = float(cfg["w_v7"])
    initial = float(cfg["initial"])
    print(f"[oneshot] gates passed (FORWARD_TEST.md sha256 {gate_hash[:16]}…)"
          f" | config {cfg['_config_path']}", flush=True)

    tradable = fwd_tradable_symbols(cfg["ustec_policy"])
    bar_files = fwd_bar_files(tradable, cfg["ustec_policy"])

    frac7_full, v7_info = load_v7_forward_frac(cfg)
    frac34_full, v34_info = load_v34_forward_frac(cfg)
    frac7, drop7 = restrict_to_forward(frac7_full, tradable)
    frac34, drop34 = restrict_to_forward(frac34_full, tradable)

    sub_runs = {}
    a = b = None
    if cfg["subequity_weighting"] == "simulated":
        print("[oneshot] parent sub-runs for causal blend weights ...",
              flush=True)
        r7 = RX.run_record_ext(
            frac7, start_quarter=FWD_QUARTERS[0], end_quarter=FWD_QUARTERS[1],
            bar_files=bar_files, initial=w * initial,
            label="fwd_v7_alone", verbose=True, run_bootstrap=False)
        r34 = RX.run_record_ext(
            frac34, start_quarter=FWD_QUARTERS[0],
            end_quarter=FWD_QUARTERS[1], bar_files=bar_files,
            initial=(1.0 - w) * initial,
            label="fwd_v34_alone", verbose=True, run_bootstrap=False)
        a = r7["curves"]["equity"] / r7["curves"]["equity"].iloc[0]
        b = r34["curves"]["equity"] / r34["curves"]["equity"].iloc[0]
        for tag, r in (("v7_alone", r7), ("v34_alone", r34)):
            sub_runs[tag] = {k: r[k] for k in
                             ("cagr", "maxdd_worst", "maxdd_close", "sharpe",
                              "final_equity", "n_trades", "quarterly")}

    fed = blend_static(frac7, frac34, w, a, b) * float(cfg["scale_mult"])
    if cfg["combined_hard_limits"]:
        hl = cfg["combined_hard_limits"]
        fed = E.apply_hard_limits(fed, gold_cap=float(hl["gold_cap"]),
                                  cross_cap=float(hl["cross_cap"]))

    print(f"[oneshot] fed matrix {fed.shape}; engine run "
          f"{FWD_QUARTERS[0]}..{FWD_QUARTERS[1]} ...", flush=True)
    res = RX.run_record_ext(
        fed, start_quarter=FWD_QUARTERS[0], end_quarter=FWD_QUARTERS[1],
        bar_files=bar_files, initial=initial, label=cfg["label"],
        verbose=True, run_bootstrap=bool(cfg["run_bootstrap"]))

    eq, wo = res["curves"]["equity"], res["curves"]["worst"]
    manifest = json.loads((FWD_1M / "MANIFEST.json").read_text())
    out = {
        "label": cfg["label"],
        "generated": pd.Timestamp.now().isoformat(),
        "preregistration": {"file": str(GATE_FILE), "sha256": gate_hash},
        "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "config_path": cfg["_config_path"],
        "window": {"quarters": list(FWD_QUARTERS),
                   "first_bar": str(eq.index[0]),
                   "last_bar": str(eq.index[-1]),
                   "data_end_summary": manifest["end_date_summary"]},
        "inputs": {"v7": v7_info, "v34": v34_info,
                   "v7_dropped": drop7, "v34_dropped": drop34,
                   "bar_files": bar_files},
        "sub_runs": sub_runs,
        "result": {k: res[k] for k in
                   ("cagr", "maxdd_worst", "maxdd_close", "sharpe",
                    "final_equity", "n_trades", "quarterly", "neg_quarters",
                    "breach")},
        "total_return": float(eq.iloc[-1] / initial - 1.0),
        "monthly_returns": monthly_returns(eq),
        "caveats": [
            "CAGR/Sharpe annualized from ~4 months — wide error bars.",
            "12/14 symbols end 2026-04-30; only EURUSD/XAUUSD cover May.",
            "USTEC policy: " + cfg["ustec_policy"]
            + (" (USA500 prices used for USTEC exposure)"
               if cfg["ustec_policy"] == "proxy" else ""),
            "swap carry = flat extension of last 2025 policy rates "
            "(record_engine_ext.ASSUMED_2026H1_POLICY_RATES).",
        ],
        "assumed_2026H1_policy_rates": RX.ASSUMED_2026H1_POLICY_RATES,
        "runtime_sec": round(time.time() - t0, 1),
    }
    pd.DataFrame({"equity": eq, "worst": wo}).to_parquet(OUT_CURVE)
    OUT_JSON.write_text(json.dumps(out, indent=1, default=str))
    print(f"\n[oneshot] DONE ({out['runtime_sec']:.0f}s)")
    print(f"  total return {out['total_return']:+.2%} | worst-mark DD "
          f"{res['maxdd_worst']:.2%} | trades {res['n_trades']:,}")
    print(f"  -> {OUT_JSON}\n  -> {OUT_CURVE}")
    print("  The 2026H1 holdout is now CONSUMED. Log the result in "
          "docs/REGISTRY.md and evaluate it ONLY against the criteria "
          "pre-registered in FORWARD_TEST.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
