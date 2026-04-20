import { type FormEvent, useEffect, useState } from "react";

import { createAccount, createApiKey, createProvider, getAccounts, getApiKeys, getHealth, getProviders } from "./api";
import type { Account, ApiKey, Provider, ProviderHealth } from "./api";

type DashboardSummary = {
  total_requests: number;
  active_api_keys: number;
  error_rate: number;
  rate_limit_hits: number;
};

async function getDashboardSummary(): Promise<DashboardSummary> {
  const response = await fetch("/admin/dashboard/summary", {
    headers: {
      "content-type": "application/json",
      "x-admin-secret": "change-me",
    },
  });

  if (!response.ok) {
    throw new Error(`dashboard summary failed: ${response.status}`);
  }

  const payload = (await response.json()) as Partial<DashboardSummary>;
  return {
    total_requests: payload.total_requests ?? 0,
    active_api_keys: payload.active_api_keys ?? 0,
    error_rate: payload.error_rate ?? 0,
    rate_limit_hits: payload.rate_limit_hits ?? 0,
  };
}

export default function App() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<DashboardSummary | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
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

  useEffect(() => {
    void Promise.all([getAccounts(), getApiKeys(), getProviders(), getHealth(), getDashboardSummary()])
      .then(([accountRows, keyRows, providerRows, healthRows, dashboard]) => {
        setAccounts(accountRows);
        setApiKeys(keyRows);
        setProviders(providerRows);
        setHealth(healthRows);
        setDashboardSummary(dashboard);
        setDashboardError(null);
        if (accountRows.length > 0) {
          setSelectedAccountId(String(accountRows[0].id));
        }
      })
      .catch((error: unknown) => {
        setDashboardSummary(null);
        setDashboardError(error instanceof Error ? error.message : "dashboard unavailable");
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

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <h1>AgentHub</h1>
        <nav>
          <a href="#dashboard">Dashboard</a>
          <a href="#providers">Providers</a>
          <a href="#models">Models</a>
          <a href="#accounts">Accounts</a>
          <a href="#api-keys">API Keys</a>
          <a href="#usage">Usage</a>
          <a href="#settings">Settings</a>
        </nav>
      </aside>
      <section className="content">
        <header className="topbar">
          <div>Developer Platform</div>
          <div>Signed in</div>
        </header>
        <div className="page-body">
          <section id="dashboard" className="dashboard">
            <h2>Platform Overview</h2>
            {dashboardError ? (
              <p role="alert">Dashboard unavailable: {dashboardError}</p>
            ) : null}
            <div
              className="kpi-grid"
              style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}
            >
              <div className="kpi-card" style={{ border: "1px solid #d1d5db", borderRadius: "12px", padding: "1rem" }}>
                <strong>Requests</strong>
                <div>{dashboardSummary?.total_requests ?? "—"}</div>
              </div>
              <div className="kpi-card" style={{ border: "1px solid #d1d5db", borderRadius: "12px", padding: "1rem" }}>
                <strong>Active Keys</strong>
                <div>{dashboardSummary?.active_api_keys ?? "—"}</div>
              </div>
              <div className="kpi-card" style={{ border: "1px solid #d1d5db", borderRadius: "12px", padding: "1rem" }}>
                <strong>Error Rate</strong>
                <div>{dashboardSummary ? `${(dashboardSummary.error_rate * 100).toFixed(1)}%` : "—"}</div>
              </div>
              <div className="kpi-card" style={{ border: "1px solid #d1d5db", borderRadius: "12px", padding: "1rem" }}>
                <strong>Rate Limit Hits</strong>
                <div>{dashboardSummary?.rate_limit_hits ?? "—"}</div>
              </div>
            </div>
            <div
              className="hero-chart"
              style={{
                marginTop: "1rem",
                border: "1px dashed #9ca3af",
                borderRadius: "16px",
                minHeight: "180px",
                display: "grid",
                placeItems: "center",
                color: "#4b5563",
              }}
            >
              24h / 7d traffic chart placeholder
            </div>
          </section>

          <section id="accounts">
            <h2>Account Management</h2>
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
            <h2>Key Management</h2>
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
            <h2>Provider Registry</h2>
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
            <h2>Provider Health</h2>
            <ul>
              {health.map((item) => (
                <li key={item.name}>
                  {item.name} - http:{String(item.capabilities.http)} - cli:{String(item.capabilities.cli)}
                </li>
              ))}
            </ul>
          </section>

          <section id="usage">
            <h2>Gateway Logs</h2>
            <p>
              Request logs land in the backend first. Keep the frontend read-only here until log
              pagination exists.
            </p>
          </section>
          <section id="settings">
            <h2>Platform Settings</h2>
            <p>Settings navigation is reserved in the shell while the current admin forms continue to handle configuration.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
