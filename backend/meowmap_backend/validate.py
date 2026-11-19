"""Validate event payloads against the repository schema.json."""

import json
from functools import lru_cache

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from meowmap_backend.config import REPO_ROOT

SCHEMA_PATH = REPO_ROOT / "schema.json"


@lru_cache(maxsize=1)
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_event(body: object) -> str | None:
    """Return an error string, or None when the document matches the schema."""
    errors = sorted(validator().iter_errors(body), key=lambda err: list(err.path))
    if not errors:
        return None
    first: ValidationError = errors[0]
    location = "/".join(str(part) for part in first.path) or "(root)"
    return f"{location}: {first.message}"
