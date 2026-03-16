from __future__ import annotations

from fastapi import Request

from .schemas import Manifest
from . import models


def _forwarded_value(header_value: str | None) -> str | None:
    if not header_value:
        return None
    return header_value.split(",", 1)[0].strip()


def _forwarded_attr(request: Request, attr: str) -> str | None:
    forwarded = _forwarded_value(request.headers.get("forwarded"))
    if not forwarded:
        return None
    for part in forwarded.split(";"):
        key, _, value = part.partition("=")
        if key.strip().lower() == attr:
            return value.strip().strip('"')
    return None


def _external_scheme(request: Request) -> str:
    return (
        _forwarded_attr(request, "proto")
        or _forwarded_value(request.headers.get("x-forwarded-proto"))
        or request.url.scheme
    )


def _external_host(request: Request) -> str:
    return (
        _forwarded_attr(request, "host")
        or _forwarded_value(request.headers.get("x-forwarded-host"))
        or request.headers.get("host")
        or request.url.netloc
    )


def build_manifest(request: Request, firmware: models.Firmware) -> Manifest:
    download_path = request.app.url_path_for("download_firmware", version=firmware.version)
    download_url = f"{_external_scheme(request)}://{_external_host(request)}{download_path}"
    return Manifest(
        version=firmware.version,
        url=download_url,
        sha256=firmware.sha256,
        size_bytes=firmware.size_bytes,
        release_notes=firmware.release_notes,
        post_install_delay=0,
    )
