import base64
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from meowmap_backend.clips import ClipError, reassemble_pcm
from meowmap_backend.db import connect
from meowmap_backend.ingest import ingest
from meowmap_backend.ordering import create_approval_requests
from tests.support import config_for, meow_header, prediction, store, vote


class OrderingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "meowmap.db"
        self.cfg = config_for(self.path)
        self.conn = connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _hunger(self, event_id="meow-hunger-0001", when="2026-01-01T00:00:00Z", confidence=0.91, **kwargs):
        body = meow_header(
            event_id,
            when,
            prediction_body=prediction("hunger", confidence),
            **kwargs,
        )
        self.assertEqual(store(self.conn, self.cfg, body), "stored")

    def _food_vote(self, event_id, when, **kwargs):
        body = vote(event_id, when, **kwargs)
        self.assertEqual(store(self.conn, self.cfg, body), "stored")

    def test_no_events_creates_nothing(self):
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_low_confidence_does_not_order(self):
        self._hunger(confidence=0.5)
        self._food_vote("vote-green-0001", "2026-01-01T00:01:00Z")
        self._food_vote("vote-green-0002", "2026-01-01T00:02:00Z")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_one_green_vote_does_not_order(self):
        self._hunger()
        self._food_vote("vote-green-0001", "2026-01-01T00:01:00Z")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_unassigned_presses_are_not_a_food_order(self):
        self._hunger()
        for index, when in enumerate(("2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z"), start=1):
            self._food_vote(
                f"vote-none-000{index}",
                when,
                option_id="unassigned",
                label="",
                source="none",
            )
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_red_votes_do_not_count(self):
        self._hunger()
        self._food_vote("vote-red-0001", "2026-01-01T00:01:00Z", choice="red")
        self._food_vote("vote-red-0002", "2026-01-01T00:02:00Z", choice="red")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_split_vote_does_not_pick_a_food(self):
        self._hunger()
        self._food_vote("vote-chicken-0001", "2026-01-01T00:01:00Z", option_id="chicken-pate", label="chicken pate")
        self._food_vote("vote-chicken-0002", "2026-01-01T00:02:00Z", option_id="chicken-pate", label="chicken pate")
        self._food_vote("vote-fish-0001", "2026-01-01T00:03:00Z", option_id="fish-stew", label="fish stew")
        self._food_vote("vote-fish-0002", "2026-01-01T00:04:00Z", option_id="fish-stew", label="fish stew")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_matching_greens_create_one_unsent_request(self):
        self._hunger()
        self._food_vote("vote-green-0001", "2026-01-01T00:01:00Z")
        self._food_vote("vote-green-0002", "2026-01-01T00:02:00Z")
        rows = create_approval_requests(self.conn)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "pending_approval")
        self.assertEqual(row["payment_status"], "not_attempted")
        self.assertIsNone(row["dispatched_at"])
        self.assertEqual(row["option_id"], "chicken-pate")
        self.assertEqual(row["green_votes"], 2)
        self.assertIn("No payment was made.", row["message_body"])
        self.assertIn("not sent", row["message_body"])
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_votes_outside_the_window_do_not_count(self):
        self._hunger(when="2026-01-01T00:00:00Z")
        self._food_vote("vote-late-0001", "2026-01-01T00:30:01Z")
        self._food_vote("vote-late-0002", "2026-01-01T00:31:00Z")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_votes_on_the_window_edge_count(self):
        self._hunger(when="2026-01-01T00:00:00Z")
        self._food_vote("vote-edge-0001", "2026-01-01T00:30:00Z")
        self._food_vote("vote-edge-0002", "2026-01-01T00:10:00Z")
        rows = create_approval_requests(self.conn)
        self.assertEqual(len(rows), 1)

    def test_other_device_votes_do_not_count(self):
        self._hunger()
        self._food_vote("vote-other-0001", "2026-01-01T00:01:00Z", device="other-bowl")
        self._food_vote("vote-other-0002", "2026-01-01T00:02:00Z", device="other-bowl")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_drama_prediction_does_not_order(self):
        body = meow_header(
            "meow-drama-0001",
            "2026-01-01T00:00:00Z",
            prediction_body=prediction("drama", 0.99),
        )
        self.assertEqual(store(self.conn, self.cfg, body), "stored")
        self._food_vote("vote-green-0001", "2026-01-01T00:01:00Z")
        self._food_vote("vote-green-0002", "2026-01-01T00:02:00Z")
        self.assertEqual(create_approval_requests(self.conn), [])

    def test_same_votes_support_only_the_earlier_meow(self):
        self._hunger("meow-early-0001", "2026-01-01T00:00:00Z")
        self._hunger("meow-late-0002", "2026-01-01T00:10:00Z")
        self._food_vote("vote-green-0001", "2026-01-01T00:05:00Z")
        self._food_vote("vote-green-0002", "2026-01-01T00:06:00Z")
        rows = create_approval_requests(self.conn)
        self.assertEqual([row["meow_event_id"] for row in rows], ["meow-early-0001"])


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "meowmap.db"
        self.cfg = config_for(self.path)
        self.conn = connect(self.path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_topic_must_match_event_type(self):
        body = meow_header("meow-topic-0001", "2026-01-01T00:00:00Z")
        status = ingest(
            self.conn,
            self.cfg.topic_vote,
            json.dumps(body).encode("utf-8"),
            self.cfg,
        )
        self.assertEqual(status, "rejected")

    def test_reassembly_checks_sha256(self):
        pcm = bytes(index % 251 for index in range(64000))
        digest = hashlib.sha256(pcm).hexdigest()
        header = meow_header("meow-clip-0001", "2026-01-01T00:00:00Z", sha256=digest)
        self.assertEqual(store(self.conn, self.cfg, header), "stored")
        count = (64000 + 479) // 480
        for index in range(count):
            piece = pcm[index * 480 : (index + 1) * 480]
            chunk = {
                "schema_version": "0.1.0",
                "event_type": "meow",
                "event_id": "meow-clip-0001",
                "device_id": "bowl-01",
                "captured_at": "2026-01-01T00:00:00Z",
                "message_role": "audio_chunk",
                "audio": dict(header["audio"]),
                "chunk": {
                    "index": index,
                    "count": count,
                    "byte_offset": index * 480,
                    "byte_length": len(piece),
                    "pcm_base64": base64.b64encode(piece).decode("ascii"),
                },
            }
            # Firmware puts the digest on the header only.
            chunk["audio"].pop("sha256", None)
            self.assertEqual(store(self.conn, self.cfg, chunk), "stored")
        self.assertEqual(reassemble_pcm(self.conn, "meow-clip-0001"), pcm)

        self.conn.execute("DELETE FROM events WHERE message_role = 'audio_chunk' AND chunk_index = 133")
        self.conn.commit()
        with self.assertRaises(ClipError):
            reassemble_pcm(self.conn, "meow-clip-0001")


if __name__ == "__main__":
    unittest.main()
