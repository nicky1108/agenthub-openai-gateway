import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    window.location.hash = "";
    const storage = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      },
      clear: () => {
        storage.clear();
      },
    });
    const getPath = (input: RequestInfo | URL): string => {
      if (typeof input === "string") {
        return input;
      }
      if (input instanceof URL) {
        return input.pathname;
      }
      if ("url" in input) {
        return input.url;
      }
      return String(input);
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = getPath(input);
        if (path.endsWith("/auth/me")) {
          return new Response(
            JSON.stringify({
              id: 1,
              name: "default-account",
              email: "alice@example.com",
            }),
          );
        }
        if (path.endsWith("/auth/providers")) {
          return new Response(
            JSON.stringify({
              email_password_enabled: true,
              github_enabled: true,
              google_enabled: false,
            }),
          );
        }
        if (
          path.endsWith("/admin/providers") &&
          (!init || init.method === undefined || init.method === "GET")
        ) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                name: "codex",
                exposed_model: "gpt-5.4",
                route_policy: "http-first",
                http_enabled: true,
                cli_enabled: false,
                chat_capable: true,
                stream_capable: true,
                http_base_url: "http://127.0.0.1:9999",
                cli_command: null,
              },
            ]),
          );
        }
        if (path.endsWith("/admin/providers/codex/models")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                native_model: "gpt-5.4",
                exposed_model_id: "codex:gpt-5.4",
                source: "discovered",
                enabled: true,
                manually_overridden: false,
                pricing: {
                  provider_name: "codex",
                  native_model: "gpt-5.4",
                  source_kind: "official_snapshot",
                  source_url: "https://openai.com/api/pricing/",
                  source_label: "OpenAI API Pricing",
                  currency: "USD",
                  unit: "1M tokens",
                  input_price: 2.5,
                  cached_input_price: 0.25,
                  output_price: 15,
                  input_price_high: 5,
                  cached_input_price_high: 0.5,
                  output_price_high: 22.5,
                  high_price_threshold_tokens: 270000,
                  notes: "Standard pricing. Higher short-context price applies above 270k context.",
                  synced_at: "2026-04-21T00:00:00Z",
                },
              },
            ]),
          );
        }
        if (
          path.endsWith("/admin/accounts") &&
          (!init || init.method === undefined || init.method === "GET")
        ) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                name: "default-account",
                status: "active",
                credit_balance: 500,
              },
            ]),
          );
        }
        if (path.endsWith("/admin/accounts/1/credits/ledger")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                account_id: 1,
                api_key_id: null,
                usage_record_id: null,
                entry_type: "manual_adjustment",
                credits_delta: 500,
                balance_after: 500,
                usd_amount: null,
                provider_name: null,
                model_id: null,
                input_tokens: null,
                output_tokens: null,
                cached_input_tokens: null,
                pricing_source: null,
                notes: "bootstrap",
                created_at: "2026-04-21T00:00:00Z",
              },
            ]),
          );
        }
        if (
          path.endsWith("/admin/api-keys") &&
          (!init || init.method === undefined || init.method === "GET")
        ) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                account_id: 1,
                name: "key-one",
                key_prefix: "abcd1234",
                status: "active",
                per_minute: null,
                per_hour: null,
                per_day: null,
                last_used_at: null,
              },
            ]),
          );
        }
        if (path.endsWith("/admin/health")) {
          return new Response(
            JSON.stringify([
              {
                name: "codex",
                route_policy: "http-first",
                capabilities: { chat: true, stream: true, http: true, cli: false },
              },
            ]),
          );
        }
        if (path.endsWith("/admin/dashboard/summary")) {
          return new Response(
            JSON.stringify({
              total_requests: 12,
              active_api_keys: 1,
              error_rate: 0.1,
              rate_limit_hits: 0,
            }),
          );
        }
        if (path.includes("/admin/dashboard/timeseries")) {
          const url = new URL(path, "http://localhost");
          const windowValue = url.searchParams.get("window");
          const labels = windowValue === "7d" ? ["Apr 14", "Apr 15", "Apr 16", "Apr 17", "Apr 18", "Apr 19", "Apr 20"] : Array.from({ length: 24 }, (_, index) => `${String(index).padStart(2, "0")}:00`);
          const buckets = labels.map((label, index) => ({
            label,
            start_at: `2026-04-20T${String(index).padStart(2, "0")}:00:00Z`,
            total_requests: windowValue === "7d" ? (index === 6 ? 9 : 0) : (index === 23 ? 4 : 0),
            error_requests: windowValue === "7d" ? (index === 6 ? 1 : 0) : 0,
            limited_requests: windowValue === "7d" ? (index === 5 ? 2 : 0) : 0,
          }));
          return new Response(JSON.stringify({ window: windowValue ?? "24h", buckets }));
        }
        if (path.endsWith("/admin/settings/overview")) {
          return new Response(
            JSON.stringify({
              gateway_host: "127.0.0.1",
              gateway_port: 8787,
              frontend_base_url: "http://127.0.0.1:3000",
              database_scheme: "sqlite+aiosqlite",
              email_password_enabled: true,
              github_oauth_enabled: true,
              google_oauth_enabled: false,
              admin_secret_configured: true,
            }),
          );
        }
        if (path.endsWith("/admin/usage/overview")) {
          return new Response(
            JSON.stringify({
              key_activity: [
                {
                  api_key_id: 1,
                  account_id: 1,
                  name: "key-one",
                  key_prefix: "abcd1234",
                  status: "active",
                  last_used_at: null,
                  total_requests: 12,
                  limited_requests: 0,
                },
              ],
              by_provider: { codex: 12 },
              by_model: { "codex:gpt-5.4": 12 },
            }),
          );
        }
        return new Response(JSON.stringify({}), { status: 201 });
      }),
    );
  });

  it("renders the signed-in product shell navigation", async () => {
    render(<App />);

    expect(await screen.findByText("alice@example.com")).toBeTruthy();
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(screen.getByText("Providers")).toBeTruthy();
    expect(screen.getByText("Models")).toBeTruthy();
    expect(screen.getByText("Accounts")).toBeTruthy();
    expect(screen.getByText("API Keys")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Usage" })).toBeTruthy();
    expect(screen.getByText("Settings")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(screen.getByText("Platform Overview")).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "Accounts" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByRole("button", { name: "Add Account" })).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "Models" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByText("gpt-5.4")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "codex" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("$2.50 in · $15.00 out")).toBeTruthy();
    expect(screen.getByText("OpenAI API Pricing")).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "Providers" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByText("Provider Registry")).toBeTruthy();
    expect(screen.getByText("Runtime coverage")).toBeTruthy();
    expect(screen.getByRole("button", { name: "View models" })).toBeTruthy();
    expect(screen.getAllByText("OpenAI-compatible HTTP").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("link", { name: "Settings" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByText("Gateway endpoint")).toBeTruthy();
    expect(screen.getByText("GitHub OAuth: Enabled")).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "Dashboard" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    fireEvent.click(await screen.findByRole("button", { name: "7d" }));
    expect(await screen.findByText("7d default")).toBeTruthy();
    expect(screen.getByText("9 requests in window")).toBeTruthy();
  });

  it("renders disabled oauth controls when providers are not configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = typeof input === "string" ? input : input instanceof URL ? input.pathname : "url" in input ? input.url : String(input);
        if (path.endsWith("/auth/me")) {
          return new Response(JSON.stringify({ detail: "missing session cookie" }), { status: 401 });
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
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    render(<App />);

    expect(await screen.findByText("Sign in to your platform")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue with GitHub" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Continue with Google" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("GitHub needs configuration · Google needs configuration")).toBeTruthy();
  });

  it("switches the shell to Chinese and persists the locale", async () => {
    render(<App />);

    expect(await screen.findByText("alice@example.com")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "中文" })[0]);

    expect((await screen.findAllByText("总览")).length).toBeGreaterThan(0);
    expect(screen.getByText("服务提供方")).toBeTruthy();
    expect(screen.getByText("平台概览")).toBeTruthy();
    expect(window.localStorage.getItem("agh_locale")).toBe("zh");
  });
});
