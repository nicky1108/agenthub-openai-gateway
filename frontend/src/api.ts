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

async function request(path: string, init?: RequestInit) {
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

  return response.json();
}

export async function getProviders(): Promise<Provider[]> {
  return request("/admin/providers");
}

export async function createProvider(payload: Record<string, unknown>): Promise<Provider> {
  return request("/admin/providers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getHealth(): Promise<ProviderHealth[]> {
  return request("/admin/health");
}

export async function getAccounts(): Promise<Account[]> {
  return request("/admin/accounts");
}

export async function createAccount(payload: Record<string, unknown>): Promise<Account> {
  return request("/admin/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getApiKeys(): Promise<ApiKey[]> {
  return request("/admin/api-keys");
}

export async function createApiKey(payload: Record<string, unknown>): Promise<CreatedApiKey> {
  return request("/admin/api-keys", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
