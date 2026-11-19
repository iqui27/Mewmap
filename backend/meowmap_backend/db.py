"""SQLite storage.

approval_requests cannot record a sent message or a payment. Those columns
are constrained so this process has nowhere to write either fact.
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message_role TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    topic TEXT NOT NULL,
    body_json TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (event_id, message_role, chunk_index)
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'pending_approval'),
    device_id TEXT NOT NULL,
    meow_event_id TEXT NOT NULL UNIQUE,
    model_id TEXT NOT NULL,
    hunger_confidence REAL NOT NULL,
    option_id TEXT NOT NULL,
    option_label TEXT NOT NULL,
    green_votes INTEGER NOT NULL,
    message_body TEXT NOT NULL,
    dispatched_at TEXT,
    payment_status TEXT NOT NULL CHECK (payment_status = 'not_attempted'),
    CHECK (dispatched_at IS NULL)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
