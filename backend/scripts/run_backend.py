from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import Settings
from app.runtime.instance_guard import RuntimeInstanceRunningError, backend_instance_guard, port_in_use


def main() -> int:
    settings = Settings()
    if port_in_use(settings.openai_gateway_host, settings.openai_gateway_port):
        print(f"backend already running on {settings.openai_gateway_host}:{settings.openai_gateway_port}")
        return 1
    guard = backend_instance_guard()
    try:
        guard.acquire()
    except RuntimeInstanceRunningError as exc:
        print(f"{exc.kind} already running with pid {exc.pid}")
        return 1

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.openai_gateway_host,
            port=settings.openai_gateway_port,
        )
    finally:
        guard.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
