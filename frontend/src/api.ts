export type AuthAccount = {
  account_id: string;
  workspace_id: string;
  name: string;
  email: string;
  is_admin?: boolean;
};

export type AuthProviderStatus = {
  email_password_enabled: boolean;
  github_enabled: boolean;
  google_enabled: boolean;
};

export type AdminDashboardSummary = {
  total_requests: number;
  active_api_keys: number;
  error_rate: number;
  rate_limit_hits: number;
};

export type AdminDashboardTimeseriesBucket = {
  label: string;
  start_at: string;
  total_requests: number;
  error_requests: number;
  limited_requests: number;
};

export type AdminDashboardTimeseries = {
  window: "24h" | "7d";
  buckets: AdminDashboardTimeseriesBucket[];
};

export type AdminSettingsOverview = {
  gateway_host: string;
  gateway_port: number;
  frontend_base_url: string;
  database_scheme: string;
  email_password_enabled: boolean;
  github_oauth_enabled: boolean;
  google_oauth_enabled: boolean;
  admin_secret_configured: boolean;
};

export type AdminProviderHealthRecord = {
  name: string;
  route_policy: string;
  capabilities: {
    chat: boolean;
    stream: boolean;
    http: boolean;
    cli: boolean;
  };
};

export type AdminModelPricingRecord = {
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

export type AdminProviderRecord = {
  id: number;
  name: string;
  exposed_model: string;
  route_policy: string;
  http_enabled: boolean;
  cli_enabled: boolean;
  chat_capable: boolean;
  stream_capable: boolean;
  http_base_url?: string | null;
  http_api_key?: string | null;
  http_api_key_configured?: boolean;
  http_headers_json?: string | null;
  http_headers_configured?: boolean;
  cli_command?: string | null;
  cli_env_json?: string | null;
  cli_env_configured?: boolean;
};

export type AdminProviderModelRecord = {
  id: number;
  native_model: string;
  exposed_model_id: string;
  source: string;
  enabled: boolean;
  manually_overridden: boolean;
  pricing?: AdminModelPricingRecord | null;
};

export type AdminAccountRecord = {
  id: number;
  name: string;
  email?: string | null;
  status: string;
  is_admin: boolean;
  credit_balance?: number;
  public_account_id?: string | null;
  public_workspace_id?: string | null;
  notes?: string | null;
  created_at?: string | null;
};

export type AdminCreditLedgerEntry = {
  id: number;
  account_id: number;
  api_key_id?: number | null;
  usage_record_id?: number | null;
  entry_type: string;
  credits_delta: number;
  balance_after: number;
  usd_amount?: number | null;
  provider_name?: string | null;
  model_id?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_input_tokens?: number | null;
  pricing_source?: string | null;
  notes?: string | null;
  created_at: string;
};

export type AdminApiKeyRecord = {
  id: number;
  account_id: number;
  name: string;
  key_prefix: string;
  status: string;
  per_minute?: number | null;
  per_hour?: number | null;
  per_day?: number | null;
  last_used_at?: string | null;
};

export type AdminUsageOverview = {
  key_activity: Array<{
    api_key_id: number;
    account_id: number;
    name: string;
    key_prefix: string;
    status: string;
    last_used_at: string | null;
    total_requests: number;
    limited_requests: number;
  }>;
  by_provider: Record<string, number>;
  by_model: Record<string, number>;
};

export type AdminUsageRecord = {
  id: number;
  account_id: number;
  account_name?: string | null;
  api_key_id: number;
  api_key_name?: string | null;
  key_prefix?: string | null;
  provider_name?: string | null;
  model_id?: string | null;
  outcome: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_input_tokens?: number | null;
  usd_amount?: number | null;
  credits_charged?: number | null;
  pricing_source?: string | null;
  token_source?: string | null;
  created_at: string;
};

export type AdminUsageRecordsPage = {
  items: AdminUsageRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminAccountSyncSummary = {
  total_accounts: number;
  mirrored_accounts: number;
  accounts_needing_backfill: number;
  accounts_with_pending_sync: number;
  accounts_with_failed_sync: number;
  accounts_fully_converged: number;
};

export type AdminTestChatResponse = {
  choices: Array<{
    message: {
      content: string;
    };
  }>;
};

export type AdminTestChatChunk = {
  choices?: Array<{
    delta?: {
      content?: string;
    };
  }>;
};

export type ApiKeyRecord = {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string | null;
  last_used_at: string | null;
  per_minute: number | null;
  per_hour: number | null;
  per_day: number | null;
  total_requests: number;
  limited_requests: number;
};

export type PortalUsageRecord = {
  id: number;
  api_key_id: number;
  api_key_name?: string | null;
  key_prefix?: string | null;
  provider_name?: string | null;
  model_id?: string | null;
  outcome: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cached_input_tokens?: number | null;
  usd_amount?: number | null;
  credits_charged?: number | null;
  pricing_source?: string | null;
  token_source?: string | null;
  created_at: string;
};

export type PortalUsageRecordsPage = {
  items: PortalUsageRecord[];
  total: number;
  limit: number;
  offset: number;
};

export type CreatedApiKey = ApiKeyRecord & {
  api_key: string;
};

export type ApiKeyUpdatePayload = {
  name: string;
  per_minute: number | null;
  per_hour: number | null;
  per_day: number | null;
};

export type UserProviderRecord = {
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

export type UserProviderUpdatePayload = {
  name: string;
  protocol: string;
  base_url: string;
  api_key?: string;
  description?: string;
};

export type DashboardSummary = {
  credits_balance?: number;
  api_key_count?: number;
  request_count_24h?: number;
  request_count_7d?: number;
  platform_requests_24h?: number;
  custom_requests_24h?: number;
  local_provider_count?: number;
  account_sync?: {
    linked: boolean;
    local_account_id: string | null;
    upstream_account_id: string | null;
    upstream_workspace_id: string | null;
    local_mirror?: {
      public_account_id?: string;
      workspace_id?: string;
      local_account_id?: string;
      email?: string | null;
      status: string;
      api_keys?: Array<{
        public_api_key_id: string;
        local_api_key_id: string;
        name: string;
        key_prefix: string;
        status: string;
      }>;
    } | null;
    sync_queue?: {
      pending: number;
      failed: number;
    };
  };
};

export type RetrySyncResult = {
  status: string;
  sync_queue: {
    pending: number;
    failed: number;
  };
};

export type PlatformProviderRecord = {
  name: string;
  route_policy: string;
  http_enabled: boolean;
  cli_enabled: boolean;
  chat_capable: boolean;
  stream_capable: boolean;
  model_count: number;
};

export type CatalogModelRecord = {
  id: string;
  provider: string;
  source: string;
  enabled: boolean;
};

export type PortalCatalog = {
  platform_providers: PlatformProviderRecord[];
  platform_models: CatalogModelRecord[];
  custom_models: CatalogModelRecord[];
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
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("unauthorized");
    }
    const err = await response.json().catch(() => ({ detail: `request failed: ${response.status}` }));
    throw new Error(err.detail || `request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function requestAdmin<T>(path: string, _adminSecret: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `request failed: ${response.status}` }));
    throw new Error(err.detail || `request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function getPortalDashboard(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/portal/dashboard");
}

export async function getPortalCatalog(): Promise<PortalCatalog> {
  return request<PortalCatalog>("/portal/catalog");
}

export async function getPortalUsageRecords(
  params: {
    apiKeyId?: number | null;
    limit?: number;
    offset?: number;
  } = {},
): Promise<PortalUsageRecordsPage> {
  const search = new URLSearchParams();
  if (params.apiKeyId) search.set("api_key_id", String(params.apiKeyId));
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return request<PortalUsageRecordsPage>(`/user/usage/records${suffix}`);
}

export async function retryPortalSync(): Promise<RetrySyncResult> {
  return request<RetrySyncResult>("/portal/sync/retry", {
    method: "POST",
  });
}

export async function getUserApiKeys(): Promise<ApiKeyRecord[]> {
  return request<ApiKeyRecord[]>("/user/api-keys");
}

export async function createUserApiKey(payload: {
  name: string;
  per_minute?: number;
  per_hour?: number;
  per_day?: number;
}): Promise<CreatedApiKey> {
  const params = new URLSearchParams();
  params.append("name", payload.name);
  if (payload.per_minute) params.append("per_minute", String(payload.per_minute));
  if (payload.per_hour) params.append("per_hour", String(payload.per_hour));
  if (payload.per_day) params.append("per_day", String(payload.per_day));

  return request<CreatedApiKey>(`/user/api-keys?${params.toString()}`, {
    method: "POST",
  });
}

export async function deleteUserApiKey(keyId: number): Promise<{ status: string }> {
  return request<{ status: string }>(`/user/api-keys/${keyId}`, {
    method: "DELETE",
  });
}

export async function updateUserApiKey(
  keyId: number,
  payload: ApiKeyUpdatePayload,
): Promise<ApiKeyRecord> {
  return request<ApiKeyRecord>(`/user/api-keys/${keyId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getUserProviders(): Promise<UserProviderRecord[]> {
  return request<UserProviderRecord[]>("/user/providers");
}

export async function addUserProvider(payload: {
  name: string;
  protocol: string;
  base_url: string;
  api_key: string;
  description?: string;
}): Promise<UserProviderRecord> {
  const params = new URLSearchParams();
  params.append("name", payload.name);
  params.append("protocol", payload.protocol);
  params.append("base_url", payload.base_url);
  params.append("api_key", payload.api_key);
  if (payload.description) params.append("description", payload.description);

  return request<UserProviderRecord>(`/user/providers?${params.toString()}`, {
    method: "POST",
  });
}

export async function deleteUserProvider(providerId: number): Promise<{ status: string }> {
  return request<{ status: string }>(`/user/providers/${providerId}`, {
    method: "DELETE",
  });
}

export async function updateUserProvider(
  providerId: number,
  payload: UserProviderUpdatePayload,
): Promise<UserProviderRecord> {
  return request<UserProviderRecord>(`/user/providers/${providerId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function probeUserProvider(payload: {
  protocol: string;
  base_url: string;
  api_key: string;
  candidate_models?: string[];
}): Promise<ProviderProbeResult> {
  return request<ProviderProbeResult>("/user/providers/probe", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function probeSavedUserProvider(providerId: number): Promise<UserProviderRecord> {
  return request<UserProviderRecord>(`/user/providers/${providerId}/probe`, {
    method: "POST",
  });
}

// Auth API
export async function getCurrentAccount(): Promise<AuthAccount> {
  return request<AuthAccount>("/auth/me");
}

export async function loginWithPassword(payload: {
  email: string;
  password: string;
}): Promise<AuthAccount> {
  return request<AuthAccount>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function registerWithPassword(payload: {
  name: string;
  email: string;
  password: string;
}): Promise<AuthAccount> {
  return request<AuthAccount>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutSession(): Promise<{ status: string }> {
  return request<{ status: string }>("/auth/logout", {
    method: "POST",
  });
}

export async function getAdminDashboardSummary(adminSecret: string): Promise<AdminDashboardSummary> {
  return requestAdmin<AdminDashboardSummary>("/admin/dashboard/summary", adminSecret);
}

export async function getAdminDashboardTimeseries(
  adminSecret: string,
  window: "24h" | "7d",
): Promise<AdminDashboardTimeseries> {
  return requestAdmin<AdminDashboardTimeseries>(`/admin/dashboard/timeseries?window=${window}`, adminSecret);
}

export async function getAdminSettingsOverview(adminSecret: string): Promise<AdminSettingsOverview> {
  return requestAdmin<AdminSettingsOverview>("/admin/settings/overview", adminSecret);
}

export async function getAdminProviders(adminSecret: string): Promise<AdminProviderRecord[]> {
  return requestAdmin<AdminProviderRecord[]>("/admin/providers", adminSecret);
}

export async function getAdminHealth(adminSecret: string): Promise<AdminProviderHealthRecord[]> {
  return requestAdmin<AdminProviderHealthRecord[]>("/admin/health", adminSecret);
}

export async function getAdminProviderModels(
  adminSecret: string,
  providerName: string,
): Promise<AdminProviderModelRecord[]> {
  return requestAdmin<AdminProviderModelRecord[]>(`/admin/providers/${providerName}/models`, adminSecret);
}

export async function rediscoverAdminProviderModels(
  adminSecret: string,
  providerName: string,
): Promise<AdminProviderModelRecord[]> {
  return requestAdmin<AdminProviderModelRecord[]>(`/admin/providers/${providerName}/rediscover`, adminSecret, {
    method: "POST",
  });
}

export async function refreshAdminProviderPricing(
  adminSecret: string,
  providerName: string,
): Promise<AdminProviderModelRecord[]> {
  return requestAdmin<AdminProviderModelRecord[]>(`/admin/providers/${providerName}/pricing/refresh`, adminSecret, {
    method: "POST",
  });
}

export async function patchAdminProviderModel(
  adminSecret: string,
  providerName: string,
  nativeModel: string,
  payload: { exposed_model_id?: string; enabled?: boolean },
): Promise<AdminProviderModelRecord> {
  return requestAdmin<AdminProviderModelRecord>(`/admin/providers/${providerName}/models/${nativeModel}`, adminSecret, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function patchAdminProviderModelPricing(
  adminSecret: string,
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
): Promise<AdminModelPricingRecord> {
  return requestAdmin<AdminModelPricingRecord>(`/admin/providers/${providerName}/models/${nativeModel}/pricing`, adminSecret, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function createAdminProvider(
  adminSecret: string,
  payload: Record<string, unknown>,
): Promise<AdminProviderRecord> {
  return requestAdmin<AdminProviderRecord>("/admin/providers", adminSecret, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAdminProvider(
  adminSecret: string,
  providerName: string,
  payload: Record<string, unknown>,
): Promise<AdminProviderRecord> {
  return requestAdmin<AdminProviderRecord>(`/admin/providers/${providerName}`, adminSecret, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminProvider(adminSecret: string, providerName: string): Promise<AdminProviderRecord> {
  return requestAdmin<AdminProviderRecord>(`/admin/providers/${providerName}`, adminSecret, {
    method: "DELETE",
  });
}

export async function createAdminProviderModel(
  adminSecret: string,
  providerName: string,
  payload: { native_model: string; exposed_model_id: string; enabled: boolean },
): Promise<AdminProviderModelRecord> {
  return requestAdmin<AdminProviderModelRecord>(`/admin/providers/${providerName}/models`, adminSecret, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminProviderModel(
  adminSecret: string,
  providerName: string,
  nativeModel: string,
): Promise<AdminProviderModelRecord> {
  return requestAdmin<AdminProviderModelRecord>(`/admin/providers/${providerName}/models/${nativeModel}`, adminSecret, {
    method: "DELETE",
  });
}

export async function getAdminAccounts(adminSecret: string): Promise<AdminAccountRecord[]> {
  return requestAdmin<AdminAccountRecord[]>("/admin/accounts", adminSecret);
}

export async function createAdminAccount(
  adminSecret: string,
  payload: { name: string; email?: string | null; is_admin?: boolean; public_account_id?: string | null; public_workspace_id?: string | null; notes?: string | null },
): Promise<AdminAccountRecord> {
  return requestAdmin<AdminAccountRecord>("/admin/accounts", adminSecret, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAdminAccount(
  adminSecret: string,
  accountId: number,
  payload: { name?: string; email?: string | null; status?: string; is_admin?: boolean; public_account_id?: string | null; public_workspace_id?: string | null; notes?: string | null },
): Promise<AdminAccountRecord> {
  return requestAdmin<AdminAccountRecord>(`/admin/accounts/${accountId}`, adminSecret, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminAccount(adminSecret: string, accountId: number): Promise<AdminAccountRecord> {
  return requestAdmin<AdminAccountRecord>(`/admin/accounts/${accountId}`, adminSecret, {
    method: "DELETE",
  });
}

export async function getAdminAccountSyncSummary(adminSecret: string): Promise<AdminAccountSyncSummary> {
  return requestAdmin<AdminAccountSyncSummary>("/admin/account-sync/summary", adminSecret);
}

export async function adjustAdminAccountCredits(
  adminSecret: string,
  accountId: number,
  payload: { credits_delta: number; notes?: string },
): Promise<AdminAccountRecord> {
  return requestAdmin<AdminAccountRecord>(`/admin/accounts/${accountId}/credits/adjust`, adminSecret, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getAdminAccountCreditLedger(
  adminSecret: string,
  accountId: number,
): Promise<AdminCreditLedgerEntry[]> {
  return requestAdmin<AdminCreditLedgerEntry[]>(`/admin/accounts/${accountId}/credits/ledger`, adminSecret);
}

export async function getAdminApiKeys(adminSecret: string): Promise<AdminApiKeyRecord[]> {
  return requestAdmin<AdminApiKeyRecord[]>("/admin/api-keys", adminSecret);
}

export async function createAdminApiKey(
  adminSecret: string,
  payload: { account_id: number; name: string; per_minute?: number | null; per_hour?: number | null; per_day?: number | null },
): Promise<AdminApiKeyRecord & { api_key: string }> {
  return requestAdmin<AdminApiKeyRecord & { api_key: string }>("/admin/api-keys", adminSecret, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeAdminApiKey(adminSecret: string, keyId: number): Promise<AdminApiKeyRecord> {
  return requestAdmin<AdminApiKeyRecord>(`/admin/api-keys/${keyId}/revoke`, adminSecret, {
    method: "POST",
  });
}

export async function updateAdminApiKey(
  adminSecret: string,
  keyId: number,
  payload: { name?: string; status?: string; per_minute?: number | null; per_hour?: number | null; per_day?: number | null },
): Promise<AdminApiKeyRecord> {
  return requestAdmin<AdminApiKeyRecord>(`/admin/api-keys/${keyId}`, adminSecret, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminApiKey(adminSecret: string, keyId: number): Promise<AdminApiKeyRecord> {
  return requestAdmin<AdminApiKeyRecord>(`/admin/api-keys/${keyId}`, adminSecret, {
    method: "DELETE",
  });
}

export async function getAdminUsageOverview(adminSecret: string): Promise<AdminUsageOverview> {
  return requestAdmin<AdminUsageOverview>("/admin/usage/overview", adminSecret);
}

export async function getAdminUsageRecords(
  adminSecret: string,
  params: {
    accountId?: number | null;
    apiKeyId?: number | null;
    limit?: number;
    offset?: number;
  } = {},
): Promise<AdminUsageRecordsPage> {
  const search = new URLSearchParams();
  if (params.accountId) search.set("account_id", String(params.accountId));
  if (params.apiKeyId) search.set("api_key_id", String(params.apiKeyId));
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return requestAdmin<AdminUsageRecordsPage>(`/admin/usage/records${suffix}`, adminSecret);
}

export async function sendAdminTestChat(
  adminSecret: string,
  payload: { model: string; messages: Array<{ role: string; content: string }>; temperature?: number | null; top_p?: number | null; max_tokens?: number | null },
): Promise<AdminTestChatResponse> {
  return requestAdmin<AdminTestChatResponse>("/admin/test-chat", adminSecret, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function streamAdminTestChat(
  _adminSecret: string,
  payload: { model: string; messages: Array<{ role: string; content: string }>; temperature?: number | null; top_p?: number | null; max_tokens?: number | null },
  options: { signal?: AbortSignal; onChunk: (chunk: AdminTestChatChunk) => void },
): Promise<void> {
  const response = await fetch("/admin/test-chat", {
    method: "POST",
    credentials: "same-origin",
    signal: options.signal,
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({ ...payload, stream: true }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `request failed: ${response.status}` }));
    throw new Error(err.detail || `request failed: ${response.status}`);
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
      const dataLines = eventBlock.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6).trim());
      if (dataLines.length === 0) continue;
      const data = dataLines.join("\n");
      if (data === "[DONE]") return;
      options.onChunk(JSON.parse(data) as AdminTestChatChunk);
    }
    if (done) return;
  }
}

export async function getAuthProviders(): Promise<AuthProviderStatus> {
  return request<AuthProviderStatus>("/auth/providers");
}
