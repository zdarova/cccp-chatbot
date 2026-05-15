"""Start MLflow tracking server."""
import os
import subprocess
import sys

backend_uri = os.environ.get("MLFLOW_BACKEND_URI", "sqlite:///mlflow.db")
artifact_root = os.environ.get("MLFLOW_ARTIFACT_ROOT", "./mlruns")

cmd = [
    sys.executable, "-m", "mlflow", "server",
    "--host", "0.0.0.0",
    "--port", "5000",
    "--backend-store-uri", backend_uri,
    "--default-artifact-root", artifact_root,
]

print(f"Starting MLflow server with backend: {backend_uri}")
sys.stdout.flush()
os.execvp(cmd[0], cmd)
