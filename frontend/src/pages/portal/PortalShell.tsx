import { useEffect, useState } from "react";

import {
  createUserApiKey,
  deleteUserApiKey,
  deleteUserProvider,
  getPortalCatalog,
  getPortalDashboard,
  getUserApiKeys,
  getUserProviders,
  logoutSession,
  addUserProvider,
  probeSavedUserProvider,
  probeUserProvider,
  retryPortalSync,
  updateUserApiKey,
  updateUserProvider,
  type AuthAccount,
  type ApiKeyUpdatePayload,
  type ApiKeyRecord,
  type CatalogModelRecord,
  type DashboardSummary,
  type PlatformProviderRecord,
  type ProviderProbeResult,
  type UserProviderUpdatePayload,
  type UserProviderRecord,
} from "../../api";
import type { Copy, Locale } from "../../i18n";
import { DashboardPage } from "./DashboardPage";
import { ApiKeysPage } from "./ApiKeysPage";
import { ConfirmDialog } from "./ConfirmDialog";
import { ModelsPage } from "./ModelsPage";
import { ProvidersPage } from "./ProvidersPage";
import { providerPresets } from "./providerPresets";

type PortalShellProps = {
  copy: Copy;
  locale: Locale;
  onLogout: () => void;
  onNavigate: (pathname: string) => void;
  onToggleLocale: () => void;
  pathname: string;
  user: AuthAccount | null;
};

type PortalView = "dashboard" | "api-keys" | "models" | "providers";
type PendingConfirmation =
  | { kind: "api-key"; id: number; label: string }
  | { kind: "provider"; id: number; label: string }
  | null;

function currentView(pathname: string): PortalView {
  if (pathname === "/portal/api-keys") {
    return "api-keys";
  }
  if (pathname === "/portal/providers") {
    return "providers";
  }
  if (pathname === "/portal/models") {
    return "models";
  }
  return "dashboard";
}

