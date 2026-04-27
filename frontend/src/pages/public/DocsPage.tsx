import { useEffect, useState } from "react";

import { getPortalCatalog, type AuthAccount, type CatalogModelRecord } from "../../api";
import {
  buildChatCurlExample,
  buildModelsListCurlExample,
  pickDefaultModelId,
  pickDefaultCustomModelId,
  pickDefaultPlatformModelId,
  resolveApiBaseUrl,
  type ExampleMode,
} from "../../app/requestExamples";
import type { Copy, Locale } from "../../i18n";

type DocsPageProps = {
  authUser: AuthAccount | null;
  copy: Copy;
  locale: Locale;
  onNavigate: (pathname: string) => void;
  onToggleLocale: () => void;
};

function isPublicDocsModel(model: CatalogModelRecord) {
  return !model.id.startsWith("hermes:");
}

export function DocsPage({ authUser, copy, locale, onNavigate, onToggleLocale }: DocsPageProps) {
  const apiBase = resolveApiBaseUrl();
  const isZh = locale === "zh";
  const docsCopy = isZh
    ? {
        catalogFallback: "当前账户的模型目录暂时不可用，已显示默认示例。",
        selectedPlatform: "平台模型",
        selectedCustom: "自定义 Provider",
        unifiedExample: "统一模型示例",
        exampleLead:
          "平台模型和自定义 Provider 共用同一个 /v1/chat/completions 地址。只需要切换 namespaced model id；流式和非流式也只通过 stream 字段切换。",
        exampleModel: "示例模型",
        nonStream: "非流式",
        stream: "流式",
        copyExample: "复制示例",
        currentExample: "当前示例",
        webFetchTitle: "Tools 调用：web_fetch",
        webFetchBody:
          "平台模型可选择启用网关侧 web_fetch。只有在 tools 里显式声明 web_fetch 时才会抓取网页；自定义 Provider 请求不会执行内置工具。网关会阻止 localhost、内网、保留地址和非文本响应。",
        platformModels: "平台模型",
        platformBody:
          "平台模型由 AgentHub 提供，模型 ID 使用平台 provider 前缀，例如 codex:gpt-5.4。它们和自定义模型共用上面的示例生成器。",
        customProviders: "自定义 Provider",
        customOnboarding:
          "Available custom model ids:\n{models}\n\nCustom provider onboarding:\n1. Sign in\n2. Open Console -> Providers\n3. Add provider name, base URL, and Provider API key\n4. Test the provider and copy one generated model id",
        openAiProvider: "OpenAI-compatible Provider",
        openAiBody:
          "Base URL 必须指向包含 /v1 的 OpenAI 兼容根路径，例如 https://api.example.com/v1。AgentHub 会调用该 Provider 的 /chat/completions 和可选的 /models。",
        anthropicProvider: "Anthropic Messages Provider",
        anthropicBody:
          "AgentHub 会把 OpenAI chat.completions 请求转换为 Anthropic Messages 请求，并用 x-api-key 与 anthropic-version 访问 Provider。",
        commonErrors: "常见错误",
        errors:
          "401 invalid api key:\n检查 Authorization: Bearer 是否使用 AgentHub API Key。\n\n429 rate limit exceeded:\n当前 API Key 命中了 per-minute / per-hour / per-day 限额。\n\n502 custom provider returned ...:\n自定义 Provider 返回错误。请在 Providers 页面重新测试，并确认 Base URL、协议和 API Key。\n\n503 service temporarily unavailable:\n平台模型服务暂时不可用，请稍后重试或联系支持。",
        streaming: "流式调用",
        streamingBody:
          "Switch the shared example above to stream mode.\nThe response is Server-Sent Events and terminates with:\n\ndata: [DONE]",
        copied: "已复制",
      }
    : {
        catalogFallback: "The live model catalog is temporarily unavailable, so default examples are shown.",
        selectedPlatform: "Managed model",
        selectedCustom: "Custom Provider",
        unifiedExample: "Unified model example",
        exampleLead:
          "Managed models and custom providers share the same /v1/chat/completions endpoint. Switch only the namespaced model ID, and use the stream field for streaming.",
        exampleModel: "Example model",
        nonStream: "Non-streaming",
        stream: "Streaming",
        copyExample: "Copy example",
        currentExample: "Current example",
        webFetchTitle: "Tools call: web_fetch",
        webFetchBody:
          "Managed models can opt into gateway-side web_fetch. Fetching only runs when the request explicitly declares web_fetch in tools; custom provider requests do not execute built-in tools. The gateway blocks localhost, private/reserved addresses, and non-text responses.",
        platformModels: "Managed models",
        platformBody:
          "Managed models are provided by AgentHub and use provider-prefixed model IDs such as codex:gpt-5.4. They share the same example generator as custom models.",
        customProviders: "Custom Providers",
        customOnboarding:
          "Available custom model ids:\n{models}\n\nCustom provider onboarding:\n1. Sign in\n2. Open Console -> Providers\n3. Add provider name, base URL, and Provider API key\n4. Test the provider and copy one generated model id",
        openAiProvider: "OpenAI-compatible Provider",
        openAiBody:
          "The Base URL must point to an OpenAI-compatible /v1 root, for example https://api.example.com/v1. AgentHub calls that provider's /chat/completions endpoint and optionally /models.",
        anthropicProvider: "Anthropic Messages Provider",
        anthropicBody:
          "AgentHub converts OpenAI chat.completions requests to Anthropic Messages requests and calls the provider with x-api-key and anthropic-version.",
        commonErrors: "Common errors",
        errors:
          "401 invalid api key:\nCheck that Authorization: Bearer uses your AgentHub API key.\n\n429 rate limit exceeded:\nThe API key reached its per-minute, per-hour, or per-day limit.\n\n502 custom provider returned ...:\nYour custom provider returned an error. Retest it in Providers and confirm the Base URL, protocol, and API key.\n\n503 service temporarily unavailable:\nManaged model service is temporarily unavailable. Retry later or contact support.",
        streaming: "Streaming calls",
        streamingBody:
          "Switch the shared example above to stream mode.\nThe response is Server-Sent Events and terminates with:\n\ndata: [DONE]",
        copied: "Copied",
      };
  const [platformModels, setPlatformModels] = useState<CatalogModelRecord[]>([]);
  const [customModels, setCustomModels] = useState<CatalogModelRecord[]>([]);
  const [catalogFallbackNotice, setCatalogFallbackNotice] = useState<string | null>(null);
  const [selectedExampleModelId, setSelectedExampleModelId] = useState<string>(pickDefaultModelId([]));
  const [selectedExampleMode, setSelectedExampleMode] = useState<ExampleMode>("non-stream");
  const [copiedLabel, setCopiedLabel] = useState<string | null>(null);

  useEffect(() => {
    if (!authUser) {
      return;
    }
    let active = true;
    void getPortalCatalog()
      .then((catalog) => {
        if (!active) {
          return;
        }
        setPlatformModels(catalog.platform_models.filter(isPublicDocsModel));
        setCustomModels(catalog.custom_models);
        setCatalogFallbackNotice(null);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setPlatformModels([]);
        setCustomModels([]);
        setCatalogFallbackNotice(docsCopy.catalogFallback);
      });
    return () => {
      active = false;
    };
  }, [authUser, docsCopy.catalogFallback]);

  const fallbackPlatformModelId = pickDefaultPlatformModelId([]);
  const fallbackCustomModelId = pickDefaultCustomModelId([]);
  const liveModelOptions: CatalogModelRecord[] = [...platformModels, ...customModels];
  const modelOptions =
    liveModelOptions.length > 0
      ? liveModelOptions
      : [
          { id: fallbackPlatformModelId, provider: "codex", source: "platform", enabled: true },
          { id: fallbackCustomModelId, provider: "minimax-cn", source: "custom", enabled: true },
        ];

  useEffect(() => {
    const nextModelId = pickDefaultModelId(modelOptions);
    if (!modelOptions.some((model) => model.id === selectedExampleModelId)) {
      setSelectedExampleModelId(nextModelId);
    }
  }, [modelOptions, selectedExampleModelId]);

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

  const selectedExampleModel =
    modelOptions.find((model) => model.id === selectedExampleModelId) ?? modelOptions[0];
  const selectedModelKind =
    selectedExampleModel?.source === "custom" ? docsCopy.selectedCustom : docsCopy.selectedPlatform;
  const webFetchModelId = pickDefaultPlatformModelId(platformModels);
  const exampleCurl = buildChatCurlExample({
    apiBaseUrl: apiBase,
    modelId: selectedExampleModelId,
    mode: selectedExampleMode,
    userMessage: "hello",
  });
  const webFetchCurl = `curl ${apiBase}/chat/completions \\
  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${webFetchModelId}",
    "messages": [
      {"role": "user", "content": "Fetch https://example.com and summarize it in one sentence."}
    ],
    "stream": false,
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "web_fetch",
          "description": "Fetch a public HTTP or HTTPS URL and return readable text.",
          "parameters": {
            "type": "object",
            "properties": {
              "url": {"type": "string", "description": "Public HTTP or HTTPS URL"}
            },
            "required": ["url"]
          }
        }
      }
    ],
    "tool_choice": {"type": "function", "function": {"name": "web_fetch"}}
  }'`;
  const platformModelList =
    platformModels.length > 0 ? platformModels.map((model) => model.id).join("\n") : fallbackPlatformModelId;
  const customModelList =
    customModels.length > 0 ? customModels.map((model) => model.id).join("\n") : fallbackCustomModelId;

  return (
    <div className="site-shell site-shell--subpage">
      <header className="site-header">
        <button className="site-logo" onClick={() => onNavigate("/")}>
          <span className="site-logo__mark" />
          <span>{copy.public.brand}</span>
        </button>
        <div className="site-header__actions">
          <button className="locale-switch" onClick={onToggleLocale}>
            {copy.common.locale}
          </button>
          {authUser?.is_admin ? (
            <button className="ghost-action" onClick={() => onNavigate("/admin")}>
              {copy.common.admin}
            </button>
          ) : null}
          <button className="ghost-action" onClick={() => onNavigate(authUser ? "/portal" : "/login")}>
            {authUser ? copy.common.console : copy.common.signIn}
          </button>
        </div>
      </header>
      <main className="subpage-body docs-body">
        <section className="subpage-intro">
          <div className="eyebrow">{copy.public.docsTitle}</div>
          <h1>{copy.docs.title}</h1>
          <p>{copy.docs.lead}</p>
        </section>
        {catalogFallbackNotice ? <div className="inline-error">{catalogFallbackNotice}</div> : null}
        <section className="docs-grid">
          <article className="docs-cardless">
            <h3>{copy.docs.authTitle}</h3>
            <pre>
              <code>{`Base URL: ${apiBase}\nAuthorization: Bearer YOUR_GATEWAY_API_KEY`}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{copy.docs.modelsTitle}</h3>
            <pre>
              <code>{buildModelsListCurlExample(apiBase)}</code>
            </pre>
          </article>
          <article className="docs-cardless docs-cardless--wide">
            <h3>{docsCopy.unifiedExample}</h3>
            <p>
              {docsCopy.exampleLead}
            </p>
            <div className="docs-example-controls">
              <label>
                {docsCopy.exampleModel}
                <select
                  aria-label={docsCopy.exampleModel}
                  value={selectedExampleModelId}
                  onChange={(event) => setSelectedExampleModelId(event.target.value)}
                >
                  {modelOptions.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.source === "custom" ? "Custom" : "Platform"} · {model.id}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={selectedExampleMode === "non-stream" ? "ghost-action ghost-action--bright" : "ghost-action"}
                onClick={() => setSelectedExampleMode("non-stream")}
              >
                {docsCopy.nonStream}
              </button>
              <button
                className={selectedExampleMode === "stream" ? "ghost-action ghost-action--bright" : "ghost-action"}
                onClick={() => setSelectedExampleMode("stream")}
              >
                {docsCopy.stream}
              </button>
              <button
                className="ghost-action ghost-action--bright"
                aria-label={docsCopy.copyExample}
                onClick={() => void copyText(exampleCurl, "docs-example")}
              >
                {docsCopy.copyExample}
              </button>
            </div>
            <small>
              {docsCopy.currentExample}: {selectedModelKind} · <code>{selectedExampleModelId}</code>
            </small>
            <pre>
              <code>{exampleCurl}</code>
            </pre>
          </article>
          <article className="docs-cardless docs-cardless--wide">
            <h3>{docsCopy.webFetchTitle}</h3>
            <p>{docsCopy.webFetchBody}</p>
            <small>
              {docsCopy.currentExample}: {docsCopy.selectedPlatform} · <code>{webFetchModelId}</code>
            </small>
            <pre>
              <code>{webFetchCurl}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{docsCopy.platformModels}</h3>
            <p>
              {docsCopy.platformBody}
            </p>
            <pre>
              <code>{`Available platform model ids:\n${platformModelList}`}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{docsCopy.customProviders}</h3>
            <p>{copy.docs.routingBody}</p>
            <pre>
              <code>{docsCopy.customOnboarding.replace("{models}", customModelList)}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{docsCopy.openAiProvider}</h3>
            <p>
              {docsCopy.openAiBody}
            </p>
            <pre>
              <code>{`Provider settings:
protocol: openai
base_url: https://api.example.com/v1
auth: Authorization: Bearer YOUR_PROVIDER_API_KEY

Public model id:
provider-slug:model-id`}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{docsCopy.anthropicProvider}</h3>
            <p>
              {docsCopy.anthropicBody}
            </p>
            <pre>
              <code>{`Provider settings:
protocol: anthropic
base_url: https://api.anthropic.com/v1
auth: x-api-key: YOUR_PROVIDER_API_KEY

Public model id:
claude:claude-sonnet-4-20250514`}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{docsCopy.commonErrors}</h3>
            <pre>
              <code>{docsCopy.errors}</code>
            </pre>
          </article>
          <article className="docs-cardless">
            <h3>{docsCopy.streaming}</h3>
            <pre>
              <code>{docsCopy.streamingBody}</code>
            </pre>
          </article>
        </section>
        {copiedLabel ? <div className="inline-success">{docsCopy.copied} {copiedLabel}</div> : null}
      </main>
    </div>
  );
}
