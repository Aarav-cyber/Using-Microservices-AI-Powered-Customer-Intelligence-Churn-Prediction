
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:29092",
)
KAFKA_SECURITY_PROTOCOL = os.getenv(
    "KAFKA_SECURITY_PROTOCOL",
    "PLAINTEXT",
)
KAFKA_SASL_MECHANISM = os.getenv(
    "KAFKA_SASL_MECHANISM",
    "SCRAM-SHA-256",
)
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME")
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD")
KAFKA_SSL_CA_LOCATION = os.getenv("KAFKA_SSL_CA_LOCATION")
KAFKA_CA_CERT = os.getenv("KAFKA_CA_CERT") or os.getenv("KAFKA_SSL_CA_CERT")

TOPIC = "feedback.submitted"
_producer = None


def get_ca_file_path():
    if KAFKA_SSL_CA_LOCATION and os.path.exists(KAFKA_SSL_CA_LOCATION):
        return KAFKA_SSL_CA_LOCATION

    ca_cert = KAFKA_CA_CERT or os.getenv("KAFKA_CA_CERT") or os.getenv("KAFKA_SSL_CA_CERT")
    if ca_cert:
        normalized = ca_cert.strip().strip("'\"").replace("\\n", "\n")
        temp_dir = os.path.join(tempfile.gettempdir(), "kafka_certs")
        os.makedirs(temp_dir, exist_ok=True)
        cert_path = os.path.join(temp_dir, "ca.pem")
        with open(cert_path, "w", encoding="utf-8") as f:
            f.write(normalized)
        return cert_path

    if os.path.exists("ca.pem"):
        return "ca.pem"

    return None


def get_producer():
    global _producer

    if _producer is None:
        config = {
            "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
            "value_serializer": lambda value: json.dumps(value).encode("utf-8"),
            "acks": "all",
            "retries": 3,
            "max_block_ms": 10000,
            "request_timeout_ms": 10000,
        }

        if KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
            if not KAFKA_SASL_USERNAME or not KAFKA_SASL_PASSWORD:
                raise RuntimeError(
                    "Kafka SASL username and password must be configured."
                )

            config.update({
                "security_protocol": "SASL_SSL",
                "sasl_mechanism": KAFKA_SASL_MECHANISM,
                "sasl_plain_username": KAFKA_SASL_USERNAME,
                "sasl_plain_password": KAFKA_SASL_PASSWORD,
            })

            ca_file = get_ca_file_path()
            if ca_file:
                config["ssl_cafile"] = ca_file

        _producer = KafkaProducer(**config)

    return _producer


def publish_feedback(feedback):
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "feedback.submitted",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": {
            "feedback_id": str(feedback.id),
            "tenant_id": str(feedback.tenant_id),
            "customer_id": str(feedback.customer_id),
            "message": feedback.message,
            "channel": feedback.channel,
            "created_at": feedback.created_at.isoformat(),
        },
    }

    producer = get_producer()
    producer.send(TOPIC, value=event).get(timeout=15)
    return event
