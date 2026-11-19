"""WAV dataset laid out as one folder per class.

A clip is accepted only when it is exactly the firmware spec: 16 kHz, mono,
16-bit, 2.0 seconds. There is no resampler in this scaffold.
"""

import wave
from pathlib import Path

import numpy as np

from meowmap_ml.audio_spec import (
    CHANNELS,
    CLASSES,
    CLIP_BYTES,
    COLLECTION_TARGET,
    MIN_PER_CLASS_TO_TRAIN,
    SAMPLE_COUNT,
    SAMPLE_RATE_HZ,
    SAMPLE_WIDTH_BYTES,
)

ML_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ML_ROOT / "data" / "raw"


class DatasetFormatError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} clip(s) do not match the audio spec")


def class_dir(root: Path, name: str) -> Path:
    if name not in CLASSES:
        raise ValueError(f"unknown class {name!r}")
    return root / name


def count_wavs(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in CLASSES:
        folder = root / name
        if not folder.is_dir():
            counts[name] = 0
            continue
        counts[name] = sum(1 for _ in folder.glob("*.wav"))
    return counts


def readiness(counts: dict[str, int]) -> str:
    if any(counts.get(name, 0) < MIN_PER_CLASS_TO_TRAIN for name in CLASSES):
        return "too_small"
    if any(counts.get(name, 0) < COLLECTION_TARGET for name in CLASSES):
        return "below_target"
    return "at_target"


def format_counts(counts: dict[str, int]) -> str:
    parts = [f"{name}={counts.get(name, 0)}" for name in CLASSES]
    return (
        ", ".join(parts)
        + f" (script minimum {MIN_PER_CLASS_TO_TRAIN}/class,"
        + f" collection target about {COLLECTION_TARGET}/class)"
    )


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        width = handle.getsampwidth()
        frames = handle.getnframes()
        if (
            channels != CHANNELS
            or rate != SAMPLE_RATE_HZ
            or width != SAMPLE_WIDTH_BYTES
            or frames != SAMPLE_COUNT
        ):
            raise ValueError(
                "expected mono 16 kHz 16-bit WAV of exactly "
                f"{SAMPLE_COUNT} frames ({CLIP_BYTES} PCM bytes); "
                f"got channels={channels} rate={rate} width={width} frames={frames}"
            )
        raw = handle.readframes(frames)
    if len(raw) != CLIP_BYTES:
        raise ValueError(f"expected {CLIP_BYTES} PCM bytes, read {len(raw)}")
    return np.frombuffer(raw, dtype="<i2").copy()


def load_labeled(root: Path) -> tuple[list[np.ndarray], list[str]]:
    clips: list[np.ndarray] = []
    labels: list[str] = []
    problems: list[str] = []
    for name in CLASSES:
        folder = root / name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.wav")):
            try:
                clips.append(read_wav(path))
                labels.append(name)
            except ValueError as exc:
                problems.append(f"{path}: {exc}")
    if problems:
        raise DatasetFormatError(problems)
    return clips, labels
