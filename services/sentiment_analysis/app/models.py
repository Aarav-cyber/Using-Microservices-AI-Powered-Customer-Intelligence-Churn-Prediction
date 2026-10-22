from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SentimentResult(Base):
    __tablename__ = "sentiment_results"

    feedback_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    customer_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    sentiment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    positive_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    neutral_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    negative_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
