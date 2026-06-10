from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "churn_audit.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                churn_probability REAL NOT NULL,
                risk_band TEXT NOT NULL,
                model_version TEXT NOT NULL
            )
            """
        )
        conn.commit()


def db_ok() -> bool:
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def log_prediction(
    customer_id: str,
    churn_probability: float,
    risk_band: str,
    model_version: str,
) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO predictions
            (created_at, customer_id, churn_probability, risk_band, model_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (created_at, customer_id, churn_probability, risk_band, model_version),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_predictions(page: int = 1, page_size: int = 25) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM predictions").fetchone()["c"]
        rows = conn.execute(
            """
            SELECT id, created_at, customer_id, churn_probability, risk_band, model_version
            FROM predictions
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
    return [dict(r) for r in rows], int(total)
