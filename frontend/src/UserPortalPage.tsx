import { type FormEvent, useEffect, useState } from "react";

import {
  createUserApiKey,
  createUserProvider,
  deleteUserApiKey,
  deleteUserProvider,
  getPortalCatalog,
  getPortalDashboard,
  getProviderPresets,
  getUserApiKeys,
  getUserProviders,
  probeUserProvider,
} from "./api";
import type { PortalCatalog, PortalDashboard, ProviderPreset, UserApiKey, UserProvider } from "./api";

type LoadState = "loading" | "ready" | "error";
type ModelTab = "custom" | "platform";

function formatNullableDate(value: string | null): string {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function formatCompactNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value ?? 0);
}

function probeLabel(provider: UserProvider): string {
  if (provider.last_probe_ok === true) {
    return `verified: ${provider.last_probe_model ?? "model detected"}`;
  }
  if (provider.last_probe_ok === false) {
    return provider.last_probe_detail ? `failed: ${provider.last_probe_detail}` : "probe failed";
  }
  return "not probed";
}

function probeTone(provider: UserProvider): string {
  if (provider.last_probe_ok === true) return "ok";
  if (provider.last_probe_ok === false) return "danger";
  return "idle";
}

function resolveApiBaseUrl(): string {
  if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
    return "http://127.0.0.1:8787/v1";
  }
  return `${window.location.origin}/v1`;
}

function chatCurlExample(apiBaseUrl: string, apiKey: string, modelId: string): string {
  return [
    `curl ${apiBaseUrl}/chat/completions \\`,
    `  -H "Authorization: Bearer ${apiKey}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"model":"${modelId}","messages":[{"role":"user","content":"Reply with only OK"}],"stream":false}'`,
  ].join("\n");
}

function sdkExample(apiBaseUrl: string, apiKey: string, modelId: string): string {
  return [
    `import OpenAI from "openai";`,
    ``,
    `const client = new OpenAI({`,
    `  apiKey: "${apiKey}",`,
    `  baseURL: "${apiBaseUrl}",`,
    `});`,
    ``,
    `const response = await client.chat.completions.create({`,
    `  model: "${modelId}",`,
    `  messages: [{ role: "user", content: "Reply with only OK" }],`,
    `});`,
  ].join("\n");
}

function protocolLabel(protocol: string): string {
  return protocol === "anthropic" ? "Anthropic Messages" : "OpenAI-compatible";
}

