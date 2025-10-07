from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def test_client(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    storage_dir = tmp_path / "storage"
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()
    schedules_yaml = config_dir / "schedules.yaml"
    schedules_yaml.write_text("schedules: []\n", encoding="utf-8")

    server_yaml = {
        "server": {
            "host": "127.0.0.1",
            "port": 8443,
            "api_token": "test-token",
            "cert_file": str(cert_dir / "server.crt"),
            "key_file": str(cert_dir / "server.key"),
            "storage_root": str(storage_dir),
            "manifest_ttl_seconds": 60,
            "poll_interval_minutes": 5,
            "max_firmware_size_kb": 3900,
        },
        "scheduler": {
            "timezone": "UTC",
            "schedules_file": str(schedules_yaml),
        },
        "database": {
            "url": f"sqlite:///{tmp_path / 'test.db'}",
        },
        "logging": {
            "level": "INFO",
        },
    }
    config_path = config_dir / "server.yml"
    config_path.write_text(json.dumps(server_yaml), encoding="utf-8")

    monkeypatch.setenv("OTA_CONFIG", str(config_path))

    from server.app import config as app_config

    app_config.get_config.cache_clear()

    database_module = importlib.import_module("server.app.database")
    database_module.Base.metadata.clear()
    if hasattr(database_module.Base, "registry"):
        database_module.Base.registry.dispose()

    modules_to_reload = [
        "server.app.config",
        "server.app.database",
        "server.app.models",
        "server.app.crud",
        "server.app.scheduler",
        "server.app.main",
    ]
    reloaded = {}
    for module_name in modules_to_reload:
        sys.modules.pop(module_name, None)
        reloaded[module_name] = importlib.import_module(module_name)

    from server.app import main as app_main

    class DummyScheduler:
        def start(self):
            return None

        def shutdown(self):
            return None

        def refresh_jobs(self, *args, **kwargs):
            return None

    app_main._scheduler = DummyScheduler()

    with TestClient(app_main.app) as client:
        yield client, app_main


def test_check_update_no_rollout(test_client):
    client, app_main = test_client
    response = client.post(
        "/api/v1/check-update",
        headers={"X-OTA-Token": "test-token"},
        json={
            "mac": "aa:bb:cc:dd:ee:ff",
            "current_version": "0.9.0",
            "labels": ["pilot"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["update_available"] is False
    assert payload["manifest"] is None

    from server.app import models
    from server.app.database import session_scope

    with session_scope() as session:
        device = session.execute(
            select(models.Device).where(models.Device.mac == "aabbccddeeff")
        ).scalar_one_or_none()
        assert device is not None
        assert device.current_version == "0.9.0"


def test_check_update_with_rollout_and_report(test_client, tmp_path):
    client, app_main = test_client
    from server.app import crud, models
    from server.app.database import session_scope
    from server.app.storage import store_firmware_file

    firmware_path = tmp_path / "firmware.bin"
    firmware_path.write_bytes(b"test-binary")

    stored_path, size_bytes, sha256 = store_firmware_file(firmware_path, "1.0.0")

    with session_scope() as session:
        firmware = crud.create_firmware(
            session,
            version="1.0.0",
            channel="pilot",
            file_path=str(stored_path),
            size_bytes=size_bytes,
            sha256=sha256,
            release_notes="Test build",
            pilot_ready=True,
        )
        label = session.execute(
            select(models.Label).where(models.Label.name == "pilot")
        ).scalar_one_or_none()
        if not label:
            label = models.Label(name="pilot")
            session.add(label)
            session.flush()
        rollout = crud.create_rollout(
            session,
            name="pilot-rollout",
            firmware=firmware,
            target_label=label,
            stage=models.RolloutStage.pilot,
            status=models.RolloutStatus.active,
        )
        crud.set_rollout_status(session, rollout, status=models.RolloutStatus.active, is_active=True)

    response = client.post(
        "/api/v1/check-update",
        headers={"X-OTA-Token": "test-token"},
        json={
            "mac": "aa:bb:cc:dd:ee:11",
            "current_version": "0.9.0",
            "labels": ["pilot"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["update_available"] is True
    manifest = payload["manifest"]
    assert manifest["version"] == "1.0.0"
    assert manifest["sha256"] == sha256

    report = client.post(
        "/api/v1/report-status",
        headers={"X-OTA-Token": "test-token"},
        json={
            "mac": "aa:bb:cc:dd:ee:11",
            "firmware_version": "1.0.0",
            "status": "success",
        },
    )
    assert report.status_code == 200

    from server.app.database import session_scope as scope2
    with scope2() as session:
        device = session.execute(
            select(models.Device).where(models.Device.mac == "aabbccddee11")
        ).scalar_one()
        assert device.current_version == "1.0.0"
        logs = session.execute(
            select(models.DownloadLog).where(models.DownloadLog.device_id == device.id)
        ).scalars().all()
        statuses = [entry.status.value for entry in logs]
        assert "downloading" in statuses
        assert "success" in statuses
