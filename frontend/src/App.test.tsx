import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (
          String(input).endsWith("/admin/providers") &&
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
        if (
          String(input).endsWith("/admin/accounts") &&
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
          String(input).endsWith("/admin/api-keys") &&
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
        if (String(input).endsWith("/admin/health")) {
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
        return new Response(JSON.stringify({}), { status: 201 });
      }),
    );
  });

  it("renders provider data, health data, and the add form", async () => {
    render(<App />);

    const providerRows = await screen.findAllByText(
      (_, element) =>
        element?.textContent ===
        "codex - gpt-5.4 - http-first - http:true - cli:false",
    );
    expect(providerRows.some((element) => element.tagName === "LI")).toBe(true);
    expect(screen.getByText("Accounts")).toBeTruthy();
    expect(screen.getByText("API Keys")).toBeTruthy();
    expect(screen.getByText("Providers")).toBeTruthy();
    expect(screen.getByText("Health")).toBeTruthy();
    expect(screen.getByLabelText("Provider Name")).toBeTruthy();
    expect(screen.getByLabelText("CLI Command")).toBeTruthy();
    expect(screen.getByLabelText("Account Name")).toBeTruthy();
    expect(screen.getByLabelText("API Key Name")).toBeTruthy();
  });
});
