"""Store one MQTT payload after it matches schema.json."""

import base64
import json
import logging
import sqlite3
from datetime import datetime, timezone

from meowmap_backend.audio_const import CLIP_BYTES
from meowmap_backend.config import Config
from meowmap_backend.validate import validate_event

log = logging.getLogger(__name__)


def parse_time(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return parsed.astimezone(timezone.utc)


def ingest(conn: sqlite3.Connection, topic: str, payload: bytes, cfg: Config) -> str:
    """Return 'stored' or 'rejected'. Invalid payloads are not written."""
    try:
        text = payload.decode("utf-8")
        body = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("rejected payload: %s", exc)
        return "rejected"

    error = validate_event(body)
    if error is not None:
        log.warning("rejected event: %s", error[:300])
        return "rejected"

    event_type = body["event_type"]
    expected = None
    if topic == cfg.topic_meow:
        expected = "meow"
    elif topic == cfg.topic_vote:
        expected = "vote"
    if expected is None or event_type != expected:
        log.warning("rejected event: topic %s does not match event_type %s", topic, event_type)
        return "rejected"

    try:
        parse_time(body["captured_at"])
        prediction = body.get("prediction")
        if isinstance(prediction, dict) and "produced_at" in prediction:
            parse_time(prediction["produced_at"])
    except ValueError as exc:
        log.warning("rejected event: %s", exc)
        return "rejected"

    if event_type == "meow" and body["message_role"] == "audio_chunk":
        chunk = body["chunk"]
        try:
            raw = base64.b64decode(chunk["pcm_base64"], validate=True)
        except ValueError as exc:
            log.warning("rejected chunk: %s", exc)
            return "rejected"
        if len(raw) != chunk["byte_length"]:
            log.warning("rejected chunk: decoded length != byte_length")
            return "rejected"
        if chunk["index"] >= chunk["count"]:
            log.warning("rejected chunk: index >= count")
            return "rejected"
        if chunk["byte_offset"] + chunk["byte_length"] > CLIP_BYTES:
            log.warning("rejected chunk: extends past the clip")
            return "rejected"
        message_role = "audio_chunk"
        chunk_index = chunk["index"]
    elif event_type == "meow":
        message_role = "header"
        chunk_index = -1
    else:
        message_role = "vote"
        chunk_index = -1

    received = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT OR REPLACE INTO events (
            event_id, event_type, message_role, chunk_index, device_id,
            captured_at, topic, body_json, received_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            body["event_id"],
            event_type,
            message_role,
            chunk_index,
            body["device_id"],
            body["captured_at"],
            topic,
            text,
            received,
        ),
    )
    conn.commit()
    return "stored"
