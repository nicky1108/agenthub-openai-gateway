const ADMIN_SECRET = "change-me";

export type Provider = {
  id: number;
  name: string;
  exposed_model: string;
  route_policy: string;
  http_enabled: boolean;
  cli_enabled: boolean;
  chat_capable: boolean;
  stream_capable: boolean;
  http_base_url: string | null;
  cli_command: string | null;
};

export type ProviderHealth = {
  name: string;
  route_policy: string;
  capabilities: {
    chat: boolean;
    stream: boolean;
    http: boolean;
    cli: boolean;
  };
};

export type Account = {
  id: number;
  name: string;
  status: string;
  credit_balance: number;
  notes?: string | null;
};

export type AuthAccount = {
  id: number;
  name: string;
  email: string | null;
};

export type AuthProviderStatus = {
  email_password_enabled: boolean;
  github_enabled: boolean;
  google_enabled: boolean;
};

export type ApiKey = {
  id: number;
  account_id: number;
  name: string;
  key_prefix: string;
  status: string;
  per_minute: number | null;
  per_hour: number | null;
  per_day: number | null;
  last_used_at: string | null;
};

export type CreatedApiKey = ApiKey & {
  api_key: string;
};

export type UsageSummary = {
  account_id: number;
  api_key_id: number;
  total_requests: number;
  limited_requests: number;
  by_provider: Record<string, number>;
  by_model: Record<string, number>;
};

export type UsageActivityKey = {
  api_key_id: number;
  account_id: number;
  name: string;
  key_prefix: string;
  status: string;
  last_used_at: string | null;
  total_requests: number;
  limited_requests: number;
};

export type UsageOverview = {
  key_activity: UsageActivityKey[];
  by_provider: Record<string, number>;
  by_model: Record<string, number>;
};

export type ProviderModel = {
  id: number;
  native_model: string;
  exposed_model_id: string;
  source: string;
  enabled: boolean;
  manually_overridden: boolean;
  pricing: ModelPricing | null;
};

export type ModelPricing = {
  provider_name: string;
  native_model: string;
  source_kind: string;
  source_url: string;
  source_label: string;
  currency: string;
  unit: string;
  input_price: number | null;
  cached_input_price: number | null;
  output_price: number | null;
  input_price_high: number | null;
  cached_input_price_high: number | null;
  output_price_high: number | null;
  high_price_threshold_tokens: number | null;
  notes: string | null;
  synced_at: string;
};

export type DashboardTimeseriesBucket = {
  label: string;
  start_at: string;
  total_requests: number;
  error_requests: number;
  limited_requests: number;
};

export type DashboardTimeseries = {
  window: "24h" | "7d";
  buckets: DashboardTimeseriesBucket[];
};

export type SettingsOverview = {
  gateway_host: string;
  gateway_port: number;
  frontend_base_url: string;
  database_scheme: string;
  email_password_enabled: boolean;
  github_oauth_enabled: boolean;
  google_oauth_enabled: boolean;
  admin_secret_configured: boolean;
};

export type AdminTestChatResponse = {
  id: string;
  object: string;
  model: string;
  choices: Array<{
    index: number;
    message: { role: string; content: string };
    finish_reason: string | null;
  }>;
};

export type AdminTestChatChunk = {
  id: string;
  object: string;
  model: string;
  choices?: Array<{
    index: number;
    delta?: { content?: string };
    finish_reason?: string | null;
  }>;
};

export type CreditLedgerEntry = {
  id: number;
  account_id: number;
  api_key_id: number | null;
  usage_record_id: number | null;
  entry_type: string;
  credits_delta: number;
  balance_after: number;
  usd_amount: number | null;
  provider_name: string | null;
  model_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  pricing_source: string | null;
  notes: string | null;
  created_at: string;
};

export type PortalUsageRecord = {
  id: number;
  api_key_id: number;
  provider_name: string | null;
  model_id: string | null;
  outcome: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  usd_amount: number | null;
  credits_charged: number | null;
  created_at: string;
};

export type PortalDashboard = {
  credits_balance: number;
  api_key_count: number;
  request_count_24h: number;
  request_count_7d: number;
  platform_requests_24h: number;
  custom_requests_24h: number;
  local_provider_count: number;
  recent_usage: PortalUsageRecord[];
  credit_ledger: CreditLedgerEntry[];
};

export type PortalModelRecord = {
  id: string;
  provider: string;
  source: string;
  enabled: boolean;
};

export type PortalCatalog = {
  platform_models: PortalModelRecord[];
  custom_models: PortalModelRecord[];
};

export type ProviderPreset = {
  id: string;
  display_name: string;
  slug: string;
  protocol: string;
  base_url: string;
  description: string;
  recommended_models: string[];
};

