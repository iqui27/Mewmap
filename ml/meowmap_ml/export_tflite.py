"""Export a tiny CNN to TensorFlow Lite.

The network is a single 3x3 convolution and a softmax over the four class
names. `--smoke-test` trains it for one epoch on synthetic tones and writes
a `.tflite` file so the converter path can be checked. The file is not a
meow classifier and is not sized or tested for an ESP32.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from meowmap_ml.audio_spec import (
    BANDPASS_HIGH_HZ,
    BANDPASS_LOW_HZ,
    CLASSES,
    COLLECTION_TARGET,
    FMAX_HZ,
    FMIN_HZ,
    FRAME_COUNT,
    HOP_LENGTH,
    N_FFT,
    N_MELS,
    SAMPLE_RATE_HZ,
    WIN_LENGTH,
)
from meowmap_ml.dataset import (
    DEFAULT_RAW,
    DatasetFormatError,
    count_wavs,
    format_counts,
    load_labeled,
    readiness,
)
from meowmap_ml.features import log_mel
from meowmap_ml.synthetic import make_clips

ML_ROOT = Path(__file__).resolve().parents[1]


def _matrices(clips: list[np.ndarray]) -> np.ndarray:
    mats = [log_mel(clip).astype(np.float32) for clip in clips]
    stacked = np.stack(mats, axis=0)
    return stacked[..., np.newaxis]


def _label_ids(labels: list[str]) -> np.ndarray:
    index = {name: i for i, name in enumerate(CLASSES)}
    return np.asarray([index[label] for label in labels], dtype=np.int32)


def _sidecar(*, synthetic: bool, counts: dict[str, int], state: str) -> dict:
    if synthetic:
        warning = "Export-path check on synthetic tones. Not a meow classifier and not for the ESP32."
    elif state == "below_target":
        warning = (
            "Trained on fewer clips than the collection target. Not a published result "
            "and not checked on an ESP32."
        )
    else:
        warning = "This scaffold never marks a TFLite file publishable or ready for the device."
    return {
        "project": "meowmap",
        "schema_version": "0.1.0",
        "artifact": "tflite",
        "synthetic": synthetic,
        "publishable": False,
        "device_ready": False,
        "collection_target_per_class": COLLECTION_TARGET,
        "counts": counts,
        "readiness": state,
        "input": {
            "name": "log_mel",
            "dtype": "float32",
            "shape": [1, FRAME_COUNT, N_MELS, 1],
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "window_samples": WIN_LENGTH,
            "hop_samples": HOP_LENGTH,
            "n_fft": N_FFT,
            "n_mels": N_MELS,
            "fmin_hz": FMIN_HZ,
            "fmax_hz": FMAX_HZ,
            "bandpass_hz": [BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ],
        },
        "labels": list(CLASSES),
        "warning": warning,
    }


def export(clips: list[np.ndarray], labels: list[str], out_dir: Path, *, synthetic: bool, counts: dict[str, int], epochs: int) -> dict:
    import tensorflow as tf
    from tensorflow import keras

    features = _matrices(clips)
    targets = _label_ids(labels)
    inputs = keras.Input(shape=(FRAME_COUNT, N_MELS, 1), name="log_mel")
    hidden = keras.layers.Conv2D(4, (3, 3), padding="same", activation="relu")(inputs)
    pooled = keras.layers.GlobalAveragePooling2D()(hidden)
    outputs = keras.layers.Dense(len(CLASSES), activation="softmax", name="label")(pooled)
    model = keras.Model(inputs, outputs)
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy")
    model.fit(features, targets, epochs=epochs, batch_size=min(4, len(clips)), verbose=0)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    tflite_model = converter.convert()
    interpreter = tf.lite.Interpreter(model_content=tflite_model)
    interpreter.allocate_tensors()
    detail = interpreter.get_input_details()[0]
    got = [int(dim) for dim in detail["shape"]]
    want = [1, FRAME_COUNT, N_MELS, 1]
    if got != want:
        raise RuntimeError(f"tflite input shape {got} != {want}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model.tflite").write_bytes(tflite_model)
    state = "synthetic" if synthetic else readiness(counts)
    report = _sidecar(synthetic=synthetic, counts=counts, state=state)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a tiny meowmap CNN to TFLite.")
    parser.add_argument("--data", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=ML_ROOT / "models" / "tflite")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)
    if args.epochs < 1:
        print("meowmap export: --epochs must be >= 1", file=sys.stderr)
        return 2

    if args.smoke_test:
        clips, labels = make_clips(per_class=4, seed=args.seed)
        counts = {name: 4 for name in CLASSES}
        synthetic = True
    else:
        counts = count_wavs(args.data)
        if readiness(counts) == "too_small":
            print("meowmap export: not writing a model. " + format_counts(counts), file=sys.stderr)
            return 2
        try:
            clips, labels = load_labeled(args.data)
        except DatasetFormatError as exc:
            print("meowmap export: clips do not match the audio spec:", file=sys.stderr)
            for problem in exc.problems:
                print(f"  {problem}", file=sys.stderr)
            return 2
        synthetic = False

    try:
        report = export(
            clips,
            labels,
            args.out,
            synthetic=synthetic,
            counts=counts,
            epochs=args.epochs,
        )
    except ImportError:
        print(
            "meowmap export: tensorflow is not installed. Install ml/requirements.txt.",
            file=sys.stderr,
        )
        return 2
    print(
        "meowmap export: "
        f"synthetic={str(report['synthetic']).lower()} "
        f"publishable={str(report['publishable']).lower()} "
        f"device_ready={str(report['device_ready']).lower()}"
    )
    print(f"meowmap export: wrote {args.out / 'model.tflite'}")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
