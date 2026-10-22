import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from kafka import KafkaProducer
from pydantic import BaseModel, Field

from app.recommendations import recommend_retention_action

logger = logging.getLogger("retention_service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Retention Recommendation Service",
    description="Generates actionable retention recommendations and publishes Kafka events.",
    version="1.0.0",
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
    churn_probability: float = Field(ge=0, le=1)
    contract: str
    tech_support: str
    sentiment: str | None = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "retention",
    }


@app.post("/api/v1/recommendations")
def create_recommendation(payload: RetentionRequest):
    recommendation = recommend_retention_action(
        churn_probability=payload.churn_probability,
        contract=payload.contract,
        tech_support=payload.tech_support,
        sentiment=payload.sentiment,
    )

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "retention.recommended",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "customer_id": payload.customer_id,
            **recommendation,
        },
    }

    try:
        kafka_producer = get_producer()
        kafka_producer.send(
            "retention.recommended",
            value=event,
        ).get(timeout=15)
        logger.info(
            "Published retention.recommended event for customer %s",
            payload.customer_id,
        )
    except Exception as exc:
        logger.error("Failed to publish retention event: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not publish recommendation event",
        ) from exc

    return event
