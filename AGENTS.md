# Repository Guidelines

## Project Structure & Module Organization
Operate from the repo root. Core FastAPI services live in `server/app` (config, database, schema, and scheduler modules). Persistent assets land in `server/firmware_store`, TLS material in `server/certs`, and runtime settings under `server/config`. Management utilities (`manage.py`, `tools`, `scripts`) stay alongside the app so CLI tasks share the same environment. Hardware samples live in `firmware/`, while integration artefacts and downloads are separated in `downloads/` for traceability.

## Build, Test, and Development Commands
Create a virtualenv (`python -m venv .venv && source .venv/bin/activate`) before installing `pip install -r server/requirements.txt`. Initialise state with `python server/manage.py initdb`, then seed firmware via `python server/manage.py firmware-upload <path> --version <semver> --channel <label>`. Run the HTTPS service locally with `uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt` from `server/`. Docker workflows use `docker compose build` and `docker compose up -d` in the root.

## Coding Style & Naming Conventions
Write Python in PEP 8 style: four-space indents, `snake_case` for functions and variables, `PascalCase` for Pydantic models, and module-level constants in `UPPER_SNAKE_CASE`. Keep FastAPI routers and CRUD helpers thin; push shared logic into `server/app/storage.py` or `server/app/crud.py` to avoid duplication. Format docstrings in Google style when adding async endpoints, and prefer type hints for every public function.

## Testing Guidelines
All automated checks use `pytest`; run `python -m pytest server/tests` from the root. Place new suites in `server/tests/test_<feature>.py`, mirroring module names. When adding async paths, mark coroutines with `pytest.mark.asyncio`. Expand fixtures instead of hardcoding database file paths, and assert both HTTP status and persisted state (e.g., entries in `ota.db` or blobs under `firmware_store`). Aim to cover new endpoints and CLI flows before opening a PR.

## Commit & Pull Request Guidelines
Follow the existing Git history: short, imperative commit subjects (`Add rollout scheduler sync`) without trailing periods. Squash noisy WIP commits before handing off. Every PR should include a clear problem statement, summary of changes, verification notes (commands run, tests, manual steps), and references to issues or tickets. Attach screenshots or CLI output when touching device-facing payloads or UI tooling, and flag any migrations or configuration changes for reviewers.

## Security & Configuration Tips
Never commit real certificates or API tokens; use the `server/certs` placeholders and `.env` loading via `pydantic-settings`. Keep `server/config/server.yml` synced with the desired deployment, and run `python server/manage.py scheduler-sync` whenever `server/config/schedules.yaml` changes so runtime jobs stay consistent.
