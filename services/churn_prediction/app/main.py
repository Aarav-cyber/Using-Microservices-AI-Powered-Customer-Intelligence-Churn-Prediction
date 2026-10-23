import os
from contextlib import asynccontextmanager
from pathlib import Path
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_PATH = Path(
    os.getenv(
        "MODEL_PATH",
        str(
            Path(__file__).resolve().parent.parent
            / "model"
            / "churn_model.joblib"
        ),
    )
)

VALID_PLANS = {"free", "starter", "professional", "enterprise"}
FEATURES = [
    "account_age_days",
    "monthly_price_usd",
    "support_tickets_90d",
    "days_since_last_login",
    "plan_tier",
]

model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    if not MODEL_PATH.exists():
        print(f"Warning: Model file not found at {MODEL_PATH}")
    else:
        model = joblib.load(MODEL_PATH)
        print(f"Loaded SaaS churn prediction model from {MODEL_PATH}")
    yield


app = FastAPI(
    title="Churn Prediction Service",
    description=(
        "Predicts customer churn probability using "
        "SaaS account and engagement features."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


class ChurnRequest(BaseModel):
    account_age_days: int = Field(ge=0, le=100000)
    monthly_price_usd: float = Field(ge=0, le=1000000)
    support_tickets_90d: int = Field(ge=0, le=10000)
    days_since_last_login: int = Field(ge=0, le=100000)
    plan_tier: str


class ChurnResponse(BaseModel):
    churn_probability: float
    churn_prediction: bool
    risk_level: str


@app.get("/health")
def health():
    return {
        "status": "ok" if model is not None else "unavailable",
        "service": "churn-prediction",
        "model_loaded": model is not None,
        "model_type": "saas",
    }


@app.post(
    "/api/v1/predict",
    response_model=ChurnResponse,
)
def predict_churn(payload: ChurnRequest):
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="SaaS churn prediction model is not loaded.",
        )

    plan = payload.plan_tier.strip().lower()
    if plan not in VALID_PLANS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported plan_tier '{payload.plan_tier}'. "
                f"Expected one of: {sorted(VALID_PLANS)}"
            ),
        )

    input_data = {
        "account_age_days": payload.account_age_days,
        "monthly_price_usd": payload.monthly_price_usd,
        "support_tickets_90d": payload.support_tickets_90d,
        "days_since_last_login": payload.days_since_last_login,
        "plan_tier": plan,
    }

    df = pd.DataFrame([input_data], columns=FEATURES)

    try:
        probabilities = model.predict_proba(df)[0]
        classes = list(model.classes_)
        churn_idx = classes.index(1) if 1 in classes else 1
        prob = float(probabilities[churn_idx])
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Inference error: {exc}",
        )

    if prob >= 0.70:
        risk_level = "high"
    elif prob >= 0.40:
        risk_level = "medium"
    else:
        risk_level = "low"

    return ChurnResponse(
        churn_probability=round(prob, 4),
        churn_prediction=prob >= 0.50,
        risk_level=risk_level,
    )
