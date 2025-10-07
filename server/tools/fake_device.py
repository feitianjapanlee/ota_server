#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from pathlib import Path
from typing import Optional

import httpx


async def download_and_verify(client: httpx.AsyncClient, url: str, token: str, expected_sha: str, dest: Path) -> Path:
    headers = {"X-OTA-Token": token}
    async with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        hasher = hashlib.sha256()
        with dest.open("wb") as fh:
            async for chunk in response.aiter_bytes():
                fh.write(chunk)
                hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != expected_sha:
        raise ValueError(f"SHA mismatch: expected {expected_sha}, got {digest}")
    return dest


async def simulate_device(
    *,
    base_url: str,
    mac: str,
    version: str,
    labels: list[str],
    token: str,
    verify: Optional[str | bool],
    download_dir: Path,
) -> None:
    payload = {
        "mac": mac,
        "current_version": version,
        "labels": labels,
    }
    headers = {"X-OTA-Token": token}
    async with httpx.AsyncClient(base_url=base_url, verify=verify, timeout=30.0) as client:
        response = await client.post("/api/v1/check-update", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        print("Check update response:", data)
        if not data.get("update_available"):
            return
        manifest = data["manifest"]
        firmware_url = manifest["url"]
        sha256 = manifest["sha256"]
        dest = download_dir / Path(firmware_url).name
        downloaded = await download_and_verify(client, firmware_url, token, sha256, dest)
        print(f"Firmware downloaded to {downloaded}")
        report_payload = {
            "mac": mac,
            "firmware_version": manifest["version"],
            "status": "success",
        }
        report = await client.post("/api/v1/report-status", json=report_payload, headers=headers)
        report.raise_for_status()
        print("Reported success:", report.json())


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate an ESP32 device checking for OTA updates")
    parser.add_argument("--base-url", default="https://localhost:8443", help="OTA server base URL")
    parser.add_argument("--mac", default="aa:bb:cc:dd:ee:ff", help="Device MAC address")
    parser.add_argument("--version", default="0.0.1", help="Current firmware version")
    parser.add_argument("--labels", nargs="*", default=["pilot"], help="Device labels")
    parser.add_argument("--token", default=os.getenv("OTA_TOKEN", "change-me"), help="API token")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification (development only)")
    parser.add_argument("--cert", help="Path to CA bundle for TLS verification")
    parser.add_argument("--download-dir", default="./downloads", help="Directory to store downloaded firmware")

    args = parser.parse_args()

    verify: Optional[str | bool]
    if args.insecure:
        verify = False
    elif args.cert:
        verify = args.cert
    else:
        verify = True

    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(
        simulate_device(
            base_url=args.base_url,
            mac=args.mac,
            version=args.version,
            labels=args.labels,
            token=args.token,
            verify=verify,
            download_dir=download_dir,
        )
    )


if __name__ == "__main__":
    main()
