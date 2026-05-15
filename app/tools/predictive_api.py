"""Predictive API tool - calls existing ML microservices for propensity scores."""

import os
import logging
import requests


def get_propensity_scores(query: str) -> str:
    """Call predictive microservices for cross-sell/upsell propensity scores."""
    endpoint = os.environ.get("PREDICTIVE_API_ENDPOINT", "")
    api_key = os.environ.get("PREDICTIVE_API_KEY", "")

    if not endpoint:
        return _mock_predictions(query)

    try:
        response = requests.post(
            f"{endpoint}/predict",
            json={"query": query},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        if response.ok:
            return str(response.json())
    except Exception as e:
        logging.warning(f"Predictive API call failed: {e}")

    return _mock_predictions(query)


def _mock_predictions(query: str) -> str:
    """Mock predictions for PoC when microservices are not available."""
    return """
Propensity scores for customer context:
- Security Pack: 0.72 (HIGH) — customer has had 2 security-related inquiries
- Premium Support: 0.65 (MEDIUM) — frequent caller, values quick resolution
- Cloud Backup Pro: 0.58 (MEDIUM) — already has basic backup, natural upgrade
- Business Analytics: 0.34 (LOW) — no signals of interest
- Contract Renewal (2yr): 0.81 (HIGH) — loyalty signals, price-sensitive

Churn risk: 0.35 (MODERATE) — billing dispute unresolved >30 days
Recommended action: resolve billing issue BEFORE upsell attempt
"""
