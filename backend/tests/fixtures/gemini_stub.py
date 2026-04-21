import json
import sys
import time


def main() -> None:
    args = sys.argv[1:]
    model = args[args.index("-m") + 1]
    output_format = args[args.index("--output-format") + 1]

    if output_format == "json":
        sys.stdout.write(
            json.dumps(
                {
                    "session_id": "gemini-session",
                    "response": f"gemini:{model}:ok",
                }
            )
        )
        return

    if output_format == "stream-json":
        lines = [
            {
                "type": "init",
                "session_id": "gemini-session",
                "model": model,
            },
            {
                "type": "message",
                "role": "assistant",
                "content": "gemini-stream",
                "delta": True,
                "session_id": "gemini-session",
            },
            {
                "type": "result",
                "status": "success",
                "session_id": "gemini-session",
            },
        ]
        for line in lines:
            sys.stdout.write(json.dumps(line) + "\n")
            sys.stdout.flush()
            if line.get("type") == "message":
                time.sleep(0.4)
        return

    raise SystemExit(f"unexpected format: {output_format}")


if __name__ == "__main__":
    main()
