import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from kafka import KafkaConsumer, KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

KAFKA_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"
)
INPUT_TOPIC = "sentiment.completed"
DLQ_TOPIC = "sentiment.orchestration.dlq"
GROUP_ID = "customer-intelligence-orchestrator"

CUSTOMER_PROFILE_URL = os.getenv(
    "CUSTOMER_PROFILE_URL", "http://customer-profile:8001"
).rstrip("/")
CHURN_URL = os.getenv(
    "CHURN_PREDICTION_URL", "http://churn-prediction:8004"
).rstrip("/")
RETENTION_URL = os.getenv(
    "RETENTION_URL", "http://retention:8005"
).rstrip("/")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")

VALID_PLANS = {"free", "starter", "professional", "enterprise"}


class PermanentEventError(Exception):
    """The event cannot be processed without changing its data."""


class DependencyError(Exception):
    """A downstream service or network request failed."""


def create_service_token(tenant_id: str) -> str:
    """Generate an internal service Bearer token for inter-service calls."""
    payload = {
        "sub": "orchestrator",
        "tenant_id": str(tenant_id),
        "role": "internal_service",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def request_json(
    url: str,
    payload: dict | None = None,
    token: str | None = None,
) -> dict:
    """Make a JSON HTTP request and classify permanent vs transient errors."""
    body = None
    headers = {"Accept": "application/json"}

    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=body, headers=headers)

    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict):
                raise DependencyError(
                    f"Expected a JSON object from {url}"
                )
            return result

    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if 400 <= exc.code < 500 and exc.code not in {408, 429}:
            raise PermanentEventError(
                f"HTTP {exc.code} from {url}: {detail}"
            ) from exc
        raise DependencyError(
            f"HTTP {exc.code} from {url}: {detail}"
        ) from exc

    except (URLError, TimeoutError, OSError) as exc:
        raise DependencyError(
            f"Request to {url} failed: {exc}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise DependencyError(
            f"Invalid JSON response from {url}"
        ) from exc


def build_churn_features(profile: dict) -> dict:
    """Map the customer profile to the exact SaaS model features."""
    try:
        tenure_months = int(profile["tenure_months"])
        monthly_spend = float(profile["monthly_spend"])
        support_tickets = int(profile["support_tickets_90d"])
        raw_plan = profile.get("subscription_plan")
    except (KeyError, TypeError, ValueError) as exc:
        raise PermanentEventError(
            f"Customer profile has invalid required fields: {exc}"
        ) from exc

    if tenure_months < 0 or support_tickets < 0 or monthly_spend < 0:
        raise PermanentEventError(
            "Customer profile contains negative numeric values."
        )

    if not raw_plan or not str(raw_plan).strip():
        raise PermanentEventError(
            "Customer has no subscription_plan; cannot predict churn."
        )

    plan = str(raw_plan).strip().lower()
    if plan not in VALID_PLANS:
        raise PermanentEventError(
            f"Unsupported subscription_plan {raw_plan!r}. "
            f"Expected one of {sorted(VALID_PLANS)}."
        )

    raw_last_active = profile.get("last_active_at")
    if not raw_last_active:
        raise PermanentEventError(
            "Customer has no last_active_at; cannot calculate "
            "days_since_last_login reliably."
        )

    try:
        last_active = datetime.fromisoformat(
            str(raw_last_active).replace("Z", "+00:00")
        )
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)

        elapsed = datetime.now(timezone.utc) - last_active.astimezone(
            timezone.utc
        )
        # A future timestamp should not create negative model input.
        days_since_last_login = max(0, elapsed.days)

    except (ValueError, TypeError) as exc:
        raise PermanentEventError(
            f"Invalid last_active_at value: {raw_last_active!r}"
        ) from exc

    return {
        "account_age_days": tenure_months * 30,
        "monthly_price_usd": monthly_spend,
        "support_tickets_90d": support_tickets,
        "days_since_last_login": days_since_last_login,
        "plan_tier": plan,
    }


