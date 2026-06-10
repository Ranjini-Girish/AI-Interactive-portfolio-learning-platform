from __future__ import annotations

import io
import re

import pandas as pd

REQUIRED_COLUMNS = ["customer_id", "txn_count", "avg_balance", "monthly_spend"]
FEATURE_COLUMNS = ["txn_count", "avg_balance", "monthly_spend"]

# Common export labels -> canonical names
ALIASES: dict[str, list[str]] = {
    "customer_id": [
        "customer_id",
        "customerid",
        "cust_id",
        "custid",
        "client_id",
        "id",
        "customer",
    ],
    "txn_count": [
        "txn_count",
        "transaction_count",
        "transactioncount",
        "num_transactions",
        "transactions",
        "txn",
    ],
    "avg_balance": [
        "avg_balance",
        "average_balance",
        "avgbalance",
        "balance",
        "account_balance",
        "mean_balance",
    ],
    "monthly_spend": [
        "monthly_spend",
        "monthlyspend",
        "spend",
        "monthly_spending",
        "avg_spend",
        "total_spend",
    ],
}


def _normalize_header(name: str) -> str:
    text = str(name).strip().lower()
    text = text.replace("\ufeff", "")
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[^\w]", "", text)
    return text


def _read_flexible(content: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=encoding, sep=sep)
                if len(df.columns) >= len(REQUIRED_COLUMNS) and len(df) > 0:
                    return df
            except Exception as exc:
                last_error = exc
                continue
    raise ValueError(
        f"Could not parse CSV. Use comma-separated headers: {', '.join(REQUIRED_COLUMNS)}"
        + (f" ({last_error})" if last_error else "")
    )


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = {_normalize_header(c): c for c in df.columns}
    rename: dict[str, str] = {}

    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized:
                rename[normalized[key]] = canonical
                break

    df = df.rename(columns=rename)
    return df


def parse_csv(content: bytes) -> pd.DataFrame:
    df = _read_flexible(content)
    df = _map_columns(df)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        found = ", ".join(str(c) for c in df.columns) or "(none)"
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}. "
            f"Found in file: {found}. "
            f"Expected: {', '.join(REQUIRED_COLUMNS)}"
        )

    df = df[REQUIRED_COLUMNS].copy()
    for col in FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[FEATURE_COLUMNS].isna().any().any():
        raise ValueError("Numeric columns contain invalid or missing values")

    df["customer_id"] = df["customer_id"].astype(str).str.strip()
    df = df[df["customer_id"].astype(bool)]
    if df.empty:
        raise ValueError("CSV has no valid customer rows")

    return df


def profile_dataframe(df: pd.DataFrame) -> dict:
    return {
        "row_count": int(len(df)),
        "columns": list(df.columns),
        "stats": {
            col: {
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": round(float(df[col].mean()), 2),
            }
            for col in FEATURE_COLUMNS
        },
    }
