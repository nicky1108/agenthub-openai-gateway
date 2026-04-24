from __future__ import annotations

import json
from pathlib import Path

from app.core.settings import Settings


GEMINI_MINIMAL_WORKSPACE_SETTINGS: dict[str, object] = {
    "context": {
        "includeDirectoryTree": False,
        "discoveryMaxDirs": 0,
        "memoryBoundaryMarkers": [],
        "loadMemoryFromIncludeDirectories": False,
    },
    "skills": {"enabled": False},
    "hooksConfig": {"enabled": False},
    "experimental": {"jitContext": True},
}


def _runtime_root() -> Path:
    root = Path(Settings().provider_cli_runtime_dir).expanduser()
    if root.is_absolute():
        return root
    return (Path.cwd() / root).resolve()


def _bootstrap_gemini_workspace(cwd: Path) -> None:
    settings_path = cwd / ".gemini" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        return
    settings_path.write_text(
        json.dumps(GEMINI_MINIMAL_WORKSPACE_SETTINGS, indent=2, sort_keys=True) + "\n",
    )


def provider_cli_cwd(provider_name: str, configured_cwd: str | None) -> str | None:
    if configured_cwd:
        return configured_cwd
    if provider_name not in {"codex", "gemini"}:
        return None

    cwd = _runtime_root() / provider_name
    cwd.mkdir(parents=True, exist_ok=True)
    if provider_name == "gemini" and Settings().provider_cli_bootstrap_workspaces:
        _bootstrap_gemini_workspace(cwd)
    return str(cwd)
