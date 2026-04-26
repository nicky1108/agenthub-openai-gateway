import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "./App";

function setPath(pathname: string): void {
  window.history.pushState({}, "", pathname);
}

describe("public gateway frontend", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the public landing page when signed out", async () => {
    setPath("/");

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = typeof input === "string" ? input : String(input);
        if (path.endsWith("/auth/me")) {
          return new Response(JSON.stringify({ detail: "unauthorized" }), { status: 401 });
        }
        if (path.endsWith("/auth/providers")) {
          return new Response(
            JSON.stringify({
              email_password_enabled: true,
              github_enabled: true,
              google_enabled: true,
            }),
          );
        }
        return new Response(JSON.stringify({}));
      }),
    );

    render(<App />);

    expect(await screen.findByText("统一 AI 模型接入的标准 API。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "注册" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Admin" })).toBeNull();
  });

  it("renders the portal shell when authenticated", async () => {
    setPath("/portal/api-keys");

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = typeof input === "string" ? input : String(input);
        if (path.endsWith("/auth/me")) {
          return new Response(
            JSON.stringify({
              account_id: "acct_123",
              workspace_id: "ws_personal_123",
              name: "Nicky",
              email: "nicky@example.com",
              is_admin: false,
            }),
          );
        }
        if (path.endsWith("/auth/providers")) {
          return new Response(
            JSON.stringify({
              email_password_enabled: true,
              github_enabled: false,
              google_enabled: false,
            }),
          );
        }
        if (path.endsWith("/portal/dashboard")) {
          return new Response(
            JSON.stringify({
              credits_balance: 12.5,
              request_count_24h: 8,
              request_count_7d: 44,
              platform_requests_24h: 5,
              custom_requests_24h: 3,
              local_provider_count: 1,
            }),
          );
        }
        if (path.endsWith("/portal/catalog")) {
          return new Response(
            JSON.stringify({
              platform_providers: [],
              platform_models: [],
              custom_models: [],
            }),
          );
        }
        if (path.includes("/portal/usage/records")) {
          return new Response(
            JSON.stringify({
              items: [],
              total: 0,
              limit: 25,
              offset: 0,
            }),
          );
        }
        if (path.endsWith("/user/api-keys")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                name: "primary",
                key_prefix: "agk_1234",
                created_at: null,
                last_used_at: null,
                per_minute: null,
                per_hour: null,
                per_day: null,
                total_requests: 0,
                limited_requests: 0,
              },
            ]),
          );
        }
        if (path.endsWith("/user/providers")) {
          return new Response(
            JSON.stringify([
              {
                id: 7,
                account_id: "acct_123",
                slug: "custom-provider",
                name: "Custom Provider",
                base_url: "https://api.example.com/v1",
                description: null,
                status: "active",
              },
            ]),
          );
        }
        return new Response(JSON.stringify({ status: "ok" }));
      }),
    );

    render(<App />);

    expect(await screen.findByRole("navigation", { name: "Portal navigation" })).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "API Key 管理" })).toBeTruthy();
    });
    expect(screen.getByText("nicky@example.com")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Admin" })).toBeNull();
  });

  it("redirects unauthenticated admin visits to the standard login page", async () => {
    setPath("/admin");

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = typeof input === "string" ? input : String(input);
        if (path.endsWith("/auth/me")) {
          return new Response(JSON.stringify({ detail: "unauthorized" }), { status: 401 });
        }
        if (path.endsWith("/auth/providers")) {
          return new Response(
            JSON.stringify({
              email_password_enabled: true,
              github_enabled: false,
              google_enabled: false,
            }),
          );
        }
        return new Response(JSON.stringify({}));
      }),
    );

    render(<App />);

    expect((await screen.findAllByRole("button", { name: "登录" })).length).toBeGreaterThan(0);
  });

  it("renders the admin console when the signed-in account is an admin", async () => {
    setPath("/admin");

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = typeof input === "string" ? input : String(input);
        if (path.endsWith("/auth/me")) {
          return new Response(
            JSON.stringify({
              account_id: "acct_admin",
              workspace_id: "ws_admin",
              name: "Nicky",
              email: "nicky.liyang@gmail.com",
              is_admin: true,
            }),
          );
        }
        if (path.endsWith("/auth/providers")) {
          return new Response(
            JSON.stringify({
              email_password_enabled: true,
              github_enabled: false,
              google_enabled: false,
            }),
          );
        }
        if (path.endsWith("/admin/dashboard/summary")) {
          return new Response(
            JSON.stringify({
              total_requests: 128,
              active_api_keys: 4,
              error_rate: 0.01,
              rate_limit_hits: 2,
            }),
          );
        }
        if (path.includes("/admin/dashboard/timeseries")) {
          return new Response(
            JSON.stringify({
              window: "24h",
              buckets: [
                {
                  label: "00:00",
                  start_at: "2026-04-25T00:00:00Z",
                  total_requests: 10,
                  error_requests: 0,
                  limited_requests: 0,
                },
                {
                  label: "01:00",
                  start_at: "2026-04-25T01:00:00Z",
                  total_requests: 20,
                  error_requests: 1,
                  limited_requests: 1,
                },
              ],
            }),
          );
        }
        if (path.endsWith("/admin/account-sync/summary")) {
          return new Response(
            JSON.stringify({
              total_accounts: 2,
              mirrored_accounts: 1,
              accounts_needing_backfill: 1,
              accounts_with_pending_sync: 0,
              accounts_with_failed_sync: 0,
              accounts_fully_converged: 1,
            }),
          );
        }
        if (path.endsWith("/admin/settings/overview")) {
          return new Response(
            JSON.stringify({
              gateway_host: "127.0.0.1",
              gateway_port: 8788,
              frontend_base_url: "http://127.0.0.1:3000",
              database_scheme: "sqlite",
              email_password_enabled: true,
              github_oauth_enabled: false,
              google_oauth_enabled: false,
              admin_secret_configured: true,
            }),
          );
        }
        if (path.endsWith("/admin/providers")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                name: "codex",
                exposed_model: "default",
                route_policy: "fixed-http",
                http_enabled: true,
                cli_enabled: false,
                chat_capable: true,
                stream_capable: true,
              },
            ]),
          );
        }
        if (path.endsWith("/admin/health")) {
          return new Response(JSON.stringify([]));
        }
        if (path.endsWith("/admin/accounts")) {
          return new Response(JSON.stringify([
            {
              id: 1,
              name: "Nicky",
              email: "nicky.liyang@gmail.com",
              status: "active",
              is_admin: true,
              credit_balance: 100,
              public_account_id: "acct_admin",
              public_workspace_id: "ws_admin",
              notes: null,
              created_at: "2026-04-25T00:00:00Z",
            },
          ]));
        }
        if (path.endsWith("/admin/accounts/1/credits/ledger")) {
          return new Response(JSON.stringify([]));
        }
        if (path.endsWith("/admin/api-keys")) {
          return new Response(JSON.stringify([]));
        }
        if (path.endsWith("/admin/usage/overview")) {
          return new Response(
            JSON.stringify({
              key_activity: [
                {
                  api_key_id: 1,
                  account_id: 1,
                  name: "primary",
                  key_prefix: "9ac99097",
                  status: "active",
                  last_used_at: "2026-04-25T00:00:00Z",
                  total_requests: 3,
                  limited_requests: 1,
                },
              ],
              by_provider: { codex: 3 },
              by_model: { "codex:gpt-5.4": 3 },
            }),
          );
        }
        if (path.includes("/admin/usage/records")) {
          return new Response(
            JSON.stringify({
              items: [
                {
                  id: 1,
                  account_id: 1,
                  account_name: "Nicky",
                  api_key_id: 1,
                  api_key_name: "primary",
                  key_prefix: "9ac99097",
                  provider_name: "codex",
                  model_id: "codex:gpt-5.4",
                  outcome: "success",
                  input_tokens: 10,
                  output_tokens: 2,
                  cached_input_tokens: 0,
                  usd_amount: 0.001,
                  credits_charged: 0.1,
                  pricing_source: "official",
                  token_source: "provider_usage",
                  created_at: "2026-04-25T00:00:00Z",
                },
              ],
              total: 1,
              limit: 25,
              offset: 0,
            }),
          );
        }
        if (path.includes("/admin/providers/codex/models")) {
          return new Response(JSON.stringify([]));
        }
        return new Response(JSON.stringify({ detail: `unhandled ${path}` }), { status: 404 });
      }),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Admin Console" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Admin navigation" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Providers" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Permissions" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Providers" }));
    fireEvent.click(screen.getByRole("button", { name: "新建" }));
    expect(screen.getByRole("dialog", { name: "注册 Provider" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));

    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    fireEvent.click(screen.getByRole("button", { name: "新建" }));
    expect(screen.getByRole("dialog", { name: "创建账户" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));

    fireEvent.click(screen.getByRole("button", { name: "Usage" }));
    expect(screen.getByRole("heading", { name: "Usage 明细" })).toBeTruthy();
    expect(screen.getAllByRole("columnheader", { name: "Provider" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("codex").length).toBeGreaterThan(0);
  });
});
