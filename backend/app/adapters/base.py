from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChatRequest:
    provider_name: str
    provider_model: str
    messages: list[dict[str, Any]]
    stream: bool
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)
