import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  beforeEach(() => {
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

    fireEvent.click(screen.getByRole("link", { name: "Providers" }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await screen.findByText("Provider Registry")).toBeTruthy();
  });
});
