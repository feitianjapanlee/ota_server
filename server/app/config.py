from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8443)
    api_token: str
    cert_file: str
    key_file: str
    storage_root: str = Field(default="firmware_store")
    manifest_ttl_seconds: int = Field(default=300)
    poll_interval_minutes: int = Field(default=10)
    max_firmware_size_kb: int = Field(default=3900)


class SchedulerConfig(BaseModel):
    timezone: str = Field(default="UTC")
    schedules_file: str = Field(default="config/schedules.yaml")


class DatabaseConfig(BaseModel):
    url: str = Field(default="sqlite:///./ota.db")


class LoggingConfig(BaseModel):
    level: str = Field(default="INFO")


class AppConfig(BaseModel):
    server: ServerConfig
    scheduler: SchedulerConfig
    database: DatabaseConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @property
    def storage_path(self) -> Path:
        return Path(self.server.storage_root).resolve()

    @property
    def cert_path(self) -> Path:
        return Path(self.server.cert_file).resolve()

    @property
    def key_path(self) -> Path:
        return Path(self.server.key_file).resolve()


def _default_config_path() -> Path:
    env_path = os.getenv("OTA_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "config" / "server.yml"


def _config_base_dir(config_path: Path) -> Path:
    parent = config_path.parent
    if parent.name == "config":
        return parent.parent.resolve()
    return parent.resolve()


def _resolve_path(value: str, *, base_dir: Path) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((base_dir / path).resolve())


def _resolve_sqlite_url(url: str, *, base_dir: Path) -> str:
    prefix = "sqlite:///"
    if not url.startswith(prefix) or url.startswith("sqlite:////"):
        return url

    path_part, separator, suffix = url[len(prefix):].partition("?")
    if not path_part or path_part == ":memory:":
        return url

    resolved_path = Path(path_part).expanduser()
    if not resolved_path.is_absolute():
        resolved_path = (base_dir / resolved_path).resolve()
    else:
        resolved_path = resolved_path.resolve()

    normalized = f"{prefix}{resolved_path}"
    if separator:
        normalized = f"{normalized}?{suffix}"
    return normalized


def _normalize_paths(config: AppConfig, *, config_path: Path) -> AppConfig:
    base_dir = _config_base_dir(config_path)
    config.server.cert_file = _resolve_path(config.server.cert_file, base_dir=base_dir)
    config.server.key_file = _resolve_path(config.server.key_file, base_dir=base_dir)
    config.server.storage_root = _resolve_path(config.server.storage_root, base_dir=base_dir)
    config.scheduler.schedules_file = _resolve_path(config.scheduler.schedules_file, base_dir=base_dir)
    config.database.url = _resolve_sqlite_url(config.database.url, base_dir=base_dir)
    return config


def load_config(path: Optional[Path] = None) -> AppConfig:
    config_path = path or _default_config_path()
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    config = AppConfig.model_validate(raw)
    return _normalize_paths(config, config_path=config_path)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
