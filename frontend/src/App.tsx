import { type FormEvent, useEffect, useState } from "react";

import {
  createAccount,
  createApiKey,
  createProvider,
  getDashboardSummary,
  getCurrentAccount,
  getAccounts,
  getApiKeys,
  getHealth,
  getProviders,
  getUsageOverview,
  loginWithPassword,
  logoutSession,
  registerWithPassword,
} from "./api";
import type { Account, ApiKey, AuthAccount, Provider, ProviderHealth, UsageOverview } from "./api";

type DashboardSummary = Awaited<ReturnType<typeof getDashboardSummary>>;

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

export default function App() {
  const [authUser, setAuthUser] = useState<AuthAccount | null>(null);
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authName, setAuthName] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [usageOverview, setUsageOverview] = useState<UsageOverview | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [accountName, setAccountName] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [exposedModel, setExposedModel] = useState("default");
  const [routePolicy, setRoutePolicy] = useState("http-first");
  const [httpEnabled, setHttpEnabled] = useState(true);
  const [cliEnabled, setCliEnabled] = useState(false);
  const [httpBaseUrl, setHttpBaseUrl] = useState("");
  const [cliCommand, setCliCommand] = useState("");
  const [chatCapable, setChatCapable] = useState(true);
  const [streamCapable, setStreamCapable] = useState(true);

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
  }

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
    setName("");
    setExposedModel("default");
    setRoutePolicy("http-first");
    setHttpEnabled(true);
    setCliEnabled(false);
    setHttpBaseUrl("");
    setCliCommand("");
    setChatCapable(true);
    setStreamCapable(true);
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
          <a href="#dashboard">Dashboard</a>
          <a href="#providers">Providers</a>
          <a href="#models">Models</a>
          <a href="#accounts">Accounts</a>
          <a href="#api-keys">API Keys</a>
          <a href="#usage">Usage</a>
          <a href="#settings">Settings</a>
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
        <div className="page-body">
          <section id="dashboard" className="dashboard">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Overview</span>
                <h2>Platform Overview</h2>
              </div>
              <div className="status-pill">24h default</div>
            </div>
            {dashboardError ? (
              <p role="alert">Dashboard unavailable: {dashboardError}</p>
            ) : null}
            <div
              className="kpi-grid"
            >
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
                  {account.name} - {account.status}
                </li>
              ))}
            </ul>
          </section>

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
                <select
                  value={selectedAccountId}
                  onChange={(event) => setSelectedAccountId(event.target.value)}
                >
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
              <button type="submit">Create API Key</button>
            </form>

            {createdApiKey ? <p>Last Created Key: {createdApiKey}</p> : null}

            <ul>
              {apiKeys.map((apiKey) => (
                <li key={apiKey.id}>
                  {apiKey.name} - {apiKey.key_prefix} - {apiKey.status}
                </li>
              ))}
            </ul>
          </section>

          <section id="providers">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Runtime</span>
                <h2>Provider Registry</h2>
              </div>
            </div>
            <form onSubmit={handleSubmit}>
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
              <label>
                HTTP Enabled
                <input
                  type="checkbox"
                  checked={httpEnabled}
                  onChange={(event) => setHttpEnabled(event.target.checked)}
                />
              </label>
              <label>
                CLI Enabled
                <input
                  type="checkbox"
                  checked={cliEnabled}
                  onChange={(event) => setCliEnabled(event.target.checked)}
                />
              </label>
              <label>
                HTTP Base URL
                <input
                  required={httpEnabled}
                  value={httpBaseUrl}
                  onChange={(event) => setHttpBaseUrl(event.target.value)}
                />
              </label>
              <label>
                CLI Command
                <input
                  required={cliEnabled}
                  value={cliCommand}
                  onChange={(event) => setCliCommand(event.target.value)}
                />
              </label>
              <label>
                Chat Capable
                <input
                  type="checkbox"
                  checked={chatCapable}
                  onChange={(event) => setChatCapable(event.target.checked)}
                />
              </label>
              <label>
                Stream Capable
                <input
                  type="checkbox"
                  checked={streamCapable}
                  onChange={(event) => setStreamCapable(event.target.checked)}
                />
              </label>
              <button type="submit">Add Provider</button>
            </form>

            <ul>
              {providers.map((provider) => (
                <li key={provider.id}>
                  {provider.name} - {provider.exposed_model} - {provider.route_policy} - http:
                  {String(provider.http_enabled)} - cli:{String(provider.cli_enabled)}
                </li>
              ))}
            </ul>
          </section>

          <section id="models">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Status</span>
                <h2>Provider Health</h2>
              </div>
            </div>
            <ul>
              {health.map((item) => (
                <li key={item.name}>
                  {item.name} - http:{String(item.capabilities.http)} - cli:{String(item.capabilities.cli)}
                </li>
              ))}
            </ul>
          </section>

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
          <section id="settings">
            <div className="section-header">
              <div>
                <span className="section-eyebrow">Configuration</span>
                <h2>Platform Settings</h2>
              </div>
            </div>
            <p>Settings navigation is reserved in the shell while the current admin forms continue to handle configuration.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
