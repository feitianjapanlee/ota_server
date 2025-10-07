# ESP32 OTA Server Toolkit

This directory contains the Python OTA backend, management utilities, simulator scripts, and test assets required to manage large ESP32 fleets.

## Quick Start

1. **Install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r ota_server/requirements.txt
   ```
2. **Generate a self-signed certificate**
   ```bash
   cd server
   ./scripts/generate_cert.sh certs
   ```
   The generated certificate includes subject alternative names for `localhost` and `127.0.0.1` so simulators and browsers accept it without hostname warnings.
3. **Initialise the database**
   ```bash
   python manage.py initdb
   ```
4. **Upload a firmware build**
   ```bash
   python manage.py firmware-upload firmware/app.bin --version 1.0.0 --channel pilot --notes "Pilot build" --pilot-ready
   ```
5. **Create a pilot rollout**
   ```bash
   python manage.py rollout-create pilot-rollout --firmware 1.0.0 --label pilot --stage pilot --activate
   ```
6. **Run the server with HTTPS**
   ```bash
   cd server
   uvicorn app.main:app --host 0.0.0.0 --port 8443 \
       --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt
   ```

## Docker Deployment

Container builds ship only the application code; the SQLite database, firmware binaries, and certificates stay on the host via bind mounts.

1. **Generate host certificates (if absent)**
   ```bash
   ./server/scripts/generate_cert.sh server/certs
   ```
2. **Build the image**
   ```bash
   docker compose build
   ```
3. **Initialise the database (idempotent)**
   ```bash
   docker compose run --rm ota-server python server/manage.py initdb
   ```
4. **Start the HTTPS server**
   ```bash
   docker compose up -d
   ```

The compose file maps `server/ota.db`, `server/firmware_store`, `server/certs`, and `server/config` into the container so that uploads, rollouts, and configuration changes persist on the host. Use `docker compose run --rm ota-server python server/manage.py <command>` for other management tasks.

## Configuration

Runtime settings live in `server/config/server.yml`. Update the API token, certificate paths, storage directory, and database URL before running in production. Cron-based rollouts are defined in `server/config/schedules.yaml`; sync them into the database with `python manage.py scheduler-sync`.

## Device Simulator

Use the fake device to verify the OTA workflow without hardware:
```bash
python server/tools/fake_device.py --base-url https://localhost:8443 \
    --mac aa:bb:cc:dd:ee:ff --version 0.9.0 --labels pilot \
    --token <API_TOKEN> --cert server/certs/server.crt
```

## Tests

Run the automated test suite from the repository root (with the virtual environment active):
```bash
python -m pytest server/tests
```

The tests exercise the check-update and report-status endpoints, verifying that firmware manifests and download logs are persisted correctly.

## ESP32 Firmware

The Arduino sketch in `firmware/esp32_ota_client.ino` implements the polling, download, verification, and rollback logic for ESP32 devices. Replace the Wi-Fi credentials, OTA token, and embedded certificate, then flash it with the Arduino IDE or `arduino-cli`.

## Next Steps

- Integrate with your continuous delivery pipeline to push signed binaries into `server/firmware_store`.
- Extend the CLI to gate general rollouts on pilot feedback or telemetry thresholds.
- Harden the Docker image for production (multi-stage build, non-root user, monitored health checks).
