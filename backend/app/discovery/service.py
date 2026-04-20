from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ProviderModelRecord, ProviderRecord


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    native_model: str
    source: str


class ProviderDiscoveryService:
    _CODEX_BOOTSTRAP_MODELS = (
        "gpt-5-codex",
        "gpt-5.3-codex",
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
        "gemini-3-pro-preview",
    )

    def discover_models(self, provider: ProviderRecord) -> list[DiscoveredModel]:
        if provider.name == "codex":
            return [DiscoveredModel(native_model=model, source="bootstrap") for model in self._CODEX_BOOTSTRAP_MODELS]
        if provider.name == "gemini":
            return [DiscoveredModel(native_model=model, source="bootstrap") for model in self._GEMINI_BOOTSTRAP_MODELS]
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
