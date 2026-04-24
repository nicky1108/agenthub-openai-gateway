from __future__ import annotations

import json
from pathlib import Path

from app.runtime.provider_cli_workspace import provider_cli_cwd


def test_provider_cli_cwd_uses_configured_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROVIDER_CLI_RUNTIME_DIR", str(tmp_path / "runtime"))

    assert provider_cli_cwd("gemini", "/custom/gemini") == "/custom/gemini"

    assert not (tmp_path / "runtime").exists()


def test_provider_cli_cwd_bootstraps_gemini_workspace(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROVIDER_CLI_RUNTIME_DIR", str(tmp_path / "runtime"))

    cwd = Path(provider_cli_cwd("gemini", None))

    assert cwd == tmp_path / "runtime" / "gemini"
    settings_path = cwd / ".gemini" / "settings.json"
    payload = json.loads(settings_path.read_text())
    assert payload["context"]["includeDirectoryTree"] is False
    assert payload["context"]["discoveryMaxDirs"] == 0
    assert payload["context"]["memoryBoundaryMarkers"] == []
    assert payload["skills"]["enabled"] is False
    assert payload["hooksConfig"]["enabled"] is False
    assert payload["experimental"]["jitContext"] is True


def test_provider_cli_cwd_returns_clean_codex_workspace(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROVIDER_CLI_RUNTIME_DIR", str(tmp_path / "runtime"))

    cwd = Path(provider_cli_cwd("codex", None))

    assert cwd == tmp_path / "runtime" / "codex"
    assert cwd.exists()
    assert not (cwd / ".gemini").exists()


def test_provider_cli_cwd_resolves_relative_runtime_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROVIDER_CLI_RUNTIME_DIR", "data/provider-cwd")

    cwd = Path(provider_cli_cwd("gemini", None))

    assert cwd == tmp_path / "data" / "provider-cwd" / "gemini"
    assert cwd.is_absolute()
