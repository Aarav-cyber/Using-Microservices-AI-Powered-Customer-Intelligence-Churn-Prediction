import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from kafka import KafkaProducer
from pydantic import BaseModel, Field

from app.recommendations import recommend_retention_action

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("retention_service")

app = FastAPI(
    title="SaaS Retention Recommendation Service",
    description="Generates SaaS customer retention recommendations.",
    version="2.0.0",
)

producer = None

KAFKA_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:29092",
)


def get_producer():
    global producer

    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVERS,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            acks="all",
            retries=3,
        )

    return producer


class RetentionRequest(BaseModel):
    customer_id: str
    tenant_id: str
    churn_probability: float = Field(ge=0, le=1)
    plan_tier: str
    support_tickets_90d: int = Field(ge=0)
    sentiment: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "retention"}


@app.post("/api/v1/recommendations")
def create_recommendation(payload: RetentionRequest):
    try:
        recommendation = recommend_retention_action(
            churn_probability=payload.churn_probability,
            plan_tier=payload.plan_tier,
            support_tickets_90d=payload.support_tickets_90d,
            sentiment=payload.sentiment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "retention.recommended",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "customer_id": payload.customer_id,
            "tenant_id": payload.tenant_id,
            **recommendation,
        },
    }

    try:
        get_producer().send(
            "retention.recommended",
            value=event,
        ).get(timeout=15)

        logger.info(
            "Published retention recommendation for customer %s",
            payload.customer_id,
        )
    except Exception as exc:
        logger.exception("Failed to publish retention event")
        raise HTTPException(
            status_code=503,
            detail="Could not publish recommendation event",
        ) from exc

    return event
