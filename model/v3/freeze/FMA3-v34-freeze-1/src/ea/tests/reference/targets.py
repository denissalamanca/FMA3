"""Reference implementation of the targets.json protocol.

The Python brain writes an hourly target file; the MQL5 executor reads it. This
module is the shared contract: schema, atomic write (tmp+fsync+rename), sequence
monotonicity, staleness, and config-hash gating. The EA re-implements the READ
side in MQL5; this reference lets us test the contract off-MT5.

Acceptance rule (EA side): a freshly written target set is ACCEPTED only if
  - it is schema-valid, AND
  - its config_hash matches the EA's compiled config (else the brain and the
    executor disagree about weights/scale -> reject, keep last good), AND
  - its seq is strictly greater than the last accepted seq (monotonic; rejects
    replays / out-of-order NFS writes), AND
  - it is not stale (written_at within max_age of now; a frozen brain must not
    keep the EA trading an hour-old target).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

SCHEMA_VERSION = "2.0"

# required top-level keys and their python types
_REQUIRED = {
    "schema_version": str,
    "seq": int,
    "written_at": str,      # ISO-8601 server time
    "bar_time": str,        # ISO-8601 hourly bar this target set is decided on
    "config_hash": str,
    "global_scale": (int, float),
    "targets": dict,        # {symbol: signed fraction of equity}
}


def config_hash(weights: dict[str, float], scale: float,
                schema_version: str = SCHEMA_VERSION) -> str:
    """Stable hash over the shipped config. Order-independent; rounded so
    float-repr noise does not change the hash across hosts."""
    items = sorted((k, round(float(v), 10)) for k, v in weights.items())
    blob = json.dumps({"schema": schema_version, "scale": round(float(scale), 10),
                       "weights": items}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_payload(seq: int, targets: dict[str, float], *,
                  weights: dict[str, float], scale: float,
                  bar_time: datetime, written_at: datetime | None = None) -> dict:
    written = written_at or datetime.now(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "seq": int(seq),
        "written_at": written.isoformat(),
        "bar_time": bar_time.isoformat(),
        "config_hash": config_hash(weights, scale),
        "global_scale": float(scale),
        "targets": {k: float(v) for k, v in targets.items()},
    }


class SchemaError(ValueError):
    pass


def validate_schema(payload: dict) -> None:
    """Raise SchemaError on any structural problem."""
    if not isinstance(payload, dict):
        raise SchemaError("payload is not an object")
    for key, typ in _REQUIRED.items():
        if key not in payload:
            raise SchemaError(f"missing key: {key}")
        if not isinstance(payload[key], typ):
            raise SchemaError(f"key {key} has wrong type: {type(payload[key])}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(f"schema_version {payload['schema_version']} "
                          f"!= {SCHEMA_VERSION}")
    if payload["seq"] < 0:
        raise SchemaError("seq must be >= 0")
    for sym, val in payload["targets"].items():
        if not isinstance(sym, str):
            raise SchemaError(f"target key not a string: {sym!r}")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise SchemaError(f"target {sym} not numeric: {val!r}")
        # NaN/inf would corrupt sizing downstream
        if val != val or val in (float("inf"), float("-inf")):
            raise SchemaError(f"target {sym} not finite: {val!r}")


def write_targets(path: str, payload: dict) -> None:
    """Atomic write: validate -> tmp -> fsync -> rename. The rename is the
    commit point; a crash mid-write leaves the previous file intact."""
    validate_schema(payload)
    tmp = f"{path}.tmp"
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)  # atomic on POSIX


def read_targets(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    validate_schema(payload)
    return payload


@dataclass
class AcceptResult:
    accepted: bool
    reason: str
    seq: int | None = None


def accept_targets(payload: dict, *, last_seq: int, expected_hash: str,
                   now: datetime, max_age_sec: float = 300.0) -> AcceptResult:
    """EA-side acceptance gate. `last_seq` is the last accepted seq (-1 if
    none). Returns AcceptResult; on reject the EA keeps its last good target."""
    try:
        validate_schema(payload)
    except SchemaError as exc:
        return AcceptResult(False, f"schema:{exc}")

    if payload["config_hash"] != expected_hash:
        return AcceptResult(False, "config_hash_mismatch", payload["seq"])

    if payload["seq"] <= last_seq:
        return AcceptResult(False, "seq_not_monotonic", payload["seq"])

    written = datetime.fromisoformat(payload["written_at"])
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    age = (now - written).total_seconds()
    if age > max_age_sec:
        return AcceptResult(False, f"stale:{age:.0f}s", payload["seq"])
    if age < -max_age_sec:
        # clock skew / future-dated file -> also refuse
        return AcceptResult(False, f"future:{age:.0f}s", payload["seq"])

    return AcceptResult(True, "ok", payload["seq"])
