def recommend_retention_action(
    churn_probability: float,
    plan_tier: str,
    support_tickets_90d: int,
    sentiment: str | None = None,
) -> dict:
    if not 0 <= churn_probability <= 1:
        raise ValueError("churn_probability must be between 0 and 1")

    if support_tickets_90d < 0:
        raise ValueError("support_tickets_90d cannot be negative")

    plan = plan_tier.strip().lower()

    valid_plans = {"free", "starter", "professional", "enterprise"}
    if plan not in valid_plans:
        raise ValueError(f"Unsupported plan_tier: {plan_tier}")

    if churn_probability >= 0.7:
        risk = "high"
    elif churn_probability >= 0.4:
        risk = "medium"
    else:
        risk = "low"

    actions = []

    if risk == "high":
        actions.append("Prioritize customer-success outreach.")

    if support_tickets_90d >= 3:
        actions.append(
            "Review recent support tickets and resolve recurring issues."
        )

    if sentiment and sentiment.strip().lower() == "negative":
        actions.append(
            "Review recent feedback and address the customer's concerns."
        )

    if plan == "free" and risk in {"high", "medium"}:
        actions.append(
            "Offer relevant product guidance and explain suitable plan options."
        )

    if plan in {"professional", "enterprise"} and risk in {"high", "medium"}:
        actions.append(
            "Arrange a personalized account review with customer success."
        )

    if not actions:
        actions.append(
            "Continue normal engagement and monitor customer activity."
        )

    return {
        "risk_level": risk,
        "churn_probability": round(churn_probability, 4),
        "recommended_actions": actions,
    }
