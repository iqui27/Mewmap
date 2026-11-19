import unittest

import numpy as np

from meowmap_ml.audio_spec import FRAME_COUNT, N_MELS, SAMPLE_COUNT, SAMPLE_RATE_HZ
from meowmap_ml.features import log_mel


def _tone(freq_hz: float, amplitude: float) -> np.ndarray:
    time = np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ
    wave = amplitude * np.sin(2.0 * np.pi * freq_hz * time)
    return np.clip(np.round(wave * 32767.0), -32768, 32767).astype(np.int16)


class FeaturesTest(unittest.TestCase):
    def test_shape_and_finite(self):
        mel = log_mel(_tone(700.0, 0.2))
        self.assertEqual(mel.shape, (FRAME_COUNT, N_MELS))
        self.assertTrue(np.isfinite(mel).all())

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValueError):
            log_mel(np.zeros(100, dtype=np.int16))

    def test_louder_clip_has_higher_mean_energy(self):
        quiet = log_mel(_tone(700.0, 0.02)).mean()
        loud = log_mel(_tone(700.0, 0.4)).mean()
        self.assertGreater(loud, quiet)


if __name__ == "__main__":
    unittest.main()
