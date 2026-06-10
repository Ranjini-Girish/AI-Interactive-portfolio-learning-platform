from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from validation import FEATURE_COLUMNS

SEGMENT_NAMES = [
    "High-value active",
    "Steady savers",
    "Budget conscious",
    "Occasional spenders",
    "Premium transactors",
    "Low-activity dormant",
    "Growth potential",
    "At-risk low balance",
]


def run_kmeans(df: pd.DataFrame, k: int) -> dict:
    if k < 2 or k > 8:
        raise ValueError("k must be between 2 and 8")

    features = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)

    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(scaled)

    sil = float(silhouette_score(scaled, labels)) if len(set(labels)) > 1 else 0.0
    centroids = scaler.inverse_transform(model.cluster_centers_)

    labeled = []
    for row, label in zip(df.itertuples(index=False), labels):
        labeled.append(
            {
                "customer_id": row.customer_id,
                "txn_count": float(row.txn_count),
                "avg_balance": float(row.avg_balance),
                "monthly_spend": float(row.monthly_spend),
                "segment_id": int(label),
                "segment_name": SEGMENT_NAMES[int(label) % len(SEGMENT_NAMES)],
            }
        )

    centroid_payload = []
    for idx, center in enumerate(centroids):
        centroid_payload.append(
            {
                "segment_id": idx,
                "segment_name": SEGMENT_NAMES[idx % len(SEGMENT_NAMES)],
                "txn_count": round(float(center[0]), 2),
                "avg_balance": round(float(center[1]), 2),
                "monthly_spend": round(float(center[2]), 2),
            }
        )

    return {
        "customers": labeled,
        "centroids": centroid_payload,
        "metrics": {
            "k": k,
            "silhouette_score": round(sil, 4),
            "inertia": round(float(model.inertia_), 2),
        },
    }
