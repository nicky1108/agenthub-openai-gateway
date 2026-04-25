import type { CatalogModelRecord } from "../api";

export type ExampleMode = "non-stream" | "stream";

const DEFAULT_PLATFORM_MODEL_ID = "codex:gpt-5.4";
const DEFAULT_CUSTOM_MODEL_ID = "minimax-cn:MiniMax-M2.7";
const DEFAULT_USER_MESSAGE = "Reply with only OK";

export function resolveApiBaseUrl(origin?: string): string {
  const baseOrigin =
    origin ?? (typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:3002");
  return `${baseOrigin}/v1`;
}

export function pickDefaultPlatformModelId(models: CatalogModelRecord[]): string {
  return models.find((model) => model.enabled)?.id ?? DEFAULT_PLATFORM_MODEL_ID;
}

export function pickDefaultCustomModelId(models: CatalogModelRecord[]): string {
  return models.find((model) => model.enabled)?.id ?? DEFAULT_CUSTOM_MODEL_ID;
}

export function pickDefaultModelId(models: CatalogModelRecord[]): string {
  return models.find((model) => model.enabled)?.id ?? DEFAULT_PLATFORM_MODEL_ID;
}

export function buildModelsListCurlExample(apiBaseUrl: string): string {
  return `curl ${apiBaseUrl}/models \\\n  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY"`;
}

export function buildChatCurlExample(options: {
  apiBaseUrl: string;
  modelId: string;
  mode: ExampleMode;
  userMessage?: string;
}): string {
  const userMessage = options.userMessage ?? DEFAULT_USER_MESSAGE;
  return [
    `curl ${options.apiBaseUrl}/chat/completions \\`,
    `  -H "Authorization: Bearer YOUR_GATEWAY_API_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    "  -d '{",
    `    \"model\": \"${options.modelId}\",`,
    `    \"messages\": [{\"role\": \"user\", \"content\": \"${userMessage}\"}],`,
    `    \"stream\": ${options.mode === "stream" ? "true" : "false"}`,
    "  }'",
    ...(options.mode === "stream" ? ["", "# stream terminates with: data: [DONE]"] : []),
  ].join("\n");
}
