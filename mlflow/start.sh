#!/bin/bash
exec mlflow server \
  --host 0.0.0.0 \
  --port 5000 \
  --backend-store-uri "${MLFLOW_BACKEND_URI:-sqlite:///mlflow.db}" \
  --default-artifact-root "${MLFLOW_ARTIFACT_ROOT:-./mlruns}" \
  --serve-artifacts \
  --allowed-hosts all \
  --cors-allowed-origins "*"
