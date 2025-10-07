from __future__ import annotations

from fastapi import Request

from .schemas import Manifest
from . import models


def build_manifest(request: Request, firmware: models.Firmware) -> Manifest:
    download_url = str(request.url_for("download_firmware", version=firmware.version))
    return Manifest(
        version=firmware.version,
        url=download_url,
        sha256=firmware.sha256,
        size_bytes=firmware.size_bytes,
        release_notes=firmware.release_notes,
        post_install_delay=0,
    )
