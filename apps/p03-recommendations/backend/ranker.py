from __future__ import annotations

import math
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from db import connect

WEIGHT = {"view": 1.0, "click": 2.0, "cart": 4.0, "purchase": 6.0}


def load_catalog() -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute(
            "SELECT product_id, title, category, tags, image_url, price FROM products"
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def load_interactions() -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id, product_id, event_type FROM interactions"
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def popularity_scores(interactions: pd.DataFrame) -> dict[str, float]:
    if interactions.empty:
        return {}
    scores: Counter[str] = Counter()
    for row in interactions.itertuples(index=False):
        scores[row.product_id] += WEIGHT.get(row.event_type, 1.0)
    max_s = max(scores.values()) if scores else 1.0
    return {k: v / max_s for k, v in scores.items()}


def item_item_cf(user_id: str, interactions: pd.DataFrame, limit: int) -> dict[str, float]:
    user_rows = interactions[interactions["user_id"] == user_id]
    if user_rows.empty:
        return {}

    user_items = set(user_rows["product_id"])
    item_users: dict[str, set[str]] = defaultdict(set)
    for row in interactions.itertuples(index=False):
        item_users[row.product_id].add(row.user_id)

    scores: Counter[str] = Counter()
    for pid in user_items:
        users = item_users.get(pid, set())
        if len(users) < 2:
            continue
        for other_pid, other_users in item_users.items():
            if other_pid in user_items:
                continue
            overlap = len(users & other_users)
            if overlap:
                scores[other_pid] += overlap / math.sqrt(len(users) * len(other_users))

    if not scores:
        return {}
    max_s = max(scores.values())
    top = scores.most_common(limit)
    return {k: v / max_s for k, v in top}


def content_similarity(
    user_id: str, catalog: pd.DataFrame, interactions: pd.DataFrame, limit: int
) -> dict[str, float]:
    user_rows = interactions[interactions["user_id"] == user_id]
    if user_rows.empty or catalog.empty:
        return {}

    liked = catalog[catalog["product_id"].isin(user_rows["product_id"])]
    if liked.empty:
        return {}

    catalog = catalog.copy()
    catalog["doc"] = catalog["category"] + " " + catalog["tags"].str.replace(",", " ")
    liked_docs = liked["category"] + " " + liked["tags"].str.replace(",", " ")
    profile = " ".join(liked_docs.tolist())

    vec = TfidfVectorizer(stop_words="english")
    matrix = vec.fit_transform(catalog["doc"].tolist() + [profile])
    sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    order = np.argsort(-sims)[:limit]
    out: dict[str, float] = {}
    for idx in order:
        if sims[idx] <= 0:
            continue
        pid = catalog.iloc[int(idx)]["product_id"]
        out[str(pid)] = float(sims[idx])
    return out


def hybrid_recommend(
    user_id: str,
    alpha: float = 0.6,
    limit: int = 20,
) -> list[dict]:
    alpha = max(0.0, min(1.0, alpha))
    catalog = load_catalog()
    interactions = load_interactions()
    pop = popularity_scores(interactions)

    cf = item_item_cf(user_id, interactions, limit * 3)
    content = content_similarity(user_id, catalog, interactions, limit * 3)

    if not cf and not content:
        top_pop = sorted(pop.items(), key=lambda x: -x[1])[:limit]
        ids = [p for p, _ in top_pop]
    else:
        all_ids = set(cf) | set(content) | set(pop)
        ranked: list[tuple[str, float]] = []
        for pid in all_ids:
            score = alpha * cf.get(pid, 0.0) + (1 - alpha) * content.get(pid, 0.0)
            score += 0.15 * pop.get(pid, 0.0)
            ranked.append((pid, score))
        ranked.sort(key=lambda x: -x[1])
        ids = [p for p, _ in ranked[:limit]]

    by_id = catalog.set_index("product_id")
    results = []
    for pid in ids:
        if pid not in by_id.index:
            continue
        row = by_id.loc[pid]
        results.append(
            {
                "product_id": pid,
                "title": row["title"],
                "category": row["category"],
                "tags": row["tags"].split(","),
                "image_url": row["image_url"],
                "price": float(row["price"]),
                "cf_score": round(cf.get(pid, 0.0), 4),
                "content_score": round(content.get(pid, 0.0), 4),
                "popularity": round(pop.get(pid, 0.0), 4),
            }
        )
    return results[:limit]
