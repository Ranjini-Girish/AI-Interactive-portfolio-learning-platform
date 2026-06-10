from __future__ import annotations

from pydantic import BaseModel, Field


class CustomerFeatures(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    tenure_months: int = Field(ge=0, le=120)
    monthly_charges: float = Field(ge=0, le=500)
    total_charges: float = Field(ge=0)
    contract_type: str = Field(pattern=r"^(month|year|two_year)$")
    support_calls: int = Field(ge=0, le=20)


class FeatureDriver(BaseModel):
    feature: str
    impact: float
    direction: str


class PredictionResult(BaseModel):
    customer_id: str
    churn_probability: float
    risk_band: str
    model_version: str
    top_drivers: list[FeatureDriver]


class BatchPredictRequest(BaseModel):
    customers: list[CustomerFeatures] = Field(min_length=1, max_length=500)


class BatchPredictResponse(BaseModel):
    predictions: list[PredictionResult]
    count: int


class PredictionLogItem(BaseModel):
    id: int
    created_at: str
    customer_id: str
    churn_probability: float
    risk_band: str
    model_version: str


class PredictionHistoryResponse(BaseModel):
    items: list[PredictionLogItem]
    total: int
    page: int
    page_size: int
