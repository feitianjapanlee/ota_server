#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="${1:-certs}"
mkdir -p "$CERT_DIR"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

if command -v openssl >/dev/null 2>&1; then
  openssl req -x509 -nodes -days 365 \
    -newkey rsa:4096 \
    -subj "/C=JP/ST=Tokyo/L=Shinjuku/O=Keihin/OU=OTA/CN=localhost" \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE"
  echo "Generated certificate: $CERT_FILE"
  echo "Generated key        : $KEY_FILE"
else
  echo "openssl not found. Please install OpenSSL to generate certificates." >&2
  exit 1
fi
