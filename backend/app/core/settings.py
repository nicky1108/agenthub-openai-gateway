from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    admin_secret: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./data/gateway.db"
    openai_gateway_host: str = "127.0.0.1"
    openai_gateway_port: int = 8787
    frontend_base_url: str = "http://127.0.0.1:3000"
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    @property
    def database_scheme(self) -> str:
        return self.database_url.split("://", 1)[0]

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(self.github_oauth_client_id and self.github_oauth_client_secret)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)
