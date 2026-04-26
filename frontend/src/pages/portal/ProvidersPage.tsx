import { useState } from "react";

import type {
  PlatformProviderRecord,
  ProviderProbeResult,
  UserProviderRecord,
  UserProviderUpdatePayload,
} from "../../api";
import { buildChatCurlExample, resolveApiBaseUrl } from "../../app/requestExamples";
import type { Copy } from "../../i18n";
import { summarizeProviderDetail } from "./providerDiagnostics";
import type { ProviderPreset } from "./providerPresets";

type ProvidersPageProps = {
  copy: Copy;
  customModels: string[];
  name: string;
  platformProviders: PlatformProviderRecord[];
  probeResult: ProviderProbeResult | null;
  probeRunning: boolean;
  presetId: string;
  presets: ProviderPreset[];
  protocol: "openai" | "anthropic";
  providers: UserProviderRecord[];
  previewModelId: string | null;
  reprobeProviderId: number | null;
  secret: string;
  url: string;
  onAdd: () => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onNameChange: (value: string) => void;
  onProtocolChange: (value: "openai" | "anthropic") => void;
  onPresetChange: (value: string) => void;
  onProbe: () => Promise<void>;
  onReprobe: (id: number) => Promise<void>;
  onSecretChange: (value: string) => void;
  onUpdate: (id: number, payload: UserProviderUpdatePayload) => Promise<void>;
  onUrlChange: (value: string) => void;
};

