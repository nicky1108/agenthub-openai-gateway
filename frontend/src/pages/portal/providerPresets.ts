export type ProviderPreset = {
  id: string;
  label: string;
  defaultName: string;
  protocol: "openai" | "anthropic";
  baseUrl: string;
  note: string;
  recommendedModels: string[];
};

export const providerPresets: ProviderPreset[] = [
  {
    id: "openrouter",
    label: "OpenRouter",
    defaultName: "openrouter",
    protocol: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
    note: "OpenRouter exposes an OpenAI-compatible base URL and uses bearer API keys.",
    recommendedModels: ["openai/gpt-4.1", "anthropic/claude-sonnet-4"],
  },
  {
    id: "groq",
    label: "Groq",
    defaultName: "groq",
    protocol: "openai",
    baseUrl: "https://api.groq.com/openai/v1",
    note: "Groq keeps an OpenAI-compatible endpoint under /openai/v1.",
    recommendedModels: ["llama-3.3-70b-versatile", "qwen-qwq-32b"],
  },
  {
    id: "together",
    label: "Together AI",
    defaultName: "together",
    protocol: "openai",
    baseUrl: "https://api.together.xyz/v1",
    note: "Together supports the OpenAI SDK shape directly on api.together.xyz/v1.",
    recommendedModels: ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3"],
  },
  {
    id: "fireworks",
    label: "Fireworks AI",
    defaultName: "fireworks",
    protocol: "openai",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    note: "Fireworks exposes an OpenAI-compatible inference endpoint.",
    recommendedModels: ["accounts/fireworks/models/llama-v3p1-70b-instruct", "accounts/fireworks/models/deepseek-v3"],
  },
  {
    id: "minimax",
    label: "MiniMax",
    defaultName: "minimax-cn",
    protocol: "openai",
    baseUrl: "https://api.minimaxi.com/v1",
    note: "MiniMax responds on api.minimaxi.com/v1 and often does not expose /models, so use the recommended model list and the test-connection probe.",
    recommendedModels: [
      "MiniMax-M2.7",
      "MiniMax-M2.7-highspeed",
      "MiniMax-M2.5",
      "MiniMax-M2.5-highspeed",
      "MiniMax-M2.1",
      "MiniMax-M2.1-highspeed",
      "MiniMax-M2",
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    defaultName: "claude",
    protocol: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    note: "Anthropic-compatible providers use /v1/messages plus x-api-key and anthropic-version headers.",
    recommendedModels: [
      "claude-sonnet-4-20250514",
      "claude-3-7-sonnet-latest",
      "claude-3-5-haiku-latest",
    ],
  },
  {
    id: "other",
    label: "Other OpenAI-compatible",
    defaultName: "custom-provider",
    protocol: "openai",
    baseUrl: "",
    note: "Use this when your provider exposes /v1/chat/completions with bearer auth.",
    recommendedModels: [],
  },
];
