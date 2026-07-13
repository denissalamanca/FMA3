"""target_engine — the Python brain's hourly target-position producer.

Computes the shipped v3 book (v2 F3-capped weights + mag_xau@0.05 overlay @
scale 10 + hard limits, freed weight cash-parked) at the position level and
writes ONE atomic ``ea/bridge/targets.json`` per hour for the MQL5 executor to
diff-and-fill.

The pipeline is IDENTICAL to the official 1m pin (``research/eval_c2_pin_s11.py``)
except it stops at the hourly position matrix (the executor owns lot sizing /
execution):

    per_sleeve = sleeve_pos * weight * GLOBAL_SCALE           # NO renormalize
    net        = sum(per_sleeve)                              # cash-park kept
    net_capped = apply_hard_limits(net, gold_cap=structural_gold_cap(), 0.5)

The alpha is never re-derived here: sleeve matrices come from the audited
``research/outputs/*_pos.parquet`` (rebuild=False, bit-identical to module
output) or, with rebuild=True, straight from ``research/sleeves/*.make_positions``.

MAGIC ATTRIBUTION.  MT5 nets positions per symbol, but XAUUSD is traded by four
sleeves (seasonal, crisis, trend_v2, mag_xau). The executor reattributes by magic,
so the target file carries a per-sleeve breakdown. The book-level hard-limit clip
is distributed back to the contributing sleeves *pro-rata* so the per-magic
targets always sum to the validated net exposure (research parity preserved).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import brain_config as C                                 # noqa: E402

# ensemble carries the load-bearing research logic we MUST reuse verbatim.
import ensemble as E                                     # noqa: E402

_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Sleeve loading
# --------------------------------------------------------------------------- #
# Overlay sleeves that are NOT audited-parquet sleeves under research/sleeves:
# they are imported modules with their own make_positions(). v3 adds mag_xau
# (research/ext_import/mag_xau.py) — the gold round-number magnet. It has no
# frozen ``*_pos.parquet``, so it is always built from its module (exactly as
# research/eval_c2_pin_s11.build_c2 does) and reindexed to the core grid.
_EXT_IMPORT_SLEEVES = {"mag_xau": "ext_import.mag_xau"}


def _load_ext_import(name: str, grid) -> pd.DataFrame:
    import importlib
    mod = importlib.import_module(_EXT_IMPORT_SLEEVES[name])
    return mod.make_positions().reindex(grid).fillna(0.0)


def load_sleeve_positions(rebuild: bool = False) -> dict[str, pd.DataFrame]:
    """Return {sleeve -> hourly position matrix} on the union grid.

    rebuild=False : audited frozen parquets (production default). Overlay sleeves
                    with no frozen parquet (mag_xau) are built from their module.
    rebuild=True  : recompute every sleeve from *.make_positions() against
                    whatever hourly cache research.core is pointed at (extend it
                    via data_feed before a live rebuild).
    """
    if rebuild:
        import research.core as _core
        grid = _core.universe_frames(tuple(_core.ALL))["ret"].index
        out: dict[str, pd.DataFrame] = {}
        for name in C.SLEEVES:
            if name in _EXT_IMPORT_SLEEVES:
                out[name] = _load_ext_import(name, grid)
                continue
            mod = __import__(name)                        # research/sleeves on path
            out[name] = mod.make_positions()
        # align to a common index (union of all sleeve indices)
        idx = None
        for df in out.values():
            idx = df.index if idx is None else idx.union(df.index)
        return {n: df.reindex(idx).fillna(0.0) for n, df in out.items()}

    # production default: frozen parquets for the audited sleeves + module-built
    # overlays (mag_xau). E.load_sleeves reindexes the parquet sleeves to the
    # core return grid; reuse that same grid for the overlays so they align.
    parquet_sleeves = [n for n in C.SLEEVES if n not in _EXT_IMPORT_SLEEVES]
    sleeves = E.load_sleeves(parquet_sleeves)             # reindexed to core grid
    if sleeves:
        grid = next(iter(sleeves.values())).index
    else:
        import research.core as _core
        grid = _core.universe_frames(tuple(_core.ALL))["ret"].index
    for name in C.SLEEVES:
        if name in _EXT_IMPORT_SLEEVES:
            sleeves[name] = _load_ext_import(name, grid)
    return sleeves


# --------------------------------------------------------------------------- #
# Book construction (research-parity) with per-sleeve attribution
# --------------------------------------------------------------------------- #
def build_book(rebuild: bool = False):
    """Build the full hourly book. Returns (net_capped, per_sleeve_capped).

    net_capped         : DataFrame, final fraction-of-equity exposure per symbol.
    per_sleeve_capped  : {sleeve -> DataFrame}, contributions that SUM to
                         net_capped (pro-rata distribution of the hard-limit clip).
    """
    sleeves = load_sleeve_positions(rebuild=rebuild)

    # 1) scaled per-sleeve contributions — combine(...) * SCALE, NO renormalize.
    per_sleeve = {n: sleeves[n] * (C.SLEEVE_WEIGHTS[n] * C.GLOBAL_SCALE)
                  for n in C.SLEEVES}

    # 2) net = sum over sleeves on the union column/index grid.
    net = None
    for df in per_sleeve.values():
        net = df if net is None else net.add(df, fill_value=0.0)
    net = net.fillna(0.0)

    # align every sleeve to the net grid so distribution is elementwise-safe.
    per_sleeve = {n: df.reindex(index=net.index, columns=net.columns).fillna(0.0)
                  for n, df in per_sleeve.items()}

    # 3) hard limits on the NET book (exactly ensemble.apply_hard_limits).
    #    gold_cap = the SHIPPED effective overnight cap = the structural rule
    #    seasonal_w x scale = 0.18*10 = 1.80xE at v3.4 scale 10 (no tighter
    #    override; MKT-4a; SPEC §9 / PROTOCOL §1). See brain_config.
    gold_cap = C.effective_gold_cap()
    net_capped = E.apply_hard_limits(net, gold_cap=gold_cap,
                                     cross_cap=C.CROSS_CAP_X_EQUITY)

    # 4) distribute the clip back to sleeves pro-rata (factor = capped/net).
    #    where net==0 the factor is 1 (no clip possible), preserving offsets.
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = net_capped.to_numpy() / np.where(np.abs(net.to_numpy()) < _EPS,
                                                   np.nan, net.to_numpy())
    factor = np.where(np.isfinite(factor), factor, 1.0)
    factor = pd.DataFrame(factor, index=net.index, columns=net.columns)

    per_sleeve_capped = {n: (df * factor).fillna(0.0)
                         for n, df in per_sleeve.items()}
    return net_capped, per_sleeve_capped


# --------------------------------------------------------------------------- #
# Target-row selection + serialization
# --------------------------------------------------------------------------- #
def _tradable_symbols(per_sleeve_capped: dict[str, pd.DataFrame]) -> list[str]:
    """Symbols any sleeve ever trades — emitted with explicit 0.0 so the
    executor flattens on a target that dropped to zero."""
    syms: set[str] = set()
    for df in per_sleeve_capped.values():
        syms |= {c for c in df.columns if df[c].abs().sum() > _EPS}
    return sorted(syms)


def _select_row(net_capped: pd.DataFrame, as_of: str | pd.Timestamp | None):
    """Pick the bar to target. as_of=None => last available bar. Otherwise the
    last bar at/BEFORE as_of (never look ahead)."""
    if as_of is None:
        ts = net_capped.index[-1]
    else:
        ts = pd.Timestamp(as_of)
        sub = net_capped.index[net_capped.index <= ts]
        if len(sub) == 0:
            raise ValueError(f"as_of {ts} precedes all available bars")
        ts = sub[-1]
    return ts


def median_gross_xE(net_capped: pd.DataFrame | None = None) -> float:
    """Trailing backtest median book gross (sum|exposure| per bar / equity).
    Feeds the MKT-7 notional-ratchet echo (cap = 1.4x this). Batch-Python later
    maintains the live trailing-252d version."""
    if net_capped is None:
        net_capped, _ = build_book()
    gross = net_capped.abs().sum(axis=1)
    return round(float(gross.median()), 4)


def build_targets(as_of: str | pd.Timestamp | None = None,
                  rebuild: bool = False, seq: int | None = None) -> dict:
    """Assemble the targets.json payload for one bar (no I/O).

    Emits the PROTOCOL.md fable.targets.v1 schema: a FLAT LIST of per-
    (sleeve, symbol) records (exposure = signed fraction of live equity), with
    the hard-limit echo and per-sleeve exit schedule the EA needs.
    """
    net_capped, per_sleeve_capped = build_book(rebuild=rebuild)
    ts = pd.Timestamp(_select_row(net_capped, as_of))
    syms = _tradable_symbols(per_sleeve_capped)

    records: list[dict] = []
    for n in C.SLEEVES:
        df = per_sleeve_capped[n]
        sched = C.SLEEVE_SCHEDULE.get(n, {})
        for sym in syms:
            if sym not in df.columns:
                continue
            v = float(df.at[ts, sym])
            if abs(v) <= _EPS:                            # absence => target 0 (flatten)
                continue
            rec = {"sleeve": n, "magic": C.MAGIC_OF[n], "symbol": sym,
                   "exposure": round(v, 6)}
            rec.update(sched)                             # flat_at/no_entry_after
            records.append(rec)

    now = pd.Timestamp.utcnow().tz_localize(None)
    # bar_time / generated stamps are BROKER SERVER time (the bar index already is)
    payload = {
        "schema": "fable.targets.v1",
        "seq": int(seq) if seq is not None else _next_seq(),
        "generated_utc": now.isoformat(timespec="seconds") + "Z",
        "generated_server": now.strftime("%Y-%m-%d %H:%M:%S"),
        "bar_time_server": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "global_scale": C.GLOBAL_SCALE,
        "equity_ref": C.EQUITY_REF_EUR,
        "config_hash": C.config_hash(),
        "hard_limits": {
            "overnight_gold_cap_xE": C.effective_gold_cap(),
            "overnight_gold_symbol": C.GOLD_SYMBOL,
            "overnight_gold_sleeves": C.GOLD_OVERNIGHT_SLEEVES,
            "overnight_hours_server": C.GOLD_OVERNIGHT_HOURS,
            "managed_cross_cap_xE": C.CROSS_CAP_X_EQUITY,
            "managed_crosses": C.MANAGED_CROSSES,
            "gross_notional_median_xE": median_gross_xE(net_capped),
            "structural_gold_cap_xE": round(C.structural_gold_cap(), 4),
        },
        # brain-side provenance (EA ignores unknown keys)
        "engine_model": C.ENGINE_MODEL,
        "weights": {k: round(v, 8) for k, v in C.SLEEVE_WEIGHTS.items()},
        "weight_sum": round(C.WEIGHT_SUM, 8),
        "cash_park": round(C.CASH_PARK, 8),
        "n_records": len(records),
        "targets": records,
    }
    return payload


# --------------------------------------------------------------------------- #
# Sequence + atomic write
# --------------------------------------------------------------------------- #
def _next_seq() -> int:
    try:
        return int(C.SEQ_PATH.read_text().strip()) + 1
    except (FileNotFoundError, ValueError):
        # resume from an existing targets.json if the seq store was lost
        try:
            return int(json.loads(C.TARGETS_PATH.read_text())["seq"]) + 1
        except Exception:
            return 1


def _atomic_write_json(path: Path, obj: dict) -> None:
    """tmp + fsync + atomic rename (production-quality-bar item 6)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)                                 # atomic on POSIX


