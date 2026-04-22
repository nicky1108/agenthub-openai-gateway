import os
import socket
from pathlib import Path

import pytest

from app.runtime.instance_guard import (
    RuntimeInstanceGuard,
    RuntimeInstanceRunningError,
    backend_instance_guard,
    tunnel_agent_instance_guard,
)


def test_backend_guard_rejects_existing_live_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr("app.runtime.instance_guard.RUNTIME_DIR", runtime_dir)

    guard = backend_instance_guard()
    guard.acquire(pid=os.getpid())

    with pytest.raises(RuntimeInstanceRunningError) as exc_info:
        guard.acquire(pid=2002)

    assert exc_info.value.pid == os.getpid()
    assert guard.read_metadata()["pid"] == os.getpid()


def test_tunnel_guard_is_scoped_by_device_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr("app.runtime.instance_guard.RUNTIME_DIR", runtime_dir)

    first = tunnel_agent_instance_guard("local-mac-dev")
    second = tunnel_agent_instance_guard("other-device")

    first.acquire(pid=1001)
    second.acquire(pid=2002)

    assert first.path != second.path
    assert first.read_metadata()["pid"] == 1001
    assert second.read_metadata()["pid"] == 2002


def test_guard_reclaims_stale_pid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr("app.runtime.instance_guard.RUNTIME_DIR", runtime_dir)

    guard = RuntimeInstanceGuard("backend", path=runtime_dir / "backend.pid")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    guard.path.write_text('{"pid": 999999, "kind": "backend"}')

    guard.acquire(pid=os.getpid())

    assert guard.read_metadata()["pid"] == os.getpid()


def test_guard_release_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr("app.runtime.instance_guard.RUNTIME_DIR", runtime_dir)

    guard = backend_instance_guard()
    guard.acquire(pid=os.getpid())
    guard.release(pid=os.getpid())
    guard.release(pid=os.getpid())

    assert not guard.path.exists()


def test_port_in_use_detects_bound_socket() -> None:
    from app.runtime.instance_guard import port_in_use

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        host, port = sock.getsockname()
        assert port_in_use(host, port) is True
