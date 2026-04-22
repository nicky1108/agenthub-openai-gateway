from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import Settings
from app.runtime.instance_guard import RuntimeInstanceRunningError, tunnel_agent_instance_guard
from app.tunnel.agent import PublicGatewayTunnelAgent


async def _run() -> int:
    settings = Settings()
    if not settings.public_gateway_tunnel_device_id:
        print("PUBLIC_GATEWAY_TUNNEL_DEVICE_ID is required")
        return 1

    guard = tunnel_agent_instance_guard(settings.public_gateway_tunnel_device_id)
    try:
        guard.acquire()
    except RuntimeInstanceRunningError as exc:
        print(f"{exc.kind} already running with pid {exc.pid}")
        return 1

    try:
        agent = PublicGatewayTunnelAgent.from_settings(settings)
        await agent.run_forever()
    finally:
        guard.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