export function ProvidersPage({
  copy,
  customModels,
  name,
  platformProviders,
  probeResult,
  probeRunning,
  presetId,
  presets,
  protocol,
  providers,
  previewModelId,
  reprobeProviderId,
  secret,
  url,
  onAdd,
  onDelete,
  onNameChange,
  onProtocolChange,
  onPresetChange,
  onProbe,
  onReprobe,
  onSecretChange,
  onUpdate,
  onUrlChange,
}: ProvidersPageProps) {
  const [expandedProviderModels, setExpandedProviderModels] = useState<Record<number, boolean>>({});
  const [editingProviderId, setEditingProviderId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editProtocol, setEditProtocol] = useState<"openai" | "anthropic">("openai");
  const [editUrl, setEditUrl] = useState("");
  const [editSecret, setEditSecret] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const selectedPreset = presets.find((preset) => preset.id === presetId) ?? presets[0];
  const apiBaseUrl = resolveApiBaseUrl();
  const canTest = Boolean(url.trim() && secret.trim());
  const canCreate = Boolean(name.trim() && url.trim() && secret.trim());

  function platformProviderSummary(provider: PlatformProviderRecord): string {
    if (provider.cli_enabled) {
      return "Managed model service";
    }
    return "HTTP model service";
  }

  function modelProbeState(provider: UserProviderRecord, modelId: string): "verified" | "detected" | "recommended" {
    const [, nativeModel = ""] = modelId.split(":", 2);
    if (provider.last_probe_ok && provider.last_probe_model === nativeModel) {
      return "verified";
    }
    if ((provider.last_detected_models ?? []).includes(nativeModel)) {
      return "detected";
    }
    return "recommended";
  }

  function modelProbeLabel(state: "verified" | "detected" | "recommended"): string {
    if (state === "verified") {
      return "已验证";
    }
    if (state === "detected") {
      return "已探测";
    }
    return "推荐";
  }

  function sortByProbeState(provider: UserProviderRecord, models: string[]): string[] {
    const rank = { verified: 0, recommended: 1, detected: 2 };
    return [...models].sort((left, right) => {
      const leftRank = rank[modelProbeState(provider, left)];
      const rightRank = rank[modelProbeState(provider, right)];
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return left.localeCompare(right);
    });
  }

  function toggleProviderModels(providerId: number) {
    setExpandedProviderModels((current) => ({
      ...current,
      [providerId]: !current[providerId],
    }));
  }

  function startEditingProvider(provider: UserProviderRecord) {
    setEditingProviderId(provider.id);
    setEditName(provider.name);
    setEditProtocol(provider.protocol === "anthropic" ? "anthropic" : "openai");
    setEditUrl(provider.base_url);
    setEditSecret("");
    setEditDescription(provider.description ?? "");
  }

  async function saveProviderEdit(providerId: number) {
    const payload: UserProviderUpdatePayload = {
      name: editName,
      protocol: editProtocol,
      base_url: editUrl,
      description: editDescription.trim() ? editDescription.trim() : undefined,
      ...(editSecret.trim() ? { api_key: editSecret } : {}),
    };
    await onUpdate(providerId, payload);
    setEditingProviderId(null);
    setEditSecret("");
  }

  async function copyText(value: string) {
    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(value);
  }

  return (
    <section className="portal-section portal-section--providers">
      <div className="portal-section__header">
        <div>
          <div className="eyebrow">{copy.portal.providersTitle}</div>
          <h1>{copy.portal.providersTitle}</h1>
          <p>{copy.portal.providersLead}</p>
        </div>
      </div>
      <div className="provider-builder">
        <div className="provider-builder__steps" aria-label="Provider setup steps">
          <span className="active">1 Choose</span>
          <span className={name.trim() ? "active" : ""}>2 Configure</span>
          <span className={probeResult ? "active" : ""}>3 Verify</span>
          <span className={canCreate ? "active" : ""}>4 Save</span>
        </div>
        <div className="provider-form">
          <label>
            <span>Provider preset</span>
            <select value={presetId} onChange={(event) => onPresetChange(event.target.value)}>
              {presets.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{copy.portal.providerName}</span>
            <input placeholder={copy.portal.providerName} value={name} onChange={(event) => onNameChange(event.target.value)} />
          </label>
          <label>
            <span>Protocol</span>
            <select value={protocol} onChange={(event) => onProtocolChange(event.target.value as "openai" | "anthropic")}>
              <option value="openai">OpenAI-compatible</option>
              <option value="anthropic">Anthropic Messages</option>
            </select>
          </label>
          <label>
            <span>{copy.portal.providerUrl}</span>
            <input placeholder={copy.portal.providerUrl} value={url} onChange={(event) => onUrlChange(event.target.value)} />
          </label>
          <label>
            <span>{copy.portal.providerSecret}</span>
            <input
              placeholder={copy.portal.providerSecret}
              type="password"
              value={secret}
              onChange={(event) => onSecretChange(event.target.value)}
            />
          </label>
          <div className="provider-form__actions">
            <button
              className="ghost-action ghost-action--bright"
              disabled={!canTest || probeRunning}
              onClick={() => void onProbe()}
            >
              {probeRunning ? "Testing..." : "Test connection"}
            </button>
            <button
              className="primary-action"
              disabled={!canCreate}
              onClick={() => void onAdd()}
            >
              {copy.common.create}
            </button>
          </div>
        </div>
        <div className="provider-preset-note">
          <div className="provider-preset-note__header">
            <div>
              <strong>{selectedPreset.label}</strong>
              <p>{selectedPreset.note}</p>
            </div>
            <span className="status-pill status-pill--ok">Protocol: {selectedPreset.protocol}</span>
          </div>
          <code>{selectedPreset.baseUrl || "Set your own base URL"}</code>
          {previewModelId ? <small>Generated model id: {previewModelId}</small> : null}
          {selectedPreset.recommendedModels.length > 0 ? (
            <div className="model-chip-group">
              {selectedPreset.recommendedModels.map((model) => (
                <span className="model-chip" key={model}>
                  {model}
                </span>
              ))}
            </div>
          ) : null}
          {probeResult ? (
            <div className="probe-panel">
              <strong>{probeResult.completion_probe_ok ? "Connection ready" : "Connection needs review"}</strong>
              <p>
                {probeResult.models_endpoint_supported
                  ? `${probeResult.detected_models.length} model ids detected`
                  : "This provider does not publish /models, so recommended models are shown instead."}
              </p>
              {probeResult.completion_probe_model ? <code>{probeResult.completion_probe_model}</code> : null}
              {probeResult.detected_models.length > 0 ? (
                <div className="model-chip-group">
                  {probeResult.detected_models.slice(0, 8).map((model) => (
                    <span className="model-chip" key={model}>
                      {model}
                    </span>
                  ))}
                </div>
              ) : null}
              {summarizeProviderDetail(probeResult.detail) ? (
                <div className={`provider-diagnostic provider-diagnostic--${summarizeProviderDetail(probeResult.detail)!.tone}`}>
                  {summarizeProviderDetail(probeResult.detail)!.summary}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      <div className="catalog-columns">
        <article className="catalog-column">
          <h3>Managed model catalog</h3>
          {platformProviders.length === 0 ? (
            <div className="empty-state empty-state--compact">
              <strong>No managed model sources yet.</strong>
              <p>Managed model sources will appear here automatically when available.</p>
            </div>
          ) : (
          <div className="provider-list">
            {platformProviders.map((provider) => (
              <article className="provider-row provider-row--managed" key={provider.name}>
                <div>
                  <strong>{provider.name}</strong>
                  <p>{platformProviderSummary(provider)}</p>
                </div>
                <div className="model-chip-group">
                  <span className="model-chip">{provider.model_count} models</span>
                  <span className="model-chip">{provider.cli_enabled ? "managed" : "http"}</span>
                </div>
              </article>
            ))}
          </div>
          )}
        </article>
        <article className="catalog-column">
          <h3>Custom Providers</h3>
          {providers.length === 0 ? (
            <div className="empty-state empty-state--action">
              <strong>{copy.portal.noProviders}</strong>
              <p>Choose a preset, enter the Base URL and Provider API key, then test the connection before saving.</p>
            </div>
          ) : (
            <div className="provider-list">
              {providers.map((provider) => {
                const detectedModels = provider.last_detected_models ?? [];
                const providerModels = customModels.filter((modelId) => modelId.startsWith(`${provider.slug}:`));
                const listedModels = sortByProbeState(
                  provider,
                  providerModels.length > 0 ? providerModels : [`${provider.slug}:default`],
                );
                const visibleModels = listedModels.filter((modelId) => modelProbeState(provider, modelId) === "verified");
                const hiddenModels = listedModels.filter((modelId) => modelProbeState(provider, modelId) !== "verified");
                const expandedModels = Boolean(expandedProviderModels[provider.id]);
                const modelsToRender = expandedModels ? [...visibleModels, ...hiddenModels] : visibleModels;
                const providerDiagnostic = summarizeProviderDetail(provider.last_probe_detail);

                return (
                  <article className="provider-row provider-row--custom" key={provider.id}>
                    <div className="provider-row__body">
                      <strong>{provider.name}</strong>
                      <p>{provider.base_url}</p>
                      <small>{provider.slug} · {provider.protocol}</small>
                      {editingProviderId === provider.id ? (
                        <div className="provider-edit-form">
                          <label>
                            <span>Provider 名称</span>
                            <input
                              aria-label="编辑 Provider 名称"
                              value={editName}
                              onChange={(event) => setEditName(event.target.value)}
                            />
                          </label>
                          <label>
                            <span>Protocol</span>
                            <select
                              aria-label="编辑 Provider Protocol"
                              value={editProtocol}
                              onChange={(event) => setEditProtocol(event.target.value as "openai" | "anthropic")}
                            >
                              <option value="openai">OpenAI-compatible</option>
                              <option value="anthropic">Anthropic Messages</option>
                            </select>
                          </label>
                          <label>
                            <span>Base URL</span>
                            <input
                              aria-label="编辑 Provider Base URL"
                              value={editUrl}
                              onChange={(event) => setEditUrl(event.target.value)}
                            />
                          </label>
                          <label>
                            <span>API Key</span>
                            <input
                              aria-label="编辑 Provider API Key"
                              placeholder="留空则保留现有密钥"
                              type="password"
                              value={editSecret}
                              onChange={(event) => setEditSecret(event.target.value)}
                            />
                          </label>
                          <label>
                            <span>描述</span>
                            <input
                              aria-label="编辑 Provider 描述"
                              value={editDescription}
                              onChange={(event) => setEditDescription(event.target.value)}
                            />
                          </label>
                          <div className="provider-edit-form__actions">
                            <button
                              className="primary-action"
                              disabled={!editName.trim() || !editUrl.trim()}
                              onClick={() => void saveProviderEdit(provider.id)}
                            >
                              保存 Provider
                            </button>
                            <button className="ghost-action" onClick={() => setEditingProviderId(null)}>
                              取消编辑
                            </button>
                          </div>
                        </div>
                      ) : null}
                      <div className="provider-model-list">
                        {modelsToRender.length === 0 ? (
                          <div className="empty-state empty-state--compact">
                            没有已验证模型。展开后可查看已探测或推荐模型。
                          </div>
                        ) : null}
                        {modelsToRender.map((modelId) => {
                          const curlExample = buildChatCurlExample({
                            apiBaseUrl,
                            modelId,
                            mode: "non-stream",
                          });
                          const streamCurlExample = buildChatCurlExample({
                            apiBaseUrl,
                            modelId,
                            mode: "stream",
                          });

                          return (
                            <div className="provider-model-row" key={modelId}>
                              <div className="provider-model-row__label">
                                <code>{modelId}</code>
                                <span className={`model-chip model-chip--${modelProbeState(provider, modelId)}`}>
                                  {modelProbeLabel(modelProbeState(provider, modelId))}
                                </span>
                              </div>
                              <div className="provider-model-row__actions">
                                <button
                                  className="ghost-action ghost-action--bright"
                                  aria-label={`复制 ID ${modelId}`}
                                  onClick={() => void copyText(modelId)}
                                >
                                  复制 ID
                                </button>
                                <button
                                  className="ghost-action ghost-action--bright"
                                  aria-label={`复制 cURL ${modelId}`}
                                  onClick={() => void copyText(curlExample)}
                                >
                                  复制 cURL
                                </button>
                                <button
                                  className="ghost-action ghost-action--bright"
                                  aria-label={`复制流式 cURL ${modelId}`}
                                  onClick={() => void copyText(streamCurlExample)}
                                >
                                  复制流式 cURL
                                </button>
                              </div>
                            </div>
                          );
                        })}
                        {hiddenModels.length > 0 ? (
                          <button
                            className="ghost-action ghost-action--bright"
                            onClick={() => toggleProviderModels(provider.id)}
                          >
                            {expandedModels ? "隐藏其他模型" : `查看其他模型 (${hiddenModels.length})`}
                          </button>
                        ) : null}
                      </div>
                      <div className="provider-row__status">
                        <strong
                          className={
                            provider.last_probe_ok === true
                              ? "probe-status probe-status--ok"
                              : provider.last_probe_ok === false
                                ? "probe-status probe-status--fail"
                                : "probe-status"
                          }
                        >
                          {provider.last_probe_at
                            ? provider.last_probe_ok
                              ? "Latest connection test passed"
                              : "Latest connection test failed"
                            : "No saved connection test yet"}
                        </strong>
                        {provider.last_probe_at ? (
                          <small>{new Date(provider.last_probe_at).toLocaleString()}</small>
                        ) : null}
                        {provider.last_probe_model ? <code>{provider.last_probe_model}</code> : null}
                        {detectedModels.length > 0 ? (
                          <div className="model-chip-group">
                            {detectedModels.slice(0, 8).map((modelId) => (
                              <span className="model-chip" key={modelId}>
                                {modelId}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        {providerDiagnostic ? (
                          <div className={`provider-diagnostic provider-diagnostic--${providerDiagnostic.tone}`}>
                            {providerDiagnostic.summary}
                          </div>
                        ) : null}
                      </div>
                    </div>
                    <div className="provider-row__actions">
                      <button
                        className="ghost-action ghost-action--bright"
                        aria-label={`编辑 ${provider.slug}`}
                        onClick={() => startEditingProvider(provider)}
                      >
                        编辑
                      </button>
                      <button
                        className="ghost-action ghost-action--bright"
                        disabled={reprobeProviderId === provider.id}
                        onClick={() => void onReprobe(provider.id)}
                      >
                        {reprobeProviderId === provider.id ? "Testing..." : "Retest"}
                      </button>
                      <button className="ghost-action ghost-action--danger" onClick={() => void onDelete(provider.id)}>
                        {copy.common.delete}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
