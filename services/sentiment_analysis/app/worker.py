import json
import logging
import os
import time
from kafka import KafkaConsumer, KafkaProducer

from app.analyzer import analyze_sentiment
from app.database import Base, SessionLocal, engine
from app.models import SentimentResult

logger = logging.getLogger("sentiment_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
INPUT_TOPIC = "feedback.submitted"
OUTPUT_TOPIC = "sentiment.completed"
GROUP_ID = "sentiment-analysis-group"


def save_result(data: dict) -> None:
    with SessionLocal() as db:
        existing = db.get(SentimentResult, data["feedback_id"])
        if existing:
            logger.info("Feedback %s already analyzed. Skipping duplicate DB insert.", data["feedback_id"])
            return

        result = SentimentResult(
            feedback_id=data["feedback_id"],
            customer_id=data["customer_id"],
            message=data["message"],
            sentiment=data["sentiment"],
            positive_score=data["positive_score"],
            neutral_score=data["neutral_score"],
            negative_score=data["negative_score"],
        )
        db.add(result)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise


def main() -> None:
    Base.metadata.create_all(bind=engine)

    consumer = None
    producer = None

    # Retry connecting to Kafka
    for attempt in range(1, 11):
        try:
            logger.info("Connecting to Kafka at %s (attempt %d/10)...", BOOTSTRAP_SERVERS, attempt)
            consumer = KafkaConsumer(
                INPUT_TOPIC,
                bootstrap_servers=BOOTSTRAP_SERVERS,
                group_id=GROUP_ID,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                value_deserializer=lambda value: json.loads(
                    value.decode("utf-8")
                ),
            )
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS,
                value_serializer=lambda value: json.dumps(
                    value
                ).encode("utf-8"),
                acks="all",
                retries=3,
            )
            logger.info("Connected to Kafka successfully.")
            break
        except Exception as exc:
            logger.warning("Kafka not ready yet: %s. Retrying in 3 seconds...", exc)
            time.sleep(3)

    if not consumer or not producer:
        logger.error("Could not establish connection to Kafka. Exiting worker.")
        return

    logger.info("Listening to %s", INPUT_TOPIC)
    try:
        for record in consumer:
            event = record.value
            try:
                data = event["data"]
                # Require tenant identity on incoming events.
                tenant_id = data["tenant_id"]
                result = analyze_sentiment(data["message"])
                # Preserve tenant identity in the downstream event.
                output_event = {
                    "event_id": event.get("event_id"),
                    "event_type": OUTPUT_TOPIC,
                    "data": {
                        "feedback_id": data["feedback_id"],
                        "tenant_id": tenant_id,
                        "customer_id": data["customer_id"],
                        **result,
                    },
                }
                save_result({
                    "feedback_id": data["feedback_id"],
                    "tenant_id": tenant_id,
                    "customer_id": data["customer_id"],
                    "message": data["message"],
                    **result,
                })
                producer.send(
                    OUTPUT_TOPIC,
                    value=output_event,
                ).get(timeout=15)
                # Commit only after persistence and publishing succeed.
                consumer.commit()
                logger.info(
                    "Processed feedback %s for tenant %s "
                    "(sentiment: %s, compound: %.2f)",
                    data["feedback_id"],
                    tenant_id,
                    result["sentiment"],
                    result["compound_score"],
                )
            except Exception:
                logger.exception("Error processing record")
    finally:
        consumer.close()
        producer.close()


if __name__ == "__main__":
    main()
