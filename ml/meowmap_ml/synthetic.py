"""Deterministic tones used only to exercise the training path.

These are not meows. Callers must mark every artifact they produce as
synthetic and not publishable.
"""

import numpy as np

from meowmap_ml.audio_spec import CLASSES, SAMPLE_COUNT, SAMPLE_RATE_HZ

# Distinct tones so a pipeline that ignores its input fails a smoke test
# for a mechanical reason. The frequencies are not meow formants.
_TONES_HZ = {
    "hunger": 700.0,
    "drama": 1200.0,
    "attention": 400.0,
    "not_cat": 2000.0,
}


def make_clips(per_class: int = 8, seed: int = 0) -> tuple[list[np.ndarray], list[str]]:
    if per_class < 1:
        raise ValueError("per_class must be positive")
    rng = np.random.default_rng(seed)
    time = np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ
    clips: list[np.ndarray] = []
    labels: list[str] = []
    for label in CLASSES:
        freq = _TONES_HZ[label]
        for index in range(per_class):
            if label == "not_cat":
                wave = 0.05 * rng.standard_normal(SAMPLE_COUNT)
            else:
                amplitude = 0.15 + 0.02 * (index % 3)
                wave = amplitude * np.sin(2.0 * np.pi * freq * time)
                wave = wave + 0.01 * rng.standard_normal(SAMPLE_COUNT)
            pcm = np.clip(np.round(wave * 32767.0), -32768, 32767).astype(np.int16)
            clips.append(pcm)
            labels.append(label)
    return clips, labels
