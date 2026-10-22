import json
import os
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:29092",
)

TOPIC = "feedback.submitted"

_producer = None


def get_producer():
    global _producer

    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda value: json.dumps(
                value
            ).encode("utf-8"),
            acks="all",
            retries=3,
            max_block_ms=10000,
            request_timeout_ms=10000,
        )

    return _producer


def publish_feedback(feedback):
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "feedback.submitted",
        "occurred_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "data": {
            "feedback_id": feedback.id,
            "customer_id": feedback.customer_id,
            "message": feedback.message,
            "channel": feedback.channel,
            "created_at": feedback.created_at.isoformat(),
        },
    }

    producer = get_producer()

    producer.send(TOPIC, value=event).get(timeout=15)

    return event