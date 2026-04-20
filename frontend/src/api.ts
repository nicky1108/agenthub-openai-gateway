const ADMIN_SECRET = "change-me";

export type Provider = {
  id: number;
  name: string;
  exposed_model: string;
  route_policy: string;
  http_enabled: boolean;
  cli_enabled: boolean;
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
