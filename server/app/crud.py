from __future__ import annotations

from datetime import datetime
from typing import Iterable

from packaging.version import Version
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from . import models


def _ensure_labels(session: Session, label_names: Iterable[str]) -> list[models.Label]:
    labels: list[models.Label] = []
    normalized = {name.strip() for name in label_names if name and name.strip()}
    if not normalized:
        return []
    existing = {
        label.name: label
        for label in session.execute(
            select(models.Label).where(models.Label.name.in_(normalized))
        ).scalars()
    }
    for name in normalized:
        label = existing.get(name)
        if not label:
            label = models.Label(name=name)
            session.add(label)
            session.flush()
        labels.append(label)
    return labels


def register_or_update_device(
    session: Session,
    *,
    mac: str,
    ip: str | None,
    current_version: str,
    label_names: Iterable[str],
    meta: dict | None = None,
) -> models.Device:
    labels = _ensure_labels(session, label_names)
    device = session.execute(
        select(models.Device).where(models.Device.mac == mac)
    ).scalar_one_or_none()

    if not device:
        device = models.Device(mac=mac)
        session.add(device)
        session.flush()

    device.ip = ip
    device.current_version = current_version
    device.last_seen = datetime.utcnow()
    device.meta = meta or {}

    # update labels
    existing_label_ids = {dl.label_id for dl in device.labels}
    for label in labels:
        if label.id not in existing_label_ids:
            device.labels.append(models.DeviceLabel(device=device, label=label))
    # remove labels not in provided list only if we have explicit set
    if labels:
        session.flush()
        desired_ids = {label.id for label in labels}
        device.labels[:] = [
            dl for dl in device.labels if dl.label_id in desired_ids
        ]

    return device


def list_device_labels(device: models.Device) -> set[str]:
    return {dl.label.name for dl in device.labels}


def get_firmware_by_version(session: Session, version: str) -> models.Firmware | None:
    return session.execute(
        select(models.Firmware).where(models.Firmware.version == version)
    ).scalar_one_or_none()


def create_firmware(
    session: Session,
    *,
    version: str,
    channel: str | None,
    file_path: str,
    size_bytes: int,
    sha256: str,
    release_notes: str | None,
    pilot_ready: bool,
) -> models.Firmware:
    existing = get_firmware_by_version(session, version)
    if existing:
        raise ValueError(f"Firmware {version} already exists")
    firmware = models.Firmware(
        version=version,
        channel=channel,
        file_path=file_path,
        size_bytes=size_bytes,
        sha256=sha256,
        release_notes=release_notes,
        pilot_ready=pilot_ready,
    )
    session.add(firmware)
    session.flush()
    return firmware


def create_rollout(
    session: Session,
    *,
    name: str,
    firmware: models.Firmware,
    target_label: models.Label | None,
    stage: models.RolloutStage,
    status: models.RolloutStatus = models.RolloutStatus.draft,
) -> models.Rollout:
    existing = session.execute(
        select(models.Rollout).where(models.Rollout.name == name)
    ).scalar_one_or_none()
    if existing:
        raise ValueError(f"Rollout name '{name}' already exists")
    rollout = models.Rollout(
        name=name,
        firmware=firmware,
        target_label=target_label,
        stage=stage,
        status=status,
        is_active=status == models.RolloutStatus.active,
    )
    session.add(rollout)
    session.flush()
    return rollout


def set_rollout_status(
    session: Session,
    rollout: models.Rollout,
    *,
    status: models.RolloutStatus,
    is_active: bool | None = None,
) -> models.Rollout:
    rollout.status = status
    if is_active is not None:
        rollout.is_active = is_active
    elif status in {models.RolloutStatus.active}:
        rollout.is_active = True
    elif status in {models.RolloutStatus.completed, models.RolloutStatus.paused}:
        rollout.is_active = False
    rollout.start_at = rollout.start_at or (datetime.utcnow() if rollout.is_active else rollout.start_at)
    if status == models.RolloutStatus.completed:
        rollout.end_at = datetime.utcnow()
    session.flush()
    return rollout


def ensure_schedule(
    session: Session,
    *,
    name: str,
    rollout: models.Rollout,
    cron: str,
    enabled: bool,
) -> models.Schedule:
    schedule = session.execute(
        select(models.Schedule).where(models.Schedule.name == name)
    ).scalar_one_or_none()
    if schedule:
        schedule.cron = cron
        schedule.enabled = enabled
        schedule.rollout = rollout
    else:
        schedule = models.Schedule(name=name, cron=cron, enabled=enabled, rollout=rollout)
        session.add(schedule)
    session.flush()
    return schedule


def record_download(
    session: Session,
    *,
    device: models.Device,
    firmware: models.Firmware,
    status: models.DownloadStatus,
    error: str | None = None,
) -> models.DownloadLog:
    entry = models.DownloadLog(device=device, firmware=firmware, status=status, error=error)
    session.add(entry)
    session.flush()
    return entry


def find_active_rollouts_for_labels(
    session: Session,
    *,
    label_names: Iterable[str],
) -> list[models.Rollout]:
    labels = set(label_names)
    query = select(models.Rollout).join(models.Firmware)
    conditions = [models.Rollout.is_active.is_(True), models.Rollout.status == models.RolloutStatus.active]
    if labels:
        query = query.outerjoin(models.Label, models.Rollout.target_label)
        label_condition = or_(
            models.Rollout.target_label_id.is_(None),
            models.Label.name.in_(labels),
        )
        conditions.append(label_condition)
    else:
        conditions.append(models.Rollout.target_label_id.is_(None))
    return list(session.execute(query.where(and_(*conditions))).scalars())


def choose_manifest_for_device(
    session: Session,
    *,
    device: models.Device,
) -> tuple[models.Firmware | None, models.Rollout | None]:
    device_labels = list_device_labels(device)
    rollouts = find_active_rollouts_for_labels(session, label_names=device_labels or {"general"})
    try:
        current_version = Version(device.current_version) if device.current_version else None
    except Exception:  # pragma: no cover - invalid version strings
        current_version = None
    selected_firmware: models.Firmware | None = None
    selected_rollout: models.Rollout | None = None

    for rollout in rollouts:
        fw = rollout.firmware
        fw_version = Version(fw.version)
        if current_version and fw_version <= current_version:
            continue
        if not selected_firmware or Version(selected_firmware.version) < fw_version:
            selected_firmware = fw
            selected_rollout = rollout
    return selected_firmware, selected_rollout


def get_label(session: Session, name: str) -> models.Label:
    try:
        return session.execute(
            select(models.Label).where(models.Label.name == name)
        ).scalar_one()
    except NoResultFound as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Label '{name}' does not exist") from exc


def list_devices(session: Session) -> list[models.Device]:
    return list(session.execute(select(models.Device)).scalars())


def list_rollouts(session: Session) -> list[models.Rollout]:
    return list(session.execute(select(models.Rollout)).scalars())


def list_firmware(session: Session) -> list[models.Firmware]:
    return list(session.execute(select(models.Firmware)).scalars())
