"""Process configuration. Passwords come from the environment, never from argv."""

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

DEFAULT_TOPIC_MEOW = "meowmap/events/meow"
DEFAULT_TOPIC_VOTE = "meowmap/events/vote"


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str
    mqtt_password: str
    topic_meow: str
    topic_vote: str
    sqlite_path: Path


def load_dotenv(path: Path) -> None:
    """Fill unset environment keys from a local .env file. Missing file is fine."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def from_env(environ: dict[str, str] | None = None) -> Config:
    if environ is None:
        load_dotenv(BACKEND_ROOT / ".env")
        environ = dict(os.environ)
    data = environ
    return Config(
        mqtt_host=data.get("MEOWMAP_MQTT_HOST", "127.0.0.1"),
        mqtt_port=int(data.get("MEOWMAP_MQTT_PORT", "1883")),
        mqtt_user=data.get("MEOWMAP_MQTT_USER", ""),
        mqtt_password=data.get("MEOWMAP_MQTT_PASSWORD", ""),
        topic_meow=data.get("MEOWMAP_MQTT_TOPIC_MEOW", DEFAULT_TOPIC_MEOW),
        topic_vote=data.get("MEOWMAP_MQTT_TOPIC_VOTE", DEFAULT_TOPIC_VOTE),
        sqlite_path=Path(data.get("MEOWMAP_SQLITE_PATH", "meowmap.db")),
    )
