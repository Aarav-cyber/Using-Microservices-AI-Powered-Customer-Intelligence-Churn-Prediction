import os
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.events import publish_feedback
from app.models import Feedback
from app.schemas import FeedbackCreate, FeedbackRead

CUSTOMER_PROFILE_URL = os.getenv(
    "CUSTOMER_PROFILE_URL",
    "http://customer-profile:8001",
)


def validate_customer_tenant(customer_id: str, tenant_id: str) -> None:
    url = f"{CUSTOMER_PROFILE_URL}/api/v1/customers/{customer_id}"
    try:
        response = httpx.get(
            url,
            params={"tenant_id": tenant_id},
            timeout=5.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Customer Profile service is unavailable.",
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{customer_id}' does not exist for tenant '{tenant_id}'.",
        )

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to validate customer with Customer Profile service.",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Feedback Ingestion Service",
    description="Stores customer feedback and publishes Kafka events.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "feedback-ingestion",
    }


@app.post(
    "/api/v1/feedback",
    response_model=FeedbackRead,
    status_code=201,
)
def create_feedback(
    payload: FeedbackCreate,
    db: Annotated[Session, Depends(get_db)],
):
    message = payload.message.strip()
    channel = payload.channel.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Feedback message cannot be empty.",
        )

    if not channel:
        raise HTTPException(
            status_code=422,
            detail="Feedback channel cannot be empty.",
        )

    tenant_id = str(payload.tenant_id)
    customer_id = str(payload.customer_id)

    # Validate tenant ownership before persisting feedback.
    validate_customer_tenant(customer_id, tenant_id)

    feedback = Feedback(
        tenant_id=tenant_id,
        customer_id=customer_id,
        message=message,
        channel=channel,
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    try:
        publish_feedback(feedback)
    except Exception:
        # The row remains saved if Kafka publishing fails.
        # A durable outbox/retry mechanism is needed for production.
        print(
            f"WARNING: Feedback {feedback.id} was saved, "
            "but publishing to Kafka failed."
        )

    return feedback


@app.get(
    "/api/v1/feedback",
    response_model=list[FeedbackRead],
)
def list_feedback(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: str,
    customer_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    # Require tenant_id and always scope the query by tenant.
    query = select(Feedback).where(
        Feedback.tenant_id == tenant_id
    )

    if customer_id:
        query = query.where(
            Feedback.customer_id == customer_id
        )

    query = query.order_by(
        Feedback.created_at.desc()
    ).limit(limit)

    return list(db.scalars(query).all())