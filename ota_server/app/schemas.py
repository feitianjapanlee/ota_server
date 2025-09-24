from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator
from packaging.version import Version


class CheckUpdateRequest(BaseModel):
    mac: str = Field(min_length=8, max_length=32)
    current_version: str = Field(min_length=1)
    labels: list[str] = Field(default_factory=list)
    meta: dict[str, Any] | None = None

    @field_validator("mac")
    @classmethod
    def normalize_mac(cls, value: str) -> str:
        clean = value.replace(":", "").replace("-", "").lower()
        if len(clean) != 12:
            raise ValueError("MAC address must be 12 hexadecimal characters")
        return clean


class Manifest(BaseModel):
    version: str
    url: HttpUrl
    sha256: str
    size_bytes: int
    release_notes: str | None = None
    post_install_delay: int = Field(default=0, ge=0)

    def version_object(self) -> Version:
        return Version(self.version)


class CheckUpdateResponse(BaseModel):
    update_available: bool
    manifest: Manifest | None = None
    poll_interval_minutes: int | None = None


class ReportStatusRequest(BaseModel):
    mac: str
    firmware_version: str
    status: str = Field(pattern="^(success|failed)$")
    error: str | None = None


class DeviceRead(BaseModel):
    mac: str
    current_version: str | None
    labels: list[str]
    last_seen: datetime
    ip: str | None = None


class FirmwareRead(BaseModel):
    version: str
    channel: str | None
    release_notes: str | None
    created_at: datetime


class RolloutRead(BaseModel):
    name: str
    firmware_version: str
    target_label: str | None
    stage: str
    status: str
    is_active: bool
    start_at: datetime | None
    end_at: datetime | None
