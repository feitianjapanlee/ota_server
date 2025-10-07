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


def load_config(path: Optional[Path] = None) -> AppConfig:
    config_path = path or _default_config_path()
    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return AppConfig.model_validate(raw)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
