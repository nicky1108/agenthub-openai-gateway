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
      (_, element) => element?.textContent === "codex - gpt-5.4 - http-first",
    );
    expect(providerRows.some((element) => element.tagName === "LI")).toBe(true);
    expect(screen.getByText("Providers")).toBeTruthy();
    expect(screen.getByText("Health")).toBeTruthy();
    expect(screen.getByLabelText("Provider Name")).toBeTruthy();
  });
});
