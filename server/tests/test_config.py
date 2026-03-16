from __future__ import annotations

from pathlib import Path

import yaml

from server.app.config import load_config


def test_load_config_resolves_relative_paths_from_server_root(tmp_path):
    server_root = tmp_path / "server"
    config_dir = server_root / "config"
    config_dir.mkdir(parents=True)

    config_path = config_dir / "server.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "server": {
                    "host": "127.0.0.1",
                    "port": 8443,
                    "api_token": "token",
                    "cert_file": "certs/server.crt",
                    "key_file": "certs/server.key",
                    "storage_root": "firmware_store",
                },
                "scheduler": {
                    "timezone": "UTC",
                    "schedules_file": "config/schedules.yaml",
                },
                "database": {
                    "url": "sqlite:///./ota.db",
                },
                "logging": {
                    "level": "INFO",
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.server.cert_file == str((server_root / "certs/server.crt").resolve())
    assert config.server.key_file == str((server_root / "certs/server.key").resolve())
    assert config.server.storage_root == str((server_root / "firmware_store").resolve())
    assert config.scheduler.schedules_file == str((server_root / "config/schedules.yaml").resolve())
    assert config.database.url == f"sqlite:///{(server_root / 'ota.db').resolve()}"
