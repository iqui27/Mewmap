"""Draft a food-approval request. This module does not send or pay.

Thresholds below are named placeholders. They were not fit on any audio.
A request is inserted only when a meow header already carries a hunger
prediction and enough green votes name the same real food option.
Votes with option.source "none" do not count: the firmware sends those
until an e-ink panel exists, and they do not name a food.

SQLite refuses any row whose payment_status is not 'not_attempted' or
whose dispatched_at is set. There is no SMS client and no payment client.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from meowmap_backend.ingest import parse_time

log = logging.getLogger(__name__)

# Untuned. Not the result of an experiment.
HUNGER_CONFIDENCE_MIN = 0.85
GREEN_VOTES_MIN = 2
WINDOW = timedelta(minutes=30)


def render_message(
    *,
    device_id: str,
    meow_event_id: str,
    model_id: str,
    confidence: float,
    option_id: str,
    option_label: str,
    green_votes: int,
) -> str:
    return (
        "meowmap approval request\n"
        "status: pending_approval\n"
        "payment: not_attempted\n"
        "delivery: not sent\n"
        f"device: {device_id}\n"
        f"meow_event: {meow_event_id}\n"
        f"model_id: {model_id}\n"
        f"hunger_confidence: {confidence:.3f}\n"
        f"food_option: {option_label} ({option_id})\n"
        f"green_votes: {green_votes}\n"
        f"window_minutes: {int(WINDOW.total_seconds() // 60)}\n"
        "\n"
        "Stored locally only. This was not sent to a phone. No payment was made.\n"
    )


def _concrete_option(vote: dict) -> tuple[str, str] | None:
    option = vote["option"]
    if option["source"] not in {"eink", "manual"}:
        return None
    if option["option_id"] == "unassigned" or not option["label"]:
        return None
    return option["option_id"], option["label"]


def create_approval_requests(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Insert pending requests. Returns the new rows. Sends nothing."""
    headers = conn.execute(
        """
        SELECT body_json FROM events
        WHERE event_type = 'meow' AND message_role = 'header'
        """
    ).fetchall()
    candidates = []
    for row in headers:
        body = json.loads(row["body_json"])
        prediction = body.get("prediction")
        if not isinstance(prediction, dict):
            continue
        if prediction.get("label") != "hunger":
            continue
        confidence = prediction.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            continue
        if confidence < HUNGER_CONFIDENCE_MIN:
            continue
        candidates.append((parse_time(body["captured_at"]), body, float(confidence)))
    candidates.sort(key=lambda item: item[0])

    votes = []
    for row in conn.execute(
        "SELECT body_json FROM events WHERE event_type = 'vote'"
    ).fetchall():
        body = json.loads(row["body_json"])
        if body["choice"] != "green":
            continue
        option = _concrete_option(body)
        if option is None:
            continue
        votes.append(
            {
                "id": body["event_id"],
                "device": body["device_id"],
                "at": parse_time(body["captured_at"]),
                "option_id": option[0],
                "label": option[1],
            }
        )

    existing = {
        row["meow_event_id"]
        for row in conn.execute("SELECT meow_event_id FROM approval_requests")
    }
    used: set[str] = set()
    created_ids: list[int] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for captured_at, body, confidence in candidates:
        meow_id = body["event_id"]
        if meow_id in existing:
            continue
        device = body["device_id"]
        in_window = [
            vote
            for vote in votes
            if vote["device"] == device
            and vote["id"] not in used
            and abs(vote["at"] - captured_at) <= WINDOW
        ]
        grouped: dict[str, list[dict]] = {}
        for vote in in_window:
            grouped.setdefault(vote["option_id"], []).append(vote)
        ranked = sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)
        if not ranked or len(ranked[0][1]) < GREEN_VOTES_MIN:
            continue
        if len(ranked) > 1 and len(ranked[1][1]) == len(ranked[0][1]):
            log.info("ambiguous food votes for %s; no request", meow_id)
            continue
        option_id, group = ranked[0]
        label = group[0]["label"]
        if any(vote["label"] != label for vote in group):
            log.info("option label mismatch for %s; no request", meow_id)
            continue
        model_id = body["prediction"]["model_id"]
        message = render_message(
            device_id=device,
            meow_event_id=meow_id,
            model_id=model_id,
            confidence=confidence,
            option_id=option_id,
            option_label=label,
            green_votes=len(group),
        )
        cursor = conn.execute(
            """
            INSERT INTO approval_requests (
                created_at, status, device_id, meow_event_id, model_id,
                hunger_confidence, option_id, option_label, green_votes,
                message_body, payment_status
            ) VALUES (?, 'pending_approval', ?, ?, ?, ?, ?, ?, ?, ?, 'not_attempted')
            """,
            (
                now,
                device,
                meow_id,
                model_id,
                confidence,
                option_id,
                label,
                len(group),
                message,
            ),
        )
        for vote in group:
            used.add(vote["id"])
        created_ids.append(int(cursor.lastrowid))

    conn.commit()
    if not created_ids:
        return []
    placeholders = ",".join("?" for _ in created_ids)
    return list(
        conn.execute(
            f"SELECT * FROM approval_requests WHERE id IN ({placeholders}) ORDER BY id",
            created_ids,
        )
    )
