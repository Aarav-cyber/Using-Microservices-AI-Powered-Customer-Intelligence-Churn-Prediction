import json
import os

from kafka import KafkaConsumer, KafkaProducer

DLQ_TOPIC = "sentiment.orchestration.dlq"
INPUT_TOPIC = "sentiment.completed"

KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256")
SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME")
SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD")
SSL_CA_LOCATION = os.getenv("KAFKA_SSL_CA_LOCATION")

kafka_config = {
    "bootstrap_servers": KAFKA_SERVERS,
    "security_protocol": SECURITY_PROTOCOL,
    "api_version": (2, 5, 0),
}

if SECURITY_PROTOCOL == "SASL_SSL":
    kafka_config.update({
        "sasl_mechanism": SASL_MECHANISM,
        "sasl_plain_username": SASL_USERNAME,
        "sasl_plain_password": SASL_PASSWORD,
        "ssl_cafile": SSL_CA_LOCATION,
    })


def main():
    event_id = input("Enter failed event ID to replay: ").strip()

    consumer = KafkaConsumer(
        DLQ_TOPIC,
        **kafka_config,
        group_id=None,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=10000,
        value_deserializer=lambda value: json.loads(value.decode()),
    )

    producer = KafkaProducer(
        **kafka_config,
        value_serializer=lambda value: json.dumps(value).encode(),
        acks="all",
        retries=3,
    )

    try:
        print(f"Searching DLQ for event {event_id}...")

        for record in consumer:
            dead_letter = record.value
            original_event = dead_letter.get("original_event", {})

            if original_event.get("event_id") == event_id:
                producer.send(
                    INPUT_TOPIC,
                    value=original_event,
                ).get(timeout=15)

                print(f"Successfully replayed event {event_id}")
                return

        print("Event not found in DLQ.")

    finally:
        consumer.close()
        producer.close()


if __name__ == "__main__":
    main()
