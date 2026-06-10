from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "reco.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                tags TEXT NOT NULL,
                image_url TEXT NOT NULL,
                price REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ts TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
            """
        )
        conn.commit()


def count_products() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])


def count_interactions() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0])
