"""Log-mel features for a fixed 2 second clip.

This is a small self-contained implementation. It is not meant to match
librosa, and the band edges are a starting point, not a measured meow band.
"""

from functools import lru_cache

import numpy as np
from scipy import signal

from meowmap_ml.audio_spec import (
    BANDPASS_HIGH_HZ,
    BANDPASS_LOW_HZ,
    BANDPASS_ORDER,
    FMAX_HZ,
    FMIN_HZ,
    FRAME_COUNT,
    HOP_LENGTH,
    N_FFT,
    N_MELS,
    SAMPLE_COUNT,
    SAMPLE_RATE_HZ,
    WIN_LENGTH,
)


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1.0)


@lru_cache(maxsize=1)
def mel_filterbank() -> np.ndarray:
    n_freqs = N_FFT // 2 + 1
    mels = np.linspace(_hz_to_mel(FMIN_HZ), _hz_to_mel(FMAX_HZ), N_MELS + 2)
    hz = _mel_to_hz(mels)
    bins = np.floor((N_FFT + 1) * hz / SAMPLE_RATE_HZ).astype(int)
    bins = np.clip(bins, 0, n_freqs - 1)
    weights = np.zeros((N_MELS, n_freqs), dtype=np.float64)
    for i in range(N_MELS):
        left, center, right = int(bins[i]), int(bins[i + 1]), int(bins[i + 2])
        if center <= left:
            center = min(left + 1, n_freqs - 1)
        if right <= center:
            right = min(center + 1, n_freqs - 1)
        for freq in range(left, center):
            weights[i, freq] = (freq - left) / (center - left)
        for freq in range(center, right):
            weights[i, freq] = (right - freq) / (right - center)
    return weights


def bandpass(samples: np.ndarray) -> np.ndarray:
    sos = signal.butter(
        BANDPASS_ORDER,
        [BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ],
        btype="bandpass",
        fs=SAMPLE_RATE_HZ,
        output="sos",
    )
    return signal.sosfiltfilt(sos, samples)


def log_mel(samples: np.ndarray) -> np.ndarray:
    """Return a (frames, mels) log-mel matrix for one int16 clip."""
    if not isinstance(samples, np.ndarray):
        raise TypeError("samples must be a numpy array")
    if samples.dtype != np.int16 or samples.shape != (SAMPLE_COUNT,):
        raise ValueError(
            f"expected int16 shape {(SAMPLE_COUNT,)}, got {samples.dtype} {samples.shape}"
        )
    waveform = samples.astype(np.float64) / 32768.0
    waveform = bandpass(waveform)
    window = np.hanning(WIN_LENGTH)
    weights = mel_filterbank()
    frames = []
    for start in range(0, SAMPLE_COUNT - WIN_LENGTH + 1, HOP_LENGTH):
        piece = waveform[start : start + WIN_LENGTH] * window
        spectrum = np.fft.rfft(piece, n=N_FFT)
        power = spectrum.real * spectrum.real + spectrum.imag * spectrum.imag
        frames.append(power)
    if len(frames) != FRAME_COUNT:
        raise RuntimeError(f"frame count {len(frames)} != {FRAME_COUNT}")
    mel = np.stack(frames, axis=0) @ weights.T
    return np.log(np.maximum(mel, 1e-10))


def summarize(mel: np.ndarray) -> np.ndarray:
    """Mean and standard deviation of each mel band, for the linear model."""
    if mel.ndim != 2 or mel.shape[1] != N_MELS:
        raise ValueError(f"expected (frames, {N_MELS}), got {mel.shape}")
    return np.concatenate([mel.mean(axis=0), mel.std(axis=0)]).astype(np.float64)
