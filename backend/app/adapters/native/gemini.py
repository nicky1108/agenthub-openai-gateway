from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from app.adapters.base import ChatRequest
from app.runtime.logging import elapsed_ms, log_gateway_event


DEFAULT_GEMINI_NATIVE_BASE_URL = "https://cloudcode-pa.googleapis.com"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DEFAULT_USER_AGENT = "google-api-nodejs-client/9.15.1 (gzip)"
DEFAULT_X_GOOG_API_CLIENT = "gl-node/24.0.0"


class GeminiNativeAuthError(RuntimeError):
    """Raised when local Gemini CLI OAuth credentials are missing or unusable."""


class GeminiNativeProviderError(RuntimeError):
    """Raised when Google's Code Assist backend rejects or fails a request."""


@dataclass(slots=True)
class GeminiOAuthCredentials:
    access_token: str
    refresh_token: str | None = None
    expires_ms: int | None = None
    project_id: str | None = None
    managed_project_id: str | None = None
    raw: dict[str, Any] | None = None

    def expiring(self, refresh_skew_seconds: int) -> bool:
        if not self.expires_ms:
            return False
        return (time.time() + max(0, refresh_skew_seconds)) * 1000 >= self.expires_ms


def _parse_packed_refresh(value: str) -> tuple[str, str | None, str | None]:
    parts = value.split("|", 2)
    refresh_token = parts[0]
    project_id = parts[1] if len(parts) > 1 and parts[1] else None
    managed_project_id = parts[2] if len(parts) > 2 and parts[2] else None
    return refresh_token, project_id, managed_project_id