export type UserApiKey = ApiKey & {
  created_at: string;
  total_requests: number;
  limited_requests: number;
};

export type UserProvider = {
  id: number;
  account_id: string;
  slug: string;
  name: string;
  protocol: string;
  base_url: string;
  description: string | null;
  status: string;
  last_probe_at: string | null;
  last_probe_ok: boolean | null;
  last_probe_model: string | null;
  last_probe_detail: string | null;
  last_detected_models: string[];
};

export type ProviderProbeResult = {
  models_endpoint_supported: boolean;
  detected_models: string[];
  completion_probe_ok: boolean;
  completion_probe_model: string | null;
  detail: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "content-type": "application/json",
      "x-admin-secret": ADMIN_SECRET,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function getProviders(): Promise<Provider[]> {
  return request<Provider[]>("/admin/providers");
}

export async function createProvider(payload: Record<string, unknown>): Promise<Provider> {
  return request<Provider>("/admin/providers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getHealth(): Promise<ProviderHealth[]> {
  return request<ProviderHealth[]>("/admin/health");
}

export async function getAccounts(): Promise<Account[]> {
  return request<Account[]>("/admin/accounts");
}

export async function createAccount(payload: Record<string, unknown>): Promise<Account> {
  return request<Account>("/admin/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function adjustAccountCredits(
  accountId: number,
  payload: { credits_delta: number; notes?: string | null },
): Promise<Account> {
  return request<Account>(`/admin/accounts/${accountId}/credits/adjust`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getAccountCreditLedger(accountId: number): Promise<CreditLedgerEntry[]> {
  return request<CreditLedgerEntry[]>(`/admin/accounts/${accountId}/credits/ledger`);
}

export async function getApiKeys(): Promise<ApiKey[]> {
  return request<ApiKey[]>("/admin/api-keys");
}

export async function createApiKey(payload: Record<string, unknown>): Promise<CreatedApiKey> {
  return request<CreatedApiKey>("/admin/api-keys", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeApiKey(keyId: number): Promise<ApiKey> {
  return request<ApiKey>(`/admin/api-keys/${keyId}/revoke`, {
    method: "POST",
  });
}

export async function getApiKeyUsage(keyId: number): Promise<UsageSummary> {
  const payload = await request<Partial<UsageSummary>>(`/admin/api-keys/${keyId}/usage`);
  return {
    account_id: payload.account_id ?? 0,
    api_key_id: payload.api_key_id ?? keyId,
    total_requests: payload.total_requests ?? 0,
    limited_requests: payload.limited_requests ?? 0,
    by_provider: payload.by_provider ?? {},
    by_model: payload.by_model ?? {},
  };
}

export async function getUsageOverview(): Promise<UsageOverview> {
  const payload = await request<Partial<UsageOverview>>("/admin/usage/overview");
  return {
    key_activity: payload.key_activity ?? [],
    by_provider: payload.by_provider ?? {},
    by_model: payload.by_model ?? {},
  };
}

export async function getProviderModels(providerName: string): Promise<ProviderModel[]> {
  return request<ProviderModel[]>(`/admin/providers/${providerName}/models`);
}

export async function rediscoverProviderModels(providerName: string): Promise<ProviderModel[]> {
  return request<ProviderModel[]>(`/admin/providers/${providerName}/rediscover`, {
    method: "POST",
  });
}

export async function patchProviderModel(
  providerName: string,
  nativeModel: string,
  payload: { exposed_model_id?: string; enabled?: boolean },
): Promise<ProviderModel> {
  return request<ProviderModel>(`/admin/providers/${providerName}/models/${nativeModel}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function createProviderModel(
  providerName: string,
  payload: { native_model: string; exposed_model_id: string; enabled: boolean },
): Promise<ProviderModel> {
  return request<ProviderModel>(`/admin/providers/${providerName}/models`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function refreshProviderPricing(providerName: string): Promise<ProviderModel[]> {
  return request<ProviderModel[]>(`/admin/providers/${providerName}/pricing/refresh`, {
    method: "POST",
  });
}

export async function patchProviderModelPricing(
  providerName: string,
  nativeModel: string,
  payload: {
    input_price?: number | null;
    cached_input_price?: number | null;
    output_price?: number | null;
    input_price_high?: number | null;
    cached_input_price_high?: number | null;
    output_price_high?: number | null;
    high_price_threshold_tokens?: number | null;
    notes?: string | null;
  },
): Promise<ModelPricing> {
  return request<ModelPricing>(`/admin/providers/${providerName}/models/${nativeModel}/pricing`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`auth request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function getCurrentAccount(): Promise<AuthAccount> {
  return authRequest<AuthAccount>("/auth/me");
}

export async function loginWithPassword(payload: {
  email: string;
  password: string;
}): Promise<AuthAccount> {
  return authRequest<AuthAccount>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function registerWithPassword(payload: {
  name: string;
  email: string;
  password: string;
}): Promise<AuthAccount> {
  return authRequest<AuthAccount>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutSession(): Promise<{ status: string }> {
  return authRequest<{ status: string }>("/auth/logout", {
    method: "POST",
  });
}

export async function getDashboardSummary(): Promise<{
  total_requests: number;
  active_api_keys: number;
  error_rate: number;
  rate_limit_hits: number;
}> {
  return request("/admin/dashboard/summary");
}

export async function getDashboardTimeseries(window: "24h" | "7d"): Promise<DashboardTimeseries> {
  return request<DashboardTimeseries>(`/admin/dashboard/timeseries?window=${window}`);
}

export async function getSettingsOverview(): Promise<SettingsOverview> {
  return request<SettingsOverview>("/admin/settings/overview");
}

export async function sendAdminTestChat(payload: {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
}): Promise<AdminTestChatResponse> {
  return request<AdminTestChatResponse>("/admin/test-chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function streamAdminTestChat(
  payload: {
    model: string;
    messages: Array<{ role: string; content: string }>;
    temperature?: number | null;
    top_p?: number | null;
    max_tokens?: number | null;
  },
  options: {
    signal?: AbortSignal;
    onChunk: (chunk: AdminTestChatChunk) => void;
  },
): Promise<void> {
  const response = await fetch("/admin/test-chat", {
    method: "POST",
    signal: options.signal,
    headers: {
      "content-type": "application/json",
      "x-admin-secret": ADMIN_SECRET,
    },
    body: JSON.stringify({
      ...payload,
      stream: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("stream unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const eventBlock of events) {
      const dataLines = eventBlock
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6).trim());

      if (dataLines.length === 0) {
        continue;
      }

      const data = dataLines.join("\n");
      if (data === "[DONE]") {
        return;
      }

      options.onChunk(JSON.parse(data) as AdminTestChatChunk);
    }

    if (done) {
      return;
    }
  }
}

export async function getAuthProviders(): Promise<AuthProviderStatus> {
  const response = await fetch("/auth/providers");
  if (!response.ok) {
    throw new Error(`auth request failed: ${response.status}`);
  }
  return response.json() as Promise<AuthProviderStatus>;
}

export async function getPortalDashboard(): Promise<PortalDashboard> {
  return authRequest<PortalDashboard>("/portal/dashboard");
}

export async function getPortalCatalog(): Promise<PortalCatalog> {
  return authRequest<PortalCatalog>("/portal/catalog");
}

export async function getProviderPresets(): Promise<ProviderPreset[]> {
  return authRequest<ProviderPreset[]>("/portal/provider-presets");
}

export async function getUserApiKeys(): Promise<UserApiKey[]> {
  return authRequest<UserApiKey[]>("/portal/api-keys");
}

export async function createUserApiKey(payload: {
  name: string;
  per_minute?: number;
  per_hour?: number;
  per_day?: number;
}): Promise<CreatedApiKey & UserApiKey> {
  const params = new URLSearchParams();
  params.append("name", payload.name);
  if (payload.per_minute) params.append("per_minute", String(payload.per_minute));
  if (payload.per_hour) params.append("per_hour", String(payload.per_hour));
  if (payload.per_day) params.append("per_day", String(payload.per_day));
  return authRequest<CreatedApiKey & UserApiKey>(`/portal/api-keys?${params.toString()}`, {
    method: "POST",
  });
}

export async function deleteUserApiKey(keyId: number): Promise<{ status: string }> {
  return authRequest<{ status: string }>(`/portal/api-keys/${keyId}/revoke`, {
    method: "POST",
  });
}

export async function getUserProviders(): Promise<UserProvider[]> {
  return authRequest<UserProvider[]>("/portal/providers");
}

export async function createUserProvider(payload: {
  name: string;
  protocol: string;
  base_url: string;
  api_key: string;
  description?: string;
}): Promise<UserProvider> {
  const params = new URLSearchParams();
  params.append("name", payload.name);
  params.append("protocol", payload.protocol);
  params.append("base_url", payload.base_url);
  params.append("api_key", payload.api_key);
  if (payload.description) params.append("description", payload.description);
  return authRequest<UserProvider>(`/portal/providers?${params.toString()}`, {
    method: "POST",
  });
}

export async function deleteUserProvider(providerId: number): Promise<{ status: string }> {
  return authRequest<{ status: string }>(`/portal/providers/${providerId}`, {
    method: "DELETE",
  });
}

export async function probeUserProvider(providerId: number): Promise<UserProvider> {
  return authRequest<UserProvider>(`/portal/providers/${providerId}/probe`, {
    method: "POST",
  });
}
