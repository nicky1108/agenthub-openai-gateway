from sqlalchemy import Boolean, Integer, String, Text
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
