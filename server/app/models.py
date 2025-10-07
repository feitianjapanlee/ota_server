from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class RolloutStage(str, enum.Enum):
    pilot = "pilot"
    general = "general"


class RolloutStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    active = "active"
    paused = "paused"
    completed = "completed"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    mac: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    labels: Mapped[list["DeviceLabel"]] = relationship("DeviceLabel", back_populates="device", cascade="all, delete-orphan")
    downloads: Mapped[list["DownloadLog"]] = relationship("DownloadLog", back_populates="device", cascade="all, delete-orphan")


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)

    devices: Mapped[list["DeviceLabel"]] = relationship("DeviceLabel", back_populates="label", cascade="all, delete-orphan")
    rollouts: Mapped[list["Rollout"]] = relationship("Rollout", back_populates="target_label")


class DeviceLabel(Base):
    __tablename__ = "device_labels"
    __table_args__ = (UniqueConstraint("device_id", "label_id", name="uq_device_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id", ondelete="CASCADE"))

    device: Mapped[Device] = relationship(Device, back_populates="labels")
    label: Mapped[Label] = relationship(Label, back_populates="devices")


class Firmware(Base):
    __tablename__ = "firmware"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str] = mapped_column(String(256), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    release_notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    pilot_ready: Mapped[bool] = mapped_column(Boolean, default=False)

    rollouts: Mapped[list["Rollout"]] = relationship("Rollout", back_populates="firmware")
    downloads: Mapped[list["DownloadLog"]] = relationship("DownloadLog", back_populates="firmware")


class Rollout(Base):
    __tablename__ = "rollouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    firmware_id: Mapped[int] = mapped_column(ForeignKey("firmware.id", ondelete="CASCADE"))
    target_label_id: Mapped[int | None] = mapped_column(ForeignKey("labels.id", ondelete="SET NULL"), nullable=True)
    stage: Mapped[RolloutStage] = mapped_column(Enum(RolloutStage), default=RolloutStage.general, nullable=False)
    status: Mapped[RolloutStatus] = mapped_column(Enum(RolloutStatus), default=RolloutStatus.draft, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    firmware: Mapped[Firmware] = relationship(Firmware, back_populates="rollouts")
    target_label: Mapped[Label | None] = relationship(Label, back_populates="rollouts")
    schedule: Mapped[Schedule | None] = relationship("Schedule", back_populates="rollout", uselist=False)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rollout_id: Mapped[int] = mapped_column(ForeignKey("rollouts.id", ondelete="CASCADE"), unique=True)

    rollout: Mapped[Rollout] = relationship(Rollout, back_populates="schedule")


class DownloadStatus(str, enum.Enum):
    downloading = "downloading"
    success = "success"
    failed = "failed"


class DownloadLog(Base):
    __tablename__ = "download_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    firmware_id: Mapped[int] = mapped_column(ForeignKey("firmware.id", ondelete="CASCADE"))
    status: Mapped[DownloadStatus] = mapped_column(Enum(DownloadStatus), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    device: Mapped[Device] = relationship(Device, back_populates="downloads")
    firmware: Mapped[Firmware] = relationship(Firmware, back_populates="downloads")
