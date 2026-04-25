import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    window.history.pushState(null, "", "/admin");
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
        if (path.endsWith("/admin/test-chat")) {
          return new Response(
            JSON.stringify({
              id: "chatcmpl-test-1",
              object: "chat.completion",
              model: "codex:gpt-5.4",
              choices: [
                {
                  index: 0,
                  message: { role: "assistant", content: "test-model-response" },
                  finish_reason: "stop",
                },
              ],
            }),
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
        if (path.endsWith("/portal/dashboard")) {
          return new Response(
            JSON.stringify({
              credits_balance: 500,
              api_key_count: 1,
              request_count_24h: 3,
              request_count_7d: 9,
              platform_requests_24h: 2,
              custom_requests_24h: 1,
              local_provider_count: 1,
              recent_usage: [
                {
                  id: 1,
                  api_key_id: 1,
                  provider_name: "minimax-cn",
                  model_id: "minimax-cn:MiniMax-M2.7",
                  outcome: "success",
                  input_tokens: null,
                  output_tokens: null,
                  cached_input_tokens: null,
                  usd_amount: null,
                  credits_charged: 0,
                  created_at: "2026-04-21T00:00:00Z",
                },
              ],
              credit_ledger: [],
            }),
          );
        }
        if (path.endsWith("/portal/catalog")) {
          return new Response(
            JSON.stringify({
              platform_models: [{ id: "codex:gpt-5.4", provider: "codex", source: "platform", enabled: true }],
              custom_models: [{ id: "minimax-cn:MiniMax-M2.7", provider: "minimax-cn", source: "custom", enabled: true }],
            }),
          );
        }
        if (path.endsWith("/portal/provider-presets")) {
          return new Response(
            JSON.stringify([
              {
                id: "minimax-cn",
                display_name: "MiniMax",
                slug: "minimax-cn",
                protocol: "openai",
                base_url: "https://api.minimaxi.com/v1",
                description: "MiniMax OpenAI-compatible API.",
                recommended_models: ["MiniMax-M2.7"],
              },
              {
                id: "other-openai-compatible",
                display_name: "Other OpenAI-compatible",
                slug: "custom-openai",
                protocol: "openai",
                base_url: "",
                description: "Use this for any provider that exposes /v1/chat/completions.",
                recommended_models: ["default"],
              },
            ]),
          );
        }
        if (path.endsWith("/portal/api-keys") && (!init || init.method === undefined || init.method === "GET")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                account_id: 1,
                name: "user-key",
                key_prefix: "user1234",
                status: "active",
                created_at: "2026-04-21T00:00:00Z",
                per_minute: null,
                per_hour: null,
                per_day: null,
                last_used_at: null,
                total_requests: 3,
                limited_requests: 0,
              },
            ]),
          );
        }
        if (path.endsWith("/portal/providers") && (!init || init.method === undefined || init.method === "GET")) {
          return new Response(
            JSON.stringify([
              {
                id: 1,
                account_id: "1",
                slug: "minimax-cn",
                name: "MiniMax CN",
                protocol: "openai",
                base_url: "https://api.minimaxi.com/v1",
                description: null,
                status: "active",
                last_probe_at: "2026-04-21T00:00:00Z",
                last_probe_ok: true,
                last_probe_model: "MiniMax-M2.7",
                last_probe_detail: null,
                last_detected_models: ["MiniMax-M2.7"],
              },
            ]),
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
    expect((await screen.findAllByText("gpt-5.4")).length).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: "codex" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getAllByText("$2.50 in · $15.00 out").length).toBeGreaterThan(0);
    expect(screen.getAllByText("OpenAI API Pricing").length).toBeGreaterThan(0);
    expect(screen.getByText("Search models")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Enabled" })).toBeTruthy();
    expect(screen.getByText("Exposure controls")).toBeTruthy();
    expect(screen.getByText("Pricing workspace")).toBeTruthy();
    expect(screen.getByText("Validation console")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Clear Transcript" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Stream Response" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel Stream" })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Test this model"), { target: { value: "hello model" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Test Message" }));
    expect((await screen.findAllByText("hello model")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("test-model-response").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("link", { name: "Providers" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByText("Provider Registry")).toBeTruthy();
    expect(screen.getByText("Selected runtime")).toBeTruthy();
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

  it("keeps the public website separate from the admin console", async () => {
    window.history.pushState(null, "", "/");

    render(<App />);

    expect(await screen.findByText("One OpenAI-compatible gateway for managed and custom models.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Admin console" })).toBeTruthy();
    expect(screen.queryByText("Platform Overview")).toBeNull();
  });

  it("renders the customer portal outside the admin sidebar", async () => {
    window.history.pushState(null, "", "/portal");

    render(<App />);

    expect(await screen.findByText("User Portal")).toBeTruthy();
    expect(screen.getByText("Admin console")).toBeTruthy();
    expect(screen.getAllByText("minimax-cn:MiniMax-M2.7").length).toBeGreaterThan(0);
    expect(screen.getByText("verified: MiniMax-M2.7")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Dashboard" })).toBeNull();
  });

  it("surfaces model test failures inline", async () => {
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
        if (path.endsWith("/admin/providers") && (!init || init.method === undefined || init.method === "GET")) {
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
        if (path.endsWith("/admin/test-chat")) {
          return new Response(JSON.stringify({ detail: "request failed: 500" }), { status: 500 });
        }
        if (path.endsWith("/admin/accounts") && (!init || init.method === undefined || init.method === "GET")) {
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
        if (path.endsWith("/admin/api-keys") && (!init || init.method === undefined || init.method === "GET")) {
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

    render(<App />);

    expect(await screen.findByText("alice@example.com")).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "Models" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findAllByText("gpt-5.4")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Test this model"), { target: { value: "hello model" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Test Message" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("request failed: 500");
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
