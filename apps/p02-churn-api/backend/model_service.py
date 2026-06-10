from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from schemas import CustomerFeatures, FeatureDriver, PredictionResult

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "model.joblib"
METADATA_PATH = ARTIFACTS_DIR / "metadata.json"

FEATURE_COLUMNS = [
    "tenure_months",
    "monthly_charges",
    "total_charges",
    "contract_month",
    "contract_year",
    "contract_two_year",
    "support_calls",
]

FEATURE_LABELS = {
    "tenure_months": "Tenure (months)",
    "monthly_charges": "Monthly charges",
    "total_charges": "Total charges",
    "contract_month": "Month-to-month contract",
    "contract_year": "One-year contract",
    "contract_two_year": "Two-year contract",
    "support_calls": "Support calls",
}


def artifacts_ready() -> bool:
    return MODEL_PATH.exists() and METADATA_PATH.exists()


def load_metadata() -> dict:
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def load_model():
    if not artifacts_ready():
        raise FileNotFoundError(
            "Model artifacts missing. Run: python train.py"
        )
    return joblib.load(MODEL_PATH)


def _to_frame(customer: CustomerFeatures) -> pd.DataFrame:
    contract_month = 1 if customer.contract_type == "month" else 0
    contract_year = 1 if customer.contract_type == "year" else 0
    contract_two_year = 1 if customer.contract_type == "two_year" else 0
    return pd.DataFrame(
        [
            {
                "tenure_months": customer.tenure_months,
                "monthly_charges": customer.monthly_charges,
                "total_charges": customer.total_charges,
                "contract_month": contract_month,
                "contract_year": contract_year,
                "contract_two_year": contract_two_year,
                "support_calls": customer.support_calls,
            }
        ]
    )


def risk_band(probability: float) -> str:
    if probability < 0.33:
        return "low"
    if probability < 0.66:
        return "medium"
    return "high"


def top_drivers(model, row: pd.DataFrame) -> list[FeatureDriver]:
    values = row[FEATURE_COLUMNS].iloc[0].to_numpy(dtype=float)

    if hasattr(model, "coef_"):
        weights = np.abs(model.coef_[0])
        signed = model.coef_[0]
    elif hasattr(model, "feature_importances_"):
        weights = model.feature_importances_
        signed = weights
    else:
        return []

    order = np.argsort(weights)[::-1][:3]
    drivers: list[FeatureDriver] = []
    for idx in order:
        name = FEATURE_COLUMNS[int(idx)]
        impact = round(float(weights[int(idx)]), 4)
        direction = "increases churn" if signed[int(idx)] > 0 else "decreases churn"
        drivers.append(
            FeatureDriver(
                feature=FEATURE_LABELS.get(name, name),
                impact=impact,
                direction=direction,
            )
        )
    return drivers


def predict_one(customer: CustomerFeatures) -> PredictionResult:
    model = load_model()
    meta = load_metadata()
    frame = _to_frame(customer)
    prob = float(model.predict_proba(frame)[0][1])
    return PredictionResult(
        customer_id=customer.customer_id,
        churn_probability=round(prob, 4),
        risk_band=risk_band(prob),
        model_version=meta["model_version"],
        top_drivers=top_drivers(model, frame),
    )
