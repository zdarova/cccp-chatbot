FROM ghcr.io/mlflow/mlflow:v3.1.0
RUN pip install --no-cache-dir psycopg2-binary
EXPOSE 5000
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
