from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProviderPresetDefinition:
    display_name: str
    default_slug: str
    default_base_url: str
    description: str
    slugs: tuple[str, ...]
    hostnames: tuple[str, ...]
    recommended_models: tuple[str, ...]
    protocols: tuple[str, ...] = ("openai",)


_PRESETS = (
    ProviderPresetDefinition(
        display_name="OpenAI API",
        default_slug="openai-api",
        default_base_url="https://api.openai.com/v1",
        description="OpenAI-compatible Chat Completions endpoint.",
        slugs=("openai-api", "openai-compatible"),
        hostnames=("api.openai.com",),
        recommended_models=("gpt-4.1", "gpt-4.1-mini", "gpt-4o"),
    ),
    ProviderPresetDefinition(
        display_name="DeepSeek",
        default_slug="deepseek",
        default_base_url="https://api.deepseek.com/v1",
        description="DeepSeek OpenAI-compatible API.",
        slugs=("deepseek",),
        hostnames=("api.deepseek.com",),
        recommended_models=("deepseek-chat", "deepseek-reasoner"),
    ),
    ProviderPresetDefinition(
        display_name="MiniMax",
        default_slug="minimax-cn",
        default_base_url="https://api.minimaxi.com/v1",
        description="MiniMax OpenAI-compatible API.",
        slugs=("minimax", "minimax-cn"),
        hostnames=("api.minimaxi.com", "api.minimax.io"),
        recommended_models=(
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
        ),
    ),
    ProviderPresetDefinition(
        display_name="Groq",
        default_slug="groq",
        default_base_url="https://api.groq.com/openai/v1",
        description="Groq OpenAI-compatible API.",
        slugs=("groq",),
        hostnames=("api.groq.com",),
        recommended_models=("llama-3.3-70b-versatile", "qwen-qwq-32b"),
    ),
    ProviderPresetDefinition(
        display_name="Together AI",
        default_slug="together",
        default_base_url="https://api.together.xyz/v1",
        description="Together OpenAI-compatible API.",
        slugs=("together",),
        hostnames=("api.together.xyz",),
        recommended_models=("meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3"),
    ),
    ProviderPresetDefinition(
        display_name="Fireworks AI",
        default_slug="fireworks",
        default_base_url="https://api.fireworks.ai/inference/v1",
        description="Fireworks OpenAI-compatible inference API.",
        slugs=("fireworks",),
        hostnames=("api.fireworks.ai",),
        recommended_models=("accounts/fireworks/models/llama-v3p1-70b-instruct", "accounts/fireworks/models/deepseek-v3"),
    ),
    ProviderPresetDefinition(
        display_name="OpenRouter",
        default_slug="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        description="OpenRouter OpenAI-compatible routing API.",
        slugs=("openrouter",),
        hostnames=("openrouter.ai",),
        recommended_models=("openai/gpt-4.1", "anthropic/claude-sonnet-4"),
    ),
    ProviderPresetDefinition(
        display_name="DashScope compatible mode",
        default_slug="dashscope",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="Alibaba Cloud DashScope OpenAI-compatible mode.",
        slugs=("dashscope", "qwen"),
        hostnames=("dashscope.aliyuncs.com",),
        recommended_models=("qwen-plus", "qwen-max", "qwen-turbo"),
    ),
    ProviderPresetDefinition(
        display_name="Anthropic",
        default_slug="claude",
        default_base_url="https://api.anthropic.com/v1",
        description="Anthropic Messages API.",
        slugs=("claude", "anthropic-api", "anthropic-compatible"),
        hostnames=("api.anthropic.com",),
        protocols=("anthropic",),
        recommended_models=(
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
        ),
    ),
)

_OTHER_OPENAI_COMPATIBLE = {
    "id": "other-openai-compatible",
    "display_name": "Other OpenAI-compatible",
    "slug": "custom-openai",
    "protocol": "openai",
    "base_url": "",
    "description": "Use this for any provider that exposes /v1/chat/completions.",
    "recommended_models": ["default"],
}


def list_provider_presets() -> list[dict[str, object]]:
    return [
        {
            "id": preset.default_slug,
            "display_name": preset.display_name,
            "slug": preset.default_slug,
            "protocol": preset.protocols[0],
            "base_url": preset.default_base_url,
            "description": preset.description,
            "recommended_models": list(preset.recommended_models),
        }
        for preset in _PRESETS
    ] + [_OTHER_OPENAI_COMPATIBLE]


def recommended_upstream_models(provider_slug: str, base_url: str, protocol: str = "openai") -> list[str]:
    slug = provider_slug.strip().lower()
    hostname = urlparse(base_url).hostname or ""
    for preset in _PRESETS:
        if slug in preset.slugs or hostname in preset.hostnames:
            return list(preset.recommended_models)
    if protocol == "anthropic":
        for preset in _PRESETS:
            if "anthropic" in preset.protocols:
                return list(preset.recommended_models)
    return ["default"]


def resolved_custom_provider_models(
    *,
    provider_slug: str,
    base_url: str,
    protocol: str = "openai",
    detected_models_json: str | None = None,
    preferred_model: str | None = None,
) -> list[str]:
    if detected_models_json:
        try:
            decoded = json.loads(detected_models_json)
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, list):
            detected = [item for item in decoded if isinstance(item, str) and item]
            if detected:
                if preferred_model and preferred_model in detected:
                    return [preferred_model, *[item for item in detected if item != preferred_model]]
                return detected

    recommended = recommended_upstream_models(provider_slug, base_url, protocol)
    if preferred_model and preferred_model in recommended:
        return [preferred_model, *[item for item in recommended if item != preferred_model]]
    return recommended
