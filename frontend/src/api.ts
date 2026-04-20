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

export async function getAuthProviders(): Promise<AuthProviderStatus> {
  const response = await fetch("/auth/providers");
  if (!response.ok) {
    throw new Error(`auth request failed: ${response.status}`);
  }
  return response.json() as Promise<AuthProviderStatus>;
}