export function PortalShell({
  copy,
  onLogout,
  onNavigate,
  onToggleLocale,
  pathname,
  user,
}: PortalShellProps) {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyRecord[]>([]);
  const [providers, setProviders] = useState<UserProviderRecord[]>([]);
  const [platformProviders, setPlatformProviders] = useState<PlatformProviderRecord[]>([]);
  const [platformModels, setPlatformModels] = useState<CatalogModelRecord[]>([]);
  const [customModels, setCustomModels] = useState<CatalogModelRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [apiKeyName, setApiKeyName] = useState("");
  const [apiKeyLimitMinute, setApiKeyLimitMinute] = useState("");
  const [apiKeyLimitHour, setApiKeyLimitHour] = useState("");
  const [apiKeyLimitDay, setApiKeyLimitDay] = useState("");
  const [providerPresetId, setProviderPresetId] = useState(providerPresets[0].id);
  const [providerProtocol, setProviderProtocol] = useState<"openai" | "anthropic">(providerPresets[0].protocol);
  const [providerProbeResult, setProviderProbeResult] = useState<ProviderProbeResult | null>(null);
  const [providerProbeRunning, setProviderProbeRunning] = useState(false);
  const [providerReprobeId, setProviderReprobeId] = useState<number | null>(null);
  const [syncRetrying, setSyncRetrying] = useState(false);
  const [providerName, setProviderName] = useState("");
  const [providerUrl, setProviderUrl] = useState("");
  const [providerSecret, setProviderSecret] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation>(null);

  async function loadPortalData() {
    setLoading(true);
    setError(null);
    try {
      const [dashboardResult, apiKeysResult, providersResult, catalogResult] = await Promise.all([
        getPortalDashboard(),
        getUserApiKeys(),
        getUserProviders(),
        getPortalCatalog(),
      ]);
      setDashboard(dashboardResult);
      setApiKeys(apiKeysResult);
      setProviders(providersResult);
      setPlatformProviders(catalogResult.platform_providers ?? []);
      setPlatformModels(catalogResult.platform_models ?? []);
      setCustomModels(catalogResult.custom_models ?? []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPortalData();
  }, []);

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setNotice(null);
    }, 2500);
    return () => window.clearTimeout(timeoutId);
  }, [notice]);

  async function handleCreateKey() {
    const result = await createUserApiKey({
      name: apiKeyName,
      per_minute: parsePositiveLimit(apiKeyLimitMinute),
      per_hour: parsePositiveLimit(apiKeyLimitHour),
      per_day: parsePositiveLimit(apiKeyLimitDay),
    });
    setCreatedKey(result.api_key);
    setApiKeyName("");
    setApiKeyLimitMinute("");
    setApiKeyLimitHour("");
    setApiKeyLimitDay("");
    setNotice("API key 已创建。");
    await loadPortalData();
  }

  async function handleDeleteKey(id: number) {
    await deleteUserApiKey(id);
    setNotice("API key 已撤销。");
    await loadPortalData();
  }

  async function handleUpdateKey(id: number, payload: ApiKeyUpdatePayload) {
    await updateUserApiKey(id, payload);
    setNotice("API key 限额已更新。");
    await loadPortalData();
  }

  async function handleAddProvider() {
    await addUserProvider({
      name: providerName,
      protocol: providerProtocol,
      base_url: providerUrl,
      api_key: providerSecret,
    });
    setProviderName("");
    setProviderUrl("");
    setProviderSecret("");
    setProviderProbeResult(null);
    setNotice("Provider 已添加。");
    await loadPortalData();
  }

  async function handleDeleteProvider(id: number) {
    await deleteUserProvider(id);
    setNotice("Provider 已删除。");
    await loadPortalData();
  }

  async function handleConfirmDelete() {
    if (!pendingConfirmation) {
      return;
    }
    if (pendingConfirmation.kind === "api-key") {
      await handleDeleteKey(pendingConfirmation.id);
    } else {
      await handleDeleteProvider(pendingConfirmation.id);
    }
    setPendingConfirmation(null);
  }

  async function handleReprobeProvider(id: number) {
    setProviderReprobeId(id);
    try {
      await probeSavedUserProvider(id);
      setNotice("Provider 测试结果已更新。");
      await loadPortalData();
    } catch (probeError) {
      setError(probeError instanceof Error ? probeError.message : "request failed");
    } finally {
      setProviderReprobeId(null);
    }
  }

  async function handleUpdateProvider(id: number, payload: UserProviderUpdatePayload) {
    try {
      await updateUserProvider(id, payload);
      await probeSavedUserProvider(id);
      setNotice("Provider 已保存并重新测试。");
      await loadPortalData();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "request failed");
      await loadPortalData();
    }
  }

  async function handleRetrySync() {
    setSyncRetrying(true);
    try {
      await retryPortalSync();
      setNotice("状态已刷新。");
      await loadPortalData();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : "request failed");
    } finally {
      setSyncRetrying(false);
    }
  }

  const view = currentView(pathname);
  const previewModelId = providerName.trim() ? `${providerName.trim().toLowerCase()}:default` : null;
  const pendingSyncEvents = dashboard?.account_sync?.sync_queue?.pending ?? 0;
  const failedSyncEvents = dashboard?.account_sync?.sync_queue?.failed ?? 0;
  const gatewayStatusTone =
    error ? "danger" : loading ? "warning" : failedSyncEvents > 0 || pendingSyncEvents > 0 ? "warning" : "ok";
  const gatewayStatusText = error
    ? "Needs attention"
    : loading
      ? copy.common.loading
      : failedSyncEvents > 0
        ? "Review required"
        : pendingSyncEvents > 0
          ? "Updating"
          : "Ready";
  const workspaceStatusText =
    failedSyncEvents > 0
      ? "Recent account updates need review."
      : pendingSyncEvents > 0
        ? "Recent account updates are being applied."
        : "Workspace ready";

  function handlePresetChange(nextPresetId: string) {
    setProviderPresetId(nextPresetId);
    const preset = providerPresets.find((item) => item.id === nextPresetId);
    if (!preset) {
      return;
    }
    setProviderName(preset.defaultName);
    setProviderProtocol(preset.protocol);
    setProviderUrl(preset.baseUrl);
    setProviderProbeResult(null);
  }

  async function handleProbeProvider() {
    setProviderProbeRunning(true);
    try {
      const preset = providerPresets.find((item) => item.id === providerPresetId);
      const result = await probeUserProvider({
        protocol: providerProtocol,
        base_url: providerUrl,
        api_key: providerSecret,
        candidate_models: preset?.recommendedModels ?? [],
      });
      setProviderProbeResult(result);
      setNotice(result.completion_probe_ok ? "临时测试成功。" : "临时测试已完成。");
    } catch (probeError) {
      setProviderProbeResult({
        models_endpoint_supported: false,
        detected_models: [],
        completion_probe_ok: false,
        completion_probe_model: null,
        detail: probeError instanceof Error ? probeError.message : "request failed",
      });
    } finally {
      setProviderProbeRunning(false);
    }
  }

  return (
    <div className="portal-shell">
      <aside className="portal-sidebar">
        <div className="portal-sidebar__top">
          <button className="site-logo portal-sidebar__brand" onClick={() => onNavigate("/")}>
            <span className="site-logo__mark" />
            <span>{copy.public.brand}</span>
          </button>
          <div className={`portal-status portal-status--${gatewayStatusTone}`}>
            <span className="portal-status__dot" />
            <span>{gatewayStatusText}</span>
          </div>
        </div>
        <nav aria-label="Portal navigation" className="portal-nav">
          <button className={view === "dashboard" ? "active" : ""} onClick={() => onNavigate("/portal")}>
            <span>{copy.common.dashboard}</span>
            <small>Credits and usage</small>
          </button>
          <button className={view === "api-keys" ? "active" : ""} onClick={() => onNavigate("/portal/api-keys")}>
            <span>{copy.common.apiKeys}</span>
            <small>{apiKeys.length} active</small>
          </button>
          <button className={view === "models" ? "active" : ""} onClick={() => onNavigate("/portal/models")}>
            <span>Models</span>
            <small>{platformModels.length + customModels.length} available</small>
          </button>
          <button className={view === "providers" ? "active" : ""} onClick={() => onNavigate("/portal/providers")}>
            <span>{copy.common.providers}</span>
            <small>{providers.length} connected</small>
          </button>
          <button onClick={() => onNavigate("/docs")}>
            <span>{copy.portal.docsShortcut}</span>
            <small>Quickstart and reference</small>
          </button>
        </nav>
        <div className="portal-sidebar__footer">
          <div>
            <strong>{user?.name ?? "—"}</strong>
            <p>{user?.email ?? ""}</p>
          </div>
          <div className="portal-sidebar__sync">
            <span>Workspace status</span>
            <strong>{workspaceStatusText}</strong>
          </div>
          <div className="portal-sidebar__actions">
            <button className="ghost-action" onClick={onToggleLocale}>
              {copy.common.locale}
            </button>
            <button
              className="ghost-action ghost-action--danger"
              onClick={async () => {
                await logoutSession();
                onLogout();
              }}
            >
              {copy.common.signOut}
            </button>
          </div>
        </div>
      </aside>
      <main className="portal-main">
        <div className="portal-main__topbar">
          <div>
            <span className={`status-pill status-pill--${gatewayStatusTone}`}>{gatewayStatusText}</span>
            <span className="portal-main__meta">Customer console</span>
          </div>
          <button className="ghost-action ghost-action--bright" onClick={() => onNavigate("/docs")}>
            {copy.portal.docsShortcut}
          </button>
        </div>
        {loading ? <div className="empty-state empty-state--loading">{copy.common.loading}</div> : null}
        {notice ? <div className="inline-success">{notice}</div> : null}
        {error ? (
          <div className="inline-error inline-error--with-action">
            <span>{error}</span>
            <button className="ghost-action ghost-action--bright" onClick={() => void loadPortalData()}>
              重试加载
            </button>
          </div>
        ) : null}
        {!loading && !error && view === "dashboard" ? (
          <DashboardPage
            apiKeyCount={apiKeys.length}
            copy={copy}
            dashboard={dashboard}
            onRetrySync={handleRetrySync}
            providerCount={providers.length}
            syncRetrying={syncRetrying}
          />
        ) : null}
        {!loading && !error && view === "api-keys" ? (
          <ApiKeysPage
            apiKeys={apiKeys}
            copy={copy}
            createdKey={createdKey}
            keyName={apiKeyName}
            limitDay={apiKeyLimitDay}
            limitHour={apiKeyLimitHour}
            limitMinute={apiKeyLimitMinute}
            onCreate={handleCreateKey}
            onDelete={(id) => {
              const record = apiKeys.find((item) => item.id === id);
              setPendingConfirmation({ kind: "api-key", id, label: record?.name ?? "API key" });
              return Promise.resolve();
            }}
            onUpdate={handleUpdateKey}
            onKeyNameChange={setApiKeyName}
            onLimitDayChange={setApiKeyLimitDay}
            onLimitHourChange={setApiKeyLimitHour}
            onLimitMinuteChange={setApiKeyLimitMinute}
            onDismissCreatedKey={() => setCreatedKey(null)}
          />
        ) : null}
        {!loading && !error && view === "providers" ? (
          <ProvidersPage
            copy={copy}
            customModels={customModels.map((model) => model.id)}
            name={providerName}
            platformProviders={platformProviders}
            probeResult={providerProbeResult}
            probeRunning={providerProbeRunning}
            presetId={providerPresetId}
            presets={providerPresets}
            protocol={providerProtocol}
            providers={providers}
            previewModelId={previewModelId}
            reprobeProviderId={providerReprobeId}
            secret={providerSecret}
            url={providerUrl}
            onAdd={handleAddProvider}
            onDelete={(id) => {
              const record = providers.find((item) => item.id === id);
              setPendingConfirmation({ kind: "provider", id, label: record?.name ?? "Provider" });
              return Promise.resolve();
            }}
            onNameChange={setProviderName}
            onProtocolChange={setProviderProtocol}
            onPresetChange={handlePresetChange}
            onProbe={handleProbeProvider}
            onReprobe={handleReprobeProvider}
            onSecretChange={setProviderSecret}
            onUpdate={handleUpdateProvider}
            onUrlChange={setProviderUrl}
          />
        ) : null}
        {!loading && !error && view === "models" ? (
          <ModelsPage copy={copy} customModels={customModels} platformModels={platformModels} providers={providers} />
        ) : null}
        <ConfirmDialog
          open={pendingConfirmation !== null}
          title={pendingConfirmation?.kind === "api-key" ? "确认删除 API key" : "确认删除 Provider"}
          body={
            pendingConfirmation
              ? `这会删除 ${pendingConfirmation.label}。这个动作会立即生效。`
              : ""
          }
          confirmLabel="确认删除"
          onCancel={() => setPendingConfirmation(null)}
          onConfirm={handleConfirmDelete}
        />
      </main>
    </div>
  );
}

function parsePositiveLimit(value: string): number | undefined {
  if (!value.trim()) {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}
