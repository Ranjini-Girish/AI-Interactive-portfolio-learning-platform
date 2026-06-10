#!/usr/bin/env python3
"""Train churn model and write artifacts/model.joblib + metadata.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT.parent / "data" / "churn_training.csv"
ARTIFACTS_DIR = ROOT / "artifacts"
MODEL_VERSION = "churn-gb-v1"


def generate_dataset(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    tenure = rng.integers(1, 72, size=n)
    monthly = rng.uniform(20, 120, size=n).round(2)
    total = (monthly * tenure * rng.uniform(0.8, 1.2, size=n)).round(2)
    contract = rng.choice(["month", "year", "two_year"], size=n, p=[0.45, 0.35, 0.2])
    support = rng.integers(0, 8, size=n)

    churn_score = (
        0.12 * (72 - tenure)
        + 0.04 * monthly
        + 0.08 * support
        + np.where(contract == "month", 2.5, 0.0)
        + np.where(contract == "year", 0.5, 0.0)
        - 2.0
    )
    churn = (churn_score > 0).astype(int)

    return pd.DataFrame(
        {
            "customer_id": [f"C{i:05d}" for i in range(n)],
            "tenure_months": tenure,
            "monthly_charges": monthly,
            "total_charges": total,
            "contract_type": contract,
            "support_calls": support,
            "churn": churn,
        }
    )


def prepare_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    features = df.copy()
    features["contract_month"] = (features["contract_type"] == "month").astype(int)
    features["contract_year"] = (features["contract_type"] == "year").astype(int)
    features["contract_two_year"] = (features["contract_type"] == "two_year").astype(int)

    x_cols = [
        "tenure_months",
        "monthly_charges",
        "total_charges",
        "contract_month",
        "contract_year",
        "contract_two_year",
        "support_calls",
    ]
    return features[x_cols], features["churn"]


def main() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        print(f"Writing synthetic dataset to {DATA_PATH}")
        generate_dataset().to_csv(DATA_PATH, index=False)

    df = pd.read_csv(DATA_PATH)
    x, y = prepare_features(df)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42, stratify=y
    )

    model = GradientBoostingClassifier(random_state=42)
    model.fit(x_train, y_train)
    auc = float(roc_auc_score(y_test, model.predict_proba(x_test)[:, 1]))

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, ARTIFACTS_DIR / "model.joblib")

    metadata = {
        "model_version": MODEL_VERSION,
        "algorithm": "GradientBoostingClassifier",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "auc_holdout": round(auc, 4),
        "feature_columns": list(x.columns),
        "training_rows": int(len(x_train)),
        "holdout_rows": int(len(x_test)),
    }
    (ARTIFACTS_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"AUC (holdout): {auc:.4f}")
    if auc < 0.75:
        print(f"WARNING: AUC below 0.75 mentor target — model saved for demo use.")
    print(f"Artifacts written to {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
