def recommend_retention_action(
    churn_probability: float,
    contract: str,
    tech_support: str,
    sentiment: str | None = None,
) -> dict:
    if not 0 <= churn_probability <= 1:
        raise ValueError("churn_probability must be between 0 and 1")

    if churn_probability >= 0.75:
        risk = "high"
    elif churn_probability >= 0.45:
        risk = "medium"
    else:
        risk = "low"

    actions = []

    if risk == "high":
        actions.append("Prioritize a customer-success outreach.")

    if contract.lower() == "month-to-month":
        actions.append("Offer suitable longer-term plans for review.")

    if tech_support.lower() == "no":
        actions.append("Offer a technical-support walkthrough.")

    if sentiment == "negative":
        actions.append("Review recent feedback and address the complaint.")

    if not actions:
        actions.append("Continue normal engagement and monitor customer activity.")

    return {
        "risk_level": risk,
        "churn_probability": round(churn_probability, 4),
        "recommended_actions": actions,
    }
