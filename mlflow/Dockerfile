FROM python:3.12-slim
RUN pip install --no-cache-dir mlflow==3.1.0 psycopg2-binary
EXPOSE 5000
ENV MLFLOW_BACKEND_URI=sqlite:///mlflow.db
ENV MLFLOW_ARTIFACT_ROOT=./mlruns
COPY entrypoint.py /entrypoint.py
CMD ["python", "/entrypoint.py"]
