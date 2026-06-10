from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from segmentation import run_kmeans
from validation import parse_csv, profile_dataframe

SAMPLE_CANDIDATES = [
    Path(__file__).resolve().parent / "data" / "customers.csv",
    Path(__file__).resolve().parent.parent / "data" / "customers.csv",
]


def _read_sample_csv() -> bytes:
    for path in SAMPLE_CANDIDATES:
        if path.is_file():
            return path.read_bytes()
    tried = ", ".join(str(p) for p in SAMPLE_CANDIDATES)
    raise HTTPException(status_code=500, detail=f"Sample CSV not found. Looked at: {tried}")

app = FastAPI(title="Customer Segmentation Lab", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3200",
        "http://127.0.0.1:3200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_dataset: pd.DataFrame | None = None


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/dataset/status")
def dataset_status() -> dict:
    if _dataset is None:
        return {"loaded": False, "row_count": 0}
    return {"loaded": True, "row_count": int(len(_dataset))}


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict:
    global _dataset

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file")

    content = await file.read()
    try:
        df = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _dataset = df
    return profile_dataframe(df)


@app.post("/sample/load")
@app.get("/sample/load")
def load_sample() -> dict:
    """Load bundled sample dataset (no file picker needed)."""
    global _dataset

    try:
        df = parse_csv(_read_sample_csv())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _dataset = df
    return profile_dataframe(df)


class SegmentRequest(BaseModel):
    k: int = Field(ge=2, le=8, default=4)


@app.post("/segment")
def segment(request: SegmentRequest) -> dict:
    if _dataset is None:
        raise HTTPException(
            status_code=400,
            detail="No dataset loaded. Upload a CSV first.",
        )

    try:
        return run_kmeans(_dataset, request.k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
