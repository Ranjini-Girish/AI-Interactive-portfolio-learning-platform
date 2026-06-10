from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from db import db_ok, init_db, list_predictions, log_prediction
from model_service import artifacts_ready, load_metadata, predict_one
from schemas import (
    BatchPredictRequest,
    BatchPredictResponse,
    CustomerFeatures,
    PredictionHistoryResponse,
    PredictionLogItem,
    PredictionResult,
)

app = FastAPI(
    title="Churn Prediction API",
    version="0.1.0",
    description="Banking churn scoring with audit log and batch inference.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    meta = load_metadata() if artifacts_ready() else None
    return {
        "ok": True,
        "db_ok": db_ok(),
        "model_loaded": artifacts_ready(),
        "model_version": meta["model_version"] if meta else None,
    }


@app.get("/model/metadata")
def model_metadata() -> dict:
    if not artifacts_ready():
        raise HTTPException(status_code=503, detail="Model not trained. Run train.py first.")
    return load_metadata()


@app.post("/predict", response_model=PredictionResult)
def predict(customer: CustomerFeatures) -> PredictionResult:
    try:
        result = predict_one(customer)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    log_prediction(
        result.customer_id,
        result.churn_probability,
        result.risk_band,
        result.model_version,
    )
    return result


@app.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(body: BatchPredictRequest) -> BatchPredictResponse:
    if len(body.customers) > 500:
        raise HTTPException(status_code=422, detail="Batch limit is 500 customers")

    predictions: list[PredictionResult] = []
    try:
        for customer in body.customers:
            result = predict_one(customer)
            log_prediction(
                result.customer_id,
                result.churn_probability,
                result.risk_band,
                result.model_version,
            )
            predictions.append(result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return BatchPredictResponse(predictions=predictions, count=len(predictions))


@app.get("/predictions", response_model=PredictionHistoryResponse)
def prediction_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> PredictionHistoryResponse:
    rows, total = list_predictions(page, page_size)
    return PredictionHistoryResponse(
        items=[PredictionLogItem(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
