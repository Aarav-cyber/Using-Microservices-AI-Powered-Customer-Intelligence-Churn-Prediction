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

model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    if not MODEL_PATH.exists():
        print(f"Warning: Model file not found at {MODEL_PATH}")
    else:
        model = joblib.load(MODEL_PATH)
        print(f"Loaded churn prediction model from {MODEL_PATH}")
    yield


app = FastAPI(
    title="Churn Prediction Service",
    description="Estimates customer churn probability based on historical features.",
    version="1.0.0",
    lifespan=lifespan,
)


class ChurnRequest(BaseModel):
    tenure: int = Field(ge=0, le=1000, description="Tenure in months")
    monthly_charges: float = Field(ge=0, le=100000, description="Monthly charges")
    total_charges: float = Field(ge=0, le=10000000, description="Total charges")
    contract: str = Field(description="Contract type e.g. Month-to-month, One year, Two year")
    internet_service: str = Field(description="Internet service e.g. DSL, Fiber optic, No")
    tech_support: str = Field(description="Tech support e.g. Yes, No, No internet service")
    online_security: str = Field(description="Online security e.g. Yes, No, No internet service")
    payment_method: str = Field(description="Payment method e.g. Electronic check, Mailed check, Bank transfer (automatic), Credit card (automatic)")
    paperless_billing: str = Field(description="Paperless billing e.g. Yes, No")


class ChurnResponse(BaseModel):
    churn_probability: float
    churn_prediction: bool
    risk_level: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "churn-prediction",
        "model_loaded": model is not None,
    }


@app.post(
    "/api/v1/predict",
    response_model=ChurnResponse,
)
def predict_churn(payload: ChurnRequest):
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Prediction model is not loaded",
        )

    input_data = {
        "tenure": payload.tenure,
        "MonthlyCharges": payload.monthly_charges,
        "TotalCharges": payload.total_charges,
        "Contract": payload.contract,
        "InternetService": payload.internet_service,
        "TechSupport": payload.tech_support,
        "OnlineSecurity": payload.online_security,
        "PaymentMethod": payload.payment_method,
        "PaperlessBilling": payload.paperless_billing,
    }

    df = pd.DataFrame([input_data])

    try:
        prob = float(model.predict_proba(df)[0, 1])
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Inference error: {exc}",
        )

    if prob >= 0.7:
        risk_level = "high"
    elif prob >= 0.4:
        risk_level = "medium"
    else:
        risk_level = "low"

    return ChurnResponse(
        churn_probability=round(prob, 4),
        churn_prediction=prob >= 0.5,
        risk_level=risk_level,
    )
