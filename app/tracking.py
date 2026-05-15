"""MLflow tracking for LLMOps - logs every query with metrics."""

import os
import time
import logging

_client = None
_experiment_id = None


def _get_client():
    global _client, _experiment_id
    if _client is None:
        try:
            import mlflow
            tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "https://cccp-mlflow.agreeablecliff-8b7135c2.northeurope.azurecontainerapps.io/")
            mlflow.set_tracking_uri(tracking_uri)
            _client = mlflow
            # Create or get experiment
            exp = mlflow.get_experiment_by_name("cccp-chatbot")
            if exp is None:
                _experiment_id = mlflow.create_experiment("cccp-chatbot")
            else:
                _experiment_id = exp.experiment_id
        except Exception as e:
            logging.warning(f"MLflow init failed: {e}")
            return None
    return _client


def log_query(query: str, routes: list, response_len: int, quality: dict,
              latency_ms: float, user_name: str = ""):
    """Log a chatbot query to MLflow."""
    mlflow = _get_client()
    if mlflow is None:
        return
    try:
        with mlflow.start_run(experiment_id=_experiment_id):
            # Parameters
            mlflow.log_param("query", query[:200])
            mlflow.log_param("routes", ",".join(routes))
            mlflow.log_param("user", user_name[:50])
            mlflow.log_param("num_agents", len(routes))

            # Metrics
            mlflow.log_metric("latency_ms", latency_ms)
            mlflow.log_metric("response_length", response_len)
            mlflow.log_metric("num_routes", len(routes))

            if quality:
                for key, val in quality.items():
                    if isinstance(val, (int, float)):
                        mlflow.log_metric(f"quality_{key}", val)

            # Tags
            mlflow.set_tag("primary_agent", routes[0] if routes else "unknown")
            mlflow.set_tag("multi_route", str(len(routes) > 1))
    except Exception as e:
        logging.warning(f"MLflow log failed: {e}")
