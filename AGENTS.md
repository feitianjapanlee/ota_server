# Repository Guidelines

## Project Structure & Module Organization
Core runtime for the MaixCam device sits in `main.py`, which starts the Flask status API and the Maix YOLOv8 pipeline. Use `main-usb.py` when streaming frames over USB for lab debugging. Supporting assets are grouped by purpose: model binaries in `models/`, packaged firmware builds in `dist/`, and web overlays in `static/`. Training notebooks, scripts, and augmentation utilities live in `train/`; keep experimental notebooks there and store raw captures under `datasets/`. Utility scripts for polygon masks and sample sprites are in `utils/`, and deployment manifests live alongside the app (`app.yaml`, `bytetrack.yaml`).

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: create an isolated environment before installing dependencies.
- `pip install -r requirements.txt`: install runtime and training libraries; the file is UTF-16 encoded, so convert to UTF-8 if your shell cannot parse it.
- `python main.py`: run the MaixCam-integrated app on-device (requires MaixPy runtime and camera access).
- `python train/augmentate.py`: generate augmented samples before retraining.
- `docker run --gpus all ... nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 bash`: start the documented containerized training workspace.
- `sh train/convert_yolo_onnx2cvimodel.sh`: convert ONNX exports into `.mud` firmware for deployment.

## Coding Style & Naming Conventions
Write Python with 4-space indentation and follow PEP 8 unless hardware SDK constraints require otherwise. Keep module-level constants uppercase and snake_case for variables and functions, mirroring existing code. Retain bilingual comments where they clarify Maix-specific behavior. Place configuration in YAML or JSON files at the repository root and reference them by absolute paths (`/root/...`) as done in `main.py`.

## Testing Guidelines
There is no automated test harness; rely on repeatable hardware checks. Validate inference on the MaixCam by observing the `/static` web preview and verifying count resets between sessions. For training changes, capture a before/after mAP or precision metric in the CUDA container and attach screenshots or logs to the PR. When adding scripts, include a small CLI smoke test (e.g., `python train/p2y-convertor.py --help`) and document manual steps.

## Commit & Pull Request Guidelines
Existing history favors short, present-tense summaries (`count_ids discard`, `train64`). Follow that pattern, and group unrelated work into separate commits. Each PR should describe the scenario being addressed, list manual test evidence (device capture, metric table), and mention affected artifacts (`models/`, `dist/`) explicitly. Link issue IDs when available and add deployment notes if firmware bundles in `dist/` changed.

## Model & Data Handling
Keep large datasets out of the repo; store derived archives under `datasets/` and ship only curated subsets. When updating `.mud` or `.zip` artifacts, bump version suffixes consistently (`v0.1.xx`) and update consuming scripts to the new filename. Scrub personal data from captures before committing and document any new secrets or API keys in `app.yaml` comments rather than storing credentials in code.
