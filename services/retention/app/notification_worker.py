import json
import logging
import os
import time
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("notification_worker")

BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:29092",
)
TOPIC = "retention.recommended"
GROUP_ID = "notification-worker-v1"


def get_consumer():
    for attempt in range(1, 11):
        try:
            logger.info("Connecting to Kafka at %s (attempt %d/10)...", BOOTSTRAP_SERVERS, attempt)
            consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=BOOTSTRAP_SERVERS,
                group_id=GROUP_ID,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                value_deserializer=lambda value: json.loads(
                    value.decode("utf-8")
                ),
            )
            logger.info("Connected to Kafka successfully.")
            return consumer
        except Exception as exc:
            logger.warning("Kafka not ready yet: %s. Retrying in 3 seconds...", exc)
            time.sleep(3)
    return None


def main():
    consumer = get_consumer()
    if consumer is None:
        logger.error("Could not connect to Kafka after multiple retries. Exiting.")
        return

    logger.info("Listening for retention recommendations on topic: %s", TOPIC)
    try:
        for record in consumer:
            event = record.value
            try:
                data = event["data"]
                actions_str = "; ".join(data.get("recommended_actions", []))
                logger.info(
                    "NOTIFICATION | customer=%s | risk=%s | actions=%s",
                    data.get("customer_id"),
                    data.get("risk_level"),
                    actions_str,
                )
                consumer.commit()
            except Exception:
                logger.exception("Could not process notification event")
                raise
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
