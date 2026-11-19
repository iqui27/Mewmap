import json
import unittest
from pathlib import Path

from meowmap_backend.validate import validate_event

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


class SchemaTest(unittest.TestCase):
    def test_examples_match_the_schema(self):
        for path in sorted(EXAMPLES.glob("*.json")):
            body = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsNone(validate_event(body), path.name)

    def test_header_cannot_claim_calibration(self):
        body = json.loads((EXAMPLES / "meow_header.json").read_text(encoding="utf-8"))
        body["detector"]["calibrated"] = True
        self.assertIsNotNone(validate_event(body))

    def test_header_rejects_a_chunk(self):
        body = json.loads((EXAMPLES / "meow_header.json").read_text(encoding="utf-8"))
        body["chunk"] = {
            "index": 0,
            "count": 1,
            "byte_offset": 0,
            "byte_length": 4,
            "pcm_base64": "AAAA",
        }
        self.assertIsNotNone(validate_event(body))

    def test_confidence_above_one_is_rejected(self):
        body = json.loads((EXAMPLES / "meow_header.json").read_text(encoding="utf-8"))
        body["prediction"] = {
            "model_id": "not-a-model",
            "label": "hunger",
            "confidence": 1.5,
        }
        self.assertIsNotNone(validate_event(body))

    def test_vote_needs_a_label_when_a_panel_is_the_source(self):
        body = json.loads((EXAMPLES / "vote.json").read_text(encoding="utf-8"))
        body["option"] = {"option_id": "chicken-pate", "label": "", "source": "eink"}
        self.assertIsNotNone(validate_event(body))

    def test_chunk_example_is_silence_slice(self):
        import base64

        body = json.loads((EXAMPLES / "meow_chunk.json").read_text(encoding="utf-8"))
        raw = base64.b64decode(body["chunk"]["pcm_base64"], validate=True)
        self.assertEqual(len(raw), 480)
        self.assertEqual(raw, b"\x00" * 480)
        self.assertEqual(body["chunk"]["count"], 134)


if __name__ == "__main__":
    unittest.main()