def publish_to_dlq(producer, event: dict, reason: str) -> None:
    """Persist an unprocessable event to the dead-letter topic."""
    dead_letter = {
        "event_type": "orchestration.failed",
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "original_event": event,
    }

    producer.send(DLQ_TOPIC, value=dead_letter).get(timeout=15)
    logger.error(
        "Sent event %s to %s: %s",
        event.get("event_id"),
        DLQ_TOPIC,
        reason,
    )


def process_event(event: dict) -> None:
    data = event.get("data")
    if not isinstance(data, dict):
        raise PermanentEventError("Event is missing its data object.")

    try:
        tenant_id = str(data["tenant_id"])
        customer_id = str(data["customer_id"])
        feedback_id = str(data["feedback_id"])
    except KeyError as exc:
        raise PermanentEventError(
            f"Event is missing required identity field {exc}."
        ) from exc

    sentiment = data.get("sentiment")
    if not sentiment or not str(sentiment).strip():
        raise PermanentEventError(
            "Sentiment result is missing from the event."
        )

    # Fetch customer using authenticated internal service token
    token = create_service_token(tenant_id)
    profile = request_json(
        f"{CUSTOMER_PROFILE_URL}/api/v1/customers/{customer_id}",
        token=token,
    )

    # Convert profile data to the churn model's feature contract.
    churn_features = build_churn_features(profile)

    prediction = request_json(
        f"{CHURN_URL}/api/v1/predict",
        churn_features,
    )

    probability = prediction.get("churn_probability")
    if probability is None:
        raise DependencyError(
            "Churn API response has no churn_probability."
        )

    retention_payload = {
        "customer_id": customer_id,
        "tenant_id": tenant_id,
        "churn_probability": probability,
        "plan_tier": churn_features["plan_tier"],
        "support_tickets_90d": churn_features["support_tickets_90d"],
        "sentiment": str(sentiment).strip().lower(),
    }

    recommendation = request_json(
        f"{RETENTION_URL}/api/v1/recommendations",
        retention_payload,
    )

    logger.info(
        "Completed pipeline: feedback=%s tenant=%s customer=%s "
        "churn_probability=%.4f risk=%s",
        feedback_id,
        tenant_id,
        customer_id,
        float(probability),
        recommendation.get("data", {}).get("risk_level", "unknown"),
    )


def main() -> None:
    consumer = None
    producer = None

    for attempt in range(1, 11):
        try:
            logger.info(
                "Connecting to Kafka at %s (attempt %d/10)",
                KAFKA_SERVERS,
                attempt,
            )

            consumer = KafkaConsumer(
                INPUT_TOPIC,
                bootstrap_servers=KAFKA_SERVERS,
                group_id=GROUP_ID,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                value_deserializer=lambda value: json.loads(
                    value.decode("utf-8")
                ),
            )

            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVERS,
                value_serializer=lambda value: json.dumps(
                    value
                ).encode("utf-8"),
                acks="all",
                retries=3,
            )
            break

        except Exception:
            logger.exception("Kafka connection failed")
            if consumer is not None:
                consumer.close()
                consumer = None
            if producer is not None:
                producer.close()
                producer = None
            time.sleep(3)

    if consumer is None or producer is None:
        logger.error("Could not connect to Kafka; exiting.")
        return

    logger.info("Listening to %s", INPUT_TOPIC)

    try:
        for record in consumer:
            event = record.value

            while True:
                try:
                    process_event(event)
                    consumer.commit()
                    break

                except PermanentEventError as exc:
                    # Do not block the partition forever on invalid data.
                    # Commit only after the DLQ publish succeeds.
                    try:
                        publish_to_dlq(producer, event, str(exc))
                        consumer.commit()
                    except Exception:
                        logger.exception(
                            "Could not publish to DLQ; will retry event."
                        )
                        time.sleep(3)
                        continue
                    break

                except Exception as exc:
                    # Keep the current record uncommitted and retry it.
                    # This prevents later offsets from skipping this event.
                    logger.warning(
                        "Transient processing failure for event %s: %s. "
                        "Retrying in 5 seconds.",
                        event.get("event_id"),
                        exc,
                    )
                    time.sleep(5)

    finally:
        consumer.close()
        producer.close()


if __name__ == "__main__":
    main()
