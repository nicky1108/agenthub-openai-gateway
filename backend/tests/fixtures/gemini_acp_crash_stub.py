from __future__ import annotations

import json
import sys


def send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        message = json.loads(line)
        request_id = message.get("id")
        method = message.get("method")

        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": 1,
                        "agentInfo": {"name": "gemini-cli", "version": "stub"},
                        "agentCapabilities": {},
                    },
                }
            )
            continue

        if method == "session/new":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "sessionId": "crash-session",
                        "modes": {"availableModes": [], "currentModeId": "default"},
                        "models": {"availableModels": [], "currentModelId": "gemini-2.5-flash"},
                    },
                }
            )
            continue

        if method == "session/prompt":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
