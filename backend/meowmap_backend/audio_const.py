"""Audio sizes from schema.json. Kept here so ingest does not import the ML package."""

CLIP_BYTES = 64000
CHUNK_RAW_BYTES = 480
CHUNK_COUNT = (CLIP_BYTES + CHUNK_RAW_BYTES - 1) // CHUNK_RAW_BYTES
