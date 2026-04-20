import json
import sys

payload = json.loads(sys.stdin.read())
sys.stdout.write(
    json.dumps(
        {
            "id": "fixture-cli-1",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "real-cli-response"},
                    "finish_reason": "stop",
                }
            ],
        }
    )
)
