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
        params = message.get("params") or {}

        if method == "initialize":
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": 1,
                        "agentInfo": {"name": "gemini-cli", "version": "stub"},
                        "agentCapabilities": {
                            "loadSession": True,
                            "promptCapabilities": {"image": True, "audio": True, "embeddedContext": True},
                            "mcpCapabilities": {"http": True, "sse": True},
                        },
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
                        "sessionId": "stub-session",
                        "modes": {"availableModes": [], "currentModeId": "default"},
                        "models": {"availableModels": [], "currentModelId": "gemini-2.5-flash"},
                    },
                }
            )
            continue

        if method == "session/prompt":
            session_id = params.get("sessionId", "stub-session")
            send(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "OK"},
                        },
                    },
                }
            )
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "stopReason": "end_turn",
                        "_meta": {
                            "quota": {
                                "token_count": {"input_tokens": 12, "output_tokens": 1},
                            }
                        },
                    },
                }
            )
            continue

        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"unknown method {method}"},
            }
        )


if __name__ == "__main__":
    main()
