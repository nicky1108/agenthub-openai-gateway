import json
import sys
import time


def main() -> None:
    model = "unknown"
    if "-m" in sys.argv:
        model = sys.argv[sys.argv.index("-m") + 1]
    prompt = sys.stdin.read()
    if "-" not in sys.argv or "USER: hello" not in prompt:
        sys.stderr.write("expected prompt on stdin\n")
        raise SystemExit(2)

    events = [
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "codex-item-1",
                "type": "agent_message",
                "text": f"codex:{model}:ok",
            },
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "output_tokens": 3},
        },
    ]
    for event in events:
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()
        if event.get("type") == "item.completed":
            time.sleep(0.4)


if __name__ == "__main__":
    main()
