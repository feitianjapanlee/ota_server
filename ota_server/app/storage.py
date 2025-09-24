from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .config import get_config


def ensure_storage_root() -> Path:
    storage_root = get_config().storage_path
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def store_firmware_file(source: Path, version: str) -> tuple[Path, int, str]:
    config = get_config()
    storage_root = ensure_storage_root()
    target_dir = storage_root / version
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / source.name
    shutil.copy2(source, target_file)
    size_bytes = target_file.stat().st_size
    max_bytes = config.server.max_firmware_size_kb * 1024
    if size_bytes > max_bytes:
        target_file.unlink(missing_ok=True)
        raise ValueError(
            f"Firmware file exceeds limit ({size_bytes} bytes > {max_bytes} bytes)"
        )
    sha256 = compute_sha256(target_file)
    return target_file, size_bytes, sha256
