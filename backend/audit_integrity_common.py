"""Common canonical hashing helpers for ValidaOT audit integrity v0.6."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

EVENT_FIELDS = (
    "id",
    "actor_user_id",
    "event_type",
    "entity_type",
    "entity_id",
    "occurred_at",
    "correlation_id",
    "outcome",
    "details",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_event_details(raw_details: Any) -> Any:
    if raw_details is None or raw_details == "":
        return {}
    if isinstance(raw_details, (dict, list, int, float, bool)):
        return raw_details
    return json.loads(str(raw_details))


def compute_event_hash(sequence: int, previous_hash: str, record: Mapping[str, Any]) -> str:
    """Hash a chain entry using the exact timestamp text stored by SQLite."""
    event = {
        "id": record["id"],
        "actor_user_id": record["actor_user_id"],
        "event_type": record["event_type"],
        "entity_type": record["entity_type"],
        "entity_id": record["entity_id"],
        "occurred_at": str(record["occurred_at"]),
        "correlation_id": record["correlation_id"],
        "outcome": record["outcome"],
        "details": normalize_event_details(record["details"]),
    }
    envelope = {
        "chain_sequence": int(sequence),
        "previous_hash": previous_hash,
        "event": event,
    }
    return payload_sha256(envelope)
