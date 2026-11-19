"""Train a small linear model on log-mel summaries.

With no WAV files this exits without writing a model and without a score.
`--smoke-test` fits the same code on synthetic tones so the path can be
checked. That fit is not a meow classifier.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from meowmap_ml.audio_spec import CLASSES, COLLECTION_TARGET
from meowmap_ml.dataset import (
    DEFAULT_RAW,
    DatasetFormatError,
    count_wavs,
    format_counts,
    load_labeled,
    readiness,
)
from meowmap_ml.features import log_mel, summarize
from meowmap_ml.synthetic import make_clips

ML_ROOT = Path(__file__).resolve().parents[1]


def _vectors(clips: list[np.ndarray]) -> np.ndarray:
    return np.stack([summarize(log_mel(clip)) for clip in clips])


def _report(
    *,
    synthetic: bool,
    counts: dict[str, int],
    state: str,
    held_out_accuracy: float | None,
) -> dict:
    warning = (
        "Synthetic tones are not meows. Do not cite any score in this file as a meowmap result."
        if synthetic
        else "This scaffold does not mark an artifact publishable, even when the collection target is met."
    )
    if not synthetic and state == "below_target":
        warning = (
            "The set is below the collection target of about "
            f"{COLLECTION_TARGET} clips per class. This file is not a result."
        )
    return {
        "project": "meowmap",
        "schema_version": "0.1.0",
        "artifact": "sklearn_logmel_summary",
        "synthetic": synthetic,
        "publishable": False,
        "collection_target_per_class": COLLECTION_TARGET,
        "counts": counts,
        "readiness": state,
        "labels": list(CLASSES),
        "held_out_accuracy": held_out_accuracy,
        "warning": warning,
    }


def fit_sklearn(
    clips: list[np.ndarray],
    labels: list[str],
    out_dir: Path,
    *,
    synthetic: bool,
    counts: dict[str, int],
    seed: int,
) -> dict:
    features = _vectors(clips)
    target = np.asarray(labels)
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    train_idx, test_idx = next(splitter.split(features, target))
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )
    model.fit(features[train_idx], target[train_idx])
    accuracy = float(model.score(features[test_idx], target[test_idx]))
    state = "synthetic" if synthetic else readiness(counts)
    import joblib

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "labels": list(CLASSES),
            "synthetic": synthetic,
            "publishable": False,
        },
        out_dir / "model.joblib",
    )
    report = _report(
        synthetic=synthetic,
        counts=counts,
        state=state,
        # A score on tones is not a meow result, so it is not written down.
        held_out_accuracy=None if synthetic else accuracy,
    )
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the meowmap linear baseline.")
    parser.add_argument("--data", type=Path, default=DEFAULT_RAW, help="class folders of WAV clips")
    parser.add_argument("--out", type=Path, default=ML_ROOT / "models" / "sklearn")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="fit on synthetic tones and mark the artifact as not a result",
    )
    args = parser.parse_args(argv)

    if args.smoke_test:
        clips, labels = make_clips(per_class=8, seed=args.seed)
        counts = {name: 8 for name in CLASSES}
        synthetic = True
    else:
        counts = count_wavs(args.data)
        state = readiness(counts)
        if state == "too_small":
            print(
                "meowmap train: not writing a model. " + format_counts(counts),
                file=sys.stderr,
            )
            print(
                "Add WAV clips under data/raw/{hunger,drama,attention,not_cat}/ "
                "or pass --smoke-test to exercise the code on synthetic tones.",
                file=sys.stderr,
            )
            return 2
        try:
            clips, labels = load_labeled(args.data)
        except DatasetFormatError as exc:
            print("meowmap train: clips do not match the audio spec:", file=sys.stderr)
            for problem in exc.problems:
                print(f"  {problem}", file=sys.stderr)
            return 2
        synthetic = False

    report = fit_sklearn(
        clips,
        labels,
        args.out,
        synthetic=synthetic,
        counts=counts,
        seed=args.seed,
    )
    print(
        "meowmap train: "
        f"synthetic={str(report['synthetic']).lower()} "
        f"publishable={str(report['publishable']).lower()}"
    )
    print(f"meowmap train: wrote {args.out / 'report.json'}")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
