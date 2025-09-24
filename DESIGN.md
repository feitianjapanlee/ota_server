# OTA Design Overview

## Scope
Target: ESP32 fleet running Arduino-based app with OTA add-on. Server: Python FastAPI, runs locally for now, packaged later for containers. HTTPS via self-signed cert. Firmware limits: single binary ≤ 3.9 MB, semantic versioning.

## Architecture
- **ESP32 Client**: Periodically calls `/api/v1/check-update` with MAC, current version, device label hints. Validates `manifest.json` (sha256, size) before staged flash using Arduino OTA APIs; retains previous image for rollback.
- **OTA Server**: FastAPI + Uvicorn + SQLite (SQLAlchemy). Modules: `api`, `scheduler`, `db`, `rollout`, `certs`, `storage`. Firmware stored under `firmware/<version>/<file>` with manifest.
- **Scheduler**: APScheduler cron jobs from `config/schedules.yaml` trigger rollouts by label windows.
- **Rollout Engine**: Manages pilot cohorts (label-based). Tracks rollout states (`draft → pilot → expand → complete`) and monitors device adoption.

## Data Model
- `devices`: id, mac, ip, current_version, last_seen, labels JSON, status.
- `labels`: id, name, description; with `device_labels` join table.
- `firmware`: id, version, channel, file_path, size, sha256, release_notes, created_at, pilot_ready.
- `rollouts`: id, firmware_id, stage (`pilot`, `general`), target_label_id, schedule_id, status, start_at, end_at.
- `download_log`: device_id, firmware_id, status (`downloading`, `success`, `failed`), timestamp, error.
- `schedules`: id, cron_expr, rollout_id, enabled.

## API Surface
- `POST /api/v1/check-update`: client sends `{mac, current_version, labels[]}`; server returns `manifest` or `update_available: false`.
- `GET /firmware/{version}/image.bin`: pre-shared token via header; enforces size limit.
- `POST /api/v1/report-status`: optional telemetry for success/fail.
- Admin CLI manages firmware, labels, rollouts, and schedules; scripts backed by Typer.

## Client OTA Flow
1. Boot → connect Wi-Fi → load stored MAC/version.
2. Periodic timer (default 10 min ± jitter).
3. HTTPS query with server certificate pinning.
4. If update: compare SemVer, check label rules, verify size ≤ 3.9 MB.
5. Stream download via `Update` API, verifying sha256 incrementally.
6. Apply during idle window; on success reboot and report, else rollback to previous partition and report failure.

## Rollout Strategy
- Firmware upload flagged `pilot_ready` before exposure.
- Rollout targets label (e.g., `pilot`); scheduler activates at cron time.
- Monitor download logs, then promote rollout by switching target label to `general`.
- Rollback: mark firmware `blocked`, halt manifest responses, offer prior stable build.

## Security
- HTTPS with self-signed cert script; clients pin fingerprint.
- API tokens in `config/server.yml`.
- SHA256 manifest verification.
- Upload CLI enforces size & SemVer uniqueness.
- Optional basic auth for admin endpoints (future).

## Configuration Files
- `config/server.yml`: ports, cert paths, API token, default poll interval.
- `config/schedules.yaml`: cron definitions.
- `.env`: DB path, storage root (future use).

## Testing Strategy
1. Local server setup: venv, install deps, generate cert, run `uvicorn`.
2. Seed firmware via CLI, assign labels.
3. Create pilot rollout, configure cron, trigger manually.
4. Use `tools/fake_device.py` for simulated checks.
5. Hardware validation on ESP32, verify rollback by forcing failure.
6. Run `pytest` suite for API paths.
7. Security smoke tests: invalid token, bad cert.

## Deliverables
- FastAPI project with modules & CLI.
- Arduino OTA sketch and simulator utilities.
- Cert generation script, configs, documentation.
- Pytest coverage and setup guide.
