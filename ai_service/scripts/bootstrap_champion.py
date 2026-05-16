"""Bootstrap the Champion v1 model.

Trains the first model version off the highest-priority data source the AI
service can find (Kaggle preferred; falls back to synthetic) and immediately
promotes it to CHAMPION so the prediction endpoints have something to serve.

Run from the ``ai_service/`` directory::

    python -m scripts.bootstrap_champion              # auto-pick source
    python -m scripts.bootstrap_champion --source kaggle
    python -m scripts.bootstrap_champion --source synthetic

If a CHAMPION already exists this script no-ops (use ``--force`` to retrain
v{N+1} and re-promote).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.ml.registry import (
    get_champion,
    list_versions,
    promote_candidate,
    register_candidate,
)
from app.ml.trainer import next_version_number, train_model
from app.pipeline.data_loader import DataSource, load_training_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bootstrap_champion")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bootstrap the AI Champion model.")
    p.add_argument(
        "--source",
        choices=["auto", "kaggle", "synthetic", "live"],
        default="auto",
        help="Which data source to train on (default: auto).",
    )
    p.add_argument(
        "--holdout-days",
        type=int,
        default=14,
        help="Number of trailing days reserved for holdout MAE (default: 14).",
    )
    p.add_argument(
        "--rows",
        type=int,
        default=None,
        help="Optional cap on the number of training rows (handy for fast smoke runs).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Train + promote a new version even if a CHAMPION already exists.",
    )
    p.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Optional notes to attach to the registry row.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    prefer = {
        "auto": None,
        "kaggle": DataSource.KAGGLE,
        "synthetic": DataSource.SYNTHETIC,
        "live": DataSource.LIVE,
    }[args.source]

    with SessionLocal() as db:
        existing_champion = get_champion(db)
        if existing_champion and not args.force:
            logger.info(
                "Champion already exists: v%d (MAE=%.4f, path=%s). Use --force to retrain.",
                existing_champion.version,
                existing_champion.holdout_mae or 0.0,
                existing_champion.model_path,
            )
            return 0

        logger.info("Loading training data (prefer=%s)...", args.source)
        load = load_training_data(db=db, prefer=prefer)
        logger.info(
            "Loaded %d rows from %s (%s)",
            load.rows,
            load.source.value,
            load.description,
        )

        df = load.df
        if args.rows is not None and len(df) > args.rows:
            df = df.head(args.rows).copy()
            logger.info("Capped training data to first %d rows for speed.", args.rows)

        next_version = next_version_number(list_versions(db))
        model_dir = Path(settings.MODEL_DIR)
        logger.info("Training v%d -> %s", next_version, model_dir / f"v{next_version}.joblib")

        result = train_model(
            df,
            model_dir=model_dir,
            version=next_version,
            holdout_days=args.holdout_days,
        )
        logger.info(
            "Trained v%d: holdout MAE=%.4f over %d rows (best_iter=%d, %.1fs).",
            next_version,
            result.holdout_mae,
            result.holdout_rows,
            result.best_iteration,
            result.runtime_seconds,
        )

        candidate = register_candidate(
            db,
            version=next_version,
            model_path=str(result.model_path),
            holdout_mae=result.holdout_mae,
            training_rows_used=result.training_rows,
            training_source=load.source.value,
            feature_columns=result.state.feature_columns,
            notes=args.notes or f"Bootstrap from {load.source.value}",
        )
        logger.info("Registered CANDIDATE v%d (id=%s)", candidate.version, candidate.id)

        promoted = promote_candidate(
            db,
            candidate_version=candidate.version,
            reason="bootstrap",
            payload=result.to_log_payload(),
        )
        logger.info(
            "Promoted v%d to CHAMPION (path=%s).",
            promoted.version,
            promoted.model_path,
        )

    print()
    print(f"Champion v{promoted.version} ready at {promoted.model_path}")
    print(f"Holdout MAE: {result.holdout_mae:.4f} ({result.holdout_rows} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
