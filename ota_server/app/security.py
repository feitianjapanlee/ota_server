from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from .config import get_config


def verify_api_token(x_ota_token: str = Header(...)) -> str:
    config = get_config()
    if x_ota_token != config.server.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTA token")
    return x_ota_token


def get_poll_interval_minutes() -> int:
    return get_config().server.poll_interval_minutes
