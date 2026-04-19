from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProviderRecord(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    http_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cli_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    route_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="http-first")
