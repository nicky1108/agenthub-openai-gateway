from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext
from app.core.models import AccountRecord, CreditLedgerRecord, ModelPricingRecord, UsageRecord


def estimate_text_tokens(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / 4))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += 4
        total += estimate_text_tokens(str(message.get("content", "")))
    return total


def extract_assistant_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        return ""
    return str(message.get("content", ""))


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    token_source: str


@dataclass(frozen=True, slots=True)
class ChargeQuote:
    pricing: ModelPricingRecord
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_credits_ceiling: float


class CreditBillingService:
    CREDITS_PER_USD = 100
    CREDIT_QUANTUM = Decimal("0.01")

    @classmethod
    def _decimal(cls, value: float | int | str | Decimal) -> Decimal:
        return value if isinstance(value, Decimal) else Decimal(str(value))

    @classmethod
    def _round_credits(cls, value: float | Decimal) -> float:
        return float(cls._decimal(value).quantize(cls.CREDIT_QUANTUM, rounding=ROUND_HALF_UP))

    @classmethod
    def _round_credits_up(cls, value: float | Decimal) -> float:
        return float(cls._decimal(value).quantize(cls.CREDIT_QUANTUM, rounding=ROUND_UP))

    async def get_pricing(self, session: AsyncSession, provider_name: str, native_model: str) -> ModelPricingRecord:
        pricing = await session.scalar(
            select(ModelPricingRecord).where(
                ModelPricingRecord.provider_name == provider_name,
                ModelPricingRecord.native_model == native_model,
            )
        )
        if pricing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该模型暂无可用价格，请先配置定价",
            )
        return pricing

    async def quote_request(
        self,
        session: AsyncSession,
        account: AccountRecord,
        provider_name: str,
        native_model: str,
        messages: list[dict[str, Any]],
        max_tokens: int | None,
    ) -> ChargeQuote:
        pricing = await self.get_pricing(session, provider_name, native_model)
        estimated_input_tokens = estimate_messages_tokens(messages)
        estimated_output_tokens = max_tokens if max_tokens is not None else max(estimated_input_tokens, 1024)
        estimated_credits_ceiling = self.credits_for_usage(
            pricing=pricing,
            input_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens,
            cached_input_tokens=0,
        )
        if estimated_credits_ceiling <= 0:
            estimated_credits_ceiling = 0.01
        if account.credit_balance < estimated_credits_ceiling:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="余额不足，请充值",
            )
        return ChargeQuote(
            pricing=pricing,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_credits_ceiling=estimated_credits_ceiling,
        )

    def usage_from_result(
        self,
        request_messages: list[dict[str, Any]],
        response_payload: dict[str, Any],
    ) -> UsageSnapshot:
        usage = response_payload.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            cached_tokens = 0
            prompt_details = usage.get("prompt_tokens_details")
            if isinstance(prompt_details, dict):
                cached_tokens = int(prompt_details.get("cached_tokens") or 0)
            return UsageSnapshot(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_tokens,
                token_source="provider_usage",
            )

        output_text = extract_assistant_text(response_payload)
        return UsageSnapshot(
            input_tokens=estimate_messages_tokens(request_messages),
            output_tokens=estimate_text_tokens(output_text),
            cached_input_tokens=0,
            token_source="estimated",
        )

    def usage_from_stream(
        self,
        request_messages: list[dict[str, Any]],
        assistant_text: str,
        usage_payload: dict[str, Any] | None,
    ) -> UsageSnapshot:
        if isinstance(usage_payload, dict):
            prompt_tokens = int(usage_payload.get("prompt_tokens") or 0)
            completion_tokens = int(usage_payload.get("completion_tokens") or 0)
            cached_tokens = 0
            prompt_details = usage_payload.get("prompt_tokens_details")
            if isinstance(prompt_details, dict):
                cached_tokens = int(prompt_details.get("cached_tokens") or 0)
            return UsageSnapshot(
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_tokens,
                token_source="provider_usage",
            )

        return UsageSnapshot(
            input_tokens=estimate_messages_tokens(request_messages),
            output_tokens=estimate_text_tokens(assistant_text),
            cached_input_tokens=0,
            token_source="estimated",
        )

    def usd_for_usage(
        self,
        *,
        pricing: ModelPricingRecord,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int,
    ) -> float:
        billable_input_tokens = max(input_tokens - cached_input_tokens, 0)
        high_tier = (
            pricing.high_price_threshold_tokens is not None
            and input_tokens > pricing.high_price_threshold_tokens
        )
        input_price = pricing.input_price_high if high_tier and pricing.input_price_high is not None else pricing.input_price
        cached_input_price = (
            pricing.cached_input_price_high
            if high_tier and pricing.cached_input_price_high is not None
            else pricing.cached_input_price
        )
        output_price = pricing.output_price_high if high_tier and pricing.output_price_high is not None else pricing.output_price

        usd_total = Decimal("0")
        if input_price is not None:
            usd_total += (Decimal(billable_input_tokens) / Decimal("1000000")) * self._decimal(input_price)
        if cached_input_price is not None:
            usd_total += (Decimal(cached_input_tokens) / Decimal("1000000")) * self._decimal(cached_input_price)
        if output_price is not None:
            usd_total += (Decimal(output_tokens) / Decimal("1000000")) * self._decimal(output_price)
        return float(usd_total)

    def credits_for_usage(
        self,
        *,
        pricing: ModelPricingRecord,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int,
    ) -> float:
        usd_total = self.usd_for_usage(
            pricing=pricing,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        if usd_total <= 0:
            return 0.0
        return max(
            0.01,
            self._round_credits_up(self._decimal(usd_total) * self._decimal(self.CREDITS_PER_USD)),
        )

    async def settle_inference(
        self,
        session: AsyncSession,
        context: AuthContext,
        provider_name: str,
        model_id: str,
        pricing: ModelPricingRecord,
        usage: UsageSnapshot,
        notes: str | None = None,
    ) -> UsageRecord:
        usd_amount = self.usd_for_usage(
            pricing=pricing,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
        )
        credits_charged = self.credits_for_usage(
            pricing=pricing,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
        )

        context.account.credit_balance = self._round_credits(context.account.credit_balance - credits_charged)
        context.api_key.last_used_at = datetime.now(timezone.utc)

        usage_row = UsageRecord(
            account_id=context.account.id,
            api_key_id=context.api_key.id,
            provider_name=provider_name,
            model_id=model_id,
            outcome="success",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            usd_amount=usd_amount,
            credits_charged=credits_charged,
            pricing_source=pricing.source_kind,
            token_source=usage.token_source,
        )
        session.add(usage_row)
        await session.flush()

        ledger_row = CreditLedgerRecord(
            account_id=context.account.id,
            api_key_id=context.api_key.id,
            usage_record_id=usage_row.id,
            entry_type="model_inference",
            credits_delta=-credits_charged,
            balance_after=context.account.credit_balance,
            usd_amount=usd_amount,
            provider_name=provider_name,
            model_id=model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            pricing_source=pricing.source_kind,
            notes=notes,
        )
        session.add(ledger_row)
        await session.commit()
        await session.refresh(usage_row)
        return usage_row

    async def record_manual_adjustment(
        self,
        session: AsyncSession,
        account: AccountRecord,
        credits_delta: float,
        notes: str | None,
    ) -> CreditLedgerRecord:
        account.credit_balance = self._round_credits(account.credit_balance + credits_delta)
        ledger_row = CreditLedgerRecord(
            account_id=account.id,
            api_key_id=None,
            usage_record_id=None,
            entry_type="manual_adjustment",
            credits_delta=credits_delta,
            balance_after=account.credit_balance,
            notes=notes,
        )
        session.add(ledger_row)
        await session.commit()
        await session.refresh(ledger_row)
        return ledger_row


billing_service = CreditBillingService()
