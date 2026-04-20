import { type FormEvent, useEffect, useState } from "react";

import {
  createAccount,
  createApiKey,
  createProviderModel,
  createProvider,
  getDashboardSummary,
  getCurrentAccount,
  getAccounts,
  getApiKeys,
  getHealth,
  getProviderModels,
  getProviders,
  getUsageOverview,
  loginWithPassword,
  patchProviderModel,
  revokeApiKey,
  rediscoverProviderModels,
  logoutSession,
  registerWithPassword,
} from "./api";
import type { Account, ApiKey, AuthAccount, Provider, ProviderHealth, ProviderModel, UsageOverview } from "./api";

type DashboardSummary = Awaited<ReturnType<typeof getDashboardSummary>>;
type RouteId = "dashboard" | "providers" | "models" | "accounts" | "api-keys" | "usage" | "settings";

const NAV_ITEMS: Array<{ id: RouteId; label: string }> = [
  { id: "dashboard", label: "Dashboard" },
  { id: "providers", label: "Providers" },
  { id: "models", label: "Models" },
  { id: "accounts", label: "Accounts" },
  { id: "api-keys", label: "API Keys" },
  { id: "usage", label: "Usage" },
  { id: "settings", label: "Settings" },
];

function getRouteFromHash(hash: string): RouteId {
  const value = hash.replace(/^#/, "");
  if (NAV_ITEMS.some((item) => item.id === value)) {
    return value as RouteId;
  }
  return "dashboard";
}

function aggregateUsage(
  usageSummary: UsageOverview | null,
  field: "by_provider" | "by_model",
): Array<[string, number]> {
  if (!usageSummary) {
    return [];
  }
  return Object.entries(usageSummary[field]).sort((left, right) => right[1] - left[1]);
}

function formatLastUsed(lastUsedAt: string | null): string {
  if (!lastUsedAt) {
    return "No activity yet";
  }

  return new Date(lastUsedAt).toLocaleString();
}

function formatProviderState(health: ProviderHealth | undefined): string {
  if (!health) {
    return "Awaiting probe";
  }
  if (health.capabilities.http || health.capabilities.cli) {
    return "Healthy";
  }
  return "Offline";
}

export default function App() {
  const [authUser, setAuthUser] = useState<AuthAccount | null>(null);
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [currentRoute, setCurrentRoute] = useState<RouteId>(() => getRouteFromHash(window.location.hash));

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [usageOverview, setUsageOverview] = useState<UsageOverview | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerModels, setProviderModels] = useState<Record<string, ProviderModel[]>>({});
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);

  const [accountName, setAccountName] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);
  const [keyPerMinute, setKeyPerMinute] = useState("");
  const [keyPerHour, setKeyPerHour] = useState("");
  const [keyPerDay, setKeyPerDay] = useState("");
  const [name, setName] = useState("");
  const [exposedModel, setExposedModel] = useState("default");
  const [routePolicy, setRoutePolicy] = useState("http-first");
  const [httpEnabled, setHttpEnabled] = useState(true);
  const [cliEnabled, setCliEnabled] = useState(false);
  const [httpBaseUrl, setHttpBaseUrl] = useState("");
  const [cliCommand, setCliCommand] = useState("");
  const [chatCapable, setChatCapable] = useState(true);
  const [streamCapable, setStreamCapable] = useState(true);
  const [selectedProviderName, setSelectedProviderName] = useState("");
  const [manualNativeModel, setManualNativeModel] = useState("");
  const [manualExposedModelId, setManualExposedModelId] = useState("");

  async function loadAuthenticatedData() {
    const [accountRows, keyRows, providerRows, healthRows, dashboard, usage] = await Promise.all([
      getAccounts(),
      getApiKeys(),
      getProviders(),
      getHealth(),
      getDashboardSummary(),
      getUsageOverview(),
    ]);

    setAccounts(accountRows);
    setApiKeys(keyRows);
    setUsageOverview(usage);
    setProviders(providerRows);
    setHealth(healthRows);
    setDashboardSummary(dashboard);
    setDashboardError(null);
    setUsageError(null);
    if (accountRows.length > 0) {
      setSelectedAccountId(String(accountRows[0].id));
    }
    if (providerRows.length > 0) {
      const defaultProvider = providerRows[0].name;
      setSelectedProviderName(defaultProvider);
      const models = await getProviderModels(defaultProvider);
      setProviderModels((current) => ({ ...current, [defaultProvider]: models }));
    }
  }

  useEffect(() => {
    const syncRoute = () => {
      setCurrentRoute(getRouteFromHash(window.location.hash));
    };

    if (!window.location.hash) {
      window.location.hash = "#dashboard";
      syncRoute();
    }

    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  useEffect(() => {
    void getCurrentAccount()
      .then(async (account) => {
        setAuthUser(account);
        setAuthState("authenticated");
        setAuthError(null);
        await loadAuthenticatedData();
      })
      .catch(() => {
        setAuthUser(null);
        setAuthState("unauthenticated");
      });
  }, []);

  async function handleAccountSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createAccount({ name: accountName });
    setAccounts((current) => current.concat(created));
    setSelectedAccountId(String(created.id));
    setAccountName("");
  }

  async function handleApiKeySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createApiKey({
      account_id: Number(selectedAccountId),
      name: apiKeyName,
      per_minute: keyPerMinute ? Number(keyPerMinute) : null,
      per_hour: keyPerHour ? Number(keyPerHour) : null,
      per_day: keyPerDay ? Number(keyPerDay) : null,
    });
    setApiKeys((current) => current.concat(created));
    setUsageOverview((current) => ({
      key_activity: [
        ...(current?.key_activity ?? []),
        {
          api_key_id: created.id,
          account_id: created.account_id,
          name: created.name,
          key_prefix: created.key_prefix,
          status: created.status,
          last_used_at: created.last_used_at,
          total_requests: 0,
          limited_requests: 0,
        },
      ],
      by_provider: current?.by_provider ?? {},
      by_model: current?.by_model ?? {},
    }));
    setCreatedApiKey(created.api_key);
    setApiKeyName("");
    setKeyPerMinute("");
    setKeyPerHour("");
    setKeyPerDay("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createProvider({
      name,
      exposed_model: exposedModel,
      route_policy: routePolicy,
      http_enabled: httpEnabled,
      cli_enabled: cliEnabled,
      chat_capable: chatCapable,
      stream_capable: streamCapable,
      http_base_url: httpEnabled ? httpBaseUrl : null,
      http_headers_json: "{}",
      cli_command: cliEnabled ? cliCommand : null,
      cli_args_json: "[]",
      cli_env_json: "{}",
    });
    setProviders((current) => current.concat(created));
    setSelectedProviderName(created.name);
    setName("");
    setExposedModel("default");
    setRoutePolicy("http-first");
    setHttpEnabled(true);
    setCliEnabled(false);
    setHttpBaseUrl("");
    setCliCommand("");
    setChatCapable(true);
    setStreamCapable(true);
    const models = await getProviderModels(created.name);
    setProviderModels((current) => ({ ...current, [created.name]: models }));
  }

  async function loadSelectedProviderModels(providerName: string) {
    const rows = await getProviderModels(providerName);
    setProviderModels((current) => ({ ...current, [providerName]: rows }));
  }

  async function handleRediscoverModels(providerNameOverride?: string) {
    const providerName = providerNameOverride ?? selectedProviderName;
    if (!providerName) return;
    const rows = await rediscoverProviderModels(providerName);
    setProviderModels((current) => ({ ...current, [providerName]: rows }));
  }

  async function handleOpenProviderModels(providerName: string) {
    setSelectedProviderName(providerName);
    await loadSelectedProviderModels(providerName);
    window.location.hash = "#models";
    setCurrentRoute("models");
  }

  async function handleToggleProviderModel(nativeModel: string, enabled: boolean) {
    if (!selectedProviderName) return;
    const updated = await patchProviderModel(selectedProviderName, nativeModel, { enabled: !enabled });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) =>
        row.native_model === nativeModel ? updated : row,
      ),
    }));
  }

  async function handleRenameProviderModel(nativeModel: string, exposedModelId: string) {
    if (!selectedProviderName) return;
    const updated = await patchProviderModel(selectedProviderName, nativeModel, {
      exposed_model_id: exposedModelId,
    });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: (current[selectedProviderName] ?? []).map((row) =>
        row.native_model === nativeModel ? updated : row,
      ),
    }));
  }

  async function handleManualModelSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProviderName) return;
    const created = await createProviderModel(selectedProviderName, {
      native_model: manualNativeModel,
      exposed_model_id: manualExposedModelId,
      enabled: true,
    });
    setProviderModels((current) => ({
      ...current,
      [selectedProviderName]: [...(current[selectedProviderName] ?? []), created],
    }));
    setManualNativeModel("");
    setManualExposedModelId("");
  }

  async function handleRevokeKey(keyId: number) {
    const revoked = await revokeApiKey(keyId);
    setApiKeys((current) => current.map((row) => (row.id === keyId ? revoked : row)));
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const account =
        authMode === "login"
          ? await loginWithPassword({ email: authEmail, password: authPassword })
          : await registerWithPassword({ name: authName, email: authEmail, password: authPassword });
      setAuthUser(account);
      setAuthState("authenticated");
      setAuthError(null);
      if (authMode === "register") {
        const loginAccount = await loginWithPassword({ email: authEmail, password: authPassword });
        setAuthUser(loginAccount);
      }
      await loadAuthenticatedData();
      setAuthPassword("");
      setCurrentRoute(getRouteFromHash(window.location.hash));
    } catch (error: unknown) {
      setAuthError(error instanceof Error ? error.message : "authentication failed");
    }
  }

  async function handleLogout() {
    await logoutSession();
    setAuthUser(null);
    setAuthState("unauthenticated");
    setAccounts([]);
    setApiKeys([]);
    setUsageOverview(null);
    setProviders([]);
    setHealth([]);
    setDashboardSummary(null);
  }

  const recentKeyActivity = [...(usageOverview?.key_activity ?? [])].sort((left, right) => {
    const leftTime = left.last_used_at ? new Date(left.last_used_at).getTime() : 0;
    const rightTime = right.last_used_at ? new Date(right.last_used_at).getTime() : 0;
    return rightTime - leftTime || right.total_requests - left.total_requests;
  });
  const providerActivity = aggregateUsage(usageOverview, "by_provider").slice(0, 5);
  const modelActivity = aggregateUsage(usageOverview, "by_model").slice(0, 5);
  const selectedProviderModels = selectedProviderName ? (providerModels[selectedProviderName] ?? []) : [];
  const providerHealthByName = new Map(health.map((entry) => [entry.name, entry]));
  const totalProviders = providers.length;
  const httpProviders = providers.filter((provider) => provider.http_enabled).length;
  const cliProviders = providers.filter((provider) => provider.cli_enabled).length;
  const streamingProviders = providers.filter((provider) => provider.stream_capable).length;

  function renderCurrentPage() {
    switch (currentRoute) {
      case "dashboard":
        return (
          <section id="dashboard" className="dashboard">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Overview</span>
                <h2>Platform Overview</h2>
              </div>
              <div className="status-pill">24h default</div>
            </div>
            {dashboardError ? <p role="alert">Dashboard unavailable: {dashboardError}</p> : null}
            <div className="kpi-grid">
              <div className="kpi-card">
                <strong>Requests</strong>
                <span className="kpi-subtitle">Gateway traffic volume</span>
                <div>{dashboardSummary?.total_requests ?? "—"}</div>
              </div>
              <div className="kpi-card">
                <strong>Active Keys</strong>
                <span className="kpi-subtitle">Live access credentials</span>
                <div>{dashboardSummary?.active_api_keys ?? "—"}</div>
              </div>
              <div className="kpi-card">
                <strong>Error Rate</strong>
                <span className="kpi-subtitle">Failed request ratio</span>
                <div>{dashboardSummary ? `${(dashboardSummary.error_rate * 100).toFixed(1)}%` : "—"}</div>
              </div>
              <div className="kpi-card">
                <strong>Rate Limit Hits</strong>
                <span className="kpi-subtitle">Quota pressure</span>
                <div>{dashboardSummary?.rate_limit_hits ?? "—"}</div>
              </div>
            </div>
            <div className="hero-chart">
              <div className="chart-header">
                <div>
                  <strong>Traffic</strong>
                  <p>24h / 7d runtime activity</p>
                </div>
                <div className="chart-toggle">
                  <button type="button" className="chart-toggle-active">
                    24h
                  </button>
                  <button type="button">7d</button>
                </div>
              </div>
              <svg viewBox="0 0 600 180" className="chart-svg" aria-hidden="true">
                <defs>
                  <linearGradient id="traffic-fill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="rgba(102,210,255,0.35)" />
                    <stop offset="100%" stopColor="rgba(102,210,255,0)" />
                  </linearGradient>
                </defs>
                <path
                  d="M0 160 C40 120, 70 126, 95 98 S160 55, 205 84 285 145, 320 108 375 42, 438 70 515 132, 600 48"
                  fill="none"
                  stroke="rgba(102,210,255,0.96)"
                  strokeWidth="4"
                  strokeLinecap="round"
                />
                <path
                  d="M0 160 C40 120, 70 126, 95 98 S160 55, 205 84 285 145, 320 108 375 42, 438 70 515 132, 600 48 L600 180 L0 180 Z"
                  fill="url(#traffic-fill)"
                />
              </svg>
            </div>
          </section>
        );
      case "accounts":
        return (
          <section id="accounts">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Identity</span>
                <h2>Account Management</h2>
              </div>
            </div>
            <form onSubmit={handleAccountSubmit}>
              <label>
                Account Name
                <input value={accountName} onChange={(event) => setAccountName(event.target.value)} />
              </label>
              <button type="submit">Add Account</button>
            </form>
            <ul>
              {accounts.map((account) => (
                <li key={account.id}>
                  <strong>{account.name}</strong>
                  <div className="usage-meta">{account.status}</div>
                  {account.notes ? <div className="usage-meta">{account.notes}</div> : null}
                </li>
              ))}
            </ul>
          </section>
        );
      case "api-keys":
        return (
          <section id="api-keys">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Access</span>
                <h2>Key Management</h2>
              </div>
            </div>
            <form onSubmit={handleApiKeySubmit}>
              <label>
                Account
                <select value={selectedAccountId} onChange={(event) => setSelectedAccountId(event.target.value)}>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                API Key Name
                <input value={apiKeyName} onChange={(event) => setApiKeyName(event.target.value)} />
              </label>
              <label>
                Per Minute
                <input value={keyPerMinute} onChange={(event) => setKeyPerMinute(event.target.value)} />
              </label>
              <label>
                Per Hour
                <input value={keyPerHour} onChange={(event) => setKeyPerHour(event.target.value)} />
              </label>
              <label>
                Per Day
                <input value={keyPerDay} onChange={(event) => setKeyPerDay(event.target.value)} />
              </label>
              <button type="submit">Create API Key</button>
            </form>
            {createdApiKey ? <p>Last Created Key: {createdApiKey}</p> : null}
            <ul>
              {apiKeys.map((apiKey) => (
                <li key={apiKey.id}>
                  <strong>{apiKey.name}</strong>
                  <div className="usage-meta">{apiKey.key_prefix} · {apiKey.status}</div>
                  <div className="usage-meta">
                    {apiKey.per_minute ?? "—"}/min · {apiKey.per_hour ?? "—"}/hr · {apiKey.per_day ?? "—"}/day
                  </div>
                  <button type="button" onClick={() => handleRevokeKey(apiKey.id)}>
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      case "providers":
        return (
          <section id="providers" className="providers-page">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Runtime</span>
                <h2>Provider Registry</h2>
                <p>Control transport policy, health posture, and model entry points for every upstream runtime.</p>
              </div>
            </div>
            <div className="provider-summary-grid">
              <article className="provider-summary-card">
                <span className="provider-summary-label">Runtime coverage</span>
                <strong>{totalProviders}</strong>
                <p>Total configured providers in the gateway registry.</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">OpenAI-compatible HTTP</span>
                <strong>{httpProviders}</strong>
                <p>Providers currently able to route through HTTP transport.</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">CLI runtimes</span>
                <strong>{cliProviders}</strong>
                <p>Providers available through local command execution.</p>
              </article>
              <article className="provider-summary-card">
                <span className="provider-summary-label">Streaming ready</span>
                <strong>{streamingProviders}</strong>
                <p>Providers marked as stream-capable from the control plane.</p>
              </article>
            </div>
            <div className="provider-layout">
              <div className="provider-panel provider-registry-panel">
                <div className="provider-panel-header">
                  <div>
                    <span className="section-eyebrow">Registry</span>
                    <h3>Active providers</h3>
                  </div>
                </div>
                <div className="provider-card-grid">
                  {providers.map((provider) => {
                    const providerHealth = providerHealthByName.get(provider.name);
                    const providerModelsCount = providerModels[provider.name]?.length ?? 0;

                    return (
                      <article key={provider.id} className="provider-card">
                        <div className="provider-card-topline">
                          <span
                            className={
                              formatProviderState(providerHealth) === "Healthy"
                                ? "provider-status provider-status--healthy"
                                : "provider-status"
                            }
                          >
                            {formatProviderState(providerHealth)}
                          </span>
                          <span className="provider-route-pill">{provider.route_policy}</span>
                        </div>
                        <h3>{provider.name}</h3>
                        <p>Primary exposed model: {provider.exposed_model}</p>
                        <div className="provider-chip-row">
                          {provider.http_enabled ? <span className="provider-chip">OpenAI-compatible HTTP</span> : null}
                          {provider.cli_enabled ? <span className="provider-chip">CLI runtime</span> : null}
                          {provider.chat_capable ? <span className="provider-chip">Chat capable</span> : null}
                          {provider.stream_capable ? <span className="provider-chip">Streaming</span> : null}
                        </div>
                        <div className="provider-detail-list">
                          <div>
                            <span>HTTP base</span>
                            <strong>{provider.http_base_url ?? "Not configured"}</strong>
                          </div>
                          <div>
                            <span>CLI command</span>
                            <strong>{provider.cli_command ?? "Not configured"}</strong>
                          </div>
                          <div>
                            <span>Model catalog</span>
                            <strong>{providerModelsCount > 0 ? `${providerModelsCount} loaded` : "Open catalog"}</strong>
                          </div>
                        </div>
                        <div className="inline-actions">
                          <button type="button" onClick={() => void handleOpenProviderModels(provider.name)}>
                            View models
                          </button>
                          <button type="button" onClick={() => void handleRediscoverModels(provider.name)}>
                            Rediscover
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </div>
              <aside className="provider-panel provider-compose-panel">
                <div className="provider-panel-header">
                  <div>
                    <span className="section-eyebrow">Compose</span>
                    <h3>Register provider</h3>
                  </div>
                  <p>Add a new upstream and decide which transport the gateway should prefer.</p>
                </div>
                <form onSubmit={handleSubmit} className="provider-form">
                  <label>
                    Provider Name
                    <input value={name} onChange={(event) => setName(event.target.value)} />
                  </label>
                  <label>
                    Exposed Model
                    <input value={exposedModel} onChange={(event) => setExposedModel(event.target.value)} />
                  </label>
                  <label>
                    Route Policy
                    <select value={routePolicy} onChange={(event) => setRoutePolicy(event.target.value)}>
                      <option value="http-first">http-first</option>
                      <option value="cli-first">cli-first</option>
                      <option value="fixed-http">fixed-http</option>
                      <option value="fixed-cli">fixed-cli</option>
                    </select>
                  </label>
                  <label className="checkbox-field">
                    <span>HTTP Enabled</span>
                    <input
                      type="checkbox"
                      checked={httpEnabled}
                      onChange={(event) => setHttpEnabled(event.target.checked)}
                    />
                  </label>
                  <label className="checkbox-field">
                    <span>CLI Enabled</span>
                    <input type="checkbox" checked={cliEnabled} onChange={(event) => setCliEnabled(event.target.checked)} />
                  </label>
                  <label>
                    HTTP Base URL
                    <input required={httpEnabled} value={httpBaseUrl} onChange={(event) => setHttpBaseUrl(event.target.value)} />
                  </label>
                  <label>
                    CLI Command
                    <input required={cliEnabled} value={cliCommand} onChange={(event) => setCliCommand(event.target.value)} />
                  </label>
                  <label className="checkbox-field">
                    <span>Chat Capable</span>
                    <input
                      type="checkbox"
                      checked={chatCapable}
                      onChange={(event) => setChatCapable(event.target.checked)}
                    />
                  </label>
                  <label className="checkbox-field">
                    <span>Stream Capable</span>
                    <input
                      type="checkbox"
                      checked={streamCapable}
                      onChange={(event) => setStreamCapable(event.target.checked)}
                    />
                  </label>
                  <button type="submit">Add Provider</button>
                </form>
              </aside>
            </div>
          </section>
        );
      case "models":
        return (
          <section id="models">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Catalog</span>
                <h2>Models</h2>
              </div>
              <button type="button" onClick={() => void handleRediscoverModels()}>
                Rediscover
              </button>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void loadSelectedProviderModels(selectedProviderName);
              }}
            >
              <label>
                Provider
                <select
                  value={selectedProviderName}
                  onChange={(event) => {
                    setSelectedProviderName(event.target.value);
                    void loadSelectedProviderModels(event.target.value);
                  }}
                >
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.name}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </label>
            </form>
            <ul>
              {selectedProviderModels.map((model) => (
                <li key={model.id}>
                  <strong>{model.native_model}</strong>
                  <div className="usage-meta">{model.source}</div>
                  <div className="usage-meta">Exposed as {model.exposed_model_id}</div>
                  <div className="inline-actions">
                    <button type="button" onClick={() => handleToggleProviderModel(model.native_model, model.enabled)}>
                      {model.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleRenameProviderModel(model.native_model, `${selectedProviderName}:${model.native_model}-alt`)
                      }
                    >
                      Rename
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <form onSubmit={handleManualModelSubmit}>
              <label>
                Native Model
                <input value={manualNativeModel} onChange={(event) => setManualNativeModel(event.target.value)} />
              </label>
              <label>
                Exposed Model ID
                <input
                  value={manualExposedModelId}
                  onChange={(event) => setManualExposedModelId(event.target.value)}
                />
              </label>
              <button type="submit">Add Manual Model</button>
            </form>
          </section>
        );
      case "usage":
        return (
          <section id="usage">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Activity</span>
                <h2>Usage</h2>
              </div>
            </div>
            {usageError ? <p role="alert">Usage unavailable: {usageError}</p> : null}
            <div className="split">
              <div className="panel">
                <h3>Recent key activity</h3>
                {recentKeyActivity.length === 0 ? (
                  <p>No API keys yet.</p>
                ) : (
                  <ul>
                    {recentKeyActivity.map((apiKey) => (
                      <li key={apiKey.api_key_id}>
                        <strong>{apiKey.name}</strong>
                        <div className="usage-meta">{apiKey.key_prefix} · {apiKey.status}</div>
                        <div className="usage-stats">
                          {apiKey.total_requests} requests · {apiKey.limited_requests} limited
                        </div>
                        <div className="usage-meta">Last used {formatLastUsed(apiKey.last_used_at)}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="panel">
                <h3>Top providers / models</h3>
                <p>
                  Providers:{" "}
                  {providerActivity.length === 0
                    ? "No attributed usage yet."
                    : providerActivity.map(([name, count]) => `${name} (${count})`).join(", ")}
                </p>
                <p>
                  Models:{" "}
                  {modelActivity.length === 0
                    ? "No model activity yet."
                    : modelActivity.map(([name, count]) => `${name} (${count})`).join(", ")}
                </p>
              </div>
            </div>
          </section>
        );
      case "settings":
        return (
          <section id="settings">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Configuration</span>
                <h2>Platform Settings</h2>
              </div>
            </div>
            <p>Settings navigation is reserved in the shell while the current admin forms continue to handle configuration.</p>
          </section>
        );
      default:
        return null;
    }
  }

  if (authState === "loading") {
    return (
      <main className="auth-shell">
        <section id="auth-loading" className="auth-card auth-card--loading">
          <div className="auth-brand-lockup">
            <div className="auth-brand-mark">AG</div>
            <div>
              <h1>AgentHub</h1>
              <p className="auth-kicker">Gateway control plane</p>
            </div>
          </div>
          <p>Checking session…</p>
        </section>
      </main>
    );
  }

  if (authState === "unauthenticated") {
    return (
      <main className="auth-shell">
        <section id="auth" className="auth-card">
          <div className="auth-split">
            <div className="auth-copy">
              <div className="auth-brand-lockup">
                <div className="auth-brand-mark">AG</div>
                <div>
                  <h1>AgentHub</h1>
                  <p className="auth-kicker">Gateway control plane</p>
                </div>
              </div>
              <h2>{authMode === "login" ? "Sign in to your platform" : "Create your operator account"}</h2>
              <p>
                Manage providers, keys, model catalogs, quotas, and traffic from one dark developer
                console.
              </p>
              <ul className="auth-feature-list">
                <li>Track request volume, key activity, and rate-limit hits</li>
                <li>Control HTTP and CLI providers from the same shell</li>
                <li>Keep OpenAI-compatible access behind managed API keys</li>
              </ul>
            </div>
            <div className="auth-form-panel">
              <div className="auth-form-header">
                <span className="auth-eyebrow">{authMode === "login" ? "Primary access" : "Create workspace access"}</span>
                <h3>{authMode === "login" ? "Email sign in" : "Register with email"}</h3>
              </div>
              {authError ? <p role="alert">Authentication failed: {authError}</p> : null}
              <form className="auth-form" onSubmit={handleAuthSubmit}>
                {authMode === "register" ? (
                  <label className="auth-field">
                    <span className="auth-label">Name</span>
                    <input value={authName} onChange={(event) => setAuthName(event.target.value)} />
                  </label>
                ) : null}
                <label className="auth-field">
                  <span className="auth-label">Email</span>
                  <input value={authEmail} onChange={(event) => setAuthEmail(event.target.value)} />
                </label>
                <label className="auth-field">
                  <span className="auth-label">Password</span>
                  <input
                    type="password"
                    value={authPassword}
                    onChange={(event) => setAuthPassword(event.target.value)}
                  />
                </label>
                <button className="auth-submit" type="submit">
                  {authMode === "login" ? "Sign In" : "Create Account"}
                </button>
              </form>
              <div className="auth-toggle-group">
                <button
                  className={authMode === "login" ? "auth-secondary auth-secondary--active" : "auth-secondary"}
                  type="button"
                  onClick={() => setAuthMode("login")}
                >
                  Use Email Login
                </button>
                <button
                  className={authMode === "register" ? "auth-secondary auth-secondary--active" : "auth-secondary"}
                  type="button"
                  onClick={() => setAuthMode("register")}
                >
                  Create Account
                </button>
              </div>
              <div className="auth-social-group">
                <button className="auth-social-button" type="button">
                  Continue with GitHub
                </button>
                <button className="auth-social-button" type="button">
                  Continue with Google
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-mark">AG</div>
          <div>
            <h1>AgentHub</h1>
            <p>Developer Platform</p>
          </div>
        </div>
        <div className="sidebar-section-label">Navigation</div>
        <nav>
          {NAV_ITEMS.map((item) => (
            <a key={item.id} href={`#${item.id}`} aria-current={currentRoute === item.id ? "page" : undefined}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="sidebar-footer-label">Runtime</span>
          <strong>OpenAI-compatible gateway</strong>
        </div>
      </aside>
      <section className="content">
        <header className="topbar">
          <div className="topbar-title-group">
            <span className="topbar-eyebrow">Developer Platform</span>
            <strong>Gateway operations</strong>
          </div>
          <div className="topbar-user">
            <span className="topbar-user-email">{authUser?.email ?? "Signed in"}</span>
            <button className="topbar-logout" type="button" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        </header>
        <div className="page-body">{renderCurrentPage()}</div>
      </section>
    </main>
  );
}
