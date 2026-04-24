from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ModelPricingRecord


@dataclass(frozen=True, slots=True)
class PricingSnapshot:
    provider_name: str
    native_model: str
    source_url: str
    source_label: str
    source_kind: str = "official_snapshot"
    currency: str = "USD"
    unit: str = "1M tokens"
    input_price: float | None = None
    cached_input_price: float | None = None
    output_price: float | None = None
    input_price_high: float | None = None
    cached_input_price_high: float | None = None
    output_price_high: float | None = None
    high_price_threshold_tokens: int | None = None
    notes: str | None = None


class OfficialPricingService:
    _OPENAI_FLAGSHIP_SOURCE = "https://openai.com/api/pricing/"
    _OPENAI_MODEL_DOCS_BASE = "https://developers.openai.com/api/docs/models"
    _GEMINI_SOURCE = "https://ai.google.dev/pricing"

    _SNAPSHOTS: tuple[PricingSnapshot, ...] = (
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.5",
            source_url=_OPENAI_FLAGSHIP_SOURCE,
            source_label="OpenAI API Pricing",
            input_price=5.00,
            cached_input_price=0.50,
            output_price=30.00,
            notes="Listed as GPT-5.5 coming soon on the official OpenAI API pricing page.",
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.4",
            source_url=_OPENAI_FLAGSHIP_SOURCE,
            source_label="OpenAI API Pricing",
            input_price=2.50,
            cached_input_price=0.25,
            output_price=15.00,
            input_price_high=5.00,
            cached_input_price_high=0.50,
            output_price_high=22.50,
            high_price_threshold_tokens=270000,
            notes="Standard pricing. Higher short-context price applies above 270k context.",
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.4-mini",
            source_url=_OPENAI_FLAGSHIP_SOURCE,
            source_label="OpenAI API Pricing",
            input_price=0.75,
            cached_input_price=0.075,
            output_price=4.50,
            input_price_high=1.50,
            cached_input_price_high=0.15,
            output_price_high=6.75,
            high_price_threshold_tokens=270000,
            notes="Standard pricing. Higher short-context price applies above 270k context.",
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.4-nano",
            source_url=_OPENAI_FLAGSHIP_SOURCE,
            source_label="OpenAI API Pricing",
            input_price=0.20,
            cached_input_price=0.02,
            output_price=1.25,
            input_price_high=0.40,
            cached_input_price_high=0.04,
            output_price_high=1.80,
            high_price_threshold_tokens=270000,
            notes="Standard pricing. Higher short-context price applies above 270k context.",
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5-codex",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5-codex",
            source_label="OpenAI Model Pricing",
            input_price=1.25,
            cached_input_price=0.125,
            output_price=10.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.3-codex",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5.3-codex",
            source_label="OpenAI Model Pricing",
            input_price=1.75,
            cached_input_price=0.175,
            output_price=14.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.2",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5.2",
            source_label="OpenAI Model Pricing",
            input_price=1.75,
            cached_input_price=0.175,
            output_price=14.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.2-codex",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5.2-codex",
            source_label="OpenAI Model Pricing",
            input_price=1.75,
            cached_input_price=0.175,
            output_price=14.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.1-codex",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5.1-codex",
            source_label="OpenAI Model Pricing",
            input_price=1.25,
            cached_input_price=0.125,
            output_price=10.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.1-codex-mini",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5.1-codex-mini",
            source_label="OpenAI Model Pricing",
            input_price=0.25,
            cached_input_price=0.025,
            output_price=2.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="gpt-5.1-codex-max",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/gpt-5.1-codex-max",
            source_label="OpenAI Model Pricing",
            input_price=1.25,
            cached_input_price=0.125,
            output_price=10.00,
        ),
        PricingSnapshot(
            provider_name="codex",
            native_model="codex-mini-latest",
            source_url=f"{_OPENAI_MODEL_DOCS_BASE}/codex-mini-latest",
            source_label="OpenAI Model Pricing",
            input_price=1.50,
            cached_input_price=0.375,
            output_price=6.00,
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-2.5-pro",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            input_price=1.25,
            cached_input_price=0.125,
            output_price=10.00,
            input_price_high=2.50,
            cached_input_price_high=0.25,
            output_price_high=15.00,
            high_price_threshold_tokens=200000,
            notes="Standard pricing for text/image/video. Audio pricing differs.",
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-2.5-flash",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            input_price=0.30,
            cached_input_price=0.03,
            output_price=2.50,
            notes="Standard pricing for text/image/video. Audio pricing differs.",
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-2.5-flash-lite",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            input_price=0.10,
            cached_input_price=0.01,
            output_price=0.40,
            notes="Standard pricing for Gemini 2.5 Flash-Lite text/image/video requests.",
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-2.0-flash",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            input_price=0.10,
            cached_input_price=0.025,
            output_price=0.40,
            notes="Standard pricing for text/image/video. Audio and image-generation pricing differ.",
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-2.0-flash-lite",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            input_price=0.075,
            output_price=0.30,
            notes="Standard pricing from the official Gemini pricing page.",
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-3-pro-preview",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            input_price=2.00,
            cached_input_price=0.20,
            output_price=12.00,
            input_price_high=4.00,
            cached_input_price_high=0.40,
            output_price_high=18.00,
            high_price_threshold_tokens=200000,
            notes="Standard pricing for Gemini 3 Pro Preview.",
        ),
        PricingSnapshot(
            provider_name="gemini",
            native_model="gemini-3.1-pro-preview",
            source_url=_GEMINI_SOURCE,
            source_label="Gemini Developer API Pricing",
            notes="This model is not listed with a dedicated official API price snapshot on the Gemini pricing page.",
        ),
    )

    def snapshots_for_provider(self, provider_name: str) -> list[PricingSnapshot]:
        return [snapshot for snapshot in self._SNAPSHOTS if snapshot.provider_name == provider_name]

    async def sync_provider_pricing(self, session: AsyncSession, provider_name: str) -> list[ModelPricingRecord]:
        snapshots = self.snapshots_for_provider(provider_name)
        existing = await session.scalars(
            select(ModelPricingRecord).where(ModelPricingRecord.provider_name == provider_name)
        )
        existing_by_model = {row.native_model: row for row in existing}
        synced_at = datetime.now(timezone.utc)

        for snapshot in snapshots:
            row = existing_by_model.get(snapshot.native_model)
            if row is None:
                session.add(
                    ModelPricingRecord(
                        provider_name=snapshot.provider_name,
                        native_model=snapshot.native_model,
                        source_kind=snapshot.source_kind,
                        source_url=snapshot.source_url,
                        source_label=snapshot.source_label,
                        currency=snapshot.currency,
                        unit=snapshot.unit,
                        input_price=snapshot.input_price,
                        cached_input_price=snapshot.cached_input_price,
                        output_price=snapshot.output_price,
                        input_price_high=snapshot.input_price_high,
                        cached_input_price_high=snapshot.cached_input_price_high,
                        output_price_high=snapshot.output_price_high,
                        high_price_threshold_tokens=snapshot.high_price_threshold_tokens,
                        notes=snapshot.notes,
                        synced_at=synced_at,
                    )
                )
                continue

            if row.source_kind == "manual_override":
                continue

            row.source_kind = snapshot.source_kind
            row.source_url = snapshot.source_url
            row.source_label = snapshot.source_label
            row.currency = snapshot.currency
            row.unit = snapshot.unit
            row.input_price = snapshot.input_price
            row.cached_input_price = snapshot.cached_input_price
            row.output_price = snapshot.output_price
            row.input_price_high = snapshot.input_price_high
            row.cached_input_price_high = snapshot.cached_input_price_high
            row.output_price_high = snapshot.output_price_high
            row.high_price_threshold_tokens = snapshot.high_price_threshold_tokens
            row.notes = snapshot.notes
            row.synced_at = synced_at

        await session.commit()
        rows = await session.scalars(
            select(ModelPricingRecord)
            .where(ModelPricingRecord.provider_name == provider_name)
            .order_by(ModelPricingRecord.native_model.asc())
        )
        return list(rows)
