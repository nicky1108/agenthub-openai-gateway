#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${GATEWAY_ENV_FILE:-/etc/agenthub-openai-gateway.env}"
HERMES_API_BASE_VALUE="${HERMES_API_BASE:-http://127.0.0.1:8642/v1}"
HERMES_MODEL_VALUE="${HERMES_MODEL:-hermes-agent}"
HERMES_MAX_CONCURRENT_TASKS_VALUE="${HERMES_MAX_CONCURRENT_TASKS:-2}"
HERMES_TASK_START_CREDITS_VALUE="${HERMES_TASK_START_CREDITS:-10}"
HERMES_TASK_RUNTIME_CREDITS_PER_MINUTE_VALUE="${HERMES_TASK_RUNTIME_CREDITS_PER_MINUTE:-1}"

read_env_value() {
  local key="$1"
  local file="$2"
  if ! sudo test -r "$file"; then
    return 1
  fi
  sudo sed -n "s/^${key}=//p" "$file" | tail -n 1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

candidate_paths=()
if [ -n "${HERMES_SERVER_ENV_FILE:-}" ]; then
  candidate_paths+=("$HERMES_SERVER_ENV_FILE")
fi
candidate_paths+=(
  "/home/agenthub/.hermes/.env"
  "/home/${USER}/.hermes/.env"
  "/root/.hermes/.env"
  "/opt/hermes/.env"
)
if [ -n "${SUDO_USER:-}" ]; then
  candidate_paths+=("/home/${SUDO_USER}/.hermes/.env")
fi

HERMES_API_KEY_VALUE="${HERMES_API_KEY:-}"
HERMES_KEY_SOURCE="environment"
if [ -z "$HERMES_API_KEY_VALUE" ]; then
  for candidate_path in "${candidate_paths[@]}"; do
    if [ -z "$candidate_path" ]; then
      continue
    fi
    if HERMES_API_KEY_VALUE="$(read_env_value API_SERVER_KEY "$candidate_path")" && [ -n "$HERMES_API_KEY_VALUE" ]; then
      HERMES_KEY_SOURCE="$candidate_path"
      break
    fi
  done
fi

if [ -z "$HERMES_API_KEY_VALUE" ]; then
  echo "Hermes API_SERVER_KEY was not found in expected server env files" >&2
  exit 1
fi

if command -v curl >/dev/null 2>&1; then
  hermes_status="$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${HERMES_API_KEY_VALUE}" \
    "${HERMES_API_BASE_VALUE%/}/models" || true)"
  if [ "$hermes_status" != "200" ]; then
    echo "Hermes local API check failed with HTTP ${hermes_status}" >&2
    exit 1
  fi
else
  echo "curl is required to verify Hermes local API connectivity" >&2
  exit 1
fi

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT
if sudo test -f "$ENV_FILE"; then
  sudo cat "$ENV_FILE" > "$tmp_file"
fi

HERMES_CONFIG_API_KEY="$HERMES_API_KEY_VALUE" \
HERMES_CONFIG_API_BASE="$HERMES_API_BASE_VALUE" \
HERMES_CONFIG_MODEL="$HERMES_MODEL_VALUE" \
HERMES_CONFIG_MAX_CONCURRENT_TASKS="$HERMES_MAX_CONCURRENT_TASKS_VALUE" \
HERMES_CONFIG_TASK_START_CREDITS="$HERMES_TASK_START_CREDITS_VALUE" \
HERMES_CONFIG_TASK_RUNTIME_CREDITS_PER_MINUTE="$HERMES_TASK_RUNTIME_CREDITS_PER_MINUTE_VALUE" \
python3 - "$tmp_file" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
updates = {
    "HERMES_ENABLED": "true",
    "HERMES_API_BASE": os.environ["HERMES_CONFIG_API_BASE"],
    "HERMES_API_KEY": os.environ["HERMES_CONFIG_API_KEY"],
    "HERMES_MODEL": os.environ["HERMES_CONFIG_MODEL"],
    "HERMES_MAX_CONCURRENT_TASKS": os.environ["HERMES_CONFIG_MAX_CONCURRENT_TASKS"],
    "HERMES_TASK_START_CREDITS": os.environ["HERMES_CONFIG_TASK_START_CREDITS"],
    "HERMES_TASK_RUNTIME_CREDITS_PER_MINUTE": os.environ[
        "HERMES_CONFIG_TASK_RUNTIME_CREDITS_PER_MINUTE"
    ],
}
lines = path.read_text().splitlines() if path.exists() else []
seen: set[str] = set()
next_lines: list[str] = []
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        next_lines.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        next_lines.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        next_lines.append(line)
for key, value in updates.items():
    if key not in seen:
        next_lines.append(f"{key}={value}")
path.write_text("\n".join(next_lines).rstrip() + "\n")
PY

sudo install -m 600 -o root -g root "$tmp_file" "$ENV_FILE"
echo "Hermes gateway environment configured from ${HERMES_KEY_SOURCE}"
