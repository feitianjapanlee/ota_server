FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY ota_server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY ota_server /app/ota_server

EXPOSE 8443

CMD [
    "uvicorn",
    "ota_server.app.main:app",
    "--host", "0.0.0.0",
    "--port", "8443",
    "--ssl-keyfile", "ota_server/certs/server.key",
    "--ssl-certfile", "ota_server/certs/server.crt"
]
