from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from logging.config import dictConfig

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crud, models
from .config import get_config
from .database import get_session, init_db
from .manifest import build_manifest
from .scheduler import RolloutScheduler
from .schemas import CheckUpdateRequest, CheckUpdateResponse, ReportStatusRequest
from .security import get_poll_interval_minutes, verify_api_token
from .storage import ensure_storage_root

logger = logging.getLogger(__name__)

app = FastAPI(title="ESP32 OTA Server", version="1.0")
_config = get_config()


def _resolve_log_level(level: str) -> int:
    mapping = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }
    return mapping.get(level.upper(), logging.INFO)


def _configure_logging(level: str) -> None:
    resolved_level = _resolve_log_level(level)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "uvicorn": {
                    "handlers": ["console"],
                    "level": resolved_level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": resolved_level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": logging.INFO,
                    "propagate": False,
                },
            },
            "root": {
                "handlers": ["console"],
                "level": resolved_level,
            },
        }
    )


_configure_logging(_config.logging.level)
_scheduler = RolloutScheduler()


@app.on_event("startup")
async def on_startup() -> None:
    ensure_storage_root()
    init_db()
    _scheduler.start()
    logger.info("OTA server started on %s:%s", _config.server.host, _config.server.port)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    _scheduler.shutdown()


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


TokenDependency = Annotated[str, Depends(verify_api_token)]
SessionDependency = Annotated[Session, Depends(get_session)]


@app.post("/api/v1/check-update", response_model=CheckUpdateResponse)
def check_update(
    payload: CheckUpdateRequest,
    request: Request,
    _: TokenDependency,
    session: SessionDependency,
) -> CheckUpdateResponse:
    device_ip = request.client.host if request.client else None
    device = crud.register_or_update_device(
        session,
        mac=payload.mac,
        ip=device_ip,
        current_version=payload.current_version,
        label_names=payload.labels,
        meta=payload.meta,
    )
    firmware, rollout = crud.choose_manifest_for_device(session, device=device)
    poll_interval = get_poll_interval_minutes()

    if not firmware:
        session.commit()
        logger.debug("No update available for device %s", payload.mac)
        return CheckUpdateResponse(update_available=False, manifest=None, poll_interval_minutes=poll_interval)

    logger.debug(
        "Preparing manifest for device %s with firmware %s (rollout=%s)",
        payload.mac,
        firmware.version,
        rollout.name if rollout else "n/a",
    )
    manifest = build_manifest(request, firmware)
    crud.record_download(session, device=device, firmware=firmware, status=models.DownloadStatus.downloading)
    logger.info("Offering firmware %s to device %s (rollout=%s)", firmware.version, payload.mac, rollout.name if rollout else "n/a")
    session.commit()
    return CheckUpdateResponse(update_available=True, manifest=manifest, poll_interval_minutes=poll_interval)


@app.get("/firmware/{version}/image.bin", response_model=None)
def download_firmware(
    version: str,
    _: TokenDependency,
    session: SessionDependency,
) -> Response:
    firmware = session.execute(
        select(models.Firmware).where(models.Firmware.version == version)
    ).scalar_one_or_none()
    if not firmware:
        logger.debug("Firmware version %s requested but not found in database", version)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware not found")
    file_path = Path(firmware.file_path).resolve()
    if not file_path.exists():
        logger.debug("Firmware file missing on disk for version %s at %s", version, file_path)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware file missing")
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@app.post("/api/v1/report-status")
def report_status(
    payload: ReportStatusRequest,
    _: TokenDependency,
    session: SessionDependency,
) -> dict[str, str]:
    device = session.execute(
        select(models.Device).where(models.Device.mac == payload.mac)
    ).scalar_one_or_none()
    if not device:
        logger.debug("Device %s attempted to report status but is not registered", payload.mac)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not registered")
    firmware = crud.get_firmware_by_version(session, payload.firmware_version)
    if not firmware:
        logger.debug(
            "Device %s reported status for unknown firmware %s",
            payload.mac,
            payload.firmware_version,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firmware not tracked")

    status_value = models.DownloadStatus.success if payload.status == "success" else models.DownloadStatus.failed
    if status_value == models.DownloadStatus.failed and payload.error:
        logger.debug(
            "Device %s reported failure for firmware %s (error=%s)",
            payload.mac,
            payload.firmware_version,
            payload.error,
        )
    crud.record_download(session, device=device, firmware=firmware, status=status_value, error=payload.error)

    if status_value == models.DownloadStatus.success:
        device.current_version = payload.firmware_version
        logger.debug("Updated device %s current version to %s", payload.mac, payload.firmware_version)
    device.last_seen = datetime.utcnow()
    session.commit()
    logger.info("Device %s reported %s for firmware %s", payload.mac, payload.status, payload.firmware_version)
    return {"status": "ok"}
