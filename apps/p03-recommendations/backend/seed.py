#!/usr/bin/env python3
"""Seed 500 products and 10k interaction events into SQLite."""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import DB_PATH, connect, init_db

CATEGORIES = ["jackets", "fleece", "shirts", "pants", "shoes", "accessories"]
TAGS = {
    "jackets": ["waterproof", "insulated", "hiking", "winter"],
    "fleece": ["warm", "layering", "outdoor"],
    "shirts": ["moisture-wicking", "casual", "sun-protection"],
    "pants": ["hiking", "convertible", "durable"],
    "shoes": ["trail", "waterproof", "lightweight"],
    "accessories": ["hat", "gloves", "backpack", "socks"],
}
USERS = [f"user-{i:04d}" for i in range(1, 201)]
EVENTS = ["view", "click", "cart", "purchase"]


def seed(force: bool = False) -> None:
    init_db()
    if not force and DB_PATH.exists():
        with connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if n >= 500:
                print(f"Already seeded ({n} products). Use --force to reseed.")
                return

    if force and DB_PATH.exists():
        DB_PATH.unlink()

    init_db()
    rng = random.Random(42)
    now = datetime.now(timezone.utc)

    products = []
    for i in range(1, 501):
        cat = rng.choice(CATEGORIES)
        tag_sample = rng.sample(TAGS[cat], k=min(2, len(TAGS[cat])))
        products.append(
            (
                f"prod-{i:04d}",
                f"Columbia {cat[:-1].capitalize()} {i % 50}",
                cat,
                ",".join(tag_sample),
                f"https://picsum.photos/seed/{i}/400/400",
                round(rng.uniform(29, 249), 2),
            )
        )

    interactions = []
    for _ in range(10_000):
        interactions.append(
            (
                rng.choice(USERS),
                f"prod-{rng.randint(1, 500):04d}",
                rng.choices(EVENTS, weights=[50, 25, 15, 10])[0],
                (now - timedelta(days=rng.randint(0, 90))).isoformat(),
            )
        )

    with connect() as conn:
        conn.executemany(
            "INSERT INTO products (product_id, title, category, tags, image_url, price) VALUES (?,?,?,?,?,?)",
            products,
        )
        conn.executemany(
            "INSERT INTO interactions (user_id, product_id, event_type, ts) VALUES (?,?,?,?)",
            interactions,
        )
        conn.commit()

    print(f"Seeded {len(products)} products and {len(interactions)} interactions -> {DB_PATH}")


if __name__ == "__main__":
    import sys

    seed(force="--force" in sys.argv)
