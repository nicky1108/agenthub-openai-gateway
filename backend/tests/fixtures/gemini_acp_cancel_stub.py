from __future__ import annotations

import json
import sys


def send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    pending_prompt_id: object | None = None
    session_id = "cancel-session"
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        message = json.loads(line)
        request_id = message.get("id")
        method = message.get("method")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": 1}})
            continue

        if method == "session/new":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"sessionId": session_id}})
            continue

        if method == "session/prompt":
            pending_prompt_id = request_id
            send(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "partial"},
                        },
                    },
                }
            )
            continue

        if method == "session/cancel":
            send({"jsonrpc": "2.0", "id": request_id, "result": {"cancelled": True}})
            if pending_prompt_id is not None:
                send({"jsonrpc": "2.0", "id": pending_prompt_id, "result": {"stopReason": "cancelled"}})
            continue

        send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": method}})


if __name__ == "__main__":
    main()
