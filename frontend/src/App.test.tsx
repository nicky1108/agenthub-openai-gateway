import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

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
  });
});
