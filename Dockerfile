FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY server /app/server

EXPOSE 8443

CMD [ "uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8443", "--ssl-keyfile", "server/certs/server.key", "--ssl-certfile", "server/certs/server.crt"]
