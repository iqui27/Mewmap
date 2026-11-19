"""Clip contract shared with schema.json and the firmware.

On disk the dataset uses WAV containers. The samples inside are the same
16 kHz mono signed-16-bit little-endian PCM the firmware publishes raw.
"""

SAMPLE_RATE_HZ = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
DURATION_MS = 2000
SAMPLE_COUNT = SAMPLE_RATE_HZ * DURATION_MS // 1000
CLIP_BYTES = SAMPLE_COUNT * SAMPLE_WIDTH_BYTES

CLASSES = ("hunger", "drama", "attention", "not_cat")
COLLECTION_TARGET = 200
# Below this the script will not write a model file. It is a guard against
# a one-example fit, not a claim that four clips are enough.
MIN_PER_CLASS_TO_TRAIN = 4

WIN_LENGTH = 400  # 25 ms
HOP_LENGTH = 160  # 10 ms
N_FFT = 512
N_MELS = 40
FMIN_HZ = 200.0
FMAX_HZ = 7000.0
BANDPASS_LOW_HZ = 200.0
BANDPASS_HIGH_HZ = 7000.0
BANDPASS_ORDER = 4


def frame_count(
    n_samples: int = SAMPLE_COUNT,
    win: int = WIN_LENGTH,
    hop: int = HOP_LENGTH,
) -> int:
    if n_samples < win:
        return 0
    return 1 + (n_samples - win) // hop


FRAME_COUNT = frame_count()
