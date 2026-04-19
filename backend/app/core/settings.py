from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    admin_secret: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./data/gateway.db"
    openai_gateway_host: str = "127.0.0.1"
    openai_gateway_port: int = 8787

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")
