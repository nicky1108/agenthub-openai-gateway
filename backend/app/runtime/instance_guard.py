from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parents[2] / "data" / "runtime"


class RuntimeInstanceRunningError(RuntimeError):
    def __init__(self, kind: str, pid: int, path: Path) -> None:
        super().__init__(f"{kind} instance already running with pid {pid}")
        self.kind = kind
        self.pid = pid
        self.path = path


@dataclass(slots=True)
class RuntimeInstanceGuard:
    kind: str
    path: Path

    def acquire(self, *, pid: int | None = None) -> None:
        resolved_pid = pid or os.getpid()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        metadata = self.read_metadata()
        if metadata is not None:
            existing_pid = int(metadata.get("pid") or 0)
            if existing_pid and existing_pid != resolved_pid and self._pid_is_alive(existing_pid):
                raise RuntimeInstanceRunningError(self.kind, existing_pid, self.path)

        self.path.write_text(
            json.dumps(
                {
                    "kind": self.kind,
                    "pid": resolved_pid,
                }
            )
        )

    def release(self, *, pid: int | None = None) -> None:
        metadata = self.read_metadata()
        if metadata is None:
            return
        if pid is not None and int(metadata.get("pid") or 0) != pid:
            return
        self.path.unlink(missing_ok=True)

    def read_metadata(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


def backend_instance_guard() -> RuntimeInstanceGuard:
    return RuntimeInstanceGuard("backend", RUNTIME_DIR / "backend.pid")


def tunnel_agent_instance_guard(device_id: str) -> RuntimeInstanceGuard:
    safe_device_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in device_id)
    return RuntimeInstanceGuard("tunnel-agent", RUNTIME_DIR / f"tunnel-{safe_device_id}.pid")


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0