export function UserPortalPage() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<PortalDashboard | null>(null);
  const [catalog, setCatalog] = useState<PortalCatalog | null>(null);
  const [keys, setKeys] = useState<UserApiKey[]>([]);
  const [providers, setProviders] = useState<UserProvider[]>([]);
  const [providerPresets, setProviderPresets] = useState<ProviderPreset[]>([]);
  const [keyName, setKeyName] = useState("production");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [selectedPresetId, setSelectedPresetId] = useState("minimax-cn");
  const [providerName, setProviderName] = useState("minimax-cn");
  const [providerProtocol, setProviderProtocol] = useState("openai");
  const [providerBaseUrl, setProviderBaseUrl] = useState("https://api.minimaxi.com/v1");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [modelTab, setModelTab] = useState<ModelTab>("custom");
  const [modelQuery, setModelQuery] = useState("");

  async function loadPortalData() {
    setLoadState("loading");
    setError(null);
    try {
      const [dashboardPayload, catalogPayload, keyRows, providerRows, presets] = await Promise.all([
        getPortalDashboard(),
        getPortalCatalog(),
        getUserApiKeys(),
        getUserProviders(),
        getProviderPresets(),
      ]);
      setDashboard(dashboardPayload);
      setCatalog(catalogPayload);
      setKeys(keyRows);
      setProviders(providerRows);
      setProviderPresets(presets);
      setLoadState("ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "portal unavailable");
      setLoadState("error");
    }
  }

  useEffect(() => {
    void loadPortalData();
  }, []);

  async function handleCreateKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    try {
      const created = await createUserApiKey({ name: keyName });
      setCreatedKey(created.api_key);
      setKeys((current) => current.concat(created));
      setKeyName("production");
      const nextDashboard = await getPortalDashboard();
      setDashboard(nextDashboard);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "failed to create key");
    }
  }

  async function handleDeleteKey(keyId: number) {
    setActionError(null);
    try {
      await deleteUserApiKey(keyId);
      setKeys((current) => current.map((key) => (key.id === keyId ? { ...key, status: "revoked" } : key)));
      const nextDashboard = await getPortalDashboard();
      setDashboard(nextDashboard);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "failed to revoke key");
    }
  }

  async function handleCreateProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    try {
      const created = await createUserProvider({
        name: providerName,
        protocol: providerProtocol,
        base_url: providerBaseUrl,
        api_key: providerApiKey,
      });
      setProviders((current) => current.concat(created));
      setProviderApiKey("");
      setModelTab("custom");
      const [nextDashboard, nextCatalog] = await Promise.all([getPortalDashboard(), getPortalCatalog()]);
      setDashboard(nextDashboard);
      setCatalog(nextCatalog);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "failed to add provider");
    }
  }

  function handleSelectProviderPreset(presetId: string) {
    setSelectedPresetId(presetId);
    const preset = providerPresets.find((item) => item.id === presetId);
    if (!preset) return;
    setProviderName(preset.slug);
    setProviderProtocol(preset.protocol);
    setProviderBaseUrl(preset.base_url);
  }

  const markProviderEdited = () => setSelectedPresetId("manual");

  async function handleProbeProvider(providerId: number) {
    setActionError(null);
    try {
      const updated = await probeUserProvider(providerId);
      setProviders((current) => current.map((provider) => (provider.id === providerId ? updated : provider)));
      const nextCatalog = await getPortalCatalog();
      setCatalog(nextCatalog);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "failed to probe provider");
    }
  }

  async function handleDeleteProvider(providerId: number) {
    setActionError(null);
    try {
      await deleteUserProvider(providerId);
      setProviders((current) => current.filter((provider) => provider.id !== providerId));
      const [nextDashboard, nextCatalog] = await Promise.all([getPortalDashboard(), getPortalCatalog()]);
      setDashboard(nextDashboard);
      setCatalog(nextCatalog);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "failed to delete provider");
    }
  }

  if (loadState === "loading") {
    return (
      <section className="portal-console portal-console--loading">
        <div className="portal-loading-orb" />
        <span>Loading your gateway console...</span>
      </section>
    );
  }

  if (loadState === "error") {
    return (
      <section className="portal-console portal-error-state">
        <span className="section-eyebrow">Customer Portal</span>
        <h2>Portal unavailable</h2>
        <p role="alert">{error}</p>
        <button type="button" onClick={() => void loadPortalData()}>Retry</button>
      </section>
    );
  }

  const activeKeys = keys.filter((key) => key.status === "active");
  const customModelIds = catalog?.custom_models.map((model) => model.id) ?? [];
  const platformModelIds = catalog?.platform_models.map((model) => model.id) ?? [];
  const selectedPreset = providerPresets.find((preset) => preset.id === selectedPresetId);
  const apiBaseUrl = resolveApiBaseUrl();
  const exampleApiKey = createdKey ?? (activeKeys[0] ? `${activeKeys[0].key_prefix}...` : "<API_KEY>");
  const exampleModelId = customModelIds[0] ?? platformModelIds[0] ?? "codex:gpt-5.4";
  const selectedModels = modelTab === "custom" ? customModelIds : platformModelIds;
  const visibleModels = selectedModels.filter((modelId) => modelId.toLowerCase().includes(modelQuery.toLowerCase()));
  const topPresets = providerPresets.slice(0, 8);
  const readySteps = [
    { label: "Create API key", ready: activeKeys.length > 0 },
    { label: "Add provider", ready: providers.length > 0 },
    { label: "Probe models", ready: customModelIds.length > 0 },
    { label: "Call /v1", ready: (dashboard?.request_count_24h ?? 0) > 0 },
  ];

  return (
    <section id="portal" className="portal-console">
      <div className="portal-hero-card">
        <div className="portal-hero-copy">
          <span className="section-eyebrow">Customer Gateway Console</span>
          <h2>User Portal</h2>
          <p>
            Manage your AgentHub API keys, connect your own model providers, inspect available models,
            and copy production-ready OpenAI-compatible request examples from one place.
          </p>
          <div className="portal-hero-actions">
            <a href="#portal-provider-studio">Add provider</a>
            <a href="#portal-api-example">View API example</a>
            <button type="button" onClick={() => void loadPortalData()}>Refresh data</button>
          </div>
        </div>
        <div className="portal-hero-terminal">
          <span>Base URL</span>
          <strong>{apiBaseUrl}</strong>
          <small>Works with OpenAI SDK compatible clients.</small>
        </div>
      </div>

      {actionError ? <p className="portal-alert" role="alert">{actionError}</p> : null}
      {createdKey ? (
        <div className="portal-secret portal-secret--wide">
          <div>
            <strong>New API key created</strong>
            <span>Copy it now. It will not be shown again.</span>
          </div>
          <code>{createdKey}</code>
        </div>
      ) : null}

      <div className="portal-stat-grid">
        <article>
          <span>Balance</span>
          <strong>{formatCompactNumber(dashboard?.credits_balance)}</strong>
          <small>Local credit ledger</small>
        </article>
        <article>
          <span>Active keys</span>
          <strong>{activeKeys.length}</strong>
          <small>{keys.length} total keys</small>
        </article>
        <article>
          <span>24h requests</span>
          <strong>{formatCompactNumber(dashboard?.request_count_24h)}</strong>
          <small>{formatCompactNumber(dashboard?.request_count_7d)} in 7 days</small>
        </article>
        <article>
          <span>Custom providers</span>
          <strong>{providers.length}</strong>
          <small>{customModelIds.length} custom models</small>
        </article>
      </div>

      <div className="portal-lane-grid">
        <article className="portal-card portal-card--compact">
          <div className="portal-card-heading">
            <span className="section-eyebrow">Launch checklist</span>
            <h3>Ready to send traffic</h3>
          </div>
          <div className="portal-step-list">
            {readySteps.map((step, index) => (
              <div className={step.ready ? "portal-step portal-step--done" : "portal-step"} key={step.label}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step.label}</strong>
                <small>{step.ready ? "Done" : "Pending"}</small>
              </div>
            ))}
          </div>
        </article>

        <article className="portal-card portal-card--compact">
          <div className="portal-card-heading">
            <span className="section-eyebrow">Traffic split</span>
            <h3>Platform vs custom</h3>
          </div>
          <div className="portal-split-meter">
            <div
              style={{
                width: `${Math.min(100, Math.max(8, ((dashboard?.custom_requests_24h ?? 0) / Math.max(1, dashboard?.request_count_24h ?? 0)) * 100))}%`,
              }}
            />
          </div>
          <div className="portal-split-labels">
            <span>Platform {formatCompactNumber(dashboard?.platform_requests_24h)}</span>
            <span>Custom {formatCompactNumber(dashboard?.custom_requests_24h)}</span>
          </div>
        </article>
      </div>

      <div className="portal-section-grid">
        <article className="portal-card portal-card--keys">
          <div className="portal-card-heading">
            <span className="section-eyebrow">Access</span>
            <h3>API Keys</h3>
          </div>
          <form className="portal-inline-form" onSubmit={handleCreateKey}>
            <label>
              <span>Key name</span>
              <input value={keyName} onChange={(event) => setKeyName(event.target.value)} />
            </label>
            <button type="submit">Create key</button>
          </form>
          <div className="portal-key-list">
            {keys.length === 0 ? <p>No API keys yet. Create one to start calling `/v1`.</p> : null}
            {keys.map((key) => (
              <div className="portal-key-row" key={key.id}>
                <div>
                  <strong>{key.name}</strong>
                  <span>{key.key_prefix} · {key.status}</span>
                </div>
                <div>
                  <small>{key.total_requests} requests</small>
                  {key.status === "active" ? (
                    <button type="button" onClick={() => void handleDeleteKey(key.id)}>Revoke</button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="portal-card portal-card--api" id="portal-api-example">
          <div className="portal-card-heading">
            <span className="section-eyebrow">Integration</span>
            <h3>Drop-in API example</h3>
          </div>
          <div className="api-example-block">
            <span>OpenAI SDK base URL</span>
            <code>{apiBaseUrl}</code>
          </div>
          <div className="portal-code-tabs">
            <pre>{chatCurlExample(apiBaseUrl, exampleApiKey, exampleModelId)}</pre>
            <pre>{sdkExample(apiBaseUrl, exampleApiKey, exampleModelId)}</pre>
          </div>
        </article>
      </div>

      <section className="portal-card portal-provider-studio" id="portal-provider-studio">
        <div className="portal-card-heading">
          <span className="section-eyebrow">Provider Studio</span>
          <h3>Connect a custom model provider</h3>
          <p>Choose a mainstream preset, paste your API key, then probe the provider to populate custom model IDs.</p>
        </div>
        <div className="portal-preset-rail">
          {topPresets.map((preset) => (
            <button
              className={selectedPresetId === preset.id ? "portal-preset-card portal-preset-card--selected" : "portal-preset-card"}
              key={preset.id}
              type="button"
              onClick={() => handleSelectProviderPreset(preset.id)}
            >
              <strong>{preset.display_name}</strong>
              <span>{protocolLabel(preset.protocol)}</span>
              <small>{preset.recommended_models.slice(0, 2).join(" · ")}</small>
            </button>
          ))}
        </div>
        <div className="portal-provider-workbench">
          <form className="portal-provider-form" onSubmit={handleCreateProvider}>
            <label>
              <span>Preset</span>
              <select value={selectedPresetId} onChange={(event) => handleSelectProviderPreset(event.target.value)}>
                <option value="manual">Manual / edited</option>
                {providerPresets.map((preset) => (
                  <option value={preset.id} key={preset.id}>{preset.display_name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Provider slug</span>
              <input
                value={providerName}
                onChange={(event) => {
                  markProviderEdited();
                  setProviderName(event.target.value);
                }}
              />
            </label>
            <label>
              <span>Protocol</span>
              <select
                value={providerProtocol}
                onChange={(event) => {
                  markProviderEdited();
                  setProviderProtocol(event.target.value);
                }}
              >
                <option value="openai">OpenAI-compatible</option>
                <option value="anthropic">Anthropic Messages</option>
              </select>
            </label>
            <label>
              <span>Base URL</span>
              <input
                placeholder="https://provider.example.com/v1"
                value={providerBaseUrl}
                onChange={(event) => {
                  markProviderEdited();
                  setProviderBaseUrl(event.target.value);
                }}
              />
            </label>
            <label>
              <span>API key</span>
              <input type="password" value={providerApiKey} onChange={(event) => setProviderApiKey(event.target.value)} />
            </label>
            {selectedPreset ? (
              <p className="provider-preset-hint">
                {selectedPreset.description} Suggested models: {selectedPreset.recommended_models.slice(0, 4).join(", ")}
              </p>
            ) : null}
            <button type="submit">Add provider</button>
          </form>
          <div className="portal-provider-list">
            {providers.length === 0 ? <p>No custom providers yet. Add one from the preset gallery.</p> : null}
            {providers.map((provider) => (
              <div className="portal-provider-card" key={provider.id}>
                <div>
                  <strong>{provider.slug}</strong>
                  <span>{protocolLabel(provider.protocol)} · {provider.base_url}</span>
                </div>
                <div className={`portal-provider-status portal-provider-status--${probeTone(provider)}`}>
                  {probeLabel(provider)}
                </div>
                {provider.last_detected_models.length > 0 ? (
                  <div className="portal-provider-models">
                    {provider.last_detected_models.slice(0, 4).map((model) => <code key={model}>{model}</code>)}
                  </div>
                ) : null}
                <div className="inline-actions">
                  <button type="button" onClick={() => void handleProbeProvider(provider.id)}>Probe</button>
                  <button type="button" onClick={() => void handleDeleteProvider(provider.id)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="portal-card portal-model-catalog">
        <div className="portal-card-heading">
          <span className="section-eyebrow">Model Directory</span>
          <h3>Available models</h3>
          <p>Custom model IDs are scoped to this account. Platform models are managed by the gateway operator.</p>
        </div>
        <div className="portal-model-toolbar">
          <div className="portal-tab-group">
            <button className={modelTab === "custom" ? "active" : undefined} type="button" onClick={() => setModelTab("custom")}>
              Custom {customModelIds.length}
            </button>
            <button className={modelTab === "platform" ? "active" : undefined} type="button" onClick={() => setModelTab("platform")}>
              Platform {platformModelIds.length}
            </button>
          </div>
          <input placeholder="Search models" value={modelQuery} onChange={(event) => setModelQuery(event.target.value)} />
        </div>
        <div className="portal-model-grid">
          {visibleModels.length === 0 ? <p>No models match this filter.</p> : null}
          {visibleModels.slice(0, 36).map((modelId) => (
            <code key={modelId}>{modelId}</code>
          ))}
        </div>
      </section>

      <section className="portal-card">
        <div className="portal-card-heading">
          <span className="section-eyebrow">Usage</span>
          <h3>Recent requests</h3>
        </div>
        <div className="portal-usage-list">
          {(dashboard?.recent_usage ?? []).length === 0 ? <p>No recent usage yet.</p> : null}
          {(dashboard?.recent_usage ?? []).map((usage) => (
            <div className="portal-usage-row" key={usage.id}>
              <div>
                <strong>{usage.model_id ?? "n/a"}</strong>
                <span>{usage.provider_name ?? "platform"} · {usage.outcome}</span>
              </div>
              <div>
                <small>{formatNullableDate(usage.created_at)}</small>
                <span>{formatCompactNumber(usage.credits_charged)} credits</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}
