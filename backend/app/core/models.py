from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProviderRecord(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    exposed_model: Mapped[str] = mapped_column(String(200), default="default", nullable=False)
    http_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cli_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    route_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="http-first")
    chat_capable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stream_capable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    http_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    http_api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    http_headers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    cli_command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cli_args_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    cli_env_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    cli_cwd: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ProviderModelRecord(Base):
    __tablename__ = "provider_models"
    __table_args__ = (UniqueConstraint("provider_id", "native_model", name="uq_provider_models_native"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False, index=True)
    native_model: Mapped[str] = mapped_column(String(200), nullable=False)
    exposed_model_id: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    manually_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ModelPricingRecord(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (UniqueConstraint("provider_name", "native_model", name="uq_model_pricing_provider_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    native_model: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="official_snapshot")
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="1M tokens")
    input_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    cached_input_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_price_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    cached_input_price_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_price_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price_threshold_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AccountRecord(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    oauth_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    public_workspace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    public_api_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), nullable=False, index=True)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usd_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    credits_charged: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pricing_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    token_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class CreditLedgerRecord(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True, index=True)
    usage_record_id: Mapped[int | None] = mapped_column(ForeignKey("usage_records.id"), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    credits_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    usd_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pricing_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
