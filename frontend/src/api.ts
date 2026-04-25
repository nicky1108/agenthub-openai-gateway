export type AuthAccount = {
  account_id: string;
  workspace_id: string;
  name: string;
  email: string;
};

export type AuthProviderStatus = {
  email_password_enabled: boolean;
  github_enabled: boolean;
  google_enabled: boolean;
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
      public_account_id: string;
      workspace_id: string;
      local_account_id: string;
      email: string | null;
      status: string;
      api_keys: Array<{
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

export async function getPortalDashboard(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/portal/dashboard");
}

export async function getPortalCatalog(): Promise<PortalCatalog> {
  return request<PortalCatalog>("/portal/catalog");
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

export async function getAuthProviders(): Promise<AuthProviderStatus> {
  return request<AuthProviderStatus>("/auth/providers");
}
