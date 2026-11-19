import json
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from meowmap_ml.audio_spec import CLASSES, SAMPLE_COUNT, SAMPLE_RATE_HZ
from meowmap_ml.dataset import read_wav
from meowmap_ml.train import run


def _write_wav(path: Path, frames: int, rate: int = SAMPLE_RATE_HZ) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.zeros(frames, dtype="<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


class TrainTest(unittest.TestCase):
    def test_empty_dataset_refuses_to_train(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "raw"
            out = Path(tmp) / "out"
            for name in CLASSES:
                (root / name).mkdir(parents=True)
            code = run(["--data", str(root), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())

    def test_wrong_wav_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.wav"
            _write_wav(path, frames=100)
            with self.assertRaises(ValueError):
                read_wav(path)

    def test_smoke_model_is_marked_synthetic(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            code = run(["--smoke-test", "--out", str(out)])
            self.assertEqual(code, 0)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["synthetic"])
            self.assertFalse(report["publishable"])
            self.assertIsNone(report["held_out_accuracy"])
            self.assertIn("not meows", report["warning"].lower())
            self.assertTrue((out / "model.joblib").is_file())

    def test_roundtrip_spec_wav(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.wav"
            _write_wav(path, frames=SAMPLE_COUNT)
            clip = read_wav(path)
            self.assertEqual(clip.shape, (SAMPLE_COUNT,))
            self.assertEqual(clip.dtype, np.int16)


if __name__ == "__main__":
    unittest.main()
