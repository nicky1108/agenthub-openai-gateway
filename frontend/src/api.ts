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
