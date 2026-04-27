from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: str = "development"
    admin_secret: str = "change-me"
    admin_emails_csv: str = ""
    secret_encryption_key: str | None = None
    cookie_secure: bool | None = None
    provider_url_strict_dns: bool | None = None
    auth_login_rate_limit_max_attempts: int = 5
    auth_login_rate_limit_window_seconds: int = 300
    auth_register_rate_limit_max_attempts: int = 100
    auth_register_rate_limit_window_seconds: int = 3600
    admin_cli_provider_management_enabled: bool = False
    admin_cli_provider_command_allowlist_csv: str = ""
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
    hermes_enabled: bool = False
    hermes_api_base: str = "http://127.0.0.1:8642/v1"
    hermes_api_key: str | None = None
    hermes_model: str = "hermes-agent"
    hermes_request_timeout_seconds: float = 60.0
    hermes_stream_read_timeout_seconds: float = 1800.0
    hermes_task_max_runtime_seconds: float = 7200.0
    hermes_task_start_credits: float = 10.0
    hermes_task_runtime_credits_per_minute: float = 1.0
    hermes_task_event_retention_days: int = 30
    hermes_max_concurrent_tasks: int = 2
    hermes_input_max_chars: int = 200_000
    hermes_metadata_max_bytes: int = 16_384
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
    reserved_provider_slugs_csv: str = "openai,codex,gemini,anthropic"

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    @property
    def database_scheme(self) -> str:
        return self.database_url.split("://", 1)[0]

    @property
    def reserved_provider_slugs(self) -> set[str]:
        return {item.strip() for item in self.reserved_provider_slugs_csv.split(",") if item.strip()}

    @property
    def admin_emails(self) -> set[str]:
        return {item.strip().lower() for item in self.admin_emails_csv.split(",") if item.strip()}

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(self.github_oauth_client_id and self.github_oauth_client_secret)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)

    @property
    def is_production(self) -> bool:
        return self.app_environment.strip().lower() in {"prod", "production"}

    @property
    def session_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production or self.frontend_base_url.strip().lower().startswith("https://")

    @property
    def require_provider_dns_resolution(self) -> bool:
        if self.provider_url_strict_dns is not None:
            return self.provider_url_strict_dns
        return self.is_production

    @property
    def admin_cli_provider_command_allowlist(self) -> set[str]:
        return {
            item.strip()
            for item in self.admin_cli_provider_command_allowlist_csv.split(",")
            if item.strip()
        }


def validate_secure_runtime_config(settings: Settings) -> None:
    if not settings.is_production:
        return
    if settings.admin_secret == "change-me":
        raise RuntimeError("ADMIN_SECRET must be configured for production")
    if settings.public_gateway_service_token == "public-gateway-token":
        raise RuntimeError("PUBLIC_GATEWAY_SERVICE_TOKEN must be configured for production")
    if not settings.secret_encryption_key or len(settings.secret_encryption_key) < 32:
        raise RuntimeError("SECRET_ENCRYPTION_KEY must be at least 32 characters for production")
    if (
        settings.admin_cli_provider_management_enabled
        and not settings.admin_cli_provider_command_allowlist
    ):
        raise RuntimeError(
            "ADMIN_CLI_PROVIDER_COMMAND_ALLOWLIST_CSV must be configured when CLI provider management is enabled"
        )
    if settings.hermes_enabled and not settings.hermes_api_key:
        raise RuntimeError("HERMES_API_KEY must be configured when HERMES_ENABLED=true")
