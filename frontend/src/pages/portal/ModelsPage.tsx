import { useEffect, useState } from "react";

import type { CatalogModelRecord, UserProviderRecord } from "../../api";
import { buildChatCurlExample, resolveApiBaseUrl, type ExampleMode } from "../../app/requestExamples";
import type { Copy } from "../../i18n";

type ModelsPageProps = {
  copy: Copy;
  customModels: CatalogModelRecord[];
  platformModels: CatalogModelRecord[];
  providers: UserProviderRecord[];
};

type CustomModelHealth = "verified" | "detected" | "recommended";

function customModelHealth(modelId: string, providers: UserProviderRecord[]): CustomModelHealth {
  const [providerSlug, nativeModel] = modelId.split(":", 2);
  const provider = providers.find((item) => item.slug === providerSlug);
  if (!provider) {
    return "recommended";
  }
  if (provider.last_probe_ok && provider.last_probe_model === nativeModel) {
    return "verified";
  }
  if (provider.last_detected_models.includes(nativeModel)) {
    return "detected";
  }
  return "recommended";
}

function healthLabel(health: CustomModelHealth): string {
  if (health === "verified") {
    return "已验证";
  }
  if (health === "detected") {
    return "已探测";
  }
  return "推荐";
}

export function ModelsPage({ copy, customModels, platformModels, providers }: ModelsPageProps) {
  const groupedCustomModels = customModels.reduce<Record<string, CatalogModelRecord[]>>((groups, model) => {
    const key = model.provider;
    groups[key] = groups[key] ? [...groups[key], model] : [model];
    return groups;
  }, {});
  const allModels = [...platformModels, ...customModels];
  const [selectedModelId, setSelectedModelId] = useState<string>(allModels[0]?.id ?? "");
  const [exampleMode, setExampleMode] = useState<ExampleMode>("non-stream");
  const [copiedLabel, setCopiedLabel] = useState<string | null>(null);
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!allModels.some((model) => model.id === selectedModelId)) {
      setSelectedModelId(allModels[0]?.id ?? "");
    }
  }, [allModels, selectedModelId]);

  const apiBaseUrl = resolveApiBaseUrl();
  const verifiedCustomModelCount = customModels.filter((model) => customModelHealth(model.id, providers) === "verified").length;
  const curlExample = selectedModelId
    ? buildChatCurlExample({ apiBaseUrl, modelId: selectedModelId, mode: exampleMode })
    : "";

  async function copyText(value: string, label: string) {
    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(value);
    setCopiedLabel(label);
    window.setTimeout(() => {
      setCopiedLabel((current) => (current === label ? null : current));
    }, 1600);
  }

  function toggleProviderDetails(providerId: string) {
    setExpandedProviders((current) => ({
      ...current,
      [providerId]: !current[providerId],
    }));
  }

  return (
    <section className="portal-section">
      <div className="portal-section__header">
        <div>
          <div className="eyebrow">Models</div>
          <h1>Models</h1>
          <p>{copy.portal.routingCardBody}</p>
        </div>
      </div>
      <div className="resource-summary-grid">
        <article>
          <span>Total models</span>
          <strong>{allModels.length}</strong>
        </article>
        <article>
          <span>Platform</span>
          <strong>{platformModels.length}</strong>
        </article>
        <article>
          <span>Custom</span>
          <strong>{customModels.length}</strong>
        </article>
        <article>
          <span>Verified custom</span>
          <strong>{verifiedCustomModelCount}</strong>
        </article>
      </div>
      <div className="detail-grid">
        <article className="detail-panel">
          <h3>{copy.portal.platformTraffic}</h3>
          <p>
            Managed platform models are exposed through <code>/v1/models</code> and keep namespaced
            ids such as <code>codex:gpt-5.4</code>.
          </p>
        </article>
        <article className="detail-panel">
          <h3>{copy.portal.customTraffic}</h3>
          <p>
            Every active custom provider is surfaced as namespaced model ids using the provider
            slug, for example <code>minimax-cn:MiniMax-M2.7</code>. Verified models are the ones
            that most recently passed the connection probe.
          </p>
        </article>
        <article className="detail-panel detail-panel--wide">
          <h3>Sample request</h3>
          <p>
            Pick any model below, switch between non-stream and stream, then copy the model id or
            the ready-to-run <code>curl</code> example.
          </p>
          {selectedModelId ? (
            <div className="snippet-card">
              <div className="snippet-card__actions">
                <strong>{selectedModelId}</strong>
                <div className="model-chip-group">
                  <button
                    className={exampleMode === "non-stream" ? "ghost-action ghost-action--bright" : "ghost-action"}
                    onClick={() => setExampleMode("non-stream")}
                  >
                    非流式示例
                  </button>
                  <button
                    className={exampleMode === "stream" ? "ghost-action ghost-action--bright" : "ghost-action"}
                    onClick={() => setExampleMode("stream")}
                  >
                    流式示例
                  </button>
                  <button
                    className="ghost-action ghost-action--bright"
                    onClick={() => void copyText(selectedModelId, "model-id")}
                  >
                    复制 Model ID
                  </button>
                  <button
                    className="ghost-action ghost-action--bright"
                    onClick={() => void copyText(curlExample, exampleMode === "stream" ? "curl-stream" : "curl")}
                  >
                    复制 cURL
                  </button>
                </div>
              </div>
              <pre className="snippet-card__code">
                <code>{curlExample}</code>
              </pre>
              {copiedLabel ? <small>已复制 {copiedLabel}</small> : null}
            </div>
          ) : (
            <div className="empty-state empty-state--action">
              <strong>No model ids available yet.</strong>
              <p>平台模型目录为空时，先在 Providers 添加一个自定义模型提供商并完成连接测试。</p>
            </div>
          )}
        </article>
      </div>
      <div className="catalog-columns">
        <article className="catalog-column">
          <h3>Platform Models</h3>
          {platformModels.length === 0 ? (
            <div className="empty-state empty-state--compact">
              <strong>No platform models.</strong>
              <p>等待托管模型目录同步后，这里会显示 codex:* 等平台模型。</p>
            </div>
          ) : (
            <div className="provider-list">
              {platformModels.map((model) => (
                <article className="provider-row" key={model.id}>
                  <div className="provider-row__body">
                    <strong>{model.id}</strong>
                    <p>{model.provider}</p>
                  </div>
                  <div className="provider-row__actions">
                    <button
                      className="ghost-action ghost-action--bright"
                      onClick={() => setSelectedModelId(model.id)}
                    >
                      查看示例
                    </button>
                    <button
                      className="ghost-action ghost-action--bright"
                      onClick={() => void copyText(model.id, "model-id")}
                    >
                      复制 ID
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>
        <article className="catalog-column">
          <h3>Custom Models</h3>
          {customModels.length === 0 ? (
            <div className="empty-state empty-state--compact">
              <strong>{copy.portal.noProviders}</strong>
              <p>添加 Provider 并测试连接后，将出现 provider-slug:model 的模型 ID。</p>
            </div>
          ) : (
            <div className="provider-list">
              {Object.entries(groupedCustomModels).map(([provider, models]) => (
                <article className="provider-row" key={provider}>
                  <div className="provider-row__body">
                    <strong>{provider}</strong>
                    <p>
                      {models.length} custom models ·{" "}
                      {models.filter((model) => customModelHealth(model.id, providers) === "verified").length} verified
                    </p>
                    <div className="model-chip-group">
                      {models
                        .filter((model) => customModelHealth(model.id, providers) === "verified")
                        .map((model) => (
                        <span className={`model-chip model-chip--${customModelHealth(model.id, providers)}`} key={model.id}>
                          {model.id} · {healthLabel(customModelHealth(model.id, providers))}
                        </span>
                        ))}
                      {models.filter((model) => customModelHealth(model.id, providers) !== "verified").length > 0 ? (
                        <button
                          className="ghost-action ghost-action--bright"
                          onClick={() => toggleProviderDetails(provider)}
                        >
                          {expandedProviders[provider] ? "隐藏其他模型" : "查看其他模型"}
                        </button>
                      ) : null}
                    </div>
                    {expandedProviders[provider] ? (
                      <div className="model-chip-group model-chip-group--secondary">
                        {models
                          .filter((model) => customModelHealth(model.id, providers) !== "verified")
                          .map((model) => (
                            <span className={`model-chip model-chip--${customModelHealth(model.id, providers)}`} key={model.id}>
                              {model.id} · {healthLabel(customModelHealth(model.id, providers))}
                            </span>
                          ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="provider-row__actions">
                    <button
                      className="ghost-action ghost-action--bright"
                      onClick={() => setSelectedModelId(models[0].id)}
                    >
                      查看示例
                    </button>
                    <button
                      className="ghost-action ghost-action--bright"
                      onClick={() => void copyText(models[0].id, "model-id")}
                    >
                      复制首个 ID
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
