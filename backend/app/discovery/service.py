from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ProviderModelRecord, ProviderRecord
from app.core.settings import Settings
from app.pricing.service import OfficialPricingService


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    native_model: str
    source: str


class ProviderDiscoveryService:
    _pricing = OfficialPricingService()
    _CODEX_BOOTSTRAP_MODELS = (
        "gpt-5.5",
        "gpt-5-codex",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5.3-codex",
        "gpt-5.2",
        "gpt-5.2-codex",
        "gpt-5.1-codex",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex-max",
        "codex-mini-latest",
    )
    _GEMINI_BOOTSTRAP_MODELS = (
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3-pro-preview",
    )

    @staticmethod
    def _merge_model_names(*groups: tuple[str, ...] | list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for model in group:
                if model in seen:
                    continue
                seen.add(model)
                ordered.append(model)
        return ordered

    @staticmethod
    def _codex_models_from_cache() -> list[str]:
        cache_file = Settings().codex_models_cache_file
        if not cache_file:
            return []
        path = Path(cache_file).expanduser()
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return []

        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug") or item.get("id") or item.get("model")
            if not isinstance(slug, str) or not slug.strip():
                continue
            if item.get("visibility") not in {None, "list"}:
                continue
            if item.get("supported_in_api") is False:
                continue
            names.append(slug.strip())
        return names

    def discover_models(self, provider: ProviderRecord) -> list[DiscoveredModel]:
        if provider.name == "codex":
            model_names = self._merge_model_names(
                self._codex_models_from_cache(),
                self._CODEX_BOOTSTRAP_MODELS,
                [snapshot.native_model for snapshot in self._pricing.snapshots_for_provider("codex")],
            )
            return [DiscoveredModel(native_model=model, source="bootstrap") for model in model_names]
        if provider.name == "gemini":
            model_names = self._merge_model_names(
                self._GEMINI_BOOTSTRAP_MODELS,
                [snapshot.native_model for snapshot in self._pricing.snapshots_for_provider("gemini")],
            )
            return [DiscoveredModel(native_model=model, source="bootstrap") for model in model_names]
        return [DiscoveredModel(native_model=provider.exposed_model, source="provider-default")]

    async def sync_provider_models(
        self,
        session: AsyncSession,
        provider: ProviderRecord,
    ) -> list[ProviderModelRecord]:
        discovered = self.discover_models(provider)
        existing_rows = await session.scalars(
            select(ProviderModelRecord).where(ProviderModelRecord.provider_id == provider.id)
        )
        existing_by_native = {row.native_model: row for row in existing_rows}
        now = datetime.utcnow()

        for item in discovered:
            row = existing_by_native.get(item.native_model)
            if row is None:
                session.add(
                    ProviderModelRecord(
                        provider_id=provider.id,
                        native_model=item.native_model,
                        exposed_model_id=f"{provider.name}:{item.native_model}",
                        source=item.source,
                        enabled=True,
                        manually_overridden=False,
                        last_seen_at=now,
                    )
                )
                continue

            row.source = item.source
            row.last_seen_at = now
            if not row.manually_overridden:
                row.enabled = True
                row.exposed_model_id = f"{provider.name}:{item.native_model}"

        await session.commit()
        rows = await session.scalars(
            select(ProviderModelRecord)
            .where(ProviderModelRecord.provider_id == provider.id)
            .order_by(ProviderModelRecord.native_model.asc())
        )
        return list(rows)
