from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from packaging.version import Version, InvalidVersion
from sqlalchemy import select

from app import crud, models
from app.config import get_config
from app.database import init_db, session_scope
from app.scheduler import RolloutScheduler
from app.storage import store_firmware_file

app = typer.Typer(help="OTA server management CLI")


@app.command()
def initdb() -> None:
    """Initialise the SQLite database."""
    init_db()
    typer.echo("Database initialised")


@app.command()
def firmware_upload(
    path: Path = typer.Argument(..., exists=True, readable=True),
    version: str = typer.Option(..., "--version", "-v", help="Firmware semantic version"),
    channel: Optional[str] = typer.Option(None, "--channel", help="Distribution channel label"),
    release_notes: Optional[str] = typer.Option(None, "--notes", help="Release notes"),
    pilot_ready: bool = typer.Option(False, "--pilot-ready/--not-pilot-ready", help="Flag firmware as ready for pilot rollout"),
) -> None:
    """Upload firmware binary to the storage directory and register it."""
    try:
        Version(version)
    except InvalidVersion as exc:  # pragma: no cover - validated at runtime
        raise typer.BadParameter(f"Invalid semantic version: {version}") from exc

    stored_path, size_bytes, sha256 = store_firmware_file(path, version)
    with session_scope() as session:
        firmware = crud.create_firmware(
            session,
            version=version,
            channel=channel,
            file_path=str(stored_path),
            size_bytes=size_bytes,
            sha256=sha256,
            release_notes=release_notes,
            pilot_ready=pilot_ready,
        )
        typer.echo(f"Registered firmware {firmware.version} (sha256={firmware.sha256})")


@app.command()
def label_assign(
    mac: str = typer.Argument(..., help="Device MAC address"),
    label: str = typer.Argument(..., help="Label to assign to the device"),
) -> None:
    """Assign a label to a device."""
    with session_scope() as session:
        existing = session.execute(
            select(models.Device).where(models.Device.mac == mac)
        ).scalar_one_or_none()
        current_version = existing.current_version if existing else "0.0.0"
        device = crud.register_or_update_device(
            session,
            mac=mac,
            ip=None,
            current_version=current_version or "0.0.0",
            label_names=[label],
            meta=None,
        )
        session.commit()
        typer.echo(f"Assigned label '{label}' to device {device.mac}")


@app.command()
def device_list() -> None:
    """List registered devices."""
    with session_scope() as session:
        data = [
            {
                "mac": device.mac,
                "ip": device.ip,
                "current_version": device.current_version,
                "labels": sorted(crud.list_device_labels(device)),
                "last_seen": device.last_seen.isoformat(),
            }
            for device in crud.list_devices(session)
        ]
    typer.echo(json.dumps(data, indent=2))


@app.command()
def firmware_list() -> None:
    """List known firmware builds."""
    with session_scope() as session:
        data = [
            {
                "version": fw.version,
                "channel": fw.channel,
                "size_bytes": fw.size_bytes,
                "pilot_ready": fw.pilot_ready,
                "created_at": fw.created_at.isoformat(),
            }
            for fw in crud.list_firmware(session)
        ]
    typer.echo(json.dumps(data, indent=2))


@app.command()
def rollout_create(
    name: str = typer.Argument(..., help="Rollout name"),
    firmware_version: str = typer.Option(..., "--firmware", help="Firmware version to rollout"),
    target_label: Optional[str] = typer.Option(None, "--label", help="Target label (None applies to all devices)"),
    stage: models.RolloutStage = typer.Option(models.RolloutStage.general, "--stage", case_sensitive=False),
    activate: bool = typer.Option(False, "--activate/--no-activate", help="Immediately activate rollout"),
) -> None:
    """Create a rollout."""
    with session_scope() as session:
        firmware = crud.get_firmware_by_version(session, firmware_version)
        if not firmware:
            raise typer.BadParameter(f"Firmware {firmware_version} not found")
        target = None
        if target_label:
            target = crud.get_label(session, target_label)
        rollout = crud.create_rollout(
            session,
            name=name,
            firmware=firmware,
            target_label=target,
            stage=stage,
            status=models.RolloutStatus.active if activate else models.RolloutStatus.draft,
        )
        if activate:
            crud.set_rollout_status(session, rollout, status=models.RolloutStatus.active, is_active=True)
        session.commit()
        typer.echo(f"Rollout '{name}' created for firmware {firmware_version}")


@app.command()
def rollout_status(
    name: str = typer.Argument(..., help="Rollout name"),
    status_value: models.RolloutStatus = typer.Option(..., "--status", case_sensitive=False),
) -> None:
    """Update rollout status."""
    with session_scope() as session:
        rollout = session.execute(
            select(models.Rollout).where(models.Rollout.name == name)
        ).scalar_one_or_none()
        if not rollout:
            raise typer.BadParameter(f"Rollout '{name}' not found")
        crud.set_rollout_status(session, rollout, status=status_value)
        session.commit()
        typer.echo(f"Rollout '{name}' updated to {status_value}")


@app.command()
def scheduler_sync() -> None:
    """Synchronise cron schedules from configuration file."""
    scheduler = RolloutScheduler()
    scheduler.refresh_jobs(apply_jobs=False)
    typer.echo("Scheduler jobs refreshed")


if __name__ == "__main__":
    app()
