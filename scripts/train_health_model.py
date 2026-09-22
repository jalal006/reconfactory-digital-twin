"""Train on healthy sequences, evaluate held-out scenarios, save a local artifact."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maintenance.ml import DEFAULT_MODEL, evaluate_model, train_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    estimator = train_model(args.seed)
    evaluation = evaluate_model(estimator)
    estimator.metadata["evaluation"] = evaluation
    estimator.save(args.output)
    print(json.dumps(evaluation, indent=2))
    print(f"Saved {args.output} and metadata JSON. Load only trusted local artifacts.")


if __name__ == "__main__":
    main()