def load_gemini_oauth_credentials(auth_file: str, *, refresh_skew_seconds: int) -> GeminiOAuthCredentials:
    path = Path(auth_file).expanduser()
    if not path.is_file():
        raise GeminiNativeAuthError("Gemini OAuth auth file is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GeminiNativeAuthError("Gemini OAuth auth file is invalid") from exc
    if not isinstance(payload, dict):
        raise GeminiNativeAuthError("Gemini OAuth auth file is invalid")

    # Official Gemini CLI shape: access_token / refresh_token / expiry_date.
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_ms = payload.get("expiry_date")
    project_id: str | None = None
    managed_project_id: str | None = None

    # Hermes-compatible shape: access / refresh / expires, with refresh packed
    # as refreshToken|projectId|managedProjectId.
    if not isinstance(access_token, str) or not access_token.strip():
        access_token = payload.get("access")
        packed_refresh = payload.get("refresh")
        if isinstance(packed_refresh, str):
            refresh_token, project_id, managed_project_id = _parse_packed_refresh(packed_refresh)
        expires_ms = payload.get("expires")

    if not isinstance(access_token, str) or not access_token.strip():
        raise GeminiNativeAuthError("Gemini OAuth access token is missing")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        refresh_token = None
    try:
        expires = int(expires_ms) if expires_ms is not None else None
    except (TypeError, ValueError):
        expires = None

    credentials = GeminiOAuthCredentials(
        access_token=access_token.strip(),
        refresh_token=refresh_token.strip() if isinstance(refresh_token, str) else None,
        expires_ms=expires,
        project_id=project_id,
        managed_project_id=managed_project_id,
        raw=payload,
    )
    if credentials.expiring(refresh_skew_seconds) and not credentials.refresh_token:
        raise GeminiNativeAuthError("Gemini OAuth access token is expired or expiring")
    return credentials


def _oauth_client_from_env() -> tuple[str | None, str | None]:
    client_id = os.getenv("GEMINI_NATIVE_OAUTH_CLIENT_ID") or os.getenv("HERMES_GEMINI_CLIENT_ID")
    client_secret = os.getenv("GEMINI_NATIVE_OAUTH_CLIENT_SECRET") or os.getenv("HERMES_GEMINI_CLIENT_SECRET")
    return (client_id.strip() if client_id else None, client_secret.strip() if client_secret else None)


def _oauth_client_from_local_gemini() -> tuple[str | None, str | None]:
    binary = shutil.which("gemini")
    if not binary:
        return None, None
    try:
        real = Path(binary).resolve()
    except OSError:
        return None, None

    roots: list[Path] = []
    current = real.parent
    for _ in range(10):
        roots.append(current)
        if (current / "node_modules").exists():
            roots.append(current / "node_modules" / "@google" / "gemini-cli-core")
            break
        if current.parent == current:
            break
        current = current.parent

    client_id_pattern = re.compile(r"([0-9]{8,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com)")
    client_secret_pattern = re.compile(r"(GOCSPX-[A-Za-z0-9_-]{20,})")
    for root in roots:
        if not root.exists():
            continue
        candidates = [
            root / "dist" / "src" / "code_assist" / "oauth2.js",
            root / "dist" / "code_assist" / "oauth2.js",
            root / "src" / "code_assist" / "oauth2.js",
        ]
        try:
            candidates.extend(root.rglob("oauth2.js"))
        except OSError:
            pass
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            client_id = client_id_pattern.search(content)
            client_secret = client_secret_pattern.search(content)
            if client_id:
                return client_id.group(1), client_secret.group(1) if client_secret else None
    return None, None


def _coerce_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                pieces.append(part["text"])
        return "\n".join(pieces)
    return str(content)


def _tool_call_to_gemini(tool_call: dict[str, Any]) -> dict[str, Any] | None:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    raw_arguments = function.get("arguments", "{}")
    try:
        args = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        args = {"_raw": raw_arguments}
    if not isinstance(args, dict):
        args = {"_value": args}
    return {
        "functionCall": {"name": name.strip(), "args": args},
        "thoughtSignature": "skip_thought_signature_validator",
    }


def _tool_result_to_gemini(message: dict[str, Any]) -> dict[str, Any]:
    name = str(message.get("name") or message.get("tool_call_id") or "tool")
    content = _coerce_content_to_text(message.get("content"))
    try:
        parsed = json.loads(content) if content.strip().startswith(("{", "[")) else None
    except json.JSONDecodeError:
        parsed = None
    return {"functionResponse": {"name": name, "response": parsed if isinstance(parsed, dict) else {"output": content}}}


def _build_gemini_contents(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        if role in {"system", "developer"}:
            text = _coerce_content_to_text(message.get("content")).strip()
            if text:
                system_parts.append(text)
            continue
        if role in {"tool", "function"}:
            contents.append({"role": "user", "parts": [_tool_result_to_gemini(message)]})
            continue

        parts: list[dict[str, Any]] = []
        text = _coerce_content_to_text(message.get("content")).strip()
        if text:
            parts.append({"text": text})
        if role == "assistant":
            for tool_call in message.get("tool_calls") or []:
                if isinstance(tool_call, dict):
                    part = _tool_call_to_gemini(tool_call)
                    if part is not None:
                        parts.append(part)
        if parts:
            contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})

    system_instruction = None
    system_text = "\n".join(system_parts).strip()
    if system_text:
        system_instruction = {"role": "system", "parts": [{"text": system_text}]}
    return contents or [{"role": "user", "parts": [{"text": ""}]}], system_instruction


def _translate_tools_to_gemini(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list):
        return []
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        declaration: dict[str, Any] = {"name": name.strip()}
        description = function.get("description")
        if isinstance(description, str) and description:
            declaration["description"] = description
        parameters = function.get("parameters")
        if isinstance(parameters, dict):
            declaration["parameters"] = parameters
        declarations.append(declaration)
    return [{"functionDeclarations": declarations}] if declarations else []


def _translate_tool_choice_to_gemini(tool_choice: Any) -> dict[str, Any] | None:
    if isinstance(tool_choice, str):
        if tool_choice == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        if tool_choice == "required":
            return {"functionCallingConfig": {"mode": "ANY"}}
        if tool_choice == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
    if isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [function["name"]],
                }
            }
    return None


