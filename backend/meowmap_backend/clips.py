"""Reassemble chunked PCM and check it against the header."""

import base64
import hashlib
import json
import sqlite3

from meowmap_backend.audio_const import CLIP_BYTES


class ClipError(Exception):
    pass


def reassemble_pcm(conn: sqlite3.Connection, event_id: str) -> bytes:
    header = conn.execute(
        """
        SELECT body_json FROM events
        WHERE event_id = ? AND message_role = 'header' AND chunk_index = -1
        """,
        (event_id,),
    ).fetchone()
    if header is None:
        raise ClipError("missing header")
    header_body = json.loads(header["body_json"])
    rows = conn.execute(
        """
        SELECT chunk_index, body_json FROM events
        WHERE event_id = ? AND message_role = 'audio_chunk'
        ORDER BY chunk_index
        """,
        (event_id,),
    ).fetchall()
    if not rows:
        raise ClipError("no chunks")

    parts: list[bytes] = []
    expected_count: int | None = None
    offset = 0
    for position, row in enumerate(rows):
        body = json.loads(row["body_json"])
        chunk = body["chunk"]
        if chunk["index"] != position or row["chunk_index"] != position:
            raise ClipError("gap or duplicate chunk index")
        if expected_count is None:
            expected_count = chunk["count"]
        elif chunk["count"] != expected_count:
            raise ClipError("chunks disagree on count")
        if chunk["index"] >= chunk["count"]:
            raise ClipError("chunk index out of range")
        raw = base64.b64decode(chunk["pcm_base64"], validate=True)
        if len(raw) != chunk["byte_length"]:
            raise ClipError("decoded length does not match byte_length")
        if chunk["byte_offset"] != offset:
            raise ClipError("chunk byte_offset is not contiguous")
        parts.append(raw)
        offset += len(raw)

    if expected_count is None or len(parts) != expected_count:
        raise ClipError("incomplete clip")
    pcm = b"".join(parts)
    if len(pcm) != CLIP_BYTES or len(pcm) != header_body["audio"]["byte_length"]:
        raise ClipError("reassembled clip is not 64000 bytes")
    digest = header_body["audio"].get("sha256")
    if digest is not None and digest != hashlib.sha256(pcm).hexdigest():
        raise ClipError("sha256 does not match the header")
    return pcm
