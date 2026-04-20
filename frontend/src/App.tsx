import { type FormEvent, useEffect, useState } from "react";

import { createAccount, createApiKey, createProvider, getAccounts, getApiKeys, getHealth, getProviders } from "./api";
import type { Account, ApiKey, Provider, ProviderHealth } from "./api";

export default function App() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [health, setHealth] = useState<ProviderHealth[]>([]);
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
    void Promise.all([getAccounts(), getApiKeys(), getProviders(), getHealth()]).then(
      ([accountRows, keyRows, providerRows, healthRows]) => {
        setAccounts(accountRows);
        setApiKeys(keyRows);
        setProviders(providerRows);
        setHealth(healthRows);
        if (accountRows.length > 0) {
          setSelectedAccountId(String(accountRows[0].id));
        }
      },
    );
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
          <section id="dashboard">
            <h2>Platform Overview</h2>
            <p>The runtime dashboard will land here next while the existing admin tools stay available inside the shell.</p>
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