def _normalize_thinking_config(config: Any) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    normalized: dict[str, Any] = {}
    budget = config.get("thinkingBudget", config.get("thinking_budget"))
    level = config.get("thinkingLevel", config.get("thinking_level"))
    include = config.get("includeThoughts", config.get("include_thoughts"))
    if isinstance(budget, (int, float)):
        normalized["thinkingBudget"] = int(budget)
    if isinstance(level, str) and level.strip():
        normalized["thinkingLevel"] = level.strip().lower()
    if isinstance(include, bool):
        normalized["includeThoughts"] = include
    return normalized or None


def _map_finish_reason(reason: str) -> str:
    mapping = {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
        "OTHER": "stop",
    }
    return mapping.get(reason.upper(), "stop")


def _usage_payload(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    prompt_tokens = int(usage.get("promptTokenCount") or 0)
    completion_tokens = int(usage.get("candidatesTokenCount") or 0)
    total_tokens = int(usage.get("totalTokenCount") or prompt_tokens + completion_tokens)
    cached_tokens = int(usage.get("cachedContentTokenCount") or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens_details": {"cached_tokens": cached_tokens},
    }


class GeminiNativeAdapter:
    def __init__(
        self,
        *,
        auth_file: str,
        base_url: str = DEFAULT_GEMINI_NATIVE_BASE_URL,
        timeout_seconds: float = 120.0,
        refresh_skew_seconds: int = 120,
        project_id: str | None = None,
        projects_file: str = "~/.gemini/projects.json",
        project_lookup_path: str | None = None,
        auto_discover_project: bool = True,
        refresh_enabled: bool = True,
        thinking_budget: int | None = 0,
        oauth_client_id: str | None = None,
        oauth_client_secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.auth_file = auth_file
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.refresh_skew_seconds = refresh_skew_seconds
        self.project_id = project_id
        self.projects_file = projects_file
        self.project_lookup_path = project_lookup_path
        self.auto_discover_project = auto_discover_project
        self.refresh_enabled = refresh_enabled
        self.thinking_budget = thinking_budget
        self.oauth_client_id = oauth_client_id
        self.oauth_client_secret = oauth_client_secret
        self.transport = transport
        self._project_id_cache: str | None = None

    def _client(self, credentials: GeminiOAuthCredentials, *, accept: str = "application/json") -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={
                "Authorization": f"Bearer {credentials.access_token}",
                "Content-Type": "application/json",
                "Accept": accept,
                "User-Agent": DEFAULT_USER_AGENT,
                "X-Goog-Api-Client": DEFAULT_X_GOOG_API_CLIENT,
            },
            transport=self.transport,
            trust_env=True,
        )

    def _load_credentials(self) -> GeminiOAuthCredentials:
        return load_gemini_oauth_credentials(self.auth_file, refresh_skew_seconds=self.refresh_skew_seconds)

    def _oauth_client_credentials(self) -> tuple[str, str | None]:
        if self.oauth_client_id:
            return self.oauth_client_id, self.oauth_client_secret
        env_client_id, env_client_secret = _oauth_client_from_env()
        if env_client_id:
            return env_client_id, env_client_secret
        local_client_id, local_client_secret = _oauth_client_from_local_gemini()
        if local_client_id:
            return local_client_id, local_client_secret
        raise GeminiNativeAuthError("Gemini OAuth client credentials are unavailable for token refresh")

    async def _refresh_credentials(self, credentials: GeminiOAuthCredentials) -> GeminiOAuthCredentials:
        if not self.refresh_enabled:
            raise GeminiNativeAuthError("Gemini OAuth access token is expired or expiring")
        if not credentials.refresh_token:
            raise GeminiNativeAuthError("Gemini OAuth refresh token is missing")
        client_id, client_secret = self._oauth_client_credentials()
        data = {
            "grant_type": "refresh_token",
            "refresh_token": credentials.refresh_token,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), transport=self.transport, trust_env=True) as client:
            response = await client.post(TOKEN_ENDPOINT, data=data)
        if response.status_code >= 400:
            raise GeminiNativeAuthError(f"Gemini OAuth refresh failed with status {response.status_code}")
        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise GeminiNativeAuthError("Gemini OAuth refresh response did not include access_token")
        refresh_token = payload.get("refresh_token")
        expires_in = int(payload.get("expires_in") or 3600)
        updated_raw = dict(credentials.raw or {})
        if "access" in updated_raw or "refresh" in updated_raw:
            updated_raw["access"] = access_token
            updated_raw["expires"] = int((time.time() + max(60, expires_in)) * 1000)
            if isinstance(refresh_token, str) and refresh_token.strip():
                packed = _parse_packed_refresh(str(updated_raw.get("refresh") or credentials.refresh_token or ""))
                updated_raw["refresh"] = "|".join(
                    part for part in [refresh_token.strip(), packed[1] or "", packed[2] or ""] if part
                )
        else:
            updated_raw["access_token"] = access_token
            updated_raw["expiry_date"] = int((time.time() + max(60, expires_in)) * 1000)
            if isinstance(refresh_token, str) and refresh_token.strip():
                updated_raw["refresh_token"] = refresh_token.strip()
        self._save_credentials(updated_raw)
        return self._load_credentials()

    def _save_credentials(self, payload: dict[str, Any]) -> None:
        path = Path(self.auth_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)

    async def _credentials(self) -> GeminiOAuthCredentials:
        credentials = self._load_credentials()
        if credentials.expiring(self.refresh_skew_seconds):
            credentials = await self._refresh_credentials(credentials)
        return credentials

    def _project_from_projects_file(self) -> str | None:
        path = Path(self.projects_file).expanduser()
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        projects = payload.get("projects")
        if not isinstance(projects, dict):
            return None
        lookup_path = self.project_lookup_path or os.getcwd()
        candidates = [lookup_path]
        try:
            candidates.append(str(Path(lookup_path).resolve()))
        except OSError:
            pass
        for candidate in candidates:
            project = projects.get(candidate)
            if isinstance(project, str) and project.strip():
                return project.strip()
        return None

    async def _load_code_assist_project(self, client: httpx.AsyncClient, model: str) -> str | None:
        body = {
            "metadata": {
                "duetProject": "",
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        }
        response = await client.post(f"{self.base_url}/v1internal:loadCodeAssist", json=body)
        if response.status_code >= 400:
            raise GeminiNativeProviderError(
                f"Gemini loadCodeAssist failed with status {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        project = payload.get("cloudaicompanionProject")
        if isinstance(project, str) and project.strip():
            return project.strip()
        current_tier = payload.get("currentTier")
        if isinstance(current_tier, dict) and current_tier.get("id"):
            return None

        onboard_response = await client.post(
            f"{self.base_url}/v1internal:onboardUser",
            json={
                "tierId": "free-tier",
                "metadata": {
                    "ideType": "IDE_UNSPECIFIED",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "GEMINI",
                },
            },
        )
        if onboard_response.status_code >= 400:
            raise GeminiNativeProviderError(
                f"Gemini onboardUser failed with status {onboard_response.status_code}: {onboard_response.text[:200]}"
            )
        onboard_payload = onboard_response.json()
        response_body = onboard_payload.get("response")
        if isinstance(response_body, dict):
            project = response_body.get("cloudaicompanionProject")
            if isinstance(project, str) and project.strip():
                return project.strip()
        return None

    async def _resolve_project_id(self, credentials: GeminiOAuthCredentials, client: httpx.AsyncClient, model: str) -> str:
        if self.project_id:
            return self.project_id
        if self._project_id_cache:
            return self._project_id_cache
        if credentials.project_id:
            self._project_id_cache = credentials.project_id
            return credentials.project_id
        project = self._project_from_projects_file()
        if project:
            self._project_id_cache = project
            return project
        if self.auto_discover_project:
            project = await self._load_code_assist_project(client, model)
            if project:
                self._project_id_cache = project
                return project
        raise GeminiNativeProviderError("Gemini Code Assist project id could not be resolved")

    def _request_body(self, request: ChatRequest, *, project_id: str) -> dict[str, Any]:
        contents, system_instruction = _build_gemini_contents(request.messages)
        inner: dict[str, Any] = {"contents": contents}
        if system_instruction is not None:
            inner["systemInstruction"] = system_instruction

        tools = _translate_tools_to_gemini(request.provider_options.get("tools"))
        if tools:
            inner["tools"] = tools
        tool_config = _translate_tool_choice_to_gemini(request.provider_options.get("tool_choice"))
        if tool_config is not None:
            inner["toolConfig"] = tool_config

        generation_config: dict[str, Any] = {}
        if isinstance(request.temperature, (int, float)):
            generation_config["temperature"] = float(request.temperature)
        if isinstance(request.max_tokens, int) and request.max_tokens > 0:
            generation_config["maxOutputTokens"] = request.max_tokens
        if isinstance(request.top_p, (int, float)):
            generation_config["topP"] = float(request.top_p)
        if isinstance(request.stop, str) and request.stop:
            generation_config["stopSequences"] = [request.stop]
        elif isinstance(request.stop, list) and request.stop:
            generation_config["stopSequences"] = [str(item) for item in request.stop if item]

        extra_body = request.provider_options.get("extra_body")
        thinking_config = None
        if isinstance(extra_body, dict):
            thinking_config = extra_body.get("thinking_config") or extra_body.get("thinkingConfig")
        thinking_config = thinking_config or request.provider_options.get("thinking_config") or request.provider_options.get("thinkingConfig")
        normalized_thinking = _normalize_thinking_config(thinking_config)
        if normalized_thinking is None and self.thinking_budget is not None:
            normalized_thinking = {"thinkingBudget": int(self.thinking_budget)}
        if normalized_thinking:
            generation_config["thinkingConfig"] = normalized_thinking
        if generation_config:
            inner["generationConfig"] = generation_config

        return {
            "project": project_id,
            "model": request.provider_model,
            "user_prompt_id": str(uuid.uuid4()),
            "request": inner,
        }

    @staticmethod
    def _unwrap_response(event: dict[str, Any]) -> dict[str, Any]:
        response = event.get("response")
        return response if isinstance(response, dict) else event

    @staticmethod
    def _parts_from_event(event: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, dict[str, Any] | None]:
        inner = GeminiNativeAdapter._unwrap_response(event)
        candidates = inner.get("candidates")
        usage = inner.get("usageMetadata") if isinstance(inner.get("usageMetadata"), dict) else None
        if not isinstance(candidates, list) or not candidates:
            return [], None, usage
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            return [], None, usage
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else []
        finish_reason = candidate.get("finishReason")
        return parts if isinstance(parts, list) else [], str(finish_reason) if finish_reason else None, usage

    @staticmethod
    async def _iter_sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
        async for line in response.aiter_lines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            raw_data = line.removeprefix("data:").strip()
            if not raw_data or raw_data == "[DONE]":
                continue
            try:
                event = json.loads(raw_data)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                yield event

    def _log_native_event(self, event: str, request: ChatRequest, *, mode: str, elapsed_since: float) -> None:
        log_gateway_event(
            event,
            request_id=request.request_id,
            provider=request.provider_name,
            model=f"{request.provider_name}:{request.provider_model}",
            mode=mode,
            elapsed_ms=elapsed_ms(elapsed_since),
        )

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        started_at = perf_counter()
        credentials = await self._credentials()
        response_id = f"gemini-native-{uuid.uuid4().hex[:12]}"
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        finish_reason = "stop"
        usage: dict[str, Any] | None = None
        first_output_logged = False

        async with self._client(credentials, accept="text/event-stream") as client:
            project_id = await self._resolve_project_id(credentials, client, request.provider_model)
            body = self._request_body(request, project_id=project_id)
            self._log_native_event("gateway.gemini_native.request", request, mode="chat", elapsed_since=started_at)
            async with client.stream(
                "POST",
                f"{self.base_url}/v1internal:streamGenerateContent?alt=sse",
                json=body,
            ) as response:
                if response.status_code >= 400:
                    error_text = await response.aread()
                    raise GeminiNativeProviderError(
                        f"Gemini native request failed with status {response.status_code}: {error_text[:200]!r}"
                    )
                async for event in self._iter_sse_events(response):
                    parts, raw_finish_reason, raw_usage = self._parts_from_event(event)
                    if raw_usage is not None:
                        usage = _usage_payload(raw_usage)
                    for part in parts:
                        if not isinstance(part, dict) or part.get("thought") is True:
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            if not first_output_logged:
                                self._log_native_event(
                                    "gateway.gemini_native.first_output",
                                    request,
                                    mode="chat",
                                    elapsed_since=started_at,
                                )
                                first_output_logged = True
                            text_parts.append(text)
                            continue
                        function_call = part.get("functionCall")
                        if isinstance(function_call, dict) and function_call.get("name"):
                            tool_calls.append(self._tool_call_payload(function_call))
                    if raw_finish_reason:
                        finish_reason = "tool_calls" if tool_calls else _map_finish_reason(raw_finish_reason)

        message: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
        if tool_calls:
            message["tool_calls"] = tool_calls
        self._log_native_event("gateway.gemini_native.complete", request, mode="chat", elapsed_since=started_at)
        return {
            "id": response_id,
            "object": "chat.completion",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            **({"usage": usage} if usage is not None else {}),
        }

    @staticmethod
    def _tool_call_payload(function_call: dict[str, Any]) -> dict[str, Any]:
        try:
            arguments = json.dumps(function_call.get("args") or {}, ensure_ascii=False)
        except (TypeError, ValueError):
            arguments = "{}"
        return {
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": str(function_call.get("name") or ""), "arguments": arguments},
        }

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        started_at = perf_counter()
        credentials = await self._credentials()
        response_id = f"gemini-native-{uuid.uuid4().hex[:12]}"
        finish_reason = "stop"
        usage: dict[str, Any] | None = None
        emitted_content = False
        emitted_tool_call = False

        async with self._client(credentials, accept="text/event-stream") as client:
            project_id = await self._resolve_project_id(credentials, client, request.provider_model)
            body = self._request_body(request, project_id=project_id)
            self._log_native_event("gateway.gemini_native.request", request, mode="stream", elapsed_since=started_at)
            async with client.stream(
                "POST",
                f"{self.base_url}/v1internal:streamGenerateContent?alt=sse",
                json=body,
            ) as response:
                if response.status_code >= 400:
                    error_text = await response.aread()
                    raise GeminiNativeProviderError(
                        f"Gemini native stream failed with status {response.status_code}: {error_text[:200]!r}"
                    )
                async for event in self._iter_sse_events(response):
                    parts, raw_finish_reason, raw_usage = self._parts_from_event(event)
                    if raw_usage is not None:
                        usage = _usage_payload(raw_usage)
                    for part in parts:
                        if not isinstance(part, dict) or part.get("thought") is True:
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            if not emitted_content:
                                self._log_native_event(
                                    "gateway.gemini_native.first_output",
                                    request,
                                    mode="stream",
                                    elapsed_since=started_at,
                                )
                                emitted_content = True
                            chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "model": f"{request.provider_name}:{request.provider_model}",
                                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                            }
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                            continue
                        function_call = part.get("functionCall")
                        if isinstance(function_call, dict) and function_call.get("name"):
                            emitted_tool_call = True
                            chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "model": f"{request.provider_name}:{request.provider_model}",
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"tool_calls": [{"index": 0, **self._tool_call_payload(function_call)}]},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    if raw_finish_reason:
                        finish_reason = "tool_calls" if emitted_tool_call else _map_finish_reason(raw_finish_reason)

        finish_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "model": f"{request.provider_name}:{request.provider_model}",
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            **({"usage": usage} if usage is not None else {}),
        }
        self._log_native_event("gateway.gemini_native.complete", request, mode="stream", elapsed_since=started_at)
        yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
