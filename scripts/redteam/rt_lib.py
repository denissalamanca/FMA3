"""Shared plumbing for the FMA3 red-team battery (PROTOCOL.md §6).

Design rules
------------
* Module import stays CHEAP. Nothing here imports the record engine or the
  parent repos at module level, so ``python3 -c "import rt_x"`` compile
  checks and the no-engine scripts (rt_dsr, rt_cpcv_alloc) can run while a
  pre-registered experiment grid owns the machine (CPU etiquette).
* Engine access is deferred behind :class:`EngineSession`, which reuses the
  exact H-FED input loaders (``run_hfed1_lib.load_inputs``) and the engine of
  record (``record_engine.run_record``) so every red-team number is computed
  in the same accounting as the number it batters.
* The bookkeeping functions replicate ``run_hfed1.build_book_frac`` /
  ``run_hfed2.federation_weights`` arithmetic EXACTLY (same operation order,
  same rebasing conventions) with the structural parameters exposed — seeds,
  min-gap, band edges, fixed schedules.  Replaying a winner's own
  configuration must reproduce the winner's fraction matrix bit-for-bit;
  only the deliberately perturbed parameter may differ.  rt_fixed_schedule
  leans on this property as an explicit identity check.

The RT_VERDICT convention
-------------------------
Every battery script ends with exactly one line of the form::

    RT_VERDICT [<script>] <PASS|FAIL|NOT_APPLICABLE> | <one-line reason>

so a detached monitor can ``grep RT_VERDICT`` across logs.  Exit codes:
0 = PASS or NOT_APPLICABLE (both are honest terminal states), 1 = FAIL,
2 = usage / input error.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_FMA3 = Path(__file__).resolve().parents[2]
_SCRIPTS = _FMA3 / "scripts"

# Mirror of run_hfed1.W_GRID (pre-registered H-FED-1 grid).  Duplicated here
# so the no-engine scripts can use it without triggering the engine bootstrap;
# any change to the registered grid must be reflected in both places.
W_GRID: tuple[float, ...] = (0.30, 0.40, 0.50, 0.60, 0.70)

# NSF5 chaos-probe magnitude: EUR 128 on the EUR 10,000 account — the V7.1
# chaos-study perturbation that exposed the -EUR59k single-account coupling
# failure the PROTOCOL §5.7 guard exists to prevent.
CHAOS_SEED_DELTA: float = 128.0 / 10_000.0


def load_fma3_paths():
    """Load FMA3/config/paths.py by file location under a collision-free name.

    Mirrors ``record_engine._load_fma3_paths``: FMA3's repo root must never go
    on ``sys.path`` (its ``config``/``engine`` dirs shadow NSF5's packages in
    any process that later bootstraps the parents), and the no-engine scripts
    need canonical paths WITHOUT importing the engine at all.
    """
    if "fma3_paths" in sys.modules:
        return sys.modules["fma3_paths"]
    spec = importlib.util.spec_from_file_location(
        "fma3_paths", _FMA3 / "config" / "paths.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fma3_paths"] = mod
    spec.loader.exec_module(mod)
    return mod


PATHS = load_fma3_paths()
REDTEAM_DIR = PATHS.OUTPUTS / "redteam"


def log(tag: str, msg: str) -> None:
    """Detached-friendly progress line (flushed so `tail -f` sees it live)."""
    print(f"[{tag}] {msg}", flush=True)


def write_results(name: str, payload: dict[str, Any]) -> Path:
    """Write a battery result JSON to research/outputs/redteam/<name>.json."""
    REDTEAM_DIR.mkdir(parents=True, exist_ok=True)
    out = REDTEAM_DIR / f"{name}.json"
    payload = {"generated": datetime.now().isoformat(), **payload}
    out.write_text(json.dumps(payload, indent=1, default=str))
    log(name, f"results -> {out}")
    return out


def verdict(script: str, status: str, reason: str) -> int:
    """Print the greppable RT_VERDICT line; return the process exit code."""
    print(f"RT_VERDICT [{script}] {status} | {reason}", flush=True)
    return {"PASS": 0, "NOT_APPLICABLE": 0, "FAIL": 1}.get(status, 2)


# ---------------------------------------------------------------------------
# winner-config loading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FedConfig:
    """Structural blend parameters (the ONLY licensed design space).

    kind          : "static" (H-FED-1), "quarterly" (F2a) or "band" (F2b).
    core_weight          : v7 capital share; the re-split target is always (w, 1-w).
    b_up          : band upper trigger on the v7 share (band only);
                    B_dn = 1 - b_up by the registered symmetric semantics.
    min_gap_days  : minimum days between band re-splits (run_hfed2 baseline 5).
    """
    kind: str
    core_weight: float
    b_up: float | None = None
    min_gap_days: int = 5


def load_winner(results_path: Path, key: str
                ) -> tuple[FedConfig, dict, dict]:
    """Read a winning config out of an H-FED results JSON.

    Understands both runners' shapes: hfed1_results.json grid entries carry
    ``core_weight`` (static); hfed2_results.json grid entries carry ``mode``/``b_up``
    with the base w under ``data["base"]["core_weight"]``.  Returns (config, the raw
    grid entry with its recorded metric block, the full JSON).
    """
    data = json.loads(Path(results_path).read_text())
    grid = data.get("grid", {})
    if key not in grid:
        raise KeyError(
            f"key {key!r} not found in {results_path}; available grid keys: "
            f"{sorted(grid)}")
    entry = grid[key]
    if "mode" in entry:                      # H-FED-2 shape
        w = float(data["base"]["w_v7"])
        mode = entry["mode"]
        if mode == "band":
            cfg = FedConfig("band", w, b_up=float(entry["b_up"]))
        elif mode == "quarterly":
            cfg = FedConfig("quarterly", w)
        else:
            raise ValueError(f"unknown H-FED-2 mode {mode!r} in {key}")
    elif "w_v7" in entry:                    # H-FED-1 shape
        cfg = FedConfig("static", float(entry["w_v7"]))
    else:
        raise ValueError(
            f"entry {key!r} has neither 'mode' nor 'w_v7' — not an H-FED "
            "grid entry")
    return cfg, entry, data


# ---------------------------------------------------------------------------
# blend bookkeeping (exact replicas of the H-FED runners' arithmetic)
# ---------------------------------------------------------------------------

def federation_bookkeeping(a: pd.Series, b: pd.Series,
                           hours: pd.DatetimeIndex, cfg: FedConfig, *,
                           seed_a: float | None = None,
                           seed_b: float | None = None,
                           fixed_edges: list | None = None
                           ) -> tuple[pd.Series, pd.Series, list[dict]]:
    """Hourly (A*, B*) virtual sub-account bookkeeping with re-splits.

    ``a``/``b`` are the parents' NATIVE 1m curves normalized to 1.0 at t0;
    the anti-coupling guard (PROTOCOL §5.7) holds by construction because
    each book's growth factor comes only from its own native curve.

    Parameterization on top of the runners' fixed constants:
      * ``seed_a``/``seed_b``: initial bookkeeping sub-equities (default the
        registered (w, 1-w)).  The re-split TARGET stays (w, 1-w) — only the
        seed is perturbable (rt_coupling's ±EUR128 probe).
      * ``cfg.min_gap_days``: the band min-gap (run_hfed2 hardcodes 5).
      * ``fixed_edges``: replaces ALL trigger logic with an unconditional
        edge list (rt_fixed_schedule).  Rebasing then follows the BAND
        convention (native value AT the edge, ``asof(edge)``) so replaying a
        band winner's own event dates reproduces the winner bit-for-bit.

    Exactness contract: with default seeds and no fixed_edges this replicates
    run_hfed1.build_book_frac (static: A* = w·a_h, same float order) and
    run_hfed2.federation_weights (quarterly rebases at the last pre-edge
    hour, band rebases at ``asof(act)`` — both copied verbatim).
    """
    w = cfg.core_weight
    seed_a = w if seed_a is None else float(seed_a)
    seed_b = (1.0 - w) if seed_b is None else float(seed_b)

    # causal hourly samples of the native curves (run_hfed1/2 convention:
    # last known 1m value <= h; before a book's first bar its sub-equity is
    # its seed, i.e. 1.0 in normalized native units)
    a_h = a.reindex(a.index.union(hours)).ffill().reindex(hours).fillna(1.0)
    b_h = b.reindex(b.index.union(hours)).ffill().reindex(hours).fillna(1.0)

    if cfg.kind == "static" and fixed_edges is None:
        # run_hfed1 static: wa = w*a_h/j with j = w*a_h + (1-w)*b_h;
        # returning A* = seed*a_h keeps the identical float sequence.
        return seed_a * a_h, seed_b * b_h, []

    a_star = pd.Series(np.nan, index=hours)
    b_star = pd.Series(np.nan, index=hours)
    events: list[dict] = []
    seg_start = hours[0]
    ja, jb = seed_a, seed_b
    a0, b0 = float(a_h.iloc[0]), float(b_h.iloc[0])

    def grow(seg_end: pd.Timestamp) -> None:
        """Fill [seg_start, seg_end) with the current segment's growth."""
        m = (hours >= seg_start) & (hours < seg_end)
        a_star.loc[m] = ja * (a_h[m] / a0)
        b_star.loc[m] = jb * (b_h[m] / b0)

    if fixed_edges is not None or cfg.kind == "quarterly":
        if fixed_edges is not None:
            edges = sorted(pd.Timestamp(e) for e in fixed_edges)
            n_all = len(edges)
            edges = [e for e in edges if hours[0] < e <= hours[-1]]
            if len(edges) != n_all:
                log("bookkeeping", f"NOTE: {n_all - len(edges)} fixed edges "
                    "outside the sample were dropped (no-op re-splits)")
            kind_lbl, rebase_at_edge = "frozen", True
        else:
            qs = pd.date_range(hours[0].normalize(), hours[-1], freq="QS")
            edges = [e for e in qs if e > hours[0]]
            kind_lbl, rebase_at_edge = "quarter", False

        sentinel = hours[-1] + pd.Timedelta(hours=1)
        for e in list(edges) + [sentinel]:
            grow(e)
            m = (hours >= seg_start) & (hours < e)
            if not m.any():
                continue
            last = hours[m][-1]
            j = float(a_star[last] + b_star[last])
            events.append({"act": str(e), "kind": kind_lbl,
                           "v7_share_before": float(a_star[last] / j),
                           "joint": j})
            ja, jb = w * j, (1.0 - w) * j
            if rebase_at_edge:
                av, bv = a_h.asof(e), b_h.asof(e)
                a0 = float(av) if not np.isnan(av) else float(a_h[m][-1])
                b0 = float(bv) if not np.isnan(bv) else float(b_h[m][-1])
            else:
                a0, b0 = float(a_h[last]), float(b_h[last])
            seg_start = e
        events = events[:-1]     # the sentinel grow is not a re-split
        return a_star, b_star, events

    if cfg.kind != "band":
        raise ValueError(f"unknown federation kind {cfg.kind!r}")
    if cfg.b_up is None:
        raise ValueError("band bookkeeping requires cfg.b_up")

    # band mode — verbatim replica of run_hfed2.federation_weights with
    # MIN_GAP_DAYS and the seeds parameterized
    days = a_h.resample("1D").last().dropna().index
    last_split_day: pd.Timestamp | None = None
    d_i = 0
    while d_i < len(days):
        d = days[d_i]
        if d <= seg_start:
            d_i += 1
            continue
        a_d = ja * (float(a_h.asof(d)) / a0)
        b_d = jb * (float(b_h.asof(d)) / b0)
        share = a_d / (a_d + b_d)
        gap_ok = (last_split_day is None
                  or (d - last_split_day).days >= cfg.min_gap_days)
        if gap_ok and (share > cfg.b_up or share < 1.0 - cfg.b_up):
            act = d.normalize() + pd.Timedelta(days=1)   # next server midnight
            grow(act)
            m = (hours >= seg_start) & (hours < act)
            last = hours[m][-1]
            j = float(a_star[last] + b_star[last])
            events.append({"act": str(act), "kind": "band",
                           "decided": str(d.date()),
                           "v7_share": float(share), "joint": j})
            ja, jb = w * j, (1.0 - w) * j
            a0 = float(a_h.asof(act) if not np.isnan(a_h.asof(act))
                       else a_h[m][-1])
            b0 = float(b_h.asof(act) if not np.isnan(b_h.asof(act))
                       else b_h[m][-1])
            seg_start = act
            last_split_day = d
        d_i += 1
    grow(hours[-1] + pd.Timedelta(hours=1))
    return a_star, b_star, events


def blend_scaled(core_frac: pd.DataFrame, sat_frac: pd.DataFrame,
                 a_star: pd.Series, b_star: pd.Series,
                 scale_v7: float = 1.0, scale_v34: float = 1.0
                 ) -> pd.DataFrame:
    """Capital-weighted blend of the parents' fraction matrices.

    run_hfed2.blend arithmetic, plus optional per-book contribution scaling
    for rt_loo's half-strength probes (scaling by exactly 1.0 is an IEEE
    no-op, so default calls remain bit-identical to the runners).
    """
    j = a_star + b_star
    wa = (a_star / j) * scale_v7
    wb = (b_star / j) * scale_v34
    hours = a_star.index
    f_core = core_frac.reindex(hours).fillna(0.0)
    f_sat = sat_frac.reindex(hours).fillna(0.0)
    cols = sorted(set(f_core.columns) | set(f_sat.columns))
    return (f_core.reindex(columns=cols, fill_value=0.0).mul(wa, axis=0)
            + f_sat.reindex(columns=cols, fill_value=0.0).mul(wb, axis=0))


# ---------------------------------------------------------------------------
# engine session (HEAVY — deferred; never instantiate while a grid is running)
# ---------------------------------------------------------------------------

class EngineSession:
    """Deferred loader for the engine of record + the H-FED input artifacts.

    Instantiation is heavy (~1 min: FMA2/NSF5 sys.path bootstrap + v3.4 book
    build) and every :meth:`run` is a full record-engine pass (~5-7 min plus
    ~1 min house bootstrap).  CPU etiquette: never construct one while a
    pre-registered experiment grid is running on this machine.
    """

    def __init__(self) -> None:
        t0 = time.time()
        if str(_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS))
        # run_hfed1_lib performs the record_engine sys.path bootstrap; using
        # its load_inputs keeps red-team inputs byte-identical to the H-FED
        # runs being battered.
        import run_hfed1_lib as lib      # noqa: PLC0415 (deferred by design)
        import record_engine as RE       # noqa: PLC0415
        self.RE, self.lib = RE, lib
        log("engine", "loading H-FED inputs (frac matrices + native curves)"
            " ...")
        self.core_frac, self.sat_frac, self.a, self.b = lib.load_inputs()
        self.hours = self.core_frac.index.union(self.sat_frac.index)
        log("engine", f"inputs ready in {time.time() - t0:.0f}s")

    def run(self, cfg: FedConfig, label: str, *,
            seed_a: float | None = None, seed_b: float | None = None,
            fixed_edges: list | None = None,
            scale_v7: float = 1.0, scale_v34: float = 1.0,
            run_bootstrap: bool = True, save_curve: bool = True) -> dict:
        """One record-engine pass of a (possibly perturbed) blend config.

        Returns the standard FMA3 metric row; persists the 1m curves to
        research/outputs/redteam/<label>_curve.parquet for later autopsies.
        """
        t0 = time.time()
        eff_seed_a = cfg.core_weight if seed_a is None else float(seed_a)
        eff_seed_b = (1.0 - cfg.core_weight) if seed_b is None else float(seed_b)
        a_star, b_star, events = federation_bookkeeping(
            self.a, self.b, self.hours, cfg,
            seed_a=seed_a, seed_b=seed_b, fixed_edges=fixed_edges)
        fed = blend_scaled(self.core_frac, self.sat_frac, a_star, b_star,
                           scale_v7, scale_v34)
        res = self.RE.run_record(fed, label=label, verbose=False,
                                 run_bootstrap=run_bootstrap)
        tail = self.lib.crisis_tail(res["curves"]["equity"],
                                    res["curves"]["worst"])
        if save_curve:
            REDTEAM_DIR.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"equity": res["curves"]["equity"],
                          "worst": res["curves"]["worst"]}).to_parquet(
                REDTEAM_DIR / f"{label}_curve.parquet")
        row = {
            "label": label,
            "config": dataclasses.asdict(cfg),
            "seed_a": eff_seed_a, "seed_b": eff_seed_b,
            "scale_v7": scale_v7, "scale_v34": scale_v34,
            "fixed_edges": ([str(e) for e in fixed_edges]
                            if fixed_edges is not None else None),
            "n_events": len(events), "events": events,
            "cagr": res["cagr"], "maxdd_worst": res["maxdd_worst"],
            "maxdd_close": res["maxdd_close"], "sharpe": res["sharpe"],
            "crisis_tail": tail, "final_equity": res["final_equity"],
            "n_trades": res["n_trades"],
            "neg_years": res["neg_years"],
            "neg_quarters": res["neg_quarters"],
            "n_neg_years": res["n_neg_years"],
            "n_neg_quarters": res["n_neg_quarters"],
            "breach": res["breach"], "yearly": res["yearly"],
        }
        log(label, f"CAGR {row['cagr']:+.4f} | DDworst "
            f"{row['maxdd_worst']:.4f} | Sh {row['sharpe']:.3f} | "
            f"tail {tail:.4f} | negQ {row['n_neg_quarters']} | "
            f"events {len(events)} | {time.time() - t0:.0f}s")
        return row
