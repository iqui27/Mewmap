"""Event builders that follow schema.json."""

import json
from pathlib import Path

from meowmap_backend.config import DEFAULT_TOPIC_MEOW, DEFAULT_TOPIC_VOTE, Config
from meowmap_backend.ingest import ingest

AUDIO = {
    "sample_rate_hz": 16000,
    "channels": 1,
    "bit_depth": 16,
    "encoding": "pcm_s16le",
    "duration_ms": 2000,
    "byte_length": 64000,
}

DETECTOR = {
    "method": "energy_rms",
    "frame_ms": 20,
    "trigger_rms": 1200.0,
    "threshold": 800.0,
    "consecutive_frames": 3,
    "calibrated": False,
}


def config_for(path: Path) -> Config:
    return Config(
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_user="",
        mqtt_password="",
        topic_meow=DEFAULT_TOPIC_MEOW,
        topic_vote=DEFAULT_TOPIC_VOTE,
        sqlite_path=path,
    )


def prediction(label: str, confidence: float, model_id: str = "not-a-model") -> dict:
    return {
        "model_id": model_id,
        "label": label,
        "confidence": confidence,
        "produced_at": "2026-01-01T00:00:00Z",
    }


def meow_header(
    event_id: str,
    captured_at: str,
    *,
    device: str = "bowl-01",
    prediction_body: dict | None = None,
    sha256: str | None = None,
) -> dict:
    audio = dict(AUDIO)
    if sha256 is not None:
        audio["sha256"] = sha256
    body = {
        "schema_version": "0.1.0",
        "event_type": "meow",
        "event_id": event_id,
        "device_id": device,
        "captured_at": captured_at,
        "message_role": "header",
        "audio": audio,
        "detector": dict(DETECTOR),
    }
    if prediction_body is not None:
        body["prediction"] = prediction_body
    return body


def vote(
    event_id: str,
    captured_at: str,
    *,
    choice: str = "green",
    device: str = "bowl-01",
    option_id: str = "chicken-pate",
    label: str = "chicken pate",
    source: str = "manual",
    related: str | None = None,
) -> dict:
    return {
        "schema_version": "0.1.0",
        "event_type": "vote",
        "event_id": event_id,
        "device_id": device,
        "captured_at": captured_at,
        "choice": choice,
        "option": {"option_id": option_id, "label": label, "source": source},
        "related_meow_event_id": related,
    }


def store(conn, cfg: Config, body: dict) -> str:
    topic = cfg.topic_meow if body["event_type"] == "meow" else cfg.topic_vote
    return ingest(conn, topic, json.dumps(body).encode("utf-8"), cfg)
