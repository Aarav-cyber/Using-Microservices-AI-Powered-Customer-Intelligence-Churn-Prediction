import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import SentimentResult
from app.worker import main as run_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Start Kafka consumer worker as background daemon thread
    worker_thread = threading.Thread(target=run_worker, daemon=True, name="sentiment-worker")
    worker_thread.start()
    yield


app = FastAPI(
    title="Sentiment Analysis Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "sentiment-analysis",
    }


@app.get("/api/v1/sentiments/{feedback_id}")
def get_sentiment(feedback_id: str):
    with SessionLocal() as db:
        result = db.get(SentimentResult, feedback_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Sentiment result not found",
            )
        return {
            "feedback_id": result.feedback_id,
            "customer_id": result.customer_id,
            "sentiment": result.sentiment,
            "positive_score": result.positive_score,
            "neutral_score": result.neutral_score,
            "negative_score": result.negative_score,
            "processed_at": result.processed_at,
        }


@app.get("/api/v1/sentiments")
def list_sentiments(limit: int = 20):
    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=422,
            detail="limit must be between 1 and 100",
        )
    with SessionLocal() as db:
        results = db.scalars(
            select(SentimentResult)
            .order_by(SentimentResult.processed_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "feedback_id": item.feedback_id,
                "customer_id": item.customer_id,
                "sentiment": item.sentiment,
                "positive_score": item.positive_score,
                "neutral_score": item.neutral_score,
                "negative_score": item.negative_score,
                "processed_at": item.processed_at,
            }
            for item in results
        ]
