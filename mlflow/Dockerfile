FROM python:3.12-slim
RUN pip install --no-cache-dir mlflow==3.12.0 psycopg2-binary
EXPOSE 5000
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