def write_targets(payload: dict) -> Path:
    _atomic_write_json(C.TARGETS_PATH, payload)
    # persist the sequence AFTER the targets commit
    tmp = C.SEQ_PATH.with_suffix(".tmp")
    tmp.write_text(str(payload["seq"]))
    os.replace(tmp, C.SEQ_PATH)
    return C.TARGETS_PATH


def compute_and_write(as_of: str | pd.Timestamp | None = None,
                      rebuild: bool = False) -> dict:
    """One hourly cycle: build the payload and atomically publish it."""
    payload = build_targets(as_of=as_of, rebuild=rebuild)
    write_targets(payload)
    return payload


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Fable v2 brain — target engine")
    ap.add_argument("--as-of", default=None,
                    help="server timestamp of the bar to target (default: latest)")
    ap.add_argument("--rebuild", action="store_true",
                    help="recompute sleeves from source instead of frozen parquets")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payload, do not write the bridge file")
    args = ap.parse_args()

    payload = build_targets(as_of=args.as_of, rebuild=args.rebuild)
    print(f"seq={payload['seq']} bar={payload['bar_time_server']} "
          f"hash={payload['config_hash']} records={payload['n_records']} "
          f"gold_cap={payload['hard_limits']['overnight_gold_cap_xE']}xE")
    # aggregate to net per symbol for a readable summary
    net: dict[str, float] = {}
    detail: dict[str, list] = {}
    for r in payload["targets"]:
        net[r["symbol"]] = net.get(r["symbol"], 0.0) + r["exposure"]
        detail.setdefault(r["symbol"], []).append(f"{r['sleeve']}:{r['exposure']:+.3f}")
    print("net exposure per symbol (sum of sleeve records):")
    for s, v in sorted(net.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {s:8s} {v:+.4f}  " + ", ".join(detail[s]))
    gross = sum(abs(v) for v in net.values())
    print(f"gross = {gross:.3f} xE | median_gross = "
          f"{payload['hard_limits']['gross_notional_median_xE']} xE")
    if not args.dry_run:
        write_targets(payload)
        print(f"written -> {C.TARGETS_PATH}")


if __name__ == "__main__":
    main()
