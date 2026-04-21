from __future__ import annotations

import asyncio

from app.core.settings import Settings
from app.tunnel.agent import PublicGatewayTunnelAgent


async def main() -> None:
    agent = PublicGatewayTunnelAgent.from_settings(Settings())
    await agent.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
