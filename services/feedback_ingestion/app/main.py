from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.events import publish_feedback
from app.models import Feedback
from app.schemas import FeedbackCreate, FeedbackRead


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Feedback Ingestion Service",
    description="Stores customer feedback and publishes Kafka events.",
    version="1.0.0",
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
    feedback = Feedback(
        customer_id=str(payload.customer_id),
        message=payload.message.strip(),
        channel=payload.channel.strip(),
    )

    if not feedback.message:
        raise HTTPException(
            status_code=422,
            detail="Feedback message cannot be empty.",
        )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    try:
        publish_feedback(feedback)
    except Exception:
        # The feedback is saved, but the event may not
        # have reached Kafka. A durable retry/outbox
        # mechanism should be added before production.
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
    customer_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    query = select(Feedback).order_by(
        Feedback.created_at.desc()
    )

    if customer_id:
        query = query.where(
            Feedback.customer_id == customer_id
        )

    query = query.limit(limit)

    return list(db.scalars(query).all())