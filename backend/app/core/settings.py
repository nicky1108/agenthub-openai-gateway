from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    admin_secret: str = "change-me"
    codex_native_enabled: bool = True
    codex_native_auth_file: str = "~/.codex/auth.json"
    codex_native_base_url: str = "https://chatgpt.com/backend-api/codex"
    codex_native_timeout_seconds: float = 120.0
    codex_native_token_refresh_skew_seconds: int = 120
    codex_native_reasoning_effort: str | None = "low"
    codex_models_cache_file: str | None = "~/.codex/models_cache.json"
    gemini_native_enabled: bool = True
    gemini_native_auth_file: str = "~/.gemini/oauth_creds.json"
    gemini_native_base_url: str = "https://cloudcode-pa.googleapis.com"
    gemini_native_timeout_seconds: float = 120.0
    gemini_native_token_refresh_skew_seconds: int = 120
    gemini_native_project_id: str | None = None
    gemini_native_projects_file: str = "~/.gemini/projects.json"
    gemini_native_auto_discover_project: bool = True
    gemini_native_refresh_enabled: bool = True
    gemini_native_thinking_budget: int | None = 0
    gemini_native_oauth_client_id: str | None = None
    gemini_native_oauth_client_secret: str | None = None
    gemini_acp_enabled: bool = False
    gemini_acp_pool_size: int = 1
    gemini_acp_prewarm_enabled: bool = True
    provider_cli_runtime_dir: str = "./data/provider-cwd"
    provider_cli_bootstrap_workspaces: bool = True
    public_gateway_service_token: str = "public-gateway-token"
    public_gateway_tunnel_url: str | None = None
    public_gateway_tunnel_reconnect_base_seconds: float = 1.0
    public_gateway_tunnel_reconnect_max_seconds: float = 15.0
    database_url: str = "sqlite+aiosqlite:///./data/gateway.db"
    openai_gateway_host: str = "127.0.0.1"
    openai_gateway_port: int = 8787
    frontend_base_url: str = "http://127.0.0.1:3000"
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    public_gateway_tunnel_device_id: str | None = None
    public_gateway_tunnel_secret: str | None = None

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
