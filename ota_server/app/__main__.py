from __future__ import annotations

import uvicorn

from .config import get_config


def main() -> None:
    config = get_config()
    uvicorn.run(
        "ota_server.app.main:app",
        host=config.server.host,
        port=config.server.port,
        ssl_certfile=config.server.cert_file,
        ssl_keyfile=config.server.key_file,
    )


if __name__ == "__main__":
    main()
